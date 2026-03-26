# -*- coding: utf-8 -*-
"""
gestion_eps_ops_ui.py
======================
Seccion 5.4 — Gestion de EPS para Usuarios OPS.

Diferencias respecto a gestion_eps_ui.py (Admin):
  - SIN botones de carga masiva ni descarga de plantilla.
  - Solo creacion individual de EPS.
  - Menu de acciones: Ver | Editar | Activar/Desactivar | Eliminar
    pero Editar, Desactivar y Eliminar solo estan habilitados si
    el OPS fue quien registro esa EPS (creado_por_ops = ops_id actual).
  - El registro queda vinculado al ops_id en creado_por_ops.

Modos de operacion:
  Standalone  (python gestion_eps_ops_ui.py):
      Muestra selector de entidad real desde la BD.
  Produccion  (.exe / GestionWindow):
      Usa sesion.set(entidad_id, rol, ops_id, nombre).

Responsivo — 3 modos:
  < 560px   Compacto:   Nombre | Estado | Acciones
  560-960px Tablet:     Codigo | Nombre | NIT | Estado | Acciones
  > 960px   Escritorio: Codigo | Nombre | NIT | Municipio | Tipo | Estado | Contrato | Acciones

Menu (click izquierdo '...' o click derecho en la fila):
  Ver detalle | Editar * | Activar/Desactivar * | Eliminar *
  (* solo disponible si el OPS es el creador de esa EPS)
"""
from __future__ import annotations

import sys
import io
from functools import partial

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem,
    QFrame, QSizePolicy, QScrollArea,
    QAbstractItemView, QMessageBox, QMenu,
    QHeaderView,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer, QPoint
from PySide6.QtGui import QCursor, QFont, QResizeEvent

import gestion_eps_ops_backend as bk


# ══════════════════════════════════════════════════════════════
# PALETA Y ESTILOS (identica al resto del sistema)
# ══════════════════════════════════════════════════════════════

P = {
    "bg":      "#0D1117", "card":    "#161B22", "input":   "#21262D",
    "border":  "#30363D", "focus":   "#388BFD", "accent":  "#2D6ADF",
    "acc_h":   "#388BFD", "acc_lt":  "#1C3A6E",
    "ok":      "#3FB950", "err":     "#F85149", "warn":    "#D29922",
    "txt":     "#E6EDF3", "txt2":    "#8B949E", "muted":   "#484F58",
    "white":   "#FFFFFF", "row_alt": "#0F1419", "row_sel": "#1C3A6E",
    "contrato":"#3FB950", "sin_cont":"#D29922",
}

BP_COMPACT = 560
BP_TABLET  = 960

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
QComboBox {{
    background:{P['input']}; border:1.5px solid {P['border']};
    border-radius:7px; padding:7px 12px; color:{P['txt']};
    font-size:13px; min-height:38px;
}}
QComboBox:focus {{ border-color:{P['focus']}; }}
QComboBox::drop-down {{ border:none; width:24px; }}
QComboBox QAbstractItemView {{
    background:{P['card']}; color:{P['txt']};
    border:1px solid {P['border']}; border-radius:6px;
    selection-background-color:{P['acc_lt']};
}}
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
_CC, _CN, _CNIT, _CM, _CT, _CE, _CCON, _CA = 0, 1, 2, 3, 4, 5, 6, 7


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
            self.done.emit(bk.Resultado(False, str(e)))

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
    f.setStyleSheet(f"border:none;border-top:1px solid {P['border']};background:transparent;")
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
    }
    b.setStyleSheet(S.get(style, S["prim"]))
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    return b

def _item(txt, align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft):
    i = QTableWidgetItem(str(txt) if txt is not None else "")
    i.setFlags(i.flags() & ~Qt.ItemFlag.ItemIsEditable)
    i.setTextAlignment(align)
    return i

def _pill(texto, color, rgb):
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
    return _pill("Activa" if activo else "Inactiva",
                 P["ok"] if activo else P["err"],
                 "63,185,80" if activo else "248,81,73")

def _tag_contrato(tiene: bool) -> QWidget:
    return _pill("Con contrato" if tiene else "Sin contrato",
                 P["contrato"] if tiene else P["sin_cont"],
                 "63,185,80" if tiene else "210,153,34")

def _tag_propietario(es_mio: bool) -> QWidget:
    """
    Pequena insignia que indica si el OPS actual es quien creo esta EPS.
    Ayuda visual para saber cuales puede editar/eliminar.
    """
    return _pill("Registrada por mi" if es_mio else "Otro registro",
                 P["focus"] if es_mio else P["muted"],
                 "56,139,253" if es_mio else "72,79,88")

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
    t.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    return t

def _btn_accion():
    b = QPushButton("...")
    b.setFixedSize(36, 32)
    b.setToolTip("Acciones")
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    b.setStyleSheet(
        f"QPushButton{{background:{P['acc_lt']};color:{P['acc_h']};"
        f"border:1.5px solid {P['focus']};border-radius:7px;"
        f"font-size:15px;font-weight:900;letter-spacing:1px;}}"
        f"QPushButton:hover{{background:{P['focus']};color:{P['white']};}}"
        f"QPushButton:pressed{{background:{P['accent']};}}"
    )
    return b

def _make_menu():
    m = QMenu()
    m.setStyleSheet(
        f"QMenu{{background:{P['card']};color:{P['txt']};"
        f"border:1.5px solid {P['border']};border-radius:10px;"
        f"padding:6px 0;font-size:13px;}}"
        f"QMenu::item{{padding:10px 22px 10px 16px;border-radius:5px;margin:1px 6px;}}"
        f"QMenu::item:selected{{background:{P['acc_lt']};color:{P['acc_h']};}}"
        f"QMenu::item:disabled{{color:{P['muted']};}}"
        f"QMenu::separator{{background:{P['border']};height:1px;margin:5px 10px;}}"
    )
    return m


# ══════════════════════════════════════════════════════════════
# WIDGETS REUTILIZABLES
# ══════════════════════════════════════════════════════════════

class StatusBar(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter); self.hide()
    def _show(self, msg, css): self.setStyleSheet(css); self.setText(msg); self.show()
    def ok(self, m):
        self._show(m, f"background:rgba(63,185,80,.15);border:1px solid {P['ok']};"
                      f"border-radius:7px;color:{P['ok']};padding:9px 14px;font-size:12px;")
    def err(self, m):
        self._show(m, f"background:rgba(248,81,73,.15);border:1px solid {P['err']};"
                      f"border-radius:7px;color:{P['err']};padding:9px 14px;font-size:12px;")
    def warn(self, m):
        self._show(m, f"background:rgba(210,153,34,.15);border:1px solid {P['warn']};"
                      f"border-radius:7px;color:{P['warn']};padding:9px 14px;font-size:12px;")
    def ocultar(self): self.hide()


class InputF(QWidget):
    def __init__(self, label: str, ph: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QWidget{{background:{P['bg']};border:none;}}")
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(4)
        if label:
            lb = QLabel(label)
            lb.setStyleSheet(f"color:{P['txt2']};font-size:12px;background:transparent;")
            lay.addWidget(lb)
        self.inp = QLineEdit(); self.inp.setPlaceholderText(ph)
        self.inp.setMinimumHeight(38); self.inp.setStyleSheet(_CSS_LINE)
        self._e = QLabel("")
        self._e.setStyleSheet(f"color:{P['err']};font-size:11px;background:transparent;")
        self._e.hide()
        lay.addWidget(self.inp); lay.addWidget(self._e)
    def text(self) -> str:  return self.inp.text().strip()
    def set(self, v):       self.inp.setText(str(v) if v else "")
    def clear(self):        self.inp.clear()
    def setEnabled(self, v): self.inp.setEnabled(v)
    def err(self, m):
        self._e.setText(m); self._e.show()
        self.inp.setStyleSheet(_CSS_LINE + f"QLineEdit{{border-color:{P['err']};}}")
    def ok(self):
        self._e.hide(); self.inp.setStyleSheet(_CSS_LINE)


class ComboF(QWidget):
    def __init__(self, label: str, opciones: list[str], parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QWidget{{background:{P['bg']};border:none;}}")
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(4)
        if label:
            lb = QLabel(label)
            lb.setStyleSheet(f"color:{P['txt2']};font-size:12px;background:transparent;")
            lay.addWidget(lb)
        self.cb = QComboBox()
        for op in opciones: self.cb.addItem(op)
        lay.addWidget(self.cb)
    def text(self) -> str: return self.cb.currentText()
    def set(self, v: str):
        idx = self.cb.findText(str(v) if v else "", Qt.MatchFlag.MatchFixedString)
        if idx >= 0: self.cb.setCurrentIndex(idx)


# ══════════════════════════════════════════════════════════════
# BASE DIALOG RESPONSIVO
# ══════════════════════════════════════════════════════════════

class BaseDialog(QDialog):
    def __init__(self, titulo: str, ancho_ref: int = 560, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo); self.setModal(True)
        self.setStyleSheet(f"QDialog{{background:{P['bg']};}}" + _CSS_BASE)
        sc = QApplication.primaryScreen()
        if sc:
            geo = sc.availableGeometry()
            self._mw = int(geo.width() * .95); self._mh = int(geo.height() * .92)
        else:
            self._mw, self._mh = 1000, 800
        ancho = min(ancho_ref, self._mw)
        self.setMinimumWidth(min(320, ancho)); self.setMaximumWidth(self._mw)
        self.setMaximumHeight(self._mh)
        outer = QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
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
        self.lay = QVBoxLayout(inner); self.lay.setContentsMargins(24,20,24,20); self.lay.setSpacing(0)
        t = QLabel(titulo)
        t.setStyleSheet(f"color:{P['txt']};font-size:17px;font-weight:700;background:transparent;")
        self.lay.addWidget(t); self.lay.addSpacing(8); self.lay.addWidget(_sep()); self.lay.addSpacing(16)
        scroll.setWidget(inner); outer.addWidget(scroll)
        self.resize(ancho, min(500, self._mh))

    def _fin(self):
        QTimer.singleShot(0, self._sz)
    def _sz(self):
        self.adjustSize()
        w = min(self.width(), self._mw); h = max(min(self.height(), self._mh), 220)
        self.resize(w, h)
        sc = QApplication.primaryScreen()
        if sc:
            g = sc.availableGeometry()
            self.move(g.x()+(g.width()-w)//2, g.y()+(g.height()-h)//2)


# ══════════════════════════════════════════════════════════════
# DIALOGO VER (solo lectura)
# ══════════════════════════════════════════════════════════════

class DialogEpsOpsVer(BaseDialog):
    def __init__(self, d: dict, ops_id: int | None, parent=None):
        super().__init__("Detalle EPS / Aseguradora", 500, parent)
        lay = self.lay

        # Encabezado con nombre y contrato
        enc = QWidget(); enc.setStyleSheet(f"background:{P['card']};border-radius:8px;")
        el = QHBoxLayout(enc); el.setContentsMargins(16,12,16,12)
        el.addWidget(_lbl(d.get("nombre","—"), size=15, bold=True))
        el.addStretch()
        el.addWidget(_tag_contrato(d.get("tiene_contrato", False)))
        lay.addWidget(enc); lay.addSpacing(16)

        # Insignia de propietario
        creado_por = d.get("creado_por_ops")
        es_mio = (creado_por is not None and ops_id is not None
                  and int(creado_por) == int(ops_id))
        fila_prop = QHBoxLayout()
        fila_prop.addWidget(_tag_propietario(es_mio)); fila_prop.addStretch()
        lay.addLayout(fila_prop); lay.addSpacing(10)

        for etiqueta, valor in [
            ("Codigo MSPS",    d.get("codigo","")          or "—"),
            ("Tipo",           d.get("tipo","")             or "—"),
            ("NIT",            f"{d.get('nit','')} - {d.get('dv','')}".strip(" -") or "—"),
            ("Departamento",   d.get("departamento","")     or "—"),
            ("Municipio",      d.get("municipio","")        or "—"),
            ("Correo",         d.get("correo","")           or "—"),
            ("Telefono",       d.get("telefono","")         or "—"),
            ("Direccion",      d.get("direccion","")        or "—"),
            ("Digitado por",   d.get("digitado_por","")     or "—"),
            ("Estado",         "Activa" if d.get("activo") else "Inactiva"),
            ("Creado",         d.get("fecha_creacion","")   or "—"),
            ("Actualizado",    d.get("ultima_actualizacion","") or "—"),
        ]:
            fila = QHBoxLayout()
            lb = QLabel(f"{etiqueta}:")
            lb.setMinimumWidth(120); lb.setMaximumWidth(160)
            lb.setStyleSheet(f"color:{P['txt2']};font-size:12px;background:transparent;")
            vl = QLabel(str(valor)); vl.setWordWrap(True)
            vl.setStyleSheet(f"color:{P['txt']};font-size:13px;background:transparent;")
            fila.addWidget(lb); fila.addWidget(vl, 1)
            lay.addLayout(fila); lay.addSpacing(8)

        lay.addSpacing(16)
        bc = _btn("Cerrar", "sec"); bc.clicked.connect(self.accept); lay.addWidget(bc)
        self._fin()


# ══════════════════════════════════════════════════════════════
# DIALOGO CREAR / EDITAR (solo individual, sin carga masiva)
# ══════════════════════════════════════════════════════════════

_TIPOS_EPS = ["EPS", "IPS", "ARL", "Aseguradora", "Regimen Especial", "Otro"]

class DialogEpsOps(BaseDialog):
    """
    Formulario para crear o editar UNA EPS de forma individual.
    ops_id es obligatorio — queda registrado en creado_por_ops.
    """
    def __init__(self, eid: int, ops_id: int, datos_ini: dict | None = None,
                 parent=None):
        titulo = "Editar EPS / Aseguradora" if datos_ini else "Nueva EPS / Aseguradora"
        super().__init__(titulo, 620, parent)
        self._eid    = eid
        self._oid    = int(ops_id)
        self._eps_id = datos_ini.get("eps_id") if datos_ini else None
        lay = self.lay

        # Grid 2 columnas
        g = QWidget(); g.setStyleSheet(f"background:{P['bg']};border:none;")
        gl = QGridLayout(g); gl.setContentsMargins(0,0,0,0); gl.setSpacing(12)

        self.f_nombre   = InputF("Nombre *",         "Nombre completo de la entidad")
        self.f_codigo   = InputF("Codigo MSPS/SNS",  "Ej: EPS001")
        self.f_tipo     = ComboF("Tipo",              _TIPOS_EPS)
        self.f_nit      = InputF("NIT",              "Solo numeros")
        self.f_dv       = InputF("DV",               "1 digito")
        self.f_dpto     = InputF("Departamento",     "")
        self.f_mpio     = InputF("Municipio",        "")
        self.f_correo   = InputF("Correo",           "correo@entidad.com")
        self.f_tel      = InputF("Telefono",         "")
        self.f_dir      = InputF("Direccion",        "")
        self.f_digitado = InputF("Digitado por",     "")

        gl.addWidget(self.f_nombre,   0, 0, 1, 2)
        gl.addWidget(self.f_codigo,   1, 0)
        gl.addWidget(self.f_tipo,     1, 1)
        gl.addWidget(self.f_nit,      2, 0)
        gl.addWidget(self.f_dv,       2, 1)
        gl.addWidget(self.f_dpto,     3, 0)
        gl.addWidget(self.f_mpio,     3, 1)
        gl.addWidget(self.f_correo,   4, 0)
        gl.addWidget(self.f_tel,      4, 1)
        gl.addWidget(self.f_dir,      5, 0, 1, 2)
        gl.addWidget(self.f_digitado, 6, 0, 1, 2)

        lay.addWidget(g); lay.addSpacing(18)
        self.sb = StatusBar(); lay.addWidget(self.sb); lay.addSpacing(12)

        row = QHBoxLayout(); row.setSpacing(10)
        bc = _btn("Cancelar", "sec"); bc.clicked.connect(self.reject)
        self.bok = _btn("Guardar"); self.bok.clicked.connect(self._guardar)
        row.addWidget(bc); row.addStretch(); row.addWidget(self.bok)
        lay.addLayout(row)

        if datos_ini:
            self.f_nombre.set(datos_ini.get("nombre",""))
            self.f_codigo.set(datos_ini.get("codigo",""))
            self.f_tipo.set(datos_ini.get("tipo","EPS"))
            self.f_nit.set(datos_ini.get("nit",""))
            self.f_dv.set(datos_ini.get("dv",""))
            self.f_dpto.set(datos_ini.get("departamento",""))
            self.f_mpio.set(datos_ini.get("municipio",""))
            self.f_correo.set(datos_ini.get("correo",""))
            self.f_tel.set(datos_ini.get("telefono",""))
            self.f_dir.set(datos_ini.get("direccion",""))
            self.f_digitado.set(datos_ini.get("digitado_por",""))

        self._fin()

    def _guardar(self):
        self.sb.ocultar(); self.f_nombre.ok()
        if not self.f_nombre.text():
            self.f_nombre.err("El nombre es obligatorio."); return

        datos = {
            "nombre":       self.f_nombre.text(),
            "codigo":       self.f_codigo.text(),
            "tipo":         self.f_tipo.text(),
            "nit":          self.f_nit.text(),
            "dv":           self.f_dv.text(),
            "departamento": self.f_dpto.text(),
            "municipio":    self.f_mpio.text(),
            "correo":       self.f_correo.text(),
            "telefono":     self.f_tel.text(),
            "direccion":    self.f_dir.text(),
            "digitado_por": self.f_digitado.text(),
        }
        self.bok.setEnabled(False); self.bok.setText("Guardando...")

        def _done(res: bk.Resultado):
            self.bok.setEnabled(True); self.bok.setText("Guardar")
            if res.ok: self.sb.ok(res.mensaje); QTimer.singleShot(500, self.accept)
            else:      self.sb.err(res.mensaje)

        _run_async(self, bk.guardar_eps_ops,
                   self._eid, self._oid, datos, self._eps_id, on_done=_done)


# ══════════════════════════════════════════════════════════════
# TAB PRINCIPAL — sin carga masiva, menu con control de propietario
# ══════════════════════════════════════════════════════════════

class TabEpsOps(QWidget):
    """
    Widget principal para OPS.
    - Solo puede crear EPS individualmente.
    - Editar / Desactivar / Eliminar solo disponibles en EPS propias.
    - Ver disponible para todas.
    """
    def __init__(self, entidad_id: int, ops_id: int, parent=None):
        super().__init__(parent)
        self._eid  = entidad_id
        self._oid  = int(ops_id)
        self._modo = None
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
        hl  = QHBoxLayout(hdr); hl.setContentsMargins(0,0,0,0)
        hl.addWidget(_lbl("EPS / Aseguradoras", size=15, bold=True))
        hl.addStretch()
        self._cnt = _lbl("", size=11, color=P["muted"])
        hl.addWidget(self._cnt)
        root.addWidget(hdr); root.addWidget(_sep())

        # Barra: busqueda + boton nueva
        barra = QWidget(); barra.setStyleSheet("background:transparent;")
        bl = QVBoxLayout(barra); bl.setContentsMargins(0,8,0,0); bl.setSpacing(8)

        fila1 = QWidget(); fila1.setStyleSheet("background:transparent;")
        fl1 = QHBoxLayout(fila1); fl1.setContentsMargins(0,0,0,0); fl1.setSpacing(8)
        self.bus = QLineEdit()
        self.bus.setPlaceholderText("Buscar por nombre, codigo, NIT, municipio o tipo...")
        self.bus.setMinimumHeight(38); self.bus.setStyleSheet(_CSS_LINE)
        self._deb = QTimer(self); self._deb.setSingleShot(True)
        self._deb.timeout.connect(lambda: self._cargar(self.bus.text()))
        self.bus.textChanged.connect(lambda _: self._deb.start(300))
        fl1.addWidget(self.bus, 1)

        fila2 = QWidget(); fila2.setStyleSheet("background:transparent;")
        fl2 = QHBoxLayout(fila2); fl2.setContentsMargins(0,0,0,0); fl2.setSpacing(8)
        self.btn_nueva = _btn("+ Nueva EPS")
        self.btn_nueva.clicked.connect(self._nueva)
        fl2.addWidget(self.btn_nueva); fl2.addStretch()

        bl.addWidget(fila1); bl.addWidget(fila2)
        root.addWidget(barra)

        # Tabla — columna extra "Mia" para identificar EPS propias
        self.tabla = _make_table([
            "Codigo", "Nombre", "NIT", "Municipio", "Tipo",
            "Estado", "Contrato", "Acciones"
        ])
        self.tabla.customContextMenuRequested.connect(self._ctx_fila)
        root.addWidget(self.tabla, 1)

        # Leyenda de colores
        leyenda = QWidget(); leyenda.setStyleSheet("background:transparent;")
        ll = QHBoxLayout(leyenda); ll.setContentsMargins(0,4,0,0); ll.setSpacing(12)
        ll.addWidget(_pill("Registrada por mi", P["focus"], "56,139,253"))
        ll.addWidget(_lbl("= puedes editar / desactivar / eliminar", size=11, color=P["muted"]))
        ll.addStretch()
        root.addWidget(leyenda)

    # ── Responsivo ────────────────────────────────────────────

    def resizeEvent(self, e: QResizeEvent):
        super().resizeEvent(e); self._resize_timer.start(40)

    def _aplicar_resize(self):
        w = self.width()
        nuevo = ("compacto" if w < BP_COMPACT else
                 "tablet"   if w < BP_TABLET  else "escritorio")
        if nuevo != self._modo:
            self._modo = nuevo; self._vis_cols(nuevo)
        self._anchos(w)

    def _vis_cols(self, modo: str):
        hdr = self.tabla.horizontalHeader()
        ocultas = (
            {_CC, _CNIT, _CM, _CT, _CCON} if modo == "compacto" else
            {_CM, _CT, _CCON}              if modo == "tablet"   else
            set()
        )
        for c in range(self.tabla.columnCount()):
            hdr.setSectionHidden(c, c in ocultas)
        self.btn_nueva.setSizePolicy(
            QSizePolicy.Policy.Expanding if modo == "compacto"
            else QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

    def _anchos(self, w: int):
        hdr = self.tabla.horizontalHeader()
        hdr.setSectionResizeMode(_CN, QHeaderView.ResizeMode.Stretch)
        if self._modo == "compacto":
            self.tabla.setColumnWidth(_CE, 90); self.tabla.setColumnWidth(_CA, 52)
        elif self._modo == "tablet":
            self.tabla.setColumnWidth(_CC, 90); self.tabla.setColumnWidth(_CNIT, 110)
            self.tabla.setColumnWidth(_CE, 90); self.tabla.setColumnWidth(_CA, 52)
        else:
            self.tabla.setColumnWidth(_CC, 90); self.tabla.setColumnWidth(_CNIT, 120)
            self.tabla.setColumnWidth(_CM, 110); self.tabla.setColumnWidth(_CT, 110)
            self.tabla.setColumnWidth(_CE, 90); self.tabla.setColumnWidth(_CCON, 115)
            self.tabla.setColumnWidth(_CA, 52)

    # ── Carga ─────────────────────────────────────────────────

    def _cargar(self, filtro: str = ""):
        filtro = filtro if isinstance(filtro, str) else ""
        _run_async(self, bk.listar_eps, self._eid, filtro, on_done=self._poblar)

    def _poblar(self, datos):
        if not isinstance(datos, list): datos = []
        self._cache = datos
        self.tabla.setRowCount(0)

        for d in datos:
            r = self.tabla.rowCount(); self.tabla.insertRow(r)
            self.tabla.setItem(r, _CC,   _item(d.get("codigo","")    or "—"))
            self.tabla.setItem(r, _CN,   _item(d.get("nombre","")    or "—"))
            self.tabla.setItem(r, _CNIT, _item(d.get("nit","")       or "—"))
            self.tabla.setItem(r, _CM,   _item(d.get("municipio","") or "—"))
            self.tabla.setItem(r, _CT,   _item(d.get("tipo","")      or "—"))
            self.tabla.setCellWidget(r, _CE,   _tag_estado(d.get("activo", True)))
            self.tabla.setCellWidget(r, _CCON, _tag_contrato(d.get("tiene_contrato", False)))
            self.tabla.setCellWidget(r, _CA,   self._celda_acc(d))
            self.tabla.setRowHeight(r, 48)

        total = len(datos)
        suf = " (filtrado)" if self.bus.text().strip() else ""
        self._cnt.setText(f"{total} EPS{suf}")
        if self._modo is None:
            QTimer.singleShot(50, self._aplicar_resize)

    # ── Celda accion ──────────────────────────────────────────

    def _celda_acc(self, d: dict) -> QWidget:
        w = QWidget(); w.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(w); lay.setContentsMargins(2,2,2,2)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn = _btn_accion()
        btn.clicked.connect(lambda _c, dato=d, b=btn:
            self._menu(dato, widget=b))
        lay.addWidget(btn); return w

    # ── Menu contextual ───────────────────────────────────────

    def _ctx_fila(self, pos: QPoint):
        idx = self.tabla.indexAt(pos)
        if not idx.isValid(): return
        fila = idx.row()
        if fila < 0 or fila >= len(self._cache): return
        self._menu(self._cache[fila],
                   pos=self.tabla.viewport().mapToGlobal(pos))

    def _es_mio(self, d: dict) -> bool:
        """Retorna True si el OPS actual creo esta EPS."""
        creado = d.get("creado_por_ops")
        return (creado is not None and int(creado) == self._oid)

    def _menu(self, d: dict, widget=None, pos: QPoint | None = None):
        eid    = d["eps_id"]
        activo = d.get("activo", True)
        es_mio = self._es_mio(d)

        m = _make_menu()

        # Ver — siempre disponible
        m.addAction("  Ver detalle").triggered.connect(
            lambda: self._ver(eid))

        # Editar — solo si es propietario
        m.addSeparator()
        a_edit = m.addAction("  Editar")
        if es_mio:
            a_edit.triggered.connect(lambda: self._editar(eid))
        else:
            a_edit.setEnabled(False)
            a_edit.setText("  Editar  (no es tu registro)")

        # Activar / Desactivar — solo si es propietario
        m.addSeparator()
        lbl_est = "  Desactivar" if activo else "  Activar"
        a_est = m.addAction(lbl_est)
        if es_mio:
            a_est.triggered.connect(lambda: self._estado(eid, not activo))
        else:
            a_est.setEnabled(False)
            a_est.setText(f"  {lbl_est.strip()}  (no es tu registro)")

        # Eliminar — solo si es propietario
        m.addSeparator()
        a_del = m.addAction("  Eliminar")
        if es_mio:
            a_del.triggered.connect(
                lambda: self._eliminar(eid, d.get("nombre","")))
        else:
            a_del.setEnabled(False)
            a_del.setText("  Eliminar  (no es tu registro)")

        if pos:    m.exec(pos)
        elif widget: m.exec(widget.mapToGlobal(widget.rect().bottomLeft()))
        else:      m.exec(QCursor.pos())

    # ── Acciones ──────────────────────────────────────────────

    def _ver(self, eid: int):
        # Necesitamos creado_por_ops para la insignia — buscamos en cache
        d_cache = next(
            (d for d in self._cache if d.get("eps_id") == eid), None
        )
        d = bk.obtener_eps(self._eid, int(eid))
        if not d: QMessageBox.warning(self, "No encontrada", "EPS no encontrada."); return
        # Pasar creado_por_ops desde cache si no viene en obtener_eps
        if d_cache and "creado_por_ops" not in d:
            d["creado_por_ops"] = d_cache.get("creado_por_ops")
        DialogEpsOpsVer(d, self._oid, self).exec()

    def _nueva(self):
        if DialogEpsOps(self._eid, self._oid, parent=self).exec():
            self._cargar(self.bus.text())

    def _editar(self, eid: int):
        d = bk.obtener_eps(self._eid, int(eid))
        if not d: QMessageBox.warning(self, "No encontrada", "EPS no encontrada."); return
        if DialogEpsOps(self._eid, self._oid, d, parent=self).exec():
            self._cargar(self.bus.text())

    def _estado(self, eid: int, activo: bool):
        accion = "activar" if activo else "desactivar"
        if QMessageBox.question(
            self, "Confirmar", f"¿Deseas {accion} esta EPS?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        def _done(res: bk.Resultado):
            if res.ok: QMessageBox.information(self, "Resultado", res.mensaje)
            else:      QMessageBox.warning(self, "Error", res.mensaje)
            self._cargar(self.bus.text())
        _run_async(self, bk.cambiar_estado_eps_ops,
                   self._eid, self._oid, int(eid), activo, on_done=_done)

    def _eliminar(self, eid: int, nombre: str):
        if QMessageBox.question(
            self, "Confirmar eliminacion",
            f"¿Eliminar '{nombre}' permanentemente?\n\n"
            "Se bloqueara si tiene pacientes, eventos o contratos vinculados.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        def _done(res: bk.Resultado):
            if res.ok: QMessageBox.information(self, "Eliminada", res.mensaje)
            else:      QMessageBox.warning(self, "No se pudo eliminar", res.mensaje)
            self._cargar(self.bus.text())
        _run_async(self, bk.eliminar_eps_ops,
                   self._eid, self._oid, int(eid), on_done=_done)


# ══════════════════════════════════════════════════════════════
# DIALOGO SELECTOR DE ENTIDAD (solo modo standalone)
# ══════════════════════════════════════════════════════════════

class _DialogSelectorEntidad(QDialog):
    """
    Solo aparece al ejecutar el modulo directamente.
    En produccion el entidad_id y ops_id vienen de la sesion.
    """
    def __init__(self, entidades: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar entidad — Modo desarrollo")
        self.setModal(True); self.setFixedWidth(480)
        self.setStyleSheet(f"QDialog{{background:{P['bg']};}}" + _CSS_BASE)
        self.entidad_id: int | None = None
        self.ops_id_sim: int        = 1   # ops_id simulado para pruebas

        lay = QVBoxLayout(self); lay.setContentsMargins(24,20,24,20); lay.setSpacing(12)

        t = QLabel("Modo desarrollo — Seleccionar entidad")
        t.setStyleSheet(
            f"color:{P['txt']};font-size:16px;font-weight:700;background:transparent;"
        )
        lay.addWidget(t)

        av = QLabel(
            "Este selector solo aparece al ejecutar el modulo directamente. "
            "En produccion el entidad_id y ops_id vienen de la sesion autenticada."
        )
        av.setWordWrap(True)
        av.setStyleSheet(
            f"background:rgba(210,153,34,.12);border:1px solid {P['warn']};"
            f"border-radius:7px;color:{P['warn']};padding:10px 12px;font-size:11px;"
        )
        lay.addWidget(av)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(
            f"border:none;border-top:1px solid {P['border']};background:transparent;"
        )
        sep.setFixedHeight(1); lay.addWidget(sep)

        # Selector de entidad
        lbl_e = QLabel("IPS / Entidad:")
        lbl_e.setStyleSheet(f"color:{P['txt2']};font-size:12px;background:transparent;")
        lay.addWidget(lbl_e)
        self._combo_ent = QComboBox()
        self._combo_ent.setStyleSheet(
            f"QComboBox{{background:{P['input']};border:1.5px solid {P['border']};"
            f"border-radius:7px;padding:8px 12px;color:{P['txt']};font-size:13px;"
            f"min-height:40px;}}"
            f"QComboBox:focus{{border-color:{P['focus']};}}"
            f"QComboBox QAbstractItemView{{background:{P['card']};color:{P['txt']};"
            f"border:1px solid {P['border']};selection-background-color:{P['acc_lt']};}}"
        )
        for e in entidades:
            self._combo_ent.addItem(
                f"[{e['id']}] {e['nombre_entidad']}  —  NIT {e['nit']}",
                e["id"]
            )
        lay.addWidget(self._combo_ent)

        # Campo ops_id simulado
        lbl_o = QLabel("OPS ID (simulado para pruebas):")
        lbl_o.setStyleSheet(f"color:{P['txt2']};font-size:12px;background:transparent;")
        lay.addWidget(lbl_o)
        self._ops_input = QLineEdit()
        self._ops_input.setPlaceholderText("ID del usuario OPS, ej: 1")
        self._ops_input.setText("1")
        self._ops_input.setMinimumHeight(38); self._ops_input.setStyleSheet(_CSS_LINE)
        nota_ops = QLabel(
            "Nota: en produccion este ID viene de la sesion autenticada. "
            "Solo las EPS creadas con este ops_id seran editables."
        )
        nota_ops.setWordWrap(True)
        nota_ops.setStyleSheet(
            f"color:{P['muted']};font-size:10px;background:transparent;"
        )
        lay.addWidget(self._ops_input); lay.addWidget(nota_ops); lay.addSpacing(8)

        row = QHBoxLayout(); row.setSpacing(10)
        bc = QPushButton("Cancelar")
        bc.setStyleSheet(
            f"QPushButton{{background:transparent;color:{P['txt2']};"
            f"border:1.5px solid {P['border']};border-radius:7px;padding:8px 18px;}}"
            f"QPushButton:hover{{border-color:{P['focus']};color:{P['txt']};}}"
        )
        bc.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        bc.clicked.connect(self.reject)
        bo = QPushButton("Continuar")
        bo.setStyleSheet(
            f"QPushButton{{background:{P['accent']};color:white;border:none;"
            f"border-radius:7px;padding:9px 18px;font-weight:600;}}"
            f"QPushButton:hover{{background:{P['acc_h']};}}"
        )
        bo.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        bo.clicked.connect(self._aceptar)
        row.addWidget(bc); row.addStretch(); row.addWidget(bo)
        lay.addLayout(row)

    def _aceptar(self):
        self.entidad_id = self._combo_ent.currentData()
        try:
            self.ops_id_sim = int(self._ops_input.text().strip() or "1")
        except ValueError:
            self.ops_id_sim = 1
        self.accept()


# ══════════════════════════════════════════════════════════════
# SESION GLOBAL
# ══════════════════════════════════════════════════════════════

class _Sesion:
    """
    Modo standalone  → se llena desde _DialogSelectorEntidad.
    Modo produccion  → llamar sesion.set(...) antes de EpsOpsWindow.

    Uso desde el sistema principal:
        from gestion_eps_ops_ui import sesion, EpsOpsWindow
        sesion.set(entidad_id=5, ops_id=42, nombre="Maria Lopez")
        win = EpsOpsWindow()
        win.show()
    """
    def __init__(self):
        self.entidad_id: int | None = None
        self.ops_id:     int | None = None
        self.nombre:     str        = ""
        self._inyectada: bool       = False

    def set(self, entidad_id: int, ops_id: int,
            nombre: str = ""):
        self.entidad_id = entidad_id
        self.ops_id     = int(ops_id)
        self.nombre     = nombre
        self._inyectada = True

    @property
    def es_standalone(self) -> bool:
        return not self._inyectada


sesion = _Sesion()


# ══════════════════════════════════════════════════════════════
# VENTANA PRINCIPAL
# ══════════════════════════════════════════════════════════════

class EpsOpsWindow(QMainWindow):
    """
    Ventana principal del modulo EPS para OPS.

    Modo standalone  → muestra selector de entidad + campo ops_id simulado.
    Modo produccion  → usa sesion.entidad_id y sesion.ops_id (ya autenticado).

    Integracion en GestionWindow:
        tab = TabEpsOps(entidad_id=5, ops_id=42, parent=stack)
    """
    def __init__(
        self,
        entidad_id: int | None = None,
        ops_id:     int | None = None,
        nombre_usuario: str    = "",
    ):
        super().__init__()
        self.setWindowTitle("EPS / Aseguradoras — Vista OPS")
        self.setStyleSheet(_CSS_BASE); self.setMinimumSize(400, 480)

        # Resolver sesion
        if entidad_id is not None and ops_id is not None:
            self._eid    = entidad_id
            self._oid    = int(ops_id)
            self._nombre = nombre_usuario
        elif sesion.entidad_id is not None:
            self._eid    = sesion.entidad_id
            self._oid    = sesion.ops_id
            self._nombre = sesion.nombre
        else:
            self._eid    = None
            self._oid    = None
            self._nombre = "Desarrollo OPS"

        sc = QApplication.primaryScreen()
        if sc:
            geo = sc.availableGeometry()
            w = max(480, min(int(geo.width()  * .75), geo.width()))
            h = max(520, min(int(geo.height() * .78), geo.height()))
            self.resize(w, h)
            self.move(geo.x()+(geo.width()-w)//2, geo.y()+(geo.height()-h)//2)
        else:
            self.resize(1100, 680)

        central = QWidget(); central.setStyleSheet(f"background:{P['bg']};")
        self.setCentralWidget(central)
        self._root = QVBoxLayout(central)
        self._root.setContentsMargins(0,0,0,0); self._root.setSpacing(0)

        # Topbar
        topbar = QWidget(); topbar.setFixedHeight(52)
        topbar.setStyleSheet(
            f"background:{P['card']};border-bottom:1px solid {P['border']};"
        )
        tl = QHBoxLayout(topbar); tl.setContentsMargins(20,0,20,0); tl.setSpacing(8)
        tl.addWidget(_lbl("Gestion", size=12, color=P["txt2"]))
        tl.addWidget(_lbl(" / ", size=12, color=P["muted"]))
        tl.addWidget(_lbl("EPS / Aseguradoras", size=14, bold=True))
        tl.addStretch()
        self._lbl_top = _lbl("", size=11, color=P["muted"])
        tl.addWidget(self._lbl_top)
        self._root.addWidget(topbar)

        # Tip
        tip = QWidget()
        tip.setStyleSheet(
            f"background:rgba(56,139,253,.07);border-bottom:1px solid {P['border']};"
        )
        tl2 = QHBoxLayout(tip); tl2.setContentsMargins(20,6,20,6)
        tl2.addWidget(_lbl(
            "Tip: clic '...' o clic derecho en la fila para ver acciones. "
            "Solo puedes editar/eliminar las EPS que tu registraste.",
            size=11, color=P["txt2"],
        ))
        self._root.addWidget(tip)

        # Placeholder
        self._placeholder = QLabel("Cargando...")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(
            f"color:{P['muted']};font-size:14px;background:transparent;"
        )
        self._root.addWidget(self._placeholder, 1)

        QTimer.singleShot(50, self._resolver_sesion)

    def _resolver_sesion(self):
        if self._eid is not None and self._oid is not None:
            self._construir_tab(); return

        # Modo standalone
        from gestion_eps_backend import listar_entidades_disponibles
        entidades = listar_entidades_disponibles()

        if not entidades:
            self._placeholder.setText(
                "No hay entidades registradas en la base de datos.\n"
                "Crea una entidad (IPS) primero."
            )
            self._placeholder.setStyleSheet(
                f"color:{P['err']};font-size:13px;background:transparent;padding:20px;"
            )
            return

        if len(entidades) == 1 and self._oid is not None:
            self._eid = entidades[0]["id"]; self._construir_tab(); return

        dlg = _DialogSelectorEntidad(entidades, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.entidad_id is None:
            self.close(); return

        self._eid = dlg.entidad_id
        self._oid = dlg.ops_id_sim
        self._construir_tab()

    def _construir_tab(self):
        self._placeholder.hide(); self._root.removeWidget(self._placeholder)
        self._tab = TabEpsOps(self._eid, self._oid, self)
        self._root.addWidget(self._tab, 1)
        txt = f"Entidad #{self._eid}  |  OPS #{self._oid}"
        if self._nombre: txt += f"  |  {self._nombre}"
        if sesion.es_standalone: txt += "  [DEV]"
        self._lbl_top.setText(txt)


# ══════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════

def main():
    """
    Modo standalone para pruebas del modulo OPS.

    En produccion el sistema principal hace:
        from gestion_eps_ops_ui import sesion, EpsOpsWindow
        sesion.set(entidad_id=5, ops_id=42, nombre="Maria Lopez")
        win = EpsOpsWindow()
        win.show()

    O usando TabEpsOps directamente en GestionWindow:
        tab = TabEpsOps(entidad_id=5, ops_id=42, parent=stack)
    """
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    win = EpsOpsWindow()   # modo standalone → selector automatico
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
