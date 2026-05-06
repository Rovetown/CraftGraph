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

    Files are matched by ``source_path``. Within a matched pair, every
    block-type list is walked and entries are classified by ``_model_key``.
    """
    old_by_path = {pf.source_path: pf for pf in old}
    new_by_path = {pf.source_path: pf for pf in new}

    unchanged_paths: list[Path] = []
    removed_paths: list[Path] = []
    added_files: list[ParsedFile] = []
    changed_files: list[tuple[ParsedFile, ParsedFile, FileDiff]] = []

    for path in old_by_path.keys() - new_by_path.keys():
        removed_paths.append(path)

    for path in new_by_path.keys() - old_by_path.keys():
        added_files.append(new_by_path[path])

    for path in old_by_path.keys() & new_by_path.keys():
        old_pf = old_by_path[path]
        new_pf = new_by_path[path]
        fd = _diff_one_file(old_pf, new_pf)
        if not fd.added and not fd.removed and not fd.modified:
            unchanged_paths.append(path)
        else:
            changed_files.append((old_pf, new_pf, fd))

    return ProjectDiff(
        unchanged_paths=unchanged_paths,
        removed_paths=removed_paths,
        added_files=added_files,
        changed_files=changed_files,
    )


# Per-ParsedFile attribute names that hold lists of model entries. Walking
# these covers every CC3 block type that lands at the top level. Nested
# children of CustomFabricator (added_recipes, alias_recipes, custom_foods,
# crafting_tabs) are not walked here -- a CustomFabricator with different
# children is detected as "modified" via dataclass __eq__ and the apply
# layer handles the nested delta.
_ENTRY_LIST_ATTRS: tuple[str, ...] = (
    "modified_recipes",
    "added_recipes",
    "alias_recipes",
    "custom_foods",
    "crafting_tabs",
    "custom_fabricators",
    "moved_recipes",
    "custom_sizes",
    "custom_bio_fuels",
    "custom_fragment_counts",
)


def _diff_one_file(old_pf: ParsedFile, new_pf: ParsedFile) -> FileDiff:
    """Walk every entry list on the ParsedFile and classify by _model_key."""
    added: list[object] = []
    removed: list[object] = []
    modified: list[tuple[object, object]] = []

    for attr in _ENTRY_LIST_ATTRS:
        old_entries = getattr(old_pf, attr, None) or []
        new_entries = getattr(new_pf, attr, None) or []
        _classify(old_entries, new_entries, added, removed, modified)

    return FileDiff(added=added, removed=removed, modified=modified)


def _classify(
    old_entries: list[object],
    new_entries: list[object],
    added: list[object],
    removed: list[object],
    modified: list[tuple[object, object]],
) -> None:
    old_by_key = {_model_key(e): e for e in old_entries}
    new_by_key = {_model_key(e): e for e in new_entries}

    for key in old_by_key.keys() - new_by_key.keys():
        removed.append(old_by_key[key])
    for key in new_by_key.keys() - old_by_key.keys():
        added.append(new_by_key[key])
    for key in old_by_key.keys() & new_by_key.keys():
        old_e = old_by_key[key]
        new_e = new_by_key[key]
        if old_e != new_e:
            modified.append((old_e, new_e))
