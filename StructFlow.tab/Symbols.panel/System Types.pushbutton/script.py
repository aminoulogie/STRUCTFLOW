# -*- coding: utf-8 -*-
"""Navigator for the system family types loaded in the model: dimension
styles, text, filled regions, arrowheads, grids, levels, view tags,
viewports, walls, floors, roofs, ceilings, view types, line styles and
patterns. See how many elements use each; delete, merge, rename,
duplicate, select users, or open a dimension / text type in the Style
Designer."""
__title__ = "System\nTypes"

import os

from pyrevit import forms, revit
from System.Collections.Generic import List
from System.Windows.Controls import CheckBox, TextBlock
from Autodesk.Revit.DB import ElementId

import sf_audit as au
import sf_systypes as st

doc, uidoc = revit.doc, revit.uidoc
cfg = au.load_config()


def label(text):
    tb = TextBlock()
    tb.Text = text
    return tb


class Navigator(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, os.path.join(os.path.dirname(__file__), "ui.xaml"))
        self.ticked = set()
        self.reload()

    def reload(self, keep=None):
        self.data = st.groups(doc)
        self.groups.Items.Clear()
        for g in sorted(self.data):
            n_unused = sum(1 for i in self.data[g] if i["unused"])
            self.groups.Items.Add(label("%s  (%d, %d unused)" % (g, len(self.data[g]), n_unused)))
        names = sorted(self.data)
        self.group_names = names
        self.groups.SelectedIndex = names.index(keep) if keep in names else 0

    def group(self):
        i = self.groups.SelectedIndex
        return self.group_names[i] if 0 <= i < len(self.group_names) else None

    def group_changed(self, sender, args):
        self.ticked = set()
        self.refresh(None, None)

    def shown(self):
        g = self.group()
        if g is None:
            return []
        text = (self.search.Text or "").lower()
        return [i for i in self.data[g] if text in i["name"].lower() and (not self.only_unused.IsChecked or i["unused"])]

    def refresh(self, sender, args):
        self.items.Items.Clear()
        items = self.shown()
        for it in items:
            cb = CheckBox()
            use = "UNUSED" if it["unused"] else ("used by %d" % it["uses"] if it["uses"] is not None else "in use")
            cb.Content = label("%s     [%s]" % (it["name"], use))
            cb.Tag = it
            cb.IsChecked = it["name"] in self.ticked
            cb.Click += self._ticked
            self.items.Items.Add(cb)
        self.merge_into.Items.Clear()
        g = self.group()
        for it in (self.data[g] if g else []):
            self.merge_into.Items.Add(it["name"])
        self.count.Text = "%d shown, %d ticked" % (len(items), len(self.ticked))

    def _ticked(self, sender, args):
        name = sender.Tag["name"]
        if sender.IsChecked:
            self.ticked.add(name)
        else:
            self.ticked.discard(name)
        self.count.Text = "%d shown, %d ticked" % (self.items.Items.Count, len(self.ticked))

    def _tick(self, pred):
        for cb in self.items.Items:
            cb.IsChecked = pred(cb.Tag)
            self._ticked(cb, None)

    def tick_all(self, sender, args):
        self._tick(lambda it: True)

    def tick_unused(self, sender, args):
        self._tick(lambda it: it["unused"])

    def untick_all(self, sender, args):
        self._tick(lambda it: False)

    def selected(self):
        cb = self.items.SelectedItem
        return cb.Tag if cb is not None else None

    def item_selected(self, sender, args):
        it = self.selected()
        if it is None:
            return
        self.new_name.Text = it["name"]
        self.detail.Text = "%s\n%s\n%s" % (it["name"], self.group(),
                                          "UNUSED" if it["unused"] else "used by %s element(s)" % it["uses"])

    def ticked_items(self):
        g = self.group()
        return [i for i in self.data[g] if i["name"] in self.ticked] if g else []

    def _log(self, lines, name):
        path = au.write_log(lines, cfg, name)
        forms.alert("\n".join(lines[-25:]) + "\n\nLog: " + path, title="StructFlow System Types")

    def delete_click(self, sender, args):
        items = self.ticked_items()
        if not items:
            forms.alert("Tick the types to delete first.")
            return
        used = [i for i in items if not i["unused"]]
        msg = "Delete %d type(s)?" % len(items)
        if used:
            msg += ("\n\n%d of them are IN USE - deleting them also deletes the elements using them:\n  "
                    % len(used)) + "\n  ".join(i["name"] for i in used[:15]) + "\n\nUse Merge instead to keep those elements."
        if not forms.alert(msg, yes=True, no=True, title="StructFlow System Types"):
            return
        log = ["System Types - delete"]
        st.delete(doc, items, log.append)
        self._log(log, "systypes_delete")
        self.ticked = set()
        self.reload(self.group())

    def merge_click(self, sender, args):
        items = self.ticked_items()
        target_name = self.merge_into.SelectedItem
        if not items or not target_name:
            forms.alert("Tick the types to merge and pick the type to merge them into.")
            return
        target = [i for i in self.data[self.group()] if i["name"] == target_name][0]
        if target.get("sub") is not None or target["kind"] == "pattern":
            forms.alert("Line styles and patterns cannot be merged this way.")
            return
        if not forms.alert("Move every element using the %d ticked type(s) onto '%s', then delete them?"
                           % (len(items), target_name), yes=True, no=True):
            return
        log = ["System Types - merge into %s" % target_name]
        st.merge(doc, items, target["el"], log.append)
        self._log(log, "systypes_merge")
        self.ticked = set()
        self.reload(self.group())

    def rename_click(self, sender, args):
        it = self.selected()
        if it is None or not self.new_name.Text.strip():
            return
        try:
            st.rename(doc, it, self.new_name.Text.strip())
            self.reload(self.group())
        except Exception as ex:
            forms.alert("Not renamed: %s" % ex)

    def duplicate_click(self, sender, args):
        it = self.selected()
        name = self.new_name.Text.strip()
        if it is None or not name or name == it["name"]:
            forms.alert("Select a type and type a new name first.")
            return
        try:
            st.duplicate(doc, it, name)
            self.reload(self.group())
        except Exception as ex:
            forms.alert("Not duplicated: %s" % ex)

    def select_users(self, sender, args):
        it = self.selected()
        if it is None or it["kind"] in ("linestyle", "pattern"):
            return
        ids = [e.Id for e in st.users(doc, it["el"])]
        uidoc.Selection.SetElementIds(List[ElementId](ids))
        forms.alert("%d element(s) selected in the model." % len(ids))

    def open_designer(self, sender, args):
        it = self.selected()
        if it is None or it["kind"] not in ("dimension", "text"):
            forms.alert("Select a dimension style or text type first.")
            return
        import sf_styledesigner as sd
        sd.StyleDesigner(doc, it["el"]).ShowDialog()
        self.reload(self.group())


Navigator().ShowDialog()
