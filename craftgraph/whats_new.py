"""Per-version "What's New" slides + first-show tracking.

Each release pins its slide list under ``SLIDES_BY_VERSION[<version>]``.
On launch ``should_show(current_version)`` consults the persisted
``whats_new_last_shown_version`` setting; if it doesn't match the
current version AND we actually have slides for it, the dialog pops
once. ``mark_shown(version)`` records the version so subsequent
launches stay quiet.

Adding a new version means dropping a new list of slides into the dict
plus optionally placing the matching images under
``craftgraph/data/slides/whats-new/<version>/``. Slides without images
fall back to gradient placeholders.
"""

from __future__ import annotations

from pathlib import Path

from craftgraph import app_dirs
from craftgraph.carousel import CarouselSlide

_SETTING_KEY = "whats_new_last_shown_version"
_STARTUP_TOGGLE_KEY = "show_whats_new_on_startup"

_ASSETS_DIR = Path(__file__).parent / "data" / "assets"


# Slides per release. Keys must match ``craftgraph.__version__`` exactly.
SLIDES_BY_VERSION: dict[str, list[CarouselSlide]] = {
    "0.1.0-alpha.1": [
        CarouselSlide(
            title="Welcome to CraftGraph 0.1.0-alpha.1",
            body=(
                "First public alpha of CraftGraph. Visual node editor for "
                "CustomCraft3 recipes, real-time cycle detection, and a "
                "lightweight CLI for batch validation."
            ),
            placeholder_color=(60, 100, 180),
        ),
        CarouselSlide(
            title="83% Smaller Bundle",
            body=(
                "The Windows installer dropped from ~660 MB to ~125 MB "
                "through targeted PyInstaller exclusions, post-build "
                "trims, and a curated PySide6 module list. Cold launch "
                "feels snappier too."
            ),
            placeholder_color=(80, 140, 90),
        ),
        CarouselSlide(
            title="Live Diagnostics Toggle",
            body=(
                "Settings -> General -> Diagnostics flips frame-budget "
                "logging, the HWND counter, and perf.log writes on or "
                "off without a restart. Off by default in release "
                "builds so the status bar stays clean."
            ),
            placeholder_color=(180, 130, 70),
        ),
        CarouselSlide(
            title="Roadmap",
            body=(
                "Coming next: Recipe Import / Snippet Paste, in-app "
                "version-check, welcome screen polish, and Linux / "
                "macOS bundles. Check the GitHub releases page for "
                "updates."
            ),
            image_path=_ASSETS_DIR / "CraftGraph Roadmap.png",
            placeholder_color=(140, 100, 180),
        ),
    ],
}


def slides_for(version: str) -> list[CarouselSlide] | None:
    """Return the slide list for *version* if one exists, else None."""
    return SLIDES_BY_VERSION.get(version)


def should_show(current_version: str) -> bool:
    """True when the startup toggle is on AND slides exist AND the version
    hasn't been seen yet."""
    if not show_on_startup_enabled():
        return False
    if current_version not in SLIDES_BY_VERSION:
        return False
    last = str(app_dirs.load_setting(_SETTING_KEY, ""))
    return last != current_version


def mark_shown(version: str) -> None:
    """Record *version* as the most recently shown What's New release."""
    app_dirs.save_setting(_SETTING_KEY, version)


def show_on_startup_enabled() -> bool:
    """Whether the user has the "show What's New on startup" toggle on."""
    return bool(app_dirs.load_setting(_STARTUP_TOGGLE_KEY, True))


def set_show_on_startup(enabled: bool) -> None:
    app_dirs.save_setting(_STARTUP_TOGGLE_KEY, enabled)


def reset_seen_versions() -> None:
    """Forget the last-shown version so the dialog re-pops on next launch."""
    app_dirs.save_setting(_SETTING_KEY, "")
