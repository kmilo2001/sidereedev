# -*- coding: utf-8 -*-
"""
gestion_afiliacion_ui.py
=========================
Seccion 5.2 - Tipos de Afiliacion (Admin y OPS).

Acciones disponibles por fila:
  - Ver detalle   (catalogo oficial y personalizado)
  - Editar        (solo personalizado)
  - Activar / Desactivar  (solo personalizado)
  - Eliminar      (solo personalizado, sin dependencias)

Interaccion con el menu de acciones:
  - Click izquierdo sobre el icono  →  despliega el menu
  - Click derecho  sobre la fila    →  despliega el mismo menu

Busqueda en tiempo real con debounce de 300 ms.

Sistema responsivo — 3 modos:
  < 500px   Compacto:   Nombre | Estado | Acciones
  500-900px Tablet:     Nombre | Cod. | Tipo | Estado | Acciones
  > 900px   Escritorio: ID | Nombre | Cod. | Tipo | Estado | Acciones
"""
from __future__ import annotations

import sys
import io
from functools import partial

# Nota: la reasignacion de sys.stdout la maneja main.py al arrancar.
# No se reasigna aqui para evitar "I/O operation on closed file"
# cuando el modulo se importa de forma lazy dentro del proceso principal.

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem,
    QFrame, QSizePolicy, QScrollArea,
    QAbstractItemView, QMessageBox, QMenu,
    QHeaderView,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer, QPoint
from PySide6.QtGui import QCursor, QFont, QResizeEvent

import gestion_afiliacion_backend as afil_bk


# ══════════════════════════════════════════════════════════════
# PALETA Y ESTILOS
# ══════════════════════════════════════════════════════════════

P = {
    "bg":      "#0D1117", "card":    "#161B22", "input":   "#21262D",
    "border":  "#30363D", "focus":   "#388BFD", "accent":  "#2D6ADF",
    "acc_h":   "#388BFD", "acc_lt":  "#1C3A6E",
    "ok":      "#3FB950", "err":     "#F85149", "warn":    "#D29922",
    "txt":     "#E6EDF3", "txt2":    "#8B949E", "muted":   "#484F58",
    "white":   "#FFFFFF", "row_alt": "#0F1419", "row_sel": "#1C3A6E",
    "oficial": "#8B5CF6",
}

BP_COMPACT = 500
BP_TABLET  = 900

_CSS_BASE = f"""
QWidget {{
    background-color:{P['bg']}; color:{P['txt']};
    font-family:'Segoe UI','Helvetica Neue',Arial,sans-serif; font-size:13px;
}}
QLabel  {{ background:transparent; }}
QDialog {{ background-color:{P['bg']}; }}
QLineEdit {{
    background:{P['input']}; border:1.5px solid {P['border']};
    border-radius:7px; padding:8px 12px; color:{P['txt']}; font-size:13px;
}}
QLineEdit:focus  {{ border-color:{P['focus']}; background:#1C2128; }}
QLineEdit:disabled {{ color:{P['muted']}; background:{P['card']}; }}
QScrollBar:vertical,QScrollBar:horizontal {{
    background:transparent; width:8px; height:8px;
}}
QScrollBar::handle:vertical,QScrollBar::handle:horizontal {{
    background:{P['border']}; border-radius:4px; min-height:20px;
}}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal {{ height:0; width:0; }}
QTableWidget {{
    background:{P['card']}; border:1px solid {P['border']};
    border-radius:8px; gridline-color:{P['border']};
    color:{P['txt']}; font-size:13px;
    alternate-background-color:{P['row_alt']};
    selection-background-color:{P['row_sel']}; selection-color:{P['txt']};
}}
QTableWidget::item {{ padding:6px 10px; border:none; }}
QHeaderView::section {{
    background:#0F1419; color:{P['txt2']}; border:none;
    border-right:1px solid {P['border']}; border-bottom:1px solid {P['border']};
    padding:8px 10px; font-size:12px; font-weight:600;
}}
"""

_CSS_LINE = (
    f"QLineEdit{{background:{P['input']};border:1.5px solid {P['border']};"
    f"border-radius:7px;padding:8px 12px;color:{P['txt']};font-size:13px;}}"
    f"QLineEdit:focus{{border-color:{P['focus']};background:#1C2128;}}"
    f"QLineEdit:disabled{{color:{P['muted']};background:{P['card']};}}"
)

# Indices de columnas
_CI, _CN, _CC, _CT, _CE, _CA = 0, 1, 2, 3, 4, 5


# ══════════════════════════════════════════════════════════════
# HILO DE TRABAJO
# ══════════════════════════════════════════════════════════════

class _Worker(QThread):
    done = Signal(object)
    def __init__(self, fn, args, kw):
        super().__init__()
        self._fn, self._args, self._kw = fn, args, kw
    def run(self):
        try:    self.done.emit(self._fn(*self._args, **self._kw))
        except Exception as e:
            self.done.emit(afil_bk.Resultado(False, str(e)))

_workers: list = []

def _run_async(parent, fn, *args, on_done=None, **kw):
    w = _Worker(fn, args, kw)
    _workers.append(w)
    if on_done: w.done.connect(on_done)
    w.done.connect(lambda _: _workers.remove(w) if w in _workers else None)
    w.start()


# ══════════════════════════════════════════════════════════════
# HELPERS DE WIDGETS
# ══════════════════════════════════════════════════════════════

def _lbl(txt, size=13, color=None, bold=False, wrap=False):
    lb = QLabel(txt)
    lb.setStyleSheet(
        f"color:{color or P['txt']};font-size:{size}px;"
        f"font-weight:{'600' if bold else '400'};background:transparent;"
    )
    if wrap: lb.setWordWrap(True)
    return lb

def _sep():
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(
        f"border:none;border-top:1px solid {P['border']};background:transparent;"
    )
    f.setFixedHeight(1); return f

def _btn(txt, style="prim", parent=None):
    b = QPushButton(txt, parent)
    S = {
        "prim":   (f"QPushButton{{background:{P['accent']};color:white;border:none;"
                   f"border-radius:7px;padding:9px 18px;font-size:13px;font-weight:600;}}"
                   f"QPushButton:hover{{background:{P['acc_h']};}}"
                   f"QPushButton:pressed{{background:#1A4FAF;}}"
                   f"QPushButton:disabled{{background:{P['muted']};color:{P['bg']};}}"),
        "sec":    (f"QPushButton{{background:transparent;color:{P['txt2']};"
                   f"border:1.5px solid {P['border']};border-radius:7px;"
                   f"padding:8px 18px;font-size:13px;font-weight:500;}}"
                   f"QPushButton:hover{{border-color:{P['focus']};color:{P['txt']};"
                   f"background:{P['input']};}}"),
        "danger": (f"QPushButton{{background:rgba(248,81,73,.15);color:{P['err']};"
                   f"border:1px solid {P['err']};border-radius:7px;"
                   f"padding:7px 14px;font-size:12px;font-weight:600;}}"
                   f"QPushButton:hover{{background:rgba(248,81,73,.28);}}"),
        "ok":     (f"QPushButton{{background:rgba(63,185,80,.15);color:{P['ok']};"
                   f"border:1px solid {P['ok']};border-radius:7px;"
                   f"padding:7px 14px;font-size:12px;font-weight:600;}}"
                   f"QPushButton:hover{{background:rgba(63,185,80,.28);}}"),
    }
    b.setStyleSheet(S.get(style, S["prim"]))
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    return b

def _item(txt, align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft):
    i = QTableWidgetItem(str(txt) if txt is not None else "")
    i.setFlags(i.flags() & ~Qt.ItemFlag.ItemIsEditable)
    i.setTextAlignment(align)
    return i

def _tag(texto: str, color: str, rgb: str) -> QWidget:
    w = QWidget(); w.setStyleSheet("background:transparent;")
    lay = QHBoxLayout(w); lay.setContentsMargins(4,2,4,2)
    lb = QLabel(texto)
    lb.setStyleSheet(
        f"background:rgba({rgb},.18);color:{color};border:1px solid {color};"
        f"border-radius:10px;padding:2px 10px;font-size:11px;font-weight:600;"
    )
    lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(lb); return w

def _tag_estado(activo: bool) -> QWidget:
    return _tag(
        "Activo" if activo else "Inactivo",
        P["ok"] if activo else P["err"],
        "63,185,80" if activo else "248,81,73",
    )

def _tag_tipo(es_oficial: bool) -> QWidget:
    return _tag(
        "Ley 100" if es_oficial else "Personalizado",
        P["oficial"] if es_oficial else P["focus"],
        "139,92,246" if es_oficial else "56,139,253",
    )

def _make_table(cols):
    t = QTableWidget()
    t.setColumnCount(len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(True)
    t.setShowGrid(True)
    t.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    # Click derecho en la fila → menu contextual (se conecta en TabAfiliacion)
    t.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    return t


# ══════════════════════════════════════════════════════════════
# MENU DE ACCIONES (unico, reutilizable)
# ══════════════════════════════════════════════════════════════

def _build_menu(
    es_oficial: bool,
    activo:     bool,
    on_ver,
    on_editar,
    on_estado,
    on_eliminar,
) -> QMenu:
    """
    Construye el QMenu con las acciones disponibles segun el tipo de registro.

    Catalogo oficial (Ley 100):  solo Ver.
    Personalizado activo:        Ver | Editar | Desactivar | Eliminar
    Personalizado inactivo:      Ver | Editar | Activar    | Eliminar
    """
    m = QMenu()
    m.setStyleSheet(
        f"QMenu{{background:{P['card']};color:{P['txt']};"
        f"border:1.5px solid {P['border']};border-radius:10px;"
        f"padding:6px 0;font-size:13px;}}"
        f"QMenu::item{{padding:10px 22px 10px 16px;"
        f"border-radius:5px;margin:1px 6px;}}"
        f"QMenu::item:selected{{background:{P['acc_lt']};color:{P['acc_h']};}}"
        f"QMenu::item:disabled{{color:{P['muted']};}}"
        f"QMenu::separator{{background:{P['border']};height:1px;margin:5px 10px;}}"
    )

    # --- Ver (siempre disponible) ---
    a_ver = m.addAction("  Ver detalle")
    a_ver.triggered.connect(on_ver)

    if es_oficial:
        m.addSeparator()
        inf = m.addAction("  Catalogo oficial — solo lectura")
        inf.setEnabled(False)
        return m

    # --- Editar ---
    m.addSeparator()
    a_ed = m.addAction("  Editar")
    a_ed.triggered.connect(on_editar)

    # --- Activar / Desactivar ---
    m.addSeparator()
    lbl_est = "  Desactivar" if activo else "  Activar"
    a_est = m.addAction(lbl_est)
    a_est.triggered.connect(on_estado)
    # Color visual
    css_est = (
        f"color:{P['warn']};" if activo
        else f"color:{P['ok']};"
    )
    a_est.setData(css_est)   # guardamos para colorear si necesario

    # --- Eliminar ---
    m.addSeparator()
    a_del = m.addAction("  Eliminar")
    a_del.triggered.connect(on_eliminar)
    # Colorear en rojo con stylesheet via widget action
    # (QMenu no soporta color por item directamente, usamos el texto)

    return m


def _popup(menu: QMenu, widget: QWidget | None = None, pos: QPoint | None = None):
    """Muestra el menu en la posicion correcta."""
    if pos:
        menu.exec(pos)
    elif widget:
        menu.exec(widget.mapToGlobal(widget.rect().bottomLeft()))
    else:
        menu.exec(QCursor.pos())


# ══════════════════════════════════════════════════════════════
# WIDGETS REUTILIZABLES
# ══════════════════════════════════════════════════════════════

class StatusBar(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hide()
    def _show(self, msg, css):
        self.setStyleSheet(css); self.setText(msg); self.show()
    def ok(self, m):
        self._show(m,
            f"background:rgba(63,185,80,.15);border:1px solid {P['ok']};"
            f"border-radius:7px;color:{P['ok']};padding:9px 14px;font-size:12px;")
    def err(self, m):
        self._show(m,
            f"background:rgba(248,81,73,.15);border:1px solid {P['err']};"
            f"border-radius:7px;color:{P['err']};padding:9px 14px;font-size:12px;")
    def warn(self, m):
        self._show(m,
            f"background:rgba(210,153,34,.15);border:1px solid {P['warn']};"
            f"border-radius:7px;color:{P['warn']};padding:9px 14px;font-size:12px;")
    def ocultar(self): self.hide()


class InputF(QWidget):
    def __init__(self, label: str, ph: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QWidget{{background:{P['bg']};border:none;}}")
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(4)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color:{P['txt2']};font-size:12px;background:transparent;")
        lay.addWidget(lbl)
        self.inp = QLineEdit()
        self.inp.setPlaceholderText(ph)
        self.inp.setMinimumHeight(40)
        self.inp.setStyleSheet(_CSS_LINE)
        self._err_lbl = QLabel("")
        self._err_lbl.setStyleSheet(
            f"color:{P['err']};font-size:11px;background:transparent;"
        )
        self._err_lbl.hide()
        lay.addWidget(self.inp); lay.addWidget(self._err_lbl)
    def text(self) -> str: return self.inp.text().strip()
    def set(self, v):       self.inp.setText(str(v) if v else "")
    def clear(self):        self.inp.clear()
    def setEnabled(self, v: bool): self.inp.setEnabled(v)
    def err(self, m: str):
        self._err_lbl.setText(m); self._err_lbl.show()
        self.inp.setStyleSheet(_CSS_LINE + f"QLineEdit{{border-color:{P['err']};}}")
    def ok(self):
        self._err_lbl.hide(); self.inp.setStyleSheet(_CSS_LINE)


# ══════════════════════════════════════════════════════════════
# BASE DIALOG RESPONSIVO
# ══════════════════════════════════════════════════════════════

class BaseDialog(QDialog):
    def __init__(self, titulo: str, ancho_ref: int = 460, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setStyleSheet(f"QDialog{{background:{P['bg']};}}" + _CSS_BASE)

        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self._max_w = int(geo.width()  * 0.95)
            self._max_h = int(geo.height() * 0.92)
        else:
            self._max_w, self._max_h = 900, 700

        ancho = min(ancho_ref, self._max_w)
        self.setMinimumWidth(min(300, ancho))
        self.setMaximumWidth(self._max_w)
        self.setMaximumHeight(self._max_h)

        outer  = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea{{border:none;background:{P['bg']};}}"
            f"QScrollBar:vertical{{background:{P['bg']};width:8px;}}"
            f"QScrollBar::handle:vertical{{background:{P['border']};"
            f"border-radius:4px;min-height:20px;}}"
            f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}"
        )
        inner = QWidget(); inner.setStyleSheet(f"background:{P['bg']};")
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(24,20,24,20); self.lay.setSpacing(0)
        t = QLabel(titulo)
        t.setStyleSheet(
            f"color:{P['txt']};font-size:17px;font-weight:700;background:transparent;"
        )
        self.lay.addWidget(t); self.lay.addSpacing(8)
        self.lay.addWidget(_sep()); self.lay.addSpacing(16)
        scroll.setWidget(inner); outer.addWidget(scroll)
        self.resize(ancho, min(400, self._max_h))

    def _fin(self):
        QTimer.singleShot(0, self._aplicar_tamanio)

    def _aplicar_tamanio(self):
        self.adjustSize()
        w = min(self.width(),  self._max_w)
        h = max(min(self.height(), self._max_h), 200)
        self.resize(w, h)
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.x()+(geo.width() -w)//2,
                geo.y()+(geo.height()-h)//2,
            )


# ══════════════════════════════════════════════════════════════
# DIALOGO VER (solo lectura)
# ══════════════════════════════════════════════════════════════

class DialogAfiliacionVer(BaseDialog):
    def __init__(self, datos: dict, parent=None):
        super().__init__("Detalle — Tipo de afiliacion", 420, parent)
        lay = self.lay

        if datos.get("es_catalogo_oficial"):
            ri = QHBoxLayout()
            ins = QLabel("  Catalogo oficial — Ley 100/1993 (MSPS)  ")
            ins.setStyleSheet(
                f"background:rgba(139,92,246,.18);color:{P['oficial']};"
                f"border:1px solid {P['oficial']};border-radius:10px;"
                f"padding:4px 12px;font-size:11px;font-weight:600;"
            )
            ri.addWidget(ins); ri.addStretch()
            lay.addLayout(ri); lay.addSpacing(14)

        for etiqueta, valor in [
            ("ID",                str(datos.get("id", ""))),
            ("Nombre",            datos.get("nombre", "")),
            ("Codigo RIPS",       datos.get("codigo", "") or "—"),
            ("Estado",            "Activo" if datos.get("activo") else "Inactivo"),
            ("Fecha de creacion", datos.get("fecha_creacion", "") or "—"),
        ]:
            fila = QHBoxLayout()
            lb   = QLabel(f"{etiqueta}:")
            lb.setMinimumWidth(140); lb.setMaximumWidth(180)
            lb.setStyleSheet(
                f"color:{P['txt2']};font-size:12px;background:transparent;"
            )
            vl = QLabel(str(valor))
            vl.setStyleSheet(
                f"color:{P['txt']};font-size:13px;background:transparent;"
            )
            vl.setWordWrap(True)
            fila.addWidget(lb); fila.addWidget(vl, 1)
            lay.addLayout(fila); lay.addSpacing(10)

        lay.addSpacing(16)
        bc = _btn("Cerrar", "sec"); bc.clicked.connect(self.accept)
        lay.addWidget(bc)
        self._fin()


# ══════════════════════════════════════════════════════════════
# DIALOGO CREAR / EDITAR
# ══════════════════════════════════════════════════════════════

class DialogAfiliacion(BaseDialog):
    def __init__(
        self,
        eid:         int,
        afil_id:     int | None = None,
        nombre_ini:  str = "",
        codigo_ini:  str = "",
        parent=None,
    ):
        titulo = "Editar tipo de afiliacion" if afil_id else "Nuevo tipo de afiliacion"
        super().__init__(titulo, 460, parent)
        self._eid = eid; self._afil_id = afil_id
        lay = self.lay

        self.f_nombre = InputF("Nombre *", "Ej: Subsidiado especial...")
        if nombre_ini: self.f_nombre.set(nombre_ini)
        lay.addWidget(self.f_nombre); lay.addSpacing(12)

        self.f_codigo = InputF("Codigo RIPS (opcional)", "Ej: 06  —  Max. 5 caracteres")
        if codigo_ini and codigo_ini not in ("—", ""):
            self.f_codigo.set(codigo_ini)
        lay.addWidget(self.f_codigo); lay.addSpacing(6)

        nota = _lbl(
            "El codigo RIPS se usa en reportes oficiales (Res. 3374/2000). "
            "Dejalo vacio si no aplica. Los codigos 01-05 estan reservados para Ley 100.",
            size=11, color=P["muted"], wrap=True,
        )
        lay.addWidget(nota); lay.addSpacing(18)

        self.sb = StatusBar(); lay.addWidget(self.sb); lay.addSpacing(12)

        row = QHBoxLayout(); row.setSpacing(10)
        bc = _btn("Cancelar", "sec"); bc.clicked.connect(self.reject)
        self.bok = _btn("Guardar"); self.bok.clicked.connect(self._guardar)
        row.addWidget(bc); row.addStretch(); row.addWidget(self.bok)
        lay.addLayout(row)
        self._fin()

    def _guardar(self):
        self.sb.ocultar(); self.f_nombre.ok(); self.f_codigo.ok()
        nombre = self.f_nombre.text()
        codigo = self.f_codigo.text()

        if not nombre:
            self.f_nombre.err("El nombre es obligatorio."); return
        if len(nombre) > 80:
            self.f_nombre.err("Maximo 80 caracteres."); return
        if codigo and len(codigo) > 5:
            self.f_codigo.err("El codigo no puede superar 5 caracteres."); return

        self.bok.setEnabled(False); self.bok.setText("Guardando...")

        def _done(res: afil_bk.Resultado):
            self.bok.setEnabled(True); self.bok.setText("Guardar")
            if res.ok:
                self.sb.ok(res.mensaje)
                QTimer.singleShot(500, self.accept)
            else:
                self.sb.err(res.mensaje)

        if self._afil_id:
            _run_async(self, afil_bk.actualizar_afiliacion,
                       self._eid, self._afil_id, nombre, codigo, on_done=_done)
        else:
            _run_async(self, afil_bk.crear_afiliacion,
                       self._eid, nombre, codigo, on_done=_done)


# ══════════════════════════════════════════════════════════════
# TAB PRINCIPAL — responsivo + menu unificado
# ══════════════════════════════════════════════════════════════

class TabAfiliacion(QWidget):
    """
    Widget principal del modulo 5.2.

    Menu de acciones:
      - Icono al final de cada fila → click izquierdo → menu desplegable
      - Click derecho sobre cualquier celda de la fila → mismo menu
    """

    def __init__(self, entidad_id: int, parent=None):
        super().__init__(parent)
        self._eid  = entidad_id
        self._modo = None
        # Cache de datos para el menu contextual por fila
        self._cache: list[dict] = []

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._aplicar_resize)

        self._construir_ui()
        self._cargar()

    # ── Construccion ──────────────────────────────────────────

    def _construir_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16,16,16,16); root.setSpacing(10)

        # Cabecera
        hdr = QWidget(); hdr.setStyleSheet("background:transparent;")
        hl  = QHBoxLayout(hdr); hl.setContentsMargins(0,0,0,0); hl.setSpacing(0)
        hl.addWidget(_lbl("Tipos de afiliacion", size=15, bold=True))
        hl.addStretch()
        self._cnt = _lbl("", size=11, color=P["muted"])
        hl.addWidget(self._cnt)
        root.addWidget(hdr); root.addWidget(_sep())

        # Barra de acciones
        barra = QWidget(); barra.setStyleSheet("background:transparent;")
        bl = QVBoxLayout(barra); bl.setContentsMargins(0,8,0,0); bl.setSpacing(8)

        # Fila 1: busqueda
        fila1 = QWidget(); fila1.setStyleSheet("background:transparent;")
        fl1 = QHBoxLayout(fila1); fl1.setContentsMargins(0,0,0,0); fl1.setSpacing(8)

        self.bus = QLineEdit()
        self.bus.setPlaceholderText("Buscar por nombre o codigo RIPS...")
        self.bus.setMinimumHeight(38)
        self.bus.setStyleSheet(_CSS_LINE)

        # Busqueda en tiempo real con debounce 300 ms
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(lambda: self._cargar(self.bus.text()))
        self.bus.textChanged.connect(lambda _: self._debounce.start(300))

        fl1.addWidget(self.bus, 1)

        # Fila 2: boton nuevo
        fila2 = QWidget(); fila2.setStyleSheet("background:transparent;")
        fl2 = QHBoxLayout(fila2); fl2.setContentsMargins(0,0,0,0); fl2.setSpacing(8)
        self.btn_nuevo = _btn("+ Nuevo tipo")
        self.btn_nuevo.clicked.connect(self._nuevo)
        fl2.addWidget(self.btn_nuevo); fl2.addStretch()

        bl.addWidget(fila1); bl.addWidget(fila2)
        root.addWidget(barra)

        # Tabla
        self.tabla = _make_table(["ID", "Nombre", "Cod. RIPS", "Tipo", "Estado", "Acciones"])
        # Click derecho en la tabla → menu contextual de la fila
        self.tabla.customContextMenuRequested.connect(self._ctx_menu_fila)
        root.addWidget(self.tabla, 1)

    # ── Responsivo ────────────────────────────────────────────

    def resizeEvent(self, e: QResizeEvent):
        super().resizeEvent(e)
        self._resize_timer.start(40)

    def _aplicar_resize(self):
        w = self.width()
        nuevo = (
            "compacto"   if w < BP_COMPACT else
            "tablet"     if w < BP_TABLET  else
            "escritorio"
        )
        if nuevo != self._modo:
            self._modo = nuevo
            self._actualizar_cols(nuevo)
        self._ajustar_anchos(w)

    def _actualizar_cols(self, modo: str):
        hdr    = self.tabla.horizontalHeader()
        ocultas = (
            {_CI, _CC, _CT} if modo == "compacto" else
            {_CI}           if modo == "tablet"   else
            set()
        )
        for c in range(self.tabla.columnCount()):
            hdr.setSectionHidden(c, c in ocultas)

        self.btn_nuevo.setSizePolicy(
            QSizePolicy.Policy.Expanding if modo == "compacto" else QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

    def _ajustar_anchos(self, w: int):
        hdr = self.tabla.horizontalHeader()
        hdr.setSectionResizeMode(_CN, QHeaderView.ResizeMode.Stretch)
        if self._modo == "compacto":
            self.tabla.setColumnWidth(_CE, 95)
            self.tabla.setColumnWidth(_CA, 52)
        elif self._modo == "tablet":
            self.tabla.setColumnWidth(_CC, 85)
            self.tabla.setColumnWidth(_CT, 120)
            self.tabla.setColumnWidth(_CE, 95)
            self.tabla.setColumnWidth(_CA, 52)
        else:
            self.tabla.setColumnWidth(_CI, 50)
            self.tabla.setColumnWidth(_CC, 85)
            self.tabla.setColumnWidth(_CT, 130)
            self.tabla.setColumnWidth(_CE, 95)
            self.tabla.setColumnWidth(_CA, 52)

    # ── Carga y poblado ───────────────────────────────────────

    def _cargar(self, filtro: str = ""):
        filtro = filtro if isinstance(filtro, str) else ""
        _run_async(self, afil_bk.listar_afiliaciones, self._eid, filtro,
                   on_done=self._poblar)

    def _poblar(self, datos):
        if not isinstance(datos, list): datos = []
        self._cache = datos   # guardar para menu contextual
        self.tabla.setRowCount(0)

        for d in datos:
            r          = self.tabla.rowCount()
            es_oficial = d.get("es_catalogo_oficial", False)
            self.tabla.insertRow(r)
            self.tabla.setItem(r, _CI, _item(d["id"]))
            self.tabla.setItem(r, _CN, _item(d["nombre"]))
            self.tabla.setItem(r, _CC, _item(d.get("codigo") or "—"))
            self.tabla.setCellWidget(r, _CT, _tag_tipo(es_oficial))
            self.tabla.setCellWidget(r, _CE, _tag_estado(d["activo"]))
            self.tabla.setCellWidget(r, _CA, self._celda_acc(r, d))
            self.tabla.setRowHeight(r, 48)

        total  = len(datos)
        sufijo = " (filtrado)" if self.bus.text().strip() else ""
        self._cnt.setText(f"{total} registro{'s' if total!=1 else ''}{sufijo}")

        if self._modo is None:
            QTimer.singleShot(50, self._aplicar_resize)

    # ── Celda de accion (UN solo icono) ───────────────────────

    def _celda_acc(self, fila: int, d: dict) -> QWidget:
        """
        Devuelve un widget con UN unico boton de accion.
        Click izquierdo → despliega el menu.
        """
        w   = QWidget(); w.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(w); lay.setContentsMargins(2,2,2,2)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn = QPushButton("...")
        btn.setFixedSize(36, 32)
        btn.setToolTip("Acciones (clic izquierdo o derecho)")
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setStyleSheet(
            f"QPushButton{{background:{P['acc_lt']};color:{P['acc_h']};"
            f"border:1.5px solid {P['focus']};border-radius:7px;"
            f"font-size:15px;font-weight:900;letter-spacing:1px;}}"
            f"QPushButton:hover{{background:{P['focus']};color:{P['white']};"
            f"border-color:{P['acc_h']};}}"
            f"QPushButton:pressed{{background:{P['accent']};}}"
        )

        # Click izquierdo → mismo menu que click derecho
        btn.clicked.connect(lambda _checked, b=btn, dato=d:
            self._mostrar_menu(dato, widget=b))

        lay.addWidget(btn)
        return w

    # ── Menu contextual ───────────────────────────────────────

    def _ctx_menu_fila(self, pos: QPoint):
        """Click derecho sobre la tabla → mismo menu que el boton."""
        idx = self.tabla.indexAt(pos)
        if not idx.isValid(): return
        fila = idx.row()
        if fila < 0 or fila >= len(self._cache): return
        d = self._cache[fila]
        pos_global = self.tabla.viewport().mapToGlobal(pos)
        self._mostrar_menu(d, pos=pos_global)

    def _mostrar_menu(
        self, d: dict,
        widget: QWidget | None = None,
        pos:    QPoint  | None = None,
    ):
        """Construye y muestra el menu de acciones para el registro d."""
        aid        = d["id"]
        nombre     = d["nombre"]
        codigo     = d.get("codigo", "")
        activo     = d["activo"]
        es_oficial = d.get("es_catalogo_oficial", False)

        menu = _build_menu(
            es_oficial  = es_oficial,
            activo      = activo,
            on_ver      = lambda: self._ver(aid),
            on_editar   = lambda: self._editar(aid, nombre, codigo),
            on_estado   = lambda: self._estado(aid, not activo),
            on_eliminar = lambda: self._eliminar(aid, nombre),
        )
        _popup(menu, widget=widget, pos=pos)

    # ── Acciones ──────────────────────────────────────────────

    def _ver(self, aid: int):
        datos = afil_bk.obtener_afiliacion(int(aid))
        if not datos:
            QMessageBox.warning(self, "No encontrado",
                                "No se encontro el tipo de afiliacion.")
            return
        DialogAfiliacionVer(datos, self).exec()

    def _nuevo(self):
        if DialogAfiliacion(self._eid, parent=self).exec():
            self._cargar(self.bus.text())

    def _editar(self, aid: int, nombre: str, codigo: str):
        if DialogAfiliacion(
            self._eid, afil_id=int(aid),
            nombre_ini=nombre, codigo_ini=codigo,
            parent=self,
        ).exec():
            self._cargar(self.bus.text())

    def _estado(self, aid: int, activo: bool):
        accion = "activar" if activo else "desactivar"
        if QMessageBox.question(
            self, "Confirmar",
            f"¿Deseas {accion} este tipo de afiliacion?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        def _done(res: afil_bk.Resultado):
            if res.ok: QMessageBox.information(self, "Resultado", res.mensaje)
            else:      QMessageBox.warning(self, "Error", res.mensaje)
            self._cargar(self.bus.text())

        _run_async(self, afil_bk.cambiar_estado_afiliacion,
                   self._eid, int(aid), activo, on_done=_done)

    def _eliminar(self, aid: int, nombre: str):
        resp = QMessageBox.question(
            self,
            "Confirmar eliminacion",
            f"¿Eliminar '{nombre}' permanentemente?\n\n"
            "Esta accion no se puede deshacer. Si el tipo tiene\n"
            "pacientes o eventos vinculados, se bloqueara automaticamente.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        def _done(res: afil_bk.Resultado):
            if res.ok: QMessageBox.information(self, "Eliminado", res.mensaje)
            else:      QMessageBox.warning(self, "No se pudo eliminar", res.mensaje)
            self._cargar(self.bus.text())

        _run_async(self, afil_bk.eliminar_afiliacion,
                   self._eid, int(aid), on_done=_done)


# ══════════════════════════════════════════════════════════════
# DIALOGO SELECTOR DE ENTIDAD (solo modo standalone / desarrollo)
# ══════════════════════════════════════════════════════════════

class _DialogSelectorEntidad(QDialog):
    """
    Aparece SOLO en modo standalone (python gestion_afiliacion_ui.py).
    En produccion (.exe / main) esta ventana NUNCA se muestra.
    """
    def __init__(self, entidades: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar entidad — Modo desarrollo")
        self.setModal(True); self.setFixedWidth(460)
        self.setStyleSheet(f"QDialog{{background:{P['bg']};}}" + _CSS_BASE)
        self.entidad_id: int | None = None

        lay = QVBoxLayout(self); lay.setContentsMargins(24,20,24,20); lay.setSpacing(12)

        t = QLabel("Modo desarrollo — Seleccionar entidad")
        t.setStyleSheet(f"color:{P['txt']};font-size:16px;font-weight:700;background:transparent;")
        lay.addWidget(t)

        av = QLabel(
            "Este selector solo aparece al ejecutar el modulo directamente. "
            "En produccion el entidad_id viene de la sesion autenticada."
        )
        av.setWordWrap(True)
        av.setStyleSheet(
            f"background:rgba(210,153,34,.12);border:1px solid {P['warn']};"
            f"border-radius:7px;color:{P['warn']};padding:10px 12px;font-size:11px;"
        )
        lay.addWidget(av)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"border:none;border-top:1px solid {P['border']};background:transparent;")
        sep.setFixedHeight(1); lay.addWidget(sep)

        lbl_e = QLabel("IPS / Entidad:")
        lbl_e.setStyleSheet(f"color:{P['txt2']};font-size:12px;background:transparent;")
        lay.addWidget(lbl_e)

        self._combo = QComboBox()
        self._combo.setStyleSheet(
            f"QComboBox{{background:{P['input']};border:1.5px solid {P['border']};"
            f"border-radius:7px;padding:8px 12px;color:{P['txt']};font-size:13px;"
            f"min-height:40px;}}"
            f"QComboBox:focus{{border-color:{P['focus']};}}"
            f"QComboBox QAbstractItemView{{background:{P['card']};color:{P['txt']};"
            f"border:1px solid {P['border']};selection-background-color:{P['acc_lt']};}}"
        )
        for e in entidades:
            self._combo.addItem(
                f"[{e['id']}] {e['nombre_entidad']}  —  NIT {e['nit']}",
                e["id"]
            )
        lay.addWidget(self._combo); lay.addSpacing(8)

        row = QHBoxLayout(); row.setSpacing(10)
        bc = QPushButton("Cancelar"); bc.setStyleSheet(
            f"QPushButton{{background:transparent;color:{P['txt2']};"
            f"border:1.5px solid {P['border']};border-radius:7px;padding:8px 18px;}}"
            f"QPushButton:hover{{border-color:{P['focus']};color:{P['txt']};}}"
        )
        bc.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        bc.clicked.connect(self.reject)
        bo = QPushButton("Continuar"); bo.setStyleSheet(
            f"QPushButton{{background:{P['accent']};color:white;border:none;"
            f"border-radius:7px;padding:9px 18px;font-weight:600;}}"
            f"QPushButton:hover{{background:{P['acc_h']};}}"
        )
        bo.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        bo.clicked.connect(self._aceptar)
        row.addWidget(bc); row.addStretch(); row.addWidget(bo)
        lay.addLayout(row)

    def _aceptar(self):
        self.entidad_id = self._combo.currentData(); self.accept()


# ══════════════════════════════════════════════════════════════
# SESION GLOBAL
# ══════════════════════════════════════════════════════════════

class _Sesion:
    """
    Modo standalone  → entidad_id se resuelve desde _DialogSelectorEntidad.
    Modo produccion  → llamar sesion.set(...) antes de instanciar AfiliacionWindow.

    Uso desde el sistema principal:
        from gestion_afiliacion_ui import sesion
        sesion.set(entidad_id=5, rol="admin", ops_id=42, nombre="Juan")
        win = AfiliacionWindow()
        win.show()
    """
    def __init__(self):
        self.entidad_id: int | None = None
        self.ops_id:     int | None = None
        self.rol:        str        = "admin"
        self.nombre:     str        = ""
        self._inyectada: bool       = False

    def set(self, entidad_id: int, rol: str = "admin",
            ops_id=None, nombre: str = ""):
        self.entidad_id = entidad_id
        self.rol        = rol
        self.ops_id     = int(ops_id) if ops_id and str(ops_id).strip() not in ("","0") else None
        self.nombre     = nombre
        self._inyectada = True

    @property
    def es_standalone(self) -> bool:
        return not self._inyectada


sesion = _Sesion()


# ══════════════════════════════════════════════════════════════
# VENTANA PRINCIPAL
# ══════════════════════════════════════════════════════════════

class AfiliacionWindow(QMainWindow):
    """
    Modo standalone  → muestra selector de entidad real de la BD.
    Modo produccion  → usa sesion.entidad_id (inyectado por el sistema).
    """
    def __init__(self, entidad_id: int | None = None, rol: str | None = None,
                 ops_id=None, nombre_usuario: str = ""):
        super().__init__()
        self.setWindowTitle("Tipos de afiliacion — Gestion Eventos Salud")
        self.setStyleSheet(_CSS_BASE); self.setMinimumSize(360, 400)

        # Resolver sesion
        if entidad_id is not None:
            self._eid = entidad_id; self._rol = rol or "admin"
        elif sesion.entidad_id is not None:
            self._eid = sesion.entidad_id; self._rol = sesion.rol
        else:
            self._eid = None; self._rol = "admin"

        self._nombre = nombre_usuario or sesion.nombre

        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            w = max(380, min(int(geo.width()  * 0.70), geo.width()))
            h = max(480, min(int(geo.height() * 0.75), geo.height()))
            self.resize(w, h)
            self.move(geo.x()+(geo.width()-w)//2, geo.y()+(geo.height()-h)//2)
        else:
            self.resize(960, 620)

        central = QWidget(); central.setStyleSheet(f"background:{P['bg']};")
        self.setCentralWidget(central)
        self._root = QVBoxLayout(central); self._root.setContentsMargins(0,0,0,0); self._root.setSpacing(0)

        # Topbar
        topbar = QWidget(); topbar.setFixedHeight(52)
        topbar.setStyleSheet(f"background:{P['card']};border-bottom:1px solid {P['border']};")
        tl = QHBoxLayout(topbar); tl.setContentsMargins(20,0,20,0); tl.setSpacing(8)
        tl.addWidget(_lbl("Gestion", size=12, color=P["txt2"]))
        tl.addWidget(_lbl(" / ", size=12, color=P["muted"]))
        tl.addWidget(_lbl("Tipos de afiliacion", size=14, bold=True))
        tl.addStretch()
        self._lbl_top = _lbl("", size=11, color=P["muted"])
        tl.addWidget(self._lbl_top)
        self._root.addWidget(topbar)

        ayuda = QWidget()
        ayuda.setStyleSheet(f"background:rgba(56,139,253,.08);border-bottom:1px solid {P['border']};")
        al = QHBoxLayout(ayuda); al.setContentsMargins(20,6,20,6)
        al.addWidget(_lbl("Tip: clic '...' o clic derecho en la fila para ver acciones.", size=11, color=P["txt2"]))
        self._root.addWidget(ayuda)

        self._placeholder = QLabel("Cargando...")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(f"color:{P['muted']};font-size:14px;background:transparent;")
        self._root.addWidget(self._placeholder, 1)

        QTimer.singleShot(50, self._resolver_entidad)

    def _resolver_entidad(self):
        if self._eid is not None:
            self._construir_tab(); return

        entidades = afil_bk.listar_entidades_disponibles()
        if not entidades:
            self._placeholder.setText(
                "No hay entidades registradas en la base de datos.\n"
                "Crea una entidad (IPS) primero."
            )
            self._placeholder.setStyleSheet(
                f"color:{P['err']};font-size:13px;background:transparent;padding:20px;"
            )
            return

        if len(entidades) == 1:
            self._eid = entidades[0]["id"]; self._construir_tab(); return

        dlg = _DialogSelectorEntidad(entidades, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.entidad_id is None:
            self.close(); return
        self._eid = dlg.entidad_id; self._construir_tab()

    def _construir_tab(self):
        self._placeholder.hide(); self._root.removeWidget(self._placeholder)
        self._tab = TabAfiliacion(self._eid, self)
        self._root.addWidget(self._tab, 1)
        modo = "DEV" if sesion.es_standalone and sesion.entidad_id is None else self._rol.upper()
        txt = f"Entidad #{self._eid}  |  {modo}"
        if self._nombre: txt += f"  |  {self._nombre}"
        self._lbl_top.setText(txt)


# ══════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════

def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    font = QFont("Segoe UI", 10)
    font.setHintingPreference(QFont.HintingPreference.PreferDefaultHinting)
    app.setFont(font)

    win = AfiliacionWindow()  # entidad_id=None → modo standalone → selector automatico
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()