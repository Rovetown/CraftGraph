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
        # Try other small numbers.
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
