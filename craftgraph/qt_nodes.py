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

from craftgraph.pin_registry import (
    FieldPin,
    OutputPin,
    PinType,
    convert_to_display,
    convert_to_model,
)
from NodeGraphQt import BaseNode
from NodeGraphQt.constants import PortTypeEnum, ViewerEnum, Z_VAL_NODE_WIDGET
from NodeGraphQt.widgets.node_widgets import NodeBaseWidget, _NodeGroupBox
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget

if TYPE_CHECKING:
    from craftgraph.commands import EditHistory

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IDENTIFIER = "com.craftgraph"
SPRITE_SIZE = 64

# Port colors (R, G, B)
PORT_COLOR_HIERARCHY = (200, 200, 100)
PORT_COLOR_OUTPUT = (100, 200, 100)
PORT_COLOR_INGREDIENT = (180, 80, 0)
PORT_COLOR_CHILDREN = (100, 100, 220)

# Node colors by category
NODE_COLOR_MODIFIED_RECIPE = (60, 120, 80)
NODE_COLOR_ADDED_RECIPE = (60, 140, 80)
NODE_COLOR_ALIAS_RECIPE = (80, 120, 120)
NODE_COLOR_CUSTOM_FOOD = (120, 100, 60)
NODE_COLOR_FABRICATOR = (80, 80, 160)
NODE_COLOR_CRAFTING_TAB = (160, 120, 40)
NODE_COLOR_CUSTOM_SIZE = (100, 100, 100)
NODE_COLOR_MOVED_RECIPE = (120, 80, 120)
NODE_COLOR_CUSTOM_BIO_FUEL = (140, 100, 40)
NODE_COLOR_CUSTOM_FRAGMENT_COUNT = (80, 100, 140)
NODE_COLOR_ORPHAN_INGREDIENT = (90, 90, 90)
NODE_COLOR_SPRITE = (180, 160, 60)

PORT_COLOR_SPRITE = (180, 160, 60)
PORT_COLOR_VARIABLE = (100, 70, 130)

# Stylesheet fragments for required-field validation highlighting.
_REQUIRED_EMPTY_STYLE = "border: 1px solid rgb(200, 60, 60);"
_REQUIRED_VALID_STYLE = "border: none;"


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
            " font-size: 11pt; font-weight: bold; }}"
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
            " font-size: 11pt; font-weight: bold; }}"
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
    HAS_SPRITE_PORT: bool = True
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

        self.set_color(*self.NODE_COLOR)
        if self.HAS_SPRITE_PORT:
            self.add_input("sprite_in", multi_input=False, color=PORT_COLOR_SPRITE)
        self._build_from_registry()
        self._build_outputs()
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

    def set_sprite(self, path: Path | None) -> None:
        """Set a sprite image on this node at SPRITE_SIZE pixels.

        Bypasses NodeGraphQt's built-in 18px icon scaling by setting
        the pixmap directly on the view's QGraphicsPixmapItem.

        If *path* is None or does not exist, clears the sprite.
        """
        if path is None or not path.exists():
            self.clear_sprite()
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.clear_sprite()
            return
        pixmap = pixmap.scaled(
            SPRITE_SIZE,
            SPRITE_SIZE,
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

    def _build_outputs(self) -> None:
        """Create output ports from OUTPUT_PINS declarations."""
        for op in self.OUTPUT_PINS:
            self.add_output(op.name, multi_output=op.multi, color=op.pin_color)

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


# ---------------------------------------------------------------------------
# Recipe nodes
# ---------------------------------------------------------------------------


class ModifiedRecipeNode(CraftGraphBaseNode):
    """Visual node for a ModifiedRecipe."""

    NODE_NAME = "Modified Recipe"
    NODE_COLOR = NODE_COLOR_MODIFIED_RECIPE

    FIELD_REGISTRY = [
        FieldPin("item_id", PinType.STRING, label="ItemID", required=True),
        FieldPin("amount_crafted", PinType.INT, label="Amount", default=1, min_val=0, max_val=99),
        FieldPin("ingredients", PinType.INGREDIENT_LIST, label="Ingredients"),
        FieldPin("linked_item_ids", PinType.CSV, label="Linked IDs"),
        FieldPin("unlocks", PinType.CSV, label="Unlocks"),
        FieldPin("unlocked_by", PinType.CSV, label="Unlocked By"),
        FieldPin(
            "force_unlock_at_start",
            PinType.ENUM,
            label="Force Unlock",
            nullable=True,
            enum_items=["auto", "YES", "NO"],
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
        if in_port.name().startswith("ingredient_"):
            idx = self._ingredient_port_count()
            self.add_input(
                f"ingredient_{idx}",
                multi_input=False,
                color=PORT_COLOR_INGREDIENT,
            )

    def on_input_disconnected(self, in_port, out_port) -> None:  # type: ignore[override]
        """Remove trailing empty ingredient slots on disconnect."""
        if not in_port.name().startswith("ingredient_"):
            return
        # Collect ingredient ports, remove empty ones from the tail
        ing_ports = [p for p in self.input_ports() if p.name().startswith("ingredient_")]
        while len(ing_ports) > 1 and not ing_ports[-1].connected_ports():
            self.delete_input(ing_ports.pop())


class AddedRecipeNode(ModifiedRecipeNode):
    """Visual node for an AddedRecipe."""

    NODE_NAME = "Added Recipe"
    NODE_COLOR = NODE_COLOR_ADDED_RECIPE

    FIELD_REGISTRY = ModifiedRecipeNode.FIELD_REGISTRY + [
        FieldPin(
            "path", PinType.STRING, label="Path", required=True, preferred_var_kind="PathVar"
        ),
        FieldPin(
            "pda_group",
            PinType.ENUM,
            label="PDA Group",
            nullable=True,
            enum_items=[
                "",
                "Uncategorized",
                "Resources",
                "Survival",
                "Personal",
                "Machines",
                "InteriorModules",
                "InteriorPieces",
                "ExteriorModules",
                "BasePieces",
                "Cyclops",
                "Constructor",
                "Miscellaneous",
                "VehicleUpgrades",
                "MapRoomUpgrades",
            ],
        ),
        FieldPin(
            "pda_category",
            PinType.ENUM,
            label="PDA Category",
            nullable=True,
            enum_items=[
                "",
                "Misc",
                "BasicMaterials",
                "AdvancedMaterials",
                "Electronics",
                "Water",
                "CookedFood",
                "CuredFood",
                "FoodAndDrinks",
                "Equipment",
                "Tools",
                "Machines",
                "InteriorModule",
                "InteriorPiece",
                "ExteriorModule",
                "BasePiece",
                "BaseRoom",
                "BaseWall",
                "CyclopsUpgrades",
                "Constructor",
                "VehicleUpgrades",
                "MapRoomUpgrades",
                "Rocket",
                "Workbench",
            ],
        ),
    ]
    PAIRED_FIELDS = [("pda_group", "pda_category")]


class AliasRecipeNode(AddedRecipeNode):
    """Visual node for an AliasRecipe."""

    NODE_NAME = "Alias Recipe"
    NODE_COLOR = NODE_COLOR_ALIAS_RECIPE

    FIELD_REGISTRY = AddedRecipeNode.FIELD_REGISTRY + [
        FieldPin("display_name", PinType.STRING, label="Display Name"),
        FieldPin("tooltip", PinType.STRING, label="Tooltip"),
        FieldPin("functional_id", PinType.STRING, label="Functional ID", nullable=True),
        FieldPin("sprite_item_id", PinType.STRING, label="Sprite ID", nullable=True),
    ]


class CustomFoodNode(AliasRecipeNode):
    """Visual node for a CustomFood."""

    NODE_NAME = "Custom Food"
    NODE_COLOR = NODE_COLOR_CUSTOM_FOOD

    FIELD_REGISTRY = AliasRecipeNode.FIELD_REGISTRY + [
        FieldPin("food_value", PinType.INT, label="Food", default=0, min_val=-200, max_val=200),
        FieldPin("water_value", PinType.INT, label="Water", default=0, min_val=-200, max_val=200),
        FieldPin(
            "oxygen_value", PinType.INT, label="Oxygen", default=0, min_val=-200, max_val=200
        ),
        FieldPin(
            "health_value", PinType.INT, label="Health", default=0, min_val=-200, max_val=200
        ),
        FieldPin(
            "decay_rate_mod",
            PinType.FLOAT,
            label="Decay Rate",
            default=0.0,
            min_val=0.0,
            max_val=100.0,
            step=0.1,
        ),
        FieldPin(
            "food_type",
            PinType.ENUM,
            label="Food Type",
            nullable=True,
            enum_items=[
                "",
                "None",
                "BigFilteredWater",
                "DisinfectedWater",
                "FilteredWater",
                "WaterFiltrationSuitWater",
                "BulboTreePiece",
                "PurpleVegetable",
                "CreepvinePiece",
                "JellyPlant",
                "KooshChunk",
                "HangingFruit",
                "Melon",
                "NutrientBlock",
                "CookedPeeper",
                "CookedHoleFish",
                "CookedGarryFish",
                "CookedReginald",
                "CookedBladderfish",
                "CookedHoverfish",
                "CookedSpadefish",
                "CookedBoomerang",
                "CookedEyeye",
                "CookedOculus",
                "CookedHoopfish",
                "CookedSpinefish",
                "CookedLavaEyeye",
                "CookedLavaBoomerang",
                "CuredPeeper",
                "CuredHoleFish",
                "CuredGarryFish",
                "CuredReginald",
                "CuredBladderfish",
                "CuredHoverfish",
                "CuredSpadefish",
                "CuredBoomerang",
                "CuredEyeye",
                "CuredOculus",
                "CuredHoopfish",
                "CuredSpinefish",
                "CuredLavaEyeye",
                "CuredLavaBoomerang",
            ],
        ),
        FieldPin(
            "use_drink_sound",
            PinType.ENUM,
            label="Drink Sound",
            nullable=True,
            enum_items=["auto", "YES", "NO"],
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
        FieldPin("item_id", PinType.STRING, label="ItemID", required=True),
        FieldPin("display_name", PinType.STRING, label="Display Name"),
        FieldPin("tooltip", PinType.STRING, label="Tooltip"),
        FieldPin(
            "model",
            PinType.ENUM,
            label="Model",
            enum_items=["Fabricator", "Workbench", "MoonPool"],
        ),
        FieldPin("color_tint", PinType.CSV, label="Color Tint", preferred_var_kind="ColorVar"),
        FieldPin("allowed_in_base", PinType.BOOL, label="In Base", default=True),
        FieldPin("allowed_in_cyclops", PinType.BOOL, label="In Cyclops", default=True),
        FieldPin(
            "pda_group",
            PinType.ENUM,
            label="PDA Group",
            nullable=True,
            enum_items=[
                "",
                "Uncategorized",
                "Resources",
                "Survival",
                "Personal",
                "Machines",
                "InteriorModules",
                "InteriorPieces",
                "ExteriorModules",
                "BasePieces",
                "Cyclops",
                "Constructor",
                "Miscellaneous",
                "VehicleUpgrades",
                "MapRoomUpgrades",
            ],
        ),
        FieldPin(
            "pda_category",
            PinType.ENUM,
            label="PDA Category",
            nullable=True,
            enum_items=[
                "",
                "Misc",
                "BasicMaterials",
                "AdvancedMaterials",
                "Electronics",
                "Water",
                "CookedFood",
                "CuredFood",
                "FoodAndDrinks",
                "Equipment",
                "Tools",
                "Machines",
                "InteriorModule",
                "InteriorPiece",
                "ExteriorModule",
                "BasePiece",
                "BaseRoom",
                "BaseWall",
                "CyclopsUpgrades",
                "Constructor",
                "VehicleUpgrades",
                "MapRoomUpgrades",
                "Rocket",
                "Workbench",
            ],
        ),
        FieldPin(
            "force_unlock_at_start",
            PinType.ENUM,
            label="Force Unlock",
            nullable=True,
            enum_items=["auto", "YES", "NO"],
        ),
        FieldPin("unlocked_by", PinType.CSV, label="Unlocked By"),
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


class CraftingTabNode(CraftGraphBaseNode):
    """Visual node for a CraftingTab."""

    NODE_NAME = "Crafting Tab"
    NODE_COLOR = NODE_COLOR_CRAFTING_TAB

    FIELD_REGISTRY = [
        FieldPin("tab_id", PinType.STRING, label="TabID", required=True),
        FieldPin("display_name", PinType.STRING, label="Display Name"),
        FieldPin("sprite_item_id", PinType.STRING, label="Sprite ID", nullable=True),
        FieldPin(
            "parent_tab_path", PinType.STRING, label="Parent Path", preferred_var_kind="PathVar"
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
        FieldPin("item_id", PinType.STRING, label="ItemID", required=True),
        FieldPin(
            "size_width",
            PinType.INT,
            label="Width",
            default=1,
            min_val=1,
            max_val=6,
            model_field="width",
        ),
        FieldPin(
            "size_height",
            PinType.INT,
            label="Height",
            default=1,
            min_val=1,
            max_val=6,
            model_field="height",
        ),
    ]


class MovedRecipeNode(CraftGraphBaseNode):
    """Visual node for a MovedRecipe directive."""

    NODE_NAME = "Moved Recipe"
    NODE_COLOR = NODE_COLOR_MOVED_RECIPE

    FIELD_REGISTRY = [
        FieldPin("item_id", PinType.STRING, label="ItemID", required=True),
        FieldPin(
            "old_path",
            PinType.STRING,
            label="Old Path",
            nullable=True,
            preferred_var_kind="PathVar",
        ),
        FieldPin(
            "new_path",
            PinType.STRING,
            label="New Path",
            nullable=True,
            preferred_var_kind="PathVar",
        ),
        FieldPin("copied", PinType.BOOL, label="Copied", default=False),
        FieldPin("hidden", PinType.BOOL, label="Hidden", default=False),
    ]
    MUTUAL_EXCLUSIONS = [("copied", "hidden")]


class CustomBioFuelNode(CraftGraphBaseNode):
    """Visual node for a CustomBioFuel entry."""

    NODE_NAME = "Custom BioFuel"
    NODE_COLOR = NODE_COLOR_CUSTOM_BIO_FUEL

    FIELD_REGISTRY = [
        FieldPin("item_id", PinType.STRING, label="ItemID", required=True),
        FieldPin(
            "energy",
            PinType.FLOAT,
            label="Energy",
            default=0.0,
            min_val=0.0,
            max_val=99999.0,
            step=10.0,
        ),
    ]


class CustomFragmentCountNode(CraftGraphBaseNode):
    """Visual node for a CustomFragmentCount entry."""

    NODE_NAME = "Custom Fragment Count"
    NODE_COLOR = NODE_COLOR_CUSTOM_FRAGMENT_COUNT

    FIELD_REGISTRY = [
        FieldPin("item_id", PinType.STRING, label="ItemID", required=True),
        FieldPin(
            "fragments_to_scan", PinType.INT, label="Fragments", default=1, min_val=1, max_val=30
        ),
    ]


# ---------------------------------------------------------------------------
# Orphan ingredient node (visual-only, not model-backed)
# ---------------------------------------------------------------------------


class OrphanIngredientNode(CraftGraphBaseNode):
    """Visual-only ingredient node not backed by the data model."""

    NODE_NAME = "Orphan Ingredient"
    NODE_COLOR = NODE_COLOR_ORPHAN_INGREDIENT

    FIELD_REGISTRY = [
        FieldPin("item_id", PinType.STRING, label="ItemID"),
    ]

    OUTPUT_PINS = [
        OutputPin("output", multi=True, pin_color=PORT_COLOR_OUTPUT),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._node_uuid: str = uuid.uuid4().hex[:8]


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
