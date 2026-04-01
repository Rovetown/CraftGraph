"""Tests for craftgraph.recent -- recent files tracking."""

from __future__ import annotations

import json
from pathlib import Path

from craftgraph.recent import RecentFiles


class TestRecentFilesRoundTrip:
    """Add entries and read them back."""

    def test_add_folder_entry(self, tmp_path: Path) -> None:
        rf = RecentFiles(tmp_path / "recent.json")
        rf.add(tmp_path / "my_mod", "folder")

        assert len(rf.entries) == 1
        entry = rf.entries[0]
        assert entry.entry_type == "folder"
        assert entry.path == str((tmp_path / "my_mod").resolve())

    def test_add_project_entry(self, tmp_path: Path) -> None:
        rf = RecentFiles(tmp_path / "recent.json")
        rf.add(tmp_path / "my_mod.craftgraph", "project")

        assert len(rf.entries) == 1
        assert rf.entries[0].entry_type == "project"

    def test_most_recent_first(self, tmp_path: Path) -> None:
        rf = RecentFiles(tmp_path / "recent.json")
        rf.add(tmp_path / "first", "folder")
        rf.add(tmp_path / "second", "folder")
        rf.add(tmp_path / "third", "folder")

        names = [Path(e.path).name for e in rf.entries]
        assert names == ["third", "second", "first"]

    def test_timestamp_is_set(self, tmp_path: Path) -> None:
        rf = RecentFiles(tmp_path / "recent.json")
        rf.add(tmp_path / "mod", "folder")
        assert rf.entries[0].timestamp  # non-empty ISO string


class TestDeduplication:
    """Adding the same path twice moves it to the top, not duplicating."""

    def test_duplicate_moves_to_top(self, tmp_path: Path) -> None:
        rf = RecentFiles(tmp_path / "recent.json")
        rf.add(tmp_path / "alpha", "folder")
        rf.add(tmp_path / "beta", "folder")
        rf.add(tmp_path / "alpha", "folder")

        paths = [Path(e.path).name for e in rf.entries]
        assert paths == ["alpha", "beta"]

    def test_duplicate_updates_timestamp(self, tmp_path: Path) -> None:
        rf = RecentFiles(tmp_path / "recent.json")
        rf.add(tmp_path / "mod", "folder")
        ts1 = rf.entries[0].timestamp

        rf.add(tmp_path / "mod", "folder")
        ts2 = rf.entries[0].timestamp

        assert ts2 >= ts1


class TestMaxEntries:
    """Oldest entries are dropped when the list exceeds max."""

    def test_trim_on_add(self, tmp_path: Path) -> None:
        rf = RecentFiles(tmp_path / "recent.json", max_entries=3)
        for i in range(5):
            rf.add(tmp_path / f"mod_{i}", "folder")

        assert len(rf.entries) == 3
        names = [Path(e.path).name for e in rf.entries]
        assert names == ["mod_4", "mod_3", "mod_2"]

    def test_trim_on_max_decrease(self, tmp_path: Path) -> None:
        rf = RecentFiles(tmp_path / "recent.json", max_entries=5)
        for i in range(5):
            rf.add(tmp_path / f"mod_{i}", "folder")

        rf.max_entries = 2
        assert len(rf.entries) == 2
        names = [Path(e.path).name for e in rf.entries]
        assert names == ["mod_4", "mod_3"]


class TestRemove:
    """Remove a specific entry by path."""

    def test_remove_existing(self, tmp_path: Path) -> None:
        rf = RecentFiles(tmp_path / "recent.json")
        rf.add(tmp_path / "alpha", "folder")
        rf.add(tmp_path / "beta", "folder")

        rf.remove(tmp_path / "alpha")

        assert len(rf.entries) == 1
        assert Path(rf.entries[0].path).name == "beta"

    def test_remove_nonexistent_is_noop(self, tmp_path: Path) -> None:
        rf = RecentFiles(tmp_path / "recent.json")
        rf.add(tmp_path / "alpha", "folder")

        rf.remove(tmp_path / "does_not_exist")
        assert len(rf.entries) == 1


class TestClear:
    """Clear empties the list."""

    def test_clear_all(self, tmp_path: Path) -> None:
        rf = RecentFiles(tmp_path / "recent.json")
        rf.add(tmp_path / "a", "folder")
        rf.add(tmp_path / "b", "project")

        rf.clear()
        assert rf.entries == []


class TestPersistence:
    """Entries survive across instances (reloaded from disk)."""

    def test_reload_from_disk(self, tmp_path: Path) -> None:
        json_path = tmp_path / "recent.json"
        rf1 = RecentFiles(json_path)
        rf1.add(tmp_path / "mod_a", "folder")
        rf1.add(tmp_path / "proj.craftgraph", "project")

        rf2 = RecentFiles(json_path)
        assert len(rf2.entries) == 2
        assert rf2.entries[0].entry_type == "project"
        assert rf2.entries[1].entry_type == "folder"

    def test_clear_persists(self, tmp_path: Path) -> None:
        json_path = tmp_path / "recent.json"
        rf1 = RecentFiles(json_path)
        rf1.add(tmp_path / "mod", "folder")
        rf1.clear()

        rf2 = RecentFiles(json_path)
        assert rf2.entries == []


class TestCorruptFile:
    """Corrupt or missing files are handled gracefully."""

    def test_garbage_json(self, tmp_path: Path) -> None:
        json_path = tmp_path / "recent.json"
        json_path.write_text("not json at all {{{", encoding="utf-8")

        rf = RecentFiles(json_path)
        assert rf.entries == []

    def test_missing_file(self, tmp_path: Path) -> None:
        rf = RecentFiles(tmp_path / "nonexistent" / "recent.json")
        assert rf.entries == []

    def test_wrong_structure(self, tmp_path: Path) -> None:
        json_path = tmp_path / "recent.json"
        json_path.write_text('{"entries": [{"bad": true}]}', encoding="utf-8")

        rf = RecentFiles(json_path)
        assert rf.entries == []


class TestVersionField:
    """Written JSON contains the version marker."""

    def test_version_is_1(self, tmp_path: Path) -> None:
        json_path = tmp_path / "recent.json"
        rf = RecentFiles(json_path)
        rf.add(tmp_path / "mod", "folder")

        raw = json.loads(json_path.read_text(encoding="utf-8"))
        assert raw["version"] == 1
