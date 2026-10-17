"""Tests for craftgraph.theme -- centralized color definitions."""

from __future__ import annotations

from craftgraph.theme import (
    ACCENT_COLORS,
    COLORBLIND_PALETTES,
    UI_SCALE_OPTIONS,
    CodeEditorSettings,
    EditorColors,
    HighlightColors,
    NodeColors,
    NodeEditorSettings,
    SyntaxColors,
    ThemeColors,
    accent_name_from_hex,
    active_theme,
    apply_colorblind_palette,
    code_editor_settings_from_dict,
    code_editor_settings_to_dict,
    node_editor_settings_from_dict,
    node_editor_settings_to_dict,
    set_active_theme,
    theme_from_dict,
    theme_to_dict,
)


class TestNodeColors:
    """Default node colors match the originals in qt_nodes.py."""

    def test_defaults_exist_for_all_block_types(self) -> None:
        nc = NodeColors()
        assert nc.modified_recipe == (60, 120, 80)
        assert nc.added_recipe == (60, 140, 80)
        assert nc.alias_recipe == (80, 120, 120)
        assert nc.custom_food == (120, 100, 60)
        assert nc.fabricator == (80, 80, 160)
        assert nc.crafting_tab == (160, 120, 40)
        assert nc.custom_size == (100, 100, 100)
        assert nc.moved_recipe == (120, 80, 120)
        assert nc.custom_bio_fuel == (140, 100, 40)
        assert nc.custom_fragment_count == (80, 100, 140)
        assert nc.orphan_ingredient == (90, 90, 90)
        assert nc.sprite == (180, 160, 60)

    def test_override_single_color(self) -> None:
        nc = NodeColors(modified_recipe=(255, 0, 0))
        assert nc.modified_recipe == (255, 0, 0)
        # Others stay at defaults
        assert nc.added_recipe == (60, 140, 80)


class TestHighlightColors:
    def test_cycle_edge_default(self) -> None:
        hc = HighlightColors()
        assert hc.cycle_edge == (220, 60, 60, 255)

    def test_default_pipe(self) -> None:
        hc = HighlightColors()
        assert hc.default_pipe == (175, 95, 30, 255)

    def test_selected_node_border_default(self) -> None:
        hc = HighlightColors()
        assert hc.selected_node_border == "#ffcc00"


class TestSyntaxColors:
    def test_defaults_match_highlighter(self) -> None:
        sc = SyntaxColors()
        assert sc.block_type == "#8B008B"
        assert sc.field_key == "#007080"
        assert sc.string == "#228B22"
        assert sc.comment == "#808080"
        assert sc.error_underline == "#CC0000"


class TestEditorColors:
    def test_gutter_defaults_match_code_editor(self) -> None:
        ec = EditorColors()
        assert ec.gutter_background == "#F0F0F0"
        assert ec.gutter_text == "#808080"

    def test_background_default(self) -> None:
        ec = EditorColors()
        assert ec.background == "#252526"


class TestThemeColors:
    def test_default_construction(self) -> None:
        tc = ThemeColors()
        assert isinstance(tc.node, NodeColors)
        assert isinstance(tc.highlight, HighlightColors)
        assert isinstance(tc.syntax, SyntaxColors)
        assert isinstance(tc.editor, EditorColors)
        assert tc.high_contrast_borders is False
        assert tc.app_theme == "dark"
        assert tc.colorblind_mode == "none"
        assert tc.ui_scale == 100

    def test_override_nested(self) -> None:
        tc = ThemeColors(node=NodeColors(sprite=(0, 0, 0)))
        assert tc.node.sprite == (0, 0, 0)
        # Default sub-groups untouched
        assert tc.highlight.cycle_edge == (220, 60, 60, 255)


class TestActiveTheme:
    def test_active_theme_returns_instance(self) -> None:
        theme = active_theme()
        assert isinstance(theme, ThemeColors)

    def test_set_active_theme(self) -> None:
        original = active_theme()
        custom = ThemeColors(accent="#FF0000")
        set_active_theme(custom)
        assert active_theme().accent == "#FF0000"
        # Restore
        set_active_theme(original)

    def test_active_theme_identity(self) -> None:
        """Same object returned until replaced."""
        a = active_theme()
        b = active_theme()
        assert a is b


class TestSerialization:
    """Round-trip serialization of ThemeColors via dict."""

    def test_round_trip_defaults(self) -> None:
        """Default theme survives to_dict -> from_dict unchanged."""
        original = ThemeColors()
        rebuilt = theme_from_dict(theme_to_dict(original))
        assert rebuilt.node.modified_recipe == original.node.modified_recipe
        assert rebuilt.highlight.cycle_edge == original.highlight.cycle_edge
        assert rebuilt.syntax.block_type == original.syntax.block_type
        assert rebuilt.editor.background == original.editor.background
        assert rebuilt.accent == original.accent
        assert rebuilt.high_contrast_borders == original.high_contrast_borders

    def test_round_trip_custom_values(self) -> None:
        """Custom overrides survive serialization."""
        custom = ThemeColors(
            node=NodeColors(modified_recipe=(255, 0, 0), sprite=(10, 20, 30)),
            highlight=HighlightColors(cycle_edge=(0, 255, 0, 128)),
            syntax=SyntaxColors(block_type="#FF00FF"),
            editor=EditorColors(background="#111111"),
            accent="#00FF00",
            high_contrast_borders=True,
        )
        rebuilt = theme_from_dict(theme_to_dict(custom))
        assert rebuilt.node.modified_recipe == (255, 0, 0)
        assert rebuilt.node.sprite == (10, 20, 30)
        assert rebuilt.highlight.cycle_edge == (0, 255, 0, 128)
        assert rebuilt.syntax.block_type == "#FF00FF"
        assert rebuilt.editor.background == "#111111"
        assert rebuilt.accent == "#00FF00"
        assert rebuilt.high_contrast_borders is True

    def test_from_dict_empty_falls_back_to_defaults(self) -> None:
        """Empty dict produces default theme."""
        rebuilt = theme_from_dict({})
        defaults = ThemeColors()
        assert rebuilt.node.modified_recipe == defaults.node.modified_recipe
        assert rebuilt.syntax.block_type == defaults.syntax.block_type

    def test_from_dict_partial_preserves_defaults(self) -> None:
        """Partially populated dict fills missing fields with defaults."""
        data = {"node": {"modified_recipe": [200, 100, 50]}}
        rebuilt = theme_from_dict(data)
        assert rebuilt.node.modified_recipe == (200, 100, 50)
        # Other node colors stay at defaults
        assert rebuilt.node.added_recipe == NodeColors().added_recipe

    def test_from_dict_malformed_ignored(self) -> None:
        """Malformed values are silently skipped."""
        data = {
            "node": {"modified_recipe": "not-a-list"},
            "syntax": {"block_type": 12345},
            "accent": 999,
            "high_contrast_borders": "maybe",
        }
        rebuilt = theme_from_dict(data)
        defaults = ThemeColors()
        assert rebuilt.node.modified_recipe == defaults.node.modified_recipe
        assert rebuilt.syntax.block_type == defaults.syntax.block_type
        assert rebuilt.accent == defaults.accent
        assert rebuilt.high_contrast_borders == defaults.high_contrast_borders

    def test_to_dict_uses_lists_for_tuples(self) -> None:
        """JSON-compatible: tuples become lists in the dict."""
        d = theme_to_dict(ThemeColors())
        assert isinstance(d["node"], dict)
        assert isinstance(d["node"]["modified_recipe"], list)  # type: ignore[index]
        assert isinstance(d["highlight"], dict)
        assert isinstance(d["highlight"]["cycle_edge"], list)  # type: ignore[index]


class TestAccentColors:
    def test_known_accents(self) -> None:
        assert "Blue" in ACCENT_COLORS
        assert "Red" in ACCENT_COLORS
        assert len(ACCENT_COLORS) == 6

    def test_accent_name_from_hex_known(self) -> None:
        assert accent_name_from_hex("#8CB4FF") == "Blue"
        assert accent_name_from_hex("#E57373") == "Red"

    def test_accent_name_from_hex_case_insensitive(self) -> None:
        assert accent_name_from_hex("#8cb4ff") == "Blue"

    def test_accent_name_from_hex_unknown_falls_back(self) -> None:
        assert accent_name_from_hex("#123456") == "Blue"


class TestColorblindPalettes:
    def test_all_modes_defined(self) -> None:
        assert "deuteranopia" in COLORBLIND_PALETTES
        assert "protanopia" in COLORBLIND_PALETTES
        assert "tritanopia" in COLORBLIND_PALETTES

    def test_palettes_have_all_fields(self) -> None:
        for mode, palette in COLORBLIND_PALETTES.items():
            for f in (
                "modified_recipe",
                "added_recipe",
                "alias_recipe",
                "custom_food",
                "fabricator",
                "crafting_tab",
                "custom_size",
                "moved_recipe",
                "custom_bio_fuel",
                "custom_fragment_count",
                "orphan_ingredient",
                "sprite",
            ):
                val = getattr(palette, f)
                assert isinstance(val, tuple), f"{mode}.{f} not a tuple"
                assert len(val) == 3, f"{mode}.{f} wrong length"

    def test_apply_colorblind_none_unchanged(self) -> None:
        theme = ThemeColors(colorblind_mode="none")
        result = apply_colorblind_palette(theme)
        assert result is theme

    def test_apply_colorblind_deuteranopia_remaps(self) -> None:
        theme = ThemeColors(colorblind_mode="deuteranopia")
        result = apply_colorblind_palette(theme)
        assert result.node is COLORBLIND_PALETTES["deuteranopia"]
        assert result.colorblind_mode == "deuteranopia"
        # Other groups unchanged
        assert result.highlight == theme.highlight

    def test_apply_preserves_other_fields(self) -> None:
        theme = ThemeColors(
            accent="#FF0000",
            high_contrast_borders=True,
            app_theme="light",
            colorblind_mode="tritanopia",
            ui_scale=150,
        )
        result = apply_colorblind_palette(theme)
        assert result.accent == "#FF0000"
        assert result.high_contrast_borders is True
        assert result.app_theme == "light"
        assert result.ui_scale == 150


class TestUIScale:
    def test_options_include_100_and_200(self) -> None:
        assert 100 in UI_SCALE_OPTIONS
        assert 200 in UI_SCALE_OPTIONS

    def test_default_is_100(self) -> None:
        assert ThemeColors().ui_scale == 100


class TestScaledPt:
    """scaled_pt multiplies a base point size by the active UI scale."""

    def test_identity_at_100(self) -> None:
        from craftgraph.theme import scaled_pt

        assert scaled_pt(10, ThemeColors(ui_scale=100)) == 10
        assert scaled_pt(11, ThemeColors(ui_scale=100)) == 11

    def test_scales_up(self) -> None:
        from craftgraph.theme import scaled_pt

        assert scaled_pt(10, ThemeColors(ui_scale=150)) == 15
        assert scaled_pt(20, ThemeColors(ui_scale=200)) == 40

    def test_minimum_is_one_pt(self) -> None:
        from craftgraph.theme import scaled_pt

        # Even an absurdly tiny base never returns 0.
        assert scaled_pt(0, ThemeColors(ui_scale=100)) == 1

    def test_uses_active_theme_when_omitted(self) -> None:
        from craftgraph.theme import scaled_pt

        original = active_theme()
        try:
            set_active_theme(ThemeColors(ui_scale=125))
            assert scaled_pt(8) == 10
        finally:
            set_active_theme(original)


class TestScaledSize:
    """scaled_size scales a (w, h) pair by the active UI scale."""

    def test_identity_at_100(self) -> None:
        from craftgraph.theme import scaled_size

        assert scaled_size(600, 520, ThemeColors(ui_scale=100)) == (600, 520)

    def test_scales_both_dimensions(self) -> None:
        from craftgraph.theme import scaled_size

        assert scaled_size(600, 520, ThemeColors(ui_scale=150)) == (900, 780)

    def test_uses_active_theme_when_omitted(self) -> None:
        from craftgraph.theme import scaled_size

        original = active_theme()
        try:
            set_active_theme(ThemeColors(ui_scale=200))
            assert scaled_size(100, 50) == (200, 100)
        finally:
            set_active_theme(original)


class TestSerializationNewFields:
    """Round-trip of app_theme, colorblind_mode, and ui_scale."""

    def test_round_trip_new_fields(self) -> None:
        original = ThemeColors(
            app_theme="light",
            colorblind_mode="protanopia",
            ui_scale=150,
        )
        rebuilt = theme_from_dict(theme_to_dict(original))
        assert rebuilt.app_theme == "light"
        assert rebuilt.colorblind_mode == "protanopia"
        assert rebuilt.ui_scale == 150

    def test_from_dict_invalid_app_theme_falls_back(self) -> None:
        rebuilt = theme_from_dict({"app_theme": "neon"})
        assert rebuilt.app_theme == "dark"

    def test_from_dict_invalid_colorblind_falls_back(self) -> None:
        rebuilt = theme_from_dict({"colorblind_mode": "monochromacy"})
        assert rebuilt.colorblind_mode == "none"

    def test_from_dict_invalid_ui_scale_falls_back(self) -> None:
        rebuilt = theme_from_dict({"ui_scale": 137})
        assert rebuilt.ui_scale == 100

    def test_from_dict_missing_new_fields_uses_defaults(self) -> None:
        rebuilt = theme_from_dict({})
        assert rebuilt.app_theme == "dark"
        assert rebuilt.colorblind_mode == "none"
        assert rebuilt.ui_scale == 100


class TestNodeEditorSettings:
    """NodeEditorSettings defaults and serialization."""

    def test_defaults(self) -> None:
        s = NodeEditorSettings()
        assert s.zoom_speed == 1.0
        assert s.invert_zoom is False
        assert s.pan_with_mmb is False
        assert s.show_minimap is True
        assert s.show_grid is True
        assert s.grid_size == 50
        assert s.snap_to_grid is False
        assert s.grid_style == "lines"
        assert s.show_thumbnails is True
        assert s.thumbnail_size == 64
        assert s.show_port_labels is True
        assert s.warn_before_cycles is True
        assert s.pipe_style == "curved"
        assert s.pipe_width == 2.0
        assert s.animate_pipes is False

    def test_round_trip(self) -> None:
        custom = NodeEditorSettings(
            zoom_speed=2.5,
            invert_zoom=True,
            pan_with_mmb=False,
            show_minimap=False,
            show_grid=False,
            grid_size=30,
            snap_to_grid=True,
            grid_style="dots",
            show_thumbnails=False,
            thumbnail_size=48,
            show_port_labels=False,
            warn_before_cycles=False,
            pipe_style="angle",
            pipe_width=3.5,
            animate_pipes=True,
        )
        rebuilt = node_editor_settings_from_dict(node_editor_settings_to_dict(custom))
        assert rebuilt.zoom_speed == 2.5
        assert rebuilt.invert_zoom is True
        assert rebuilt.pan_with_mmb is False
        assert rebuilt.show_minimap is False
        assert rebuilt.show_grid is False
        assert rebuilt.grid_size == 30
        assert rebuilt.snap_to_grid is True
        assert rebuilt.grid_style == "dots"
        assert rebuilt.show_thumbnails is False
        assert rebuilt.thumbnail_size == 48
        assert rebuilt.show_port_labels is False
        assert rebuilt.warn_before_cycles is False
        assert rebuilt.pipe_style == "angle"
        assert rebuilt.pipe_width == 3.5
        assert rebuilt.animate_pipes is True

    def test_from_dict_empty_falls_back(self) -> None:
        rebuilt = node_editor_settings_from_dict({})
        defaults = NodeEditorSettings()
        assert rebuilt.zoom_speed == defaults.zoom_speed
        assert rebuilt.grid_style == defaults.grid_style

    def test_from_dict_invalid_values_fall_back(self) -> None:
        rebuilt = node_editor_settings_from_dict(
            {
                "zoom_speed": 99.0,
                "grid_size": 5,
                "grid_style": "hexagonal",
                "invert_zoom": "yes",
                "thumbnail_size": 999,
                "pipe_style": "zigzag",
                "pipe_width": 0.1,
                "show_thumbnails": "maybe",
                "animate_pipes": 42,
            }
        )
        defaults = NodeEditorSettings()
        assert rebuilt.zoom_speed == defaults.zoom_speed
        assert rebuilt.grid_size == defaults.grid_size
        assert rebuilt.grid_style == defaults.grid_style
        assert rebuilt.invert_zoom == defaults.invert_zoom
        assert rebuilt.thumbnail_size == defaults.thumbnail_size
        assert rebuilt.pipe_style == defaults.pipe_style
        assert rebuilt.pipe_width == defaults.pipe_width
        assert rebuilt.show_thumbnails == defaults.show_thumbnails
        assert rebuilt.animate_pipes == defaults.animate_pipes


class TestCodeEditorSettingsDefaults:
    """CodeEditorSettings has sensible defaults."""

    def test_default_font(self) -> None:
        s = CodeEditorSettings()
        assert s.font_family == "Consolas"
        assert s.font_size == 10

    def test_default_display(self) -> None:
        s = CodeEditorSettings()
        assert s.show_line_numbers is True
        assert s.highlight_current_line is True
        assert s.word_wrap is False
        assert s.tab_width == 4

    def test_default_editing(self) -> None:
        s = CodeEditorSettings()
        assert s.auto_indent is True
        assert s.auto_close_brackets is True
        assert s.strip_trailing_whitespace is True

    def test_default_sync(self) -> None:
        s = CodeEditorSettings()
        assert s.parse_debounce_enabled is True
        assert s.parse_debounce_ms == 400
        assert s.show_parse_errors_inline is True


class TestCodeEditorSettingsRoundTrip:
    """Serialize and deserialize CodeEditorSettings."""

    def test_round_trip_defaults(self) -> None:
        original = CodeEditorSettings()
        rebuilt = code_editor_settings_from_dict(code_editor_settings_to_dict(original))
        assert rebuilt == original

    def test_round_trip_custom_values(self) -> None:
        original = CodeEditorSettings(
            font_family="Courier New",
            font_size=14,
            show_line_numbers=False,
            highlight_current_line=False,
            word_wrap=True,
            tab_width=2,
            auto_indent=False,
            auto_close_brackets=False,
            strip_trailing_whitespace=False,
            parse_debounce_enabled=False,
            parse_debounce_ms=800,
            show_parse_errors_inline=False,
        )
        rebuilt = code_editor_settings_from_dict(code_editor_settings_to_dict(original))
        assert rebuilt == original

    def test_missing_keys_use_defaults(self) -> None:
        rebuilt = code_editor_settings_from_dict({})
        assert rebuilt == CodeEditorSettings()

    def test_invalid_values_fall_back_to_defaults(self) -> None:
        rebuilt = code_editor_settings_from_dict(
            {
                "font_family": "",
                "font_size": 99,
                "tab_width": 0,
                "parse_debounce_ms": 50,
                "show_line_numbers": "yes",
                "auto_indent": 1,
            }
        )
        defaults = CodeEditorSettings()
        assert rebuilt.font_family == defaults.font_family
        assert rebuilt.font_size == defaults.font_size
        assert rebuilt.tab_width == defaults.tab_width
        assert rebuilt.parse_debounce_ms == defaults.parse_debounce_ms
        assert rebuilt.show_line_numbers == defaults.show_line_numbers
        assert rebuilt.auto_indent == defaults.auto_indent

    def test_to_dict_keys(self) -> None:
        d = code_editor_settings_to_dict(CodeEditorSettings())
        expected_keys = {
            "font_family",
            "font_size",
            "show_line_numbers",
            "highlight_current_line",
            "word_wrap",
            "tab_width",
            "auto_indent",
            "auto_close_brackets",
            "strip_trailing_whitespace",
            "parse_debounce_enabled",
            "parse_debounce_ms",
            "show_parse_errors_inline",
        }
        assert set(d.keys()) == expected_keys


class TestFileWatchingSettingsRoundTrip:
    """Serialize and deserialize FileWatchingSettings."""

    def test_round_trip_defaults(self) -> None:
        from craftgraph.theme import (
            FileWatchingSettings,
            file_watching_settings_from_dict,
            file_watching_settings_to_dict,
        )

        original = FileWatchingSettings()
        rebuilt = file_watching_settings_from_dict(file_watching_settings_to_dict(original))
        assert rebuilt == original

    def test_round_trip_custom(self) -> None:
        from craftgraph.theme import (
            FileWatchingSettings,
            file_watching_settings_from_dict,
            file_watching_settings_to_dict,
        )

        original = FileWatchingSettings(
            enabled=False,
            debounce_enabled=False,
            debounce_ms=500,
            notify_status_bar=False,
            notify_flash_tab=False,
            notify_sound_on_cycle=True,
        )
        rebuilt = file_watching_settings_from_dict(file_watching_settings_to_dict(original))
        assert rebuilt == original

    def test_invalid_debounce_enabled_falls_back(self) -> None:
        from craftgraph.theme import FileWatchingSettings, file_watching_settings_from_dict

        rebuilt = file_watching_settings_from_dict({"debounce_enabled": "yes"})
        assert rebuilt.debounce_enabled is FileWatchingSettings().debounce_enabled

    def test_missing_debounce_enabled_defaults_true(self) -> None:
        from craftgraph.theme import file_watching_settings_from_dict

        rebuilt = file_watching_settings_from_dict({})
        assert rebuilt.debounce_enabled is True

    def test_notification_defaults(self) -> None:
        from craftgraph.theme import FileWatchingSettings

        s = FileWatchingSettings()
        assert s.notify_status_bar is True
        assert s.notify_flash_tab is True
        assert s.notify_sound_on_cycle is False

    def test_invalid_notification_values_fall_back(self) -> None:
        from craftgraph.theme import FileWatchingSettings, file_watching_settings_from_dict

        rebuilt = file_watching_settings_from_dict(
            {
                "notify_status_bar": "yes",
                "notify_flash_tab": 1,
                "notify_sound_on_cycle": "true",
            }
        )
        defaults = FileWatchingSettings()
        assert rebuilt.notify_status_bar is defaults.notify_status_bar
        assert rebuilt.notify_flash_tab is defaults.notify_flash_tab
        assert rebuilt.notify_sound_on_cycle is defaults.notify_sound_on_cycle


class TestNoQtImports:
    """Theme module must stay Qt-free."""

    def test_no_pyside6_import(self) -> None:
        import importlib
        from pathlib import Path

        spec = importlib.util.find_spec("craftgraph.theme")
        assert spec is not None
        assert spec.origin is not None
        code = Path(spec.origin).read_text(encoding="utf-8")
        assert "PySide6" not in code
        assert "NodeGraphQt" not in code
