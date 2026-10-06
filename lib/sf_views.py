# -*- coding: utf-8 -*-
"""StructFlow beam views: long section (elevation) + cross sections at
start / mid / end of every span, with scale, view template, tags,
multi-rebar annotations, lap dimensions and labels chosen per element.
Settings are saved as named presets."""
import json
import os

from System.Collections.Generic import List
from Autodesk.Revit.DB import (
    BoundingBoxXYZ, BuiltInCategory, BuiltInParameter, DimensionStyleType,
    DimensionType, ElementId, ElementTypeGroup, FamilySymbol,
    FilteredElementCollector, GeometryInstance, Grid, IndependentTag, Line,
    MultiReferenceAnnotation, MultiReferenceAnnotationOptions,
    MultiReferenceAnnotationType, Options, Reference, ReferenceArray,
    SubTransaction, TagOrientation, TextNote, TextNoteType, Transform, View,
    ViewDetailLevel, ViewFamily, ViewFamilyType, ViewSection, ViewType, XYZ,
)
from Autodesk.Revit.DB.Structure import RebarBarType, RebarHostData, RebarStyle

import sf_beamrebar as br

MM = br.MM
PRESETS = os.path.join(os.environ["APPDATA"], "pyRevit", "StructFlow_view_presets.json")
_VIEW_MARK = "SF_AUTO_VIEW:"
_NOTE_MARK = "SF_AUTO_NOTE:"

LINK_MODES = [
    ("Middle3", "3 links in a clear spot (no lap, no crossing beam)"),
    ("FirstMidLast", "First / clear middle / last"),
    ("FirstLast", "First and last"),
    ("All", "All links"),
]

DEFAULTS = {
    # views
    "section_type": "", "make_elev": True,
    # section line / crop: how far past the beam (model mm); room for tags (paper mm)
    "mark_ext": 100.0, "anno_space": 30.0,
    "template_elev": "", "scale_elev": 50, "elev_name": "{L}-{L}", "raise_elev": 30,
    "sec_start": True, "sec_mid": True, "sec_end": True, "per_span": True,
    "sec_offset": 300.0, "sec_depth": 200.0,
    "template_section": "", "scale_section": 20, "sec_name": "{L}{n}-{L}{n}", "raise_sec": 30,
    "replace_old": True,
    # rebar display
    "elev_links": "Middle3", "other_main": False, "other_links": False,
    "unobscure": True, "fine": True,
    # tags and dimensions
    "beam_tag": "", "bar_tag": "", "link_tag": "", "tag_leader": True,
    "link_mra": True, "mra_type": "",
    "lap_dims": True, "lap_dim_type": "", "lap_suffix": " (overlap)",
    "grid_dims": True, "depth_dim": True,
    # labels
    "label_plan": True, "label_type": "", "avoid_clash": True,
}


# ---------------------------------------------------------------- presets
def load_presets():
    try:
        with open(PRESETS) as f:
            return json.load(f)
    except Exception:
        return {}


def _write_presets(data):
    with open(PRESETS, "w") as f:
        json.dump(data, f, indent=1, sort_keys=True)


def save_preset(name, settings):
    data = load_presets()
    data[name] = settings
    _write_presets(data)


def delete_preset(name):
    data = load_presets()
    data.pop(name, None)
    _write_presets(data)


def preset(name):
    s = dict(DEFAULTS)
    s.update(load_presets().get(name, {}))
    # setups saved before the {L} code existed get the A-A / A1-A1 scheme
    for key in ("elev_name", "sec_name"):
        if "{L}" not in s[key]:
            s[key] = DEFAULTS[key]
    return s


# --------------------------------------------------------------- lookups
def section_types(doc):
    return dict((br.ename(t), t) for t in FilteredElementCollector(doc).OfClass(ViewFamilyType)
                if t.ViewFamily == ViewFamily.Section)


def section_templates(doc):
    return dict((v.Name, v) for v in FilteredElementCollector(doc).OfClass(View)
                if v.IsTemplate and v.ViewType == ViewType.Section)


def tag_types(doc, bic):
    return dict(("%s : %s" % (s.FamilyName, br.ename(s)), s)
                for s in FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(bic))


def text_types(doc):
    return dict((br.ename(t), t) for t in FilteredElementCollector(doc).OfClass(TextNoteType))


def linear_dim_types(doc):
    out = {}
    for t in FilteredElementCollector(doc).OfClass(DimensionType):
        try:
            if t.StyleType == DimensionStyleType.Linear and br.ename(t):
                out[br.ename(t)] = t
        except Exception:
            pass
    return out


def mra_types(doc):
    return dict((br.ename(t), t) for t in FilteredElementCollector(doc).OfClass(MultiReferenceAnnotationType))


def resolve(doc, s):
    """Settings names -> elements, once per run."""
    tags_f = tag_types(doc, BuiltInCategory.OST_StructuralFramingTags)
    tags_r = tag_types(doc, BuiltInCategory.OST_RebarTags)
    temps = section_templates(doc)
    texts = text_types(doc)
    default_text = doc.GetDefaultElementTypeId(ElementTypeGroup.TextNoteType)
    pick_text = lambda name: texts[name].Id if name in texts else default_text
    return {
        "vft": section_types(doc)[s["section_type"]],
        "t_elev": temps.get(s["template_elev"]),
        "t_sec": temps.get(s["template_section"]),
        "beam_tag": tags_f.get(s["beam_tag"]),
        "bar_tag": tags_r.get(s["bar_tag"]),
        "link_tag": tags_r.get(s["link_tag"]),
        "mra": mra_types(doc).get(s["mra_type"]) if s["link_mra"] else None,
        "lap_dim": linear_dim_types(doc).get(s["lap_dim_type"]),
        "label_text": pick_text(s["label_type"]),
    }


# ----------------------------------------------------------------- views
def _set_name(view, name):
    """Revit refuses duplicate view names; add (2), (3)... until it accepts."""
    for i in range(1, 200):
        try:
            view.Name = name if i == 1 else "%s (%d)" % (name, i)
            return
        except Exception:
            continue
    raise ValueError("could not find a free name for view '%s'" % name)


def _sf_views(doc):
    """{beam UniqueId: [letter, [view ids]]} for views StructFlow made."""
    out = {}
    for v in FilteredElementCollector(doc).OfClass(ViewSection):
        if v.IsTemplate:
            continue
        data = br._get_data(v) or ""
        if not data.startswith(_VIEW_MARK):
            continue
        uid, _, letter = data[len(_VIEW_MARK):].partition("|")
        entry = out.setdefault(uid, [letter, []])
        entry[0] = entry[0] or letter
        entry[1].append(v.Id)
    return out


def _letters(i):
    """0 -> A ... 25 -> Z, 26 -> AA ..."""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def assign_letters(doc, beams):
    """Beam letters for {L}: a beam keeps the letter it had before; new
    beams get the next free letters, ordered top-to-bottom, left-to-right."""
    existing = _sf_views(doc)
    used = set(l for l, _ in existing.values() if l)
    out = {}

    def key(b):
        bb = b.get_BoundingBox(None)
        return (-round((bb.Min.Y + bb.Max.Y) / 2.0, 1), (bb.Min.X + bb.Max.X) / 2.0)

    i = 0
    for b in sorted(beams, key=key):
        old = existing.get(b.UniqueId, [""])[0]
        if old:
            out[b.Id] = old
            continue
        while _letters(i) in used:
            i += 1
        out[b.Id] = _letters(i)
        used.add(out[b.Id])
    return out


def delete_old_views(doc, beam):
    ids = list(_sf_views(doc).get(beam.UniqueId, ["", []])[1])
    key = _NOTE_MARK + beam.UniqueId
    ids += [n.Id for n in FilteredElementCollector(doc).OfClass(TextNote)
            if br._get_data(n) == key]
    if ids:
        doc.Delete(List[ElementId](ids))
    return len(ids)


def make_section(doc, beam, vft, origin, bx, bz, half_w, half_h, depth,
                 name, scale, template, fine, letter, anno, anno_top):
    """Section box: cut plane at origin, looking along -bz, far clip at depth.
    The crop hugs the beam (short section lines in other views); tags live
    in the annotation crop, `anno` on paper around it, `anno_top` above."""
    t = Transform.Identity
    t.Origin = origin
    t.BasisX = bx
    t.BasisY = XYZ.BasisZ
    t.BasisZ = bz
    box = BoundingBoxXYZ()
    box.Transform = t
    box.Min = XYZ(-half_w, -half_h, -depth)
    box.Max = XYZ(half_w, half_h, 0)
    v = ViewSection.CreateSection(doc, vft.Id, box)
    _set_name(v, name)
    try:
        v.Scale = int(scale)
    except Exception:
        pass
    if fine and v.CanModifyDetailLevel():
        v.DetailLevel = ViewDetailLevel.Fine
    if template is not None:
        v.ViewTemplateId = template.Id
    v.CropBoxActive = True
    _annotation_crop(doc, v, origin.Z + half_h, anno, anno_top)
    br._set_data(v, _VIEW_MARK + beam.UniqueId + "|" + letter)
    return v


def _annotation_crop(doc, v, crop_top_z, anno, anno_top):
    """Turn on the annotation crop and size it. Revit's offsets are paper
    distances; if this version reads them as model distances, rescale."""
    try:
        p = v.get_Parameter(BuiltInParameter.VIEWER_ANNOTATION_CROP_ACTIVE)
        if p is not None and not p.IsReadOnly:
            p.Set(1)
        mgr = v.GetCropRegionShapeManager()
        if not mgr.CanHaveAnnotationCrop:
            return

        def apply(k):
            mgr.LeftAnnotationCropOffset = anno * k
            mgr.RightAnnotationCropOffset = anno * k
            mgr.BottomAnnotationCropOffset = anno * k
            mgr.TopAnnotationCropOffset = anno_top * k

        apply(1.0)
        doc.Regenerate()
        top = max(pt.Z for c in mgr.GetAnnotationCropShape() for pt in (c.GetEndPoint(0), c.GetEndPoint(1)))
        got = top - crop_top_z  # model distance actually obtained
        if abs(got - anno_top) < abs(got - anno_top * v.Scale):
            apply(float(v.Scale))
    except Exception:
        pass


def _mark_of(beam):
    p = beam.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
    m = p.AsString() if p else None
    return m or ("B%s" % beam.Id)


def _fmt(pattern, beam, L, letter="", n=0):
    return (pattern.replace("{mark}", _mark_of(beam))
            .replace("{type}", br.ename(beam))
            .replace("{L}", L)
            .replace("{letter}", letter).replace("{n}", str(n)))


def _priority(beam):
    stored = br.load_beam_settings(beam)
    return stored["link_priority"] if stored else "auto"


def section_positions(doc, beam, fr, s, supports):
    spans = br.complement(fr.u0, fr.u1, supports) if s["per_span"] else [(fr.u0, fr.u1)]
    off = s["sec_offset"] * MM
    out = []
    for a, b in spans:
        if s["sec_start"]:
            out.append(min(a + off, (a + b) / 2.0))
        if s["sec_mid"]:
            out.append((a + b) / 2.0)
        if s["sec_end"]:
            out.append(max(b - off, (a + b) / 2.0))
    uniq = []
    for u in sorted(out):
        if not uniq or u - uniq[-1] > 50 * MM:
            uniq.append(u)
    return uniq


# ------------------------------------------------------------ beam rebar
class BarInfo(object):
    def __init__(self, rebar, kind, a, b):
        self.r, self.kind, self.a, self.b = rebar, kind, a, b


def _rebars(doc, beam, fr):
    """Bars hosted by this beam with their kind (top / bot / link) and u-range."""
    wm = (fr.w0 + fr.w1) / 2.0
    out = []
    for r in RebarHostData.GetRebarHostData(beam).GetRebarsInHost():
        bb = r.get_BoundingBox(None)
        if bb is None:
            continue
        kind = br.rebar_layer(r)
        if not kind:
            shape = doc.GetElement(r.GetShapeId())
            if shape is not None and shape.RebarStyle == RebarStyle.StirrupTie:
                kind = "link"
            else:
                kind = "top" if (bb.Min.Z + bb.Max.Z) / 2.0 > wm else "bot"
        us = [fr.u(bb.Min), fr.u(bb.Max)]
        out.append(BarInfo(r, kind, min(us), max(us)))
    return out


def _lap_zones(doc, beam, fr):
    """u-intervals occupied by laps, from the settings stored by Beam Rebar."""
    st = br.load_beam_settings(beam)
    if not st:
        return []
    zones = []
    for layer in ("top", "bot"):
        bt = br.by_name(doc, RebarBarType, st[layer + "_type"])
        if bt is None:
            continue
        lap = st["lap_factor"] * bt.BarNominalDiameter
        for c in st.get(layer + "_splices_at") or []:
            u = fr.u0 + c * MM
            zones.append((u - lap / 2.0, u + lap / 2.0))
    return zones


def clear_point(a, b, blocked, trim=0.1):
    """Middle of the longest stretch of [a, b] free of the blocked intervals,
    keeping away from the ends by `trim` of the length."""
    lo, hi = a + (b - a) * trim, b - (b - a) * trim
    free = br.complement(lo, hi, blocked) or [(lo, hi)]
    s, e = max(free, key=lambda f: f[1] - f[0])
    return (s + e) / 2.0


def show_links_at(rebar, view, mode, u_clear, a, b):
    """Link set display in this view, centred on a clear spot."""
    if not rebar.CanApplyPresentationMode(view):
        return
    n = rebar.NumberOfBarPositions
    if mode == "All" or n <= 3:
        br.apply_display(rebar, view, "All")
        return
    m = int(round((u_clear - a) / (b - a) * (n - 1))) if b > a else n // 2
    m = max(1, min(n - 2, m))
    show = {"Middle3": {m - 1, m, m + 1}, "FirstMidLast": {0, m, n - 1},
            "FirstLast": {0, n - 1}}.get(mode, set(range(n)))
    for i in range(n):
        rebar.SetBarHiddenStatus(view, i, i not in show)


# ----------------------------------------------------------- annotations
def _bar_references(el, view):
    """References to individual bars as seen in the view."""
    opt = Options()
    opt.View = view
    opt.ComputeReferences = True
    refs = []

    def walk(geo):
        for g in geo:
            if isinstance(g, GeometryInstance):
                walk(g.GetInstanceGeometry())
            elif getattr(g, "Reference", None) is not None:
                refs.append(g.Reference)

    geo = el.get_Geometry(opt)
    if geo is not None:
        walk(geo)
    return refs


def _view_lines(el, view):
    opt = Options()
    opt.View = view
    opt.ComputeReferences = True
    out = []

    def walk(geo):
        for g in geo:
            if isinstance(g, GeometryInstance):
                walk(g.GetInstanceGeometry())
            elif isinstance(g, Line):
                out.append(g)

    geo = el.get_Geometry(opt)
    if geo is not None:
        walk(geo)
    return out


def _tag(doc, view, el, sym, pt, leader, warn):
    if sym is None:
        return
    err = None
    for ref in [Reference(el)] + _bar_references(el, view)[:20]:
        st = SubTransaction(doc)
        st.Start()
        try:
            IndependentTag.Create(doc, sym.Id, view.Id, ref, leader, TagOrientation.Horizontal, pt)
            st.Commit()
            return
        except Exception as ex:
            err = ex
            st.RollBack()
    visible = el.Id in [e.Id for e in FilteredElementCollector(doc, view.Id).OfCategoryId(el.Category.Id)]
    warn("could not tag %s in '%s' (visible in view: %s): %s"
         % (el.Id, view.Name, visible, br._err(err)))


def _mra(doc, view, rebar, mra_type, fr, line_pt, head_pt, warn):
    """Multi-rebar annotation on a link set: spacing dimension + one tag."""
    try:
        opts = MultiReferenceAnnotationOptions(mra_type)
        opts.SetElementsToDimension(List[ElementId]([rebar.Id]))
        opts.DimensionLineOrigin = line_pt
        opts.DimensionLineDirection = fr.X
        opts.DimensionPlaneNormal = view.ViewDirection
        opts.TagHeadPosition = head_pt
        opts.TagHasLeader = True
        MultiReferenceAnnotation.Create(doc, view.Id, opts)
        return True
    except Exception as ex:
        warn("multi-rebar annotation failed in '%s': %s" % (view.Name, br._err(ex)))
        return False


def _lap_dims(doc, view, fr, vm, bars, dim_type, suffix, paper, warn):
    """One dimension per lap, between the two bar ends that overlap."""
    for kind in ("top", "bot"):
        pieces = sorted([b for b in bars if b.kind == kind], key=lambda b: b.a)
        for p, q in zip(pieces, pieces[1:]):
            if q.a >= p.b:
                continue  # not overlapping
            ends = []
            for bar, target in ((q, q.a), (p, p.b)):
                best = None
                for ln in _view_lines(bar.r, view):
                    if abs(ln.Direction.DotProduct(fr.X)) < 0.99:
                        continue  # only the horizontal run
                    for i in (0, 1):
                        d = abs(fr.u(ln.GetEndPoint(i)) - target)
                        if best is None or d < best[0]:
                            best = (d, ln.GetEndPointReference(i), ln.GetEndPoint(i))
                if best is None or best[0] > 60 * MM or best[1] is None:
                    break
                ends.append(best)
            if len(ends) != 2:
                warn("could not find the bar ends for a %s lap in '%s'"
                     % ("top" if kind == "top" else "bottom", view.Name))
                continue
            z = ends[0][2].Z + (paper(5) if kind == "bot" else -paper(5))
            line = Line.CreateBound(fr.pt(fr.u(ends[0][2]), vm, z), fr.pt(fr.u(ends[1][2]), vm, z))
            refs = ReferenceArray()
            refs.Append(ends[0][1])
            refs.Append(ends[1][1])
            try:
                dim = (doc.Create.NewDimension(view, line, refs, dim_type) if dim_type
                       else doc.Create.NewDimension(view, line, refs))
                if suffix:
                    dim.Suffix = suffix
            except Exception as ex:
                warn("could not dimension a lap in '%s': %s" % (view.Name, br._err(ex)))


def _hide_other_beams(doc, view, own_ids, s):
    """Hide main bars / links of other beams that show up in this view."""
    if s["other_main"] and s["other_links"]:
        return
    hide = []
    for r in (FilteredElementCollector(doc, view.Id)
              .OfCategory(BuiltInCategory.OST_Rebar).WhereElementIsNotElementType()):
        if r.Id in own_ids or not r.CanBeHidden(view):
            continue
        shape = doc.GetElement(r.GetShapeId()) if hasattr(r, "GetShapeId") else None
        is_link = shape is not None and shape.RebarStyle == RebarStyle.StirrupTie
        if (is_link and not s["other_links"]) or (not is_link and not s["other_main"]):
            hide.append(r.Id)
    if hide:
        view.HideElements(List[ElementId](hide))


def grid_hits(doc, fr, lo, hi):
    """[(u, grid)] for straight grids crossing the beam line between lo and hi."""
    hits = []
    for g in FilteredElementCollector(doc).OfClass(Grid):
        c = g.Curve
        if not isinstance(c, Line):
            continue
        p, d = c.GetEndPoint(0), c.Direction
        den = fr.X.X * d.Y - fr.X.Y * d.X
        if abs(den) < 1e-6:
            continue  # parallel to the beam
        t = ((p.X - fr.o.X) * d.Y - (p.Y - fr.o.Y) * d.X) / den
        if lo <= t <= hi:
            hits.append((t, g))
    return sorted(hits, key=lambda h: h[0])


def _grid_dims(doc, view, fr, vm, w, half_len, warn):
    """Dimension string between the grids that cross this long section."""
    um = (fr.u0 + fr.u1) / 2.0
    hits = grid_hits(doc, fr, um - half_len, um + half_len)
    if len(hits) < 2:
        return
    refs = ReferenceArray()
    for _, g in hits:
        refs.Append(Reference(g))
    line = Line.CreateBound(fr.pt(hits[0][0], vm, w), fr.pt(hits[-1][0], vm, w))
    try:
        doc.Create.NewDimension(view, line, refs)
    except Exception as ex:
        warn("could not dimension grids in '%s': %s" % (view.Name, br._err(ex)))


def _depth_dim(doc, view, beam, fr, u, v_line, warn):
    """Beam depth dimension (top face to bottom face) beside a cross section."""
    opt = Options()
    opt.View = view
    opt.ComputeReferences = True
    top = bot = None
    for solid in br._solids_with(beam, opt):
        for f in solid.Faces:
            n = getattr(f, "FaceNormal", None)
            if n is None or f.Reference is None:
                continue
            if n.Z > 0.99 and (top is None or f.Origin.Z > top[1]):
                top = (f.Reference, f.Origin.Z)
            elif n.Z < -0.99 and (bot is None or f.Origin.Z < bot[1]):
                bot = (f.Reference, f.Origin.Z)
    if top is None or bot is None:
        warn("could not find the beam top/bottom faces in '%s'" % view.Name)
        return
    refs = ReferenceArray()
    refs.Append(top[0])
    refs.Append(bot[0])
    try:
        doc.Create.NewDimension(view, Line.CreateBound(fr.pt(u, v_line, bot[1]), fr.pt(u, v_line, top[1])), refs)
    except Exception as ex:
        warn("could not dimension the beam depth in '%s': %s" % (view.Name, br._err(ex)))


def _multi_tag(doc, view, el, sym, head, warn):
    """One tag with a leader to every bar of the set (as seen in the view)."""
    if sym is None:
        return
    st = SubTransaction(doc)
    st.Start()
    try:
        tag = IndependentTag.Create(doc, sym.Id, view.Id, Reference(el), True,
                                    TagOrientation.Horizontal, head)
        seen = set()
        extra = []
        for ref in _bar_references(el, view):
            key = ref.ConvertToStableRepresentation(doc)
            if key not in seen:
                seen.add(key)
                extra.append(ref)
        if len(extra) > 1:
            try:
                tag.AddReferences(List[Reference](extra))
            except Exception:
                pass  # single leader is still fine
        st.Commit()
    except Exception:
        st.RollBack()
        _tag(doc, view, el, sym, head, True, warn)


def _note(doc, view, pt, text, type_id, beam=None):
    n = TextNote.Create(doc, view.Id, pt, text, type_id)
    if beam is not None:
        br._set_data(n, _NOTE_MARK + beam.UniqueId)
    return n


# ------------------------------------------------- plan markers and labels
def new_context(doc, plan):
    """Shared state for one run: where section heads already sit in plan."""
    scale = plan.Scale if plan is not None else 100
    return {
        "plan": plan,
        "markers": [],
        "clear": 12 * scale * MM,  # 12 mm on paper between heads
        "paper": lambda mm: mm * scale * MM,
    }


def _fit(ctx, s, base, heads):
    """Smallest crop margin >= base whose section heads keep clear of all
    heads placed so far. Only the white space around the view changes."""
    flat = lambda p: (p.X, p.Y)
    chosen = base
    if s["avoid_clash"]:
        for k in range(16):
            m = base + k * ctx["clear"] * 0.5
            pts = [flat(p) for p in heads(m)]
            if all((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 >= ctx["clear"] ** 2
                   for a in pts for b in ctx["markers"]):
                chosen = m
                break
    ctx["markers"].extend(flat(p) for p in heads(chosen))
    return chosen


def _plan_label(doc, beam, ctx, s, look, view, head, outward, warn):
    if not (s["label_plan"] and ctx["plan"] is not None):
        return
    try:
        plan = ctx["plan"]
        pt = head + outward * ctx["paper"](6)
        z = plan.GenLevel.Elevation if plan.GenLevel is not None else 0.0
        _note(doc, plan, XYZ(pt.X, pt.Y, z), view.Name, look["label_text"], beam)
        ctx["markers"].append((pt.X, pt.Y))
    except Exception as ex:
        warn("could not label '%s' in the plan: %s" % (view.Name, br._err(ex)))


# ------------------------------------------------------------------ main
def build_views(doc, beam, s, look, warn, L="A", ctx=None):
    """Create the long section and cross sections of one beam.
    Returns the list of created views."""
    if s["replace_old"]:
        delete_old_views(doc, beam)
    ctx = ctx or new_context(doc, None)
    fr = br.BeamFrame(beam)
    bars = _rebars(doc, beam, fr)
    own = set(b.r.Id for b in bars)
    bj, cj = br.junctions(doc, beam, fr, warn, _priority(beam))
    supports = br.merged(bj + cj)
    laps = _lap_zones(doc, beam, fr)

    vm, wm = (fr.v0 + fr.v1) / 2.0, (fr.w0 + fr.w1) / 2.0
    um = (fr.u0 + fr.u1) / 2.0
    ext = s["mark_ext"] * MM
    half_h = (fr.w1 - fr.w0) / 2.0 + ext
    half_b = (fr.v1 - fr.v0) / 2.0
    anno = s["anno_space"] * MM  # paper
    views = []
    cuts = section_positions(doc, beam, fr, s, supports)

    # ---- long section
    if s["make_elev"]:
        sc = int(s["scale_elev"])
        paper = lambda mm: mm * sc * MM
        half_l = (fr.u1 - fr.u0) / 2.0
        anno_top = anno + (2 * half_h / sc) * s["raise_elev"] / 100.0
        m = _fit(ctx, s, ext, lambda m: [fr.pt(um - half_l - m, vm, 0), fr.pt(um + half_l + m, vm, 0)])
        v = make_section(doc, beam, look["vft"], fr.pt(um, vm, wm), fr.X, -fr.Y,
                         half_l + m, half_h, half_b + 50 * MM,
                         _fmt(s["elev_name"], beam, L), sc, look["t_elev"], s["fine"], L,
                         anno, anno_top)
        doc.Regenerate()
        _plan_label(doc, beam, ctx, s, look, v, fr.pt(um + half_l + m, vm, 0), fr.X, warn)
        _hide_other_beams(doc, v, own, s)
        if s["unobscure"]:
            for b in bars:
                b.r.SetUnobscuredInView(v, True)
        if s["grid_dims"]:
            _grid_dims(doc, v, fr, vm, fr.w1 + paper(30), half_l + m, warn)
        _tag(doc, v, beam, look["beam_tag"], fr.pt(um, vm, fr.w1 + paper(24)), False, warn)

        # things the eye already has to read: keep tags and the 3 links away
        room = paper(12)
        busy = list(supports) + list(laps)
        busy += [(g - room, g + room) for g, _ in grid_hits(doc, fr, fr.u0, fr.u1)]
        busy += [(c - room, c + room) for c in cuts]
        busy.append((um - paper(20), um + paper(20)))  # beam tag

        # one simple tag per main bar piece
        for b in bars:
            if b.kind == "link":
                continue
            others = [(o.a, o.b) for o in bars if o.kind == b.kind and o is not b]
            u = clear_point(b.a, b.b, others + busy, trim=0.05)
            z = fr.w1 + paper(7) if b.kind == "top" else fr.w0 - paper(7)
            _tag(doc, v, b.r, look["bar_tag"], fr.pt(u, vm, z), s["tag_leader"], warn)
            busy.append((u - room, u + room))

        # links: shown at a clear spot, multi-rebar annotation above the bar tag
        for b in bars:
            if b.kind != "link":
                continue
            u = clear_point(b.a, b.b, busy)
            show_links_at(b.r, v, s["elev_links"], u, b.a, b.b)
            done = False
            if look["mra"] is not None:
                done = _mra(doc, v, b.r, look["mra"], fr, fr.pt(u, vm, fr.w1 + paper(13)),
                            fr.pt(u, vm, fr.w1 + paper(17)), warn)
            if not done:
                _tag(doc, v, b.r, look["link_tag"], fr.pt(u, vm, fr.w1 + paper(15)),
                     s["tag_leader"], warn)

        if s["lap_dims"]:
            _lap_dims(doc, v, fr, vm, bars, look["lap_dim"], s["lap_suffix"], paper, warn)
        views.append(v)

    # ---- cross sections, looking from the beam start toward its end
    sc = int(s["scale_section"])
    paper = lambda mm: mm * sc * MM
    anno_top = anno + (2 * half_h / sc) * s["raise_sec"] / 100.0
    bz = -fr.X
    bx = XYZ.BasisZ.CrossProduct(bz)  # view right = -v, so +v is the left of the view
    left, right = fr.v1, fr.v0
    for i, u in enumerate(cuts):
        letter = chr(ord("A") + i) if i < 26 else str(i + 1)
        m = _fit(ctx, s, ext, lambda m: [fr.pt(u, vm - half_b - m, 0), fr.pt(u, vm + half_b + m, 0)])
        v = make_section(doc, beam, look["vft"], fr.pt(u, vm, wm), bx, bz, half_b + m, half_h,
                         s["sec_depth"] * MM, _fmt(s["sec_name"], beam, L, letter, i + 1),
                         sc, look["t_sec"], s["fine"], L, anno, anno_top)
        doc.Regenerate()
        _plan_label(doc, beam, ctx, s, look, v, fr.pt(u, vm + half_b + m, 0), fr.Y, warn)
        _hide_other_beams(doc, v, own, s)
        if s["unobscure"]:
            for b in bars:
                b.r.SetUnobscuredInView(v, True)
        k = {"top": 0, "bot": 0}
        for b in bars:
            if not (b.a - 1 * MM <= u <= b.b + 1 * MM):
                continue
            if b.kind == "link":
                # tag on the left, leader to the link at mid height
                _tag(doc, v, b.r, look["link_tag"], fr.pt(u, left + paper(14), wm), True, warn)
                continue
            k[b.kind] += 1
            # one tag per bar set, top-left above / bottom-left below, leaders to every bar
            z = (fr.w1 + paper(7 + 6 * (k[b.kind] - 1)) if b.kind == "top"
                 else fr.w0 - paper(7 + 6 * (k[b.kind] - 1)))
            _multi_tag(doc, v, b.r, look["bar_tag"], fr.pt(u, left + paper(4), z), warn)
        if s["depth_dim"]:
            _depth_dim(doc, v, beam, fr, u, right - paper(8), warn)
        views.append(v)
    return views
