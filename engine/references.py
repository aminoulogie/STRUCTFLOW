"""Code article references printed in the note de calcul.

Edit freely: these strings are only used for display. RPA 2024 references were checked
against the official text (DTR B-C 2.48, version finale).
"""

REFS = {
    # --- Béton armé (BAEL 91 mod.99 / CBA 93) ---
    "ft28": "BAEL 91 mod.99 A.2.1.12 / CBA 93 A.2.1.1.2",
    "fbu": "BAEL 91 mod.99 A.4.3.41 / CBA 93 A.4.3.4.1",
    "sigma_s": "BAEL 91 mod.99 A.4.3.2 / CBA 93 A.4.3.2",
    "sigma_bc": "BAEL 91 mod.99 A.4.5.2 / CBA 93 A.4.5.2",
    "sigma_s_bar_mod99": "BAEL 91 mod.99 A.4.5.33 (FP) / A.4.5.34 (FTP)",
    "sigma_s_bar_cba": "CBA 93 A.4.5.3.3 (FP) / A.4.5.3.4 (FTP)",
    "mu_l": "BAEL 91 mod.99 A.4.3.3 – pivot A/B, μl",
    "flexion": "BAEL 91 mod.99 A.4.3 – flexion simple ELU",
    "flexion_els": "BAEL 91 mod.99 A.4.5 – vérification / dimensionnement ELS",
    "non_frag": "BAEL 91 mod.99 A.4.2.1 / CBA 93 A.4.2.1 – condition de non-fragilité",
    "tau_s": "BAEL 91 mod.99 A.6.1.21 / CBA 93 A.6.1.2.1",
    "ls": "BAEL 91 mod.99 A.6.1.22 / CBA 93 A.6.1.2.2 – longueur de scellement droit",
    "anc_semelle": "DTU 13.12 §3.2 / DTR BC 2.331 – ancrage des armatures de semelles",
    "punch": "BAEL 91 mod.99 A.5.2.4 / CBA 93 A.5.2.4 – poinçonnement",
    "tau_u": "BAEL 91 mod.99 A.5.2.2 – dalles/semelles sans armatures d'effort tranchant",
    "espacement": "BAEL 91 mod.99 A.4.5.33-34 / A.8.2.42 – espacement maximal des barres",
    "bielles": "DTU 13.12 §3.2 / DTR BC 2.331 – méthode des bielles (semelle rigide)",
    "bielles_exc": "DTU 13.12 – méthode des bielles avec excentricité : N' = N(1 + 3e₀/B), e₀ ≤ B/6",
    "moment_S1": "DTU 13.12 / BAEL – méthode des moments, section S1 à 0,35·b de l'axe du poteau",
    "rigidite": "DTU 13.12 / DTR BC 2.331 – semelle rigide : (B − b)/4 ≤ d ≤ (B − b)",
    "combo_elu": "BAEL 91 mod.99 A.3.3.2 / CCM 97 §2.3 – combinaisons fondamentales",
    "combo_els": "BAEL 91 mod.99 A.3.3.3 / CCM 97 – combinaisons de service",
    # --- Sol / fondations ---
    "dtr_portance": "DTR BC 2.331 – Règles de calcul des fondations superficielles",
    "dtr_trapeze": "DTR BC 2.331 – diagramme trapézoïdal : σ₃/₄ = (3σmax + σmin)/4 ≤ q",
    "dtr_cphi": "DTR BC 2.331 – formule de Terzaghi généralisée (facteurs de forme)",
    "dtr_pressio": "DTR BC 2.331 / Fascicule 62-V – méthode pressiométrique : ql = q₀ + kp·ple*",
    "dtr_penetro": "DTR BC 2.331 / Fascicule 62-V – méthode pénétrométrique : ql = q₀ + kc·qce",
    "ec7_bearing": "EN 1997-1 §6.5.2 et Annexe D – capacité portante (approche 2)",
    "ec7_upl": "EN 1997-1 §2.4.7.4 – état limite UPL (γG,stb = 0,9 ; γQ,dst = 1,5)",
    # --- Parasismique : RPA 2024 (DTR B-C 2.48) ---
    "rpa_combo": "RPA 2024 §5.7 éq. (5.6) et §5.2 éq. (5.1)-(5.2) – fondations d'éléments verticaux individuels : "
                 "G + ψQ ± (R/Q_F)·E1 ; G + ψQ ± (R/Q_F)·E2 avec E1 = Ex ± 0,3Ey, E2 = 0,3Ex ± Ey "
                 "(fondations communes : ± 1,4E, éq. (5.7)) ; ψ : tableau 4.2",
    "rpa_renv": "RPA 2024 §4.5.1 et §5.5 – stabilité au renversement : Fs = Ms/Mr ≥ 1,3, moment stabilisant "
                "calculé au niveau bas de la fondation par rapport au bord extrême (poids construction + fondation + sol)",
    "rpa_longrine": "RPA 2024 §10.1.1 – solidarisation des points d'appui (longrines)",
    "rpa_longrine_F": "RPA 2024 §10.1.1, éq. (10.1)-(10.2) – F = ±α·(A·I·S)·N ≥ 20 kN ; α = 0,3 (S2) / 0,4 (S3) / 0,6 (S4)",
    "rpa_portance": "RPA 2024 §10.1.4 – coefficient de sécurité global 2,0 sur la contrainte de rupture Ql "
                    "sous combinaisons sismiques (cf. DTR BC 2.33)",
    "rpa_glissement": "RPA 2024 §5.5 et §10.1.5 – résistance au glissement : coefficient de sécurité global 1,25 (cf. DTR BC 2.33)",
    "dtr_glissement": "DTR BC 2.33.1 – glissement : H ≤ (N·tanφ' + c'·A')/Fs",
    "rpa_gamma": "RPA 2024 §7.3.2 – situation sismique : γb = 1,20 ; γs = 1,00",
    "rpa_materiaux": "RPA 2024 §7.2 – béton ≥ C20/25 (hors zone 0) ; acier HA 400 ≤ fe ≤ 600 MPa",
    "rpa_poteau_min": "RPA 2024 §7.4 – poteaux : ρmin = 0,8 % (zones I-II), 0,9 % (III), 1,0 % (IV-VI) ; "
                      "φ ≥ 12 mm ; espacement ≤ 20 cm (I-III) / 15 cm (IV-VI) ; une barre intermédiaire par face",
    "renv_classique": "Stabilité au renversement sous charges de service et ultimes (vent) – Fs = Mstab/Mrenv ≥ 1,5 (règle de l'art)",
    "soulevement": "Stabilité au soulèvement (vent) – Fs = Wstab/Tsoul : poids stabilisant / traction (règle de l'art)",
}

RPA2024_ALPHA = {"S1": None, "S2": 0.3, "S3": 0.4, "S4": 0.6}          # éq. (10.2)
RPA2024_LONGRINE_MIN = {"S1": (0.25, 0.30), "S2": (0.25, 0.30), "S3": (0.25, 0.30), "S4": (0.30, 0.30)}
RPA2024_ZONES = ["0", "I", "II", "III", "IV", "V", "VI"]
RPA2024_GROUPS = ["1A", "1B", "2", "3"]
# RPA 2024 chapter III (checked against the official text)
RPA2024_A = {"0": 0.00, "I": 0.07, "II": 0.10, "III": 0.15, "IV": 0.20, "V": 0.25, "VI": 0.30}      # tableau 3.3
RPA2024_I = {"1A": 1.40, "1B": 1.20, "2": 1.00, "3": 0.80}                                          # tableau 3.11
RPA2024_S_LOW = {"S1": 1.00, "S2": 1.30, "S3": 1.55, "S4": 1.80}    # zones I-III, spectre type 2 (tableau 3.5)
RPA2024_S_HIGH = {"S1": 1.00, "S2": 1.20, "S3": 1.30, "S4": 1.35}   # zones IV-VI, spectre type 1 (tableau 3.4)


def seismic_coeffs(zone, site, group):
    """Return (A, I, S) for a zone / site / importance group."""
    S = (RPA2024_S_LOW if zone in ("I", "II", "III") else RPA2024_S_HIGH).get(site)
    return RPA2024_A.get(zone), RPA2024_I.get(group), S
RPA2024_RHO_POTEAU = {"0": 0.8, "I": 0.8, "II": 0.8, "III": 0.9, "IV": 1.0, "V": 1.0, "VI": 1.0}   # %
RPA2024_S_POTEAU = {"0": 0.20, "I": 0.20, "II": 0.20, "III": 0.20, "IV": 0.15, "V": 0.15, "VI": 0.15}  # m


def longrine_required(site, zone):
    """RPA 2024 §10.1.1 c) – not required on S1 (rock) nor on S2 in zone I."""
    return not (site == "S1" or (site == "S2" and zone in ("0", "I")))


def ref(key):
    return REFS.get(key, key)
