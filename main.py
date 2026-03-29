# -*- coding: utf-8 -*-
# =============================================================================
# main.py  --  SIGES — Sistema de Gestion de Eventos en Salud
#
# FLUJO GENERAL:
#   1. Verificar / configurar conexion a la BD (config_conexion).
#   2. Mostrar ventana de Login.
#   3. Al login exitoso, construir el ejecutor y lanzar la ventana
#      principal del rol correspondiente (admin / ops / maestro).
#   4. La ventana principal integra todos los modulos en un layout
#      responsivo con sidebar de navegacion.
#   5. Al cerrar sesion volver al Login.
#
# ROLES Y VENTANAS:
#   admin   -> VentanaPrincipal con modulos: OPS, EPS, Pacientes,
#              Afiliaciones, Eventos, Reportes, Ajustes
#   ops     -> VentanaPrincipal con modulos: EPS (OPS), Pacientes,
#              Afiliaciones, Eventos, Reportes
#   maestro -> VentanaPrincipal con modulos: Entidades, OPS, EPS,
#              Pacientes, Afiliaciones, Eventos, Reportes, Ajustes
#
# RESPONSIVIDAD:
#   >= 1200px  sidebar 220px expandida
#   768-1199px sidebar 60px solo iconos
#   < 768px    sidebar oculta + bottom navigation bar
#
# VERSION: 1.0  |  Python 3.11+  |  PySide6
# =============================================================================

from __future__ import annotations

import sys
import io
import logging
from typing import Optional

# Forzar UTF-8 en stdout (Windows)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QScrollArea, QSpacerItem,
    QMessageBox, QDialog,
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QSize, QPropertyAnimation,
    QEasingCurve, QThread,
)
from PySide6.QtGui import QCursor, QResizeEvent, QIcon, QFont

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("siges.main")

# ──────────────────────────────────────────────────────────────
# PALETA GLOBAL (compartida con todos los modulos)
# ──────────────────────────────────────────────────────────────
P = {
    "bg":      "#0D1117", "card":    "#161B22", "input":   "#21262D",
    "border":  "#30363D", "focus":   "#388BFD", "accent":  "#2D6ADF",
    "acc_h":   "#388BFD", "acc_lt":  "#1C3A6E",
    "ok":      "#3FB950", "err":     "#F85149", "warn":    "#D29922",
    "txt":     "#E6EDF3", "txt2":    "#8B949E", "muted":   "#484F58",
    "white":   "#FFFFFF",
}

STYLE_GLOBAL = f"""
QMainWindow, QWidget {{
    background-color: {P['bg']};
    color: {P['txt']};
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    font-size: 13px;
}}
QLabel  {{ background: transparent; }}
QDialog {{ background-color: {P['bg']}; }}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: transparent; width: 8px; height: 8px;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {P['border']}; border-radius: 4px; min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    height: 0; width: 0;
}}
QToolTip {{
    background: {P['card']}; color: {P['txt']};
    border: 1px solid {P['border']}; border-radius: 6px;
    padding: 5px 10px; font-size: 12px;
}}
"""

# ──────────────────────────────────────────────────────────────
# PUNTOS DE QUIEBRE RESPONSIVO
# ──────────────────────────────────────────────────────────────
BP_SIDEBAR_FULL    = 1200   # sidebar expandida con etiquetas
BP_SIDEBAR_ICONS   = 768    # sidebar solo iconos
# < 768  sidebar oculta, bottom nav visible


# ──────────────────────────────────────────────────────────────
# HELPERS UI
# ──────────────────────────────────────────────────────────────

def _sep_h() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(
        f"border: none; border-top: 1px solid {P['border']}; background: transparent;"
    )
    f.setFixedHeight(1)
    return f


def _lbl(txt: str, size=13, color=None, bold=False) -> QLabel:
    lb = QLabel(txt)
    c = color or P["txt"]; w = "700" if bold else "400"
    lb.setStyleSheet(
        f"color:{c}; font-size:{size}px; font-weight:{w}; background:transparent;"
    )
    return lb


# ══════════════════════════════════════════════════════════════
# SESION GLOBAL (singleton en memoria)
# Almacena los datos del usuario autenticado durante la sesion.
# ══════════════════════════════════════════════════════════════

class _Sesion:
    """
    Singleton de sesion. Campos disponibles tras login exitoso:

    Para admin (rol='admin'):
        rol        = 'admin'
        id         = entidad_id (str)
        entidad_id = int
        nombre     = nombre_entidad
        correo     = correo
        nit        = nit
        sesion_id  = uuid

    Para ops / maestro (rol='ops'):
        rol        = 'ops'
        id         = ops_id (str)
        ops_id     = int
        entidad_id = int
        nombre     = nombre_completo
        correo     = correo
        es_maestro = bool
        sesion_id  = uuid
    """
    rol:        str        = ""
    id:         str        = ""
    nombre:     str        = ""
    correo:     str        = ""
    sesion_id:  str        = ""
    entidad_id: int        = 0
    ops_id:     int | None = None
    nit:        str        = ""
    es_maestro: bool       = False

    @classmethod
    def cargar(cls, datos: dict) -> None:
        """Carga los datos del login exitoso."""
        cls.rol        = datos.get("rol", "")
        cls.id         = datos.get("id", "")
        cls.nombre     = datos.get("nombre", "")
        cls.correo     = datos.get("correo", "")
        cls.sesion_id  = datos.get("sesion_id", "")
        cls.nit        = datos.get("nit", "")

        if cls.rol == "admin":
            cls.entidad_id = int(datos.get("id", 0))
            cls.ops_id     = None
            cls.es_maestro = False
        else:
            # ops o maestro
            cls.entidad_id = int(datos.get("entidad_id", 0))
            cls.ops_id     = int(datos.get("id", 0))
            # Detectar maestro por nombre
            cls.es_maestro = str(cls.nombre).strip().lower().startswith("maestro")

    @classmethod
    def limpiar(cls) -> None:
        """Cierra la sesion y limpia todos los datos."""
        sesion_id = cls.sesion_id
        cls.rol = cls.id = cls.nombre = cls.correo = ""
        cls.sesion_id = cls.nit = ""
        cls.entidad_id = 0
        cls.ops_id     = None
        cls.es_maestro = False
        # Cerrar sesion en BD en hilo aparte para no bloquear UI
        if sesion_id:
            try:
                import login_backend as lb
                _CloseWorker(lb.cerrar_sesion, sesion_id).start()
            except Exception:
                pass

    @classmethod
    def construir_ejecutor(cls) -> dict:
        """
        Construye el ejecutor estandar compatible con todos los backends.
        """
        if cls.rol == "admin":
            return {
                "rol":        "admin",
                "ops_id":     None,
                "entidad_id": cls.entidad_id,
                "es_maestro": False,
                "nombre":     cls.nombre,
            }
        return {
            "rol":        "ops",
            "ops_id":     cls.ops_id,
            "entidad_id": cls.entidad_id,
            "es_maestro": cls.es_maestro,
            "nombre":     cls.nombre,
        }


class _CloseWorker(QThread):
    """Cierra sesion en BD sin bloquear la UI."""
    def __init__(self, fn, *args):
        super().__init__()
        self._fn   = fn
        self._args = args

    def run(self):
        try:
            self._fn(*self._args)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
# BOTON DE NAVEGACION EN SIDEBAR
# ══════════════════════════════════════════════════════════════

class _NavBtn(QPushButton):
    """
    Boton de sidebar que puede estar expandido (icono + texto)
    o colapsado (solo icono). Marca el item activo con borde lateral.
    """
    def __init__(self, ico: str, lbl: str, parent=None):
        super().__init__(parent)
        self._ico  = ico
        self._lbl  = lbl
        self._act  = False
        self._exp  = True   # True = expandido
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(48)
        self.setToolTip(lbl)
        self._render()

    def set_activo(self, v: bool):
        self._act = v
        self._render()

    def set_expandido(self, v: bool):
        self._exp = v
        self.setFixedWidth(220 if v else 60)
        self._render()

    def _render(self):
        if self._act:
            bg   = P["acc_lt"]; c = P["acc_h"]
            bord = f"border-left: 3px solid {P['accent']};"; fw = "700"
        else:
            bg   = "transparent"; c = P["txt2"]
            bord = "border-left: 3px solid transparent;"; fw = "500"
        txt = f"   {self._ico}   {self._lbl}" if self._exp else f"  {self._ico}"
        self.setText(txt)
        self.setStyleSheet(
            f"QPushButton {{ background:{bg}; color:{c}; border:none; {bord}"
            f"  border-radius:0; padding:0 12px; font-size:14px;"
            f"  font-weight:{fw}; text-align:left; }}"
            f"QPushButton:hover {{ background:{P['input']}; color:{P['txt']}; }}"
        )


# ══════════════════════════════════════════════════════════════
# SIDEBAR DE NAVEGACION
# ══════════════════════════════════════════════════════════════

class Sidebar(QWidget):
    """
    Panel de navegacion lateral.
    Emite: nav_solicitado(idx:int) al hacer clic en un item.
    """
    nav_solicitado = Signal(int)

    def __init__(self, items: list[tuple[str, str]], parent=None):
        """
        items: lista de (icono, etiqueta) para cada modulo.
        """
        super().__init__(parent)
        self._exp   = True
        self._btns: list[_NavBtn] = []
        self._items = items

        self.setFixedWidth(220)
        self.setStyleSheet(
            f"QWidget {{ background:{P['card']}; "
            f"border-right:1px solid {P['border']}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header: logo + toggle ──────────────────────────────
        hdr = QWidget(); hdr.setFixedHeight(64)
        hdr.setStyleSheet(
            f"background:{P['card']}; border-bottom:1px solid {P['border']};"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(16, 0, 10, 0); hl.setSpacing(10)

        logo_box = QLabel("S")
        logo_box.setFixedSize(34, 34)
        logo_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_box.setStyleSheet(
            f"background:{P['accent']}; color:white; border-radius:9px;"
            f"font-size:16px; font-weight:700;"
        )
        self._logo_txt = QLabel("SIGES")
        self._logo_txt.setStyleSheet(
            f"color:{P['white']}; font-size:15px; font-weight:700; background:transparent;"
        )
        self._tog = QPushButton("◀")
        self._tog.setFixedSize(28, 28)
        self._tog.setStyleSheet(
            f"QPushButton {{ background:{P['input']}; color:{P['txt2']};"
            f"  border:1px solid {P['border']}; border-radius:6px; font-size:12px; }}"
            f"QPushButton:hover {{ background:{P['border']}; color:{P['txt']}; }}"
        )
        self._tog.clicked.connect(self.toggle)
        hl.addWidget(logo_box)
        hl.addWidget(self._logo_txt, 1)
        hl.addWidget(self._tog)
        root.addWidget(hdr)

        # ── Items de navegacion ────────────────────────────────
        sec = QWidget(); sec.setStyleSheet("background:transparent; border:none;")
        sl = QVBoxLayout(sec)
        sl.setContentsMargins(0, 12, 0, 8); sl.setSpacing(2)

        self._sec_lbl = QLabel("  MODULOS")
        self._sec_lbl.setStyleSheet(
            f"color:{P['muted']}; font-size:10px; font-weight:700;"
            f"letter-spacing:1.5px; padding:0 16px 6px; background:transparent;"
        )
        sl.addWidget(self._sec_lbl)

        for idx, (ico, lbl) in enumerate(items):
            b = _NavBtn(ico, lbl)
            b.setFixedWidth(220)
            b.clicked.connect(lambda checked=False, i=idx: self.nav_solicitado.emit(i))
            self._btns.append(b)
            sl.addWidget(b)

        root.addWidget(sec)
        root.addStretch()

        # ── Pie: separador ─────────────────────────────────────
        root.addWidget(_sep_h())
        self._pie = QWidget(); self._pie.setFixedHeight(60)
        self._pie.setStyleSheet(f"background:{P['card']};")
        pl = QVBoxLayout(self._pie)
        pl.setContentsMargins(16, 8, 16, 8); pl.setSpacing(2)
        self._pie_nom = QLabel("")
        self._pie_nom.setStyleSheet(
            f"color:{P['txt']}; font-size:12px; font-weight:700; background:transparent;"
        )
        self._pie_rol = QLabel("")
        self._pie_rol.setStyleSheet(
            f"color:{P['acc_h']}; font-size:10px; background:transparent;"
        )
        pl.addWidget(self._pie_nom); pl.addWidget(self._pie_rol)
        root.addWidget(self._pie)

    # ── API publica ────────────────────────────────────────────

    def set_activo(self, idx: int):
        for i, b in enumerate(self._btns):
            b.set_activo(i == idx)

    def set_usuario(self, nombre: str, rol_txt: str):
        self._pie_nom.setText(nombre[:26])
        self._pie_rol.setText(rol_txt)

    def toggle(self):
        self._exp = not self._exp
        ancho = 220 if self._exp else 60
        self.setFixedWidth(ancho)
        self._tog.setText("◀" if self._exp else "▶")
        self._logo_txt.setVisible(self._exp)
        self._sec_lbl.setVisible(self._exp)
        self._pie_nom.setVisible(self._exp)
        self._pie_rol.setVisible(self._exp)
        for b in self._btns:
            b.set_expandido(self._exp)

    def colapsar(self):
        if self._exp: self.toggle()

    def expandir(self):
        if not self._exp: self.toggle()


# ══════════════════════════════════════════════════════════════
# BOTTOM NAVIGATION (pantallas pequenas < 768px)
# ══════════════════════════════════════════════════════════════

class BottomNav(QWidget):
    """Barra inferior para pantallas pequenas."""
    nav_solicitado = Signal(int)

    def __init__(self, items: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setFixedHeight(62)
        self.setStyleSheet(
            f"QWidget {{ background:{P['card']}; "
            f"border-top:1px solid {P['border']}; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)

        self._btns: list[QPushButton] = []
        for idx, (ico, lbl) in enumerate(items):
            # Mostrar maximo 5 items; el resto en overflow
            if idx >= 5: break
            b = QPushButton(f"{ico}\n{lbl[:8]}")
            b.setCheckable(True)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            b.setStyleSheet(
                f"QPushButton {{ background:{P['card']}; color:{P['txt2']};"
                f"  border:none; padding:4px 2px; font-size:10px; font-weight:600; }}"
                f"QPushButton:checked {{ color:{P['acc_h']};"
                f"  border-top:2px solid {P['accent']}; }}"
                f"QPushButton:hover {{ background:{P['input']}; }}"
            )
            b.clicked.connect(lambda checked=False, i=idx: self._on_click(i))
            self._btns.append(b)
            lay.addWidget(b)

    def set_activo(self, idx: int):
        for i, b in enumerate(self._btns):
            b.setChecked(i == idx)

    def _on_click(self, idx: int):
        self.set_activo(idx)
        self.nav_solicitado.emit(idx)


# ══════════════════════════════════════════════════════════════
# TOP BAR
# ══════════════════════════════════════════════════════════════

class TopBar(QWidget):
    """Barra superior con titulo del modulo activo y boton cerrar sesion."""
    cerrar_sesion_solicitado = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(56)
        self.setStyleSheet(
            f"QWidget {{ background:{P['card']}; "
            f"border-bottom:1px solid {P['border']}; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 16, 0); lay.setSpacing(8)

        self._breadcrumb = QLabel("SIGES")
        self._breadcrumb.setStyleSheet(
            f"color:{P['txt2']}; font-size:12px; background:transparent;"
        )
        self._titulo = QLabel("")
        self._titulo.setStyleSheet(
            f"color:{P['txt']}; font-size:15px; font-weight:700; background:transparent;"
        )

        lay.addWidget(self._breadcrumb)
        sep = QLabel(" / ")
        sep.setStyleSheet(f"color:{P['muted']}; font-size:12px; background:transparent;")
        lay.addWidget(sep)
        lay.addWidget(self._titulo)
        lay.addStretch()

        # Boton cerrar sesion
        btn_out = QPushButton("Cerrar sesion")
        btn_out.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_out.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{P['txt2']};"
            f"  border:1px solid {P['border']}; border-radius:6px;"
            f"  padding:6px 14px; font-size:12px; }}"
            f"QPushButton:hover {{ border-color:{P['err']}; color:{P['err']};"
            f"  background:rgba(248,81,73,.08); }}"
        )
        btn_out.clicked.connect(self.cerrar_sesion_solicitado.emit)
        lay.addWidget(btn_out)

    def set_modulo(self, nombre: str):
        self._titulo.setText(nombre)


# ══════════════════════════════════════════════════════════════
# VENTANA PRINCIPAL
# ══════════════════════════════════════════════════════════════

class VentanaPrincipal(QMainWindow):
    """
    Shell principal del sistema tras el login.
    Integra sidebar + topbar + stack de modulos.

    Los modulos se cargan de forma lazy (solo al activarse por primera vez)
    para reducir el tiempo de arranque.
    """
    sesion_cerrada = Signal()

    # Definicion de modulos por rol:
    # (icono, etiqueta, clave_modulo)
    _MODULOS_ADMIN = [
        ("U", "Usuarios OPS",    "ops"),
        ("E", "EPS",             "eps"),
        ("P", "Pacientes",       "pacientes"),
        ("A", "Afiliaciones",    "afiliaciones"),
        ("V", "Eventos",         "eventos"),
        ("R", "Reportes",        "reportes"),
        ("C", "Configuracion",   "config"),
    ]
    _MODULOS_OPS = [
        ("E", "EPS",             "eps_ops"),
        ("P", "Pacientes",       "pacientes"),
        ("A", "Afiliaciones",    "afiliaciones"),
        ("V", "Eventos",         "eventos"),
        ("R", "Reportes",        "reportes"),
    ]
    _MODULOS_MAESTRO = [
        ("H", "Entidades",       "entidades"),
        ("U", "Usuarios OPS",    "ops"),
        ("E", "EPS",             "eps"),
        ("P", "Pacientes",       "pacientes"),
        ("A", "Afiliaciones",    "afiliaciones"),
        ("V", "Eventos",         "eventos"),
        ("R", "Reportes",        "reportes"),
        ("C", "Configuracion",   "config"),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SIGES — Sistema de Gestion de Eventos en Salud")
        self.setMinimumSize(400, 520)
        self.setStyleSheet(STYLE_GLOBAL)

        # Dimensionar al 90% de la pantalla disponible
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.resize(
                min(int(geo.width()  * 0.90), 1600),
                min(int(geo.height() * 0.90), 1000),
            )
        else:
            self.resize(1280, 800)

        self._modulos_def: list[tuple[str, str, str]] = []
        self._widgets_modulo: dict[int, QWidget]       = {}
        self._idx_activo: int = 0

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Fila horizontal: sidebar + contenido
        h_row = QWidget()
        h_row.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        hl = QHBoxLayout(h_row)
        hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(0)

        # Sidebar (se instancia vacia; se rellena en cargar_sesion)
        self._sidebar = Sidebar([])
        self._sidebar.nav_solicitado.connect(self._activar_modulo)
        hl.addWidget(self._sidebar)

        # Panel derecho: topbar + stack
        right = QWidget(); right.setStyleSheet(f"background:{P['bg']};")
        rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)

        self._topbar = TopBar()
        self._topbar.cerrar_sesion_solicitado.connect(self._pedir_cerrar_sesion)
        rl.addWidget(self._topbar)

        self._stack = QStackedWidget()
        rl.addWidget(self._stack, 1)
        hl.addWidget(right, 1)

        root.addWidget(h_row, 1)

        # Bottom nav (oculta por defecto)
        self._bottom = BottomNav([])
        self._bottom.nav_solicitado.connect(self._activar_modulo)
        self._bottom.hide()
        root.addWidget(self._bottom)

    # ── Inicio de sesion ───────────────────────────────────────

    def cargar_sesion(self):
        """
        Llama tras login exitoso. Construye la lista de modulos
        segun el rol y carga el primer modulo activo.
        """
        if _Sesion.es_maestro:
            defs = self._MODULOS_MAESTRO
            rol_txt = "Maestro"
        elif _Sesion.rol == "admin":
            defs = self._MODULOS_ADMIN
            rol_txt = "Administrador"
        else:
            defs = self._MODULOS_OPS
            rol_txt = "OPS"

        self._modulos_def = defs
        self._widgets_modulo.clear()

        # Reconstruir sidebar y bottom nav con los items del rol
        items = [(ico, lbl) for ico, lbl, _ in defs]
        self._sidebar.deleteLater()
        self._bottom.deleteLater()

        self._sidebar = Sidebar(items)
        self._sidebar.nav_solicitado.connect(self._activar_modulo)
        self._sidebar.set_usuario(_Sesion.nombre, rol_txt)

        self._bottom = BottomNav(items)
        self._bottom.nav_solicitado.connect(self._activar_modulo)
        self._bottom.hide()

        # Reinsertar en el layout
        central = self.centralWidget()
        root: QVBoxLayout = central.layout()
        h_row: QWidget    = root.itemAt(0).widget()
        hl: QHBoxLayout   = h_row.layout()

        # Limpiar stack
        while self._stack.count():
            w = self._stack.widget(0)
            self._stack.removeWidget(w)
            w.deleteLater()

        # Placeholder para cada modulo (carga lazy)
        for _ in defs:
            ph = QWidget(); ph.setStyleSheet(f"background:{P['bg']};")
            self._stack.addWidget(ph)

        # Insertar sidebar al principio del h_row
        hl.insertWidget(0, self._sidebar)
        root.addWidget(self._bottom)

        self._activar_modulo(0)
        self._aplicar_resize()

    def _activar_modulo(self, idx: int):
        """Activa el modulo en el indice dado. Carga el widget si es la primera vez."""
        if idx < 0 or idx >= len(self._modulos_def):
            return
        self._idx_activo = idx
        _, lbl, clave = self._modulos_def[idx]
        self._topbar.set_modulo(lbl)
        self._sidebar.set_activo(idx)
        self._bottom.set_activo(idx)

        # Carga lazy del modulo
        if idx not in self._widgets_modulo:
            w = self._crear_modulo(clave)
            if w is None:
                w = self._placeholder_error(clave)
            self._widgets_modulo[idx] = w
            self._stack.removeWidget(self._stack.widget(idx))
            # Insertar en la posicion correcta
            # QStackedWidget no tiene insertWidget, asi que reemplazamos
            # el placeholder temporal con el widget real
            self._stack.insertWidget(idx, w)

        self._stack.setCurrentIndex(idx)

    def _crear_modulo(self, clave: str) -> QWidget | None:
        """
        Instancia el widget del modulo indicado segun el rol activo.
        Retorna None si el modulo no esta disponible para este rol.
        """
        ejecutor    = _Sesion.construir_ejecutor()
        entidad_id  = _Sesion.entidad_id
        ops_id      = _Sesion.ops_id
        nombre      = _Sesion.nombre
        rol         = "maestro" if _Sesion.es_maestro else _Sesion.rol

        try:
            # ── Entidades (solo maestro) ───────────────────────
            if clave == "entidades":
                from entidad_ui import EntidadWindow
                return EntidadWindow(ops_id=ops_id)

            # ── Usuarios OPS ───────────────────────────────────
            elif clave == "ops":
                from ops_ui import OpsWindow
                return OpsWindow(ejecutor=ejecutor)

            # ── EPS (admin / maestro) ──────────────────────────
            elif clave == "eps":
                from gestion_eps_ui import EpsWindow
                return EpsWindow(
                    entidad_id=entidad_id, rol=rol,
                    ops_id=ops_id, nombre_usuario=nombre,
                )

            # ── EPS (vista OPS) ────────────────────────────────
            elif clave == "eps_ops":
                from gestion_eps_ops_ui import EpsOpsWindow
                return EpsOpsWindow(
                    entidad_id=entidad_id,
                    ops_id=ops_id,
                    nombre_usuario=nombre,
                )

            # ── Pacientes ──────────────────────────────────────
            elif clave == "pacientes":
                from pacientes_ui import PacientesWindow
                return PacientesWindow(ejecutor=ejecutor, entidad_id=entidad_id)

            # ── Afiliaciones ───────────────────────────────────
            elif clave == "afiliaciones":
                from gestion_afiliacion_ui import AfiliacionWindow
                return AfiliacionWindow(
                    entidad_id=entidad_id,
                    rol=rol,
                    ops_id=ops_id,
                    nombre_usuario=nombre,
                )

            # ── Eventos ────────────────────────────────────────
            elif clave == "eventos":
                from gestion_eventos_ui import EventosWindow
                return EventosWindow(
                    rol=rol,
                    entidad_id=entidad_id,
                    ops_id=ops_id,
                    nombre_usuario=nombre,
                )

            # ── Reportes ───────────────────────────────────────
            elif clave == "reportes":
                from gestion_reportes_ui import ReportesWindow
                return ReportesWindow(
                    rol=rol,
                    entidad_id=entidad_id,
                    ops_id=ops_id,
                    nombre_usuario=nombre,
                    ops_nombre=nombre,
                )

            # ── Configuracion conexion ─────────────────────────
            elif clave == "config":
                from config_conexion_ui import ConfigConexionDialog
                # Para la seccion de ajustes mostramos un wrapper
                return _ConfigWrapper()

            else:
                return None

        except ImportError as e:
            logger.error("No se pudo importar modulo '%s': %s", clave, e)
            return self._placeholder_error(clave, str(e))
        except Exception as e:
            logger.exception("Error al crear modulo '%s'", clave)
            return self._placeholder_error(clave, str(e))

    def _placeholder_error(self, clave: str, detalle: str = "") -> QWidget:
        """Widget de error cuando un modulo no puede cargarse."""
        w = QWidget(); w.setStyleSheet(f"background:{P['bg']};")
        lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ico = QLabel("!"); ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ico.setStyleSheet(
            f"font-size:48px; color:{P['err']}; background:transparent;"
        )
        msg = QLabel(f"No se pudo cargar el modulo '{clave}'")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet(
            f"color:{P['txt']}; font-size:15px; font-weight:600; background:transparent;"
        )
        det = QLabel(detalle)
        det.setAlignment(Qt.AlignmentFlag.AlignCenter)
        det.setWordWrap(True)
        det.setStyleSheet(
            f"color:{P['txt2']}; font-size:12px; background:transparent;"
        )
        lay.addWidget(ico); lay.addSpacing(8)
        lay.addWidget(msg); lay.addWidget(det)
        return w

    # ── Cerrar sesion ──────────────────────────────────────────

    def _pedir_cerrar_sesion(self):
        """Muestra confirmacion antes de cerrar sesion."""
        box = QMessageBox(self)
        box.setWindowTitle("Cerrar sesion")
        box.setText(f"Hola <b>{_Sesion.nombre}</b>.<br>Estas seguro de que deseas cerrar sesion?")
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )
        box.button(QMessageBox.StandardButton.Yes).setText("Si, cerrar sesion")
        box.button(QMessageBox.StandardButton.Cancel).setText("Cancelar")
        box.setStyleSheet(
            f"QMessageBox {{ background:{P['card']}; color:{P['txt']}; }}"
            f"QLabel {{ color:{P['txt']}; }}"
            f"QPushButton {{ background:{P['accent']}; color:white; border:none;"
            f"  border-radius:6px; padding:8px 18px; font-size:13px; }}"
            f"QPushButton:hover {{ background:{P['acc_h']}; }}"
        )
        if box.exec() == QMessageBox.StandardButton.Yes:
            self._cerrar_sesion()

    def _cerrar_sesion(self):
        _Sesion.limpiar()
        self.sesion_cerrada.emit()

    # ── Responsividad ──────────────────────────────────────────

    def resizeEvent(self, e: QResizeEvent):
        super().resizeEvent(e)
        if not hasattr(self, "_resize_timer"):
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._aplicar_resize)
        self._resize_timer.start(60)

    def _aplicar_resize(self):
        w = self.width()
        if w < BP_SIDEBAR_ICONS:
            # Pantalla pequena: ocultar sidebar, mostrar bottom nav
            self._sidebar.hide()
            self._bottom.show()
        elif w < BP_SIDEBAR_FULL:
            # Pantalla media: sidebar colapsada (solo iconos)
            self._sidebar.show()
            self._bottom.hide()
            self._sidebar.colapsar()
        else:
            # Pantalla grande: sidebar expandida
            self._sidebar.show()
            self._bottom.hide()
            self._sidebar.expandir()


# ══════════════════════════════════════════════════════════════
# WRAPPER CONFIGURACION (modulo de ajustes dentro del shell)
# ══════════════════════════════════════════════════════════════

class _ConfigWrapper(QWidget):
    """
    Envuelve el dialogo de configuracion de BD como un widget
    embebido en el stack principal (no como un QDialog flotante).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{P['bg']};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.setSpacing(20)

        lay.addWidget(_lbl("Configuracion de conexion", 20, P["txt"], bold=True))
        lay.addWidget(_lbl(
            "Administra la conexion a la base de datos PostgreSQL del sistema.",
            13, P["txt2"]
        ))
        lay.addWidget(_sep_h())

        btn_config = QPushButton("Abrir configuracion de base de datos")
        btn_config.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_config.setFixedHeight(46)
        btn_config.setStyleSheet(
            f"QPushButton {{ background:{P['accent']}; color:white; border:none;"
            f"  border-radius:8px; padding:0 24px; font-size:14px; font-weight:600; }}"
            f"QPushButton:hover {{ background:{P['acc_h']}; }}"
        )
        btn_config.clicked.connect(self._abrir_config)
        lay.addWidget(btn_config)
        lay.addStretch()

    def _abrir_config(self):
        try:
            from config_conexion_ui import ConfigConexionDialog
            dlg = ConfigConexionDialog(parent=self.window())
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(
                self.window(), "Error",
                f"No se pudo abrir la configuracion:\n{e}"
            )


# ══════════════════════════════════════════════════════════════
# CONTROLADOR DE APLICACION
# Coordina: config -> login -> ventana principal -> login (loop)
# ══════════════════════════════════════════════════════════════

class AppController:
    """
    Coordina el ciclo de vida completo de la aplicacion:
      1. Verificar/configurar la conexion a BD.
      2. Mostrar el Login.
      3. Al login exitoso, mostrar la VentanaPrincipal.
      4. Al cerrar sesion, volver al Login (sin reiniciar el proceso).
    """

    def __init__(self, app: QApplication):
        self._app = app
        self._login_win:   "LoginWindow | None"       = None
        self._main_win:    "VentanaPrincipal | None"  = None

    def iniciar(self):
        """Punto de entrada: verificar BD y mostrar login."""
        self._verificar_conexion()

    def _verificar_conexion(self):
        """
        Verifica que la conexion a BD este configurada.
        Si no existe config o la conexion falla, abre el dialogo.
        """
        try:
            from config_conexion_ui import mostrar_config_si_necesario
            ok = mostrar_config_si_necesario(self._app)
            if not ok:
                # El usuario cancelo la configuracion -> salir
                QMessageBox.critical(
                    None,
                    "Sin conexion",
                    "No se pudo establecer conexion con la base de datos.\n"
                    "El sistema no puede iniciar.",
                )
                self._app.quit()
                return
        except ImportError:
            # Si config_conexion_ui no esta disponible, continuar igual
            logger.warning("config_conexion_ui no disponible. Continuando sin verificacion.")

        self._mostrar_login()

    def _mostrar_login(self):
        """Crea y muestra la ventana de Login."""
        try:
            from login_ui import LoginWindow
            self._login_win = LoginWindow()
            self._login_win.login_exitoso.connect(self._on_login_exitoso)
            self._login_win.show()
        except ImportError as e:
            QMessageBox.critical(
                None, "Error critico",
                f"No se pudo cargar el modulo de login:\n{e}"
            )
            self._app.quit()

    def _on_login_exitoso(self, datos: dict):
        """Callback del login exitoso. Carga la sesion y muestra el shell."""
        logger.info(
            "Login exitoso — rol=%s nombre=%s",
            datos.get("rol"), datos.get("nombre")
        )
        _Sesion.cargar(datos)

        # Crear ventana principal si no existe
        if self._main_win is None:
            self._main_win = VentanaPrincipal()
            self._main_win.sesion_cerrada.connect(self._on_sesion_cerrada)

        self._main_win.cargar_sesion()
        self._main_win.show()

        # Ocultar login
        if self._login_win:
            self._login_win.hide()

    def _on_sesion_cerrada(self):
        """Al cerrar sesion, ocultar el shell y mostrar el login de nuevo."""
        logger.info("Sesion cerrada — volviendo al login.")
        if self._main_win:
            self._main_win.hide()

        # Reutilizar el login existente o crear uno nuevo
        if self._login_win is None:
            self._mostrar_login()
        else:
            self._login_win.show()


# ══════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════

def main():
    # Alta resolucion DPI (4K, monitores de alta densidad)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("SIGES")
    app.setApplicationDisplayName("Sistema de Gestion de Eventos en Salud")
    app.setApplicationVersion("1.0")
    app.setStyleSheet(STYLE_GLOBAL)

    # Fuente base del sistema
    fuente = QFont("Segoe UI", 10)
    fuente.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(fuente)

    ctrl = AppController(app)
    ctrl.iniciar()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
