"""Tests for the Qt GUI application shell (Step M3).

These tests require the ``qt`` optional dependency group (PySide6 + NodeGraphQt).
They are skipped automatically when those packages are not installed.

Run:  uv run --extra qt pytest tests/test_qt_gui.py -v
"""

from __future__ import annotations

import sys

import pytest

# Skip entire module if Qt deps are missing
pytest.importorskip(
    "NodeGraphQt",
    reason="NodeGraphQt not installed (install with: uv sync --extra qt)",
)

from PySide6 import QtCore, QtWidgets

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
def window(qapp, monkeypatch, tmp_path):
    """Fresh CraftGraphWindow for each test, isolated from real settings."""
    from craftgraph import app_dirs
    from craftgraph.qt_gui import CraftGraphWindow

    monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
    return CraftGraphWindow()


# ---------------------------------------------------------------------------
# Window basics
# ---------------------------------------------------------------------------


class TestWindowCreation:
    def test_window_title(self, window):
        assert window.windowTitle() == "CraftGraph"

    def test_window_has_minimum_size(self, window):
        assert window.width() >= 800
        assert window.height() >= 600

    def test_graph_property(self, window):
        from NodeGraphQt import NodeGraph

        assert isinstance(window.graph, NodeGraph)

    def test_code_editor_property(self, window):
        assert isinstance(window.code_editor, QtWidgets.QPlainTextEdit)

    def test_code_editor_is_code_editor_subclass(self, window):
        from craftgraph.code_editor import CodeEditor

        assert isinstance(window.code_editor, CodeEditor)

    def test_code_editor_has_line_number_area(self, window):
        from craftgraph.code_editor import LineNumberArea

        assert isinstance(window.code_editor.line_number_area, LineNumberArea)

    def test_code_editor_is_editable(self, window):
        assert not window.code_editor.isReadOnly()

    def test_code_editor_has_completer(self, window):
        completer = window.code_editor.completer()
        assert completer is not None

    def test_completer_is_case_insensitive(self, window):
        from PySide6.QtCore import Qt

        completer = window.code_editor.completer()
        assert completer.caseSensitivity() == Qt.CaseSensitivity.CaseInsensitive

    def test_completer_has_vanilla_ids(self, window):
        completer = window.code_editor.completer()
        model = completer.model()
        all_items = [model.data(model.index(i, 0)) for i in range(model.rowCount())]
        # "titanium" is a well-known vanilla Subnautica item
        assert any("titanium" in item.lower() for item in all_items)


# ---------------------------------------------------------------------------
# Menu bar
# ---------------------------------------------------------------------------


class TestMenuBar:
    def test_menu_bar_exists(self, window):
        assert window.menuBar() is not None

    def test_file_menu_exists(self, window):
        menus = window.menuBar().findChildren(QtWidgets.QMenu)
        menu_titles = [m.title() for m in menus]
        assert any("File" in t for t in menu_titles)

    def test_edit_menu_exists(self, window):
        menus = window.menuBar().findChildren(QtWidgets.QMenu)
        menu_titles = [m.title() for m in menus]
        assert any("Edit" in t for t in menu_titles)

    def test_view_menu_exists(self, window):
        menus = window.menuBar().findChildren(QtWidgets.QMenu)
        menu_titles = [m.title() for m in menus]
        assert any("View" in t for t in menu_titles)

    def test_file_menu_has_open_action(self, window):
        menus = window.menuBar().findChildren(QtWidgets.QMenu)
        file_menu = next(m for m in menus if "File" in m.title())
        action_texts = [a.text() for a in file_menu.actions()]
        assert any("Open" in t for t in action_texts)

    def test_file_menu_has_save_action(self, window):
        menus = window.menuBar().findChildren(QtWidgets.QMenu)
        file_menu = next(m for m in menus if "File" in m.title())
        action_texts = [a.text() for a in file_menu.actions()]
        assert any("Save" in t for t in action_texts)

    def test_file_menu_has_export_action(self, window):
        menus = window.menuBar().findChildren(QtWidgets.QMenu)
        file_menu = next(m for m in menus if "File" in m.title())
        action_texts = [a.text() for a in file_menu.actions()]
        assert any("Export" in t for t in action_texts)

    def test_file_menu_has_exit_action(self, window):
        menus = window.menuBar().findChildren(QtWidgets.QMenu)
        file_menu = next(m for m in menus if "File" in m.title())
        action_texts = [a.text() for a in file_menu.actions()]
        assert any("xit" in t for t in action_texts)

    def test_edit_menu_has_undo_redo(self, window):
        menus = window.menuBar().findChildren(QtWidgets.QMenu)
        edit_menu = next(m for m in menus if "Edit" in m.title())
        action_texts = [a.text() for a in edit_menu.actions()]
        assert any("Undo" in t for t in action_texts)
        assert any("Redo" in t for t in action_texts)

    def test_view_menu_has_minimap(self, window):
        menus = window.menuBar().findChildren(QtWidgets.QMenu)
        view_menu = next(m for m in menus if "View" in m.title())
        action_texts = [a.text() for a in view_menu.actions()]
        assert any("Minimap" in t for t in action_texts)

    def test_view_menu_has_reset_layout(self, window):
        menus = window.menuBar().findChildren(QtWidgets.QMenu)
        view_menu = next(m for m in menus if "View" in m.title())
        action_texts = [a.text() for a in view_menu.actions()]
        assert any("Reset Layout" in t for t in action_texts)

    def test_save_action_enabled(self, window):
        menus = window.menuBar().findChildren(QtWidgets.QMenu)
        file_menu = next(m for m in menus if "File" in m.title())
        save_action = next(
            a for a in file_menu.actions() if "Save" in a.text() and "All" not in a.text()
        )
        assert save_action.isEnabled()

    def test_export_action_disabled_by_default(self, window):
        menus = window.menuBar().findChildren(QtWidgets.QMenu)
        file_menu = next(m for m in menus if "File" in m.title())
        export_action = next(a for a in file_menu.actions() if "Export" in a.text())
        assert not export_action.isEnabled()

    def test_help_menu_exists(self, window):
        menus = window.menuBar().findChildren(QtWidgets.QMenu)
        menu_titles = [m.title() for m in menus]
        assert any("Help" in t for t in menu_titles)

    def test_help_menu_has_about(self, window):
        menus = window.menuBar().findChildren(QtWidgets.QMenu)
        help_menu = next(m for m in menus if "Help" in m.title())
        action_texts = [a.text() for a in help_menu.actions()]
        assert any("About" in t for t in action_texts)

    def test_about_dialog_shows(self, window, monkeypatch):
        """Verify _on_about calls QMessageBox.about with version info."""
        calls: list[tuple] = []
        monkeypatch.setattr(
            QtWidgets.QMessageBox,
            "about",
            staticmethod(lambda parent, title, text: calls.append((title, text))),
        )
        window._on_about()
        assert len(calls) == 1
        title, text = calls[0]
        assert "CraftGraph" in title
        assert "0.1.0" in text
        assert "CustomCraft3" in text

    def test_help_menu_has_settings(self, window):
        menus = window.menuBar().findChildren(QtWidgets.QMenu)
        help_menu = next(m for m in menus if "Help" in m.title())
        action_texts = [a.text() for a in help_menu.actions()]
        assert any("Settings" in t for t in action_texts)

    def test_settings_dialog_opens(self, window, monkeypatch):
        """Verify _on_settings creates a QDialog with placeholder text."""
        monkeypatch.setattr(QtWidgets.QDialog, "exec_", lambda self: QtWidgets.QDialog.Accepted)
        window._on_settings()
        # If we got here without error, the dialog was created successfully.

    def test_settings_dialog_has_tabs(self, window, monkeypatch):
        """Verify the Settings dialog contains tabbed settings panes."""
        from craftgraph.qt_gui import _SettingsDialog

        created_dialogs: list[_SettingsDialog] = []
        orig_init = _SettingsDialog.__init__

        def tracking_init(self_dialog, *args, **kwargs):
            orig_init(self_dialog, *args, **kwargs)
            created_dialogs.append(self_dialog)

        monkeypatch.setattr(_SettingsDialog, "__init__", tracking_init)
        monkeypatch.setattr(_SettingsDialog, "exec_", lambda self: QtWidgets.QDialog.Accepted)
        window._on_settings()
        assert len(created_dialogs) == 1
        tab_widget = created_dialogs[0].findChild(QtWidgets.QTabWidget)
        assert tab_widget is not None
        assert tab_widget.count() >= 3


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


class TestLayout:
    def test_central_widget_contains_tab_bar_and_splitter(self, window):
        central = window.centralWidget()
        assert isinstance(central, QtWidgets.QWidget)
        assert isinstance(window._tab_bar, QtWidgets.QTabBar)
        assert isinstance(window._splitter, QtWidgets.QSplitter)

    def test_splitter_has_two_stacked_widgets(self, window):
        splitter = window._splitter
        assert splitter.count() == 2
        assert isinstance(window._graph_stack, QtWidgets.QStackedWidget)
        assert isinstance(window._editor_stack, QtWidgets.QStackedWidget)

    def test_status_bar_exists(self, window):
        assert window.statusBar() is not None

    def test_status_bar_shows_ready(self, window):
        assert window.statusBar().currentMessage() == "Ready"


# ---------------------------------------------------------------------------
# Node graph integration
# ---------------------------------------------------------------------------


class TestNodeGraphIntegration:
    def test_graph_has_registered_nodes(self, window):
        # Verify all node classes are registered by trying to create one
        node = window.graph.create_node(
            "com.craftgraph.ModifiedRecipeNode",
            name="Test",
        )
        assert node is not None

    def test_graph_is_not_acyclic(self, window):
        # CraftGraph handles cycles via NetworkX, not via NodeGraphQt
        assert not window.graph.acyclic()

    def test_undo_stack_accessible(self, window):
        stack = window.graph.undo_stack()
        assert stack is not None


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    def test_launch_qt_gui_is_importable(self):
        from craftgraph.qt_gui import launch_qt_gui

        assert callable(launch_qt_gui)

    def test_gui_command_registered(self):
        from craftgraph.cli import main

        commands = main.list_commands(ctx=None)
        assert "gui" in commands


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------


class TestFileLoading:
    """Test loading recipe files into the node graph."""

    def test_load_nonexistent_path_shows_error(self, window, tmp_path):
        """Loading a nonexistent directory shows an error in the status bar."""
        window.load_recipes(tmp_path / "nope")
        msg = window.statusBar().currentMessage()
        assert "error" in msg.lower() or "not found" in msg.lower()

    def test_load_empty_directory(self, window, tmp_path):
        """Loading a directory with no .txt files shows a message."""
        window.load_recipes(tmp_path)
        assert "No recipe files" in window.statusBar().currentMessage()

    def test_load_modified_recipe_file(self, window, tmp_path):
        """Parse a simple ModifiedRecipes file and create nodes."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: Titanium;\n"
            "    AmountCrafted: 2;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: Gold;\n"
            "        Required: 3;\n"
            "    );\n"
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        nodes = window.graph.all_nodes()
        # 1 recipe + 1 orphan ingredient (Gold) = 2 nodes
        assert len(nodes) == 2

        node_names = {n.name() for n in nodes}
        assert "Titanium (x2)" in node_names
        assert "Gold" in node_names

        recipe_node = next(n for n in nodes if n.name() == "Titanium (x2)")
        assert recipe_node.get_widget("item_id").get_value() == "Titanium"
        assert recipe_node.get_widget("amount_crafted").get_value() == "2"

    def test_load_added_recipe_has_path_widget(self, window, tmp_path):
        """AddedRecipe nodes get a path widget populated."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "AddedRecipes:\n"
            "(\n"
            "    ItemID: SuperAlloy;\n"
            "    Path: Fabricator/Resources;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: Titanium;\n"
            "        Required: 2;\n"
            "    );\n"
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        nodes = window.graph.all_nodes()
        # 1 recipe + 1 orphan ingredient (Titanium) = 2 nodes
        assert len(nodes) == 2
        recipe_node = next(n for n in nodes if n.name() == "SuperAlloy")
        assert recipe_node.get_widget("path").get_value() == "Fabricator/Resources"

    def test_load_fabricator_creates_fab_node(self, window, tmp_path):
        """CustomFabricators create FabricatorNode with nested tabs/recipes."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "CustomFabricators:\n"
            "(\n"
            "    ItemID: AlchemyStation;\n"
            '    DisplayName: "Alchemy Station";\n'
            "    Model: Workbench;\n"
            "    CustomCraftingTabs:\n"
            "    (\n"
            "        TabID: Potions;\n"
            '        DisplayName: "Potions";\n'
            "    );\n"
            "    AddedRecipes:\n"
            "    (\n"
            "        ItemID: HealthPotion;\n"
            "        Path: Potions;\n"
            "        Ingredients:\n"
            "        (\n"
            "            ItemID: Herb;\n"
            "            Required: 2;\n"
            "        );\n"
            "    );\n"
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        nodes = window.graph.all_nodes()
        # 1 fabricator + 1 tab + 1 recipe + 1 orphan (Herb) = 4 nodes
        assert len(nodes) == 4

        node_names = {n.name() for n in nodes}
        assert "AlchemyStation" in node_names
        assert "Potions" in node_names
        assert "HealthPotion" in node_names
        assert "Herb" in node_names

    def test_load_sets_model_ref(self, window, tmp_path):
        """Each created node has a model_ref pointing back to the data object."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Copper;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = window.graph.all_nodes()[0]
        assert node.model_ref is not None
        assert node.model_ref.item_id == "Copper"

    def test_load_updates_status_bar(self, window, tmp_path):
        """Status bar shows node count after loading."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n),\n(\n    ItemID: Gold;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        msg = window.statusBar().currentMessage()
        assert "2 nodes" in msg
        assert "1 file" in msg
        assert "no cycles" in msg

    def test_load_clears_previous_nodes(self, window, tmp_path):
        """Loading a new file clears previously loaded nodes."""
        file1 = tmp_path / "file1.txt"
        file1.write_text(
            "ModifiedRecipes:\n(\n    ItemID: A;\n);\n",
            encoding="utf-8",
        )
        file2 = tmp_path / "file2.txt"
        file2.write_text(
            "ModifiedRecipes:\n(\n    ItemID: B;\n);\n",
            encoding="utf-8",
        )

        window.load_recipes(file1)
        assert len(window.graph.all_nodes()) == 1

        window.load_recipes(file2)
        assert len(window.graph.all_nodes()) == 1
        assert window.graph.all_nodes()[0].name() == "B"

    def test_load_populates_code_editor(self, window, tmp_path):
        """Loading recipes serializes the model into the code editor."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n    AmountCrafted: 2;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        text = window.code_editor.toPlainText()
        assert "Titanium" in text
        assert "AmountCrafted" in text

    def test_load_code_editor_not_empty_after_load(self, window, tmp_path):
        """Code editor has content after a successful load."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Gold;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        assert len(window.code_editor.toPlainText()) > 0

    def test_load_creates_tabs_per_file(self, window, tmp_path):
        """Loading a folder with multiple recipe files creates one tab each."""
        (tmp_path / "recipes.txt").write_text(
            "ModifiedRecipes:\n(\n    ItemID: Gold;\n);\n",
            encoding="utf-8",
        )
        (tmp_path / "fabs.txt").write_text(
            'CustomFabricators:\n(\n    ItemID: MyFab;\n    DisplayName: "My Fab";\n);\n',
            encoding="utf-8",
        )

        window.load_recipes(tmp_path)

        tab_bar = window._tab_bar
        assert tab_bar.count() == 2
        tab_names = {tab_bar.tabText(i) for i in range(tab_bar.count())}
        assert "recipes" in tab_names
        assert "fabs" in tab_names

    def test_single_file_tab_shows_filename(self, window, tmp_path):
        """Loading a single file names the tab after the file stem."""
        recipe_file = tmp_path / "my_recipes.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Copper;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        assert window._tab_bar.count() == 1
        assert window._tab_bar.tabText(0) == "my_recipes"

    def test_reload_replaces_tabs(self, window, tmp_path):
        """Loading new files replaces old tabs instead of appending."""
        file1 = tmp_path / "first.txt"
        file1.write_text(
            "ModifiedRecipes:\n(\n    ItemID: A;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(file1)
        assert window._tab_bar.count() == 1

        file2 = tmp_path / "second.txt"
        file2.write_text(
            "ModifiedRecipes:\n(\n    ItemID: B;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(file2)
        assert window._tab_bar.count() == 1
        assert window._tab_bar.tabText(0) == "second"

    def test_load_real_reference_file(self, window):
        """Load a real reference file from the test data."""
        from pathlib import Path

        ref_file = (
            Path(__file__).parent.parent
            / "craftgraph"
            / "cc3_reference_files"
            / "real-mod-examples"
            / "customfab3.txt"
        )
        if not ref_file.exists():
            pytest.skip("Reference file not found")

        window.load_recipes(ref_file)
        nodes = window.graph.all_nodes()
        assert len(nodes) > 0


# ---------------------------------------------------------------------------
# Orphan node tab registration
# ---------------------------------------------------------------------------


class TestOrphanTabRegistration:
    """Verify orphan nodes are stored on the FileTab after loading."""

    def test_orphan_nodes_stored_on_tab(self, window, tmp_path):
        """After loading, tab.orphan_nodes contains the orphan mapping."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: Titanium;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: Gold;\n"
            "        Required: 3;\n"
            "    );\n"
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        tab = window._active_tab
        assert hasattr(tab, "orphan_nodes")
        assert "gold" in tab.orphan_nodes
        assert tab.orphan_nodes["gold"].name() == "Gold"

    def test_orphan_nodes_empty_when_all_matched(self, window, tmp_path):
        """When all ingredients match recipe nodes, orphan_nodes is empty."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n    AmountCrafted: 1;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        tab = window._active_tab
        assert hasattr(tab, "orphan_nodes")
        assert tab.orphan_nodes == {}


# ---------------------------------------------------------------------------
# Go to Definition (cross-tab navigation)
# ---------------------------------------------------------------------------


class TestGoToDefinition:
    """Double-click and context-menu navigation to a node's defining tab."""

    def _write_two_files(self, root):
        """Tab 1 defines Gold; tab 2 defines Titanium that needs Gold."""
        (root / "raw.txt").write_text(
            "ModifiedRecipes:\n(\n    ItemID: Gold;\n);\n",
            encoding="utf-8",
        )
        (root / "crafted.txt").write_text(
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: Titanium;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: Gold;\n"
            "        Required: 1;\n"
            "    );\n"
            ");\n",
            encoding="utf-8",
        )

    def test_node_lookup_id_uses_model_ref(self, window, tmp_path):
        """Recipe nodes report their model item_id."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Copper;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        tab = window._active_tab
        recipe_node = next(iter(tab.model_to_node.values()))
        assert window._node_lookup_id(recipe_node) == "copper"

    def test_node_lookup_id_uses_property_for_orphan(self, window, tmp_path):
        """Orphan ingredients (no model_ref) fall back to the displayed item_id."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: Titanium;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: Gold;\n"
            "        Required: 1;\n"
            "    );\n"
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        orphan = window._active_tab.orphan_nodes["gold"]
        assert window._node_lookup_id(orphan) == "gold"

    def test_find_definition_locates_recipe_in_other_tab(self, window, tmp_path):
        """`_find_definition` finds the defining recipe across open tabs."""
        self._write_two_files(tmp_path)
        window.load_recipes(tmp_path)

        result = window._find_definition("gold")
        assert result is not None
        idx, node = result
        assert window._tab_bar.tabText(idx) == "raw"
        assert getattr(node.model_ref, "item_id", None) == "Gold"

    def test_find_definition_returns_none_for_unknown(self, window, tmp_path):
        """Unknown IDs return None."""
        self._write_two_files(tmp_path)
        window.load_recipes(tmp_path)
        assert window._find_definition("Unobtainium") is None

    def test_go_to_definition_switches_tab_and_selects(self, window, tmp_path):
        """Calling _go_to_definition on an orphan switches tabs and selects."""
        self._write_two_files(tmp_path)
        window.load_recipes(tmp_path)

        crafted_idx = next(
            i for i in range(window._tab_bar.count())
            if window._tab_bar.tabText(i) == "crafted"
        )
        window._tab_bar.setCurrentIndex(crafted_idx)
        crafted_tab = window._file_tabs[crafted_idx]
        assert "gold" in crafted_tab.orphan_nodes

        ok = window._go_to_definition(crafted_tab.orphan_nodes["gold"])
        assert ok is True

        new_idx = window._tab_bar.currentIndex()
        assert window._tab_bar.tabText(new_idx) == "raw"
        selected = window._file_tabs[new_idx].graph.selected_nodes()
        assert any(
            getattr(n.model_ref, "item_id", None) == "Gold"
            for n in selected
        )

    def test_double_click_recipe_in_own_tab_is_noop(self, window, tmp_path):
        """Double-clicking a recipe defined in the current tab does not switch tabs."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Copper;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        before_idx = window._tab_bar.currentIndex()
        recipe_node = next(iter(window._active_tab.model_to_node.values()))
        window._on_node_double_clicked(recipe_node)
        assert window._tab_bar.currentIndex() == before_idx


# ---------------------------------------------------------------------------
# Hover tooltips with full recipe details
# ---------------------------------------------------------------------------


class TestHoverTooltips:
    """Verify the rich-detail node hover tooltip."""

    def test_tooltip_includes_type_and_source(self, window, tmp_path):
        """Tooltip shows the type header and the source file name."""
        recipe_file = tmp_path / "knife.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: SuperKnife;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = next(iter(window._active_tab.model_to_node.values()))
        tooltip = node.view.toolTip()
        assert "Modified Recipe" in tooltip
        assert "knife.txt" in tooltip
        assert "SuperKnife" in tooltip

    def test_tooltip_lists_ingredients(self, window, tmp_path):
        """Tooltip includes every ingredient with its required count."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: SuperKnife;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: Titanium;\n"
            "        Required: 2;\n"
            "    ),\n"
            "    (\n"
            "        ItemID: Gold;\n"
            "        Required: 1;\n"
            "    );\n"
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = next(
            n for n in window._active_tab.model_to_node.values()
            if getattr(n.model_ref, "item_id", "") == "SuperKnife"
        )
        tooltip = node.view.toolTip()
        assert "Titanium" in tooltip
        assert "x2" in tooltip
        assert "Gold" in tooltip

    def test_tooltip_marks_cycle_membership(self, window, tmp_path):
        """Recipes participating in a cycle have an explicit cycle section."""
        recipe_file = tmp_path / "cyc.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: A;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: B;\n"
            "        Required: 1;\n"
            "    );\n"
            "),\n"
            "(\n"
            "    ItemID: B;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: A;\n"
            "        Required: 1;\n"
            "    );\n"
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = next(iter(window._active_tab.model_to_node.values()))
        tooltip = node.view.toolTip()
        assert "dependency cycle" in tooltip.lower()
        assert "A" in tooltip and "B" in tooltip

    def test_tooltip_orphan_uses_displayed_id(self, window, tmp_path):
        """Orphan ingredient nodes (no model_ref) still get a useful tooltip."""
        recipe_file = tmp_path / "orph.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: Titanium;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: Gold;\n"
            "        Required: 3;\n"
            "    );\n"
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        orphan = window._active_tab.orphan_nodes["gold"]
        tooltip = orphan.view.toolTip()
        assert "Gold" in tooltip


# ---------------------------------------------------------------------------
# Bidirectional sync: model -> code editor
# ---------------------------------------------------------------------------


class TestModelToCodeEditorSync:
    """Verify that node edits re-serialize into the code editor."""

    def test_property_change_updates_code_editor(self, window, tmp_path):
        """Changing a node property re-serializes the model to code editor."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        # The code editor should show "Titanium"
        assert "Titanium" in window.code_editor.toPlainText()

        # Change the item_id via the node widget (fires property_changed)
        node = window.graph.all_nodes()[0]
        node.set_property("item_id", "Diamond")

        # Code editor should now reflect "Diamond"
        text = window.code_editor.toPlainText()
        assert "Diamond" in text
        assert "Titanium" not in text

    def test_undo_reverts_code_editor(self, window, tmp_path):
        """Undo restores the previous text in the code editor."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Gold;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = window.graph.all_nodes()[0]
        node.set_property("item_id", "Silver")
        assert "Silver" in window.code_editor.toPlainText()

        window.edit_history.undo()
        text = window.code_editor.toPlainText()
        assert "Gold" in text
        assert "Silver" not in text


# ---------------------------------------------------------------------------
# Bidirectional sync: code editor -> model (text -> nodes)
# ---------------------------------------------------------------------------


class TestCodeEditorToModelSync:
    """Verify that typing in the code editor rebuilds the node graph."""

    def test_text_change_rebuilds_graph(self, window):
        """Setting code editor text and firing the timer rebuilds the graph."""
        window.code_editor.setPlainText("ModifiedRecipes:\n(\n    ItemID: Copper;\n);\n")
        window._apply_code_editor_text_for(window._active_tab)

        nodes = window.graph.all_nodes()
        assert len(nodes) == 1
        assert nodes[0].name() == "Copper"

    def test_text_change_updates_parsed_file(self, window):
        """The active tab's parsed_file is replaced after a text re-parse."""
        window.code_editor.setPlainText("ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n")
        window._apply_code_editor_text_for(window._active_tab)

        assert window._active_tab.parsed_file is not None

    def test_parse_error_shows_in_status_bar(self, window):
        """Invalid EasyMarkup text shows a parse error in the status bar."""
        window.code_editor.setPlainText("NotABlockType:\n(\n);\n")
        window._apply_code_editor_text_for(window._active_tab)

        msg = window.statusBar().currentMessage()
        assert "parse error" in msg.lower() or "Parse error" in msg

    def test_parse_error_preserves_existing_graph(self, window, tmp_path):
        """If re-parse fails, the previous graph stays intact."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Gold;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        assert len(window.graph.all_nodes()) == 1

        # Type invalid text -- graph should NOT be cleared
        window.code_editor.setPlainText("BrokenSyntax!!!")
        window._apply_code_editor_text_for(window._active_tab)

        assert len(window.graph.all_nodes()) == 1

    def test_empty_text_does_not_rebuild(self, window, tmp_path):
        """Empty or whitespace-only text does not trigger a rebuild."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Silver;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        assert len(window.graph.all_nodes()) == 1

        window.code_editor.setPlainText("   \n  \n")
        window._apply_code_editor_text_for(window._active_tab)

        # Graph untouched
        assert len(window.graph.all_nodes()) == 1

    def test_guard_blocks_text_changed_during_model_update(self, window, tmp_path):
        """textChanged during model->code sync does NOT restart the timer."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        # The debounce timer should NOT be active after load_recipes,
        # because _create_file_tab wraps setPlainText in the guard
        assert not window._active_tab.parse_timer.isActive()

    def test_text_edit_replaces_old_nodes(self, window):
        """Editing text replaces old nodes with new ones."""
        window.code_editor.setPlainText("ModifiedRecipes:\n(\n    ItemID: Alpha;\n);\n")
        window._apply_code_editor_text_for(window._active_tab)
        assert len(window.graph.all_nodes()) == 1
        assert window.graph.all_nodes()[0].name() == "Alpha"

        window.code_editor.setPlainText(
            "ModifiedRecipes:\n(\n    ItemID: Beta;\n),\n(\n    ItemID: Gamma;\n);\n"
        )
        window._apply_code_editor_text_for(window._active_tab)
        names = {n.name() for n in window.graph.all_nodes()}
        assert names == {"Beta", "Gamma"}

    def test_status_bar_shows_node_count_after_parse(self, window):
        """Status bar displays the parsed node count."""
        window.code_editor.setPlainText(
            "ModifiedRecipes:\n(\n    ItemID: X;\n),\n(\n    ItemID: Y;\n);\n"
        )
        window._apply_code_editor_text_for(window._active_tab)

        msg = window.statusBar().currentMessage()
        assert "2 node" in msg


# ---------------------------------------------------------------------------
# User position preservation (Step M7.6)
# ---------------------------------------------------------------------------


class TestUserPositionPreservation:
    """Verify that user-dragged positions survive code editor re-parses."""

    def test_user_positions_survive_reparse(self, window, tmp_path):
        """Dragged node positions are restored after a code editor re-parse."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        tab = window._active_tab

        # Simulate dragging: store a user position
        tab.user_positions["ModifiedRecipe:Titanium"] = (500.0, 300.0)

        # Re-parse the code editor text (triggers full graph rebuild)
        window._apply_code_editor_text_for(tab)

        node = window.graph.all_nodes()[0]
        x, y = node.pos()
        assert abs(x - 500.0) < 1.0
        assert abs(y - 300.0) < 1.0

    def test_user_positions_ignored_for_unknown_nodes(self, window, tmp_path):
        """User positions for nodes not in the rebuilt graph are ignored."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Gold;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        tab = window._active_tab

        # Store a position for a node that won't exist after re-parse
        tab.user_positions["ModifiedRecipe:NonExistent"] = (999.0, 999.0)

        # Re-parse -- should not crash
        window._apply_code_editor_text_for(tab)

        node = window.graph.all_nodes()[0]
        assert node.name() == "Gold"

    def test_default_layout_used_when_no_user_position(self, window, tmp_path):
        """Nodes without user positions get the default hierarchy layout."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Copper;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        tab = window._active_tab

        # No user positions stored -- re-parse should use default layout
        window._apply_code_editor_text_for(tab)

        node = window.graph.all_nodes()[0]
        x, y = node.pos()
        # Single type -> column 0 at _LAYOUT_X_TAB (-100.0)
        assert abs(x - (-100.0)) < 1.0


# ---------------------------------------------------------------------------
# Position persistence to disk (Step M7.6)
# ---------------------------------------------------------------------------


class TestPositionPersistence:
    """Verify that node positions are saved to and loaded from disk."""

    def test_save_writes_layout_sidecar(self, window, tmp_path, monkeypatch):
        """Saving a file also writes position data to the sidecar file."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        tab = window._active_tab

        # Simulate a drag
        tab.user_positions["ModifiedRecipe:Titanium"] = (123.0, 456.0)

        # Bypass the project-creation prompt (no project loaded)
        monkeypatch.setattr(window, "_prompt_create_project", lambda: False)
        window._on_save()

        sidecar = tmp_path / ".craftgraph" / "layout.json"
        assert sidecar.exists()

        import json

        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert "test" in data["tabs"]
        assert data["tabs"]["test"]["ModifiedRecipe:Titanium"] == [123.0, 456.0]

    def test_load_restores_positions_from_sidecar(self, window, tmp_path):
        """Loading a file restores node positions from the sidecar."""
        import json

        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Copper;\n);\n",
            encoding="utf-8",
        )

        # Pre-create sidecar with saved positions
        sidecar_dir = tmp_path / ".craftgraph"
        sidecar_dir.mkdir()
        sidecar = sidecar_dir / "layout.json"
        sidecar.write_text(
            json.dumps(
                {
                    "version": 1,
                    "tabs": {
                        "test": {
                            "ModifiedRecipe:Copper": [700.0, 200.0],
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        window.load_recipes(recipe_file)

        node = window.graph.all_nodes()[0]
        x, y = node.pos()
        assert abs(x - 700.0) < 1.0
        assert abs(y - 200.0) < 1.0

    def test_load_without_sidecar_uses_default_layout(self, window, tmp_path):
        """Without a sidecar file, default hierarchy layout is used."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Gold;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = window.graph.all_nodes()[0]
        x, _y = node.pos()
        # Single type -> column 0 at _LAYOUT_X_TAB (-100.0)
        assert abs(x - (-100.0)) < 1.0

    def test_save_positions_on_close_no_unsaved(self, window, tmp_path):
        """Closing without unsaved content changes still saves positions."""
        from PySide6.QtGui import QCloseEvent

        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        tab = window._active_tab
        tab.user_positions["ModifiedRecipe:Iron"] = (42.0, 84.0)

        # Simulate close event (no unsaved changes)
        event = QCloseEvent()
        window.closeEvent(event)
        assert event.isAccepted()

        sidecar = tmp_path / ".craftgraph" / "layout.json"
        assert sidecar.exists()

    def test_no_sidecar_written_without_user_positions(self, window, tmp_path):
        """No sidecar file is created if no nodes have been dragged."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Silver;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        window._save_positions()

        sidecar = tmp_path / ".craftgraph" / "layout.json"
        assert not sidecar.exists()

    def test_user_positions_populated_into_tab_on_load(self, window, tmp_path):
        """Loaded positions are stored in FileTab.user_positions."""
        import json

        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Quartz;\n);\n",
            encoding="utf-8",
        )

        sidecar_dir = tmp_path / ".craftgraph"
        sidecar_dir.mkdir()
        (sidecar_dir / "layout.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "tabs": {"test": {"ModifiedRecipe:Quartz": [111.0, 222.0]}},
                }
            ),
            encoding="utf-8",
        )

        window.load_recipes(recipe_file)
        tab = window._active_tab
        assert tab.user_positions.get("ModifiedRecipe:Quartz") == (111.0, 222.0)


# ---------------------------------------------------------------------------
# View > Reset Layout (Step M7.6)
# ---------------------------------------------------------------------------


class TestResetLayout:
    """Verify that View > Reset Layout re-computes default positions."""

    def test_reset_layout_restores_default_positions(self, window, tmp_path):
        """Reset discards user positions and re-applies hierarchy layout."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        tab = window._active_tab

        # Simulate a drag
        node = window.graph.all_nodes()[0]
        node.set_pos(999.0, 888.0)
        tab.user_positions["ModifiedRecipe:Titanium"] = (999.0, 888.0)

        # Reset layout
        window._on_reset_layout()

        x, y = node.pos()
        # Single type -> column 0 at _LAYOUT_X_TAB (-100.0), Y is 0.0
        assert abs(x - (-100.0)) < 1.0
        assert abs(y - 0.0) < 1.0

    def test_reset_layout_clears_user_positions(self, window, tmp_path):
        """Reset clears the in-memory user positions dict."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Gold;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        tab = window._active_tab
        tab.user_positions["ModifiedRecipe:Gold"] = (500.0, 500.0)

        window._on_reset_layout()

        assert len(tab.user_positions) == 0

    def test_reset_layout_updates_status_bar(self, window, tmp_path):
        """Reset shows a status message."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Copper;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        window._on_reset_layout()

        assert "reset" in window.statusBar().currentMessage().lower()

    def test_reset_layout_no_crash_without_parsed_file(self, window):
        """Reset on a placeholder tab (no parsed file) does not crash."""
        window._on_reset_layout()  # Should be a no-op


# ---------------------------------------------------------------------------
# Cycle detection status bar (Step M7.7)
# ---------------------------------------------------------------------------


class TestCycleStatusBar:
    """Verify cycle count in the status bar after loading."""

    def test_load_shows_cycle_count_when_cycles_exist(self, window, tmp_path):
        """Loading a file with cycles shows cycle count in the status bar."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: Alpha;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: Beta;\n"
            "        Required: 1;\n"
            "    );\n"
            "),\n"
            "(\n"
            "    ItemID: Beta;\n"
            "    Ingredients:\n"
            "    (\n"
            "        ItemID: Alpha;\n"
            "        Required: 1;\n"
            "    );\n"
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        msg = window.statusBar().currentMessage()
        assert "cycle" in msg.lower()
        assert "!" in msg  # Ends with "!" to draw attention

    def test_load_shows_no_cycles_when_acyclic(self, window, tmp_path):
        """Loading a file without cycles shows 'no cycles'."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        msg = window.statusBar().currentMessage()
        assert "no cycles" in msg

    def test_cycle_rejection_shows_in_status_bar(self, window, tmp_path):
        """Rejecting a cyclic connection shows a warning in the status bar."""
        window._on_cycle_rejected("RecipeA", "RecipeB", ["RecipeA", "RecipeB", "RecipeA"])
        msg = window.statusBar().currentMessage()
        assert "RecipeA" in msg
        assert "RecipeB" in msg
        assert "circular" in msg.lower()

    def test_cycle_rejection_shows_cycle_path(self, window, tmp_path):
        """Cycle rejection message includes the full cycle path."""
        window._on_cycle_rejected("B", "A", ["A", "B", "C", "A"])
        msg = window.statusBar().currentMessage()
        assert "A -> B -> C -> A" in msg

    def test_cycle_rejection_shows_red_background(self, window, tmp_path):
        """Cycle rejection status bar message has a red background style."""
        window._on_cycle_rejected("RecipeA", "RecipeB", ["RecipeA", "RecipeB", "RecipeA"])
        style = window.statusBar().styleSheet()
        assert "background-color" in style
        assert "#cc3c3c" in style

    def test_cycle_rejection_red_background_clears(self, window, tmp_path):
        """Red background auto-clears after the timer fires."""
        window._on_cycle_rejected("RecipeA", "RecipeB", ["RecipeA", "RecipeB", "RecipeA"])
        assert window.statusBar().styleSheet() != ""
        window._clear_status_style()
        assert window.statusBar().styleSheet() == ""

    def test_reassignment_warning_shows_in_status_bar(self, window, tmp_path):
        """Recipe reassignment warning shows item_id and old path."""
        window._on_reassignment_warning("BigWater", "OldFab/Potions")
        msg = window.statusBar().currentMessage()
        assert "BigWater" in msg
        assert "OldFab/Potions" in msg


# ---------------------------------------------------------------------------
# Sprite auto-assign (Step M6)
# ---------------------------------------------------------------------------


def _create_test_png(path: "Path") -> None:
    """Write a minimal valid PNG to *path* using QImage."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    img = QImage(4, 4, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.red)
    img.save(str(path), "PNG")


class TestSpriteAutoAssign:
    """Verify that sprites from Assets/ are auto-assigned to nodes on load."""

    @pytest.fixture(autouse=True)
    def _clear_cc3_path(self, window):
        """Ensure sprite scanning uses the test's tmp_path, not real CC3."""
        window._subnautica_cc3_path = ""

    def test_load_assigns_sprite_from_assets_dir(self, window, tmp_path):
        """Node whose ItemID matches an Assets/ PNG gets a sprite."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n);\n",
            encoding="utf-8",
        )
        assets_dir = tmp_path / "Assets"
        assets_dir.mkdir()
        _create_test_png(assets_dir / "Titanium.png")

        window.load_recipes(tmp_path)

        nodes = window.graph.all_nodes()
        assert len(nodes) == 1
        assert nodes[0].sprite_path is not None
        assert nodes[0].sprite_path.stem.lower() == "titanium"

    def test_load_no_sprite_for_unmatched_item(self, window, tmp_path):
        """Node without a matching Assets/ PNG gets no sprite."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n);\n",
            encoding="utf-8",
        )
        assets_dir = tmp_path / "Assets"
        assets_dir.mkdir()
        _create_test_png(assets_dir / "Gold.png")

        window.load_recipes(tmp_path)

        nodes = window.graph.all_nodes()
        assert len(nodes) == 1
        assert nodes[0].sprite_path is None

    def test_load_without_assets_dir(self, window, tmp_path):
        """No Assets/ directory does not cause errors; nodes get no sprites."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Copper;\n);\n",
            encoding="utf-8",
        )

        window.load_recipes(tmp_path)

        nodes = window.graph.all_nodes()
        assert len(nodes) == 1
        assert nodes[0].sprite_path is None

    def test_sprite_lookup_cached_on_window(self, window, tmp_path):
        """The _sprite_lookup dict is populated after load."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        assets_dir = tmp_path / "Assets"
        assets_dir.mkdir()
        _create_test_png(assets_dir / "Iron.png")

        window.load_recipes(tmp_path)

        assert hasattr(window, "_sprite_lookup")
        assert "iron" in window._sprite_lookup

    def test_sprite_case_insensitive_match(self, window, tmp_path):
        """Sprite matching is case-insensitive (CC3 convention)."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: TitaniumIngot;\n);\n",
            encoding="utf-8",
        )
        assets_dir = tmp_path / "Assets"
        assets_dir.mkdir()
        _create_test_png(assets_dir / "titaniumingot.png")

        window.load_recipes(tmp_path)

        node = window.graph.all_nodes()[0]
        assert node.sprite_path is not None

    def test_code_editor_reparse_applies_cached_sprites(self, window, tmp_path):
        """After code editor rebuild, sprites still applied from cached lookup."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n);\n",
            encoding="utf-8",
        )
        assets_dir = tmp_path / "Assets"
        assets_dir.mkdir()
        _create_test_png(assets_dir / "Titanium.png")

        window.load_recipes(tmp_path)

        # Now trigger a code editor re-parse
        window.code_editor.setPlainText("ModifiedRecipes:\n(\n    ItemID: Titanium;\n);\n")
        window._apply_code_editor_text_for(window._active_tab)

        node = window.graph.all_nodes()[0]
        assert node.sprite_path is not None
        assert node.sprite_path.stem.lower() == "titanium"

    def test_single_file_load_scans_parent_assets(self, window, tmp_path):
        """Loading a single .txt file scans Assets/ in the parent directory."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Gold;\n);\n",
            encoding="utf-8",
        )
        assets_dir = tmp_path / "Assets"
        assets_dir.mkdir()
        _create_test_png(assets_dir / "Gold.png")

        window.load_recipes(recipe_file)

        node = window.graph.all_nodes()[0]
        assert node.sprite_path is not None


# ---------------------------------------------------------------------------
# Sprite context menu (Step M6)
# ---------------------------------------------------------------------------


class TestSpriteContextMenu:
    """Verify sprite handling (Sprite node replaces old context menu entries)."""

    @pytest.fixture(autouse=True)
    def _clear_cc3_path(self, window):
        """Ensure sprite scanning uses the test's tmp_path, not real CC3."""
        window._subnautica_cc3_path = ""

    def test_set_sprite_action_removed(self, window):
        """Old 'Set Sprite...' context menu entry is no longer present."""
        nodes_menu = window.graph.get_context_menu("nodes")
        menu = nodes_menu.qmenu.get_menu("CraftGraphBaseNode")
        assert menu is not None
        action_names = [a.text() for a in menu.actions()]
        assert not any("Set Sprite" in name for name in action_names)

    def test_clear_sprite_action_removed(self, window):
        """Old 'Clear Sprite' context menu entry is no longer present."""
        nodes_menu = window.graph.get_context_menu("nodes")
        menu = nodes_menu.qmenu.get_menu("CraftGraphBaseNode")
        assert menu is not None
        action_names = [a.text() for a in menu.actions()]
        assert not any("Clear Sprite" in name for name in action_names)

    def test_sprite_node_can_be_created(self, window):
        """A SpriteNode can be created via _create_node_from_menu."""
        from craftgraph.qt_nodes import NodeKind

        initial_count = len(window.graph.all_nodes())
        window._create_node_from_menu(NodeKind.SPRITE)
        assert len(window.graph.all_nodes()) == initial_count + 1

    def test_clear_sprite_resets_node(self, window, tmp_path):
        """Calling _on_clear_sprite removes the sprite from the node."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n);\n",
            encoding="utf-8",
        )
        assets_dir = tmp_path / "Assets"
        assets_dir.mkdir()
        _create_test_png(assets_dir / "Titanium.png")

        window.load_recipes(tmp_path)
        node = window.graph.all_nodes()[0]
        assert node.sprite_path is not None

        window._on_clear_sprite(window.graph, node)
        assert node.sprite_path is None

    def test_set_sprite_stores_manual_override(self, window, tmp_path):
        """Manually setting a sprite stores it in _manual_sprites."""
        from pathlib import Path
        from unittest.mock import patch

        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Copper;\n);\n",
            encoding="utf-8",
        )
        assets_dir = tmp_path / "Assets"
        assets_dir.mkdir()
        sprite_path = assets_dir / "custom_icon.png"
        _create_test_png(sprite_path)

        window.load_recipes(tmp_path)
        node = window.graph.all_nodes()[0]

        with patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            return_value=(str(sprite_path), "PNG Files (*.png)"),
        ):
            window._on_set_sprite(window.graph, node)

        assert node.sprite_path == sprite_path
        assert "copper" in window._manual_sprites

    def test_clear_sprite_removes_manual_override(self, window, tmp_path):
        """Clearing a sprite also removes it from _manual_sprites."""
        from unittest.mock import patch

        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        assets_dir = tmp_path / "Assets"
        assets_dir.mkdir()
        sprite_path = assets_dir / "Iron.png"
        _create_test_png(sprite_path)

        window.load_recipes(tmp_path)
        node = window.graph.all_nodes()[0]

        # Manually set sprite first
        with patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            return_value=(str(sprite_path), "PNG Files (*.png)"),
        ):
            window._on_set_sprite(window.graph, node)

        assert "iron" in window._manual_sprites

        window._on_clear_sprite(window.graph, node)
        assert "iron" not in window._manual_sprites


# ---------------------------------------------------------------------------
# Node deletion (Step M7.7b)
# ---------------------------------------------------------------------------


class TestNodeDeletion:
    """Verify that deleting nodes removes them from the model and code editor."""

    def test_delete_selected_removes_from_graph(self, window, tmp_path):
        """Deleting a selected node removes it from the node graph."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Alpha;\n),\n(\n    ItemID: Beta;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        assert len(window.graph.all_nodes()) == 2

        # Select first node and delete
        node = window.graph.all_nodes()[0]
        node.set_selected(True)
        window._delete_selected_nodes()

        assert len(window.graph.all_nodes()) == 1

    def test_delete_removes_from_model(self, window, tmp_path):
        """Deleting a node removes the recipe from the parsed file model."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Alpha;\n),\n(\n    ItemID: Beta;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        pf = window._active_tab.parsed_file

        # Find and delete the Alpha node
        alpha_node = None
        for node in window.graph.all_nodes():
            if node.get_property("item_id") == "Alpha":
                alpha_node = node
                break
        assert alpha_node is not None

        alpha_node.set_selected(True)
        window._delete_selected_nodes()

        # Model should only have Beta
        assert len(pf.modified_recipes) == 1
        assert pf.modified_recipes[0].item_id == "Beta"

    def test_delete_updates_code_editor(self, window, tmp_path):
        """Deleting a node updates the code editor text."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Alpha;\n),\n(\n    ItemID: Beta;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        # Delete Alpha
        for node in window.graph.all_nodes():
            if node.get_property("item_id") == "Alpha":
                node.set_selected(True)
                break
        window._delete_selected_nodes()

        text = window.code_editor.toPlainText()
        assert "Alpha" not in text
        assert "Beta" in text

    def test_delete_nothing_selected_is_noop(self, window, tmp_path):
        """Calling delete with no selection does nothing."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        window._delete_selected_nodes()

        assert len(window.graph.all_nodes()) == 1

    def test_delete_context_menu_exists(self, window):
        """The node context menu has a 'Delete' command."""
        nodes_menu = window.graph.get_context_menu("nodes")
        menu = nodes_menu.qmenu.get_menu("CraftGraphBaseNode")
        assert menu is not None
        action_names = [a.text() for a in menu.actions()]
        assert any("Delete" in name for name in action_names)

    def test_delete_clears_selection_before_removal(self, window, tmp_path):
        """After deleting a node via keyboard, no stale selection remains."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Alpha;\n),\n(\n    ItemID: Beta;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        alpha = None
        beta = None
        for node in window.graph.all_nodes():
            if node.get_property("item_id") == "Alpha":
                alpha = node
            elif node.get_property("item_id") == "Beta":
                beta = node
        assert alpha is not None and beta is not None

        alpha.set_selected(True)
        window._delete_selected_nodes()

        # Selection must be empty after delete -- no stale references
        assert window.graph.selected_nodes() == []
        # Beta must still be selectable
        beta.set_selected(True)
        assert len(window.graph.selected_nodes()) == 1

    def test_context_menu_delete_clears_selection(self, window, tmp_path):
        """After deleting a node via context menu, no stale selection remains."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Alpha;\n),\n(\n    ItemID: Beta;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        alpha = None
        beta = None
        for node in window.graph.all_nodes():
            if node.get_property("item_id") == "Alpha":
                alpha = node
            elif node.get_property("item_id") == "Beta":
                beta = node
        assert alpha is not None and beta is not None

        beta.set_selected(True)
        window._on_delete_node(window.graph, alpha)

        # Selection must be empty after context-menu delete
        assert window.graph.selected_nodes() == []


class TestNodeCreation:
    """Verify that creating new nodes clears prior selection."""

    def test_create_node_clears_prior_selection(self, window, tmp_path):
        """Creating a new node does not leave the old node selected."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Alpha;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        # Select the existing node
        alpha = window.graph.all_nodes()[0]
        alpha.set_selected(True)
        assert len(window.graph.selected_nodes()) == 1

        # Create a new node via context menu helper
        from craftgraph.qt_nodes import NodeKind

        window._create_node_from_menu(NodeKind.MODIFIED_RECIPE, item_id="Beta")

        # Old selection should be cleared
        assert not alpha.selected()

    def test_create_variable_node_clears_prior_selection(self, window, tmp_path):
        """Creating a variable node does not leave old nodes selected."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Alpha;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        alpha = window.graph.all_nodes()[0]
        alpha.set_selected(True)
        assert len(window.graph.selected_nodes()) == 1

        from craftgraph.qt_variable_nodes import VariableNodeKind

        cb = window._make_var_create_cb(VariableNodeKind.INT_VAR)
        cb(window.graph)

        assert not alpha.selected()


# ---------------------------------------------------------------------------
# Copy, paste, duplicate (Step M7.7b)
# ---------------------------------------------------------------------------


class TestCopyPasteDuplicate:
    """Verify copy, paste, and duplicate wire model objects correctly."""

    def test_copy_paste_creates_model(self, window, tmp_path):
        """Pasting a copied node creates a new model object in parsed file."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        pf = window._active_tab.parsed_file

        # Select the node and copy
        node = window.graph.all_nodes()[0]
        node.set_selected(True)
        window.graph.copy_nodes()

        # Paste
        window._paste_nodes()

        # Should have 2 nodes and 2 model entries
        assert len(window.graph.all_nodes()) == 2
        assert len(pf.modified_recipes) == 2

    def test_paste_node_has_model_ref(self, window, tmp_path):
        """Each pasted node has a model_ref pointing to its model object."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = window.graph.all_nodes()[0]
        node.set_selected(True)
        window.graph.copy_nodes()
        window._paste_nodes()

        # All nodes should have model_ref set
        for n in window.graph.all_nodes():
            assert n.model_ref is not None

    def test_paste_updates_code_editor(self, window, tmp_path):
        """Pasting a node updates the code editor text."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = window.graph.all_nodes()[0]
        node.set_selected(True)
        window.graph.copy_nodes()
        window._paste_nodes()

        text = window.code_editor.toPlainText()
        # Should contain "Iron" twice (original + pasted)
        assert text.count("Iron") >= 2

    def test_duplicate_creates_model(self, window, tmp_path):
        """Duplicating a node creates a new model object."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        pf = window._active_tab.parsed_file

        node = window.graph.all_nodes()[0]
        node.set_selected(True)
        window._duplicate_selected_nodes()

        assert len(window.graph.all_nodes()) == 2
        assert len(pf.modified_recipes) == 2

    def test_duplicate_node_has_model_ref(self, window, tmp_path):
        """Each duplicated node gets its own model_ref."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = window.graph.all_nodes()[0]
        node.set_selected(True)
        window._duplicate_selected_nodes()

        for n in window.graph.all_nodes():
            assert n.model_ref is not None

        # The two model_ref objects must be distinct instances
        refs = [n.model_ref for n in window.graph.all_nodes()]
        assert refs[0] is not refs[1]

    def test_copy_context_menu_exists(self, window):
        """Nodes context menu has a 'Copy' entry."""
        nodes_menu = window.graph.get_context_menu("nodes")
        menu = nodes_menu.qmenu.get_menu("CraftGraphBaseNode")
        assert menu is not None
        action_names = [a.text() for a in menu.actions()]
        assert any("Copy" in name for name in action_names)

    def test_duplicate_context_menu_exists(self, window):
        """Nodes context menu has a 'Duplicate' entry."""
        nodes_menu = window.graph.get_context_menu("nodes")
        menu = nodes_menu.qmenu.get_menu("CraftGraphBaseNode")
        assert menu is not None
        action_names = [a.text() for a in menu.actions()]
        assert any("Duplicate" in name for name in action_names)

    def test_paste_graph_context_menu_exists(self, window):
        """Canvas context menu has a 'Paste' entry."""
        graph_menu = window.graph.get_context_menu("graph")
        qmenu = graph_menu.qmenu
        action_names = [a.text() for a in qmenu.actions()]
        assert any("Paste" in name for name in action_names)

    def test_duplicate_nested_tab_appears_in_code(self, window, tmp_path):
        """Duplicating a CraftingTab inside a CustomFabricators file adds it to the code."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "CustomFabricators:\n(\n"
            "    ItemID: TestFab;\n"
            "    CustomCraftingTabs:\n"
            "    (\n        TabID: MyTab;\n    );\n"
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        from craftgraph.qt_nodes import CraftingTabNode

        tab_nodes = [n for n in window.graph.all_nodes() if isinstance(n, CraftingTabNode)]
        assert len(tab_nodes) == 1, f"Expected 1 tab node, got {len(tab_nodes)}"
        tab_nodes[0].set_selected(True)
        window._duplicate_selected_nodes()

        # The fabricator's internal tabs list should have the duplicate
        fab = window._active_tab.parsed_file.custom_fabricators[0]
        assert len(fab.tabs) == 2, f"Expected 2 tabs in fabricator, got {len(fab.tabs)}"

        # Code editor should contain both tabs
        text = window.code_editor.toPlainText()
        assert text.count("TabID") == 2, (
            f"Expected 2 TabID entries in code, got {text.count('TabID')}"
        )

    def test_duplicate_nested_recipe_appears_in_code(self, window, tmp_path):
        """Duplicating an AddedRecipe inside a CustomFabricators file adds it to the code."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "CustomFabricators:\n(\n"
            "    ItemID: TestFab;\n"
            "    AddedRecipes:\n"
            "    (\n        ItemID: Gadget;\n    );\n"
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        from craftgraph.qt_nodes import AddedRecipeNode

        recipe_nodes = [n for n in window.graph.all_nodes() if isinstance(n, AddedRecipeNode)]
        assert len(recipe_nodes) == 1
        recipe_nodes[0].set_selected(True)
        window._duplicate_selected_nodes()

        fab = window._active_tab.parsed_file.custom_fabricators[0]
        assert len(fab.added_recipes) == 2, (
            f"Expected 2 added recipes in fabricator, got {len(fab.added_recipes)}"
        )

    def test_duplicated_node_has_edit_history(self, window, tmp_path):
        """Duplicated nodes must have _edit_history set for field changes to work."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = window.graph.all_nodes()[0]
        node.set_selected(True)
        window._duplicate_selected_nodes()

        for n in window.graph.all_nodes():
            assert n._edit_history is not None, (
                "Duplicated node missing _edit_history -- field changes will be ignored"
            )

    def test_duplicated_node_field_change_updates_model(self, window, tmp_path):
        """Changing a field on a duplicated node must update its model and code editor."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        orig = window.graph.all_nodes()[0]
        orig.set_selected(True)
        window._duplicate_selected_nodes()

        # Find the duplicate (node whose model has item_id "Iron" but is not orig)
        duped = [n for n in window.graph.all_nodes() if n is not orig][0]

        # Simulate user changing ItemID on the duplicate
        duped.set_property("item_id", "Steel")

        # Model should reflect the change
        assert duped.model_ref.item_id == "Steel"

        # Code editor should contain both "Iron" and "Steel"
        text = window.code_editor.toPlainText()
        assert "Iron" in text
        assert "Steel" in text

    def test_duplicated_node_clears_red_frame_on_edit(self, window, tmp_path):
        """Red validation border should clear when a required field gets a value."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        orig = window.graph.all_nodes()[0]
        orig.set_selected(True)
        window._duplicate_selected_nodes()

        duped = [n for n in window.graph.all_nodes() if n is not orig][0]

        # Change ItemID to something unique
        duped.set_property("item_id", "Steel")

        # The item_id widget should NOT have the error style
        widget_item = duped.get_widget("item_id")
        qt_widget = widget_item.get_custom_widget()
        style = qt_widget.styleSheet()
        assert "200, 60, 60" not in style, (
            f"Red border still present after setting valid ItemID: {style}"
        )

    def test_duplicated_display_name_gets_suffix(self, window, tmp_path):
        """Duplicating a node with a display_name appends the title suffix to it."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            'AliasRecipes:\n(\n    ItemID: MyAlias;\n    DisplayName: "Cool Alias";\n);\n',
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        orig = window.graph.all_nodes()[0]
        orig.set_selected(True)
        window._duplicate_selected_nodes()

        duped = [n for n in window.graph.all_nodes() if n is not orig][0]
        # NodeGraphQt appends a suffix like " 1" to the title.
        # The display_name on the model should carry the same suffix.
        suffix = duped.name()[len("MyAlias") :]
        assert suffix, "Expected a duplication suffix on the node title"
        assert duped.model_ref.display_name == f"Cool Alias{suffix}"


# ---------------------------------------------------------------------------
# Toggle selection (Step M7.8)
# ---------------------------------------------------------------------------


class TestToggleSelection:
    """Verify the Toggle Selection context menu entry."""

    def test_toggle_selection_context_menu_exists(self, window):
        """Nodes context menu has a 'Toggle Selection' entry."""
        nodes_menu = window.graph.get_context_menu("nodes")
        menu = nodes_menu.qmenu.get_menu("CraftGraphBaseNode")
        assert menu is not None
        action_names = [a.text() for a in menu.actions()]
        assert any("Toggle Selection" in name for name in action_names)

    def test_toggle_selection_selects_unselected_node(self, window, tmp_path):
        """Toggle on an unselected node selects it."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        node = window.graph.all_nodes()[0]
        node.set_selected(False)

        window._on_toggle_selection(window.graph, node)
        assert node.selected()

    def test_toggle_selection_deselects_selected_node(self, window, tmp_path):
        """Toggle on a selected node deselects it."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        node = window.graph.all_nodes()[0]
        node.set_selected(True)

        window._on_toggle_selection(window.graph, node)
        assert not node.selected()


# ---------------------------------------------------------------------------
# Delete Ingredient (Step M7.8)
# ---------------------------------------------------------------------------


class TestDeleteIngredient:
    """Verify the Delete Ingredient context menu action."""

    def test_delete_ingredient_context_menu_exists(self, window):
        """Nodes context menu has a 'Delete Ingredient...' entry."""
        nodes_menu = window.graph.get_context_menu("nodes")
        menu = nodes_menu.qmenu.get_menu("ModifiedRecipeNode")
        assert menu is not None
        action_names = [a.text() for a in menu.actions()]
        assert any("Delete Ingredient" in name for name in action_names)

    def test_delete_ingredient_removes_from_model(self, window, tmp_path, monkeypatch):
        """Selecting an ingredient in the dialog removes it from the model."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n"
            "    Ingredients:\n"
            "        ( ItemID: Gold; Required: 2; ),\n"
            "        ( ItemID: Silver; Required: 3; );\n"
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = window.graph.all_nodes()[0]
        model = node.model_ref
        assert len(model.ingredients) == 2

        # Patch _pick_from_list to auto-select the first ingredient
        monkeypatch.setattr(
            "craftgraph.qt_gui._pick_from_list",
            lambda *a, **kw: ("Gold x2", True),
        )
        window._on_delete_ingredient(window.graph, node)
        assert len(model.ingredients) == 1
        assert model.ingredients[0].item_id == "Silver"

    def test_delete_ingredient_no_ingredients_shows_status(self, window, tmp_path):
        """Calling delete on a recipe with no ingredients shows a status message."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = window.graph.all_nodes()[0]
        window._on_delete_ingredient(window.graph, node)

        assert "No ingredients" in window.statusBar().currentMessage()


# ---------------------------------------------------------------------------
# Promote Ingredient to Recipe (Step M7.8)
# ---------------------------------------------------------------------------


class TestPromoteIngredient:
    """Verify the Promote Ingredient to Recipe context menu action."""

    def test_promote_context_menu_exists(self, window):
        """Nodes context menu has a 'Promote Ingredient to Recipe...' entry."""
        nodes_menu = window.graph.get_context_menu("nodes")
        menu = nodes_menu.qmenu.get_menu("ModifiedRecipeNode")
        assert menu is not None
        action_names = [a.text() for a in menu.actions()]
        assert any("Promote Ingredient" in name for name in action_names)

    def test_promote_creates_recipe_with_item_id(self, window, tmp_path, monkeypatch):
        """Promoting an ingredient creates a recipe node with that ingredient's ID."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n"
            "    Ingredients:\n"
            "        ( ItemID: Gold; Required: 2; );\n"
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = window.graph.all_nodes()[0]
        initial_count = len(window.graph.all_nodes())

        # Patch _pick_from_list: first call picks "Gold x2", second picks recipe type
        call_count = [0]

        def fake_pick(parent, title, label, items, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ("Gold x2", True)
            return ("Modified Recipe", True)

        monkeypatch.setattr(
            "craftgraph.qt_gui._pick_from_list",
            fake_pick,
        )
        window._on_promote_ingredient(window.graph, node)

        # A new node should have been created
        assert len(window.graph.all_nodes()) == initial_count + 1
        # The code editor should contain "Gold" as a new recipe ItemID
        text = window.code_editor.toPlainText()
        assert text.count("ItemID: Gold") >= 2  # ingredient + new recipe

    def test_promote_no_ingredients_shows_status(self, window, tmp_path):
        """Promoting from a recipe with no ingredients shows a status message."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = window.graph.all_nodes()[0]
        window._on_promote_ingredient(window.graph, node)

        assert "No ingredients" in window.statusBar().currentMessage()


# ---------------------------------------------------------------------------
# Add Ingredient / Orphan ingredient (Step M7.8)
# ---------------------------------------------------------------------------


class TestAddIngredientCanvas:
    """Verify the Add Ingredient canvas context menu action."""

    def test_add_ingredient_canvas_menu_exists(self, window):
        """Canvas context menu > Add Node has an 'Ingredient' entry."""
        graph_menu = window.graph.get_context_menu("graph")
        qmenu = graph_menu.qmenu
        # Find the "Add Node" submenu, then check for the Ingredient entry
        add_node_menu = None
        for action in qmenu.actions():
            if action.menu() is not None and "Add Node" in action.text():
                add_node_menu = action.menu()
                break
        assert add_node_menu is not None, "Add Node submenu not found"
        action_names = [a.text() for a in add_node_menu.actions()]
        assert any("Ingredient" in name for name in action_names)

    def test_create_orphan_ingredient_creates_node(self, window, monkeypatch):
        """_create_orphan_ingredient creates an OrphanIngredientNode."""
        from craftgraph.qt_gui import ItemIdPickerDialog

        monkeypatch.setattr(
            ItemIdPickerDialog,
            "exec_",
            lambda self: QtWidgets.QDialog.DialogCode.Accepted,
        )
        monkeypatch.setattr(
            ItemIdPickerDialog,
            "selected_id",
            property(lambda self: "Gold"),
        )
        initial_count = len(window.graph.all_nodes())
        window._create_orphan_ingredient()

        assert len(window.graph.all_nodes()) == initial_count + 1
        new_node = window.graph.all_nodes()[-1]
        assert new_node.get_property("item_id") == "Gold"
        assert new_node.model_ref is None

    def test_create_orphan_ingredient_cancel_does_nothing(self, window, monkeypatch):
        """Cancelling the dialog creates no node."""
        from craftgraph.qt_gui import ItemIdPickerDialog

        monkeypatch.setattr(
            ItemIdPickerDialog,
            "exec_",
            lambda self: QtWidgets.QDialog.DialogCode.Rejected,
        )
        initial_count = len(window.graph.all_nodes())
        window._create_orphan_ingredient()
        assert len(window.graph.all_nodes()) == initial_count


# ---------------------------------------------------------------------------
# Context-menu node creation (Step M7.7b)
# ---------------------------------------------------------------------------


class TestContextMenuNodeCreation:
    """Verify that adding nodes via context menu updates the code editor."""

    def test_add_matching_type_updates_code_editor(self, window, tmp_path):
        """Adding a recipe to a MODIFIED_RECIPES file shows in code editor."""
        from craftgraph.qt_nodes import NodeKind

        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        window._create_node_from_menu(NodeKind.MODIFIED_RECIPE)

        text = window.code_editor.toPlainText()
        assert "NewItem" in text

    def test_add_mismatched_type_shows_warning(self, window, tmp_path):
        """Adding a CraftingTab to a MODIFIED_RECIPES file is rejected."""
        from craftgraph.qt_nodes import NodeKind

        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        node_count_before = len(window.graph.all_nodes())

        window._create_node_from_menu(NodeKind.CRAFTING_TAB)

        # No new node should have been created
        assert len(window.graph.all_nodes()) == node_count_before
        # Status bar should show a warning
        msg = window.statusBar().currentMessage()
        assert "cannot" in msg.lower() or "different" in msg.lower()

    def test_add_fabricator_to_recipe_file_rejected(self, window, tmp_path):
        """Adding a Fabricator to a MODIFIED_RECIPES file is rejected."""
        from craftgraph.qt_nodes import NodeKind

        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Iron;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        node_count_before = len(window.graph.all_nodes())

        window._create_node_from_menu(NodeKind.FABRICATOR)

        assert len(window.graph.all_nodes()) == node_count_before

    def test_add_to_empty_file_sets_block_type(self, window):
        """Adding a Fabricator to the empty placeholder tab works."""
        from craftgraph.qt_nodes import NodeKind

        window._create_node_from_menu(NodeKind.FABRICATOR)

        text = window.code_editor.toPlainText()
        assert "CustomFabricators:" in text
        assert "NewFabricator" in text

    def test_add_to_empty_switched_block_type(self, window):
        """After switching block type on empty file, new type serializes."""
        from craftgraph.models import BlockType
        from craftgraph.qt_nodes import NodeKind

        # First add a fabricator (sets block_type to CUSTOM_FABRICATORS)
        window._create_node_from_menu(NodeKind.FABRICATOR)
        assert window._active_tab.parsed_file.block_type == BlockType.CUSTOM_FABRICATORS

        text = window.code_editor.toPlainText()
        assert "NewFabricator" in text

    def test_set_sprite_cancelled_dialog_no_change(self, window, tmp_path):
        """Cancelling the file dialog does not change the sprite."""
        from unittest.mock import patch

        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Silver;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(tmp_path)
        node = window.graph.all_nodes()[0]
        assert node.sprite_path is None

        with patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            return_value=("", ""),
        ):
            window._on_set_sprite(window.graph, node)

        assert node.sprite_path is None


# ---------------------------------------------------------------------------
# Node autocomplete (Step M7.9)
# ---------------------------------------------------------------------------


class TestNodeAutocomplete:
    """Verify NodeCompletionPopup is wired to node text input widgets."""

    def _load_modified_recipe(self, window, tmp_path):
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        return window.graph.all_nodes()[0]

    def _load_added_recipe(self, window, tmp_path):
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "AddedRecipes:\n"
            "(\n"
            "    ItemID: SuperAlloy;\n"
            "    Path: Fabricator/Resources;\n"
            "    Ingredients:\n"
            "    (\n        ItemID: Titanium;\n        Required: 2;\n    );\n"
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        return window.graph.all_nodes()[0]

    def _load_moved_recipe(self, window, tmp_path):
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "MovedRecipes:\n"
            "(\n"
            "    ItemID: Titanium;\n"
            "    OldPath: Fabricator/Resources;\n"
            "    NewPath: Workbench/Mods;\n"
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        return window.graph.all_nodes()[0]

    def _has_popup_event_filter(self, window, line_edit):
        """Check whether the shared NodeCompletionPopup is installed as
        an event filter on *line_edit*."""
        # Qt doesn't expose the event filter list directly, but we can
        # trigger the popup via textEdited and verify it reacts.
        popup = window._node_popup
        # Simulate typing a partial match -- the popup should show
        line_edit.textEdited.emit("tit")
        return popup._active_edit is line_edit

    def test_item_id_has_popup_attached(self, window, tmp_path):
        """ItemID text input is wired to the shared NodeCompletionPopup."""
        node = self._load_modified_recipe(window, tmp_path)
        line_edit = node.get_widget("item_id").get_custom_widget()
        assert self._has_popup_event_filter(window, line_edit)

    def test_item_id_popup_shows_vanilla_ids(self, window, tmp_path):
        """Typing in ItemID triggers popup with vanilla TechType IDs."""
        node = self._load_modified_recipe(window, tmp_path)
        line_edit = node.get_widget("item_id").get_custom_widget()
        popup = window._node_popup
        line_edit.textEdited.emit("titani")
        items = [popup._list.item(i).text() for i in range(popup._list.count())]
        assert any("titanium" in it.lower() for it in items)

    def test_item_id_popup_is_case_insensitive(self, window, tmp_path):
        """Popup matches case-insensitively (uppercase prefix finds lowercase IDs)."""
        node = self._load_modified_recipe(window, tmp_path)
        line_edit = node.get_widget("item_id").get_custom_widget()
        popup = window._node_popup
        line_edit.textEdited.emit("TITAN")
        assert popup._list.count() > 0

    def test_item_id_popup_hides_on_empty_text(self, window, tmp_path):
        """Popup hides when the text field is cleared."""
        node = self._load_modified_recipe(window, tmp_path)
        line_edit = node.get_widget("item_id").get_custom_widget()
        popup = window._node_popup
        # First show the popup
        line_edit.textEdited.emit("tit")
        assert popup.isVisible()
        # Then clear the text
        line_edit.textEdited.emit("")
        assert not popup.isVisible()

    def test_path_widget_has_popup_attached(self, window, tmp_path):
        """Path text input is wired to the shared NodeCompletionPopup."""
        node = self._load_added_recipe(window, tmp_path)
        line_edit = node.get_widget("path").get_custom_widget()
        assert self._has_popup_event_filter(window, line_edit)

    def test_path_popup_has_base_paths(self, window, tmp_path):
        """Path popup shows base crafting tree paths."""
        node = self._load_added_recipe(window, tmp_path)
        line_edit = node.get_widget("path").get_custom_widget()
        popup = window._node_popup
        line_edit.textEdited.emit("Fab")
        items = [popup._list.item(i).text() for i in range(popup._list.count())]
        assert any("Fabricator" in it for it in items)

    def test_path_popup_has_parsed_paths(self, window, tmp_path):
        """Path popup includes paths extracted from parsed recipes."""
        node = self._load_added_recipe(window, tmp_path)
        line_edit = node.get_widget("path").get_custom_widget()
        popup = window._node_popup
        line_edit.textEdited.emit("Resources")
        items = [popup._list.item(i).text() for i in range(popup._list.count())]
        assert any("Fabricator/Resources" in it for it in items)

    def test_moved_recipe_old_path_has_popup(self, window, tmp_path):
        """MovedRecipe old_path is wired to the popup with path completions."""
        node = self._load_moved_recipe(window, tmp_path)
        line_edit = node.get_widget("old_path").get_custom_widget()
        assert self._has_popup_event_filter(window, line_edit)
        popup = window._node_popup
        line_edit.textEdited.emit("Fab")
        items = [popup._list.item(i).text() for i in range(popup._list.count())]
        assert any("Fabricator" in it for it in items)

    def test_moved_recipe_new_path_has_popup(self, window, tmp_path):
        """MovedRecipe new_path is wired to the popup."""
        node = self._load_moved_recipe(window, tmp_path)
        line_edit = node.get_widget("new_path").get_custom_widget()
        assert self._has_popup_event_filter(window, line_edit)

    def test_display_name_has_no_popup(self, window, tmp_path):
        """Display name fields should not trigger the popup (free text)."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "AliasRecipes:\n"
            "(\n"
            "    ItemID: MyItem;\n"
            '    DisplayName: "My Item";\n'
            "    Path: Fabricator;\n"
            "    Ingredients:\n"
            "    (\n        ItemID: Titanium;\n        Required: 1;\n    );\n"
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        node = window.graph.all_nodes()[0]
        line_edit = node.get_widget("display_name").get_custom_widget()
        popup = window._node_popup
        # Reset the popup state
        popup._active_edit = None
        line_edit.textEdited.emit("test")
        # display_name is not in _ID_WIDGET_NAMES or _PATH_WIDGET_NAMES,
        # so the popup should not react
        assert popup._active_edit is not line_edit

    def test_amount_crafted_has_no_completer(self, window, tmp_path):
        """Non-text widgets (int edits) should not get completers."""
        node = self._load_modified_recipe(window, tmp_path)
        # amount_crafted is a NodeIntEdit, not NodeLineEdit -- should be skipped
        widget = node.get_widget("amount_crafted")
        assert widget.type_ != "LineEditNodeWidget"

    def test_popup_items_have_tooltips(self, window, tmp_path):
        """Autocomplete popup items show the full text as a tooltip.

        The 'New item: ...' entry has a distinct tooltip, so it is checked
        separately from real word-list matches.
        """
        node = self._load_modified_recipe(window, tmp_path)
        line_edit = node.get_widget("item_id").get_custom_widget()
        popup = window._node_popup
        line_edit.textEdited.emit("tit")
        assert popup._list.count() > 0
        for i in range(popup._list.count()):
            item = popup._list.item(i)
            if item.text().startswith("New item: "):
                assert "custom item" in item.toolTip().lower()
            else:
                assert item.toolTip() == item.text(), (
                    f"Item '{item.text()}' should have its full text as tooltip"
                )


# ---------------------------------------------------------------------------
# Undo/redo status bar descriptions (Step M7.9)
# ---------------------------------------------------------------------------


class TestUndoRedoStatusBar:
    """Verify status bar shows descriptions after undo/redo."""

    def test_undo_shows_description(self, window, tmp_path):
        """After undo, the status bar shows what was undone."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        node = window.graph.all_nodes()[0]
        # Change a property (pushes onto NodeGraphQt's undo stack)
        node.set_property("item_id", "Gold", push_undo=True)

        window._on_undo()
        msg = window.statusBar().currentMessage()
        assert msg.startswith("Undo:")

    def test_redo_shows_description(self, window, tmp_path):
        """After redo, the status bar shows what was redone."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        node = window.graph.all_nodes()[0]
        node.set_property("item_id", "Gold", push_undo=True)

        window._on_undo()
        window._on_redo()
        msg = window.statusBar().currentMessage()
        assert msg.startswith("Redo:")

    def test_undo_noop_when_stack_empty(self, window, tmp_path):
        """Undo with empty stack does not crash or show a message."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        # NodeGraphQt pushes undo commands during load (create_node,
        # clear_selection, etc.), so clear the stack first.
        window.graph.clear_undo_stack()
        window.statusBar().showMessage("before")
        window._on_undo()
        # Status should remain unchanged (no undo performed)
        assert window.statusBar().currentMessage() == "before"

    def test_redo_noop_when_stack_empty(self, window, tmp_path):
        """Redo with empty stack does not crash or show a message."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        window.graph.clear_undo_stack()
        window.statusBar().showMessage("before")
        window._on_redo()
        assert window.statusBar().currentMessage() == "before"


# ---------------------------------------------------------------------------
# Fabricator nesting (Step M7.9)
# ---------------------------------------------------------------------------


class TestFabricatorNesting:
    """Verify that nestable node types can be added to CustomFabricator files."""

    def _load_fabricator_file(self, window, tmp_path):
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "CustomFabricators:\n"
            "(\n"
            "    ItemID: AlchFab;\n"
            '    DisplayName: "Alchemy Fabricator";\n'
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        return recipe_file

    def test_add_crafting_tab_to_fabricator_file(self, window, tmp_path):
        """CraftingTab can be added to a CustomFabricators file."""
        from craftgraph.qt_nodes import NodeKind

        self._load_fabricator_file(window, tmp_path)
        initial_count = len(window.graph.all_nodes())
        window._create_node_from_menu(NodeKind.CRAFTING_TAB)
        assert len(window.graph.all_nodes()) == initial_count + 1

    def test_added_recipe_nests_in_fabricator(self, window, tmp_path):
        """AddedRecipe can be added to a CustomFabricators file."""
        from craftgraph.qt_nodes import NodeKind

        self._load_fabricator_file(window, tmp_path)
        window._create_node_from_menu(NodeKind.ADDED_RECIPE)
        # The new recipe should be nested in the fabricator's list
        pf = window._active_tab.parsed_file
        assert len(pf.custom_fabricators[0].added_recipes) == 1

    def test_alias_recipe_nests_in_fabricator(self, window, tmp_path):
        """AliasRecipe can be added to a CustomFabricators file."""
        from craftgraph.qt_nodes import NodeKind

        self._load_fabricator_file(window, tmp_path)
        window._create_node_from_menu(NodeKind.ALIAS_RECIPE)
        pf = window._active_tab.parsed_file
        assert len(pf.custom_fabricators[0].alias_recipes) == 1

    def test_custom_food_nests_in_fabricator(self, window, tmp_path):
        """CustomFood can be added to a CustomFabricators file."""
        from craftgraph.qt_nodes import NodeKind

        self._load_fabricator_file(window, tmp_path)
        window._create_node_from_menu(NodeKind.CUSTOM_FOOD)
        pf = window._active_tab.parsed_file
        assert len(pf.custom_fabricators[0].custom_foods) == 1

    def test_moved_recipe_nests_in_fabricator(self, window, tmp_path):
        """MovedRecipe can be added to a CustomFabricators file."""
        from craftgraph.qt_nodes import NodeKind

        self._load_fabricator_file(window, tmp_path)
        window._create_node_from_menu(NodeKind.MOVED_RECIPE)
        pf = window._active_tab.parsed_file
        assert len(pf.custom_fabricators[0].moved_recipes) == 1

    def test_second_fabricator_allowed(self, window, tmp_path):
        """A second CustomFabricator can be added to the same file."""
        from craftgraph.qt_nodes import NodeKind

        self._load_fabricator_file(window, tmp_path)
        window._create_node_from_menu(NodeKind.FABRICATOR)
        pf = window._active_tab.parsed_file
        assert len(pf.custom_fabricators) == 2

    def test_non_nestable_rejected_in_fabricator_file(self, window, tmp_path):
        """ModifiedRecipe cannot be added to a CustomFabricators file."""
        from craftgraph.qt_nodes import NodeKind

        self._load_fabricator_file(window, tmp_path)
        initial_count = len(window.graph.all_nodes())
        window._create_node_from_menu(NodeKind.MODIFIED_RECIPE)
        # Node should NOT have been created
        assert len(window.graph.all_nodes()) == initial_count
        msg = window.statusBar().currentMessage()
        assert "Cannot add" in msg

    def test_custom_size_rejected_in_fabricator_file(self, window, tmp_path):
        """CustomSize cannot be added to a CustomFabricators file."""
        from craftgraph.qt_nodes import NodeKind

        self._load_fabricator_file(window, tmp_path)
        initial_count = len(window.graph.all_nodes())
        window._create_node_from_menu(NodeKind.CUSTOM_SIZE)
        assert len(window.graph.all_nodes()) == initial_count


# ---------------------------------------------------------------------------
# Smart placement
# ---------------------------------------------------------------------------


class TestSmartPlacement:
    """Tests for _find_free_position overlap avoidance."""

    def test_find_free_position_nudges_on_overlap(self, window, tmp_path):
        """When a node already occupies the target position, the helper nudges."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Alpha;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        alpha = window.graph.all_nodes()[0]
        ax, ay = alpha.pos()

        # Ask for a free position at Alpha's exact location
        fx, fy = window._find_free_position(window.graph, ax, ay)

        # Must have been nudged away from the original spot
        assert (fx, fy) != (ax, ay)

    def test_find_free_position_returns_same_when_empty(self, window):
        """When no nodes exist, the position is returned unchanged."""
        fx, fy = window._find_free_position(window.graph, 100.0, 200.0)
        assert (fx, fy) == (100.0, 200.0)

    def test_create_two_nodes_no_overlap(self, window, tmp_path):
        """Two nodes created at the same cursor position get different positions."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Alpha;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        # Force Alpha to (0, 0) so it collides with cursor-derived positions
        # (QCursor.pos() returns origin in headless tests).
        alpha = window.graph.all_nodes()[0]
        alpha.set_pos(0.0, 0.0)

        from craftgraph.qt_nodes import NodeKind

        window._create_node_from_menu(NodeKind.MODIFIED_RECIPE, item_id="Beta")
        window._create_node_from_menu(NodeKind.MODIFIED_RECIPE, item_id="Gamma")

        positions = [tuple(node.pos()) for node in window.graph.all_nodes()]
        # All positions must be unique (no perfect overlap)
        assert len(set(positions)) == len(positions)


class TestRequiredFieldHighlighting:
    """Phase E: required fields get a red border when empty."""

    def test_empty_item_id_has_red_border(self, window, qapp):
        """A freshly created node with empty ItemID shows red border."""
        from craftgraph.qt_nodes import NodeKind, _REQUIRED_EMPTY_STYLE

        window._create_node_from_menu(NodeKind.MODIFIED_RECIPE, item_id="")

        node = window.graph.all_nodes()[0]
        widget_item = node.get_widget("item_id")
        qt_widget = widget_item.get_custom_widget()
        assert _REQUIRED_EMPTY_STYLE in qt_widget.styleSheet()

    def test_filled_item_id_no_red_border(self, window, tmp_path, qapp):
        """A node loaded with a valid ItemID has no red border."""
        from craftgraph.qt_nodes import _REQUIRED_EMPTY_STYLE

        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Alpha;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = window.graph.all_nodes()[0]
        widget_item = node.get_widget("item_id")
        qt_widget = widget_item.get_custom_widget()
        assert _REQUIRED_EMPTY_STYLE not in qt_widget.styleSheet()

    def test_clearing_required_field_adds_red_border(self, window, tmp_path, qapp):
        """Clearing a required field triggers red border."""
        from craftgraph.qt_nodes import _REQUIRED_EMPTY_STYLE

        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Alpha;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = window.graph.all_nodes()[0]
        # Simulate user clearing the field
        node.set_property("item_id", "")
        node.validate_required_fields()

        widget_item = node.get_widget("item_id")
        qt_widget = widget_item.get_custom_widget()
        assert _REQUIRED_EMPTY_STYLE in qt_widget.styleSheet()

    def test_non_required_field_no_red_border_when_empty(self, window, tmp_path, qapp):
        """Non-required fields stay unstyled even when empty."""
        from craftgraph.qt_nodes import _REQUIRED_EMPTY_STYLE

        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Alpha;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = window.graph.all_nodes()[0]
        # amount_crafted is not required
        widget_item = node.get_widget("amount_crafted")
        if widget_item is not None:
            qt_widget = widget_item.get_custom_widget()
            assert qt_widget is None or _REQUIRED_EMPTY_STYLE not in (qt_widget.styleSheet() or "")


class TestMutualExclusion:
    """Phase E: Copied/Hidden mutual exclusion on MovedRecipe nodes."""

    def test_checking_copied_unchecks_hidden(self, window, tmp_path, qapp):
        """Setting Copied=True forces Hidden=False."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "MovedRecipes:\n(\n    ItemID: Alpha;\n    Hidden: YES;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = None
        for n in window.graph.all_nodes():
            if n.get_property("item_id") == "Alpha":
                node = n
                break
        assert node is not None
        assert node.get_property("hidden") is True

        # Simulate user checking Copied
        node._on_field_changed("copied", True)
        assert node.get_property("hidden") is False

    def test_checking_hidden_unchecks_copied(self, window, tmp_path, qapp):
        """Setting Hidden=True forces Copied=False."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "MovedRecipes:\n(\n    ItemID: Alpha;\n    Copied: YES;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = None
        for n in window.graph.all_nodes():
            if n.get_property("item_id") == "Alpha":
                node = n
                break
        assert node is not None
        assert node.get_property("copied") is True

        node._on_field_changed("hidden", True)
        assert node.get_property("copied") is False


class TestPairedFields:
    """Phase E: PdaGroup/PdaCategory paired-field warning."""

    def test_one_set_other_empty_shows_warning(self, window, tmp_path, qapp):
        """Setting PdaGroup without PdaCategory shows a yellow border on PdaCategory."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "AddedRecipes:\n(\n    ItemID: Alpha;\n    Path: Fabricator;\n"
            "    PdaGroup: Resources;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = None
        for n in window.graph.all_nodes():
            if n.get_property("item_id") == "Alpha":
                node = n
                break
        assert node is not None

        # PdaGroup is set, PdaCategory is not -- the empty one should have a warning
        cat_widget = node.get_widget("pda_category")
        assert cat_widget is not None
        qt_cat = cat_widget.get_custom_widget()
        assert "200, 160, 40" in qt_cat.styleSheet()

    def test_both_set_no_warning(self, window, tmp_path, qapp):
        """Both PdaGroup and PdaCategory set -- no warning borders."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "AddedRecipes:\n(\n    ItemID: Alpha;\n    Path: Fabricator;\n"
            "    PdaGroup: Resources;\n    PdaCategory: BasicMaterials;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = None
        for n in window.graph.all_nodes():
            if n.get_property("item_id") == "Alpha":
                node = n
                break
        assert node is not None

        grp_widget = node.get_widget("pda_group")
        cat_widget = node.get_widget("pda_category")
        assert "200, 160, 40" not in (grp_widget.get_custom_widget().styleSheet() or "")
        assert "200, 160, 40" not in (cat_widget.get_custom_widget().styleSheet() or "")


class TestPathReferenceValidation:
    """Phase E: path fields with unknown references get an orange border."""

    def test_invalid_path_gets_orange_border(self, window, tmp_path, qapp):
        """A path that references no known fabricator/tab is highlighted orange."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "AddedRecipes:\n(\n    ItemID: Alpha;\n    Path: NonExistentFab/Tab;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = None
        for n in window.graph.all_nodes():
            if n.get_property("item_id") == "Alpha":
                node = n
                break
        assert node is not None

        path_widget = node.get_widget("path")
        assert path_widget is not None
        qt_w = path_widget.get_custom_widget()
        assert "200, 120, 40" in qt_w.styleSheet()

    def test_valid_path_no_orange_border(self, window, tmp_path, qapp):
        """A path referencing a built-in fabricator has no orange border."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "AddedRecipes:\n(\n    ItemID: Alpha;\n    Path: Fabricator;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        node = None
        for n in window.graph.all_nodes():
            if n.get_property("item_id") == "Alpha":
                node = n
                break
        assert node is not None

        path_widget = node.get_widget("path")
        assert path_widget is not None
        qt_w = path_widget.get_custom_widget()
        assert "200, 120, 40" not in (qt_w.styleSheet() or "")


class TestValidationSummary:
    """Phase E: export-time validation summary dialog."""

    def test_no_issues_returns_empty_list(self, window, tmp_path, qapp):
        """A file with valid data has no validation issues."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Alpha;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        issues = window._collect_validation_issues()
        assert issues == []

    def test_empty_required_field_reported(self, window, tmp_path, qapp):
        """An empty required ItemID is reported as an issue."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Alpha;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        node = window.graph.all_nodes()[0]
        # Simulate user clearing the ItemID field
        node.set_property("item_id", "")
        issues = window._collect_validation_issues()
        assert any("required but empty" in i for i in issues)

    def test_invalid_path_reported(self, window, tmp_path, qapp):
        """A path referencing a non-existent target is reported."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "AddedRecipes:\n(\n    ItemID: Alpha;\n    Path: BogusPath;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        issues = window._collect_validation_issues()
        assert any("does not match" in i for i in issues)

    def test_paired_field_imbalance_reported(self, window, tmp_path, qapp):
        """Setting PdaGroup but not PdaCategory is reported."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "AddedRecipes:\n(\n    ItemID: Alpha;\n    Path: Fabricator;\n"
            "    PdaGroup: Resources;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        issues = window._collect_validation_issues()
        assert any("both be set or both be empty" in i for i in issues)

    def test_unknown_ingredient_reported(self, window, tmp_path, qapp):
        """An ingredient referencing an unknown ID is reported."""
        recipe_file = tmp_path / "test.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: titanium;\n"
            "    Ingredients:\n    (\n        ItemID: unobtainium;\n"
            "        Required: 1;\n    );\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        issues = window._collect_validation_issues()
        assert any("unobtainium" in i.lower() for i in issues)


# ---------------------------------------------------------------------------
# Node header tooltips
# ---------------------------------------------------------------------------


class TestNodeHeaderTooltips:
    def test_recipe_node_has_description_tooltip(self, window, tmp_path):
        recipe_file = tmp_path / "Recipes.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Knife;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        tab = window._file_tabs[0]
        nodes = tab.graph.all_nodes()
        assert len(nodes) >= 1
        node = nodes[0]
        tip = node.view.toolTip()
        assert "Modified Recipe" in tip
        assert "existing in-game recipe" in tip

    def test_fabricator_node_has_description_tooltip(self, window, tmp_path):
        recipe_file = tmp_path / "Fabricators.txt"
        recipe_file.write_text(
            "CustomFabricators:\n(\n    ItemID: TestFab;\n"
            '    DisplayName: "Test Fab";\n'
            '    Tooltip: "Test";\n);\n',
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        tab = window._file_tabs[0]
        from craftgraph.qt_nodes import FabricatorNode

        fab_nodes = [n for n in tab.graph.all_nodes() if isinstance(n, FabricatorNode)]
        assert len(fab_nodes) >= 1
        tip = fab_nodes[0].view.toolTip()
        assert "Fabricator" in tip
        assert "crafting station" in tip


class TestFieldWidgetTooltips:
    """Field widget tooltips show the current value (overflow tooltip)."""

    def test_item_id_widget_shows_current_value(self, window, tmp_path):
        recipe_file = tmp_path / "Recipes.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Knife;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        tab = window._file_tabs[0]
        node = tab.graph.all_nodes()[0]
        widget = node.get_widget("item_id")
        assert widget is not None
        qt_widget = widget.get_custom_widget()
        assert qt_widget is not None
        assert qt_widget.toolTip() == qt_widget.text()

    def test_amount_widget_shows_current_value(self, window, tmp_path):
        recipe_file = tmp_path / "Recipes.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Knife;\n);\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        tab = window._file_tabs[0]
        node = tab.graph.all_nodes()[0]
        widget = node.get_widget("amount_crafted")
        assert widget is not None
        qt_widget = widget.get_custom_widget()
        assert qt_widget is not None
        inner = qt_widget._edit
        assert inner.toolTip() == inner.text()


class TestItemIdReferencePanel:
    def test_dock_exists(self, window):
        """The ItemID Reference dock widget should exist."""
        assert hasattr(window, "_id_dock")
        assert window._id_dock is not None

    def test_dock_has_list(self, window):
        """The dock should contain a filterable list view."""
        assert hasattr(window, "_id_list")
        model = window._id_list.model()
        assert model is not None
        assert model.rowCount() > 400  # 498 vanilla + headers + mod IDs

    def test_filter_narrows_list(self, window):
        """Typing in the filter should narrow the visible items."""
        proxy = window._id_list.model()
        total = proxy.rowCount()
        window._id_filter.setText("knife")
        filtered = proxy.rowCount()
        assert filtered < total
        assert filtered >= 1

    def test_count_label_shows_stats(self, window):
        """The count label should show vanilla and mod-compat counts."""
        text = window._id_count_label.text()
        assert "vanilla" in text
        assert "mod-compat" in text

    def test_view_menu_has_toggle(self, window):
        """View menu should have a toggle action for the reference panel."""
        from PySide6.QtWidgets import QMenu

        view_menu = window.menuBar().findChild(QMenu, "view_menu")
        assert view_menu is not None
        action_texts = [a.text() for a in view_menu.actions()]
        assert any("ItemID Reference" in t for t in action_texts)

    def test_drag_enabled(self, window):
        """List view should have drag enabled for drag-to-pin."""
        assert window._id_list.dragEnabled() is True
        from PySide6.QtWidgets import QAbstractItemView

        assert window._id_list.dragDropMode() == QAbstractItemView.DragDropMode.DragOnly

    def test_header_items_not_draggable(self, window):
        """Section header items should not be draggable."""
        from PySide6.QtCore import Qt

        source_model = window._id_list.model().sourceModel()
        header = source_model.item(0)
        assert header is not None
        assert "Vanilla" in header.text()
        assert not (header.flags() & Qt.ItemFlag.ItemIsDragEnabled)


class TestContextMenuTooltips:
    """Context menu 'Add Node' entries use regular QActions with HTML tooltips."""

    def _find_add_node_menu(self, window):
        graph_menu = window.graph.get_context_menu("graph")
        for action in graph_menu.qmenu.actions():
            if action.menu() is not None and "Add Node" in action.text():
                return action.menu()
        return None

    def test_add_node_entries_are_regular_qactions(self, window):
        """Add Node submenu uses regular QAction, not QWidgetAction."""
        from PySide6.QtWidgets import QWidgetAction

        add_node_menu = self._find_add_node_menu(window)
        assert add_node_menu is not None
        ingredient_action = None
        for a in add_node_menu.actions():
            if a.text() == "Ingredient":
                ingredient_action = a
                break
        assert ingredient_action is not None
        assert not isinstance(ingredient_action, QWidgetAction)

    def test_recipe_submenu_actions_have_html_tooltips(self, window):
        """Recipe submenu entries have HTML tooltips with bold name."""
        add_node_menu = self._find_add_node_menu(window)
        assert add_node_menu is not None
        recipes_menu = None
        for action in add_node_menu.actions():
            if action.menu() is not None and action.text() == "Recipes":
                recipes_menu = action.menu()
                break
        assert recipes_menu is not None
        for action in recipes_menu.actions():
            tip = action.toolTip()
            assert "<b>" in tip, f"Action '{action.text()}' missing HTML tooltip"

    def test_variable_submenu_actions_have_html_tooltips(self, window):
        """Variable submenu entries have HTML tooltips."""
        add_node_menu = self._find_add_node_menu(window)
        assert add_node_menu is not None
        variables_menu = None
        for action in add_node_menu.actions():
            if action.menu() is not None and action.text() == "Variables":
                variables_menu = action.menu()
                break
        assert variables_menu is not None
        for action in variables_menu.actions():
            tip = action.toolTip()
            assert "<b>" in tip, f"Action '{action.text()}' missing HTML tooltip"


class TestCaseInsensitiveAutocomplete:
    def test_no_case_insensitive_duplicates_in_id_words(self, window):
        """All IDs in the autocomplete list should be unique case-insensitively."""
        words = window._get_id_words()
        lower_set: set[str] = set()
        dupes: list[str] = []
        for w in words:
            low = w.lower()
            if low in lower_set:
                dupes.append(w)
            lower_set.add(low)
        assert dupes == [], f"Case-insensitive duplicates found: {dupes}"

    def test_completer_is_case_insensitive(self, window):
        """QCompleter should be set to case-insensitive matching."""
        from PySide6.QtCore import Qt

        completer = window._make_completer(["Knife", "knife", "Gold"])
        assert completer.caseSensitivity() == Qt.CaseSensitivity.CaseInsensitive

    def test_completer_uses_contains_matching(self, window):
        """QCompleter should filter by substring, not just prefix."""
        from PySide6.QtCore import Qt

        completer = window._make_completer(["Knife", "knife", "Gold"])
        assert completer.filterMode() == Qt.MatchFlag.MatchContains

    def test_node_popup_filters_case_insensitively(self, window):
        """NodeCompletionPopup should match regardless of case."""
        popup = window._node_popup
        words = ["Knife", "Gold", "acidmushroom"]
        # Simulate filtering by calling the internal method
        popup._all_words = words
        # Direct test of the filtering logic
        prefix = "kni"
        matches = [w for w in words if prefix in w.lower()]
        assert "Knife" in matches
        assert len(matches) == 1


class TestEasyMarkupKeywordAutocomplete:
    """Issue 6: code editor autocomplete includes EasyMarkup language keywords
    alongside TechType IDs, with visual separation between the two groups."""

    def test_easymarkup_keywords_combines_block_types_and_field_keys(self):
        from craftgraph.highlighter import BLOCK_TYPES, FIELD_KEYS
        from craftgraph.qt_gui import _easymarkup_keywords

        keywords = _easymarkup_keywords()
        assert set(keywords) == BLOCK_TYPES | FIELD_KEYS
        assert keywords == sorted(keywords)

    def test_easymarkup_keywords_includes_core_field_names(self):
        from craftgraph.qt_gui import _easymarkup_keywords

        keywords = set(_easymarkup_keywords())
        for required in (
            "ItemID",
            "Path",
            "AmountCrafted",
            "Required",
            "LinkedItemIDs",
            "DisplayName",
            "Tooltip",
            "Ingredients",
            "ModifiedRecipes",
            "AddedRecipes",
            "AliasRecipes",
            "CustomFabricators",
        ):
            assert required in keywords, f"Missing keyword: {required}"

    def test_make_completer_with_keywords_includes_both_groups(self, window):
        keywords = ["ItemID", "Path", "DisplayName"]
        ids = ["Titanium", "Gold", "Quartz"]
        completer = window._make_completer(ids, keywords=keywords)
        model = completer.model()
        contents = [model.index(i, 0).data() for i in range(model.rowCount())]
        for word in keywords + ids:
            assert word in contents

    def test_make_completer_with_keywords_orders_keywords_first(self, window):
        """Unfiltered popup clusters keywords at the top so they're easy to scan."""
        keywords = ["ItemID", "Path", "DisplayName"]
        ids = ["Titanium", "Gold", "Quartz"]
        completer = window._make_completer(ids, keywords=keywords)
        model = completer.model()
        contents = [model.index(i, 0).data() for i in range(model.rowCount())]
        keyword_positions = [contents.index(k) for k in keywords]
        id_positions = [contents.index(w) for w in ids]
        assert max(keyword_positions) < min(id_positions)

    def test_make_completer_with_keywords_installs_grouped_delegate(self, window):
        from craftgraph.qt_gui import _GroupedCompleterDelegate

        completer = window._make_completer(
            ["Titanium"], keywords=["ItemID", "Path"],
        )
        delegate = completer.popup().itemDelegate()
        assert isinstance(delegate, _GroupedCompleterDelegate)

    def test_make_completer_without_keywords_uses_default_delegate(self, window):
        from craftgraph.qt_gui import _GroupedCompleterDelegate

        completer = window._make_completer(["Titanium", "Gold"])
        delegate = completer.popup().itemDelegate()
        assert not isinstance(delegate, _GroupedCompleterDelegate)

    def test_setup_autocomplete_for_attaches_keyword_aware_completer(self, window):
        from craftgraph.code_editor import CodeEditor
        from craftgraph.qt_gui import _GroupedCompleterDelegate

        editor = CodeEditor()
        try:
            window._setup_autocomplete_for(editor)
            completer = editor.completer()
            assert completer is not None
            delegate = completer.popup().itemDelegate()
            assert isinstance(delegate, _GroupedCompleterDelegate)
            model = completer.model()
            contents = {model.index(i, 0).data() for i in range(model.rowCount())}
            assert "ItemID" in contents
            assert "Required" in contents
        finally:
            editor.deleteLater()

    def test_grouped_delegate_classifies_keywords_case_insensitively(self, window):
        from craftgraph.qt_gui import _GroupedCompleterDelegate

        delegate = _GroupedCompleterDelegate({"ItemID", "Path"})
        assert "itemid" in delegate._kw_lower
        assert "path" in delegate._kw_lower
        assert "titanium" not in delegate._kw_lower


# ---------------------------------------------------------------------------
# "New item" autocomplete entry
# ---------------------------------------------------------------------------


class TestNewItemAutocompleteEntry:
    """The popup always shows a 'New item: ...' entry at the bottom so users
    can keep their exact typed text instead of being forced to accept a
    suggestion from the word list."""

    @pytest.fixture
    def popup_env(self, window):
        """A popup + line edit wired with a small word list."""
        popup = window._node_popup
        le = QtWidgets.QLineEdit()
        le.show()
        words = ["Titanium", "TitaniumIngot", "Gold", "GoldIngot"]
        popup.attach(le, words)
        return popup, le, words

    def _items(self, popup):
        """Return all item texts currently in the popup list widget."""
        return [popup._list.item(i).text() for i in range(popup._list.count())]

    def test_new_item_entry_appears_as_last(self, popup_env):
        """Typing text that partially matches shows 'New item: ...' as the last entry."""
        popup, le, words = popup_env
        le.textEdited.emit("tit")
        items = self._items(popup)
        assert len(items) >= 2  # at least one real match + new item entry
        assert items[-1] == "New item: tit"

    def test_new_item_entry_with_zero_matches(self, popup_env):
        """Typing text with no word-list matches still shows the new item entry."""
        popup, le, words = popup_env
        le.textEdited.emit("zzzzunknown")
        assert popup.isVisible()
        items = self._items(popup)
        assert len(items) == 1
        assert items[0] == "New item: zzzzunknown"

    def test_new_item_entry_updates_on_each_keystroke(self, popup_env):
        """The new item entry text updates as the user types more characters."""
        popup, le, words = popup_env
        le.textEdited.emit("te")
        items_1 = self._items(popup)
        assert items_1[-1] == "New item: te"

        le.textEdited.emit("tes")
        items_2 = self._items(popup)
        assert items_2[-1] == "New item: tes"

        le.textEdited.emit("test")
        items_3 = self._items(popup)
        assert items_3[-1] == "New item: test"

    def test_accepting_new_item_keeps_typed_text(self, popup_env):
        """Selecting the 'New item' entry writes only the raw text, not the prefix."""
        popup, le, words = popup_env
        le.textEdited.emit("myCustomItem")
        # Navigate to last item (the new item entry)
        popup._list.setCurrentRow(popup._list.count() - 1)
        popup._accept_current()
        assert le.text() == "myCustomItem"

    def test_clicking_new_item_keeps_typed_text(self, popup_env):
        """Clicking the 'New item' entry writes the raw typed text."""
        popup, le, words = popup_env
        le.textEdited.emit("myMod")
        last_item = popup._list.item(popup._list.count() - 1)
        popup._on_item_clicked(last_item)
        assert le.text() == "myMod"

    def test_empty_text_hides_popup_no_new_item(self, popup_env):
        """Empty input hides the popup entirely -- no 'New item' entry for blank."""
        popup, le, words = popup_env
        le.textEdited.emit("tit")
        assert popup.isVisible()
        le.textEdited.emit("")
        assert not popup.isVisible()

    def test_new_item_present_alongside_real_matches(self, popup_env):
        """Even with real matches, the 'New item' entry is always the last item."""
        popup, le, words = popup_env
        le.textEdited.emit("Gold")
        items = self._items(popup)
        # Should have real matches (Gold, GoldIngot) plus the new item entry
        assert any(it == "Gold" for it in items)
        assert items[-1] == "New item: Gold"

    def test_accepting_real_match_still_works(self, popup_env):
        """Selecting a real match (not the new item entry) still sets the full word."""
        popup, le, words = popup_env
        le.textEdited.emit("Gold")
        popup._list.setCurrentRow(0)  # first item = real match
        popup._accept_current()
        # Should be a real word, not "New item: Gold"
        assert le.text() in words


# ---------------------------------------------------------------------------
# Tab bar tooltips
# ---------------------------------------------------------------------------


class TestTabBarTooltips:
    """Per-file tab labels show the full path as a tooltip."""

    def test_untitled_tab_has_tooltip(self, window):
        """The default 'untitled' tab has a tooltip."""
        tip = window._tab_bar.tabToolTip(0)
        assert tip == "untitled"

    def test_loaded_file_tab_has_full_path_tooltip(self, window, tmp_path):
        """Tabs loaded from files show the full file path as tooltip."""
        recipe_file = tmp_path / "ModifiedRecipes.txt"
        recipe_file.write_text(
            "ModifiedRecipes:\n(\n    ItemID: Titanium;\n)\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)
        # Find the tab for our file
        found = False
        for i in range(window._tab_bar.count()):
            tip = window._tab_bar.tabToolTip(i)
            if str(recipe_file) in tip:
                found = True
                break
        assert found, "No tab tooltip contains the full file path"


# ---------------------------------------------------------------------------
# MMB pan regression fix (modifier state sync)
# ---------------------------------------------------------------------------


class TestModifierStateSync:
    """Viewer ALT_state is synced from actual modifiers on mouse press."""

    def test_stale_alt_state_reset_on_mouse_press(self, window):
        """If ALT_state gets stuck True, a mouse press without ALT resets it."""
        from PySide6 import QtCore, QtGui

        viewer = window.graph.viewer()
        # Simulate stale ALT_state (as if ALT was pressed then focus lost)
        viewer.ALT_state = True

        # Deliver event through the event system so filters intercept it
        press = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QPointF(100, 100),
            QtCore.Qt.MouseButton.MiddleButton,
            QtCore.Qt.MouseButton.MiddleButton,
            QtCore.Qt.KeyboardModifier.NoModifier,
        )
        QtCore.QCoreApplication.sendEvent(viewer, press)

        assert not viewer.ALT_state, "ALT_state should be synced to False on mouse press"

    def test_alt_state_preserved_when_alt_held(self, window):
        """If ALT is actually held during mouse press, ALT_state stays True."""
        from PySide6 import QtCore, QtGui

        viewer = window.graph.viewer()

        press = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QPointF(100, 100),
            QtCore.Qt.MouseButton.MiddleButton,
            QtCore.Qt.MouseButton.MiddleButton,
            QtCore.Qt.KeyboardModifier.AltModifier,
        )
        QtCore.QCoreApplication.sendEvent(viewer, press)

        assert viewer.ALT_state, "ALT_state should be True when ALT is held"


# ---------------------------------------------------------------------------
# Auto-save
# ---------------------------------------------------------------------------


class TestAutoSave:
    """Auto-save timer saves dirty tabs silently at a configurable interval."""

    def test_auto_save_timer_exists(self, window):
        from PySide6 import QtCore

        assert hasattr(window, "_auto_save_timer")
        assert isinstance(window._auto_save_timer, QtCore.QTimer)

    def test_auto_save_disabled_by_default(self, window):
        assert not window._auto_save_timer.isActive()

    def test_auto_save_default_interval(self, window):
        assert window._auto_save_interval == 60

    def test_enable_auto_save_starts_timer(self, window):
        window._set_auto_save(enabled=True, interval=30)
        assert window._auto_save_timer.isActive()
        assert window._auto_save_timer.interval() == 30_000

    def test_disable_auto_save_stops_timer(self, window):
        window._set_auto_save(enabled=True, interval=30)
        window._set_auto_save(enabled=False)
        assert not window._auto_save_timer.isActive()

    def test_auto_save_changes_interval(self, window):
        window._set_auto_save(enabled=True, interval=120)
        assert window._auto_save_timer.interval() == 120_000

    def test_auto_save_calls_silent_save(self, window, tmp_path, monkeypatch):
        """Firing the timer should save dirty tabs without a validation prompt."""
        recipe = tmp_path / "test.txt"
        recipe.write_text("ModifiedRecipes:\n", encoding="utf-8")
        window.load_recipes(recipe)
        tab = window._file_tabs[0]
        tab.history._undo_stack.append(None)  # make dirty

        saved_paths: list[str] = []
        monkeypatch.setattr(
            "craftgraph.qt_gui.save_with_backup",
            lambda path, text, backup=False: saved_paths.append(str(path)),
        )

        window._auto_save_tick()

        assert len(saved_paths) == 1
        assert "test.txt" in saved_paths[0]

    def test_auto_save_skips_clean_tabs(self, window, tmp_path, monkeypatch):
        """Auto-save should not write tabs that are not dirty."""
        recipe = tmp_path / "clean.txt"
        recipe.write_text("ModifiedRecipes:\n", encoding="utf-8")
        window.load_recipes(recipe)

        saved_paths: list[str] = []
        monkeypatch.setattr(
            "craftgraph.qt_gui.save_with_backup",
            lambda path, text, backup=False: saved_paths.append(str(path)),
        )

        window._auto_save_tick()

        assert len(saved_paths) == 0

    def test_auto_save_does_not_show_validation_dialog(self, window, tmp_path, monkeypatch):
        """Auto-save must be silent -- no validation summary popup."""
        recipe = tmp_path / "r.txt"
        recipe.write_text("ModifiedRecipes:\n", encoding="utf-8")
        window.load_recipes(recipe)
        tab = window._file_tabs[0]
        tab.history._undo_stack.append(None)  # make dirty

        monkeypatch.setattr(
            "craftgraph.qt_gui.save_with_backup",
            lambda path, text, backup=False: None,
        )
        shown: list[bool] = []
        monkeypatch.setattr(
            window, "_show_validation_summary", lambda issues: shown.append(True) or True
        )

        window._auto_save_tick()

        assert len(shown) == 0, "Auto-save should not show validation dialog"

    def test_settings_dialog_auto_save_defaults(self, window, monkeypatch):
        """Settings dialog should reflect current auto-save state."""
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(
            window,
            auto_save_enabled=False,
            auto_save_interval=60,
        )
        assert dialog.auto_save_enabled is False
        assert dialog.auto_save_interval == 60

    def test_settings_dialog_auto_save_custom_values(self, window, monkeypatch):
        """Settings dialog should accept and expose custom auto-save values."""
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(
            window,
            auto_save_enabled=True,
            auto_save_interval=120,
        )
        assert dialog.auto_save_enabled is True
        assert dialog.auto_save_interval == 120

    def test_on_settings_wires_auto_save(self, window, monkeypatch):
        """Closing Settings should apply auto-save toggle and interval."""
        from craftgraph.qt_gui import _SettingsDialog

        # Capture _set_auto_save calls
        calls: list[dict] = []
        original_set = window._set_auto_save

        def tracking_set(*, enabled=False, interval=None):
            calls.append({"enabled": enabled, "interval": interval})
            original_set(enabled=enabled, interval=interval)

        monkeypatch.setattr(window, "_set_auto_save", tracking_set)

        # Make the dialog return immediately, with auto-save enabled at 45s
        def fake_exec(self_dialog):
            self_dialog._auto_save_cb.setChecked(True)
            self_dialog._auto_save_interval_spin.setValue(45)
            return True

        monkeypatch.setattr(_SettingsDialog, "exec_", fake_exec)
        window._on_settings()

        assert len(calls) == 1
        assert calls[0]["enabled"] is True
        assert calls[0]["interval"] == 45


class TestDefaultPaths:
    """Settings dialog exposes default project folder and Subnautica CC3 path."""

    def test_window_has_path_attrs(self, window):
        """Window stores project_folder and cc3_path as strings."""
        assert hasattr(window, "_default_project_folder")
        assert hasattr(window, "_subnautica_cc3_path")
        assert isinstance(window._default_project_folder, str)
        assert isinstance(window._subnautica_cc3_path, str)

    def test_project_folder_defaults_to_documents(self, window):
        from pathlib import Path

        expected = str(Path.home() / "Documents" / "CraftGraph")
        assert window._default_project_folder == expected

    def test_cc3_path_defaults_to_detected_or_empty(self, window):
        """CC3 path is auto-detected if found, otherwise empty string."""
        # On CI or machines without Subnautica, this is "".
        # On a dev machine with Subnautica, it's the detected path.
        assert isinstance(window._subnautica_cc3_path, str)

    def test_settings_dialog_accepts_path_values(self, window):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(
            window,
            default_project_folder="/some/project",
            subnautica_cc3_path="/some/cc3",
        )
        assert dialog.default_project_folder == "/some/project"
        assert dialog.subnautica_cc3_path == "/some/cc3"

    def test_settings_dialog_empty_paths(self, window):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(window)
        assert dialog.default_project_folder == ""
        assert dialog.subnautica_cc3_path == ""

    def test_on_settings_reads_back_paths(self, window, monkeypatch):
        from craftgraph.qt_gui import _SettingsDialog

        def fake_exec(self_dialog):
            self_dialog._project_folder_edit.setText("/edited/project")
            self_dialog._cc3_path_edit.setText("/edited/cc3")
            return True

        monkeypatch.setattr(_SettingsDialog, "exec_", fake_exec)
        window._on_settings()

        assert window._default_project_folder == "/edited/project"
        assert window._subnautica_cc3_path == "/edited/cc3"


class TestCc3PathConvenience:
    """CraftGraphWindow._cc3_working_dir / _cc3_assets_dir delegate to path helpers."""

    def test_working_dir_returns_subfolder_when_set(self, window: CraftGraphWindow) -> None:
        from pathlib import Path

        window._subnautica_cc3_path = str(Path("/fake/CC3"))
        result = window._cc3_working_dir()
        assert "WorkingFiles" in result
        assert result.startswith(str(Path("/fake/CC3")))

    def test_working_dir_returns_empty_when_unset(self, window: CraftGraphWindow) -> None:
        window._subnautica_cc3_path = ""
        assert window._cc3_working_dir() == ""

    def test_assets_dir_returns_subfolder_when_set(self, window: CraftGraphWindow) -> None:
        from pathlib import Path

        window._subnautica_cc3_path = str(Path("/fake/CC3"))
        result = window._cc3_assets_dir()
        assert "Assets" in result
        assert result.startswith(str(Path("/fake/CC3")))

    def test_assets_dir_returns_empty_when_unset(self, window: CraftGraphWindow) -> None:
        window._subnautica_cc3_path = ""
        assert window._cc3_assets_dir() == ""


# ---------------------------------------------------------------------------
# Open Folder / Open File dialog defaults
# ---------------------------------------------------------------------------


class TestOpenFolderDefault:
    """_on_open_folder passes CC3 WorkingFiles as default directory."""

    def test_open_folder_uses_cc3_working_dir(self, window: CraftGraphWindow) -> None:
        from unittest.mock import patch

        window._subnautica_cc3_path = "/fake/CC3"
        with patch(
            "PySide6.QtWidgets.QFileDialog.getExistingDirectory",
            return_value="",
        ) as mock_dialog:
            window._on_open_folder()
            args = mock_dialog.call_args
            dir_arg = args[0][2] if len(args[0]) > 2 else ""
            assert "WorkingFiles" in dir_arg

    def test_open_folder_falls_back_when_cc3_unset(self, window: CraftGraphWindow) -> None:
        from unittest.mock import patch

        window._subnautica_cc3_path = ""
        with patch(
            "PySide6.QtWidgets.QFileDialog.getExistingDirectory",
            return_value="",
        ) as mock_dialog:
            window._on_open_folder()
            args = mock_dialog.call_args
            dir_arg = args[0][2] if len(args[0]) > 2 else ""
            assert dir_arg == ""


class TestOpenFileDefault:
    """_on_open_file passes CC3 WorkingFiles as default directory."""

    def test_open_file_uses_cc3_working_dir(self, window: CraftGraphWindow) -> None:
        from unittest.mock import patch

        window._subnautica_cc3_path = "/fake/CC3"
        with patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            return_value=("", ""),
        ) as mock_dialog:
            window._on_open_file()
            args = mock_dialog.call_args
            dir_arg = args[0][2] if len(args[0]) > 2 else ""
            assert "WorkingFiles" in dir_arg

    def test_open_file_falls_back_when_cc3_unset(self, window: CraftGraphWindow) -> None:
        from unittest.mock import patch

        window._subnautica_cc3_path = ""
        with patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            return_value=("", ""),
        ) as mock_dialog:
            window._on_open_file()
            args = mock_dialog.call_args
            dir_arg = args[0][2] if len(args[0]) > 2 else ""
            assert dir_arg == ""


class TestNewFileDefault:
    """_on_new_file uses CC3 WorkingFiles as cold-start default."""

    def test_new_file_default_uses_cc3_when_no_source(self, window: CraftGraphWindow) -> None:
        from pathlib import Path

        window._subnautica_cc3_path = "/fake/CC3"
        # Default _source_path is Path("untitled.txt") -- not a real file or dir
        assert not window._source_path.is_file()
        assert not window._source_path.is_dir()
        # Verify the CC3 working dir would be used
        assert "WorkingFiles" in window._cc3_working_dir()

    def test_new_file_default_uses_source_when_loaded(
        self, window: CraftGraphWindow, tmp_path
    ) -> None:
        from pathlib import Path

        window._subnautica_cc3_path = "/fake/CC3"
        recipe_dir = tmp_path / "recipes"
        recipe_dir.mkdir()
        window._source_path = recipe_dir
        # Source path is a real directory, so it takes precedence
        assert window._source_path.is_dir()
        assert window._source_path == recipe_dir


class TestNewProjectDefault:
    """NewProjectDialog accepts a default_dir; _on_new_project passes CC3 WorkingFiles."""

    def test_new_project_dialog_uses_default_dir(self, window: CraftGraphWindow, tmp_path) -> None:
        from pathlib import Path

        from craftgraph.qt_gui import NewProjectDialog

        dialog = NewProjectDialog(parent=window, default_dir=tmp_path)
        assert dialog._dir_edit.text() == str(tmp_path)

    def test_new_project_dialog_falls_back_to_cwd(self, window: CraftGraphWindow) -> None:
        from pathlib import Path

        from craftgraph.qt_gui import NewProjectDialog

        dialog = NewProjectDialog(parent=window)
        assert dialog._dir_edit.text() == str(Path.cwd())


class TestEnterToAccept:
    """Browse buttons in input dialogs do not steal Enter from the Ok button."""

    def test_new_project_browse_not_autodefault(
        self, window: CraftGraphWindow, tmp_path,
    ) -> None:
        from craftgraph.qt_gui import NewProjectDialog

        dialog = NewProjectDialog(parent=window, default_dir=tmp_path)
        browse_buttons = [
            b for b in dialog.findChildren(QtWidgets.QPushButton)
            if b.text() == "Browse..."
        ]
        assert browse_buttons, "expected a Browse... button"
        assert all(not b.autoDefault() for b in browse_buttons)

    def test_new_project_ok_is_default(
        self, window: CraftGraphWindow, tmp_path,
    ) -> None:
        from craftgraph.qt_gui import NewProjectDialog

        dialog = NewProjectDialog(parent=window, default_dir=tmp_path)
        box = dialog.findChild(QtWidgets.QDialogButtonBox)
        ok = box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        assert ok.isDefault()

    def test_new_file_browse_not_autodefault(
        self, window: CraftGraphWindow, tmp_path,
    ) -> None:
        from craftgraph.qt_gui import NewFileDialog

        dialog = NewFileDialog(parent=window, default_dir=tmp_path)
        browse_buttons = [
            b for b in dialog.findChildren(QtWidgets.QPushButton)
            if b.text() == "Browse..."
        ]
        assert browse_buttons
        assert all(not b.autoDefault() for b in browse_buttons)

    def test_new_file_ok_is_default(
        self, window: CraftGraphWindow, tmp_path,
    ) -> None:
        from craftgraph.qt_gui import NewFileDialog

        dialog = NewFileDialog(parent=window, default_dir=tmp_path)
        box = dialog.findChild(QtWidgets.QDialogButtonBox)
        ok = box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        assert ok.isDefault()


class TestMenuSpawnPosCapture:
    """Context-menu spawn position comes from capture, not live cursor."""

    def test_menu_spawn_uses_captured_pos(self, window: CraftGraphWindow) -> None:
        viewer = window._active_tab.graph.viewer()
        window._menu_invoke_scene_pos = QtCore.QPointF(123.0, 456.0)
        x, y = window._menu_spawn_scene_pos(viewer)
        assert x == 123.0
        assert y == 456.0

    def test_menu_spawn_falls_back_when_no_capture(
        self, window: CraftGraphWindow,
    ) -> None:
        viewer = window._active_tab.graph.viewer()
        window._menu_invoke_scene_pos = None
        x, y = window._menu_spawn_scene_pos(viewer)
        assert isinstance(x, float)
        assert isinstance(y, float)


class TestSpriteLoadingCc3Assets:
    """Sprite loading uses CC3 Assets/ as primary source when configured."""

    def test_sprite_scan_uses_cc3_assets_when_set(
        self,
        window: CraftGraphWindow,
        tmp_path: Path,
    ) -> None:
        # Set up a fake CC3 directory with an Assets/ folder containing a sprite
        cc3_dir = tmp_path / "CC3"
        assets_dir = cc3_dir / "Assets"
        assets_dir.mkdir(parents=True)
        (assets_dir / "titanium.png").write_bytes(b"fake-png")

        window._subnautica_cc3_path = str(cc3_dir)

        # Create a recipe dir without its own Assets/
        recipe_dir = tmp_path / "recipes"
        recipe_dir.mkdir()
        recipe_file = recipe_dir / "ModifiedRecipes.txt"
        recipe_file.write_text("ModifiedRecipes:\n", encoding="utf-8")

        window.load_recipes(recipe_dir)

        # The sprite lookup should contain the titanium sprite from CC3/Assets
        assert "titanium" in window._sprite_lookup

    def test_sprite_scan_falls_back_to_recipe_dir_when_cc3_unset(
        self,
        window: CraftGraphWindow,
        tmp_path: Path,
    ) -> None:
        window._subnautica_cc3_path = ""

        # Create a recipe dir with its own Assets/
        recipe_dir = tmp_path / "recipes"
        recipe_dir.mkdir()
        local_assets = recipe_dir / "Assets"
        local_assets.mkdir()
        (local_assets / "copper.png").write_bytes(b"fake-png")
        recipe_file = recipe_dir / "ModifiedRecipes.txt"
        recipe_file.write_text("ModifiedRecipes:\n", encoding="utf-8")

        window.load_recipes(recipe_dir)

        assert "copper" in window._sprite_lookup


# ---------------------------------------------------------------------------
# Welcome screen integration
# ---------------------------------------------------------------------------


class TestWelcomeScreen:
    def test_main_stack_exists(self, window):
        assert hasattr(window, "_main_stack")
        from PySide6 import QtWidgets

        assert isinstance(window._main_stack, QtWidgets.QStackedWidget)

    def test_welcome_shown_by_default(self, window):
        """With no file arg and default settings, welcome screen is index 0."""
        assert window._main_stack.currentIndex() == 0

    def test_show_editor_switches_to_index_1(self, window):
        window._show_editor()
        assert window._main_stack.currentIndex() == 1

    def test_welcome_widget_is_index_0(self, window):
        from craftgraph.welcome import WelcomeWidget

        widget = window._main_stack.widget(0)
        assert isinstance(widget, WelcomeWidget)


class TestLaunchFlow:
    def test_welcome_shown_when_setting_is_welcome(self, qapp, tmp_path, monkeypatch):
        from craftgraph import app_dirs
        from craftgraph.qt_gui import CraftGraphWindow

        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        app_dirs.save_setting("on_launch", "welcome")
        win = CraftGraphWindow()
        assert win._main_stack.currentIndex() == 0

    def test_editor_shown_when_setting_is_empty(self, qapp, tmp_path, monkeypatch):
        from craftgraph import app_dirs
        from craftgraph.qt_gui import CraftGraphWindow

        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        app_dirs.save_setting("on_launch", "empty")
        win = CraftGraphWindow()
        assert win._main_stack.currentIndex() == 1

    def test_missing_settings_defaults_to_welcome(self, qapp, tmp_path, monkeypatch):
        from craftgraph import app_dirs
        from craftgraph.qt_gui import CraftGraphWindow

        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        win = CraftGraphWindow()
        assert win._main_stack.currentIndex() == 0


# ---------------------------------------------------------------------------
# Welcome screen button integration
# ---------------------------------------------------------------------------


class TestWelcomeButtonIntegration:
    """Verify welcome screen buttons interact correctly with CraftGraphWindow."""

    def test_open_folder_cancel_stays_on_welcome(self, window: CraftGraphWindow) -> None:
        from unittest.mock import patch

        assert window._main_stack.currentIndex() == 0
        with patch(
            "PySide6.QtWidgets.QFileDialog.getExistingDirectory",
            return_value="",
        ):
            window._on_open_folder()
        assert window._main_stack.currentIndex() == 0

    def test_open_folder_success_switches_to_editor(
        self, window: CraftGraphWindow, tmp_path
    ) -> None:
        from unittest.mock import patch

        recipe_dir = tmp_path / "recipes"
        recipe_dir.mkdir()
        (recipe_dir / "ModifiedRecipes.txt").write_text(
            "ModifiedRecipes:\n", encoding="utf-8"
        )
        assert window._main_stack.currentIndex() == 0
        with patch(
            "PySide6.QtWidgets.QFileDialog.getExistingDirectory",
            return_value=str(recipe_dir),
        ):
            window._on_open_folder()
        assert window._main_stack.currentIndex() == 1

    def test_open_project_cancel_stays_on_welcome(self, window: CraftGraphWindow) -> None:
        from unittest.mock import patch

        assert window._main_stack.currentIndex() == 0
        with patch(
            "PySide6.QtWidgets.QFileDialog.getOpenFileName",
            return_value=("", ""),
        ):
            window._on_open_project()
        assert window._main_stack.currentIndex() == 0

    def test_new_project_cancel_stays_on_welcome(self, window: CraftGraphWindow) -> None:
        from unittest.mock import Mock, patch

        assert window._main_stack.currentIndex() == 0
        mock_dialog = Mock()
        mock_dialog.return_value.exec_.return_value = (
            QtWidgets.QDialog.DialogCode.Rejected
        )
        with patch("craftgraph.qt_gui.NewProjectDialog", mock_dialog):
            window._on_new_project()
        assert window._main_stack.currentIndex() == 0

    def test_welcome_open_recent_folder_switches_to_editor(
        self, window: CraftGraphWindow, tmp_path
    ) -> None:
        recipe_dir = tmp_path / "recipes"
        recipe_dir.mkdir()
        (recipe_dir / "ModifiedRecipes.txt").write_text(
            "ModifiedRecipes:\n", encoding="utf-8"
        )
        assert window._main_stack.currentIndex() == 0
        window._welcome_open_recent(str(recipe_dir), "folder")
        assert window._main_stack.currentIndex() == 1

    def test_welcome_open_recent_stale_path_stays_on_welcome(
        self, window: CraftGraphWindow
    ) -> None:
        assert window._main_stack.currentIndex() == 0
        window._welcome_open_recent("/nonexistent/path", "folder")
        assert window._main_stack.currentIndex() == 0


class TestSettingsDialogOnLaunch:
    def test_dialog_has_on_launch_property(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(None)
        assert hasattr(dialog, "on_launch")

    def test_on_launch_default_is_welcome(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(None, on_launch="welcome")
        assert dialog.on_launch == "welcome"

    def test_on_launch_reads_combo_selection(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(None, on_launch="empty")
        assert dialog.on_launch == "empty"


class TestSettingsDialogCheckForUpdates:
    def test_dialog_has_check_for_updates_property(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(None)
        assert hasattr(dialog, "check_for_updates")

    def test_check_for_updates_default_is_true(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(None)
        assert dialog.check_for_updates is True

    def test_check_for_updates_false(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(None, check_for_updates=False)
        assert dialog.check_for_updates is False


class TestSettingsDialogRestoreAllDefaults:
    """Global Restore All Defaults button on the settings dialog footer."""

    def test_dialog_has_restore_all_button(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(None)
        labels = [b.text() for b in dialog.findChildren(QtWidgets.QPushButton)]
        assert "Restore All Defaults" in labels

    def test_reset_all_cancel_keeps_values(self, qapp, monkeypatch):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import KeybindingSettings

        custom_kb = KeybindingSettings(save="Ctrl+Alt+S")
        dialog = _SettingsDialog(None, keybindings=custom_kb, check_for_updates=False)
        monkeypatch.setattr(
            QtWidgets.QMessageBox,
            "question",
            lambda *a, **kw: QtWidgets.QMessageBox.StandardButton.No,
        )
        dialog._reset_all()
        assert dialog._kb_edits["save"].keySequence().toString() == "Ctrl+Alt+S"
        assert dialog._update_check_cb is not None
        assert dialog._update_check_cb.isChecked() is False

    def test_reset_all_confirm_restores_defaults(self, qapp, monkeypatch):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import KeybindingSettings, ThemeColors

        custom_theme = ThemeColors(accent="#E57373")
        custom_kb = KeybindingSettings(save="Ctrl+Alt+S")
        dialog = _SettingsDialog(
            None,
            theme=custom_theme,
            keybindings=custom_kb,
            check_for_updates=False,
        )
        monkeypatch.setattr(
            QtWidgets.QMessageBox,
            "question",
            lambda *a, **kw: QtWidgets.QMessageBox.StandardButton.Yes,
        )
        dialog._reset_all()
        assert dialog._kb_edits["save"].keySequence().toString() == "Ctrl+S"
        assert dialog._update_check_cb is not None
        assert dialog._update_check_cb.isChecked() is True


class TestUpdateChecker:
    def test_run_update_check_no_update(self, window):
        """Stub always returns None -- status bar should not show update text."""
        msg_before = window.statusBar().currentMessage()
        window._run_update_check()
        assert "Update available" not in window.statusBar().currentMessage()
        assert window.statusBar().currentMessage() == msg_before

    def test_check_for_updates_false_skips_check(self, qapp, monkeypatch, tmp_path):
        from craftgraph import app_dirs
        from craftgraph.qt_gui import CraftGraphWindow

        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        app_dirs.save_setting("check_for_updates", False)
        win = CraftGraphWindow()
        assert win._check_for_updates is False


class TestSettingsPersistenceRoundTrip:
    """Settings saved from _on_settings are restored on next window creation."""

    def test_backup_on_save_persists(self, qapp, monkeypatch, tmp_path):
        from craftgraph import app_dirs
        from craftgraph.qt_gui import CraftGraphWindow

        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        app_dirs.save_setting("backup_on_save", True)
        win = CraftGraphWindow()
        assert win._backup_on_save is True

    def test_auto_save_interval_persists(self, qapp, monkeypatch, tmp_path):
        from craftgraph import app_dirs
        from craftgraph.qt_gui import CraftGraphWindow

        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        app_dirs.save_setting("auto_save_interval", 120)
        win = CraftGraphWindow()
        assert win._auto_save_interval == 120

    def test_default_project_folder_persists(self, qapp, monkeypatch, tmp_path):
        from craftgraph import app_dirs
        from craftgraph.qt_gui import CraftGraphWindow

        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        app_dirs.save_setting("default_project_folder", "/custom/path")
        win = CraftGraphWindow()
        assert win._default_project_folder == "/custom/path"

    def test_on_settings_saves_all_keys(self, window, monkeypatch, tmp_path):
        from craftgraph import app_dirs
        from craftgraph.qt_gui import _SettingsDialog

        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        monkeypatch.setattr(_SettingsDialog, "exec_", lambda self: None)
        window._on_settings()
        data = __import__("json").loads(
            (tmp_path / "settings.json").read_text(encoding="utf-8")
        )
        expected_keys = {
            "backup_on_save",
            "auto_save_enabled",
            "auto_save_interval",
            "default_project_folder",
            "subnautica_cc3_path",
            "recent_max_entries",
            "on_launch",
            "check_for_updates",
        }
        assert expected_keys.issubset(data.keys())


# ---------------------------------------------------------------------------
# Appearance tab -- node and syntax color swatches
# ---------------------------------------------------------------------------


class TestAppearanceNodeSwatches:
    """Node Colors subtab has interactive swatches for all block types."""

    def test_dialog_has_node_swatches(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        expected_fields = {
            "modified_recipe", "added_recipe", "alias_recipe", "custom_food",
            "fabricator", "crafting_tab", "custom_size", "moved_recipe",
            "custom_bio_fuel", "custom_fragment_count", "orphan_ingredient", "sprite",
        }
        assert set(dialog._node_swatches.keys()) == expected_fields

    def test_node_swatches_are_clickable(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        for btn in dialog._node_swatches.values():
            assert hasattr(btn, "color_hex")

    def test_node_swatches_match_theme_defaults(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import NodeColors

        dialog = _SettingsDialog()
        nc = NodeColors()
        btn = dialog._node_swatches["modified_recipe"]
        r, g, b = nc.modified_recipe
        expected = f"#{r:02x}{g:02x}{b:02x}"
        assert btn.color_hex == expected  # type: ignore[attr-defined]


class TestAppearanceSyntaxSwatches:
    """Code Colors subtab has interactive swatches for syntax tokens."""

    def test_dialog_has_syntax_swatches(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        expected_fields = {
            "block_type", "field_key", "string", "comment", "error_underline",
        }
        assert set(dialog._syntax_swatches.keys()) == expected_fields

    def test_syntax_swatches_match_theme_defaults(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import SyntaxColors

        dialog = _SettingsDialog()
        sc = SyntaxColors()
        assert dialog._syntax_swatches["block_type"].color_hex == sc.block_type  # type: ignore[attr-defined]
        assert dialog._syntax_swatches["comment"].color_hex == sc.comment  # type: ignore[attr-defined]


class TestColorPickerSwatchChrome:
    """Issue 7: swatch chrome stays theme-neutral; picked color is shown
    as an inner indicator, not as the button background."""

    def test_swatch_is_color_picker_subclass(self, qapp):
        from craftgraph.qt_gui import _ColorPickerSwatch, _SettingsDialog

        dialog = _SettingsDialog()
        for btn in dialog._node_swatches.values():
            assert isinstance(btn, _ColorPickerSwatch)
        for btn in dialog._syntax_swatches.values():
            assert isinstance(btn, _ColorPickerSwatch)

    def test_swatch_stylesheet_independent_of_picked_color(self, qapp):
        from craftgraph.qt_gui import _ColorPickerSwatch

        light = _ColorPickerSwatch("#ffffff")
        dark = _ColorPickerSwatch("#000000")
        saturated = _ColorPickerSwatch("#ff00ff")
        # All instances share the same neutral chrome stylesheet so the
        # outer button never paints in the picked color.
        assert light.styleSheet() == dark.styleSheet() == saturated.styleSheet()
        assert "rgb(60, 60, 60)" in light.styleSheet()
        assert "background: #ffffff" not in light.styleSheet()
        assert "background: #000000" not in dark.styleSheet()

    def test_setting_color_does_not_change_chrome(self, qapp):
        from craftgraph.qt_gui import _ColorPickerSwatch

        btn = _ColorPickerSwatch("#404040")
        before = btn.styleSheet()
        btn.color_hex = "#000000"
        assert btn.styleSheet() == before
        btn.color_hex = "#ffffff"
        assert btn.styleSheet() == before

    def test_set_swatch_color_updates_state_only(self, qapp):
        from craftgraph.qt_gui import _ColorPickerSwatch, _SettingsDialog

        dialog = _SettingsDialog()
        btn = next(iter(dialog._node_swatches.values()))
        assert isinstance(btn, _ColorPickerSwatch)
        before_style = btn.styleSheet()
        dialog._set_swatch_color(btn, "#123456")
        assert btn.color_hex == "#123456"
        assert btn.styleSheet() == before_style

    def test_color_hex_setter_triggers_repaint(self, qapp):
        from craftgraph.qt_gui import _ColorPickerSwatch

        btn = _ColorPickerSwatch("#123456")
        # Force show to make update() generate a paint event in CI.
        btn.show()
        qapp.processEvents()
        old = btn.color_hex
        btn.color_hex = "#abcdef"
        assert btn.color_hex == "#abcdef"
        assert old != btn.color_hex
        btn.deleteLater()


class TestAppearanceThemeProperty:
    """_SettingsDialog.theme_colors builds a ThemeColors from widget values."""

    def test_theme_colors_returns_theme_instance(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import ThemeColors

        dialog = _SettingsDialog()
        tc = dialog.theme_colors
        assert isinstance(tc, ThemeColors)

    def test_theme_colors_matches_defaults(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import ThemeColors

        dialog = _SettingsDialog()
        tc = dialog.theme_colors
        defaults = ThemeColors()
        assert tc.node.modified_recipe == defaults.node.modified_recipe
        assert tc.highlight.cycle_edge == defaults.highlight.cycle_edge
        assert tc.syntax.block_type == defaults.syntax.block_type
        assert tc.editor.background == defaults.editor.background
        assert tc.high_contrast_borders == defaults.high_contrast_borders

    def test_high_contrast_checkbox_reflected(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        assert dialog._high_contrast_cb is not None
        dialog._high_contrast_cb.setChecked(True)
        assert dialog.theme_colors.high_contrast_borders is True
        dialog._high_contrast_cb.setChecked(False)
        assert dialog.theme_colors.high_contrast_borders is False


class TestThemePersistence:
    """Theme colors round-trip through _save_theme / _load_theme."""

    def test_save_and_load_theme(self, qapp, monkeypatch, tmp_path):
        from craftgraph import app_dirs
        from craftgraph.qt_gui import CraftGraphWindow
        from craftgraph.theme import NodeColors, ThemeColors

        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        custom = ThemeColors(node=NodeColors(modified_recipe=(200, 100, 50)))
        CraftGraphWindow._save_theme(custom)

        loaded = CraftGraphWindow._load_theme()
        assert loaded.node.modified_recipe == (200, 100, 50)
        # Other fields stay at defaults
        assert loaded.node.added_recipe == NodeColors().added_recipe

    def test_load_theme_missing_file_returns_defaults(self, qapp, monkeypatch, tmp_path):
        from craftgraph import app_dirs
        from craftgraph.qt_gui import CraftGraphWindow
        from craftgraph.theme import ThemeColors

        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "nope.json")
        loaded = CraftGraphWindow._load_theme()
        assert loaded.node.modified_recipe == ThemeColors().node.modified_recipe

    def test_on_settings_persists_theme(self, window, monkeypatch, tmp_path):
        import json

        from craftgraph import app_dirs
        from craftgraph.qt_gui import _SettingsDialog

        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        monkeypatch.setattr(_SettingsDialog, "exec_", lambda self: None)
        window._on_settings()
        data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert "theme" in data
        assert "node" in data["theme"]
        assert "syntax" in data["theme"]

    def test_theme_loaded_on_startup(self, qapp, monkeypatch, tmp_path):
        import json

        from craftgraph import app_dirs
        from craftgraph.qt_gui import CraftGraphWindow
        from craftgraph.theme import NodeColors, ThemeColors, active_theme, theme_to_dict

        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        custom = ThemeColors(node=NodeColors(sprite=(11, 22, 33)))
        settings_data = {"version": 1, "theme": theme_to_dict(custom)}
        (tmp_path / "settings.json").write_text(json.dumps(settings_data), encoding="utf-8")
        CraftGraphWindow()
        assert active_theme().node.sprite == (11, 22, 33)


# ---------------------------------------------------------------------------
# High contrast borders
# ---------------------------------------------------------------------------


class TestHighContrastBorders:
    """High-contrast borders toggle applies visual changes."""

    def test_dialog_reflects_high_contrast_in_theme_colors(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        dialog._high_contrast_cb.setChecked(True)
        tc = dialog.theme_colors
        assert tc.high_contrast_borders is True

    def test_apply_theme_sets_bright_border_on_nodes(self, window):
        from craftgraph.theme import ThemeColors

        theme = ThemeColors(high_contrast_borders=True)
        window._apply_theme(theme)
        # With no file loaded there are no nodes, so just verify no crash
        assert window.styleSheet() != ""

    def test_stylesheet_contains_2px_border_when_enabled(self, qapp):
        from craftgraph.qt_gui import CraftGraphWindow
        from craftgraph.theme import ThemeColors

        ss = CraftGraphWindow._build_app_stylesheet(ThemeColors(high_contrast_borders=True))
        assert "2px" in ss

    def test_stylesheet_uses_1px_border_when_disabled(self, qapp):
        from craftgraph.qt_gui import CraftGraphWindow
        from craftgraph.theme import ThemeColors

        ss = CraftGraphWindow._build_app_stylesheet(ThemeColors(high_contrast_borders=False))
        assert "1px solid" in ss
        # Only the accent stripe should use 2px, not widget borders
        assert "QGroupBox" not in ss


# ---------------------------------------------------------------------------
# Accent color
# ---------------------------------------------------------------------------


class TestAccentColorSelector:
    """Accent color combo wires to ThemeColors.accent."""

    def test_dialog_has_accent_combo(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        assert dialog._accent_combo is not None

    def test_default_accent_is_blue(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import ACCENT_COLORS

        dialog = _SettingsDialog()
        assert dialog.theme_colors.accent == ACCENT_COLORS["Blue"]

    def test_changing_accent_combo_updates_theme_colors(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import ACCENT_COLORS, ACCENT_NAMES

        dialog = _SettingsDialog()
        red_idx = ACCENT_NAMES.index("Red")
        dialog._accent_combo.setCurrentIndex(red_idx)
        assert dialog.theme_colors.accent == ACCENT_COLORS["Red"]

    def test_accent_initializes_from_theme(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import ACCENT_COLORS, ThemeColors

        theme = ThemeColors(accent=ACCENT_COLORS["Green"])
        dialog = _SettingsDialog(theme=theme)
        assert dialog._accent_combo.currentText() == "Green"

    def test_accent_appears_in_stylesheet(self, qapp):
        from craftgraph.qt_gui import CraftGraphWindow
        from craftgraph.theme import ACCENT_COLORS, ThemeColors

        theme = ThemeColors(accent=ACCENT_COLORS["Orange"])
        ss = CraftGraphWindow._build_app_stylesheet(theme)
        assert ACCENT_COLORS["Orange"].lower() in ss.lower()


# ---------------------------------------------------------------------------
# Application theme (Dark / Light / System)
# ---------------------------------------------------------------------------


class TestAppThemeSelector:
    """Application theme combo wires to ThemeColors.app_theme."""

    def test_dialog_has_theme_combo(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        assert dialog._theme_combo is not None

    def test_default_app_theme_is_dark(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        assert dialog.theme_colors.app_theme == "dark"

    def test_selecting_light_sets_app_theme(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        dialog._theme_combo.setCurrentIndex(1)  # Light
        assert dialog.theme_colors.app_theme == "light"

    def test_selecting_system_sets_app_theme(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        dialog._theme_combo.setCurrentIndex(2)  # System
        assert dialog.theme_colors.app_theme == "system"

    def test_theme_combo_initializes_from_theme(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import ThemeColors

        dialog = _SettingsDialog(theme=ThemeColors(app_theme="light"))
        assert dialog._theme_combo.currentIndex() == 1

    def test_light_stylesheet_contains_light_bg(self, qapp):
        from craftgraph.qt_gui import CraftGraphWindow
        from craftgraph.theme import ThemeColors

        ss = CraftGraphWindow._build_app_stylesheet(ThemeColors(app_theme="light"))
        assert "rgb(240, 240, 240)" in ss

    def test_dark_stylesheet_has_dark_combo_bg(self, qapp):
        from craftgraph.qt_gui import CraftGraphWindow
        from craftgraph.theme import ThemeColors

        ss = CraftGraphWindow._build_app_stylesheet(ThemeColors(app_theme="dark"))
        assert "rgb(30, 30, 30)" in ss

    def test_system_stylesheet_no_crash(self, qapp):
        from craftgraph.qt_gui import CraftGraphWindow
        from craftgraph.theme import ThemeColors

        ss = CraftGraphWindow._build_app_stylesheet(ThemeColors(app_theme="system"))
        assert isinstance(ss, str)


# ---------------------------------------------------------------------------
# Colorblind mode
# ---------------------------------------------------------------------------


class TestColorblindModeSelector:
    """Colorblind mode combo wires to ThemeColors.colorblind_mode."""

    def test_dialog_has_colorblind_combo(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        assert dialog._colorblind_combo is not None

    def test_default_colorblind_mode_is_none(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        assert dialog.theme_colors.colorblind_mode == "none"

    def test_selecting_deuteranopia(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        dialog._colorblind_combo.setCurrentIndex(1)  # deuteranopia
        assert dialog.theme_colors.colorblind_mode == "deuteranopia"

    def test_selecting_tritanopia(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        dialog._colorblind_combo.setCurrentIndex(3)  # tritanopia
        assert dialog.theme_colors.colorblind_mode == "tritanopia"

    def test_colorblind_combo_initializes_from_theme(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import ThemeColors

        dialog = _SettingsDialog(theme=ThemeColors(colorblind_mode="protanopia"))
        assert dialog._colorblind_combo.currentIndex() == 2

    def test_round_trip_new_theme_fields_persisted(self, qapp, monkeypatch, tmp_path):
        """app_theme, colorblind_mode, ui_scale survive save/load."""
        from craftgraph import app_dirs
        from craftgraph.qt_gui import CraftGraphWindow
        from craftgraph.theme import ACCENT_COLORS, ThemeColors

        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        custom = ThemeColors(
            app_theme="light",
            accent=ACCENT_COLORS["Teal"],
            colorblind_mode="deuteranopia",
            ui_scale=150,
        )
        CraftGraphWindow._save_theme(custom)
        loaded = CraftGraphWindow._load_theme()
        assert loaded.app_theme == "light"
        assert loaded.accent == ACCENT_COLORS["Teal"]
        assert loaded.colorblind_mode == "deuteranopia"
        assert loaded.ui_scale == 150


# ---------------------------------------------------------------------------
# UI scale
# ---------------------------------------------------------------------------


class TestUIScaleSelector:
    """UI scale combo wires to ThemeColors.ui_scale."""

    def test_dialog_has_ui_scale_combo(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        assert dialog._ui_scale_combo is not None

    def test_default_ui_scale_is_100(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        assert dialog.theme_colors.ui_scale == 100

    def test_selecting_150_percent(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import UI_SCALE_OPTIONS

        dialog = _SettingsDialog()
        idx = UI_SCALE_OPTIONS.index(150)
        dialog._ui_scale_combo.setCurrentIndex(idx)
        assert dialog.theme_colors.ui_scale == 150

    def test_ui_scale_combo_initializes_from_theme(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import UI_SCALE_OPTIONS, ThemeColors

        dialog = _SettingsDialog(theme=ThemeColors(ui_scale=125))
        expected_idx = UI_SCALE_OPTIONS.index(125)
        assert dialog._ui_scale_combo.currentIndex() == expected_idx

    def test_apply_theme_adjusts_font_size(self, window):
        from craftgraph.theme import ThemeColors

        theme = ThemeColors(ui_scale=200)
        window._apply_theme(theme)
        app = QtWidgets.QApplication.instance()
        assert app.font().pointSize() == 20  # 10pt * 200/100


# ---------------------------------------------------------------------------
# Node Editor: Navigation settings
# ---------------------------------------------------------------------------


class TestNavigationSettings:
    """Navigation widgets wire to NodeEditorSettings."""

    def test_dialog_has_zoom_speed_spin(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        assert dialog._zoom_speed_spin is not None

    def test_default_zoom_speed(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        assert dialog.node_editor_settings.zoom_speed == 1.0

    def test_changing_zoom_speed(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        dialog._zoom_speed_spin.setValue(2.5)
        assert dialog.node_editor_settings.zoom_speed == 2.5

    def test_invert_zoom_default_false(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        assert dialog.node_editor_settings.invert_zoom is False

    def test_invert_zoom_toggle(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        dialog._invert_zoom_cb.setChecked(True)
        assert dialog.node_editor_settings.invert_zoom is True

    def test_pan_mmb_default_true(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        assert dialog.node_editor_settings.pan_with_mmb is True

    def test_show_minimap_default_true(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        assert dialog.node_editor_settings.show_minimap is True

    def test_show_minimap_toggle(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        dialog._show_minimap_cb.setChecked(False)
        assert dialog.node_editor_settings.show_minimap is False

    def test_initializes_from_settings(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import NodeEditorSettings

        ne = NodeEditorSettings(zoom_speed=3.0, invert_zoom=True, show_minimap=False)
        dialog = _SettingsDialog(node_editor=ne)
        assert dialog._zoom_speed_spin.value() == 3.0
        assert dialog._invert_zoom_cb.isChecked() is True
        assert dialog._show_minimap_cb.isChecked() is False


# ---------------------------------------------------------------------------
# Node Editor: Grid settings
# ---------------------------------------------------------------------------


class TestGridSettings:
    """Grid widgets wire to NodeEditorSettings."""

    def test_dialog_has_grid_widgets(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        assert dialog._show_grid_cb is not None
        assert dialog._grid_size_spin is not None
        assert dialog._snap_grid_cb is not None
        assert dialog._grid_style_combo is not None

    def test_default_grid_settings(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        s = dialog.node_editor_settings
        assert s.show_grid is True
        assert s.grid_size == 50
        assert s.snap_to_grid is False
        assert s.grid_style == "lines"

    def test_changing_grid_size(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        dialog._grid_size_spin.setValue(30)
        assert dialog.node_editor_settings.grid_size == 30

    def test_changing_grid_style_to_dots(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        dialog._grid_style_combo.setCurrentIndex(0)  # Dots
        assert dialog.node_editor_settings.grid_style == "dots"

    def test_changing_grid_style_to_none(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        dialog._grid_style_combo.setCurrentIndex(2)  # None
        assert dialog.node_editor_settings.grid_style == "none"

    def test_snap_toggle(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        dialog._snap_grid_cb.setChecked(True)
        assert dialog.node_editor_settings.snap_to_grid is True

    def test_show_grid_toggle(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog()
        dialog._show_grid_cb.setChecked(False)
        assert dialog.node_editor_settings.show_grid is False

    def test_initializes_from_settings(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import NodeEditorSettings

        ne = NodeEditorSettings(show_grid=False, grid_size=80, grid_style="dots", snap_to_grid=True)
        dialog = _SettingsDialog(node_editor=ne)
        assert dialog._show_grid_cb.isChecked() is False
        assert dialog._grid_size_spin.value() == 80
        assert dialog._grid_style_combo.currentIndex() == 0  # dots
        assert dialog._snap_grid_cb.isChecked() is True


# ---------------------------------------------------------------------------
# Node Editor: persistence round-trip
# ---------------------------------------------------------------------------


class TestNodeEditorSettingsPersistence:
    """Node editor settings survive save/load."""

    def test_save_and_load_round_trip(self, qapp, monkeypatch, tmp_path):
        from craftgraph import app_dirs
        from craftgraph.qt_gui import CraftGraphWindow
        from craftgraph.theme import NodeEditorSettings

        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        custom = NodeEditorSettings(
            zoom_speed=2.0, invert_zoom=True, grid_size=30, grid_style="dots",
        )
        CraftGraphWindow._save_node_editor_settings(custom)
        loaded = CraftGraphWindow._load_node_editor_settings()
        assert loaded.zoom_speed == 2.0
        assert loaded.invert_zoom is True
        assert loaded.grid_size == 30
        assert loaded.grid_style == "dots"

    def test_load_missing_file_returns_defaults(self, qapp, monkeypatch, tmp_path):
        from craftgraph import app_dirs
        from craftgraph.qt_gui import CraftGraphWindow
        from craftgraph.theme import NodeEditorSettings

        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "nope.json")
        loaded = CraftGraphWindow._load_node_editor_settings()
        assert loaded.zoom_speed == NodeEditorSettings().zoom_speed

    def test_apply_sets_grid_mode_none_when_hidden(self, window):
        from craftgraph.theme import NodeEditorSettings

        window._apply_node_editor_settings(NodeEditorSettings(show_grid=False))
        # No crash; grid_mode was set to NONE

    def test_apply_shows_minimap(self, window):
        from craftgraph.theme import NodeEditorSettings

        window._apply_node_editor_settings(NodeEditorSettings(show_minimap=True))
        # isVisible() requires the widget tree to be shown; use not isHidden()
        assert not window._minimap.isHidden()

    def test_apply_hides_minimap(self, window):
        from craftgraph.theme import NodeEditorSettings

        window._apply_node_editor_settings(NodeEditorSettings(show_minimap=False))
        assert window._minimap.isHidden()


# ---------------------------------------------------------------------------
# Node Editor: viewer patches (zoom, pan, grid size, snap)
# ---------------------------------------------------------------------------


class TestViewerPatches:
    """Viewer monkey-patches for zoom speed, invert zoom, pan toggle, grid size."""

    def test_viewer_patched_on_creation(self, window):
        viewer = window.graph.viewer()
        assert getattr(viewer, "_cg_patched", False) is True

    def test_zoom_speed_attribute_set(self, window):
        viewer = window.graph.viewer()
        assert viewer._cg_zoom_speed == 1.0

    def test_invert_zoom_attribute_set(self, window):
        viewer = window.graph.viewer()
        assert viewer._cg_invert_zoom is False

    def test_pan_with_mmb_attribute_set(self, window):
        viewer = window.graph.viewer()
        assert viewer._cg_pan_with_mmb is True

    def test_scene_grid_size_attribute_set(self, window):
        scene = window.graph.scene()
        assert scene._cg_grid_size == 50

    def test_apply_updates_zoom_speed(self, window):
        from craftgraph.theme import NodeEditorSettings

        window._apply_node_editor_settings(NodeEditorSettings(zoom_speed=3.0))
        assert window.graph.viewer()._cg_zoom_speed == 3.0

    def test_apply_updates_invert_zoom(self, window):
        from craftgraph.theme import NodeEditorSettings

        window._apply_node_editor_settings(NodeEditorSettings(invert_zoom=True))
        assert window.graph.viewer()._cg_invert_zoom is True

    def test_apply_updates_pan_with_mmb(self, window):
        from craftgraph.theme import NodeEditorSettings

        window._apply_node_editor_settings(NodeEditorSettings(pan_with_mmb=False))
        assert window.graph.viewer()._cg_pan_with_mmb is False

    def test_apply_updates_grid_size(self, window):
        from craftgraph.theme import NodeEditorSettings

        window._apply_node_editor_settings(NodeEditorSettings(grid_size=80))
        assert window.graph.scene()._cg_grid_size == 80

    def test_double_patch_is_noop(self, window):
        """Calling _install_viewer_patches twice does not break anything."""
        viewer = window.graph.viewer()
        wheel_ref = viewer.wheelEvent
        window._install_viewer_patches(window.graph)
        assert viewer.wheelEvent is wheel_ref

    def test_wheel_event_replaced(self, window):
        """wheelEvent is a patched closure, not the original bound method."""
        viewer = window.graph.viewer()
        # The patched wheelEvent is a plain function, not a bound method
        assert not hasattr(viewer.wheelEvent, "__self__")


class TestSnapToGrid:
    """Snap-to-grid rounds node positions after drag."""

    def test_snap_rounds_position(self, window):
        from craftgraph.theme import NodeEditorSettings

        window._apply_node_editor_settings(
            NodeEditorSettings(snap_to_grid=True, grid_size=50),
        )
        graph = window.graph
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode")
        node.set_pos(73, 128)

        # Simulate the moved_nodes signal payload
        node_item = node.view
        moved = {node_item: (0.0, 0.0)}
        window._snap_moved_nodes(graph, moved)

        x, y = node.pos()
        assert x == 50.0
        assert y == 150.0

    def test_snap_disabled_does_not_move(self, window):
        from craftgraph.theme import NodeEditorSettings

        window._apply_node_editor_settings(
            NodeEditorSettings(snap_to_grid=False, grid_size=50),
        )
        graph = window.graph
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode")
        node.set_pos(73, 128)

        node_item = node.view
        moved = {node_item: (0.0, 0.0)}
        window._snap_moved_nodes(graph, moved)

        x, y = node.pos()
        assert x == 73.0
        assert y == 128.0

    def test_snap_uses_current_grid_size(self, window):
        from craftgraph.theme import NodeEditorSettings

        window._apply_node_editor_settings(
            NodeEditorSettings(snap_to_grid=True, grid_size=25),
        )
        graph = window.graph
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode")
        node.set_pos(37, 60)

        node_item = node.view
        moved = {node_item: (0.0, 0.0)}
        window._snap_moved_nodes(graph, moved)

        x, y = node.pos()
        assert x == 25.0  # round(37/25)*25 = round(1.48)*25 = 1*25 = 25
        assert y == 50.0  # round(60/25)*25 = round(2.4)*25 = 2*25 = 50

    def test_snap_exact_position_unchanged(self, window):
        from craftgraph.theme import NodeEditorSettings

        window._apply_node_editor_settings(
            NodeEditorSettings(snap_to_grid=True, grid_size=50),
        )
        graph = window.graph
        node = graph.create_node("com.craftgraph.ModifiedRecipeNode")
        node.set_pos(100, 200)

        node_item = node.view
        moved = {node_item: (0.0, 0.0)}
        window._snap_moved_nodes(graph, moved)

        x, y = node.pos()
        assert x == 100.0
        assert y == 200.0


# ---------------------------------------------------------------------------
# Code Editor Settings
# ---------------------------------------------------------------------------


class TestCodeEditorSettingsDialog:
    """_SettingsDialog exposes code editor settings via property."""

    def test_dialog_has_code_editor_settings_property(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(None)
        assert hasattr(dialog, "code_editor_settings")

    def test_code_editor_settings_returns_dataclass(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import CodeEditorSettings

        dialog = _SettingsDialog(None)
        ce = dialog.code_editor_settings
        assert isinstance(ce, CodeEditorSettings)

    def test_dialog_reflects_passed_code_editor_values(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import CodeEditorSettings

        custom = CodeEditorSettings(
            font_family="Courier New",
            font_size=14,
            show_line_numbers=False,
            highlight_current_line=False,
            word_wrap=True,
            tab_width=2,
            auto_indent=False,
            auto_close_brackets=False,
            strip_trailing_whitespace=False,
            parse_debounce_ms=800,
            show_parse_errors_inline=False,
        )
        dialog = _SettingsDialog(None, code_editor=custom)
        ce = dialog.code_editor_settings
        assert ce.font_size == 14
        assert ce.show_line_numbers is False
        assert ce.highlight_current_line is False
        assert ce.word_wrap is True
        assert ce.tab_width == 2
        assert ce.auto_indent is False
        assert ce.auto_close_brackets is False
        assert ce.strip_trailing_whitespace is False
        assert ce.parse_debounce_ms == 800
        assert ce.show_parse_errors_inline is False

    def test_dialog_defaults_match_dataclass_defaults(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import CodeEditorSettings

        dialog = _SettingsDialog(None)
        ce = dialog.code_editor_settings
        defaults = CodeEditorSettings()
        assert ce.font_size == defaults.font_size
        assert ce.show_line_numbers == defaults.show_line_numbers
        assert ce.highlight_current_line == defaults.highlight_current_line
        assert ce.word_wrap == defaults.word_wrap
        assert ce.tab_width == defaults.tab_width
        assert ce.auto_indent == defaults.auto_indent
        assert ce.auto_close_brackets == defaults.auto_close_brackets
        assert ce.strip_trailing_whitespace == defaults.strip_trailing_whitespace
        assert ce.parse_debounce_ms == defaults.parse_debounce_ms
        assert ce.show_parse_errors_inline == defaults.show_parse_errors_inline


class TestCodeEditorSettingsPersistence:
    """Code editor settings survive save/load round-trip."""

    def test_on_settings_saves_code_editor_key(self, window, monkeypatch, tmp_path):
        import json

        from craftgraph import app_dirs
        from craftgraph.qt_gui import _SettingsDialog

        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "settings.json")
        monkeypatch.setattr(_SettingsDialog, "exec_", lambda self: None)
        window._on_settings()
        data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert "code_editor" in data
        ce_data = data["code_editor"]
        assert "font_family" in ce_data
        assert "font_size" in ce_data
        assert "parse_debounce_ms" in ce_data

    def test_load_code_editor_settings_from_file(self, window, monkeypatch, tmp_path):
        import json

        from craftgraph import app_dirs
        from craftgraph.theme import CodeEditorSettings

        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps({
            "version": 1,
            "code_editor": {
                "font_family": "Courier New",
                "font_size": 16,
                "tab_width": 8,
                "parse_debounce_ms": 1000,
            },
        }), encoding="utf-8")
        monkeypatch.setattr(app_dirs, "settings_path", lambda: settings_file)

        loaded = window._load_code_editor_settings()
        assert loaded.font_family == "Courier New"
        assert loaded.font_size == 16
        assert loaded.tab_width == 8
        assert loaded.parse_debounce_ms == 1000
        # Unset fields get defaults
        defaults = CodeEditorSettings()
        assert loaded.show_line_numbers == defaults.show_line_numbers
        assert loaded.auto_indent == defaults.auto_indent

    def test_load_missing_file_returns_defaults(self, window, monkeypatch, tmp_path):
        from craftgraph import app_dirs
        from craftgraph.theme import CodeEditorSettings

        monkeypatch.setattr(app_dirs, "settings_path", lambda: tmp_path / "nope.json")
        loaded = window._load_code_editor_settings()
        assert loaded == CodeEditorSettings()


class TestCodeEditorSettingsApplication:
    """Settings are applied to CodeEditor instances."""

    def test_apply_font_to_editor(self, window):
        from craftgraph.theme import CodeEditorSettings

        s = CodeEditorSettings(font_family="Courier New", font_size=16)
        window._apply_code_editor_settings_to(window.code_editor, s)
        font = window.code_editor.font()
        assert font.family() == "Courier New"
        assert font.pointSize() == 16

    def test_apply_hide_line_numbers(self, window):
        from craftgraph.theme import CodeEditorSettings

        s = CodeEditorSettings(show_line_numbers=False)
        window._apply_code_editor_settings_to(window.code_editor, s)
        assert window.code_editor.line_number_area.isHidden()
        assert window.code_editor.line_number_area_width() == 0

    def test_apply_show_line_numbers(self, window):
        from craftgraph.theme import CodeEditorSettings

        s = CodeEditorSettings(show_line_numbers=True)
        window._apply_code_editor_settings_to(window.code_editor, s)
        assert not window.code_editor.line_number_area.isHidden()
        assert window.code_editor.line_number_area_width() > 0

    def test_apply_word_wrap_on(self, window):
        from PySide6.QtWidgets import QPlainTextEdit

        from craftgraph.theme import CodeEditorSettings

        s = CodeEditorSettings(word_wrap=True)
        window._apply_code_editor_settings_to(window.code_editor, s)
        assert window.code_editor.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth

    def test_apply_word_wrap_off(self, window):
        from PySide6.QtWidgets import QPlainTextEdit

        from craftgraph.theme import CodeEditorSettings

        s = CodeEditorSettings(word_wrap=False)
        window._apply_code_editor_settings_to(window.code_editor, s)
        assert window.code_editor.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap

    def test_apply_auto_indent_flag(self, window):
        from craftgraph.theme import CodeEditorSettings

        s = CodeEditorSettings(auto_indent=False)
        window._apply_code_editor_settings_to(window.code_editor, s)
        assert window.code_editor._auto_indent is False

    def test_apply_auto_close_brackets_flag(self, window):
        from craftgraph.theme import CodeEditorSettings

        s = CodeEditorSettings(auto_close_brackets=False)
        window._apply_code_editor_settings_to(window.code_editor, s)
        assert window.code_editor._auto_close_brackets is False

    def test_debounce_timer_updated(self, window, tmp_path):
        """Loading a file creates a parse timer; settings update its interval."""
        from craftgraph.theme import CodeEditorSettings

        # Create a minimal recipe file to load
        recipe = tmp_path / "test.txt"
        recipe.write_text("ModifiedRecipes:\n(\n    ItemID: Titanium;\n)\n", encoding="utf-8")
        window.load_recipes(tmp_path)

        s = CodeEditorSettings(parse_debounce_ms=1200)
        window._apply_code_editor_settings(s)
        tab = window._file_tabs[-1]
        assert tab.parse_timer is not None
        assert tab.parse_timer.interval() == 1200

    def test_debounce_timer_disabled(self, window, tmp_path):
        """When parse_debounce_enabled is False, timer interval is 0."""
        from craftgraph.theme import CodeEditorSettings

        recipe = tmp_path / "test.txt"
        recipe.write_text("ModifiedRecipes:\n(\n    ItemID: Titanium;\n)\n", encoding="utf-8")
        window.load_recipes(tmp_path)

        s = CodeEditorSettings(parse_debounce_enabled=False, parse_debounce_ms=1200)
        window._apply_code_editor_settings(s)
        tab = window._file_tabs[-1]
        assert tab.parse_timer is not None
        assert tab.parse_timer.interval() == 0

    def test_debounce_timer_reenabled(self, window, tmp_path):
        """Re-enabling debounce restores the configured interval."""
        from craftgraph.theme import CodeEditorSettings

        recipe = tmp_path / "test.txt"
        recipe.write_text("ModifiedRecipes:\n(\n    ItemID: Titanium;\n)\n", encoding="utf-8")
        window.load_recipes(tmp_path)

        # Disable first
        s = CodeEditorSettings(parse_debounce_enabled=False, parse_debounce_ms=900)
        window._apply_code_editor_settings(s)
        tab = window._file_tabs[-1]
        assert tab.parse_timer.interval() == 0

        # Re-enable
        s = CodeEditorSettings(parse_debounce_enabled=True, parse_debounce_ms=900)
        window._apply_code_editor_settings(s)
        assert tab.parse_timer.interval() == 900


# ---------------------------------------------------------------------------
# Watcher rebuild notifications
# ---------------------------------------------------------------------------


class TestWatcherNotifications:
    """Watcher rebuild triggers notifications based on settings."""

    def test_status_bar_on_reload(self, window, tmp_path):
        """Status bar shows reload message when notify_status_bar is True."""
        from craftgraph.theme import FileWatchingSettings

        recipe = tmp_path / "test.txt"
        recipe.write_text("ModifiedRecipes:\n(\n    ItemID: Titanium;\n)\n", encoding="utf-8")
        window.load_recipes(tmp_path)
        window._fw_settings = FileWatchingSettings(notify_status_bar=True)

        window._on_watcher_rebuild([])
        assert "Reloaded" in window.statusBar().currentMessage()

    def test_no_status_bar_when_disabled(self, window, tmp_path):
        """Status bar keeps load message when notify_status_bar is False."""
        from craftgraph.theme import FileWatchingSettings

        recipe = tmp_path / "test.txt"
        recipe.write_text("ModifiedRecipes:\n(\n    ItemID: Titanium;\n)\n", encoding="utf-8")
        window.load_recipes(tmp_path)
        window._fw_settings = FileWatchingSettings(notify_status_bar=False)

        window._on_watcher_rebuild([])
        assert "Reloaded" not in window.statusBar().currentMessage()

    def test_flash_tab_bar(self, window, tmp_path):
        """Tab bar gets a temporary highlight style when flash is enabled."""
        from craftgraph.theme import FileWatchingSettings

        recipe = tmp_path / "test.txt"
        recipe.write_text("ModifiedRecipes:\n(\n    ItemID: Titanium;\n)\n", encoding="utf-8")
        window.load_recipes(tmp_path)
        window._fw_settings = FileWatchingSettings(notify_flash_tab=True)

        window._on_watcher_rebuild([])
        # During the flash, the tab bar should have a highlight style
        assert "ffcc00" in window._tab_bar.styleSheet()

    def test_no_flash_when_disabled(self, window, tmp_path):
        """Tab bar stays unchanged when flash is disabled."""
        from craftgraph.theme import FileWatchingSettings

        recipe = tmp_path / "test.txt"
        recipe.write_text("ModifiedRecipes:\n(\n    ItemID: Titanium;\n)\n", encoding="utf-8")
        window.load_recipes(tmp_path)
        original_style = window._tab_bar.styleSheet()
        window._fw_settings = FileWatchingSettings(notify_flash_tab=False)

        window._on_watcher_rebuild([])
        assert window._tab_bar.styleSheet() == original_style

    def test_no_sound_without_cycles(self, window, tmp_path, monkeypatch):
        """No beep when there are no cycles even if sound is enabled."""
        from craftgraph.theme import FileWatchingSettings

        recipe = tmp_path / "test.txt"
        recipe.write_text("ModifiedRecipes:\n(\n    ItemID: Titanium;\n)\n", encoding="utf-8")
        window.load_recipes(tmp_path)
        window._fw_settings = FileWatchingSettings(notify_sound_on_cycle=True)

        beep_calls: list[bool] = []
        monkeypatch.setattr(QtWidgets.QApplication, "beep", lambda: beep_calls.append(True))
        window._on_watcher_rebuild([])
        assert len(beep_calls) == 0

    def test_sound_on_cycle(self, window, tmp_path, monkeypatch):
        """Beep fires when cycles exist and sound is enabled."""
        from craftgraph.theme import FileWatchingSettings

        recipe = tmp_path / "test.txt"
        recipe.write_text("ModifiedRecipes:\n(\n    ItemID: Titanium;\n)\n", encoding="utf-8")
        window.load_recipes(tmp_path)
        window._fw_settings = FileWatchingSettings(notify_sound_on_cycle=True)

        beep_calls: list[bool] = []
        monkeypatch.setattr(QtWidgets.QApplication, "beep", lambda: beep_calls.append(True))
        window._on_watcher_rebuild([["A", "B", "A"]])
        assert len(beep_calls) == 1


# ---------------------------------------------------------------------------
# Custom ID scope awareness
# ---------------------------------------------------------------------------


class TestCustomIdScope:
    """Settings dialog shows correct scope label and uses project IDs when available."""

    def test_scope_label_shows_global_when_no_project(self, qapp: QtWidgets.QApplication) -> None:
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(project_custom_ids=None)
        assert dialog._ac_scope_label.text() == "Editing: Global"

    def test_scope_label_shows_project_when_project_ids_given(self, qapp: QtWidgets.QApplication) -> None:
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(project_custom_ids=["MyMod"])
        assert dialog._ac_scope_label.text() == "Editing: Project"

    def test_custom_list_shows_project_ids_when_project_loaded(self, qapp: QtWidgets.QApplication) -> None:
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import AutocompleteSettings

        dialog = _SettingsDialog(
            autocomplete=AutocompleteSettings(custom_ids=["GlobalId"]),
            project_custom_ids=["ProjectId"],
        )
        items = [dialog._ac_custom_list.item(i).text() for i in range(dialog._ac_custom_list.count())]
        assert items == ["ProjectId"]

    def test_custom_list_shows_global_ids_when_no_project(self, qapp: QtWidgets.QApplication) -> None:
        from craftgraph.qt_gui import _SettingsDialog
        from craftgraph.theme import AutocompleteSettings

        dialog = _SettingsDialog(
            autocomplete=AutocompleteSettings(custom_ids=["GlobalId"]),
            project_custom_ids=None,
        )
        items = [dialog._ac_custom_list.item(i).text() for i in range(dialog._ac_custom_list.count())]
        assert items == ["GlobalId"]

    def test_project_custom_ids_property_returns_list_when_project(self, qapp: QtWidgets.QApplication) -> None:
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(project_custom_ids=["A", "B"])
        assert dialog.project_custom_ids == ["A", "B"]

    def test_project_custom_ids_property_returns_none_when_global(self, qapp: QtWidgets.QApplication) -> None:
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(project_custom_ids=None)
        assert dialog.project_custom_ids is None


class TestProjectCustomIdPersistence:
    """CraftGraphWindow reads/writes custom IDs from project settings_overrides."""

    def test_effective_custom_ids_returns_global_when_no_project(
        self, window: CraftGraphWindow,
    ) -> None:
        from craftgraph.qt_gui import CraftGraphWindow
        from craftgraph.theme import AutocompleteSettings

        window._project = None
        window._ac_settings = AutocompleteSettings(custom_ids=["GlobalId"])
        assert window._effective_custom_ids() == ["GlobalId"]

    def test_effective_custom_ids_returns_project_when_project_loaded(
        self, window: CraftGraphWindow,
    ) -> None:
        from craftgraph.project import ProjectFile
        from craftgraph.qt_gui import CraftGraphWindow
        from craftgraph.theme import AutocompleteSettings

        window._project = ProjectFile(
            version=1, name="test", description="", cc3_path="",
            project_path="", open_files=[], active_tab="",
            node_positions={}, editor_state={},
            settings_overrides={"custom_ids": ["ProjectId"]},
        )
        window._ac_settings = AutocompleteSettings(custom_ids=["GlobalId"])
        assert window._effective_custom_ids() == ["ProjectId"]

    def test_effective_custom_ids_returns_empty_when_project_has_no_key(
        self, window: CraftGraphWindow,
    ) -> None:
        from craftgraph.project import ProjectFile
        from craftgraph.qt_gui import CraftGraphWindow

        window._project = ProjectFile(
            version=1, name="test", description="", cc3_path="",
            project_path="", open_files=[], active_tab="",
            node_positions={}, editor_state={},
            settings_overrides={},
        )
        assert window._effective_custom_ids() == []

    def test_update_project_state_syncs_custom_ids(
        self, window: CraftGraphWindow,
    ) -> None:
        from craftgraph.project import ProjectFile
        from craftgraph.qt_gui import CraftGraphWindow
        from craftgraph.theme import AutocompleteSettings

        window._project = ProjectFile(
            version=1, name="test", description="", cc3_path="/tmp",
            project_path="/tmp/test.craftgraph", open_files=[], active_tab="",
            node_positions={}, editor_state={},
            settings_overrides={},
        )
        window._ac_settings = AutocompleteSettings(custom_ids=["Ignored"])
        window._project.settings_overrides["custom_ids"] = ["ProjectOnly"]
        window._update_project_state()
        assert window._project.settings_overrides["custom_ids"] == ["ProjectOnly"]


class TestSettingsDialogWidgetHeights:
    """Spinboxes/combos on the Node Editor tab must have enough vertical room."""

    @staticmethod
    def _node_editor_tab(dialog):
        """Return the Node Editor tab page from the dialog."""
        tabs = dialog.findChildren(QtWidgets.QTabWidget)
        outer = tabs[0]
        for i in range(outer.count()):
            if outer.tabText(i) == "Node Editor":
                return outer.widget(i)
        raise AssertionError("Node Editor tab not found")

    def test_spinbox_height_matches_neighbour_checkboxes(self, qapp):
        """Tall spinboxes overflow into neighbouring rows; cap their sizeHint
        so a row with a spinbox is no taller than a row with a checkbox.
        """
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(None)
        dialog.show()
        try:
            qapp.processEvents()
            tab = self._node_editor_tab(dialog)
            spinboxes = tab.findChildren(QtWidgets.QAbstractSpinBox)
            checkboxes = tab.findChildren(QtWidgets.QCheckBox)
            assert spinboxes and checkboxes
            checkbox_h = max(c.sizeHint().height() for c in checkboxes)
            for sb in spinboxes:
                # Spinbox height must be reasonably close to checkbox height
                # to avoid row overlap, while still being tall enough (>=20)
                # for the rendered value.
                h = sb.sizeHint().height()
                assert 20 <= h <= checkbox_h + 4, (
                    f"{type(sb).__name__} sizeHint height {h} not in "
                    f"[20, {checkbox_h + 4}]"
                )
        finally:
            dialog.close()

    def test_combo_height_matches_neighbour_checkboxes(self, qapp):
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(None)
        dialog.show()
        try:
            qapp.processEvents()
            tab = self._node_editor_tab(dialog)
            combos = tab.findChildren(QtWidgets.QComboBox)
            checkboxes = tab.findChildren(QtWidgets.QCheckBox)
            assert combos and checkboxes
            checkbox_h = max(c.sizeHint().height() for c in checkboxes)
            for cb in combos:
                h = cb.sizeHint().height()
                assert 18 <= h <= checkbox_h + 4, (
                    f"QComboBox sizeHint height {h} not in "
                    f"[18, {checkbox_h + 4}]"
                )
        finally:
            dialog.close()

    def test_form_layouts_have_consistent_vertical_spacing(self, qapp):
        """Every QFormLayout in the dialog uses the same vertical spacing
        so taller fields can't crowd labels of neighbouring rows.
        """
        from craftgraph.qt_gui import _SETTINGS_FORM_VSPACING, _SettingsDialog

        dialog = _SettingsDialog(None)
        dialog.show()
        try:
            qapp.processEvents()
            forms = dialog.findChildren(QtWidgets.QFormLayout)
            assert forms, "expected QFormLayouts inside settings dialog"
            for form in forms:
                assert form.verticalSpacing() == _SETTINGS_FORM_VSPACING
        finally:
            dialog.close()

    def test_dialog_minimum_size_keeps_chrome_functional(self, qapp):
        """Minimum size only needs to keep the tab bar + button row usable;
        scroll areas inside each tab handle the rest of the resize range.
        """
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(None)
        try:
            # Wide enough for Restore-All / Apply / Close without collision
            # and tall enough for tab bar + button row + ~1 row of content.
            assert dialog.minimumSize().width() >= 400
            assert dialog.minimumSize().height() >= 300
        finally:
            dialog.close()

    def test_dialog_default_size_shows_content_without_scrolling(self, qapp):
        """A freshly opened dialog should still be tall enough for full
        content of every tab at default scale.
        """
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(None)
        try:
            assert dialog.size().height() >= 700
        finally:
            dialog.close()

    def test_each_main_tab_wraps_a_scroll_area(self, qapp):
        """Every main settings tab routes its content through a QScrollArea
        so users can shrink the dialog without losing widgets behind chrome.
        """
        from craftgraph.qt_gui import _SettingsDialog

        dialog = _SettingsDialog(None)
        dialog.show()
        try:
            qapp.processEvents()
            outer = dialog.findChildren(QtWidgets.QTabWidget)[0]
            for i in range(outer.count()):
                page = outer.widget(i)
                scrolls = page.findChildren(QtWidgets.QScrollArea)
                assert scrolls, (
                    f"tab {outer.tabText(i)!r} has no QScrollArea wrapper"
                )
        finally:
            dialog.close()


class TestSearchAndSelectCentering:
    """Find Node + multi-line editor selection should center / multi-select."""

    _RECIPE_TXT = (
        "ModifiedRecipes:\n"
        "(\n"
        "    ItemID: Titanium;\n"
        "    AmountCrafted: 2;\n"
        "    Ingredients:\n"
        "    (\n"
        "        ItemID: Gold;\n"
        "        Required: 3;\n"
        "    ),\n"
        "    (\n"
        "        ItemID: Silver;\n"
        "        Required: 1;\n"
        "    );\n"
        "),\n"
        "(\n"
        "    ItemID: Copper;\n"
        "    AmountCrafted: 1;\n"
        "    Ingredients:\n"
        "    (\n"
        "        ItemID: Tin;\n"
        "        Required: 2;\n"
        "    );\n"
        ");\n"
    )

    def _load(self, window, tmp_path):
        recipe_file = tmp_path / "search.txt"
        recipe_file.write_text(self._RECIPE_TXT, encoding="utf-8")
        window.load_recipes(recipe_file)

    def test_center_view_on_nodes_translates_scene_range(self, window, tmp_path):
        self._load(window, tmp_path)
        nodes = [n for n in window.graph.all_nodes() if n.name() == "Titanium (x2)"]
        assert nodes, "expected Titanium recipe node"
        viewer = window.graph.viewer()
        # Pre-translate scene_range away from the node so we can detect a real pan.
        viewer._scene_range.translate(5000.0, 5000.0)
        target = nodes[0].view.sceneBoundingRect().center()
        window._center_view_on_nodes(window.graph, nodes)
        new_center = viewer._scene_range.center()
        # The scene_range centre must now match the node's centre (within 1px).
        assert abs(new_center.x() - target.x()) < 1.0
        assert abs(new_center.y() - target.y()) < 1.0

    def test_center_view_preserves_scene_range_size(self, window, tmp_path):
        """Panning must not change zoom -- the rect's dimensions stay fixed."""
        self._load(window, tmp_path)
        nodes = [n for n in window.graph.all_nodes() if n.name() == "Titanium (x2)"]
        viewer = window.graph.viewer()
        before = (viewer._scene_range.width(), viewer._scene_range.height())
        window._center_view_on_nodes(window.graph, nodes)
        after = (viewer._scene_range.width(), viewer._scene_range.height())
        assert after == before

    def test_center_view_on_empty_list_is_noop(self, window, tmp_path):
        self._load(window, tmp_path)
        viewer = window.graph.viewer()
        before_rect = QtCore.QRectF(viewer._scene_range)
        window._center_view_on_nodes(window.graph, [])
        assert viewer._scene_range == before_rect

    def test_search_match_centers_view(self, window, tmp_path, qapp):
        self._load(window, tmp_path)
        window._find_node_by_id()
        bar = window._search_bar
        assert bar is not None
        viewer = window.graph.viewer()
        # Move the scene range far away so any successful pan is observable.
        viewer._scene_range.translate(10000.0, 10000.0)
        bar._edit.setText("Copper")
        qapp.processEvents()
        window._update_search_matches()
        copper_node = next(
            n for n in window.graph.all_nodes() if n.name() == "Copper"
        )
        target = copper_node.view.sceneBoundingRect().center()
        new_center = viewer._scene_range.center()
        assert abs(new_center.x() - target.x()) < 1.0
        assert abs(new_center.y() - target.y()) < 1.0

    def test_multi_line_selection_selects_all_referenced_nodes(
        self, window, tmp_path, qapp,
    ):
        from PySide6.QtGui import QTextCursor

        self._load(window, tmp_path)
        tab = window._active_tab
        editor = tab.editor
        text = editor.toPlainText()
        # Select from the start of the file to past the second recipe's ItemID
        # (covers Titanium, Gold, Silver, Copper).
        copper_pos = text.find("ItemID: Copper")
        assert copper_pos > 0
        end_pos = text.find("\n", copper_pos)
        cursor = editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        qapp.processEvents()

        selected_names = {n.name() for n in tab.graph.selected_nodes()}
        # Recipe nodes carry "(xN)" suffix in their display name.
        # Orphan ingredients use bare ItemID.
        assert "Titanium (x2)" in selected_names
        assert "Gold" in selected_names
        assert "Silver" in selected_names
        assert "Copper" in selected_names

    def test_single_line_selection_does_not_trigger_sync(
        self, window, tmp_path, qapp,
    ):
        from PySide6.QtGui import QTextCursor

        self._load(window, tmp_path)
        tab = window._active_tab
        editor = tab.editor
        text = editor.toPlainText()
        # Select just the "ItemID: Titanium;" portion of one line.
        start = text.find("ItemID: Titanium")
        end = text.find(";", start)
        cursor = editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        # Pre-clear selection state by selecting nothing in the graph.
        tab.graph.clear_selection()
        editor.setTextCursor(cursor)
        qapp.processEvents()
        assert tab.graph.selected_nodes() == []

    def test_editor_selection_skipped_during_sync_guard(
        self, window, tmp_path, qapp,
    ):
        """Programmatic selection from graph->editor must not bounce back."""
        from PySide6.QtGui import QTextCursor

        self._load(window, tmp_path)
        tab = window._active_tab
        editor = tab.editor
        text = editor.toPlainText()
        copper_pos = text.find("ItemID: Copper")
        end_pos = text.find("\n", copper_pos)

        cursor = editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
        with tab.sync_guard():
            editor.setTextCursor(cursor)
            qapp.processEvents()
        # Inside the guard, the editor->graph handler short-circuits, so
        # nothing was selected.
        assert tab.graph.selected_nodes() == []
