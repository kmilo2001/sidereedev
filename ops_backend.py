# -*- coding: utf-8 -*-
# =============================================================================
# ops_backend.py
# Gestión de Usuarios OPS — Sistema SIGES
#
# COMPATIBILIDAD:
#   - Usa conexion.py (Conexion, get_conexion_dict) directamente.
#   - Schema real: public.usuario_ops, public.tipo_documento,
#     public.entidad, public.sesion
#
# ── MODELO DE PERMISOS ───────────────────────────────────────────────────────
#
#   REGISTRO:
#     El usuario se registra por sí mismo desde el módulo de login.
#     Queda con activo = TRUE por defecto (según schema).
#     El admin/maestro puede desactivarlo si es necesario.
#
#   ACTIVACIÓN / DESACTIVACIÓN:
#     Solo pueden cambiar el campo activo:
#       • La entidad  (rol = 'admin')
#       • El usuario maestro (ops con nombre ILIKE 'maestro%')
#     Ningún otro OPS puede cambiar el estado de sus compañeros.
#
#   MAESTRO:
#     - Nombre debe comenzar con "Maestro" (case-insensitive).
#     - Solo puede existir uno por entidad.
#     - El maestro NO puede ser desactivado (ni por el admin).
#     - El maestro puede activar/desactivar cualquier OPS regular.
#     - El admin puede activar/desactivar cualquier OPS regular.
#
#   CONTRASEÑA (reset por gestor):
#     - Admin: puede resetear a cualquier OPS excepto al maestro.
#     - Maestro: puede resetear a cualquier OPS regular (no a sí mismo).
#     - El maestro cambia su pw SOLO por recuperación en el login.
#
# ── EJECUTOR ─────────────────────────────────────────────────────────────────
#   Funciones que requieren permisos reciben:
#     ejecutor: dict  { 'rol': 'admin'|'ops', 'ops_id': int|None,
#                       'entidad_id': int,     'es_maestro': bool }
#   Construir con construir_ejecutor() justo después del login.
#
# RPC UTILIZADAS:
#   rpc_registrar_ops(entidad_id, tipo_doc_abrev, numero_doc,
#                     nombre_completo, correo, whatsapp, hash) → json
#   rpc_cambiar_password(entidad_id, ops_id, nuevo_hash)       → json
# =============================================================================

from __future__ import annotations

import re
import json
import logging
from dataclasses import dataclass, field

import bcrypt

from conexion import Conexion

logger = logging.getLogger("siges.ops")


# ──────────────────────────────────────────────────────────────
# Tipo de resultado
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


def _rpc(v) -> dict:
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        return json.loads(v)
    return dict(v)


def _es_maestro(nombre_completo: str) -> bool:
    """True si el nombre corresponde al usuario maestro del sistema."""
    return str(nombre_completo).strip().lower().startswith("maestro")


def _es_ops_maestro(entidad_id: int, ops_id: int) -> bool:
    """Comprueba en la BD si el OPS dado es el usuario maestro."""
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT nombre_completo FROM public.usuario_ops "
                "WHERE id = %s AND entidad_id = %s LIMIT 1",
                (ops_id, entidad_id),
            )
            row = cur.fetchone()
            return _es_maestro(row["nombre_completo"]) if row else False
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────
# CONTEXTO DEL EJECUTOR
# ──────────────────────────────────────────────────────────────

def construir_ejecutor(rol: str, ops_id: int | None, entidad_id: int) -> dict:
    """
    Construye el dict ejecutor que se pasa a las funciones de permisos.
    Llamar justo después del login exitoso en la UI.

    Retorna:
        {
          'rol':        'admin' | 'ops',
          'ops_id':      int | None,
          'entidad_id':  int,
          'es_maestro':  bool,
          'nombre':      str,    # para mostrar en UI
        }
    """
    es_maestro = False
    nombre     = ""

    if rol == "ops" and ops_id:
        try:
            with Conexion(dict_cursor=True) as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT nombre_completo FROM public.usuario_ops "
                    "WHERE id = %s AND entidad_id = %s LIMIT 1",
                    (int(ops_id), entidad_id),
                )
                row = cur.fetchone()
                if row:
                    nombre     = row["nombre_completo"]
                    es_maestro = _es_maestro(nombre)
        except Exception:
            pass
    elif rol == "admin":
        try:
            with Conexion(dict_cursor=True) as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT nombre_entidad FROM public.entidad WHERE id = %s LIMIT 1",
                    (entidad_id,),
                )
                row = cur.fetchone()
                if row:
                    nombre = row["nombre_entidad"]
        except Exception:
            pass

    return {
        "rol":        rol,
        "ops_id":     int(ops_id) if ops_id else None,
        "entidad_id": entidad_id,
        "es_maestro": es_maestro,
        "nombre":     nombre,
    }


def puede_gestionar_estados(ejecutor: dict) -> bool:
    """True si el ejecutor puede activar/desactivar usuarios OPS."""
    return ejecutor.get("rol") == "admin" or ejecutor.get("es_maestro", False)


def puede_resetear_password(ejecutor: dict, objetivo_es_maestro: bool) -> bool:
    """
    True si el ejecutor puede resetear la contraseña del OPS objetivo.
    Nunca se puede resetear al maestro desde aquí.
    """
    if objetivo_es_maestro:
        return False
    return puede_gestionar_estados(ejecutor)


# ──────────────────────────────────────────────────────────────
# CATÁLOGOS
# ──────────────────────────────────────────────────────────────

def obtener_tipos_documento() -> list[dict]:
    """Retorna tipos de documento activos para ComboBox."""
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, abreviatura, nombre "
            "FROM public.tipo_documento WHERE activo = TRUE ORDER BY nombre"
        )
        return [dict(r) for r in cur.fetchall()]


# ──────────────────────────────────────────────────────────────
# LISTADO Y BÚSQUEDA
# ──────────────────────────────────────────────────────────────

def listar_ops(
    entidad_id:   int,
    filtro:       str  = "",
    solo_activos: bool = False,
    solo_inactivos: bool = False,
) -> list[dict]:
    """
    Lista usuarios OPS de la entidad.

    Filtros:
        filtro        → búsqueda ILIKE por nombre, documento o correo
        solo_activos  → solo usuarios con activo = TRUE
        solo_inactivos→ solo usuarios con activo = FALSE  (pendientes/desactivados)

    Columnas retornadas:
        ops_id, entidad_id, tipo_doc (abreviatura), tipo_doc_nombre,
        numero_documento, nombre_completo, correo, whatsapp,
        activo, creado_en, actualizado_en, es_maestro,
        sesiones_activas  (int — sesiones abiertas en este momento)
    """
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()

            filtro = filtro.strip() if filtro else ""
            like   = f"%{filtro}%" if filtro else "%"

            q = """
                SELECT
                    u.id               AS ops_id,
                    u.entidad_id,
                    td.abreviatura     AS tipo_doc,
                    td.nombre          AS tipo_doc_nombre,
                    u.numero_documento,
                    u.nombre_completo,
                    u.correo,
                    u.whatsapp,
                    u.activo,
                    u.creado_en,
                    u.actualizado_en,
                    (LOWER(u.nombre_completo) LIKE 'maestro%%') AS es_maestro,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM   public.sesion s
                        WHERE  s.usuario_ops_id = u.id
                          AND  s.activa = TRUE
                          AND  s.expira_en > NOW()
                    ), 0)::int                                   AS sesiones_activas
                FROM   public.usuario_ops u
                JOIN   public.tipo_documento td ON td.id = u.tipo_documento_id
                WHERE  u.entidad_id = %s
                  AND  (
                         u.nombre_completo ILIKE %s
                      OR u.numero_documento ILIKE %s
                      OR u.correo          ILIKE %s
                  )
            """
            params: list = [entidad_id, like, like, like]

            if solo_activos:
                q += " AND u.activo = TRUE"
            elif solo_inactivos:
                q += " AND u.activo = FALSE"

            # Maestro siempre primero, luego activos, luego nombre
            q += """
                ORDER BY
                    (LOWER(u.nombre_completo) LIKE 'maestro%%') DESC,
                    u.activo DESC,
                    u.nombre_completo ASC
                LIMIT 500
            """
            cur.execute(q, params)
            return [dict(r) for r in cur.fetchall()]

    except Exception:
        logger.exception("Error en listar_ops")
        raise


def listar_pendientes(entidad_id: int) -> list[dict]:
    """
    Atajo: retorna solo los usuarios con activo = FALSE.
    Son los que se registraron en el login y esperan aprobación,
    o los que fueron desactivados manualmente.
    """
    return listar_ops(entidad_id, solo_inactivos=True)


def obtener_ops(entidad_id: int, ops_id: int) -> dict | None:
    """Retorna el detalle completo de un OPS o None si no existe."""
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    u.id               AS ops_id,
                    u.entidad_id,
                    td.abreviatura     AS tipo_doc,
                    td.nombre          AS tipo_doc_nombre,
                    u.numero_documento,
                    u.nombre_completo,
                    u.correo,
                    u.whatsapp,
                    u.activo,
                    u.creado_en,
                    u.actualizado_en,
                    (LOWER(u.nombre_completo) LIKE 'maestro%%') AS es_maestro,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM   public.sesion s
                        WHERE  s.usuario_ops_id = u.id
                          AND  s.activa = TRUE
                          AND  s.expira_en > NOW()
                    ), 0)::int                                   AS sesiones_activas
                FROM   public.usuario_ops u
                JOIN   public.tipo_documento td ON td.id = u.tipo_documento_id
                WHERE  u.id = %s AND u.entidad_id = %s
                """,
                (ops_id, entidad_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception:
        logger.exception("Error en obtener_ops")
        raise


# ──────────────────────────────────────────────────────────────
# CREAR (desde el módulo de gestión, no desde el login)
# ──────────────────────────────────────────────────────────────

def crear_ops(entidad_id: int, datos: dict) -> Resultado:
    """
    Crea un nuevo usuario OPS vía public.rpc_registrar_ops.
    Solo admin o maestro pueden crear usuarios desde este módulo.

    datos requeridos:
        tipo_doc_abrev, numero_documento, nombre_completo,
        correo, whatsapp, password, confirmar_password

    Regla especial: Si nombre empieza con 'maestro' → usuario maestro.
    Solo puede existir uno por entidad.
    """
    requeridos = [
        "tipo_doc_abrev", "numero_documento", "nombre_completo",
        "correo", "whatsapp", "password", "confirmar_password",
    ]
    for campo in requeridos:
        if not str(datos.get(campo, "")).strip():
            return Resultado(False, f"El campo '{campo}' es obligatorio.")

    if not _email_ok(datos["correo"]):
        return Resultado(False, "El correo electrónico no es válido.")
    if len(datos["password"]) < 8:
        return Resultado(False, "La contraseña debe tener al menos 8 caracteres.")
    if datos["password"] != datos["confirmar_password"]:
        return Resultado(False, "Las contraseñas no coinciden.")

    nombre = datos["nombre_completo"].strip()

    if _es_maestro(nombre):
        try:
            with Conexion(dict_cursor=True) as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT 1 FROM public.usuario_ops "
                    "WHERE entidad_id = %s AND LOWER(nombre_completo) LIKE 'maestro%%' LIMIT 1",
                    (entidad_id,),
                )
                if cur.fetchone():
                    return Resultado(
                        False,
                        "Ya existe un usuario maestro para esta entidad. Solo puede haber uno.",
                    )
        except Exception as e:
            return Resultado(False, f"Error al verificar usuario maestro: {e}")

    try:
        pw_hash = _hash(datos["password"])
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT public.rpc_registrar_ops(%s,%s,%s,%s,%s,%s,%s) AS resultado",
                (
                    entidad_id,
                    datos["tipo_doc_abrev"].strip().upper(),
                    datos["numero_documento"].strip(),
                    nombre,
                    datos["correo"].strip().lower(),
                    datos["whatsapp"].strip(),
                    pw_hash,
                ),
            )
            fila = cur.fetchone()
            if fila is None:
                return Resultado(False, "La base de datos no devolvió respuesta.")
            res = _rpc(fila["resultado"])

        if not res.get("ok"):
            return Resultado(False, res.get("error", "Error al crear el usuario."))

        tipo_msg = "Usuario Maestro creado" if _es_maestro(nombre) else "Usuario OPS creado"
        return Resultado(True, f"{tipo_msg} exitosamente.", {"ops_id": str(res["ops_id"])})

    except Exception as e:
        logger.exception("Error en crear_ops")
        return Resultado(False, f"Error al crear usuario: {e}")


# ──────────────────────────────────────────────────────────────
# ACTUALIZAR (nombre, correo, whatsapp)
# ──────────────────────────────────────────────────────────────

def actualizar_ops(entidad_id: int, ops_id: int, datos: dict) -> Resultado:
    """
    Edita nombre_completo, correo y whatsapp.
    Tipo de documento y número de documento NO son modificables.
    """
    nombre   = str(datos.get("nombre_completo", "")).strip()
    correo   = str(datos.get("correo", "")).strip().lower()
    whatsapp = str(datos.get("whatsapp", "")).strip() or None

    if not nombre:
        return Resultado(False, "El nombre completo es obligatorio.")
    if not _email_ok(correo):
        return Resultado(False, "El correo electrónico no es válido.")

    actual = obtener_ops(entidad_id, ops_id)
    if not actual:
        return Resultado(False, "Usuario OPS no encontrado.")

    era_maestro  = _es_maestro(actual["nombre_completo"])
    sera_maestro = _es_maestro(nombre)

    if sera_maestro and not era_maestro:
        try:
            with Conexion(dict_cursor=True) as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT 1 FROM public.usuario_ops "
                    "WHERE entidad_id = %s AND LOWER(nombre_completo) LIKE 'maestro%%' "
                    "AND id != %s LIMIT 1",
                    (entidad_id, ops_id),
                )
                if cur.fetchone():
                    return Resultado(False, "Ya existe un usuario maestro. Solo puede haber uno.")
        except Exception as e:
            return Resultado(False, f"Error al verificar: {e}")

    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE public.usuario_ops
                SET    nombre_completo = %s,
                       correo          = %s,
                       whatsapp        = %s
                WHERE  id = %s AND entidad_id = %s
                """,
                (nombre, correo, whatsapp, ops_id, entidad_id),
            )
            if cur.rowcount == 0:
                return Resultado(False, "Usuario no encontrado o sin cambios.")
        return Resultado(True, "Usuario OPS actualizado correctamente.")

    except Exception as e:
        err = str(e).lower()
        if "unique" in err and "correo" in err:
            return Resultado(False, "Ya existe un usuario con ese correo en esta entidad.")
        logger.exception("Error en actualizar_ops")
        return Resultado(False, f"Error al actualizar: {e}")


# ──────────────────────────────────────────────────────────────
# ACTIVAR / DESACTIVAR  ← operación con control de permisos
# ──────────────────────────────────────────────────────────────

def cambiar_estado_ops(
    ejecutor:  dict,
    ops_id:    int,
    nuevo_activo: bool,
) -> Resultado:
    """
    Activa o desactiva un usuario OPS.

    Permisos requeridos:
        - ejecutor['rol'] == 'admin'  O
        - ejecutor['es_maestro'] == True

    Restricciones:
        - El usuario maestro NUNCA puede desactivarse (sea quien sea el ejecutor).
        - Un OPS regular sin permisos no puede cambiar el estado de nadie.
        - El ejecutor no puede cambiar su propio estado.

    Parámetros:
        ejecutor      dict construido con construir_ejecutor()
        ops_id        ID del OPS objetivo
        nuevo_activo  True = activar,  False = desactivar
    """
    entidad_id = ejecutor.get("entidad_id")

    # ── Verificar permiso del ejecutor ───────────────────────
    if not puede_gestionar_estados(ejecutor):
        return Resultado(
            False,
            "No tienes permiso para activar o desactivar usuarios. "
            "Esta acción es exclusiva de la entidad administradora o del usuario Maestro.",
        )

    # ── El ejecutor no puede cambiarse a sí mismo ────────────
    ejecutor_ops_id = ejecutor.get("ops_id")
    if ejecutor_ops_id and ejecutor_ops_id == ops_id:
        return Resultado(False, "No puedes cambiar tu propio estado de acceso.")

    # ── Obtener datos del objetivo ───────────────────────────
    objetivo = obtener_ops(entidad_id, ops_id)
    if not objetivo:
        return Resultado(False, "Usuario no encontrado en esta entidad.")

    # ── El maestro no puede desactivarse ─────────────────────
    if objetivo.get("es_maestro") and not nuevo_activo:
        return Resultado(
            False,
            "El usuario Maestro no puede ser desactivado. "
            "Es el responsable de la gestión de la entidad.",
        )

    accion = "activado" if nuevo_activo else "desactivado"

    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE public.usuario_ops SET activo = %s "
                "WHERE id = %s AND entidad_id = %s",
                (nuevo_activo, ops_id, entidad_id),
            )
            if cur.rowcount == 0:
                return Resultado(False, "No se pudo actualizar el estado del usuario.")

        # Cerrar sesiones activas al desactivar
        if not nuevo_activo:
            try:
                with Conexion() as conn2:
                    cur2 = conn2.cursor()
                    cur2.execute(
                        "UPDATE public.sesion "
                        "SET    activa = FALSE, cerrado_en = NOW() "
                        "WHERE  usuario_ops_id = %s AND activa = TRUE",
                        (ops_id,),
                    )
            except Exception:
                pass  # No crítico — las sesiones expirarán solas

        nombre_obj = objetivo.get("nombre_completo", "")
        return Resultado(
            True,
            f"Usuario '{nombre_obj}' {accion} correctamente.",
            {"ops_id": ops_id, "activo": nuevo_activo},
        )

    except Exception as e:
        logger.exception("Error en cambiar_estado_ops")
        return Resultado(False, f"Error al cambiar estado: {e}")


# ──────────────────────────────────────────────────────────────
# ACTIVACIÓN MASIVA (aprobar todos los pendientes)
# ──────────────────────────────────────────────────────────────

def activar_todos_pendientes(ejecutor: dict) -> Resultado:
    """
    Activa todos los usuarios con activo = FALSE de la entidad.
    Útil para aprobar en lote a los que se registraron en el login.

    Requiere: admin o maestro.
    """
    if not puede_gestionar_estados(ejecutor):
        return Resultado(
            False,
            "No tienes permiso para activar usuarios en lote.",
        )

    entidad_id = ejecutor.get("entidad_id")
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE public.usuario_ops SET activo = TRUE "
                "WHERE entidad_id = %s AND activo = FALSE",
                (entidad_id,),
            )
            cantidad = cur.rowcount
        return Resultado(
            True,
            f"{cantidad} usuario(s) activado(s) correctamente.",
            {"activados": cantidad},
        )
    except Exception as e:
        logger.exception("Error en activar_todos_pendientes")
        return Resultado(False, f"Error al activar usuarios: {e}")


# ──────────────────────────────────────────────────────────────
# CAMBIAR CONTRASEÑA (reset por admin/maestro)
# ──────────────────────────────────────────────────────────────

def cambiar_password_ops(
    ejecutor:  dict,
    ops_id:    int,
    nueva_pw:  str,
    confirmar: str,
) -> Resultado:
    """
    Reset de contraseña de un OPS ejecutado por admin o maestro.

    Restricciones:
        - El ejecutor debe ser admin o maestro.
        - El usuario maestro NO puede recibir reset (usa recuperación en login).
        - El ejecutor no puede resetear su propia contraseña desde aquí.
    """
    entidad_id = ejecutor.get("entidad_id")

    if not puede_gestionar_estados(ejecutor):
        return Resultado(False, "No tienes permiso para resetear contraseñas.")

    if len(nueva_pw) < 8:
        return Resultado(False, "La contraseña debe tener al menos 8 caracteres.")
    if nueva_pw != confirmar:
        return Resultado(False, "Las contraseñas no coinciden.")

    objetivo = obtener_ops(entidad_id, ops_id)
    if not objetivo:
        return Resultado(False, "Usuario no encontrado.")

    if not puede_resetear_password(ejecutor, objetivo.get("es_maestro", False)):
        if objetivo.get("es_maestro"):
            return Resultado(
                False,
                "El usuario Maestro debe cambiar su contraseña mediante el proceso "
                "de recuperación desde la pantalla de inicio de sesión.",
            )
        return Resultado(False, "No tienes permiso para resetear esta contraseña.")

    # El ejecutor OPS (maestro) no puede resetear su propia contraseña aquí
    ejecutor_ops_id = ejecutor.get("ops_id")
    if ejecutor_ops_id and ejecutor_ops_id == ops_id:
        return Resultado(
            False,
            "Para cambiar tu propia contraseña usa la opción 'Mi cuenta'.",
        )

    try:
        pw_hash = _hash(nueva_pw)
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            # rpc_cambiar_password cierra sesiones activas automáticamente
            cur.execute(
                "SELECT public.rpc_cambiar_password(%s, %s, %s) AS resultado",
                (None, ops_id, pw_hash),
            )
            fila = cur.fetchone()
            if fila is None:
                return Resultado(False, "La base de datos no devolvió respuesta.")
            res = _rpc(fila["resultado"])

        if not res.get("ok"):
            return Resultado(False, res.get("error", "Error al cambiar contraseña."))

        nombre_obj = objetivo.get("nombre_completo", "")
        return Resultado(
            True,
            f"Contraseña de '{nombre_obj}' actualizada. Las sesiones activas fueron cerradas.",
        )
    except Exception as e:
        logger.exception("Error en cambiar_password_ops")
        return Resultado(False, f"Error al cambiar contraseña: {e}")


# ──────────────────────────────────────────────────────────────
# ESTADÍSTICAS RÁPIDAS
# ──────────────────────────────────────────────────────────────

def stats_ops(entidad_id: int) -> dict:
    """
    Retorna contadores del módulo:
        total, activos, inactivos, pendientes (inactivos),
        maestro_existe, sesiones_en_curso
    """
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    COUNT(*)                                                AS total,
                    COUNT(*) FILTER (WHERE activo = TRUE)                  AS activos,
                    COUNT(*) FILTER (WHERE activo = FALSE)                 AS inactivos,
                    COUNT(*) FILTER (
                        WHERE LOWER(nombre_completo) LIKE 'maestro%%'
                    )                                                      AS maestros,
                    COALESCE((
                        SELECT COUNT(*)
                        FROM   public.sesion s
                        JOIN   public.usuario_ops u2 ON u2.id = s.usuario_ops_id
                        WHERE  u2.entidad_id = %s
                          AND  s.activa = TRUE
                          AND  s.expira_en > NOW()
                    ), 0)::int                                             AS sesiones_en_curso
                FROM public.usuario_ops
                WHERE entidad_id = %s
                """,
                (entidad_id, entidad_id),
            )
            row = cur.fetchone()
            if row:
                return {
                    "total":           int(row["total"]),
                    "activos":         int(row["activos"]),
                    "inactivos":       int(row["inactivos"]),
                    "maestro_existe":  int(row["maestros"]) > 0,
                    "sesiones_en_curso": int(row["sesiones_en_curso"]),
                }
    except Exception as e:
        logger.error("Error en stats_ops: %s", e)

    return {
        "total": 0, "activos": 0, "inactivos": 0,
        "maestro_existe": False, "sesiones_en_curso": 0,
    }
