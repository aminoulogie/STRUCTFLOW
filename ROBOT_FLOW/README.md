# GCStructFlow — Robot modeling tools

Initial source release for **Autodesk Robot Structural Analysis Professional 2027**.
This folder is independent of the repository's Revit, AutoCAD and ETABS tools.

**Status:** geometry/domain tests run on Linux. The Windows UI, Robot API operations,
C# compilation, COM registration and native menu placement still require the
Windows smoke test below. This is a development preview, not a verified installer
or a completed production add-in. No Autodesk binaries are included.

## What is included

- Exact named reference levels and offsets from other levels; decimal comma or point.
- Cartesian grid definitions with independent origin, rotation and selected levels.
- Native Robot grid creation and show/hide/only/restore commands.
- New concrete elastic material labels, rectangular column/beam sections and
  homogeneous wall/floor thickness labels. Existing labels are never overwritten.
- Columns and walls between reference levels; beams by endpoints; rectangular
  bases and planar polygon panels, including sloping pool bases.
- Isolation in a new Robot view and return to the original view.
- Read-only node/bar checks: nearby nodes, duplicate/zero-length bars, missing
  sections and nodes slightly off a reference level. Select a finding's objects.
- Versioned JSON settings and a sample pool with irregular elevations.
- C# `IRobotAddIn` menu launcher, small original icons, menus and local shortcuts.

The tool panel is a **separate modeless Windows window launched from Robot**.
It is not docked into Robot. Exact placement beside Communauté, global shortcuts,
graphical picking inside Robot, panel connectivity checks, automatic repair,
openings, supports/restraints and analysis are follow-up work.

## Start the panel

On the Windows computer with Robot installed, open a terminal in `ROBOT_FLOW`:

```powershell
python -m pip install -r requirements.txt
python run.py
```

Or double-click `Lancer.bat`. Use **64-bit Python 3.10+ with Tk**, `.NET Framework
4.x`, and `pythonnet 3`. Robot 2027 must be running with a project open. Click
**Connect**. Only one Robot process should be running when connecting: the COM
Running Object Table does not provide a reliable user-facing instance picker.
The native menu launcher passes the launching project's ID and refuses a mismatch.

The default SDK search checks:

```text
C:\Program Files\Autodesk\Robot Structural Analysis Professional 2027\Exe\Interop.RobotOM.dll
C:\Program Files\Autodesk\Robot Structural Analysis Professional 2027\System\Exe\Interop.RobotOM.dll
```

For another installation location, set `ROBOTOM_DLL` to the full DLL path in the
same terminal before launching. Do not download arbitrary interop DLLs.

## Build and install the native Robot menu

Keep this folder in a permanent location. Close Robot. In 64-bit Windows
PowerShell, first build without registration:

```powershell
.\plugin\BuildAndInstall.ps1 -PythonExe 'C:\path\to\python.exe'
```

If the SDK is elsewhere, add `-RobotDll 'C:\path\to\Interop.RobotOM.dll'`.
The script checks Python and compiles the C# launcher using the Windows .NET
Framework compiler. It copies the local SDK DLL into `plugin/bin` for runtime
resolution; that folder is ignored by Git.

To register, run the same command with **`-Install`** from elevated 64-bit Windows
PowerShell **under your normal Windows account**. Registration adds this add-in's
COM class and its own HKCU Robot AddIns/MenuExtension keys. Start Robot and look
for **GCStructFlow Robot** in **Add-ins / Modules complémentaires**. Menu position
is controlled by Robot; placing it beside Communauté is not yet validated.

The menu offers Levels, Grids, Properties, Draw and Checks. Only one panel is
launched by each add-in instance. Select tabs in the panel if it is already open.
The Python console remains visible so startup failures can be read.

To unregister, close Robot and run `plugin/Uninstall.ps1` from elevated 64-bit
Windows PowerShell under the same account, before deleting or moving the folder.
If PowerShell blocks local scripts, use your organization's approved script policy;
the installer does not change the machine's execution policy.

## First pool workflow

1. Open a **copy** of a Robot 3D shell/building model and connect the panel.
2. Open `examples/pool.gcrobot.json`, or enter your actual levels. The sample uses
   Deck +0.23 m, shallow bottom −1.22 m, deep bottom −2.14 m and wall top +0.43 m.
3. Double-click a level to use it as the drawing reference. Editing levels changes
   reference data only; it never moves already-created Robot elements.
4. Add Pool, Columns and Walls grid sets. Coordinates use semicolons (`0; 2.37; 5.12`)
   so decimal commas remain unambiguous. Blank level names means all reference levels.
5. Select a local grid and **Create selected in Robot**. Native names are prefixed
   `GC / `. Select its Robot row to toggle it or show only that set. **Restore**
   restores visibility from before the first visibility action, even after several
   toggles. Save the RTD in Robot to persist the created grids.
6. Refresh Properties. Choose an existing material, or create an elastic concrete
   material, then create column/beam sections or wall/base thicknesses. Dimensions
   are in **metres**, E in **MPa**, unit weight in **kN/m³**, thermal expansion in **1/°C**.
   Custom materials do not define code-specific strength/reinforcement design data;
   configure those in Robot before design calculations.
7. Draw a base, wall or column with explicit coordinates and reference levels.
   Review coordinates in the preview before creation. Polygon points are entered
   one per line as `X; Y; Z`, in perimeter order. Warped or crossed panels are refused.
8. Run Checks. Double-click a finding to select its nodes/bars. Findings require
   engineering review; close nodes may be intentional. No repairs are automatic.
9. Save the RTD in Robot and save reference settings separately with **Ctrl+S**.

Panel creation sets geometry and thickness. It does not mesh the structure or
prove adjacent panels share compatible edges/nodes. Isolation creates an additional
view; returning to the original view does not close the isolated view.

API operations are additive but are not transactional. A failure can leave created
nodes, a contour, or a label. The action log lists completed creations; inspect
Robot before retrying. Node reuse uses **1e-8 m** positional equality; the proximity
check's default **0.001 m** tolerance is not a merge or snapping tolerance.

## Shortcuts (panel focused)

| Key | Action |
|---|---|
| Ctrl+L / Ctrl+G | Add level / grid |
| Ctrl+I / Ctrl+R | Isolate selected / return to original view |
| Ctrl+S / Ctrl+O | Save / open reference settings |
| F5 / F8 | Refresh Robot lists / run checks |

## Verification

From this folder, on any supported Python platform:

```text
python -m unittest discover -s tests -v
python -m compileall -q gcrobot run.py
```

Tests cover domain rules and a small fake-host contract for project identity,
visibility restoration and pre-write rejection. They do **not** simulate or prove
Robot's COM API. No root test suite or CI configuration is changed.

Before using the preview on a project, complete [the Windows smoke test](docs/windows-smoke-test.md).
See [design](docs/design.md), [plan](docs/plan.md) and [API references](docs/api-references.md).
