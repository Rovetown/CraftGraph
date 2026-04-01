"""Minimap widget for the NodeGraphQt graph viewer.

Renders a scaled-down overview of the entire node graph with a
semi-transparent rectangle showing the current viewport position.
Click or drag within the minimap to pan the main viewer.

Usage::

    from craftgraph.minimap import MinimapWidget

    minimap = MinimapWidget(parent=main_window)
    minimap.attach(node_graph)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

if TYPE_CHECKING:
    from NodeGraphQt import NodeGraph

_MINIMAP_W = 220
_MINIMAP_H = 160
_UPDATE_INTERVAL_MS = 100
_BG_COLOR = QtGui.QColor(25, 25, 30, 220)
_BORDER_COLOR = QtGui.QColor(80, 80, 80)
_NODE_COLOR = QtGui.QColor(100, 140, 180)
_VIEWPORT_FILL = QtGui.QColor(255, 255, 255, 25)
_VIEWPORT_BORDER = QtGui.QColor(200, 200, 200, 160)


class MinimapWidget(QtWidgets.QWidget):
    """Small overview widget showing the full graph and current viewport."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_MINIMAP_W, _MINIMAP_H)
        self._graph: NodeGraph | None = None
        self._dragging = False

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(_UPDATE_INTERVAL_MS)
        self._timer.timeout.connect(self.update)

    def attach(self, graph: NodeGraph) -> None:
        """Bind this minimap to a NodeGraph instance."""
        self._graph = graph
        self._timer.start()
        self.update()

    def detach(self) -> None:
        """Unbind from the current graph."""
        self._timer.stop()
        self._graph = None
        self.update()

    # -- Rendering ------------------------------------------------------------

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), _BG_COLOR)
        painter.setPen(QtGui.QPen(_BORDER_COLOR, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        if self._graph is None:
            painter.end()
            return

        viewer = self._graph.viewer()
        scene = viewer.scene()
        if scene is None:
            painter.end()
            return

        scene_rect = scene.itemsBoundingRect()
        if scene_rect.isEmpty():
            painter.end()
            return

        # Add margin so nodes aren't flush against minimap edges
        margin = max(scene_rect.width(), scene_rect.height()) * 0.1
        padded = scene_rect.adjusted(-margin, -margin, margin, margin)

        # Compute scale to fit padded scene rect into minimap area (with border inset)
        inset = 4
        available_w = self.width() - 2 * inset
        available_h = self.height() - 2 * inset
        scale_x = available_w / padded.width() if padded.width() > 0 else 1.0
        scale_y = available_h / padded.height() if padded.height() > 0 else 1.0
        scale = min(scale_x, scale_y)

        # Offset to center the content
        content_w = padded.width() * scale
        content_h = padded.height() * scale
        offset_x = inset + (available_w - content_w) / 2
        offset_y = inset + (available_h - content_h) / 2

        # Draw each node as a small rectangle
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        for item in scene.items():
            if not hasattr(item, "boundingRect"):
                continue
            item_rect = item.sceneBoundingRect()
            # Only draw top-level items (nodes), skip tiny sub-items
            if item.parentItem() is not None:
                continue
            if item_rect.width() < 5 or item_rect.height() < 5:
                continue

            node_color = _node_color_for(item)
            painter.setBrush(node_color)
            rx = offset_x + (item_rect.x() - padded.x()) * scale
            ry = offset_y + (item_rect.y() - padded.y()) * scale
            rw = max(item_rect.width() * scale, 3)
            rh = max(item_rect.height() * scale, 3)
            painter.drawRoundedRect(QtCore.QRectF(rx, ry, rw, rh), 1, 1)

        # Draw viewport indicator rectangle
        vp_rect = viewer.mapToScene(viewer.viewport().rect()).boundingRect()
        vx = offset_x + (vp_rect.x() - padded.x()) * scale
        vy = offset_y + (vp_rect.y() - padded.y()) * scale
        vw = vp_rect.width() * scale
        vh = vp_rect.height() * scale

        painter.setBrush(_VIEWPORT_FILL)
        painter.setPen(QtGui.QPen(_VIEWPORT_BORDER, 1.5))
        painter.drawRect(QtCore.QRectF(vx, vy, vw, vh))

        painter.end()

        # Stash transform params for mouse event coordinate conversion
        self._transform = (padded, scale, offset_x, offset_y)

    # -- Mouse interaction (click/drag to pan) --------------------------------

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._dragging = True
            self._pan_to(event.position())

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._dragging:
            self._pan_to(event.position())

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._dragging = False

    def _pan_to(self, pos: QtCore.QPointF) -> None:
        """Center the main viewer on the scene coordinate under *pos*."""
        if self._graph is None or not hasattr(self, "_transform"):
            return
        padded, scale, offset_x, offset_y = self._transform
        if scale <= 0:
            return

        scene_x = padded.x() + (pos.x() - offset_x) / scale
        scene_y = padded.y() + (pos.y() - offset_y) / scale

        viewer = self._graph.viewer()
        viewer.centerOn(scene_x, scene_y)


def _node_color_for(item: QtWidgets.QGraphicsItem) -> QtGui.QColor:
    """Pick a minimap dot color based on the item's brush or fallback."""
    if hasattr(item, "brush"):
        brush = item.brush()
        if brush.color().alpha() > 0:
            color = brush.color()
            # Brighten slightly for visibility on dark minimap background
            return QtGui.QColor(
                min(color.red() + 40, 255),
                min(color.green() + 40, 255),
                min(color.blue() + 40, 255),
                200,
            )
    return _NODE_COLOR
