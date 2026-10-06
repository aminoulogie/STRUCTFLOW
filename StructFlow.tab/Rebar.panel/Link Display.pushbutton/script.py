# -*- coding: utf-8 -*-
"""Set which bars of the selected rebar sets show in the active view:
all, first / middle / last, or 3 in the middle."""
__title__ = "Link\nDisplay"

from pyrevit import forms, revit
from Autodesk.Revit.DB import BuiltInCategory, Transaction

import sf_beamrebar as br
import sf_common as common

doc, uidoc = revit.doc, revit.uidoc
view = revit.active_view

rebars = common.pick(uidoc, BuiltInCategory.OST_Rebar, "Select rebar sets, then click Finish")
if rebars:
    labels = [label for _, label in br.DISPLAY_MODES]
    choice = forms.CommandSwitchWindow.show(labels, message="Show which bars in this view?")
    if choice:
        mode = br.DISPLAY_MODES[labels.index(choice)][0]
        t = Transaction(doc, "StructFlow Link Display")
        t.Start()
        skipped = 0
        for r in rebars:
            if r.CanApplyPresentationMode(view):
                br.apply_display(r, view, mode)
            else:
                skipped += 1
        t.Commit()
        if skipped:
            forms.alert("{} rebar set(s) can't change display in this view type.".format(skipped))
