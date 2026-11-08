"""Optional isolated smoke checks using FreeCAD's bundled Python and offscreen Qt."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

try:
    import FreeCAD
except ImportError:
    FreeCAD = None

from catalogbom import catalog, model, preferences, dimensions


@unittest.skipUnless(FreeCAD is not None, "Requires FreeCAD's bundled Python")
class NativeTests(unittest.TestCase):
    def setUp(self):
        self.document = FreeCAD.newDocument("CatalogBOMNativeSmoke")
        originalParamGet = FreeCAD.ParamGet
        testParameters = originalParamGet("User parameter:BaseApp/Preferences/Mod/CatalogBOMNativeTests")
        testParameters.RemString("CatalogFile")
        testParameters.RemString("CatalogSheet")
        parameterPatch = patch.object(FreeCAD, "ParamGet", side_effect=lambda parameterPath: testParameters if parameterPath == preferences.PREFERENCE_PATH else originalParamGet(parameterPath))
        parameterPatch.start()
        self.addCleanup(parameterPatch.stop)
        self.addCleanup(originalParamGet("User parameter:BaseApp/Preferences/Mod").RemGroup, "CatalogBOMNativeTests")

    def tearDown(self):
        FreeCAD.closeDocument(self.document.Name)

    def createCatalogSheet(self, document, name="Data"):
        import Spreadsheet

        sheet = document.addObject("Spreadsheet::Sheet", name)
        sheet.Label = "A freely named catalog"
        rows = [catalog.COLUMNS, ["PN-001", "Bolt", "Acme", "Model X", "A part", "M6", "ea"]]
        for rowIndex, row in enumerate(rows, 1):
            for columnIndex, value in enumerate(row):
                sheet.set(f"{chr(65 + columnIndex)}{rowIndex}", value)
        document.recompute()
        return sheet

    def test_settings_selects_current_spreadsheet_and_migrates_path(self):
        import FreeCADGui
        from PySide import QtWidgets
        from catalogbom.commands import SettingsDialog

        qtApplication = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        temporaryFolder = TemporaryDirectory()
        self.addCleanup(temporaryFolder.cleanup)
        self.document.saveAs(str(Path(temporaryFolder.name) / "model.FCStd"))
        sheet = self.createCatalogSheet(self.document, "LocalData")
        legacySettings = self.document.addObject("App::FeaturePython", model.SETTINGS_NAME)
        legacySettings.addProperty("App::PropertyString", "CatalogPath")
        legacySettings.CatalogPath = "old/catalog.FCStd"
        with patch.object(FreeCADGui, "getMainWindow", return_value=None, create=True):
            dialog = SettingsDialog(self.document)
            self.assertEqual(dialog.documentCombo.currentData(), self.document.Name)
            dialog.sheetCombo.setCurrentIndex(dialog.sheetCombo.findData(sheet.Name))
            dialog.save()
            self.assertEqual(dialog.result(), QtWidgets.QDialog.Accepted)
            self.assertIs(model.getCatalogSpreadsheet(self.document), sheet)
            self.assertEqual(preferences.getCatalogSelection(FreeCAD), (str(Path(self.document.FileName).resolve()), sheet.Name))
            self.assertNotIn("CatalogPath", legacySettings.PropertiesList)
            sheet.Label = "Changed label"
            secondDialog = SettingsDialog(self.document)
            self.assertEqual(secondDialog.sheetCombo.currentData(), sheet.Name)
            secondDialog.reject()

    def test_global_catalog_is_shared_while_models_keep_native_dependencies(self):
        import FreeCADGui
        from PySide import QtWidgets
        from catalogbom.commands import SettingsDialog

        qtApplication = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        sourceDocument = FreeCAD.newDocument("CatalogBOMGlobalSource")
        secondModel = None
        try:
            sheet = self.createCatalogSheet(sourceDocument)
            with TemporaryDirectory() as folderPath:
                sourceDocument.saveAs(str(Path(folderPath) / "catalog.FCStd"))
                preferences.saveCatalogSelection(FreeCAD, sheet)
                with patch.object(FreeCADGui, "getMainWindow", return_value=None, create=True):
                    dialog = SettingsDialog(None)
                    dialog.save()
                    self.assertEqual(dialog.result(), QtWidgets.QDialog.Accepted)
                self.assertIsNone(model.getSettings(sourceDocument))
                self.document.saveAs(str(Path(folderPath) / "model1.FCStd"))
                secondModel = FreeCAD.newDocument("CatalogBOMSecondModel")
                secondModel.saveAs(str(Path(folderPath) / "model2.FCStd"))
                for modelDocument in (self.document, secondModel):
                    entries = catalog.loadCatalog(FreeCAD, modelDocument)
                    self.assertEqual(entries[0]["PartNumber"], "PN-001")
                    self.assertIs(model.getCatalogSpreadsheet(modelDocument), sheet)
                    self.assertTrue(model.documentDependsOn(modelDocument, sourceDocument))
                self.assertEqual(preferences.getCatalogSelection(FreeCAD), (str(Path(sourceDocument.FileName).resolve()), sheet.Name))
        finally:
            if secondModel is not None:
                FreeCAD.closeDocument(secondModel.Name)
            FreeCAD.closeDocument(self.document.Name)
            self.document = FreeCAD.newDocument("CatalogBOMNativeSmoke")
            FreeCAD.closeDocument(sourceDocument.Name)

    def test_settings_browse_cancel_and_dependency_retention(self):
        import FreeCADGui
        from PySide import QtWidgets
        from catalogbom.commands import SettingsDialog

        qtApplication = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        sourceDocument = FreeCAD.newDocument("CatalogBOMBrowseSource")
        try:
            self.createCatalogSheet(sourceDocument)
            with TemporaryDirectory() as folderPath:
                catalogFile = Path(folderPath) / "source.FCStd"
                sourceDocument.saveAs(str(catalogFile))
                FreeCAD.closeDocument(sourceDocument.Name)
                sourceDocument = None
                self.document.saveAs(str(Path(folderPath) / "model.FCStd"))
                FreeCAD.setActiveDocument(self.document.Name)
                with patch.object(FreeCADGui, "getMainWindow", return_value=None, create=True), patch.object(
                    QtWidgets.QFileDialog, "getOpenFileName", return_value=(str(catalogFile), "")
                ):
                    cancelDialog = SettingsDialog(self.document)
                    cancelDialog.browse()
                    openedName = cancelDialog.documentCombo.currentData()
                    self.assertNotEqual(openedName, self.document.Name)
                    self.assertEqual(FreeCAD.ActiveDocument.Name, self.document.Name)
                    cancelDialog.reject()
                    self.assertNotIn(openedName, FreeCAD.listDocuments())
                    self.assertIsNone(model.getSettings(self.document))
                    saveDialog = SettingsDialog(self.document)
                    saveDialog.browse()
                    saveDialog.save()
                    self.assertEqual(saveDialog.result(), QtWidgets.QDialog.Accepted)
                    sheet = model.getCatalogSpreadsheet(self.document)
                    sourceDocument = sheet.Document
                    self.assertIn(sourceDocument.Name, FreeCAD.listDocuments())
                    self.assertTrue(model.documentDependsOn(self.document, sourceDocument))
                    self.assertEqual(catalog.loadCatalog(FreeCAD, self.document)[0]["PartNumber"], "PN-001")
                    existingDialog = SettingsDialog(self.document)
                    existingDialog.browse()
                    self.assertEqual(existingDialog.openedDocumentNames, set())
                    existingDialog.reject()
                    self.assertIn(sourceDocument.Name, FreeCAD.listDocuments())
        finally:
            if sourceDocument is not None:
                FreeCAD.closeDocument(self.document.Name)
                self.document = FreeCAD.newDocument("CatalogBOMNativeSmoke")
                FreeCAD.closeDocument(sourceDocument.Name)

    def test_native_circular_document_dependency_is_rejected(self):
        sourceDocument = FreeCAD.newDocument("CatalogBOMCycleSource")
        try:
            modelSheet = self.createCatalogSheet(self.document, "LocalData")
            catalogSheet = self.createCatalogSheet(sourceDocument)
            with TemporaryDirectory() as folderPath:
                self.document.saveAs(str(Path(folderPath) / "model.FCStd"))
                sourceDocument.saveAs(str(Path(folderPath) / "catalog.FCStd"))
                reverseLink = sourceDocument.addObject("App::FeaturePython", "ReverseLink")
                reverseLink.addProperty("App::PropertyXLink", "ModelSheet")
                reverseLink.ModelSheet = modelSheet
                with self.assertRaisesRegex(ValueError, "circular"):
                    model.saveCatalogSpreadsheet(self.document, catalogSheet)
                self.assertIsNone(model.getSettings(self.document))
        finally:
            FreeCAD.closeDocument(sourceDocument.Name)

    def test_spreadsheet_reference_persists_and_survives_rename(self):
        import Spreadsheet

        sourceDocument = FreeCAD.newDocument("CatalogBOMReferenceSource")
        try:
            sheet = sourceDocument.addObject("Spreadsheet::Sheet", "Data")
            sheet.Label = "Any sheet label"
            with TemporaryDirectory() as folderPath:
                sourceDocument.saveAs(str(Path(folderPath) / "catalog.FCStd"))
                modelFile = Path(folderPath) / "model.FCStd"
                self.document.saveAs(str(modelFile))
                model.saveCatalogSpreadsheet(self.document, sheet)
                self.assertIs(model.getCatalogSpreadsheet(self.document), sheet)
                settingsObject = model.getSettings(self.document)
                self.assertEqual(settingsObject.getTypeIdOfProperty("CatalogSpreadsheet"), "App::PropertyXLink")
                self.assertIn(sheet, settingsObject.OutList)
                sheet.Label = "Renamed sheet"
                sourceDocument.save()
                self.document.saveAs(str(modelFile))
                FreeCAD.closeDocument(self.document.Name)
                FreeCAD.closeDocument(sourceDocument.Name)
                sourceDocument = None
                self.document = FreeCAD.openDocument(str(modelFile))
                restoredSheet = model.getCatalogSpreadsheet(self.document)
                self.assertEqual(restoredSheet.Name, "Data")
                self.assertEqual(restoredSheet.Label, "Renamed sheet")
                sourceDocument = restoredSheet.Document
        finally:
            if sourceDocument is not None:
                FreeCAD.closeDocument(self.document.Name)
                self.document = FreeCAD.newDocument("CatalogBOMNativeSmoke")
                FreeCAD.closeDocument(sourceDocument.Name)

    def test_spreadsheet_reference_in_current_unsaved_document(self):
        import Spreadsheet

        sheet = self.document.addObject("Spreadsheet::Sheet", "LocalData")
        model.saveCatalogSpreadsheet(self.document, sheet)
        self.assertIs(model.getCatalogSpreadsheet(self.document), sheet)

    def test_live_dimensions_follow_body_not_outer_part_rotation(self):
        import PartDesign

        container = self.document.addObject("App::Part", "StockPart")
        innerContainer = self.document.addObject("App::Part", "InnerPart")
        container.addObject(innerContainer)
        body = self.document.addObject("PartDesign::Body", "StockBody")
        innerContainer.addObject(body)
        stockFeature = body.newObject("PartDesign::AdditiveBox", "Stock")
        stockFeature.Length = 100
        stockFeature.Width = 20
        stockFeature.Height = 3
        body.Tip = stockFeature
        self.document.recompute()
        self.assertIs(dimensions.loadDimensions(container), container)
        self.assertEqual(tuple(getattr(container, name).Value for name, axis in dimensions.DIMENSION_AXES), (100, 20, 3))
        self.assertEqual(dict(container.ExpressionEngine)["Length"], "StockBody.Tip.Shape.BoundBox.XLength")
        self.assertNotIn("Length", body.PropertiesList)
        container.Placement = FreeCAD.Placement(FreeCAD.Vector(30, 40, 50), FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 37))
        self.document.recompute()
        self.assertEqual(tuple(getattr(container, name).Value for name, axis in dimensions.DIMENSION_AXES), (100, 20, 3))
        stockFeature.Length = 125
        stockFeature.Width = 25
        self.document.recompute()
        self.assertEqual(tuple(getattr(container, name).Value for name, axis in dimensions.DIMENSION_AXES), (125, 25, 3))
        dimensions.loadDimensions(container)
        self.assertNotIn("Invalid", container.State)
        instance = self.document.addObject("App::Link", "StockInstance")
        instance.setLink(container)
        instance.Placement = FreeCAD.Placement(FreeCAD.Vector(80, 90, 100), FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 63))
        self.assertIs(dimensions.loadDimensions(instance), container)
        self.assertEqual(tuple(getattr(container, name).Value for name, axis in dimensions.DIMENSION_AXES), (125, 25, 3))
        import Assembly

        bomObject = self.document.addObject("Assembly::BomObject", "DimensionBOM")
        bomObject.columnsNames = ["Name", ".Length", ".Width", ".Height"]
        self.document.recompute()
        dataRows = sorted({int(cellAddress[1:]) for cellAddress in bomObject.getNonEmptyCells() if cellAddress.startswith("A") and cellAddress[1:].isdigit() and int(cellAddress[1:]) > 1})
        matchingRows = [rowNumber for rowNumber in dataRows if str(bomObject.get(f"A{rowNumber}")) == container.Label]
        self.assertTrue(matchingRows)
        rowNumber = matchingRows[0]
        for columnLetters, propertyName in zip(("B", "C", "D"), ("Length", "Width", "Height")):
            exportedValue = FreeCAD.Units.Quantity(str(bomObject.get(f"{columnLetters}{rowNumber}"))).Value
            formattedValue = FreeCAD.Units.Quantity(getattr(container, propertyName).UserString).Value
            self.assertAlmostEqual(exportedValue, formattedValue)

    def test_dimensions_ignore_body_placement_and_migrate_old_bindings(self):
        import PartDesign

        container = self.document.addObject("App::Part", "Shelf")
        body = self.document.addObject("PartDesign::Body", "ShelfBody")
        container.addObject(body)
        stockFeature = body.newObject("PartDesign::AdditiveBox", "ShelfStock")
        stockFeature.Length = 196.85
        stockFeature.Width = 285.75
        stockFeature.Height = 19.05
        body.Tip = stockFeature
        body.Placement = FreeCAD.Placement(FreeCAD.Vector(-84.3278, 337.95, 0), FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), -25))
        self.document.recompute()
        for propertyName, axisName in dimensions.DIMENSION_AXES:
            container.addProperty("App::PropertyLength", propertyName)
            container.setExpression(propertyName, f"{body.Name}.Shape.BoundBox.{axisName}")
        self.document.recompute()
        self.assertGreater(container.Length.Value, 290)
        dimensions.loadDimensions(container)
        for propertyName, expectedValue in zip(("Length", "Width", "Height"), (196.85, 285.75, 19.05)):
            self.assertAlmostEqual(getattr(container, propertyName).Value, expectedValue)
        body.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 41)
        container.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 67)
        stockFeature.Length = 210
        self.document.recompute()
        self.assertAlmostEqual(container.Length.Value, 210)
        self.assertAlmostEqual(container.Width.Value, 285.75)
        self.assertAlmostEqual(container.Height.Value, 19.05)
        extension = body.newObject("PartDesign::AdditiveBox", "ShelfExtension")
        extension.Length = 225
        extension.Width = 285.75
        extension.Height = 19.05
        extension.Placement = FreeCAD.Placement()
        body.Tip = extension
        self.document.recompute()
        self.assertAlmostEqual(container.Length.Value, 225)
        self.assertAlmostEqual(container.Width.Value, 285.75)
        self.assertAlmostEqual(container.Height.Value, 19.05)

    def test_catalog_entry_add_change_delete_and_undo(self):
        sheet = self.createCatalogSheet(self.document)
        self.document.UndoMode = 1
        newEntry = {columnName: "" for columnName in catalog.COLUMNS}
        newEntry.update(PartNumber="00123", Type="Panel", Description="=2+3", Unit="ea")
        catalog.writeEntry(sheet, newEntry)
        entries = catalog.readCatalog(sheet)
        self.assertEqual(entries[1]["PartNumber"], "00123")
        self.assertEqual(entries[1]["Description"], "=2+3")
        self.assertEqual(sheet.getContents("A3"), "'00123")
        with self.assertRaisesRegex(ValueError, "already exists"):
            catalog.writeEntry(sheet, newEntry)
        sheet.set("D2", "=2+3")
        self.document.recompute()
        originalFormula = sheet.getContents("D2")
        changedEntry = dict(catalog.findEntry(catalog.readCatalog(sheet), "PN-001"))
        changedEntry["Description"] = "Changed description"
        catalog.writeEntry(sheet, changedEntry, previousPartNumber="PN-001")
        self.assertEqual(sheet.getContents("D2"), originalFormula)
        self.assertEqual(catalog.readCatalog(sheet)[0]["Description"], "Changed description")
        catalog.deleteEntry(sheet, "00123")
        self.assertEqual(len(catalog.readCatalog(sheet)), 1)
        self.document.undo()
        self.document.recompute()
        self.assertEqual(len(catalog.readCatalog(sheet)), 2)
        catalog.deleteEntry(sheet, "00123")
        catalog.deleteEntry(sheet, "PN-001")
        self.assertEqual(catalog.readCatalog(sheet, allowEmpty=True), [])
        catalog.writeEntry(sheet, newEntry)
        self.assertEqual(catalog.readCatalog(sheet)[0]["PartNumber"], "00123")

    def test_catalog_browser_add_change_delete_confirmations(self):
        import FreeCADGui
        from PySide import QtWidgets
        from catalogbom import commands

        qtApplication = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        sheet = self.createCatalogSheet(self.document)
        target = self.document.addObject("App::Part", "Part")
        model.assignPartNumber(target, "PN-001", 1)

        def addEditor(editorDialog):
            self.assertEqual(tuple(editorDialog.fieldEditors), catalog.COLUMNS)
            editorDialog.fieldEditors["PartNumber"].setText("NEW-001")
            editorDialog.fieldEditors["Type"].setText("Panel")
            editorDialog.fieldEditors["Description"].setPlainText("New panel")
            editorDialog.fieldEditors["Unit"].setText("ea")
            editorDialog.save()
            return editorDialog.result()

        def changeEditor(editorDialog):
            self.assertEqual(editorDialog.fieldEditors["PartNumber"].text(), "NEW-001")
            editorDialog.fieldEditors["Description"].setPlainText("Updated panel")
            editorDialog.save()
            return editorDialog.result()

        with patch.object(FreeCADGui, "getMainWindow", return_value=None, create=True):
            browser = commands.CatalogDialog(target, catalog.readCatalog(sheet), spreadsheet=sheet)
            browser.show()
            qtApplication.processEvents()
            self.assertTrue(browser.addButton.isEnabled())
            with patch.object(commands.CatalogEntryDialog, "exec_", addEditor):
                browser.addButton.click()
            self.assertEqual(browser.selectedPartNumber(), "NEW-001")
            self.assertEqual(target.PartNumber, "PN-001")
            with patch.object(commands.CatalogEntryDialog, "exec_", changeEditor):
                browser.changeButton.click()
            self.assertEqual(catalog.findEntry(catalog.readCatalog(sheet), "NEW-001")["Description"], "Updated panel")
            with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.No) as question:
                browser.deleteButton.click()
                self.assertEqual(question.call_args.args[-1], QtWidgets.QMessageBox.No)
            self.assertEqual(len(catalog.readCatalog(sheet)), 2)
            with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Yes):
                browser.deleteButton.click()
            self.assertEqual(len(catalog.readCatalog(sheet)), 1)
            browser.table.selectRow(0)
            with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Yes):
                browser.deleteButton.click()
            self.assertEqual(browser.proxyModel.rowCount(), 0)
            self.assertFalse(browser.applyButton.isEnabled())
            self.assertTrue(browser.addButton.isEnabled())
            with patch.object(commands.CatalogEntryDialog, "exec_", return_value=QtWidgets.QDialog.Rejected):
                browser.addButton.click()
            self.assertEqual(catalog.readCatalog(sheet, allowEmpty=True), [])
            browser.reject()
            self.assertEqual(target.PartNumber, "PN-001")

    def test_catalog_editor_rejects_duplicates_and_confirms_renames(self):
        import FreeCADGui
        from PySide import QtWidgets
        from catalogbom import commands

        qtApplication = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        sheet = self.createCatalogSheet(self.document)
        target = self.document.addObject("App::Part", "Part")
        model.assignPartNumber(target, "PN-001", 1)
        with patch.object(FreeCADGui, "getMainWindow", return_value=None, create=True), patch.object(commands, "showError") as errorHandler:
            duplicateEditor = commands.CatalogEntryDialog(sheet)
            duplicateEditor.fieldEditors["PartNumber"].setText("PN-001")
            duplicateEditor.save()
            self.assertIn("already exists", str(errorHandler.call_args.args[0]))
            self.assertEqual(duplicateEditor.result(), QtWidgets.QDialog.Rejected)
            self.assertEqual(len(catalog.readCatalog(sheet)), 1)
            duplicateEditor.reject()
            editor = commands.CatalogEntryDialog(sheet, catalog.readCatalog(sheet)[0])
            editor.fieldEditors["PartNumber"].setText("RENAMED")
            with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.No):
                editor.save()
            self.assertEqual(catalog.readCatalog(sheet)[0]["PartNumber"], "PN-001")
            with patch.object(QtWidgets.QMessageBox, "question", return_value=QtWidgets.QMessageBox.Yes):
                editor.save()
            self.assertEqual(catalog.readCatalog(sheet)[0]["PartNumber"], "RENAMED")
            self.assertEqual(target.PartNumber, "PN-001")

    def test_lookup_refreshes_catalog_edits_even_when_assignment_is_canceled(self):
        import FreeCADGui
        from PySide import QtWidgets
        from catalogbom import commands

        qtApplication = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        sheet = self.createCatalogSheet(self.document)
        target = self.document.addObject("App::Part", "Part")
        model.assignPartNumber(target, "PN-001", 1)

        def changeAndCancel(browser):
            entry = dict(catalog.readCatalog(sheet)[0])
            entry["Description"] = "Catalog description updated"
            catalog.writeEntry(sheet, entry, "PN-001")
            browser.catalogChanged = True
            browser.reloadEntries()
            browser.reject()
            return browser.result()

        def deleteAndCancel(browser):
            catalog.deleteEntry(sheet, "PN-001")
            browser.catalogChanged = True
            browser.reloadEntries()
            browser.reject()
            return browser.result()

        with patch.object(FreeCADGui, "getMainWindow", return_value=None, create=True):
            lookup = commands.LookupDialog(target, catalog.readCatalog(sheet), spreadsheet=sheet)
            with patch.object(commands.CatalogDialog, "exec_", changeAndCancel):
                lookup.editButton.click()
            self.assertEqual(lookup.valueLabels["Description"].text(), "Catalog description updated")
            with patch.object(commands.CatalogDialog, "exec_", deleteAndCancel), patch.object(commands, "showError") as errorHandler:
                lookup.editButton.click()
                self.assertIn("not found", str(errorHandler.call_args.args[0]))
            self.assertEqual(lookup.valueLabels["Description"].text(), "")
            self.assertEqual(target.PartNumber, "PN-001")
            lookup.reject()

    def test_native_catalog_load_settings_and_assignment(self):
        import Spreadsheet

        catalogDocument = FreeCAD.newDocument("CatalogBOMNativeCatalog")
        try:
            rows = [catalog.COLUMNS, ["PN-001", "Bolt", "Acme", "Model X", "A part", "M6", "ea"]]
            sheet = catalogDocument.addObject("Spreadsheet::Sheet", "Data")
            sheet.Label = "catalog"
            for rowIndex, row in enumerate(rows, 1):
                for columnIndex, value in enumerate(row):
                    sheet.set(f"{chr(65 + columnIndex)}{rowIndex}", value)
            catalogDocument.recompute()
            with TemporaryDirectory() as folderPath:
                catalogFile = Path(folderPath) / "catalog.FCStd"
                catalogDocument.saveAs(str(catalogFile))
                self.document.saveAs(str(Path(folderPath) / "model.FCStd"))
                model.saveCatalogSpreadsheet(self.document, sheet)
                self.assertIs(model.getCatalogSpreadsheet(self.document), sheet)
                FreeCAD.setActiveDocument(self.document.Name)
                entries = catalog.loadCatalog(FreeCAD, self.document)
                self.assertEqual(entries[0]["Make"], "Acme")
                self.assertEqual(entries[0]["Unit"], "ea")
                self.assertEqual(FreeCAD.ActiveDocument.Name, self.document.Name)
                target = self.document.addObject("App::Part", "Part")
                model.assignPartNumber(target, entries[0]["PartNumber"], 9)
                model.assignPartNumber(target, "PN-002", 9)
                self.assertEqual(target.PartNumber, "PN-002")
                self.assertEqual(target.PartQuantity, 1)
                self.document.save()
        finally:
            if catalogDocument is not None:
                FreeCAD.closeDocument(self.document.Name)
                self.document = FreeCAD.newDocument("CatalogBOMNativeSmoke")
                FreeCAD.closeDocument(catalogDocument.Name)

    def test_offscreen_dialog_filters_and_apply(self):
        import FreeCADGui
        from PySide import QtWidgets
        from catalogbom.commands import CatalogDialog, SettingsDialog

        qtApplication = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        entries = [{"PartNumber": "PN-001", "Type": "Bolt", "Make": "Acme", "Model": "X", "Description": "A bolt", "NominalDimensions": "M6", "Unit": "ea"}]
        with patch.object(FreeCADGui, "getMainWindow", return_value=None, create=True):
            settingsDialog = SettingsDialog(self.document)
            settingsDialog.reject()
            self.assertIsNone(model.getSettings(self.document))
            for isAssembly in (False, True):
                with self.subTest(isAssembly=isAssembly):
                    target = self.document.addObject("App::Part", "Assembly" if isAssembly else "Part")
                    if isAssembly:
                        target.Type = "Assembly"
                    dialog = CatalogDialog(target, entries)
                    dialog.show()
                    qtApplication.processEvents()
                    self.assertEqual(dialog.quantityEdit.isEnabled(), isAssembly)
                    dialog.proxyModel.setSearch("not-present")
                    self.assertEqual(dialog.proxyModel.rowCount(), 0)
                    dialog.proxyModel.setSearch("m6")
                    self.assertEqual(dialog.proxyModel.rowCount(), 1)
                    dialog.proxyModel.setColumnFilter(2, "unknown")
                    self.assertEqual(dialog.proxyModel.rowCount(), 0)
                    dialog.proxyModel.setColumnFilter(2, "acme")
                    dialog.proxyModel.setColumnFilter(6, "kg")
                    self.assertEqual(dialog.proxyModel.rowCount(), 0)
                    dialog.proxyModel.setColumnFilter(6, "EA")
                    self.assertEqual(dialog.proxyModel.rowCount(), 1)
                    dialog.quantityEdit.setValue(5)
                    dialog.table.selectRow(0)
                    qtApplication.processEvents()
                    self.assertTrue(dialog.applyButton.isEnabled())
                    dialog.applyButton.click()
                    self.assertEqual(target.PartNumber, "PN-001")
                    self.assertEqual(target.PartQuantity, 5 if isAssembly else 1)
                    self.assertEqual(dialog.result(), QtWidgets.QDialog.Accepted)

    def test_lookup_details_edit_apply_and_cancel(self):
        import FreeCADGui
        from PySide import QtWidgets
        from catalogbom import commands

        qtApplication = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        entries = [
            {"PartNumber": "PN-001", "Type": "Bolt", "Make": "Acme", "Model": "X", "Description": "A bolt", "NominalDimensions": "M6", "Unit": "ea"},
            {"PartNumber": "PN-002", "Type": "Nut", "Make": "Acme", "Model": "Y", "Description": "<b>A nut</b>", "NominalDimensions": "M8", "Unit": "ea"},
        ]
        target = self.document.addObject("App::Part", "Part")
        model.assignPartNumber(target, "PN-001", 1)

        def applyEditor(editorDialog):
            self.assertTrue(editorDialog.windowTitle().startswith("Add/Change Part Number:"))
            self.assertEqual(editorDialog.table.selectionModel().selectedRows()[0].row(), 0)
            editorDialog.table.selectRow(1)
            editorDialog.applyButton.click()
            return editorDialog.result()

        with patch.object(FreeCADGui, "getMainWindow", return_value=None, create=True):
            lookupDialog = commands.LookupDialog(target, entries)
            lookupDialog.show()
            qtApplication.processEvents()
            self.assertEqual(tuple(lookupDialog.valueLabels), catalog.COLUMNS)
            self.assertEqual(lookupDialog.valueLabels["PartNumber"].text(), "PN-001")
            self.assertEqual(target.PartQuantity, 1)
            with patch.object(commands.CatalogDialog, "exec_", applyEditor):
                lookupDialog.editButton.click()
            self.assertEqual(target.PartNumber, "PN-002")
            self.assertEqual(lookupDialog.valueLabels["PartNumber"].text(), "PN-002")
            self.assertEqual(lookupDialog.valueLabels["Description"].text(), "<b>A nut</b>")
            self.assertEqual(lookupDialog.valueLabels["Description"].textFormat(), commands.QtCore.Qt.PlainText)
            with patch.object(commands.CatalogDialog, "exec_", return_value=QtWidgets.QDialog.Rejected):
                lookupDialog.editButton.click()
            self.assertEqual(target.PartNumber, "PN-002")
            self.assertEqual(lookupDialog.valueLabels["PartNumber"].text(), "PN-002")
            target.setEditorMode("PartNumber", 1)
            with patch.object(commands, "showError") as errorHandler, patch.object(commands, "CatalogDialog") as editorFactory:
                lookupDialog.editButton.click()
                editorFactory.assert_not_called()
                self.assertIn("not editable", str(errorHandler.call_args.args[0]))
            self.assertEqual(lookupDialog.valueLabels["PartNumber"].text(), "PN-002")
            lookupDialog.reject()

    def test_lookup_command_errors_and_registration(self):
        import FreeCADGui
        from catalogbom import commands

        target = self.document.addObject("App::Part", "Part")
        with patch.object(commands, "selectedTarget", return_value=target), patch.object(commands, "showError") as errorHandler:
            with patch.object(catalog, "loadCatalog") as loader:
                commands.LookupPartNumberCommand().Activated()
                self.assertIn("no assigned PartNumber", str(errorHandler.call_args.args[0]))
                loader.assert_not_called()
            model.assignPartNumber(target, "MISSING", 1)
            with patch.object(catalog, "loadCatalog", return_value=[]):
                commands.LookupPartNumberCommand().Activated()
                self.assertIn("not found", str(errorHandler.call_args.args[0]))
        with patch.object(FreeCADGui, "addCommand", create=True) as commandRegistrar:
            self.assertEqual(commands.registerCommands(), commands.COMMAND_NAMES)
            self.assertEqual([call.args[0] for call in commandRegistrar.call_args_list], commands.COMMAND_NAMES)
            self.assertEqual(commandRegistrar.call_args_list[2].args[1].GetResources()["MenuText"], "Lookup PartNumber")
            self.assertEqual(commandRegistrar.call_args_list[3].args[1].GetResources()["MenuText"], "Load Dimensions")

    def test_native_link_assignment_is_instance_local(self):
        sourceObject = self.document.addObject("App::Part", "Source")
        model.assignPartNumber(sourceObject, "SOURCE", 1)
        linkObject = self.document.addObject("App::Link", "Instance")
        linkObject.setLink(sourceObject)
        model.assignPartNumber(linkObject, "INSTANCE", 1)
        self.assertEqual(sourceObject.PartNumber, "SOURCE")
        self.assertEqual(linkObject.PartNumber, "INSTANCE")

    def test_native_assembly_classification_and_quantity(self):
        import Assembly

        assemblyObject = self.document.addObject("Assembly::AssemblyObject", "NativeAssembly")
        model.assignPartNumber(assemblyObject, "ASM-001", 7)
        self.assertEqual(assemblyObject.PartQuantity, 7)


if __name__ == "__main__":
    unittest.main()