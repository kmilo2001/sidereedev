# -*- coding: utf-8 -*-
# =============================================================================
# login_backend.py
# Lógica de autenticación para el Sistema de Gestión de Eventos - Sector Salud
#
# COMPATIBILIDAD:
#   - Usa conexion.py (Conexion, get_conexion_dict) directamente.
#   - Schema PostgreSQL: entidad, usuario_ops, tipo_documento,
#     sesion, token_recuperacion  (gestion_eventos_salud.sql)
#
# FLUJO LOGIN:
#   1. Siempre primero verifica si el documento corresponde al Maestro
#      (usuario_ops con nombre_completo ILIKE 'maestro%').  Si coincide →
#      autentica contra usuario_ops y retorna rol='maestro'.
#   2. Tipo doc == 'NIT'  → busca en public.entidad  por nit      (admin)
#   3. Cualquier otro     → busca en public.usuario_ops por tipo+doc (ops)
#
# RPC UTILIZADAS (todas en public.*):
#   rpc_registrar_entidad(nombre, nit, cod_hab, nivel, municipio,
#                         departamento, celular, correo, hash) → json
#   rpc_registrar_ops(entidad_id, tipo_doc_abrev, doc,
#                     nombre, correo, wa, hash)                  → json
#   rpc_cambiar_password(entidad_id, ops_id, nuevo_hash)         → json
#   cerrar_sesion(uuid)                                          → void
#   validar_token_recuperacion(ent_id, ops_id, codigo, medio)    → bool
#
# HASHING: bcrypt en Python (nunca delegado a la BD).
# =============================================================================

from __future__ import annotations

import re
import logging
import secrets
import string
from dataclasses import dataclass, field

import bcrypt

from conexion import Conexion

logger = logging.getLogger("siges.login")


# ──────────────────────────────────────────────────────────────
# Tipo de resultado unificado
# ──────────────────────────────────────────────────────────────

@dataclass
class AuthResult:
    """Resultado estándar de todas las operaciones de autenticación."""
    ok:      bool
    mensaje: str
    datos:   dict | None = field(default=None)


# ──────────────────────────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────────────────────────

def _hash_pw(plain: str) -> str:
    """Genera hash bcrypt (costo 10). NUNCA almacenar la contraseña en claro."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(10)).decode("utf-8")


def _check_pw(plain: str, hashed: str) -> bool:
    """Verifica contraseña contra hash bcrypt. Retorna False ante cualquier error."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _validar_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))


def _validar_nit(nit: str) -> bool:
    """Formato requerido por la BD: dígitos-dígito  (ej. 900123456-7)."""
    return bool(re.match(r"^\d+-\d$", nit.strip()))


def _generar_otp(longitud: int = 6) -> str:
    """Genera un código OTP numérico seguro."""
    return "".join(secrets.choice(string.digits) for _ in range(longitud))


# ──────────────────────────────────────────────────────────────
# CATÁLOGOS
# ──────────────────────────────────────────────────────────────

def obtener_tipos_documento() -> list[dict]:
    """
    Retorna lista de tipos de documento activos para poblar ComboBox.
    Campos: id (smallint), abreviatura, nombre
    """
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, abreviatura, nombre
            FROM   public.tipo_documento
            WHERE  activo = TRUE
            ORDER  BY nombre
            """
        )
        return [dict(r) for r in cur.fetchall()]


# ──────────────────────────────────────────────────────────────
# LOGIN
# ──────────────────────────────────────────────────────────────

def login(tipo_doc_abrev: str, documento: str, password: str) -> AuthResult:
    """
    Autentica un usuario.

    Parámetros:
        tipo_doc_abrev  'NIT' para entidad-admin; cualquier abreviatura de
                        tipo_documento para usuario OPS.
        documento       NIT (ej. 900123456-7) o número de documento.
        password        Contraseña en texto claro.

    Retorna AuthResult con datos = {
        'rol':        'maestro' | 'admin' | 'ops',
        'id':         str,
        'entidad_id': str,   # presente en rol='ops' y rol='maestro'
        'nombre':     str,
        'correo':     str,
        'nit':        str,   # solo presente en rol='admin'
        'sesion_id':  str    # UUID
    }
    """
    if not tipo_doc_abrev or not documento or not password:
        return AuthResult(False, "Todos los campos son obligatorios.")

    tipo_abrev = tipo_doc_abrev.strip().upper()
    documento  = documento.strip()

    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()

            # ── 1. Verificar si es el Maestro (SIEMPRE primero, sin importar tipo_doc) ──
            # El Maestro vive en usuario_ops, no en entidad.
            # Se identifica por nombre_completo ILIKE 'maestro%'.
            cur.execute(
                """
                SELECT u.id, u.entidad_id, u.nombre_completo AS nombre,
                       u.correo, u.password_hash, u.activo
                FROM   public.usuario_ops u
                JOIN   public.tipo_documento td ON td.id = u.tipo_documento_id
                WHERE  u.numero_documento = %s
                  AND  LOWER(u.nombre_completo) LIKE 'maestro%%'
                LIMIT  1
                """,
                (documento,),
            )
            fila_maestro = cur.fetchone()

            if fila_maestro:
                if not fila_maestro["activo"]:
                    return AuthResult(
                        False,
                        "La cuenta Maestro está inactiva. Contacta al administrador del sistema.",
                    )
                if not _check_pw(password, fila_maestro["password_hash"]):
                    return AuthResult(False, "Contraseña incorrecta.")

                sesion_id = _crear_sesion(cur, entidad_id=None, ops_id=fila_maestro["id"])
                payload = {
                    "rol":        "maestro",
                    "id":         str(fila_maestro["id"]),
                    "entidad_id": str(fila_maestro["entidad_id"]),
                    "nombre":     fila_maestro["nombre"],
                    "correo":     fila_maestro["correo"],
                    "sesion_id":  sesion_id,
                }
                logger.info("Login OK — rol=maestro id=%s", payload["id"])
                return AuthResult(ok=True, mensaje="Inicio de sesión exitoso.", datos=payload)

            # ── 2. Login normal: NIT = entidad (admin) ─────────────────────
            if tipo_abrev == "NIT":
                # ── Autenticación de entidad (admin) ──────────────────
                cur.execute(
                    """
                    SELECT id, nombre_entidad AS nombre, nit, correo,
                           password_hash, activo
                    FROM   public.entidad
                    WHERE  nit = %s
                    LIMIT  1
                    """,
                    (documento,),
                )
                fila = cur.fetchone()

                if not fila:
                    return AuthResult(
                        False,
                        "No se encontró ninguna entidad con ese NIT. "
                        "Verifica el número ingresado.",
                    )

                if not fila["activo"]:
                    return AuthResult(
                        False,
                        "Esta entidad está inactiva. Contacta al administrador del sistema.",
                    )

                if not _check_pw(password, fila["password_hash"]):
                    return AuthResult(False, "Contraseña incorrecta.")

                sesion_id = _crear_sesion(cur, entidad_id=fila["id"], ops_id=None)
                payload = {
                    "rol":       "admin",
                    "id":        str(fila["id"]),
                    "nombre":    fila["nombre"],
                    "correo":    fila["correo"],
                    "nit":       fila["nit"],
                    "sesion_id": sesion_id,
                }

            else:
                # ── 3. Login OPS normal ───────────────────────────────
                cur.execute(
                    """
                    SELECT u.id, u.entidad_id, u.nombre_completo AS nombre,
                           u.correo, u.password_hash, u.activo
                    FROM   public.usuario_ops   u
                    JOIN   public.tipo_documento td ON td.id = u.tipo_documento_id
                    WHERE  td.abreviatura      = %s
                      AND  u.numero_documento  = %s
                    LIMIT  1
                    """,
                    (tipo_abrev, documento),
                )
                fila = cur.fetchone()

                if not fila:
                    return AuthResult(
                        False,
                        "Usuario no encontrado. Verifica el tipo y número de documento.",
                    )

                if not fila["activo"]:
                    return AuthResult(
                        False,
                        "Esta cuenta está inactiva. Contacta al administrador de tu entidad.",
                    )

                if not _check_pw(password, fila["password_hash"]):
                    return AuthResult(False, "Contraseña incorrecta.")

                sesion_id = _crear_sesion(cur, entidad_id=None, ops_id=fila["id"])
                payload = {
                    "rol":        "ops",
                    "id":         str(fila["id"]),
                    "entidad_id": str(fila["entidad_id"]),
                    "nombre":     fila["nombre"],
                    "correo":     fila["correo"],
                    "sesion_id":  sesion_id,
                }

        logger.info("Login OK — rol=%s id=%s", payload["rol"], payload["id"])
        return AuthResult(ok=True, mensaje="Inicio de sesión exitoso.", datos=payload)

    except Exception as e:
        logger.exception("Error inesperado en login")
        return AuthResult(False, f"Error al iniciar sesión: {e}")


def _crear_sesion(
    cur,
    entidad_id: int | None,
    ops_id:     int | None,
    ip:         str = "127.0.0.1",
    horas:      int = 8,
) -> str:
    """Inserta una sesión y retorna su UUID como str."""
    cur.execute(
        """
        INSERT INTO public.sesion (entidad_id, usuario_ops_id, ip_origen, expira_en)
        VALUES (%s, %s, %s::inet, NOW() + (%s || ' hours')::INTERVAL)
        RETURNING id
        """,
        (entidad_id, ops_id, ip, horas),
    )
    return str(cur.fetchone()["id"])


def cerrar_sesion(sesion_id: str) -> None:
    """Invalida la sesión en la BD."""
    try:
        with Conexion() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT public.cerrar_sesion(%s::uuid)",
                (sesion_id,),
            )
    except Exception as e:
        logger.warning("No se pudo cerrar sesión %s: %s", sesion_id, e)


# ──────────────────────────────────────────────────────────────
# REGISTRO DE ENTIDAD (admin)
# ──────────────────────────────────────────────────────────────

def registrar_entidad(datos: dict) -> AuthResult:
    """
    Registra una nueva IPS/Hospital vía public.rpc_registrar_entidad.

    datos requeridos:
        nombre_entidad, nit, celular, correo,
        password, confirmar_password

    datos opcionales:
        codigo_habilitacion, nivel_atencion (1|2|3),
        municipio, departamento
    """
    requeridos = ["nombre_entidad", "nit", "celular", "correo",
                  "password", "confirmar_password"]
    for campo in requeridos:
        if not datos.get(campo, "").strip():
            return AuthResult(False, f"El campo '{campo}' es obligatorio.")

    if not _validar_nit(datos["nit"]):
        return AuthResult(
            False,
            "El NIT debe tener el formato xxxxx-x  (ej. 900123456-7).",
        )
    if not _validar_email(datos["correo"]):
        return AuthResult(False, "El correo electrónico no tiene un formato válido.")
    if len(datos["password"]) < 8:
        return AuthResult(False, "La contraseña debe tener al menos 8 caracteres.")
    if datos["password"] != datos["confirmar_password"]:
        return AuthResult(False, "Las contraseñas no coinciden.")

    try:
        pw_hash = _hash_pw(datos["password"])

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
                    datos.get("codigo_habilitacion", "").strip() or None,
                    datos.get("nivel_atencion") or None,
                    datos.get("municipio", "").strip() or None,
                    datos.get("departamento", "").strip() or None,
                    datos["celular"].strip(),
                    datos["correo"].strip().lower(),
                    pw_hash,
                ),
            )
            fila = cur.fetchone()

        if fila is None:
            return AuthResult(False, "La base de datos no devolvió respuesta.")

        res = fila["resultado"]
        if isinstance(res, str):
            import json
            res = json.loads(res)

        if not res.get("ok"):
            return AuthResult(False, res.get("error", "Error al registrar la entidad."))

        return AuthResult(
            ok=True,
            mensaje="Entidad registrada exitosamente. Ya puedes iniciar sesión.",
            datos={"id": str(res["entidad_id"])},
        )

    except Exception as e:
        logger.exception("Error inesperado en registrar_entidad")
        return AuthResult(False, f"Error al registrar entidad: {e}")


# Alias de compatibilidad
registrar_admin = registrar_entidad


# ──────────────────────────────────────────────────────────────
# REGISTRO DE USUARIO OPS
# ──────────────────────────────────────────────────────────────

def registrar_ops(datos: dict) -> AuthResult:
    """
    Registra un nuevo usuario operativo vía public.rpc_registrar_ops.

    datos requeridos:
        entidad_id, tipo_doc_abrev, numero_documento,
        nombre_completo, correo, whatsapp,
        password, confirmar_password
    """
    requeridos = [
        "entidad_id", "tipo_doc_abrev", "numero_documento",
        "nombre_completo", "correo", "whatsapp",
        "password", "confirmar_password",
    ]
    for campo in requeridos:
        if not str(datos.get(campo, "")).strip():
            return AuthResult(False, f"El campo '{campo}' es obligatorio.")

    if not _validar_email(datos["correo"]):
        return AuthResult(False, "El correo electrónico no tiene un formato válido.")
    if len(datos["password"]) < 8:
        return AuthResult(False, "La contraseña debe tener al menos 8 caracteres.")
    if datos["password"] != datos["confirmar_password"]:
        return AuthResult(False, "Las contraseñas no coinciden.")

    try:
        pw_hash = _hash_pw(datos["password"])

        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT public.rpc_registrar_ops(
                    %s, %s, %s, %s, %s, %s, %s
                ) AS resultado
                """,
                (
                    int(datos["entidad_id"]),
                    datos["tipo_doc_abrev"].strip().upper(),
                    datos["numero_documento"].strip(),
                    datos["nombre_completo"].strip(),
                    datos["correo"].strip().lower(),
                    datos["whatsapp"].strip(),
                    pw_hash,
                ),
            )
            fila = cur.fetchone()

        if fila is None:
            return AuthResult(False, "La base de datos no devolvió respuesta.")

        res = fila["resultado"]
        if isinstance(res, str):
            import json
            res = json.loads(res)

        if not res.get("ok"):
            return AuthResult(False, res.get("error", "Error al registrar el usuario."))

        return AuthResult(
            ok=True,
            mensaje="Usuario OPS registrado exitosamente. Ya puedes iniciar sesión.",
            datos={"id": str(res["ops_id"])},
        )

    except Exception as e:
        logger.exception("Error inesperado en registrar_ops")
        return AuthResult(False, f"Error al registrar usuario: {e}")


# ──────────────────────────────────────────────────────────────
# RECUPERACIÓN DE CONTRASEÑA — PASO 1: solicitar OTP
# ──────────────────────────────────────────────────────────────

def solicitar_recuperacion(
    tipo_doc_abrev: str,
    documento:      str,
    medio:          str,   # 'correo' | 'whatsapp'
) -> AuthResult:
    """
    Genera un token OTP de 6 dígitos y lo almacena en token_recuperacion.
    En producción debe enviarse por correo/WhatsApp; aquí se devuelve
    en datos['codigo_dev'] para desarrollo.

    Respuesta ambigua por seguridad: siempre retorna ok=True si
    los parámetros son válidos, independientemente de si el usuario existe.
    """
    if medio not in ("correo", "whatsapp"):
        return AuthResult(False, "El medio debe ser 'correo' o 'whatsapp'.")

    tipo_abrev = tipo_doc_abrev.strip().upper()
    documento  = documento.strip()
    codigo     = _generar_otp()

    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()

            entidad_id: int | None = None
            ops_id:     int | None = None
            destino:    str | None = None

            if tipo_abrev == "NIT":
                cur.execute(
                    "SELECT id, correo, celular FROM public.entidad "
                    "WHERE nit = %s AND activo = TRUE LIMIT 1",
                    (documento,),
                )
                row = cur.fetchone()
                if row:
                    entidad_id = row["id"]
                    destino    = row["correo"] if medio == "correo" else row["celular"]
            else:
                cur.execute(
                    """
                    SELECT u.id, u.correo, u.whatsapp
                    FROM   public.usuario_ops   u
                    JOIN   public.tipo_documento td ON td.id = u.tipo_documento_id
                    WHERE  td.abreviatura     = %s
                      AND  u.numero_documento = %s
                      AND  u.activo           = TRUE
                    LIMIT  1
                    """,
                    (tipo_abrev, documento),
                )
                row = cur.fetchone()
                if row:
                    ops_id  = row["id"]
                    destino = row["correo"] if medio == "correo" else row["whatsapp"]

            # Respuesta genérica si el usuario no existe (seguridad anti-enumeración)
            if entidad_id is None and ops_id is None:
                return AuthResult(
                    True,
                    "Si el usuario existe, recibirás un código de verificación.",
                )

            if not destino:
                campo = "correo electrónico" if medio == "correo" else "número de WhatsApp"
                return AuthResult(
                    False,
                    f"No hay {campo} registrado para este usuario.",
                )

            # Invalidar tokens anteriores no usados del mismo usuario
            cur.execute(
                """
                UPDATE public.token_recuperacion
                SET    usado = TRUE
                WHERE  usado = FALSE
                  AND  expira_en > NOW()
                  AND  ((entidad_id = %s AND %s IS NOT NULL)
                     OR (usuario_ops_id = %s AND %s IS NOT NULL))
                """,
                (entidad_id, entidad_id, ops_id, ops_id),
            )

            # Insertar nuevo token (expira en 15 minutos)
            cur.execute(
                """
                INSERT INTO public.token_recuperacion
                    (entidad_id, usuario_ops_id, codigo, medio, expira_en)
                VALUES (%s, %s, %s, %s, NOW() + INTERVAL '15 minutes')
                RETURNING id
                """,
                (entidad_id, ops_id, codigo, medio),
            )
            token_id = str(cur.fetchone()["id"])

        # TODO producción: enviar `codigo` a `destino` por `medio`
        logger.debug("[OTP DEV] → %s (%s): %s", destino, medio, codigo)
        print(f"[OTP DEV] → {destino} ({medio}): {codigo}")

        canal = "correo electrónico" if medio == "correo" else "WhatsApp"
        return AuthResult(
            ok=True,
            mensaje=f"Código enviado a tu {canal}. Expira en 15 minutos.",
            datos={
                "entidad_id": str(entidad_id) if entidad_id else None,
                "ops_id":     str(ops_id)     if ops_id     else None,
                "token_id":   token_id,
                "codigo_dev": codigo,   # ELIMINAR en producción
            },
        )

    except Exception as e:
        logger.exception("Error en solicitar_recuperacion")
        return AuthResult(False, f"Error al solicitar recuperación: {e}")


# ──────────────────────────────────────────────────────────────
# RECUPERACIÓN — PASO 2: verificar código OTP
# ──────────────────────────────────────────────────────────────

def verificar_codigo(
    entidad_id: str | None,
    ops_id:     str | None,
    codigo:     str,
) -> AuthResult:
    """
    Verifica el OTP en token_recuperacion.
    No lo marca como usado todavía (eso ocurre al cambiar la contraseña).
    """
    if not codigo:
        return AuthResult(False, "Ingresa el código de verificación.")
    if not entidad_id and not ops_id:
        return AuthResult(False, "Sesión de recuperación inválida.")

    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id AS token_id
                FROM   public.token_recuperacion
                WHERE  codigo    = %s
                  AND  usado     = FALSE
                  AND  expira_en > NOW()
                  AND (
                        (entidad_id     = %s AND %s IS NOT NULL)
                     OR (usuario_ops_id = %s AND %s IS NOT NULL)
                  )
                ORDER  BY creado_en DESC
                LIMIT  1
                """,
                (
                    codigo.strip(),
                    entidad_id, entidad_id,
                    ops_id,     ops_id,
                ),
            )
            row = cur.fetchone()

        if not row:
            return AuthResult(False, "Código incorrecto o expirado. Verifica e intenta de nuevo.")

        return AuthResult(
            ok=True,
            mensaje="Código verificado. Establece tu nueva contraseña.",
            datos={
                "entidad_id": entidad_id,
                "ops_id":     ops_id,
                "token_id":   str(row["token_id"]),
            },
        )

    except Exception as e:
        logger.exception("Error en verificar_codigo")
        return AuthResult(False, f"Error al verificar código: {e}")


# ──────────────────────────────────────────────────────────────
# RECUPERACIÓN — PASO 3: establecer nueva contraseña
# ──────────────────────────────────────────────────────────────

def cambiar_password_recuperacion(
    entidad_id: str | None,
    ops_id:     str | None,
    token_id:   str,
    nueva_pw:   str,
    confirmar:  str,
) -> AuthResult:
    """
    Cambia la contraseña con el token validado, lo marca como usado
    y cierra todas las sesiones activas.
    """
    if len(nueva_pw) < 8:
        return AuthResult(False, "La nueva contraseña debe tener al menos 8 caracteres.")
    if nueva_pw != confirmar:
        return AuthResult(False, "Las contraseñas no coinciden.")

    try:
        nuevo_hash = _hash_pw(nueva_pw)

        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()

            # Doble verificación del token
            cur.execute(
                "SELECT 1 FROM public.token_recuperacion "
                "WHERE id = %s AND usado = FALSE AND expira_en > NOW()",
                (token_id,),
            )
            if not cur.fetchone():
                return AuthResult(False, "Sesión de recuperación inválida o expirada.")

            # Cambiar contraseña vía RPC (también cierra sesiones)
            cur.execute(
                "SELECT public.rpc_cambiar_password(%s, %s, %s) AS resultado",
                (
                    int(entidad_id) if entidad_id else None,
                    int(ops_id)     if ops_id     else None,
                    nuevo_hash,
                ),
            )
            res = cur.fetchone()["resultado"]
            if isinstance(res, str):
                import json
                res = json.loads(res)

            if not res.get("ok"):
                return AuthResult(False, res.get("error", "Error al cambiar contraseña."))

            # Marcar token como usado
            cur.execute(
                "UPDATE public.token_recuperacion SET usado = TRUE WHERE id = %s",
                (token_id,),
            )

        return AuthResult(ok=True, mensaje="¡Contraseña actualizada! Ya puedes iniciar sesión.")

    except Exception as e:
        logger.exception("Error en cambiar_password_recuperacion")
        return AuthResult(False, f"Error al cambiar contraseña: {e}")


# ──────────────────────────────────────────────────────────────
# CAMBIO DE CONTRASEÑA (usuario autenticado)
# ──────────────────────────────────────────────────────────────

def cambiar_password_autenticado(
    rol:        str,   # 'admin' | 'ops'
    usuario_id: str,
    nueva_pw:   str,
    confirmar:  str,
) -> AuthResult:
    """
    Cambia la contraseña de un usuario con sesión activa.
    Delega en rpc_cambiar_password que también invalida las sesiones.
    """
    if len(nueva_pw) < 8:
        return AuthResult(False, "La nueva contraseña debe tener al menos 8 caracteres.")
    if nueva_pw != confirmar:
        return AuthResult(False, "Las contraseñas no coinciden.")

    entidad_id = int(usuario_id) if rol == "admin" else None
    ops_id     = int(usuario_id) if rol == "ops"   else None

    try:
        nuevo_hash = _hash_pw(nueva_pw)

        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT public.rpc_cambiar_password(%s, %s, %s) AS resultado",
                (entidad_id, ops_id, nuevo_hash),
            )
            res = cur.fetchone()["resultado"]
            if isinstance(res, str):
                import json
                res = json.loads(res)

        if not res.get("ok"):
            return AuthResult(False, res.get("error", "Error al cambiar contraseña."))

        return AuthResult(ok=True, mensaje=res.get("mensaje", "Contraseña actualizada."))

    except Exception as e:
        logger.exception("Error en cambiar_password_autenticado")
        return AuthResult(False, f"Error al cambiar contraseña: {e}")


# ──────────────────────────────────────────────────────────────
# CONSULTA AUXILIAR: resolver entidad_id por NIT
# ──────────────────────────────────────────────────────────────

def resolver_entidad_por_nit(nit: str) -> int | None:
    """
    Retorna el id de la entidad con ese NIT y activo=TRUE, o None si no existe.
    Usada en el registro OPS para asociar al usuario con su entidad.
    """
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM public.entidad WHERE nit = %s AND activo = TRUE LIMIT 1",
                (nit.strip(),),
            )
            row = cur.fetchone()
            return row["id"] if row else None
    except Exception as e:
        logger.error("Error al resolver entidad por NIT: %s", e)
        return None
