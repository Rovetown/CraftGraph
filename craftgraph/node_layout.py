"""Painted-grid layout helper for floating-input nodes.

Pure data: takes structural port geometry plus a ``FIELD_REGISTRY`` and
returns the coordinate maps needed to paint and hit-test value rects on
top of a NodeGraphQt port column.

The only Qt dependency in the core layout is ``QRectF``. The
``collect_port_geometry`` adapter is the single seam to NodeGraphQt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
    value_v_padding: float = 3.0

    value_rects: dict[str, QRectF] = field(default_factory=dict)
    hit_rects: dict[str, QRectF] = field(default_factory=dict)
    field_rects: list[FieldRect] = field(default_factory=list)
    min_node_width: float = 0.0

    def build(self) -> NodeLayout:
        self.value_rects = {}
        self.hit_rects = {}
        self.field_rects = []
        if self.port_rows:
            # All value rects share the same x so the column is left-aligned
            # regardless of how wide each port's label happens to be.
            value_left = (
                max(row.label_right for row in self.port_rows.values()) + self.margin
            )
        else:
            value_left = 0.0
        value_width = max(self.value_column_width, 0.0)
        for fp in self.registry:
            if fp.pin_type is PinType.INGREDIENT_LIST:
                continue
            row = self.port_rows.get(fp.name)
            if row is None:
                continue
            v_pad = min(self.value_v_padding, row.height / 2.0)
            value_top = row.y + v_pad
            value_height = max(row.height - 2 * v_pad, 0.0)
            value_rect = QRectF(value_left, value_top, value_width, value_height)
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
                    render_as=fp.render_as,
                )
            )
        if self.port_rows:
            self.min_node_width = value_left + value_width
        else:
            self.min_node_width = 0.0
        return self


def collect_port_geometry(node_item: Any) -> dict[str, PortRowGeometry]:
    """Extract per-field port geometry from a NodeGraphQt node item.

    Walks ``node_item._input_items`` (an OrderedDict mapping port qgraphics
    items to their label text items). Returns one ``PortRowGeometry`` per
    port whose name starts with ``field_``, keyed by the unprefixed field
    name.

    Must be called after NodeGraphQt's ``align_ports`` has run for that
    node (typically inside ``PaintedFieldsNodeItem.paint`` immediately
    after ``super().paint(...)``); before that, ``port.y()`` may be 0.

    For variable nodes (IS_VARIABLE) there are no field_ input ports, so
    we fall back to the node's output port row and key it under the single
    registered field's name (``value`` by convention).
    """
    rows: dict[str, PortRowGeometry] = {}
    for port_item, text_item in node_item._input_items.items():
        port_name = port_item.name
        if not port_name.startswith("field_"):
            continue
        field_name = port_name[len("field_"):]
        text_rect = text_item.boundingRect()
        port_rect = port_item.boundingRect()
        rows[field_name] = PortRowGeometry(
            y=port_item.y(),
            height=max(port_rect.height(), text_rect.height()),
            label_left=text_item.x(),
            label_right=text_item.x() + text_rect.width(),
        )
    if rows:
        return rows
    node = getattr(node_item, "_cg_node", None)
    if node is None or not getattr(node, "IS_VARIABLE", False):
        return rows
    registry = getattr(node, "FIELD_REGISTRY", None) or []
    fp = next((p for p in registry if p.pin_type is not PinType.INGREDIENT_LIST), None)
    if fp is None:
        return rows
    out_items = getattr(node_item, "_output_items", None) or {}
    for port_item, text_item in out_items.items():
        port_rect = port_item.boundingRect()
        text_rect = text_item.boundingRect()
        rows[fp.name] = PortRowGeometry(
            y=port_item.y(),
            height=max(port_rect.height(), text_rect.height()),
            label_left=0.0,
            label_right=0.0,
        )
        break
    return rows
