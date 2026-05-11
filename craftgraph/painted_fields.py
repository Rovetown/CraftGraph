"""Painted-field grid layout for floating-input nodes.

Pure data: turns a ``FIELD_REGISTRY`` and node geometry into a list of
``FieldRect`` objects describing where each field's label and value
should be drawn in node-local coordinates. No Qt widgets, no painting.

Used by ``PaintedFieldsNodeItem`` (paint + hit-test) and tested without
a display via ``tests/test_painted_fields.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QRectF

from craftgraph.pin_registry import FieldPin, PinType


class FieldState(Enum):
    NORMAL = "normal"
    DISABLED = "disabled"
    REQUIRED_EMPTY = "required_empty"
    CONNECTED_TO_VARIABLE = "connected_to_variable"
    PAIRED_INCOMPLETE = "paired_incomplete"


@dataclass
class FieldRect:
    """A single field's label + value layout in node-local coordinates."""

    name: str
    pin_type: PinType
    label_rect: QRectF | None
    value_rect: QRectF | None
    state: FieldState = FieldState.NORMAL


def compute_field_grid(
    registry: list[FieldPin],
    node_width: float,
    row_height: float,
    label_fraction: float,
) -> list[FieldRect]:
    """Layout painted fields as a vertical grid.

    One row per field, except ``INGREDIENT_LIST`` fields which are skipped
    (they use NodeGraphQt input ports, not painted text).

    Returns rects in node-local coordinates with origin at (0, 0).
    """
    rects: list[FieldRect] = []
    label_width = node_width * label_fraction
    value_width = node_width - label_width
    y = 0.0
    for fp in registry:
        if fp.pin_type is PinType.INGREDIENT_LIST:
            continue
        label_rect = QRectF(0.0, y, label_width, row_height)
        value_rect = QRectF(label_width, y, value_width, row_height)
        rects.append(FieldRect(
            name=fp.name,
            pin_type=fp.pin_type,
            label_rect=label_rect,
            value_rect=value_rect,
        ))
        y += row_height
    return rects
