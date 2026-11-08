"""FreeCAD toolbar commands and native Qt dialogs, loaded on workbench activation."""

from pathlib import Path
import traceback

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui, QtWidgets

from catalogbom import catalog, model, preferences


ICON_FOLDER = Path(__file__).resolve().parent.parent / "Resources" / "icons"
COMMAND_NAMES = ["CatalogBOM_Settings", "CatalogBOM_AddPartNumber", "CatalogBOM_LookupPartNumber"]


def showError(error):
    message = str(error)
    FreeCAD.Console.PrintError(f"Catalog BOM: {message}\n")
    if not isinstance(error, ValueError):
        FreeCAD.Console.PrintError(traceback.format_exc())
    QtWidgets.QMessageBox.warning(FreeCADGui.getMainWindow(), "Catalog BOM", message)


def selectedTarget():
    """Share whole-object selection rules between lookup and assignment commands."""
    document = FreeCAD.ActiveDocument
    if document is None:
        raise ValueError("Open a model document first.")
    selection = FreeCADGui.Selection.getSelectionEx()
    if len(selection) != 1 or selection[0].SubElementNames:
        raise ValueError("Select exactly one part or assembly object in the tree, not a face or edge.")
    target = selection[0].Object
    if target.Document is not document:
        raise ValueError("Select an object in the active model document.")
    model.classifyTarget(target)
    return target


class CatalogFilter(QtCore.QSortFilterProxyModel):
    """Combine a global search with AND-combined per-column substring filters."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.searchText = ""
        self.columnFilters = [""] * len(catalog.COLUMNS)

    def setSearch(self, searchText):
        self.searchText = searchText.casefold().strip()
        self.invalidate()

    def setColumnFilter(self, columnIndex, filterText):
        self.columnFilters[columnIndex] = filterText.casefold().strip()
        self.invalidate()

    def filterAcceptsRow(self, sourceRow, sourceParent):
        sourceModel = self.sourceModel()
        values = [str(sourceModel.data(sourceModel.index(sourceRow, columnIndex, sourceParent)) or "").casefold()
                  for columnIndex in range(len(catalog.COLUMNS))]
        return (not self.searchText or any(self.searchText in value for value in values)) and all(
            not filterText or filterText in values[columnIndex]
            for columnIndex, filterText in enumerate(self.columnFilters)
        )


class SettingsDialog(QtWidgets.QDialog):
    """Edit the global workbench preference and maintain internal model dependencies."""

    def __init__(self, document=None):
        super().__init__(FreeCADGui.getMainWindow())
        self.document = document
        self.setWindowTitle("Catalog BOM Settings")
        self.resize(620, 180)
        self.openedDocumentNames = set()
        self.savedSourceName = None
        layout = QtWidgets.QVBoxLayout(self)
        formLayout = QtWidgets.QFormLayout()
        documentLayout = QtWidgets.QHBoxLayout()
        self.documentCombo = QtWidgets.QComboBox()
        documentLayout.addWidget(self.documentCombo, 1)
        browseButton = QtWidgets.QToolButton()
        browseButton.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirOpenIcon))
        browseButton.setToolTip("Open a FreeCAD file to select a spreadsheet")
        browseButton.clicked.connect(self.browse)
        documentLayout.addWidget(browseButton)
        formLayout.addRow("Document", documentLayout)
        self.sheetCombo = QtWidgets.QComboBox()
        formLayout.addRow("Spreadsheet", self.sheetCombo)
        layout.addLayout(formLayout)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        self.saveButton = buttons.button(QtWidgets.QDialogButtonBox.Save)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.documentCombo.currentIndexChanged.connect(lambda index: self.refreshSheets())
        self.sheetCombo.currentIndexChanged.connect(self.updateSave)
        self.finished.connect(self.cleanupDocuments)
        currentSheet = None
        catalogFile, sheetName = preferences.getCatalogSelection(FreeCAD)
        configuredDocument = next((sourceDocument for sourceDocument in FreeCAD.listDocuments().values()
                                   if catalogFile and sourceDocument.FileName and Path(sourceDocument.FileName).resolve() == Path(catalogFile).resolve()), None)
        if configuredDocument is not None:
            currentSheet = configuredDocument.getObject(sheetName)
        elif document is not None:
            try:
                currentSheet = model.getCatalogSpreadsheet(document)
            except ValueError:
                pass
        self.refreshDocuments(
            currentSheet.Document.Name if currentSheet is not None else (document.Name if document is not None else None),
            currentSheet.Name if currentSheet is not None else None,
        )
        if configuredDocument is None and catalogFile and Path(catalogFile).is_file():
            self.openFile(catalogFile)
            self.refreshSheets(sheetName)

    def refreshDocuments(self, preferredDocumentName, preferredSheetName=None):
        self.documentCombo.blockSignals(True)
        self.documentCombo.clear()
        openDocuments = sorted(FreeCAD.listDocuments().values(), key=lambda sourceDocument: (sourceDocument is not self.document, sourceDocument.Label, sourceDocument.Name))
        for sourceDocument in openDocuments:
            suffix = " [current]" if sourceDocument is self.document else ""
            self.documentCombo.addItem(f"{sourceDocument.Label} ({sourceDocument.Name}){suffix}", sourceDocument.Name)
        self.documentCombo.setCurrentIndex(self.documentCombo.findData(preferredDocumentName))
        self.documentCombo.blockSignals(False)
        self.refreshSheets(preferredSheetName)

    def refreshSheets(self, preferredSheetName=None):
        self.sheetCombo.clear()
        sourceDocument = FreeCAD.listDocuments().get(self.documentCombo.currentData())
        if sourceDocument is not None:
            for spreadsheet in sourceDocument.Objects:
                if spreadsheet.isDerivedFrom("Spreadsheet::Sheet"):
                    self.sheetCombo.addItem(f"{spreadsheet.Label} ({spreadsheet.Name})", spreadsheet.Name)
        if preferredSheetName is not None:
            self.sheetCombo.setCurrentIndex(self.sheetCombo.findData(preferredSheetName))
        self.updateSave()

    def updateSave(self, index=0):
        self.saveButton.setEnabled(self.sheetCombo.currentIndex() >= 0)

    def browse(self):
        startingPath = (self.document.FileName if self.document is not None else "") or str(Path.home())
        selectedPath, selectedFilter = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose catalog file", startingPath, "FreeCAD documents (*.FCStd *.fcstd)"
        )
        if not selectedPath:
            return
        self.openFile(selectedPath)

    def openFile(self, selectedPath):
        """Open configured/browsed files while preserving the model command context."""
        existingDocuments = FreeCAD.listDocuments()
        try:
            filePath = Path(selectedPath).resolve()
            sourceDocument = next((sourceDocument for sourceDocument in existingDocuments.values()
                                   if sourceDocument.FileName and Path(sourceDocument.FileName).resolve() == filePath), None)
            if sourceDocument is None:
                sourceDocument = FreeCAD.openDocument(str(filePath))
            self.openedDocumentNames.update(set(FreeCAD.listDocuments()) - set(existingDocuments))
            if sourceDocument is None:
                raise ValueError("FreeCAD could not open the selected document.")
            self.refreshDocuments(sourceDocument.Name)
        except Exception as error:
            self.openedDocumentNames.update(set(FreeCAD.listDocuments()) - set(existingDocuments))
            self.cleanupDocuments()
            self.refreshDocuments(self.document.Name if self.document is not None else None)
            showError(error)
        finally:
            if self.document is not None:
                FreeCAD.setActiveDocument(self.document.Name)

    def cleanupDocuments(self, result=0):
        openDocuments = FreeCAD.listDocuments()
        existingRoots = [sourceDocument for sourceDocument in openDocuments.values()
                         if sourceDocument.Name not in self.openedDocumentNames]
        if self.savedSourceName in openDocuments:
            existingRoots.append(openDocuments[self.savedSourceName])
        for documentName in self.openedDocumentNames:
            sourceDocument = openDocuments.get(documentName)
            if sourceDocument is not None and documentName != self.savedSourceName and not any(model.documentDependsOn(rootDocument, sourceDocument) for rootDocument in existingRoots):
                FreeCAD.closeDocument(documentName)
        self.openedDocumentNames.clear()

    def save(self):
        try:
            sourceDocument = FreeCAD.listDocuments().get(self.documentCombo.currentData())
            spreadsheet = sourceDocument.getObject(self.sheetCombo.currentData()) if sourceDocument is not None else None
            catalog.readCatalog(spreadsheet)
            preferences.validateCatalogSelection(spreadsheet)
            if self.document is not None and (self.document.FileName or spreadsheet.Document is self.document):
                model.saveCatalogSpreadsheet(self.document, spreadsheet)
            preferences.saveCatalogSelection(FreeCAD, spreadsheet)
            self.savedSourceName = spreadsheet.Document.Name
        except Exception as error:
            showError(error)
            return
        self.accept()


class CatalogDialog(QtWidgets.QDialog):
    """Shared assignment picker; only Apply writes PartNumber and PartQuantity."""

    def __init__(self, target, entries):
        super().__init__(FreeCADGui.getMainWindow())
        self.target = target
        self.setWindowTitle(f"Add/Change Part Number: {target.Label}")
        self.resize(1000, 600)
        layout = QtWidgets.QVBoxLayout(self)
        searchEdit = QtWidgets.QLineEdit()
        searchEdit.setPlaceholderText("Search catalog")
        searchEdit.setClearButtonEnabled(True)
        layout.addWidget(searchEdit)
        self.sourceModel = QtGui.QStandardItemModel(self)
        self.sourceModel.setHorizontalHeaderLabels(catalog.COLUMNS)
        for entry in entries:
            items = [QtGui.QStandardItem(entry[columnName]) for columnName in catalog.COLUMNS]
            for item in items:
                item.setEditable(False)
            self.sourceModel.appendRow(items)
        self.proxyModel = CatalogFilter(self)
        self.proxyModel.setSourceModel(self.sourceModel)
        searchEdit.textChanged.connect(self.proxyModel.setSearch)
        filtersLayout = QtWidgets.QHBoxLayout()
        for columnIndex, columnName in enumerate(catalog.COLUMNS):
            filterEdit = QtWidgets.QLineEdit()
            filterEdit.setPlaceholderText(columnName)
            filterEdit.setToolTip(f"Filter {columnName}")
            filterEdit.setClearButtonEnabled(True)
            filterEdit.textChanged.connect(
                lambda filterText, columnIndex=columnIndex: self.proxyModel.setColumnFilter(columnIndex, filterText)
            )
            filtersLayout.addWidget(filterEdit)
        layout.addLayout(filtersLayout)
        self.table = QtWidgets.QTableView()
        self.table.setModel(self.proxyModel)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, QtCore.Qt.AscendingOrder)
        self.table.verticalHeader().hide()
        for columnIndex, columnWidth in enumerate((130, 110, 120, 120, 280, 150, 80)):
            self.table.setColumnWidth(columnIndex, columnWidth)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        controlsLayout = QtWidgets.QHBoxLayout()
        controlsLayout.addWidget(QtWidgets.QLabel("Quantity"))
        self.quantityEdit = QtWidgets.QSpinBox()
        self.quantityEdit.setRange(1, model.MAX_QUANTITY)
        existingQuantity = getattr(target, "PartQuantity", 1)
        isAssembly = model.classifyTarget(target) == "assembly"
        initialQuantity = existingQuantity if isinstance(existingQuantity, int) and 1 <= existingQuantity <= model.MAX_QUANTITY else 1
        self.quantityEdit.setValue(initialQuantity if isAssembly else 1)
        self.quantityEdit.setEnabled(isAssembly)
        controlsLayout.addWidget(self.quantityEdit)
        controlsLayout.addStretch(1)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Apply | QtWidgets.QDialogButtonBox.Cancel)
        self.applyButton = buttons.button(QtWidgets.QDialogButtonBox.Apply)
        self.applyButton.setEnabled(False)
        self.applyButton.clicked.connect(self.apply)
        buttons.rejected.connect(self.reject)
        controlsLayout.addWidget(buttons)
        layout.addLayout(controlsLayout)
        self.table.selectionModel().selectionChanged.connect(self.updateApply)
        currentPartNumber = getattr(target, "PartNumber", "")
        for rowIndex in range(self.proxyModel.rowCount()):
            if self.proxyModel.data(self.proxyModel.index(rowIndex, 0)) == currentPartNumber:
                self.table.selectRow(rowIndex)
                break

    def updateApply(self, selected, deselected):
        self.applyButton.setEnabled(bool(self.table.selectionModel().selectedRows()))

    def apply(self):
        selectedRows = self.table.selectionModel().selectedRows()
        if not selectedRows:
            return
        partNumber = self.proxyModel.data(self.proxyModel.index(selectedRows[0].row(), 0))
        try:
            model.assignPartNumber(self.target, partNumber, self.quantityEdit.value())
        except Exception as error:
            showError(error)
            return
        self.accept()


class LookupDialog(QtWidgets.QDialog):
    """Read-only catalog details for one assigned object, with an assignment editor."""

    def __init__(self, target, entries):
        super().__init__(FreeCADGui.getMainWindow())
        self.target = target
        self.entries = entries
        self.setWindowTitle(f"Lookup PartNumber: {target.Label}")
        self.resize(620, 380)
        layout = QtWidgets.QVBoxLayout(self)
        scrollArea = QtWidgets.QScrollArea()
        scrollArea.setWidgetResizable(True)
        detailsWidget = QtWidgets.QWidget()
        detailsLayout = QtWidgets.QFormLayout(detailsWidget)
        detailsLayout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.valueLabels = {}
        for columnName in catalog.COLUMNS:
            valueLabel = QtWidgets.QLabel()
            valueLabel.setTextFormat(QtCore.Qt.PlainText)
            valueLabel.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            valueLabel.setWordWrap(True)
            detailsLayout.addRow(columnName, valueLabel)
            self.valueLabels[columnName] = valueLabel
        scrollArea.setWidget(detailsWidget)
        layout.addWidget(scrollArea, 1)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        self.editButton = buttons.addButton("Edit", QtWidgets.QDialogButtonBox.ActionRole)
        self.editButton.clicked.connect(self.edit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def refresh(self):
        entry = catalog.findEntry(self.entries, getattr(self.target, "PartNumber", ""))
        for columnName, valueLabel in self.valueLabels.items():
            valueLabel.setText(entry[columnName])

    def edit(self):
        """Reuse the assignment picker and refresh details only after an accepted edit."""
        try:
            model.validateProperties(self.target)
            editorDialog = CatalogDialog(self.target, self.entries)
            if editorDialog.exec_() == QtWidgets.QDialog.Accepted:
                self.refresh()
        except Exception as error:
            showError(error)


class SettingsCommand:
    """Edit the user-wide catalog preference, even without an active model."""

    def GetResources(self):
        return {"MenuText": "Settings", "ToolTip": "Choose the global Catalog BOM spreadsheet",
                "Pixmap": str(ICON_FOLDER / "settings.svg")}

    def IsActive(self):
        return True

    def Activated(self):
        try:
            SettingsDialog(FreeCAD.ActiveDocument).exec_()
        except Exception as error:
            showError(error)


class AddPartNumberCommand:
    """Validate a model selection before opening the shared assignment picker."""

    def GetResources(self):
        return {"MenuText": "Add PartNumber", "ToolTip": "Assign a catalog part number to the selected part or assembly",
                "Pixmap": str(ICON_FOLDER / "catalogbom.svg")}

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        try:
            target = selectedTarget()
            model.validateProperties(target)
            entries = catalog.loadCatalog(FreeCAD, target.Document)
            CatalogDialog(target, entries).exec_()
        except Exception as error:
            showError(error)


class LookupPartNumberCommand:
    """Show catalog details without requiring editable assignment properties."""

    def GetResources(self):
        return {"MenuText": "Lookup PartNumber", "ToolTip": "Show catalog information for the selected object's part number",
                "Pixmap": str(ICON_FOLDER / "lookup.svg")}

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        try:
            target = selectedTarget()
            if "PartNumber" not in target.PropertiesList:
                raise ValueError("The selected object has no assigned PartNumber. Use Add PartNumber first.")
            if target.getTypeIdOfProperty("PartNumber") != "App::PropertyString":
                raise ValueError("PartNumber has an incompatible existing property type.")
            if not target.PartNumber.strip():
                raise ValueError("The selected object has no assigned PartNumber. Use Add PartNumber first.")
            entries = catalog.loadCatalog(FreeCAD, target.Document)
            catalog.findEntry(entries, target.PartNumber)
            LookupDialog(target, entries).exec_()
        except Exception as error:
            showError(error)


def registerCommands():
    """Register stable command identifiers when the workbench is initialized."""
    FreeCADGui.addCommand(COMMAND_NAMES[0], SettingsCommand())
    FreeCADGui.addCommand(COMMAND_NAMES[1], AddPartNumberCommand())
    FreeCADGui.addCommand(COMMAND_NAMES[2], LookupPartNumberCommand())
    return list(COMMAND_NAMES)