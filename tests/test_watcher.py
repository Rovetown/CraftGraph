"""Tests for the file watcher module.

Tests cover:
- Event filtering: only .txt files trigger rebuilds, directories are ignored
- Per-file cache: add, update, and delete operations
- Debouncing: rapid events coalesce into a single rebuild
- Error handling: unparseable files keep the previously cached version
- Integration: temp directory with real file writes triggers rebuilds
"""

import time
from pathlib import Path
from unittest.mock import MagicMock

from craftgraph.models import BlockType, Ingredient, ModifiedRecipe, ParsedFile
from craftgraph.watcher import _RecipeEventHandler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_parsed_file(
    path: Path,
    item_id: str = "Titanium",
) -> ParsedFile:
    """Create a minimal ParsedFile for cache testing."""
    pf = ParsedFile(source_path=path, block_type=BlockType.MODIFIED_RECIPES)
    pf.modified_recipes = [
        ModifiedRecipe(
            item_id=item_id,
            ingredients=[Ingredient("ScrapMetal", 1)],
        ),
    ]
    return pf


def _make_handler(
    tmp_path: Path,
    callback: MagicMock | None = None,
) -> _RecipeEventHandler:
    """Create a handler with a mock callback, skipping initial_parse."""
    cb = callback or MagicMock()
    return _RecipeEventHandler(tmp_path, cb)


def _make_event(
    src_path: str,
    *,
    is_directory: bool = False,
) -> MagicMock:
    """Create a mock FileSystemEvent."""
    event = MagicMock()
    event.src_path = src_path
    event.is_directory = is_directory
    return event


# ---------------------------------------------------------------------------
# Event filtering
# ---------------------------------------------------------------------------


class TestEventFiltering:
    """Only .txt file events should trigger rebuilds."""

    def test_txt_file_is_relevant(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path)
        event = _make_event(str(tmp_path / "recipes.txt"))
        assert handler._is_relevant(event) is True

    def test_non_txt_file_ignored(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path)
        for ext in [".py", ".json", ".md", ".png", ".cfg"]:
            event = _make_event(str(tmp_path / f"file{ext}"))
            assert handler._is_relevant(event) is False

    def test_directory_event_ignored(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path)
        event = _make_event(str(tmp_path / "subdir"), is_directory=True)
        assert handler._is_relevant(event) is False

    def test_txt_case_insensitive(self, tmp_path: Path) -> None:
        handler = _make_handler(tmp_path)
        event = _make_event(str(tmp_path / "RECIPES.TXT"))
        assert handler._is_relevant(event) is True


# ---------------------------------------------------------------------------
# File cache operations
# ---------------------------------------------------------------------------


class TestFileCache:
    """Test the per-file parse cache."""

    def test_reparse_adds_to_cache(self, tmp_path: Path) -> None:
        """A valid .txt file is added to the cache after reparse."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:(ItemID:Titanium;Ingredients:(ItemID:ScrapMetal;Required:1;););",
            encoding="utf-8",
        )
        handler = _make_handler(tmp_path)

        handler._reparse_file(recipe_file)

        assert recipe_file in handler._cache
        assert handler._cache[recipe_file].modified_recipes[0].item_id == "Titanium"

    def test_reparse_updates_existing_cache(self, tmp_path: Path) -> None:
        """Re-parsing a file replaces the old cached version."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:(ItemID:Glass;Ingredients:(ItemID:Quartz;Required:5;););",
            encoding="utf-8",
        )
        handler = _make_handler(tmp_path)
        handler._reparse_file(recipe_file)

        # Now update the file
        recipe_file.write_text(
            "ModifiedRecipes:(ItemID:Diamond;Ingredients:(ItemID:Carbon;Required:3;););",
            encoding="utf-8",
        )
        handler._reparse_file(recipe_file)

        assert handler._cache[recipe_file].modified_recipes[0].item_id == "Diamond"

    def test_delete_removes_from_cache(self, tmp_path: Path) -> None:
        """Deleting a file removes it from the cache."""
        recipe_file = tmp_path / "test.txt"
        handler = _make_handler(tmp_path)
        # Manually seed the cache
        handler._cache[recipe_file] = _make_parsed_file(recipe_file)

        event = _make_event(str(recipe_file))
        handler.on_deleted(event)

        assert recipe_file not in handler._cache

    def test_reparse_empty_file_removes_from_cache(self, tmp_path: Path) -> None:
        """An empty/comment-only file is removed from the cache."""
        recipe_file = tmp_path / "test.txt"
        handler = _make_handler(tmp_path)
        # Seed with a valid entry
        handler._cache[recipe_file] = _make_parsed_file(recipe_file)

        # Write an empty file
        recipe_file.write_text("# just a comment", encoding="utf-8")
        handler._reparse_file(recipe_file)

        assert recipe_file not in handler._cache

    def test_reparse_nonexistent_file_is_noop(self, tmp_path: Path) -> None:
        """Re-parsing a file that doesn't exist does nothing."""
        handler = _make_handler(tmp_path)
        handler._reparse_file(tmp_path / "gone.txt")
        assert len(handler._cache) == 0


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Unparseable files should keep the previous cached version."""

    def test_parse_error_keeps_cached_version(self, tmp_path: Path) -> None:
        """If a file fails to parse, the old cache entry is preserved."""
        recipe_file = tmp_path / "test.txt"
        handler = _make_handler(tmp_path)

        # Seed with a good version
        good_parsed = _make_parsed_file(recipe_file, item_id="Titanium")
        handler._cache[recipe_file] = good_parsed

        # Write broken content
        recipe_file.write_text("this is not valid EasyMarkup {{{{", encoding="utf-8")
        handler._reparse_file(recipe_file)

        # Cache should still have the old good version
        assert recipe_file in handler._cache
        assert handler._cache[recipe_file].modified_recipes[0].item_id == "Titanium"

    def test_parse_error_with_empty_cache_stays_empty(self, tmp_path: Path) -> None:
        """A file that was never cached and fails to parse stays absent."""
        recipe_file = tmp_path / "broken.txt"
        recipe_file.write_text("invalid content )))((:", encoding="utf-8")
        handler = _make_handler(tmp_path)

        handler._reparse_file(recipe_file)

        assert recipe_file not in handler._cache


# ---------------------------------------------------------------------------
# Debouncing
# ---------------------------------------------------------------------------


class TestDebouncing:
    """Rapid events should coalesce into a single rebuild."""

    def test_rapid_events_coalesce(self, tmp_path: Path) -> None:
        """Multiple rapid _schedule_rebuild calls produce one _rebuild call."""
        callback = MagicMock()
        handler = _make_handler(tmp_path, callback)

        # Seed cache so _rebuild has something to work with
        recipe_file = tmp_path / "test.txt"
        handler._cache[recipe_file] = _make_parsed_file(recipe_file)

        # Fire 5 rapid schedule calls
        for _ in range(5):
            handler._schedule_rebuild()

        # Wait for debounce to fire (0.3s + buffer)
        time.sleep(0.6)

        # Should have coalesced into exactly 1 callback
        assert callback.call_count == 1

    def test_spaced_events_trigger_separate_rebuilds(self, tmp_path: Path) -> None:
        """Events spaced beyond the debounce window trigger separate rebuilds."""
        callback = MagicMock()
        handler = _make_handler(tmp_path, callback)

        recipe_file = tmp_path / "test.txt"
        handler._cache[recipe_file] = _make_parsed_file(recipe_file)

        handler._schedule_rebuild()
        time.sleep(0.6)  # Wait for first to fire

        handler._schedule_rebuild()
        time.sleep(0.6)  # Wait for second to fire

        assert callback.call_count == 2


# ---------------------------------------------------------------------------
# Rebuild pipeline
# ---------------------------------------------------------------------------


class TestRebuildPipeline:
    """Test the full rebuild: cache -> graph -> cycles -> callback."""

    def test_rebuild_invokes_callback_with_correct_args(self, tmp_path: Path) -> None:
        """_rebuild passes parsed files, graph, and cycles to the callback."""
        callback = MagicMock()
        handler = _make_handler(tmp_path, callback)

        recipe_file = tmp_path / "recipes.txt"
        handler._cache[recipe_file] = _make_parsed_file(recipe_file, item_id="Glass")

        handler._rebuild()

        callback.assert_called_once()
        parsed_files, graph, cycles = callback.call_args[0]
        assert len(parsed_files) == 1
        assert "Glass" in graph.nodes
        assert "ScrapMetal" in graph.nodes
        assert cycles == []

    def test_rebuild_empty_cache(self, tmp_path: Path) -> None:
        """Rebuilding with an empty cache produces an empty graph."""
        callback = MagicMock()
        handler = _make_handler(tmp_path, callback)

        handler._rebuild()

        callback.assert_called_once()
        parsed_files, graph, cycles = callback.call_args[0]
        assert parsed_files == []
        assert graph.number_of_nodes() == 0
        assert cycles == []


# ---------------------------------------------------------------------------
# Initial parse
# ---------------------------------------------------------------------------


class TestInitialParse:
    """Test initial_parse populates the cache from a real directory."""

    def test_initial_parse_populates_cache(self, tmp_path: Path) -> None:
        """initial_parse walks the directory and caches all valid .txt files."""
        (tmp_path / "a.txt").write_text(
            "ModifiedRecipes:(ItemID:Glass;Ingredients:(ItemID:Quartz;Required:5;););",
            encoding="utf-8",
        )
        (tmp_path / "b.txt").write_text(
            "ModifiedRecipes:(ItemID:Titanium;Ingredients:(ItemID:ScrapMetal;Required:1;););",
            encoding="utf-8",
        )
        # Non-.txt file should not appear in cache
        (tmp_path / "readme.md").write_text("# README", encoding="utf-8")

        callback = MagicMock()
        handler = _RecipeEventHandler(tmp_path, callback)
        handler.initial_parse()

        assert len(handler._cache) == 2
        callback.assert_called_once()

    def test_initial_parse_skips_broken_files(self, tmp_path: Path) -> None:
        """initial_parse skips files that fail to parse."""
        (tmp_path / "good.txt").write_text(
            "ModifiedRecipes:(ItemID:Glass;Ingredients:(ItemID:Quartz;Required:5;););",
            encoding="utf-8",
        )
        (tmp_path / "broken.txt").write_text("not valid markup", encoding="utf-8")

        callback = MagicMock()
        handler = _RecipeEventHandler(tmp_path, callback)
        handler.initial_parse()

        # parse_directory already skips broken files, so only the good one is cached
        assert len(handler._cache) == 1


# ---------------------------------------------------------------------------
# Integration: full event flow
# ---------------------------------------------------------------------------


class TestIntegration:
    """End-to-end test: write files and verify the event handler responds."""

    def test_on_created_triggers_rebuild(self, tmp_path: Path) -> None:
        """Simulating a created event re-parses the file and schedules a rebuild."""
        recipe_file = tmp_path / "new_recipe.txt"
        recipe_file.write_text(
            "ModifiedRecipes:(ItemID:Copper;Ingredients:(ItemID:CopperOre;Required:1;););",
            encoding="utf-8",
        )

        callback = MagicMock()
        handler = _make_handler(tmp_path, callback)

        event = _make_event(str(recipe_file))
        handler.on_created(event)

        # Wait for debounce
        time.sleep(0.6)

        assert recipe_file in handler._cache
        assert handler._cache[recipe_file].modified_recipes[0].item_id == "Copper"
        callback.assert_called_once()

    def test_on_modified_updates_and_rebuilds(self, tmp_path: Path) -> None:
        """Simulating a modified event updates the cache and rebuilds."""
        recipe_file = tmp_path / "recipe.txt"
        recipe_file.write_text(
            "ModifiedRecipes:(ItemID:Silver;Ingredients:(ItemID:SilverOre;Required:2;););",
            encoding="utf-8",
        )

        callback = MagicMock()
        handler = _make_handler(tmp_path, callback)
        handler._reparse_file(recipe_file)

        # Modify the file
        recipe_file.write_text(
            "ModifiedRecipes:(ItemID:Gold;Ingredients:(ItemID:GoldOre;Required:3;););",
            encoding="utf-8",
        )
        event = _make_event(str(recipe_file))
        handler.on_modified(event)

        time.sleep(0.6)

        assert handler._cache[recipe_file].modified_recipes[0].item_id == "Gold"
        callback.assert_called_once()

    def test_non_txt_events_do_not_trigger_rebuild(self, tmp_path: Path) -> None:
        """Events on non-.txt files are completely ignored."""
        callback = MagicMock()
        handler = _make_handler(tmp_path, callback)

        for name in ["data.json", "notes.md", "image.png"]:
            event = _make_event(str(tmp_path / name))
            handler.on_modified(event)
            handler.on_created(event)
            handler.on_deleted(event)

        time.sleep(0.6)
        callback.assert_not_called()
