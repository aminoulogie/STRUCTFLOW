"""« Note de calcul » tab shared by the footing and column apps: tick the chapters, choose the style of each
chapter (equations / tables / Excel-like grid / plain), tick the columns printed for each chapter, show or hide the numerical applications, enter the loads table
[DTR B.C. 2.2] and (footings) the soil-report data."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

STYLES = [("latex", "Équations (LaTeX)"), ("tables", "Tableaux"), ("excel", "Tableau Excel (style feuille de calcul)"),
          ("plain", "Texte simple")]
INHERIT = ("", "↳ comme le chapitre parent")
CHARGE_COLS = ["Plancher", "Désignation", "e (m)", "ρ (kN/m³)", "Poids (kN/m²)", "Nature"]
SOIL_FIELDS = ["Coefficient de réaction du sol", "Tassement", "Agressivité du sol", "Teneur en sulfates",
               "Classe d'exposition"]
NO_STYLE = {"cover", "toc"}
# tick columns of the tree: what each chapter prints for every calculation line
COL_FLAGS = [(2, "sym", "Formule"), (3, "num", "Appl. num."), (4, "res", "Résultat"), (5, "ok", "Vérif.")]


class NoteTab(QWidget):
    def __init__(self, sections, table_cls, export_cb, soil_fields=False):
        super().__init__()
        self.sections = sections
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Style par défaut :"))
        self.style = QComboBox()
        for k, t in STYLES:
            self.style.addItem(t, k)
        top.addWidget(self.style)
        b = QPushButton("Appliquer ce style à tous les chapitres")
        b.clicked.connect(self.apply_style_all)
        top.addWidget(b)
        self.show_num = QCheckBox("Applications numériques")
        self.show_num.setChecked(True)
        self.show_num.setToolTip("Coche / décoche la colonne « Appl. num. » de tous les chapitres.")
        self.show_num.toggled.connect(lambda v: self.set_col("num", v))
        top.addWidget(self.show_num)
        for txt, val in (("Tout cocher", True), ("Tout décocher", False)):
            b = QPushButton(txt)
            b.clicked.connect(lambda _=False, v=val: self.set_all(v))
            top.addWidget(b)
        b = QPushButton("📝 Exporter la note Word…")
        b.setStyleSheet("font-weight:bold; padding:6px 18px;")
        b.clicked.connect(export_cb)
        top.addWidget(b)
        top.addStretch()
        lay.addLayout(top)
        sp = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2 + len(COL_FLAGS))
        self.tree.setHeaderLabels(["Contenu de la note (cocher les titres à imprimer)", "Style du chapitre"]
                                  + [t for _, _, t in COL_FLAGS])
        self.tree.headerItem().setToolTip(2, "Cocher les colonnes à imprimer pour chaque ligne de calcul du chapitre "
                                             "(valable pour tous les styles). Un chapitre transmet son choix à ses sous-chapitres.")
        self.tree.setColumnWidth(0, 330)
        self.tree.setColumnWidth(1, 230)
        for c, _, _ in COL_FLAGS:
            self.tree.setColumnWidth(c, 78)
        self.items, self.combos = {}, {}
        parent = None
        for key, label, level in sections:
            it = QTreeWidgetItem([label, ""] + [""] * len(COL_FLAGS))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(0, Qt.Checked)
            if key not in NO_STYLE:
                for c, _, _ in COL_FLAGS:
                    it.setCheckState(c, Qt.Checked)
            it.setData(0, Qt.UserRole, key)
            if level == 1:
                self.tree.addTopLevelItem(it)
                parent = it
            else:
                (parent or self.tree.invisibleRootItem()).addChild(it)
            self.items[key] = it
        for key, label, level in sections:
            if key in NO_STYLE:
                continue
            cb = QComboBox()
            cb.addItem(INHERIT[1], INHERIT[0])
            for k, t in STYLES:
                cb.addItem(t, k)
            self.tree.setItemWidget(self.items[key], 1, cb)
            self.combos[key] = cb
        self.tree.expandAll()
        self.tree.itemChanged.connect(self._propagate)
        sp.addWidget(self.tree)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(QLabel("<b>Charges permanentes et surcharges [DTR B.C. 2.2]</b> – facultatif (imprimé s'il est rempli). "
                            "Poids vide = e × ρ. Nature Q = surcharge."))
        self.charges = table_cls(CHARGE_COLS, {"Nature": ["G", "Q"]})
        rl.addWidget(self.charges, 1)
        self.soil = {}
        if soil_fields:
            g = QGroupBox("Données du rapport de sol (imprimées dans « Caractéristiques du site »)")
            fl = QFormLayout(g)
            for f in SOIL_FIELDS:
                le = QLineEdit()
                self.soil[f] = le
                fl.addRow(f, le)
            rl.addWidget(g)
        sp.addWidget(right)
        sp.setSizes([620, 700])
        lay.addWidget(sp, 1)

    def _propagate(self, item, col):
        if item.childCount() and (col == 0 or col >= 2):
            self.tree.blockSignals(True)
            for i in range(item.childCount()):
                item.child(i).setCheckState(col, item.checkState(col))
            self.tree.blockSignals(False)

    def set_col(self, flag, on):
        c = next(c for c, f, _ in COL_FLAGS if f == flag)
        self.tree.blockSignals(True)
        for k, it in self.items.items():
            if k not in NO_STYLE:
                it.setCheckState(c, Qt.Checked if on else Qt.Unchecked)
        self.tree.blockSignals(False)

    def cols_map(self):
        return {k: {f: it.checkState(c) == Qt.Checked for c, f, _ in COL_FLAGS}
                for k, it in self.items.items() if k not in NO_STYLE}

    def set_all(self, on):
        for it in self.items.values():
            it.setCheckState(0, Qt.Checked if on else Qt.Unchecked)

    def apply_style_all(self):
        for cb in self.combos.values():
            cb.setCurrentIndex(0)  # inherit → default style

    def selected(self):
        return {k for k, it in self.items.items() if it.checkState(0) == Qt.Checked}

    def options(self):
        """Keyword arguments for engine.report.build_docx."""
        sel = self.selected()
        style = self.style.currentData()
        smap = {k: cb.currentData() for k, cb in self.combos.items() if cb.currentData()}
        return dict(selected=sel - NO_STYLE, cover="cover" in sel, toc="toc" in sel, style=style,
                    equations=style == "latex", style_map=smap, show_num=self.show_num.isChecked(),
                    cols_map=self.cols_map())

    def soil_extra(self):
        return {k: le.text() for k, le in self.soil.items() if le.text().strip()}

    def state(self):
        return dict(sel=sorted(self.selected()), style=self.style.currentData(), charges=self.charges.records(),
                    soil={k: le.text() for k, le in self.soil.items()}, show_num=self.show_num.isChecked(),
                    smap={k: cb.currentData() for k, cb in self.combos.items()},
                    cols={k: [v[f] for _, f, _ in COL_FLAGS] for k, v in self.cols_map().items()})

    def load(self, d):
        if not d:
            return
        sel = set(d.get("sel", []))
        if sel:
            self.tree.blockSignals(True)
            for k, it in self.items.items():
                it.setCheckState(0, Qt.Checked if k in sel else Qt.Unchecked)
            self.tree.blockSignals(False)
        i = self.style.findData(d.get("style", "latex"))
        self.style.setCurrentIndex(max(i, 0))
        self.show_num.blockSignals(True)
        self.show_num.setChecked(d.get("show_num", True))
        self.show_num.blockSignals(False)
        self.tree.blockSignals(True)
        for k, flags in (d.get("cols") or {}).items():
            if k in self.items:
                for (c, _, _), v in zip(COL_FLAGS, flags):
                    self.items[k].setCheckState(c, Qt.Checked if v else Qt.Unchecked)
        self.tree.blockSignals(False)
        for k, v in (d.get("smap") or {}).items():
            if k in self.combos:
                self.combos[k].setCurrentIndex(max(self.combos[k].findData(v), 0))
        self.charges.set_records(d.get("charges", []))
        for k, v in d.get("soil", {}).items():
            if k in self.soil:
                self.soil[k].setText(v)
