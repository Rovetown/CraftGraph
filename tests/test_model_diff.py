"""Unit tests for the pure-data diff layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from craftgraph.model_diff import _model_key, compute_diff
from craftgraph.models import CraftingTab, ModifiedRecipe, ParsedFile


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


def _empty_pf(path: Path) -> ParsedFile:
    """Construct a ParsedFile with no entries for tests."""
    return ParsedFile(source_path=path)


class TestComputeDiffFileLevel:
    def test_unchanged_file(self, tmp_path):
        pf = _empty_pf(tmp_path / "a.txt")
        diff = compute_diff([pf], [pf])
        assert diff.unchanged_paths == [pf.source_path]
        assert diff.removed_paths == []
        assert diff.added_files == []
        assert diff.changed_files == []

    def test_added_file(self, tmp_path):
        new = _empty_pf(tmp_path / "new.txt")
        diff = compute_diff([], [new])
        assert diff.added_files == [new]
        assert diff.unchanged_paths == []
        assert diff.removed_paths == []
        assert diff.changed_files == []

    def test_removed_file(self, tmp_path):
        old = _empty_pf(tmp_path / "gone.txt")
        diff = compute_diff([old], [])
        assert diff.removed_paths == [old.source_path]

    def test_changed_file_empty_diff_when_content_equal(self, tmp_path):
        a = _empty_pf(tmp_path / "a.txt")
        b = _empty_pf(tmp_path / "a.txt")
        diff = compute_diff([a], [b])
        assert diff.unchanged_paths == [a.source_path]
        assert diff.changed_files == []


class TestComputeDiffEntryLevel:
    def test_added_entry(self, tmp_path):
        a = _empty_pf(tmp_path / "f.txt")
        b = _empty_pf(tmp_path / "f.txt")
        b.modified_recipes.append(ModifiedRecipe(item_id="Titanium"))
        diff = compute_diff([a], [b])
        assert len(diff.changed_files) == 1
        _, _, fd = diff.changed_files[0]
        assert len(fd.added) == 1
        assert fd.added[0].item_id == "Titanium"
        assert fd.removed == [] and fd.modified == []

    def test_removed_entry(self, tmp_path):
        a = _empty_pf(tmp_path / "f.txt")
        a.modified_recipes.append(ModifiedRecipe(item_id="Titanium"))
        b = _empty_pf(tmp_path / "f.txt")
        diff = compute_diff([a], [b])
        _, _, fd = diff.changed_files[0]
        assert len(fd.removed) == 1
        assert fd.removed[0].item_id == "Titanium"
        assert fd.added == [] and fd.modified == []

    def test_modified_entry(self, tmp_path):
        a = _empty_pf(tmp_path / "f.txt")
        a.modified_recipes.append(ModifiedRecipe(item_id="Titanium", amount_crafted=1))
        b = _empty_pf(tmp_path / "f.txt")
        b.modified_recipes.append(ModifiedRecipe(item_id="Titanium", amount_crafted=2))
        diff = compute_diff([a], [b])
        _, _, fd = diff.changed_files[0]
        assert len(fd.modified) == 1
        old, new = fd.modified[0]
        assert old.amount_crafted == 1 and new.amount_crafted == 2
        assert fd.added == [] and fd.removed == []

    def test_renamed_entry_is_remove_plus_add(self, tmp_path):
        """ItemID change is treated as remove(old) + add(new), by spec design."""
        a = _empty_pf(tmp_path / "f.txt")
        a.modified_recipes.append(ModifiedRecipe(item_id="OldName"))
        b = _empty_pf(tmp_path / "f.txt")
        b.modified_recipes.append(ModifiedRecipe(item_id="NewName"))
        diff = compute_diff([a], [b])
        _, _, fd = diff.changed_files[0]
        assert {e.item_id for e in fd.removed} == {"OldName"}
        assert {e.item_id for e in fd.added} == {"NewName"}
        assert fd.modified == []

    def test_distinct_classes_with_same_id_do_not_collide(self, tmp_path):
        """A ModifiedRecipe and a CraftingTab can both have the string 'Foo' as their key."""
        a = _empty_pf(tmp_path / "f.txt")
        a.modified_recipes.append(ModifiedRecipe(item_id="Foo"))
        b = _empty_pf(tmp_path / "f.txt")
        b.modified_recipes.append(ModifiedRecipe(item_id="Foo"))
        diff = compute_diff([a], [b])
        assert diff.unchanged_paths == [a.source_path]
