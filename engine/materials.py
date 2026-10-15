"""Materials: BAEL 91 mod.99 / CBA 93."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .references import ref
from .trace import Trace, fmt

ES = 200000.0  # MPa


@dataclass
class Materials:
    fc28: float            # MPa
    fe: float              # MPa
    cracking: str          # "FPP" | "FP" | "FTP"
    cover: float           # m
    gamma_c: float = 25.0  # kN/m3
    gamma_b: float = 1.5
    gamma_b_acc: float = 1.20   # RPA 2024 §7.3.2
    gamma_s: float = 1.15
    gamma_s_acc: float = 1.0
    theta: float = 1.0
    eta: float = 1.6
    psi_s: float = 1.5
    code: str = "BAEL 91 mod.99"   # or "CBA 93"

    @property
    def ft28(self):
        return 0.6 + 0.06 * self.fc28

    def gb(self, acc=False):
        return self.gamma_b_acc if acc else self.gamma_b

    def gs(self, acc=False):
        return self.gamma_s_acc if acc else self.gamma_s

    def fbu(self, acc=False):
        return 0.85 * self.fc28 / (self.theta * self.gb(acc))

    def sigma_s(self, acc=False):
        """ELU steel stress, MPa."""
        return self.fe / self.gs(acc)

    @property
    def sigma_bc_bar(self):
        return 0.6 * self.fc28

    @property
    def is_cba(self):
        return self.code.upper().startswith("CBA")

    @property
    def sigma_s_bar(self):
        """ELS steel stress limit (MPa); None when cracking is not harmful (FPP)."""
        ft, fe, eta = self.ft28, self.fe, self.eta
        if self.cracking == "FPP":
            return None
        if self.is_cba:
            if self.cracking == "FP":
                return min(2 / 3 * fe, 110 * math.sqrt(eta * ft))
            return min(0.5 * fe, 90 * math.sqrt(eta * ft))
        xi = min(2 / 3 * fe, max(0.5 * fe, 110 * math.sqrt(eta * ft)))
        return xi if self.cracking == "FP" else 0.8 * xi

    def mu_l(self, acc=False):
        eps = self.sigma_s(acc) / ES
        al = 3.5 / (3.5 + 1000 * eps)
        return 0.8 * al * (1 - 0.4 * al)

    @property
    def tau_s(self):
        return 0.6 * self.psi_s ** 2 * self.ft28

    def ls(self, phi_m):
        return phi_m * self.fe / (4 * self.tau_s)

    def s_max(self, h):
        """Maximum bar spacing (m) by cracking class."""
        if self.cracking == "FTP":
            return min(1.5 * h, 0.20)
        if self.cracking == "FP":
            return min(2 * h, 0.25)
        return min(3 * h, 0.33)

    # ------------------------------------------------------------------ report
    def warnings(self, zone="III"):
        w = []
        if self.fc28 < 20 and zone != "0":
            w.append("RPA 2024 §7.2 : béton de classe inférieure à C20/25 interdit hors zone 0.")
        if not 400 <= self.fe <= 600:
            w.append("RPA 2024 §7.2 : armatures HA avec 400 ≤ fe ≤ 600 MPa exigées.")
        return w

    def describe(self, tr: Trace):
        tr.para(f"Règlement béton armé retenu : {self.code}. "
                f"Fissuration : {dict(FPP='peu préjudiciable', FP='préjudiciable', FTP='très préjudiciable')[self.cracking]} "
                f"({self.cracking}). Enrobage c = {fmt(self.cover * 100, 1)} cm. "
                f"Poids volumique du béton γc = {fmt(self.gamma_c, 1)} kN/m³.")
        tr.step("Résistance caractéristique du béton à 28 jours", "fc28", "", f"{fmt(self.fc28, 1)} MPa")
        tr.step("Résistance à la traction", "ft28 = 0,6 + 0,06·fc28",
                f"0,6 + 0,06 × {fmt(self.fc28, 1)}", f"{fmt(self.ft28)} MPa", ref("ft28"))
        tr.step("Résistance de calcul du béton (situation durable)", "fbu = 0,85·fc28 / (θ·γb)",
                f"0,85 × {fmt(self.fc28, 1)} / ({fmt(self.theta, 2)} × {fmt(self.gamma_b, 2)})",
                f"{fmt(self.fbu())} MPa", ref("fbu"))
        tr.step("Résistance de calcul du béton (situation sismique)", "fbu,acc = 0,85·fc28 / (θ·γb,acc)",
                f"0,85 × {fmt(self.fc28, 1)} / ({fmt(self.theta, 2)} × {fmt(self.gamma_b_acc, 2)})",
                f"{fmt(self.fbu(True))} MPa", ref("rpa_gamma"))
        tr.step("Contrainte de calcul de l'acier (durable)", "σs = fe / γs",
                f"{fmt(self.fe, 0)} / {fmt(self.gamma_s, 2)}", f"{fmt(self.sigma_s())} MPa", ref("sigma_s"))
        tr.step("Contrainte de calcul de l'acier (situation sismique)", "σs,acc = fe / γs,acc",
                f"{fmt(self.fe, 0)} / {fmt(self.gamma_s_acc, 2)}", f"{fmt(self.sigma_s(True))} MPa", ref("rpa_gamma"))
        tr.step("Contrainte limite de compression du béton (ELS)", "σ̄bc = 0,6·fc28",
                f"0,6 × {fmt(self.fc28, 1)}", f"{fmt(self.sigma_bc_bar)} MPa", ref("sigma_bc"))
        if self.cracking == "FPP":
            tr.para("Fissuration peu préjudiciable : pas de limitation de la contrainte des aciers à l'ELS.", "note")
        else:
            ft = self.ft28
            r = math.sqrt(self.eta * ft)
            if self.is_cba:
                if self.cracking == "FP":
                    sym = "σ̄s = min(2/3·fe ; 110·√(η·ft28))"
                    num = f"min({fmt(2 / 3 * self.fe)} ; 110 × √({fmt(self.eta, 1)} × {fmt(ft)}) = {fmt(110 * r)})"
                else:
                    sym = "σ̄s = min(0,5·fe ; 90·√(η·ft28))"
                    num = f"min({fmt(0.5 * self.fe)} ; 90 × √({fmt(self.eta, 1)} × {fmt(ft)}) = {fmt(90 * r)})"
                rk = "sigma_s_bar_cba"
            else:
                xi = min(2 / 3 * self.fe, max(0.5 * self.fe, 110 * r))
                if self.cracking == "FP":
                    sym = "σ̄s = ξ = min(2/3·fe ; max(0,5·fe ; 110·√(η·ft28)))"
                    num = f"min({fmt(2 / 3 * self.fe)} ; max({fmt(0.5 * self.fe)} ; {fmt(110 * r)}))"
                else:
                    sym = "σ̄s = 0,8·ξ ;  ξ = min(2/3·fe ; max(0,5·fe ; 110·√(η·ft28)))"
                    num = f"0,8 × {fmt(xi)}"
                rk = "sigma_s_bar_mod99"
            tr.step("Contrainte limite de traction des aciers (ELS)", sym, num, f"{fmt(self.sigma_s_bar)} MPa", ref(rk))
        tr.step("Contrainte d'adhérence limite", "τs = 0,6·ψs²·ft28",
                f"0,6 × {fmt(self.psi_s, 1)}² × {fmt(self.ft28)}", f"{fmt(self.tau_s)} MPa", ref("tau_s"))
        tr.step("Moment réduit limite (durable)", "μl = 0,8·αl·(1 − 0,4·αl) ; αl = 3,5/(3,5 + 1000·εl) ; εl = σs/Es",
                f"εl = {fmt(self.sigma_s())}/{fmt(ES, 0)} = {fmt(self.sigma_s() / ES * 1000, 3)}‰",
                f"μl = {fmt(self.mu_l(), 3)}", ref("mu_l"))
