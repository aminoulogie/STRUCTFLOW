# -*- coding: utf-8 -*-
"""Make or edit column / beam / slab / wall types from a size list, and
set how they look (line styles, cut / surface patterns, 3D colour) and
their concrete material, with a live preview."""
__title__ = "Type\nMaker"

import os
import re

from pyrevit import forms, revit
from Autodesk.Revit.DB import ElementId, FillPatternTarget, FilteredElementCollector, Transaction
from System.Collections.Generic import List
from System import TimeSpan
from System.Windows import Visibility
from System.Windows.Threading import DispatcherTimer

import sf_families as sf
import sf_graphics as sg
import sf_preview as pv
import sf_profiles as sp
import sf_filters as sfl

doc = revit.doc
CURRENT = "Current model"
NONE = "(none)"
GFIELDS_COMBO = ["cut_w", "proj_w", "proj_pattern", "hidden_pattern", "hidden_w", "cut_fill", "surface_fill"]
GFIELDS_COLOUR = ["colour", "cut_fill_colour", "surface_colour", "shade"]
MFIELDS = ["fck", "ecm", "density", "poisson", "thermal"]
NOTES = {
    "EPL (recommended UK)": "Print-first: black lines, heavy cut lines on columns and walls, solid grey cut "
                            "fill (clean at 1:100, rebar reads well at 1:20), no surface patterns, soft "
                            "concrete greys in 3D, beams below slabs dashed.",
    "Colour coordination": "One colour per element type for model reviews and coordination.",
    "Classic concrete hatch": "Traditional concrete stipple in cut, all black.",
    CURRENT: "What the model uses now.",
}


class TypeMakerWindow(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, os.path.join(os.path.dirname(__file__), "ui.xaml"))
        self.result = None
        self.key = None
        self.choices = {}
        self.state = {}
        saved = sg.load_saved()
        for key, _, _, _ in sf.CATEGORIES:
            entry = saved.get(key) or {}
            self.state[key] = {"g": entry.get("graphics") or dict(sg.PRESETS["EPL (recommended UK)"][key]),
                               "m": entry.get("material") or sg.default_material(key)}
        self.dashes = sp.line_dashes(doc)
        self.type_items = {}
        self._fill_static_lists()
        for _, label, _, _ in sf.CATEGORIES:
            self.category.Items.Add(label)
        self.category.SelectedIndex = 0
        self._last = None
        self.timer = DispatcherTimer()
        self.timer.Interval = TimeSpan.FromMilliseconds(300)
        self.timer.Tick += self._tick
        self.timer.Start()
        self.Closed += lambda s, e: self.timer.Stop()

    # ------------------------------------------------------------ lists
    def _fill_static_lists(self):
        for name in sg.PRESETS:
            self.preset.Items.Add(name)
        self.preset.Items.Add(CURRENT)
        for w in range(1, 17):
            for key in ("cut_w", "proj_w", "hidden_w"):
                getattr(self, key).Items.Add(str(w))
        for name in sorted(sg.line_patterns(doc)):
            self.proj_pattern.Items.Add(name)
            self.hidden_pattern.Items.Add(name)
        self.cut_fill.Items.Add("None")
        for name in sorted(sg.fill_patterns(doc)):
            self.cut_fill.Items.Add(name)
        self.surface_fill.Items.Add("None")
        for name in sorted(sg.fill_patterns(doc, FillPatternTarget.Model)):
            self.surface_fill.Items.Add(name)
        for key in GFIELDS_COLOUR:
            for name, _ in sg.NAMED_COLOURS:
                getattr(self, key).Items.Add(name)
        for g, _, _ in sg.GRADES:
            self.grade.Items.Add(g)
        for _, label in sfl.SCOPES:
            self.filter_scope.Items.Add(label)
        self.filter_scope.SelectedIndex = 0

    @property
    def kind(self):
        return sf.CATEGORIES[self.category.SelectedIndex][3]

    # ------------------------------------------------- graphics <-> UI
    def _set_graphics(self, g):
        for key in GFIELDS_COMBO:
            combo, val = getattr(self, key), str(g[key])
            if val not in list(combo.Items):
                # loose match for pattern names such as "Concrete [Drafting]"
                match = [i for i in combo.Items if val.lower() in str(i).lower()]
                val = match[0] if match else (combo.Items[0] if combo.Items.Count else val)
            combo.SelectedItem = val
        for key in GFIELDS_COLOUR:
            getattr(self, key).Text = sg.colour_label(g[key])
        self.transparency.Value = float(g["transparency"])

    def _get_graphics(self):
        g = {}
        for key in GFIELDS_COMBO:
            g[key] = str(getattr(self, key).SelectedItem or "")
        for key in ("cut_w", "proj_w", "hidden_w"):
            g[key] = int(g[key] or 1)
        for key in GFIELDS_COLOUR:
            g[key] = "%d,%d,%d" % tuple(sg.parse_rgb(getattr(self, key).Text))
        g["transparency"] = int(self.transparency.Value)
        return g

    def _set_material(self, m):
        self.mat_name.Text = chr(10).join(m.get("names") or [m["name"]])
        self.grade.SelectedItem = m["grade"]
        for key in MFIELDS:
            getattr(self, key).Text = "%g" % float(m[key])
        self.description.Text = m.get("description", "")
        self.keynote.Text = m.get("keynote", "")

    def _get_material(self):
        names = [n.strip() for n in re.split(r"[,;\n]+", self.mat_name.Text) if n.strip()]
        if not names:
            raise ValueError("give the material a name")
        m = {"name": names[0], "names": names, "grade": str(self.grade.SelectedItem or ""),
             "description": self.description.Text.strip(), "keynote": self.keynote.Text.strip()}
        for key in MFIELDS:
            m[key] = float(getattr(self, key).Text)
        return m

    def materials(self, m):
        """One material dict per name; a grade written in the name sets fck / Ecm."""
        out = []
        for name in m["names"]:
            mm = dict(m)
            mm["name"] = name
            found = re.search(r"C\d{2}/\d{2}", name)
            grade = found.group(0) if found else m["grade"]
            for g, fck, ecm in sg.GRADES:
                if g == grade and found:
                    mm["fck"], mm["ecm"] = fck, ecm
            if m["grade"] and grade != m["grade"]:
                mm["description"] = m["description"].replace(m["grade"], grade)
            mm["grade"], mm["short"] = grade, (grade if found else name)
            out.append(mm)
        return out

    def _store(self):
        if self.key is None:
            return
        try:
            self.state[self.key]["g"] = self._get_graphics()
        except Exception:
            pass
        try:
            self.state[self.key]["m"] = self._get_material()
        except Exception:
            pass

    # ------------------------------------------------------------ events
    def category_changed(self, sender, args):
        self._store()
        key, label, bic, kind = sf.CATEGORIES[self.category.SelectedIndex]
        self.key = key
        self.base.Items.Clear()
        if kind == "host":
            self.choices = sf.host_types(doc, key)
            self.base_label.Text = "Copy from %s type" % ("slab" if key == "floors" else "wall")
            self.param_panel.Visibility = Visibility.Collapsed
            self.pattern.Text = "Slab {t}mm" if key == "floors" else "Wall {t}mm"
            self.pattern_hint.Text = "{t} = total thickness"
            self.sizes_hint.Text = ("Total thicknesses in mm, separated by commas or new lines; "
                                    "name one with 'Name: 200'.  e.g.  150, 200, 250, 300")
        else:
            self.choices = sf.families_of(doc, bic)
            self.base_label.Text = "Family"
            self.param_panel.Visibility = Visibility.Visible
            three = key == "foundations"
            self.pattern.Text = "{b}x{h}x{d}" if three else "{b}x{h}"
            self.pattern_hint.Text = ("{b} = width, {h} = length, {d} = thickness" if three
                                      else "{b} = width, {h} = depth")
            self.sizes_hint.Text = ("Sizes in mm as width x depth, separated by commas or new lines; "
                                    "name one with 'C1: 300x400'.  e.g.  300x300, 300x450, 400x400")
        for name in sorted(self.choices):
            self.base.Items.Add(name)
        if self.base.Items.Count:
            self.base.SelectedIndex = 0
        self._set_graphics(self.state[key]["g"])
        self._set_material(self.state[key]["m"])
        self.edit_mode.IsChecked = False
        self._load_current()

    def base_changed(self, sender, args):
        if self.base.SelectedItem is None:
            return
        if self.kind == "family":
            sym = sf.first_symbol(doc, self.choices[self.base.SelectedItem])
            names = sf.length_params(sym) if sym else []
            fdn = self.key == "foundations"
            for combo, wanted in ((self.p_w, ["width", "b", "w", "diameter"]),
                                  (self.p_h, ["length", "l", "h", "depth", "d", "height", "diameter"])):
                combo.Items.Clear()
                for n in names:
                    combo.Items.Add(n)
                combo.SelectedItem = sf.guess(names, wanted if fdn else [w for w in wanted if w not in ("length", "l", "diameter")] or wanted)
            self.p_d.Items.Clear()
            self.p_d.Items.Add(NONE)
            for n in names:
                self.p_d.Items.Add(n)
            pick = [n for n in names if n.lower() in ("foundation thickness", "thickness", "t", "depth")] if fdn else []
            self.p_d.SelectedItem = pick[0] if pick else NONE
        if self.edit_mode.IsChecked:
            self.edit_changed(None, None)
        if self.key is not None:
            self._load_current()

    def edit_changed(self, sender, args):
        on = bool(self.edit_mode.IsChecked) and self.base.SelectedItem is not None
        self.types_panel.Visibility = Visibility.Visible if on else Visibility.Collapsed
        self.types_list.Items.Clear()
        self.type_items = {}
        if not on:
            return
        base = self.choices[self.base.SelectedItem]
        self.sizes.Text = sf.describe_existing(doc, self.key, base, self.p_w.SelectedItem, self.p_h.SelectedItem,
                                               self._p_d())
        types = (sf.host_types(doc, self.key) if self.kind == "host"
                 else dict((sf.br.ename(s), s) for s in sf.symbols_of(doc, base)))
        for name in sorted(types):
            self.type_items[name] = types[name]
            self.types_list.Items.Add(name)

    def delete_types(self, sender, args):
        """Delete the selected types from the model (and from the family's type list)."""
        types = self.selected_types()
        if not types:
            forms.alert("Select the types to delete in the list first.")
            return
        bic = sf.CATEGORIES[self.category.SelectedIndex][2]
        used = {}
        for el in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
            tid = el.GetTypeId()
            used[tid] = used.get(tid, 0) + 1
        placed = [(t, used.get(t.Id, 0)) for t in types if used.get(t.Id, 0)]
        total = len(self.type_items)
        if total - len(types) < 1:
            forms.alert("A family must keep at least one type: leave one unselected.")
            return
        nl = chr(10)
        names = nl.join("  %s%s" % (sf.br.ename(t), "   (%d placed)" % used[t.Id] if t.Id in used else "")
                        for t in types)
        if placed:
            choice = forms.CommandSwitchWindow.show(
                ["Delete only the unused ones", "Delete all, including their %d placed element(s)"
                 % sum(n for _, n in placed)],
                message="Delete these types?" + nl + names)
            if not choice:
                return
            if choice.startswith("Delete only"):
                types = [t for t in types if t.Id not in used]
        elif not forms.alert("Delete these types?" + nl + names, yes=True, no=True):
            return
        if not types:
            return
        t = Transaction(doc, "StructFlow delete types")
        t.Start()
        try:
            doc.Delete(List[ElementId]([x.Id for x in types]))
            t.Commit()
        except Exception as ex:
            t.RollBack()
            forms.alert("Nothing deleted: %s" % ex)
            return
        self.edit_changed(None, None)

    def _p_d(self):
        val = self.p_d.SelectedItem
        return None if val in (None, NONE) or self.kind == "host" else val

    def _family_name(self):
        base = self.choices[self.base.SelectedItem]
        return base.FamilyName if self.kind == "host" else base.Name

    def selected_types(self):
        return [self.type_items[n] for n in self.types_list.SelectedItems if n in self.type_items]

    def type_selected(self, sender, args):
        """Show the clicked type alone: its shape, its look and its material."""
        types = self.selected_types()
        if not types:
            return
        t = types[0]
        mat = sg.material_of(doc, t)
        g, notes = sg.read_with_view(doc, self.key, mat, revit.active_view)
        g, fname = sfl.read_look(doc, g, revit.active_view, self._family_name(), sf.br.ename(t))
        if fname:
            notes.append("filter '%s'" % fname)
        self._set_graphics(g)
        self._set_material(sg.read_material(doc, mat, self.key))
        self.preset.SelectedIndex = -1
        self.preset_note.Text = "Showing '%s' (%s)" % (sf.br.ename(t), ", ".join(notes))
        self._last = None

    def _load_current(self):
        """Show how the picked family / type looks in the model right now."""
        if self.preset.SelectedItem == CURRENT:
            self.preset_changed(None, None)
        else:
            self.preset.SelectedItem = CURRENT

    def preset_changed(self, sender, args):
        name = self.preset.SelectedItem
        if not name:
            return
        self.preset_note.Text = NOTES.get(name, "")
        if name == CURRENT:
            mat = None
            if self.base.SelectedItem is not None:
                base = self.choices[self.base.SelectedItem]
                t = base if self.kind == "host" else sf.first_symbol(doc, base)
                mat = sg.material_of(doc, t) if t is not None else None
            g, notes = sg.read_with_view(doc, self.key, mat, revit.active_view)
            if self.base.SelectedItem is not None:
                g, fname = sfl.read_look(doc, g, revit.active_view, self._family_name())
                if fname:
                    notes.append("filter '%s'" % fname)
            self._set_graphics(g)
            self.preset_note.Text = ("Loaded from what you see now: " + ", ".join(notes) +
                                     ". Pick EPL or another preset to change it.")
        else:
            self._set_graphics(sg.PRESETS[name][self.key])

    def grade_changed(self, sender, args):
        grade = self.grade.SelectedItem
        for g, fck, ecm in sg.GRADES:
            if g == grade:
                self.fck.Text, self.ecm.Text = "%g" % fck, "%g" % ecm
                # keep a single default name in step with the grade
                # (a list of several materials is left as typed)
                name = self.mat_name.Text
                if len([n for n in re.split(r"[,;\n]+", name) if n.strip()]) > 1:
                    break
                for other, _, _ in sg.GRADES:
                    if other in name:
                        self.mat_name.Text = name.replace(other, g)
                        self.description.Text = self.description.Text.replace(other, g)
                        break

    # ----------------------------------------------------------- preview
    def _preview_profile(self):
        """Real section of the clicked type, else the family's shape with the
        first size typed, else the family's first type."""
        typed = None
        try:
            typed = sf.parse_sizes(self.sizes.Text, self.kind == "family", bool(self._p_d()))[0][1]
        except Exception:
            pass
        sel = self.selected_types() if self.edit_mode.IsChecked else []
        if self.kind == "host":
            if sel:
                return {"shape": "layer", "t": sf.thickness_of(sel[0])}
            return {"shape": "layer", "t": typed[0] if typed else 200.0}
        if self.base.SelectedItem is None:
            return sp.rect_profile(*(typed or (300.0, 450.0)))
        sym = sel[0] if sel else sf.first_symbol(doc, self.choices[self.base.SelectedItem])
        prof = sp.profile_of_symbol(sym, self.p_w.SelectedItem, self.p_h.SelectedItem)
        if self.key == "foundations":
            prof = dict(prof)
            pd = self._p_d()
            prof["d"] = sp._param_mm(sym, pd) if pd else 600.0
            if typed and not sel:
                prof["w"], prof["h"] = typed[0], typed[1]
                if len(typed) > 2:
                    prof["d"] = typed[2]
            return prof
        if typed and not sel and prof["shape"] in ("rect", "circle"):
            prof = dict(prof)
            prof["w"], prof["h"] = (typed[0], typed[0]) if prof["shape"] == "circle" else typed
        return prof

    def _tick(self, sender, args):
        try:
            g = self._get_graphics()
        except Exception:
            return  # half-typed colour: keep the last drawing
        try:
            prof = self._preview_profile()
        except Exception:
            return
        snap = (self.key, repr(sorted(prof.items())), repr(sorted(g.items())))
        if snap != self._last:
            self._last = snap
            pv.draw(self.preview, self.key, prof, g, self.dashes)

    # --------------------------------------------------------------- run
    def ok_click(self, sender, args):
        if self.base.SelectedItem is None:
            forms.alert("Nothing to copy from: load a family / type of this category first.")
            return
        try:
            entries = sf.parse_sizes(self.sizes.Text, self.kind == "family", bool(self._p_d()))
            g = self._get_graphics()
            m = self._get_material()
        except ValueError as ex:
            forms.alert(str(ex))
            return
        if self.kind == "family" and (self.p_w.SelectedItem is None or self.p_h.SelectedItem is None):
            forms.alert("Pick the width and depth parameters.")
            return
        self.result = {
            "key": self.key, "kind": self.kind, "base": self.choices[self.base.SelectedItem],
            "pattern": self.pattern.Text, "entries": entries, "update": bool(self.update.IsChecked),
            "p_w": self.p_w.SelectedItem, "p_h": self.p_h.SelectedItem, "p_d": self._p_d(),
            "g": g, "m": m, "mats": self.materials(m), "per_material": bool(self.per_material.IsChecked),
            "apply_styles": bool(self.apply_styles.IsChecked),
            "apply_view": bool(self.apply_view.IsChecked),
            "apply_filter": bool(self.apply_filter.IsChecked),
            "scope": sfl.SCOPES[max(self.filter_scope.SelectedIndex, 0)][0],
            "mat_graphics": bool(self.mat_graphics.IsChecked),
            "family_name": self._family_name(),
            "targets": self.selected_types() if self.edit_mode.IsChecked else [],
            "apply_material": bool(self.apply_material.IsChecked),
        }
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()


win = TypeMakerWindow()
win.ShowDialog()
r = win.result
if r:
    log = []
    t = Transaction(doc, "StructFlow Type Maker")
    t.Start()
    try:
        def make(entries):
            if r["kind"] == "host":
                return sf.make_host_types(doc, r["key"], r["base"], r["pattern"], entries,
                                          r["update"], log.append)
            return sf.make_family_types(doc, r["base"], r["pattern"], entries,
                                        r["p_w"], r["p_h"], r["update"], log.append, r["p_d"])

        if r["apply_styles"]:
            sg.apply_object_styles(doc, r["key"], r["g"])
            log.append("object styles updated for all %s" % sg.CATS[r["key"]][0].lower())
        if r["apply_view"]:
            name = sg.apply_view_overrides(doc, r["key"], r["g"], revit.active_view)
            if name:
                log.append("view overrides set in '%s'" % name)

        mats = r["mats"] if r["apply_material"] else []
        if r["per_material"] and len(mats) > 1:
            # every size in every material: '300x600 C30/37', 'GB 300x600 C25/30'...
            for mm in mats:
                entries = [((name or sf.type_name(r["pattern"].replace("{m}", ""), size)).strip()
                            + " " + mm["short"], size) for name, size in r["entries"]]
                made = make(entries)
                mat = sg.apply_material(doc, r["key"], r["g"] if r["mat_graphics"] else None, mm)
                n = sum(1 for e in made if sg.assign_material(doc, e, mat))
                log.append("material '%s' set on %d type(s)" % (mat.Name, n))
        else:
            touched = make(r["entries"])
            first = None
            for mm in mats:
                mat = sg.apply_material(doc, r["key"], r["g"] if r["mat_graphics"] else None, mm)
                first = first or mat
                log.append("material '%s' created / updated" % mat.Name)
            if first is not None:
                targets = r["targets"] or touched
                n = sum(1 for e in targets if sg.assign_material(doc, e, first))
                log.append("material '%s' set on %d type(s)" % (first.Name, n))
        if r["apply_filter"]:
            # the look by family / type name, not by material
            if r["targets"]:
                names = [sf.br.ename(x) for x in r["targets"]]
            elif r["kind"] == "host":
                names = [name or sf.type_name(r["pattern"], size) for name, size in r["entries"]]
            else:
                names = []  # the whole family
            views = sfl.target_views(doc, r["scope"], revit.active_view)
            nf, nv = sfl.apply(doc, r["key"], r["g"], r["family_name"], names, views)
            log.append("look applied with %d filter(s) (%s) in %d view template(s)/view(s)"
                       % (nf, ", ".join(names) if names else "whole family " + r["family_name"], nv))
        t.Commit()
        sg.save(r["key"], r["g"], r["m"])
    except Exception as ex:
        t.RollBack()
        log.append("STOPPED, nothing was changed: %s" % ex)
    for line in log:
        print(line)
