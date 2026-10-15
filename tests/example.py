"""Example hangar: 2 footing groups, elementary cases G/Q/S/W1/W2/Ex/Ey. Writes tests/out/exemple.docx."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.combos import generate
from engine.footing import Codes, GroupInput, Options
from engine.longrine import LongrineInput
from engine.materials import Materials
from engine.project import Project, run, build_trace
from engine.report import build_docx
from engine.soil import Soil

def L(j, g, case, t, N, Vx=0, Vy=0, Mx=0, My=0):
    return dict(Appui=j, Groupe=g, Cas=case, Type=t, N=N, Vx=Vx, Vy=Vy, Mx=Mx, My=My)

def example(method="adm", codes=None):
    loads = []
    for j in ("12", "15"):  # main portal frame columns, fixed bases
        loads += [L(j, "S1", "G", "G", 85, Vx=12, My=18), L(j, "S1", "Q", "Q", 30, Vx=6, My=9),
                  L(j, "S1", "S", "S", 40, Vx=8, My=12), L(j, "S1", "W1", "W", -95, Vx=-28, My=-60),
                  L(j, "S1", "W2", "W", -40, Vy=15, Mx=-25), L(j, "S1", "Ex", "E", 10, Vx=22, My=55),
                  L(j, "S1", "Ey", "E", 8, Vy=18, Mx=40)]
    loads += [L("30", "S2", "G", "G", 35, Vy=3), L("30", "S2", "Q", "Q", 8), L("30", "S2", "W1", "W", -30, Vy=-9),
              L("30", "S2", "Ex", "E", 3, Vx=6)]
    mat = Materials(fc28=25, fe=400, cracking="FP", cover=0.05)
    soil = Soil(method=method, D=1.5, gamma_r=18, phi_s=28, c_s=0, sigma_adm=200, c=10, phi=28, gamma=18, pl=800, kp=0.9, qc=4000, kc=0.12)
    groups = [GroupInput("S1", 0.50, 0.50, 0.40, 0.40, 0.20, "Encastré"),
              GroupInput("S2", 0.40, 0.40, 0.30, 0.30, 0.20, "Articulé")]
    prj = Project(dict(zone="IV", site="S3", ouvrage="Hangar métallique – test", bureau="GCSTRUCTFLOW", ingenieur="M.A. Lassal"),
                  mat, soil, codes or Codes(), Options(), generate(sorted({(l['Cas'], l['Type']) for l in loads}), psi=0.3, omega=3.6), loads, groups,
                  LongrineInput('S3', 'IV', A=0.25, I=1.0, S=1.2, b=0.30, h=0.35, L=6.0))
    run(prj)
    return prj

if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "out")
    os.makedirs(out, exist_ok=True)
    for meth in ("adm", "cphi", "pressio", "penetro"):
        prj = example(meth)
        for r in prj.results:
            g = r.geo
            print(meth, r.gi.name, f"A={g.A} B={g.B} h={g.h}", "OK" if r.ok else "NON OK", r.msgs,
                  r.rc["X"]["bars"], r.rc["Y"]["bars"], r.rc["X"]["bars_top"], r.ped["bars"])
    prj = example("adm")
    data = build_docx(build_trace(prj), prj.meta)
    open(os.path.join(out, "exemple.docx"), "wb").write(data)
    print("docx bytes", len(data))
