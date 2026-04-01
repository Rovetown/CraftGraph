"""Save utilities for CraftGraph files (backup-on-save)."""

from __future__ import annotations

import shutil
from pathlib import Path


def save_with_backup(
    path: Path,
    text: str,
    *,
    backup: bool = False,
) -> None:
    """Write *text* to *path*, optionally creating a ``.bak`` copy first.

    If *backup* is ``True`` and *path* already exists, the current file is
    copied to ``<path>.bak`` before the new content is written.  If the file
    does not yet exist, no backup is created (there is nothing to back up).
    """
    if backup and path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    path.write_text(text, encoding="utf-8")
