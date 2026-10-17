"""Welcome screen widget for CraftGraph.

Displays recent projects, action buttons, and links on fresh launch.
No dependency on CraftGraphWindow -- communicates via callbacks.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from craftgraph.recent import RecentEntry
from craftgraph.theme import scaled_pt


class WelcomeWidget(QtWidgets.QWidget):
    """IntelliJ-style welcome screen embedded in the main window."""

    def __init__(
        self,
        recent_entries: list[RecentEntry],
        *,
        on_open_recent: Callable[[str, str], None],
        on_new_project: Callable[[], None],
        on_open_folder: Callable[[], None],
        on_open_project: Callable[[], None],
        on_startup_toggle: Callable[[bool], None],
        on_clear_recent: Callable[[], None] | None = None,
        show_on_startup: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_open_recent = on_open_recent
        self._on_new_project = on_new_project
        self._on_open_folder = on_open_folder
        self._on_open_project = on_open_project
        self._on_startup_toggle = on_startup_toggle
        # Callback invoked when the user clicks "Clear" on the recents
        # header. Optional so existing tests / callers that do not need
        # the clear feature stay source-compatible.
        self._on_clear_recent = on_clear_recent
        self._recent_entries = recent_entries

        self._body_layout: QtWidgets.QHBoxLayout | None = None
        self._left_column: QtWidgets.QWidget | None = None

        self._setup_ui(show_on_startup)

    def _setup_ui(self, show_on_startup: bool) -> None:
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 20)

        # Two-column body
        body = QtWidgets.QHBoxLayout()
        body.setSpacing(40)
        self._body_layout = body
        self._left_column = self._build_left_column()
        body.addWidget(self._left_column, stretch=40)
        body.addWidget(self._build_right_column(), stretch=60)
        outer.addLayout(body, stretch=1)

        # Bottom checkbox
        self._startup_cb = QtWidgets.QCheckBox("Don't show on startup")
        self._startup_cb.setChecked(not show_on_startup)
        self._startup_cb.toggled.connect(self._on_startup_toggle)
        outer.addWidget(self._startup_cb)

    # -- Left column: recent projects -----------------------------------------

    def _build_left_column(self) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        header_row = QtWidgets.QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header = QtWidgets.QLabel("Recent Projects")
        header.setStyleSheet(
            f"font-size: {scaled_pt(12)}pt; font-weight: bold; color: rgb(180, 200, 255);"
        )
        header_row.addWidget(header)
        header_row.addStretch()
        # "Clear" appears only when a callback is wired AND there is something
        # to clear. Stays disabled (but visible) when the list is empty so the
        # affordance is discoverable without being a no-op when clicked.
        if self._on_clear_recent is not None:
            clear_btn = QtWidgets.QPushButton("Clear")
            clear_btn.setFlat(True)
            clear_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            clear_btn.setEnabled(bool(self._recent_entries))
            clear_btn.setStyleSheet(
                f"QPushButton {{ color: rgb(150, 170, 210); "
                f"font-size: {scaled_pt(9)}pt; padding: 2px 6px; }}"
                "QPushButton:hover:enabled { color: rgb(200, 220, 255); }"
                "QPushButton:disabled { color: rgb(90, 90, 90); }"
            )
            clear_btn.clicked.connect(self._handle_clear_clicked)
            header_row.addWidget(clear_btn)
        layout.addLayout(header_row)

        if not self._recent_entries:
            empty = QtWidgets.QLabel("(No recent projects)")
            empty.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: rgb(120, 120, 120); font-style: italic; padding: 40px;")
            layout.addWidget(empty, stretch=1)
        else:
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )

            list_widget = QtWidgets.QWidget()
            list_layout = QtWidgets.QVBoxLayout(list_widget)
            list_layout.setContentsMargins(0, 4, 0, 4)
            list_layout.setSpacing(2)

            for entry in self._recent_entries:
                item = _RecentEntryItem(entry, on_click=self._on_open_recent)
                list_layout.addWidget(item)

            list_layout.addStretch()
            scroll.setWidget(list_widget)
            layout.addWidget(scroll, stretch=1)

        return container

    def _handle_clear_clicked(self) -> None:
        """Notify the host, then re-render the left column as the empty state."""
        if self._on_clear_recent is not None:
            self._on_clear_recent()
        self.set_recent_entries([])

    def set_recent_entries(self, entries: list[RecentEntry]) -> None:
        """Replace the recents list and rebuild the left column in place."""
        self._recent_entries = entries
        if self._body_layout is None or self._left_column is None:
            return
        old = self._left_column
        new_column = self._build_left_column()
        self._body_layout.replaceWidget(old, new_column)
        old.deleteLater()
        self._body_layout.setStretchFactor(new_column, 40)
        self._left_column = new_column

    # -- Right column: branding + actions + links -----------------------------

    def _build_right_column(self) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # Branding
        layout.addSpacing(20)

        icon_label = QtWidgets.QLabel()
        icon_path = _bundled_icon()
        if icon_path is not None:
            pixmap = QtGui.QPixmap(str(icon_path))
            if not pixmap.isNull():
                icon_label.setPixmap(
                    pixmap.scaled(
                        64,
                        64,
                        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    ),
                )
        layout.addWidget(icon_label, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        title = QtWidgets.QLabel("CraftGraph")
        title.setStyleSheet(
            f"font-size: {scaled_pt(20)}pt; font-weight: bold; color: rgb(220, 220, 220);"
        )
        title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        try:
            ver = version("craftgraph")
        except Exception:
            ver = "dev"
        version_label = QtWidgets.QLabel(f"v{ver}")
        version_label.setStyleSheet(
            f"font-size: {scaled_pt(10)}pt; color: rgb(140, 140, 140);"
        )
        version_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)

        layout.addSpacing(24)

        # Action buttons
        style = self.style()
        btn_width = 220

        new_proj_btn = QtWidgets.QPushButton(
            style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogNewFolder),
            "New Project",
        )
        new_proj_btn.setFixedWidth(btn_width)
        new_proj_btn.setMinimumHeight(36)
        new_proj_btn.clicked.connect(self._on_new_project)
        layout.addWidget(new_proj_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        open_folder_btn = QtWidgets.QPushButton(
            style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DirOpenIcon),
            "Open Folder",
        )
        open_folder_btn.setFixedWidth(btn_width)
        open_folder_btn.setMinimumHeight(36)
        open_folder_btn.clicked.connect(self._on_open_folder)
        layout.addWidget(open_folder_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        open_proj_btn = QtWidgets.QPushButton(
            style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileIcon),
            "Open Project",
        )
        open_proj_btn.setFixedWidth(btn_width)
        open_proj_btn.setMinimumHeight(36)
        open_proj_btn.clicked.connect(self._on_open_project)
        layout.addWidget(open_proj_btn, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(24)

        # Links
        links_header = QtWidgets.QLabel("Links")
        links_header.setStyleSheet(
            f"font-size: {scaled_pt(12)}pt; font-weight: bold; color: rgb(180, 200, 255);"
        )
        layout.addWidget(links_header, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)

        for label, url in _LINKS:
            link = QtWidgets.QLabel(
                f'<a href="{url}" style="color: rgb(100, 160, 255);">{label}</a>'
            )
            link.setOpenExternalLinks(True)
            link.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(link)

        layout.addStretch()

        return container


class _RecentEntryItem(QtWidgets.QFrame):
    """A clickable row representing one recent project/folder."""

    def __init__(
        self,
        entry: RecentEntry,
        *,
        on_click: Callable[[str, str], None],
    ) -> None:
        super().__init__()
        self._entry = entry
        self._on_click = on_click
        self._stale = not Path(entry.path).exists()

        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QFrame { padding: 6px 8px; border-radius: 4px; }"
            "QFrame:hover { background: rgb(55, 55, 55); }"
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        path_obj = Path(entry.path)
        display_name = path_obj.stem if entry.entry_type == "project" else path_obj.name

        style = self.style()
        if entry.entry_type == "project":
            icon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileIcon)
        else:
            icon = style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DirIcon)

        name_row = QtWidgets.QHBoxLayout()
        icon_label = QtWidgets.QLabel()
        icon_label.setPixmap(icon.pixmap(16, 16))
        name_row.addWidget(icon_label)

        name_label = QtWidgets.QLabel(display_name)
        name_pt = scaled_pt(11)
        name_style = f"font-size: {name_pt}pt; color: rgb(200, 200, 200);"
        if self._stale:
            name_style = (
                f"font-size: {name_pt}pt; color: rgb(100, 100, 100);"
                " text-decoration: line-through;"
            )
        name_label.setStyleSheet(name_style)
        name_row.addWidget(name_label)
        name_row.addStretch()
        layout.addLayout(name_row)

        path_label = QtWidgets.QLabel(entry.path)
        path_pt = scaled_pt(9)
        path_style = f"font-size: {path_pt}pt; color: rgb(120, 120, 120);"
        if self._stale:
            path_style = (
                f"font-size: {path_pt}pt; color: rgb(80, 80, 80);"
                " text-decoration: line-through;"
            )
        path_label.setStyleSheet(path_style)
        path_label.setWordWrap(True)
        layout.addWidget(path_label)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        self._on_click(self._entry.path, self._entry.entry_type)


def _bundled_icon() -> Path | None:
    from craftgraph.app_dirs import bundled_icon_path

    path = bundled_icon_path()
    return path if path.exists() else None


GITHUB_URL = "https://github.com/Rovetown/CraftGraph"
CC3_WIKI_URL = (
    "https://github.com/MrPurple6411/PrimeSonicSubnauticaMods/tree/master/CustomCraft3"
)
_LINKS: list[tuple[str, str]] = [
    ("GitHub", GITHUB_URL),
    ("CC3 Wiki", CC3_WIKI_URL),
]
