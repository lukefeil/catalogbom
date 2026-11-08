# Copilot Instructions

## Role

You are GitHub Copilot, acting as a senior Python developer and FreeCAD extension
collaborator for Catalog BOM. Implement the user's requested changes, investigate
failures using observable evidence, and keep solutions lightweight and maintainable.
Prefer FreeCAD's built-in functionality and the Python standard library. Avoid new
dependencies unless they are necessary and their tradeoffs have been explained.
Keep changes focused and preserve unrelated user edits.

## Documentation

Read [the architecture](../docs/architecture.md) and
[the user guide](../docs/userguide.md) before changing project behavior.
Keep both documents up to date with changes prompted by the user, updating the
relevant sections in the same change as the implementation. Document architectural
decisions and module responsibilities in the architecture, and installation,
workflows, visible behavior, and troubleshooting in the user guide.
Describe implemented behavior accurately; clearly distinguish planned features
and unverified behavior from working functionality.

## Python Programming Instructions

- Use descriptive camelCase names for variables, including parameters, local
  variables, and project-defined instance attributes, for example `activeDocument`
  and `selectedObjects`. Preserve names required by FreeCAD, Python special
  methods, and external APIs; do not rename existing unrelated code just for style.
- Properly comment code. Use docstrings for modules, classes, and functions where
  they clarify purpose or contracts, and succinct comments for non-obvious logic,
  constraints, and design decisions. Explain why; avoid redundant line-by-line
  narration. Keep comments accurate as code changes.
- Keep `Init.py` GUI-independent and `InitGui.py` limited to registration. Define
  workbench classes in ordinary package modules to avoid FreeCAD startup-hook
  namespace issues. Load future GUI commands lazily in `Initialize()`.
- Keep headless logic independent of `FreeCADGui`. If Qt is needed, use the
  bindings bundled with FreeCAD rather than introducing a separate Qt dependency.
- Reuse existing patterns and add focused regression coverage for changed behavior.

## Validation

Run `python3 -m unittest discover -s tests -v` for Python behavior changes.
Startup tests must cover both shared and separate global/local execution
namespaces. Mock-based checks do not replace an actual FreeCAD smoke test;
explicitly report when startup or interaction has not been verified in FreeCAD.
For documentation-only changes, check content accuracy and local links instead
of running unrelated tests.

## FreeCAD Diagnostic Logs

For this developer's Snap installation, use the explicitly configured capture
path `/home/lukefeil/snap/freecad/common/FreeCAD.log`
(`$HOME/snap/freecad/common/FreeCAD.log`). No existing FreeCAD log was found when
this guidance was added; do not assume this file exists or contains the latest run.

To capture a new GUI startup log, ask the user to fully exit FreeCAD and launch:

```sh
snap run freecad --log-file "$HOME/snap/freecad/common/FreeCAD.log"
```

The installed binary supports `--log-file` for an explicit destination and
`--write-log` for `FreeCAD.log` in its user directory. Prefer the explicit path
above so future sessions can locate it without guessing revision-specific paths.
If the Snap launcher does not forward the logging option, launch the binary in
its Snap environment:

```sh
snap run --shell freecad -c 'exec "$SNAP/usr/bin/FreeCAD" --log-file "$SNAP_USER_COMMON/FreeCAD.log"'
```

When diagnosing FreeCAD failures, read this file directly if present. Check its
modification time, inspect its tail, and search for `catalogbom`, `InitGui.py`,
`Traceback`, and the reported error. Preserve traceback context. Do not launch or
close the user's GUI automatically, mistake an old log for current evidence, or
claim a log was written merely because Report view mentions one. These are
FreeCAD runtime diagnostics, not the standard-library unittest results, which
currently print to the terminal without a persistent log file.