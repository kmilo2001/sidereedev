# -*- coding: utf-8 -*-
# =============================================================================
# auditoria_backend.py
# Módulo de Auditoría / Historial de actividad — SIGES
#
# REGLAS DE VISIBILIDAD:
#   Maestro  → ve TODAS las entidades, todos los usuarios, todas las tablas.
#   Admin    → ve solo su entidad_id: acciones de sus OPS + las del Maestro.
#   OPS      → ve solo su entidad_id: sus propias acciones + las del Maestro.
#
# TABLAS AUDITADAS (triggers automáticos en BD):
#   eps, paciente, evento, contrato_eps,
#   gestion_cobro_sin_contrato, usuario_ops
#
# ESTRUCTURA de public.auditoria:
#   id, tabla, operacion (INSERT/UPDATE/DELETE),
#   registro_id, entidad_id, usuario_ops_id,
#   datos_antes (jsonb), datos_despues (jsonb),
#   ip_origen, realizado_en
# =============================================================================

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from conexion import Conexion

logger = logging.getLogger("siges.auditoria")

# ── Etiquetas legibles para la UI ────────────────────────────────────────────
TABLA_LABELS = {
    "eps":                       "EPS / Aseguradora",
    "paciente":                  "Paciente",
    "evento":                    "Evento de Atención",
    "contrato_eps":              "Contrato EPS",
    "gestion_cobro_sin_contrato":"Cobro sin Contrato",
    "usuario_ops":               "Usuario OPS",
}

OPERACION_LABELS = {
    "INSERT": "Creación",
    "UPDATE": "Actualización",
    "DELETE": "Eliminación",
}

# Número máximo de filas a mostrar en la UI de una sola vez
LIMITE_UI = 500


# ──────────────────────────────────────────────────────────────────────────────
# Resultado estándar
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Resultado:
    ok:      bool
    mensaje: str
    datos:   object = field(default=None)


# ──────────────────────────────────────────────────────────────────────────────
# Control de acceso
# ──────────────────────────────────────────────────────────────────────────────

def _puede_acceder(ejecutor: dict) -> bool:
    return ejecutor.get("rol") in ("admin", "ops")


def _check(ejecutor: dict) -> Optional[Resultado]:
    if not _puede_acceder(ejecutor):
        return Resultado(False, "Acceso denegado.")
    return None


def _es_maestro(ejecutor: dict) -> bool:
    return bool(ejecutor.get("es_maestro", False))


# ──────────────────────────────────────────────────────────────────────────────
# CONSULTA PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────

def listar_auditoria(
    ejecutor:      dict,
    entidad_id:    int,                     # entidad_activa_id desde _Sesion
    tabla:         Optional[str]  = None,   # filtro por tabla (None = todas)
    operacion:     Optional[str]  = None,   # INSERT / UPDATE / DELETE
    ops_id_filtro: Optional[int]  = None,   # filtrar por un OPS específico
    fecha_desde:   Optional[str]  = None,   # 'YYYY-MM-DD'
    fecha_hasta:   Optional[str]  = None,   # 'YYYY-MM-DD'
    texto:         Optional[str]  = None,   # búsqueda libre en datos JSON
    limite:        int            = LIMITE_UI,
    offset:        int            = 0,
) -> list[dict]:
    """
    Retorna el historial de auditoría según el rol:

    Maestro  → entidad_id ignorado, ve TODO el sistema.
    Admin    → ve su entidad_id (sus OPS + acciones del Maestro en su entidad).
    OPS      → ve su entidad_id filtrado además por su ops_id propio.
    """
    err = _check(ejecutor)
    if err:
        raise PermissionError(err.mensaje)

    es_maestro_usr = _es_maestro(ejecutor)
    rol            = ejecutor.get("rol")
    ops_id_sesion  = ejecutor.get("ops_id")

    cond:   list[str] = []
    params: list      = []

    # ── Filtro de visibilidad por rol ─────────────────────────────────────────
    if es_maestro_usr:
        pass                                       # ve todo el sistema
    elif rol == "admin":
        cond.append("a.entidad_id = %s")
        params.append(entidad_id)
    else:
        # OPS regular: solo su entidad + solo sus propias acciones
        cond.append("a.entidad_id = %s")
        params.append(entidad_id)
        cond.append("a.usuario_ops_id = %s")
        params.append(ops_id_sesion)

    # ── Filtros opcionales ────────────────────────────────────────────────────
    if tabla:
        cond.append("a.tabla = %s")
        params.append(tabla)

    if operacion:
        cond.append("a.operacion = %s")
        params.append(operacion.upper())

    if ops_id_filtro:
        cond.append("a.usuario_ops_id = %s")
        params.append(ops_id_filtro)

    if fecha_desde:
        cond.append("a.realizado_en::date >= %s::date")
        params.append(fecha_desde)

    if fecha_hasta:
        cond.append("a.realizado_en::date <= %s::date")
        params.append(fecha_hasta)

    if texto:
        like = f"%{texto.strip()}%"
        cond.append(
            "(a.datos_despues::text ILIKE %s OR a.datos_antes::text ILIKE %s)"
        )
        params += [like, like]

    where = ("WHERE " + " AND ".join(cond)) if cond else ""

    sql = f"""
        SELECT
            a.id                                                AS auditoria_id,
            a.tabla,
            a.operacion,
            a.registro_id,
            a.entidad_id,
            COALESCE(e.nombre_entidad, '—')                    AS entidad_nombre,
            a.usuario_ops_id,
            COALESCE(u.nombre_completo, '—')                   AS ops_nombre,
            a.datos_antes,
            a.datos_despues,
            a.ip_origen::text                                   AS ip_origen,
            a.realizado_en,
            to_char(a.realizado_en AT TIME ZONE 'America/Bogota',
                    'DD/MM/YYYY HH24:MI:SS')                   AS fecha_legible,
            COUNT(*) OVER()::int                               AS total_count
        FROM  public.auditoria        a
        LEFT  JOIN public.entidad     e ON e.id = a.entidad_id
        LEFT  JOIN public.usuario_ops u ON u.id = a.usuario_ops_id
        {where}
        ORDER BY a.realizado_en DESC
        LIMIT  %s OFFSET %s
    """
    params += [limite, offset]

    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.exception("Error en listar_auditoria")
        return []


def obtener_detalle(
    ejecutor:    dict,
    auditoria_id: int,
) -> Optional[dict]:
    """Retorna una fila completa de auditoría con datos JSON completos."""
    err = _check(ejecutor)
    if err:
        return None
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    a.*,
                    COALESCE(e.nombre_entidad, '—')   AS entidad_nombre,
                    COALESCE(u.nombre_completo, '—')  AS ops_nombre,
                    to_char(a.realizado_en AT TIME ZONE 'America/Bogota',
                            'DD/MM/YYYY HH24:MI:SS')  AS fecha_legible
                FROM  public.auditoria        a
                LEFT  JOIN public.entidad     e ON e.id = a.entidad_id
                LEFT  JOIN public.usuario_ops u ON u.id = a.usuario_ops_id
                WHERE a.id = %s
                """,
                (auditoria_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.exception("Error en obtener_detalle")
        return None


def stats_auditoria(
    ejecutor:   dict,
    entidad_id: int,
) -> dict:
    """
    Resumen de actividad para el encabezado del módulo:
    total hoy, esta semana, este mes; desglose por tabla y por operación.
    """
    err = _check(ejecutor)
    if err:
        return {}

    es_maestro_usr = _es_maestro(ejecutor)
    rol            = ejecutor.get("rol")
    ops_id_sesion  = ejecutor.get("ops_id")

    filtro_ent = ""
    params_ent: list = []

    if not es_maestro_usr:
        filtro_ent = "WHERE a.entidad_id = %s"
        params_ent = [entidad_id]
        if rol == "ops":
            filtro_ent += " AND a.usuario_ops_id = %s"
            params_ent.append(ops_id_sesion)

    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT
                    COUNT(*)                                               AS total,
                    COUNT(*) FILTER (WHERE a.realizado_en::date = CURRENT_DATE)           AS hoy,
                    COUNT(*) FILTER (WHERE a.realizado_en >= date_trunc('week',  NOW())) AS semana,
                    COUNT(*) FILTER (WHERE a.realizado_en >= date_trunc('month', NOW())) AS mes,
                    COUNT(*) FILTER (WHERE a.operacion = 'INSERT')        AS inserts,
                    COUNT(*) FILTER (WHERE a.operacion = 'UPDATE')        AS updates,
                    COUNT(*) FILTER (WHERE a.operacion = 'DELETE')        AS deletes
                FROM public.auditoria a
                {filtro_ent}
                """,
                params_ent or None,
            )
            row = cur.fetchone()
            return {k: int(row[k] or 0) for k in row.keys()}
    except Exception as e:
        logger.exception("Error en stats_auditoria")
        return {}


def listar_ops_auditables(
    ejecutor:   dict,
    entidad_id: int,
) -> list[dict]:
    """
    Lista los OPS que aparecen en la auditoría de la entidad.
    Usada para poblar el filtro de usuario en la UI.
    """
    err = _check(ejecutor)
    if err:
        return []

    es_maestro_usr = _es_maestro(ejecutor)

    cond   = "" if es_maestro_usr else "WHERE a.entidad_id = %s"
    params = [] if es_maestro_usr else [entidad_id]

    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT DISTINCT
                    u.id              AS ops_id,
                    u.nombre_completo AS nombre
                FROM  public.auditoria        a
                JOIN  public.usuario_ops u ON u.id = a.usuario_ops_id
                {cond}
                ORDER BY u.nombre_completo
                """,
                params or None,
            )
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.exception("Error en listar_ops_auditables")
        return []
