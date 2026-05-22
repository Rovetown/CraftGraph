"""Tests for the CodeEditor widget with line number sidebar (Step M5).

These tests require PySide6.  They are skipped automatically when
PySide6 is not installed.

Run:  uv run --extra qt pytest tests/test_code_editor.py -v
"""

from __future__ import annotations


import pytest

pytest.importorskip(
    "PySide6",
    reason="PySide6 not installed (install with: uv sync --extra qt)",
)

from PySide6 import QtWidgets

from craftgraph.code_editor import CodeEditor, FieldContext, LineNumberArea

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def editor(qapp):
    """Fresh CodeEditor for each test."""
    return CodeEditor()


# ---------------------------------------------------------------------------
# Tests: construction
# ---------------------------------------------------------------------------


class TestCodeEditorCreation:
    def test_is_plain_text_edit(self, editor):
        assert isinstance(editor, QtWidgets.QPlainTextEdit)

    def test_has_line_number_area(self, editor):
        assert isinstance(editor.line_number_area, LineNumberArea)

    def test_line_number_area_is_child(self, editor):
        assert editor.line_number_area.parent() is editor


# ---------------------------------------------------------------------------
# Tests: gutter width calculation
# ---------------------------------------------------------------------------


class TestLineNumberAreaWidth:
    def test_width_positive_for_empty_document(self, editor):
        assert editor.line_number_area_width() > 0

    def test_width_increases_at_10_lines(self, editor):
        width_single = editor.line_number_area_width()
        editor.setPlainText("\n" * 10)  # 11 blocks -> 2 digits
        width_double = editor.line_number_area_width()
        assert width_double > width_single

    def test_width_increases_at_100_lines(self, editor):
        editor.setPlainText("\n" * 9)  # 10 blocks -> 2 digits
        width_two = editor.line_number_area_width()
        editor.setPlainText("\n" * 100)  # 101 blocks -> 3 digits
        width_three = editor.line_number_area_width()
        assert width_three > width_two


# ---------------------------------------------------------------------------
# Tests: viewport margins
# ---------------------------------------------------------------------------


class TestViewportMargins:
    def test_left_margin_matches_gutter_width(self, editor):
        assert editor.viewportMargins().left() == editor.line_number_area_width()

    def test_margins_update_on_block_count_change(self, editor):
        margin_before = editor.viewportMargins().left()
        editor.setPlainText("\n" * 100)
        margin_after = editor.viewportMargins().left()
        assert margin_after > margin_before


# ---------------------------------------------------------------------------
# Tests: size hint
# ---------------------------------------------------------------------------


class TestLineNumberAreaSizeHint:
    def test_size_hint_width_matches_gutter(self, editor):
        hint = editor.line_number_area.sizeHint()
        assert hint.width() == editor.line_number_area_width()

    def test_size_hint_height_is_zero(self, editor):
        hint = editor.line_number_area.sizeHint()
        assert hint.height() == 0


# ---------------------------------------------------------------------------
# Tests: autocomplete (Step M7)
# ---------------------------------------------------------------------------


def _make_completer(words: list[str]) -> QtWidgets.QCompleter:
    """Create a QCompleter from a word list."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QCompleter

    completer = QCompleter(words)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    return completer


class TestAutocompleteSetup:
    def test_set_completer_stores_reference(self, editor):
        completer = _make_completer(["Titanium", "Gold"])
        editor.set_completer(completer)
        assert editor.completer() is completer

    def test_completer_widget_is_editor(self, editor):
        completer = _make_completer(["Titanium"])
        editor.set_completer(completer)
        assert completer.widget() is editor

    def test_completer_default_is_none(self, editor):
        assert editor.completer() is None

    def test_replace_completer(self, editor):
        c1 = _make_completer(["Alpha"])
        c2 = _make_completer(["Beta"])
        editor.set_completer(c1)
        editor.set_completer(c2)
        assert editor.completer() is c2


class TestTextUnderCursor:
    def test_empty_document(self, editor):
        assert editor.text_under_cursor() == ""

    def test_single_word(self, editor):
        editor.setPlainText("Titanium")
        cursor = editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        assert editor.text_under_cursor() == "Titanium"

    def test_word_after_colon_space(self, editor):
        editor.setPlainText("ItemID: Tit")
        cursor = editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        assert editor.text_under_cursor() == "Tit"

    def test_mid_line_word(self, editor):
        editor.setPlainText("ItemID: Gold;")
        cursor = editor.textCursor()
        # Position cursor inside "Gold" (position 10 = 'l')
        cursor.setPosition(10)
        editor.setTextCursor(cursor)
        assert editor.text_under_cursor() == "Gold"


class TestInsertCompletion:
    def test_replaces_current_word(self, editor):
        completer = _make_completer(["Titanium", "TitaniumIngot"])
        editor.set_completer(completer)

        editor.setPlainText("ItemID: Tit")
        cursor = editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        editor.setTextCursor(cursor)

        editor._insert_completion("Titanium")

        assert editor.toPlainText() == "ItemID: Titanium"

    def test_replaces_partial_match(self, editor):
        completer = _make_completer(["Quartz"])
        editor.set_completer(completer)

        editor.setPlainText("Qu")
        cursor = editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        editor.setTextCursor(cursor)

        editor._insert_completion("Quartz")

        assert editor.toPlainText() == "Quartz"

    def test_empty_prefix_inserts_full_word(self, editor):
        completer = _make_completer(["Glass"])
        editor.set_completer(completer)

        editor.setPlainText("ItemID: ")
        cursor = editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        editor.setTextCursor(cursor)

        editor._insert_completion("Glass")

        assert editor.toPlainText() == "ItemID: Glass"


class TestMinPrefixLength:
    def test_short_prefix_does_not_trigger(self, editor):
        """Prefixes shorter than MIN_PREFIX_LENGTH should not show popup."""
        assert editor.MIN_PREFIX_LENGTH >= 2


# ---------------------------------------------------------------------------
# Tests: context-aware autocomplete (Step M7 -- final checkbox)
# ---------------------------------------------------------------------------


def _place_cursor_at_end(editor):
    """Move the text cursor to the end of the document."""
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)


def _place_cursor_at(editor, line: int, col: int):
    """Move cursor to a specific line (0-based) and column."""
    block = editor.document().findBlockByNumber(line)
    cursor = editor.textCursor()
    cursor.setPosition(block.position() + col)
    editor.setTextCursor(cursor)


class TestDetectFieldContext:
    def test_item_id_field(self, editor):
        editor.setPlainText("    ItemID: Tit")
        _place_cursor_at_end(editor)
        assert editor.detect_field_context() == FieldContext.ITEM_ID

    def test_path_field(self, editor):
        editor.setPlainText("    Path: Fabr")
        _place_cursor_at_end(editor)
        assert editor.detect_field_context() == FieldContext.PATH

    def test_old_path_field(self, editor):
        editor.setPlainText("    OldPath: Fabricator/Resources")
        _place_cursor_at_end(editor)
        assert editor.detect_field_context() == FieldContext.PATH

    def test_new_path_field(self, editor):
        editor.setPlainText("    NewPath: Fabricator/Surv")
        _place_cursor_at_end(editor)
        assert editor.detect_field_context() == FieldContext.PATH

    def test_parent_tab_path_field(self, editor):
        editor.setPlainText("    ParentTabPath: MyFab/Tab")
        _place_cursor_at_end(editor)
        assert editor.detect_field_context() == FieldContext.PATH

    def test_sprite_item_id_field(self, editor):
        editor.setPlainText("    SpriteItemID: Peep")
        _place_cursor_at_end(editor)
        assert editor.detect_field_context() == FieldContext.ITEM_ID

    def test_no_field_key_defaults_to_item_id(self, editor):
        editor.setPlainText("    some random text")
        _place_cursor_at_end(editor)
        assert editor.detect_field_context() == FieldContext.ITEM_ID

    def test_empty_document(self, editor):
        assert editor.detect_field_context() == FieldContext.ITEM_ID

    def test_case_insensitive_path(self, editor):
        editor.setPlainText("    path: Fabr")
        _place_cursor_at_end(editor)
        assert editor.detect_field_context() == FieldContext.PATH

    def test_compact_inline_last_field_wins(self, editor):
        """Multiple fields on one line -- last field key before cursor wins."""
        editor.setPlainText("(TabID:Foods;ParentTabPath:CF3mod/")
        _place_cursor_at_end(editor)
        assert editor.detect_field_context() == FieldContext.PATH

    def test_compact_inline_id_after_path(self, editor):
        """ItemID after Path on the same line."""
        editor.setPlainText("Path:Fabricator;ItemID:Tit")
        _place_cursor_at_end(editor)
        assert editor.detect_field_context() == FieldContext.ITEM_ID

    def test_multiline_cursor_on_id_line(self, editor):
        editor.setPlainText("Path: Fabricator;\n    ItemID: Tit")
        _place_cursor_at(editor, 1, 15)  # inside "Tit"
        assert editor.detect_field_context() == FieldContext.ITEM_ID

    def test_multiline_cursor_on_path_line(self, editor):
        editor.setPlainText("ItemID: Titanium;\n    Path: Fabr")
        _place_cursor_at(editor, 1, 14)  # inside "Fabr"
        assert editor.detect_field_context() == FieldContext.PATH


class TestPathPrefix:
    def test_simple_path(self, editor):
        editor.setPlainText("    Path: Fabr")
        _place_cursor_at_end(editor)
        assert editor.path_prefix() == "Fabr"

    def test_path_with_slashes(self, editor):
        editor.setPlainText("    Path: Fabricator/Resources/Basi")
        _place_cursor_at_end(editor)
        assert editor.path_prefix() == "Fabricator/Resources/Basi"

    def test_no_space_after_colon(self, editor):
        editor.setPlainText("    Path:Fabricator/Surv")
        _place_cursor_at_end(editor)
        assert editor.path_prefix() == "Fabricator/Surv"

    def test_empty_after_colon(self, editor):
        editor.setPlainText("    Path: ")
        _place_cursor_at_end(editor)
        assert editor.path_prefix() == ""

    def test_no_colon_on_line(self, editor):
        editor.setPlainText("    some text")
        _place_cursor_at_end(editor)
        assert editor.path_prefix() == ""

    def test_compact_inline_extracts_last_value(self, editor):
        """In compact inline, extract text after the LAST colon."""
        editor.setPlainText("TabID:Foods;ParentTabPath:CF3mod/Ta")
        _place_cursor_at_end(editor)
        assert editor.path_prefix() == "CF3mod/Ta"


class TestSetPathCompletions:
    def test_set_path_completions_stores_model(self, editor):
        editor.set_path_completions(["Fabricator/Resources", "Workbench"])
        assert editor._path_model is not None

    def test_path_model_is_none_by_default(self, editor):
        assert editor._path_model is None


class TestContextAwareInsertion:
    def test_path_insertion_replaces_from_colon(self, editor):
        """Path completion replaces the entire text after the colon."""
        completer = _make_completer(["Fabricator/Resources/BasicMaterials"])
        editor.set_completer(completer)

        editor.setPlainText("    Path: Fabr")
        _place_cursor_at_end(editor)
        editor._field_context = FieldContext.PATH
        editor._insert_completion("Fabricator/Resources/BasicMaterials")

        assert editor.toPlainText() == "    Path: Fabricator/Resources/BasicMaterials"

    def test_path_insertion_no_space_after_colon(self, editor):
        completer = _make_completer(["Fabricator"])
        editor.set_completer(completer)

        editor.setPlainText("    Path:Fab")
        _place_cursor_at_end(editor)
        editor._field_context = FieldContext.PATH
        editor._insert_completion("Fabricator")

        assert editor.toPlainText() == "    Path:Fabricator"

    def test_item_id_insertion_still_word_based(self, editor):
        """Non-path context uses standard word-under-cursor replacement."""
        completer = _make_completer(["Titanium"])
        editor.set_completer(completer)

        editor.setPlainText("    ItemID: Tit")
        _place_cursor_at_end(editor)
        editor._field_context = FieldContext.ITEM_ID
        editor._insert_completion("Titanium")

        assert editor.toPlainText() == "    ItemID: Titanium"

    def test_path_insertion_compact_inline(self, editor):
        """In compact inline, only replaces text after the last colon."""
        completer = _make_completer(["CF3mod/Foods"])
        editor.set_completer(completer)

        editor.setPlainText("TabID:Foods;ParentTabPath:CF3")
        _place_cursor_at_end(editor)
        editor._field_context = FieldContext.PATH
        editor._insert_completion("CF3mod/Foods")

        assert editor.toPlainText() == "TabID:Foods;ParentTabPath:CF3mod/Foods"
