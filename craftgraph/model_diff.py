"""Pure-data diff layer over ParsedFile lists.

Used by the watcher path (``_on_watcher_rebuild``) to apply only the actual
deltas to the existing per-tab graphs instead of tearing everything down.

No Qt imports; this module is callable from CLI / REPL / tests without a
QApplication.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from craftgraph.models import ParsedFile


@dataclass(frozen=True, slots=True)
class FileDiff:
    """Delta between two ParsedFiles with the same source_path."""

    added: list[object]
    removed: list[object]
    modified: list[tuple[object, object]]


@dataclass(frozen=True, slots=True)
class ProjectDiff:
    """Delta across an entire mod folder between two parser snapshots."""

    unchanged_paths: list[Path]
    removed_paths: list[Path]
    added_files: list[ParsedFile]
    changed_files: list[tuple[ParsedFile, ParsedFile, FileDiff]]


def _model_key(entry: object) -> tuple[type, str]:
    """Identity tuple used to match entries across diffs.

    Almost every CC3 model uses ``item_id`` as its primary key; the exception
    is ``CraftingTab`` which uses ``tab_id``. The class participates in the
    key so a recipe and a fabricator with the same ID don't collide.
    """
    cls = type(entry)
    if hasattr(entry, "item_id"):
        return (cls, entry.item_id)
    if hasattr(entry, "tab_id"):
        return (cls, entry.tab_id)
    raise TypeError(
        f"unsupported entry type for diff: {cls.__name__}"
    )


def compute_diff(old: list[ParsedFile], new: list[ParsedFile]) -> ProjectDiff:
    """Compare two ParsedFile lists and return the project-level delta.

    Implementation lands in Task 4.
    """
    raise NotImplementedError("compute_diff lands in Task 4")
