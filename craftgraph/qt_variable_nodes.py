"""Variable node classes for CraftGraph (Phase B).

Variable nodes are standalone value-holder nodes that connect to field
pins on CC3 block type nodes, overriding their inline widget values.
They are not model-backed and do not participate in parsing or export.

Architecture notes:
  - Each variable node has one FIELD_REGISTRY entry (the value widget)
    and one OUTPUT_PINS entry (value_out).
  - IS_VARIABLE = True flag is used by sync.py to detect variable nodes.
  - HAS_SPRITE_PORT = False suppresses the sprite_in port.
  - _var_uuid provides a stable key for layout persistence.
"""

from __future__ import annotations

import uuid
from enum import Enum

from craftgraph.pin_registry import FieldPin, OutputPin, PinType
from craftgraph.qt_nodes import CraftGraphBaseNode

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NODE_COLOR_VARIABLE = (100, 70, 130)
PORT_COLOR_VAR_OUT = (100, 70, 130)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class VariableNode(CraftGraphBaseNode):
    """Base class for all variable nodes.

    Variable nodes hold a single editable value and expose it via an
    output port. When connected to a CC3 node's field_* input port,
    the variable's value overrides that field's inline widget.

    Not model-backed: model_ref stays None. Layout persistence uses
    _var_uuid instead of model_position_key().
    """

    NODE_NAME = "Variable"
    NODE_COLOR = NODE_COLOR_VARIABLE
    IS_VARIABLE = True
    HAS_SPRITE_PORT = False

    def __init__(self) -> None:
        super().__init__()
        self._var_uuid: str = uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Concrete variable node types
# ---------------------------------------------------------------------------


class StringVarNode(VariableNode):
    """Holds a string value. Connects to STRING field pins."""

    NODE_NAME = "String Variable"

    FIELD_REGISTRY = [
        FieldPin("value", PinType.STRING, label="Value", default=""),
    ]
    OUTPUT_PINS = [
        OutputPin("value_out", label="String", pin_color=PORT_COLOR_VAR_OUT),
    ]


class IntVarNode(VariableNode):
    """Holds an integer value. Connects to INT field pins."""

    NODE_NAME = "Int Variable"

    FIELD_REGISTRY = [
        FieldPin("value", PinType.INT, label="Value", default=0,
                 min_val=-9999, max_val=9999),
    ]
    OUTPUT_PINS = [
        OutputPin("value_out", label="Int", pin_color=PORT_COLOR_VAR_OUT),
    ]


class FloatVarNode(VariableNode):
    """Holds a float value. Connects to FLOAT field pins."""

    NODE_NAME = "Float Variable"

    FIELD_REGISTRY = [
        FieldPin("value", PinType.FLOAT, label="Value", default=0.0,
                 min_val=-99999.0, max_val=99999.0, step=0.1),
    ]
    OUTPUT_PINS = [
        OutputPin("value_out", label="Float", pin_color=PORT_COLOR_VAR_OUT),
    ]


class BoolVarNode(VariableNode):
    """Holds a boolean value. Connects to BOOL field pins."""

    NODE_NAME = "Bool Variable"

    FIELD_REGISTRY = [
        FieldPin("value", PinType.BOOL, label="Value", default=False),
    ]
    OUTPUT_PINS = [
        OutputPin("value_out", label="Bool", pin_color=PORT_COLOR_VAR_OUT),
    ]


class CSVListVarNode(VariableNode):
    """Holds a comma-separated list. Connects to CSV field pins."""

    NODE_NAME = "CSV List Variable"

    FIELD_REGISTRY = [
        FieldPin("value", PinType.CSV, label="Value", default=""),
    ]
    OUTPUT_PINS = [
        OutputPin("value_out", label="CSV", pin_color=PORT_COLOR_VAR_OUT),
    ]


class EnumVarNode(VariableNode):
    """Holds an enum value. Connects to ENUM field pins.

    The enum_items list must be set at creation time via set_enum_items().
    By default, the combo box is empty.
    """

    NODE_NAME = "Enum Variable"

    FIELD_REGISTRY = [
        FieldPin("value", PinType.ENUM, label="Value", enum_items=[]),
    ]
    OUTPUT_PINS = [
        OutputPin("value_out", label="Enum", pin_color=PORT_COLOR_VAR_OUT),
    ]

    def set_enum_items(self, items: list[str]) -> None:
        """Populate the combo box with enum values after creation."""
        widget = self.get_widget("value")
        if widget is not None:
            combo = widget.get_custom_widget()
            if combo is not None:
                combo.clear()
                combo.addItems(items)


class PathVarNode(VariableNode):
    """Holds a path string. Connects to STRING field pins with path semantics."""

    NODE_NAME = "Path Variable"

    FIELD_REGISTRY = [
        FieldPin("value", PinType.STRING, label="Path", default=""),
    ]
    OUTPUT_PINS = [
        OutputPin("value_out", label="Path", pin_color=PORT_COLOR_VAR_OUT),
    ]


class ColorVarNode(VariableNode):
    """Holds an RGB color as comma-separated floats. Connects to CSV field pins."""

    NODE_NAME = "Color Variable"

    FIELD_REGISTRY = [
        FieldPin("value", PinType.CSV, label="RGB", default="0.0, 0.0, 0.0"),
    ]
    OUTPUT_PINS = [
        OutputPin("value_out", label="Color", pin_color=PORT_COLOR_VAR_OUT),
    ]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class VariableNodeKind(Enum):
    """Variable node types available in CraftGraph."""

    STRING_VAR = "StringVar"
    INT_VAR = "IntVar"
    FLOAT_VAR = "FloatVar"
    BOOL_VAR = "BoolVar"
    CSV_LIST_VAR = "CSVListVar"
    ENUM_VAR = "EnumVar"
    INGREDIENT_LIST_VAR = "IngredientListVar"  # STUB -- Phase B+
    PATH_VAR = "PathVar"
    COLOR_VAR = "ColorVar"


VARIABLE_NODE_REGISTRY: dict[VariableNodeKind, type[VariableNode]] = {
    VariableNodeKind.STRING_VAR: StringVarNode,
    VariableNodeKind.INT_VAR: IntVarNode,
    VariableNodeKind.FLOAT_VAR: FloatVarNode,
    VariableNodeKind.BOOL_VAR: BoolVarNode,
    VariableNodeKind.CSV_LIST_VAR: CSVListVarNode,
    VariableNodeKind.ENUM_VAR: EnumVarNode,
    # IngredientListVarNode omitted -- STUB, Phase B+
    VariableNodeKind.PATH_VAR: PathVarNode,
    VariableNodeKind.COLOR_VAR: ColorVarNode,
}


_PINTYPE_TO_VAR_KIND: dict[PinType, VariableNodeKind] = {
    PinType.STRING: VariableNodeKind.STRING_VAR,
    PinType.INT: VariableNodeKind.INT_VAR,
    PinType.FLOAT: VariableNodeKind.FLOAT_VAR,
    PinType.BOOL: VariableNodeKind.BOOL_VAR,
    PinType.CSV: VariableNodeKind.CSV_LIST_VAR,
    PinType.ENUM: VariableNodeKind.ENUM_VAR,
}

_PREFERRED_KIND_MAP: dict[str, VariableNodeKind] = {
    "PathVar": VariableNodeKind.PATH_VAR,
    "ColorVar": VariableNodeKind.COLOR_VAR,
}


def pintype_to_variable_kind(
    pin_type: PinType,
    preferred_var_kind: str | None = None,
) -> VariableNodeKind | None:
    """Map a PinType (with optional override) to the right VariableNodeKind."""
    if preferred_var_kind is not None:
        override = _PREFERRED_KIND_MAP.get(preferred_var_kind)
        if override is not None:
            return override
    return _PINTYPE_TO_VAR_KIND.get(pin_type)


def all_variable_node_classes() -> list[type[VariableNode]]:
    """Return every concrete variable node class for graph.register_node()."""
    return list(VARIABLE_NODE_REGISTRY.values())
