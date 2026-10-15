# Windows / Robot 2027 acceptance checklist

Not executed in the Linux authoring environment. Record Robot build, Python version,
SDK path and results here when testing. Use a disposable copy of a 3D shell project.

- [ ] `python run.py` opens all five tabs; icon toolbar and dialog layouts fit at 100% and 150% DPI.
- [ ] BuildAndInstall compiles against the installed 2027 SDK with no errors.
- [ ] Installation creates GCStructFlow commands in Robot; each command opens its tab.
- [ ] Connect reaches the intended project. Close/change project: operations are refused.
- [ ] Starting from a menu with multiple Robot processes cannot modify the wrong project.
- [ ] Decimal `-1,37` stores and reloads as -1.37 m, without coordinate rounding.
- [ ] Relative levels evaluate correctly; cyclic edits fail without changing levels.
- [ ] Sample grid axes are at the specified X/Y/Z coordinates, including the first axis.
- [ ] Rotated grid with origin (10,20), 90°: local (2.37,4.12) is world (5.88,22.37).
- [ ] Reopening the RTD retains axes; toggles affect only the chosen grid; restore restores the prior combination.
- [ ] E=30000 MPa, unit weight=25 kN/m³ produce E=30 GPa and unit weight=25 kN/m³ in Robot.
- [ ] Rectangular section dimensions/material are correct; wall/base thickness is correct.
- [ ] Existing property/grid names are refused without changing existing definitions.
- [ ] Column top/bottom Z coordinates match selected levels. Shared exact endpoints reuse nodes.
- [ ] Beam creation rejects duplicate bars and zero-length members.
- [ ] Base/wall/polygon become actual panels with assigned thickness, not bare contours.
- [ ] Sloping planar panel succeeds; nonplanar or crossed polygon fails before writes.
- [ ] Isolated view displays only selected objects; returning restores original view activation.
- [ ] Checks locate intentional duplicate/near nodes and bars; selecting a finding selects correct IDs.
- [ ] Invalid file loads preserve the current reference settings. Close prompts for unsaved settings.
- [ ] Uninstall removes only the GCStructFlow COM class and menu keys.

If an API call fails, capture the exact dialog and Python console traceback. Do not
repeatedly retry geometry creation: inspect the action log and Robot model first.
