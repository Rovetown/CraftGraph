"""Tests for the EasyMarkup syntax highlighter (Step M5).

These tests require PySide6.  They are skipped automatically when
PySide6 is not installed.

Run:  uv run --extra qt pytest tests/test_highlighter.py -v
"""

from __future__ import annotations

import sys

import pytest

pytest.importorskip(
    "PySide6",
    reason="PySide6 not installed (install with: uv sync --extra qt)",
)

from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCharFormat

from craftgraph.highlighter import (
    BLOCK_TYPES,
    FIELD_KEYS,
    EasyMarkupHighlighter,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication (one per test run)."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


@pytest.fixture
def doc_and_hl(qapp):
    """Fresh QTextDocument with an attached EasyMarkupHighlighter."""
    doc = QtGui.QTextDocument()
    hl = EasyMarkupHighlighter(doc)
    return doc, hl


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _highlight(doc: QtGui.QTextDocument, hl: EasyMarkupHighlighter, text: str) -> None:
    """Set text on the document and force synchronous rehighlighting.

    Qt schedules rehighlighting asynchronously via the event loop after
    ``setPlainText``.  Calling ``rehighlight()`` forces it to run
    synchronously so that ``layout().formats()`` returns results
    immediately in tests.
    """
    doc.setPlainText(text)
    hl.rehighlight()


def _format_ranges(doc: QtGui.QTextDocument, block_index: int = 0):
    """Extract format ranges from a text block after highlighting.

    Returns a list of ``(start, length, fg_hex_or_none, is_bold, is_italic)``
    tuples.  ``fg_hex_or_none`` is ``None`` when no foreground colour was
    explicitly set (e.g. delimiter-only bold).
    """
    block = doc.firstBlock()
    for _ in range(block_index):
        block = block.next()

    result = []
    for r in block.layout().formats():
        fg_brush = r.format.foreground()
        has_fg = fg_brush.style() != Qt.BrushStyle.NoBrush
        fg = fg_brush.color().name() if has_fg else None
        bold = r.format.fontWeight() >= QFont.Weight.Bold
        italic = r.format.fontItalic()
        result.append((r.start, r.length, fg, bold, italic))
    return result


# ---------------------------------------------------------------------------
# Tests: keyword sets
# ---------------------------------------------------------------------------


class TestKeywordSets:
    """Verify the keyword sets cover all CC3 block types and fields."""

    def test_all_ten_block_types_present(self):
        assert len(BLOCK_TYPES) == 10

    def test_block_types_are_strings(self):
        for bt in BLOCK_TYPES:
            assert isinstance(bt, str)

    def test_field_keys_non_empty(self):
        assert len(FIELD_KEYS) > 20

    def test_no_overlap_between_block_types_and_field_keys(self):
        overlap = BLOCK_TYPES & FIELD_KEYS
        assert not overlap, f"Unexpected overlap: {overlap}"


# ---------------------------------------------------------------------------
# Tests: block type highlighting
# ---------------------------------------------------------------------------


class TestBlockTypeHighlighting:
    """Block type keywords should be dark magenta and bold."""

    BLOCK_FG = "#8b008b"

    def test_modified_recipes(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "ModifiedRecipes:")
        ranges = _format_ranges(doc)
        block_ranges = [r for r in ranges if r[2] == self.BLOCK_FG]
        assert len(block_ranges) == 1
        start, length, _, bold, _ = block_ranges[0]
        assert start == 0
        assert length == len("ModifiedRecipes:")
        assert bold is True

    def test_case_insensitive(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "modifiedrecipes:")
        ranges = _format_ranges(doc)
        assert any(fg == self.BLOCK_FG for _, _, fg, _, _ in ranges)

    def test_with_leading_whitespace(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "    AddedRecipes:")
        ranges = _format_ranges(doc)
        block_ranges = [(s, ln) for s, ln, fg, _, _ in ranges if fg == self.BLOCK_FG]
        assert len(block_ranges) == 1
        assert block_ranges[0][0] == 4

    def test_space_before_colon(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "AliasRecipes :")
        ranges = _format_ranges(doc)
        block_ranges = [(s, ln) for s, ln, fg, _, _ in ranges if fg == self.BLOCK_FG]
        assert len(block_ranges) == 1
        assert block_ranges[0][1] == len("AliasRecipes :")

    @pytest.mark.parametrize("block_type", sorted(BLOCK_TYPES))
    def test_all_block_types_match(self, doc_and_hl, block_type):
        doc, hl = doc_and_hl
        _highlight(doc, hl, f"{block_type}:")
        ranges = _format_ranges(doc)
        block_ranges = [r for r in ranges if r[2] == self.BLOCK_FG]
        assert len(block_ranges) == 1


# ---------------------------------------------------------------------------
# Tests: field key highlighting
# ---------------------------------------------------------------------------


class TestFieldKeyHighlighting:
    """Field keys should be teal."""

    FIELD_FG = "#007080"

    def test_item_id(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "    ItemID: Titanium;")
        ranges = _format_ranges(doc)
        field_ranges = [(s, ln) for s, ln, fg, _, _ in ranges if fg == self.FIELD_FG]
        assert len(field_ranges) == 1
        assert field_ranges[0][0] == 4
        assert field_ranges[0][1] == len("ItemID:")

    def test_case_insensitive(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "    itemid: Titanium;")
        ranges = _format_ranges(doc)
        assert any(fg == self.FIELD_FG for _, _, fg, _, _ in ranges)

    def test_ingredients(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "    Ingredients:")
        ranges = _format_ranges(doc)
        field_ranges = [r for r in ranges if r[2] == self.FIELD_FG]
        assert len(field_ranges) == 1

    def test_field_not_bold(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "    Required: 3;")
        ranges = _format_ranges(doc)
        field_ranges = [r for r in ranges if r[2] == self.FIELD_FG]
        assert len(field_ranges) == 1
        assert field_ranges[0][3] is False  # not bold


# ---------------------------------------------------------------------------
# Tests: delimiter highlighting
# ---------------------------------------------------------------------------


class TestDelimiterHighlighting:
    """Delimiters should be bold with no explicit foreground colour."""

    def test_parenthesis(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "(")
        ranges = _format_ranges(doc)
        assert len(ranges) >= 1
        _, _, fg, bold, _ = ranges[0]
        assert fg is None  # no foreground set
        assert bold is True

    def test_comma_and_semicolon(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, ",;")
        ranges = _format_ranges(doc)
        bold_ranges = [r for r in ranges if r[3] is True and r[2] is None]
        # Qt merges adjacent identical formats, so ",;" may be one range
        total_bold_chars = sum(ln for _, ln, _, _, _ in bold_ranges)
        assert total_bold_chars == 2

    def test_close_parenthesis(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, ")")
        ranges = _format_ranges(doc)
        assert len(ranges) >= 1
        assert ranges[0][3] is True  # bold


# ---------------------------------------------------------------------------
# Tests: string highlighting
# ---------------------------------------------------------------------------


class TestStringHighlighting:
    """Quoted strings should be green and italic."""

    STRING_FG = "#228b22"

    def test_simple_string(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, 'DisplayName: "My Item";')
        ranges = _format_ranges(doc)
        string_ranges = [(s, ln) for s, ln, fg, _, _ in ranges if fg == self.STRING_FG]
        assert len(string_ranges) == 1
        _, matched_len = string_ranges[0]
        assert matched_len == len('"My Item"')

    def test_string_italic(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, '"hello"')
        ranges = _format_ranges(doc)
        string_ranges = [r for r in ranges if r[2] == self.STRING_FG]
        assert len(string_ranges) == 1
        assert string_ranges[0][4] is True  # italic

    def test_string_with_escaped_quote(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, r'Tooltip: "Contains \"quotes\"";')
        ranges = _format_ranges(doc)
        string_ranges = [r for r in ranges if r[2] == self.STRING_FG]
        assert len(string_ranges) == 1

    def test_string_overrides_keyword_inside(self, doc_and_hl):
        """A keyword inside a string should not keep keyword formatting."""
        doc, hl = doc_and_hl
        _highlight(doc, hl, 'DisplayName: "ItemID: inside string";')
        ranges = _format_ranges(doc)
        # Locate the string span
        string_ranges = [(s, ln) for s, ln, fg, _, _ in ranges if fg == self.STRING_FG]
        assert len(string_ranges) == 1
        s_start, _s_len = string_ranges[0]
        # No teal (field key) format should overlap with the string
        for start, length, fg, _, _ in ranges:
            if fg == "#007080":
                assert start + length <= s_start


# ---------------------------------------------------------------------------
# Tests: comment highlighting
# ---------------------------------------------------------------------------


class TestCommentHighlighting:
    """Comments should be gray and italic."""

    COMMENT_FG = "#808080"

    def test_full_line_comment(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "# This is a comment")
        ranges = _format_ranges(doc)
        comment_ranges = [(s, ln) for s, ln, fg, _, _ in ranges if fg == self.COMMENT_FG]
        assert len(comment_ranges) == 1
        assert comment_ranges[0][0] == 0
        assert comment_ranges[0][1] == len("# This is a comment")

    def test_comment_italic(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "# note")
        ranges = _format_ranges(doc)
        comment_ranges = [r for r in ranges if r[2] == self.COMMENT_FG]
        assert comment_ranges[0][4] is True  # italic

    def test_inline_comment(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "ItemID: Titanium; # comment")
        ranges = _format_ranges(doc)
        comment_ranges = [(s, ln) for s, ln, fg, _, _ in ranges if fg == self.COMMENT_FG]
        assert len(comment_ranges) == 1

    def test_comment_overrides_keyword(self, doc_and_hl):
        """Keywords after # should get comment formatting, not keyword."""
        doc, hl = doc_and_hl
        _highlight(doc, hl, "# ModifiedRecipes:")
        ranges = _format_ranges(doc)
        comment_ranges = [(s, ln) for s, ln, fg, _, _ in ranges if fg == self.COMMENT_FG]
        assert len(comment_ranges) == 1
        assert comment_ranges[0][0] == 0
        assert comment_ranges[0][1] == len("# ModifiedRecipes:")


# ---------------------------------------------------------------------------
# Tests: lifecycle and edge cases
# ---------------------------------------------------------------------------


class TestHighlighterLifecycle:
    """Basic construction and attachment tests."""

    def test_attach_to_document(self, qapp):
        doc = QtGui.QTextDocument()
        hl = EasyMarkupHighlighter(doc)
        assert hl.document() is doc

    def test_empty_text(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "")
        ranges = _format_ranges(doc)
        assert ranges == []

    def test_plain_text_no_highlights(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "Hello world")
        ranges = _format_ranges(doc)
        assert ranges == []

    def test_real_recipe_block(self, doc_and_hl):
        """A realistic multi-line recipe should highlight without errors."""
        doc, hl = doc_and_hl
        text = (
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: Titanium;\n"
            "    AmountCrafted: 2;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: Quartz;\n"
            "        Required: 3;\n"
            "    );\n"
            ")"
        )
        _highlight(doc, hl, text)
        # Block type on line 0
        line0 = _format_ranges(doc, block_index=0)
        assert any(fg == "#8b008b" for _, _, fg, _, _ in line0)
        # Field key on line 2 (ItemID:)
        line2 = _format_ranges(doc, block_index=2)
        assert any(fg == "#007080" for _, _, fg, _, _ in line2)


# ---------------------------------------------------------------------------
# Helper: error (wavy underline) range extractor
# ---------------------------------------------------------------------------


def _error_ranges(doc: QtGui.QTextDocument, block_index: int = 0):
    """Extract error (wavy underline) ranges from a text block.

    Returns a list of ``(start, length)`` tuples for spans that have
    ``WaveUnderline`` style.
    """
    block = doc.firstBlock()
    for _ in range(block_index):
        block = block.next()

    result = []
    for r in block.layout().formats():
        if r.format.underlineStyle() == QTextCharFormat.UnderlineStyle.WaveUnderline:
            result.append((r.start, r.length))
    return result


# ---------------------------------------------------------------------------
# Tests: error format style
# ---------------------------------------------------------------------------


class TestErrorFormatStyle:
    """Verify the error format uses red wavy underline."""

    def test_error_format_is_wave_underline(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "ItemID: Titanium")  # missing semicolon
        errors = _error_ranges(doc)
        assert len(errors) >= 1

    def test_error_format_color_is_red(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "ItemID: Titanium")  # missing semicolon
        block = doc.firstBlock()
        for r in block.layout().formats():
            if r.format.underlineStyle() == QTextCharFormat.UnderlineStyle.WaveUnderline:
                assert r.format.underlineColor().name() == "#cc0000"
                break
        else:
            pytest.fail("No wavy underline format found")

    def test_error_does_not_override_foreground(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "ItemID: Titanium")  # missing semicolon
        block = doc.firstBlock()
        for r in block.layout().formats():
            if r.format.underlineStyle() == QTextCharFormat.UnderlineStyle.WaveUnderline:
                fg_brush = r.format.foreground()
                assert fg_brush.style() == Qt.BrushStyle.NoBrush
                break


# ---------------------------------------------------------------------------
# Tests: error suppression (comments and strings)
# ---------------------------------------------------------------------------


class TestErrorSuppression:
    """Errors inside comments or strings should not be flagged."""

    def test_missing_semicolon_in_comment_not_flagged(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "# ItemID: Titanium")
        errors = _error_ranges(doc)
        assert errors == []

    def test_value_inside_string_not_flagged(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, 'DisplayName: "My Custom Item";')
        errors = _error_ranges(doc)
        assert errors == []

    def test_inline_comment_after_valid_line_not_flagged(self, doc_and_hl):
        doc, hl = doc_and_hl
        _highlight(doc, hl, "ItemID: Titanium; # a comment")
        errors = _error_ranges(doc)
        assert errors == []
