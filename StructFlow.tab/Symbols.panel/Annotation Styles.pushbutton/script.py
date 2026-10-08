# -*- coding: utf-8 -*-
"""EPL text and dimension types (Arial, all black, from epl_standards.jsonc):
EPL_Text_1.8mm ... 10mm, bold / underline / masked title types, filled 15
degree leader arrows; EPL_Dim_2.5mm / 1.8mm (text above and _Centre),
angular, radial, diameter, spot elevation (+0.000) and EPL_Dim_Lap with
'(overlap)'. Shows the list first; changes nothing until you confirm."""
__title__ = "Annotation\nStyles"

from pyrevit import forms, revit, script

import sf_audit as au
import sf_styles as ss

doc = revit.doc
out = script.get_output()
cfg = au.load_config()
EXTRAS = ["bold", "underline", "mask", "leader"]
WANTED = ["linear", "angular", "spot", "lap"]

rows = ss.plan(doc, cfg, EXTRAS, WANTED)
out.print_md("## EPL annotation styles - preview (nothing changed yet)")
out.print_table([[k, n, a] for k, n, a in rows], columns=["Kind", "Type", "Action"])
create = sum(1 for r in rows if r[2] == "create")
choice = forms.CommandSwitchWindow.show(
    ["Create {} and update {} types".format(create, len(rows) - create), "Cancel"],
    message="EPL text and dimension types (see the list in the output window)")
if choice and choice.startswith("Create"):
    log = ["StructFlow Annotation Styles - {}".format(doc.PathName or doc.Title)]
    ok, failed = ss.apply(doc, cfg, EXTRAS, WANTED, log.append)
    log.append("done: {} ok, {} failed".format(ok, failed))
    path = au.write_log(log, cfg, "annotation_styles")
    for line in log:
        print(line)
    out.print_md("Log: `{}`  -  Ctrl+Z undoes it all.".format(path))
