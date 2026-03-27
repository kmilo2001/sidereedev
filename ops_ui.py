# -*- coding: utf-8 -*-
# =============================================================================
# ops_ui.py
# Módulo de Gestión de Usuarios OPS — PySide6 / SIGES
#
# USO:
#   # Después del login exitoso, construir el ejecutor:
#   ejecutor = bk.construir_ejecutor(rol, ops_id, entidad_id)
#
#   # Insertar en cualquier layout:
#   panel = PanelOps(ejecutor=ejecutor, tipos_doc=tipos, parent=self)
#
#   # O como ventana autónoma (pruebas):
#   win = OpsWindow(ejecutor=ejecutor)
#
# RESPONSIVE:
#   < 640 px  → tarjetas apiladas
#   ≥ 640 px  → tabla completa
#
# PERMISOS (reflejados visualmente):
#   Admin o Maestro → ve botones Activar/Desactivar y Reset contraseña
#   OPS regular     → solo puede ver su propio perfil (sin acceso al módulo)
#   Maestro         → no puede tocarse a sí mismo desde aquí
# =============================================================================

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFrame,
    QScrollArea, QSizePolicy, QListWidget, QListWidgetItem,
    QAbstractItemView, QStackedWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QTabWidget,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QCursor, QColor

import ops_backend as bk

# ══════════════════════════════════════════════════════════════
# PALETA
# ══════════════════════════════════════════════════════════════

C = {
    "bg":        "#090D18",
    "panel":     "#0C1120",
    "card":      "#101726",
    "input":     "#182030",
    "input_f":   "#1C2840",
    "border":    "#1E2D4A",
    "border_f":  "#3B82F6",
    "accent":    "#2563EB",
    "acc_h":     "#3B82F6",
    "acc_dim":   "#1E3355",
    "maestro":   "#D97706",
    "maestro_d": "#451A03",
    "ok":        "#10B981",
    "ok_d":      "#064E3B",
    "err":       "#EF4444",
    "err_d":     "#450A0A",
    "warn":      "#F59E0B",
    "warn_d":    "#451A03",
    "pend":      "#8B5CF6",   # violeta — pendientes
    "pend_d":    "#2E1065",
    "t1":        "#F1F5F9",
    "t2":        "#64748B",
    "t3":        "#2D3D58",
    "white":     "#FFFFFF",
    "row_a":     "#0D1520",
    "row_sel":   "#1E3A6E",
}

FONT_UI = "font-family:'Exo 2','Outfit','Segoe UI',sans-serif;"

STYLE = f"""
QWidget {{
    background:{C['bg']}; color:{C['t1']};
    {FONT_UI} font-size:13px;
}}
QLabel {{ background:transparent; }}
QScrollArea {{ border:none; background:transparent; }}
QLineEdit {{
    background:{C['input']}; border:1.5px solid {C['border']};
    border-radius:8px; padding:9px 14px; color:{C['t1']}; font-size:13px;
}}
QLineEdit:focus {{ border-color:{C['border_f']}; background:{C['input_f']}; }}
QLineEdit:disabled {{ color:{C['t3']}; background:{C['card']}; }}
QScrollBar:vertical {{ background:transparent; width:6px; margin:0; }}
QScrollBar::handle:vertical {{
    background:{C['border']}; border-radius:3px; min-height:20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QTableWidget {{
    background:{C['card']}; border:1px solid {C['border']};
    border-radius:10px; gridline-color:{C['border']};
    color:{C['t1']}; font-size:13px;
    alternate-background-color:{C['row_a']};
    selection-background-color:{C['row_sel']};
    selection-color:{C['t1']};
}}
QTableWidget::item {{ padding:6px 10px; border:none; }}
QHeaderView::section {{
    background:{C['panel']}; color:{C['t2']};
    border:none; border-right:1px solid {C['border']};
    border-bottom:1px solid {C['border']};
    padding:8px 12px; font-size:11px; font-weight:700; letter-spacing:0.5px;
}}
QTabWidget::pane {{
    border:1px solid {C['border']}; border-radius:10px;
    background:{C['card']};
}}
QTabBar::tab {{
    background:{C['panel']}; color:{C['t2']};
    border:none; padding:10px 20px; font-size:13px; font-weight:600;
    border-top-left-radius:8px; border-top-right-radius:8px;
    margin-right:2px;
}}
QTabBar::tab:selected {{
    background:{C['card']}; color:{C['t1']};
    border-bottom:2px solid {C['accent']};
}}
QTabBar::tab:hover:!selected {{ color:{C['t1']}; background:{C['input']}; }}
"""


# ══════════════════════════════════════════════════════════════
# FÁBRICA DE WIDGETS
# ══════════════════════════════════════════════════════════════

def lbl(text: str, size=13, color=None, bold=False, wrap=False) -> QLabel:
    lb = QLabel(text)
    c  = color or C["t1"]
    fw = "700" if bold else "400"
    lb.setStyleSheet(
        f"color:{c}; font-size:{size}px; font-weight:{fw}; background:transparent;"
    )
    if wrap:
        lb.setWordWrap(True)
    return lb


def sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet(f"border:none; background:{C['border']};")
    return f


def btn(text: str, estilo="primary", parent=None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    estilos = {
        "primary":   (f"QPushButton{{background:{C['accent']};color:{C['white']};border:none;"
                      f"border-radius:8px;padding:10px 20px;font-size:13px;font-weight:700;}}"
                      f"QPushButton:hover{{background:{C['acc_h']};}}"
                      f"QPushButton:pressed{{background:#1D4ED8;}}"
                      f"QPushButton:disabled{{background:{C['t3']};color:{C['bg']};}}"),
        "secondary": (f"QPushButton{{background:transparent;color:{C['t2']};"
                      f"border:1.5px solid {C['border']};border-radius:8px;"
                      f"padding:9px 18px;font-size:13px;font-weight:500;}}"
                      f"QPushButton:hover{{border-color:{C['border_f']};color:{C['t1']};"
                      f"background:{C['input']};}}"),
        "danger":    (f"QPushButton{{background:{C['err_d']};color:{C['err']};"
                      f"border:1px solid {C['err']};border-radius:8px;"
                      f"padding:8px 14px;font-size:12px;font-weight:700;}}"
                      f"QPushButton:hover{{background:rgba(239,68,68,0.25);}}"),
        "success":   (f"QPushButton{{background:{C['ok_d']};color:{C['ok']};"
                      f"border:1px solid {C['ok']};border-radius:8px;"
                      f"padding:8px 14px;font-size:12px;font-weight:700;}}"
                      f"QPushButton:hover{{background:rgba(16,185,129,0.25);}}"),
        "warn":      (f"QPushButton{{background:{C['warn_d']};color:{C['warn']};"
                      f"border:1px solid {C['warn']};border-radius:8px;"
                      f"padding:8px 14px;font-size:12px;font-weight:700;}}"
                      f"QPushButton:hover{{background:rgba(245,158,11,0.25);}}"),
        "pend":      (f"QPushButton{{background:{C['pend_d']};color:{C['pend']};"
                      f"border:1px solid {C['pend']};border-radius:8px;"
                      f"padding:8px 14px;font-size:12px;font-weight:700;}}"
                      f"QPushButton:hover{{background:rgba(139,92,246,0.25);}}"),
        "icon":      (f"QPushButton{{background:transparent;color:{C['t2']};"
                      f"border:none;border-radius:6px;padding:5px 9px;font-size:15px;}}"
                      f"QPushButton:hover{{background:{C['input']};color:{C['t1']};}}"),
    }
    b.setStyleSheet(estilos.get(estilo, estilos["primary"]))
    return b


def _it(text: str) -> QTableWidgetItem:
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

    def _show(self, msg: str, bg: str, border: str, color: str):
        self.setStyleSheet(
            f"background:{bg}; border:1px solid {border}; border-radius:8px;"
            f"color:{color}; padding:10px 14px; font-size:12px;"
        )
        self.setText(msg)
        self.show()
        w = self.window()
        if w and w != self:
            w.adjustSize()

    def ok(self, m: str):   self._show(m, C["ok_d"],   C["ok"],   C["ok"])
    def err(self, m: str):  self._show(m, C["err_d"],  C["err"],  C["err"])
    def warn(self, m: str): self._show(m, C["warn_d"], C["warn"], C["warn"])
    def pend(self, m: str): self._show(m, C["pend_d"], C["pend"], C["pend"])
    def ocultar(self):      self.hide()


class InputField(QWidget):
    returnPressed = Signal()

    def __init__(self, label: str, ph="", pw=False, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent; border:none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(lbl(label, size=11, color=C["t2"]))
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

    def text(self) -> str:  return self.inp.text().strip()
    def set(self, v):       self.inp.setText(str(v) if v is not None else "")
    def clear(self):        self.inp.clear()
    def set_error(self, m): self._err.setText(m); self._err.show()
    def clear_error(self):  self._err.hide()

    def setEnabled(self, v: bool):
        self.inp.setEnabled(v)
        super().setEnabled(v)


class ComboField(QWidget):
    selectionChanged = Signal(object)
    _ITEM_H = 36
    _MAX_ROWS = 7

    def __init__(self, label_text: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent; border:none;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._items: list[tuple[str, object]] = []
        self._sel = -1
        self._open = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(lbl(label_text, size=11, color=C["t2"]))
        self._btn = QPushButton()
        self._btn.setMinimumHeight(40)
        self._btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn.clicked.connect(self._toggle)
        self._render_btn(False)
        lay.addWidget(self._btn)
        self._list = QListWidget()
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setStyleSheet(
            f"QListWidget{{background:{C['card']};border:1.5px solid {C['border_f']};"
            f"border-top:none;border-bottom-left-radius:8px;"
            f"border-bottom-right-radius:8px;outline:none;padding:2px 0;}}"
            f"QListWidget::item{{min-height:{self._ITEM_H}px;padding:0 14px;"
            f"color:{C['t1']};border:none;}}"
            f"QListWidget::item:hover{{background:{C['input']};}}"
            f"QListWidget::item:selected{{background:{C['accent']};color:white;}}"
        )
        self._list.hide()
        self._list.itemClicked.connect(self._pick)
        lay.addWidget(self._list)

    def _btn_css(self, open_):
        bc = C["border_f"] if open_ else C["border"]
        rb = "0" if open_ else "8px"
        return (f"QPushButton{{background:{C['input']};color:{C['t1']};"
                f"border:1.5px solid {bc};border-radius:8px;"
                f"border-bottom-left-radius:{rb};border-bottom-right-radius:{rb};"
                f"font-size:13px;text-align:left;padding:0 14px;}}"
                f"QPushButton::menu-indicator{{width:0;}}")

    def _render_btn(self, open_):
        self._btn.setText(f"{self.text() or '— Selecciona —'}   {'▴' if open_ else '▾'}")
        self._btn.setStyleSheet(self._btn_css(open_))

    def _toggle(self): self._close() if self._open else self._open_list()

    def _open_list(self):
        if not self._items: return
        self._list.setFixedHeight(
            min(len(self._items), self._MAX_ROWS) * self._ITEM_H + 8
        )
        self._list.show()
        self._open = True
        self._render_btn(True)
        if self._sel >= 0:
            self._list.setCurrentRow(self._sel)

    def _close(self):
        self._list.hide()
        self._open = False
        self._render_btn(False)

    def _pick(self, item):
        self._sel = self._list.row(item)
        self._render_btn(False)
        self._close()
        self.selectionChanged.emit(self.data())

    def add(self, text: str, data=None):
        self._items.append((text, data))
        li = QListWidgetItem(text)
        li.setData(Qt.ItemDataRole.UserRole, data)
        self._list.addItem(li)

    def data(self): return self._items[self._sel][1] if self._sel >= 0 else None
    def text(self) -> str: return self._items[self._sel][0] if self._sel >= 0 else ""
    def reset(self):
        self._items.clear(); self._list.clear(); self._sel = -1; self._render_btn(False)

    def set_by_data(self, val):
        for i, (_, d) in enumerate(self._items):
            if d == val:
                self._sel = i; self._render_btn(False); return

    def setEnabled(self, v: bool):
        self._btn.setEnabled(v)
        if not v: self._close()
        super().setEnabled(v)


# ══════════════════════════════════════════════════════════════
# DIÁLOGO BASE
# ══════════════════════════════════════════════════════════════

class BaseDialog(QDialog):
    def __init__(self, titulo: str, ancho=520, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setMinimumWidth(min(ancho, 380))
        self.setMaximumWidth(740)
        self.setStyleSheet(STYLE + f"QDialog{{background:{C['bg']};}}")
        self.resize(ancho, 200)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QWidget()
        hdr.setStyleSheet(f"background:{C['panel']}; border:none;")
        hl = QVBoxLayout(hdr)
        hl.setContentsMargins(28, 22, 28, 0)
        hl.setSpacing(0)
        hl.addWidget(lbl(titulo, size=18, bold=True))
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
        inner.setStyleSheet(f"background:{C['bg']}; border:none;")
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(28, 20, 28, 26)
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
        max_h  = int(screen.availableGeometry().height() * 0.88) if screen else 860
        self.resize(self.width(), max(300, min(self.sizeHint().height(), max_h)))


# ══════════════════════════════════════════════════════════════
# BADGES
# ══════════════════════════════════════════════════════════════

def _badge_estado(activo: bool) -> QWidget:
    w = QWidget()
    w.setStyleSheet("background:transparent;")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(4, 2, 4, 2)
    lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if activo:
        lb = QLabel("● Activo")
        lb.setStyleSheet(
            f"background:rgba(16,185,129,0.14);color:{C['ok']};"
            f"border:1px solid {C['ok']};border-radius:10px;"
            f"padding:3px 10px;font-size:11px;font-weight:700;"
        )
    else:
        lb = QLabel("○ Inactivo")
        lb.setStyleSheet(
            f"background:rgba(139,92,246,0.14);color:{C['pend']};"
            f"border:1px solid {C['pend']};border-radius:10px;"
            f"padding:3px 10px;font-size:11px;font-weight:700;"
        )
    lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(lb)
    return w


def _badge_maestro() -> QLabel:
    lb = QLabel("♛ Maestro")
    lb.setStyleSheet(
        f"background:rgba(217,119,6,0.18);color:{C['maestro']};"
        f"border:1px solid {C['maestro']};border-radius:10px;"
        f"padding:3px 10px;font-size:11px;font-weight:700;"
    )
    lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lb


def _badge_sesion(n: int) -> QLabel | None:
    if not n:
        return None
    lb = QLabel(f"⚡ {n} sesión{'es' if n != 1 else ''}")
    lb.setStyleSheet(
        f"background:rgba(37,99,235,0.18);color:{C['acc_h']};"
        f"border:1px solid {C['acc_h']};border-radius:10px;"
        f"padding:3px 10px;font-size:11px;font-weight:700;"
    )
    lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lb


# ══════════════════════════════════════════════════════════════
# AVISO DE PERMISO (cuando el usuario no puede hacer algo)
# ══════════════════════════════════════════════════════════════

def _aviso_sin_permiso(parent=None):
    QMessageBox.information(
        parent,
        "Sin permiso",
        "Esta acción solo la puede realizar la entidad administradora "
        "o el usuario Maestro.\n\n"
        "Si eres un usuario OPS registrado, solicita al administrador "
        "que active tu cuenta.",
    )


# ══════════════════════════════════════════════════════════════
# DIÁLOGO: VER DETALLE
# ══════════════════════════════════════════════════════════════

class DialogVerOps(BaseDialog):
    def __init__(self, datos: dict, parent=None):
        super().__init__("Detalle del usuario", 480, parent)
        self._build(datos)

    def _build(self, d: dict):
        lay = self.lay

        # Badges
        badge_row = QHBoxLayout()
        if d.get("es_maestro"):
            badge_row.addWidget(_badge_maestro())
        badge_row.addWidget(_badge_estado(d.get("activo", True)))
        bs = _badge_sesion(d.get("sesiones_activas", 0))
        if bs:
            badge_row.addWidget(bs)
        badge_row.addStretch()
        lay.addLayout(badge_row)
        lay.addSpacing(16)

        # Datos
        campos = [
            ("Nombre",       d.get("nombre_completo", "")),
            ("Tipo doc.",     d.get("tipo_doc_nombre", "")),
            ("Documento",    d.get("numero_documento", "")),
            ("Correo",       d.get("correo", "")),
            ("WhatsApp",     d.get("whatsapp") or "—"),
            ("Estado",       "Activo ✓" if d.get("activo") else "Inactivo — pendiente"),
            ("Creado",       str(d.get("creado_en", ""))[:19] or "—"),
            ("Actualizado",  str(d.get("actualizado_en", ""))[:19] or "—"),
        ]
        for etiqueta, valor in campos:
            row = QHBoxLayout()
            lb_e = lbl(etiqueta + ":", size=12, color=C["t2"])
            lb_e.setFixedWidth(120)
            lb_v = lbl(str(valor), size=13)
            lb_v.setWordWrap(True)
            row.addWidget(lb_e)
            row.addWidget(lb_v, 1)
            lay.addLayout(row)
            lay.addSpacing(8)

        lay.addSpacing(14)
        lay.addWidget(sep())
        lay.addSpacing(14)
        bc = btn("Cerrar", "secondary")
        bc.clicked.connect(self.accept)
        lay.addWidget(bc)
        self._fin()


# ══════════════════════════════════════════════════════════════
# DIÁLOGO: CREAR / EDITAR
# ══════════════════════════════════════════════════════════════

class DialogFormOps(BaseDialog):
    def __init__(
        self,
        ejecutor:   dict,
        tipos_doc:  list[dict],
        datos_ini:  dict | None = None,
        parent=None,
    ):
        titulo = "Editar usuario" if datos_ini else "Crear usuario OPS"
        super().__init__(titulo, 540, parent)
        self._ejecutor = ejecutor
        self._eid      = ejecutor["entidad_id"]
        self._tipos    = tipos_doc
        self._editando = datos_ini
        self._oid      = datos_ini["ops_id"] if datos_ini else None
        self._build()

    def _build(self):
        lay = self.lay
        editando = self._editando is not None

        if not editando:
            nota = QLabel(
                "💡  Para crear el usuario Maestro del sistema, el nombre "
                "debe comenzar con  Maestro  (ej: Maestro Juan García)."
            )
            nota.setWordWrap(True)
            nota.setStyleSheet(
                f"background:rgba(217,119,6,0.1); border:1px solid {C['maestro']};"
                f"border-radius:8px; padding:10px 14px; color:{C['maestro']}; font-size:12px;"
            )
            lay.addWidget(nota)
            lay.addSpacing(16)

        if not editando:
            self.f_tipo = ComboField("Tipo de documento *")
            self.f_tipo.add("— Selecciona —", None)
            for td in self._tipos:
                self.f_tipo.add(f"{td['abreviatura']}  —  {td['nombre']}", td["abreviatura"])
            lay.addWidget(self.f_tipo)
            lay.addSpacing(12)

            self.f_doc = InputField("Número de documento *", "Ej: 1234567890")
            lay.addWidget(self.f_doc)
            lay.addSpacing(12)

        self.f_nombre = InputField("Nombre completo *", "Ej: Juan Pérez García")
        lay.addWidget(self.f_nombre)
        lay.addSpacing(12)

        self.f_correo = InputField("Correo electrónico *", "correo@ejemplo.com")
        lay.addWidget(self.f_correo)
        lay.addSpacing(12)

        self.f_wa = InputField("WhatsApp *", "+57 300 000 0000")
        lay.addWidget(self.f_wa)
        lay.addSpacing(12)

        if not editando:
            self.f_pw  = InputField("Contraseña *", "Mínimo 8 caracteres", pw=True)
            self.f_pw2 = InputField("Confirmar contraseña *", "", pw=True)
            lay.addWidget(self.f_pw)
            lay.addSpacing(12)
            lay.addWidget(self.f_pw2)
            lay.addSpacing(12)

        self.sb = StatusBar()
        lay.addWidget(self.sb)
        lay.addSpacing(14)

        row = QHBoxLayout()
        bc = btn("Cancelar", "secondary")
        bc.clicked.connect(self.reject)
        self.bok = btn("Guardar cambios" if editando else "Crear usuario")
        self.bok.clicked.connect(self._guardar)
        row.addWidget(bc)
        row.addWidget(self.bok)
        lay.addLayout(row)
        self._fin()

        if editando:
            self.f_nombre.set(self._editando.get("nombre_completo"))
            self.f_correo.set(self._editando.get("correo"))
            self.f_wa.set(self._editando.get("whatsapp") or "")

    def _guardar(self):
        self.sb.ocultar()
        self.bok.setEnabled(False)
        lbl_ok = "Guardar cambios" if self._editando else "Crear usuario"
        self.bok.setText("Guardando…")

        def done(res: bk.Resultado):
            self.bok.setEnabled(True)
            self.bok.setText(lbl_ok)
            if res.ok:
                self.sb.ok(res.mensaje)
                QTimer.singleShot(600, self.accept)
            else:
                self.sb.err(res.mensaje)

        if self._editando:
            datos = {
                "nombre_completo": self.f_nombre.text(),
                "correo":          self.f_correo.text(),
                "whatsapp":        self.f_wa.text(),
            }
            run_async(bk.actualizar_ops, self._eid, self._oid, datos, on_done=done)
        else:
            tipo = self.f_tipo.data()
            if tipo is None:
                self.sb.err("Selecciona el tipo de documento.")
                self.bok.setEnabled(True)
                self.bok.setText("Crear usuario")
                return
            datos = {
                "tipo_doc_abrev":     tipo,
                "numero_documento":   self.f_doc.text(),
                "nombre_completo":    self.f_nombre.text(),
                "correo":             self.f_correo.text(),
                "whatsapp":           self.f_wa.text(),
                "password":           self.f_pw.text(),
                "confirmar_password": self.f_pw2.text(),
            }
            run_async(bk.crear_ops, self._eid, datos, on_done=done)


# ══════════════════════════════════════════════════════════════
# DIÁLOGO: CAMBIAR CONTRASEÑA (reset por admin/maestro)
# ══════════════════════════════════════════════════════════════

class DialogResetPw(BaseDialog):
    def __init__(self, ejecutor: dict, datos_ops: dict, parent=None):
        super().__init__("Resetear contraseña", 440, parent)
        self._ejecutor  = ejecutor
        self._datos_ops = datos_ops
        self._build()

    def _build(self):
        lay = self.lay
        d   = self._datos_ops

        nota = QLabel(
            f"Resetando contraseña de:\n{d.get('nombre_completo','')}\n\n"
            "Las sesiones activas de este usuario serán cerradas automáticamente."
        )
        nota.setWordWrap(True)
        nota.setStyleSheet(
            f"background:{C['card']}; border:1px solid {C['border']};"
            f"border-radius:8px; padding:12px 14px; color:{C['t2']}; font-size:12px;"
        )
        lay.addWidget(nota)
        lay.addSpacing(16)

        self.f_pw  = InputField("Nueva contraseña *", "Mínimo 8 caracteres", pw=True)
        self.f_pw2 = InputField("Confirmar contraseña *", "", pw=True)
        lay.addWidget(self.f_pw)
        lay.addSpacing(12)
        lay.addWidget(self.f_pw2)
        lay.addSpacing(16)

        self.sb = StatusBar()
        lay.addWidget(self.sb)
        lay.addSpacing(14)

        row = QHBoxLayout()
        bc  = btn("Cancelar", "secondary")
        bc.clicked.connect(self.reject)
        self.bok = btn("Actualizar contraseña")
        self.bok.clicked.connect(self._guardar)
        row.addWidget(bc)
        row.addWidget(self.bok)
        lay.addLayout(row)
        self._fin()

    def _guardar(self):
        self.sb.ocultar()
        self.bok.setEnabled(False)
        self.bok.setText("Guardando…")

        def done(res: bk.Resultado):
            self.bok.setEnabled(True)
            self.bok.setText("Actualizar contraseña")
            if res.ok:
                self.sb.ok(res.mensaje)
                QTimer.singleShot(900, self.accept)
            else:
                self.sb.err(res.mensaje)

        run_async(
            bk.cambiar_password_ops,
            self._ejecutor,
            int(self._datos_ops["ops_id"]),
            self.f_pw.text(),
            self.f_pw2.text(),
            on_done=done,
        )


# ══════════════════════════════════════════════════════════════
# BOTONES DE ACCIÓN POR FILA (tabla)
# ══════════════════════════════════════════════════════════════

def _botones_fila(d: dict, ejecutor: dict, callbacks: dict) -> QWidget:
    """
    Genera la celda de acciones para una fila de la tabla.
    Los botones de activar/desactivar y reset solo se muestran
    si el ejecutor tiene permiso.
    """
    w = QWidget()
    w.setStyleSheet("background:transparent;")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(4, 2, 4, 2)
    lay.setSpacing(4)
    lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

    # Ver — siempre visible
    b_ver = btn("👁", "icon")
    b_ver.setToolTip("Ver detalle")
    b_ver.setFixedSize(32, 32)
    b_ver.clicked.connect(lambda: callbacks["ver"](d))
    lay.addWidget(b_ver)

    # Editar — admin o maestro
    if bk.puede_gestionar_estados(ejecutor):
        b_ed = btn("✏", "icon")
        b_ed.setToolTip("Editar datos")
        b_ed.setFixedSize(32, 32)
        b_ed.clicked.connect(lambda: callbacks["editar"](d))
        lay.addWidget(b_ed)

    # Reset contraseña — solo si puede y no es el objetivo maestro
    objetivo_es_maestro = d.get("es_maestro", False)
    if bk.puede_resetear_password(ejecutor, objetivo_es_maestro):
        b_pw = btn("🔑", "icon")
        b_pw.setToolTip("Resetear contraseña")
        b_pw.setFixedSize(32, 32)
        b_pw.clicked.connect(lambda: callbacks["pw"](d))
        lay.addWidget(b_pw)

    # Activar / Desactivar — admin o maestro, no al maestro, no a sí mismo
    if bk.puede_gestionar_estados(ejecutor) and not objetivo_es_maestro:
        ejecutor_ops_id = ejecutor.get("ops_id")
        es_uno_mismo    = ejecutor_ops_id and ejecutor_ops_id == int(d.get("ops_id", -1))
        if not es_uno_mismo:
            activo = d.get("activo", True)
            if activo:
                b_est = btn("⛔", "icon")
                b_est.setToolTip("Desactivar usuario")
            else:
                b_est = btn("✅", "icon")
                b_est.setToolTip("Activar usuario")
            b_est.setFixedSize(32, 32)
            b_est.clicked.connect(lambda: callbacks["estado"](d, not activo))
            lay.addWidget(b_est)

    return w


# ══════════════════════════════════════════════════════════════
# TABLA OPS
# ══════════════════════════════════════════════════════════════

COLS_TABLA = ["", "Tipo", "Documento", "Nombre", "Correo", "WhatsApp", "Estado", "Acciones"]
#              ^badge_maestro/sesion


def _nueva_tabla() -> QTableWidget:
    t = QTableWidget()
    t.setColumnCount(len(COLS_TABLA))
    t.setHorizontalHeaderLabels(COLS_TABLA)
    t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(False)
    t.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
    t.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
    t.setColumnWidth(0, 32)    # badge
    t.setColumnWidth(1, 55)    # tipo
    t.setColumnWidth(2, 110)   # documento
    t.setColumnWidth(5, 120)   # whatsapp
    t.setColumnWidth(6, 90)    # estado
    t.setColumnWidth(7, 160)   # acciones
    t.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return t


# ══════════════════════════════════════════════════════════════
# TARJETA OPS (modo compacto)
# ══════════════════════════════════════════════════════════════

class TarjetaOps(QWidget):
    def __init__(self, d: dict, ejecutor: dict, callbacks: dict, parent=None):
        super().__init__(parent)
        self._d = d
        self.setObjectName("tarjeta")
        self.setStyleSheet(
            f"QWidget#tarjeta{{background:{C['card']};border:1px solid {C['border']};"
            f"border-radius:10px;}}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)

        # Nombre + badges
        row1 = QHBoxLayout()
        nombre = lbl(d.get("nombre_completo", ""), size=13, bold=True)
        nombre.setWordWrap(True)
        row1.addWidget(nombre, 1)
        if d.get("es_maestro"):
            row1.addWidget(_badge_maestro())
        row1.addWidget(_badge_estado(d.get("activo", True)))
        lay.addLayout(row1)

        # Doc + correo
        lay.addWidget(lbl(
            f"{d.get('tipo_doc','')}  {d.get('numero_documento','')}",
            size=12, color=C["t2"]
        ))
        lay.addWidget(lbl(d.get("correo", ""), size=12, color=C["t2"]))

        sesiones = d.get("sesiones_activas", 0)
        if sesiones:
            lay.addWidget(lbl(f"⚡ {sesiones} sesión(es) activa(s)", size=11, color=C["acc_h"]))

        lay.addWidget(sep())

        # Botones
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        b_ver = btn("Ver", "secondary")
        b_ver.setFixedHeight(32)
        b_ver.clicked.connect(lambda: callbacks["ver"](d))
        btn_row.addWidget(b_ver)

        if bk.puede_gestionar_estados(ejecutor):
            b_ed = btn("Editar", "secondary")
            b_ed.setFixedHeight(32)
            b_ed.clicked.connect(lambda: callbacks["editar"](d))
            btn_row.addWidget(b_ed)

        objetivo_es_maestro = d.get("es_maestro", False)
        if bk.puede_resetear_password(ejecutor, objetivo_es_maestro):
            b_pw = btn("🔑 Contraseña", "warn")
            b_pw.setFixedHeight(32)
            b_pw.clicked.connect(lambda: callbacks["pw"](d))
            btn_row.addWidget(b_pw)

        if bk.puede_gestionar_estados(ejecutor) and not objetivo_es_maestro:
            ejecutor_ops_id = ejecutor.get("ops_id")
            es_uno_mismo    = ejecutor_ops_id and ejecutor_ops_id == int(d.get("ops_id", -1))
            if not es_uno_mismo:
                activo = d.get("activo", True)
                b_est  = btn("Desactivar" if activo else "✅ Activar",
                             "danger" if activo else "success")
                b_est.setFixedHeight(32)
                b_est.clicked.connect(lambda: callbacks["estado"](d, not activo))
                btn_row.addWidget(b_est)

        lay.addLayout(btn_row)


# ══════════════════════════════════════════════════════════════
# HEADER DEL MÓDULO (estadísticas)
# ══════════════════════════════════════════════════════════════

class HeaderOps(QWidget):
    busqueda_cambiada = Signal(str)
    nuevo_clicked     = Signal()
    filtro_cambiado   = Signal(str)   # 'todos' | 'activos' | 'inactivos'

    def __init__(self, ejecutor: dict, parent=None):
        super().__init__(parent)
        self._ejecutor  = ejecutor
        self._eid       = ejecutor["entidad_id"]
        self._filtro_actual = "todos"
        self.setStyleSheet("background:transparent; border:none;")
        self._build()
        self._cargar_stats()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        # Título + contexto del ejecutor
        title_row = QHBoxLayout()
        title_row.addWidget(lbl("Usuarios OPS", size=22, bold=True))
        title_row.addSpacing(12)

        # Badge del ejecutor actual
        rol = self._ejecutor.get("rol", "")
        if rol == "admin":
            tag_txt   = "Entidad Admin"
            tag_color = C["acc_h"]
            tag_bg    = C["acc_dim"]
        elif self._ejecutor.get("es_maestro"):
            tag_txt   = "♛ Maestro"
            tag_color = C["maestro"]
            tag_bg    = C["maestro_d"]
        else:
            tag_txt   = "OPS"
            tag_color = C["t2"]
            tag_bg    = C["card"]

        tag = QLabel(f"  {tag_txt}  ")
        tag.setStyleSheet(
            f"background:{tag_bg};color:{tag_color};"
            f"border:1px solid {tag_color};border-radius:8px;"
            f"padding:4px 10px;font-size:11px;font-weight:700;"
        )
        title_row.addWidget(tag)
        title_row.addStretch()

        # Botón nuevo solo para admin/maestro
        if bk.puede_gestionar_estados(self._ejecutor):
            b_nuevo = btn("＋  Nuevo usuario")
            b_nuevo.setMinimumHeight(40)
            b_nuevo.clicked.connect(self.nuevo_clicked)
            title_row.addWidget(b_nuevo)

        lay.addLayout(title_row)

        # Tarjetas de estadísticas
        stats_row = QHBoxLayout()
        stats_row.setSpacing(8)
        self._sc = {}
        for key, etiqueta, color in [
            ("total",           "Total",         C["t2"]),
            ("activos",         "Activos",       C["ok"]),
            ("inactivos",       "Pendientes",    C["pend"]),
            ("sesiones_en_curso", "En sesión",   C["acc_h"]),
        ]:
            card = QWidget()
            card.setStyleSheet(
                f"QWidget{{background:{C['card']};border:1px solid {C['border']};"
                f"border-radius:8px;}}"
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 8, 12, 8)
            cl.setSpacing(2)
            v = lbl("—", size=20, color=color, bold=True)
            t = lbl(etiqueta, size=11, color=C["t2"])
            cl.addWidget(v)
            cl.addWidget(t)
            card._val = v
            self._sc[key] = card
            stats_row.addWidget(card)

        # Maestro
        card_m = QWidget()
        card_m.setStyleSheet(
            f"QWidget{{background:{C['card']};border:1px solid {C['border']};"
            f"border-radius:8px;}}"
        )
        cm = QVBoxLayout(card_m)
        cm.setContentsMargins(12, 8, 12, 8)
        cm.setSpacing(2)
        self._maestro_val = lbl("—", size=14, color=C["err"], bold=True)
        self._maestro_tit = lbl("Maestro", size=11, color=C["t2"])
        cm.addWidget(self._maestro_val)
        cm.addWidget(self._maestro_tit)
        stats_row.addWidget(card_m)
        lay.addLayout(stats_row)

        # Barra de búsqueda + filtros
        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Buscar por nombre, documento o correo…")
        self._search.setMinimumHeight(40)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.busqueda_cambiada.emit(self._search.text()))
        self._search.textChanged.connect(lambda: self._timer.start(350))
        search_row.addWidget(self._search, 1)

        # Filtros rápidos
        for f_id, f_txt in [("todos", "Todos"), ("activos", "Activos"), ("inactivos", "Pendientes")]:
            b = QPushButton(f_txt)
            b.setCheckable(True)
            b.setMinimumHeight(40)
            b.setMinimumWidth(96)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            b.setProperty("f_id", f_id)
            b.clicked.connect(lambda _, fi=f_id: self._set_filtro(fi))
            setattr(self, f"_fb_{f_id}", b)
            search_row.addWidget(b)

        lay.addLayout(search_row)
        self._render_filtros()

    def _set_filtro(self, f_id: str):
        self._filtro_actual = f_id
        self._render_filtros()
        self.filtro_cambiado.emit(f_id)

    def _render_filtros(self):
        estilos = {
            "todos":    (C["t2"],    C["input"],  C["border"]),
            "activos":  (C["ok"],    C["ok_d"],   C["ok"]),
            "inactivos":(C["pend"],  C["pend_d"], C["pend"]),
        }
        for f_id, (color, bg, border) in estilos.items():
            b = getattr(self, f"_fb_{f_id}")
            sel = (f_id == self._filtro_actual)
            b.setChecked(sel)
            if sel:
                b.setStyleSheet(
                    f"QPushButton{{background:{bg};color:{color};"
                    f"border:1px solid {border};border-radius:8px;"
                    f"padding:0 12px;font-size:12px;font-weight:700;}}"
                )
            else:
                b.setStyleSheet(
                    f"QPushButton{{background:{C['input']};color:{C['t2']};"
                    f"border:1.5px solid {C['border']};border-radius:8px;"
                    f"padding:0 12px;font-size:12px;}}"
                    f"QPushButton:hover{{border-color:{C['border_f']};color:{C['t1']};}}"
                )

    def _cargar_stats(self):
        def done(s):
            if not isinstance(s, dict):
                return
            for key in ("total", "activos", "inactivos", "sesiones_en_curso"):
                if key in self._sc:
                    self._sc[key]._val.setText(str(s.get(key, "—")))
            existe = s.get("maestro_existe", False)
            self._maestro_val.setText("✓ Creado" if existe else "✗ Sin crear")
            self._maestro_val.setStyleSheet(
                f"color:{C['ok']};font-size:14px;font-weight:700;background:transparent;"
                if existe else
                f"color:{C['err']};font-size:14px;font-weight:700;background:transparent;"
            )

        run_async(bk.stats_ops, self._eid, on_done=done)

    def refrescar(self):
        self._cargar_stats()


# ══════════════════════════════════════════════════════════════
# PANEL PRINCIPAL
# ══════════════════════════════════════════════════════════════

class PanelOps(QWidget):
    """
    Widget autónomo de gestión OPS.

    Parámetros:
        ejecutor   dict construido con bk.construir_ejecutor()
        tipos_doc  lista de tipos de documento
    """
    _BP = 640   # px — breakpoint tabla/tarjetas

    def __init__(self, ejecutor: dict, tipos_doc: list[dict], parent=None):
        super().__init__(parent)
        self._ejecutor = ejecutor
        self._eid      = ejecutor["entidad_id"]
        self._tipos    = tipos_doc
        self._datos:   list[dict] = []
        self._filtro   = ""
        self._f_estado = "todos"
        self._compacto = False
        self.setStyleSheet(STYLE)
        self._build()
        self._cargar()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(14)

        self._header = HeaderOps(self._ejecutor)
        self._header.busqueda_cambiada.connect(self._on_busqueda)
        self._header.nuevo_clicked.connect(self._nuevo)
        self._header.filtro_cambiado.connect(self._on_filtro)
        lay.addWidget(self._header)
        lay.addWidget(sep())

        # Banner de pendientes (solo visible si hay inactivos y el ejecutor puede activar)
        self._banner_pend = self._mk_banner_pendientes()
        lay.addWidget(self._banner_pend)
        self._banner_pend.hide()

        # Stack tabla / tarjetas
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background:transparent; border:none;")

        self._tabla = _nueva_tabla()
        self._stack.addWidget(self._tabla)

        # Tarjetas
        self._scroll_c = QScrollArea()
        self._scroll_c.setWidgetResizable(True)
        self._scroll_c.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_c.setStyleSheet("background:transparent; border:none;")
        self._cont_c = QWidget()
        self._cont_c.setStyleSheet("background:transparent; border:none;")
        self._lay_c  = QVBoxLayout(self._cont_c)
        self._lay_c.setContentsMargins(0, 0, 0, 0)
        self._lay_c.setSpacing(10)
        self._scroll_c.setWidget(self._cont_c)
        self._stack.addWidget(self._scroll_c)
        lay.addWidget(self._stack, 1)

        self._lbl_vacio = lbl(
            "No se encontraron usuarios que coincidan.", size=13, color=C["t2"]
        )
        self._lbl_vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_vacio.hide()
        lay.addWidget(self._lbl_vacio)

    def _mk_banner_pendientes(self) -> QWidget:
        """Banner que informa que hay usuarios inactivos esperando activación."""
        w = QWidget()
        w.setStyleSheet(
            f"QWidget{{background:{C['pend_d']};border:1px solid {C['pend']};"
            f"border-radius:8px;}}"
        )
        lay = QHBoxLayout(w)
        lay.setContentsMargins(14, 10, 14, 10)
        self._lbl_pend_txt = lbl("", size=12, color=C["pend"], bold=True)
        lay.addWidget(self._lbl_pend_txt, 1)

        if bk.puede_gestionar_estados(self._ejecutor):
            b_ver = btn("Ver pendientes", "pend")
            b_ver.setMinimumHeight(34)
            b_ver.clicked.connect(lambda: self._header._set_filtro("inactivos"))
            b_ver.clicked.connect(lambda: self._header.filtro_cambiado.emit("inactivos"))
            lay.addWidget(b_ver)

            b_todos = btn("Activar todos", "success")
            b_todos.setMinimumHeight(34)
            b_todos.clicked.connect(self._activar_todos)
            lay.addWidget(b_todos)

        return w

    # ── Carga ─────────────────────────────────────────────────

    def _cargar(self):
        solo_activos   = (self._f_estado == "activos")
        solo_inactivos = (self._f_estado == "inactivos")
        run_async(
            bk.listar_ops,
            self._eid, self._filtro, solo_activos, solo_inactivos,
            on_done=self._poblar,
        )

    def _poblar(self, datos):
        self._datos = datos if isinstance(datos, list) else []
        self._lbl_vacio.setVisible(len(self._datos) == 0)

        # Banner de pendientes
        inactivos_total = sum(1 for d in self._datos if not d.get("activo", True))
        if self._f_estado == "todos" and inactivos_total > 0:
            s = "s" if inactivos_total != 1 else ""
            self._lbl_pend_txt.setText(
                f"⚠  Hay {inactivos_total} usuario{s} inactivo{s} esperando activación."
            )
            self._banner_pend.show()
        else:
            self._banner_pend.hide()

        if self._compacto:
            self._poblar_tarjetas()
        else:
            self._poblar_tabla()

        self._header.refrescar()

    def _poblar_tabla(self):
        t = self._tabla
        t.setRowCount(0)
        cb = self._callbacks()
        for d in self._datos:
            r = t.rowCount()
            t.insertRow(r)

            # Col 0 — ícono maestro o sesión
            badge_w = QWidget()
            badge_w.setStyleSheet("background:transparent;")
            bl = QHBoxLayout(badge_w)
            bl.setContentsMargins(2, 2, 2, 2)
            bl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if d.get("es_maestro"):
                ic = QLabel("♛")
                ic.setStyleSheet(f"color:{C['maestro']};font-size:14px;background:transparent;")
                bl.addWidget(ic)
            elif d.get("sesiones_activas", 0):
                ic = QLabel("⚡")
                ic.setStyleSheet(f"color:{C['acc_h']};font-size:13px;background:transparent;")
                bl.addWidget(ic)
            t.setCellWidget(r, 0, badge_w)

            t.setItem(r, 1, _it(d.get("tipo_doc", "")))

            # Documento
            it_doc = _it(d.get("numero_documento", ""))
            if d.get("es_maestro"):
                it_doc.setForeground(QColor(C["maestro"]))
            t.setItem(r, 2, it_doc)

            it_nom = _it(d.get("nombre_completo", ""))
            if d.get("es_maestro"):
                it_nom.setForeground(QColor(C["maestro"]))
            elif not d.get("activo", True):
                it_nom.setForeground(QColor(C["t3"]))
            t.setItem(r, 3, it_nom)

            t.setItem(r, 4, _it(d.get("correo", "")))
            t.setItem(r, 5, _it(d.get("whatsapp") or "—"))
            t.setCellWidget(r, 6, _badge_estado(d.get("activo", True)))
            t.setCellWidget(r, 7, _botones_fila(d, self._ejecutor, cb))
            t.setRowHeight(r, 50)

    def _poblar_tarjetas(self):
        while self._lay_c.count():
            item = self._lay_c.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        cb = self._callbacks()
        for d in self._datos:
            card = TarjetaOps(d, self._ejecutor, cb)
            self._lay_c.addWidget(card)
        self._lay_c.addStretch()

    def _callbacks(self) -> dict:
        return {
            "ver":    self._ver,
            "editar": self._editar,
            "pw":     self._pw,
            "estado": self._estado,
        }

    # ── Acciones ──────────────────────────────────────────────

    def _nuevo(self):
        dlg = DialogFormOps(self._ejecutor, self._tipos, parent=self)
        if dlg.exec():
            self._cargar()

    def _ver(self, d: dict):
        datos = bk.obtener_ops(self._eid, int(d["ops_id"]))
        if datos:
            DialogVerOps(datos, self).exec()
        else:
            QMessageBox.warning(self, "Error", "Usuario no encontrado.")

    def _editar(self, d: dict):
        if not bk.puede_gestionar_estados(self._ejecutor):
            _aviso_sin_permiso(self)
            return
        datos = bk.obtener_ops(self._eid, int(d["ops_id"]))
        if not datos:
            QMessageBox.warning(self, "Error", "Usuario no encontrado.")
            return
        dlg = DialogFormOps(self._ejecutor, self._tipos, datos_ini=datos, parent=self)
        if dlg.exec():
            self._cargar()

    def _pw(self, d: dict):
        if not bk.puede_gestionar_estados(self._ejecutor):
            _aviso_sin_permiso(self)
            return
        datos = bk.obtener_ops(self._eid, int(d["ops_id"]))
        if not datos:
            return
        if datos.get("es_maestro"):
            QMessageBox.information(
                self, "Usuario Maestro",
                "El Maestro debe cambiar su contraseña desde el login "
                "usando la opción de recuperación."
            )
            return
        DialogResetPw(self._ejecutor, datos, self).exec()

    def _estado(self, d: dict, nuevo_activo: bool):
        if not bk.puede_gestionar_estados(self._ejecutor):
            _aviso_sin_permiso(self)
            return
        nombre = d.get("nombre_completo", "")
        accion = "activar" if nuevo_activo else "desactivar"
        resp = QMessageBox.question(
            self, f"Confirmar {accion}",
            f"¿Deseas {accion} al usuario '{nombre}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        res = bk.cambiar_estado_ops(self._ejecutor, int(d["ops_id"]), nuevo_activo)
        if res.ok:
            self._cargar()
        else:
            QMessageBox.warning(self, "Error", res.mensaje)

    def _activar_todos(self):
        if not bk.puede_gestionar_estados(self._ejecutor):
            _aviso_sin_permiso(self)
            return
        resp = QMessageBox.question(
            self, "Activar todos los pendientes",
            "¿Deseas activar a todos los usuarios inactivos de esta entidad?\n"
            "Esta acción les dará acceso inmediato al sistema.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        res = bk.activar_todos_pendientes(self._ejecutor)
        if res.ok:
            self._cargar()
            QMessageBox.information(self, "Listo", res.mensaje)
        else:
            QMessageBox.warning(self, "Error", res.mensaje)

    # ── Filtros ───────────────────────────────────────────────

    def _on_busqueda(self, texto: str):
        self._filtro = texto
        self._cargar()

    def _on_filtro(self, f_estado: str):
        self._f_estado = f_estado
        self._cargar()

    # ── Responsive ───────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = event.size().width()
        nuevo_compacto = w < self._BP
        if nuevo_compacto != self._compacto:
            self._compacto = nuevo_compacto
            self._stack.setCurrentIndex(1 if nuevo_compacto else 0)
            if nuevo_compacto:
                self._poblar_tarjetas()
            else:
                self._poblar_tabla()

        if not self._compacto:
            disponible = max(200, w - 40)
            fijo = 32 + 55 + 110 + 120 + 90 + 160
            elastico = max(80, (disponible - fijo) // 2)
            self._tabla.setColumnWidth(3, elastico)
            self._tabla.setColumnWidth(4, elastico)


# ══════════════════════════════════════════════════════════════
# VENTANA AUTÓNOMA (pruebas / standalone)
# ══════════════════════════════════════════════════════════════

class OpsWindow(QMainWindow):
    """
    Ventana completa de gestión OPS para uso autónomo o pruebas.

    Uso:
        ejecutor = bk.construir_ejecutor(rol='admin', ops_id=None, entidad_id=1)
        win = OpsWindow(ejecutor=ejecutor)
        win.show()
    """

    def __init__(self, ejecutor: dict):
        super().__init__()
        self.setWindowTitle("SIGES — Gestión de Usuarios OPS")
        self.setMinimumSize(360, 500)
        self.resize(1240, 800)
        self.setStyleSheet(STYLE)

        self._ejecutor = ejecutor
        self._panel: PanelOps | None = None

        central = QWidget()
        self.setCentralWidget(central)
        self._root = QVBoxLayout(central)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)

        # Top bar
        top = QWidget()
        top.setFixedHeight(54)
        top.setStyleSheet(
            f"QWidget{{background:{C['panel']};border-bottom:1px solid {C['border']};}}"
        )
        tl = QHBoxLayout(top)
        tl.setContentsMargins(24, 0, 24, 0)
        tl.addWidget(lbl("⚕", size=22, color=C["acc_h"]))
        nombre_lbl = QLabel("SIGES")
        nombre_lbl.setStyleSheet(
            f"color:{C['white']};font-size:15px;font-weight:800;"
            f"letter-spacing:3px;background:transparent;"
        )
        tl.addWidget(nombre_lbl)
        tl.addWidget(lbl("  /  ", size=15, color=C["t3"]))
        tl.addWidget(lbl("Gestión de Usuarios OPS", size=14, color=C["t2"]))
        tl.addStretch()
        self._root.addWidget(top)

        # Placeholder mientras carga
        self._ph = lbl("Cargando módulo…", size=14, color=C["t2"])
        self._ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._root.addWidget(self._ph, 1)

        run_async(bk.obtener_tipos_documento, on_done=self._tipos_listos)

    def _tipos_listos(self, tipos):
        tipos = tipos if isinstance(tipos, list) else []
        self._ph.hide()
        self._root.removeWidget(self._ph)
        self._panel = PanelOps(self._ejecutor, tipos, self)
        self._root.addWidget(self._panel, 1)


# ══════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Ejemplo: ejecutor tipo admin
    ejecutor = bk.construir_ejecutor(rol="admin", ops_id=None, entidad_id=1)
    win = OpsWindow(ejecutor=ejecutor)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
