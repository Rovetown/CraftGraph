"""Painted-grid layout helper for floating-input nodes.

Pure data: takes structural port geometry plus a ``FIELD_REGISTRY`` and
returns the coordinate maps needed to paint and hit-test value rects on
top of a NodeGraphQt port column.

The only Qt dependency in the core layout is ``QRectF``. The
``collect_port_geometry`` adapter is the single seam to NodeGraphQt.
"""

from __future__ import annotations

from dataclasses import dataclass


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
