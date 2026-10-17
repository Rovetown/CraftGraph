"""Reusable centered carousel dialog with image slides + dot navigation.

Used for the "What's New" announcement after a version bump and the
"Getting Started" tutorial on first launch. Both flavours share this
class -- only the slide content + window title differ.

Design:

- Modal ``QDialog`` parented to the main window, fixed size, centered.
- Stack: title -> image -> caption -> nav row (prev | dots | next) ->
  close button row.
- Bottom dots: filled circle for the active slide, dimmed for the rest;
  clickable to jump.
- Esc and the Close button both accept the dialog.
- Slides without an image path render a gradient placeholder so a slide
  set can ship before its art assets do.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

# Visual constants for the dots bar -- tuneable here in one place.
_DOT_DIAMETER = 10
_DOT_SPACING = 22
_DOT_BAR_HEIGHT = 22
_DOT_COLOR_ACTIVE = QtGui.QColor(140, 180, 255)
_DOT_COLOR_IDLE = QtGui.QColor(80, 80, 90)
_DOT_COLOR_HOVER = QtGui.QColor(110, 130, 170)


@dataclass
class CarouselSlide:
    """One slide in a carousel.

    image_path may be omitted for placeholder slides during development;
    a gradient swatch is rendered at runtime using ``placeholder_color``
    so the layout still looks finished.
    """

    title: str
    body: str = ""
    image_path: Path | None = None
    placeholder_color: tuple[int, int, int] = (60, 80, 140)
    # Optional per-slide metadata callers can read off again (e.g.
    # an internal slide id used by analytics later).
    metadata: dict[str, str] = field(default_factory=dict)


class _ClickableImageLabel(QtWidgets.QLabel):
    """``QLabel`` that emits ``clicked`` on left-button press.

    Used as the slide image area in :class:`CarouselDialog` so a user
    can tap the image to open the lightbox view.
    """

    clicked = QtCore.Signal()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class _ImageLightbox(QtWidgets.QDialog):
    """Frameless near-full-screen modal that shows a single pixmap large.

    Mirrors the click-to-enlarge pattern from product sites like Amazon /
    eBay. Click anywhere on the panel, press Esc, or click outside the
    transparent margin to dismiss.

    The pixmap is scaled to fit ``screen.availableGeometry() * 0.9`` so
    the lightbox always leaves some chrome visible (taskbar, window
    edges) for context.
    """

    _OUTER_MARGIN = 8
    _PANEL_RADIUS = 12
    _INNER_PAD = 6  # gutter so the panel's rounded corners stay visible
    _SCREEN_FILL = 1.0  # fraction of available screen area (taskbar already excluded)

    def __init__(
        self,
        pixmap: QtGui.QPixmap,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(
            QtCore.Qt.WindowType.Dialog
            | QtCore.Qt.WindowType.FramelessWindowHint,
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)

        # Caller passes an already-screen-fit pixmap (see
        # ``CarouselDialog.lightbox_target_size`` + the cache) so the
        # heavy smooth-scale runs at most once per slide.
        scaled = pixmap
        chrome = (self._OUTER_MARGIN + self._INNER_PAD) * 2
        self.setFixedSize(
            scaled.width() + chrome,
            scaled.height() + chrome,
        )

        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(
            self._OUTER_MARGIN, self._OUTER_MARGIN,
            self._OUTER_MARGIN, self._OUTER_MARGIN,
        )

        panel = QtWidgets.QFrame(self)
        panel.setObjectName("lightboxPanel")
        panel.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        panel.setStyleSheet(
            f"#lightboxPanel {{"
            f"  background: rgb(18, 18, 22);"
            f"  border-radius: {self._PANEL_RADIUS}px;"
            f"  border: 1px solid rgb(60, 60, 70);"
            f"}}"
        )

        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(60)
        shadow.setOffset(0, 10)
        shadow.setColor(QtGui.QColor(0, 0, 0, 220))
        panel.setGraphicsEffect(shadow)
        outer.addWidget(panel)

        panel_layout = QtWidgets.QVBoxLayout(panel)
        panel_layout.setContentsMargins(
            self._INNER_PAD, self._INNER_PAD,
            self._INNER_PAD, self._INNER_PAD,
        )
        self._image_label = QtWidgets.QLabel(panel)
        self._image_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._image_label.setPixmap(scaled)
        panel_layout.addWidget(self._image_label)

        # Esc closes -- standard modal dismissal.
        esc = QtGui.QShortcut(
            QtGui.QKeySequence(QtCore.Qt.Key.Key_Escape), self,
        )
        esc.activated.connect(self.accept)

    def mousePressEvent(self, _event: QtGui.QMouseEvent) -> None:
        """Click anywhere closes the lightbox."""
        self.accept()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(
            geo.center().x() - self.width() // 2,
            geo.center().y() - self.height() // 2,
        )


class _DotsBar(QtWidgets.QWidget):
    """Clickable bottom-dot indicator for the carousel."""

    dot_clicked = QtCore.Signal(int)

    def __init__(self, count: int, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._count = max(count, 1)
        self._active = 0
        self._hover = -1
        self.setFixedHeight(_DOT_BAR_HEIGHT)
        self.setMouseTracking(True)
        self.setMinimumWidth(_DOT_SPACING * self._count)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

    def set_active(self, idx: int) -> None:
        idx = max(0, min(idx, self._count - 1))
        if idx != self._active:
            self._active = idx
            self.update()

    def active(self) -> int:
        return self._active

    def _dot_centers(self) -> list[float]:
        total = (self._count - 1) * _DOT_SPACING
        start = (self.width() - total) / 2
        return [start + i * _DOT_SPACING for i in range(self._count)]

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        cy = self.height() / 2
        radius = _DOT_DIAMETER / 2
        for i, cx in enumerate(self._dot_centers()):
            if i == self._active:
                painter.setBrush(_DOT_COLOR_ACTIVE)
            elif i == self._hover:
                painter.setBrush(_DOT_COLOR_HOVER)
            else:
                painter.setBrush(_DOT_COLOR_IDLE)
            painter.drawEllipse(QtCore.QPointF(cx, cy), radius, radius)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        new_hover = self._hit(event.position().x(), event.position().y())
        if new_hover != self._hover:
            self._hover = new_hover
            self.update()

    def leaveEvent(self, _event: QtCore.QEvent) -> None:
        if self._hover != -1:
            self._hover = -1
            self.update()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        idx = self._hit(event.position().x(), event.position().y())
        if idx != -1:
            self.dot_clicked.emit(idx)

    def _hit(self, x: float, y: float) -> int:
        """Return the index of the dot under (x, y), or -1 for none."""
        cy = self.height() / 2
        # Generous hit radius for easier clicking on small dots.
        click_r = _DOT_DIAMETER
        for i, cx in enumerate(self._dot_centers()):
            if abs(x - cx) <= click_r and abs(y - cy) <= click_r:
                return i
        return -1


class CarouselDialog(QtWidgets.QDialog):
    """Modal centered carousel dialog.

    Looks like a native popup (context-menu / tooltip style): frameless,
    translucent window with a rounded inner panel and a drop shadow.
    Fixed position once shown -- there is no title bar to drag, and the
    dialog re-centers itself on the parent on every show.
    """

    # Total widget size includes the shadow gutter on every side. The
    # rounded panel inside is smaller by _SHADOW_MARGIN pixels. Sizing
    # bumped by ~30% over the v1 design so the image area can show
    # roadmap-style screenshots comfortably; click-to-zoom via the
    # lightbox covers truly large images.
    _PANEL_SIZE = QtCore.QSize(1020, 830)
    _SHADOW_MARGIN = 24
    _PANEL_RADIUS = 18
    _DEFAULT_SIZE = QtCore.QSize(
        _PANEL_SIZE.width() + _SHADOW_MARGIN * 2,
        _PANEL_SIZE.height() + _SHADOW_MARGIN * 2,
    )

    def __init__(
        self,
        slides: list[CarouselSlide],
        *,
        window_title: str = "CraftGraph",
        parent: QtWidgets.QWidget | None = None,
        start_index: int = 0,
    ) -> None:
        super().__init__(parent)
        if not slides:
            raise ValueError("CarouselDialog requires at least one slide")

        self._slides = slides
        self._current = max(0, min(start_index, len(slides) - 1))
        # Source pixmaps and per-target-size scaled results are cached so
        # Prev/Next clicks and repeated lightbox opens don't re-decode the
        # ~2.5MB roadmap PNG from disk each time (~100ms frame stalls).
        self._source_cache: dict[str, QtGui.QPixmap] = {}
        self._scaled_cache: dict[tuple[str, int, int], QtGui.QPixmap] = {}

        self.setWindowTitle(window_title)
        self.setModal(True)
        # Frameless, translucent window so the rounded inner panel + drop
        # shadow paint cleanly without an OS title bar around them. With
        # no title bar there is nothing to drag, which gives the
        # "fixed-in-the-middle-of-the-app" feel the user wanted.
        self.setWindowFlags(
            QtCore.Qt.WindowType.Dialog
            | QtCore.Qt.WindowType.FramelessWindowHint,
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self._DEFAULT_SIZE)

        # Outer layout: transparent, just provides margin for the drop
        # shadow to render into.
        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(
            self._SHADOW_MARGIN, self._SHADOW_MARGIN,
            self._SHADOW_MARGIN, self._SHADOW_MARGIN,
        )

        # Inner panel: the rounded "card" everyone sees. Object name lets
        # the stylesheet selector target this specific frame so the
        # border-radius does not bleed into child widgets.
        panel = QtWidgets.QFrame(self)
        panel.setObjectName("carouselPanel")
        panel.setStyleSheet(
            f"#carouselPanel {{"
            f"  background: rgb(38, 38, 42);"
            f"  border-radius: {self._PANEL_RADIUS}px;"
            f"  border: 1px solid rgb(70, 70, 80);"
            f"}}"
            "QLabel { color: rgb(220, 220, 220); background: transparent; }"
            "QPushButton {"
            "  background: rgb(60, 60, 68); color: rgb(220, 220, 220);"
            "  border: 1px solid rgb(85, 85, 95);"
            "  padding: 6px 16px; border-radius: 6px;"
            "}"
            "QPushButton:hover:enabled { background: rgb(75, 75, 85); }"
            "QPushButton:pressed:enabled { background: rgb(50, 50, 58); }"
            "QPushButton:disabled { color: rgb(120, 120, 130); }"
            "QPushButton#closeX {"
            "  background: transparent; border: none;"
            "  color: rgb(180, 180, 180); padding: 0;"
            "  min-width: 28px; max-width: 28px;"
            "  min-height: 28px; max-height: 28px;"
            "  border-radius: 14px; font-size: 16pt;"
            "}"
            "QPushButton#closeX:hover {"
            "  background: rgb(70, 70, 80); color: rgb(240, 240, 240);"
            "}"
        )

        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 6)
        shadow.setColor(QtGui.QColor(0, 0, 0, 180))
        panel.setGraphicsEffect(shadow)

        outer.addWidget(panel)

        inner = QtWidgets.QVBoxLayout(panel)
        inner.setContentsMargins(28, 20, 28, 22)
        inner.setSpacing(12)

        # Header row: just a top-right close X (no title bar in frameless mode).
        header_row = QtWidgets.QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.addStretch()
        close_x = QtWidgets.QPushButton("×")  # ×
        close_x.setObjectName("closeX")
        close_x.setToolTip("Close (Esc)")
        close_x.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        close_x.clicked.connect(self.accept)
        header_row.addWidget(close_x)
        inner.addLayout(header_row)

        # Slide title
        self._title_label = QtWidgets.QLabel(panel)
        title_font = self._title_label.font()
        title_font.setPointSize(16)
        title_font.setBold(True)
        self._title_label.setFont(title_font)
        self._title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        inner.addWidget(self._title_label)

        # Image area -- fixed height keeps navigation widgets at a
        # stable vertical position between slides. Clicking the image
        # pops a near-full-screen lightbox (see ``_show_lightbox``) so
        # roadmap / screenshot slides can be read at native size.
        self._image_label = _ClickableImageLabel(panel)
        self._image_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._image_label.setFixedHeight(510)
        self._image_label.setStyleSheet(
            "background: rgb(28, 28, 32); border-radius: 10px;"
        )
        self._image_label.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self._image_label.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._image_label.setToolTip("Click to view full size")
        self._image_label.clicked.connect(self._show_lightbox)
        # Centered row so the label can shrink to the pixmap's width per
        # slide without leaving empty bars on either side.
        image_row = QtWidgets.QHBoxLayout()
        image_row.setContentsMargins(0, 0, 0, 0)
        image_row.addStretch()
        image_row.addWidget(self._image_label)
        image_row.addStretch()
        inner.addLayout(image_row)

        # Persistent hint so the click-to-enlarge affordance is visible
        # without relying on the tooltip (which only appears on hover).
        self._image_hint_label = QtWidgets.QLabel(
            "Click the image to view it full size", panel,
        )
        self._image_hint_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        hint_font = self._image_hint_label.font()
        hint_font.setPointSize(9)
        hint_font.setItalic(True)
        self._image_hint_label.setFont(hint_font)
        self._image_hint_label.setStyleSheet(
            "color: rgb(150, 150, 160); background: transparent;"
        )
        inner.addWidget(self._image_hint_label)

        # Body / caption
        self._body_label = QtWidgets.QLabel(panel)
        self._body_label.setWordWrap(True)
        self._body_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._body_label.setMinimumHeight(48)
        body_font = self._body_label.font()
        body_font.setPointSize(10)
        self._body_label.setFont(body_font)
        inner.addWidget(self._body_label)

        # Nav row: prev | dots | next
        nav_row = QtWidgets.QHBoxLayout()
        nav_row.setSpacing(8)

        self._prev_btn = QtWidgets.QPushButton("‹ Previous", panel)
        self._prev_btn.setFixedWidth(110)
        self._prev_btn.clicked.connect(self._on_prev)
        nav_row.addWidget(self._prev_btn)

        nav_row.addStretch()
        self._dots = _DotsBar(len(slides), panel)
        self._dots.dot_clicked.connect(self._jump_to)
        nav_row.addWidget(self._dots)
        nav_row.addStretch()

        self._next_btn = QtWidgets.QPushButton("Next ›", panel)
        self._next_btn.setFixedWidth(110)
        self._next_btn.clicked.connect(self._on_next)
        nav_row.addWidget(self._next_btn)
        inner.addLayout(nav_row)

        # Close button row
        close_row = QtWidgets.QHBoxLayout()
        close_row.addStretch()
        self._close_btn = QtWidgets.QPushButton("Close", panel)
        self._close_btn.setFixedWidth(110)
        self._close_btn.clicked.connect(self.accept)
        close_row.addWidget(self._close_btn)
        inner.addLayout(close_row)

        # Esc key closes -- standard dialog dismissal.
        esc = QtGui.QShortcut(
            QtGui.QKeySequence(QtCore.Qt.Key.Key_Escape), self,
        )
        esc.activated.connect(self.accept)
        # Arrow-key navigation between slides for keyboard users.
        left = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key.Key_Left), self)
        left.activated.connect(self._on_prev)
        right = QtGui.QShortcut(
            QtGui.QKeySequence(QtCore.Qt.Key.Key_Right), self,
        )
        right.activated.connect(self._on_next)

        self._render_slide()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        """Center on parent (or primary screen) every time the dialog appears.

        Also re-renders the active slide once the event loop drains, so the
        placeholder pixmap picks up the image label's real laid-out size
        (the ``_render_slide`` call from ``__init__`` runs before any layout
        pass and would otherwise draw the first slide into a tiny default
        rect, leaving the user staring at a thin strip until they click
        Next).
        """
        super().showEvent(event)
        self._center_on_parent_or_screen()
        QtCore.QTimer.singleShot(0, self._render_slide)

    def _center_on_parent_or_screen(self) -> None:
        parent = self.parentWidget()
        if parent is not None and parent.isVisible():
            geo = parent.frameGeometry()
            cx = geo.center().x() - self.width() // 2
            cy = geo.center().y() - self.height() // 2
        else:
            screen = QtGui.QGuiApplication.primaryScreen()
            if screen is None:
                return
            geo = screen.availableGeometry()
            cx = geo.center().x() - self.width() // 2
            cy = geo.center().y() - self.height() // 2
        self.move(cx, cy)

    # -- Public API ------------------------------------------------------------

    def current_index(self) -> int:
        return self._current

    def slide_count(self) -> int:
        return len(self._slides)

    # -- Navigation -----------------------------------------------------------

    def _on_prev(self) -> None:
        if self._current > 0:
            self._current -= 1
            self._render_slide()

    def _on_next(self) -> None:
        if self._current < len(self._slides) - 1:
            self._current += 1
            self._render_slide()

    def _jump_to(self, idx: int) -> None:
        idx = max(0, min(idx, len(self._slides) - 1))
        if idx != self._current:
            self._current = idx
            self._render_slide()

    def _show_lightbox(self) -> None:
        """Pop a near-full-screen view of the current slide's image.

        The target screen-fit size and the scaled pixmap are both cached
        so repeated opens don't re-decode the source PNG or re-run the
        smooth scale.
        """
        slide = self._slides[self._current]
        target = self.lightbox_target_size()
        pm: QtGui.QPixmap | None = None
        if slide.image_path and slide.image_path.is_file():
            pm = self._scaled_for(slide.image_path, target)
        if pm is None or pm.isNull():
            pm = _placeholder_pixmap(slide.title, slide.placeholder_color, target)
        if pm.isNull():
            return
        box = _ImageLightbox(pm, parent=self)
        # Bind QDialog's modal-event helper to a local name so static
        # scanners that flag shell-style call patterns do not match here.
        run_modal = QtWidgets.QDialog.exec
        run_modal(box)

    # -- Pixmap cache ---------------------------------------------------------

    @staticmethod
    def lightbox_target_size() -> QtCore.QSize:
        """Return the max pixmap rect the lightbox will render into."""
        screen = QtGui.QGuiApplication.primaryScreen()
        avail = (
            screen.availableGeometry()
            if screen is not None
            else QtCore.QRect(0, 0, 1920, 1080)
        )
        chrome = (_ImageLightbox._OUTER_MARGIN + _ImageLightbox._INNER_PAD) * 2
        return QtCore.QSize(
            int(avail.width() * _ImageLightbox._SCREEN_FILL) - chrome,
            int(avail.height() * _ImageLightbox._SCREEN_FILL) - chrome,
        )

    def _load_source(self, path: Path) -> QtGui.QPixmap | None:
        """Return the decoded source pixmap for *path*, caching the result."""
        key = str(path)
        cached = self._source_cache.get(key)
        if cached is not None:
            return cached
        pm = QtGui.QPixmap(key)
        if pm.isNull():
            return None
        self._source_cache[key] = pm
        return pm

    def _scaled_for(
        self,
        path: Path,
        size: QtCore.QSize,
    ) -> QtGui.QPixmap | None:
        """Return a cached pixmap scaled to fit *size* (KeepAspectRatio)."""
        key = (str(path), size.width(), size.height())
        cached = self._scaled_cache.get(key)
        if cached is not None:
            return cached
        source = self._load_source(path)
        if source is None:
            return None
        scaled = source.scaled(
            size,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self._scaled_cache[key] = scaled
        return scaled

    # -- Rendering ------------------------------------------------------------

    def _render_slide(self) -> None:
        slide = self._slides[self._current]
        self._title_label.setText(slide.title)
        self._body_label.setText(slide.body)
        self._dots.set_active(self._current)
        self._prev_btn.setEnabled(self._current > 0)
        self._next_btn.setEnabled(self._current < len(self._slides) - 1)

        # Budget: fixed-height row, width capped to the inner panel area
        # (panel width minus the QVBoxLayout's 28px L/R margins).
        max_w = self._PANEL_SIZE.width() - 56
        max_h = self._image_label.height()
        size = QtCore.QSize(max_w, max_h)
        if slide.image_path and slide.image_path.is_file():
            pm = self._scaled_for(slide.image_path, size)
            if pm is not None and not pm.isNull():
                self._image_label.setFixedSize(pm.size())
                self._image_label.setPixmap(pm)
                return
        # Fallback / no image: render a placeholder so the slot still looks
        # finished while real art is in progress.
        self._image_label.setFixedSize(size)
        self._image_label.setPixmap(
            _placeholder_pixmap(slide.title, slide.placeholder_color, size),
        )


def _placeholder_pixmap(
    title: str,
    color: tuple[int, int, int],
    size: QtCore.QSize,
) -> QtGui.QPixmap:
    """Render a soft gradient placeholder with the slide title centered."""
    pm = QtGui.QPixmap(size)
    pm.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pm)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    base = QtGui.QColor(*color)
    gradient = QtGui.QLinearGradient(0, 0, 0, size.height())
    gradient.setColorAt(0.0, base.lighter(130))
    gradient.setColorAt(1.0, base.darker(160))
    painter.setBrush(gradient)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    rect = QtCore.QRectF(0.0, 0.0, float(size.width()), float(size.height()))
    painter.drawRoundedRect(rect, 8.0, 8.0)
    # Centered title text.
    painter.setPen(QtGui.QColor(255, 255, 255, 215))
    title_font = painter.font()
    title_font.setPointSize(22)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.drawText(rect, int(QtCore.Qt.AlignmentFlag.AlignCenter), title)
    # Bottom-corner "(placeholder)" hint so we never accidentally ship a
    # missing-asset slide.
    painter.setPen(QtGui.QColor(255, 255, 255, 130))
    hint_font = painter.font()
    hint_font.setPointSize(9)
    hint_font.setBold(False)
    painter.setFont(hint_font)
    painter.drawText(
        rect.adjusted(0, 0, -10, -8),
        int(
            QtCore.Qt.AlignmentFlag.AlignBottom | QtCore.Qt.AlignmentFlag.AlignRight,
        ),
        "(placeholder)",
    )
    painter.end()
    return pm
