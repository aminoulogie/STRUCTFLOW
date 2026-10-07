# -*- coding: utf-8 -*-
"""Real cross-section of a type, for the preview: Revit's structural
section data (round, tube, I, RHS, angle, channel, tee, rectangle) with
its dimensions, as polygons in mm centred on the section; and the real
dash / gap lengths of line patterns."""
import math

from Autodesk.Revit.DB import LinePatternElement, LinePatternSegmentType, FilteredElementCollector

import sf_beamrebar as br

MM = br.MM


def _mm(v):
    return (v or 0.0) / MM


def _get(sec, *names):
    for n in names:
        v = getattr(sec, n, None)
        if v:
            return _mm(v)
    return 0.0


def _param_mm(symbol, name):
    p = symbol.LookupParameter(name) if (symbol is not None and name) else None
    return p.AsDouble() / MM if p is not None and p.HasValue else 0.0


def profile_of_symbol(symbol, p_w=None, p_h=None):
    """{'shape', 'w', 'h', 't', 'tw', 'tf', 'name'} in mm."""
    sec = None
    try:
        if symbol is not None and symbol.CanHaveStructuralSection():
            sec = symbol.GetStructuralSection()
    except Exception:
        sec = None
    if sec is not None:
        shape = str(sec.StructuralSectionShape)
        if shape.startswith("Concrete"):
            # concrete section data is not always kept in step with the
            # family's b / h: the parameters are the truth
            pw, ph = _param_mm(symbol, p_w), _param_mm(symbol, p_h)
            if shape == "ConcreteRound":
                d = pw or ph or _get(sec, "Diameter")
                return {"shape": "circle", "w": d, "h": d, "name": shape}
            w, h = pw or _get(sec, "Width"), ph or _get(sec, "Height")
            tw, tf = _get(sec, "WebThickness"), _get(sec, "FlangeThickness")
            if shape == "ConcreteT" and tw and tf:
                return {"shape": "T", "w": w, "h": h, "tw": tw, "tf": tf, "name": shape}
            if shape == "ConcreteL" and tw and tf:
                return {"shape": "L", "w": w, "h": h, "tw": tw, "tf": tf, "name": shape}
            if shape == "ConcreteI" and tw and tf:
                return {"shape": "I", "w": w, "h": h, "tw": tw, "tf": tf, "name": shape}
            return {"shape": "rect", "w": w or 300.0, "h": h or 450.0, "name": shape}
        d = _get(sec, "Diameter")
        w, h = _get(sec, "Width"), _get(sec, "Height")
        t = _get(sec, "WallNominalThickness", "WallDesignThickness")
        tw, tf = _get(sec, "WebThickness"), _get(sec, "FlangeThickness")
        if shape in ("RoundBar", "ConcreteRound"):
            return {"shape": "circle", "w": d, "h": d, "name": shape}
        if shape in ("PipeStandard", "RoundHSS"):
            return {"shape": "ring", "w": d, "h": d, "t": t or d * 0.08, "name": shape}
        if shape == "RectangleHSS":
            return {"shape": "rhs", "w": w, "h": h, "t": t or min(w, h) * 0.08, "name": shape}
        if shape.startswith("I") or shape == "ConcreteI":
            return {"shape": "I", "w": w, "h": h, "tw": tw or w * 0.08, "tf": tf or h * 0.08, "name": shape}
        if shape.startswith("C"):
            return {"shape": "C", "w": w, "h": h, "tw": tw or t or w * 0.1, "tf": tf or t or h * 0.08, "name": shape}
        if shape.startswith("L") or shape == "ConcreteL":
            th = tf or tw or t or min(w, h) * 0.1
            return {"shape": "L", "w": w, "h": h, "tw": tw or th, "tf": tf or th, "name": shape}
        if shape in ("StructuralTees", "ConcreteT"):
            return {"shape": "T", "w": w, "h": h, "tw": tw or w * 0.1, "tf": tf or h * 0.1, "name": shape}
        if w and h:
            return {"shape": "rect", "w": w, "h": h, "name": shape}
    # no section data: read the chosen width / depth parameters
    w = h = 0.0
    if symbol is not None:
        for name, slot in ((p_w, "w"), (p_h, "h")):
            p = symbol.LookupParameter(name) if name else None
            if p is not None:
                if slot == "w":
                    w = p.AsDouble() / MM
                else:
                    h = p.AsDouble() / MM
    fam = symbol.Family.Name.lower() if symbol is not None else ""
    if any(k in fam for k in ("round", "circular", "circle")):
        d = w or h or 300.0
        return {"shape": "circle", "w": d, "h": d, "name": "round (by name)"}
    return {"shape": "rect", "w": w or 300.0, "h": h or 450.0, "name": "rectangle"}


def rect_profile(w, h):
    return {"shape": "rect", "w": w, "h": h, "name": "rectangle"}


def _circle(r, n=40):
    return [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def polygons(p):
    """Outer polygon (and holes) in mm, y up, centred. Returns (outer, [holes])."""
    w, h = p["w"], p["h"]
    x0, x1, y0, y1 = -w / 2.0, w / 2.0, -h / 2.0, h / 2.0
    s = p["shape"]
    if s == "circle":
        return _circle(w / 2.0), []
    if s == "ring":
        return _circle(w / 2.0), [_circle(max(w / 2.0 - p["t"], 1.0))]
    if s == "rhs":
        t = p["t"]
        return ([(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                [[(x0 + t, y0 + t), (x1 - t, y0 + t), (x1 - t, y1 - t), (x0 + t, y1 - t)]])
    if s == "I":
        tw, tf = p["tw"], p["tf"]
        return ([(x0, y0), (x1, y0), (x1, y0 + tf), (tw / 2, y0 + tf), (tw / 2, y1 - tf), (x1, y1 - tf),
                 (x1, y1), (x0, y1), (x0, y1 - tf), (-tw / 2, y1 - tf), (-tw / 2, y0 + tf), (x0, y0 + tf)], [])
    if s == "C":
        tw, tf = p["tw"], p["tf"]
        return ([(x0, y0), (x1, y0), (x1, y0 + tf), (x0 + tw, y0 + tf), (x0 + tw, y1 - tf),
                 (x1, y1 - tf), (x1, y1), (x0, y1)], [])
    if s == "L":
        tw, tf = p["tw"], p["tf"]
        return ([(x0, y0), (x1, y0), (x1, y0 + tf), (x0 + tw, y0 + tf), (x0 + tw, y1), (x0, y1)], [])
    if s == "T":
        tw, tf = p["tw"], p["tf"]
        return ([(x0, y1), (x1, y1), (x1, y1 - tf), (tw / 2, y1 - tf), (tw / 2, y0),
                 (-tw / 2, y0), (-tw / 2, y1 - tf), (x0, y1 - tf)], [])
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], []


def line_dashes(doc):
    """{pattern name: [(kind, length mm on paper)]}; 'Solid' -> []."""
    out = {"Solid": []}
    for lp in FilteredElementCollector(doc).OfClass(LinePatternElement):
        segs = []
        try:
            for sg in lp.GetLinePattern().GetSegments():
                kind = {LinePatternSegmentType.Dash: "dash", LinePatternSegmentType.Space: "space",
                        LinePatternSegmentType.Dot: "dot"}.get(sg.Type, "space")
                segs.append((kind, sg.Length * 304.8))
        except Exception:
            pass
        out[lp.Name] = segs
    return out
