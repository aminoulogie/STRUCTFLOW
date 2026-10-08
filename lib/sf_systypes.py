# -*- coding: utf-8 -*-
"""System family types in the model (dimension styles, text, filled regions,
arrowheads, grids, levels, view tags, viewports, walls, floors, roofs,
ceilings, view types, line styles, line / fill patterns) with how many
placed elements use each, and safe actions: rename, duplicate, delete, and
'merge' = move every user of one type onto another, then delete it."""
from System.Collections.Generic import HashSet, List
from Autodesk.Revit.DB import (
    BuiltInCategory, CeilingType, CurveElement, DimensionType, ElementId,
    ElementType, FilledRegionType, FillPatternElement, FilteredElementCollector,
    FloorType, GraphicsStyleType, LinePatternElement, RoofType, SubTransaction,
    TextNoteType, Transaction, ViewFamilyType, WallType,
)

import sf_beamrebar as br


def _key(eid):
    return eid.Value if hasattr(eid, "Value") else eid.IntegerValue


def _uses(doc):
    uses = {}
    for el in FilteredElementCollector(doc).WhereElementIsNotElementType():
        try:
            tid = el.GetTypeId()
        except Exception:
            continue
        if tid is not None and tid != ElementId.InvalidElementId:
            uses[_key(tid)] = uses.get(_key(tid), 0) + 1
    return uses


def _by_family(doc, family_name):
    out = []
    for t in FilteredElementCollector(doc).OfClass(ElementType):
        try:
            if t.FamilyName == family_name:
                out.append(t)
        except Exception:
            pass
    return out


def groups(doc):
    """{group name: [item]} item = {el, name, uses (int or None), unused (bool), kind}"""
    unused = set(_key(i) for i in doc.GetAllUnusedElements(HashSet[ElementId]()))
    uses = _uses(doc)
    out = {}

    def add(group, el, kind, n=None):
        n = uses.get(_key(el.Id), 0) if n is None else n
        out.setdefault(group, []).append({"el": el, "name": br.ename(el) or el.Name, "uses": n,
                                          "unused": _key(el.Id) in unused or n == 0, "kind": kind})

    for d in FilteredElementCollector(doc).OfClass(DimensionType):
        try:
            style = str(d.StyleType)
        except Exception:
            style = "Other"
        if br.ename(d):
            add("Dimension styles - %s" % style, d, "dimension")
    for t in FilteredElementCollector(doc).OfClass(TextNoteType):
        add("Text types", t, "text")
    for t in FilteredElementCollector(doc).OfClass(FilledRegionType):
        add("Filled region types", t, "type")
    for t in _by_family(doc, "Arrowhead"):
        add("Arrowheads", t, "type")
    from Autodesk.Revit.DB import GridType, LevelType
    for t in FilteredElementCollector(doc).OfClass(GridType):
        add("Grid types", t, "type")
    for t in FilteredElementCollector(doc).OfClass(LevelType):
        add("Level types", t, "type")
    for fam, label in (("Section Tag", "Section tags"), ("Callout Tag", "Callout tags"),
                       ("Elevation Tag", "Elevation tags"), ("Viewport", "Viewport types")):
        for t in _by_family(doc, fam):
            add(label, t, "type")
    for cls, label in ((WallType, "Wall types"), (FloorType, "Floor types"), (RoofType, "Roof types"),
                       (CeilingType, "Ceiling types")):
        for t in FilteredElementCollector(doc).OfClass(cls):
            add(label, t, "type")
    vt_uses = {}
    from Autodesk.Revit.DB import View
    for v in FilteredElementCollector(doc).OfClass(View):
        vt_uses[_key(v.GetTypeId())] = vt_uses.get(_key(v.GetTypeId()), 0) + 1
    for t in FilteredElementCollector(doc).OfClass(ViewFamilyType):
        add("View types", t, "viewtype", vt_uses.get(_key(t.Id), 0))

    # line styles: subcategories of Lines, counted by the curves drawn with them
    curve_uses = {}
    for c in FilteredElementCollector(doc).OfClass(CurveElement):
        try:
            curve_uses[_key(c.LineStyle.Id)] = curve_uses.get(_key(c.LineStyle.Id), 0) + 1
        except Exception:
            pass
    lines = doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines)
    for sub in lines.SubCategories:
        gs = sub.GetGraphicsStyle(GraphicsStyleType.Projection)
        if gs is None or sub.Name.startswith("<"):
            continue  # Revit's own <Hidden> / <Overhead>... cannot be deleted
        n = curve_uses.get(_key(gs.Id), 0)
        out.setdefault("Line styles", []).append({"el": gs, "name": sub.Name, "uses": n,
                                                  "unused": n == 0, "kind": "linestyle", "sub": sub})
    for p in FilteredElementCollector(doc).OfClass(LinePatternElement):
        out.setdefault("Line patterns", []).append({"el": p, "name": p.Name, "uses": None,
                                                    "unused": _key(p.Id) in unused, "kind": "pattern"})
    for p in FilteredElementCollector(doc).OfClass(FillPatternElement):
        out.setdefault("Fill patterns", []).append({"el": p, "name": p.Name, "uses": None,
                                                    "unused": _key(p.Id) in unused, "kind": "pattern"})
    for items in out.values():
        items.sort(key=lambda i: i["name"].lower())
    return out


def users(doc, type_el):
    return [el for el in FilteredElementCollector(doc).WhereElementIsNotElementType()
            if _safe_type(el) == type_el.Id]


def _safe_type(el):
    try:
        return el.GetTypeId()
    except Exception:
        return None


def delete(doc, items, log):
    ok = failed = 0
    t = Transaction(doc, "StructFlow delete system types")
    t.Start()
    for it in items:
        st = SubTransaction(doc)
        st.Start()
        try:
            target = it.get("sub").Id if it.get("sub") is not None else it["el"].Id
            doc.Delete(target)
            st.Commit()
            ok += 1
            log("deleted  %s" % it["name"])
        except Exception as ex:
            st.RollBack()
            failed += 1
            log("FAILED   %s: %s" % (it["name"], br._err(ex)))
    t.Commit()
    return ok, failed


def merge(doc, items, into, log):
    """Move every element using each item's type onto 'into', then delete the item."""
    ok = failed = 0
    t = Transaction(doc, "StructFlow merge types")
    t.Start()
    for it in items:
        if it["el"].Id == into.Id:
            continue
        st = SubTransaction(doc)
        st.Start()
        try:
            moved = 0
            for el in users(doc, it["el"]):
                el.ChangeTypeId(into.Id)
                moved += 1
            doc.Delete(it["el"].Id)
            st.Commit()
            ok += 1
            log("merged   %s -> %s  (%d elements moved)" % (it["name"], br.ename(into), moved))
        except Exception as ex:
            st.RollBack()
            failed += 1
            log("FAILED   %s: %s" % (it["name"], br._err(ex)))
    t.Commit()
    return ok, failed


def rename(doc, item, new_name):
    t = Transaction(doc, "StructFlow rename type")
    t.Start()
    try:
        if item.get("sub") is not None:
            raise ValueError("line styles cannot be renamed through the API - rename in Manage > Line Styles")
        item["el"].Name = new_name
        t.Commit()
    except Exception:
        t.RollBack()
        raise


def duplicate(doc, item, new_name):
    t = Transaction(doc, "StructFlow duplicate type")
    t.Start()
    try:
        new = item["el"].Duplicate(new_name)
        t.Commit()
        return new
    except Exception:
        t.RollBack()
        raise
