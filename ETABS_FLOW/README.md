# GCStructFlow – ETABS 22

## Lancement
- **Depuis ETABS (plugin)** : Tools > Add/Show Plug-Ins > Add
  - Plug-In Name : `GCStructFlow`
  - Path : `C:\Users\pro\Desktop\GCSTRUCTFLOW\ETABS_FLOW\plugin\GCStructFlow.dll`
  - Le menu Tools affiche alors « GCStructFlow » ; il ouvre la fenêtre de l'app, connectée à cet ETABS.
- **Autonome** : `Lancer.bat` (ETABS doit être ouvert).
- Prérequis (déjà faits sur ce PC) : `RegisterETABS.exe` exécuté une fois en administrateur, `pip install pythonnet`.

## Flux
1. ETABS : File > New > Blank (unités kN, m). La création de modèle par l'API est refusée de l'extérieur ;
   le bouton « Nouveau projet » vide donc le modèle ouvert.
2. **Plan → Modèle** (AutoCAD / DXF) ou **Script** → CRÉER LE MODÈLE. L'app crée : étages, axes avec repères,
   béton BETONxx (Eij = 11000·fc28^1/3), FeE400/500, sections avec ferraillage (POT = « à calculer »),
   poteaux/poutres/voiles, dalles (coque ou membrane corps creux) + diaphragme rigide D1, encastrements.
3. **Charges** : patterns G (poids propre) et Q, charges surfaciques par niveau, murs extérieurs sur poutres de rive.
4. **Sismique RPA 2024** : spectre → fonction ETABS utilisateur (Sa/g × 9.81), source de masse G + βQ, Modal,
   Ex/Ey (CQC, excentricité accidentelle 5 %). « Exporter / Importer .txt » pour réutiliser un spectre.
5. **Combinaisons** (voir ci-dessous) + enveloppes ENV ELU / ELS / ACC.
6. **▶ Calculer** (enregistre le .edb puis lance l'analyse) → **Résultats** : Nmax/Mcorr, Nmin/Mcorr, Mmax/Ncorr
   (pied/tête), ν, ferraillage des poutres, τu → Excel / Word, « Copier pour Expert BA ».
7. **Fondations & ressorts** : ressorts de Winkler ponctuels (Kz = ks·A) ou surfaciques (radier), compression seule
   + cas non linéaire « NL G+Q » ; contrôle σ = N/A ≤ σadm (ELS/ELU) et ≤ 2·σadm en ACC (RPA 2024 §10.1.4),
   détection du soulèvement ; export des réactions vers l'app Semelles.
8. **Robot → ETABS** : transfère le modèle Robot ouvert (barres, sections béton et profilés, appuis).

## Combinaisons dans ETABS
Les cas spectraux ETABS sont des enveloppes positives (CQC) : toute combinaison qui les contient donne
automatiquement **Max et Min** (±E). Il suffit donc de :
`1.35G+1.5Q`, `G+Q`, `G+ψQ+Ex+0.3Ey`, `G+ψQ+0.3Ex+Ey`, `0.8G+Ex+0.3Ey`, `0.8G+0.3Ex+Ey` (RPA 2024) — l'app les crée.
Limite : dans une combinaison sismique, Max(N) et Max(M) viennent de valeurs CQC indépendantes ; les couples
« N max / M correspondant » sont donc enveloppes (sécuritaires), pas strictement concomitants.

## Ferraillage « Algérien » dans ETABS
ETABS ne contient pas BAEL/CBA/RPA. Ce que l'app fait : sections poteaux avec ferraillage ETABS (mode « à calculer »),
et les vérifications algériennes sont faites par l'app (ν, poutres BAEL, τu) et par POTEAUX_FCD (flexion déviée
exacte). Pour le contrôle ETABS, choisir Design > Concrete Frame > Eurocode 2-2004 (méthode la plus proche du BAEL).
