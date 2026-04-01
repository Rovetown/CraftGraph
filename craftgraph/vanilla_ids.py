"""Loader for static Subnautica TechType ID lists.

Provides known item IDs for autocomplete and case-insensitive deduplication.
Uses ``importlib.resources`` so it works both from source and when bundled
with PyInstaller.

Two lists are available:
- **vanilla**: Canonical IDs from the base game (lowercase).
- **mod_compat**: IDs from popular CC3 mods found in the reference files.
"""

import importlib.resources

_VANILLA_IDS: frozenset[str] | None = None
_MOD_COMPAT_IDS: frozenset[str] | None = None


def _load_id_file(filename: str) -> frozenset[str]:
    """Read a newline-delimited ID file from the ``craftgraph.data`` package."""
    ref = importlib.resources.files("craftgraph.data").joinpath(filename)
    text = ref.read_text(encoding="utf-8")
    return frozenset(line.strip() for line in text.splitlines() if line.strip())


def load_vanilla_ids() -> frozenset[str]:
    """Return all known vanilla Subnautica item IDs as a frozen set.

    IDs are lowercase, matching the canonical form used on community
    sites and in CC3 files.  CC3 resolves them case-insensitively.
    The result is cached after the first call.
    """
    global _VANILLA_IDS
    if _VANILLA_IDS is not None:
        return _VANILLA_IDS
    _VANILLA_IDS = _load_id_file("vanilla_tech_types.txt")
    return _VANILLA_IDS


def load_mod_compat_ids() -> frozenset[str]:
    """Return item IDs from popular CC3 mods (Alchemy, VModFab, etc.).

    These supplement the vanilla set in autocomplete when working with
    mod files that reference these IDs.  Cached after the first call.
    """
    global _MOD_COMPAT_IDS
    if _MOD_COMPAT_IDS is not None:
        return _MOD_COMPAT_IDS
    _MOD_COMPAT_IDS = _load_id_file("mod_compat_tech_types.txt")
    return _MOD_COMPAT_IDS
