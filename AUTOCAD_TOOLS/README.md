# GCCad – cotation automatique AutoCAD

## Installation (une fois)
AutoCAD > commande `APPLOAD` > « Porte-documents de démarrage » (Contenu…) > Ajouter >
`C:\Users\pro\Desktop\GCSTRUCTFLOW\AUTOCAD_TOOLS\GCCad.lsp` > Fermer. Le fichier se charge alors à chaque dessin.
(Si AutoCAD demande l'autorisation de charger : « Toujours charger ».)

## Commandes
| Commande | Action |
|---|---|
| `GCGRILLE` | Fenêtre : entraxes X et Y (`300 5*500 400`), nommage 1 2 3 / A B C / noms personnalisés (gauche→droite, bas→haut, ex. `C F E B A A'`), débord, annotations (bulles, cotes en chaîne + totale) → clic du point d'insertion → grille dessinée. Les derniers réglages sont mémorisés. |
| `GCAXES` | Sélectionner les lignes d'axes → bulles numérotées (verticaux 1,2,3… / horizontaux A,B,C… ou l'inverse), cotes en chaîne + cote totale, des deux côtés au choix. |
| `GCCOTE` | Tracer un trait à travers murs / axes / poteaux → cotes en chaîne de tous les éléments coupés + cote totale. |
| `GCPOT` | Sélectionner les axes puis les poteaux → cotes axe ↔ nus du poteau + étiquette « 40x40 ». |
| `GCPARAM` | Diamètre des bulles (0 = automatique selon la taille du plan). |

Calques créés : `GC-AXES` (bulles), `GC-COTES` (cotes). Annulable d'un seul `U` par commande.
