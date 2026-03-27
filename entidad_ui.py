# -*- coding: utf-8 -*-
# =============================================================================
# entidad_ui.py  —  v2.1  RESPONSIVE TOTAL
# Módulo de Gestión de Entidades — PySide6 / SIGES
#
# RESPONSIVE (automático, sin acción del usuario):
#   ≤ 500 px   → tarjetas 1 columna, stats 2×3, sin NIT visible
#   501–800 px → tarjetas 1 col, stats 3×2, tabla colapsada a 4 cols
#   801–1100px → tabla 6 cols, stats fila completa
#   > 1100 px  → tabla completa 8 cols, stats fila completa
#
# La tabla recalcula anchos en cada resize con debounce de 40 ms.
# El NivelSelector envuelve a 2 filas en pantallas angostas.
#
# ACCESO: EXCLUSIVO para el usuario Maestro.
# =============================================================================

from __future__ import annotations

import sys

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFrame,
    QScrollArea, QSizePolicy, QListWidget, QListWidgetItem,
    QAbstractItemView, QStackedWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox,
    QButtonGroup, QRadioButton,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer, QSize
from PySide6.QtGui import QCursor, QColor, QResizeEvent

import entidad_backend as bk

# ══════════════════════════════════════════════════════════════
# PALETA
# ══════════════════════════════════════════════════════════════

C = {
    "bg":       "#08100F",
    "panel":    "#0B1612",
    "card":     "#0F1D1A",
    "input":    "#172320",
    "input_f":  "#1C2D29",
    "border":   "#1E3530",
    "border_f": "#059669",
    "accent":   "#047857",
    "acc_h":    "#059669",
    "acc_dim":  "#064E3B",
    "maestro":  "#D97706",
    "maestro_d":"#451A03",
    "ok":       "#10B981",
    "ok_d":     "#064E3B",
    "err":      "#EF4444",
    "err_d":    "#450A0A",
    "warn":     "#F59E0B",
    "warn_d":   "#451A03",
    "prot":     "#6366F1",
    "prot_d":   "#1E1B4B",
    "t1":       "#ECFDF5",
    "t2":       "#6EE7B7",
    "t3":       "#065F46",
    "muted":    "#134E4A",
    "white":    "#FFFFFF",
    "row_a":    "#0D1A18",
    "row_sel":  "#064E3B",
}

FONT = "font-family:'Exo 2','Outfit','Segoe UI',sans-serif;"

STYLE = f"""
QWidget {{
    background:{C['bg']}; color:{C['t1']};
    {FONT} font-size:13px;
}}
QLabel  {{ background:transparent; }}
QDialog {{ background:{C['bg']}; }}
QScrollArea {{ border:none; background:transparent; }}
QLineEdit {{
    background:{C['input']}; border:1.5px solid {C['border']};
    border-radius:8px; padding:9px 14px; color:{C['t1']}; font-size:13px;
}}
QLineEdit:focus  {{ border-color:{C['border_f']}; background:{C['input_f']}; }}
QLineEdit:disabled {{ color:{C['t3']}; background:{C['card']}; }}
QScrollBar:vertical   {{ background:transparent; width:6px;  margin:0; }}
QScrollBar:horizontal {{ background:transparent; height:6px; margin:0; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background:{C['border']}; border-radius:3px; min-height:20px; min-width:20px;
}}
QScrollBar::add-line:vertical,   QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ height:0; width:0; }}
QTableWidget {{
    background:{C['card']}; border:1px solid {C['border']};
    border-radius:10px; gridline-color:{C['border']};
    color:{C['t1']}; font-size:13px;
    alternate-background-color:{C['row_a']};
    selection-background-color:{C['row_sel']}; selection-color:{C['t1']};
}}
QTableWidget::item {{ padding:5px 8px; border:none; }}
QHeaderView::section {{
    background:{C['panel']}; color:{C['t2']};
    border:none; border-right:1px solid {C['border']};
    border-bottom:1px solid {C['border']};
    padding:7px 8px; font-size:11px; font-weight:700; letter-spacing:0.3px;
}}
QHeaderView::section:last {{ border-right:none; }}
QRadioButton {{ color:{C['t1']}; spacing:6px; background:transparent; }}
QRadioButton::indicator {{
    width:15px; height:15px;
    border:1.5px solid {C['border']}; border-radius:7px; background:{C['input']};
}}
QRadioButton::indicator:checked {{ background:{C['accent']}; border-color:{C['acc_h']}; }}
"""

# ──────────────────────────────────────────────────────────────
# Breakpoints
# ──────────────────────────────────────────────────────────────
BP_CARD  = 680   # < este ancho → tarjetas
BP_NARROW = 900  # < este → tabla reducida (ocultar columnas opcionales)


# ══════════════════════════════════════════════════════════════
# HELPERS DE WIDGET
# ══════════════════════════════════════════════════════════════

def lbl(text: str, size=13, color=None, bold=False, wrap=False) -> QLabel:
    lb = QLabel(text)
    c  = color or C["t1"]
    fw = "700" if bold else "400"
    lb.setStyleSheet(f"color:{c};font-size:{size}px;font-weight:{fw};background:transparent;")
    if wrap:
        lb.setWordWrap(True)
    return lb


def sep(vertical=False) -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine if vertical else QFrame.Shape.HLine)
    if vertical:
        f.setFixedWidth(1)
    else:
        f.setFixedHeight(1)
    f.setStyleSheet(f"border:none; background:{C['border']};")
    return f


def btn(text: str, estilo="primary", parent=None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    S = {
        "primary":   (f"QPushButton{{background:{C['accent']};color:{C['white']};border:none;"
                      f"border-radius:8px;padding:9px 18px;font-size:13px;font-weight:700;}}"
                      f"QPushButton:hover{{background:{C['acc_h']};}}"
                      f"QPushButton:pressed{{background:#065F46;}}"
                      f"QPushButton:disabled{{background:{C['muted']};color:{C['t3']};}}"),
        "secondary": (f"QPushButton{{background:transparent;color:{C['t2']};"
                      f"border:1.5px solid {C['border']};border-radius:8px;"
                      f"padding:8px 16px;font-size:13px;font-weight:500;}}"
                      f"QPushButton:hover{{border-color:{C['border_f']};color:{C['t1']};"
                      f"background:{C['input']};}}"),
        "danger":    (f"QPushButton{{background:{C['err_d']};color:{C['err']};"
                      f"border:1px solid {C['err']};border-radius:8px;"
                      f"padding:7px 12px;font-size:12px;font-weight:700;}}"
                      f"QPushButton:hover{{background:rgba(239,68,68,0.28);}}"),
        "success":   (f"QPushButton{{background:{C['ok_d']};color:{C['ok']};"
                      f"border:1px solid {C['ok']};border-radius:8px;"
                      f"padding:7px 12px;font-size:12px;font-weight:700;}}"
                      f"QPushButton:hover{{background:rgba(16,185,129,0.28);}}"),
        "warn":      (f"QPushButton{{background:{C['warn_d']};color:{C['warn']};"
                      f"border:1px solid {C['warn']};border-radius:8px;"
                      f"padding:7px 12px;font-size:12px;font-weight:700;}}"
                      f"QPushButton:hover{{background:rgba(245,158,11,0.28);}}"),
        "icon":      (f"QPushButton{{background:transparent;color:{C['t2']};"
                      f"border:none;border-radius:6px;padding:4px 8px;font-size:15px;}}"
                      f"QPushButton:hover{{background:{C['input']};color:{C['t1']};}}"),
        "ghost":     (f"QPushButton{{background:{C['card']};color:{C['t2']};"
                      f"border:1px solid {C['border']};border-radius:8px;"
                      f"padding:7px 12px;font-size:12px;}}"
                      f"QPushButton:hover{{border-color:{C['border_f']};color:{C['t1']};}}"),
    }
    b.setStyleSheet(S.get(estilo, S["primary"]))
    return b


def _it(text) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text) if text is not None else "")
    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return it


# ══════════════════════════════════════════════════════════════
# WORKER ASÍNCRONO
# ══════════════════════════════════════════════════════════════

class _Worker(QThread):
    done = Signal(object)

    def __init__(self, fn, args, kw):
        super().__init__()
        self._fn, self._args, self._kw = fn, args, kw
        self.setTerminationEnabled(True)

    def run(self):
        try:
            self.done.emit(self._fn(*self._args, **self._kw))
        except Exception as e:
            self.done.emit(bk.Resultado(False, str(e)))


_workers: list = []


def run_async(fn, *args, on_done=None, **kw):
    w = _Worker(fn, args, kw)
    _workers.append(w)
    if on_done:
        w.done.connect(on_done)
    w.done.connect(lambda _: _workers.remove(w) if w in _workers else None)
    w.start()


# ══════════════════════════════════════════════════════════════
# WIDGETS COMUNES
# ══════════════════════════════════════════════════════════════

class StatusBar(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(0)
        self.hide()

    def _show(self, msg, bg, border, color):
        self.setStyleSheet(
            f"background:{bg};border:1px solid {border};border-radius:8px;"
            f"color:{color};padding:10px 14px;font-size:12px;"
        )
        self.setText(msg)
        self.show()
        w = self.window()
        if w and w != self:
            w.adjustSize()

    def ok(self, m):   self._show(m, C["ok_d"],   C["ok"],   C["ok"])
    def err(self, m):  self._show(m, C["err_d"],  C["err"],  C["err"])
    def warn(self, m): self._show(m, C["warn_d"], C["warn"], C["warn"])
    def ocultar(self): self.hide()


class InputField(QWidget):
    returnPressed = Signal()

    def __init__(self, label: str, ph="", pw=False, required=False, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;border:none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(lbl(label + (" *" if required else ""), size=11, color=C["t2"]))
        self.inp = QLineEdit()
        self.inp.setPlaceholderText(ph)
        self.inp.setMinimumHeight(40)
        if pw:
            self.inp.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp.returnPressed.connect(self.returnPressed)
        lay.addWidget(self.inp)
        self._err = lbl("", size=11, color=C["err"])
        self._err.hide()
        lay.addWidget(self._err)

    def text(self) -> str:   return self.inp.text().strip()
    def set(self, v):        self.inp.setText(str(v) if v is not None else "")
    def clear(self):         self.inp.clear()
    def set_error(self, m):  self._err.setText(m); self._err.show()
    def clear_error(self):   self._err.hide()
    def setEnabled(self, v):
        self.inp.setEnabled(v); super().setEnabled(v)


class NivelSelector(QWidget):
    """Selector de nivel de atencion. Usa QGridLayout 2x2 — compatible con todas las versiones PySide6."""
    selectionChanged = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;border:none;")
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(6)
        main.addWidget(lbl("Nivel de atencion", size=11, color=C["t2"]))

        grid_w = QWidget()
        grid_w.setStyleSheet("background:transparent;border:none;")
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(6)

        opciones = [
            (0, "Sin definir"),
            (1, "Nivel 1 - Basico"),
            (2, "Nivel 2 - Mediano"),
            (3, "Nivel 3 - Alto"),
        ]
        self._bg = QButtonGroup(self)
        for idx, (val, texto) in enumerate(opciones):
            rb = QRadioButton(texto)
            rb.toggled.connect(lambda checked, v=val: self._on_toggle(checked, v))
            self._bg.addButton(rb, val)
            grid.addWidget(rb, idx // 2, idx % 2)

        self._bg.button(0).setChecked(True)
        main.addWidget(grid_w)

    def _on_toggle(self, checked, val):
        if checked:
            self.selectionChanged.emit(val if val != 0 else None)

    def value(self):
        v = self._bg.checkedId()
        return v if v and v != 0 else None

    def set_value(self, v):
        key = v if v in (1, 2, 3) else 0
        b = self._bg.button(key)
        if b:
            b.setChecked(True)


# ══════════════════════════════════════════════════════════════
# BADGES
# ══════════════════════════════════════════════════════════════

def _badge(texto, color, bg):
    lb = QLabel(texto)
    lb.setStyleSheet(
        f"background:{bg};color:{color};border:1px solid {color};"
        f"border-radius:10px;padding:2px 9px;font-size:11px;font-weight:700;"
    )
    lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lb


def _badge_activo(activo: bool) -> QWidget:
    w = QWidget(); w.setStyleSheet("background:transparent;")
    lay = QHBoxLayout(w); lay.setContentsMargins(2, 1, 2, 1)
    lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(_badge("● Activa" if activo else "○ Inactiva",
                         C["ok"] if activo else C["err"],
                         "rgba(16,185,129,0.14)" if activo else "rgba(239,68,68,0.12)"))
    return w


def _badge_protegida():
    return _badge("🔒 Protegida", C["prot"], C["prot_d"])


def _badge_sesion(n: int):
    if not n:
        return None
    return _badge(f"⚡{n}", C["acc_h"], C["acc_dim"])


# ══════════════════════════════════════════════════════════════
# DIÁLOGO BASE
# ══════════════════════════════════════════════════════════════

class BaseDialog(QDialog):
    def __init__(self, titulo: str, ancho=580, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setStyleSheet(STYLE)
        self.setMinimumWidth(340)
        self.setMaximumWidth(820)

        # Tomar ancho óptimo según pantalla disponible
        screen = QApplication.primaryScreen()
        if screen:
            sw = screen.availableGeometry().width()
            ancho = min(ancho, max(380, int(sw * 0.55)))
        self.resize(ancho, 200)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QWidget()
        hdr.setStyleSheet(f"background:{C['panel']};border:none;")
        hl = QVBoxLayout(hdr)
        hl.setContentsMargins(24, 20, 24, 0)
        hl.setSpacing(0)
        hl.addWidget(lbl(titulo, size=17, bold=True))
        hl.addSpacing(10)
        hl.addWidget(sep())
        root.addWidget(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea{{border:none;background:{C['bg']};}}"
            f"QScrollBar:vertical{{background:{C['bg']};width:6px;}}"
            f"QScrollBar::handle:vertical{{background:{C['border']};border-radius:3px;min-height:20px;}}"
            f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}"
        )
        inner = QWidget()
        inner.setStyleSheet(f"background:{C['bg']};border:none;")
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(24, 18, 24, 24)
        self.lay.setSpacing(0)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)
        self._scroll = scroll

    def _fin(self):
        QTimer.singleShot(0, self._ajustar)

    def _ajustar(self):
        self._scroll.widget().adjustSize()
        self.adjustSize()
        screen = QApplication.primaryScreen()
        max_h = int(screen.availableGeometry().height() * 0.90) if screen else 900
        self.resize(self.width(), max(320, min(self.sizeHint().height(), max_h)))


# ══════════════════════════════════════════════════════════════
# DIÁLOGO: VER DETALLE
# ══════════════════════════════════════════════════════════════

class DialogVerEntidad(BaseDialog):
    def __init__(self, datos: dict, parent=None):
        super().__init__("Detalle de la entidad", 540, parent)
        self._build(datos)

    def _build(self, d: dict):
        lay = self.lay

        # Badges
        badge_row = QHBoxLayout()
        badge_row.addWidget(_badge_activo(d.get("activo", True)))
        if d.get("protegido"):
            badge_row.addWidget(_badge_protegida())
        bs = _badge_sesion(d.get("sesiones_activas", 0))
        if bs:
            badge_row.addWidget(bs)
        badge_row.addStretch()
        lay.addLayout(badge_row)
        lay.addSpacing(14)

        # Grid 2 columnas
        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        for i, (etq, val, row, col) in enumerate([
            ("Nombre",           d.get("nombre_entidad", ""),        0, 0),
            ("NIT",              d.get("nit", ""),                   0, 2),
            ("Código hab.",      d.get("codigo_habilitacion") or "—", 1, 0),
            ("Nivel atención",   d.get("nivel_texto", "No definido"),1, 2),
            ("Municipio",        d.get("municipio") or "—",          2, 0),
            ("Departamento",     d.get("departamento") or "—",       2, 2),
            ("Celular",          d.get("celular", ""),               3, 0),
            ("Correo",           d.get("correo", ""),                3, 2),
        ]):
            lb_e = lbl(etq + ":", size=11, color=C["t2"])
            lb_v = lbl(str(val), size=13); lb_v.setWordWrap(True)
            grid.addWidget(lb_e, row, col)
            grid.addWidget(lb_v, row, col + 1)

        lay.addLayout(grid)
        lay.addSpacing(12)
        lay.addWidget(sep())
        lay.addSpacing(10)

        # Métricas
        met = QHBoxLayout(); met.setSpacing(8)
        for val, etq, color in [
            (d.get("total_ops", 0),          "Total OPS",   C["t2"]),
            (d.get("ops_activos", 0),        "OPS activos", C["ok"]),
            (d.get("sesiones_activas", 0),   "En sesión",   C["acc_h"]),
        ]:
            c = QWidget()
            c.setStyleSheet(f"QWidget{{background:{C['card']};border:1px solid {C['border']};border-radius:8px;}}")
            cl = QVBoxLayout(c); cl.setContentsMargins(10, 8, 10, 8); cl.setSpacing(2)
            cl.addWidget(lbl(str(val), size=18, color=color, bold=True))
            cl.addWidget(lbl(etq, size=11, color=C["t2"]))
            met.addWidget(c)
        lay.addLayout(met)
        lay.addSpacing(12)
        lay.addWidget(lbl(
            f"Creada: {str(d.get('creado_en',''))[:19]}   ·   "
            f"Actualizada: {str(d.get('actualizado_en',''))[:19]}",
            size=11, color=C["t3"]
        ))
        lay.addSpacing(14)
        lay.addWidget(sep())
        lay.addSpacing(12)

        bc = btn("Cerrar", "secondary")
        bc.clicked.connect(self.accept)
        lay.addWidget(bc)
        self._fin()


# ══════════════════════════════════════════════════════════════
# DIÁLOGO: CREAR / EDITAR
# ══════════════════════════════════════════════════════════════

class DialogFormEntidad(BaseDialog):
    def __init__(self, ops_id: int, datos_ini: dict | None = None, parent=None):
        titulo = "Editar entidad" if datos_ini else "Registrar nueva entidad"
        super().__init__(titulo, 600, parent)
        self._ops_id   = ops_id
        self._editando = datos_ini
        self._eid      = datos_ini["id"] if datos_ini else None
        self._build()

    def _build(self):
        lay      = self.lay
        editando = self._editando is not None

        # ── Identificación ────────────────────────────────────
        lay.addWidget(lbl("Identificación", size=12, color=C["t2"], bold=True))
        lay.addSpacing(8)

        # Nombre (fila completa)
        self.f_nombre = InputField("Nombre de la entidad",
                                   "Ej: E.S.E Hospital Local San Ángel", required=True)
        lay.addWidget(self.f_nombre)
        lay.addSpacing(10)

        # NIT + Código habilitación en fila
        row_nit = QHBoxLayout(); row_nit.setSpacing(10)
        self.f_nit = InputField("NIT", "Ej: 900123456-7", required=True)
        if editando:
            self.f_nit.setEnabled(False)
            self.f_nit.inp.setToolTip("El NIT no es modificable.")
        self.f_cod_hab = InputField("Código de habilitación", "Ej: 47001001234567")
        row_nit.addWidget(self.f_nit, 1)
        row_nit.addWidget(self.f_cod_hab, 2)
        lay.addLayout(row_nit)
        lay.addSpacing(12)

        # Nivel de atencion
        self.f_nivel = NivelSelector()
        lay.addWidget(self.f_nivel)
        lay.addSpacing(14)
        lay.addWidget(sep())
        lay.addSpacing(14)

        # ── Ubicación ─────────────────────────────────────────
        lay.addWidget(lbl("Ubicación", size=12, color=C["t2"], bold=True))
        lay.addSpacing(8)
        row_ub = QHBoxLayout(); row_ub.setSpacing(10)
        self.f_municipio    = InputField("Municipio", "Ej: Santa Marta")
        self.f_departamento = InputField("Departamento", "Ej: Magdalena")
        row_ub.addWidget(self.f_municipio, 1)
        row_ub.addWidget(self.f_departamento, 1)
        lay.addLayout(row_ub)
        lay.addSpacing(14)
        lay.addWidget(sep())
        lay.addSpacing(14)

        # ── Contacto y acceso ─────────────────────────────────
        lay.addWidget(lbl("Contacto y acceso", size=12, color=C["t2"], bold=True))
        lay.addSpacing(8)
        row_ct = QHBoxLayout(); row_ct.setSpacing(10)
        self.f_celular = InputField("Celular", "+57 300 000 0000", required=True)
        self.f_correo  = InputField("Correo electrónico", "correo@entidad.com", required=True)
        row_ct.addWidget(self.f_celular, 1)
        row_ct.addWidget(self.f_correo, 1)
        lay.addLayout(row_ct)
        lay.addSpacing(12)

        if not editando:
            row_pw = QHBoxLayout(); row_pw.setSpacing(10)
            self.f_pw  = InputField("Contraseña inicial", "Mínimo 8 caracteres",
                                    pw=True, required=True)
            self.f_pw2 = InputField("Confirmar contraseña", "", pw=True, required=True)
            row_pw.addWidget(self.f_pw, 1)
            row_pw.addWidget(self.f_pw2, 1)
            lay.addLayout(row_pw)
            lay.addSpacing(6)
            nota = QLabel("ℹ  La contraseña la establece el Maestro. La entidad puede cambiarla desde su perfil.")
            nota.setWordWrap(True)
            nota.setStyleSheet(
                f"background:rgba(5,150,105,0.08);border:1px solid {C['acc_dim']};"
                f"border-radius:7px;padding:8px 12px;color:{C['t2']};font-size:11px;"
            )
            lay.addWidget(nota)

        lay.addSpacing(16)
        self.sb = StatusBar()
        lay.addWidget(self.sb)
        lay.addSpacing(12)

        btn_row = QHBoxLayout()
        bc = btn("Cancelar", "secondary"); bc.clicked.connect(self.reject)
        label_ok = "Guardar cambios" if editando else "Registrar entidad"
        self.bok = btn(label_ok); self.bok.clicked.connect(self._guardar)
        btn_row.addWidget(bc); btn_row.addWidget(self.bok)
        lay.addLayout(btn_row)
        self._fin()

        if editando:
            d = self._editando
            self.f_nombre.set(d.get("nombre_entidad"))
            self.f_nit.set(d.get("nit"))
            self.f_cod_hab.set(d.get("codigo_habilitacion") or "")
            self.f_nivel.set_value(d.get("nivel_atencion"))
            self.f_municipio.set(d.get("municipio") or "")
            self.f_departamento.set(d.get("departamento") or "")
            self.f_celular.set(d.get("celular"))
            self.f_correo.set(d.get("correo"))

    def _guardar(self):
        self.sb.ocultar()
        self.bok.setEnabled(False)
        label_ok = "Guardar cambios" if self._editando else "Registrar entidad"
        self.bok.setText("Guardando…")

        def done(res: bk.Resultado):
            self.bok.setEnabled(True); self.bok.setText(label_ok)
            if res.ok:
                self.sb.ok(res.mensaje); QTimer.singleShot(700, self.accept)
            else:
                self.sb.err(res.mensaje)

        datos = {
            "nombre_entidad":      self.f_nombre.text(),
            "nit":                 self.f_nit.text(),
            "codigo_habilitacion": self.f_cod_hab.text(),
            "nivel_atencion":      self.f_nivel.value(),
            "municipio":           self.f_municipio.text(),
            "departamento":        self.f_departamento.text(),
            "celular":             self.f_celular.text(),
            "correo":              self.f_correo.text(),
        }
        if self._editando:
            run_async(bk.editar_entidad, self._ops_id, self._eid, datos, on_done=done)
        else:
            datos["password"]           = self.f_pw.text()
            datos["confirmar_password"] = self.f_pw2.text()
            run_async(bk.crear_entidad, self._ops_id, datos, on_done=done)


# ══════════════════════════════════════════════════════════════
# DIÁLOGO: RESETEAR CONTRASEÑA
# ══════════════════════════════════════════════════════════════

class DialogResetPw(BaseDialog):
    def __init__(self, ops_id: int, datos_entidad: dict, parent=None):
        super().__init__("Resetear contraseña", 460, parent)
        self._ops_id = ops_id
        self._datos  = datos_entidad
        self._build()

    def _build(self):
        lay = self.lay
        nota = QLabel(
            f"Reseteando la contraseña de:\n"
            f"{self._datos.get('nombre_entidad','')}\n"
            f"NIT: {self._datos.get('nit','')}\n\n"
            "Las sesiones activas de esta entidad serán cerradas."
        )
        nota.setWordWrap(True)
        nota.setStyleSheet(
            f"background:{C['card']};border:1px solid {C['border']};"
            f"border-radius:8px;padding:12px 14px;color:{C['t2']};font-size:12px;"
        )
        lay.addWidget(nota); lay.addSpacing(16)
        self.f_pw  = InputField("Nueva contraseña *", "Mínimo 8 caracteres", pw=True)
        self.f_pw2 = InputField("Confirmar contraseña *", "", pw=True)
        lay.addWidget(self.f_pw); lay.addSpacing(10)
        lay.addWidget(self.f_pw2); lay.addSpacing(16)
        self.sb = StatusBar(); lay.addWidget(self.sb); lay.addSpacing(12)
        row = QHBoxLayout()
        bc = btn("Cancelar", "secondary"); bc.clicked.connect(self.reject)
        self.bok = btn("Actualizar contraseña", "warn"); self.bok.clicked.connect(self._guardar)
        row.addWidget(bc); row.addWidget(self.bok); lay.addLayout(row)
        self._fin()

    def _guardar(self):
        self.sb.ocultar(); self.bok.setEnabled(False); self.bok.setText("Guardando…")

        def done(res: bk.Resultado):
            self.bok.setEnabled(True); self.bok.setText("Actualizar contraseña")
            if res.ok:
                self.sb.ok(res.mensaje); QTimer.singleShot(900, self.accept)
            else:
                self.sb.err(res.mensaje)

        run_async(bk.resetear_password_entidad, self._ops_id,
                  int(self._datos["id"]), self.f_pw.text(), self.f_pw2.text(), on_done=done)


# ══════════════════════════════════════════════════════════════
# TARJETA (modo compacto ≤ BP_CARD)
# ══════════════════════════════════════════════════════════════

class TarjetaEntidad(QWidget):
    def __init__(self, d: dict, callbacks: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("tarjeta")
        self.setStyleSheet(
            f"QWidget#tarjeta{{background:{C['card']};border:1px solid {C['border']};"
            f"border-radius:10px;}}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(5)

        # Nombre + badges
        top = QWidget(); top.setStyleSheet("background:transparent;border:none;")
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(0, 0, 0, 0); top_lay.setSpacing(6)
        nombre_lb = lbl(d.get("nombre_entidad", ""), size=13, bold=True)
        nombre_lb.setWordWrap(True)
        top_lay.addWidget(nombre_lb, 1)
        if d.get("protegido"):
            top_lay.addWidget(_badge_protegida())
        top_lay.addWidget(
            _badge("● Activa" if d.get("activo") else "○ Inactiva",
                   C["ok"] if d.get("activo") else C["err"],
                   "rgba(16,185,129,0.14)" if d.get("activo") else "rgba(239,68,68,0.12)")
        )
        lay.addWidget(top)

        lay.addWidget(lbl(f"NIT: {d.get('nit','')}", size=12, color=C["t2"]))

        partes = [x for x in [d.get("municipio"), d.get("departamento")] if x]
        if partes:
            lay.addWidget(lbl("  ·  ".join(partes), size=12, color=C["t2"]))

        lay.addWidget(lbl(d.get("correo", ""), size=11, color=C["t3"]))

        ops_txt = f"OPS: {d.get('ops_activos',0)}/{d.get('total_ops',0)}"
        ses = d.get("sesiones_activas", 0)
        if ses:
            ops_txt += f"  |  ⚡{ses} sesión"
        lay.addWidget(lbl(ops_txt, size=11, color=C["acc_h"]))

        lay.addWidget(sep())

        btn_row = QHBoxLayout(); btn_row.setSpacing(5)
        for texto, estilo, key in [("Ver","ghost","ver"),("Editar","ghost","editar"),("🔑","warn","pw")]:
            b = btn(texto, estilo)
            b.setFixedHeight(30)
            b.clicked.connect(lambda _, k=key: callbacks[k](d))
            btn_row.addWidget(b)

        if not d.get("protegido"):
            activo = d.get("activo", True)
            b_est = btn("Desactivar" if activo else "✅ Activar",
                        "danger" if activo else "success")
            b_est.setFixedHeight(30)
            b_est.clicked.connect(lambda _, a=activo: callbacks["estado"](d, not a))
            btn_row.addWidget(b_est)

        lay.addLayout(btn_row)


# ══════════════════════════════════════════════════════════════
# TABLA — definición de columnas con visibilidad por breakpoint
# ══════════════════════════════════════════════════════════════

# (nombre_header, ancho_minimo, visible_en_narrow, stretch)
_COLS: list[tuple[str, int, bool, bool]] = [
    ("",            28,  True,  False),   # 0 – icono
    ("Nombre",      160, True,  True),    # 1 – stretch
    ("NIT",         110, True,  False),   # 2
    ("Municipio",   100, False, False),   # 3 – oculta en narrow
    ("Nivel",       110, False, False),   # 4 – oculta en narrow
    ("OPS",          55, False, False),   # 5 – oculta en narrow
    ("Estado",       80, True,  False),   # 6
    ("Acciones",    155, True,  False),   # 7
]


def _nueva_tabla() -> QTableWidget:
    t = QTableWidget()
    t.setColumnCount(len(_COLS))
    t.setHorizontalHeaderLabels([c[0] for c in _COLS])
    t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(False)
    # Col 1 (Nombre) es la única que estira
    t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    for i, (_, w, _, _) in enumerate(_COLS):
        if i != 1:
            t.setColumnWidth(i, w)
            t.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
    t.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return t


def _ajustar_columnas_tabla(tabla: QTableWidget, ancho_disponible: int):
    """
    Muestra / oculta columnas según el ancho disponible.
    Solo la columna Nombre (idx 1) estira; el resto son Fixed.
    """
    narrow = ancho_disponible < BP_NARROW
    for i, (_, w, visible_narrow, _) in enumerate(_COLS):
        if i == 1:
            continue  # la maneja QHeaderView::Stretch
        ocultar = narrow and not visible_narrow
        tabla.setColumnHidden(i, ocultar)
        if not ocultar:
            tabla.setColumnWidth(i, w)


def _botones_fila(d: dict, callbacks: dict) -> QWidget:
    w = QWidget(); w.setStyleSheet("background:transparent;")
    lay = QHBoxLayout(w); lay.setContentsMargins(3, 1, 3, 1)
    lay.setSpacing(3); lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

    for icono, tip, key in [("👁","Ver","ver"),("✏","Editar","editar"),("🔑","Contraseña","pw")]:
        b = btn(icono, "icon"); b.setToolTip(tip); b.setFixedSize(30, 30)
        b.clicked.connect(lambda _, k=key: callbacks[k](d))
        lay.addWidget(b)

    if not d.get("protegido"):
        activo = d.get("activo", True)
        b_est = btn("⛔" if activo else "✅", "icon")
        b_est.setToolTip("Desactivar" if activo else "Activar"); b_est.setFixedSize(30, 30)
        b_est.clicked.connect(lambda _, a=activo: callbacks["estado"](d, not a))
        lay.addWidget(b_est)

    return w


# ══════════════════════════════════════════════════════════════
# HEADER — estadísticas + búsqueda + filtros
# ══════════════════════════════════════════════════════════════

class HeaderEntidad(QWidget):
    busqueda_cambiada = Signal(str)
    nuevo_clicked     = Signal()
    filtro_cambiado   = Signal(str)

    def __init__(self, ops_id: int, parent=None):
        super().__init__(parent)
        self._ops_id = ops_id
        self._filtro_sel = "todos"
        self.setStyleSheet("background:transparent;border:none;")
        self._build()
        self._cargar_stats()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)

        # Fila título
        title_row = QHBoxLayout(); title_row.setSpacing(8)
        title_row.addWidget(lbl("Gestión de Entidades", size=20, bold=True))
        tag = QLabel("  ♛ Maestro  ")
        tag.setStyleSheet(
            f"background:{C['maestro_d']};color:{C['maestro']};"
            f"border:1px solid {C['maestro']};border-radius:7px;"
            f"padding:4px 10px;font-size:11px;font-weight:700;"
        )
        title_row.addWidget(tag)
        title_row.addStretch()
        self._btn_nuevo = btn("＋ Nueva entidad")
        self._btn_nuevo.setMinimumHeight(38)
        self._btn_nuevo.clicked.connect(self.nuevo_clicked)
        title_row.addWidget(self._btn_nuevo)
        lay.addLayout(title_row)

        lay.addWidget(lbl(
            "Solo el Maestro puede gestionar las entidades del sistema.",
            size=11, color=C["t3"]
        ))

        # Stats — QHBoxLayout con wrapping en dos filas via QGridLayout cuando hay poco espacio
        self._sc: dict = {}
        self._stats_outer = QWidget()
        self._stats_outer.setStyleSheet("background:transparent;border:none;")
        self._stats_grid = QGridLayout(self._stats_outer)
        self._stats_grid.setContentsMargins(0, 0, 0, 0)
        self._stats_grid.setSpacing(6)
        stats_list = [
            ("total",            "Total",         C["t2"]),
            ("activas",          "Activas",       C["ok"]),
            ("inactivas",        "Inactivas",     C["err"]),
            ("protegidas",       "Protegidas",    C["prot"]),
            ("sesiones_en_curso","En sesion",     C["acc_h"]),
        ]
        for i, (key, etq, color) in enumerate(stats_list):
            card = QWidget()
            card.setMinimumWidth(80)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            card.setStyleSheet(
                f"QWidget{{background:{C['card']};border:1px solid {C['border']};"
                f"border-radius:8px;}}"
            )
            cl = QVBoxLayout(card); cl.setContentsMargins(10, 7, 10, 7); cl.setSpacing(1)
            v = lbl("--", size=18, color=color, bold=True)
            t = lbl(etq, size=10, color=C["t2"])
            cl.addWidget(v); cl.addWidget(t)
            card._val = v
            self._sc[key] = card
            # fila 0 en pantallas anchas; se reordena en _adaptar_stats
            self._stats_grid.addWidget(card, 0, i)
        lay.addWidget(self._stats_outer)

        # Búsqueda + filtros
        search_row = QHBoxLayout(); search_row.setSpacing(6)
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Buscar por nombre, NIT, municipio, departamento o correo…")
        self._search.setMinimumHeight(38)
        self._timer = QTimer(self); self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.busqueda_cambiada.emit(self._search.text()))
        self._search.textChanged.connect(lambda: self._timer.start(350))
        search_row.addWidget(self._search, 1)

        self._fb = {}
        for f_id, txt in [("todos","Todas"),("activas","Activas"),("inactivas","Inactivas")]:
            b = QPushButton(txt)
            b.setMinimumHeight(38); b.setMinimumWidth(80)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.clicked.connect(lambda _, fi=f_id: self._set_filtro(fi))
            self._fb[f_id] = b
            search_row.addWidget(b)

        lay.addLayout(search_row)
        self._render_filtros()

    def _set_filtro(self, f_id: str):
        self._filtro_sel = f_id
        self._render_filtros()
        self.filtro_cambiado.emit(f_id)

    def _render_filtros(self):
        temas = {
            "todos":    (C["t2"],  C["input"], C["border"]),
            "activas":  (C["ok"],  C["ok_d"],  C["ok"]),
            "inactivas":(C["err"], C["err_d"], C["err"]),
        }
        for f_id, b in self._fb.items():
            color, bg, border = temas[f_id]
            sel = (f_id == self._filtro_sel)
            if sel:
                b.setStyleSheet(
                    f"QPushButton{{background:{bg};color:{color};"
                    f"border:1px solid {border};border-radius:8px;"
                    f"padding:0 10px;font-size:12px;font-weight:700;}}"
                )
            else:
                b.setStyleSheet(
                    f"QPushButton{{background:{C['input']};color:{C['t2']};"
                    f"border:1.5px solid {C['border']};border-radius:8px;"
                    f"padding:0 10px;font-size:12px;}}"
                    f"QPushButton:hover{{border-color:{C['border_f']};color:{C['t1']};}}"
                )

    def _cargar_stats(self):
        def done(s):
            if not isinstance(s, dict):
                return
            for key, card in self._sc.items():
                card._val.setText(str(s.get(key, "—")))
        run_async(bk.stats_globales, self._ops_id, on_done=done)

    def refrescar(self):
        self._cargar_stats()

    # Ocultar botón "Nueva" si el ancho es muy pequeño
    def adaptar(self, ancho: int):
        self._btn_nuevo.setVisible(ancho > 440)
        self._adaptar_stats(ancho)

    def _adaptar_stats(self, ancho: int):
        """Reorganiza las tarjetas de stats segun el ancho disponible."""
        n = len(self._sc)
        # Quitar todos los widgets del grid
        for i in range(self._stats_grid.count()):
            item = self._stats_grid.itemAt(i)
            if item and item.widget():
                self._stats_grid.removeWidget(item.widget())
        cards = list(self._sc.values())
        if ancho < 500:
            # 2 columnas x 3 filas
            cols = 2
        elif ancho < 800:
            # 3 columnas x 2 filas
            cols = 3
        else:
            # 5 en una sola fila
            cols = 5
        for i, card in enumerate(cards):
            self._stats_grid.addWidget(card, i // cols, i % cols)


# ══════════════════════════════════════════════════════════════
# PANTALLA DE BLOQUEO
# ══════════════════════════════════════════════════════════════

class PantallaBloqueo(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(STYLE)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(14)
        ic = lbl("🔒", size=48)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ic)
        lay.addWidget(lbl("Acceso restringido", size=22, bold=True, color=C["err"]))
        lay.addWidget(lbl(
            "Este módulo es exclusivo del usuario Maestro.\n"
            "Inicia sesión con las credenciales del Maestro para acceder.",
            size=13, color=C["t2"], wrap=True
        ))


# ══════════════════════════════════════════════════════════════
# PANEL PRINCIPAL
# ══════════════════════════════════════════════════════════════

class PanelEntidad(QWidget):
    """
    Widget autónomo. Insértalo en cualquier layout:
        panel = PanelEntidad(ops_id=maestro_id)
        main_layout.addWidget(panel)
    """

    def __init__(self, ops_id: int, parent=None):
        super().__init__(parent)
        self._ops_id   = ops_id
        self._datos:   list[dict] = []
        self._filtro   = ""
        self._f_estado = "todos"
        self._compacto = False          # tarjetas vs tabla
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._aplicar_resize)
        self.setStyleSheet(STYLE)

        if not bk._es_maestro_ops(ops_id):
            QVBoxLayout(self).addWidget(PantallaBloqueo())
            return

        self._build()
        self._cargar()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        self._header = HeaderEntidad(self._ops_id)
        self._header.busqueda_cambiada.connect(self._on_busqueda)
        self._header.nuevo_clicked.connect(self._nuevo)
        self._header.filtro_cambiado.connect(self._on_filtro)
        lay.addWidget(self._header)
        lay.addWidget(sep())

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background:transparent;border:none;")

        # Índice 0 — tabla
        self._tabla = _nueva_tabla()
        self._stack.addWidget(self._tabla)

        # Índice 1 — tarjetas con scroll
        self._scroll_c = QScrollArea()
        self._scroll_c.setWidgetResizable(True)
        self._scroll_c.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_c.setStyleSheet("background:transparent;border:none;")
        self._cont_c = QWidget(); self._cont_c.setStyleSheet("background:transparent;border:none;")
        self._lay_c  = QVBoxLayout(self._cont_c)
        self._lay_c.setContentsMargins(0, 0, 0, 0); self._lay_c.setSpacing(8)
        self._scroll_c.setWidget(self._cont_c)
        self._stack.addWidget(self._scroll_c)
        lay.addWidget(self._stack, 1)

        self._lbl_vacio = lbl("No se encontraron entidades.", size=13, color=C["t2"])
        self._lbl_vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_vacio.hide()
        lay.addWidget(self._lbl_vacio)

    # ── Carga ─────────────────────────────────────────────────

    def _cargar(self):
        sa = self._f_estado == "activas"
        si = self._f_estado == "inactivas"

        def _fetch():
            try:
                return bk.listar_entidades(self._ops_id, self._filtro, sa, si)
            except Exception as e:
                return bk.Resultado(False, str(e))

        run_async(_fetch, on_done=self._poblar)

    def _poblar(self, datos):
        if isinstance(datos, bk.Resultado):
            QMessageBox.warning(self, "Error", datos.mensaje)
            return
        self._datos = datos if isinstance(datos, list) else []
        self._lbl_vacio.setVisible(len(self._datos) == 0)
        if self._compacto:
            self._poblar_tarjetas()
        else:
            self._poblar_tabla()
        self._header.refrescar()

    def _poblar_tabla(self):
        t = self._tabla; cb = self._callbacks()
        t.setRowCount(0)
        for d in self._datos:
            r = t.rowCount(); t.insertRow(r)

            # Col 0 — icono
            badge_w = QWidget(); badge_w.setStyleSheet("background:transparent;")
            bl = QHBoxLayout(badge_w); bl.setContentsMargins(2,1,2,1)
            bl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if d.get("protegido"):
                ic = QLabel("🔒"); ic.setStyleSheet(f"color:{C['prot']};font-size:12px;background:transparent;")
                bl.addWidget(ic)
            elif d.get("sesiones_activas", 0):
                ic = QLabel("⚡"); ic.setStyleSheet(f"color:{C['acc_h']};font-size:12px;background:transparent;")
                bl.addWidget(ic)
            t.setCellWidget(r, 0, badge_w)

            it_nom = _it(d.get("nombre_entidad", ""))
            if not d.get("activo", True):
                it_nom.setForeground(QColor(C["t3"]))
            t.setItem(r, 1, it_nom)
            t.setItem(r, 2, _it(d.get("nit", "")))
            t.setItem(r, 3, _it(d.get("municipio") or "—"))
            t.setItem(r, 4, _it(d.get("nivel_texto", "—")))
            t.setItem(r, 5, _it(f"{d.get('ops_activos',0)}/{d.get('total_ops',0)}"))
            t.setCellWidget(r, 6, _badge_activo(d.get("activo", True)))
            t.setCellWidget(r, 7, _botones_fila(d, cb))
            t.setRowHeight(r, 48)

    def _poblar_tarjetas(self):
        while self._lay_c.count():
            item = self._lay_c.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        cb = self._callbacks()
        for d in self._datos:
            self._lay_c.addWidget(TarjetaEntidad(d, cb))
        self._lay_c.addStretch()

    def _callbacks(self) -> dict:
        return {"ver": self._ver, "editar": self._editar,
                "pw": self._pw, "estado": self._estado}

    # ── Acciones ──────────────────────────────────────────────

    def _nuevo(self):
        if DialogFormEntidad(self._ops_id, parent=self).exec():
            self._cargar()

    def _ver(self, d: dict):
        try:
            datos = bk.obtener_entidad(self._ops_id, int(d["id"]))
            if datos: DialogVerEntidad(datos, self).exec()
            else: QMessageBox.warning(self, "Error", "Entidad no encontrada.")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def _editar(self, d: dict):
        try:
            datos = bk.obtener_entidad(self._ops_id, int(d["id"]))
            if not datos: QMessageBox.warning(self, "Error", "Entidad no encontrada."); return
            if DialogFormEntidad(self._ops_id, datos_ini=datos, parent=self).exec():
                self._cargar()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def _pw(self, d: dict):
        try:
            datos = bk.obtener_entidad(self._ops_id, int(d["id"]))
            if datos: DialogResetPw(self._ops_id, datos, self).exec()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def _estado(self, d: dict, nuevo_activo: bool):
        nombre = d.get("nombre_entidad", "")
        accion = "activar" if nuevo_activo else "desactivar"
        msg = f"¿Deseas {accion} la entidad '{nombre}'?"
        if not nuevo_activo:
            msg += "\n\nEsto cerrará todas las sesiones activas de la entidad y sus OPS."
        if QMessageBox.question(self, f"Confirmar {accion}", msg,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                ) != QMessageBox.StandardButton.Yes:
            return
        res = bk.cambiar_estado_entidad(self._ops_id, int(d["id"]), nuevo_activo)
        if res.ok: self._cargar()
        else: QMessageBox.warning(self, "Error", res.mensaje)

    # ── Filtros ───────────────────────────────────────────────

    def _on_busqueda(self, texto: str):
        self._filtro = texto; self._cargar()

    def _on_filtro(self, f_estado: str):
        self._f_estado = f_estado; self._cargar()

    # ── Responsive ───────────────────────────────────────────

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        # Debounce 40 ms para no recalcular en cada píxel
        self._resize_timer.start(40)

    def _aplicar_resize(self):
        w = self.width()
        nuevo_compacto = w < BP_CARD

        if nuevo_compacto != self._compacto:
            self._compacto = nuevo_compacto
            self._stack.setCurrentIndex(1 if nuevo_compacto else 0)
            if nuevo_compacto:
                self._poblar_tarjetas()
            else:
                self._poblar_tabla()

        if not self._compacto:
            # Márgenes del panel (16×2) = 32 px
            disponible = max(200, w - 32)
            _ajustar_columnas_tabla(self._tabla, disponible)

        # El header también se adapta
        self._header.adaptar(w)


# ══════════════════════════════════════════════════════════════
# VENTANA AUTÓNOMA
# ══════════════════════════════════════════════════════════════

class EntidadWindow(QMainWindow):
    """
    Ventana standalone.
        win = EntidadWindow(ops_id=maestro_ops_id)
        win.show()
    """

    def __init__(self, ops_id: int):
        super().__init__()
        self.setWindowTitle("SIGES — Gestión de Entidades")
        self.setMinimumSize(360, 500)

        # Tamaño inicial: 85% de la pantalla, máximo 1440×900
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.resize(min(int(geo.width() * 0.85), 1440),
                        min(int(geo.height() * 0.85), 900))
        else:
            self.resize(1280, 800)

        self.setStyleSheet(STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # Top bar
        top = QWidget(); top.setFixedHeight(52)
        top.setStyleSheet(f"QWidget{{background:{C['panel']};border-bottom:1px solid {C['border']};}}")
        tl = QHBoxLayout(top); tl.setContentsMargins(20, 0, 20, 0); tl.setSpacing(8)
        tl.addWidget(lbl("⚕", size=20, color=C["acc_h"]))
        nm = QLabel("SIGES")
        nm.setStyleSheet(
            f"color:{C['white']};font-size:14px;font-weight:800;"
            f"letter-spacing:3px;background:transparent;"
        )
        tl.addWidget(nm)
        tl.addWidget(lbl(" / ", size=14, color=C["t3"]))
        tl.addWidget(lbl("Gestión de Entidades", size=13, color=C["t2"]))
        tl.addStretch()
        tag = QLabel("  ♛ Solo Maestro  ")
        tag.setStyleSheet(
            f"background:{C['maestro_d']};color:{C['maestro']};"
            f"border:1px solid {C['maestro']};border-radius:6px;"
            f"padding:3px 10px;font-size:11px;font-weight:700;"
        )
        tl.addWidget(tag)
        root.addWidget(top)
        root.addWidget(PanelEntidad(ops_id=ops_id), 1)


# ══════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = EntidadWindow(ops_id=1)   # reemplazar con ops_id real del Maestro
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()