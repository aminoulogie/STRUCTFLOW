# Verification record — 2026-10-15

- Python 3.12: `python -m unittest discover -s tests -v` — 18 tests passed.
- `python -m compileall -q gcrobot run.py` — exit 0.
- Independent read-only code review identified endpoint reuse bypassing duplicate/zero-length validation and stale findings after reconnect.
- Three regression tests reproduced those defects, then passed after fixes; full suite passed.
- Tk runtime could not start: no display or Xvfb in the authoring environment.
- C# compilation, PowerShell installer, COM registration and Robot 2027 runtime were not executed (Linux; no Robot SDK/.NET compiler).
- No existing repository files are part of this change. All delivery files are beneath ROBOT_FLOW/.

The test suite covers geometry and limited fake-host contracts. It does not establish host compatibility or structural correctness. Complete windows-smoke-test.md on a disposable model before using the preview for project work.
