# -*- coding: utf-8 -*-
"""Step 1a - read-only audit: every family, type, material, filter and view
template, marked UNUSED or in use. Writes a CSV report and shows a summary.
Changes nothing in the model."""
__title__ = "Audit"

import os

from pyrevit import revit, script

import sf_audit as au

doc = revit.doc
out = script.get_output()

cfg = au.load_config()
rows = au.audit(doc)
name = os.path.splitext(doc.Title)[0]
csv_path = os.path.join(au.reports_folder(cfg), "audit_%s_%s.csv" % (name, au.stamp()))
au.write_csv(rows, csv_path)

out.print_md("## Template audit - {}".format(doc.Title))
out.print_md("Nothing was changed. Full list: `{}`".format(csv_path))
table = [[kind, used, unused] for kind, (used, unused) in sorted(au.summary(rows).items())]
out.print_table(table, columns=["Kind", "In use", "Unused"])
for kind in sorted(set(r["kind"] for r in rows)):
    bad = [r for r in rows if r["kind"] == kind and not r["used"]]
    if not bad:
        continue
    out.print_md("### Unused {} ({})".format(kind.lower() + "s", len(bad)))
    for r in bad[:300]:
        print("  {}   [{}]".format(r["name"], r["category"]))
    if len(bad) > 300:
        print("  ... {} more in the CSV".format(len(bad) - 300))
out.print_md("Next: **Clean Up** to tick and delete only what you choose.")
