# -*- coding: utf-8 -*-
# =============================================================================
# pacientes_ui.py
# Modulo de Gestion de Pacientes -- PySide6 / SIGES
#
# ACCESO:
#   Admin (entidad)  -> acceso completo + carga masiva + plantilla
#   Maestro          -> acceso completo + carga masiva + plantilla
#   OPS regular      -> puede crear, editar, activar/desactivar pacientes
#                       SIN carga masiva ni plantilla (solo formulario uno a uno)
#
# BUGS CORREGIDOS respecto a version anterior:
#   1. OPS regular ya puede acceder al formulario de nuevo paciente.
#   2. Los catalogos (tipos_doc, eps, afiliacion) se cargan en paralelo
#      al arrancar el panel. El boton "Nuevo" espera a que esten listos
#      mostrando un aviso si aun no cargaron, sin bloquear la UI.
#   3. La pantalla de bloqueo solo aparece si el ejecutor no tiene
#      ninguno de los roles validos (sesion invalida).
#
# INTEGRACION:
#   from ops_backend import construir_ejecutor
#   ejecutor = construir_ejecutor(rol, ops_id, entidad_id)
#   panel = PanelPacientes(ejecutor=ejecutor, entidad_id=eid, parent=self)
# =============================================================================

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFrame,
    QScrollArea, QSizePolicy, QAbstractItemView,
    QStackedWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QButtonGroup,
    QRadioButton, QFileDialog, QComboBox, QProgressBar,
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer, Q_ARG, QMetaObject
from PySide6.QtGui import QCursor, QColor, QResizeEvent

import pacientes_backend as pbk

# ══════════════════════════════════════════════════════════════
# PALETA
# ══════════════════════════════════════════════════════════════

C = {
    "bg":       "#080E18",
    "panel":    "#0B1220",
    "card":     "#0F1828",
    "input":    "#162030",
    "input_f":  "#1A2840",
    "border":   "#1E3050",
    "border_f": "#0EA5E9",
    "accent":   "#0369A1",
    "acc_h":    "#0EA5E9",
    "acc_dim":  "#0C2740",
    "ok":       "#10B981",
    "ok_d":     "#064E3B",
    "err":      "#EF4444",
    "err_d":    "#450A0A",
    "warn":     "#F59E0B",
    "warn_d":   "#451A03",
    "info":     "#6366F1",
    "info_d":   "#1E1B4B",
    "t1":       "#E8F4FD",
    "t2":       "#7DB8D9",
    "t3":       "#1E4060",
    "white":    "#FFFFFF",
    "row_a":    "#0C1622",
    "row_sel":  "#0C2740",
}

FONT = "font-family:'Exo 2','Outfit','Segoe UI',sans-serif;"

STYLE = f"""
QWidget {{
    background:{C['bg']}; color:{C['t1']};
    {FONT} font-size:13px;
}}
QLabel {{ background:transparent; }}
QScrollArea {{ border:none; background:transparent; }}
QLineEdit {{
    background:{C['input']}; border:1.5px solid {C['border']};
    border-radius:8px; padding:9px 14px; color:{C['t1']}; font-size:13px;
}}
QLineEdit:focus  {{ border-color:{C['border_f']}; background:{C['input_f']}; }}
QLineEdit:disabled {{ color:{C['t3']}; background:{C['card']}; }}
QComboBox {{
    background:{C['input']}; border:1.5px solid {C['border']};
    border-radius:8px; padding:8px 36px 8px 14px;
    color:{C['t1']}; font-size:13px; min-height:40px;
}}
QComboBox:focus {{ border-color:{C['border_f']}; background:{C['input_f']}; }}
QComboBox:hover {{ border-color:{C['t2']}; }}
QComboBox:disabled {{ color:{C['t3']}; background:{C['card']}; }}
QComboBox::drop-down {{
    subcontrol-origin:padding; subcontrol-position:top right;
    width:32px; border:none;
    border-left:1px solid {C['border']};
    border-top-right-radius:7px; border-bottom-right-radius:7px;
    background:{C['input']};
}}
QComboBox::down-arrow {{
    image:none;
    border-left:5px solid transparent;
    border-right:5px solid transparent;
    border-top:6px solid {C['t2']};
    width:0; height:0;
}}
QComboBox::down-arrow:hover {{ border-top-color:{C['acc_h']}; }}
QComboBox QAbstractItemView {{
    background:{C['card']}; color:{C['t1']};
    border:1.5px solid {C['border_f']}; border-radius:6px;
    padding:4px; outline:none;
    selection-background-color:{C['accent']}; selection-color:{C['white']};
}}
QComboBox QAbstractItemView::item {{
    min-height:32px; padding:4px 12px; border-radius:4px;
}}
QComboBox QAbstractItemView::item:hover {{
    background:{C['acc_dim']}; color:{C['t1']};
}}
QScrollBar:vertical {{ background:transparent; width:6px; margin:0; }}
QScrollBar::handle:vertical {{ background:{C['border']}; border-radius:3px; min-height:20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QTableWidget {{
    background:{C['card']}; border:1px solid {C['border']};
    border-radius:10px; gridline-color:{C['border']};
    color:{C['t1']}; font-size:13px;
    alternate-background-color:{C['row_a']};
    selection-background-color:{C['row_sel']}; selection-color:{C['t1']};
}}
QTableWidget::item {{ padding:5px 9px; border:none; }}
QHeaderView::section {{
    background:{C['panel']}; color:{C['t2']};
    border:none; border-right:1px solid {C['border']};
    border-bottom:1px solid {C['border']};
    padding:7px 9px; font-size:11px; font-weight:700; letter-spacing:0.3px;
}}
QRadioButton {{ color:{C['t1']}; spacing:6px; background:transparent; }}
QRadioButton::indicator {{
    width:15px; height:15px;
    border:1.5px solid {C['border']}; border-radius:7px; background:{C['input']};
}}
QRadioButton::indicator:checked {{ background:{C['accent']}; border-color:{C['acc_h']}; }}
"""

BP_CARD   = 660
BP_NARROW = 900


# ══════════════════════════════════════════════════════════════
# HELPERS DE WIDGET
# ══════════════════════════════════════════════════════════════

def lbl(text, size=13, color=None, bold=False, wrap=False):
    lb = QLabel(str(text))
    lb.setStyleSheet(
        f"color:{color or C['t1']};font-size:{size}px;"
        f"font-weight:{'700' if bold else '400'};background:transparent;"
    )
    if wrap:
        lb.setWordWrap(True)
    return lb


def sep():
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet(f"border:none;background:{C['border']};")
    return f


def btn(text, estilo="primary", parent=None):
    b = QPushButton(text, parent)
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    S = {
        "primary":   (f"QPushButton{{background:{C['accent']};color:{C['white']};border:none;"
                      f"border-radius:8px;padding:9px 18px;font-size:13px;font-weight:700;}}"
                      f"QPushButton:hover{{background:{C['acc_h']};}}"
                      f"QPushButton:disabled{{background:{C['t3']};color:{C['bg']};}}"),
        "secondary": (f"QPushButton{{background:transparent;color:{C['t2']};"
                      f"border:1.5px solid {C['border']};border-radius:8px;"
                      f"padding:8px 16px;font-size:13px;}}"
                      f"QPushButton:hover{{border-color:{C['border_f']};color:{C['t1']};"
                      f"background:{C['input']};}}"),
        "danger":    (f"QPushButton{{background:{C['err_d']};color:{C['err']};"
                      f"border:1px solid {C['err']};border-radius:8px;"
                      f"padding:7px 12px;font-size:12px;font-weight:700;}}"
                      f"QPushButton:hover{{background:rgba(239,68,68,0.25);}}"),
        "success":   (f"QPushButton{{background:{C['ok_d']};color:{C['ok']};"
                      f"border:1px solid {C['ok']};border-radius:8px;"
                      f"padding:7px 12px;font-size:12px;font-weight:700;}}"
                      f"QPushButton:hover{{background:rgba(16,185,129,0.25);}}"),
        "warn":      (f"QPushButton{{background:{C['warn_d']};color:{C['warn']};"
                      f"border:1px solid {C['warn']};border-radius:8px;"
                      f"padding:7px 12px;font-size:12px;font-weight:700;}}"
                      f"QPushButton:hover{{background:rgba(245,158,11,0.25);}}"),
        "info":      (f"QPushButton{{background:{C['info_d']};color:{C['info']};"
                      f"border:1px solid {C['info']};border-radius:8px;"
                      f"padding:7px 12px;font-size:12px;font-weight:700;}}"
                      f"QPushButton:hover{{background:rgba(99,102,241,0.25);}}"),
        "icon":      (f"QPushButton{{background:transparent;color:{C['t2']};"
                      f"border:none;border-radius:6px;padding:4px 8px;font-size:15px;}}"
                      f"QPushButton:hover{{background:{C['input']};color:{C['t1']};}}"),
    }
    b.setStyleSheet(S.get(estilo, S["primary"]))
    return b


def _it(text):
    it = QTableWidgetItem(str(text) if text is not None else "")
    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return it


# ══════════════════════════════════════════════════════════════
# WORKER ASINCRONO
# ══════════════════════════════════════════════════════════════

class _Worker(QThread):
    done     = Signal(object)
    progreso = Signal(int, int)   # procesadas, total

    def __init__(self, fn, args, kw):
        super().__init__()
        self._fn, self._args, self._kw = fn, args, kw
        self.setTerminationEnabled(True)

    def run(self):
        try:
            import inspect
            sig = inspect.signature(self._fn)
            if "on_progreso" in sig.parameters:
                self._kw["on_progreso"] = lambda p, t: self.progreso.emit(p, t)
            self.done.emit(self._fn(*self._args, **self._kw))
        except Exception as e:
            self.done.emit(pbk.Resultado(False, str(e)))


_workers: list = []


def run_async(fn, *args, on_done=None, on_progreso=None, **kw):
    w = _Worker(fn, args, kw)
    _workers.append(w)
    if on_done:
        w.done.connect(on_done)
    if on_progreso:
        w.progreso.connect(on_progreso)
    w.done.connect(lambda _: _workers.remove(w) if w in _workers else None)
    w.start()
    return w


# ══════════════════════════════════════════════════════════════
# DIÁLOGO DE PROGRESO (carga masiva) — no bloqueante
# ══════════════════════════════════════════════════════════════

class DialogProgresoCarga(QDialog):
    """
    Ventana de progreso NO modal para la carga masiva.
    - Muestra barra de progreso real con porcentaje.
    - La X funciona: el usuario puede cerrarla sin detener la carga.
    - Se cierra automáticamente al terminar si no fue cerrada antes.
    - El botón cambia de "Cancelar" a "Ver resultado" al terminar.
    """

    def __init__(self, nombre_archivo: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Carga masiva en progreso")
        self.setModal(False)
        self.setMinimumWidth(460)
        self._terminado = False
        self._resultado_pendiente: pbk.Resultado | None = None

        C_local = {
            "bg": "#080E18", "panel": "#0B1220", "card": "#0F1828",
            "input": "#162030", "border": "#1E3050", "border_f": "#0EA5E9",
            "accent": "#0369A1", "acc_h": "#0EA5E9",
            "t1": "#E8F4FD", "t2": "#7DB8D9", "t3": "#1E4060",
        }

        self.setStyleSheet(
            f"QWidget{{background:{C_local['bg']};color:{C_local['t1']};"
            f"font-family:'Exo 2','Segoe UI',sans-serif;font-size:13px;}}"
            f"QProgressBar{{background:{C_local['input']};"
            f"border:1.5px solid {C_local['border']};border-radius:8px;"
            f"height:20px;text-align:center;color:{C_local['t1']};}}"
            f"QProgressBar::chunk{{background:{C_local['accent']};border-radius:7px;}}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        self._lbl_titulo = QLabel("⟳  Procesando carga masiva...")
        self._lbl_titulo.setStyleSheet(
            f"color:{C_local['t1']};font-size:14px;font-weight:700;"
        )
        lay.addWidget(self._lbl_titulo)

        lbl_arch = QLabel(f"Archivo: {nombre_archivo}")
        lbl_arch.setStyleSheet(f"color:{C_local['t2']};font-size:11px;")
        lbl_arch.setWordWrap(True)
        lay.addWidget(lbl_arch)

        self._barra = QProgressBar()
        self._barra.setRange(0, 100)
        self._barra.setValue(0)
        self._barra.setFormat("Iniciando...")
        self._barra.setMinimumHeight(22)
        lay.addWidget(self._barra)

        self._lbl_cnt = QLabel("Preparando archivo...")
        self._lbl_cnt.setStyleSheet(f"color:{C_local['t2']};font-size:12px;")
        lay.addWidget(self._lbl_cnt)

        self._lbl_nota = QLabel(
            "Puedes cerrar esta ventana — la carga continúa en segundo plano."
        )
        self._lbl_nota.setWordWrap(True)
        self._lbl_nota.setStyleSheet(f"color:{C_local['t3']};font-size:11px;")
        lay.addWidget(self._lbl_nota)

        self._btn_cerrar = QPushButton("Cerrar ventana")
        self._btn_cerrar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_cerrar.setStyleSheet(
            f"QPushButton{{background:transparent;color:{C_local['t2']};"
            f"border:1.5px solid {C_local['border']};border-radius:8px;"
            f"padding:8px 16px;font-size:13px;}}"
            f"QPushButton:hover{{border-color:{C_local['border_f']};"
            f"color:{C_local['t1']};background:{C_local['input']};}}"
        )
        self._btn_cerrar.clicked.connect(self.accept)
        lay.addWidget(self._btn_cerrar)

        self.adjustSize()

    def actualizar(self, procesadas: int, total: int):
        """Llamado desde el worker vía señal progreso."""
        if total <= 0:
            return
        pct = int(procesadas * 100 / total)
        self._barra.setValue(pct)
        self._barra.setFormat(f"{pct}%")
        self._lbl_cnt.setText(f"{procesadas:,} / {total:,} filas procesadas")

    def marcar_completado(self):
        """Indica que la carga terminó — cambia el título y el botón."""
        self._terminado = True
        self._lbl_titulo.setText("✓  Carga completada")
        self._barra.setValue(100)
        self._barra.setFormat("100% — Completado")
        self._lbl_nota.setText("La carga ha finalizado correctamente.")
        self._btn_cerrar.setText("Ver resultado")
        self._btn_cerrar.setStyleSheet(
            f"QPushButton{{background:#0369A1;color:white;"
            f"border:none;border-radius:8px;"
            f"padding:8px 16px;font-size:13px;font-weight:700;}}"
            f"QPushButton:hover{{background:#0EA5E9;}}"
        )


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

    def ok(self, m):   self._show(m, C["ok_d"],   C["ok"],   C["ok"])
    def err(self, m):  self._show(m, C["err_d"],  C["err"],  C["err"])
    def warn(self, m): self._show(m, C["warn_d"], C["warn"], C["warn"])
    def info(self, m): self._show(m, C["info_d"], C["info"], C["info"])
    def ocultar(self): self.hide()


class InputField(QWidget):
    returnPressed = Signal()

    def __init__(self, label, ph="", pw=False, required=False, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;border:none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        # Etiqueta con asterisco si es requerido
        etq_txt = label + (" *" if required else "")
        etq = QLabel(etq_txt)
        etq.setStyleSheet(
            f"color:{C['t2']};font-size:11px;font-weight:600;"
            f"background:transparent;letter-spacing:0.2px;"
        )
        lay.addWidget(etq)

        self.inp = QLineEdit()
        self.inp.setPlaceholderText(ph)
        self.inp.setMinimumHeight(42)
        self.inp.setStyleSheet(
            f"QLineEdit{{"
            f"background:{C['input']};border:1.5px solid {C['border']};"
            f"border-radius:8px;padding:9px 14px;"
            f"color:{C['t1']};font-size:13px;"
            f"}}"
            f"QLineEdit:focus{{"
            f"border-color:{C['border_f']};background:{C['input_f']};"
            f"}}"
            f"QLineEdit:hover{{"
            f"border-color:{C['t2']};"
            f"}}"
            f"QLineEdit:disabled{{"
            f"color:{C['t3']};background:{C['card']};"
            f"border-color:{C['border']};"
            f"}}"
        )
        if pw:
            self.inp.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp.returnPressed.connect(self.returnPressed)
        lay.addWidget(self.inp)

        self._err = QLabel("")
        self._err.setStyleSheet(
            f"color:{C['err']};font-size:11px;background:transparent;"
        )
        self._err.hide()
        lay.addWidget(self._err)

    def text(self):         return self.inp.text().strip()
    def set(self, v):       self.inp.setText(str(v) if v is not None else "")
    def clear(self):        self.inp.clear()
    def set_error(self, m): self._err.setText(m); self._err.show()
    def clear_error(self):  self._err.hide()
    def setEnabled(self, v): self.inp.setEnabled(v); super().setEnabled(v)


class ComboField(QWidget):
    """QComboBox nativo con estilo explicito garantizado."""
    selectionChanged = Signal(object)

    _CSS = (
        f"QComboBox{{"
        f"background:{C['input']};border:1.5px solid {C['border']};"
        f"border-radius:8px;padding:8px 36px 8px 14px;"
        f"color:{C['t1']};font-size:13px;min-height:42px;"
        f"}}"
        f"QComboBox:focus{{border-color:{C['border_f']};background:{C['input_f']};}}"
        f"QComboBox:hover{{border-color:{C['t2']};}}"
        f"QComboBox:disabled{{color:{C['t3']};background:{C['card']};"
        f"border-color:{C['border']};}}"
        f"QComboBox::drop-down{{"
        f"subcontrol-origin:padding;subcontrol-position:top right;"
        f"width:32px;border:none;"
        f"border-left:1px solid {C['border']};"
        f"border-top-right-radius:7px;border-bottom-right-radius:7px;"
        f"background:{C['input']};"
        f"}}"
        f"QComboBox::down-arrow{{"
        f"image:none;"
        f"border-left:5px solid transparent;"
        f"border-right:5px solid transparent;"
        f"border-top:6px solid {C['t2']};"
        f"width:0;height:0;"
        f"}}"
        f"QComboBox::down-arrow:hover{{border-top-color:{C['acc_h']};}}"
        f"QComboBox QAbstractItemView{{"
        f"background:{C['card']};color:{C['t1']};"
        f"border:1.5px solid {C['border_f']};border-radius:6px;"
        f"padding:4px;outline:none;"
        f"selection-background-color:{C['accent']};selection-color:{C['white']};"
        f"}}"
        f"QComboBox QAbstractItemView::item{{"
        f"min-height:32px;padding:4px 12px;border-radius:4px;"
        f"}}"
        f"QComboBox QAbstractItemView::item:hover{{"
        f"background:{C['acc_dim']};color:{C['t1']};"
        f"}}"
    )

    def __init__(self, label_text, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;border:none;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._items: list[tuple[str, object]] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        etq = QLabel(label_text)
        etq.setStyleSheet(
            f"color:{C['t2']};font-size:11px;font-weight:600;"
            f"background:transparent;letter-spacing:0.2px;"
        )
        lay.addWidget(etq)

        self._cb = QComboBox()
        self._cb.setMinimumHeight(42)
        self._cb.setStyleSheet(self._CSS)
        self._cb.currentIndexChanged.connect(
            lambda _: self.selectionChanged.emit(self.data())
        )
        lay.addWidget(self._cb)

    def add(self, text, data=None):
        self._items.append((text, data))
        self._cb.addItem(text)

    def data(self):
        i = self._cb.currentIndex()
        return self._items[i][1] if 0 <= i < len(self._items) else None

    def text(self):
        i = self._cb.currentIndex()
        return self._items[i][0] if 0 <= i < len(self._items) else ""

    def reset(self):
        self._items.clear()
        self._cb.clear()

    def set_by_data(self, val):
        for i, (_, d) in enumerate(self._items):
            if d == val:
                self._cb.setCurrentIndex(i)
                return

    def setEnabled(self, v):
        self._cb.setEnabled(v)
        super().setEnabled(v)


class SexoSelector(QWidget):
    """Radio buttons para Sexo. Compatible con todas versiones PySide6."""
    selectionChanged = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;border:none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        etq = QLabel("Sexo biológico")
        etq.setStyleSheet(
            f"color:{C['t2']};font-size:11px;font-weight:600;"
            f"background:transparent;letter-spacing:0.2px;"
        )
        lay.addWidget(etq)

        # Contenedor con fondo sutil para que los radio buttons se vean
        cont = QWidget()
        cont.setStyleSheet(
            f"background:{C['input']};border:1.5px solid {C['border']};"
            f"border-radius:8px;"
        )
        cont.setMinimumHeight(42)
        rl = QHBoxLayout(cont)
        rl.setContentsMargins(14, 8, 14, 8)
        rl.setSpacing(20)

        self._bg = QButtonGroup(self)
        self._val_map: dict = {}

        for val, texto in [("", "No especificado"), ("M", "Masculino"),
                           ("F", "Femenino"), ("O", "Otro")]:
            rb = QRadioButton(texto)
            rb.setStyleSheet(
                f"QRadioButton{{color:{C['t1']};font-size:13px;"
                f"spacing:6px;background:transparent;}}"
                f"QRadioButton::indicator{{"
                f"width:16px;height:16px;"
                f"border:1.5px solid {C['border']};border-radius:8px;"
                f"background:{C['card']};"
                f"}}"
                f"QRadioButton::indicator:checked{{"
                f"background:{C['accent']};border-color:{C['acc_h']};"
                f"}}"
                f"QRadioButton::indicator:hover{{"
                f"border-color:{C['border_f']};"
                f"}}"
            )
            rb.toggled.connect(
                lambda checked, v=val: self.selectionChanged.emit(v or None) if checked else None
            )
            self._bg.addButton(rb)
            self._val_map[texto] = (rb, val)
            rl.addWidget(rb)
            if val == "":
                rb.setChecked(True)

        rl.addStretch()
        lay.addWidget(cont)

    def value(self):
        for rb in self._bg.buttons():
            if rb.isChecked():
                for _, (r, v) in self._val_map.items():
                    if r is rb:
                        return v or None
        return None

    def set_value(self, v):
        mapa = {"M": "Masculino", "F": "Femenino", "O": "Otro"}
        target = mapa.get(str(v or "").upper(), "No especificado")
        rb, _ = self._val_map.get(target, (None, None))
        if rb:
            rb.setChecked(True)


# ══════════════════════════════════════════════════════════════
# DIALOGO BASE
# ══════════════════════════════════════════════════════════════

class BaseDialog(QDialog):
    def __init__(self, titulo, ancho=580, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setStyleSheet(STYLE)
        self.setMinimumWidth(340)

        screen = QApplication.primaryScreen()
        if screen:
            sw = screen.availableGeometry().width()
            ancho = min(ancho, max(380, int(sw * 0.58)))
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
            f"QScrollBar::handle:vertical{{background:{C['border']};"
            f"border-radius:3px;min-height:20px;}}"
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
        self.resize(self.width(), max(340, min(self.sizeHint().height(), max_h)))


# ══════════════════════════════════════════════════════════════
# DIALOGO: VER DETALLE
# ══════════════════════════════════════════════════════════════

class DialogVerPaciente(BaseDialog):
    def __init__(self, datos: dict, parent=None):
        super().__init__("Detalle del paciente", 520, parent)
        self._build(datos)

    def _build(self, d):
        lay = self.lay

        activo = d.get("activo", True)
        brow = QHBoxLayout()
        brow.addWidget(lbl(
            "● Activo" if activo else "○ Inactivo",
            size=11, color=C["ok"] if activo else C["err"], bold=True
        ))
        brow.addStretch()
        lay.addLayout(brow)
        lay.addSpacing(6)

        nombre = " ".join(filter(None, [
            d.get("primer_nombre"), d.get("segundo_nombre"),
            d.get("primer_apellido"), d.get("segundo_apellido")
        ]))
        lay.addWidget(lbl(nombre, size=16, bold=True))
        lay.addSpacing(14)
        lay.addWidget(sep())
        lay.addSpacing(12)

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        def _c(etq, val, row, col):
            e = lbl(etq + ":", size=11, color=C["t2"])
            e.setFixedWidth(130)
            v = lbl(str(val or "—"), size=13)
            v.setWordWrap(True)
            grid.addWidget(e, row, col)
            grid.addWidget(v, row, col + 1)

        _c("Tipo documento",   d.get("tipo_doc_nombre"),        0, 0)
        _c("Identificacion",   d.get("numero_documento"),        0, 2)
        _c("Fecha nacimiento", d.get("fecha_nacimiento"),        1, 0)
        _c("Sexo",             {"M":"Masculino","F":"Femenino","O":"Otro"}.get(
                               str(d.get("sexo") or ""), "—"),   1, 2)
        _c("Municipio",        d.get("municipio_residencia"),    2, 0)
        _c("Zona",             d.get("zona_residencia"),         2, 2)
        _c("Telefono",         d.get("telefono"),                3, 0)
        _c("Direccion",        d.get("direccion"),               3, 2)

        eps_txt = ""
        if d.get("eps_nombre"):
            eps_txt = f"{d['eps_nombre']}"
            if d.get("eps_codigo"):
                eps_txt = f"[{d['eps_codigo']}] {eps_txt}"
        _c("EPS",              eps_txt or "—",                   4, 0)
        _c("Afiliacion",       d.get("tipo_afiliacion"),         4, 2)

        lay.addLayout(grid)
        lay.addSpacing(12)
        lay.addWidget(sep())
        lay.addSpacing(10)

        fc = str(d.get("creado_en", ""))[:19]
        fa = str(d.get("actualizado_en", ""))[:19]
        reg_por = d.get("creado_por_ops_nombre", "")
        meta_txt = f"Creado: {fc}   |   Actualizado: {fa}"
        if reg_por:
            meta_txt += f"   |   Registrado por: {reg_por}"
        lay.addWidget(lbl(meta_txt, size=11, color=C["t3"], wrap=True))
        lay.addSpacing(14)

        bc = btn("Cerrar", "secondary")
        bc.clicked.connect(self.accept)
        lay.addWidget(bc)
        self._fin()


# ══════════════════════════════════════════════════════════════
# DIALOGO: CREAR / EDITAR PACIENTE
# ══════════════════════════════════════════════════════════════

class DialogFormPaciente(BaseDialog):
    """
    Formulario de paciente. Funciona para todos los roles:
    admin, Maestro y OPS regular.

    En modo edicion: tipo y numero de documento se deshabilitan.
    """

    def __init__(
        self,
        ejecutor:   dict,
        entidad_id: int,
        tipos_doc:  list,
        eps_list:   list,
        afil_list:  list,
        datos_ini:  dict | None = None,
        parent=None,
    ):
        titulo = "Editar paciente" if datos_ini else "Nuevo paciente"
        super().__init__(titulo, 620, parent)
        self._ejecutor  = ejecutor
        self._eid       = entidad_id
        self._editando  = datos_ini
        self._pid       = datos_ini["paciente_id"] if datos_ini else None
        self._tipos_doc = tipos_doc
        self._eps_list  = eps_list
        self._afil_list = afil_list
        self._build()

    def _build(self):
        lay      = self.lay
        editando = self._editando is not None

        # ── Helper: cabecera de seccion ───────────────────────
        def _sec(titulo):
            w = QWidget()
            w.setStyleSheet(
                f"background:{C['panel']};border-left:3px solid {C['accent']};"
                f"border-radius:0 6px 6px 0;"
            )
            wl = QHBoxLayout(w)
            wl.setContentsMargins(10, 6, 10, 6)
            lb = QLabel(titulo)
            lb.setStyleSheet(
                f"color:{C['acc_h']};font-size:12px;font-weight:700;"
                f"letter-spacing:0.5px;background:transparent;"
            )
            wl.addWidget(lb)
            return w

        # ── Helper: bloque de campos con fondo ────────────────
        def _bloque(inner_lay):
            """Envuelve un layout en un widget con fondo card."""
            wrap = QWidget()
            wrap.setStyleSheet(
                f"background:{C['card']};border:1px solid {C['border']};"
                f"border-radius:10px;"
            )
            wl = QVBoxLayout(wrap)
            wl.setContentsMargins(14, 14, 14, 14)
            wl.setSpacing(10)
            wl.addLayout(inner_lay)
            return wrap

        # ══ SECCION 1: Identificacion ═════════════════════════
        lay.addWidget(_sec("Identificacion del paciente"))
        lay.addSpacing(8)

        row_id = QHBoxLayout()
        row_id.setSpacing(12)

        self.f_tipo = ComboField("Tipo de documento *")
        self.f_tipo.add("-- Selecciona tipo --", None)
        for td in self._tipos_doc:
            self.f_tipo.add(f"{td['abreviatura']} — {td['nombre']}", td["abreviatura"])
        if editando:
            self.f_tipo.setEnabled(False)

        self.f_doc = InputField(
            "Numero de identificacion", "Ej: 1234567890",
            required=True
        )
        if editando:
            self.f_doc.setEnabled(False)

        row_id.addWidget(self.f_tipo, 1)
        row_id.addWidget(self.f_doc, 1)
        lay.addWidget(_bloque(row_id))
        lay.addSpacing(14)

        # ══ SECCION 2: Nombres ════════════════════════════════
        lay.addWidget(_sec("Nombres y apellidos"))
        lay.addSpacing(8)

        grid_nom = QGridLayout()
        grid_nom.setSpacing(12)
        self.f_pa = InputField("Primer apellido", "Ej: Garcia", required=True)
        self.f_sa = InputField("Segundo apellido", "Ej: Lopez  (si no tiene, deja vacio)")
        self.f_pn = InputField("Primer nombre", "Ej: Carlos", required=True)
        self.f_sn = InputField("Segundo nombre", "Ej: Andres  (opcional)")
        grid_nom.addWidget(self.f_pa, 0, 0)
        grid_nom.addWidget(self.f_sa, 0, 1)
        grid_nom.addWidget(self.f_pn, 1, 0)
        grid_nom.addWidget(self.f_sn, 1, 1)
        lay.addWidget(_bloque(grid_nom))
        lay.addSpacing(14)

        # ══ SECCION 3: Datos personales ═══════════════════════
        lay.addWidget(_sec("Datos personales"))
        lay.addSpacing(8)

        datos_lay = QVBoxLayout()
        datos_lay.setSpacing(10)

        row_p1 = QHBoxLayout()
        row_p1.setSpacing(12)
        self.f_fn  = InputField("Fecha de nacimiento", "DD/MM/AAAA")
        self.f_tel = InputField("Telefono de contacto", "Ej: 3001234567")
        row_p1.addWidget(self.f_fn, 1)
        row_p1.addWidget(self.f_tel, 1)
        datos_lay.addLayout(row_p1)

        row_p2 = QHBoxLayout()
        row_p2.setSpacing(12)
        self.f_mun  = InputField("Municipio de residencia", "Ej: Santa Marta")
        self.f_zona = ComboField("Zona de residencia")
        self.f_zona.add("No especificada", None)
        self.f_zona.add("Urbana", "Urbana")
        self.f_zona.add("Rural", "Rural")
        row_p2.addWidget(self.f_mun, 1)
        row_p2.addWidget(self.f_zona, 1)
        datos_lay.addLayout(row_p2)

        self.f_dir = InputField("Direccion de residencia", "Ej: Cra 5 # 10-20, Barrio Centro")
        datos_lay.addWidget(self.f_dir)

        self.f_sexo = SexoSelector()
        datos_lay.addWidget(self.f_sexo)

        lay.addWidget(_bloque(datos_lay))
        lay.addSpacing(14)

        # ══ SECCION 4: EPS y Afiliacion ═══════════════════════
        lay.addWidget(_sec("EPS y regimen de afiliacion"))
        lay.addSpacing(8)

        eps_lay = QVBoxLayout()
        eps_lay.setSpacing(10)

        row_eps = QHBoxLayout()
        row_eps.setSpacing(12)

        self.f_eps = ComboField("EPS aseguradora del paciente")
        self.f_eps.add("-- Sin EPS / Particular --", None)
        for e in self._eps_list:
            cod  = e.get("codigo", "")
            nom  = e.get("nombre", "")
            cont = "  ✓" if e.get("tiene_contrato") else ""
            etiq = f"[{cod}] {nom}{cont}" if cod else f"{nom}{cont}"
            self.f_eps.add(etiq, e["eps_id"])

        self.f_afil = ComboField("Tipo / regimen de afiliacion")
        self.f_afil.add("-- Sin seleccionar --", None)
        for a in self._afil_list:
            self.f_afil.add(a["nombre"], a["id"])

        row_eps.addWidget(self.f_eps, 1)
        row_eps.addWidget(self.f_afil, 1)
        eps_lay.addLayout(row_eps)

        nota = QLabel("Las EPS marcadas con ✓ tienen contrato vigente con la entidad.")
        nota.setStyleSheet(
            f"color:{C['t2']};font-size:11px;background:transparent;"
        )
        eps_lay.addWidget(nota)
        lay.addWidget(_bloque(eps_lay))
        lay.addSpacing(16)

        # ══ Barra de estado y botones ═════════════════════════
        self.sb = StatusBar()
        lay.addWidget(self.sb)
        lay.addSpacing(10)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        bc = btn("Cancelar", "secondary")
        bc.clicked.connect(self.reject)
        label_ok = "Guardar cambios" if editando else "Crear paciente"
        self.bok = btn(label_ok)
        self.bok.clicked.connect(self._guardar)
        btn_row.addWidget(bc)
        btn_row.addWidget(self.bok)
        lay.addLayout(btn_row)
        self._fin()

        if editando:
            self._precargar(self._editando)

    def _precargar(self, d):
        self.f_tipo.set_by_data(d.get("tipo_doc"))
        self.f_doc.set(d.get("numero_documento"))
        self.f_pa.set(d.get("primer_apellido"))
        self.f_sa.set(d.get("segundo_apellido"))
        self.f_pn.set(d.get("primer_nombre"))
        self.f_sn.set(d.get("segundo_nombre"))
        fn = d.get("fecha_nacimiento")
        if fn:
            self.f_fn.set(str(fn)[:10])
        self.f_tel.set(d.get("telefono"))
        self.f_dir.set(d.get("direccion"))
        self.f_mun.set(d.get("municipio_residencia"))
        self.f_zona.set_by_data(d.get("zona_residencia"))
        self.f_sexo.set_value(d.get("sexo"))
        self.f_eps.set_by_data(d.get("eps_id"))
        self.f_afil.set_by_data(d.get("tipo_afiliacion_id"))

    def _guardar(self):
        self.sb.ocultar()

        if not self._editando and self.f_tipo.data() is None:
            self.sb.err("Selecciona el tipo de documento.")
            return

        if not self.f_pa.text():
            self.sb.err("El primer apellido es obligatorio.")
            return

        if not self.f_pn.text():
            self.sb.err("El primer nombre es obligatorio.")
            return

        datos = {
            "tipo_doc_abrev":      self.f_tipo.data(),
            "numero_documento":    self.f_doc.text(),
            "primer_apellido":     self.f_pa.text(),
            "segundo_apellido":    self.f_sa.text(),
            "primer_nombre":       self.f_pn.text(),
            "segundo_nombre":      self.f_sn.text(),
            "fecha_nacimiento":    self.f_fn.text() or None,
            "sexo":                self.f_sexo.value(),
            "municipio_residencia":self.f_mun.text() or None,
            "zona_residencia":     self.f_zona.data(),
            "telefono":            self.f_tel.text() or None,
            "direccion":           self.f_dir.text() or None,
            "eps_id":              self.f_eps.data(),
            "tipo_afiliacion_id":  self.f_afil.data(),
        }

        self.bok.setEnabled(False)
        self.bok.setText("Guardando...")
        label_ok = "Guardar cambios" if self._editando else "Crear paciente"

        def done(res: pbk.Resultado):
            self.bok.setEnabled(True)
            self.bok.setText(label_ok)
            if res.ok:
                self.sb.ok(res.mensaje)
                QTimer.singleShot(600, self.accept)
            else:
                self.sb.err(res.mensaje)

        run_async(
            pbk.guardar_paciente,
            self._ejecutor, self._eid, datos, self._pid,
            on_done=done,
        )


# ══════════════════════════════════════════════════════════════
# DIALOGO: RESULTADO CARGA MASIVA
# ══════════════════════════════════════════════════════════════

class DialogResultadoCarga(BaseDialog):
    def __init__(self, resultado: pbk.Resultado, parent=None):
        super().__init__("Resultado de la carga masiva", 640, parent)
        self._build(resultado)

    def _build(self, res: pbk.Resultado):
        lay = self.lay
        d   = res.datos or {}

        errores_todos = d.get("errores", [])
        adv_eps  = [e for e in errores_todos if e.get("campo") == "Codigo_EPS"]
        err_real = [e for e in errores_todos if e.get("campo") != "Codigo_EPS"]

        # Tarjetas de resumen
        met = QHBoxLayout()
        met.setSpacing(8)
        for val, etq, color in [
            (d.get("total", 0),        "Total filas",  C["t2"]),
            (d.get("creados", 0),      "Nuevos",       C["ok"]),
            (d.get("actualizados", 0), "Actualizados", C["acc_h"]),
            (len(err_real),            "Errores",      C["err"]),
            (len(adv_eps),             "Advert. EPS",  C["warn"]),
        ]:
            card = QWidget()
            card.setStyleSheet(
                f"QWidget{{background:{C['card']};border:1px solid {C['border']};"
                f"border-radius:8px;}}"
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 8, 10, 8)
            cl.setSpacing(2)
            cl.addWidget(lbl(str(val), size=20, color=color, bold=True))
            cl.addWidget(lbl(etq, size=10, color=C["t2"]))
            met.addWidget(card)
        lay.addLayout(met)
        lay.addSpacing(10)

        lay.addWidget(lbl(res.mensaje, size=12, color=C["t2"], wrap=True))
        lay.addSpacing(12)

        if errores_todos:
            lay.addWidget(sep())
            lay.addSpacing(10)
            lay.addWidget(lbl(f"Detalle ({len(errores_todos)} filas):", size=12, bold=True))
            lay.addSpacing(6)

            t = QTableWidget()
            t.setColumnCount(3)
            t.setHorizontalHeaderLabels(["Fila", "Campo", "Descripcion"])
            t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            t.verticalHeader().setVisible(False)
            t.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            t.setColumnWidth(0, 55)
            t.setColumnWidth(1, 120)
            t.setAlternatingRowColors(True)
            t.setMaximumHeight(min(280, len(errores_todos) * 40 + 44))
            t.setStyleSheet(
                f"QTableWidget{{background:{C['card']};border:1px solid {C['border']};"
                f"border-radius:8px;gridline-color:{C['border']};"
                f"alternate-background-color:{C['row_a']};}}"
                f"QHeaderView::section{{background:{C['panel']};color:{C['t2']};"
                f"border:none;border-bottom:1px solid {C['border']};padding:6px;}}"
            )

            for e in errores_todos[:200]:
                r = t.rowCount()
                t.insertRow(r)
                es_adv = e.get("campo") == "Codigo_EPS"
                color_fila = C["warn"] if es_adv else C["err"]
                for ci, txt in enumerate([
                    str(e.get("fila", "")),
                    e.get("campo", ""),
                    e.get("error", ""),
                ]):
                    it = _it(txt)
                    it.setForeground(QColor(color_fila))
                    t.setItem(r, ci, it)
                t.setRowHeight(r, 36)

            lay.addWidget(t)
            lay.addSpacing(8)

            if adv_eps:
                nota = QLabel(
                    "Las filas en amarillo (Advert. EPS) se guardaron "
                    "sin EPS asignada porque el codigo no fue encontrado."
                )
                nota.setWordWrap(True)
                nota.setStyleSheet(
                    f"color:{C['warn']};font-size:11px;background:transparent;"
                )
                lay.addWidget(nota)

        lay.addSpacing(14)
        bc = btn("Cerrar")
        bc.clicked.connect(self.accept)
        lay.addWidget(bc)
        self._fin()


# ══════════════════════════════════════════════════════════════
# BADGES
# ══════════════════════════════════════════════════════════════

def _badge_activo(activo: bool) -> QWidget:
    w = QWidget()
    w.setStyleSheet("background:transparent;")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(3, 1, 3, 1)
    lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lb = QLabel("● Activo" if activo else "○ Inactivo")
    color = C["ok"] if activo else C["err"]
    bg    = "rgba(16,185,129,0.14)" if activo else "rgba(239,68,68,0.12)"
    lb.setStyleSheet(
        f"background:{bg};color:{color};border:1px solid {color};"
        f"border-radius:10px;padding:2px 9px;font-size:11px;font-weight:700;"
    )
    lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(lb)
    return w


# ══════════════════════════════════════════════════════════════
# TABLA
# ══════════════════════════════════════════════════════════════

#  (encabezado, ancho_fijo, visible_en_narrow)
_COLS = [
    ("Tipo",          55,  True),
    ("Documento",     110, True),
    ("Nombre",        0,   True),   # stretch
    ("EPS",           120, False),
    ("Afiliacion",    110, False),
    ("Registrado por",120, False),  # creado_por_ops_nombre — visible en pantallas anchas
    ("Estado",        80,  True),
    ("Acciones",      130, True),
]

# Índices de columna — se usan en _poblar_tabla y _ajustar_cols
_CI_TIPO  = 0
_CI_DOC   = 1
_CI_NOM   = 2
_CI_EPS   = 3
_CI_AFIL  = 4
_CI_REG   = 5   # Registrado por
_CI_EST   = 6
_CI_ACC   = 7


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
    # Col _CI_NOM (Nombre) estira
    t.horizontalHeader().setSectionResizeMode(_CI_NOM, QHeaderView.ResizeMode.Stretch)
    for i, (_, w, _) in enumerate(_COLS):
        if i != _CI_NOM and w > 0:
            t.setColumnWidth(i, w)
            t.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
    t.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return t


def _ajustar_cols(tabla: QTableWidget, ancho: int):
    narrow = ancho < BP_NARROW
    for i, (_, _, visible) in enumerate(_COLS):
        if i == _CI_NOM:
            continue
        tabla.setColumnHidden(i, not visible and narrow)


def _botones_fila(d: dict, callbacks: dict) -> QWidget:
    w = QWidget()
    w.setStyleSheet("background:transparent;")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(3, 1, 3, 1)
    lay.setSpacing(3)
    lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

    b_ver = btn("👁", "icon")
    b_ver.setToolTip("Ver detalle")
    b_ver.setFixedSize(30, 30)
    b_ver.clicked.connect(lambda: callbacks["ver"](d))
    lay.addWidget(b_ver)

    b_ed = btn("✏", "icon")
    b_ed.setToolTip("Editar")
    b_ed.setFixedSize(30, 30)
    b_ed.clicked.connect(lambda: callbacks["editar"](d))
    lay.addWidget(b_ed)

    activo = d.get("activo", True)
    b_est = btn("⛔" if activo else "✅", "icon")
    b_est.setToolTip("Desactivar" if activo else "Activar")
    b_est.setFixedSize(30, 30)
    b_est.clicked.connect(lambda: callbacks["estado"](d, not activo))
    lay.addWidget(b_est)

    return w


# ══════════════════════════════════════════════════════════════
# TARJETA (modo compacto < BP_CARD)
# ══════════════════════════════════════════════════════════════

class TarjetaPaciente(QWidget):
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

        row1 = QHBoxLayout()
        nombre = " ".join(filter(None, [
            d.get("primer_nombre"), d.get("segundo_nombre"),
            d.get("primer_apellido"), d.get("segundo_apellido")
        ]))
        nombre_lb = lbl(nombre, size=13, bold=True)
        nombre_lb.setWordWrap(True)
        row1.addWidget(nombre_lb, 1)
        row1.addWidget(_badge_activo(d.get("activo", True)))
        lay.addLayout(row1)

        tipo = d.get("tipo_doc", "")
        num  = d.get("numero_documento", "")
        lay.addWidget(lbl(f"{tipo}  {num}", size=12, color=C["t2"]))

        eps  = d.get("eps_nombre", "")
        if d.get("eps_codigo"):
            eps = f"[{d['eps_codigo']}] {eps}"
        afil = d.get("tipo_afiliacion", "")
        if eps or afil:
            lay.addWidget(lbl(
                f"{eps}  |  {afil}" if eps and afil else (eps or afil),
                size=11, color=C["t3"]
            ))

        lay.addWidget(sep())

        btn_row = QHBoxLayout()
        btn_row.setSpacing(5)
        for texto, estilo, key in [
            ("Ver",    "secondary", "ver"),
            ("Editar", "secondary", "editar"),
        ]:
            b = btn(texto, estilo)
            b.setFixedHeight(30)
            b.clicked.connect(lambda _, k=key: callbacks[k](d))
            btn_row.addWidget(b)

        activo = d.get("activo", True)
        b_est  = btn("Desactivar" if activo else "Activar",
                     "danger" if activo else "success")
        b_est.setFixedHeight(30)
        b_est.clicked.connect(lambda: callbacks["estado"](d, not activo))
        btn_row.addWidget(b_est)
        lay.addLayout(btn_row)


# ══════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════

class HeaderPacientes(QWidget):
    busqueda_cambiada = Signal(str)
    nuevo_clicked     = Signal()
    masivo_clicked    = Signal()
    plantilla_clicked = Signal()
    filtro_cambiado   = Signal(bool)   # True = solo activos

    def __init__(self, ejecutor: dict, entidad_id: int, parent=None):
        super().__init__(parent)
        self._ejecutor = ejecutor
        self._eid      = entidad_id
        self._solo_act = False
        self._es_admin_o_maestro = (
            ejecutor.get("rol") == "admin"
            or ejecutor.get("es_maestro", False)
        )
        self.setStyleSheet("background:transparent;border:none;")
        self._build()
        self._cargar_stats()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # Fila titulo + acciones
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.addWidget(lbl("Pacientes", size=20, bold=True))

        # Badge de rol
        if self._ejecutor.get("es_maestro"):
            tag_txt = "Maestro"; tag_color = "#D97706"; tag_bg = "#451A03"
        elif self._ejecutor.get("rol") == "admin":
            tag_txt = "Entidad Admin"; tag_color = C["acc_h"]; tag_bg = C["acc_dim"]
        else:
            tag_txt = "OPS"; tag_color = C["ok"]; tag_bg = C["ok_d"]

        tag = QLabel(f"  {tag_txt}  ")
        tag.setStyleSheet(
            f"background:{tag_bg};color:{tag_color};border:1px solid {tag_color};"
            f"border-radius:7px;padding:3px 10px;font-size:11px;font-weight:700;"
        )
        title_row.addWidget(tag)
        title_row.addStretch()

        # Boton nuevo — disponible para TODOS los roles
        self._b_nuevo = btn("+ Nuevo paciente")
        self._b_nuevo.setMinimumHeight(38)
        self._b_nuevo.clicked.connect(self.nuevo_clicked)
        title_row.addWidget(self._b_nuevo)

        # Carga masiva y plantilla — solo admin y Maestro
        if self._es_admin_o_maestro:
            b_masivo = btn("Carga Excel/CSV", "info")
            b_masivo.setMinimumHeight(38)
            b_masivo.clicked.connect(self.masivo_clicked)
            title_row.addWidget(b_masivo)

            b_plant = btn("Plantilla", "secondary")
            b_plant.setMinimumHeight(38)
            b_plant.clicked.connect(self.plantilla_clicked)
            title_row.addWidget(b_plant)

        lay.addLayout(title_row)

        # Stats
        stats_row = QHBoxLayout()
        stats_row.setSpacing(8)
        self._sc: dict = {}
        for key, etq, color in [
            ("total",    "Total",     C["t2"]),
            ("activos",  "Activos",   C["ok"]),
            ("inactivos","Inactivos", C["err"]),
            ("con_eps",  "Con EPS",   C["acc_h"]),
            ("sin_eps",  "Sin EPS",   C["warn"]),
        ]:
            card = QWidget()
            card.setMinimumWidth(80)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            card.setStyleSheet(
                f"QWidget{{background:{C['card']};border:1px solid {C['border']};"
                f"border-radius:8px;}}"
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 7, 10, 7)
            cl.setSpacing(1)
            v = lbl("--", size=18, color=color, bold=True)
            t = lbl(etq, size=10, color=C["t2"])
            cl.addWidget(v)
            cl.addWidget(t)
            card._val = v
            self._sc[key] = card
            stats_row.addWidget(card)
        lay.addLayout(stats_row)

        # Busqueda + filtro
        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Buscar por nombre, identificacion, EPS...")
        self._search.setMinimumHeight(38)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(
            lambda: self.busqueda_cambiada.emit(self._search.text())
        )
        self._search.textChanged.connect(lambda: self._timer.start(350))
        search_row.addWidget(self._search, 1)

        self._btn_filtro = QPushButton("Todos")
        self._btn_filtro.setMinimumHeight(38)
        self._btn_filtro.setMinimumWidth(100)
        self._btn_filtro.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_filtro.clicked.connect(self._toggle_filtro)
        self._render_filtro()
        search_row.addWidget(self._btn_filtro)
        lay.addLayout(search_row)

    def _toggle_filtro(self):
        self._solo_act = not self._solo_act
        self._render_filtro()
        self.filtro_cambiado.emit(self._solo_act)

    def _render_filtro(self):
        if self._solo_act:
            self._btn_filtro.setText("Solo activos")
            self._btn_filtro.setStyleSheet(
                f"QPushButton{{background:{C['ok_d']};color:{C['ok']};"
                f"border:1px solid {C['ok']};border-radius:8px;"
                f"padding:0 12px;font-size:12px;font-weight:700;}}"
            )
        else:
            self._btn_filtro.setText("Todos")
            self._btn_filtro.setStyleSheet(
                f"QPushButton{{background:{C['input']};color:{C['t2']};"
                f"border:1.5px solid {C['border']};border-radius:8px;"
                f"padding:0 12px;font-size:12px;}}"
                f"QPushButton:hover{{border-color:{C['border_f']};color:{C['t1']};}}"
            )

    def _cargar_stats(self):
        def done(s):
            if not isinstance(s, dict):
                return
            for key, card in self._sc.items():
                card._val.setText(str(s.get(key, "--")))

        run_async(pbk.stats_pacientes, self._ejecutor, self._eid, on_done=done)

    def refrescar(self):
        self._cargar_stats()


# ══════════════════════════════════════════════════════════════
# PANEL PRINCIPAL
# ══════════════════════════════════════════════════════════════

class PanelPacientes(QWidget):
    """
    Widget autonomo de gestion de pacientes.

    Uso:
        # Tras el login, construir el ejecutor:
        from ops_backend import construir_ejecutor
        ejecutor = construir_ejecutor(rol, ops_id, entidad_id)
        panel = PanelPacientes(ejecutor=ejecutor, entidad_id=eid, parent=self)
        stack.addWidget(panel)

    Acceso:
        Admin y Maestro: todo (incluyendo carga masiva)
        OPS regular:     crear, editar, activar/desactivar (formulario uno a uno)
    """

    _BP = BP_CARD

    def __init__(self, ejecutor: dict, entidad_id: int, parent=None):
        super().__init__(parent)
        self._ejecutor   = ejecutor
        self._eid        = entidad_id
        self._datos:     list[dict] = []
        self._filtro     = ""
        self._solo_act   = False
        self._compacto   = False
        self._catalogos_listos = False

        # Catalogos — se cargan async al arrancar
        self._tipos_doc: list[dict] = []
        self._eps_list:  list[dict] = []
        self._afil_list: list[dict] = []
        self._pendientes_catalogo   = 3   # contador de cargas pendientes

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._aplicar_resize)

        self.setStyleSheet(STYLE)
        self._build()
        self._cargar_catalogos()   # async — no bloquea
        self._cargar()             # async — muestra lista vacía mientras carga

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        self._header = HeaderPacientes(self._ejecutor, self._eid)
        self._header.busqueda_cambiada.connect(self._on_busqueda)
        self._header.nuevo_clicked.connect(self._nuevo)
        self._header.masivo_clicked.connect(self._masivo)
        self._header.plantilla_clicked.connect(self._plantilla)
        self._header.filtro_cambiado.connect(self._on_filtro)
        lay.addWidget(self._header)
        lay.addWidget(sep())

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background:transparent;border:none;")

        # Indice 0: tabla
        self._tabla = _nueva_tabla()
        self._stack.addWidget(self._tabla)

        # Indice 1: tarjetas (modo compacto)
        self._scroll_c = QScrollArea()
        self._scroll_c.setWidgetResizable(True)
        self._scroll_c.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_c.setStyleSheet("background:transparent;border:none;")
        self._cont_c = QWidget()
        self._cont_c.setStyleSheet("background:transparent;border:none;")
        self._lay_c  = QVBoxLayout(self._cont_c)
        self._lay_c.setContentsMargins(0, 0, 0, 0)
        self._lay_c.setSpacing(8)
        self._scroll_c.setWidget(self._cont_c)
        self._stack.addWidget(self._scroll_c)

        lay.addWidget(self._stack, 1)

        self._lbl_vacio = lbl("No se encontraron pacientes.", size=13, color=C["t2"])
        self._lbl_vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_vacio.hide()
        lay.addWidget(self._lbl_vacio)

    # ── Carga de catalogos ────────────────────────────────────

    def _cargar_catalogos(self):
        """
        Carga los tres catalogos en paralelo.
        El boton Nuevo queda habilitado cuando los tres esten listos.
        """
        self._pendientes_catalogo = 3

        def _uno_listo():
            self._pendientes_catalogo -= 1
            if self._pendientes_catalogo <= 0:
                self._catalogos_listos = True

        def done_td(r):
            if isinstance(r, list):
                self._tipos_doc = r
            _uno_listo()

        def done_eps(r):
            if isinstance(r, list):
                self._eps_list = r
            _uno_listo()

        def done_afil(r):
            if isinstance(r, list):
                self._afil_list = r
            _uno_listo()

        run_async(pbk.obtener_tipos_documento,                on_done=done_td)
        run_async(pbk.obtener_eps_activas,    self._eid,      on_done=done_eps)
        run_async(pbk.obtener_tipos_afiliacion,               on_done=done_afil)

    # ── Carga de datos ────────────────────────────────────────

    def _cargar(self):
        run_async(
            pbk.listar_pacientes,
            self._ejecutor, self._eid, self._filtro, self._solo_act, 500,
            on_done=self._poblar,
        )

    def _poblar(self, datos):
        if isinstance(datos, pbk.Resultado):
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
        t  = self._tabla
        cb = self._callbacks()
        t.setRowCount(0)
        for d in self._datos:
            r = t.rowCount()
            t.insertRow(r)
            t.setItem(r, _CI_TIPO, _it(d.get("tipo_doc", "")))
            t.setItem(r, _CI_DOC,  _it(d.get("numero_documento", "")))
            nombre = " ".join(filter(None, [
                d.get("primer_nombre"), d.get("segundo_nombre"),
                d.get("primer_apellido"), d.get("segundo_apellido")
            ]))
            it_nom = _it(nombre)
            if not d.get("activo", True):
                it_nom.setForeground(QColor(C["t3"]))
            t.setItem(r, _CI_NOM, it_nom)
            eps_txt = d.get("eps_nombre", "")
            if d.get("eps_codigo"):
                eps_txt = f"[{d['eps_codigo']}] {eps_txt}"
            t.setItem(r, _CI_EPS,  _it(eps_txt or "—"))
            t.setItem(r, _CI_AFIL, _it(d.get("tipo_afiliacion") or "—"))
            # Quién lo registró (Maestro u OPS)
            registrado_por = d.get("creado_por_ops_nombre") or "—"
            it_reg = _it(registrado_por)
            it_reg.setForeground(QColor(C["t2"]))
            t.setItem(r, _CI_REG, it_reg)
            t.setCellWidget(r, _CI_EST, _badge_activo(d.get("activo", True)))
            t.setCellWidget(r, _CI_ACC, _botones_fila(d, cb))
            t.setRowHeight(r, 46)

    def _poblar_tarjetas(self):
        while self._lay_c.count():
            item = self._lay_c.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        cb = self._callbacks()
        for d in self._datos:
            self._lay_c.addWidget(TarjetaPaciente(d, cb))
        self._lay_c.addStretch()

    def _callbacks(self) -> dict:
        return {
            "ver":    self._ver,
            "editar": self._editar,
            "estado": self._estado,
        }

    # ── Acciones ──────────────────────────────────────────────

    def _nuevo(self):
        """
        Abre el formulario de nuevo paciente.
        Si los catalogos aun no cargaron los recarga sincrono
        para no mostrar un formulario vacio.
        """
        # Si los catalogos no llegaron aun, cargarlos sincronamente
        if not self._catalogos_listos:
            try:
                if not self._tipos_doc:
                    self._tipos_doc = pbk.obtener_tipos_documento()
                if not self._eps_list:
                    self._eps_list  = pbk.obtener_eps_activas(self._eid)
                if not self._afil_list:
                    self._afil_list = pbk.obtener_tipos_afiliacion()
                self._catalogos_listos = True
            except Exception as e:
                QMessageBox.warning(self, "Error", f"No se pudieron cargar los catalogos: {e}")
                return

        dlg = DialogFormPaciente(
            self._ejecutor, self._eid,
            self._tipos_doc, self._eps_list, self._afil_list,
            parent=self,
        )
        if dlg.exec():
            self._cargar()

    def _ver(self, d: dict):
        try:
            datos = pbk.obtener_paciente(
                self._ejecutor, self._eid, int(d["paciente_id"])
            )
            if datos:
                DialogVerPaciente(datos, self).exec()
            else:
                QMessageBox.warning(self, "Error", "Paciente no encontrado.")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def _editar(self, d: dict):
        try:
            datos = pbk.obtener_paciente(
                self._ejecutor, self._eid, int(d["paciente_id"])
            )
            if not datos:
                QMessageBox.warning(self, "Error", "Paciente no encontrado.")
                return
            # Asegurar catalogos antes de abrir el formulario
            if not self._catalogos_listos:
                try:
                    if not self._tipos_doc:
                        self._tipos_doc = pbk.obtener_tipos_documento()
                    if not self._eps_list:
                        self._eps_list  = pbk.obtener_eps_activas(self._eid)
                    if not self._afil_list:
                        self._afil_list = pbk.obtener_tipos_afiliacion()
                    self._catalogos_listos = True
                except Exception:
                    pass
            dlg = DialogFormPaciente(
                self._ejecutor, self._eid,
                self._tipos_doc, self._eps_list, self._afil_list,
                datos_ini=datos, parent=self,
            )
            if dlg.exec():
                self._cargar()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def _estado(self, d: dict, nuevo_activo: bool):
        nombre = " ".join(filter(None, [
            d.get("primer_nombre"), d.get("primer_apellido")
        ]))
        accion = "activar" if nuevo_activo else "desactivar"
        if QMessageBox.question(
            self, f"Confirmar {accion}",
            f"Deseas {accion} al paciente '{nombre}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        res = pbk.cambiar_estado_paciente(
            self._ejecutor, self._eid,
            int(d["paciente_id"]), nuevo_activo,
        )
        if res.ok:
            self._cargar()
        else:
            QMessageBox.warning(self, "Error", res.mensaje)

    def _masivo(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo de carga masiva",
            "", "Archivos compatibles (*.csv *.xlsx *.xls)",
        )
        if not ruta:
            return

        self._header._btn_filtro.setEnabled(False)

        # Ventana de progreso NO bloqueante (tiene X funcional)
        dlg_prog = DialogProgresoCarga(Path(ruta).name, self)
        dlg_prog.show()

        def on_progreso(procesadas: int, total: int):
            dlg_prog.actualizar(procesadas, total)

        def done(res: pbk.Resultado):
            # Marcar como completado en el diálogo de progreso
            dlg_prog.marcar_completado()
            self._header._btn_filtro.setEnabled(True)
            self._cargar()

            # Si el diálogo ya fue cerrado por el usuario, abrir resultado
            # directamente. Si sigue abierto, esperar a que haga clic en
            # "Ver resultado" — reconectar el botón para mostrar el resultado.
            def _mostrar_resultado():
                dlg_prog.close()
                DialogResultadoCarga(res, self).exec()

            # Reconectar el botón del diálogo de progreso
            try:
                dlg_prog._btn_cerrar.clicked.disconnect()
            except Exception:
                pass
            dlg_prog._btn_cerrar.clicked.connect(_mostrar_resultado)

            # Si el usuario ya cerró el diálogo, mostrar resultado de inmediato
            if not dlg_prog.isVisible():
                QTimer.singleShot(0, lambda: DialogResultadoCarga(res, self).exec())

        run_async(
            pbk.procesar_carga_masiva,
            self._ejecutor, self._eid, ruta,
            on_done=done,
            on_progreso=on_progreso,
        )

    def _plantilla(self):
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar plantilla",
            "plantilla_pacientes.xlsx", "Excel (*.xlsx)",
        )
        if not ruta:
            return
        res = pbk.generar_plantilla_excel(ruta)
        if res.ok:
            QMessageBox.information(self, "Plantilla guardada", res.mensaje)
        else:
            QMessageBox.warning(self, "Error", res.mensaje)

    # ── Filtros ───────────────────────────────────────────────

    def _on_busqueda(self, texto: str):
        self._filtro = texto
        self._cargar()

    def _on_filtro(self, solo_activos: bool):
        self._solo_act = solo_activos
        self._cargar()

    # ── Responsive ───────────────────────────────────────────

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._resize_timer.start(40)

    def _aplicar_resize(self):
        w = self.width()
        nuevo = w < self._BP
        if nuevo != self._compacto:
            self._compacto = nuevo
            self._stack.setCurrentIndex(1 if nuevo else 0)
            if nuevo:
                self._poblar_tarjetas()
            else:
                self._poblar_tabla()
        if not self._compacto:
            _ajustar_cols(self._tabla, w - 32)


# ══════════════════════════════════════════════════════════════
# VENTANA AUTONOMA (pruebas)
# ══════════════════════════════════════════════════════════════

class PacientesWindow(QMainWindow):
    """
    Ventana standalone para pruebas del modulo.

    Admin:
        ejecutor = {'rol':'admin','es_maestro':False,'entidad_id':1,'ops_id':None}
    Maestro:
        ejecutor = {'rol':'ops','es_maestro':True,'entidad_id':1,'ops_id':1}
    OPS regular:
        ejecutor = {'rol':'ops','es_maestro':False,'entidad_id':1,'ops_id':5}
    """

    def __init__(self, ejecutor: dict, entidad_id: int):
        super().__init__()
        self.setWindowTitle("SIGES - Gestion de Pacientes")
        self.setMinimumSize(360, 500)

        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.resize(
                min(int(geo.width() * 0.88), 1400),
                min(int(geo.height() * 0.88), 900),
            )
        else:
            self.resize(1280, 800)

        self.setStyleSheet(STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QWidget()
        top.setFixedHeight(52)
        top.setStyleSheet(
            f"QWidget{{background:{C['panel']};border-bottom:1px solid {C['border']};}}"
        )
        tl = QHBoxLayout(top)
        tl.setContentsMargins(20, 0, 20, 0)
        tl.setSpacing(8)
        tl.addWidget(lbl("⚕", size=20, color=C["acc_h"]))
        nm = QLabel("SIGES")
        nm.setStyleSheet(
            f"color:{C['white']};font-size:14px;font-weight:800;"
            f"letter-spacing:3px;background:transparent;"
        )
        tl.addWidget(nm)
        tl.addWidget(lbl(" / ", size=14, color=C["t3"]))
        tl.addWidget(lbl("Pacientes", size=13, color=C["t2"]))
        tl.addStretch()
        root.addWidget(top)
        root.addWidget(PanelPacientes(ejecutor=ejecutor, entidad_id=entidad_id), 1)


# ══════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # Cambiar el rol para probar distintos perfiles:
    ejecutor = {
        "rol":        "ops",       # "admin" | "ops"
        "es_maestro": False,       # True = Maestro
        "entidad_id": 1,
        "ops_id":     5,           # None si rol="admin"
        "nombre":     "Juan OPS",
    }
    win = PacientesWindow(ejecutor=ejecutor, entidad_id=1)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()