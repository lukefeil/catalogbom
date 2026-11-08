"""GUI workbench implementation, imported only by FreeCAD's GUI startup hook."""

from pathlib import Path

import FreeCADGui


class CatalogBOMWorkbench(FreeCADGui.Workbench):
    MenuText = "Catalog BOM"
    ToolTip = "Catalog and bill of materials workbench"
    Icon = str(
        Path(__file__).resolve().parent.parent
        / "Resources"
        / "icons"
        / "catalogbom.svg"
    )

    def Initialize(self):
        """Register GUI commands only when the workbench is first activated."""
        from catalogbom.commands import registerCommands

        commandNames = registerCommands()
        self.appendToolbar("Catalog BOM", commandNames)
        self.appendMenu("Catalog BOM", commandNames)

    def GetClassName(self):
        return "Gui::PythonWorkbench"