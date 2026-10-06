# -*- coding: utf-8 -*-
"""Hide / show the pyRevit and StructFlow ribbon tabs (e.g. before
screen sharing). Give this command a keyboard shortcut so you can bring
the tabs back while they are hidden:
View > User Interface > Keyboard Shortcuts, search 'Privacy'."""
__title__ = "Privacy\nMode"

import clr
clr.AddReference("AdWindows")
from Autodesk.Windows import ComponentManager

TABS = ("pyRevit", "StructFlow")

ribbon = ComponentManager.Ribbon
targets = [t for t in ribbon.Tabs if t.Title in TABS]
hide = any(t.IsVisible for t in targets)

if hide and ribbon.ActiveTab in targets:
    for t in ribbon.Tabs:
        if t.IsVisible and t not in targets:
            t.IsActive = True
            break
for t in targets:
    t.IsVisible = not hide
