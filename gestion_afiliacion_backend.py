# -*- coding: utf-8 -*-
"""
gestion_afiliacion_backend.py
==============================
Gestion de Tipos de Afiliacion — Seccion 5.2.
Disponible para Admin y OPS.

Tabla real: public.tipo_afiliacion
  id        smallint NOT NULL GENERATED ALWAYS AS IDENTITY
  nombre    character varying(80) NOT NULL  UNIQUE
  codigo    character varying(5)            -- codigo RIPS (opcional)
  activo    boolean  DEFAULT true NOT NULL
  creado_en timestamptz DEFAULT now() NOT NULL

IMPORTANTE — la tabla NO tiene columna 'creado_por_entidad'.
Los cinco registros semilla (01-05) son catalogos de Ley 100/1993
y se identifican por su codigo oficial ('01'-'05'), NO por un campo
de entidad. La logica de "solo lectura para oficiales" se basa en
ese rango de codigos.

Modo standalone (prueba modulo a modulo):
  - Cuando se ejecuta sin el sistema completo de sesiones, entidad_id
    se ignora en las consultas (la tabla es global al sistema).
  - Cuando esten todos los modulos unidos, entidad_id se pasa desde
    la sesion del usuario autenticado y se usa para auditorias futuras.

Normativa: Ley 100/1993, Res. 3374/2000 (RIPS).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ── Importacion de conexion compatible con modo standalone ───
# Si existe conexion.py en el proyecto lo usa directamente.
# Fallback: intenta db_conexion (estructura previa del proyecto).
try:
    from conexion import Conexion
    _MODO_CONEXION = "conexion"
except ImportError:
    try:
        from db_conexion import obtener_cursor as _obtener_cursor
        _MODO_CONEXION = "db_conexion"
    except ImportError:
        _MODO_CONEXION = None


# ── Codigos RIPS de los catalogos oficiales de Ley 100/1993 ──
# Estos registros NO pueden modificarse ni desactivarse desde la UI.
_CODIGOS_OFICIALES = {"01", "02", "03", "04", "05"}


# ══════════════════════════════════════════════════════════════
# RESULTADO
# ══════════════════════════════════════════════════════════════

@dataclass
class Resultado:
    ok:      bool
    mensaje: str
    datos:   object = field(default=None)


# ══════════════════════════════════════════════════════════════
# HELPER INTERNO DE CONEXION
# ══════════════════════════════════════════════════════════════

class _CursorCtx:
    """
    Contexto de cursor unificado.
    Abstrae si usamos conexion.py (Conexion) o db_conexion.py (obtener_cursor).
    Uso:
        with _CursorCtx() as cur:
            cur.execute(...)
    """
    def __init__(self):
        self._conn = None
        self._cur  = None

    def __enter__(self):
        if _MODO_CONEXION == "conexion":
            self._conn = Conexion(dict_cursor=True)
            self._cur  = self._conn.__enter__().cursor()
        elif _MODO_CONEXION == "db_conexion":
            self._cur = _obtener_cursor().__enter__()
        else:
            raise RuntimeError(
                "No se encontro modulo de conexion. "
                "Asegurate de tener conexion.py o db_conexion.py en el proyecto."
            )
        return self._cur

    def __exit__(self, exc_type, exc_val, exc_tb):
        if _MODO_CONEXION == "conexion" and self._conn:
            self._conn.__exit__(exc_type, exc_val, exc_tb)
        elif _MODO_CONEXION == "db_conexion" and self._cur:
            # db_conexion maneja el commit/rollback internamente
            pass
        return False


def _es_oficial(codigo: Optional[str]) -> bool:
    """Retorna True si el codigo corresponde a un catalogo oficial de Ley 100."""
    return bool(codigo and str(codigo).strip() in _CODIGOS_OFICIALES)


# ══════════════════════════════════════════════════════════════
# LISTADO
# ══════════════════════════════════════════════════════════════

def listar_afiliaciones(
    entidad_id: int,           # reservado para cuando haya multientidad
    filtro:     str  = "",
    solo_activos: bool = False,
) -> list[dict]:
    """
    Retorna todos los tipos de afiliacion del sistema.

    La tabla tipo_afiliacion es global (no tiene campo entidad).
    entidad_id se acepta para compatibilidad con la firma que usa
    GestionWindow, pero no filtra por entidad en esta version.

    Args:
        entidad_id:   ID de la IPS autenticada (reservado).
        filtro:       Texto libre para buscar por nombre o codigo.
        solo_activos: Si True, devuelve solo los registros activos.
    """
    try:
        with _CursorCtx() as cur:
            condiciones = ["1=1"]
            params: list = []

            if solo_activos:
                condiciones.append("activo = TRUE")

            if filtro.strip():
                condiciones.append(
                    "(nombre ILIKE %s OR COALESCE(codigo, '') ILIKE %s)"
                )
                like = f"%{filtro.strip()}%"
                params += [like, like]

            where = " AND ".join(condiciones)

            cur.execute(
                f"""
                SELECT
                    id,
                    nombre,
                    COALESCE(codigo, '') AS codigo,
                    activo,
                    to_char(
                        creado_en AT TIME ZONE 'America/Bogota',
                        'DD/MM/YYYY'
                    ) AS fecha_creacion
                FROM  public.tipo_afiliacion
                WHERE {where}
                ORDER BY
                    CASE
                        WHEN codigo IN ('01','02','03','04','05') THEN 0
                        ELSE 1
                    END,
                    nombre
                """,
                params or None,
            )
            filas = cur.fetchall()

        resultado = []
        for r in filas:
            d = dict(r)
            d["es_catalogo_oficial"] = _es_oficial(d.get("codigo"))
            resultado.append(d)
        return resultado

    except Exception as e:
        print(f"[ERROR] listar_afiliaciones: {e}")
        return []


def obtener_afiliacion(afil_id: int) -> Optional[dict]:
    """
    Retorna el detalle de un tipo de afiliacion por ID.
    Retorna None si no existe.
    """
    try:
        with _CursorCtx() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    nombre,
                    COALESCE(codigo, '') AS codigo,
                    activo,
                    to_char(
                        creado_en AT TIME ZONE 'America/Bogota',
                        'DD/MM/YYYY HH24:MI'
                    ) AS fecha_creacion
                FROM  public.tipo_afiliacion
                WHERE id = %s
                """,
                (afil_id,),
            )
            row = cur.fetchone()

        if not row:
            return None
        d = dict(row)
        d["es_catalogo_oficial"] = _es_oficial(d.get("codigo"))
        return d

    except Exception as e:
        print(f"[ERROR] obtener_afiliacion: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# CREAR
# ══════════════════════════════════════════════════════════════

def crear_afiliacion(
    entidad_id: int,
    nombre:     str,
    codigo:     str = "",
) -> Resultado:
    """
    Crea un nuevo tipo de afiliacion.

    Validaciones:
      - nombre obligatorio, maximo 80 caracteres, debe ser unico.
      - codigo opcional, maximo 5 caracteres.
      - No se puede usar un codigo de los oficiales (01-05).
    """
    nombre = nombre.strip()
    codigo = codigo.strip() or None

    if not nombre:
        return Resultado(False, "El nombre es obligatorio.")
    if len(nombre) > 80:
        return Resultado(False, "El nombre no puede superar 80 caracteres.")
    if codigo and len(codigo) > 5:
        return Resultado(False, "El codigo RIPS no puede superar 5 caracteres.")
    if codigo and codigo in _CODIGOS_OFICIALES:
        return Resultado(
            False,
            f"El codigo '{codigo}' esta reservado para catalogos oficiales de Ley 100/1993."
        )

    try:
        with _CursorCtx() as cur:
            # Verificar nombre duplicado
            cur.execute(
                "SELECT 1 FROM public.tipo_afiliacion "
                "WHERE LOWER(TRIM(nombre)) = LOWER(%s)",
                (nombre,),
            )
            if cur.fetchone():
                return Resultado(
                    False,
                    f"Ya existe un tipo de afiliacion con el nombre '{nombre}'."
                )

            # Verificar codigo duplicado
            if codigo:
                cur.execute(
                    "SELECT 1 FROM public.tipo_afiliacion WHERE codigo = %s",
                    (codigo,),
                )
                if cur.fetchone():
                    return Resultado(
                        False,
                        f"El codigo '{codigo}' ya esta en uso por otro tipo de afiliacion."
                    )

            # Insertar — la tabla usa GENERATED ALWAYS AS IDENTITY
            cur.execute(
                """
                INSERT INTO public.tipo_afiliacion (nombre, codigo, activo)
                VALUES (%s, %s, TRUE)
                RETURNING id, nombre
                """,
                (nombre, codigo),
            )
            row = cur.fetchone()

        return Resultado(
            True,
            f"Tipo de afiliacion '{nombre}' creado correctamente.",
            {"id": row["id"], "nombre": row["nombre"]},
        )

    except Exception as e:
        msg = str(e).split("\n")[0]
        return Resultado(False, f"Error al crear: {msg}")


# ══════════════════════════════════════════════════════════════
# ACTUALIZAR
# ══════════════════════════════════════════════════════════════

def actualizar_afiliacion(
    entidad_id: int,
    afil_id:    int,
    nombre:     str,
    codigo:     str = "",
) -> Resultado:
    """
    Actualiza nombre y/o codigo de un tipo de afiliacion.

    Restriccion: no se pueden editar los catalogos oficiales
    (identificados por codigo '01'-'05').
    """
    nombre = nombre.strip()
    codigo = codigo.strip() or None

    if not nombre:
        return Resultado(False, "El nombre es obligatorio.")
    if len(nombre) > 80:
        return Resultado(False, "El nombre no puede superar 80 caracteres.")
    if codigo and len(codigo) > 5:
        return Resultado(False, "El codigo RIPS no puede superar 5 caracteres.")
    if codigo and codigo in _CODIGOS_OFICIALES:
        return Resultado(
            False,
            f"El codigo '{codigo}' esta reservado para catalogos oficiales."
        )

    try:
        with _CursorCtx() as cur:
            # Verificar que existe y no es catalogo oficial
            cur.execute(
                "SELECT codigo FROM public.tipo_afiliacion WHERE id = %s",
                (afil_id,),
            )
            row = cur.fetchone()
            if not row:
                return Resultado(False, "Tipo de afiliacion no encontrado.")
            if _es_oficial(row["codigo"]):
                return Resultado(
                    False,
                    "Los catalogos oficiales de Ley 100/1993 no pueden "
                    "modificarse desde la aplicacion."
                )

            # Verificar nombre duplicado (excluyendo el registro actual)
            cur.execute(
                "SELECT 1 FROM public.tipo_afiliacion "
                "WHERE LOWER(TRIM(nombre)) = LOWER(%s) AND id != %s",
                (nombre, afil_id),
            )
            if cur.fetchone():
                return Resultado(
                    False,
                    f"Ya existe otro tipo de afiliacion con el nombre '{nombre}'."
                )

            # Verificar codigo duplicado (excluyendo el registro actual)
            if codigo:
                cur.execute(
                    "SELECT 1 FROM public.tipo_afiliacion "
                    "WHERE codigo = %s AND id != %s",
                    (codigo, afil_id),
                )
                if cur.fetchone():
                    return Resultado(
                        False,
                        f"El codigo '{codigo}' ya esta en uso por otro tipo."
                    )

            # Actualizar
            cur.execute(
                "UPDATE public.tipo_afiliacion "
                "SET nombre = %s, codigo = %s "
                "WHERE id = %s",
                (nombre, codigo, afil_id),
            )

        return Resultado(True, "Tipo de afiliacion actualizado correctamente.")

    except Exception as e:
        msg = str(e).split("\n")[0]
        return Resultado(False, f"Error al actualizar: {msg}")


# ══════════════════════════════════════════════════════════════
# CAMBIAR ESTADO
# ══════════════════════════════════════════════════════════════

def cambiar_estado_afiliacion(
    entidad_id: int,
    afil_id:    int,
    activo:     bool,
) -> Resultado:
    """
    Activa o desactiva un tipo de afiliacion (soft-disable).
    No se pueden desactivar los catalogos oficiales de Ley 100.
    """
    accion = "activar" if activo else "desactivar"

    try:
        with _CursorCtx() as cur:
            cur.execute(
                "SELECT nombre, codigo FROM public.tipo_afiliacion WHERE id = %s",
                (afil_id,),
            )
            row = cur.fetchone()
            if not row:
                return Resultado(False, "Tipo de afiliacion no encontrado.")
            if _es_oficial(row["codigo"]):
                return Resultado(
                    False,
                    f"Los catalogos oficiales de Ley 100/1993 no pueden "
                    f"{accion}se desde la aplicacion."
                )

            nombre_tipo = row["nombre"]

            # Advertencia si hay pacientes vinculados (solo al desactivar)
            advertencia = ""
            if not activo:
                cur.execute(
                    "SELECT COUNT(*) AS total FROM public.paciente "
                    "WHERE tipo_afiliacion_id = %s AND activo = TRUE",
                    (afil_id,),
                )
                n_pac = cur.fetchone()["total"]
                if n_pac > 0:
                    advertencia = (
                        f" Nota: {n_pac} paciente(s) tienen este tipo "
                        "como preferido; los registros existentes no se veran afectados."
                    )

            cur.execute(
                "UPDATE public.tipo_afiliacion SET activo = %s WHERE id = %s",
                (activo, afil_id),
            )

        estado_lbl = "activado" if activo else "desactivado"
        return Resultado(
            True,
            f"'{nombre_tipo}' {estado_lbl} correctamente.{advertencia}",
        )

    except Exception as e:
        msg = str(e).split("\n")[0]
        return Resultado(False, f"Error al {accion}: {msg}")


# ══════════════════════════════════════════════════════════════
# ELIMINAR (hard delete — solo si no tiene dependencias)
# ══════════════════════════════════════════════════════════════

def eliminar_afiliacion(
    entidad_id: int,
    afil_id:    int,
) -> Resultado:
    """
    Elimina fisicamente un tipo de afiliacion personalizado.

    Reglas:
      - Los catalogos oficiales (codigo 01-05) NUNCA se pueden eliminar.
      - Si hay pacientes o eventos referenciando este tipo, se bloquea
        la eliminacion y se informa cuantos registros estan vinculados.
        En ese caso usar cambiar_estado_afiliacion(activo=False) en su lugar.
    """
    try:
        with _CursorCtx() as cur:
            # Verificar existencia y que no sea oficial
            cur.execute(
                "SELECT nombre, codigo FROM public.tipo_afiliacion WHERE id = %s",
                (afil_id,),
            )
            row = cur.fetchone()
            if not row:
                return Resultado(False, "Tipo de afiliacion no encontrado.")
            if _es_oficial(row["codigo"]):
                return Resultado(
                    False,
                    "Los catalogos oficiales de Ley 100/1993 no pueden eliminarse."
                )

            nombre_tipo = row["nombre"]

            # Verificar pacientes vinculados
            cur.execute(
                "SELECT COUNT(*) AS total FROM public.paciente "
                "WHERE tipo_afiliacion_id = %s",
                (afil_id,),
            )
            n_pac = cur.fetchone()["total"]

            # Verificar eventos vinculados
            cur.execute(
                "SELECT COUNT(*) AS total FROM public.evento "
                "WHERE tipo_afiliacion_id = %s",
                (afil_id,),
            )
            n_ev = cur.fetchone()["total"]

            if n_pac > 0 or n_ev > 0:
                partes = []
                if n_pac > 0:
                    partes.append(f"{n_pac} paciente(s)")
                if n_ev > 0:
                    partes.append(f"{n_ev} evento(s)")
                return Resultado(
                    False,
                    f"No se puede eliminar '{nombre_tipo}': "
                    f"esta referenciado por {' y '.join(partes)}. "
                    "Usa 'Desactivar' en su lugar."
                )

            # Eliminar
            cur.execute(
                "DELETE FROM public.tipo_afiliacion WHERE id = %s",
                (afil_id,),
            )

        return Resultado(
            True,
            f"Tipo de afiliacion '{nombre_tipo}' eliminado correctamente.",
        )

    except Exception as e:
        msg = str(e).split("\n")[0]
        return Resultado(False, f"Error al eliminar: {msg}")


# ══════════════════════════════════════════════════════════════
# HELPERS PARA OTROS MODULOS
# ══════════════════════════════════════════════════════════════

def obtener_tipos_afiliacion_activos(entidad_id: int = 1) -> list[dict]:
    """
    Retorna lista simplificada [{id, nombre, codigo}] de tipos activos.
    Usado por formularios de pacientes y eventos para poblar selectores.
    """
    return [
        {
            "id":     r["id"],
            "nombre": r["nombre"],
            "codigo": r.get("codigo", ""),
        }
        for r in listar_afiliaciones(entidad_id, solo_activos=True)
    ]


def nombre_afiliacion(afil_id: int) -> str:
    """
    Retorna el nombre de un tipo de afiliacion por ID.
    Retorna cadena vacia si no existe.
    """
    row = obtener_afiliacion(afil_id)
    return row["nombre"] if row else ""