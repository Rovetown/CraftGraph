"""Tests for craftgraph.updater -- update check stub."""

from __future__ import annotations

from craftgraph.updater import UpdateResult, check_for_update


class TestUpdateResult:
    def test_fields(self) -> None:
        result = UpdateResult(version="1.0.0", url="https://example.com")
        assert result.version == "1.0.0"
        assert result.url == "https://example.com"

    def test_immutable(self) -> None:
        result = UpdateResult(version="1.0.0", url="https://example.com")
        try:
            result.version = "2.0.0"  # type: ignore[misc]
            raised = False
        except AttributeError:
            raised = True
        assert raised


class TestCheckForUpdate:
    def test_stub_returns_none(self) -> None:
        result = check_for_update("0.1.0")
        assert result is None

    def test_accepts_any_version_string(self) -> None:
        assert check_for_update("0.0.0") is None
        assert check_for_update("99.99.99") is None
