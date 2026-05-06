"""Unit tests for the pure-data diff layer."""

from __future__ import annotations

import pytest

from craftgraph.model_diff import _model_key
from craftgraph.models import CraftingTab, ModifiedRecipe


class TestModelKey:
    def test_item_id_models(self):
        recipe = ModifiedRecipe(item_id="Titanium")
        assert _model_key(recipe) == (ModifiedRecipe, "Titanium")

    def test_tab_id_models(self):
        tab = CraftingTab(tab_id="MyTab")
        assert _model_key(tab) == (CraftingTab, "MyTab")

    def test_unsupported_raises(self):
        with pytest.raises(TypeError, match="unsupported entry type"):
            _model_key(object())
