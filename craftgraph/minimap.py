"""Minimap widget for the NodeGraphQt graph viewer.

Renders a scaled-down overview of the entire node graph with a
semi-transparent rectangle showing the current viewport position.
Click or drag within the minimap to pan the main viewer.

The static content (background + node dots) is cached as a QPixmap
since it only changes when the graph topology or node positions change.
The viewport overlay rectangle is the only thing redrawn on each paint,
which keeps pan/zoom paints essentially free.

Usage::

    from craftgraph.minimap import MinimapWidget

    minimap = MinimapWidget(parent=main_window)
    minimap.attach(node_graph)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from craftgraph.config import get_config

if TYPE_CHECKING:
    from NodeGraphQt import NodeGraph

_MINIMAP_CFG = get_config().ui.minimap
_MINIMAP_W = _MINIMAP_CFG.width
_MINIMAP_H = _MINIMAP_CFG.height
_BG_COLOR = QtGui.QColor(*_MINIMAP_CFG.bg_color)
_BORDER_COLOR = QtGui.QColor(*_MINIMAP_CFG.border_color)
_NODE_COLOR = QtGui.QColor(*_MINIMAP_CFG.node_color)
_VIEWPORT_FILL = QtGui.QColor(*_MINIMAP_CFG.viewport_fill)
_VIEWPORT_BORDER = QtGui.QColor(*_MINIMAP_CFG.viewport_border)

# Scene items smaller than this (in scene pixels) are not drawn as minimap
# dots -- prevents tiny sub-items of nodes from cluttering the overview.
_MIN_SCENE_ITEM_PX = 5
# Minimum visible size (in minimap pixels) for drawn node rects, so that
# heavily zoomed-out scenes still show legible dots.
_MIN_DOT_PX = 3
# Fraction of scene width/height used as margin around the minimap content,
# so nodes never sit flush against the minimap border.
_CONTENT_MARGIN_FRAC = 0.1
# Inset (minimap-space pixels) between the minimap border and its content.
_CONTENT_INSET_PX = 4
# Per-channel brightness boost applied to node brush colors so they remain
# legible against the dark minimap background. Alpha is capped separately.
_COLOR_BOOST = 40
_COLOR_MAX = 255
_COLOR_DOT_ALPHA = 200
# How long (ms) to keep the cached node-content pixmap before forcing a
# rebuild. Catches node moves/additions without wiring graph signals.
_CONTENT_REBUILD_INTERVAL_MS = 1000


class MinimapWidget(QtWidgets.QWidget):
    """Small overview widget showing the full graph and current viewport."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_MINIMAP_W, _MINIMAP_H)
        self._graph: NodeGraph | None = None
        self._dragging = False

        # Cached pixmap holding the slow-changing layer (background + node
        # dots). Rebuilt on resize, detach, or every
        # _content_rebuild_interval_ms; blitted as-is on every paint.
        self._content_pixmap: QtGui.QPixmap | None = None
        self._content_rebuild_interval_ms = _CONTENT_REBUILD_INTERVAL_MS
        self._last_content_rebuild_ms = 0
        # (padded_scene_rect, scale, offset_x, offset_y) -- captured during
        # the static-layer render and reused for viewport overlay + mouse
        # coordinate conversion.
        self._transform: tuple[QtCore.QRectF, float, float, float] | None = None

        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(get_config().timings.minimap_update_interval_ms)
        self._timer.timeout.connect(self.update)

    def attach(self, graph: NodeGraph) -> None:
        """Bind this minimap to a NodeGraph instance."""
        self._graph = graph
        self._invalidate_content_cache()
        self._timer.start()
        self.update()

    def detach(self) -> None:
        """Unbind from the current graph."""
        self._timer.stop()
        self._graph = None
        self._invalidate_content_cache()
        self.update()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        self._invalidate_content_cache()
        super().resizeEvent(event)

    def _invalidate_content_cache(self) -> None:
        self._content_pixmap = None
        self._transform = None

    # -- Rendering ------------------------------------------------------------

    def _render_content_pixmap(self) -> None:
        """Build the cached background + node-dots layer."""
        pixmap = QtGui.QPixmap(self.size())
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)

        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.fillRect(pixmap.rect(), _BG_COLOR)
        painter.setPen(QtGui.QPen(_BORDER_COLOR, 1))
        painter.drawRect(pixmap.rect().adjusted(0, 0, -1, -1))

        if self._graph is None:
            painter.end()
            self._content_pixmap = pixmap
            self._transform = None
            return

        viewer = self._graph.viewer()
        scene = viewer.scene()
        if scene is None:
            painter.end()
            self._content_pixmap = pixmap
            self._transform = None
            return

        scene_rect = scene.itemsBoundingRect()
        if scene_rect.isEmpty():
            painter.end()
            self._content_pixmap = pixmap
            self._transform = None
            return

        # Add margin so nodes aren't flush against minimap edges
        margin = max(scene_rect.width(), scene_rect.height()) * _CONTENT_MARGIN_FRAC
        padded = scene_rect.adjusted(-margin, -margin, margin, margin)

        # Compute scale to fit padded scene rect into minimap area (with border inset)
        inset = _CONTENT_INSET_PX
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
            # Filter top-level items first so we never pay sceneBoundingRect
            # cost for child ports/overlays we discard anyway.
            if item.parentItem() is not None:
                continue
            if not hasattr(item, "boundingRect"):
                continue
            item_rect = item.sceneBoundingRect()
            if item_rect.width() < _MIN_SCENE_ITEM_PX or item_rect.height() < _MIN_SCENE_ITEM_PX:
                continue

            node_color = _node_color_for(item)
            painter.setBrush(node_color)
            rx = offset_x + (item_rect.x() - padded.x()) * scale
            ry = offset_y + (item_rect.y() - padded.y()) * scale
            rw = max(item_rect.width() * scale, _MIN_DOT_PX)
            rh = max(item_rect.height() * scale, _MIN_DOT_PX)
            painter.drawRoundedRect(QtCore.QRectF(rx, ry, rw, rh), 1, 1)

        painter.end()

        self._content_pixmap = pixmap
        self._transform = (padded, scale, offset_x, offset_y)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        now_ms = QtCore.QDateTime.currentMSecsSinceEpoch()
        cache_stale = (
            self._content_pixmap is None
            or now_ms - self._last_content_rebuild_ms >= self._content_rebuild_interval_ms
        )
        if cache_stale:
            self._render_content_pixmap()
            self._last_content_rebuild_ms = now_ms

        painter = QtGui.QPainter(self)
        if self._content_pixmap is not None:
            painter.drawPixmap(0, 0, self._content_pixmap)

        # Viewport overlay -- the only piece that actually changes during
        # pan/zoom, so it stays out of the cached pixmap.
        if self._graph is not None and self._transform is not None:
            viewer = self._graph.viewer()
            padded, scale, offset_x, offset_y = self._transform
            vp_rect = viewer.mapToScene(viewer.viewport().rect()).boundingRect()
            vx = offset_x + (vp_rect.x() - padded.x()) * scale
            vy = offset_y + (vp_rect.y() - padded.y()) * scale
            vw = vp_rect.width() * scale
            vh = vp_rect.height() * scale

            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            painter.setBrush(_VIEWPORT_FILL)
            painter.setPen(QtGui.QPen(_VIEWPORT_BORDER, 1.5))
            painter.drawRect(QtCore.QRectF(vx, vy, vw, vh))

        painter.end()

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
        if self._graph is None or self._transform is None:
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
                min(color.red() + _COLOR_BOOST, _COLOR_MAX),
                min(color.green() + _COLOR_BOOST, _COLOR_MAX),
                min(color.blue() + _COLOR_BOOST, _COLOR_MAX),
                _COLOR_DOT_ALPHA,
            )
    return _NODE_COLOR
