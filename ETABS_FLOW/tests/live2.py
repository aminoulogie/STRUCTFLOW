import os, sys, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, r"C:\Users\pro\Desktop\GCSTRUCTFLOW\ETABS_FLOW")
from ef import etabs as ET
E = ET.api()
h = E.cHelper(E.Helper())
t = time.time()
app = h.CreateObject(os.path.join(ET.ETABS_DIR, "ETABS.exe"))
print("create", app is not None, flush=True)
app.ApplicationStart(); print("started", round(time.time() - t), flush=True)
m = app.SapModel
print("init", m.InitializeNewModel(E.eUnits.kN_m_C), "grid", m.File.NewGridOnly(3, 3.06, 3.4, 4, 3, 5.0, 4.0), flush=True)
e = ET.Etabs.__new__(ET.Etabs); e.app, e.m, e.E = app, m, E
ET._CONN = e
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
QMessageBox.critical = lambda *a, **k: print("CRITICAL", a[1:], flush=True)
QMessageBox.warning = lambda *a, **k: print("WARNING", a[1:], flush=True)
QMessageBox.question = lambda *a, **k: QMessageBox.Yes
OUT = r"C:\Users\pro\Desktop\GCSTRUCTFLOW\ETABS_FLOW\tests\out"
import etabsflow, robotflow
robotflow.os.startfile = lambda p: print("would open", p)
etabsflow.os.startfile = lambda p: print("would open", p)
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(OUT, "t_" + a[2]) if len(a) > 2 else os.path.join(OUT, "model.edb"), ""))
qa = QApplication([])
w = etabsflow.EMain()
w.script.setPlainText(robotflow.SCRIPT_EXAMPLE.replace('# wall("C1", "D1", 0.20)', 'wall("C1", "D1", 0.20)'))
w.run_script(); w.create_model(); w.create_cases_and_loads()
w.e_modes.setValue(12); w.create_seismic(); w.create_combos()
w.calculate(); w.read_modal(); w.read_results()
w.run_rpa_checks()
print("PD", [r for r in w.rpa_rows if "P-" in r[0]])
for r in w.rpa_rows: print("RPA", r)
w.bulk_columns()
for r in w.dcol_rows[:4]: print("COL", {k: r[k] for k in ("type", "bars", "As_prov", "ratio", "ties", "ok", "fails")})
w.bulk_beams(); print("BEAM", {k: w.bd_rows[0].get(k) for k in ("bar", "bars_trav", "St_courant", "St_nodal")})
w._etabs_screenshot=lambda p: None
w.export_rpa(); w.export_design(); w.export_word()
print("\n".join(w.logbox.toPlainText().splitlines()[-12:]))
app.ApplicationExit(False)
print("closed", flush=True)
