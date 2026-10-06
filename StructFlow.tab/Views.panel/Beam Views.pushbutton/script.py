# -*- coding: utf-8 -*-
"""Create a long section and cross sections for each selected beam,
with your chosen section type, view templates, scales and tags."""
__title__ = "Beam\nViews"

import os

from pyrevit import forms, revit, script
from Autodesk.Revit.DB import BuiltInCategory, SubTransaction, Transaction, ViewPlan

import sf_common as common
import sf_views as sv

doc, uidoc = revit.doc, revit.uidoc
NONE = "(none)"
LAST = "(last used)"

NUM = ["margin", "sec_offset", "sec_depth"]
SCALES = ["scale_elev", "scale_section"]
TEXT = ["elev_name", "sec_name"]
BOOLS = ["make_elev", "sec_start", "sec_mid", "sec_end", "per_span",
         "tag_leader", "unobscure", "fine", "replace_old",
         "label_plan", "label_view", "grid_dims", "avoid_clash"]


class ViewsWindow(forms.WPFWindow):
    def __init__(self, n_beams):
        forms.WPFWindow.__init__(self, os.path.join(os.path.dirname(__file__), "ui.xaml"))
        self.result = None
        self._loading = True
        self.info.Text = "{} beam(s) selected.".format(n_beams)
        self.lists = {
            "section_type": sorted(sv.section_types(doc)),
            "template_elev": [NONE] + sorted(sv.section_templates(doc)),
            "template_section": [NONE] + sorted(sv.section_templates(doc)),
            "beam_tag": [NONE] + sorted(sv.tag_types(doc, BuiltInCategory.OST_StructuralFramingTags)),
            "bar_tag": [NONE] + sorted(sv.tag_types(doc, BuiltInCategory.OST_RebarTags)),
            "link_tag": [NONE] + sorted(sv.tag_types(doc, BuiltInCategory.OST_RebarTags)),
        }
        for key, items in self.lists.items():
            for it in items:
                getattr(self, key).Items.Add(it)
        for key in SCALES:
            for sc in ("10", "20", "25", "50", "100"):
                getattr(self, key).Items.Add(sc)
        self.preset.Items.Add(LAST)
        for name in sorted(sv.load_presets()):
            if name != LAST:
                self.preset.Items.Add(name)
        self.preset.SelectedItem = LAST
        self._fill(sv.preset(LAST))
        self._loading = False

    def _fill(self, s):
        for key, items in self.lists.items():
            combo = getattr(self, key)
            combo.SelectedItem = s[key] if s[key] in items else (items[0] if items else None)
        for key in NUM:
            getattr(self, key).Text = "{:g}".format(s[key])
        for key in SCALES:
            getattr(self, key).Text = str(int(s[key]))
        for key in TEXT:
            getattr(self, key).Text = s[key]
        for key in BOOLS:
            getattr(self, key).IsChecked = bool(s[key])

    def _read(self):
        s = dict(sv.DEFAULTS)
        for key in self.lists:
            val = getattr(self, key).SelectedItem
            s[key] = "" if val in (None, NONE) else val
        if not s["section_type"]:
            raise ValueError("This model has no section view type.")
        for key in NUM:
            try:
                s[key] = float(getattr(self, key).Text)
            except ValueError:
                raise ValueError("'{}' must be a number".format(key))
        for key in SCALES:
            try:
                s[key] = int(getattr(self, key).Text)
            except ValueError:
                raise ValueError("scale must be a whole number, e.g. 20 for 1:20")
            if s[key] <= 0:
                raise ValueError("scale must be positive")
        for key in TEXT:
            s[key] = getattr(self, key).Text
        for key in BOOLS:
            s[key] = bool(getattr(self, key).IsChecked)
        return s

    def preset_changed(self, sender, args):
        if not self._loading and self.preset.SelectedItem:
            self._fill(sv.preset(self.preset.SelectedItem))

    def save_click(self, sender, args):
        name = (self.preset.Text or "").strip()
        if not name or name == LAST:
            forms.alert("Type a name for this setup first (e.g. the client name).")
            return
        try:
            sv.save_preset(name, self._read())
        except ValueError as ex:
            forms.alert(str(ex))
            return
        if name not in list(self.preset.Items):
            self.preset.Items.Add(name)
        forms.alert("Setup '{}' saved.".format(name), title="StructFlow")

    def delete_click(self, sender, args):
        name = self.preset.Text
        if name and name != LAST and forms.alert("Delete setup '{}'?".format(name), yes=True, no=True):
            sv.delete_preset(name)
            self.preset.Items.Remove(name)
            self.preset.SelectedItem = LAST

    def ok_click(self, sender, args):
        try:
            self.result = self._read()
        except ValueError as ex:
            forms.alert(str(ex), title="StructFlow Beam Views")
            return
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()


beams = common.pick_beams(uidoc)
if beams:
    win = ViewsWindow(len(beams))
    win.ShowDialog()
    s = win.result
    if s:
        sv.save_preset(LAST, s)
        tags_f = sv.tag_types(doc, BuiltInCategory.OST_StructuralFramingTags)
        tags_r = sv.tag_types(doc, BuiltInCategory.OST_RebarTags)
        temps = sv.section_templates(doc)
        look = {
            "vft": sv.section_types(doc)[s["section_type"]],
            "t_elev": temps.get(s["template_elev"]),
            "t_sec": temps.get(s["template_section"]),
            "beam_tag": tags_f.get(s["beam_tag"]),
            "bar_tag": tags_r.get(s["bar_tag"]),
            "link_tag": tags_r.get(s["link_tag"]),
        }
        out = script.get_output()
        total = 0
        t = Transaction(doc, "StructFlow Beam Views")
        t.Start()
        letters = sv.assign_letters(doc, beams)
        plan = revit.active_view if isinstance(revit.active_view, ViewPlan) else None
        if s["label_plan"] and plan is None:
            print("note: open a plan view and run again to get names next to the section marks.")
        ctx = sv.new_context(doc, plan)
        beams.sort(key=lambda b: letters[b.Id])
        for beam in beams:
            warnings = []
            st = SubTransaction(doc)
            st.Start()
            try:
                views = sv.build_views(doc, beam, s, look, warnings.append, letters[beam.Id], ctx)
                st.Commit()
                total += len(views)
                print("{} : {}".format(out.linkify(beam.Id),
                                       ", ".join(out.linkify(v.Id, v.Name) for v in views)))
            except Exception as ex:
                st.RollBack()
                print("{} : SKIPPED - {}".format(out.linkify(beam.Id), ex))
            for w in warnings:
                print("    warning: " + w)
        t.Commit()
        print("\nDone: {} views created. Click a view name to open it.".format(total))
