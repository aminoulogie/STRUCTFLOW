# -*- coding: utf-8 -*-
"""StructFlow beam views: long section (elevation) + cross sections at
start / mid / end of every span, with scale, view template and tags
chosen per element type. Settings are saved as named presets."""
import json
import os

from System.Collections.Generic import List
from Autodesk.Revit.DB import (
    BoundingBoxXYZ, BuiltInCategory, BuiltInParameter, ElementId,
    FamilySymbol, FilteredElementCollector, IndependentTag, Reference,
    TagOrientation, Transform, View, ViewDetailLevel, ViewFamily,
    ViewFamilyType, ViewSection, ViewType, XYZ, GeometryInstance, Options,
    SubTransaction,
)
from Autodesk.Revit.DB.Structure import RebarHostData, RebarShape, RebarStyle

import sf_beamrebar as br

MM = br.MM
PRESETS = os.path.join(os.environ["APPDATA"], "pyRevit", "StructFlow_view_presets.json")
_VIEW_MARK = "SF_AUTO_VIEW:"

DEFAULTS = {
    "section_type": "", "make_elev": True,
    "template_elev": "", "scale_elev": 50, "elev_name": "{L}-{L}",
    "sec_start": True, "sec_mid": True, "sec_end": True, "per_span": True,
    "sec_offset": 300.0, "sec_depth": 200.0,
    "template_section": "", "scale_section": 20, "sec_name": "{L}{n}-{L}{n}",
    "margin": 300.0,
    "beam_tag": "", "bar_tag": "", "link_tag": "", "tag_leader": True,
    "unobscure": True, "fine": True, "replace_old": True,
}


# ---------------------------------------------------------------- presets
def load_presets():
    try:
        with open(PRESETS) as f:
            return json.load(f)
    except Exception:
        return {}


def save_preset(name, settings):
    data = load_presets()
    data[name] = settings
    with open(PRESETS, "w") as f:
        json.dump(data, f, indent=1, sort_keys=True)


def delete_preset(name):
    data = load_presets()
    data.pop(name, None)
    with open(PRESETS, "w") as f:
        json.dump(data, f, indent=1, sort_keys=True)


def preset(name):
    s = dict(DEFAULTS)
    s.update(load_presets().get(name, {}))
    return s


# --------------------------------------------------------------- lookups
def section_types(doc):
    return dict((br.ename(t), t) for t in FilteredElementCollector(doc).OfClass(ViewFamilyType)
                if t.ViewFamily == ViewFamily.Section)


def section_templates(doc):
    out = {}
    for v in FilteredElementCollector(doc).OfClass(View):
        if v.IsTemplate and v.ViewType == ViewType.Section:
            out[v.Name] = v
    return out


def tag_types(doc, bic):
    out = {}
    for s in FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(bic):
        out["%s : %s" % (s.FamilyName, br.ename(s))] = s
    return out


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
    """{beam UniqueId: (letter, [view ids])} for views StructFlow made."""
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
    ids = _sf_views(doc).get(beam.UniqueId, ["", []])[1]
    if ids:
        doc.Delete(List[ElementId](ids))
    return len(ids)


def make_section(doc, beam, vft, origin, bx, bz, half_w, half_h, depth,
                 name, scale, template, fine, letter=""):
    """Section box: cut plane at origin, looking along -bz, far clip at depth."""
    by = XYZ.BasisZ
    t = Transform.Identity
    t.Origin = origin
    t.BasisX = bx
    t.BasisY = by
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
    br._set_data(v, _VIEW_MARK + beam.UniqueId + "|" + letter)
    return v


def _mark_of(beam):
    p = beam.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
    m = p.AsString() if p else None
    return m or ("B%s" % beam.Id)


def _fmt(pattern, beam, L, letter="", n=0):
    return (pattern.replace("{mark}", _mark_of(beam))
            .replace("{type}", br.ename(beam))
            .replace("{L}", L)
            .replace("{letter}", letter).replace("{n}", str(n)))


def section_positions(doc, beam, fr, s, warn):
    if s["per_span"]:
        bj, cj = br.junctions(doc, beam, fr, warn)
        spans = br.complement(fr.u0, fr.u1, br.merged(bj + cj))
    else:
        spans = [(fr.u0, fr.u1)]
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


# ------------------------------------------------------------------ tags
def _rebars(doc, beam):
    """[(rebar, is_link, u0, u1, wc)] in beam-frame coordinates."""
    fr = br.BeamFrame(beam)
    out = []
    for r in RebarHostData.GetRebarHostData(beam).GetRebarsInHost():
        shape = doc.GetElement(r.GetShapeId())
        is_link = shape is not None and shape.RebarStyle == RebarStyle.StirrupTie
        bb = r.get_BoundingBox(None)
        if bb is None:
            continue
        us = [fr.u(bb.Min), fr.u(bb.Max)]
        out.append((r, is_link, min(us), max(us), (bb.Min.Z + bb.Max.Z) / 2.0))
    return fr, out


def _bar_references(el, view):
    """References to individual bars as seen in the view (rebar sets are
    tagged through one of their bars in recent Revit versions)."""
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


def _tag(doc, view, el, sym, pt, leader, warn):
    if sym is None:
        return
    err = None
    for ref in [Reference(el)] + _bar_references(el, view)[:20]:
        st = SubTransaction(doc)
        st.Start()
        try:
            IndependentTag.Create(doc, sym.Id, view.Id, ref, leader,
                                  TagOrientation.Horizontal, pt)
            st.Commit()
            return
        except Exception as ex:
            err = ex
            st.RollBack()
    warn("could not tag %s in '%s': %s" % (el.Id, view.Name, br._err(err)))


def build_views(doc, beam, s, look, warn, L="A"):
    """look: dict of resolved elements {vft, t_elev, t_sec, beam_tag, bar_tag, link_tag}.
    Returns list of created views."""
    if s["replace_old"]:
        delete_old_views(doc, beam)
    fr, rebars = _rebars(doc, beam)
    vm, wm = (fr.v0 + fr.v1) / 2.0, (fr.w0 + fr.w1) / 2.0
    half_h = (fr.w1 - fr.w0) / 2.0 + s["margin"] * MM
    views = []

    if s["make_elev"]:
        um = (fr.u0 + fr.u1) / 2.0
        sc = int(s["scale_elev"])
        v = make_section(doc, beam, look["vft"], fr.pt(um, vm, wm), fr.X, -fr.Y,
                         (fr.u1 - fr.u0) / 2.0 + s["margin"] * MM, half_h,
                         (fr.v1 - fr.v0) / 2.0 + 50 * MM,
                         _fmt(s["elev_name"], beam, L), sc, look["t_elev"], s["fine"], L)
        paper = lambda mm: mm * sc * MM
        _tag(doc, v, beam, look["beam_tag"], fr.pt(um, vm, fr.w1 + paper(12)), False, warn)
        n_top = n_bot = 0
        for r, is_link, a, b, wc in rebars:
            if s["unobscure"]:
                r.SetUnobscuredInView(v, True)
            if is_link:
                _tag(doc, v, r, look["link_tag"], fr.pt((a + b) / 2.0, vm, fr.w0 - paper(10)),
                     s["tag_leader"], warn)
            elif wc > wm:
                n_top += 1
                u = a + (b - a) * (0.2 + 0.15 * (n_top - 1))
                _tag(doc, v, r, look["bar_tag"], fr.pt(u, vm, fr.w1 + paper(6)), s["tag_leader"], warn)
            else:
                n_bot += 1
                u = b - (b - a) * (0.2 + 0.15 * (n_bot - 1))
                _tag(doc, v, r, look["bar_tag"], fr.pt(u, vm, fr.w0 - paper(18)), s["tag_leader"], warn)
        views.append(v)

    sc = int(s["scale_section"])
    paper = lambda mm: mm * sc * MM
    half_w = (fr.v1 - fr.v0) / 2.0 + s["margin"] * MM
    # looking from the beam start toward its end
    bz = -fr.X
    bx = XYZ.BasisZ.CrossProduct(bz)
    side = fr.v1 + paper(15)
    for i, u in enumerate(section_positions(doc, beam, fr, s, warn)):
        letter = chr(ord("A") + i) if i < 26 else str(i + 1)
        v = make_section(doc, beam, look["vft"], fr.pt(u, vm, wm), bx, bz, half_w, half_h,
                         s["sec_depth"] * MM, _fmt(s["sec_name"], beam, L, letter, i + 1),
                         sc, look["t_sec"], s["fine"], L)
        k = 0
        for r, is_link, a, b, wc in rebars:
            if s["unobscure"]:
                r.SetUnobscuredInView(v, True)
            if not (a - 1 * MM <= u <= b + 1 * MM):
                continue
            if is_link:
                _tag(doc, v, r, look["link_tag"], fr.pt(u, fr.v0 - paper(15), wm),
                     s["tag_leader"], warn)
            else:
                k += 1
                z = fr.w1 + paper(5 * k) if wc > wm else fr.w0 - paper(5 * k)
                _tag(doc, v, r, look["bar_tag"], fr.pt(u, side, z), s["tag_leader"], warn)
        views.append(v)
    return views
