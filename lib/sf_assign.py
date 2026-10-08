# -*- coding: utf-8 -*-
"""EPL symbol assignment: which symbol family each grid / level / section /
callout / elevation / viewport type and each default tag uses, and switching
the ticked ones to the EPL families named in epl_standards.jsonc. Plus a test
sheet that shows every symbol."""
import math

from Autodesk.Revit.DB import (
    BoundingBoxXYZ, BuiltInCategory, BuiltInParameter, ElementId, ElementType,
    FamilySymbol, FilteredElementCollector, Grid, IndependentTag, Level,
    Line, Reference, SubTransaction, TagMode, TagOrientation, Transaction,
    Transform, ViewFamily, ViewFamilyType, ViewPlan, ViewSection, ViewSheet,
    Viewport, XYZ, ElevationMarker,
)

import sf_beamrebar as br

TAGS = [
    (BuiltInCategory.OST_RebarTags, "Rebar", "EPL_TAG_Rebar"),
    (BuiltInCategory.OST_StructuralColumnTags, "Structural columns", "EPL_TAG_StrColumn"),
    (BuiltInCategory.OST_StructuralFramingTags, "Structural framing", "EPL_TAG_StrFraming"),
    (BuiltInCategory.OST_StructuralFoundationTags, "Structural foundations", "EPL_TAG_StrFoundation"),
]


def find_symbol(doc, family_name):
    for s in FilteredElementCollector(doc).OfClass(FamilySymbol):
        if s.FamilyName == family_name:
            return s
    return None


def _name(doc, eid):
    if eid is None or eid == ElementId.InvalidElementId:
        return "(none)"
    el = doc.GetElement(eid)
    if el is None:
        return "(none)"
    fam = getattr(el, "FamilyName", "")
    return "%s : %s" % (fam, br.ename(el)) if fam else br.ename(el)


def _types(doc, family_name):
    out = []
    for t in FilteredElementCollector(doc).OfClass(ElementType):
        try:
            if t.FamilyName == family_name:
                out.append(t)
        except Exception:
            pass
    return out


def rows(doc, cfg):
    """[{kind, type_name, current, target, apply(fn), state}] state: 'ok' / 'change' / 'missing'."""
    sym = cfg["symbols"]
    sec = cfg.get("sections", {})
    out = []

    def param_row(kind, el, bip, family):
        p = el.get_Parameter(bip)
        if p is None:
            return
        target = find_symbol(doc, family)
        cur = p.AsElementId()
        state = "missing" if target is None else ("ok" if cur == target.Id else "change")

        def do(p=p, target=target):
            p.Set(target.Id)
        out.append({"kind": kind, "type_name": br.ename(el), "current": _name(doc, cur),
                    "target": family, "apply": do, "state": state})

    from Autodesk.Revit.DB import GridType, LevelType
    for t in FilteredElementCollector(doc).OfClass(GridType):
        param_row("Grid type", t, BuiltInParameter.GRID_HEAD_TAG, sym["grid_head"])
    for t in FilteredElementCollector(doc).OfClass(LevelType):
        param_row("Level type", t, BuiltInParameter.LEVEL_HEAD_TAG, sym["level_head"])
    for t in _types(doc, "Section Tag"):
        param_row("Section tag (head)", t, BuiltInParameter.SECTION_ATTR_HEAD_TAG, sym["section_head"])
        param_row("Section tag (tail)", t, BuiltInParameter.SECTION_ATTR_TAIL_TAG,
                  sec.get("tail_family", "EPL_ANN_SectionTail_Filled"))
    for t in _types(doc, "Callout Tag"):
        param_row("Callout tag", t, BuiltInParameter.CALLOUT_ATTR_HEAD_TAG, sym["callout_head"])
    for t in _types(doc, "Viewport"):
        param_row("Viewport type (view title)", t, BuiltInParameter.VIEWPORT_ATTR_LABEL_TAG, sym["view_title"])
    for t in _types(doc, "Elevation Tag"):
        p = t.LookupParameter("Elevation Mark")
        if p is not None:
            target = find_symbol(doc, sym["elevation_body"])
            cur = p.AsElementId()
            state = "missing" if target is None else ("ok" if cur == target.Id else "change")

            def do(p=p, target=target):
                p.Set(target.Id)
            out.append({"kind": "Elevation tag", "type_name": br.ename(t), "current": _name(doc, cur),
                        "target": sym["elevation_body"], "apply": do, "state": state})
    for bic, label, family in TAGS:
        cat = doc.Settings.Categories.get_Item(bic)
        cur = doc.GetDefaultFamilyTypeId(cat.Id)
        target = find_symbol(doc, family)
        state = "missing" if target is None else ("ok" if cur == target.Id else "change")

        def do(cat=cat, target=target):
            doc.SetDefaultFamilyTypeId(cat.Id, target.Id)
        out.append({"kind": "Default tag", "type_name": label, "current": _name(doc, cur),
                    "target": family, "apply": do, "state": state})
    return out


def assign(doc, chosen, log):
    ok = failed = 0
    t = Transaction(doc, "StructFlow symbol assign")
    t.Start()
    for r in chosen:
        st = SubTransaction(doc)
        st.Start()
        try:
            r["apply"]()
            st.Commit()
            ok += 1
            log("set      %s '%s': %s  ->  %s" % (r["kind"], r["type_name"], r["current"], r["target"]))
        except Exception as ex:
            st.RollBack()
            failed += 1
            log("FAILED   %s '%s': %s" % (r["kind"], r["type_name"], br._err(ex)))
    t.Commit()
    return ok, failed


# ------------------------------------------------------------- test sheet
def _vft(doc, family):
    for v in FilteredElementCollector(doc).OfClass(ViewFamilyType):
        if v.ViewFamily == family:
            return v
    return None


def test_sheet(doc, title_block_name, log):
    """A plan with a section, a callout, an elevation mark and a few tags,
    placed on a test sheet with its view title. Returns the sheet."""
    import sf_views as sv
    levels = sorted(FilteredElementCollector(doc).OfClass(Level), key=lambda l: l.Elevation)
    if not levels:
        raise ValueError("the model has no level")
    vft = _vft(doc, ViewFamily.StructuralPlan) or _vft(doc, ViewFamily.FloorPlan)
    t = Transaction(doc, "StructFlow symbol test sheet")
    t.Start()
    plan = ViewPlan.Create(doc, vft.Id, levels[0].Id)
    sv._set_name(plan, "EPL TEST - Symbols")
    plan.Scale = 100

    # middle of the grids (or the origin)
    pts = []
    for g in FilteredElementCollector(doc).OfClass(Grid):
        c = g.Curve
        pts += [c.GetEndPoint(0), c.GetEndPoint(1)]
    if pts:
        cx = (min(p.X for p in pts) + max(p.X for p in pts)) / 2.0
        cy = (min(p.Y for p in pts) + max(p.Y for p in pts)) / 2.0
        span = max(max(p.X for p in pts) - min(p.X for p in pts), 10.0)
    else:
        cx = cy = 0.0
        span = 30.0
    z = levels[0].Elevation

    made = [plan]
    try:  # section across the middle
        sec_vft = _vft(doc, ViewFamily.Section)
        tr = Transform.Identity
        tr.Origin = XYZ(cx, cy, z)
        tr.BasisX, tr.BasisY, tr.BasisZ = XYZ.BasisX, XYZ.BasisZ, -XYZ.BasisY
        box = BoundingBoxXYZ()
        box.Transform = tr
        box.Min, box.Max = XYZ(-span / 3, -3, -5), XYZ(span / 3, 12, 0)
        s = ViewSection.CreateSection(doc, sec_vft.Id, box)
        sv._set_name(s, "EPL TEST - Section")
        made.append(s)
        log("section placed")
    except Exception as ex:
        log("section not placed: %s" % br._err(ex))
    try:  # callout in a corner
        c = ViewSection.CreateCallout(doc, plan.Id, vft.Id, XYZ(cx + span / 8, cy + span / 8, z),
                                      XYZ(cx + span / 4, cy + span / 4, z))
        sv._set_name(c, "EPL TEST - Callout")
        log("callout placed")
    except Exception as ex:
        log("callout not placed: %s" % br._err(ex))
    try:  # elevation mark
        el_vft = _vft(doc, ViewFamily.Elevation)
        m = ElevationMarker.CreateElevationMarker(doc, el_vft.Id, XYZ(cx - span / 4, cy - span / 6, z), 100)
        e = m.CreateElevation(doc, plan.Id, 0)
        sv._set_name(e, "EPL TEST - Elevation")
        log("elevation mark placed")
    except Exception as ex:
        log("elevation mark not placed: %s" % br._err(ex))
    doc.Regenerate()
    n = 0
    for bic in (BuiltInCategory.OST_StructuralColumns, BuiltInCategory.OST_StructuralFraming,
                BuiltInCategory.OST_StructuralFoundation):
        for el in list(FilteredElementCollector(doc, plan.Id).OfCategory(bic).WhereElementIsNotElementType())[:3]:
            try:
                bb = el.get_BoundingBox(None)
                pt = XYZ((bb.Min.X + bb.Max.X) / 2, (bb.Min.Y + bb.Max.Y) / 2, z)
                IndependentTag.Create(doc, plan.Id, Reference(el), False, TagMode.TM_ADDBY_CATEGORY,
                                      TagOrientation.Horizontal, pt)
                n += 1
            except Exception:
                pass
    log("%d tags placed" % n)

    import sf_sheets as ss
    tbs = ss.title_blocks(doc)
    tb = tbs.get(title_block_name) or (list(tbs.values())[0] if tbs else None)
    if tb is None:
        raise ValueError("no title block loaded")
    if not tb.IsActive:
        tb.Activate()
    sheet = ViewSheet.Create(doc, tb.Id)
    sheet.SheetNumber = "EPL-TEST-%d" % len(list(FilteredElementCollector(doc).OfClass(ViewSheet)))
    sheet.Name = "EPL TEST - Symbols"
    doc.Regenerate()
    bb = sheet.get_BoundingBox(sheet)
    tbe = list(FilteredElementCollector(doc, sheet.Id).OfCategory(BuiltInCategory.OST_TitleBlocks))
    if tbe:
        bb = tbe[0].get_BoundingBox(sheet)
    w = bb.Max.X - bb.Min.X
    mid = XYZ(bb.Min.X + w * 0.35, (bb.Min.Y + bb.Max.Y) / 2, 0)
    Viewport.Create(doc, sheet.Id, plan.Id, mid)
    if len(made) > 1 and Viewport.CanAddViewToSheet(doc, sheet.Id, made[1].Id):
        Viewport.Create(doc, sheet.Id, made[1].Id, XYZ(bb.Min.X + w * 0.75, mid.Y, 0))
    t.Commit()
    log("test sheet %s created" % sheet.SheetNumber)
    return sheet
