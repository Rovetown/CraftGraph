"""Tests for craftgraph.file_assoc -- cross-platform file association."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from craftgraph import file_assoc


class TestExecutablePath:
    """executable_path() returns a Path regardless of environment."""

    def test_returns_path(self) -> None:
        result = file_assoc.executable_path()
        assert isinstance(result, Path)

    def test_frozen_returns_sys_executable(self) -> None:
        with patch.object(sys, "frozen", True, create=True):
            result = file_assoc.executable_path()
            assert result == Path(sys.executable)


class TestPublicAPI:
    """register/unregister/is_registered dispatch to platform implementations."""

    def test_register_returns_string(self) -> None:
        # On Windows, actually registering would touch the registry.
        # Mock the platform implementation.
        if sys.platform == "win32":
            with patch.object(file_assoc, "_register_windows", return_value="mocked"):
                result = file_assoc.register()
                assert result == "mocked"
        elif sys.platform == "linux":
            with patch.object(file_assoc, "_register_linux", return_value="mocked"):
                result = file_assoc.register()
                assert result == "mocked"
        else:
            result = file_assoc.register()
            assert isinstance(result, str)

    def test_unregister_returns_string(self) -> None:
        if sys.platform == "win32":
            with patch.object(file_assoc, "_unregister_windows", return_value="mocked"):
                result = file_assoc.unregister()
                assert result == "mocked"
        elif sys.platform == "linux":
            with patch.object(file_assoc, "_unregister_linux", return_value="mocked"):
                result = file_assoc.unregister()
                assert result == "mocked"
        else:
            result = file_assoc.unregister()
            assert isinstance(result, str)

    def test_is_registered_returns_bool(self) -> None:
        if sys.platform == "win32":
            with patch.object(file_assoc, "_is_registered_windows", return_value=False):
                assert file_assoc.is_registered() is False
        elif sys.platform == "linux":
            with patch.object(file_assoc, "_is_registered_linux", return_value=False):
                assert file_assoc.is_registered() is False
        else:
            assert file_assoc.is_registered() is False


class TestIconResolution:
    """Icon path resolution selects the right format per platform."""

    def test_windows_icon_is_ico(self) -> None:
        if sys.platform != "win32":
            pytest.skip("Windows-only test")
        exe = str(file_assoc.executable_path())
        result = file_assoc._resolve_icon_windows(exe)
        # Without the .ico file, falls back to exe,0
        assert result.endswith(",0") or result.endswith(".ico")


class TestWindowsRegistry:
    """Windows registry operations (mocked -- no real registry changes)."""

    @pytest.fixture(autouse=True)
    def _skip_non_windows(self) -> None:
        if sys.platform != "win32":
            pytest.skip("Windows-only test")

    def test_register_creates_keys(self) -> None:
        mock_set = MagicMock()
        mock_notify = MagicMock()
        with (
            patch.object(file_assoc, "_winreg_set", mock_set),
            patch.object(file_assoc, "_notify_shell_windows", mock_notify),
        ):
            result = file_assoc._register_windows()

        assert mock_set.call_count == 4  # ext, description, icon, command
        assert mock_notify.called
        assert "CraftGraph.Project" in result

    def test_unregister_deletes_keys(self) -> None:
        mock_delete = MagicMock(return_value=True)
        mock_notify = MagicMock()
        with (
            patch.object(file_assoc, "_winreg_delete", mock_delete),
            patch.object(file_assoc, "_notify_shell_windows", mock_notify),
        ):
            result = file_assoc._unregister_windows()

        assert mock_delete.call_count == 6  # all registry key paths
        assert mock_notify.called
        assert "Removed" in result

    def test_is_registered_false_when_key_missing(self) -> None:
        import winreg

        with patch.object(winreg, "OpenKey", side_effect=FileNotFoundError):
            assert file_assoc._is_registered_windows() is False


class TestLinuxFiles:
    """Linux XDG file generation (mocked -- no real file writes)."""

    @pytest.fixture(autouse=True)
    def _skip_non_linux(self) -> None:
        if sys.platform != "linux":
            pytest.skip("Linux-only test")

    def test_register_creates_files(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        home.mkdir()
        with (
            patch("pathlib.Path.home", return_value=home),
            patch("shutil.which", return_value=None),
        ):
            result = file_assoc._register_linux()

        mime_file = home / ".local" / "share" / "mime" / "packages" / "craftgraph.xml"
        desktop_file = home / ".local" / "share" / "applications" / "craftgraph.desktop"
        assert mime_file.exists()
        assert desktop_file.exists()
        assert "application/x-craftgraph" in mime_file.read_text(encoding="utf-8")
        assert "craftgraph gui %f" in desktop_file.read_text(encoding="utf-8")
        assert "MIME" in result or "Wrote" in result

    def test_unregister_removes_files(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        mime_dir = home / ".local" / "share" / "mime" / "packages"
        apps_dir = home / ".local" / "share" / "applications"
        mime_dir.mkdir(parents=True)
        apps_dir.mkdir(parents=True)
        (mime_dir / "craftgraph.xml").write_text("x", encoding="utf-8")
        (apps_dir / "craftgraph.desktop").write_text("x", encoding="utf-8")

        with (
            patch("pathlib.Path.home", return_value=home),
            patch("shutil.which", return_value=None),
        ):
            result = file_assoc._unregister_linux()

        assert not (mime_dir / "craftgraph.xml").exists()
        assert not (apps_dir / "craftgraph.desktop").exists()
        assert "Removed" in result

    def test_is_registered_checks_desktop_file(self, tmp_path: Path) -> None:
        home = tmp_path / "home"
        apps_dir = home / ".local" / "share" / "applications"
        apps_dir.mkdir(parents=True)

        with patch("pathlib.Path.home", return_value=home):
            assert file_assoc._is_registered_linux() is False

        (apps_dir / "craftgraph.desktop").write_text("x", encoding="utf-8")

        with patch("pathlib.Path.home", return_value=home):
            assert file_assoc._is_registered_linux() is True


class TestMacOSGuidance:
    """macOS returns guidance text instead of doing runtime registration."""

    @pytest.fixture(autouse=True)
    def _skip_non_macos(self) -> None:
        if sys.platform != "darwin":
            pytest.skip("macOS-only test")

    def test_register_returns_plist_guidance(self) -> None:
        result = file_assoc._register_macos()
        assert "Info.plist" in result
        assert "CFBundleDocumentTypes" in result


class TestNoQtImports:
    """The module must not depend on Qt."""

    def test_no_pyside6_import(self) -> None:
        import importlib.util

        source = importlib.util.find_spec("craftgraph.file_assoc")
        assert source is not None
        assert source.origin is not None
        code = Path(source.origin).read_text(encoding="utf-8")
        assert "PySide6" not in code
        assert "NodeGraphQt" not in code
