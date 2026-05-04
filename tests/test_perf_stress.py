"""Tiered cProfile harness for performance work.

Runs folder-load scenarios on Tier B/A/C workloads. Tier A asserts on a
generous regression threshold (tightened as Phase 1 wins land). Tier B is
a smoke test (must complete). Tier C is informational and skipped by
default. All scenarios are gated on the existing ``--no-stress`` flag.
"""

from __future__ import annotations

import cProfile
import pstats
import sys
from pathlib import Path

import pytest

# Skip the whole module when Qt deps aren't installed (matches test_qt_gui.py).
pytest.importorskip(
    "NodeGraphQt",
    reason="NodeGraphQt not installed (install with: uv sync --extra qt)",
)

from PySide6 import QtWidgets  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
TIER_B = (
    REPO_ROOT
    / "craftgraph"
    / "cc3_reference_files"
    / "original-source"
    / "CustomCraft3"
    / "SampleFiles"
    / "EquipmentSalvage"
)
TIER_A = REPO_ROOT / "craftgraph" / "cc3_reference_files" / "real-mod-examples"


@pytest.fixture(scope="session")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    from craftgraph import app_dirs
    from craftgraph.qt_gui import CraftGraphWindow

    monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(app_dirs, "log_dir", lambda: tmp_path)
    return CraftGraphWindow()


def _skip_if_no_stress(request: pytest.FixtureRequest) -> None:
    if request.config.getoption("--no-stress", default=False):
        pytest.skip("--no-stress passed")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-first dev workflow")
class TestTierAFolderLoad:
    # Generous initial cap; tighten as Phase 1 wins land.
    REGRESSION_LIMIT_MS = 10_000.0

    def test_load_recipes_under_regression_limit(
        self,
        window,
        request,
        tmp_path,
    ):
        _skip_if_no_stress(request)
        if not TIER_A.exists():
            pytest.skip(f"Tier A workload missing: {TIER_A}")

        profile_path = tmp_path / "tier_a.prof"
        profiler = cProfile.Profile()
        profiler.enable()
        window.load_recipes(TIER_A)
        profiler.disable()
        profiler.dump_stats(str(profile_path))

        stats = pstats.Stats(str(profile_path))
        total_ms = stats.total_tt * 1000.0
        assert total_ms < self.REGRESSION_LIMIT_MS, (
            f"Tier A folder load {total_ms:.1f} ms exceeded "
            f"{self.REGRESSION_LIMIT_MS:.0f} ms regression limit"
        )


class TestTierBFolderLoad:
    """Smoke test: folder must load to completion. No timing assertion."""

    def test_load_recipes_smoke(self, window, request):
        _skip_if_no_stress(request)
        if not TIER_B.exists():
            pytest.skip(f"Tier B workload missing: {TIER_B}")
        window.load_recipes(TIER_B)


@pytest.mark.skip(reason="Tier C is informational; manual run only")
class TestTierCFolderLoad:
    """Tier C runs are manual; numbers are recorded but no assertion."""
