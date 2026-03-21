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

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from NodeGraphQt import NodeGraph
from PySide6 import QtCore, QtGui, QtWidgets

from craftgraph.code_editor import CodeEditor
from craftgraph.highlighter import EasyMarkupHighlighter
from craftgraph.layout_store import layout_path_for, load_layout, save_layout
from craftgraph.minimap import MinimapWidget
from craftgraph.models import BlockType, ParsedFile
from craftgraph.qt_nodes import (
    IDENTIFIER,
    NODE_REGISTRY,
    CraftGraphBaseNode,
    ModifiedRecipeNode,
    NodeKind,
    OrphanIngredientNode,
    all_node_classes,
)
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
    place_variable_nodes,
    populate_graph,
    update_child_count_labels,
)
from craftgraph.tooltips import (
    NODE_DESCRIPTIONS,
    OPERATION_DESCRIPTIONS,
    VARIABLE_DESCRIPTIONS,
    enable_menu_tooltips,
)

if TYPE_CHECKING:
    from craftgraph.pin_registry import FieldPin
    from craftgraph.qt_variable_nodes import VariableNodeKind

_DIALOG_FLAGS = QtCore.Qt.WindowType.Popup

_DIALOG_STYLE = (
    "QDialog {"
    "  background: rgb(40, 40, 40);"
    "  border: 1px solid rgb(100, 100, 100);"
    "  border-radius: 4px;"
    "}"
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
_POPUP_STYLE = (
    "QListWidget {"
    "  background: rgb(30, 30, 30);"
    "  color: rgb(200, 200, 200);"
    "  border: 1px solid rgb(80, 80, 80);"
    "  font-size: 11pt;"
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
        self.setMinimumSize(340, 420)

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
        self._count_label.setStyleSheet("color: gray; font-size: 11px;")

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

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent, _DIALOG_FLAGS)
        self.setStyleSheet(_DIALOG_STYLE)
        self.setMinimumWidth(420)

        # Project name
        self._name_edit = QtWidgets.QLineEdit(self)
        self._name_edit.setPlaceholderText("e.g. MySubnauticaMod")

        # Parent directory
        dir_row = QtWidgets.QHBoxLayout()
        self._dir_edit = QtWidgets.QLineEdit(self)
        self._dir_edit.setText(str(Path.cwd()))
        browse_btn = QtWidgets.QPushButton("Browse...", self)
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(self._dir_edit)
        dir_row.addWidget(browse_btn)

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

        form = QtWidgets.QFormLayout(self)
        form.addRow("Project Name:", self._name_edit)
        form.addRow("Location:", dir_row)
        form.addRow(types_group)
        form.addRow(buttons)
        self.move(QtGui.QCursor.pos())

    @property
    def project_path(self) -> Path:
        return Path(self._dir_edit.text().strip()) / self._name_edit.text().strip()

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
        self._list.setStyleSheet(_POPUP_STYLE)
        self._list.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self._list.itemClicked.connect(self._on_item_clicked)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._list)

        self._active_edit: QtWidgets.QLineEdit | None = None
        self._all_words: list[str] = []
        self.hide()

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
        try:
            line_edit.textEdited.disconnect()
        except RuntimeError:
            pass
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

        prefix = text.lower()
        matches = [w for w in words if prefix in w.lower()]

        # Hide if nothing matches or if text is an exact match
        if not matches or (len(matches) == 1 and matches[0].lower() == prefix):
            self.hide()
            return

        self._list.clear()
        for m in matches[:_POPUP_MAX_VISIBLE]:
            self._list.addItem(m)
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
        visible = min(self._list.count(), _POPUP_MAX_VISIBLE)
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

    def _accept_current(self) -> None:
        item = self._list.currentItem()
        if item is not None and self._active_edit is not None:
            self._active_edit.setText(item.text())
        self.hide()

    def _on_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        if self._active_edit is not None:
            self._active_edit.setText(item.text())
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
    parse_timer: QtCore.QTimer | None = None
    user_positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    cycle_count: int = 0


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class CraftGraphWindow(QtWidgets.QMainWindow):
    """Main application window for the Qt-based CraftGraph editor."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("CraftGraph")
        self.resize(1400, 900)

        # -- Per-file tabs ------------------------------------------------
        self._file_tabs: list[FileTab] = []
        self._source_path = Path("untitled.txt")
        self._sprite_lookup: dict[str, Path] = {}
        self._manual_sprites: dict[str, Path] = {}
        self._id_words: list[str] | None = None
        self._path_words: list[str] = []
        self._node_popup = NodeCompletionPopup(self)

        # -- Build UI ---------------------------------------------------------
        self._setup_menu_bar()
        self._setup_central_widget()
        self._setup_status_bar()

        # Force combo box dropdowns to be fully opaque so underlying
        # scene content does not bleed through the popup list.
        self.setStyleSheet(
            "QComboBox QAbstractItemView {"
            "  background: rgb(30, 30, 30);"
            "  color: rgb(200, 200, 200);"
            "  selection-background-color: rgb(60, 80, 120);"
            "  border: 1px solid rgb(80, 80, 80);"
            "}"
        )

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

        new_file_action = QtGui.QAction("&New File...", self)
        new_file_action.setShortcut(QtGui.QKeySequence.StandardKey.New)
        new_file_action.triggered.connect(self._on_new_file)
        file_menu.addAction(new_file_action)

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

        self._save_action = QtGui.QAction("&Save", self)
        self._save_action.setShortcut(QtGui.QKeySequence.StandardKey.Save)
        self._save_action.triggered.connect(self._on_save)
        file_menu.addAction(self._save_action)

        save_all_action = QtGui.QAction("Save &All", self)
        save_all_action.triggered.connect(self._on_save_all)
        file_menu.addAction(save_all_action)

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

        undo_action = QtGui.QAction("&Undo", self)
        undo_action.triggered.connect(self._on_undo)
        edit_menu.addAction(undo_action)

        redo_action = QtGui.QAction("&Redo", self)
        redo_action.triggered.connect(self._on_redo)
        edit_menu.addAction(redo_action)

        # View menu
        view_menu = menu_bar.addMenu("&View")

        self._minimap_action = QtGui.QAction("&Minimap", self)
        self._minimap_action.setCheckable(True)
        self._minimap_action.setChecked(True)
        self._minimap_action.triggered.connect(self._on_toggle_minimap)
        view_menu.addAction(self._minimap_action)

        self._reset_layout_action = QtGui.QAction("&Reset Layout", self)
        self._reset_layout_action.triggered.connect(self._on_reset_layout)
        view_menu.addAction(self._reset_layout_action)

        # Help menu
        help_menu = menu_bar.addMenu("&Help")

        settings_action = QtGui.QAction("&Settings...", self)
        settings_action.triggered.connect(self._on_settings)
        help_menu.addAction(settings_action)

        help_menu.addSeparator()

        about_action = QtGui.QAction("&About CraftGraph", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    # -- Central widget (splitter layout) -------------------------------------

    def _setup_central_widget(self) -> None:
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab bar (file tabs across the top)
        self._tab_bar = QtWidgets.QTabBar()
        self._tab_bar.setTabsClosable(False)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tab_bar)

        # Splitter with two stacked widgets
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

        # Minimap overlay (anchored to bottom-right of graph container)
        self._minimap = MinimapWidget(parent=self._graph_container)
        self._minimap.raise_()
        self._graph_container.installEventFilter(self)

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

        self._setup_context_menus_for(graph)
        self._minimap.attach(graph)

    def _on_tab_changed(self, index: int) -> None:
        """Switch both stacked widgets to the selected file tab."""
        if index < 0 or index >= len(self._file_tabs):
            return
        self._graph_stack.setCurrentIndex(index)
        self._editor_stack.setCurrentIndex(index)

        tab = self._file_tabs[index]
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

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        if obj is self._graph_container and event.type() == QtCore.QEvent.Type.Resize:
            self._position_minimap()
        return super().eventFilter(obj, event)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        # Deferred positioning so widget geometry is finalized
        QtCore.QTimer.singleShot(0, self._position_minimap)

    # -- Status bar -----------------------------------------------------------

    def _setup_status_bar(self) -> None:
        self.statusBar().showMessage("Ready")

    # -- Close event ----------------------------------------------------------

    def _has_unsaved_changes(self) -> bool:
        """True if any file tab has unsaved edits."""
        return any(
            hasattr(tab.history, "is_dirty") and tab.history.is_dirty for tab in self._file_tabs
        )

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        """Prompt the user if there are unsaved changes before closing."""
        if not self._has_unsaved_changes():
            self._save_positions()
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
            event.accept()
        elif result == QtWidgets.QMessageBox.StandardButton.Discard:
            self._save_positions()
            event.accept()
        else:
            event.ignore()

    def _save_positions(self) -> None:
        """Persist all user-dragged node positions to the layout sidecar file."""
        if not self._file_tabs:
            return
        # Find a tab with a real source path to determine the sidecar location
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

        # Only write if at least one tab has user positions
        if any(pos for pos in all_positions.values()):
            save_layout(layout_file, all_positions)

    def _save_all(self) -> None:
        """Save all dirty tabs to disk."""
        saved = 0
        for tab in self._file_tabs:
            if tab.parsed_file is None:
                continue
            if not hasattr(tab.history, "is_dirty") or not tab.history.is_dirty:
                continue
            path = tab.parsed_file.source_path
            text = serialize_file(tab.parsed_file)
            path.write_text(text, encoding="utf-8")
            tab.history.mark_saved()
            saved += 1
        self._save_positions()
        if saved:
            self._on_tab_changed(self._tab_bar.currentIndex())
            self.statusBar().showMessage(f"Saved {saved} file(s)")

    # -- Menu handlers --------------------------------------------------------

    def _on_new_file(self) -> None:
        """Open the New File dialog and create an empty tab for the chosen block type."""
        default_dir = (
            self._source_path.parent
            if self._source_path.is_file()
            else self._source_path
            if self._source_path.is_dir()
            else Path.cwd()
        )
        dialog = NewFileDialog(parent=self, default_dir=default_dir)
        if dialog.exec_() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        pf = ParsedFile(source_path=dialog.file_path, block_type=dialog.block_type)
        tab = self._create_file_tab(pf)
        self._file_tabs.append(tab)

        self._graph_stack.addWidget(tab.graph.widget)
        self._editor_stack.addWidget(tab.editor)
        self._tab_bar.addTab(pf.source_path.stem)

        # Switch to the new tab
        new_index = len(self._file_tabs) - 1
        self._tab_bar.setCurrentIndex(new_index)
        self._on_tab_changed(new_index)

        # Spawn a starter node for the block type
        self._spawn_starter_node(pf.block_type)

        self.statusBar().showMessage(
            f"New file: {pf.source_path.name} ({pf.block_type.value})"
        )

    def _on_new_project(self) -> None:
        """Open the New Project dialog and scaffold a CC3 mod directory."""
        dialog = NewProjectDialog(parent=self)
        if dialog.exec_() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        project_dir = dialog.project_path
        block_types = dialog.selected_block_types

        # Create directory structure
        project_dir.mkdir(parents=True)
        (project_dir / "Assets").mkdir()
        (project_dir / ".craftgraph").mkdir()

        # Create one empty .txt file per selected block type
        for bt in block_types:
            filename = f"{_BLOCK_TYPE_DEFAULT_NAMES[bt]}.txt"
            file_path = project_dir / filename
            # Write a minimal template: just the block type header with empty body
            file_path.write_text(f"{bt.value}:\n", encoding="utf-8")

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

        self.statusBar().showMessage(
            f"Created project: {project_dir.name} ({len(block_types)} files)"
        )

    def _on_open_folder(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Open Recipe Directory",
        )
        if directory:
            self.load_recipes(Path(directory))

    def _on_open_file(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open Recipe File",
            "",
            "CC3 Recipe Files (*.txt);;All Files (*)",
        )
        if file_path:
            self.load_recipes(Path(file_path))

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
            node_label = node.get_property("item_id") or node.get_property("tab_id") or node.NODE_NAME
            for fp in node.FIELD_REGISTRY:
                if fp.pin_type == PinType.INGREDIENT_LIST:
                    continue
                value = node.get_property(fp.name)
                empty = value is None or (isinstance(value, str) and not value.strip())
                if fp.required and empty:
                    issues.append(f"{node_label}: {fp.label} is required but empty")
                if fp.name in self._PATH_WIDGET_NAMES and not empty and isinstance(value, str):
                    if value.strip() not in valid_paths:
                        issues.append(f"{node_label}: Path '{value}' does not match any known fabricator or tab")
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
                    issues.append(f"{node_label}: {la} and {lb} should both be set or both be empty")
        return issues

    def _show_validation_summary(self, issues: list[str]) -> bool:
        """Show a validation summary dialog. Returns True if user wants to save anyway."""
        if not issues:
            return True
        dlg = QtWidgets.QDialog(self, _DIALOG_FLAGS)
        dlg.setStyleSheet(_DIALOG_STYLE)
        dlg.setMinimumSize(480, 300)

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
        issues = self._collect_validation_issues(tab)
        if issues and not self._show_validation_summary(issues):
            self.statusBar().showMessage("Save cancelled")
            return
        path = tab.parsed_file.source_path
        text = serialize_file(tab.parsed_file)
        path.write_text(text, encoding="utf-8")
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
        tab.graph.clear_selection()
        self._save_positions()
        self.statusBar().showMessage("Layout reset to default")

    def _on_settings(self) -> None:
        """Show a placeholder Settings dialog."""
        dialog = QtWidgets.QDialog(self, _DIALOG_FLAGS)
        dialog.setStyleSheet(_DIALOG_STYLE)
        dialog.setMinimumSize(300, 150)
        layout = QtWidgets.QVBoxLayout(dialog)
        label = QtWidgets.QLabel("Settings coming soon.")
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        dialog.move(QtGui.QCursor.pos())
        dialog.exec()

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

    def _show_error_status(self, message: str, duration_ms: int = 5000) -> None:
        """Show *message* with a red background in the status bar."""
        bar = self.statusBar()
        bar.setStyleSheet("QStatusBar { background-color: #cc3c3c; color: white; }")
        bar.showMessage(message)
        QtCore.QTimer.singleShot(duration_ms, self._clear_status_style)

    def _on_cycle_rejected(self, consumer_id: str, ingredient_id: str) -> None:
        """Show a red-background status bar warning when a connection would create a cycle."""
        self._show_error_status(
            f"Rejected: adding {ingredient_id} to {consumer_id} would create a circular dependency"
        )

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
                if (
                    x < nx + nw
                    and x + w_est > nx
                    and y < ny + nh
                    and y + h_est > ny
                ):
                    collision = True
                    break
            if not collision:
                return x, y
            x += CraftGraphWindow._NUDGE_X
            y += CraftGraphWindow._NUDGE_Y
        return x, y

    # -- Node operations (delete, copy, paste, duplicate) --------------------

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # type: ignore[override]
        """Handle keyboard shortcuts for node operations."""
        key = event.key()
        ctrl = bool(event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier)

        if key == QtCore.Qt.Key.Key_Delete:
            self._delete_selected_nodes()
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

            node.model_ref = model
            tab.model_to_node[id(model)] = node
            getattr(tab.parsed_file, attr_name).append(model)

            if tab.ui_handler is not None:
                tab.ui_handler.register_node(node)

        self._update_code_editor_from_model()

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
            return

        # Tear down previous handler
        if tab.ui_handler is not None:
            tab.ui_handler.disconnect()
            tab.ui_handler = None

        tab.graph.clear_session()
        tab.history.clear()

        with tab.sync_guard():
            tab.model_to_node = populate_graph(tab.graph, [pf], edit_history=tab.history)
            connect_hierarchy(tab.graph, [pf], tab.model_to_node)
            connect_ingredients(tab.graph, [pf], tab.model_to_node)
            positions = compute_hierarchy_layout([pf], tab.model_to_node)
            overlay_user_positions(positions, tab.user_positions, tab.model_to_node)
            apply_layout(positions, tab.model_to_node)
            highlight_cycle_edges(tab.graph, [pf], tab.model_to_node)
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

        # Ingredient management (recipe nodes only)
        for op_name, op_func in [
            ("Delete Ingredient...", self._on_delete_ingredient),
            ("Promote Ingredient to Recipe...", self._on_promote_ingredient),
        ]:
            cmd = nodes_menu.add_command(
                op_name, func=op_func, node_class=ModifiedRecipeNode,
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

        # Node creation submenu
        add_menu = graph_menu.add_menu("Add Node")

        cmd = add_menu.add_command(
            "Ingredient",
            func=lambda g: self._create_orphan_ingredient(),
        )
        cmd.qaction.setToolTip(NODE_DESCRIPTIONS["Ingredient"])

        recipes_menu = add_menu.add_menu("Recipes")
        for kind, name in [
            (NodeKind.MODIFIED_RECIPE, "Modified Recipe"),
            (NodeKind.ADDED_RECIPE, "Added Recipe"),
            (NodeKind.ALIAS_RECIPE, "Alias Recipe"),
            (NodeKind.CUSTOM_FOOD, "Custom Food"),
        ]:
            cmd = recipes_menu.add_command(
                name, func=self._make_create_callback(kind),
            )
            if name in NODE_DESCRIPTIONS:
                cmd.qaction.setToolTip(NODE_DESCRIPTIONS[name])

        containers_menu = add_menu.add_menu("Containers")
        for kind, name in [
            (NodeKind.FABRICATOR, "Fabricator"),
            (NodeKind.CRAFTING_TAB, "Crafting Tab"),
        ]:
            cmd = containers_menu.add_command(
                name, func=self._make_create_callback(kind),
            )
            if name in NODE_DESCRIPTIONS:
                cmd.qaction.setToolTip(NODE_DESCRIPTIONS[name])

        other_menu = add_menu.add_menu("Utility")
        for kind, name in [
            (NodeKind.CUSTOM_SIZE, "Custom Size"),
            (NodeKind.MOVED_RECIPE, "Moved Recipe"),
            (NodeKind.CUSTOM_BIO_FUEL, "Custom BioFuel"),
            (NodeKind.CUSTOM_FRAGMENT_COUNT, "Custom Fragment Count"),
            (NodeKind.SPRITE, "Sprite"),
        ]:
            cmd = other_menu.add_command(
                name, func=self._make_create_callback(kind),
            )
            if name in NODE_DESCRIPTIONS:
                cmd.qaction.setToolTip(NODE_DESCRIPTIONS[name])

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
            cmd = variables_menu.add_command(
                name, func=self._make_var_create_cb(var_kind),
            )
            if name in VARIABLE_DESCRIPTIONS:
                cmd.qaction.setToolTip(VARIABLE_DESCRIPTIONS[name])

        # Enable floating tooltips on all context menus
        enable_menu_tooltips(nodes_menu.qmenu)
        enable_menu_tooltips(graph_menu.qmenu)

    def _make_var_create_cb(self, kind: VariableNodeKind):  # type: ignore[no-untyped-def]
        """Return a callback that creates a variable node of the given kind."""
        from craftgraph.qt_variable_nodes import VARIABLE_NODE_REGISTRY

        def callback(graph: NodeGraph) -> None:
            cls = VARIABLE_NODE_REGISTRY[kind]
            type_name = f"com.craftgraph.{cls.__name__}"
            viewer = graph.viewer()
            cursor_pos = viewer.mapFromGlobal(QtGui.QCursor.pos())
            scene_pos = viewer.mapToScene(cursor_pos)
            sx, sy = CraftGraphWindow._find_free_position(
                graph, scene_pos.x(), scene_pos.y(),
            )
            graph.clear_selection()
            node = graph.create_node(
                type_name, name=cls.NODE_NAME,
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
        cursor_pos = viewer.mapFromGlobal(QtGui.QCursor.pos())
        scene_pos = viewer.mapToScene(cursor_pos)

        node = tab.graph.create_node(
            type_,
            name=item_id,
            pos=[scene_pos.x(), scene_pos.y()],
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
        """Return a callback that creates a node of the given kind.

        Each callback must be a separate closure so that ``kind`` is
        captured by value, not by reference.
        """

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
            cursor_pos = viewer.mapFromGlobal(QtGui.QCursor.pos())
            scene_pos = viewer.mapToScene(cursor_pos)
            sx, sy = self._find_free_position(
                tab.graph, scene_pos.x(), scene_pos.y(),
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
                self._show_error_status(
                    "No fabricator to nest into -- add a Fabricator first"
                )
                return
            target_fab = fabs[0]
            fab_attr = fab_nestable[block_type]
            getattr(target_fab, fab_attr).append(model)
        else:
            getattr(pf, attr_name).append(model)

        viewer = tab.graph.viewer()
        cursor_pos = viewer.mapFromGlobal(QtGui.QCursor.pos())
        scene_pos = viewer.mapToScene(cursor_pos)
        sx, sy = self._find_free_position(
            tab.graph, scene_pos.x(), scene_pos.y(),
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
        """Return the cached, sorted list of vanilla + mod-compat TechType IDs."""
        if self._id_words is None:
            from craftgraph.vanilla_ids import load_mod_compat_ids, load_vanilla_ids

            self._id_words = sorted(
                load_vanilla_ids() | load_mod_compat_ids(),
                key=str.lower,
            )
        return self._id_words

    def _make_completer(
        self,
        words: list[str],
        parent: QtCore.QObject | None = None,
    ) -> QtWidgets.QCompleter:
        """Build a case-insensitive, substring-matching QCompleter."""
        completer = QtWidgets.QCompleter(words, parent or self)
        completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
        return completer

    def _setup_autocomplete_for(self, editor: CodeEditor) -> None:
        """Attach a QCompleter to the given code editor.

        TechType IDs are the default completion source.  Path completions
        are populated after recipe files are loaded.
        """
        editor.set_completer(self._make_completer(self._get_id_words()))

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
        paths: set[str] = {
            "Fabricator",
            "Workbench",
            "SeamothUpgrades",
            "MapRoomFunctionality",
            "CyclopsFabricator",
        }

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
    _BUILTIN_PATH_ROOTS: frozenset[str] = frozenset({
        "Fabricator",
        "Workbench",
        "SeamothUpgrades",
        "MapRoomFunctionality",
        "CyclopsFabricator",
    })

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
        """Disconnect and remove all existing file tabs."""
        for tab in self._file_tabs:
            if tab.ui_handler is not None:
                tab.ui_handler.disconnect()
            if tab.parse_timer is not None:
                tab.parse_timer.stop()
            tab.graph.clear_session()

        self._file_tabs.clear()
        self._tab_bar.blockSignals(True)
        while self._tab_bar.count():
            self._tab_bar.removeTab(0)
        self._tab_bar.blockSignals(False)

        while self._graph_stack.count():
            w = self._graph_stack.widget(0)
            self._graph_stack.removeWidget(w)

        while self._editor_stack.count():
            w = self._editor_stack.widget(0)
            self._editor_stack.removeWidget(w)

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

        guard = SyncGuard()
        history = EditHistory(on_change=self._on_model_changed)

        initial_user_positions = dict(saved_positions) if saved_positions else {}

        with guard():
            model_to_node = populate_graph(graph, [parsed_file], edit_history=history)
            connect_hierarchy(graph, [parsed_file], model_to_node)
            connect_ingredients(graph, [parsed_file], model_to_node)
            positions = compute_hierarchy_layout([parsed_file], model_to_node)
            overlay_user_positions(positions, initial_user_positions, model_to_node)
            apply_layout(positions, model_to_node)
            cycle_count = highlight_cycle_edges(graph, [parsed_file], model_to_node)
            update_child_count_labels(model_to_node)
            # NodeGraphQt defaults create_node(selected=True); clear to
            # avoid accidental bulk deletion of newly-loaded nodes.
            graph.clear_selection()

        self._attach_completers_bulk(model_to_node)

        editor = CodeEditor()
        EasyMarkupHighlighter(editor.document())
        self._setup_autocomplete_for(editor)

        # Per-tab debounce timer
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(300)

        tab = FileTab(
            parsed_file=parsed_file,
            graph=graph,
            editor=editor,
            history=history,
            ui_handler=None,
            sync_guard=guard,
            model_to_node=model_to_node,
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

        # Wire node drag -> save user positions
        def on_nodes_moved(moved: dict, _tab: FileTab = tab) -> None:
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
        )

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

        # Scan for sprite assets
        recipe_dir = path.parent if path.is_file() else path
        self._sprite_lookup = scan_assets_dir(recipe_dir)

        # Load persisted node positions from sidecar file
        layout_file = layout_path_for(path)
        disk_positions = load_layout(layout_file) or {}

        # Create one FileTab per parsed file
        for pf in parsed_files:
            tab_key = pf.source_path.stem
            tab_saved = disk_positions.get(tab_key, {})
            # Convert [x, y] lists to (x, y) tuples for in-memory use
            saved_pos = {k: (v[0], v[1]) for k, v in tab_saved.items()}
            tab = self._create_file_tab(pf, saved_positions=saved_pos)
            self._file_tabs.append(tab)

            self._graph_stack.addWidget(tab.graph.widget)
            self._editor_stack.addWidget(tab.editor)
            self._tab_bar.addTab(pf.source_path.stem)

        # Apply sprites across all tabs
        for tab in self._file_tabs:
            self._apply_sprites_for(tab)

        self._update_path_completions()
        self._refresh_all_ref_nodes()

        # Activate first tab
        self._tab_bar.setCurrentIndex(0)
        self._on_tab_changed(0)

        total_nodes = sum(len(t.model_to_node) for t in self._file_tabs)
        total_cycles = sum(t.cycle_count for t in self._file_tabs)
        cycle_msg = f", {total_cycles} cycle(s)!" if total_cycles else ", no cycles"
        self.statusBar().showMessage(
            f"Loaded {total_nodes} nodes from {len(parsed_files)} file(s){cycle_msg}"
        )


# ---------------------------------------------------------------------------
# Launch helper
# ---------------------------------------------------------------------------


def launch_qt_gui(recipe_path: Path | None = None) -> None:
    """Create the QApplication and show the CraftGraph main window.

    Called by the ``craftgraph qt-gui`` CLI command.
    """
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    window = CraftGraphWindow()

    if recipe_path is not None:
        window.load_recipes(recipe_path)

    window.show()
    app.exec()
