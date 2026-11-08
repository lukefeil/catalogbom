"""Validate live-dimension selection, bindings, and failure safeguards without FreeCAD."""

import unittest
from unittest.mock import Mock, call

from catalogbom import dimensions


def makeObject(typeId, name, document):
    documentObject = Mock()
    documentObject.Name = name
    documentObject.Document = document
    documentObject.Type = "Part"
    documentObject.isDerivedFrom.side_effect = lambda candidateType: candidateType == typeId
    documentObject.PropertiesList = []
    documentObject.ExpressionEngine = []
    documentObject.State = []
    documentObject.getEditorMode.return_value = []
    documentObject.Group = []
    return documentObject


class DimensionTests(unittest.TestCase):
    def setUp(self):
        self.document = Mock()
        self.container = makeObject("App::Part", "Part", self.document)
        self.body = makeObject("PartDesign::Body", "Body", self.document)
        self.body.Shape.isNull.return_value = False
        self.body.Shape.Solids = [object()]
        self.body.Tip.Shape.isNull.return_value = False
        self.body.Tip.Shape.Solids = [object()]
        self.container.Group = [self.body]

    def test_properties_and_expressions_are_added_to_container(self):
        self.assertIs(dimensions.loadDimensions(self.container), self.container)
        self.assertEqual(self.container.setExpression.call_args_list, [
            call("Length", "Body.Tip.Shape.BoundBox.XLength"),
            call("Width", "Body.Tip.Shape.BoundBox.YLength"),
            call("Height", "Body.Tip.Shape.BoundBox.ZLength"),
        ])
        self.assertEqual(self.container.addProperty.call_count, 3)
        self.body.addProperty.assert_not_called()
        self.document.commitTransaction.assert_called_once()

    def test_zero_or_multiple_bodies_are_rejected(self):
        otherBody = makeObject("PartDesign::Body", "OtherBody", self.document)
        for children in ([], [self.body, otherBody]):
            with self.subTest(count=len(children)):
                self.container.Group = children
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    dimensions.loadDimensions(self.container)
        self.document.openTransaction.assert_not_called()

    def test_body_selection_is_not_silently_promoted(self):
        with self.assertRaisesRegex(ValueError, "part container"):
            dimensions.loadDimensions(self.body)

    def test_empty_body_is_rejected(self):
        self.body.Shape.isNull.return_value = True
        with self.assertRaisesRegex(ValueError, "valid solid"):
            dimensions.loadDimensions(self.container)
        self.document.openTransaction.assert_not_called()

    def test_existing_property_type_is_preserved(self):
        self.container.PropertiesList = ["Length"]
        self.container.getTypeIdOfProperty.return_value = "App::PropertyString"
        with self.assertRaisesRegex(ValueError, "incompatible"):
            dimensions.loadDimensions(self.container)
        self.container.addProperty.assert_not_called()
        self.document.openTransaction.assert_not_called()

    def test_unrelated_expression_is_preserved(self):
        self.container.PropertiesList = ["Length"]
        self.container.getTypeIdOfProperty.return_value = "App::PropertyLength"
        self.container.ExpressionEngine = [("Length", "Other.Length")]
        with self.assertRaisesRegex(ValueError, "another expression"):
            dimensions.loadDimensions(self.container)
        self.document.openTransaction.assert_not_called()

    def test_old_body_bounding_box_expression_is_migrated(self):
        self.container.PropertiesList = ["Length"]
        self.container.getTypeIdOfProperty.return_value = "App::PropertyLength"
        self.container.ExpressionEngine = [("Length", "Body.Shape.BoundBox.XLength")]
        dimensions.loadDimensions(self.container)
        self.container.setExpression.assert_any_call("Length", "Body.Tip.Shape.BoundBox.XLength")

    def test_body_without_tip_is_rejected(self):
        self.body.Tip = None
        with self.assertRaisesRegex(ValueError, "final feature"):
            dimensions.loadDimensions(self.container)
        self.document.openTransaction.assert_not_called()

    def test_failed_recompute_aborts_transaction(self):
        self.document.recompute.side_effect = RuntimeError("Recompute failed")
        with self.assertRaises(RuntimeError):
            dimensions.loadDimensions(self.container)
        self.document.abortTransaction.assert_called_once()
        self.document.commitTransaction.assert_not_called()

    def test_link_writes_dimensions_on_source_container(self):
        linkObject = makeObject("App::Link", "Instance", self.document)
        linkObject.ElementCount = 0
        linkObject.getLinkedObject.return_value = self.container
        self.assertIs(dimensions.loadDimensions(linkObject), self.container)
        linkObject.addProperty.assert_not_called()