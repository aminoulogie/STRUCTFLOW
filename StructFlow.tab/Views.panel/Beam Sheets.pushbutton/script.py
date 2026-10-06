# -*- coding: utf-8 -*-
"""Put the StructFlow views of the selected beams on sheets: each beam's
long section followed by its cross sections, as many rows per sheet as
fit, new sheets as needed."""
__title__ = "Beam\nSheets"

import os

from pyrevit import forms, revit, script
from Autodesk.Revit.DB import Transaction

import sf_common as common
import sf_sheets as ss

doc, uidoc = revit.doc, revit.uidoc
DEFAULT = "(default)"
NUM = ["m_left", "m_right", "m_top", "m_bottom", "gap_x", "gap_y"]


class SheetsWindow(forms.WPFWindow):
    def __init__(self, n_beams, s):
        forms.WPFWindow.__init__(self, os.path.join(os.path.dirname(__file__), "ui.xaml"))
        self.result = None
        self.info.Text = "{} beam(s) selected.".format(n_beams)
        self.lists = {
            "title_block": sorted(ss.title_blocks(doc)),
            "vp_type": [DEFAULT] + sorted(ss.viewport_types(doc)),
            "align": ["Centre", "Top"],
        }
        for key, items in self.lists.items():
            combo = getattr(self, key)
            for it in items:
                combo.Items.Add(it)
            combo.SelectedItem = s[key] if s[key] in items else (items[0] if items else None)
        for key in NUM:
            getattr(self, key).Text = "{:g}".format(s[key])
        self.number_prefix.Text = s["number_prefix"]
        self.number_start.Text = str(int(s["number_start"]))
        self.sheet_name.Text = s["sheet_name"]

    def ok_click(self, sender, args):
        s = dict(ss.DEFAULTS)
        for key in self.lists:
            val = getattr(self, key).SelectedItem
            s[key] = "" if val in (None, DEFAULT) else val
        if not s["title_block"]:
            forms.alert("Load your A0 title block family into the project first.")
            return
        try:
            for key in NUM:
                s[key] = float(getattr(self, key).Text)
            s["number_start"] = int(self.number_start.Text)
        except ValueError:
            forms.alert("Margins, gaps and the start number must be numbers.")
            return
        s["number_prefix"] = self.number_prefix.Text
        s["sheet_name"] = self.sheet_name.Text
        self.result = s
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()


beams = common.pick_beams(uidoc)
if beams:
    win = SheetsWindow(len(beams), ss.load_settings())
    win.ShowDialog()
    s = win.result
    if s:
        ss.save_settings(s)
        out = script.get_output()
        warnings = []
        t = Transaction(doc, "StructFlow Beam Sheets")
        t.Start()
        try:
            sheets = ss.layout(doc, beams, s, warnings.append)
            t.Commit()
        except Exception as ex:
            t.RollBack()
            forms.alert(str(ex), title="StructFlow Beam Sheets")
            sheets = []
        for w in warnings:
            print("warning: " + w)
        for sh in sheets:
            print("{}  {} - {}".format(out.linkify(sh.Id), sh.SheetNumber, sh.Name))
        if sheets:
            print("\nDone: {} sheet(s). Click one to open it.".format(len(sheets)))
