"""Formula text (as written in the calculation trace) → LaTeX → native Word equation (OMML).

to_latex("σmax = N/(A·B)·(1 + 6e/A)")  →  "\\sigma_{max} = \\frac{N}{A\\cdot B}\\cdot \\left(1 + 6\\frac{e}{A}\\right)"
latex_to_omml(latex)                  →  lxml <m:oMath> element ready to insert in a python-docx paragraph.
Callers fall back to plain text when anything fails.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache

GREEK = {"α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "ε": r"\varepsilon", "η": r"\eta",
         "θ": r"\theta", "λ": r"\lambda", "μ": r"\mu", "ξ": r"\xi", "π": r"\pi", "ρ": r"\rho", "σ": r"\sigma",
         "τ": r"\tau", "φ": r"\varphi", "ψ": r"\psi", "ω": r"\omega", "Ω": r"\Omega", "Δ": r"\Delta",
         "Σ": r"\Sigma", "Φ": r"\Phi"}
GREEK_CMDS = "sigma|gamma|varphi|tau|psi|mu|alpha|eta|rho|theta|lambda|xi|delta|omega"
SUBS = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
        "ₓ": "x", "ᵧ": "y"}
SYMS = {"·": r"\cdot ", "×": r"\times ", "−": "-", "≤": r"\le ", "≥": r"\ge ", "→": r"\rightarrow ", "⇒": r"\Rightarrow ", "±": r"\pm ",
        "∞": r"\infty ", "≈": r"\approx ", "⟂": r"\perp ", "°": r"^{\circ}", "²": "^{2}", "³": "^{3}", "⁴": "^{4}",
        "%": r"\%", "‰": r"\text{‰}", "’": "'", "≠": r"\neq "}
FUNCS = {"max", "min", "tan", "sin", "cos", "exp", "ln", "log", "cot", "atan"}
UNITS = {"kN", "kPa", "MPa", "cm", "mm", "bar", "m", "MN", "kNm"}
FR = {"de", "et", "la", "le", "si", "pas", "sur", "des", "par", "avec", "sans", "non", "oui", "ou", "en", "au", "à",
      "du", "un", "une", "les", "pour", "est", "sont", "selon", "lit", "face", "fût", "voir", "soit", "cas",
      "taux", "dans", "même", "rayon", "puis", "sinon", "oui", "non"}
LET = "A-Za-zÀ-ÖØ-öø-ÿ"


class G(list):
    """Parenthesised group; kind = '(' '[' or '|'."""
    kind = "("


def _close(s, i):
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return j
    return len(s) - 1


def _word(w):
    if w in FUNCS:
        return "\\arctan " if w == "atan" else "\\" + w + " "
    if w == "ds":
        return r"\mathrm{d}s"
    if w in UNITS:
        return r"\text{ " + w + "}"
    if w.lower() in FR or re.search(r"[À-ÖØ-öø-ÿ]", w):
        return r"\text{ " + w + " }"
    m = re.fullmatch(r"([A-Za-z])('?)([A-Za-z0-9,]{1,7})", w)
    if m and not w.isupper() and (len(w) <= 4 or "," in w):
        return m.group(1) + m.group(2) + "_{" + m.group(3) + "}"
    if len(w) >= 3:
        return r"\text{ " + w + " }"
    return w


def _tokenize(s):
    out, stack = G(), []
    cur = out
    i = 0
    while i < len(s):
        ch = s[i]
        if ch in "([" or (ch == "|" and not (stack and stack[-1][1] == "|")):
            g = G()
            g.kind = ch
            stack.append((cur, ch))
            cur.append(g)
            cur = g
            i += 1
            continue
        if ch in ")]" or (ch == "|" and stack and stack[-1][1] == "|"):
            if stack:
                cur, _ = stack.pop()
            i += 1
        elif ch.isspace():
            cur.append(" ")
            i += 1
        elif ch == "\\":
            m = re.match(r"\\(?:[A-Za-z]+|.)", s[i:])
            tok = m.group(0) if m else "\\"
            j = i + len(tok)
            while j < len(s) and s[j] == "{":
                k = _close(s, j)
                tok += s[j:k + 1]
                j = k + 1
            cur.append(tok + " ")
            i = j
        else:
            m = re.match(r"[0-9]+(?:[.,][0-9]+)?", s[i:]) or \
                re.match(rf"[{LET}][{LET}0-9']*(?:,[a-z]{{1,4}}(?![{LET}]))?", s[i:])
            if m:
                tok = m.group(0)
                i += len(tok)
                cur.append(tok.replace(",", "{,}") if tok[0].isdigit() else _word(tok))
            else:
                cur.append(ch)
                i += 1
        while i + 1 < len(s) and s[i] in "_^" and s[i + 1] == "{":  # attach scripts to previous atom
            j = _close(s, i + 1)
            if cur and isinstance(cur[-1], str) and cur[-1] != " ":
                cur[-1] = cur[-1].rstrip() + s[i:j + 1]
            else:
                cur.append(s[i:j + 1])
            i = j + 1
    return out


def _grp(g, strip=False):
    inner = _render(g)
    k = getattr(g, "kind", "(")
    if k == "|":
        return r"\left|" + inner + r"\right|"
    if strip and k == "(":
        return inner
    lo, hi = (r"\left(", r"\right)") if k == "(" else (r"\left[", r"\right]")
    return lo + inner + hi


def _render(items):
    seq = []
    k = 0
    while k < len(items):  # √(x) → \sqrt{x}
        it = items[k]
        if it == "√":
            j = k + 1
            while j < len(items) and items[j] == " ":
                j += 1
            if j < len(items):
                arg = items[j]
                seq.append(r"\sqrt{" + (_grp(arg, True) if isinstance(arg, list) else arg) + "}")
                k = j + 1
                continue
        seq.append(it)
        k += 1
    out = []
    k = 0
    while k < len(seq):  # a / b → \frac{a}{b}
        it = seq[k]
        if it == "/" and out:
            p = len(out) - 1
            while p >= 0 and out[p] == " ":
                p -= 1
            j = k + 1
            while j < len(seq) and seq[j] == " ":
                j += 1
            if p >= 0 and j < len(seq) and seq[j] not in ("+", "-", "=", ";", "/"):
                num, den = out[p], seq[j]
                ns = _grp(num, True) if isinstance(num, list) else num
                ds = _grp(den, True) if isinstance(den, list) else den
                del out[p:]
                out.append(r"\dfrac{" + ns + "}{" + ds + "}")
                k = j + 1
                continue
        out.append(it)
        k += 1
    s = ""
    for it in out:
        if isinstance(it, list):
            s += _grp(it)
        elif it == ";":
            s += r"\text{ ;   }"
        else:
            s += it
    return s


def to_latex(text: str) -> str:
    t = text.strip()
    t = re.sub(r"σ̄([a-z]+)", lambda m: "SIGBAR_{" + m.group(1) + "}", t)
    t = t.replace("σ̄", "SIGBAR").replace("₃/₄", "_{3/4}")
    t = t.replace("∫₀^l₁", r"\int_{0}^{l_{1}}")
    t = re.sub(r"\^\(([^)]*)\)", lambda m: "^{" + m.group(1) + "}", t)
    t = re.sub(r"[₀₁₂₃₄₅₆₇₈₉ₓᵧ]+", lambda m: "_{" + "".join(SUBS[c] for c in m.group(0)) + "}", t)
    for k, v in SYMS.items():
        t = t.replace(k, v)
    for k, v in GREEK.items():
        t = t.replace(k, v + " ")
    t = t.replace("SIGBAR", r"\bar{\sigma}")
    t = re.sub(rf"(\\(?:{GREEK_CMDS})) ([A-Za-z0-9,]{{1,9}})(?![a-zà-ÿ])", lambda m: m.group(1) + "_{" + m.group(2) + "}", t)
    return re.sub(r" {2,}", " ", _render(_tokenize(t))).strip()


@lru_cache(maxsize=1)
def _xslt():
    from lxml import etree
    for p in (os.environ.get("MML2OMML", ""),
              r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL",
              r"C:\Program Files (x86)\Microsoft Office\root\Office16\MML2OMML.XSL",
              r"C:\Program Files\Microsoft Office\Office16\MML2OMML.XSL",
              r"C:\Program Files (x86)\Microsoft Office\Office16\MML2OMML.XSL"):
        if p and os.path.exists(p):
            return etree.XSLT(etree.parse(p))
    return None


def available():
    try:
        import latex2mathml.converter  # noqa: F401
        return _xslt() is not None
    except Exception:  # noqa: BLE001
        return False


def latex_to_omml(latex: str):
    from latex2mathml.converter import convert
    from lxml import etree
    tree = etree.fromstring(convert(latex).encode("utf-8"))
    return _xslt()(tree).getroot()
