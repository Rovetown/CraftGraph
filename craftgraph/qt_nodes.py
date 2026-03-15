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
    Only FabricatorNode.children and CraftingTabNode.children are valid sources.
    """
    port = node.get_input(port_name)
    if port is None:
        return
    for node_type in (_FABRICATOR_TYPE, _CRAFTING_TAB_TYPE):
        node.add_accept_port_type(
            port,
            {
                "port_name": "children",
                "port_type": PortTypeEnum.OUT.value,
                "node_type": node_type,
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

    def __init__(self) -> None:
        super().__init__()
        self.set_port_deletion_allowed(True)
        self._model_ref: Any = None
        self._sprite_path: Path | None = None
        self._edit_history: EditHistory | None = None
        self._populating: bool = False

        self.set_color(*self.NODE_COLOR)
        self.add_input("sprite_in", multi_input=False, color=PORT_COLOR_SPRITE)
        self._build_from_registry()
        self._build_outputs()

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
            SPRITE_SIZE, SPRITE_SIZE,
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
        """Create widgets for all declared field pins."""
        for fp in self.FIELD_REGISTRY:
            if fp.pin_type == PinType.INGREDIENT_LIST:
                continue
            self._create_widget_for_field(fp)

    def _create_widget_for_field(self, fp: FieldPin) -> None:
        """Create the appropriate widget for a single field pin."""
        match fp.pin_type:
            case PinType.STRING | PinType.CSV:
                self.add_text_input(fp.name, label=fp.label, text=str(fp.default or ""))
            case PinType.INT:
                self.add_int_edit(
                    fp.name, label=fp.label,
                    value=fp.default if fp.default is not None else 0,
                    min_value=int(fp.min_val) if fp.min_val is not None else 0,
                    max_value=int(fp.max_val) if fp.max_val is not None else 99,
                )
            case PinType.FLOAT:
                self.add_float_edit(
                    fp.name, label=fp.label,
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
        widget = NodeIntEdit(parent=self.view, name=name, label=label,
                             value=value, min_value=min_value,
                             max_value=max_value)
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
        widget = NodeFloatEdit(parent=self.view, name=name, label=label,
                               value=value, min_value=min_value,
                               max_value=max_value, step=step)
        self.add_custom_widget(widget)


# ---------------------------------------------------------------------------
# Recipe nodes
# ---------------------------------------------------------------------------


class ModifiedRecipeNode(CraftGraphBaseNode):
    """Visual node for a ModifiedRecipe.

    Ports:
      - input ``hierarchy``: parent tab or fabricator
      - input ``ingredient_0..N``: dynamic ingredient slots
      - output ``output``: what this recipe produces

    Widgets:
      - ``item_id`` (text): the TechType ID
      - ``amount_crafted`` (spinbox): crafting yield
    """

    NODE_NAME = "Modified Recipe"

    def __init__(self) -> None:
        super().__init__()
        self.set_color(*NODE_COLOR_MODIFIED_RECIPE)

        self.add_output("output", multi_output=True, color=PORT_COLOR_OUTPUT)
        self.add_input("hierarchy", multi_input=False, color=PORT_COLOR_HIERARCHY)
        self.add_input("ingredient_0", multi_input=False, color=PORT_COLOR_INGREDIENT)

        _add_hierarchy_accept_constraints(self, "hierarchy")

        self.add_text_input("item_id", label="ItemID", text="")
        self.add_int_edit(
            "amount_crafted", label="Amount", value=1, min_value=0, max_value=99,
        )

    # -- dynamic ingredient slots ------------------------------------------

    def _ingredient_port_count(self) -> int:
        """Count current ingredient input ports."""
        return len(
            [p for p in self.input_ports() if p.name().startswith("ingredient_")]
        )

    def on_input_connected(self, in_port, out_port) -> None:  # type: ignore[override]
        """Spawn a new empty ingredient slot when one is filled."""
        if in_port.name().startswith("ingredient_"):
            idx = self._ingredient_port_count()
            self.add_input(
                f"ingredient_{idx}", multi_input=False, color=PORT_COLOR_INGREDIENT,
            )

    def on_input_disconnected(self, in_port, out_port) -> None:  # type: ignore[override]
        """Remove trailing empty ingredient slots on disconnect."""
        if not in_port.name().startswith("ingredient_"):
            return
        # Collect ingredient ports, remove empty ones from the tail
        ing_ports = [
            p for p in self.input_ports() if p.name().startswith("ingredient_")
        ]
        while len(ing_ports) > 1 and not ing_ports[-1].connected_ports():
            self.delete_input(ing_ports.pop())


class AddedRecipeNode(ModifiedRecipeNode):
    """Visual node for an AddedRecipe.

    Extends ModifiedRecipeNode with a ``path`` widget for the crafting
    tree placement (e.g. ``"Fabricator/Resources"``).
    """

    NODE_NAME = "Added Recipe"

    def __init__(self) -> None:
        super().__init__()
        self.set_color(*NODE_COLOR_ADDED_RECIPE)

        self.add_text_input("path", label="Path", text="")


class AliasRecipeNode(AddedRecipeNode):
    """Visual node for an AliasRecipe.

    Extends AddedRecipeNode with display_name and tooltip widgets.
    """

    NODE_NAME = "Alias Recipe"

    def __init__(self) -> None:
        super().__init__()
        self.set_color(*NODE_COLOR_ALIAS_RECIPE)

        self.add_text_input("display_name", label="Display Name", text="")
        self.add_text_input("tooltip", label="Tooltip", text="")


class CustomFoodNode(AliasRecipeNode):
    """Visual node for a CustomFood.

    Extends AliasRecipeNode with food/water/health stat spinboxes.
    """

    NODE_NAME = "Custom Food"

    def __init__(self) -> None:
        super().__init__()
        self.set_color(*NODE_COLOR_CUSTOM_FOOD)

        self.add_int_edit("food_value", label="Food", value=0, min_value=-100, max_value=100)
        self.add_int_edit("water_value", label="Water", value=0, min_value=-100, max_value=100)


# ---------------------------------------------------------------------------
# Container nodes
# ---------------------------------------------------------------------------


class FabricatorNode(CraftGraphBaseNode):
    """Visual node for a CustomFabricator.

    Ports:
      - output ``children``: tabs and recipes connect here as children

    Widgets:
      - ``item_id`` (text): fabricator TechType ID
      - ``display_name`` (text): in-game display name
      - ``model`` (combo): fabricator model type
    """

    NODE_NAME = "Fabricator"

    def __init__(self) -> None:
        super().__init__()
        self.set_color(*NODE_COLOR_FABRICATOR)

        self.add_output("children", multi_output=True, color=PORT_COLOR_CHILDREN)

        self.add_text_input("item_id", label="ItemID", text="")
        self.add_text_input("display_name", label="Display Name", text="")
        self.add_combo_menu(
            "model",
            label="Model",
            items=["Fabricator", "Workbench", "MoonPool"],
        )


class CraftingTabNode(CraftGraphBaseNode):
    """Visual node for a CraftingTab.

    Ports:
      - input ``parent``: parent fabricator or parent tab
      - output ``children``: child tabs or recipes connect here

    Widgets:
      - ``tab_id`` (text): tab identifier
      - ``display_name`` (text): in-game display name
    """

    NODE_NAME = "Crafting Tab"

    def __init__(self) -> None:
        super().__init__()
        self.set_color(*NODE_COLOR_CRAFTING_TAB)

        self.add_input("parent", multi_input=False, color=PORT_COLOR_HIERARCHY)
        self.add_output("children", multi_output=True, color=PORT_COLOR_CHILDREN)

        _add_hierarchy_accept_constraints(self, "parent")

        self.add_text_input("tab_id", label="TabID", text="")
        self.add_text_input("display_name", label="Display Name", text="")


class CustomSizeNode(CraftGraphBaseNode):
    """Visual node for a CustomSize entry.

    Widgets:
      - ``item_id`` (text): the TechType ID
      - ``size_width`` (int edit): inventory slot width (named to avoid NodeGraphQt reserved ``width``)
      - ``size_height`` (int edit): inventory slot height (named to avoid NodeGraphQt reserved ``height``)
    """

    NODE_NAME = "Custom Size"

    def __init__(self) -> None:
        super().__init__()
        self.set_color(*NODE_COLOR_CUSTOM_SIZE)

        self.add_text_input("item_id", label="ItemID", text="")
        self.add_int_edit("size_width", label="Width", value=1, min_value=1, max_value=6)
        self.add_int_edit("size_height", label="Height", value=1, min_value=1, max_value=6)


class MovedRecipeNode(CraftGraphBaseNode):
    """Visual node for a MovedRecipe directive.

    MovedRecipes relocate, copy, or hide existing recipe nodes in the
    crafting tree. They have no ingredient/output ports since they are
    purely organizational directives, not crafting recipes.

    Widgets:
      - ``item_id`` (text): the TechType being moved
      - ``old_path`` (text): original crafting tree path
      - ``new_path`` (text): destination crafting tree path
      - ``copied`` (checkbox): keep original or move
      - ``hidden`` (checkbox): hide from crafting menu
    """

    NODE_NAME = "Moved Recipe"

    def __init__(self) -> None:
        super().__init__()
        self.set_color(*NODE_COLOR_MOVED_RECIPE)

        self.add_text_input("item_id", label="ItemID", text="")
        self.add_text_input("old_path", label="Old Path", text="")
        self.add_text_input("new_path", label="New Path", text="")
        self.add_checkbox("copied", label="Copied", state=False)
        self.add_checkbox("hidden", label="Hidden", state=False)


class CustomBioFuelNode(CraftGraphBaseNode):
    """Visual node for a CustomBioFuel entry.

    Defines how much energy an item produces in a BioReactor.
    Standalone node with no ports.

    Widgets:
      - ``item_id`` (text): the TechType ID
      - ``energy`` (float edit): BioReactor energy value
    """

    NODE_NAME = "Custom BioFuel"

    def __init__(self) -> None:
        super().__init__()
        self.set_color(*NODE_COLOR_CUSTOM_BIO_FUEL)

        self.add_text_input("item_id", label="ItemID", text="")
        self.add_float_edit(
            "energy", label="Energy", value=0.0,
            min_value=0.0, max_value=99999.0, step=10.0,
        )


class CustomFragmentCountNode(CraftGraphBaseNode):
    """Visual node for a CustomFragmentCount entry.

    Defines how many fragments the player must scan to unlock a blueprint.
    Standalone node with no ports.

    Widgets:
      - ``item_id`` (text): the TechType ID
      - ``fragments_to_scan`` (int edit): number of fragments required
    """

    NODE_NAME = "Custom Fragment Count"

    def __init__(self) -> None:
        super().__init__()
        self.set_color(*NODE_COLOR_CUSTOM_FRAGMENT_COUNT)

        self.add_text_input("item_id", label="ItemID", text="")
        self.add_int_edit(
            "fragments_to_scan", label="Fragments", value=1,
            min_value=1, max_value=30,
        )


# ---------------------------------------------------------------------------
# Orphan ingredient node (visual-only, not model-backed)
# ---------------------------------------------------------------------------


class OrphanIngredientNode(CraftGraphBaseNode):
    """A visual-only ingredient node not backed by the data model.

    Used for staging ingredients before wiring them to a recipe.  Has a
    muted grey appearance to distinguish from model-backed nodes.  Provides
    a single output port that connects to recipe ingredient input ports.

    Widgets:
      - ``item_id`` (text): the TechType ID of the ingredient
    """

    NODE_NAME = "Orphan Ingredient"

    def __init__(self) -> None:
        super().__init__()
        self.set_color(*NODE_COLOR_ORPHAN_INGREDIENT)
        self.add_output("output", multi_output=True, color=PORT_COLOR_OUTPUT)
        self.add_text_input("item_id", label="ItemID", text="")


class SpriteNode(CraftGraphBaseNode):
    """A node that holds a sprite image reference.

    Connecting this node's ``sprite_out`` port to another node's
    ``sprite_in`` port overrides or assigns the sprite for that target
    node.  The default sprite selection (automatic ItemID lookup) remains
    as a fallback when no SpriteNode is connected.

    Widgets:
      - ``file_path`` (text): path to the PNG sprite file
    """

    NODE_NAME = "Sprite"

    def __init__(self) -> None:
        super().__init__()
        self.set_color(*NODE_COLOR_SPRITE)
        self.add_output("sprite_out", multi_output=True, color=PORT_COLOR_SPRITE)
        self.add_text_input("file_path", label="File", text="")


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
