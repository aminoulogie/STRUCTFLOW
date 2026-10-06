# -*- coding: utf-8 -*-
"""StructFlow beam sheets: place each beam's long section followed by its
cross sections on one row, rows top to bottom, as many as fit on each
sheet of the chosen title block. New sheets are added as needed."""
import json
import os

from System.Collections.Generic import List
from Autodesk.Revit.DB import (
    BuiltInCategory, ElementId, ElementType, FamilySymbol,
    FilteredElementCollector, ViewPlacementOnSheetStatus, ViewSheet, Viewport, XYZ,
)

import sf_beamrebar as br
import sf_views as sv

MM = br.MM
SETTINGS = os.path.join(os.environ["APPDATA"], "pyRevit", "StructFlow_sheet_settings.json")

DEFAULTS = {
    "title_block": "", "vp_type": "",
    "number_prefix": "S-", "number_start": 301, "sheet_name": "BEAM DETAILS - {n}",
    "m_left": 30.0, "m_right": 30.0, "m_top": 25.0, "m_bottom": 25.0,
    "gap_x": 25.0, "gap_y": 30.0, "align": "Centre",
}


def load_settings():
    s = dict(DEFAULTS)
    try:
        with open(SETTINGS) as f:
            s.update(json.load(f))
    except Exception:
        pass
    return s


def save_settings(s):
    try:
        with open(SETTINGS, "w") as f:
            json.dump(s, f, indent=1, sort_keys=True)
    except Exception:
        pass


def title_blocks(doc):
    return dict(("%s : %s" % (t.FamilyName, br.ename(t)), t)
                for t in FilteredElementCollector(doc).OfClass(FamilySymbol)
                .OfCategory(BuiltInCategory.OST_TitleBlocks))


def viewport_types(doc):
    out = {}
    for t in FilteredElementCollector(doc).OfClass(ElementType):
        try:
            if t.FamilyName == "Viewport":
                out[br.ename(t)] = t
        except Exception:
            pass
    return out


def beam_groups(doc, beams):
    """[(letter, beam, [long views], [cross views in order along the beam])]"""
    by_uid = sv._sf_views(doc)
    groups = []
    for b in beams:
        letter, ids = by_uid.get(b.UniqueId, ["", []])
        if not ids:
            continue
        fr = br.BeamFrame(b)
        longs, crosses = [], []
        for vid in ids:
            v = doc.GetElement(vid)
            if abs(v.RightDirection.DotProduct(fr.X)) > 0.9:
                longs.append(v)
            else:
                crosses.append((fr.u(v.Origin), v))
        crosses = [v for _, v in sorted(crosses, key=lambda c: c[0])]
        groups.append((letter, b, longs, crosses))
    groups.sort(key=lambda g: (len(g[0]), g[0]))
    return groups


def _next_number(doc, prefix, n):
    taken = set(sh.SheetNumber for sh in FilteredElementCollector(doc).OfClass(ViewSheet))
    while "%s%d" % (prefix, n) in taken:
        n += 1
    return n


def _new_sheet(doc, tb, s, index, counter):
    sheet = ViewSheet.Create(doc, tb.Id)
    counter[0] = _next_number(doc, s["number_prefix"], counter[0])
    sheet.SheetNumber = "%s%d" % (s["number_prefix"], counter[0])
    counter[0] += 1
    try:
        sheet.Name = s["sheet_name"].replace("{n}", str(index))
    except Exception:
        pass
    return sheet


def _area(doc, sheet, s):
    """Usable drawing area (sheet coordinates) inside the title block."""
    tbs = list(FilteredElementCollector(doc, sheet.Id).OfCategory(BuiltInCategory.OST_TitleBlocks))
    bb = tbs[0].get_BoundingBox(sheet) if tbs else None
    if bb is None:
        raise ValueError("the title block has no size on the sheet")
    return (bb.Min.X + s["m_left"] * MM, bb.Max.X - s["m_right"] * MM,
            bb.Max.Y - s["m_top"] * MM, bb.Min.Y + s["m_bottom"] * MM)


def _measure(doc, sheet, views):
    """Paper size (w, h) of each view, measured on a throw-away viewport."""
    sizes = {}
    for v in views:
        vp = Viewport.Create(doc, sheet.Id, v.Id, XYZ(0, 0, 0))
        o = vp.GetBoxOutline()
        sizes[v.Id] = (o.MaximumPoint.X - o.MinimumPoint.X, o.MaximumPoint.Y - o.MinimumPoint.Y)
        doc.Delete(vp.Id)
    return sizes


def layout(doc, beams, s, warn):
    """Create sheets and viewports. Returns the list of sheets created."""
    tb = title_blocks(doc).get(s["title_block"])
    if tb is None:
        raise ValueError("pick a title block")
    if not tb.IsActive:
        tb.Activate()
        doc.Regenerate()
    vpt = viewport_types(doc).get(s["vp_type"])

    groups = beam_groups(doc, beams)
    todo = []
    for letter, beam, longs, crosses in groups:
        row = []
        for v in longs + crosses:
            if v.GetPlacementOnSheetStatus() != ViewPlacementOnSheetStatus.NotPlaced:
                warn("'%s' is already on a sheet, skipped" % v.Name)
            else:
                row.append(v)
        if row:
            todo.append((letter, row))
    if not todo:
        raise ValueError("no unplaced StructFlow views for these beams (run Beam Views first)")

    counter = [int(s["number_start"])]
    sheets = [_new_sheet(doc, tb, s, 1, counter)]
    doc.Regenerate()
    left, right, top, bottom = _area(doc, sheets[0], s)
    sizes = _measure(doc, sheets[0], [v for _, row in todo for v in row])
    gx, gy = s["gap_x"] * MM, s["gap_y"] * MM
    width = right - left

    # split every beam group into rows that fit the sheet width
    rows = []
    for letter, views in todo:
        cur, x = [], 0.0
        for v in views:
            w = sizes[v.Id][0]
            if w > width:
                warn("'%s' is wider than the sheet's drawing area" % v.Name)
            if cur and x + w > width:
                rows.append(cur)
                cur, x = [], 0.0
            cur.append(v)
            x += w + gx
        rows.append(cur)

    # place rows top to bottom; new sheet when a row does not fit
    y = top
    sheet = sheets[0]
    for row in rows:
        h = max(sizes[v.Id][1] for v in row)
        if y - h < bottom and y < top:
            sheet = _new_sheet(doc, tb, s, len(sheets) + 1, counter)
            sheets.append(sheet)
            y = top
        x = left
        for v in row:
            w, vh = sizes[v.Id]
            if s["align"] == "Top":
                cy = y - vh / 2.0
            else:
                cy = y - h / 2.0
            vp = Viewport.Create(doc, sheet.Id, v.Id, XYZ(x + w / 2.0, cy, 0))
            if vpt is not None:
                vp.ChangeTypeId(vpt.Id)
            x += w + gx
        y -= h + gy
    return sheets
