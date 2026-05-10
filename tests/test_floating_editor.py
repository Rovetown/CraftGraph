"""Tests for the floating-editor pool used by painted-field nodes."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import QApplication, QComboBox, QGraphicsView, QLineEdit

from craftgraph.floating_editor import FloatingEditorHost
from craftgraph.pin_registry import PinType


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication (one per test run)."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def view(qapp):
    v = QGraphicsView()
    v.setObjectName("test_view")
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


class TestFloatingEditorHost:
    def test_pool_constructs_three_widgets(self, host):
        assert isinstance(host._string_editor, QLineEdit)
        assert isinstance(host._int_editor, QLineEdit)
        assert isinstance(host._combo_editor, QComboBox)
        assert host._string_editor.validator() is None
        assert isinstance(host._int_editor.validator(), QIntValidator)

    def test_summon_string_focuses_editor(self, host):
        host.summon(
            field_name="item_id",
            field_type=PinType.STRING,
            view_rect=QRect(10, 10, 100, 22),
            current_value="Titanium",
        )
        assert host._string_editor.isVisible()
        assert host._string_editor.text() == "Titanium"
        # All text selected so the user can overwrite.
        assert host._string_editor.selectedText() == "Titanium"

    def test_summon_int_uses_int_editor(self, host):
        host.summon(
            field_name="amount",
            field_type=PinType.INT,
            view_rect=QRect(10, 10, 100, 22),
            current_value="5",
        )
        assert host._int_editor.isVisible()
        assert not host._string_editor.isVisible()
        assert host._int_editor.text() == "5"

    def test_summon_enum_populates_combo(self, host):
        host.summon(
            field_name="force_unlock",
            field_type=PinType.ENUM,
            view_rect=QRect(10, 10, 100, 22),
            current_value="auto",
            enum_items=["auto", "YES", "NO"],
        )
        assert host._combo_editor.isVisible()
        assert host._combo_editor.count() == 3
        assert host._combo_editor.currentText() == "auto"

    def test_commit_on_enter(self, qapp, host):
        results = []
        host.committed.connect(lambda fname, val: results.append((fname, val)))
        host.summon("item_id", PinType.STRING, QRect(10, 10, 100, 22), current_value="X")
        host._string_editor.setText("Titanium")
        host._string_editor.returnPressed.emit()
        qapp.processEvents()
        assert results == [("item_id", "Titanium")]
        assert not host._string_editor.isVisible()

    def test_escape_cancels_without_commit(self, qapp, host):
        committed: list = []
        cancelled: list = []
        host.committed.connect(lambda *a: committed.append(a))
        host.cancelled.connect(lambda *a: cancelled.append(a))
        host.summon("item_id", PinType.STRING, QRect(10, 10, 100, 22), current_value="X")
        host._string_editor.setText("Y")
        host._cancel()  # simulates Escape handler
        qapp.processEvents()
        assert committed == []
        assert cancelled == [("item_id",)]
        assert not host._string_editor.isVisible()

    def test_resummon_commits_pending_first(self, qapp, host):
        results = []
        host.committed.connect(lambda fname, val: results.append((fname, val)))
        host.summon("item_id", PinType.STRING, QRect(10, 10, 100, 22), current_value="A")
        host._string_editor.setText("B")
        # Re-summon to a different field while pending.
        host.summon("amount", PinType.INT, QRect(10, 40, 100, 22), current_value="3")
        qapp.processEvents()
        # First field's pending value got committed before the new summon.
        assert results == [("item_id", "B")]
        assert host._int_editor.isVisible()
        assert not host._string_editor.isVisible()

    def test_only_three_widgets_total(self, host):
        # Pool size is the headline HWND-saving claim. Lock it.
        editors = (host._string_editor, host._int_editor, host._combo_editor)
        assert len({id(e) for e in editors}) == 3
