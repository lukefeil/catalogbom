# Catalog BOM Architecture

## Scope And Principles

Catalog BOM is a directory-based Python workbench for FreeCAD. The current
implementation provides Settings, Add PartNumber, and Lookup PartNumber commands,
spreadsheet catalog reading, and model property assignments. Catalog editing and BOM generation are
not implemented.

Prefer FreeCAD's built-in document and GUI APIs and the Python standard library.
There are no third-party Python dependencies, build steps, or package installation
requirements for the scaffold. Keep startup cheap and future headless logic
separate from GUI code.

## Catalog Commands And Data Contracts

The catalog contract follows the user's table format on one selected spreadsheet. Model selection and
quantity behavior use the documented defaults. Different schemas and assembly
add-ons require explicit support rather than silent inference.

### Spreadsheet Catalog

The catalog is a selected Spreadsheet::Sheet object in the model document or an
external FreeCAD document. The global selection stores its saved filename and
internal Name in FreeCAD preferences; consuming models retain a native object
reference separately. Both labels and sheet counts are unrestricted. No catalog
creation or editing command is provided.

Row 1 contains PartNumber, Type, Make, Model, Description, NominalDimensions, and
Unit. All seven headers are required, matched ignoring case and punctuation.
Column positions are resolved from headers; picker order follows this field list.
The reader uses native Spreadsheet APIs to read populated cells and evaluated
values directly. Lookup sheets and relational joins are no longer used.
PartNumber must be nonempty and unique; remaining values may be blank. Missing
headers, duplicate headers, invalid PartNumbers, and empty catalogs are errors.
No SQLite or external database dependency is used.

readCatalog receives the spreadsheet directly. loadCatalog resolves the global
preference against open files or opens the configured file, parses the selected
sheet, and binds the consuming model's native link. On failure it closes only new
documents without dependents, and always restores the active model. With no global
preference, an existing saved model link is supported for migration. Catalog cells
are never modified or saved. GUI code captures the target before loading.

### Global Preference And Native Dependencies

preferences.py owns the user-wide selection through FreeCAD.ParamGet at
`User parameter:BaseApp/Preferences/Mod/CatalogBOM`. CatalogFile stores an absolute
saved filename and CatalogSheet stores the spreadsheet's internal Name. All models
use this global choice when catalog commands run; changing it does not rewrite
closed model files. The source must be saved, including a sheet chosen in the
current document. No global preference is represented by a model tree object.

Native dependencies require a document-object owner. model.py maintains an internal
App::FeaturePython carrier, retaining the name CatalogBOMSettings for compatibility,
with CatalogSpreadsheet as App::PropertyXLink and label Catalog BOM dependency.
Its view provider has ShowInTree=False. This is dependency bookkeeping, not the
configuration source. Both owner and source must be saved for an external link;
the native link preserves FreeCAD dependency loading and reference serialization.
Identical bindings do not create repeated transactions. A new or changed binding
uses a Catalog BOM dependency transaction and can mark the model modified before
an assignment dialog opens. Cancellation preserves assignment properties, not
necessarily this dependency bookkeeping.

SettingsDialog presents current/open documents and sheets and can run without an
active model. It opens the configured source when needed; Browse reuses matching
open files. Save validates the table and preference locator, updates the active
model dependency if its save requirements permit, and sets the global parameters.
An unsaved model can configure an external catalog but must be saved before using
its native dependency. Already open documents are never closed. Dialog-created
unused documents are closed on completion; the saved global source and anything
depended on by existing documents are retained. Cancel does not change preferences.

Legacy model links are used only when no global choice exists. Reading/updating
their carrier hides it; updating the link removes obsolete CatalogPath properties.
documentDependsOn follows native OutList links across document boundaries and
rejects circular external dependencies before a binding write.

### Object Classification And Property Targets

FreeCAD workbench names and tree labels are not sufficient object classifiers.
Part geometry objects such as `Part::Feature`, Part Design bodies
(`PartDesign::Body`), part containers (`App::Part`), assembly containers, and linked
instances (`App::Link`) require distinct treatment. An `App::Part` is a general
container, not proof of an assembly; a body contains features rather than being
an assembly. A face or modeling feature selection is not automatically the
intended catalog target.

The installed FreeCAD 1.1.4 creation code uses Assembly::AssemblyObject for its
built-in assembly. That type and App::Part objects with Type equal to Assembly
are recognized as assemblies. Plain App::Part containers and PartDesign::Body
objects are parts. Part::Feature objects are accepted if they contain a solid,
except individual PartDesign::Feature objects, which require selecting the Body.
Other groups and assembly add-ons are not inferred from labels or child counts.

GUI selection requires exactly one whole object in the active model document;
subelement selections are rejected. An individual App::Link is classified by its
recursively linked source, but assignments remain on the selected instance.
Link arrays and unresolved links are rejected. No child traversal or automatic
parent promotion changes the property target.

### Shared Catalog Picker

Settings, Add PartNumber, and Lookup PartNumber commands are registered lazily
during workbench initialization. FreeCAD's bundled PySide Qt bindings provide
the dialogs.
The shared picker uses a read-only QStandardItemModel, QTableView, and a custom
QSortFilterProxyModel with sorting, AND-combined per-column substring filters,
and global substring search across any column. Matching is case-insensitive.
Rows show directly evaluated catalog values, including Unit. No external UI
dependency is used. Unit is display/filter/search data only; it does not add a
model property or alter the integer quantity rules.

CatalogDialog retains its implementation class name but is titled
Add/Change Part Number. It preselects the object's current PartNumber if found
in the catalog. The Add PartNumber toolbar name and command identifier remain
unchanged so existing workbench registration stays compatible.

Add PartNumber validates the selection and checks for `PartNumber` and
`PartQuantity` custom properties. Apply writes the selected catalog key to
`PartNumber`; for parts it writes quantity 1 and disables the quantity control,
while for assemblies it enables the control and writes the entered quantity.
Only these two target properties are requested, not copies of all catalog fields.

New PartNumber properties use App::PropertyString, and PartQuantity uses
App::PropertyInteger. Existing App::PropertyIntegerConstraint quantities are also
accepted. Quantity ranges from 1 to 2147483647; assemblies start with an existing
valid quantity or 1. Part quantity is forced to 1 in the model layer, independently
of the disabled dialog control. Existing incompatible, read-only, or
expression-driven properties are rejected, using FreeCAD's ExpressionEngine and
getEditorMode flag list.

Missing properties are added only on Apply, so Cancel leaves the model unchanged.
Both writes share one document transaction, which is aborted on failure. Apply
requires a selected row, writes the target, and closes the picker. Changes become
persistent when the user saves the model.

### Lookup And Edit

LookupPartNumberCommand uses the same selectedTarget helper as assignment, so
whole-object selection and active-document rules remain consistent. It requires
a nonempty string PartNumber but does not require editable assignment properties
for viewing. The catalog reader's findEntry helper matches identifiers exactly
and reports unassigned or absent identifiers without changing data.

LookupDialog displays only the matching row's seven catalog fields in a scrollable
read-only form, with selectable, word-wrapped plain-text values. Plain-text mode
prevents catalog content from being interpreted as rich-text markup.
Edit validates property compatibility and editability, then opens CatalogDialog
for the same target and loaded catalog snapshot. Accepted edits refresh the detail
labels; cancellation leaves the view and object unchanged. Closing lookup does
not modify either document. Lookup does not create properties or change quantity.

### Verification Coverage

Regression tests cover direct-reference validation, name-independent sheet/header parsing, invalid
keys, classifications, instance targeting, existing property compatibility,
quantity rules, transactions, legacy migration, save requirements, and cycle checks.
Optional native smoke tests use temporary FreeCAD documents and offscreen Qt to
verify spreadsheet reads, setting persistence, repeated assignment, real links,
native assembly quantities, filtering, Apply, lookup details, Edit/Cancel refresh,
lookup errors, read-only Edit rejection, command registration, spreadsheet chooser
Save/Cancel, browsed-document cleanup, dependency retention, and external-link
save/reopen after a label rename. Full on-screen workbench startup
and the user's actual catalog/model remain separate verification requirements.

## Structure

| Path | Responsibility |
| --- | --- |
| `Init.py` | GUI-independent FreeCAD startup hook; currently only a docstring. |
| `InitGui.py` | Imports and registers a `CatalogBOMWorkbench` instance. |
| `catalogbom/__init__.py` | GUI-independent package entry point and version (`0.1.0`). |
| `catalogbom/workbench.py` | GUI workbench class, icon path, and activation hook. |
| `catalogbom/commands.py` | Toolbar handlers, Settings dialog, shared picker, lookup detail dialog. |
| `catalogbom/model.py` | Internal native dependencies, dependency checks, target classification, transactional writes. |
| `catalogbom/preferences.py` | Standard FreeCAD user-wide workbench catalog preference. |
| `catalogbom/catalog.py` | GUI-independent evaluated parsing of the directly linked spreadsheet. |
| `Resources/icons/catalogbom.svg` | Workbench selector icon. |
| `Resources/icons/settings.svg` | Settings toolbar icon. |
| `Resources/icons/lookup.svg` | Lookup PartNumber toolbar icon. |
| `tests/test_startup.py` | Standard-library startup regression tests. |
| `tests/test_catalog.py` | Catalog and model regressions with simulated APIs. |
| `tests/test_native.py` | Optional native FreeCAD and offscreen Qt integration smoke tests. |
| `.github/workflows/tests.yml` | Runs scaffold checks on Python 3.11 and 3.14. |
| `.github/copilot-instructions.md` | Shared Copilot role, coding, and documentation rules. |
| `docs/userguide.md` | Installation, current user-facing behavior, and troubleshooting. |
| `docs/architecture.md` | Implementation structure, constraints, and verification boundaries. |

## Startup And Activation

FreeCAD discovers the installed directory under its user `Mod` directory and
executes the root startup hooks. `Init.py` does not import GUI modules and is safe
for headless startup. During GUI startup, `InitGui.py` imports `FreeCADGui` and the
workbench class, then calls `FreeCADGui.addWorkbench()` with an instance.

`CatalogBOMWorkbench` inherits from `FreeCADGui.Workbench`. Its `MenuText`,
`ToolTip`, and `Icon` provide selector metadata; `GetClassName()` returns
`Gui::PythonWorkbench`. The icon path is resolved relative to the implementation
module's location, not the working directory.

`Initialize()` imports the GUI commands, registers them, and attaches the Catalog
BOM toolbar and menu. Command and Qt code is not loaded by the GUI registration
hook at startup. No additional command framework is needed.

## Startup Namespace Constraint

FreeCAD can execute `InitGui.py` with distinct global and local namespaces.
Imports in the hook can then be visible to top-level expressions but unavailable
inside class bodies or methods. Defining the workbench class directly in the hook
previously caused `NameError: name 'Path' is not defined` during icon evaluation.

Keep implementation classes in normally imported Python modules, where imports
and definitions share a module namespace. Keep the hook registration-only and
avoid relying on the hook's `__file__` being available.

## Coding And Extension Boundaries

Use descriptive camelCase variable names for new Python code, with exceptions
for names imposed by FreeCAD and other external APIs. Properly document purpose,
contracts, and non-obvious decisions with docstrings and meaningful comments.
These conventions do not require unrelated renaming of existing code.

The model and catalog modules do not import FreeCADGui or Qt; they receive document
or application objects explicitly. GUI-specific code uses FreeCAD's bundled Qt
bindings. Do not introduce another Qt installation or speculative layers before
an implemented feature needs them.

## Validation

Run from the repository root:

```sh
python3 -m unittest discover -s tests -v
```

Startup coverage includes shared and separate execution namespaces, lazy command
registration, GUI-independent initialization, and SVG validity. Standard Python
runs simulated-API tests and skips native smoke tests when FreeCAD cannot be
imported. CI's Python versions are test environments, not FreeCAD compatibility
claims.

For this Snap installation, run the native smoke tests in an isolated offscreen
process from the repository root:

```sh
env QT_QPA_PLATFORM=offscreen snap run --shell freecad -c 'PYTHONPATH="$PWD:$SNAP/usr/lib:$SNAP/usr/Ext:$PYTHONPATH" exec "$SNAP/bin/python3" -m unittest discover -s tests -p test_native.py -v'
```

The native smoke tests passed with FreeCAD 1.1.4. They do not launch or alter the
user's open GUI session and use only temporary model/catalog files. Normal
on-screen startup, command registration in a real workbench, and the user's
actual catalog still require a separate smoke test.

### Runtime Diagnostic Logs

The local Snap binary supports `--write-log` (the user-directory default) and
`--log-file` (an explicit destination). The documented capture destination is
`$HOME/snap/freecad/common/FreeCAD.log`, outside the repository and independent of
Snap revision directories. No pre-existing log was found in accessible locations;
the configured path is not evidence of a captured GUI startup.

See [the user guide](userguide.md#capturing-a-startup-log) for launch commands.
Copilot should check file existence and modification time before reading runtime
diagnostics. The startup unit tests do not create a persistent log; their output
remains in the invoking terminal or GitHub Actions job.

## Documentation Maintenance

Update this architecture and [the user guide](userguide.md) alongside relevant
user-requested implementation changes. Keep architectural decisions here and
user-facing workflows in the guide. Update verification status only when evidence
supports it. See [the README](../README.md) for Git and GitHub setup; no publication
metadata or license has been chosen as part of this scaffold.