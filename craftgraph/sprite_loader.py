"""Sprite/image scanner for CC3 mod Assets/ folders.

Scans for PNG files in the Assets/ subfolder (the standard CC3 convention)
and builds a case-insensitive lookup from ItemID/TabID to file path.

CC3 mods place custom item icons as PNGs in an Assets/ directory alongside
their recipe .txt files. The filename (minus extension) matches the ItemID.
For example, ``Assets/Titanium.png`` maps to ItemID ``Titanium``.

This module provides the scanning infrastructure. Actual rendering of
sprites on DPG nodes is handled by gui_nodes.py.
"""

from pathlib import Path


def scan_assets_dir(recipe_dir: Path) -> dict[str, Path]:
    """Scan for an Assets/ subfolder and build an ItemID-to-PNG lookup.

    Walks ``recipe_dir/Assets/`` (non-recursive, flat scan) for .png files.
    Returns a dict mapping **lowercase** ItemID (filename stem) to the
    absolute Path of the PNG. Case-insensitive because CC3 resolves
    TechType IDs with ``Enum.TryParse(ignoreCase=true)``.

    If ``Assets/`` does not exist or contains no PNGs, returns an empty dict.
    """
    assets_dir = recipe_dir / "Assets"
    if not assets_dir.is_dir():
        return {}

    lookup: dict[str, Path] = {}
    for png_path in assets_dir.iterdir():
        if not png_path.is_file():
            continue
        if png_path.suffix.lower() != ".png":
            continue
        item_id_lower = png_path.stem.lower()
        # First match wins (shouldn't have duplicates, but be deterministic)
        if item_id_lower not in lookup:
            lookup[item_id_lower] = png_path.resolve()

    return lookup


def lookup_sprite(sprite_lookup: dict[str, Path], item_id: str) -> Path | None:
    """Find a sprite path for the given ItemID (case-insensitive).

    Returns the PNG path if a match exists, None otherwise.
    """
    return sprite_lookup.get(item_id.lower())


def resolve_sprite(
    item_id: str,
    manual_sprites: dict[str, Path],
    sprite_lookup: dict[str, Path],
) -> Path | None:
    """Resolve a sprite path: manual overrides first, then auto-assign.

    Both lookups are case-insensitive (keyed by lowercase item_id).
    """
    key = item_id.lower()
    if key in manual_sprites:
        return manual_sprites[key]
    return lookup_sprite(sprite_lookup, item_id)
