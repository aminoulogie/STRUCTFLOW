# -*- coding: utf-8 -*-
"""Make many sizes at once: column / beam types from a list like
300x300, 300x400 ... or floor types from thicknesses like 150, 200."""
__title__ = "Type\nMaker"

import os

from pyrevit import forms, revit, script
from Autodesk.Revit.DB import Transaction
from System.Windows import Visibility

import sf_families as sf

doc = revit.doc


class TypeMakerWindow(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, os.path.join(os.path.dirname(__file__), "ui.xaml"))
        self.result = None
        for label, _ in sf.CATEGORIES:
            self.category.Items.Add(label)
        self.category.SelectedIndex = 0

    @property
    def is_floor(self):
        return self.category.SelectedIndex == 2

    def category_changed(self, sender, args):
        bic = sf.CATEGORIES[self.category.SelectedIndex][1]
        self.base.Items.Clear()
        if self.is_floor:
            self.choices = sf.floor_types(doc)
            self.base_label.Text = "Copy from floor type"
            self.param_panel.Visibility = Visibility.Collapsed
            self.pattern.Text = "Slab {t}mm"
            self.pattern_hint.Text = "{t} = thickness"
            self.sizes_hint.Text = ("Total thicknesses in mm, separated by commas or new lines "
                                    "(the structural layer takes up the difference):  150, 200, 250")
        else:
            self.choices = sf.families_of(doc, bic)
            self.base_label.Text = "Family"
            self.param_panel.Visibility = Visibility.Visible
            self.pattern.Text = "{b}x{h}"
            self.pattern_hint.Text = "{b} = width, {h} = depth"
            self.sizes_hint.Text = ("Sizes in mm as width x depth, separated by commas or new lines:  "
                                    "300x300, 300x400, 400x400, 400x600")
        for name in sorted(self.choices):
            self.base.Items.Add(name)
        if self.base.Items.Count:
            self.base.SelectedIndex = 0

    def base_changed(self, sender, args):
        if self.is_floor or self.base.SelectedItem is None:
            return
        sym = sf.first_symbol(doc, self.choices[self.base.SelectedItem])
        names = sf.length_params(sym) if sym else []
        for combo, wanted in ((self.p_w, ["b", "width", "w"]), (self.p_h, ["h", "depth", "d", "height"])):
            combo.Items.Clear()
            for n in names:
                combo.Items.Add(n)
            combo.SelectedItem = sf.guess(names, wanted)

    def ok_click(self, sender, args):
        if self.base.SelectedItem is None:
            forms.alert("Nothing to copy from: load a family of this category first.")
            return
        try:
            sizes = sf.parse_sizes(self.sizes.Text, not self.is_floor)
        except ValueError as ex:
            forms.alert(str(ex))
            return
        if not self.is_floor and (self.p_w.SelectedItem is None or self.p_h.SelectedItem is None):
            forms.alert("Pick the width and depth parameters.")
            return
        self.result = {
            "floor": self.is_floor, "base": self.choices[self.base.SelectedItem],
            "pattern": self.pattern.Text, "sizes": sizes, "update": bool(self.update.IsChecked),
            "p_w": self.p_w.SelectedItem, "p_h": self.p_h.SelectedItem,
        }
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()


win = TypeMakerWindow()
win.ShowDialog()
r = win.result
if r:
    out = script.get_output()
    log = []
    t = Transaction(doc, "StructFlow Type Maker")
    t.Start()
    try:
        if r["floor"]:
            sf.make_floor_types(doc, r["base"], r["pattern"], r["sizes"], r["update"], log.append)
        else:
            sf.make_family_types(doc, r["base"], r["pattern"], r["sizes"], r["p_w"], r["p_h"],
                                 r["update"], log.append)
        t.Commit()
    except Exception as ex:
        t.RollBack()
        log.append("STOPPED, nothing was changed: %s" % ex)
    for line in log:
        print(line)
