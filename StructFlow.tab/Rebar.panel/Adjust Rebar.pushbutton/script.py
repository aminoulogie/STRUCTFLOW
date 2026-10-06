# -*- coding: utf-8 -*-
"""Change A / C legs, bar counts, covers, laps... on beams that already
have StructFlow rebar. Empty fields keep each beam's own value."""
__title__ = "Adjust\nRebar"

import os

from pyrevit import forms, revit
from Autodesk.Revit.DB.Structure import RebarBarType

import sf_beamrebar as br
import sf_common as common

doc, uidoc = revit.doc, revit.uidoc
KEEP = "(keep)"
NUM = ["top_A", "top_C", "bot_A", "bot_C", "cover_top", "cover_bottom", "cover_side",
       "cover_end", "lap_factor", "stock", "link_spacing"]
INT = ["top_n", "bot_n"]
SPLICES = [KEEP, "Reset to automatic zones"]


class AdjustWindow(forms.WPFWindow):
    def __init__(self, beams):
        forms.WPFWindow.__init__(self, os.path.join(os.path.dirname(__file__), "ui.xaml"))
        self.result = None
        self.info.Text = "{} beam(s) with StructFlow rebar selected.".format(len(beams))
        bars = br.names_of(doc, RebarBarType)
        for key in ("top_type", "bot_type"):
            getattr(self, key).Items.Add(KEEP)
            for b in bars:
                getattr(self, key).Items.Add(b)
            getattr(self, key).SelectedIndex = 0
        for v in (KEEP, "Yes", "No"):
            self.full_length.Items.Add(v)
        self.full_length.SelectedIndex = 0
        for v in SPLICES:
            self.splices.Items.Add(v)
        self.splices.SelectedIndex = 0
        if len(beams) == 1:
            # one beam: show its current values as hints
            s = br.load_beam_settings(beams[0])
            for key in NUM + INT:
                getattr(self, key).ToolTip = "current: {:g}".format(s[key])

    def _read(self):
        ch = {}
        for key in NUM + INT:
            txt = getattr(self, key).Text.strip()
            if not txt:
                continue
            try:
                ch[key] = int(txt) if key in INT else float(txt)
            except ValueError:
                raise ValueError("'{}' must be a number".format(key))
        for key in ("top_type", "bot_type"):
            if getattr(self, key).SelectedItem != KEEP:
                ch[key] = getattr(self, key).SelectedItem
        if self.full_length.SelectedItem != KEEP:
            ch["full_length"] = self.full_length.SelectedItem == "Yes"
        if self.splices.SelectedItem != KEEP:
            ch["top_splices"] = ch["bot_splices"] = None
        return ch

    def ok_click(self, sender, args):
        try:
            self.result = self._read()
        except ValueError as ex:
            forms.alert(str(ex), title="StructFlow Adjust Rebar")
            return
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()


beams = [b for b in common.pick_beams(uidoc) if br.load_beam_settings(b)]
if not beams:
    forms.alert("Select beams that already have StructFlow rebar (use Beam Rebar first).",
                title="StructFlow Adjust Rebar")
else:
    win = AdjustWindow(beams)
    win.ShowDialog()
    if win.result is not None:
        if not win.result:
            forms.alert("Nothing changed.", title="StructFlow Adjust Rebar")
        else:
            jobs = []
            for b in beams:
                s = br.load_beam_settings(b)
                s.update(win.result)
                jobs.append((b, s))
            common.run(doc, revit.active_view, jobs, "StructFlow Adjust Rebar")
