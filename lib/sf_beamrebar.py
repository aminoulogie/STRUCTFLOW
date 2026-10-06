# -*- coding: utf-8 -*-
"""StructFlow beam rebar engine.

Builds top / bottom longitudinal bars (shape 00 / 11 / 21), laps at a
chosen multiple of d inside allowed splice zones, and links (shape 51)
that skip junctions with main beams / columns.

All bars are generated from the beam's real concrete geometry, so the
tool can be re-run at any time ("Rebuild") after the beam moves or
changes size: old auto bars are deleted and recreated with the exact
same settings, so covers and lap lengths never drift.

All user-facing lengths are millimetres. Revit internal units are feet.
"""
import json
import math

import clr
clr.AddReference("System")
from System import Guid, String
from System.Collections.Generic import List

from Autodesk.Revit.DB import (
    BoundingBoxIntersectsFilter, BuiltInCategory, Curve, Element,
    ElementId, ElementMulticategoryFilter, FilteredElementCollector,
    GeometryInstance, Line, Options, Outline, Solid,
    SolidCurveIntersectionOptions, SubTransaction, ViewDetailLevel, XYZ,
)
from Autodesk.Revit.DB.ExtensibleStorage import (
    AccessLevel, Entity, Schema, SchemaBuilder,
)
from Autodesk.Revit.DB.Structure import (
    BarTerminationsData, Rebar, RebarBarType, RebarHookType,
    RebarHostData, RebarPresentationMode, RebarShape, RebarStyle,
    RebarTerminationOrientation,
)

MM = 1.0 / 304.8
TOL = 1.0 * MM

DEFAULTS = {
    "cover_top": 30.0, "cover_bottom": 30.0, "cover_side": 30.0,
    "cover_end": 30.0, "end_ext": 0.0,
    "top_type": "H16", "top_n": 2, "top_A": 0.0, "top_C": 0.0,
    "bot_type": "H20", "bot_n": 3, "bot_A": 0.0, "bot_C": 0.0,
    "lap_factor": 60.0, "stock": 12000.0,
    "top_zones": "", "bot_zones": "",
    "links_on": True, "link_type": "H10", "link_spacing": 200.0,
    "link_offset": 50.0, "link_hook": "Stirrup/Tie - 135 deg.",
    "link_flip": False, "primary": False, "stop_cols": True,
    "display": "FirstMidLast",
    "full_length": False,
    # which beams keep continuous links at crossings: auto / horizontal / vertical
    "link_priority": "auto",
    # manual splice centres, mm from beam start face (None = automatic)
    "top_splices": None, "bot_splices": None,
}

DISPLAY_MODES = [
    ("All", "Show all links"),
    ("FirstMidLast", "First / middle / last"),
    ("Middle3", "3 in the middle"),
]


# --------------------------------------------------------------- helpers
def ename(el):
    try:
        return Element.Name.__get__(el)
    except Exception:
        return el.Name


def by_name(doc, cls, name):
    for el in FilteredElementCollector(doc).OfClass(cls):
        if ename(el) == name:
            return el
    return None


def names_of(doc, cls):
    return sorted(ename(e) for e in FilteredElementCollector(doc).OfClass(cls))


def is_category(el, bic):
    cat = el.Category
    if cat is None:
        return False
    try:
        return cat.BuiltInCategory == bic
    except Exception:
        return cat.Id == ElementId(bic)


def merged(intervals):
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1] + TOL:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def complement(lo, hi, intervals):
    """Clear segments of [lo, hi] not covered by intervals."""
    out, cur = [], lo
    for a, b in merged(intervals):
        if a > cur + TOL:
            out.append((cur, a))
        cur = max(cur, b)
    if hi > cur + TOL:
        out.append((cur, hi))
    return out


# ------------------------------------------------------ settings storage
_SCHEMA_GUID = Guid("a3d95b71-0c4e-4f8a-b2d6-7e19c5f0a842")
_AUTO_MARK = "SF_AUTO_REBAR"


def _schema():
    s = Schema.Lookup(_SCHEMA_GUID)
    if s is not None:
        return s
    sb = SchemaBuilder(_SCHEMA_GUID)
    sb.SetSchemaName("StructFlowBeamRebar")
    sb.SetReadAccessLevel(AccessLevel.Public)
    sb.SetWriteAccessLevel(AccessLevel.Public)
    sb.AddSimpleField("Data", clr.GetClrType(String))
    return sb.Finish()


def _set_data(el, text):
    ent = Entity(_schema())
    ent.Set[String]("Data", text)
    el.SetEntity(ent)


def _get_data(el):
    ent = el.GetEntity(_schema())
    if ent is None or not ent.IsValid():
        return None
    return ent.Get[String]("Data")


def load_beam_settings(beam):
    raw = _get_data(beam)
    if not raw or raw.startswith(_AUTO_MARK):
        return None
    s = dict(DEFAULTS)
    s.update(json.loads(raw))
    return s


def is_auto_rebar(rebar):
    return (_get_data(rebar) or "").startswith(_AUTO_MARK)


def rebar_layer(rebar):
    """'top', 'bot', 'link' or '' for StructFlow bars."""
    data = _get_data(rebar) or ""
    return data.split("|")[1] if data.startswith(_AUTO_MARK + "|") else ""


# -------------------------------------------------------- beam geometry
def _solids(el):
    opt = Options()
    opt.DetailLevel = ViewDetailLevel.Fine
    opt.ComputeReferences = False
    out = []

    def walk(geo):
        for g in geo:
            if isinstance(g, Solid) and g.Volume > 1e-9:
                out.append(g)
            elif isinstance(g, GeometryInstance):
                walk(g.GetInstanceGeometry())

    geo = el.get_Geometry(opt)
    if geo is not None:
        walk(geo)
    return out


def _points(el):
    pts = []
    for s in _solids(el):
        for e in s.Edges:
            pts.extend(e.Tessellate())
    return pts


class BeamFrame(object):
    """Local axes: u along beam, v across width, w = world Z (height)."""

    def __init__(self, beam):
        loc = beam.Location
        crv = getattr(loc, "Curve", None)
        if not isinstance(crv, Line):
            raise ValueError("only straight beams are supported")
        p0, p1 = crv.GetEndPoint(0), crv.GetEndPoint(1)
        d = XYZ(p1.X - p0.X, p1.Y - p0.Y, 0)
        if d.GetLength() < 1e-6:
            raise ValueError("vertical members are not supported")
        self.o = XYZ(p0.X, p0.Y, 0)
        self.X = d.Normalize()
        self.Y = XYZ.BasisZ.CrossProduct(self.X)

        pts = _points(beam)
        if not pts:
            raise ValueError("beam has no solid geometry")
        us = [self.u(p) for p in pts]
        vs = [self.v(p) for p in pts]
        ws = [p.Z for p in pts]
        self.u0, self.u1 = min(us), max(us)
        self.v0, self.v1 = min(vs), max(vs)
        self.w0, self.w1 = min(ws), max(ws)

    def u(self, p):
        return (p - self.o).DotProduct(self.X)

    def v(self, p):
        return (p - self.o).DotProduct(self.Y)

    def pt(self, u, v, w):
        h = self.o + self.X * u + self.Y * v
        return XYZ(h.X, h.Y, w)


def _has_material(solids, top, bottom):
    """True if a vertical line between two points hits any of the solids."""
    line = Line.CreateBound(bottom, top)
    opts = SolidCurveIntersectionOptions()
    for s in solids:
        try:
            if s.IntersectWithCurve(line, opts).SegmentCount > 0:
                return True
        except Exception:
            pass
    return False


def _other_is_main(beam_solids, other, fr, a, b, warn):
    """At a crossing, decide which beam is the main one:
    1. the beam that is cut (has a gap at the crossing) is secondary;
    2. if they overlap without a join, the deeper beam is main;
    3. equal depth and no join -> treat the other as main and warn."""
    uc, vc = (a + b) / 2.0, (fr.v0 + fr.v1) / 2.0
    top, bot = fr.pt(uc, vc, fr.w1 + 0.5), fr.pt(uc, vc, fr.w0 - 0.5)
    if not _has_material(beam_solids, top, bot):
        return True
    other_solids = _solids(other)
    if not _has_material(other_solids, top, bot):
        return False
    ws = [p.Z for p in _points(other)]
    other_depth, our_depth = max(ws) - min(ws), fr.w1 - fr.w0
    if abs(other_depth - our_depth) > 5 * MM:
        return other_depth > our_depth
    warn("beam %s overlaps this beam without a join; links stopped there. "
         "Use Join / Switch Join Order so the main beam cuts the other." % other.Id)
    return True


def is_horizontal(vec):
    """Runs left-right on the plan (model X) rather than up-down (model Y)."""
    return abs(vec.X) >= abs(vec.Y)


def _direction(el):
    crv = getattr(el.Location, "Curve", None)
    if isinstance(crv, Line):
        return crv.Direction
    return None


def junctions(doc, beam, fr, warn, priority="auto"):
    """Intervals along u where a crossing MAIN beam or a column passes
    through this beam. Secondary beams that frame into or cross this one
    are ignored (this beam is the main one there).
    Returns (beam_intervals, column_intervals)."""
    beam_solids = _solids(beam)
    bb = beam.get_BoundingBox(None)
    pad = XYZ(10 * MM, 10 * MM, 10 * MM)
    cats = List[BuiltInCategory]([BuiltInCategory.OST_StructuralFraming,
                                  BuiltInCategory.OST_StructuralColumns])
    els = (FilteredElementCollector(doc)
           .WhereElementIsNotElementType()
           .WherePasses(ElementMulticategoryFilter(cats))
           .WherePasses(BoundingBoxIntersectsFilter(Outline(bb.Min - pad, bb.Max + pad))))
    beams, cols = [], []
    for el in els:
        if el.Id == beam.Id:
            continue
        pts = _points(el)
        if not pts:
            continue
        vs = [fr.v(p) for p in pts]
        ws = [p.Z for p in pts]
        # must cover our full width and overlap our depth
        if min(vs) > fr.v0 + 5 * MM or max(vs) < fr.v1 - 5 * MM:
            continue
        if max(ws) < fr.w0 + TOL or min(ws) > fr.w1 - TOL:
            continue
        us = [fr.u(p) for p in pts]
        a, b = max(min(us), fr.u0), min(max(us), fr.u1)
        if b - a <= TOL:
            continue
        # a collinear beam lying along ours is not a junction
        if (b - a) > 0.9 * (fr.u1 - fr.u0):
            continue
        if is_category(el, BuiltInCategory.OST_StructuralColumns):
            cols.append((a, b))
        else:
            other_dir = _direction(el)
            if priority in ("horizontal", "vertical") and other_dir is not None:
                want_h = priority == "horizontal"
                if is_horizontal(fr.X) == want_h:
                    continue  # this beam is the chosen main direction
                if is_horizontal(other_dir) == want_h:
                    beams.append((a, b))
                    continue
            if _other_is_main(beam_solids, el, fr, a, b, warn):
                beams.append((a, b))
    return merged(beams), merged(cols)


def end_supports(doc, beam, fr):
    """Far faces (u) of the supports at each beam end, for bars that run
    'side to side' through the supports. Falls back to the beam ends."""
    bb = beam.get_BoundingBox(None)
    pad = XYZ(50 * MM, 50 * MM, 50 * MM)
    cats = List[BuiltInCategory]([BuiltInCategory.OST_StructuralFraming,
                                  BuiltInCategory.OST_StructuralColumns])
    els = (FilteredElementCollector(doc)
           .WhereElementIsNotElementType()
           .WherePasses(ElementMulticategoryFilter(cats))
           .WherePasses(BoundingBoxIntersectsFilter(Outline(bb.Min - pad, bb.Max + pad))))
    start, end = fr.u0, fr.u1
    for el in els:
        if el.Id == beam.Id:
            continue
        pts = _points(el)
        if not pts:
            continue
        vs = [fr.v(p) for p in pts]
        ws = [p.Z for p in pts]
        if min(vs) > fr.v0 + 5 * MM or max(vs) < fr.v1 - 5 * MM:
            continue
        if max(ws) < fr.w0 + TOL or min(ws) > fr.w1 - TOL:
            continue
        us = [fr.u(p) for p in pts]
        a, b = min(us), max(us)
        if b - a > 2000 * MM:
            continue  # a collinear continuation, not a support
        if a < fr.u0 - TOL and b >= fr.u0 - 5 * MM and b <= fr.u0 + (b - a):
            start = min(start, a)
        if b > fr.u1 + TOL and a <= fr.u1 + 5 * MM and a >= fr.u1 - (b - a):
            end = max(end, b)
    return start, end


# --------------------------------------------------------- splice zones
def parse_zones(text, fr):
    """'2000-3500, 6000-7000' (mm from the beam start face) -> u intervals."""
    out = []
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        a, b = [float(x) for x in part.split("-")]
        out.append((fr.u0 + min(a, b) * MM, fr.u0 + max(a, b) * MM))
    return out


def auto_zones(fr, supports, top):
    """BS practice: top bars lap at midspan (hogging at supports),
    bottom bars lap near / over supports (sagging at midspan)."""
    spans = complement(fr.u0, fr.u1, supports)
    zones = []
    for a, b in spans:
        L = b - a
        if top:
            zones.append((a + L / 3.0, b - L / 3.0))
        else:
            zones.append((a, a + L / 4.0))
            zones.append((b - L / 4.0, b))
    if not top:
        zones.extend(supports)
    return zones


def split_manual(us, ue, leg_s, leg_e, stock, lap, centres, warn):
    """Pieces from fixed splice centres; the lap stays exactly `lap`."""
    cs = sorted(c for c in centres if us + lap / 2.0 < c < ue - lap / 2.0)
    if len(cs) < len(centres):
        warn("a manual splice was outside the bar and was ignored")
    starts = [us] + [c - lap / 2.0 for c in cs]
    ends = [c + lap / 2.0 for c in cs] + [ue]
    pieces = []
    for i, (a, b) in enumerate(zip(starts, ends)):
        first, last = i == 0, i == len(starts) - 1
        length = (b - a) + (leg_s if first else 0) + (leg_e if last else 0)
        if length > stock + TOL:
            warn("bar piece %d is %.0f mm, longer than the %.0f mm stock length"
                 % (i + 1, length / MM, stock / MM))
        pieces.append((a, b, first, last))
    return pieces


def split_run(us, ue, leg_s, leg_e, stock, lap, zones, warn):
    """Split horizontal run [us, ue] into pieces <= stock length.
    Returns list of (start, end, has_start_leg, has_end_leg)."""
    pieces, s, first = [], us, True
    for _ in range(50):
        ls = leg_s if first else 0.0
        if (ue - s) + ls + leg_e <= stock + TOL:
            pieces.append((s, ue, first, True))
            return pieces
        c_max = s + stock - ls - lap / 2.0
        c_min = s + lap / 2.0 + 10 * MM
        if c_max <= c_min:
            raise ValueError("stock length is shorter than the lap length")
        best = None
        for a, b in zones:
            lo, hi = a + lap / 2.0, b - lap / 2.0
            if lo > hi:
                lo = hi = (a + b) / 2.0
            lo, hi = max(lo, c_min), min(hi, c_max)
            if lo <= hi and (best is None or hi > best):
                best = hi
        if best is None:
            best = c_max
            warn("no splice zone reachable within stock length; lap placed at %.0f mm from start"
                 % ((best - us) / MM))
        pieces.append((s, best + lap / 2.0, first, False))
        s, first = best - lap / 2.0, False
    raise ValueError("too many splices")


# ------------------------------------------------------------- creation
def _terminations(doc, hook=None, orient=RebarTerminationOrientation.Left):
    t = BarTerminationsData(doc)
    none = ElementId.InvalidElementId
    hid = hook.Id if hook is not None else none
    t.HookTypeIdAtStart = hid
    t.HookTypeIdAtEnd = hid
    t.EndTreatmentTypeIdAtStart = none
    t.EndTreatmentTypeIdAtEnd = none
    t.CrankTypeIdAtStart = none
    t.CrankTypeIdAtEnd = none
    t.TerminationOrientationAtStart = orient
    t.TerminationOrientationAtEnd = orient
    t.TerminationRotationAngleAtStart = 0.0
    t.TerminationRotationAngleAtEnd = 0.0
    return t


def _err(ex):
    inner = getattr(ex, "clsException", None) or ex
    return "%s: %s" % (type(inner).__name__, getattr(inner, "Message", None) or ex)


def creation_attempts(doc, host, style, bar_type, normal, curves, shape, hook, orient, box):
    """(label, callable) pairs, most exact first."""
    crvs = List[Curve](curves)
    term = lambda: _terminations(doc, hook, orient)
    out = []
    if shape is not None:
        out.append(("CurvesAndShape '%s'" % ename(shape), lambda: Rebar.CreateFromCurvesAndShape(
            doc, shape, bar_type, host, normal, crvs, term())))
    out.append(("Curves (match existing shape)", lambda: Rebar.CreateFromCurves(
        doc, style, bar_type, host, normal, crvs, term(), True, False)))
    out.append(("Curves (allow new shape)", lambda: Rebar.CreateFromCurves(
        doc, style, bar_type, host, normal, crvs, term(), True, True)))
    if shape is not None and box is not None:
        def from_shape():
            r = Rebar.CreateFromRebarShape(doc, shape, bar_type, host, box[0], box[1], box[2])
            if r is not None:
                r.GetShapeDrivenAccessor().ScaleToBox(box[0], box[1], box[2])
            return r
        out.append(("RebarShape + ScaleToBox '%s'" % ename(shape), from_shape))
    return out


def create_rebar(doc, host, style, bar_type, normal, curves, shape=None,
                 hook=None, orient=RebarTerminationOrientation.Left, box=None):
    errors = []
    for label, fn in creation_attempts(doc, host, style, bar_type, normal, curves,
                                       shape, hook, orient, box):
        st = SubTransaction(doc)
        st.Start()
        try:
            r = fn()
            if r is not None:
                st.Commit()
                return r
            errors.append(label + ": returned nothing")
        except Exception as ex:
            errors.append(label + ": " + _err(ex))
        st.RollBack()
    raise ValueError("Revit refused the bar:\n      - " + "\n      - ".join(errors))


def set_layout(rebar, n, length):
    acc = rebar.GetShapeDrivenAccessor()
    if n <= 1 or length <= TOL:
        acc.SetLayoutAsSingle()
    else:
        acc.SetLayoutAsFixedNumber(n, length, True, True, True)


def apply_display(rebar, view, mode):
    if view is None or not rebar.CanApplyPresentationMode(view):
        return
    n = rebar.NumberOfBarPositions
    if mode == "All" or n <= 3:
        rebar.SetPresentationMode(view, RebarPresentationMode.All)
        return
    m = n // 2
    show = {0, m, n - 1} if mode == "FirstMidLast" else {m - 1, m, m + 1}
    for i in range(n):
        rebar.SetBarHiddenStatus(view, i, i not in show)


def _mark(el, layer):
    _set_data(el, _AUTO_MARK + "|" + layer)


def delete_auto_rebar(doc, beam):
    ids = [r.Id for r in RebarHostData.GetRebarHostData(beam).GetRebarsInHost()
           if is_auto_rebar(r)]
    if ids:
        doc.Delete(List[ElementId](ids))
    return len(ids)


def _long_bars(doc, beam, fr, s, top, supports, made, warn):
    bt = by_name(doc, RebarBarType, s["top_type" if top else "bot_type"])
    n = int(s["top_n" if top else "bot_n"])
    if bt is None or n <= 0:
        return
    d = bt.BarModelDiameter
    dl = 0.0
    lt = by_name(doc, RebarBarType, s["link_type"])
    if lt is not None:
        dl = lt.BarModelDiameter

    cs = s["cover_side"] * MM
    if top:
        w = fr.w1 - s["cover_top"] * MM - dl - d / 2.0
        sign = -1.0
    else:
        w = fr.w0 + s["cover_bottom"] * MM + dl + d / 2.0
        sign = 1.0
    va = fr.v0 + cs + dl + d / 2.0
    vb = fr.v1 - cs - dl - d / 2.0
    if n == 1:
        va = vb = (fr.v0 + fr.v1) / 2.0

    ext = s["end_ext"] * MM
    if s.get("full_length"):
        fa, fb = end_supports(doc, beam, fr)
        ce = s["cover_end"] * MM
        us, ue = fa + ce + d / 2.0, fb - ce - d / 2.0
    elif ext > TOL:
        us, ue = fr.u0 - ext + d / 2.0, fr.u1 + ext - d / 2.0
    else:
        ce = s["cover_end"] * MM
        us, ue = fr.u0 + ce + d / 2.0, fr.u1 - ce - d / 2.0

    max_leg = (fr.w1 - fr.w0) - s["cover_top"] * MM - s["cover_bottom"] * MM - 2 * dl - d
    legs = []
    for key in ("A", "C"):
        L = s[("top_" if top else "bot_") + key] * MM
        if L > TOL:
            L = L - d / 2.0  # BS 8666 dims are outside dims
            if L > max_leg:
                warn("%s leg %s clipped to fit the beam depth" % ("top" if top else "bottom", key))
                L = max_leg
        legs.append(max(L, 0.0))
    leg_s, leg_e = legs

    lap = s["lap_factor"] * bt.BarNominalDiameter
    zone_text = s["top_zones" if top else "bot_zones"].strip()
    zones = parse_zones(zone_text, fr) if zone_text else auto_zones(fr, supports, top)
    manual = s.get("top_splices" if top else "bot_splices")
    if manual is not None:
        pieces = split_manual(us, ue, leg_s, leg_e, s["stock"] * MM, lap,
                              [fr.u0 + c * MM for c in manual], warn)
    else:
        pieces = split_run(us, ue, leg_s, leg_e, s["stock"] * MM, lap, zones, warn)
    s[("top" if top else "bot") + "_splices_at"] = [
        round((b - lap / 2.0 - fr.u0) / MM, 1) for a, b, _, last in pieces if not last]

    shapes = {
        2: by_name(doc, RebarShape, "21"),
        1: by_name(doc, RebarShape, "11"),
        0: by_name(doc, RebarShape, "00"),
    }
    for a, b, has_s, has_e in pieces:
        curves = []
        p = lambda u, ww: fr.pt(u, va, ww)
        if has_s and leg_s > TOL:
            curves.append(Line.CreateBound(p(a, w + sign * leg_s), p(a, w)))
        curves.append(Line.CreateBound(p(a, w), p(b, w)))
        if has_e and leg_e > TOL:
            curves.append(Line.CreateBound(p(b, w), p(b, w + sign * leg_e)))
        shape = shapes.get(len(curves) - 1)
        leg = leg_s if (has_s and leg_s > TOL) else leg_e
        box = None
        if leg > TOL:
            box = (p(a, w), fr.X * (b - a), XYZ.BasisZ * (sign * leg))
        r = create_rebar(doc, beam, RebarStyle.Standard, bt, fr.Y, curves, shape, box=box)
        set_layout(r, n, vb - va)
        _mark(r, "top" if top else "bot")
        made.append(r)


def _links(doc, beam, fr, s, beam_j, col_j, view, made, warn):
    lt = by_name(doc, RebarBarType, s["link_type"])
    if lt is None:
        warn("link bar type '%s' not found" % s["link_type"])
        return
    dl = lt.BarModelDiameter
    hook = by_name(doc, RebarHookType, s["link_hook"]) if s["link_hook"] else None
    orient = (RebarTerminationOrientation.Right if s["link_flip"]
              else RebarTerminationOrientation.Left)

    va = fr.v0 + s["cover_side"] * MM + dl / 2.0
    vb = fr.v1 - s["cover_side"] * MM - dl / 2.0
    wa = fr.w0 + s["cover_bottom"] * MM + dl / 2.0
    wb = fr.w1 - s["cover_top"] * MM - dl / 2.0

    skip = []
    if not s["primary"]:
        skip.extend(beam_j)
    if s["stop_cols"]:
        skip.extend(col_j)
    off = s["link_offset"] * MM
    spacing = s["link_spacing"] * MM
    shape51 = by_name(doc, RebarShape, "51")

    for a, b in complement(fr.u0, fr.u1, skip):
        u, length = a + off, (b - a) - 2 * off
        if length < 0:
            continue
        # closed loop, counter-clockwise seen from +u, starting top-left
        loop = [fr.pt(u, va, wb), fr.pt(u, va, wa), fr.pt(u, vb, wa),
                fr.pt(u, vb, wb), fr.pt(u, va, wb)]
        curves = [Line.CreateBound(loop[i], loop[i + 1]) for i in range(4)]
        box = (fr.pt(u, va, wa), fr.Y * (vb - va), XYZ.BasisZ * (wb - wa))
        r = create_rebar(doc, beam, RebarStyle.StirrupTie, lt, fr.X, curves,
                         shape51, hook, orient, box)
        acc = r.GetShapeDrivenAccessor()
        if length <= TOL:
            acc.SetLayoutAsSingle()
        else:
            acc.SetLayoutAsMaximumSpacing(spacing, length, True, True, True)
        _mark(r, "link")
        apply_display(r, view, s["display"])
        made.append(r)


def build(doc, beam, s, view=None):
    """Delete previous auto bars of this beam and rebuild. Must run
    inside a transaction. Returns (bars_created, bars_deleted, warnings)."""
    warnings = []
    warn = warnings.append
    if not RebarHostData.IsValidHost(beam):
        raise ValueError("not a valid rebar host (is its structural material concrete?)")
    fr = BeamFrame(beam)
    beam_j, col_j = junctions(doc, beam, fr, warn, s.get("link_priority", "auto"))
    supports = merged(beam_j + col_j)

    deleted = delete_auto_rebar(doc, beam)
    s = dict(s)
    made = []
    _long_bars(doc, beam, fr, s, True, supports, made, warn)
    _long_bars(doc, beam, fr, s, False, supports, made, warn)
    if s["links_on"]:
        _links(doc, beam, fr, s, beam_j, col_j, view, made, warn)
    _set_data(beam, json.dumps(s, sort_keys=True))
    return len(made), deleted, warnings
