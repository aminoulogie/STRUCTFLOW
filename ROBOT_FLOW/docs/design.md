# GCStructFlow Robot — initial modeling release

User-authorized destination: a new ROBOT_FLOW folder in aminoulogie/STRUCTFLOW,
whose desktop checkout is named GCSTRUCTFLOW. Existing files are outside scope.

## Outcome
A Robot menu command opens a compact desktop panel with original engineering icons,
menus and local keyboard shortcuts. Python/Tk follows the existing ETABS tool's
Python architecture; a small C# IRobotAddIn DLL provides the native menu entry.
Windows, 64-bit Python 3.10+, pythonnet 3 and Robot 2027 are the runtime target.
The SDK DLL is supplied by the user's Robot installation, never redistributed.

## Initial slice
- Named exact decimal elevations, offsets from named levels, active level selection.
- Independent Cartesian grid sets with origin, rotation, explicit X/Y coordinates,
  and chosen Z elevations. Create native Robot axes; list/toggle/isolate/restore grids.
- Concrete material creation with explicitly entered elastic constants; rectangular
  beam/column sections and homogeneous wall/floor thicknesses using existing materials.
- Coordinate-based column, beam, rectangular base, polygon panel and wall creation.
  All lengths use metres; material E uses MPa and unit weight uses kN/m3 in the UI.
- Read-only node/bar checks: close nodes, zero length and duplicate bars, missing
  section, and nodes slightly off a named level. Select affected IDs in Robot.
- Versioned JSON settings, atomic save/load, no model mutation on settings load.

## Boundaries
No analysis, loads, supports, automatic repair, meshing, design checks, or deletion
of existing model objects. Editing reference levels never moves existing geometry.
Native menu uses Autodesk's documented add-in registration; exact top-menu position,
docking, global shortcuts and interactive viewport picking are not promised.
The UI is a separate modeless tool window launched from Robot. Native integration
must be smoke-tested on Windows/Robot; Linux tests cannot validate the host API.

## Failure handling
Attach only to a running Robot; bind to its Project.UniqueId, reject project changes.
Validate complete geometry and labels before writes. Never overwrite existing labels
or grids. Reuse a node only if its position matches within 1e-8 m; ambiguous matches
are rejected. API writes may partially complete: errors identify that possibility,
and created object IDs are logged. Never retry failed mutations automatically.

## Validation
Unit tests exercise decimal parsing, relative levels/cycles, rotations, invalid
geometry, persistence, model diagnostics and project guard. UI smoke tests where a
Tk display is available. Manual Windows checklist verifies SDK, native launch,
material/section creation, axis positions/toggles, panel thickness and node reuse.
