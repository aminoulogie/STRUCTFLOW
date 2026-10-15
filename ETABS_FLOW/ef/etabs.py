"""ETABS 22 API layer (ETABSv1.dll through pythonnet).  Units: kN, m, °C.

Every call returns CSI's status code (0 = OK); ref/out parameters come back as a tuple (ret, out1, out2, ...).
"""
from __future__ import annotations

import os

ETABS_DIR = r"C:\Program Files\Computers and Structures\ETABS 22"
_E = None
_CONN = None


def api():
    global _E
    if _E is None:
        import clr  # pythonnet

        clr.AddReference(os.path.join(ETABS_DIR, "ETABSv1.dll"))
        import ETABSv1 as E

        _E = E
    return _E


class EtabsError(RuntimeError):
    pass


def _ok(ret, what):
    code = ret[0] if isinstance(ret, tuple) else ret
    if code not in (0, None):
        raise EtabsError(f"ETABS a refusé : {what} (code {code})")
    return ret


def _arr(typ, values):
    from System import Array

    return Array[typ](list(values))


class Etabs:
    def __init__(self, start=False):
        E = api()
        h = E.cHelper(E.Helper())
        app = h.GetObject("CSI.ETABS.API.ETABSObject")
        if app is None and start:
            app = h.CreateObject(os.path.join(ETABS_DIR, "ETABS.exe"))
            if app is None:
                raise EtabsError("Impossible de lancer ETABS.")
            app.ApplicationStart()
        if app is None:
            raise EtabsError("ETABS n'est pas ouvert (ou l'API n'est pas enregistrée : RegisterETABS.exe en admin).")
        self.app = app
        self.m = app.SapModel
        if self.m is None:
            raise EtabsError("ETABS ouvert mais aucun modèle accessible (fermez la fenêtre de démarrage).")
        self.E = E
        try:
            self.m.SetPresentUnits(E.eUnits.kN_m_C)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ project
    def filename(self):
        try:
            return self.m.GetModelFilename(True) or ""
        except Exception:  # noqa: BLE001
            return ""

    def new_model(self, n_stories=1, h_typ=3.06, h_bot=3.4):
        """ETABS refuses File.New* from an external program: never re-initialise (it would leave a model without
        stories). The open model is emptied instead; for a truly new model use File > New > Grid Only in ETABS."""
        self.unlock()
        self.clear_objects()
        self.m.SetPresentUnits(self.E.eUnits.kN_m_C)

    def unlock(self):
        try:
            if self.m.GetModelIsLocked():
                self.m.SetModelIsLocked(False)
        except Exception:  # noqa: BLE001
            pass

    def clear_objects(self):
        """Delete every frame and area object of the open model (keeps definitions)."""
        it = self.E.eItemType.SelectedObjects
        self.m.SelectObj.ClearSelection()
        self.m.SelectObj.All(False)
        self.m.FrameObj.Delete("", it)
        self.m.SelectObj.All(False)
        self.m.AreaObj.Delete("", it)
        self.m.SelectObj.ClearSelection()
        try:                                   # remaining restrained points
            for p in list(self.m.PointObj.GetNameList(0, None)[2] or []):
                self.m.PointObj.SetRestraint(p, _arr(bool, [False] * 6), self.E.eItemType.Objects)
                self.m.PointObj.DeleteSpecialPoint(p, self.E.eItemType.Objects)
        except Exception:  # noqa: BLE001
            pass

    def save(self, path=None):
        path = path or self.filename()
        if not path:
            raise EtabsError("Enregistrez d'abord le modèle ETABS (.edb).")
        _ok(self.m.File.Save(path), "enregistrement")
        return path

    def refresh(self):
        try:
            self.m.View.RefreshView(0, False)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ tables
    def table_get(self, key):
        ret = self.m.DatabaseTables.GetTableForEditingArray(key, "", 0, None, 0, None)
        fields = list(ret[2]) if ret[2] else []
        data = list(ret[4]) if ret[4] else []
        n = len(fields)
        rows = [data[i * n:(i + 1) * n] for i in range(ret[3])] if n else []
        return ret[1], fields, rows

    def table_set(self, key, fields, rows, version=None):
        D = self.m.DatabaseTables
        if version is None:
            version = self.table_get(key)[0]
        flat = [str(v) for r in rows for v in r]
        _ok(D.SetTableForEditingArray(key, version, _arr(str, fields), len(rows), _arr(str, flat)), f"table {key}")
        ret = D.ApplyEditedTables(True, 0, 0, 0, 0, "")
        if ret[1]:
            raise EtabsError(f"Table {key} : {ret[1]} erreur(s) fatale(s)\n{ret[5]}")
        return ret[5]

    def display_table(self, key):
        ret = self.m.DatabaseTables.GetTableForDisplayArray(key, None, "", 0, None, 0, None)
        # ret = (code, FieldKeyList, TableVersion, FieldsKeysIncluded, NumberRecords, TableData)
        fields = list(ret[3]) if ret[3] else []
        data = list(ret[5]) if ret[5] else []
        n = len(fields)
        return fields, [data[i * n:(i + 1) * n] for i in range(ret[4])] if n else []

    # ------------------------------------------------------------------ materials & sections
    def ensure_concrete(self, name="BETON25", fc28=25.0):
        E = self.E
        P = self.m.PropMaterial
        _ok(P.SetMaterial(name, E.eMatType.Concrete, -1, "GCStructFlow", ""), "matériau")
        Ec = 11000.0 * fc28 ** (1 / 3) * 1e3            # kN/m² (Eij BAEL)
        P.SetMPIsotropic(name, Ec, 0.2, 1e-5, 0)
        P.SetWeightAndMass(name, 1, 25.0, 0)           # 25 kN/m³
        P.SetOConcrete_1(name, fc28 * 1e3, False, 1.0, 2, 4, 0.002, 0.0035, -0.1, 0, 0, 0)
        return name

    def ensure_rebar(self, name="FeE400", fe=400.0):
        E = self.E
        P = self.m.PropMaterial
        _ok(P.SetMaterial(name, E.eMatType.Rebar, -1, "GCStructFlow", ""), "acier")
        try:
            P.SetMPUniaxial(name, 2.0e8, 1.17e-5, 0)
        except Exception:  # noqa: BLE001
            pass
        try:
            P.SetORebar_1(name, fe * 1e3, fe * 1.1e3, fe * 1e3, fe * 1.1e3, 1, 1, 0.01, 0.09, -0.1, False, 0)
        except Exception:  # noqa: BLE001
            pass
        return name

    def ensure_steel(self, name="S275", fy=275.0):
        E = self.E
        P = self.m.PropMaterial
        _ok(P.SetMaterial(name, E.eMatType.Steel, -1, "GCStructFlow", ""), "acier")
        P.SetMPIsotropic(name, 2.1e8, 0.3, 1.2e-5, 0)
        P.SetWeightAndMass(name, 1, 77.0, 0)
        try:
            P.SetOSteel_1(name, fy * 1e3, fy * 1.5e3, fy * 1.1e3, fy * 1.5e3, 1, 2, 0.02, 0.1, 0.2, -0.1, 0)
        except Exception:  # noqa: BLE001
            pass
        return name

    def frame_props(self):
        import System

        names = []
        T = self.E.eFramePropType
        for nm in System.Enum.GetNames(T):
            try:
                ret = self.m.PropFrame.GetNameList(0, None, getattr(T, str(nm)))
                names += [n for n in (list(ret[2]) if ret[2] else []) if n not in names]
            except Exception:  # noqa: BLE001
                pass
        return names

    def rebar_sizes(self):
        try:
            ret = self.m.PropRebar.GetNameList(0, None)
            return list(ret[2]) if ret[2] else []
        except Exception:  # noqa: BLE001
            return []

    def _bar(self, phi):
        sizes = self.rebar_sizes()
        for cand in (f"{phi}", f"{phi}d", f"T{phi}", f"HA{phi}", f"{phi}M"):
            if cand in sizes:
                return cand
        return sizes[0] if sizes else str(phi)

    def ensure_rect(self, name, b, h, kind="beam", material="BETON25", rebar="FeE400", cover=0.03, phi=14,
                    n2=3, n3=3, check_only=False):
        """Rectangular section; b = width (T2), h = depth (T3), m. Columns get a rebar layout (design or check)."""
        P = self.m.PropFrame
        _ok(P.SetRectangle(name, material, float(h), float(b), -1, "GCStructFlow", ""), f"section {name}")
        if kind == "col":
            P.SetRebarColumn(name, rebar, rebar, 1, 1, cover + 0.008 + phi / 2000, 0, int(n3), int(n2), self._bar(phi),
                             self._bar(8), 0.15, 2, 2, not check_only)
        else:
            P.SetRebarBeam(name, rebar, rebar, cover + 0.02, cover + 0.02, 0, 0, 0, 0)
        return name

    def ensure_circ(self, name, d, material="BETON25", rebar="FeE400", phi=14, n=8, cover=0.03, check_only=False):
        P = self.m.PropFrame
        _ok(P.SetCircle(name, material, float(d), -1, "GCStructFlow", ""), f"section {name}")
        P.SetRebarColumn(name, rebar, rebar, 2, 2, cover + 0.008 + phi / 2000, int(n), 0, 0, self._bar(phi),
                         self._bar(8), 0.15, 0, 0, not check_only)
        return name

    def ensure_slab(self, name, t, material="BETON25", membrane=False):
        E = self.E
        st = E.eShellType.Membrane if membrane else E.eShellType.ShellThin
        _ok(self.m.PropArea.SetSlab(name, E.eSlabType.Slab, st, material, float(t), -1, "GCStructFlow", ""), name)
        return name

    def ensure_wall(self, name, t, material="BETON25"):
        E = self.E
        _ok(self.m.PropArea.SetWall(name, E.eWallPropType.Specified, E.eShellType.ShellThin, material, float(t), -1,
                                    "GCStructFlow", ""), name)
        return name

    def sections_info(self):
        out = []
        for n in self.frame_props():
            try:
                ret = self.m.PropFrame.GetRectangle(n, "", "", 0.0, 0.0, 0, "", "")
                if ret[0] == 0:
                    out.append(dict(name=n, kind="rect", b=ret[4], h=ret[3], d=None, material=ret[2]))
                    continue
            except Exception:  # noqa: BLE001
                pass
            out.append(dict(name=n, kind="?", b=None, h=None, d=None, material=""))
        return out

    # ------------------------------------------------------------------ stories & grids
    def set_stories(self, names, heights, base=0.0):
        n = len(names)
        r = self.m.Story.SetStories_2(float(base), n, _arr(str, names), _arr(float, heights), _arr(bool, [True] + [False] * (n - 1)),
                                      _arr(str, ["None"] + [names[0]] * (n - 1)), _arr(bool, [False] * n),
                                      _arr(float, [0.0] * n), _arr(int, [-1] * n))
        if (r[0] if isinstance(r, tuple) else r) != 0:
            raise EtabsError("ETABS refuse de créer les étages : le modèle ouvert n'est pas initialisé. "
                             "Dans ETABS : File > New Model > Grid Only (kN, m) > OK, puis relancez.")

    def set_grids(self, xs, ys, xlabels, ylabels, system="G1"):
        """Replace the grid lines of the default grid system through the database table."""
        ver, fields, rows = self.table_get("Grid Definitions - Grid Lines")
        if not fields:
            raise EtabsError("Table des axes introuvable.")
        f = {k: i for i, k in enumerate(fields)}
        tmpl = rows[0] if rows else [""] * len(fields)
        sysname = tmpl[f["Name"]] if "Name" in f and rows else system
        new = []
        for lines, labels, typ in ((xs, xlabels, "X (Cartesian)"), (ys, ylabels, "Y (Cartesian)")):
            for pos, lab in zip(lines, labels):
                r = list(tmpl)
                for k, v in (("Name", sysname), ("LineType", typ), ("ID", lab), ("Ordinate", f"{pos:.4f}"),
                             ("Visible", "Yes"), ("BubbleLoc", "End" if typ.startswith("X") else "Start")):
                    if k in f:
                        r[f[k]] = v
                new.append(r)
        return self.table_set("Grid Definitions - Grid Lines", fields, new, ver)

    # ------------------------------------------------------------------ objects
    def add_frame(self, p1, p2, prop, angle=0.0):
        ret = _ok(self.m.FrameObj.AddByCoord(p1[0], p1[1], p1[2], p2[0], p2[1], p2[2], "", prop, "", "Global"), "barre")
        name = ret[1]
        if angle:
            self.m.FrameObj.SetLocalAxes(name, float(angle), self.E.eItemType.Objects)
        return name

    def frame_points(self, name):
        ret = self.m.FrameObj.GetPoints(name, "", "")
        return ret[1], ret[2]

    def add_area(self, pts, prop):
        xs, ys, zs = zip(*pts)
        ret = _ok(self.m.AreaObj.AddByCoord(len(pts), _arr(float, xs), _arr(float, ys), _arr(float, zs), "", prop, "",
                                            "Global"), "panneau")
        return ret[4]

    def restrain(self, point, fixed=(True,) * 6):
        self.m.PointObj.SetRestraint(point, _arr(bool, fixed), self.E.eItemType.Objects)

    def point_spring(self, point, k):
        """k = [U1, U2, U3, R1, R2, R3] in kN/m, kN·m/rad."""
        self.m.PointObj.SetSpring(point, _arr(float, k), self.E.eItemType.Objects, False, True)

    def area_spring_prop(self, name, kz, kx=0.0, ky=0.0, compression_only=True):
        """Winkler area spring (kN/m³). compression_only → 'Compression Only' (needs a nonlinear case to be exact)."""
        _ok(self.m.PropAreaSpring.SetAreaSpringProp(name, float(kx), float(ky), float(kz), 1 if compression_only else 0,
                                                     1, "", 0.0, 0.0, -1, "GCStructFlow", ""), "ressort surfacique")
        return name

    def assign_area_spring(self, area, prop):
        self.m.AreaObj.SetSpringAssignment(area, prop, self.E.eItemType.Objects)

    def diaphragm(self, areas, name="D1"):
        self.m.Diaphragm.SetDiaphragm(name, False)
        for a in areas:
            self.m.AreaObj.SetDiaphragm(a, name)

    # ------------------------------------------------------------------ loads
    def load_pattern(self, name, kind="G", self_weight=0.0):
        T = self.E.eLoadPatternType
        typ = {"G": T.Dead, "Gs": T.SuperDead, "Q": T.Live, "W": T.Wind, "S": T.Snow, "E": T.Quake}.get(kind, T.Other)
        self.m.LoadPatterns.Add(name, typ, float(self_weight), True)
        return name

    def area_load(self, area, pattern, q):
        """Uniform gravity load (kN/m², positive = downward)."""
        self.m.AreaObj.SetLoadUniform(area, pattern, float(q), 10, False, "Global", self.E.eItemType.Objects)

    def frame_load(self, frame, pattern, w):
        self.m.FrameObj.SetLoadDistributed(frame, pattern, 1, 10, 0.0, 1.0, float(w), float(w), "Global", True, False,
                                           self.E.eItemType.Objects)

    def mass_source(self, items, include_elements=True):
        """items: [(pattern, factor)] — e.g. [('G', 1), ('Q', 0.2)].  Written through the database table."""
        key = "Mass Source Definition"
        ver, fields, rows = self.table_get(key)
        f = {k: i for i, k in enumerate(fields)}
        tmpl = rows[0] if rows else [""] * len(fields)
        name = tmpl[f["Name"]] if rows and "Name" in f else "MsSrc1"
        new = []
        for pat, fac in items:
            r = list(tmpl)
            for k, v in (("Name", name), ("IsDefault", "Yes"), ("IncLateral", "Yes"), ("IncVertical", "No"),
                         ("LumpMass", "Yes"), ("SourceSelf", "Yes" if include_elements else "No"), ("SourceAdded", "Yes"),
                         ("SourceLoads", "Yes"), ("MoveMass", "No"), ("LoadPattern", pat), ("Multiplier", f"{fac:g}"),
                         ("GUID", "")):
                if k in f:
                    r[f[k]] = v
            new.append(r)
        return self.table_set(key, fields, new, ver)

    # ------------------------------------------------------------------ dynamics
    def rs_function(self, name, pts, damping=0.05):
        """User response spectrum function: pts = [(T s, Sa/g)]."""
        key = "Functions - Response Spectrum - User Defined"
        ver, fields, rows = self.table_get(key)
        f = {k: i for i, k in enumerate(fields)}
        keep = [r for r in rows if "Name" in f and r[f["Name"]] != name]
        tmpl = [""] * len(fields)
        new = []
        for k_, (T, a) in enumerate(pts):
            r = list(tmpl)
            for k, v in (("Name", name), ("Period", f"{T:.4f}"), ("Value", f"{a:.6f}"),
                         ("DampRatio", f"{damping:g}" if k_ == 0 else "")):
                if k in f:
                    r[f[k]] = v
            new.append(r)
        return self.table_set(key, fields, keep + new, ver)

    def modal(self, name="Modal", modes=12):
        self.m.LoadCases.ModalEigen.SetCase(name)
        self.m.LoadCases.ModalEigen.SetNumberModes(name, int(modes), 1)
        return name

    def rs_case(self, name, direction, func, modal="Modal", ecc=0.05, g=9.81):
        RS = self.m.LoadCases.ResponseSpectrum
        _ok(RS.SetCase(name), f"cas {name}")
        RS.SetModalCase(name, modal)
        RS.SetLoads(name, 1, _arr(str, [{"X": "U1", "Y": "U2", "Z": "U3"}[direction]]), _arr(str, [func]),
                    _arr(float, [g]), _arr(str, ["Global"]), _arr(float, [0.0]))
        RS.SetEccentricity(name, float(ecc))
        return name

    # ------------------------------------------------------------------ combinations
    def combos(self):
        ret = self.m.RespCombo.GetNameList(0, None)
        return list(ret[2]) if ret[2] else []

    def delete_combos(self, names):
        for n in names:
            self.m.RespCombo.Delete(n)

    def combo(self, name, factors, envelope=False):
        """factors: {case_or_pattern_name: sf}"""
        C = self.m.RespCombo
        C.Delete(name)
        _ok(C.Add(name, 1 if envelope else 0), f"combinaison {name}")
        for case, sf in factors.items():
            typ = self.E.eCNameType.LoadCombo if case in self.combos() else self.E.eCNameType.LoadCase
            C.SetCaseList(name, typ, case, float(sf))
        return name

    def load_cases(self):
        ret = self.m.LoadCases.GetNameList(0, None)
        return list(ret[2]) if ret[2] else []

    # ------------------------------------------------------------------ analysis & results
    def run(self, path=None):
        self.save(path)
        _ok(self.m.Analyze.RunAnalysis(), "analyse")

    def frames(self):
        r = self.m.FrameObj.GetAllFrames(0, *([None] * 19), "Global")
        out = {}
        for i in range(r[1]):
            out[r[2][i]] = dict(prop=r[3][i], story=r[4][i], p1=(r[7][i], r[8][i], r[9][i]),
                                p2=(r[10][i], r[11][i], r[12][i]), pt1=r[5][i], pt2=r[6][i], angle=r[13][i])
        return out

    def select_output(self, combos):
        S = self.m.Results.Setup
        S.DeselectAllCasesAndCombosForOutput()
        for c in combos:
            if S.SetComboSelectedForOutput(c, True) != 0:
                S.SetCaseSelectedForOutput(c, True)

    def frame_forces(self, combos):
        """All frames, all stations: list of dict(frame, sta, combo, step, P, V2, V3, T, M2, M3)."""
        self.select_output(combos)
        r = self.m.Results.FrameForce("All", self.E.eItemTypeElm.GroupElm, 0, None, None, None, None, None, None, None,
                                      None, None, None, None, None, None)
        out = []
        n = r[1]
        for i in range(n):
            out.append(dict(frame=r[2][i], sta=r[3][i], combo=r[6][i], step=r[7][i], P=r[9][i], V2=r[10][i],
                            V3=r[11][i], T=r[12][i], M2=r[13][i], M3=r[14][i]))
        return out

    def modal_table(self):
        r = self.m.Results.ModalParticipatingMassRatios(0, None, None, None, None, None, None, None, None, None, None,
                                                         None, None, None, None, None, None)
        return [(int(r[4][i]), r[5][i], 1 / r[5][i] if r[5][i] else 0, 100 * r[6][i], 100 * r[7][i], 100 * r[9][i],
                 100 * r[10][i]) for i in range(r[1])]

    def base_reactions(self, cases):
        self.select_output(cases)
        r = self.m.Results.BaseReact(0, None, None, None, None, None, None, None, None, None, 0.0, 0.0, 0.0)
        return [dict(case=r[2][i], step=r[3][i], FX=r[5][i], FY=r[6][i], FZ=r[7][i], MX=r[8][i], MY=r[9][i]) for i in range(r[1])]

    def story_drifts(self, cases):
        self.select_output(cases)
        r = self.m.Results.StoryDrifts(0, None, None, None, None, None, None, None, None, None, None)
        return [dict(story=r[2][i], case=r[3][i], step=r[4][i], dir=r[6][i], drift=r[7][i]) for i in range(r[1])]

    def joint_reactions(self, combos):
        self.select_output(combos)
        r = self.m.Results.JointReact("All", self.E.eItemTypeElm.GroupElm, 0, None, None, None, None, None, None, None,
                                      None, None, None, None)
        return [dict(point=r[2][i], combo=r[4][i], step=r[5][i], F1=r[7][i], F2=r[8][i], F3=r[9][i], M1=r[10][i],
                     M2=r[11][i], M3=r[12][i]) for i in range(r[1])]


def connect(start=False):
    global _CONN
    if _CONN is not None:
        try:
            _ = _CONN.m.GetModelFilename(True)
            return _CONN
        except Exception:  # noqa: BLE001
            _CONN = None
    _CONN = Etabs(start)
    return _CONN
