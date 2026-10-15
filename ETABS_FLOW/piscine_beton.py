"""Piscine semi-olympique – partie BÉTON (fûts, nervures/longrines, bassin) → modèle ETABS ouvert.

Coller ce fichier dans l'onglet Script de GCStructFlow (ou lancer piscine_beton.bat), ETABS ouvert sur un modèle
« Grid Only » en kN, m.  Origine : axe 1 / axe C.  Toutes les données sont en tête de fichier.

Sources :  plan de fondations (axes, fûts, nervures), détails d'ancrage (têtes de fûts ±0.00 / +1.44),
coupes longitudinales du bassin (+1.39, −2.11, −0.14, radier, nervures 35), plan (ruptures de pente 7.00 /
14.36 / 24.41, pentes 12 % et 11 %).
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ef import etabs as ET  # noqa: E402

# ================================================================== DONNÉES
X = {"1": 0.0, "2": 3.0, "3": 8.0, "4": 13.0, "5": 18.0, "6": 23.0, "7": 28.0, "8": 32.0}
Y = {"C": 0.0, "F": 6.0, "E": 12.0, "B": 18.0, "A": 25.0, "A'": 26.75}
FC28 = 25.0

# ---- fûts : pied −3.75 (au-dessus du gros béton) ; tête = niveau d'ancrage des poteaux acier
Z_PIED = -3.75
FUT_X = {"P1": 0.99, "P2": 1.17, "P2'": 0.80, "P3": 0.99, "P4": 0.84, "P5": 0.30}       # suivant X (plan)
FUT_Y_RANGEE = {"C": 0.80, "A": 1.40, "A'": 1.40}                                        # suivant Y (consigne)
FUT_Y_AUTRES = 0.90                                                                      # rangées B, E, F
TYPES = {
    "P1": ["1C", "2C", "7C", "8C", "1A", "2A", "7A"],
    "P2": ["3C", "4C", "5C", "6C", "3A", "5A", "6A", "3B", "6B"],
    "P2'": ["4A", "4B", "5B"],
    "P3": ["1B", "2B", "7B"],
    "P4": ["1E", "1F", "8E", "8F", "8B"],
    "P5": ["3A'", "4A'", "5A'", "6A'"],
}


def tete_fut(w):
    """Détails d'ancrage : file C et file B (axes 1-2-3-6-7-8) à +1.44 ; file A, A' et B (axes 4-5) à ±0.00."""
    row = w.lstrip("12345678")
    if row == "C" or row in ("E", "F") or (row == "B" and w[0] not in "45"):
        return 1.44
    return 0.00


# ---- nervures / longrines (sur semelles, au pied des fûts)
NERVURES = [(f"{ax}B", f"{ax}A", (0.80, 0.70), "NERV 80x70") for ax in ("2", "3", "6", "7")] + [
    ("4A", "4A'", (0.80, 0.70), "NERV 80x70"), ("5A", "5A'", (0.80, 0.70), "NERV 80x70"),
    ("3A'", "4A'", (0.70, 0.60), "NERV 70x60"), ("5A'", "6A'", (0.70, 0.60), "NERV 70x60"),
    ("4B", "4A", (0.30, 0.60), "LONG 30x60"), ("5B", "5A", (0.30, 0.60), "LONG 30x60"),
]

# ---- bassin
Z_REBORD = 1.39                          # arase des voiles (goulotte)
X_VOILES = (3.10, 28.31)                 # axes des voiles d'extrémité (intérieur 3.20 → 28.21 = 25.01 m)
Y_VOILES = (2.18, 14.88)                 # axes des voiles latéraux (intérieur 2.28 → 14.78 = 12.50 m)
E_VOILE = 0.20
E_RADIER = 0.375                         # 387.5 rebord → sous-face radier (−2.485) − fond −2.11
# fond du bassin (dessus radier) : points (x, z) – fosse −2.11, pente 12 %, pente 11 %, petit bain −0.14
FOND = [(3.10, -2.11), (7.00, -2.11), (14.36, -1.23), (24.41, -0.14), (28.31, -0.14)]
NERV_RADIER_X = [6.75, 12.65, 20.81, 25.81]   # nervures 35 sous radier (coupes longitudinales), suivant Y
NERV_RADIER = (0.35, 0.75)
SIGMA_SOL = 120.0                        # kPa (1.2 bar)
KS = 120.0 * SIGMA_SOL                   # kN/m³
BANDE_EAU = 0.50                         # hauteur des bandes de voile pour la pression hydrostatique
GAMMA_EAU = 10.0


# ================================================================== OUTILS
def pt(name):
    for cut in range(1, len(name)):
        a, b = name[:cut], name[cut:]
        if a in X and b in Y:
            return X[a], Y[b]
    raise ValueError(name)


def z_fond(x):
    for (x0, z0), (x1, z1) in zip(FOND, FOND[1:]):
        if x0 - 1e-9 <= x <= x1 + 1e-9:
            return z0 + (z1 - z0) * (x - x0) / (x1 - x0)
    return FOND[-1][1] if x > FOND[-1][0] else FOND[0][1]


def local3(e, area):
    """Unit normal (local 3) of a planar area from its first three points."""
    r = e.m.AreaObj.GetPoints(area, 0, None)
    P = []
    for p in list(r[2])[:3]:
        c = e.m.PointObj.GetCoordCartesian(p, 0.0, 0.0, 0.0, "Global")
        P.append((c[1], c[2], c[3]))
    u = [P[1][i] - P[0][i] for i in range(3)]
    v = [P[2][i] - P[0][i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    L = math.sqrt(sum(c * c for c in n)) or 1.0
    return tuple(c / L for c in n)


def main(e=None):
    e = e or ET.connect()
    e.unlock()
    e.clear_objects()
    lv = [(-2.11, "FOSSE -2.11"), (-0.14, "PETIT BAIN -0.14"), (0.00, "N 0.00"), (1.44, "N +1.44")]
    e.set_stories([n for _, n in lv], [lv[0][0] - Z_PIED] + [b[0] - a[0] for a, b in zip(lv, lv[1:])], Z_PIED)
    e.set_grids(list(X.values()), list(Y.values()), list(X), list(Y))
    mat = e.ensure_concrete("BETON25", FC28)
    reb = e.ensure_rebar("FeE400", 400)

    # ---------------------------------------------------------- fûts
    nf = 0
    for typ, where in TYPES.items():
        for w in where:
            row = w.lstrip("12345678")
            dx, dy = FUT_X[typ], FUT_Y_RANGEE.get(row, FUT_Y_AUTRES)
            sec = e.ensure_rect(f"FUT {round(dx * 100)}x{round(dy * 100)}", dy, dx, "col", mat, reb)
            x, y = pt(w)
            name = e.add_frame((x, y, Z_PIED), (x, y, tete_fut(w)), sec)
            p1, _ = e.frame_points(name)
            e.restrain(p1, (True,) * 6)
            nf += 1
    # ---------------------------------------------------------- nervures / longrines au pied des fûts
    for a, b, (bw, h), nm in NERVURES:
        sec = e.ensure_rect(nm, bw, h, "beam", mat, reb)
        (xa, ya), (xb, yb) = pt(a), pt(b)
        e.add_frame((xa, ya, Z_PIED), (xb, yb, Z_PIED), sec)

    # ---------------------------------------------------------- bassin
    rad = e.ensure_slab(f"RADIER {round(E_RADIER * 100, 1):g}", E_RADIER, mat)
    voi = e.ensure_wall(f"VOILE {round(E_VOILE * 100)}", E_VOILE, mat)
    spring = e.area_spring_prop("SOL 1.2bar", KS, 0, 0, compression_only=True)
    e.load_pattern("G", "G", 1.0)
    e.load_pattern("Q", "Q", 0.0)
    e.load_pattern("EAU", "Gs", 0.0)
    y0, y1 = Y_VOILES
    # radier : un panneau par zone de pente (+ découpe aux nervures)
    xs = sorted({x for x, _ in FOND} | set(NERV_RADIER_X))
    rafts = []
    for xa, xb in zip(xs, xs[1:]):
        za, zb = z_fond(xa), z_fond(xb)
        r = e.add_area([(xa, y0, za), (xb, y0, zb), (xb, y1, zb), (xa, y1, za)], rad)
        e.assign_area_spring(r, spring)
        e.area_load(r, "EAU", GAMMA_EAU * (Z_REBORD - (za + zb) / 2))      # poids de l'eau (moyenne de la zone)
        rafts.append(r)
    for xn in NERV_RADIER_X:
        sec = e.ensure_rect("NERV RAD 35x75", NERV_RADIER[0], NERV_RADIER[1], "beam", mat, reb)
        z = z_fond(xn)
        e.add_frame((xn, y0, z), (xn, y1, z), sec)
    # voiles : bandes horizontales (pression hydrostatique 10·(1.39 − z) vers l'extérieur)
    xc, yc = (X_VOILES[0] + X_VOILES[1]) / 2, (y0 + y1) / 2
    walls = 0

    def wall_strip(a, b, za, zb, ztop_a, ztop_b, outward):
        nonlocal walls
        pts = [(a[0], a[1], za), (b[0], b[1], zb), (b[0], b[1], ztop_b), (a[0], a[1], ztop_a)]
        pts = [q for i, q in enumerate(pts) if all(abs(q[k] - pts[i - 1][k]) > 1e-6 for k in (2,)) or
               any(abs(q[k] - pts[i - 1][k]) > 1e-6 for k in (0, 1))]          # drop coincident corners
        if len(pts) < 3:
            return
        ar = e.add_area(pts, voi)
        zm = (za + zb + ztop_a + ztop_b) / 4
        p = GAMMA_EAU * max(Z_REBORD - zm, 0.0)
        n = local3(e, ar)
        sign = 1.0 if (n[0] * outward[0] + n[1] * outward[1]) > 0 else -1.0
        if p > 0:
            e.m.AreaObj.SetLoadUniform(ar, "EAU", sign * p, 3, False, "Local", e.E.eItemType.Objects)
        walls += 1

    def wall_bands(a, b, zbot_a, zbot_b, outward):
        z_lo = max(zbot_a, zbot_b)
        # bande inférieure (suit le fond), puis bandes horizontales jusqu'au rebord
        levels = [z_lo]
        while levels[-1] + BANDE_EAU < Z_REBORD - 1e-6:
            levels.append(levels[-1] + BANDE_EAU)
        levels.append(Z_REBORD)
        wall_strip(a, b, zbot_a, zbot_b, levels[0], levels[0], outward) if abs(zbot_a - zbot_b) > 1e-6 else None
        for z0, z1 in zip(levels, levels[1:]):
            wall_strip(a, b, z0, z0, z1, z1, outward)

    # voiles d'extrémité (x = cste)
    wall_bands((X_VOILES[0], y0), (X_VOILES[0], y1), z_fond(X_VOILES[0]), z_fond(X_VOILES[0]), (-1, 0))
    wall_bands((X_VOILES[1], y0), (X_VOILES[1], y1), z_fond(X_VOILES[1]), z_fond(X_VOILES[1]), (1, 0))
    # voiles latéraux (y = cste), découpés comme le radier pour suivre la pente
    for yw, out in ((y0, (0, -1)), (y1, (0, 1))):
        for xa, xb in zip(xs, xs[1:]):
            wall_bands((xa, yw), (xb, yw), z_fond(xa), z_fond(xb), out)
    # maillage automatique
    for name in list(e.m.AreaObj.GetNameList(0, None)[2] or []):
        try:
            e.m.AreaObj.SetAutoMesh(name, 1, 0, 0, True, True, True, True, False, 1.0, 1.0, False, False, False,
                                    False, False, "ALL", e.E.eItemType.Objects)
        except Exception:  # noqa: BLE001
            pass
    e.refresh()
    print(f"OK : {nf} fûts (−3.75 → ±0.00 / +1.44), {len(NERVURES)} nervures/longrines à −3.75, "
          f"radier en {len(rafts)} panneaux (−2.11 → 12 % → 11 % → −0.14) sur ressorts ks = {KS:.0f} kN/m³, "
          f"{len(NERV_RADIER_X)} nervures sous radier, {walls} bandes de voile (rebord +1.39) chargées par l'eau.")


if __name__ == "__main__":
    main(globals().get("e"))
