"""RPA 2024 global checks on an analysed ETABS model → list of rows (label, value, limit, ok, detail).

Checks: modal mass participation, period vs empirical period, V_dyn ≥ 0.8·V_st (+ scale factor), inter-storey drift,
P-Δ, frames/walls interaction (seismic shear and vertical loads at the base), overturning, centres of mass.
"""
from __future__ import annotations

import math
from collections import defaultdict

from rf import codes

G_ACC = 9.81


def _base_points(e, z_tol=0.02):
    """{point: (x, y, z, kind)} of restrained / spring points at the lowest level; kind 'wall' if on a vertical area."""
    pts = {}
    names = list(e.m.PointObj.GetNameList(0, None)[2] or [])
    coords = {}
    for p in names:
        c = e.m.PointObj.GetCoordCartesian(p, 0.0, 0.0, 0.0, "Global")
        coords[p] = (c[1], c[2], c[3])
    if not coords:
        return {}
    zmin = min(c[2] for c in coords.values())
    wall_pts = set()
    try:
        r = e.m.AreaObj.GetAllAreas(0, None, None, 0, None, None, None, None, None)
        names_a, delim = list(r[2]), list(r[5])
        pn, zs = list(r[6]), list(r[9])
        start = 0
        for i, _a in enumerate(names_a):
            end = delim[i] + 1
            if max(zs[start:end]) - min(zs[start:end]) > 0.5:          # vertical area = wall
                wall_pts.update(pn[start:end])
            start = end
    except Exception:  # noqa: BLE001
        pass
    for p, (x, y, z) in coords.items():
        if abs(z - zmin) <= z_tol:
            rr = e.m.PointObj.GetRestraint(p, None)
            if any(rr[1]):
                pts[p] = (x, y, z, "wall" if p in wall_pts else "frame")
    return pts


def _react_by_case(e, cases):
    rows = e.joint_reactions(cases)
    out = defaultdict(list)
    for r in rows:
        out[r["combo"]].append(r)
    return out


def _story_table(e, cases):
    try:
        from ef.etabs import _arr

        e.m.DatabaseTables.SetLoadCasesSelectedForDisplay(_arr(str, list(cases)))
        fields, rows = e.display_table("Story Forces")
        f = {k: i for i, k in enumerate(fields)}
        return [{k: r[i] for k, i in f.items()} for r in rows]
    except Exception:  # noqa: BLE001
        return []


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def run_checks(e, spec_params, R, QF, beta, Ct=0.050, ex="Ex", ey="Ey", g_case="G", q_case="Q", modal_table=None):
    rows = []
    # ---------------------------------------------------------------- weight W = G + β·Q (base reactions)
    br = e.base_reactions([g_case, q_case, ex, ey])
    FZ = defaultdict(float)
    VX, VY, MXb, MYb = defaultdict(float), defaultdict(float), defaultdict(float), defaultdict(float)
    for r in br:
        FZ[r["case"]] = max(FZ[r["case"]], abs(r["FZ"]))
        VX[r["case"]] = max(VX[r["case"]], abs(r["FX"]))
        VY[r["case"]] = max(VY[r["case"]], abs(r["FY"]))
    W = FZ[g_case] + beta * FZ[q_case]
    rows.append(("W = G + β·Q (poids sismique)", W, None, None, f"G = {FZ[g_case]:.0f} kN, Q = {FZ[q_case]:.0f} kN, β = {beta:g}"))

    # ---------------------------------------------------------------- modal
    T1 = None
    if modal_table:
        T1 = modal_table[0][1]
        last = modal_table[-1]
        for lab, v in (("Masse modale cumulée UX", last[5]), ("Masse modale cumulée UY", last[6])):
            rows.append((lab + " (%)", v, 90.0, v >= 90.0, f"{len(modal_table)} modes"))
    # ---------------------------------------------------------------- empirical period & static equivalent shear
    pts = _base_points(e)
    zs = []
    for p in list(e.m.PointObj.GetNameList(0, None)[2] or []):
        zs.append(e.m.PointObj.GetCoordCartesian(p, 0.0, 0.0, 0.0, "Global")[3])
    hN = (max(zs) - min(zs)) if zs else 0.0
    T_emp = Ct * hN ** 0.75 if hN > 0 else 0.0
    rows.append(("Période empirique T = Ct·hN^3/4 (s)", T_emp, None, None, f"Ct = {Ct:g}, hN = {hN:.2f} m"))
    if T1:
        rows.append(("Période dynamique T1 (s)", T1, 1.3 * T_emp, None,
                     "V_st calculé avec T = min(T1 ; 1,3·T empirique)"))
    T = min(T1 or T_emp, 1.3 * T_emp) if T_emp else (T1 or 0.0)
    p = dict(spec_params)
    sad = codes.sad_g(T, p["A"], p["I"], p["S"], p["T1"], p["T2"], p["T3"], R, QF, p.get("eta", 1.0), p.get("floor", 0.2))
    nst = len({round(z, 2) for z in zs}) - 1
    lam = 0.85 if (nst > 2 and T <= 2 * p["T2"]) else 1.0
    Vst = lam * sad * W
    rows.append(("V_st = λ·(Sad(T)/g)·W (kN)", Vst, None, None, f"T = {T:.3f} s, Sad/g = {sad:.4f}, λ = {lam:g}"))
    scale = {}
    for d, case, V in (("X", ex, VX[ex]), ("Y", ey, VY[ey])):
        if not V:
            continue
        ok = V >= 0.8 * Vst
        scale[case] = 1.0 if ok else 0.8 * Vst / V
        rows.append((f"V_dyn {d} ≥ 0,8·V_st (kN)", V, 0.8 * Vst, ok,
                     "OK" if ok else f"majorer {case} de r = {scale[case]:.3f}"))
    # ---------------------------------------------------------------- drift Δk = R·δe ≤ 1 % he
    try:
        dr = e.story_drifts([ex, ey])
        worst = defaultdict(float)
        for r in dr:
            worst[(r["story"], r["case"])] = max(worst[(r["story"], r["case"])], abs(r["drift"]))
        if worst:
            (st, cs), dmax = max(worst.items(), key=lambda kv: kv[1])
            v = R * dmax
            rows.append(("Déplacement relatif max Δk/he = R·δe/he", v * 100, 1.0, v <= 0.01, f"{st}, {cs} (en %)"))
    except Exception as ex_:  # noqa: BLE001
        rows.append(("Déplacements relatifs", None, None, None, f"non lus : {ex_}"))
    # ---------------------------------------------------------------- P-Δ  θ = Pk·Δk/(Vk·hk) ≤ 0.10
    sf = _story_table(e, [g_case, q_case, ex, ey])
    if sf:
        P_story, V_story = defaultdict(float), defaultdict(float)
        for r in sf:
            case = r.get("OutputCase", "")
            loc = r.get("Location", "Bottom")
            if loc != "Bottom":
                continue
            st = r.get("Story")
            if case == g_case:
                P_story[st] += abs(_num(r.get("P")))
            elif case == q_case:
                P_story[st] += beta * abs(_num(r.get("P")))
            elif case == ex:
                V_story[(st, "X")] = max(V_story[(st, "X")], abs(_num(r.get("VX"))))
            elif case == ey:
                V_story[(st, "Y")] = max(V_story[(st, "Y")], abs(_num(r.get("VY"))))
        try:
            dr = e.story_drifts([ex, ey])
        except Exception:  # noqa: BLE001
            dr = []
        thmax, where = 0.0, ""
        for r in dr:
            d = "X" if r["case"] == ex else "Y"
            V = V_story.get((r["story"], d))
            P = P_story.get(r["story"])
            if V and P:
                th = P * R * abs(r["drift"]) / V
                if th > thmax:
                    thmax, where = th, f"{r['story']} ({d})"
        if thmax:
            rows.append(("Effet P-Δ θ = Pk·Δk/(Vk·hk)", thmax, 0.10, thmax <= 0.10, where))
    else:
        rows.append(("Effet P-Δ", None, None, None, "table « Story Forces » disponible après analyse"))
    # ---------------------------------------------------------------- interaction frames / walls (base reactions)
    if any(k == "wall" for *_x, k in pts.values()):
        R_ = _react_by_case(e, [g_case, q_case, ex, ey])

        def share(case, comp):
            tot, wall = 0.0, 0.0
            for r in R_.get(case, []):
                if r["point"] in pts:
                    v = abs(r[comp])
                    tot += v
                    if pts[r["point"]][3] == "wall":
                        wall += v
            return wall / tot if tot else 0.0

        for case, comp, d in ((ex, "F1", "X"), (ey, "F2", "Y")):
            s = share(case, comp)
            rows.append((f"Effort tranchant repris par les portiques {d} (%)", (1 - s) * 100, 25.0, (1 - s) >= 0.25,
                         f"voiles {s * 100:.0f} % – système mixte : portiques ≥ 25 %"))
        sG = share(g_case, "F3")
        rows.append(("Charges verticales reprises par les voiles (%)", sG * 100, 20.0, sG <= 0.20,
                     "système mixte : voiles ≤ 20 % des charges verticales"))
    # ---------------------------------------------------------------- overturning
    if pts:
        xs = [v[0] for v in pts.values()]
        ys = [v[1] for v in pts.values()]
        Lx, Ly = max(xs) - min(xs), max(ys) - min(ys)
        for r in br:
            MXb[r["case"]] = max(MXb[r["case"]], abs(r.get("MX", 0.0)))
            MYb[r["case"]] = max(MYb[r["case"]], abs(r.get("MY", 0.0)))
        for d, case, Mr, L in (("X", ex, MYb.get(ex, 0.0), Lx), ("Y", ey, MXb.get(ey, 0.0), Ly)):
            if Mr:
                Ms = 0.8 * W * L / 2
                rows.append((f"Renversement {d} : Ms/Mr", Ms / Mr, 1.5, Ms / Mr >= 1.5,
                             f"Ms = 0,8·W·L/2 = {Ms:.0f} kN·m ; Mr = {Mr:.0f} kN·m"))
    # ---------------------------------------------------------------- centres of mass per storey (assembled masses)
    try:
        r = e.m.Results.AssembledJointMass("All", e.E.eItemTypeElm.GroupElm, 0, None, None, None, None, None, None, None)
        mass = defaultdict(lambda: [0.0, 0.0, 0.0])
        for i in range(r[1]):
            pnt = r[2][i]
            m = r[3][i]
            if m <= 0:
                continue
            c = e.m.PointObj.GetCoordCartesian(pnt, 0.0, 0.0, 0.0, "Global")
            k = round(c[3], 2)
            mass[k][0] += m
            mass[k][1] += m * c[1]
            mass[k][2] += m * c[2]
        for z, (m, mx, my) in sorted(mass.items()):
            if m > 0 and z > min(mass):
                rows.append((f"Centre de masse niveau {z:+.2f}", None, None, None,
                             f"XCM = {mx / m:.2f} m ; YCM = {my / m:.2f} m ; M = {m * G_ACC:.0f} kN"))
    except Exception:  # noqa: BLE001
        pass
    return rows, scale


def apply_scale(e, case, factor, g=G_ACC):
    """Multiply the spectral case scale factor (RS case) by factor."""
    RS = e.m.LoadCases.ResponseSpectrum
    r = RS.GetLoads(case, 0, None, None, None, None, None)
    n = r[1]
    names, funcs, sfs, csys, ang = list(r[2]), list(r[3]), [s * factor for s in r[4]], list(r[5]), list(r[6])
    e.unlock()
    from ef.etabs import _arr

    RS.SetLoads(case, n, _arr(str, names), _arr(str, funcs), _arr(float, sfs), _arr(str, csys), _arr(float, ang))
    return sfs
