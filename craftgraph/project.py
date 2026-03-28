"""CraftGraph project file (.craftgraph) -- MessagePack serialization.

A project file persists workspace state (open files, node positions,
editor state) separately from the recipe .txt files.  The file lives
in ~/Documents/CraftGraph/ and points to a CC3 WorkingFiles folder.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import msgpack
from msgpack.exceptions import UnpackException

CURRENT_VERSION: int = 1


class ProjectLoadError(Exception):
    """Raised when a .craftgraph file cannot be loaded or parsed."""


@dataclass
class ProjectFile:
    """All persistent state for a CraftGraph project."""

    version: int
    name: str
    description: str
    cc3_path: str
    project_path: str
    open_files: list[str]
    active_tab: str
    node_positions: dict[str, dict[str, list[float]]]
    editor_state: dict[str, dict[str, Any]]
    settings_overrides: dict[str, Any]


def _project_to_dict(project: ProjectFile) -> dict[str, Any]:
    """Convert a ProjectFile to a plain dict for msgpack serialization."""
    return {
        "version": project.version,
        "name": project.name,
        "description": project.description,
        "cc3_path": project.cc3_path,
        "project_path": project.project_path,
        "open_files": project.open_files,
        "active_tab": project.active_tab,
        "node_positions": project.node_positions,
        "editor_state": project.editor_state,
        "settings_overrides": project.settings_overrides,
    }


def _dict_to_project(data: dict[str, Any]) -> ProjectFile:
    """Reconstruct a ProjectFile from a deserialized dict."""
    return ProjectFile(
        version=data["version"],
        name=data["name"],
        description=data.get("description", ""),
        cc3_path=data["cc3_path"],
        project_path=data["project_path"],
        open_files=data.get("open_files", []),
        active_tab=data.get("active_tab", ""),
        node_positions=data.get("node_positions", {}),
        editor_state=data.get("editor_state", {}),
        settings_overrides=data.get("settings_overrides", {}),
    )


def save_project(project: ProjectFile) -> None:
    """Serialize and write a project to *project.project_path*."""
    path = Path(project.project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _project_to_dict(project)
    with open(path, "wb") as fh:
        msgpack.pack(data, fh)


def load_project(path: Path) -> ProjectFile:
    """Read and deserialize a .craftgraph file, returning a ProjectFile.

    Raises ``ProjectLoadError`` on corrupt files or unsupported versions.
    """
    try:
        with open(path, "rb") as fh:
            data = msgpack.unpack(fh, raw=False)
    except (UnpackException, FileNotFoundError, OSError) as exc:
        msg = f"Failed to load project file: {path}: {exc}"
        raise ProjectLoadError(msg) from exc

    if not isinstance(data, dict):
        msg = f"Invalid project file (expected dict, got {type(data).__name__}): {path}"
        raise ProjectLoadError(msg)

    version = data.get("version", 0)
    if version > CURRENT_VERSION:
        msg = (
            f"Project file version {version} is newer than supported "
            f"({CURRENT_VERSION}). Please update CraftGraph."
        )
        raise ProjectLoadError(msg)

    # Store the actual path we loaded from (overrides whatever was serialized)
    data["project_path"] = str(path)
    return _dict_to_project(data)
