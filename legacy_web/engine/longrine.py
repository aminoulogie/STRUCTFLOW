"""Tie beams (longrines) — RPA."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .footing import BARS
from .materials import Materials
from .references import ref
from .trace import Trace, fmt


@dataclass
class LongrineInput:
    alpha: float          # RPA coefficient α
    b: float              # m
    h: float              # m
    L: float = 0.0        # m, span for self-weight bending (0 = ignore)
    q_add: float = 0.0    # kN/m additional load (wall…)
    rho_min: float = 0.6  # %
    b_min: float = 0.25
    h_min: float = 0.30


def design_longrine(li: LongrineInput, Nmax, mat: Materials, tr: Trace | None = None):
    ss = mat.sigma_s()
    F = max(Nmax / li.alpha, 20.0)
    As_t = 10 * F / ss
    M, As_f, q = 0.0, 0.0, 0.0
    d = li.h - mat.cover - 0.01
    if li.L > 0:
        q = 1.35 * (mat.gamma_c * li.b * li.h + li.q_add)
        M = q * li.L ** 2 / 8
        As_f = 10 * M / (0.9 * d * ss)
    As_req = As_t + As_f
    As_min = li.rho_min / 100 * li.b * li.h * 1e4
    As = max(As_req, As_min)
    choice = None
    for phi in (12, 14, 16, 20):
        for n in (4, 6, 8):
            if n * BARS[phi] >= As - 1e-9:
                choice = dict(n=n, phi=phi, As=n * BARS[phi])
                break
        if choice:
            break
    st = min(0.20, 15 * choice["phi"] / 1000)
    phit = max(8, math.ceil(choice["phi"] / 3))
    ok_dim = li.b >= li.b_min - 1e-9 and li.h >= li.h_min - 1e-9
    if tr:
        tr.step("Section minimale de la longrine", f"b × h ≥ {fmt(li.b_min * 100, 0)} × {fmt(li.h_min * 100, 0)} cm²", "",
                f"{fmt(li.b * 100, 0)} × {fmt(li.h * 100, 0)} cm²", ref("rpa_longrine"), ok_dim,
                f"{fmt(li.b * 100, 0)} × {fmt(li.h * 100, 0)} ≥ {fmt(li.b_min * 100, 0)} × {fmt(li.h_min * 100, 0)}")
        tr.step("Effort de traction (RPA)", "F = N/α ≥ 20 kN", f"max({fmt(Nmax)} / {fmt(li.alpha, 0)} ; 20)",
                f"{fmt(F)} kN", ref("rpa_longrine"))
        tr.step("Armatures de traction", "As,t = F/σs", f"{fmt(F)} / {fmt(ss / 10, 2)}", f"{fmt(As_t)} cm²", ref("sigma_s"))
        if li.L > 0:
            tr.step("Flexion sous poids propre (+ charge additionnelle), ELU",
                    "q = 1,35·(γc·b·h + q_add) ; M = q·L²/8 ; As,f = M/(0,9·d·σs)",
                    f"q = {fmt(q)} kN/m ; M = {fmt(q)} × {fmt(li.L)}²/8 = {fmt(M)} kN·m ; d = {fmt(d, 3)} m",
                    f"{fmt(As_f)} cm²", ref("flexion"))
        tr.step("Armatures minimales", f"As,min = {fmt(li.rho_min, 1)} %·b·h",
                f"{fmt(li.rho_min / 100, 3)} × {fmt(li.b * 100, 0)} × {fmt(li.h * 100, 0)}", f"{fmt(As_min)} cm²", ref("rpa_longrine"))
        tr.step("Section retenue", "As = max(As,t + As,f ; As,min)", f"max({fmt(As_req)} ; {fmt(As_min)})",
                f"{fmt(As)} cm² → {choice['n']} HA{choice['phi']} = {fmt(choice['As'])} cm²", ref("rpa_longrine"),
                choice["As"] >= As - 1e-9, f"{fmt(choice['As'])} ≥ {fmt(As)} cm²")
        tr.step("Armatures transversales", "φt ≥ φl/3 ; St ≤ min(20 cm ; 15·φl)",
                f"min(20 ; 15 × {choice['phi'] / 10:.1f})", f"cadres HA{phit} — St = {fmt(st * 100, 0)} cm", ref("rpa_longrine"))
    return dict(F=F, As_t=As_t, As_f=As_f, M=M, As_min=As_min, As=As, bars=choice, st=st, phit=phit, ok=ok_dim)
