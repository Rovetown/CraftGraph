"""Tests for the painted-field grid layout helper."""

from __future__ import annotations

import pytest

from craftgraph.painted_fields import FieldRect, FieldState, compute_field_grid
from craftgraph.pin_registry import FieldPin, PinType


@pytest.fixture
def sample_registry() -> list[FieldPin]:
    return [
        FieldPin("item_id", PinType.STRING, label="ItemID", required=True),
        FieldPin("amount", PinType.INT, label="Amount", default=1),
        FieldPin("ingredients", PinType.INGREDIENT_LIST, label="Ingredients"),
        FieldPin("linked", PinType.CSV, label="Linked"),
    ]


class TestFieldGrid:
    def test_excludes_ingredient_list(self, sample_registry):
        rects = compute_field_grid(
            sample_registry,
            node_width=180.0,
            row_height=22.0,
            label_fraction=0.4,
        )
        names = [r.name for r in rects]
        assert "ingredients" not in names
        assert names == ["item_id", "amount", "linked"]

    def test_one_row_per_painted_field(self, sample_registry):
        rects = compute_field_grid(sample_registry, 180.0, 22.0, 0.4)
        # 4 fields - 1 INGREDIENT_LIST excluded == 3 rows.
        assert len(rects) == 3

    def test_label_and_value_split(self, sample_registry):
        rects = compute_field_grid(sample_registry, 200.0, 22.0, 0.4)
        rect = rects[0]
        assert rect.label_rect.width() == pytest.approx(80.0)  # 200 * 0.4
        assert rect.value_rect.width() == pytest.approx(120.0)
        assert rect.label_rect.right() == pytest.approx(rect.value_rect.left())

    def test_row_y_progression(self, sample_registry):
        rects = compute_field_grid(sample_registry, 180.0, 22.0, 0.4)
        assert rects[0].label_rect.top() == 0.0
        assert rects[1].label_rect.top() == pytest.approx(22.0)
        assert rects[2].label_rect.top() == pytest.approx(44.0)

    def test_rects_carry_pin_type(self, sample_registry):
        rects = compute_field_grid(sample_registry, 180.0, 22.0, 0.4)
        types = [r.pin_type for r in rects]
        assert types == [PinType.STRING, PinType.INT, PinType.CSV]

    def test_default_field_state_is_normal(self):
        rect = FieldRect(name="x", pin_type=PinType.STRING,
                         label_rect=None, value_rect=None)
        assert rect.state is FieldState.NORMAL

    def test_total_height(self, sample_registry):
        rects = compute_field_grid(sample_registry, 180.0, 22.0, 0.4)
        assert max(r.label_rect.bottom() for r in rects) == pytest.approx(66.0)
