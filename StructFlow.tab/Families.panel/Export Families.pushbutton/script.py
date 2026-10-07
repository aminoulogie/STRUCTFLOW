# -*- coding: utf-8 -*-
"""Save chosen loaded families (title blocks, tags, columns...) as .rfa
files into a folder, e.g. the folder you prepared for the client."""
__title__ = "Export\nFamilies"

from pyrevit import forms, revit, script

import sf_families as sf

doc = revit.doc

groups = sf.exportable_families(doc)
if not groups:
    forms.alert("No editable loaded families in this model.")
else:
    by_label = {}
    options = {}
    for cat, fams in sorted(groups.items()):
        options[cat] = []
        for f in fams:
            label = "{}  [{}]".format(f.Name, cat)
            by_label[label] = f
            options[cat].append(label)
    picked = forms.SelectFromList.show(options, title="Families to export (pick a category above)",
                                       multiselect=True, group_selector_title="Category:",
                                       button_name="Next")
    if picked:
        folder = forms.pick_folder(title="Folder to save the families in")
        if folder:
            by_cat = forms.alert("Put each category in its own subfolder?\n(e.g. Title Blocks\\, Structural Columns\\)",
                                 yes=True, no=True)
            fams = [by_label[p] for p in picked]
            log = []
            done = sf.export_families(doc, fams, folder, by_cat, True, log.append)
            for line in log:
                print(line)
            print("\nDone: {} of {} families saved to {}".format(done, len(fams), folder))
