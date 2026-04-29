"""Qt-based GUI application shell for CraftGraph (PySide6 + NodeGraphQt).

Provides the main application window with:
  - NodeGraphQt graph widget (left panel)
  - Code editor via QPlainTextEdit (right panel)
  - Menu bar (File, Edit, View)
  - Status bar

Architecture notes:
  - This module is part of the GUI layer and imports from qt_nodes.py.
  - Core modules (parser, models, graph) are imported only when needed
    (file loading), keeping startup fast.
  - The existing ``craftgraph gui`` (DearPyGui) command is preserved;
    this module powers the ``craftgraph qt-gui`` command.
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
import types
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from collections.abc import Iterator

from NodeGraphQt import NodeGraph
from PySide6 import QtCore, QtGui, QtWidgets

from craftgraph import app_dirs, config, hwnd_diag
from craftgraph.code_editor import CodeEditor
from craftgraph.highlighter import BLOCK_TYPES, FIELD_KEYS, EasyMarkupHighlighter
from craftgraph.layout_store import layout_path_for, load_layout, save_layout
from craftgraph.minimap import MinimapWidget
from craftgraph.models import SN1_CRAFT_TREE_PATH_ROOTS, BlockType, ParsedFile
from craftgraph.paths import (
    cc3_assets,
    cc3_working_files,
    default_project_folder,
    detect_subnautica_cc3_path,
)
from craftgraph.project import (
    ProjectFile,
    ProjectLoadError,
    load_project,
    new_project,
    save_project,
)
from craftgraph.qt_nodes import (
    IDENTIFIER,
    NODE_COLOR_FIELD_FOR_CLASS,
    NODE_REGISTRY,
    CraftGraphBaseNode,
    ModifiedRecipeNode,
    NodeKind,
    OrphanIngredientNode,
    all_node_classes,
)
from craftgraph.recent import RecentFiles
from craftgraph.save_utils import save_with_backup
from craftgraph.serializer import serialize_file
from craftgraph.sprite_loader import resolve_sprite, scan_assets_dir
from craftgraph.sync import (
    SyncGuard,
    UIToModelHandler,
    apply_layout,
    compute_hierarchy_layout,
    connect_hierarchy,
    connect_ingredients,
    highlight_cycle_edges,
    model_position_key,
    overlay_user_positions,
    place_orphan_nodes,
    place_variable_nodes,
    populate_graph,
    update_child_count_labels,
    update_node_issue_overlays,
)
from craftgraph.theme import (
    ACCENT_COLORS,
    ACCENT_NAMES,
    COLORBLIND_LABELS,
    COLORBLIND_MODES,
    GRID_STYLE_LABELS,
    GRID_STYLES,
    KEYBINDING_LABELS,
    PIPE_STYLE_LABELS,
    PIPE_STYLES,
    UI_SCALE_OPTIONS,
    AutocompleteSettings,
    CodeEditorSettings,
    FileWatchingSettings,
    KeybindingSettings,
    NodeEditorSettings,
    ThemeColors,
    accent_name_from_hex,
    active_theme,
    apply_colorblind_palette,
    autocomplete_settings_from_dict,
    autocomplete_settings_to_dict,
    code_editor_settings_from_dict,
    code_editor_settings_to_dict,
    file_watching_settings_from_dict,
    file_watching_settings_to_dict,
    keybinding_settings_from_dict,
    keybinding_settings_to_dict,
    node_editor_settings_from_dict,
    node_editor_settings_to_dict,
    scaled_pt,
    scaled_size,
    set_active_theme,
    theme_from_dict,
    theme_to_dict,
)
from craftgraph.tooltips import (
    NODE_DESCRIPTIONS,
    OPERATION_DESCRIPTIONS,
    VARIABLE_DESCRIPTIONS,
    enable_menu_tooltips,
    format_node_details_tooltip,
    format_tooltip,
)
from craftgraph.watcher import RecipeWatcher

if TYPE_CHECKING:
    from craftgraph.pin_registry import FieldPin
    from craftgraph.qt_variable_nodes import VariableNodeKind

_DIALOG_FLAGS = QtCore.Qt.WindowType.Dialog | QtCore.Qt.WindowType.FramelessWindowHint

_DIALOG_STYLE = (
    "QDialog {"
    "  background: rgb(40, 40, 40);"
    "  border: 1px solid rgb(100, 100, 100);"
    "  border-radius: 4px;"
    "}"
)

# Window / dialog dimensions (width, height) in pixels.
_MAIN_WINDOW_DEFAULT_SIZE = (1400, 900)
_SETTINGS_DIALOG_MIN_SIZE = (450, 350)
_SETTINGS_DIALOG_DEFAULT_SIZE = (720, 760)
# Vertical spacing applied uniformly to every QFormLayout inside the
# settings dialog so taller field widgets (spinboxes, combos) cannot
# crowd or overlap their neighbouring labels.
_SETTINGS_FORM_VSPACING = 10
_VALIDATION_DIALOG_MIN_SIZE = (480, 300)
_ID_PICKER_DIALOG_MIN_SIZE = (340, 420)
# Square swatch used in the Appearance tab for picking node colors.
_COLOR_SWATCH_PX = 36

# Timer intervals / durations in milliseconds.
_PIPE_ANIM_TICK_MS = 50              # pipe dash-offset animation tick
_TAB_FLASH_DURATION_MS = 400         # tab-bar highlight after watcher rebuild
_STATUS_ERROR_DEFAULT_MS = 5000      # default auto-dismiss for status bar errors
_DEFERRED_TICK_MS = 0                # "run after event loop drain" singleShot delay

# Pattern for extracting ItemID / TabID values from selected EasyMarkup text.
# Captures the value (a single token) so multi-line code-editor selections
# can be mapped to graph nodes for highlighting.
_ID_REFERENCE_RE = re.compile(
    r"(?:ItemID|TabID)\s*:\s*([^\s;,)]+)",
    re.IGNORECASE,
)


def _pick_from_list(
    parent: QtWidgets.QWidget,
    title: str,
    label: str,
    items: list[str],
    *,
    editable: bool = False,
) -> tuple[str, bool]:
    """Show a modal list-picker dialog contained within *parent*.

    Replaces ``QInputDialog.getItem()`` static calls so we can set
    window flags that prevent the dialog from appearing as a separate
    OS window on Windows.
    """
    dlg = QtWidgets.QInputDialog(parent, _DIALOG_FLAGS)
    dlg.setStyleSheet(_DIALOG_STYLE)
    dlg.setLabelText(label)
    dlg.setComboBoxItems(items)
    dlg.setComboBoxEditable(editable)
    dlg.move(QtGui.QCursor.pos())
    ok = dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted
    return dlg.textValue(), ok


_POPUP_MAX_VISIBLE = 12
_NEW_ITEM_PREFIX = "New item: "


def _easymarkup_keywords() -> list[str]:
    """Return the sorted list of EasyMarkup keywords (block types + field keys).

    Sourced from ``craftgraph.highlighter`` so the autocomplete suggestion set
    stays in lockstep with the syntax highlighter and serializer.
    """
    return sorted(BLOCK_TYPES | FIELD_KEYS)


class _GroupedCompleterDelegate(QtWidgets.QStyledItemDelegate):
    """Tints completer popup rows differently for keywords vs ID entries.

    The QCompleter is given a flat string list combining both groups so
    prefix filtering works normally.  This delegate paints a soft warm
    tint behind keyword rows and a soft cool tint behind ID rows so the
    user can tell which category a match belongs to without reading the
    full list.  Selection state still wins (no tint when row is selected
    so the selection colour stays readable).
    """

    _KEYWORD_BG = QtGui.QColor(160, 120, 60, 70)
    _ID_BG = QtGui.QColor(70, 110, 170, 50)
    _KEYWORD_TAG = "keyword"
    _ID_TAG = "id"
    _TAG_FG = QtGui.QColor(180, 180, 180)

    def __init__(
        self,
        keywords: set[str],
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._kw_lower: frozenset[str] = frozenset(kw.lower() for kw in keywords)

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        text = index.data(QtCore.Qt.ItemDataRole.DisplayRole) or ""
        is_keyword = text.lower() in self._kw_lower
        if not (option.state & QtWidgets.QStyle.StateFlag.State_Selected):
            painter.fillRect(
                option.rect,
                self._KEYWORD_BG if is_keyword else self._ID_BG,
            )
        super().paint(painter, option, index)
        # Right-aligned category label, dimmed so it doesn't compete with
        # the matched text.
        painter.save()
        font = painter.font()
        font.setPointSize(max(font.pointSize() - 2, 6))
        font.setItalic(True)
        painter.setFont(font)
        painter.setPen(self._TAG_FG)
        painter.drawText(
            option.rect.adjusted(0, 0, -8, 0),
            int(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter),
            self._KEYWORD_TAG if is_keyword else self._ID_TAG,
        )
        painter.restore()


class _ColorPickerSwatch(QtWidgets.QPushButton):
    """Clickable swatch that paints a fixed neutral chrome plus an inner
    colored indicator for the picked color.

    The previous implementation set ``background-color: <picked>`` on the
    whole button, which made dark or saturated picks blend into the dark
    settings dialog and washed out the swatch's outline. Here the outer
    chrome stays theme-neutral (rgb 60/60/60 with a light grey border)
    and only the inner rectangle reflects the picked color, framed by a
    light border so even fully black or fully transparent picks remain
    clearly visible.

    Stores the current hex color in ``color_hex`` so legacy callers that
    set ``btn.color_hex = "#abcdef"`` keep working.
    """

    _CHROME_STYLE = (
        "QPushButton {"
        "  background: rgb(60, 60, 60);"
        "  border: 1px solid rgb(120, 120, 120);"
        "  border-radius: 3px;"
        "}"
        "QPushButton:hover {"
        "  border: 1px solid rgb(180, 180, 180);"
        "}"
        "QPushButton:pressed {"
        "  background: rgb(50, 50, 50);"
        "}"
    )
    _INNER_BORDER = QtGui.QColor(220, 220, 220)
    _INNER_MARGIN = 5

    def __init__(
        self,
        initial: str,
        size: int = 28,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__("", parent)
        self.setFixedSize(size, size)
        self._color_hex: str = initial
        self.setStyleSheet(self._CHROME_STYLE)
        self.clicked.connect(self._open_picker)

    @property
    def color_hex(self) -> str:
        return self._color_hex

    @color_hex.setter
    def color_hex(self, value: str) -> None:
        self._color_hex = value
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(
            self._INNER_MARGIN,
            self._INNER_MARGIN,
            -self._INNER_MARGIN,
            -self._INNER_MARGIN,
        )
        painter.setBrush(QtGui.QColor(self._color_hex))
        painter.setPen(QtGui.QPen(self._INNER_BORDER, 1))
        painter.drawRoundedRect(rect, 2, 2)

    def _open_picker(self) -> None:
        current = QtGui.QColor(self._color_hex)
        chosen = QtWidgets.QColorDialog.getColor(current, self, "Pick color")
        if chosen.isValid():
            self.color_hex = chosen.name()


def _popup_style() -> str:
    """Return the autocomplete popup stylesheet, scaled to the active UI scale."""
    return (
        "QListWidget {"
        "  background: rgb(30, 30, 30);"
        "  color: rgb(200, 200, 200);"
        "  border: 1px solid rgb(80, 80, 80);"
        f"  font-size: {scaled_pt(11)}pt;"
        "}"
        "QListWidget::item:selected {"
        "  background: rgb(60, 80, 120);"
        "}"
    )


class _ViewerWheelFilter(QtCore.QObject):
    """Forward wheel events to QGraphicsProxyWidget combo boxes.

    NodeGraphQt's viewer unconditionally zooms on wheel events.
    This filter intercepts the event and forwards it to the widget
    under the cursor if it is a combo box, fixing scrollwheel-in-
    dropdown behavior.
    """

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        if event.type() != QtCore.QEvent.Type.Wheel:
            return False
        viewer = obj
        if not isinstance(viewer, QtWidgets.QGraphicsView):
            return False
        wheel = event  # QWheelEvent
        pos = wheel.position().toPoint()
        item = viewer.itemAt(pos)
        if item is None:
            return False
        proxy = None
        candidate = item
        while candidate is not None:
            if isinstance(candidate, QtWidgets.QGraphicsProxyWidget):
                proxy = candidate
                break
            candidate = candidate.parentItem()
        if proxy is None:
            return False
        widget = proxy.widget()
        if widget is None:
            return False
        # Find the actual child widget under the cursor
        local = proxy.mapFromScene(viewer.mapToScene(pos)).toPoint()
        child = widget.childAt(local)
        target = child if child is not None else widget
        if isinstance(target, (QtWidgets.QComboBox, QtWidgets.QAbstractSpinBox)):
            QtCore.QCoreApplication.sendEvent(target, event)
            return True
        return False


class _ViewerModifierSyncFilter(QtCore.QObject):
    """Sync viewer modifier states from actual event modifiers on mouse press.

    NodeGraphQt's viewer tracks ALT_state/CTRL_state/SHIFT_state via
    keyPressEvent/keyReleaseEvent.  If focus leaves the viewer between a key
    press and its release (e.g. ALT activating the menu bar), the stored state
    becomes stale.  This filter resets the states from the real modifiers on
    every mouse-button press so that stale modifier flags never affect panning
    or zooming behavior.
    """

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        if event.type() == QtCore.QEvent.Type.MouseButtonPress:
            mods = event.modifiers()
            obj.ALT_state = bool(mods & QtCore.Qt.KeyboardModifier.AltModifier)
            obj.CTRL_state = bool(mods & QtCore.Qt.KeyboardModifier.ControlModifier)
            obj.SHIFT_state = bool(mods & QtCore.Qt.KeyboardModifier.ShiftModifier)
        return False


class _ViewerDropFilter(QtCore.QObject):
    """Accept PNG file drops on the NodeGraphQt viewer.

    Drag-enter: accepts if the drag carries at least one file URL ending
    in ``.png`` (case-insensitive). Rejects everything else.

    Drop on node: if a node with a ``sprite_in`` port is under the cursor,
    sets the sprite directly on that node and records a manual override.

    Drop on empty canvas: creates a new SpriteNode at the drop position
    with ``file_path`` pre-filled.
    """

    def __init__(
        self,
        viewer: QtWidgets.QGraphicsView,
        window: CraftGraphWindow | None,
    ) -> None:
        super().__init__(viewer)
        self._viewer = viewer
        self._window = window

    def _extract_png_path(self, event: QtCore.QEvent) -> Path | None:
        """Return the first .png path from the event's mime URLs, or None."""
        mime = event.mimeData()
        if mime is None or not mime.hasUrls():
            return None
        for url in mime.urls():
            local = url.toLocalFile()
            if local and local.lower().endswith(".png"):
                return Path(local)
        return None

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        etype = event.type()

        if etype == QtCore.QEvent.Type.DragEnter:
            png_path = self._extract_png_path(event)
            if png_path is None:
                return False  # Not our drag, let default handling proceed
            event.acceptProposedAction()
            return True

        if etype == QtCore.QEvent.Type.DragMove:
            png_path = self._extract_png_path(event)
            if png_path is None:
                return False
            event.acceptProposedAction()
            return True

        if etype == QtCore.QEvent.Type.Drop:
            png_path = self._extract_png_path(event)
            if png_path is None:
                return False
            self._handle_drop(event, png_path)
            return True

        return False

    def _handle_drop(self, event: QtCore.QEvent, png_path: Path) -> None:
        """Process a PNG drop on the viewer."""
        event.acceptProposedAction()
        if self._window is None:
            return

        pos = event.position() if hasattr(event, "position") else event.posF()
        scene_pos = self._viewer.mapToScene(pos.toPoint())

        # Check if a node is under the drop cursor
        item = self._viewer.itemAt(pos.toPoint(), self._viewer.transform())
        node = self._node_from_item(item)

        if node is not None and node.get_input("sprite_in") is not None:
            # Drop on a node with sprite_in: set sprite directly
            node.set_sprite(png_path)
            item_id = getattr(node.model_ref, "item_id", None)
            if not item_id:
                item_id = getattr(node.model_ref, "tab_id", None)
            if item_id:
                self._window._manual_sprites[item_id.lower()] = png_path
            self._window.statusBar().showMessage(f"Set sprite on {node.name()}: {png_path.name}")
        else:
            # Drop on empty canvas: create a SpriteNode
            tab = self._window._active_tab
            node_cls = NODE_REGISTRY[NodeKind.SPRITE]
            type_ = f"{IDENTIFIER}.{node_cls.__name__}"
            sx, sy = self._window._find_free_position(
                tab.graph,
                scene_pos.x(),
                scene_pos.y(),
            )
            tab.graph.clear_selection()
            new_node = tab.graph.create_node(
                type_,
                name=png_path.stem,
                pos=[sx, sy],
            )
            new_node.set_property("file_path", str(png_path))
            self._window._attach_node_completers(new_node)
            self._window.statusBar().showMessage(f"Created Sprite node: {png_path.name}")

    def _node_from_item(
        self,
        item: object,
    ) -> CraftGraphBaseNode | None:
        """Walk up the QGraphicsItem hierarchy to find a CraftGraphBaseNode."""
        from NodeGraphQt.qgraphics.node_abstract import AbstractNodeItem

        candidate = item
        while candidate is not None:
            if isinstance(candidate, AbstractNodeItem):
                node = candidate.node
                if isinstance(node, CraftGraphBaseNode):
                    return node
                return None
            candidate = getattr(candidate, "parentItem", lambda: None)()
        return None


def collect_fab_tab_choices(
    parsed_files: list,
) -> tuple[list[str], list[str]]:
    """Scan parsed files for fabricator and tab choices.

    Returns (fab_choices, tab_choices) where:
      fab_choices = list of fabricator item_id strings
      tab_choices = list of resolved slash-separated path strings
    """
    fab_choices: list[str] = []
    tab_choices: list[str] = []

    for pf in parsed_files:
        for fab in pf.custom_fabricators:
            fab_choices.append(fab.item_id)
            for tab in fab.tabs:
                if tab.parent_tab_path:
                    tab_choices.append(f"{tab.parent_tab_path}/{tab.tab_id}")
                else:
                    tab_choices.append(f"{fab.item_id}/{tab.tab_id}")

        # Standalone crafting tabs (from their own files)
        for tab in pf.crafting_tabs:
            if tab.parent_tab_path:
                tab_choices.append(f"{tab.parent_tab_path}/{tab.tab_id}")

    return fab_choices, tab_choices


class _SettingsDialog(QtWidgets.QDialog):
    """Settings dialog with real tab layout for planning future settings."""

    # Emitted when the user clicks Apply.  The host window connects this to its
    # apply-settings path so changes preview live without closing the dialog.
    applied = QtCore.Signal()

    _STYLE = (
        "QDialog { background: rgb(40, 40, 40); }"
        "QTabWidget::pane { border: 1px solid rgb(80, 80, 80); background: rgb(40, 40, 40); }"
        "QTabBar::tab { background: rgb(55, 55, 55); color: rgb(200, 200, 200);"
        "  padding: 6px 16px; border: 1px solid rgb(80, 80, 80);"
        "  border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; }"
        "QTabBar::tab:selected { background: rgb(40, 40, 40); }"
        "QTabBar::tab:!selected { margin-top: 2px; }"
        "QLabel { color: rgb(200, 200, 200); }"
        "QGroupBox { color: rgb(180, 200, 255); border: 1px solid rgb(80, 80, 80);"
        "  border-radius: 4px; margin-top: 8px; padding-top: 12px; }"
        "QGroupBox::title { subcontrol-origin: margin; left: 10px; }"
        "QCheckBox, QRadioButton { color: rgb(200, 200, 200); }"
        # Split into two rules: QLineEdit / QKeySequenceEdit accept the
        # custom padding cleanly, but Qt's stylesheet handling on
        # QAbstractSpinBox / QComboBox internals interacts badly with
        # "padding: Npx Mpx;" -- the inner line-edit gets clipped to a
        # smaller height than the rendered text, cutting off digits.  Keep
        # the colours/border for those classes but skip padding so Qt's
        # native sub-control layout decides the inner geometry.
        "QLineEdit, QKeySequenceEdit { background: rgb(30, 30, 30);"
        "  color: rgb(200, 200, 200); border: 1px solid rgb(80, 80, 80);"
        "  padding: 2px 4px; }"
        "QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox {"
        "  background: rgb(30, 30, 30); color: rgb(200, 200, 200);"
        "  border: 1px solid rgb(80, 80, 80); }"
        "QSlider::groove:horizontal { background: rgb(60, 60, 60); height: 6px;"
        "  border-radius: 3px; }"
        "QSlider::handle:horizontal { background: rgb(140, 180, 255); width: 14px;"
        "  margin: -4px 0; border-radius: 7px; }"
        "QPushButton { background: rgb(60, 60, 60); color: rgb(200, 200, 200);"
        "  border: 1px solid rgb(80, 80, 80); padding: 4px 12px; border-radius: 3px; }"
        "QPushButton:hover { background: rgb(75, 75, 75); }"
        "QListWidget { background: rgb(30, 30, 30); color: rgb(200, 200, 200);"
        "  border: 1px solid rgb(80, 80, 80); }"
    )

    _ON_LAUNCH_VALUES: ClassVar[list[str]] = ["last_project", "welcome", "empty"]

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        backup_on_save: bool = False,
        auto_save_enabled: bool = False,
        auto_save_interval: int = 60,
        default_project_folder: str = "",
        subnautica_cc3_path: str = "",
        recent_max_entries: int = 10,
        on_launch: str = "welcome",
        check_for_updates: bool = True,
        theme: ThemeColors | None = None,
        node_editor: NodeEditorSettings | None = None,
        code_editor: CodeEditorSettings | None = None,
        autocomplete: AutocompleteSettings | None = None,
        file_watching: FileWatchingSettings | None = None,
        keybindings: KeybindingSettings | None = None,
        project_custom_ids: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(*scaled_size(*_SETTINGS_DIALOG_MIN_SIZE))
        self.resize(*scaled_size(*_SETTINGS_DIALOG_DEFAULT_SIZE))
        self.setStyleSheet(self._STYLE)

        self._theme = theme if theme is not None else active_theme()
        self._ne = node_editor if node_editor is not None else NodeEditorSettings()
        self._ce = code_editor if code_editor is not None else CodeEditorSettings()
        self._ac = autocomplete if autocomplete is not None else AutocompleteSettings()
        self._fw = file_watching if file_watching is not None else FileWatchingSettings()
        self._kb = keybindings if keybindings is not None else KeybindingSettings()
        self._project_custom_ids = project_custom_ids

        root = QtWidgets.QVBoxLayout(self)
        tabs = QtWidgets.QTabWidget()
        root.addWidget(tabs)

        # -- General tab widgets --
        self._backup_cb: QtWidgets.QCheckBox | None = None
        self._auto_save_cb: QtWidgets.QCheckBox | None = None
        self._auto_save_interval_spin: QtWidgets.QSpinBox | None = None
        self._project_folder_edit: QtWidgets.QLineEdit | None = None
        self._cc3_path_edit: QtWidgets.QLineEdit | None = None
        self._recent_spin: QtWidgets.QSpinBox | None = None
        self._on_launch_combo: QtWidgets.QComboBox | None = None
        self._update_check_cb: QtWidgets.QCheckBox | None = None
        # -- Appearance tab widgets --
        self._theme_combo: QtWidgets.QComboBox | None = None
        self._accent_combo: QtWidgets.QComboBox | None = None
        self._high_contrast_cb: QtWidgets.QCheckBox | None = None
        self._colorblind_combo: QtWidgets.QComboBox | None = None
        self._ui_scale_combo: QtWidgets.QComboBox | None = None
        self._cycle_edge_swatch: QtWidgets.QPushButton | None = None
        self._selected_border_swatch: QtWidgets.QPushButton | None = None
        self._editor_bg_swatch: QtWidgets.QPushButton | None = None
        self._editor_current_line_swatch: QtWidgets.QPushButton | None = None
        self._editor_gutter_bg_swatch: QtWidgets.QPushButton | None = None
        # Node color swatches keyed by NodeColors field name
        self._node_swatches: dict[str, QtWidgets.QPushButton] = {}
        # Syntax color swatches keyed by SyntaxColors field name
        self._syntax_swatches: dict[str, QtWidgets.QPushButton] = {}
        # -- Node Editor tab widgets --
        self._zoom_speed_spin: QtWidgets.QDoubleSpinBox | None = None
        self._invert_zoom_cb: QtWidgets.QCheckBox | None = None
        self._pan_mmb_cb: QtWidgets.QCheckBox | None = None
        self._show_minimap_cb: QtWidgets.QCheckBox | None = None
        self._show_grid_cb: QtWidgets.QCheckBox | None = None
        self._grid_size_spin: QtWidgets.QSpinBox | None = None
        self._snap_grid_cb: QtWidgets.QCheckBox | None = None
        self._grid_style_combo: QtWidgets.QComboBox | None = None
        # -- Nodes settings widgets --
        self._show_thumbnails_cb: QtWidgets.QCheckBox | None = None
        self._thumbnail_size_spin: QtWidgets.QSpinBox | None = None
        self._show_port_labels_cb: QtWidgets.QCheckBox | None = None
        self._warn_cycles_cb: QtWidgets.QCheckBox | None = None
        # -- Connections settings widgets --
        self._pipe_style_combo: QtWidgets.QComboBox | None = None
        self._pipe_width_spin: QtWidgets.QDoubleSpinBox | None = None
        self._animate_pipes_cb: QtWidgets.QCheckBox | None = None
        # -- Code Editor tab widgets --
        self._ce_font_combo: QtWidgets.QFontComboBox | None = None
        self._ce_font_size_spin: QtWidgets.QSpinBox | None = None
        self._ce_line_numbers_cb: QtWidgets.QCheckBox | None = None
        self._ce_highlight_line_cb: QtWidgets.QCheckBox | None = None
        self._ce_word_wrap_cb: QtWidgets.QCheckBox | None = None
        self._ce_tab_width_spin: QtWidgets.QSpinBox | None = None
        self._ce_auto_indent_cb: QtWidgets.QCheckBox | None = None
        self._ce_auto_close_cb: QtWidgets.QCheckBox | None = None
        self._ce_strip_ws_cb: QtWidgets.QCheckBox | None = None
        self._ce_debounce_enabled_cb: QtWidgets.QCheckBox | None = None
        self._ce_debounce_spin: QtWidgets.QSpinBox | None = None
        self._ce_parse_errors_cb: QtWidgets.QCheckBox | None = None
        # -- Autocomplete tab widgets --
        self._ac_scope_label: QtWidgets.QLabel | None = None
        self._ac_case_insensitive_cb: QtWidgets.QCheckBox | None = None
        self._ac_min_chars_spin: QtWidgets.QSpinBox | None = None
        self._ac_max_visible_spin: QtWidgets.QSpinBox | None = None
        self._ac_vanilla_cb: QtWidgets.QCheckBox | None = None
        self._ac_mod_compat_cb: QtWidgets.QCheckBox | None = None
        self._ac_project_ids_cb: QtWidgets.QCheckBox | None = None
        self._ac_custom_list: QtWidgets.QListWidget | None = None
        # -- File Watching tab widgets --
        self._fw_enabled_cb: QtWidgets.QCheckBox | None = None
        self._fw_debounce_enabled_cb: QtWidgets.QCheckBox | None = None
        self._fw_debounce_spin: QtWidgets.QSpinBox | None = None
        self._fw_notify_status_cb: QtWidgets.QCheckBox | None = None
        self._fw_notify_flash_cb: QtWidgets.QCheckBox | None = None
        self._fw_notify_sound_cb: QtWidgets.QCheckBox | None = None
        # -- Keybinding tab widgets --
        self._kb_edits: dict[str, QtWidgets.QKeySequenceEdit] = {}

        # Most tabs are vertical forms that grow with the number of rows;
        # wrap them in a scroll area so a small dialog still shows every
        # widget at its natural size.  Appearance has its own inner subtabs
        # (each wrapped where needed) and Widget Gallery already returns a
        # scrollable wrapper, so they're added unwrapped.
        tabs.addTab(
            self._scrollable(
                self._build_general_tab(
                    backup_on_save,
                    auto_save_enabled=auto_save_enabled,
                    auto_save_interval=auto_save_interval,
                    default_project_folder=default_project_folder,
                    subnautica_cc3_path=subnautica_cc3_path,
                    recent_max_entries=recent_max_entries,
                    on_launch=on_launch,
                    check_for_updates=check_for_updates,
                ),
            ),
            "General",
        )
        tabs.addTab(self._build_appearance_tab(), "Appearance")
        tabs.addTab(self._scrollable(self._build_node_editor_tab()), "Node Editor")
        tabs.addTab(self._scrollable(self._build_code_editor_tab()), "Code Editor")
        tabs.addTab(self._scrollable(self._build_autocomplete_tab()), "Autocomplete")
        tabs.addTab(self._scrollable(self._build_file_watching_tab()), "File Watching")
        tabs.addTab(self._scrollable(self._build_keybindings_tab()), "Keybindings")
        tabs.addTab(self._build_gallery_tab(), "Widget Gallery")

        # Apply consistent vertical spacing to every QFormLayout so that
        # taller field widgets (spinboxes, combos) keep clear of the
        # labels in adjacent rows.  Walking the dialog after construction
        # avoids editing every per-tab build method.
        for form in self.findChildren(QtWidgets.QFormLayout):
            form.setVerticalSpacing(_SETTINGS_FORM_VSPACING)

        button_row = QtWidgets.QHBoxLayout()
        restore_all_btn = QtWidgets.QPushButton("Restore All Defaults")
        restore_all_btn.setToolTip("Reset every settings tab to its built-in defaults")
        restore_all_btn.clicked.connect(self._reset_all)
        button_row.addWidget(restore_all_btn)
        button_row.addStretch(1)
        apply_btn = QtWidgets.QPushButton("Apply")
        apply_btn.setToolTip("Apply current settings without closing the dialog")
        apply_btn.clicked.connect(self.applied.emit)
        button_row.addWidget(apply_btn)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_row.addWidget(close_btn)
        root.addLayout(button_row)

    # -- Public accessors for wired settings ----------------------------------

    @property
    def backup_on_save(self) -> bool:
        if self._backup_cb is not None:
            return self._backup_cb.isChecked()
        return False

    @property
    def auto_save_enabled(self) -> bool:
        if self._auto_save_cb is not None:
            return self._auto_save_cb.isChecked()
        return False

    @property
    def auto_save_interval(self) -> int:
        if self._auto_save_interval_spin is not None:
            return self._auto_save_interval_spin.value()
        return 60

    @property
    def default_project_folder(self) -> str:
        if self._project_folder_edit is not None:
            return self._project_folder_edit.text()
        return ""

    @property
    def subnautica_cc3_path(self) -> str:
        if self._cc3_path_edit is not None:
            return self._cc3_path_edit.text()
        return ""

    @property
    def recent_max_entries(self) -> int:
        if self._recent_spin is not None:
            return self._recent_spin.value()
        return 10

    @property
    def on_launch(self) -> str:
        if self._on_launch_combo is not None:
            idx = self._on_launch_combo.currentIndex()
            return self._ON_LAUNCH_VALUES[idx]
        return "welcome"

    @property
    def check_for_updates(self) -> bool:
        if self._update_check_cb is not None:
            return self._update_check_cb.isChecked()
        return True

    @property
    def theme_colors(self) -> ThemeColors:
        """Build a :class:`ThemeColors` from the current dialog widget values."""
        from craftgraph.theme import (
            EditorColors,
            HighlightColors,
            NodeColors,
            SyntaxColors,
        )

        def _swatch_hex(btn: QtWidgets.QPushButton | None, fallback: str) -> str:
            if btn is not None:
                return btn.color_hex  # type: ignore[attr-defined]
            return fallback

        def _swatch_rgb3(
            btn: QtWidgets.QPushButton | None,
            fallback: tuple[int, int, int],
        ) -> tuple[int, int, int]:
            if btn is not None:
                return self._hex_to_rgb3(btn.color_hex)  # type: ignore[attr-defined]
            return fallback

        def _swatch_rgba4(
            btn: QtWidgets.QPushButton | None,
            fallback: tuple[int, int, int, int],
        ) -> tuple[int, int, int, int]:
            if btn is not None:
                return self._hex_to_rgba4(btn.color_hex)  # type: ignore[attr-defined]
            return fallback

        defaults = self._theme
        node_kwargs: dict[str, tuple[int, int, int]] = {}
        for field_name, btn in self._node_swatches.items():
            node_kwargs[field_name] = _swatch_rgb3(btn, getattr(defaults.node, field_name))

        syntax_kwargs: dict[str, str] = {}
        for field_name, btn in self._syntax_swatches.items():
            syntax_kwargs[field_name] = _swatch_hex(btn, getattr(defaults.syntax, field_name))

        dhl = defaults.highlight
        ded = defaults.editor
        return ThemeColors(
            node=NodeColors(**node_kwargs),
            highlight=HighlightColors(
                cycle_edge=_swatch_rgba4(self._cycle_edge_swatch, dhl.cycle_edge),
                selected_node_border=_swatch_hex(
                    self._selected_border_swatch,
                    dhl.selected_node_border,
                ),
                default_pipe=dhl.default_pipe,
            ),
            syntax=SyntaxColors(**syntax_kwargs),
            editor=EditorColors(
                background=_swatch_hex(self._editor_bg_swatch, ded.background),
                current_line=_swatch_hex(
                    self._editor_current_line_swatch,
                    ded.current_line,
                ),
                gutter_background=_swatch_hex(
                    self._editor_gutter_bg_swatch,
                    ded.gutter_background,
                ),
                gutter_text=ded.gutter_text,
            ),
            accent=self._selected_accent_hex(),
            high_contrast_borders=(
                self._high_contrast_cb.isChecked()
                if self._high_contrast_cb is not None
                else defaults.high_contrast_borders
            ),
            app_theme=self._selected_app_theme(),
            colorblind_mode=self._selected_colorblind_mode(),
            ui_scale=self._selected_ui_scale(),
        )

    @property
    def node_editor_settings(self) -> NodeEditorSettings:
        """Build a :class:`NodeEditorSettings` from the current dialog widgets."""
        d = self._ne
        return NodeEditorSettings(
            zoom_speed=(
                self._zoom_speed_spin.value()
                if self._zoom_speed_spin is not None
                else d.zoom_speed
            ),
            invert_zoom=(
                self._invert_zoom_cb.isChecked()
                if self._invert_zoom_cb is not None
                else d.invert_zoom
            ),
            pan_with_mmb=(
                self._pan_mmb_cb.isChecked() if self._pan_mmb_cb is not None else d.pan_with_mmb
            ),
            show_minimap=(
                self._show_minimap_cb.isChecked()
                if self._show_minimap_cb is not None
                else d.show_minimap
            ),
            show_grid=(
                self._show_grid_cb.isChecked() if self._show_grid_cb is not None else d.show_grid
            ),
            grid_size=(
                self._grid_size_spin.value() if self._grid_size_spin is not None else d.grid_size
            ),
            snap_to_grid=(
                self._snap_grid_cb.isChecked()
                if self._snap_grid_cb is not None
                else d.snap_to_grid
            ),
            grid_style=(
                GRID_STYLES[self._grid_style_combo.currentIndex()]
                if self._grid_style_combo is not None
                else d.grid_style
            ),
            show_thumbnails=(
                self._show_thumbnails_cb.isChecked()
                if self._show_thumbnails_cb is not None
                else d.show_thumbnails
            ),
            thumbnail_size=(
                self._thumbnail_size_spin.value()
                if self._thumbnail_size_spin is not None
                else d.thumbnail_size
            ),
            show_port_labels=(
                self._show_port_labels_cb.isChecked()
                if self._show_port_labels_cb is not None
                else d.show_port_labels
            ),
            warn_before_cycles=(
                self._warn_cycles_cb.isChecked()
                if self._warn_cycles_cb is not None
                else d.warn_before_cycles
            ),
            pipe_style=(
                PIPE_STYLES[self._pipe_style_combo.currentIndex()]
                if self._pipe_style_combo is not None
                else d.pipe_style
            ),
            pipe_width=(
                self._pipe_width_spin.value()
                if self._pipe_width_spin is not None
                else d.pipe_width
            ),
            animate_pipes=(
                self._animate_pipes_cb.isChecked()
                if self._animate_pipes_cb is not None
                else d.animate_pipes
            ),
        )

    @property
    def code_editor_settings(self) -> CodeEditorSettings:
        """Build a :class:`CodeEditorSettings` from the current dialog widgets."""
        d = self._ce
        return CodeEditorSettings(
            font_family=(
                self._ce_font_combo.currentFont().family()
                if self._ce_font_combo is not None
                else d.font_family
            ),
            font_size=(
                self._ce_font_size_spin.value()
                if self._ce_font_size_spin is not None
                else d.font_size
            ),
            show_line_numbers=(
                self._ce_line_numbers_cb.isChecked()
                if self._ce_line_numbers_cb is not None
                else d.show_line_numbers
            ),
            highlight_current_line=(
                self._ce_highlight_line_cb.isChecked()
                if self._ce_highlight_line_cb is not None
                else d.highlight_current_line
            ),
            word_wrap=(
                self._ce_word_wrap_cb.isChecked()
                if self._ce_word_wrap_cb is not None
                else d.word_wrap
            ),
            tab_width=(
                self._ce_tab_width_spin.value()
                if self._ce_tab_width_spin is not None
                else d.tab_width
            ),
            auto_indent=(
                self._ce_auto_indent_cb.isChecked()
                if self._ce_auto_indent_cb is not None
                else d.auto_indent
            ),
            auto_close_brackets=(
                self._ce_auto_close_cb.isChecked()
                if self._ce_auto_close_cb is not None
                else d.auto_close_brackets
            ),
            strip_trailing_whitespace=(
                self._ce_strip_ws_cb.isChecked()
                if self._ce_strip_ws_cb is not None
                else d.strip_trailing_whitespace
            ),
            parse_debounce_enabled=(
                self._ce_debounce_enabled_cb.isChecked()
                if self._ce_debounce_enabled_cb is not None
                else d.parse_debounce_enabled
            ),
            parse_debounce_ms=(
                self._ce_debounce_spin.value()
                if self._ce_debounce_spin is not None
                else d.parse_debounce_ms
            ),
            show_parse_errors_inline=(
                self._ce_parse_errors_cb.isChecked()
                if self._ce_parse_errors_cb is not None
                else d.show_parse_errors_inline
            ),
        )

    @property
    def autocomplete_settings(self) -> AutocompleteSettings:
        """Build :class:`AutocompleteSettings` from current dialog widgets."""
        d = self._ac
        return AutocompleteSettings(
            case_insensitive=(
                self._ac_case_insensitive_cb.isChecked()
                if self._ac_case_insensitive_cb is not None
                else d.case_insensitive
            ),
            min_prefix_length=(
                self._ac_min_chars_spin.value()
                if self._ac_min_chars_spin is not None
                else d.min_prefix_length
            ),
            max_visible_items=(
                self._ac_max_visible_spin.value()
                if self._ac_max_visible_spin is not None
                else d.max_visible_items
            ),
            include_vanilla_ids=(
                self._ac_vanilla_cb.isChecked()
                if self._ac_vanilla_cb is not None
                else d.include_vanilla_ids
            ),
            include_mod_compat_ids=(
                self._ac_mod_compat_cb.isChecked()
                if self._ac_mod_compat_cb is not None
                else d.include_mod_compat_ids
            ),
            include_project_ids=(
                self._ac_project_ids_cb.isChecked()
                if self._ac_project_ids_cb is not None
                else d.include_project_ids
            ),
            custom_ids=(
                [self._ac_custom_list.item(i).text() for i in range(self._ac_custom_list.count())]
                if self._ac_custom_list is not None
                else list(d.custom_ids)
            ),
        )

    @property
    def file_watching_settings(self) -> FileWatchingSettings:
        """Build :class:`FileWatchingSettings` from current dialog widgets."""
        d = self._fw
        return FileWatchingSettings(
            enabled=(
                self._fw_enabled_cb.isChecked()
                if self._fw_enabled_cb is not None
                else d.enabled
            ),
            debounce_enabled=(
                self._fw_debounce_enabled_cb.isChecked()
                if self._fw_debounce_enabled_cb is not None
                else d.debounce_enabled
            ),
            debounce_ms=(
                self._fw_debounce_spin.value()
                if self._fw_debounce_spin is not None
                else d.debounce_ms
            ),
            on_external_change=self._read_external_change_setting(),
            notify_status_bar=(
                self._fw_notify_status_cb.isChecked()
                if self._fw_notify_status_cb is not None
                else d.notify_status_bar
            ),
            notify_flash_tab=(
                self._fw_notify_flash_cb.isChecked()
                if self._fw_notify_flash_cb is not None
                else d.notify_flash_tab
            ),
            notify_sound_on_cycle=(
                self._fw_notify_sound_cb.isChecked()
                if self._fw_notify_sound_cb is not None
                else d.notify_sound_on_cycle
            ),
        )

    def _read_external_change_setting(self) -> str:
        """Read the On External Change radio group, falling back to default."""
        if getattr(self, "_fw_ext_prompt", None) is not None:
            if self._fw_ext_prompt.isChecked():
                return "prompt"
            if self._fw_ext_ignore.isChecked():
                return "ignore"
            return "auto_reload"
        return self._fw.on_external_change

    @property
    def keybinding_settings(self) -> KeybindingSettings:
        """Build :class:`KeybindingSettings` from current dialog widgets."""
        if not self._kb_edits:
            return self._kb
        kwargs: dict[str, str] = {}
        for field_name in KEYBINDING_LABELS:
            edit = self._kb_edits.get(field_name)
            if edit is not None:
                kwargs[field_name] = edit.keySequence().toString()
            else:
                kwargs[field_name] = getattr(self._kb, field_name)
        return KeybindingSettings(**kwargs)

    @property
    def project_custom_ids(self) -> list[str] | None:
        """Return the custom ID list for project scope, or None if global."""
        if self._project_custom_ids is None:
            return None
        lw = self._ac_custom_list
        if lw is None:
            return list(self._project_custom_ids)
        return [lw.item(i).text() for i in range(lw.count())]

    # -- Autocomplete custom ID slots --------------------------------------------

    def _on_ac_add_custom_id(self) -> None:
        text, ok = QtWidgets.QInputDialog.getText(
            self,
            "Add Custom TechType ID",
            "TechType ID:",
        )
        if not ok or not text.strip():
            return
        tid = text.strip()
        lw = self._ac_custom_list
        if lw is None:
            return
        # Duplicate check
        for i in range(lw.count()):
            if lw.item(i).text().lower() == tid.lower():
                return
        lw.addItem(tid)

    def _on_ac_remove_custom_id(self) -> None:
        lw = self._ac_custom_list
        if lw is None:
            return
        for item in reversed(lw.selectedItems()):
            lw.takeItem(lw.row(item))

    def _on_ac_export_custom_ids(self) -> None:
        """Export the Custom IDs list to a JSON file."""
        import json

        lw = self._ac_custom_list
        if lw is None:
            return

        ids = [lw.item(i).text() for i in range(lw.count())]
        if not ids:
            QtWidgets.QMessageBox.information(
                self,
                "Export IDs",
                "No custom IDs to export.",
            )
            return

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export Custom IDs",
            "custom_ids.json",
            "JSON files (*.json);;All Files (*)",
        )
        if not file_path:
            return

        try:
            Path(file_path).write_text(json.dumps(ids, indent=2), encoding="utf-8")
        except OSError as exc:
            QtWidgets.QMessageBox.warning(
                self,
                "Export Error",
                f"Failed to write file: {exc}",
            )
            return

        QtWidgets.QMessageBox.information(
            self,
            "Export IDs",
            f"Exported {len(ids)} IDs to {Path(file_path).name}.",
        )

    def _on_import_ids_from_file(self) -> None:
        """Import TechType IDs from a single recipe .txt file."""
        from craftgraph.parser import extract_ids, parse_file

        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Import IDs from Recipe File",
            "",
            "Recipe files (*.txt);;All Files (*)",
        )
        if not file_path:
            return

        p = Path(file_path)
        try:
            parsed = parse_file(p)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self,
                "Parse Error",
                f"Failed to parse {p.name}: {exc}",
            )
            return

        extracted = extract_ids([parsed])
        if not extracted:
            QtWidgets.QMessageBox.information(
                self,
                "Import IDs",
                f"No IDs found in {p.name}.",
            )
            return

        self._merge_imported_ids(extracted, p.name)

    def _merge_imported_ids(self, extracted: set[str], source_label: str) -> None:
        """Deduplicate *extracted* against the Custom IDs list and append new ones."""
        lw = self._ac_custom_list
        if lw is None:
            return

        existing_lower: set[str] = set()
        for i in range(lw.count()):
            existing_lower.add(lw.item(i).text().lower())

        new_ids = sorted(tid for tid in extracted if tid.lower() not in existing_lower)
        dupes = len(extracted) - len(new_ids)

        if not new_ids:
            QtWidgets.QMessageBox.information(
                self,
                "Import IDs",
                f"All {len(extracted)} IDs from {source_label} already in list.",
            )
            return

        for tid in new_ids:
            lw.addItem(tid)

        QtWidgets.QMessageBox.information(
            self,
            "Import IDs",
            f"Imported {len(new_ids)} new IDs ({dupes} duplicates skipped).",
        )

    def _on_import_ids_from_folder(self) -> None:
        """Import TechType IDs from all .txt files in a directory."""
        from craftgraph.parser import extract_ids, parse_directory

        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Import IDs from Mod Folder",
            "",
        )
        if not folder:
            return

        folder_path = Path(folder)
        try:
            parsed_files = parse_directory(folder_path)
        except (FileNotFoundError, NotADirectoryError) as exc:
            QtWidgets.QMessageBox.warning(
                self,
                "Import Error",
                str(exc),
            )
            return

        if not parsed_files:
            QtWidgets.QMessageBox.information(
                self,
                "Import IDs",
                f"No parseable .txt files found in {folder_path.name}.",
            )
            return

        extracted = extract_ids(parsed_files)
        if not extracted:
            QtWidgets.QMessageBox.information(
                self,
                "Import IDs",
                f"No IDs found in {folder_path.name} ({len(parsed_files)} files parsed).",
            )
            return

        self._merge_imported_ids(extracted, folder_path.name)

    # -- Appearance combo readers -----------------------------------------------

    _APP_THEME_VALUES: ClassVar[list[str]] = ["dark", "light", "system"]

    def _selected_app_theme(self) -> str:
        if self._theme_combo is not None:
            return self._APP_THEME_VALUES[self._theme_combo.currentIndex()]
        return self._theme.app_theme

    def _selected_accent_hex(self) -> str:
        if self._accent_combo is not None:
            name = self._accent_combo.currentText()
            return ACCENT_COLORS.get(name, self._theme.accent)
        return self._theme.accent

    def _selected_colorblind_mode(self) -> str:
        if self._colorblind_combo is not None:
            return COLORBLIND_MODES[self._colorblind_combo.currentIndex()]
        return self._theme.colorblind_mode

    def _selected_ui_scale(self) -> int:
        if self._ui_scale_combo is not None:
            text = self._ui_scale_combo.currentText().rstrip("%")
            if text.isdigit():
                return int(text)
        return self._theme.ui_scale

    # -- Helpers --------------------------------------------------------------

    @staticmethod
    def _scrollable(content: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Wrap *content* in a QScrollArea inside a zero-margin container."""
        wrapper = QtWidgets.QWidget()
        wrapper_layout = QtWidgets.QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        wrapper_layout.addWidget(scroll)
        return wrapper

    @staticmethod
    def _color_swatch(color: str, size: int = 28) -> QtWidgets.QPushButton:
        """Small colored button (non-functional placeholder)."""
        btn = QtWidgets.QPushButton("")
        btn.setFixedSize(size, size)
        btn.setStyleSheet(
            f"background: {color}; border: 1px solid rgb(120,120,120); border-radius: 3px;"
        )
        return btn

    @staticmethod
    def _color_picker_swatch(
        initial: str,
        size: int = 28,
    ) -> QtWidgets.QPushButton:
        """Clickable color swatch that opens QColorDialog on click.

        Returns a `_ColorPickerSwatch` instance that paints a fixed
        theme-neutral chrome with the picked color shown as a clearly
        bordered inner indicator. This keeps the swatch readable against
        the dialog background regardless of how dark or saturated the
        picked color is.
        """
        return _ColorPickerSwatch(initial, size)

    @staticmethod
    def _set_swatch_color(btn: QtWidgets.QPushButton, hex_color: str) -> None:
        """Reset a color-picker swatch button to *hex_color* (state + style)."""
        btn.color_hex = hex_color  # type: ignore[attr-defined]

    @staticmethod
    def _restore_defaults_row(handler: object) -> QtWidgets.QHBoxLayout:
        """Build a right-aligned row containing a single 'Restore Defaults' button."""
        row = QtWidgets.QHBoxLayout()
        row.addStretch()
        btn = QtWidgets.QPushButton("Restore Defaults")
        btn.setToolTip("Reset settings on this section to their built-in defaults")
        btn.clicked.connect(handler)  # type: ignore[arg-type]
        row.addWidget(btn)
        return row

    @staticmethod
    def _rgba4_to_hex(rgba: tuple[int, int, int, int]) -> str:
        """Convert an (R, G, B, A) tuple to ``#rrggbb`` hex (alpha ignored)."""
        return f"#{rgba[0]:02x}{rgba[1]:02x}{rgba[2]:02x}"

    @staticmethod
    def _hex_to_rgba4(hex_color: str) -> tuple[int, int, int, int]:
        """Convert ``#rrggbb`` hex to an (R, G, B, 255) tuple."""
        c = QtGui.QColor(hex_color)
        return (c.red(), c.green(), c.blue(), 255)

    @staticmethod
    def _rgb3_to_hex(rgb: tuple[int, int, int]) -> str:
        """Convert an (R, G, B) tuple to ``#rrggbb`` hex."""
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    @staticmethod
    def _hex_to_rgb3(hex_color: str) -> tuple[int, int, int]:
        """Convert ``#rrggbb`` hex to an (R, G, B) tuple."""
        c = QtGui.QColor(hex_color)
        return (c.red(), c.green(), c.blue())

    def _browse_project_folder(self) -> None:
        """Open a directory picker for the default project folder."""
        start = self._project_folder_edit.text() if self._project_folder_edit else ""
        chosen = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Project Folder", start)
        if chosen and self._project_folder_edit is not None:
            self._project_folder_edit.setText(chosen)

    def _browse_cc3_path(self) -> None:
        """Open a directory picker for the Subnautica CC3 plugin folder."""
        start = self._cc3_path_edit.text() if self._cc3_path_edit else ""
        chosen = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select CustomCraft3 Folder", start
        )
        if chosen and self._cc3_path_edit is not None:
            self._cc3_path_edit.setText(chosen)

    # =========================================================================
    # Tab 1: General
    # =========================================================================

    def _build_general_tab(
        self,
        backup_on_save: bool,
        *,
        auto_save_enabled: bool = False,
        auto_save_interval: int = 60,
        default_project_folder: str = "",
        subnautica_cc3_path: str = "",
        recent_max_entries: int = 10,
        on_launch: str = "welcome",
        check_for_updates: bool = True,
    ) -> QtWidgets.QWidget:
        content = QtWidgets.QWidget()
        col = QtWidgets.QVBoxLayout(content)
        col.setSpacing(12)

        # Startup
        startup = QtWidgets.QGroupBox("Startup")
        sl = QtWidgets.QFormLayout(startup)
        on_open = QtWidgets.QComboBox()
        on_open.addItems(["Open last project", "Show welcome screen", "Start empty"])
        try:
            idx = self._ON_LAUNCH_VALUES.index(on_launch)
        except ValueError:
            idx = 1  # default to "welcome"
        on_open.setCurrentIndex(idx)
        self._on_launch_combo = on_open
        sl.addRow("On launch:", on_open)
        self._recent_spin = QtWidgets.QSpinBox()
        self._recent_spin.setRange(1, 25)
        self._recent_spin.setValue(recent_max_entries)
        sl.addRow("Recent files to remember:", self._recent_spin)
        col.addWidget(startup)

        # Saving
        saving = QtWidgets.QGroupBox("Saving")
        sv = QtWidgets.QFormLayout(saving)
        self._auto_save_cb = QtWidgets.QCheckBox("Enable auto-save")
        self._auto_save_cb.setChecked(auto_save_enabled)
        sv.addRow("Auto-save:", self._auto_save_cb)
        self._auto_save_interval_spin = QtWidgets.QSpinBox()
        self._auto_save_interval_spin.setRange(10, 600)
        self._auto_save_interval_spin.setValue(auto_save_interval)
        self._auto_save_interval_spin.setSuffix(" sec")
        sv.addRow("Auto-save interval:", self._auto_save_interval_spin)
        self._backup_cb = QtWidgets.QCheckBox("Keep .bak copy")
        self._backup_cb.setChecked(backup_on_save)
        sv.addRow("Backup on save:", self._backup_cb)
        col.addWidget(saving)

        # Paths
        paths = QtWidgets.QGroupBox("Default Paths")
        pl = QtWidgets.QFormLayout(paths)
        proj_row = QtWidgets.QHBoxLayout()
        self._project_folder_edit = QtWidgets.QLineEdit()
        self._project_folder_edit.setPlaceholderText("~/Documents/CraftGraph")
        self._project_folder_edit.setText(default_project_folder)
        proj_browse = QtWidgets.QPushButton("Browse...")
        proj_browse.clicked.connect(self._browse_project_folder)
        proj_row.addWidget(self._project_folder_edit)
        proj_row.addWidget(proj_browse)
        pl.addRow("Default project folder:", proj_row)
        asset_row = QtWidgets.QHBoxLayout()
        self._cc3_path_edit = QtWidgets.QLineEdit()
        self._cc3_path_edit.setPlaceholderText("(auto-detect from Subnautica install)")
        self._cc3_path_edit.setText(subnautica_cc3_path)
        asset_browse = QtWidgets.QPushButton("Browse...")
        asset_browse.clicked.connect(self._browse_cc3_path)
        asset_row.addWidget(self._cc3_path_edit)
        asset_row.addWidget(asset_browse)
        pl.addRow("Subnautica CC3 folder:", asset_row)
        col.addWidget(paths)

        # Updates
        updates = QtWidgets.QGroupBox("Updates")
        ul = QtWidgets.QVBoxLayout(updates)
        self._update_check_cb = QtWidgets.QCheckBox("Check for updates on startup")
        self._update_check_cb.setChecked(check_for_updates)
        ul.addWidget(self._update_check_cb)
        col.addWidget(updates)

        col.addStretch()
        col.addLayout(self._restore_defaults_row(self._reset_general))
        return content

    def _reset_general(self) -> None:
        """Reset General-tab widgets to their built-in defaults."""
        if self._on_launch_combo is not None:
            self._on_launch_combo.setCurrentIndex(self._ON_LAUNCH_VALUES.index("welcome"))
        if self._recent_spin is not None:
            self._recent_spin.setValue(config.get_config().limits.recent_files_default_max)
        if self._auto_save_cb is not None:
            self._auto_save_cb.setChecked(False)
        if self._auto_save_interval_spin is not None:
            self._auto_save_interval_spin.setValue(60)
        if self._backup_cb is not None:
            self._backup_cb.setChecked(False)
        if self._project_folder_edit is not None:
            self._project_folder_edit.setText("")
        if self._cc3_path_edit is not None:
            self._cc3_path_edit.setText("")
        if self._update_check_cb is not None:
            self._update_check_cb.setChecked(True)

    # =========================================================================
    # Tab 2: Appearance (with subtabs)
    # =========================================================================

    def _build_appearance_tab(self) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        subtabs = QtWidgets.QTabWidget()
        subtabs.setObjectName("appearanceSubtabs")
        subtabs.setTabPosition(QtWidgets.QTabWidget.TabPosition.West)
        subtabs.setStyleSheet(
            "#appearanceSubtabs QTabBar::tab {"
            "  border: 1px solid rgb(80, 80, 80);"
            "  border-right: none;"
            "  border-top-left-radius: 4px;"
            "  border-top-right-radius: 0px;"
            "  border-bottom-left-radius: 4px;"
            "  padding: 8px 12px;"
            "}"
            "#appearanceSubtabs QTabBar::tab:selected {"
            "  background: rgb(40, 40, 40);"
            "  margin-top: 0px;"
            "}"
            "#appearanceSubtabs QTabBar::tab:!selected {"
            "  margin-top: 0px;"
            "  margin-left: 2px;"
            "}"
        )
        subtabs.addTab(self._build_appearance_theme(), "Theme")
        subtabs.addTab(self._build_appearance_nodes(), "Node Colors")
        subtabs.addTab(self._build_appearance_code(), "Code Colors")
        layout.addWidget(subtabs)
        return container

    def _build_appearance_theme(self) -> QtWidgets.QWidget:
        content = QtWidgets.QWidget()
        col = QtWidgets.QVBoxLayout(content)
        col.setSpacing(12)

        theme_group = QtWidgets.QGroupBox("Application Theme")
        tl = QtWidgets.QFormLayout(theme_group)
        self._theme_combo = QtWidgets.QComboBox()
        self._theme_combo.addItems(["Dark (default)", "Light", "System"])
        theme_idx = self._APP_THEME_VALUES.index(self._theme.app_theme)
        self._theme_combo.setCurrentIndex(theme_idx)
        tl.addRow("Theme:", self._theme_combo)
        self._accent_combo = QtWidgets.QComboBox()
        self._accent_combo.addItems(ACCENT_NAMES)
        accent_name = accent_name_from_hex(self._theme.accent)
        accent_idx = ACCENT_NAMES.index(accent_name)
        self._accent_combo.setCurrentIndex(accent_idx)
        tl.addRow("Accent color:", self._accent_combo)
        col.addWidget(theme_group)

        access = QtWidgets.QGroupBox("Accessibility")
        al = QtWidgets.QFormLayout(access)
        self._colorblind_combo = QtWidgets.QComboBox()
        self._colorblind_combo.addItems([COLORBLIND_LABELS[m] for m in COLORBLIND_MODES])
        cb_idx = COLORBLIND_MODES.index(self._theme.colorblind_mode)
        self._colorblind_combo.setCurrentIndex(cb_idx)
        al.addRow("Colorblind mode:", self._colorblind_combo)
        self._ui_scale_combo = QtWidgets.QComboBox()
        self._ui_scale_combo.addItems([f"{s}%" for s in UI_SCALE_OPTIONS])
        scale_idx = (
            UI_SCALE_OPTIONS.index(self._theme.ui_scale)
            if self._theme.ui_scale in UI_SCALE_OPTIONS
            else 0
        )
        self._ui_scale_combo.setCurrentIndex(scale_idx)
        al.addRow("UI scale:", self._ui_scale_combo)
        self._high_contrast_cb = QtWidgets.QCheckBox("Enable")
        self._high_contrast_cb.setChecked(self._theme.high_contrast_borders)
        al.addRow("High contrast borders:", self._high_contrast_cb)
        col.addWidget(access)

        col.addStretch()
        col.addLayout(self._restore_defaults_row(self._reset_appearance_theme))
        return content

    def _reset_appearance_theme(self) -> None:
        """Reset Appearance > Theme widgets to defaults."""
        defaults = ThemeColors()
        if self._theme_combo is not None:
            self._theme_combo.setCurrentIndex(self._APP_THEME_VALUES.index(defaults.app_theme))
        if self._accent_combo is not None:
            self._accent_combo.setCurrentIndex(
                ACCENT_NAMES.index(accent_name_from_hex(defaults.accent))
            )
        if self._colorblind_combo is not None:
            self._colorblind_combo.setCurrentIndex(COLORBLIND_MODES.index(defaults.colorblind_mode))
        if self._ui_scale_combo is not None and defaults.ui_scale in UI_SCALE_OPTIONS:
            self._ui_scale_combo.setCurrentIndex(UI_SCALE_OPTIONS.index(defaults.ui_scale))
        if self._high_contrast_cb is not None:
            self._high_contrast_cb.setChecked(defaults.high_contrast_borders)

    def _build_appearance_nodes(self) -> QtWidgets.QWidget:
        content = QtWidgets.QWidget()
        col = QtWidgets.QVBoxLayout(content)
        col.setSpacing(12)

        colors = QtWidgets.QGroupBox("Node Colors by Block Type")
        cl = QtWidgets.QFormLayout(colors)
        nc = self._theme.node
        node_types: list[tuple[str, str, tuple[int, int, int]]] = [
            ("modified_recipe", "ModifiedRecipe", nc.modified_recipe),
            ("added_recipe", "AddedRecipe", nc.added_recipe),
            ("alias_recipe", "AliasRecipe", nc.alias_recipe),
            ("custom_food", "CustomFood", nc.custom_food),
            ("fabricator", "CustomFabricator", nc.fabricator),
            ("crafting_tab", "CraftingTab", nc.crafting_tab),
            ("custom_size", "CustomSize", nc.custom_size),
            ("moved_recipe", "MovedRecipe", nc.moved_recipe),
            ("custom_bio_fuel", "CustomBioFuel", nc.custom_bio_fuel),
            ("custom_fragment_count", "CustomFragmentCount", nc.custom_fragment_count),
            ("orphan_ingredient", "Orphan Ingredient", nc.orphan_ingredient),
            ("sprite", "Sprite", nc.sprite),
        ]
        for field_name, label, rgb in node_types:
            row = QtWidgets.QHBoxLayout()
            swatch = self._color_picker_swatch(self._rgb3_to_hex(rgb))
            self._node_swatches[field_name] = swatch
            row.addWidget(swatch)
            row.addWidget(QtWidgets.QLabel(label))
            row.addStretch()
            cl.addRow(row)
        col.addWidget(colors)

        highlight = QtWidgets.QGroupBox("Highlights")
        hl = QtWidgets.QFormLayout(highlight)
        hl_row = QtWidgets.QHBoxLayout()
        self._cycle_edge_swatch = self._color_picker_swatch(
            self._rgba4_to_hex(self._theme.highlight.cycle_edge),
        )
        hl_row.addWidget(self._cycle_edge_swatch)
        hl_row.addWidget(QtWidgets.QLabel("Cycle edges"))
        hl_row.addStretch()
        hl.addRow(hl_row)
        sel_row = QtWidgets.QHBoxLayout()
        self._selected_border_swatch = self._color_picker_swatch(
            self._theme.highlight.selected_node_border,
        )
        sel_row.addWidget(self._selected_border_swatch)
        sel_row.addWidget(QtWidgets.QLabel("Selected node border"))
        sel_row.addStretch()
        hl.addRow(sel_row)
        col.addWidget(highlight)

        col.addStretch()
        col.addLayout(self._restore_defaults_row(self._reset_appearance_nodes))
        return self._scrollable(content)

    def _reset_appearance_nodes(self) -> None:
        """Reset Appearance > Node Colors swatches to defaults."""
        from craftgraph.theme import HighlightColors, NodeColors

        nc = NodeColors()
        for field_name, btn in self._node_swatches.items():
            self._set_swatch_color(btn, self._rgb3_to_hex(getattr(nc, field_name)))
        hl = HighlightColors()
        if self._cycle_edge_swatch is not None:
            self._set_swatch_color(self._cycle_edge_swatch, self._rgba4_to_hex(hl.cycle_edge))
        if self._selected_border_swatch is not None:
            self._set_swatch_color(self._selected_border_swatch, hl.selected_node_border)

    def _build_appearance_code(self) -> QtWidgets.QWidget:
        content = QtWidgets.QWidget()
        col = QtWidgets.QVBoxLayout(content)
        col.setSpacing(12)

        syntax = QtWidgets.QGroupBox("Syntax Colors")
        sl = QtWidgets.QFormLayout(syntax)
        sc = self._theme.syntax
        syntax_tokens: list[tuple[str, str, str]] = [
            ("block_type", "Keywords (block type names)", sc.block_type),
            ("field_key", "Field names (ItemID, Required, ...)", sc.field_key),
            ("string", "String values (quoted text)", sc.string),
            ("comment", "Comments (#)", sc.comment),
            ("error_underline", "Error underline", sc.error_underline),
        ]
        for field_name, label, hex_color in syntax_tokens:
            swatch = self._color_picker_swatch(hex_color)
            self._syntax_swatches[field_name] = swatch
            sl.addRow(f"{label}:", swatch)
        col.addWidget(syntax)

        editor_bg = QtWidgets.QGroupBox("Editor Background")
        el = QtWidgets.QFormLayout(editor_bg)
        self._editor_bg_swatch = self._color_picker_swatch(
            self._theme.editor.background,
        )
        el.addRow("Background:", self._editor_bg_swatch)
        self._editor_current_line_swatch = self._color_picker_swatch(
            self._theme.editor.current_line,
        )
        el.addRow("Current line highlight:", self._editor_current_line_swatch)
        self._editor_gutter_bg_swatch = self._color_picker_swatch(
            self._theme.editor.gutter_background,
        )
        el.addRow("Line number gutter:", self._editor_gutter_bg_swatch)
        col.addWidget(editor_bg)

        col.addStretch()
        col.addLayout(self._restore_defaults_row(self._reset_appearance_code))
        return content

    def _reset_appearance_code(self) -> None:
        """Reset Appearance > Code Colors swatches to defaults."""
        from craftgraph.theme import EditorColors, SyntaxColors

        sc = SyntaxColors()
        for field_name, btn in self._syntax_swatches.items():
            self._set_swatch_color(btn, getattr(sc, field_name))
        ec = EditorColors()
        if self._editor_bg_swatch is not None:
            self._set_swatch_color(self._editor_bg_swatch, ec.background)
        if self._editor_current_line_swatch is not None:
            self._set_swatch_color(self._editor_current_line_swatch, ec.current_line)
        if self._editor_gutter_bg_swatch is not None:
            self._set_swatch_color(self._editor_gutter_bg_swatch, ec.gutter_background)

    # =========================================================================
    # Tab 3: Node Editor
    # =========================================================================

    def _build_node_editor_tab(self) -> QtWidgets.QWidget:
        content = QtWidgets.QWidget()
        col = QtWidgets.QVBoxLayout(content)
        col.setSpacing(12)
        ne = self._ne

        # Navigation
        nav = QtWidgets.QGroupBox("Navigation")
        nl = QtWidgets.QFormLayout(nav)
        self._zoom_speed_spin = QtWidgets.QDoubleSpinBox()
        self._zoom_speed_spin.setRange(0.1, 5.0)
        self._zoom_speed_spin.setSingleStep(0.1)
        self._zoom_speed_spin.setValue(ne.zoom_speed)
        nl.addRow("Zoom speed:", self._zoom_speed_spin)
        self._invert_zoom_cb = QtWidgets.QCheckBox()
        self._invert_zoom_cb.setChecked(ne.invert_zoom)
        nl.addRow("Invert zoom direction:", self._invert_zoom_cb)
        self._pan_mmb_cb = QtWidgets.QCheckBox("Enable")
        self._pan_mmb_cb.setChecked(ne.pan_with_mmb)
        nl.addRow("Pan with middle mouse:", self._pan_mmb_cb)
        self._show_minimap_cb = QtWidgets.QCheckBox("Enable")
        self._show_minimap_cb.setChecked(ne.show_minimap)
        nl.addRow("Show minimap:", self._show_minimap_cb)
        col.addWidget(nav)

        # Grid
        grid = QtWidgets.QGroupBox("Grid")
        gl = QtWidgets.QFormLayout(grid)
        self._show_grid_cb = QtWidgets.QCheckBox("Enable")
        self._show_grid_cb.setChecked(ne.show_grid)
        gl.addRow("Show grid:", self._show_grid_cb)
        self._grid_size_spin = QtWidgets.QSpinBox()
        self._grid_size_spin.setRange(10, 200)
        self._grid_size_spin.setValue(ne.grid_size)
        self._grid_size_spin.setSuffix(" px")
        gl.addRow("Grid size:", self._grid_size_spin)
        self._snap_grid_cb = QtWidgets.QCheckBox("Enable")
        self._snap_grid_cb.setChecked(ne.snap_to_grid)
        gl.addRow("Snap to grid:", self._snap_grid_cb)
        self._grid_style_combo = QtWidgets.QComboBox()
        self._grid_style_combo.addItems([GRID_STYLE_LABELS[s] for s in GRID_STYLES])
        style_idx = GRID_STYLES.index(ne.grid_style) if ne.grid_style in GRID_STYLES else 1
        self._grid_style_combo.setCurrentIndex(style_idx)
        gl.addRow("Grid style:", self._grid_style_combo)
        col.addWidget(grid)

        # Connections
        conn = QtWidgets.QGroupBox("Connections")
        cnl = QtWidgets.QFormLayout(conn)
        self._pipe_style_combo = QtWidgets.QComboBox()
        self._pipe_style_combo.addItems([PIPE_STYLE_LABELS[s] for s in PIPE_STYLES])
        pipe_idx = PIPE_STYLES.index(ne.pipe_style) if ne.pipe_style in PIPE_STYLES else 0
        self._pipe_style_combo.setCurrentIndex(pipe_idx)
        cnl.addRow("Connection style:", self._pipe_style_combo)
        self._pipe_width_spin = QtWidgets.QDoubleSpinBox()
        self._pipe_width_spin.setRange(1.0, 5.0)
        self._pipe_width_spin.setSingleStep(0.5)
        self._pipe_width_spin.setValue(ne.pipe_width)
        self._pipe_width_spin.setSuffix(" px")
        cnl.addRow("Connection width:", self._pipe_width_spin)
        self._animate_pipes_cb = QtWidgets.QCheckBox()
        self._animate_pipes_cb.setChecked(ne.animate_pipes)
        cnl.addRow("Animate connections:", self._animate_pipes_cb)
        col.addWidget(conn)

        # Nodes
        nodes = QtWidgets.QGroupBox("Nodes")
        ndl = QtWidgets.QFormLayout(nodes)
        self._show_thumbnails_cb = QtWidgets.QCheckBox("Enable")
        self._show_thumbnails_cb.setChecked(ne.show_thumbnails)
        ndl.addRow("Show node thumbnails:", self._show_thumbnails_cb)
        self._thumbnail_size_spin = QtWidgets.QSpinBox()
        self._thumbnail_size_spin.setRange(24, 128)
        self._thumbnail_size_spin.setValue(ne.thumbnail_size)
        self._thumbnail_size_spin.setSuffix(" px")
        ndl.addRow("Thumbnail size:", self._thumbnail_size_spin)
        self._show_port_labels_cb = QtWidgets.QCheckBox("Enable")
        self._show_port_labels_cb.setChecked(ne.show_port_labels)
        ndl.addRow("Show port labels:", self._show_port_labels_cb)
        self._warn_cycles_cb = QtWidgets.QCheckBox("Enable")
        self._warn_cycles_cb.setChecked(ne.warn_before_cycles)
        ndl.addRow(
            "Warn before creating cycles:",
            self._warn_cycles_cb,
        )
        col.addWidget(nodes)

        col.addStretch()
        col.addLayout(self._restore_defaults_row(self._reset_node_editor))
        return content

    def _reset_node_editor(self) -> None:
        """Reset Node Editor tab widgets to defaults."""
        ne = NodeEditorSettings()
        if self._zoom_speed_spin is not None:
            self._zoom_speed_spin.setValue(ne.zoom_speed)
        if self._invert_zoom_cb is not None:
            self._invert_zoom_cb.setChecked(ne.invert_zoom)
        if self._pan_mmb_cb is not None:
            self._pan_mmb_cb.setChecked(ne.pan_with_mmb)
        if self._show_minimap_cb is not None:
            self._show_minimap_cb.setChecked(ne.show_minimap)
        if self._show_grid_cb is not None:
            self._show_grid_cb.setChecked(ne.show_grid)
        if self._grid_size_spin is not None:
            self._grid_size_spin.setValue(ne.grid_size)
        if self._snap_grid_cb is not None:
            self._snap_grid_cb.setChecked(ne.snap_to_grid)
        if self._grid_style_combo is not None and ne.grid_style in GRID_STYLES:
            self._grid_style_combo.setCurrentIndex(GRID_STYLES.index(ne.grid_style))
        if self._pipe_style_combo is not None and ne.pipe_style in PIPE_STYLES:
            self._pipe_style_combo.setCurrentIndex(PIPE_STYLES.index(ne.pipe_style))
        if self._pipe_width_spin is not None:
            self._pipe_width_spin.setValue(ne.pipe_width)
        if self._animate_pipes_cb is not None:
            self._animate_pipes_cb.setChecked(ne.animate_pipes)
        if self._show_thumbnails_cb is not None:
            self._show_thumbnails_cb.setChecked(ne.show_thumbnails)
        if self._thumbnail_size_spin is not None:
            self._thumbnail_size_spin.setValue(ne.thumbnail_size)
        if self._show_port_labels_cb is not None:
            self._show_port_labels_cb.setChecked(ne.show_port_labels)
        if self._warn_cycles_cb is not None:
            self._warn_cycles_cb.setChecked(ne.warn_before_cycles)

    # =========================================================================
    # Tab 4: Code Editor
    # =========================================================================

    def _build_code_editor_tab(self) -> QtWidgets.QWidget:
        content = QtWidgets.QWidget()
        col = QtWidgets.QVBoxLayout(content)
        col.setSpacing(12)
        ce = self._ce

        # Font
        font_group = QtWidgets.QGroupBox("Font")
        fl = QtWidgets.QFormLayout(font_group)
        self._ce_font_combo = QtWidgets.QFontComboBox()
        self._ce_font_combo.setCurrentFont(QtGui.QFont(ce.font_family))
        fl.addRow("Font family:", self._ce_font_combo)
        self._ce_font_size_spin = QtWidgets.QSpinBox()
        self._ce_font_size_spin.setRange(6, 36)
        self._ce_font_size_spin.setValue(ce.font_size)
        self._ce_font_size_spin.setSuffix(" pt")
        fl.addRow("Font size:", self._ce_font_size_spin)
        col.addWidget(font_group)

        # Display
        display = QtWidgets.QGroupBox("Display")
        dl = QtWidgets.QFormLayout(display)
        self._ce_line_numbers_cb = QtWidgets.QCheckBox("Enable")
        self._ce_line_numbers_cb.setChecked(ce.show_line_numbers)
        dl.addRow("Show line numbers:", self._ce_line_numbers_cb)
        self._ce_highlight_line_cb = QtWidgets.QCheckBox("Enable")
        self._ce_highlight_line_cb.setChecked(ce.highlight_current_line)
        dl.addRow("Highlight current line:", self._ce_highlight_line_cb)
        self._ce_word_wrap_cb = QtWidgets.QCheckBox("Enable")
        self._ce_word_wrap_cb.setChecked(ce.word_wrap)
        dl.addRow("Word wrap:", self._ce_word_wrap_cb)
        self._ce_tab_width_spin = QtWidgets.QSpinBox()
        self._ce_tab_width_spin.setRange(1, 8)
        self._ce_tab_width_spin.setValue(ce.tab_width)
        dl.addRow("Tab width (spaces):", self._ce_tab_width_spin)
        col.addWidget(display)

        # Editing
        editing = QtWidgets.QGroupBox("Editing")
        el = QtWidgets.QFormLayout(editing)
        self._ce_auto_indent_cb = QtWidgets.QCheckBox("Enable")
        self._ce_auto_indent_cb.setChecked(ce.auto_indent)
        el.addRow("Auto-indent:", self._ce_auto_indent_cb)
        self._ce_auto_close_cb = QtWidgets.QCheckBox("Enable")
        self._ce_auto_close_cb.setChecked(ce.auto_close_brackets)
        el.addRow("Auto-close brackets:", self._ce_auto_close_cb)
        self._ce_strip_ws_cb = QtWidgets.QCheckBox("On save")
        self._ce_strip_ws_cb.setChecked(ce.strip_trailing_whitespace)
        el.addRow("Strip trailing whitespace:", self._ce_strip_ws_cb)
        col.addWidget(editing)

        # Sync
        sync = QtWidgets.QGroupBox("Bidirectional Sync")
        synl = QtWidgets.QFormLayout(sync)
        self._ce_debounce_enabled_cb = QtWidgets.QCheckBox("Enable")
        self._ce_debounce_enabled_cb.setChecked(ce.parse_debounce_enabled)
        synl.addRow("Parse debounce:", self._ce_debounce_enabled_cb)
        self._ce_debounce_spin = QtWidgets.QSpinBox()
        self._ce_debounce_spin.setRange(100, 2000)
        self._ce_debounce_spin.setValue(ce.parse_debounce_ms)
        self._ce_debounce_spin.setSuffix(" ms")
        self._ce_debounce_spin.setEnabled(ce.parse_debounce_enabled)
        synl.addRow("Debounce interval:", self._ce_debounce_spin)
        self._ce_debounce_enabled_cb.toggled.connect(self._ce_debounce_spin.setEnabled)
        self._ce_parse_errors_cb = QtWidgets.QCheckBox("Enable")
        self._ce_parse_errors_cb.setChecked(ce.show_parse_errors_inline)
        synl.addRow("Show parse errors inline:", self._ce_parse_errors_cb)
        col.addWidget(sync)

        col.addStretch()
        col.addLayout(self._restore_defaults_row(self._reset_code_editor))
        return content

    def _reset_code_editor(self) -> None:
        """Reset Code Editor tab widgets to defaults."""
        ce = CodeEditorSettings()
        if self._ce_font_combo is not None:
            self._ce_font_combo.setCurrentFont(QtGui.QFont(ce.font_family))
        if self._ce_font_size_spin is not None:
            self._ce_font_size_spin.setValue(ce.font_size)
        if self._ce_line_numbers_cb is not None:
            self._ce_line_numbers_cb.setChecked(ce.show_line_numbers)
        if self._ce_highlight_line_cb is not None:
            self._ce_highlight_line_cb.setChecked(ce.highlight_current_line)
        if self._ce_word_wrap_cb is not None:
            self._ce_word_wrap_cb.setChecked(ce.word_wrap)
        if self._ce_tab_width_spin is not None:
            self._ce_tab_width_spin.setValue(ce.tab_width)
        if self._ce_auto_indent_cb is not None:
            self._ce_auto_indent_cb.setChecked(ce.auto_indent)
        if self._ce_auto_close_cb is not None:
            self._ce_auto_close_cb.setChecked(ce.auto_close_brackets)
        if self._ce_strip_ws_cb is not None:
            self._ce_strip_ws_cb.setChecked(ce.strip_trailing_whitespace)
        if self._ce_debounce_enabled_cb is not None:
            self._ce_debounce_enabled_cb.setChecked(ce.parse_debounce_enabled)
        if self._ce_debounce_spin is not None:
            self._ce_debounce_spin.setValue(ce.parse_debounce_ms)
            self._ce_debounce_spin.setEnabled(ce.parse_debounce_enabled)
        if self._ce_parse_errors_cb is not None:
            self._ce_parse_errors_cb.setChecked(ce.show_parse_errors_inline)

    # =========================================================================
    # Tab 5: Autocomplete
    # =========================================================================

    def _build_autocomplete_tab(self) -> QtWidgets.QWidget:
        content = QtWidgets.QWidget()
        col = QtWidgets.QVBoxLayout(content)
        col.setSpacing(12)
        ac = self._ac

        # ID Sources
        sources = QtWidgets.QGroupBox("TechType ID Sources")
        sl = QtWidgets.QVBoxLayout(sources)
        self._ac_vanilla_cb = QtWidgets.QCheckBox("Vanilla IDs (498 items)")
        self._ac_vanilla_cb.setChecked(ac.include_vanilla_ids)
        sl.addWidget(self._ac_vanilla_cb)
        self._ac_mod_compat_cb = QtWidgets.QCheckBox("Mod-compat IDs (120 items)")
        self._ac_mod_compat_cb.setChecked(ac.include_mod_compat_ids)
        sl.addWidget(self._ac_mod_compat_cb)
        self._ac_project_ids_cb = QtWidgets.QCheckBox("IDs from open project files")
        self._ac_project_ids_cb.setChecked(ac.include_project_ids)
        self._ac_project_ids_cb.setToolTip(
            "Placeholder -- will extract IDs from loaded files in a future update"
        )
        sl.addWidget(self._ac_project_ids_cb)
        col.addWidget(sources)

        # Custom IDs
        custom = QtWidgets.QGroupBox("Custom TechType IDs")
        cl = QtWidgets.QVBoxLayout(custom)
        self._ac_scope_label = QtWidgets.QLabel()
        if self._project_custom_ids is not None:
            self._ac_scope_label.setText("Editing: Project")
            self._ac_scope_label.setStyleSheet(
                f"color: rgb(140, 180, 255); font-weight: bold; font-size: {scaled_pt(9)}pt;"
            )
        else:
            self._ac_scope_label.setText("Editing: Global")
            self._ac_scope_label.setStyleSheet(
                f"color: rgb(160, 160, 160); font-weight: bold; font-size: {scaled_pt(9)}pt;"
            )
        cl.addWidget(self._ac_scope_label)
        self._ac_custom_list = QtWidgets.QListWidget()
        active_ids = (
            self._project_custom_ids if self._project_custom_ids is not None else ac.custom_ids
        )
        if active_ids:
            self._ac_custom_list.addItems(active_ids)
        self._ac_custom_list.setMaximumHeight(120)
        self._ac_custom_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection,
        )
        cl.addWidget(self._ac_custom_list)
        btn_row = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("Add")
        add_btn.clicked.connect(self._on_ac_add_custom_id)
        btn_row.addWidget(add_btn)
        remove_btn = QtWidgets.QPushButton("Remove")
        remove_btn.clicked.connect(self._on_ac_remove_custom_id)
        btn_row.addWidget(remove_btn)
        export_btn = QtWidgets.QPushButton("Export")
        export_btn.clicked.connect(self._on_ac_export_custom_ids)
        btn_row.addWidget(export_btn)
        btn_row.addStretch()
        cl.addLayout(btn_row)
        col.addWidget(custom)

        # Import
        imp = QtWidgets.QGroupBox("Import IDs From")
        il = QtWidgets.QVBoxLayout(imp)
        recipe_row = QtWidgets.QHBoxLayout()
        recipe_row.addWidget(QtWidgets.QLabel("Recipe file (.txt):"))
        import_file_btn = QtWidgets.QPushButton("Browse...")
        import_file_btn.clicked.connect(self._on_import_ids_from_file)
        recipe_row.addWidget(import_file_btn)
        recipe_row.addStretch()
        il.addLayout(recipe_row)
        folder_row = QtWidgets.QHBoxLayout()
        folder_row.addWidget(QtWidgets.QLabel("Mod folder (scan all):"))
        import_folder_btn = QtWidgets.QPushButton("Browse...")
        import_folder_btn.clicked.connect(self._on_import_ids_from_folder)
        folder_row.addWidget(import_folder_btn)
        folder_row.addStretch()
        il.addLayout(folder_row)
        col.addWidget(imp)

        # Behavior
        behavior = QtWidgets.QGroupBox("Behavior")
        bl = QtWidgets.QFormLayout(behavior)
        self._ac_case_insensitive_cb = QtWidgets.QCheckBox("Enable")
        self._ac_case_insensitive_cb.setChecked(ac.case_insensitive)
        bl.addRow("Case-insensitive matching:", self._ac_case_insensitive_cb)
        self._ac_min_chars_spin = QtWidgets.QSpinBox()
        self._ac_min_chars_spin.setRange(1, 5)
        self._ac_min_chars_spin.setValue(ac.min_prefix_length)
        bl.addRow("Min chars to trigger popup:", self._ac_min_chars_spin)
        self._ac_max_visible_spin = QtWidgets.QSpinBox()
        self._ac_max_visible_spin.setRange(5, 50)
        self._ac_max_visible_spin.setValue(ac.max_visible_items)
        bl.addRow("Max visible suggestions:", self._ac_max_visible_spin)
        col.addWidget(behavior)

        col.addStretch()
        col.addLayout(self._restore_defaults_row(self._reset_autocomplete))
        return content

    def _reset_autocomplete(self) -> None:
        """Reset Autocomplete tab widgets to defaults.

        Note: the Custom IDs list is intentionally preserved -- "Restore Defaults"
        only resets behavior toggles and source flags.  Use the Remove button on
        individual entries to clear the custom-ID list.
        """
        ac = AutocompleteSettings()
        if self._ac_vanilla_cb is not None:
            self._ac_vanilla_cb.setChecked(ac.include_vanilla_ids)
        if self._ac_mod_compat_cb is not None:
            self._ac_mod_compat_cb.setChecked(ac.include_mod_compat_ids)
        if self._ac_project_ids_cb is not None:
            self._ac_project_ids_cb.setChecked(ac.include_project_ids)
        if self._ac_case_insensitive_cb is not None:
            self._ac_case_insensitive_cb.setChecked(ac.case_insensitive)
        if self._ac_min_chars_spin is not None:
            self._ac_min_chars_spin.setValue(ac.min_prefix_length)
        if self._ac_max_visible_spin is not None:
            self._ac_max_visible_spin.setValue(ac.max_visible_items)

    # =========================================================================
    # Tab 6: File Watching
    # =========================================================================

    def _build_file_watching_tab(self) -> QtWidgets.QWidget:
        fw = self._fw
        content = QtWidgets.QWidget()
        col = QtWidgets.QVBoxLayout(content)
        col.setSpacing(12)

        # Watcher
        watcher = QtWidgets.QGroupBox("Watchdog File Watcher")
        wl = QtWidgets.QFormLayout(watcher)
        self._fw_enabled_cb = QtWidgets.QCheckBox("Enable")
        self._fw_enabled_cb.setChecked(fw.enabled)
        wl.addRow("Enable file watching:", self._fw_enabled_cb)
        self._fw_debounce_enabled_cb = QtWidgets.QCheckBox("Enable")
        self._fw_debounce_enabled_cb.setChecked(fw.debounce_enabled)
        wl.addRow("Debounce:", self._fw_debounce_enabled_cb)
        self._fw_debounce_spin = QtWidgets.QSpinBox()
        self._fw_debounce_spin.setRange(100, 2000)
        self._fw_debounce_spin.setValue(fw.debounce_ms)
        self._fw_debounce_spin.setSuffix(" ms")
        self._fw_debounce_spin.setEnabled(fw.debounce_enabled)
        wl.addRow("Debounce interval:", self._fw_debounce_spin)
        self._fw_debounce_enabled_cb.toggled.connect(self._fw_debounce_spin.setEnabled)
        col.addWidget(watcher)

        # Reload behavior
        reload_grp = QtWidgets.QGroupBox("On External Change")
        rl = QtWidgets.QVBoxLayout(reload_grp)
        self._fw_ext_auto = QtWidgets.QRadioButton("Auto-reload file")
        self._fw_ext_prompt = QtWidgets.QRadioButton("Prompt before reloading")
        self._fw_ext_ignore = QtWidgets.QRadioButton("Ignore external changes")
        _ext_map = {
            "auto_reload": self._fw_ext_auto,
            "prompt": self._fw_ext_prompt,
            "ignore": self._fw_ext_ignore,
        }
        _ext_map.get(fw.on_external_change, self._fw_ext_auto).setChecked(True)
        rl.addWidget(self._fw_ext_auto)
        rl.addWidget(self._fw_ext_prompt)
        rl.addWidget(self._fw_ext_ignore)
        col.addWidget(reload_grp)

        # Notifications
        notif = QtWidgets.QGroupBox("Notifications")
        nl = QtWidgets.QVBoxLayout(notif)
        self._fw_notify_status_cb = QtWidgets.QCheckBox("Show status bar message on reload")
        self._fw_notify_status_cb.setChecked(fw.notify_status_bar)
        nl.addWidget(self._fw_notify_status_cb)
        self._fw_notify_flash_cb = QtWidgets.QCheckBox("Flash tab on external change")
        self._fw_notify_flash_cb.setChecked(fw.notify_flash_tab)
        nl.addWidget(self._fw_notify_flash_cb)
        self._fw_notify_sound_cb = QtWidgets.QCheckBox("Play sound on cycle detection")
        self._fw_notify_sound_cb.setChecked(fw.notify_sound_on_cycle)
        nl.addWidget(self._fw_notify_sound_cb)
        col.addWidget(notif)

        col.addStretch()
        col.addLayout(self._restore_defaults_row(self._reset_file_watching))
        return content

    def _reset_file_watching(self) -> None:
        """Reset File Watching tab widgets to defaults."""
        fw = FileWatchingSettings()
        if self._fw_enabled_cb is not None:
            self._fw_enabled_cb.setChecked(fw.enabled)
        if self._fw_debounce_enabled_cb is not None:
            self._fw_debounce_enabled_cb.setChecked(fw.debounce_enabled)
        if self._fw_debounce_spin is not None:
            self._fw_debounce_spin.setValue(fw.debounce_ms)
            self._fw_debounce_spin.setEnabled(fw.debounce_enabled)
        ext_radios = {
            "auto_reload": self._fw_ext_auto,
            "prompt": self._fw_ext_prompt,
            "ignore": self._fw_ext_ignore,
        }
        target = ext_radios.get(fw.on_external_change)
        if target is not None:
            target.setChecked(True)
        if self._fw_notify_status_cb is not None:
            self._fw_notify_status_cb.setChecked(fw.notify_status_bar)
        if self._fw_notify_flash_cb is not None:
            self._fw_notify_flash_cb.setChecked(fw.notify_flash_tab)
        if self._fw_notify_sound_cb is not None:
            self._fw_notify_sound_cb.setChecked(fw.notify_sound_on_cycle)

    # =========================================================================
    # Tab 7: Keybindings
    # =========================================================================

    def _build_keybindings_tab(self) -> QtWidgets.QWidget:
        content = QtWidgets.QWidget()
        col = QtWidgets.QVBoxLayout(content)
        col.setSpacing(12)

        desc = QtWidgets.QLabel("Customize keyboard shortcuts for common actions.")
        desc.setStyleSheet(f"color: rgb(160, 160, 160); font-size: {scaled_pt(9)}pt;")
        col.addWidget(desc)

        shortcuts = QtWidgets.QGroupBox("Shortcuts")
        sl = QtWidgets.QFormLayout(shortcuts)
        for field_name, label in KEYBINDING_LABELS.items():
            current = getattr(self._kb, field_name, "")
            key_edit = QtWidgets.QKeySequenceEdit(QtGui.QKeySequence(current))
            self._kb_edits[field_name] = key_edit
            sl.addRow(f"{label}:", key_edit)
        col.addWidget(shortcuts)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        reset_btn = QtWidgets.QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_keybindings)
        btn_row.addWidget(reset_btn)
        col.addLayout(btn_row)

        col.addStretch()
        return content

    def _reset_keybindings(self) -> None:
        """Restore all keybinding editors to their default values."""
        defaults = KeybindingSettings()
        for field_name, edit in self._kb_edits.items():
            edit.setKeySequence(QtGui.QKeySequence(getattr(defaults, field_name)))

    def _reset_all(self) -> None:
        """Reset every settings tab to its built-in defaults (with confirmation).

        Custom IDs in the autocomplete list are preserved (matches the
        per-section Restore Defaults behavior on the Autocomplete tab).
        """
        reply = QtWidgets.QMessageBox.question(
            self,
            "Restore All Defaults",
            "Reset every setting on every tab to its built-in default?\n\n"
            "Custom IDs in your autocomplete list are preserved; everything "
            "else (paths, colors, fonts, keybindings, watcher and editor "
            "preferences) is reset.",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._reset_general()
        self._reset_appearance_theme()
        self._reset_appearance_nodes()
        self._reset_appearance_code()
        self._reset_node_editor()
        self._reset_code_editor()
        self._reset_autocomplete()
        self._reset_file_watching()
        self._reset_keybindings()

    # =========================================================================
    # Tab 8: Widget Gallery (for testing)
    # =========================================================================

    def _build_gallery_tab(self) -> QtWidgets.QWidget:
        content = QtWidgets.QWidget()
        col = QtWidgets.QVBoxLayout(content)
        col.setSpacing(12)

        col.addWidget(self._build_toggles_group())
        col.addWidget(self._build_selection_group())
        col.addWidget(self._build_numeric_group())
        col.addWidget(self._build_text_group())
        col.addWidget(self._build_color_group())
        col.addWidget(self._build_list_group())
        col.addStretch()

        return self._scrollable(content)

    # -- Widget Gallery groups ------------------------------------------------

    @staticmethod
    def _build_toggles_group() -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Toggles")
        layout = QtWidgets.QVBoxLayout(group)

        cb = QtWidgets.QCheckBox("QCheckBox -- simple on/off toggle")
        cb.setChecked(True)
        layout.addWidget(cb)

        cb_tri = QtWidgets.QCheckBox("QCheckBox -- tristate (on/partial/off)")
        cb_tri.setTristate(True)
        cb_tri.setCheckState(QtCore.Qt.CheckState.PartiallyChecked)
        layout.addWidget(cb_tri)

        radio_row = QtWidgets.QHBoxLayout()
        radio_row.addWidget(QtWidgets.QLabel("QRadioButton group:"))
        for i, text in enumerate(("Option A", "Option B", "Option C")):
            rb = QtWidgets.QRadioButton(text)
            if i == 0:
                rb.setChecked(True)
            radio_row.addWidget(rb)
        radio_row.addStretch()
        layout.addLayout(radio_row)
        return group

    @staticmethod
    def _build_selection_group() -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Selection")
        layout = QtWidgets.QFormLayout(group)

        combo = QtWidgets.QComboBox()
        combo.addItems(["Default", "Deuteranopia", "Protanopia", "Tritanopia"])
        layout.addRow("QComboBox:", combo)

        editable = QtWidgets.QComboBox()
        editable.setEditable(True)
        editable.addItems(["Preset 1", "Preset 2", "Preset 3"])
        editable.setCurrentText("")
        editable.lineEdit().setPlaceholderText("Editable -- type or pick")
        layout.addRow("QComboBox (editable):", editable)

        layout.addRow("QFontComboBox:", QtWidgets.QFontComboBox())
        return group

    @staticmethod
    def _build_numeric_group() -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Numeric")
        layout = QtWidgets.QFormLayout(group)

        spin = QtWidgets.QSpinBox()
        spin.setRange(0, 999)
        spin.setValue(48)
        layout.addRow("QSpinBox (int):", spin)

        dspin = QtWidgets.QDoubleSpinBox()
        dspin.setRange(0.0, 10.0)
        dspin.setSingleStep(0.1)
        dspin.setValue(1.5)
        layout.addRow("QDoubleSpinBox (float):", dspin)

        slider_row = QtWidgets.QHBoxLayout()
        slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(50)
        value_label = QtWidgets.QLabel("50")
        value_label.setFixedWidth(30)
        slider.valueChanged.connect(lambda v: value_label.setText(str(v)))
        slider_row.addWidget(slider)
        slider_row.addWidget(value_label)
        layout.addRow("QSlider:", slider_row)
        return group

    @staticmethod
    def _build_text_group() -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Text Input")
        layout = QtWidgets.QFormLayout(group)

        line = QtWidgets.QLineEdit()
        line.setPlaceholderText("QLineEdit -- single line text")
        layout.addRow("QLineEdit:", line)

        key = QtWidgets.QKeySequenceEdit(QtGui.QKeySequence("Ctrl+Shift+S"))
        layout.addRow("QKeySequenceEdit:", key)
        return group

    def _build_color_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Color Picker")
        layout = QtWidgets.QHBoxLayout(group)

        swatch = QtWidgets.QPushButton("")
        swatch.setFixedSize(_COLOR_SWATCH_PX, _COLOR_SWATCH_PX)
        current = QtGui.QColor(100, 180, 255)
        swatch.setStyleSheet(
            f"background: {current.name()};"
            " border: 1px solid rgb(120,120,120); border-radius: 4px;"
        )
        info = QtWidgets.QLabel(f"Current: {current.name()}")

        def _pick() -> None:
            chosen = QtWidgets.QColorDialog.getColor(current, self, "Pick a color")
            if chosen.isValid():
                swatch.setStyleSheet(
                    f"background: {chosen.name()};"
                    " border: 1px solid rgb(120,120,120); border-radius: 4px;"
                )
                info.setText(f"Current: {chosen.name()}")

        swatch.clicked.connect(_pick)
        layout.addWidget(QtWidgets.QLabel("Click swatch:"))
        layout.addWidget(swatch)
        layout.addWidget(info)
        layout.addStretch()
        return group

    def _build_list_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("List (add / remove items)")
        layout = QtWidgets.QVBoxLayout(group)

        lw = QtWidgets.QListWidget()
        lw.addItems(["ExampleItem1", "ExampleItem2", "ExampleItem3"])
        layout.addWidget(lw)

        btn_row = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("Add")
        remove_btn = QtWidgets.QPushButton("Remove")

        def _add() -> None:
            text, ok = QtWidgets.QInputDialog.getText(self, "Add Item", "Item name:")
            if ok and text.strip():
                lw.addItem(text.strip())

        def _remove() -> None:
            if lw.currentRow() >= 0:
                lw.takeItem(lw.currentRow())

        add_btn.clicked.connect(_add)
        remove_btn.clicked.connect(_remove)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        return group


class ItemIdPickerDialog(QtWidgets.QDialog):
    """Searchable item-ID picker with type-to-filter list.

    Shows all known TechType IDs in a filterable list.  The user can
    either select from the list or type a custom ID in the search field.
    """

    def __init__(
        self,
        words: list[str],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent, _DIALOG_FLAGS)
        self.setStyleSheet(_DIALOG_STYLE)
        self.setMinimumSize(*scaled_size(*_ID_PICKER_DIALOG_MIN_SIZE))

        self._words = words

        self._search = QtWidgets.QLineEdit(self)
        self._search.setPlaceholderText("Type to filter or enter custom ID...")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._filter)

        self._list = QtWidgets.QListWidget(self)
        self._list.addItems(words)
        self._list.itemDoubleClicked.connect(self._accept_item)
        self._list.currentItemChanged.connect(self._sync_search)

        self._count_label = QtWidgets.QLabel(f"{len(words)} items", self)
        self._count_label.setStyleSheet(f"color: gray; font-size: {scaled_pt(8)}pt;")

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self._search)
        layout.addWidget(self._list)
        layout.addWidget(self._count_label)
        layout.addWidget(buttons)

        self._search.setFocus()
        self.move(QtGui.QCursor.pos())

    @property
    def selected_id(self) -> str:
        """Return the chosen ID (from list selection or typed text)."""
        return self._search.text().strip()

    def _filter(self, text: str) -> None:
        text_lower = text.lower()
        self._list.clear()
        if not text_lower:
            self._list.addItems(self._words)
            self._count_label.setText(f"{len(self._words)} items")
            return
        matches = [w for w in self._words if text_lower in w.lower()]
        self._list.addItems(matches)
        self._count_label.setText(f"{len(matches)} of {len(self._words)} items")

    def _accept_item(self, item: QtWidgets.QListWidgetItem) -> None:
        self._search.setText(item.text())
        self.accept()

    def _sync_search(
        self,
        current: QtWidgets.QListWidgetItem | None,
        _previous: QtWidgets.QListWidgetItem | None,
    ) -> None:
        if current is not None:
            self._search.setText(current.text())


# -- Block type mappings ------------------------------------------------------

# Maps BlockType -> the NodeKind used for starter node spawning.
_BLOCK_TYPE_TO_NODE_KIND: dict[BlockType, NodeKind] = {
    BlockType.MODIFIED_RECIPES: NodeKind.MODIFIED_RECIPE,
    BlockType.ADDED_RECIPES: NodeKind.ADDED_RECIPE,
    BlockType.ALIAS_RECIPES: NodeKind.ALIAS_RECIPE,
    BlockType.CUSTOM_FOODS: NodeKind.CUSTOM_FOOD,
    BlockType.CUSTOM_CRAFTING_TABS: NodeKind.CRAFTING_TAB,
    BlockType.CUSTOM_FABRICATORS: NodeKind.FABRICATOR,
    BlockType.MOVED_RECIPES: NodeKind.MOVED_RECIPE,
    BlockType.CUSTOM_SIZES: NodeKind.CUSTOM_SIZE,
    BlockType.CUSTOM_BIO_FUELS: NodeKind.CUSTOM_BIO_FUEL,
    BlockType.CUSTOM_FRAGMENT_COUNTS: NodeKind.CUSTOM_FRAGMENT_COUNT,
}

# -- Block type display helpers -----------------------------------------------

# Human-readable descriptions for each CC3 block type.
_BLOCK_TYPE_LABELS: dict[BlockType, str] = {
    BlockType.MODIFIED_RECIPES: "Modified Recipes -- change existing in-game recipes",
    BlockType.ADDED_RECIPES: "Added Recipes -- new recipes at crafting paths",
    BlockType.ALIAS_RECIPES: "Alias Recipes -- clone and rename existing recipes",
    BlockType.CUSTOM_FOODS: "Custom Foods -- food or drink with nutrition values",
    BlockType.CUSTOM_CRAFTING_TABS: "Custom Crafting Tabs -- organize recipes into tabs",
    BlockType.CUSTOM_FABRICATORS: "Custom Fabricators -- custom crafting stations",
    BlockType.MOVED_RECIPES: "Moved Recipes -- relocate existing recipes",
    BlockType.CUSTOM_SIZES: "Custom Sizes -- change inventory slot sizes",
    BlockType.CUSTOM_BIO_FUELS: "Custom BioFuels -- set bioreactor energy values",
    BlockType.CUSTOM_FRAGMENT_COUNTS: "Custom Fragment Counts -- change scan requirements",
}

# Default filename stems for each block type (matches CC3 convention).
_BLOCK_TYPE_DEFAULT_NAMES: dict[BlockType, str] = {
    BlockType.MODIFIED_RECIPES: "ModifiedRecipes",
    BlockType.ADDED_RECIPES: "AddedRecipes",
    BlockType.ALIAS_RECIPES: "AliasRecipes",
    BlockType.CUSTOM_FOODS: "CustomFoods",
    BlockType.CUSTOM_CRAFTING_TABS: "CustomCraftingTabs",
    BlockType.CUSTOM_FABRICATORS: "CustomFabricators",
    BlockType.MOVED_RECIPES: "MovedRecipes",
    BlockType.CUSTOM_SIZES: "CustomSizes",
    BlockType.CUSTOM_BIO_FUELS: "CustomBioFuels",
    BlockType.CUSTOM_FRAGMENT_COUNTS: "CustomFragmentCounts",
}


class NewFileDialog(QtWidgets.QDialog):
    """Dialog for creating a new CC3 recipe file.

    Collects a filename, block type, and target directory.
    """

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        default_dir: Path | None = None,
    ) -> None:
        super().__init__(parent, _DIALOG_FLAGS)
        self.setStyleSheet(_DIALOG_STYLE)
        self.setMinimumWidth(420)

        self._default_dir = default_dir or Path.cwd()

        # Block type combo
        type_label = QtWidgets.QLabel("Block Type:")
        self._type_combo = QtWidgets.QComboBox(self)
        for bt in BlockType:
            self._type_combo.addItem(_BLOCK_TYPE_LABELS[bt], userData=bt)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)

        # Filename input
        name_label = QtWidgets.QLabel("Filename:")
        self._name_edit = QtWidgets.QLineEdit(self)
        self._name_edit.setPlaceholderText("e.g. ModifiedRecipes.txt")
        self._name_edit.setText(f"{_BLOCK_TYPE_DEFAULT_NAMES[BlockType.MODIFIED_RECIPES]}.txt")

        # Directory picker
        dir_label = QtWidgets.QLabel("Directory:")
        dir_row = QtWidgets.QHBoxLayout()
        self._dir_edit = QtWidgets.QLineEdit(self)
        self._dir_edit.setText(str(self._default_dir))
        browse_btn = QtWidgets.QPushButton("Browse...", self)
        browse_btn.setAutoDefault(False)
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(self._dir_edit)
        dir_row.addWidget(browse_btn)

        # Buttons
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setDefault(True)

        form = QtWidgets.QFormLayout(self)
        form.addRow(type_label, self._type_combo)
        form.addRow(name_label, self._name_edit)
        form.addRow(dir_label)
        form.addRow(dir_row)
        form.addRow(buttons)
        self.move(QtGui.QCursor.pos())

    @property
    def block_type(self) -> BlockType:
        return self._type_combo.currentData()

    @property
    def file_path(self) -> Path:
        name = self._name_edit.text().strip()
        if not name.endswith(".txt"):
            name += ".txt"
        return Path(self._dir_edit.text().strip()) / name

    def _on_type_changed(self, _index: int) -> None:
        bt = self._type_combo.currentData()
        if bt in _BLOCK_TYPE_DEFAULT_NAMES:
            self._name_edit.setText(f"{_BLOCK_TYPE_DEFAULT_NAMES[bt]}.txt")

    def _browse_dir(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Directory",
            self._dir_edit.text(),
        )
        if directory:
            self._dir_edit.setText(directory)

    def _validate_and_accept(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Invalid", "Filename cannot be empty.")
            return
        target_dir = Path(self._dir_edit.text().strip())
        if not target_dir.is_dir():
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid",
                f"Directory does not exist: {target_dir}",
            )
            return
        full_path = self.file_path
        if full_path.exists():
            QtWidgets.QMessageBox.warning(
                self,
                "File Exists",
                f"A file already exists at:\n{full_path}\n\nUse Open File to load it instead.",
            )
            return
        self.accept()


class NewProjectDialog(QtWidgets.QDialog):
    """Dialog for creating a new CC3 mod project directory.

    Creates a project folder with 10 starter .txt files (one per block type),
    an Assets/ directory for sprites, and a .craftgraph/ directory for layout data.
    """

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        default_dir: Path | None = None,
    ) -> None:
        super().__init__(parent, _DIALOG_FLAGS)
        self.setStyleSheet(_DIALOG_STYLE)
        self.setMinimumWidth(420)

        self._default_dir = default_dir or Path.cwd()

        # Project name
        self._name_edit = QtWidgets.QLineEdit(self)
        self._name_edit.setPlaceholderText("e.g. MySubnauticaMod")

        # Parent directory
        dir_row = QtWidgets.QHBoxLayout()
        self._dir_edit = QtWidgets.QLineEdit(self)
        self._dir_edit.setText(str(self._default_dir))
        browse_btn = QtWidgets.QPushButton("Browse...", self)
        browse_btn.setAutoDefault(False)
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(self._dir_edit)
        dir_row.addWidget(browse_btn)

        # Description (optional)
        self._desc_edit = QtWidgets.QLineEdit(self)
        self._desc_edit.setPlaceholderText("Short description of this mod project")

        # Checkboxes for optional block types (all checked by default)
        self._type_checks: dict[BlockType, QtWidgets.QCheckBox] = {}
        types_group = QtWidgets.QGroupBox("Starter Files")
        types_layout = QtWidgets.QVBoxLayout(types_group)
        for bt in BlockType:
            cb = QtWidgets.QCheckBox(bt.value, types_group)
            cb.setChecked(True)
            types_layout.addWidget(cb)
            self._type_checks[bt] = cb

        # Buttons
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setDefault(True)

        form = QtWidgets.QFormLayout(self)
        form.addRow("Project Name:", self._name_edit)
        form.addRow("Description:", self._desc_edit)
        form.addRow("Location:", dir_row)
        form.addRow(types_group)
        form.addRow(buttons)
        self.move(QtGui.QCursor.pos())

    @property
    def project_path(self) -> Path:
        return Path(self._dir_edit.text().strip()) / self._name_edit.text().strip()

    @property
    def project_name(self) -> str:
        """The project name as entered by the user."""
        return self._name_edit.text().strip()

    @property
    def description(self) -> str:
        """Optional project description."""
        return self._desc_edit.text().strip()

    @property
    def selected_block_types(self) -> list[BlockType]:
        return [bt for bt, cb in self._type_checks.items() if cb.isChecked()]

    def _browse_dir(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Parent Directory",
            self._dir_edit.text(),
        )
        if directory:
            self._dir_edit.setText(directory)

    def _validate_and_accept(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Invalid", "Project name cannot be empty.")
            return
        parent = Path(self._dir_edit.text().strip())
        if not parent.is_dir():
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid",
                f"Parent directory does not exist: {parent}",
            )
            return
        project_dir = parent / name
        if project_dir.exists():
            QtWidgets.QMessageBox.warning(
                self,
                "Already Exists",
                f"Directory already exists:\n{project_dir}",
            )
            return
        if not self.selected_block_types:
            QtWidgets.QMessageBox.warning(
                self,
                "No Files",
                "Select at least one block type for the project.",
            )
            return
        self.accept()


class QuickProjectDialog(QtWidgets.QDialog):
    """Minimal dialog to collect project name + description when promoting
    raw files to a project on save."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent, _DIALOG_FLAGS)
        self.setStyleSheet(_DIALOG_STYLE)
        self.setWindowTitle("Create CraftGraph Project")
        self.setMinimumWidth(360)

        layout = QtWidgets.QVBoxLayout(self)

        name_label = QtWidgets.QLabel("Project name:")
        self._name_edit = QtWidgets.QLineEdit()
        self._name_edit.setPlaceholderText("My Mod")
        layout.addWidget(name_label)
        layout.addWidget(self._name_edit)

        desc_label = QtWidgets.QLabel("Description (optional):")
        self._desc_edit = QtWidgets.QLineEdit()
        self._desc_edit.setPlaceholderText("Short description of this mod project")
        layout.addWidget(desc_label)
        layout.addWidget(self._desc_edit)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.move(QtGui.QCursor.pos())

    def _validate_and_accept(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Missing Name", "Please enter a project name.")
            return
        unsafe = set('<>:"/\\|?*')
        if any(c in unsafe for c in name):
            QtWidgets.QMessageBox.warning(
                self, "Invalid Name", "Project name contains invalid characters."
            )
            return
        self.accept()

    @property
    def project_name(self) -> str:
        return self._name_edit.text().strip()

    @property
    def description(self) -> str:
        return self._desc_edit.text().strip()


class NodeCompletionPopup(QtWidgets.QFrame):
    """IDE-style autocomplete popup for node text inputs.

    A single instance is shared across all nodes in the window.
    It lives outside the QGraphicsScene to avoid proxy widget focus
    issues, and positions itself via coordinate transforms.

    Behavior mirrors VS Code / PyCharm intellisense:
      - Appears while typing, filters with each keystroke
      - Up/Down navigate, Enter/Tab accept, Escape dismisses
      - Click on an item accepts it
      - Hides when no matches remain or text matches exactly
    """

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent, QtCore.Qt.WindowType.ToolTip)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        self._list = QtWidgets.QListWidget(self)
        self._list.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self._list.setStyleSheet(_popup_style())
        self._list.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self._list.itemClicked.connect(self._on_item_clicked)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._list)

        self._active_edit: QtWidgets.QLineEdit | None = None
        self._all_words: list[str] = []
        self._max_visible: int = _POPUP_MAX_VISIBLE
        self._case_insensitive: bool = True
        self.hide()

    def set_max_visible(self, count: int) -> None:
        """Set maximum visible suggestion rows."""
        self._max_visible = max(5, min(count, 50))

    def set_case_insensitive(self, enabled: bool) -> None:
        """Toggle case-insensitive matching for node popup filtering."""
        self._case_insensitive = enabled

    # -- public API -----------------------------------------------------------

    def attach(
        self,
        line_edit: QtWidgets.QLineEdit,
        words: list[str],
    ) -> None:
        """Wire *line_edit* to show this popup with *words* as candidates."""
        line_edit.textEdited.connect(
            lambda text, le=line_edit, w=words: self._on_text_edited(le, w, text),
        )
        line_edit.installEventFilter(self)

    def update_words(
        self,
        line_edit: QtWidgets.QLineEdit,
        words: list[str],
    ) -> None:
        """Replace the word list for a previously attached line edit.

        Reconnects ``textEdited`` so the new word list is used.
        """
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            line_edit.textEdited.disconnect()
        line_edit.textEdited.connect(
            lambda text, le=line_edit, w=words: self._on_text_edited(le, w, text),
        )

    # -- filtering & display --------------------------------------------------

    def _on_text_edited(
        self,
        line_edit: QtWidgets.QLineEdit,
        words: list[str],
        text: str,
    ) -> None:
        self._active_edit = line_edit
        self._all_words = words

        if not text:
            self.hide()
            return

        if self._case_insensitive:
            prefix = text.lower()
            matches = [w for w in words if prefix in w.lower()]
        else:
            matches = [w for w in words if text in w]

        self._list.clear()

        # Add real word-list matches (capped to leave room for the new-item entry)
        for m in matches[: self._max_visible - 1]:
            item = QtWidgets.QListWidgetItem(m)
            item.setToolTip(m)
            self._list.addItem(item)

        # Always append a "New item: {text}" entry as the last item,
        # styled distinctly (italic, dimmer) so it stands apart from matches.
        new_item = QtWidgets.QListWidgetItem(f"{_NEW_ITEM_PREFIX}{text}")
        new_item.setToolTip(f"Use '{text}' as a custom item")
        font = new_item.font()
        font.setItalic(True)
        new_item.setFont(font)
        new_item.setForeground(QtGui.QColor(140, 140, 140))
        self._list.addItem(new_item)

        self._list.setCurrentRow(0)

        self._position_near(line_edit)
        self.show()
        self.raise_()

    def _position_near(self, line_edit: QtWidgets.QLineEdit) -> None:
        """Place the popup just below the QLineEdit in screen coordinates.

        If the popup would extend below the visible screen area, it flips
        to appear above the line edit instead.
        """
        below = line_edit.mapToGlobal(
            QtCore.QPoint(0, line_edit.height()),
        )
        row_height = self._list.sizeHintForRow(0) or 20
        visible = min(self._list.count(), self._max_visible)
        popup_h = row_height * visible + 4
        popup_w = max(line_edit.width(), 180)
        self.setFixedWidth(popup_w)
        self.setFixedHeight(popup_h)

        # Flip above the line edit if the popup would go off-screen
        screen = line_edit.screen()
        if screen is not None:
            avail = screen.availableGeometry()
            if below.y() + popup_h > avail.bottom():
                above = line_edit.mapToGlobal(QtCore.QPoint(0, 0))
                below = QtCore.QPoint(above.x(), above.y() - popup_h)
            if below.x() + popup_w > avail.right():
                below.setX(avail.right() - popup_w)

        self.move(below)

    # -- accept / dismiss -----------------------------------------------------

    @staticmethod
    def _resolve_item_text(text: str) -> str:
        """Extract raw text from a popup item, stripping the 'New item: ' prefix."""
        if text.startswith(_NEW_ITEM_PREFIX):
            return text[len(_NEW_ITEM_PREFIX) :]
        return text

    def _accept_current(self) -> None:
        item = self._list.currentItem()
        if item is not None and self._active_edit is not None:
            self._active_edit.setText(self._resolve_item_text(item.text()))
        self.hide()

    def _on_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        if self._active_edit is not None:
            self._active_edit.setText(self._resolve_item_text(item.text()))
        self.hide()

    # -- keyboard navigation via event filter ---------------------------------

    def eventFilter(
        self,
        obj: QtCore.QObject,
        event: QtCore.QEvent,
    ) -> bool:
        if not self.isVisible() or obj is not self._active_edit:
            return False

        if event.type() != QtCore.QEvent.Type.KeyPress:
            return False

        key = event.key()

        if key == QtCore.Qt.Key.Key_Down:
            row = self._list.currentRow()
            if row < self._list.count() - 1:
                self._list.setCurrentRow(row + 1)
            return True

        if key == QtCore.Qt.Key.Key_Up:
            row = self._list.currentRow()
            if row > 0:
                self._list.setCurrentRow(row - 1)
            return True

        if key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter, QtCore.Qt.Key.Key_Tab):
            self._accept_current()
            return True

        if key == QtCore.Qt.Key.Key_Escape:
            self.hide()
            return True

        return False


@dataclass
class FileTab:
    """Everything needed for one recipe file's tab."""

    parsed_file: object  # ParsedFile
    graph: NodeGraph
    editor: CodeEditor
    history: object  # EditHistory
    ui_handler: UIToModelHandler | None
    sync_guard: SyncGuard
    model_to_node: dict[int, object] = field(default_factory=dict)
    orphan_nodes: dict[str, object] = field(default_factory=dict)
    parse_timer: QtCore.QTimer | None = None
    user_positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    cycle_count: int = 0


# ---------------------------------------------------------------------------
# Node search bar
# ---------------------------------------------------------------------------


class NodeSearchBar(QtWidgets.QFrame):
    """Inline search bar overlaid on the node graph.

    Live-filters nodes by substring across item_id / tab_id / display_name /
    node name. Enter jumps to the next match (with wrap-around), Shift+Enter
    jumps to the previous, Esc closes the bar.
    """

    next_requested = QtCore.Signal()
    prev_requested = QtCore.Signal()
    text_changed = QtCore.Signal(str)
    close_requested = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "NodeSearchBar {"
            "  background: rgb(40, 40, 40);"
            "  border: 1px solid rgb(100, 100, 100);"
            "  border-radius: 4px;"
            "}"
            "QLineEdit {"
            "  background: rgb(30, 30, 30); color: rgb(220, 220, 220);"
            "  border: 1px solid rgb(80, 80, 80); padding: 2px 4px;"
            "}"
            "QLabel { color: rgb(180, 180, 180); }"
            "QPushButton {"
            "  background: rgb(60, 60, 60); color: rgb(220, 220, 220);"
            "  border: 1px solid rgb(80, 80, 80); padding: 2px 6px;"
            "}"
            "QPushButton:hover { background: rgb(80, 80, 80); }",
        )

        self._edit = QtWidgets.QLineEdit(self)
        self._edit.setPlaceholderText("Find node (ItemID, TabID, or name)...")
        self._edit.setMinimumWidth(240)
        self._edit.textChanged.connect(self.text_changed.emit)
        self._edit.returnPressed.connect(self.next_requested.emit)

        self._count = QtWidgets.QLabel("", self)
        self._count.setMinimumWidth(80)

        prev_btn = QtWidgets.QPushButton("<", self)
        prev_btn.setAutoDefault(False)
        prev_btn.setToolTip("Previous match (Shift+Enter)")
        prev_btn.clicked.connect(self.prev_requested.emit)

        next_btn = QtWidgets.QPushButton(">", self)
        next_btn.setAutoDefault(False)
        next_btn.setToolTip("Next match (Enter)")
        next_btn.clicked.connect(self.next_requested.emit)

        close_btn = QtWidgets.QPushButton("x", self)
        close_btn.setAutoDefault(False)
        close_btn.setToolTip("Close (Esc)")
        close_btn.clicked.connect(self.close_requested.emit)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)
        layout.addWidget(self._edit)
        layout.addWidget(self._count)
        layout.addWidget(prev_btn)
        layout.addWidget(next_btn)
        layout.addWidget(close_btn)

        self.hide()

    def focus_field(self) -> None:
        """Give keyboard focus to the search line edit and select its text."""
        self._edit.setFocus(QtCore.Qt.FocusReason.ShortcutFocusReason)
        self._edit.selectAll()

    @property
    def query(self) -> str:
        return self._edit.text().strip()

    def clear_query(self) -> None:
        self._edit.clear()

    def set_match_count(self, current: int, total: int) -> None:
        """Update the "N of M" label; empty when no query."""
        if not self.query:
            self._count.setText("")
        elif total == 0:
            self._count.setText("no matches")
        else:
            self._count.setText(f"{current + 1} / {total}")

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        if key == QtCore.Qt.Key.Key_Escape:
            self.close_requested.emit()
            return
        if key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                self.prev_requested.emit()
            else:
                self.next_requested.emit()
            return
        super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class CraftGraphWindow(QtWidgets.QMainWindow):
    """Main application window for the Qt-based CraftGraph editor."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("CraftGraph")
        self.resize(*_MAIN_WINDOW_DEFAULT_SIZE)

        # -- Per-file tabs ------------------------------------------------
        self._file_tabs: list[FileTab] = []
        self._source_path = Path("untitled.txt")
        self._sprite_lookup: dict[str, Path] = {}
        self._manual_sprites: dict[str, Path] = {}
        self._id_words: list[str] | None = None
        self._path_words: list[str] = []
        self._node_popup = NodeCompletionPopup(self)
        self._backup_on_save = bool(app_dirs.load_setting("backup_on_save", False))
        self._auto_save_enabled = bool(app_dirs.load_setting("auto_save_enabled", False))
        self._auto_save_interval = int(app_dirs.load_setting("auto_save_interval", 60))
        saved_project_folder = app_dirs.load_setting("default_project_folder", "")
        self._default_project_folder: str = (
            str(saved_project_folder) if saved_project_folder else str(default_project_folder())
        )
        detected = detect_subnautica_cc3_path()
        saved_cc3 = app_dirs.load_setting("subnautica_cc3_path", "")
        self._subnautica_cc3_path: str = (
            str(saved_cc3) if saved_cc3 else (str(detected) if detected is not None else "")
        )
        self._check_for_updates = bool(app_dirs.load_setting("check_for_updates", True))

        # Scene position captured when any context menu was last opened.
        # Spawn-at-cursor callbacks use this instead of live QCursor.pos()
        # (which has drifted to the menu item the user clicked by the time
        # the callback runs).
        self._menu_invoke_scene_pos: QtCore.QPointF | None = None

        # Node search state (inline search bar, built lazily on first use).
        self._search_bar: NodeSearchBar | None = None
        self._search_matches: list[object] = []
        self._search_index: int = 0
        self._auto_save_timer = QtCore.QTimer(self)
        self._auto_save_timer.timeout.connect(self._auto_save_tick)
        self._project: ProjectFile | None = None
        app_dirs.migrate_legacy_config()
        recent_max = int(
            app_dirs.load_setting(
                "recent_max_entries", config.get_config().limits.recent_files_default_max,
            )
        )
        self._recent = RecentFiles(app_dirs.recent_files_path(), max_entries=recent_max)

        # -- Load persisted theme, node editor, and code editor settings ---------
        set_active_theme(self._load_theme())
        self._ne_settings: NodeEditorSettings = self._load_node_editor_settings()
        self._ce_settings: CodeEditorSettings = self._load_code_editor_settings()
        self._ac_settings: AutocompleteSettings = self._load_autocomplete_settings()
        self._fw_settings: FileWatchingSettings = self._load_file_watching_settings()
        self._kb_settings: KeybindingSettings = self._load_keybinding_settings()

        # -- File watcher (Watchdog) --
        self._recipe_watcher: RecipeWatcher | None = None

        # -- Build UI ---------------------------------------------------------
        # Status bar must be set up before the menu bar so the
        # `View > Show Handle Counter` toggle can wire its initial visibility
        # against the existing `_hwnd_counter` widget.
        self._setup_status_bar()
        self._setup_menu_bar()
        self._setup_central_widget()
        self._setup_id_reference_panel()

        # Apply theme stylesheet (dark/light/system + accent + high-contrast)
        self._apply_theme(active_theme())

        # Apply node editor settings (grid, minimap, etc.)
        self._apply_node_editor_settings(self._ne_settings)

        # Apply keybinding settings (shortcuts on menu actions)
        self._apply_keybinding_settings(self._kb_settings)

        # Apply autocomplete settings to node popup
        self._node_popup.set_max_visible(self._ac_settings.max_visible_items)
        self._node_popup.set_case_insensitive(self._ac_settings.case_insensitive)

        # -- Apply persisted auto-save setting --------------------------------
        if self._auto_save_enabled:
            self._set_auto_save(enabled=True, interval=self._auto_save_interval)

        # -- Launch flow: decide what to show on startup --
        on_launch = app_dirs.load_setting("on_launch", "welcome")
        if on_launch == "empty":
            self._show_editor()
        elif on_launch == "last_project":
            entries = self._recent.entries
            if entries and Path(entries[0].path).exists():
                first = entries[0]
                if first.entry_type == "project":
                    self.open_project_file(Path(first.path))
                else:
                    self.load_recipes(Path(first.path))
                    self._recent.add(Path(first.path), "folder")
                    self._rebuild_recent_menu()

        # -- Deferred update check (runs after the event loop starts) --
        if self._check_for_updates:
            QtCore.QTimer.singleShot(_DEFERRED_TICK_MS, self._run_update_check)

    # -- Properties -----------------------------------------------------------

    @property
    def _active_tab(self) -> FileTab:
        """The currently active FileTab."""
        idx = self._tab_bar.currentIndex()
        if idx < 0 or idx >= len(self._file_tabs):
            return self._file_tabs[0]
        return self._file_tabs[idx]

    @property
    def graph(self) -> NodeGraph:
        return self._active_tab.graph

    @property
    def code_editor(self) -> CodeEditor:
        return self._active_tab.editor

    @property
    def sync_guard(self) -> SyncGuard:
        return self._active_tab.sync_guard

    @property
    def model_to_node(self) -> dict[int, object]:
        return self._active_tab.model_to_node

    @property
    def edit_history(self) -> object:
        return self._active_tab.history

    @property
    def ui_handler(self) -> UIToModelHandler | None:
        return self._active_tab.ui_handler

    # -- Menu bar -------------------------------------------------------------

    def _setup_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("&File")

        self._new_file_action = QtGui.QAction("&New File...", self)
        self._new_file_action.triggered.connect(self._on_new_file)
        file_menu.addAction(self._new_file_action)

        new_project_action = QtGui.QAction("New &Project...", self)
        new_project_action.triggered.connect(self._on_new_project)
        file_menu.addAction(new_project_action)

        file_menu.addSeparator()

        open_folder_action = QtGui.QAction("Open &Folder...", self)
        open_folder_action.setShortcut(QtGui.QKeySequence.StandardKey.Open)
        open_folder_action.triggered.connect(self._on_open_folder)
        file_menu.addAction(open_folder_action)

        open_file_action = QtGui.QAction("Open &File...", self)
        open_file_action.triggered.connect(self._on_open_file)
        file_menu.addAction(open_file_action)

        open_project_action = QtGui.QAction("Open Pro&ject...", self)
        open_project_action.triggered.connect(self._on_open_project)
        file_menu.addAction(open_project_action)

        self._recent_menu = file_menu.addMenu("Open &Recent")
        self._rebuild_recent_menu()

        file_menu.addSeparator()

        self._save_action = QtGui.QAction("&Save", self)
        self._save_action.triggered.connect(self._on_save)
        file_menu.addAction(self._save_action)

        self._save_all_action = QtGui.QAction("Save &All", self)
        self._save_all_action.triggered.connect(self._on_save_all)
        file_menu.addAction(self._save_all_action)

        self._export_action = QtGui.QAction("&Export...", self)
        self._export_action.setEnabled(False)
        file_menu.addAction(self._export_action)

        file_menu.addSeparator()

        exit_action = QtGui.QAction("E&xit", self)
        exit_action.setShortcut(QtGui.QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        # Note: Ctrl+Z / Ctrl+Y shortcuts are already handled by
        # NodeGraphQt's internal NodeViewer undo/redo actions. Adding
        # duplicate shortcuts here causes "Ambiguous shortcut overload"
        # warnings. Menu items are still clickable without hotkeys.
        edit_menu = menu_bar.addMenu("&Edit")

        self._undo_action = QtGui.QAction("&Undo", self)
        self._undo_action.triggered.connect(self._on_undo)
        edit_menu.addAction(self._undo_action)

        self._redo_action = QtGui.QAction("&Redo", self)
        self._redo_action.triggered.connect(self._on_redo)
        edit_menu.addAction(self._redo_action)

        edit_menu.addSeparator()

        self._find_action = QtGui.QAction("&Find Node...", self)
        self._find_action.triggered.connect(self._find_node_by_id)
        edit_menu.addAction(self._find_action)

        # View menu
        view_menu = menu_bar.addMenu("&View")
        view_menu.setObjectName("view_menu")

        self._minimap_action = QtGui.QAction("&Minimap", self)
        self._minimap_action.setCheckable(True)
        self._minimap_action.setChecked(True)
        self._minimap_action.triggered.connect(self._on_toggle_minimap)
        view_menu.addAction(self._minimap_action)

        self._reset_layout_action = QtGui.QAction("&Reset Layout", self)
        self._reset_layout_action.triggered.connect(self._on_reset_layout)
        view_menu.addAction(self._reset_layout_action)

        view_menu.addSeparator()
        self._hwnd_counter_action = QtGui.QAction("Show &Handle Counter", self)
        self._hwnd_counter_action.setCheckable(True)
        initial_visible = bool(app_dirs.load_setting("show_hwnd_counter", False))
        self._hwnd_counter_action.setChecked(initial_visible)
        self._hwnd_counter.setVisible(initial_visible)
        self._hwnd_counter_action.toggled.connect(self._on_toggle_hwnd_counter)
        view_menu.addAction(self._hwnd_counter_action)

        # Help menu
        help_menu = menu_bar.addMenu("&Help")

        self._settings_action = QtGui.QAction("&Settings...", self)
        self._settings_action.triggered.connect(self._on_settings)
        help_menu.addAction(self._settings_action)

        self._dump_hwnd_action = QtGui.QAction("Dump Handle &Snapshot...", self)
        self._dump_hwnd_action.triggered.connect(self._on_dump_handle_snapshot)
        help_menu.addAction(self._dump_hwnd_action)

        help_menu.addSeparator()

        about_action = QtGui.QAction("&About CraftGraph", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    # -- Central widget (splitter layout) -------------------------------------

    def _setup_central_widget(self) -> None:
        central = QtWidgets.QWidget()
        root_layout = QtWidgets.QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._main_stack = QtWidgets.QStackedWidget()

        # -- Index 0: Welcome screen --
        from craftgraph.welcome import WelcomeWidget

        on_launch = app_dirs.load_setting("on_launch", "welcome")
        self._welcome = WelcomeWidget(
            self._recent.entries,
            on_open_recent=self._welcome_open_recent,
            on_new_project=self._on_new_project,
            on_open_folder=self._on_open_folder,
            on_open_project=self._on_open_project,
            on_startup_toggle=self._on_startup_toggle,
            show_on_startup=(on_launch == "welcome"),
        )
        self._main_stack.addWidget(self._welcome)

        # -- Index 1: Editor (tab bar + splitter) --
        editor_container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(editor_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tab_bar = QtWidgets.QTabBar()
        self._tab_bar.setTabsClosable(False)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tab_bar)

        self._splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

        # Wrap graph_stack in a plain container so the minimap can overlay
        # on top without being managed by QStackedWidget.
        self._graph_container = QtWidgets.QWidget()
        container_layout = QtWidgets.QVBoxLayout(self._graph_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        self._graph_stack = QtWidgets.QStackedWidget()
        container_layout.addWidget(self._graph_stack)
        self._splitter.addWidget(self._graph_container)

        self._editor_stack = QtWidgets.QStackedWidget()
        self._splitter.addWidget(self._editor_stack)

        self._splitter.setSizes([980, 420])
        layout.addWidget(self._splitter)

        self._main_stack.addWidget(editor_container)

        # Minimap overlay (anchored to bottom-right of graph container)
        self._minimap = MinimapWidget(parent=self._graph_container)
        self._minimap.raise_()
        self._graph_container.installEventFilter(self)

        root_layout.addWidget(self._main_stack)
        self.setCentralWidget(central)

        # Create placeholder tab (shown before files are loaded)
        self._create_placeholder_tab()

    def _create_placeholder_tab(self) -> None:
        """Set up the initial empty tab shown before any files are loaded."""
        graph = NodeGraph()
        graph.set_acyclic(False)
        for cls in all_node_classes():
            graph.register_node(cls)
        from craftgraph.qt_variable_nodes import all_variable_node_classes

        for cls in all_variable_node_classes():
            graph.register_node(cls)

        editor = CodeEditor()
        editor.setPlaceholderText("Open a recipe file to view its source...")
        EasyMarkupHighlighter(editor.document())
        self._setup_autocomplete_for(editor)
        self._apply_code_editor_settings_to(editor, self._ce_settings)
        self._apply_autocomplete_settings_to(editor, self._ac_settings)

        from craftgraph.commands import EditHistory

        tab = FileTab(
            parsed_file=None,  # type: ignore[arg-type]
            graph=graph,
            editor=editor,
            history=EditHistory(on_change=self._on_model_changed),
            ui_handler=None,
            sync_guard=SyncGuard(),
        )
        self._file_tabs.append(tab)

        self._graph_stack.addWidget(graph.widget)
        self._editor_stack.addWidget(editor)
        self._tab_bar.addTab("untitled")
        self._tab_bar.setTabToolTip(self._tab_bar.count() - 1, "untitled")

        self._setup_context_menus_for(graph)
        self._install_viewer_patches(graph)

        # Snap-to-grid for placeholder tab
        def _on_placeholder_moved(moved: dict) -> None:
            self._snap_moved_nodes(graph, moved)

        graph.viewer().moved_nodes.connect(_on_placeholder_moved)

        self._minimap.attach(graph)

    def _on_tab_changed(self, index: int) -> None:
        """Switch both stacked widgets to the selected file tab."""
        if index < 0 or index >= len(self._file_tabs):
            return
        self._graph_stack.setCurrentIndex(index)
        self._editor_stack.setCurrentIndex(index)

        tab = self._file_tabs[index]
        if self._project is not None:
            name = f"CraftGraph - {self._project.name}"
            if tab.parsed_file is not None:
                name += f" [{tab.parsed_file.source_path.name}]"
        else:
            name = "CraftGraph"
            if tab.parsed_file is not None:
                name += f" - {tab.parsed_file.source_path.name}"
        if hasattr(tab.history, "is_dirty") and tab.history.is_dirty:
            name += " *"
        self.setWindowTitle(name)

        self._attach_minimap_to_current_tab()

    # -- Minimap --------------------------------------------------------------

    def _position_minimap(self) -> None:
        """Anchor the minimap to the bottom-right corner of the graph panel."""
        margin = 8
        parent = self._graph_container
        x = parent.width() - self._minimap.width() - margin
        y = parent.height() - self._minimap.height() - margin
        if x < 0 or y < 0:
            return  # Window not sized yet
        self._minimap.move(x, y)
        self._minimap.raise_()

    def _on_toggle_minimap(self, checked: bool) -> None:
        self._minimap.setVisible(checked)

    def _on_toggle_hwnd_counter(self, checked: bool) -> None:
        self._hwnd_counter.setVisible(checked)
        app_dirs.save_setting("show_hwnd_counter", checked)

    def _on_dump_handle_snapshot(self) -> None:
        path = hwnd_diag.snapshot_to_file()
        self.statusBar().showMessage(f"Handle snapshot written to {path}", 5000)

    def _spawn_main_context_menu_for_test(self) -> None:
        """Test hook: pop up and immediately dismiss the main graph context menu.

        Used by ``tests/test_hwnd_stress.py`` to exercise the same QMenu the
        viewer pops up on right-click without synthesising a real mouse event.
        """
        viewer = self.graph.viewer()
        viewport = viewer.viewport()
        menu = self.graph.get_context_menu("graph").qmenu
        global_pos = viewport.mapToGlobal(viewport.rect().center())
        menu.popup(global_pos)
        menu.close()

    def _attach_minimap_to_current_tab(self) -> None:
        """Bind the minimap to the active tab's graph."""
        idx = self._tab_bar.currentIndex()
        if idx < 0 or idx >= len(self._file_tabs):
            self._minimap.detach()
            return
        self._minimap.attach(self._file_tabs[idx].graph)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._position_minimap()
        if self._search_bar is not None and self._search_bar.isVisible():
            self._position_search_bar()

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        if obj is self._graph_container and event.type() == QtCore.QEvent.Type.Resize:
            self._position_minimap()
        return super().eventFilter(obj, event)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        # Deferred positioning so widget geometry is finalized
        QtCore.QTimer.singleShot(_DEFERRED_TICK_MS, self._position_minimap)

    # -- Status bar -----------------------------------------------------------

    def _setup_status_bar(self) -> None:
        self.statusBar().showMessage("Ready")
        # HWND counter (Surface A). Hidden by default; toggled via View menu.
        self._hwnd_counter = QtWidgets.QLabel("")
        self._hwnd_counter.setVisible(False)
        self.statusBar().addPermanentWidget(self._hwnd_counter)
        self._hwnd_last_count: int | None = None
        self._hwnd_counter_timer = QtCore.QTimer(self)
        self._hwnd_counter_timer.setInterval(2000)
        self._hwnd_counter_timer.timeout.connect(self._refresh_hwnd_counter)
        self._hwnd_counter_timer.start()

    def _refresh_hwnd_counter(self) -> None:
        from craftgraph import hwnd_diag

        count = hwnd_diag.gui_handle_count()
        if self._hwnd_last_count is None:
            delta_str = ""
        else:
            d = count - self._hwnd_last_count
            delta_str = f" ({d:+d})" if d != 0 else ""
        self._hwnd_last_count = count

        if count > 8000:
            color = "#cc4444"   # red
        elif count > 5000:
            color = "#cc8844"   # amber
        else:
            color = "#cccccc"   # neutral
        self._hwnd_counter.setStyleSheet(f"color: {color};")
        self._hwnd_counter.setText(f"HWND: {count}{delta_str}")

    # -- ItemID reference panel (dockable) ------------------------------------

    def _setup_id_reference_panel(self) -> None:
        """Create a dockable panel listing all vanilla and mod-compat IDs."""
        from craftgraph.vanilla_ids import load_mod_compat_ids, load_vanilla_ids

        dock = QtWidgets.QDockWidget("ItemID Reference", self)
        dock.setAllowedAreas(
            QtCore.Qt.DockWidgetArea.LeftDockWidgetArea
            | QtCore.Qt.DockWidgetArea.RightDockWidgetArea,
        )

        container = QtWidgets.QWidget()
        vbox = QtWidgets.QVBoxLayout(container)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(4)

        # Search filter
        self._id_filter = QtWidgets.QLineEdit()
        self._id_filter.setPlaceholderText("Filter IDs...")
        self._id_filter.setClearButtonEnabled(True)
        vbox.addWidget(self._id_filter)

        # ID count label
        self._id_count_label = QtWidgets.QLabel()
        vbox.addWidget(self._id_count_label)

        # List model + proxy filter
        vanilla = sorted(load_vanilla_ids())
        mod = sorted(load_mod_compat_ids() - load_vanilla_ids())

        model = QtGui.QStandardItemModel()
        if vanilla:
            header = QtGui.QStandardItem("-- Vanilla --")
            header.setEnabled(False)
            header.setDragEnabled(False)
            model.appendRow(header)
            for tid in vanilla:
                model.appendRow(QtGui.QStandardItem(tid))
        if mod:
            header = QtGui.QStandardItem("-- Mod Compat --")
            header.setEnabled(False)
            header.setDragEnabled(False)
            model.appendRow(header)
            for tid in mod:
                model.appendRow(QtGui.QStandardItem(tid))

        proxy = QtCore.QSortFilterProxyModel()
        proxy.setSourceModel(model)
        proxy.setFilterCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)

        self._id_list = QtWidgets.QListView()
        self._id_list.setModel(proxy)
        self._id_list.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers,
        )
        self._id_list.setDragEnabled(True)
        self._id_list.setDragDropMode(
            QtWidgets.QAbstractItemView.DragDropMode.DragOnly,
        )
        self._id_list.setDefaultDropAction(QtCore.Qt.DropAction.CopyAction)
        vbox.addWidget(self._id_list)

        self._id_count_label.setText(f"{len(vanilla)} vanilla, {len(mod)} mod-compat")

        self._id_filter.textChanged.connect(proxy.setFilterFixedString)

        dock.setWidget(container)
        self.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, dock)
        self._id_dock = dock

        # Add toggle to View menu
        view_menu = self.menuBar().findChild(QtWidgets.QMenu, "view_menu")
        if view_menu is not None:
            view_menu.addAction(dock.toggleViewAction())

    # -- Close event ----------------------------------------------------------

    def _has_unsaved_changes(self) -> bool:
        """True if any file tab has unsaved edits."""
        return any(
            hasattr(tab.history, "is_dirty") and tab.history.is_dirty for tab in self._file_tabs
        )

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        """Prompt the user if there are unsaved changes before closing."""
        if not self._has_unsaved_changes():
            if self._project is not None:
                self._update_project_state()
                save_project(self._project)
            self._save_positions()
            self._stop_file_watcher()
            event.accept()
            return

        result = QtWidgets.QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Do you want to save before closing?",
            QtWidgets.QMessageBox.StandardButton.Save
            | QtWidgets.QMessageBox.StandardButton.Discard
            | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Save,
        )

        if result == QtWidgets.QMessageBox.StandardButton.Save:
            self._save_all()
            self._stop_file_watcher()
            event.accept()
        elif result == QtWidgets.QMessageBox.StandardButton.Discard:
            # Still save project state (positions, editor state) even on discard
            if self._project is not None:
                self._update_project_state()
                save_project(self._project)
            self._save_positions()
            self._stop_file_watcher()
            event.accept()
        else:
            event.ignore()

    def _save_positions(self) -> None:
        """Persist all user-dragged node positions.

        In project mode, positions are stored in the project file (handled
        by ``_update_project_state``).  In raw-file mode, uses the sidecar
        ``layout.json``.
        """
        if self._project is not None:
            return
        if not self._file_tabs:
            return
        source_path = None
        for tab in self._file_tabs:
            if tab.parsed_file is not None:
                source_path = tab.parsed_file.source_path
                break
        if source_path is None:
            return

        layout_file = layout_path_for(self._source_path)
        all_positions: dict[str, dict[str, list[float]]] = {}
        for tab in self._file_tabs:
            if tab.parsed_file is None:
                continue
            tab_key = tab.parsed_file.source_path.stem
            all_positions[tab_key] = {k: [v[0], v[1]] for k, v in tab.user_positions.items()}

        if any(pos for pos in all_positions.values()):
            save_layout(layout_file, all_positions)

    def _update_project_state(self) -> None:
        """Sync current workspace state into ``self._project``."""
        if self._project is None:
            return

        cc3 = Path(self._project.cc3_path)
        open_files: list[str] = []
        for tab in self._file_tabs:
            if tab.parsed_file is None:
                continue
            try:
                rel = tab.parsed_file.source_path.relative_to(cc3)
                open_files.append(str(rel))
            except ValueError:
                open_files.append(str(tab.parsed_file.source_path))
        self._project.open_files = open_files

        idx = self._tab_bar.currentIndex()
        if 0 <= idx < len(self._file_tabs):
            tab = self._file_tabs[idx]
            if tab.parsed_file is not None:
                self._project.active_tab = tab.parsed_file.source_path.stem
        else:
            self._project.active_tab = ""

        positions: dict[str, dict[str, list[float]]] = {}
        for tab in self._file_tabs:
            if tab.parsed_file is None:
                continue
            tab_key = tab.parsed_file.source_path.stem
            positions[tab_key] = {k: [v[0], v[1]] for k, v in tab.user_positions.items()}
        self._project.node_positions = positions

        editor_state: dict[str, dict[str, object]] = {}
        for tab in self._file_tabs:
            if tab.parsed_file is None:
                continue
            tab_key = tab.parsed_file.source_path.stem
            cursor = tab.editor.textCursor()
            scroll_bar = tab.editor.verticalScrollBar()
            editor_state[tab_key] = {
                "cursor_pos": cursor.position(),
                "scroll": scroll_bar.value() if scroll_bar is not None else 0,
            }
        self._project.editor_state = editor_state  # type: ignore[assignment]

    def _prompt_create_project(self) -> bool:
        """Ask if user wants to create a project. Returns True if created."""
        reply = QtWidgets.QMessageBox.question(
            self,
            "Save as Project?",
            "Would you like to save this as a CraftGraph project?\n\n"
            "A project file remembers your open files, node positions,\n"
            "and editor state across sessions.",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.Yes,
        )
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return False

        dialog = QuickProjectDialog(parent=self)
        if dialog.exec_() != QtWidgets.QDialog.DialogCode.Accepted:
            return False

        docs_dir = app_dirs.documents_dir()
        cc3_path = self._source_path
        if cc3_path.is_file():
            cc3_path = cc3_path.parent

        project = new_project(
            dialog.project_name,
            cc3_path,
            docs_dir,
            description=dialog.description,
        )
        self._project = project
        self._update_project_state()
        save_project(project)
        self.setWindowTitle(f"CraftGraph - {project.name}")
        self.statusBar().showMessage(f"Created project '{project.name}'")
        return True

    def _save_all(self) -> None:
        """Save all dirty tabs to disk, showing validation summary first."""
        # Project-first: save or prompt before recipe files
        if self._project is not None:
            self._update_project_state()
            save_project(self._project)
        else:
            self._prompt_create_project()

        all_issues: list[str] = []
        dirty_tabs: list[FileTab] = []
        for tab in self._file_tabs:
            if tab.parsed_file is None:
                continue
            if not hasattr(tab.history, "is_dirty") or not tab.history.is_dirty:
                continue
            dirty_tabs.append(tab)
            all_issues.extend(self._collect_validation_issues(tab))
        if all_issues and not self._show_validation_summary(all_issues):
            self.statusBar().showMessage("Save All cancelled")
            return
        saved = 0
        for tab in dirty_tabs:
            if self._ce_settings.strip_trailing_whitespace:
                tab.editor.strip_trailing_whitespace()
            path = tab.parsed_file.source_path  # type: ignore[union-attr]
            text = serialize_file(tab.parsed_file)  # type: ignore[arg-type]
            save_with_backup(path, text, backup=self._backup_on_save)
            tab.history.mark_saved()
            saved += 1
        self._save_positions()
        if saved:
            self._on_tab_changed(self._tab_bar.currentIndex())
            self.statusBar().showMessage(f"Saved {saved} file(s)")

    # -- Auto-save ------------------------------------------------------------

    def _set_auto_save(
        self,
        enabled: bool = False,
        interval: int | None = None,
    ) -> None:
        """Enable or disable the auto-save timer.

        *interval* is in seconds.  If ``None``, the current interval is kept.
        """
        if interval is not None:
            self._auto_save_interval = interval
        self._auto_save_enabled = enabled
        if enabled:
            self._auto_save_timer.start(self._auto_save_interval * 1000)
        else:
            self._auto_save_timer.stop()

    def _auto_save_tick(self) -> None:
        """Silently save all dirty tabs (no validation prompt)."""
        # Save project file silently if loaded (no prompt in auto-save)
        if self._project is not None:
            self._update_project_state()
            save_project(self._project)

        for tab in self._file_tabs:
            if tab.parsed_file is None:
                continue
            if not hasattr(tab.history, "is_dirty") or not tab.history.is_dirty:
                continue
            path = tab.parsed_file.source_path
            text = serialize_file(tab.parsed_file)
            save_with_backup(path, text, backup=self._backup_on_save)
            tab.history.mark_saved()
        self._save_positions()

    # -- Menu handlers --------------------------------------------------------

    def _on_new_file(self) -> None:
        """Open the New File dialog and create an empty tab for the chosen block type."""
        if self._source_path.is_file():
            default_dir = self._source_path.parent
        elif self._source_path.is_dir():
            default_dir = self._source_path
        else:
            cc3_dir = self._cc3_working_dir()
            default_dir = Path(cc3_dir) if cc3_dir else Path.cwd()
        dialog = NewFileDialog(parent=self, default_dir=default_dir)
        if dialog.exec_() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        pf = ParsedFile(source_path=dialog.file_path, block_type=dialog.block_type)
        tab = self._create_file_tab(pf)
        self._file_tabs.append(tab)

        self._graph_stack.addWidget(tab.graph.widget)
        self._editor_stack.addWidget(tab.editor)
        self._tab_bar.addTab(pf.source_path.stem)
        self._tab_bar.setTabToolTip(
            self._tab_bar.count() - 1,
            str(pf.source_path),
        )

        # Switch to the new tab
        new_index = len(self._file_tabs) - 1
        self._tab_bar.setCurrentIndex(new_index)
        self._on_tab_changed(new_index)

        # Spawn a starter node for the block type
        self._spawn_starter_node(pf.block_type)

        self.statusBar().showMessage(f"New file: {pf.source_path.name} ({pf.block_type.value})")
        self._show_editor()

    def _on_new_project(self) -> None:
        """Open the New Project dialog and scaffold a CC3 mod directory."""
        cc3_dir = self._cc3_working_dir()
        default_dir = Path(cc3_dir) if cc3_dir else None
        dialog = NewProjectDialog(parent=self, default_dir=default_dir)
        if dialog.exec_() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        project_dir = dialog.project_path
        block_types = dialog.selected_block_types
        project_name = dialog.project_name
        project_desc = dialog.description

        # Create directory structure
        project_dir.mkdir(parents=True)
        (project_dir / "Assets").mkdir()
        (project_dir / ".craftgraph").mkdir()

        # Create one empty .txt file per selected block type
        created_files: list[str] = []
        for bt in block_types:
            filename = f"{_BLOCK_TYPE_DEFAULT_NAMES[bt]}.txt"
            file_path = project_dir / filename
            file_path.write_text(f"{bt.value}:\n", encoding="utf-8")
            created_files.append(filename)

        # Create the .craftgraph project file
        docs_dir = app_dirs.documents_dir()
        docs_dir.mkdir(parents=True, exist_ok=True)
        project = new_project(
            project_name,
            project_dir,
            docs_dir,
            description=project_desc,
        )
        project.open_files = created_files
        save_project(project)
        self._project = project

        # Load the newly created project
        self.load_recipes(project_dir)

        # Spawn a starter node on each tab
        for i, tab in enumerate(self._file_tabs):
            if tab.parsed_file is not None and tab.parsed_file.block_type is not None:
                self._tab_bar.setCurrentIndex(i)
                self._on_tab_changed(i)
                self._spawn_starter_node(tab.parsed_file.block_type)
        # Return to the first tab
        if self._file_tabs:
            self._tab_bar.setCurrentIndex(0)
            self._on_tab_changed(0)

        self._recent.add(Path(project.project_path), "project")
        self._rebuild_recent_menu()
        self.setWindowTitle(f"CraftGraph - {project.name}")
        self.statusBar().showMessage(
            f"Created project '{project.name}' ({len(block_types)} files)"
        )
        self._show_editor()

    def _on_open_folder(self) -> None:
        with hwnd_diag.measure("open_folder"):
            directory = QtWidgets.QFileDialog.getExistingDirectory(
                self,
                "Open Recipe Directory",
                self._cc3_working_dir(),
            )
            if directory:
                self.load_recipes(Path(directory))
                self._recent.add(Path(directory), "folder")
                self._rebuild_recent_menu()
                self._show_editor()

    def _on_open_file(self) -> None:
        with hwnd_diag.measure("open_file"):
            file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Open Recipe File",
                self._cc3_working_dir(),
                "CC3 Recipe Files (*.txt);;All Files (*)",
            )
            if file_path:
                self.load_recipes(Path(file_path))
                self._recent.add(Path(file_path).parent, "folder")
                self._rebuild_recent_menu()
                self._show_editor()

    def _on_open_project(self) -> None:
        """Show a file dialog and open the selected .craftgraph project."""
        docs_dir = app_dirs.documents_dir()
        docs_dir.mkdir(parents=True, exist_ok=True)
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open CraftGraph Project",
            str(docs_dir),
            "CraftGraph Projects (*.craftgraph);;All Files (*)",
        )
        if not file_path:
            return
        self.open_project_file(Path(file_path))

    def open_project_file(self, path: Path) -> None:
        """Load a .craftgraph project file and restore workspace state.

        Called from the menu dialog, from recent-files clicks, and from
        ``launch_qt_gui`` when a ``.craftgraph`` file is passed on the
        command line (e.g. double-click file association).
        """
        try:
            project = load_project(path)
        except ProjectLoadError as exc:
            QtWidgets.QMessageBox.critical(self, "Project Load Error", str(exc))
            return

        cc3_path = Path(project.cc3_path)
        if not cc3_path.is_dir():
            new_dir = QtWidgets.QFileDialog.getExistingDirectory(
                self,
                f"CC3 folder not found at {cc3_path}. Browse to the correct location:",
                "",
            )
            if not new_dir:
                return
            project.cc3_path = new_dir
            cc3_path = Path(new_dir)
            save_project(project)

        self._project = project
        self._recent.add(path, "project")
        self._rebuild_recent_menu()

        # Load recipes from CC3 path
        self.load_recipes(cc3_path)

        # Restore node positions from project (overwrite sidecar-loaded ones)
        for tab in self._file_tabs:
            if tab.parsed_file is None:
                continue
            tab_key = tab.parsed_file.source_path.stem
            if tab_key in project.node_positions:
                pos = project.node_positions[tab_key]
                tab.user_positions = {k: (v[0], v[1]) for k, v in pos.items()}
                for node_key, (x, y) in tab.user_positions.items():
                    for node in tab.graph.all_nodes():
                        ref = getattr(node, "model_ref", None)
                        if ref is not None and model_position_key(ref) == node_key:
                            node.set_pos(x, y)
                            break

        # Restore active tab
        if project.active_tab:
            for i, tab in enumerate(self._file_tabs):
                if (
                    tab.parsed_file is not None
                    and tab.parsed_file.source_path.stem == project.active_tab
                ):
                    self._tab_bar.setCurrentIndex(i)
                    self._on_tab_changed(i)
                    break

        # Restore editor state (cursor position, scroll)
        for tab in self._file_tabs:
            if tab.parsed_file is None:
                continue
            tab_key = tab.parsed_file.source_path.stem
            if tab_key in project.editor_state:
                state = project.editor_state[tab_key]
                cursor = tab.editor.textCursor()
                cursor.setPosition(state.get("cursor_pos", 0))
                tab.editor.setTextCursor(cursor)
                scroll_bar = tab.editor.verticalScrollBar()
                if scroll_bar is not None:
                    scroll_bar.setValue(state.get("scroll", 0))

        # Update window title
        self.setWindowTitle(f"CraftGraph - {project.name}")

        missing = [r for r in project.open_files if not (cc3_path / r).is_file()]
        if missing:
            self.statusBar().showMessage(
                f"Opened project '{project.name}' ({len(missing)} file(s) not found, skipped)"
            )
        else:
            self.statusBar().showMessage(f"Opened project '{project.name}'")
        self._show_editor()

    # -- Welcome screen -------------------------------------------------------

    def _show_editor(self) -> None:
        """Switch from welcome screen to the editor view."""
        self._main_stack.setCurrentIndex(1)

    def _welcome_open_recent(self, path: str, entry_type: str) -> None:
        """Handle a click on a recent entry in the welcome screen."""
        target = Path(path)
        if not target.exists():
            self.statusBar().showMessage("Path no longer exists")
            self._recent.remove(target)
            self._rebuild_recent_menu()
            return
        if entry_type == "project":
            self.open_project_file(target)
        else:
            self.load_recipes(target)
            self._recent.add(target, "folder")
            self._rebuild_recent_menu()
            self._show_editor()

    def _on_startup_toggle(self, checked: bool) -> None:
        """Handle the 'Don't show on startup' checkbox toggle."""
        value = "empty" if checked else "welcome"
        app_dirs.save_setting("on_launch", value)

    # -- Recent files ---------------------------------------------------------

    def _rebuild_recent_menu(self) -> None:
        """Repopulate the Open Recent submenu from the RecentFiles store."""
        menu = self._recent_menu
        menu.clear()

        entries = self._recent.entries
        if not entries:
            no_recent = menu.addAction("(No recent files)")
            no_recent.setEnabled(False)
            return

        for entry in entries:
            path = Path(entry.path)
            label = path.stem if entry.entry_type == "project" else path.name
            action = menu.addAction(label)
            action.setToolTip(str(path))
            if not path.exists():
                action.setEnabled(False)
            action.setData(entry)
            action.triggered.connect(lambda checked=False, e=entry: self._on_recent_entry(e))

        menu.addSeparator()
        clear_action = menu.addAction("Clear Recent")
        clear_action.triggered.connect(self._on_clear_recent)

    def _on_recent_entry(self, entry: object) -> None:
        """Handle clicking a recent-files entry."""
        from craftgraph.recent import RecentEntry

        if not isinstance(entry, RecentEntry):
            return
        path = Path(entry.path)
        if not path.exists():
            self._recent.remove(path)
            self._rebuild_recent_menu()
            self.statusBar().showMessage(f"Path not found, removed from recent files: {path}")
            return

        if entry.entry_type == "project":
            try:
                project = load_project(path)
            except ProjectLoadError as exc:
                QtWidgets.QMessageBox.critical(self, "Project Load Error", str(exc))
                self._recent.remove(path)
                self._rebuild_recent_menu()
                return
            self._project = project
            self.load_recipes(Path(project.cc3_path))
            self.setWindowTitle(f"CraftGraph - {project.name}")
            self.statusBar().showMessage(f"Opened project '{project.name}'")
        else:
            self.load_recipes(path)

        self._recent.add(path, entry.entry_type)
        self._rebuild_recent_menu()

    def _on_clear_recent(self) -> None:
        """Clear the recent-files list."""
        self._recent.clear()
        self._rebuild_recent_menu()

    def _collect_validation_issues(self, tab: FileTab | None = None) -> list[str]:
        """Collect all validation issues for the given tab (or active tab)."""
        from craftgraph.pin_registry import PinType

        if tab is None:
            tab = self._active_tab
        issues: list[str] = []
        valid_paths = self._collect_valid_path_targets()
        for node in tab.graph.all_nodes():
            if not isinstance(node, CraftGraphBaseNode):
                continue
            node_label = (
                node.get_property("item_id") or node.get_property("tab_id") or node.NODE_NAME
            )
            for fp in node.FIELD_REGISTRY:
                if fp.pin_type == PinType.INGREDIENT_LIST:
                    continue
                value = node.get_property(fp.name)
                empty = value is None or (isinstance(value, str) and not value.strip())
                if fp.required and empty:
                    issues.append(f"{node_label}: {fp.label} is required but empty")
                if fp.name in self._PATH_WIDGET_NAMES and not empty and isinstance(value, str):
                    if value.strip() not in valid_paths:
                        issues.append(
                            f"{node_label}: Path '{value}' does not match any known fabricator or tab"
                        )
            for a, b in node.PAIRED_FIELDS:
                va = node.get_property(a)
                vb = node.get_property(b)
                ea = va is None or (isinstance(va, str) and not va.strip())
                eb = vb is None or (isinstance(vb, str) and not vb.strip())
                if ea != eb:
                    fp_a = node._get_field_pin(a)
                    fp_b = node._get_field_pin(b)
                    la = fp_a.label if fp_a else a
                    lb = fp_b.label if fp_b else b
                    issues.append(
                        f"{node_label}: {la} and {lb} should both be set or both be empty"
                    )

        # Model-level checks (unknown ingredients, broken parent_tab_path, etc.)
        if tab.parsed_file is not None:
            from craftgraph.sync import validate_parsed_files

            known_ids = frozenset(i.lower() for i in self._get_id_words())
            issues.extend(validate_parsed_files([tab.parsed_file], known_ids))

        return issues

    def _show_validation_summary(self, issues: list[str]) -> bool:
        """Show a validation summary dialog. Returns True if user wants to save anyway."""
        if not issues:
            return True
        dlg = QtWidgets.QDialog(self, _DIALOG_FLAGS)
        dlg.setStyleSheet(_DIALOG_STYLE)
        dlg.setMinimumSize(*scaled_size(*_VALIDATION_DIALOG_MIN_SIZE))

        layout = QtWidgets.QVBoxLayout(dlg)
        header = QtWidgets.QLabel(f"{len(issues)} validation issue(s) found:")
        header.setStyleSheet("font-weight: bold; color: rgb(200, 160, 40);")
        layout.addWidget(header)

        issue_list = QtWidgets.QListWidget(dlg)
        issue_list.addItems(issues)
        issue_list.setStyleSheet(
            "QListWidget { background: rgb(30, 30, 30); color: rgb(200, 200, 200); }"
        )
        layout.addWidget(issue_list)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            parent=dlg,
        )
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Save).setText("Save Anyway")
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        dlg.move(QtGui.QCursor.pos())

        return dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted

    def _on_save(self) -> None:
        """Save the active tab's file to disk, showing validation summary first."""
        tab = self._active_tab
        if tab.parsed_file is None:
            return

        # Project-first: save or prompt before recipe files
        if self._project is not None:
            self._update_project_state()
            save_project(self._project)
        else:
            self._prompt_create_project()

        # Strip trailing whitespace from the code editor before serializing
        if self._ce_settings.strip_trailing_whitespace:
            tab.editor.strip_trailing_whitespace()

        issues = self._collect_validation_issues(tab)
        if issues and not self._show_validation_summary(issues):
            self.statusBar().showMessage("Save cancelled")
            return
        path = tab.parsed_file.source_path
        text = serialize_file(tab.parsed_file)
        save_with_backup(path, text, backup=self._backup_on_save)
        tab.history.mark_saved()
        self._save_positions()
        self._on_tab_changed(self._tab_bar.currentIndex())
        msg = f"Saved {path.name}"
        if issues:
            msg += f" (with {len(issues)} warning(s))"
        self.statusBar().showMessage(msg)

    def _on_save_all(self) -> None:
        """Save all dirty tabs to disk."""
        self._save_all()

    def _on_undo(self) -> None:
        stack = self._active_tab.graph.undo_stack()
        if not stack.canUndo():
            return
        desc = stack.undoText()
        stack.undo()
        self.statusBar().showMessage(f"Undo: {desc}" if desc else "Undo")

    def _on_redo(self) -> None:
        stack = self._active_tab.graph.undo_stack()
        if not stack.canRedo():
            return
        desc = stack.redoText()
        stack.redo()
        self.statusBar().showMessage(f"Redo: {desc}" if desc else "Redo")

    def _on_reset_layout(self) -> None:
        """Re-compute the default hierarchical layout for the active tab.

        Discards all user-dragged positions and updates the sidecar file.
        """
        tab = self._active_tab
        if tab.parsed_file is None:
            return
        tab.user_positions.clear()
        with tab.sync_guard():
            positions = compute_hierarchy_layout([tab.parsed_file], tab.model_to_node)
            apply_layout(positions, tab.model_to_node)
            place_variable_nodes(tab.graph)
            place_orphan_nodes(tab.graph)
        tab.graph.clear_selection()
        self._save_positions()
        self.statusBar().showMessage("Layout reset to default")

    def _on_settings(self) -> None:
        """Show the Settings dialog and apply changed settings."""
        with hwnd_diag.measure("open_settings"):
            dialog = _SettingsDialog(
                self,
                backup_on_save=self._backup_on_save,
                auto_save_enabled=self._auto_save_enabled,
                auto_save_interval=self._auto_save_interval,
                default_project_folder=self._default_project_folder,
                subnautica_cc3_path=self._subnautica_cc3_path,
                recent_max_entries=self._recent.max_entries,
                on_launch=str(app_dirs.load_setting("on_launch", "welcome")),
                check_for_updates=self._check_for_updates,
                theme=active_theme(),
                node_editor=self._ne_settings,
                code_editor=self._ce_settings,
                autocomplete=self._ac_settings,
                file_watching=self._fw_settings,
                keybindings=self._kb_settings,
                project_custom_ids=(
                    self._effective_custom_ids() if self._project is not None else None
                ),
            )
            dialog.applied.connect(lambda: self._apply_settings_from_dialog(dialog))
            try:
                dialog.exec_()
                self._apply_settings_from_dialog(dialog)
            finally:
                # Without this, the dialog stays as a child of the main window
                # and its 473-widget subtree (per Phase 1 measurements) leaks
                # on every open. deleteLater queues destruction for after the
                # event loop returns, so any in-flight applied-signal callbacks
                # finish first.
                dialog.deleteLater()

    def _apply_settings_from_dialog(self, dialog: "_SettingsDialog") -> None:
        """Read current values from *dialog* and apply + persist them.

        Used by both the Apply button (live preview) and dialog close.
        """
        self._backup_on_save = dialog.backup_on_save
        self._set_auto_save(
            enabled=dialog.auto_save_enabled,
            interval=dialog.auto_save_interval,
        )
        self._default_project_folder = dialog.default_project_folder
        self._subnautica_cc3_path = dialog.subnautica_cc3_path
        self._check_for_updates = dialog.check_for_updates
        self._recent.max_entries = dialog.recent_max_entries
        self._rebuild_recent_menu()

        new_theme = dialog.theme_colors
        set_active_theme(new_theme)
        self._apply_theme(new_theme)

        self._ne_settings = dialog.node_editor_settings
        self._apply_node_editor_settings(self._ne_settings)

        self._ce_settings = dialog.code_editor_settings
        self._apply_code_editor_settings(self._ce_settings)

        self._ac_settings = dialog.autocomplete_settings
        self._apply_autocomplete_settings(self._ac_settings)

        self._fw_settings = dialog.file_watching_settings
        self._apply_file_watching_settings(self._fw_settings)

        self._kb_settings = dialog.keybinding_settings
        self._apply_keybinding_settings(self._kb_settings)

        if self._project is not None:
            proj_ids = dialog.project_custom_ids
            if proj_ids is not None:
                self._project.settings_overrides["custom_ids"] = proj_ids

        app_dirs.save_setting("backup_on_save", dialog.backup_on_save)
        app_dirs.save_setting("auto_save_enabled", dialog.auto_save_enabled)
        app_dirs.save_setting("auto_save_interval", dialog.auto_save_interval)
        app_dirs.save_setting("default_project_folder", dialog.default_project_folder)
        app_dirs.save_setting("subnautica_cc3_path", dialog.subnautica_cc3_path)
        app_dirs.save_setting("recent_max_entries", dialog.recent_max_entries)
        app_dirs.save_setting("on_launch", dialog.on_launch)
        app_dirs.save_setting("check_for_updates", dialog.check_for_updates)
        self._save_theme(new_theme)
        self._save_node_editor_settings(self._ne_settings)
        self._save_code_editor_settings(self._ce_settings)
        self._save_autocomplete_settings(self._ac_settings)
        self._save_file_watching_settings(self._fw_settings)
        self._save_keybinding_settings(self._kb_settings)

    def _apply_theme(self, theme: ThemeColors) -> None:
        """Apply visual theme changes: stylesheet, node borders, fill colors, UI scale."""
        self.setStyleSheet(self._build_app_stylesheet(theme))

        # Resolve node-color palette through the colorblind remap so the picked
        # colors and the active vision-deficiency palette compose correctly.
        effective_node_colors = apply_colorblind_palette(theme).node
        border_color = (220, 220, 220, 255) if theme.high_contrast_borders else (46, 57, 66, 255)

        for tab in self._file_tabs:
            for node in tab.graph.all_nodes():
                view = node.view
                view.border_color = border_color
                field_name = NODE_COLOR_FIELD_FOR_CLASS.get(type(node))
                if field_name is None:
                    continue
                rgb = getattr(effective_node_colors, field_name, None)
                if rgb is None:
                    continue
                node.set_color(*rgb)
            # Force a viewport repaint so new fills appear without panning.
            scene = tab.graph.scene()
            if scene is not None:
                scene.update()

        # UI scale: adjust the application-wide default font size
        app = QtWidgets.QApplication.instance()
        if app is not None:
            base_font = app.font()
            # 10pt is our baseline at 100%
            scaled_pt = round(10.0 * theme.ui_scale / 100.0)
            base_font.setPointSize(max(scaled_pt, 6))
            app.setFont(base_font)

    @staticmethod
    def _build_app_stylesheet(theme: ThemeColors) -> str:
        """Build the root window stylesheet from theme settings."""
        accent = theme.accent
        if theme.app_theme == "light":
            bg = "rgb(240, 240, 240)"
            fg = "rgb(30, 30, 30)"
            panel_bg = "rgb(255, 255, 255)"
            border = "rgb(180, 180, 180)"
            combo_bg = "rgb(250, 250, 250)"
            combo_sel = "rgb(210, 230, 255)"
        elif theme.app_theme == "system":
            palette = QtWidgets.QApplication.palette()
            bg_c = palette.color(QtGui.QPalette.ColorRole.Window)
            fg_c = palette.color(QtGui.QPalette.ColorRole.WindowText)
            bg = f"rgb({bg_c.red()}, {bg_c.green()}, {bg_c.blue()})"
            fg = f"rgb({fg_c.red()}, {fg_c.green()}, {fg_c.blue()})"
            panel_bg = bg
            border = "rgb(140, 140, 140)"
            combo_bg = bg
            combo_sel = f"rgb({bg_c.red() + 20}, {bg_c.green() + 20}, {bg_c.blue() + 40})"
        else:
            bg = "rgb(30, 30, 30)"
            fg = "rgb(200, 200, 200)"
            panel_bg = "rgb(30, 30, 30)"
            border = "rgb(80, 80, 80)"
            combo_bg = "rgb(30, 30, 30)"
            combo_sel = "rgb(60, 80, 120)"

        hc_border = "2px" if theme.high_contrast_borders else "1px"

        parts = [
            # Combo box dropdown opacity fix (always needed)
            f"QComboBox QAbstractItemView {{"
            f"  background: {combo_bg}; color: {fg};"
            f"  selection-background-color: {combo_sel};"
            f"  border: {hc_border} solid {border};"
            f"}}",
            # Status bar accent stripe
            f"QStatusBar {{ border-top: 2px solid {accent}; }}",
        ]

        if theme.app_theme == "light":
            parts.append(
                f"QMainWindow {{ background: {bg}; color: {fg}; }}"
                f"QMenuBar {{ background: {panel_bg}; color: {fg}; }}"
                f"QMenuBar::item:selected {{ background: {combo_sel}; }}"
                f"QMenu {{ background: {panel_bg}; color: {fg};"
                f"  border: {hc_border} solid {border}; }}"
                f"QMenu::item:selected {{ background: {combo_sel}; }}"
                f"QTabBar::tab {{ background: rgb(230, 230, 230); color: {fg};"
                f"  border: {hc_border} solid {border}; padding: 4px 10px; }}"
                f"QTabBar::tab:selected {{ background: {panel_bg}; }}"
                f"QSplitter::handle {{ background: {border}; }}"
            )

        if theme.high_contrast_borders:
            parts.append(
                f"QGroupBox {{ border: {hc_border} solid {border}; }}"
                f"QLineEdit, QSpinBox, QComboBox {{"
                f"  border: {hc_border} solid {border}; }}"
            )

        return "\n".join(parts)

    @staticmethod
    def _save_theme(theme: ThemeColors) -> None:
        """Persist theme colors to settings.json under the ``theme`` key."""
        import contextlib

        path = app_dirs.settings_path()
        data: dict[str, object] = {"version": 1}
        if path.is_file():
            with contextlib.suppress(json.JSONDecodeError, ValueError):
                data = json.loads(path.read_text(encoding="utf-8"))
        data["theme"] = theme_to_dict(theme)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _load_theme() -> ThemeColors:
        """Load theme colors from settings.json, falling back to defaults."""
        path = app_dirs.settings_path()
        if not path.is_file():
            return ThemeColors()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw_theme = data.get("theme")
            if isinstance(raw_theme, dict):
                return theme_from_dict(raw_theme)
        except json.JSONDecodeError, TypeError, ValueError:
            pass
        return ThemeColors()

    def _install_viewer_patches(self, graph: NodeGraph) -> None:
        """Patch a graph's viewer and scene for CraftGraph-specific settings.

        Installs one-time monkey-patches that read dynamic ``_cg_*`` attributes
        from the viewer/scene so that settings changes take effect immediately
        without re-patching.  Safe to call multiple times per graph (guarded).
        """
        viewer = graph.viewer()
        if getattr(viewer, "_cg_patched", False):
            return
        viewer._cg_patched = True

        # Seed dynamic attributes from current settings
        s = self._ne_settings
        viewer._cg_zoom_speed: float = s.zoom_speed
        viewer._cg_invert_zoom: bool = s.invert_zoom
        viewer._cg_pan_with_mmb: bool = s.pan_with_mmb

        # -- Patch wheelEvent (zoom speed + invert) --
        def _patched_wheel(event: QtGui.QWheelEvent) -> None:
            try:
                delta = event.delta()
            except AttributeError:
                delta = event.angleDelta().y()
                if delta == 0:
                    delta = event.angleDelta().x()
            delta = int(delta * viewer._cg_zoom_speed)
            if viewer._cg_invert_zoom:
                delta = -delta
            try:
                viewer._set_viewer_zoom(delta, pos=event.pos())
            except AttributeError:
                viewer._set_viewer_zoom(delta, pos=event.position().toPoint())

        viewer.wheelEvent = _patched_wheel

        # -- Patch mouseMoveEvent (pan-with-MMB toggle) --
        _orig_mouse_move = viewer.mouseMoveEvent

        def _patched_mouse_move(event: QtGui.QMouseEvent) -> None:
            # When MMB pan is disabled, skip the plain-MMB pan branch but
            # preserve Alt+MMB zoom and Alt+LMB pan.
            if viewer.MMB_state and not viewer.ALT_state and not viewer._cg_pan_with_mmb:
                viewer._previous_pos = event.pos()
                QtWidgets.QGraphicsView.mouseMoveEvent(viewer, event)
                return
            _orig_mouse_move(event)

        viewer.mouseMoveEvent = _patched_mouse_move

        # -- Patch scene.drawBackground (custom grid size) --
        scene = graph.scene()
        scene._cg_grid_size: int = s.grid_size

        def _patched_draw_bg(
            painter: QtGui.QPainter,
            rect: QtCore.QRectF,
        ) -> None:
            from NodeGraphQt.constants import ViewerEnum
            from NodeGraphQt.widgets.scene import NodeScene

            super(NodeScene, scene).drawBackground(painter, rect)
            painter.save()
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
            painter.setBrush(scene.backgroundBrush())

            gs: int = scene._cg_grid_size

            if scene._grid_mode is ViewerEnum.GRID_DISPLAY_DOTS.value:
                pen = QtGui.QPen(QtGui.QColor(*scene.grid_color), 0.65)
                scene._draw_dots(painter, rect, pen, gs)
            elif scene._grid_mode is ViewerEnum.GRID_DISPLAY_LINES.value:
                zoom = scene.viewer().get_zoom()
                if zoom > -0.5:
                    pen = QtGui.QPen(QtGui.QColor(*scene.grid_color), 0.65)
                    scene._draw_grid(painter, rect, pen, gs)
                color = QtGui.QColor(*scene._bg_color).darker(200)
                if zoom < -0.0:
                    color = color.darker(100 - int(zoom * 110))
                pen = QtGui.QPen(color, 0.65)
                scene._draw_grid(painter, rect, pen, gs * 8)

            painter.restore()

        scene.drawBackground = types.MethodType(
            lambda self, p, r: _patched_draw_bg(p, r),
            scene,
        )

    def _snap_moved_nodes(self, graph: NodeGraph, moved: dict) -> None:
        """Snap recently moved nodes to the grid if snap-to-grid is enabled."""
        if not self._ne_settings.snap_to_grid:
            return
        size = self._ne_settings.grid_size
        for node_item in moved:
            node = graph.get_node_by_id(node_item.id)
            if node is None:
                continue
            x, y = node.pos()
            sx = round(x / size) * size
            sy = round(y / size) * size
            if sx != x or sy != y:
                node.set_pos(sx, sy)

    def _apply_node_editor_settings(self, s: NodeEditorSettings) -> None:
        """Apply node editor preferences to all open graphs."""
        from NodeGraphQt.constants import PipeLayoutEnum, ViewerEnum

        old = self._ne_settings
        self._ne_settings = s

        grid_mode_map = {
            "dots": ViewerEnum.GRID_DISPLAY_DOTS.value,
            "lines": ViewerEnum.GRID_DISPLAY_LINES.value,
            "none": ViewerEnum.GRID_DISPLAY_NONE.value,
        }
        mode = grid_mode_map.get(s.grid_style, ViewerEnum.GRID_DISPLAY_LINES.value)
        if not s.show_grid:
            mode = ViewerEnum.GRID_DISPLAY_NONE.value

        pipe_style_map = {
            "curved": PipeLayoutEnum.CURVED.value,
            "straight": PipeLayoutEnum.STRAIGHT.value,
            "angle": PipeLayoutEnum.ANGLE.value,
        }
        pipe_mode = pipe_style_map.get(s.pipe_style, PipeLayoutEnum.CURVED.value)

        for tab in self._file_tabs:
            tab.graph.set_grid_mode(mode)

            # Update dynamic attributes on patched viewers/scenes
            viewer = tab.graph.viewer()
            if getattr(viewer, "_cg_patched", False):
                viewer._cg_zoom_speed = s.zoom_speed
                viewer._cg_invert_zoom = s.invert_zoom
                viewer._cg_pan_with_mmb = s.pan_with_mmb
                tab.graph.scene()._cg_grid_size = s.grid_size
                viewer.force_update()

            # Pipe style
            tab.graph.set_pipe_style(pipe_mode)

            # Pipe width -- update pen on all existing pipe items
            self._apply_pipe_width(tab, s.pipe_width)

            # Port label visibility
            self._apply_port_label_visibility(tab, s.show_port_labels)

        # Thumbnails: toggle visibility or re-apply at new size
        thumbnails_changed = (
            s.show_thumbnails != old.show_thumbnails or s.thumbnail_size != old.thumbnail_size
        )
        if thumbnails_changed:
            self._apply_thumbnail_settings(s.show_thumbnails, s.thumbnail_size)

        # Pipe animation
        if s.animate_pipes != old.animate_pipes:
            self._set_pipe_animation(s.animate_pipes)

        # Cycle warning toggle
        for tab in self._file_tabs:
            if tab.ui_handler is not None:
                tab.ui_handler.warn_before_cycles = s.warn_before_cycles

        # Minimap visibility
        if hasattr(self, "_minimap"):
            self._minimap.setVisible(s.show_minimap)
            if hasattr(self, "_minimap_action"):
                self._minimap_action.setChecked(s.show_minimap)

    def _apply_pipe_width(self, tab: FileTab, width: float) -> None:
        """Update pen width on all existing pipe items in a tab's scene."""
        from NodeGraphQt.qgraphics.pipe import PipeItem

        scene = tab.graph.scene()
        if scene is None:
            return
        for item in scene.items():
            if isinstance(item, PipeItem):
                pen = item.pen()
                pen.setWidthF(width)
                item.setPen(pen)

    @staticmethod
    def _apply_port_label_visibility(tab: FileTab, visible: bool) -> None:
        """Show or hide port name labels on all nodes in a tab."""
        for node in tab.graph.all_nodes():
            view = getattr(node, "view", None)
            if view is None:
                continue
            for port_item in list(view.inputs) + list(view.outputs):
                port_item.display_name = visible
            view.post_init()

    def _apply_thumbnail_settings(
        self,
        show: bool,
        size: int,
    ) -> None:
        """Toggle sprite visibility and re-apply at *size* across all tabs."""
        from craftgraph.qt_nodes import CraftGraphBaseNode

        for tab in self._file_tabs:
            for node in tab.model_to_node.values():
                if not isinstance(node, CraftGraphBaseNode):
                    continue
                if not show:
                    node.clear_sprite()
                elif node._sprite_path is not None and node._sprite_path.exists():
                    node.set_sprite(node._sprite_path, size=size)

    def _set_pipe_animation(self, enabled: bool) -> None:
        """Start or stop the pipe dash-offset animation timer."""
        if enabled:
            if not hasattr(self, "_pipe_anim_timer"):
                self._pipe_anim_timer = QtCore.QTimer(self)
                self._pipe_anim_timer.setInterval(_PIPE_ANIM_TICK_MS)
                self._pipe_anim_timer.timeout.connect(self._tick_pipe_animation)
                self._pipe_anim_offset = 0.0
            self._pipe_anim_timer.start()
        elif hasattr(self, "_pipe_anim_timer"):
            self._pipe_anim_timer.stop()
            # Reset pipes to solid style
            self._reset_pipe_dash()

    def _tick_pipe_animation(self) -> None:
        """Advance the dash offset on all pipes for a flowing animation."""
        from NodeGraphQt.qgraphics.pipe import PipeItem

        self._pipe_anim_offset = (self._pipe_anim_offset + 1.5) % 20.0
        for tab in self._file_tabs:
            scene = tab.graph.scene()
            if scene is None:
                continue
            for item in scene.items():
                if isinstance(item, PipeItem):
                    pen = item.pen()
                    pen.setDashPattern([4, 3])
                    pen.setDashOffset(self._pipe_anim_offset)
                    item.setPen(pen)

    def _reset_pipe_dash(self) -> None:
        """Remove dash pattern from all pipes (restore solid lines)."""
        from NodeGraphQt.qgraphics.pipe import PipeItem

        for tab in self._file_tabs:
            scene = tab.graph.scene()
            if scene is None:
                continue
            for item in scene.items():
                if isinstance(item, PipeItem):
                    pen = item.pen()
                    pen.setStyle(QtCore.Qt.PenStyle.SolidLine)
                    item.setPen(pen)

    @staticmethod
    def _save_node_editor_settings(s: NodeEditorSettings) -> None:
        """Persist node editor settings to settings.json."""
        import contextlib

        path = app_dirs.settings_path()
        data: dict[str, object] = {"version": 1}
        if path.is_file():
            with contextlib.suppress(json.JSONDecodeError, ValueError):
                data = json.loads(path.read_text(encoding="utf-8"))
        data["node_editor"] = node_editor_settings_to_dict(s)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _load_node_editor_settings() -> NodeEditorSettings:
        """Load node editor settings from settings.json, with defaults."""
        path = app_dirs.settings_path()
        if not path.is_file():
            return NodeEditorSettings()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data.get("node_editor")
            if isinstance(raw, dict):
                return node_editor_settings_from_dict(raw)
        except json.JSONDecodeError, TypeError, ValueError:
            pass
        return NodeEditorSettings()

    def _apply_code_editor_settings(self, s: CodeEditorSettings) -> None:
        """Apply code editor preferences to all open editors."""
        for tab in self._file_tabs:
            editor = tab.editor
            editor.set_editor_font(s.font_family, s.font_size)
            editor.set_show_line_numbers(s.show_line_numbers)
            editor.set_highlight_current_line(s.highlight_current_line)
            editor.set_word_wrap(s.word_wrap)
            editor.set_tab_width(s.tab_width)
            editor.set_auto_indent(s.auto_indent)
            editor.set_auto_close_brackets(s.auto_close_brackets)
            # Update parse debounce timer interval
            if tab.parse_timer is not None:
                tab.parse_timer.setInterval(
                    s.parse_debounce_ms if s.parse_debounce_enabled else 0,
                )

    def _apply_code_editor_settings_to(
        self,
        editor: CodeEditor,
        s: CodeEditorSettings,
    ) -> None:
        """Apply code editor preferences to a single editor instance."""
        editor.set_editor_font(s.font_family, s.font_size)
        editor.set_show_line_numbers(s.show_line_numbers)
        editor.set_highlight_current_line(s.highlight_current_line)
        editor.set_word_wrap(s.word_wrap)
        editor.set_tab_width(s.tab_width)
        editor.set_auto_indent(s.auto_indent)
        editor.set_auto_close_brackets(s.auto_close_brackets)

    @staticmethod
    def _save_code_editor_settings(s: CodeEditorSettings) -> None:
        """Persist code editor settings to settings.json."""
        import contextlib

        path = app_dirs.settings_path()
        data: dict[str, object] = {"version": 1}
        if path.is_file():
            with contextlib.suppress(json.JSONDecodeError, ValueError):
                data = json.loads(path.read_text(encoding="utf-8"))
        data["code_editor"] = code_editor_settings_to_dict(s)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _load_code_editor_settings() -> CodeEditorSettings:
        """Load code editor settings from settings.json, with defaults."""
        path = app_dirs.settings_path()
        if not path.is_file():
            return CodeEditorSettings()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data.get("code_editor")
            if isinstance(raw, dict):
                return code_editor_settings_from_dict(raw)
        except json.JSONDecodeError, TypeError, ValueError:
            pass
        return CodeEditorSettings()

    def _effective_custom_ids(self) -> list[str]:
        """Return the active custom ID list: project scope if loaded, else global."""
        if self._project is not None:
            raw = self._project.settings_overrides.get("custom_ids")
            if isinstance(raw, list):
                return [s for s in raw if isinstance(s, str)]
            return []
        return list(self._ac_settings.custom_ids)

    def _apply_autocomplete_settings(self, s: AutocompleteSettings) -> None:
        """Apply autocomplete preferences to all editors and node popup."""
        # Invalidate cached word list so _get_id_words() rebuilds with new sources
        self._id_words = None

        for tab in self._file_tabs:
            editor = tab.editor
            editor.set_min_prefix_length(s.min_prefix_length)
            editor.set_case_insensitive(s.case_insensitive)
            # Rebuild completer with updated word list
            self._setup_autocomplete_for(editor)

        # Rebuild node completers with updated word list
        for tab in self._file_tabs:
            for node in tab.graph.all_nodes():
                if isinstance(node, CraftGraphBaseNode):
                    self._attach_node_completers(node)

        self._node_popup.set_max_visible(s.max_visible_items)
        self._node_popup.set_case_insensitive(s.case_insensitive)

    def _apply_autocomplete_settings_to(
        self,
        editor: CodeEditor,
        s: AutocompleteSettings,
    ) -> None:
        """Apply autocomplete preferences to a single editor instance."""
        editor.set_min_prefix_length(s.min_prefix_length)
        editor.set_case_insensitive(s.case_insensitive)

    @staticmethod
    def _save_autocomplete_settings(s: AutocompleteSettings) -> None:
        """Persist autocomplete settings to settings.json."""
        import contextlib

        path = app_dirs.settings_path()
        data: dict[str, object] = {"version": 1}
        if path.is_file():
            with contextlib.suppress(json.JSONDecodeError, ValueError):
                data = json.loads(path.read_text(encoding="utf-8"))
        data["autocomplete"] = autocomplete_settings_to_dict(s)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _load_autocomplete_settings() -> AutocompleteSettings:
        """Load autocomplete settings from settings.json, with defaults."""
        path = app_dirs.settings_path()
        if not path.is_file():
            return AutocompleteSettings()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data.get("autocomplete")
            if isinstance(raw, dict):
                return autocomplete_settings_from_dict(raw)
        except json.JSONDecodeError, TypeError, ValueError:
            pass
        return AutocompleteSettings()

    def _start_file_watcher(self) -> None:
        """Start the Watchdog file watcher for the current source path."""
        if self._recipe_watcher is not None:
            return
        watch_dir = self._source_path
        if watch_dir.is_file():
            watch_dir = watch_dir.parent
        if not watch_dir.is_dir():
            return

        effective = (
            self._fw_settings.debounce_ms / 1000.0
            if self._fw_settings.debounce_enabled
            else 0.0
        )

        # RecipeWatcher.start() runs an initial_parse that fires on_rebuild
        # before any disk change has happened.  The GUI already loaded the
        # files itself via load_recipes(), so swallow that first callback to
        # avoid an infinite reload cycle (load_recipes -> watcher -> reload).
        skipped_initial = [False]

        def on_rebuild(
            _files: list[ParsedFile],
            _graph: networkx.DiGraph,
            _cycles: list[list[str]],
        ) -> None:
            if not skipped_initial[0]:
                skipped_initial[0] = True
                return
            QtCore.QTimer.singleShot(
                _DEFERRED_TICK_MS, lambda: self._on_watcher_rebuild(_cycles),
            )

        self._recipe_watcher = RecipeWatcher(
            watch_dir, on_rebuild, debounce_seconds=effective,
        )
        self._recipe_watcher.start()

    def _on_watcher_rebuild(self, cycles: list[list[str]]) -> None:
        """Handle a watcher-triggered reload with notification settings."""
        with hwnd_diag.measure("watcher_rebuild"):
            fw = self._fw_settings

            if fw.on_external_change == "ignore":
                return

            if fw.on_external_change == "prompt":
                reply = QtWidgets.QMessageBox.question(
                    self,
                    "External Change Detected",
                    "Recipe files changed on disk. Reload?",
                    QtWidgets.QMessageBox.StandardButton.Yes
                    | QtWidgets.QMessageBox.StandardButton.No,
                    QtWidgets.QMessageBox.StandardButton.Yes,
                )
                if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                    return

            self.load_recipes(self._source_path)

            fw = self._fw_settings
            if fw.notify_status_bar:
                total_nodes = sum(len(t.model_to_node) for t in self._file_tabs)
                total_cycles = sum(t.cycle_count for t in self._file_tabs)
                cycle_msg = f", {total_cycles} cycle(s)!" if total_cycles else ""
                self.statusBar().showMessage(
                    f"Reloaded {total_nodes} nodes from {len(self._file_tabs)} file(s){cycle_msg}"
                )

            if fw.notify_flash_tab:
                self._flash_tab_bar()

            if fw.notify_sound_on_cycle and cycles:
                QtWidgets.QApplication.beep()

    def _flash_tab_bar(self) -> None:
        """Briefly highlight the tab bar to signal an external change."""
        bar = self._tab_bar
        original_style = bar.styleSheet()
        bar.setStyleSheet("QTabBar { background-color: #ffcc00; }")
        QtCore.QTimer.singleShot(
            _TAB_FLASH_DURATION_MS, lambda: bar.setStyleSheet(original_style),
        )

    def _stop_file_watcher(self) -> None:
        """Stop the Watchdog file watcher if running."""
        if self._recipe_watcher is not None:
            self._recipe_watcher.stop()
            self._recipe_watcher = None

    def _apply_file_watching_settings(self, s: FileWatchingSettings) -> None:
        """Start, stop, or reconfigure the Watchdog file watcher."""
        if s.enabled and self._recipe_watcher is not None:
            effective = s.debounce_ms / 1000.0 if s.debounce_enabled else 0.0
            self._recipe_watcher.set_debounce_seconds(effective)
        elif not s.enabled and self._recipe_watcher is not None:
            self._stop_file_watcher()
        elif s.enabled and self._recipe_watcher is None:
            self._start_file_watcher()

    @staticmethod
    def _save_file_watching_settings(s: FileWatchingSettings) -> None:
        """Persist file watching settings to settings.json."""
        import contextlib

        path = app_dirs.settings_path()
        data: dict[str, object] = {"version": 1}
        if path.is_file():
            with contextlib.suppress(json.JSONDecodeError, ValueError):
                data = json.loads(path.read_text(encoding="utf-8"))
        data["file_watching"] = file_watching_settings_to_dict(s)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _load_file_watching_settings() -> FileWatchingSettings:
        """Load file watching settings from settings.json, with defaults."""
        path = app_dirs.settings_path()
        if not path.is_file():
            return FileWatchingSettings()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data.get("file_watching")
            if isinstance(raw, dict):
                return file_watching_settings_from_dict(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return FileWatchingSettings()

    def _apply_keybinding_settings(self, s: KeybindingSettings) -> None:
        """Set shortcuts on menu actions from persisted keybinding settings."""
        _action_map: dict[str, QtGui.QAction] = {
            "save": self._save_action,
            "save_all": self._save_all_action,
            "undo": self._undo_action,
            "redo": self._redo_action,
            "add_recipe": self._new_file_action,
            "open_settings": self._settings_action,
            "find_node": self._find_action,
        }
        for field_name, action in _action_map.items():
            seq = getattr(s, field_name, "")
            action.setShortcut(QtGui.QKeySequence(seq) if seq else QtGui.QKeySequence())

    @staticmethod
    def _save_keybinding_settings(s: KeybindingSettings) -> None:
        """Persist keybinding settings to settings.json."""
        import contextlib

        path = app_dirs.settings_path()
        data: dict[str, object] = {"version": 1}
        if path.is_file():
            with contextlib.suppress(json.JSONDecodeError, ValueError):
                data = json.loads(path.read_text(encoding="utf-8"))
        data["keybindings"] = keybinding_settings_to_dict(s)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _load_keybinding_settings() -> KeybindingSettings:
        """Load keybinding settings from settings.json, with defaults."""
        path = app_dirs.settings_path()
        if not path.is_file():
            return KeybindingSettings()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data.get("keybindings")
            if isinstance(raw, dict):
                return keybinding_settings_from_dict(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return KeybindingSettings()

    def _run_update_check(self) -> None:
        """Check for a newer CraftGraph version and show a status message."""
        from craftgraph import __version__
        from craftgraph.updater import check_for_update

        result = check_for_update(__version__)
        if result is not None:
            self.statusBar().showMessage(
                f"Update available: CraftGraph {result.version} -- download at {result.url}",
                15_000,
            )

    def _cc3_working_dir(self) -> str:
        """CC3 WorkingFiles/ path if configured, else empty string."""
        return cc3_working_files(self._subnautica_cc3_path)

    def _cc3_assets_dir(self) -> str:
        """CC3 Assets/ path if configured, else empty string."""
        return cc3_assets(self._subnautica_cc3_path)

    def _on_about(self) -> None:
        """Show the About CraftGraph dialog."""
        from craftgraph import __version__

        QtWidgets.QMessageBox.about(
            self,
            "About CraftGraph",
            f"<h3>CraftGraph v{__version__}</h3>"
            f"<p>Recipe dependency graph tool for "
            f"<b>CustomCraft3</b> (Subnautica).</p>"
            f"<p>Parses EasyMarkup recipe files, detects circular "
            f"dependencies, and provides a visual node editor.</p>",
        )

    def _show_error_status(
        self, message: str, duration_ms: int = _STATUS_ERROR_DEFAULT_MS,
    ) -> None:
        """Show *message* with a red background in the status bar."""
        bar = self.statusBar()
        bar.setStyleSheet("QStatusBar { background-color: #cc3c3c; color: white; }")
        bar.showMessage(message)
        QtCore.QTimer.singleShot(duration_ms, self._clear_status_style)

    def _on_cycle_rejected(
        self,
        consumer_id: str,
        ingredient_id: str,
        cycle_path: list[str],
    ) -> None:
        """Show a red-background status bar warning when a connection would create a cycle."""
        path_str = " -> ".join(cycle_path)
        self._show_error_status(f"Rejected: circular dependency detected ({path_str})")

    def _on_reassignment_warning(self, item_id: str, old_path: str) -> None:
        """Show a warning when a recipe is reassigned from an existing path."""
        self._show_error_status(f"Recipe '{item_id}' reassigned from '{old_path}'")

    def _clear_status_style(self) -> None:
        """Reset the status bar to its default style."""
        self.statusBar().setStyleSheet("")

    # -- Smart placement -------------------------------------------------------

    # Nudge offset per collision iteration.
    _NUDGE_X = 30.0
    _NUDGE_Y = 30.0
    _NUDGE_MAX_ITER = 20

    @staticmethod
    def _find_free_position(
        graph: NodeGraph,
        x: float,
        y: float,
        w_est: float = 200.0,
        h_est: float = 120.0,
    ) -> tuple[float, float]:
        """Return (x, y) nudged away from existing nodes if overlapping.

        Coordinates are top-left origin (matching NodeGraphQt's node.pos()).
        Checks whether a rectangle of *w_est* x *h_est* at (x, y) collides
        with any existing node's bounding rect.  On each collision the
        candidate is shifted by (_NUDGE_X, _NUDGE_Y) and retested, up to
        _NUDGE_MAX_ITER times.
        """
        for _ in range(CraftGraphWindow._NUDGE_MAX_ITER):
            collision = False
            for node in graph.all_nodes():
                nx, ny = node.pos()
                view = getattr(node, "view", None)
                if view is not None:
                    rect = view.boundingRect()
                    nw, nh = rect.width(), rect.height()
                else:
                    nw, nh = w_est, h_est
                # Top-left AABB overlap: two rects overlap when
                # each left edge is left of the other's right edge
                # and each top edge is above the other's bottom edge.
                if x < nx + nw and x + w_est > nx and y < ny + nh and y + h_est > ny:
                    collision = True
                    break
            if not collision:
                return x, y
            x += CraftGraphWindow._NUDGE_X
            y += CraftGraphWindow._NUDGE_Y
        return x, y

    # -- Node operations (delete, copy, paste, duplicate) --------------------

    def _matches_keybinding(self, event: QtGui.QKeyEvent, field_name: str) -> bool:
        """Return True if *event* matches the keybinding for *field_name*.

        ``QKeyEvent.matches()`` only takes a ``StandardKey`` enum, so build a
        single-key ``QKeySequence`` from the event itself and compare it to
        the configured sequence string.
        """
        seq_str = getattr(self._kb_settings, field_name, "")
        if not seq_str:
            return False
        configured = QtGui.QKeySequence(seq_str)
        if configured.isEmpty():
            return False
        event_seq = QtGui.QKeySequence(event.keyCombination())
        return event_seq == configured

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # type: ignore[override]
        """Handle keyboard shortcuts for node operations."""
        key = event.key()
        ctrl = bool(event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier)

        if self._matches_keybinding(event, "delete_nodes"):
            self._delete_selected_nodes()
        elif self._matches_keybinding(event, "select_all"):
            self._select_all_nodes()
        elif self._matches_keybinding(event, "zoom_to_fit"):
            self._zoom_to_fit()
        elif self._matches_keybinding(event, "toggle_code_editor"):
            self._toggle_code_editor()
        elif self._matches_keybinding(event, "find_node"):
            self._find_node_by_id()
        elif ctrl and key == QtCore.Qt.Key.Key_C:
            self.graph.copy_nodes()
        elif ctrl and key == QtCore.Qt.Key.Key_V:
            self._paste_nodes()
        elif ctrl and key == QtCore.Qt.Key.Key_D:
            self._duplicate_selected_nodes()
        else:
            super().keyPressEvent(event)

    def _delete_selected_nodes(self) -> None:
        """Delete all currently selected nodes from the graph and model."""
        selected = self.graph.selected_nodes()
        if not selected:
            return
        self.graph.clear_selection()
        self.graph.delete_nodes(selected)
        self._update_code_editor_from_model()

    def _select_all_nodes(self) -> None:
        """Select every node in the active graph."""
        if not self._file_tabs:
            return
        self._active_tab.graph.select_all()

    def _zoom_to_fit(self) -> None:
        """Zoom the active graph to fit all nodes in view."""
        if not self._file_tabs:
            return
        self._active_tab.graph.fit_to_selection()

    def _toggle_code_editor(self) -> None:
        """Show or hide the right-hand code editor panel."""
        sizes = self._splitter.sizes()
        if sizes[1] > 0:
            self._splitter_saved_sizes = list(sizes)
            self._splitter.setSizes([sizes[0] + sizes[1], 0])
        else:
            restored = getattr(self, "_splitter_saved_sizes", [980, 420])
            self._splitter.setSizes(restored)

    def _find_node_by_id(self) -> None:
        """Open the inline node search bar (keybinding entry point)."""
        if not self._file_tabs:
            return
        bar = self._ensure_search_bar()
        self._position_search_bar()
        bar.show()
        bar.focus_field()
        self._update_search_matches()

    def _ensure_search_bar(self) -> NodeSearchBar:
        """Create the search bar lazily and wire its signals."""
        if self._search_bar is not None:
            return self._search_bar
        bar = NodeSearchBar(self)
        bar.text_changed.connect(self._on_search_text_changed)
        bar.next_requested.connect(self._on_search_next)
        bar.prev_requested.connect(self._on_search_prev)
        bar.close_requested.connect(self._close_search_bar)
        self._search_bar = bar
        return bar

    def _position_search_bar(self) -> None:
        """Anchor the search bar to the top-right of the central widget."""
        bar = self._search_bar
        if bar is None:
            return
        bar.adjustSize()
        anchor = self.centralWidget() or self
        margin = 12
        x = anchor.width() - bar.width() - margin
        y = margin
        bar.move(anchor.mapTo(self, QtCore.QPoint(x, y)))
        bar.raise_()

    def _close_search_bar(self) -> None:
        """Hide the search bar and clear match state."""
        if self._search_bar is None:
            return
        self._search_bar.hide()
        self._search_bar.clear_query()
        self._search_matches = []
        self._search_index = 0

    def _node_search_strings(self, node: object) -> list[str]:
        """Return the lowercase strings to match against for *node*."""
        result: list[str] = []
        model = getattr(node, "model_ref", None)
        for attr in ("item_id", "tab_id", "display_name"):
            value = getattr(model, attr, None)
            if isinstance(value, str) and value:
                result.append(value.lower())
        name = getattr(node, "name", None)
        if callable(name):
            nm = name()
            if isinstance(nm, str) and nm:
                result.append(nm.lower())
        return result

    def _compute_search_matches(self, query: str) -> list[object]:
        """Return nodes whose searchable strings contain *query* (lowercased)."""
        if not query:
            return []
        tab = self._active_tab
        if tab is None:
            return []
        q = query.lower()
        return [
            node
            for node in tab.graph.all_nodes()
            if any(q in s for s in self._node_search_strings(node))
        ]

    def _update_search_matches(self) -> None:
        """Recompute matches for the current query and refresh the count label."""
        bar = self._search_bar
        if bar is None:
            return
        self._search_matches = self._compute_search_matches(bar.query)
        self._search_index = 0
        bar.set_match_count(self._search_index, len(self._search_matches))
        if self._search_matches:
            self._select_current_search_match()

    def _select_current_search_match(self) -> None:
        """Select + center the graph on the current search match."""
        if not self._search_matches:
            return
        tab = self._active_tab
        if tab is None:
            return
        node = self._search_matches[self._search_index]
        tab.graph.clear_selection()
        node.set_selected(True)
        self._center_view_on_nodes(tab.graph, [node])
        bar = self._search_bar
        if bar is not None:
            bar.set_match_count(self._search_index, len(self._search_matches))

    def _on_editor_selection_changed(self, tab: FileTab) -> None:
        """Sync a multi-line code-editor selection into multi-node graph selection.

        Single-line selections (or no selection) are ignored to avoid
        spamming the graph on every cursor movement.  When the selected
        text spans multiple lines, every ``ItemID:`` / ``TabID:`` value
        within the range is matched against the active graph and the
        union of matching nodes is selected and centred on.
        """
        if tab.sync_guard.active:
            return
        cursor = tab.editor.textCursor()
        if not cursor.hasSelection():
            return
        selected_text = cursor.selectedText()
        # ``QTextCursor.selectedText`` returns U+2029 between blocks rather
        # than ``\n``.  A bare cursor on one line has neither separator;
        # only react to multi-line selections.
        if "\u2029" not in selected_text:
            return

        ids: set[str] = set()
        for match in _ID_REFERENCE_RE.finditer(selected_text):
            ids.add(match.group(1).strip().lower())
        if not ids:
            return

        matches: list[object] = []
        for node in tab.graph.all_nodes():
            ref = getattr(node, "model_ref", None)
            matched = False
            for attr in ("item_id", "tab_id"):
                value = getattr(ref, attr, None)
                if isinstance(value, str) and value.lower() in ids:
                    matches.append(node)
                    matched = True
                    break
            if matched:
                continue
            # Orphan ingredient nodes have no model_ref; fall back to the
            # ItemID widget value carried directly on the node.
            getter = getattr(node, "get_property", None)
            if callable(getter):
                widget_id = getter("item_id")
                if isinstance(widget_id, str) and widget_id.lower() in ids:
                    matches.append(node)
        if not matches:
            return

        with tab.sync_guard():
            tab.graph.clear_selection()
            for node in matches:
                node.set_selected(True)
        self._center_view_on_nodes(tab.graph, matches)

    @staticmethod
    def _center_view_on_nodes(graph: NodeGraph, nodes: list[object]) -> None:
        """Pan the QGraphicsView so the union of *nodes* is centred.

        NodeGraphQt's viewer keeps both scrollbars set to
        ``ScrollBarAlwaysOff`` (see ``NodeViewer.__init__``), so the
        canonical ``QGraphicsView.centerOn`` is a no-op: there are no
        scrollbars for it to drive.  Panning happens by translating the
        viewer's internal ``_scene_range`` rect and re-fitting it via
        ``fitInView`` -- the same dance ``_set_viewer_pan`` performs on
        every drag step.  Zoom is preserved because the rect's width and
        height are unchanged; only its centre moves.
        """
        if not nodes:
            return
        viewer = graph.viewer()
        if viewer is None:
            return
        rect = QtCore.QRectF()
        for node in nodes:
            view = getattr(node, "view", None)
            if view is None:
                continue
            node_rect = view.sceneBoundingRect()
            rect = node_rect if rect.isEmpty() else rect.united(node_rect)
        if rect.isEmpty():
            return
        scene_range = getattr(viewer, "_scene_range", None)
        if scene_range is None:
            # Defensive fallback for non-NodeGraphQt viewers (e.g. plain
            # QGraphicsView in unit tests) -- keep the standard centerOn.
            viewer.centerOn(rect.center())
            return
        delta = rect.center() - scene_range.center()
        scene_range.translate(delta)
        viewer.setSceneRect(scene_range)
        viewer.fitInView(scene_range, QtCore.Qt.AspectRatioMode.KeepAspectRatio)

    def _on_search_text_changed(self, _text: str) -> None:
        self._update_search_matches()

    def _on_search_next(self) -> None:
        if not self._search_matches:
            return
        self._search_index = (self._search_index + 1) % len(self._search_matches)
        self._select_current_search_match()

    def _on_search_prev(self) -> None:
        if not self._search_matches:
            return
        self._search_index = (
            self._search_index - 1
        ) % len(self._search_matches)
        self._select_current_search_match()

    def _node_lookup_id(self, node: object) -> str | None:
        """Return the lowercase ItemID/TabID of *node* for cross-tab matching.

        Prefers the model_ref (definitive) over the displayed widget value
        (which orphan ingredients use, since they have no model_ref).
        """
        ref = getattr(node, "model_ref", None)
        for attr in ("item_id", "tab_id"):
            value = getattr(ref, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
        for attr in ("item_id", "tab_id"):
            try:
                value = node.get_property(attr)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                value = None
            if isinstance(value, str) and value.strip():
                return value.strip().lower()
        return None

    def _find_definition(self, item_id: str) -> tuple[int, object] | None:
        """Locate the model-backed node defining *item_id* across all open tabs.

        Returns ``(tab_index, node)`` or ``None`` when no defining tab holds
        a recipe / tab / fabricator with the given ID.  Orphan nodes are
        ignored — they are references, not definitions.
        """
        target = item_id.strip().lower()
        if not target:
            return None
        for idx, tab in enumerate(self._file_tabs):
            for node in tab.model_to_node.values():
                ref = getattr(node, "model_ref", None)
                for attr in ("item_id", "tab_id"):
                    value = getattr(ref, attr, None)
                    if isinstance(value, str) and value.strip().lower() == target:
                        return idx, node
        return None

    def _go_to_definition(self, node: object) -> bool:
        """Switch to the tab where *node* is defined and select it.

        Returns ``True`` when navigation happened, ``False`` when the
        definition could not be located (e.g. references an ID with no
        defining recipe in any open tab).
        """
        item_id = self._node_lookup_id(node)
        if item_id is None:
            self._show_error_status("No ID on this node to look up")
            return False
        target = self._find_definition(item_id)
        if target is None:
            self._show_error_status(f"No definition for '{item_id}' in open tabs")
            return False
        tab_index, def_node = target
        if 0 <= tab_index < len(self._file_tabs):
            self._tab_bar.setCurrentIndex(tab_index)
        tab = self._file_tabs[tab_index]
        tab.graph.clear_selection()
        def_node.set_selected(True)
        self._center_view_on_nodes(tab.graph, [def_node])
        self.statusBar().showMessage(f"Jumped to '{item_id}'")
        return True

    def _on_go_to_definition(
        self,
        _graph: NodeGraph,
        node: CraftGraphBaseNode,
    ) -> None:
        """Context menu callback: jump to the tab/node that defines this ID."""
        self._go_to_definition(node)

    def _on_node_double_clicked(self, node: object) -> None:
        """Double-click handler: navigate to the defining recipe across tabs.

        For nodes already living in the current tab the call is a no-op
        (the node is already on screen).  Cross-file orphan ingredients
        and reference nodes navigate to their source.
        """
        if node is None:
            return
        item_id = self._node_lookup_id(node)
        if item_id is None:
            return
        # Skip when this very node is already the definition.
        ref = getattr(node, "model_ref", None)
        if ref is not None:
            for attr in ("item_id", "tab_id"):
                value = getattr(ref, attr, None)
                if isinstance(value, str) and value.strip().lower() == item_id:
                    return
        self._go_to_definition(node)

    def _on_delete_node(
        self,
        graph: NodeGraph,
        node: CraftGraphBaseNode,
    ) -> None:
        """Context menu callback: delete a single node."""
        graph.clear_selection()
        graph.delete_node(node)
        self._update_code_editor_from_model()

    def _on_copy_node(
        self,
        graph: NodeGraph,
        node: CraftGraphBaseNode,
    ) -> None:
        """Context menu callback: copy the node to clipboard."""
        graph.copy_nodes([node])

    def _on_duplicate_node(
        self,
        graph: NodeGraph,
        node: CraftGraphBaseNode,
    ) -> None:
        """Context menu callback: duplicate a single node."""
        new_nodes = graph.duplicate_nodes([node])
        if new_nodes:
            self._adopt_orphan_nodes(new_nodes)

    def _paste_nodes(self) -> None:
        """Paste nodes from clipboard and wire them into the model."""
        new_nodes = self.graph.paste_nodes()
        if new_nodes:
            self._adopt_orphan_nodes(new_nodes)

    def _duplicate_selected_nodes(self) -> None:
        """Duplicate selected nodes and wire them into the model."""
        selected = self.graph.selected_nodes()
        if not selected:
            return
        new_nodes = self.graph.duplicate_nodes(selected)
        if new_nodes:
            self._adopt_orphan_nodes(new_nodes)

    def _adopt_orphan_nodes(self, nodes: list[object]) -> None:
        """Create model objects for pasted/duplicated nodes.

        NodeGraphQt's paste/duplicate creates visual nodes with correct
        properties but no ``model_ref``. This method reads each node's
        properties, creates a matching model object, appends it to the
        parsed file, and sets ``model_ref``.
        """
        from craftgraph.models import (
            AddedRecipe,
            AliasRecipe,
            CraftingTab,
            CustomBioFuel,
            CustomFabricator,
            CustomFood,
            CustomFragmentCount,
            CustomSize,
            ModifiedRecipe,
            MovedRecipe,
        )
        from craftgraph.qt_nodes import (
            AddedRecipeNode,
            AliasRecipeNode,
            CraftingTabNode,
            CustomBioFuelNode,
            CustomFoodNode,
            CustomFragmentCountNode,
            CustomSizeNode,
            FabricatorNode,
            ModifiedRecipeNode,
            MovedRecipeNode,
        )

        tab = self._active_tab
        if tab.parsed_file is None:
            return

        # Map node class -> (model_class, parsed_file_attr_name)
        # Order: most-specific first for isinstance dispatch
        node_to_model: list[tuple[type, type, str]] = [
            (CustomFoodNode, CustomFood, "custom_foods"),
            (AliasRecipeNode, AliasRecipe, "alias_recipes"),
            (AddedRecipeNode, AddedRecipe, "added_recipes"),
            (ModifiedRecipeNode, ModifiedRecipe, "modified_recipes"),
            (FabricatorNode, CustomFabricator, "custom_fabricators"),
            (CraftingTabNode, CraftingTab, "crafting_tabs"),
            (CustomSizeNode, CustomSize, "custom_sizes"),
            (MovedRecipeNode, MovedRecipe, "moved_recipes"),
            (CustomBioFuelNode, CustomBioFuel, "custom_bio_fuels"),
            (CustomFragmentCountNode, CustomFragmentCount, "custom_fragment_counts"),
        ]

        for node in nodes:
            if not isinstance(node, CraftGraphBaseNode):
                continue
            if node.model_ref is not None:
                continue  # already adopted

            model = None
            attr_name = None

            for node_cls, model_cls, attr in node_to_model:
                if not isinstance(node, node_cls):
                    continue

                if model_cls is CraftingTab:
                    model = model_cls(
                        tab_id=node.get_property("tab_id") or "NewTab",
                    )
                elif model_cls is CustomFabricator:
                    model = model_cls(
                        item_id=node.get_property("item_id") or "NewFab",
                        display_name=node.get_property("display_name") or "",
                    )
                elif model_cls is CustomSize:
                    model = model_cls(
                        item_id=node.get_property("item_id") or "NewItem",
                    )
                    model.width = int(node.get_property("size_width") or 1)
                    model.height = int(node.get_property("size_height") or 1)
                elif model_cls is CustomBioFuel:
                    model = model_cls(
                        item_id=node.get_property("item_id") or "NewItem",
                    )
                    model.energy = float(node.get_property("energy") or 0)
                elif model_cls is CustomFragmentCount:
                    model = model_cls(
                        item_id=node.get_property("item_id") or "NewItem",
                    )
                    model.fragments_to_scan = int(node.get_property("fragments_to_scan") or 1)
                elif model_cls is MovedRecipe:
                    model = model_cls(
                        item_id=node.get_property("item_id") or "NewItem",
                    )
                    model.old_path = node.get_property("old_path") or ""
                    model.new_path = node.get_property("new_path") or ""
                else:
                    # Recipe types
                    model = model_cls(
                        item_id=node.get_property("item_id") or "NewItem",
                    )
                    if hasattr(model, "amount_crafted"):
                        model.amount_crafted = int(node.get_property("amount_crafted") or 1)
                    if hasattr(model, "path"):
                        model.path = node.get_property("path") or ""
                    if hasattr(model, "display_name"):
                        model.display_name = node.get_property("display_name") or ""
                    if hasattr(model, "tooltip"):
                        model.tooltip = node.get_property("tooltip") or ""

                attr_name = attr
                break

            if model is None or attr_name is None:
                continue

            # Apply the duplication suffix (e.g. " 1") to display_name so
            # serialised paths stay unique across copies.
            base_id = getattr(model, "item_id", None) or getattr(model, "tab_id", "")
            node_title = node.name()
            if base_id and node_title.startswith(base_id) and len(node_title) > len(base_id):
                suffix = node_title[len(base_id) :]
                if hasattr(model, "display_name") and model.display_name:
                    model.display_name += suffix
                    node.set_property("display_name", model.display_name)

            node.model_ref = model
            node.set_edit_history(tab.history)
            tab.model_to_node[id(model)] = node
            self._append_model_to_parsed_file(tab.parsed_file, attr_name, model)

            if tab.ui_handler is not None:
                tab.ui_handler.register_node(node)

            self._attach_node_completers(node)

        self._update_code_editor_from_model()

    # Attribute name mapping: top-level ParsedFile attr -> CustomFabricator attr
    # for types that nest inside fabricators.
    _FAB_NESTED_ATTR: dict[str, str] = {
        "crafting_tabs": "tabs",
        "added_recipes": "added_recipes",
        "alias_recipes": "alias_recipes",
        "moved_recipes": "moved_recipes",
        "custom_foods": "custom_foods",
    }

    def _append_model_to_parsed_file(
        self,
        pf: ParsedFile,
        attr_name: str,
        model: object,
    ) -> None:
        """Append a model to the correct list in the parsed file.

        For ``CustomFabricators`` files, certain types (tabs, recipes)
        nest inside the fabricator rather than at the top level.  This
        method routes the model to the right sub-list so the serializer
        picks it up.
        """
        if (
            pf.block_type == BlockType.CUSTOM_FABRICATORS
            and attr_name in self._FAB_NESTED_ATTR
            and pf.custom_fabricators
        ):
            fab_attr = self._FAB_NESTED_ATTR[attr_name]
            getattr(pf.custom_fabricators[0], fab_attr).append(model)
        else:
            getattr(pf, attr_name).append(model)

    def _on_model_changed(self) -> None:
        """Called by EditHistory after every execute/undo/redo.

        Updates the window title (dirty flag), re-serializes the model
        into the code editor, and refreshes child count labels on
        container nodes so the text always reflects the current state.
        """
        tab = self._active_tab
        title = "CraftGraph"
        if tab.parsed_file is not None:
            title += f" - {tab.parsed_file.source_path.name}"
        if hasattr(tab.history, "is_dirty") and tab.history.is_dirty:
            title += " *"
        self.setWindowTitle(title)
        self._update_code_editor_from_model()
        update_child_count_labels(tab.model_to_node)

    def _update_code_editor_from_model(self) -> None:
        """Serialize the active tab's model into its code editor.

        Preserves the cursor position and scroll offset so the editor
        does not jump to the top after every model re-serialization.
        """
        tab = self._active_tab
        if tab.parsed_file is None:
            return
        editor = tab.editor
        # Save position before replacing text
        cursor = editor.textCursor()
        cursor_pos = cursor.position()
        anchor_pos = cursor.anchor()
        scroll_val = editor.verticalScrollBar().value()

        with tab.sync_guard():
            editor.setPlainText(serialize_file(tab.parsed_file))

        # Restore cursor position (clamped to new document length)
        new_cursor = editor.textCursor()
        doc_len = editor.document().characterCount() - 1
        new_cursor.setPosition(min(anchor_pos, doc_len))
        if anchor_pos != cursor_pos:
            new_cursor.setPosition(
                min(cursor_pos, doc_len),
                QtGui.QTextCursor.MoveMode.KeepAnchor,
            )
        editor.setTextCursor(new_cursor)
        editor.verticalScrollBar().setValue(scroll_val)

    # -- Node selection -> code editor scroll -----------------------------------

    def _scroll_editor_to_node(self, node: object, tab: FileTab) -> None:
        """Scroll the code editor to the entry corresponding to *node*.

        Searches for ``ItemID: <value>`` or ``TabID: <value>`` in the
        editor text and highlights the entire block (from the ID line
        up to the next entry or end of file).
        """
        model = getattr(node, "model_ref", None)
        if model is None:
            return

        item_id = getattr(model, "item_id", None) or getattr(model, "tab_id", None)
        if not item_id:
            return

        editor = tab.editor
        text = editor.toPlainText()

        # Search for "ItemID: <value>" or "TabID: <value>" (case-insensitive).
        # Use a word-boundary anchor after the value so that e.g.
        # "Alch_LabContainer" does not match "Alch_LabContainer3".
        import re

        search_patterns = [
            rf"ItemID:\s*{re.escape(item_id)}\b",
            rf"TabID:\s*{re.escape(item_id)}\b",
        ]

        target_line = -1
        for pattern in search_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                target_line = text[: match.start()].count("\n")
                break

        if target_line < 0:
            return

        # Move cursor to the target line and highlight it
        block = editor.document().findBlockByNumber(target_line)
        if not block.isValid():
            return

        cursor = editor.textCursor()
        cursor.setPosition(block.position())

        # Select from the ItemID/TabID line to the closing ");" or next entry
        end_block = block
        lines_text = text.split("\n")
        for i in range(target_line + 1, min(target_line + 200, len(lines_text))):
            line = lines_text[i].strip()
            # Stop at the next entry boundary or closing delimiter
            if line.startswith("ItemID:") or line.startswith("TabID:"):
                break
            if line in ("),", ");", ")"):
                break
            end_block = end_block.next()
            if not end_block.isValid():
                break

        cursor.setPosition(
            end_block.position() + end_block.length() - 1,
            QtGui.QTextCursor.MoveMode.KeepAnchor,
        )
        with tab.sync_guard():
            editor.setTextCursor(cursor)
        editor.centerCursor()

    # -- Code editor -> model sync (per-tab) ----------------------------------

    def _apply_code_editor_text_for(self, tab: FileTab) -> None:
        """Parse the code editor text and rebuild the tab's node graph."""
        from craftgraph.parser import MappingError, ParseError, parse_text

        text = tab.editor.toPlainText()
        if not text.strip():
            return

        src = tab.parsed_file.source_path if tab.parsed_file is not None else self._source_path
        try:
            pf = parse_text(text, source_path=src)
        except (ParseError, MappingError) as exc:
            self.statusBar().showMessage(f"Parse error: {exc}")
            if self._ce_settings.show_parse_errors_inline:
                line = getattr(exc, "line", 0)
                tab.editor.show_parse_error(line, str(exc))
            return

        tab.editor.clear_parse_errors()

        # Tear down previous handler
        if tab.ui_handler is not None:
            tab.ui_handler.disconnect()
            tab.ui_handler = None

        tab.graph.clear_session()
        tab.history.clear()

        with tab.sync_guard(), self._suspend_graph_updates(tab.graph):
            tab.model_to_node = populate_graph(tab.graph, [pf], edit_history=tab.history)
            connect_hierarchy(tab.graph, [pf], tab.model_to_node)
            conn_result = connect_ingredients(tab.graph, [pf], tab.model_to_node)
            tab.orphan_nodes = conn_result.orphan_nodes
            positions = compute_hierarchy_layout([pf], tab.model_to_node)
            overlay_user_positions(positions, tab.user_positions, tab.model_to_node)
            apply_layout(positions, tab.model_to_node)
            place_orphan_nodes(tab.graph)
            highlight_cycle_edges(tab.graph, [pf], tab.model_to_node)
            update_node_issue_overlays(
                tab.graph,
                [pf],
                tab.model_to_node,
                frozenset(i.lower() for i in self._get_id_words()),
            )
            self._stamp_source_file(tab.model_to_node, pf.source_path.name)
            update_child_count_labels(tab.model_to_node)

        tab.parsed_file = pf
        self._apply_sprites_for(tab)
        self._update_path_completions()
        tab.ui_handler = UIToModelHandler(
            graph=tab.graph,
            history=tab.history,
            guard=tab.sync_guard,
            parsed_files=[pf],
            model_to_node=tab.model_to_node,
            on_cycle_rejected=self._on_cycle_rejected,
            on_reassignment_warning=self._on_reassignment_warning,
        )

        node_count = len(tab.model_to_node)
        self.statusBar().showMessage(f"Parsed {node_count} node(s) from editor")

    # -- Context menus (per-graph) --------------------------------------------

    def _setup_context_menus_for(self, graph: NodeGraph) -> None:
        """Register sprite and node-creation context menus on a graph."""
        # Fix scrollwheel in embedded combo boxes
        viewer = graph.viewer()
        wheel_filter = _ViewerWheelFilter(viewer)
        viewer.installEventFilter(wheel_filter)

        # Sync modifier states on mouse press to fix stale ALT_state
        mod_filter = _ViewerModifierSyncFilter(viewer)
        viewer.installEventFilter(mod_filter)

        # Accept PNG file drag-drop from OS file manager
        viewer.setAcceptDrops(True)
        drop_filter = _ViewerDropFilter(viewer, window=self)
        viewer.installEventFilter(drop_filter)

        # Node operations
        nodes_menu = graph.get_context_menu("nodes")
        nodes_menu.add_command(
            "Delete",
            func=self._on_delete_node,
            node_class=CraftGraphBaseNode,
        )
        nodes_menu.add_command(
            "Copy",
            func=self._on_copy_node,
            node_class=CraftGraphBaseNode,
        )
        nodes_menu.add_command(
            "Duplicate",
            func=self._on_duplicate_node,
            node_class=CraftGraphBaseNode,
        )

        # Selection toggle
        nodes_menu.add_command(
            "Toggle Selection",
            func=self._on_toggle_selection,
            node_class=CraftGraphBaseNode,
        )

        nodes_menu.add_command(
            "Go to Definition",
            func=self._on_go_to_definition,
            node_class=CraftGraphBaseNode,
        )

        # Ingredient management (recipe nodes only)
        for op_name, op_func in [
            ("Delete Ingredient...", self._on_delete_ingredient),
            ("Promote Ingredient to Recipe...", self._on_promote_ingredient),
        ]:
            cmd = nodes_menu.add_command(
                op_name,
                func=op_func,
                node_class=ModifiedRecipeNode,
            )
            if op_name in OPERATION_DESCRIPTIONS:
                cmd.qaction.setToolTip(OPERATION_DESCRIPTIONS[op_name])

        # Promote field to variable node
        cmd = nodes_menu.add_command(
            "Promote to Variable...",
            func=self._on_promote_to_variable,
            node_class=CraftGraphBaseNode,
        )
        if "Promote to Variable..." in OPERATION_DESCRIPTIONS:
            cmd.qaction.setToolTip(OPERATION_DESCRIPTIONS["Promote to Variable..."])

        # Sprite context menu entries removed -- use SpriteNode instead

        # Canvas operations
        graph_menu = graph.get_context_menu("graph")
        graph_menu.add_command(
            "Paste",
            func=lambda g: self._paste_nodes(),
        )

        # Node creation submenu (regular QActions with HTML tooltips)
        add_menu = graph_menu.add_menu("Add Node")

        cmd = add_menu.add_command(
            "Ingredient",
            func=lambda g: self._create_orphan_ingredient(),
        )
        cmd.qaction.setToolTip(format_tooltip("Ingredient", NODE_DESCRIPTIONS["Ingredient"]))

        recipes_menu = add_menu.add_menu("Recipes")
        for kind, name in [
            (NodeKind.MODIFIED_RECIPE, "Modified Recipe"),
            (NodeKind.ADDED_RECIPE, "Added Recipe"),
            (NodeKind.ALIAS_RECIPE, "Alias Recipe"),
            (NodeKind.CUSTOM_FOOD, "Custom Food"),
        ]:
            desc = NODE_DESCRIPTIONS.get(name, "")
            cmd = recipes_menu.add_command(
                name,
                func=self._make_create_callback(kind),
            )
            cmd.qaction.setToolTip(format_tooltip(name, desc))

        containers_menu = add_menu.add_menu("Containers")
        for kind, name in [
            (NodeKind.FABRICATOR, "Fabricator"),
            (NodeKind.CRAFTING_TAB, "Crafting Tab"),
        ]:
            desc = NODE_DESCRIPTIONS.get(name, "")
            cmd = containers_menu.add_command(
                name,
                func=self._make_create_callback(kind),
            )
            cmd.qaction.setToolTip(format_tooltip(name, desc))

        other_menu = add_menu.add_menu("Utility")
        for kind, name in [
            (NodeKind.CUSTOM_SIZE, "Custom Size"),
            (NodeKind.MOVED_RECIPE, "Moved Recipe"),
            (NodeKind.CUSTOM_BIO_FUEL, "Custom BioFuel"),
            (NodeKind.CUSTOM_FRAGMENT_COUNT, "Custom Fragment Count"),
            (NodeKind.SPRITE, "Sprite"),
        ]:
            desc = NODE_DESCRIPTIONS.get(name, "")
            cmd = other_menu.add_command(
                name,
                func=self._make_create_callback(kind),
            )
            cmd.qaction.setToolTip(format_tooltip(name, desc))

        from craftgraph.qt_variable_nodes import VariableNodeKind

        variables_menu = add_menu.add_menu("Variables")
        for var_kind, name in [
            (VariableNodeKind.STRING_VAR, "String Variable"),
            (VariableNodeKind.INT_VAR, "Int Variable"),
            (VariableNodeKind.FLOAT_VAR, "Float Variable"),
            (VariableNodeKind.BOOL_VAR, "Bool Variable"),
            (VariableNodeKind.CSV_LIST_VAR, "CSV List Variable"),
            (VariableNodeKind.ENUM_VAR, "Enum Variable"),
            (VariableNodeKind.PATH_VAR, "Path Variable"),
            (VariableNodeKind.COLOR_VAR, "Color Variable"),
            (VariableNodeKind.GET_FABRICATOR, "Get Fabricator"),
            (VariableNodeKind.GET_TAB, "Get Tab"),
        ]:
            desc = VARIABLE_DESCRIPTIONS.get(name, "")
            cmd = variables_menu.add_command(
                name,
                func=self._make_var_create_cb(var_kind),
            )
            cmd.qaction.setToolTip(format_tooltip(name, desc))

        # Enable floating tooltips on all context menus
        enable_menu_tooltips(nodes_menu.qmenu)
        enable_menu_tooltips(graph_menu.qmenu)

        # Snapshot the scene pos at menu open-time. By the time a "Create X"
        # callback runs, the cursor has moved to the chosen menu item; use
        # this snapshot so nodes spawn at the actual right-click location.
        def _snapshot_scene_pos() -> None:
            pos = viewer.mapFromGlobal(QtGui.QCursor.pos())
            self._menu_invoke_scene_pos = viewer.mapToScene(pos)

        graph_menu.qmenu.aboutToShow.connect(_snapshot_scene_pos)
        nodes_menu.qmenu.aboutToShow.connect(_snapshot_scene_pos)

        # Double-click on a node = jump to its definition across tabs.
        graph.node_double_clicked.connect(self._on_node_double_clicked)

    def _menu_spawn_scene_pos(self, viewer: QtWidgets.QGraphicsView) -> tuple[float, float]:
        """Return the scene (x, y) for spawning a node from a context-menu action.

        Uses the scene pos captured when the menu opened. Falls back to the
        live cursor pos only when no capture is available (e.g. keyboard
        shortcut invocation with no menu).
        """
        pos = self._menu_invoke_scene_pos
        if pos is not None:
            return pos.x(), pos.y()
        cursor_pos = viewer.mapFromGlobal(QtGui.QCursor.pos())
        scene_pos = viewer.mapToScene(cursor_pos)
        return scene_pos.x(), scene_pos.y()

    def _make_var_create_cb(self, kind: VariableNodeKind):  # type: ignore[no-untyped-def]
        """Return a callback that creates a variable node of the given kind."""
        from craftgraph.qt_variable_nodes import VARIABLE_NODE_REGISTRY

        def callback(graph: NodeGraph) -> None:
            cls = VARIABLE_NODE_REGISTRY[kind]
            type_name = f"com.craftgraph.{cls.__name__}"
            viewer = graph.viewer()
            spawn_x, spawn_y = self._menu_spawn_scene_pos(viewer)
            sx, sy = CraftGraphWindow._find_free_position(
                graph,
                spawn_x,
                spawn_y,
            )
            graph.clear_selection()
            node = graph.create_node(
                type_name,
                name=cls.NODE_NAME,
                pos=[sx, sy],
            )
            tab = self._active_tab
            if tab is not None:
                node.set_edit_history(tab.history)
            self._attach_node_completers(node)

            # Refresh dropdown for Get Fab / Get Tab nodes
            if hasattr(node, "refresh_fab_tab_choices"):
                from craftgraph.qt_variable_nodes import GetFabricatorNode, GetTabNode

                fab_choices, tab_choices = self._collect_fab_tab_choices()
                if isinstance(node, GetFabricatorNode):
                    node.refresh_fab_tab_choices(fab_choices)
                elif isinstance(node, GetTabNode):
                    node.refresh_fab_tab_choices(tab_choices)

        return callback

    def _on_promote_to_variable(
        self,
        graph: NodeGraph,
        node: CraftGraphBaseNode,
    ) -> None:
        """Promote a field on this node to a standalone variable node."""
        if getattr(node, "IS_VARIABLE", False):
            return

        from craftgraph.pin_registry import PinType
        from craftgraph.qt_variable_nodes import (
            VARIABLE_NODE_REGISTRY,
            pintype_to_variable_kind,
        )

        # Build list of promotable fields
        promotable: list[tuple[str, str, FieldPin]] = []
        for fp in node.FIELD_REGISTRY:
            if fp.pin_type == PinType.INGREDIENT_LIST:
                continue
            field_port = node.get_input(f"field_{fp.name}")
            if field_port is not None and field_port.connected_ports():
                continue  # Already connected
            promotable.append((fp.label or fp.name, fp.name, fp))

        if not promotable:
            self.statusBar().showMessage("No promotable fields available", 3000)
            return

        labels = [p[0] for p in promotable]
        chosen, ok = _pick_from_list(
            self,
            "Promote to Variable",
            "Select field:",
            labels,
        )
        if not ok:
            return

        idx = labels.index(chosen)
        label, field_name, fp = promotable[idx]

        var_kind = pintype_to_variable_kind(fp.pin_type, fp.preferred_var_kind)
        if var_kind is None:
            return

        cls = VARIABLE_NODE_REGISTRY.get(var_kind)
        if cls is None:
            return

        # Create variable node
        type_name = f"com.craftgraph.{cls.__name__}"
        var_node = graph.create_node(type_name, name=f"{label} Var")

        # Copy current value
        current_value = node.get_property(field_name)
        var_node.set_property("value", current_value)

        # Position one offset left of consumer
        from craftgraph.sync import _VAR_X_OFFSET

        nx, ny = node.pos()
        var_node.set_pos(nx - _VAR_X_OFFSET, ny)

        # Set edit history and attach completers
        tab = self._active_tab
        if tab is not None:
            var_node.set_edit_history(tab.history)
        self._attach_node_completers(var_node)

        # If enum, copy items
        if fp.pin_type == PinType.ENUM and fp.enum_items and hasattr(var_node, "set_enum_items"):
            var_node.set_enum_items(fp.enum_items)

        # Connect
        var_out = var_node.get_output("value_out")
        field_in = node.get_input(f"field_{field_name}")
        if var_out is not None and field_in is not None:
            var_out.connect_to(field_in)

        self.statusBar().showMessage(f"Promoted '{label}' to variable node", 3000)

    def _on_toggle_selection(self, graph: NodeGraph, node: CraftGraphBaseNode) -> None:
        """Toggle the selection state of the right-clicked node."""
        now_selected = not node.selected()
        node.set_selected(now_selected)
        # NodeGraphQt's set_selected() doesn't emit node_selected, so
        # fire it manually to trigger code editor scroll.
        if now_selected:
            graph.node_selected.emit(node)

    def _on_delete_ingredient(self, graph: NodeGraph, node: CraftGraphBaseNode) -> None:
        """Show a dialog to pick and delete an ingredient from this recipe."""
        model = node.model_ref
        if model is None:
            return
        ingredients = getattr(model, "ingredients", None)
        if not ingredients:
            self.statusBar().showMessage("No ingredients to delete")
            return

        # Build list labels: "ItemID x Required"
        labels = [f"{ing.item_id} x{ing.required}" for ing in ingredients]
        chosen, ok = _pick_from_list(
            self,
            "Delete Ingredient",
            "Select ingredient to remove:",
            labels,
        )
        if not ok:
            return
        idx = labels.index(chosen)
        ingredients.pop(idx)

        # Disconnect the corresponding ingredient port if connected
        ing_ports = [p for p in node.input_ports() if p.name().startswith("ingredient_")]
        if idx < len(ing_ports):
            port = ing_ports[idx]
            for connected in port.connected_ports():
                port.disconnect_from(connected)

        # Resync the code editor, child count labels, and title
        self._on_model_changed()

    def _on_promote_ingredient(self, graph: NodeGraph, node: CraftGraphBaseNode) -> None:
        """Promote an ingredient to a full recipe node.

        Shows two dialogs: first to pick the ingredient, then to pick the
        recipe type. Creates a new recipe node with the ingredient's ItemID
        pre-filled.
        """
        model = node.model_ref
        if model is None:
            return
        ingredients = getattr(model, "ingredients", None)
        if not ingredients:
            self.statusBar().showMessage("No ingredients to promote")
            return

        # Step 1: pick ingredient
        labels = [f"{ing.item_id} x{ing.required}" for ing in ingredients]
        chosen, ok = _pick_from_list(
            self,
            "Promote Ingredient to Recipe",
            "Select ingredient to promote:",
            labels,
        )
        if not ok:
            return
        idx = labels.index(chosen)
        item_id = ingredients[idx].item_id

        # Step 2: pick recipe type
        type_labels = [
            "Modified Recipe",
            "Added Recipe",
            "Alias Recipe",
            "Custom Food",
        ]
        type_chosen, ok = _pick_from_list(
            self,
            "Recipe Type",
            f"Create recipe type for '{item_id}':",
            type_labels,
        )
        if not ok:
            return

        kind_map = {
            "Modified Recipe": NodeKind.MODIFIED_RECIPE,
            "Added Recipe": NodeKind.ADDED_RECIPE,
            "Alias Recipe": NodeKind.ALIAS_RECIPE,
            "Custom Food": NodeKind.CUSTOM_FOOD,
        }
        kind = kind_map[type_chosen]
        self._create_node_from_menu(kind, item_id=item_id)

    def _create_orphan_ingredient(self) -> None:
        """Create an OrphanIngredientNode at the cursor position.

        Opens a searchable item-ID picker dialog.  The orphan node is
        visual-only (no model_ref) and has a muted grey style.
        """
        dialog = ItemIdPickerDialog(self._get_id_words(), parent=self)
        if dialog.exec_() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        item_id = dialog.selected_id
        if not item_id:
            return

        tab = self._active_tab
        type_ = f"{IDENTIFIER}.{OrphanIngredientNode.__name__}"
        viewer = tab.graph.viewer()
        spawn_x, spawn_y = self._menu_spawn_scene_pos(viewer)

        node = tab.graph.create_node(
            type_,
            name=item_id,
            pos=[spawn_x, spawn_y],
        )
        node.set_property("item_id", item_id)
        self.statusBar().showMessage(f"Created orphan ingredient: {item_id}")

    def _on_set_sprite(self, graph: NodeGraph, node: CraftGraphBaseNode) -> None:
        """Open a file dialog to pick a PNG sprite for the node."""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Sprite Image",
            "",
            "PNG Files (*.png)",
        )
        if not file_path:
            return
        path = Path(file_path)
        node.set_sprite(path)
        item_id = getattr(node.model_ref, "item_id", None)
        if not item_id:
            item_id = getattr(node.model_ref, "tab_id", None)
        if item_id:
            self._manual_sprites[item_id.lower()] = path

    def _on_clear_sprite(self, graph: NodeGraph, node: CraftGraphBaseNode) -> None:
        """Remove the sprite from a node and clear any manual override."""
        node.clear_sprite()
        item_id = getattr(node.model_ref, "item_id", None)
        if not item_id:
            item_id = getattr(node.model_ref, "tab_id", None)
        if item_id:
            self._manual_sprites.pop(item_id.lower(), None)

    def _make_create_callback(self, kind: NodeKind):  # type: ignore[no-untyped-def]
        """Return a callback(graph) that creates a node of the given kind."""

        def _callback(graph: NodeGraph) -> None:
            self._create_node_from_menu(kind)

        return _callback

    def _spawn_starter_node(self, block_type: BlockType) -> None:
        """Create a starter node at the canvas center for the given block type."""
        node_kind = _BLOCK_TYPE_TO_NODE_KIND.get(block_type)
        if node_kind is None:
            return
        self._create_node_from_menu(node_kind, item_id="NewItem")

    def _create_node_from_menu(
        self,
        kind: NodeKind,
        item_id: str | None = None,
    ) -> None:
        """Create a new node of the given kind at the cursor position.

        Also creates the corresponding model object and wires it into
        the active tab's parsed file so the code editor stays in sync.
        When *item_id* is given, the new node uses that ID instead of
        the default ``"NewItem"`` placeholder.
        """
        from craftgraph.models import (
            AddedRecipe,
            AliasRecipe,
            CraftingTab,
            CustomBioFuel,
            CustomFabricator,
            CustomFood,
            CustomFragmentCount,
            CustomSize,
            ModifiedRecipe,
            MovedRecipe,
        )

        tab = self._active_tab

        # Visual-only node types (not model-backed) get created directly
        if kind in (NodeKind.ORPHAN_INGREDIENT, NodeKind.SPRITE):
            node_cls = NODE_REGISTRY[kind]
            type_ = f"{IDENTIFIER}.{node_cls.__name__}"
            viewer = tab.graph.viewer()
            spawn_x, spawn_y = self._menu_spawn_scene_pos(viewer)
            sx, sy = self._find_free_position(
                tab.graph,
                spawn_x,
                spawn_y,
            )
            tab.graph.clear_selection()
            node = tab.graph.create_node(
                type_,
                name=item_id or node_cls.NODE_NAME,
                pos=[sx, sy],
            )
            if item_id and kind == NodeKind.ORPHAN_INGREDIENT:
                node.set_property("item_id", item_id)
            self._attach_node_completers(node)
            self.statusBar().showMessage(f"Created {node_cls.NODE_NAME}: {node.name()}")
            return

        kind_to_model: dict[NodeKind, tuple[type, BlockType, str]] = {
            NodeKind.MODIFIED_RECIPE: (
                ModifiedRecipe,
                BlockType.MODIFIED_RECIPES,
                "modified_recipes",
            ),
            NodeKind.ADDED_RECIPE: (
                AddedRecipe,
                BlockType.ADDED_RECIPES,
                "added_recipes",
            ),
            NodeKind.ALIAS_RECIPE: (
                AliasRecipe,
                BlockType.ALIAS_RECIPES,
                "alias_recipes",
            ),
            NodeKind.CUSTOM_FOOD: (
                CustomFood,
                BlockType.CUSTOM_FOODS,
                "custom_foods",
            ),
            NodeKind.FABRICATOR: (
                CustomFabricator,
                BlockType.CUSTOM_FABRICATORS,
                "custom_fabricators",
            ),
            NodeKind.CRAFTING_TAB: (
                CraftingTab,
                BlockType.CUSTOM_CRAFTING_TABS,
                "crafting_tabs",
            ),
            NodeKind.CUSTOM_SIZE: (
                CustomSize,
                BlockType.CUSTOM_SIZES,
                "custom_sizes",
            ),
            NodeKind.MOVED_RECIPE: (
                MovedRecipe,
                BlockType.MOVED_RECIPES,
                "moved_recipes",
            ),
            NodeKind.CUSTOM_BIO_FUEL: (
                CustomBioFuel,
                BlockType.CUSTOM_BIO_FUELS,
                "custom_bio_fuels",
            ),
            NodeKind.CUSTOM_FRAGMENT_COUNT: (
                CustomFragmentCount,
                BlockType.CUSTOM_FRAGMENT_COUNTS,
                "custom_fragment_counts",
            ),
        }

        model_cls, block_type, attr_name = kind_to_model[kind]

        # Block types that can nest inside a CustomFabricator entry.
        # Maps BlockType -> attribute name on the CustomFabricator model.
        fab_nestable: dict[BlockType, str] = {
            BlockType.CUSTOM_CRAFTING_TABS: "tabs",
            BlockType.ADDED_RECIPES: "added_recipes",
            BlockType.ALIAS_RECIPES: "alias_recipes",
            BlockType.MOVED_RECIPES: "moved_recipes",
            BlockType.CUSTOM_FOODS: "custom_foods",
        }

        # Determine whether this node should nest inside a fabricator
        nest_in_fab = False
        if tab.parsed_file is not None and tab.parsed_file.block_type is not None:
            existing_bt = tab.parsed_file.block_type
            if existing_bt != block_type:
                # CustomFabricators files allow nestable block types
                if existing_bt == BlockType.CUSTOM_FABRICATORS and block_type in fab_nestable:
                    nest_in_fab = True
                else:
                    existing_attr = {
                        BlockType.MODIFIED_RECIPES: "modified_recipes",
                        BlockType.ADDED_RECIPES: "added_recipes",
                        BlockType.ALIAS_RECIPES: "alias_recipes",
                        BlockType.CUSTOM_FOODS: "custom_foods",
                        BlockType.CUSTOM_CRAFTING_TABS: "crafting_tabs",
                        BlockType.CUSTOM_FABRICATORS: "custom_fabricators",
                        BlockType.MOVED_RECIPES: "moved_recipes",
                        BlockType.CUSTOM_SIZES: "custom_sizes",
                        BlockType.CUSTOM_BIO_FUELS: "custom_bio_fuels",
                        BlockType.CUSTOM_FRAGMENT_COUNTS: "custom_fragment_counts",
                    }[existing_bt]
                    if getattr(tab.parsed_file, existing_attr):
                        self._show_error_status(
                            f"Cannot add {block_type.value} to a "
                            f"{existing_bt.value} file -- CC3 requires "
                            f"one block type per file"
                        )
                        return
                    # Primary list is empty; safe to switch block type
                    tab.parsed_file.block_type = block_type

        if model_cls is CraftingTab:
            model = model_cls(tab_id=item_id or "NewTab")
        elif model_cls is CustomFabricator:
            model = model_cls(
                item_id=item_id or "NewFabricator",
                display_name=item_id or "New Fabricator",
            )
        else:
            model = model_cls(item_id=item_id or "NewItem")

        # Add to the active tab's parsed file
        if tab.parsed_file is None:
            tab.parsed_file = ParsedFile(
                source_path=self._source_path,
                block_type=block_type,
            )
        pf: ParsedFile = tab.parsed_file  # type: ignore[assignment]

        if nest_in_fab:
            # Append to the first fabricator's nested list
            fabs = pf.custom_fabricators
            if not fabs:
                self._show_error_status("No fabricator to nest into -- add a Fabricator first")
                return
            target_fab = fabs[0]
            fab_attr = fab_nestable[block_type]
            getattr(target_fab, fab_attr).append(model)
        else:
            getattr(pf, attr_name).append(model)

        viewer = tab.graph.viewer()
        spawn_x, spawn_y = self._menu_spawn_scene_pos(viewer)
        sx, sy = self._find_free_position(
            tab.graph,
            spawn_x,
            spawn_y,
        )

        node_cls = NODE_REGISTRY[kind]
        type_ = f"{IDENTIFIER}.{node_cls.__name__}"
        tab.graph.clear_selection()
        node = tab.graph.create_node(
            type_,
            name=getattr(model, "item_id", None) or getattr(model, "tab_id", "Node"),
            pos=[sx, sy],
        )

        if hasattr(model, "item_id"):
            node.set_property("item_id", model.item_id)
        if hasattr(model, "tab_id"):
            node.set_property("tab_id", model.tab_id)
        if hasattr(model, "display_name") and model.display_name:
            node.set_property("display_name", model.display_name)

        node.model_ref = model
        tab.model_to_node[id(model)] = node
        self._attach_node_completers(node)

        if tab.ui_handler is not None:
            tab.ui_handler.register_node(node)

        self._update_code_editor_from_model()
        self._update_path_completions()

        self.statusBar().showMessage(f"Created {node_cls.NODE_NAME}: {node.name()}")

    # -- Autocomplete ---------------------------------------------------------

    # Widget names that should complete against TechType IDs.
    _ID_WIDGET_NAMES: frozenset[str] = frozenset(
        {
            "item_id",
            "tab_id",
        }
    )
    # Widget names that should complete against crafting-tree paths.
    _PATH_WIDGET_NAMES: frozenset[str] = frozenset(
        {
            "path",
            "old_path",
            "new_path",
        }
    )

    def _get_id_words(self) -> list[str]:
        """Return the cached, sorted list of TechType IDs per settings."""
        if self._id_words is None:
            from craftgraph.vanilla_ids import load_mod_compat_ids, load_vanilla_ids

            ids: set[str] = set()
            if self._ac_settings.include_vanilla_ids:
                ids |= load_vanilla_ids()
            if self._ac_settings.include_mod_compat_ids:
                ids |= load_mod_compat_ids()
            # include_project_ids: placeholder for future project-extracted IDs
            effective = self._effective_custom_ids()
            if effective:
                ids |= set(effective)
            self._id_words = sorted(ids, key=str.lower)
        return self._id_words

    def _make_completer(
        self,
        words: list[str],
        parent: QtCore.QObject | None = None,
        *,
        keywords: list[str] | None = None,
    ) -> QtWidgets.QCompleter:
        """Build a substring-matching QCompleter using current settings.

        When *keywords* is supplied the popup uses a custom delegate that
        paints a distinct background tint for keyword entries vs ID entries
        and labels each row "keyword" / "id" on the right so users can tell
        at a glance which category a suggestion belongs to.  Keywords are
        listed first so they cluster at the top of unfiltered popups.
        """
        if keywords:
            combined = sorted(keywords) + sorted(words)
            completer = QtWidgets.QCompleter(combined, parent or self)
            popup = completer.popup()
            popup.setItemDelegate(_GroupedCompleterDelegate(set(keywords), popup))
        else:
            completer = QtWidgets.QCompleter(words, parent or self)
        sensitivity = (
            QtCore.Qt.CaseSensitivity.CaseInsensitive
            if self._ac_settings.case_insensitive
            else QtCore.Qt.CaseSensitivity.CaseSensitive
        )
        completer.setCaseSensitivity(sensitivity)
        completer.setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
        completer.setMaxVisibleItems(self._ac_settings.max_visible_items)
        return completer

    def _setup_autocomplete_for(self, editor: CodeEditor) -> None:
        """Attach a QCompleter to the given code editor.

        Combines EasyMarkup language keywords (block types + field keys)
        with the active TechType ID set so a single popup serves both.
        Path completions are populated separately after recipe files load.
        """
        editor.set_completer(
            self._make_completer(
                self._get_id_words(),
                keywords=_easymarkup_keywords(),
            ),
        )

    def _attach_node_completers(self, node: CraftGraphBaseNode) -> None:
        """Wire the shared NodeCompletionPopup to text input widgets on *node*.

        ItemID / TabID fields get TechType ID completion.
        Path fields get crafting-tree path completion.
        Other text fields (display_name, tooltip, file_path) are left alone.

        Uses a standalone popup widget (NodeCompletionPopup) instead of
        QCompleter because node widgets live inside QGraphicsProxyWidget
        where QCompleter's popup has focus issues.
        """
        for name, widget in node.widgets().items():
            if widget.type_ != "LineEditNodeWidget":
                continue
            line_edit: QtWidgets.QLineEdit = widget.get_custom_widget()
            if name in self._ID_WIDGET_NAMES:
                self._node_popup.attach(line_edit, self._get_id_words())
            elif name in self._PATH_WIDGET_NAMES:
                self._node_popup.attach(line_edit, self._path_words)

    def _attach_completers_bulk(self, model_to_node: dict[int, CraftGraphBaseNode]) -> None:
        """Attach completers to all nodes in a model_to_node map (bulk load)."""
        for node in model_to_node.values():
            if isinstance(node, CraftGraphBaseNode):
                self._attach_node_completers(node)

    def _update_path_completions(self) -> None:
        """Extract all known paths from parsed files and update editors + nodes."""
        paths: set[str] = set(SN1_CRAFT_TREE_PATH_ROOTS)

        def _add_path(p: str) -> None:
            if not p:
                return
            paths.add(p)
            parts = p.split("/")
            for i in range(1, len(parts)):
                paths.add("/".join(parts[:i]))

        for file_tab in self._file_tabs:
            if file_tab.parsed_file is None:
                continue
            pf: ParsedFile = file_tab.parsed_file  # type: ignore[assignment]
            for r in pf.all_recipes:
                if hasattr(r, "path"):
                    _add_path(r.path)
            for ctab in pf.crafting_tabs:
                _add_path(ctab.parent_tab_path)
            for mr in pf.moved_recipes:
                _add_path(mr.old_path or "")
                _add_path(mr.new_path or "")
            for fab in pf.custom_fabricators:
                paths.add(fab.item_id)
                for ctab in fab.tabs:
                    _add_path(ctab.parent_tab_path)
                for r in fab.added_recipes + fab.alias_recipes + fab.custom_foods:
                    if hasattr(r, "path"):
                        _add_path(r.path)

        sorted_paths = sorted(paths, key=str.lower)
        self._path_words = sorted_paths

        for file_tab in self._file_tabs:
            file_tab.editor.set_path_completions(sorted_paths)
            # Refresh path completions on existing nodes
            for node in file_tab.model_to_node.values():
                if not isinstance(node, CraftGraphBaseNode):
                    continue
                for name, widget in node.widgets().items():
                    if name not in self._PATH_WIDGET_NAMES:
                        continue
                    if widget.type_ != "LineEditNodeWidget":
                        continue
                    line_edit: QtWidgets.QLineEdit = widget.get_custom_widget()
                    self._node_popup.update_words(line_edit, sorted_paths)

        self._validate_path_references()

    _INVALID_PATH_STYLE = "border: 1px solid rgb(200, 120, 40);"
    _VALID_PATH_STYLE = ""

    # Built-in crafting station roots that are always valid path targets.
    _BUILTIN_PATH_ROOTS: frozenset[str] = SN1_CRAFT_TREE_PATH_ROOTS

    def _collect_valid_path_targets(self) -> set[str]:
        """Build the set of valid path targets from fabricator/tab definitions.

        Unlike ``_path_words`` (which includes paths used by recipes for
        autocomplete), this set only contains paths that are *defined* by
        fabricators and crafting tabs -- i.e. valid destinations.
        """
        targets: set[str] = set(self._BUILTIN_PATH_ROOTS)
        for file_tab in self._file_tabs:
            if file_tab.parsed_file is None:
                continue
            pf: ParsedFile = file_tab.parsed_file  # type: ignore[assignment]
            for fab in pf.custom_fabricators:
                targets.add(fab.item_id)
                for ctab in fab.tabs:
                    if ctab.parent_tab_path:
                        targets.add(ctab.parent_tab_path)
                        targets.add(f"{ctab.parent_tab_path}/{ctab.tab_id}")
                    else:
                        targets.add(f"{fab.item_id}/{ctab.tab_id}")
            for ctab in pf.crafting_tabs:
                if ctab.parent_tab_path:
                    targets.add(ctab.parent_tab_path)
                    targets.add(f"{ctab.parent_tab_path}/{ctab.tab_id}")
        # Also add all prefix segments so "Fabricator/Resources" matches
        # when "Fabricator" is a known root.
        expanded: set[str] = set()
        for t in targets:
            parts = t.split("/")
            for i in range(1, len(parts) + 1):
                expanded.add("/".join(parts[:i]))
        targets |= expanded
        return targets

    def _validate_path_references(self) -> None:
        """Mark path fields orange when their value does not match any defined target."""
        valid = self._collect_valid_path_targets()
        for file_tab in self._file_tabs:
            for node in file_tab.graph.all_nodes():
                if not isinstance(node, CraftGraphBaseNode):
                    continue
                for name in self._PATH_WIDGET_NAMES:
                    widget_item = node.get_widget(name)
                    if widget_item is None:
                        continue
                    qt_widget = widget_item.get_custom_widget()
                    if qt_widget is None:
                        continue
                    value = node.get_property(name)
                    if not value or not isinstance(value, str) or not value.strip():
                        continue
                    if value.strip() in valid:
                        qt_widget.setStyleSheet(self._VALID_PATH_STYLE)
                    else:
                        qt_widget.setStyleSheet(self._INVALID_PATH_STYLE)

    # -- Fab/Tab reference node refresh ---------------------------------------

    def _collect_fab_tab_choices(self) -> tuple[list[str], list[str]]:
        """Collect fabricator and tab choices from all open file tabs."""
        parsed_files = [tab.parsed_file for tab in self._file_tabs if tab.parsed_file is not None]
        return collect_fab_tab_choices(parsed_files)

    def _refresh_all_ref_nodes(self) -> None:
        """Refresh dropdown choices on all Get Fab / Get Tab nodes across all tabs."""
        from craftgraph.qt_variable_nodes import GetFabricatorNode, GetTabNode

        fab_choices, tab_choices = self._collect_fab_tab_choices()
        for file_tab in self._file_tabs:
            for node in file_tab.graph.all_nodes():
                if isinstance(node, GetFabricatorNode):
                    node.refresh_fab_tab_choices(fab_choices)
                elif isinstance(node, GetTabNode):
                    node.refresh_fab_tab_choices(tab_choices)

    # -- Sprite auto-assign ---------------------------------------------------

    def _apply_sprites_for(self, tab: FileTab) -> None:
        """Set sprites on all nodes in a tab that have a matching Assets/ PNG."""
        for node in tab.model_to_node.values():
            if not isinstance(node, CraftGraphBaseNode):
                continue
            item_id = getattr(node.model_ref, "item_id", None)
            if not item_id:
                item_id = getattr(node.model_ref, "tab_id", None)
            if not item_id:
                continue
            sprite_path = resolve_sprite(
                item_id,
                self._manual_sprites,
                self._sprite_lookup,
            )
            if sprite_path is not None:
                node.set_sprite(sprite_path)

    # -- Recipe loading -------------------------------------------------------

    def _tear_down_tabs(self) -> None:
        """Disconnect, destroy, and remove all existing file tabs."""
        if hasattr(self, "_minimap") and self._minimap is not None:
            self._minimap.detach()

        for tab in self._file_tabs:
            if tab.ui_handler is not None:
                tab.ui_handler.disconnect()
            if tab.parse_timer is not None:
                tab.parse_timer.stop()
                tab.parse_timer.deleteLater()
                tab.parse_timer = None

            tab.model_to_node.clear()
            tab.orphan_nodes.clear()
            tab.user_positions.clear()

        self._tab_bar.blockSignals(True)
        while self._tab_bar.count():
            self._tab_bar.removeTab(0)
        self._tab_bar.blockSignals(False)

        while self._graph_stack.count():
            w = self._graph_stack.widget(0)
            self._graph_stack.removeWidget(w)
            w.setParent(None)
            w.deleteLater()

        while self._editor_stack.count():
            w = self._editor_stack.widget(0)
            self._editor_stack.removeWidget(w)
            w.setParent(None)
            w.deleteLater()

        self._file_tabs.clear()

    @staticmethod
    def _apply_node_header_tooltip(node: object) -> None:
        """Patch a node's view so hovering it shows full recipe details.

        NodeGraphQt's ``_draw_node_horizontal`` calls ``_tooltip_disable``
        on every redraw, overwriting any tooltip set via ``setToolTip``.
        We monkey-patch ``_tooltip_disable`` on the view instance so the
        rich tooltip gets recomposed (and stays consistent) across redraws.
        """
        if not isinstance(node, CraftGraphBaseNode):
            return
        type_name = type(node).NODE_NAME
        type_desc = NODE_DESCRIPTIONS.get(type_name) or VARIABLE_DESCRIPTIONS.get(type_name)

        def _compose() -> str:
            try:
                fallback_id = None
                if node.model_ref is None:
                    fallback_id = node.get_property("item_id") or node.get_property("tab_id")
                return format_node_details_tooltip(
                    type_name=type_name,
                    type_desc=type_desc,
                    model=node.model_ref,
                    fallback_id=fallback_id if isinstance(fallback_id, str) else None,
                    source_file=node._source_file_name or None,
                    issues=list(node._issue_messages),
                    cycle_paths=list(node._cycle_paths),
                )
            except Exception:  # noqa: BLE001
                # Tooltip composition must never break a redraw.
                return f"<b>{type_name}</b>"

        def _patched_tooltip_disable(self: object, state: bool) -> None:
            tooltip = _compose()
            if state:
                tooltip += '<br><font color="red"><b>(DISABLED)</b></font>'
            self.setToolTip(tooltip)  # type: ignore[attr-defined]

        node.view._tooltip_disable = types.MethodType(  # type: ignore[attr-defined]
            _patched_tooltip_disable,
            node.view,
        )
        # Set an initial tooltip so it shows up before the first redraw.
        node.view.setToolTip(_compose())

    def _stamp_source_file(self, model_to_node: dict[int, object], source_name: str) -> None:
        """Tag every node in *model_to_node* with the originating file name."""
        for node in model_to_node.values():
            if isinstance(node, CraftGraphBaseNode):
                node._source_file_name = source_name

    @staticmethod
    @contextlib.contextmanager
    def _suspend_graph_updates(graph: NodeGraph) -> "Iterator[None]":
        """Suppress NodeGraphQt redraws and scene re-indexing during bulk load.

        Each ``setWidget()``, port-add, and property-change normally triggers
        a node redraw + scene reindex.  With hundreds of nodes that adds
        seconds of UI churn before anything is visible.  This wraps the
        bulk-load region: disable view updates, switch the scene to NoIndex,
        run the build, then restore both and trigger one final repaint.
        """
        viewer = graph.viewer()
        scene = viewer.scene()
        prev_index_method = scene.itemIndexMethod()
        scene.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.NoIndex)
        viewer.setUpdatesEnabled(False)
        try:
            yield
        finally:
            viewer.setUpdatesEnabled(True)
            scene.setItemIndexMethod(prev_index_method)
            viewer.update()

    def _create_file_tab(
        self,
        parsed_file: object,
        saved_positions: dict[str, tuple[float, float]] | None = None,
    ) -> FileTab:
        """Build a complete FileTab for one ParsedFile.

        Args:
            parsed_file: The parsed recipe data.
            saved_positions: Optional user positions loaded from disk.
                When provided, these override the computed hierarchy layout.
        """
        from craftgraph.commands import EditHistory

        graph = NodeGraph()
        graph.set_acyclic(False)
        for cls in all_node_classes():
            graph.register_node(cls)
        from craftgraph.qt_variable_nodes import all_variable_node_classes

        for cls in all_variable_node_classes():
            graph.register_node(cls)
        self._setup_context_menus_for(graph)
        self._install_viewer_patches(graph)
        graph.node_created.connect(self._apply_node_header_tooltip)

        guard = SyncGuard()
        history = EditHistory(on_change=self._on_model_changed)

        initial_user_positions = dict(saved_positions) if saved_positions else {}

        with guard(), self._suspend_graph_updates(graph):
            model_to_node = populate_graph(graph, [parsed_file], edit_history=history)
            connect_hierarchy(graph, [parsed_file], model_to_node)
            conn_result = connect_ingredients(graph, [parsed_file], model_to_node)
            orphan_nodes = conn_result.orphan_nodes
            positions = compute_hierarchy_layout([parsed_file], model_to_node)
            overlay_user_positions(positions, initial_user_positions, model_to_node)
            apply_layout(positions, model_to_node)
            place_orphan_nodes(graph)
            cycle_count = highlight_cycle_edges(graph, [parsed_file], model_to_node)
            update_node_issue_overlays(
                graph,
                [parsed_file],
                model_to_node,
                frozenset(i.lower() for i in self._get_id_words()),
            )
            self._stamp_source_file(model_to_node, parsed_file.source_path.name)
            update_child_count_labels(model_to_node)
            # NodeGraphQt defaults create_node(selected=True); clear to
            # avoid accidental bulk deletion of newly-loaded nodes.
            graph.clear_selection()

        self._attach_completers_bulk(model_to_node)

        editor = CodeEditor()
        EasyMarkupHighlighter(editor.document())
        self._setup_autocomplete_for(editor)
        self._apply_code_editor_settings_to(editor, self._ce_settings)
        self._apply_autocomplete_settings_to(editor, self._ac_settings)

        # Per-tab debounce timer
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(
            self._ce_settings.parse_debounce_ms
            if self._ce_settings.parse_debounce_enabled
            else 0,
        )

        tab = FileTab(
            parsed_file=parsed_file,
            graph=graph,
            editor=editor,
            history=history,
            ui_handler=None,
            sync_guard=guard,
            model_to_node=model_to_node,
            orphan_nodes=orphan_nodes,
            parse_timer=timer,
            cycle_count=cycle_count,
            user_positions=initial_user_positions,
        )

        # Wire code editor -> model re-parse for this tab
        def on_text_changed(_tab: FileTab = tab) -> None:
            if _tab.sync_guard.active:
                return
            if _tab.parse_timer is not None:
                _tab.parse_timer.start()

        def apply_text(_tab: FileTab = tab) -> None:
            self._apply_code_editor_text_for(_tab)

        editor.textChanged.connect(on_text_changed)
        timer.timeout.connect(apply_text)

        # Serialize model into editor
        with guard():
            editor.setPlainText(serialize_file(parsed_file))

        # Wire node selection -> code editor scroll + z-order raise
        _Z_SELECTED = 10.0
        _Z_DEFAULT = 0.0

        def on_node_selected(node: object, _tab: FileTab = tab) -> None:
            self._scroll_editor_to_node(node, _tab)
            # Raise selected node above siblings so combo dropdowns
            # don't get occluded by neighbouring nodes.
            view = getattr(node, "view", None)
            if view is not None:
                # Reset all other nodes to default z
                for other in _tab.graph.all_nodes():
                    other_view = getattr(other, "view", None)
                    if other_view is not None and other_view is not view:
                        other_view.setZValue(_Z_DEFAULT)
                view.setZValue(_Z_SELECTED)

        graph.node_selected.connect(on_node_selected)

        # Wire multi-line code-editor selection -> multi-node graph selection.
        # When the user highlights several lines of code that reference IDs
        # (e.g. an entire recipe block, or a slice spanning two recipes),
        # mirror that into the graph by selecting every referenced node.
        def on_editor_selection_changed(_tab: FileTab = tab) -> None:
            self._on_editor_selection_changed(_tab)

        editor.selectionChanged.connect(on_editor_selection_changed)

        # Wire node drag -> snap-to-grid + save user positions
        def on_nodes_moved(moved: dict, _tab: FileTab = tab) -> None:
            # Snap first so recorded positions are already on-grid
            self._snap_moved_nodes(_tab.graph, moved)

            for node_item in moved:
                node = _tab.graph.get_node_by_id(node_item.id)
                if node is None:
                    continue
                # Variable nodes use UUID-based keys
                if hasattr(node, "_var_uuid"):
                    key = f"VarNode:{node._var_uuid}"
                # Orphan/sprite nodes use _node_uuid keys
                elif hasattr(node, "_node_uuid"):
                    key = f"{node.NODE_NAME}:{node._node_uuid}"
                elif hasattr(node, "model_ref") and node.model_ref is not None:
                    key = model_position_key(node.model_ref)
                else:
                    continue
                x, y = node.pos()
                _tab.user_positions[key] = (x, y)

        graph.viewer().moved_nodes.connect(on_nodes_moved)

        # Wire UI handler
        tab.ui_handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[parsed_file],
            model_to_node=model_to_node,
            on_cycle_rejected=self._on_cycle_rejected,
            on_reassignment_warning=self._on_reassignment_warning,
        )
        tab.ui_handler.warn_before_cycles = self._ne_settings.warn_before_cycles

        return tab

    def load_recipes(self, path: Path) -> None:
        """Parse recipes from *path* and populate per-file tabs."""
        from craftgraph.parser import MappingError, ParseError, parse_directory, parse_file

        self.statusBar().showMessage(f"Parsing {path}...")

        try:
            parsed_files = [parse_file(path)] if path.is_file() else parse_directory(path)
        except (ParseError, MappingError, FileNotFoundError, NotADirectoryError) as exc:
            self.statusBar().showMessage(f"Parse error: {exc}")
            return

        if not parsed_files:
            self.statusBar().showMessage("No recipe files found.")
            return

        self._tear_down_tabs()
        self._source_path = path

        # Scan for sprite assets -- CC3 Assets/ is the primary source
        if self._subnautica_cc3_path:
            self._sprite_lookup = scan_assets_dir(Path(self._subnautica_cc3_path))
        else:
            recipe_dir = path.parent if path.is_file() else path
            self._sprite_lookup = scan_assets_dir(recipe_dir)

        # Load persisted node positions from sidecar file
        layout_file = layout_path_for(path)
        disk_positions = load_layout(layout_file) or {}

        # Create one FileTab per parsed file. Pump the event loop between
        # tabs so the UI does not appear frozen during a multi-file load
        # (each tab queues thousands of Qt events that would otherwise pile
        # up and drain in one big stutter at the end).
        total_files = len(parsed_files)
        for idx, pf in enumerate(parsed_files, start=1):
            tab_key = pf.source_path.stem
            tab_saved = disk_positions.get(tab_key, {})
            saved_pos = {k: (v[0], v[1]) for k, v in tab_saved.items()}
            self.statusBar().showMessage(
                f"Loading {pf.source_path.name} ({idx}/{total_files})..."
            )
            tab = self._create_file_tab(pf, saved_positions=saved_pos)
            self._file_tabs.append(tab)

            self._graph_stack.addWidget(tab.graph.widget)
            self._editor_stack.addWidget(tab.editor)
            self._tab_bar.addTab(pf.source_path.stem)
            self._tab_bar.setTabToolTip(
                self._tab_bar.count() - 1,
                str(pf.source_path),
            )
            QtWidgets.QApplication.processEvents(
                QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents,
                50,
            )

        # Apply sprites across all tabs
        for tab in self._file_tabs:
            self._apply_sprites_for(tab)

        self._update_path_completions()
        self._refresh_all_ref_nodes()

        # Apply persisted node editor settings (pipe style, port labels, etc.)
        self._apply_node_editor_settings(self._ne_settings)

        # Activate first tab
        self._tab_bar.setCurrentIndex(0)
        self._on_tab_changed(0)

        total_nodes = sum(len(t.model_to_node) for t in self._file_tabs)
        total_cycles = sum(t.cycle_count for t in self._file_tabs)
        cycle_msg = f", {total_cycles} cycle(s)!" if total_cycles else ", no cycles"
        self.statusBar().showMessage(
            f"Loaded {total_nodes} nodes from {len(parsed_files)} file(s){cycle_msg}"
        )

        # (Re)start file watcher if enabled
        self._stop_file_watcher()
        if self._fw_settings.enabled:
            self._start_file_watcher()


# ---------------------------------------------------------------------------
# Launch helper
# ---------------------------------------------------------------------------


def _install_message_filter() -> None:
    """Suppress known harmless Qt warnings.

    ``QGraphicsScene::sendEvent`` fires when Qt's hover-event delivery
    loop encounters items that were removed mid-iteration (e.g. node
    deletion during mouse tracking).  The event is silently dropped by
    Qt -- the warning is purely diagnostic console noise.
    """

    def _handler(
        mode: QtCore.QtMsgType,
        context: QtCore.QMessageLogContext,
        message: str,
    ) -> None:
        if "QGraphicsScene::sendEvent" in message:
            return
        # Forward everything else to stderr (default Qt behaviour)
        sys.stderr.write(message + "\n")

    QtCore.qInstallMessageHandler(_handler)


def launch_qt_gui(recipe_path: Path | None = None) -> None:
    """Create the QApplication and show the CraftGraph main window.

    Called by the ``craftgraph gui`` CLI command.
    """
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    # Set application icon (taskbar, title bar, ALT+TAB).
    icon_path = app_dirs.bundled_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QtGui.QIcon(str(icon_path)))

    _install_message_filter()

    def _hwnd_threshold_warning(action: str, delta: int) -> None:
        # Surface a non-blocking warning on the active window's status bar.
        active = QtWidgets.QApplication.activeWindow()
        if isinstance(active, QtWidgets.QMainWindow):
            active.statusBar().showMessage(
                f"HWND spike: {action} +{delta} handles", 5000,
            )

    hwnd_diag.install_logger(threshold=20, on_threshold_exceeded=_hwnd_threshold_warning)

    window = CraftGraphWindow()

    if recipe_path is not None:
        if recipe_path.suffix == ".craftgraph":
            window.open_project_file(recipe_path)
        else:
            window.load_recipes(recipe_path)
        window._show_editor()

    window.show()
    app.exec()
