# -*- coding: utf-8 -*-
"""Privacy Mode toggle (same button / shortcut hides and shows).

Revit will not run a shortcut whose button is invisible, so the
StructFlow tab is never hidden: it is emptied instead (no title, panels
hidden, this button with no text or icon). The pyRevit tab is hidden
completely. Restarting Revit also brings everything back."""
__title__ = "Privacy\nMode"

import clr
clr.AddReference("AdWindows")
from Autodesk.Windows import ComponentManager

MY_TAB, MY_PANEL = "StructFlow", "Tools"
OTHER_TABS = ("pyRevit",)
BUTTON_TEXT = "Privacy\nMode"


def find_tab(title_or_id):
    for t in ComponentManager.Ribbon.Tabs:
        if t.Title == title_or_id or t.Id == title_or_id:
            return t
    return None


def my_tab():
    # once emptied the title is blank, so fall back to the tab's id
    t = find_tab(MY_TAB)
    if t is None:
        for cand in ComponentManager.Ribbon.Tabs:
            if MY_TAB in (cand.Id or ""):
                return cand
    return t


def privacy_item(panel):
    for item in panel.Source.Items:
        if "Privacy" in (item.Id or "") or "Privacy" in (item.Text or ""):
            return item
    return None


def is_private(tab):
    return tab.Title != MY_TAB


def hide(tab):
    ribbon = ComponentManager.Ribbon
    for t in ribbon.Tabs:
        if t.Title in OTHER_TABS:
            if t.IsActive:
                ribbon.Tabs[0].IsActive = True
            t.IsVisible = False
    for p in tab.Panels:
        if p.Source.Title == MY_PANEL:
            p.Source.Title = ""
            item = privacy_item(p)
            if item is not None:
                item.Text = ""
                item.ShowText = False
                item.ShowImage = False
        else:
            p.IsVisible = False
    tab.Title = ""
    if tab.IsActive:
        ribbon.Tabs[0].IsActive = True


def show(tab):
    for t in ComponentManager.Ribbon.Tabs:
        if t.Title in OTHER_TABS:
            t.IsVisible = True
    for p in tab.Panels:
        p.IsVisible = True
        if p.Source.Title == "":
            p.Source.Title = MY_PANEL
            item = privacy_item(p)
            if item is not None:
                item.Text = BUTTON_TEXT
                item.ShowText = True
                item.ShowImage = True
    tab.Title = MY_TAB


tab = my_tab()
if tab is not None:
    if is_private(tab):
        show(tab)
    else:
        hide(tab)
