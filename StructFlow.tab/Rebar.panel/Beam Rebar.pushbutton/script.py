# -*- coding: utf-8 -*-
"""Place top/bottom bars, laps and links in selected concrete beams.
Settings are saved on each beam so 'Rebuild' can regenerate them."""
__title__ = "Beam\nRebar"

import os

from pyrevit import forms, revit
from Autodesk.Revit.DB.Structure import RebarBarType, RebarHookType

import sf_beamrebar as br
import sf_common as common

doc, uidoc = revit.doc, revit.uidoc

NUM_FIELDS = ["cover_top", "cover_bottom", "cover_side", "cover_end", "end_ext",
              "top_A", "top_C", "bot_A", "bot_C", "link_spacing", "link_offset"]
INT_FIELDS = ["top_n", "bot_n"]
TEXT_FIELDS = ["top_zones", "bot_zones"]
COMMENT_FIELDS = ["top_comment", "top_partition", "bot_comment", "bot_partition",
                  "link_comment", "link_partition"]
COMBO_NUM = {"lap_factor": ["50", "60"], "stock": ["6000", "12000"]}
PRIORITY = [("auto", "Automatic (beam that cuts / deeper beam is main)"),
            ("horizontal", "Horizontal beams continuous, vertical beams stop"),
            ("vertical", "Vertical beams continuous, horizontal beams stop")]
BOOL_FIELDS = ["links_on", "link_flip", "primary", "stop_cols", "full_length"]


class BeamRebarWindow(forms.WPFWindow):
    def __init__(self, s, n_beams):
        forms.WPFWindow.__init__(self, os.path.join(os.path.dirname(__file__), "ui.xaml"))
        self.result = None
        self.info.Text = ("{} beam(s) selected. Existing StructFlow auto-rebar in them will be "
                          "replaced; manually drawn rebar is not touched.".format(n_beams))
        bars = br.names_of(doc, RebarBarType)
        for key in ("top_type", "bot_type", "link_type"):
            combo = getattr(self, key)
            for b in bars:
                combo.Items.Add(b)
            combo.SelectedItem = s[key] if s[key] in bars else (bars[0] if bars else None)
        self.link_hook.Items.Add("(none)")
        for h in br.names_of(doc, RebarHookType):
            self.link_hook.Items.Add(h)
        self.link_hook.SelectedItem = s["link_hook"] or "(none)"
        for key, label in PRIORITY:
            self.link_priority.Items.Add(label)
        self.link_priority.SelectedIndex = [k for k, _ in PRIORITY].index(s.get("link_priority", "auto"))
        for key, label in br.DISPLAY_MODES:
            self.display.Items.Add(label)
        self.display.SelectedIndex = [k for k, _ in br.DISPLAY_MODES].index(s["display"])

        for key in NUM_FIELDS + INT_FIELDS:
            getattr(self, key).Text = "{:g}".format(s[key])
        for key in TEXT_FIELDS:
            getattr(self, key).Text = s[key]
        for key in COMMENT_FIELDS:
            getattr(self, key).Text = s.get(key) or ""
        for key, choices in COMBO_NUM.items():
            combo = getattr(self, key)
            for c in choices:
                combo.Items.Add(c)
            combo.Text = "{:g}".format(s[key])
        for key in BOOL_FIELDS:
            getattr(self, key).IsChecked = bool(s[key])

    def _read(self):
        s = dict(br.DEFAULTS)
        for key in NUM_FIELDS + list(COMBO_NUM):
            try:
                s[key] = float(getattr(self, key).Text)
            except ValueError:
                raise ValueError("'{}' must be a number".format(key))
        for key in INT_FIELDS:
            try:
                s[key] = int(getattr(self, key).Text)
            except ValueError:
                raise ValueError("'{}' must be a whole number".format(key))
        for key in TEXT_FIELDS:
            s[key] = getattr(self, key).Text.strip()
            try:
                for part in s[key].replace(";", ",").split(","):
                    if part.strip():
                        a, b = [float(x) for x in part.split("-")]
            except ValueError:
                raise ValueError("splice zones must look like 2000-3500, 7000-8200")
        for key in COMMENT_FIELDS:
            s[key] = getattr(self, key).Text.strip()
        for key in ("top_type", "bot_type", "link_type"):
            s[key] = getattr(self, key).SelectedItem
        hook = self.link_hook.SelectedItem
        s["link_hook"] = "" if hook == "(none)" else hook
        s["display"] = br.DISPLAY_MODES[self.display.SelectedIndex][0]
        s["link_priority"] = PRIORITY[self.link_priority.SelectedIndex][0]
        for key in BOOL_FIELDS:
            s[key] = bool(getattr(self, key).IsChecked)
        if s["lap_factor"] <= 0 or s["stock"] <= 0 or s["link_spacing"] <= 0:
            raise ValueError("lap factor, stock length and spacing must be positive")
        return s

    def ok_click(self, sender, args):
        try:
            self.result = self._read()
        except ValueError as ex:
            forms.alert(str(ex), title="StructFlow Beam Rebar")
            return
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()


beams = common.pick_beams(uidoc)
if beams:
    stored = br.load_beam_settings(beams[0]) if len(beams) == 1 else None
    win = BeamRebarWindow(stored or common.load_last(), len(beams))
    win.ShowDialog()
    if win.result:
        common.save_last(win.result)
        common.run(doc, revit.active_view, [(b, win.result) for b in beams], "StructFlow Beam Rebar")
