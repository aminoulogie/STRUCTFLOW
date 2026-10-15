"""Import support reactions exported from ETABS or Robot Structural Analysis.

ETABS : Display > Show Tables > Analysis Results > Joint Output > Reactions > "Joint Reactions"
        → Export to Excel (columns Story, Label/Unique Name, Output Case, Case Type, Step Type, FX … MZ).
Robot : Results > Reactions → right click > "Export to Excel" (columns "Node/Case", FX, FY, FZ, MX, MY, MZ)
        or a table with separate "Node" and "Case" columns.
"""
from __future__ import annotations

import re

import pandas as pd

UNIT_FACTORS = {"kN, kN·m": 1.0, "N, N·m": 1e-3, "T, T·m": 9.81, "MN, MN·m": 1000.0, "kgf, kgf·m": 9.81e-3}

_JOINT = ["label", "unique name", "uniquename", "joint", "node", "point", "noeud", "nœud", "appui", "support"]
_CASE = ["output case", "outputcase", "load case", "loadcase", "case", "cas", "load", "combo", "combinaison"]


def _norm(s):
    s = str(s).strip().lower()
    s = re.sub(r"[\(\[].*?[\)\]]", "", s)
    return s.strip()


def _read_any(file, name):
    name = (name or "").lower()
    if name.endswith((".csv", ".txt")):
        raw = file.read() if hasattr(file, "read") else open(file, "rb").read()
        text = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else raw
        sep = ";" if text.count(";") > text.count(",") else ("\t" if "\t" in text else ",")
        from io import StringIO
        return {"csv": pd.read_csv(StringIO(text), sep=sep, header=None, dtype=str)}
    return pd.read_excel(file, sheet_name=None, header=None, dtype=str)


def _find_header(df):
    for i in range(min(len(df), 15)):
        cells = [_norm(x) for x in df.iloc[i].tolist()]
        if "fz" in cells and ("fx" in cells or "mx" in cells):
            return i
    return None


def _num(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    s = str(x).strip().replace(" ", "").replace(" ", "")
    if s.count(",") == 1 and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def guess_type(case):
    s = str(case).upper().strip()
    s = re.sub(r"^\d+\s*\((C|K|S)\)\s*", "", s).strip()  # Robot "3 (C) V1" -> "V1"
    if re.search(r"ELU|ULS|ULT", s):
        return "ELU"
    if re.search(r"ELS|SLS|SER", s):
        return "ELS"
    if re.search(r"ACC|G\s*\+\s*Q\s*[\+±]\s*E|0[.,]8\s*G", s):
        return "ACC"
    if "+" in s or "COMB" in s or "ENV" in s:
        return "Ignorer"
    if re.search(r"^E|EX|EY|SEIS|SISM|SPEC|RSA|^SX|^SY", s):
        return "E"
    if re.search(r"^W|^V\d|^V[ _-]|VENT|WIND", s):
        return "W"
    if re.search(r"^S\d*$|NEIGE|SNOW|^SN", s):
        return "S"
    if re.search(r"^Q|LIVE|EXPL|^L\d*$|SURCH|^LL", s):
        return "Q"
    if re.search(r"^G|DEAD|^PP|PERM|SDL|^CP|SELF|POIDS|^D\d*$|^DL", s):
        return "G"
    return "Ignorer"


def read_reactions(file, filename, units="kN, kN·m", reactions=True):
    """Return a DataFrame: Appui, Groupe, Cas, Type, N, Vx, Vy, Mx, My."""
    sheets = _read_any(file, filename)
    for sname, df in sheets.items():
        hi = _find_header(df)
        if hi is None:
            continue
        headers = [_norm(x) for x in df.iloc[hi].tolist()]
        body = df.iloc[hi + 1:].reset_index(drop=True)
        col = {h: i for i, h in reversed(list(enumerate(headers)))}

        def find(cands):
            for c in cands:
                if c in col:
                    return col[c]
            return None

        ij, ic = find(_JOINT), find(_CASE)
        composite = next((i for i, h in enumerate(headers) if "/" in h and ("node" in h or "noeud" in h or "nœud" in h)), None)
        istep = find(["step type", "steptype"])
        istory = find(["story", "etage", "étage"])
        f = {k: col.get(k.lower()) for k in ("FX", "FY", "FZ", "MX", "MY")}
        if f["FZ"] is None:
            continue
        k = UNIT_FACTORS.get(units, 1.0)
        rows = []
        for _, r in body.iterrows():
            vals = {key: _num(r.iloc[i]) if i is not None else 0.0 for key, i in f.items()}
            if vals["FZ"] is None:
                continue
            vals = {key: (v or 0.0) * k for key, v in vals.items()}
            if composite is not None and (ij is None or ic is None):
                parts = str(r.iloc[composite]).split("/", 1)
                joint = parts[0].strip()
                case = parts[1].strip() if len(parts) > 1 else "?"
            else:
                joint = str(r.iloc[ij]).strip() if ij is not None else "?"
                case = str(r.iloc[ic]).strip() if ic is not None else "?"
            if istory is not None and ij is not None and headers[ij] == "label":
                story = str(r.iloc[istory]).strip()
                if story and story.lower() != "nan":
                    joint = f"{story}-{joint}"
            if istep is not None:
                st = str(r.iloc[istep]).strip()
                if st and st.lower() not in ("nan", "", "none"):
                    case = f"{case} {st}"
            sgn = -1.0 if reactions else 1.0
            vals = {key: v + 0.0 for key, v in vals.items()}
            rows.append(dict(Appui=joint, Groupe="S-" + joint, Cas=case, Type=guess_type(case),
                             N=vals["FZ"] if reactions else -vals["FZ"],
                             Vx=sgn * vals["FX"] + 0.0, Vy=sgn * vals["FY"] + 0.0, Mx=sgn * vals["MX"] + 0.0, My=sgn * vals["MY"] + 0.0))
        if rows:
            out = pd.DataFrame(rows)
            # ETABS envelopes (Max/Min) of the same case: keep both as separate cases
            return out, f"Feuille « {sname} » : {len(out)} lignes, {out['Appui'].nunique()} appuis, {out['Cas'].nunique()} cas."
    raise ValueError("Aucun tableau de réactions reconnu (colonnes FX/FY/FZ/MX/MY introuvables).")
