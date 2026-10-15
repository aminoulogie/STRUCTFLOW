"""Direct link with an open Autodesk Robot Structural Analysis model (COM API, read-only).

Reads: load cases (name, nature, simple / combination, combination type and factors),
support nodes, and support reactions for every simple case (and optionally every combination).
Nothing is written to the Robot model.
"""
from __future__ import annotations

I_LT_SUPPORT = 0
I_CT_SIMPLE, I_CT_COMBINATION = 0, 1
NATURE = {0: "G", 1: "Q", 2: "W", 3: "S", 4: "Ignorer", 5: "Ignorer", 6: "E"}
COMB_TYPE = {0: "ELU", 1: "ELS", 2: "ACC"}


def _robot():
    try:
        import win32com.client as w
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Module pywin32 absent : pip install pywin32") from e
    try:
        app = w.gencache.EnsureDispatch("Robot.Application")
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("Robot Structural Analysis n'est pas accessible (Robot doit être ouvert avec le modèle).") from e
    if not app.Visible or app.Project is None:
        raise RuntimeError("Aucun projet Robot ouvert.")
    return w, app


def read_cases():
    """Return list of dicts: number, name, kind ('simple'|'comb'), type (G/Q/W/S/E/ELU/ELS/ACC/Ignorer), factors."""
    w, app = _robot()
    st = app.Project.Structure
    allc = st.Cases.GetAll()
    out = []
    for i in range(1, allc.Count + 1):
        c = allc.Get(i)
        try:
            ctype, nature, num, name = c.Type, c.Nature, c.Number, str(c.Name).strip()
        except Exception:  # noqa: BLE001
            continue
        if ctype == I_CT_SIMPLE:
            t = NATURE.get(nature, "Ignorer")
            if "modal" in name.lower():
                t = "Ignorer"
            out.append(dict(number=num, name=name, kind="simple", type=t, factors={}))
        elif ctype == I_CT_COMBINATION:
            cc = w.CastTo(c, "IRobotCaseCombination")
            facs = {}
            for k in range(1, cc.CaseFactors.Count + 1):
                f = cc.CaseFactors.Get(k)
                facs[f.CaseNumber] = facs.get(f.CaseNumber, 0.0) + float(f.Factor)
            out.append(dict(number=num, name=name, kind="comb", type=COMB_TYPE.get(cc.CombinationType, "Ignorer"),
                            factors=facs))
    return out


def read_reactions(case_numbers, progress=None):
    """Return (supports, rows). rows: dicts Appui, Cas number, N, Vx, Vy, Mx, My in kN / kN·m (actions on the footing)."""
    w, app = _robot()
    st = app.Project.Structure
    nodes = st.Nodes.GetAll()
    sup = []
    for i in range(1, nodes.Count + 1):
        n = w.CastTo(nodes.Get(i), "IRobotNode")
        if n.HasLabel(I_LT_SUPPORT):
            sup.append(n.Number)
    reac = st.Results.Nodes.Reactions
    rows = []
    total = len(sup) * len(case_numbers)
    k = 0
    for node in sup:
        for cn in case_numbers:
            k += 1
            if progress:
                progress(k, total)
            try:
                r = reac.Value(node, cn)
            except Exception:  # noqa: BLE001
                continue
            # reaction → action on the footing: N = FZ, Vx = −FX, Vy = −FY, Mx = −MX, My = −MY ; N → kN
            rows.append(dict(Appui=str(node), Cas=cn, N=r.FZ / 1000, Vx=-r.FX / 1000, Vy=-r.FY / 1000,
                             Mx=-r.MX / 1000, My=-r.MY / 1000))
    return sup, rows


def read_support_coords():
    """{support number (str): (x, y)} in m."""
    w, app = _robot()
    nodes = app.Project.Structure.Nodes.GetAll()
    out = {}
    for i in range(1, nodes.Count + 1):
        n = w.CastTo(nodes.Get(i), "IRobotNode")
        if n.HasLabel(I_LT_SUPPORT):
            out[str(n.Number)] = (float(n.X), float(n.Y))
    return out
