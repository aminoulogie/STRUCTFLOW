"""Export the designed foundations to IFC 4 (opened / linked by Revit) and to CSV.

Elements: IfcFooting (semelles, longrines), IfcColumn (fûts), IfcReinforcingBar (nappes, attentes, cadres,
barres de longrines) at the real support coordinates. Global axes: X, Y from the model (m), Z = 0 at ground level.
Footing A along X, B along Y.
"""
from __future__ import annotations

import csv
import math

import numpy as np

from .footing import BARS


def _placement(f, api, product, x, y, z):
    M = np.eye(4)
    M[:3, 3] = (x, y, z)
    api.run("geometry.edit_object_placement", f, product=product, matrix=M, is_si=True)


STY = {}  # styles / materials of the file being written


def _box(f, api, body, product, x0, y0, z0, lx, ly, lz):
    if product is None:
        return
    rep = api.run("geometry.add_wall_representation", f, context=body, length=lx, height=lz, thickness=ly)
    api.run("geometry.assign_representation", f, product=product, representation=rep)
    if STY.get("concrete"):
        api.run("style.assign_representation_styles", f, shape_representation=rep, styles=[STY["concrete"]])
        api.run("material.assign_material", f, products=[product], material=STY["mat_concrete"])
    _placement(f, api, product, x0, y0, z0)


def _pset(api, f, product, name, props):
    if product is None:
        return
    ps = api.run("pset.add_pset", f, product=product, name=name)
    api.run("pset.edit_pset", f, pset=ps, properties={k: (str(v) if not isinstance(v, (int, float)) else v)
                                                       for k, v in props.items()})


def _bar(f, api, body, storey, name, pts, phi_mm, kind="MAIN"):
    bar = api.run("root.create_entity", f, ifc_class="IfcReinforcingBar", name=name, predefined_type=kind)
    api.run("spatial.assign_container", f, products=[bar], relating_structure=storey)
    poly = f.createIfcPolyline([f.createIfcCartesianPoint(tuple(float(c) for c in p)) for p in pts])
    solid = f.createIfcSweptDiskSolid(poly, phi_mm / 2000.0, None, None, None)
    shape = f.createIfcShapeRepresentation(body, "Body", "AdvancedSweptSolid", [solid])
    bar.Representation = f.createIfcProductDefinitionShape(None, None, [shape])
    if STY.get("steel"):
        api.run("style.assign_representation_styles", f, shape_representation=shape, styles=[STY["steel"]])
        api.run("material.assign_material", f, products=[bar], material=STY["mat_steel"])
    _placement(f, api, bar, 0, 0, 0)
    length = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    bar.NominalDiameter = phi_mm / 1000.0
    bar.CrossSectionArea = BARS.get(phi_mm, math.pi * phi_mm ** 2 / 400) * 1e-4
    bar.BarLength = length
    return length


def layout_positions(prj):
    """{joint: (x, y)} – model coordinates if known, otherwise a 6 m grid per footing type."""
    pos = dict(prj.coords or {})
    k = 0
    for r in prj.results:
        for j in r.gi.joints:
            if j not in pos:
                pos[j] = ((k % 10) * 6.0, (k // 10) * 6.0)
                k += 1
    return pos


def _styles(f, api, body, transparency):
    STY.clear()
    sc = api.run("style.add_style", f, name="Béton (transparent)")
    api.run("style.add_surface_style", f, style=sc, ifc_class="IfcSurfaceStyleShading",
            attributes={"SurfaceColour": {"Name": None, "Red": 0.72, "Green": 0.72, "Blue": 0.72},
                        "Transparency": float(transparency)})
    ss = api.run("style.add_style", f, name="Acier HA")
    api.run("style.add_surface_style", f, style=ss, ifc_class="IfcSurfaceStyleShading",
            attributes={"SurfaceColour": {"Name": None, "Red": 0.85, "Green": 0.10, "Blue": 0.10}, "Transparency": 0.0})
    mc = api.run("material.add_material", f, name="Béton armé C25/30", category="concrete")
    ms = api.run("material.add_material", f, name="Acier HA FeE500", category="steel")
    api.run("style.assign_material_style", f, material=mc, style=sc, context=body)
    api.run("style.assign_material_style", f, material=ms, style=ss, context=body)
    STY.update(concrete=sc, steel=ss, mat_concrete=mc, mat_steel=ms)


def export_ifc(prj, path, with_rebar=True, with_longrines=True, lean=True, longrine_top=0.0,
               with_concrete=True, transparency=0.6):
    import ifcopenshell
    import ifcopenshell.api as api
    f = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", f, ifc_class="IfcProject", name=prj.meta.get("ouvrage") or "Fondations")
    api.run("unit.assign_unit", f, length={"is_metric": True, "raw": "METERS"})
    model = api.run("context.add_context", f, context_type="Model")
    body = api.run("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW",
                   parent=model)
    _styles(f, api, body, transparency)
    site = api.run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    bld = api.run("root.create_entity", f, ifc_class="IfcBuilding", name=prj.meta.get("ouvrage") or "Bâtiment")
    storey = api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Fondations")
    api.run("aggregate.assign_object", f, products=[site], relating_object=project)
    api.run("aggregate.assign_object", f, products=[bld], relating_object=site)
    api.run("aggregate.assign_object", f, products=[storey], relating_object=bld)
    cover = prj.mat.cover
    pos = layout_positions(prj)
    stats = dict(footings=0, pedestals=0, longrines=0, bars=0, steel_kg=0.0)
    for r in prj.results:
        g, gi, rc = r.geo, r.gi, r.rc
        for j in r.gi.joints:
            x, y = pos[j]
            zb = -g.D
            ft = api.run("root.create_entity", f, ifc_class="IfcFooting", name=f"{gi.name}-{j}", predefined_type="PAD_FOOTING") if with_concrete else None
            if ft is not None:
                api.run("spatial.assign_container", f, products=[ft], relating_structure=storey)
            _box(f, api, body, ft, x - g.A / 2, y - g.B / 2, zb, g.A, g.B, g.h)
            _pset(api, f, ft, "GCSTRUCTFLOW_Semelle", {
                "Type": gi.name, "Appui": j, "A_m": g.A, "B_m": g.B, "h_m": g.h, "D_m": g.D,
                "Nappe_inf_A": f"{rc['X']['bars']['n']} HA{rc['X']['bars']['phi']} e={rc['X']['bars']['s'] * 100:.0f}",
                "Nappe_inf_B": f"{rc['Y']['bars']['n']} HA{rc['Y']['bars']['phi']} e={rc['Y']['bars']['s'] * 100:.0f}",
                "Nappe_sup": "oui" if (rc["X"]["bars_top"] or rc["Y"]["bars_top"]) else "non"})
            stats["footings"] += 1 if with_concrete else 0
            if lean:
                lc = api.run("root.create_entity", f, ifc_class="IfcSlab", name=f"Propreté-{j}", predefined_type="BASESLAB") if with_concrete else None
                if lc is not None:
                    api.run("spatial.assign_container", f, products=[lc], relating_structure=storey)
                _box(f, api, body, lc, x - g.A / 2 - 0.05, y - g.B / 2 - 0.05, zb - 0.05, g.A + 0.10, g.B + 0.10, 0.05)
            ped = api.run("root.create_entity", f, ifc_class="IfcColumn", name=f"Fût-{gi.name}-{j}", predefined_type="COLUMN") if with_concrete else None
            if ped is not None:
                api.run("spatial.assign_container", f, products=[ped], relating_structure=storey)
            _box(f, api, body, ped, x - g.ap / 2, y - g.bp / 2, zb + g.h, g.ap, g.bp, g.Hp)
            stats["pedestals"] += 1 if with_concrete else 0
            if not with_rebar:
                continue
            # bottom mats (bars // A lowest when A ≥ B)
            for key, lab in (("X", "A"), ("Y", "B")):
                b = rc[key]["bars"]
                low = (key == "X") == (g.A >= g.B)
                z = zb + cover + (b["phi"] / 2000 if low else rc["X" if key == "Y" else "Y"]["bars"]["phi"] / 1000 + b["phi"] / 2000)
                hook = rc[key]["ls"] > rc[key]["L"] / 4
                hk = min(g.h - 2 * cover, 12 * b["phi"] / 1000)
                L_, W_ = (g.A, g.B) if key == "X" else (g.B, g.A)
                for i in range(b["n"]):
                    t = -W_ / 2 + cover + i * (W_ - 2 * cover) / max(b["n"] - 1, 1)
                    a0, a1 = -L_ / 2 + cover, L_ / 2 - cover
                    if key == "X":
                        pts = [(x + a0, y + t, z), (x + a1, y + t, z)]
                        if hook:
                            pts = [(x + a0, y + t, z + hk)] + pts + [(x + a1, y + t, z + hk)]
                    else:
                        pts = [(x + t, y + a0, z), (x + t, y + a1, z)]
                        if hook:
                            pts = [(x + t, y + a0, z + hk)] + pts + [(x + t, y + a1, z + hk)]
                    ln = _bar(f, api, body, storey, f"{gi.name}-{j}-inf//{lab}", pts, b["phi"])
                    stats["bars"] += 1
                    stats["steel_kg"] += ln * BARS[b["phi"]] * 1e-4 * 7850
                bt = rc[key]["bars_top"]
                if bt:
                    zt = zb + g.h - cover - bt["phi"] / 2000
                    for i in range(bt["n"]):
                        t = -W_ / 2 + cover + i * (W_ - 2 * cover) / max(bt["n"] - 1, 1)
                        a0, a1 = -L_ / 2 + cover, L_ / 2 - cover
                        pts = [(x + a0, y + t, zt), (x + a1, y + t, zt)] if key == "X" else [(x + t, y + a0, zt), (x + t, y + a1, zt)]
                        ln = _bar(f, api, body, storey, f"{gi.name}-{j}-sup//{lab}", pts, bt["phi"])
                        stats["bars"] += 1
                        stats["steel_kg"] += ln * BARS[bt["phi"]] * 1e-4 * 7850
            # pedestal starter bars with 90° foot on the bottom mat + ties
            pb = r.ped["bars"]
            if pb:
                cp = cover + 0.008 + pb["phi"] / 2000
                xs = np.linspace(-g.ap / 2 + cp, g.ap / 2 - cp, pb["ny"])
                ys = np.linspace(-g.bp / 2 + cp, g.bp / 2 - cp, pb["nx"])
                pts_set = {(round(a, 4), round(ys[0], 4)) for a in xs} | {(round(a, 4), round(ys[-1], 4)) for a in xs} | \
                          {(round(xs[0], 4), round(c, 4)) for c in ys} | {(round(xs[-1], 4), round(c, 4)) for c in ys}
                z0 = zb + cover + 0.03
                z1 = g.h0 if hasattr(g, "h0") else gi.h_above
                z1 = gi.h_above - 0.03
                foot = 15 * pb["phi"] / 1000
                for (px, py) in sorted(pts_set):
                    dx = math.copysign(foot, px) if abs(px) >= abs(py) else 0.0
                    dy = 0.0 if dx else math.copysign(foot, py)
                    pts = [(x + px + dx, y + py + dy, z0), (x + px, y + py, z0), (x + px, y + py, z1)]
                    ln = _bar(f, api, body, storey, f"{gi.name}-{j}-attente", pts, pb["phi"])
                    stats["bars"] += 1
                    stats["steel_kg"] += ln * BARS[pb["phi"]] * 1e-4 * 7850
                ct = cover + 0.004
                zz = zb + g.h + 0.05
                while zz < gi.h_above - 0.02:
                    pts = [(x - g.ap / 2 + ct, y - g.bp / 2 + ct, zz), (x + g.ap / 2 - ct, y - g.bp / 2 + ct, zz),
                           (x + g.ap / 2 - ct, y + g.bp / 2 - ct, zz), (x - g.ap / 2 + ct, y + g.bp / 2 - ct, zz),
                           (x - g.ap / 2 + ct, y - g.bp / 2 + ct + 0.02, zz)]  # open loop (hook gap)
                    ln = _bar(f, api, body, storey, f"{gi.name}-{j}-cadre", pts, 8, "LIGATURE")
                    stats["bars"] += 1
                    stats["steel_kg"] += ln * BARS[8] * 1e-4 * 7850
                    zz += 0.15
    # tie beams
    lg = prj.lg or {}
    if with_longrines and lg.get("beams"):
        li = prj.longrine
        dims = {j: (r.geo.ap, r.geo.bp) for r in prj.results for j in r.gi.joints}
        tmap = {t["name"]: t for t in lg.get("types", [])}
        for bm in lg["beams"]:
            if not bm["kept"] or bm["j1"] not in pos or bm["j2"] not in pos:
                continue
            (x1, y1), (x2, y2) = pos[bm["j1"]], pos[bm["j2"]]
            a1, b1 = dims.get(bm["j1"], (0.5, 0.5))
            a2, b2 = dims.get(bm["j2"], (0.5, 0.5))
            if bm["dir"] == "X":
                xa, xb = min(x1, x2) + (a1 if x1 < x2 else a2) / 2, max(x1, x2) - (a2 if x1 < x2 else a1) / 2
                ox, oy, lx, ly = xa, y1 - li.b / 2, xb - xa, li.b
            else:
                ya, yb = min(y1, y2) + (b1 if y1 < y2 else b2) / 2, max(y1, y2) - (b2 if y1 < y2 else b1) / 2
                ox, oy, lx, ly = x1 - li.b / 2, ya, li.b, yb - ya
            el = api.run("root.create_entity", f, ifc_class="IfcFooting", name=f"{bm['id']}-{bm.get('tname', '')}",
                         predefined_type="STRIP_FOOTING") if with_concrete else None
            if el is not None:
                api.run("spatial.assign_container", f, products=[el], relating_structure=storey)
            _box(f, api, body, el, ox, oy, longrine_top - li.h, lx, ly, li.h)
            stats["longrines"] += 1 if with_concrete else 0
            t = tmap.get(bm.get("tname"))
            if t:
                _pset(api, f, el, "GCSTRUCTFLOW_Longrine", {"Type": t["name"], "Appuis": f"{bm['j1']}-{bm['j2']}",
                                                           "Ferraillage": f"{t['res']['bars']['n']} HA{t['res']['bars']['phi']}"})
            if with_rebar and t:
                bb = t["res"]["bars"]
                c2 = cover + 0.008 + bb["phi"] / 2000
                n_side = bb["n"] // 2
                for k in range(bb["n"]):
                    row = k // n_side
                    col = k % n_side
                    off = -li.b / 2 + c2 + col * (li.b - 2 * c2) / max(n_side - 1, 1)
                    zz = longrine_top - li.h + c2 if row == 0 else longrine_top - c2
                    if bm["dir"] == "X":
                        pts = [(ox, y1 + off, zz), (ox + lx, y1 + off, zz)]
                    else:
                        pts = [(x1 + off, oy, zz), (x1 + off, oy + ly, zz)]
                    ln = _bar(f, api, body, storey, f"{bm['id']}-long", pts, bb["phi"])
                    stats["bars"] += 1
                    stats["steel_kg"] += ln * BARS[bb["phi"]] * 1e-4 * 7850
    f.write(path)
    return stats


def export_csv(prj, path):
    pos = layout_positions(prj)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["Appui", "Type", "X (m)", "Y (m)", "Z base (m)", "A (m)", "B (m)", "h (m)", "ap (m)", "bp (m)",
                    "Nappe inf // A", "Nappe inf // B", "Nappe sup // A", "Nappe sup // B", "Fût"])
        for r in prj.results:
            g, rc = r.geo, r.rc

            def bt(b):
                return f"{b['n']} HA{b['phi']} e={b['s'] * 100:.0f}" if b else ""
            for j in r.gi.joints:
                x, y = pos[j]
                w.writerow([j, r.gi.name, f"{x:.3f}", f"{y:.3f}", f"{-g.D:.3f}", g.A, g.B, g.h, g.ap, g.bp,
                            bt(rc["X"]["bars"]), bt(rc["Y"]["bars"]), bt(rc["X"]["bars_top"]), bt(rc["Y"]["bars_top"]),
                            f"{r.ped['bars']['n']} HA{r.ped['bars']['phi']}" if r.ped["bars"] else ""])
