# -*- coding: utf-8 -*-
# =============================================================================
# entidad_backend.py
# Gestión de Entidades (IPS / Hospital) — SIGES
#
# ACCESO:  EXCLUSIVO para el usuario Maestro (ops con nombre ILIKE 'maestro%').
#          Ningún otro perfil puede llamar estas funciones.
#
# TABLA:   public.entidad
#   id, nombre_entidad, nit, codigo_habilitacion, nivel_atencion,
#   municipio, departamento, celular, correo, password_hash,
#   activo, protegido, creado_en, actualizado_en
#
# REGLAS DE NEGOCIO:
#   1. Solo el Maestro puede crear, editar, activar/desactivar entidades.
#   2. Una entidad con protegido = TRUE nunca puede desactivarse.
#   3. Al desactivar una entidad se cierran todas sus sesiones activas
#      (entidad + sus usuarios OPS).
#   4. No existe eliminación física. Solo desactivación.
#   5. El NIT tiene formato ^\\d+-\\d$  (ej: 900123456-7).
#   6. La contraseña inicial la establece el Maestro; la entidad puede
#      cambiarla después desde su propio perfil.
#
# RPC UTILIZADAS (schema public.*):
#   rpc_registrar_entidad(nombre, nit, cod_hab, nivel, municipio,
#                         departamento, celular, correo, hash)  → json
#   rpc_cambiar_password(entidad_id, ops_id, nuevo_hash)        → json
#   cerrar_todas_sesiones(entidad_id, ops_id)                   → int
# =============================================================================

from __future__ import annotations

import re
import json
import logging
from dataclasses import dataclass, field

import bcrypt

from conexion import Conexion

logger = logging.getLogger("siges.entidad")


# ──────────────────────────────────────────────────────────────
# Resultado estándar
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
    """Formato DIAN: dígitos-dígito  (ej: 900123456-7)."""
    return bool(re.match(r"^\d+-\d$", nit.strip()))


def _rpc(v) -> dict:
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        return json.loads(v)
    return dict(v)


def _es_maestro_ops(ops_id: int) -> bool:
    """Verifica en la BD que el OPS sea el usuario Maestro."""
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT nombre_completo FROM public.usuario_ops "
                "WHERE id = %s AND activo = TRUE LIMIT 1",
                (ops_id,),
            )
            row = cur.fetchone()
            return bool(row) and row["nombre_completo"].strip().lower().startswith("maestro")
    except Exception:
        return False


def _verificar_maestro(ops_id: int) -> Resultado | None:
    """
    Retorna None si el ops_id corresponde al Maestro (acceso permitido).
    Retorna Resultado de error si NO tiene acceso.
    """
    if not ops_id or not _es_maestro_ops(ops_id):
        return Resultado(
            False,
            "Acceso denegado. Este módulo es exclusivo del usuario Maestro.",
        )
    return None


# ──────────────────────────────────────────────────────────────
# LISTADO Y BÚSQUEDA
# ──────────────────────────────────────────────────────────────

NIVELES = {1: "Nivel 1 — Básico", 2: "Nivel 2 — Mediano", 3: "Nivel 3 — Alto"}


def listar_entidades(
    ops_id:        int,
    filtro:        str  = "",
    solo_activas:  bool = False,
    solo_inactivas:bool = False,
) -> list[dict]:
    """
    Lista todas las entidades registradas (visión global del Maestro).

    Columnas retornadas:
        id, nombre_entidad, nit, codigo_habilitacion, nivel_atencion,
        nivel_texto, municipio, departamento, celular, correo,
        activo, protegido, creado_en, actualizado_en,
        total_ops, ops_activos, sesiones_activas
    """
    err = _verificar_maestro(ops_id)
    if err:
        raise PermissionError(err.mensaje)

    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            filtro = filtro.strip() if filtro else ""
            like   = f"%{filtro}%" if filtro else "%"

            q = """
                SELECT
                    e.id,
                    e.nombre_entidad,
                    e.nit,
                    e.codigo_habilitacion,
                    e.nivel_atencion,
                    CASE e.nivel_atencion
                        WHEN 1 THEN 'Nivel 1 — Básico'
                        WHEN 2 THEN 'Nivel 2 — Mediano'
                        WHEN 3 THEN 'Nivel 3 — Alto'
                        ELSE        'No definido'
                    END                                          AS nivel_texto,
                    e.municipio,
                    e.departamento,
                    e.celular,
                    e.correo,
                    e.activo,
                    e.protegido,
                    e.creado_en,
                    e.actualizado_en,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM   public.usuario_ops u
                        WHERE  u.entidad_id = e.id
                    ), 0)::int                                   AS total_ops,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM   public.usuario_ops u
                        WHERE  u.entidad_id = e.id AND u.activo = TRUE
                    ), 0)::int                                   AS ops_activos,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM   public.sesion s
                        WHERE  s.entidad_id = e.id
                          AND  s.activa     = TRUE
                          AND  s.expira_en  > NOW()
                    ), 0)::int                                   AS sesiones_activas
                FROM public.entidad e
                WHERE (
                       e.nombre_entidad ILIKE %s
                    OR e.nit            ILIKE %s
                    OR e.municipio      ILIKE %s
                    OR e.departamento   ILIKE %s
                    OR e.correo         ILIKE %s
                )
            """
            params: list = [like, like, like, like, like]

            if solo_activas:
                q += " AND e.activo = TRUE"
            elif solo_inactivas:
                q += " AND e.activo = FALSE"

            q += """
                ORDER BY
                    e.protegido  DESC,
                    e.activo     DESC,
                    e.nombre_entidad ASC
                LIMIT 500
            """
            cur.execute(q, params)
            return [dict(r) for r in cur.fetchall()]

    except PermissionError:
        raise
    except Exception:
        logger.exception("Error en listar_entidades")
        raise


def obtener_entidad(ops_id: int, entidad_id: int) -> dict | None:
    """Retorna el detalle completo de una entidad o None."""
    err = _verificar_maestro(ops_id)
    if err:
        raise PermissionError(err.mensaje)

    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    e.id,
                    e.nombre_entidad,
                    e.nit,
                    e.codigo_habilitacion,
                    e.nivel_atencion,
                    CASE e.nivel_atencion
                        WHEN 1 THEN 'Nivel 1 — Básico'
                        WHEN 2 THEN 'Nivel 2 — Mediano'
                        WHEN 3 THEN 'Nivel 3 — Alto'
                        ELSE        'No definido'
                    END                                          AS nivel_texto,
                    e.municipio,
                    e.departamento,
                    e.celular,
                    e.correo,
                    e.activo,
                    e.protegido,
                    e.creado_en,
                    e.actualizado_en,
                    COALESCE((
                        SELECT COUNT(*) FROM public.usuario_ops u
                        WHERE u.entidad_id = e.id
                    ), 0)::int   AS total_ops,
                    COALESCE((
                        SELECT COUNT(*) FROM public.usuario_ops u
                        WHERE u.entidad_id = e.id AND u.activo = TRUE
                    ), 0)::int   AS ops_activos,
                    COALESCE((
                        SELECT COUNT(*) FROM public.sesion s
                        WHERE s.entidad_id = e.id
                          AND s.activa = TRUE AND s.expira_en > NOW()
                    ), 0)::int   AS sesiones_activas
                FROM public.entidad e
                WHERE e.id = %s
                """,
                (entidad_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    except PermissionError:
        raise
    except Exception:
        logger.exception("Error en obtener_entidad")
        raise


# ──────────────────────────────────────────────────────────────
# CREAR ENTIDAD
# ──────────────────────────────────────────────────────────────

def crear_entidad(ops_id: int, datos: dict) -> Resultado:
    """
    Registra una nueva IPS/Hospital vía public.rpc_registrar_entidad.

    datos requeridos:
        nombre_entidad, nit, celular, correo,
        password, confirmar_password

    datos opcionales:
        codigo_habilitacion, nivel_atencion (1|2|3),
        municipio, departamento
    """
    err = _verificar_maestro(ops_id)
    if err:
        return err

    requeridos = ["nombre_entidad", "nit", "celular", "correo",
                  "password", "confirmar_password"]
    for campo in requeridos:
        if not str(datos.get(campo, "")).strip():
            return Resultado(False, f"El campo '{campo}' es obligatorio.")

    if not _nit_ok(datos["nit"]):
        return Resultado(
            False,
            "El NIT debe tener formato xxxxx-x  (ej: 900123456-7).",
        )
    if not _email_ok(datos["correo"]):
        return Resultado(False, "El correo electrónico no tiene un formato válido.")
    if len(datos["password"]) < 8:
        return Resultado(False, "La contraseña debe tener al menos 8 caracteres.")
    if datos["password"] != datos["confirmar_password"]:
        return Resultado(False, "Las contraseñas no coinciden.")

    nivel = datos.get("nivel_atencion")
    if nivel is not None:
        try:
            nivel = int(nivel)
            if nivel not in (1, 2, 3):
                raise ValueError
        except (ValueError, TypeError):
            return Resultado(False, "El nivel de atención debe ser 1, 2 o 3.")

    try:
        pw_hash = _hash(datos["password"])
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT public.rpc_registrar_entidad(
                    %s, %s, %s, %s::smallint, %s, %s, %s, %s, %s
                ) AS resultado
                """,
                (
                    datos["nombre_entidad"].strip(),
                    datos["nit"].strip(),
                    (datos.get("codigo_habilitacion") or "").strip() or None,
                    nivel,
                    (datos.get("municipio") or "").strip() or None,
                    (datos.get("departamento") or "").strip() or None,
                    datos["celular"].strip(),
                    datos["correo"].strip().lower(),
                    pw_hash,
                ),
            )
            fila = cur.fetchone()
            if fila is None:
                return Resultado(False, "La base de datos no devolvió respuesta.")
            res = _rpc(fila["resultado"])

        if not res.get("ok"):
            return Resultado(False, res.get("error", "Error al registrar la entidad."))

        return Resultado(
            True,
            f"Entidad '{datos['nombre_entidad'].strip()}' registrada exitosamente.",
            {"entidad_id": str(res["entidad_id"])},
        )

    except Exception as e:
        logger.exception("Error en crear_entidad")
        return Resultado(False, f"Error al registrar: {e}")


# ──────────────────────────────────────────────────────────────
# EDITAR ENTIDAD
# ──────────────────────────────────────────────────────────────

def editar_entidad(ops_id: int, entidad_id: int, datos: dict) -> Resultado:
    """
    Actualiza los campos editables de una entidad.
    Campos editables: nombre_entidad, codigo_habilitacion, nivel_atencion,
                      municipio, departamento, celular, correo.
    NIT no es modificable (es el identificador único de la entidad).
    """
    err = _verificar_maestro(ops_id)
    if err:
        return err

    nombre = str(datos.get("nombre_entidad", "")).strip()
    correo = str(datos.get("correo", "")).strip().lower()

    if not nombre:
        return Resultado(False, "El nombre de la entidad es obligatorio.")
    if not _email_ok(correo):
        return Resultado(False, "El correo electrónico no es válido.")

    celular = str(datos.get("celular", "")).strip() or None
    municipio   = str(datos.get("municipio", "")).strip() or None
    departamento = str(datos.get("departamento", "")).strip() or None
    cod_hab     = str(datos.get("codigo_habilitacion", "")).strip() or None

    nivel = datos.get("nivel_atencion")
    if nivel is not None and nivel != "":
        try:
            nivel = int(nivel)
            if nivel not in (1, 2, 3):
                raise ValueError
        except (ValueError, TypeError):
            return Resultado(False, "El nivel de atención debe ser 1, 2 o 3.")
    else:
        nivel = None

    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE public.entidad
                SET    nombre_entidad       = %s,
                       codigo_habilitacion  = %s,
                       nivel_atencion       = %s::smallint,
                       municipio            = %s,
                       departamento         = %s,
                       celular              = %s,
                       correo               = %s
                WHERE  id = %s
                RETURNING id
                """,
                (nombre, cod_hab, nivel, municipio, departamento,
                 celular, correo, entidad_id),
            )
            if not cur.fetchone():
                return Resultado(False, "Entidad no encontrada.")

        return Resultado(True, "Entidad actualizada correctamente.")

    except Exception as e:
        err_str = str(e).lower()
        if "unique" in err_str and "correo" in err_str:
            return Resultado(False, "Ya existe otra entidad con ese correo.")
        logger.exception("Error en editar_entidad")
        return Resultado(False, f"Error al actualizar: {e}")


# ──────────────────────────────────────────────────────────────
# ACTIVAR / DESACTIVAR
# ──────────────────────────────────────────────────────────────

def cambiar_estado_entidad(
    ops_id:      int,
    entidad_id:  int,
    nuevo_activo: bool,
) -> Resultado:
    """
    Activa o desactiva una entidad.

    Restricciones:
        - Solo el Maestro puede ejecutar esta acción.
        - Una entidad con protegido = TRUE NUNCA puede desactivarse.
        - Al desactivar se cierran todas las sesiones de esa entidad
          y de todos sus usuarios OPS.
    """
    err = _verificar_maestro(ops_id)
    if err:
        return err

    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()

            # Verificar existencia y estado protegido
            cur.execute(
                "SELECT nombre_entidad, protegido, activo "
                "FROM public.entidad WHERE id = %s LIMIT 1",
                (entidad_id,),
            )
            fila = cur.fetchone()
            if not fila:
                return Resultado(False, "Entidad no encontrada.")

            if not nuevo_activo and fila["protegido"]:
                return Resultado(
                    False,
                    f"La entidad '{fila['nombre_entidad']}' está protegida "
                    "y no puede ser desactivada.",
                )

            nombre = fila["nombre_entidad"]

            # Actualizar estado
            cur.execute(
                "UPDATE public.entidad SET activo = %s WHERE id = %s",
                (nuevo_activo, entidad_id),
            )

        # Cerrar sesiones si se desactiva
        if not nuevo_activo:
            try:
                with Conexion() as conn2:
                    cur2 = conn2.cursor()
                    # Sesiones de la entidad misma
                    cur2.execute(
                        "UPDATE public.sesion SET activa = FALSE, cerrado_en = NOW() "
                        "WHERE entidad_id = %s AND activa = TRUE",
                        (entidad_id,),
                    )
                    # Sesiones de todos sus OPS
                    cur2.execute(
                        """
                        UPDATE public.sesion
                        SET    activa = FALSE, cerrado_en = NOW()
                        WHERE  activa = TRUE
                          AND  usuario_ops_id IN (
                                SELECT id FROM public.usuario_ops
                                WHERE  entidad_id = %s
                          )
                        """,
                        (entidad_id,),
                    )
            except Exception:
                pass  # No crítico — las sesiones expirarán solas

        accion = "activada" if nuevo_activo else "desactivada"
        return Resultado(
            True,
            f"Entidad '{nombre}' {accion} correctamente.",
            {"entidad_id": entidad_id, "activo": nuevo_activo},
        )

    except Exception as e:
        logger.exception("Error en cambiar_estado_entidad")
        return Resultado(False, f"Error al cambiar estado: {e}")


# ──────────────────────────────────────────────────────────────
# RESETEAR CONTRASEÑA DE ENTIDAD
# ──────────────────────────────────────────────────────────────

def resetear_password_entidad(
    ops_id:     int,
    entidad_id: int,
    nueva_pw:   str,
    confirmar:  str,
) -> Resultado:
    """
    El Maestro puede resetear la contraseña de cualquier entidad.
    Usa rpc_cambiar_password que además cierra todas las sesiones activas.
    """
    err = _verificar_maestro(ops_id)
    if err:
        return err

    if len(nueva_pw) < 8:
        return Resultado(False, "La contraseña debe tener al menos 8 caracteres.")
    if nueva_pw != confirmar:
        return Resultado(False, "Las contraseñas no coinciden.")

    try:
        # Verificar que la entidad existe
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT nombre_entidad FROM public.entidad WHERE id = %s LIMIT 1",
                (entidad_id,),
            )
            fila = cur.fetchone()
            if not fila:
                return Resultado(False, "Entidad no encontrada.")
            nombre = fila["nombre_entidad"]

        pw_hash = _hash(nueva_pw)

        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT public.rpc_cambiar_password(%s, %s, %s) AS resultado",
                (entidad_id, None, pw_hash),
            )
            fila = cur.fetchone()
            if fila is None:
                return Resultado(False, "La base de datos no devolvió respuesta.")
            res = _rpc(fila["resultado"])

        if not res.get("ok"):
            return Resultado(False, res.get("error", "Error al cambiar contraseña."))

        return Resultado(
            True,
            f"Contraseña de '{nombre}' actualizada. Las sesiones activas fueron cerradas.",
        )

    except Exception as e:
        logger.exception("Error en resetear_password_entidad")
        return Resultado(False, f"Error al cambiar contraseña: {e}")


# ──────────────────────────────────────────────────────────────
# ESTADÍSTICAS GLOBALES
# ──────────────────────────────────────────────────────────────

def stats_globales(ops_id: int) -> dict:
    """
    Estadísticas del sistema completo para la vista del Maestro.
    Usa public.stats_sistema() + conteos directos.
    """
    err = _verificar_maestro(ops_id)
    if err:
        raise PermissionError(err.mensaje)

    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    COUNT(*)                                           AS total,
                    COUNT(*) FILTER (WHERE activo = TRUE)             AS activas,
                    COUNT(*) FILTER (WHERE activo = FALSE)            AS inactivas,
                    COUNT(*) FILTER (WHERE protegido = TRUE)          AS protegidas,
                    COALESCE((
                        SELECT COUNT(*) FROM public.sesion
                        WHERE activa = TRUE AND expira_en > NOW()
                    ), 0)::int                                        AS sesiones_en_curso
                FROM public.entidad
            """)
            row = cur.fetchone()
            return {
                "total":            int(row["total"]),
                "activas":          int(row["activas"]),
                "inactivas":        int(row["inactivas"]),
                "protegidas":       int(row["protegidas"]),
                "sesiones_en_curso": int(row["sesiones_en_curso"]),
            }
    except PermissionError:
        raise
    except Exception as e:
        logger.error("Error en stats_globales: %s", e)
        return {"total": 0, "activas": 0, "inactivas": 0,
                "protegidas": 0, "sesiones_en_curso": 0}