"""Parity harness: incremental diff path vs full-reload path.

For each scenario, two windows converge to the same end state via different
paths. Both windows' snapshots must be equal modulo positions, undo state,
and selection (see the design spec).

Marked @pytest.mark.slow so this runs under `just test-qt` but not
`just test-fast`.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

import pytest

pytest.importorskip("NodeGraphQt")

from PySide6 import QtWidgets

pytestmark = pytest.mark.slow


_BASELINE = Path("craftgraph/cc3_reference_files/real-mod-examples")


@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


@pytest.fixture
def baseline_copy(tmp_path):
    """Tmp copy of the Tier-A reference set."""
    if not _BASELINE.exists():
        pytest.skip("real-mod-examples baseline missing")
    dest = tmp_path / "real-mod-examples"
    shutil.copytree(_BASELINE, dest)
    return dest


def _model_dict(model: object) -> object:
    """Stable serialisation of a model dataclass for snapshot comparison."""
    if is_dataclass(model):
        return asdict(model)
    return repr(model)


def _stable_key(model: object) -> tuple[str, str]:
    cls_name = type(model).__name__
    item_id = getattr(model, "item_id", None)
    if item_id is not None:
        return (cls_name, item_id)
    tab_id = getattr(model, "tab_id", None)
    if tab_id is not None:
        return (cls_name, tab_id)
    return (cls_name, repr(model))


def _snapshot_window(window) -> dict:
    """Project state keyed by stable identifiers (no id() values)."""
    snapshot: dict = {}
    for tab in window._file_tabs:
        if tab.parsed_file is None:
            continue
        models_by_key: dict = {}
        for attr in (
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
        ):
            for entry in getattr(tab.parsed_file, attr, None) or []:
                models_by_key[_stable_key(entry)] = _model_dict(entry)

        nodes_by_key: dict = {}
        for node in tab.model_to_node.values():
            model = node.model_ref
            if model is None:
                continue
            nodes_by_key[_stable_key(model)] = type(node).__name__

        snapshot[str(tab.parsed_file.source_path)] = {
            "models": models_by_key,
            "nodes": nodes_by_key,
        }
    return snapshot


def _make_window(qapp, monkeypatch, tmp_path):
    """Construct a CraftGraphWindow isolated from real settings."""
    from craftgraph import app_dirs
    from craftgraph.qt_gui import CraftGraphWindow

    settings_dir = tmp_path / "settings"
    settings_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        app_dirs, "settings_path", lambda: settings_dir / "settings.json"
    )
    return CraftGraphWindow()


def _multi_recipe_file(baseline_copy):
    """Pick a baseline file containing multiple recipes (for add/remove/rename)."""
    target = baseline_copy / "_Alch_AliasRecipes_0_NEW_Lab_Equipment.txt"
    if not target.exists():
        pytest.skip("expected multi-recipe baseline file missing")
    return target


def test_modify_recipe_field_parity(qapp, monkeypatch, baseline_copy, tmp_path):
    """Change AmountCrafted on one recipe; both paths converge to equal state."""
    target_file = next(
        (
            p
            for p in baseline_copy.glob("*.txt")
            if "AmountCrafted: " in p.read_text(encoding="utf-8")
        ),
        None,
    )
    if target_file is None:
        pytest.skip("no recipe with AmountCrafted in baseline")

    text = target_file.read_text(encoding="utf-8")
    mutated = text.replace("AmountCrafted: 1", "AmountCrafted: 7", 1)
    if mutated == text:
        mutated = text.replace("AmountCrafted: 2", "AmountCrafted: 7", 1)
    if mutated == text:
        pytest.skip("could not locate an AmountCrafted line to mutate")

    win_a = _make_window(qapp, monkeypatch, tmp_path / "a")
    win_a.load_recipes(baseline_copy)
    target_file.write_text(mutated, encoding="utf-8")
    win_a._on_watcher_rebuild([])
    snap_a = _snapshot_window(win_a)

    win_b = _make_window(qapp, monkeypatch, tmp_path / "b")
    win_b.load_recipes(baseline_copy)
    snap_b = _snapshot_window(win_b)

    assert snap_a == snap_b


def test_add_recipe_parity(qapp, monkeypatch, baseline_copy, tmp_path):
    """Append a new alias recipe; both paths produce the same nodes."""
    target_file = _multi_recipe_file(baseline_copy)

    win_a = _make_window(qapp, monkeypatch, tmp_path / "a")
    win_a.load_recipes(baseline_copy)

    text = target_file.read_text(encoding="utf-8")
    insert = (
        "(\n"
        "    ItemID: ParityTestRecipe;\n"
        '    DisplayName: "Parity Test";\n'
        '    Tooltip: "Parity Test";\n'
        "    Ingredients:\n"
        "    ( ItemID: Titanium; Required: 1; );\n"
        "    LinkedItemIDs: ParityTestRecipe;\n"
        "    Path: Alch_Fab/Alch_LabEquipment;\n"
        "    ForceUnlockAtStart: NO;\n"
        "),\n"
    )
    last_paren = text.rfind(");")
    if last_paren < 0:
        pytest.skip("baseline target lacks expected closing paren")
    mutated = text[:last_paren] + insert + text[last_paren:]
    target_file.write_text(mutated, encoding="utf-8")

    win_a._on_watcher_rebuild([])
    snap_a = _snapshot_window(win_a)

    win_b = _make_window(qapp, monkeypatch, tmp_path / "b")
    win_b.load_recipes(baseline_copy)
    snap_b = _snapshot_window(win_b)

    assert snap_a == snap_b


def test_remove_recipe_parity(qapp, monkeypatch, baseline_copy, tmp_path):
    """Delete the second recipe block; both paths produce the same nodes."""
    target_file = _multi_recipe_file(baseline_copy)

    win_a = _make_window(qapp, monkeypatch, tmp_path / "a")
    win_a.load_recipes(baseline_copy)

    # Cut the second recipe block: from its ",\n(" boundary to the matching "),".
    text = target_file.read_text(encoding="utf-8")
    second_open = text.find("),\n(")
    if second_open < 0:
        pytest.skip("baseline target lacks an inter-recipe boundary")
    block_start = second_open + 2  # position of '\n('
    next_close = text.find("),", block_start) + 2
    if next_close <= 1:
        pytest.skip("baseline target lacks a recipe close after target block")
    mutated = text[:block_start] + text[next_close:]
    target_file.write_text(mutated, encoding="utf-8")

    win_a._on_watcher_rebuild([])
    snap_a = _snapshot_window(win_a)

    win_b = _make_window(qapp, monkeypatch, tmp_path / "b")
    win_b.load_recipes(baseline_copy)
    snap_b = _snapshot_window(win_b)

    assert snap_a == snap_b


def test_rename_recipe_parity(qapp, monkeypatch, baseline_copy, tmp_path):
    """Rename the first ItemID; remove+add semantics produce parity."""
    target_file = _multi_recipe_file(baseline_copy)

    win_a = _make_window(qapp, monkeypatch, tmp_path / "a")
    win_a.load_recipes(baseline_copy)

    text = target_file.read_text(encoding="utf-8")
    mutated = text.replace("ItemID: ", "ItemID: ParityRenamed_", 1)
    target_file.write_text(mutated, encoding="utf-8")

    win_a._on_watcher_rebuild([])
    snap_a = _snapshot_window(win_a)

    win_b = _make_window(qapp, monkeypatch, tmp_path / "b")
    win_b.load_recipes(baseline_copy)
    snap_b = _snapshot_window(win_b)

    assert snap_a == snap_b


def test_ingredient_count_change_parity(qapp, monkeypatch, baseline_copy, tmp_path):
    """Bump one Required value; exercises topology fallback."""
    import re

    target_file = _multi_recipe_file(baseline_copy)

    win_a = _make_window(qapp, monkeypatch, tmp_path / "a")
    win_a.load_recipes(baseline_copy)

    text = target_file.read_text(encoding="utf-8")
    mutated = re.sub(
        r"Required: (\d+);",
        lambda m: f"Required: {int(m.group(1)) + 1};",
        text,
        count=1,
    )
    if mutated == text:
        pytest.skip("baseline target lacks any Required: N; line")
    target_file.write_text(mutated, encoding="utf-8")

    win_a._on_watcher_rebuild([])
    snap_a = _snapshot_window(win_a)

    win_b = _make_window(qapp, monkeypatch, tmp_path / "b")
    win_b.load_recipes(baseline_copy)
    snap_b = _snapshot_window(win_b)

    assert snap_a == snap_b


def test_unchanged_file_skipped(qapp, monkeypatch, baseline_copy, tmp_path):
    """Touching an unchanged file fires a watcher event but creates zero nodes."""
    target_file = next(baseline_copy.glob("*.txt"))

    win_a = _make_window(qapp, monkeypatch, tmp_path / "a")
    win_a.load_recipes(baseline_copy)

    nodes_before = sum(len(t.model_to_node) for t in win_a._file_tabs)
    pre_node_ids = [
        {n.id for n in t.graph.all_nodes()} for t in win_a._file_tabs
    ]

    target_file.write_bytes(target_file.read_bytes())
    win_a._on_watcher_rebuild([])

    nodes_after = sum(len(t.model_to_node) for t in win_a._file_tabs)
    assert nodes_after == nodes_before
    post_node_ids = [
        {n.id for n in t.graph.all_nodes()} for t in win_a._file_tabs
    ]
    assert pre_node_ids == post_node_ids


def test_cross_file_fab_rename_parity(qapp, monkeypatch, baseline_copy, tmp_path):
    """Rename a CustomFabricator ItemID. Cross-file Path strings still resolve."""
    fab_file = next(
        (p for p in baseline_copy.glob("*.txt") if "CustomFabricators:" in p.read_text(encoding="utf-8")),
        None,
    )
    if fab_file is None:
        pytest.skip("no fabricator file in baseline")

    win_a = _make_window(qapp, monkeypatch, tmp_path / "a")
    win_a.load_recipes(baseline_copy)

    text = fab_file.read_text(encoding="utf-8")
    mutated = text.replace("ItemID: ", "ItemID: RenamedFab_", 1)
    fab_file.write_text(mutated, encoding="utf-8")

    win_a._on_watcher_rebuild([])
    snap_a = _snapshot_window(win_a)

    win_b = _make_window(qapp, monkeypatch, tmp_path / "b")
    win_b.load_recipes(baseline_copy)
    snap_b = _snapshot_window(win_b)

    assert snap_a == snap_b


def test_added_file_parity(qapp, monkeypatch, baseline_copy, tmp_path):
    """Drop a new .txt into the baseline; both paths produce the new tab."""
    win_a = _make_window(qapp, monkeypatch, tmp_path / "a")
    win_a.load_recipes(baseline_copy)

    new_file = baseline_copy / "ParityAdded_Sizes.txt"
    new_file.write_text(
        "CustomSizes:\n"
        "(\n"
        "    ItemID: ParitySizeTest;\n"
        "    Width: 2;\n"
        "    Height: 2;\n"
        ");\n",
        encoding="utf-8",
    )
    win_a._on_watcher_rebuild([])
    snap_a = _snapshot_window(win_a)

    win_b = _make_window(qapp, monkeypatch, tmp_path / "b")
    win_b.load_recipes(baseline_copy)
    snap_b = _snapshot_window(win_b)

    assert snap_a == snap_b


def test_removed_file_parity(qapp, monkeypatch, baseline_copy, tmp_path):
    """Delete a .txt; tab closes on path A, never appears on path B."""
    target = next(baseline_copy.glob("*.txt"))

    win_a = _make_window(qapp, monkeypatch, tmp_path / "a")
    win_a.load_recipes(baseline_copy)

    target.unlink()
    win_a._on_watcher_rebuild([])
    snap_a = _snapshot_window(win_a)

    win_b = _make_window(qapp, monkeypatch, tmp_path / "b")
    win_b.load_recipes(baseline_copy)
    snap_b = _snapshot_window(win_b)

    assert snap_a == snap_b
