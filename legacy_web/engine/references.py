"""Code article references printed in the note de calcul.

Edit freely: these strings are only used for display. References marked
"(à confirmer)" relate to RPA 2024, whose article numbering should be checked
against the official text; the RPA 99/2003 article given in brackets is the
equivalent clause of the previous version.
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
    # --- Parasismique ---
    "rpa_combo": "RPA 2024 – combinaisons pour fondations G+Q±E ; 0,8G±E (à confirmer) "
                 "[RPA 99/2003 art. 10.1.4.1]",
    "rpa_renv": "RPA 2024 – stabilité au renversement e = M/N ≤ B/4 (à confirmer) "
                "[RPA 99/2003 art. 10.1.5]",
    "rpa_longrine": "RPA 2024 – longrines (à confirmer) [RPA 99/2003 art. 10.1.1]",
    "rpa_poteau_min": "RPA 2024 – armatures minimales des poteaux (à confirmer) "
                      "[RPA 99/2003 art. 7.4.2.1]",
    "renv_classique": "Stabilité au renversement – Fs = Mstab/Mrenv ≥ 1,5 (pratique DTR BC 2.331)",
    "soulevement": "Stabilité au soulèvement – Fs = Wstab/Tsoul",
}

RPA99_ALPHA_TABLE = {
    # site: {zone: alpha}   (RPA 99/2003 tableau 10.1 – valeur de α pour les longrines)
    "S1": {"I": None, "II": None, "III": None},
    "S2": {"I": None, "II": 15, "III": 12},
    "S3": {"I": 15, "II": 12, "III": 10},
    "S4": {"I": 12, "II": 10, "III": 8},
}


def ref(key):
    return REFS.get(key, key)
