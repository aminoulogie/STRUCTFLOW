# -*- coding: utf-8 -*-
"""StructFlow template audit and safe cleanup.

audit()   -> rows for every family, type, material, filter and view template
             with 'unused' / 'in use' (read only, changes nothing)
cleanup() -> deletes only the element ids it is given, one at a time in its
             own sub-transaction, logging every success and failure.
Revit's own purge detection (GetAllUnusedElements) decides what is unused for
families, types and materials; filters and view templates are checked here
by looking at every view."""
import csv
import datetime
import io
import json
import os
import re
import shutil

from System.Collections.Generic import HashSet
from Autodesk.Revit.DB import (
    CategoryType, ElementId, ElementType, Family, FamilySymbol, FilterElement,
    FilteredElementCollector, Material, SubTransaction, Transaction, View,
    ViewFamilyType,
)

import sf_beamrebar as br

CONFIG = os.path.join(os.path.dirname(os.path.dirname(__file__)), "epl_standards.jsonc")


# ----------------------------------------------------------------- config
def _strip_comments(text):
    out = []
    for line in text.splitlines():
        in_str, i, cut = False, 0, None
        while i < len(line):
            ch = line[i]
            if ch == '"' and (i == 0 or line[i - 1] != "\\"):
                in_str = not in_str
            elif not in_str and line[i:i + 2] == "//":
                cut = i
                break
            i += 1
        out.append(line if cut is None else line[:cut])
    return "\n".join(out)


def load_config():
    with io.open(CONFIG, encoding="utf-8") as f:
        return json.loads(_strip_comments(f.read()))


def reports_folder(cfg):
    folder = os.path.expandvars(cfg["general"]["reports_folder"])
    if not os.path.isdir(folder):
        os.makedirs(folder)
    return folder


def stamp():
    return datetime.datetime.now().strftime("%Y-%m-%d_%H%M")


# ------------------------------------------------------------------ audit
def _cat_name(el):
    cat = el.Category
    if cat is None and isinstance(el, Family):
        cat = el.FamilyCategory
    return cat.Name if cat is not None else ""


def _is_annotation_family(fam):
    try:
        return fam.FamilyCategory is not None and fam.FamilyCategory.CategoryType == CategoryType.Annotation
    except Exception:
        return False


def audit(doc, log=None):
    """[{kind, category, name, id, used, uses, note}] - read only."""
    unused = set(i.IntegerValue if hasattr(i, "IntegerValue") else i.Value
                 for i in doc.GetAllUnusedElements(HashSet[ElementId]()))
    key = lambda eid: eid.IntegerValue if hasattr(eid, "IntegerValue") else eid.Value

    # how many placed elements use each type
    uses = {}
    for el in FilteredElementCollector(doc).WhereElementIsNotElementType():
        try:
            tid = el.GetTypeId()
        except Exception:
            continue
        if tid is not None and tid != ElementId.InvalidElementId:
            uses[key(tid)] = uses.get(key(tid), 0) + 1

    rows = []

    def add(kind, el, used, n="", note=""):
        rows.append({"kind": kind, "category": _cat_name(el), "name": br.ename(el) or "",
                     "id": key(el.Id), "used": used, "uses": n, "note": note})

    # families (annotation ones listed apart)
    for fam in FilteredElementCollector(doc).OfClass(Family):
        n = sum(uses.get(key(i), 0) for i in fam.GetFamilySymbolIds())
        add("Annotation family" if _is_annotation_family(fam) else "Family", fam,
            key(fam.Id) not in unused, n, "in-place" if fam.IsInPlace else "")

    # types: every family type, plus the system types purge can remove
    for t in FilteredElementCollector(doc).OfClass(ElementType):
        if t.Category is None and not isinstance(t, FamilySymbol):
            continue
        tid = key(t.Id)
        is_unused = tid in unused
        if not isinstance(t, FamilySymbol) and not is_unused and not uses.get(tid):
            continue  # used system types without placed instances: not worth a line
        add("Type", t, not is_unused, uses.get(tid, 0), getattr(t, "FamilyName", "") or "")

    # materials
    for m in FilteredElementCollector(doc).OfClass(Material):
        add("Material", m, key(m.Id) not in unused)

    # filters and view templates: look at every view
    applied, assigned = set(), set()
    for v in FilteredElementCollector(doc).OfClass(View):
        try:
            for fid in v.GetFilters():
                applied.add(key(fid))
        except Exception:
            pass
        if not v.IsTemplate and v.ViewTemplateId != ElementId.InvalidElementId:
            assigned.add(key(v.ViewTemplateId))
    for vft in FilteredElementCollector(doc).OfClass(ViewFamilyType):
        if vft.DefaultTemplateId != ElementId.InvalidElementId:
            assigned.add(key(vft.DefaultTemplateId))
    for f in FilteredElementCollector(doc).OfClass(FilterElement):
        add("Filter", f, key(f.Id) in applied, note="applied in a view or template" if key(f.Id) in applied else "")
    for v in FilteredElementCollector(doc).OfClass(View):
        if v.IsTemplate:
            add("View template", v, key(v.Id) in assigned,
                note="assigned to a view / view type" if key(v.Id) in assigned else "")

    rows.sort(key=lambda r: (r["kind"], r["used"], r["category"], r["name"]))
    return rows


def write_csv(rows, path):
    with io.open(path, "w", encoding="utf-8-sig") as f:
        f.write(u"kind,status,category,name,id,placed,note\n")
        for r in rows:
            vals = [r["kind"], "in use" if r["used"] else "UNUSED", r["category"], r["name"],
                    str(r["id"]), str(r["uses"]), r["note"]]
            f.write(u",".join(u'"%s"' % (u"%s" % v).replace(u'"', u'""') for v in vals) + u"\n")


def summary(rows):
    """{kind: (in use, unused)}"""
    out = {}
    for r in rows:
        used, unused = out.get(r["kind"], (0, 0))
        out[r["kind"]] = (used + 1, unused) if r["used"] else (used, unused + 1)
    return out


# ---------------------------------------------------------------- cleanup
def backup(doc, cfg, log):
    """Copy the saved file into _backup next to it. Returns the copy's path."""
    path = doc.PathName
    if not path or not os.path.isfile(path):
        raise ValueError("save the model first: there is no file on disk to back up")
    folder = os.path.join(os.path.dirname(path), cfg["general"]["backup_folder_name"])
    if not os.path.isdir(folder):
        os.makedirs(folder)
    stem, ext = os.path.splitext(os.path.basename(path))
    target = os.path.join(folder, "%s_%s%s" % (stem, stamp(), ext))
    shutil.copy2(path, target)
    log("backup: %s" % target)
    return target


def cleanup(doc, rows, log):
    """Delete the given rows, each in its own sub-transaction so one failure
    does not stop the run. Returns (deleted, failed)."""
    ok = failed = 0
    t = Transaction(doc, "StructFlow cleanup")
    t.Start()
    for r in rows:
        eid = ElementId(r["id"])
        if doc.GetElement(eid) is None:
            log("gone     %s '%s' (removed with an earlier item)" % (r["kind"], r["name"]))
            continue
        st = SubTransaction(doc)
        st.Start()
        try:
            removed = doc.Delete(eid)
            st.Commit()
            ok += 1
            extra = len(removed) - 1 if removed is not None else 0
            log("deleted  %s '%s' [%s]%s" % (r["kind"], r["name"], r["category"],
                                            ("  (+%d dependent elements)" % extra) if extra > 0 else ""))
        except Exception as ex:
            st.RollBack()
            failed += 1
            log("FAILED   %s '%s': %s" % (r["kind"], r["name"], br._err(ex)))
    t.Commit()
    return ok, failed


def write_log(lines, cfg, name):
    path = os.path.join(reports_folder(cfg), "%s_%s.log" % (name, stamp()))
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(u"\n".join(u"%s" % l for l in lines))
    return path
