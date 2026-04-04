# -*- coding: utf-8 -*-
# =============================================================================
# auditoria_ui.py
# Módulo de Auditoría / Historial de actividad — SIGES / PySide6
#
# EXPORTA: TabAuditoria  (embeber en main.py con _wrap)
#
# VISIBILIDAD (definida en auditoria_backend):
#   Maestro  → todas las entidades, todos los módulos, todos los usuarios
#   Admin    → su entidad: todos sus OPS + acciones del Maestro en su entidad
#   OPS      → su entidad: solo sus propias acciones + las del Maestro
# =============================================================================

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSizePolicy,
    QComboBox, QLineEdit, QDialog, QScrollArea,
    QGridLayout, QTextEdit, QApplication, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QColor, QCursor, QFont

import auditoria_backend as abk

# ──────────────────────────────────────────────────────────────────────────────
# Paleta (misma que el resto de SIGES)
# ──────────────────────────────────────────────────────────────────────────────
P = {
    "bg":     "#0D1117", "card":   "#161B22", "input":  "#21262D",
    "border": "#30363D", "focus":  "#388BFD", "accent": "#2D6ADF",
    "acc_h":  "#388BFD", "acc_lt": "#1C3A6E",
    "ok":     "#3FB950", "err":    "#F85149", "warn":   "#D29922",
    "txt":    "#E6EDF3", "txt2":   "#8B949E", "muted":  "#484F58",
    "white":  "#FFFFFF", "row_alt":"#0F1419", "row_sel":"#1C3A6E",
    "ins":    "#1C3A6E", "upd":    "#2D3B1A", "del":    "#3B1A1A",
}

_CSS = f"""
QWidget  {{ background:{P['bg']}; color:{P['txt']};
           font-family:'Segoe UI','Helvetica Neue',Arial,sans-serif;
           font-size:13px; }}
QLabel   {{ background:transparent; }}
QLineEdit {{
    background:{P['input']}; border:1.5px solid {P['border']};
    border-radius:7px; padding:8px 12px; color:{P['txt']}; font-size:13px;
}}
QLineEdit:focus {{ border-color:{P['focus']}; background:#1C2128; }}
QComboBox {{
    background:{P['input']}; border:1.5px solid {P['border']};
    border-radius:7px; padding:6px 28px 6px 10px;
    color:{P['txt']}; font-size:12px; min-height:36px;
}}
QComboBox:hover  {{ border-color:{P['focus']}; }}
QComboBox::drop-down {{ border:none; width:22px; }}
QComboBox QAbstractItemView {{
    background:{P['card']}; color:{P['txt']};
    border:1px solid {P['border']};
    selection-background-color:{P['acc_lt']};
}}
QTableWidget {{
    background:{P['card']}; border:1px solid {P['border']};
    border-radius:8px; gridline-color:{P['border']};
    color:{P['txt']}; font-size:12px;
    alternate-background-color:{P['row_alt']};
    selection-background-color:{P['row_sel']};
}}
QTableWidget::item {{ padding:4px 8px; border:none; }}
QHeaderView::section {{
    background:{P['card']}; color:{P['txt2']};
    border:none; border-right:1px solid {P['border']};
    border-bottom:1px solid {P['border']};
    padding:6px 8px; font-size:11px; font-weight:700;
    letter-spacing:0.3px;
}}
QScrollBar:vertical {{ background:transparent; width:6px; }}
QScrollBar::handle:vertical {{ background:{P['border']}; border-radius:3px; min-height:20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
"""


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _lbl(txt, size=13, color=None, bold=False, wrap=False):
    lb = QLabel(str(txt))
    lb.setStyleSheet(
        f"color:{color or P['txt']};font-size:{size}px;"
        f"font-weight:{'700' if bold else '400'};background:transparent;"
    )
    if wrap:
        lb.setWordWrap(True)
    return lb


def _sep():
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet(f"border:none;background:{P['border']};")
    return f


def _btn(txt, estilo="primary", parent=None):
    b = QPushButton(txt, parent)
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    S = {
        "primary":   (f"QPushButton{{background:{P['accent']};color:{P['white']};border:none;"
                      f"border-radius:7px;padding:8px 18px;font-size:13px;font-weight:600;}}"
                      f"QPushButton:hover{{background:{P['acc_h']};}}"
                      f"QPushButton:disabled{{background:{P['muted']};color:{P['bg']};}}"),
        "secondary": (f"QPushButton{{background:transparent;color:{P['txt2']};"
                      f"border:1.5px solid {P['border']};border-radius:7px;"
                      f"padding:7px 14px;font-size:12px;}}"
                      f"QPushButton:hover{{border-color:{P['focus']};color:{P['txt']};"
                      f"background:{P['input']};}}"),
    }
    b.setStyleSheet(S.get(estilo, S["primary"]))
    return b


def _item(text, color=None):
    it = QTableWidgetItem(str(text) if text is not None else "")
    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if color:
        it.setForeground(QColor(color))
    return it


def _badge_operacion(op: str) -> QLabel:
    cfg = {
        "INSERT": (P["ok"],   "#0D2A1A", "Creación"),
        "UPDATE": (P["warn"], "#2A1F00", "Actualización"),
        "DELETE": (P["err"],  "#2A0909", "Eliminación"),
    }
    color, bg, texto = cfg.get(op, (P["txt2"], P["card"], op))
    lb = QLabel(f"  {texto}  ")
    lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lb.setStyleSheet(
        f"background:{bg};color:{color};border:1px solid {color};"
        f"border-radius:6px;padding:2px 6px;font-size:11px;font-weight:700;"
    )
    return lb


# ──────────────────────────────────────────────────────────────────────────────
# Worker asíncrono
# ──────────────────────────────────────────────────────────────────────────────

class _Worker(QThread):
    done = Signal(object)

    def __init__(self, fn, args, kw):
        super().__init__()
        self._fn, self._args, self._kw = fn, args, kw

    def run(self):
        try:
            self.done.emit(self._fn(*self._args, **self._kw))
        except Exception as e:
            self.done.emit([])


_workers: list = []


def _run_async(fn, *args, on_done=None, **kw):
    w = _Worker(fn, args, kw)
    _workers.append(w)
    if on_done:
        w.done.connect(on_done)
    w.done.connect(lambda _: _workers.remove(w) if w in _workers else None)
    w.start()


# ──────────────────────────────────────────────────────────────────────────────
# Diálogo de detalle JSON
# ──────────────────────────────────────────────────────────────────────────────

class DialogDetalle(QDialog):
    """Muestra el detalle completo de un registro de auditoría."""

    def __init__(self, registro: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detalle del cambio")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setStyleSheet(_CSS)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # Encabezado
        hdr = QWidget()
        hdr.setStyleSheet(f"background:{P['card']};border-bottom:1px solid {P['border']};")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(20, 16, 20, 16)
        tabla_lbl = abk.TABLA_LABELS.get(registro.get("tabla", ""), registro.get("tabla", ""))
        hl.addWidget(_lbl(f"Detalle — {tabla_lbl}", size=15, bold=True))
        hl.addStretch()
        hl.addWidget(_badge_operacion(registro.get("operacion", "")))
        root.addWidget(hdr)

        # Scroll de contenido
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea{{border:none;background:{P['bg']}}}")
        inner = QWidget(); inner.setStyleSheet(f"background:{P['bg']};")
        lay = QVBoxLayout(inner); lay.setContentsMargins(20, 16, 20, 20); lay.setSpacing(10)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        # Metadatos
        grid = QGridLayout(); grid.setSpacing(8); grid.setColumnStretch(1, 1)

        def _campo(etq, val, row, col=0):
            e = _lbl(etq + ":", size=11, color=P["txt2"])
            e.setFixedWidth(140)
            v = _lbl(str(val or "—"), size=12)
            v.setWordWrap(True)
            grid.addWidget(e, row, col * 2)
            grid.addWidget(v, row, col * 2 + 1)

        _campo("Tabla",       abk.TABLA_LABELS.get(registro.get("tabla",""), registro.get("tabla","")), 0, 0)
        _campo("Operación",   abk.OPERACION_LABELS.get(registro.get("operacion",""), registro.get("operacion","")), 0, 1)
        _campo("ID registro", registro.get("registro_id"),    1, 0)
        _campo("Fecha/Hora",  registro.get("fecha_legible"),  1, 1)
        _campo("Entidad",     registro.get("entidad_nombre"), 2, 0)
        _campo("Realizado por", registro.get("ops_nombre"),   2, 1)
        _campo("IP origen",   registro.get("ip_origen"),      3, 0)

        lay.addLayout(grid)
        lay.addWidget(_sep())

        # Datos antes / después
        for titulo, clave, color_borde in [
            ("Datos antes del cambio",  "datos_antes",   P["err"]),
            ("Datos después del cambio","datos_despues", P["ok"]),
        ]:
            datos = registro.get(clave)
            if datos is None:
                continue
            lay.addSpacing(6)
            lay.addWidget(_lbl(titulo, size=12, bold=True))
            lay.addSpacing(4)

            if isinstance(datos, str):
                try:
                    datos = json.loads(datos)
                except Exception:
                    pass

            texto_json = json.dumps(datos, ensure_ascii=False, indent=2) if isinstance(datos, dict) else str(datos)

            te = QTextEdit()
            te.setReadOnly(True)
            te.setPlainText(texto_json)
            te.setMaximumHeight(220)
            te.setStyleSheet(
                f"QTextEdit{{background:{P['input']};border:1.5px solid {color_borde};"
                f"border-radius:7px;color:{P['txt']};font-family:'Consolas','Courier New',monospace;"
                f"font-size:11px;padding:8px;}}"
            )
            lay.addWidget(te)

        lay.addSpacing(14)
        bc = _btn("Cerrar", "secondary")
        bc.clicked.connect(self.accept)
        lay.addWidget(bc)

        # Ajustar tamaño
        screen = QApplication.primaryScreen()
        max_h = int(screen.availableGeometry().height() * 0.88) if screen else 860
        self.resize(640, min(max_h, 760))


# ──────────────────────────────────────────────────────────────────────────────
# Encabezado con tarjetas de stats
# ──────────────────────────────────────────────────────────────────────────────

class _HeaderAuditoria(QWidget):

    def __init__(self, ejecutor: dict, entidad_id: int, parent=None):
        super().__init__(parent)
        self._ejecutor  = ejecutor
        self._eid       = entidad_id
        self.setStyleSheet("background:transparent;border:none;")
        self._build()
        self._cargar_stats()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(10)

        # Título + badge de rol
        title_row = QHBoxLayout(); title_row.setSpacing(8)
        title_row.addWidget(_lbl("Auditoría / Historial de Actividad", size=18, bold=True))

        if self._ejecutor.get("es_maestro"):
            tag_txt, tag_c, tag_bg = "Maestro — visión global", "#D97706", "#451A03"
        elif self._ejecutor.get("rol") == "admin":
            tag_txt, tag_c, tag_bg = "Admin — su entidad",      P["acc_h"], P["acc_lt"]
        else:
            tag_txt, tag_c, tag_bg = "OPS — sus acciones",      P["ok"],    "#0D2A1A"

        tag = QLabel(f"  {tag_txt}  ")
        tag.setStyleSheet(
            f"background:{tag_bg};color:{tag_c};border:1px solid {tag_c};"
            f"border-radius:7px;padding:3px 10px;font-size:11px;font-weight:700;"
        )
        title_row.addWidget(tag)
        title_row.addStretch()
        lay.addLayout(title_row)

        # Tarjetas de stats
        stats_row = QHBoxLayout(); stats_row.setSpacing(8)
        self._sc: dict = {}
        for key, etq, color in [
            ("total",   "Total",        P["txt2"]),
            ("hoy",     "Hoy",          P["acc_h"]),
            ("semana",  "Esta semana",  P["ok"]),
            ("mes",     "Este mes",     P["warn"]),
            ("inserts", "Creaciones",   P["ok"]),
            ("updates", "Actualizaciones", P["warn"]),
            ("deletes", "Eliminaciones",P["err"]),
        ]:
            card = QWidget()
            card.setStyleSheet(
                f"QWidget{{background:{P['card']};border:1px solid {P['border']};"
                f"border-radius:8px;}}"
            )
            cl = QVBoxLayout(card); cl.setContentsMargins(10, 7, 10, 7); cl.setSpacing(1)
            v = _lbl("—", size=16, color=color, bold=True)
            t = _lbl(etq, size=10, color=P["txt2"])
            cl.addWidget(v); cl.addWidget(t)
            card._val = v
            self._sc[key] = card
            stats_row.addWidget(card)
        lay.addLayout(stats_row)

    def _cargar_stats(self):
        def done(s):
            if not isinstance(s, dict):
                return
            for key, card in self._sc.items():
                card._val.setText(str(s.get(key, "—")))
        _run_async(abk.stats_auditoria, self._ejecutor, self._eid, on_done=done)

    def refrescar(self):
        self._cargar_stats()


# ──────────────────────────────────────────────────────────────────────────────
# Panel de filtros
# ──────────────────────────────────────────────────────────────────────────────

class _PanelFiltros(QWidget):
    filtros_cambiados = Signal(dict)

    def __init__(self, ejecutor: dict, entidad_id: int, parent=None):
        super().__init__(parent)
        self._ejecutor = ejecutor
        self._eid      = entidad_id
        self.setStyleSheet("background:transparent;border:none;")
        self._build()
        self._cargar_ops()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(8)

        # Búsqueda libre
        self._busq = QLineEdit()
        self._busq.setPlaceholderText("Buscar en datos del registro...")
        self._busq.setMinimumHeight(36)
        self._deb = QTimer(self); self._deb.setSingleShot(True)
        self._deb.timeout.connect(self._emitir)
        self._busq.textChanged.connect(lambda _: self._deb.start(400))
        lay.addWidget(self._busq, 2)

        # Filtro tabla
        self._cb_tabla = QComboBox(); self._cb_tabla.setMinimumHeight(36)
        self._cb_tabla.addItem("Todos los módulos", None)
        for clave, etq in abk.TABLA_LABELS.items():
            self._cb_tabla.addItem(etq, clave)
        self._cb_tabla.currentIndexChanged.connect(self._emitir)
        lay.addWidget(self._cb_tabla, 1)

        # Filtro operación
        self._cb_op = QComboBox(); self._cb_op.setMinimumHeight(36)
        self._cb_op.addItem("Todas las acciones", None)
        for clave, etq in abk.OPERACION_LABELS.items():
            self._cb_op.addItem(etq, clave)
        self._cb_op.currentIndexChanged.connect(self._emitir)
        lay.addWidget(self._cb_op, 1)

        # Filtro usuario OPS
        self._cb_ops = QComboBox(); self._cb_ops.setMinimumHeight(36)
        self._cb_ops.addItem("Todos los usuarios", None)
        self._cb_ops.currentIndexChanged.connect(self._emitir)
        lay.addWidget(self._cb_ops, 1)

        # Fecha desde / hasta
        self._f_desde = QLineEdit(); self._f_desde.setPlaceholderText("Desde (AAAA-MM-DD)")
        self._f_desde.setFixedWidth(150); self._f_desde.setMinimumHeight(36)
        self._f_desde.textChanged.connect(lambda _: self._deb.start(600))
        lay.addWidget(self._f_desde)

        self._f_hasta = QLineEdit(); self._f_hasta.setPlaceholderText("Hasta (AAAA-MM-DD)")
        self._f_hasta.setFixedWidth(150); self._f_hasta.setMinimumHeight(36)
        self._f_hasta.textChanged.connect(lambda _: self._deb.start(600))
        lay.addWidget(self._f_hasta)

        # Botón limpiar
        b_limpiar = _btn("✕", "secondary")
        b_limpiar.setFixedSize(36, 36)
        b_limpiar.setToolTip("Limpiar filtros")
        b_limpiar.clicked.connect(self._limpiar)
        lay.addWidget(b_limpiar)

    def _cargar_ops(self):
        def done(lista):
            if not isinstance(lista, list):
                return
            self._cb_ops.blockSignals(True)
            self._cb_ops.clear()
            self._cb_ops.addItem("Todos los usuarios", None)
            for o in lista:
                self._cb_ops.addItem(o.get("nombre", ""), o.get("ops_id"))
            self._cb_ops.blockSignals(False)
        _run_async(abk.listar_ops_auditables, self._ejecutor, self._eid, on_done=done)

    def _limpiar(self):
        self._busq.clear()
        self._cb_tabla.setCurrentIndex(0)
        self._cb_op.setCurrentIndex(0)
        self._cb_ops.setCurrentIndex(0)
        self._f_desde.clear()
        self._f_hasta.clear()

    def _emitir(self):
        self.filtros_cambiados.emit(self.obtener())

    def obtener(self) -> dict:
        return {
            "texto":         self._busq.text().strip() or None,
            "tabla":         self._cb_tabla.currentData(),
            "operacion":     self._cb_op.currentData(),
            "ops_id_filtro": self._cb_ops.currentData(),
            "fecha_desde":   self._f_desde.text().strip() or None,
            "fecha_hasta":   self._f_hasta.text().strip() or None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Tabla de resultados
# ──────────────────────────────────────────────────────────────────────────────

# Columnas: Fecha | Módulo | Acción | Usuario | Entidad | ID Reg | Ver
_C_FECHA  = 0
_C_MODULO = 1
_C_ACCION = 2
_C_USER   = 3
_C_ENT    = 4
_C_ID     = 5
_C_VER    = 6


def _nueva_tabla() -> QTableWidget:
    t = QTableWidget()
    t.setColumnCount(7)
    t.setHorizontalHeaderLabels([
        "Fecha y hora", "Módulo", "Acción", "Usuario", "Entidad", "ID Reg", ""
    ])
    t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(False)
    # Entidad estira
    t.horizontalHeader().setSectionResizeMode(_C_ENT, QHeaderView.ResizeMode.Stretch)
    t.setColumnWidth(_C_FECHA,  148)
    t.setColumnWidth(_C_MODULO, 155)
    t.setColumnWidth(_C_ACCION, 115)   # ancho suficiente para "Actualización"
    t.setColumnWidth(_C_USER,   160)
    t.setColumnWidth(_C_ID,      65)
    t.setColumnWidth(_C_VER,     52)
    t.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return t


# ──────────────────────────────────────────────────────────────────────────────
# TAB PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────

class TabAuditoria(QWidget):
    """
    Widget principal del módulo de Auditoría.
    Embeber en main.py:
        from auditoria_ui import TabAuditoria
        _wrap(TabAuditoria(ejecutor=ejecutor, entidad_id=entidad_id))
    """

    def __init__(self, ejecutor: dict, entidad_id: int, parent=None):
        super().__init__(parent)
        self._ejecutor  = ejecutor
        self._eid       = entidad_id
        self._datos:    list[dict] = []
        self._offset    = 0
        self._total     = 0
        self._filtros:  dict = {}

        self.setStyleSheet(_CSS)
        self._build()
        self._cargar()

    # ── Construcción ──────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16); root.setSpacing(12)

        # Encabezado con tarjetas
        self._header = _HeaderAuditoria(self._ejecutor, self._eid)
        root.addWidget(self._header)
        root.addWidget(_sep())

        # Panel de filtros
        self._filtros_panel = _PanelFiltros(self._ejecutor, self._eid)
        self._filtros_panel.filtros_cambiados.connect(self._on_filtros)
        root.addWidget(self._filtros_panel)

        # Contador de resultados + paginación
        nav_row = QHBoxLayout(); nav_row.setSpacing(8)
        self._lbl_cnt = _lbl("", size=11, color=P["txt2"])
        nav_row.addWidget(self._lbl_cnt, 1)
        self._btn_prev = _btn("← Anterior", "secondary")
        self._btn_prev.setFixedHeight(32)
        self._btn_prev.clicked.connect(self._pagina_ant)
        self._btn_next = _btn("Siguiente →", "secondary")
        self._btn_next.setFixedHeight(32)
        self._btn_next.clicked.connect(self._pagina_sig)
        nav_row.addWidget(self._btn_prev)
        nav_row.addWidget(self._btn_next)
        root.addLayout(nav_row)

        # Tabla principal
        self._tabla = _nueva_tabla()
        self._tabla.doubleClicked.connect(self._on_doble_clic)
        root.addWidget(self._tabla, 1)

        self._actualizar_nav()

    # ── Carga de datos ────────────────────────────────────────────────────────

    def _cargar(self):
        f = self._filtros
        _run_async(
            abk.listar_auditoria,
            self._ejecutor,
            self._eid,
            tabla         = f.get("tabla"),
            operacion     = f.get("operacion"),
            ops_id_filtro = f.get("ops_id_filtro"),
            fecha_desde   = f.get("fecha_desde"),
            fecha_hasta   = f.get("fecha_hasta"),
            texto         = f.get("texto"),
            limite        = abk.LIMITE_UI,
            offset        = self._offset,
            on_done       = self._poblar,
        )

    def _poblar(self, datos):
        if not isinstance(datos, list):
            datos = []
        self._datos = datos
        self._total = datos[0].get("total_count", 0) if datos else 0

        t = self._tabla
        t.setRowCount(0)

        for d in datos:
            r = t.rowCount(); t.insertRow(r)

            op          = d.get("operacion", "")
            tabla_lbl   = abk.TABLA_LABELS.get(d.get("tabla", ""), d.get("tabla", ""))
            ops_nom     = d.get("ops_nombre") or "Sistema"
            entidad_nom = d.get("entidad_nombre") or "—"

            # Columna Fecha
            t.setItem(r, _C_FECHA, _item(d.get("fecha_legible", ""), P["txt2"]))

            # Columna Módulo
            t.setItem(r, _C_MODULO, _item(tabla_lbl))

            # Columna Acción — badge con texto completo como QLabel centrado
            cfg_op = {
                "INSERT": (P["ok"],   "#0D2A1A", "✚  Creación"),
                "UPDATE": (P["warn"], "#2A1F00", "↺  Actualización"),
                "DELETE": (P["err"],  "#2A0909", "✕  Eliminación"),
            }
            op_color, op_bg, op_txt = cfg_op.get(
                op, (P["txt2"], P["card"], op or "—")
            )
            badge_lb = QLabel(op_txt)
            badge_lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge_lb.setStyleSheet(
                f"background:{op_bg};color:{op_color};"
                f"border:1px solid {op_color};border-radius:6px;"
                f"padding:3px 8px;font-size:11px;font-weight:700;"
            )
            badge_w = QWidget(); badge_w.setStyleSheet("background:transparent;")
            bl = QHBoxLayout(badge_w)
            bl.setContentsMargins(3, 2, 3, 2)
            bl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bl.addWidget(badge_lb)
            t.setCellWidget(r, _C_ACCION, badge_w)

            # Columna Usuario
            it_user = _item(ops_nom)
            if str(ops_nom).strip().lower().startswith("maestro"):
                it_user.setForeground(QColor("#D97706"))
            else:
                it_user.setForeground(QColor(P["txt"]))
            t.setItem(r, _C_USER, it_user)

            # Columna Entidad
            t.setItem(r, _C_ENT, _item(entidad_nom))

            # Columna ID registro
            t.setItem(r, _C_ID, _item(d.get("registro_id", "")))

            # Columna Ver detalle
            btn_ver = QPushButton("Ver")
            btn_ver.setFixedSize(46, 28)
            btn_ver.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn_ver.setStyleSheet(
                f"QPushButton{{background:{P['acc_lt']};color:{P['acc_h']};"
                f"border:1px solid {P['acc_h']};border-radius:5px;"
                f"font-size:11px;font-weight:600;}}"
                f"QPushButton:hover{{background:{P['accent']};color:{P['white']};}}"
            )
            btn_ver.clicked.connect(lambda _c, dato=d: self._ver_detalle(dato))
            w_ver = QWidget(); w_ver.setStyleSheet("background:transparent;")
            wl = QHBoxLayout(w_ver)
            wl.setContentsMargins(3, 2, 3, 2)
            wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wl.addWidget(btn_ver)
            t.setCellWidget(r, _C_VER, w_ver)

            # Color de fondo de fila según operación
            fila_bg = {
                "INSERT": P["ins"],
                "UPDATE": P["upd"],
                "DELETE": P["del"],
            }.get(op)
            if fila_bg:
                for col in [_C_FECHA, _C_MODULO, _C_USER, _C_ENT, _C_ID]:
                    it = t.item(r, col)
                    if it:
                        it.setBackground(QColor(fila_bg))

            t.setRowHeight(r, 42)

        self._actualizar_nav()
        self._header.refrescar()

    # ── Acciones ──────────────────────────────────────────────────────────────

    def _ver_detalle(self, dato: dict):
        """Carga el registro completo y muestra el diálogo de detalle."""
        reg = abk.obtener_detalle(self._ejecutor, int(dato["auditoria_id"]))
        if reg:
            DialogDetalle(reg, self).exec()
        else:
            QMessageBox.warning(self, "Error", "No se pudo cargar el detalle.")

    def _on_doble_clic(self, index):
        r = index.row()
        if 0 <= r < len(self._datos):
            self._ver_detalle(self._datos[r])

    # ── Filtros ───────────────────────────────────────────────────────────────

    def _on_filtros(self, f: dict):
        self._filtros = f
        self._offset  = 0
        self._cargar()

    # ── Paginación ────────────────────────────────────────────────────────────

    def _pagina_ant(self):
        if self._offset >= abk.LIMITE_UI:
            self._offset -= abk.LIMITE_UI
            self._cargar()

    def _pagina_sig(self):
        if self._offset + abk.LIMITE_UI < self._total:
            self._offset += abk.LIMITE_UI
            self._cargar()

    def _actualizar_nav(self):
        pag_actual = (self._offset // abk.LIMITE_UI) + 1
        pag_total  = max(1, -(-self._total // abk.LIMITE_UI))   # ceil division
        self._lbl_cnt.setText(
            f"{self._total:,} registros   |   Página {pag_actual} de {pag_total}"
        )
        self._btn_prev.setEnabled(self._offset > 0)
        self._btn_next.setEnabled(self._offset + abk.LIMITE_UI < self._total)
