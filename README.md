# Semelles isolées – Hangar métallique (RPA 2024)

Windows desktop app (PySide6) that sizes and reinforces isolated footings with an RC pedestal under steel
columns, and writes a full French **note de calcul (.docx)**. Every formula is shown symbolically, then with
numbers substituted, then the result, the code article and a VÉRIFIÉE / NON VÉRIFIÉE verdict.

## Run
- **Compiled app:** `dist\SemellesRPA2024\SemellesRPA2024.exe` (copy the whole `SemellesRPA2024` folder to share it).
- **From source:** double-click `Lancer.bat`, or `pip install -r requirements.txt` then `python semelles_app.py`.
- **Rebuild the exe:** `build_exe.bat`.
- The previous browser version is frozen in `legacy_web/` (`legacy_web\Lancer.bat`).

## Workflow (tabs)
1. **Projet** – identification, RPA 2024 zone (0–VI), site (S1–S4), importance group (1A/1B/2/3) → A, I, S filled
   automatically (values as in RPA 2024 Integrator); R and Q_F per direction → Ω = R/Q_F; code per check.
2. **Matériaux** – fc28, fe, fissuration, enrobage; γb = 1.20 / γs = 1.00 in seismic situation (§7.3.2).
3. **Sol** – σadm / (c, φ, γ) / pressiomètre / pénétromètre; Fs = 2.0 under seismic combos (§10.1.4); φ', c' for sliding.
4. **Efforts** – **🔗 Importer depuis Robot**: reads the open Robot model directly (read-only, COM API): supports,
   simple cases with their nature (G/Q/W/S/E), Robot ELU/ELS combinations with their factors, reactions.
   Or import ETABS / Robot tables (Excel/CSV), or type/paste (Ctrl+V). "Regroupement auto" splits supports into
   n footing types by load level.
5. **Combinaisons** – matrix *combination × your load cases*. "Générer" proposes BAEL/CCM 97
   — seismic per RPA 2024 for isolated footings: G + ψQ ± Ω(Ex ± 0.3Ey), G + ψQ ± Ω(0.3Ex ± Ey).
   Every factor is editable, rows can be added/removed.
6. **Semelles** – pedestal, base plate, pinned/fixed, optional imposed A, B, h, D.
7. **Longrines** – F = ±α·(A·I·S)·N ≥ 20 kN, α = 0.3/0.4/0.6 (S2/S3/S4), min 25×30 / 30×30, 0.6 %.
8. **Options** – safety factors, bar limits, pedestal ρmin and spacing (auto from zone, §7.4).
9. **Résultats & note** – summary, drawing, details, Word export. Projects save/open as `.json`.

## RPA 2024 coverage
Checked against the supplied PDF: §7.2, §7.3.2, §7.4, §10.1.1, §10.1.4, §10.1.5.
**Not in the supplied PDF (chapters III–V, printed pages 42–94):** seismic combinations §5.2,
overturning / foundation stability §4.5.1 / §5.7, tables of A, I, S. These are user inputs or marked
"(à confirmer)" in the note — references live in `engine/references.py`. A, I, S and the isolated-footing seismic
combination follow RPA 2024 Integrator v4.8.3.

## Tests
```
python tests/example.py        # engine + Word note → tests/out/exemple.docx
python tests/test_desktop.py   # headless desktop app test
python tests/test_robot_live.py  # live test against the open Robot model (read-only)
```
