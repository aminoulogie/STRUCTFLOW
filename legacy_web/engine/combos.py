"""Load cases and combinations (BAEL / CCM 97 / RPA)."""
from __future__ import annotations

from dataclasses import dataclass

CATS = ["G", "Q", "S", "W", "E"]          # elementary load categories
DIRECT = ["ELU", "ELS", "ACC"]            # already-combined results
TYPES = CATS + DIRECT + ["Ignorer"]
FORCES = ["N", "Vx", "Vy", "Mx", "My"]

# name, type, G, Q, S, W, E  — W is applied to each wind case in turn, E to each seismic case with ±
DEFAULT_COMBOS = [
    ("ELU1", "ELU", 1.35, 1.50, 0.00, 0.00, 0.0),
    ("ELU2", "ELU", 1.35, 0.00, 1.50, 0.00, 0.0),
    ("ELU3", "ELU", 1.35, 0.00, 0.00, 1.50, 0.0),
    ("ELU4", "ELU", 1.00, 0.00, 0.00, 1.50, 0.0),
    ("ELU5", "ELU", 1.35, 1.35, 0.00, 1.35, 0.0),
    ("ELU6", "ELU", 1.35, 0.00, 1.35, 1.35, 0.0),
    ("ELS1", "ELS", 1.00, 1.00, 0.00, 0.00, 0.0),
    ("ELS2", "ELS", 1.00, 0.00, 1.00, 0.00, 0.0),
    ("ELS3", "ELS", 1.00, 0.00, 0.00, 1.00, 0.0),
    ("ELS4", "ELS", 1.00, 0.90, 0.00, 0.90, 0.0),
    ("ACC1", "ACC", 1.00, 1.00, 0.00, 0.00, 1.0),
    ("ACC2", "ACC", 0.80, 0.00, 0.00, 0.00, 1.0),
]

# factor on the footing/backfill self-weight for already-combined results: (unfavourable, favourable)
DIRECT_G = {"ELU": (1.35, 1.0), "ELS": (1.0, 1.0), "ACC": (1.0, 0.8)}


@dataclass
class ComboDef:
    name: str
    ctype: str
    G: float
    Q: float
    S: float
    W: float
    E: float

    def label(self):
        parts = []
        for k in CATS:
            f = getattr(self, k)
            if f:
                t = k if f == 1 else f"{f:g}{k}"
                if k == "E":
                    t = "±" + t
                parts.append(t)
        return " + ".join(parts).replace("+ ±", "± ")


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
    g_unf: float        # factor on self-weight when unfavourable (bearing)
    g_fav: float        # factor on self-weight when favourable (stability)
    formula: str = ""

    @property
    def acc(self):
        return self.ctype == "ACC"


def _zero():
    return dict(N=0.0, Vx=0.0, Vy=0.0, Mx=0.0, My=0.0)


def _add(a, b, f=1.0):
    for k in FORCES:
        a[k] += f * b[k]


def expand(joint, cases, defs, pinned=False, ec7_upl=False):
    """cases: list of dicts {case, type, N, Vx, Vy, Mx, My} for one support joint."""
    cases = [dict(c) for c in cases if c.get("type") in TYPES and c.get("type") != "Ignorer"]
    if pinned:
        for c in cases:
            c["Mx"] = c["My"] = 0.0
    sums = {k: _zero() for k in ("G", "Q", "S")}
    present = {k: False for k in ("G", "Q", "S")}
    W, E, out = [], [], []
    for c in cases:
        t = c["type"]
        if t in sums:
            _add(sums[t], c)
            present[t] = True
        elif t == "W":
            W.append(c)
        elif t == "E":
            E.append(c)
        elif t in DIRECT:
            gu, gf = DIRECT_G[t]
            out.append(Combo(c["case"], t, joint, *(float(c[k]) for k in FORCES), gu, gf, "résultat combiné importé"))

    for d in defs:
        if d.Q and not present["Q"] or d.S and not present["S"]:
            continue
        wl = W if d.W else [None]
        el = [(e, s) for e in E for s in (1, -1)] if d.E else [None]
        if not wl or not el:
            continue
        for w in wl:
            for es in el:
                f = _zero()
                for k in ("G", "Q", "S"):
                    if getattr(d, k):
                        _add(f, sums[k], getattr(d, k))
                tag = []
                if w is not None:
                    _add(f, w, d.W)
                    tag.append(w["case"])
                if es is not None:
                    e, s = es
                    _add(f, e, s * d.E)
                    tag.append(("+" if s > 0 else "−") + e["case"])
                name = d.name + (f" ({', '.join(tag)})" if tag else "")
                out.append(Combo(name, d.ctype, joint, f["N"], f["Vx"], f["Vy"], f["Mx"], f["My"], d.G, d.G, d.label()))

    if present["G"]:  # fallback when every definition of a type was skipped for lack of Q/S/W cases
        for t, fg in (("ELU", 1.35), ("ELS", 1.0)):
            if not any(c.ctype == t for c in out):
                f = _zero()
                _add(f, sums["G"], fg)
                out.append(Combo(f"{t}0", t, joint, *(f[k] for k in FORCES), fg, fg, f"{fg:g}G"))

    if ec7_upl:
        for w in W:
            f = _zero()
            _add(f, sums["G"], 0.9)
            _add(f, w, 1.5)
            out.append(Combo(f"UPL ({w['case']})", "UPL", joint, f["N"], f["Vx"], f["Vy"], f["Mx"], f["My"],
                             0.9, 0.9, "0.9G + 1.5W"))
    return out
