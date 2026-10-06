# -*- coding: utf-8 -*-
"""Colour the beams in the active view by how their links behave:
green = links run non-stop, orange = links stop at junctions.
Uses the same rules as Beam Rebar, so you can check before placing bars."""
__title__ = "Link\nMap"

from pyrevit import forms, revit, script
from Autodesk.Revit.DB import (
    BuiltInCategory, Color, FilteredElementCollector, FillPatternElement,
    OverrideGraphicSettings, Transaction,
)

import sf_beamrebar as br

doc, view = revit.doc, revit.active_view
out = script.get_output()
MM = br.MM

GREEN, ORANGE, GREY = Color(0, 170, 0), Color(255, 140, 0), Color(160, 160, 160)


def solid_fill():
    for f in FilteredElementCollector(doc).OfClass(FillPatternElement):
        if f.GetFillPattern().IsSolidFill:
            return f.Id
    return None


def paint(el, color, fill):
    o = OverrideGraphicSettings()
    if color is not None:
        o.SetProjectionLineColor(color).SetCutLineColor(color)
        if fill is not None:
            o.SetSurfaceForegroundPatternId(fill).SetSurfaceForegroundPatternColor(color)
            o.SetCutForegroundPatternId(fill).SetCutForegroundPatternColor(color)
    view.SetElementOverrides(el.Id, o)


beams = list(FilteredElementCollector(doc, view.Id)
             .OfCategory(BuiltInCategory.OST_StructuralFraming)
             .WhereElementIsNotElementType())
PREVIEW = {
    "Preview: horizontal beams continuous": "horizontal",
    "Preview: vertical beams continuous": "vertical",
}
choice = forms.CommandSwitchWindow.show(["Colour beams (each beam's settings)"] + sorted(PREVIEW)
                                        + ["Clear colours"],
                                        message="{} beams in this view".format(len(beams)))
if choice:
    fill = solid_fill()
    t = Transaction(doc, "StructFlow Link Map")
    t.Start()
    if choice == "Clear colours":
        for b in beams:
            paint(b, None, None)
    else:
        out.print_md("**Link map** - green: links non-stop, orange: links stop, grey: not checked")
        for b in beams:
            label = out.linkify(b.Id)
            try:
                s = dict(br.load_beam_settings(b) or br.DEFAULTS)
                if choice in PREVIEW:
                    s["link_priority"], s["primary"] = PREVIEW[choice], False
                fr = br.BeamFrame(b)
                warnings = []
                bj, cj = br.junctions(doc, b, fr, warnings.append, s.get("link_priority", "auto"))
                stops = []
                if not s["primary"]:
                    stops.extend(bj)
                if s["stop_cols"]:
                    stops.extend(cj)
                stops = br.merged(stops)
                if stops:
                    paint(b, ORANGE, fill)
                    where = ", ".join("{:.0f}-{:.0f}".format((a - fr.u0) / MM, (c - fr.u0) / MM)
                                      for a, c in stops)
                    print("{} : links STOP at {} mm from start".format(label, where))
                else:
                    paint(b, GREEN, fill)
                    print("{} : links NON-STOP{}".format(
                        label, " (forced)" if s["primary"] and bj else ""))
                for w in warnings:
                    print("    warning: " + w)
            except Exception as ex:
                paint(b, GREY, fill)
                print("{} : not checked - {}".format(label, ex))
    t.Commit()
