"""Shared floating-editor pool for painted-field nodes.

Four QWidget editors are constructed once per ``FloatingEditorHost``
and reused across every field summon. The host parks the right editor
over a target rect (in view coordinates), focuses it, and emits
``committed``/``cancelled`` when the user finishes.

The pool is deliberately tiny: four widgets total per window, regardless
of node count. The HWND/widget cost is amortized.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRect, Qt, Signal
from PySide6.QtGui import QDoubleValidator, QFocusEvent, QIntValidator, QKeyEvent
from PySide6.QtWidgets import QComboBox, QCompleter, QGraphicsView, QLineEdit, QWidget

from craftgraph.pin_registry import PinType


class _CancellingLineEdit(QLineEdit):
    """QLineEdit that emits an ``escape_pressed`` signal on Esc."""

    escape_pressed = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            return
        super().keyPressEvent(event)


class _CancellingComboBox(QComboBox):
    """QComboBox that commits on activation and cancels on Esc."""

    activated_value = Signal(str)
    escape_pressed = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            return
        super().keyPressEvent(event)


class FloatingEditorHost(QObject):
    """Pool of four editor widgets that fly to a clicked field."""

    committed = Signal(str, str)
    cancelled = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._parent_widget = QWidget()  # hidden parent, holds the editors
        self._parent_widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)

        self._string_editor = _CancellingLineEdit(self._parent_widget)
        self._string_editor.hide()
        self._string_editor.returnPressed.connect(self._commit)
        self._string_editor.escape_pressed.connect(self._cancel)
        self._string_editor.installEventFilter(self)

        self._int_editor = _CancellingLineEdit(self._parent_widget)
        self._int_editor.setValidator(QIntValidator(self._int_editor))
        self._int_editor.hide()
        self._int_editor.returnPressed.connect(self._commit)
        self._int_editor.escape_pressed.connect(self._cancel)
        self._int_editor.installEventFilter(self)

        self._combo_editor = _CancellingComboBox(self._parent_widget)
        self._combo_editor.hide()
        self._combo_editor.activated.connect(self._on_combo_activated)
        self._combo_editor.escape_pressed.connect(self._cancel)
        self._combo_editor.installEventFilter(self)

        self._float_editor = _CancellingLineEdit(self._parent_widget)
        self._float_editor.setValidator(QDoubleValidator(self._float_editor))
        self._float_editor.hide()
        self._float_editor.returnPressed.connect(self._commit)
        self._float_editor.escape_pressed.connect(self._cancel)
        self._float_editor.installEventFilter(self)

        self._view: QGraphicsView | None = None
        self._active_field_name: str | None = None
        self._active_editor: _CancellingLineEdit | _CancellingComboBox | None = None

    def attach(self, view: QGraphicsView) -> None:
        """Re-parent each editor to ``view.viewport()`` so they float over it."""
        self._view = view
        viewport = view.viewport()
        for editor in (
            self._string_editor,
            self._int_editor,
            self._combo_editor,
            self._float_editor,
        ):
            editor.setParent(viewport)
            editor.hide()

    def summon(
        self,
        field_name: str,
        field_type: PinType,
        view_rect: QRect,
        current_value: str,
        *,
        completer_words: list[str] | None = None,
        enum_items: list[str] | None = None,
    ) -> None:
        """Show the right editor over ``view_rect`` (in view-viewport coords)."""
        if self._active_editor is not None:
            self._commit()  # commit any pending edit before re-summoning

        editor: _CancellingLineEdit | _CancellingComboBox | None
        editor = self._editor_for_type(field_type)
        if editor is None:
            return

        if isinstance(editor, _CancellingComboBox):
            editor.clear()
            for item in enum_items or []:
                editor.addItem(item)
            idx = editor.findText(current_value)
            if idx >= 0:
                editor.setCurrentIndex(idx)
        else:
            editor.setText(current_value)
            editor.selectAll()
            if completer_words is not None:
                completer = QCompleter(completer_words, editor)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                editor.setCompleter(completer)
            else:
                # setCompleter(None) detaches any existing completer (valid Qt API).
                editor.setCompleter(None)  # type: ignore[arg-type]

        editor.setGeometry(view_rect)
        editor.show()
        editor.raise_()
        editor.setFocus(Qt.FocusReason.MouseFocusReason)

        self._active_field_name = field_name
        self._active_editor = editor

    def _editor_for_type(
        self, field_type: PinType
    ) -> _CancellingLineEdit | _CancellingComboBox | None:
        if field_type in (PinType.STRING, PinType.CSV):
            return self._string_editor
        if field_type is PinType.INT:
            return self._int_editor
        if field_type in (PinType.ENUM, PinType.BOOL):
            return self._combo_editor
        if field_type is PinType.FLOAT:
            return self._float_editor
        return None

    def _commit(self) -> None:
        if self._active_editor is None or self._active_field_name is None:
            return
        editor = self._active_editor
        value = editor.currentText() if isinstance(editor, _CancellingComboBox) else editor.text()
        field_name = self._active_field_name
        self._hide_active()
        self.committed.emit(field_name, value)

    def _cancel(self) -> None:
        if self._active_editor is None or self._active_field_name is None:
            return
        field_name = self._active_field_name
        self._hide_active()
        self.cancelled.emit(field_name)

    def _on_combo_activated(self, _idx: int) -> None:
        self._commit()

    def _hide_active(self) -> None:
        # Clear the active references BEFORE hiding so the synchronous
        # focus-out event doesn't re-enter _commit/_cancel.
        editor = self._active_editor
        self._active_editor = None
        self._active_field_name = None
        if editor is not None:
            editor.hide()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        # Focus-loss commits the pending edit (matches QLineEdit defaults).
        if (
            event.type() == event.Type.FocusOut
            and obj is self._active_editor
            and isinstance(event, QFocusEvent)
            and event.reason()
            not in (
                Qt.FocusReason.PopupFocusReason,
                Qt.FocusReason.ActiveWindowFocusReason,
            )
        ):
            self._commit()
        return super().eventFilter(obj, event)

    def close(self) -> None:
        """Tear down the editor pool. Call once per window lifetime."""
        for editor in (
            self._string_editor,
            self._int_editor,
            self._combo_editor,
            self._float_editor,
        ):
            editor.removeEventFilter(self)
            editor.hide()
            editor.setParent(None)
            editor.deleteLater()
        self._parent_widget.setParent(None)
        self._parent_widget.deleteLater()
        self._view = None
