"""Live part-container dimensions sourced from one nested Part Design Body."""

from catalogbom import model


DIMENSION_AXES = (("Length", "XLength"), ("Width", "YLength"), ("Height", "ZLength"))


def partContainer(target):
    """Keep dimensions on the source part container, never on an assembly instance."""
    container = target
    if target.isDerivedFrom("App::Link"):
        if getattr(target, "ElementCount", 0):
            raise ValueError("Select an individual part container, not a link array.")
        container = target.getLinkedObject(True)
        if container is None or container is target:
            raise ValueError("The selected link has no valid part container source.")
    if not container.isDerivedFrom("App::Part") or model.classifyTarget(container) != "part":
        raise ValueError("Load Dimensions requires a part container, not a Body, feature, or assembly.")
    return container


def nestedBody(container):
    """Find a single owned Body, excluding linked geometry and nested assemblies."""
    pendingObjects = list(container.Group)
    visitedNames = set()
    bodies = []
    while pendingObjects:
        child = pendingObjects.pop()
        if child.Name in visitedNames:
            continue
        visitedNames.add(child.Name)
        if child.Document is not container.Document or child.isDerivedFrom("App::Link"):
            continue
        if child.isDerivedFrom("PartDesign::Body"):
            bodies.append(child)
        elif child.isDerivedFrom("App::Part"):
            if model.classifyTarget(child) == "part":
                pendingObjects.extend(child.Group)
        elif child.isDerivedFrom("App::DocumentObjectGroup"):
            pendingObjects.extend(child.Group)
    if len(bodies) != 1:
        raise ValueError("The part container must contain exactly one nested Part Design Body.")
    return bodies[0]


def loadDimensions(target):
    """Create native unit-aware properties and live expressions in one transaction."""
    container = partContainer(target)
    body = nestedBody(container)
    if body.Shape.isNull() or not body.Shape.Solids:
        raise ValueError("The nested Body must contain valid solid geometry.")
    if body.Tip is None or body.Tip.Shape.isNull() or not body.Tip.Shape.Solids:
        raise ValueError("The nested Body must have a valid final feature (Tip).")
    expressions = {propertyName: f"{body.Name}.Tip.Shape.BoundBox.{axisName}"
                   for propertyName, axisName in DIMENSION_AXES}
    legacyExpressions = {propertyName: f"{body.Name}.Shape.BoundBox.{axisName}"
                         for propertyName, axisName in DIMENSION_AXES}
    existingExpressions = dict(container.ExpressionEngine)
    for propertyName, expressionText in expressions.items():
        if propertyName not in container.PropertiesList:
            continue
        if container.getTypeIdOfProperty(propertyName) != "App::PropertyLength":
            raise ValueError(f"{propertyName} already exists with an incompatible property type.")
        editorMode = container.getEditorMode(propertyName)
        if editorMode == 1 or (isinstance(editorMode, (list, tuple)) and "ReadOnly" in editorMode):
            raise ValueError(f"{propertyName} is read-only on the part container.")
        if existingExpressions.get(propertyName) not in (None, expressionText, legacyExpressions[propertyName]):
            raise ValueError(f"{propertyName} already has another expression; it will not be overwritten.")
    document = container.Document
    document.openTransaction("Catalog BOM Load Dimensions")
    try:
        for propertyName, expressionText in expressions.items():
            if propertyName not in container.PropertiesList:
                container.addProperty("App::PropertyLength", propertyName, "Catalog BOM Dimensions")
            container.setExpression(propertyName, expressionText)
        document.recompute()
        if "Invalid" in container.State:
            raise ValueError(f"Dimension expressions could not be evaluated: {container.getStatusString()}")
        document.commitTransaction()
    except Exception:
        document.abortTransaction()
        raise
    return container