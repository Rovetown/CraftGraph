"""Getting Started tutorial slides + visibility toggles.

Visibility is driven by two user-facing toggles persisted via
``app_dirs`` -- ``show_getting_started_on_startup`` and
``show_getting_started_on_new_project``. Both default ON so a fresh
install sees the tour without poking at settings; flip either off from
Settings -> General to mute. The previous silent
``getting_started_shown`` once-only flag is no longer consulted -- the
toggle replaces it.
"""

from __future__ import annotations

from craftgraph import app_dirs
from craftgraph.carousel import CarouselSlide

_STARTUP_TOGGLE_KEY = "show_getting_started_on_startup"
_NEW_PROJECT_TOGGLE_KEY = "show_getting_started_on_new_project"


SLIDES: list[CarouselSlide] = [
    CarouselSlide(
        title="Welcome to CraftGraph",
        body=(
            "CraftGraph is a visual editor for CustomCraft3 recipes. "
            "This quick tour shows how to open a mod folder, edit a "
            "recipe, and validate cycles."
        ),
        placeholder_color=(70, 110, 170),
    ),
    CarouselSlide(
        title="Step 1: Open a Mod Folder",
        body=(
            "File -> Open Folder, or drop a CustomCraft3 working-files "
            "folder onto the welcome screen. Each .txt recipe file gets "
            "its own tab."
        ),
        placeholder_color=(80, 140, 90),
    ),
    CarouselSlide(
        title="Step 2: Edit Recipes",
        body=(
            "Connect nodes to define ingredient relationships. Edit any "
            "field by clicking the painted value -- changes sync to the "
            "code editor in real time."
        ),
        placeholder_color=(150, 110, 70),
    ),
    CarouselSlide(
        title="Step 3: Check for Cycles",
        body=(
            "Edit -> Find Issues, or watch the status bar. Circular "
            "ingredient chains are highlighted in red on the graph."
        ),
        placeholder_color=(170, 90, 90),
    ),
    CarouselSlide(
        title="Step 4: Save",
        body=(
            "Ctrl+S saves the active tab back to its .txt file. The "
            "watcher reloads automatically if you edit the file outside "
            "CraftGraph."
        ),
        placeholder_color=(120, 100, 160),
    ),
]


def should_show_on_startup() -> bool:
    """Whether the user wants Getting Started auto-shown at app launch."""
    return bool(app_dirs.load_setting(_STARTUP_TOGGLE_KEY, True))


def should_show_on_new_project() -> bool:
    """Whether the user wants Getting Started auto-shown when creating a
    new file/project."""
    return bool(app_dirs.load_setting(_NEW_PROJECT_TOGGLE_KEY, True))


def set_show_on_startup(enabled: bool) -> None:
    app_dirs.save_setting(_STARTUP_TOGGLE_KEY, enabled)


def set_show_on_new_project(enabled: bool) -> None:
    app_dirs.save_setting(_NEW_PROJECT_TOGGLE_KEY, enabled)
