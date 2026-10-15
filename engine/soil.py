"""Soil bearing capacity: DTR BC 2.331 (4 methods) and Eurocode 7 (Annex D)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .references import ref
from .trace import Trace, fmt

METHODS = {
    "adm": "Contrainte admissible σadm (rapport de sol)",
    "cphi": "Calcul à partir de c, φ, γ (Terzaghi / DTR)",
    "pressio": "Essai pressiométrique (ple*, kp)",
    "penetro": "Essai pénétrométrique (qce, kc)",
}


@dataclass
class Soil:
    method: str            # adm | cphi | pressio | penetro
    D: float               # m, depth of footing base below ground
    gamma_r: float         # kN/m3, backfill above footing
    gamma: float = 18.0    # kN/m3, soil below the footing (cphi)
    sigma_adm: float = 0.0  # kPa (method adm)
    k_elu: float = 1.5     # q_ELU = k_elu·σadm (method adm)
    k_acc: float = 1.5     # q_ACC = k_acc·σadm (method adm)
    c: float = 0.0         # kPa
    phi: float = 0.0       # degrees
    pl: float = 0.0        # ple* kPa
    kp: float = 0.0
    qc: float = 0.0        # qce kPa
    kc: float = 0.0
    fs_els: float = 3.0
    fs_elu: float = 2.0
    fs_acc: float = 2.0        # RPA 2024 §10.1.4
    phi_s: float = 0.0         # sliding: friction angle at the base (deg)
    c_s: float = 0.0           # sliding: cohesion at the base (kPa)
    gamma_R_v: float = 1.4     # EC7 DA2
    gamma_R_acc: float = 1.0   # EC7 accidental


def bearing_factors(phi_deg):
    p = math.radians(phi_deg)
    if phi_deg <= 0:
        return 1.0, math.pi + 2, 0.0
    Nq = math.exp(math.pi * math.tan(p)) * math.tan(math.pi / 4 + p / 2) ** 2
    Nc = (Nq - 1) / math.tan(p)
    Ng = 2 * (Nq - 1) * math.tan(p)
    return Nq, Nc, Ng


def capacities(soil: Soil, A, B, D, tr: Trace | None = None):
    """Return dict q_els, q_elu, q_acc (kPa) for the DTR BC 2.331 checks."""
    q0 = soil.gamma_r * D
    m = soil.method
    if m == "adm":
        qe = soil.sigma_adm
        out = dict(q0=q0, ql=None, q_els=qe, q_elu=soil.k_elu * qe, q_acc=soil.k_acc * qe)
        if tr:
            tr.step("Contrainte admissible du sol (rapport géotechnique)", "q_ELS = σadm", "",
                    f"{fmt(qe, 1)} kPa = {fmt(qe / 100, 2)} bar", ref("dtr_portance"))
            tr.step("Contrainte limite à l'ELU", "q_ELU = k_ELU·σadm", f"{fmt(soil.k_elu)} × {fmt(qe, 1)}",
                    f"{fmt(out['q_elu'], 1)} kPa", ref("dtr_portance"))
            tr.step("Contrainte limite sous combinaisons sismiques", "q_ACC = k_ACC·σadm  (σadm = Ql/3 → Ql/2,0 = 1,5·σadm)",
                    f"{fmt(soil.k_acc)} × {fmt(qe, 1)}", f"{fmt(out['q_acc'], 1)} kPa", ref("rpa_portance"))
        return out

    if tr:
        tr.step("Contrainte verticale des terres au niveau de l'assise", "q₀ = γr·D",
                f"{fmt(soil.gamma_r, 1)} × {fmt(D)}", f"{fmt(q0, 1)} kPa")
    if m == "cphi":
        Bm, Lm = min(A, B), max(A, B)
        Nq, Nc, Ng = bearing_factors(soil.phi)
        sg, sc, sq = 1 - 0.2 * Bm / Lm, 1 + 0.2 * Bm / Lm, 1.0
        ql = 0.5 * sg * soil.gamma * Bm * Ng + sc * soil.c * Nc + sq * q0 * Nq
        if tr:
            tr.step("Facteurs de capacité portante", "Nq = e^(π·tanφ)·tan²(π/4 + φ/2) ; Nc = (Nq − 1)·cotφ ; Nγ = 2(Nq − 1)·tanφ",
                    f"φ = {fmt(soil.phi, 1)}°", f"Nq = {fmt(Nq)} ; Nc = {fmt(Nc)} ; Nγ = {fmt(Ng)}", ref("dtr_cphi"))
            tr.step("Coefficients de forme (semelle rectangulaire)", "sγ = 1 − 0,2·B/L ; sc = 1 + 0,2·B/L ; sq = 1",
                    f"B/L = {fmt(Bm)}/{fmt(Lm)} = {fmt(Bm / Lm, 3)}", f"sγ = {fmt(sg, 3)} ; sc = {fmt(sc, 3)}", ref("dtr_cphi"))
            tr.step("Contrainte de rupture", "ql = ½·sγ·γ·B·Nγ + sc·c·Nc + sq·q₀·Nq",
                    f"0,5 × {fmt(sg, 3)} × {fmt(soil.gamma, 1)} × {fmt(Bm)} × {fmt(Ng)} + {fmt(sc, 3)} × {fmt(soil.c, 1)} × {fmt(Nc)}"
                    f" + {fmt(q0, 1)} × {fmt(Nq)}", f"{fmt(ql, 1)} kPa", ref("dtr_cphi"))
    elif m == "pressio":
        ql = q0 + soil.kp * soil.pl
        if tr:
            tr.step("Contrainte de rupture (méthode pressiométrique)", "ql = q₀ + kp·ple*",
                    f"{fmt(q0, 1)} + {fmt(soil.kp, 3)} × {fmt(soil.pl, 1)}", f"{fmt(ql, 1)} kPa", ref("dtr_pressio"))
    elif m == "penetro":
        ql = q0 + soil.kc * soil.qc
        if tr:
            tr.step("Contrainte de rupture (méthode pénétrométrique)", "ql = q₀ + kc·qce",
                    f"{fmt(q0, 1)} + {fmt(soil.kc, 3)} × {fmt(soil.qc, 1)}", f"{fmt(ql, 1)} kPa", ref("dtr_penetro"))
    else:
        raise ValueError(f"Méthode de sol inconnue : {m}")

    q_els = q0 + (ql - q0) / soil.fs_els
    q_elu = q0 + (ql - q0) / soil.fs_elu
    q_acc = q0 + (ql - q0) / soil.fs_acc
    if tr:
        tr.step("Contrainte admissible à l'ELS", "q_ELS = q₀ + (ql − q₀)/Fs,ELS",
                f"{fmt(q0, 1)} + ({fmt(ql, 1)} − {fmt(q0, 1)}) / {fmt(soil.fs_els, 1)}",
                f"{fmt(q_els, 1)} kPa = {fmt(q_els / 100)} bar", ref("dtr_portance"))
        tr.step("Contrainte limite à l'ELU", "q_ELU = q₀ + (ql − q₀)/Fs,ELU",
                f"{fmt(q0, 1)} + ({fmt(ql, 1)} − {fmt(q0, 1)}) / {fmt(soil.fs_elu, 1)}",
                f"{fmt(q_elu, 1)} kPa = {fmt(q_elu / 100)} bar", ref("dtr_portance"))
        tr.step("Contrainte limite sous combinaisons sismiques", "q_ACC = q₀ + (ql − q₀)/2,0",
                f"{fmt(q0, 1)} + ({fmt(ql, 1)} − {fmt(q0, 1)}) / {fmt(soil.fs_acc, 1)}",
                f"{fmt(q_acc, 1)} kPa = {fmt(q_acc / 100)} bar", ref("rpa_portance"))
    return dict(q0=q0, ql=ql, q_els=q_els, q_elu=q_elu, q_acc=q_acc)


def ec7_resistance(soil: Soil, A, B, D, ex, ey, V, H, acc=False, tr: Trace | None = None):
    """EN 1997-1 Annex D bearing resistance with effective area. Returns (R, Rd)."""
    Ae, Be = A - 2 * ex, B - 2 * ey
    if Ae <= 0 or Be <= 0 or V <= 0:
        return 0.0, 0.0
    Bp, Lp = min(Ae, Be), max(Ae, Be)
    Aeff = Ae * Be
    q = soil.gamma_r * D
    gR = soil.gamma_R_acc if acc else soil.gamma_R_v
    if soil.phi <= 0:  # undrained, c = cu
        cu = soil.c
        sc = 1 + 0.2 * Bp / Lp
        ratio = min(H / (Aeff * cu), 1.0) if cu > 0 else 1.0
        ic = 0.5 * (1 + math.sqrt(1 - ratio))
        rA = (math.pi + 2) * cu * sc * ic + q
        sym = "R/A' = (π + 2)·cu·sc·ic + q"
        num = f"(π + 2) × {fmt(cu, 1)} × {fmt(sc, 3)} × {fmt(ic, 3)} + {fmt(q, 1)}"
        det = f"sc = 1 + 0,2·B'/L' = {fmt(sc, 3)} ; ic = ½(1 + √(1 − H/(A'·cu))) = {fmt(ic, 3)}"
    else:
        p = math.radians(soil.phi)
        Nq, Nc, Ng = bearing_factors(soil.phi)
        sq = 1 + Bp / Lp * math.sin(p)
        sg = 1 - 0.3 * Bp / Lp
        sc = (sq * Nq - 1) / (Nq - 1)
        mexp = (2 + Bp / Lp) / (1 + Bp / Lp)
        base = max(1 - H / (V + Aeff * soil.c / math.tan(p)), 0.0)
        iq, ig = base ** mexp, base ** (mexp + 1)
        ic = iq - (1 - iq) / (Nc * math.tan(p))
        rA = soil.c * Nc * sc * ic + q * Nq * sq * iq + 0.5 * soil.gamma * Bp * Ng * sg * ig
        sym = "R/A' = c·Nc·sc·ic + q'·Nq·sq·iq + ½·γ'·B'·Nγ·sγ·iγ"
        num = (f"{fmt(soil.c, 1)}×{fmt(Nc)}×{fmt(sc, 3)}×{fmt(ic, 3)} + {fmt(q, 1)}×{fmt(Nq)}×{fmt(sq, 3)}×{fmt(iq, 3)}"
               f" + 0,5×{fmt(soil.gamma, 1)}×{fmt(Bp)}×{fmt(Ng)}×{fmt(sg, 3)}×{fmt(ig, 3)}")
        det = (f"Nq = {fmt(Nq)}, Nc = {fmt(Nc)}, Nγ = {fmt(Ng)} ; sq = 1 + (B'/L')·sinφ = {fmt(sq, 3)} ; "
               f"sγ = 1 − 0,3·B'/L' = {fmt(sg, 3)} ; sc = (sq·Nq − 1)/(Nq − 1) = {fmt(sc, 3)} ; "
               f"m = {fmt(mexp, 3)} ; iq = {fmt(iq, 3)} ; iγ = {fmt(ig, 3)} ; ic = {fmt(ic, 3)}")
    R = rA * Aeff
    Rd = R / gR
    if tr:
        tr.step("Dimensions effectives (EC7)", "A' = A − 2·eₓ ; B' = B − 2·e_y",
                f"A' = {fmt(A)} − 2×{fmt(ex, 3)} ; B' = {fmt(B)} − 2×{fmt(ey, 3)}",
                f"A' = {fmt(Ae, 3)} m ; B' = {fmt(Be, 3)} m ; A'·B' = {fmt(Aeff, 3)} m²", ref("ec7_bearing"))
        tr.step("Coefficients EC7", "", det, "", ref("ec7_bearing"))
        tr.step("Résistance unitaire", sym, num, f"{fmt(rA, 1)} kPa", ref("ec7_bearing"))
        tr.step("Résistance de calcul", "Rd = A'·(R/A') / γR,v",
                f"{fmt(Aeff, 3)} × {fmt(rA, 1)} / {fmt(gR, 2)}", f"{fmt(Rd, 1)} kN", ref("ec7_bearing"))
    return R, Rd
