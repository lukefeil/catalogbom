# Catalog BOM

A lightweight Python workbench for FreeCAD. Uses FreeCAD's built-in
Python APIs and the Python standard library; no pip dependencies are required.
Settings selects a saved spreadsheet as a global FreeCAD workbench preference.
Each consuming model retains a hidden native link and external dependency when
applicable. Add PartNumber browses
that catalog and assigns PartNumber and PartQuantity to a selected part or native
assembly. Catalog editing and bill-of-materials generation are not implemented.
Lookup PartNumber shows the assigned catalog entry; Edit opens the shared
Add/Change Part Number picker for changing the model's assignment.
See the user guide for the supported spreadsheet format and selection rules.
The selected spreadsheet can have any name, with row-1 headers PartNumber, Type,
Make, Model, Description, NominalDimensions, and Unit. No lookup sheets are required.

## Documentation

- [User guide](docs/userguide.md)
- [Architecture](docs/architecture.md)
- [Copilot instructions](.github/copilot-instructions.md)

## Layout

```text
catalogbom/                    # Installed directly under FreeCAD's Mod directory
|-- Init.py                    # Startup hook; must remain GUI-independent
|-- InitGui.py                 # GUI workbench registration
|-- catalogbom/
|   |-- __init__.py             # Implementation package and version
|   |-- workbench.py            # GUI workbench class
|   |-- commands.py             # Toolbar commands and Qt dialogs
|   |-- model.py                # Document settings and property assignment
|   |-- preferences.py          # User-wide FreeCAD workbench preference
|   `-- catalog.py              # Spreadsheet catalog reader
|-- Resources/
|   `-- icons/catalogbom.svg    # Workbench icon
|-- tests/                     # Startup, catalog/model, and native smoke checks
`-- .github/workflows/tests.yml # GitHub Actions checks
```

`Init.py` and `InitGui.py` are FreeCAD entry points, not ordinary package imports.
Keep class implementations in ordinary package modules: FreeCAD can execute startup
hooks with separate global and local namespaces, unlike a normal module import.
The implementation package and resource layout are conventions, not mandatory
FreeCAD directories. Add command modules under `catalogbom/` when needed and load
GUI commands inside `CatalogBOMWorkbench.Initialize()` to keep startup cheap.
Keep headless logic independent of `FreeCADGui`; use FreeCAD's bundled Qt bindings
if a custom interface becomes necessary rather than installing another Qt copy.

## Run In FreeCAD

This checkout is already in the Snap installation's user module directory:
`~/snap/freecad/common/Mod/catalogbom`. Restart FreeCAD and select **Catalog BOM**
in the workbench selector. Use Settings to choose the catalog spreadsheet, then select a
model object and use Add PartNumber. The catalog format is documented in the user
guide.

Save the catalog before choosing it globally, and save the model before using an
external spreadsheet dependency. The preference applies across models without a
visible settings object, while native model dependencies are retained internally.
See the user guide for lifecycle and migration from older model-specific settings.

For other installations, place this entire repository in the user `Mod` directory.
Find the user data directory from FreeCAD's Python console:

```python
import FreeCAD
print(FreeCAD.getUserAppDataDir())
```

Append `Mod/catalogbom` to that directory. Do not install only the inner Python
package. Restart FreeCAD after changing startup hooks; inspect **View > Panels >
Report view** for startup errors.

## Development Checks

From the repository root:

```sh
python3 -m unittest discover -s tests -v
```

The standard tests simulate FreeCAD APIs and check startup, catalog parsing,
settings, and assignment. Native tests are skipped without FreeCAD's runtime.
GitHub Actions runs these checks on Python 3.11
and 3.14. These are scaffold checks, not certification against those versions
of FreeCAD's embedded Python. Real FreeCAD startup and activation require a
separate smoke test in the installed application. Isolated native FreeCAD 1.1.4
and offscreen Qt checks passed; see the architecture for the native test command.

## Git And GitHub

The local Git repository uses the `main` branch. No remote, commit, license,
or GitHub repository is created automatically. Choose a license before public
distribution. FreeCAD Addon Manager publication metadata (`package.xml`) can be
added when the maintainer, repository URL, and license are decided; it is not
required for this local directory-based workbench.

After reviewing the scaffold, create the first commit:

```sh
git add .
git commit -m "Initialize Catalog BOM workbench scaffold"
```

Create an empty repository named `catalogbom` on GitHub, then connect and push it
(replace `YOUR_ACCOUNT`):

```sh
git remote add origin https://github.com/YOUR_ACCOUNT/catalogbom.git
git push -u origin main
```

## FreeCAD References

- [Workbench creation](https://wiki.freecad.org/Workbench_creation)
- [Workbench structure](https://wiki.freecad.org/Workbench_structure)
- [Official Python module template](https://github.com/FreeCAD/FreeCAD/tree/main/src/Mod/TemplatePyMod)
- [Current GUI module loader](https://github.com/FreeCAD/FreeCAD/blob/main/src/Gui/FreeCADGuiInit.py)

The wiki may require browser verification. The scaffold's entry points were
cross-checked against FreeCAD's current published GUI loader and module template.