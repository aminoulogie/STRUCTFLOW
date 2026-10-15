"""Project orchestration: run every footing group and write the full calculation trace."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .combos import ComboDef, apply
from .footing import (Codes, GroupInput, GroupResult, Options, check_bearing, check_overturning, check_punching,
                      check_shear, check_sliding, check_uplift, design_group, h_required, pedestal_check, rc_direction)
from .longrine import LongrineInput, build_network, design_longrine, design_network
from .materials import Materials
from .references import ref
from .sketch import draw
from .soil import METHODS, Soil, capacities
from .notecfg import charges_tables, combos_paras, materials_rows, site_rows
from .trace import Trace, fmt

TYPE_LABEL = {"ELU": "ELU (fondamentale)", "ELS": "ELS (service)", "ACC": "Sismique (RPA 2024)", "UPL": "EC7 UPL"}


@dataclass
class Project:
    meta: dict              # ouvrage, moa, lieu, bureau, ingenieur, indice, zone, site
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
    short: bool = True          # note abrégée : combinaisons déterminantes uniquement
    coords: dict = field(default_factory=dict)   # {appui: (x, y)} for the tie-beam network
    net_tol: float = 0.30
    net_lmax: float = 12.0


def group_combos(prj: Project, gi: GroupInput):
    combos = []
    rows = [r for r in prj.loads if r["Groupe"] == gi.name]
    joints = sorted({r["Appui"] for r in rows}, key=str)
    gi.joints = joints
    for j in joints:
        cases = [dict(case=r["Cas"], type=r["Type"], N=r["N"], Vx=r["Vx"], Vy=r["Vy"], Mx=r["Mx"], My=r["My"])
                 for r in rows if r["Appui"] == j]
        combos += apply(j, cases, prj.combo_defs, gi.pinned)
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
        # RPA 2024 §10.1.1 : N = valeur moyenne des charges verticales des appuis solidarisés en situation sismique.
        # Retenu : moyenne des deux appuis les plus chargés (paire la plus défavorable).
        per = {}
        for r in prj.results:
            for c in r.combos:
                if c.ctype == "ACC":
                    per[c.joint] = max(per.get(c.joint, 0.0), c.N)
        src = "ACC"
        if not per:
            src = "ELS"
            for r in prj.results:
                for c in r.combos:
                    if c.ctype == "ELS":
                        per[c.joint] = max(per.get(c.joint, 0.0), c.N)
        top = sorted(per.items(), key=lambda kv: -kv[1])[:2]
        Nmean = sum(v for _, v in top) / max(len(top), 1)
        prj.lg = dict(Nmean=Nmean, top=top, src=src, res=design_longrine(prj.longrine, Nmean, prj.mat),
                      beams=[], types=[], Nj=per)
        coords = {j: xy for j, xy in prj.coords.items() if j in per}
        if len(coords) >= 2:
            dims = {j: (r.geo.ap, r.geo.bp) for r in prj.results for j in r.gi.joints}
            beams = build_network(coords, dims, prj.net_tol, prj.net_lmax)
            types = design_network(prj.longrine, beams, per, prj.mat)
            if types:
                gov = max(types, key=lambda t: t["res"]["As"])
                prj.lg.update(beams=beams, types=types, res=gov["res"])
    return prj.results


# ====================================================================== trace / note de calcul
def _ok(b):
    return "OK" if b else "NON OK"


def _bars(b):
    return f"{b['n']} HA{b['phi']} e = {b['s'] * 100:.0f} cm ({b['As']:.2f} cm²)" if b else "—"


def _gov(rows, key="ratio", pred=lambda r: True):
    rows = [r for r in rows if pred(r) and r.get(key) is not None and not (isinstance(r[key], float) and math.isnan(r[key]))]
    return max(rows, key=lambda r: r[key]) if rows else None


def critical_set(res: GroupResult):
    """Governing (combination, support) pairs kept in the abridged note:
    the most critical ELU, the most critical ELS, and for every seismic combination the most critical support."""
    score = {}

    def bump(key, v):
        if v is not None and v == v:
            score[key] = max(score.get(key, 0.0), min(v, 1e6))

    for k in ("bear", "ovt", "upl", "sld"):
        for r in res.ev.get(k) or []:
            bump((r["combo"], r["joint"]), r["ratio"])
    for key in ("X", "Y"):
        rows = res.rc[key]["rows"]
        amax = max([max(r["As_biel"] or 0, r["As_flex"] or 0, r["As_top"] or 0) for r in rows] or [0]) or 1.0
        for r in rows:
            bump((r["combo"], r["joint"]), max(r["As_biel"] or 0, r["As_flex"] or 0, r["As_top"] or 0) / amax)
    ctype = {(c.name, c.joint): c.ctype for c in res.combos}
    keep, role = set(), {}
    for t, lab in (("ELU", "ELU le plus défavorable"), ("ELS", "ELS le plus défavorable"),
                   ("UPL", "UPL le plus défavorable")):
        cand = [k for k in score if ctype.get(k) == t]
        if cand:
            k = max(cand, key=lambda k: score[k])
            keep.add(k)
            role[k] = lab
    names = list(dict.fromkeys(c.name for c in res.combos if c.ctype == "ACC"))
    for nm in names:
        cand = [k for k in score if k[0] == nm]
        if cand:
            k = max(cand, key=lambda k: score[k])
            keep.add(k)
            role[k] = "sismique – appui le plus défavorable"
    return keep, role


def _combo(res: GroupResult, name, joint):
    return next(c for c in res.combos if c.name == name and c.joint == joint)


def build_trace(prj: Project) -> Trace:
    tr = Trace()
    m, s, cd, o = prj.mat, prj.soil, prj.codes, prj.opts

    # ---------------------------------------------------------------- 1. hypotheses
    tr.sec("1. Objet et hypothèses générales", key="hyp")
    tr.para(f"La présente note a pour objet le dimensionnement et le ferraillage des semelles isolées sous poteaux "
            f"métalliques (avec fûts/amorces en béton armé) de l'ouvrage « {prj.meta.get('ouvrage', '')} », "
            f"ainsi que la vérification de leur stabilité vis-à-vis du sol, conformément aux règlements algériens en vigueur.")
    tr.table(["Vérification", "Règlement retenu"], [
        ["Béton armé (ferraillage, ELS, poinçonnement)", cd.rc],
        ["Portance du sol", cd.bearing + (" (ELS selon DTR BC 2.331)" if cd.ec7_bearing else "")],
        ["Règlement parasismique", "RPA 2024 (DTR B-C 2.48)"],
        ["Combinaisons sismiques", "RPA 2024 §5.7 éq. (5.6) – définies à partir des cas de charge"],
        ["Renversement", "RPA 2024 §4.5.1 et §5.5 (Fs ≥ 1,3 sous séisme)"
         + (f" + Fs ≥ {fmt(o.fs_overturn, 1)} en ELS/ELU" if cd.overturning != "RPA seul" else "")],
        ["Soulèvement", "Fs = W/T (poids stabilisant / traction) ≥ " f"{fmt(o.fs_uplift_els, 1)} ELS ; ≥ {fmt(o.fs_uplift_elu, 1)} ELU et séisme"
         if cd.uplift == "Classique" else "EN 1997-1 §2.4.7.4 – état limite UPL"],
        ["Glissement", "RPA 2024 §5.5 et §10.1.5 (Fs = 1,25 sismique) / DTR BC 2.33.1" if o.slide_on else "non vérifié"],
        ["Combinaisons fondamentales / service", "BAEL 91 mod.99 – CCM 97"],
    ], "Tableau 1 – Règlements appliqués")
    if prj.meta.get("zone") or prj.meta.get("site"):
        mt = prj.meta
        tr.table(["Paramètre sismique (RPA 2024)", "Valeur"], [
            ["Zone sismique (§3.1, annexe A)", mt.get("zone", "—")], ["Catégorie de site", mt.get("site", "—")],
            ["Groupe d'importance", mt.get("group", "—")], ["A – coefficient d'accélération de zone (tableau 3.3)", fmt(mt.get("A"), 2)],
            ["I – coefficient d'importance (tableau 3.11)", fmt(mt.get("I"), 2)],
            [f"S – coefficient de site (tableau {'3.5' if mt.get('zone') in ('I', 'II', 'III') else '3.4'})", fmt(mt.get("S"), 2)],
            ["R/Q_F (fondations isolées, §5.7 éq. (5.6))", fmt(mt.get("omega"), 2)],
            ["ψ – coefficient d'accompagnement (tableau 4.2)", fmt(mt.get("psi"), 2)],
        ], "Tableau – Données sismiques")
    for w in m.warnings(prj.meta.get("zone", "III")):
        tr.para(w, "warn")
    tr.para("Unités : forces en kN, moments en kN·m, longueurs en m, contraintes du sol en kPa (1 bar = 100 kPa), "
            "contraintes des matériaux en MPa, sections d'acier en cm².")
    tr.para("Conventions : N > 0 en compression ; A = dimension de la semelle selon x, B selon y ; fût ap × bp. "
            "Les moments sont ramenés à la sous-face de la semelle : My,b = My + Vx·H et Mx,b = Mx − Vy·H, "
            "avec H = hauteur entre le point d'application des réactions (platine, ou cote des appuis du modèle) "
            "et l'assise.")
    tr.para("Méthode de ferraillage : la section d'acier retenue est le maximum entre la méthode des bielles "
            "(semelle rigide, e₀ ≤ B/6) et la méthode des moments (consoles, section S1 à 0,35·b de l'axe), "
            "à l'ELU, en situation accidentelle et à l'ELS (fissuration préjudiciable ou très préjudiciable), "
            "sans être inférieure à la condition de non-fragilité.")

    tr.sec("2. Caractéristiques des matériaux", key="mat_tab")
    tr.table(["", ""], materials_rows(m.fc28, m.fe, m.gamma_c, m.gamma_b, m.gamma_b_acc, m.gamma_s, m.gamma_s_acc,
                                      m.theta, m.sigma_s_bar, m.cracking, "Béton – infrastructure"))

    tr.sec("3. Caractéristiques du site selon le rapport du sol", key="site")
    tr.table(["", ""], site_rows(prj.meta.get("site"), s.sigma_adm / 100 if s.method == "adm" else 0, s.D,
                                 prj.meta.get("sol_extra")))

    if prj.meta.get("charges"):
        tr.sec("4. Charges permanentes et surcharges d'exploitation [DTR B.C. 2.2]", key="charges")
        charges_tables(tr, prj.meta["charges"])

    tr.sec("5. Combinaisons d'actions", key="combos")
    combos_paras(tr, prj.meta.get("seis_label", "1,4"), prj.meta.get("psi") or 0.3)

    tr.sec("6. Résistances de calcul des matériaux", key="mat_calc")
    m.describe(tr)

    tr.sec("7. Caractéristiques du sol de fondation", key="sol")
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
        rows += [["Fs ELS / Fs ELU / Fs sismique", f"{fmt(s.fs_els, 1)} / {fmt(s.fs_elu, 1)} / {fmt(s.fs_acc, 1)}"]]
    if o.slide_on:
        rows += [["Glissement : φ' / c' à l'interface", f"{fmt(s.phi_s, 1)}° / {fmt(s.c_s, 1)} kPa"]]
    tr.table(["Paramètre", "Valeur"], rows, "Tableau 2 – Données géotechniques")
    if s.method == "cphi":
        tr.para("La contrainte de rupture dépend de la largeur B : elle est calculée pour chaque semelle (§ semelles).", "note")
    else:
        capacities(s, 1.0, 1.0, s.D, tr)

    tr.sec("8. Combinaisons retenues dans le calcul", 2, key="combos")
    tr.para("Les combinaisons sont définies par l'utilisateur en affectant un coefficient à chacun des cas de charge "
            "élémentaires issus du modèle (G permanentes, Q exploitation, S neige, W vent, E séisme). "
            "Les résultats déjà combinés importés (ELU/ELS/ACC) sont utilisés directement. Le poids propre de la "
            "semelle, du fût et du remblai est affecté du coefficient des charges permanentes G de chaque combinaison.")
    prj._keep = {r.gi.name: critical_set(r) for r in prj.results} if prj.short else {}
    used = {k[0] for ks, _ in prj._keep.values() for k in ks}
    defs = [d for d in prj.combo_defs if d.name in used] if prj.short else prj.combo_defs
    if prj.short:
        tr.para(f"{len(prj.combo_defs)} combinaisons ont été vérifiées pour chaque appui. La note ne reproduit que les "
                "combinaisons déterminantes : l'ELU et l'ELS les plus défavorables et, pour chacune des combinaisons "
                "sismiques, l'appui le plus défavorable. Toutes les vérifications restent satisfaites pour les autres "
                "combinaisons (résultats complets dans l'application).")
    if prj.meta.get("seis_desc"):
        tr.para("Combinaisons sismiques retenues : " + prj.meta["seis_desc"] + ".", "bold")
    tr.table(["Nom", "Type", "Combinaison", "Référence"],
             [[d.name, TYPE_LABEL[d.ctype], d.label(),
               ref("rpa_combo") if d.ctype == "ACC" else ref("combo_elu" if d.ctype == "ELU" else "combo_els")]
              for d in defs], "Tableau 3 – Combinaisons d'actions" + (" (déterminantes)" if prj.short else ""))
    if any(d.ctype == "UPL" for d in prj.combo_defs):
        tr.para("Combinaisons UPL (EC7) : 0,9·G + 1,5·W, utilisées pour la vérification au soulèvement.", "note")

    # ---------------------------------------------------------------- footing groups
    for i, res in enumerate(prj.results, start=5):
        _group_trace(tr, prj, res, i)

    # ---------------------------------------------------------------- longrines
    n = 5 + len(prj.results)
    if prj.lg:
        tr.sec(f"{n}. Longrines (chaînage des semelles)", key="longrines")
        li = prj.longrine
        tr.para("Les points d'appui sont solidarisés par un réseau bidirectionnel de longrines (RPA 2024 §10.1.1 a).")
        if prj.lg["types"]:
            _network_trace(tr, prj)
            n += 1
            prj_lg_done = True
        else:
            prj_lg_done = False
    if prj.lg and not prj_lg_done:
        li = prj.longrine
        top = prj.lg["top"]
        lab = "situation sismique" if prj.lg["src"] == "ACC" else "ELS (aucune combinaison sismique définie)"
        tr.step("Effort vertical moyen des appuis solidarisés (paire la plus chargée, " + lab + ")",
                "N = (N₁ + N₂)/2", " ; ".join(f"appui {j} : {fmt(v)} kN" for j, v in top), f"N = {fmt(prj.lg['Nmean'])} kN",
                ref("rpa_longrine_F"))
        tr.para(f"Données sismiques : A = {fmt(li.A, 3)} (tableau 3.3) ; I = {fmt(li.I, 2)} (tableau 3.11) ; "
                f"S = {fmt(li.S, 2)} (tableau {'3.5' if li.zone in ('I', 'II', 'III') else '3.4'}) ; site {li.site} ; zone {li.zone}.")
        design_longrine(li, prj.lg["Nmean"], m, tr)
        n += 1

    # ---------------------------------------------------------------- summary
    tr.sec(f"{n}. Tableau récapitulatif", key="recap")
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
    if prj.lg and prj.lg["types"]:
        tr.table(["Type", "Portée libre (m)", "Nb", "F (kN)", "Armatures", "Cadres"],
                 [[t["name"], fmt(t["Lc"]), len(t["beams"]), fmt(t["res"]["F"]),
                   f"{t['res']['bars']['n']} HA{t['res']['bars']['phi']}",
                   f"HA{t['res']['phit']} e = {fmt(t['res']['st'] * 100, 0)} cm"] for t in prj.lg["types"]],
                 f"Longrines {fmt(prj.longrine.b * 100, 0)} × {fmt(prj.longrine.h * 100, 0)} cm")
    elif prj.lg:
        lr = prj.lg["res"]
        tr.para(f"Longrines {fmt(prj.longrine.b * 100, 0)} × {fmt(prj.longrine.h * 100, 0)} cm : "
                f"F = {fmt(lr['F'])} kN → {lr['bars']['n']} HA{lr['bars']['phi']} — cadres HA{lr['phit']} e = {fmt(lr['st'] * 100, 0)} cm.", "bold")
    return tr


def _network_trace(tr: Trace, prj: Project):
    li, lg = prj.longrine, prj.lg
    tr.para(f"Le réseau est établi à partir des coordonnées des appuis : chaque appui est relié à son voisin aligné "
            f"le plus proche selon x et selon y (tolérance d'alignement {fmt(prj.net_tol)} m). Les liaisons de plus de "
            f"{fmt(prj.net_lmax)} m ne sont pas retenues (cas des hangars : dallage travaillant en tirant / buton, "
            "RPA 2024 §10.1.1 d). La portée libre est la distance entre axes diminuée de la demi-dimension des deux fûts.")
    tr.para(f"Données sismiques : A = {fmt(li.A, 3)} ; I = {fmt(li.I, 2)} ; S = {fmt(li.S, 2)} ; site {li.site} ; "
            f"zone {li.zone}. N = moyenne des efforts verticaux des deux appuis reliés, en situation sismique.")
    tr.table(["Longrine", "Appuis", "Dir.", "L axe (m)", "Portée libre (m)", "N moyen (kN)", "Type"],
             [[b["id"], f"{b['j1']} – {b['j2']}", b["dir"], fmt(b["L"]), fmt(b["Lc"]),
               fmt(b.get("N")) if b["kept"] else "—", b.get("tname", b["why"])] for b in lg["beams"]],
             "Réseau de longrines")
    for t in lg["types"]:
        tr.sec(f"Longrine type {t['name']} – portée libre {fmt(t['Lc'])} m ({len(t['beams'])} longrine(s))", 2)
        worst = max(t["beams"], key=lambda b: b["N"])
        tr.step("Effort vertical moyen (longrine la plus chargée du type)", "N = (N₁ + N₂)/2",
                f"{worst['id']} : ({fmt(lg['Nj'].get(worst['j1'], 0))} + {fmt(lg['Nj'].get(worst['j2'], 0))}) / 2",
                f"N = {fmt(t['N'])} kN", ref("rpa_longrine_F"))
        design_longrine(t["li"], t["N"], prj.mat, tr)


def _group_trace(tr: Trace, prj: Project, res: GroupResult, n: int):
    m, s, cd, o = prj.mat, prj.soil, prj.codes, prj.opts
    g, gi = res.geo, res.gi
    keep, role = getattr(prj, "_keep", {}).get(gi.name, (None, {}))

    def K(r):
        return keep is None or (r["combo"], r["joint"]) in keep

    sfx = " – combinaisons déterminantes" if keep is not None else " – toutes combinaisons"
    tr.sec(f"{n}. Semelle {gi.name}", key="semelles")
    tr.para(f"Appuis concernés : {', '.join(gi.joints)}. Liaison pied de poteau : {gi.base}. "
            f"Fût {fmt(gi.ap * 100, 0)} × {fmt(gi.bp * 100, 0)} cm, arase supérieure à {fmt(gi.h_above)} m au-dessus du TN.")
    for msg in res.msgs:
        tr.para(msg, "warn")

    # -------------------------------------------------- dimensions
    tr.sec(f"{n}.1 Dimensionnement de la semelle", 2, key="dim")
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
    if g.z_app is None:
        tr.step("Hauteur du fût et bras de levier des efforts horizontaux", "Hp = D − h + h₀ ; H = D + h₀",
                f"Hp = {fmt(g.D)} − {fmt(g.h)} + {fmt(gi.h_above)} ; H = {fmt(g.D)} + {fmt(gi.h_above)}",
                f"Hp = {fmt(g.Hp)} m ; H = {fmt(g.lever)} m")
    else:
        tr.para(f"Appuis du modèle Robot à la cote z = {fmt(g.z_app)} m (TN = 0) : les réactions incluent déjà le moment "
                "des efforts horizontaux jusqu'à cette cote ; elles sont transportées de z à la sous-face de la semelle.", "note")
        tr.step("Hauteur du fût et bras de levier des efforts horizontaux", "Hp = D − h + h₀ ; H = D + z_appuis",
                f"Hp = {fmt(g.D)} − {fmt(g.h)} + {fmt(gi.h_above)} ; H = {fmt(g.D)} + ({fmt(g.z_app)})",
                f"Hp = {fmt(g.Hp)} m ; H = {fmt(g.lever)} m")
    tr.table(["Prédimensionnement de la semelle", "Valeur"], [
        ["Longueur A (m)", fmt(g.A)], ["Largeur B (m)", fmt(g.B)], ["Hauteur h (m)", fmt(g.h)],
        ["Débord (A − ap)/2 (m)", fmt((g.A - g.ap) / 2)], ["Ancrage D (m)", fmt(g.D)],
        ["Fût ap × bp (m)", f"{fmt(g.ap)} × {fmt(g.bp)}"], ["Poids semelle (kN)", fmt(g.Wf)], ["Poids fût (kN)", fmt(g.Wp)],
        ["Poids des terres (kN)", fmt(g.Ws)], ["Rigidité", "SEMELLE RIGIDE" if min(dX, dY) >= dreq - 1e-9 else "semelle flexible"],
    ])
    tr.table(["Fe (MPa)", "fc28 (MPa)", "Ancrage D (m)", "σsol ELS (bar)", "a (m)", "b (m)", "A (m)", "B (m)", "H (m)"],
             [[fmt(m.fe, 0), fmt(m.fc28, 0), fmt(g.D), fmt(caps["q_els"] / 100), fmt(g.ap), fmt(g.bp), fmt(g.A), fmt(g.B),
               fmt(g.h)]], "FICHE DE LA SEMELLE")
    tr.table(["Poids terres (kN)", "Poids semelle (kN)", "Poids fût (kN)", "W total (kN)"],
             [[fmt(g.Ws), fmt(g.Wf), fmt(g.Wp), fmt(g.W)]])
    tr.fig(draw(res, m.cover), f"Figure – Semelle {gi.name} : vue en plan et coupe")

    tr.sec(f"{n}.2 Poids propres", 2, key="pp")
    tr.step("Poids de la semelle", "Wf = γc·A·B·h", f"{fmt(g.gc, 1)} × {fmt(g.A)} × {fmt(g.B)} × {fmt(g.h)}", f"{fmt(g.Wf)} kN")
    tr.step("Poids du fût", "Wp = γc·ap·bp·Hp", f"{fmt(g.gc, 1)} × {fmt(g.ap)} × {fmt(g.bp)} × {fmt(g.Hp)}", f"{fmt(g.Wp)} kN")
    tr.step("Poids du remblai", "Ws = γr·(A·B − ap·bp)·(D − h)",
            f"{fmt(g.gr, 1)} × ({fmt(g.A)} × {fmt(g.B)} − {fmt(g.ap)} × {fmt(g.bp)}) × ({fmt(g.D)} − {fmt(g.h)})", f"{fmt(g.Ws)} kN")
    tr.step("Poids total", "W = Wf + Wp + Ws", f"{fmt(g.Wf)} + {fmt(g.Wp)} + {fmt(g.Ws)}", f"{fmt(g.W)} kN")

    tr.sec(f"{n}.3 Efforts en pied de poteau (combinaisons)", 2, key="efforts")
    tr.table(["Appui", "Combinaison", "Type", "Rôle", "N", "Vx", "Vy", "Mx", "My"],
             [[c.joint, c.name, c.ctype, role.get((c.name, c.joint), ""), fmt(c.N), fmt(c.Vx), fmt(c.Vy), fmt(c.Mx),
               fmt(c.My)] for c in res.combos if keep is None or (c.name, c.joint) in keep],
             "Efforts au sommet du fût (kN, kN·m)" + sfx)

    # -------------------------------------------------- bearing
    tr.sec(f"{n}.4 Vérification de la portance du sol", 2, key="portance")
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
    for dk, lab, Ldim, mk in (("sX", "SENS LONGITUDINAL (A)", "A", "Myb"), ("sY", "SENS TRANSVERSAL (B)", "B", "Mxb")):
        rows_ = []
        for r in res.ev["bear"]:
            pr = r.get(dk)
            if not K(r) or not pr:
                continue
            e_ = r["ex"] if dk == "sX" else r["ey"]
            diag = f"e < {Ldim}/6 ⇒ trapézoïdal" if pr["regime"] in ("uniforme", "trapèze") else f"e > {Ldim}/6 ⇒ triangulaire"
            rows_.append([r["combo"], r["joint"], fmt(r["Nt"]), fmt(abs(r[mk])), fmt(e_, 3), diag, fmt(pr["smax"], 1),
                          fmt(pr["smin"], 1), fmt(pr["s34"], 1), fmt(r["q"], 1), _ok(pr["s34"] <= (r["q"] or 0) + 1e-9)])
        if rows_:
            tr.table(["Comb.", "Appui", "N (kN)", "M (kN·m)", "e (m)", "Diagramme des contraintes", "σmax (kPa)", "σmin (kPa)",
                      "σréf (kPa)", "q (kPa)", "Vérif."], rows_, f"VÉRIFICATION DES CONTRAINTES – {lab}")
    tr.table(["Appui", "Comb.", "Type", "Nt (kN)", "eₓ (m)", "e_y (m)", "Diagr. x / y", "σ₃/₄ ou Vd", "q ou Rd", "Taux", "Vérif."],
             [[r["joint"], r["combo"], r["type"], fmt(r["Nt"]), fmt(r["ex"], 3), fmt(r["ey"], 3),
               f"{r['regX']} / {r['regY']}", fmt(r["s34"], 1), fmt(r["q"], 1), f"{fmt(r['ratio'] * 100, 0)} %", _ok(r["ok"])]
              for r in res.ev["bear"] if K(r)], "Portance" + sfx)

    # -------------------------------------------------- overturning
    tr.sec(f"{n}.5 Vérification au renversement", 2, key="renv")
    for meth, lab in (("RPA §5.5", "Combinaison sismique la plus défavorable (RPA 2024 §5.5 : Fs ≥ 1,3)"),
                      ("Fs", "Combinaison la plus défavorable (coefficient de sécurité)")):
        r = _gov(res.ev["ovt"], pred=lambda r, meth=meth: r["method"] == meth)
        if r:
            tr.para(f"{lab} : {r['combo']} (appui {r['joint']})", "bold")
            check_overturning(g, _combo(res, r["combo"], r["joint"]), o, cd, tr, force_fs=meth == "Fs")
    if res.ev["ovt"]:
        tr.table(["Appui", "Comb.", "Type", "Nt (kN)", "My,b", "Mx,b", "Critère", "Détail", "Vérif."],
                 [[r["joint"], r["combo"], r["type"], fmt(r["Nt"]), fmt(r["Myb"]), fmt(r["Mxb"]),
                   r["method"], r["detail"], _ok(r["ok"])] for r in res.ev["ovt"] if K(r)], "Renversement" + sfx)

    # -------------------------------------------------- uplift
    tr.sec(f"{n}.6 Vérification au soulèvement", 2, key="soul")
    if res.ev["upl"]:
        r = _gov(res.ev["upl"])
        tr.para(f"Combinaison la plus défavorable : {r['combo']} (appui {r['joint']})", "bold")
        check_uplift(g, _combo(res, r["combo"], r["joint"]), o, cd, any(c.ctype == "UPL" for c in res.combos), tr)
        tr.table(["Appui", "Comb.", "Type", "T (kN)", "γ·W (kN)", "Fs", "Fs requis", "Vérif."],
                 [[r["joint"], r["combo"], r["type"], fmt(r["T"]), fmt(r["Wst"]), fmt(r["fs"]), fmt(r["req"]), _ok(r["ok"])]
                  for r in res.ev["upl"] if K(r) or r is _gov(res.ev["upl"])],
                 "Soulèvement – combinaisons avec traction au pied de poteau" + (" (déterminantes)" if keep is not None else ""))
    else:
        tr.para("Aucune combinaison ne provoque de traction au pied du poteau : pas de risque de soulèvement.", "note")

    # -------------------------------------------------- sliding
    if o.slide_on:
        tr.sec(f"{n}.6b Vérification au glissement", 2, key="gliss")
        sl = res.ev["sld"]
        if sl:
            for lab, pred in (("sismique (RPA 2024 §10.1.5, Fs = 1,25)", lambda r: r["type"] == "ACC"),
                              ("ELS / ELU", lambda r: r["type"] != "ACC")):
                r = _gov(sl, pred=pred)
                if r:
                    tr.para(f"Combinaison {lab} la plus défavorable : {r['combo']} (appui {r['joint']})", "bold")
                    check_sliding(g, _combo(res, r["combo"], r["joint"]), s, o, tr)
            tr.table(["Appui", "Comb.", "Type", "H (kN)", "Nt (kN)", "A' (m²)", "R (kN)", "Fs", "Fs requis", "Vérif."],
                     [[r["joint"], r["combo"], r["type"], fmt(r["H"]), fmt(r["Nt"]), fmt(r["Ac"], 3), fmt(r["R"]),
                       fmt(r["fs"]), fmt(r["req"]), _ok(r["ok"])] for r in sl if K(r)], "Glissement" + sfx)
        else:
            tr.para("Aucun effort horizontal en pied de poteau : glissement sans objet.", "note")

    # -------------------------------------------------- reinforcement
    tr.sec(f"{n}.7 Ferraillage de la semelle", 2, key="ferr")
    tr.para("Nappe inférieure : toujours nécessaire. La réaction du sol fléchit les consoles de la semelle "
            "(fibre inférieure tendue) ; sa section est le maximum de la méthode des bielles (DTU 13.12 §3.2, "
            "e0 ≤ B/6) et de la méthode des moments à la section S1 (BAEL 91 A.4.3), sans être inférieure à la "
            "condition de non-fragilité (BAEL A.4.2.1).", "note")
    tr.para("Nappe supérieure : exigée par le calcul uniquement lorsque le moment à la section S1 devient négatif "
            "(fibre supérieure tendue), c'est-à-dire lorsque le poids de la semelle et du remblai sur la console "
            "dépasse la réaction du sol – cas des poteaux soulevés par le vent ou le séisme (traction N < 0) ou des "
            "fortes excentricités (diagramme triangulaire). Aucun article des règles BAEL / CBA / DTR BC 2.331 / "
            "RPA 2024 n'impose une nappe supérieure en fonction de la largeur de la semelle ; une nappe supérieure "
            "constructive est seulement d'usage pour les semelles très épaisses (retrait, h ≳ 1,00 m).", "note")
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
                   fmt(r["As_biel"]), fmt(r["As_flex"]), fmt(r["As_top"])] for r in rc["rows"] if K(r)],
                 f"Ferraillage // {Ls} (cm²)" + sfx)
        tr.step("Condition de non-fragilité", f"As,min = 0,23·{Ws}·d·ft28/fe",
                f"0,23 × {fmt(Wd)} × {fmt(rc['d'], 3)} × {fmt(m.ft28)} / {fmt(m.fe, 0)} × 10⁴", f"{fmt(rc['Amin'])} cm²", ref("non_frag"))
        v = rc["vals"]
        lab = dict(biel_u="bielles ELU", flex_u="moments ELU", biel_s="bielles ELS", flex_s="moments ELS", min="non-fragilité")
        tr.step("Section d'acier retenue (maximum des méthodes)",
                "As = max(As,bielles ; As,moments ; As,ELS ; As,min)",
                " ; ".join(f"{lab[k]} = {fmt(x)}" for k, x in v.items()),
                f"As = {fmt(rc['As_req'])} cm² (déterminant : {lab[rc['governs']]})", ref("bielles"))
        b = rc["bars"]
        tr.step("Armatures proposées (vérification)" if b.get("user") else "Choix des armatures",
                f"n = ({Ws} − 2c)/S + 1 ; As fourni = n·aφ ≥ As requis" if b.get("user")
                else f"n = max(As/aφ ; ({Ws} − 2c)/Smax + 1) ; S = ({Ws} − 2c)/(n − 1)",
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
            bt = rc["bars_top"]
            tr.step("Nappe supérieure retenue", "As,sup = max(As,sup,calc ; As,min)",
                    f"max({fmt(t['As_top'])} ; {fmt(rc['Amin'])})", _bars(bt), ref("non_frag"),
                    bt is not None and bt["As"] >= rc["As_top"] - 1e-9,
                    f"{fmt(bt['As'] if bt else 0)} ≥ {fmt(rc['As_top'])} cm²")

    # -------------------------------------------------- punching / shear
    tr.sec(f"{n}.8 Vérification au poinçonnement", 2, key="poinc")
    p = _gov(res.punch)
    if p:
        tr.para(f"Combinaison déterminante : {p['combo']}", "bold")
        check_punching(g, _combo(res, p["combo"], p["joint"]), m, tr)
    else:
        tr.para("Pas de compression au pied du poteau : poinçonnement sans objet.", "note")
    if res.shear:
        tr.sec(f"{n}.9 Vérification à l'effort tranchant (semelle flexible)", 2, key="tranchant")
        for key in ("X", "Y"):
            sv = _gov([x for x in res.shear if x["key"] == key])
            if sv:
                check_shear(g, _combo(res, sv["combo"], sv["joint"]), key, res.rc["d"][key], m, tr)

    # -------------------------------------------------- pedestal
    tr.sec(f"{n}.10 Ferraillage du fût (amorce de poteau)", 2, key="fut")
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
    tr.para(f"Espacement maximal des barres longitudinales : {fmt(o.s_max_ped * 100, 0)} cm ; au moins une barre "
            "intermédiaire par face ; φ ≥ 12 mm (RPA 2024 §7.4).", "note")
    tr.para("Armatures transversales : cadres HA8, St = 10 cm en zone nodale, 15 cm en zone courante (RPA). "
            "Les attentes du fût sont ancrées dans la semelle par un retour horizontal sur la nappe inférieure.", "note")

    # -------------------------------------------------- constructive details
    tr.sec(f"{n}.10b Dispositions constructives", 2, key="dispo")
    bx, by = res.rc["X"]["bars"], res.rc["Y"]["bars"]
    phi_max = max(bx["phi"], by["phi"])
    ls_ = m.ls(phi_max / 1000)
    tr.step("Enrobage des armatures de la semelle", "c ≥ 5 cm (béton coulé contre le sol, sur béton de propreté)",
            "", f"c = {fmt(m.cover * 100, 1)} cm", "BAEL 91 mod.99 A.7.1 – protection des armatures",
            m.cover >= 0.05 - 1e-9, f"{fmt(m.cover * 100, 1)} ≥ 5 cm")
    tr.step("Béton de propreté", "e ≥ 5 cm, débord ≥ 5 cm", "", "dosage ≥ 150 kg/m³", "DTU 13.12 / DTR BC 2.331")
    tr.step("Longueur de scellement droit", "ls = φ·fe/(4·τs)",
            f"{phi_max} mm × {fmt(m.fe, 0)} / (4 × {fmt(m.tau_s)})", f"ls = {fmt(ls_, 3)} m", ref("ls"))
    tr.step("Crochet normal (ancrage courbe) des barres HA", "angle 180°, rayon de courbure r ≥ 5,5·φ ; "
            "longueur d'ancrage hors crochet la ≥ 0,4·ls",
            f"r ≥ 5,5 × {phi_max} = {fmt(5.5 * phi_max / 10, 1)} cm ; 0,4 × {fmt(ls_, 3)}",
            f"la ≥ {fmt(0.4 * ls_, 3)} m", "BAEL 91 mod.99 A.6.1.25 – ancrages courbes")
    for key, lab in (("X", "A"), ("Y", "B")):
        rc = res.rc[key]
        L_ = rc["L"]
        if rc["ls"] > L_ / 4:
            disp = "crochets aux deux extrémités (ls > L/4)"
        elif rc["ls"] > L_ / 8:
            disp = "barres droites sur toute la longueur, sans crochets (L/8 < ls ≤ L/4)"
        else:
            disp = "barres droites ; une barre sur deux peut être arrêtée à 0,71·L (ls ≤ L/8)"
        tr.step(f"Disposition des barres // {lab}", "ls comparé à L/4 et L/8", f"ls = {fmt(rc['ls'], 3)} m ; L = {fmt(L_)} m",
                disp, ref("anc_semelle"))
    pb = res.ped["bars"]
    lr = (60 if o.s_max_ped <= 0.15 else 50) * pb["phi"] / 1000
    tr.step("Attentes du fût (armatures en attente)", "ancrage dans la semelle par retour horizontal (coude 90°) posé "
            "sur la nappe inférieure ; longueur verticale ≥ ls", f"φ = {pb['phi']} mm ; ls = {fmt(m.ls(pb['phi'] / 1000), 3)} m",
            f"retour ≥ 15·φ = {fmt(15 * pb['phi'] / 10, 0)} cm", ref("ls"))
    tr.step("Recouvrement des barres du fût", "Lr ≥ 50·φ (zones I–III) ; 60·φ (zones IV–VI)",
            f"{60 if o.s_max_ped <= 0.15 else 50} × {pb['phi']} mm", f"Lr = {fmt(lr, 2)} m", ref("rpa_poteau_min"))
    tr.step("Cadres du fût", "crochets à 135° avec retour droit ≥ 10·φt ; φt ≥ 6 mm",
            "HA8 : retour ≥ 8 cm", "St = 10 cm (zone nodale) / 15 cm (zone courante)", ref("rpa_poteau_min"))

    # -------------------------------------------------- conclusion
    tr.sec(f"{n}.11 Conclusion – semelle {gi.name}", 2, key="concl")
    tr.table(["Vérification", "Résultat"], [
        ["Portance du sol", _ok(res.ev["ok_b"])],
        ["Renversement", _ok(res.ev["ok_o"])],
        ["Soulèvement", _ok(res.ev["ok_u"]) if res.ev["upl"] else "sans objet"],
        ["Glissement", (_ok(res.ev["ok_s"]) if res.ev["sld"] else "sans objet") if o.slide_on else "non vérifié"],
        ["Ferraillage semelle (μ ≤ μl, σbc ≤ σ̄bc)", _ok(res.rc["ok"])],
        ["Poinçonnement", _ok(all(p["ok"] for p in res.punch))],
        ["Fût", _ok(res.ped["ok"])],
        ["Global", _ok(res.ok)],
    ])
