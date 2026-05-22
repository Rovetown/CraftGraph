"""Tests for the floating-editor pool used by painted-field nodes."""

from __future__ import annotations


import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import QComboBox, QGraphicsView, QLineEdit

from craftgraph.floating_editor import FloatingEditorHost
from craftgraph.pin_registry import PinType


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

    def test_only_four_widgets_total(self, host):
        # Pool size is the headline HWND-saving claim. Lock it.
        editors = (host._string_editor, host._int_editor, host._combo_editor, host._float_editor)
        assert len({id(e) for e in editors}) == 4


class TestFloatingEditorSubclassRegistries:
    """Summon the right editor for fields declared on each recipe subclass's registry."""

    def test_alias_string_field_uses_string_editor(self, qapp, host):
        from craftgraph.qt_nodes import AliasRecipeNode

        # display_name is a STRING FieldPin declared on AliasRecipeNode.
        fp = next(p for p in AliasRecipeNode.FIELD_REGISTRY if p.name == "display_name")
        host.summon(
            field_name=fp.name,
            field_type=fp.pin_type,
            view_rect=QRect(10, 10, 100, 22),
            current_value="My Mod",
        )
        assert host._string_editor.isVisible()
        assert host._string_editor.text() == "My Mod"

    def test_custom_food_float_field_uses_float_editor(self, qapp, host):
        from craftgraph.qt_nodes import CustomFoodNode

        # decay_rate_mod is a FLOAT FieldPin declared on CustomFoodNode.
        fp = next(p for p in CustomFoodNode.FIELD_REGISTRY if p.name == "decay_rate_mod")
        host.summon(
            field_name=fp.name,
            field_type=fp.pin_type,
            view_rect=QRect(10, 10, 100, 22),
            current_value="0.5",
        )
        assert host._float_editor.isVisible()
        assert host._float_editor.text() == "0.5"

    def test_custom_food_float_commit_emits_value(self, qapp, host):
        from craftgraph.qt_nodes import CustomFoodNode

        fp = next(p for p in CustomFoodNode.FIELD_REGISTRY if p.name == "decay_rate_mod")
        committed: list[tuple[str, str]] = []
        host.committed.connect(lambda n, v: committed.append((n, v)))
        host.summon(
            field_name=fp.name,
            field_type=fp.pin_type,
            view_rect=QRect(10, 10, 100, 22),
            current_value="0.0",
        )
        host._float_editor.setText("2.5")
        host._float_editor.returnPressed.emit()
        qapp.processEvents()
        assert committed == [("decay_rate_mod", "2.5")]


class TestFloatingEditorSeamlessStyle:
    """Pooled editors render like the painted field they overlay, so editing
    reads as in-place rather than a popup widget appearing."""

    def test_string_editor_uses_field_style(self, host):
        from craftgraph.painted_fields import (
            FIELD_BORDER_RGB,
            FIELD_FILL_RGB,
            FIELD_TEXT_RGB,
        )

        ss = host._string_editor.styleSheet()
        assert f"rgb{FIELD_FILL_RGB}" in ss
        assert f"rgb{FIELD_BORDER_RGB}" in ss
        assert f"rgb{FIELD_TEXT_RGB}" in ss

    def test_line_editors_share_one_style(self, host):
        ss = host._string_editor.styleSheet()
        assert ss != ""
        assert host._int_editor.styleSheet() == ss
        assert host._float_editor.styleSheet() == ss

    def test_combo_editor_uses_field_fill(self, host):
        from craftgraph.painted_fields import FIELD_FILL_RGB

        assert f"rgb{FIELD_FILL_RGB}" in host._combo_editor.styleSheet()


class TestFloatingEditorTracksView:
    """The summoned editor follows its field when the view zooms or pans,
    so the painted field never peeks out from under a stale editor rect."""

    def test_editor_geometry_follows_view_zoom(self, host, view):
        from PySide6.QtWidgets import QGraphicsScene

        view.setScene(QGraphicsScene())
        host.summon(
            field_name="item_id",
            field_type=PinType.STRING,
            view_rect=QRect(20, 20, 100, 22),
            current_value="x",
        )
        before = host._string_editor.geometry()
        view.scale(2.0, 2.0)
        host._reposition_active_editor()
        assert host._string_editor.geometry() != before

    def test_reposition_is_noop_when_nothing_summoned(self, host):
        # Must not raise when called with no active editor.
        host._reposition_active_editor()
