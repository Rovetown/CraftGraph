"""Declarative pin registry for CraftGraph node types (Phase A).

Defines the data structures that describe field pins and output pins
on NodeGraphQt node classes. This module is pure data -- no Qt imports.
The build logic that reads these declarations lives in qt_nodes.py.

Architecture notes:
  - PinType maps to widget factory methods in CraftGraphBaseNode
  - FieldPin.resolved_model_field handles name mismatches between
    widget property names and model attribute names
  - FieldPin.nullable marks fields whose model type is T | None
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PinType(Enum):
    """Widget type for a field pin.

    Each variant maps to a widget factory method in CraftGraphBaseNode:
      STRING -> add_text_input()
      INT    -> add_int_edit()
      FLOAT  -> add_float_edit()
      BOOL   -> add_checkbox()
      ENUM   -> add_combo_menu()
      CSV    -> add_text_input() (comma-separated, parsed to list)
      INGREDIENT_LIST -> skipped (handled by dynamic ingredient ports)
    """

    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    ENUM = "enum"
    CSV = "csv"
    INGREDIENT_LIST = "ingredients"


@dataclass(frozen=True)
class FieldPin:
    """Declares a single field pin on a node class.

    The base class reads these to create widgets, input ports, and
    model-update wiring automatically.
    """

    name: str
    pin_type: PinType
    label: str = ""
    default: Any = None
    required: bool = False
    nullable: bool = False
    model_field: str = ""
    min_val: int | float | None = None
    max_val: int | float | None = None
    step: float = 1.0
    enum_items: list[str] | None = field(default=None, repr=False)
    pin_color: tuple[int, int, int] = (180, 180, 180)

    @property
    def resolved_model_field(self) -> str:
        """Return the model attribute name (falls back to name)."""
        return self.model_field or self.name


@dataclass(frozen=True)
class OutputPin:
    """Declares a single output port on a node class."""

    name: str
    label: str = ""
    multi: bool = True
    pin_color: tuple[int, int, int] = (100, 200, 100)
