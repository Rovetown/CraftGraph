"""Tests for craftgraph.project -- project file serialization."""

from __future__ import annotations

from pathlib import Path

from craftgraph.project import (
    CURRENT_VERSION,
    ProjectFile,
    load_project,
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
