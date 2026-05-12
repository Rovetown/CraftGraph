"""Tests for the pure-data painted-grid layout helper.

These tests must run without a QApplication. They exercise the layout
math by feeding synthetic ``PortRowGeometry`` dicts.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from craftgraph.node_layout import PortRowGeometry


class TestPortRowGeometry:
    def test_holds_floats(self) -> None:
        row = PortRowGeometry(y=10.0, height=22.0, label_left=4.0, label_right=80.0)
        assert row.y == 10.0
        assert row.height == 22.0
        assert row.label_left == 4.0
        assert row.label_right == 80.0

    def test_is_frozen(self) -> None:
        row = PortRowGeometry(y=0.0, height=22.0, label_left=0.0, label_right=80.0)
        with pytest.raises(FrozenInstanceError):
            row.y = 999.0  # type: ignore[misc]
