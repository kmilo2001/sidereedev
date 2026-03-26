# -*- coding: utf-8 -*-
"""
config_conexion_ui.py
=====================
Interfaz grafica (PySide6) para configurar la conexion a PostgreSQL.

Usa config_conexion_backend.py para toda la logica:
  - Leer / escribir gestion_eventos_db.cfg
  - Probar conexion con psycopg2 directo (sin tocar conexion.py)
  - Aplicar a conexion.py solo cuando el usuario confirma

Comportamiento de primera vez / produccion:
  - Si NO existe gestion_eventos_db.cfg -> abre el dialogo automaticamente.
  - Si existe pero la conexion FALLA   -> abre el dialogo automaticamente.
  - Si existe y la conexion es EXITOSA -> NO abre nada (transparente).
  - El usuario puede abrirlo manualmente desde Ajustes en cualquier momento.

Campos principales (prominentes):
  - Base de datos  (nombre del esquema)
  - Contrasena     (con boton mostrar/ocultar)

Campos secundarios (colapsables en "Configuracion avanzada"):
  - Host / Puerto / Usuario

Uso desde cualquier modulo del sistema:
    from config_conexion_ui import mostrar_config_si_necesario, ConfigConexionDialog

    # Al arrancar la app (abre solo si no hay config o falla):
    ok = mostrar_config_si_necesario(app)

    # Desde menu Ajustes (siempre abre):
    ConfigConexionDialog().exec()
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import (
    QApplication, QWidget, QDialog,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton,
    QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QCursor

import config_conexion_backend as cfg_bk


# ══════════════════════════════════════════════════════════════
# HILO DE TRABAJO (operaciones de BD sin bloquear la UI)
# ══════════════════════════════════════════════════════════════

class _Worker(QThread):
    done = Signal(object)

    def __init__(self, fn, *args):
        super().__init__()
        self._fn, self._args = fn, args

    def run(self):
        try:
            self.done.emit(self._fn(*self._args))
        except Exception as e:
            self.done.emit(cfg_bk.Resultado(False, str(e)))


_workers: list = []   # evitar GC prematuro


def _run_async(fn, *args, on_done):
    w = _Worker(fn, *args)
    _workers.append(w)
    w.done.connect(on_done)
    w.done.connect(lambda _: _workers.remove(w) if w in _workers else None)
    w.start()


# ══════════════════════════════════════════════════════════════
# PALETA Y ESTILOS (coherente con el resto del sistema)
# ══════════════════════════════════════════════════════════════

P = {
    "bg":     "#0D1117", "card":   "#161B22", "input":  "#21262D",
    "border": "#30363D", "focus":  "#388BFD", "accent": "#2D6ADF",
    "acc_h":  "#388BFD", "acc_lt": "#1C3A6E",
    "ok":     "#3FB950", "err":    "#F85149", "warn":   "#D29922",
    "txt":    "#E6EDF3", "txt2":   "#8B949E", "muted":  "#484F58",
    "white":  "#FFFFFF",
}

STYLE = f"""
QWidget {{
    background-color:{P['bg']};
    color:{P['txt']};
    font-family:'Segoe UI','Helvetica Neue',Arial,sans-serif;
    font-size:13px;
}}
QLabel {{ background:transparent; }}
QDialog {{ background-color:{P['bg']}; }}
QLineEdit {{
    background:{P['input']};
    border:1.5px solid {P['border']};
    border-radius:8px;
    padding:10px 14px;
    color:{P['txt']};
    font-size:14px;
}}
QLineEdit:focus {{
    border-color:{P['focus']};
    background:#1C2128;
}}
QLineEdit:disabled {{
    color:{P['muted']};
    background:{P['card']};
    border-color:{P['border']};
}}
"""

_CSS_INPUT_MAIN = (
    f"QLineEdit{{background:{P['input']};border:2px solid {P['border']};"
    f"border-radius:9px;padding:12px 16px;color:{P['txt']};font-size:15px;"
    f"font-weight:500;}}"
    f"QLineEdit:focus{{border-color:{P['focus']};background:#1C2128;}}"
    f"QLineEdit:disabled{{color:{P['muted']};background:{P['card']};"
    f"border-color:{P['border']};}}"
)
_CSS_INPUT_SEC = (
    f"QLineEdit{{background:{P['input']};border:1.5px solid {P['border']};"
    f"border-radius:7px;padding:8px 12px;color:{P['txt2']};font-size:13px;}}"
    f"QLineEdit:focus{{border-color:{P['focus']};color:{P['txt']};"
    f"background:#1C2128;}}"
    f"QLineEdit:disabled{{color:{P['muted']};background:{P['card']};}}"
)


# ══════════════════════════════════════════════════════════════
# HELPERS DE WIDGETS
# ══════════════════════════════════════════════════════════════

def _lbl(txt, size=13, color=None, bold=False):
    lb = QLabel(txt)
    lb.setStyleSheet(
        f"color:{color or P['txt2']};font-size:{size}px;"
        f"font-weight:{'600' if bold else '400'};background:transparent;"
    )
    return lb


def _sep():
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(
        f"border:none;border-top:1px solid {P['border']};background:transparent;"
    )
    f.setFixedHeight(1)
    return f


def _btn(txt, style="prim"):
    b = QPushButton(txt)
    S = {
        "prim": (
            f"QPushButton{{background:{P['accent']};color:white;border:none;"
            f"border-radius:8px;padding:12px 24px;font-size:14px;"
            f"font-weight:600;min-height:44px;}}"
            f"QPushButton:hover{{background:{P['acc_h']};}}"
            f"QPushButton:pressed{{background:#1A4FAF;}}"
            f"QPushButton:disabled{{background:{P['muted']};color:{P['bg']};}}"
        ),
        "sec": (
            f"QPushButton{{background:transparent;color:{P['txt2']};"
            f"border:1.5px solid {P['border']};border-radius:8px;"
            f"padding:11px 24px;font-size:14px;font-weight:500;min-height:44px;}}"
            f"QPushButton:hover{{border-color:{P['focus']};"
            f"color:{P['txt']};background:{P['input']};}}"
        ),
        "test": (
            f"QPushButton{{background:rgba(56,139,253,.12);color:{P['focus']};"
            f"border:1.5px solid {P['focus']};border-radius:8px;"
            f"padding:11px 24px;font-size:14px;font-weight:600;min-height:44px;}}"
            f"QPushButton:hover{{background:rgba(56,139,253,.22);}}"
            f"QPushButton:disabled{{opacity:.5;}}"
        ),
        "danger": (
            f"QPushButton{{background:rgba(248,81,73,.10);color:{P['err']};"
            f"border:1.5px solid {P['err']};border-radius:8px;"
            f"padding:8px 16px;font-size:12px;font-weight:500;min-height:34px;}}"
            f"QPushButton:hover{{background:rgba(248,81,73,.22);}}"
        ),
    }
    b.setStyleSheet(S.get(style, S["prim"]))
    b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    return b


# ══════════════════════════════════════════════════════════════
# CAMPO AGRUPADO (etiqueta + input + mensaje de error)
# ══════════════════════════════════════════════════════════════

class Campo(QWidget):
    def __init__(self, label: str, placeholder: str = "",
                 tipo: str = "sec", pw: bool = False,
                 ancho: int | None = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QWidget{{background:{P['bg']};border:none;}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)

        # Etiqueta
        self._lbl = QLabel(label)
        self._lbl.setStyleSheet(
            f"color:{P['txt2']};font-size:{'12' if tipo == 'sec' else '13'}px;"
            f"font-weight:{'400' if tipo == 'sec' else '500'};background:transparent;"
        )
        lay.addWidget(self._lbl)

        # Input
        self.inp = QLineEdit()
        self.inp.setPlaceholderText(placeholder)
        self.inp.setStyleSheet(
            _CSS_INPUT_MAIN if tipo == "main" else _CSS_INPUT_SEC
        )
        h = 50 if tipo == "main" else 40
        self.inp.setMinimumHeight(h)
        if ancho:
            self.inp.setFixedWidth(ancho)
        if pw:
            self.inp.setEchoMode(QLineEdit.EchoMode.Password)

        # Boton ojo para contrasena
        if pw:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(0)
            row.addWidget(self.inp, 1)
            self._eye = QPushButton("O")   # "O" como ojo - compatible con todas las fuentes
            self._eye.setFixedSize(44, h)
            self._eye.setCheckable(True)
            self._eye.setStyleSheet(
                f"QPushButton{{background:{P['input']};color:{P['txt2']};"
                f"border:2px solid {P['border']};border-left:none;"
                f"border-top-right-radius:9px;border-bottom-right-radius:9px;"
                f"font-size:13px;font-weight:600;}}"
                f"QPushButton:hover{{background:{P['border']};color:{P['txt']};}}"
                f"QPushButton:checked{{color:{P['focus']};}}"
            )
            self._eye.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self._eye.setToolTip("Mostrar / ocultar contrasena")
            self._eye.toggled.connect(self._toggle_pw)
            self.inp.setStyleSheet(
                self.inp.styleSheet().replace(
                    "border-radius:9px",
                    "border-radius:0;border-top-left-radius:9px;"
                    "border-bottom-left-radius:9px"
                )
            )
            lay.addLayout(row)
        else:
            lay.addWidget(self.inp)

        # Mensaje de error
        self._err_lbl = QLabel("")
        self._err_lbl.setStyleSheet(
            f"color:{P['err']};font-size:11px;background:transparent;"
        )
        self._err_lbl.hide()
        lay.addWidget(self._err_lbl)

    def _toggle_pw(self, visible: bool):
        self.inp.setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        )
        self._eye.setText("*" if visible else "O")

    def text(self) -> str:
        return self.inp.text()

    def set(self, valor: str):
        self.inp.setText(str(valor))

    def mostrar_error(self, mensaje: str):
        self._err_lbl.setText(mensaje)
        self._err_lbl.show()
        self.inp.setStyleSheet(
            self.inp.styleSheet() + f"QLineEdit{{border-color:{P['err']};}}"
        )

    def ocultar_error(self):
        self._err_lbl.hide()
        self._err_lbl.setText("")
        # Restaurar estilo original segun tipo
        tipo = "main" if self.inp.minimumHeight() >= 50 else "sec"
        self.inp.setStyleSheet(_CSS_INPUT_MAIN if tipo == "main" else _CSS_INPUT_SEC)


# ══════════════════════════════════════════════════════════════
# BURBUJA DE ESTADO (feedback de conexion)
# ══════════════════════════════════════════════════════════════

class BurbujaEstado(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{P['card']};border-radius:8px;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)

        self._dot = QLabel("  ")
        self._dot.setFixedWidth(10)
        self._dot.setStyleSheet(
            f"background:{P['muted']};border-radius:5px;min-height:10px;"
            f"max-height:10px;"
        )

        self._msg = QLabel("Ingresa los datos y presiona 'Probar conexion'")
        self._msg.setStyleSheet(
            f"color:{P['txt2']};font-size:12px;background:transparent;"
        )
        self._msg.setWordWrap(True)

        lay.addWidget(self._dot)
        lay.addWidget(self._msg, 1)
        self.hide()

    def _set(self, color: str, texto: str):
        self._dot.setStyleSheet(
            f"background:{color};border-radius:5px;"
            f"min-height:10px;max-height:10px;"
        )
        self._msg.setText(texto)
        self._msg.setStyleSheet(
            f"color:{color};font-size:12px;background:transparent;"
        )
        self.show()

    def ok(self, texto: str):
        self._set(P["ok"], texto)

    def err(self, texto: str):
        self._set(P["err"], texto)

    def cargando(self):
        self._set(P["warn"], "Verificando conexion...")


# ══════════════════════════════════════════════════════════════
# DIALOGO PRINCIPAL
# ══════════════════════════════════════════════════════════════

class ConfigConexionDialog(QDialog):
    """
    Dialogo de configuracion de conexion a PostgreSQL.

    Parametros:
        solo_config  -- True: solo guarda sin aplicar al pool
        forzar_modal -- True: el usuario no puede cerrar sin configurar
    """

    def __init__(self, parent=None,
                 solo_config: bool = False,
                 forzar_modal: bool = False):
        super().__init__(parent)
        self._solo_config  = solo_config
        self._forzar_modal = forzar_modal
        self._conexion_ok  = False
        self._sec_visible  = False

        self.setWindowTitle("Configuracion de base de datos — Gestion Eventos")
        self.setMinimumWidth(480)
        self.setModal(True)
        self.setStyleSheet(STYLE)

        if forzar_modal:
            self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        self._construir_ui()
        self._cargar_config_inicial()

    # ----------------------------------------------------------
    # CONSTRUCCION DE LA UI
    # ----------------------------------------------------------

    def _construir_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- Cabecera ----------------------------------------
        header = QWidget()
        header.setStyleSheet(
            f"background:{P['card']};border-bottom:1px solid {P['border']};"
        )
        hl = QHBoxLayout(header)
        hl.setContentsMargins(24, 18, 24, 18)

        titulo_col = QVBoxLayout()
        titulo_col.setSpacing(3)

        title_lbl = QLabel("Configuracion de conexion")
        title_lbl.setStyleSheet(
            f"color:{P['txt']};font-size:16px;font-weight:700;"
            f"background:transparent;"
        )

        sub_lbl = QLabel("Sistema de Gestion de Eventos — Sector Salud")
        sub_lbl.setStyleSheet(
            f"color:{P['txt2']};font-size:12px;background:transparent;"
        )

        titulo_col.addWidget(title_lbl)
        titulo_col.addWidget(sub_lbl)

        self._ind_hdr = QLabel("Sin configurar")
        self._ind_hdr.setStyleSheet(
            f"color:{P['warn']};font-size:11px;background:transparent;"
        )
        self._ind_hdr.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        hl.addLayout(titulo_col, 1)
        hl.addWidget(self._ind_hdr)
        outer.addWidget(header)

        # ---- Cuerpo ------------------------------------------
        body = QWidget()
        body.setStyleSheet(f"background:{P['bg']};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 24, 24, 24)
        bl.setSpacing(16)

        # Descripcion
        desc = QLabel(
            "Introduce el nombre de la base de datos y la contrasena de PostgreSQL.\n"
            "Esta configuracion se guarda automaticamente y no volvera a pedirse."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color:{P['txt2']};font-size:12px;line-height:1.6;"
            f"background:transparent;"
        )
        bl.addWidget(desc)
        bl.addWidget(_sep())
        bl.addSpacing(4)

        # ---- Campo: Base de datos ----------------------------
        lbl_db = _lbl("Nombre de la base de datos", size=13, bold=True,
                      color=P["txt"])
        bl.addWidget(lbl_db)
        self.f_db = Campo("", "gestion_eventos", tipo="main")
        bl.addWidget(self.f_db)
        bl.addSpacing(4)

        # ---- Campo: Contrasena -------------------------------
        lbl_pw = _lbl("Contrasena de PostgreSQL", size=13, bold=True,
                      color=P["txt"])
        bl.addWidget(lbl_pw)
        self.f_pw = Campo("", "Contrasena del usuario postgres", tipo="main", pw=True)
        bl.addWidget(self.f_pw)

        bl.addSpacing(8)
        bl.addWidget(_sep())

        # ---- Seccion avanzada (colapsable) -------------------
        self._btn_sec = QPushButton("  Configuracion avanzada")
        self._btn_sec.setStyleSheet(
            f"QPushButton{{background:transparent;color:{P['txt2']};"
            f"border:none;font-size:12px;text-align:left;padding:4px 0;}}"
            f"QPushButton:hover{{color:{P['txt']};}}"
        )
        self._btn_sec.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._btn_sec.clicked.connect(self._toggle_avanzado)
        bl.addWidget(self._btn_sec)

        self._panel_adv = QWidget()
        self._panel_adv.setStyleSheet(
            f"background:{P['card']};border-radius:8px;"
            f"border:1px solid {P['border']};"
        )
        al = QGridLayout(self._panel_adv)
        al.setContentsMargins(16, 12, 16, 12)
        al.setSpacing(12)

        self.f_host = Campo("Host", "localhost", tipo="sec")
        self.f_host.set("localhost")

        self.f_port = Campo("Puerto", "5432", tipo="sec", ancho=90)
        self.f_port.set("5432")

        self.f_user = Campo("Usuario", "postgres", tipo="sec")
        self.f_user.set("postgres")

        nota = QLabel(
            "Estos son los valores predeterminados de PostgreSQL. "
            "Modificalos solo si tu instalacion es diferente."
        )
        nota.setWordWrap(True)
        nota.setStyleSheet(
            f"color:{P['muted']};font-size:11px;background:transparent;"
            f"line-height:1.5;"
        )

        al.addWidget(self.f_host, 0, 0, 1, 2)
        al.addWidget(self.f_port, 0, 2)
        al.addWidget(self.f_user, 1, 0, 1, 3)
        al.addWidget(nota,        2, 0, 1, 3)

        self._panel_adv.hide()
        bl.addWidget(self._panel_adv)
        bl.addSpacing(16)

        # ---- Burbuja de estado -------------------------------
        self.burbuja = BurbujaEstado()
        bl.addWidget(self.burbuja)
        bl.addSpacing(16)

        # ---- Botones -----------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_test   = _btn("Probar conexion", "test")
        self.btn_save   = _btn("Guardar y conectar", "prim")
        self.btn_cancel = _btn("Cancelar", "sec")

        self.btn_test.clicked.connect(self._probar)
        self.btn_save.clicked.connect(self._guardar_y_conectar)
        self.btn_cancel.clicked.connect(self.reject)

        if self._forzar_modal:
            self.btn_cancel.hide()

        btn_row.addWidget(self.btn_test)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_save)
        bl.addLayout(btn_row)

        outer.addWidget(body)

    # ----------------------------------------------------------
    # CARGA INICIAL DE CONFIGURACION
    # ----------------------------------------------------------

    def _cargar_config_inicial(self):
        """Pre-rellena los campos con la config guardada (si existe)."""
        cfg = cfg_bk.cargar_config()
        self.f_db.set(cfg.get("dbname", "gestion_eventos"))
        # No pre-rellenar contrasena por seguridad
        self.f_host.set(cfg.get("host", "localhost"))
        self.f_port.set(str(cfg.get("port", 5432)))
        self.f_user.set(cfg.get("user", "postgres"))

        if cfg_bk.config_existe():
            self._ind_hdr.setText("Config guardada")
            self._ind_hdr.setStyleSheet(
                f"color:{P['txt2']};font-size:11px;background:transparent;"
            )

    # ----------------------------------------------------------
    # LOGICA DE INTERACCION
    # ----------------------------------------------------------

    def _toggle_avanzado(self):
        self._sec_visible = not self._sec_visible
        self._panel_adv.setVisible(self._sec_visible)
        self._btn_sec.setText(
            "  Configuracion avanzada (ocultar)"
            if self._sec_visible
            else "  Configuracion avanzada"
        )
        QTimer.singleShot(50, self._ajustar_altura)

    def _ajustar_altura(self):
        self.adjustSize()
        app = QApplication.instance()
        if app:
            sc = app.primaryScreen()
            if sc:
                mh = int(sc.availableGeometry().height() * 0.90)
                if self.height() > mh:
                    self.resize(self.width(), mh)

    def _leer_cfg(self) -> dict:
        """Construye el dict de configuracion desde los campos del formulario."""
        return {
            "host":     self.f_host.text() or "localhost",
            "port":     int(self.f_port.text() or "5432"),
            "dbname":   self.f_db.text()   or "",
            "user":     self.f_user.text() or "postgres",
            "password": self.f_pw.text(),
        }

    def _validar(self) -> bool:
        """Valida campos y muestra errores. Retorna True si todo OK."""
        for campo in (self.f_db, self.f_pw, self.f_host, self.f_port, self.f_user):
            campo.ocultar_error()

        errores = cfg_bk.validar_campos(self._leer_cfg())
        mapa = {
            "dbname":   self.f_db,
            "password": self.f_pw,
            "host":     self.f_host,
            "port":     self.f_port,
            "user":     self.f_user,
        }
        for e in errores:
            w = mapa.get(e["campo"])
            if w:
                w.mostrar_error(e["error"])
        return len(errores) == 0

    def _probar(self):
        """Prueba la conexion en un hilo separado sin guardar."""
        if not self._validar():
            return
        self.burbuja.cargando()
        self.btn_test.setEnabled(False)
        self.btn_test.setText("Probando...")
        cfg = self._leer_cfg()

        def _on_done(res):
            self.btn_test.setEnabled(True)
            self.btn_test.setText("Probar conexion")
            if res.ok:
                self.burbuja.ok(res.mensaje)
                self._ind_hdr.setText("Conexion verificada")
                self._ind_hdr.setStyleSheet(
                    f"color:{P['ok']};font-size:11px;background:transparent;"
                )
                self._conexion_ok = True
            else:
                self.burbuja.err(res.mensaje)
                self._ind_hdr.setText("Sin conexion")
                self._ind_hdr.setStyleSheet(
                    f"color:{P['err']};font-size:11px;background:transparent;"
                )
                self._conexion_ok = False

        _run_async(cfg_bk.probar_conexion, cfg, on_done=_on_done)

    def _guardar_y_conectar(self):
        """
        Guarda la configuracion, aplica a conexion.py y cierra el dialogo.
        Si solo_config=True solo guarda sin aplicar al modulo de conexion.
        """
        if not self._validar():
            return
        self.burbuja.cargando()
        self.btn_save.setEnabled(False)
        self.btn_save.setText("Conectando...")
        cfg = self._leer_cfg()

        def _accion():
            if self._solo_config:
                return cfg_bk.guardar_config(cfg)
            return cfg_bk.guardar_y_aplicar(cfg)

        def _on_done(res):
            self.btn_save.setEnabled(True)
            self.btn_save.setText("Guardar y conectar")
            if res.ok:
                if self._solo_config:
                    self.burbuja.ok("Configuracion guardada.")
                else:
                    self.burbuja.ok(res.mensaje)
                    self._ind_hdr.setText("Conectado")
                    self._ind_hdr.setStyleSheet(
                        f"color:{P['ok']};font-size:11px;background:transparent;"
                    )
                self._conexion_ok = True
                QTimer.singleShot(800, self.accept)
            else:
                self.burbuja.err(res.mensaje)

        _run_async(_accion, on_done=_on_done)

    def conexion_establecida(self) -> bool:
        """Retorna True si la conexion se probo y fue exitosa."""
        return self._conexion_ok


# ══════════════════════════════════════════════════════════════
# FUNCION PRINCIPAL: mostrar solo si es necesario
# ══════════════════════════════════════════════════════════════

def mostrar_config_si_necesario(
    app: QApplication,
    forzar: bool = False,
) -> bool:
    """
    Muestra el dialogo de configuracion UNICAMENTE si:
      1. forzar=True  (llamado manual desde Ajustes), o
      2. No existe gestion_eventos_db.cfg, o
      3. El archivo existe pero la conexion falla.

    En produccion:
      - Primera vez que se ejecuta el .exe -> abre el dialogo.
      - Ejecuciones siguientes con config valida -> NO abre nada.
      - Si cambia la BD o la contrasena falla -> abre automaticamente.

    Retorna True si hay una conexion disponible al terminar.
    """
    # Caso 1: forzar siempre (desde menu Ajustes)
    if forzar:
        dlg = ConfigConexionDialog()
        resultado = dlg.exec()
        return resultado == QDialog.DialogCode.Accepted and dlg.conexion_establecida()

    # Caso 2: no existe configuracion guardada
    if not cfg_bk.config_existe():
        dlg = ConfigConexionDialog(forzar_modal=True)
        resultado = dlg.exec()
        return resultado == QDialog.DialogCode.Accepted and dlg.conexion_establecida()

    # Caso 3: existe config -> verificar que la conexion funciona
    cfg = cfg_bk.cargar_config()
    resultado_conn: list[cfg_bk.Resultado | None] = [None]

    class _VerificaWorker(QThread):
        done = Signal(object)
        def run(self):
            self.done.emit(cfg_bk.probar_conexion(cfg))

    w = _VerificaWorker()
    pendiente = [True]

    def _on_done(res):
        resultado_conn[0] = res
        pendiente[0] = False

    w.done.connect(_on_done)
    w.start()

    # Esperar sin bloquear el event loop (max 6s por connect_timeout=5)
    while pendiente[0]:
        app.processEvents()

    if not resultado_conn[0] or not resultado_conn[0].ok:
        # Config existe pero la conexion falla -> pedir nuevos datos
        dlg = ConfigConexionDialog(forzar_modal=True)
        resultado = dlg.exec()
        return resultado == QDialog.DialogCode.Accepted and dlg.conexion_establecida()

    # Conexion exitosa -> aplicar config a conexion.py silenciosamente
    cfg_bk.aplicar_a_conexion(cfg)
    return True


# ══════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA (prueba standalone)
# ══════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    dlg = ConfigConexionDialog()
    dlg.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
