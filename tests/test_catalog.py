"""Catalog and model regressions independent of FreeCAD and Qt installations."""

import unittest
from unittest.mock import Mock

from catalogbom import model
from catalogbom import catalog
from catalogbom import preferences


def makeTarget(typeId):
    target = Mock()
    target.isDerivedFrom.side_effect = lambda candidateType: candidateType == typeId
    target.PropertiesList = []
    target.ExpressionEngine = []
    target.getEditorMode.return_value = []
    target.Document = Mock()
    target.Shape.Solids = [object()]
    return target


class ModelTests(unittest.TestCase):
    def test_current_unsaved_document_accepts_spreadsheet_reference(self):
        document = Mock(FileName="", Name="Model")
        document.getObject.return_value = None
        settingsObject = Mock(PropertiesList=[])
        document.addObject.return_value = settingsObject
        spreadsheet = makeSheet("Any label", [])
        spreadsheet.Document = document
        model.saveCatalogSpreadsheet(document, spreadsheet)
        self.assertIs(settingsObject.CatalogSpreadsheet, spreadsheet)
        self.assertFalse(settingsObject.ViewObject.ShowInTree)
        settingsObject.addProperty.assert_called_once_with("App::PropertyXLink", "CatalogSpreadsheet", "Catalog BOM")
        document.commitTransaction.assert_called_once()

    def test_external_reference_requires_both_documents_saved(self):
        document = Mock(FileName="", Name="Model")
        spreadsheet = makeSheet("Any label", [])
        spreadsheet.Document = Mock(FileName="/catalog.FCStd", Name="Catalog", Objects=[])
        with self.assertRaisesRegex(ValueError, "Save the model"):
            model.saveCatalogSpreadsheet(document, spreadsheet)
        document.FileName = "/model.FCStd"
        spreadsheet.Document.FileName = ""
        with self.assertRaisesRegex(ValueError, "Save the external"):
            model.saveCatalogSpreadsheet(document, spreadsheet)
        document.openTransaction.assert_not_called()

    def test_circular_document_dependency_is_rejected(self):
        document = Mock(FileName="/model.FCStd", Name="Model")
        linkedObject = Mock(Document=document)
        sourceObject = Mock(OutList=[linkedObject])
        spreadsheet = makeSheet("Data", [])
        spreadsheet.Document = Mock(FileName="/catalog.FCStd", Name="Catalog", Objects=[sourceObject])
        with self.assertRaisesRegex(ValueError, "circular"):
            model.saveCatalogSpreadsheet(document, spreadsheet)
        document.openTransaction.assert_not_called()

    def test_legacy_path_is_replaced_on_explicit_selection(self):
        settingsObject = Mock(PropertiesList=["CatalogPath"])
        settingsObject.getTypeIdOfProperty.return_value = "App::PropertyString"
        document = Mock(Name="Model")
        document.getObject.return_value = settingsObject
        spreadsheet = makeSheet("Data", [])
        spreadsheet.Document = document
        model.saveCatalogSpreadsheet(document, spreadsheet)
        self.assertIs(settingsObject.CatalogSpreadsheet, spreadsheet)
        settingsObject.removeProperty.assert_called_once_with("CatalogPath")

    def test_part_quantity_is_always_one(self):
        target = makeTarget("PartDesign::Body")
        model.assignPartNumber(target, "PN-001", 20)
        self.assertEqual(target.PartNumber, "PN-001")
        self.assertEqual(target.PartQuantity, 1)
        target.Document.commitTransaction.assert_called_once()

    def test_native_assembly_quantity(self):
        target = makeTarget("Assembly::AssemblyObject")
        model.assignPartNumber(target, "ASSEMBLY-01", 12)
        self.assertEqual(target.PartQuantity, 12)
        for quantity in (0, -1, 1.5, True):
            with self.subTest(quantity=quantity), self.assertRaises(ValueError):
                model.assignPartNumber(target, "ASSEMBLY-01", quantity)

    def test_plain_part_container_is_not_an_assembly(self):
        target = makeTarget("App::Part")
        target.Type = "Part"
        self.assertEqual(model.classifyTarget(target), "part")

    def test_link_assignment_does_not_write_source(self):
        sourceObject = makeTarget("Assembly::AssemblyObject")
        target = makeTarget("App::Link")
        target.ElementCount = 0
        target.getLinkedObject.return_value = sourceObject
        model.assignPartNumber(target, "LINK-01", 4)
        self.assertEqual(target.PartQuantity, 4)
        sourceObject.addProperty.assert_not_called()

    def test_incompatible_property_is_not_overwritten(self):
        target = makeTarget("PartDesign::Body")
        target.PropertiesList = ["PartNumber"]
        target.getTypeIdOfProperty.return_value = "App::PropertyInteger"
        with self.assertRaisesRegex(ValueError, "incompatible"):
            model.assignPartNumber(target, "PN-001", 1)
        target.Document.openTransaction.assert_not_called()

    def test_assignment_failure_aborts_transaction(self):
        target = makeTarget("PartDesign::Body")
        target.Document.recompute.side_effect = RuntimeError("Recompute failed")
        with self.assertRaises(RuntimeError):
            model.assignPartNumber(target, "PN-001", 1)
        target.Document.abortTransaction.assert_called_once()
        target.Document.commitTransaction.assert_not_called()

    def test_existing_editable_properties_can_be_updated(self):
        target = makeTarget("PartDesign::Body")
        target.PropertiesList = ["PartNumber", "PartQuantity"]
        target.getTypeIdOfProperty.side_effect = {"PartNumber": "App::PropertyString", "PartQuantity": "App::PropertyInteger"}.__getitem__
        model.assignPartNumber(target, "UPDATED", 1)
        self.assertEqual(target.PartNumber, "UPDATED")
        target.addProperty.assert_not_called()

    def test_readonly_and_expression_properties_are_rejected(self):
        target = makeTarget("PartDesign::Body")
        target.PropertiesList = ["PartNumber"]
        target.getTypeIdOfProperty.return_value = "App::PropertyString"
        target.getEditorMode.return_value = ["ReadOnly"]
        with self.assertRaisesRegex(ValueError, "not editable"):
            model.assignPartNumber(target, "PN-001", 1)
        target.getEditorMode.return_value = []
        target.ExpressionEngine = [("PartNumber", "Other.PartNumber")]
        with self.assertRaisesRegex(ValueError, "expression"):
            model.assignPartNumber(target, "PN-001", 1)


def makeSheet(label, rows):
    sheet = Mock()
    sheet.Label = label
    sheet.isDerivedFrom.side_effect = lambda typeId: typeId == "Spreadsheet::Sheet"
    cells = {f"{chr(65 + columnIndex)}{rowIndex}": value
             for rowIndex, row in enumerate(rows, 1)
             for columnIndex, value in enumerate(row) if value != ""}
    sheet.getNonEmptyCells.return_value = list(cells)
    sheet.get.side_effect = cells.__getitem__
    return sheet


def makeCatalog():
    return makeSheet("Any catalog label", [catalog.COLUMNS, ["PN-001", "Bolt", "Acme", "Model X", "A part", "M6", "ea"]])


class CatalogTests(unittest.TestCase):
    def test_single_catalog_sheet_reads_direct_values(self):
        entries = catalog.readCatalog(makeCatalog())
        self.assertEqual(entries[0]["Make"], "Acme")
        self.assertEqual(entries[0]["Type"], "Bolt")
        self.assertEqual(entries[0]["NominalDimensions"], "M6")
        self.assertEqual(entries[0]["Unit"], "ea")
        self.assertEqual(tuple(entries[0]), catalog.COLUMNS)

    def test_sheet_label_is_not_part_of_the_catalog_contract(self):
        spreadsheet = makeCatalog()
        spreadsheet.Label = "Parts"
        self.assertEqual(catalog.readCatalog(spreadsheet)[0]["PartNumber"], "PN-001")

    def test_lookup_matches_exact_part_number(self):
        entries = catalog.readCatalog(makeCatalog())
        self.assertIs(catalog.findEntry(entries, "PN-001"), entries[0])
        with self.assertRaisesRegex(ValueError, "not found"):
            catalog.findEntry(entries, "pn-001")

    def test_lookup_missing_and_unassigned_part_numbers(self):
        entries = catalog.readCatalog(makeCatalog())
        with self.assertRaisesRegex(ValueError, "not found"):
            catalog.findEntry(entries, "UNKNOWN")
        for partNumber in ("", " ", None):
            with self.subTest(partNumber=partNumber), self.assertRaisesRegex(ValueError, "no assigned PartNumber"):
                catalog.findEntry(entries, partNumber)

    def test_duplicate_part_number_is_rejected(self):
        entry = ["PN-001", "Bolt", "Acme", "", "", "M6", "ea"]
        spreadsheet = makeSheet("catalog", [catalog.COLUMNS, entry, entry])
        with self.assertRaisesRegex(ValueError, "duplicate PartNumber"):
            catalog.readCatalog(spreadsheet)

    def test_missing_header_is_rejected(self):
        headers = catalog.COLUMNS[:5] + catalog.COLUMNS[6:]
        spreadsheet = makeSheet("catalog", [headers, ["PN-001", "Bolt", "Acme", "", "", "ea"]])
        with self.assertRaisesRegex(ValueError, "NominalDimensions"):
            catalog.readCatalog(spreadsheet)

    def test_optional_values_can_be_blank_without_lookups(self):
        spreadsheet = makeSheet("catalog", [catalog.COLUMNS, ["PN-001", "", "", "", "", "", ""]])
        entry = catalog.readCatalog(spreadsheet)[0]
        self.assertEqual(entry["Make"], "")
        self.assertEqual(entry["Unit"], "")

    def test_unit_header_is_required(self):
        spreadsheet = makeSheet("catalog", [catalog.COLUMNS[:-1], ["PN-001", "Bolt", "Acme", "", "", "M6"]])
        with self.assertRaisesRegex(ValueError, "Unit"):
            catalog.readCatalog(spreadsheet)

    def test_selected_sheet_is_used_even_with_duplicate_labels(self):
        firstSheet = makeCatalog()
        secondSheet = makeSheet(firstSheet.Label, [catalog.COLUMNS, ["OTHER", "", "", "", "", "", ""]])
        self.assertEqual(catalog.readCatalog(firstSheet)[0]["PartNumber"], "PN-001")
        self.assertEqual(catalog.readCatalog(secondSheet)[0]["PartNumber"], "OTHER")

    def test_loading_reference_does_not_open_close_or_switch_documents(self):
        spreadsheet = makeCatalog()
        settingsObject = Mock(PropertiesList=["CatalogSpreadsheet"], CatalogSpreadsheet=spreadsheet)
        settingsObject.getTypeIdOfProperty.return_value = "App::PropertyXLink"
        modelDocument = Mock()
        modelDocument.getObject.return_value = settingsObject
        application = Mock()
        application.ParamGet.return_value.GetString.return_value = ""
        self.assertEqual(len(catalog.loadCatalog(application, modelDocument)), 1)
        application.openDocument.assert_not_called()
        application.closeDocument.assert_not_called()
        application.setActiveDocument.assert_not_called()

    def test_unresolved_reference_reports_error(self):
        settingsObject = Mock(PropertiesList=["CatalogSpreadsheet"], CatalogSpreadsheet=None)
        settingsObject.getTypeIdOfProperty.return_value = "App::PropertyXLink"
        document = Mock()
        document.getObject.return_value = settingsObject
        with self.assertRaisesRegex(ValueError, "unresolved"):
            model.getCatalogSpreadsheet(document)


class PreferenceTests(unittest.TestCase):
    def test_reads_freecad_workbench_parameter_group(self):
        application = Mock()
        parameters = application.ParamGet.return_value
        parameters.GetString.side_effect = ["/catalog.FCStd", "SheetData"]
        self.assertEqual(preferences.getCatalogSelection(application), ("/catalog.FCStd", "SheetData"))
        application.ParamGet.assert_called_once_with(preferences.PREFERENCE_PATH)

    def test_unsaved_catalog_is_rejected_without_preference_writes(self):
        application = Mock()
        spreadsheet = makeSheet("Any label", [])
        spreadsheet.Document.FileName = ""
        with self.assertRaisesRegex(ValueError, "Save the catalog document"):
            preferences.saveCatalogSelection(application, spreadsheet)
        application.ParamGet.assert_not_called()


if __name__ == "__main__":
    unittest.main()