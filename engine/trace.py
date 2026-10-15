"""Calculation trace: every formula is recorded symbolically, numerically and with
its result, so the Word note de calcul can reproduce the full calculation.

Sections carry an optional `key` so the user can choose which chapters go into the note.
Table rows may be a dict {"_group": "Béton"} to print a shaded group-header row."""
from __future__ import annotations

import math
from dataclasses import dataclass, field


def fmt(x, nd=2):
    if x is None:
        return "—"
    if isinstance(x, str):
        return x
    if isinstance(x, float) and math.isinf(x):
        return "∞"
    return f"{x:.{nd}f}"


@dataclass
class Step:
    label: str
    sym: str = ""        # symbolic formula, e.g. "σ = N/(A·B)"
    num: str = ""        # numeric substitution
    res: str = ""        # result with unit
    ref: str = ""        # code article
    ok: bool | None = None
    cond: str = ""       # verified condition, e.g. "152.1 kPa ≤ 200.0 kPa"


@dataclass
class Para:
    text: str
    kind: str = "normal"   # normal | note | warn | bold


@dataclass
class Table:
    headers: list
    rows: list
    title: str = ""


@dataclass
class Figure:
    png: bytes
    caption: str = ""
    width_cm: float = 15.0


@dataclass
class Section:
    title: str
    level: int = 1
    items: list = field(default_factory=list)
    key: str = ""


class Trace:
    def __init__(self):
        self.sections: list[Section] = []

    def sec(self, title, level=1, key=""):
        s = Section(title, level, [], key)
        self.sections.append(s)
        return s

    def _cur(self):
        if not self.sections:
            self.sec("")
        return self.sections[-1]

    def step(self, label, sym="", num="", res="", ref="", ok=None, cond=""):
        self._cur().items.append(Step(label, sym, num, res, ref, ok, cond))

    def para(self, text, kind="normal"):
        self._cur().items.append(Para(text, kind))

    def table(self, headers, rows, title=""):
        self._cur().items.append(Table(headers, rows, title))

    def fig(self, png, caption="", width_cm=15.0):
        self._cur().items.append(Figure(png, caption, width_cm))
