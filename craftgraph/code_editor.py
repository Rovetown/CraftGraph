"""Code editor widget with line number sidebar and autocomplete.

Provides a QPlainTextEdit subclass with an integrated line number gutter
and optional QCompleter-based autocomplete. This is the standard Qt
"Code Editor Example" pattern adapted for PySide6.

The editor is UI-framework-agnostic regarding syntax -- attach any
QSyntaxHighlighter to its document externally.
"""

from __future__ import annotations

import re
from enum import Enum

from PySide6.QtCore import QAbstractItemModel, QRect, QSize, QStringListModel, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QResizeEvent,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import QCompleter, QPlainTextEdit, QTextEdit, QWidget

# Bracket pairs for auto-close
_BRACKET_PAIRS: dict[str, str] = {
    "(": ")",
    "[": "]",
    "{": "}",
    '"': '"',
}
_CLOSING_BRACKETS: frozenset[str] = frozenset(_BRACKET_PAIRS.values())


class FieldContext(Enum):
    """The type of EasyMarkup field the cursor is currently in."""

    ITEM_ID = "item_id"
    PATH = "path"


_PATH_FIELDS: frozenset[str] = frozenset(
    {
        "path",
        "oldpath",
        "newpath",
        "parenttabpath",
    }
)


# -- Line number area ----------------------------------------------------------


class LineNumberArea(QWidget):
    """Thin sidebar widget that displays line numbers for a CodeEditor.

    This widget does no painting of its own -- it delegates entirely to
    ``CodeEditor.line_number_area_paint_event``.
    """

    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event: QPaintEvent) -> None:
        self._editor.line_number_area_paint_event(event)


# -- Code editor ---------------------------------------------------------------


class CodeEditor(QPlainTextEdit):
    """QPlainTextEdit with an integrated line number gutter and autocomplete.

    Usage::

        editor = CodeEditor()
        highlighter = EasyMarkupHighlighter(editor.document())

        # Optional autocomplete
        completer = QCompleter(["Titanium", "Gold", "Quartz"])
        editor.set_completer(completer)
    """

    MIN_PREFIX_LENGTH = 2

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._line_number_area = LineNumberArea(self)
        self._completer: QCompleter | None = None
        self._item_model: QAbstractItemModel | None = None
        self._path_model: QStringListModel | None = None
        self._field_context: FieldContext = FieldContext.ITEM_ID
        self._min_prefix_length: int = self.MIN_PREFIX_LENGTH

        # Settings state
        self._show_line_numbers = True
        self._highlight_current_line = True
        self._auto_indent = True
        self._auto_close_brackets = True

        # Current-line highlight color
        self._current_line_color = QColor("#2A2A3A")

        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line_slot)
        self._update_line_number_area_width()

        # Set default monospace font
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

    @property
    def line_number_area(self) -> LineNumberArea:
        """The line number gutter widget."""
        return self._line_number_area

    # -- Settings application --------------------------------------------------

    def set_editor_font(self, family: str, size: int) -> None:
        """Apply a font family and point size to the editor."""
        font = QFont(family, size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self._update_line_number_area_width()

    def set_show_line_numbers(self, show: bool) -> None:
        """Toggle line number gutter visibility."""
        self._show_line_numbers = show
        self._line_number_area.setVisible(show)
        self._update_line_number_area_width()

    def set_highlight_current_line(self, enabled: bool) -> None:
        """Toggle current-line background highlight."""
        self._highlight_current_line = enabled
        self._highlight_current_line_slot()

    def set_word_wrap(self, enabled: bool) -> None:
        """Toggle word wrapping."""
        if enabled:
            self.setWordWrapMode(self.document().defaultTextOption().wrapMode() or 1)
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        else:
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def set_tab_width(self, spaces: int) -> None:
        """Set the tab stop width in space equivalents."""
        char_width = self.fontMetrics().horizontalAdvance(" ")
        self.setTabStopDistance(char_width * spaces)

    def set_auto_indent(self, enabled: bool) -> None:
        """Toggle automatic indentation on Enter."""
        self._auto_indent = enabled

    def set_auto_close_brackets(self, enabled: bool) -> None:
        """Toggle automatic bracket/paren/quote closing."""
        self._auto_close_brackets = enabled

    def set_min_prefix_length(self, length: int) -> None:
        """Set minimum characters before autocomplete popup appears."""
        self._min_prefix_length = max(1, min(length, 5))

    def set_case_insensitive(self, enabled: bool) -> None:
        """Toggle case-insensitive matching on the attached completer."""
        if self._completer is not None:
            sensitivity = (
                Qt.CaseSensitivity.CaseInsensitive if enabled else Qt.CaseSensitivity.CaseSensitive
            )
            self._completer.setCaseSensitivity(sensitivity)

    def set_current_line_color(self, color: QColor) -> None:
        """Set the background color for the current-line highlight."""
        self._current_line_color = color
        self._highlight_current_line_slot()

    def strip_trailing_whitespace(self) -> None:
        """Remove trailing whitespace from every line in the document."""
        cursor = self.textCursor()
        cursor.beginEditBlock()
        block = self.document().begin()
        while block.isValid():
            text = block.text()
            stripped = text.rstrip()
            if len(stripped) < len(text):
                cursor.setPosition(block.position() + len(stripped))
                cursor.setPosition(
                    block.position() + len(text),
                    QTextCursor.MoveMode.KeepAnchor,
                )
                cursor.removeSelectedText()
            block = block.next()
        cursor.endEditBlock()

    def show_parse_error(self, line: int, message: str) -> None:
        """Highlight a parse error on the given line (0-based) with a tooltip."""
        self._parse_error_selections = []
        block = self.document().findBlockByNumber(line)
        if not block.isValid():
            return
        selection = QTextEdit.ExtraSelection()
        fmt = QTextCharFormat()
        fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
        fmt.setUnderlineColor(QColor("#FF4444"))
        fmt.setToolTip(message)
        fmt.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
        selection.format = fmt
        cursor = QTextCursor(block)
        cursor.movePosition(
            QTextCursor.MoveOperation.EndOfBlock,
            QTextCursor.MoveMode.KeepAnchor,
        )
        selection.cursor = cursor
        self._parse_error_selections = [selection]
        self._refresh_extra_selections()

    def clear_parse_errors(self) -> None:
        """Remove all parse error highlights."""
        self._parse_error_selections = []
        self._refresh_extra_selections()

    def _refresh_extra_selections(self) -> None:
        """Combine current-line highlight and parse error selections."""
        selections: list[QTextEdit.ExtraSelection] = []
        if self._highlight_current_line:
            sel = QTextEdit.ExtraSelection()
            fmt = QTextCharFormat()
            fmt.setBackground(self._current_line_color)
            fmt.setProperty(QTextCharFormat.Property.FullWidthSelection, True)
            sel.format = fmt
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            selections.append(sel)
        selections.extend(getattr(self, "_parse_error_selections", []))
        self.setExtraSelections(selections)

    def _highlight_current_line_slot(self) -> None:
        """Highlight the line under the cursor."""
        self._refresh_extra_selections()

    # -- Autocomplete ----------------------------------------------------------

    def completer(self) -> QCompleter | None:
        """Return the current QCompleter, or None."""
        return self._completer

    def set_completer(self, completer: QCompleter | None) -> None:
        """Attach a QCompleter for word-level autocomplete."""
        if self._completer is not None:
            self._completer.activated.disconnect()
        self._completer = completer
        if completer is None:
            return
        completer.setWidget(self)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.activated.connect(self._insert_completion)
        self._item_model = completer.model()

    def set_path_completions(self, paths: list[str]) -> None:
        """Set the word list for Path field completion."""
        self._path_model = QStringListModel(
            sorted(paths, key=str.lower),
            self,
        )

    def detect_field_context(self) -> FieldContext:
        """Detect whether the cursor is in a path field or an item ID field.

        Scans the current line backwards from the cursor to find the last
        field key (e.g. ``Path:``, ``ItemID:``).  If the last field key is
        one of the path fields, returns ``PATH``; otherwise ``ITEM_ID``.
        """
        cursor = self.textCursor()
        line_text = cursor.block().text()
        col = cursor.positionInBlock()
        text_before = line_text[:col]
        matches = re.findall(r"\b(\w+)\s*:", text_before)
        if matches:
            field_name = matches[-1].lower()
            if field_name in _PATH_FIELDS:
                return FieldContext.PATH
        return FieldContext.ITEM_ID

    def path_prefix(self) -> str:
        """Extract the path text between the last colon and the cursor.

        Used for path-field completion where ``/`` should not be treated
        as a word boundary.
        """
        cursor = self.textCursor()
        line_text = cursor.block().text()
        col = cursor.positionInBlock()
        text_before = line_text[:col]
        colon_idx = text_before.rfind(":")
        if colon_idx < 0:
            return ""
        return text_before[colon_idx + 1 :].strip()

    def text_under_cursor(self) -> str:
        """Return the word fragment to the left of the cursor."""
        tc = self.textCursor()
        tc.select(QTextCursor.SelectionType.WordUnderCursor)
        return tc.selectedText()

    def _insert_completion(self, completion: str) -> None:
        """Replace the current prefix with the completed text.

        In PATH context, replaces the entire text between the last colon
        (plus any leading whitespace) and the cursor.  In ITEM_ID context,
        uses the standard word-under-cursor replacement.
        """
        if self._completer is None:
            return
        tc = self.textCursor()
        if self._field_context == FieldContext.PATH:
            line_text = tc.block().text()
            col = tc.positionInBlock()
            text_before = line_text[:col]
            colon_idx = text_before.rfind(":")
            if colon_idx >= 0:
                after_colon = text_before[colon_idx + 1 :]
                leading_space = len(after_colon) - len(after_colon.lstrip())
                start_in_block = colon_idx + 1 + leading_space
                block_start = tc.block().position()
                tc.setPosition(block_start + start_in_block)
                tc.setPosition(
                    block_start + col,
                    QTextCursor.MoveMode.KeepAnchor,
                )
                tc.insertText(completion)
                self.setTextCursor(tc)
                return
        # Default: word-under-cursor replacement
        tc.select(QTextCursor.SelectionType.WordUnderCursor)
        tc.insertText(completion)
        self.setTextCursor(tc)

    # -- Qt overrides (autocomplete) -------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key events for autocomplete, auto-indent, and bracket closing.

        Detects the field context (path vs item ID) on every keystroke
        and swaps the completer's model accordingly.
        """
        c = self._completer
        popup = c.popup() if c is not None else None
        if (
            popup is not None
            and popup.isVisible()
            and event.key()
            in (
                Qt.Key.Key_Enter,
                Qt.Key.Key_Return,
                Qt.Key.Key_Escape,
                Qt.Key.Key_Tab,
                Qt.Key.Key_Backtab,
            )
        ):
            event.ignore()
            return

        # Auto-indent: on Enter, copy leading whitespace from current line
        if (
            self._auto_indent
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            cursor = self.textCursor()
            line_text = cursor.block().text()
            indent = ""
            for ch in line_text:
                if ch in (" ", "\t"):
                    indent += ch
                else:
                    break
            # If line ends with '(' add one extra indent level
            stripped = line_text.rstrip()
            if stripped.endswith("("):
                indent += "    "
            super().keyPressEvent(event)
            self.textCursor().insertText(indent)
            return

        # Auto-close brackets: insert matching closer after opener
        text = event.text()
        if self._auto_close_brackets and text in _BRACKET_PAIRS:
            closer = _BRACKET_PAIRS[text]
            # For quotes, skip auto-close if already inside a quoted region
            if text == '"':
                cursor = self.textCursor()
                line_text = cursor.block().text()
                col = cursor.positionInBlock()
                before = line_text[:col]
                if before.count('"') % 2 == 1:
                    super().keyPressEvent(event)
                    self._run_autocomplete()
                    return
            super().keyPressEvent(event)
            self.textCursor().insertText(closer)
            # Move cursor back between the pair
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor)
            self.setTextCursor(cursor)
            self._run_autocomplete()
            return

        # Skip-over closing bracket if the next char matches
        if self._auto_close_brackets and text in _CLOSING_BRACKETS:
            cursor = self.textCursor()
            line_text = cursor.block().text()
            col = cursor.positionInBlock()
            if col < len(line_text) and line_text[col] == text:
                cursor.movePosition(
                    QTextCursor.MoveOperation.Right,
                    QTextCursor.MoveMode.MoveAnchor,
                )
                self.setTextCursor(cursor)
                event.accept()
                self._run_autocomplete()
                return

        super().keyPressEvent(event)
        self._run_autocomplete()

    def _run_autocomplete(self) -> None:
        """Update the autocomplete popup based on current cursor context."""
        c = self._completer
        if c is None:
            return

        context = self.detect_field_context()
        self._field_context = context

        if context == FieldContext.PATH and self._path_model is not None:
            c.setModel(self._path_model)
            prefix = self.path_prefix()
        else:
            if self._item_model is not None:
                c.setModel(self._item_model)
            prefix = self.text_under_cursor()

        popup = c.popup()
        if popup is None:
            return

        if len(prefix) < self._min_prefix_length:
            popup.hide()
            return

        if prefix != c.completionPrefix():
            c.setCompletionPrefix(prefix)
            popup.setCurrentIndex(c.completionModel().index(0, 0))

        cr = self.cursorRect()
        cr.setWidth(popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width())
        c.complete(cr)

    # -- Line number area ------------------------------------------------------

    def line_number_area_width(self) -> int:
        """Calculate the pixel width needed for the line number gutter."""
        if not self._show_line_numbers:
            return 0
        digits = max(1, len(str(self.blockCount())))
        char_width = self.fontMetrics().horizontalAdvance("9")
        return 6 + char_width * digits

    def line_number_area_paint_event(self, event: QPaintEvent) -> None:
        """Paint line numbers -- called by ``LineNumberArea.paintEvent``."""
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor("#F0F0F0"))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        offset = self.contentOffset()
        top = round(self.blockBoundingGeometry(block).translated(offset).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor("#808080"))
                painter.drawText(
                    0,
                    top,
                    self._line_number_area.width() - 3,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

        painter.end()

    # -- Qt overrides ----------------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            cr.left(),
            cr.top(),
            self.line_number_area_width(),
            cr.height(),
        )

    # -- Private ---------------------------------------------------------------

    def _update_line_number_area_width(self) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(
                0,
                rect.y(),
                self._line_number_area.width(),
                rect.height(),
            )
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width()
