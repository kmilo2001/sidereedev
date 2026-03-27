# -*- coding: utf-8 -*-
# =============================================================================
# maestro_backend.py
# Backend unificado para el usuario Maestro — Sistema SIGES
#
# El Maestro tiene acceso TOTAL al sistema:
#   Modulos exclusivos del Maestro:
#     - Gestion de entidades      (crear, editar, activar/desactivar, reset pw)
#     - Vision global del sistema (stats de TODAS las entidades)
#
#   Modulos compartidos con la entidad (admin), pero el Maestro
#   puede operar sobre CUALQUIER entidad, no solo la propia:
#     - Usuarios OPS              (todas las operaciones + activar/desactivar)
#     - EPS / Aseguradoras        (CRUD + carga masiva)
#     - Tipos de afiliacion       (CRUD catalogo)
#     - Pacientes                 (listar, ver, buscar, carga masiva)
#     - Eventos de atencion       (listar, ver, buscar, reactivar ventana edicion)
#     - Contratos EPS             (listar, crear, activar/desactivar)
#     - Cobros sin contrato       (listar, actualizar estado, resumen)
#     - Auditoria                 (consultar trazabilidad de cualquier tabla)
#     - Dashboard / Resumen       (KPIs por entidad o global)
#     - Notificaciones            (ver, marcar leidas)
#     - Catalogos de sistema      (tipo_documento, causa_atencion, modalidad)
#
# COMPATIBILIDAD:
#   - Usa conexion.py (Conexion, get_conexion_dict) directamente.
#   - Mismo patron que ops_backend.py y entidad_backend.py.
#
# IDENTIFICACION DEL MAESTRO:
#   - Es un usuario_ops cuyo nombre_completo ILIKE 'maestro%'.
#   - Se verifica en BD en cada operacion critica.
#   - ops_id del Maestro se obtiene del login y se pasa como parametro.
#
# PATRON DE RESULTADO:
#   Todas las funciones retornan Resultado(ok, mensaje, datos).
# =============================================================================

from __future__ import annotations

import re
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

import bcrypt

from conexion import Conexion

logger = logging.getLogger("siges.maestro")


# ──────────────────────────────────────────────────────────────
# Resultado estandar
# ──────────────────────────────────────────────────────────────

@dataclass
class Resultado:
    ok:      bool
    mensaje: str
    datos:   object = field(default=None)


# ──────────────────────────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────────────────────────

def _hash(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(10)).decode("utf-8")


def _email_ok(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))


def _nit_ok(nit: str) -> bool:
    return bool(re.match(r"^\d+-\d$", nit.strip()))


def _rpc(v) -> dict:
    if isinstance(v, dict):   return v
    if isinstance(v, str):    return json.loads(v)
    return dict(v)


def _es_maestro_nombre(nombre: str) -> bool:
    return str(nombre).strip().lower().startswith("maestro")


# ──────────────────────────────────────────────────────────────
# VERIFICACION DE IDENTIDAD MAESTRO
# ──────────────────────────────────────────────────────────────

def verificar_maestro(ops_id: int) -> bool:
    """
    Retorna True si ops_id corresponde a un usuario Maestro activo.
    Verificacion directa en BD — no confiar solo en el nombre del login.
    """
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT nombre_completo FROM public.usuario_ops "
                "WHERE id = %s AND activo = TRUE LIMIT 1",
                (ops_id,),
            )
            row = cur.fetchone()
            return bool(row) and _es_maestro_nombre(row["nombre_completo"])
    except Exception:
        return False


def _check(ops_id: int) -> Resultado | None:
    """Retorna None si es Maestro, Resultado de error si no."""
    if not verificar_maestro(ops_id):
        return Resultado(False, "Acceso denegado. Solo el usuario Maestro puede ejecutar esta operacion.")
    return None


def obtener_perfil_maestro(ops_id: int) -> dict | None:
    """Retorna el perfil completo del Maestro incluyendo su entidad."""
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT u.id AS ops_id, u.nombre_completo, u.correo,
                       u.whatsapp, u.activo, u.creado_en,
                       td.abreviatura AS tipo_doc,
                       u.numero_documento,
                       e.id AS entidad_id, e.nombre_entidad, e.nit
                FROM   public.usuario_ops u
                JOIN   public.tipo_documento td ON td.id = u.tipo_documento_id
                JOIN   public.entidad e          ON e.id  = u.entidad_id
                WHERE  u.id = %s
                """,
                (ops_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error("Error en obtener_perfil_maestro: %s", e)
        return None


# =============================================================================
# MODULO 1: GESTION DE ENTIDADES (exclusivo Maestro)
# =============================================================================

def listar_entidades(
    ops_id:         int,
    filtro:         str  = "",
    solo_activas:   bool = False,
    solo_inactivas: bool = False,
) -> list[dict]:
    """
    Lista todas las entidades del sistema.
    Retorna: id, nombre_entidad, nit, nivel_atencion, municipio,
             departamento, celular, correo, activo, protegido,
             creado_en, actualizado_en, total_ops, ops_activos, sesiones_activas.
    """
    err = _check(ops_id)
    if err: raise PermissionError(err.mensaje)

    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        like = f"%{filtro.strip()}%" if filtro.strip() else "%"
        q = """
            SELECT e.id, e.nombre_entidad, e.nit,
                   e.codigo_habilitacion,
                   e.nivel_atencion,
                   CASE e.nivel_atencion
                       WHEN 1 THEN 'Nivel 1 - Basico'
                       WHEN 2 THEN 'Nivel 2 - Mediano'
                       WHEN 3 THEN 'Nivel 3 - Alto'
                       ELSE 'No definido' END            AS nivel_texto,
                   e.municipio, e.departamento,
                   e.celular, e.correo,
                   e.activo, e.protegido,
                   e.creado_en, e.actualizado_en,
                   COALESCE((SELECT COUNT(*) FROM public.usuario_ops u
                              WHERE u.entidad_id = e.id), 0)::int          AS total_ops,
                   COALESCE((SELECT COUNT(*) FROM public.usuario_ops u
                              WHERE u.entidad_id = e.id AND u.activo), 0)::int AS ops_activos,
                   COALESCE((SELECT COUNT(*) FROM public.sesion s
                              WHERE s.entidad_id = e.id AND s.activa
                                AND s.expira_en > NOW()), 0)::int          AS sesiones_activas
            FROM public.entidad e
            WHERE (e.nombre_entidad ILIKE %s OR e.nit ILIKE %s
                   OR e.municipio ILIKE %s OR e.departamento ILIKE %s
                   OR e.correo    ILIKE %s)
        """
        params = [like]*5
        if solo_activas:   q += " AND e.activo = TRUE"
        elif solo_inactivas: q += " AND e.activo = FALSE"
        q += " ORDER BY e.protegido DESC, e.activo DESC, e.nombre_entidad LIMIT 500"
        cur.execute(q, params)
        return [dict(r) for r in cur.fetchall()]


def obtener_entidad(ops_id: int, entidad_id: int) -> dict | None:
    err = _check(ops_id)
    if err: raise PermissionError(err.mensaje)
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT e.id, e.nombre_entidad, e.nit, e.codigo_habilitacion,
                   e.nivel_atencion,
                   CASE e.nivel_atencion WHEN 1 THEN 'Nivel 1 - Basico'
                       WHEN 2 THEN 'Nivel 2 - Mediano' WHEN 3 THEN 'Nivel 3 - Alto'
                       ELSE 'No definido' END AS nivel_texto,
                   e.municipio, e.departamento, e.celular, e.correo,
                   e.activo, e.protegido, e.creado_en, e.actualizado_en,
                   COALESCE((SELECT COUNT(*) FROM public.usuario_ops WHERE entidad_id=e.id),0)::int AS total_ops,
                   COALESCE((SELECT COUNT(*) FROM public.usuario_ops WHERE entidad_id=e.id AND activo),0)::int AS ops_activos,
                   COALESCE((SELECT COUNT(*) FROM public.sesion WHERE entidad_id=e.id AND activa AND expira_en>NOW()),0)::int AS sesiones_activas
            FROM public.entidad e WHERE e.id = %s
        """, (entidad_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def crear_entidad(ops_id: int, datos: dict) -> Resultado:
    err = _check(ops_id)
    if err: return err
    requeridos = ["nombre_entidad", "nit", "celular", "correo", "password", "confirmar_password"]
    for c in requeridos:
        if not str(datos.get(c, "")).strip():
            return Resultado(False, f"El campo '{c}' es obligatorio.")
    if not _nit_ok(datos["nit"]):
        return Resultado(False, "NIT invalido. Formato requerido: digitos-digito (ej: 900123456-7).")
    if not _email_ok(datos["correo"]):
        return Resultado(False, "Correo electronico invalido.")
    if len(datos["password"]) < 8:
        return Resultado(False, "La contrasena debe tener al menos 8 caracteres.")
    if datos["password"] != datos["confirmar_password"]:
        return Resultado(False, "Las contrasenas no coinciden.")
    nivel = datos.get("nivel_atencion")
    if nivel not in (None, "", 1, 2, 3):
        try:
            nivel = int(nivel)
            if nivel not in (1, 2, 3): raise ValueError
        except (ValueError, TypeError):
            return Resultado(False, "El nivel de atencion debe ser 1, 2 o 3.")
    elif nivel == "": nivel = None
    try:
        pw_hash = _hash(datos["password"])
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT public.rpc_registrar_entidad(%s,%s,%s,%s::smallint,%s,%s,%s,%s,%s) AS r",
                (datos["nombre_entidad"].strip(),
                 datos["nit"].strip(),
                 (datos.get("codigo_habilitacion") or "").strip() or None,
                 nivel,
                 (datos.get("municipio") or "").strip() or None,
                 (datos.get("departamento") or "").strip() or None,
                 datos["celular"].strip(),
                 datos["correo"].strip().lower(),
                 pw_hash),
            )
            res = _rpc(cur.fetchone()["r"])
        if not res.get("ok"):
            return Resultado(False, res.get("error", "Error al registrar entidad."))
        return Resultado(True, f"Entidad '{datos['nombre_entidad'].strip()}' registrada.", {"entidad_id": str(res["entidad_id"])})
    except Exception as e:
        logger.exception("Error en crear_entidad")
        return Resultado(False, f"Error: {e}")


def editar_entidad(ops_id: int, entidad_id: int, datos: dict) -> Resultado:
    err = _check(ops_id)
    if err: return err
    nombre = str(datos.get("nombre_entidad", "")).strip()
    correo = str(datos.get("correo", "")).strip().lower()
    if not nombre: return Resultado(False, "El nombre es obligatorio.")
    if not _email_ok(correo): return Resultado(False, "Correo invalido.")
    nivel = datos.get("nivel_atencion")
    if nivel in ("", None): nivel = None
    else:
        try:
            nivel = int(nivel)
            if nivel not in (1, 2, 3): raise ValueError
        except (ValueError, TypeError):
            return Resultado(False, "Nivel de atencion invalido (1, 2 o 3).")
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE public.entidad SET
                    nombre_entidad      = %s,
                    codigo_habilitacion = %s,
                    nivel_atencion      = %s::smallint,
                    municipio           = %s,
                    departamento        = %s,
                    celular             = %s,
                    correo              = %s
                WHERE id = %s RETURNING id
            """, (nombre,
                  (datos.get("codigo_habilitacion") or "").strip() or None,
                  nivel,
                  (datos.get("municipio") or "").strip() or None,
                  (datos.get("departamento") or "").strip() or None,
                  (datos.get("celular") or "").strip() or None,
                  correo, entidad_id))
            if not cur.fetchone():
                return Resultado(False, "Entidad no encontrada.")
        return Resultado(True, "Entidad actualizada correctamente.")
    except Exception as e:
        if "unique" in str(e).lower() and "correo" in str(e).lower():
            return Resultado(False, "Ya existe otra entidad con ese correo.")
        return Resultado(False, f"Error: {e}")


def cambiar_estado_entidad(ops_id: int, entidad_id: int, nuevo_activo: bool) -> Resultado:
    err = _check(ops_id)
    if err: return err
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT nombre_entidad, protegido FROM public.entidad WHERE id=%s LIMIT 1", (entidad_id,))
            fila = cur.fetchone()
            if not fila: return Resultado(False, "Entidad no encontrada.")
            if not nuevo_activo and fila["protegido"]:
                return Resultado(False, f"La entidad '{fila['nombre_entidad']}' esta protegida y no puede desactivarse.")
            nombre = fila["nombre_entidad"]
            cur.execute("UPDATE public.entidad SET activo=%s WHERE id=%s", (nuevo_activo, entidad_id))
        if not nuevo_activo:
            try:
                with Conexion() as conn2:
                    cur2 = conn2.cursor()
                    cur2.execute("UPDATE public.sesion SET activa=FALSE, cerrado_en=NOW() WHERE entidad_id=%s AND activa=TRUE", (entidad_id,))
                    cur2.execute("""UPDATE public.sesion SET activa=FALSE, cerrado_en=NOW()
                                    WHERE activa=TRUE AND usuario_ops_id IN
                                    (SELECT id FROM public.usuario_ops WHERE entidad_id=%s)""", (entidad_id,))
            except Exception: pass
        accion = "activada" if nuevo_activo else "desactivada"
        return Resultado(True, f"Entidad '{nombre}' {accion} correctamente.", {"entidad_id": entidad_id, "activo": nuevo_activo})
    except Exception as e:
        return Resultado(False, f"Error: {e}")


def resetear_password_entidad(ops_id: int, entidad_id: int, nueva_pw: str, confirmar: str) -> Resultado:
    err = _check(ops_id)
    if err: return err
    if len(nueva_pw) < 8: return Resultado(False, "La contrasena debe tener al menos 8 caracteres.")
    if nueva_pw != confirmar: return Resultado(False, "Las contrasenas no coinciden.")
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT nombre_entidad FROM public.entidad WHERE id=%s LIMIT 1", (entidad_id,))
            fila = cur.fetchone()
            if not fila: return Resultado(False, "Entidad no encontrada.")
            nombre = fila["nombre_entidad"]
            cur.execute("SELECT public.rpc_cambiar_password(%s,%s,%s) AS r", (entidad_id, None, _hash(nueva_pw)))
            res = _rpc(cur.fetchone()["r"])
        if not res.get("ok"): return Resultado(False, res.get("error", "Error al cambiar contrasena."))
        return Resultado(True, f"Contrasena de '{nombre}' actualizada. Sesiones cerradas.")
    except Exception as e:
        return Resultado(False, f"Error: {e}")


# =============================================================================
# MODULO 2: USUARIOS OPS (Maestro opera sobre cualquier entidad)
# =============================================================================

def listar_ops(
    ops_id:         int,
    entidad_id:     int,
    filtro:         str  = "",
    solo_activos:   bool = False,
    solo_inactivos: bool = False,
) -> list[dict]:
    """Lista usuarios OPS de cualquier entidad."""
    err = _check(ops_id)
    if err: raise PermissionError(err.mensaje)
    like = f"%{filtro.strip()}%" if filtro.strip() else "%"
    q = """
        SELECT u.id AS ops_id, u.entidad_id,
               td.abreviatura AS tipo_doc, td.nombre AS tipo_doc_nombre,
               u.numero_documento, u.nombre_completo,
               u.correo, u.whatsapp, u.activo, u.creado_en, u.actualizado_en,
               (LOWER(u.nombre_completo) LIKE 'maestro%%') AS es_maestro,
               COALESCE((SELECT COUNT(*) FROM public.sesion s
                          WHERE s.usuario_ops_id=u.id AND s.activa AND s.expira_en>NOW()),0)::int AS sesiones_activas
        FROM public.usuario_ops u
        JOIN public.tipo_documento td ON td.id = u.tipo_documento_id
        WHERE u.entidad_id = %s
          AND (u.nombre_completo ILIKE %s OR u.numero_documento ILIKE %s OR u.correo ILIKE %s)
    """
    params = [entidad_id, like, like, like]
    if solo_activos:   q += " AND u.activo = TRUE"
    elif solo_inactivos: q += " AND u.activo = FALSE"
    q += " ORDER BY (LOWER(u.nombre_completo) LIKE 'maestro%%') DESC, u.activo DESC, u.nombre_completo LIMIT 500"
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute(q, params)
        return [dict(r) for r in cur.fetchall()]


def crear_ops(ops_id: int, entidad_id: int, datos: dict) -> Resultado:
    """Crea un usuario OPS en cualquier entidad."""
    err = _check(ops_id)
    if err: return err
    requeridos = ["tipo_doc_abrev","numero_documento","nombre_completo",
                  "correo","whatsapp","password","confirmar_password"]
    for c in requeridos:
        if not str(datos.get(c,"")).strip():
            return Resultado(False, f"Campo '{c}' obligatorio.")
    if not _email_ok(datos["correo"]): return Resultado(False, "Correo invalido.")
    if len(datos["password"]) < 8: return Resultado(False, "Contrasena: minimo 8 caracteres.")
    if datos["password"] != datos["confirmar_password"]: return Resultado(False, "Las contrasenas no coinciden.")
    nombre = datos["nombre_completo"].strip()
    if _es_maestro_nombre(nombre):
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM public.usuario_ops WHERE entidad_id=%s AND LOWER(nombre_completo) LIKE 'maestro%%' LIMIT 1", (entidad_id,))
            if cur.fetchone(): return Resultado(False, "Ya existe un Maestro para esta entidad.")
    try:
        pw_hash = _hash(datos["password"])
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT public.rpc_registrar_ops(%s,%s,%s,%s,%s,%s,%s) AS r",
                        (entidad_id, datos["tipo_doc_abrev"].strip().upper(),
                         datos["numero_documento"].strip(), nombre,
                         datos["correo"].strip().lower(), datos["whatsapp"].strip(), pw_hash))
            res = _rpc(cur.fetchone()["r"])
        if not res.get("ok"): return Resultado(False, res.get("error","Error al crear usuario."))
        return Resultado(True, f"Usuario '{nombre}' creado.", {"ops_id": str(res["ops_id"])})
    except Exception as e:
        return Resultado(False, f"Error: {e}")


def actualizar_ops(ops_id: int, entidad_id: int, objetivo_ops_id: int, datos: dict) -> Resultado:
    err = _check(ops_id)
    if err: return err
    nombre   = str(datos.get("nombre_completo","")).strip()
    correo   = str(datos.get("correo","")).strip().lower()
    whatsapp = str(datos.get("whatsapp","")).strip() or None
    if not nombre: return Resultado(False, "Nombre obligatorio.")
    if not _email_ok(correo): return Resultado(False, "Correo invalido.")
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE public.usuario_ops SET nombre_completo=%s, correo=%s, whatsapp=%s
                WHERE id=%s AND entidad_id=%s
            """, (nombre, correo, whatsapp, objetivo_ops_id, entidad_id))
            if cur.rowcount == 0: return Resultado(False, "Usuario no encontrado.")
        return Resultado(True, "Usuario actualizado correctamente.")
    except Exception as e:
        if "unique" in str(e).lower() and "correo" in str(e).lower():
            return Resultado(False, "Ya existe un usuario con ese correo en esta entidad.")
        return Resultado(False, f"Error: {e}")


def cambiar_estado_ops(ops_id: int, entidad_id: int, objetivo_ops_id: int, nuevo_activo: bool) -> Resultado:
    """
    El Maestro puede activar/desactivar cualquier OPS de cualquier entidad.
    No puede desactivarse a si mismo.
    """
    err = _check(ops_id)
    if err: return err
    if ops_id == objetivo_ops_id: return Resultado(False, "No puedes cambiar tu propio estado.")
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT nombre_completo, (LOWER(nombre_completo) LIKE 'maestro%%') AS es_maestro FROM public.usuario_ops WHERE id=%s AND entidad_id=%s LIMIT 1", (objetivo_ops_id, entidad_id))
            fila = cur.fetchone()
            if not fila: return Resultado(False, "Usuario no encontrado.")
            if fila["es_maestro"] and not nuevo_activo:
                return Resultado(False, "El usuario Maestro no puede desactivarse.")
            cur.execute("UPDATE public.usuario_ops SET activo=%s WHERE id=%s AND entidad_id=%s", (nuevo_activo, objetivo_ops_id, entidad_id))
        if not nuevo_activo:
            try:
                with Conexion() as conn2:
                    cur2 = conn2.cursor()
                    cur2.execute("UPDATE public.sesion SET activa=FALSE, cerrado_en=NOW() WHERE usuario_ops_id=%s AND activa=TRUE", (objetivo_ops_id,))
            except Exception: pass
        accion = "activado" if nuevo_activo else "desactivado"
        return Resultado(True, f"Usuario '{fila['nombre_completo']}' {accion}.", {"ops_id": objetivo_ops_id, "activo": nuevo_activo})
    except Exception as e:
        return Resultado(False, f"Error: {e}")


def resetear_password_ops(ops_id: int, entidad_id: int, objetivo_ops_id: int, nueva_pw: str, confirmar: str) -> Resultado:
    """El Maestro puede resetear la contrasena de cualquier OPS (incluso el de otra entidad)."""
    err = _check(ops_id)
    if err: return err
    if ops_id == objetivo_ops_id: return Resultado(False, "Usa 'Mi cuenta' para cambiar tu propia contrasena.")
    if len(nueva_pw) < 8: return Resultado(False, "Minimo 8 caracteres.")
    if nueva_pw != confirmar: return Resultado(False, "Las contrasenas no coinciden.")
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT nombre_completo FROM public.usuario_ops WHERE id=%s LIMIT 1", (objetivo_ops_id,))
            fila = cur.fetchone()
            if not fila: return Resultado(False, "Usuario no encontrado.")
            nombre = fila["nombre_completo"]
            cur.execute("SELECT public.rpc_cambiar_password(%s,%s,%s) AS r", (None, objetivo_ops_id, _hash(nueva_pw)))
            res = _rpc(cur.fetchone()["r"])
        if not res.get("ok"): return Resultado(False, res.get("error","Error al cambiar contrasena."))
        return Resultado(True, f"Contrasena de '{nombre}' actualizada. Sesiones cerradas.")
    except Exception as e:
        return Resultado(False, f"Error: {e}")


def activar_todos_ops_pendientes(ops_id: int, entidad_id: int) -> Resultado:
    err = _check(ops_id)
    if err: return err
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE public.usuario_ops SET activo=TRUE WHERE entidad_id=%s AND activo=FALSE", (entidad_id,))
            n = cur.rowcount
        return Resultado(True, f"{n} usuario(s) activado(s).", {"activados": n})
    except Exception as e:
        return Resultado(False, f"Error: {e}")


def stats_ops(ops_id: int, entidad_id: int) -> dict:
    err = _check(ops_id)
    if err: return {"total":0,"activos":0,"inactivos":0,"maestro_existe":False,"sesiones_en_curso":0}
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*)                                                AS total,
                       COUNT(*) FILTER (WHERE activo)                         AS activos,
                       COUNT(*) FILTER (WHERE NOT activo)                     AS inactivos,
                       COUNT(*) FILTER (WHERE LOWER(nombre_completo) LIKE 'maestro%%') AS maestros,
                       COALESCE((SELECT COUNT(*) FROM public.sesion s
                                  JOIN public.usuario_ops u2 ON u2.id=s.usuario_ops_id
                                  WHERE u2.entidad_id=%s AND s.activa AND s.expira_en>NOW()),0)::int AS sesiones_en_curso
                FROM public.usuario_ops WHERE entidad_id=%s
            """, (entidad_id, entidad_id))
            row = cur.fetchone()
            return {"total":int(row["total"]),"activos":int(row["activos"]),
                    "inactivos":int(row["inactivos"]),
                    "maestro_existe":int(row["maestros"])>0,
                    "sesiones_en_curso":int(row["sesiones_en_curso"])}
    except Exception as e:
        logger.error("Error stats_ops: %s", e)
        return {"total":0,"activos":0,"inactivos":0,"maestro_existe":False,"sesiones_en_curso":0}


# =============================================================================
# MODULO 3: EPS / ASEGURADORAS
# =============================================================================

def listar_eps(ops_id: int, entidad_id: int, filtro: str = "", solo_activos: bool = False) -> list[dict]:
    err = _check(ops_id)
    if err: raise PermissionError(err.mensaje)
    like = f"%{filtro.strip()}%" if filtro.strip() else "%"
    cond = "e.entidad_id = %s"
    params = [entidad_id]
    if filtro.strip():
        cond += " AND (e.nombre ILIKE %s OR e.codigo ILIKE %s OR e.nit ILIKE %s OR e.tipo ILIKE %s)"
        params += [like, like, like, like]
    if solo_activos: cond += " AND e.activo = TRUE"
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT e.id AS eps_id, e.entidad_id,
                   COALESCE(e.codigo,'')      AS codigo,
                   COALESCE(e.nombre,'')      AS nombre,
                   COALESCE(e.nit,'')         AS nit,
                   COALESCE(e.tipo,'EPS')     AS tipo,
                   COALESCE(e.municipio,'')   AS municipio,
                   COALESCE(e.departamento,'') AS departamento,
                   COALESCE(e.correo,'')      AS correo,
                   COALESCE(e.telefono,'')    AS telefono,
                   e.activo,
                   public.eps_tiene_contrato(e.entidad_id, e.id, CURRENT_DATE) AS tiene_contrato,
                   to_char(e.creado_en AT TIME ZONE 'America/Bogota','DD/MM/YYYY') AS fecha_creacion
            FROM public.eps e
            WHERE {cond}
            ORDER BY e.nombre LIMIT 500
        """, params)
        return [dict(r) for r in cur.fetchall()]


def guardar_eps(ops_id: int, entidad_id: int, datos: dict, eps_id: int | None = None) -> Resultado:
    """Crea o actualiza una EPS. El Maestro puede operar sobre cualquier entidad."""
    err = _check(ops_id)
    if err: return err
    nombre = str(datos.get("nombre","")).strip()
    if not nombre: return Resultado(False, "El nombre de la EPS es obligatorio.")
    codigo   = str(datos.get("codigo","")).strip().upper() or None
    tipo     = str(datos.get("tipo","EPS")).strip()
    dpto     = str(datos.get("departamento","")).strip() or None
    mpio     = str(datos.get("municipio","")).strip() or None
    nit      = str(datos.get("nit","")).strip() or None
    dv       = str(datos.get("dv","")).strip() or None
    correo   = str(datos.get("correo","")).strip() or None
    tel      = str(datos.get("telefono","")).strip() or None
    direccion= str(datos.get("direccion","")).strip() or None
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            if eps_id:
                cur.execute("SELECT id FROM public.eps WHERE id=%s AND entidad_id=%s", (eps_id, entidad_id))
                if not cur.fetchone(): return Resultado(False, "EPS no encontrada.")
                cur.execute("""
                    UPDATE public.eps SET codigo=%s,nombre=%s,tipo=%s,departamento=%s,municipio=%s,
                        nit=%s,dv=%s,correo=%s,telefono=%s,direccion=%s,actualizado_en=NOW()
                    WHERE id=%s AND entidad_id=%s
                """, (codigo,nombre,tipo,dpto,mpio,nit,dv,correo,tel,direccion,eps_id,entidad_id))
                return Resultado(True, f"EPS '{nombre}' actualizada.", {"eps_id":eps_id,"accion":"actualizada"})
            else:
                cur.execute("SELECT id FROM public.eps WHERE entidad_id=%s AND LOWER(TRIM(nombre))=LOWER(%s)", (entidad_id,nombre))
                if cur.fetchone(): return Resultado(False, f"Ya existe una EPS con el nombre '{nombre}'.")
                cur.execute("""
                    INSERT INTO public.eps (entidad_id,codigo,nombre,tipo,departamento,municipio,
                        nit,dv,correo,telefono,direccion,activo,creado_por_ops)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s) RETURNING id
                """, (entidad_id,codigo,nombre,tipo,dpto,mpio,nit,dv,correo,tel,direccion,ops_id))
                nuevo_id = cur.fetchone()["id"]
                return Resultado(True, f"EPS '{nombre}' creada.", {"eps_id":nuevo_id,"accion":"creada"})
    except Exception as e:
        return Resultado(False, f"Error al guardar EPS: {str(e).split(chr(10))[0]}")


def cambiar_estado_eps(ops_id: int, entidad_id: int, eps_id: int, activo: bool) -> Resultado:
    err = _check(ops_id)
    if err: return err
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT nombre FROM public.eps WHERE id=%s AND entidad_id=%s", (eps_id, entidad_id))
            row = cur.fetchone()
            if not row: return Resultado(False, "EPS no encontrada.")
            nombre = row["nombre"]
            advertencia = ""
            if not activo:
                cur.execute("SELECT COUNT(*) AS n FROM public.paciente WHERE eps_id=%s AND entidad_id=%s AND activo", (eps_id, entidad_id))
                n = cur.fetchone()["n"]
                if n: advertencia = f" Atencion: {n} paciente(s) tienen esta EPS asignada."
            cur.execute("UPDATE public.eps SET activo=%s, actualizado_en=NOW() WHERE id=%s AND entidad_id=%s", (activo, eps_id, entidad_id))
        lbl = "activada" if activo else "desactivada"
        return Resultado(True, f"'{nombre}' {lbl}.{advertencia}")
    except Exception as e:
        return Resultado(False, f"Error: {e}")


def eliminar_eps(ops_id: int, entidad_id: int, eps_id: int) -> Resultado:
    err = _check(ops_id)
    if err: return err
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT nombre FROM public.eps WHERE id=%s AND entidad_id=%s", (eps_id, entidad_id))
            row = cur.fetchone()
            if not row: return Resultado(False, "EPS no encontrada.")
            nombre = row["nombre"]
            deps = []
            for tabla, col, lbl in [("public.paciente","eps_id","paciente(s)"),("public.evento","eps_id","evento(s)"),("public.contrato_eps","eps_id","contrato(s)")]:
                cur.execute(f"SELECT COUNT(*) AS n FROM {tabla} WHERE {col}=%s", (eps_id,))
                n = cur.fetchone()["n"]
                if n: deps.append(f"{n} {lbl}")
            if deps: return Resultado(False, f"No se puede eliminar '{nombre}': referenciada por {', '.join(deps)}. Usa Desactivar.")
            cur.execute("DELETE FROM public.eps WHERE id=%s AND entidad_id=%s", (eps_id, entidad_id))
        return Resultado(True, f"EPS '{nombre}' eliminada.")
    except Exception as e:
        return Resultado(False, f"Error: {e}")


# =============================================================================
# MODULO 4: PACIENTES
# =============================================================================

def buscar_pacientes(ops_id: int, entidad_id: int, texto: str = "", limite: int = 50) -> list[dict]:
    err = _check(ops_id)
    if err: raise PermissionError(err.mensaje)
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM public.buscar_pacientes(%s,%s,%s)", (entidad_id, texto or None, limite))
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("Error buscar_pacientes: %s", e)
        return []


def obtener_paciente(ops_id: int, entidad_id: int, paciente_id: int) -> dict | None:
    err = _check(ops_id)
    if err: raise PermissionError(err.mensaje)
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.*,
                   td.abreviatura AS tipo_doc,
                   td.nombre      AS tipo_doc_nombre,
                   ep.nombre      AS eps_nombre,
                   ta.nombre      AS tipo_afiliacion
            FROM   public.paciente p
            JOIN   public.tipo_documento td ON td.id = p.tipo_documento_id
            LEFT JOIN public.eps            ep ON ep.id = p.eps_id
            LEFT JOIN public.tipo_afiliacion ta ON ta.id = p.tipo_afiliacion_id
            WHERE  p.id=%s AND p.entidad_id=%s
        """, (paciente_id, entidad_id))
        row = cur.fetchone()
        return dict(row) if row else None


def cambiar_estado_paciente(ops_id: int, entidad_id: int, paciente_id: int, activo: bool) -> Resultado:
    """El Maestro puede activar/desactivar pacientes de cualquier entidad."""
    err = _check(ops_id)
    if err: return err
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE public.paciente SET activo=%s WHERE id=%s AND entidad_id=%s RETURNING id
            """, (activo, paciente_id, entidad_id))
            if not cur.fetchone(): return Resultado(False, "Paciente no encontrado.")
        accion = "activado" if activo else "desactivado"
        return Resultado(True, f"Paciente {accion} correctamente.")
    except Exception as e:
        return Resultado(False, f"Error: {e}")


def stats_pacientes(ops_id: int, entidad_id: int) -> dict:
    err = _check(ops_id)
    if err: return {"total":0,"activos":0,"con_eps":0,"sin_eps":0}
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE activo)         AS activos,
                   COUNT(*) FILTER (WHERE eps_id IS NOT NULL) AS con_eps,
                   COUNT(*) FILTER (WHERE eps_id IS NULL)     AS sin_eps
            FROM public.paciente WHERE entidad_id=%s
        """, (entidad_id,))
        row = cur.fetchone()
        return {k: int(row[k]) for k in row.keys()}


# =============================================================================
# MODULO 5: EVENTOS DE ATENCION
# =============================================================================

def buscar_eventos(
    ops_id:      int,
    entidad_id:  int,
    texto:       str | None = None,
    estado_id:   int | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    solo_sin_contrato: bool = False,
    limite:      int = 50,
    offset:      int = 0,
) -> list[dict]:
    """El Maestro puede buscar eventos de cualquier entidad."""
    err = _check(ops_id)
    if err: raise PermissionError(err.mensaje)
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM public.buscar_eventos(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (entidad_id, None, texto, estado_id, fecha_desde, fecha_hasta,
                 solo_sin_contrato, limite, offset, True),  # incluir_inactivos=True para Maestro
            )
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("Error buscar_eventos: %s", e)
        return []


def reactivar_ventana_evento(ops_id: int, entidad_id: int, evento_id: int) -> Resultado:
    """
    Solo el Maestro puede reabrir la ventana de edicion de un evento vencido.
    Extiende editable_hasta 7 dias desde ahora.
    """
    err = _check(ops_id)
    if err: return err
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE public.evento
                SET editable_hasta = NOW() + INTERVAL '7 days',
                    ventana_reactivada_en = NOW()
                WHERE id=%s AND entidad_id=%s
                RETURNING id
            """, (evento_id, entidad_id))
            if not cur.fetchone(): return Resultado(False, "Evento no encontrado.")
        return Resultado(True, "Ventana de edicion reactivada (7 dias desde ahora).", {"evento_id": evento_id})
    except Exception as e:
        return Resultado(False, f"Error: {e}")


def resumen_facturacion(
    ops_id:      int,
    entidad_id:  int,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> dict | None:
    err = _check(ops_id)
    if err: return None
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM public.resumen_facturacion(%s,%s,%s,%s)", (entidad_id, None, fecha_desde, fecha_hasta))
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error("Error resumen_facturacion: %s", e)
        return None


def stats_eventos(ops_id: int, entidad_id: int) -> dict:
    err = _check(ops_id)
    if err: return {"total":0,"pendientes":0,"terminados":0,"sin_contrato":0,"hoy":0,"valor_total":0}
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*)                                          AS total,
                   COUNT(*) FILTER (WHERE estado_id=1)              AS pendientes,
                   COUNT(*) FILTER (WHERE estado_id=2)              AS terminados,
                   COUNT(*) FILTER (WHERE NOT tiene_contrato AND eps_id IS NOT NULL AND activo) AS sin_contrato,
                   COUNT(*) FILTER (WHERE fecha_evento=CURRENT_DATE) AS hoy,
                   COALESCE(SUM(valor),0)                           AS valor_total
            FROM public.evento WHERE entidad_id=%s AND activo
        """, (entidad_id,))
        row = cur.fetchone()
        return {k: (float(row[k]) if k=="valor_total" else int(row[k])) for k in row.keys()}


# =============================================================================
# MODULO 6: CONTRATOS EPS
# =============================================================================

def listar_contratos(ops_id: int, entidad_id: int, eps_id: int | None = None) -> list[dict]:
    err = _check(ops_id)
    if err: raise PermissionError(err.mensaje)
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cond = "c.entidad_id=%s"
        params = [entidad_id]
        if eps_id:
            cond += " AND c.eps_id=%s"; params.append(eps_id)
        cur.execute(f"""
            SELECT c.id AS contrato_id, c.entidad_id, c.eps_id,
                   ep.nombre AS eps_nombre, ep.nit AS eps_nit,
                   tc.nombre AS tipo_contrato,
                   c.numero_contrato, c.fecha_inicio, c.fecha_fin,
                   c.valor_contrato, c.activo, c.observaciones,
                   c.creado_en, c.actualizado_en,
                   public.eps_tiene_contrato(c.entidad_id, c.eps_id, CURRENT_DATE) AS vigente_hoy
            FROM public.contrato_eps c
            JOIN public.eps ep ON ep.id = c.eps_id
            JOIN public.tipo_contrato_eps tc ON tc.id = c.tipo_contrato_id
            WHERE {cond}
            ORDER BY c.activo DESC, c.fecha_inicio DESC
            LIMIT 500
        """, params)
        return [dict(r) for r in cur.fetchall()]


def crear_contrato(ops_id: int, entidad_id: int, datos: dict) -> Resultado:
    """El Maestro puede crear contratos entre cualquier entidad y cualquier EPS."""
    err = _check(ops_id)
    if err: return err
    requeridos = ["eps_id","tipo_contrato_id","fecha_inicio"]
    for c in requeridos:
        if not datos.get(c): return Resultado(False, f"Campo '{c}' obligatorio.")
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO public.contrato_eps
                    (entidad_id, eps_id, tipo_contrato_id, numero_contrato,
                     fecha_inicio, fecha_fin, valor_contrato, observaciones, activo)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE) RETURNING id
            """, (entidad_id, int(datos["eps_id"]), int(datos["tipo_contrato_id"]),
                  datos.get("numero_contrato") or None, datos["fecha_inicio"],
                  datos.get("fecha_fin") or None, datos.get("valor_contrato") or None,
                  datos.get("observaciones") or None))
            nuevo_id = cur.fetchone()["id"]
        return Resultado(True, "Contrato creado correctamente.", {"contrato_id": nuevo_id})
    except Exception as e:
        return Resultado(False, f"Error: {str(e).split(chr(10))[0]}")


def cambiar_estado_contrato(ops_id: int, entidad_id: int, contrato_id: int, activo: bool) -> Resultado:
    err = _check(ops_id)
    if err: return err
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE public.contrato_eps SET activo=%s, actualizado_en=NOW() WHERE id=%s AND entidad_id=%s RETURNING id", (activo, contrato_id, entidad_id))
            if not cur.fetchone(): return Resultado(False, "Contrato no encontrado.")
        lbl = "activado" if activo else "desactivado"
        return Resultado(True, f"Contrato {lbl} correctamente.")
    except Exception as e:
        return Resultado(False, f"Error: {e}")


def obtener_tipos_contrato() -> list[dict]:
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, nombre FROM public.tipo_contrato_eps ORDER BY id")
        return [dict(r) for r in cur.fetchall()]


# =============================================================================
# MODULO 7: COBROS SIN CONTRATO
# =============================================================================

ESTADOS_COBRO = [
    "pendiente_radicacion","radicado","en_glosa",
    "pagado_parcial","pagado_total","negado","en_conciliacion",
]


def listar_cobros(
    ops_id:     int,
    entidad_id: int,
    estado:     str | None = None,
    eps_id:     int | None = None,
    limite:     int = 200,
) -> list[dict]:
    err = _check(ops_id)
    if err: raise PermissionError(err.mensaje)
    cond = "g.entidad_id=%s"
    params: list = [entidad_id]
    if estado:   cond += " AND g.estado_cobro=%s"; params.append(estado)
    if eps_id:   cond += " AND g.eps_id=%s";       params.append(eps_id)
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT g.id AS cobro_id, g.evento_id, g.entidad_id, g.eps_id,
                   ep.nombre AS eps_nombre,
                   g.estado_cobro, g.fecha_radicacion, g.numero_radicado,
                   g.valor_radicado, g.valor_glosado, g.valor_pagado,
                   g.fecha_pago, g.observaciones, g.creado_en, g.actualizado_en
            FROM public.gestion_cobro_sin_contrato g
            JOIN public.eps ep ON ep.id = g.eps_id
            WHERE {cond}
            ORDER BY g.creado_en DESC LIMIT %s
        """, params + [limite])
        return [dict(r) for r in cur.fetchall()]


def actualizar_cobro(ops_id: int, cobro_id: int, entidad_id: int, datos: dict) -> Resultado:
    """El Maestro puede actualizar cualquier campo de gestion_cobro_sin_contrato."""
    err = _check(ops_id)
    if err: return err
    nuevo_estado = datos.get("estado_cobro")
    if nuevo_estado and nuevo_estado not in ESTADOS_COBRO:
        return Resultado(False, f"Estado invalido. Validos: {', '.join(ESTADOS_COBRO)}")
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE public.gestion_cobro_sin_contrato SET
                    estado_cobro      = COALESCE(%s, estado_cobro),
                    fecha_radicacion  = COALESCE(%s, fecha_radicacion),
                    numero_radicado   = COALESCE(%s, numero_radicado),
                    valor_radicado    = COALESCE(%s, valor_radicado),
                    valor_glosado     = COALESCE(%s, valor_glosado),
                    valor_pagado      = COALESCE(%s, valor_pagado),
                    fecha_pago        = COALESCE(%s, fecha_pago),
                    observaciones     = COALESCE(%s, observaciones),
                    actualizado_en    = NOW()
                WHERE id=%s AND entidad_id=%s RETURNING id
            """, (nuevo_estado, datos.get("fecha_radicacion"), datos.get("numero_radicado"),
                  datos.get("valor_radicado"), datos.get("valor_glosado"), datos.get("valor_pagado"),
                  datos.get("fecha_pago"), datos.get("observaciones"), cobro_id, entidad_id))
            if not cur.fetchone(): return Resultado(False, "Cobro no encontrado.")
        return Resultado(True, "Cobro actualizado correctamente.")
    except Exception as e:
        return Resultado(False, f"Error: {e}")


def stats_cobros(ops_id: int, entidad_id: int) -> dict:
    err = _check(ops_id)
    if err: return {}
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(valor_radicado),0)              AS total_radicado,
                   COALESCE(SUM(valor_pagado),0)                AS total_pagado,
                   COALESCE(SUM(valor_glosado),0)               AS total_glosado,
                   COUNT(*) FILTER (WHERE estado_cobro='pendiente_radicacion') AS pendientes,
                   COUNT(*) FILTER (WHERE estado_cobro='radicado')             AS radicados,
                   COUNT(*) FILTER (WHERE estado_cobro='en_glosa')             AS en_glosa,
                   COUNT(*) FILTER (WHERE estado_cobro='pagado_total')         AS pagados
            FROM public.gestion_cobro_sin_contrato WHERE entidad_id=%s
        """, (entidad_id,))
        row = cur.fetchone()
        return {k: (float(row[k]) if row[k] is not None and "total_" in k else int(row[k] or 0)) for k in row.keys()}


# =============================================================================
# MODULO 8: TIPOS DE AFILIACION (catalogo global)
# =============================================================================

_CODIGOS_OFICIALES = {"01","02","03","04","05"}


def listar_afiliaciones(ops_id: int, filtro: str = "", solo_activos: bool = False) -> list[dict]:
    err = _check(ops_id)
    if err: raise PermissionError(err.mensaje)
    cond = ["1=1"]; params: list = []
    if solo_activos: cond.append("activo=TRUE")
    if filtro.strip():
        cond.append("(nombre ILIKE %s OR COALESCE(codigo,'') ILIKE %s)")
        like = f"%{filtro.strip()}%"; params += [like, like]
    where = " AND ".join(cond)
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT id, nombre, COALESCE(codigo,'') AS codigo, activo,
                   to_char(creado_en AT TIME ZONE 'America/Bogota','DD/MM/YYYY') AS fecha_creacion
            FROM public.tipo_afiliacion WHERE {where}
            ORDER BY CASE WHEN codigo IN ('01','02','03','04','05') THEN 0 ELSE 1 END, nombre
        """, params or None)
        rows = cur.fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["es_catalogo_oficial"] = d.get("codigo","") in _CODIGOS_OFICIALES
        result.append(d)
    return result


def crear_afiliacion(ops_id: int, nombre: str, codigo: str = "") -> Resultado:
    err = _check(ops_id)
    if err: return err
    nombre = nombre.strip(); codigo = codigo.strip() or None
    if not nombre: return Resultado(False, "Nombre obligatorio.")
    if len(nombre) > 80: return Resultado(False, "Nombre maximo 80 caracteres.")
    if codigo and codigo in _CODIGOS_OFICIALES: return Resultado(False, f"Codigo '{codigo}' reservado para catalogos oficiales.")
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM public.tipo_afiliacion WHERE LOWER(TRIM(nombre))=LOWER(%s)", (nombre,))
            if cur.fetchone(): return Resultado(False, f"Ya existe '{nombre}'.")
            if codigo:
                cur.execute("SELECT 1 FROM public.tipo_afiliacion WHERE codigo=%s", (codigo,))
                if cur.fetchone(): return Resultado(False, f"Codigo '{codigo}' ya en uso.")
            cur.execute("INSERT INTO public.tipo_afiliacion (nombre,codigo,activo) VALUES (%s,%s,TRUE) RETURNING id,nombre", (nombre,codigo))
            row = cur.fetchone()
        return Resultado(True, f"Tipo '{nombre}' creado.", {"id":row["id"],"nombre":row["nombre"]})
    except Exception as e:
        return Resultado(False, f"Error: {e}")


def actualizar_afiliacion(ops_id: int, afil_id: int, nombre: str, codigo: str = "") -> Resultado:
    err = _check(ops_id)
    if err: return err
    nombre = nombre.strip(); codigo = codigo.strip() or None
    if not nombre: return Resultado(False, "Nombre obligatorio.")
    if codigo and codigo in _CODIGOS_OFICIALES: return Resultado(False, "Codigo reservado para catalogos oficiales.")
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT codigo FROM public.tipo_afiliacion WHERE id=%s", (afil_id,))
            row = cur.fetchone()
            if not row: return Resultado(False, "Tipo no encontrado.")
            if row["codigo"] in _CODIGOS_OFICIALES: return Resultado(False, "Los catalogos oficiales no se pueden modificar.")
            cur.execute("SELECT 1 FROM public.tipo_afiliacion WHERE LOWER(TRIM(nombre))=LOWER(%s) AND id!=%s", (nombre,afil_id))
            if cur.fetchone(): return Resultado(False, f"Ya existe otro tipo con el nombre '{nombre}'.")
            cur.execute("UPDATE public.tipo_afiliacion SET nombre=%s,codigo=%s WHERE id=%s", (nombre,codigo,afil_id))
        return Resultado(True, "Tipo de afiliacion actualizado.")
    except Exception as e:
        return Resultado(False, f"Error: {e}")


def cambiar_estado_afiliacion(ops_id: int, afil_id: int, activo: bool) -> Resultado:
    err = _check(ops_id)
    if err: return err
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT nombre,codigo FROM public.tipo_afiliacion WHERE id=%s", (afil_id,))
            row = cur.fetchone()
            if not row: return Resultado(False, "Tipo no encontrado.")
            if row["codigo"] in _CODIGOS_OFICIALES: return Resultado(False, "Los catalogos oficiales de Ley 100 no se pueden cambiar de estado.")
            nombre_tipo = row["nombre"]
            advertencia = ""
            if not activo:
                cur.execute("SELECT COUNT(*) AS n FROM public.paciente WHERE tipo_afiliacion_id=%s AND activo", (afil_id,))
                n = cur.fetchone()["n"]
                if n: advertencia = f" Nota: {n} paciente(s) tienen este tipo asignado."
            cur.execute("UPDATE public.tipo_afiliacion SET activo=%s WHERE id=%s", (activo,afil_id))
        lbl = "activado" if activo else "desactivado"
        return Resultado(True, f"'{nombre_tipo}' {lbl}.{advertencia}")
    except Exception as e:
        return Resultado(False, f"Error: {e}")


# =============================================================================
# MODULO 9: AUDITORIA
# =============================================================================

def consultar_auditoria(
    ops_id:      int,
    tabla:       str,
    registro_id: int,
    limite:      int = 50,
) -> list[dict]:
    """El Maestro puede consultar la auditoria de cualquier tabla y registro."""
    err = _check(ops_id)
    if err: raise PermissionError(err.mensaje)
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM public.auditoria_registro(%s,%s,%s)", (tabla, registro_id, limite))
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("Error consultar_auditoria: %s", e)
        return []


def listar_auditoria_entidad(
    ops_id:      int,
    entidad_id:  int,
    tabla:       str | None = None,
    limite:      int = 100,
    offset:      int = 0,
) -> list[dict]:
    """Lista todos los registros de auditoria de una entidad con filtro opcional por tabla."""
    err = _check(ops_id)
    if err: raise PermissionError(err.mensaje)
    cond = "entidad_id=%s"; params: list = [entidad_id]
    if tabla: cond += " AND tabla=%s"; params.append(tabla)
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT a.id, a.tabla, a.operacion, a.registro_id,
                   a.entidad_id, a.usuario_ops_id,
                   u.nombre_completo AS usuario_nombre,
                   a.datos_antes, a.datos_despues, a.realizado_en
            FROM public.auditoria a
            LEFT JOIN public.usuario_ops u ON u.id = a.usuario_ops_id
            WHERE {cond}
            ORDER BY a.realizado_en DESC
            LIMIT %s OFFSET %s
        """, params + [limite, offset])
        return [dict(r) for r in cur.fetchall()]


# =============================================================================
# MODULO 10: DASHBOARD Y STATS GLOBALES
# =============================================================================

def dashboard_entidad(ops_id: int, entidad_id: int) -> dict | None:
    """Retorna el dashboard de KPIs de una entidad especifica."""
    err = _check(ops_id)
    if err: return None
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT public.rpc_dashboard(%s,%s) AS r", (entidad_id, None))
            row = cur.fetchone()
            if row and row["r"]:
                return _rpc(row["r"])
    except Exception as e:
        logger.error("Error dashboard_entidad: %s", e)
    return None


def stats_sistema_global(ops_id: int) -> dict | None:
    """Stats globales del sistema completo. Solo el Maestro puede verlos."""
    err = _check(ops_id)
    if err: return None
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT public.stats_sistema() AS r")
            row = cur.fetchone()
            if row and row["r"]:
                return _rpc(row["r"])
    except Exception as e:
        logger.error("Error stats_sistema_global: %s", e)
    return None


def stats_globales_maestro(ops_id: int) -> dict:
    """Contadores globales de entidades para el header del Maestro."""
    err = _check(ops_id)
    if err: return {"total":0,"activas":0,"inactivas":0,"protegidas":0,"sesiones_en_curso":0}
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE activo)    AS activas,
                       COUNT(*) FILTER (WHERE NOT activo) AS inactivas,
                       COUNT(*) FILTER (WHERE protegido) AS protegidas,
                       COALESCE((SELECT COUNT(*) FROM public.sesion WHERE activa AND expira_en>NOW()),0)::int AS sesiones_en_curso
                FROM public.entidad
            """)
            row = cur.fetchone()
            return {k: int(row[k]) for k in row.keys()}
    except Exception as e:
        logger.error("Error stats_globales_maestro: %s", e)
        return {"total":0,"activas":0,"inactivas":0,"protegidas":0,"sesiones_en_curso":0}


# =============================================================================
# MODULO 11: NOTIFICACIONES
# =============================================================================

def listar_notificaciones(ops_id: int, entidad_id: int, solo_no_leidas: bool = False) -> list[dict]:
    err = _check(ops_id)
    if err: return []
    cond = "n.entidad_id=%s"; params: list = [entidad_id]
    if solo_no_leidas: cond += " AND n.leida=FALSE"
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT n.id, n.entidad_id, n.usuario_ops_id,
                   n.tipo, n.mensaje, n.leida, n.creado_en,
                   u.nombre_completo AS ops_nombre
            FROM public.notificacion n
            LEFT JOIN public.usuario_ops u ON u.id = n.usuario_ops_id
            WHERE {cond}
            ORDER BY n.creado_en DESC LIMIT 200
        """, params)
        return [dict(r) for r in cur.fetchall()]


def marcar_notificacion_leida(ops_id: int, notificacion_id: int) -> Resultado:
    err = _check(ops_id)
    if err: return err
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("UPDATE public.notificacion SET leida=TRUE WHERE id=%s RETURNING id", (notificacion_id,))
            if not cur.fetchone(): return Resultado(False, "Notificacion no encontrada.")
        return Resultado(True, "Notificacion marcada como leida.")
    except Exception as e:
        return Resultado(False, f"Error: {e}")


# =============================================================================
# MODULO 12: CATALOGOS DE SISTEMA
# =============================================================================

def obtener_tipos_documento() -> list[dict]:
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, abreviatura, nombre FROM public.tipo_documento WHERE activo ORDER BY nombre")
        return [dict(r) for r in cur.fetchall()]


def obtener_causas_atencion() -> list[dict]:
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, codigo, nombre FROM public.causa_atencion WHERE activo ORDER BY codigo")
        return [dict(r) for r in cur.fetchall()]


def obtener_modalidades_atencion() -> list[dict]:
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, codigo, nombre FROM public.modalidad_atencion ORDER BY codigo")
        return [dict(r) for r in cur.fetchall()]


def obtener_estados_evento() -> list[dict]:
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, nombre FROM public.estado_evento ORDER BY id")
        return [dict(r) for r in cur.fetchall()]


def obtener_tipos_afiliacion_activos() -> list[dict]:
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, nombre, COALESCE(codigo,'') AS codigo FROM public.tipo_afiliacion WHERE activo ORDER BY nombre")
        return [dict(r) for r in cur.fetchall()]


# =============================================================================
# MODULO 13: SESIONES ACTIVAS (supervision global)
# =============================================================================

def listar_sesiones_activas(ops_id: int, entidad_id: int | None = None) -> list[dict]:
    """
    El Maestro puede ver TODAS las sesiones activas del sistema.
    Si entidad_id se provee, filtra por esa entidad.
    """
    err = _check(ops_id)
    if err: raise PermissionError(err.mensaje)
    cond = "s.activa=TRUE AND s.expira_en>NOW()"; params: list = []
    if entidad_id:
        cond += " AND (s.entidad_id=%s OR u.entidad_id=%s)"; params += [entidad_id, entidad_id]
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT s.id AS sesion_id,
                   s.entidad_id, s.usuario_ops_id,
                   s.ip_origen, s.activa, s.creado_en, s.expira_en,
                   CASE WHEN s.entidad_id IS NOT NULL THEN 'admin' ELSE 'ops' END AS rol,
                   COALESCE(e.nombre_entidad, ep.nombre_entidad) AS entidad_nombre,
                   u.nombre_completo AS ops_nombre
            FROM public.sesion s
            LEFT JOIN public.entidad      e  ON e.id  = s.entidad_id
            LEFT JOIN public.usuario_ops  u  ON u.id  = s.usuario_ops_id
            LEFT JOIN public.entidad      ep ON ep.id = u.entidad_id
            WHERE {cond}
            ORDER BY s.creado_en DESC LIMIT 500
        """, params)
        return [dict(r) for r in cur.fetchall()]


def cerrar_sesion(ops_id: int, sesion_id: str) -> Resultado:
    """El Maestro puede cerrar forzadamente cualquier sesion activa."""
    err = _check(ops_id)
    if err: return err
    try:
        with Conexion() as conn:
            cur = conn.cursor()
            cur.execute("SELECT public.cerrar_sesion(%s::uuid)", (sesion_id,))
        return Resultado(True, "Sesion cerrada correctamente.")
    except Exception as e:
        return Resultado(False, f"Error: {e}")


# =============================================================================
# UTILITARIOS
# =============================================================================

def resolver_entidad_del_maestro(ops_id: int) -> int | None:
    """Retorna el entidad_id al que pertenece el Maestro."""
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT entidad_id FROM public.usuario_ops WHERE id=%s LIMIT 1", (ops_id,))
            row = cur.fetchone()
            return row["entidad_id"] if row else None
    except Exception:
        return None
