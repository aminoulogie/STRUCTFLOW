# -*- coding: utf-8 -*-
"""StructFlow Symbol Designer engine.

A design is plain data (saved as JSON) describing an annotation symbol in
mm on paper, origin at the family origin, y up:
  shapes: circle (x, y, r), line (x1, y1, x2, y2), rect (x, y, w, h),
          triangle (x, y, w, h, dir up/down/left/right), text (x, y, text, h)
          each with pen (1-16) and fill (circles / rects / triangles)
  labels: the base family's labels, by index: x, y, h (text height), font
build() opens the base family, removes its old geometry, draws the design,
restyles and moves its labels, saves it under the EPL name into the library
and loads it into the model. Labels themselves come from the base family:
Revit's API can edit labels but not create them."""
import io
import json
import math
import os

from System.Collections.Generic import List
from Autodesk.Revit.DB import (
    Arc, BuiltInParameter, CategoryType, Color, CurveElement, CurveLoop,
    ElementId, Family, FamilySource, FilledRegion, FilledRegionType,
    FillPatternElement, FilteredElementCollector, GraphicsStyleType,
    IFamilyLoadOptions, Line, SaveAsOptions, TextElement, TextNote,
    TextNoteType, Transaction, View, XYZ,
)

import sf_audit as au
import sf_beamrebar as br

MM = br.MM
DESIGNS = os.path.join(os.environ["APPDATA"], "pyRevit", "StructFlow_symbol_designs")

# kind: (label, default EPL name, library folder)
KINDS = [
    ("grid_head", "Grid head", "EPL_ANN_GridHead_Circle-8mm", "01_ANNOTATION\\01_DATUMS"),
    ("level_head", "Level head", "EPL_ANN_LevelHead_Triangle", "01_ANNOTATION\\01_DATUMS"),
    ("section_head", "Section head", "EPL_ANN_SectionHead_Arrow-10mm", "01_ANNOTATION\\02_VIEW_SYMBOLS"),
    ("section_tail", "Section tail", "EPL_ANN_SectionTail_Arrow", "01_ANNOTATION\\02_VIEW_SYMBOLS"),
    ("callout_head", "Callout head", "EPL_ANN_CalloutHead", "01_ANNOTATION\\02_VIEW_SYMBOLS"),
    ("elevation_body", "Elevation mark body", "EPL_ANN_ElevationBody_Circle-10mm", "01_ANNOTATION\\02_VIEW_SYMBOLS"),
    ("elevation_pointer", "Elevation mark pointer", "EPL_ANN_ElevationPointer_Circle-10mm", "01_ANNOTATION\\02_VIEW_SYMBOLS"),
    ("view_title", "View title (sheet)", "EPL_ANN_ViewTitle", "01_ANNOTATION\\02_VIEW_SYMBOLS"),
    ("north_arrow", "North arrow", "EPL_ANN_NorthArrow", "01_ANNOTATION\\03_SYMBOLS"),
    ("spot_elevation", "Spot elevation", "EPL_ANN_SpotElevation_TargetFilled", "01_ANNOTATION\\03_SYMBOLS"),
    ("span_direction", "Span direction", "EPL_ANN_SpanDirection", "01_ANNOTATION\\03_SYMBOLS"),
    ("rebar_tag", "Rebar tag", "EPL_TAG_Rebar", "01_ANNOTATION\\04_TAGS\\03_REBAR"),
    ("column_tag", "Column tag", "EPL_TAG_StrColumn", "01_ANNOTATION\\04_TAGS\\02_STRUCTURAL"),
    ("beam_tag", "Beam tag", "EPL_TAG_StrFraming", "01_ANNOTATION\\04_TAGS\\02_STRUCTURAL"),
    ("foundation_tag", "Foundation tag", "EPL_TAG_StrFoundation", "01_ANNOTATION\\04_TAGS\\02_STRUCTURAL"),
    ("revision_tag", "Revision tag", "EPL_TAG_Revision", "01_ANNOTATION\\04_TAGS\\01_GENERAL"),
    ("generic", "Blank symbol", "EPL_ANN_Symbol", "01_ANNOTATION\\03_SYMBOLS"),
]
KIND = dict((k[0], k) for k in KINDS)


# ---------------------------------------------------------------- presets
def _c(x, y, r, pen=1, fill=False):
    return {"type": "circle", "x": x, "y": y, "r": r, "pen": pen, "fill": fill}


def _l(x1, y1, x2, y2, pen=1):
    return {"type": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "pen": pen}


def _t(x, y, w, h, d, pen=1, fill=True):
    return {"type": "triangle", "x": x, "y": y, "w": w, "h": h, "dir": d, "pen": pen, "fill": fill}


def _r(x, y, w, h, pen=1, fill=False):
    return {"type": "rect", "x": x, "y": y, "w": w, "h": h, "pen": pen, "fill": fill}


def _lab(x, y, h, font="Arial"):
    return {"x": x, "y": y, "h": h, "font": font}


def preset(kind, cfg=None):
    """A starting design per kind, from the answers in epl_standards.jsonc."""
    cfg = cfg or au.load_config()
    sd = cfg.get("symbol_design", {})
    font = cfg.get("text", {}).get("font", "Arial")
    gb, gt = float(sd.get("grid_bubble_mm", 8)), float(sd.get("grid_text_mm", 2.5))
    sh = float(sd.get("section_head_mm", 10))
    tn, ts = float(sd.get("view_title_name_mm", 5)), float(sd.get("view_title_scale_mm", 2.5))
    shapes, labels = [], []
    if kind == "grid_head":
        shapes = [_c(0, gb / 2, gb / 2, 1)]
        labels = [_lab(0, gb / 2, gt, font)]
    elif kind == "level_head":
        # filled triangle on the level line, name above, elevation below
        shapes = [_t(0, 1.3, 3.0, 2.6, "down", 1, True), _l(0, 0, 14, 0, 1)]
        labels = [_lab(4, 2.5, 2.5, font), _lab(4, -2.5, 2.5, font)]
    elif kind == "section_head":
        # letter with arrow only: short line to the arrow, filled arrow, letter above
        shapes = [_l(0, 0, 0, sh * 0.5, 2), _t(sh * 0.25, sh * 0.5, sh * 0.5, sh * 0.3, "right", 1, True)]
        labels = [_lab(sh * 0.35, sh * 0.95, 3.5, font)]
    elif kind == "section_tail":
        shapes = [_l(0, 0, 0, sh * 0.5, 2), _t(sh * 0.25, sh * 0.5, sh * 0.5, sh * 0.3, "right", 1, True)]
    elif kind == "callout_head":
        shapes = [_c(0, 0, sh / 2, 1), _l(-sh / 2, 0, sh / 2, 0, 1)]
        labels = [_lab(0, sh / 4, 2.5, font), _lab(0, -sh / 4, 2.0, font)]
    elif kind == "elevation_body":
        shapes = [_c(0, 0, sh / 2, 1)]
        labels = [_lab(0, 0, 2.5, font)]
    elif kind == "elevation_pointer":
        shapes = [_t(0, sh / 2 + 1.5, sh * 0.5, 3.0, "up", 1, True)]
    elif kind == "view_title":
        # number circle (detail number over sheet number) + name + underline + scale
        r = 6.0
        shapes = [_c(r, 0, r, 2), _l(0, 0, 2 * r, 0, 1), _l(2 * r + 2, -0.5, 2 * r + 80, -0.5, 4)]
        labels = [_lab(r, r / 2, 3.5, font), _lab(r, -r / 2, 2.5, font),
                  _lab(2 * r + 3, 1.5 + tn / 2, tn, font), _lab(2 * r + 3, -1.5 - ts / 2, ts, font)]
    elif kind == "north_arrow":
        shapes = [_c(0, 0, 8, 1), _t(0, 3, 6, 12, "up", 1, True)]
        labels = [_lab(0, 11, 3.5, font)]
    elif kind == "spot_elevation":
        shapes = [_c(0, 0, 1.5, 1, True), _l(-3, 0, 3, 0, 1), _l(0, -3, 0, 3, 1)]
        labels = [_lab(5, 1.5, 2.5, font)]
    elif kind == "span_direction":
        shapes = [_l(-15, 0, 15, 0, 1), _t(-13.5, 0, 3, 2.5, "left", 1, True), _t(13.5, 0, 3, 2.5, "right", 1, True)]
    elif kind == "rebar_tag":
        # bar mark in a circle, description beside it: (7) 4 H20 - T
        shapes = [_c(0, 0, 2.5, 1)]
        labels = [_lab(0, 0, 2.5, font), _lab(4, 0, 2.5, font)]
    elif kind in ("column_tag", "beam_tag", "foundation_tag"):
        shapes = [_r(-9, -2.5, 18, 5, 1)]
        labels = [_lab(0, 0, 2.5, font)]
    elif kind == "revision_tag":
        shapes = [_t(0, 0, 7, 6, "up", 1, False)]
        labels = [_lab(0, -0.5, 2.5, font)]
    return {"kind": kind, "name": KIND[kind][2], "folder": KIND[kind][3], "base": "",
            "shapes": shapes, "labels": labels}


# ---------------------------------------------------------- design files
def save_design(design, path):
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(design, indent=1, ensure_ascii=False))


def load_design(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def triangle_points(s):
    x, y, w, h, d = s["x"], s["y"], s["w"], s["h"], s.get("dir", "up")
    if d == "down":
        return [(x - w / 2, y + h / 2), (x + w / 2, y + h / 2), (x, y - h / 2)]
    if d == "left":
        return [(x + h / 2, y + w / 2), (x + h / 2, y - w / 2), (x - h / 2, y)]
    if d == "right":
        return [(x - h / 2, y + w / 2), (x - h / 2, y - w / 2), (x + h / 2, y)]
    return [(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x, y + h / 2)]


def bounds(s):
    """(x0, y0, x1, y1) of a shape in mm, for hit tests."""
    t = s["type"]
    if t == "circle":
        return s["x"] - s["r"], s["y"] - s["r"], s["x"] + s["r"], s["y"] + s["r"]
    if t == "line":
        return min(s["x1"], s["x2"]), min(s["y1"], s["y2"]), max(s["x1"], s["x2"]), max(s["y1"], s["y2"])
    if t == "rect":
        return s["x"], s["y"], s["x"] + s["w"], s["y"] + s["h"]
    if t == "triangle":
        pts = triangle_points(s)
        return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
    h = s.get("h", 2.5)
    return s["x"] - h, s["y"] - h / 2, s["x"] + h * max(len(s.get("text", "")), 1) * 0.35, s["y"] + h / 2


def move(s, dx, dy):
    if s["type"] == "line":
        s["x1"] += dx
        s["x2"] += dx
        s["y1"] += dy
        s["y2"] += dy
    else:
        s["x"] += dx
        s["y"] += dy


# ------------------------------------------------------- family lookups
def annotation_families(doc):
    """{'Category: Family': Family} for every editable annotation family."""
    out = {}
    for f in FilteredElementCollector(doc).OfClass(Family):
        try:
            if f.IsEditable and f.FamilyCategory is not None and \
                    f.FamilyCategory.CategoryType == CategoryType.Annotation:
                out["%s: %s" % (f.FamilyCategory.Name, f.Name)] = f
        except Exception:
            pass
    return out


def family_labels(doc, family):
    """[(text, x mm, y mm, height mm)] of the labels inside the family."""
    fdoc = doc.EditFamily(family)
    try:
        return [(lab.Text or "label", lab.Coord.X / MM, lab.Coord.Y / MM, _text_height(fdoc, lab))
                for lab in _labels(fdoc)]
    finally:
        fdoc.Close(False)


def _labels(fdoc):
    out = []
    for te in FilteredElementCollector(fdoc).OfClass(TextElement):
        if not isinstance(te, TextNote):
            out.append(te)
    out.sort(key=lambda t: (-round(t.Coord.Y, 4), t.Coord.X))
    return out


def _text_height(fdoc, te):
    t = fdoc.GetElement(te.GetTypeId())
    p = t.get_Parameter(BuiltInParameter.TEXT_SIZE) if t is not None else None
    return round(p.AsDouble() / MM, 2) if p is not None else 2.5


# ----------------------------------------------------------------- build
class _LoadOptions(IFamilyLoadOptions):
    def OnFamilyFound(self, familyInUse, overwriteParameterValues):
        overwriteParameterValues.Value = True
        return True

    def OnSharedFamilyFound(self, sharedFamily, familyInUse, source, overwriteParameterValues):
        source.Value = FamilySource.Family
        overwriteParameterValues.Value = True
        return True


def _text_type(fdoc, base_type, font, h, cache):
    """A text / label type 'EPL <font> <h>mm', black, width factor 1."""
    key = (base_type.Id, font, h)
    if key in cache:
        return cache[key]
    name = "EPL %s %gmm" % (font, h)
    existing = [t for t in FilteredElementCollector(fdoc).OfClass(type(base_type)) if br.ename(t) == name]
    t = existing[0] if existing else base_type.Duplicate(name)
    for bip, val in ((BuiltInParameter.TEXT_FONT, font), (BuiltInParameter.TEXT_SIZE, h * MM),
                     (BuiltInParameter.TEXT_WIDTH_SCALE, 1.0), (BuiltInParameter.LINE_COLOR, 0)):
        p = t.get_Parameter(bip)
        if p is not None and not p.IsReadOnly:
            p.Set(val)
    cache[key] = t
    return t


def _pen_style(fdoc, pen, cache):
    """Subcategory 'EPL Pen n' of the family category, line weight n, black."""
    if pen in cache:
        return cache[pen]
    parent = fdoc.OwnerFamily.FamilyCategory
    name = "EPL Pen %d" % pen
    sub = None
    for c in parent.SubCategories:
        if c.Name == name:
            sub = c
    if sub is None:
        sub = fdoc.Settings.Categories.NewSubcategory(parent, name)
    sub.SetLineWeight(int(pen), GraphicsStyleType.Projection)
    sub.LineColor = Color(0, 0, 0)
    cache[pen] = sub.GetGraphicsStyle(GraphicsStyleType.Projection)
    return cache[pen]


def _solid_region_type(fdoc):
    solid = None
    for fp in FilteredElementCollector(fdoc).OfClass(FillPatternElement):
        if fp.GetFillPattern().IsSolidFill:
            solid = fp
    for t in FilteredElementCollector(fdoc).OfClass(FilledRegionType):
        if solid is not None and t.ForegroundPatternId == solid.Id:
            return t
    types = list(FilteredElementCollector(fdoc).OfClass(FilledRegionType))
    if not types or solid is None:
        return None
    t = types[0].Duplicate("EPL Solid Black")
    t.ForegroundPatternId = solid.Id
    t.ForegroundPatternColor = Color(0, 0, 0)
    return t


def _P(x, y):
    return XYZ(x * MM, y * MM, 0)


def _curves(s):
    t = s["type"]
    if t == "line":
        return [Line.CreateBound(_P(s["x1"], s["y1"]), _P(s["x2"], s["y2"]))]
    if t == "circle":
        c, r = _P(s["x"], s["y"]), s["r"] * MM
        return [Arc.Create(c, r, 0, math.pi, XYZ.BasisX, XYZ.BasisY),
                Arc.Create(c, r, math.pi, 2 * math.pi, XYZ.BasisX, XYZ.BasisY)]
    if t == "rect":
        x, y, w, h = s["x"], s["y"], s["w"], s["h"]
        pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    else:
        pts = triangle_points(s)
    return [Line.CreateBound(_P(*pts[i]), _P(*pts[(i + 1) % len(pts)])) for i in range(len(pts))]


def build(doc, design, mode, root, save_file, load, log):
    """mode 'copy' = save as the design's EPL name (new family);
    'overwrite' = keep the base family's name and replace it in the model."""
    families = dict((f.Name, f) for f in FilteredElementCollector(doc).OfClass(Family))
    base = families.get(design["base"])
    if base is None:
        raise ValueError("pick a base family (it provides the labels)")
    fdoc = doc.EditFamily(base)
    try:
        view = [v for v in FilteredElementCollector(fdoc).OfClass(View) if not v.IsTemplate][0]
        t = Transaction(fdoc, "StructFlow Symbol Designer")
        t.Start()
        # old geometry out (labels stay)
        old = [e.Id for e in FilteredElementCollector(fdoc).OfClass(CurveElement)]
        old += [e.Id for e in FilteredElementCollector(fdoc).OfClass(FilledRegion)]
        old += [e.Id for e in FilteredElementCollector(fdoc).OfClass(TextNote)]
        for eid in old:
            try:
                fdoc.Delete(eid)
            except Exception:
                pass
        pens, texts = {}, {}
        region = _solid_region_type(fdoc)
        note_base = list(FilteredElementCollector(fdoc).OfClass(TextNoteType))
        for s in design["shapes"]:
            try:
                if s["type"] == "text":
                    if not note_base:
                        log("no text type in the family, text '%s' skipped" % s.get("text"))
                        continue
                    tt = _text_type(fdoc, note_base[0], design.get("font", "Arial"), float(s.get("h", 2.5)), texts)
                    TextNote.Create(fdoc, view.Id, _P(s["x"], s["y"]), s.get("text", ""), tt.Id)
                    continue
                curves = _curves(s)
                style = _pen_style(fdoc, int(s.get("pen", 1)), pens)
                for c in curves:
                    dc = fdoc.FamilyCreate.NewDetailCurve(view, c)
                    dc.LineStyle = style
                if s.get("fill") and s["type"] != "line" and region is not None:
                    loop = CurveLoop()
                    for c in curves:
                        loop.Append(c)
                    FilledRegion.Create(fdoc, region.Id, view.Id, List[CurveLoop]([loop]))
            except Exception as ex:
                log("shape %s skipped: %s" % (s["type"], br._err(ex)))
        # labels: restyle and move
        labels = _labels(fdoc)
        for i, spec in enumerate(design.get("labels", [])):
            if i >= len(labels):
                log("design has more labels than the base family (%d): extra ones ignored" % len(labels))
                break
            lab = labels[i]
            try:
                lt = _text_type(fdoc, fdoc.GetElement(lab.GetTypeId()), spec.get("font", "Arial"),
                                float(spec.get("h", 2.5)), texts)
                lab.ChangeTypeId(lt.Id)
                lab.Coord = _P(spec["x"], spec["y"])
            except Exception as ex:
                log("label %d not restyled: %s" % (i + 1, br._err(ex)))
        cat = fdoc.OwnerFamily.FamilyCategory
        cat.LineColor = Color(0, 0, 0)
        t.Commit()

        name = design["name"] if mode == "copy" else base.Name
        if save_file:
            folder = os.path.join(root, design.get("folder", ""))
            if not os.path.isdir(folder):
                os.makedirs(folder)
            path = os.path.join(folder, name + ".rfa")
            opts = SaveAsOptions()
            opts.OverwriteExistingFile = True
            opts.MaximumBackups = 1
            fdoc.SaveAs(path, opts)
            for fn in os.listdir(folder):
                if fn.startswith(name + ".") and fn.endswith(".rfa") and fn != name + ".rfa":
                    os.remove(os.path.join(folder, fn))
            log("saved %s" % path)
        elif mode == "copy":
            log("note: not saved, so the family keeps the base name '%s' when loaded" % base.Name)
        if load:
            fdoc.LoadFamily(doc, _LoadOptions())
            log("loaded '%s' into the model" % (name if save_file or mode == "overwrite" else base.Name))
    finally:
        fdoc.Close(False)
