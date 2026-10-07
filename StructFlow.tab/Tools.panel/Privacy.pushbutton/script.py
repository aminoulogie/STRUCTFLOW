# -*- coding: utf-8 -*-
"""Hide the pyRevit and StructFlow ribbon tabs (e.g. before screen
sharing). They come back by themselves after the time you pick, or when
Revit restarts. Keyboard shortcuts can't reach a hidden tab, so a timer
is the only reliable way back."""
__title__ = "Privacy\nMode"
__persistentengine__ = True  # keep the timer's callback alive after the script ends

import clr
clr.AddReference("AdWindows")
clr.AddReference("WindowsBase")
from Autodesk.Windows import ComponentManager
from System import AppDomain, TimeSpan
from System.Windows.Threading import DispatcherTimer

from pyrevit import forms

TABS = ("pyRevit", "StructFlow")
CHOICES = {"Hide for 15 minutes": 15, "Hide for 30 minutes": 30,
           "Hide for 1 hour": 60, "Hide for 2 hours": 120}
KEY = "StructFlow.PrivacyTimer"


def set_visible(visible):
    ribbon = ComponentManager.Ribbon
    targets = [t for t in ribbon.Tabs if t.Title in TABS]
    if not visible and ribbon.ActiveTab in targets:
        for t in ribbon.Tabs:
            if t.IsVisible and t not in targets:
                t.IsActive = True
                break
    for t in targets:
        t.IsVisible = visible


choice = forms.CommandSwitchWindow.show(
    sorted(CHOICES, key=lambda k: CHOICES[k]),
    message="The tabs come back by themselves afterwards (or when Revit restarts).")
if choice:
    old = AppDomain.CurrentDomain.GetData(KEY)
    if old is not None:
        old.Stop()
    timer = DispatcherTimer()
    timer.Interval = TimeSpan.FromMinutes(CHOICES[choice])

    def tick(sender, args):
        sender.Stop()
        set_visible(True)

    timer.Tick += tick
    AppDomain.CurrentDomain.SetData(KEY, timer)  # keep it referenced
    set_visible(False)
    timer.Start()
