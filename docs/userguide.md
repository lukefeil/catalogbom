# Catalog BOM User Guide

## Current Capabilities

Catalog BOM provides **Settings**, **Add PartNumber**, and **Lookup PartNumber**
in its toolbar and menu. It reads your spreadsheet catalog, displays assigned
catalog entries, and assigns a catalog part number and quantity
to a selected part or assembly. It does not create or edit catalog files or
generate a bill of materials yet.
No additional Python packages are required.

## Catalog Workflow

The catalog format below applies to the spreadsheet selected in Settings. Object
selection and quantity defaults remain as documented; provide a sample model if
your assembly workflow differs from the supported cases.

### Catalog File

Select a spreadsheet in the current model document or in another FreeCAD file.
Its label and internal name can be anything. Settings chooses the actual sheet
and remembers its saved filename and internal name as a global preference; label
changes do not break selection. Models retain native links to the sheet they use.
Other spreadsheets are ignored.
Catalog BOM reads the selected sheet without creating or editing catalog cells.
Use the following row-1 headers:

| PartNumber | Type | Make | Model | Description | NominalDimensions | Unit |
| --- | --- | --- | --- | --- | --- | --- |
| PN-001 | Bolt | Acme | Model X | Hex bolt | M6 | ea |

All seven headers must be present. Header matching ignores case, spaces, and
punctuation, and columns are mapped by header rather than fixed cell position.
The picker displays the order above. Values are read directly from the sheet;
there are no lookup tables or ID joins. PartNumber must be nonempty and unique.
The other cell values, including Unit, may be blank. Fully blank rows are ignored.
Format identifiers as spreadsheet text when leading zeros matter. Spreadsheet
formulas are read as evaluated values.

Unit is available for display, sorting, column filtering, and global search.
It is not copied to the selected object and does not change quantity rules or
trigger unit conversions. Only PartNumber and PartQuantity are assigned.

### Settings

The **Settings** command selects the global catalog spreadsheet used by this
workbench across model documents. It is available even without an active model:

1. Choose the current document or another open document from **Document**.
2. To use a file that is not open, choose the folder button and browse to a
   FreeCAD file. It opens and becomes available in the document menu.
3. Choose a sheet from **Spreadsheet**. Menus show labels and internal names to
   distinguish objects with identical labels.
4. Choose **Save** to validate the table and update the workbench preference.

The catalog document must be saved so its sheet can be found in a later session.
The preference is stored in FreeCAD's user parameter group
`BaseApp/Preferences/Mod/CatalogBOM`, using CatalogFile and CatalogSheet. It is not
stored as a user-editable settings object in the model tree.

Native dependencies are retained separately: each consuming model holds an
internal spreadsheet link, hidden from the normal tree. This helper owns the
FreeCAD document dependency; it is not the global setting. External dependencies
require the model and source documents to be saved. Settings updates the active
model's link when possible; other models update theirs when Add PartNumber or
Lookup PartNumber next uses the global catalog. With an unsaved model, the global
preference can be saved, but save the model before using an external catalog.
Save the model normally to persist its native dependency to disk.

Cancel leaves the global preference unchanged. Already open documents are not
closed; unused files opened by the dialog are closed on completion. The configured
source remains open after Save. No catalog cells are changed or saved. Circular
native document dependencies are rejected.

Moving the catalog file or deleting its sheet requires reselecting it in Settings.
Saved native links still let FreeCAD load model dependencies when reopening a
model; changing the global preference does not retroactively edit closed files.
Existing model-specific links continue working if no global catalog has been set.
Choose a global catalog once in Settings to migrate, rather than configuring each
model. Existing link carriers are made internal when accessed; obsolete CatalogPath
properties are removed when their native link is updated.

### Add/Change Part Number

The shared picker is titled **Add/Change Part Number**. Open it from the
**Add PartNumber** toolbar command or from **Edit** in the lookup dialog.
If the object already has a PartNumber present in the catalog, that row is
selected initially.

1. Select a part or assembly in the model tree and choose **Add PartNumber**.
2. If there is no valid selection, show an error.
3. The command checks existing `PartNumber` and `PartQuantity` properties for
   compatible types and editability. Missing properties are created only on Apply.
4. Open a shared catalog picker using the spreadsheet selected in Settings.
5. Browse catalog rows with columns, per-column filters, sorting, and a search bar.
6. Select one catalog entry and choose **Apply** to write its `PartNumber` and
   the quantity to the selected target, then close the dialog. Apply is disabled
   until a row is selected. Cancel leaves PartNumber and PartQuantity unchanged.

Catalog resolution may establish or update the internal dependency before the
picker opens. This bookkeeping can mark the model modified even if the assignment
dialog is canceled; it never creates PartNumber or PartQuantity until Apply.

Click table headers to sort. Each column filter uses a case-insensitive substring;
column filters combine with AND. Global search matches any column and combines
with the column filters. Only PartNumber and PartQuantity are copied to the model.

For a part, the **Quantity** control is disabled and `PartQuantity` is always set
to 1. For an assembly, the same dialog enables Quantity and writes the entered
value to `PartQuantity`. `PartQuantity` is the property name; Quantity is its
dialog label, not an additional `QTY` property.

Assembly quantities are positive whole numbers, initially using an existing valid
PartQuantity or 1. New properties use `App::PropertyString` for PartNumber and
`App::PropertyInteger` for PartQuantity, grouped under **Catalog BOM**. Existing
integer-constraint quantity properties are also accepted. Expression-driven,
read-only, or incompatible properties cause an error rather than being replaced.
Assignments are one undoable document transaction. Save the model to persist them.

### Lookup PartNumber

1. Select one supported part or assembly object in the active model document.
2. Choose **Lookup PartNumber** in the toolbar or menu.
3. The dialog shows just the matching catalog entry's PartNumber, Type, Make,
   Model, Description, NominalDimensions, and Unit as read-only, selectable text.
4. Choose **Edit** to open **Add/Change Part Number** for this same object.
5. Applying a change closes the picker and refreshes the lookup details. Cancel
   leaves the assignment and lookup details unchanged. **Close** dismisses lookup.

Lookup matches the stored PartNumber exactly, including case. An unassigned object
or a number absent from the configured catalog produces an error rather than an
empty dialog. Assign a number through Add PartNumber first if none is present.
Lookup itself does not create properties, alter quantity, or modify the catalog.
Read-only assignment properties can be viewed, but Edit requires editable,
compatible properties. Edit changes the model's assignment, not catalog cells.

### Supported Selections

Select exactly one whole tree object belonging to the active model document:

- Part Design Body: treated as a part, quantity 1. Individual modeling features
   are rejected; select their Body instead.
- Part geometry object containing a solid: treated as a part, quantity 1.
- App::Part container: treated as a part unless its native Type is `Assembly`.
- Built-in FreeCAD `Assembly::AssemblyObject`: treated as an assembly.
- An individual App::Link to a supported object: classified by its source, but
   properties are written on the selected instance, not the shared source.

Faces, edges, sketches, non-solid geometry, link arrays, and multiple selections
are rejected. Other assembly add-ons are not automatically recognized. A plain
group or part container is not inferred to be an assembly merely from its label
or child count. Missing paths and malformed catalogs show an error.

The sheet's currently evaluated values are used without saving or modifying
catalog cells. Commands reuse the global catalog if open, otherwise load its file,
resolve the stored internal sheet name, and retain a native model dependency.
The active model is restored after loading. Newly opened files are closed on
failure only if no existing document depends on them. Missing files, sheets, or
unresolved legacy links produce an error directing you to Settings.

## Installation

Place the entire repository in FreeCAD's user module directory as `Mod/catalogbom`.
The repository root must contain `Init.py` and `InitGui.py`; copying only the
inner `catalogbom` package is not sufficient.

This development checkout is already located at
`~/snap/freecad/common/Mod/catalogbom` for the Snap installation.
For other installations, open FreeCAD's Python console and run:

```python
import FreeCAD
print(FreeCAD.getUserAppDataDir())
```

Use the `Mod/catalogbom` subdirectory of the printed user data directory.
Restart FreeCAD after installing the workbench.

## Opening The Workbench

1. Start or restart FreeCAD.
2. Select **Catalog BOM** from the workbench selector.
3. Confirm its toolbar contains **Settings**, **Add PartNumber**, and
   **Lookup PartNumber**, then configure the catalog and select a model object.

## Troubleshooting

If the workbench does not appear, check the installation path and confirm that
both startup files are at the repository root. Restart FreeCAD after correcting
the installation or editing startup files.

For initialization errors, open **View > Panels > Report view** and capture the
error text. Enable FreeCAD logging if a full startup traceback is needed.

### Capturing A Startup Log

No existing FreeCAD log was found in the accessible locations checked on this
development machine. The Report view message alone does not confirm that file
logging is enabled. For a predictable destination, fully exit FreeCAD, then run:

```sh
snap run freecad --log-file "$HOME/snap/freecad/common/FreeCAD.log"
```

The selected log path is `/home/lukefeil/snap/freecad/common/FreeCAD.log` on this
machine. This is an explicit capture destination, not a discovered existing log.
If the Snap launcher does not forward the option, use:

```sh
snap run --shell freecad -c 'exec "$SNAP/usr/bin/FreeCAD" --log-file "$SNAP_USER_COMMON/FreeCAD.log"'
```

After reproducing the error, check the file's modification time and read the
latest entries:

```sh
stat "$HOME/snap/freecad/common/FreeCAD.log"
tail -n 120 "$HOME/snap/freecad/common/FreeCAD.log"
```

FreeCAD also supports `--write-log`, which uses `FreeCAD.log` in its user
directory; an explicit path avoids ambiguity across installations. FreeCAD
runtime logs are separate from this project's unittest output in the terminal.

### Previous Startup Scope Error

A previous `name 'Path' is not defined` startup error was caused by executing a
class definition inside the GUI startup hook with separate global and local
namespaces. The class now lives in an ordinary package module. Ensure the updated
`InitGui.py` and `catalogbom/workbench.py` are installed together, then restart.

## Verification Status

Standard-library tests cover startup, catalog parsing, path handling, and model
assignment with simulated APIs. Additional isolated smoke tests passed using this
installation's FreeCAD 1.1.4 bundled Python: native spreadsheet loading, settings,
part and assembly assignments, link-instance isolation, and offscreen Qt picker
filtering and Apply. These tests use temporary documents, not your catalog.
Normal on-screen workbench startup and interaction in your running FreeCAD still
need a user smoke test; compatibility with other releases or assembly add-ons is
not established.

For implementation details, see [the architecture](architecture.md).
For development checks and GitHub setup, see [the README](../README.md).