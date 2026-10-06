# -*- coding: utf-8 -*-
"""Shared helpers for StructFlow buttons."""
import json
import os

from Autodesk.Revit.DB import BuiltInCategory, SubTransaction, Transaction
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

import sf_beamrebar as br

_LAST = os.path.join(os.environ["APPDATA"], "pyRevit", "StructFlow_beamrebar_last.json")


class _CategoryFilter(ISelectionFilter):
    def __init__(self, bic):
        self.bic = bic

    def AllowElement(self, el):
        return br.is_category(el, self.bic)

    def AllowReference(self, ref, pt):
        return False


def pick(uidoc, bic, prompt):
    """Current selection filtered to a category, else ask the user to pick."""
    doc = uidoc.Document
    els = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    els = [e for e in els if br.is_category(e, bic)]
    if els:
        return els
    try:
        refs = uidoc.Selection.PickObjects(ObjectType.Element, _CategoryFilter(bic), prompt)
    except OperationCanceledException:
        return []
    return [doc.GetElement(r) for r in refs]


def pick_beams(uidoc):
    return pick(uidoc, BuiltInCategory.OST_StructuralFraming,
                "Select beams, then click Finish")


def load_last():
    s = dict(br.DEFAULTS)
    try:
        with open(_LAST) as f:
            s.update(json.load(f))
    except Exception:
        pass
    return s


def save_last(s):
    try:
        with open(_LAST, "w") as f:
            json.dump(s, f, indent=1, sort_keys=True)
    except Exception:
        pass


def run(doc, view, jobs, title):
    """jobs: list of (beam, settings). Prints a report to the pyRevit output."""
    from pyrevit import script
    out = script.get_output()
    ok = made = 0
    t = Transaction(doc, title)
    t.Start()
    try:
        for beam, s in jobs:
            label = out.linkify(beam.Id)
            st = SubTransaction(doc)
            st.Start()
            try:
                n, deleted, warnings = br.build(doc, beam, s, view)
                st.Commit()
                ok += 1
                made += n
                msg = "{} : {} rebar sets created".format(label, n)
                if deleted:
                    msg += " ({} old sets replaced)".format(deleted)
                print(msg)
                for w in warnings:
                    print("    warning: " + w)
            except Exception as ex:
                st.RollBack()
                print("{} : SKIPPED - {}".format(label, ex))
        t.Commit()
    except Exception:
        t.RollBack()
        raise
    print("\nDone: {} of {} beams, {} rebar sets.".format(ok, len(jobs), made))
