"""Centralized color and theme definitions for CraftGraph.

Every visual constant -- node colors, syntax token colors, editor
background, highlight colors, accent -- lives here as a dataclass
field with a sensible default.  The settings dialog reads and writes
theme values; consumers (``qt_nodes``, ``sync``, ``highlighter``,
``code_editor``) import from this module instead of hardcoding colors.

No Qt imports -- this module is pure data so it can be tested and
used from CLI or headless contexts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from craftgraph.config import get_config

# -- Type aliases --------------------------------------------------------------

Color3 = tuple[int, int, int]
"""RGB color tuple used by node ``set_color()``."""

Color4 = tuple[int, int, int, int]
"""RGBA color tuple used by pipe styling."""


# -- Dataclasses ---------------------------------------------------------------


@dataclass
class NodeColors:
    """Per-block-type node header colors (RGB).

    Defaults match the ``NODE_COLOR_*`` constants in ``qt_nodes.py``.
    """

    modified_recipe: Color3 = (60, 120, 80)
    added_recipe: Color3 = (60, 140, 80)
    alias_recipe: Color3 = (80, 120, 120)
    custom_food: Color3 = (120, 100, 60)
    fabricator: Color3 = (80, 80, 160)
    crafting_tab: Color3 = (160, 120, 40)
    custom_size: Color3 = (100, 100, 100)
    moved_recipe: Color3 = (120, 80, 120)
    custom_bio_fuel: Color3 = (140, 100, 40)
    custom_fragment_count: Color3 = (80, 100, 140)
    orphan_ingredient: Color3 = (90, 90, 90)
    sprite: Color3 = (180, 160, 60)


@dataclass
class HighlightColors:
    """Colors for graph highlights (cycle edges, selection)."""

    cycle_edge: Color4 = (220, 60, 60, 255)
    selected_node_border: str = "#ffcc00"
    default_pipe: Color4 = (175, 95, 30, 255)


@dataclass
class SyntaxColors:
    """Syntax highlighting token colors (hex strings).

    Defaults match the hardcoded values in ``highlighter.py``.
    """

    block_type: str = "#8B008B"
    field_key: str = "#007080"
    string: str = "#228B22"
    comment: str = "#808080"
    error_underline: str = "#CC0000"


@dataclass
class EditorColors:
    """Code editor background and gutter colors (hex strings).

    Defaults match the hardcoded values in ``code_editor.py``.
    """

    background: str = "#252526"
    current_line: str = "#2a2d2e"
    gutter_background: str = "#F0F0F0"
    gutter_text: str = "#808080"


@dataclass
class ThemeColors:
    """Complete theme color set aggregating all color groups.

    Construct with defaults for the built-in dark theme, or override
    individual groups for user customization.
    """

    node: NodeColors = field(default_factory=NodeColors)
    highlight: HighlightColors = field(default_factory=HighlightColors)
    syntax: SyntaxColors = field(default_factory=SyntaxColors)
    editor: EditorColors = field(default_factory=EditorColors)
    accent: str = "#8CB4FF"
    high_contrast_borders: bool = False
    app_theme: str = "dark"
    colorblind_mode: str = "none"
    ui_scale: int = 100


# -- Accent color lookup -------------------------------------------------------

ACCENT_COLORS: dict[str, str] = {
    "Blue": "#8CB4FF",
    "Teal": "#5EC4B6",
    "Green": "#7BC77B",
    "Orange": "#E8935A",
    "Purple": "#B39DDB",
    "Red": "#E57373",
}

ACCENT_NAMES: list[str] = list(ACCENT_COLORS)


def accent_name_from_hex(hex_color: str) -> str:
    """Return the accent name matching *hex_color*, or ``"Blue"`` if unknown."""
    lower = hex_color.lower()
    for name, val in ACCENT_COLORS.items():
        if val.lower() == lower:
            return name
    return "Blue"


# -- Colorblind palette definitions --------------------------------------------
# Based on Okabe-Ito (2008) and Wong (2011) recommendations for
# universally distinguishable colors.  Each palette remaps the 12
# NodeColors fields to an alternative set that remains distinguishable
# under the specified color-vision deficiency.

COLORBLIND_MODES: list[str] = [
    "none",
    "deuteranopia",
    "protanopia",
    "tritanopia",
]

COLORBLIND_LABELS: dict[str, str] = {
    "none": "None (default)",
    "deuteranopia": "Deuteranopia (red-green)",
    "protanopia": "Protanopia (red-green variant)",
    "tritanopia": "Tritanopia (blue-yellow)",
}

_DEUTERANOPIA_NODES = NodeColors(
    modified_recipe=(0, 114, 178),
    added_recipe=(0, 158, 115),
    alias_recipe=(86, 180, 233),
    custom_food=(230, 159, 0),
    fabricator=(0, 0, 0),
    crafting_tab=(204, 121, 167),
    custom_size=(153, 153, 153),
    moved_recipe=(213, 94, 0),
    custom_bio_fuel=(240, 228, 66),
    custom_fragment_count=(110, 110, 180),
    orphan_ingredient=(90, 90, 90),
    sprite=(170, 170, 0),
)

_PROTANOPIA_NODES = NodeColors(
    modified_recipe=(0, 114, 178),
    added_recipe=(0, 158, 115),
    alias_recipe=(86, 180, 233),
    custom_food=(230, 159, 0),
    fabricator=(20, 20, 20),
    crafting_tab=(204, 121, 167),
    custom_size=(153, 153, 153),
    moved_recipe=(140, 100, 30),
    custom_bio_fuel=(240, 228, 66),
    custom_fragment_count=(110, 110, 180),
    orphan_ingredient=(90, 90, 90),
    sprite=(170, 170, 0),
)

_TRITANOPIA_NODES = NodeColors(
    modified_recipe=(0, 100, 160),
    added_recipe=(204, 121, 167),
    alias_recipe=(230, 159, 0),
    custom_food=(213, 94, 0),
    fabricator=(0, 0, 0),
    crafting_tab=(86, 180, 233),
    custom_size=(153, 153, 153),
    moved_recipe=(0, 158, 115),
    custom_bio_fuel=(140, 140, 140),
    custom_fragment_count=(0, 114, 178),
    orphan_ingredient=(90, 90, 90),
    sprite=(200, 200, 80),
)

COLORBLIND_PALETTES: dict[str, NodeColors] = {
    "deuteranopia": _DEUTERANOPIA_NODES,
    "protanopia": _PROTANOPIA_NODES,
    "tritanopia": _TRITANOPIA_NODES,
}


def apply_colorblind_palette(theme: ThemeColors) -> ThemeColors:
    """Return a copy of *theme* with node colors remapped for its colorblind mode.

    If ``theme.colorblind_mode`` is ``"none"`` the theme is returned unchanged.
    """
    palette = COLORBLIND_PALETTES.get(theme.colorblind_mode)
    if palette is None:
        return theme
    return ThemeColors(
        node=palette,
        highlight=theme.highlight,
        syntax=theme.syntax,
        editor=theme.editor,
        accent=theme.accent,
        high_contrast_borders=theme.high_contrast_borders,
        app_theme=theme.app_theme,
        colorblind_mode=theme.colorblind_mode,
        ui_scale=theme.ui_scale,
    )


# -- UI scale bounds -----------------------------------------------------------

UI_SCALE_OPTIONS: list[int] = [100, 110, 125, 150, 175, 200]


def scaled_pt(base_pt: int, theme: ThemeColors | None = None) -> int:
    """Scale a base point size by the active (or supplied) UI scale.

    Returns at least 1pt.  Inline both at widget construction (so newly
    created widgets pick up the persisted scale) and inside any rebuild
    helper invoked from ``_apply_theme`` (so live preview keeps long-lived
    widgets in sync after the user changes the scale).
    """
    pct = (theme.ui_scale if theme is not None else _active.ui_scale) / 100.0
    return max(round(base_pt * pct), 1)


def scaled_size(
    width: int,
    height: int,
    theme: ThemeColors | None = None,
) -> tuple[int, int]:
    """Scale a (width, height) pair by the active (or supplied) UI scale.

    Used for dialog minimum sizes so larger UI scales don't clip content
    behind the chrome.  Returns ints with each dimension >= 1.
    """
    pct = (theme.ui_scale if theme is not None else _active.ui_scale) / 100.0
    return (max(round(width * pct), 1), max(round(height * pct), 1))


# -- Node Editor settings -----------------------------------------------------

GRID_STYLES: list[str] = ["dots", "lines", "none"]
PIPE_STYLES: list[str] = ["curved", "straight", "angle"]
PIPE_STYLE_LABELS: dict[str, str] = {"curved": "Curved", "straight": "Straight", "angle": "Angle"}

GRID_STYLE_LABELS: dict[str, str] = {
    "dots": "Dots",
    "lines": "Lines",
    "none": "None",
}


@dataclass
class NodeEditorSettings:
    """Persisted preferences for the node graph viewer.

    All fields have sensible defaults matching the node editor library's
    built-in behaviour so the editor works identically out of the box.
    """

    # Navigation
    zoom_speed: float = 1.0
    invert_zoom: bool = False
    pan_with_mmb: bool = False
    show_minimap: bool = True

    # Grid
    show_grid: bool = True
    grid_size: int = 50
    snap_to_grid: bool = False
    grid_style: str = "lines"

    # Nodes
    show_thumbnails: bool = True
    thumbnail_size: int = 64
    show_port_labels: bool = True
    warn_before_cycles: bool = True

    # Connections
    pipe_style: str = "curved"
    pipe_width: float = 2.0
    animate_pipes: bool = False


def node_editor_settings_to_dict(s: NodeEditorSettings) -> dict[str, object]:
    """Serialize :class:`NodeEditorSettings` to a JSON-compatible dict."""
    return {
        "zoom_speed": s.zoom_speed,
        "invert_zoom": s.invert_zoom,
        "pan_with_mmb": s.pan_with_mmb,
        "show_minimap": s.show_minimap,
        "show_grid": s.show_grid,
        "grid_size": s.grid_size,
        "snap_to_grid": s.snap_to_grid,
        "grid_style": s.grid_style,
        "show_thumbnails": s.show_thumbnails,
        "thumbnail_size": s.thumbnail_size,
        "show_port_labels": s.show_port_labels,
        "warn_before_cycles": s.warn_before_cycles,
        "pipe_style": s.pipe_style,
        "pipe_width": s.pipe_width,
        "animate_pipes": s.animate_pipes,
    }


def node_editor_settings_from_dict(data: dict[str, object]) -> NodeEditorSettings:
    """Deserialize :class:`NodeEditorSettings` from a dict.

    Missing or malformed keys fall back to defaults.
    """
    defaults = NodeEditorSettings()

    zoom_speed = data.get("zoom_speed", defaults.zoom_speed)
    if not isinstance(zoom_speed, (int, float)) or not (0.1 <= zoom_speed <= 5.0):
        zoom_speed = defaults.zoom_speed

    invert_zoom = data.get("invert_zoom", defaults.invert_zoom)
    if not isinstance(invert_zoom, bool):
        invert_zoom = defaults.invert_zoom

    pan_with_mmb = data.get("pan_with_mmb", defaults.pan_with_mmb)
    if not isinstance(pan_with_mmb, bool):
        pan_with_mmb = defaults.pan_with_mmb

    show_minimap = data.get("show_minimap", defaults.show_minimap)
    if not isinstance(show_minimap, bool):
        show_minimap = defaults.show_minimap

    show_grid = data.get("show_grid", defaults.show_grid)
    if not isinstance(show_grid, bool):
        show_grid = defaults.show_grid

    grid_size = data.get("grid_size", defaults.grid_size)
    if not isinstance(grid_size, int) or not (10 <= grid_size <= 200):
        grid_size = defaults.grid_size

    snap_to_grid = data.get("snap_to_grid", defaults.snap_to_grid)
    if not isinstance(snap_to_grid, bool):
        snap_to_grid = defaults.snap_to_grid

    grid_style = data.get("grid_style", defaults.grid_style)
    if not isinstance(grid_style, str) or grid_style not in GRID_STYLES:
        grid_style = defaults.grid_style

    show_thumbnails = data.get("show_thumbnails", defaults.show_thumbnails)
    if not isinstance(show_thumbnails, bool):
        show_thumbnails = defaults.show_thumbnails

    thumbnail_size = data.get("thumbnail_size", defaults.thumbnail_size)
    if not isinstance(thumbnail_size, int) or not (24 <= thumbnail_size <= 128):
        thumbnail_size = defaults.thumbnail_size

    show_port_labels = data.get("show_port_labels", defaults.show_port_labels)
    if not isinstance(show_port_labels, bool):
        show_port_labels = defaults.show_port_labels

    warn_before_cycles = data.get("warn_before_cycles", defaults.warn_before_cycles)
    if not isinstance(warn_before_cycles, bool):
        warn_before_cycles = defaults.warn_before_cycles

    pipe_style = data.get("pipe_style", defaults.pipe_style)
    if not isinstance(pipe_style, str) or pipe_style not in PIPE_STYLES:
        pipe_style = defaults.pipe_style

    pipe_width = data.get("pipe_width", defaults.pipe_width)
    if not isinstance(pipe_width, (int, float)) or not (1.0 <= pipe_width <= 5.0):
        pipe_width = defaults.pipe_width

    animate_pipes = data.get("animate_pipes", defaults.animate_pipes)
    if not isinstance(animate_pipes, bool):
        animate_pipes = defaults.animate_pipes

    return NodeEditorSettings(
        zoom_speed=float(zoom_speed),
        invert_zoom=invert_zoom,
        pan_with_mmb=pan_with_mmb,
        show_minimap=show_minimap,
        show_grid=show_grid,
        grid_size=grid_size,
        snap_to_grid=snap_to_grid,
        grid_style=grid_style,
        show_thumbnails=show_thumbnails,
        thumbnail_size=thumbnail_size,
        show_port_labels=show_port_labels,
        warn_before_cycles=warn_before_cycles,
        pipe_style=pipe_style,
        pipe_width=float(pipe_width),
        animate_pipes=animate_pipes,
    )


# -- Code editor settings -------------------------------------------------------

_DEFAULT_FONT_FAMILY = get_config().ui.theme.default_font_family
_DEFAULT_FONT_SIZE = get_config().ui.theme.default_font_size


@dataclass
class CodeEditorSettings:
    """Persisted preferences for the code editor panel.

    All fields have sensible defaults so the editor works out of the box.
    """

    # Font
    font_family: str = _DEFAULT_FONT_FAMILY
    font_size: int = _DEFAULT_FONT_SIZE

    # Display
    show_line_numbers: bool = True
    highlight_current_line: bool = True
    word_wrap: bool = False
    tab_width: int = 4

    # Editing
    auto_indent: bool = True
    auto_close_brackets: bool = True
    strip_trailing_whitespace: bool = True

    # Bidirectional sync
    parse_debounce_enabled: bool = True
    parse_debounce_ms: int = field(
        default_factory=lambda: get_config().timings.parse_debounce_ms_default,
    )
    show_parse_errors_inline: bool = True


def code_editor_settings_to_dict(s: CodeEditorSettings) -> dict[str, object]:
    """Serialize :class:`CodeEditorSettings` to a JSON-compatible dict."""
    return {
        "font_family": s.font_family,
        "font_size": s.font_size,
        "show_line_numbers": s.show_line_numbers,
        "highlight_current_line": s.highlight_current_line,
        "word_wrap": s.word_wrap,
        "tab_width": s.tab_width,
        "auto_indent": s.auto_indent,
        "auto_close_brackets": s.auto_close_brackets,
        "strip_trailing_whitespace": s.strip_trailing_whitespace,
        "parse_debounce_enabled": s.parse_debounce_enabled,
        "parse_debounce_ms": s.parse_debounce_ms,
        "show_parse_errors_inline": s.show_parse_errors_inline,
    }


def code_editor_settings_from_dict(data: dict[str, object]) -> CodeEditorSettings:
    """Deserialize :class:`CodeEditorSettings` from a dict.

    Missing or malformed keys fall back to defaults.
    """
    defaults = CodeEditorSettings()

    font_family = data.get("font_family", defaults.font_family)
    if not isinstance(font_family, str) or not font_family.strip():
        font_family = defaults.font_family

    font_size = data.get("font_size", defaults.font_size)
    if not isinstance(font_size, int) or not (6 <= font_size <= 36):
        font_size = defaults.font_size

    show_line_numbers = data.get("show_line_numbers", defaults.show_line_numbers)
    if not isinstance(show_line_numbers, bool):
        show_line_numbers = defaults.show_line_numbers

    highlight_current_line = data.get("highlight_current_line", defaults.highlight_current_line)
    if not isinstance(highlight_current_line, bool):
        highlight_current_line = defaults.highlight_current_line

    word_wrap = data.get("word_wrap", defaults.word_wrap)
    if not isinstance(word_wrap, bool):
        word_wrap = defaults.word_wrap

    tab_width = data.get("tab_width", defaults.tab_width)
    if not isinstance(tab_width, int) or not (1 <= tab_width <= 8):
        tab_width = defaults.tab_width

    auto_indent = data.get("auto_indent", defaults.auto_indent)
    if not isinstance(auto_indent, bool):
        auto_indent = defaults.auto_indent

    auto_close_brackets = data.get("auto_close_brackets", defaults.auto_close_brackets)
    if not isinstance(auto_close_brackets, bool):
        auto_close_brackets = defaults.auto_close_brackets

    strip_trailing_whitespace = data.get(
        "strip_trailing_whitespace", defaults.strip_trailing_whitespace,
    )
    if not isinstance(strip_trailing_whitespace, bool):
        strip_trailing_whitespace = defaults.strip_trailing_whitespace

    parse_debounce_enabled = data.get("parse_debounce_enabled", defaults.parse_debounce_enabled)
    if not isinstance(parse_debounce_enabled, bool):
        parse_debounce_enabled = defaults.parse_debounce_enabled

    parse_debounce_ms = data.get("parse_debounce_ms", defaults.parse_debounce_ms)
    if not isinstance(parse_debounce_ms, int) or not (100 <= parse_debounce_ms <= 2000):
        parse_debounce_ms = defaults.parse_debounce_ms

    show_parse_errors_inline = data.get(
        "show_parse_errors_inline", defaults.show_parse_errors_inline,
    )
    if not isinstance(show_parse_errors_inline, bool):
        show_parse_errors_inline = defaults.show_parse_errors_inline

    return CodeEditorSettings(
        font_family=font_family,
        font_size=font_size,
        show_line_numbers=show_line_numbers,
        highlight_current_line=highlight_current_line,
        word_wrap=word_wrap,
        tab_width=tab_width,
        auto_indent=auto_indent,
        auto_close_brackets=auto_close_brackets,
        strip_trailing_whitespace=strip_trailing_whitespace,
        parse_debounce_enabled=parse_debounce_enabled,
        parse_debounce_ms=parse_debounce_ms,
        show_parse_errors_inline=show_parse_errors_inline,
    )


# -- Autocomplete settings -------------------------------------------------------


@dataclass
class AutocompleteSettings:
    """Persisted preferences for the autocomplete system.

    Controls behavior of both the code editor QCompleter and the
    NodeCompletionPopup on node text inputs.
    """

    # Behavior
    case_insensitive: bool = True
    min_prefix_length: int = 2
    max_visible_items: int = 12

    # ID sources
    include_vanilla_ids: bool = True
    include_mod_compat_ids: bool = True
    include_project_ids: bool = True

    # Custom IDs (user-defined, global)
    custom_ids: list[str] = field(default_factory=list)


def autocomplete_settings_to_dict(s: AutocompleteSettings) -> dict[str, object]:
    """Serialize :class:`AutocompleteSettings` to a JSON-compatible dict."""
    return {
        "case_insensitive": s.case_insensitive,
        "min_prefix_length": s.min_prefix_length,
        "max_visible_items": s.max_visible_items,
        "include_vanilla_ids": s.include_vanilla_ids,
        "include_mod_compat_ids": s.include_mod_compat_ids,
        "include_project_ids": s.include_project_ids,
        "custom_ids": list(s.custom_ids),
    }


def autocomplete_settings_from_dict(data: dict[str, object]) -> AutocompleteSettings:
    """Deserialize :class:`AutocompleteSettings` from a dict.

    Missing or malformed keys fall back to defaults.
    """
    defaults = AutocompleteSettings()

    case_insensitive = data.get("case_insensitive", defaults.case_insensitive)
    if not isinstance(case_insensitive, bool):
        case_insensitive = defaults.case_insensitive

    min_prefix_length = data.get("min_prefix_length", defaults.min_prefix_length)
    if not isinstance(min_prefix_length, int) or not (1 <= min_prefix_length <= 5):
        min_prefix_length = defaults.min_prefix_length

    max_visible_items = data.get("max_visible_items", defaults.max_visible_items)
    if not isinstance(max_visible_items, int) or not (5 <= max_visible_items <= 50):
        max_visible_items = defaults.max_visible_items

    include_vanilla_ids = data.get("include_vanilla_ids", defaults.include_vanilla_ids)
    if not isinstance(include_vanilla_ids, bool):
        include_vanilla_ids = defaults.include_vanilla_ids

    include_mod_compat_ids = data.get("include_mod_compat_ids", defaults.include_mod_compat_ids)
    if not isinstance(include_mod_compat_ids, bool):
        include_mod_compat_ids = defaults.include_mod_compat_ids

    include_project_ids = data.get("include_project_ids", defaults.include_project_ids)
    if not isinstance(include_project_ids, bool):
        include_project_ids = defaults.include_project_ids

    raw_custom = data.get("custom_ids", defaults.custom_ids)
    if not isinstance(raw_custom, list):
        custom_ids = list(defaults.custom_ids)
    else:
        custom_ids = [s for s in raw_custom if isinstance(s, str) and s.strip()]

    return AutocompleteSettings(
        case_insensitive=case_insensitive,
        min_prefix_length=min_prefix_length,
        max_visible_items=max_visible_items,
        include_vanilla_ids=include_vanilla_ids,
        include_mod_compat_ids=include_mod_compat_ids,
        include_project_ids=include_project_ids,
        custom_ids=custom_ids,
    )


# -- File watching settings -------------------------------------------------------


@dataclass
class FileWatchingSettings:
    """Persisted preferences for the Watchdog file watcher.

    Controls whether file watching is active and how quickly changes
    trigger a rebuild.
    """

    enabled: bool = True
    debounce_enabled: bool = True
    debounce_ms: int = field(
        default_factory=lambda: get_config().timings.file_watcher_debounce_ms_default,
    )
    on_external_change: str = "auto_reload"  # "auto_reload" | "prompt" | "ignore"
    notify_status_bar: bool = True
    notify_flash_tab: bool = True
    notify_sound_on_cycle: bool = False


def file_watching_settings_to_dict(s: FileWatchingSettings) -> dict[str, object]:
    """Serialize :class:`FileWatchingSettings` to a JSON-compatible dict."""
    return {
        "enabled": s.enabled,
        "debounce_enabled": s.debounce_enabled,
        "debounce_ms": s.debounce_ms,
        "on_external_change": s.on_external_change,
        "notify_status_bar": s.notify_status_bar,
        "notify_flash_tab": s.notify_flash_tab,
        "notify_sound_on_cycle": s.notify_sound_on_cycle,
    }


def file_watching_settings_from_dict(data: dict[str, object]) -> FileWatchingSettings:
    """Deserialize :class:`FileWatchingSettings` from a dict.

    Missing or malformed keys fall back to defaults.
    """
    defaults = FileWatchingSettings()

    enabled = data.get("enabled", defaults.enabled)
    if not isinstance(enabled, bool):
        enabled = defaults.enabled

    debounce_enabled = data.get("debounce_enabled", defaults.debounce_enabled)
    if not isinstance(debounce_enabled, bool):
        debounce_enabled = defaults.debounce_enabled

    debounce_ms = data.get("debounce_ms", defaults.debounce_ms)
    if not isinstance(debounce_ms, int) or not (100 <= debounce_ms <= 2000):
        debounce_ms = defaults.debounce_ms

    notify_status_bar = data.get("notify_status_bar", defaults.notify_status_bar)
    if not isinstance(notify_status_bar, bool):
        notify_status_bar = defaults.notify_status_bar

    notify_flash_tab = data.get("notify_flash_tab", defaults.notify_flash_tab)
    if not isinstance(notify_flash_tab, bool):
        notify_flash_tab = defaults.notify_flash_tab

    notify_sound_on_cycle = data.get("notify_sound_on_cycle", defaults.notify_sound_on_cycle)
    if not isinstance(notify_sound_on_cycle, bool):
        notify_sound_on_cycle = defaults.notify_sound_on_cycle

    _VALID_EXTERNAL = {"auto_reload", "prompt", "ignore"}
    on_external_change = data.get("on_external_change", defaults.on_external_change)
    if not isinstance(on_external_change, str) or on_external_change not in _VALID_EXTERNAL:
        on_external_change = defaults.on_external_change

    return FileWatchingSettings(
        enabled=enabled,
        debounce_enabled=debounce_enabled,
        debounce_ms=debounce_ms,
        on_external_change=on_external_change,
        notify_status_bar=notify_status_bar,
        notify_flash_tab=notify_flash_tab,
        notify_sound_on_cycle=notify_sound_on_cycle,
    )


@dataclass
class KeybindingSettings:
    """Persisted keyboard shortcut assignments.

    Each field stores a Qt key-sequence string (e.g. ``"Ctrl+S"``).
    An empty string means no shortcut assigned.
    """

    save: str = "Ctrl+S"
    save_all: str = "Ctrl+Shift+S"
    undo: str = "Ctrl+Z"
    redo: str = "Ctrl+Y"
    delete_nodes: str = "Delete"
    select_all: str = "Ctrl+A"
    zoom_to_fit: str = "Home"
    add_recipe: str = "Ctrl+N"
    open_settings: str = "Ctrl+,"
    toggle_code_editor: str = "Ctrl+E"
    find_node: str = "Ctrl+F"


# Canonical labels for the settings UI, keyed by field name.
KEYBINDING_LABELS: dict[str, str] = {
    "save": "Save file",
    "save_all": "Save all",
    "undo": "Undo",
    "redo": "Redo",
    "delete_nodes": "Delete selected nodes",
    "select_all": "Select all",
    "zoom_to_fit": "Zoom to fit",
    "add_recipe": "Add recipe",
    "open_settings": "Open settings",
    "toggle_code_editor": "Toggle code editor",
    "find_node": "Find node by ID",
}


def keybinding_settings_to_dict(s: KeybindingSettings) -> dict[str, object]:
    """Serialize :class:`KeybindingSettings` to a JSON-compatible dict."""
    return {name: getattr(s, name) for name in KEYBINDING_LABELS}


def keybinding_settings_from_dict(data: dict[str, object]) -> KeybindingSettings:
    """Deserialize :class:`KeybindingSettings` from a dict.

    Missing or malformed keys fall back to defaults.
    """
    defaults = KeybindingSettings()
    kwargs: dict[str, str] = {}
    for name in KEYBINDING_LABELS:
        val = data.get(name, getattr(defaults, name))
        if not isinstance(val, str):
            val = getattr(defaults, name)
        kwargs[name] = val
    return KeybindingSettings(**kwargs)


# -- Module-level active theme -------------------------------------------------

_active: ThemeColors = ThemeColors()


def active_theme() -> ThemeColors:
    """Return the currently active theme colors."""
    return _active


def set_active_theme(theme: ThemeColors) -> None:
    """Replace the active theme (e.g. after loading from settings)."""
    global _active
    _active = theme


# -- Serialization helpers -----------------------------------------------------


def theme_to_dict(theme: ThemeColors) -> dict[str, object]:
    """Serialize a :class:`ThemeColors` to a JSON-compatible dict."""
    return {
        "node": {
            "modified_recipe": list(theme.node.modified_recipe),
            "added_recipe": list(theme.node.added_recipe),
            "alias_recipe": list(theme.node.alias_recipe),
            "custom_food": list(theme.node.custom_food),
            "fabricator": list(theme.node.fabricator),
            "crafting_tab": list(theme.node.crafting_tab),
            "custom_size": list(theme.node.custom_size),
            "moved_recipe": list(theme.node.moved_recipe),
            "custom_bio_fuel": list(theme.node.custom_bio_fuel),
            "custom_fragment_count": list(theme.node.custom_fragment_count),
            "orphan_ingredient": list(theme.node.orphan_ingredient),
            "sprite": list(theme.node.sprite),
        },
        "highlight": {
            "cycle_edge": list(theme.highlight.cycle_edge),
            "selected_node_border": theme.highlight.selected_node_border,
            "default_pipe": list(theme.highlight.default_pipe),
        },
        "syntax": {
            "block_type": theme.syntax.block_type,
            "field_key": theme.syntax.field_key,
            "string": theme.syntax.string,
            "comment": theme.syntax.comment,
            "error_underline": theme.syntax.error_underline,
        },
        "editor": {
            "background": theme.editor.background,
            "current_line": theme.editor.current_line,
            "gutter_background": theme.editor.gutter_background,
            "gutter_text": theme.editor.gutter_text,
        },
        "accent": theme.accent,
        "high_contrast_borders": theme.high_contrast_borders,
        "app_theme": theme.app_theme,
        "colorblind_mode": theme.colorblind_mode,
        "ui_scale": theme.ui_scale,
    }


def _to_rgb3(raw: object) -> Color3 | None:
    """Try to convert *raw* (list/tuple) to an (R, G, B) tuple."""
    if isinstance(raw, (list, tuple)) and len(raw) >= 3:
        return (int(raw[0]), int(raw[1]), int(raw[2]))
    return None


def _to_rgba4(raw: object) -> Color4 | None:
    """Try to convert *raw* (list/tuple) to an (R, G, B, A) tuple."""
    if isinstance(raw, (list, tuple)) and len(raw) >= 4:
        return (int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))
    return None


def theme_from_dict(data: dict[str, object]) -> ThemeColors:
    """Deserialize a :class:`ThemeColors` from a dict (as stored in settings).

    Missing or malformed keys fall back to defaults.
    """
    defaults = ThemeColors()

    # -- Node colors --
    node_data = data.get("node", {})
    node_kwargs: dict[str, Color3] = {}
    if isinstance(node_data, dict):
        for field_name in (
            "modified_recipe", "added_recipe", "alias_recipe", "custom_food",
            "fabricator", "crafting_tab", "custom_size", "moved_recipe",
            "custom_bio_fuel", "custom_fragment_count", "orphan_ingredient", "sprite",
        ):
            rgb = _to_rgb3(node_data.get(field_name))
            if rgb is not None:
                node_kwargs[field_name] = rgb

    # -- Highlight colors --
    hl_data = data.get("highlight", {})
    hl_kwargs: dict[str, object] = {}
    if isinstance(hl_data, dict):
        ce = _to_rgba4(hl_data.get("cycle_edge"))
        if ce is not None:
            hl_kwargs["cycle_edge"] = ce
        snb = hl_data.get("selected_node_border")
        if isinstance(snb, str):
            hl_kwargs["selected_node_border"] = snb
        dp = _to_rgba4(hl_data.get("default_pipe"))
        if dp is not None:
            hl_kwargs["default_pipe"] = dp

    # -- Syntax colors --
    syn_data = data.get("syntax", {})
    syn_kwargs: dict[str, str] = {}
    if isinstance(syn_data, dict):
        for field_name in ("block_type", "field_key", "string", "comment", "error_underline"):
            val = syn_data.get(field_name)
            if isinstance(val, str):
                syn_kwargs[field_name] = val

    # -- Editor colors --
    ed_data = data.get("editor", {})
    ed_kwargs: dict[str, str] = {}
    if isinstance(ed_data, dict):
        for field_name in ("background", "current_line", "gutter_background", "gutter_text"):
            val = ed_data.get(field_name)
            if isinstance(val, str):
                ed_kwargs[field_name] = val

    accent = data.get("accent", defaults.accent)
    if not isinstance(accent, str):
        accent = defaults.accent

    hcb = data.get("high_contrast_borders", defaults.high_contrast_borders)
    if not isinstance(hcb, bool):
        hcb = defaults.high_contrast_borders

    app_theme = data.get("app_theme", defaults.app_theme)
    if not isinstance(app_theme, str) or app_theme not in ("dark", "light", "system"):
        app_theme = defaults.app_theme

    cb_mode = data.get("colorblind_mode", defaults.colorblind_mode)
    if not isinstance(cb_mode, str) or cb_mode not in COLORBLIND_MODES:
        cb_mode = defaults.colorblind_mode

    ui_scale = data.get("ui_scale", defaults.ui_scale)
    if not isinstance(ui_scale, int) or ui_scale not in UI_SCALE_OPTIONS:
        ui_scale = defaults.ui_scale

    return ThemeColors(
        node=NodeColors(**node_kwargs),
        highlight=HighlightColors(**hl_kwargs),
        syntax=SyntaxColors(**syn_kwargs),
        editor=EditorColors(**ed_kwargs),
        accent=accent,
        high_contrast_borders=hcb,
        app_theme=app_theme,
        colorblind_mode=cb_mode,
        ui_scale=ui_scale,
    )
