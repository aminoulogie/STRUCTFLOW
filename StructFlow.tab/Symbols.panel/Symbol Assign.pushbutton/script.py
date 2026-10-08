# -*- coding: utf-8 -*-
"""Use the EPL symbols everywhere: grid / level types, section and callout
tags, elevation tags, viewport types (view title) and the default tags for
rebar, columns, framing and foundations. Shows what each type uses now;
only the ticked ones change. Then an optional test sheet to check them."""
__title__ = "Symbol\nAssign"

from pyrevit import forms, revit, script

import sf_assign as sa
import sf_audit as au
import sf_sheets as ss

doc, uidoc = revit.doc, revit.uidoc
out = script.get_output()
cfg = au.load_config()

rows = sa.rows(doc, cfg)
out.print_md("## EPL symbols - what each type uses now")
out.print_table([[r["kind"], r["type_name"], r["current"], r["target"],
                  {"ok": "already EPL", "change": "can switch", "missing": "EPL family not loaded"}[r["state"]]]
                 for r in rows], columns=["Kind", "Type", "Uses now", "EPL symbol", "Status"])
missing = sorted(set(r["target"] for r in rows if r["state"] == "missing"))
if missing:
    out.print_md("**Load or build these first** (Symbol Designer / EPL Library): " + ", ".join(missing))

todo = [r for r in rows if r["state"] == "change"]
if not todo:
    forms.alert("Nothing to switch: every type already uses its EPL symbol (or the EPL family is missing).",
                title="StructFlow Symbol Assign")
else:
    by_label, groups = {}, {}
    for r in todo:
        label = u"{}   ({}  ->  {})".format(r["type_name"], r["current"], r["target"])
        by_label[label] = r
        groups.setdefault(r["kind"], []).append(label)
    picked = forms.SelectFromList.show(groups, title="Tick the types to switch to EPL symbols",
                                       multiselect=True, group_selector_title="Kind:", button_name="Switch")
    if picked:
        log = [u"StructFlow Symbol Assign - {}".format(doc.PathName or doc.Title)]
        ok, failed = sa.assign(doc, [by_label[p] for p in picked], log.append)
        log.append(u"done: {} switched, {} failed".format(ok, failed))
        if forms.alert("Make a test sheet to check the symbols?", yes=True, no=True):
            try:
                sheet = sa.test_sheet(doc, ss.load_settings().get("title_block", ""), log.append)
                uidoc.ActiveView = sheet
            except Exception as ex:
                log.append(u"test sheet failed: {}".format(ex))
        path = au.write_log(log, cfg, "symbol_assign")
        for line in log:
            print(line)
        out.print_md("Log: `{}`  -  Ctrl+Z undoes it.".format(path))
