"""NodeGraphQt node subclasses for CraftGraph CC3 types (Step M2).

Maps the CC3 data model (models.py) to visual NodeGraphQt nodes.
Each node class defines its ports, embedded widgets, and callbacks.

Architecture notes:
  - This module is part of the GUI layer; it imports from models.py
    but models.py never imports from here (GUI Architecture Guardrail #3).
  - Each node stores an optional model_ref back to its data-model object,
    enabling the Model-to-UI sync layer (Step M4).
  - NodeGraphQt's type_ = __identifier__ + "." + ClassName, so
    create_node() uses e.g. "com.craftgraph.ModifiedRecipeNode".
"""

from __future__ import annotations

import uuid
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from NodeGraphQt import BaseNode
from NodeGraphQt.constants import Z_VAL_NODE_WIDGET, PortTypeEnum, ViewerEnum
from NodeGraphQt.widgets.node_widgets import NodeBaseWidget, _NodeGroupBox
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QGraphicsItem,
    QGraphicsView,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QStyleOptionGraphicsItem,
    QWidget,
)

from craftgraph.config import get_config
from craftgraph.theme import scaled_pt
from craftgraph.models import (
    FABRICATOR_MODELS,
    FOOD_MODELS,
    TECH_CATEGORIES,
    TECH_GROUPS,
)
from craftgraph.pin_registry import (
    FieldPin,
    OutputPin,
    PinType,
    convert_to_display,
    convert_to_model,
)

if TYPE_CHECKING:
    from craftgraph.commands import EditHistory

# ---------------------------------------------------------------------------
# Monkey-patch: prevent _NodeGroupBox HWND allocation on Windows
# ---------------------------------------------------------------------------
# NodeGraphQt creates every _NodeGroupBox without a parent.  On Windows, the
# moment a QWidget becomes top-level (parent = None), Qt allocates a native
# window handle (HWND) for it during the next polish/show cycle.  With large
# graphs (~894 nodes x ~8 widgets) this exhausts the per-process USER object
# limit (~10,000 handles), surfaced as
# "CreateWindowEx failed (... system allowance of handles for Window Manager)".
#
# Fix:
# 1. Create _NodeGroupBox with a shared hidden (WA_DontShowOnScreen) parent so
#    it starts out non-top-level (no HWND allocation on construction).
# 2. Mark the group AND the embedded widget tree WA_DontShowOnScreen *before*
#    the brief `setParent(None)` window so Qt skips HWND creation when the
#    group becomes top-level.
# 3. Do NOT destroy() the underlying window afterwards -- that breaks
#    QGraphicsProxyWidget rendering (only the first registry widget paints,
#    escaping the node bounds).

_GROUPBOX_PARENT: QWidget | None = None


def _suppress_native_window(widget: QWidget) -> None:
    """Mark *widget* and every descendant ``WA_DontShowOnScreen``.

    ``WA_DontShowOnScreen`` makes Qt skip the HWND-creation path during the
    polish step that runs when a widget becomes top-level or is embedded in a
    ``QGraphicsProxyWidget``.  The proxy paints via ``QWidget.render()``, which
    does not require a native window, so rendering still works.
    """
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    for child in widget.findChildren(QWidget):
        child.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)


def _patched_set_custom_widget(self: NodeBaseWidget, widget: QWidget) -> None:
    """Replacement for NodeBaseWidget.set_custom_widget that prevents HWND leaks."""
    global _GROUPBOX_PARENT
    if self.widget():
        from NodeGraphQt.errors import NodeWidgetError

        msg = "Custom node widget already set."
        raise NodeWidgetError(msg)
    if _GROUPBOX_PARENT is None:
        _GROUPBOX_PARENT = QWidget()
        _GROUPBOX_PARENT.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    group = _NodeGroupBox(self._label, parent=_GROUPBOX_PARENT)
    group.add_node_widget(widget)
    # Block HWND allocation that would otherwise fire when group becomes
    # top-level via setParent(None) below, and again during setWidget()'s
    # internal ensurePolished().
    _suppress_native_window(group)
    _suppress_native_window(widget)
    group.setParent(None)
    self.setWidget(group)


NodeBaseWidget.set_custom_widget = _patched_set_custom_widget  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Monkey-patch: guard auto_switch_mode against missing viewer
# ---------------------------------------------------------------------------
# NodeGraphQt's NodeItem.auto_switch_mode() calls self.viewer() without a
# null check.  When nodes live in a QStackedWidget (tab switching) or during
# clear_session(), the QGraphicsScene may have no attached QGraphicsView,
# so viewer() returns None and the subsequent mapToGlobal() crashes.
#
# Fix: bail out early when viewer() is None.

from NodeGraphQt.qgraphics.node_base import NodeItem as _NodeItem

_original_auto_switch_mode = _NodeItem.auto_switch_mode


def _safe_auto_switch_mode(self: _NodeItem) -> None:  # type: ignore[override]
    if self.viewer() is None:
        return
    _original_auto_switch_mode(self)


_NodeItem.auto_switch_mode = _safe_auto_switch_mode  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Monkey-patch: switch viewport update mode during live-pipe drag
# ---------------------------------------------------------------------------
# NodeGraphQt's live drag updates the LivePipeItem path and a child arrow
# polygon (``_idx_pointer``) whose geometry changes drastically each frame
# as the cursor moves.  With the default ``MinimalViewportUpdate`` mode and
# a BSP-indexed scene, prior frames of the arrow polygon are not always
# invalidated, leaving small stale "ghost arrow" fragments behind.
#
# Fix: switch the QGraphicsView to ``FullViewportUpdate`` while a live pipe
# is active so the entire viewport is repainted on each frame, then restore
# the previous mode when the drag ends.  Only the brief drag window pays
# the extra repaint cost; idle and pan/zoom keep the original behaviour.

from NodeGraphQt.widgets.viewer import NodeViewer as _NodeViewer  # noqa: E402

_original_start_live_connection = _NodeViewer.start_live_connection
_original_end_live_connection = _NodeViewer.end_live_connection
_PREV_UPDATE_MODE_ATTR = "_cg_prev_viewport_update_mode"


def _patched_start_live_connection(self: _NodeViewer, selected_port: object) -> None:
    setattr(self, _PREV_UPDATE_MODE_ATTR, self.viewportUpdateMode())
    self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
    _original_start_live_connection(self, selected_port)


def _patched_end_live_connection(self: _NodeViewer) -> None:
    _original_end_live_connection(self)
    prev = getattr(self, _PREV_UPDATE_MODE_ATTR, None)
    if prev is not None:
        self.setViewportUpdateMode(prev)


_NodeViewer.start_live_connection = _patched_start_live_connection  # type: ignore[assignment]
_NodeViewer.end_live_connection = _patched_end_live_connection  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IDENTIFIER = get_config().app.identifier

# Palettes sourced from config.toml [ui.colors.*] and [ui.variable_nodes].
_NODE_COLORS = get_config().ui.colors.nodes
_PORT_COLORS = get_config().ui.colors.ports
_VAR_NODES = get_config().ui.variable_nodes

# Port colors (R, G, B)
PORT_COLOR_HIERARCHY = _PORT_COLORS.hierarchy
PORT_COLOR_OUTPUT = _PORT_COLORS.output
PORT_COLOR_INGREDIENT = _PORT_COLORS.ingredient
PORT_COLOR_CHILDREN = _PORT_COLORS.children

# Node colors by category
NODE_COLOR_MODIFIED_RECIPE = _NODE_COLORS.modified_recipe
NODE_COLOR_ADDED_RECIPE = _NODE_COLORS.added_recipe
NODE_COLOR_ALIAS_RECIPE = _NODE_COLORS.alias_recipe
NODE_COLOR_CUSTOM_FOOD = _NODE_COLORS.custom_food
NODE_COLOR_FABRICATOR = _NODE_COLORS.fabricator
NODE_COLOR_CRAFTING_TAB = _NODE_COLORS.crafting_tab
NODE_COLOR_CUSTOM_SIZE = _NODE_COLORS.custom_size
NODE_COLOR_MOVED_RECIPE = _NODE_COLORS.moved_recipe
NODE_COLOR_CUSTOM_BIO_FUEL = _NODE_COLORS.custom_bio_fuel
NODE_COLOR_CUSTOM_FRAGMENT_COUNT = _NODE_COLORS.custom_fragment_count
NODE_COLOR_ORPHAN_INGREDIENT = _NODE_COLORS.orphan_ingredient
NODE_COLOR_SPRITE = _NODE_COLORS.sprite

PORT_COLOR_SPRITE = _PORT_COLORS.sprite
PORT_COLOR_VARIABLE = _PORT_COLORS.variable

# Stylesheet fragments for required-field validation highlighting.
_REQUIRED_EMPTY_STYLE = _VAR_NODES.required_empty_style
_REQUIRED_VALID_STYLE = _VAR_NODES.required_valid_style


# Node type strings for port constraints (identifier + "." + ClassName)
_FABRICATOR_TYPE = f"{IDENTIFIER}.FabricatorNode"
_CRAFTING_TAB_TYPE = f"{IDENTIFIER}.CraftingTabNode"


class _IntEditWidget(QWidget):
    """Compact integer editor with explicit -/+ buttons.

    Avoids the QSpinBox-in-QGraphicsProxyWidget bug where the up arrow
    button intercepts clicks as text selection instead of incrementing.
    """

    valueChanged = Signal(int)

    def __init__(
        self,
        value: int = 0,
        min_value: int = 0,
        max_value: int = 99,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._min = min_value
        self._max = max_value

        bg = ViewerEnum.BACKGROUND_COLOR.value
        txt = tuple(255 - c for c in bg)
        grid = ViewerEnum.GRID_COLOR.value

        btn_style = (
            "QPushButton {{ background: rgba({0},{1},{2},20);"
            " border: 1px solid rgb({3},{4},{5});"
            " border-radius: 3px;"
            " color: rgba({6},{7},{8},150);"
            " min-width: 18px; max-width: 18px;"
            " min-height: 18px; max-height: 18px;"
            f" font-size: {scaled_pt(11)}pt; font-weight: bold; }}}}"
            " QPushButton:hover {{ background: rgba({0},{1},{2},60); }}"
        ).format(*bg, *grid, *txt)

        edit_style = (
            "QLineEdit {{ background: rgba({0},{1},{2},20);"
            " border: 1px solid rgb({3},{4},{5});"
            " border-radius: 3px;"
            " color: rgba({6},{7},{8},150);"
            " selection-background-color: rgba({6},{7},{8},100); }}"
        ).format(*bg, *grid, *txt)

        self._minus_btn = QPushButton("-")
        self._minus_btn.setStyleSheet(btn_style)
        self._minus_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._minus_btn.clicked.connect(self._step_down)

        self._edit = QLineEdit(str(value))
        self._edit.setStyleSheet(edit_style)
        self._edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._edit.setMaximumWidth(40)
        self._edit.editingFinished.connect(self._on_editing_finished)

        self._plus_btn = QPushButton("+")
        self._plus_btn.setStyleSheet(btn_style)
        self._plus_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._plus_btn.clicked.connect(self._step_up)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._minus_btn)
        layout.addWidget(self._edit)
        layout.addWidget(self._plus_btn)

    def value(self) -> int:
        try:
            return max(self._min, min(self._max, int(self._edit.text())))
        except ValueError:
            return self._min

    def setValue(self, v: int) -> None:
        clamped = max(self._min, min(self._max, v))
        if str(clamped) != self._edit.text():
            self._edit.setText(str(clamped))
            self.valueChanged.emit(clamped)

    def _step_up(self) -> None:
        self.setValue(self.value() + 1)

    def _step_down(self) -> None:
        self.setValue(self.value() - 1)

    def _on_editing_finished(self) -> None:
        self.setValue(self.value())


class NodeIntEdit(NodeBaseWidget):
    """Integer editor node widget using explicit -/+ buttons.

    Drop-in replacement for ``NodeSpinBox`` that works reliably inside
    ``QGraphicsProxyWidget``.
    """

    def __init__(
        self,
        parent: object = None,
        name: str = "",
        label: str = "",
        value: int = 0,
        min_value: int = 0,
        max_value: int = 99,
    ) -> None:
        super().__init__(parent, name, label)
        self.setZValue(Z_VAL_NODE_WIDGET + 1)
        widget = _IntEditWidget(value, min_value, max_value)
        widget.valueChanged.connect(self.on_value_changed)
        self.set_custom_widget(widget)
        self.widget().setMaximumWidth(140)

    @property
    def type_(self) -> str:  # type: ignore[override]
        return "IntEditNodeWidget"

    def get_value(self) -> str:
        return str(self.get_custom_widget().value())

    def set_value(self, value: int | str = 0) -> None:
        v = int(value) if isinstance(value, str) else value
        if v != self.get_custom_widget().value():
            self.get_custom_widget().setValue(v)
            self.on_value_changed()


class _FloatEditWidget(QWidget):
    """Compact float editor with explicit -/+ buttons.

    Same UX as ``_IntEditWidget`` but operates on float values with a
    configurable step size (default 10.0 for energy values).
    """

    valueChanged = Signal(float)

    def __init__(
        self,
        value: float = 0.0,
        min_value: float = 0.0,
        max_value: float = 99999.0,
        step: float = 10.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._min = min_value
        self._max = max_value
        self._step = step

        bg = ViewerEnum.BACKGROUND_COLOR.value
        txt = tuple(255 - c for c in bg)
        grid = ViewerEnum.GRID_COLOR.value

        btn_style = (
            "QPushButton {{ background: rgba({0},{1},{2},20);"
            " border: 1px solid rgb({3},{4},{5});"
            " border-radius: 3px;"
            " color: rgba({6},{7},{8},150);"
            " min-width: 18px; max-width: 18px;"
            " min-height: 18px; max-height: 18px;"
            f" font-size: {scaled_pt(11)}pt; font-weight: bold; }}}}"
            " QPushButton:hover {{ background: rgba({0},{1},{2},60); }}"
        ).format(*bg, *grid, *txt)

        edit_style = (
            "QLineEdit {{ background: rgba({0},{1},{2},20);"
            " border: 1px solid rgb({3},{4},{5});"
            " border-radius: 3px;"
            " color: rgba({6},{7},{8},150);"
            " selection-background-color: rgba({6},{7},{8},100); }}"
        ).format(*bg, *grid, *txt)

        self._minus_btn = QPushButton("-")
        self._minus_btn.setStyleSheet(btn_style)
        self._minus_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._minus_btn.clicked.connect(self._step_down)

        self._edit = QLineEdit(str(value))
        self._edit.setStyleSheet(edit_style)
        self._edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._edit.setMaximumWidth(55)
        self._edit.editingFinished.connect(self._on_editing_finished)

        self._plus_btn = QPushButton("+")
        self._plus_btn.setStyleSheet(btn_style)
        self._plus_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._plus_btn.clicked.connect(self._step_up)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._minus_btn)
        layout.addWidget(self._edit)
        layout.addWidget(self._plus_btn)

    def value(self) -> float:
        try:
            return max(self._min, min(self._max, float(self._edit.text())))
        except ValueError:
            return self._min

    def setValue(self, v: float) -> None:
        clamped = max(self._min, min(self._max, v))
        display = f"{clamped:g}"
        if display != self._edit.text():
            self._edit.setText(display)
            self.valueChanged.emit(clamped)

    def _step_up(self) -> None:
        self.setValue(self.value() + self._step)

    def _step_down(self) -> None:
        self.setValue(self.value() - self._step)

    def _on_editing_finished(self) -> None:
        self.setValue(self.value())


class NodeFloatEdit(NodeBaseWidget):
    """Float editor node widget using explicit -/+ buttons."""

    def __init__(
        self,
        parent: object = None,
        name: str = "",
        label: str = "",
        value: float = 0.0,
        min_value: float = 0.0,
        max_value: float = 99999.0,
        step: float = 10.0,
    ) -> None:
        super().__init__(parent, name, label)
        self.setZValue(Z_VAL_NODE_WIDGET + 1)
        widget = _FloatEditWidget(value, min_value, max_value, step)
        widget.valueChanged.connect(self.on_value_changed)
        self.set_custom_widget(widget)
        self.widget().setMaximumWidth(140)

    @property
    def type_(self) -> str:  # type: ignore[override]
        return "FloatEditNodeWidget"

    def get_value(self) -> str:
        return str(self.get_custom_widget().value())

    def set_value(self, value: float | str = 0.0) -> None:
        v = float(value) if isinstance(value, str) else value
        if v != self.get_custom_widget().value():
            self.get_custom_widget().setValue(v)
            self.on_value_changed()


def _to_pascal_case(text: str) -> str:
    """Convert a lowercase or mixed-case ID to PascalCase for display.

    Already-PascalCase IDs (e.g. ``"TitaniumIngot"``) pass through unchanged.
    Lowercase IDs (e.g. ``"titaniumingot"``) get their first letter capitalized.
    """
    if not text:
        return text
    return text[0].upper() + text[1:]


def _add_hierarchy_accept_constraints(node: CraftGraphBaseNode, port_name: str) -> None:
    """Constrain a hierarchy/parent port to accept only container children outputs.

    This prevents users from dragging a recipe output into a hierarchy slot.
    Accepts CraftingTabNode.children and FabricatorNode typed output ports
    (tabs_out, added_out, alias_out, foods_out, moved_out) for SPLIT_OUTPUTS,
    plus FabricatorNode.children for backward compatibility.
    """
    port = node.get_input(port_name)
    if port is None:
        return
    # Accept CraftingTabNode.children (always valid)
    node.add_accept_port_type(
        port,
        {
            "port_name": "children",
            "port_type": PortTypeEnum.OUT.value,
            "node_type": _CRAFTING_TAB_TYPE,
        },
    )
    # Accept FabricatorNode.children (backward compat when SPLIT_OUTPUTS=False)
    node.add_accept_port_type(
        port,
        {
            "port_name": "children",
            "port_type": PortTypeEnum.OUT.value,
            "node_type": _FABRICATOR_TYPE,
        },
    )
    # Accept typed FabricatorNode output ports (SPLIT_OUTPUTS=True)
    for typed_port in ("tabs_out", "added_out", "alias_out", "foods_out", "moved_out"):
        node.add_accept_port_type(
            port,
            {
                "port_name": typed_port,
                "port_type": PortTypeEnum.OUT.value,
                "node_type": _FABRICATOR_TYPE,
            },
        )


# ---------------------------------------------------------------------------
# Warning overlay (issue indicator)
# ---------------------------------------------------------------------------


class _WarningOverlay(QGraphicsItem):
    """Triangle icon painted at the top-right corner of a node when it has issues.

    Severity controls the fill color: ``"warning"`` is yellow (broken refs,
    unknown ingredients), ``"error"`` is red (cycle members).
    """

    SIZE = 18
    MARGIN = 4

    _ERROR_FILL = QColor(220, 50, 50)
    _WARNING_FILL = QColor(240, 200, 50)
    _BORDER = QColor(20, 20, 20)
    _GLYPH = QColor(20, 20, 20)

    def __init__(self, parent_item: QGraphicsItem) -> None:
        super().__init__(parent_item)
        self._severity: str = "warning"
        self.setZValue(Z_VAL_NODE_WIDGET + 5)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, False)

    def boundingRect(self) -> QRectF:
        s = self.SIZE
        return QRectF(0, 0, s, s)

    def set_state(self, severity: str, tooltip: str) -> None:
        self._severity = "error" if severity == "error" else "warning"
        self.setToolTip(tooltip)
        self.update()

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        s = self.SIZE
        fill = self._ERROR_FILL if self._severity == "error" else self._WARNING_FILL
        path = QPainterPath()
        path.moveTo(s / 2.0, 1.0)
        path.lineTo(s - 1.0, s - 1.0)
        path.lineTo(1.0, s - 1.0)
        path.closeSubpath()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QBrush(fill))
        painter.setPen(QPen(self._BORDER, 1.2))
        painter.drawPath(path)
        pen = QPen(self._GLYPH, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        cx = s / 2.0
        painter.drawLine(QPointF(cx, s * 0.32), QPointF(cx, s * 0.62))
        painter.drawPoint(QPointF(cx, s * 0.78))


# ---------------------------------------------------------------------------
# Base node
# ---------------------------------------------------------------------------


class CraftGraphBaseNode(BaseNode):
    """Shared base for all CraftGraph node types.

    Provides:
    - Common ``__identifier__`` so all CraftGraph nodes live under
      the ``com.craftgraph`` namespace.
    - A ``model_ref`` slot for linking back to the data-model object.
    - Port deletion enabled by default (dynamic ingredient slots).
    - Registry-driven widget and port creation via ``FIELD_REGISTRY``
      and ``OUTPUT_PINS`` class attributes.
    - ``populate_from_model()`` for loading model data into widgets
      with an undo-safe ``_populating`` guard.
    """

    __identifier__ = IDENTIFIER
    NODE_NAME = "CraftGraphBase"
    NODE_COLOR: tuple[int, int, int] = (60, 60, 60)
    FIELD_REGISTRY: list[FieldPin] = []
    OUTPUT_PINS: list[OutputPin] = []
    SPLIT_OUTPUTS: bool = False
    HAS_SPRITE_PORT: bool = False
    IS_VARIABLE: bool = False
    # Pairs of boolean fields where at most one can be True.
    MUTUAL_EXCLUSIONS: list[tuple[str, str]] = []
    # Pairs of optional fields that should both be set or both be empty.
    PAIRED_FIELDS: list[tuple[str, str]] = []

    def __init__(self) -> None:
        super().__init__()
        self.set_port_deletion_allowed(True)
        self._model_ref: Any = None
        self._sprite_path: Path | None = None
        self._edit_history: EditHistory | None = None
        self._populating: bool = False
        self._stashed_values: dict[str, Any] = {}
        self._warning_overlay: _WarningOverlay | None = None
        self._source_file_name: str = ""
        self._issue_messages: list[str] = []
        self._cycle_paths: list[str] = []

        self.set_color(*self.NODE_COLOR)
        if self.HAS_SPRITE_PORT:
            self.add_input("sprite_in", multi_input=False, color=PORT_COLOR_SPRITE)
        self._build_from_registry()
        self._build_outputs()
        self._fix_widget_z_order()
        self.validate_required_fields()

    @property
    def model_ref(self) -> Any:
        """Reference to the backing data-model object (e.g. ModifiedRecipe)."""
        return self._model_ref

    @model_ref.setter
    def model_ref(self, value: Any) -> None:
        self._model_ref = value

    @property
    def sprite_path(self) -> Path | None:
        """Currently assigned sprite file path, or None."""
        return self._sprite_path

    def set_sprite(self, path: Path | None, size: int | None = None) -> None:
        """Set a sprite image on this node at *size* pixels.

        Bypasses NodeGraphQt's built-in 18px icon scaling by setting
        the pixmap directly on the view's QGraphicsPixmapItem.

        If *path* is None or does not exist, clears the sprite.
        """
        if path is None or not path.exists():
            self.clear_sprite()
            return
        if size is None:
            size = get_config().ui.sprite_size
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.clear_sprite()
            return
        pixmap = pixmap.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.view._icon_item.setPixmap(pixmap)
        self._sprite_path = path
        if self.view.scene():
            self.view.post_init()

    def clear_sprite(self) -> None:
        """Remove the custom sprite and restore the default icon."""
        self._sprite_path = None
        self.set_icon(None)

    # -- Warning triangle overlay -------------------------------------------

    def set_node_warning(self, severity: str, tooltip: str = "") -> None:
        """Show a warning triangle on this node.

        ``severity`` is ``"error"`` (red) or ``"warning"`` (yellow).
        ``tooltip`` is shown on hover.
        """
        if self._warning_overlay is None:
            self._warning_overlay = _WarningOverlay(self.view)
        self._warning_overlay.set_state(severity, tooltip)
        self._reposition_warning_overlay()
        self._warning_overlay.show()

    def clear_node_warning(self) -> None:
        """Remove the warning triangle, if any."""
        if self._warning_overlay is not None:
            self._warning_overlay.hide()

    def _reposition_warning_overlay(self) -> None:
        if self._warning_overlay is None:
            return
        rect = self.view.boundingRect()
        size = _WarningOverlay.SIZE
        margin = _WarningOverlay.MARGIN
        self._warning_overlay.setPos(rect.right() - size - margin, margin)

    # -- Registry-driven build methods --------------------------------------

    def _build_from_registry(self) -> None:
        """Create widgets and field input ports for all declared field pins."""
        for fp in self.FIELD_REGISTRY:
            if fp.pin_type == PinType.INGREDIENT_LIST:
                continue
            self._create_widget_for_field(fp)
            # Variable nodes produce values, not consume them --
            # they don't get field_* input ports.
            if not self.IS_VARIABLE:
                port = self.add_input(
                    f"field_{fp.name}",
                    multi_input=False,
                    color=PORT_COLOR_VARIABLE,
                    display_name=True,
                )
                # NodeGraphQt shows port.name as the label text.
                # Rename it to the human-readable field label via
                # the underlying QGraphicsTextItem so we keep the
                # internal port name for lookups but display nicely.
                if port is not None and fp.label:
                    port_item = port.view
                    node_item = self.view
                    text_item = node_item.get_input_text_item(port_item)
                    if text_item is not None:
                        text_item.setPlainText(fp.label)

    def _create_widget_for_field(self, fp: FieldPin) -> None:
        """Create the appropriate widget for a single field pin."""
        match fp.pin_type:
            case PinType.STRING | PinType.CSV:
                if fp.widget_override == "combo":
                    items = fp.enum_items or []
                    if not items:
                        items = ["(none)"]
                    self.add_combo_menu(fp.name, label=fp.label, items=items)
                else:
                    self.add_text_input(fp.name, label=fp.label, text=str(fp.default or ""))
            case PinType.INT:
                self.add_int_edit(
                    fp.name,
                    label=fp.label,
                    value=fp.default if fp.default is not None else 0,
                    min_value=int(fp.min_val) if fp.min_val is not None else 0,
                    max_value=int(fp.max_val) if fp.max_val is not None else 99,
                )
            case PinType.FLOAT:
                self.add_float_edit(
                    fp.name,
                    label=fp.label,
                    value=fp.default if fp.default is not None else 0.0,
                    min_value=float(fp.min_val) if fp.min_val is not None else 0.0,
                    max_value=float(fp.max_val) if fp.max_val is not None else 99999.0,
                    step=fp.step,
                )
            case PinType.BOOL:
                self.add_checkbox(fp.name, label=fp.label, state=bool(fp.default))
            case PinType.ENUM:
                self.add_combo_menu(fp.name, label=fp.label, items=fp.enum_items or [])

        # Overflow tooltip: show current value on hover for truncated fields
        widget_item = self.get_widget(fp.name)
        if widget_item is not None:
            qt_widget = widget_item.get_custom_widget()
            if qt_widget is not None:
                if isinstance(qt_widget, QLineEdit):
                    qt_widget.textChanged.connect(qt_widget.setToolTip)
                    qt_widget.setToolTip(qt_widget.text())
                elif isinstance(qt_widget, QComboBox):
                    qt_widget.currentTextChanged.connect(qt_widget.setToolTip)
                    qt_widget.setToolTip(qt_widget.currentText())
                elif hasattr(qt_widget, "_edit"):
                    # _IntEditWidget / _FloatEditWidget: inner QLineEdit
                    inner = qt_widget._edit
                    inner.textChanged.connect(inner.setToolTip)
                    inner.setToolTip(inner.text())

    def _build_outputs(self) -> None:
        """Create output ports from OUTPUT_PINS declarations."""
        for op in self.OUTPUT_PINS:
            self.add_output(op.name, multi_output=op.multi, color=op.pin_color)

    def _fix_widget_z_order(self) -> None:
        """Assign descending z-values to proxy widgets.

        NodeGraphQt creates all embedded widgets at the same z-level
        (Z_VAL_NODE_WIDGET).  When a combo box opens its dropdown, proxy
        widgets below it bleed through because they share the same z.
        Assigning descending z-values (topmost widget highest) prevents
        lower widgets from rendering on top of open dropdowns.
        """
        widgets = list(self.view.widgets.values())
        base_z = Z_VAL_NODE_WIDGET + len(widgets)
        for idx, widget in enumerate(widgets):
            widget.setZValue(base_z - idx)

    # -- Edit history and model population ----------------------------------

    def set_edit_history(self, history: EditHistory) -> None:
        """Inject the EditHistory for auto-wired model updates."""
        self._edit_history = history

    def populate_from_model(self) -> None:
        """Set all widget values from the model_ref's fields.

        Uses the _populating guard to prevent _on_field_changed from
        firing during programmatic population (which would corrupt
        the undo stack).
        """
        if self._model_ref is None:
            return
        self._populating = True
        try:
            for fp in self.FIELD_REGISTRY:
                if fp.pin_type == PinType.INGREDIENT_LIST:
                    continue
                value = getattr(self._model_ref, fp.resolved_model_field, fp.default)
                display = convert_to_display(fp, value)
                self.set_property(fp.name, display)
        finally:
            self._populating = False
        self.validate_required_fields()
        self.validate_paired_fields()
        self.update_title_from_model()

    def update_title_from_model(self) -> None:
        """Refresh the node title bar from model fields.

        Appends ``(xN)`` when ``amount_crafted > 1``.
        """
        if self._model_ref is None:
            return
        item_id = getattr(self._model_ref, "item_id", None)
        if item_id is None:
            return
        amount = getattr(self._model_ref, "amount_crafted", 1)
        title = f"{item_id} (x{amount})" if amount > 1 else item_id
        self.set_name(title)

    def validate_required_fields(self) -> None:
        """Apply or remove red border on required fields based on emptiness."""
        for fp in self.FIELD_REGISTRY:
            if not fp.required:
                continue
            widget_item = self.get_widget(fp.name)
            if widget_item is None:
                continue
            qt_widget = widget_item.get_custom_widget()
            if qt_widget is None:
                continue
            value = self.get_property(fp.name)
            empty = value is None or (isinstance(value, str) and not value.strip())
            qt_widget.setStyleSheet(_REQUIRED_EMPTY_STYLE if empty else _REQUIRED_VALID_STYLE)

    def _get_field_pin(self, name: str) -> FieldPin | None:
        """Look up a FieldPin by widget/property name."""
        for fp in self.FIELD_REGISTRY:
            if fp.name == name:
                return fp
        return None

    def _on_field_changed(self, field_name: str, new_value: Any) -> None:
        """Auto-wired callback: widget value changed -> update model.

        Suppressed during populate_from_model() via the _populating guard.
        """
        if self._populating:
            return
        if self._edit_history is None or self._model_ref is None:
            return
        fp = self._get_field_pin(field_name)
        if fp is None:
            return

        from craftgraph.commands import ChangeNonRecipeFieldCommand, ChangeRecipeFieldCommand
        from craftgraph.models import ModifiedRecipe

        converted = convert_to_model(fp, new_value)
        model_attr = fp.resolved_model_field

        if isinstance(self._model_ref, ModifiedRecipe):
            cmd = ChangeRecipeFieldCommand(self._model_ref, model_attr, converted)
        else:
            cmd = ChangeNonRecipeFieldCommand(self._model_ref, model_attr, converted)

        self._edit_history.execute(cmd)
        self._enforce_mutual_exclusion(field_name, converted)
        self.validate_required_fields()
        self.validate_paired_fields()
        if model_attr in ("item_id", "amount_crafted"):
            self.update_title_from_model()

    def _enforce_mutual_exclusion(self, field_name: str, value: Any) -> None:
        """If a boolean field in a mutual-exclusion pair becomes True, uncheck its partner."""
        if not value:
            return
        for a, b in self.MUTUAL_EXCLUSIONS:
            partner = None
            if field_name == a:
                partner = b
            elif field_name == b:
                partner = a
            if partner is not None:
                self._populating = True
                try:
                    self.set_property(partner, False)
                finally:
                    self._populating = False
                if self._model_ref is not None:
                    setattr(self._model_ref, partner, False)
                break

    def validate_paired_fields(self) -> None:
        """Warn when only one field in a paired set has a value."""
        for a, b in self.PAIRED_FIELDS:
            wa = self.get_widget(a)
            wb = self.get_widget(b)
            if wa is None or wb is None:
                continue
            qa = wa.get_custom_widget()
            qb = wb.get_custom_widget()
            if qa is None or qb is None:
                continue
            val_a = self.get_property(a)
            val_b = self.get_property(b)
            empty_a = val_a is None or (isinstance(val_a, str) and not val_a.strip())
            empty_b = val_b is None or (isinstance(val_b, str) and not val_b.strip())
            if empty_a != empty_b:
                # One set, the other not -- warn on the empty one
                style = "border: 1px solid rgb(200, 160, 40);"
                if empty_a:
                    qa.setStyleSheet(style)
                else:
                    qb.setStyleSheet(style)
            else:
                # Both set or both empty -- clear any warning
                qa.setStyleSheet("")
                qb.setStyleSheet("")

    # -- Variable override helpers -------------------------------------------

    def disable_field(self, field_name: str) -> None:
        """Gray out a field widget (variable node connected).

        No-op if the field name does not match any widget.
        """
        widget_item = self.get_widget(field_name)
        if widget_item is None:
            return
        qt_widget = widget_item.get_custom_widget()
        if qt_widget is not None:
            qt_widget.setEnabled(False)

    def enable_field(self, field_name: str) -> None:
        """Re-enable a field widget (variable node disconnected).

        No-op if the field name does not match any widget.
        """
        widget_item = self.get_widget(field_name)
        if widget_item is None:
            return
        qt_widget = widget_item.get_custom_widget()
        if qt_widget is not None:
            qt_widget.setEnabled(True)

    # -- Custom widget helpers ----------------------------------------------

    def add_int_edit(
        self,
        name: str,
        label: str = "",
        value: int = 0,
        min_value: int = 0,
        max_value: int = 99,
    ) -> None:
        """Add a ``NodeIntEdit`` widget (replaces ``add_spinbox``).

        Uses explicit -/+ buttons instead of QSpinBox to avoid the
        QGraphicsProxyWidget hit-testing bug with arrow buttons.

        The ``parent=self.view`` argument is critical: NodeGraphQt's
        built-in widgets (NodeLineEdit, NodeComboBox, etc.) receive
        ``self.view`` (the NodeItem QGraphicsItem) as their parent in
        their constructors. Without this, the QGraphicsProxyWidget is
        a rootless orphan in the scene graph and never renders.
        """
        widget = NodeIntEdit(
            parent=self.view,
            name=name,
            label=label,
            value=value,
            min_value=min_value,
            max_value=max_value,
        )
        self.add_custom_widget(widget)

    def add_float_edit(
        self,
        name: str,
        label: str = "",
        value: float = 0.0,
        min_value: float = 0.0,
        max_value: float = 99999.0,
        step: float = 10.0,
    ) -> None:
        """Add a ``NodeFloatEdit`` widget for float properties.

        Same parent-passing requirement as ``add_int_edit`` -- see its docstring.
        """
        widget = NodeFloatEdit(
            parent=self.view,
            name=name,
            label=label,
            value=value,
            min_value=min_value,
            max_value=max_value,
            step=step,
        )
        self.add_custom_widget(widget)


    # -- Ingredient port label helpers ----------------------------------------

    def _set_ingredient_port_label(self, port: object, label: str) -> None:
        """Set the visible text of an ingredient input port."""
        port_item = port.view  # type: ignore[attr-defined]
        node_item = self.view
        text_item = node_item.get_input_text_item(port_item)
        if text_item is not None:
            text_item.setPlainText(label)

    def update_ingredient_labels(self) -> None:
        """Refresh all ingredient port labels from connected nodes."""
        for port in self.input_ports():
            if not port.name().startswith("ingredient_"):
                continue
            connected = port.connected_ports()
            if connected:
                src_node = connected[0].node()
                item_id = getattr(getattr(src_node, "model_ref", None), "item_id", None)
                if item_id:
                    self._set_ingredient_port_label(port, _to_pascal_case(item_id))
                    continue
                if hasattr(src_node, "name"):
                    self._set_ingredient_port_label(port, _to_pascal_case(src_node.name()))
                    continue
            self._set_ingredient_port_label(port, "")


# ---------------------------------------------------------------------------
# Recipe nodes
# ---------------------------------------------------------------------------


class ModifiedRecipeNode(CraftGraphBaseNode):
    """Visual node for a ModifiedRecipe."""

    NODE_NAME = "Modified Recipe"
    NODE_COLOR = NODE_COLOR_MODIFIED_RECIPE

    FIELD_REGISTRY = [
        FieldPin("item_id", PinType.STRING, label="ItemID", required=True,
                 help_text="TechType ID (case-insensitive)"),
        FieldPin("amount_crafted", PinType.INT, label="Amount", default=1, min_val=0, max_val=99,
                 help_text="Number produced per craft"),
        FieldPin("ingredients", PinType.INGREDIENT_LIST, label="Ingredients"),
        FieldPin("linked_item_ids", PinType.CSV, label="Linked IDs",
                 help_text="TechType IDs to link with (comma-separated)"),
        FieldPin("unlocks", PinType.CSV, label="Unlocks",
                 help_text="Crafting this unlocks ALL listed TechType IDs"),
        FieldPin("unlocked_by", PinType.CSV, label="Unlocked By",
                 help_text="Unlocks when ANY ONE of these is scanned"),
        FieldPin(
            "force_unlock_at_start",
            PinType.ENUM,
            label="Force Unlock",
            nullable=True,
            enum_items=["auto", "YES", "NO"],
            help_text="Make available without scanning",
        ),
    ]

    OUTPUT_PINS = [
        OutputPin("output", label="ItemID", multi=True, pin_color=PORT_COLOR_OUTPUT),
    ]

    def __init__(self) -> None:
        super().__init__()

        # Structural ports (not registry-driven)
        self.add_input("hierarchy", multi_input=False, color=PORT_COLOR_HIERARCHY)
        self.add_input("ingredient_0", multi_input=False, color=PORT_COLOR_INGREDIENT)
        _add_hierarchy_accept_constraints(self, "hierarchy")

    # -- dynamic ingredient slots ------------------------------------------

    def _ingredient_port_count(self) -> int:
        """Count current ingredient input ports."""
        return len([p for p in self.input_ports() if p.name().startswith("ingredient_")])

    def on_input_connected(self, in_port, out_port) -> None:  # type: ignore[override]
        """Spawn a new empty ingredient slot when one is filled."""
        if not in_port.name().startswith("ingredient_"):
            return
        # NodeGraphQt's _deserialize fires on_input_connected unconditionally
        # during paste/duplicate, even when allow_connection rejected the
        # restoration.  Verify the connection is real before spawning a slot.
        if out_port not in in_port.connected_ports():
            return
        idx = self._ingredient_port_count()
        self.add_input(
            f"ingredient_{idx}",
            multi_input=False,
            color=PORT_COLOR_INGREDIENT,
        )
        self._label_ingredient_port(in_port, out_port)

    def on_input_disconnected(self, in_port, out_port) -> None:  # type: ignore[override]
        """Remove redundant trailing empty ingredient slots on disconnect.

        Keeps exactly one trailing empty slot so a "next available" pin always
        exists for new ingredient connections.
        """
        if not in_port.name().startswith("ingredient_"):
            return
        self._set_ingredient_port_label(in_port, "")
        ing_ports = [p for p in self.input_ports() if p.name().startswith("ingredient_")]
        # Pop only when there are 2+ trailing empties, preserving one as the
        # next-slot placeholder.
        while (
            len(ing_ports) > 1
            and not ing_ports[-1].connected_ports()
            and not ing_ports[-2].connected_ports()
        ):
            self.delete_input(ing_ports.pop())

    def _label_ingredient_port(self, in_port: object, out_port: object) -> None:
        """Set the ingredient port label from the source node's item ID."""
        src_node = out_port.node()  # type: ignore[attr-defined]
        item_id = getattr(getattr(src_node, "model_ref", None), "item_id", None)
        label = _to_pascal_case(item_id) if item_id else _to_pascal_case(src_node.name())
        self._set_ingredient_port_label(in_port, label)


class AddedRecipeNode(ModifiedRecipeNode):
    """Visual node for an AddedRecipe."""

    NODE_NAME = "Added Recipe"
    NODE_COLOR = NODE_COLOR_ADDED_RECIPE

    FIELD_REGISTRY = ModifiedRecipeNode.FIELD_REGISTRY + [
        FieldPin(
            "path", PinType.STRING, label="Path", required=True, preferred_var_kind="PathVar",
            help_text="Crafting tree path (e.g. Fabricator/Resources)",
        ),
        FieldPin(
            "pda_group",
            PinType.ENUM,
            label="PDA Group",
            nullable=True,
            help_text="PDA encyclopedia group",
            enum_items=["", *TECH_GROUPS],
        ),
        FieldPin(
            "pda_category",
            PinType.ENUM,
            label="PDA Category",
            nullable=True,
            help_text="PDA encyclopedia category",
            enum_items=["", *TECH_CATEGORIES],
        ),
    ]
    PAIRED_FIELDS = [("pda_group", "pda_category")]


class AliasRecipeNode(AddedRecipeNode):
    """Visual node for an AliasRecipe."""

    NODE_NAME = "Alias Recipe"
    NODE_COLOR = NODE_COLOR_ALIAS_RECIPE
    HAS_SPRITE_PORT = True

    FIELD_REGISTRY = AddedRecipeNode.FIELD_REGISTRY + [
        FieldPin("display_name", PinType.STRING, label="Display Name",
                 help_text="In-game display name (quoted in .txt)"),
        FieldPin("tooltip", PinType.STRING, label="Tooltip",
                 help_text="In-game item description (quoted in .txt)"),
        FieldPin("functional_id", PinType.STRING, label="Functional ID", nullable=True,
                 help_text="Existing TechType to clone behavior from"),
        FieldPin("sprite_item_id", PinType.STRING, label="Sprite ID", nullable=True,
                 help_text="Existing TechType for inventory icon"),
    ]


class CustomFoodNode(AliasRecipeNode):
    """Visual node for a CustomFood."""

    NODE_NAME = "Custom Food"
    NODE_COLOR = NODE_COLOR_CUSTOM_FOOD

    FIELD_REGISTRY = AliasRecipeNode.FIELD_REGISTRY + [
        FieldPin("food_value", PinType.INT, label="Food", default=0, min_val=-200, max_val=200,
                 help_text="Nutrition value (-200 to +200)"),
        FieldPin("water_value", PinType.INT, label="Water", default=0, min_val=-200, max_val=200,
                 help_text="Hydration value (-200 to +200)"),
        FieldPin("oxygen_value", PinType.INT, label="Oxygen", default=0, min_val=-200, max_val=200,
                 help_text="Oxygen restoration (-200 to +200)"),
        FieldPin("health_value", PinType.INT, label="Health", default=0, min_val=-200, max_val=200,
                 help_text="Health restoration (-200 to +200)"),
        FieldPin(
            "decay_rate_mod",
            PinType.FLOAT,
            label="Decay Rate",
            default=0.0,
            min_val=0.0,
            max_val=100.0,
            step=0.1,
            help_text="Decay rate multiplier (0 = no decay)",
        ),
        FieldPin(
            "food_type",
            PinType.ENUM,
            label="Food Type",
            nullable=True,
            help_text="Food category model",
            enum_items=["", *FOOD_MODELS],
        ),
        FieldPin(
            "use_drink_sound",
            PinType.ENUM,
            label="Drink Sound",
            nullable=True,
            enum_items=["auto", "YES", "NO"],
            help_text="Play drink sound when consumed",
        ),
    ]


# ---------------------------------------------------------------------------
# Container nodes
# ---------------------------------------------------------------------------


class FabricatorNode(CraftGraphBaseNode):
    """Visual node for a CustomFabricator."""

    NODE_NAME = "Fabricator"
    NODE_COLOR = NODE_COLOR_FABRICATOR
    SPLIT_OUTPUTS = True

    FIELD_REGISTRY = [
        FieldPin("item_id", PinType.STRING, label="ItemID", required=True,
                 help_text="TechType ID (case-insensitive)"),
        FieldPin("display_name", PinType.STRING, label="Display Name",
                 help_text="In-game display name (quoted in .txt)"),
        FieldPin("tooltip", PinType.STRING, label="Tooltip",
                 help_text="In-game item description (quoted in .txt)"),
        FieldPin(
            "model",
            PinType.ENUM,
            label="Model",
            enum_items=list(FABRICATOR_MODELS),
            help_text="Fabricator visual model (MoonPool is SN1 only)",
        ),
        FieldPin("color_tint", PinType.CSV, label="Color Tint", preferred_var_kind="ColorVar",
                 help_text="RGB(A) color tint, each 0.0-1.0"),
        FieldPin("allowed_in_base", PinType.BOOL, label="In Base", default=True,
                 help_text="Can be built in base"),
        FieldPin("allowed_in_cyclops", PinType.BOOL, label="In Cyclops", default=True,
                 help_text="Can be built in Cyclops"),
        FieldPin(
            "pda_group",
            PinType.ENUM,
            label="PDA Group",
            nullable=True,
            help_text="PDA encyclopedia group",
            enum_items=["", *TECH_GROUPS],
        ),
        FieldPin(
            "pda_category",
            PinType.ENUM,
            label="PDA Category",
            nullable=True,
            help_text="PDA encyclopedia category",
            enum_items=["", *TECH_CATEGORIES],
        ),
        FieldPin(
            "force_unlock_at_start",
            PinType.ENUM,
            label="Force Unlock",
            nullable=True,
            enum_items=["auto", "YES", "NO"],
            help_text="Make available without scanning",
        ),
        FieldPin("unlocked_by", PinType.CSV, label="Unlocked By",
                 help_text="Unlocks when ANY ONE of these is scanned"),
        FieldPin("ingredients", PinType.INGREDIENT_LIST, label="Ingredients"),
    ]
    PAIRED_FIELDS = [("pda_group", "pda_category")]

    OUTPUT_PINS = [
        OutputPin("tabs_out", label="Tabs", pin_color=PORT_COLOR_CHILDREN),
        OutputPin("added_out", label="Added", pin_color=PORT_COLOR_CHILDREN),
        OutputPin("alias_out", label="Alias", pin_color=PORT_COLOR_CHILDREN),
        OutputPin("foods_out", label="Foods", pin_color=PORT_COLOR_CHILDREN),
        OutputPin("moved_out", label="Moved", pin_color=PORT_COLOR_CHILDREN),
    ]

    def __init__(self) -> None:
        super().__init__()

        # Ingredient input port (fabricators can require ingredients to build)
        self.add_input("ingredient_0", multi_input=False, color=PORT_COLOR_INGREDIENT)

        if self.SPLIT_OUTPUTS:
            # Set accept constraints so typed outputs only connect to correct child types
            tabs_port = self.get_output("tabs_out")
            added_port = self.get_output("added_out")
            alias_port = self.get_output("alias_out")
            foods_port = self.get_output("foods_out")
            moved_port = self.get_output("moved_out")

            if tabs_port:
                tabs_port.add_accept_port_type(
                    port_name="parent",
                    port_type="in",
                    node_type="com.craftgraph.CraftingTabNode",
                )
            if added_port:
                added_port.add_accept_port_type(
                    port_name="hierarchy",
                    port_type="in",
                    node_type="com.craftgraph.AddedRecipeNode",
                )
            if alias_port:
                alias_port.add_accept_port_type(
                    port_name="hierarchy",
                    port_type="in",
                    node_type="com.craftgraph.AliasRecipeNode",
                )
            if foods_port:
                foods_port.add_accept_port_type(
                    port_name="hierarchy",
                    port_type="in",
                    node_type="com.craftgraph.CustomFoodNode",
                )
            if moved_port:
                moved_port.add_accept_port_type(
                    port_name="hierarchy",
                    port_type="in",
                    node_type="com.craftgraph.MovedRecipeNode",
                )

    # -- dynamic ingredient slots ----------------------------------------------

    def _ingredient_port_count(self) -> int:
        """Count current ingredient input ports."""
        return len([p for p in self.input_ports() if p.name().startswith("ingredient_")])

    def on_input_connected(self, in_port, out_port) -> None:  # type: ignore[override]
        """Spawn a new empty ingredient slot when one is filled."""
        if not in_port.name().startswith("ingredient_"):
            return
        # NodeGraphQt's _deserialize fires on_input_connected unconditionally
        # during paste/duplicate, even when allow_connection rejected the
        # restoration.  Verify the connection is real before spawning a slot.
        if out_port not in in_port.connected_ports():
            return
        idx = self._ingredient_port_count()
        self.add_input(
            f"ingredient_{idx}",
            multi_input=False,
            color=PORT_COLOR_INGREDIENT,
        )
        self._label_ingredient_port(in_port, out_port)

    def on_input_disconnected(self, in_port, out_port) -> None:  # type: ignore[override]
        """Remove redundant trailing empty ingredient slots on disconnect.

        Keeps exactly one trailing empty slot so a "next available" pin always
        exists for new ingredient connections.
        """
        if not in_port.name().startswith("ingredient_"):
            return
        self._set_ingredient_port_label(in_port, "")
        ing_ports = [p for p in self.input_ports() if p.name().startswith("ingredient_")]
        while (
            len(ing_ports) > 1
            and not ing_ports[-1].connected_ports()
            and not ing_ports[-2].connected_ports()
        ):
            self.delete_input(ing_ports.pop())

    def _label_ingredient_port(self, in_port: object, out_port: object) -> None:
        """Set the ingredient port label from the source node's item ID."""
        src_node = out_port.node()  # type: ignore[attr-defined]
        item_id = getattr(getattr(src_node, "model_ref", None), "item_id", None)
        label = _to_pascal_case(item_id) if item_id else _to_pascal_case(src_node.name())
        self._set_ingredient_port_label(in_port, label)


class CraftingTabNode(CraftGraphBaseNode):
    """Visual node for a CraftingTab."""

    NODE_NAME = "Crafting Tab"
    NODE_COLOR = NODE_COLOR_CRAFTING_TAB
    HAS_SPRITE_PORT = True

    FIELD_REGISTRY = [
        FieldPin("tab_id", PinType.STRING, label="TabID", required=True,
                 help_text="Unique tab identifier within fabricator"),
        FieldPin("display_name", PinType.STRING, label="Display Name",
                 help_text="Tab display name in crafting menu"),
        FieldPin("sprite_item_id", PinType.STRING, label="Sprite ID", nullable=True,
                 help_text="Existing TechType for tab icon"),
        FieldPin(
            "parent_tab_path", PinType.STRING, label="Parent Path", preferred_var_kind="PathVar",
            help_text="Parent tab path in fabricator tree",
        ),
    ]

    OUTPUT_PINS = [
        OutputPin("children", label="Children", pin_color=PORT_COLOR_CHILDREN),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.add_input("parent", multi_input=False, color=PORT_COLOR_HIERARCHY)
        _add_hierarchy_accept_constraints(self, "parent")


class CustomSizeNode(CraftGraphBaseNode):
    """Visual node for a CustomSize entry."""

    NODE_NAME = "Custom Size"
    NODE_COLOR = NODE_COLOR_CUSTOM_SIZE

    FIELD_REGISTRY = [
        FieldPin("item_id", PinType.STRING, label="ItemID", required=True,
                 help_text="TechType ID (case-insensitive)"),
        FieldPin(
            "size_width",
            PinType.INT,
            label="Width",
            default=1,
            min_val=1,
            max_val=6,
            model_field="width",
            help_text="Inventory slot width (1-6)",
        ),
        FieldPin(
            "size_height",
            PinType.INT,
            label="Height",
            default=1,
            min_val=1,
            max_val=6,
            model_field="height",
            help_text="Inventory slot height (1-6)",
        ),
    ]


class MovedRecipeNode(CraftGraphBaseNode):
    """Visual node for a MovedRecipe directive."""

    NODE_NAME = "Moved Recipe"
    NODE_COLOR = NODE_COLOR_MOVED_RECIPE

    FIELD_REGISTRY = [
        FieldPin("item_id", PinType.STRING, label="ItemID", required=True,
                 help_text="TechType ID of recipe to move"),
        FieldPin(
            "old_path",
            PinType.STRING,
            label="Old Path",
            nullable=True,
            preferred_var_kind="PathVar",
            help_text="Original crafting tree path",
        ),
        FieldPin(
            "new_path",
            PinType.STRING,
            label="New Path",
            nullable=True,
            preferred_var_kind="PathVar",
            help_text="Destination crafting tree path",
        ),
        FieldPin("copied", PinType.BOOL, label="Copied", default=False,
                 help_text="Copy instead of move (keeps original)"),
        FieldPin("hidden", PinType.BOOL, label="Hidden", default=False,
                 help_text="Hide recipe from crafting menu"),
    ]
    MUTUAL_EXCLUSIONS = [("copied", "hidden")]


class CustomBioFuelNode(CraftGraphBaseNode):
    """Visual node for a CustomBioFuel entry."""

    NODE_NAME = "Custom BioFuel"
    NODE_COLOR = NODE_COLOR_CUSTOM_BIO_FUEL

    FIELD_REGISTRY = [
        FieldPin("item_id", PinType.STRING, label="ItemID", required=True,
                 help_text="TechType ID (case-insensitive)"),
        FieldPin(
            "energy",
            PinType.FLOAT,
            label="Energy",
            default=0.0,
            min_val=0.0,
            max_val=99999.0,
            step=10.0,
            help_text="Bioreactor energy value",
        ),
    ]


class CustomFragmentCountNode(CraftGraphBaseNode):
    """Visual node for a CustomFragmentCount entry."""

    NODE_NAME = "Custom Fragment Count"
    NODE_COLOR = NODE_COLOR_CUSTOM_FRAGMENT_COUNT

    FIELD_REGISTRY = [
        FieldPin("item_id", PinType.STRING, label="ItemID", required=True,
                 help_text="TechType ID (case-insensitive)"),
        FieldPin(
            "fragments_to_scan", PinType.INT, label="Fragments", default=1, min_val=1, max_val=30,
            help_text="Number of fragments needed to unlock",
        ),
    ]


# ---------------------------------------------------------------------------
# Orphan ingredient node (visual-only, not model-backed)
# ---------------------------------------------------------------------------


class OrphanIngredientNode(CraftGraphBaseNode):
    """Visual-only ingredient node not backed by the data model."""

    NODE_NAME = "Orphan Ingredient"
    NODE_COLOR = NODE_COLOR_ORPHAN_INGREDIENT
    IS_ORPHAN: bool = True

    FIELD_REGISTRY = [
        FieldPin("item_id", PinType.STRING, label="ItemID"),
    ]

    OUTPUT_PINS = [
        OutputPin("output", multi=True, pin_color=PORT_COLOR_OUTPUT),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._node_uuid: str = uuid.uuid4().hex[:8]


class _BrowseButtonWidget(NodeBaseWidget):
    """A "Browse..." button that opens a file dialog for PNG selection.

    Remembers the last-used directory across clicks for convenience.
    """

    _last_dir: str = ""

    def __init__(
        self,
        parent: object = None,
        name: str = "",
        label: str = "",
    ) -> None:
        super().__init__(parent, name, label)
        self.setZValue(Z_VAL_NODE_WIDGET + 1)
        btn = QPushButton("Browse...")
        btn.setMaximumWidth(140)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.clicked.connect(self._open_dialog)
        self.set_custom_widget(btn)

    @property
    def type_(self) -> str:  # type: ignore[override]
        return "BrowseButtonNodeWidget"

    def get_value(self) -> str:
        return ""

    def set_value(self, value: str = "") -> None:
        pass  # Read-only button, no stored value

    def _open_dialog(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Select Sprite Image",
            _BrowseButtonWidget._last_dir,
            "PNG Files (*.png)",
        )
        if not file_path:
            return
        _BrowseButtonWidget._last_dir = str(Path(file_path).parent)
        # Walk up to the owning node and set its file_path property
        node = self.node
        if node is not None:
            node.set_property("file_path", file_path)


class SpriteNode(CraftGraphBaseNode):
    """A node that holds a sprite image reference."""

    NODE_NAME = "Sprite"
    NODE_COLOR = NODE_COLOR_SPRITE

    FIELD_REGISTRY = [
        FieldPin("file_path", PinType.STRING, label="File"),
    ]

    OUTPUT_PINS = [
        OutputPin("sprite_out", multi=True, pin_color=PORT_COLOR_SPRITE),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._node_uuid: str = uuid.uuid4().hex[:8]

        # Self-preview: update header icon when file_path changes
        widget_item = self.get_widget("file_path")
        if widget_item is not None:
            qt_widget = widget_item.get_custom_widget()
            if isinstance(qt_widget, QLineEdit):
                qt_widget.textChanged.connect(self._on_file_path_changed)

        # Browse button for file picker
        browse = _BrowseButtonWidget(
            parent=self.view,
            name="browse_file",
            label="",
        )
        self.add_custom_widget(browse)
        self._fix_widget_z_order()

    def _on_file_path_changed(self, text: str) -> None:
        """React to file_path text changes by updating the header icon."""
        if not text.strip():
            self.clear_sprite()
            self._propagate_sprite(None)
            return
        path = Path(text)
        self.set_sprite(path)
        self._propagate_sprite(path)

    def _propagate_sprite(self, path: Path | None) -> None:
        """Push the current sprite to all nodes connected via sprite_out."""
        out_port = self.get_output("sprite_out")
        if out_port is None:
            return
        for connected_port in out_port.connected_ports():
            target = connected_port.node()
            if path is not None and path.exists():
                target.set_sprite(path)
                # Update the sprite_item_id model field (e.g. for CraftingTab,
                # AliasRecipe) so the value gets serialized to the .txt file.
                if target.get_widget("sprite_item_id") is not None:
                    target.set_property("sprite_item_id", path.stem)
            else:
                target.clear_sprite()
                if target.get_widget("sprite_item_id") is not None:
                    target.set_property("sprite_item_id", "")


# ---------------------------------------------------------------------------
# Node registry
# ---------------------------------------------------------------------------


class NodeKind(Enum):
    """Visual node types available in CraftGraph's Qt node editor."""

    MODIFIED_RECIPE = "ModifiedRecipe"
    ADDED_RECIPE = "AddedRecipe"
    ALIAS_RECIPE = "AliasRecipe"
    CUSTOM_FOOD = "CustomFood"
    FABRICATOR = "Fabricator"
    CRAFTING_TAB = "CraftingTab"
    CUSTOM_SIZE = "CustomSize"
    MOVED_RECIPE = "MovedRecipe"
    CUSTOM_BIO_FUEL = "CustomBioFuel"
    CUSTOM_FRAGMENT_COUNT = "CustomFragmentCount"
    ORPHAN_INGREDIENT = "OrphanIngredient"
    SPRITE = "Sprite"


# Maps NodeKind -> concrete BaseNode subclass for factory instantiation.
NODE_REGISTRY: dict[NodeKind, type[CraftGraphBaseNode]] = {
    NodeKind.MODIFIED_RECIPE: ModifiedRecipeNode,
    NodeKind.ADDED_RECIPE: AddedRecipeNode,
    NodeKind.ALIAS_RECIPE: AliasRecipeNode,
    NodeKind.CUSTOM_FOOD: CustomFoodNode,
    NodeKind.FABRICATOR: FabricatorNode,
    NodeKind.CRAFTING_TAB: CraftingTabNode,
    NodeKind.CUSTOM_SIZE: CustomSizeNode,
    NodeKind.MOVED_RECIPE: MovedRecipeNode,
    NodeKind.CUSTOM_BIO_FUEL: CustomBioFuelNode,
    NodeKind.CUSTOM_FRAGMENT_COUNT: CustomFragmentCountNode,
    NodeKind.ORPHAN_INGREDIENT: OrphanIngredientNode,
    NodeKind.SPRITE: SpriteNode,
}


def all_node_classes() -> list[type[CraftGraphBaseNode]]:
    """Return every concrete node class for graph.register_node() calls."""
    return list(NODE_REGISTRY.values())


# Maps each concrete node class to the ``NodeColors`` field name that drives
# its fill color.  Used by the host window's theme-apply path so node header
# colors update live when the user changes them in the Settings dialog.
NODE_COLOR_FIELD_FOR_CLASS: dict[type[CraftGraphBaseNode], str] = {
    ModifiedRecipeNode: "modified_recipe",
    AddedRecipeNode: "added_recipe",
    AliasRecipeNode: "alias_recipe",
    CustomFoodNode: "custom_food",
    FabricatorNode: "fabricator",
    CraftingTabNode: "crafting_tab",
    CustomSizeNode: "custom_size",
    MovedRecipeNode: "moved_recipe",
    CustomBioFuelNode: "custom_bio_fuel",
    CustomFragmentCountNode: "custom_fragment_count",
    OrphanIngredientNode: "orphan_ingredient",
    SpriteNode: "sprite",
}
