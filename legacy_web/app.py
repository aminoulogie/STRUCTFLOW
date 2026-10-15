"""Semelles isolées – hangar métallique (RPA 2024 / BAEL 91 mod.99 / CBA 93 / DTR BC 2.331 / EC7).

Lancer :  streamlit run app.py   (ou double-clic sur Lancer.bat)
"""
from __future__ import annotations

import json
import math
from datetime import date

import pandas as pd
import streamlit as st

from engine.combos import DEFAULT_COMBOS, TYPES, ComboDef
from engine.footing import Codes, GroupInput, Options
from engine.importers import UNIT_FACTORS, guess_type, read_reactions
from engine.longrine import LongrineInput
from engine.materials import Materials
from engine.project import Project, build_trace, run
from engine.references import RPA99_ALPHA_TABLE
from engine.report import build_docx
from engine.sketch import draw
from engine.soil import METHODS, Soil

st.set_page_config(page_title="Semelles isolées – Hangar", page_icon="🏗️", layout="wide")

LOAD_COLS = ["Appui", "Groupe", "Cas", "Type", "N", "Vx", "Vy", "Mx", "My"]
GROUP_COLS = ["Groupe", "ap (m)", "bp (m)", "platine a (m)", "platine b (m)", "h0 arase/TN (m)", "Liaison",
              "A (m)", "B (m)", "h (m)", "D (m)"]
COMBO_COLS = ["Nom", "Type", "G", "Q", "S", "W", "E"]
SS = st.session_state


# ---------------------------------------------------------------- state helpers
def init():
    if "loads_base" not in SS:
        SS.loads_base = pd.DataFrame(columns=LOAD_COLS)
    if "combos_base" not in SS:
        SS.combos_base = pd.DataFrame(DEFAULT_COMBOS, columns=COMBO_COLS)
    if "groups_base" not in SS:
        SS.groups_base = pd.DataFrame(columns=GROUP_COLS)
    SS.setdefault("results", None)


def set_base(name, df):
    SS[name + "_base"] = df.reset_index(drop=True)
    SS.pop(name + "_ed", None)


def cur(name):
    return SS.get(name + "_cur", SS[name + "_base"])


def num(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


WIDGET_KEYS = ["meta_ouvrage", "meta_moa", "meta_lieu", "meta_bureau", "meta_ing", "meta_indice",
               "c_rc", "c_bear", "c_seis", "c_ovt", "c_upl",
               "m_fc28", "m_fe", "m_crack", "m_cover", "m_gc", "m_gb", "m_gba", "m_gs", "m_gsa", "m_theta", "m_eta",
               "s_method", "s_D", "s_gr", "s_g", "s_sadm", "s_kelu", "s_kacc", "s_c", "s_phi", "s_pl", "s_kp",
               "s_qc", "s_kc", "s_fsels", "s_fselu",
               "d_ap", "d_bp", "d_pa", "d_pb", "d_h0", "d_base",
               "l_on", "l_site", "l_zone", "l_alpha", "l_b", "l_h", "l_L", "l_q", "l_rho",
               "o_hmin", "o_step", "o_fso", "o_ovt", "o_fsue", "o_fsuu", "o_phi", "o_smin", "o_phimin", "o_rho", "o_sped", "o_homo"]


def project_json():
    data = {k: SS.get(k) for k in WIDGET_KEYS if k in SS}
    for n in ("loads", "combos", "groups"):
        data[n] = cur(n).to_dict(orient="records")
    return json.dumps(data, ensure_ascii=False, indent=1, default=str)


def load_project(raw):
    data = json.loads(raw)
    for n, cols in (("loads", LOAD_COLS), ("combos", COMBO_COLS), ("groups", GROUP_COLS)):
        if n in data:
            set_base(n, pd.DataFrame(data.pop(n), columns=cols))
            SS.pop(n + "_cur", None)
    for k, v in data.items():
        if k in WIDGET_KEYS:
            SS[k] = v
    SS.results = None


init()

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🏗️ Semelles isolées")
    st.caption("Hangar métallique – RPA 2024 · BAEL 91 mod.99 · CBA 93 · DTR BC 2.331 · EC7")
    with st.expander("📁 Projet (ouvrir / enregistrer)", expanded=False):
        up = st.file_uploader("Ouvrir un projet (.json)", type=["json"], key="prj_up")
        if up is not None and SS.get("prj_loaded") != up.name + str(up.size):
            load_project(up.getvalue().decode("utf-8"))
            SS.prj_loaded = up.name + str(up.size)
            st.rerun()
        st.download_button("💾 Enregistrer le projet", project_json(), file_name="projet_semelles.json",
                           mime="application/json", width="stretch")
    st.subheader("Identification")
    st.text_input("Ouvrage", key="meta_ouvrage", placeholder="Hangar de stockage …")
    st.text_input("Maître d'ouvrage", key="meta_moa")
    st.text_input("Localisation", key="meta_lieu")
    st.text_input("Bureau d'études", key="meta_bureau")
    st.text_input("Ingénieur", key="meta_ing")
    st.text_input("Indice", key="meta_indice", value="A")
    st.subheader("Règlement par vérification")
    st.selectbox("Béton armé / ferraillage", ["BAEL 91 mod.99", "CBA 93"], key="c_rc")
    st.selectbox("Portance du sol", ["DTR BC 2.331", "Eurocode 7 (DA2)"], key="c_bear",
                 help="EC7 : ELU/ACC par la formule de l'annexe D (surface effective) – nécessite un sol défini par c, φ.")
    st.selectbox("Parasismique (combinaisons, renversement, longrines)", ["RPA 2024", "RPA 99/2003"], key="c_seis")
    st.selectbox("Renversement", ["RPA + classique", "RPA seul"], key="c_ovt",
                 help="RPA : e = M/N ≤ B/4 sous combinaisons accidentelles. Classique : Fs = Mstab/Mrenv ≥ 1,5.")
    st.selectbox("Soulèvement", ["Classique", "Eurocode 7 (UPL)"], key="c_upl",
                 help="Classique : Fs = W/T. EC7 UPL : 0,9·G + 1,5·W, Fs ≥ 1.")

tabs = st.tabs(["① Matériaux", "② Sol", "③ Combinaisons", "④ Efforts", "⑤ Semelles", "⑥ Longrines", "⑦ Calcul & note"])

# ---------------------------------------------------------------- 1. materials
with tabs[0]:
    st.subheader("Matériaux (BAEL 91 mod.99 / CBA 93)")
    c1, c2, c3 = st.columns(3)
    c1.number_input("fc28 (MPa)", min_value=10.0, max_value=60.0, value=None, step=1.0, key="m_fc28")
    c2.number_input("fe (MPa)", min_value=215.0, max_value=600.0, value=None, step=10.0, key="m_fe")
    c3.selectbox("Fissuration", ["FPP", "FP", "FTP"], index=None, key="m_crack",
                 format_func=lambda x: dict(FPP="Peu préjudiciable (FPP)", FP="Préjudiciable (FP)",
                                            FTP="Très préjudiciable (FTP)")[x])
    c1.number_input("Enrobage c (cm)", min_value=1.0, max_value=10.0, value=None, step=0.5, key="m_cover")
    c2.number_input("γc béton (kN/m³)", value=25.0, step=0.5, key="m_gc")
    with st.expander("Coefficients de sécurité (valeurs réglementaires)"):
        k1, k2, k3, k4 = st.columns(4)
        k1.number_input("γb durable", value=1.5, key="m_gb")
        k2.number_input("γb accidentel", value=1.15, key="m_gba")
        k3.number_input("γs durable", value=1.15, key="m_gs")
        k4.number_input("γs accidentel", value=1.0, key="m_gsa")
        k1.number_input("θ", value=1.0, key="m_theta")
        k2.number_input("η (HA = 1,6)", value=1.6, key="m_eta")

# ---------------------------------------------------------------- 2. soil
with tabs[1]:
    st.subheader("Sol de fondation (DTR BC 2.331)")
    st.radio("Méthode de détermination de la portance", list(METHODS), format_func=METHODS.get, key="s_method",
             horizontal=True)
    c1, c2, c3 = st.columns(3)
    c1.number_input("Profondeur d'ancrage D (m) – TN → sous-face semelle", min_value=0.3, value=None, step=0.1, key="s_D")
    c2.number_input("γ remblai (kN/m³)", min_value=10.0, value=None, step=0.5, key="s_gr")
    meth = SS.get("s_method", "adm")
    if meth == "adm":
        c1.number_input("σadm (bar)", min_value=0.1, value=None, step=0.1, key="s_sadm")
        c2.number_input("k_ELU : q_ELU = k·σadm", value=1.5, step=0.1, key="s_kelu",
                        help="Rapport ELU/ELS ≈ Fs,ELS/Fs,ELU = 3/2. À adapter selon le rapport de sol.")
        c3.number_input("k_ACC : q_ACC = k·σadm", value=1.5, step=0.1, key="s_kacc")
    else:
        if meth == "cphi":
            c1.number_input("Cohésion c (kPa)  [cu si φ = 0]", min_value=0.0, value=None, key="s_c")
            c2.number_input("Angle φ (°)", min_value=0.0, max_value=45.0, value=None, key="s_phi")
            c3.number_input("γ sol sous semelle (kN/m³)", min_value=10.0, value=None, key="s_g")
        elif meth == "pressio":
            c1.number_input("ple* (MPa)", min_value=0.0, value=None, step=0.1, key="s_pl")
            c2.number_input("kp", min_value=0.0, value=None, step=0.05, key="s_kp",
                            help="Fascicule 62 / DTR : argiles 0,8–1,1 ; sables 1,0–1,5 ; craies 1,3–1,8 ; roches 1,8–2,6 (selon De/B).")
        else:
            c1.number_input("qce (MPa)", min_value=0.0, value=None, step=0.5, key="s_qc")
            c2.number_input("kc", min_value=0.0, value=None, step=0.01, key="s_kc",
                            help="Fascicule 62 / DTR : argiles 0,32 ; sables 0,14–0,15 ; craies 0,17–0,26.")
        k1, k2 = st.columns(2)
        k1.number_input("Fs ELS", value=3.0, key="s_fsels")
        k2.number_input("Fs ELU / ACC", value=2.0, key="s_fselu")

# ---------------------------------------------------------------- 3. combinations
with tabs[2]:
    st.subheader("Combinaisons d'actions")
    st.caption("Coefficients appliqués aux cas élémentaires. W : chaque cas de vent est pris séparément ; "
               "E : chaque cas sismique est pris avec ±. Les résultats importés déjà combinés (types ELU/ELS/ACC) "
               "sont utilisés tels quels.")
    if st.button("↺ Réinitialiser les combinaisons par défaut"):
        set_base("combos", pd.DataFrame(DEFAULT_COMBOS, columns=COMBO_COLS))
    SS.combos_cur = st.data_editor(
        SS.combos_base, key="combos_ed", num_rows="dynamic", width="stretch",
        column_config={"Type": st.column_config.SelectboxColumn(options=["ELU", "ELS", "ACC"], required=True),
                       **{k: st.column_config.NumberColumn(format="%.2f") for k in "GQSWE"}})

# ---------------------------------------------------------------- 4. loads
with tabs[3]:
    st.subheader("Efforts en pied de poteau")
    with st.expander("📥 Importer depuis ETABS / Robot", expanded=cur("loads").empty):
        st.markdown(
            "- **ETABS** : *Display › Show Tables › Analysis Results › Joint Output › Reactions › Joint Reactions* "
            "→ *File › Export to Excel*.\n"
            "- **Robot** : *Résultats › Réactions* → clic droit dans le tableau → *Exporter vers Excel* "
            "(cas simples de préférence : G, Q, S, W…, Ex, Ey).\n"
            "- Les colonnes FX, FY, FZ, MX, MY et appui/cas sont détectées automatiquement.")
        f = st.file_uploader("Fichier Excel / CSV", type=["xlsx", "xls", "csv", "txt"], key="imp_file")
        c1, c2, c3 = st.columns(3)
        units = c1.selectbox("Unités du fichier", list(UNIT_FACTORS), key="imp_units")
        reac = c2.checkbox("Les valeurs sont des RÉACTIONS d'appui (cas ETABS/Robot)", value=True, key="imp_reac",
                           help="Réaction → action sur la semelle : N = FZ, Vx = −FX, Vy = −FY, Mx = −MX, My = −MY.")
        mode = c3.radio("Mode", ["Remplacer", "Ajouter"], horizontal=True, key="imp_mode")
        if f is not None and st.button("Importer", type="primary"):
            try:
                df, info = read_reactions(f, f.name, units, reac)
                if mode == "Ajouter":
                    df = pd.concat([cur("loads"), df], ignore_index=True)
                set_base("loads", df[LOAD_COLS])
                SS.pop("loads_cur", None)
                st.success(info)
            except Exception as e:  # noqa: BLE001
                st.error(f"Import impossible : {e}")

    loads = cur("loads")
    if not loads.empty:
        with st.expander("🏷️ Type des cas de charge (vérifier l'affectation automatique)", expanded=True):
            cases = pd.DataFrame({"Cas": sorted(loads["Cas"].astype(str).unique())})
            first = loads.drop_duplicates("Cas").set_index("Cas")["Type"]
            cases["Type"] = [first.get(c, guess_type(c)) for c in cases["Cas"]]
            ed = st.data_editor(cases, key=f"cases_ed_{len(cases)}", width="stretch", hide_index=True,
                                column_config={"Cas": st.column_config.TextColumn(disabled=True),
                                               "Type": st.column_config.SelectboxColumn(options=TYPES, required=True)})
            if st.button("Appliquer les types"):
                mp = dict(zip(ed["Cas"], ed["Type"]))
                df = loads.copy()
                df["Type"] = df["Cas"].astype(str).map(mp).fillna(df["Type"])
                set_base("loads", df)
                SS.pop("loads_cur", None)
                st.rerun()
        with st.expander("🧩 Regrouper des appuis dans une même semelle type"):
            c1, c2, c3 = st.columns([3, 1, 1])
            sel = c1.multiselect("Appuis", sorted(loads["Appui"].astype(str).unique()), key="grp_sel")
            name = c2.text_input("Nom de la semelle", value="S1", key="grp_name")
            if c3.button("Affecter") and sel:
                df = loads.copy()
                df.loc[df["Appui"].astype(str).isin(sel), "Groupe"] = name
                set_base("loads", df)
                SS.pop("loads_cur", None)
                st.rerun()
    st.caption("Saisie manuelle possible : ajoutez des lignes (un cas élémentaire ou une combinaison par ligne). "
               "Unités : kN, kN·m. N > 0 = compression. Toutes les lignes d'un même « Groupe » sont dimensionnées "
               "ensemble (enveloppe).")
    SS.loads_cur = st.data_editor(
        SS.loads_base, key="loads_ed", num_rows="dynamic", width="stretch", height=420,
        column_config={"Type": st.column_config.SelectboxColumn(options=TYPES, required=True),
                       "Appui": st.column_config.TextColumn(required=True),
                       "Groupe": st.column_config.TextColumn(required=True),
                       **{k: st.column_config.NumberColumn(format="%.2f") for k in ("N", "Vx", "Vy", "Mx", "My")}})

# ---------------------------------------------------------------- 5. footing groups
with tabs[4]:
    st.subheader("Semelles types – fût et géométrie")
    st.caption("Valeurs par défaut appliquées aux nouvelles semelles :")
    c = st.columns(6)
    c[0].number_input("ap fût (m)", value=None, min_value=0.2, step=0.05, key="d_ap")
    c[1].number_input("bp fût (m)", value=None, min_value=0.2, step=0.05, key="d_bp")
    c[2].number_input("platine a (m)", value=None, min_value=0.0, step=0.05, key="d_pa")
    c[3].number_input("platine b (m)", value=None, min_value=0.0, step=0.05, key="d_pb")
    c[4].number_input("h0 arase / TN (m)", value=None, step=0.05, key="d_h0")
    c[5].selectbox("Liaison", ["Encastré", "Articulé"], key="d_base")
    groups = cur("groups")
    want = [g for g in pd.unique(cur("loads")["Groupe"].dropna().astype(str)) if g]
    have = list(groups["Groupe"].astype(str)) if not groups.empty else []
    if set(want) != set(have) or st.button("Appliquer les valeurs par défaut à toutes les semelles"):
        force = set(want) == set(have)
        rows = []
        for g in want:
            old = groups[groups["Groupe"].astype(str) == g]
            if len(old) and not force:
                rows.append(old.iloc[0].to_dict())
            else:
                keep = old.iloc[0].to_dict() if len(old) else {}
                rows.append({"Groupe": g, "ap (m)": SS.d_ap, "bp (m)": SS.d_bp, "platine a (m)": SS.d_pa,
                             "platine b (m)": SS.d_pb, "h0 arase/TN (m)": SS.d_h0, "Liaison": SS.d_base,
                             "A (m)": keep.get("A (m)"), "B (m)": keep.get("B (m)"), "h (m)": keep.get("h (m)"),
                             "D (m)": keep.get("D (m)")})
        set_base("groups", pd.DataFrame(rows, columns=GROUP_COLS))
        SS.pop("groups_cur", None)
    st.caption("A, B, h vides → dimensionnement automatique (pas de 5 cm). Renseignés → vérification des dimensions "
               "imposées. D vide → profondeur du sol (onglet ②).")
    SS.groups_cur = st.data_editor(
        SS.groups_base, key="groups_ed", width="stretch", hide_index=True,
        column_config={"Groupe": st.column_config.TextColumn(disabled=True),
                       "Liaison": st.column_config.SelectboxColumn(options=["Encastré", "Articulé"], required=True)})

# ---------------------------------------------------------------- 6. tie beams
with tabs[5]:
    st.subheader("Longrines (RPA)")
    st.checkbox("Calculer les longrines", value=True, key="l_on")
    c1, c2, c3 = st.columns(3)
    site = c1.selectbox("Site", list(RPA99_ALPHA_TABLE), index=2, key="l_site")
    zone = c2.selectbox("Zone sismique (table RPA 99/2003)", ["I", "II", "III"], index=1, key="l_zone")
    sug = RPA99_ALPHA_TABLE[site][zone]
    c3.info(f"α suggéré (RPA 99/2003) : {sug if sug else '— (non exigé)'}\n\n"
            "Vérifier la valeur dans le tableau RPA 2024.")
    c1.number_input("α retenu", min_value=1.0, value=None, step=1.0, key="l_alpha")
    c2.number_input("b (m)", min_value=0.2, value=None, step=0.05, key="l_b")
    c3.number_input("h (m)", min_value=0.2, value=None, step=0.05, key="l_h")
    c1.number_input("Portée L (m) pour flexion sous poids propre (0 = ignorer)", min_value=0.0, value=0.0, key="l_L")
    c2.number_input("Charge additionnelle (kN/m) – mur, dallage…", min_value=0.0, value=0.0, key="l_q")
    c3.number_input("ρmin (%)", value=0.6, key="l_rho")

# ---------------------------------------------------------------- 7. calculation
with tabs[6]:
    st.subheader("Options de calcul")
    c = st.columns(4)
    c[0].number_input("h minimale semelle (m)", value=0.40, step=0.05, key="o_hmin")
    c[1].number_input("Pas d'arrondi (m)", value=0.05, step=0.05, key="o_step")
    c[2].number_input("Fs renversement", value=1.5, key="o_fso")
    c[3].multiselect("Fs renversement appliqué aux", ["ELS", "ELU"], default=["ELS", "ELU"], key="o_ovt")
    c[0].number_input("Fs soulèvement ELS", value=1.5, key="o_fsue")
    c[1].number_input("Fs soulèvement ELU/ACC", value=1.0, key="o_fsuu")
    c[2].number_input("φ supposé pour d (mm)", value=14, step=2, key="o_phi")
    c[3].number_input("Espacement minimal barres (cm)", value=10, key="o_smin")
    c[0].selectbox("φ minimal semelle (mm)", [10, 12, 14, 16], index=1, key="o_phimin")
    c[1].number_input("ρmin fût (%) – RPA", value=0.9, step=0.1, key="o_rho",
                      help="RPA 99/2003 : 0,7 % zone I ; 0,8 % zone IIa ; 0,9 % zones IIb et III. À confirmer RPA 2024.")
    c[2].number_input("Espacement max barres fût (cm)", value=25, key="o_sped")
    c[3].checkbox("Semelle homothétique au fût (A/B = ap/bp)", value=True, key="o_homo")

    def validate():
        errs = []
        need = dict(m_fc28="fc28", m_fe="fe", m_crack="fissuration", m_cover="enrobage", s_D="profondeur D",
                    s_gr="γ remblai")
        meth = SS.get("s_method", "adm")
        need.update(dict(adm=dict(s_sadm="σadm"), cphi=dict(s_c="c", s_phi="φ", s_g="γ sol"),
                         pressio=dict(s_pl="ple*", s_kp="kp"), penetro=dict(s_qc="qce", s_kc="kc"))[meth])
        if SS.get("l_on"):
            need.update(l_alpha="α longrine", l_b="b longrine", l_h="h longrine")
        errs += [f"{lab} non renseigné" for k, lab in need.items() if SS.get(k) in (None, "")]
        L = cur("loads")
        if L.empty:
            errs.append("Aucun effort saisi (onglet ④).")
        G = cur("groups")
        for _, r in G.iterrows():
            for col in ("ap (m)", "bp (m)", "h0 arase/TN (m)"):
                if num(r[col]) is None:
                    errs.append(f"Semelle {r['Groupe']} : « {col} » non renseigné (onglet ⑤).")
        return errs

    def build_project():
        mat = Materials(SS.m_fc28, SS.m_fe, SS.m_crack, SS.m_cover / 100, SS.m_gc, SS.m_gb, SS.m_gba, SS.m_gs,
                        SS.m_gsa, SS.m_theta, SS.m_eta, code=SS.c_rc)
        meth = SS.s_method
        soil = Soil(meth, SS.s_D, SS.s_gr, gamma=SS.get("s_g") or 18.0,
                    sigma_adm=(SS.get("s_sadm") or 0) * 100, k_elu=SS.get("s_kelu", 1.5), k_acc=SS.get("s_kacc", 1.5),
                    c=SS.get("s_c") or 0.0, phi=SS.get("s_phi") or 0.0, pl=(SS.get("s_pl") or 0) * 1000,
                    kp=SS.get("s_kp") or 0.0, qc=(SS.get("s_qc") or 0) * 1000, kc=SS.get("s_kc") or 0.0,
                    fs_els=SS.get("s_fsels", 3.0), fs_elu=SS.get("s_fselu", 2.0))
        codes = Codes(SS.c_rc, SS.c_bear, SS.c_seis, SS.c_ovt, SS.c_upl)
        opts = Options(h_min=SS.o_hmin, step=SS.o_step, fs_overturn=SS.o_fso, ovt_types=tuple(SS.o_ovt),
                       fs_uplift_els=SS.o_fsue, fs_uplift_elu=SS.o_fsuu, phi_assumed=SS.o_phi / 1000,
                       s_min=SS.o_smin / 100, phi_min=SS.o_phimin, rho_min_ped=SS.o_rho, s_max_ped=SS.o_sped / 100,
                       homothetic=SS.o_homo)
        defs = [ComboDef(str(r["Nom"]), r["Type"], *(num(r[k]) or 0.0 for k in "GQSWE"))
                for _, r in cur("combos").iterrows() if r["Type"] in ("ELU", "ELS", "ACC")]
        loads = []
        for _, r in cur("loads").iterrows():
            if pd.isna(r["Appui"]) or pd.isna(r["Type"]):
                continue
            loads.append(dict(Appui=str(r["Appui"]), Groupe=str(r["Groupe"] if not pd.isna(r["Groupe"]) else r["Appui"]),
                              Cas=str(r["Cas"]), Type=r["Type"], **{k: num(r[k]) or 0.0 for k in ("N", "Vx", "Vy", "Mx", "My")}))
        groups = [GroupInput(str(r["Groupe"]), num(r["ap (m)"]), num(r["bp (m)"]), num(r["platine a (m)"]) or 0.0,
                             num(r["platine b (m)"]) or 0.0, num(r["h0 arase/TN (m)"]), r["Liaison"] or "Encastré",
                             num(r["A (m)"]), num(r["B (m)"]), num(r["h (m)"]), num(r["D (m)"]))
                  for _, r in cur("groups").iterrows()]
        lg = None
        if SS.get("l_on"):
            smin = (0.30, 0.30) if SS.l_site == "S4" else (0.25, 0.30)
            lg = LongrineInput(SS.l_alpha, SS.l_b, SS.l_h, SS.l_L, SS.l_q, SS.l_rho, *smin)
        meta = dict(ouvrage=SS.meta_ouvrage, moa=SS.meta_moa, lieu=SS.meta_lieu, bureau=SS.meta_bureau,
                    ingenieur=SS.meta_ing, indice=SS.meta_indice, date=date.today().strftime("%d/%m/%Y"))
        return Project(meta, mat, soil, codes, opts, defs, loads, groups, lg)

    st.divider()
    if st.button("▶ Calculer", type="primary", width="stretch"):
        errs = validate()
        if errs:
            st.error("Données manquantes :\n\n- " + "\n- ".join(errs))
        else:
            try:
                prj = build_project()
                with st.spinner("Calcul en cours…"):
                    run(prj)
                SS.results = prj
                SS.docx = None
            except Exception as e:  # noqa: BLE001
                st.exception(e)

    prj = SS.get("results")
    if prj:
        rows = []
        for r in prj.results:
            g, rc = r.geo, r.rc
            ratio = lambda k: max([x["ratio"] for x in r.ev[k]] or [0])  # noqa: E731
            rows.append({"Semelle": r.gi.name, "Appuis": ", ".join(r.gi.joints), "A (m)": g.A, "B (m)": g.B,
                         "h (m)": g.h, "Portance": f"{ratio('bear') * 100:.0f} %",
                         "Renversement": f"{ratio('ovt') * 100:.0f} %",
                         "Soulèvement": f"{ratio('upl') * 100:.0f} %" if r.ev["upl"] else "—",
                         "// A": f"{rc['X']['bars']['n']} HA{rc['X']['bars']['phi']} e={rc['X']['bars']['s'] * 100:.0f}",
                         "// B": f"{rc['Y']['bars']['n']} HA{rc['Y']['bars']['phi']} e={rc['Y']['bars']['s'] * 100:.0f}",
                         "Nappe sup.": "oui" if (rc["X"]["bars_top"] or rc["Y"]["bars_top"]) else "—",
                         "Fût": f"{r.ped['bars']['n']} HA{r.ped['bars']['phi']}",
                         "Statut": "✅ OK" if r.ok else "❌ NON OK"})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        if prj.lg:
            lr = prj.lg["res"]
            st.info(f"Longrines {prj.longrine.b * 100:.0f}×{prj.longrine.h * 100:.0f} : F = {lr['F']:.1f} kN → "
                    f"{lr['bars']['n']} HA{lr['bars']['phi']}, cadres HA{lr['phit']} e = {lr['st'] * 100:.0f} cm")
        for r in prj.results:
            with st.expander(f"Semelle {r.gi.name} – détails"):
                for m in r.msgs:
                    st.warning(m)
                st.image(draw(r, prj.mat.cover))
                c1, c2 = st.columns(2)
                c1.markdown("**Portance (combinaison la plus sollicitée par type)**")
                for t in ("ELS", "ELU", "ACC"):
                    rr = [x for x in r.ev["bear"] if x["type"] == t]
                    if rr:
                        x = max(rr, key=lambda x: x["ratio"])
                        c1.write(f"{t} : {x['combo']} (appui {x['joint']}) — σ₃/₄ = {x['s34']:.1f} / q = "
                                 f"{(x['q'] or 0):.1f} → {x['ratio'] * 100:.0f} %")
                c2.markdown("**Ferraillage**")
                for k, lab in (("X", "A"), ("Y", "B")):
                    rc = r.rc[k]
                    c2.write(f"// {lab} : As = {rc['As_req']:.2f} cm² ({rc['governs']}) → {rc['bars']['n']} HA"
                             f"{rc['bars']['phi']} e = {rc['bars']['s'] * 100:.0f} cm"
                             + (f" ; nappe sup. {rc['bars_top']['n']} HA{rc['bars_top']['phi']}" if rc["bars_top"] else ""))
        st.divider()
        if st.button("📝 Générer la note de calcul Word", width="stretch"):
            with st.spinner("Rédaction de la note…"):
                SS.docx = build_docx(build_trace(prj), prj.meta)
        if SS.get("docx"):
            st.download_button("⬇️ Télécharger la note de calcul (.docx)", SS.docx, type="primary",
                               file_name=f"Note_calcul_semelles_{date.today():%Y%m%d}.docx",
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                               width="stretch")
