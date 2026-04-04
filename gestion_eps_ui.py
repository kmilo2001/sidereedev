# -*- coding: utf-8 -*-
"""
gestion_eps_ui.py
==================
Seccion 5.4 - Gestion de EPS / Aseguradoras.

Funciones:
  - Busqueda en tiempo real (debounce 300 ms) por nombre, codigo, NIT, municipio, tipo
  - Ver detalle completo
  - Crear / Editar (formulario completo de 2 columnas)
  - Activar / Desactivar
  - Eliminar (con verificacion de dependencias)
  - Carga masiva CSV / XLSX hasta 20 000 filas con barra de progreso
  - Descarga de plantilla Excel

Menu de acciones:
  - Click izquierdo sobre icono '...' al final de la fila → despliega menu
  - Click derecho sobre cualquier celda → mismo menu contextual

Sistema responsivo — 3 modos:
  < 560px   Compacto:   Nombre | Estado | Acciones
  560-960px Tablet:     Codigo | Nombre | NIT | Estado | Acciones
  > 960px   Escritorio: Codigo | Nombre | NIT | Municipio | Tipo | Estado | Contrato | Acciones
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
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem,
    QFrame, QSizePolicy, QScrollArea,
    QAbstractItemView, QMessageBox, QMenu,
    QHeaderView, QProgressBar, QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer, QPoint
from PySide6.QtGui import QCursor, QFont, QResizeEvent

import gestion_eps_backend as eps_bk


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
    border-radius:7px; padding:7px 12px; color:{P['txt']}; font-size:13px;
    min-height:38px;
}}
QComboBox:focus {{ border-color:{P['focus']}; }}
QComboBox::drop-down {{ border:none; width:24px; }}
QComboBox QAbstractItemView {{
    background:{P['card']}; color:{P['txt']};
    border:1px solid {P['border']}; border-radius:6px; selection-background-color:{P['acc_lt']};
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
QProgressBar {{
    background:{P['input']}; border:1px solid {P['border']};
    border-radius:6px; height:14px; text-align:center; color:{P['txt']};
}}
QProgressBar::chunk {{ background:{P['accent']}; border-radius:5px; }}
"""

_CSS_LINE = (
    f"QLineEdit{{background:{P['input']};border:1.5px solid {P['border']};"
    f"border-radius:7px;padding:8px 12px;color:{P['txt']};font-size:13px;}}"
    f"QLineEdit:focus{{border-color:{P['focus']};background:#1C2128;}}"
    f"QLineEdit:disabled{{color:{P['muted']};background:{P['card']};}}"
)

# Indices de columnas (modo escritorio)
_CC, _CN, _CNIT, _CM, _CT, _CREG, _CE, _CCON, _CA = 0, 1, 2, 3, 4, 5, 6, 7, 8


# ══════════════════════════════════════════════════════════════
# HILOS DE TRABAJO
# ══════════════════════════════════════════════════════════════

class _Worker(QThread):
    done     = Signal(object)
    progreso = Signal(int, int)

    def __init__(self, fn, args, kw):
        super().__init__()
        self._fn, self._args, self._kw = fn, args, kw

    def run(self):
        try:
            # Inyectar on_progreso si la funcion lo acepta
            import inspect
            sig = inspect.signature(self._fn)
            if "on_progreso" in sig.parameters:
                self._kw["on_progreso"] = lambda a, t: self.progreso.emit(a, t)
            self.done.emit(self._fn(*self._args, **self._kw))
        except Exception as e:
            self.done.emit(eps_bk.Resultado(False, str(e)))


_workers: list = []


def _run_async(parent, fn, *args, on_done=None, on_progreso=None, **kw):
    w = _Worker(fn, args, kw)
    _workers.append(w)
    if on_done:    w.done.connect(on_done)
    if on_progreso: w.progreso.connect(on_progreso)
    w.done.connect(lambda _: _workers.remove(w) if w in _workers else None)
    w.start()
    return w


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
        "upload": (f"QPushButton{{background:rgba(56,139,253,.12);color:{P['focus']};"
                   f"border:1.5px solid {P['focus']};border-radius:7px;"
                   f"padding:8px 16px;font-size:13px;font-weight:600;}}"
                   f"QPushButton:hover{{background:rgba(56,139,253,.22);}}"),
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
    def ok(self, m):   self._show(m, f"background:rgba(63,185,80,.15);border:1px solid {P['ok']};border-radius:7px;color:{P['ok']};padding:9px 14px;font-size:12px;")
    def err(self, m):  self._show(m, f"background:rgba(248,81,73,.15);border:1px solid {P['err']};border-radius:7px;color:{P['err']};padding:9px 14px;font-size:12px;")
    def warn(self, m): self._show(m, f"background:rgba(210,153,34,.15);border:1px solid {P['warn']};border-radius:7px;color:{P['warn']};padding:9px 14px;font-size:12px;")
    def ocultar(self): self.hide()


class InputF(QWidget):
    def __init__(self, label: str, ph: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QWidget{{background:{P['bg']};border:none;}}")
        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0); lay.setSpacing(4)
        if label:
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{P['txt2']};font-size:12px;background:transparent;")
            lay.addWidget(lbl)
        self.inp = QLineEdit(); self.inp.setPlaceholderText(ph)
        self.inp.setMinimumHeight(38); self.inp.setStyleSheet(_CSS_LINE)
        self._e = QLabel(""); self._e.setStyleSheet(f"color:{P['err']};font-size:11px;background:transparent;"); self._e.hide()
        lay.addWidget(self.inp); lay.addWidget(self._e)
    def text(self) -> str: return self.inp.text().strip()
    def set(self, v):       self.inp.setText(str(v) if v else "")
    def clear(self):        self.inp.clear()
    def setEnabled(self, v: bool): self.inp.setEnabled(v)
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
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{P['txt2']};font-size:12px;background:transparent;")
            lay.addWidget(lbl)
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
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self._mw = int(geo.width() * .95); self._mh = int(geo.height() * .92)
        else:
            self._mw, self._mh = 1000, 800
        ancho = min(ancho_ref, self._mw)
        self.setMinimumWidth(min(320, ancho)); self.setMaximumWidth(self._mw); self.setMaximumHeight(self._mh)
        outer = QVBoxLayout(self); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea{{border:none;background:{P['bg']};}}"
                             f"QScrollBar:vertical{{background:{P['bg']};width:8px;}}"
                             f"QScrollBar::handle:vertical{{background:{P['border']};border-radius:4px;min-height:20px;}}"
                             f"QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}")
        inner = QWidget(); inner.setStyleSheet(f"background:{P['bg']};")
        self.lay = QVBoxLayout(inner); self.lay.setContentsMargins(24,20,24,20); self.lay.setSpacing(0)
        t = QLabel(titulo); t.setStyleSheet(f"color:{P['txt']};font-size:17px;font-weight:700;background:transparent;")
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
# DIALOGO VER
# ══════════════════════════════════════════════════════════════

class DialogEpsVer(BaseDialog):
    def __init__(self, d: dict, parent=None):
        super().__init__("Detalle EPS / Aseguradora", 500, parent)
        lay = self.lay

        # Encabezado con nombre y contrato
        enc = QWidget(); enc.setStyleSheet(f"background:{P['card']};border-radius:8px;")
        el = QHBoxLayout(enc); el.setContentsMargins(16,12,16,12)
        el.addWidget(_lbl(d.get("nombre","—"), size=15, bold=True))
        el.addStretch()
        el.addWidget(_tag_contrato(d.get("tiene_contrato", False)))
        lay.addWidget(enc); lay.addSpacing(16)

        campos = [
            ("Codigo MSPS",      d.get("codigo","")        or "—"),
            ("Tipo",             d.get("tipo","")           or "—"),
            ("NIT",              f"{d.get('nit','')} - {d.get('dv','')}".strip(" -") or "—"),
            ("Departamento",     d.get("departamento","")   or "—"),
            ("Municipio",        d.get("municipio","")      or "—"),
            ("Correo",           d.get("correo","")         or "—"),
            ("Telefono",         d.get("telefono","")       or "—"),
            ("Direccion",        d.get("direccion","")      or "—"),
            ("Digitado por",     d.get("digitado_por","")   or "—"),
            ("Registrado por",   d.get("creado_por_ops_nombre","") or "—"),
            ("Estado",           "Activa" if d.get("activo") else "Inactiva"),
            ("Creado",           d.get("fecha_creacion","") or "—"),
            ("Actualizado",      d.get("ultima_actualizacion","") or "—"),
        ]
        for lbl_txt, val_txt in campos:
            fila = QHBoxLayout()
            lb = QLabel(f"{lbl_txt}:")
            lb.setMinimumWidth(120); lb.setMaximumWidth(160)
            lb.setStyleSheet(f"color:{P['txt2']};font-size:12px;background:transparent;")
            vl = QLabel(str(val_txt)); vl.setWordWrap(True)
            vl.setStyleSheet(f"color:{P['txt']};font-size:13px;background:transparent;")
            fila.addWidget(lb); fila.addWidget(vl, 1)
            lay.addLayout(fila); lay.addSpacing(8)

        lay.addSpacing(16)
        bc = _btn("Cerrar", "sec"); bc.clicked.connect(self.accept); lay.addWidget(bc)
        self._fin()


# ══════════════════════════════════════════════════════════════
# DIALOGO CREAR / EDITAR
# ══════════════════════════════════════════════════════════════

_TIPOS_EPS = ["EPS", "IPS", "ARL", "Aseguradora", "Regimen Especial", "Otro"]

class DialogEps(BaseDialog):
    def __init__(self, eid: int, ops_id, datos_ini: dict | None = None, parent=None):
        titulo = "Editar EPS / Aseguradora" if datos_ini else "Nueva EPS / Aseguradora"
        super().__init__(titulo, 620, parent)
        self._eid = eid
        self._oid = int(ops_id) if ops_id and str(ops_id).strip() not in ("","0") else None
        self._eps_id = datos_ini.get("eps_id") if datos_ini else None
        lay = self.lay

        # Grid 2 columnas
        g = QWidget(); g.setStyleSheet(f"background:{P['bg']};border:none;")
        gl = QGridLayout(g); gl.setContentsMargins(0,0,0,0); gl.setSpacing(12)

        self.f_nombre    = InputF("Nombre *",          "Nombre completo de la entidad")
        self.f_codigo    = InputF("Codigo MSPS/SNS",   "Ej: EPS001")
        self.f_tipo      = ComboF("Tipo",               _TIPOS_EPS)
        self.f_nit       = InputF("NIT",               "Solo numeros")
        self.f_dv        = InputF("DV",                "1 digito")
        self.f_dpto      = InputF("Departamento",      "")
        self.f_mpio      = InputF("Municipio",         "")
        self.f_correo    = InputF("Correo",            "correo@entidad.com")
        self.f_tel       = InputF("Telefono",          "")
        self.f_dir       = InputF("Direccion",         "")
        self.f_digitado  = InputF("Digitado por",      "")

        # Fila 0
        gl.addWidget(self.f_nombre,   0, 0, 1, 2)
        # Fila 1
        gl.addWidget(self.f_codigo,   1, 0)
        gl.addWidget(self.f_tipo,     1, 1)
        # Fila 2
        gl.addWidget(self.f_nit,      2, 0)
        gl.addWidget(self.f_dv,       2, 1)
        # Fila 3
        gl.addWidget(self.f_dpto,     3, 0)
        gl.addWidget(self.f_mpio,     3, 1)
        # Fila 4
        gl.addWidget(self.f_correo,   4, 0)
        gl.addWidget(self.f_tel,      4, 1)
        # Fila 5
        gl.addWidget(self.f_dir,      5, 0, 1, 2)
        # Fila 6
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

        def _done(res: eps_bk.Resultado):
            self.bok.setEnabled(True); self.bok.setText("Guardar")
            if res.ok: self.sb.ok(res.mensaje); QTimer.singleShot(500, self.accept)
            else:      self.sb.err(res.mensaje)

        _run_async(self, eps_bk.guardar_eps,
                   self._eid, self._oid, datos, self._eps_id, on_done=_done)


# ══════════════════════════════════════════════════════════════
# DIALOGO CARGA MASIVA CON BARRA DE PROGRESO
# ══════════════════════════════════════════════════════════════

class DialogCargaMasiva(BaseDialog):
    _sig_prog = Signal(int, int)

    def __init__(self, ruta: str, eid: int, ops_id, parent=None):
        super().__init__("Carga masiva de EPS", 640, parent)
        self._ruta = ruta; self._eid = eid
        self._oid  = int(ops_id) if ops_id and str(ops_id).strip() not in ("","0") else None
        lay = self.lay

        # Nombre del archivo
        info = QLabel(f"Archivo: {ruta.split('/')[-1].split(chr(92))[-1]}")
        info.setStyleSheet(f"color:{P['txt2']};font-size:12px;background:transparent;")
        info.setWordWrap(True)
        lay.addWidget(info); lay.addSpacing(14)

        # Barra de progreso
        self._lbl_prog = _lbl("Preparando...", size=12, color=P["txt2"])
        lay.addWidget(self._lbl_prog)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100); self._bar.setValue(0)
        lay.addWidget(self._bar); lay.addSpacing(12)

        self._sb = StatusBar(); lay.addWidget(self._sb)

        # Tabla de errores (oculta hasta que haya errores)
        self._err_titulo = _lbl("", size=12, color=P["err"])
        self._err_titulo.hide(); lay.addWidget(self._err_titulo)
        self._err_tabla = _make_table(["Fila", "Campo", "Error"])
        self._err_tabla.setColumnWidth(0, 55)
        self._err_tabla.setColumnWidth(1, 140)
        self._err_tabla.hide(); lay.addWidget(self._err_tabla)

        lay.addSpacing(12)
        self.btn_cerrar = _btn("Cancelar", "sec")
        self.btn_cerrar.clicked.connect(self.reject)
        lay.addWidget(self.btn_cerrar)

        self._fin()
        QTimer.singleShot(100, self._iniciar)

    def _iniciar(self):
        self._lbl_prog.setText("Procesando archivo...")
        self._bar.setRange(0, 0)  # modo indeterminado al inicio

        def _prog(actual, total):
            if total > 0:
                self._bar.setRange(0, total)
                self._bar.setValue(actual)
                self._lbl_prog.setText(f"Procesando... {actual}/{total} filas")

        def _done(res: eps_bk.Resultado):
            self._bar.setRange(0, 100); self._bar.setValue(100)
            d = res.datos or {}
            total = d.get("total", 0); creados = d.get("creados", 0)
            actualizados = d.get("actualizados", 0); errores = d.get("errores", [])

            self._lbl_prog.setText(
                f"Completado: {total} filas procesadas — "
                f"{creados} nuevas, {actualizados} actualizadas, {len(errores)} errores"
            )
            if res.ok:
                self._sb.ok(res.mensaje)
            else:
                self._sb.err(res.mensaje)

            if errores:
                self._err_titulo.setText(f"Errores ({min(len(errores),200)} mostrados):")
                self._err_titulo.show()
                self._err_tabla.setRowCount(0)
                for e in errores[:200]:
                    r = self._err_tabla.rowCount(); self._err_tabla.insertRow(r)
                    self._err_tabla.setItem(r, 0, _item(e.get("fila","")))
                    self._err_tabla.setItem(r, 1, _item(e.get("campo","")))
                    self._err_tabla.setItem(r, 2, _item(e.get("error","")))
                    self._err_tabla.setRowHeight(r, 36)
                self._err_tabla.setMinimumHeight(min(260, len(errores)*38+46))
                self._err_tabla.show()

            self.btn_cerrar.setText("Cerrar")
            self.btn_cerrar.clicked.disconnect()
            self.btn_cerrar.clicked.connect(self.accept)
            QTimer.singleShot(30, self._sz)

        _run_async(self, eps_bk.procesar_carga_masiva,
                   self._eid, self._oid, self._ruta,
                   on_done=_done, on_progreso=_prog)


# ══════════════════════════════════════════════════════════════
# TAB PRINCIPAL — responsivo + menu unificado
# ══════════════════════════════════════════════════════════════

class TabEps(QWidget):
    """
    Widget principal del modulo 5.4.
    Exportado para usar en GestionWindow:
        self._t_eps = TabEps(rol, entidad_id, ops_id, self._stack)
    """
    def __init__(self, rol: str, entidad_id: int, ops_id, parent=None):
        super().__init__(parent)
        self._rol  = rol
        self._eid  = entidad_id
        self._oid  = int(ops_id) if ops_id and str(ops_id).strip() not in ("","0") else None
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

        # Barra de acciones (se reorganiza segun modo)
        self._barra = QWidget(); self._barra.setStyleSheet("background:transparent;")
        self._blay  = QVBoxLayout(self._barra)
        self._blay.setContentsMargins(0,8,0,0); self._blay.setSpacing(8)

        # Fila 1: busqueda
        self._fbus = QWidget(); self._fbus.setStyleSheet("background:transparent;")
        fl1 = QHBoxLayout(self._fbus); fl1.setContentsMargins(0,0,0,0); fl1.setSpacing(8)
        self.bus = QLineEdit()
        self.bus.setPlaceholderText("Buscar por nombre, codigo, NIT, municipio o tipo...")
        self.bus.setMinimumHeight(38); self.bus.setStyleSheet(_CSS_LINE)
        self._deb = QTimer(self); self._deb.setSingleShot(True)
        self._deb.timeout.connect(lambda: self._cargar(self.bus.text()))
        self.bus.textChanged.connect(lambda _: self._deb.start(300))
        fl1.addWidget(self.bus, 1)

        # Fila 2: botones
        self._fbtn = QWidget(); self._fbtn.setStyleSheet("background:transparent;")
        fl2 = QHBoxLayout(self._fbtn); fl2.setContentsMargins(0,0,0,0); fl2.setSpacing(8)
        self.btn_nueva = _btn("+ Nueva EPS")
        self.btn_nueva.clicked.connect(self._nueva)
        fl2.addWidget(self.btn_nueva)
        if self._rol == "admin":
            self.btn_masivo   = _btn("Cargar Excel/CSV", "upload")
            self.btn_plantilla = _btn("Descargar plantilla", "sec")
            self.btn_masivo.clicked.connect(self._masivo)
            self.btn_plantilla.clicked.connect(self._plantilla)
            fl2.addWidget(self.btn_masivo)
            fl2.addWidget(self.btn_plantilla)
        fl2.addStretch()

        self._blay.addWidget(self._fbus)
        self._blay.addWidget(self._fbtn)
        root.addWidget(self._barra)

        # Tabla
        self.tabla = _make_table([
            "Codigo", "Nombre", "NIT", "Municipio", "Tipo",
            "Registrado por", "Estado", "Contrato", "Acciones"
        ])
        self.tabla.customContextMenuRequested.connect(self._ctx_fila)
        root.addWidget(self.tabla, 1)

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
        if modo == "compacto":
            ocultas = {_CC, _CNIT, _CM, _CT, _CREG, _CCON}
            self.btn_nueva.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        elif modo == "tablet":
            ocultas = {_CM, _CT, _CREG, _CCON}
            self.btn_nueva.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        else:
            ocultas = set()
            self.btn_nueva.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        for c in range(self.tabla.columnCount()):
            hdr.setSectionHidden(c, c in ocultas)

    def _anchos(self, w: int):
        hdr = self.tabla.horizontalHeader()
        hdr.setSectionResizeMode(_CN, QHeaderView.ResizeMode.Stretch)
        if self._modo == "compacto":
            self.tabla.setColumnWidth(_CE, 90); self.tabla.setColumnWidth(_CA, 52)
        elif self._modo == "tablet":
            self.tabla.setColumnWidth(_CC, 90); self.tabla.setColumnWidth(_CNIT, 110)
            self.tabla.setColumnWidth(_CE, 90); self.tabla.setColumnWidth(_CA, 52)
        else:
            self.tabla.setColumnWidth(_CC, 90);  self.tabla.setColumnWidth(_CNIT, 120)
            self.tabla.setColumnWidth(_CM, 110);  self.tabla.setColumnWidth(_CT, 110)
            self.tabla.setColumnWidth(_CREG, 130); self.tabla.setColumnWidth(_CE, 90)
            self.tabla.setColumnWidth(_CCON, 115); self.tabla.setColumnWidth(_CA, 52)

    # ── Carga ─────────────────────────────────────────────────

    def _cargar(self, filtro: str = ""):
        filtro = filtro if isinstance(filtro, str) else ""
        _run_async(self, eps_bk.listar_eps, self._eid, filtro, on_done=self._poblar)

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
            # Registrado por: nombre del OPS o Maestro que creó el registro
            reg_nom = d.get("creado_por_ops_nombre") or "—"
            it_reg  = _item(reg_nom)
            from PySide6.QtGui import QColor as _QColor
            it_reg.setForeground(_QColor(P["txt2"]))
            self.tabla.setItem(r, _CREG, it_reg)
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

    # ── Menu ──────────────────────────────────────────────────

    def _ctx_fila(self, pos: QPoint):
        idx = self.tabla.indexAt(pos)
        if not idx.isValid(): return
        fila = idx.row()
        if fila < 0 or fila >= len(self._cache): return
        self._menu(self._cache[fila], pos=self.tabla.viewport().mapToGlobal(pos))

    def _menu(self, d: dict, widget=None, pos: QPoint | None = None):
        eid   = d["eps_id"]; activo = d.get("activo", True)
        m = _make_menu()
        m.addAction("  Ver detalle").triggered.connect(lambda: self._ver(eid))
        m.addSeparator()
        m.addAction("  Editar").triggered.connect(lambda: self._editar(eid))
        m.addSeparator()
        lbl_est = "  Desactivar" if activo else "  Activar"
        m.addAction(lbl_est).triggered.connect(lambda: self._estado(eid, not activo))
        m.addSeparator()
        m.addAction("  Eliminar").triggered.connect(lambda: self._eliminar(eid, d.get("nombre","")))
        if pos: m.exec(pos)
        elif widget: m.exec(widget.mapToGlobal(widget.rect().bottomLeft()))
        else: m.exec(QCursor.pos())

    # ── Acciones ──────────────────────────────────────────────

    def _ver(self, eid: int):
        d = eps_bk.obtener_eps(self._eid, int(eid))
        if not d: QMessageBox.warning(self, "No encontrada", "EPS no encontrada."); return
        DialogEpsVer(d, self).exec()

    def _nueva(self):
        if DialogEps(self._eid, self._oid, parent=self).exec():
            self._cargar(self.bus.text())

    def _editar(self, eid: int):
        d = eps_bk.obtener_eps(self._eid, int(eid))
        if not d: QMessageBox.warning(self, "No encontrada", "EPS no encontrada."); return
        if DialogEps(self._eid, self._oid, d, parent=self).exec():
            self._cargar(self.bus.text())

    def _estado(self, eid: int, activo: bool):
        accion = "activar" if activo else "desactivar"
        if QMessageBox.question(
            self, "Confirmar", f"¿Deseas {accion} esta EPS?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        def _done(res):
            if res.ok: QMessageBox.information(self, "Resultado", res.mensaje)
            else:      QMessageBox.warning(self, "Error", res.mensaje)
            self._cargar(self.bus.text())
        _run_async(self, eps_bk.cambiar_estado_eps, self._eid, int(eid), activo, on_done=_done)

    def _eliminar(self, eid: int, nombre: str):
        if QMessageBox.question(
            self, "Confirmar eliminacion",
            f"¿Eliminar '{nombre}' permanentemente?\n\n"
            "Se bloqueara si tiene pacientes, eventos o contratos vinculados.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        def _done(res):
            if res.ok: QMessageBox.information(self, "Eliminada", res.mensaje)
            else:      QMessageBox.warning(self, "No se pudo eliminar", res.mensaje)
            self._cargar(self.bus.text())
        _run_async(self, eps_bk.eliminar_eps, self._eid, int(eid), on_done=_done)

    def _masivo(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo", "",
            "Excel o CSV (*.xlsx *.xls *.csv)"
        )
        if not ruta: return
        dlg = DialogCargaMasiva(ruta, self._eid, self._oid, self)
        dlg.exec()
        self._cargar(self.bus.text())

    def _plantilla(self):
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar plantilla", "plantilla_eps.xlsx",
            "Excel (*.xlsx)"
        )
        if not ruta: return
        res = eps_bk.generar_plantilla_excel(ruta)
        if res.ok: QMessageBox.information(self, "Plantilla", res.mensaje)
        else:      QMessageBox.warning(self, "Error", res.mensaje)


# ══════════════════════════════════════════════════════════════
# DIALOGO SELECTOR DE ENTIDAD (solo modo standalone / desarrollo)
# ══════════════════════════════════════════════════════════════

class _DialogSelectorEntidad(QDialog):
    """
    Aparece SOLO en modo standalone (python gestion_eps_ui.py).
    Permite elegir la entidad (IPS) con la que trabajar sin sesion.
    En produccion (.exe / main) esta ventana NUNCA se muestra;
    el entidad_id llega desde la sesion autenticada.
    """
    def __init__(self, entidades: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar entidad — Modo desarrollo")
        self.setModal(True)
        self.setFixedWidth(480)
        self.setStyleSheet(f"QDialog{{background:{P['bg']};}}" + _CSS_BASE)

        self.entidad_id: int | None = None
        self.rol:        str        = "admin"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        # Titulo
        t = QLabel("Modo desarrollo — Seleccionar entidad")
        t.setStyleSheet(
            f"color:{P['txt']};font-size:16px;font-weight:700;background:transparent;"
        )
        lay.addWidget(t)

        # Aviso
        av = QLabel(
            "Este selector solo aparece al ejecutar el modulo directamente "
            "(python gestion_eps_ui.py). En produccion el entidad_id "
            "se toma de la sesion del usuario autenticado."
        )
        av.setWordWrap(True)
        av.setStyleSheet(
            f"background:rgba(210,153,34,.12);border:1px solid {P['warn']};"
            f"border-radius:7px;color:{P['warn']};padding:10px 12px;font-size:11px;"
        )
        lay.addWidget(av)

        # Separador
        f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet(f"border:none;border-top:1px solid {P['border']};background:transparent;")
        f.setFixedHeight(1); lay.addWidget(f)

        # Combo entidad
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
            label = f"[{e['id']}] {e['nombre_entidad']}  —  NIT {e['nit']}"
            self._combo.addItem(label, e["id"])
        lay.addWidget(self._combo)

        # Combo rol
        lbl_r = QLabel("Rol de prueba:")
        lbl_r.setStyleSheet(f"color:{P['txt2']};font-size:12px;background:transparent;")
        lay.addWidget(lbl_r)

        self._rol_combo = QComboBox()
        self._rol_combo.setStyleSheet(self._combo.styleSheet())
        self._rol_combo.addItem("Administrador  (admin)", "admin")
        self._rol_combo.addItem("Operador OPS   (ops)",   "ops")
        lay.addWidget(self._rol_combo)

        lay.addSpacing(8)

        # Botones
        row = QHBoxLayout(); row.setSpacing(10)
        bc = _btn("Cancelar", "sec"); bc.clicked.connect(self.reject)
        bo = _btn("Continuar")
        bo.clicked.connect(self._aceptar)
        row.addWidget(bc); row.addStretch(); row.addWidget(bo)
        lay.addLayout(row)

    def _aceptar(self):
        self.entidad_id = self._combo.currentData()
        self.rol        = self._rol_combo.currentData()
        self.accept()


# ══════════════════════════════════════════════════════════════
# SESION GLOBAL (inyectada por el sistema principal en produccion)
# ══════════════════════════════════════════════════════════════

class _Sesion:
    """
    Contenedor de sesion.

    Modo standalone  → se llena desde _DialogSelectorEntidad.
    Modo produccion  → se inyecta llamando a _Sesion.set(...) desde
                       el main del sistema antes de instanciar EpsWindow.

    Uso desde el sistema principal:
        from gestion_eps_ui import sesion as _sesion_eps
        _sesion_eps.set(entidad_id=5, rol="admin", ops_id=42, nombre="Juan")
        win = EpsWindow()   # ya no pide selector
        win.show()
    """
    def __init__(self):
        self.entidad_id: int | None  = None
        self.ops_id:     int | None  = None
        self.rol:        str         = "admin"
        self.nombre:     str         = ""
        self._inyectada: bool        = False

    def set(self, entidad_id: int, rol: str = "admin",
            ops_id=None, nombre: str = ""):
        """Llamar desde el sistema principal para inyectar la sesion."""
        self.entidad_id = entidad_id
        self.rol        = rol
        self.ops_id     = int(ops_id) if ops_id and str(ops_id).strip() not in ("","0") else None
        self.nombre     = nombre
        self._inyectada = True

    @property
    def es_standalone(self) -> bool:
        return not self._inyectada


# Instancia global — el sistema principal la importa y la configura
sesion = _Sesion()


# ══════════════════════════════════════════════════════════════
# VENTANA PRINCIPAL
# ══════════════════════════════════════════════════════════════

class EpsWindow(QMainWindow):
    """
    Ventana principal del modulo EPS.

    Modo standalone  (python gestion_eps_ui.py):
        - Muestra _DialogSelectorEntidad para elegir entidad real de la BD.
        - Detecta automaticamente la primera entidad si solo hay una.

    Modo produccion  (.exe / GestionWindow / main del sistema):
        - Usa sesion.entidad_id, sesion.rol, sesion.ops_id.
        - No muestra ningun selector; el usuario ya esta autenticado.

    Parametros opcionales (por compatibilidad con GestionWindow):
        entidad_id, rol, ops_id  — si se pasan explicitamente,
        sobreescriben la sesion global.
    """
    def __init__(
        self,
        entidad_id: int | None = None,
        rol:        str        | None = None,
        ops_id                 = None,
        nombre_usuario: str    = "",
    ):
        super().__init__()
        self.setWindowTitle("EPS / Aseguradoras — Gestion Eventos Salud")
        self.setStyleSheet(_CSS_BASE)
        self.setMinimumSize(400, 480)

        # ── Resolver sesion ───────────────────────────────────
        # Prioridad: parametros explicitos > sesion global > standalone
        if entidad_id is not None:
            # Llamado desde GestionWindow con datos ya validados
            self._eid    = entidad_id
            self._rol    = rol or "admin"
            self._oid    = (int(ops_id) if ops_id and str(ops_id).strip() not in ("","0")
                            else None)
            self._nombre = nombre_usuario
        elif sesion.entidad_id is not None:
            # Sesion inyectada por el sistema principal
            self._eid    = sesion.entidad_id
            self._rol    = sesion.rol
            self._oid    = sesion.ops_id
            self._nombre = sesion.nombre
        else:
            # Modo standalone — resolver entidad real de la BD
            self._eid    = None
            self._rol    = "admin"
            self._oid    = None
            self._nombre = "Desarrollo"

        # Tamaño responsivo al 75% de la pantalla
        sc = QApplication.primaryScreen()
        if sc:
            geo = sc.availableGeometry()
            w = max(480, min(int(geo.width()  * .75), geo.width()))
            h = max(520, min(int(geo.height() * .78), geo.height()))
            self.resize(w, h)
            self.move(geo.x()+(geo.width()-w)//2, geo.y()+(geo.height()-h)//2)
        else:
            self.resize(1100, 680)

        # Construir UI base (el tab se agrega despues de resolver entidad)
        central = QWidget(); central.setStyleSheet(f"background:{P['bg']};")
        self.setCentralWidget(central)
        self._root = QVBoxLayout(central)
        self._root.setContentsMargins(0,0,0,0); self._root.setSpacing(0)

        self._topbar = self._mk_topbar()
        self._root.addWidget(self._topbar)

        # Tip siempre visible
        tip = QWidget()
        tip.setStyleSheet(
            f"background:rgba(56,139,253,.07);border-bottom:1px solid {P['border']};"
        )
        tl2 = QHBoxLayout(tip); tl2.setContentsMargins(20,6,20,6)
        tl2.addWidget(_lbl(
            "Tip: clic izquierdo en '...' o clic derecho en la fila para ver acciones.",
            size=11, color=P["txt2"],
        ))
        self._root.addWidget(tip)

        # Placeholder hasta resolver entidad
        self._tab: TabEps | None = None
        self._placeholder = QLabel("Cargando...")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(
            f"color:{P['muted']};font-size:14px;background:transparent;"
        )
        self._root.addWidget(self._placeholder, 1)

        # Resolver entidad tras mostrar la ventana
        QTimer.singleShot(50, self._resolver_entidad)

    def _mk_topbar(self) -> QWidget:
        topbar = QWidget(); topbar.setFixedHeight(52)
        topbar.setStyleSheet(
            f"background:{P['card']};border-bottom:1px solid {P['border']};"
        )
        tl = QHBoxLayout(topbar); tl.setContentsMargins(20,0,20,0); tl.setSpacing(8)
        tl.addWidget(_lbl("Gestion", size=12, color=P["txt2"]))
        tl.addWidget(_lbl(" / ", size=12, color=P["muted"]))
        tl.addWidget(_lbl("EPS / Aseguradoras", size=14, bold=True))
        tl.addStretch()
        self._lbl_sesion = _lbl("", size=11, color=P["muted"])
        tl.addWidget(self._lbl_sesion)
        return topbar

    def _actualizar_topbar(self):
        modo = "DEV" if sesion.es_standalone and sesion.entidad_id is None else self._rol.upper()
        txt  = f"Entidad #{self._eid}  |  {modo}"
        if self._nombre:
            txt += f"  |  {self._nombre}"
        self._lbl_sesion.setText(txt)

    def _resolver_entidad(self):
        """
        Resuelve entidad_id:
          - Si ya tiene eid valido → construir tab directamente.
          - Si es standalone → mostrar selector con entidades reales de la BD.
        """
        if self._eid is not None:
            self._construir_tab()
            return

        # Modo standalone: buscar entidades en la BD
        entidades = eps_bk.listar_entidades_disponibles()

        if not entidades:
            self._placeholder.setText(
                "No hay entidades registradas en la base de datos.\n"
                "Crea una entidad (IPS) primero e intenta de nuevo."
            )
            self._placeholder.setStyleSheet(
                f"color:{P['err']};font-size:13px;background:transparent;"
                f"padding:20px;"
            )
            return

        if len(entidades) == 1:
            # Solo una entidad → usarla directamente sin preguntar
            self._eid = entidades[0]["id"]
            self._construir_tab()
            return

        # Multiples entidades → mostrar selector
        dlg = _DialogSelectorEntidad(entidades, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.entidad_id is None:
            self.close()
            return

        self._eid = dlg.entidad_id
        self._rol = dlg.rol
        self._construir_tab()

    def _construir_tab(self):
        """Instancia el TabEps con el entidad_id ya resuelto."""
        self._placeholder.hide()
        self._root.removeWidget(self._placeholder)

        self._tab = TabEps(self._rol, self._eid, self._oid, self)
        self._root.addWidget(self._tab, 1)
        self._actualizar_topbar()


# ══════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════

def main():
    """
    Punto de entrada para prueba standalone del modulo.

    En produccion (.exe / sistema completo) NO se llama este main().
    En su lugar el sistema principal hace:

        from gestion_eps_ui import sesion, EpsWindow
        sesion.set(entidad_id=5, rol="admin", ops_id=42, nombre="Juan Perez")
        win = EpsWindow()
        win.show()
    """
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))

    win = EpsWindow()   # entidad_id=None → modo standalone → selector automatico
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()