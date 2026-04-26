"""Tests for craftgraph.app_dirs -- platform-standard directory resolution."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from craftgraph import app_dirs


class TestDirectoryAccessors:
    """Each accessor returns a Path ending with 'CraftGraph'."""

    def test_config_dir_returns_path(self) -> None:
        result = app_dirs.config_dir()
        assert isinstance(result, Path)
        assert result.name == "CraftGraph"

    def test_data_dir_returns_path(self) -> None:
        result = app_dirs.data_dir()
        assert isinstance(result, Path)
        assert result.name == "CraftGraph"

    def test_cache_dir_returns_path(self) -> None:
        result = app_dirs.cache_dir()
        assert isinstance(result, Path)

    def test_log_dir_returns_path(self) -> None:
        result = app_dirs.log_dir()
        assert isinstance(result, Path)

    def test_documents_dir_returns_path(self) -> None:
        result = app_dirs.documents_dir()
        assert isinstance(result, Path)
        assert result.name == "CraftGraph"

    def test_recent_files_path_is_inside_config(self) -> None:
        result = app_dirs.recent_files_path()
        assert result.name == "recent.json"
        assert result.parent == app_dirs.config_dir()


class TestPlatformPaths:
    """Verify that the paths match OS conventions."""

    def test_windows_config_uses_appdata(self) -> None:
        if sys.platform != "win32":
            return
        cfg = str(app_dirs.config_dir())
        assert "AppData" in cfg

    def test_windows_cache_uses_local(self) -> None:
        if sys.platform != "win32":
            return
        cache = str(app_dirs.cache_dir())
        assert "Local" in cache or "Cache" in cache

    def test_linux_config_uses_xdg(self) -> None:
        if sys.platform != "linux":
            return
        cfg = str(app_dirs.config_dir())
        assert ".config" in cfg

    def test_macos_config_uses_library(self) -> None:
        if sys.platform != "darwin":
            return
        cfg = str(app_dirs.config_dir())
        assert "Library" in cfg


class TestLegacyMigration:
    """One-time migration from ~/.craftgraph/ to the new config dir."""

    def test_migrates_recent_json(self, tmp_path: Path) -> None:
        legacy = tmp_path / ".craftgraph"
        legacy.mkdir()
        (legacy / "recent.json").write_text('{"version":1,"entries":[]}', encoding="utf-8")

        new_config = tmp_path / "new_config" / "CraftGraph"

        with (
            patch.object(app_dirs, "_legacy_dir", return_value=legacy),
            patch.object(app_dirs, "config_dir", return_value=new_config),
        ):
            app_dirs.migrate_legacy_config()

        assert (new_config / "recent.json").exists()
        contents = (new_config / "recent.json").read_text(encoding="utf-8")
        assert '"version"' in contents

    def test_does_not_overwrite_existing(self, tmp_path: Path) -> None:
        legacy = tmp_path / ".craftgraph"
        legacy.mkdir()
        (legacy / "recent.json").write_text("old data", encoding="utf-8")

        new_config = tmp_path / "new_config" / "CraftGraph"
        new_config.mkdir(parents=True)
        (new_config / "recent.json").write_text("new data", encoding="utf-8")

        with (
            patch.object(app_dirs, "_legacy_dir", return_value=legacy),
            patch.object(app_dirs, "config_dir", return_value=new_config),
        ):
            app_dirs.migrate_legacy_config()

        contents = (new_config / "recent.json").read_text(encoding="utf-8")
        assert contents == "new data"

    def test_noop_when_no_legacy_dir(self, tmp_path: Path) -> None:
        legacy = tmp_path / ".craftgraph"  # does not exist

        with patch.object(app_dirs, "_legacy_dir", return_value=legacy):
            app_dirs.migrate_legacy_config()  # should not raise

    def test_skips_subdirectories(self, tmp_path: Path) -> None:
        legacy = tmp_path / ".craftgraph"
        legacy.mkdir()
        (legacy / "recent.json").write_text("{}", encoding="utf-8")
        sub = legacy / "subdir"
        sub.mkdir()
        (sub / "nested.txt").write_text("nested", encoding="utf-8")

        new_config = tmp_path / "new_config" / "CraftGraph"

        with (
            patch.object(app_dirs, "_legacy_dir", return_value=legacy),
            patch.object(app_dirs, "config_dir", return_value=new_config),
        ):
            app_dirs.migrate_legacy_config()

        assert (new_config / "recent.json").exists()
        assert not (new_config / "subdir").exists()


class TestSettingsPersistence:
    def test_settings_path_under_config_dir(self) -> None:
        path = app_dirs.settings_path()
        assert path.parent == app_dirs.config_dir()
        assert path.name == "settings.json"

    def test_load_setting_default_when_missing(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        assert app_dirs.load_setting("on_launch", "welcome") == "welcome"

    def test_save_and_load_setting(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        app_dirs.save_setting("on_launch", "empty")
        assert app_dirs.load_setting("on_launch", "welcome") == "empty"

    def test_save_preserves_other_keys(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        app_dirs.save_setting("on_launch", "welcome")
        app_dirs.save_setting("other_key", "value")
        assert app_dirs.load_setting("on_launch", "") == "welcome"
        assert app_dirs.load_setting("other_key", "") == "value"

    def test_load_setting_corrupt_json(self, tmp_path: Path, monkeypatch: object) -> None:
        settings_file = tmp_path / "settings.json"
        settings_file.write_text("NOT JSON", encoding="utf-8")
        monkeypatch.setattr(app_dirs, "settings_path", lambda: settings_file)
        assert app_dirs.load_setting("on_launch", "welcome") == "welcome"

    def test_save_creates_parent_dir(self, tmp_path: Path, monkeypatch: object) -> None:
        deep_path = tmp_path / "sub" / "dir" / "settings.json"
        monkeypatch.setattr(app_dirs, "settings_path", lambda: deep_path)
        app_dirs.save_setting("on_launch", "empty")
        assert deep_path.exists()

    def test_settings_file_has_version(self, tmp_path: Path, monkeypatch: object) -> None:
        settings_file = tmp_path / "settings.json"
        monkeypatch.setattr(app_dirs, "settings_path", lambda: settings_file)
        app_dirs.save_setting("on_launch", "welcome")
        data = json.loads(settings_file.read_text(encoding="utf-8"))
        assert data["version"] == 1

    def test_save_and_load_bool(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        app_dirs.save_setting("backup_on_save", True)
        result = app_dirs.load_setting("backup_on_save", False)
        assert result is True
        assert isinstance(result, bool)

    def test_save_and_load_int(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        app_dirs.save_setting("auto_save_interval", 120)
        result = app_dirs.load_setting("auto_save_interval", 60)
        assert result == 120
        assert isinstance(result, int)

    def test_save_and_load_false(self, tmp_path: Path, monkeypatch: object) -> None:
        """False must not be confused with a missing key."""
        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        app_dirs.save_setting("check_for_updates", False)
        result = app_dirs.load_setting("check_for_updates", True)
        assert result is False

    def test_mixed_types_in_one_file(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        app_dirs.save_setting("on_launch", "welcome")
        app_dirs.save_setting("backup_on_save", True)
        app_dirs.save_setting("auto_save_interval", 90)
        assert app_dirs.load_setting("on_launch", "") == "welcome"
        assert app_dirs.load_setting("backup_on_save", False) is True
        assert app_dirs.load_setting("auto_save_interval", 60) == 90


class TestNoQtImports:
    """The module must not depend on Qt."""

    def test_no_pyside6_import(self) -> None:
        import importlib

        source = importlib.util.find_spec("craftgraph.app_dirs")
        assert source is not None
        assert source.origin is not None
        code = Path(source.origin).read_text(encoding="utf-8")
        assert "PySide6" not in code
        assert "NodeGraphQt" not in code
