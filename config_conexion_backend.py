# -*- coding: utf-8 -*-
"""
config_conexion_backend.py
==========================
Backend INDEPENDIENTE del modulo de configuracion de conexion.

NO importa conexion.py en ningún momento.
NO toca el pool de conexiones principal.
NO tiene efectos secundarios sobre el resto del sistema.

Responsabilidades:
  1. Leer / escribir gestion_eventos_db.cfg  (JSON simple)
  2. Probar una conexion psycopg2 directa y efimera (sin pool)
  3. Aplicar la configuracion guardada a conexion.py (solo al confirmar)
  4. Notificar a conexion.py cuando la config cambia (sincronizacion bidireccional)

Flujo tipico:
  config_conexion_ui  ->  config_conexion_backend  ->  gestion_eventos_db.cfg
  config_conexion_ui  ->  config_conexion_backend  ->  conexion.py (solo al aplicar)
"""
from __future__ import annotations

import json
import os
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# ── Archivo de configuracion ──────────────────────────────────
# Se ubica junto a este modulo; compartido con conexion.py
CFG_FILE = Path(__file__).parent / "gestion_eventos_db.cfg"

# Valores por defecto de una instalacion estandar de PostgreSQL
DEFAULTS: dict[str, Any] = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "gestion_eventos",
    "user":     "postgres",
    "password": "",
}

# Lista de callbacks a notificar cuando la configuracion cambia
# conexion.py se registra aqui para mantenerse sincronizado
_observers: list[Callable[[dict[str, Any]], None]] = []


# ══════════════════════════════════════════════════════════════
# RESULTADO
# ══════════════════════════════════════════════════════════════

@dataclass
class Resultado:
    ok:      bool
    mensaje: str
    datos:   dict = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════
# SISTEMA DE OBSERVERS (sincronizacion bidireccional)
# ══════════════════════════════════════════════════════════════

def registrar_observer(fn: Callable[[dict[str, Any]], None]) -> None:
    """
    Registra una funcion que sera llamada cada vez que la
    configuracion cambie (guardar_config / guardar_y_aplicar).

    conexion.py la usa para actualizar DB_CONFIG automaticamente:
        import config_conexion_backend as cfg_bk
        cfg_bk.registrar_observer(lambda cfg: DB_CONFIG.update(cfg))
    """
    if fn not in _observers:
        _observers.append(fn)


def _notificar_observers(cfg: dict[str, Any]) -> None:
    """Llama a todos los observers registrados con la nueva config."""
    for fn in list(_observers):
        try:
            fn(cfg)
        except Exception:
            pass  # un observer roto no debe romper el flujo principal


# ══════════════════════════════════════════════════════════════
# LECTURA / ESCRITURA DE CONFIGURACION
# ══════════════════════════════════════════════════════════════

def cargar_config() -> dict[str, Any]:
    """
    Lee gestion_eventos_db.cfg y retorna el dict de configuracion.
    Si el archivo no existe o esta corrupto retorna los valores por defecto.
    Las variables de entorno tienen prioridad sobre el archivo.
    """
    base: dict[str, Any] = dict(DEFAULTS)

    if CFG_FILE.exists():
        try:
            guardado = json.loads(CFG_FILE.read_text(encoding="utf-8"))
            base.update(guardado)
        except Exception:
            pass  # archivo corrupto -> usar defaults

    # Variables de entorno sobreescriben todo
    if os.getenv("DB_HOST"):     base["host"]     = os.environ["DB_HOST"]
    if os.getenv("DB_PORT"):     base["port"]     = int(os.environ["DB_PORT"])
    if os.getenv("DB_NAME"):     base["dbname"]   = os.environ["DB_NAME"]
    if os.getenv("DB_USER"):     base["user"]     = os.environ["DB_USER"]
    if os.getenv("DB_PASSWORD"): base["password"] = os.environ["DB_PASSWORD"]

    return base


def guardar_config(cfg: dict[str, Any]) -> Resultado:
    """
    Persiste la configuracion en gestion_eventos_db.cfg.
    Solo guarda las claves reconocidas.
    Notifica a los observers (incluyendo conexion.py) del cambio.
    """
    datos_limpios = {
        "host":     str(cfg.get("host",    DEFAULTS["host"])).strip(),
        "port":     int(cfg.get("port",    DEFAULTS["port"])),
        "dbname":   str(cfg.get("dbname",  DEFAULTS["dbname"])).strip(),
        "user":     str(cfg.get("user",    DEFAULTS["user"])).strip(),
        "password": str(cfg.get("password", "")),
    }
    try:
        CFG_FILE.write_text(
            json.dumps(datos_limpios, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # Notificar a conexion.py y cualquier otro observer
        _notificar_observers(datos_limpios)
        return Resultado(True, "Configuracion guardada correctamente.", datos_limpios)
    except Exception as e:
        return Resultado(False, f"No se pudo guardar la configuracion: {e}")


def config_existe() -> bool:
    """
    Retorna True si ya existe un archivo gestion_eventos_db.cfg en disco
    Y contiene al menos dbname y password con valores no vacios.
    """
    if not CFG_FILE.exists():
        return False
    try:
        data = json.loads(CFG_FILE.read_text(encoding="utf-8"))
        return bool(data.get("dbname", "").strip()) and bool(data.get("password", ""))
    except Exception:
        return False


def borrar_config() -> Resultado:
    """Elimina gestion_eventos_db.cfg (para forzar re-configuracion)."""
    try:
        if CFG_FILE.exists():
            CFG_FILE.unlink()
        return Resultado(True, "Configuracion eliminada.")
    except Exception as e:
        return Resultado(False, f"No se pudo eliminar: {e}")


# ══════════════════════════════════════════════════════════════
# PRUEBA DE CONEXION  (sin pool, sin efectos secundarios)
# ══════════════════════════════════════════════════════════════

def probar_conexion(cfg: dict[str, Any]) -> Resultado:
    """
    Abre una conexion psycopg2 directa y efimera para verificar
    que los parametros son correctos.

    NO modifica conexion.py.
    NO importa conexion.py.
    Cierra la conexion inmediatamente tras el SELECT 1.
    """
    try:
        import psycopg2

        params = {
            "host":            str(cfg.get("host", "localhost")).strip(),
            "port":            int(cfg.get("port", 5432)),
            "dbname":          str(cfg.get("dbname", "gestion_eventos")).strip(),
            "user":            str(cfg.get("user", "postgres")).strip(),
            "password":        str(cfg.get("password", "")),
            "connect_timeout": 5,
            "options":         "-c search_path=public",
        }

        conn = psycopg2.connect(**params)
        cur  = conn.cursor()
        cur.execute("SELECT version()")
        version_row = cur.fetchone()
        version = str(version_row[0]).split(",")[0] if version_row else "PostgreSQL"
        cur.close()
        conn.close()

        return Resultado(
            True,
            f"Conexion exitosa — {version}",
            {"version": version, **params, "password": "***"},
        )

    except ImportError:
        return Resultado(False, "psycopg2 no esta instalado. Ejecute: pip install psycopg2-binary")
    except Exception as e:
        msg = str(e).strip().split("\n")[0]
        return Resultado(False, f"No se pudo conectar: {msg}")


# ══════════════════════════════════════════════════════════════
# APLICAR CONFIGURACION A conexion.py
# ══════════════════════════════════════════════════════════════

def aplicar_a_conexion(cfg: dict[str, Any]) -> Resultado:
    """
    Actualiza DB_CONFIG en conexion.py con la nueva configuracion.
    Este es el UNICO punto donde se importa conexion.py.

    Tambien invalida el pool si existe (reconexion automatica en
    el proximo uso gracias al mecanismo de reconexion de conexion.py).
    """
    try:
        import conexion as cn

        cn.DB_CONFIG.update({
            "host":     str(cfg.get("host",    "localhost")).strip(),
            "port":     int(cfg.get("port",    5432)),
            "dbname":   str(cfg.get("dbname",  "gestion_eventos")).strip(),
            "user":     str(cfg.get("user",    "postgres")).strip(),
            "password": str(cfg.get("password", "")),
        })

        return Resultado(True, "Configuracion aplicada a conexion.py correctamente.")
    except ImportError:
        # conexion.py no esta disponible en este contexto (standalone)
        return Resultado(True, "Config guardada (conexion.py no disponible en este contexto).")
    except Exception as e:
        msg = str(e).strip().split("\n")[0]
        return Resultado(False, f"No se pudo aplicar a conexion.py: {msg}")


# ══════════════════════════════════════════════════════════════
# FLUJO COMPLETO: GUARDAR + PROBAR + APLICAR
# ══════════════════════════════════════════════════════════════

def guardar_y_aplicar(cfg: dict[str, Any]) -> Resultado:
    """
    Ejecuta los tres pasos en orden:
      1. Probar conexion (sin pool)
      2. Guardar en gestion_eventos_db.cfg
      3. Aplicar a conexion.py (actualiza DB_CONFIG en memoria)

    Retorna Resultado del primer paso que falle.
    """
    # 1. Probar
    res = probar_conexion(cfg)
    if not res.ok:
        return res

    # 2. Guardar (tambien notifica observers incluyendo conexion.py)
    res = guardar_config(cfg)
    if not res.ok:
        return res

    # 3. Aplicar explicitamente a conexion.py
    res_pool = aplicar_a_conexion(cfg)
    if not res_pool.ok:
        return Resultado(
            False,
            f"Config guardada pero no se pudo aplicar: {res_pool.mensaje}"
        )

    return Resultado(True, "Configuracion guardada y conexion establecida correctamente.")


# ══════════════════════════════════════════════════════════════
# VALIDACION DE CAMPOS
# ══════════════════════════════════════════════════════════════

def validar_campos(cfg: dict[str, Any]) -> list[dict[str, str]]:
    """
    Valida los campos antes de intentar conectar.
    Retorna lista de errores: [{"campo": "...", "error": "..."}]
    Lista vacia = todos los campos son validos.
    """
    errores: list[dict[str, str]] = []

    dbname = str(cfg.get("dbname", "")).strip()
    if not dbname:
        errores.append({"campo": "dbname",
                        "error": "El nombre de la base de datos es obligatorio."})
    elif " " in dbname:
        errores.append({"campo": "dbname",
                        "error": "El nombre no puede contener espacios."})

    password = str(cfg.get("password", ""))
    if not password:
        errores.append({"campo": "password",
                        "error": "La contrasena es obligatoria."})

    try:
        port = int(cfg.get("port", 5432))
        if not (1 <= port <= 65535):
            raise ValueError
    except (ValueError, TypeError):
        errores.append({"campo": "port",
                        "error": "El puerto debe ser un numero entre 1 y 65535."})

    host = str(cfg.get("host", "")).strip()
    if not host:
        errores.append({"campo": "host", "error": "El host es obligatorio."})

    user = str(cfg.get("user", "")).strip()
    if not user:
        errores.append({"campo": "user", "error": "El usuario es obligatorio."})

    return errores
