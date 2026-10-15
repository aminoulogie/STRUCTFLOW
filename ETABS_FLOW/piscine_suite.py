"""Piscine – complète le modèle ETABS existant (picsine.EDB) sans rien effacer.

Ajoute : fûts −3.75 → 0.00 sous chaque poteau existant + encastrement, nervures/longrines à −3.75,
radier du bassin (suite de Slab1, en pente jusqu'au petit bain), voiles du bassin jusqu'au rebord +1.39,
ressorts de sol sous le radier, poids et poussée de l'eau, combinaisons.
Relançable : un élément déjà présent (mêmes coordonnées) n'est pas recréé.
Coller dans l'onglet Script de GCStructFlow, puis ▶ Exécuter.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else ".")
from ef import etabs as ET  # noqa: E402

# ================================================================== DONNÉES
Z_PIED = -3.75                       # pied des fûts (au-dessus du gros béton)
NERVURES = [  # (x1, y1, x2, y2, b, h, nom) – plan de fondations
    (3, 18, 3, 25, 0.80, 0.70, "NERV 80x70"), (8, 18, 8, 25, 0.80, 0.70, "NERV 80x70"),
    (23, 18, 23, 25, 0.80, 0.70, "NERV 80x70"), (28, 18, 28, 25, 0.80, 0.70, "NERV 80x70"),
    (13, 25, 13, 26.75, 0.80, 0.70, "NERV 80x70"), (18, 25, 18, 26.75, 0.80, 0.70, "NERV 80x70"),
    (8, 26.75, 13, 26.75, 0.70, 0.60, "NERV 70x60"), (18, 26.75, 23, 26.75, 0.70, 0.60, "NERV 70x60"),
    (13, 18, 13, 25, 0.30, 0.60, "LONG 30x60"), (18, 18, 18, 25, 0.30, 0.60, "LONG 30x60"),
]
# bassin – contour pris sur votre modèle (Slab1 / Wall1)
BX0, BX1 = 3.00, 29.60
BY0, BY1 = 2.10, 14.80
Z_REBORD = 1.39
# dessus du radier : (x, z) – fosse −2.11 jusqu'à 8.75 (votre Slab1), pentes, petit bain −0.14
FOND = [(3.00, -2.11), (8.75, -2.11), (14.36, -1.23), (24.41, -0.14), (29.60, -0.14)]
E_RADIER, E_VOILE = 0.375, 0.20
KS = 14400.0                         # kN/m³  (σsol 1.2 bar × 120)
BANDE = 0.50                         # hauteur des bandes de voile (pression hydrostatique)
PSI = 0.20                           # coefficient de Q en situation sismique


# ================================================================== OUTILS
def z_fond(x):
    for (x0, z0), (x1, z1) in zip(FOND, FOND[1:]):
        if x0 - 1e-9 <= x <= x1 + 1e-9:
            return z0 + (z1 - z0) * (x - x0) / (x1 - x0)
    return FOND[-1][1]


def key3(p):
    return tuple(round(v, 3) for v in p)


def main(e=None):
    e = e or ET.connect()
    e.unlock()
    mat = e.ensure_concrete("BETON25", 25.0)
    reb = e.ensure_rebar("FeE400", 400)
    frames = e.frames()
    have = {frozenset((key3(d["p1"]), key3(d["p2"]))) for d in frames.values()}

    def frame(p1, p2, prop):
        k = frozenset((key3(p1), key3(p2)))
        if k in have:
            return None
        have.add(k)
        return e.add_frame(p1, p2, prop)

    # ---------------------------------------------------------- 1. fûts sous les poteaux existants
    n_fut = 0
    for d in frames.values():
        lo, hi = sorted((d["p1"], d["p2"]), key=lambda p: p[2])
        if abs(lo[2]) < 0.01 and hi[2] > 1.0 and abs(lo[0] - hi[0]) < 1e-3 and abs(lo[1] - hi[1]) < 1e-3:
            name = frame((lo[0], lo[1], Z_PIED), (lo[0], lo[1], 0.0), d["prop"])
            if name:
                p1, _ = e.frame_points(name)
                e.restrain(p1, (True,) * 6)
                n_fut += 1
    # ---------------------------------------------------------- 2. nervures / longrines
    n_nerv = 0
    for x1, y1, x2, y2, b, h, nm in NERVURES:
        sec = e.ensure_rect(nm, b, h, "beam", mat, reb)
        if frame((x1, y1, Z_PIED), (x2, y2, Z_PIED), sec):
            n_nerv += 1
    # ---------------------------------------------------------- 3. radier (suite de Slab1)
    rad = e.ensure_slab(f"RADIER {E_RADIER * 100:g}", E_RADIER, mat)
    voi = e.ensure_wall(f"VOILE {E_VOILE * 100:g}", E_VOILE, mat)
    spring = e.area_spring_prop("SOL 1.2bar", KS, 0, 0, compression_only=True)
    e.load_pattern("EAU", "Gs", 0.0)
    r = e.m.AreaObj.GetAllAreas(0, None, None, 0, None, None, None, None, None)
    names, delim = list(r[2]), list(r[5])
    xs_, ys_, zs_ = list(r[7]), list(r[8]), list(r[9])
    existing_areas, start = [], 0
    for i, nm in enumerate(names):
        end = delim[i] + 1
        existing_areas.append((nm, frozenset(key3(p) for p in zip(xs_[start:end], ys_[start:end], zs_[start:end]))))
        start = end
    have_area = {k for _, k in existing_areas}

    def area(pts, prop):
        k = frozenset(key3(p) for p in pts)
        if k in have_area:
            return None
        have_area.add(k)
        return e.add_area(pts, prop)

    rafts = []
    for nm, k in existing_areas:                     # votre Slab1 : même propriété / ressorts / eau
        zs = {p[2] for p in k}
        if len(zs) == 1 and abs(next(iter(zs)) + 2.11) < 1e-3:
            e.m.AreaObj.SetProperty(nm, rad, e.E.eItemType.Objects)
            rafts.append((nm, -2.11, -2.11))
    for (xa, za), (xb, zb) in zip(FOND, FOND[1:]):
        a = area([(xa, BY0, za), (xb, BY0, zb), (xb, BY1, zb), (xa, BY1, za)], rad)
        if a:
            rafts.append((a, za, zb))
    for a, za, zb in rafts:
        e.assign_area_spring(a, spring)
        e.m.AreaObj.SetLoadUniform(a, "EAU", 10.0 * (Z_REBORD - (za + zb) / 2), 10, True, "Global",
                                   e.E.eItemType.Objects)
    # ---------------------------------------------------------- 4. voiles du radier jusqu'au rebord, poussée de l'eau
    n_wall = 0

    def strip(a, b, za, zb, zta, ztb, outward):
        nonlocal n_wall
        pts = [(a[0], a[1], za), (b[0], b[1], zb), (b[0], b[1], ztb), (a[0], a[1], zta)]
        ar = area(pts, voi)
        if not ar:
            return
        n_wall += 1
        p = 10.0 * max(Z_REBORD - (za + zb + zta + ztb) / 4, 0.0)
        if p <= 0:
            return
        g = e.m.AreaObj.GetPoints(ar, 0, None)
        P = [e.m.PointObj.GetCoordCartesian(q, 0.0, 0.0, 0.0, "Global")[1:4] for q in list(g[2])[:3]]
        u = [P[1][i] - P[0][i] for i in range(3)]
        v = [P[2][i] - P[0][i] for i in range(3)]
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2])
        sign = 1.0 if n[0] * outward[0] + n[1] * outward[1] > 0 else -1.0
        e.m.AreaObj.SetLoadUniform(ar, "EAU", sign * p, 3, False, "Local", e.E.eItemType.Objects)

    def bands(a, b, za, zb, outward):
        top = max(za, zb)
        if abs(za - zb) > 1e-6:                      # triangle/trapèze qui suit la pente
            strip(a, b, za, zb, top, top, outward)
        z = top
        while z < Z_REBORD - 1e-6:
            z1 = min(z + BANDE, Z_REBORD)
            strip(a, b, z, z, z1, z1, outward)
            z = z1

    bands((BX0, BY0), (BX0, BY1), z_fond(BX0), z_fond(BX0), (-1, 0))
    bands((BX1, BY0), (BX1, BY1), z_fond(BX1), z_fond(BX1), (1, 0))
    for (xa, za), (xb, zb) in zip(FOND, FOND[1:]):
        bands((xa, BY0), (xb, BY0), za, zb, (0, -1))
        bands((xa, BY1), (xb, BY1), za, zb, (0, 1))
    # maillage auto des panneaux
    for nm in list(e.m.AreaObj.GetNameList(0, None)[2] or []):
        try:
            e.m.AreaObj.SetAutoMesh(nm, 1, 0, 0, True, True, True, True, False, 1.0, 1.0, False, False, False,
                                    False, False, "ALL", e.E.eItemType.Objects)
        except Exception:  # noqa: BLE001
            pass
    # ---------------------------------------------------------- 5. combinaisons (bassin plein / vide)
    pats = list(e.m.LoadPatterns.GetNameList(0, None)[2] or [])
    G = [p for p in pats if p.upper() in ("G", "DEAD")]
    Q = [p for p in pats if p.upper() in ("Q", "LIVE")]

    def f(g, q, w):
        d = {p: g for p in G}
        d.update({p: q for p in Q})
        if w:
            d["EAU"] = w
        return d

    combos = [("ELU plein 1.35G+1.5Q+1.35EAU", f(1.35, 1.5, 1.35)), ("ELU vide 1.35G+1.5Q", f(1.35, 1.5, 0)),
              ("ELS plein G+Q+EAU", f(1, 1, 1)), ("ELS vide G+Q", f(1, 1, 0))]
    cases = e.load_cases()
    for E_ in ("Ex", "Ey"):
        if E_ in cases:
            combos += [(f"ACC plein G+{PSI:g}Q+EAU±{E_}", {**f(1, PSI, 1), E_: 1.0}),
                       (f"ACC vide 0.8G±{E_}", {**f(0.8, 0, 0), E_: 1.0})]
    for nm, fac in combos:
        e.combo(nm, fac)
    e.refresh()
    print(f"OK : {n_fut} fûts −3.75→0.00 encastrés, {n_nerv} nervures/longrines, {len(rafts)} panneaux de radier "
          f"(ressorts {KS:.0f} kN/m³ + eau), {n_wall} bandes de voile jusqu'à +1.39 (poussée de l'eau), "
          f"{len(combos)} combinaisons.")


if __name__ == "__main__":
    main(globals().get("e"))
