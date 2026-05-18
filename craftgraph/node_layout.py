"""Painted-grid layout helper for floating-input nodes.

Pure data: takes structural port geometry plus a ``FIELD_REGISTRY`` and
returns the coordinate maps needed to paint and hit-test value rects on
top of a NodeGraphQt port column.

The only Qt dependency in the core layout is ``QRectF``. The
``collect_port_geometry`` adapter is the single seam to NodeGraphQt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QRectF

from craftgraph.painted_fields import FieldRect
from craftgraph.pin_registry import FieldPin, PinType


@dataclass(frozen=True)
class PortRowGeometry:
    """Geometry of a single structural port row, in node-local coordinates.

    Populated from NodeGraphQt's ``_input_items`` after ``align_ports``
    has run. The layout core consumes plain floats only.
    """

    y: float
    height: float
    label_left: float
    label_right: float


@dataclass
class NodeLayout:
    """Painted-grid layout for a node, derived from its port geometry.

    Construct with a ``FIELD_REGISTRY`` and a port-row dict keyed by
    field name (the ``field_`` prefix is stripped by ``collect_port_geometry``).
    Call ``build()`` to populate ``value_rects``, ``hit_rects``,
    ``field_rects``, and ``min_node_width``.
    """

    registry: list[FieldPin]
    port_rows: dict[str, PortRowGeometry]
    value_column_width: float = 100.0
    margin: float = 8.0

    value_rects: dict[str, QRectF] = field(default_factory=dict)
    hit_rects: dict[str, QRectF] = field(default_factory=dict)
    field_rects: list[FieldRect] = field(default_factory=list)
    min_node_width: float = 0.0

    def build(self) -> NodeLayout:
        self.value_rects = {}
        self.hit_rects = {}
        self.field_rects = []
        for fp in self.registry:
            if fp.pin_type is PinType.INGREDIENT_LIST:
                continue
            row = self.port_rows.get(fp.name)
            if row is None:
                continue
            value_left = row.label_right + self.margin
            value_width = max(self.value_column_width, 0.0)
            value_rect = QRectF(value_left, row.y, value_width, row.height)
            hit_rect = QRectF(
                row.label_left,
                row.y,
                value_left + value_width - row.label_left,
                row.height,
            )
            self.value_rects[fp.name] = value_rect
            self.hit_rects[fp.name] = hit_rect
            self.field_rects.append(
                FieldRect(
                    name=fp.name,
                    pin_type=fp.pin_type,
                    label_rect=None,
                    value_rect=value_rect,
                )
            )
        if self.port_rows:
            widest = max(row.label_right for row in self.port_rows.values())
            self.min_node_width = widest + self.value_column_width + self.margin
        else:
            self.min_node_width = 0.0
        return self
