"""Shared pytest configuration for all test modules.

Sets the Qt offscreen platform before any QApplication is created,
preventing visible windows from spawning during the test run.
"""

import logging
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _DropFrameBudgetViolation(logging.Filter):
    """Suppress frame_budget_violation cascades during the Qt test suite.

    Heavy load_recipes / watcher_rebuild blocks naturally exceed the 33ms
    frame budget while populating ~900 nodes, emitting dozens of warnings
    per op that drown pytest output. test_perf_diag verifies the report
    mechanism via the restore_frame_budget_logging fixture.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return "frame_budget_violation" not in record.getMessage()


_FRAME_BUDGET_FILTER = _DropFrameBudgetViolation()
logging.getLogger("craftgraph.perf_diag").addFilter(_FRAME_BUDGET_FILTER)


@pytest.fixture
def restore_frame_budget_logging():
    logger = logging.getLogger("craftgraph.perf_diag")
    logger.removeFilter(_FRAME_BUDGET_FILTER)
    try:
        yield
    finally:
        logger.addFilter(_FRAME_BUDGET_FILTER)


def pytest_addoption(parser):
    parser.addoption(
        "--no-stress",
        action="store_true",
        default=False,
        help="Skip the HWND stress tests in tests/test_hwnd_stress.py.",
    )
