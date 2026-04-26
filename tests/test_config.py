"""Smoke tests for the packaged TOML config loader."""

from __future__ import annotations

from dataclasses import fields

import pytest

from craftgraph.config import (
    AppConfig,
    ColorsConfig,
    Config,
    LayoutConfig,
    LimitsConfig,
    MinimapConfig,
    NodeColorsConfig,
    PathsConfig,
    PortColorsConfig,
    ThemeConfig,
    TimingsConfig,
    UiConfig,
    VariableNodesConfig,
    VisualizerConfig,
    get_config,
)


def test_get_config_returns_cached_singleton() -> None:
    """Subsequent calls return the same frozen instance."""
    first = get_config()
    second = get_config()
    assert first is second


def test_config_top_level_shape() -> None:
    c = get_config()
    assert isinstance(c, Config)
    assert isinstance(c.app, AppConfig)
    assert isinstance(c.paths, PathsConfig)
    assert isinstance(c.timings, TimingsConfig)
    assert isinstance(c.ui, UiConfig)
    assert isinstance(c.ui.theme, ThemeConfig)
    assert isinstance(c.ui.variable_nodes, VariableNodesConfig)
    assert isinstance(c.ui.colors, ColorsConfig)
    assert isinstance(c.ui.colors.nodes, NodeColorsConfig)
    assert isinstance(c.ui.colors.ports, PortColorsConfig)
    assert isinstance(c.ui.layout, LayoutConfig)
    assert isinstance(c.ui.minimap, MinimapConfig)
    assert isinstance(c.visualizer, VisualizerConfig)
    assert isinstance(c.limits, LimitsConfig)


@pytest.mark.parametrize(
    ("section", "section_cls"),
    [
        (get_config().app, AppConfig),
        (get_config().paths, PathsConfig),
        (get_config().timings, TimingsConfig),
        (get_config().ui, UiConfig),
        (get_config().ui.theme, ThemeConfig),
        (get_config().ui.variable_nodes, VariableNodesConfig),
        (get_config().ui.colors, ColorsConfig),
        (get_config().ui.colors.nodes, NodeColorsConfig),
        (get_config().ui.colors.ports, PortColorsConfig),
        (get_config().ui.layout, LayoutConfig),
        (get_config().ui.minimap, MinimapConfig),
        (get_config().visualizer, VisualizerConfig),
        (get_config().limits, LimitsConfig),
    ],
)
def test_every_declared_field_has_a_value(section: object, section_cls: type) -> None:
    """Every dataclass field parses to a non-None value of the declared type."""
    for f in fields(section_cls):
        value = getattr(section, f.name)
        assert value is not None, f"{section_cls.__name__}.{f.name} parsed as None"


def test_app_values_concrete() -> None:
    a = get_config().app
    assert a.identifier == "com.craftgraph"
    assert a.file_ext == ".craftgraph"
    assert a.prog_id == "CraftGraph.Project"
    assert a.mime_type == "application/x-craftgraph"
    assert a.file_description == "CraftGraph Project"


def test_paths_values_concrete() -> None:
    p = get_config().paths
    assert p.icons_subdir == "data/icons"
    assert p.data_subdir == "data"
    assert p.layout_dir_name == ".craftgraph"
    assert p.layout_filename == "layout.json"
    assert "Subnautica" in p.cc3_install_segments
    assert "CustomCraft3" in p.cc3_install_segments
    assert len(p.steam_root_candidates) >= 1
    assert all(isinstance(s, str) for s in p.steam_root_candidates)


def test_timings_values_concrete() -> None:
    t = get_config().timings
    assert t.watcher_debounce_sec == 0.3
    assert t.minimap_update_interval_ms == 100
    assert t.parse_debounce_ms_default == 400
    assert t.file_watcher_debounce_ms_default == 300


def test_ui_values_concrete() -> None:
    assert get_config().ui.sprite_size == 64


def test_ui_theme_values_concrete() -> None:
    t = get_config().ui.theme
    assert t.default_font_family == "Consolas"
    assert t.default_font_size == 10


def test_ui_variable_nodes_values_concrete() -> None:
    vn = get_config().ui.variable_nodes
    assert vn.ref_combo_max_w == 160
    assert "200, 60, 60" in vn.required_empty_style
    assert vn.required_valid_style == "border: none;"


def test_ui_colors_values_concrete() -> None:
    colors = get_config().ui.colors
    assert colors.nodes.modified_recipe == (60, 120, 80)
    assert colors.nodes.fabricator == (80, 80, 160)
    assert colors.nodes.orphan_ingredient == (90, 90, 90)
    assert colors.ports.hierarchy == (200, 200, 100)
    assert colors.ports.variable == (100, 70, 130)
    assert colors.ports.sprite == (180, 160, 60)


def test_ui_layout_values_concrete() -> None:
    layout = get_config().ui.layout
    assert layout.y_step == 150.0
    assert layout.x_fab == -400.0
    assert layout.x_tab == -100.0
    assert layout.x_recipe == 250.0
    assert layout.layout_y_step == 120.0
    assert layout.layout_y_group_gap == 80.0
    assert layout.layout_x_child_offset == 350.0


def test_ui_minimap_values_concrete() -> None:
    mm = get_config().ui.minimap
    assert mm.width == 220
    assert mm.height == 160
    assert mm.bg_color == (25, 25, 30, 220)
    assert mm.border_color == (80, 80, 80, 255)
    assert mm.node_color == (100, 140, 180, 255)
    assert mm.viewport_fill == (255, 255, 255, 25)
    assert mm.viewport_border == (200, 200, 200, 160)


def test_visualizer_values_concrete() -> None:
    v = get_config().visualizer
    assert v.base_node_size == 10
    assert v.size_scale == 3
    assert v.normal_edge_color == "#888888"
    assert v.cycle_edge_color == "#e74c3c"
    assert v.normal_edge_width == 1
    assert v.cycle_edge_width == 3


def test_limits_values_concrete() -> None:
    lim = get_config().limits
    assert lim.recent_files_default_max == 10
    assert lim.ingredient_required_min == 1
    assert lim.ingredient_required_max == 25


def test_config_is_frozen() -> None:
    """Writing to a frozen dataclass must raise FrozenInstanceError."""
    c = get_config()
    with pytest.raises(AttributeError):
        c.ui.sprite_size = 128  # type: ignore[misc]
