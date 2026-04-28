"""Shared pytest configuration for all test modules.

Sets the Qt offscreen platform before any QApplication is created,
preventing visible windows from spawning during the test run.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def pytest_addoption(parser):
    parser.addoption(
        "--no-stress",
        action="store_true",
        default=False,
        help="Skip the HWND stress tests in tests/test_hwnd_stress.py.",
    )
