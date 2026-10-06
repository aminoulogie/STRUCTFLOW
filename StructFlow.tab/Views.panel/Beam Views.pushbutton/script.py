# -*- coding: utf-8 -*-
"""Create a long section and cross sections for each selected beam,
with your chosen section type, view templates, scales, tags, multi-rebar
annotations, lap dimensions and labels."""
__title__ = "Beam\nViews"

import os

from pyrevit import forms, revit, script
from Autodesk.Revit.DB import BuiltInCategory, SubTransaction, Transaction, ViewPlan

import sf_common as common
import sf_views as sv

doc, uidoc = revit.doc, revit.uidoc
NONE = "(none)"
DEFAULT = "(default)"
LAST = "(last used)"

NUM = ["margin", "sec_offset", "sec_depth"]
SCALES = ["scale_elev", "scale_section"]
SLIDERS = ["raise_elev", "raise_sec"]
TEXT = ["elev_name", "sec_name", "lap_suffix"]
BOOLS = ["make_elev", "sec_start", "sec_mid", "sec_end", "per_span", "replace_old",
         "other_main", "other_links", "unobscure", "fine",
         "tag_leader", "link_mra", "lap_dims", "grid_dims",
         "label_plan", "mark_labels", "label_view", "avoid_clash"]


class ViewsWindow(forms.WPFWindow):
    def __init__(self, n_beams):
        forms.WPFWindow.__init__(self, os.path.join(os.path.dirname(__file__), "ui.xaml"))
        self.result = None
        self._loading = True
        self.info.Text = "{} beam(s) selected.".format(n_beams)
        rebar_tags = sorted(sv.tag_types(doc, BuiltInCategory.OST_RebarTags))
        texts = [DEFAULT] + sorted(sv.text_types(doc))
        self.lists = {
            "section_type": sorted(sv.section_types(doc)),
            "template_elev": [NONE] + sorted(sv.section_templates(doc)),
            "template_section": [NONE] + sorted(sv.section_templates(doc)),
            "beam_tag": [NONE] + sorted(sv.tag_types(doc, BuiltInCategory.OST_StructuralFramingTags)),
            "bar_tag": [NONE] + rebar_tags,
            "link_tag": [NONE] + rebar_tags,
            "mra_type": sorted(sv.mra_types(doc)) or [NONE],
            "lap_dim_type": [DEFAULT] + sorted(sv.linear_dim_types(doc)),
            "label_type": texts,
            "title_type": texts,
        }
        for key, items in self.lists.items():
            for it in items:
                getattr(self, key).Items.Add(it)
        for key in SCALES:
            for sc in ("10", "20", "25", "50", "100"):
                getattr(self, key).Items.Add(sc)
        for _, label in sv.LINK_MODES:
            self.elev_links.Items.Add(label)
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
        for key in SLIDERS:
            getattr(self, key).Value = float(s[key])
        for key in TEXT:
            getattr(self, key).Text = s[key]
        for key in BOOLS:
            getattr(self, key).IsChecked = bool(s[key])
        modes = [k for k, _ in sv.LINK_MODES]
        self.elev_links.SelectedIndex = modes.index(s["elev_links"]) if s["elev_links"] in modes else 0

    def _read(self):
        s = dict(sv.DEFAULTS)
        for key in self.lists:
            val = getattr(self, key).SelectedItem
            s[key] = "" if val in (None, NONE, DEFAULT) else val
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
        for key in SLIDERS:
            s[key] = int(round(getattr(self, key).Value))
        for key in TEXT:
            s[key] = getattr(self, key).Text
        for key in BOOLS:
            s[key] = bool(getattr(self, key).IsChecked)
        s["elev_links"] = sv.LINK_MODES[max(self.elev_links.SelectedIndex, 0)][0]
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
        out = script.get_output()
        total = 0
        t = Transaction(doc, "StructFlow Beam Views")
        t.Start()
        look = sv.resolve(doc, s)
        letters = sv.assign_letters(doc, beams)
        beams.sort(key=lambda b: letters[b.Id])
        plan = revit.active_view if isinstance(revit.active_view, ViewPlan) else None
        if s["label_plan"] and plan is None:
            print("note: open a plan view and run again to get names next to the section marks.")
        ctx = sv.new_context(doc, plan)
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
