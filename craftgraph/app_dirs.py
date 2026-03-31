"""Platform-standard application directories for CraftGraph.

Uses ``platformdirs`` so that config, data, cache, and log files land in the
OS-idiomatic location on every platform:

- **Windows:** ``%APPDATA%\\CraftGraph`` (config), ``%LOCALAPPDATA%\\CraftGraph`` (cache/logs)
- **macOS:** ``~/Library/Application Support/CraftGraph``
- **Linux:** ``~/.config/CraftGraph`` (config), ``~/.local/share/CraftGraph`` (data),
  ``~/.cache/CraftGraph`` (cache)

No Qt imports -- pure paths + optional one-time migration from the legacy
``~/.craftgraph/`` location.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from platformdirs import PlatformDirs

logger = logging.getLogger(__name__)

_APP_NAME = "CraftGraph"

_dirs = PlatformDirs(_APP_NAME, appauthor=False, ensure_exists=False)


# -- Public directory accessors ------------------------------------------------


def config_dir() -> Path:
    """User config directory (roaming on Windows).

    Stores settings, recent-files list, and other small user preferences
    that should follow the user across machines on a domain.

    - Windows: ``%APPDATA%/CraftGraph``
    - macOS:   ``~/Library/Application Support/CraftGraph``
    - Linux:   ``~/.config/CraftGraph``
    """
    return Path(_dirs.user_config_dir)


def data_dir() -> Path:
    """User data directory (local).

    Stores larger persistent data that is machine-specific.

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


def load_setting(key: str, default: str) -> str:
    """Read a single setting from ``settings.json``.

    Returns *default* if the file is missing, corrupt, or lacks the key.
    """
    path = settings_path()
    if not path.is_file():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data.get(key, default))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("settings.json is corrupt, returning default for %r: %s", key, exc)
        return default


def save_setting(key: str, value: str) -> None:
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

_ICONS_PKG_DIR = Path(__file__).parent / "data" / "icons"


def _icon_name() -> str:
    """Return the platform-appropriate icon filename."""
    import sys

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
    return _ICONS_PKG_DIR / _icon_name()


def bundled_icon_dir() -> Path:
    """Directory containing bundled icon files."""
    return _ICONS_PKG_DIR


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
