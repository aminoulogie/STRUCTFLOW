"""Load cases and combinations.

A combination is a set of factors applied to the user's own load cases (by name), e.g.
{"G": 1.0, "Q": 1.0, "Ex": 1.0, "Ey": 0.3}. The generator proposes a default set from the
case types (G/Q/S/W/E); every factor remains editable by the user.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

CATS = ["G", "Q", "S", "W", "E"]          # elementary load categories
DIRECT = ["ELU", "ELS", "ACC"]            # already-combined results
TYPES = CATS + DIRECT + ["Ignorer"]
CTYPES = ["ELU", "ELS", "ACC", "UPL"]
FORCES = ["N", "Vx", "Vy", "Mx", "My"]

# Templates used by the generator: name, type, {category: factor}.
# W is applied to each wind case in turn. Seismic combinations: see rpa2024_isolated().
TEMPLATES = [
    ("ELU1", "ELU", {"G": 1.35, "Q": 1.50}),
    ("ELU2", "ELU", {"G": 1.35, "S": 1.50}),
    ("ELU3", "ELU", {"G": 1.35, "W": 1.50}),
    ("ELU4", "ELU", {"G": 1.00, "W": 1.50}),
    ("ELU5", "ELU", {"G": 1.35, "Q": 1.35, "W": 1.35}),
    ("ELU6", "ELU", {"G": 1.35, "S": 1.35, "W": 1.35}),
    ("ELS1", "ELS", {"G": 1.00, "Q": 1.00}),
    ("ELS2", "ELS", {"G": 1.00, "S": 1.00}),
    ("ELS3", "ELS", {"G": 1.00, "W": 1.00}),
    ("ELS4", "ELS", {"G": 1.00, "Q": 0.90, "W": 0.90}),
]

# factor on footing/backfill self-weight when a combination has no G case: (unfavourable, favourable)
DIRECT_G = {"ELU": (1.35, 1.0), "ELS": (1.0, 1.0), "ACC": (1.0, 1.0), "UPL": (0.9, 0.9)}


@dataclass
class ComboDef:
    name: str
    ctype: str                                   # ELU | ELS | ACC | UPL
    factors: dict = field(default_factory=dict)  # load case name -> factor

    def label(self):
        out = ""
        for case, f in self.factors.items():
            if not f:
                continue
            sgn = "−" if f < 0 else "+"
            a = abs(f)
            term = case if a == 1 else f"{a:g}·{case}"
            out += (f" {sgn} " if out else ("−" if f < 0 else "")) + term
        return out or "—"


@dataclass
class Combo:
    name: str
    ctype: str          # ELU | ELS | ACC | UPL
    joint: str
    N: float
    Vx: float
    Vy: float
    Mx: float
    My: float
    g_unf: float        # factor on self-weight when unfavourable (bearing, RC)
    g_fav: float        # factor on self-weight when favourable (stability)
    formula: str = ""

    @property
    def acc(self):
        return self.ctype == "ACC"


def _seismic_pair(E):
    """Pick the X and Y seismic cases from their names (first ones containing X / Y), else the first two."""
    ex = next((c for c in E if re.search(r"X", c.upper())), None)
    ey = next((c for c in E if re.search(r"Y", c.upper()) and c != ex), None)
    if ex is None or ey is None:
        ex, ey = (E + [None, None])[:2]
    return ex, ey


def rpa2024_isolated(by, psi=0.3, omega=1.0, label="Ω"):
    """RPA 2024 seismic combinations for isolated footings, §5.7 eq. (5.6) with §5.2 eq. (5.1)-(5.2):
    G + ψQ ± (R/Q_F)·(Ex ± 0,3·Ey)  and  G + ψQ ± (R/Q_F)·(0,3·Ex ± Ey).
    Common foundations (eq. 5.7) use 1,4·E instead of R/Q_F."""
    G, Q, E = by["G"], by["Q"], by["E"]
    if not G or not E:
        return []
    base = {c: 1.0 for c in G}
    if psi:
        base.update({c: psi for c in Q})
    ex, ey = _seismic_pair(E)
    out = []
    pre = "ACC G+ψQ"
    k = label if label != "Ω" else "Ω"
    if ey is None:
        for sg in (1, -1):
            f = dict(base)
            f[ex] = sg * omega
            out.append(ComboDef(f"{pre}{'+' if sg > 0 else '−'}{k}·{ex}", "ACC", f))
    else:
        for sg in (1, -1):
            for a, b in ((1.0, 0.3), (0.3, 1.0)):
                for s2 in (1, -1):
                    f = dict(base)
                    f[ex] = round(sg * omega * a, 4)
                    f[ey] = round(sg * omega * b * s2, 4)
                    out.append(ComboDef(f"{pre}{'+' if sg > 0 else '−'}{k}({a:g}·{ex}{'+' if s2 > 0 else '−'}{b:g}·{ey})",
                                        "ACC", f))
    for e in E:  # any other seismic case alone
        if e not in (ex, ey):
            for sg in (1, -1):
                f = dict(base)
                f[e] = sg * omega
                out.append(ComboDef(f"{pre}{'+' if sg > 0 else '−'}{k}·{e}", "ACC", f))
    return out


def generate(cases, templates=TEMPLATES, psi=0.3, omega=1.0, ec7_upl=False, label="Ω"):
    """cases: list of (case name, type). Returns list[ComboDef].

    Fundamental / service combinations from the templates (W cases taken one at a time),
    seismic combinations per RPA 2024 for isolated footings (see rpa2024_isolated)."""
    by = {k: [c for c, t in cases if t == k] for k in CATS}
    out = []
    for name, ctype, tpl in templates:
        if any(k in tpl and not by[k] for k in ("Q", "S", "W", "E")) or not by["G"]:
            continue
        for w in (by["W"] if "W" in tpl else [None]):
            f = {}
            for k in ("G", "Q", "S"):
                if k in tpl:
                    for c in by[k]:
                        f[c] = tpl[k]
            if w is not None:
                f[w] = tpl["W"]
            out.append(ComboDef(name + (f" ({w})" if w else ""), ctype, f))
    out += rpa2024_isolated(by, psi, omega, label)
    if ec7_upl:
        for w in by["W"]:
            f = {c: 0.9 for c in by["G"]}
            f[w] = 1.5
            out.append(ComboDef(f"UPL ({w})", "UPL", f))
    return out


def _zero():
    return dict(N=0.0, Vx=0.0, Vy=0.0, Mx=0.0, My=0.0)


def apply(joint, cases, defs, pinned=False):
    """cases: list of dicts {case, type, N, Vx, Vy, Mx, My} for one support joint."""
    cases = [dict(c) for c in cases if c.get("type") in TYPES and c.get("type") != "Ignorer"]
    if pinned:
        for c in cases:
            c["Mx"] = c["My"] = 0.0
    byname = {c["case"]: c for c in cases}
    out = []
    for d in defs:
        used = [(byname[k], f) for k, f in d.factors.items() if f and k in byname and byname[k]["type"] in CATS]
        if not used:
            continue
        tot = _zero()
        for c, f in used:
            for k in FORCES:
                tot[k] += f * float(c[k])
        gf = [f for c, f in used if c["type"] == "G"]
        gu, gfav = (max(gf), min(gf)) if gf else DIRECT_G[d.ctype]
        out.append(Combo(d.name, d.ctype, joint, *(tot[k] for k in FORCES), gu, gfav, d.label()))
    for c in cases:
        if c["type"] in DIRECT:
            gu, gf = DIRECT_G[c["type"]]
            out.append(Combo(c["case"], c["type"], joint, *(float(c[k]) for k in FORCES), gu, gf,
                             "résultat combiné importé"))
    return out
