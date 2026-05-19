"""Floating-editor pool routes PinType.BOOL through the combo editor."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication, QComboBox, QGraphicsView

from craftgraph.floating_editor import FloatingEditorHost
from craftgraph.pin_registry import PinType


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def host(qapp):
    view = QGraphicsView()
    host = FloatingEditorHost()
    host.attach(view)
    yield host
    host.close()


class TestComboForBool:
    def test_bool_uses_combo_editor(self, host):
        host.summon(
            field_name="allowed",
            field_type=PinType.BOOL,
            view_rect=QRect(0, 0, 60, 20),
            current_value="YES",
            enum_items=["YES", "NO"],
        )
        assert isinstance(host._active_editor, QComboBox)
        assert host._active_editor.count() == 2
        assert host._active_editor.itemText(0) == "YES"
        assert host._active_editor.currentText() == "YES"

    def test_enum_still_uses_combo(self, host):
        host.summon(
            field_name="pda_group",
            field_type=PinType.ENUM,
            view_rect=QRect(0, 0, 60, 20),
            current_value="Personal",
            enum_items=["Personal", "Survival"],
        )
        assert isinstance(host._active_editor, QComboBox)
        assert host._active_editor.count() == 2


class TestComboCommit:
    def test_commit_emits_selected_value(self, host, qapp):
        captured: list[tuple[str, str]] = []
        host.committed.connect(lambda name, val: captured.append((name, val)))

        host.summon(
            field_name="allowed",
            field_type=PinType.BOOL,
            view_rect=QRect(0, 0, 60, 20),
            current_value="YES",
            enum_items=["YES", "NO"],
        )
        host._active_editor.setCurrentIndex(1)
        host._on_combo_activated(1)

        assert captured == [("allowed", "NO")]
