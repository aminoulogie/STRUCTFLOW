"""GCStructFlow – ETABS : companion app / plugin for ETABS 22.

Re-uses the Robot plugin modules (AutoCAD recognition, script mode, RPA 2024 spectrum, BA checks, Excel/Word)
and drives ETABS through its API: grids, stories, materials, sections with rebar, columns/beams/walls/slabs,
diaphragms, supports or soil springs, load patterns + slab loads, mass source, user spectrum, modal + Ex/Ey,
combinations, analysis, results (Nmax/Mcorr…), soil pressure check, Robot → ETABS transfer.
"""
from __future__ import annotations

import math
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT_FLOW = os.path.join(os.path.dirname(HERE), "ROBOT_FLOW")
sys.path.insert(0, HERE)
sys.path.insert(0, ROBOT_FLOW)

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,  # noqa: E402
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

import robotflow as RF  # noqa: E402
from ef import etabs as ET  # noqa: E402
from rf import codes, plan, reports, verif  # noqa: E402

APP = "GCStructFlow – ETABS"
RF.APP = APP


class EMain(RF.Main):
    """Same tabs as the Robot plugin, backend = ETABS."""

    def __init__(self):
        self.e = None
        self.frames_info = {}
        self.spring_results = []
        super().__init__()
        self.setWindowTitle(APP)
        self.lbl_robot.setText("  ETABS : non connecté  ")
        # tabs specific to ETABS
        self.tabs.removeTab(5)                                   # Robot model checks → replaced
        self.tabs.insertTab(5, self.build_found_tab(), "🧱 Fondations & ressorts")
        self.tabs.insertTab(6, self.build_robot_import_tab(), "🔁 Robot → ETABS")
        self.tabs.insertTab(5, self.build_rpa_tab(), "✅ Vérifs RPA 2024")
        self.tabs.insertTab(9, self.build_design_tab(), "🧮 Ferraillage en masse")
        self.tabs.insertTab(0, self.build_assistant_tab(), "🧭 Assistant")
        self.tabs.setCurrentIndex(0)
        self.logbox.clear()
        self.log("Bienvenue. Ouvrez ETABS (modèle vide ou existant), puis l'onglet Plan → Modèle ou Script.")

    # ================================================================== connection
    def robot(self, need_project=True):           # name kept: used everywhere in the base class
        self.e = ET.connect(start=False)
        self.lbl_robot.setText(f"  ETABS : connecté – {os.path.basename(self.e.filename()) or '(sans nom)'}  ")
        return self.e

    def connect_robot(self, quiet=False):
        try:
            self.robot()
            self.log("ETABS connecté.")
            self.refresh_sections()
        except Exception as e:  # noqa: BLE001
            self.lbl_robot.setText("  ETABS : non connecté  ")
            if not quiet:
                QMessageBox.information(self, APP, str(e))

    @RF.busy
    def new_project(self):
        if QMessageBox.question(self, APP, "Créer un NOUVEAU modèle ETABS vide (kN, m) ?\n"
                                "Le modèle ouvert sera remplacé sans enregistrement.") != QMessageBox.Yes:
            return
        self.e = ET.connect(start=True)
        lv = self.levels()
        self.e.new_model(len(lv), lv[-1].height, lv[0].height)
        self.log("Nouveau modèle ETABS créé (kN, m).")

    @RF.busy
    def calculate(self):
        e = self.robot()
        path = e.filename()
        if not path or not os.path.isabs(path):
            path, _ = QFileDialog.getSaveFileName(self, "Enregistrer le modèle ETABS avant analyse", "", "ETABS (*.edb)")
            if not path:
                return
        self.log("Analyse ETABS en cours…")
        e.run(path)
        self.log("Analyse terminée.")

    @RF.busy
    def save_project(self):
        e = self.robot()
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer le modèle ETABS", "", "ETABS (*.edb)")
        if path:
            e.save(path)
            self.log(f"Modèle enregistré : {path}")

    # ================================================================== script (full Python mode)
    def run_script(self):
        code = self.script.toPlainText()
        full = ("import " in code) or ("def main" in code) or ("e." in code and "ET." in code)
        if not full:
            return super().run_script()
        self._run_full_script(code)

    @RF.busy
    def _run_full_script(self, code):
        """Paste-and-run: any Python using the ETABS layer (ET module, e = connected model)."""
        import contextlib
        import io

        self.settings.setValue("script", code)
        e = self.robot()
        e.unlock()
        ns = {"__name__": "__main__", "__file__": os.path.join(HERE, "script_colle.py"), "ET": ET, "e": e}
        buf = io.StringIO()
        self.log("Exécution du script Python sur ETABS…")
        with contextlib.redirect_stdout(buf):
            exec(compile(code, "<script>", "exec"), ns)  # noqa: S102 – the user's own script
        out = buf.getvalue().strip()
        if out:
            self.log(out)
        e.refresh()
        self.log("✔ Script terminé.")

    # ================================================================== sections
    def global_material(self):
        fc = RF.CONCRETES[self.p_fc.currentIndex()] if hasattr(self, "p_fc") else 25
        return f"BETON{fc}", fc

    def ensure_section(self, e, text, kind):
        name, dims = RF.parse_section_text(text, kind)
        if not name:
            return ""
        mat, fc = self.global_material()
        e.ensure_concrete(mat, fc)
        reb = self.steel(e)
        if kind in ("col", "beam") and "b" in dims:
            return e.ensure_rect(name, dims["b"], dims["h"], kind, mat, reb)
        if kind == "col" and "d" in dims:
            return e.ensure_circ(name, dims["d"], mat, reb)
        if kind == "wall" and "e" in dims:
            return e.ensure_wall(name, dims["e"], mat)
        if kind == "slab" and "e" in dims:
            return e.ensure_slab(name, dims["e"], mat, membrane=self.p_slab.currentIndex() == 2)
        if name in e.frame_props():
            return name
        raise ValueError(f"Section « {text} » non comprise (ex. 40x40, Ø50, 20).")

    @RF.busy
    def create_one_section(self):
        e = self.robot()
        e.unlock()
        k = self.s_kind.currentIndex()
        mat, fc = self.material_name()
        e.ensure_concrete(mat, fc)
        reb = self.steel(e)
        b, h = self.s_b.value(), self.s_h.value()
        nm = self.s_name.text().strip()
        if k == 0:
            name = e.ensure_rect(nm or f"POT {b:g}x{h:g}", b / 100, h / 100, "col", mat, reb)
        elif k == 1:
            name = e.ensure_circ(nm or f"POT Ø{b:g}", b / 100, mat, reb)
        elif k == 2:
            name = e.ensure_rect(nm or f"PP {b:g}x{h:g}", b / 100, h / 100, "beam", mat, reb)
        elif k == 3:
            name = e.ensure_wall(nm or f"VOILE {b:g}", b / 100, mat)
        elif k == 4:
            name = e.ensure_slab(nm or f"DALLE {b:g}", b / 100, mat)
        else:
            prof = self.s_prof.text().strip()
            st = e.ensure_steel("S275", 275)
            r = e.m.PropFrame.ImportProp(prof, st, "Euro.xml", prof.replace(" ", ""), -1, "", "")
            name = prof if (r[0] if isinstance(r, tuple) else r) == 0 else f"(échec import {prof})"
        self.log(f"Section créée : {name} ({mat})")
        self.refresh_sections()

    @RF.busy
    def create_batch_sections(self):
        e = self.robot()
        e.unlock()
        made = []
        for line in self.s_batch.toPlainText().splitlines():
            if ":" not in line:
                continue
            pre, items = line.split(":", 1)
            pre = pre.strip().upper()
            kind = "col" if pre.startswith(("POT", "COL")) else "wall" if pre.startswith(("VOI", "MUR")) else \
                "slab" if pre.startswith(("DAL", "PLA")) else "beam"
            for it in items.split(","):
                it = it.strip()
                if it:
                    made.append(self.ensure_section(e, f"{pre} {it}", kind))
        self.log(f"{len(made)} sections : {', '.join(made)}")
        self.refresh_sections()

    @RF.busy
    def create_materials(self):
        e = self.robot()
        e.unlock()
        for c in RF.CONCRETES:
            e.ensure_concrete(f"BETON{c}", c)
        e.ensure_rebar("FeE400", 400)
        e.ensure_rebar("FeE500", 500)
        e.ensure_steel("S235", 235)
        e.ensure_steel("S275", 275)
        self.log("Matériaux BETON20…40, FeE400/500, S235/S275 créés.")

    def refresh_sections(self):
        try:
            info = self.robot().sections_info()
        except Exception:  # noqa: BLE001
            return
        self.robot_sections = {i["name"]: dict(i, kind="col" if i["name"].upper().startswith("POT") else "beam")
                               for i in info}
        rows = [(i["name"], i["kind"], i["b"] and i["b"] * 100, i["h"] and i["h"] * 100, None, i["material"]) for i in info]
        RF.fill_table(self.t_sections, rows, n=1)

    # ================================================================== model
    def _create_axes(self, e):
        ox, oy = self._origin()
        gx = sorted([g for g in self.grids if g.use and g.direction == "X"], key=lambda g: g.pos)
        gy = sorted([g for g in self.grids if g.use and g.direction == "Y"], key=lambda g: g.pos)
        if not gx or not gy:
            self.log("Axes : il faut au moins un axe X et un axe Y.")
            return
        e.set_grids([g.pos - ox for g in gx], [g.pos - oy for g in gy], [g.label for g in gx], [g.label for g in gy])
        self.log(f"Axes ETABS : X = {' '.join(g.label for g in gx)} ; Y = {' '.join(g.label for g in gy)}")

    @RF.busy
    def create_axes(self):
        e = self.robot()
        e.unlock()
        lv = self.levels()
        e.set_stories([x.name for x in lv], [x.height for x in lv], self.p_base.value())
        self._create_axes(e)
        e.refresh()

    @RF.busy
    def create_model(self):
        e = self.robot()
        e.unlock()
        if not (self.columns or self.beams or self.walls):
            if not self.grids:
                raise ValueError("Rien à créer : reconnaissez un plan ou exécutez un script.")
            self.create_axes()
            self.log("✔ Étages et axes créés dans ETABS (aucun poteau/poutre/voile à créer).")
            return
        levels = self.levels()
        mat, fc = self.global_material()
        e.ensure_concrete(mat, fc)
        self.steel(e)
        e.set_stories([lv.name for lv in levels], [lv.height for lv in levels], self.p_base.value())
        if self.grids:
            self._create_axes(e)
        cache = {}

        def sec(kind, text):
            if not text:
                return ""
            if (kind, text) not in cache:
                cache[(kind, text)] = self.ensure_section(e, text, kind)
            return cache[(kind, text)]

        self.graph = plan.build_graph(self.columns, self.beams, self.walls)
        g = self.graph
        ox, oy = self._origin()
        gs = plan.PlanGraph(nodes=[(x - ox, y - oy) for x, y in g.nodes], col_nodes=g.col_nodes, spans=g.spans,
                            wall_segs=g.wall_segs)
        nodes3d, bars, wall_panels, zs = plan.build_3d(
            gs, self.columns, self.beams, self.walls, levels,
            lambda c, k: sec("col", self._col_section_for(c, k)),
            lambda b, k: sec("beam", self.sec["beam"].get(b.type_key, "") or b.section),
            lambda w_, k: sec("wall", self.sec["wall"].get(w_.type_key, "") or w_.section),
            mat, base=self.p_base.value())
        self.log(f"Création ETABS : {len(bars)} barres, {len(wall_panels)} voiles…")
        k_of_z = {round(z, 4): i - 1 for i, z in enumerate(zs)}
        beams_by_level, base_pts, n_made = defaultdict(list), set(), 0
        for (i, j, prop, _m, gamma, kind) in bars:
            p1, p2 = nodes3d[i], nodes3d[j]
            name = e.add_frame(p1, p2, prop, gamma if kind == "col" else 0.0)
            n_made += 1
            if kind == "beam":
                beams_by_level[k_of_z.get(round(p1[2], 4))].append(name)
            elif min(p1[2], p2[2]) <= zs[0] + 1e-6:
                a, b = e.frame_points(name)
                base_pts.add(a if p1[2] < p2[2] else b)
            if n_made % 100 == 0:
                self.log(f"  {n_made}/{len(bars)}")
        walls = []
        for pts, th, _k in wall_panels:
            walls.append(e.add_area(pts, th))
        slabs = {}
        if self.p_slab.currentIndex():
            th = sec("slab", f"DALLE {self.p_slab_e.value():g}")
            faces = plan.slab_faces(gs)
            for k in range(len(levels)):
                z = zs[k + 1]
                slabs[k] = [e.add_area([(x, y, z) for x, y in f], th) for f in faces]
                e.diaphragm(slabs[k], "D1")
        # supports at the base (columns + wall corners)
        if self.p_support.currentIndex() == 0:
            fixed = (True,) * 6
        else:
            fixed = (True, True, True, False, False, False)
        allpts = set(base_pts)
        for wname in walls:
            try:
                r = e.m.AreaObj.GetPoints(wname, 0, None)
                for p in r[2]:
                    x, y, z = e.m.PointObj.GetCoordCartesian(p, 0.0, 0.0, 0.0, "Global")[1:4]
                    if abs(z - zs[0]) < 1e-6:
                        allpts.add(p)
            except Exception:  # noqa: BLE001
                pass
        for p in allpts:
            e.restrain(p, fixed)
        perim = self._perimeter_spans(gs)
        perim_frames = defaultdict(list)
        if perim:
            fr = e.frames()
            for name, d in fr.items():
                a = (round(d["p1"][0], 3), round(d["p1"][1], 3))
                b = (round(d["p2"][0], 3), round(d["p2"][1], 3))
                if abs(d["p1"][2] - d["p2"][2]) < 1e-6 and frozenset((a, b)) in perim:
                    k = k_of_z.get(round(d["p1"][2], 4))
                    perim_frames[k].append(name)
        self.created = dict(slabs=slabs, beams=beams_by_level, perimeter=perim_frames, base_points=sorted(allpts),
                            levels=[lv.name for lv in levels], zs=zs, walls=walls)
        e.refresh()
        self.redraw()
        self.log(f"✔ Modèle ETABS : {n_made} barres, {len(walls)} voiles, {sum(len(v) for v in slabs.values())} dalles "
                 f"(diaphragme rigide D1), {len(allpts)} appuis.")
        self.refresh_sections()
        self.refresh_load_levels()

    # ================================================================== loads & combinations
    @RF.busy
    def create_cases_and_loads(self):
        e = self.robot()
        e.unlock()
        e.load_pattern("G", "G", 1.0 if self.l_sw.isChecked() else 0.0)
        e.load_pattern("Q", "Q", 0.0)
        slabs = self.created.get("slabs", {})
        per = self.created.get("perimeter", {})
        n = 0
        for i in range(self.t_loadlev.rowCount()):
            G = float(self.t_loadlev.item(i, 2).text().replace(",", ".") or 0)
            Q = float(self.t_loadlev.item(i, 3).text().replace(",", ".") or 0)
            Wl = float(self.t_loadlev.item(i, 4).text().replace(",", ".") or 0)
            for a in slabs.get(i, []):
                if G:
                    e.area_load(a, "G", G)
                if Q:
                    e.area_load(a, "Q", Q)
                n += 1
            if Wl:
                for f in per.get(i, []):
                    e.frame_load(f, "G", Wl)
        self.c_G.setText("G")
        self.c_Q.setText("Q")
        self.log(f"Patterns G (poids propre ×{1 if self.l_sw.isChecked() else 0}) et Q ; charges sur {n} dalles.")
        self.refresh_cases()

    @RF.busy
    def refresh_cases(self):
        e = self.robot()
        rows = [(i + 1, c, "cas", "", "") for i, c in enumerate(e.load_cases())]
        rows += [(len(rows) + i + 1, c, "comb.", "", "") for i, c in enumerate(e.combos())]
        RF.fill_table(self.t_cases, rows)

    @RF.busy
    def detect_cases(self):
        e = self.robot()
        cases = e.load_cases()
        up = {c.upper(): c for c in cases}
        self.c_G.setText(" ".join(c for c in cases if c.upper() in ("G", "DEAD", "GS", "SDEAD")))
        self.c_Q.setText(" ".join(c for c in cases if c.upper() in ("Q", "LIVE")))
        self.c_Ex.setText(up.get("EX", ""))
        self.c_Ey.setText(up.get("EY", ""))
        self.log(f"Cas ETABS : {', '.join(cases)}")

    def _combos(self):
        names = lambda w: [x for x in w.text().replace(",", " ").split() if x]  # noqa: E731
        G, Q, W, S = names(self.c_G), names(self.c_Q), names(self.c_W), names(self.c_S)
        Ex, Ey = (names(self.c_Ex) or [None])[0], (names(self.c_Ey) or [None])[0]
        psi = self.c_psi.value()
        out = []

        def f(g=0.0, q=0.0, s=0.0, extra=None):
            d = {}
            for c in G:
                d[c] = d.get(c, 0) + g
            for c in Q:
                d[c] = d.get(c, 0) + q
            for c in S:
                d[c] = d.get(c, 0) + s
            d.update(extra or {})
            return {k: v for k, v in d.items() if v}

        out.append(("ELU 1.35G+1.5Q", "ELU", f(1.35, 1.5)))
        out.append(("ELS G+Q", "ELS", f(1.0, 1.0)))
        for w in W:
            out += [(f"ELU 1.35G+1.5{w}", "ELU", f(1.35, extra={w: 1.5})), (f"ELU G+1.5{w}", "ELU", f(1.0, extra={w: 1.5})),
                    (f"ELS G+{w}", "ELS", f(1.0, extra={w: 1.0}))]
        if S:
            out += [("ELU 1.35G+1.5S", "ELU", f(1.35, s=1.5)), ("ELS G+S", "ELS", f(1.0, s=1.0))]
        # ETABS: spectral cases are positive envelopes → each combination gives Max and Min (± handled by ETABS)
        if Ex or Ey:
            if self.c_code.currentIndex() == 0:   # RPA 2024
                pairs = [(1.0, 0.3, "Ex+0.3Ey"), (0.3, 1.0, "0.3Ex+Ey")] if (Ex and Ey) else [(1.0, 1.0, "E")]
                for a, b, nm in pairs:
                    ex = {k: v for k, v in ((Ex, a), (Ey, b)) if k}
                    out.append((f"ACC G+{psi:g}Q±({nm})", "ACC", f(1.0, psi, extra=ex)))
                    if self.c_08.isChecked():
                        out.append((f"ACC 0.8G±({nm})", "ACC", f(0.8, extra=ex)))
            else:
                for E_, nm in ((Ex, "Ex"), (Ey, "Ey")):
                    if not E_:
                        continue
                    out.append((f"ACC G+Q±{nm}", "ACC", f(1.0, 1.0, extra={E_: 1.0})))
                    if self.c_08.isChecked():
                        out.append((f"ACC 0.8G±{nm}", "ACC", f(0.8, extra={E_: 1.0})))
                    if self.c_12.isChecked():
                        out.append((f"ACC G+Q±1.2{nm}", "ACC", f(1.0, 1.0, extra={E_: 1.2})))
        return out

    @RF.busy
    def create_combos(self):
        e = self.robot()
        e.unlock()
        cs = self._combos()
        if self.c_replace.isChecked():
            e.delete_combos(e.combos())
        for name, _t, fac in cs:
            e.combo(name, fac)
        for t in ("ELU", "ELS", "ACC"):
            members = [n for n, tt, _ in cs if tt == t]
            if members:
                e.combo(f"ENV {t}", {n: 1.0 for n in members}, envelope=True)
        self.preview_combos()
        self.refresh_cases()
        self.log(f"✔ {len(cs)} combinaisons + enveloppes ENV ELU/ELS/ACC créées dans ETABS.")

    # ================================================================== seismic
    @RF.busy
    def create_seismic(self):
        e = self.robot()
        e.unlock()
        beta = self.e_beta.value()
        e.mass_source([("G", 1.0), ("Q", beta)])
        name = f"RPA2024 Z{self.e_zone.currentText()} {self.e_site.currentText()}"
        e.rs_function(name, [(T, a / 9.81) for T, a in self.spectrum], self.e_xi.value() / 100)
        e.modal("Modal", self.e_modes.value())
        dirs = ["X", "Y"] + (["Z"] if self.e_dirs.currentIndex() == 1 else [])
        for d in dirs:
            e.rs_case(f"E{d.lower()}", d, name, "Modal", ecc=0.05)
        self.c_Ex.setText("Ex")
        self.c_Ey.setText("Ey")
        self.log(f"✔ Source de masse G + {beta:g}Q, fonction « {name} », Modal ({self.e_modes.value()} modes), "
                 f"{', '.join('E' + d.lower() for d in dirs)} (CQC, excentricité 5 %).")

    @RF.busy
    def read_modal(self):
        e = self.robot()
        self.modal = e.modal_table()
        RF.fill_table(self.t_modal, self.modal, n=3)
        if self.modal:
            last = self.modal[-1]
            self.log(f"Modal : T1 = {self.modal[0][1]:.3f} s ; ΣUX = {last[5]:.1f} %, ΣUY = {last[6]:.1f} % "
                     f"{'✔' if last[5] >= 90 and last[6] >= 90 else '✖ < 90 % (RPA 2024 §4.3.4) : augmentez les modes'}")

    def build_seismic_tab(self):
        w = super().build_seismic_tab()
        from PySide6.QtWidgets import QLabel as _L, QPushButton as _B
        for b in w.findChildren(_B):
            b.setText(b.text().replace("dans Robot", "dans ETABS").replace("(Robot / logiciel RPA)", "(.txt)"))
        for lab in w.findChildren(_L):
            if lab.text().startswith("Masses : Robot"):
                lab.setText("Masses : source de masse ETABS G + βQ (créée automatiquement).")
        self.e_beta = QDoubleSpinBox(decimals=2, minimum=0, maximum=1, value=0.20, singleStep=0.05)
        lay = w.layout().itemAt(0).layout()
        box = QGroupBox("Source de masse ETABS")
        f = QFormLayout(box)
        f.addRow("β (coefficient de pondération de Q)", self.e_beta)
        lay.insertWidget(1, box)
        return w

    # ================================================================== results
    @RF.busy
    def read_results(self):
        e = self.robot()
        combos = [c for c in e.combos() if not c.startswith("ENV")]
        if not combos:
            raise ValueError("Aucune combinaison dans ETABS.")
        typ = {}
        for c in combos:
            typ[c] = "ELU" if c.startswith("ELU") else "ELS" if c.startswith("ELS") else "ACC" if c.startswith("ACC") else "ELU"
        self.log("Lecture des efforts ETABS…")
        fr = e.frames()
        self.frames_info = fr
        data = e.frame_forces(combos)
        by = defaultdict(list)
        for r in data:
            by[r["frame"]].append(r)
        col_rows, beam_rows = [], []
        for name, d in fr.items():
            rows = by.get(name, [])
            if not rows:
                continue
            p1, p2 = d["p1"], d["p2"]
            L = math.dist(p1, p2)
            is_col = abs(p2[2] - p1[2]) > 0.9 * L
            if is_col:
                smin, smax = min(r["sta"] for r in rows), max(r["sta"] for r in rows)
                for sit in ("ELU", "ELS", "ACC"):
                    vals = [dict(case=r["combo"] + (f" {r['step']}" if r["step"] else ""), cmp=0,
                                 pos="pied" if abs(r["sta"] - smin) < 1e-6 else "tête",
                                 N=-r["P"], My=r["M2"], Mz=r["M3"], Vy=r["V2"], Vz=r["V3"], T=r["T"])
                            for r in rows if typ.get(r["combo"]) == sit and (abs(r["sta"] - smin) < 1e-6 or abs(r["sta"] - smax) < 1e-6)]
                    if not vals:
                        continue
                    crit = {"Nmax": max(vals, key=lambda v: v["N"]), "Nmin": min(vals, key=lambda v: v["N"]),
                            "|My|max": max(vals, key=lambda v: abs(v["My"])), "|Mz|max": max(vals, key=lambda v: abs(v["Mz"])),
                            "|V|max": max(vals, key=lambda v: math.hypot(v["Vy"], v["Vz"]))}
                    lo = p1 if p1[2] <= p2[2] else p2
                    for cn, v in crit.items():
                        col_rows.append(dict(bar=name, x=round(lo[0], 3), y=round(lo[1], 3), z0=round(lo[2], 3), z1=None,
                                             section=d["prop"], situation=sit, critere=cn, **v))
            else:
                for sit in ("ELU", "ACC"):
                    rr = [r for r in rows if typ.get(r["combo"]) == sit]
                    if not rr:
                        continue
                    mt = max(rr, key=lambda r: r["M3"])
                    ma = min(rr, key=lambda r: r["M3"])
                    vm = max(rr, key=lambda r: abs(r["V2"]))
                    beam_rows.append(dict(bar=name, section=d["prop"], L=round(L, 3), situation=sit,
                                          Mt=max(mt["M3"], 0), Mt_case=mt["combo"], Ma=min(ma["M3"], 0), Ma_case=ma["combo"],
                                          V=abs(vm["V2"]), V_case=vm["combo"]))
        self.col_rows, self.beam_rows = col_rows, beam_rows
        secs = {}
        for i in e.sections_info():
            secs[i["name"]] = i
        fc = float(self.x_fc.currentText())
        self.nu_rows = verif.column_nu(col_rows, secs, fc, self.x_nu.value(),
                                       situations=("ACC",) if any(t == "ACC" for t in typ.values()) else ("ELU",))
        self.bd_rows = verif.beam_design(beam_rows, secs, fc, acc_gb=self.x_gb.value())
        RF.fill_table(self.t_colres, self.col_rows, [k for k, _ in reports.COL_HEAD])
        RF.fill_table(self.t_nu, self.nu_rows, [k for k, _ in reports.NU_HEAD], n=3)
        RF.fill_table(self.t_bd, self.bd_rows, [k for k, _ in reports.BD_HEAD])
        bad = [x for x in self.nu_rows if not x["ok"]]
        self.log(f"✔ {len(col_rows)} lignes poteaux, {len(beam_rows)} poutres ; ν max = "
                 f"{max([x['nu'] for x in self.nu_rows] or [0]):.3f} ; {len(bad)} poteau(x) au-delà de la limite.")

    def _project_info(self):
        info = {"Modèle ETABS": self.e.filename() if self.e else ""}
        info.update({"Zone": self.e_zone.currentText(), "Site": self.e_site.currentText(),
                     "Groupe": self.e_group.currentText(), "R": self.e_R.value(), "Q_F": self.e_QF.value(),
                     "fc28 (MPa)": self.x_fc.currentText()})
        return info

    @RF.busy
    def export_excel(self):
        path, _ = QFileDialog.getSaveFileName(self, "Excel", "resultats_etabs.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        e = self.robot()
        combos = [dict(number=i + 1, name=n, nature=t, factors=f) for i, (n, t, f) in enumerate(self._combos())]
        reports.export_excel(path, self._project_info(), combos, self.col_rows, self.beam_rows, self.nu_rows,
                             self.bd_rows, self.modal, self.spectrum)
        self.log(f"Excel : {path}")
        os.startfile(path)  # noqa: S606
        del e

    @RF.busy
    def export_word(self):
        path, _ = QFileDialog.getSaveFileName(self, "Word", "note_de_calcul_etabs.docx", "Word (*.docx)")
        if not path:
            return
        png = os.path.splitext(path)[0] + "_spectre.png"
        self.fig.savefig(png, dpi=150)
        shot = self._etabs_screenshot(os.path.splitext(path)[0] + "_modele.png")
        combos = [dict(number=i + 1, name=n, nature=t, factors=f) for i, (n, t, f) in enumerate(self._combos())]
        mat, fc = self.global_material()
        fe = getattr(self, "d_fe", None).currentText() if getattr(self, "d_fe", None) else "FeE500"
        hyp = [("Béton", f"{mat} – fc28 = {fc} MPa", "CBA 93 / BAEL 91 mod.99"),
               ("Acier", f"{fe}", "CBA 93"),
               ("Coefficients de sécurité", "γb = 1,5 / γs = 1,15 (durable) ; γb = 1,2 / γs = 1,0 (accidentel)",
                "CBA 93 ; RPA 2024 §7.3.2"),
               ("Zone / site / groupe", f"{self.e_zone.currentText()} / {self.e_site.currentText()} / "
                                       f"{self.e_group.currentText()}", "RPA 2024"),
               ("Comportement", f"R = {self.e_R.value():g} ; Q_F = {self.e_QF.value():g}", "RPA 2024"),
               ("Source de masse", f"G + {self.e_beta.value():g}·Q", "RPA 2024"),
               ("Charges", "Permanentes et d'exploitation", "DTR B.C 2.2")]
        loads = []
        for i in range(self.t_loadlev.rowCount()):
            t = self.t_loadlev
            loads.append([t.item(i, 0).text(), t.cellWidget(i, 1).currentText()] +
                         [t.item(i, j).text() if t.item(i, j) else "" for j in (2, 3, 4, 5)])
        notes = ["Efforts extraits d'ETABS (N > 0 compression). Les cas spectraux ETABS étant des enveloppes positives, "
                 "les efforts « correspondants » des combinaisons sismiques sont les valeurs Max/Min de chaque composante."]
        reports.export_word(path, self._project_info(), combos, self.col_rows, self.beam_rows, self.nu_rows,
                            self.bd_rows, self.modal, png, notes, title="Note de calcul – structure",
                            hypotheses=hyp, loads=loads, rpa=self.rpa_rows, dcol=self.dcol_rows,
                            images=[("Modèle ETABS", shot)] if shot else None)
        self.log(f"Word : {path}")
        os.startfile(path)  # noqa: S606

    # ================================================================== steel grade, templates, assistant
    def steel(self, e):
        fe = 500 if getattr(self, "d_fe", None) is None or self.d_fe.currentText() == "FeE500" else 400
        return e.ensure_rebar(f"FeE{fe}", fe)

    TEMPLATE_WIDGETS = ("p_fc", "d_fe", "e_zone", "e_site", "e_group", "e_sys", "e_R", "e_QF", "e_xi", "e_beta",
                        "e_modes", "c_code", "c_psi", "c_08", "c_12", "x_fc", "x_nu", "k_ct", "p_slab", "p_slab_e",
                        "p_support", "p_base", "f_sigma", "f_ks")

    def template_data(self):
        from PySide6.QtWidgets import QAbstractSpinBox, QCheckBox as _C, QComboBox as _Co

        d = {}
        for name in self.TEMPLATE_WIDGETS:
            wdg = getattr(self, name, None)
            if isinstance(wdg, _Co):
                d[name] = wdg.currentText()
            elif isinstance(wdg, _C):
                d[name] = wdg.isChecked()
            elif isinstance(wdg, QAbstractSpinBox):
                d[name] = wdg.value()
        d["levels"] = [[self.t_levels.item(i, 0).text(), self.t_levels.item(i, 1).text()]
                       for i in range(self.t_levels.rowCount())]
        d["loads"] = [[self.t_loadlev.cellWidget(i, 1).currentText()] +
                      [self.t_loadlev.item(i, j).text() if self.t_loadlev.item(i, j) else "" for j in (2, 3, 4)]
                      for i in range(self.t_loadlev.rowCount())]
        return d

    def apply_template(self, d):
        from PySide6.QtWidgets import QAbstractSpinBox, QCheckBox as _C, QComboBox as _Co

        for name, v in d.items():
            wdg = getattr(self, name, None)
            if isinstance(wdg, _Co):
                wdg.setCurrentText(str(v))
            elif isinstance(wdg, _C):
                wdg.setChecked(bool(v))
            elif isinstance(wdg, QAbstractSpinBox):
                wdg.setValue(float(v))
        if d.get("levels"):
            self.t_levels.blockSignals(True)
            self.t_levels.setRowCount(len(d["levels"]))
            for i, (n, h) in enumerate(d["levels"]):
                self.t_levels.setItem(i, 0, RF.item(n, True))
                self.t_levels.setItem(i, 1, RF.item(h, True))
            self.t_levels.blockSignals(False)
            self._levels_changed()
            self.refresh_load_levels()
        for i, row in enumerate(d.get("loads", [])):
            if i < self.t_loadlev.rowCount():
                self.t_loadlev.cellWidget(i, 1).setCurrentText(row[0])
                for j, v in zip((2, 3, 4), row[1:]):
                    if self.t_loadlev.item(i, j):
                        self.t_loadlev.item(i, j).setText(v)

    def save_template(self):
        import json

        path, _ = QFileDialog.getSaveFileName(self, "Modèle de projet", self.settings.value("tpl_dir", "") +
                                              "/modele_projet.gcsf.json", "Modèle GCStructFlow (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.template_data(), f, ensure_ascii=False, indent=1)
            self.settings.setValue("tpl_dir", os.path.dirname(path))
            self.settings.setValue("tpl_last", path)
            self.log(f"Modèle de projet enregistré : {path}")

    def load_template(self, path=None):
        import json

        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Modèle de projet", self.settings.value("tpl_dir", ""),
                                                  "Modèle GCStructFlow (*.json)")
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.apply_template(json.load(f))
            self.settings.setValue("tpl_last", path)
            self.log(f"Modèle de projet chargé : {path}")

    def build_assistant_tab(self):
        from PySide6.QtWidgets import QGridLayout

        w = QWidget()
        g = QGridLayout(w)
        steps = [
            ("0", "Modèle de projet", "Charger vos réglages (béton, acier, zone, R, β, niveaux, charges)",
             [("📂 Charger", self.load_template), ("💾 Enregistrer", self.save_template)]),
            ("1", "Plan", "AutoCAD : lire le dessin, 📏 échelle, 🖱 axes, 🖱 poteaux/poutres/voiles – ou Script",
             [("📐 Plan", lambda: self._goto("Plan")), ("⌨ Script", lambda: self._goto("Script"))]),
            ("2", "Sections & niveaux", "Taper les sections par type, variation par niveau, niveaux",
             [("📐 Tableaux", lambda: self._goto("Plan"))]),
            ("3", "Créer le modèle", "Étages, axes, matériaux, sections, éléments, dalles, diaphragme, appuis",
             [("🏗 Créer", self.create_model)]),
            ("4", "Charges", "Planchers proposés DTR B.C 2.2 (G, Q, murs) → patterns G/Q + charges",
             [("⚖ Charges", lambda: self._goto("Charges")), ("✔ Appliquer", self.create_cases_and_loads)]),
            ("5", "Sismique", "Spectre RPA 2024, source de masse, Modal, Ex/Ey ; combinaisons",
             [("🌍 Sismique", lambda: self._goto("Sismique")), ("✔ Créer", self.create_seismic),
              ("✔ Combinaisons", self.create_combos)]),
            ("6", "Calcul", "Enregistrer et lancer l'analyse ETABS", [("🚀 Calculer", self.calculate)]),
            ("7", "Vérifications RPA", "V_dyn/V_st (majoration), déplacements, P-Δ, interaction, renversement",
             [("✅ Vérifier", lambda: (self._goto("Vérifs"), self.run_rpa_checks()))]),
            ("8", "Ferraillage", "Efforts → poteaux (POTEAUX_FCD), poutres (longitudinal + transversal)",
             [("📊 Efforts", self.read_results), ("🏛 Poteaux", self.bulk_columns), ("📏 Poutres", self.bulk_beams)]),
            ("9", "Note & fondations", "Note Word complète, Excel ; réactions → app Semelles",
             [("📘 Note Word", self.export_word), ("📗 Excel", self.export_excel), ("⚓ Fondations", lambda: self._goto("Fondations"))]),
        ]
        for r, (num, name, desc, buttons) in enumerate(steps):
            lab = QLabel(f"<b>{num}. {name}</b><br><span style='color:#555'>{desc}</span>")
            lab.setWordWrap(True)
            g.addWidget(lab, r, 0)
            box = QHBoxLayout()
            for txt, fn in buttons:
                b = QPushButton(txt)
                b.clicked.connect(fn)
                box.addWidget(b)
            box.addStretch()
            g.addLayout(box, r, 1)
        g.setColumnStretch(0, 2)
        g.setColumnStretch(1, 3)
        g.setRowStretch(len(steps), 1)
        return w

    def _etabs_screenshot(self, path):
        """Capture the ETABS window (it must be visible on screen)."""
        try:
            import win32gui
            from PIL import ImageGrab

            from ef.ribbon import _etabs_main, _view_rect

            h = _etabs_main()
            if not h:
                return None
            ws = getattr(getattr(self, "_ribbon", None), "ws", None)
            if ws is not None:
                ws.hide()
            win32gui.SetForegroundWindow(h)
            import time

            time.sleep(0.6)
            ImageGrab.grab(bbox=_view_rect(h)).save(path)
            return path
        except Exception:  # noqa: BLE001
            return None

    # ================================================================== RPA 2024 checks
    def build_rpa_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        self.k_ct = QDoubleSpinBox(decimals=3, minimum=0.01, maximum=0.2, value=0.050, singleStep=0.005)
        self.k_ex = QLineEdit("Ex")
        self.k_ey = QLineEdit("Ey")
        b = QPushButton("✅ Lancer les vérifications RPA 2024")
        b.setStyleSheet("font-weight:bold")
        b.clicked.connect(self.run_rpa_checks)
        bs = QPushButton("⤴ Appliquer la majoration de Ex / Ey")
        bs.clicked.connect(self.apply_rpa_scale)
        be = QPushButton("📗 Exporter (Excel)")
        be.clicked.connect(self.export_rpa)
        for wdg in (QLabel("Ct"), self.k_ct, QLabel("Cas Ex"), self.k_ex, QLabel("Cas Ey"), self.k_ey, b, bs, be):
            row.addWidget(wdg)
        v.addLayout(row)
        self.t_rpa = RF.table(["Vérification", "Valeur", "Limite", "Vérifié", "Détail"])
        v.addWidget(self.t_rpa)
        note = QLabel("Après « ▶ Calculer ». R, Q_F, β et le spectre sont ceux de l'onglet Sismique. "
                      "Si V_dyn < 0,8·V_st : « Appliquer la majoration » multiplie le facteur d'échelle des cas spectraux "
                      "par r = 0,8·V_st/V_dyn, puis relancez le calcul.")
        note.setWordWrap(True)
        v.addWidget(note)
        self.rpa_rows, self.rpa_scale = [], {}
        return w

    @RF.busy
    def run_rpa_checks(self):
        from ef import rpa

        e = self.robot()
        if not self.modal:
            try:
                self.modal = e.modal_table()
            except Exception:  # noqa: BLE001
                self.modal = []
        G = (self.c_G.text().split() or ["G"])[0]
        Q = (self.c_Q.text().split() or ["Q"])[0]
        rows, scale = rpa.run_checks(e, self.spec_params(), self.e_R.value(), self.e_QF.value(), self.e_beta.value(),
                                     self.k_ct.value(), self.k_ex.text().strip(), self.k_ey.text().strip(), G, Q,
                                     self.modal)
        self.rpa_rows, self.rpa_scale = rows, scale
        RF.fill_table(self.t_rpa, rows, n=3)
        bad = [r for r in rows if r[3] is False]
        self.log(f"Vérifications RPA 2024 : {len(rows)} lignes, {len(bad)} non vérifiée(s).")

    @RF.busy
    def apply_rpa_scale(self):
        from ef import rpa

        e = self.robot()
        done = []
        for case, f in self.rpa_scale.items():
            if f > 1.0:
                rpa.apply_scale(e, case, f)
                done.append(f"{case} × {f:.3f}")
        self.log("Majoration appliquée : " + (", ".join(done) if done else "aucune (V_dyn ≥ 0,8·V_st)") +
                 ". Relancez ▶ Calculer.")

    @RF.busy
    def export_rpa(self):
        path, _ = QFileDialog.getSaveFileName(self, "Excel", "verifications_RPA2024.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        reports.export_table(path, "Vérifications RPA 2024", ["Vérification", "Valeur", "Limite", "Vérifié", "Détail"],
                             self.rpa_rows)
        self.log(f"Excel : {path}")
        os.startfile(path)  # noqa: S606

    # ================================================================== bulk design
    def build_design_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        self.d_fe = QComboBox()
        self.d_fe.addItems(["FeE500", "FeE400"])
        bc = QPushButton("🏛 Ferrailler tous les poteaux (POTEAUX_FCD)")
        bc.setStyleSheet("font-weight:bold")
        bc.clicked.connect(self.bulk_columns)
        bb = QPushButton("📏 Poutres : armatures transversales + zones nodales")
        bb.clicked.connect(self.bulk_beams)
        bx = QPushButton("📗 Exporter (Excel)")
        bx.clicked.connect(self.export_design)
        for wdg in (QLabel("Acier"), self.d_fe, bc, bb, bx):
            row.addWidget(wdg)
        v.addLayout(row)
        self.t_dcol = RF.table(["Type", "Section", "Z pied", "Nb", "As th (cm²)", "As min (cm²)", "Barres",
                                "As (cm²)", "Taux d'utilisation", "Cadres", "OK", "Non vérifié"])
        self.t_dbeam = RF.table(["Barre", "Section", "Sit.", "Choix trav.", "Choix app.", "St courant (m)",
                                 "St nodal (m)", "L nodale (m)", "τu", "OK"])
        v.addWidget(QLabel("Poteaux – un type = même section et même étage ; les couples critiques de tous les poteaux "
                           "du type sont vérifiés (flexion composée déviée, méthode exacte)."))
        v.addWidget(self.t_dcol, 2)
        v.addWidget(QLabel("Poutres – après « Lire les efforts » (onglet Résultats)."))
        v.addWidget(self.t_dbeam, 1)
        self.dcol_rows = []
        return w

    def _sections_dims(self):
        out = {}
        for i in self.robot().sections_info():
            if i.get("b"):
                out[i["name"]] = dict(b=i["b"], h=i["h"])
        return out

    @RF.busy
    def bulk_columns(self):
        from rf import bulk

        if not self.col_rows:
            self.read_results()
        if not self.col_rows:
            raise ValueError("Pas d'efforts poteaux (lancez le calcul puis « Lire les efforts »).")
        zs = self.created.get("zs") or []
        sh = {round(a, 2): b - a for a, b in zip(zs, zs[1:])}
        fe = 500.0 if self.d_fe.currentText() == "FeE500" else 400.0
        self.log("Ferraillage des poteaux (POTEAUX_FCD)…")
        self.dcol_rows = bulk.design_columns(self.col_rows, self._sections_dims(), float(self.x_fc.currentText()), fe,
                                             self.e_zone.currentText(), sh,
                                             progress=lambda k, n: (k % 5 == 0) and self.log(f"  type {k}/{n}"))
        RF.fill_table(self.t_dcol, self.dcol_rows, ["type", "section", "z0", "n", "As_th", "As_min", "bars", "As_prov",
                                                     "ratio", "ties", "ok", "fails"])
        bad = [r for r in self.dcol_rows if not r["ok"]]
        self.log(f"✔ {len(self.dcol_rows)} types de poteaux ferraillés ; {len(bad)} avec une vérification non satisfaite.")

    @RF.busy
    def bulk_beams(self):
        from rf import bulk

        if not self.bd_rows:
            self.read_results()
        bulk.beam_stirrups(self.bd_rows, float(self.x_fc.currentText()), 400.0)
        RF.fill_table(self.t_dbeam, self.bd_rows, ["bar", "section", "situation", "bars_trav", "bars_app", "St_courant",
                                                    "St_nodal", "L_nodale", "tau", "ok"])
        self.log(f"✔ Armatures transversales : {len(self.bd_rows)} lignes poutres.")

    @RF.busy
    def export_design(self):
        path, _ = QFileDialog.getSaveFileName(self, "Excel", "ferraillage.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        reports.export_table(path, "Poteaux", ["Type", "Section", "Z pied", "Nb", "As th", "As min", "Barres", "As",
                                               "Taux", "Cadres", "OK", "Non vérifié"],
                             [[r.get(k) for k in ("type", "section", "z0", "n", "As_th", "As_min", "bars", "As_prov",
                                                  "ratio", "ties", "ok", "fails")] for r in self.dcol_rows],
                             extra=[("Poutres", ["Barre", "Section", "Sit.", "Choix trav.", "Choix app.", "St courant",
                                                 "St nodal", "L nodale", "τu", "OK"],
                                     [[r.get(k) for k in ("bar", "section", "situation", "bars_trav", "bars_app",
                                                          "St_courant", "St_nodal", "L_nodale", "tau", "ok")]
                                      for r in self.bd_rows])])
        self.log(f"Excel : {path}")
        os.startfile(path)  # noqa: S606

    # ================================================================== foundations & springs
    def build_found_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        g = QGroupBox("Ressorts de sol (Winkler) sous les appuis")
        f = QFormLayout(g)
        self.f_mode = QComboBox()
        self.f_mode.addItems(["Semelles isolées : ressorts ponctuels (Kz = ks·A)", "Radier / dalle : ressorts surfaciques (ks)"])
        self.f_sigma = QDoubleSpinBox(decimals=3, minimum=0.01, maximum=5, value=0.20, suffix=" MPa")
        self.f_ks = QDoubleSpinBox(decimals=0, minimum=1000, maximum=500000, value=40000, suffix=" kN/m³")
        self.f_ks_auto = QPushButton("ks ≈ 120·σadm (kN/m³, σ en kPa)")
        self.f_ks_auto.clicked.connect(lambda: self.f_ks.setValue(120 * self.f_sigma.value() * 1000))
        self.f_A = QDoubleSpinBox(decimals=2, minimum=0.1, maximum=50, value=2.25, suffix=" m² (B×L semelle)")
        self.f_kh = QDoubleSpinBox(decimals=2, minimum=0, maximum=2, value=0.5)
        self.f_comp = QCheckBox("Compression seule (pas de traction dans le sol) + cas non linéaire G+Q")
        self.f_comp.setChecked(True)
        f.addRow("Type", self.f_mode)
        f.addRow("σ adm sol (rapport de sol)", self.f_sigma)
        f.addRow("Module de réaction ks", self.f_ks)
        f.addRow(self.f_ks_auto)
        f.addRow("Aire semelle", self.f_A)
        f.addRow("Kx = Ky = α·Kz, α =", self.f_kh)
        f.addRow(self.f_comp)
        b = QPushButton("🧱 Remplacer les encastrements par des ressorts")
        b.clicked.connect(self.apply_springs)
        f.addRow(b)
        v.addWidget(g)
        g2 = QGroupBox("Vérification des contraintes du sol (après analyse)")
        f2 = QFormLayout(g2)
        b2 = QPushButton("📏 Contraintes sous semelles : σ = N/A ≤ σadm (ELS) / 2·σadm·… (ACC) ; soulèvement")
        b2.clicked.connect(self.check_soil)
        b3 = QPushButton("📗 Exporter les réactions pour l'app Semelles (format ETABS Joint Reactions)")
        b3.clicked.connect(self.export_reactions)
        f2.addRow(b2)
        f2.addRow(b3)
        v.addWidget(g2)
        self.t_soil = RF.table(["Appui", "Combinaison", "N (kN)", "σ (kPa)", "σ lim (kPa)", "Vérifié", "Remarque"])
        v.addWidget(self.t_soil)
        note = QLabel("Ressorts : un modèle linéaire autorise une « traction » fictive du sol. Avec « compression seule », "
                      "ETABS ne l'applique que dans les cas NON LINÉAIRES : l'app crée le cas « NL G+Q » (non linéaire "
                      "statique) ; vérifiez le soulèvement sur ce cas et sur les combinaisons ACC (0.8G±E).")
        note.setWordWrap(True)
        v.addWidget(note)
        return w

    @RF.busy
    def apply_springs(self):
        e = self.robot()
        e.unlock()
        pts = self.created.get("base_points") or []
        if not pts:
            raise ValueError("Points d'appui inconnus : créez le modèle depuis l'onglet Plan (ou utilisez ETABS).")
        ks = self.f_ks.value()
        if self.f_mode.currentIndex() == 0:
            kz = ks * self.f_A.value()
            kh = self.f_kh.value() * kz
            for p in pts:
                e.restrain(p, (False,) * 6)
                e.point_spring(p, [kh, kh, kz, 0, 0, 0])
                e.restrain(p, (False, False, False, True, True, True) if False else (False,) * 6)
            self.log(f"✔ Ressorts ponctuels sur {len(pts)} appuis : Kz = {kz:,.0f} kN/m, Kx = Ky = {kh:,.0f} kN/m.")
        else:
            prop = e.area_spring_prop("SOL ks", ks, 0, 0, self.f_comp.isChecked())
            slabs0 = [a for a in self.created.get("base_slabs", [])]
            for a in slabs0:
                e.assign_area_spring(a, prop)
            self.log(f"✔ Propriété « SOL ks » = {ks:,.0f} kN/m³ créée ; assignée à {len(slabs0)} radier(s). "
                     "Sélectionnez votre radier dans ETABS : Assign > Shell > Area Springs > SOL ks.")
        if self.f_comp.isChecked():
            try:
                NL = e.m.LoadCases.StaticNonlinear
                NL.SetCase("NL G+Q")
                NL.SetLoads("NL G+Q", 2, ET._arr(str, ["Load", "Load"]), ET._arr(str, ["G", "Q"]), ET._arr(float, [1.0, 1.0]))
                self.log("Cas non linéaire « NL G+Q » créé.")
            except Exception as ex:  # noqa: BLE001
                self.log(f"Cas non linéaire non créé ({ex}).")

    @RF.busy
    def check_soil(self):
        e = self.robot()
        combos = [c for c in e.combos() if not c.startswith("ENV")]
        rows = e.joint_reactions(combos)
        A = self.f_A.value()
        sig = self.f_sigma.value() * 1000
        out = []
        for r in rows:
            N = r["F3"]
            s = N / A
            acc = r["combo"].startswith("ACC")
            lim = 2.0 * sig if acc else sig        # RPA 2024 §10.1.4 : Fs global 2.0 sous combinaisons sismiques
            ok = 0 <= s <= lim
            rem = "soulèvement (N < 0)" if N < 0 else ""
            out.append((r["point"], f"{r['combo']} {r['step']}".strip(), N, s, lim, ok, rem))
        out.sort(key=lambda x: (x[5], -x[3]))
        RF.fill_table(self.t_soil, out)
        self.log(f"Sol : {sum(1 for x in out if not x[5])} ligne(s) non vérifiée(s) sur {len(out)} "
                 f"(A = {A:g} m², σadm = {sig:g} kPa).")

    @RF.busy
    def export_reactions(self):
        e = self.robot()
        path, _ = QFileDialog.getSaveFileName(self, "Réactions", "reactions_etabs.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        combos = [c for c in e.combos() if not c.startswith("ENV")]
        rows = e.joint_reactions(combos)
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Joint Reactions"
        ws.append(["Story", "Label", "Unique Name", "Output Case", "Case Type", "Step Type", "FX", "FY", "FZ", "MX", "MY", "MZ"])
        for r in rows:
            ws.append(["Base", r["point"], r["point"], r["combo"], "Combination", r["step"], r["F1"], r["F2"], r["F3"],
                       r["M1"], r["M2"], r["M3"]])
        wb.save(path)
        self.log(f"Réactions exportées : {path} → app Semelles : Efforts > importer tableau ETABS.")

    # ================================================================== Robot → ETABS
    def build_robot_import_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Transfère le modèle Robot OUVERT (nœuds, barres, sections béton/acier, appuis, panneaux, "
                           "cas G/Q et charges uniformes) vers le modèle ETABS ouvert. Unités : m, kN."))
        row = QHBoxLayout()
        self.ri_story = QCheckBox("Créer les étages ETABS d'après les cotes Z des nœuds Robot")
        self.ri_story.setChecked(True)
        b = QPushButton("🔁 Transférer Robot → ETABS")
        b.clicked.connect(self.robot_to_etabs)
        row.addWidget(self.ri_story)
        row.addWidget(b)
        v.addLayout(row)
        v.addStretch()
        return w

    @RF.busy
    def robot_to_etabs(self):
        from rf import rob

        r = rob.connect(start=False, require_project=True)
        e = self.robot()
        nodes, bars = r.nodes(), r.bars()
        secs = {i["name"]: i for i in r.sections_info()}
        zs = sorted({round(p[2], 3) for p in nodes.values()})
        if self.ri_story.isChecked() and len(zs) > 1:
            hs = [b - a for a, b in zip(zs, zs[1:])]
            e.set_stories([f"N{i + 1}" for i in range(len(hs))], hs, zs[0])
        mat, fc = self.global_material()
        e.ensure_concrete(mat, fc)
        self.steel(e)
        st = e.ensure_steel("S275", 275)
        made = {}
        for sname, inf in secs.items():
            try:
                if inf["kind"] in ("col", "beam") and inf.get("b"):
                    made[sname] = e.ensure_rect(sname, inf["b"], inf["h"], inf["kind"], mat)
                elif inf.get("d"):
                    made[sname] = e.ensure_circ(sname, inf["d"], mat)
                else:
                    res = e.m.PropFrame.ImportProp(sname, st, "Euro.xml", sname.replace(" ", ""), -1, "", "")
                    if (res[0] if isinstance(res, tuple) else res) == 0:
                        made[sname] = sname
            except Exception as ex:  # noqa: BLE001
                self.log(f"  section {sname} : {ex}")
        name_of = {}
        for b, d in bars.items():
            prop = made.get(d["section"])
            if not prop:
                continue
            name_of[b] = e.add_frame(nodes[d["n1"]], nodes[d["n2"]], prop, d.get("gamma", 0.0))
        sup = set(r.supported_nodes())
        done = 0
        for b, nm in name_of.items():
            d = bars[b]
            pa, pb = e.frame_points(nm)
            for n, p in ((d["n1"], pa), (d["n2"], pb)):
                if n in sup:
                    e.restrain(p, (True,) * 6)
                    done += 1
        self.log(f"✔ Robot → ETABS : {len(name_of)} barres, {len(made)} sections, {done} appuis "
                 f"({len(bars) - len(name_of)} barres sans section transférable).")
        e.refresh()


def force_light(app):
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except Exception:  # noqa: BLE001
        pass
    from PySide6.QtGui import QColor, QPalette

    p = QPalette()
    for role, col in ((QPalette.Window, "#f0f0f0"), (QPalette.WindowText, "#1a1a1a"), (QPalette.Base, "#ffffff"),
                      (QPalette.AlternateBase, "#f5f7fa"), (QPalette.Text, "#1a1a1a"), (QPalette.Button, "#e8e8e8"),
                      (QPalette.ButtonText, "#1a1a1a"), (QPalette.Highlight, "#3d7cc9"),
                      (QPalette.HighlightedText, "#ffffff"), (QPalette.ToolTipBase, "#ffffe1"),
                      (QPalette.ToolTipText, "#1a1a1a"), (QPalette.PlaceholderText, "#808080")):
        p.setColor(role, QColor(col))
    app.setPalette(p)


def main():
    """No argument / --ribbon : ruban ancré sur ETABS.  --tab <texte> : fenêtre complète sur cet onglet.
    --full : fenêtre complète seule."""
    from ef import ribbon as RB

    args = sys.argv[1:]
    req = "ribbon"
    if "--tab" in args and args.index("--tab") + 1 < len(args):
        req = "tab:" + args[args.index("--tab") + 1]
    elif "--full" in args:
        req = "tab:Plan"
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    force_light(app)                                    # light, like ETABS (ignore Windows dark mode)
    if RB.forward_to_running(req):          # an instance is already open → hand over and quit
        return
    app.setQuitOnLastWindowClosed(False)
    w = EMain()
    holder = {}

    def ribbon():
        if "rb" not in holder:
            holder["rb"] = RB.Ribbon(w)
            w._ribbon = holder["rb"]
        return holder["rb"]

    w._srv = RB.start_server(w, ribbon)
    RB.handle_request(w, ribbon, req)

    def on_main_close(ev, _orig=w.closeEvent):
        _orig(ev)
        if not ("rb" in holder and holder["rb"].isVisible()):
            app.quit()
    w.closeEvent = on_main_close
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
