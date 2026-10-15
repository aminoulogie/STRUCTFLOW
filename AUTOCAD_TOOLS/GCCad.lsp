;;; GCCad.lsp – outils de cotation automatique (GCStructFlow)
;;; Charger : APPLOAD > GCCad.lsp (ajouter au « Porte-documents de démarrage » pour l'avoir toujours).
;;; Commandes :
;;;   GCAXES  : bulles d'axes numérotées + cotes en chaîne + cote totale
;;;   GCCOTE  : cotation en chaîne de tout ce que coupe un trait (murs, axes, poteaux)
;;;   GCPOT   : cotes des poteaux par rapport aux axes + étiquette de section
;;;   GCPARAM : taille des bulles / textes, décalages

(vl-load-com)

(setq *gc-bubble* nil)        ; diamètre des bulles (unités dessin) – nil = automatique
(setq *gc-layer-dim* "GC-COTES")
(setq *gc-vlab* nil *gc-hlab* nil *gc-nobub* nil *gc-nodims* nil)
(setq *gc-layer-axe* "GC-AXES")

;;; ------------------------------------------------------------------ utilitaires
(defun gc:layer (name col)
  (if (not (tblsearch "LAYER" name))
    (entmake (list '(0 . "LAYER") '(100 . "AcDbSymbolTableRecord") '(100 . "AcDbLayerTableRecord")
                   (cons 2 name) (cons 62 col) '(70 . 0))))
  name)

(defun gc:save-vars ()
  (setq gc:old (mapcar 'getvar '("OSMODE" "CMDECHO" "CLAYER" "DIMSCALE")))
  (setvar "OSMODE" 0) (setvar "CMDECHO" 0))

(defun gc:restore-vars ()
  (if gc:old (mapcar 'setvar '("OSMODE" "CMDECHO" "CLAYER" "DIMSCALE") gc:old)))

(defun gc:err (msg)
  (gc:restore-vars)
  (if (not (member msg '("Function cancelled" "quit / exit abort" "Fonction annulée")))
    (princ (strcat "\nGCCad : " msg)))
  (princ))

(defun gc:ends (e / d p q)
  ;; extrémités d'une LINE ou d'une LWPOLYLINE à 2 sommets
  (setq d (entget e))
  (cond ((= (cdr (assoc 0 d)) "LINE") (list (cdr (assoc 10 d)) (cdr (assoc 11 d))))
        ((= (cdr (assoc 0 d)) "LWPOLYLINE")
         (setq p (mapcar 'cdr (vl-remove-if-not '(lambda (x) (= (car x) 10)) d)))
         (list (car p) (last p)))
        (t nil)))

(defun gc:ss->list (ss / i out)
  (setq i 0)
  (if ss (repeat (sslength ss) (setq out (cons (ssname ss i) out) i (1+ i))))
  (reverse out))

(defun gc:letters (i / s)
  ;; 0 -> A, 25 -> Z, 26 -> AA
  (setq s "" i (1+ i))
  (while (> i 0)
    (setq s (strcat (chr (+ 65 (rem (1- i) 26))) s) i (/ (1- i) 26)))
  s)

(defun gc:extent-size ( / a b)
  (setq a (getvar "EXTMIN") b (getvar "EXTMAX"))
  (max (- (car b) (car a)) (- (cadr b) (cadr a)) 1.0))

(defun gc:bubble-size (span)
  (if *gc-bubble* *gc-bubble* (max (* 0.025 span) 1e-6)))

(defun gc:bubble (pt lab d / r)
  (if (not *gc-nobub*) (progn
  (setq r (/ d 2.0))
  (entmake (list '(0 . "CIRCLE") (cons 8 *gc-layer-axe*) (cons 10 pt) (cons 40 r)))
  (entmake (list '(0 . "TEXT") (cons 8 *gc-layer-axe*) (cons 10 pt) (cons 11 pt) (cons 40 (* 0.5 d))
                 (cons 1 lab) '(72 . 1) '(73 . 2))))))

(defun gc:adim (p1 p2 loc horiz)
  (if (not *gc-nodims*) (gc:dim p1 p2 loc horiz)))

(defun gc:lab (i numeric custom)
  ;; nom de l'axe n° i : liste personnalisée, sinon 1 2 3… ou A B C…
  (cond ((and custom (nth i custom)) (nth i custom))
        (numeric (itoa (1+ i)))
        (t (gc:letters i))))

(defun gc:dim (p1 p2 loc horiz)
  (command "_.DIMLINEAR" "_non" p1 "_non" p2 (if horiz "_H" "_V") "_non" loc))

(defun gc:setup-dims (span / ds)
  (gc:layer *gc-layer-dim* 3)
  (gc:layer *gc-layer-axe* 1)
  (setvar "CLAYER" *gc-layer-dim*)
  ;; DIMSCALE so that the dimension text ≈ 1/3 bubble
  (setq ds (/ (* 0.33 (gc:bubble-size span)) (max (getvar "DIMTXT") 1e-6)))
  (setvar "DIMSCALE" ds))

;;; ------------------------------------------------------------------ GCAXES
(defun gc:axes (ents num-vert both / tol v h e pts a b xs ys span d gap x y lab i ymin ymax xmin xmax row)
  (setq tol 1e-6 v nil h nil)
  (foreach e ents
    (if (setq pts (gc:ends e))
      (progn
        (setq a (car pts) b (cadr pts))
        (cond ((< (abs (- (car a) (car b))) (* 1e-4 (+ 1 (distance a b))))   ; verticale
               (setq v (cons (list (car a) (min (cadr a) (cadr b)) (max (cadr a) (cadr b))) v)))
              ((< (abs (- (cadr a) (cadr b))) (* 1e-4 (+ 1 (distance a b))))  ; horizontale
               (setq h (cons (list (cadr a) (min (car a) (car b)) (max (car a) (car b))) h)))))))
  ;; tri + suppression des doublons
  (setq v (vl-sort v '(lambda (p q) (< (car p) (car q))))
        h (vl-sort h '(lambda (p q) (< (car p) (car q)))))
  (setq v (gc:uniq v) h (gc:uniq h))
  (if (and (null v) (null h)) (progn (princ "\nAucune ligne horizontale/verticale.") (exit)))
  (setq span (max (if v (- (car (last v)) (car (car v))) 0) (if h (- (car (last h)) (car (car h))) 0) 1.0))
  (setq d (gc:bubble-size span) gap (* 0.6 d))
  (gc:setup-dims span)
  ;; ---- axes verticaux : bulles en bas (et en haut), cotes sous le plan
  (if v
    (progn
      (setq ymin (apply 'min (mapcar 'cadr v)) ymax (apply 'max (mapcar 'caddr v)) i 0)
      (foreach ax v
        (setq x (car ax)
              lab (gc:lab i num-vert *gc-vlab*))
        (gc:bubble (list x (- ymin gap (/ d 2.0)) 0.0) lab d)
        (entmake (list '(0 . "LINE") (cons 8 *gc-layer-axe*) (list 10 x ymin 0.0) (list 11 x (- ymin gap) 0.0)))
        (if both (progn (gc:bubble (list x (+ ymax gap (/ d 2.0)) 0.0) lab d)
                        (entmake (list '(0 . "LINE") (cons 8 *gc-layer-axe*) (list 10 x ymax 0.0) (list 11 x (+ ymax gap) 0.0)))))
        (setq i (1+ i)))
      (setq row (- ymin gap d (* 1.2 d)))
      (setq i 0)
      (while (< i (1- (length v)))
        (gc:adim (list (car (nth i v)) ymin) (list (car (nth (1+ i) v)) ymin) (list 0 row) T)
        (setq i (1+ i)))
      (if (> (length v) 2)
        (gc:adim (list (car (car v)) ymin) (list (car (last v)) ymin) (list 0 (- row (* 1.2 d))) T))))
  ;; ---- axes horizontaux : bulles à gauche (et à droite), cotes à gauche
  (if h
    (progn
      (setq xmin (apply 'min (mapcar 'cadr h)) xmax (apply 'max (mapcar 'caddr h)) i 0)
      (foreach ax h
        (setq y (car ax)
              lab (gc:lab i (not num-vert) *gc-hlab*))
        (gc:bubble (list (- xmin gap (/ d 2.0)) y 0.0) lab d)
        (entmake (list '(0 . "LINE") (cons 8 *gc-layer-axe*) (list 10 xmin y 0.0) (list 11 (- xmin gap) y 0.0)))
        (if both (progn (gc:bubble (list (+ xmax gap (/ d 2.0)) y 0.0) lab d)
                        (entmake (list '(0 . "LINE") (cons 8 *gc-layer-axe*) (list 10 xmax y 0.0) (list 11 (+ xmax gap) y 0.0)))))
        (setq i (1+ i)))
      (setq row (- xmin gap d (* 1.2 d)) i 0)
      (while (< i (1- (length h)))
        (gc:adim (list xmin (car (nth i h))) (list xmin (car (nth (1+ i) h))) (list row 0) nil)
        (setq i (1+ i)))
      (if (> (length h) 2)
        (gc:adim (list xmin (car (car h))) (list xmin (car (last h))) (list (- row (* 1.2 d)) 0) nil))))
  (list (length v) (length h)))

(defun gc:uniq (lst / out)
  ;; fusionne les axes de même position (lignes pointillées découpées) en gardant l'étendue max
  (foreach p lst
    (if (and out (< (abs (- (car p) (car (car out)))) 1e-3))
      (setq out (cons (list (car p) (min (cadr p) (cadr (car out))) (max (caddr p) (caddr (car out)))) (cdr out)))
      (setq out (cons p out))))
  (reverse out))

(defun c:GCAXES ( / *error* ss k both res)
  (setq *error* gc:err)
  (gc:save-vars)
  (princ "\nSélectionnez les lignes d'axes (fenêtre ou clics) : ")
  (setq ss (ssget '((0 . "LINE,LWPOLYLINE"))))
  (if ss
    (progn
      (initget "Chiffres Lettres")
      (setq k (getkword "\nAxes verticaux numérotés en [Chiffres/Lettres] <Chiffres> : "))
      (initget "Oui Non")
      (setq both (/= (getkword "\nBulles des deux côtés ? [Oui/Non] <Oui> : ") "Non"))
      (command "_.UNDO" "_BE")
      (setq res (gc:axes (gc:ss->list ss) (/= k "Lettres") both))
      (command "_.UNDO" "_E")
      (princ (strcat "\nGCAXES : " (itoa (car res)) " axes verticaux, " (itoa (cadr res)) " axes horizontaux cotés."))))
  (gc:restore-vars)
  (princ))

;;; ------------------------------------------------------------------ GCCOTE (cotation par trait)
(defun gc:fence-points (p1 p2 / ss obj tmp pts arr i n ip)
  (setq ss (ssget "_F" (list p1 p2) '((0 . "LINE,LWPOLYLINE,POLYLINE,ARC,CIRCLE"))))
  (setq tmp (vlax-ename->vla-object (entmakex (list '(0 . "LINE") (cons 10 p1) (cons 11 p2)))))
  (foreach e (gc:ss->list ss)
    (setq obj (vlax-ename->vla-object e))
    (setq arr (vlax-variant-value (vla-IntersectWith tmp obj acExtendNone)))
    (if (> (vlax-safearray-get-u-bound arr 1) 0)
      (progn
        (setq arr (vlax-safearray->list arr) i 0 n (length arr))
        (while (< i n)
          (setq pts (cons (list (nth i arr) (nth (1+ i) arr) 0.0) pts) i (+ i 3))))))
  (vla-delete tmp)
  pts)

(defun c:GCCOTE ( / *error* p1 p2 pts horiz loc key prev out i d)
  (setq *error* gc:err)
  (gc:save-vars)
  (setq p1 (getpoint "\nTrait de cotation – premier point : "))
  (setq p2 (getpoint p1 "\nDeuxième point : "))
  (setq horiz (>= (abs (- (car p2) (car p1))) (abs (- (cadr p2) (cadr p1)))))
  (setq pts (gc:fence-points p1 p2))
  (if (< (length pts) 2) (progn (princ "\nMoins de 2 intersections.") (exit)))
  (setq key (if horiz 'car 'cadr))
  (setq pts (vl-sort pts '(lambda (a b) (< (apply key (list a)) (apply key (list b))))))
  ;; supprime les points confondus
  (foreach p pts
    (if (or (null out) (> (abs (- (apply key (list p)) (apply key (list (car out))))) 1e-6)) (setq out (cons p out))))
  (setq pts (reverse out))
  (setq loc (getpoint "\nPosition de la ligne de cote : "))
  (gc:layer *gc-layer-dim* 3)
  (setvar "CLAYER" *gc-layer-dim*)
  (command "_.UNDO" "_BE")
  (setq i 0)
  (while (< i (1- (length pts)))
    (gc:dim (nth i pts) (nth (1+ i) pts) loc horiz)
    (setq i (1+ i)))
  (if (> (length pts) 2)
    (progn
      (setq d (* 1.5 (getvar "DIMTXT") (getvar "DIMSCALE")))
      (gc:dim (car pts) (last pts)
              (if horiz (list (car loc) (+ (cadr loc) (if (> (cadr loc) (cadr (car pts))) d (- d))))
                        (list (+ (car loc) (if (> (car loc) (car (car pts))) d (- d))) (cadr loc)))
              horiz)))
  (command "_.UNDO" "_E")
  (princ (strcat "\nGCCOTE : " (itoa (1- (length pts))) " cotes en chaîne + cote totale."))
  (gc:restore-vars)
  (princ))

;;; ------------------------------------------------------------------ GCPOT (poteaux / axes)
(defun gc:bbox (e / mn mx)
  (vla-GetBoundingBox (vlax-ename->vla-object e) 'mn 'mx)
  (list (vlax-safearray->list mn) (vlax-safearray->list mx)))

(defun gc:nearest (val lst / best)
  (foreach x lst (if (or (null best) (< (abs (- x val)) (abs (- best val)))) (setq best x)))
  best)

(defun c:GCPOT ( / *error* ssa ssc vx hy e bb mn mx cx cy ax ay d lab scale)
  (setq *error* gc:err)
  (gc:save-vars)
  (princ "\nSélectionnez les lignes d'axes : ")
  (setq ssa (ssget '((0 . "LINE,LWPOLYLINE"))))
  (princ "\nSélectionnez les poteaux (polylignes fermées / hachures / blocs) : ")
  (setq ssc (ssget '((0 . "LWPOLYLINE,POLYLINE,HATCH,INSERT,SOLID"))))
  (if (and ssa ssc)
    (progn
      (foreach e (gc:ss->list ssa)
        (if (setq bb (gc:ends e))
          (cond ((< (abs (- (car (car bb)) (car (cadr bb)))) 1e-3) (setq vx (cons (car (car bb)) vx)))
                ((< (abs (- (cadr (car bb)) (cadr (cadr bb)))) 1e-3) (setq hy (cons (cadr (car bb)) hy))))))
      (initget 6)
      (setq scale (getreal "\nUnité du dessin : 1 = [1 cm / 0.1 cm (mm) / ...] – facteur vers cm <1> : "))
      (if (null scale) (setq scale 1.0))
      (gc:layer *gc-layer-dim* 3)
      (setvar "CLAYER" *gc-layer-dim*)
      (command "_.UNDO" "_BE")
      (foreach e (gc:ss->list ssc)
        (setq bb (gc:bbox e) mn (car bb) mx (cadr bb)
              cx (/ (+ (car mn) (car mx)) 2.0) cy (/ (+ (cadr mn) (cadr mx)) 2.0)
              d (max (- (car mx) (car mn)) (- (cadr mx) (cadr mn))))
        (if vx
          (progn
            (setq ax (gc:nearest cx vx))
            (if (> (abs (- ax (car mn))) 1e-6) (gc:dim (list ax (cadr mx)) (list (car mn) (cadr mx)) (list cx (+ (cadr mx) d)) T))
            (if (> (abs (- (car mx) ax)) 1e-6) (gc:dim (list ax (cadr mx)) (list (car mx) (cadr mx)) (list cx (+ (cadr mx) d)) T))))
        (if hy
          (progn
            (setq ay (gc:nearest cy hy))
            (if (> (abs (- ay (cadr mn))) 1e-6) (gc:dim (list (car mx) ay) (list (car mx) (cadr mn)) (list (+ (car mx) d) cy) nil))
            (if (> (abs (- (cadr mx) ay)) 1e-6) (gc:dim (list (car mx) ay) (list (car mx) (cadr mx)) (list (+ (car mx) d) cy) nil))))
        (setq lab (strcat (rtos (* scale (- (car mx) (car mn))) 2 0) "x" (rtos (* scale (- (cadr mx) (cadr mn))) 2 0)))
        (entmake (list '(0 . "TEXT") (cons 8 *gc-layer-dim*) (list 10 (car mn) (- (cadr mn) (* 0.6 d)) 0.0)
                       (cons 40 (* 0.25 d)) (cons 1 lab))))
      (command "_.UNDO" "_E")
      (princ (strcat "\nGCPOT : " (itoa (sslength ssc)) " poteaux cotés."))))
  (gc:restore-vars)
  (princ))

;;; ------------------------------------------------------------------ GCPARAM
(defun c:GCPARAM ( / v)
  (setq v (getreal (strcat "\nDiamètre des bulles d'axes (unités dessin, 0 = automatique) <"
                           (if *gc-bubble* (rtos *gc-bubble* 2 2) "auto") "> : ")))
  (if v (setq *gc-bubble* (if (> v 0) v nil)))
  (princ))

(princ "\nGCCad chargé : GCAXES (axes+bulles+cotes), GCCOTE (cotation par trait), GCPOT (poteaux), GCPARAM.")
(princ)

;;; ------------------------------------------------------------------ GCGRILLE (fenêtre : entraxes → axes)
(setq *gg-xs* "300 5*500 400" *gg-ys* "600 600 600 700 175" *gg-xmode* "x1" *gg-ymode* "yA"
      *gg-xl* "" *gg-yl* "" *gg-ext* "150" *gg-both* "1" *gg-dims* "1" *gg-bub* "1")

(defun gc:split (str / out cur ch i)
  ;; découpe sur espaces / ; / tabulations
  (setq str (vl-string-translate ";\t" "  " str) out nil cur "" i 1)
  (while (<= i (strlen str))
    (setq ch (substr str i 1))
    (if (= ch " ")
      (progn (if (/= cur "") (setq out (cons cur out))) (setq cur ""))
      (setq cur (strcat cur ch)))
    (setq i (1+ i)))
  (if (/= cur "") (setq out (cons cur out)))
  (reverse out))

(defun gc:parse-spacing (str / out p n v)
  ;; "300 5*500 400" -> (300 500 500 500 500 500 400) ; accepte aussi 5x500 et la virgule décimale
  (foreach tok (gc:split (vl-string-translate "," "." str))
    (setq p (or (vl-string-search "*" tok) (vl-string-search "x" tok) (vl-string-search "X" tok)))
    (if p
      (progn (setq n (atoi (substr tok 1 p)) v (atof (substr tok (+ p 2))))
             (repeat (max n 0) (setq out (cons v out))))
      (if (> (atof tok) 0) (setq out (cons (atof tok) out)))))
  (reverse out))

(defun gc:cumul (sp / out acc)
  (setq acc 0.0 out (list 0.0))
  (foreach s sp (setq acc (+ acc s) out (cons acc out)))
  (reverse out))

(defun gc:names (n mode custom / out i)
  (setq i 0)
  (repeat n
    (setq out (cons (cond ((and (= mode "c") custom (nth i custom)) (nth i custom))
                          ((= mode "n") (itoa (1+ i)))
                          (t (gc:letters i))) out)
          i (1+ i)))
  (reverse out))

(defun gc:axe-ltype ( / doc lin)
  (if (not (or (tblsearch "LTYPE" "AXES") (tblsearch "LTYPE" "CENTER")))
    (progn
      (setq doc (vla-get-activedocument (vlax-get-acad-object))
            lin (findfile (if (= (getvar "MEASUREMENT") 1) "acadiso.lin" "acad.lin")))
      (if lin (vl-catch-all-apply 'vla-load (list (vla-get-linetypes doc) "CENTER" lin)))))
  (cond ((tblsearch "LTYPE" "AXES") "AXES") ((tblsearch "LTYPE" "CENTER") "CENTER") (t "BYLAYER")))

(defun gc:grille (xsp ysp org ext both xnames ynames / xs ys x0 y0 XX YY ents lt)
  ;; dessine les axes (calque GC-AXES) puis bulles + cotes via gc:axes
  (setq xs (gc:cumul xsp) ys (gc:cumul ysp) x0 (car org) y0 (cadr org)
        XX (last xs) YY (last ys))
  (gc:layer *gc-layer-axe* 1)
  (setq lt (gc:axe-ltype))
  (foreach x xs
    (setq ents (cons (entmakex (list '(0 . "LINE") (cons 8 *gc-layer-axe*) (cons 6 lt)
                                     (list 10 (+ x0 x) (- y0 ext) 0.0) (list 11 (+ x0 x) (+ y0 YY ext) 0.0))) ents)))
  (foreach y ys
    (setq ents (cons (entmakex (list '(0 . "LINE") (cons 8 *gc-layer-axe*) (cons 6 lt)
                                     (list 10 (- x0 ext) (+ y0 y) 0.0) (list 11 (+ x0 XX ext) (+ y0 y) 0.0))) ents)))
  (setq *gc-vlab* xnames *gc-hlab* ynames)
  (gc:axes ents T both)
  (setq *gc-vlab* nil *gc-hlab* nil)
  (list (length xs) (length ys)))

(defun gc:write-dcl ( / f fn)
  (setq fn (findfile "GCCad.lsp"))
  (setq fn (if fn (strcat (vl-filename-directory fn) "/gcgrille.dcl")
                  (strcat (getvar "TEMPPREFIX") "gcgrille.dcl")))
  (setq f (open fn "w"))
  (if (null f) (progn (setq fn (strcat (getvar "TEMPPREFIX") "gcgrille.dcl")) (setq f (open fn "w"))))
  (foreach l
    (list "gcgrille : dialog { label = \"GCStructFlow - Grille d'axes\";"
      " : boxed_column { label = \"Axes verticaux (de gauche a droite)\";"
      "   : edit_box { key = \"xs\"; label = \"Entraxes (ex. 300 5*500 400)\"; edit_width = 42; }"
      "   : radio_row { key = \"xmode\";"
      "     : radio_button { key = \"x1\"; label = \"1 2 3\"; }"
      "     : radio_button { key = \"xA\"; label = \"A B C\"; }"
      "     : radio_button { key = \"xc\"; label = \"Noms personnalises\"; } }"
      "   : edit_box { key = \"xl\"; label = \"Noms (ex. 1 2 3 3' 4)\"; edit_width = 42; } }"
      " : boxed_column { label = \"Axes horizontaux (de bas en haut)\";"
      "   : edit_box { key = \"ys\"; label = \"Entraxes (ex. 600 3*600 175)\"; edit_width = 42; }"
      "   : radio_row { key = \"ymode\";"
      "     : radio_button { key = \"y1\"; label = \"1 2 3\"; }"
      "     : radio_button { key = \"yA\"; label = \"A B C\"; }"
      "     : radio_button { key = \"yc\"; label = \"Noms personnalises\"; } }"
      "   : edit_box { key = \"yl\"; label = \"Noms (ex. C F E B A A')\"; edit_width = 42; } }"
      " : boxed_column { label = \"Options (unites du dessin)\";"
      "   : edit_box { key = \"ext\"; label = \"Debord des axes au-dela de la grille\"; edit_width = 10; }"
      "   : toggle { key = \"bub\"; label = \"Annotations : bulles et noms d'axes\"; }"
      "   : toggle { key = \"both\"; label = \"Bulles des deux cotes\"; }"
      "   : toggle { key = \"dims\"; label = \"Annotations : cotes en chaine + cote totale\"; } }"
      " : text { key = \"info\"; label = \"\"; width = 60; }"
      " ok_cancel; }")
    (write-line l f))
  (close f)
  fn)

(defun gc:dlg-info ()
  (vl-catch-all-apply 'gc:dlg-info0 nil))

(defun gc:dlg-info0 ( / xs ys)
  (setq xs (gc:parse-spacing (get_tile "xs")) ys (gc:parse-spacing (get_tile "ys")))
  (set_tile "info" (strcat (itoa (1+ (length xs))) " axes verticaux (L = " (rtos (apply '+ (cons 0.0 xs)) 2 2) ")   "
                           (itoa (1+ (length ys))) " axes horizontaux (L = " (rtos (apply '+ (cons 0.0 ys)) 2 2) ")")))

(defun gc:dlg-accept ()
  (setq *gg-xs* (get_tile "xs") *gg-ys* (get_tile "ys") *gg-xl* (get_tile "xl") *gg-yl* (get_tile "yl")
        *gg-xmode* (get_tile "xmode") *gg-ymode* (get_tile "ymode") *gg-ext* (get_tile "ext")
        *gg-both* (get_tile "both") *gg-dims* (get_tile "dims") *gg-bub* (get_tile "bub"))
  (done_dialog 1))

(defun c:GCGRILLE ( / *error* id ok org xsp ysp xn yn res fn)
  (setq *error* (lambda (m) (gc:restore-vars) (princ (strcat "\nGCGRILLE – erreur : " m)) (princ)))
  (setq fn (gc:write-dcl))
  (setq id (load_dialog fn))
  (cond
    ((< id 0) (princ (strcat "\nGCGRILLE : impossible de charger la fenêtre " fn)))
    ((not (new_dialog "gcgrille" id)) (princ (strcat "\nGCGRILLE : fenêtre invalide dans " fn)) (unload_dialog id))
    (t (gc:grille-dialog id)))
  (princ))

(defun gc:grille-dialog (id / ok org xsp ysp xn yn res)
  (set_tile "xs" *gg-xs*) (set_tile "ys" *gg-ys*) (set_tile "xl" *gg-xl*) (set_tile "yl" *gg-yl*)
  (set_tile *gg-xmode* "1") (set_tile *gg-ymode* "1") (set_tile "ext" *gg-ext*)
  (set_tile "both" *gg-both*) (set_tile "dims" *gg-dims*) (set_tile "bub" *gg-bub*)
  (gc:dlg-info)
  (action_tile "xs" "(gc:dlg-info)")
  (action_tile "ys" "(gc:dlg-info)")
  (action_tile "accept" "(gc:dlg-accept)")
  (setq ok (start_dialog))
  (unload_dialog id)
  (if (= ok 1)
    (progn
      (setq xsp (gc:parse-spacing *gg-xs*) ysp (gc:parse-spacing *gg-ys*))
      (setq xn (gc:names (1+ (length xsp)) (cond ((= *gg-xmode* "x1") "n") ((= *gg-xmode* "xc") "c") (t "a")) (gc:split *gg-xl*))
            yn (gc:names (1+ (length ysp)) (cond ((= *gg-ymode* "y1") "n") ((= *gg-ymode* "yc") "c") (t "a")) (gc:split *gg-yl*)))
      (setq org (getpoint "\nPoint d'insertion (premier axe vertical x premier axe horizontal) <0,0> : "))
      (if (null org) (setq org '(0.0 0.0 0.0)))
      (gc:save-vars)
      (setq *gc-nobub* (= *gg-bub* "0") *gc-nodims* (= *gg-dims* "0"))
      (command "_.UNDO" "_BE")
      (setq res (gc:grille xsp ysp org (atof *gg-ext*) (= *gg-both* "1") xn yn))
      (command "_.UNDO" "_E")
      (setq *gc-nobub* nil *gc-nodims* nil)
      (gc:restore-vars)
      (princ (strcat "\nGCGRILLE : " (itoa (car res)) " axes verticaux, " (itoa (cadr res)) " axes horizontaux."))))
  (princ))

(princ "\nGCGRILLE : fenetre de creation de grille d'axes (entraxes, noms, annotations).")
(princ)
