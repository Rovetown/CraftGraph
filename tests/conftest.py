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


def make_scene_mouse_event(
    pos,
    button,
    *,
    event_type=None,
    modifiers=None,
):
    """Build a QGraphicsSceneMouseEvent for unit-testing painted-field click handlers.

    Tests deliver the returned event directly to ``node.view.mousePressEvent``
    to bypass scene dispatch (the intentional unit-test surface). Imported
    from conftest by test files that need to synthesize scene mouse events.
    """
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtWidgets import QGraphicsSceneMouseEvent

    if event_type is None:
        event_type = QEvent.Type.GraphicsSceneMousePress
    if modifiers is None:
        modifiers = Qt.KeyboardModifier.NoModifier

    event = QGraphicsSceneMouseEvent(event_type)
    event.setPos(QPointF(pos))
    event.setScenePos(QPointF(pos))
    event.setButton(button)
    event.setButtons(button)
    event.setModifiers(modifiers)
    return event


def make_test_window(qtbot):
    """Single test-suite construction path for CraftGraphWindow.

    Builds the window with a non-modal close confirmer (DISCARD) so
    closeEvent never blocks on a modal in offscreen tests, and registers
    the window with qtbot.addWidget so pytest-qt manages its lifecycle.
    Together these replace the autouse _reap_file_watchers fixture once
    every CraftGraphWindow() call in the suite is routed through here.
    """
    from craftgraph.qt_gui import CloseDecision, CraftGraphWindow

    win = CraftGraphWindow(close_confirmer=lambda _w: CloseDecision.DISCARD)
    qtbot.addWidget(win)
    return win


def pytest_addoption(parser):
    parser.addoption(
        "--no-stress",
        action="store_true",
        default=False,
        help="Skip the HWND stress tests in tests/test_hwnd_stress.py.",
    )
