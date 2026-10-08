# -*- coding: utf-8 -*-
"""Step 1b - delete only the unused items you tick. Re-runs the audit,
lets you tick items, shows the list again for confirmation, backs the file
up (setting in epl_standards.jsonc), then deletes one item at a time and
writes a log. Ctrl+Z undoes the whole cleanup."""
__title__ = "Clean\nUp"

from pyrevit import forms, revit, script

import sf_audit as au

doc = revit.doc
out = script.get_output()

cfg = au.load_config()
rows = [r for r in au.audit(doc) if not r["used"]]
if not rows:
    forms.alert("Nothing unused found.", title="StructFlow Clean Up")
else:
    by_label, groups = {}, {}
    for r in rows:
        label = u"{}   [{}]   #{}".format(r["name"], r["category"], r["id"])
        by_label[label] = r
        groups.setdefault(r["kind"], []).append(label)
    picked = forms.SelectFromList.show(groups, title="Tick the unused items to delete (nothing is ticked for you)",
                                       multiselect=True, group_selector_title="Kind:", button_name="Next")
    if picked:
        chosen = [by_label[p] for p in picked]
        lines = "\n".join(u"  {} - {}".format(r["kind"], r["name"]) for r in chosen[:40])
        more = "\n  ... and {} more".format(len(chosen) - 40) if len(chosen) > 40 else ""
        if forms.alert(u"Delete these {} items?\n\n{}{}".format(len(chosen), lines, more),
                       yes=True, no=True, title="StructFlow Clean Up"):
            log = [u"StructFlow Clean Up - {}".format(doc.PathName or doc.Title)]
            go = True
            if cfg["general"].get("backup_before_delete", True):
                try:
                    au.backup(doc, cfg, log.append)
                except Exception as ex:
                    go = forms.alert(u"Backup not made: {}\n\nDelete anyway?".format(ex), yes=True, no=True)
                    log.append(u"backup skipped: {}".format(ex))
            if go:
                ok, failed = au.cleanup(doc, chosen, log.append)
                log.append(u"done: {} deleted, {} failed".format(ok, failed))
                path = au.write_log(log, cfg, "cleanup")
                for line in log:
                    print(line)
                out.print_md("Log: `{}`  -  Ctrl+Z undoes the whole cleanup.".format(path))
