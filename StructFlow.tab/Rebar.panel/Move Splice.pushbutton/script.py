# -*- coding: utf-8 -*-
"""Move a lap: pick a StructFlow bar near the splice, then click the new
splice centre (or type it). The bars are rebuilt with the lap kept at
exactly the beam's lap factor x d. The position is stored on the beam, so
'Rebuild' keeps it."""
__title__ = "Move\nSplice"

from pyrevit import forms, revit
from Autodesk.Revit.DB import Plane, SketchPlane, Transaction
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

import sf_beamrebar as br
import sf_common as common

doc, uidoc = revit.doc, revit.uidoc
view = revit.active_view
MM = br.MM


class LapBarFilter(ISelectionFilter):
    def AllowElement(self, el):
        return br.rebar_layer(el) in ("top", "bot") if hasattr(el, "GetHostId") else False

    def AllowReference(self, ref, pt):
        return False


def ensure_work_plane():
    if view.SketchPlane is not None:
        return
    t = Transaction(doc, "StructFlow work plane")
    t.Start()
    view.SketchPlane = SketchPlane.Create(doc, Plane.CreateByNormalAndOrigin(view.ViewDirection, view.Origin))
    t.Commit()


try:
    ref = uidoc.Selection.PickObject(ObjectType.Element, LapBarFilter(),
                                     "Pick a top or bottom bar next to the splice to move")
except OperationCanceledException:
    ref = None

if ref:
    bar = doc.GetElement(ref)
    layer = br.rebar_layer(bar)
    beam = doc.GetElement(bar.GetHostId())
    s = br.load_beam_settings(beam)
    fr = br.BeamFrame(beam)
    centres = list(s.get(layer + "_splices_at") or [])
    if not centres:
        forms.alert("The {} bars of this beam have no splice.".format("top" if layer == "top" else "bottom"),
                    title="StructFlow Move Splice")
    else:
        gp = ref.GlobalPoint
        if gp is None:
            bb = bar.get_BoundingBox(None)
            gp = (bb.Min + bb.Max) / 2.0
        picked = (fr.u(gp) - fr.u0) / MM
        i = min(range(len(centres)), key=lambda k: abs(centres[k] - picked))
        how = forms.CommandSwitchWindow.show(
            ["Click the new position", "Type distance from beam start"],
            message="Splice now at {:.0f} mm from the beam start. Lap stays {:g} x d.".format(
                centres[i], s["lap_factor"]))
        new = None
        if how == "Click the new position":
            ensure_work_plane()
            try:
                pt = uidoc.Selection.PickPoint("Click the new splice centre")
                new = (fr.u(pt) - fr.u0) / MM
            except OperationCanceledException:
                pass
        elif how:
            txt = forms.ask_for_string(default="{:.0f}".format(centres[i]),
                                       prompt="New splice centre, mm from the beam start face:",
                                       title="StructFlow Move Splice")
            try:
                new = float(txt) if txt else None
            except ValueError:
                forms.alert("Not a number.")
        if new is not None:
            centres[i] = round(new, 1)
            s[layer + "_splices"] = sorted(centres)
            common.run(doc, view, [(beam, s)], "StructFlow Move Splice")
