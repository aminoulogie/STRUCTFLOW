# -*- coding: utf-8 -*-
"""One click: regenerate StructFlow auto-rebar in beams using the settings saved
on each beam. Run it after moving or resizing beams so covers and lap
lengths are exact again. Nothing selected = every beam in the model that
has StructFlow settings."""
__title__ = "Rebuild\nRebar"

from pyrevit import forms, revit
from Autodesk.Revit.DB import BuiltInCategory, FilteredElementCollector

import sf_beamrebar as br
import sf_common as common

doc, uidoc = revit.doc, revit.uidoc

sel = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
beams = [e for e in sel if br.is_category(e, BuiltInCategory.OST_StructuralFraming)]
picked = bool(beams)
if not picked:
    beams = list(FilteredElementCollector(doc)
                 .OfCategory(BuiltInCategory.OST_StructuralFraming)
                 .WhereElementIsNotElementType())
jobs = []
for b in beams:
    s = br.load_beam_settings(b)
    if s:
        jobs.append((b, s))

if not jobs:
    forms.alert("No beams with StructFlow rebar settings found. Use 'Beam Rebar' first.",
                title="StructFlow Rebuild")
elif picked or forms.alert("Nothing selected. Rebuild rebar in all {} StructFlow beams?".format(len(jobs)),
                        yes=True, no=True, title="StructFlow Rebuild"):
    common.run(doc, revit.active_view, jobs, "StructFlow Rebuild Rebar")
