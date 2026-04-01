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

# Forzar UTF-8 en stdout (Windows).
# IMPORTANTE: verificar que stdout.buffer exista y no este cerrado
# antes de reasignar, para evitar el error "I/O operation on closed file"
# que ocurre cuando los modulos UI intentan reasignar sys.stdout en su
# importacion y el buffer ya fue cerrado por una reasignacion previa.
def _fijar_stdout_utf8() -> None:
    try:
        buf = getattr(sys.stdout, "buffer", None)
        if buf is not None and not getattr(buf, "closed", False):
            # Solo reasignar si aun no es un TextIOWrapper UTF-8
            enc = getattr(sys.stdout, "encoding", "").lower()
            if enc not in ("utf-8", "utf_8"):
                sys.stdout = io.TextIOWrapper(
                    buf, encoding="utf-8", errors="replace"
                )
    except Exception:
        pass  # En entornos donde stdout no tiene buffer (pytest, etc.)

_fijar_stdout_utf8()

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

    def actualizar_items(self, items: list[tuple[str, str]]):
        """
        Reemplaza los botones de navegacion con una nueva lista de items.
        Llamado al cambiar de sesion / rol sin destruir la sidebar.
        """
        # Eliminar botones actuales
        for b in self._btns:
            b.setParent(None)
            b.deleteLater()
        self._btns.clear()
        self._items = items

        # Recrear botones en el layout de la seccion
        # El layout de sec es el segundo item en root (idx 1)
        # Buscamos la seccion por su widget hijo _sec_lbl
        sec_lay = self._sec_lbl.parent().layout()
        # Limpiar items de navegacion (dejar solo _sec_lbl)
        while sec_lay.count() > 1:
            item = sec_lay.takeAt(1)
            if item.widget():
                item.widget().deleteLater()

        for idx, (ico, lbl) in enumerate(items):
            b = _NavBtn(ico, lbl)
            b.setFixedWidth(220 if self._exp else 60)
            b.set_expandido(self._exp)
            b.clicked.connect(lambda checked=False, i=idx: self.nav_solicitado.emit(i))
            self._btns.append(b)
            sec_lay.addWidget(b)

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

    def actualizar_items(self, items: list[tuple[str, str]]):
        """Reemplaza los botones del bottom nav con la nueva lista de items."""
        lay = self.layout()
        for b in self._btns:
            b.setParent(None)
            b.deleteLater()
        self._btns.clear()
        for idx, (ico, lbl) in enumerate(items):
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


def _wrap(widget: QWidget) -> QWidget:
    """
    Envuelve un Tab/Panel en un QWidget con fondo y margen cero,
    para embeber correctamente en el QStackedWidget del shell.
    El widget ocupa todo el espacio disponible.
    """
    container = QWidget()
    container.setStyleSheet(f"background:{P['bg']};")
    lay = QVBoxLayout(container)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.addWidget(widget, 1)
    return container


class _OpsLoader(QWidget):
    """
    Carga el modulo de Usuarios OPS instanciando PanelOps directamente.

    obtener_tipos_documento() es una consulta SQL simple y rapida
    (tabla pequena, sin joins pesados), por lo que corre en el hilo
    principal sin afectar la experiencia del usuario.

    Eliminar el hilo evita problemas con el sistema de senales de Qt
    en Windows cuando QThread se define como clase anidada.
    """

    def __init__(self, ejecutor: dict, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{P['bg']};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        try:
            import ops_backend as bk
            from ops_ui import PanelOps

            tipos = bk.obtener_tipos_documento()
            if not isinstance(tipos, list):
                tipos = []

            panel = PanelOps(ejecutor, tipos, self)
            lay.addWidget(panel, 1)

        except Exception as e:
            logger.error("Error al cargar modulo OPS: %s", e)
            lbl = QLabel(
                f"No se pudo cargar el modulo de usuarios OPS.\n\n{e}"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                f"color:{P['err']}; font-size:13px; background:transparent;"
            )
            lay.addWidget(lbl, 1)


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
        self._h_row = QWidget()
        self._h_row.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        hl = QHBoxLayout(self._h_row)
        hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(0)

        # Sidebar (vacia al inicio; se rellena en cargar_sesion)
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

        root.addWidget(self._h_row, 1)

        # Bottom nav (oculta por defecto)
        self._bottom = BottomNav([])
        self._bottom.nav_solicitado.connect(self._activar_modulo)
        self._bottom.hide()
        root.addWidget(self._bottom)

    # ── Inicio de sesion ───────────────────────────────────────

    def cargar_sesion(self):
        """
        Llama tras login exitoso. Reconstruye la lista de modulos segun
        el rol activo y carga el primer modulo. Limpia el estado anterior
        correctamente para permitir cerrar sesion y volver a entrar.
        """
        if _Sesion.es_maestro:
            defs    = self._MODULOS_MAESTRO
            rol_txt = "Maestro"
        elif _Sesion.rol == "admin":
            defs    = self._MODULOS_ADMIN
            rol_txt = "Administrador"
        else:
            defs    = self._MODULOS_OPS
            rol_txt = "OPS"

        self._modulos_def = defs

        # Limpiar modulos cargados previamente
        self._widgets_modulo.clear()

        # Vaciar el stack
        while self._stack.count():
            w = self._stack.widget(0)
            self._stack.removeWidget(w)
            w.deleteLater()

        # Insertar un placeholder por cada modulo (carga lazy)
        for _ in defs:
            ph = QWidget()
            ph.setStyleSheet(f"background:{P['bg']};")
            self._stack.addWidget(ph)

        # Actualizar sidebar y bottom nav con los items del rol
        items = [(ico, lbl) for ico, lbl, _ in defs]
        self._sidebar.actualizar_items(items)
        self._sidebar.set_usuario(_Sesion.nombre, rol_txt)
        self._bottom.actualizar_items(items)

        self._activar_modulo(0)
        self._aplicar_resize()

    def _activar_modulo(self, idx: int):
        """
        Activa el modulo en el indice dado.
        Carga el widget la primera vez (lazy); las siguientes solo cambia
        el indice del stack sin crear ni destruir nada.
        """
        if idx < 0 or idx >= len(self._modulos_def):
            return
        self._idx_activo = idx
        _, lbl, clave = self._modulos_def[idx]
        self._topbar.set_modulo(lbl)
        self._sidebar.set_activo(idx)
        self._bottom.set_activo(idx)

        # Carga lazy: solo crea el widget la primera vez que se navega a el
        if idx not in self._widgets_modulo:
            w = self._crear_modulo(clave)
            if w is None:
                w = self._placeholder_error(clave)
            # Reemplazar el placeholder temporal en el stack
            ph = self._stack.widget(idx)
            self._stack.insertWidget(idx, w)
            if ph is not None:
                self._stack.removeWidget(ph)
                ph.deleteLater()
            self._widgets_modulo[idx] = w

        self._stack.setCurrentIndex(idx)

    def _crear_modulo(self, clave: str) -> QWidget | None:
        """
        Instancia el widget del modulo indicado segun el rol activo.

        REGLA CRITICA: nunca embeber Window completas (EventosWindow,
        ReportesWindow, etc.) porque traen su propia sidebar y topbar
        integradas, lo que genera sidebar duplicada dentro del shell.

        En su lugar se usan los Tab/Panel internos de cada modulo:
          TabEventos, TabReportes, TabEps, TabEpsOps, TabAfiliacion,
          PanelOps, PanelEntidad, PanelPacientes.

        Los modulos se envuelven en _wrap() para darles margen y
        fondo consistentes con el shell.
        """
        ejecutor   = _Sesion.construir_ejecutor()
        entidad_id = _Sesion.entidad_id
        ops_id     = _Sesion.ops_id
        nombre     = _Sesion.nombre
        rol        = "maestro" if _Sesion.es_maestro else _Sesion.rol

        try:
            # ── Entidades (solo maestro) ───────────────────────────
            if clave == "entidades":
                from entidad_ui import PanelEntidad
                return PanelEntidad(ops_id=ops_id)

            # ── Usuarios OPS ───────────────────────────────────────
            elif clave == "ops":
                # PanelOps necesita tipos_doc; se carga en _OpsLoader
                # para no bloquear el hilo principal.
                return _OpsLoader(ejecutor)

            # ── EPS (admin / maestro) ──────────────────────────────
            elif clave == "eps":
                from gestion_eps_ui import TabEps
                return _wrap(TabEps(rol=rol, entidad_id=entidad_id, ops_id=ops_id))

            # ── EPS (vista OPS regular) ────────────────────────────
            elif clave == "eps_ops":
                from gestion_eps_ops_ui import TabEpsOps
                return _wrap(TabEpsOps(entidad_id=entidad_id, ops_id=ops_id))

            # ── Pacientes ──────────────────────────────────────────
            elif clave == "pacientes":
                from pacientes_ui import PanelPacientes
                return PanelPacientes(ejecutor=ejecutor, entidad_id=entidad_id)

            # ── Afiliaciones ───────────────────────────────────────
            elif clave == "afiliaciones":
                from gestion_afiliacion_ui import TabAfiliacion
                return _wrap(TabAfiliacion(entidad_id=entidad_id))

            # ── Eventos ────────────────────────────────────────────
            elif clave == "eventos":
                from gestion_eventos_ui import TabEventos
                return _wrap(TabEventos(rol=rol, entidad_id=entidad_id, ops_id=ops_id))

            # ── Reportes ───────────────────────────────────────────
            elif clave == "reportes":
                from gestion_reportes_ui import TabReportes
                return _wrap(
                    TabReportes(
                        rol=rol, entidad_id=entidad_id,
                        ops_id=ops_id, ops_nombre=nombre,
                    )
                )

            # ── Configuracion conexion ─────────────────────────────
            elif clave == "config":
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
      1. Verificar / configurar la conexion a BD.
      2. Mostrar el Login.
      3. Al login exitoso, mostrar la VentanaPrincipal.
      4. Al cerrar sesion, volver al Login — sin reiniciar el proceso.

    El LoginWindow se crea UNA sola vez y se oculta/muestra segun el estado.
    La VentanaPrincipal tambien se crea una sola vez y recibe cargar_sesion()
    cada vez que el usuario hace login (puede ser distinto usuario/rol).
    """

    def __init__(self, app: QApplication):
        self._app       = app
        self._login_win: Optional["LoginWindow"]      = None
        self._main_win:  Optional["VentanaPrincipal"] = None

    # ── Arranque ───────────────────────────────────────────────

    def iniciar(self):
        """Punto de entrada: verificar BD y mostrar login."""
        self._verificar_conexion()

    # ── BD ─────────────────────────────────────────────────────

    def _verificar_conexion(self):
        """
        Verifica que la conexion a BD este configurada.
        Si no existe config o la conexion falla, abre el dialogo.
        Al terminar (exito o no) siempre muestra el Login.
        """
        try:
            from config_conexion_ui import mostrar_config_si_necesario
            ok = mostrar_config_si_necesario(self._app)
            if not ok:
                resp = QMessageBox.question(
                    None,
                    "Sin conexion",
                    "No se pudo establecer conexion con la base de datos.\n\n"
                    "Deseas intentar configurarla ahora?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if resp == QMessageBox.StandardButton.No:
                    self._app.quit()
                    return
        except ImportError:
            logger.warning(
                "config_conexion_ui no disponible. Continuando sin verificacion."
            )

        self._mostrar_login()

    # ── Login ──────────────────────────────────────────────────

    def _mostrar_login(self):
        """
        Muestra la ventana de Login.
        Si ya existe la reutiliza; si no, la crea.
        Al reutilizar limpia los campos y el status bar para que
        el usuario vea el formulario limpio tras cerrar sesion.
        """
        try:
            from login_ui import LoginWindow
        except ImportError as e:
            QMessageBox.critical(
                None, "Error critico",
                f"No se pudo cargar el modulo de login:\n{e}"
            )
            self._app.quit()
            return

        if self._login_win is None:
            self._login_win = LoginWindow()
            # Conectar la señal SOLO la primera vez que se crea
            self._login_win.login_exitoso.connect(self._on_login_exitoso)
        else:
            # Limpiar formulario para la proxima sesion
            self._limpiar_formulario_login()

        self._login_win.show()
        self._login_win.raise_()
        self._login_win.activateWindow()

    def _limpiar_formulario_login(self):
        """
        Limpia los campos del formulario de login y oculta mensajes
        de error para que el usuario vea un formulario en blanco.
        """
        win = self._login_win
        if win is None:
            return
        try:
            # Limpiar campo documento
            if hasattr(win, "f_doc"):
                win.f_doc.input.clear() if hasattr(win.f_doc, "input") \
                    else win.f_doc.clear()
            # Limpiar campo password
            if hasattr(win, "f_pw"):
                win.f_pw.input.clear() if hasattr(win.f_pw, "input") \
                    else win.f_pw.clear()
            # Ocultar mensajes de error/estado
            if hasattr(win, "status"):
                win.status.ocultar() if hasattr(win.status, "ocultar") \
                    else win.status.hide()
            # Rehabilitar boton login (puede quedar deshabilitado si hubo error)
            if hasattr(win, "btn_login"):
                win.btn_login.setEnabled(True)
                win.btn_login.setText("Iniciar sesión")
        except Exception as e:
            logger.debug("No se pudo limpiar formulario login: %s", e)

    # ── Login exitoso ──────────────────────────────────────────

    def _on_login_exitoso(self, datos: dict):
        """
        Callback del Signal login_exitoso de LoginWindow.
        Carga la sesion y muestra la VentanaPrincipal.
        """
        logger.info(
            "Login exitoso — rol=%s nombre=%s",
            datos.get("rol"), datos.get("nombre"),
        )
        _Sesion.cargar(datos)

        # Ocultar login ANTES de mostrar la ventana principal
        if self._login_win:
            self._login_win.hide()

        # Crear VentanaPrincipal una sola vez
        if self._main_win is None:
            self._main_win = VentanaPrincipal()
            self._main_win.sesion_cerrada.connect(self._on_sesion_cerrada)

        # Reconfigurar para el nuevo usuario/rol
        self._main_win.cargar_sesion()
        self._main_win.show()
        self._main_win.raise_()
        self._main_win.activateWindow()

    # ── Cierre de sesion ───────────────────────────────────────

    def _on_sesion_cerrada(self):
        """
        Al cerrar sesion:
          1. Ocultar la VentanaPrincipal completamente.
          2. Mostrar el Login con formulario limpio.
        La sesion ya fue limpiada en VentanaPrincipal._cerrar_sesion().
        """
        logger.info("Sesion cerrada — volviendo al login.")

        if self._main_win is not None:
            self._main_win.hide()

        # Mostrar login (limpia formulario si ya existia)
        self._mostrar_login()


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