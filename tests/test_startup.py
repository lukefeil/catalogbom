"""Check the startup contract without requiring an installed FreeCAD GUI."""

from pathlib import Path
import runpy
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ElementTree

import catalogbom


ROOT = Path(__file__).resolve().parent.parent


class StartupTests(unittest.TestCase):
    def test_headless_startup_does_not_import_gui(self):
        with patch.dict(sys.modules, {"FreeCADGui": None}):
            runpy.run_path(str(ROOT / "Init.py"))

    def test_package_import_does_not_require_freecad(self):
        with patch.dict(sys.modules, {"FreeCAD": None, "FreeCADGui": None}):
            namespace = runpy.run_path(str(ROOT / "catalogbom" / "__init__.py"))
        self.assertEqual(namespace["__version__"], catalogbom.__version__)

    def test_gui_registers_an_activatable_python_workbench(self):
        gui = ModuleType("FreeCADGui")
        registered = []
        gui.Workbench = type("Workbench", (), {"appendToolbar": Mock(), "appendMenu": Mock()})
        gui.addWorkbench = registered.append
        commands = ModuleType("catalogbom.commands")
        commandNames = ["CatalogBOM_Settings", "CatalogBOM_AddPartNumber", "CatalogBOM_LookupPartNumber", "CatalogBOM_LoadDimensions"]
        commands.registerCommands = Mock(return_value=commandNames)

        with patch.dict(sys.modules, {"FreeCADGui": gui, "catalogbom.commands": commands}):
            source_path = ROOT / "InitGui.py"
            for separate_namespaces in (False, True):
                with self.subTest(separate_namespaces=separate_namespaces):
                    registered.clear()
                    namespace = {}
                    global_namespace = {} if separate_namespaces else namespace
                    exec(
                        compile(source_path.read_text(), str(source_path), "exec"),
                        global_namespace,
                        namespace,
                    )
                    self.assertEqual(len(registered), 1)
                    workbench = registered[0]
                    self.assertIsInstance(workbench, gui.Workbench)
                    self.assertEqual(workbench.MenuText, "Catalog BOM")
                    self.assertEqual(workbench.GetClassName(), "Gui::PythonWorkbench")
                    self.assertTrue(Path(workbench.Icon).is_file())
                    self.assertIsNone(workbench.Initialize())
                    workbench.appendToolbar.assert_called_with("Catalog BOM", commandNames)
                    workbench.appendMenu.assert_called_with("Catalog BOM", commandNames)

    def test_icon_is_valid_svg(self):
        for iconName in ("catalogbom.svg", "settings.svg", "lookup.svg", "dimensions.svg"):
            with self.subTest(iconName=iconName):
                icon = ElementTree.parse(ROOT / "Resources" / "icons" / iconName)
                self.assertEqual(icon.getroot().tag, "{http://www.w3.org/2000/svg}svg")


if __name__ == "__main__":
    unittest.main()