"""Tests for craftgraph.hwnd_diag handle-counting helpers."""

from __future__ import annotations

import sys

import pytest


class TestHandleCounters:
    def test_gui_handle_count_returns_int(self):
        from craftgraph.hwnd_diag import gui_handle_count

        result = gui_handle_count()
        assert isinstance(result, int)
        assert result >= 0

    def test_gdi_handle_count_returns_int(self):
        from craftgraph.hwnd_diag import gdi_handle_count

        result = gdi_handle_count()
        assert isinstance(result, int)
        assert result >= 0

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only metric")
    def test_gui_handle_count_is_positive_on_windows(self):
        from craftgraph.hwnd_diag import gui_handle_count

        # Even a bare process has a few USER objects allocated.
        assert gui_handle_count() > 0

    @pytest.mark.skipif(sys.platform == "win32", reason="non-Windows fallback")
    def test_gui_handle_count_is_zero_off_windows(self):
        from craftgraph.hwnd_diag import gui_handle_count

        assert gui_handle_count() == 0
