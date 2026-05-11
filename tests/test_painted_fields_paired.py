"""Tests for FieldState.PAIRED_INCOMPLETE and paired-field validation."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QApplication

from craftgraph.painted_fields import FieldRect, FieldState
from craftgraph.pin_registry import PinType


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class TestFieldStatePairedIncomplete:
    def test_paired_incomplete_enum_value_exists(self):
        assert FieldState.PAIRED_INCOMPLETE
        assert FieldState.PAIRED_INCOMPLETE.value == "paired_incomplete"


class TestPaintedFieldsPairedBorder:
    def test_paired_incomplete_renders_orange_border(self, qapp):
        """PaintedFieldsNodeItem.paint draws an orange value border for PAIRED_INCOMPLETE."""
        from unittest.mock import MagicMock

        from PySide6.QtGui import QColor

        from craftgraph.qt_nodes import PaintedFieldsNodeItem

        item = PaintedFieldsNodeItem(name="test_node")
        item._cg_field_rects = [
            FieldRect(
                name="pda_group",
                pin_type=PinType.ENUM,
                label_rect=QRectF(0, 0, 50, 22),
                value_rect=QRectF(50, 0, 100, 22),
                state=FieldState.PAIRED_INCOMPLETE,
            )
        ]

        painter = MagicMock()
        item._paint_one_field(painter, item._cg_field_rects[0])

        # Look at the QPen objects passed to painter.setPen
        pens = [call.args[0] for call in painter.setPen.call_args_list]
        colors = [p.color() for p in pens if hasattr(p, "color")]
        # At least one pen must be the orange paired-incomplete color (200, 160, 40)
        orange = QColor(200, 160, 40)
        assert any(
            c.red() == orange.red() and c.green() == orange.green() and c.blue() == orange.blue()
            for c in colors
        ), f"No orange pen used; saw colors {[(c.red(), c.green(), c.blue()) for c in colors]}"
