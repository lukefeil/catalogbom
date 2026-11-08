"""Internal catalog dependencies and undoable assignments without GUI imports."""

SETTINGS_NAME = "CatalogBOMSettings"
MAX_QUANTITY = 2147483647


def getSettings(document):
    settingsObject = document.getObject(SETTINGS_NAME)
    if settingsObject is not None:
        if not {"CatalogPath", "CatalogSpreadsheet"}.intersection(settingsObject.PropertiesList):
            raise ValueError("An unrelated object already uses the name CatalogBOMSettings.")
        if "CatalogSpreadsheet" in settingsObject.PropertiesList:
            if settingsObject.getTypeIdOfProperty("CatalogSpreadsheet") != "App::PropertyXLink":
                raise ValueError("CatalogBOMSettings.CatalogSpreadsheet must be a native object link.")
        elif settingsObject.getTypeIdOfProperty("CatalogPath") != "App::PropertyString":
            raise ValueError("The legacy CatalogPath setting has an incompatible type.")
    return settingsObject


def getCatalogSpreadsheet(document):
    """Return the actual linked object, not a name or path-based substitute."""
    settingsObject = getSettings(document)
    if settingsObject is None:
        raise ValueError("Select a catalog spreadsheet in Catalog BOM Settings first.")
    if "CatalogSpreadsheet" not in settingsObject.PropertiesList:
        raise ValueError("Reselect the spreadsheet in Settings to replace the legacy catalog path.")
    spreadsheet = settingsObject.CatalogSpreadsheet
    if spreadsheet is None:
        raise ValueError("The catalog spreadsheet link is missing or unresolved. Check its source file and reselect it in Settings.")
    if not spreadsheet.isDerivedFrom("Spreadsheet::Sheet"):
        raise ValueError("The linked catalog object is not a spreadsheet.")
    hideCatalogDependency(settingsObject)
    return spreadsheet


def documentDependsOn(document, dependencyDocument):
    """Follow native object links across document boundaries to detect dependencies."""
    pendingDocuments = [document]
    visitedNames = set()
    while pendingDocuments:
        currentDocument = pendingDocuments.pop()
        if currentDocument.Name in visitedNames:
            continue
        visitedNames.add(currentDocument.Name)
        for documentObject in currentDocument.Objects:
            for linkedObject in documentObject.OutList:
                linkedDocument = linkedObject.Document
                if linkedDocument is currentDocument:
                    continue
                if linkedDocument is dependencyDocument:
                    return True
                pendingDocuments.append(linkedDocument)
    return False


def saveCatalogSpreadsheet(document, spreadsheet):
    """Persist an internal spreadsheet dependency; catalog choice is a global preference."""
    if spreadsheet is None or not spreadsheet.isDerivedFrom("Spreadsheet::Sheet"):
        raise ValueError("Select a spreadsheet object.")
    if spreadsheet.Document is not document and not spreadsheet.Document.FileName:
        raise ValueError("Save the external catalog document before linking its spreadsheet.")
    if spreadsheet.Document is not document and not document.FileName:
        raise ValueError("Save the model document before linking an external spreadsheet.")
    if spreadsheet.Document is not document and documentDependsOn(spreadsheet.Document, document):
        raise ValueError("The catalog already depends on this model; linking it would create a circular document dependency.")
    settingsObject = getSettings(document)
    if settingsObject is not None and "CatalogSpreadsheet" in settingsObject.PropertiesList:
        if settingsObject.CatalogSpreadsheet is spreadsheet:
            hideCatalogDependency(settingsObject)
            return
    document.openTransaction("Catalog BOM dependency")
    try:
        if settingsObject is None:
            settingsObject = document.addObject("App::FeaturePython", SETTINGS_NAME)
            settingsObject.Label = "Catalog BOM dependency"
        if "CatalogSpreadsheet" not in settingsObject.PropertiesList:
            settingsObject.addProperty("App::PropertyXLink", "CatalogSpreadsheet", "Catalog BOM")
        settingsObject.CatalogSpreadsheet = spreadsheet
        settingsObject.Label = "Catalog BOM dependency"
        hideCatalogDependency(settingsObject)
        if "CatalogPath" in settingsObject.PropertiesList:
            settingsObject.removeProperty("CatalogPath")
        document.recompute()
        document.commitTransaction()
    except Exception:
        document.abortTransaction()
        raise


def hideCatalogDependency(dependencyObject):
    """Keep the native link carrier internal without changing its dependency behavior."""
    viewObject = dependencyObject.ViewObject
    if viewObject is not None:
        viewObject.ShowInTree = False


def classifyTarget(target):
    """Classify the linked source, but return no replacement assignment target."""
    sourceObject = target
    if target.isDerivedFrom("App::Link"):
        if getattr(target, "ElementCount", 0):
            raise ValueError("Select an individual part or assembly, not a link array.")
        sourceObject = target.getLinkedObject(True)
        if sourceObject is None or sourceObject is target:
            raise ValueError("The selected link has no valid source object.")
    if sourceObject.isDerivedFrom("Assembly::AssemblyObject"):
        return "assembly"
    if sourceObject.isDerivedFrom("App::Part"):
        return "assembly" if getattr(sourceObject, "Type", "") == "Assembly" else "part"
    if sourceObject.isDerivedFrom("PartDesign::Body"):
        return "part"
    if sourceObject.isDerivedFrom("Part::Feature"):
        if sourceObject.isDerivedFrom("PartDesign::Feature"):
            raise ValueError("Select the Part Design Body, not an individual modeling feature.")
        if not sourceObject.Shape.Solids:
            raise ValueError("Select a solid part, not a sketch, surface, or datum object.")
        return "part"
    raise ValueError("Select a part, Body, part container, native assembly, or a link to one.")


def validateProperties(target):
    for propertyName, allowedTypes in (
        ("PartNumber", ("App::PropertyString",)),
        ("PartQuantity", ("App::PropertyInteger", "App::PropertyIntegerConstraint")),
    ):
        if propertyName in target.PropertiesList:
            if target.getTypeIdOfProperty(propertyName) not in allowedTypes:
                raise ValueError(f"{propertyName} has an incompatible existing property type.")
            if any(expressionPath == propertyName for expressionPath, expressionText in target.ExpressionEngine):
                raise ValueError(f"Remove the expression on {propertyName} before assigning it.")
            editorMode = target.getEditorMode(propertyName)
            if editorMode == 1 or (isinstance(editorMode, (list, tuple)) and "ReadOnly" in editorMode):
                raise ValueError(f"{propertyName} is not editable on the selected object.")


def assignPartNumber(target, partNumber, quantity):
    """Add properties and write both values in one transaction, only on Apply."""
    targetKind = classifyTarget(target)
    validateProperties(target)
    if not isinstance(partNumber, str) or not partNumber.strip():
        raise ValueError("Select a catalog entry with a nonempty PartNumber.")
    if targetKind == "part":
        quantity = 1
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MAX_QUANTITY:
        raise ValueError("Assembly quantity must be a positive whole number.")
    document = target.Document
    document.openTransaction("Catalog BOM Add PartNumber")
    try:
        if "PartNumber" not in target.PropertiesList:
            target.addProperty("App::PropertyString", "PartNumber", "Catalog BOM")
        if "PartQuantity" not in target.PropertiesList:
            target.addProperty("App::PropertyInteger", "PartQuantity", "Catalog BOM")
        target.PartNumber = partNumber
        target.PartQuantity = quantity
        document.recompute()
        document.commitTransaction()
    except Exception:
        document.abortTransaction()
        raise