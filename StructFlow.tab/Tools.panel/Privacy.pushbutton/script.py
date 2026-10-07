# -*- coding: utf-8 -*-
"""Privacy Mode toggle: hides the pyRevit and StructFlow ribbon tabs
(e.g. before screen sharing); run it again (same button / shortcut) to
show them. As a safety net they also come back by themselves after the
time you pick, or when Revit restarts."""
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


def targets():
    return [t for t in ComponentManager.Ribbon.Tabs if t.Title in TABS]


def set_visible(visible):
    ribbon = ComponentManager.Ribbon
    tabs = targets()
    if not visible and ribbon.ActiveTab in tabs:
        for t in ribbon.Tabs:
            if t.IsVisible and t not in tabs:
                t.IsActive = True
                break
    for t in tabs:
        t.IsVisible = visible


def stop_timer():
    old = AppDomain.CurrentDomain.GetData(KEY)
    if old is not None:
        old.Stop()


if any(not t.IsVisible for t in targets()):
    # tabs are hidden: this press brings them back
    stop_timer()
    set_visible(True)
else:
    choice = forms.CommandSwitchWindow.show(
        sorted(CHOICES, key=lambda k: CHOICES[k]),
        message="Press the same shortcut again to show the tabs (they also come back by themselves).")
    if choice:
        stop_timer()
        timer = DispatcherTimer()
        timer.Interval = TimeSpan.FromMinutes(CHOICES[choice])

        def tick(sender, args):
            sender.Stop()
            set_visible(True)

        timer.Tick += tick
        AppDomain.CurrentDomain.SetData(KEY, timer)  # keep it referenced
        set_visible(False)
        timer.Start()
