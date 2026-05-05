"""Tests for the MinimapWidget pixmap-cache optimization (TODO 1.10).

The minimap was the dominant pan/zoom hotspot (~50% of the cProfile sample
window) because it re-walked every scene item on every paintEvent. The
content layer (node dots + background) only changes when the graph topology
or node positions change, so we cache it as a QPixmap and only redraw the
viewport overlay each frame.

Run:  uv run --extra qt pytest tests/test_minimap.py -v
"""

from __future__ import annotations

import sys

import pytest

pytest.importorskip(
    "NodeGraphQt",
    reason="NodeGraphQt not installed (install with: uv sync --extra qt)",
)

from PySide6 import QtCore, QtGui, QtWidgets


@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


@pytest.fixture
def minimap(qapp):
    from craftgraph.minimap import MinimapWidget

    widget = MinimapWidget()
    yield widget
    widget.deleteLater()


def _force_paint(widget: QtWidgets.QWidget) -> None:
    """Synthesize a paintEvent without showing the window."""
    pixmap = QtGui.QPixmap(widget.size())
    widget.render(pixmap)


class TestContentPixmapCache:
    def test_cache_built_after_first_paint(self, minimap):
        assert minimap._content_pixmap is None
        _force_paint(minimap)
        assert minimap._content_pixmap is not None

    def test_resize_invalidates_cache(self, minimap):
        _force_paint(minimap)
        assert minimap._content_pixmap is not None
        # MinimapWidget uses setFixedSize, so synthesize a QResizeEvent to
        # exercise the resizeEvent override directly.
        old_size = minimap.size()
        new_size = QtCore.QSize(old_size.width() + 10, old_size.height() + 10)
        minimap.resizeEvent(QtGui.QResizeEvent(new_size, old_size))
        assert minimap._content_pixmap is None

    def test_detach_invalidates_cache(self, minimap):
        from NodeGraphQt import NodeGraph

        graph = NodeGraph()
        minimap.attach(graph)
        _force_paint(minimap)
        assert minimap._content_pixmap is not None

        minimap.detach()
        assert minimap._content_pixmap is None

    def test_repeated_paints_reuse_cache(self, minimap, monkeypatch):
        """Within the rebuild interval, the static layer must not be rebuilt."""
        # Stretch the rebuild interval so the test isn't time-sensitive.
        minimap._content_rebuild_interval_ms = 60_000

        rebuild_count = 0
        original = minimap._render_content_pixmap

        def counting_rebuild() -> None:
            nonlocal rebuild_count
            rebuild_count += 1
            original()

        monkeypatch.setattr(minimap, "_render_content_pixmap", counting_rebuild)

        _force_paint(minimap)
        _force_paint(minimap)
        _force_paint(minimap)

        assert rebuild_count == 1

    def test_invalidate_forces_rebuild_on_next_paint(self, minimap, monkeypatch):
        minimap._content_rebuild_interval_ms = 60_000

        rebuild_count = 0
        original = minimap._render_content_pixmap

        def counting_rebuild() -> None:
            nonlocal rebuild_count
            rebuild_count += 1
            original()

        monkeypatch.setattr(minimap, "_render_content_pixmap", counting_rebuild)

        _force_paint(minimap)
        assert rebuild_count == 1

        minimap._invalidate_content_cache()
        _force_paint(minimap)
        assert rebuild_count == 2
