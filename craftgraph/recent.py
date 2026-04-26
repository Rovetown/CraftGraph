"""Recent files tracking for CraftGraph.

Stores recently opened folders and projects in the platform-standard config
directory (see ``app_dirs.recent_files_path()``).
No Qt imports -- pure data + file I/O.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from craftgraph.config import get_config

CURRENT_VERSION = 1


@dataclass
class RecentEntry:
    """One recently opened folder or project."""

    path: str
    entry_type: str  # "folder" or "project"
    timestamp: str  # ISO 8601


class RecentFiles:
    """Manages the recent-files list, backed by a JSON file on disk."""

    def __init__(self, path: Path, *, max_entries: int | None = None) -> None:
        if max_entries is None:
            max_entries = get_config().limits.recent_files_default_max
        self._path = path
        self._max_entries = max_entries
        self._entries: list[RecentEntry] = []
        self._load()

    # -- Public API -----------------------------------------------------------

    @property
    def entries(self) -> list[RecentEntry]:
        """Return all entries, most recent first."""
        return list(self._entries)

    @property
    def max_entries(self) -> int:
        return self._max_entries

    @max_entries.setter
    def max_entries(self, value: int) -> None:
        self._max_entries = value
        self._trim()
        self._save()

    def add(self, path: Path, entry_type: str) -> None:
        """Add or move-to-top a recent entry, then save."""
        abs_path = str(path.resolve())
        self._entries = [e for e in self._entries if e.path != abs_path]
        entry = RecentEntry(
            path=abs_path,
            entry_type=entry_type,
            timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        self._entries.insert(0, entry)
        self._trim()
        self._save()

    def remove(self, path: Path) -> None:
        """Remove a specific entry by path, then save."""
        abs_path = str(path.resolve())
        self._entries = [e for e in self._entries if e.path != abs_path]
        self._save()

    def clear(self) -> None:
        """Remove all entries and save."""
        self._entries.clear()
        self._save()

    # -- Internals ------------------------------------------------------------

    def _trim(self) -> None:
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[: self._max_entries]

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            for item in raw.get("entries", []):
                self._entries.append(
                    RecentEntry(
                        path=item["path"],
                        entry_type=item["type"],
                        timestamp=item["timestamp"],
                    )
                )
        except (json.JSONDecodeError, KeyError, TypeError):
            self._entries = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": CURRENT_VERSION,
            "entries": [
                {
                    "path": e.path,
                    "type": e.entry_type,
                    "timestamp": e.timestamp,
                }
                for e in self._entries
            ],
        }
        self._path.write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )
