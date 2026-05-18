"""Tests for the pure-data painted-grid layout helper.

These tests must run without a QApplication. They exercise the layout
math by feeding synthetic ``PortRowGeometry`` dicts.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from PySide6.QtCore import QRectF as _QRectF

from craftgraph.node_layout import NodeLayout, PortRowGeometry
from craftgraph.painted_fields import FieldState
from craftgraph.pin_registry import FieldPin, PinType


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


def _row(
    y: float,
    label_left: float = 4.0,
    label_right: float = 80.0,
    height: float = 22.0,
) -> PortRowGeometry:
    return PortRowGeometry(
        y=y, height=height, label_left=label_left, label_right=label_right,
    )


def _registry(*specs: tuple[str, PinType]) -> list[FieldPin]:
    return [FieldPin(name=n, pin_type=t) for n, t in specs]


class TestNodeLayoutBuild:
    def test_empty_registry_yields_empty_layout(self) -> None:
        layout = NodeLayout(registry=[], port_rows={}).build()
        assert layout.value_rects == {}
        assert layout.hit_rects == {}
        assert layout.field_rects == []
        assert layout.min_node_width == 0.0

    def test_single_field_value_rect_aligns_to_port_row(self) -> None:
        layout = NodeLayout(
            registry=_registry(("item_id", PinType.STRING)),
            port_rows={"item_id": _row(y=30.0, label_left=4.0, label_right=80.0)},
            value_column_width=100.0,
            margin=8.0,
        ).build()
        rect = layout.value_rects["item_id"]
        assert rect.x() == pytest.approx(80.0 + 8.0)
        assert rect.y() == pytest.approx(30.0)
        assert rect.width() == pytest.approx(100.0)
        assert rect.height() == pytest.approx(22.0)

    def test_hit_rect_unions_label_and_value(self) -> None:
        layout = NodeLayout(
            registry=_registry(("item_id", PinType.STRING)),
            port_rows={"item_id": _row(y=0.0, label_left=4.0, label_right=80.0)},
            value_column_width=100.0,
            margin=8.0,
        ).build()
        hit = layout.hit_rects["item_id"]
        assert hit.left() == pytest.approx(4.0)
        assert hit.right() == pytest.approx(80.0 + 8.0 + 100.0)
        assert hit.y() == pytest.approx(0.0)
        assert hit.height() == pytest.approx(22.0)

    def test_min_node_width_uses_widest_label(self) -> None:
        layout = NodeLayout(
            registry=_registry(("a", PinType.STRING), ("b", PinType.STRING)),
            port_rows={
                "a": _row(y=0.0, label_right=60.0),
                "b": _row(y=22.0, label_right=110.0),
            },
            value_column_width=100.0,
            margin=8.0,
        ).build()
        assert layout.min_node_width == pytest.approx(110.0 + 100.0 + 8.0)

    def test_ingredient_list_field_skipped(self) -> None:
        layout = NodeLayout(
            registry=[
                FieldPin(name="ingredients", pin_type=PinType.INGREDIENT_LIST),
                FieldPin(name="item_id", pin_type=PinType.STRING),
            ],
            port_rows={"item_id": _row(y=0.0)},
        ).build()
        assert "ingredients" not in layout.value_rects
        assert "item_id" in layout.value_rects

    def test_missing_port_row_skipped(self) -> None:
        layout = NodeLayout(
            registry=_registry(("ghost", PinType.STRING), ("real", PinType.STRING)),
            port_rows={"real": _row(y=0.0)},
        ).build()
        assert "ghost" not in layout.value_rects
        assert "real" in layout.value_rects

    def test_field_rects_carry_name_and_pin_type(self) -> None:
        layout = NodeLayout(
            registry=_registry(("amount", PinType.INT)),
            port_rows={"amount": _row(y=0.0)},
        ).build()
        assert [r.name for r in layout.field_rects] == ["amount"]
        assert layout.field_rects[0].pin_type is PinType.INT
        assert layout.field_rects[0].label_rect is None
        assert layout.field_rects[0].state is FieldState.NORMAL

    def test_value_width_clamped_non_negative_when_label_exceeds_width(self) -> None:
        layout = NodeLayout(
            registry=_registry(("x", PinType.STRING)),
            port_rows={"x": _row(y=0.0, label_right=200.0)},
            value_column_width=100.0,
            margin=8.0,
        ).build()
        rect = layout.value_rects["x"]
        assert rect.width() >= 0.0


class _FakePortItem:
    def __init__(self, name: str, y: float, height: float = 22.0) -> None:
        self.name = name
        self._y = y
        self._h = height

    def y(self) -> float:
        return self._y

    def boundingRect(self) -> _QRectF:
        return _QRectF(0.0, 0.0, 12.0, self._h)


class _FakeTextItem:
    def __init__(self, x: float, width: float, height: float = 22.0) -> None:
        self._x = x
        self._w = width
        self._h = height

    def x(self) -> float:
        return self._x

    def boundingRect(self) -> _QRectF:
        return _QRectF(0.0, 0.0, self._w, self._h)


class _FakeNodeItem:
    def __init__(self, items: list[tuple[_FakePortItem, _FakeTextItem]]) -> None:
        self._input_items = dict(items)


class TestCollectPortGeometry:
    def test_returns_geometry_for_field_ports_only(self) -> None:
        from craftgraph.node_layout import collect_port_geometry

        items = [
            (_FakePortItem("hierarchy", 0.0), _FakeTextItem(20.0, 60.0)),
            (_FakePortItem("ingredient_0", 22.0), _FakeTextItem(20.0, 80.0)),
            (_FakePortItem("field_item_id", 44.0), _FakeTextItem(20.0, 50.0)),
            (_FakePortItem("field_amount", 66.0), _FakeTextItem(20.0, 60.0)),
        ]
        node_item = _FakeNodeItem(items)
        rows = collect_port_geometry(node_item)
        assert set(rows.keys()) == {"item_id", "amount"}
        item_id_row = rows["item_id"]
        assert item_id_row.y == 44.0
        assert item_id_row.label_left == 20.0
        assert item_id_row.label_right == 70.0
        assert item_id_row.height == 22.0

    def test_empty_input_items_returns_empty_dict(self) -> None:
        from craftgraph.node_layout import collect_port_geometry

        rows = collect_port_geometry(_FakeNodeItem([]))
        assert rows == {}
