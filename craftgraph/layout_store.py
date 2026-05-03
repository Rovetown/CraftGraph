"""Persistent storage for node editor layout positions.

Saves and loads node positions to a sidecar file so that users don't lose
their carefully arranged node layouts between sessions.

Layout file: ``<recipe_dir>/.craftgraph/layout.json``

Format::

    {
        "version": 1,
        "tabs": {
            "filename_stem": {
                "NodeKey": [x, y],
                ...
            },
            ...
        }
    }

No DPG dependency -- operates on plain dicts of position data.
"""

import logging
from pathlib import Path

import msgspec

from craftgraph.config import get_config

logger = logging.getLogger(__name__)

_CURRENT_VERSION = 1


def layout_path_for(recipe_path: Path) -> Path:
    """Return the layout sidecar path for a given recipe file or directory.

    For a file: ``<parent>/.craftgraph/layout.json``
    For a directory: ``<dir>/.craftgraph/layout.json``
    """
    base = recipe_path if recipe_path.is_dir() else recipe_path.parent
    cfg = get_config().paths
    return base / cfg.layout_dir_name / cfg.layout_filename


def save_layout(
    path: Path,
    positions: dict[str, dict[str, list[float]]],
) -> None:
    """Write position data to the layout sidecar file.

    Args:
        path: The layout file path (from ``layout_path_for``).
        positions: Mapping of ``tab_name -> {node_key: [x, y]}``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": _CURRENT_VERSION,
        "tabs": positions,
    }
    # msgspec encodes ~5-10x faster than json and outputs UTF-8 bytes
    # directly (no .encode("utf-8") trip). format_json adds the indent
    # cosmetic so saved files remain hand-readable.
    encoded = msgspec.json.encode(data)
    path.write_bytes(msgspec.json.format(encoded, indent=2))


def load_layout(
    path: Path,
) -> dict[str, dict[str, list[float]]] | None:
    """Load position data from the layout sidecar file.

    Returns ``None`` if the file does not exist or cannot be parsed.
    Malformed entries are silently skipped -- the caller falls back
    to computed layout for any missing nodes.
    """
    if not path.exists():
        return None

    raw = path.read_bytes()
    if not raw.strip():
        return None

    try:
        data = msgspec.json.decode(raw)
    except msgspec.DecodeError:
        logger.warning("Layout file contains invalid JSON: %s", path)
        return None

    if not isinstance(data, dict):
        logger.warning("Layout file is not a JSON object: %s", path)
        return None

    version = data.get("version")
    if version != _CURRENT_VERSION:
        logger.warning(
            "Layout file version %s != expected %s: %s",
            version,
            _CURRENT_VERSION,
            path,
        )
        return None

    tabs = data.get("tabs")
    if not isinstance(tabs, dict):
        return None

    # Validate structure: each tab should map node keys to [x, y] pairs
    result: dict[str, dict[str, list[float]]] = {}
    for tab_name, node_positions in tabs.items():
        if not isinstance(tab_name, str) or not isinstance(node_positions, dict):
            continue
        validated: dict[str, list[float]] = {}
        for node_key, pos in node_positions.items():
            if not isinstance(node_key, str):
                continue
            if not isinstance(pos, list) or len(pos) != 2:
                continue
            if all(isinstance(v, int | float) for v in pos):
                validated[node_key] = [float(pos[0]), float(pos[1])]
        result[tab_name] = validated

    return result
