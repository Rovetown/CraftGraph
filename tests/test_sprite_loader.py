"""Tests for craftgraph.sprite_loader -- Assets/ folder scanning."""

from pathlib import Path

from craftgraph.sprite_loader import lookup_sprite, resolve_sprite, scan_assets_dir


class TestScanAssetsDir:
    """Tests for scan_assets_dir()."""

    def test_returns_empty_when_no_assets_dir(self, tmp_path: Path) -> None:
        result = scan_assets_dir(tmp_path)
        assert result == {}

    def test_returns_empty_when_assets_is_file(self, tmp_path: Path) -> None:
        (tmp_path / "Assets").write_text("not a dir", encoding="utf-8")
        result = scan_assets_dir(tmp_path)
        assert result == {}

    def test_returns_empty_when_assets_has_no_pngs(self, tmp_path: Path) -> None:
        assets = tmp_path / "Assets"
        assets.mkdir()
        (assets / "readme.txt").write_text("no pngs", encoding="utf-8")
        result = scan_assets_dir(tmp_path)
        assert result == {}

    def test_finds_single_png(self, tmp_path: Path) -> None:
        assets = tmp_path / "Assets"
        assets.mkdir()
        png = assets / "Titanium.png"
        png.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header

        result = scan_assets_dir(tmp_path)
        assert "titanium" in result
        assert result["titanium"] == png.resolve()

    def test_case_insensitive_keys(self, tmp_path: Path) -> None:
        assets = tmp_path / "Assets"
        assets.mkdir()
        (assets / "Alch_Fab.png").write_bytes(b"\x89PNG")
        (assets / "DR_PEEPER.png").write_bytes(b"\x89PNG")

        result = scan_assets_dir(tmp_path)
        assert "alch_fab" in result
        assert "dr_peeper" in result

    def test_ignores_non_png_files(self, tmp_path: Path) -> None:
        assets = tmp_path / "Assets"
        assets.mkdir()
        (assets / "icon.png").write_bytes(b"\x89PNG")
        (assets / "icon.jpg").write_bytes(b"\xff\xd8")
        (assets / "icon.bmp").write_bytes(b"BM")
        (assets / "notes.txt").write_text("text", encoding="utf-8")

        result = scan_assets_dir(tmp_path)
        assert len(result) == 1
        assert "icon" in result

    def test_ignores_subdirectories(self, tmp_path: Path) -> None:
        assets = tmp_path / "Assets"
        assets.mkdir()
        subdir = assets / "SubFolder.png"  # directory named like a PNG
        subdir.mkdir()

        result = scan_assets_dir(tmp_path)
        assert result == {}

    def test_multiple_pngs(self, tmp_path: Path) -> None:
        assets = tmp_path / "Assets"
        assets.mkdir()
        for name in ["Titanium", "Copper", "Gold", "Alch_Fab"]:
            (assets / f"{name}.png").write_bytes(b"\x89PNG")

        result = scan_assets_dir(tmp_path)
        assert len(result) == 4
        assert all(k == k.lower() for k in result)

    def test_first_match_wins_on_case_collision(self, tmp_path: Path) -> None:
        """If two files differ only by case, the first one found wins."""
        assets = tmp_path / "Assets"
        assets.mkdir()
        (assets / "Titanium.png").write_bytes(b"\x89PNG")
        # On case-insensitive filesystems (Windows), this overwrites.
        # On case-sensitive filesystems (Linux), both exist.
        # Either way, only one key "titanium" should appear.
        (assets / "titanium.png").write_bytes(b"\x89PNG")

        result = scan_assets_dir(tmp_path)
        assert "titanium" in result
        # Should have exactly one entry regardless of filesystem
        assert len([k for k in result if k == "titanium"]) == 1

    def test_png_extension_case_insensitive(self, tmp_path: Path) -> None:
        assets = tmp_path / "Assets"
        assets.mkdir()
        (assets / "Icon.PNG").write_bytes(b"\x89PNG")

        result = scan_assets_dir(tmp_path)
        assert "icon" in result


class TestLookupSprite:
    """Tests for lookup_sprite()."""

    def test_returns_path_on_match(self) -> None:
        p = Path("/fake/Assets/Titanium.png")
        lookup = {"titanium": p}
        assert lookup_sprite(lookup, "Titanium") == p

    def test_case_insensitive_match(self) -> None:
        p = Path("/fake/Assets/Alch_Fab.png")
        lookup = {"alch_fab": p}
        assert lookup_sprite(lookup, "ALCH_FAB") == p
        assert lookup_sprite(lookup, "alch_fab") == p
        assert lookup_sprite(lookup, "Alch_Fab") == p

    def test_returns_none_on_no_match(self) -> None:
        lookup = {"titanium": Path("/fake/Assets/Titanium.png")}
        assert lookup_sprite(lookup, "Gold") is None

    def test_empty_lookup(self) -> None:
        assert lookup_sprite({}, "Anything") is None


class TestResolveSprite:
    """Tests for resolve_sprite() -- manual override + auto-assign fallback."""

    def test_manual_override_takes_priority(self) -> None:
        manual = {"titanium": Path("/custom/Titanium.png")}
        auto = {"titanium": Path("/assets/Titanium.png")}
        result = resolve_sprite("Titanium", manual, auto)
        assert result == Path("/custom/Titanium.png")

    def test_falls_back_to_auto_assign(self) -> None:
        manual: dict[str, Path] = {}
        auto = {"titanium": Path("/assets/Titanium.png")}
        result = resolve_sprite("Titanium", manual, auto)
        assert result == Path("/assets/Titanium.png")

    def test_returns_none_when_no_match(self) -> None:
        result = resolve_sprite("Gold", {}, {})
        assert result is None

    def test_case_insensitive_manual_lookup(self) -> None:
        manual = {"alch_fab": Path("/custom/Alch_Fab.png")}
        result = resolve_sprite("ALCH_FAB", manual, {})
        assert result == Path("/custom/Alch_Fab.png")

    def test_manual_override_with_no_auto_match(self) -> None:
        manual = {"custom_item": Path("/custom/custom.png")}
        result = resolve_sprite("custom_item", manual, {})
        assert result == Path("/custom/custom.png")
