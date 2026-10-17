"""Tests for the float editor added to the floating-editor pool."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import QGraphicsView, QLineEdit

from craftgraph.floating_editor import FloatingEditorHost
from craftgraph.pin_registry import PinType


@pytest.fixture
def view(qapp):
    v = QGraphicsView()
    v.resize(400, 300)
    v.show()
    qapp.processEvents()
    yield v
    v.close()


@pytest.fixture
def host(qapp, view):
    h = FloatingEditorHost()
    h.attach(view)
    yield h
    h.close()


class TestFloatingEditorFloat:
    def test_pool_constructs_float_editor(self, host):
        assert isinstance(host._float_editor, QLineEdit)
        assert isinstance(host._float_editor.validator(), QDoubleValidator)

    def test_editor_for_type_float_returns_float_editor(self, host):
        # _editor_for_type is the dispatch used by summon.
        assert host._editor_for_type(PinType.FLOAT) is host._float_editor

    def test_summon_float_commits_value(self, qapp, host):
        results: list[tuple[str, str]] = []
        host.committed.connect(lambda f, v: results.append((f, v)))
        host.summon(
            field_name="decay_rate_mod",
            field_type=PinType.FLOAT,
            view_rect=QRect(10, 10, 100, 22),
            current_value="0.0",
        )
        host._float_editor.setText("1.5")
        host._float_editor.returnPressed.emit()
        qapp.processEvents()
        assert results == [("decay_rate_mod", "1.5")]
        assert not host._float_editor.isVisible()
