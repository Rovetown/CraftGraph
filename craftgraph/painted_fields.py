"""Painted-field types for floating-input nodes.

``FieldState`` enumerates the visual states a painted field can be in
(normal, disabled, required-but-empty, connected-to-variable, etc.).
``FieldRect`` is the per-field layout record consumed by
``PaintedFieldsNodeItem.paint``; instances are built fresh each frame
by ``craftgraph.node_layout.NodeLayout`` from the node's port geometry.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QRectF

from craftgraph.pin_registry import PinType

# Shared visual style for a painted value field and the floating editor that
# overlays it while the user types. Both render from these constants so that
# entering edit mode reads as the field becoming editable in place, rather
# than a separate popup widget appearing on top of it.
FIELD_FILL_RGB = (40, 40, 40)
FIELD_BORDER_RGB = (80, 80, 80)
FIELD_TEXT_RGB = (220, 220, 220)
FIELD_TEXT_PADDING_PX = 4


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
    render_as: str = "text"
