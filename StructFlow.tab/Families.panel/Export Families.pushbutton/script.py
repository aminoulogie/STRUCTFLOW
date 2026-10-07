# -*- coding: utf-8 -*-
"""Export families to a folder: pick families and their types one by one,
concrete grades (one file per grade), graphic style, and the naming
(EPL_<CODE>_<Element>_<Variant>_<Material>) and folder layout.
The model itself is not changed."""
__title__ = "Export\nFamilies"

import os

from pyrevit import forms, revit, script
from System.Windows.Controls import CheckBox

import sf_families as sf
import sf_graphics as sg

doc = revit.doc
ALL = "(all categories)"
KEEP = "Keep as it is"
NAMINGS = ["EPL standard  (Company_Code_Element_Variant_Material)", "Keep the family names"]
FOLDERS = ["EPL library folders (01_ANNOTATION, 03_STRUCTURAL\\01_COLUMNS...)",
           "One folder per category", "All in one folder"]


def material_for(key, grade):
    m = sg.default_material(key)
    fck, ecm = [(f, e) for g, f, e in sg.GRADES if g == grade][0]
    old = m["grade"]
    m.update({"grade": grade, "fck": fck, "ecm": ecm,
              "name": m["name"].replace(old, grade), "description": m["description"].replace(old, grade)})
    return m


class ExportWindow(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, os.path.join(os.path.dirname(__file__), "ui.xaml"))
        self.result = None
        self.lib = sf.load_library()
        groups = sf.exportable_families(doc)
        self.fams = [f for cat in sorted(groups) for f in groups[cat]]
        self.checked = set()
        self.types = dict((f.Id, set(self._type_names(f))) for f in self.fams)
        self.current = None
        self._busy = False

        self.category.Items.Add(ALL)
        for cat in sorted(groups):
            self.category.Items.Add(cat)
        for g, _, _ in sg.GRADES:
            cb = CheckBox()
            cb.Content = g
            cb.Click += self.refresh_names
            self.grades.Children.Add(cb)
        self.graphics.Items.Add(KEEP)
        for name in sg.PRESETS:
            self.graphics.Items.Add(name)
        self.graphics.SelectedIndex = 0
        for n in NAMINGS:
            self.naming.Items.Add(n)
        for f in FOLDERS:
            self.folders.Items.Add(f)
        self.folders.SelectedIndex = 0
        self.company.Text = "EPL"
        self.root.Text = os.path.join(os.environ["USERPROFILE"], "Desktop", "EPL_FAMILIES")
        self.naming.SelectedIndex = 0
        self.category.SelectedIndex = 0

    # ------------------------------------------------------- families
    def _type_names(self, f):
        return sorted(sf.br.ename(doc.GetElement(i)) for i in f.GetFamilySymbolIds())

    def _visible(self):
        cat, text = self.category.SelectedItem, (self.search.Text or "").lower()
        return [f for f in self.fams
                if (cat in (None, ALL) or (f.FamilyCategory and f.FamilyCategory.Name == cat))
                and text in f.Name.lower()]

    def _fill_families(self):
        self.families.Items.Clear()
        for f in self._visible():
            cb = CheckBox()
            cb.Content = "%s   [%s]" % (f.Name, f.FamilyCategory.Name if f.FamilyCategory else "?")
            cb.Tag = f
            cb.IsChecked = f.Id in self.checked
            cb.Click += self._family_ticked
            self.families.Items.Add(cb)
        self.refresh_names(None, None)

    def _family_ticked(self, sender, args, bulk=False):
        f = sender.Tag
        if sender.IsChecked:
            self.checked.add(f.Id)
            if not self.types[f.Id]:
                self.types[f.Id] = set(self._type_names(f))
        else:
            self.checked.discard(f.Id)
        if not bulk:
            self.families.SelectedItem = sender
            self.refresh_names(None, None)

    def category_changed(self, sender, args):
        self._fill_families()

    def search_changed(self, sender, args):
        self._fill_families()

    def family_selected(self, sender, args):
        item = self.families.SelectedItem
        if item is None:
            return
        f = item.Tag
        self.current = f
        self.types_title.Text = "Types of %s (tick the ones to export)" % f.Name
        self.types_list_fill(f)

    def types_list_fill(self, f):
        lst = self.types_list
        lst.Items.Clear()
        for name in self._type_names(f):
            cb = CheckBox()
            cb.Content = name
            cb.IsChecked = name in self.types[f.Id]
            cb.Click += self._type_ticked
            lst.Items.Add(cb)

    def _type_ticked(self, sender, args):
        f = self.current
        if f is None:
            return
        name = str(sender.Content)
        if sender.IsChecked:
            self.types[f.Id].add(name)
            self.checked.add(f.Id)
        else:
            self.types[f.Id].discard(name)
            if not self.types[f.Id]:
                self.checked.discard(f.Id)
        for cb in self.families.Items:
            if cb.Tag.Id == f.Id:
                cb.IsChecked = f.Id in self.checked
        self.refresh_names(None, None)

    def _families_all(self, value):
        for cb in list(self.families.Items):
            cb.IsChecked = value
            self._family_ticked(cb, None, bulk=True)
        self.refresh_names(None, None)

    def _types_all(self, value):
        for cb in list(self.types_list.Items):
            cb.IsChecked = value
            self._type_ticked(cb, None)

    def fam_all(self, sender, args):
        self._families_all(True)

    def fam_none(self, sender, args):
        self._families_all(False)

    def type_all(self, sender, args):
        self._types_all(True)

    def type_none(self, sender, args):
        self._types_all(False)

    def grade_all(self, sender, args):
        for cb in self.grades.Children:
            cb.IsChecked = True
        self.refresh_names(None, None)

    def grade_none(self, sender, args):
        for cb in self.grades.Children:
            cb.IsChecked = False
        self.refresh_names(None, None)

    # --------------------------------------------------------- naming
    def naming_changed(self, sender, args):
        epl = self.naming.SelectedIndex == 0
        for name in ("n_company", "n_code", "n_element", "n_variant"):
            getattr(self, name).IsChecked = epl
        self.n_material.IsChecked = True
        self.refresh_names(None, None)

    def browse(self, sender, args):
        folder = forms.pick_folder(title="Folder to save the families in")
        if folder:
            self.root.Text = folder

    def _opts(self):
        return {"rename": self.naming.SelectedIndex == 0 or any(
                    getattr(self, n).IsChecked for n in ("n_company", "n_code", "n_element", "n_variant")),
                "company": self.company.Text.strip() if self.n_company.IsChecked else "",
                "code": bool(self.n_code.IsChecked), "element": bool(self.n_element.IsChecked),
                "variant": bool(self.n_variant.IsChecked), "material": bool(self.n_material.IsChecked)}

    def _grades(self):
        return [str(cb.Content) for cb in self.grades.Children if cb.IsChecked]

    def jobs(self):
        opts, grades, out = self._opts(), self._grades(), []
        gname = self.graphics.SelectedItem
        root = self.root.Text.strip()
        for f in self.fams:
            if f.Id not in self.checked:
                continue
            cat = f.FamilyCategory.Name if f.FamilyCategory else "Other"
            key = sf.MATERIAL_KEY.get(cat)
            graphics = sg.PRESETS[gname][key] if key and gname in sg.PRESETS else None
            names = set(self._type_names(f))
            types = None if self.types[f.Id] >= names else set(self.types[f.Id])
            for grade in (grades if key and grades else [None]):
                fname = sf.build_name(f, opts, grade, self.lib) + ".rfa"
                if self.folders.SelectedIndex == 0:
                    sub = sf.library_folder(f, self.lib)
                elif self.folders.SelectedIndex == 1:
                    sub = sf._safe(cat)
                else:
                    sub = ""
                out.append({"family": f, "types": types, "key": key,
                            "material": material_for(key, grade) if grade else None,
                            "graphics": graphics, "path": os.path.join(root, sub, fname),
                            "show": os.path.join(sub, fname) + (
                                "   (%d of %d types)" % (len(types), len(names)) if types is not None else "")})
        return out

    def refresh_names(self, sender, args):
        if not hasattr(self, "fams"):
            return
        try:
            jobs = self.jobs()
        except Exception:
            return
        self.preview.Items.Clear()
        for j in jobs[:500]:
            self.preview.Items.Add(j["show"])
        self.summary.Text = "%d families ticked, %d files" % (len(self.checked), len(jobs))

    # ------------------------------------------------------------ run
    def ok_click(self, sender, args):
        jobs = self.jobs()
        if not jobs:
            forms.alert("Tick at least one family (tab 1).")
            return
        if not self.root.Text.strip():
            forms.alert("Choose where to save (tab 4).")
            return
        self.result = jobs
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()


win = ExportWindow()
win.ShowDialog()
if win.result:
    log = []
    done = sf.export_jobs(doc, win.result, log.append)
    out = script.get_output()
    for line in log:
        print(line)
    print("\nDone: {} of {} files saved. Your model was not changed.".format(done, len(win.result)))
