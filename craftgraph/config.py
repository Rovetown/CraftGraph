"""Build/runtime defaults loaded from ``craftgraph/config.toml``.

Call :func:`get_config` to obtain the frozen :class:`Config` singleton.
The TOML is read once on first access (cached) via ``importlib.resources``
so it works both from source and inside a PyInstaller bundle.

Values here are the compiled-in defaults. User-overridable runtime
preferences live separately in ``settings.json`` (see :mod:`app_dirs`).
"""

from __future__ import annotations

import importlib.resources
import tomllib
from dataclasses import dataclass
from functools import cache
from typing import Any

_CONFIG_FILENAME = "config.toml"


@dataclass(frozen=True, slots=True)
class PathsConfig:
    """App-internal resource paths and platform install probes."""

    icons_subdir: str
    data_subdir: str
    layout_dir_name: str
    layout_filename: str
    cc3_install_segments: tuple[str, ...]
    steam_root_candidates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TimingsConfig:
    """Debounce and polling intervals."""

    watcher_debounce_sec: float
    minimap_update_interval_ms: int
    parse_debounce_ms_default: int
    file_watcher_debounce_ms_default: int


RgbTuple = tuple[int, int, int]
RgbaTuple = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Stable application identifiers (do not edit after first release)."""

    identifier: str
    file_ext: str
    prog_id: str
    mime_type: str
    file_description: str


@dataclass(frozen=True, slots=True)
class ThemeConfig:
    """Baseline theme defaults (users can still override via settings.json)."""

    default_font_family: str
    default_font_size: int


@dataclass(frozen=True, slots=True)
class VariableNodesConfig:
    """Variable/getter node tunables from ``qt_variable_nodes.py``."""

    ref_combo_max_w: int
    required_empty_style: str
    required_valid_style: str


@dataclass(frozen=True, slots=True)
class NodeColorsConfig:
    """Title-bar tint (RGB) for each node block type."""

    modified_recipe: RgbTuple
    added_recipe: RgbTuple
    alias_recipe: RgbTuple
    custom_food: RgbTuple
    fabricator: RgbTuple
    crafting_tab: RgbTuple
    custom_size: RgbTuple
    moved_recipe: RgbTuple
    custom_bio_fuel: RgbTuple
    custom_fragment_count: RgbTuple
    orphan_ingredient: RgbTuple
    sprite: RgbTuple


@dataclass(frozen=True, slots=True)
class PortColorsConfig:
    """Pin-color palette (RGB) per semantic port role."""

    hierarchy: RgbTuple
    output: RgbTuple
    ingredient: RgbTuple
    children: RgbTuple
    sprite: RgbTuple
    variable: RgbTuple


@dataclass(frozen=True, slots=True)
class ColorsConfig:
    """Grouped color palettes under ``ui.colors``."""

    nodes: NodeColorsConfig
    ports: PortColorsConfig


@dataclass(frozen=True, slots=True)
class LayoutConfig:
    """Node editor column X positions + vertical spacing (from ``sync.py``)."""

    y_step: float
    x_fab: float
    x_tab: float
    x_recipe: float
    layout_y_step: float
    layout_y_group_gap: float
    layout_x_child_offset: float


@dataclass(frozen=True, slots=True)
class MinimapConfig:
    """Minimap widget dimensions and colors (from ``minimap.py``)."""

    width: int
    height: int
    bg_color: RgbaTuple
    border_color: RgbaTuple
    node_color: RgbaTuple
    viewport_fill: RgbaTuple
    viewport_border: RgbaTuple


@dataclass(frozen=True, slots=True)
class UiConfig:
    """GUI size defaults that users do not typically tweak at runtime."""

    sprite_size: int
    theme: ThemeConfig
    variable_nodes: VariableNodesConfig
    colors: ColorsConfig
    layout: LayoutConfig
    minimap: MinimapConfig


@dataclass(frozen=True, slots=True)
class VisualizerConfig:
    """Pyvis HTML rendering tunables (from ``visualizer.py``)."""

    base_node_size: int
    size_scale: int
    normal_edge_color: str
    cycle_edge_color: str
    normal_edge_width: int
    cycle_edge_width: int


@dataclass(frozen=True, slots=True)
class LimitsConfig:
    """Caps and valid ranges for app-wide behavior."""

    recent_files_default_max: int
    ingredient_required_min: int
    ingredient_required_max: int


@dataclass(frozen=True, slots=True)
class Config:
    """Top-level aggregate of all config sections."""

    app: AppConfig
    paths: PathsConfig
    timings: TimingsConfig
    ui: UiConfig
    visualizer: VisualizerConfig
    limits: LimitsConfig


def _load_toml() -> dict[str, Any]:
    ref = importlib.resources.files("craftgraph").joinpath(_CONFIG_FILENAME)
    return tomllib.loads(ref.read_text(encoding="utf-8"))


def _build_paths(raw: dict[str, Any]) -> PathsConfig:
    return PathsConfig(
        icons_subdir=str(raw["icons_subdir"]),
        data_subdir=str(raw["data_subdir"]),
        layout_dir_name=str(raw["layout_dir_name"]),
        layout_filename=str(raw["layout_filename"]),
        cc3_install_segments=tuple(str(s) for s in raw["cc3_install_segments"]),
        steam_root_candidates=tuple(str(s) for s in raw["steam_root_candidates"]),
    )


def _build_timings(raw: dict[str, Any]) -> TimingsConfig:
    return TimingsConfig(
        watcher_debounce_sec=float(raw["watcher_debounce_sec"]),
        minimap_update_interval_ms=int(raw["minimap_update_interval_ms"]),
        parse_debounce_ms_default=int(raw["parse_debounce_ms_default"]),
        file_watcher_debounce_ms_default=int(raw["file_watcher_debounce_ms_default"]),
    )


def _rgb(raw: list[Any]) -> RgbTuple:
    if len(raw) != 3:
        msg = f"expected 3 RGB components, got {len(raw)}"
        raise ValueError(msg)
    r, g, b = (int(c) for c in raw)
    return (r, g, b)


def _rgba(raw: list[Any]) -> RgbaTuple:
    if len(raw) == 3:
        r, g, b = (int(c) for c in raw)
        return (r, g, b, 255)
    if len(raw) == 4:
        r, g, b, a = (int(c) for c in raw)
        return (r, g, b, a)
    msg = f"expected 3 or 4 color components, got {len(raw)}"
    raise ValueError(msg)


def _build_app(raw: dict[str, Any]) -> AppConfig:
    return AppConfig(
        identifier=str(raw["identifier"]),
        file_ext=str(raw["file_ext"]),
        prog_id=str(raw["prog_id"]),
        mime_type=str(raw["mime_type"]),
        file_description=str(raw["file_description"]),
    )


def _build_theme(raw: dict[str, Any]) -> ThemeConfig:
    return ThemeConfig(
        default_font_family=str(raw["default_font_family"]),
        default_font_size=int(raw["default_font_size"]),
    )


def _build_variable_nodes(raw: dict[str, Any]) -> VariableNodesConfig:
    return VariableNodesConfig(
        ref_combo_max_w=int(raw["ref_combo_max_w"]),
        required_empty_style=str(raw["required_empty_style"]),
        required_valid_style=str(raw["required_valid_style"]),
    )


def _build_node_colors(raw: dict[str, Any]) -> NodeColorsConfig:
    return NodeColorsConfig(
        modified_recipe=_rgb(raw["modified_recipe"]),
        added_recipe=_rgb(raw["added_recipe"]),
        alias_recipe=_rgb(raw["alias_recipe"]),
        custom_food=_rgb(raw["custom_food"]),
        fabricator=_rgb(raw["fabricator"]),
        crafting_tab=_rgb(raw["crafting_tab"]),
        custom_size=_rgb(raw["custom_size"]),
        moved_recipe=_rgb(raw["moved_recipe"]),
        custom_bio_fuel=_rgb(raw["custom_bio_fuel"]),
        custom_fragment_count=_rgb(raw["custom_fragment_count"]),
        orphan_ingredient=_rgb(raw["orphan_ingredient"]),
        sprite=_rgb(raw["sprite"]),
    )


def _build_port_colors(raw: dict[str, Any]) -> PortColorsConfig:
    return PortColorsConfig(
        hierarchy=_rgb(raw["hierarchy"]),
        output=_rgb(raw["output"]),
        ingredient=_rgb(raw["ingredient"]),
        children=_rgb(raw["children"]),
        sprite=_rgb(raw["sprite"]),
        variable=_rgb(raw["variable"]),
    )


def _build_colors(raw: dict[str, Any]) -> ColorsConfig:
    return ColorsConfig(
        nodes=_build_node_colors(raw["nodes"]),
        ports=_build_port_colors(raw["ports"]),
    )


def _build_layout(raw: dict[str, Any]) -> LayoutConfig:
    return LayoutConfig(
        y_step=float(raw["y_step"]),
        x_fab=float(raw["x_fab"]),
        x_tab=float(raw["x_tab"]),
        x_recipe=float(raw["x_recipe"]),
        layout_y_step=float(raw["layout_y_step"]),
        layout_y_group_gap=float(raw["layout_y_group_gap"]),
        layout_x_child_offset=float(raw["layout_x_child_offset"]),
    )


def _build_minimap(raw: dict[str, Any]) -> MinimapConfig:
    return MinimapConfig(
        width=int(raw["width"]),
        height=int(raw["height"]),
        bg_color=_rgba(raw["bg_color"]),
        border_color=_rgba(raw["border_color"]),
        node_color=_rgba(raw["node_color"]),
        viewport_fill=_rgba(raw["viewport_fill"]),
        viewport_border=_rgba(raw["viewport_border"]),
    )


def _build_ui(raw: dict[str, Any]) -> UiConfig:
    return UiConfig(
        sprite_size=int(raw["sprite_size"]),
        theme=_build_theme(raw["theme"]),
        variable_nodes=_build_variable_nodes(raw["variable_nodes"]),
        colors=_build_colors(raw["colors"]),
        layout=_build_layout(raw["layout"]),
        minimap=_build_minimap(raw["minimap"]),
    )


def _build_visualizer(raw: dict[str, Any]) -> VisualizerConfig:
    return VisualizerConfig(
        base_node_size=int(raw["base_node_size"]),
        size_scale=int(raw["size_scale"]),
        normal_edge_color=str(raw["normal_edge_color"]),
        cycle_edge_color=str(raw["cycle_edge_color"]),
        normal_edge_width=int(raw["normal_edge_width"]),
        cycle_edge_width=int(raw["cycle_edge_width"]),
    )


def _build_limits(raw: dict[str, Any]) -> LimitsConfig:
    return LimitsConfig(
        recent_files_default_max=int(raw["recent_files_default_max"]),
        ingredient_required_min=int(raw["ingredient_required_min"]),
        ingredient_required_max=int(raw["ingredient_required_max"]),
    )


@cache
def get_config() -> Config:
    """Return the parsed :class:`Config` singleton (loaded on first call)."""
    data = _load_toml()
    return Config(
        app=_build_app(data["app"]),
        paths=_build_paths(data["paths"]),
        timings=_build_timings(data["timings"]),
        ui=_build_ui(data["ui"]),
        visualizer=_build_visualizer(data["visualizer"]),
        limits=_build_limits(data["limits"]),
    )
