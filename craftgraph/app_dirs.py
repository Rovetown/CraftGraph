"""Platform-standard application directories for CraftGraph.

Uses ``platformdirs`` so that config, data, cache, and log files land in the
OS-idiomatic location on every platform:

- **Windows:** ``%LOCALAPPDATA%\\CraftGraph`` for everything (config + data +
  cache + logs as subdirs). ``PlatformDirs`` is constructed with the default
  ``roaming=False``, so the roaming ``%APPDATA%`` tree is never used.
- **macOS:** ``~/Library/Application Support/CraftGraph``
- **Linux:** ``~/.config/CraftGraph`` (config), ``~/.local/share/CraftGraph`` (data),
  ``~/.cache/CraftGraph`` (cache)

No Qt imports -- pure paths + optional one-time migration from the legacy
``~/.craftgraph/`` location.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from pathlib import Path

from platformdirs import PlatformDirs

from craftgraph.config import get_config

logger = logging.getLogger(__name__)

_APP_NAME = "CraftGraph"

_dirs = PlatformDirs(_APP_NAME, appauthor=False, ensure_exists=False)


# -- Build-mode detection ------------------------------------------------------


_DEV_ENV_TRUE = frozenset({"1", "true", "yes", "on"})


def is_dev() -> bool:
    """Return True when running from source (dev) rather than a PyInstaller bundle.

    Used to gate diagnostic features (frame-budget logs, paint timing, etc.)
    that should not fire in a shipped binary. Two signals:

    - ``CRAFTGRAPH_DEV`` env var forces the answer regardless of how the
      app was launched. Accepts ``1`` / ``true`` / ``yes`` / ``on`` (case
      insensitive). Useful for opting a release binary into dev diagnostics
      when reproducing a bug, or for forcing dev-off in tests.
    - ``sys.frozen`` is set by PyInstaller bundles. False = source install.

    The env var takes precedence; on its absence the frozen attribute decides.
    """
    raw = os.environ.get("CRAFTGRAPH_DEV")
    if raw is not None:
        return raw.strip().lower() in _DEV_ENV_TRUE
    return not getattr(sys, "frozen", False)


def perf_diagnostics_enabled() -> bool:
    """Return True when perf diagnostics (frame-budget logs, perf.log, etc.) should run.

    Two paths:

    - Dev builds: always on. ``is_dev() == True`` short-circuits to True so
      developers see frame-budget warnings and ``perf.log`` records without
      having to enable anything.
    - Release builds: off by default. The user can opt in via Settings ->
      General -> Diagnostics, which writes ``perf_diagnostics_enabled``
      into ``settings.json``.

    Loading the setting from disk on every check is fine -- it's a single
    JSON read of a small file and the call sites are not in hot paths
    (frame_tick happens at ~60 Hz at most; everything else is per-action).
    """
    if is_dev():
        return True
    return bool(load_setting("perf_diagnostics_enabled", False))


# -- Public directory accessors ------------------------------------------------


def config_dir() -> Path:
    """User config directory.

    Stores settings, the recent-files list, and other small user preferences.

    - Windows: ``%LOCALAPPDATA%/CraftGraph`` (``PlatformDirs`` defaults to
      ``roaming=False``, so this is the Local AppData tree, not the
      roaming ``%APPDATA%`` tree.)
    - macOS:   ``~/Library/Application Support/CraftGraph``
    - Linux:   ``~/.config/CraftGraph``
    """
    return Path(_dirs.user_config_dir)


def data_dir() -> Path:
    """User data directory.

    Stores larger persistent data. On Windows this is the same Local AppData
    folder as ``config_dir()``; on Linux it is a separate path.

    - Windows: ``%LOCALAPPDATA%/CraftGraph``
    - macOS:   ``~/Library/Application Support/CraftGraph``
    - Linux:   ``~/.local/share/CraftGraph``
    """
    return Path(_dirs.user_data_dir)


def cache_dir() -> Path:
    """User cache directory.

    Stores expendable data (thumbnails, temporary build artifacts).

    - Windows: ``%LOCALAPPDATA%/CraftGraph/Cache``
    - macOS:   ``~/Library/Caches/CraftGraph``
    - Linux:   ``~/.cache/CraftGraph``
    """
    return Path(_dirs.user_cache_dir)


def log_dir() -> Path:
    """User log directory.

    Stores application log files.

    - Windows: ``%LOCALAPPDATA%/CraftGraph/Logs``
    - macOS:   ``~/Library/Logs/CraftGraph``
    - Linux:   ``~/.local/state/CraftGraph/log``
    """
    return Path(_dirs.user_log_dir)


def documents_dir() -> Path:
    """User documents directory for CraftGraph projects.

    This is the default location for new projects and the initial
    browse directory in Open/Save dialogs.

    - Windows: ``~/Documents/CraftGraph``
    - macOS:   ``~/Documents/CraftGraph``
    - Linux:   ``~/Documents/CraftGraph``
    """
    return Path(_dirs.user_documents_dir) / _APP_NAME


# -- Concrete file paths -------------------------------------------------------


def recent_files_path() -> Path:
    """Path to the recent-files JSON store."""
    return config_dir() / "recent.json"


def settings_path() -> Path:
    """Path to the application settings JSON store."""
    return config_dir() / "settings.json"


_SettingValue = str | int | float | bool


def load_setting(key: str, default: _SettingValue) -> _SettingValue:
    """Read a single setting from ``settings.json``.

    Returns the native JSON value (str, int, float, bool) stored under
    *key*, or *default* if the file is missing, corrupt, or lacks the key.
    """
    path = settings_path()
    if not path.is_file():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("settings.json is corrupt, returning default for %r: %s", key, exc)
        return default
    if not isinstance(data, dict) or key not in data:
        return default
    value = data[key]
    if isinstance(value, str | int | float | bool):
        return value
    return default


def save_setting(key: str, value: _SettingValue) -> None:
    """Write a single setting to ``settings.json``, preserving other keys."""
    path = settings_path()
    data: dict[str, object] = {"version": 1}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("settings.json is corrupt, starting fresh: %s", exc)
            data = {"version": 1}
    data[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# -- Icon paths ----------------------------------------------------------------


def _icon_name() -> str:
    """Return the platform-appropriate icon filename."""
    if sys.platform == "win32":
        return "craftgraph.ico"
    if sys.platform == "darwin":
        return "craftgraph.icns"
    return "craftgraph.png"


def bundled_icon_path() -> Path:
    """Path to the app icon shipped inside the package.

    Returns the path even if the file does not yet exist (the caller
    should check ``.exists()`` before using it).
    """
    return bundled_icon_dir() / _icon_name()


def bundled_icon_dir() -> Path:
    """Directory containing bundled icon files."""
    return Path(__file__).parent / get_config().paths.icons_subdir


# -- Legacy migration -----------------------------------------------------------

_LEGACY_DIR_NAME = ".craftgraph"


def _legacy_dir() -> Path:
    return Path.home() / _LEGACY_DIR_NAME


def migrate_legacy_config() -> None:
    """Copy files from ``~/.craftgraph/`` to the new config directory.

    Runs once on startup. Skips silently if the legacy directory does not
    exist or if the target file already exists (new location wins).
    After a successful copy the legacy file is left in place so the user
    can verify and delete it manually.
    """
    legacy = _legacy_dir()
    if not legacy.is_dir():
        return

    target = config_dir()
    target.mkdir(parents=True, exist_ok=True)

    for src_file in legacy.iterdir():
        if not src_file.is_file():
            continue
        dest = target / src_file.name
        if dest.exists():
            logger.debug("Skipping migration of %s (already exists at %s)", src_file, dest)
            continue
        shutil.copy2(src_file, dest)
        logger.info("Migrated %s -> %s", src_file, dest)
