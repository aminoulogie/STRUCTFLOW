"""Isolated rectangular footing + RC pedestal under a steel column.

Units: kN, m, kPa (= kN/m²), materials in MPa, steel areas in cm².
Axes: A = footing dimension along x, B along y; pedestal ap (x) × bp (y).
Sign convention of actions at the top of the pedestal: N > 0 compression,
Mx about x (eccentricity along y, compared with B), My about y (along x, compared with A).
Moments at the footing underside:  My,b = My + Vx·H ;  Mx,b = Mx − Vy·H.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .combos import Combo
from .materials import Materials
from .references import ref
from .soil import Soil, capacities, ec7_resistance
from .trace import Trace, fmt

BARS = {8: 0.503, 10: 0.785, 12: 1.131, 14: 1.539, 16: 2.011, 20: 3.142, 25: 4.909, 32: 8.042}  # cm²
INF = float("inf")


def ceil_to(x, step=0.05):
    return round(math.ceil(x / step - 1e-9) * step, 3)


@dataclass
class Codes:
    rc: str = "BAEL 91 mod.99"            # | "CBA 93"
    bearing: str = "DTR BC 2.331"         # | "Eurocode 7 (DA2)"
    seismic: str = "RPA 2024"             # | "RPA 99/2003"
    overturning: str = "RPA + classique"  # | "RPA seul"
    uplift: str = "Classique"             # | "Eurocode 7 (UPL)"

    @property
    def ec7_bearing(self):
        return self.bearing.lower().startswith("euro")

    @property
    def ec7_uplift(self):
        return self.uplift.lower().startswith("euro")


@dataclass
class Options:
    h_min: float = 0.40
    step: float = 0.05
    fs_overturn: float = 1.5
    ovt_types: tuple = ("ELS", "ELU")   # combination types checked with the classic safety factor
    fs_uplift_els: float = 1.5
    fs_uplift_elu: float = 1.0
    phi_assumed: float = 0.014
    s_min: float = 0.10
    phi_min: int = 12
    rho_min_ped: float = 0.9   # %
    s_max_ped: float = 0.25
    homothetic: bool = True
    max_size: float = 8.0


@dataclass
class GroupInput:
    name: str
    ap: float
    bp: float
    plate_a: float
    plate_b: float
    h_above: float
    base: str = "Encastré"
    A: float | None = None
    B: float | None = None
    h: float | None = None
    D: float | None = None
    joints: list = field(default_factory=list)

    @property
    def pinned(self):
        return self.base.lower().startswith("art")


@dataclass
class Geo:
    A: float
    B: float
    h: float
    D: float
    ap: float
    bp: float
    h_above: float
    gc: float
    gr: float

    @property
    def Hp(self):
        return self.D - self.h + self.h_above

    @property
    def lever(self):
        return self.D + self.h_above

    @property
    def Wf(self):
        return self.gc * self.A * self.B * self.h

    @property
    def Wp(self):
        return self.gc * self.ap * self.bp * self.Hp

    @property
    def Ws(self):
        return self.gr * (self.A * self.B - self.ap * self.bp) * max(self.D - self.h, 0)

    @property
    def W(self):
        return self.Wf + self.Wp + self.Ws

    def dir(self, key):
        """(L, width, pedestal dim, symbol of L, symbol of width, symbol of l)"""
        if key == "X":
            return self.A, self.B, self.ap, "A", "B", "ap"
        return self.B, self.A, self.bp, "B", "A", "bp"


def base_moment(c: Combo, geo: Geo, key, lever=None):
    H = geo.lever if lever is None else lever
    if key == "X":
        return c.My + c.Vx * H, "My,b = My + Vx·H", f"{fmt(c.My)} + ({fmt(c.Vx)}) × {fmt(H)}"
    return c.Mx - c.Vy * H, "Mx,b = Mx − Vy·H", f"{fmt(c.Mx)} − ({fmt(c.Vy)}) × {fmt(H)}"


# ------------------------------------------------------------------ soil pressure
def pressure(N, e, L, W):
    """Linear soil pressure along L (width W) for a resultant N at eccentricity e.
    σ(s) = max(0, σmax − k·s), s measured from the most loaded edge."""
    if N <= 0:
        return dict(regime="N ≤ 0", smax=0.0, smin=0.0, s34=0.0, k=0.0, x=0.0)
    if e <= L / 6 + 1e-9:
        smax = N / (L * W) * (1 + 6 * e / L)
        smin = N / (L * W) * (1 - 6 * e / L)
        return dict(regime="uniforme" if e < 1e-6 else "trapèze", smax=smax, smin=smin,
                    s34=(3 * smax + smin) / 4, k=(smax - smin) / L, x=L)
    if e < L / 2:
        x = 3 * (L / 2 - e)
        smax = 2 * N / (W * x)
        return dict(regime="triangle", smax=smax, smin=0.0, s34=0.75 * smax, k=smax / x, x=x)
    return dict(regime="instable (e ≥ L/2)", smax=INF, smin=0.0, s34=INF, k=0.0, x=0.0)


def integrate(p, l1, W):
    """Resultant and moment, about a section at l1 from the most loaded edge, of the pressure over [0, l1]."""
    smax, k = p["smax"], p["k"]
    if smax <= 0 or math.isinf(smax):
        return 0.0, 0.0
    s = l1 if k <= 0 else min(l1, smax / k)
    F = W * (smax * s - k * s ** 2 / 2)
    M = W * (smax * (l1 * s - s ** 2 / 2) - k * (l1 * s ** 2 / 2 - s ** 3 / 3))
    return F, M


def _pressure_steps(tr, N, e, L, W, Ls, Ws, tag):
    p = pressure(N, e, L, W)
    if p["regime"] in ("uniforme", "trapèze"):
        tr.step(f"Diagramme des contraintes {tag} : e = {fmt(e, 3)} m ≤ {Ls}/6 = {fmt(L / 6, 3)} m → {p['regime']}",
                f"σmax,min = N/({Ls}·{Ws})·(1 ± 6e/{Ls})",
                f"{fmt(N)}/({fmt(L)}×{fmt(W)}) × (1 ± 6×{fmt(e, 3)}/{fmt(L)})",
                f"σmax = {fmt(p['smax'], 1)} kPa ; σmin = {fmt(p['smin'], 1)} kPa", ref("dtr_trapeze"))
    elif p["regime"] == "triangle":
        tr.step(f"Diagramme des contraintes {tag} : e = {fmt(e, 3)} m > {Ls}/6 = {fmt(L / 6, 3)} m → triangle (soulèvement partiel)",
                f"σmax = 2N / (3·{Ws}·({Ls}/2 − e)) ; σmin = 0",
                f"2 × {fmt(N)} / (3 × {fmt(W)} × ({fmt(L)}/2 − {fmt(e, 3)}))",
                f"σmax = {fmt(p['smax'], 1)} kPa ; longueur comprimée = {fmt(p['x'], 3)} m", ref("dtr_trapeze"))
    else:
        tr.step(f"Diagramme des contraintes {tag}", "e ≥ L/2", f"e = {fmt(e, 3)} m ; {Ls}/2 = {fmt(L / 2, 3)} m",
                "semelle instable", ref("dtr_trapeze"), False, "résultante hors de la semelle")
    return p


# ------------------------------------------------------------------ geotechnical checks
def check_bearing(geo: Geo, c: Combo, caps, soil: Soil, codes: Codes, tr: Trace | None = None):
    g = c.g_unf
    Nt = c.N + g * geo.W
    Myb, sMy, nMy = base_moment(c, geo, "X")
    Mxb, sMx, nMx = base_moment(c, geo, "Y")
    row = dict(combo=c.name, type=c.ctype, joint=c.joint, Nt=Nt, Myb=Myb, Mxb=Mxb)
    if tr:
        tr.step("Effort normal total à la base (poids propre semelle + fût + remblai inclus)",
                "Nt = N + γG·(Wf + Wp + Ws)", f"{fmt(c.N)} + {fmt(g, 2)} × {fmt(geo.W)}", f"{fmt(Nt)} kN")
        tr.step("Moments ramenés à la sous-face de la semelle (H = D + h₀)", f"{sMy} ; {sMx}",
                f"My,b = {nMy} ; Mx,b = {nMx}", f"My,b = {fmt(Myb)} kN·m ; Mx,b = {fmt(Mxb)} kN·m")
    if Nt <= 0:
        row.update(ex=None, ey=None, regX="N ≤ 0", regY="N ≤ 0", s34=0.0, q=None, ratio=0.0, ok=True,
                   note="traction globale – voir soulèvement")
        if tr:
            tr.para("Nt ≤ 0 : la semelle est soulevée, pas de contrainte sur le sol. Voir vérification au soulèvement.", "warn")
        return row
    ex, ey = abs(Myb) / Nt, abs(Mxb) / Nt
    use_ec7 = codes.ec7_bearing and c.ctype in ("ELU", "ACC") and soil.method == "cphi"
    if tr:
        tr.step("Excentricités", "eₓ = |My,b|/Nt ; e_y = |Mx,b|/Nt",
                f"eₓ = {fmt(abs(Myb))}/{fmt(Nt)} ; e_y = {fmt(abs(Mxb))}/{fmt(Nt)}",
                f"eₓ = {fmt(ex, 3)} m ; e_y = {fmt(ey, 3)} m")
    if use_ec7:
        H = math.hypot(c.Vx, c.Vy)
        R, Rd = ec7_resistance(soil, geo.A, geo.B, geo.D, ex, ey, Nt, H, c.acc, tr)
        ratio = Nt / Rd if Rd > 0 else INF
        row.update(ex=ex, ey=ey, regX="EC7", regY="EC7", s34=Nt, q=Rd, ratio=ratio, ok=ratio <= 1.0,
                   note="EC7 : Vd ≤ Rd (kN)")
        if tr:
            tr.step("Vérification de la portance (EC7)", "Vd ≤ Rd", "", f"taux = {fmt(ratio * 100, 1)} %",
                    ref("ec7_bearing"), ratio <= 1.0, f"Vd = {fmt(Nt)} kN ≤ Rd = {fmt(Rd)} kN")
        return row
    q = caps["q_" + c.ctype.lower()]
    if tr:
        pX = _pressure_steps(tr, Nt, ex, geo.A, geo.B, "A", "B", "selon x")
        pY = _pressure_steps(tr, Nt, ey, geo.B, geo.A, "B", "A", "selon y")
    else:
        pX, pY = pressure(Nt, ex, geo.A, geo.B), pressure(Nt, ey, geo.B, geo.A)
    s34 = max(pX["s34"], pY["s34"])
    ratio = s34 / q if q > 0 else INF
    row.update(ex=ex, ey=ey, regX=pX["regime"], regY=pY["regime"], sX=pX, sY=pY, s34=s34, q=q,
               ratio=ratio, ok=ratio <= 1.0 + 1e-9, note="")
    if tr:
        for p, tag in ((pX, "x"), (pY, "y")):
            if math.isinf(p["s34"]):
                continue
            tr.step(f"Contrainte de référence selon {tag} (règle des 3/4)", "σ₃/₄ = (3·σmax + σmin)/4",
                    f"(3 × {fmt(p['smax'], 1)} + {fmt(p['smin'], 1)}) / 4", f"{fmt(p['s34'], 1)} kPa", ref("dtr_trapeze"))
        tr.step(f"Vérification de la portance ({c.ctype})", f"σ₃/₄ ≤ q_{c.ctype}", "",
                f"taux = {fmt(ratio * 100, 1)} %", ref("dtr_trapeze"), row["ok"],
                f"σ₃/₄ = {fmt(s34, 1)} kPa ≤ q = {fmt(q, 1)} kPa ({fmt(q / 100)} bar)")
    return row


def check_overturning(geo: Geo, c: Combo, opts: Options, codes: Codes, tr: Trace | None = None):
    if c.ctype == "UPL":
        return None
    rpa = c.ctype == "ACC"
    if not rpa and (codes.overturning == "RPA seul" or c.ctype not in opts.ovt_types):
        return None
    Nt = c.N + c.g_fav * geo.W
    Myb, sMy, nMy = base_moment(c, geo, "X")
    Mxb, sMx, nMx = base_moment(c, geo, "Y")
    row = dict(combo=c.name, type=c.ctype, joint=c.joint, Nt=Nt, Myb=Myb, Mxb=Mxb, method="RPA" if rpa else "Fs")
    if tr:
        tr.step("Effort normal stabilisant (poids propres pris avec le coefficient favorable)",
                "Nt = N + γG,fav·W", f"{fmt(c.N)} + {fmt(c.g_fav, 2)} × {fmt(geo.W)}", f"{fmt(Nt)} kN")
        tr.step("Moments renversants à la base", f"{sMy} ; {sMx}", f"My,b = {nMy} ; Mx,b = {nMx}",
                f"My,b = {fmt(Myb)} kN·m ; Mx,b = {fmt(Mxb)} kN·m")
    if Nt <= 0:
        row.update(ratio=INF, ok=False, detail="Nt ≤ 0 : soulèvement")
        if tr:
            tr.step("Renversement", "Nt > 0", "", "", ref("rpa_renv" if rpa else "renv_classique"), False, f"Nt = {fmt(Nt)} kN ≤ 0")
        return row
    if rpa:
        ex, ey = abs(Myb) / Nt, abs(Mxb) / Nt
        ratio = max(ex / (geo.A / 4), ey / (geo.B / 4))
        row.update(ratio=ratio, ok=ratio <= 1 + 1e-9,
                   detail=f"eₓ={fmt(ex, 3)} ≤ A/4={fmt(geo.A / 4, 3)} ; e_y={fmt(ey, 3)} ≤ B/4={fmt(geo.B / 4, 3)}")
        if tr:
            tr.step("Renversement selon x (RPA)", "eₓ = |My,b|/Nt ≤ A/4", f"{fmt(abs(Myb))}/{fmt(Nt)}",
                    f"eₓ = {fmt(ex, 3)} m", ref("rpa_renv"), ex <= geo.A / 4 + 1e-9, f"{fmt(ex, 3)} m ≤ {fmt(geo.A / 4, 3)} m")
            tr.step("Renversement selon y (RPA)", "e_y = |Mx,b|/Nt ≤ B/4", f"{fmt(abs(Mxb))}/{fmt(Nt)}",
                    f"e_y = {fmt(ey, 3)} m", ref("rpa_renv"), ey <= geo.B / 4 + 1e-9, f"{fmt(ey, 3)} m ≤ {fmt(geo.B / 4, 3)} m")
        return row
    fsx = Nt * geo.A / 2 / abs(Myb) if abs(Myb) > 1e-6 else INF
    fsy = Nt * geo.B / 2 / abs(Mxb) if abs(Mxb) > 1e-6 else INF
    fs = min(fsx, fsy)
    ratio = opts.fs_overturn / fs if fs > 0 else INF
    row.update(ratio=ratio, ok=fs >= opts.fs_overturn - 1e-9, detail=f"Fsx={fmt(fsx)} ; Fsy={fmt(fsy)}")
    if tr:
        tr.step("Renversement autour de l'arête // y", "Fsₓ = Nt·(A/2) / |My,b| ≥ Fs", f"{fmt(Nt)} × {fmt(geo.A / 2)} / {fmt(abs(Myb))}",
                f"Fsₓ = {fmt(fsx)}", ref("renv_classique"), fsx >= opts.fs_overturn - 1e-9, f"{fmt(fsx)} ≥ {fmt(opts.fs_overturn)}")
        tr.step("Renversement autour de l'arête // x", "Fs_y = Nt·(B/2) / |Mx,b| ≥ Fs", f"{fmt(Nt)} × {fmt(geo.B / 2)} / {fmt(abs(Mxb))}",
                f"Fs_y = {fmt(fsy)}", ref("renv_classique"), fsy >= opts.fs_overturn - 1e-9, f"{fmt(fsy)} ≥ {fmt(opts.fs_overturn)}")
    return row


def check_uplift(geo: Geo, c: Combo, opts: Options, codes: Codes, has_upl: bool, tr: Trace | None = None):
    if c.N >= 0:
        return None
    if codes.ec7_uplift and has_upl and c.ctype != "UPL":
        return None
    if c.ctype == "UPL" and not codes.ec7_uplift:
        return None
    T = -c.N
    Wst = c.g_fav * geo.W
    fs = Wst / T
    req = 1.0 if c.ctype == "UPL" else (opts.fs_uplift_els if c.ctype == "ELS" else opts.fs_uplift_elu)
    row = dict(combo=c.name, type=c.ctype, joint=c.joint, T=T, Wst=Wst, fs=fs, req=req, ratio=req / fs, ok=fs >= req - 1e-9)
    if tr:
        tr.step("Poids propres stabilisants", "Wf = γc·A·B·h ; Wp = γc·ap·bp·Hp ; Ws = γr·(A·B − ap·bp)·(D − h)",
                f"Wf = {fmt(geo.Wf)} ; Wp = {fmt(geo.Wp)} ; Ws = {fmt(geo.Ws)}", f"W = {fmt(geo.W)} kN")
        rk = "ec7_upl" if c.ctype == "UPL" else "soulevement"
        tr.step("Effort de soulèvement (traction au pied du poteau)", "T = −N", f"−({fmt(c.N)})", f"{fmt(T)} kN")
        tr.step("Coefficient de sécurité au soulèvement", "Fs = γG,stb·W / T ≥ Fs,req",
                f"{fmt(c.g_fav, 2)} × {fmt(geo.W)} / {fmt(T)}", f"Fs = {fmt(fs)}", ref(rk), row["ok"],
                f"{fmt(fs)} ≥ {fmt(req)}")
    return row


# ------------------------------------------------------------------ RC design helpers
def design_mu(M, b, d, fbu, ss, mul):
    """BAEL simple bending, rectangular section b×d. M kN·m, stresses MPa. As in cm²."""
    mu = M / (b * d ** 2 * fbu * 1000)
    if mu >= 0.5:
        return dict(mu=mu, alpha=None, z=None, As=INF, ok=False)
    alpha = 1.25 * (1 - math.sqrt(1 - 2 * mu))
    z = d * (1 - 0.4 * alpha)
    As = 10 * M / (z * ss)
    return dict(mu=mu, alpha=alpha, z=z, As=As, ok=mu <= mul)


def design_els(M, b, d, ssb, sbcb):
    """Exact ELS design (n = 15) with σs = σ̄s. Returns y1, σbc, z, As (cm²)."""
    def Mr(y):
        sbc = ssb * y / (15 * (d - y))
        return 0.5 * b * y * sbc * (d - y / 3) * 1000
    lo, hi = 1e-6, d * (1 - 1e-6)
    for _ in range(200):
        mid = (lo + hi) / 2
        if Mr(mid) < M:
            lo = mid
        else:
            hi = mid
    y = (lo + hi) / 2
    sbc = ssb * y / (15 * (d - y))
    z = d - y / 3
    return dict(y1=y, sbc=sbc, z=z, As=10 * M / (z * ssb), ok=sbc <= sbcb + 1e-9)


def choose_bars(As, width, cover, smax, smin, phi_min):
    span = width - 2 * cover
    best = None
    for phi in (10, 12, 14, 16, 20, 25, 32):
        if phi < phi_min:
            continue
        a = BARS[phi]
        n = max(math.ceil(As / a - 1e-9), math.ceil(span / smax - 1e-9) + 1, 2)
        s = span / (n - 1)
        best = dict(n=n, phi=phi, s=s, As=n * a)
        if s >= smin - 1e-9:
            return best
    return best


# ------------------------------------------------------------------ RC footing, one direction / one combination
def rc_direction(geo: Geo, c: Combo, key, d, mat: Materials, tr: Trace | None = None):
    L, Wd, l, Ls, Ws, ls = geo.dir(key)
    Mb, sM, nM = base_moment(c, geo, key)
    els = c.ctype == "ELS"
    acc = c.acc
    g = c.g_unf
    Nrc = c.N + g * geo.Wp
    Nt = c.N + g * geo.W
    w = g * (geo.gc * geo.h + geo.gr * max(geo.D - geo.h, 0))
    l1 = L / 2 - 0.35 * l
    out = dict(combo=c.name, type=c.ctype, joint=c.joint, key=key, Nrc=Nrc, Nt=Nt, Mb=Mb, M1=None,
               As_biel=None, As_flex=None, As_top=None, mu=None, ok=True, note="")
    if els:
        ss = mat.sigma_s_bar
        if ss is None:
            return None
        sname = "σ̄s"
    else:
        ss = mat.sigma_s(acc)
        fbu = mat.fbu(acc)
        sname = "σs,acc" if acc else "σs"
    if tr:
        tr.step("Effort transmis par le fût (sans semelle ni remblai)", "Nu = N + γG·Wp",
                f"{fmt(c.N)} + {fmt(g, 2)} × {fmt(geo.Wp)}", f"{fmt(Nrc)} kN")
        tr.step("Moment à la sous-face de la semelle", sM, nM, f"{fmt(Mb)} kN·m")

    # ---- méthode des bielles
    if Nrc > 0:
        e0 = abs(Mb) / Nrc
        out["e0"] = e0
        if e0 <= L / 6 + 1e-9:
            Np = Nrc * (1 + 3 * e0 / L)
            As = 10 * Np * (L - l) / (8 * d * ss)
            out["As_biel"] = As
            if tr:
                tr.step("Excentricité de l'effort du fût", f"e₀ = |M|/Nu ≤ {Ls}/6",
                        f"{fmt(abs(Mb))}/{fmt(Nrc)} = {fmt(e0, 3)} m ; {Ls}/6 = {fmt(L / 6, 3)} m",
                        "méthode des bielles applicable", ref("bielles_exc"))
                tr.step("Effort majoré pour l'excentricité", f"N' = Nu·(1 + 3e₀/{Ls})",
                        f"{fmt(Nrc)} × (1 + 3 × {fmt(e0, 3)}/{fmt(L)})", f"{fmt(Np)} kN", ref("bielles_exc"))
                tr.step(f"Armatures // {Ls} — méthode des bielles", f"As = N'·({Ls} − {ls}) / (8·d·{sname})",
                        f"{fmt(Np)} × ({fmt(L)} − {fmt(l)}) / (8 × {fmt(d, 3)} × {fmt(ss / 10, 2)} kN/cm²)",
                        f"{fmt(As)} cm²", ref("bielles"))
        elif tr:
            tr.step("Excentricité de l'effort du fût", f"e₀ = |M|/Nu > {Ls}/6",
                    f"{fmt(abs(Mb))}/{fmt(Nrc)} = {fmt(e0, 3)} m > {fmt(L / 6, 3)} m",
                    "méthode des bielles non applicable → méthode des moments (S1)", ref("bielles_exc"))

    # ---- méthode des moments (console) à la section S1
    if Nt > 0:
        et = abs(Mb) / Nt
        p = pressure(Nt, et, L, Wd)
        if math.isinf(p["smax"]):
            out.update(ok=False, note="résultante hors semelle")
            if tr:
                tr.para("Résultante hors de la semelle : ferraillage impossible, augmenter les dimensions.", "warn")
            return out
        F, Ms = integrate(p, l1, Wd)
    else:
        p, F, Ms = None, 0.0, 0.0
    Mw = w * Wd * l1 ** 2 / 2
    M1 = Ms - Mw
    out["M1"] = M1
    if tr:
        tr.step("Position de la section S1 (à 0,35·b de l'axe du fût)", f"l₁ = {Ls}/2 − 0,35·{ls}",
                f"{fmt(L)}/2 − 0,35 × {fmt(l)}", f"{fmt(l1, 3)} m", ref("moment_S1"))
        if p:
            tr.step("Réaction du sol (Nt, e = |M|/Nt)", "σ(s) = σmax − k·s ≥ 0",
                    f"Nt = {fmt(Nt)} kN ; e = {fmt(et, 3)} m ; {p['regime']}",
                    f"σmax = {fmt(p['smax'], 1)} kPa ; σmin = {fmt(p['smin'], 1)} kPa")
        tr.step("Poids de la semelle et du remblai sur la console", "w = γG·(γc·h + γr·(D − h))",
                f"{fmt(g, 2)} × ({fmt(geo.gc, 1)} × {fmt(geo.h)} + {fmt(geo.gr, 1)} × {fmt(max(geo.D - geo.h, 0))})", f"{fmt(w, 2)} kPa")
        tr.step("Moment à la section S1", f"M₁ = {Ws}·∫₀^l₁ σ(s)·(l₁ − s)·ds − w·{Ws}·l₁²/2",
                f"{fmt(Ms)} − {fmt(w, 2)} × {fmt(Wd)} × {fmt(l1, 3)}² / 2", f"{fmt(M1)} kN·m", ref("moment_S1"))
    side = "inférieure" if M1 >= 0 else "supérieure"
    Mabs = abs(M1)
    if els:
        r = design_els(Mabs, Wd, d, ss, mat.sigma_bc_bar) if Mabs > 0 else None
        As = r["As"] if r else 0.0
        if tr and r:
            tr.step(f"Dimensionnement ELS (nappe {side}) — fissuration {mat.cracking}",
                    "σbc = σ̄s·y₁/(15(d − y₁)) ; M = ½·b·y₁·σbc·(d − y₁/3) ; As = M/(z·σ̄s), z = d − y₁/3",
                    f"b = {fmt(Wd)} m ; d = {fmt(d, 3)} m ; σ̄s = {fmt(ss)} MPa → y₁ = {fmt(r['y1'], 3)} m ; z = {fmt(r['z'], 3)} m",
                    f"As = {fmt(As)} cm²", ref("flexion_els"))
            tr.step("Contrainte du béton à l'ELS", "σbc ≤ σ̄bc = 0,6·fc28", "", f"σbc = {fmt(r['sbc'])} MPa",
                    ref("sigma_bc"), r["ok"], f"{fmt(r['sbc'])} ≤ {fmt(mat.sigma_bc_bar)} MPa")
        if r and not r["ok"]:
            out.update(ok=False, note="σbc > σ̄bc : augmenter h")
    else:
        mul = mat.mu_l(acc)
        r = design_mu(Mabs, Wd, d, fbu, ss, mul) if Mabs > 0 else None
        As = r["As"] if r else 0.0
        out["mu"] = r["mu"] if r else 0.0
        if tr and r:
            tr.step("Moment réduit", "μ = M₁/(b·d²·fbu)",
                    f"{fmt(Mabs / 1000, 4)} / ({fmt(Wd)} × {fmt(d, 3)}² × {fmt(fbu)})", f"μ = {fmt(r['mu'], 4)}",
                    ref("flexion"), r["ok"], f"μ = {fmt(r['mu'], 4)} ≤ μl = {fmt(mul, 3)} → pas d'acier comprimé")
            if r["alpha"] is not None:
                tr.step(f"Armatures // {Ls} — méthode des moments (nappe {side})",
                        f"α = 1,25(1 − √(1 − 2μ)) ; z = d(1 − 0,4α) ; As = M₁/(z·{sname})",
                        f"α = {fmt(r['alpha'], 4)} ; z = {fmt(r['z'], 3)} m ; As = {fmt(Mabs)} / ({fmt(r['z'], 3)} × {fmt(ss / 10, 2)})",
                        f"{fmt(As)} cm²", ref("flexion"))
        if r and not r["ok"]:
            out.update(ok=False, note="μ > μl : augmenter h")
    if M1 >= 0:
        out["As_flex"] = As
    else:
        out["As_top"] = As
        out["As_flex"] = 0.0
        if tr:
            tr.para(f"M₁ < 0 : la console est tendue en fibre supérieure (soulèvement) → nappe supérieure nécessaire.", "warn")
    return out


def check_shear(geo: Geo, c: Combo, key, d, mat: Materials, tr: Trace | None = None):
    """BAEL A.5.2.2 – only for flexible footings (d < (L − l)/4)."""
    L, Wd, l, Ls, Ws, ls = geo.dir(key)
    lv = L / 2 - l / 2 - d
    if lv <= 0 or c.ctype not in ("ELU", "ACC"):
        return None
    g = c.g_unf
    Nt = c.N + g * geo.W
    Mb, *_ = base_moment(c, geo, key)
    if Nt <= 0:
        return None
    p = pressure(Nt, abs(Mb) / Nt, L, Wd)
    if math.isinf(p["smax"]):
        return None
    F, _ = integrate(p, lv, Wd)
    w = g * (geo.gc * geo.h + geo.gr * max(geo.D - geo.h, 0))
    Vu = F - w * Wd * lv
    tau = Vu / (Wd * d) / 1000
    lim = 0.07 * mat.fc28 / mat.gb(c.acc)
    ok = tau <= lim
    if tr:
        tr.step(f"Effort tranchant à d du nu du fût (semelle flexible, direction {key})",
                "Vu = ∫ σ(s)·b·ds − w·b·lv ; τu = Vu/(b·d) ≤ 0,07·fc28/γb",
                f"lv = {fmt(lv, 3)} m ; Vu = {fmt(Vu)} kN ; τu = {fmt(Vu)}/({fmt(Wd)} × {fmt(d, 3)})",
                f"τu = {fmt(tau, 3)} MPa", ref("tau_u"), ok, f"{fmt(tau, 3)} ≤ {fmt(lim, 3)} MPa")
    return dict(combo=c.name, joint=c.joint, key=key, Vu=Vu, tau=tau, lim=lim, ratio=tau / lim, ok=ok)


def check_punching(geo: Geo, c: Combo, mat: Materials, tr: Trace | None = None):
    if c.ctype not in ("ELU", "ACC"):
        return None
    Nrc = c.N + c.g_unf * geo.Wp
    if Nrc <= 0:
        return None
    a2, b2 = geo.ap + 2 * geo.h, geo.bp + 2 * geo.h
    if a2 >= geo.A and b2 >= geo.B:
        if tr:
            tr.para("Le cône de poinçonnement (à 45°) déborde la semelle dans les deux directions : "
                    "pas de risque de poinçonnement.", "note")
        return dict(combo=c.name, joint=c.joint, Pu=0.0, Plim=INF, ratio=0.0, ok=True)
    Pu = Nrc * (1 - min(a2, geo.A) * min(b2, geo.B) / (geo.A * geo.B))
    uc = 2 * (geo.ap + geo.bp + 2 * geo.h)
    gb = mat.gb(c.acc)
    Plim = 0.045 * uc * geo.h * mat.fc28 / gb * 1000
    ok = Pu <= Plim
    if tr:
        tr.step("Charge de poinçonnement (déduction de la réaction du sol sous le cône à 45°)",
                "P'u = Nu·[1 − (ap + 2h)(bp + 2h)/(A·B)]",
                f"{fmt(Nrc)} × [1 − ({fmt(geo.ap)} + 2×{fmt(geo.h)})({fmt(geo.bp)} + 2×{fmt(geo.h)})/({fmt(geo.A)}×{fmt(geo.B)})]",
                f"{fmt(Pu)} kN", ref("punch"))
        tr.step("Périmètre du contour à mi-hauteur", "uc = 2·(ap + bp + 2h)",
                f"2 × ({fmt(geo.ap)} + {fmt(geo.bp)} + 2 × {fmt(geo.h)})", f"{fmt(uc, 3)} m", ref("punch"))
        tr.step("Vérification au poinçonnement", "P'u ≤ 0,045·uc·h·fc28/γb",
                f"0,045 × {fmt(uc, 3)} × {fmt(geo.h)} × {fmt(mat.fc28, 1)} / {fmt(gb, 2)} × 10³",
                f"P'lim = {fmt(Plim)} kN", ref("punch"), ok, f"{fmt(Pu)} kN ≤ {fmt(Plim)} kN")
    return dict(combo=c.name, joint=c.joint, Pu=Pu, Plim=Plim, ratio=Pu / Plim, ok=ok)


# ------------------------------------------------------------------ pedestal (fût / amorce poteau)
def pedestal_check(geo: Geo, c: Combo, mat: Materials, tr: Trace | None = None, keys=("X", "Y"), header=True):
    if c.ctype not in ("ELU", "ACC"):
        return None
    acc = c.acc
    fbu, ss, mul = mat.fbu(acc), mat.sigma_s(acc), mat.mu_l(acc)
    Hp = geo.Hp
    Np = c.N + c.g_unf * geo.Wp
    out = dict(combo=c.name, type=c.ctype, joint=c.joint, Np=Np, ok=True, note="")
    sig = Np / (geo.ap * geo.bp) / 1000
    out["sig"] = sig
    if tr and header:
        tr.step("Effort normal à la base du fût", "Np = N + γG·Wp", f"{fmt(c.N)} + {fmt(c.g_unf, 2)} × {fmt(geo.Wp)}", f"{fmt(Np)} kN")
        if Np > 0:
            tr.step("Compression moyenne du béton du fût (sans armatures)", "σ = Np/(ap·bp) ≤ fbu",
                    f"{fmt(Np)} / ({fmt(geo.ap)} × {fmt(geo.bp)}) × 10⁻³", f"{fmt(sig, 3)} MPa", ref("fbu"),
                    sig <= fbu, f"{fmt(sig, 3)} ≤ {fmt(fbu)} MPa")
    if sig > fbu:
        out.update(ok=False, note="compression excessive : agrandir le fût")
    for key, hd, bw, M, sym, num in (
            ("X", geo.ap, geo.bp, c.My + c.Vx * Hp, "My,p = My + Vx·Hp", f"{fmt(c.My)} + ({fmt(c.Vx)}) × {fmt(Hp)}"),
            ("Y", geo.bp, geo.ap, c.Mx - c.Vy * Hp, "Mx,p = Mx − Vy·Hp", f"{fmt(c.Mx)} − ({fmt(c.Vy)}) × {fmt(Hp)}")):
        d = hd - mat.cover - 0.01
        dp = mat.cover + 0.01
        M = abs(M)
        t = tr if key in keys else None
        if t:
            t.step(f"Moment à la base du fût (flexion selon {key})", sym, num, f"{fmt(M)} kN·m (valeur absolue)")
        if Np >= 0:
            Mua = M + Np * (d - hd / 2)
            r = design_mu(Mua, bw, d, fbu, ss, mul)
            As = max(0.0, r["As"] - 10 * Np / ss) if r["alpha"] is not None else INF
            if not r["ok"]:
                out.update(ok=False, note="μ > μl dans le fût : agrandir la section")
            if t:
                t.step(f"Flexion composée (section partiellement comprimée), face ⟂ {key}",
                        "Mua = M + N·(d − h/2) ; μ = Mua/(b·d²·fbu) ; As = Mua/(z·σs) − N/σs",
                        f"Mua = {fmt(M)} + {fmt(Np)} × ({fmt(d, 3)} − {fmt(hd / 2, 3)}) = {fmt(Mua)} ; μ = {fmt(r['mu'], 4)}"
                        + (f" ; z = {fmt(r['z'], 3)}" if r["z"] else ""),
                        f"As = {fmt(As)} cm² par face", ref("flexion"))
        else:
            As = 10 * (abs(Np) / (2 * ss) + M / ((d - dp) * ss))
            if t:
                t.step(f"Traction + flexion (section entièrement tendue), face ⟂ {key}",
                        "As = |N|/(2·σs) + M/((d − d')·σs)",
                        f"{fmt(abs(Np))}/(2 × {fmt(ss / 10, 2)}) + {fmt(M)}/(({fmt(d, 3)} − {fmt(dp, 3)}) × {fmt(ss / 10, 2)})",
                        f"As = {fmt(As)} cm² par face", ref("sigma_s"))
        out["As_" + key] = As
    return out


def choose_ped_bars(Afx, Afy, Amin, ap, bp, cover, smax, phi_min):
    for phi in (12, 14, 16, 20, 25, 32):
        if phi < phi_min:
            continue
        a = BARS[phi]
        nx = max(2, math.ceil(Afx / a - 1e-9), math.ceil((bp - 2 * cover) / smax - 1e-9) + 1)
        ny = max(2, math.ceil(Afy / a - 1e-9), math.ceil((ap - 2 * cover) / smax - 1e-9) + 1)
        while (2 * nx + 2 * ny - 4) * a < Amin - 1e-9:
            if nx <= ny:
                nx += 1
            else:
                ny += 1
        sx, sy = (bp - 2 * cover) / (nx - 1), (ap - 2 * cover) / (ny - 1)
        if min(sx, sy) >= 0.08 or phi == 32:
            n = 2 * nx + 2 * ny - 4
            return dict(phi=phi, n=n, nx=nx, ny=ny, As=n * a, sx=sx, sy=sy)


# ------------------------------------------------------------------ evaluation & sizing
def h_required(A, B, gi: GroupInput, mat: Materials, opts: Options):
    dreq = max((A - gi.ap) / 4, (B - gi.bp) / 4)
    return max(opts.h_min, ceil_to(dreq + mat.cover + 1.5 * opts.phi_assumed, opts.step))


def d_values(geo: Geo, mat: Materials, opts: Options):
    phi = opts.phi_assumed
    d1 = geo.h - mat.cover - phi / 2
    d2 = geo.h - mat.cover - 1.5 * phi
    return (d1, d2) if geo.A >= geo.B else (d2, d1)  # (dX, dY): bars // the longer side in the lower layer


def evaluate(geo: Geo, combos, mat: Materials, soil: Soil, codes: Codes, opts: Options):
    caps = capacities(soil, geo.A, geo.B, geo.D)
    has_upl = any(c.ctype == "UPL" for c in combos)
    bear = [check_bearing(geo, c, caps, soil, codes) for c in combos if c.ctype in ("ELU", "ELS", "ACC")]
    ovt = [r for c in combos if (r := check_overturning(geo, c, opts, codes))]
    upl = [r for c in combos if (r := check_uplift(geo, c, opts, codes, has_upl))]
    ok_b = all(r["ok"] for r in bear)
    ok_o = all(r["ok"] for r in ovt)
    ok_u = all(r["ok"] for r in upl)
    return dict(caps=caps, bear=bear, ovt=ovt, upl=upl, ok_b=ok_b, ok_o=ok_o, ok_u=ok_u, ok=ok_b and ok_o and ok_u)


def autosize(gi: GroupInput, combos, mat, soil, codes, opts, D):
    msgs = []
    r = gi.ap / gi.bp if opts.homothetic else 1.0
    Ns = [c.N for c in combos if c.ctype == "ELS"] or [c.N / 1.35 for c in combos]
    Nmax = max(max(Ns), 1.0)
    caps = capacities(soil, 1.0, 1.0, D)
    area = 1.15 * Nmax / max(caps["q_els"] - 20.0 * D, 10.0)  # ~20 kN/m³ average for footing + backfill
    B = ceil_to(max(math.sqrt(area / r), gi.bp + 0.30, 0.80), opts.step)
    A = ceil_to(max(r * B, gi.ap + 0.30), opts.step)
    while True:
        h = gi.h or h_required(A, B, gi, mat, opts)
        geo = Geo(A, B, h, D, gi.ap, gi.bp, gi.h_above, mat.gamma_c, soil.gamma_r)
        if h > D:
            msgs.append(f"h = {fmt(h)} m > D = {fmt(D)} m : augmenter la profondeur d'ancrage D.")
            return geo, msgs
        ev = evaluate(geo, combos, mat, soil, codes, opts)
        if ev["ok"]:
            return geo, msgs
        if max(A, B) >= opts.max_size:
            msgs.append(f"Dimension maximale {fmt(opts.max_size)} m atteinte sans satisfaire toutes les vérifications.")
            return geo, msgs
        B = ceil_to(B + opts.step, opts.step)
        A = ceil_to(max(r * B, A), opts.step)


@dataclass
class GroupResult:
    gi: GroupInput
    geo: Geo
    combos: list
    ev: dict
    rc: dict
    punch: list
    shear: list
    ped: dict
    msgs: list
    auto: bool

    @property
    def ok(self):
        return (self.ev["ok"] and self.rc["ok"] and all(p["ok"] for p in self.punch)
                and all(s["ok"] for s in self.shear) and self.ped["ok"])


def design_rc(geo: Geo, combos, mat: Materials, opts: Options):
    dX, dY = d_values(geo, mat, opts)
    res = dict(ok=True, d=dict(X=dX, Y=dY))
    for key, d in (("X", dX), ("Y", dY)):
        L, Wd, l, Ls, Ws, ls = geo.dir(key)
        rows = [r for c in combos if c.ctype in ("ELU", "ACC", "ELS") and (r := rc_direction(geo, c, key, d, mat))]
        ult = [r for r in rows if r["type"] != "ELS"]
        ser = [r for r in rows if r["type"] == "ELS"]

        def gov(rs, k):
            rs = [r for r in rs if r.get(k) is not None]
            return max(rs, key=lambda r: r[k]) if rs else None

        cand = dict(biel_u=gov(ult, "As_biel"), flex_u=gov(ult, "As_flex"),
                    biel_s=gov(ser, "As_biel"), flex_s=gov(ser, "As_flex"))
        Amin = 0.23 * Wd * d * mat.ft28 / mat.fe * 1e4
        vals = {k: (v[{"biel_u": "As_biel", "flex_u": "As_flex", "biel_s": "As_biel", "flex_s": "As_flex"}[k]] if v else 0.0)
                for k, v in cand.items()}
        vals["min"] = Amin
        As_req = max(vals.values())
        governs = max(vals, key=vals.get)
        top = gov(rows, "As_top")
        As_top = max(top["As_top"], Amin) if top else 0.0
        smax = mat.s_max(geo.h)
        bars = choose_bars(As_req, Wd, mat.cover, smax, opts.s_min, opts.phi_min)
        bars_top = choose_bars(As_top, Wd, mat.cover, smax, opts.s_min, opts.phi_min) if top else None
        ok = all(r["ok"] for r in rows)
        rigid = d >= (L - l) / 4 - 1e-9
        res[key] = dict(rows=rows, cand=cand, vals=vals, As_req=As_req, governs=governs, Amin=Amin, top=top,
                        As_top=As_top, bars=bars, bars_top=bars_top, smax=smax, ok=ok, rigid=rigid, d=d,
                        ls=mat.ls(bars["phi"] / 1000), L=L)
        res["ok"] = res["ok"] and ok
    return res


def design_group(gi: GroupInput, combos, mat: Materials, soil: Soil, codes: Codes, opts: Options) -> GroupResult:
    D = gi.D or soil.D
    msgs = []
    auto = not (gi.A and gi.B)
    if auto:
        geo, m = autosize(gi, combos, mat, soil, codes, opts, D)
        msgs += m
    else:
        h = gi.h or h_required(gi.A, gi.B, gi, mat, opts)
        geo = Geo(gi.A, gi.B, h, D, gi.ap, gi.bp, gi.h_above, mat.gamma_c, soil.gamma_r)
    ev = evaluate(geo, combos, mat, soil, codes, opts)
    rc = design_rc(geo, combos, mat, opts)
    punch = [p for c in combos if (p := check_punching(geo, c, mat))]
    shear = []
    for key in ("X", "Y"):
        if not rc[key]["rigid"]:
            shear += [s for c in combos if (s := check_shear(geo, c, key, rc["d"][key], mat))]
    ped_rows = [p for c in combos if (p := pedestal_check(geo, c, mat))]
    Afx = max([p["As_X"] for p in ped_rows] or [0.0])
    Afy = max([p["As_Y"] for p in ped_rows] or [0.0])
    Amin = opts.rho_min_ped / 100 * geo.ap * geo.bp * 1e4
    pb = choose_ped_bars(Afx, Afy, Amin, geo.ap, geo.bp, mat.cover, opts.s_max_ped, opts.phi_min)
    ped = dict(rows=ped_rows, Afx=Afx, Afy=Afy, Amin=Amin, bars=pb,
               ok=all(p["ok"] for p in ped_rows) and not math.isinf(Afx) and not math.isinf(Afy))
    if codes.ec7_bearing and soil.method != "cphi":
        msgs.append("Portance EC7 demandée mais le sol n'est pas défini par (c, φ) : vérification faite selon le DTR BC 2.331.")
    if codes.ec7_uplift and not any(c.ctype == "UPL" for c in combos):
        msgs.append("Soulèvement EC7 (UPL) demandé mais aucun cas de vent élémentaire (W) : vérification classique appliquée.")
    for key in ("X", "Y"):
        if not rc[key]["rigid"]:
            msgs.append(f"Semelle flexible selon {key} : d < (L − l)/4 → vérification de l'effort tranchant effectuée.")
    return GroupResult(gi, geo, combos, ev, rc, punch, shear, ped, msgs, auto)
