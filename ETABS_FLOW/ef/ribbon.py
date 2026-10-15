"""Revit-style ribbon pinned to the ETABS window + single-instance launcher.

etabsflow.py --ribbon            → ribbon (default when started from the ETABS plugin)
etabsflow.py --tab "Sismique"    → open the main window on that tab
A second launch forwards its request to the running instance (QLocalServer) and exits.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

SERVER = "GCStructFlow-ETABS"

# (panel title, [(icon, label, action)])  action = tab text fragment | "!calc" | "!save" | "!connect" | "!main"
PANELS = [
    ("Modèle", [("📐", "Plan\nAutoCAD", "Plan"), ("⌨", "Script", "Script"), ("📏", "Sections\nmatériaux", "Sections")]),
    ("Charges", [("⚖", "Charges\ncombinaisons", "Charges"), ("🌍", "Sismique\nRPA 2024", "Sismique")]),
    ("Analyse", [("🚀", "Calculer", "!calc"), ("💾", "Enregistrer", "!save"), ("🔗", "Connecter", "!connect")]),
    ("Résultats", [("📊", "Efforts\nnotes", "Résultats"), ("⚓", "Fondations\nressorts", "Fondations")]),
    ("Outils", [("🔁", "Robot →\nETABS", "Robot"), ("🏗", "Semelles", "Semelles"), ("🏛", "Poteaux\nFCD", "Poteaux"),
                ("🗔", "Fenêtre\ncomplète", "!main")]),
]


def emoji_icon(ch, px=28):
    pm = QPixmap(px * 2, px * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    f = QFont("Segoe UI Emoji")
    f.setPixelSize(int(px * 1.5))
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, ch)
    p.end()
    pm.setDevicePixelRatio(2.0)
    return QIcon(pm)


def forward_to_running(request: str) -> bool:
    """True if another instance is running (request sent to it)."""
    s = QLocalSocket()
    s.connectToServer(SERVER)
    if not s.waitForConnected(300):
        return False
    s.write(request.encode("utf-8"))
    s.flush()
    s.waitForBytesWritten(500)
    s.disconnectFromServer()
    return True


VIEW_TITLES = ("Plan View", "3-D View", "Elevation View", "Section View", "Developed Elevation", "Perspective",
               "Custom View", "Story")


def _etabs_main():
    import win32gui

    found = []

    def cb(h, _):
        t = win32gui.GetWindowText(h)
        if win32gui.IsWindowVisible(h) and t.startswith("ETABS") and "GCStructFlow" not in t:
            found.append(h)
        return True

    win32gui.EnumWindows(cb, None)
    return found[0] if found else None


def _view_rect(hmain):
    """Screen rect (l, t, r, b) of the active ETABS view (document area below the view-tab row)."""
    import win32gui

    best = []

    def cb(h, _):
        if win32gui.IsWindowVisible(h) and win32gui.GetWindowText(h).startswith(VIEW_TITLES):
            l, t, r, b = win32gui.GetWindowRect(h)
            if r - l > 200 and b - t > 200:
                best.append((l, t, r, b))
        return True

    win32gui.EnumChildWindows(hmain, cb, None)
    if best:
        return max(best, key=lambda q: (q[2] - q[0]) * (q[3] - q[1]))
    l, t, r, b = win32gui.GetWindowRect(hmain)
    return l + 400, t + 160, r - 10, b - 40


class _Pinned(QWidget):
    """Frameless window owned by ETABS, repositioned on a timer."""

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint)
        self.etabs = None

    def ensure_owner(self):
        """Keep the window owned by ETABS (re-attach if Qt recreated the native window) and above ETABS."""
        import win32con
        import win32gui

        if not self.etabs or not win32gui.IsWindow(self.etabs):
            self.etabs = _etabs_main()
        if not self.etabs:
            return None
        hwnd = int(self.winId())
        if win32gui.GetWindow(hwnd, win32con.GW_OWNER) != self.etabs:
            win32gui.SetWindowLong(hwnd, win32con.GWL_HWNDPARENT, self.etabs)
        if self.isVisible() and win32gui.GetForegroundWindow() == self.etabs:
            try:
                win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 0, 0, 0, 0,
                                      win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
            except Exception:  # noqa: BLE001
                pass
        return self.etabs

    def ratio(self):
        return self.devicePixelRatioF() or 1.0


class Workspace(_Pinned):
    """Our tools as tabs laid over the ETABS view area (like an extra view tab)."""

    def __init__(self, main):
        super().__init__()
        from PySide6.QtWidgets import QPushButton, QTabWidget

        self.main = main
        self.setObjectName("ws")
        self.setStyleSheet("#ws { background: #f0f0f0; border: 1px solid #8fa8c8; }")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        back = QPushButton("◀ Vue ETABS")
        back.setToolTip("Masquer les outils GCStructFlow et revenir à la vue ETABS")
        back.clicked.connect(self.hide)
        self.tabs.setCornerWidget(back, Qt.TopRightCorner)
        v.addWidget(self.tabs)
        self.status = QLabel("")
        self.status.setStyleSheet("background:#e4e4e4; color:#333; padding:2px 6px; font: 8pt 'Segoe UI';")
        v.addWidget(self.status)
        self.home = {}                       # widget -> (index in main tabs, title)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.follow)
        self.timer.start(300)
        orig_log = main.log

        def log(msg, _orig=orig_log):
            _orig(msg)
            self.status.setText(str(msg).splitlines()[0] if msg else "")
        main.log = log

    def open(self, fragment):
        m = self.main
        for i in range(self.tabs.count()):
            if fragment in self.tabs.tabText(i):
                self.tabs.setCurrentIndex(i)
                return self.show_now()
        for i in range(m.tabs.count()):
            title = m.tabs.tabText(i)
            if fragment in title:
                w = m.tabs.widget(i)
                self.home[w] = (i, title)
                m.tabs.removeTab(i)
                self.tabs.addTab(w, title)
                self.tabs.setCurrentWidget(w)
                return self.show_now()

    def close_tab(self, i):
        w = self.tabs.widget(i)
        self.tabs.removeTab(i)
        idx, title = self.home.pop(w, (self.main.tabs.count(), "?"))
        self.main.tabs.insertTab(min(idx, self.main.tabs.count()), w, title)
        if self.tabs.count() == 0:
            self.hide()

    def return_all(self):
        order = sorted(range(self.tabs.count()), key=lambda i: self.home.get(self.tabs.widget(i), (99, ""))[0])
        widgets = [self.tabs.widget(i) for i in order]
        for w in widgets:
            self.close_tab(self.tabs.indexOf(w))
        self.hide()

    def show_now(self):
        self.follow(force=True)
        self.show()
        self.raise_()
        self.activateWindow()

    def follow(self, force=False):
        try:
            import win32gui
        except ImportError:
            return
        if not self.isVisible() and not force:
            return
        if not self.ensure_owner():
            return
        if win32gui.IsIconic(self.etabs):
            self.hide()
            return
        l, t, r, b = _view_rect(self.etabs)
        k = self.ratio()
        g = (int(l / k), int(t / k), int((r - l) / k), int((b - t) / k))
        if (self.x(), self.y(), self.width(), self.height()) != g:
            self.setGeometry(*g)


TOOLS = [  # (group, icon, tooltip, action, hotkey letter for Ctrl+Alt)
    ("Modèle", "🧭", "Assistant pas à pas (modèle → charges → sismique → calcul → vérifs → note)", "Assistant", "A"),
    ("Modèle", "📐", "Plan AutoCAD → modèle", "Plan", "P"),
    ("Modèle", "⌨", "Script (coller et exécuter)", "Script", "S"),
    ("Modèle", "📏", "Sections et matériaux", "Sections", "M"),
    ("Charges", "⚖", "Charges et combinaisons", "Charges", "C"),
    ("Charges", "🌍", "Sismique RPA 2024 (spectre, modale, Ex/Ey)", "Sismique", "E"),
    ("Analyse", "🚀", "Calculer (enregistre puis lance l'analyse)", "!calc", "R"),
    ("Analyse", "💾", "Enregistrer le modèle", "!save", None),
    ("Analyse", "🔗", "Reconnecter à ETABS", "!connect", None),
    ("Résultats", "📊", "Efforts, vérifications, Excel / Word", "Résultats", "F"),
    ("Résultats", "✅", "Vérifications RPA 2024 (V_dyn, drift, P-Δ, interaction…)", "Vérifs", "K"),
    ("Résultats", "🧮", "Ferraillage en masse (poteaux POTEAUX_FCD, poutres)", "Ferraillage", "D"),
    ("Résultats", "⚓", "Fondations, ressorts, contraintes du sol", "Fondations", "O"),
    ("Outils", "🔁", "Robot → ETABS", "Robot", None),
    ("Outils", "🏗", "Semelles isolées (votre application)", "Semelles", None),
    ("Outils", "🏛", "Poteaux FCD (votre application)", "Poteaux", None),
    ("Outils", "🗺", "Afficher / masquer les onglets GCStructFlow", "!toggle", "V"),
    ("Outils", "🖥", "Fenêtre complète", "!main", None),
]


def _toolbar_slot(hmain):
    """(x, y, h) in screen px: right after the last toolbar of the lowest ETABS toolbar row."""
    import win32gui

    bars = []

    def cb(c, _):
        if win32gui.IsWindowVisible(c) and win32gui.GetWindowText(c) and win32gui.GetWindowText(c) != "MenuBar":
            l, t, r, b = win32gui.GetWindowRect(c)
            if 20 <= b - t <= 40 and r - l > 40:
                bars.append((t, l, r, b))
        return True

    win32gui.EnumChildWindows(hmain, cb, None)
    _ml, mt, _mr, _mb = win32gui.GetWindowRect(hmain)
    bars = [q for q in bars if q[0] < mt + 260]
    if not bars:
        return None
    top = max(q[0] for q in bars)
    row = [q for q in bars if abs(q[0] - top) <= 3]
    right = max(q[2] for q in row)
    return right + 4, top, row[0][3] - row[0][0]


class Ribbon(_Pinned):
    """ETABS-style toolbar docked at the end of the lowest ETABS toolbar row (+ Ctrl+Alt shortcuts)."""

    WM_HOTKEY = 0x0312

    def __init__(self, main):
        super().__init__()
        from PySide6.QtCore import QSettings

        self.main = main
        self.ws = Workspace(main)
        self._drag = None
        self.settings = QSettings("GCStructFlow", "EtabsToolbar")
        off = self.settings.value("offset")
        self.offset = tuple(int(v) for v in off) if off else None
        self.setObjectName("bar")
        self.setStyleSheet(
            "#bar { background: #f0f0f0; }"
            "QToolButton { border: 1px solid transparent; border-radius: 2px; padding: 1px; margin: 0; }"
            "QToolButton:hover { background: #cde4f7; border-color: #7eb4ea; }"
            "QToolButton:pressed { background: #a8d0f0; }"
            "QFrame#sep { color: #c0c0c0; }"
            "QLabel#grip { color: #a0a0a0; font: 8pt 'Segoe UI'; padding: 0 1px; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(1, 0, 1, 0)
        lay.setSpacing(1)
        grip = QLabel("⋮")
        grip.setObjectName("grip")
        grip.setToolTip("GCStructFlow – glisser pour déplacer · double-clic : position automatique")
        grip.setCursor(Qt.SizeAllCursor)
        lay.addWidget(grip)
        self.hotkeys = {}
        group = None
        for g, icon, tip, action, key in TOOLS:
            if group is not None and g != group:
                sep = QFrame()
                sep.setObjectName("sep")
                sep.setFrameShape(QFrame.VLine)
                sep.setFixedWidth(5)
                lay.addWidget(sep)
            group = g
            b = QToolButton()
            b.setIcon(emoji_icon(icon, 20))
            b.setIconSize(QSize(20, 20))
            b.setFixedSize(QSize(25, 25))
            b.setAutoRaise(True)
            b.setToolTip(f"<b>{tip}</b>" + (f"<br>Ctrl+Alt+{key}" if key else "") + f"<br><i>GCStructFlow · {g}</i>")
            b.clicked.connect(lambda _=False, a=action: self.do(a))
            lay.addWidget(b)
            if key:
                self.hotkeys[ord(key)] = action
        self.hotkeys[ord("G")] = "!show"                       # rescue: bring the bar back
        self.adjustSize()
        self.setFixedSize(self.sizeHint())
        self._hk_hwnd = None
        self._register_hotkeys()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.follow)
        self.timer.start(300)
        self.follow()

    # ------------------------------------------------------------------ shortcuts Ctrl+Alt+<key> (active over ETABS only)
    def _register_hotkeys(self):
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            if self._hk_hwnd == hwnd:
                return
            self._hk_hwnd = hwnd
            MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x1, 0x2, 0x4000
            for vk in self.hotkeys:
                user32.RegisterHotKey(hwnd, vk, MOD_ALT | MOD_CONTROL | MOD_NOREPEAT, vk)
        except Exception:  # noqa: BLE001
            pass

    def nativeEvent(self, event_type, message):
        try:
            import ctypes
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(int(message))
            if msg.message == self.WM_HOTKEY and msg.wParam in self.hotkeys:
                fg = ctypes.windll.user32.GetForegroundWindow()
                ours = {int(self.winId()), int(self.ws.winId()), int(self.main.winId())}
                if fg == self.etabs or fg in ours or self.hotkeys[msg.wParam] == "!show":
                    self.do(self.hotkeys[msg.wParam])
                return True, 0
        except Exception:  # noqa: BLE001
            pass
        return False, 0

    # ------------------------------------------------------------------ actions
    def do(self, action):
        m = self.main
        if action == "!show":
            self.offset = None
            self.settings.remove("offset")
            self.show()
            self.follow()
            self.raise_()
            return
        if action == "!calc":
            m.calculate()
        elif action == "!save":
            m.save_project()
        elif action == "!connect":
            m.connect_robot()
        elif action == "!toggle":
            if self.ws.isVisible():
                self.ws.hide()
            elif self.ws.tabs.count():
                self.ws.show_now()
            else:
                self.ws.open("Plan")
        elif action == "!main":
            self.ws.return_all()
            m.showNormal()
            m.raise_()
            m.activateWindow()
        else:
            self.ws.open(action)

    def close_all(self):
        self.timer.stop()
        self.ws.return_all()
        self.hide()

    # ------------------------------------------------------------------ position: end of the lowest toolbar row
    def follow(self):
        try:
            import win32gui
        except ImportError:
            return
        if not self.ensure_owner():
            return
        if win32gui.IsIconic(self.etabs):
            if self.isVisible():
                self.hide()
            return
        if not self.isVisible():
            self.show()
        self._register_hotkeys()                       # no-op unless the native window was recreated
        if self._drag is not None:
            return
        k = self.ratio()
        if self.offset is None:
            slot = _toolbar_slot(self.etabs)
            if not slot:
                l, t, _r, _b = win32gui.GetWindowRect(self.etabs)
                slot = (l + 300, t + 110, 27)
            x, y, h = slot
            target = QPoint(int(x / k), int(y / k) + max(0, (int(h / k) - self.height()) // 2))
        else:
            l, t, _r, _b = win32gui.GetWindowRect(self.etabs)
            target = QPoint(int(l / k) + self.offset[0], int(t / k) + self.offset[1])
        if self.pos() != target:
            self.move(target)

    # ------------------------------------------------------------------ drag the grip → manual position (remembered)
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        if self._drag is not None and self.etabs:
            import win32gui

            k = self.ratio()
            l, t, _r, _b = win32gui.GetWindowRect(self.etabs)
            self.offset = (self.x() - int(l / k), self.y() - int(t / k))
            self.settings.setValue("offset", list(self.offset))
        self._drag = None

    def mouseDoubleClickEvent(self, e):
        self.offset = None
        self.settings.remove("offset")
        self.follow()


def start_server(main, ribbon_factory):
    """Listen for requests from later launches ('ribbon' or 'tab:<text>')."""
    QLocalServer.removeServer(SERVER)
    srv = QLocalServer(main)
    srv.listen(SERVER)

    def on_conn():
        c = srv.nextPendingConnection()
        c.waitForReadyRead(500)
        req = bytes(c.readAll()).decode("utf-8", "ignore").strip()
        handle_request(main, ribbon_factory, req)
        c.disconnectFromServer()

    srv.newConnection.connect(on_conn)
    return srv


def handle_request(main, ribbon_factory, req):
    rb = ribbon_factory()
    rb.show()
    rb.raise_()
    if req.startswith("tab:"):
        rb.ws.open(req[4:])
