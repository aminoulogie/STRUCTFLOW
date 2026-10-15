# Robot modeling tools Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Start the Robot modeling tool in its own repository folder and publish it.
**Architecture:** Pure Python geometry/domain logic, a lazy-loaded RobotOM adapter,
Tk tool window, and a native C# menu launcher.
**Tech Stack:** Python 3.10+, Tk, pythonnet 3, .NET Framework C# / RobotOM.
**Spec:** design.md

## Global Constraints
Only ROBOT_FLOW files. Metres for geometry. Exact decimals for reference levels.
No automatic geometry repairs or changes to existing labels. Windows validation remains explicit.

## Review Focus
- Decimal comma must not become a thousands separator.
- Level cycles and malformed settings must not replace a valid workspace.
- Coincident nodes must be reused without merging nearby intentional nodes.
- Switching Robot projects must invalidate access.
- Native launch and COM errors must be visible and not silently reported as success.

## Task 1: Domain and persistence
- [x] Write tests for levels, grids, polygon validation, diagnostics and save/load.
- [x] Run tests to demonstrate missing implementation.
- [x] Implement gcrobot/model.py and gcrobot/checks.py.
- [x] Run unittest discovery; expected all domain cases pass.

## Task 2: Robot operations and UI
- [x] Test the project guard and node match behavior.
- [x] Implement gcrobot/robot.py with named SDK types and enums.
- [x] Implement gcrobot/ui.py and run.py with menus, icons, tabs and shortcuts.
- [x] Verify Python compilation. UI startup could not run: no display/Xvfb.

## Task 3: Native launcher and delivery
- [x] Add plugin/RobotAddIn.cs, build/install scripts and usage/smoke-test docs.
- [x] Review full folder and run tests again.
- [ ] Publish folder through a new commit based on the current remote main tree,
      preserving every existing file; verify remote commit and file listing.
