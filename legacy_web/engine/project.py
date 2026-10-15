"""Project orchestration: run every footing group and write the full calculation trace."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .combos import ComboDef, expand
from .footing import (Codes, GroupInput, GroupResult, Options, check_bearing, check_overturning, check_punching,
                      check_shear, check_uplift, design_group, h_required, pedestal_check, rc_direction)
from .longrine import LongrineInput, design_longrine
from .materials import Materials
from .references import ref
from .sketch import draw
from .soil import METHODS, Soil, capacities
from .trace import Trace, fmt

TYPE_LABEL = {"ELU": "ELU (fondamentale)", "ELS": "ELS (service)", "ACC": "Accidentelle (RPA)", "UPL": "EC7 UPL"}


@dataclass
class Project:
    meta: dict
    mat: Materials
    soil: Soil
    codes: Codes
    opts: Options
    combo_defs: list            # list[ComboDef]
    loads: list                 # list of dict: Appui, Groupe, Cas, Type, N, Vx, Vy, Mx, My
    groups: list                # list[GroupInput]
    longrine: LongrineInput | None = None
    results: list = field(default_factory=list)
    lg: dict | None = None


def group_combos(prj: Project, gi: GroupInput):
    combos = []
    rows = [r for r in prj.loads if r["Groupe"] == gi.name]
    joints = sorted({r["Appui"] for r in rows}, key=str)
    gi.joints = joints
    for j in joints:
        cases = [dict(case=r["Cas"], type=r["Type"], N=r["N"], Vx=r["Vx"], Vy=r["Vy"], Mx=r["Mx"], My=r["My"])
                 for r in rows if r["Appui"] == j]
        combos += expand(j, cases, prj.combo_defs, gi.pinned, prj.codes.ec7_uplift)
    return combos


def run(prj: Project):
    prj.results = []
    for gi in prj.groups:
        combos = group_combos(prj, gi)
        if not combos:
            continue
        prj.results.append(design_group(gi, combos, prj.mat, prj.soil, prj.codes, prj.opts))
    prj.lg = None
    if prj.longrine and prj.results:
        Nmax = max(c.N for r in prj.results for c in r.combos if c.ctype in ("ELU", "ACC"))
        prj.lg = dict(Nmax=Nmax, res=design_longrine(prj.longrine, Nmax, prj.mat))
    return prj.results


# ====================================================================== trace / note de calcul
def _ok(b):
    return "OK" if b else "NON OK"


def _bars(b):
    return f"{b['n']} HA{b['phi']} e = {b['s'] * 100:.0f} cm ({b['As']:.2f} cm²)" if b else "—"


def _gov(rows, key="ratio", pred=lambda r: True):
    rows = [r for r in rows if pred(r) and r.get(key) is not None and not (isinstance(r[key], float) and math.isnan(r[key]))]
    return max(rows, key=lambda r: r[key]) if rows else None


def _combo(res: GroupResult, name, joint):
    return next(c for c in res.combos if c.name == name and c.joint == joint)


def build_trace(prj: Project) -> Trace:
    tr = Trace()
    m, s, cd, o = prj.mat, prj.soil, prj.codes, prj.opts

    # ---------------------------------------------------------------- 1. hypotheses
    tr.sec("1. Objet et hypothèses générales")
    tr.para(f"La présente note a pour objet le dimensionnement et le ferraillage des semelles isolées sous poteaux "
            f"métalliques (avec fûts/amorces en béton armé) de l'ouvrage « {prj.meta.get('ouvrage', '')} », "
            f"ainsi que la vérification de leur stabilité vis-à-vis du sol, conformément aux règlements algériens en vigueur.")
    tr.table(["Vérification", "Règlement retenu"], [
        ["Béton armé (ferraillage, ELS, poinçonnement)", cd.rc],
        ["Portance du sol", cd.bearing + (" (ELS selon DTR BC 2.331)" if cd.ec7_bearing else "")],
        ["Combinaisons sismiques, renversement, longrines", cd.seismic],
        ["Renversement", cd.overturning],
        ["Soulèvement", cd.uplift],
        ["Combinaisons fondamentales / service", "BAEL 91 mod.99 – CCM 97"],
    ], "Tableau 1 – Règlements appliqués")
    tr.para("Unités : forces en kN, moments en kN·m, longueurs en m, contraintes du sol en kPa (1 bar = 100 kPa), "
            "contraintes des matériaux en MPa, sections d'acier en cm².")
    tr.para("Conventions : N > 0 en compression ; A = dimension de la semelle selon x, B selon y ; fût ap × bp. "
            "Les moments sont ramenés à la sous-face de la semelle : My,b = My + Vx·H et Mx,b = Mx − Vy·H, "
            "avec H = D + h₀ (hauteur entre la platine et l'assise).")
    tr.para("Méthode de ferraillage : la section d'acier retenue est le maximum entre la méthode des bielles "
            "(semelle rigide, e₀ ≤ B/6) et la méthode des moments (consoles, section S1 à 0,35·b de l'axe), "
            "à l'ELU, en situation accidentelle et à l'ELS (fissuration préjudiciable ou très préjudiciable), "
            "sans être inférieure à la condition de non-fragilité.")

    tr.sec("2. Caractéristiques des matériaux")
    m.describe(tr)

    tr.sec("3. Caractéristiques du sol de fondation")
    rows = [["Méthode", METHODS[s.method]], ["Profondeur d'ancrage D", f"{fmt(s.D)} m"],
            ["Poids volumique du remblai γr", f"{fmt(s.gamma_r, 1)} kN/m³"]]
    if s.method == "adm":
        rows += [["σadm (ELS)", f"{fmt(s.sigma_adm, 1)} kPa = {fmt(s.sigma_adm / 100)} bar"],
                 ["Coefficient ELU k_ELU", fmt(s.k_elu)], ["Coefficient accidentel k_ACC", fmt(s.k_acc)]]
    elif s.method == "cphi":
        rows += [["Cohésion c", f"{fmt(s.c, 1)} kPa"], ["Angle de frottement φ", f"{fmt(s.phi, 1)}°"],
                 ["Poids volumique du sol γ", f"{fmt(s.gamma, 1)} kN/m³"]]
    elif s.method == "pressio":
        rows += [["Pression limite nette équivalente ple*", f"{fmt(s.pl, 1)} kPa"], ["Facteur de portance kp", fmt(s.kp, 3)]]
    else:
        rows += [["Résistance de pointe équivalente qce", f"{fmt(s.qc, 1)} kPa"], ["Facteur de portance kc", fmt(s.kc, 3)]]
    if s.method != "adm":
        rows += [["Fs ELS / Fs ELU", f"{fmt(s.fs_els, 1)} / {fmt(s.fs_elu, 1)}"]]
    tr.table(["Paramètre", "Valeur"], rows, "Tableau 2 – Données géotechniques")
    if s.method == "cphi":
        tr.para("La contrainte de rupture dépend de la largeur B : elle est calculée pour chaque semelle (§ semelles).", "note")
    else:
        capacities(s, 1.0, 1.0, s.D, tr)

    tr.sec("4. Combinaisons de charges")
    tr.para("Cas de charges élémentaires : G (permanentes), Q (exploitation), S (neige), W (vent – chaque cas pris "
            "séparément), E (séisme – chaque cas pris avec les deux signes). Les résultats déjà combinés importés "
            "(ELU/ELS/ACC) sont utilisés directement.")
    tr.table(["Nom", "Type", "Combinaison", "Référence"],
             [[d.name, TYPE_LABEL[d.ctype], d.label(),
               ref("rpa_combo") if d.ctype == "ACC" else ref("combo_elu" if d.ctype == "ELU" else "combo_els")]
              for d in prj.combo_defs], "Tableau 3 – Combinaisons d'actions")
    if cd.ec7_uplift:
        tr.para("Soulèvement selon EC7 (UPL) : combinaison 0,9·G + 1,5·W pour chaque cas de vent.", "note")

    # ---------------------------------------------------------------- footing groups
    for i, res in enumerate(prj.results, start=5):
        _group_trace(tr, prj, res, i)

    # ---------------------------------------------------------------- longrines
    n = 5 + len(prj.results)
    if prj.lg:
        tr.sec(f"{n}. Longrines (chaînage des semelles)")
        li = prj.longrine
        tr.para(f"Les semelles isolées sont solidarisées par un réseau bidirectionnel de longrines. "
                f"N = effort normal maximal (ELU / accidentel) des poteaux solidarisés = {fmt(prj.lg['Nmax'])} kN ; "
                f"α = {fmt(li.alpha, 0)}.")
        design_longrine(li, prj.lg["Nmax"], m, tr)
        n += 1

    # ---------------------------------------------------------------- summary
    tr.sec(f"{n}. Tableau récapitulatif")
    rows = []
    for r in prj.results:
        g, rc = r.geo, r.rc
        top = rc["X"]["bars_top"] or rc["Y"]["bars_top"]
        pb = r.ped["bars"]
        rows.append([r.gi.name, ", ".join(r.gi.joints)[:40], f"{fmt(g.A)} × {fmt(g.B)} × {fmt(g.h)}",
                     f"{fmt(g.ap * 100, 0)}×{fmt(g.bp * 100, 0)}", _bars(rc["X"]["bars"]), _bars(rc["Y"]["bars"]),
                     (f"// A : {_bars(rc['X']['bars_top'])} ; // B : {_bars(rc['Y']['bars_top'])}" if top else "—"),
                     f"{pb['n']} HA{pb['phi']}" if pb else "—", _ok(r.ok)])
    tr.table(["Semelle", "Appuis", "A × B × h (m)", "Fût (cm)", "Nappe inf. // A", "Nappe inf. // B",
              "Nappe sup.", "Fût", "Statut"], rows, "Tableau récapitulatif des semelles")
    if prj.lg:
        lr = prj.lg["res"]
        tr.para(f"Longrines {fmt(prj.longrine.b * 100, 0)} × {fmt(prj.longrine.h * 100, 0)} cm : "
                f"{lr['bars']['n']} HA{lr['bars']['phi']} — cadres HA{lr['phit']} e = {fmt(lr['st'] * 100, 0)} cm.", "bold")
    return tr


def _group_trace(tr: Trace, prj: Project, res: GroupResult, n: int):
    m, s, cd, o = prj.mat, prj.soil, prj.codes, prj.opts
    g, gi = res.geo, res.gi
    tr.sec(f"{n}. Semelle {gi.name}")
    tr.para(f"Appuis concernés : {', '.join(gi.joints)}. Liaison pied de poteau : {gi.base}. "
            f"Fût {fmt(gi.ap * 100, 0)} × {fmt(gi.bp * 100, 0)} cm, arase supérieure à {fmt(gi.h_above)} m au-dessus du TN.")
    for msg in res.msgs:
        tr.para(msg, "warn")

    # -------------------------------------------------- dimensions
    tr.sec(f"{n}.1 Dimensionnement de la semelle", 2)
    els = [c for c in res.combos if c.ctype == "ELS"] or res.combos
    cmax = max(els, key=lambda c: c.N)
    caps = res.ev["caps"]
    if res.auto:
        tr.step("Pré-dimensionnement (surface portante)", "A·B ≥ Nser,max / (q_ELS − γmoy·D)",
                f"{fmt(cmax.N)} / ({fmt(caps['q_els'], 1)} − 20 × {fmt(g.D)})",
                f"{fmt(cmax.N / max(caps['q_els'] - 20 * g.D, 10), 3)} m² (valeur initiale)", ref("dtr_portance"))
        if o.homothetic:
            tr.step("Homothétie avec le fût", "A/B = ap/bp", f"{fmt(gi.ap)}/{fmt(gi.bp)}", f"{fmt(gi.ap / gi.bp, 3)}")
        tr.para("Les dimensions A et B sont ensuite augmentées par pas de "
                f"{fmt(o.step * 100, 0)} cm jusqu'à satisfaction de toutes les vérifications "
                "(portance, renversement, soulèvement).", "note")
    else:
        tr.para("Dimensions imposées par l'utilisateur (vérification).", "note")
    dX, dY = res.rc["d"]["X"], res.rc["d"]["Y"]
    dreq = max((g.A - g.ap) / 4, (g.B - g.bp) / 4)
    tr.step("Condition de rigidité (hauteur utile)", "d ≥ max((A − ap)/4 ; (B − bp)/4)",
            f"max(({fmt(g.A)} − {fmt(g.ap)})/4 ; ({fmt(g.B)} − {fmt(g.bp)})/4)", f"d ≥ {fmt(dreq, 3)} m", ref("rigidite"),
            min(dX, dY) >= dreq - 1e-9, f"d = min({fmt(dX, 3)} ; {fmt(dY, 3)}) m ≥ {fmt(dreq, 3)} m")
    if not gi.h:
        tr.step("Hauteur totale", "h = max(h_min ; d + c + 1,5·φ) arrondie à 5 cm",
                f"max({fmt(o.h_min)} ; {fmt(dreq, 3)} + {fmt(m.cover)} + 1,5 × {fmt(o.phi_assumed, 3)})",
                f"h = {fmt(g.h)} m")
    tr.step("Dimensions retenues", "A × B × h", "", f"{fmt(g.A)} × {fmt(g.B)} × {fmt(g.h)} m — D = {fmt(g.D)} m")
    tr.step("Hauteur du fût et bras de levier des efforts horizontaux", "Hp = D − h + h₀ ; H = D + h₀",
            f"Hp = {fmt(g.D)} − {fmt(g.h)} + {fmt(gi.h_above)} ; H = {fmt(g.D)} + {fmt(gi.h_above)}",
            f"Hp = {fmt(g.Hp)} m ; H = {fmt(g.lever)} m")
    tr.fig(draw(res, m.cover), f"Figure – Semelle {gi.name} : vue en plan et coupe")

    tr.sec(f"{n}.2 Poids propres", 2)
    tr.step("Poids de la semelle", "Wf = γc·A·B·h", f"{fmt(g.gc, 1)} × {fmt(g.A)} × {fmt(g.B)} × {fmt(g.h)}", f"{fmt(g.Wf)} kN")
    tr.step("Poids du fût", "Wp = γc·ap·bp·Hp", f"{fmt(g.gc, 1)} × {fmt(g.ap)} × {fmt(g.bp)} × {fmt(g.Hp)}", f"{fmt(g.Wp)} kN")
    tr.step("Poids du remblai", "Ws = γr·(A·B − ap·bp)·(D − h)",
            f"{fmt(g.gr, 1)} × ({fmt(g.A)} × {fmt(g.B)} − {fmt(g.ap)} × {fmt(g.bp)}) × ({fmt(g.D)} − {fmt(g.h)})", f"{fmt(g.Ws)} kN")
    tr.step("Poids total", "W = Wf + Wp + Ws", f"{fmt(g.Wf)} + {fmt(g.Wp)} + {fmt(g.Ws)}", f"{fmt(g.W)} kN")

    tr.sec(f"{n}.3 Efforts en pied de poteau (combinaisons)", 2)
    tr.table(["Appui", "Combinaison", "Type", "N", "Vx", "Vy", "Mx", "My"],
             [[c.joint, c.name, c.ctype, fmt(c.N), fmt(c.Vx), fmt(c.Vy), fmt(c.Mx), fmt(c.My)] for c in res.combos],
             "Efforts au sommet du fût (kN, kN·m)")

    # -------------------------------------------------- bearing
    tr.sec(f"{n}.4 Vérification de la portance du sol", 2)
    if s.method == "cphi":
        capacities(s, g.A, g.B, g.D, tr)
    else:
        tr.para(f"q_ELS = {fmt(caps['q_els'], 1)} kPa ; q_ELU = {fmt(caps['q_elu'], 1)} kPa ; "
                f"q_ACC = {fmt(caps['q_acc'], 1)} kPa (voir § 3).")
    for t in ("ELS", "ELU", "ACC"):
        r = _gov(res.ev["bear"], pred=lambda r, t=t: r["type"] == t)
        if not r:
            continue
        tr.para(f"Combinaison {t} la plus défavorable : {r['combo']} (appui {r['joint']})", "bold")
        check_bearing(g, _combo(res, r["combo"], r["joint"]), caps, s, cd, tr)
    tr.table(["Appui", "Comb.", "Type", "Nt (kN)", "eₓ (m)", "e_y (m)", "Diagr. x / y", "σ₃/₄ ou Vd", "q ou Rd", "Taux", "Vérif."],
             [[r["joint"], r["combo"], r["type"], fmt(r["Nt"]), fmt(r["ex"], 3), fmt(r["ey"], 3),
               f"{r['regX']} / {r['regY']}", fmt(r["s34"], 1), fmt(r["q"], 1), f"{fmt(r['ratio'] * 100, 0)} %", _ok(r["ok"])]
              for r in res.ev["bear"]], "Portance – toutes combinaisons")

    # -------------------------------------------------- overturning
    tr.sec(f"{n}.5 Vérification au renversement", 2)
    for meth, lab in (("RPA", "Combinaison accidentelle la plus défavorable (RPA)"),
                      ("Fs", "Combinaison la plus défavorable (coefficient de sécurité)")):
        r = _gov(res.ev["ovt"], pred=lambda r, meth=meth: r["method"] == meth)
        if r:
            tr.para(f"{lab} : {r['combo']} (appui {r['joint']})", "bold")
            check_overturning(g, _combo(res, r["combo"], r["joint"]), o, cd, tr)
    if res.ev["ovt"]:
        tr.table(["Appui", "Comb.", "Type", "Nt (kN)", "My,b", "Mx,b", "Critère", "Détail", "Vérif."],
                 [[r["joint"], r["combo"], r["type"], fmt(r["Nt"]), fmt(r["Myb"]), fmt(r["Mxb"]),
                   r["method"], r["detail"], _ok(r["ok"])] for r in res.ev["ovt"]], "Renversement – toutes combinaisons")

    # -------------------------------------------------- uplift
    tr.sec(f"{n}.6 Vérification au soulèvement", 2)
    if res.ev["upl"]:
        r = _gov(res.ev["upl"])
        tr.para(f"Combinaison la plus défavorable : {r['combo']} (appui {r['joint']})", "bold")
        check_uplift(g, _combo(res, r["combo"], r["joint"]), o, cd, any(c.ctype == "UPL" for c in res.combos), tr)
        tr.table(["Appui", "Comb.", "Type", "T (kN)", "γ·W (kN)", "Fs", "Fs requis", "Vérif."],
                 [[r["joint"], r["combo"], r["type"], fmt(r["T"]), fmt(r["Wst"]), fmt(r["fs"]), fmt(r["req"]), _ok(r["ok"])]
                  for r in res.ev["upl"]], "Soulèvement – combinaisons avec traction au pied de poteau")
    else:
        tr.para("Aucune combinaison ne provoque de traction au pied du poteau : pas de risque de soulèvement.", "note")

    # -------------------------------------------------- reinforcement
    tr.sec(f"{n}.7 Ferraillage de la semelle", 2)
    tr.step("Hauteurs utiles (barres // au plus grand côté en lit inférieur)",
            "d₁ = h − c − φ/2 ; d₂ = h − c − 1,5·φ",
            f"φ supposé = {fmt(o.phi_assumed * 1000, 0)} mm", f"dₓ = {fmt(dX, 3)} m ; d_y = {fmt(dY, 3)} m")
    for key in ("X", "Y"):
        rc = res.rc[key]
        L, Wd, l, Ls, Ws, ls = g.dir(key)
        tr.sec(f"Armatures parallèles à {Ls} (direction {key.lower()}), réparties sur {Ws} = {fmt(Wd)} m", 3)
        ult = [r for r in rc["rows"] if r["type"] != "ELS"]
        ser = [r for r in rc["rows"] if r["type"] == "ELS"]
        for rows, lab in ((ult, "ELU / accidentel"), (ser, "ELS")):
            gv = max(rows, key=lambda r: max(r["As_biel"] or 0, r["As_flex"] or 0), default=None)
            if gv and max(gv["As_biel"] or 0, gv["As_flex"] or 0) > 0:
                tr.para(f"Combinaison {lab} déterminante : {gv['combo']} (appui {gv['joint']})", "bold")
                rc_direction(g, _combo(res, gv["combo"], gv["joint"]), key, rc["d"], m, tr)
        tr.table(["Appui", "Comb.", "Type", "Nu (kN)", "M (kN·m)", "M₁ (kN·m)", "As bielles", "As moments", "As sup."],
                 [[r["joint"], r["combo"], r["type"], fmt(r["Nrc"]), fmt(r["Mb"]), fmt(r["M1"]),
                   fmt(r["As_biel"]), fmt(r["As_flex"]), fmt(r["As_top"])] for r in rc["rows"]],
                 f"Ferraillage // {Ls} – toutes combinaisons (cm²)")
        tr.step("Condition de non-fragilité", f"As,min = 0,23·{Ws}·d·ft28/fe",
                f"0,23 × {fmt(Wd)} × {fmt(rc['d'], 3)} × {fmt(m.ft28)} / {fmt(m.fe, 0)} × 10⁴", f"{fmt(rc['Amin'])} cm²", ref("non_frag"))
        v = rc["vals"]
        lab = dict(biel_u="bielles ELU", flex_u="moments ELU", biel_s="bielles ELS", flex_s="moments ELS", min="non-fragilité")
        tr.step("Section d'acier retenue (maximum des méthodes)",
                "As = max(As,bielles ; As,moments ; As,ELS ; As,min)",
                " ; ".join(f"{lab[k]} = {fmt(x)}" for k, x in v.items()),
                f"As = {fmt(rc['As_req'])} cm² (déterminant : {lab[rc['governs']]})", ref("bielles"))
        b = rc["bars"]
        tr.step("Choix des armatures", f"n = max(As/aφ ; ({Ws} − 2c)/Smax + 1) ; S = ({Ws} − 2c)/(n − 1)",
                f"Smax = {fmt(rc['smax'] * 100, 0)} cm ({m.cracking}) ; {Ws} − 2c = {fmt(Wd - 2 * m.cover)} m",
                _bars(b), ref("espacement"), b["As"] >= rc["As_req"] - 1e-9 and b["s"] <= rc["smax"] + 1e-9,
                f"{fmt(b['As'])} ≥ {fmt(rc['As_req'])} cm² ; S = {fmt(b['s'] * 100, 1)} ≤ {fmt(rc['smax'] * 100, 0)} cm")
        lsv = rc["ls"]
        if lsv > L / 4:
            disp = "ls > L/4 : toutes les barres doivent comporter des crochets d'ancrage (ancrage courbe)"
        elif lsv > L / 8:
            disp = "L/8 < ls ≤ L/4 : barres droites sur toute la longueur, sans crochets"
        else:
            disp = "ls ≤ L/8 : barres droites ; arrêt possible d'une barre sur deux à 0,71·L (ou alternées à 0,86·L)"
        tr.step("Ancrage des barres", "ls = φ·fe/(4·τs) — comparaison avec L/4 et L/8",
                f"{b['phi']} mm × {fmt(m.fe, 0)} / (4 × {fmt(m.tau_s)}) ; {Ls}/4 = {fmt(L / 4, 3)} m ; {Ls}/8 = {fmt(L / 8, 3)} m",
                f"ls = {fmt(lsv, 3)} m → {disp}", ref("anc_semelle"))
        if rc["top"]:
            t = rc["top"]
            tr.para(f"Nappe supérieure (soulèvement) – combinaison déterminante : {t['combo']} (appui {t['joint']})", "bold")
            rc_direction(g, _combo(res, t["combo"], t["joint"]), key, rc["d"], m, tr)
            tr.step("Nappe supérieure retenue", "As,sup = max(As,sup,calc ; As,min)",
                    f"max({fmt(t['As_top'])} ; {fmt(rc['Amin'])})", _bars(rc["bars_top"]), ref("non_frag"))

    # -------------------------------------------------- punching / shear
    tr.sec(f"{n}.8 Vérification au poinçonnement", 2)
    p = _gov(res.punch)
    if p:
        tr.para(f"Combinaison déterminante : {p['combo']}", "bold")
        check_punching(g, _combo(res, p["combo"], p["joint"]), m, tr)
    else:
        tr.para("Pas de compression au pied du poteau : poinçonnement sans objet.", "note")
    if res.shear:
        tr.sec(f"{n}.9 Vérification à l'effort tranchant (semelle flexible)", 2)
        for key in ("X", "Y"):
            sv = _gov([x for x in res.shear if x["key"] == key])
            if sv:
                check_shear(g, _combo(res, sv["combo"], sv["joint"]), key, res.rc["d"][key], m, tr)

    # -------------------------------------------------- pedestal
    tr.sec(f"{n}.10 Ferraillage du fût (amorce de poteau)", 2)
    ped = res.ped
    tr.para("Approche simplifiée : chaque direction est calculée en flexion composée (ou traction) avec les efforts "
            "à la base du fût ; les armatures sont disposées symétriquement.", "note")
    for key in ("X", "Y"):
        pr = max(ped["rows"], key=lambda r: r["As_" + key], default=None)
        if pr:
            tr.para(f"Direction {key.lower()} – combinaison déterminante : {pr['combo']} (appui {pr['joint']})", "bold")
            pedestal_check(g, _combo(res, pr["combo"], pr["joint"]), m, tr, keys=(key,), header=(key == "X"))
    tr.step("Section minimale", "As,min = ρmin·ap·bp",
            f"{fmt(o.rho_min_ped, 2)} % × {fmt(g.ap * 100, 0)} × {fmt(g.bp * 100, 0)}", f"{fmt(ped['Amin'])} cm²", ref("rpa_poteau_min"))
    pb = ped["bars"]
    tr.step("Armatures longitudinales retenues",
            "n = 2·nₓ + 2·n_y − 4 (barres d'angle communes)",
            f"face ⟂ x : {fmt(ped['Afx'])} cm² ; face ⟂ y : {fmt(ped['Afy'])} cm² ; As,min = {fmt(ped['Amin'])} cm²",
            f"{pb['n']} HA{pb['phi']} = {fmt(pb['As'])} cm² ({pb['nx']} par face ⟂ x, {pb['ny']} par face ⟂ y)",
            ref("rpa_poteau_min"), pb["As"] >= ped["Amin"] - 1e-9, f"{fmt(pb['As'])} ≥ {fmt(ped['Amin'])} cm²")
    tr.para("Armatures transversales : cadres HA8, St = 10 cm en zone nodale, 15 cm en zone courante (RPA). "
            "Les attentes du fût sont ancrées dans la semelle par un retour horizontal sur la nappe inférieure.", "note")

    # -------------------------------------------------- conclusion
    tr.sec(f"{n}.11 Conclusion – semelle {gi.name}", 2)
    tr.table(["Vérification", "Résultat"], [
        ["Portance du sol", _ok(res.ev["ok_b"])],
        ["Renversement", _ok(res.ev["ok_o"])],
        ["Soulèvement", _ok(res.ev["ok_u"]) if res.ev["upl"] else "sans objet"],
        ["Ferraillage semelle (μ ≤ μl, σbc ≤ σ̄bc)", _ok(res.rc["ok"])],
        ["Poinçonnement", _ok(all(p["ok"] for p in res.punch))],
        ["Fût", _ok(res.ped["ok"])],
        ["Global", _ok(res.ok)],
    ])
