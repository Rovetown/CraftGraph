"""Tests for save utilities (backup-on-save)."""

from pathlib import Path

import pytest

from craftgraph.save_utils import save_with_backup


class TestSaveWithBackup:
    """save_with_backup() creates a .bak before overwriting."""

    def test_creates_bak_when_file_exists(self, tmp_path: Path) -> None:
        target = tmp_path / "recipes.txt"
        target.write_text("original content", encoding="utf-8")

        save_with_backup(target, "new content", backup=True)

        bak = tmp_path / "recipes.txt.bak"
        assert bak.exists()
        assert bak.read_text(encoding="utf-8") == "original content"
        assert target.read_text(encoding="utf-8") == "new content"

    def test_overwrites_existing_bak(self, tmp_path: Path) -> None:
        target = tmp_path / "recipes.txt"
        target.write_text("v1", encoding="utf-8")
        bak = tmp_path / "recipes.txt.bak"
        bak.write_text("stale backup", encoding="utf-8")

        save_with_backup(target, "v2", backup=True)

        assert bak.read_text(encoding="utf-8") == "v1"
        assert target.read_text(encoding="utf-8") == "v2"

    def test_no_bak_when_file_is_new(self, tmp_path: Path) -> None:
        target = tmp_path / "brand_new.txt"

        save_with_backup(target, "fresh content", backup=True)

        assert target.read_text(encoding="utf-8") == "fresh content"
        assert not (tmp_path / "brand_new.txt.bak").exists()

    def test_no_bak_when_backup_disabled(self, tmp_path: Path) -> None:
        target = tmp_path / "recipes.txt"
        target.write_text("original", encoding="utf-8")

        save_with_backup(target, "updated", backup=False)

        assert target.read_text(encoding="utf-8") == "updated"
        assert not (tmp_path / "recipes.txt.bak").exists()

    def test_backup_false_by_default(self, tmp_path: Path) -> None:
        target = tmp_path / "recipes.txt"
        target.write_text("original", encoding="utf-8")

        save_with_backup(target, "updated")

        assert target.read_text(encoding="utf-8") == "updated"
        assert not (tmp_path / "recipes.txt.bak").exists()

    def test_preserves_utf8_content_in_bak(self, tmp_path: Path) -> None:
        target = tmp_path / "recipes.txt"
        original = "DisplayName: \"Messer des Todes\";\n"
        target.write_text(original, encoding="utf-8")

        save_with_backup(target, "replaced", backup=True)

        bak = tmp_path / "recipes.txt.bak"
        assert bak.read_text(encoding="utf-8") == original
