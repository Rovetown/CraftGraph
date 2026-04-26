"""Tests for craftgraph.project -- project file serialization."""

from __future__ import annotations

from pathlib import Path

import msgpack
import pytest

from craftgraph.project import (
    CURRENT_VERSION,
    ProjectFile,
    ProjectLoadError,
    load_project,
    new_project,
    save_project,
)


class TestProjectFile:
    """ProjectFile dataclass construction."""

    def test_create_with_defaults(self) -> None:
        pf = ProjectFile(
            version=1,
            name="Test",
            description="",
            cc3_path="/fake/cc3",
            project_path="/fake/test.craftgraph",
            open_files=[],
            active_tab="",
            node_positions={},
            editor_state={},
            settings_overrides={},
        )
        assert pf.name == "Test"
        assert pf.version == 1
        assert pf.open_files == []

    def test_create_with_populated_fields(self) -> None:
        pf = ProjectFile(
            version=1,
            name="My Mod",
            description="A cool mod",
            cc3_path="/game/cc3",
            project_path="/docs/mymod.craftgraph",
            open_files=["AddedRecipes.txt", "ModifiedRecipes.txt"],
            active_tab="AddedRecipes",
            node_positions={"AddedRecipes": {"node_1": [10.0, 20.0]}},
            editor_state={"AddedRecipes": {"cursor_pos": 42, "scroll": 100}},
            settings_overrides={"auto_save": True},
        )
        assert pf.open_files == ["AddedRecipes.txt", "ModifiedRecipes.txt"]
        assert pf.node_positions["AddedRecipes"]["node_1"] == [10.0, 20.0]


class TestSaveAndLoadRoundTrip:
    """save_project -> load_project preserves all fields."""

    def _make_project(self, tmp_path: Path) -> ProjectFile:
        return ProjectFile(
            version=CURRENT_VERSION,
            name="RoundTrip",
            description="test description",
            cc3_path="/game/cc3/WorkingFiles",
            project_path=str(tmp_path / "roundtrip.craftgraph"),
            open_files=["AddedRecipes.txt", "sub/ModifiedRecipes.txt"],
            active_tab="AddedRecipes",
            node_positions={
                "AddedRecipes": {"Titanium_0": [100.0, 200.0], "Knife_1": [-50.0, 75.5]},
                "ModifiedRecipes": {},
            },
            editor_state={
                "AddedRecipes": {"cursor_pos": 42, "scroll": 100},
            },
            settings_overrides={"backup_on_save": True},
        )

    def test_round_trip_preserves_all_fields(self, tmp_path: Path) -> None:
        original = self._make_project(tmp_path)
        save_project(original)
        loaded = load_project(Path(original.project_path))

        assert loaded.version == original.version
        assert loaded.name == original.name
        assert loaded.description == original.description
        assert loaded.cc3_path == original.cc3_path
        assert loaded.project_path == original.project_path
        assert loaded.open_files == original.open_files
        assert loaded.active_tab == original.active_tab
        assert loaded.node_positions == original.node_positions
        assert loaded.editor_state == original.editor_state
        assert loaded.settings_overrides == original.settings_overrides

    def test_round_trip_empty_collections(self, tmp_path: Path) -> None:
        project = ProjectFile(
            version=CURRENT_VERSION,
            name="Empty",
            description="",
            cc3_path="/fake",
            project_path=str(tmp_path / "empty.craftgraph"),
            open_files=[],
            active_tab="",
            node_positions={},
            editor_state={},
            settings_overrides={},
        )
        save_project(project)
        loaded = load_project(Path(project.project_path))
        assert loaded.open_files == []
        assert loaded.node_positions == {}

    def test_file_created_on_disk(self, tmp_path: Path) -> None:
        project = self._make_project(tmp_path)
        save_project(project)
        assert Path(project.project_path).exists()
        assert Path(project.project_path).stat().st_size > 0

    def test_save_overwrites_existing(self, tmp_path: Path) -> None:
        project = self._make_project(tmp_path)
        save_project(project)
        project.name = "Updated"
        save_project(project)
        loaded = load_project(Path(project.project_path))
        assert loaded.name == "Updated"

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        project = self._make_project(tmp_path)
        project.project_path = str(tmp_path / "nested" / "deep" / "test.craftgraph")
        save_project(project)
        assert Path(project.project_path).exists()


class TestLoadProjectErrors:
    """load_project error handling."""

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ProjectLoadError, match="Failed to load"):
            load_project(tmp_path / "nonexistent.craftgraph")

    def test_corrupt_file_raises(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "corrupt.craftgraph"
        bad_file.write_bytes(b"this is not msgpack")
        with pytest.raises(ProjectLoadError, match="Failed to load"):
            load_project(bad_file)

    def test_non_dict_raises(self, tmp_path: Path) -> None:
        bad_file = tmp_path / "list.craftgraph"
        with open(bad_file, "wb") as fh:
            msgpack.pack([1, 2, 3], fh)
        with pytest.raises(ProjectLoadError, match="expected dict"):
            load_project(bad_file)

    def test_future_version_raises(self, tmp_path: Path) -> None:
        future_file = tmp_path / "future.craftgraph"
        with open(future_file, "wb") as fh:
            msgpack.pack({"version": 999, "name": "X", "cc3_path": "/x", "project_path": "/x"}, fh)
        with pytest.raises(ProjectLoadError, match="newer than supported"):
            load_project(future_file)

    def test_current_version_loads(self, tmp_path: Path) -> None:
        valid_file = tmp_path / "valid.craftgraph"
        with open(valid_file, "wb") as fh:
            msgpack.pack(
                {
                    "version": CURRENT_VERSION,
                    "name": "OK",
                    "cc3_path": "/cc3",
                    "project_path": str(valid_file),
                },
                fh,
            )
        project = load_project(valid_file)
        assert project.name == "OK"

    def test_missing_optional_fields_get_defaults(self, tmp_path: Path) -> None:
        minimal_file = tmp_path / "minimal.craftgraph"
        with open(minimal_file, "wb") as fh:
            msgpack.pack(
                {
                    "version": CURRENT_VERSION,
                    "name": "Minimal",
                    "cc3_path": "/cc3",
                    "project_path": str(minimal_file),
                },
                fh,
            )
        project = load_project(minimal_file)
        assert project.description == ""
        assert project.open_files == []
        assert project.active_tab == ""
        assert project.node_positions == {}
        assert project.editor_state == {}
        assert project.settings_overrides == {}


class TestNewProject:
    """new_project() creates a ProjectFile and writes it to disk."""

    def test_creates_file_on_disk(self, tmp_path: Path) -> None:
        project = new_project("MyMod", Path("/fake/cc3"), tmp_path)
        expected_path = tmp_path / "MyMod.craftgraph"
        assert expected_path.exists()
        assert project.project_path == str(expected_path)

    def test_returns_valid_project(self, tmp_path: Path) -> None:
        cc3 = Path("/fake/cc3")
        project = new_project("MyMod", cc3, tmp_path, description="A mod")
        assert project.version == CURRENT_VERSION
        assert project.name == "MyMod"
        assert project.description == "A mod"
        assert project.cc3_path == str(cc3)
        assert project.open_files == []
        assert project.active_tab == ""

    def test_default_description_is_empty(self, tmp_path: Path) -> None:
        project = new_project("Test", Path("/cc3"), tmp_path)
        assert project.description == ""

    def test_created_file_round_trips(self, tmp_path: Path) -> None:
        project = new_project("RT", Path("/cc3"), tmp_path, description="round trip")
        loaded = load_project(Path(project.project_path))
        assert loaded.name == project.name
        assert loaded.description == project.description
        assert loaded.cc3_path == project.cc3_path

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested"
        project = new_project("Deep", Path("/cc3"), nested)
        assert Path(project.project_path).exists()
