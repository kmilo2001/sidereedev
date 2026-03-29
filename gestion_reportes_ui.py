# -*- coding: utf-8 -*-
"""
gestion_reportes_ui.py -- Modulo de Reportes SIGES (v2)

4 tipos de reporte en pestanas:
  1. Produccion General   -- todos los eventos del periodo
  2. Facturacion          -- eventos Terminados
  3. Cartera Operativa    -- eventos Pendientes
  4. Estrategico por EPS  -- consolidado por aseguradora

Visibilidad:
  OPS    --> solo sus eventos / sus EPS
  Maestro / Entidad / Admin --> todos

Responsividad:
  >= 960px --> sidebar 220px
  680-960px --> sidebar 56px iconos
  < 680px  --> sidebar oculta + bottom nav
"""
from __future__ import annotations
import sys
from datetime import date
from functools import partial

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem,
    QFrame, QSizePolicy, QScrollArea,
    QMessageBox, QAbstractItemView,
    QButtonGroup, QFileDialog, QStackedWidget,
    QDateEdit,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer, QDate
from PySide6.QtGui import QCursor, QResizeEvent

import gestion_reportes_backend as rep_bk

# ══════════════════════════════════════════════════════════════
# PALETA
# ══════════════════════════════════════════════════════════════
P = {
    "bg":      "#0D1117", "card":    "#161B22", "input":   "#21262D",
    "border":  "#30363D", "focus":   "#388BFD", "accent":  "#2D6ADF",
    "acc_h":   "#388BFD", "acc_lt":  "#1C3A6E",
    "ok":      "#3FB950", "err":     "#F85149", "warn":    "#D29922",
    "txt":     "#E6EDF3", "txt2":    "#8B949E", "muted":   "#484F58",
    "white":   "#FFFFFF", "row_alt": "#0F1419", "row_sel": "#1C3A6E",
}

STYLE = f"""
QMainWindow, QWidget {{
    background-color:{P['bg']}; color:{P['txt']};
    font-family:'Segoe UI','Helvetica Neue',Arial,sans-serif;
    font-size:13px;
}}
QLabel {{ background:transparent; }}
QDialog {{ background-color:{P['bg']}; }}
QTableWidget {{
    background:{P['card']}; border:1px solid {P['border']};
    border-radius:8px; gridline-color:{P['border']};
    color:{P['txt']}; font-size:12px;
    alternate-background-color:{P['row_alt']};
    selection-background-color:{P['row_sel']};
    selection-color:{P['txt']};
}}
QTableWidget::item {{ padding:5px 8px; border:none; }}
QHeaderView::section {{
    background:#0F1419; color:{P['txt2']}; border:none;
    border-right:1px solid {P['border']};
    border-bottom:1px solid {P['border']};
    padding:7px 8px; font-size:11px; font-weight:600;
}}
QLineEdit {{
    background:{P['input']}; border:1.5px solid {P['border']};
    border-radius:7px; padding:8px 12px;
    color:{P['txt']}; font-size:13px;
}}
QLineEdit:focus {{ border-color:{P['focus']}; background:#1C2128; }}
QScrollBar:vertical, QScrollBar:horizontal {{
    background:transparent; width:8px; height:8px;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background:{P['border']}; border-radius:4px; min-height:20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    height:0; width:0;
}}
"""

_CSS_DATE = (
    f"QDateEdit{{background:{P['input']};border:1.5px solid {P['border']};"
    f"border-radius:7px;padding:0 12px;color:{P['txt']};font-size:13px;"
    f"min-height:38px;}}"
    f"QDateEdit:focus{{border-color:{P['focus']};background:#1C2128;}}"
    f"QDateEdit::drop-down{{border:none;width:26px;}}"
    f"QDateEdit::down-arrow{{border-left:5px solid transparent;"
    f"border-right:5px solid transparent;"
    f"border-top:6px solid {P['txt2']};margin-right:8px;}}"
    f"QCalendarWidget{{background:{P['card']};color:{P['txt']};"
    f"border:1.5px solid {P['border']};border-radius:8px;}}"
    f"QCalendarWidget QToolButton{{background:{P['card']};color:{P['txt']};"
    f"border:none;border-radius:5px;padding:4px 8px;"
    f"font-size:13px;font-weight:600;}}"
    f"QCalendarWidget QToolButton:hover{{background:{P['input']};}}"
    f"QCalendarWidget QAbstractItemView:enabled{{background:{P['bg']};"
    f"color:{P['txt']};selection-background-color:{P['accent']};"
    f"selection-color:white;}}"
    f"QCalendarWidget QAbstractItemView:disabled{{color:{P['muted']};}}"
    f"QCalendarWidget QWidget#qt_calendar_navigationbar{{"
    f"background:{P['card']};border-bottom:1px solid {P['border']};"
    f"padding:4px;}}"
)

_ROLES_VER_TODO = {"admin", "maestro", "entidad"}


# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _lbl(txt, size=13, color=None, bold=False, wrap=False):
    lb = QLabel(txt)
    c = color or P["txt"]; w = "600" if bold else "400"
    lb.setStyleSheet(
        f"color:{c};font-size:{size}px;font-weight:{w};background:transparent;"
    )
    if wrap: lb.setWordWrap(True)
    return lb


def _sep():
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(
        f"border:none;border-top:1px solid {P['border']};background:transparent;"
    )
    f.setFixedHeight(1); return f


def _vsep():
    f = QFrame(); f.setFrameShape(QFrame.Shape.VLine)
    f.setStyleSheet(f"background:{P['border']};max-width:1px;")
    return f


def _btn(txt, style="prim", parent=None):
    b = QPushButton(txt, parent)
    S = {
        "prim": (
            f"QPushButton{{background:{P['accent']};color:white;border:none;"
            f"border-radius:7px;padding:9px 20px;font-size:13px;font-weight:600;}}"
            f"QPushButton:hover{{background:{P['acc_h']};}}"
            f"QPushButton:pressed{{background:#1A4FAF;}}"
            f"QPushButton:disabled{{background:{P['muted']};color:{P['bg']};}}"
        ),
        "sec": (
            f"QPushButton{{background:transparent;color:{P['txt2']};"
            f"border:1.5px solid {P['border']};border-radius:7px;"
            f"padding:8px 16px;font-size:13px;font-weight:500;}}"
            f"QPushButton:hover{{border-color:{P['focus']};"
            f"color:{P['txt']};background:{P['input']};}}"
        ),
        "tab": (
            f"QPushButton{{background:transparent;color:{P['txt2']};"
            f"border:none;border-bottom:3px solid transparent;"
            f"padding:8px 16px;font-size:13px;font-weight:500;}}"
            f"QPushButton:hover{{color:{P['txt']};background:{P['input']};"
            f"border-radius:6px;}}"
            f"QPushButton:checked{{color:{P['acc_h']};font-weight:700;"
            f"border-bottom:3px solid {P['accent']};"
            f"background:transparent;border-radius:0;}}"
        ),
        "filtro": (
            f"QPushButton{{background:{P['card']};color:{P['txt2']};"
            f"border:1.5px solid {P['border']};border-radius:6px;"
            f"padding:6px 14px;font-size:12px;font-weight:500;}}"
            f"QPushButton:hover{{border-color:{P['focus']};color:{P['txt']};}}"
            f"QPushButton:checked{{background:{P['acc_lt']};color:{P['acc_h']};"
            f"border-color:{P['accent']};font-weight:700;}}"
        ),
        "xlsx": (
            f"QPushButton{{background:rgba(63,185,80,.15);color:{P['ok']};"
            f"border:1.5px solid {P['ok']};border-radius:7px;"
            f"padding:8px 18px;font-size:13px;font-weight:600;}}"
            f"QPushButton:hover{{background:rgba(63,185,80,.28);}}"
            f"QPushButton:disabled{{opacity:.45;}}"
        ),
        "pdf": (
            f"QPushButton{{background:rgba(248,81,73,.15);color:{P['err']};"
            f"border:1.5px solid {P['err']};border-radius:7px;"
            f"padding:8px 18px;font-size:13px;font-weight:600;}}"
            f"QPushButton:hover{{background:rgba(248,81,73,.28);}}"
            f"QPushButton:disabled{{opacity:.45;}}"
        ),
    }
    b.setStyleSheet(S.get(style, S["prim"]))
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    return b


def _item(txt):
    i = QTableWidgetItem(str(txt) if txt is not None else "")
    i.setFlags(i.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return i


def _make_table(cols: list[str]) -> QTableWidget:
    t = QTableWidget(); t.setColumnCount(len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(True)
    t.setShowGrid(True)
    t.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    t.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    return t


class _Worker(QThread):
    done = Signal(object)
    def __init__(self, fn, args, kw):
        super().__init__()
        self._fn, self._args, self._kw = fn, args, kw
    def run(self):
        try:    self.done.emit(self._fn(*self._args, **self._kw))
        except Exception as e: self.done.emit(rep_bk.Resultado(False, str(e)))

_workers: list = []

def run_async(parent, fn, *args, on_done=None, **kw):
    w = _Worker(fn, args, kw)
    _workers.append(w)
    if on_done: w.done.connect(on_done)
    w.done.connect(lambda _: _workers.remove(w) if w in _workers else None)
    w.start()


def _ops_safe(ops_id) -> int | None:
    if ops_id is None or ops_id == 0 or str(ops_id) == "":
        return None
    return int(ops_id)


# ══════════════════════════════════════════════════════════════
# DATE FIELD
# ══════════════════════════════════════════════════════════════

class DateF(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QWidget{{background:{P['bg']};border:none;}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(4)
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"color:{P['txt2']};font-size:11px;font-weight:600;background:transparent;"
        )
        lay.addWidget(lbl)
        self.de = QDateEdit()
        self.de.setDate(QDate.currentDate())
        self.de.setCalendarPopup(True)
        self.de.setDisplayFormat("dd/MM/yyyy")
        self.de.setMinimumHeight(38)
        self.de.setStyleSheet(_CSS_DATE)
        lay.addWidget(self.de)

    def text(self) -> str:
        return self.de.date().toString("yyyy-MM-dd")

    def set(self, v: str):
        if v:
            d = QDate.fromString(str(v)[:10], "yyyy-MM-dd")
            if d.isValid(): self.de.setDate(d)


# ══════════════════════════════════════════════════════════════
# KPI CARDS (compartido entre pestanas)
# ══════════════════════════════════════════════════════════════

class KpiCards(QWidget):
    def __init__(self, rol: str = "ops", parent=None):
        super().__init__(parent)
        self._rol = rol
        self.setStyleSheet(
            f"background:{P['card']};border:1px solid {P['border']};"
            f"border-radius:10px;"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 14, 20, 14); lay.setSpacing(0)
        self._nums: dict[str, QLabel] = {}

        ver_todo = rol in _ROLES_VER_TODO
        tarjetas = [
            ("total",       "Total eventos"  if ver_todo else "Mis eventos",    P["txt"]),
            ("pendientes",  "Pendientes",     P["warn"]),
            ("terminados",  "Terminados",     P["ok"]),
            ("facturado",   "Total facturado" if ver_todo else "Mi facturado",  P["acc_h"]),
        ]

        for i, (key, etq, color) in enumerate(tarjetas):
            blk = QVBoxLayout()
            n = QLabel("--"); n.setAlignment(Qt.AlignmentFlag.AlignCenter)
            n.setStyleSheet(
                f"color:{color};font-size:22px;font-weight:700;background:transparent;"
            )
            lb = QLabel(etq); lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lb.setStyleSheet(
                f"color:{P['txt2']};font-size:11px;background:transparent;"
            )
            blk.addWidget(n); blk.addWidget(lb)
            lay.addLayout(blk); self._nums[key] = n
            if i < len(tarjetas) - 1:
                sv = QFrame(); sv.setFrameShape(QFrame.Shape.VLine)
                sv.setStyleSheet(f"background:{P['border']};max-width:1px;")
                lay.addWidget(sv)

    def actualizar(self, r: dict):
        tot  = int(r.get("total_eventos")    or 0)
        pend = int(r.get("eventos_pendientes") or 0)
        term = int(r.get("eventos_terminados") or 0)
        fact = float(r.get("total_facturado")  or 0)
        if "total"      in self._nums: self._nums["total"].setText(str(tot))
        if "pendientes" in self._nums: self._nums["pendientes"].setText(str(pend))
        if "terminados" in self._nums: self._nums["terminados"].setText(str(term))
        if "facturado"  in self._nums: self._nums["facturado"].setText(f"${fact:,.0f}")


# ══════════════════════════════════════════════════════════════
# PANEL DE FILTROS (reutilizable por cada pestana)
# ══════════════════════════════════════════════════════════════

class PanelFiltros(QWidget):
    """
    Filtros de periodo compartidos.
    Emite: periodo_cambiado(desde, hasta) al aplicar un filtro.
    """
    periodo_cambiado = Signal(object, object)  # (str|None, str|None)

    _PERIODOS = [
        ("hoy",    "Hoy"),
        ("semana", "Esta semana"),
        ("mes",    "Este mes"),
        ("todos",  "Todos"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background:{P['card']};border:1px solid {P['border']};"
            f"border-radius:10px;"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12); lay.setSpacing(10)

        lay.addWidget(_lbl("Filtro de periodo", 12, P["txt2"], bold=True))

        # Botones rapidos
        fscroll = QScrollArea()
        fscroll.setWidgetResizable(True); fscroll.setFixedHeight(40)
        fscroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        fscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        fscroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            f"QScrollBar:horizontal{{background:transparent;height:4px;}}"
            f"QScrollBar::handle:horizontal{{background:{P['border']};border-radius:2px;}}"
        )
        fi = QWidget(); fi.setStyleSheet("background:transparent;")
        fl = QHBoxLayout(fi); fl.setContentsMargins(0, 0, 0, 0); fl.setSpacing(6)

        self._bg_per = QButtonGroup(self)
        for pid, ptq in self._PERIODOS:
            b = _btn(ptq, "filtro"); b.setCheckable(True)
            b.setProperty("periodo", pid)
            self._bg_per.addButton(b); fl.addWidget(b)
            if pid == "mes": b.setChecked(True)
        self._bg_per.buttonClicked.connect(
            lambda btn: self._on_periodo(btn.property("periodo"))
        )
        fl.addStretch()
        fscroll.setWidget(fi); lay.addWidget(fscroll)

        # Rango personalizado
        rw = QWidget(); rw.setStyleSheet("background:transparent;")
        rl = QHBoxLayout(rw); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(10)
        self.f_desde = DateF("Desde")
        self.f_hasta = DateF("Hasta")
        self.f_hasta.set(str(date.today()))
        b_ap = _btn("Aplicar rango", "sec"); b_ap.setMinimumHeight(38)
        b_ap.clicked.connect(self._on_rango)
        rl.addWidget(self.f_desde, 1); rl.addWidget(self.f_hasta, 1)
        rl.addWidget(b_ap); rl.addStretch()
        lay.addWidget(rw)

        # Etiqueta periodo activo
        self._lbl_activo = _lbl("Periodo activo: Este mes", 11, P["acc_h"])
        lay.addWidget(self._lbl_activo)

    def _on_periodo(self, pid: str):
        fd, fh = rep_bk.fechas_filtro(pid)
        nombres = {"hoy": "Hoy", "semana": "Esta semana",
                   "mes": "Este mes", "todos": "Todos"}
        self._lbl_activo.setText(f"Periodo activo: {nombres.get(pid, pid)}")
        if fd: self.f_desde.set(fd)
        if fh: self.f_hasta.set(fh)
        self.periodo_cambiado.emit(fd, fh)

    def _on_rango(self):
        d = self.f_desde.text(); h = self.f_hasta.text()
        self._lbl_activo.setText(f"Rango personalizado: {d}  a  {h}")
        self._bg_per.setExclusive(False)
        for b in self._bg_per.buttons(): b.setChecked(False)
        self._bg_per.setExclusive(True)
        self.periodo_cambiado.emit(d or None, h or None)

    def aplicar_inicial(self, periodo: str = "mes"):
        """Dispara el periodo inicial sin interaccion del usuario."""
        for b in self._bg_per.buttons():
            if b.property("periodo") == periodo:
                b.setChecked(True)
                break
        self._on_periodo(periodo)


# ══════════════════════════════════════════════════════════════
# PESTANA BASE (logica comun de carga + exportacion)
# ══════════════════════════════════════════════════════════════

class _PestanaBase(QWidget):
    """
    Clase base para las 4 pestanas de reporte.
    Subclases deben implementar:
      - _columnas_tabla()  -> list[str]
      - _poblar_fila(tabla, r, d)
      - _fn_backend()      -> callable
      - _tipo_reporte()    -> str  ('produccion'|'facturacion'|'cartera'|'eps')
      - _ajustar_cols()
    """

    def __init__(self, rol: str, entidad_id: int, ops_id,
                 ops_nombre: str, parent=None):
        super().__init__(parent)
        self._rol      = rol
        self._eid      = entidad_id
        self._oid      = _ops_safe(ops_id)
        self._ops_nom  = ops_nombre
        self._ver_todo = rol in _ROLES_VER_TODO
        self._f_desde: str | None = None
        self._f_hasta: str | None = None
        self._datos: list[dict] = []
        self._entidad: dict = {}
        self._build_base()

    def _build_base(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 0); root.setSpacing(8)

        # Tabla
        self.tabla = _make_table(self._columnas_tabla())
        root.addWidget(self.tabla, 1)

        # Pie: contadores + botones exportar
        pie = QWidget(); pie.setStyleSheet("background:transparent;")
        pl = QHBoxLayout(pie)
        pl.setContentsMargins(0, 4, 0, 0); pl.setSpacing(12)
        self._lbl_cnt  = _lbl("", 12, P["txt2"])
        self._lbl_fact = _lbl("", 13, P["ok"], bold=True)
        self._lbl_fact.setVisible(self._ver_todo or
                                  self._tipo_reporte() in ("facturacion",))
        pl.addStretch()
        pl.addWidget(self._lbl_cnt); pl.addWidget(self._lbl_fact)
        pl.addWidget(_vsep())
        self.btn_xlsx = _btn("Excel", "xlsx")
        self.btn_pdf  = _btn("PDF",   "pdf")
        self.btn_xlsx.setEnabled(False); self.btn_pdf.setEnabled(False)
        self.btn_xlsx.clicked.connect(self._exportar_xlsx)
        self.btn_pdf.clicked.connect(self._exportar_pdf)
        pl.addWidget(self.btn_xlsx); pl.addWidget(self.btn_pdf)
        root.addWidget(pie)

    # -- Metodos a implementar en subclase --

    def _columnas_tabla(self) -> list[str]:
        raise NotImplementedError

    def _poblar_fila(self, r: int, d: dict):
        raise NotImplementedError

    def _fn_backend(self):
        raise NotImplementedError

    def _tipo_reporte(self) -> str:
        raise NotImplementedError

    def _ajustar_cols(self):
        pass

    # -- Carga --

    def cargar(self, fecha_desde: str | None, fecha_hasta: str | None,
               entidad: dict):
        self._f_desde  = fecha_desde
        self._f_hasta  = fecha_hasta
        self._entidad  = entidad
        self.btn_xlsx.setEnabled(False)
        self.btn_pdf.setEnabled(False)
        self._lbl_cnt.setText("Cargando...")

        def _done(r):
            if isinstance(r, rep_bk.Resultado):
                self._lbl_cnt.setText(f"Error: {r.mensaje}")
                self._lbl_cnt.setStyleSheet(f"color:{P['err']};font-size:12px;")
                return
            datos = r if isinstance(r, list) else []
            self._datos = datos
            self._poblar(datos)
            habilitado = len(datos) > 0
            self.btn_xlsx.setEnabled(habilitado)
            self.btn_pdf.setEnabled(habilitado)

        run_async(
            self, self._fn_backend(),
            self._eid, self._rol, self._oid,
            self._f_desde, self._f_hasta,
            on_done=_done
        )

    def _poblar(self, datos: list[dict]):
        self.tabla.setRowCount(0)
        self._lbl_cnt.setStyleSheet(f"color:{P['txt2']};font-size:12px;")
        total_f = 0.0
        for d in datos:
            r = self.tabla.rowCount(); self.tabla.insertRow(r)
            self._poblar_fila(r, d)
            total_f += float(d.get("valor") or d.get("total_facturado") or 0)
            self.tabla.setRowHeight(r, 42)
        self._lbl_cnt.setText(f"Total: {len(datos)} registro(s)")
        if self._lbl_fact.isVisible():
            self._lbl_fact.setText(f"Facturado: ${total_f:,.0f}")
        QTimer.singleShot(0, self._ajustar_cols)

    # -- Exportacion --

    def _exportar_xlsx(self):
        if not self._datos:
            QMessageBox.information(self, "", "No hay datos para exportar."); return
        hoy = date.today().isoformat()
        tipo = self._tipo_reporte()
        ruta, _ = QFileDialog.getSaveFileName(
            self.window(), "Guardar Excel",
            f"reporte_{tipo}_{hoy}.xlsx", "Excel (*.xlsx)"
        )
        if not ruta: return
        self.btn_xlsx.setEnabled(False); self.btn_xlsx.setText("Generando...")

        def _done(res: rep_bk.Resultado):
            self.btn_xlsx.setEnabled(True); self.btn_xlsx.setText("Excel")
            if res.ok:
                _dlg_ok(self.window(), f"Excel guardado:\n{ruta}")
            else:
                QMessageBox.critical(self.window(), "Error", res.mensaje)

        run_async(
            self, rep_bk.exportar_excel,
            self._datos, self._entidad, ruta, tipo,
            self._f_desde, self._f_hasta,
            self._ops_nom if not self._ver_todo else None,
            on_done=_done
        )

    def _exportar_pdf(self):
        if not self._datos:
            QMessageBox.information(self, "", "No hay datos para exportar."); return
        hoy = date.today().isoformat()
        tipo = self._tipo_reporte()
        ruta, _ = QFileDialog.getSaveFileName(
            self.window(), "Guardar PDF",
            f"reporte_{tipo}_{hoy}.pdf", "PDF (*.pdf)"
        )
        if not ruta: return
        self.btn_pdf.setEnabled(False); self.btn_pdf.setText("Generando...")

        def _done(res: rep_bk.Resultado):
            self.btn_pdf.setEnabled(True); self.btn_pdf.setText("PDF")
            if res.ok:
                _dlg_ok(self.window(), f"PDF guardado:\n{ruta}")
            else:
                QMessageBox.critical(self.window(), "Error", res.mensaje)

        run_async(
            self, rep_bk.exportar_pdf,
            self._datos, self._entidad, ruta, tipo,
            self._f_desde, self._f_hasta,
            self._ops_nom if not self._ver_todo else None,
            on_done=_done
        )


def _dlg_ok(parent, msg: str):
    dlg = QDialog(parent)
    dlg.setWindowTitle("Exportacion exitosa")
    dlg.setModal(True)
    dlg.setStyleSheet(f"QDialog{{background:{P['bg']};}}")
    lay = QVBoxLayout(dlg); lay.setContentsMargins(28, 24, 28, 24); lay.setSpacing(14)
    ico = QLabel("OK"); ico.setStyleSheet(
        f"font-size:32px;background:transparent;color:{P['ok']};"
    ); ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
    txt = QLabel(msg); txt.setWordWrap(True)
    txt.setStyleSheet(f"color:{P['txt']};font-size:13px;background:transparent;")
    txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
    bc = _btn("Cerrar", "sec"); bc.clicked.connect(dlg.accept)
    lay.addWidget(ico); lay.addWidget(txt); lay.addWidget(bc)
    dlg.resize(400, 200); dlg.exec()


# ══════════════════════════════════════════════════════════════
# PESTANA 1: PRODUCCION GENERAL
# ══════════════════════════════════════════════════════════════

class PestanaProduccion(_PestanaBase):
    """
    Todos los eventos del periodo.
    OPS: sus eventos. Maestro/Admin: todos.
    Columnas: Paciente | TipoID | NID | EPS | Afiliacion | Motivo |
              NAdmision | CodEvento | NFactura | Valor | Estado | Fecha | Ops
    """
    _COLS = [
        "Paciente", "Tipo ID", "N Identificacion",
        "EPS", "Tipo afiliacion", "Motivo",
        "N Admision", "Cod Evento", "N Factura",
        "Valor", "Estado", "Fecha", "Registrado por",
    ]

    def _columnas_tabla(self): return self._COLS
    def _tipo_reporte(self):   return "produccion"
    def _fn_backend(self):     return rep_bk.reporte_produccion

    def _poblar_fila(self, r: int, d: dict):
        t = self.tabla
        motivo = str(d.get("motivo_evento") or "")
        t.setItem(r, 0, _item(d.get("nombre_paciente", "")))
        t.setItem(r, 1, _item(d.get("tipo_identificacion", "")))
        t.setItem(r, 2, _item(d.get("numero_identificacion", "")))
        t.setItem(r, 3, _item(d.get("eps", "") or "--"))
        t.setItem(r, 4, _item(d.get("tipo_afiliacion", "") or "--"))
        t.setItem(r, 5, _item(motivo[:48] + ("..." if len(motivo) > 48 else "")))
        t.setItem(r, 6, _item(d.get("numero_admision", "") or "--"))
        t.setItem(r, 7, _item(d.get("codigo_evento", "") or "--"))
        t.setItem(r, 8, _item(d.get("numero_factura", "") or "--"))
        val = float(d.get("valor") or 0)
        t.setItem(r, 9,  _item(f"${val:,.0f}" if self._ver_todo else "--"))
        t.setItem(r, 10, _item(d.get("estado_evento", "")))
        t.setItem(r, 11, _item(str(d.get("fecha_evento", ""))[:10]))
        t.setItem(r, 12, _item(d.get("registrado_por", "") or "Admin"))

    def _ajustar_cols(self):
        t = self.tabla; vw = t.viewport().width()
        fijos = 70 + 110 + 100 + 100 + 90 + 90 + 90 + 65 + 80 + 110
        resto = max(120, vw - fijos)
        t.setColumnWidth(1,  70)   # Tipo ID
        t.setColumnWidth(2, 110)   # N ID
        t.setColumnWidth(3, 100)   # EPS
        t.setColumnWidth(4, 100)   # Afiliacion
        t.setColumnWidth(6,  90)   # N Admision
        t.setColumnWidth(7,  90)   # Cod Evento
        t.setColumnWidth(8,  90)   # N Factura
        t.setColumnWidth(9,  65)   # Valor
        t.setColumnWidth(10, 80)   # Estado
        t.setColumnWidth(11, 90)   # Fecha
        t.setColumnWidth(12, 110)  # Ops
        t.setColumnWidth(0, int(resto * 0.55))  # Paciente
        t.setColumnWidth(5, int(resto * 0.45))  # Motivo

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not hasattr(self, "_rt"):
            self._rt = QTimer(self); self._rt.setSingleShot(True)
            self._rt.timeout.connect(self._ajustar_cols)
        self._rt.start(50)


# ══════════════════════════════════════════════════════════════
# PESTANA 2: FACTURACION / EVENTOS TERMINADOS
# ══════════════════════════════════════════════════════════════

class PestanaFacturacion(_PestanaBase):
    """
    Solo eventos Terminados.
    Columnas: Paciente | TipoID | NID | EPS | Afiliacion |
              NAdmision | CodEvento | NFactura | Valor | Fecha | Ops
    """
    _COLS = [
        "Paciente", "Tipo ID", "N Identificacion",
        "EPS", "Tipo afiliacion",
        "N Admision", "Cod Evento", "N Factura",
        "Valor", "Fecha", "Registrado por",
    ]

    def _columnas_tabla(self): return self._COLS
    def _tipo_reporte(self):   return "facturacion"
    def _fn_backend(self):     return rep_bk.reporte_facturacion

    def _poblar_fila(self, r: int, d: dict):
        t = self.tabla
        t.setItem(r, 0, _item(d.get("nombre_paciente", "")))
        t.setItem(r, 1, _item(d.get("tipo_identificacion", "")))
        t.setItem(r, 2, _item(d.get("numero_identificacion", "")))
        t.setItem(r, 3, _item(d.get("eps", "") or "--"))
        t.setItem(r, 4, _item(d.get("tipo_afiliacion", "") or "--"))
        t.setItem(r, 5, _item(d.get("numero_admision", "") or "--"))
        t.setItem(r, 6, _item(d.get("codigo_evento", "") or "--"))
        t.setItem(r, 7, _item(d.get("numero_factura", "") or "--"))
        val = float(d.get("valor") or 0)
        t.setItem(r, 8,  _item(f"${val:,.0f}"))
        t.setItem(r, 9,  _item(str(d.get("fecha_evento", ""))[:10]))
        t.setItem(r, 10, _item(d.get("registrado_por", "") or "Admin"))

    def _ajustar_cols(self):
        t = self.tabla; vw = t.viewport().width()
        fijos = 70 + 110 + 100 + 100 + 90 + 90 + 95 + 70 + 85 + 110
        resto = max(150, vw - fijos)
        t.setColumnWidth(0, int(resto)); t.setColumnWidth(1,  70)
        t.setColumnWidth(2, 110); t.setColumnWidth(3, 100)
        t.setColumnWidth(4, 100); t.setColumnWidth(5,  90)
        t.setColumnWidth(6,  90); t.setColumnWidth(7,  95)
        t.setColumnWidth(8,  70); t.setColumnWidth(9,  85)
        t.setColumnWidth(10, 110)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not hasattr(self, "_rt"):
            self._rt = QTimer(self); self._rt.setSingleShot(True)
            self._rt.timeout.connect(self._ajustar_cols)
        self._rt.start(50)


# ══════════════════════════════════════════════════════════════
# PESTANA 3: CARTERA OPERATIVA / PENDIENTES
# ══════════════════════════════════════════════════════════════

class PestanaCartera(_PestanaBase):
    """
    Solo eventos Pendientes. Ordenados por dias transcurridos (mas urgentes primero).
    Columnas: Paciente | TipoID | NID | EPS | Afiliacion |
              Motivo | NAdmision | Dias | Fecha | Ops
    """
    _COLS = [
        "Paciente", "Tipo ID", "N Identificacion",
        "EPS", "Tipo afiliacion", "Motivo",
        "N Admision", "Dias transcurridos", "Fecha", "Registrado por",
    ]

    def _columnas_tabla(self): return self._COLS
    def _tipo_reporte(self):   return "cartera"
    def _fn_backend(self):     return rep_bk.reporte_cartera

    def _poblar_fila(self, r: int, d: dict):
        t = self.tabla
        motivo = str(d.get("motivo_evento") or "")
        dias = int(d.get("dias_transcurridos") or 0)
        t.setItem(r, 0, _item(d.get("nombre_paciente", "")))
        t.setItem(r, 1, _item(d.get("tipo_identificacion", "")))
        t.setItem(r, 2, _item(d.get("numero_identificacion", "")))
        t.setItem(r, 3, _item(d.get("eps", "") or "--"))
        t.setItem(r, 4, _item(d.get("tipo_afiliacion", "") or "--"))
        t.setItem(r, 5, _item(motivo[:48] + ("..." if len(motivo) > 48 else "")))
        t.setItem(r, 6, _item(d.get("numero_admision", "") or "--"))

        # Colorear segun urgencia
        dias_item = _item(f"{dias} dias")
        if dias > 30:
            dias_item.setForeground(__import__(
                "PySide6.QtGui", fromlist=["QColor"]
            ).QColor(P["err"]))
        elif dias > 15:
            dias_item.setForeground(__import__(
                "PySide6.QtGui", fromlist=["QColor"]
            ).QColor(P["warn"]))
        t.setItem(r, 7, dias_item)
        t.setItem(r, 8, _item(str(d.get("fecha_evento", ""))[:10]))
        t.setItem(r, 9, _item(d.get("registrado_por", "") or "Admin"))

    def _ajustar_cols(self):
        t = self.tabla; vw = t.viewport().width()
        fijos = 70 + 110 + 100 + 100 + 90 + 90 + 85 + 110
        resto = max(150, vw - fijos)
        t.setColumnWidth(0, int(resto * 0.55))
        t.setColumnWidth(1,  70); t.setColumnWidth(2, 110)
        t.setColumnWidth(3, 100); t.setColumnWidth(4, 100)
        t.setColumnWidth(5, int(resto * 0.45))
        t.setColumnWidth(6,  90); t.setColumnWidth(7,  90)
        t.setColumnWidth(8,  85); t.setColumnWidth(9, 110)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not hasattr(self, "_rt"):
            self._rt = QTimer(self); self._rt.setSingleShot(True)
            self._rt.timeout.connect(self._ajustar_cols)
        self._rt.start(50)


# ══════════════════════════════════════════════════════════════
# PESTANA 4: ESTRATEGICO POR EPS
# ══════════════════════════════════════════════════════════════

class PestanaEPS(_PestanaBase):
    """
    Consolidado por EPS.
    Columnas: EPS | Total eventos | Total facturado | Con contrato |
              Sin contrato | Pendientes | Terminados | % Participacion
    """
    _COLS = [
        "EPS", "Total eventos", "Total facturado ($)",
        "Con contrato", "Sin contrato",
        "Pendientes", "Terminados", "% Participacion",
    ]

    def _columnas_tabla(self): return self._COLS
    def _tipo_reporte(self):   return "eps"
    def _fn_backend(self):     return rep_bk.reporte_eps

    def _poblar_fila(self, r: int, d: dict):
        t = self.tabla
        t.setItem(r, 0, _item(d.get("eps", "--")))
        t.setItem(r, 1, _item(str(int(d.get("total_eventos") or 0))))
        val = float(d.get("total_facturado") or 0)
        t.setItem(r, 2, _item(f"${val:,.0f}"))
        t.setItem(r, 3, _item(str(int(d.get("eventos_con_contrato") or 0))))
        sin_c = int(d.get("eventos_sin_contrato") or 0)
        sin_item = _item(str(sin_c))
        if sin_c > 0:
            sin_item.setForeground(__import__(
                "PySide6.QtGui", fromlist=["QColor"]
            ).QColor(P["warn"]))
        t.setItem(r, 4, sin_item)
        t.setItem(r, 5, _item(str(int(d.get("pendientes") or 0))))
        t.setItem(r, 6, _item(str(int(d.get("terminados") or 0))))
        pct = float(d.get("pct_participacion") or 0)
        t.setItem(r, 7, _item(f"{pct:.1f}%"))

    def _ajustar_cols(self):
        t = self.tabla; vw = t.viewport().width()
        fijos = 100 + 120 + 100 + 100 + 90 + 90 + 110
        resto = max(180, vw - fijos)
        t.setColumnWidth(0, int(resto))  # EPS
        t.setColumnWidth(1, 100); t.setColumnWidth(2, 120)
        t.setColumnWidth(3, 100); t.setColumnWidth(4, 100)
        t.setColumnWidth(5,  90); t.setColumnWidth(6,  90)
        t.setColumnWidth(7, 110)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not hasattr(self, "_rt"):
            self._rt = QTimer(self); self._rt.setSingleShot(True)
            self._rt.timeout.connect(self._ajustar_cols)
        self._rt.start(50)

    # El reporte EPS no tiene columna "valor" directa — sobreescribir _poblar
    def _poblar(self, datos: list[dict]):
        self.tabla.setRowCount(0)
        self._lbl_cnt.setStyleSheet(f"color:{P['txt2']};font-size:12px;")
        total_val = 0.0
        for d in datos:
            r = self.tabla.rowCount(); self.tabla.insertRow(r)
            self._poblar_fila(r, d)
            total_val += float(d.get("total_facturado") or 0)
            self.tabla.setRowHeight(r, 42)
        self._lbl_cnt.setText(f"EPS registradas: {len(datos)}")
        if self._lbl_fact.isVisible():
            self._lbl_fact.setText(f"Total facturado: ${total_val:,.0f}")
        QTimer.singleShot(0, self._ajustar_cols)


# ══════════════════════════════════════════════════════════════
# TAB PRINCIPAL DE REPORTES
# ══════════════════════════════════════════════════════════════

class TabReportes(QWidget):
    def __init__(self, rol: str, entidad_id: int, ops_id,
                 ops_nombre: str = "", parent=None):
        super().__init__(parent)
        self._rol      = rol
        self._eid      = entidad_id
        self._oid      = _ops_safe(ops_id)
        self._ops_nom  = ops_nombre
        self._ver_todo = rol in _ROLES_VER_TODO
        self._entidad: dict = {}
        self._f_desde: str | None = None
        self._f_hasta: str | None = None

        self._build()
        QTimer.singleShot(0, self._cargar_entidad)
        QTimer.singleShot(80, lambda: self._filtros.aplicar_inicial("mes"))

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 12); root.setSpacing(10)

        # Titulo
        tit_w = QWidget(); tit_w.setStyleSheet("background:transparent;")
        tl = QHBoxLayout(tit_w)
        tl.setContentsMargins(0, 0, 0, 0); tl.setSpacing(10)
        ico = QLabel("Reportes SIGES")
        ico.setStyleSheet(
            f"color:{P['txt']};font-size:20px;font-weight:700;background:transparent;"
        )
        sub = _lbl(
            "Todos los eventos de la entidad" if self._ver_todo
            else "Solo tus eventos",
            12, P["txt2"]
        )
        tl.addWidget(ico); tl.addWidget(sub); tl.addStretch()
        root.addWidget(tit_w)

        # KPIs
        self._kpi = KpiCards(rol=self._rol)
        root.addWidget(self._kpi)

        # Panel de filtros (compartido)
        self._filtros = PanelFiltros()
        self._filtros.periodo_cambiado.connect(self._on_periodo_cambiado)
        root.addWidget(self._filtros)

        # Barra de pestanas
        tabs_bar = QWidget(); tabs_bar.setStyleSheet("background:transparent;")
        tb = QHBoxLayout(tabs_bar)
        tb.setContentsMargins(0, 0, 0, 0); tb.setSpacing(0)

        self._tab_btns = QButtonGroup(self)
        self._tab_btns.setExclusive(True)
        _TABS_DEF = [
            (0, "Produccion general"),
            (1, "Facturacion"),
            (2, "Cartera pendiente"),
            (3, "Por EPS"),
        ]
        for idx, nombre in _TABS_DEF:
            b = _btn(nombre, "tab"); b.setCheckable(True)
            self._tab_btns.addButton(b, idx); tb.addWidget(b)
            if idx == 0: b.setChecked(True)
        tb.addStretch()
        root.addWidget(tabs_bar)
        root.addWidget(_sep())

        # Stack de pestanas
        self._stack = QStackedWidget()
        kw = dict(rol=self._rol, entidad_id=self._eid,
                  ops_id=self._oid, ops_nombre=self._ops_nom)
        self._p_prod  = PestanaProduccion(**kw)
        self._p_fact  = PestanaFacturacion(**kw)
        self._p_cart  = PestanaCartera(**kw)
        self._p_eps   = PestanaEPS(**kw)
        for p in (self._p_prod, self._p_fact, self._p_cart, self._p_eps):
            self._stack.addWidget(p)
        root.addWidget(self._stack, 1)

        self._tab_btns.idClicked.connect(self._cambiar_tab)

    # -- Slots --

    def _cambiar_tab(self, idx: int):
        self._stack.setCurrentIndex(idx)
        # Recargar la pestana activa con el periodo actual
        self._cargar_tab_actual()

    def _on_periodo_cambiado(self, fd, fh):
        self._f_desde = fd; self._f_hasta = fh
        self._cargar_kpis()
        self._cargar_tab_actual()

    def _cargar_kpis(self):
        def _done(r):
            if isinstance(r, dict): self._kpi.actualizar(r)
        run_async(
            self, rep_bk.obtener_resumen,
            self._eid, self._rol, self._oid,
            self._f_desde, self._f_hasta,
            on_done=_done
        )

    def _cargar_tab_actual(self):
        idx = self._stack.currentIndex()
        pestana = self._stack.widget(idx)
        if isinstance(pestana, _PestanaBase):
            pestana.cargar(self._f_desde, self._f_hasta, self._entidad)

    def _cargar_entidad(self):
        def _done(r):
            if isinstance(r, dict):
                self._entidad = r
        run_async(self, rep_bk.obtener_datos_entidad, self._eid, on_done=_done)

    def _ajustar_cols(self):
        p = self._stack.currentWidget()
        if hasattr(p, "_ajustar_cols"):
            p._ajustar_cols()

    def resizeEvent(self, e: QResizeEvent):
        super().resizeEvent(e)
        if not hasattr(self, "_resize_timer"):
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._ajustar_cols)
        self._resize_timer.start(50)


# ══════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════

class _NavBtn(QPushButton):
    def __init__(self, ico, lbl, parent=None):
        super().__init__(parent)
        self._ico = ico; self._lbl = lbl
        self._act = False; self._exp = True
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(46); self._render()

    def set_activo(self, v): self._act = v; self._render()
    def set_exp(self, v):
        self._exp = v; self.setFixedWidth(220 if v else 56); self._render()

    def _render(self):
        if self._act:
            bg = P["acc_lt"]; c = P["acc_h"]
            bord = f"border-left:3px solid {P['accent']};"; fw = "600"
        else:
            bg = "transparent"; c = P["txt2"]
            bord = "border-left:3px solid transparent;"; fw = "400"
        txt = (f"   {self._ico}   {self._lbl}" if self._exp else f"  {self._ico}")
        self.setText(txt)
        self.setStyleSheet(
            f"QPushButton{{background:{bg};color:{c};border:none;{bord}"
            f"border-radius:0;padding:0 12px;font-size:13px;"
            f"font-weight:{fw};text-align:left;}}"
            f"QPushButton:hover{{background:{P['input']};color:{P['txt']};}}"
        )


class Sidebar(QWidget):
    nav = Signal(int)

    _ROL_LABELS = {
        "ops":     "OPS",
        "maestro": "Maestro",
        "entidad": "Entidad",
        "admin":   "Administrador",
    }

    def __init__(self, nombre: str, rol: str, parent=None):
        super().__init__(parent)
        self._exp = True; self._btns: list[_NavBtn] = []
        self.setFixedWidth(220)
        self.setStyleSheet(
            f"QWidget{{background:{P['card']};"
            f"border-right:1px solid {P['border']};}}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        hdr = QWidget(); hdr.setFixedHeight(64)
        hdr.setStyleSheet(
            f"background:{P['card']};border-bottom:1px solid {P['border']};"
        )
        hl = QHBoxLayout(hdr); hl.setContentsMargins(16, 0, 10, 0); hl.setSpacing(10)
        ic = QLabel("S"); ic.setFixedSize(32, 32)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setStyleSheet(
            f"background:{P['accent']};color:white;border-radius:8px;"
            f"font-size:16px;font-weight:700;"
        )
        self._logo = QLabel("SIGES")
        self._logo.setStyleSheet(
            f"color:{P['white']};font-size:14px;font-weight:700;background:transparent;"
        )
        self._tog = QPushButton("◀"); self._tog.setFixedSize(28, 28)
        self._tog.setStyleSheet(
            f"QPushButton{{background:{P['input']};color:{P['txt2']};"
            f"border:1px solid {P['border']};border-radius:6px;font-size:12px;}}"
            f"QPushButton:hover{{background:{P['border']};color:{P['txt']};}}"
        )
        self._tog.clicked.connect(self.toggle)
        hl.addWidget(ic); hl.addWidget(self._logo, 1); hl.addWidget(self._tog)
        root.addWidget(hdr)

        sec = QWidget(); sec.setStyleSheet("background:transparent;border:none;")
        sl = QVBoxLayout(sec); sl.setContentsMargins(0, 16, 0, 8); sl.setSpacing(2)
        self._sec_lbl = QLabel("  MODULO")
        self._sec_lbl.setStyleSheet(
            f"color:{P['muted']};font-size:10px;font-weight:700;"
            f"letter-spacing:1.5px;padding:0 16px 8px;background:transparent;"
        )
        sl.addWidget(self._sec_lbl)
        b = _NavBtn("R", "Reportes"); b.setFixedWidth(220); b.set_activo(True)
        b.clicked.connect(lambda: self.nav.emit(0))
        self._btns.append(b); sl.addWidget(b)
        root.addWidget(sec); root.addStretch()

        pie = QWidget(); pie.setFixedHeight(64)
        pie.setStyleSheet(
            f"background:{P['card']};border-top:1px solid {P['border']};"
        )
        pl = QVBoxLayout(pie); pl.setContentsMargins(16, 10, 16, 10); pl.setSpacing(2)
        self._pie_nom = QLabel(nombre[:26])
        self._pie_nom.setStyleSheet(
            f"color:{P['txt']};font-size:12px;font-weight:700;background:transparent;"
        )
        rol_label = self._ROL_LABELS.get(rol.lower(), rol.upper())
        self._pie_rol = QLabel(rol_label)
        self._pie_rol.setStyleSheet(
            f"color:{P['acc_h']};font-size:10px;background:transparent;"
        )
        pl.addWidget(self._pie_nom); pl.addWidget(self._pie_rol)
        root.addWidget(pie)

    def toggle(self):
        self._exp = not self._exp
        self.setFixedWidth(220 if self._exp else 56)
        self._tog.setText("◀" if self._exp else "▶")
        self._logo.setVisible(self._exp)
        self._sec_lbl.setVisible(self._exp)
        self._pie_nom.setVisible(self._exp)
        self._pie_rol.setVisible(self._exp)
        for b in self._btns: b.set_exp(self._exp)

    def colapsar(self):
        if self._exp: self.toggle()

    def expandir(self):
        if not self._exp: self.toggle()


class BottomNav(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(58)
        self.setStyleSheet(
            f"QWidget{{background:{P['card']};border-top:1px solid {P['border']};}}"
        )
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        b = QPushButton("R\nReportes"); b.setCheckable(True); b.setChecked(True)
        b.setStyleSheet(
            f"QPushButton{{background:{P['card']};color:{P['acc_h']};"
            f"border:none;border-top:2px solid {P['accent']};"
            f"padding:4px 2px;font-size:11px;font-weight:700;}}"
        )
        b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay.addWidget(b)


class TopBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent); self.setFixedHeight(56)
        self.setStyleSheet(
            f"QWidget{{background:{P['card']};border-bottom:1px solid {P['border']};}}"
        )
        lay = QHBoxLayout(self); lay.setContentsMargins(24, 0, 24, 0); lay.setSpacing(8)
        r = QLabel("Gestion"); r.setStyleSheet(
            f"color:{P['txt2']};font-size:12px;background:transparent;"
        )
        s = QLabel(" / "); s.setStyleSheet(
            f"color:{P['muted']};font-size:12px;background:transparent;"
        )
        t = QLabel("Reportes"); t.setStyleSheet(
            f"color:{P['txt']};font-size:15px;font-weight:700;background:transparent;"
        )
        lay.addWidget(r); lay.addWidget(s); lay.addWidget(t); lay.addStretch()
        self._dim = QLabel(""); self._dim.setStyleSheet(
            f"color:{P['muted']};font-size:11px;background:transparent;"
        )
        lay.addWidget(self._dim)

    def set_dim(self, w, h): self._dim.setText(f"{w}x{h}")


# ══════════════════════════════════════════════════════════════
# VENTANA PRINCIPAL
# ══════════════════════════════════════════════════════════════

class ReportesWindow(QMainWindow):
    """
    Ventana standalone del modulo de reportes.

    Uso:
        win = ReportesWindow(
            rol='maestro', entidad_id=1,
            ops_id=None, nombre_usuario='Maria Lopez',
            ops_nombre='Maria Lopez'
        )
        win.show()
    """
    _BP_COLLAPSE = 960
    _BP_BOTTOM   = 680

    def __init__(self, rol: str, entidad_id: int, ops_id,
                 nombre_usuario: str, ops_nombre: str = ""):
        super().__init__()
        self.setWindowTitle("SIGES - Reportes")
        self.setMinimumSize(360, 480)
        self.resize(1200, 760)
        self.setStyleSheet(STYLE)

        central = QWidget(); self.setCentralWidget(central)
        root_lay = QVBoxLayout(central)
        root_lay.setContentsMargins(0, 0, 0, 0); root_lay.setSpacing(0)

        h_row = QWidget()
        h_row.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        h_lay = QHBoxLayout(h_row)
        h_lay.setContentsMargins(0, 0, 0, 0); h_lay.setSpacing(0)

        self._sidebar = Sidebar(nombre_usuario, rol)
        h_lay.addWidget(self._sidebar)

        right = QWidget(); right.setStyleSheet(f"background:{P['bg']};")
        rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)
        self._top = TopBar(); rl.addWidget(self._top)
        self._tab = TabReportes(rol, entidad_id, ops_id, ops_nombre)
        rl.addWidget(self._tab, 1)
        h_lay.addWidget(right, 1)
        root_lay.addWidget(h_row, 1)

        self._bottom = BottomNav(); self._bottom.hide()
        root_lay.addWidget(self._bottom)

    def resizeEvent(self, e: QResizeEvent):
        super().resizeEvent(e)
        self._pending_w = self.width()
        if not hasattr(self, "_resize_timer"):
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._aplicar_resize)
        self._resize_timer.start(50)

    def _aplicar_resize(self):
        w = getattr(self, "_pending_w", self.width())
        if w < self._BP_BOTTOM:
            self._sidebar.hide(); self._bottom.show()
        elif w < self._BP_COLLAPSE:
            self._sidebar.show(); self._bottom.hide()
            self._sidebar.colapsar()
        else:
            self._sidebar.show(); self._bottom.hide()
            self._sidebar.expandir()
        self._top.set_dim(w, self.height())
        self._tab._ajustar_cols()


# ══════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    win = ReportesWindow(
        rol="maestro",        # "ops" | "maestro" | "entidad" | "admin"
        entidad_id=1,
        ops_id=None,
        nombre_usuario="Maria Lopez",
        ops_nombre="Maria Lopez",
    )
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
