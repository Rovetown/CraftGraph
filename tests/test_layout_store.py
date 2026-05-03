"""Tests for the layout sidecar file storage.

Tests cover:
- layout_path_for: file vs directory input
- save_layout / load_layout: round-trip fidelity
- Missing file returns None
- Empty file returns None
- Corrupt JSON returns None
- Wrong version returns None
- Malformed entries are skipped
"""

import json
from pathlib import Path

from craftgraph.layout_store import layout_path_for, load_layout, save_layout


class TestLayoutPathFor:
    """Test sidecar path computation."""

    def test_file_path(self, tmp_path: Path) -> None:
        recipe_file = tmp_path / "recipes.txt"
        recipe_file.touch()
        result = layout_path_for(recipe_file)
        assert result == tmp_path / ".craftgraph" / "layout.json"

    def test_directory_path(self, tmp_path: Path) -> None:
        recipe_dir = tmp_path / "recipes"
        recipe_dir.mkdir()
        result = layout_path_for(recipe_dir)
        assert result == recipe_dir / ".craftgraph" / "layout.json"


class TestSaveLayout:
    """Test writing layout data to disk."""

    def test_creates_directory(self, tmp_path: Path) -> None:
        layout_path = tmp_path / ".craftgraph" / "layout.json"
        positions: dict[str, dict[str, list[float]]] = {
            "test_tab": {"NodeA": [100.0, 200.0]},
        }
        save_layout(layout_path, positions)
        assert layout_path.exists()
        assert layout_path.parent.exists()

    def test_writes_valid_json(self, tmp_path: Path) -> None:
        layout_path = tmp_path / ".craftgraph" / "layout.json"
        positions: dict[str, dict[str, list[float]]] = {
            "tab1": {"A": [1.0, 2.0], "B": [3.0, 4.0]},
        }
        save_layout(layout_path, positions)
        data = json.loads(layout_path.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert data["tabs"]["tab1"]["A"] == [1.0, 2.0]


class TestLoadLayout:
    """Test reading layout data from disk."""

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        result = load_layout(tmp_path / "nonexistent.json")
        assert result is None

    def test_empty_file_returns_none(self, tmp_path: Path) -> None:
        layout_path = tmp_path / "layout.json"
        layout_path.write_text("", encoding="utf-8")
        result = load_layout(layout_path)
        assert result is None

    def test_invalid_json_returns_none(self, tmp_path: Path) -> None:
        layout_path = tmp_path / "layout.json"
        layout_path.write_text("not json {{{", encoding="utf-8")
        result = load_layout(layout_path)
        assert result is None

    def test_wrong_version_returns_none(self, tmp_path: Path) -> None:
        layout_path = tmp_path / "layout.json"
        data = {"version": 999, "tabs": {}}
        layout_path.write_text(json.dumps(data), encoding="utf-8")
        result = load_layout(layout_path)
        assert result is None

    def test_non_dict_root_returns_none(self, tmp_path: Path) -> None:
        layout_path = tmp_path / "layout.json"
        layout_path.write_text("[1, 2, 3]", encoding="utf-8")
        result = load_layout(layout_path)
        assert result is None

    def test_missing_tabs_returns_none(self, tmp_path: Path) -> None:
        layout_path = tmp_path / "layout.json"
        data = {"version": 1}
        layout_path.write_text(json.dumps(data), encoding="utf-8")
        result = load_layout(layout_path)
        assert result is None


class TestRoundTrip:
    """Test save -> load round-trip fidelity."""

    def test_basic_round_trip(self, tmp_path: Path) -> None:
        layout_path = tmp_path / ".craftgraph" / "layout.json"
        positions: dict[str, dict[str, list[float]]] = {
            "tab1": {
                "Glass": [100.0, 200.0],
                "Quartz": [300.0, 400.0],
                "Glass::Quartz": [150.0, 250.0],
            },
            "tab2": {
                "Titanium": [50.0, 75.0],
            },
        }
        save_layout(layout_path, positions)
        result = load_layout(layout_path)
        assert result is not None
        assert result == positions

    def test_empty_tabs_round_trip(self, tmp_path: Path) -> None:
        layout_path = tmp_path / ".craftgraph" / "layout.json"
        positions: dict[str, dict[str, list[float]]] = {}
        save_layout(layout_path, positions)
        result = load_layout(layout_path)
        assert result is not None
        assert result == {}

    def test_integer_positions_loaded_as_float(self, tmp_path: Path) -> None:
        """JSON integers should be converted to floats on load."""
        layout_path = tmp_path / "layout.json"
        data = {"version": 1, "tabs": {"t": {"A": [100, 200]}}}
        layout_path.write_text(json.dumps(data), encoding="utf-8")
        result = load_layout(layout_path)
        assert result is not None
        assert result["t"]["A"] == [100.0, 200.0]

    def test_malformed_entries_skipped(self, tmp_path: Path) -> None:
        """Invalid position entries are skipped, valid ones preserved."""
        layout_path = tmp_path / "layout.json"
        data = {
            "version": 1,
            "tabs": {
                "t": {
                    "Good": [1.0, 2.0],
                    "BadPos": [1.0],  # wrong length
                    "BadType": "not a list",  # wrong type
                },
            },
        }
        layout_path.write_text(json.dumps(data), encoding="utf-8")
        result = load_layout(layout_path)
        assert result is not None
        assert "Good" in result["t"]
        assert "BadPos" not in result["t"]
        assert "BadType" not in result["t"]


class TestMsgspecBackend:
    """layout_store uses msgspec for encode/decode (faster JSON)."""

    def test_save_layout_uses_msgspec(self, tmp_path: Path, monkeypatch) -> None:
        from craftgraph import layout_store

        # Spy: count msgspec.json.encode calls during save_layout.
        import msgspec

        original_encode = msgspec.json.encode
        calls: list[object] = []

        def counting_encode(obj):
            calls.append(obj)
            return original_encode(obj)

        monkeypatch.setattr(layout_store.msgspec.json, "encode", counting_encode)

        layout_store.save_layout(
            tmp_path / "layout.json",
            {"tab": {"Node": [1.0, 2.0]}},
        )
        assert calls, "save_layout must encode via msgspec.json.encode"

    def test_round_trip_via_msgspec(self, tmp_path: Path) -> None:
        from craftgraph.layout_store import load_layout, save_layout

        positions = {"tab1": {"NodeA": [10.5, 20.25], "NodeB": [-3.0, 4.0]}}
        out = tmp_path / "layout.json"
        save_layout(out, positions)
        loaded = load_layout(out)
        assert loaded == positions
