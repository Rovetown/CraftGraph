"""Qt-based GUI application shell for CraftGraph (PySide6 + NodeGraphQt).

Provides the main application window with:
  - NodeGraphQt graph widget (left panel)
  - Code editor via QPlainTextEdit (right panel)
  - Menu bar (File, Edit, View)
  - Status bar

Architecture notes:
  - This module is part of the GUI layer and imports from qt_nodes.py.
  - Core modules (parser, models, graph) are imported only when needed
    (file loading), keeping startup fast.
  - The existing ``craftgraph gui`` (DearPyGui) command is preserved;
    this module powers the ``craftgraph qt-gui`` command.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from NodeGraphQt import NodeGraph
from PySide6 import QtCore, QtGui, QtWidgets

from craftgraph.code_editor import CodeEditor
from craftgraph.highlighter import EasyMarkupHighlighter
from craftgraph.layout_store import layout_path_for, load_layout, save_layout
from craftgraph.qt_nodes import (
    IDENTIFIER,
    NODE_REGISTRY,
    CraftGraphBaseNode,
    ModifiedRecipeNode,
    NodeKind,
    OrphanIngredientNode,
    all_node_classes,
)
from craftgraph.serializer import serialize_file
from craftgraph.sprite_loader import resolve_sprite, scan_assets_dir
from craftgraph.sync import (
    SyncGuard,
    UIToModelHandler,
    apply_layout,
    compute_hierarchy_layout,
    connect_hierarchy,
    connect_ingredients,
    highlight_cycle_edges,
    model_position_key,
    overlay_user_positions,
    populate_graph,
    update_child_count_labels,
)

_POPUP_MAX_VISIBLE = 12
_POPUP_STYLE = (
    "QListWidget {"
    "  background: rgb(30, 30, 30);"
    "  color: rgb(200, 200, 200);"
    "  border: 1px solid rgb(80, 80, 80);"
    "  font-size: 11pt;"
    "}"
    "QListWidget::item:selected {"
    "  background: rgb(60, 80, 120);"
    "}"
)


class NodeCompletionPopup(QtWidgets.QFrame):
    """IDE-style autocomplete popup for node text inputs.

    A single instance is shared across all nodes in the window.
    It lives outside the QGraphicsScene to avoid proxy widget focus
    issues, and positions itself via coordinate transforms.

    Behavior mirrors VS Code / PyCharm intellisense:
      - Appears while typing, filters with each keystroke
      - Up/Down navigate, Enter/Tab accept, Escape dismisses
      - Click on an item accepts it
      - Hides when no matches remain or text matches exactly
    """

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent, QtCore.Qt.WindowType.ToolTip)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        self._list = QtWidgets.QListWidget(self)
        self._list.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self._list.setStyleSheet(_POPUP_STYLE)
        self._list.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self._list.itemClicked.connect(self._on_item_clicked)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._list)

        self._active_edit: QtWidgets.QLineEdit | None = None
        self._all_words: list[str] = []
        self.hide()

    # -- public API -----------------------------------------------------------

    def attach(
        self,
        line_edit: QtWidgets.QLineEdit,
        words: list[str],
    ) -> None:
        """Wire *line_edit* to show this popup with *words* as candidates."""
        line_edit.textEdited.connect(
            lambda text, le=line_edit, w=words: self._on_text_edited(le, w, text),
        )
        line_edit.installEventFilter(self)

    def update_words(
        self,
        line_edit: QtWidgets.QLineEdit,
        words: list[str],
    ) -> None:
        """Replace the word list for a previously attached line edit.

        Reconnects ``textEdited`` so the new word list is used.
        """
        try:
            line_edit.textEdited.disconnect()
        except RuntimeError:
            pass
        line_edit.textEdited.connect(
            lambda text, le=line_edit, w=words: self._on_text_edited(le, w, text),
        )

    # -- filtering & display --------------------------------------------------

    def _on_text_edited(
        self,
        line_edit: QtWidgets.QLineEdit,
        words: list[str],
        text: str,
    ) -> None:
        self._active_edit = line_edit
        self._all_words = words

        if not text:
            self.hide()
            return

        prefix = text.lower()
        matches = [w for w in words if prefix in w.lower()]

        # Hide if nothing matches or if text is an exact match
        if not matches or (len(matches) == 1 and matches[0].lower() == prefix):
            self.hide()
            return

        self._list.clear()
        for m in matches[:_POPUP_MAX_VISIBLE]:
            self._list.addItem(m)
        self._list.setCurrentRow(0)

        self._position_near(line_edit)
        self.show()
        self.raise_()

    def _position_near(self, line_edit: QtWidgets.QLineEdit) -> None:
        """Place the popup just below the QLineEdit in screen coordinates."""
        global_pos = line_edit.mapToGlobal(
            QtCore.QPoint(0, line_edit.height()),
        )
        row_height = self._list.sizeHintForRow(0) or 20
        visible = min(self._list.count(), _POPUP_MAX_VISIBLE)
        popup_h = row_height * visible + 4
        self.setFixedWidth(max(line_edit.width(), 180))
        self.setFixedHeight(popup_h)
        self.move(global_pos)

    # -- accept / dismiss -----------------------------------------------------

    def _accept_current(self) -> None:
        item = self._list.currentItem()
        if item is not None and self._active_edit is not None:
            self._active_edit.setText(item.text())
        self.hide()

    def _on_item_clicked(self, item: QtWidgets.QListWidgetItem) -> None:
        if self._active_edit is not None:
            self._active_edit.setText(item.text())
        self.hide()

    # -- keyboard navigation via event filter ---------------------------------

    def eventFilter(
        self,
        obj: QtCore.QObject,
        event: QtCore.QEvent,
    ) -> bool:
        if not self.isVisible() or obj is not self._active_edit:
            return False

        if event.type() != QtCore.QEvent.Type.KeyPress:
            return False

        key = event.key()

        if key == QtCore.Qt.Key.Key_Down:
            row = self._list.currentRow()
            if row < self._list.count() - 1:
                self._list.setCurrentRow(row + 1)
            return True

        if key == QtCore.Qt.Key.Key_Up:
            row = self._list.currentRow()
            if row > 0:
                self._list.setCurrentRow(row - 1)
            return True

        if key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter, QtCore.Qt.Key.Key_Tab):
            self._accept_current()
            return True

        if key == QtCore.Qt.Key.Key_Escape:
            self.hide()
            return True

        return False


@dataclass
class FileTab:
    """Everything needed for one recipe file's tab."""

    parsed_file: object  # ParsedFile
    graph: NodeGraph
    editor: CodeEditor
    history: object  # EditHistory
    ui_handler: UIToModelHandler | None
    sync_guard: SyncGuard
    model_to_node: dict[int, object] = field(default_factory=dict)
    parse_timer: QtCore.QTimer | None = None
    user_positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    cycle_count: int = 0


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class CraftGraphWindow(QtWidgets.QMainWindow):
    """Main application window for the Qt-based CraftGraph editor."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("CraftGraph")
        self.resize(1400, 900)

        # -- Per-file tabs ------------------------------------------------
        self._file_tabs: list[FileTab] = []
        self._source_path = Path("untitled.txt")
        self._sprite_lookup: dict[str, Path] = {}
        self._manual_sprites: dict[str, Path] = {}
        self._id_words: list[str] | None = None
        self._path_words: list[str] = []
        self._node_popup = NodeCompletionPopup(self)

        # -- Build UI ---------------------------------------------------------
        self._setup_menu_bar()
        self._setup_central_widget()
        self._setup_status_bar()

    # -- Properties -----------------------------------------------------------

    @property
    def _active_tab(self) -> FileTab:
        """The currently active FileTab."""
        idx = self._tab_bar.currentIndex()
        if idx < 0 or idx >= len(self._file_tabs):
            return self._file_tabs[0]
        return self._file_tabs[idx]

    @property
    def graph(self) -> NodeGraph:
        return self._active_tab.graph

    @property
    def code_editor(self) -> CodeEditor:
        return self._active_tab.editor

    @property
    def sync_guard(self) -> SyncGuard:
        return self._active_tab.sync_guard

    @property
    def model_to_node(self) -> dict[int, object]:
        return self._active_tab.model_to_node

    @property
    def edit_history(self) -> object:
        return self._active_tab.history

    @property
    def ui_handler(self) -> UIToModelHandler | None:
        return self._active_tab.ui_handler

    # -- Menu bar -------------------------------------------------------------

    def _setup_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("&File")

        open_folder_action = QtGui.QAction("Open &Folder...", self)
        open_folder_action.setShortcut(QtGui.QKeySequence.StandardKey.Open)
        open_folder_action.triggered.connect(self._on_open_folder)
        file_menu.addAction(open_folder_action)

        open_file_action = QtGui.QAction("Open &File...", self)
        open_file_action.triggered.connect(self._on_open_file)
        file_menu.addAction(open_file_action)

        self._save_action = QtGui.QAction("&Save", self)
        self._save_action.setShortcut(QtGui.QKeySequence.StandardKey.Save)
        self._save_action.triggered.connect(self._on_save)
        file_menu.addAction(self._save_action)

        save_all_action = QtGui.QAction("Save &All", self)
        save_all_action.triggered.connect(self._on_save_all)
        file_menu.addAction(save_all_action)

        self._export_action = QtGui.QAction("&Export...", self)
        self._export_action.setEnabled(False)
        file_menu.addAction(self._export_action)

        file_menu.addSeparator()

        exit_action = QtGui.QAction("E&xit", self)
        exit_action.setShortcut(QtGui.QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        # Note: Ctrl+Z / Ctrl+Y shortcuts are already handled by
        # NodeGraphQt's internal NodeViewer undo/redo actions. Adding
        # duplicate shortcuts here causes "Ambiguous shortcut overload"
        # warnings. Menu items are still clickable without hotkeys.
        edit_menu = menu_bar.addMenu("&Edit")

        undo_action = QtGui.QAction("&Undo", self)
        undo_action.triggered.connect(self._on_undo)
        edit_menu.addAction(undo_action)

        redo_action = QtGui.QAction("&Redo", self)
        redo_action.triggered.connect(self._on_redo)
        edit_menu.addAction(redo_action)

        # View menu
        view_menu = menu_bar.addMenu("&View")

        self._minimap_action = QtGui.QAction("&Minimap", self)
        self._minimap_action.setCheckable(True)
        self._minimap_action.setChecked(False)
        self._minimap_action.setEnabled(False)  # No built-in minimap in NodeGraphQt
        view_menu.addAction(self._minimap_action)

        self._reset_layout_action = QtGui.QAction("&Reset Layout", self)
        self._reset_layout_action.triggered.connect(self._on_reset_layout)
        view_menu.addAction(self._reset_layout_action)

        # Help menu
        help_menu = menu_bar.addMenu("&Help")

        settings_action = QtGui.QAction("&Settings...", self)
        settings_action.triggered.connect(self._on_settings)
        help_menu.addAction(settings_action)

        help_menu.addSeparator()

        about_action = QtGui.QAction("&About CraftGraph", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    # -- Central widget (splitter layout) -------------------------------------

    def _setup_central_widget(self) -> None:
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab bar (file tabs across the top)
        self._tab_bar = QtWidgets.QTabBar()
        self._tab_bar.setTabsClosable(False)
        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tab_bar)

        # Splitter with two stacked widgets
        self._splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

        self._graph_stack = QtWidgets.QStackedWidget()
        self._splitter.addWidget(self._graph_stack)

        self._editor_stack = QtWidgets.QStackedWidget()
        self._splitter.addWidget(self._editor_stack)

        self._splitter.setSizes([980, 420])
        layout.addWidget(self._splitter)

        self.setCentralWidget(central)

        # Create placeholder tab (shown before files are loaded)
        self._create_placeholder_tab()

    def _create_placeholder_tab(self) -> None:
        """Set up the initial empty tab shown before any files are loaded."""
        graph = NodeGraph()
        graph.set_acyclic(False)
        for cls in all_node_classes():
            graph.register_node(cls)

        editor = CodeEditor()
        editor.setPlaceholderText("Open a recipe file to view its source...")
        EasyMarkupHighlighter(editor.document())
        self._setup_autocomplete_for(editor)

        from craftgraph.commands import EditHistory

        tab = FileTab(
            parsed_file=None,  # type: ignore[arg-type]
            graph=graph,
            editor=editor,
            history=EditHistory(on_change=self._on_model_changed),
            ui_handler=None,
            sync_guard=SyncGuard(),
        )
        self._file_tabs.append(tab)

        self._graph_stack.addWidget(graph.widget)
        self._editor_stack.addWidget(editor)
        self._tab_bar.addTab("untitled")

        self._setup_context_menus_for(graph)

    def _on_tab_changed(self, index: int) -> None:
        """Switch both stacked widgets to the selected file tab."""
        if index < 0 or index >= len(self._file_tabs):
            return
        self._graph_stack.setCurrentIndex(index)
        self._editor_stack.setCurrentIndex(index)

        tab = self._file_tabs[index]
        name = "CraftGraph"
        if tab.parsed_file is not None:
            name += f" - {tab.parsed_file.source_path.name}"
        if hasattr(tab.history, "is_dirty") and tab.history.is_dirty:
            name += " *"
        self.setWindowTitle(name)

    # -- Status bar -----------------------------------------------------------

    def _setup_status_bar(self) -> None:
        self.statusBar().showMessage("Ready")

    # -- Close event ----------------------------------------------------------

    def _has_unsaved_changes(self) -> bool:
        """True if any file tab has unsaved edits."""
        return any(
            hasattr(tab.history, "is_dirty") and tab.history.is_dirty for tab in self._file_tabs
        )

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        """Prompt the user if there are unsaved changes before closing."""
        if not self._has_unsaved_changes():
            self._save_positions()
            event.accept()
            return

        result = QtWidgets.QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Do you want to save before closing?",
            QtWidgets.QMessageBox.StandardButton.Save
            | QtWidgets.QMessageBox.StandardButton.Discard
            | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Save,
        )

        if result == QtWidgets.QMessageBox.StandardButton.Save:
            self._save_all()
            event.accept()
        elif result == QtWidgets.QMessageBox.StandardButton.Discard:
            self._save_positions()
            event.accept()
        else:
            event.ignore()

    def _save_positions(self) -> None:
        """Persist all user-dragged node positions to the layout sidecar file."""
        if not self._file_tabs:
            return
        # Find a tab with a real source path to determine the sidecar location
        source_path = None
        for tab in self._file_tabs:
            if tab.parsed_file is not None:
                source_path = tab.parsed_file.source_path
                break
        if source_path is None:
            return

        layout_file = layout_path_for(self._source_path)
        all_positions: dict[str, dict[str, list[float]]] = {}
        for tab in self._file_tabs:
            if tab.parsed_file is None:
                continue
            tab_key = tab.parsed_file.source_path.stem
            all_positions[tab_key] = {k: [v[0], v[1]] for k, v in tab.user_positions.items()}

        # Only write if at least one tab has user positions
        if any(pos for pos in all_positions.values()):
            save_layout(layout_file, all_positions)

    def _save_all(self) -> None:
        """Save all dirty tabs to disk."""
        saved = 0
        for tab in self._file_tabs:
            if tab.parsed_file is None:
                continue
            if not hasattr(tab.history, "is_dirty") or not tab.history.is_dirty:
                continue
            path = tab.parsed_file.source_path
            text = serialize_file(tab.parsed_file)
            path.write_text(text, encoding="utf-8")
            tab.history.mark_saved()
            saved += 1
        self._save_positions()
        if saved:
            self._on_tab_changed(self._tab_bar.currentIndex())
            self.statusBar().showMessage(f"Saved {saved} file(s)")

    # -- Menu handlers --------------------------------------------------------

    def _on_open_folder(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Open Recipe Directory",
        )
        if directory:
            self.load_recipes(Path(directory))

    def _on_open_file(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open Recipe File",
            "",
            "CC3 Recipe Files (*.txt);;All Files (*)",
        )
        if file_path:
            self.load_recipes(Path(file_path))

    def _on_save(self) -> None:
        """Save the active tab's file to disk."""
        tab = self._active_tab
        if tab.parsed_file is None:
            return
        path = tab.parsed_file.source_path
        text = serialize_file(tab.parsed_file)
        path.write_text(text, encoding="utf-8")
        tab.history.mark_saved()
        self._save_positions()
        self._on_tab_changed(self._tab_bar.currentIndex())
        self.statusBar().showMessage(f"Saved {path.name}")

    def _on_save_all(self) -> None:
        """Save all dirty tabs to disk."""
        self._save_all()

    def _on_undo(self) -> None:
        stack = self._active_tab.graph.undo_stack()
        if not stack.canUndo():
            return
        desc = stack.undoText()
        stack.undo()
        self.statusBar().showMessage(f"Undo: {desc}" if desc else "Undo")

    def _on_redo(self) -> None:
        stack = self._active_tab.graph.undo_stack()
        if not stack.canRedo():
            return
        desc = stack.redoText()
        stack.redo()
        self.statusBar().showMessage(f"Redo: {desc}" if desc else "Redo")

    def _on_reset_layout(self) -> None:
        """Re-compute the default hierarchical layout for the active tab.

        Discards all user-dragged positions and updates the sidecar file.
        """
        tab = self._active_tab
        if tab.parsed_file is None:
            return
        tab.user_positions.clear()
        with tab.sync_guard():
            positions = compute_hierarchy_layout([tab.parsed_file], tab.model_to_node)
            apply_layout(positions, tab.model_to_node)
        self._save_positions()
        self.statusBar().showMessage("Layout reset to default")

    def _on_settings(self) -> None:
        """Show a placeholder Settings dialog."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.setMinimumSize(300, 150)
        layout = QtWidgets.QVBoxLayout(dialog)
        label = QtWidgets.QLabel("Settings coming soon.")
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def _on_about(self) -> None:
        """Show the About CraftGraph dialog."""
        from craftgraph import __version__

        QtWidgets.QMessageBox.about(
            self,
            "About CraftGraph",
            f"<h3>CraftGraph v{__version__}</h3>"
            f"<p>Recipe dependency graph tool for "
            f"<b>CustomCraft3</b> (Subnautica).</p>"
            f"<p>Parses EasyMarkup recipe files, detects circular "
            f"dependencies, and provides a visual node editor.</p>",
        )

    def _on_cycle_rejected(self, consumer_id: str, ingredient_id: str) -> None:
        """Show a red-background status bar warning when a connection would create a cycle."""
        bar = self.statusBar()
        bar.setStyleSheet("QStatusBar { background-color: #cc3c3c; color: white; }")
        bar.showMessage(
            f"Rejected: adding {ingredient_id} to {consumer_id} would create a circular dependency"
        )
        QtCore.QTimer.singleShot(5000, self._clear_status_style)

    def _clear_status_style(self) -> None:
        """Reset the status bar to its default style."""
        self.statusBar().setStyleSheet("")

    # -- Node operations (delete, copy, paste, duplicate) --------------------

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # type: ignore[override]
        """Handle keyboard shortcuts for node operations."""
        key = event.key()
        ctrl = bool(event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier)

        if key == QtCore.Qt.Key.Key_Delete:
            self._delete_selected_nodes()
        elif ctrl and key == QtCore.Qt.Key.Key_C:
            self.graph.copy_nodes()
        elif ctrl and key == QtCore.Qt.Key.Key_V:
            self._paste_nodes()
        elif ctrl and key == QtCore.Qt.Key.Key_D:
            self._duplicate_selected_nodes()
        else:
            super().keyPressEvent(event)

    def _delete_selected_nodes(self) -> None:
        """Delete all currently selected nodes from the graph and model."""
        selected = self.graph.selected_nodes()
        if not selected:
            return
        self.graph.delete_nodes(selected)
        self._update_code_editor_from_model()

    def _on_delete_node(
        self,
        graph: NodeGraph,
        node: CraftGraphBaseNode,
    ) -> None:
        """Context menu callback: delete a single node."""
        graph.delete_node(node)
        self._update_code_editor_from_model()

    def _on_copy_node(
        self,
        graph: NodeGraph,
        node: CraftGraphBaseNode,
    ) -> None:
        """Context menu callback: copy the node to clipboard."""
        graph.copy_nodes([node])

    def _on_duplicate_node(
        self,
        graph: NodeGraph,
        node: CraftGraphBaseNode,
    ) -> None:
        """Context menu callback: duplicate a single node."""
        new_nodes = graph.duplicate_nodes([node])
        if new_nodes:
            self._adopt_orphan_nodes(new_nodes)

    def _paste_nodes(self) -> None:
        """Paste nodes from clipboard and wire them into the model."""
        new_nodes = self.graph.paste_nodes()
        if new_nodes:
            self._adopt_orphan_nodes(new_nodes)

    def _duplicate_selected_nodes(self) -> None:
        """Duplicate selected nodes and wire them into the model."""
        selected = self.graph.selected_nodes()
        if not selected:
            return
        new_nodes = self.graph.duplicate_nodes(selected)
        if new_nodes:
            self._adopt_orphan_nodes(new_nodes)

    def _adopt_orphan_nodes(self, nodes: list[object]) -> None:
        """Create model objects for pasted/duplicated nodes.

        NodeGraphQt's paste/duplicate creates visual nodes with correct
        properties but no ``model_ref``. This method reads each node's
        properties, creates a matching model object, appends it to the
        parsed file, and sets ``model_ref``.
        """
        from craftgraph.models import (
            AddedRecipe,
            AliasRecipe,
            CraftingTab,
            CustomBioFuel,
            CustomFabricator,
            CustomFood,
            CustomFragmentCount,
            CustomSize,
            Ingredient,
            ModifiedRecipe,
            MovedRecipe,
        )
        from craftgraph.qt_nodes import (
            AddedRecipeNode,
            AliasRecipeNode,
            CraftingTabNode,
            CustomBioFuelNode,
            CustomFoodNode,
            CustomFragmentCountNode,
            CustomSizeNode,
            FabricatorNode,
            ModifiedRecipeNode,
            MovedRecipeNode,
        )

        tab = self._active_tab
        if tab.parsed_file is None:
            return

        # Map node class -> (model_class, parsed_file_attr_name)
        # Order: most-specific first for isinstance dispatch
        node_to_model: list[tuple[type, type, str]] = [
            (CustomFoodNode, CustomFood, "custom_foods"),
            (AliasRecipeNode, AliasRecipe, "alias_recipes"),
            (AddedRecipeNode, AddedRecipe, "added_recipes"),
            (ModifiedRecipeNode, ModifiedRecipe, "modified_recipes"),
            (FabricatorNode, CustomFabricator, "custom_fabricators"),
            (CraftingTabNode, CraftingTab, "crafting_tabs"),
            (CustomSizeNode, CustomSize, "custom_sizes"),
            (MovedRecipeNode, MovedRecipe, "moved_recipes"),
            (CustomBioFuelNode, CustomBioFuel, "custom_bio_fuels"),
            (CustomFragmentCountNode, CustomFragmentCount, "custom_fragment_counts"),
        ]

        for node in nodes:
            if not isinstance(node, CraftGraphBaseNode):
                continue
            if node.model_ref is not None:
                continue  # already adopted

            model = None
            attr_name = None

            for node_cls, model_cls, attr in node_to_model:
                if not isinstance(node, node_cls):
                    continue

                if model_cls is CraftingTab:
                    model = model_cls(
                        tab_id=node.get_property("tab_id") or "NewTab",
                    )
                elif model_cls is CustomFabricator:
                    model = model_cls(
                        item_id=node.get_property("item_id") or "NewFab",
                        display_name=node.get_property("display_name") or "",
                    )
                elif model_cls is CustomSize:
                    model = model_cls(
                        item_id=node.get_property("item_id") or "NewItem",
                    )
                    model.width = int(node.get_property("size_width") or 1)
                    model.height = int(node.get_property("size_height") or 1)
                elif model_cls is CustomBioFuel:
                    model = model_cls(
                        item_id=node.get_property("item_id") or "NewItem",
                    )
                    model.energy = float(node.get_property("energy") or 0)
                elif model_cls is CustomFragmentCount:
                    model = model_cls(
                        item_id=node.get_property("item_id") or "NewItem",
                    )
                    model.fragments_to_scan = int(node.get_property("fragments_to_scan") or 1)
                elif model_cls is MovedRecipe:
                    model = model_cls(
                        item_id=node.get_property("item_id") or "NewItem",
                    )
                    model.old_path = node.get_property("old_path") or ""
                    model.new_path = node.get_property("new_path") or ""
                else:
                    # Recipe types
                    model = model_cls(
                        item_id=node.get_property("item_id") or "NewItem",
                    )
                    if hasattr(model, "amount_crafted"):
                        model.amount_crafted = int(node.get_property("amount_crafted") or 1)
                    if hasattr(model, "path"):
                        model.path = node.get_property("path") or ""
                    if hasattr(model, "display_name"):
                        model.display_name = node.get_property("display_name") or ""
                    if hasattr(model, "tooltip"):
                        model.tooltip = node.get_property("tooltip") or ""

                attr_name = attr
                break

            if model is None or attr_name is None:
                continue

            node.model_ref = model
            tab.model_to_node[id(model)] = node
            getattr(tab.parsed_file, attr_name).append(model)

            if tab.ui_handler is not None:
                tab.ui_handler.register_node(node)

        self._update_code_editor_from_model()

    def _on_model_changed(self) -> None:
        """Called by EditHistory after every execute/undo/redo.

        Updates the window title (dirty flag), re-serializes the model
        into the code editor, and refreshes child count labels on
        container nodes so the text always reflects the current state.
        """
        tab = self._active_tab
        title = "CraftGraph"
        if tab.parsed_file is not None:
            title += f" - {tab.parsed_file.source_path.name}"
        if hasattr(tab.history, "is_dirty") and tab.history.is_dirty:
            title += " *"
        self.setWindowTitle(title)
        self._update_code_editor_from_model()
        update_child_count_labels(tab.model_to_node)

    def _update_code_editor_from_model(self) -> None:
        """Serialize the active tab's model into its code editor.

        Preserves the cursor position and scroll offset so the editor
        does not jump to the top after every model re-serialization.
        """
        tab = self._active_tab
        if tab.parsed_file is None:
            return
        editor = tab.editor
        # Save position before replacing text
        cursor = editor.textCursor()
        cursor_pos = cursor.position()
        anchor_pos = cursor.anchor()
        scroll_val = editor.verticalScrollBar().value()

        with tab.sync_guard():
            editor.setPlainText(serialize_file(tab.parsed_file))

        # Restore cursor position (clamped to new document length)
        new_cursor = editor.textCursor()
        doc_len = editor.document().characterCount() - 1
        new_cursor.setPosition(min(anchor_pos, doc_len))
        if anchor_pos != cursor_pos:
            new_cursor.setPosition(
                min(cursor_pos, doc_len),
                QtGui.QTextCursor.MoveMode.KeepAnchor,
            )
        editor.setTextCursor(new_cursor)
        editor.verticalScrollBar().setValue(scroll_val)

    # -- Node selection -> code editor scroll -----------------------------------

    def _scroll_editor_to_node(self, node: object, tab: FileTab) -> None:
        """Scroll the code editor to the entry corresponding to *node*.

        Searches for ``ItemID: <value>`` or ``TabID: <value>`` in the
        editor text and highlights the entire block (from the ID line
        up to the next entry or end of file).
        """
        model = getattr(node, "model_ref", None)
        if model is None:
            return

        item_id = getattr(model, "item_id", None) or getattr(model, "tab_id", None)
        if not item_id:
            return

        editor = tab.editor
        text = editor.toPlainText()

        # Search for "ItemID: <value>" or "TabID: <value>" (case-insensitive).
        # Use a word-boundary anchor after the value so that e.g.
        # "Alch_LabContainer" does not match "Alch_LabContainer3".
        import re

        search_patterns = [
            rf"ItemID:\s*{re.escape(item_id)}\b",
            rf"TabID:\s*{re.escape(item_id)}\b",
        ]

        target_line = -1
        for pattern in search_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                target_line = text[: match.start()].count("\n")
                break

        if target_line < 0:
            return

        # Move cursor to the target line and highlight it
        block = editor.document().findBlockByNumber(target_line)
        if not block.isValid():
            return

        cursor = editor.textCursor()
        cursor.setPosition(block.position())

        # Select from the ItemID/TabID line to the closing ");" or next entry
        end_block = block
        lines_text = text.split("\n")
        for i in range(target_line + 1, min(target_line + 200, len(lines_text))):
            line = lines_text[i].strip()
            # Stop at the next entry boundary or closing delimiter
            if line.startswith("ItemID:") or line.startswith("TabID:"):
                break
            if line in ("),", ");", ")"):
                break
            end_block = end_block.next()
            if not end_block.isValid():
                break

        cursor.setPosition(
            end_block.position() + end_block.length() - 1,
            QtGui.QTextCursor.MoveMode.KeepAnchor,
        )
        editor.setTextCursor(cursor)
        editor.centerCursor()

    # -- Code editor -> model sync (per-tab) ----------------------------------

    def _apply_code_editor_text_for(self, tab: FileTab) -> None:
        """Parse the code editor text and rebuild the tab's node graph."""
        from craftgraph.parser import MappingError, ParseError, parse_text

        text = tab.editor.toPlainText()
        if not text.strip():
            return

        src = tab.parsed_file.source_path if tab.parsed_file is not None else self._source_path
        try:
            pf = parse_text(text, source_path=src)
        except (ParseError, MappingError) as exc:
            self.statusBar().showMessage(f"Parse error: {exc}")
            return

        # Tear down previous handler
        if tab.ui_handler is not None:
            tab.ui_handler.disconnect()
            tab.ui_handler = None

        tab.graph.clear_session()
        tab.history.clear()

        with tab.sync_guard():
            tab.model_to_node = populate_graph(tab.graph, [pf], edit_history=tab.history)
            connect_hierarchy(tab.graph, [pf], tab.model_to_node)
            connect_ingredients(tab.graph, [pf], tab.model_to_node)
            positions = compute_hierarchy_layout([pf], tab.model_to_node)
            overlay_user_positions(positions, tab.user_positions, tab.model_to_node)
            apply_layout(positions, tab.model_to_node)
            highlight_cycle_edges(tab.graph, [pf], tab.model_to_node)
            update_child_count_labels(tab.model_to_node)

        tab.parsed_file = pf
        self._apply_sprites_for(tab)
        self._update_path_completions()
        tab.ui_handler = UIToModelHandler(
            graph=tab.graph,
            history=tab.history,
            guard=tab.sync_guard,
            parsed_files=[pf],
            model_to_node=tab.model_to_node,
            on_cycle_rejected=self._on_cycle_rejected,
        )

        node_count = len(tab.model_to_node)
        self.statusBar().showMessage(f"Parsed {node_count} node(s) from editor")

    # -- Context menus (per-graph) --------------------------------------------

    def _setup_context_menus_for(self, graph: NodeGraph) -> None:
        """Register sprite and node-creation context menus on a graph."""
        # Node operations
        nodes_menu = graph.get_context_menu("nodes")
        nodes_menu.add_command(
            "Delete",
            func=self._on_delete_node,
            node_class=CraftGraphBaseNode,
        )
        nodes_menu.add_command(
            "Copy",
            func=self._on_copy_node,
            node_class=CraftGraphBaseNode,
        )
        nodes_menu.add_command(
            "Duplicate",
            func=self._on_duplicate_node,
            node_class=CraftGraphBaseNode,
        )

        # Selection toggle
        nodes_menu.add_command(
            "Toggle Selection",
            func=self._on_toggle_selection,
            node_class=CraftGraphBaseNode,
        )

        # Ingredient management (recipe nodes only)
        nodes_menu.add_command(
            "Delete Ingredient...",
            func=self._on_delete_ingredient,
            node_class=ModifiedRecipeNode,
        )
        nodes_menu.add_command(
            "Promote Ingredient to Recipe...",
            func=self._on_promote_ingredient,
            node_class=ModifiedRecipeNode,
        )

        # Sprite context menu entries removed -- use SpriteNode instead

        # Canvas operations
        graph_menu = graph.get_context_menu("graph")
        graph_menu.add_command(
            "Paste",
            func=lambda g: self._paste_nodes(),
        )

        # Quick ingredient shortcut on canvas root
        graph_menu.add_command(
            "Add Ingredient",
            func=lambda g: self._create_orphan_ingredient(),
        )

        # Node creation submenu
        add_menu = graph_menu.add_menu("Add Node")

        recipes_menu = add_menu.add_menu("Recipes")
        for kind, label in [
            (NodeKind.MODIFIED_RECIPE, "Modified Recipe -- change an existing in-game recipe"),
            (NodeKind.ADDED_RECIPE, "Added Recipe -- new recipe at a crafting path"),
            (NodeKind.ALIAS_RECIPE, "Alias Recipe -- clone and rename an existing recipe"),
            (NodeKind.CUSTOM_FOOD, "Custom Food -- food or drink with nutrition values"),
        ]:
            recipes_menu.add_command(
                label,
                func=self._make_create_callback(kind),
            )

        containers_menu = add_menu.add_menu("Containers")
        for kind, label in [
            (NodeKind.FABRICATOR, "Fabricator -- custom crafting station"),
            (NodeKind.CRAFTING_TAB, "Crafting Tab -- organize recipes into tabs"),
        ]:
            containers_menu.add_command(
                label,
                func=self._make_create_callback(kind),
            )

        other_menu = add_menu.add_menu("Other")
        for kind, label in [
            (NodeKind.CUSTOM_SIZE, "Custom Size -- change inventory slot size"),
            (NodeKind.MOVED_RECIPE, "Moved Recipe -- relocate an existing recipe"),
            (NodeKind.CUSTOM_BIO_FUEL, "Custom BioFuel -- set bioreactor energy value"),
            (NodeKind.CUSTOM_FRAGMENT_COUNT, "Custom Fragment Count -- change scan requirements"),
            (NodeKind.SPRITE, "Sprite -- assign an image to a node"),
        ]:
            other_menu.add_command(
                label,
                func=self._make_create_callback(kind),
            )

    def _on_toggle_selection(self, graph: NodeGraph, node: CraftGraphBaseNode) -> None:
        """Toggle the selection state of the right-clicked node."""
        node.set_selected(not node.selected())

    def _on_delete_ingredient(self, graph: NodeGraph, node: CraftGraphBaseNode) -> None:
        """Show a dialog to pick and delete an ingredient from this recipe."""
        model = node.model_ref
        if model is None:
            return
        ingredients = getattr(model, "ingredients", None)
        if not ingredients:
            self.statusBar().showMessage("No ingredients to delete")
            return

        # Build list labels: "ItemID x Required"
        labels = [f"{ing.item_id} x{ing.required}" for ing in ingredients]
        chosen, ok = QtWidgets.QInputDialog.getItem(
            self,
            "Delete Ingredient",
            "Select ingredient to remove:",
            labels,
            editable=False,
        )
        if not ok:
            return
        idx = labels.index(chosen)
        ingredients.pop(idx)

        # Disconnect the corresponding ingredient port if connected
        ing_ports = [p for p in node.input_ports() if p.name().startswith("ingredient_")]
        if idx < len(ing_ports):
            port = ing_ports[idx]
            for connected in port.connected_ports():
                port.disconnect_from(connected)

        # Resync the code editor, child count labels, and title
        self._on_model_changed()

    def _on_promote_ingredient(self, graph: NodeGraph, node: CraftGraphBaseNode) -> None:
        """Promote an ingredient to a full recipe node.

        Shows two dialogs: first to pick the ingredient, then to pick the
        recipe type. Creates a new recipe node with the ingredient's ItemID
        pre-filled.
        """
        model = node.model_ref
        if model is None:
            return
        ingredients = getattr(model, "ingredients", None)
        if not ingredients:
            self.statusBar().showMessage("No ingredients to promote")
            return

        # Step 1: pick ingredient
        labels = [f"{ing.item_id} x{ing.required}" for ing in ingredients]
        chosen, ok = QtWidgets.QInputDialog.getItem(
            self,
            "Promote Ingredient to Recipe",
            "Select ingredient to promote:",
            labels,
            editable=False,
        )
        if not ok:
            return
        idx = labels.index(chosen)
        item_id = ingredients[idx].item_id

        # Step 2: pick recipe type
        type_labels = [
            "Modified Recipe",
            "Added Recipe",
            "Alias Recipe",
            "Custom Food",
        ]
        type_chosen, ok = QtWidgets.QInputDialog.getItem(
            self,
            "Recipe Type",
            f"Create recipe type for '{item_id}':",
            type_labels,
            editable=False,
        )
        if not ok:
            return

        kind_map = {
            "Modified Recipe": NodeKind.MODIFIED_RECIPE,
            "Added Recipe": NodeKind.ADDED_RECIPE,
            "Alias Recipe": NodeKind.ALIAS_RECIPE,
            "Custom Food": NodeKind.CUSTOM_FOOD,
        }
        kind = kind_map[type_chosen]
        self._create_node_from_menu(kind, item_id=item_id)

    def _create_orphan_ingredient(self) -> None:
        """Create an OrphanIngredientNode at the cursor position.

        Opens a text input dialog for the ingredient ItemID.  The orphan
        node is visual-only (no model_ref) and has a muted grey style.
        """
        item_id, ok = QtWidgets.QInputDialog.getText(
            self,
            "Add Ingredient",
            "Ingredient ItemID:",
        )
        if not ok or not item_id.strip():
            return
        item_id = item_id.strip()

        tab = self._active_tab
        type_ = f"{IDENTIFIER}.{OrphanIngredientNode.__name__}"
        viewer = tab.graph.viewer()
        cursor_pos = viewer.mapFromGlobal(QtGui.QCursor.pos())
        scene_pos = viewer.mapToScene(cursor_pos)

        node = tab.graph.create_node(
            type_,
            name=item_id,
            pos=[scene_pos.x(), scene_pos.y()],
        )
        node.set_property("item_id", item_id)
        self.statusBar().showMessage(f"Created orphan ingredient: {item_id}")

    def _on_set_sprite(self, graph: NodeGraph, node: CraftGraphBaseNode) -> None:
        """Open a file dialog to pick a PNG sprite for the node."""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Sprite Image",
            "",
            "PNG Files (*.png)",
        )
        if not file_path:
            return
        path = Path(file_path)
        node.set_sprite(path)
        item_id = getattr(node.model_ref, "item_id", None)
        if not item_id:
            item_id = getattr(node.model_ref, "tab_id", None)
        if item_id:
            self._manual_sprites[item_id.lower()] = path

    def _on_clear_sprite(self, graph: NodeGraph, node: CraftGraphBaseNode) -> None:
        """Remove the sprite from a node and clear any manual override."""
        node.clear_sprite()
        item_id = getattr(node.model_ref, "item_id", None)
        if not item_id:
            item_id = getattr(node.model_ref, "tab_id", None)
        if item_id:
            self._manual_sprites.pop(item_id.lower(), None)

    def _make_create_callback(self, kind: NodeKind):  # type: ignore[no-untyped-def]
        """Return a callback that creates a node of the given kind.

        Each callback must be a separate closure so that ``kind`` is
        captured by value, not by reference.
        """

        def _callback(graph: NodeGraph) -> None:
            self._create_node_from_menu(kind)

        return _callback

    def _create_node_from_menu(
        self,
        kind: NodeKind,
        item_id: str | None = None,
    ) -> None:
        """Create a new node of the given kind at the cursor position.

        Also creates the corresponding model object and wires it into
        the active tab's parsed file so the code editor stays in sync.
        When *item_id* is given, the new node uses that ID instead of
        the default ``"NewItem"`` placeholder.
        """
        from craftgraph.models import (
            AddedRecipe,
            AliasRecipe,
            BlockType,
            CraftingTab,
            CustomBioFuel,
            CustomFabricator,
            CustomFood,
            CustomFragmentCount,
            CustomSize,
            ModifiedRecipe,
            MovedRecipe,
            ParsedFile,
        )

        tab = self._active_tab

        # Visual-only node types (not model-backed) get created directly
        if kind in (NodeKind.ORPHAN_INGREDIENT, NodeKind.SPRITE):
            node_cls = NODE_REGISTRY[kind]
            type_ = f"{IDENTIFIER}.{node_cls.__name__}"
            viewer = tab.graph.viewer()
            cursor_pos = viewer.mapFromGlobal(QtGui.QCursor.pos())
            scene_pos = viewer.mapToScene(cursor_pos)
            node = tab.graph.create_node(
                type_,
                name=item_id or node_cls.NODE_NAME,
                pos=[scene_pos.x(), scene_pos.y()],
            )
            if item_id and kind == NodeKind.ORPHAN_INGREDIENT:
                node.set_property("item_id", item_id)
            self._attach_node_completers(node)
            self.statusBar().showMessage(f"Created {node_cls.NODE_NAME}: {node.name()}")
            return

        kind_to_model: dict[NodeKind, tuple[type, BlockType, str]] = {
            NodeKind.MODIFIED_RECIPE: (
                ModifiedRecipe,
                BlockType.MODIFIED_RECIPES,
                "modified_recipes",
            ),
            NodeKind.ADDED_RECIPE: (
                AddedRecipe,
                BlockType.ADDED_RECIPES,
                "added_recipes",
            ),
            NodeKind.ALIAS_RECIPE: (
                AliasRecipe,
                BlockType.ALIAS_RECIPES,
                "alias_recipes",
            ),
            NodeKind.CUSTOM_FOOD: (
                CustomFood,
                BlockType.CUSTOM_FOODS,
                "custom_foods",
            ),
            NodeKind.FABRICATOR: (
                CustomFabricator,
                BlockType.CUSTOM_FABRICATORS,
                "custom_fabricators",
            ),
            NodeKind.CRAFTING_TAB: (
                CraftingTab,
                BlockType.CUSTOM_CRAFTING_TABS,
                "crafting_tabs",
            ),
            NodeKind.CUSTOM_SIZE: (
                CustomSize,
                BlockType.CUSTOM_SIZES,
                "custom_sizes",
            ),
            NodeKind.MOVED_RECIPE: (
                MovedRecipe,
                BlockType.MOVED_RECIPES,
                "moved_recipes",
            ),
            NodeKind.CUSTOM_BIO_FUEL: (
                CustomBioFuel,
                BlockType.CUSTOM_BIO_FUELS,
                "custom_bio_fuels",
            ),
            NodeKind.CUSTOM_FRAGMENT_COUNT: (
                CustomFragmentCount,
                BlockType.CUSTOM_FRAGMENT_COUNTS,
                "custom_fragment_counts",
            ),
        }

        model_cls, block_type, attr_name = kind_to_model[kind]

        # Block types that can nest inside a CustomFabricator entry.
        # Maps BlockType -> attribute name on the CustomFabricator model.
        fab_nestable: dict[BlockType, str] = {
            BlockType.CUSTOM_CRAFTING_TABS: "tabs",
            BlockType.ADDED_RECIPES: "added_recipes",
            BlockType.ALIAS_RECIPES: "alias_recipes",
            BlockType.MOVED_RECIPES: "moved_recipes",
            BlockType.CUSTOM_FOODS: "custom_foods",
        }

        # Determine whether this node should nest inside a fabricator
        nest_in_fab = False
        if tab.parsed_file is not None and tab.parsed_file.block_type is not None:
            existing_bt = tab.parsed_file.block_type
            if existing_bt != block_type:
                # CustomFabricators files allow nestable block types
                if existing_bt == BlockType.CUSTOM_FABRICATORS and block_type in fab_nestable:
                    nest_in_fab = True
                else:
                    existing_attr = {
                        BlockType.MODIFIED_RECIPES: "modified_recipes",
                        BlockType.ADDED_RECIPES: "added_recipes",
                        BlockType.ALIAS_RECIPES: "alias_recipes",
                        BlockType.CUSTOM_FOODS: "custom_foods",
                        BlockType.CUSTOM_CRAFTING_TABS: "crafting_tabs",
                        BlockType.CUSTOM_FABRICATORS: "custom_fabricators",
                        BlockType.MOVED_RECIPES: "moved_recipes",
                        BlockType.CUSTOM_SIZES: "custom_sizes",
                        BlockType.CUSTOM_BIO_FUELS: "custom_bio_fuels",
                        BlockType.CUSTOM_FRAGMENT_COUNTS: "custom_fragment_counts",
                    }[existing_bt]
                    if getattr(tab.parsed_file, existing_attr):
                        self.statusBar().showMessage(
                            f"Cannot add {block_type.value} to a "
                            f"{existing_bt.value} file -- CC3 requires "
                            f"one block type per file"
                        )
                        return
                    # Primary list is empty; safe to switch block type
                    tab.parsed_file.block_type = block_type

        if model_cls is CraftingTab:
            model = model_cls(tab_id=item_id or "NewTab")
        elif model_cls is CustomFabricator:
            model = model_cls(
                item_id=item_id or "NewFabricator",
                display_name=item_id or "New Fabricator",
            )
        else:
            model = model_cls(item_id=item_id or "NewItem")

        # Add to the active tab's parsed file
        if tab.parsed_file is None:
            tab.parsed_file = ParsedFile(
                source_path=self._source_path,
                block_type=block_type,
            )
        pf: ParsedFile = tab.parsed_file  # type: ignore[assignment]

        if nest_in_fab:
            # Append to the first fabricator's nested list
            fabs = pf.custom_fabricators
            if not fabs:
                self.statusBar().showMessage(
                    "No fabricator to nest into -- add a Fabricator first"
                )
                return
            target_fab = fabs[0]
            fab_attr = fab_nestable[block_type]
            getattr(target_fab, fab_attr).append(model)
        else:
            getattr(pf, attr_name).append(model)

        viewer = tab.graph.viewer()
        cursor_pos = viewer.mapFromGlobal(QtGui.QCursor.pos())
        scene_pos = viewer.mapToScene(cursor_pos)

        node_cls = NODE_REGISTRY[kind]
        type_ = f"{IDENTIFIER}.{node_cls.__name__}"
        node = tab.graph.create_node(
            type_,
            name=getattr(model, "item_id", None) or getattr(model, "tab_id", "Node"),
            pos=[scene_pos.x(), scene_pos.y()],
        )

        if hasattr(model, "item_id"):
            node.set_property("item_id", model.item_id)
        if hasattr(model, "tab_id"):
            node.set_property("tab_id", model.tab_id)
        if hasattr(model, "display_name") and model.display_name:
            node.set_property("display_name", model.display_name)

        node.model_ref = model
        tab.model_to_node[id(model)] = node
        self._attach_node_completers(node)

        if tab.ui_handler is not None:
            tab.ui_handler.register_node(node)

        self._update_code_editor_from_model()
        self._update_path_completions()

        self.statusBar().showMessage(f"Created {node_cls.NODE_NAME}: {node.name()}")

    # -- Autocomplete ---------------------------------------------------------

    # Widget names that should complete against TechType IDs.
    _ID_WIDGET_NAMES: frozenset[str] = frozenset(
        {
            "item_id",
            "tab_id",
        }
    )
    # Widget names that should complete against crafting-tree paths.
    _PATH_WIDGET_NAMES: frozenset[str] = frozenset(
        {
            "path",
            "old_path",
            "new_path",
        }
    )

    def _get_id_words(self) -> list[str]:
        """Return the cached, sorted list of vanilla + mod-compat TechType IDs."""
        if self._id_words is None:
            from craftgraph.vanilla_ids import load_mod_compat_ids, load_vanilla_ids

            self._id_words = sorted(
                load_vanilla_ids() | load_mod_compat_ids(),
                key=str.lower,
            )
        return self._id_words

    def _make_completer(
        self,
        words: list[str],
        parent: QtCore.QObject | None = None,
    ) -> QtWidgets.QCompleter:
        """Build a case-insensitive, substring-matching QCompleter."""
        completer = QtWidgets.QCompleter(words, parent or self)
        completer.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
        return completer

    def _setup_autocomplete_for(self, editor: CodeEditor) -> None:
        """Attach a QCompleter to the given code editor.

        TechType IDs are the default completion source.  Path completions
        are populated after recipe files are loaded.
        """
        editor.set_completer(self._make_completer(self._get_id_words()))

    def _attach_node_completers(self, node: CraftGraphBaseNode) -> None:
        """Wire the shared NodeCompletionPopup to text input widgets on *node*.

        ItemID / TabID fields get TechType ID completion.
        Path fields get crafting-tree path completion.
        Other text fields (display_name, tooltip, file_path) are left alone.

        Uses a standalone popup widget (NodeCompletionPopup) instead of
        QCompleter because node widgets live inside QGraphicsProxyWidget
        where QCompleter's popup has focus issues.
        """
        for name, widget in node.widgets().items():
            if widget.type_ != "LineEditNodeWidget":
                continue
            line_edit: QtWidgets.QLineEdit = widget.get_custom_widget()
            if name in self._ID_WIDGET_NAMES:
                self._node_popup.attach(line_edit, self._get_id_words())
            elif name in self._PATH_WIDGET_NAMES:
                self._node_popup.attach(line_edit, self._path_words)

    def _attach_completers_bulk(self, model_to_node: dict[int, CraftGraphBaseNode]) -> None:
        """Attach completers to all nodes in a model_to_node map (bulk load)."""
        for node in model_to_node.values():
            if isinstance(node, CraftGraphBaseNode):
                self._attach_node_completers(node)

    def _update_path_completions(self) -> None:
        """Extract all known paths from parsed files and update editors + nodes."""
        from craftgraph.models import ParsedFile

        paths: set[str] = {
            "Fabricator",
            "Workbench",
            "SeamothUpgrades",
            "MapRoomFunctionality",
            "CyclopsFabricator",
        }

        def _add_path(p: str) -> None:
            if not p:
                return
            paths.add(p)
            parts = p.split("/")
            for i in range(1, len(parts)):
                paths.add("/".join(parts[:i]))

        for file_tab in self._file_tabs:
            if file_tab.parsed_file is None:
                continue
            pf: ParsedFile = file_tab.parsed_file  # type: ignore[assignment]
            for r in pf.all_recipes:
                if hasattr(r, "path"):
                    _add_path(r.path)
            for ctab in pf.crafting_tabs:
                _add_path(ctab.parent_tab_path)
            for mr in pf.moved_recipes:
                _add_path(mr.old_path or "")
                _add_path(mr.new_path or "")
            for fab in pf.custom_fabricators:
                paths.add(fab.item_id)
                for ctab in fab.tabs:
                    _add_path(ctab.parent_tab_path)
                for r in fab.added_recipes + fab.alias_recipes + fab.custom_foods:
                    if hasattr(r, "path"):
                        _add_path(r.path)

        sorted_paths = sorted(paths, key=str.lower)
        self._path_words = sorted_paths

        for file_tab in self._file_tabs:
            file_tab.editor.set_path_completions(sorted_paths)
            # Refresh path completions on existing nodes
            for node in file_tab.model_to_node.values():
                if not isinstance(node, CraftGraphBaseNode):
                    continue
                for name, widget in node.widgets().items():
                    if name not in self._PATH_WIDGET_NAMES:
                        continue
                    if widget.type_ != "LineEditNodeWidget":
                        continue
                    line_edit: QtWidgets.QLineEdit = widget.get_custom_widget()
                    self._node_popup.update_words(line_edit, sorted_paths)

    # -- Sprite auto-assign ---------------------------------------------------

    def _apply_sprites_for(self, tab: FileTab) -> None:
        """Set sprites on all nodes in a tab that have a matching Assets/ PNG."""
        for node in tab.model_to_node.values():
            if not isinstance(node, CraftGraphBaseNode):
                continue
            item_id = getattr(node.model_ref, "item_id", None)
            if not item_id:
                item_id = getattr(node.model_ref, "tab_id", None)
            if not item_id:
                continue
            sprite_path = resolve_sprite(
                item_id,
                self._manual_sprites,
                self._sprite_lookup,
            )
            if sprite_path is not None:
                node.set_sprite(sprite_path)

    # -- Recipe loading -------------------------------------------------------

    def _tear_down_tabs(self) -> None:
        """Disconnect and remove all existing file tabs."""
        for tab in self._file_tabs:
            if tab.ui_handler is not None:
                tab.ui_handler.disconnect()
            if tab.parse_timer is not None:
                tab.parse_timer.stop()
            tab.graph.clear_session()

        self._file_tabs.clear()
        self._tab_bar.blockSignals(True)
        while self._tab_bar.count():
            self._tab_bar.removeTab(0)
        self._tab_bar.blockSignals(False)

        while self._graph_stack.count():
            w = self._graph_stack.widget(0)
            self._graph_stack.removeWidget(w)

        while self._editor_stack.count():
            w = self._editor_stack.widget(0)
            self._editor_stack.removeWidget(w)

    def _create_file_tab(
        self,
        parsed_file: object,
        saved_positions: dict[str, tuple[float, float]] | None = None,
    ) -> FileTab:
        """Build a complete FileTab for one ParsedFile.

        Args:
            parsed_file: The parsed recipe data.
            saved_positions: Optional user positions loaded from disk.
                When provided, these override the computed hierarchy layout.
        """
        from craftgraph.commands import EditHistory

        graph = NodeGraph()
        graph.set_acyclic(False)
        for cls in all_node_classes():
            graph.register_node(cls)
        self._setup_context_menus_for(graph)

        guard = SyncGuard()
        history = EditHistory(on_change=self._on_model_changed)

        initial_user_positions = dict(saved_positions) if saved_positions else {}

        with guard():
            model_to_node = populate_graph(graph, [parsed_file], edit_history=history)
            connect_hierarchy(graph, [parsed_file], model_to_node)
            connect_ingredients(graph, [parsed_file], model_to_node)
            positions = compute_hierarchy_layout([parsed_file], model_to_node)
            overlay_user_positions(positions, initial_user_positions, model_to_node)
            apply_layout(positions, model_to_node)
            cycle_count = highlight_cycle_edges(graph, [parsed_file], model_to_node)
            update_child_count_labels(model_to_node)
            # NodeGraphQt defaults create_node(selected=True); clear to
            # avoid accidental bulk deletion of newly-loaded nodes.
            graph.clear_selection()

        self._attach_completers_bulk(model_to_node)

        editor = CodeEditor()
        EasyMarkupHighlighter(editor.document())
        self._setup_autocomplete_for(editor)

        # Per-tab debounce timer
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(300)

        tab = FileTab(
            parsed_file=parsed_file,
            graph=graph,
            editor=editor,
            history=history,
            ui_handler=None,
            sync_guard=guard,
            model_to_node=model_to_node,
            parse_timer=timer,
            cycle_count=cycle_count,
            user_positions=initial_user_positions,
        )

        # Wire code editor -> model re-parse for this tab
        def on_text_changed(_tab: FileTab = tab) -> None:
            if _tab.sync_guard.active:
                return
            if _tab.parse_timer is not None:
                _tab.parse_timer.start()

        def apply_text(_tab: FileTab = tab) -> None:
            self._apply_code_editor_text_for(_tab)

        editor.textChanged.connect(on_text_changed)
        timer.timeout.connect(apply_text)

        # Serialize model into editor
        with guard():
            editor.setPlainText(serialize_file(parsed_file))

        # Wire node selection -> code editor scroll
        def on_node_selected(node: object, _tab: FileTab = tab) -> None:
            self._scroll_editor_to_node(node, _tab)

        graph.node_selected.connect(on_node_selected)

        # Wire node drag -> save user positions
        def on_nodes_moved(moved: dict, _tab: FileTab = tab) -> None:
            for node_item in moved:
                node = _tab.graph.get_node_by_id(node_item.id)
                if node is None:
                    continue
                # Variable nodes use UUID-based keys
                if hasattr(node, "_var_uuid"):
                    key = f"VarNode:{node._var_uuid}"
                elif hasattr(node, "model_ref") and node.model_ref is not None:
                    key = model_position_key(node.model_ref)
                else:
                    continue
                x, y = node.pos()
                _tab.user_positions[key] = (x, y)

        graph.viewer().moved_nodes.connect(on_nodes_moved)

        # Wire UI handler
        tab.ui_handler = UIToModelHandler(
            graph=graph,
            history=history,
            guard=guard,
            parsed_files=[parsed_file],
            model_to_node=model_to_node,
            on_cycle_rejected=self._on_cycle_rejected,
        )

        return tab

    def load_recipes(self, path: Path) -> None:
        """Parse recipes from *path* and populate per-file tabs."""
        from craftgraph.parser import MappingError, ParseError, parse_directory, parse_file

        self.statusBar().showMessage(f"Parsing {path}...")

        try:
            parsed_files = [parse_file(path)] if path.is_file() else parse_directory(path)
        except (ParseError, MappingError, FileNotFoundError, NotADirectoryError) as exc:
            self.statusBar().showMessage(f"Parse error: {exc}")
            return

        if not parsed_files:
            self.statusBar().showMessage("No recipe files found.")
            return

        self._tear_down_tabs()
        self._source_path = path

        # Scan for sprite assets
        recipe_dir = path.parent if path.is_file() else path
        self._sprite_lookup = scan_assets_dir(recipe_dir)

        # Load persisted node positions from sidecar file
        layout_file = layout_path_for(path)
        disk_positions = load_layout(layout_file) or {}

        # Create one FileTab per parsed file
        for pf in parsed_files:
            tab_key = pf.source_path.stem
            tab_saved = disk_positions.get(tab_key, {})
            # Convert [x, y] lists to (x, y) tuples for in-memory use
            saved_pos = {k: (v[0], v[1]) for k, v in tab_saved.items()}
            tab = self._create_file_tab(pf, saved_positions=saved_pos)
            self._file_tabs.append(tab)

            self._graph_stack.addWidget(tab.graph.widget)
            self._editor_stack.addWidget(tab.editor)
            self._tab_bar.addTab(pf.source_path.stem)

        # Apply sprites across all tabs
        for tab in self._file_tabs:
            self._apply_sprites_for(tab)

        self._update_path_completions()

        # Activate first tab
        self._tab_bar.setCurrentIndex(0)
        self._on_tab_changed(0)

        total_nodes = sum(len(t.model_to_node) for t in self._file_tabs)
        total_cycles = sum(t.cycle_count for t in self._file_tabs)
        cycle_msg = f", {total_cycles} cycle(s)!" if total_cycles else ", no cycles"
        self.statusBar().showMessage(
            f"Loaded {total_nodes} nodes from {len(parsed_files)} file(s){cycle_msg}"
        )


# ---------------------------------------------------------------------------
# Launch helper
# ---------------------------------------------------------------------------


def launch_qt_gui(recipe_path: Path | None = None) -> None:
    """Create the QApplication and show the CraftGraph main window.

    Called by the ``craftgraph qt-gui`` CLI command.
    """
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    window = CraftGraphWindow()

    if recipe_path is not None:
        window.load_recipes(recipe_path)

    window.show()
    app.exec()
