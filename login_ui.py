# -*- coding: utf-8 -*-
# =============================================================================
# login_ui.py
# Interfaz de autenticación PySide6 — Sistema de Gestión de Eventos (SIGES)
#
# COMPATIBILIDAD:
#   - Usa login_backend.py (que usa conexion.py internamente).
#   - Sin imports de db_conexion ni auth_backend.
#
# PANTALLAS:
#   LoginWindow          → inicio de sesión (admin por NIT / OPS por doc)
#   RegistroOpsDialog    → registro de usuario OPS
#   RegistroEntidadDialog→ registro de entidad/administrador
#   RecuperarPaso1       → solicitar código OTP
#   RecuperarPaso2       → ingresar código OTP (6 dígitos)
#   RecuperarPaso3       → establecer nueva contraseña
#   CambiarPasswordDialog→ cambio de contraseña con sesión activa
#
# SEÑAL:
#   LoginWindow.login_exitoso(dict) emite:
#     {rol, id, nombre, correo, sesion_id, [entidad_id], [nit]}
# =============================================================================

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QLineEdit, QPushButton,
    QFrame, QSizePolicy,
    QListWidget, QListWidgetItem,
    QAbstractItemView,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import (
    Qt, Signal, QThread, QTimer, QPropertyAnimation,
    QEasingCurve, QSize,
)
from PySide6.QtGui import QCursor, QResizeEvent, QIcon, QFont

import login_backend as bk


# ══════════════════════════════════════════════════════════════
# ICONO DE APLICACIÓN
# ══════════════════════════════════════════════════════════════

def _app_icon() -> QIcon:
    ico = Path(__file__).parent / "logo.ico"
    return QIcon(str(ico)) if ico.exists() else QIcon()


# ══════════════════════════════════════════════════════════════
# PALETA DE COLORES
# ══════════════════════════════════════════════════════════════

C = {
    # Fondos
    "bg":          "#0B0F19",
    "bg_panel":    "#0E1420",
    "bg_card":     "#131928",
    "bg_input":    "#1A2235",
    "bg_input_f":  "#1E2940",

    # Bordes
    "border":      "#243050",
    "border_f":    "#2E6BE6",

    # Acento principal: azul cobalto
    "accent":      "#2259D4",
    "accent_h":    "#2E6BE6",
    "accent_dim":  "#162250",

    # Semáforo
    "ok":          "#22C55E",
    "error":       "#EF4444",
    "warn":        "#F59E0B",

    # Texto
    "t1":          "#EDF0F7",
    "t2":          "#8494B2",
    "t3":          "#3D4F70",

    # Utilitarios
    "white":       "#FFFFFF",
    "separator":   "#1C2540",
}

# ── Fuentes ────────────────────────────────────────────────────
FONT_TITLE = "font-family:'Outfit','Exo 2','Segoe UI',sans-serif; font-weight:700;"
FONT_BODY  = "font-family:'DM Sans','Nunito','Segoe UI',sans-serif; font-weight:400;"

STYLE_GLOBAL = f"""
QWidget {{
    background-color: {C['bg']};
    color: {C['t1']};
    {FONT_BODY}
    font-size: 13px;
}}
QLabel {{ background: transparent; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 6px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C['border']}; border-radius: 3px; min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QAbstractItemView {{
    background-color: {C['bg_card']}; color: {C['t1']}; border: none;
}}
QLineEdit {{
    background-color: {C['bg_input']};
    border: 1.5px solid {C['border']};
    border-radius: 8px;
    padding: 10px 14px;
    color: {C['t1']};
    font-size: 13px;
    selection-background-color: {C['accent']};
}}
QLineEdit:focus {{
    border-color: {C['border_f']};
    background-color: {C['bg_input_f']};
}}
QLineEdit:disabled {{ color: {C['t3']}; }}
QPushButton {{
    border-radius: 8px; padding: 10px 20px;
    font-size: 13px; font-weight: 600;
}}
"""


# ══════════════════════════════════════════════════════════════
# FÁBRICA DE BOTONES
# ══════════════════════════════════════════════════════════════

def btn_primary(text: str, parent=None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setStyleSheet(f"""
        QPushButton {{
            background-color: {C['accent']}; color: {C['white']};
            border: none; border-radius: 8px;
            padding: 11px 22px; font-size: 13px; font-weight: 700;
            letter-spacing: 0.3px;
        }}
        QPushButton:hover {{ background-color: {C['accent_h']}; }}
        QPushButton:pressed {{ background-color: #1A4DC2; }}
        QPushButton:disabled {{
            background-color: {C['t3']}; color: {C['bg']};
        }}
    """)
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    return b


def btn_secondary(text: str, parent=None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setStyleSheet(f"""
        QPushButton {{
            background-color: transparent; color: {C['t2']};
            border: 1.5px solid {C['border']}; border-radius: 8px;
            padding: 10px 20px; font-size: 13px; font-weight: 500;
        }}
        QPushButton:hover {{
            border-color: {C['border_f']}; color: {C['t1']};
            background-color: {C['bg_input']};
        }}
    """)
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    return b


def btn_link(text: str, parent=None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setStyleSheet(f"""
        QPushButton {{
            background: transparent; color: {C['accent_h']};
            border: none; padding: 3px 2px;
            font-size: 12px; text-decoration: underline;
        }}
        QPushButton:hover {{ color: {C['white']}; }}
    """)
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    return b


# ══════════════════════════════════════════════════════════════
# WIDGETS AUXILIARES
# ══════════════════════════════════════════════════════════════

def label(text: str, size=13, color=None, bold=False, wrap=False) -> QLabel:
    lb = QLabel(text)
    color = color or C["t1"]
    w = "700" if bold else "400"
    lb.setStyleSheet(
        f"color:{color}; font-size:{size}px; font-weight:{w}; background:transparent;"
    )
    if wrap:
        lb.setWordWrap(True)
    return lb


def separador() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"border:none; border-top:1px solid {C['separator']}; background:transparent;")
    f.setFixedHeight(1)
    return f


class InputField(QWidget):
    """Etiqueta + QLineEdit + mensaje de error inline."""

    returnPressed = Signal()

    def __init__(self, lbl: str, placeholder="", password=False, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent; border:none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self._lbl   = label(lbl, size=11, color=C["t2"])
        self.input  = QLineEdit()
        self.input.setPlaceholderText(placeholder)
        self.input.setMinimumHeight(42)
        if password:
            self.input.setEchoMode(QLineEdit.EchoMode.Password)
        self.input.returnPressed.connect(self.returnPressed)

        self._err = label("", size=11, color=C["error"])
        self._err.hide()

        lay.addWidget(self._lbl)
        lay.addWidget(self.input)
        lay.addWidget(self._err)

    def text(self) -> str:
        return self.input.text().strip()

    def setText(self, t: str):
        self.input.setText(t)

    def set_error(self, msg: str):
        self._err.setText(msg)
        self._err.show()
        self.input.setStyleSheet(f"border-color:{C['error']};")

    def clear_error(self):
        self._err.hide()
        self.input.setStyleSheet("")

    def setEnabled(self, v: bool):
        self.input.setEnabled(v)
        super().setEnabled(v)


class ComboField(QWidget):
    """
    Selector desplegable completamente custom (sin QComboBox).
    La lista se despliega INLINE en el layout.
    """
    selectionChanged = Signal(object)

    _ITEM_H   = 36
    _MAX_ROWS = 7

    def __init__(self, lbl: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent; border:none;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._items: list[tuple[str, object]] = []
        self._selected_idx = -1
        self._open = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self._lbl = label(lbl, size=11, color=C["t2"])
        lay.addWidget(self._lbl)

        self._btn = QPushButton()
        self._btn.setMinimumHeight(42)
        self._btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn.setStyleSheet(self._btn_style(False))
        self._btn.clicked.connect(self._toggle)
        self._btn.setText("— Selecciona —   ▾")
        lay.addWidget(self._btn)

        self._list = QListWidget()
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setStyleSheet(f"""
            QListWidget {{
                background-color: {C['bg_card']};
                border: 1.5px solid {C['border_f']};
                border-top: none;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
                outline: none; padding: 2px 0;
            }}
            QListWidget::item {{
                height: {self._ITEM_H}px; padding: 0 14px;
                color: {C['t1']}; border: none;
            }}
            QListWidget::item:hover {{ background-color: {C['bg_input']}; }}
            QListWidget::item:selected {{
                background-color: {C['accent']}; color: {C['white']};
            }}
            QScrollBar:vertical {{ background:{C['bg_card']}; width:6px; border:none; }}
            QScrollBar::handle:vertical {{
                background:{C['border']}; border-radius:3px; min-height:20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        """)
        self._list.hide()
        self._list.itemClicked.connect(self._on_click)
        lay.addWidget(self._list)

    def _btn_style(self, focused: bool) -> str:
        bc  = C["border_f"] if focused else C["border"]
        rb  = "0px"         if focused else "8px"
        return f"""
            QPushButton {{
                background-color: {C['bg_input']};
                border: 1.5px solid {bc};
                border-radius: 8px;
                border-bottom-left-radius:  {rb};
                border-bottom-right-radius: {rb};
                color: {C['t1']}; font-size: 13px;
                text-align: left; padding: 0 42px 0 14px;
            }}
            QPushButton::menu-indicator {{ width: 0; }}
        """

    def _toggle(self):
        if self._open:
            self._close()
        else:
            self._open_list()

    def _open_list(self):
        if not self._items:
            return
        rows   = min(len(self._items), self._MAX_ROWS)
        altura = rows * self._ITEM_H + 8
        self._list.setFixedHeight(altura)
        self._list.show()
        self._open = True
        self._btn.setStyleSheet(self._btn_style(True))
        txt = self.currentText() or "— Selecciona —"
        self._btn.setText(f"{txt}   ▴")
        if self._selected_idx >= 0:
            self._list.setCurrentRow(self._selected_idx)
            self._list.scrollToItem(
                self._list.currentItem(),
                QAbstractItemView.ScrollHint.PositionAtCenter,
            )

    def _close(self):
        self._list.hide()
        self._open = False
        self._btn.setStyleSheet(self._btn_style(False))
        txt = self.currentText() or "— Selecciona —"
        self._btn.setText(f"{txt}   ▾")

    def _on_click(self, item: QListWidgetItem):
        idx = self._list.row(item)
        self._selected_idx = idx
        texto, data = self._items[idx]
        self._btn.setText(f"{texto}   ▾")
        self._close()
        self.selectionChanged.emit(data)

    # ── API pública ───────────────────────────────────────────
    def addItem(self, text: str, data=None):
        self._items.append((text, data))
        it = QListWidgetItem(text)
        it.setData(Qt.ItemDataRole.UserRole, data)
        self._list.addItem(it)

    def currentData(self):
        if self._selected_idx < 0:
            return None
        return self._items[self._selected_idx][1]

    def currentText(self) -> str:
        if self._selected_idx < 0:
            return ""
        return self._items[self._selected_idx][0]

    def reset(self):
        self._items.clear()
        self._list.clear()
        self._selected_idx = -1
        self._btn.setText("— Selecciona —   ▾")
        self._close()

    def setEnabled(self, v: bool):
        self._btn.setEnabled(v)
        if not v:
            self._close()
        super().setEnabled(v)


class StatusBar(QLabel):
    """Barra de error / éxito animada."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(0)
        self.hide()

    def _show(self, msg: str, bg: str, border: str, color: str):
        self.setStyleSheet(f"""
            background-color: {bg};
            border: 1px solid {border};
            border-radius: 8px; color: {color};
            padding: 10px 14px; font-size: 12px;
        """)
        self.setText(msg)
        self.show()
        w = self.window()
        if w and w != self:
            w.adjustSize()

    def mostrar_error(self, msg: str):
        self._show(msg, "rgba(239,68,68,0.12)", C["error"], C["error"])

    def mostrar_exito(self, msg: str):
        self._show(msg, "rgba(34,197,94,0.12)", C["ok"], C["ok"])

    def ocultar(self):
        self.hide()


# ══════════════════════════════════════════════════════════════
# WORKER ASÍNCRONO
# ══════════════════════════════════════════════════════════════

class _Worker(QThread):
    done = Signal(object)

    def __init__(self, fn, args, kwargs):
        super().__init__()
        self._fn, self._args, self._kwargs = fn, args, kwargs
        self.setTerminationEnabled(True)

    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as e:
            result = bk.AuthResult(False, f"Error inesperado: {e}")
        self.done.emit(result)


_workers: list = []


def run_async(fn, *args, on_done=None, **kwargs):
    w = _Worker(fn, args, kwargs)
    _workers.append(w)
    if on_done:
        w.done.connect(on_done)

    def _cleanup(_):
        if w in _workers:
            _workers.remove(w)

    w.done.connect(_cleanup)
    w.start()


# ══════════════════════════════════════════════════════════════
# VENTANA PRINCIPAL DE LOGIN
# ══════════════════════════════════════════════════════════════

class LoginWindow(QMainWindow):
    """
    Ventana de inicio de sesión.
    ≥ 920 px  → layout de dos columnas (panel de marca + formulario)
    < 920 px  → solo formulario centrado

    login_exitoso(dict) emite:
        {rol, id, nombre, correo, sesion_id, [entidad_id], [nit]}
    """
    login_exitoso = Signal(dict)
    _BREAKPOINT = 920

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SIGES — Sistema de Gestión de Eventos en Salud")
        self.setWindowIcon(_app_icon())
        self.setMinimumSize(420, 580)
        self.resize(980, 660)
        self.setStyleSheet(STYLE_GLOBAL)
        self._tipos_doc: list[dict] = []

        central = QWidget()
        self.setCentralWidget(central)
        self._root = QHBoxLayout(central)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)

        self._marca = self._mk_panel_marca()
        self._form  = self._mk_panel_form()

        self._root.addWidget(self._marca, stretch=5)
        self._root.addWidget(self._form,  stretch=4)

        self._cargar_tipos_doc()

    # ── Panel izquierdo (marca) ───────────────────────────────

    def _mk_panel_marca(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"background:{C['bg_panel']};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(56, 56, 56, 44)
        lay.setSpacing(0)

        # Logo-texto
        logo_row = QWidget()
        logo_row.setStyleSheet("background:transparent; border:none;")
        lr = QHBoxLayout(logo_row)
        lr.setContentsMargins(0, 0, 0, 0)
        lr.setSpacing(12)
        icono = label("⚕", size=36, color=C["accent_h"])
        nombre = QLabel("SIGES")
        nombre.setStyleSheet(
            f"font-size:22px; font-weight:800; color:{C['white']}; "
            f"letter-spacing:3px; background:transparent; {FONT_TITLE}"
        )
        lr.addWidget(icono)
        lr.addWidget(nombre)
        lr.addStretch()
        lay.addWidget(logo_row)
        lay.addSpacing(12)

        sub = QLabel("Sistema de Gestión de\nRegistro de Eventos en Salud")
        sub.setStyleSheet(
            f"color:#7A9CC0; font-size:20px; font-weight:300; "
            f"line-height:1.5; background:transparent; {FONT_TITLE}"
        )
        sub.setWordWrap(True)
        lay.addWidget(sub)
        lay.addSpacing(44)

        # Características
        items = [
            ("👤", "Gestión de usuarios OPS y administradores"),
            ("📋", "Registro de eventos de atención"),
            ("🏥", "Control de EPS y contratos"),
            ("📊", "Reportes RIPS y facturación"),
            ("🔒", "Trazabilidad y auditoría completa"),
        ]
        for emoji, texto in items:
            row = QWidget()
            row.setStyleSheet("background:transparent; border:none;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(14)
            em = label(emoji, size=16)
            em.setFixedWidth(26)
            tx = label(texto, size=12, color="#6B8FAF")
            rl.addWidget(em)
            rl.addWidget(tx)
            rl.addStretch()
            lay.addWidget(row)
            lay.addSpacing(10)

        lay.addStretch()

        # Pie de página
        lay.addWidget(separador())
        lay.addSpacing(14)
        lay.addWidget(label("v2.1  ·  2026", size=11, color=C["t3"]))
        lay.addWidget(label("Camilo Andrés Ortiz Regalado", size=11, color=C["t3"]))
        lay.addWidget(label("Ingeniero de Sistemas · camiloortizcpt@gmail.com",
                            size=11, color=C["t3"]))
        return w

    # ── Panel derecho (formulario) ────────────────────────────

    def _mk_panel_form(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet(f"background:{C['bg']};")
        outer = QVBoxLayout(wrapper)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background:transparent; border:none;")

        inner = QWidget()
        inner.setStyleSheet("background:transparent;")
        il = QVBoxLayout(inner)
        il.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._form_container = self._mk_form_login()
        il.addWidget(self._form_container)

        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return wrapper

    # ── Formulario de login ───────────────────────────────────

    def _mk_form_login(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(56, 60, 56, 60)
        lay.setSpacing(0)
        lay.addStretch(1)

        # Encabezado
        lay.addWidget(label("Bienvenido", size=30, bold=True))
        lay.addSpacing(6)
        lay.addWidget(label("Ingresa tus credenciales para continuar",
                             size=13, color=C["t2"]))
        lay.addSpacing(30)

        # Selector de tipo de documento
        self.f_tipo = ComboField("Tipo de documento")
        lay.addWidget(self.f_tipo)
        lay.addSpacing(14)

        # Documento
        self.f_doc = InputField(
            "Número de documento / NIT",
            "Ej: 1234567890  o  900123456-7",
        )
        self.f_doc.returnPressed.connect(self._hacer_login)
        lay.addWidget(self.f_doc)
        lay.addSpacing(14)

        # Contraseña
        self.f_pw = InputField("Contraseña", "••••••••", password=True)
        self.f_pw.returnPressed.connect(self._hacer_login)
        lay.addWidget(self.f_pw)
        lay.addSpacing(10)

        # Recuperar
        rec = QHBoxLayout()
        rec.addStretch()
        br = btn_link("¿Olvidaste tu contraseña?")
        br.clicked.connect(self._abrir_recuperar)
        rec.addWidget(br)
        lay.addLayout(rec)
        lay.addSpacing(20)

        # Status
        self.status = StatusBar()
        lay.addWidget(self.status)
        lay.addSpacing(8)

        # Botón ingresar
        self.btn_login = btn_primary("Iniciar sesión")
        self.btn_login.setMinimumHeight(46)
        self.btn_login.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_login.clicked.connect(self._hacer_login)
        lay.addWidget(self.btn_login)
        lay.addSpacing(26)

        lay.addWidget(separador())
        lay.addSpacing(22)

        # Registro OPS
        r1 = QHBoxLayout()
        r1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        r1.addWidget(label("¿No tienes cuenta?", size=12, color=C["t2"]))
        r1.addSpacing(6)
        b1 = btn_link("Registrarse como OPS")
        b1.clicked.connect(self._abrir_registro_ops)
        r1.addWidget(b1)
        lay.addLayout(r1)
        lay.addSpacing(10)

        # Registro entidad
        r2 = QHBoxLayout()
        r2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        r2.addWidget(label("¿Registrar entidad?", size=12, color=C["t2"]))
        r2.addSpacing(6)
        b2 = btn_link("Registrar entidad administradora")
        b2.clicked.connect(self._abrir_registro_entidad)
        r2.addWidget(b2)
        lay.addLayout(r2)

        lay.addStretch(2)
        return w

    # ── Resize responsive ─────────────────────────────────────

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._pending_w = event.size().width()
        if not hasattr(self, "_rt"):
            self._rt = QTimer(self)
            self._rt.setSingleShot(True)
            self._rt.timeout.connect(self._aplicar_resize)
        self._rt.start(50)

    def _aplicar_resize(self):
        ancho = getattr(self, "_pending_w", self.width())
        self._marca.setVisible(ancho >= self._BREAKPOINT)
        m = max(24, min(56, int(ancho * 0.065)))
        if hasattr(self, "f_pw"):
            self._form_container.layout().setContentsMargins(m, 48, m, 48)

    # ── Carga tipos de documento (hilo separado) ──────────────

    def _cargar_tipos_doc(self):
        self.f_tipo.setEnabled(False)
        self.f_tipo.addItem("Cargando tipos de documento…", None)

        def _cargar():
            try:
                return bk.obtener_tipos_documento()
            except Exception:
                return []

        def _on_done(result):
            tipos = result if isinstance(result, list) else []
            self._tipos_doc = tipos
            self.f_tipo.reset()
            self.f_tipo.addItem("— Selecciona tipo de documento —", None)
            for td in tipos:
                self.f_tipo.addItem(
                    f"{td['abreviatura']}  —  {td['nombre']}",
                    td["abreviatura"],
                )
            self.f_tipo.addItem("NIT  —  Entidad administradora", "NIT")
            self.f_tipo.setEnabled(True)
            if not tipos:
                self.status.mostrar_error(
                    "No se pudieron cargar los tipos de documento. "
                    "Verifica la conexión a la base de datos."
                )

        run_async(_cargar, on_done=_on_done)

    # ── Acción login ──────────────────────────────────────────

    def _hacer_login(self):
        self.status.ocultar()
        tipo_data = self.f_tipo.currentData()
        documento = self.f_doc.text()
        password  = self.f_pw.text()

        if tipo_data is None:
            self.status.mostrar_error("Selecciona el tipo de documento.")
            return
        if not documento:
            self.status.mostrar_error("Ingresa tu número de documento o NIT.")
            return
        if not password:
            self.status.mostrar_error("Ingresa tu contraseña.")
            return

        tipo_abrev = tipo_data if isinstance(tipo_data, str) else str(tipo_data)

        self.btn_login.setEnabled(False)
        self.btn_login.setText("Verificando…")

        def on_done(result: bk.AuthResult):
            self.btn_login.setEnabled(True)
            self.btn_login.setText("Iniciar sesión")
            if result.ok:
                self.login_exitoso.emit(result.datos)
                self.close()
            else:
                self.status.mostrar_error(result.mensaje)

        run_async(bk.login, tipo_abrev, documento, password, on_done=on_done)

    # ── Abrir diálogos ────────────────────────────────────────

    def _abrir_registro_ops(self):
        RegistroOpsDialog(self._tipos_doc, self).exec()

    def _abrir_registro_entidad(self):
        RegistroEntidadDialog(self).exec()

    def _abrir_recuperar(self):
        RecuperarPaso1(self._tipos_doc, self).exec()


# ══════════════════════════════════════════════════════════════
# DIÁLOGO BASE CON SCROLL
# ══════════════════════════════════════════════════════════════

class BaseDialog(QDialog):
    """
    Diálogo base: fondo oscuro + scroll vertical automático.
    Las subclases usan self.contenido_lay para agregar widgets
    y llaman self._finalizar() al final de _build().
    """
    _MAX_H_RATIO = 0.88

    def __init__(self, titulo: str, ancho=500, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setWindowIcon(_app_icon())
        self.setStyleSheet(STYLE_GLOBAL)
        self.setModal(True)
        self.setMinimumWidth(min(ancho, 380))
        self.setMaximumWidth(700)
        self.resize(ancho, 200)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Cabecera fija
        header = QWidget()
        header.setStyleSheet(f"background:{C['bg']}; border:none;")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(32, 26, 32, 0)
        hl.setSpacing(0)
        hl.addWidget(label(titulo, size=20, bold=True))
        hl.addSpacing(10)
        hl.addWidget(separador())
        root.addWidget(header)

        # Scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border:none; background:{C['bg']}; }}
            QScrollBar:vertical {{
                background:{C['bg']}; width:6px;
                margin:4px 2px 4px 0; border-radius:3px;
            }}
            QScrollBar::handle:vertical {{
                background:{C['border']}; border-radius:3px; min-height:24px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        """)

        inner = QWidget()
        inner.setStyleSheet(f"background:{C['bg']}; border:none;")
        self.contenido_lay = QVBoxLayout(inner)
        self.contenido_lay.setContentsMargins(32, 22, 32, 28)
        self.contenido_lay.setSpacing(0)

        scroll.setWidget(inner)
        root.addWidget(scroll, 1)
        self._scroll = scroll

    def _finalizar(self):
        QTimer.singleShot(0, self._ajustar_tamanio)

    def _ajustar_tamanio(self):
        self._scroll.widget().adjustSize()
        self.adjustSize()
        screen = QApplication.primaryScreen()
        max_h = int(screen.availableGeometry().height() * self._MAX_H_RATIO) if screen else 800
        self.resize(self.width(), max(300, min(self.sizeHint().height(), max_h)))


# ══════════════════════════════════════════════════════════════
# REGISTRO OPS
# ══════════════════════════════════════════════════════════════

class RegistroOpsDialog(BaseDialog):
    def __init__(self, tipos_doc: list, parent=None):
        super().__init__("Crear cuenta de usuario OPS", ancho=520, parent=parent)
        self._tipos_doc = tipos_doc
        self._build()

    def _build(self):
        lay = self.contenido_lay

        nota = QLabel(
            "El NIT de la entidad te lo proporciona el administrador "
            "de tu clínica u hospital."
        )
        nota.setWordWrap(True)
        nota.setStyleSheet(f"""
            background-color:{C['accent_dim']}; border-radius:8px;
            padding:10px 14px; color:{C['t2']}; font-size:12px;
        """)
        lay.addWidget(nota)
        lay.addSpacing(16)

        self.f_nit   = InputField("NIT de la entidad *", "Ej: 900123456-7")
        self.f_tipo  = ComboField("Tipo de documento *")
        self.f_tipo.addItem("— Selecciona —", None)
        for td in self._tipos_doc:
            self.f_tipo.addItem(
                f"{td['abreviatura']}  —  {td['nombre']}", td["abreviatura"]
            )
        self.f_doc    = InputField("Número de documento *", "Ej: 1234567890")
        self.f_nombre = InputField("Nombre completo *", "Ej: Juan Pérez García")
        self.f_correo = InputField("Correo electrónico *", "correo@ejemplo.com")
        self.f_wa     = InputField("WhatsApp *", "+57 300 000 0000")
        self.f_pw     = InputField("Contraseña *", "Mínimo 8 caracteres", password=True)
        self.f_pw2    = InputField("Confirmar contraseña *", "Repite la contraseña", password=True)

        for f in [self.f_nit, self.f_tipo, self.f_doc, self.f_nombre,
                  self.f_correo, self.f_wa, self.f_pw, self.f_pw2]:
            lay.addWidget(f)
            lay.addSpacing(10)

        self.status = StatusBar()
        lay.addWidget(self.status)
        lay.addSpacing(12)

        btns = QHBoxLayout()
        bc = btn_secondary("Cancelar")
        bc.clicked.connect(self.reject)
        self.btn_reg = btn_primary("Crear cuenta")
        self.btn_reg.clicked.connect(self._registrar)
        btns.addWidget(bc)
        btns.addWidget(self.btn_reg)
        lay.addLayout(btns)
        self._finalizar()

    def _registrar(self):
        self.status.ocultar()
        tipo_abrev = self.f_tipo.currentData()
        nit        = self.f_nit.text()

        if tipo_abrev is None:
            self.status.mostrar_error("Selecciona el tipo de documento.")
            return
        if not nit:
            self.status.mostrar_error("Ingresa el NIT de la entidad.")
            return

        datos_form = {
            "tipo_doc_abrev":     tipo_abrev,
            "nit_entidad":        nit,
            "numero_documento":   self.f_doc.text(),
            "nombre_completo":    self.f_nombre.text(),
            "correo":             self.f_correo.text(),
            "whatsapp":           self.f_wa.text(),
            "password":           self.f_pw.text(),
            "confirmar_password": self.f_pw2.text(),
        }

        self.btn_reg.setEnabled(False)
        self.btn_reg.setText("Verificando…")

        def _resolver_y_registrar():
            entidad_id = bk.resolver_entidad_por_nit(datos_form["nit_entidad"])
            if entidad_id is None:
                return bk.AuthResult(
                    False, "No se encontró ninguna entidad activa con ese NIT."
                )
            datos = {
                "entidad_id":       entidad_id,
                "tipo_doc_abrev":   datos_form["tipo_doc_abrev"],
                "numero_documento": datos_form["numero_documento"],
                "nombre_completo":  datos_form["nombre_completo"],
                "correo":           datos_form["correo"],
                "whatsapp":         datos_form["whatsapp"],
                "password":         datos_form["password"],
                "confirmar_password": datos_form["confirmar_password"],
            }
            return bk.registrar_ops(datos)

        def on_done(result: bk.AuthResult):
            self.btn_reg.setEnabled(True)
            self.btn_reg.setText("Crear cuenta")
            if result.ok:
                self.status.mostrar_exito(result.mensaje)
                QTimer.singleShot(700, self.accept)
            else:
                self.status.mostrar_error(result.mensaje)

        run_async(_resolver_y_registrar, on_done=on_done)


# ══════════════════════════════════════════════════════════════
# REGISTRO ENTIDAD
# ══════════════════════════════════════════════════════════════

class RegistroEntidadDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__("Registrar entidad administradora", ancho=520, parent=parent)
        self._build()

    def _build(self):
        lay = self.contenido_lay

        nota = QLabel(
            "El NIT será tu identificador de acceso. "
            "Formato obligatorio: dígitos-dígito  (ej. 900123456-7)."
        )
        nota.setWordWrap(True)
        nota.setStyleSheet(f"""
            background-color:{C['accent_dim']}; border-radius:8px;
            padding:10px 14px; color:{C['t2']}; font-size:12px;
        """)
        lay.addWidget(nota)
        lay.addSpacing(16)

        self.f_nombre  = InputField("Nombre de la entidad *", "Ej: E.S.E Hospital Local San Ángel")
        self.f_nit     = InputField("NIT *", "Ej: 900123456-7")
        self.f_celular = InputField("Celular *", "+57 300 000 0000")
        self.f_correo  = InputField("Correo electrónico *", "correo@entidad.com")
        self.f_pw      = InputField("Contraseña *", "Mínimo 8 caracteres", password=True)
        self.f_pw2     = InputField("Confirmar contraseña *", "Repite la contraseña", password=True)

        for f in [self.f_nombre, self.f_nit, self.f_celular,
                  self.f_correo, self.f_pw, self.f_pw2]:
            lay.addWidget(f)
            lay.addSpacing(10)

        self.status = StatusBar()
        lay.addWidget(self.status)
        lay.addSpacing(12)

        btns = QHBoxLayout()
        bc = btn_secondary("Cancelar")
        bc.clicked.connect(self.reject)
        self.btn_reg = btn_primary("Registrar entidad")
        self.btn_reg.clicked.connect(self._registrar)
        btns.addWidget(bc)
        btns.addWidget(self.btn_reg)
        lay.addLayout(btns)
        self._finalizar()

    def _registrar(self):
        self.status.ocultar()
        datos = {
            "nombre_entidad":    self.f_nombre.text(),
            "nit":               self.f_nit.text(),
            "celular":           self.f_celular.text(),
            "correo":            self.f_correo.text(),
            "password":          self.f_pw.text(),
            "confirmar_password":self.f_pw2.text(),
        }
        self.btn_reg.setEnabled(False)
        self.btn_reg.setText("Registrando…")

        def on_done(result: bk.AuthResult):
            self.btn_reg.setEnabled(True)
            self.btn_reg.setText("Registrar entidad")
            if result.ok:
                self.status.mostrar_exito(result.mensaje)
                QTimer.singleShot(700, self.accept)
            else:
                self.status.mostrar_error(result.mensaje)

        run_async(bk.registrar_entidad, datos, on_done=on_done)


# Alias de compatibilidad
RegistroAdminDialog = RegistroEntidadDialog


# ══════════════════════════════════════════════════════════════
# RECUPERACIÓN — PASO 1 (solicitar OTP)
# ══════════════════════════════════════════════════════════════

class RecuperarPaso1(BaseDialog):
    def __init__(self, tipos_doc: list, parent=None):
        super().__init__("Recuperar contraseña", ancho=460, parent=parent)
        self._tipos_doc = tipos_doc
        self._build()

    def _build(self):
        lay = self.contenido_lay

        lay.addWidget(label(
            "Ingresa tu tipo y número de documento. "
            "Te enviaremos un código de verificación de 6 dígitos.",
            size=12, color=C["t2"], wrap=True
        ))
        lay.addSpacing(18)

        self.f_tipo = ComboField("Tipo de documento")
        self.f_tipo.addItem("— Selecciona —", None)
        for td in self._tipos_doc:
            self.f_tipo.addItem(f"{td['abreviatura']}  —  {td['nombre']}", td["abreviatura"])
        self.f_tipo.addItem("NIT  —  Entidad administradora", "NIT")
        lay.addWidget(self.f_tipo)
        lay.addSpacing(12)

        self.f_doc = InputField("Número de documento / NIT", "Tu número de documento")
        lay.addWidget(self.f_doc)
        lay.addSpacing(16)

        # Selector de medio
        lay.addWidget(label("Enviar código por:", size=11, color=C["t2"]))
        lay.addSpacing(8)
        self._medio = "correo"
        medio_row = QHBoxLayout()
        self.btn_correo    = self._mk_medio_btn("📧  Correo electrónico", "correo")
        self.btn_whatsapp  = self._mk_medio_btn("💬  WhatsApp", "whatsapp")
        self._marcar_medio("correo")
        medio_row.addWidget(self.btn_correo)
        medio_row.addSpacing(10)
        medio_row.addWidget(self.btn_whatsapp)
        lay.addLayout(medio_row)
        lay.addSpacing(20)

        self.status = StatusBar()
        lay.addWidget(self.status)
        lay.addSpacing(12)

        btns = QHBoxLayout()
        bc = btn_secondary("Cancelar")
        bc.clicked.connect(self.reject)
        self.btn_env = btn_primary("Enviar código")
        self.btn_env.clicked.connect(self._solicitar)
        btns.addWidget(bc)
        btns.addWidget(self.btn_env)
        lay.addLayout(btns)
        self._finalizar()

    def _mk_medio_btn(self, texto: str, medio: str) -> QPushButton:
        b = QPushButton(texto)
        b.setMinimumHeight(42)
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        b.clicked.connect(lambda: self._marcar_medio(medio))
        return b

    def _marcar_medio(self, medio: str):
        self._medio = medio
        on  = (f"background-color:{C['accent_dim']}; border:1.5px solid {C['accent']};"
               f"border-radius:8px; color:{C['accent_h']};"
               f"padding:10px 16px; font-size:13px; font-weight:600;")
        off = (f"background-color:{C['bg_input']}; border:1.5px solid {C['border']};"
               f"border-radius:8px; color:{C['t2']};"
               f"padding:10px 16px; font-size:13px;")
        self.btn_correo.setStyleSheet(
            f"QPushButton{{{on}}}" if medio == "correo" else f"QPushButton{{{off}}}"
        )
        self.btn_whatsapp.setStyleSheet(
            f"QPushButton{{{on}}}" if medio == "whatsapp" else f"QPushButton{{{off}}}"
        )

    def _solicitar(self):
        self.status.ocultar()
        tipo_abrev = self.f_tipo.currentData()
        documento  = self.f_doc.text()

        if tipo_abrev is None:
            self.status.mostrar_error("Selecciona el tipo de documento.")
            return
        if not documento:
            self.status.mostrar_error("Ingresa tu número de documento.")
            return

        self.btn_env.setEnabled(False)
        self.btn_env.setText("Enviando…")

        def on_done(result: bk.AuthResult):
            self.btn_env.setEnabled(True)
            self.btn_env.setText("Enviar código")
            if result.ok:
                self.status.mostrar_exito(result.mensaje)
                QTimer.singleShot(500, lambda: self._ir_paso2(result))
            else:
                self.status.mostrar_error(result.mensaje)

        run_async(
            bk.solicitar_recuperacion,
            tipo_abrev, documento, self._medio,
            on_done=on_done,
        )

    def _ir_paso2(self, result: bk.AuthResult):
        d = result.datos or {}
        dlg = RecuperarPaso2(
            d.get("entidad_id"), d.get("ops_id"),
            d.get("codigo_dev", ""), self.parent()
        )
        self.accept()
        dlg.exec()


# ══════════════════════════════════════════════════════════════
# RECUPERACIÓN — PASO 2 (código OTP)
# ══════════════════════════════════════════════════════════════

class RecuperarPaso2(BaseDialog):
    def __init__(self, entidad_id, ops_id, codigo_dev="", parent=None):
        super().__init__("Verificación de identidad", ancho=420, parent=parent)
        self._entidad_id = entidad_id
        self._ops_id     = ops_id
        self._build(codigo_dev)

    def _build(self, codigo_dev: str):
        lay = self.contenido_lay

        lay.addWidget(label(
            "Ingresa el código de 6 dígitos que recibiste.\nExpira en 15 minutos.",
            size=12, color=C["t2"], wrap=True
        ))
        lay.addSpacing(22)

        otp_row = QHBoxLayout()
        otp_row.setSpacing(8)
        self._otp: list[QLineEdit] = []
        for i in range(6):
            f = QLineEdit()
            f.setMaxLength(1)
            f.setMinimumSize(46, 56)
            f.setAlignment(Qt.AlignmentFlag.AlignCenter)
            f.setStyleSheet(f"""
                QLineEdit {{
                    background-color:{C['bg_input']}; border:2px solid {C['border']};
                    border-radius:10px; color:{C['t1']};
                    font-size:22px; font-weight:700;
                }}
                QLineEdit:focus {{
                    border-color:{C['border_f']}; background-color:{C['bg_input_f']};
                }}
            """)
            f.textChanged.connect(lambda txt, ix=i: self._avanzar(txt, ix))
            self._otp.append(f)
            otp_row.addWidget(f)

        lay.addLayout(otp_row)

        if codigo_dev:
            hint = label(f"[DEV] Código: {codigo_dev}", size=11, color=C["warn"])
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addSpacing(6)
            lay.addWidget(hint)

        lay.addSpacing(20)
        self.status = StatusBar()
        lay.addWidget(self.status)
        lay.addSpacing(12)

        btns = QHBoxLayout()
        bc = btn_secondary("Cancelar")
        bc.clicked.connect(self.reject)
        self.btn_ver = btn_primary("Verificar código")
        self.btn_ver.clicked.connect(self._verificar)
        btns.addWidget(bc)
        btns.addWidget(self.btn_ver)
        lay.addLayout(btns)
        self._finalizar()

        if self._otp:
            self._otp[0].setFocus()

    def _avanzar(self, txt: str, idx: int):
        if txt and idx < 5:
            self._otp[idx + 1].setFocus()

    def _verificar(self):
        self.status.ocultar()
        codigo = "".join(f.text() for f in self._otp)
        if len(codigo) < 6:
            self.status.mostrar_error("Ingresa los 6 dígitos del código.")
            return
        self.btn_ver.setEnabled(False)
        self.btn_ver.setText("Verificando…")

        def on_done(result: bk.AuthResult):
            self.btn_ver.setEnabled(True)
            self.btn_ver.setText("Verificar código")
            if result.ok:
                self.status.mostrar_exito("¡Código correcto!")
                QTimer.singleShot(500, lambda: self._ir_paso3(result))
            else:
                self.status.mostrar_error(result.mensaje)
                for f in self._otp:
                    f.clear()
                self._otp[0].setFocus()

        run_async(
            bk.verificar_codigo,
            self._entidad_id, self._ops_id, codigo,
            on_done=on_done,
        )

    def _ir_paso3(self, result: bk.AuthResult):
        d = result.datos or {}
        dlg = RecuperarPaso3(
            d.get("entidad_id"), d.get("ops_id"),
            d.get("token_id", ""), self.parent()
        )
        self.accept()
        dlg.exec()


# ══════════════════════════════════════════════════════════════
# RECUPERACIÓN — PASO 3 (nueva contraseña)
# ══════════════════════════════════════════════════════════════

class RecuperarPaso3(BaseDialog):
    def __init__(self, entidad_id, ops_id, token_id, parent=None):
        super().__init__("Establecer nueva contraseña", ancho=420, parent=parent)
        self._entidad_id = entidad_id
        self._ops_id     = ops_id
        self._token_id   = token_id
        self._build()

    def _build(self):
        lay = self.contenido_lay
        self.f_nueva = InputField("Nueva contraseña *", "Mínimo 8 caracteres", password=True)
        self.f_conf  = InputField("Confirmar contraseña *", "Repite la contraseña", password=True)
        lay.addWidget(self.f_nueva)
        lay.addSpacing(10)
        lay.addWidget(self.f_conf)
        lay.addSpacing(20)

        self.status = StatusBar()
        lay.addWidget(self.status)
        lay.addSpacing(12)

        btns = QHBoxLayout()
        bc = btn_secondary("Cancelar")
        bc.clicked.connect(self.reject)
        self.btn_g = btn_primary("Guardar contraseña")
        self.btn_g.clicked.connect(self._guardar)
        btns.addWidget(bc)
        btns.addWidget(self.btn_g)
        lay.addLayout(btns)
        self._finalizar()

    def _guardar(self):
        self.status.ocultar()
        self.btn_g.setEnabled(False)
        self.btn_g.setText("Guardando…")

        def on_done(result: bk.AuthResult):
            self.btn_g.setEnabled(True)
            self.btn_g.setText("Guardar contraseña")
            if result.ok:
                self.status.mostrar_exito("¡Contraseña actualizada! Ya puedes iniciar sesión.")
                QTimer.singleShot(700, self.accept)
            else:
                self.status.mostrar_error(result.mensaje)

        run_async(
            bk.cambiar_password_recuperacion,
            self._entidad_id, self._ops_id, self._token_id,
            self.f_nueva.text(), self.f_conf.text(),
            on_done=on_done,
        )


# ══════════════════════════════════════════════════════════════
# CAMBIO DE CONTRASEÑA (sesión activa)
# ══════════════════════════════════════════════════════════════

class CambiarPasswordDialog(BaseDialog):
    """
    Uso:
        dlg = CambiarPasswordDialog(rol='ops', usuario_id='42', parent=self)
        dlg.exec()
    """
    def __init__(self, rol: str, usuario_id: str, parent=None):
        super().__init__("Cambiar contraseña", ancho=420, parent=parent)
        self._rol        = rol
        self._usuario_id = usuario_id
        self._build()

    def _build(self):
        lay = self.contenido_lay

        nota = label(
            "Ingresa y confirma tu nueva contraseña.\n"
            "Por seguridad se cerrarán todas tus sesiones activas.",
            size=12, color=C["t2"], wrap=True
        )
        lay.addWidget(nota)
        lay.addSpacing(16)

        self.f_nueva = InputField("Nueva contraseña *", "Mínimo 8 caracteres", password=True)
        self.f_conf  = InputField("Confirmar contraseña *", "Repite la contraseña", password=True)
        lay.addWidget(self.f_nueva)
        lay.addSpacing(10)
        lay.addWidget(self.f_conf)
        lay.addSpacing(20)

        self.status = StatusBar()
        lay.addWidget(self.status)
        lay.addSpacing(12)

        btns = QHBoxLayout()
        bc = btn_secondary("Cancelar")
        bc.clicked.connect(self.reject)
        self.btn_g = btn_primary("Actualizar contraseña")
        self.btn_g.clicked.connect(self._guardar)
        btns.addWidget(bc)
        btns.addWidget(self.btn_g)
        lay.addLayout(btns)
        self._finalizar()

    def _guardar(self):
        self.status.ocultar()
        self.btn_g.setEnabled(False)
        self.btn_g.setText("Guardando…")

        def on_done(result: bk.AuthResult):
            self.btn_g.setEnabled(True)
            self.btn_g.setText("Actualizar contraseña")
            if result.ok:
                self.status.mostrar_exito(result.mensaje)
                QTimer.singleShot(700, self.accept)
            else:
                self.status.mostrar_error(result.mensaje)

        run_async(
            bk.cambiar_password_autenticado,
            self._rol, self._usuario_id,
            self.f_nueva.text(), self.f_conf.text(),
            on_done=on_done,
        )


# ══════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    def on_login(datos: dict):
        print(
            f"\n[LOGIN OK]\n"
            f"  Rol      : {datos['rol']}\n"
            f"  ID       : {datos['id']}\n"
            f"  Nombre   : {datos['nombre']}\n"
            f"  Correo   : {datos['correo']}\n"
            f"  Sesión   : {datos['sesion_id']}"
        )

    win = LoginWindow()
    win.login_exitoso.connect(on_login)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
