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
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPaintEvent, QResizeEvent, QTextCursor
from PySide6.QtWidgets import QCompleter, QPlainTextEdit, QWidget


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
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self._update_line_number_area_width()

    @property
    def line_number_area(self) -> LineNumberArea:
        """The line number gutter widget."""
        return self._line_number_area

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
        """Handle key events for context-aware autocomplete.

        Detects the field context (path vs item ID) on every keystroke
        and swaps the completer's model accordingly.
        """
        c = self._completer
        if (
            c is not None
            and c.popup().isVisible()
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

        super().keyPressEvent(event)

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

        if len(prefix) < self.MIN_PREFIX_LENGTH:
            c.popup().hide()
            return

        if prefix != c.completionPrefix():
            c.setCompletionPrefix(prefix)
            c.popup().setCurrentIndex(c.completionModel().index(0, 0))

        cr = self.cursorRect()
        cr.setWidth(
            c.popup().sizeHintForColumn(0) + c.popup().verticalScrollBar().sizeHint().width()
        )
        c.complete(cr)

    # -- Line number area ------------------------------------------------------

    def line_number_area_width(self) -> int:
        """Calculate the pixel width needed for the line number gutter."""
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
