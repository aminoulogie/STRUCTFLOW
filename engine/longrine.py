"""Tie beams (longrines) — RPA 2024 §10.1.1."""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .footing import BARS
from .materials import Materials
from .references import RPA2024_ALPHA, RPA2024_LONGRINE_MIN, longrine_required, ref
from .trace import Trace, fmt


@dataclass
class LongrineInput:
    site: str             # S1..S4
    zone: str             # 0, I..VI
    A: float              # zone acceleration coefficient (RPA 2024 tableau 3.3)
    I: float              # importance coefficient (tableau 3.11)
    S: float              # site coefficient (tableaux 3.3 / 3.4)
    b: float              # m
    h: float              # m
    L: float = 0.0        # m, span for self-weight bending (0 = ignore)
    q_add: float = 0.0    # kN/m additional load (wall…)
    rho_min: float = 0.6  # %
    alpha: float | None = None   # override of α (None → eq. 10.2)

    @property
    def alpha_eff(self):
        return self.alpha if self.alpha else RPA2024_ALPHA.get(self.site) or 0.0

    @property
    def dims_min(self):
        return RPA2024_LONGRINE_MIN.get(self.site, (0.25, 0.30))


def design_longrine(li: LongrineInput, Nmean, mat: Materials, tr: Trace | None = None):
    ss = mat.sigma_s(True)        # seismic situation: γs = 1,00 (RPA 2024 §7.3.2)
    a = li.alpha_eff
    F = max(a * li.A * li.I * li.S * Nmean, 20.0)
    As_t = 10 * F / ss
    M, As_f, q = 0.0, 0.0, 0.0
    d = li.h - mat.cover - 0.01
    if li.L > 0:
        q = 1.35 * (mat.gamma_c * li.b * li.h + li.q_add)
        M = q * li.L ** 2 / 8
        As_f = 10 * M / (0.9 * d * mat.sigma_s())
    As_req = As_t + As_f
    As_min = li.rho_min / 100 * li.b * li.h * 1e4
    As = max(As_req, As_min)
    choice = None
    for phi in (12, 14, 16, 20, 25):
        for n in (4, 6, 8):
            if n * BARS[phi] >= As - 1e-9:
                choice = dict(n=n, phi=phi, As=n * BARS[phi])
                break
        if choice:
            break
    st = min(0.20, 15 * choice["phi"] / 1000)
    phit = max(8, math.ceil(choice["phi"] / 3))
    bmin, hmin = li.dims_min
    ok_dim = li.b >= bmin - 1e-9 and li.h >= hmin - 1e-9
    req = longrine_required(li.site, li.zone)
    if tr:
        if not req:
            tr.para(f"Site {li.site}, zone {li.zone} : la solidarisation par longrines n'est pas exigée (RPA 2024 §10.1.1 c). "
                    "Le calcul est néanmoins fourni.", "note")
        tr.para("Pour les structures légères (type hangar), les longrines peuvent être remplacées par le dallage "
                "travaillant en tirant ou en buton dans le sens transversal (RPA 2024 §10.1.1 d).", "note")
        tr.step("Section minimale de la longrine", f"b × h ≥ {fmt(bmin * 100, 0)} × {fmt(hmin * 100, 0)} cm (site {li.site})",
                "", f"{fmt(li.b * 100, 0)} × {fmt(li.h * 100, 0)} cm", ref("rpa_longrine"), ok_dim,
                f"{fmt(li.b * 100, 0)} × {fmt(li.h * 100, 0)} ≥ {fmt(bmin * 100, 0)} × {fmt(hmin * 100, 0)}")
        tr.step("Coefficient α (fonction de la catégorie de site)", "α = 0,3 (S2) ; 0,4 (S3) ; 0,6 (S4)", f"site {li.site}",
                f"α = {fmt(a, 2)}", ref("rpa_longrine_F"))
        tr.step("Effort axial de calcul (traction / compression)", "F = ±α·(A·I·S)·N ≥ 20 kN",
                f"max({fmt(a, 2)} × ({fmt(li.A, 3)} × {fmt(li.I, 2)} × {fmt(li.S, 2)}) × {fmt(Nmean)} ; 20)",
                f"F = {fmt(F)} kN", ref("rpa_longrine_F"))
        tr.step("Armatures pour l'effort axial (situation sismique)", "As,F = F/σs,acc",
                f"{fmt(F)} / {fmt(ss / 10, 2)}", f"{fmt(As_t)} cm²", ref("rpa_gamma"))
        if li.L > 0:
            tr.step("Flexion sous poids propre (+ charge additionnelle), ELU",
                    "q = 1,35·(γc·b·h + q_add) ; M = q·L²/8 ; As,f = M/(0,9·d·σs)",
                    f"q = {fmt(q)} kN/m ; M = {fmt(q)} × {fmt(li.L)}²/8 = {fmt(M)} kN·m ; d = {fmt(d, 3)} m",
                    f"{fmt(As_f)} cm²", ref("flexion"))
        tr.step("Armatures minimales", f"As,min = {fmt(li.rho_min, 1)} %·b·h",
                f"{fmt(li.rho_min / 100, 3)} × {fmt(li.b * 100, 0)} × {fmt(li.h * 100, 0)}", f"{fmt(As_min)} cm²",
                ref("rpa_longrine"))
        tr.step("Section retenue", "As = max(As,F + As,f ; As,min)", f"max({fmt(As_req)} ; {fmt(As_min)})",
                f"{fmt(As)} cm² → {choice['n']} HA{choice['phi']} = {fmt(choice['As'])} cm²", ref("rpa_longrine"),
                choice["As"] >= As - 1e-9, f"{fmt(choice['As'])} ≥ {fmt(As)} cm²")
        tr.step("Armatures transversales", "St < min(20 cm ; 15·φl)",
                f"min(20 ; 15 × {choice['phi'] / 10:.1f})", f"cadres HA{phit} — St = {fmt(st * 100, 0)} cm", ref("rpa_longrine"))
    return dict(F=F, alpha=a, As_t=As_t, As_f=As_f, M=M, As_min=As_min, As=As, bars=choice, st=st, phit=phit,
                ok=ok_dim, required=req)


def build_network(coords, dims, tol=0.30, lmax=12.0, dirs=("X", "Y")):
    """Bidirectional tie-beam network: each support is linked to its nearest aligned neighbour in +X and +Y.

    coords: {joint: (x, y)} in m ; dims: {joint: (ap, bp)} pedestal sizes in m.
    Returns list of dicts: id, j1, j2, dir, L (axis distance), Lc (clear span between pedestal faces), kept, why."""
    beams = []
    items = list(coords.items())
    for j, (x, y) in items:
        for d in dirs:
            if d == "X":
                cand = [(xk - x, k) for k, (xk, yk) in items if k != j and xk - x > tol and abs(yk - y) <= tol]
            else:
                cand = [(yk - y, k) for k, (xk, yk) in items if k != j and yk - y > tol and abs(xk - x) <= tol]
            if not cand:
                continue
            L, k = min(cand)
            a1, b1 = dims.get(j, (0.0, 0.0))
            a2, b2 = dims.get(k, (0.0, 0.0))
            Lc = L - ((a1 + a2) / 2 if d == "X" else (b1 + b2) / 2)
            kept = L <= lmax + 1e-9
            beams.append(dict(j1=j, j2=k, dir=d, L=L, Lc=max(Lc, 0.0), kept=kept,
                              why="" if kept else f"L > {lmax:g} m (dallage / non retenue)"))
    beams.sort(key=lambda b: (b["dir"], b["Lc"]))
    for i, b in enumerate(beams, 1):
        b["id"] = f"L{i}"
    return beams


def design_network(li: LongrineInput, beams, Nj, mat: Materials, step=0.05):
    """Group kept tie beams by clear span (rounded up to `step`) and design one type per span."""
    types = {}
    for b in beams:
        if not b["kept"]:
            continue
        b["N"] = (Nj.get(b["j1"], 0.0) + Nj.get(b["j2"], 0.0)) / 2
        key = round(math.ceil(b["Lc"] / step - 1e-9) * step, 2)
        b["type"] = key
        t = types.setdefault(key, dict(Lc=key, beams=[], N=0.0))
        t["beams"].append(b)
        t["N"] = max(t["N"], b["N"])
    out = []
    for k, (key, t) in enumerate(sorted(types.items()), 1):
        t["name"] = f"LG{k}"
        t["li"] = replace(li, L=key)
        t["res"] = design_longrine(t["li"], t["N"], mat)
        for b in t["beams"]:
            b["tname"] = t["name"]
        out.append(t)
    return out
