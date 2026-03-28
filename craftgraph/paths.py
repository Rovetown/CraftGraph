"""Path detection utilities for CraftGraph."""

from __future__ import annotations

from collections.abc import Sequence
from functools import cache
from pathlib import Path

# Segments appended to each Steam library root to reach the CC3 plugin folder.
_CC3_SEGMENTS = ("steamapps", "common", "Subnautica", "BepInEx", "plugins", "CustomCraft3")


@cache
def _default_roots() -> tuple[Path, ...]:
    """Return the standard Windows Steam library root candidates."""
    return (
        Path("C:/Program Files (x86)/Steam"),
        Path("D:/SteamLibrary"),
        Path("D:/Program Files (x86)/Steam"),
        Path("C:/SteamLibrary"),
    )


def detect_subnautica_cc3_path(
    *,
    roots: Sequence[Path] | None = None,
) -> Path | None:
    """Walk candidate Steam roots and return the first existing CC3 folder.

    For each root, the function checks each segment incrementally
    (steamapps -> common -> Subnautica -> ...).  If a segment is missing
    it skips to the next root immediately.

    Pass *roots* to override the built-in Windows candidates (useful for
    testing).  Returns ``None`` if no complete path is found.
    """
    candidates = roots if roots is not None else _default_roots()

    for root in candidates:
        if not root.exists():
            continue

        current = root
        found = True
        for segment in _CC3_SEGMENTS:
            current = current / segment
            if not current.is_dir():
                found = False
                break

        if found:
            return current

    return None


def default_project_folder() -> Path:
    """Return the default project folder (~/Documents/CraftGraph)."""
    return Path.home() / "Documents" / "CraftGraph"


def cc3_working_files(cc3_path: str) -> str:
    """Return '<cc3_path>/WorkingFiles' if *cc3_path* is non-empty, else ''."""
    if not cc3_path:
        return ""
    return str(Path(cc3_path) / "WorkingFiles")


def cc3_assets(cc3_path: str) -> str:
    """Return '<cc3_path>/Assets' if *cc3_path* is non-empty, else ''."""
    if not cc3_path:
        return ""
    return str(Path(cc3_path) / "Assets")
