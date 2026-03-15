"""Tests for the pin registry data structures (Phase A).

Pure-data tests -- no Qt dependency needed.

Run: uv run pytest tests/test_pin_registry.py -v
"""

from __future__ import annotations

import pytest


class TestPinType:

    def test_all_variants_exist(self):
        from craftgraph.pin_registry import PinType

        expected = {"string", "int", "float", "bool", "enum", "csv", "ingredients"}
        assert {pt.value for pt in PinType} == expected

    def test_variant_count(self):
        from craftgraph.pin_registry import PinType

        assert len(PinType) == 7


class TestFieldPin:

    def test_minimal_construction(self):
        from craftgraph.pin_registry import FieldPin, PinType

        fp = FieldPin("item_id", PinType.STRING)
        assert fp.name == "item_id"
        assert fp.pin_type == PinType.STRING
        assert fp.label == ""
        assert fp.default is None
        assert fp.required is False
        assert fp.nullable is False
        assert fp.model_field == ""

    def test_resolved_model_field_defaults_to_name(self):
        from craftgraph.pin_registry import FieldPin, PinType

        fp = FieldPin("item_id", PinType.STRING)
        assert fp.resolved_model_field == "item_id"

    def test_resolved_model_field_uses_override(self):
        from craftgraph.pin_registry import FieldPin, PinType

        fp = FieldPin("size_width", PinType.INT, model_field="width")
        assert fp.resolved_model_field == "width"

    def test_frozen(self):
        from craftgraph.pin_registry import FieldPin, PinType

        fp = FieldPin("item_id", PinType.STRING)
        with pytest.raises(AttributeError):
            fp.name = "other"  # type: ignore[misc]

    def test_full_construction(self):
        from craftgraph.pin_registry import FieldPin, PinType

        fp = FieldPin(
            "amount_crafted",
            PinType.INT,
            label="Amount",
            default=1,
            required=False,
            nullable=False,
            model_field="",
            min_val=0,
            max_val=99,
            step=1.0,
            enum_items=None,
            pin_color=(180, 180, 180),
        )
        assert fp.label == "Amount"
        assert fp.default == 1
        assert fp.min_val == 0
        assert fp.max_val == 99

    def test_enum_items(self):
        from craftgraph.pin_registry import FieldPin, PinType

        fp = FieldPin(
            "model", PinType.ENUM,
            enum_items=["Fabricator", "Workbench", "MoonPool"],
        )
        assert fp.enum_items == ["Fabricator", "Workbench", "MoonPool"]


class TestOutputPin:

    def test_minimal_construction(self):
        from craftgraph.pin_registry import OutputPin

        op = OutputPin("output")
        assert op.name == "output"
        assert op.label == ""
        assert op.multi is True
        assert op.pin_color == (100, 200, 100)

    def test_frozen(self):
        from craftgraph.pin_registry import OutputPin

        op = OutputPin("output")
        with pytest.raises(AttributeError):
            op.name = "other"  # type: ignore[misc]

    def test_custom_color(self):
        from craftgraph.pin_registry import OutputPin

        op = OutputPin("children", pin_color=(100, 100, 220))
        assert op.pin_color == (100, 100, 220)
