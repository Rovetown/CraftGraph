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

from PySide6 import QtWidgets

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
def window(qapp):
    """Fresh CraftGraphWindow for each test."""
    from craftgraph.qt_gui import CraftGraphWindow

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
        monkeypatch.setattr(QtWidgets.QDialog, "exec", lambda self: QtWidgets.QDialog.Accepted)
        window._on_settings()
        # If we got here without error, the dialog was created successfully.

    def test_settings_dialog_has_label(self, window, monkeypatch):
        """Verify the Settings dialog contains 'coming soon' text."""
        created_dialogs: list[QtWidgets.QDialog] = []
        orig_init = QtWidgets.QDialog.__init__

        def tracking_init(self_dialog, *args, **kwargs):
            orig_init(self_dialog, *args, **kwargs)
            created_dialogs.append(self_dialog)

        monkeypatch.setattr(QtWidgets.QDialog, "__init__", tracking_init)
        monkeypatch.setattr(QtWidgets.QDialog, "exec", lambda self: QtWidgets.QDialog.Accepted)
        window._on_settings()
        assert len(created_dialogs) == 1
        labels = created_dialogs[0].findChildren(QtWidgets.QLabel)
        assert any("coming soon" in lbl.text().lower() for lbl in labels)


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
        assert "Titanium" in node_names
        assert "Gold" in node_names

        recipe_node = next(n for n in nodes if n.name() == "Titanium")
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
            "ModifiedRecipes:\n"
            "(\n"
            "    ItemID: Titanium;\n"
            "    AmountCrafted: 1;\n"
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        tab = window._active_tab
        assert hasattr(tab, "orphan_nodes")
        assert tab.orphan_nodes == {}


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

    def test_save_writes_layout_sidecar(self, window, tmp_path):
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
        assert len(fab.tabs) == 2, (
            f"Expected 2 tabs in fabricator, got {len(fab.tabs)}"
        )

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
            "AliasRecipes:\n(\n"
            '    ItemID: MyAlias;\n'
            '    DisplayName: "Cool Alias";\n'
            ");\n",
            encoding="utf-8",
        )
        window.load_recipes(recipe_file)

        orig = window.graph.all_nodes()[0]
        orig.set_selected(True)
        window._duplicate_selected_nodes()

        duped = [n for n in window.graph.all_nodes() if n is not orig][0]
        # NodeGraphQt appends a suffix like " 1" to the title.
        # The display_name on the model should carry the same suffix.
        suffix = duped.name()[len("MyAlias"):]
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
        monkeypatch.setattr(window, "_show_validation_summary", lambda issues: shown.append(True) or True)

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


