# -*- coding: utf-8 -*-
"""Save every family of this model into the EPL library: numbered folders,
EPL_<CODE>_<Element>_<Variant>.rfa names (rebar shapes keep their BS 8666
code). Optionally rename the families in the model to their EPL names.
The standard lives in lib/epl_library.json - add lines there to extend it."""
__title__ = "EPL\nLibrary"

import os

from pyrevit import forms, revit, script
from Autodesk.Revit.DB import Transaction

import sf_families as sf

doc = revit.doc
out = script.get_output()

PREVIEW = "Preview only (report, changes nothing)"
EXPORT = "Export to the library folders"
BOTH = "Export + rename the families in this model"

lib = sf.load_library()
planned, unmapped, missing, to_delete = sf.plan_library(doc, lib)

choice = forms.CommandSwitchWindow.show(
    [PREVIEW, EXPORT, BOTH],
    message="{} families match the EPL standard, {} don't.".format(len(planned), len(unmapped)))

if choice:
    root = None
    if choice != PREVIEW:
        default = os.path.join(os.environ["USERPROFILE"], "Desktop", "EPL_FAMILIES")
        if os.path.isdir(default) and forms.alert("Save into\n{}?".format(default), yes=True, no=True):
            root = default
        else:
            root = forms.pick_folder(title="EPL_FAMILIES library folder")
    if choice == PREVIEW or root:
        log = []
        if root:
            done = sf.export_library(doc, planned, root, log.append)
            log.append("")
            log.append("{} of {} families saved to {}".format(done, len(planned), root))
        if choice == BOTH:
            t = Transaction(doc, "StructFlow EPL rename")
            t.Start()
            try:
                n = sf.rename_to_library(doc, planned, log.append)
                t.Commit()
                log.append("{} families renamed in the model".format(n))
            except Exception as ex:
                t.RollBack()
                log.append("rename stopped, nothing renamed: {}".format(ex))

        out.print_md("## EPL library")
        if choice == PREVIEW:
            out.print_md("**Where each family goes**")
            for f, rel in planned:
                print("{}  ->  {}.rfa".format(f.Name, rel))
        for line in log:
            print(line)
        if unmapped:
            out.print_md("**Not in the standard yet** (add them to lib/epl_library.json):")
            for f in unmapped:
                print("  {}  [{}]".format(f.Name, f.FamilyCategory.Name if f.FamilyCategory else "?"))
        if to_delete:
            out.print_md("**On the proposed-delete list** (not exported, not deleted):")
            for f in to_delete:
                print("  " + f.Name)
        if missing:
            out.print_md("**In the standard but not in this model:**")
            for name in missing:
                print("  " + name)
