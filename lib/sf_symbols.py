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


WRAP_MM = 20.0  # default text box width: longer text wraps onto a new line


def _lab(x, y, h, font="Arial", ha="center", va="middle", wrap=WRAP_MM):
    return {"x": x, "y": y, "h": h, "font": font, "ha": ha, "va": va, "wrap": wrap}


def _align_enums(spec):
    from Autodesk.Revit.DB import HorizontalTextAlignment, VerticalTextAlignment
    ha = {"left": HorizontalTextAlignment.Left, "right": HorizontalTextAlignment.Right}.get(
        spec.get("ha", "center"), HorizontalTextAlignment.Center)
    va = {"top": VerticalTextAlignment.Top, "bottom": VerticalTextAlignment.Bottom}.get(
        spec.get("va", "middle"), VerticalTextAlignment.Middle)
    return ha, va


def _apply_text_layout(te, spec, log, what):
    """Alignment, wrap width and position on a label / text note."""
    ha, va = _align_enums(spec)
    try:
        te.HorizontalAlignment = ha
        te.VerticalAlignment = va
    except Exception as ex:
        log("%s: alignment not set: %s" % (what, br._err(ex)))
    wrap = float(spec.get("wrap", 0) or 0)
    if wrap > 0:
        try:
            w = wrap * MM
            w = max(te.GetMinimumAllowedWidth(), min(te.GetMaximumAllowedWidth(), w))
            te.Width = w
        except Exception as ex:
            log("%s: wrap width not set: %s" % (what, br._err(ex)))
    te.Coord = _P(spec["x"], spec["y"])


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
        # the box grows with the text: label border, not a drawn rectangle
        labels = [dict(_lab(0, 0, 2.5, font), box=True, box_offset=1.0)]
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


def _raw_pieces(s):
    """Unrotated geometry: [{'kind': 'poly', 'pts', 'closed', 'fill'} | {'kind': 'circle', 'x', 'y', 'r', 'fill'}]"""
    t = s["type"]
    fill = bool(s.get("fill"))
    if t in ("circle", "dot"):
        return [{"kind": "circle", "x": s["x"], "y": s["y"], "r": s["r"], "fill": fill or t == "dot"}]
    if t == "line":
        return [{"kind": "poly", "pts": [(s["x1"], s["y1"]), (s["x2"], s["y2"])], "closed": False, "fill": False}]
    if t == "arrow":
        (x1, y1), (x2, y2) = (s["x1"], s["y1"]), (s["x2"], s["y2"])
        L = math.hypot(x2 - x1, y2 - y1) or 1.0
        ux, uy = (x2 - x1) / L, (y2 - y1) / L
        head = float(s.get("head", 2.5))
        w = head * 0.35
        bx, by = x2 - ux * head, y2 - uy * head
        tri = [(x2, y2), (bx - uy * w, by + ux * w), (bx + uy * w, by - ux * w)]
        return [{"kind": "poly", "pts": [(x1, y1), (bx, by)], "closed": False, "fill": False},
                {"kind": "poly", "pts": tri, "closed": True, "fill": s.get("fill", True)}]
    if t == "rect":
        x, y, w, h = s["x"], s["y"], s["w"], s["h"]
        return [{"kind": "poly", "pts": [(x, y), (x + w, y), (x + w, y + h), (x, y + h)], "closed": True, "fill": fill}]
    if t == "triangle":
        return [{"kind": "poly", "pts": triangle_points(s), "closed": True, "fill": fill}]
    if t == "polygon":
        return [{"kind": "poly", "pts": [tuple(p) for p in s["pts"]], "closed": s.get("closed", True), "fill": fill}]
    if t == "arc":
        return [{"kind": "arc", "x": s["x"], "y": s["y"], "r": s["r"], "a0": s["a0"], "a1": s["a1"], "fill": False}]
    return []


def arc_points(p, n=24):
    a0, a1 = math.radians(p["a0"]), math.radians(p["a1"])
    return [(p["x"] + p["r"] * math.cos(a0 + (a1 - a0) * i / float(n)),
             p["y"] + p["r"] * math.sin(a0 + (a1 - a0) * i / float(n))) for i in range(n + 1)]


def _raw_box(s):
    pts = []
    for p in _raw_pieces(s):
        if p["kind"] == "circle":
            pts += [(p["x"] - p["r"], p["y"] - p["r"]), (p["x"] + p["r"], p["y"] + p["r"])]
        elif p["kind"] == "arc":
            pts += arc_points(p, 12)
        else:
            pts += p["pts"]
    if not pts:  # text
        h = s.get("h", 2.5)
        return s["x"] - h, s["y"] - h / 2, s["x"] + h * max(len(s.get("text", "")), 1) * 0.35, s["y"] + h / 2
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def centre(s):
    x0, y0, x1, y1 = _raw_box(s)
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def pieces(s):
    """Geometry in mm with the shape's rotation (degrees, about its centre)."""
    rot = math.radians(float(s.get("rot", 0) or 0))
    raw = _raw_pieces(s)
    if not rot:
        return raw
    cx, cy = centre(s)
    c, sn = math.cos(rot), math.sin(rot)
    turn = lambda x, y: (cx + (x - cx) * c - (y - cy) * sn, cy + (x - cx) * sn + (y - cy) * c)
    out = []
    for p in raw:
        q = dict(p)
        if p["kind"] == "circle":
            q["x"], q["y"] = turn(p["x"], p["y"])
        elif p["kind"] == "arc":
            q["x"], q["y"] = turn(p["x"], p["y"])
            q["a0"], q["a1"] = p["a0"] + math.degrees(rot), p["a1"] + math.degrees(rot)
        else:
            q["pts"] = [turn(x, y) for x, y in p["pts"]]
        out.append(q)
    return out


def bounds(s):
    """(x0, y0, x1, y1) of a shape in mm (rotation included), for hit tests."""
    pts = []
    for p in pieces(s):
        if p["kind"] == "circle":
            pts += [(p["x"] - p["r"], p["y"] - p["r"]), (p["x"] + p["r"], p["y"] + p["r"])]
        elif p["kind"] == "arc":
            pts += arc_points(p, 12)
        else:
            pts += p["pts"]
    if not pts:
        return _raw_box(s)
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def move(s, dx, dy):
    if s["type"] in ("line", "arrow"):
        s["x1"] += dx
        s["x2"] += dx
        s["y1"] += dy
        s["y2"] += dy
    elif s["type"] == "polygon":
        s["pts"] = [[x + dx, y + dy] for x, y in s["pts"]]
    elif s["type"] == "arc":
        s["x"] += dx
        s["y"] += dy
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
    """[(what it shows, x mm, y mm, height mm)] of the labels in the family;
    'what it shows' lists the parameters, e.g. 'Quantity | Type | Comments'."""
    fdoc = doc.EditFamily(family)
    try:
        return [(_label_contents(fdoc, lab), lab.Coord.X / MM, lab.Coord.Y / MM, _text_height(fdoc, lab))
                for lab in _labels(fdoc)]
    finally:
        fdoc.Close(False)


def _label_contents(fdoc, lab):
    names = []
    try:
        for fmt in lab.GetParameterFormatting():
            d = fmt.GetParameterDefinition(fdoc)
            if d is not None:
                names.append((fmt.Prefix or "") + d.Name + (fmt.Suffix or ""))
    except Exception:
        pass
    return " | ".join(names) or (lab.Text or "label")


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


def _text_type(fdoc, base_type, font, h, cache, box=False, box_offset=1.0):
    """A text / label type 'EPL <font> <h>mm', black, width factor 1;
    with box=True Revit draws a border that fits the text ('Show Border')."""
    key = (base_type.Id, font, h, box, box_offset)
    if key in cache:
        return cache[key]
    name = "EPL %s %gmm%s" % (font, h, " Box" if box else "")
    existing = [t for t in FilteredElementCollector(fdoc).OfClass(type(base_type)) if br.ename(t) == name]
    t = existing[0] if existing else base_type.Duplicate(name)
    for bip, val in ((BuiltInParameter.TEXT_FONT, font), (BuiltInParameter.TEXT_SIZE, h * MM),
                     (BuiltInParameter.TEXT_WIDTH_SCALE, 1.0), (BuiltInParameter.LINE_COLOR, 0),
                     (BuiltInParameter.TEXT_BOX_VISIBILITY, 1 if box else 0),
                     (BuiltInParameter.LEADER_OFFSET_SHEET, box_offset * MM)):
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


def _piece_curves(p):
    if p["kind"] == "arc":
        a0, a1 = math.radians(p["a0"]), math.radians(p["a1"])
        if a1 <= a0:
            a1 += 2 * math.pi
        return [Arc.Create(_P(p["x"], p["y"]), p["r"] * MM, a0, a1, XYZ.BasisX, XYZ.BasisY)]
    if p["kind"] == "circle":
        c, r = _P(p["x"], p["y"]), p["r"] * MM
        return [Arc.Create(c, r, 0, math.pi, XYZ.BasisX, XYZ.BasisY),
                Arc.Create(c, r, math.pi, 2 * math.pi, XYZ.BasisX, XYZ.BasisY)]
    pts = p["pts"]
    n = len(pts) if p["closed"] else len(pts) - 1
    return [Line.CreateBound(_P(*pts[i]), _P(*pts[(i + 1) % len(pts)])) for i in range(n)]


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
                    wrap = float(s.get("wrap", 0) or 0)
                    if wrap > 0:
                        tn = TextNote.Create(fdoc, view.Id, _P(s["x"], s["y"]), wrap * MM, s.get("text", ""), tt.Id)
                    else:
                        tn = TextNote.Create(fdoc, view.Id, _P(s["x"], s["y"]), s.get("text", ""), tt.Id)
                    _apply_text_layout(tn, s, log, "text '%s'" % s.get("text", ""))
                    continue
                style = _pen_style(fdoc, int(s.get("pen", 1)), pens)
                for piece in pieces(s):
                    curves = _piece_curves(piece)
                    for c in curves:
                        dc = fdoc.FamilyCreate.NewDetailCurve(view, c)
                        dc.LineStyle = style
                    closed = piece["kind"] == "circle" or piece.get("closed")
                    if piece.get("fill") and closed and region is not None:
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
            if spec.get("deleted"):
                try:
                    fdoc.Delete(lab.Id)
                    log("label %d deleted" % (i + 1))
                except Exception as ex:
                    log("label %d not deleted: %s" % (i + 1, br._err(ex)))
                continue
            try:
                lt = _text_type(fdoc, fdoc.GetElement(lab.GetTypeId()), spec.get("font", "Arial"),
                                float(spec.get("h", 2.5)), texts, bool(spec.get("box")),
                                float(spec.get("box_offset", 1.0)))
                lab.ChangeTypeId(lt.Id)
                _apply_text_layout(lab, spec, log, "label %d" % (i + 1))
                if spec.get("sample"):
                    try:
                        fmts = list(lab.GetParameterFormatting())
                        if fmts:
                            fmts[0].SampleText = spec["sample"]
                    except Exception:
                        pass
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



# ------------------------------------------------------- read a real family
KIND_CATEGORY = {
    "grid_head": "OST_GridHeads", "level_head": "OST_LevelHeads", "section_head": "OST_SectionHeads",
    "section_tail": "OST_SectionHeads", "callout_head": "OST_CalloutHeads",
    "elevation_body": "OST_ElevationMarks", "elevation_pointer": "OST_ElevationMarks",
    "view_title": "OST_ViewportLabel", "north_arrow": "OST_GenericAnnotation",
    "spot_elevation": "OST_SpotElevSymbols", "span_direction": "OST_SpanDirectionSymbol",
    "rebar_tag": "OST_RebarTags", "column_tag": "OST_StructuralColumnTags",
    "beam_tag": "OST_StructuralFramingTags", "foundation_tag": "OST_StructuralFoundationTags",
    "revision_tag": "OST_RevisionCloudTags", "generic": "OST_GenericAnnotation",
}


def families_of_kind(doc, kind):
    """{name: Family} loaded in the model for this symbol kind."""
    from Autodesk.Revit.DB import BuiltInCategory
    bic = getattr(BuiltInCategory, KIND_CATEGORY.get(kind, "OST_GenericAnnotation"), None)
    out = {}
    for f in FilteredElementCollector(doc).OfClass(Family):
        try:
            if f.IsEditable and f.FamilyCategory is not None and br.is_category_id(f.FamilyCategory, bic):
                out[f.Name] = f
        except Exception:
            pass
    return out


def _mm(v):
    return round(v / MM, 3)


def _pen_of(fdoc, ce):
    """Line weight of the line style a curve is drawn with."""
    try:
        gs = ce.LineStyle
        cat = gs.GraphicsStyleCategory if gs is not None else None
        w = cat.GetLineWeight(GraphicsStyleType.Projection) if cat is not None else None
        if not w and cat is not None and cat.Parent is not None:
            w = cat.Parent.GetLineWeight(GraphicsStyleType.Projection)
        return int(w or 1)
    except Exception:
        return 1


def _ccw_angles(arc):
    c = arc.Center
    p0, p1, pm = arc.GetEndPoint(0), arc.GetEndPoint(1), arc.Evaluate(0.5, True)
    ang = lambda p: math.atan2(p.Y - c.Y, p.X - c.X)
    a0, a1, am = ang(p0), ang(p1), ang(pm)
    norm = lambda a, base: a + 2 * math.pi * math.ceil((base - a) / (2 * math.pi)) if a < base else a
    a1n, amn = norm(a1, a0), norm(am, a0)
    if amn <= a1n:
        return a0, a1n
    return a1, norm(a0, a1)  # it ran clockwise: same arc, counter-clockwise from the other end


def _curve_shape(c, pen):
    if isinstance(c, Line):
        p, q = c.GetEndPoint(0), c.GetEndPoint(1)
        return {"type": "line", "x1": _mm(p.X), "y1": _mm(p.Y), "x2": _mm(q.X), "y2": _mm(q.Y), "pen": pen}
    if isinstance(c, Arc):
        if not c.IsBound:
            return {"type": "circle", "x": _mm(c.Center.X), "y": _mm(c.Center.Y), "r": _mm(c.Radius),
                    "pen": pen, "fill": False}
        a0, a1 = _ccw_angles(c)
        return {"type": "arc", "x": _mm(c.Center.X), "y": _mm(c.Center.Y), "r": _mm(c.Radius),
                "a0": round(math.degrees(a0), 3), "a1": round(math.degrees(a1), 3), "pen": pen}
    pts = [[_mm(p.X), _mm(p.Y)] for p in c.Tessellate()]
    return {"type": "polygon", "pts": pts, "closed": False, "pen": pen, "fill": False}


def _layout_of(te):
    """ha / va / wrap (mm) of a label or text note."""
    out = {"ha": "center", "va": "middle", "wrap": 0.0}
    try:
        out["ha"] = str(te.HorizontalAlignment).lower()
        out["va"] = str(te.VerticalAlignment).lower()
        out["wrap"] = _mm(te.Width)
    except Exception:
        pass
    return out


def import_family(doc, family, kind):
    """The family as a design: its real lines, arcs, circles, fills, texts and
    labels (with their fonts, heights, borders and sample text)."""
    from Autodesk.Revit.DB import BuiltInCategory
    fdoc = doc.EditFamily(family)
    try:
        shapes = []
        for ce in FilteredElementCollector(fdoc).OfClass(CurveElement):
            try:
                if ce.Category is not None and br.is_category_id(ce.Category, BuiltInCategory.OST_SketchLines):
                    continue
                shapes.append(_curve_shape(ce.GeometryCurve, _pen_of(fdoc, ce)))
            except Exception:
                pass
        for fr in FilteredElementCollector(fdoc).OfClass(FilledRegion):
            for loop in fr.GetBoundaries():
                pts = []
                for c in loop:
                    pts += [[_mm(p.X), _mm(p.Y)] for p in c.Tessellate()[:-1]]
                if len(pts) >= 3:
                    shapes.append({"type": "polygon", "pts": pts, "closed": True, "pen": 1, "fill": True})
        for tn in FilteredElementCollector(fdoc).OfClass(TextNote):
            shape = {"type": "text", "x": _mm(tn.Coord.X), "y": _mm(tn.Coord.Y), "text": tn.Text.strip(),
                     "h": _text_height(fdoc, tn), "pen": 1}
            shape.update(_layout_of(tn))
            shapes.append(shape)
        labels = []
        for lab in _labels(fdoc):
            lt = fdoc.GetElement(lab.GetTypeId())
            font = "Arial"
            box, gap = False, 1.0
            if lt is not None:
                p = lt.get_Parameter(BuiltInParameter.TEXT_FONT)
                font = (p.AsString() if p else None) or font
                p = lt.get_Parameter(BuiltInParameter.TEXT_BOX_VISIBILITY)
                box = bool(p.AsInteger()) if p else False
                p = lt.get_Parameter(BuiltInParameter.LEADER_OFFSET_SHEET)
                gap = _mm(p.AsDouble()) if p else 1.0
            sample = ""
            try:
                fmts = list(lab.GetParameterFormatting())
                sample = " ".join((f.SampleText or "") for f in fmts).strip()
            except Exception:
                pass
            spec = {"x": _mm(lab.Coord.X), "y": _mm(lab.Coord.Y), "h": _text_height(fdoc, lab),
                    "font": font, "box": box, "box_offset": gap,
                    "sample": sample or (lab.Text or "1"), "shows": _label_contents(fdoc, lab)}
            spec.update(_layout_of(lab))
            labels.append(spec)
    finally:
        fdoc.Close(False)
    folder = KIND[kind][3] if kind in KIND else "01_ANNOTATION\\03_SYMBOLS"
    return {"kind": kind, "name": family.Name, "folder": folder, "base": family.Name,
            "shapes": shapes, "labels": labels}


def verify(doc, design, family_name, kind):
    """Read the built family back and list what Revit did not keep."""
    fam = families_of_kind(doc, kind).get(family_name)
    if fam is None:
        return ["could not find '%s' in the model to check it" % family_name]
    got = import_family(doc, fam, kind)
    notes = []
    want_geo = len([s for s in design["shapes"] if s["type"] != "text"])
    have_geo = len([s for s in got["shapes"] if s["type"] != "text"])
    if have_geo < want_geo:
        notes.append("geometry: %d shapes asked, %d found" % (want_geo, have_geo))
    for i, (w, h) in enumerate(zip(design.get("labels", []), got["labels"])):
        for key in ("h", "font", "box", "ha", "va"):
            if key in w and str(w[key]) != str(h.get(key)) and not (
                    key == "h" and abs(float(w[key]) - float(h[key])) < 0.01):
                notes.append("label %d: Revit kept %s = %s (asked %s)" % (i + 1, key, h.get(key), w[key]))
        if float(w.get("wrap", 0) or 0) > 0 and abs(float(w["wrap"]) - float(h.get("wrap", 0))) > 0.1:
            notes.append("label %d: Revit kept wrap width %g mm (asked %g)" % (i + 1, h.get("wrap", 0), w["wrap"]))
        if abs(float(w["x"]) - float(h["x"])) > 0.05 or abs(float(w["y"]) - float(h["y"])) > 0.05:
            notes.append("label %d: position (%g, %g) asked, (%g, %g) kept" % (i + 1, w["x"], w["y"], h["x"], h["y"]))
    return notes or ["checked: every shape and label setting was kept"]



# ----------------------------------------------------------- preset choice
def _wedge(cx, cy, r, a0, a1, n=8):
    pts = [[cx, cy]]
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / float(n))
        pts.append([round(cx + r * math.cos(a), 3), round(cy + r * math.sin(a), 3)])
    return {"type": "polygon", "pts": pts, "closed": True, "pen": 1, "fill": True}


def preset_variants(kind, cfg=None):
    """[(label, design)] starting points; the first is the EPL default."""
    base = preset(kind, cfg)
    out = [("EPL default", base)]
    font = base["labels"][0]["font"] if base["labels"] else "Arial"
    if kind == "level_head":
        d = json.loads(json.dumps(base))
        d["shapes"] = [_c(0, 0, 3, 1), _wedge(0, 0, 3, 90, 180), _wedge(0, 0, 3, 270, 360), _l(0, 0, 14, 0, 1)]
        out.append(("Target circle", d))
        d = json.loads(json.dumps(base))
        d["shapes"] = [_l(0, 0, 14, 0, 1)]
        out.append(("Text on the line", d))
    elif kind == "grid_head":
        for dia in (10.0, 12.0):
            d = json.loads(json.dumps(base))
            d["shapes"] = [_c(0, dia / 2, dia / 2, 1)]
            d["labels"] = [_lab(0, dia / 2, 3.5, font)]
            d["name"] = "EPL_ANN_GridHead_Circle-%gmm" % dia
            out.append(("Circle %g mm" % dia, d))
    elif kind == "section_head":
        d = json.loads(json.dumps(base))
        d["shapes"] = [_c(0, 5, 5, 1), _wedge(0, 5, 5, 180, 360), _l(0, 0, 0, 5, 2)]
        d["labels"] = [_lab(0, 7, 3.5, font)]
        out.append(("Half-filled circle", d))
    elif kind == "view_title":
        d = json.loads(json.dumps(base))
        d["shapes"] = [_l(0, -0.5, 80, -0.5, 4)]
        d["labels"] = [_lab(1, 3.5, 5.0, font), _lab(1, -2.75, 2.5, font)]
        out.append(("Underline only", d))
    elif kind in ("column_tag", "beam_tag", "foundation_tag"):
        d = json.loads(json.dumps(base))
        d["labels"] = [_lab(0, 0, 2.5, font)]
        out.append(("No box", d))
    return out


# --------------------------------------------------------- delete family
def family_in_use(doc, family):
    from System.Collections.Generic import HashSet
    unused = set(i for i in doc.GetAllUnusedElements(HashSet[ElementId]()))
    return family.Id not in unused


def delete_family(doc, family):
    t = Transaction(doc, "StructFlow delete family")
    t.Start()
    try:
        doc.Delete(family.Id)
        t.Commit()
    except Exception:
        t.RollBack()
        raise


# --------------------------------------------- the line a datum head sits on
# grid / level types (system families) own the line under a grid / level head
DATUM_PARAMS = {
    "grid": [("Center Segment", "segment"), ("Center Segment Weight", "pen"), ("Center Segment Color", "colour"),
             ("Center Segment Pattern", "pattern"), ("End Segment Weight", "pen"), ("End Segment Color", "colour"),
             ("End Segment Pattern", "pattern"), ("End Segments Length", "mm")],
    "level": [("Line Weight", "pen"), ("Color", "colour"), ("Line Pattern", "pattern")],
}
SEGMENTS = ["Continuous", "None", "Custom"]


def datum_types(doc, kind):
    from Autodesk.Revit.DB import GridType, LevelType
    cls = GridType if kind == "grid_head" else LevelType
    return dict((br.ename(t), t) for t in FilteredElementCollector(doc).OfClass(cls))


def read_datum(doc, t, kind):
    from Autodesk.Revit.DB import LinePatternElement
    v = {}
    for name, k in DATUM_PARAMS["grid" if kind == "grid_head" else "level"]:
        p = t.LookupParameter(name)
        if p is None:
            continue
        if k == "pattern":
            pid = p.AsElementId()
            el = doc.GetElement(pid) if pid != ElementId.InvalidElementId else None
            v[name] = el.Name if el is not None else "Solid"
        elif k == "colour":
            c = p.AsInteger()
            v[name] = "%d,%d,%d" % (c & 255, (c >> 8) & 255, (c >> 16) & 255)
        elif k == "mm":
            v[name] = round(p.AsDouble() / MM, 2)
        else:
            v[name] = p.AsInteger()
    return v


def write_datum(doc, t, kind, values):
    """Write the line settings to the grid / level type; returns what Revit refused."""
    from Autodesk.Revit.DB import LinePatternElement
    patterns = dict((lp.Name, lp.Id) for lp in FilteredElementCollector(doc).OfClass(LinePatternElement))
    patterns["Solid"] = LinePatternElement.GetSolidPatternId()
    kinds = dict(DATUM_PARAMS["grid" if kind == "grid_head" else "level"])
    tr = Transaction(doc, "StructFlow datum line")
    tr.Start()
    try:
        for name, val in values.items():
            p = t.LookupParameter(name)
            if p is None or p.IsReadOnly:
                continue
            k = kinds[name]
            if k == "pattern":
                p.Set(patterns.get(val, LinePatternElement.GetSolidPatternId()))
            elif k == "colour":
                r, g, b = [int(x) for x in str(val).split(",")]
                p.Set(r + g * 256 + b * 65536)
            elif k == "mm":
                p.Set(float(val) * MM)
            else:
                p.Set(int(val))
        tr.Commit()
    except Exception:
        tr.RollBack()
        raise
    got = read_datum(doc, t, kind)
    return ["Revit kept %s = %s (asked %s)" % (n, got.get(n), v) for n, v in values.items()
            if n in got and str(got.get(n)) != str(v)]
