# -*- coding: utf-8 -*-
"""Floors, walls, roofs and ceilings are system families: they cannot be
saved as .rfa. This puts the chosen types (with their materials) into a
small .rvt library; the client loads them with Manage > Transfer Project
Standards."""
__title__ = "Export\nSystem Types"

import os

from pyrevit import forms, revit

import sf_families as sf

doc = revit.doc

groups = sf.system_types(doc)
options, lookup = {}, {}
for kind in sorted(groups):
    options[kind] = []
    for name in sorted(groups[kind]):
        label = "{}  [{}]".format(name, kind[:-1])
        lookup[label] = groups[kind][name]
        options[kind].append(label)

picked = forms.SelectFromList.show(options, title="System types to export (pick Floors / Walls... above)",
                                   multiselect=True, group_selector_title="Kind:", button_name="Next")
if picked:
    path = forms.save_file(file_ext="rvt", default_name="EPL_SystemTypes",
                           init_dir=os.path.join(os.environ["USERPROFILE"], "Desktop", "EPL_FAMILIES"))
    if path:
        log = []
        sf.export_system_types(doc, [lookup[p] for p in picked], path, log.append)
        for line in log:
            print(line)
        print("\nTo use them in another project: open it, Manage > Transfer Project Standards, "
              "pick this file and tick Floor Types / Wall Types / Roof Types / Ceiling Types.")
