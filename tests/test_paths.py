"""Tests for path detection utilities."""

from __future__ import annotations

from pathlib import Path

import pytest

from craftgraph.paths import cc3_assets, cc3_working_files, default_project_folder, detect_subnautica_cc3_path

# The segment chain that detect_subnautica_cc3_path walks for each root.
_TAIL = Path("steamapps/common/Subnautica/BepInEx/plugins/CustomCraft3")


class TestDetectSubnauticaCc3Path:
    """detect_subnautica_cc3_path() scans candidate roots for the CC3 folder."""

    def test_returns_first_matching_root(self, tmp_path: Path) -> None:
        root_a = tmp_path / "RootA"
        target = root_a / _TAIL
        target.mkdir(parents=True)

        result = detect_subnautica_cc3_path(roots=[root_a])
        assert result == target

    def test_skips_missing_root_tries_next(self, tmp_path: Path) -> None:
        missing = tmp_path / "Missing"
        good = tmp_path / "Good"
        target = good / _TAIL
        target.mkdir(parents=True)

        result = detect_subnautica_cc3_path(roots=[missing, good])
        assert result == target

    def test_returns_none_when_nothing_found(self, tmp_path: Path) -> None:
        empty_a = tmp_path / "EmptyA"
        empty_a.mkdir()
        empty_b = tmp_path / "EmptyB"
        empty_b.mkdir()

        result = detect_subnautica_cc3_path(roots=[empty_a, empty_b])
        assert result is None

    def test_returns_none_for_empty_roots_list(self) -> None:
        result = detect_subnautica_cc3_path(roots=[])
        assert result is None

    def test_partial_path_does_not_match(self, tmp_path: Path) -> None:
        """A root with only steamapps/common but no deeper folders should not match."""
        root = tmp_path / "Partial"
        (root / "steamapps" / "common").mkdir(parents=True)

        result = detect_subnautica_cc3_path(roots=[root])
        assert result is None

    def test_walks_segments_incrementally(self, tmp_path: Path) -> None:
        """The first root is missing midway; the second has the full chain."""
        bad_root = tmp_path / "BadRoot"
        # Only create up to Subnautica -- BepInEx missing
        (bad_root / "steamapps" / "common" / "Subnautica").mkdir(parents=True)

        good_root = tmp_path / "GoodRoot"
        (good_root / _TAIL).mkdir(parents=True)

        result = detect_subnautica_cc3_path(roots=[bad_root, good_root])
        assert result == good_root / _TAIL

    def test_uses_default_roots_when_none(self) -> None:
        """Calling without roots= uses the built-in Windows Steam candidates."""
        # We can't assert a specific result (depends on machine), but it
        # must return Path or None without raising.
        result = detect_subnautica_cc3_path()
        assert result is None or isinstance(result, Path)


class TestDefaultProjectFolder:
    """default_project_folder() returns ~/Documents/CraftGraph."""

    def test_returns_path_under_documents(self) -> None:
        result = default_project_folder()
        assert isinstance(result, Path)
        assert result.name == "CraftGraph"
        assert result.parent.name == "Documents"

    def test_is_under_home(self) -> None:
        result = default_project_folder()
        assert result.is_relative_to(Path.home())


class TestCc3Subfolders:
    """cc3_working_files() and cc3_assets() derive known subfolder paths."""

    def test_working_files_returns_subfolder_when_set(self) -> None:
        result = cc3_working_files("/fake/CustomCraft3")
        assert result == str(Path("/fake/CustomCraft3/WorkingFiles"))

    def test_working_files_returns_empty_when_empty(self) -> None:
        assert cc3_working_files("") == ""

    def test_assets_returns_subfolder_when_set(self) -> None:
        result = cc3_assets("/fake/CustomCraft3")
        assert result == str(Path("/fake/CustomCraft3/Assets"))

    def test_assets_returns_empty_when_empty(self) -> None:
        assert cc3_assets("") == ""
