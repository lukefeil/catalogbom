"""Catalog selection stored in FreeCAD's standard, user-wide workbench preferences."""

from pathlib import Path


PREFERENCE_PATH = "User parameter:BaseApp/Preferences/Mod/CatalogBOM"


def getCatalogSelection(application):
    """Return the saved filename and internal sheet name without loading a document."""
    parameters = application.ParamGet(PREFERENCE_PATH)
    return parameters.GetString("CatalogFile", ""), parameters.GetString("CatalogSheet", "")


def validateCatalogSelection(spreadsheet):
    """Validate that the selected object can be restored from a saved file."""
    if spreadsheet is None or not spreadsheet.isDerivedFrom("Spreadsheet::Sheet"):
        raise ValueError("Select a spreadsheet object.")
    if not spreadsheet.Document.FileName:
        raise ValueError("Save the catalog document before storing it as a global preference.")
    catalogFile = Path(spreadsheet.Document.FileName).resolve()
    if not catalogFile.is_file():
        raise ValueError("The saved catalog file is missing. Save the catalog document again.")
    return str(catalogFile), spreadsheet.Name


def saveCatalogSelection(application, spreadsheet):
    """Save the global catalog choice; native dependencies are managed separately."""
    catalogFile, sheetName = validateCatalogSelection(spreadsheet)
    parameters = application.ParamGet(PREFERENCE_PATH)
    parameters.SetString("CatalogFile", catalogFile)
    parameters.SetString("CatalogSheet", sheetName)