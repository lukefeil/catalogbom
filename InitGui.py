"""Register the Catalog BOM workbench with FreeCAD's GUI."""

import FreeCADGui

from catalogbom.workbench import CatalogBOMWorkbench


FreeCADGui.addWorkbench(CatalogBOMWorkbench())