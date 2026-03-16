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
            "model",
            PinType.ENUM,
            enum_items=["Fabricator", "Workbench", "MoonPool"],
        )
        assert fp.enum_items == ["Fabricator", "Workbench", "MoonPool"]


class TestFieldPinWidgetOverride:
    def test_default_widget_override_is_none(self):
        from craftgraph.pin_registry import FieldPin, PinType

        fp = FieldPin("test", PinType.STRING)
        assert fp.widget_override is None

    def test_widget_override_combo(self):
        from craftgraph.pin_registry import FieldPin, PinType

        fp = FieldPin("test", PinType.STRING, widget_override="combo")
        assert fp.widget_override == "combo"

    def test_widget_override_preserved_in_frozen_dataclass(self):
        from craftgraph.pin_registry import FieldPin, PinType

        fp = FieldPin("test", PinType.STRING, widget_override="combo")
        with pytest.raises(AttributeError):
            fp.widget_override = "text"  # type: ignore[misc]


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


class TestConvertToModel:
    """Tests for display-value -> model-value conversion."""

    def test_int_from_string(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_model

        fp = FieldPin("amount", PinType.INT)
        assert convert_to_model(fp, "5") == 5

    def test_float_from_string(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_model

        fp = FieldPin("energy", PinType.FLOAT)
        assert convert_to_model(fp, "42.5") == 42.5

    def test_bool_passthrough(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_model

        fp = FieldPin("copied", PinType.BOOL)
        assert convert_to_model(fp, True) is True
        assert convert_to_model(fp, False) is False

    def test_csv_splits_string(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_model

        fp = FieldPin("linked_ids", PinType.CSV)
        assert convert_to_model(fp, "Gold, Silver, Lead") == ["Gold", "Silver", "Lead"]

    def test_csv_empty_string_returns_empty_list(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_model

        fp = FieldPin("linked_ids", PinType.CSV)
        assert convert_to_model(fp, "") == []

    def test_enum_tristate_auto_to_none(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_model

        fp = FieldPin(
            "force_unlock", PinType.ENUM, nullable=True, enum_items=["auto", "YES", "NO"]
        )
        assert convert_to_model(fp, "auto") is None

    def test_enum_tristate_yes_to_true(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_model

        fp = FieldPin(
            "force_unlock", PinType.ENUM, nullable=True, enum_items=["auto", "YES", "NO"]
        )
        assert convert_to_model(fp, "YES") is True

    def test_enum_tristate_no_to_false(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_model

        fp = FieldPin(
            "force_unlock", PinType.ENUM, nullable=True, enum_items=["auto", "YES", "NO"]
        )
        assert convert_to_model(fp, "NO") is False

    def test_enum_nullable_empty_to_none(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_model

        fp = FieldPin(
            "pda_group", PinType.ENUM, nullable=True, enum_items=["", "Resources", "Survival"]
        )
        assert convert_to_model(fp, "") is None

    def test_enum_nullable_value_passthrough(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_model

        fp = FieldPin(
            "pda_group", PinType.ENUM, nullable=True, enum_items=["", "Resources", "Survival"]
        )
        assert convert_to_model(fp, "Resources") == "Resources"

    def test_string_nullable_empty_to_none(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_model

        fp = FieldPin("functional_id", PinType.STRING, nullable=True)
        assert convert_to_model(fp, "") is None

    def test_string_nullable_value_passthrough(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_model

        fp = FieldPin("functional_id", PinType.STRING, nullable=True)
        assert convert_to_model(fp, "Knife") == "Knife"

    def test_string_non_nullable_empty_stays_empty(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_model

        fp = FieldPin("item_id", PinType.STRING)
        assert convert_to_model(fp, "") == ""


class TestConvertToDisplay:
    """Tests for model-value -> display-value conversion."""

    def test_csv_list_to_string(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_display

        fp = FieldPin("linked_ids", PinType.CSV)
        assert convert_to_display(fp, ["Gold", "Silver"]) == "Gold, Silver"

    def test_csv_empty_list_to_empty_string(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_display

        fp = FieldPin("linked_ids", PinType.CSV)
        assert convert_to_display(fp, []) == ""

    def test_csv_float_list(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_display

        fp = FieldPin("color_tint", PinType.CSV)
        assert convert_to_display(fp, [0.5, 0.3, 0.8]) == "0.5, 0.3, 0.8"

    def test_nullable_bool_none_to_auto(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_display

        fp = FieldPin(
            "force_unlock", PinType.ENUM, nullable=True, enum_items=["auto", "YES", "NO"]
        )
        assert convert_to_display(fp, None) == "auto"

    def test_nullable_bool_true_to_yes(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_display

        fp = FieldPin(
            "force_unlock", PinType.ENUM, nullable=True, enum_items=["auto", "YES", "NO"]
        )
        assert convert_to_display(fp, True) == "YES"

    def test_nullable_bool_false_to_no(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_display

        fp = FieldPin(
            "force_unlock", PinType.ENUM, nullable=True, enum_items=["auto", "YES", "NO"]
        )
        assert convert_to_display(fp, False) == "NO"

    def test_nullable_enum_none_to_empty(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_display

        fp = FieldPin("pda_group", PinType.ENUM, nullable=True, enum_items=["", "Resources"])
        assert convert_to_display(fp, None) == ""

    def test_nullable_string_none_to_empty(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_display

        fp = FieldPin("functional_id", PinType.STRING, nullable=True)
        assert convert_to_display(fp, None) == ""

    def test_non_nullable_none_uses_default(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_display

        fp = FieldPin("amount", PinType.INT, default=1)
        assert convert_to_display(fp, None) == 1

    def test_non_nullable_none_no_default_uses_empty(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_display

        fp = FieldPin("item_id", PinType.STRING)
        assert convert_to_display(fp, None) == ""

    def test_bool_passthrough(self):
        from craftgraph.pin_registry import FieldPin, PinType, convert_to_display

        fp = FieldPin("copied", PinType.BOOL, default=False)
        assert convert_to_display(fp, True) is True
        assert convert_to_display(fp, False) is False
