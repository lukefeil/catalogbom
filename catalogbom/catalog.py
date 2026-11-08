"""Read evaluated spreadsheet catalog rows without modifying the catalog document."""

import re
from pathlib import Path

from catalogbom import model, preferences


COLUMNS = ("PartNumber", "Type", "Make", "Model", "Description", "NominalDimensions", "Unit")


def normalizedHeader(value):
    return "".join(character for character in value.casefold() if character.isalnum())


def readSheet(sheet):
    """Use row 1 as headers; inspect populated cells instead of guessing row limits."""
    populatedCells = set(sheet.getNonEmptyCells())

    def cellValue(cellAddress):
        if cellAddress not in populatedCells:
            return ""
        try:
            return str(sheet.get(cellAddress)).strip()
        except Exception as error:
            raise ValueError(f"Cannot read {sheet.Label}.{cellAddress}: {error}") from error

    headers = {}
    rowNumbers = set()
    for cellAddress in populatedCells:
        match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", cellAddress)
        if match is None:
            continue
        columnLetters, rowText = match.groups()
        rowNumber = int(rowText)
        if rowNumber == 1:
            header = normalizedHeader(cellValue(cellAddress))
            if header:
                if header in headers:
                    raise ValueError(f"Duplicate header in spreadsheet {sheet.Label}.")
                headers[header] = columnLetters
        else:
            rowNumbers.add(rowNumber)
    rows = []
    for rowNumber in sorted(rowNumbers):
        values = {header: cellValue(f"{columnLetters}{rowNumber}") for header, columnLetters in headers.items()}
        if any(values.values()):
            rows.append((rowNumber, values))
    return headers, rows


def readCatalog(spreadsheet):
    """Read a selected spreadsheet of any name; all fields are stored directly."""
    if spreadsheet is None or not spreadsheet.isDerivedFrom("Spreadsheet::Sheet"):
        raise ValueError("Select a spreadsheet object for the catalog.")
    headers, rows = readSheet(spreadsheet)
    requiredHeaders = {normalizedHeader(columnName) for columnName in COLUMNS}
    if not requiredHeaders.issubset(headers):
        raise ValueError("The selected spreadsheet needs row-1 headers: " + ", ".join(COLUMNS) + ".")
    entries = []
    partNumbers = set()
    for rowNumber, values in rows:
        entry = {columnName: values[normalizedHeader(columnName)] for columnName in COLUMNS}
        partNumber = entry["PartNumber"]
        if not partNumber or partNumber in partNumbers:
            raise ValueError(f"Missing or duplicate PartNumber in {spreadsheet.Label}, row {rowNumber}.")
        partNumbers.add(partNumber)
        entries.append(entry)
    if not entries:
        raise ValueError("The catalog contains no parts.")
    return entries


def findEntry(entries, partNumber):
    """Match an assigned identifier exactly, without changing model or catalog data."""
    if not isinstance(partNumber, str) or not partNumber.strip():
        raise ValueError("The selected object has no assigned PartNumber. Use Add PartNumber first.")
    for entry in entries:
        if entry["PartNumber"] == partNumber:
            return entry
    raise ValueError(f"PartNumber '{partNumber}' was not found in the catalog.")


def loadCatalog(application, modelDocument):
    """Resolve the global catalog and keep the consuming model's native dependency."""
    catalogFile, sheetName = preferences.getCatalogSelection(application)
    if not catalogFile and not sheetName:
        return readCatalog(model.getCatalogSpreadsheet(modelDocument))
    if not catalogFile or not sheetName:
        raise ValueError("Select a catalog spreadsheet in Settings; the global preference is incomplete.")
    filePath = Path(catalogFile).expanduser().resolve()
    if not filePath.is_file():
        raise ValueError("The global catalog file is missing. Reselect it in Settings.")
    existingDocuments = application.listDocuments()
    try:
        sourceDocument = next((document for document in existingDocuments.values()
                               if document.FileName and Path(document.FileName).resolve() == filePath), None)
        if sourceDocument is None:
            sourceDocument = application.openDocument(str(filePath))
        spreadsheet = sourceDocument.getObject(sheetName) if sourceDocument is not None else None
        entries = readCatalog(spreadsheet)
        model.saveCatalogSpreadsheet(modelDocument, spreadsheet)
        return entries
    finally:
        currentDocuments = application.listDocuments()
        existingRoots = [document for name, document in currentDocuments.items() if name in existingDocuments]
        for documentName in set(currentDocuments) - set(existingDocuments):
            sourceDocument = currentDocuments[documentName]
            if not any(model.documentDependsOn(document, sourceDocument) for document in existingRoots):
                application.closeDocument(documentName)
        application.setActiveDocument(modelDocument.Name)