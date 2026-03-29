"""
gestion_eventos_ui.py -- Modulo de Eventos CAOR (v3)

NOVEDADES v3:
  Permisos por rol
    ops     -> ve y gestiona SOLO sus propios eventos
               (sin columna "Registrado por", sin boton Nuevo si ops_id None)
    maestro -> ve TODOS los eventos de la entidad; puede registrar y gestionar
    entidad -> igual que maestro
    admin   -> acceso total (activar/desactivar, reactivar ventanas)
  Formularios mejorados
    - Secciones agrupadas visualmente con cabeceras
    - Labels descriptivos y placeholders de ejemplo reales
    - EPS muestra nombre limpio + indicador de contrato
    - Tipo afiliacion muestra nombre sin codigos
    - Checkbox "Afiliado a EPS" con texto explicativo
    - Campo Valor con ejemplo de formato
    - Aviso automatico cuando EPS no tiene contrato vigente
  Tabla
    - Columna "Registrado por" visible para maestro/entidad/admin
    - Badge de estado mas visible
    - Menu de acciones diferenciado por rol

Responsividad:
  >= 960px -> sidebar 220px expandida
  680-960px -> sidebar 56px solo iconos
  < 680px  -> sidebar oculta + barra inferior
"""
from __future__ import annotations
import sys
from datetime import date
from functools import partial

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox,
    QTableWidget, QTableWidgetItem,
    QFrame, QSizePolicy, QScrollArea,
    QMessageBox, QAbstractItemView,
    QListWidget, QListWidgetItem,
    QButtonGroup, QStackedWidget, QMenu,
    QDateEdit,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer, QPoint, QDate
from PySide6.QtGui import QCursor, QResizeEvent

import gestion_eventos_backend as ev_bk

# Roles que ven todos los eventos
_ROLES_VER_TODO = {"admin", "maestro", "entidad"}

# Cache de catalogos por entidad
_cache_catalogos: dict[int, dict] = {}


def _obtener_catalogos(entidad_id: int) -> dict:
    if entidad_id not in _cache_catalogos:
        try:
            form = ev_bk.cargar_formulario(entidad_id)
            _cache_catalogos[entidad_id] = {
                "eps_lista":        form.get("eps_lista") or [],
                "tipos_afiliacion": form.get("tipos_afiliacion") or [],
            }
        except Exception:
            _cache_catalogos[entidad_id] = {
                "eps_lista":        ev_bk.obtener_eps_entidad(entidad_id),
                "tipos_afiliacion": ev_bk.obtener_tipos_afiliacion(entidad_id),
            }
    return _cache_catalogos[entidad_id]


def _limpiar_cache(entidad_id: int | None = None):
    if entidad_id is None:
        _cache_catalogos.clear()
    else:
        _cache_catalogos.pop(entidad_id, None)


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
    "sec_hdr": "#0F1419",
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
    color:{P['txt']}; font-size:13px;
    alternate-background-color:{P['row_alt']};
    selection-background-color:{P['row_sel']};
    selection-color:{P['txt']};
}}
QTableWidget::item {{ padding:6px 10px; border:none; }}
QHeaderView::section {{
    background:#0F1419; color:{P['txt2']}; border:none;
    border-right:1px solid {P['border']};
    border-bottom:1px solid {P['border']};
    padding:8px 10px; font-size:12px; font-weight:600;
}}
QLineEdit {{
    background:{P['input']}; border:1.5px solid {P['border']};
    border-radius:7px; padding:8px 12px;
    color:{P['txt']}; font-size:13px;
}}
QLineEdit:focus {{ border-color:{P['focus']}; background:#1C2128; }}
QLineEdit:disabled {{ color:{P['muted']}; background:{P['card']}; }}
QCheckBox {{ color:{P['txt']}; spacing:8px; }}
QCheckBox::indicator {{
    width:16px; height:16px;
    border:1.5px solid {P['border']}; border-radius:4px;
    background:{P['input']};
}}
QCheckBox::indicator:checked {{
    background:{P['accent']}; border-color:{P['accent']};
}}
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

_CSS_LINE = (
    f"QLineEdit{{background:{P['input']};border:1.5px solid {P['border']};"
    f"border-radius:7px;padding:8px 12px;color:{P['txt']};font-size:13px;}}"
    f"QLineEdit:focus{{border-color:{P['focus']};background:#1C2128;}}"
    f"QLineEdit:disabled{{color:{P['muted']};background:{P['card']};}}"
)

# ══════════════════════════════════════════════════════════════
# HELPERS GLOBALES
# ══════════════════════════════════════════════════════════════

def _lbl(txt, size=13, color=None, bold=False, wrap=False):
    lb = QLabel(txt)
    c = color or P["txt"]; w = "600" if bold else "400"
    lb.setStyleSheet(
        f"color:{c};font-size:{size}px;font-weight:{w};background:transparent;"
    )
    if wrap: lb.setWordWrap(True)
    return lb


def _sec_header(txt: str) -> QWidget:
    """Cabecera de seccion con linea separadora."""
    w = QWidget(); w.setStyleSheet("background:transparent;")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 4, 0, 0); lay.setSpacing(4)
    lb = QLabel(txt)
    lb.setStyleSheet(
        f"color:{P['txt2']};font-size:11px;font-weight:700;"
        f"letter-spacing:1px;background:transparent;"
        f"text-transform:uppercase;"
    )
    sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(
        f"border:none;border-top:1px solid {P['border']};background:transparent;"
    )
    sep.setFixedHeight(1)
    lay.addWidget(lb); lay.addWidget(sep)
    return w


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
        "danger": (
            f"QPushButton{{background:rgba(248,81,73,.15);color:{P['err']};"
            f"border:1px solid {P['err']};border-radius:7px;"
            f"padding:7px 14px;font-size:12px;font-weight:600;}}"
            f"QPushButton:hover{{background:rgba(248,81,73,.28);}}"
        ),
        "ok": (
            f"QPushButton{{background:rgba(63,185,80,.15);color:{P['ok']};"
            f"border:1px solid {P['ok']};border-radius:7px;"
            f"padding:7px 14px;font-size:12px;font-weight:600;}}"
            f"QPushButton:hover{{background:rgba(63,185,80,.28);}}"
        ),
        "warn": (
            f"QPushButton{{background:rgba(210,153,34,.15);color:{P['warn']};"
            f"border:1px solid {P['warn']};border-radius:7px;"
            f"padding:7px 14px;font-size:12px;font-weight:600;}}"
            f"QPushButton:hover{{background:rgba(210,153,34,.28);}}"
        ),
        "filtro": (
            f"QPushButton{{background:{P['card']};color:{P['txt2']};"
            f"border:1.5px solid {P['border']};border-radius:6px;"
            f"padding:6px 12px;font-size:12px;font-weight:500;}}"
            f"QPushButton:hover{{border-color:{P['focus']};color:{P['txt']};}}"
            f"QPushButton:checked{{background:{P['acc_lt']};color:{P['acc_h']};"
            f"border-color:{P['accent']};font-weight:700;}}"
        ),
    }
    b.setStyleSheet(S.get(style, S["prim"]))
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    return b


def _item(txt):
    i = QTableWidgetItem(str(txt) if txt is not None else "")
    i.setFlags(i.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return i


def _make_table(cols):
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
        try:
            r = self._fn(*self._args, **self._kw)
        except Exception as e:
            r = ev_bk.Resultado(False, str(e))
        self.done.emit(r)


_workers: list = []


def run_async(parent, fn, *args, on_done=None, **kw):
    w = _Worker(fn, args, kw)
    _workers.append(w)
    if on_done:
        w.done.connect(on_done)
    w.done.connect(lambda _: _workers.remove(w) if w in _workers else None)
    w.start()


def _ops_safe(ops_id) -> int | None:
    if ops_id is None or ops_id == 0 or str(ops_id) == "":
        return None
    return int(ops_id)


def _screen_h() -> int:
    app = QApplication.instance()
    if app:
        sc = app.primaryScreen()
        if sc: return sc.availableGeometry().height()
    return 768


# ══════════════════════════════════════════════════════════════
# BADGE DE ESTADO
# ══════════════════════════════════════════════════════════════

def _badge(estado: str) -> QWidget:
    w = QWidget(); w.setStyleSheet("background:transparent;")
    lay = QHBoxLayout(w); lay.setContentsMargins(4, 2, 4, 2)
    e = (estado or "").lower()
    if "inactiv" in e:
        color = P["muted"]; rgb = "72,79,88"
    elif "ermin" in e:
        color = P["ok"];    rgb = "63,185,80"
    else:
        color = P["warn"];  rgb = "210,153,34"
    lb = QLabel(f"  {estado}  ")
    lb.setStyleSheet(
        f"background:rgba({rgb},.18);color:{color};"
        f"border:1px solid {color};border-radius:10px;"
        f"padding:2px 8px;font-size:11px;font-weight:600;"
    )
    lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(lb); return w


# ══════════════════════════════════════════════════════════════
# STATUS BAR
# ══════════════════════════════════════════════════════════════

class StatusBar(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hide()

    def ok(self, m):
        self.setStyleSheet(
            f"background:rgba(63,185,80,.15);border:1px solid {P['ok']};"
            f"border-radius:7px;color:{P['ok']};padding:9px 14px;font-size:12px;"
        )
        self.setText(m); self.show()

    def err(self, m):
        self.setStyleSheet(
            f"background:rgba(248,81,73,.15);border:1px solid {P['err']};"
            f"border-radius:7px;color:{P['err']};padding:9px 14px;font-size:12px;"
        )
        self.setText(m); self.show()

    def ocultar(self): self.hide()


# ══════════════════════════════════════════════════════════════
# INPUT FIELD
# ══════════════════════════════════════════════════════════════

class InputF(QWidget):
    def __init__(self, label: str, ph: str = "", pw: bool = False,
                 ayuda: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QWidget{{background:{P['bg']};border:none;}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(4)
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"color:{P['txt2']};font-size:12px;background:transparent;"
        )
        lay.addWidget(lbl)
        self.inp = QLineEdit()
        self.inp.setPlaceholderText(ph)
        self.inp.setMinimumHeight(40)
        self.inp.setStyleSheet(_CSS_LINE)
        if pw: self.inp.setEchoMode(QLineEdit.EchoMode.Password)
        if ayuda:
            hl = QLabel(ayuda)
            hl.setWordWrap(True)
            hl.setStyleSheet(
                f"color:{P['muted']};font-size:11px;background:transparent;"
            )
        self.e = QLabel("")
        self.e.setStyleSheet(
            f"color:{P['err']};font-size:11px;background:transparent;"
        )
        self.e.hide()
        lay.addWidget(self.inp)
        if ayuda: lay.addWidget(hl)
        lay.addWidget(self.e)

    def text(self) -> str:   return self.inp.text().strip()
    def set(self, v):        self.inp.setText(str(v) if v else "")
    def clear(self):         self.inp.clear()
    def setEnabled(self, v): self.inp.setEnabled(v)
    def err(self, m):        self.e.setText(m); self.e.show()
    def ok(self):            self.e.hide()


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
            f"color:{P['txt2']};font-size:12px;background:transparent;"
        )
        lay.addWidget(lbl)
        self.de = QDateEdit()
        self.de.setDate(QDate.currentDate())
        self.de.setCalendarPopup(True)
        self.de.setDisplayFormat("dd/MM/yyyy")
        self.de.setMinimumHeight(40)
        self.de.setStyleSheet(
            f"QDateEdit{{background:{P['input']};border:1.5px solid {P['border']};"
            f"border-radius:7px;padding:0 12px;color:{P['txt']};font-size:13px;}}"
            f"QDateEdit:focus{{border-color:{P['focus']};background:#1C2128;}}"
            f"QDateEdit::drop-down{{border:none;width:28px;}}"
            f"QDateEdit::down-arrow{{"
            f"border-left:5px solid transparent;"
            f"border-right:5px solid transparent;"
            f"border-top:6px solid {P['txt2']};margin-right:8px;}}"
            f"QCalendarWidget{{background:{P['card']};color:{P['txt']};"
            f"border:1.5px solid {P['border']};border-radius:8px;}}"
            f"QCalendarWidget QToolButton{{background:{P['card']};"
            f"color:{P['txt']};border:none;border-radius:5px;"
            f"padding:4px 8px;font-size:13px;font-weight:600;}}"
            f"QCalendarWidget QToolButton:hover{{background:{P['input']};}}"
            f"QCalendarWidget QAbstractItemView:enabled{{"
            f"background:{P['bg']};color:{P['txt']};"
            f"selection-background-color:{P['accent']};"
            f"selection-color:white;}}"
            f"QCalendarWidget QAbstractItemView:disabled{{"
            f"color:{P['muted']};}}"
            f"QCalendarWidget QWidget#qt_calendar_navigationbar{{"
            f"background:{P['card']};"
            f"border-bottom:1px solid {P['border']};padding:4px;}}"
        )
        lay.addWidget(self.de)

    def text(self) -> str:
        return self.de.date().toString("yyyy-MM-dd")

    def set(self, v: str):
        if v:
            d = QDate.fromString(str(v)[:10], "yyyy-MM-dd")
            if d.isValid():
                self.de.setDate(d)

    def setEnabled(self, v: bool):
        self.de.setEnabled(v)


# ══════════════════════════════════════════════════════════════
# COMBO FIELD (selector desplegable con buscador)
# ══════════════════════════════════════════════════════════════

class ComboF(QWidget):
    selectionChanged = Signal(object)
    _ITEM_H   = 36
    _MAX_ROWS = 8

    def __init__(self, label: str, ayuda: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QWidget{{background:{P['bg']};border:none;}}")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._items:    list[tuple[str, object]] = []
        self._filtered: list[int] = []
        self._sel  = -1
        self._open = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(4)

        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"color:{P['txt2']};font-size:12px;background:transparent;"
        )
        lay.addWidget(lbl)

        self._btn = QPushButton()
        self._btn.setMinimumHeight(40)
        self._btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn.clicked.connect(self._toggle)
        self._render_btn(False)
        lay.addWidget(self._btn)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Escribe para filtrar…")
        self._search.setMinimumHeight(34)
        self._search.setStyleSheet(
            f"QLineEdit{{background:{P['input']};"
            f"border:1.5px solid {P['focus']};"
            f"border-top:none;border-bottom:none;"
            f"border-radius:0;padding:4px 12px;"
            f"color:{P['txt']};font-size:12px;}}"
            f"QLineEdit:focus{{background:#1C2128;}}"
        )
        self._search.textChanged.connect(self._filtrar)
        self._search.hide()
        lay.addWidget(self._search)

        self._list = QListWidget()
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._list.setStyleSheet(
            f"QListWidget{{background:{P['card']};color:{P['txt']};"
            f"border:1.5px solid {P['focus']};border-top:none;"
            f"border-bottom-left-radius:7px;border-bottom-right-radius:7px;"
            f"outline:none;padding:4px 0;}}"
            f"QListWidget::item{{min-height:{self._ITEM_H}px;"
            f"padding:0 12px;color:{P['txt']};border:none;}}"
            f"QListWidget::item:hover{{background:{P['input']};}}"
            f"QListWidget::item:selected"
            f"{{background:{P['accent']};color:white;}}"
            f"QScrollBar:vertical{{background:{P['card']};width:8px;}}"
            f"QScrollBar::handle:vertical{{background:{P['border']};"
            f"border-radius:4px;min-height:20px;}}"
        )
        self._list.hide()
        self._list.itemClicked.connect(self._pick)
        lay.addWidget(self._list)

        if ayuda:
            hl = QLabel(ayuda)
            hl.setWordWrap(True)
            hl.setStyleSheet(
                f"color:{P['muted']};font-size:11px;background:transparent;"
            )
            lay.addWidget(hl)

    def _btn_css(self, open_):
        bc = P["focus"] if open_ else P["border"]
        rb = "0" if open_ else "7px"
        return (
            f"QPushButton{{background:{P['input']};color:{P['txt']};"
            f"border:1.5px solid {bc};border-radius:7px;"
            f"border-bottom-left-radius:{rb};"
            f"border-bottom-right-radius:{rb};"
            f"font-size:13px;text-align:left;padding:0 12px;}}"
            f"QPushButton::menu-indicator{{width:0;}}"
        )

    def _render_btn(self, open_):
        t = self.text() or "-- Selecciona una opcion --"
        self._btn.setText(f"{t}   {'▴' if open_ else '▾'}")
        self._btn.setStyleSheet(self._btn_css(open_))

    def _toggle(self):
        self._close() if self._open else self._abrir()

    def _abrir(self):
        if not self._items:
            return
        self._search.clear()
        self._filtrar("")
        self._search.show()
        self._open = True
        self._render_btn(True)
        QTimer.singleShot(50, self._search.setFocus)
        if self._sel >= 0:
            for row in range(self._list.count()):
                item = self._list.item(row)
                if item and item.data(Qt.ItemDataRole.UserRole + 1) == self._sel:
                    self._list.setCurrentRow(row)
                    self._list.scrollToItem(
                        item,
                        QAbstractItemView.ScrollHint.PositionAtCenter
                    )
                    break

    def _close(self):
        self._search.hide()
        self._list.hide()
        self._open = False
        self._render_btn(False)

    def _filtrar(self, texto: str):
        term = texto.strip().lower()
        self._filtered = [
            i for i, (t, _) in enumerate(self._items)
            if term in t.lower()
        ] if term else list(range(len(self._items)))

        self._list.clear()
        for idx in self._filtered:
            txt, data = self._items[idx]
            li = QListWidgetItem(txt)
            li.setData(Qt.ItemDataRole.UserRole,     data)
            li.setData(Qt.ItemDataRole.UserRole + 1, idx)
            self._list.addItem(li)

        visible = len(self._filtered)
        if visible == 0:
            li_vacio = QListWidgetItem("Sin resultados para esta busqueda")
            li_vacio.setFlags(Qt.ItemFlag.NoItemFlags)
            li_vacio.setForeground(
                __import__("PySide6.QtGui", fromlist=["QColor"]).QColor(P["muted"])
            )
            self._list.addItem(li_vacio)
            visible = 1

        h = min(visible, self._MAX_ROWS) * self._ITEM_H + 8
        self._list.setFixedHeight(h)
        self._list.show()

    def _pick(self, item: QListWidgetItem):
        if not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        original_idx = item.data(Qt.ItemDataRole.UserRole + 1)
        if original_idx is None:
            return
        self._sel = original_idx
        self._render_btn(False)
        self._close()
        self.selectionChanged.emit(self.data())

    def add(self, txt: str, data=None):
        self._items.append((txt, data))

    def data(self):
        return self._items[self._sel][1] if self._sel >= 0 else None

    def text(self) -> str:
        return self._items[self._sel][0] if self._sel >= 0 else ""

    def clear(self):
        self._items.clear()
        self._filtered.clear()
        self._list.clear()
        self._sel = -1
        self._render_btn(False)

    def set_by_data(self, val):
        for i, (_, d) in enumerate(self._items):
            if d == val:
                self._sel = i
                self._render_btn(False)
                return

    def setEnabled(self, v: bool):
        self._btn.setEnabled(v)
        if not v:
            self._close()


# ══════════════════════════════════════════════════════════════
# SELECTOR DE PACIENTE
# ══════════════════════════════════════════════════════════════

class SelectorPaciente(QWidget):
    paciente_seleccionado = Signal(dict)

    def __init__(self, entidad_id: int, label: str = "Paciente *",
                 parent=None):
        super().__init__(parent)
        self._eid = entidad_id
        self._pac: dict | None = None
        self.setStyleSheet(f"QWidget{{background:{P['bg']};border:none;}}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(4)

        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"color:{P['txt2']};font-size:12px;background:transparent;"
        )
        lay.addWidget(lbl)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0); row.setSpacing(6)
        self._inp = QLineEdit()
        self._inp.setPlaceholderText(
            "Busca por nombre o numero de documento (cedula, TI, etc.)…"
        )
        self._inp.setMinimumHeight(40)
        self._inp.setStyleSheet(_CSS_LINE)
        self._inp.textChanged.connect(self._on_texto)

        self._btn_x = QPushButton("x")
        self._btn_x.setFixedSize(40, 40)
        self._btn_x.setStyleSheet(
            f"QPushButton{{background:{P['input']};color:{P['txt2']};"
            f"border:1.5px solid {P['border']};border-radius:7px;"
            f"font-size:13px;font-weight:600;}}"
            f"QPushButton:hover{{background:{P['border']};"
            f"color:{P['txt']};}}"
        )
        self._btn_x.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_x.setToolTip("Limpiar seleccion")
        self._btn_x.clicked.connect(self._limpiar)
        self._btn_x.hide()
        row.addWidget(self._inp, 1); row.addWidget(self._btn_x)
        lay.addLayout(row)

        hl = QLabel("Escribe al menos 1 caracter para buscar")
        hl.setStyleSheet(
            f"color:{P['muted']};font-size:11px;background:transparent;"
        )
        lay.addWidget(hl)

        self._lista = QListWidget()
        self._lista.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._lista.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._lista.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._lista.setStyleSheet(
            f"QListWidget{{background:{P['card']};color:{P['txt']};"
            f"border:1.5px solid {P['focus']};border-top:none;"
            f"border-bottom-left-radius:7px;border-bottom-right-radius:7px;"
            f"outline:none;padding:4px 0;}}"
            f"QListWidget::item{{min-height:50px;padding:4px 14px;"
            f"color:{P['txt']};border:none;}}"
            f"QListWidget::item:hover{{background:{P['input']};}}"
            f"QListWidget::item:selected"
            f"{{background:{P['accent']};color:white;}}"
            f"QScrollBar:vertical{{background:{P['card']};width:8px;}}"
            f"QScrollBar::handle:vertical{{background:{P['border']};"
            f"border-radius:4px;min-height:20px;}}"
        )
        self._lista.hide()
        self._lista.itemClicked.connect(self._elegir)
        lay.addWidget(self._lista)

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._buscar)

    def _on_texto(self, texto: str):
        if self._pac: return
        if len(texto.strip()) >= 1:
            self._timer.start(280)
        else:
            self._lista.hide()

    def _buscar(self):
        texto = self._inp.text().strip()
        if not texto: return
        resultados = ev_bk.buscar_pacientes(self._eid, texto, 25)
        self._lista.clear()
        for d in resultados:
            nombre = d.get("nombre_completo", "")
            tipo   = d.get("tipo_doc", "")
            num    = d.get("numero_documento", "")
            eps    = d.get("eps_nombre", "") or ""
            afil   = d.get("tipo_afiliacion_nombre", "") or ""
            linea1 = nombre
            info   = f"{tipo} {num}"
            if eps:  info += f"  |  EPS: {eps}"
            if afil: info += f"  |  {afil}"
            li = QListWidgetItem(f"{linea1}\n   {info}")
            li.setData(Qt.ItemDataRole.UserRole, d)
            self._lista.addItem(li)
        if resultados:
            h = min(len(resultados), 5) * 60 + 8
            self._lista.setFixedHeight(h)
            self._lista.show()
        else:
            self._lista.clear()
            li_vacio = QListWidgetItem("No se encontraron pacientes con ese dato")
            li_vacio.setFlags(Qt.ItemFlag.NoItemFlags)
            self._lista.addItem(li_vacio)
            self._lista.setFixedHeight(56)
            self._lista.show()

    def _elegir(self, item: QListWidgetItem):
        if not item.flags() & Qt.ItemFlag.ItemIsEnabled:
            return
        d = item.data(Qt.ItemDataRole.UserRole)
        if not d: return
        self._pac = d
        nombre = d.get("nombre_completo", "")
        num    = d.get("numero_documento", "")
        tipo   = d.get("tipo_doc", "")
        self._inp.setText(f"{nombre}  [{tipo} {num}]")
        self._inp.setReadOnly(True)
        self._btn_x.show(); self._lista.hide()
        self.paciente_seleccionado.emit(d)

    def _limpiar(self):
        self._pac = None
        self._inp.clear(); self._inp.setReadOnly(False)
        self._btn_x.hide(); self._lista.hide()

    def get_paciente(self) -> dict | None:
        return self._pac

    def set_paciente(self, d: dict):
        self._pac = d
        nombre = (d.get("nombre_completo") or d.get("paciente_nombre", ""))
        tipo   = (d.get("tipo_doc") or d.get("paciente_tipo_doc", ""))
        num    = (d.get("numero_documento") or d.get("paciente_numero_doc", ""))
        self._inp.setText(f"{nombre}  [{tipo} {num}]")
        self._inp.setReadOnly(True)
        self._btn_x.show()


# ══════════════════════════════════════════════════════════════
# DIALOGO BASE
# ══════════════════════════════════════════════════════════════

class BaseDialog(QDialog):
    def __init__(self, titulo: str, ancho: int = 560, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setModal(True)
        app = QApplication.instance()
        sw = 800
        if app:
            sc = app.primaryScreen()
            if sc: sw = sc.availableGeometry().width()
        ancho = min(ancho, max(360, int(sw * 0.92)))
        self.setMinimumWidth(min(360, ancho))
        self.setMaximumWidth(min(840, sw))
        self.setStyleSheet(f"QDialog{{background:{P['bg']};}}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(
            f"QScrollArea{{border:none;background:{P['bg']};}}"
            f"QScrollBar:vertical{{background:{P['bg']};width:8px;}}"
            f"QScrollBar::handle:vertical{{background:{P['border']};"
            f"border-radius:4px;min-height:20px;}}"
            f"QScrollBar::add-line:vertical,"
            f"QScrollBar::sub-line:vertical{{height:0;}}"
        )
        inner = QWidget()
        inner.setStyleSheet(f"background:{P['bg']};")
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(28, 24, 28, 24)
        self.lay.setSpacing(0)

        t = QLabel(titulo)
        t.setStyleSheet(
            f"color:{P['txt']};font-size:18px;"
            f"font-weight:700;background:transparent;"
        )
        self.lay.addWidget(t); self.lay.addSpacing(8)
        sp = QFrame(); sp.setFrameShape(QFrame.Shape.HLine)
        sp.setStyleSheet(
            f"border:none;border-top:1px solid {P['border']};"
            f"background:transparent;"
        )
        sp.setFixedHeight(1)
        self.lay.addWidget(sp); self.lay.addSpacing(18)

        scroll.setWidget(inner)
        outer.addWidget(scroll)
        sh = _screen_h()
        self.resize(ancho, min(int(sh * 0.82), 720))

    def _fin(self):
        QTimer.singleShot(0, self._aplicar_tamanio)

    def _aplicar_tamanio(self):
        self.adjustSize()
        sh = _screen_h()
        mh = int(sh * 0.88)
        if self.height() > mh:
            self.resize(self.width(), mh)
        if self.height() < 340:
            self.resize(self.width(), 400)


# ══════════════════════════════════════════════════════════════
# DIALOGO: Nuevo / Editar evento
# ══════════════════════════════════════════════════════════════

class DialogEvento(BaseDialog):
    """
    Formulario completo de evento con secciones agrupadas y labels claros.
    """

    def __init__(self, entidad_id: int, ops_id, rol: str,
                 datos_ini: dict | None = None, parent=None):
        titulo = "Editar evento de atencion" if datos_ini else "Registrar nuevo evento de atencion"
        super().__init__(titulo, 620, parent)
        self._eid       = entidad_id
        self._oid       = _ops_safe(ops_id)
        self._rol       = rol
        self._editando  = datos_ini
        self._evid      = datos_ini["evento_id"] if datos_ini else None
        self._es_editable = True

        cats = _obtener_catalogos(entidad_id)
        self._eps_list  = cats["eps_lista"]
        self._afil_list = cats["tipos_afiliacion"]

        self._build()
        if datos_ini:
            self._precargar(datos_ini)
        if self._evid:
            def _check_editable():
                try:
                    form = ev_bk.cargar_formulario(entidad_id, self._evid)
                    return form.get("es_editable", True)
                except Exception:
                    return True
            def _on_editable(result):
                self._es_editable = bool(result)
                if not self._es_editable and hasattr(self, "bok"):
                    self.bok.setEnabled(False)
            run_async(self, _check_editable, on_done=_on_editable)

    def _build(self):
        lay = self.lay

        # ── SECCION 1: Paciente ────────────────────────────────
        lay.addWidget(_sec_header("1. Identificacion del paciente"))
        lay.addSpacing(10)

        self.selector = SelectorPaciente(self._eid, "Buscar paciente *")
        self.selector.paciente_seleccionado.connect(self._auto_completar)
        lay.addWidget(self.selector); lay.addSpacing(10)

        # Nombre visible tras seleccion
        self.lbl_pac_nombre = QLabel("-- Selecciona un paciente para ver su nombre --")
        self.lbl_pac_nombre.setWordWrap(True)
        self.lbl_pac_nombre.setStyleSheet(
            f"color:{P['muted']};font-size:13px;font-weight:400;"
            f"background:{P['input']};border:1.5px solid {P['border']}; "
            f"border-radius:7px;padding:12px 14px;"
        )
        self.lbl_pac_nombre.setMinimumHeight(46)
        lay.addWidget(self.lbl_pac_nombre)
        lay.addSpacing(20)

        # ── SECCION 2: Datos del evento ────────────────────────
        lay.addWidget(_sec_header("2. Datos del evento"))
        lay.addSpacing(10)

        self.f_fecha = DateF("Fecha en que ocurrio el evento *")
        self.f_fecha.set(str(date.today()))
        lay.addWidget(self.f_fecha); lay.addSpacing(12)

        self.f_admision = InputF(
            "Numero de admision *",
            "Ej: ADM-2024-001",
            ayuda="Obligatorio siempre. Numero asignado por admisiones al ingreso del paciente."
        )
        lay.addWidget(self.f_admision); lay.addSpacing(12)

        self.f_motivo = InputF(
            "Motivo de la consulta / atencion *",
            "Describe brevemente el motivo: ej. Consulta de urgencias por dolor toracico…"
        )
        lay.addWidget(self.f_motivo)
        lay.addSpacing(20)

        # ── SECCION 3: EPS y afiliacion ────────────────────────
        lay.addWidget(_sec_header("3. Aseguradora (EPS) y tipo de afiliacion"))
        lay.addSpacing(10)

        # EPS
        self.f_eps = ComboF(
            "EPS del paciente",
            ayuda="Se autocompleta al seleccionar el paciente. Puedes cambiarlo si es diferente."
        )
        self.f_eps.add("-- Sin EPS / no aplica --", None)
        for e in self._eps_list:
            eid  = e.get("eps_id") or e.get("id")
            nom  = e.get("nombre") or "--"
            cod  = e.get("codigo", "")
            tiene = e.get("tiene_contrato", None)
            if tiene is True:
                etxt = f"[contrato vigente] {nom}"
            elif tiene is False:
                etxt = f"[sin contrato] {nom}"
            else:
                etxt = f"[{cod}] {nom}" if cod else nom
            self.f_eps.add(etxt, eid)
        self.f_eps.selectionChanged.connect(self._on_eps_cambia)
        lay.addWidget(self.f_eps); lay.addSpacing(6)

        # Aviso sin contrato
        self._aviso_contrato = QLabel(
            "Aviso: esta EPS no tiene contrato vigente con la institucion."
        )
        self._aviso_contrato.setWordWrap(True)
        self._aviso_contrato.setStyleSheet(
            f"color:{P['warn']};font-size:12px;"
            f"background:rgba(210,153,34,.08);"
            f"border:1px solid rgba(210,153,34,.4);"
            f"border-radius:6px;padding:8px 12px;"
        )
        self._aviso_contrato.hide()
        lay.addWidget(self._aviso_contrato); lay.addSpacing(8)

        # Checkbox afiliado
        afil_w = QWidget(); afil_w.setStyleSheet("background:transparent;")
        afil_lay = QVBoxLayout(afil_w)
        afil_lay.setContentsMargins(0, 0, 0, 0); afil_lay.setSpacing(4)
        self.ck_afil = QCheckBox("El paciente esta afiliado a esta EPS")
        self.ck_afil.setStyleSheet(f"color:{P['txt']};font-size:13px;")
        nota_afil = QLabel("Marca esta casilla si el paciente es afiliado activo de la EPS seleccionada")
        nota_afil.setStyleSheet(
            f"color:{P['muted']};font-size:11px;background:transparent;"
        )
        afil_lay.addWidget(self.ck_afil); afil_lay.addWidget(nota_afil)
        lay.addWidget(afil_w); lay.addSpacing(12)

        # Tipo de afiliacion
        self.f_afil = ComboF(
            "Tipo de afiliacion *",
            ayuda="Indica como esta vinculado el paciente al sistema de salud"
        )
        self.f_afil.add("-- Selecciona el tipo de afiliacion --", None)
        for a in self._afil_list:
            self.f_afil.add(a["nombre"], a["id"])
        lay.addWidget(self.f_afil)
        lay.addSpacing(20)

        # ── SECCION 4: Facturacion ─────────────────────────────
        lay.addWidget(_sec_header("4. Facturacion (obligatorio al terminar)"))
        lay.addSpacing(10)

        self.f_valor = InputF(
            "Valor facturado ($)",
            "Ej: 150000  (dejar en 0 si aun no se ha facturado)",
            ayuda="Al ingresar un valor mayor a 0 el evento pasa automaticamente a estado Terminado"
        )
        lay.addWidget(self.f_valor); lay.addSpacing(12)

        self.f_codigo = InputF(
            "Codigo del evento",
            "Ej: EV-2024-00456",
            ayuda="Obligatorio para terminar el evento. Codigo interno asignado por la IPS o el HIS."
        )
        lay.addWidget(self.f_codigo); lay.addSpacing(12)

        self.f_factura = InputF(
            "Numero de factura",
            "Ej: FE-2024-00123",
            ayuda="Obligatorio para terminar el evento. Numero de la factura electronica o fisica."
        )
        lay.addWidget(self.f_factura)
        lay.addSpacing(10)

        aviso_term = QLabel(
            "Al terminar el evento (valor > 0) los campos "
            "Numero de admision, Codigo del evento y Numero de factura son obligatorios."
        )
        aviso_term.setWordWrap(True)
        aviso_term.setStyleSheet(
            f"color:{P['txt2']};font-size:11px;"
            f"background:rgba(44,106,223,.07);"
            f"border:1px solid {P['border']};"
            f"border-radius:6px;padding:8px 12px;"
        )
        lay.addWidget(aviso_term)
        lay.addSpacing(20)

        # ── SECCION 5: Estado (solo admin en edicion) ──────────
        if self._rol == "admin" and self._editando:
            lay.addWidget(_sec_header("5. Estado del evento"))
            lay.addSpacing(10)
            row_e = QHBoxLayout()
            row_e.setContentsMargins(0, 0, 0, 0); row_e.setSpacing(8)
            self._bg_est = QButtonGroup(self)
            estados = [
                (1, "Pendiente", P["warn"]),
                (2, "Terminado", P["ok"]),
            ]
            for sid, snom, col in estados:
                b = _btn(snom, "filtro"); b.setCheckable(True)
                b.setStyleSheet(
                    b.styleSheet() +
                    f"QPushButton:checked{{background:{P['acc_lt']};"
                    f"color:{col};border-color:{col};font-weight:700;}}"
                )
                self._bg_est.addButton(b, sid)
                row_e.addWidget(b)
            row_e.addStretch()
            lay.addLayout(row_e)
            lay.addSpacing(20)

        # ── Aviso ventana vencida ──────────────────────────────
        if self._editando and not self._es_editable:
            av = QLabel(
                "La ventana de edicion ha vencido. "
                "Este evento es de solo lectura. "
                "Solicita al administrador que reactive la ventana."
            )
            av.setWordWrap(True)
            av.setStyleSheet(
                f"color:{P['warn']};font-size:12px;"
                f"background:rgba(210,153,34,.1);"
                f"border:1px solid {P['warn']};"
                f"border-radius:6px;padding:10px 12px;"
            )
            lay.addWidget(av); lay.addSpacing(10)

        # ── StatusBar ──────────────────────────────────────────
        self.sb = StatusBar()
        lay.addWidget(self.sb); lay.addSpacing(14)

        # ── Botones ────────────────────────────────────────────
        brow = QHBoxLayout()
        bc = _btn("Cancelar", "sec"); bc.clicked.connect(self.reject)
        self.bok = _btn("Guardar evento")
        self.bok.clicked.connect(self._guardar)
        if self._editando and not self._es_editable:
            self.bok.setEnabled(False)
        brow.addWidget(bc); brow.addWidget(self.bok)
        lay.addLayout(brow)
        self._fin()

    def _on_eps_cambia(self, eps_data):
        """Muestra aviso si la EPS no tiene contrato."""
        if eps_data is None:
            self._aviso_contrato.hide()
            return
        # Buscar en la lista si tiene_contrato = False
        for e in self._eps_list:
            eid = e.get("eps_id") or e.get("id")
            if eid == eps_data and e.get("tiene_contrato") is False:
                self._aviso_contrato.show()
                return
        self._aviso_contrato.hide()

    def _auto_completar(self, pac: dict):
        nombre = pac.get("nombre_completo", "")
        tipo   = pac.get("tipo_doc", "")
        num    = pac.get("numero_documento", "")
        doc_txt = f"Documento: {tipo} {num}" if tipo or num else ""
        self.lbl_pac_nombre.setText(
            f"{nombre}\n{doc_txt}" if doc_txt else nombre
        )
        self.lbl_pac_nombre.setStyleSheet(
            f"color:{P['txt']};font-size:14px;font-weight:600;"
            f"background:{P['acc_lt']};border:1.5px solid {P['accent']}; "
            f"border-radius:7px;padding:12px 14px;"
        )
        eps_id  = pac.get("eps_id")
        afil_id = pac.get("tipo_afiliacion_id")
        if eps_id:
            self.f_eps.set_by_data(eps_id)
            self.ck_afil.setChecked(True)
        else:
            self.f_eps.set_by_data(None)
            self.ck_afil.setChecked(False)
        if afil_id:
            self.f_afil.set_by_data(afil_id)

    def _precargar(self, d: dict):
        pac = ev_bk.obtener_datos_paciente(self._eid, d.get("paciente_id", 0))
        if pac:
            pac.setdefault("nombre_completo", d.get("paciente_nombre", ""))
            pac.setdefault("tipo_doc", d.get("paciente_tipo_doc", ""))
            pac.setdefault("numero_documento", d.get("paciente_numero_doc", ""))
            self.selector.set_paciente(pac)

        self.f_fecha.set(str(d.get("fecha_evento", ""))[:10])
        self.f_eps.set_by_data(d.get("eps_id"))
        self.ck_afil.setChecked(bool(d.get("afiliado_eps")))
        self.f_afil.set_by_data(d.get("tipo_afiliacion_id"))
        self.f_factura.set(d.get("numero_factura", "") or "")
        pac_nombre = (d.get("paciente_nombre") or d.get("nombre_paciente", ""))
        if pac_nombre:
            tipo = d.get("paciente_tipo_doc", "") or d.get("tipo_doc", "")
            num  = d.get("paciente_numero_doc", "") or d.get("numero_doc", "")
            doc_txt = f"Documento: {tipo} {num}" if tipo or num else ""
            self.lbl_pac_nombre.setText(
                f"{pac_nombre}\n{doc_txt}" if doc_txt else pac_nombre
            )
            self.lbl_pac_nombre.setStyleSheet(
                f"color:{P['txt']};font-size:14px;font-weight:600;"
                f"background:{P['acc_lt']};border:1.5px solid {P['accent']}; "
                f"border-radius:7px;padding:12px 14px;"
            )
        self.f_motivo.set(d.get("motivo", ""))
        self.f_admision.set(d.get("numero_admision", "") or "")
        self.f_codigo.set(d.get("codigo_evento", "") or "")
        val = d.get("valor", 0)
        self.f_valor.set(f"{float(val):.2f}" if val else "")
        if self._rol == "admin" and self._editando and hasattr(self, "_bg_est"):
            btn = self._bg_est.button(d.get("estado_id", 1))
            if btn: btn.setChecked(True)

    def _guardar(self):
        self.sb.ocultar()
        pac = self.selector.get_paciente()
        if not pac:
            self.sb.err("Debes seleccionar un paciente antes de guardar."); return
        if not self.f_afil.data():
            self.sb.err("Debes seleccionar el tipo de afiliacion."); return
        if not self.f_motivo.text():
            self.sb.err("El motivo de la atencion es obligatorio."); return
        if not self.f_admision.text():
            self.sb.err("El numero de admision es obligatorio."); return

        estado_id = 1
        if self._rol == "admin" and self._editando and hasattr(self, "_bg_est"):
            bc = self._bg_est.checkedButton()
            if bc: estado_id = self._bg_est.id(bc)

        valor_txt = self.f_valor.text() or "0"
        try:
            valor_num = float(valor_txt)
        except ValueError:
            valor_num = 0

        # Si hay valor (-> Terminado) los tres campos de cierre son obligatorios
        terminando = valor_num > 0 or estado_id == 2
        if terminando:
            errores = []
            if not self.f_admision.text():
                self.f_admision.err("Obligatorio al terminar el evento.")
                errores.append("numero de admision")
            if not self.f_codigo.text():
                self.f_codigo.err("Obligatorio al terminar el evento.")
                errores.append("codigo del evento")
            if not self.f_factura.text():
                self.f_factura.err("Obligatorio al terminar el evento.")
                errores.append("numero de factura")
            if errores:
                self.sb.err(
                    "Para terminar el evento debes completar: "
                    + ", ".join(errores) + "."
                )
                return
        else:
            self.f_admision.ok()
            self.f_codigo.ok()
            self.f_factura.ok()

        datos = {
            "paciente_id":        pac["paciente_id"],
            "fecha_evento":       self.f_fecha.text(),
            "eps_id":             self.f_eps.data(),
            "tipo_afiliacion_id": self.f_afil.data(),
            "afiliado_eps":       self.ck_afil.isChecked(),
            "motivo":             self.f_motivo.text(),
            "numero_admision":    self.f_admision.text() or None,
            "codigo_evento":      self.f_codigo.text() or None,
            "valor":              valor_txt,
            "numero_factura":     self.f_factura.text() or None,
            "estado_id":          estado_id,
        }
        self.bok.setEnabled(False); self.bok.setText("Guardando…")

        def _done(res):
            self.bok.setEnabled(True); self.bok.setText("Guardar evento")
            if res.ok:
                self.sb.ok(res.mensaje)
                QTimer.singleShot(500, self.accept)
            else:
                self.sb.err(res.mensaje)

        run_async(
            self, ev_bk.guardar_evento,
            self._eid, self._oid, datos, self._evid,
            on_done=_done
        )


# ══════════════════════════════════════════════════════════════
# DIALOGO: Gestionar evento (valor + motivo)
# ══════════════════════════════════════════════════════════════

class DialogGestionar(BaseDialog):
    """Gestion rapida de evento: actualiza motivo y valor de facturacion."""

    def __init__(self, entidad_id: int, ops_id, rol: str,
                 evento: dict, parent=None):
        super().__init__("Gestionar evento - acceso rapido", 560, parent)
        self._eid    = entidad_id
        self._oid    = _ops_safe(ops_id)
        self._rol    = rol
        self._ev     = evento
        self._evid   = evento["evento_id"]
        self._pac_id = evento.get("paciente_id", 0)
        self._build()

    def _build(self):
        lay = self.lay
        ev  = self._ev

        # ── Resumen del evento ─────────────────────────────────
        card = QWidget()
        card.setStyleSheet(
            f"background:{P['card']};border:1px solid {P['border']};"
            f"border-radius:8px;"
        )
        cl = QGridLayout(card)
        cl.setContentsMargins(16, 14, 16, 14); cl.setSpacing(10)

        def _row(lbl_txt, val_txt, fila):
            lb = QLabel(lbl_txt + ":")
            lb.setStyleSheet(
                f"color:{P['txt2']};font-size:12px;background:transparent;"
            )
            vl = QLabel(str(val_txt) if val_txt else "--")
            vl.setWordWrap(True)
            vl.setStyleSheet(
                f"color:{P['txt']};font-size:13px;font-weight:600;background:transparent;"
            )
            cl.addWidget(lb, fila, 0)
            cl.addWidget(vl, fila, 1)

        pac_nom = ev.get("nombre_paciente") or ev.get("paciente_nombre", "")
        tipo_doc = ev.get("tipo_doc", "") or ""
        num_doc  = ev.get("numero_doc", "") or ""
        _row("Paciente",         pac_nom,                               0)
        _row("Documento",        f"{tipo_doc} {num_doc}".strip() or "--", 1)
        _row("Fecha del evento", str(ev.get("fecha_evento", ""))[:10],  2)
        _row("EPS",              ev.get("eps_nombre", "") or "--",      3)
        _row("Tipo afiliacion",
             ev.get("tipo_afiliacion", "") or
             ev.get("tipo_afiliacion_nombre", "") or "--",              4)

        lay.addWidget(card); lay.addSpacing(18)

        # ── Datos editables ────────────────────────────────────
        lay.addWidget(_sec_header("Datos a actualizar"))
        lay.addSpacing(10)

        self.f_motivo = InputF(
            "Motivo de la atencion *",
            "Describe el motivo de la consulta o atencion…"
        )
        self.f_motivo.set(ev.get("motivo", ""))
        lay.addWidget(self.f_motivo); lay.addSpacing(12)

        self.f_admision = InputF(
            "Numero de admision *",
            "Ej: ADM-2024-001"
        )
        self.f_admision.set(ev.get("numero_admision", "") or "")
        lay.addWidget(self.f_admision); lay.addSpacing(12)

        val_actual = float(ev.get("valor") or 0)
        label_valor = "Valor facturado ($)"
        if val_actual > 0:
            label_valor += f"  [valor actual: ${val_actual:,.0f}]"
        self.f_valor = InputF(
            label_valor,
            "Ej: 150000  -- al ingresar valor el evento pasa a Terminado"
        )
        if val_actual > 0:
            self.f_valor.set(f"{val_actual:.2f}")
        lay.addWidget(self.f_valor); lay.addSpacing(12)

        self.f_codigo = InputF(
            "Codigo del evento",
            "Ej: EV-2024-00456  (obligatorio al terminar)"
        )
        self.f_codigo.set(ev.get("codigo_evento", "") or "")
        lay.addWidget(self.f_codigo); lay.addSpacing(12)

        self.f_factura = InputF(
            "Numero de factura",
            "Ej: FE-2024-00123  (obligatorio al terminar)",
        )
        self.f_factura.set(ev.get("numero_factura", "") or "")
        lay.addWidget(self.f_factura); lay.addSpacing(14)

        aviso = QLabel(
            "Al guardar con un valor mayor a 0 el evento pasa a Terminado. "
            "En ese caso, Numero de admision, Codigo del evento y "
            "Numero de factura son obligatorios."
        )
        aviso.setWordWrap(True)
        aviso.setStyleSheet(
            f"color:{P['txt2']};font-size:12px;"
            f"background:rgba(44,106,223,.08);"
            f"border:1px solid {P['border']};"
            f"border-radius:6px;padding:10px 12px;"
        )
        lay.addWidget(aviso); lay.addSpacing(14)

        self.sb = StatusBar(); lay.addWidget(self.sb); lay.addSpacing(12)

        brow = QHBoxLayout()
        bc = _btn("Cancelar", "sec"); bc.clicked.connect(self.reject)
        self.bok = _btn("Guardar cambios"); self.bok.clicked.connect(self._guardar)
        brow.addWidget(bc); brow.addWidget(self.bok)
        lay.addLayout(brow)
        self._fin()

    def _guardar(self):
        self.sb.ocultar()
        if not self.f_motivo.text():
            self.sb.err("El motivo es obligatorio."); return
        if not self.f_admision.text():
            self.f_admision.err("El numero de admision es obligatorio.")
            self.sb.err("El numero de admision es obligatorio."); return

        valor_txt = self.f_valor.text() or "0"
        try:
            valor_num = float(valor_txt)
        except ValueError:
            valor_num = 0

        # Al terminar (valor > 0) los tres campos son obligatorios
        if valor_num > 0:
            errores = []
            if not self.f_admision.text():
                self.f_admision.err("Obligatorio al terminar.")
                errores.append("numero de admision")
            if not self.f_codigo.text():
                self.f_codigo.err("Obligatorio al terminar.")
                errores.append("codigo del evento")
            if not self.f_factura.text():
                self.f_factura.err("Obligatorio al terminar.")
                errores.append("numero de factura")
            if errores:
                self.sb.err(
                    "Para terminar el evento completa: "
                    + ", ".join(errores) + "."
                )
                return
        else:
            self.f_admision.ok()
            self.f_codigo.ok()
            self.f_factura.ok()

        datos = {
            "paciente_id":        self._pac_id,
            "fecha_evento":       str(self._ev.get("fecha_evento", ""))[:10],
            "eps_id":             self._ev.get("eps_id"),
            "tipo_afiliacion_id": self._ev.get("tipo_afiliacion_id"),
            "afiliado_eps":       bool(self._ev.get("afiliado_eps")),
            "motivo":             self.f_motivo.text(),
            "numero_admision":    self.f_admision.text() or None,
            "codigo_evento":      self.f_codigo.text() or None,
            "valor":              valor_txt,
            "numero_factura":     self.f_factura.text() or None,
        }
        self.bok.setEnabled(False); self.bok.setText("Guardando…")

        def _done(res):
            self.bok.setEnabled(True); self.bok.setText("Guardar cambios")
            if res.ok:
                self.sb.ok(res.mensaje)
                QTimer.singleShot(500, self.accept)
            else:
                self.sb.err(res.mensaje)

        run_async(
            self, ev_bk.guardar_evento,
            self._eid, self._oid, datos, self._evid,
            on_done=_done
        )


# ══════════════════════════════════════════════════════════════
# DIALOGO: Ver detalle (solo lectura)
# ══════════════════════════════════════════════════════════════

class DialogVerEvento(BaseDialog):
    def __init__(self, ev: dict, parent=None):
        super().__init__("Detalle completo del evento", 560, parent)

        def _fila(lbl_txt, val, negrita=False):
            row = QHBoxLayout()
            lb = QLabel(lbl_txt + ":"); lb.setFixedWidth(180)
            lb.setStyleSheet(
                f"color:{P['txt2']};font-size:12px;background:transparent;"
            )
            peso = "font-weight:600;" if negrita else ""
            vl = QLabel(str(val) if val else "--")
            vl.setWordWrap(True)
            vl.setStyleSheet(
                f"color:{P['txt']};font-size:13px;{peso}background:transparent;"
            )
            row.addWidget(lb); row.addWidget(vl, 1); row.addStretch()
            return row

        # Seccion paciente
        self.lay.addWidget(_sec_header("Paciente"))
        self.lay.addSpacing(8)
        pac_nom = ev.get("nombre_paciente") or ev.get("paciente_nombre", "")
        tipo_doc = ev.get("tipo_doc", "") or ev.get("paciente_tipo_doc", "")
        num_doc  = ev.get("numero_doc", "") or ev.get("paciente_numero_doc", "")
        self.lay.addLayout(_fila("Nombre completo", pac_nom, True))
        self.lay.addSpacing(6)
        self.lay.addLayout(_fila("Tipo y numero de documento",
                                 f"{tipo_doc} {num_doc}".strip()))
        self.lay.addSpacing(14)

        # Seccion evento
        self.lay.addWidget(_sec_header("Datos del evento"))
        self.lay.addSpacing(8)
        self.lay.addLayout(_fila("Fecha del evento",
                                 str(ev.get("fecha_evento", ""))[:10]))
        self.lay.addSpacing(6)
        self.lay.addLayout(_fila("Motivo de la atencion",
                                 ev.get("motivo", ""), True))
        self.lay.addSpacing(6)
        self.lay.addLayout(_fila("Numero de admision",
                                 ev.get("numero_admision", "") or "--"))
        self.lay.addSpacing(6)
        self.lay.addLayout(_fila("Codigo del evento",
                                 ev.get("codigo_evento", "") or "--"))
        self.lay.addSpacing(6)

        estado_txt = ev.get("estado", "") or ev.get("estado_nombre", "")
        self.lay.addLayout(_fila("Estado actual", estado_txt))
        self.lay.addSpacing(14)

        # Seccion EPS
        self.lay.addWidget(_sec_header("EPS y afiliacion"))
        self.lay.addSpacing(8)
        self.lay.addLayout(_fila("EPS",
                                 ev.get("eps_nombre", "") or "--"))
        self.lay.addSpacing(6)
        self.lay.addLayout(_fila("Afiliado a la EPS",
                                 "Si" if ev.get("afiliado_eps") else "No"))
        self.lay.addSpacing(6)
        afil = (ev.get("tipo_afiliacion") or
                ev.get("tipo_afiliacion_nombre", "") or "--")
        self.lay.addLayout(_fila("Tipo de afiliacion", afil))
        self.lay.addSpacing(14)

        # Seccion facturacion
        self.lay.addWidget(_sec_header("Facturacion"))
        self.lay.addSpacing(8)
        self.lay.addLayout(_fila("Valor facturado",
                                 f"${float(ev.get('valor') or 0):,.0f}", True))
        self.lay.addSpacing(6)
        self.lay.addLayout(_fila("Codigo del evento",
                                 ev.get("codigo_evento", "") or "--"))
        self.lay.addSpacing(6)
        self.lay.addLayout(_fila("Numero de factura",
                                 ev.get("numero_factura", "") or "--"))
        self.lay.addSpacing(14)

        # Seccion auditoria
        self.lay.addWidget(_sec_header("Auditoria"))
        self.lay.addSpacing(8)
        self.lay.addLayout(_fila("Registrado por",
                                 ev.get("ops_nombre", "") or "Administrador"))
        self.lay.addSpacing(6)
        self.lay.addLayout(_fila("Fecha de creacion",
                                 str(ev.get("creado_en", ""))[:16]))
        self.lay.addSpacing(6)
        self.lay.addLayout(_fila("Editable hasta",
                                 str(ev.get("editable_hasta", ""))[:16]))

        self.lay.addSpacing(16)
        bc = _btn("Cerrar", "sec"); bc.clicked.connect(self.accept)
        self.lay.addWidget(bc)
        self._fin()


# ══════════════════════════════════════════════════════════════
# BARRA DE TABS (Todos / Pendientes / Terminados / Inactivos)
# ══════════════════════════════════════════════════════════════

class NavTab(QWidget):
    cambio = Signal(object, bool)

    _TABS: list[tuple[str, object, bool]] = [
        ("Todos",       None, False),
        ("Pendientes",  1,    False),
        ("Terminados",  2,    False),
    ]
    _TABS_ADMIN: list[tuple[str, object, bool]] = [
        ("Todos",       None, False),
        ("Pendientes",  1,    False),
        ("Terminados",  2,    False),
        ("Inactivos",   None, True),
    ]

    def __init__(self, rol: str = "ops", parent=None):
        super().__init__(parent)
        self._rol  = rol
        self._idx  = 0
        self._tabs = self._TABS_ADMIN if rol == "admin" else self._TABS
        self.setStyleSheet("background:transparent;")
        self.setFixedHeight(46)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 6); lay.setSpacing(4)

        self._btns: list[QPushButton] = []
        self._badges: list[QLabel]    = []

        for i, (etq, _, _inact) in enumerate(self._tabs):
            btn_w = QWidget(); btn_w.setStyleSheet("background:transparent;")
            bwl = QHBoxLayout(btn_w)
            bwl.setContentsMargins(0, 0, 0, 0); bwl.setSpacing(0)

            btn = QPushButton(etq)
            btn.setCheckable(True)
            btn.setFixedHeight(38)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setProperty("tab_idx", i)
            btn.setStyleSheet(self._css_btn(False, i))
            btn.clicked.connect(partial(self._seleccionar, i))
            self._btns.append(btn); bwl.addWidget(btn)

            badge = QLabel("")
            badge.setFixedSize(22, 18)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                f"background:{P['muted']};color:{P['white']};"
                f"border-radius:9px;font-size:10px;font-weight:700;"
                f"margin-top:4px;"
            )
            badge.hide()
            self._badges.append(badge); bwl.addWidget(badge)

            lay.addWidget(btn_w)

        lay.addStretch()
        self._seleccionar(0, emit=False)

    def _css_btn(self, activo: bool, idx: int) -> str:
        tab = self._tabs[idx]
        if activo:
            col = (P["warn"] if tab[1] == 1
                   else P["ok"] if tab[1] == 2
                   else P["muted"] if tab[2]
                   else P["acc_h"])
            return (
                f"QPushButton{{background:transparent;color:{col};"
                f"border:none;border-bottom:3px solid {col};"
                f"padding:6px 14px;font-size:13px;font-weight:700;}}"
            )
        return (
            f"QPushButton{{background:transparent;color:{P['txt2']};"
            f"border:none;border-bottom:3px solid transparent;"
            f"padding:6px 14px;font-size:13px;font-weight:500;}}"
            f"QPushButton:hover{{color:{P['txt']};background:{P['input']};"
            f"border-radius:6px;}}"
        )

    def _seleccionar(self, idx: int, emit: bool = True):
        self._idx = idx
        for i, btn in enumerate(self._btns):
            btn.setChecked(i == idx)
            btn.setStyleSheet(self._css_btn(i == idx, i))
        if emit:
            tab = self._tabs[idx]
            self.cambio.emit(tab[1], tab[2])

    def actualizar_badges(self, pendientes: int, terminados: int,
                          total: int, inactivos: int = 0):
        valores = {
            "Todos":      total,
            "Pendientes": pendientes,
            "Terminados": terminados,
            "Inactivos":  inactivos,
        }
        for i, (etq, _, _) in enumerate(self._tabs):
            n = valores.get(etq, 0)
            b = self._badges[i]
            if n > 0:
                b.setText(str(n) if n < 100 else "99+")
                if etq == "Pendientes":
                    bg = P["warn"]
                elif etq == "Terminados":
                    bg = P["ok"]
                elif etq == "Inactivos":
                    bg = P["muted"]
                else:
                    bg = P["accent"]
                b.setStyleSheet(
                    f"background:{bg};color:{P['white']};"
                    f"border-radius:9px;font-size:10px;font-weight:700;"
                    f"margin-top:4px;padding:0 4px;"
                )
                b.show()
            else:
                b.hide()

    def idx_activo(self) -> int:
        return self._idx


def _date_mini() -> QDateEdit:
    de = QDateEdit()
    de.setDate(QDate.currentDate())
    de.setCalendarPopup(True)
    de.setDisplayFormat("dd/MM/yyyy")
    de.setFixedSize(120, 32)
    de.setStyleSheet(
        f"QDateEdit{{background:{P['input']};border:1.5px solid {P['border']};"
        f"border-radius:6px;padding:0 8px;color:{P['txt']};font-size:12px;}}"
        f"QDateEdit:focus{{border-color:{P['focus']};}}"
        f"QDateEdit::drop-down{{border:none;width:20px;}}"
        f"QDateEdit::down-arrow{{"
        f"border-left:4px solid transparent;"
        f"border-right:4px solid transparent;"
        f"border-top:5px solid {P['txt2']};margin-right:6px;}}"
        f"QCalendarWidget{{background:{P['card']};color:{P['txt']};"
        f"border:1.5px solid {P['border']};border-radius:8px;}}"
        f"QCalendarWidget QAbstractItemView:enabled{{"
        f"background:{P['bg']};color:{P['txt']};"
        f"selection-background-color:{P['accent']};"
        f"selection-color:white;}}"
        f"QCalendarWidget QToolButton{{background:{P['card']};"
        f"color:{P['txt']};border:none;border-radius:4px;padding:3px 6px;}}"
        f"QCalendarWidget QToolButton:hover{{background:{P['input']};}}"
        f"QCalendarWidget QWidget#qt_calendar_navigationbar{{"
        f"background:{P['card']};border-bottom:1px solid {P['border']};padding:3px;}}"
    )
    return de


# ══════════════════════════════════════════════════════════════
# KPI CARDS
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

        es_todo = rol in _ROLES_VER_TODO

        if es_todo:
            tarjetas = [
                ("pendientes", "Pendientes",      P["warn"]),
                ("terminados", "Terminados",       P["ok"]),
                ("total",      "Total eventos",    P["txt2"]),
                ("facturado",  "Total facturado",  P["acc_h"]),
            ]
        else:
            tarjetas = [
                ("pendientes", "Mis pendientes",  P["warn"]),
                ("terminados", "Mis terminados",  P["ok"]),
                ("total",      "Mis eventos",     P["txt2"]),
                ("facturado",  "Mi facturado",    P["acc_h"]),
            ]

        for i, (key, etq, color) in enumerate(tarjetas):
            blk = QVBoxLayout()
            n = QLabel("--"); n.setAlignment(Qt.AlignmentFlag.AlignCenter)
            n.setStyleSheet(
                f"color:{color};font-size:22px;"
                f"font-weight:700;background:transparent;"
            )
            lb = QLabel(etq); lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lb.setStyleSheet(
                f"color:{P['txt2']};font-size:11px;background:transparent;"
            )
            blk.addWidget(n); blk.addWidget(lb)
            lay.addLayout(blk)
            self._nums[key] = n
            if i < len(tarjetas) - 1:
                sv = QFrame(); sv.setFrameShape(QFrame.Shape.VLine)
                sv.setStyleSheet(f"background:{P['border']};max-width:1px;")
                lay.addWidget(sv)

    def actualizar(self, r: dict):
        p = int(r.get("eventos_pendientes") or 0)
        t = int(r.get("eventos_terminados") or 0)
        f = float(r.get("total_facturado") or 0)
        tot = int(r.get("total_eventos") or 0)
        if "pendientes" in self._nums: self._nums["pendientes"].setText(str(p))
        if "terminados" in self._nums: self._nums["terminados"].setText(str(t))
        if "total"      in self._nums: self._nums["total"].setText(str(tot))
        if "facturado"  in self._nums: self._nums["facturado"].setText(f"${f:,.0f}")


# ══════════════════════════════════════════════════════════════
# TAB PRINCIPAL DE EVENTOS
# ══════════════════════════════════════════════════════════════

class TabEventos(QWidget):
    """
    Widget embebible. Se adapta al rol:
      - ops:             columnas sin "Registrado por"; boton Nuevo solo si tiene ops_id
      - maestro/entidad: todas las columnas incluyendo "Registrado por"
      - admin:           todas las columnas + opciones de activacion
    """

    # Columnas base y sus anchos
    _COLS_OPS  = ["Fecha", "Paciente", "Documento",
                  "EPS", "Tipo Afiliacion", "Motivo",
                  "N Admision", "Cod Evento", "N Factura", "Valor", "Estado", "Acciones"]
    _COLS_TODO = ["Fecha", "Paciente", "Documento",
                  "EPS", "Tipo Afiliacion", "Motivo",
                  "N Admision", "Cod Evento", "N Factura", "Valor", "Estado",
                  "Registrado por", "Acciones"]

    def __init__(self, rol: str, entidad_id: int, ops_id, parent=None):
        super().__init__(parent)
        self._rol    = rol
        self._eid    = entidad_id
        self._oid    = _ops_safe(ops_id)
        self._estado: int | None = None
        self._incluir_inact: bool = False
        self._periodo = "hoy"
        self._f_desde: str | None = None
        self._f_hasta: str | None = None
        self._ver_todo = rol in _ROLES_VER_TODO

        self._build()
        self._refrescar()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12); root.setSpacing(0)

        # ── Etiqueta de vista segun rol ────────────────────────
        rol_txt = {
            "ops":     "Vista personal — solo tus eventos",
            "maestro": "Vista maestro — todos los eventos de la entidad",
            "entidad": "Vista entidad — todos los eventos registrados",
            "admin":   "Vista administrador — acceso completo",
        }.get(self._rol, "")
        if rol_txt:
            rv = QLabel(rol_txt)
            rv.setStyleSheet(
                f"color:{P['acc_h']};font-size:11px;font-weight:600;"
                f"background:{P['acc_lt']};border:1px solid {P['accent']};"
                f"border-radius:6px;padding:5px 12px;"
            )
            root.addWidget(rv); root.addSpacing(10)

        # ── KPIs ──────────────────────────────────────────────
        self.kpi = KpiCards(rol=self._rol); root.addWidget(self.kpi)
        root.addSpacing(10)

        # ── NavTab ────────────────────────────────────────────
        self._nav = NavTab(rol=self._rol)
        self._nav.cambio.connect(self._on_nav_tab)
        root.addWidget(self._nav)

        sep_nav = QFrame(); sep_nav.setFrameShape(QFrame.Shape.HLine)
        sep_nav.setStyleSheet(
            f"border:none;border-top:1px solid {P['border']};background:transparent;"
        )
        sep_nav.setFixedHeight(1)
        root.addWidget(sep_nav); root.addSpacing(10)

        # ── Barra: buscador + nuevo ────────────────────────────
        bar_top = QWidget(); bar_top.setStyleSheet("background:transparent;")
        btl = QHBoxLayout(bar_top)
        btl.setContentsMargins(0, 0, 0, 0); btl.setSpacing(8)

        self.bus = QLineEdit()
        self.bus.setPlaceholderText(
            "Buscar por nombre del paciente, documento, motivo…"
        )
        self.bus.setMinimumHeight(38)
        self.bus.textChanged.connect(lambda: self._timer_bus.start(400))
        btl.addWidget(self.bus, 1)

        # Boton nuevo: OPS solo puede crear si tiene ops_id valido
        puede_crear = (self._ver_todo or self._oid is not None)
        if puede_crear:
            self.btn_nuevo = _btn("+ Registrar nuevo evento")
            self.btn_nuevo.clicked.connect(self._nuevo)
            btl.addWidget(self.btn_nuevo)

        root.addWidget(bar_top); root.addSpacing(8)

        # ── Filtros de periodo ─────────────────────────────────
        fscroll = QScrollArea()
        fscroll.setWidgetResizable(True)
        fscroll.setFixedHeight(42)
        fscroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        fscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        fscroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            f"QScrollBar:horizontal{{background:transparent;height:4px;}}"
            f"QScrollBar::handle:horizontal{{background:{P['border']};border-radius:2px;}}"
        )
        finner = QWidget(); finner.setStyleSheet("background:transparent;")
        fl = QHBoxLayout(finner)
        fl.setContentsMargins(0, 0, 0, 0); fl.setSpacing(6)

        self._bg_per = QButtonGroup(self)
        periodos = [
            ("hoy",    "Hoy"),
            ("semana", "Esta semana"),
            ("mes",    "Este mes"),
            ("todos",  "Todos"),
        ]
        for pid, ptq in periodos:
            b = _btn(ptq, "filtro"); b.setCheckable(True)
            b.setProperty("periodo", pid)
            self._bg_per.addButton(b); fl.addWidget(b)
            if pid == "hoy": b.setChecked(True)
        self._bg_per.buttonClicked.connect(self._on_periodo)

        fl.addWidget(_vsep())
        fl.addWidget(_lbl("Desde:", 12, P["txt2"]))
        self.f_desde = _date_mini()
        fl.addWidget(self.f_desde)
        fl.addWidget(_lbl("Hasta:", 12, P["txt2"]))
        self.f_hasta = _date_mini()
        fl.addWidget(self.f_hasta)

        b_ap = _btn("Aplicar rango", "sec"); b_ap.setFixedHeight(32)
        b_ap.clicked.connect(self._on_rango); fl.addWidget(b_ap)
        fl.addStretch()

        fscroll.setWidget(finner)
        root.addWidget(fscroll); root.addSpacing(8)

        # ── Tabla ─────────────────────────────────────────────
        cols = self._COLS_TODO if self._ver_todo else self._COLS_OPS
        self.tabla = _make_table(cols)
        root.addWidget(self.tabla, 1)

        # ── Totales ───────────────────────────────────────────
        tot = QWidget(); tot.setStyleSheet("background:transparent;")
        tl = QHBoxLayout(tot)
        tl.setContentsMargins(0, 2, 0, 0); tl.setSpacing(20)
        self._lbl_cnt  = _lbl("", 12, P["txt2"])
        self._lbl_fact = _lbl("", 13, P["ok"], bold=True)
        tl.addStretch(); tl.addWidget(self._lbl_cnt); tl.addWidget(self._lbl_fact)
        root.addWidget(tot)

        self._timer_bus = QTimer()
        self._timer_bus.setSingleShot(True)
        self._timer_bus.timeout.connect(self._cargar)

    # ── Filtros ───────────────────────────────────────────────

    def _on_nav_tab(self, estado_id, incluir_inactivos: bool):
        self._estado        = estado_id
        self._incluir_inact = incluir_inactivos
        self._cargar()

    def _on_periodo(self, btn):
        self._periodo = btn.property("periodo")
        self._f_desde = None; self._f_hasta = None
        d, h = ev_bk.fechas_filtro(self._periodo)
        if d: self.f_desde.setDate(QDate.fromString(d, "yyyy-MM-dd"))
        else: self.f_desde.setDate(QDate.currentDate())
        if h: self.f_hasta.setDate(QDate.fromString(h, "yyyy-MM-dd"))
        else: self.f_hasta.setDate(QDate.currentDate())
        self._cargar()

    def _on_rango(self):
        d = self.f_desde.date().toString("yyyy-MM-dd")
        h = self.f_hasta.date().toString("yyyy-MM-dd")
        if d or h:
            self._f_desde = d or None; self._f_hasta = h or None
            self._bg_per.setExclusive(False)
            for b in self._bg_per.buttons(): b.setChecked(False)
            self._bg_per.setExclusive(True)
            self._cargar()

    # ── Carga ─────────────────────────────────────────────────

    def _refrescar(self):
        if self._f_desde or self._f_hasta:
            d, h = self._f_desde, self._f_hasta
        else:
            d, h = ev_bk.fechas_filtro(self._periodo)
        run_async(
            self, ev_bk.resumen_facturacion,
            self._eid, self._oid, d, h, self._rol,
            on_done=lambda r: self.kpi.actualizar(r) if isinstance(r, dict) else None
        )
        self._cargar()

    def _cargar(self):
        if self._f_desde or self._f_hasta:
            d, h = self._f_desde, self._f_hasta
        else:
            d, h = ev_bk.fechas_filtro(self._periodo)
        run_async(
            self, ev_bk.listar_eventos,
            self._eid, self._oid, self.bus.text(),
            self._estado, d, h, 200, 0,
            self._incluir_inact, self._rol,
            on_done=self._poblar
        )

    def _poblar(self, datos):
        if hasattr(datos, 'ok') and not datos.ok:
            self.tabla.setRowCount(0)
            self._lbl_cnt.setText(f"Error al cargar: {datos.mensaje}")
            self._lbl_cnt.setStyleSheet(f"color:{P['err']};font-size:12px;")
            return
        if not isinstance(datos, list): datos = []
        self._lbl_cnt.setStyleSheet(f"color:{P['txt2']};font-size:12px;")
        self.tabla.setRowCount(0)
        total_f = 0.0
        kpi_pend = sum(1 for d in datos if str(d.get("estado", "")).lower() in ("pendiente", ""))
        kpi_term = sum(1 for d in datos if str(d.get("estado", "")).lower() == "terminado")
        kpi_tot  = len(datos)
        kpi_fact = sum(float(d.get("valor") or 0) for d in datos)
        self.kpi.actualizar({
            "eventos_pendientes": kpi_pend,
            "eventos_terminados": kpi_term,
            "total_eventos":      kpi_tot,
            "total_facturado":    kpi_fact,
        })
        inact = sum(1 for d in datos if not d.get("activo", True))
        self._nav.actualizar_badges(kpi_pend, kpi_term, kpi_tot, inact)

        for d in datos:
            r = self.tabla.rowCount(); self.tabla.insertRow(r)
            self.tabla.setItem(r, 0, _item(str(d.get("fecha_evento", ""))[:10]))
            self.tabla.setItem(r, 1, _item(d.get("nombre_paciente", "")))
            num = (f"{d.get('tipo_doc', '')} {d.get('numero_doc', '')}").strip()
            self.tabla.setItem(r, 2, _item(num))
            self.tabla.setItem(r, 3, _item(d.get("eps_nombre", "") or "--"))
            self.tabla.setItem(r, 4, _item(d.get("tipo_afiliacion", "") or "--"))
            mot = str(d.get("motivo", ""))
            self.tabla.setItem(r, 5, _item(mot[:45] + ("…" if len(mot) > 45 else "")))
            self.tabla.setItem(r, 6, _item(d.get("numero_admision", "") or "--"))
            self.tabla.setItem(r, 7, _item(d.get("codigo_evento", "") or "--"))
            self.tabla.setItem(r, 8, _item(d.get("numero_factura", "") or "--"))
            val = float(d.get("valor") or 0)
            total_f += val
            self.tabla.setItem(r, 9, _item(f"${val:,.0f}"))
            estado_txt = d.get("estado", "Pendiente")
            if not d.get("activo", True): estado_txt = "Inactivo"
            self.tabla.setCellWidget(r, 10, _badge(estado_txt))

            if self._ver_todo:
                # Col 11: Registrado por
                self.tabla.setItem(r, 11, _item(
                    d.get("ops_nombre", "") or "Administrador"
                ))
                self.tabla.setCellWidget(r, 12, self._celdas_acc(d))
            else:
                self.tabla.setCellWidget(r, 11, self._celdas_acc(d))

            self.tabla.setRowHeight(r, 46)

        cnt = datos[0].get("total_registros", len(datos)) if datos else 0
        self._lbl_cnt.setText(f"Total: {cnt} evento(s)")
        self._lbl_fact.setText(f"Facturado: ${total_f:,.0f}")
        QTimer.singleShot(10, self._ajustar_cols)

    def _celdas_acc(self, d: dict) -> QWidget:
        """Menu de acciones diferenciado por rol."""
        w = QWidget(); w.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        evid     = d.get("evento_id")
        editable = d.get("es_editable", False)
        estado   = (d.get("estado") or "").lower()

        btn = QPushButton("  Acciones  ")
        btn.setFixedHeight(32)
        btn.setMinimumWidth(110)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setStyleSheet(
            f"QPushButton{{background:{P['card']};color:{P['txt']};"
            f"border:1.5px solid {P['border']};border-radius:7px;"
            f"padding:0 10px;font-size:12px;font-weight:600;}}"
            f"QPushButton:hover{{background:{P['input']};"
            f"border-color:{P['focus']};color:{P['white']};}}"
            f"QPushButton:pressed{{background:{P['acc_lt']};}}"
        )

        def _abrir_menu():
            menu = QMenu(btn)
            menu.setStyleSheet(
                f"QMenu{{background:{P['card']};color:{P['txt']};"
                f"border:1.5px solid {P['border']};border-radius:8px;"
                f"padding:4px 0;font-size:13px;}}"
                f"QMenu::item{{padding:10px 20px 10px 16px;"
                f"border-radius:4px;margin:1px 4px;}}"
                f"QMenu::item:selected{{background:{P['acc_lt']};"
                f"color:{P['acc_h']};}}"
                f"QMenu::separator{{background:{P['border']};"
                f"height:1px;margin:4px 8px;}}"
            )

            # Ver siempre disponible
            a_ver = menu.addAction("Ver detalle completo")
            a_ver.triggered.connect(partial(self._ver, evid))
            menu.addSeparator()

            # Editar y gestionar si es editable
            if editable:
                a_edit = menu.addAction("Editar evento")
                a_edit.triggered.connect(partial(self._editar, evid))

                a_gest = menu.addAction("Gestionar — actualizar valor/motivo")
                a_gest.triggered.connect(partial(self._gestionar, evid))

                # Desactivar: OPS sus propios, maestro/entidad/admin todos
                puede_desact = (
                    self._rol in _ROLES_VER_TODO or
                    self._oid is not None
                )
                if puede_desact:
                    menu.addSeparator()
                    a_del = menu.addAction("Desactivar evento")
                    a_del.triggered.connect(partial(self._desactivar, evid))

            # Opciones exclusivas admin
            if self._rol == "admin":
                menu.addSeparator()
                activo_ev = d.get("activo", True)
                if not activo_ev:
                    a_on = menu.addAction("Activar evento (reactivar)")
                    a_on.triggered.connect(partial(self._activar, evid))
                if not editable:
                    a_act = menu.addAction("Reactivar ventana de edicion (+7 dias)")
                    a_act.triggered.connect(partial(self._reactivar, evid))

            pos = btn.mapToGlobal(btn.rect().bottomLeft())
            menu.exec(pos)

        btn.clicked.connect(_abrir_menu)
        lay.addWidget(btn); lay.addStretch()
        return w

    # ── Acciones ──────────────────────────────────────────────

    def _nuevo(self):
        dlg = DialogEvento(
            self._eid, self._oid, self._rol,
            parent=self.window()
        )
        if dlg.exec():
            self._refrescar()

    def _editar(self, evid):
        def _on_done(d):
            if not d or not isinstance(d, dict):
                QMessageBox.warning(self, "", "Evento no encontrado."); return
            if not d.get("es_editable"):
                QMessageBox.warning(
                    self, "",
                    "La ventana de edicion ha vencido.\n"
                    "Solo el administrador puede reactivarla."
                ); return
            dlg = DialogEvento(
                self._eid, self._oid, self._rol,
                datos_ini=d, parent=self.window()
            )
            if dlg.exec():
                self._refrescar()
        run_async(self, ev_bk.obtener_evento, self._eid, int(evid), on_done=_on_done)

    def _ver(self, evid):
        def _on_done(d):
            if not d or not isinstance(d, dict):
                QMessageBox.warning(self, "", "Evento no encontrado."); return
            DialogVerEvento(d, self.window()).exec()
        run_async(self, ev_bk.obtener_evento, self._eid, int(evid), on_done=_on_done)

    def _gestionar(self, evid):
        def _on_done(d):
            if not d or not isinstance(d, dict):
                QMessageBox.warning(self, "", "Evento no encontrado."); return
            if not d.get("es_editable"):
                QMessageBox.warning(self, "", "La ventana de edicion ha vencido."); return
            dlg = DialogGestionar(
                self._eid, self._oid, self._rol, d, parent=self.window()
            )
            if dlg.exec():
                self._refrescar()
        run_async(self, ev_bk.obtener_evento, self._eid, int(evid), on_done=_on_done)

    def _desactivar(self, evid):
        if QMessageBox.question(
            self, "Confirmar desactivacion",
            "El evento quedara inactivo pero no se eliminara del sistema.\n"
            "Los administradores podran reactivarlo si es necesario.\n\n"
            "Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes: return
        res = ev_bk.desactivar_evento(self._eid, int(evid), self._oid)
        QMessageBox.information(self, "Resultado", res.mensaje)
        if res.ok: self._refrescar()

    def _activar(self, evid):
        if QMessageBox.question(
            self, "Confirmar activacion",
            "El evento volvera a aparecer en el listado activo.\n\nContinuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes: return
        res = ev_bk.activar_evento(self._eid, int(evid))
        QMessageBox.information(self, "Resultado", res.mensaje)
        if res.ok: self._refrescar()

    def _reactivar(self, evid):
        if QMessageBox.question(
            self, "Reactivar ventana de edicion",
            "Se agregaran 7 dias adicionales para editar este evento.\nContinuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes: return
        res = ev_bk.reactivar_ventana(self._eid, int(evid))
        QMessageBox.information(self, "Resultado", res.mensaje)
        if res.ok: self._refrescar()

    # ── Responsividad ─────────────────────────────────────────

    def _ajustar_cols(self):
        t = self.tabla; vw = t.viewport().width()
        if self._ver_todo:
            # 13 columnas: +Cod Evento entre N Admision y N Factura
            # 0:Fecha 1:Paciente 2:Doc 3:EPS 4:Afil 5:Motivo
            # 6:NAdm  7:CodEvento 8:NFact 9:Valor 10:Estado 11:RegPor 12:Acc
            cols_fijas = 90 + 130 + 110 + 110 + 100 + 110 + 90 + 80 + 90 + 120 + 130
            resto = max(120, vw - cols_fijas)
            t.setColumnWidth(0, 90)    # Fecha
            t.setColumnWidth(2, 130)   # Documento
            t.setColumnWidth(3, 110)   # EPS
            t.setColumnWidth(4, 110)   # Tipo Afiliacion
            t.setColumnWidth(6, 100)   # N Admision
            t.setColumnWidth(7, 110)   # Cod Evento
            t.setColumnWidth(8, 90)    # N Factura
            t.setColumnWidth(9, 80)    # Valor
            t.setColumnWidth(10, 90)   # Estado
            t.setColumnWidth(11, 120)  # Registrado por
            t.setColumnWidth(12, 130)  # Acciones
            t.setColumnWidth(1, int(resto * 0.55))  # Paciente
            t.setColumnWidth(5, int(resto * 0.45))  # Motivo
        else:
            # 12 columnas: sin "Registrado por"
            # 0:Fecha 1:Paciente 2:Doc 3:EPS 4:Afil 5:Motivo
            # 6:NAdm  7:CodEvento 8:NFact 9:Valor 10:Estado 11:Acc
            cols_fijas = 90 + 130 + 110 + 110 + 100 + 110 + 90 + 80 + 90 + 130
            resto = max(120, vw - cols_fijas)
            t.setColumnWidth(0, 90)    # Fecha
            t.setColumnWidth(2, 130)   # Documento
            t.setColumnWidth(3, 110)   # EPS
            t.setColumnWidth(4, 110)   # Tipo Afiliacion
            t.setColumnWidth(6, 100)   # N Admision
            t.setColumnWidth(7, 110)   # Cod Evento
            t.setColumnWidth(8, 90)    # N Factura
            t.setColumnWidth(9, 80)    # Valor
            t.setColumnWidth(10, 90)   # Estado
            t.setColumnWidth(11, 130)  # Acciones
            t.setColumnWidth(1, int(resto * 0.55))  # Paciente
            t.setColumnWidth(5, int(resto * 0.45))  # Motivo

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
        self._ico  = ico; self._lbl = lbl
        self._act  = False; self._exp = True
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(46); self._render()

    def set_activo(self, v): self._act = v; self._render()
    def set_exp(self, v):
        self._exp = v
        self.setFixedWidth(220 if v else 56)
        self._render()

    def _render(self):
        if self._act:
            bg = P["acc_lt"]; c = P["acc_h"]
            bord = f"border-left:3px solid {P['accent']};"; fw = "600"
        else:
            bg = "transparent"; c = P["txt2"]
            bord = "border-left:3px solid transparent;"; fw = "400"
        txt = (f"   {self._ico}   {self._lbl}"
               if self._exp else f"  {self._ico}")
        self.setText(txt)
        self.setStyleSheet(
            f"QPushButton{{background:{bg};color:{c};"
            f"border:none;{bord}border-radius:0;"
            f"padding:0 12px;font-size:13px;"
            f"font-weight:{fw};text-align:left;}}"
            f"QPushButton:hover{{background:"
            f"{P['input'] if not self._act else P['acc_lt']};"
            f"color:{P['txt']};}}"
        )


class Sidebar(QWidget):
    nav = Signal(int)

    # Etiqueta legible segun rol
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

        # Header
        hdr = QWidget(); hdr.setFixedHeight(64)
        hdr.setStyleSheet(
            f"background:{P['card']};border-bottom:1px solid {P['border']};"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(16, 0, 10, 0); hl.setSpacing(10)
        ic = QLabel("S")
        ic.setFixedSize(32, 32)
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ic.setStyleSheet(
            f"background:{P['accent']};color:white;border-radius:8px;"
            f"font-size:16px;font-weight:700;"
        )
        self._logo = QLabel("SIGES")
        self._logo.setStyleSheet(
            f"color:{P['txt']};font-size:14px;font-weight:700;background:transparent;"
        )
        self._tog = QPushButton("◀")
        self._tog.setFixedSize(28, 28)
        self._tog.setStyleSheet(
            f"QPushButton{{background:{P['input']};color:{P['txt2']};"
            f"border:1px solid {P['border']};border-radius:6px;font-size:12px;}}"
            f"QPushButton:hover{{background:{P['border']};color:{P['txt']};}}"
        )
        self._tog.clicked.connect(self.toggle)
        hl.addWidget(ic); hl.addWidget(self._logo, 1); hl.addWidget(self._tog)
        root.addWidget(hdr)

        sec = QWidget()
        sl = QVBoxLayout(sec)
        sl.setContentsMargins(0, 16, 0, 0); sl.setSpacing(2)

        self._sec_lbl = QLabel("  MODULO")
        self._sec_lbl.setStyleSheet(
            f"color:{P['muted']};font-size:10px;font-weight:700;"
            f"letter-spacing:1.5px;padding:0 16px 8px;background:transparent;"
        )
        sl.addWidget(self._sec_lbl)

        b = _NavBtn("E", "Eventos")
        b.setFixedWidth(220); b.set_activo(True)
        b.clicked.connect(lambda: self.nav.emit(0))
        self._btns.append(b); sl.addWidget(b)

        root.addWidget(sec); root.addStretch()

        # Pie
        pie = QWidget(); pie.setFixedHeight(64)
        pie.setStyleSheet(
            f"background:{P['card']};border-top:1px solid {P['border']};"
        )
        pl = QVBoxLayout(pie)
        pl.setContentsMargins(16, 10, 16, 10); pl.setSpacing(2)

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
        w = 220 if self._exp else 56
        self.setFixedWidth(w)
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


# ══════════════════════════════════════════════════════════════
# BOTTOM NAV (< 680px)
# ══════════════════════════════════════════════════════════════

class BottomNav(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(58)
        self.setStyleSheet(
            f"QWidget{{background:{P['card']};border-top:1px solid {P['border']};}}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
        b = QPushButton("E\nEventos")
        b.setCheckable(True); b.setChecked(True)
        b.setStyleSheet(
            f"QPushButton{{background:{P['card']};color:{P['acc_h']};"
            f"border:none;border-top:2px solid {P['accent']};"
            f"padding:4px 2px;font-size:11px;font-weight:700;}}"
        )
        b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay.addWidget(b)


# ══════════════════════════════════════════════════════════════
# TOP BAR
# ══════════════════════════════════════════════════════════════

class TopBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(56)
        self.setStyleSheet(
            f"QWidget{{background:{P['card']};border-bottom:1px solid {P['border']};}}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 0, 24, 0); lay.setSpacing(8)
        r = QLabel("Gestion")
        r.setStyleSheet(f"color:{P['txt2']};font-size:12px;background:transparent;")
        s = QLabel(" / ")
        s.setStyleSheet(f"color:{P['muted']};font-size:12px;background:transparent;")
        self._tit = QLabel("Eventos de Atencion")
        self._tit.setStyleSheet(
            f"color:{P['txt']};font-size:15px;font-weight:700;background:transparent;"
        )
        lay.addWidget(r); lay.addWidget(s); lay.addWidget(self._tit)
        lay.addStretch()
        self._dim = QLabel("")
        self._dim.setStyleSheet(
            f"color:{P['muted']};font-size:11px;background:transparent;"
        )
        lay.addWidget(self._dim)

    def set_dim(self, w, h):
        self._dim.setText(f"{w}x{h}")


# ══════════════════════════════════════════════════════════════
# VENTANA PRINCIPAL
# ══════════════════════════════════════════════════════════════

class EventosWindow(QMainWindow):
    """
    Ventana standalone del modulo de eventos.
    Responsiva: sidebar >=960px | iconos 680-960px | bottom nav <680px.

    Uso:
        win = EventosWindow(
            rol='maestro', entidad_id=1,
            ops_id=None, nombre_usuario='Maria Lopez'
        )
        win.show()
    """
    _BP_COLLAPSE = 960
    _BP_BOTTOM   = 680

    def __init__(self, rol: str, entidad_id: int,
                 ops_id, nombre_usuario: str):
        super().__init__()
        self.setWindowTitle("SIGES - Eventos de Atencion")
        self.setMinimumSize(360, 480)
        self.resize(1024, 720)
        self.setStyleSheet(STYLE)

        central = QWidget()
        self.setCentralWidget(central)
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

        right = QWidget()
        right.setStyleSheet(f"background:{P['bg']};")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)

        self._top = TopBar(); rl.addWidget(self._top)
        self._tab = TabEventos(rol, entidad_id, ops_id)
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

    # Cambia el rol para probar diferentes vistas:
    #   'ops'     -> ve solo sus eventos; necesita ops_id valido
    #   'maestro' -> ve todos los eventos, puede registrar
    #   'entidad' -> igual que maestro
    #   'admin'   -> acceso total
    win = EventosWindow(
        rol="maestro", entidad_id=1,
        ops_id=None, nombre_usuario="Maria Lopez"
    )
    win.show()
    import sys as _sys; _sys.exit(app.exec())


if __name__ == "__main__":
    main()