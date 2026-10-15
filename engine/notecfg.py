"""Shared 'first part' of the notes (materials / site / combinations / loads tables) and the list of chapters
the user can tick. Same file in ISOLATED_FOOTINGS and POTEAUX_FCD."""
from __future__ import annotations

CLASSES = {12: "C12/15", 16: "C16/20", 20: "C20/25", 25: "C25/30", 30: "C30/37", 35: "C35/45", 40: "C40/50",
           45: "C45/55", 50: "C50/60"}
SITE_NAMES = {"S1": "Rocheux", "S2": "Ferme", "S3": "Meuble", "S4": "Très meuble"}
# RPA 2024 tableau 4.2 – coefficient d'accompagnement ψ de la charge d'exploitation
PSI_TABLE = [("Cas 1 – habitation, bureaux ou assimilés", 0.30),
             ("Cas 2 – public temporaire (exposition, sport, culte, classes…)", 0.40),
             ("Cas 3 – entrepôts, hangars", 0.50),
             ("Cas 4 – archives, bibliothèques, réservoirs, équipements médicaux critiques", 1.00),
             ("Cas 5 – autres locaux non visés", 0.60)]

# (key, label, level) — level 1 = chapter, 2 = sub-chapter of each footing / column
SECTIONS_FOOTINGS = [
    ("cover", "Page de garde", 1), ("toc", "Sommaire", 1),
    ("hyp", "Objet et hypothèses générales", 1),
    ("mat_tab", "Caractéristiques des matériaux (tableau)", 1),
    ("site", "Caractéristiques du site selon le rapport de sol", 1),
    ("charges", "Charges permanentes et surcharges d'exploitation [DTR B.C. 2.2]", 1),
    ("combos", "Combinaisons d'actions", 1),
    ("mat_calc", "Résistances de calcul des matériaux (détail)", 1),
    ("sol", "Contraintes admissibles du sol (détail)", 1),
    ("semelles", "Semelles (une partie par semelle type)", 1),
    ("dim", "Dimensionnement / prédimensionnement", 2), ("pp", "Poids propres", 2), ("efforts", "Efforts en pied de poteau", 2),
    ("portance", "Vérification des contraintes du sol", 2), ("renv", "Renversement", 2), ("soul", "Soulèvement", 2),
    ("gliss", "Glissement", 2), ("ferr", "Ferraillage de la semelle", 2), ("poinc", "Poinçonnement", 2),
    ("tranchant", "Effort tranchant (semelle flexible)", 2), ("fut", "Ferraillage du fût", 2),
    ("dispo", "Dispositions constructives", 2), ("concl", "Conclusion de la semelle", 2),
    ("longrines", "Longrines", 1), ("recap", "Tableau récapitulatif", 1),
]
SECTIONS_COLUMNS = [
    ("cover", "Page de garde", 1), ("toc", "Sommaire", 1),
    ("hyp", "Objet et hypothèses", 1), ("mat_tab", "Caractéristiques des matériaux (tableau)", 1),
    ("charges", "Charges permanentes et surcharges d'exploitation [DTR B.C. 2.2]", 1),
    ("combos", "Combinaisons d'actions", 1), ("mat_calc", "Résistances de calcul des matériaux (détail)", 1),
    ("poteaux", "Poteaux (une partie par poteau type)", 1),
    ("coffrage", "Coffrage (RPA 2024 §7.4.1)", 2), ("efforts", "Sollicitations", 2),
    ("stab", "Stabilité de forme (second ordre)", 2), ("elu", "Flexion composée déviée ELU", 2),
    ("long", "Armatures longitudinales", 2), ("els", "État limite de service", 2),
    ("comp", "Compression centrée et effort normal réduit", 2), ("trans", "Effort tranchant et armatures transversales", 2),
    ("ec2", "Contrôle croisé Eurocode 2", 2), ("concl", "Conclusion du poteau", 2),
    ("recap", "Tableau récapitulatif", 1),
]


def fr(x, nd=2):
    return f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")


def concrete_class(fc28):
    return CLASSES.get(int(round(fc28)), f"fc28 = {fr(fc28, 0)} MPa")


def materials_rows(fc28, fe, gamma_c=25.0, gb=1.5, gba=1.2, gs=1.15, gsa=1.0, theta=1.0, sigma_s_bar=None,
                   cracking="FP", label="Béton"):
    ft = 0.6 + 0.06 * fc28
    ei = 11000 * fc28 ** (1 / 3)
    ed = 3700 * fc28 ** (1 / 3)
    crack = {"FPP": "peu préjudiciable", "FP": "préjudiciable", "FTP": "très préjudiciable"}.get(cracking, cracking)
    return [
        {"_group": label},
        ["Poids volumique ρ", f"{fr(gamma_c, 0)} kN/m³"],
        ["Classe de béton", concrete_class(fc28)],
        [f"Résistance du béton à la compression fc28 [{concrete_class(fc28)}]", f"{fr(fc28)} MPa"],
        [f"Résistance du béton à la traction ft28 = 0,6 + 0,06·fc28", f"{fr(ft)} MPa"],
        {"_group": "Module de déformation longitudinale – CBA art. A.2.1.2.1 et A.2.1.2.2", "dark": False},
        ["Module d'élasticité instantané Ei28 = 11 000·fc28^(1/3)", f"{fr(ei)} MPa"],
        ["Module d'élasticité différé Ed28 = 3 700·fc28^(1/3)", f"{fr(ed)} MPa"],
        {"_group": "Coefficients de sécurité", "dark": False},
        ["Situation durable γb", fr(gb)],
        ["Situation accidentelle γb (RPA 2024 §7.3.2)", fr(gba)],
        {"_group": "Contraintes limites de calcul", "dark": False},
        ["ELU – situation durable σbu = 0,85·fc28/(θ·γb)", f"{fr(0.85 * fc28 / (theta * gb))} MPa"],
        ["ELU – situation accidentelle", f"{fr(0.85 * fc28 / (theta * gba))} MPa"],
        ["ELS – σ̄bc = 0,6·fc28", f"{fr(0.6 * fc28)} MPa"],
        {"_group": "Acier"},
        ["Nuance", f"FeE{fr(fe, 0)} – fe = {fr(fe, 0)} MPa"],
        ["Module d'élasticité Es", "200 000 MPa"],
        {"_group": "Coefficients de sécurité", "dark": False},
        ["Situation durable γs", fr(gs)],
        ["Situation accidentelle γs (RPA 2024 §7.3.2)", fr(gsa)],
        {"_group": "Contraintes limites de calcul", "dark": False},
        ["ELU – situation durable σs = fe/γs", f"{fr(fe / gs)} MPa"],
        ["ELU – situation accidentelle", f"{fr(fe / gsa)} MPa"],
        [f"ELS – fissuration {crack}", f"{fr(sigma_s_bar)} MPa" if sigma_s_bar else "non limitée"],
    ]


def site_rows(site, sadm_bar, D, extra=None):
    rows = [{"_group": "Caractéristiques du site selon le rapport du sol"}]
    if site:
        rows.append(["Type de sol", f"{site} : {SITE_NAMES.get(site, '')}"])
    rows.append(["Contrainte admissible", f"{fr(sadm_bar)} bars"])
    rows.append(["Profondeur d'ancrage", f"{fr(D)} m"])
    for k, v in (extra or {}).items():
        if str(v).strip():
            rows.append([k, str(v)])
    return rows


def combos_paras(tr, factor_label="(R/Q_F)", psi=0.5, infra=True):
    """Combinations written like the usual Algerian note (RPA 2024 §5.2 and §5.7)."""
    tr.para("COMBINAISONS ACCIDENTELLES EN SUPERSTRUCTURE – RPA 2024 §5.2, éq. (5.1)-(5.2) :", "sub")
    for t in ("G + ΨQ ± E1", "G + ΨQ ± E2", "E1 = ± Ex ± 0,3·Ey", "E2 = ± 0,3·Ex ± Ey"):
        tr.para(t, "bold")
    if infra and factor_label:
        eq = "éq. (5.7), fondations communes" if factor_label.startswith("1,4") else              "éq. (5.6), fondations d'éléments verticaux individuels" if "R" in factor_label else "situation accidentelle"
        tr.para(f"COMBINAISONS ACCIDENTELLES EN INFRASTRUCTURE – RPA 2024 §5.7, {eq} :", "sub")
        for t in (f"G + ΨQ ± {factor_label}·E1", f"G + ΨQ ± {factor_label}·E2"):
            tr.para(t, "bold")
        if "R" in factor_label:
            tr.para("R : coefficient de comportement (tableau 3.18) ; Q_F : facteur de qualité (§3.8).", "note")
    case = next((n for n, v in PSI_TABLE if abs(v - psi) < 1e-9), "")
    tr.para(f"Ψ = {fr(psi)} : coefficient d'accompagnement de la charge d'exploitation, RPA 2024 tableau 4.2"
            + (f" ({case.split(' – ')[1]})." if case else "."), "note")
    tr.para("COMBINAISON À L'ÉTAT LIMITE ULTIME :", "sub")
    tr.para("1,35·G + 1,5·Q", "bold")
    tr.para("COMBINAISON À L'ÉTAT LIMITE DE SERVICE :", "sub")
    tr.para("G + Q", "bold")


def charges_tables(tr, rows):
    """rows: dicts Plancher, Désignation, e (m), ρ (kN/m³), Poids (kN/m²), Nature (G/Q)."""
    def num(v):
        try:
            return float(str(v).replace(",", "."))
        except (TypeError, ValueError):
            return None
    groups = {}
    for r in rows:
        if any(str(v).strip() for v in r.values()):
            groups.setdefault(r.get("Plancher") or "Plancher", []).append(r)
    for name, rs in groups.items():
        out = [{"_group": name}]
        G = Q = 0.0
        for r in rs:
            e, rho, w = num(r.get("e (m)")), num(r.get("ρ (kN/m³)")), num(r.get("Poids (kN/m²)"))
            if w is None and e is not None and rho is not None:
                w = e * rho
            w = w or 0.0
            if str(r.get("Nature", "G")).upper().startswith("Q"):
                Q += w
                continue
            G += w
            out.append([r.get("Désignation", ""), f"{fr(e)} m" if e else "", f"{fr(rho)} kN/m³" if rho else "", f"{fr(w)} kN/m²"])
        out.append(["", "", "G", f"{fr(G)} kN/m²"])
        out.append(["", "", "Q", f"{fr(Q)} kN/m²"])
        tr.table(["Désignation des éléments", "e", "Masse volumique", "Poids"], out)
