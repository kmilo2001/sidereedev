# -*- coding: utf-8 -*-
"""
gestion_eps_ops_backend.py
===========================
Gestion de EPS para Usuarios OPS — Seccion 5.4 (vista OPS).

Diferencias respecto a gestion_eps_backend.py (Admin):
  - SIN carga masiva (ni procesar_carga_masiva ni generar_plantilla_excel).
  - SIN listar_entidades_disponibles ni resolver_entidad_standalone
    (el OPS siempre tiene sesion activa; no trabaja en modo standalone).
  - ops_id es OBLIGATORIO en guardar_eps y cambiar_estado_eps:
    el registro queda vinculado al operador que lo creo/modifico.
  - eliminar_eps esta disponible pero solo si el OPS es el creador
    y no tiene dependencias (mismo control que el admin).

Reutilizacion:
  Este modulo importa directamente las funciones de gestion_eps_backend
  para no duplicar logica de BD. Solo sobreescribe / restringe lo necesario.

Tabla: public.eps  (misma que el admin)
  creado_por_ops integer FK usuario_ops — se llena siempre en OPS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ── Reutilizar todo lo que no cambia del modulo admin ─────────
from gestion_eps_backend import (
    _Cur,
    _v,
    Resultado,
    listar_eps,
    obtener_eps,
    cambiar_estado_eps,
    obtener_eps_activas,
    TIPOS_VALIDOS,
)


# ══════════════════════════════════════════════════════════════
# GUARDAR (OPS: ops_id obligatorio, registrado en creado_por_ops)
# ══════════════════════════════════════════════════════════════

def guardar_eps_ops(
    entidad_id: int,
    ops_id:     int,           # OBLIGATORIO para OPS
    datos:      dict,
    eps_id:     Optional[int] = None,
) -> Resultado:
    """
    Crea o actualiza una EPS desde el perfil OPS.

    Reglas especificas OPS:
      - ops_id es requerido (no puede ser None ni 0).
      - Al crear: creado_por_ops = ops_id.
      - Al actualizar: solo puede editar si el OPS fue quien la creo
        (creado_por_ops = ops_id).  Si fue creada por otro OPS o por
        el admin (creado_por_ops IS NULL) → error de permisos.
      - digitado_por se llena automaticamente con el ops_id en texto
        si no viene en datos (el frontend puede pasarlo con el nombre).
    """
    if not ops_id or str(ops_id).strip() in ("", "0"):
        return Resultado(False, "El ID del operador es obligatorio para esta accion.")

    oid = int(ops_id)

    nombre    = _v("nombre",       "Nombre",       src=datos)
    codigo    = _v("codigo",       "Codigo",       src=datos)
    tipo      = _v("tipo",         "Tipo",         src=datos) or "EPS"
    dpto      = _v("departamento", "Departamento", src=datos)
    mpio      = _v("municipio",    "Municipio",    src=datos)
    nit       = _v("nit",          "NIT",          src=datos)
    dv        = _v("dv",           "DV",           src=datos)
    correo    = _v("correo",       "Correo",       src=datos)
    tel       = _v("telefono",     "Telefono",     src=datos)
    direccion = _v("direccion",    "Direccion",    src=datos)
    digitado  = _v("digitado_por", "Digitado_por", src=datos)

    if not nombre:
        return Resultado(False, "El nombre de la EPS es obligatorio.")
    if len(nombre) > 200:
        return Resultado(False, "El nombre no puede superar 200 caracteres.")

    try:
        with _Cur() as cur:

            if eps_id:
                # ── ACTUALIZAR ────────────────────────────────
                # Verificar que el OPS es quien la creo
                cur.execute(
                    "SELECT id, creado_por_ops FROM public.eps "
                    "WHERE id=%s AND entidad_id=%s",
                    (eps_id, entidad_id),
                )
                row = cur.fetchone()
                if not row:
                    return Resultado(False, "EPS no encontrada.")
                if row["creado_por_ops"] != oid:
                    return Resultado(
                        False,
                        "No tienes permiso para editar esta EPS. "
                        "Solo puede editarla el operador que la registro "
                        "o el administrador."
                    )

                cur.execute(
                    """
                    UPDATE public.eps SET
                        codigo         = %s,
                        nombre         = %s,
                        tipo           = %s,
                        departamento   = %s,
                        municipio      = %s,
                        nit            = %s,
                        dv             = %s,
                        correo         = %s,
                        telefono       = %s,
                        direccion      = %s,
                        digitado_por   = COALESCE(%s, digitado_por),
                        actualizado_en = now()
                    WHERE id = %s AND entidad_id = %s
                    """,
                    (codigo, nombre, tipo, dpto, mpio, nit, dv,
                     correo, tel, direccion, digitado, eps_id, entidad_id),
                )
                return Resultado(
                    True,
                    f"EPS '{nombre}' actualizada correctamente.",
                    {"eps_id": eps_id, "accion": "actualizada"},
                )

            else:
                # ── CREAR ─────────────────────────────────────
                cur.execute(
                    "SELECT id FROM public.eps "
                    "WHERE entidad_id=%s AND LOWER(TRIM(nombre))=LOWER(%s)",
                    (entidad_id, nombre),
                )
                if cur.fetchone():
                    return Resultado(
                        False,
                        f"Ya existe una EPS con el nombre '{nombre}'."
                    )

                cur.execute(
                    """
                    INSERT INTO public.eps
                        (entidad_id, codigo, nombre, tipo, departamento, municipio,
                         nit, dv, correo, telefono, direccion, digitado_por,
                         activo, creado_por_ops)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s)
                    RETURNING id
                    """,
                    (entidad_id, codigo, nombre, tipo, dpto, mpio,
                     nit, dv, correo, tel, direccion, digitado, oid),
                )
                nuevo_id = cur.fetchone()["id"]
                return Resultado(
                    True,
                    f"EPS '{nombre}' registrada correctamente.",
                    {"eps_id": nuevo_id, "accion": "creada"},
                )

    except Exception as e:
        msg = str(e).split("\n")[0]
        return Resultado(False, f"Error al guardar: {msg}")


# ══════════════════════════════════════════════════════════════
# ELIMINAR (OPS: solo si es el creador y sin dependencias)
# ══════════════════════════════════════════════════════════════

def eliminar_eps_ops(
    entidad_id: int,
    ops_id:     int,
    eps_id:     int,
) -> Resultado:
    """
    Elimina una EPS solo si:
      1. El OPS es quien la creo (creado_por_ops = ops_id).
      2. No tiene pacientes, eventos ni contratos vinculados.
    """
    if not ops_id or str(ops_id).strip() in ("", "0"):
        return Resultado(False, "El ID del operador es obligatorio.")

    oid = int(ops_id)

    try:
        with _Cur() as cur:
            cur.execute(
                "SELECT nombre, creado_por_ops FROM public.eps "
                "WHERE id=%s AND entidad_id=%s",
                (eps_id, entidad_id),
            )
            row = cur.fetchone()
            if not row:
                return Resultado(False, "EPS no encontrada.")
            if row["creado_por_ops"] != oid:
                return Resultado(
                    False,
                    "Solo puedes eliminar EPS que hayas registrado tu mismo. "
                    "Contacta al administrador para eliminar otras EPS."
                )

            nombre = row["nombre"]

            # Verificar dependencias
            deps = []
            for tabla, col, lbl in [
                ("public.paciente",    "eps_id", "paciente(s)"),
                ("public.evento",      "eps_id", "evento(s)"),
                ("public.contrato_eps","eps_id", "contrato(s)"),
            ]:
                cur.execute(
                    f"SELECT COUNT(*) AS n FROM {tabla} WHERE {col}=%s",
                    (eps_id,),
                )
                n = cur.fetchone()["n"]
                if n:
                    deps.append(f"{n} {lbl}")

            if deps:
                return Resultado(
                    False,
                    f"No se puede eliminar '{nombre}': "
                    f"referenciada por {', '.join(deps)}. "
                    "Usa 'Desactivar' en su lugar."
                )

            cur.execute(
                "DELETE FROM public.eps WHERE id=%s AND entidad_id=%s",
                (eps_id, entidad_id),
            )

        return Resultado(True, f"EPS '{nombre}' eliminada correctamente.")

    except Exception as e:
        msg = str(e).split("\n")[0]
        return Resultado(False, f"Error al eliminar: {msg}")


# ══════════════════════════════════════════════════════════════
# CAMBIAR ESTADO (OPS: solo si es el creador)
# ══════════════════════════════════════════════════════════════

def cambiar_estado_eps_ops(
    entidad_id: int,
    ops_id:     int,
    eps_id:     int,
    activo:     bool,
) -> Resultado:
    """
    Activa o desactiva una EPS.
    El OPS solo puede cambiar el estado de EPS que el registro.
    El admin puede cambiar cualquier EPS via cambiar_estado_eps().
    """
    if not ops_id or str(ops_id).strip() in ("", "0"):
        return Resultado(False, "El ID del operador es obligatorio.")

    oid    = int(ops_id)
    accion = "activar" if activo else "desactivar"

    try:
        with _Cur() as cur:
            cur.execute(
                "SELECT nombre, creado_por_ops FROM public.eps "
                "WHERE id=%s AND entidad_id=%s",
                (eps_id, entidad_id),
            )
            row = cur.fetchone()
            if not row:
                return Resultado(False, "EPS no encontrada.")
            if row["creado_por_ops"] != oid:
                return Resultado(
                    False,
                    f"No tienes permiso para {accion} esta EPS. "
                    "Solo puede hacerlo el operador que la registro "
                    "o el administrador."
                )

            nombre = row["nombre"]

            # Advertencia si hay pacientes (solo al desactivar)
            advertencia = ""
            if not activo:
                cur.execute(
                    "SELECT COUNT(*) AS n FROM public.paciente "
                    "WHERE eps_id=%s AND entidad_id=%s AND activo=TRUE",
                    (eps_id, entidad_id),
                )
                n = cur.fetchone()["n"]
                if n:
                    advertencia = (
                        f" Atencion: {n} paciente(s) tienen esta EPS asignada."
                    )

            cur.execute(
                "UPDATE public.eps SET activo=%s, actualizado_en=now() "
                "WHERE id=%s AND entidad_id=%s",
                (activo, eps_id, entidad_id),
            )

        lbl = "activada" if activo else "desactivada"
        return Resultado(True, f"'{nombre}' {lbl} correctamente.{advertencia}")

    except Exception as e:
        msg = str(e).split("\n")[0]
        return Resultado(False, f"Error al {accion}: {msg}")


# ══════════════════════════════════════════════════════════════
# RE-EXPORTAR helpers que el UI necesita directamente
# ══════════════════════════════════════════════════════════════
# El UI de OPS importa solo de este modulo, nunca de gestion_eps_backend.
# Aqui reexportamos lo que no cambia para que el import sea limpio.

__all__ = [
    "Resultado",
    "listar_eps",
    "obtener_eps",
    "guardar_eps_ops",
    "cambiar_estado_eps_ops",
    "eliminar_eps_ops",
    "obtener_eps_activas",
    "TIPOS_VALIDOS",
]
