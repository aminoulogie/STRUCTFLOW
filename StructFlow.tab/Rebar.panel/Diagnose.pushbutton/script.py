# -*- coding: utf-8 -*-
"""Try every way of creating a bar in one beam and report which ones
Revit accepts. Changes nothing: everything is rolled back."""
__title__ = "Diagnose"

import traceback

from pyrevit import revit, script
from Autodesk.Revit.DB import Line, SubTransaction, Transaction, XYZ
from Autodesk.Revit.DB.Structure import (
    RebarBarType, RebarHookType, RebarHostData, RebarShape, RebarStyle,
    RebarTerminationOrientation,
)

import sf_beamrebar as br
import sf_common as common

doc, uidoc = revit.doc, revit.uidoc
out = script.get_output()
MM = br.MM

beams = common.pick_beams(uidoc)
if beams:
    beam = beams[0]
    print("Beam {}  valid rebar host: {}".format(out.linkify(beam.Id), RebarHostData.IsValidHost(beam)))
    fr = br.BeamFrame(beam)
    print("Extents (mm): length {:.0f}, width {:.0f}, depth {:.0f}".format(
        (fr.u1 - fr.u0) / MM, (fr.v1 - fr.v0) / MM, (fr.w1 - fr.w0) / MM))
    print("Shapes found: " + ", ".join(
        "{}={}".format(n, "yes" if br.by_name(doc, RebarShape, n) else "NO") for n in ("00", "11", "21", "51")))

    bt = br.by_name(doc, RebarBarType, "H16") or list(br.names_of(doc, RebarBarType))[0]
    if not hasattr(bt, "BarModelDiameter"):
        bt = br.by_name(doc, RebarBarType, bt)
    lt = br.by_name(doc, RebarBarType, "H10") or bt
    hook = br.by_name(doc, RebarHookType, "Stirrup/Tie - 135 deg.")

    c = 60 * MM
    vm = (fr.v0 + fr.v1) / 2.0
    ua, ub = fr.u0 + c, fr.u1 - c
    wt = fr.w1 - c
    leg = min(300 * MM, (fr.w1 - fr.w0) - 2 * c)
    p = lambda u, w: fr.pt(u, vm, w)
    va, vb, wa, wb = fr.v0 + c, fr.v1 - c, fr.w0 + c, fr.w1 - c
    loop = [fr.pt(ua, va, wb), fr.pt(ua, va, wa), fr.pt(ua, vb, wa), fr.pt(ua, vb, wb), fr.pt(ua, va, wb)]

    cases = [
        ("Straight bar", RebarStyle.Standard, bt, fr.Y,
         [Line.CreateBound(p(ua, wt), p(ub, wt))], "00", None, None),
        ("U bar shape 21 (legs down)", RebarStyle.Standard, bt, fr.Y,
         [Line.CreateBound(p(ua, wt - leg), p(ua, wt)), Line.CreateBound(p(ua, wt), p(ub, wt)),
          Line.CreateBound(p(ub, wt), p(ub, wt - leg))], "21", None,
         (p(ua, wt), fr.X * (ub - ua), XYZ.BasisZ * -leg)),
        ("Link shape 51, 135 hooks", RebarStyle.StirrupTie, lt, fr.X,
         [Line.CreateBound(loop[i], loop[i + 1]) for i in range(4)], "51", hook,
         (fr.pt(ua, va, wa), fr.Y * (vb - va), XYZ.BasisZ * (wb - wa))),
        ("Link, no hooks", RebarStyle.StirrupTie, lt, fr.X,
         [Line.CreateBound(loop[i], loop[i + 1]) for i in range(4)], None, None, None),
    ]

    t = Transaction(doc, "StructFlow diagnose")
    t.Start()
    try:
        for name, style, btype, normal, curves, shape_name, hk, box in cases:
            print("\n== " + name)
            shape = br.by_name(doc, RebarShape, shape_name) if shape_name else None
            for label, fn in br.creation_attempts(doc, beam, style, btype, normal, curves, shape, hk,
                                                  RebarTerminationOrientation.Left, box):
                st = SubTransaction(doc)
                st.Start()
                try:
                    r = fn()
                    print("  OK    {}  -> shape '{}'".format(
                        label, br.ename(doc.GetElement(r.GetShapeId())) if r else "?"))
                except Exception as ex:
                    print("  FAIL  {}  -> {}".format(label, br._err(ex)))
                    print("        " + traceback.format_exc().strip().splitlines()[-1])
                st.RollBack()
    finally:
        t.RollBack()
    print("\nNothing was changed in the model. Send this report to Claude.")
