# -*- coding: utf-8 -*-
# =============================================================================
# pacientes_backend.py
# Modulo de Gestion de Pacientes -- Sistema SIGES
#
# ACCESO:
#   PERMITIDO  -> rol='admin'  (entidad administradora)
#   PERMITIDO  -> rol='ops' es_maestro=True  (usuario Maestro)
#   PERMITIDO  -> rol='ops' es_maestro=False  (OPS regular)
#   Todos los usuarios autenticados tienen acceso completo al modulo.
#   La carga masiva esta disponible para admin y Maestro.
#   El OPS puede crear, editar y activar/desactivar pacientes de su entidad.
#
# EJECUTOR (dict):
#   { 'rol': 'admin'|'ops', 'ops_id': int|None,
#     'entidad_id': int, 'es_maestro': bool, 'nombre': str }
#   Construir con ops_backend.construir_ejecutor() tras el login.
#
# COMPATIBILIDAD maestro_backend:
#   maestro_backend pasa un ejecutor valido directamente a estas funciones.
#
# SCHEMA REAL (ver 1_gestion_eventos_salud__1_.sql):
#   paciente(id, entidad_id, tipo_documento_id smallint NOT NULL,
#            numero_documento varchar(50) NOT NULL,
#            primer_apellido  varchar(100) NOT NULL,
#            segundo_apellido varchar(100) NOT NULL,   <- NOT NULL, usar '' si falta
#            primer_nombre    varchar(100) NOT NULL,
#            segundo_nombre   varchar(100),
#            fecha_nacimiento date, sexo char(1) CHECK(M/F/O),
#            direccion text, municipio_residencia varchar(100),
#            zona_residencia varchar(20), telefono varchar(30),
#            eps_id integer, tipo_afiliacion_id smallint,
#            activo boolean DEFAULT true, creado_en timestamptz,
#            creado_por_ops integer, actualizado_en timestamptz)
#
#   tipo_afiliacion(id smallint, nombre varchar(80), codigo varchar(5), activo bool, creado_en)
#     -> SIN creado_por_entidad (la tabla es global)
#
#   carga_masiva_lote.tipo CHECK IN ('pacientes', 'eps')
#
# CARGA MASIVA:
#   EPS se resuelve por Codigo_EPS -> eps.codigo (no por nombre)
#   Tipo afiliacion se resuelve por nombre (catalogo global)
#   Upsert por (entidad_id, tipo_documento_id, numero_documento)
# =============================================================================

from __future__ import annotations

import csv
import datetime
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from conexion import Conexion

logger = logging.getLogger("siges.pacientes")

MAX_FILAS_LOTE = 20_000


# ══════════════════════════════════════════════════════════════
# RESULTADO
# ══════════════════════════════════════════════════════════════

@dataclass
class Resultado:
    ok:      bool
    mensaje: str
    datos:   object = field(default=None)


# ══════════════════════════════════════════════════════════════
# CONTROL DE ACCESO
# ══════════════════════════════════════════════════════════════

def puede_acceder(ejecutor: dict) -> bool:
    """
    True si el ejecutor tiene acceso al modulo de pacientes.
    PERMITIDO: admin (entidad), Maestro, y cualquier OPS regular.
    Todos los usuarios autenticados pueden registrar y gestionar pacientes.
    """
    rol = ejecutor.get("rol", "")
    return rol in ("admin", "ops")  # cualquier usuario autenticado


def _check(ejecutor: dict) -> Optional[Resultado]:
    if not puede_acceder(ejecutor):
        return Resultado(
            False,
            "Acceso denegado. Inicia sesion para gestionar pacientes."
        )
    return None


# ══════════════════════════════════════════════════════════════
# HELPERS INTERNOS
# ══════════════════════════════════════════════════════════════

def _ops_none(v) -> Optional[int]:
    if v is None or v == 0 or str(v).strip() == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _sexo(raw) -> Optional[str]:
    s = str(raw or "").strip().upper()
    if s in ("M", "MASCULINO", "HOMBRE", "MALE", "H"):
        return "M"
    if s in ("F", "FEMENINO", "MUJER", "FEMALE"):
        return "F"
    if s in ("O", "OTRO", "OTHER"):
        return "O"
    return None


def _zona(raw) -> Optional[str]:
    z = str(raw or "").strip().upper()
    if z in ("URBANA", "U", "URBAN", "1"):
        return "Urbana"
    if z in ("RURAL", "R", "2"):
        return "Rural"
    return None


def _fecha(raw) -> Optional[datetime.date]:
    s = str(raw or "").strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ══════════════════════════════════════════════════════════════
# CATALOGOS
# ══════════════════════════════════════════════════════════════

def obtener_tipos_documento() -> list[dict]:
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, abreviatura, nombre "
            "FROM public.tipo_documento WHERE activo = TRUE ORDER BY nombre"
        )
        return [dict(r) for r in cur.fetchall()]


def obtener_eps_activas(entidad_id: int) -> list[dict]:
    """
    EPS activas para el selector del formulario.
    Retorna: eps_id, codigo, nombre, tiene_contrato.
    Primero las que tienen contrato vigente.
    """
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT  e.id  AS eps_id,
                    COALESCE(e.codigo, '') AS codigo,
                    COALESCE(e.nombre, '') AS nombre,
                    public.eps_tiene_contrato(e.entidad_id, e.id, CURRENT_DATE) AS tiene_contrato
            FROM    public.eps e
            WHERE   e.entidad_id = %s AND e.activo = TRUE
            ORDER BY
                public.eps_tiene_contrato(e.entidad_id, e.id, CURRENT_DATE) DESC,
                e.nombre
            """,
            (entidad_id,)
        )
        return [dict(r) for r in cur.fetchall()]


def obtener_tipos_afiliacion() -> list[dict]:
    """
    Tipos de afiliacion activos (catalogo global).
    La tabla tipo_afiliacion NO tiene columna entidad_id.
    Retorna: id, nombre, codigo. Primero los oficiales (01-05).
    """
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT  id,
                    nombre,
                    COALESCE(codigo, '') AS codigo
            FROM    public.tipo_afiliacion
            WHERE   activo = TRUE
            ORDER BY
                CASE WHEN codigo IN ('01','02','03','04','05') THEN 0 ELSE 1 END,
                nombre
            """
        )
        return [dict(r) for r in cur.fetchall()]


# ══════════════════════════════════════════════════════════════
# LISTAR / BUSCAR
# ══════════════════════════════════════════════════════════════

def listar_pacientes(
    ejecutor:     dict,
    entidad_id:   int,
    filtro:       str  = "",
    solo_activos: bool = False,
    limite:       int  = 500,
    offset:       int  = 0,
) -> list[dict]:
    """
    Lista pacientes con busqueda en tiempo real (debounce en la UI).
    Busca en numero_documento, apellidos y nombres.

    Retorna por fila:
        paciente_id, entidad_id, tipo_doc, tipo_doc_nombre,
        numero_documento, primer_apellido, segundo_apellido,
        primer_nombre, segundo_nombre, nombre_completo,
        fecha_nacimiento, sexo, municipio_residencia, zona_residencia,
        direccion, telefono, eps_id, eps_nombre, eps_codigo,
        tipo_afiliacion_id, tipo_afiliacion, activo,
        creado_en, actualizado_en, total_count
    """
    err = _check(ejecutor)
    if err:
        raise PermissionError(err.mensaje)

    like = f"%{filtro.strip()}%" if filtro.strip() else "%"
    cond_activo = "AND p.activo = TRUE" if solo_activos else ""

    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT
                p.id                                                    AS paciente_id,
                p.entidad_id,
                td.abreviatura                                          AS tipo_doc,
                td.nombre                                               AS tipo_doc_nombre,
                p.numero_documento,
                p.primer_apellido,
                COALESCE(p.segundo_apellido, '')                        AS segundo_apellido,
                p.primer_nombre,
                COALESCE(p.segundo_nombre, '')                          AS segundo_nombre,
                CONCAT_WS(' ',
                    p.primer_nombre,
                    NULLIF(p.segundo_nombre, ''),
                    p.primer_apellido,
                    NULLIF(p.segundo_apellido, '')
                )                                                       AS nombre_completo,
                p.fecha_nacimiento,
                p.sexo,
                COALESCE(p.municipio_residencia, '')                    AS municipio_residencia,
                COALESCE(p.zona_residencia, '')                         AS zona_residencia,
                COALESCE(p.direccion, '')                               AS direccion,
                COALESCE(p.telefono,  '')                               AS telefono,
                p.eps_id,
                COALESCE(ep.nombre,   '')                               AS eps_nombre,
                COALESCE(ep.codigo,   '')                               AS eps_codigo,
                p.tipo_afiliacion_id,
                COALESCE(ta.nombre,   '')                               AS tipo_afiliacion,
                p.activo,
                p.creado_en,
                p.actualizado_en,
                COUNT(*) OVER()::int                                    AS total_count
            FROM   public.paciente         p
            JOIN   public.tipo_documento   td ON td.id = p.tipo_documento_id
            LEFT   JOIN public.eps          ep ON ep.id = p.eps_id
            LEFT   JOIN public.tipo_afiliacion ta ON ta.id = p.tipo_afiliacion_id
            WHERE  p.entidad_id = %s
              AND  (
                     p.numero_documento ILIKE %s
                  OR p.primer_apellido  ILIKE %s
                  OR p.segundo_apellido ILIKE %s
                  OR p.primer_nombre    ILIKE %s
                  OR CONCAT_WS(' ',
                        p.primer_nombre, p.segundo_nombre,
                        p.primer_apellido, p.segundo_apellido) ILIKE %s
              )
              {cond_activo}
            ORDER  BY p.primer_apellido, p.primer_nombre
            LIMIT  %s OFFSET %s
            """,
            (entidad_id, like, like, like, like, like, limite, offset)
        )
        return [dict(r) for r in cur.fetchall()]


def obtener_paciente(
    ejecutor:    dict,
    entidad_id:  int,
    paciente_id: int,
) -> Optional[dict]:
    """Detalle completo de un paciente, incluye nombre del OPS creador."""
    err = _check(ejecutor)
    if err:
        raise PermissionError(err.mensaje)

    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                p.id                                                    AS paciente_id,
                p.entidad_id,
                td.id                                                   AS tipo_doc_id,
                td.abreviatura                                          AS tipo_doc,
                td.nombre                                               AS tipo_doc_nombre,
                p.numero_documento,
                p.primer_apellido,
                COALESCE(p.segundo_apellido, '')                        AS segundo_apellido,
                p.primer_nombre,
                COALESCE(p.segundo_nombre, '')                          AS segundo_nombre,
                p.fecha_nacimiento,
                p.sexo,
                COALESCE(p.municipio_residencia, '')                    AS municipio_residencia,
                COALESCE(p.zona_residencia, '')                         AS zona_residencia,
                COALESCE(p.direccion, '')                               AS direccion,
                COALESCE(p.telefono,  '')                               AS telefono,
                p.eps_id,
                COALESCE(ep.nombre,   '')                               AS eps_nombre,
                COALESCE(ep.codigo,   '')                               AS eps_codigo,
                p.tipo_afiliacion_id,
                COALESCE(ta.nombre,   '')                               AS tipo_afiliacion,
                p.activo,
                p.creado_en,
                p.actualizado_en,
                u.nombre_completo                                       AS creado_por_ops_nombre
            FROM   public.paciente          p
            JOIN   public.tipo_documento    td ON td.id  = p.tipo_documento_id
            LEFT   JOIN public.eps           ep ON ep.id = p.eps_id
            LEFT   JOIN public.tipo_afiliacion ta ON ta.id = p.tipo_afiliacion_id
            LEFT   JOIN public.usuario_ops   u  ON u.id  = p.creado_por_ops
            WHERE  p.id = %s AND p.entidad_id = %s
            """,
            (paciente_id, entidad_id)
        )
        row = cur.fetchone()
        return dict(row) if row else None


def buscar_pacientes_rapido(
    ejecutor:   dict,
    entidad_id: int,
    texto:      str,
    limite:     int = 20,
) -> list[dict]:
    """
    Busqueda rapida via public.buscar_pacientes() para el
    selector en el formulario de eventos.
    """
    err = _check(ejecutor)
    if err:
        return []
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM public.buscar_pacientes(%s, %s, %s)",
                (entidad_id, texto or None, limite)
            )
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("buscar_pacientes_rapido: %s", e)
        return []


# ══════════════════════════════════════════════════════════════
# GUARDAR (CREAR / ACTUALIZAR CON UPSERT)
# ══════════════════════════════════════════════════════════════

def guardar_paciente(
    ejecutor:    dict,
    entidad_id:  int,
    datos:       dict,
    paciente_id: Optional[int] = None,
) -> Resultado:
    """
    Crea o actualiza un paciente.

    Si paciente_id es None y el par (tipo_documento_id, numero_documento)
    ya existe en la entidad -> ACTUALIZA (upsert, nunca duplica).

    datos aceptados:
        tipo_doc_abrev *      str  abreviatura tipo_documento
        numero_documento *    str
        primer_apellido *     str
        primer_nombre *       str
        segundo_apellido      str  (schema NOT NULL -> '' si falta)
        segundo_nombre        str  (nullable)
        fecha_nacimiento      str  DD/MM/AAAA o AAAA-MM-DD (opcional)
        sexo                  str  M / F / O (opcional)
        municipio_residencia  str  (opcional)
        zona_residencia       str  Urbana / Rural (opcional)
        direccion             str  (opcional)
        telefono              str  (opcional)
        eps_id                int  (opcional, FK eps)
        tipo_afiliacion_id    int  (opcional, FK tipo_afiliacion)
    """
    err = _check(ejecutor)
    if err:
        return err

    for campo in ("tipo_doc_abrev", "numero_documento", "primer_apellido", "primer_nombre"):
        if not str(datos.get(campo, "")).strip():
            return Resultado(False, f"El campo '{campo}' es obligatorio.")

    tipo_abrev = datos["tipo_doc_abrev"].strip().upper()
    num_doc    = datos["numero_documento"].strip()
    p_ape      = datos["primer_apellido"].strip()
    p_nom      = datos["primer_nombre"].strip()
    # segundo_apellido NOT NULL -> '' si no viene
    s_ape      = str(datos.get("segundo_apellido") or "").strip()
    s_nom      = str(datos.get("segundo_nombre") or "").strip() or None
    direccion  = str(datos.get("direccion") or "").strip() or None
    telefono   = str(datos.get("telefono") or "").strip() or None
    municipio  = str(datos.get("municipio_residencia") or "").strip() or None
    zona       = _zona(datos.get("zona_residencia"))
    sexo       = _sexo(datos.get("sexo"))
    eps_id     = _ops_none(datos.get("eps_id"))
    afil_id    = _ops_none(datos.get("tipo_afiliacion_id"))
    fecha_nac  = _fecha(str(datos.get("fecha_nacimiento") or ""))
    ops_autor  = _ops_none(ejecutor.get("ops_id"))

    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()

            # Resolver tipo_documento_id
            cur.execute(
                "SELECT id FROM public.tipo_documento "
                "WHERE abreviatura = %s AND activo = TRUE LIMIT 1",
                (tipo_abrev,)
            )
            td_row = cur.fetchone()
            if not td_row:
                return Resultado(
                    False,
                    f"Tipo de documento '{tipo_abrev}' no existe o no esta activo."
                )
            td_id = td_row["id"]

            # Si no hay paciente_id buscar si existe (upsert)
            if paciente_id is None:
                cur.execute(
                    "SELECT id FROM public.paciente "
                    "WHERE entidad_id=%s AND tipo_documento_id=%s "
                    "AND numero_documento=%s LIMIT 1",
                    (entidad_id, td_id, num_doc)
                )
                row = cur.fetchone()
                if row:
                    paciente_id = row["id"]

            if paciente_id:
                # ACTUALIZAR
                cur.execute(
                    """
                    UPDATE public.paciente SET
                        primer_apellido      = %s,
                        segundo_apellido     = %s,
                        primer_nombre        = %s,
                        segundo_nombre       = %s,
                        fecha_nacimiento     = %s,
                        sexo                 = %s,
                        municipio_residencia = %s,
                        zona_residencia      = %s,
                        direccion            = %s,
                        telefono             = %s,
                        eps_id               = %s,
                        tipo_afiliacion_id   = %s
                    WHERE id = %s AND entidad_id = %s
                    RETURNING id
                    """,
                    (p_ape, s_ape, p_nom, s_nom, fecha_nac, sexo,
                     municipio, zona, direccion, telefono,
                     eps_id, afil_id, paciente_id, entidad_id)
                )
                if not cur.fetchone():
                    return Resultado(False, "Paciente no encontrado en esta entidad.")
                return Resultado(
                    True,
                    "Paciente actualizado exitosamente.",
                    {"paciente_id": paciente_id, "accion": "actualizado"}
                )
            else:
                # CREAR — verificar duplicado por numero_documento
                cur.execute(
                    "SELECT id FROM public.paciente "
                    "WHERE entidad_id=%s AND numero_documento=%s LIMIT 1",
                    (entidad_id, num_doc)
                )
                if cur.fetchone():
                    return Resultado(
                        False,
                        f"Ya existe un paciente con el documento '{num_doc}'. "
                        "Edite el registro existente en lugar de crear uno nuevo."
                    )

                cur.execute(
                    """
                    INSERT INTO public.paciente (
                        entidad_id, tipo_documento_id, numero_documento,
                        primer_apellido, segundo_apellido,
                        primer_nombre,  segundo_nombre,
                        fecha_nacimiento, sexo,
                        municipio_residencia, zona_residencia,
                        direccion, telefono,
                        eps_id, tipo_afiliacion_id,
                        activo, creado_por_ops
                    ) VALUES (
                        %s, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        TRUE, %s
                    ) RETURNING id
                    """,
                    (entidad_id, td_id, num_doc,
                     p_ape, s_ape,
                     p_nom, s_nom,
                     fecha_nac, sexo,
                     municipio, zona,
                     direccion, telefono,
                     eps_id, afil_id,
                     ops_autor)
                )
                nuevo_id = cur.fetchone()["id"]
                return Resultado(
                    True,
                    "Paciente creado exitosamente.",
                    {"paciente_id": nuevo_id, "accion": "creado"}
                )

    except Exception as e:
        err_str = str(e).lower()
        if "chk_paciente_sexo" in err_str:
            return Resultado(False, "Valor de Sexo invalido. Use M, F u O.")
        if "unique" in err_str:
            return Resultado(False, "Ya existe un paciente con ese documento.")
        logger.exception("guardar_paciente")
        return Resultado(False, f"Error al guardar: {str(e).split(chr(10))[0]}")


# ══════════════════════════════════════════════════════════════
# CAMBIAR ESTADO
# ══════════════════════════════════════════════════════════════

def cambiar_estado_paciente(
    ejecutor:    dict,
    entidad_id:  int,
    paciente_id: int,
    activo:      bool,
) -> Resultado:
    err = _check(ejecutor)
    if err:
        return err
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE public.paciente SET activo=%s "
                "WHERE id=%s AND entidad_id=%s RETURNING id",
                (activo, paciente_id, entidad_id)
            )
            if not cur.fetchone():
                return Resultado(False, "Paciente no encontrado.")
        return Resultado(True, f"Paciente {'activado' if activo else 'desactivado'} correctamente.")
    except Exception as e:
        return Resultado(False, f"Error: {e}")


# ══════════════════════════════════════════════════════════════
# ESTADISTICAS
# ══════════════════════════════════════════════════════════════

def stats_pacientes(ejecutor: dict, entidad_id: int) -> dict:
    err = _check(ejecutor)
    if err:
        return {"total": 0, "activos": 0, "inactivos": 0, "con_eps": 0, "sin_eps": 0}
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    COUNT(*)                                        AS total,
                    COUNT(*) FILTER (WHERE activo = TRUE)          AS activos,
                    COUNT(*) FILTER (WHERE activo = FALSE)         AS inactivos,
                    COUNT(*) FILTER (WHERE eps_id IS NOT NULL)     AS con_eps,
                    COUNT(*) FILTER (WHERE eps_id IS NULL)         AS sin_eps
                FROM public.paciente WHERE entidad_id = %s
                """,
                (entidad_id,)
            )
            row = cur.fetchone()
            return {k: int(row[k]) for k in row.keys()}
    except Exception as e:
        logger.error("stats_pacientes: %s", e)
        return {"total": 0, "activos": 0, "inactivos": 0, "con_eps": 0, "sin_eps": 0}


# ══════════════════════════════════════════════════════════════
# PLANTILLA EXCEL
# ══════════════════════════════════════════════════════════════

COLUMNAS_PLANTILLA = [
    "Tipo_identificacion",    # obligatorio
    "Numero_documento",       # obligatorio
    "Primer_apellido",        # obligatorio
    "Segundo_apellido",       # schema NOT NULL -> '' si falta
    "Primer_nombre",          # obligatorio
    "Segundo_nombre",
    "Fecha_nacimiento",       # DD/MM/AAAA
    "Sexo",                   # M / F / O
    "Municipio_residencia",
    "Zona_residencia",        # Urbana / Rural
    "Telefono",
    "Direccion",
    "Codigo_EPS",             # eps.codigo -- NO el nombre
    "Tipo_afiliacion",        # nombre exacto del tipo
]


def generar_plantilla_excel(ruta: str) -> Resultado:
    """Genera plantilla XLSX. Codigo_EPS usa eps.codigo, no el nombre."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        AZ = "2D6ADF"; AZ_C = "EEF3FF"; GR = "F5F7FA"; BL = "FFFFFF"; BO = "D1D5DB"

        def _fill(c): return PatternFill("solid", fgColor=c)
        def _font(bold=False, color="1A1A2E", size=10, italic=False):
            return Font(bold=bold, color=color, size=size, italic=italic, name="Arial")
        def _aln(h="left", v="center", wrap=False):
            return Alignment(horizontal=h, vertical=v, wrap_text=wrap)
        def _brd():
            s = Side(border_style="thin", color=BO)
            return Border(left=s, right=s, top=s, bottom=s)

        wb = Workbook()
        ws = wb.active
        ws.title = "Carga Pacientes"

        ws.merge_cells("A1:N1")
        ws["A1"].value     = "SIGES - Plantilla Carga Masiva de Pacientes"
        ws["A1"].font      = _font(bold=True, color=BL, size=13)
        ws["A1"].fill      = _fill(AZ)
        ws["A1"].alignment = _aln("left", "center")
        ws.row_dimensions[1].height = 28

        instrucciones = [
            "INSTRUCCIONES:",
            "Campos obligatorios (*): Tipo_identificacion, Numero_documento, "
            "Primer_apellido, Primer_nombre.",
            "Tipo_identificacion validos: CC, TI, RC, CE, TE, NIT, PEP, PPT, CD, PP, TD, CNV.",
            "Fecha_nacimiento formato DD/MM/AAAA. Dejar vacio si no se conoce.",
            "Sexo: M=Masculino, F=Femenino, O=Otro. Dejar vacio si no aplica.",
            "Zona_residencia: Urbana o Rural.",
            "Codigo_EPS: usar el CODIGO de la EPS (campo Codigo en el modulo EPS), NO el nombre.",
            "Tipo_afiliacion: nombre EXACTO del tipo (ej: Subsidiado, Contributivo).",
            "Maximo 20.000 filas por archivo. Datos desde la fila 13.",
        ]
        for i, txt in enumerate(instrucciones, 2):
            ws.merge_cells(f"A{i}:N{i}")
            c = ws[f"A{i}"]
            c.value = txt
            c.font = _font(size=9, italic=(i > 2), bold=(i == 2), color="374151")
            c.fill = _fill(AZ_C)
            c.alignment = _aln("left", "center", wrap=True)
            ws.row_dimensions[i].height = 14

        ws.merge_cells("A11:N11")
        ws["A11"].fill = _fill(AZ)
        ws.row_dimensions[11].height = 4

        COLS_DEF = [
            ("Tipo_identificacion *", 18), ("Numero_documento *", 20),
            ("Primer_apellido *", 20), ("Segundo_apellido", 20),
            ("Primer_nombre *", 20), ("Segundo_nombre", 18),
            ("Fecha_nacimiento", 18), ("Sexo", 10),
            ("Municipio_residencia", 22), ("Zona_residencia", 16),
            ("Telefono", 16), ("Direccion", 28),
            ("Codigo_EPS", 16), ("Tipo_afiliacion", 22),
        ]
        HDR = 12
        for col, (titulo, ancho) in enumerate(COLS_DEF, 1):
            ws.column_dimensions[get_column_letter(col)].width = ancho
            c = ws.cell(row=HDR, column=col, value=titulo)
            c.font = _font(bold=True, color=BL, size=10)
            c.fill = _fill(AZ)
            c.alignment = _aln("center", "center")
            c.border = _brd()
        ws.row_dimensions[HDR].height = 22

        ayudas = [
            "RC,TI,CC,CE...", "Solo numeros", "Texto", "'' si no tiene",
            "Texto", "Opcional", "DD/MM/AAAA", "M/F/O",
            "Texto", "Urbana/Rural", "Solo numeros", "Texto",
            "CODIGO EPS (no nombre)", "Nombre tipo afiliacion",
        ]
        for col, txt in enumerate(ayudas, 1):
            c = ws.cell(row=HDR + 1, column=col, value=txt)
            c.font = _font(size=8, italic=True, color="6B7280")
            c.fill = _fill(GR)
            c.alignment = _aln("center", "center", wrap=True)
            c.border = _brd()
        ws.row_dimensions[HDR + 1].height = 16

        ejemplos = [
            ["CC","1234567890","PEREZ","GARCIA","JUAN","CARLOS","15/03/1985","M",
             "Bogota","Urbana","3001234567","Calle 10 No 5-20","EPS001","Contributivo"],
            ["TI","987654321","LOPEZ","","MARIA","","20/07/2005","F",
             "Medellin","Urbana","3109876543","","EPS002","Subsidiado"],
            ["CE","E123456","MARTINEZ","DIAZ","ANA","LUCIA","01/01/1990","F",
             "Cali","Urbana","","Cra 5 No 10-20","",""],
            ["CNV","","SIERRA","","JUAN","","","M",
             "Santa Marta","Rural","","","EPS003","Subsidiado"],
        ]
        for fi, fila in enumerate(ejemplos, HDR + 2):
            for col, val in enumerate(fila, 1):
                c = ws.cell(row=fi, column=col, value=val)
                c.font = _font(size=9, color="374151")
                c.fill = _fill(BL if fi % 2 == 0 else GR)
                c.alignment = _aln("left", "center")
                c.border = _brd()
            ws.row_dimensions[fi].height = 18

        ws.freeze_panes = ws.cell(row=HDR + 2, column=1)

        # Hoja tipos de documento
        ws2 = wb.create_sheet("Tipos Documento")
        ws2.merge_cells("A1:C1")
        ws2["A1"].value = "Tipos de Documento Validos"
        ws2["A1"].font = _font(bold=True, color=BL, size=11)
        ws2["A1"].fill = _fill(AZ)
        ws2["A1"].alignment = _aln("center", "center")
        tipos_ref = [
            ("Abrev.", "Nombre completo", "Uso tipico"),
            ("RC","Registro Civil","Recien nacidos"),
            ("TI","Tarjeta de Identidad","Menores 7-17 anos"),
            ("CC","Cedula de Ciudadania","Adultos colombianos"),
            ("CE","Cedula de Extranjeria","Extranjeros residentes"),
            ("TE","Tarjeta de Extranjeria","Extranjeros menores"),
            ("NIT","NIT","Personas juridicas"),
            ("PP","Pasaporte","Colombianos o extranjeros"),
            ("PEP","Permiso Especial de Permanencia","Migrantes venezolanos"),
            ("PPT","Permiso de Proteccion Temporal","Migrantes venezolanos"),
            ("CD","Carne Diplomatico","Diplomaticos"),
            ("TD","Documento desconocido","Sin identificar"),
            ("CNV","Certificado de Nacido Vivo","Neonatos sin RC"),
        ]
        for ri, (a, b, c_v) in enumerate(tipos_ref, 2):
            is_h = (ri == 2)
            for ci, val in enumerate([a, b, c_v], 1):
                cell = ws2.cell(row=ri, column=ci, value=val)
                cell.font = _font(bold=is_h, color=BL if is_h else "374151")
                cell.fill = _fill(AZ if is_h else (AZ_C if ci == 1 else (GR if ri % 2 == 0 else BL)))
                cell.alignment = _aln("center" if ci == 1 else "left", "center")
                cell.border = _brd()
        ws2.column_dimensions["A"].width = 12
        ws2.column_dimensions["B"].width = 30
        ws2.column_dimensions["C"].width = 24

        ruta_final = str(Path(ruta).with_suffix(".xlsx"))
        wb.save(ruta_final)
        return Resultado(True, f"Plantilla guardada en: {ruta_final}", {"ruta": ruta_final})

    except ImportError:
        return Resultado(False, "Instala openpyxl: pip install openpyxl")
    except Exception as e:
        return Resultado(False, f"Error al generar plantilla: {e}")


def generar_plantilla_csv(ruta: str) -> Resultado:
    """Alias que genera xlsx aunque la ruta diga .csv."""
    return generar_plantilla_excel(ruta)


# ══════════════════════════════════════════════════════════════
# CARGA MASIVA
# ══════════════════════════════════════════════════════════════

def procesar_carga_masiva(
    ejecutor:     dict,
    entidad_id:   int,
    ruta_archivo: str,
    on_progreso:  Optional[Callable[[int, int], None]] = None,
) -> Resultado:
    """
    Carga masiva de pacientes desde CSV o XLSX.

    EPS: resuelve Codigo_EPS -> eps.codigo (exacto, case-insensitive).
         Si no encuentra: advertencia, fila se guarda sin EPS.

    Tipo afiliacion: resuelve por nombre (case-insensitive).

    Upsert: (tipo_documento_id, numero_documento) existente -> UPDATE.
            No existente -> INSERT.

    segundo_apellido: NOT NULL en schema; si viene vacio se guarda ''.

    Retorna datos:
        { total, creados, actualizados,
          errores_bloqueo, advertencias_eps,
          errores: [{fila, campo, error}], lote_id }
    """
    err = _check(ejecutor)
    if err:
        return err

    ruta = Path(ruta_archivo)
    if not ruta.exists():
        return Resultado(False, "El archivo no existe.")

    # ── Leer filas del archivo ────────────────────────────────
    filas: list[dict] = []
    try:
        ext = ruta.suffix.lower()
        if ext == ".csv":
            with open(ruta, newline="", encoding="utf-8-sig") as f:
                filas = list(csv.DictReader(f))
        elif ext in (".xlsx", ".xls"):
            try:
                import openpyxl
            except ImportError:
                return Resultado(False, "Instala openpyxl: pip install openpyxl")
            wb  = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
            ws  = wb.active
            # Detectar fila de encabezados
            _buscar = {
                "tipo_identificacion", "tipo_identificacion *",
                "numero_documento", "numero_documento *",
                "primer_apellido", "primer_apellido *",
                "codigo_eps", "codigo eps",
            }
            hdr_row = 1
            for row in ws.iter_rows(min_row=1, max_row=20):
                vals = {str(c.value or "").strip().rstrip(" *").lower() for c in row}
                if vals & _buscar:
                    hdr_row = row[0].row
                    break
            enc = [
                str(c.value or "").strip().rstrip(" *") if c.value else None
                for c in ws[hdr_row]
            ]
            for row in ws.iter_rows(min_row=hdr_row + 2, values_only=True):
                if all(v is None or str(v).strip() == "" for v in row):
                    continue
                filas.append(dict(zip(
                    enc,
                    [str(v).strip() if v is not None else "" for v in row]
                )))
            wb.close()
        else:
            return Resultado(False, "Formato no soportado. Use .csv o .xlsx")
    except Exception as e:
        return Resultado(False, f"Error al leer el archivo: {e}")

    if not filas:
        return Resultado(False, "El archivo esta vacio o no tiene datos validos.")

    total = len(filas)
    if total > MAX_FILAS_LOTE:
        return Resultado(False, f"El archivo tiene {total} filas. Maximo: {MAX_FILAS_LOTE}.")

    # ── Mapas de catalogos ────────────────────────────────────
    # EPS: UPPER(codigo) -> id
    mapa_eps: dict[str, int] = {}
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, UPPER(TRIM(codigo)) AS c "
                "FROM public.eps "
                "WHERE entidad_id=%s AND activo=TRUE "
                "AND codigo IS NOT NULL AND TRIM(codigo)<>''",
                (entidad_id,)
            )
            for r in cur.fetchall():
                mapa_eps[r["c"]] = r["id"]
    except Exception as e:
        logger.warning("mapa_eps: %s", e)

    # Afiliacion: lower(nombre) -> id
    mapa_afil: dict[str, int] = {}
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, LOWER(TRIM(nombre)) AS n "
                "FROM public.tipo_afiliacion WHERE activo=TRUE"
            )
            for r in cur.fetchall():
                mapa_afil[r["n"]] = r["id"]
    except Exception as e:
        logger.warning("mapa_afil: %s", e)

    # ── Registrar lote ────────────────────────────────────────
    lote_id: Optional[int] = None
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO public.carga_masiva_lote "
                "(entidad_id, tipo, nombre_archivo, total_filas, estado) "
                "VALUES (%s,'pacientes',%s,%s,'procesando') RETURNING id",
                (entidad_id, ruta.name, total)
            )
            lote_id = cur.fetchone()["id"]
    except Exception:
        pass

    # ── Procesar fila a fila ──────────────────────────────────
    creados      = 0
    actualizados = 0
    errores_log: list[dict]  = []
    errores_bd:  list[tuple] = []

    def _g(fila: dict, *claves: str) -> str:
        """Extrae primer valor no vacio entre las claves (case-insensitive, ignora asteriscos)."""
        for clave in claves:
            k_clean = clave.strip().rstrip(" *").lower()
            for k, v in fila.items():
                if k is not None and k.strip().rstrip(" *").lower() == k_clean:
                    val = str(v or "").strip()
                    if val:
                        return val
        return ""

    for idx, fila in enumerate(filas, start=2):
        tipo    = _g(fila, "Tipo_identificacion").upper()
        num_doc = _g(fila, "Numero_documento")
        p_ape   = _g(fila, "Primer_apellido")
        p_nom   = _g(fila, "Primer_nombre")

        # Campos obligatorios — bloquean la fila
        bloq = False
        for val, campo in [
            (tipo,    "Tipo_identificacion"),
            (num_doc, "Numero_documento"),
            (p_ape,   "Primer_apellido"),
            (p_nom,   "Primer_nombre"),
        ]:
            if not val:
                e = {"fila": idx, "campo": campo, "error": "Campo obligatorio"}
                errores_log.append(e)
                errores_bd.append((lote_id, idx, campo, "Campo obligatorio"))
                bloq = True
        if bloq:
            continue

        # Resolver EPS por CODIGO
        codigo_raw = _g(fila, "Codigo_EPS", "codigo_eps", "CodigoEPS").upper()
        eps_id_fila: Optional[int] = None
        if codigo_raw:
            eps_id_fila = mapa_eps.get(codigo_raw)
            if eps_id_fila is None:
                msg = f"EPS codigo '{codigo_raw}' no encontrado -- fila guardada sin EPS"
                errores_log.append({"fila": idx, "campo": "Codigo_EPS", "error": msg})
                errores_bd.append((lote_id, idx, "Codigo_EPS", msg))

        # Resolver tipo afiliacion por nombre
        afil_raw = _g(fila, "Tipo_afiliacion", "TIPO_DE_AFILIACION").lower()
        afil_id_fila: Optional[int] = mapa_afil.get(afil_raw) if afil_raw else None

        datos_fila = {
            "tipo_doc_abrev":      tipo,
            "numero_documento":    num_doc,
            "primer_apellido":     p_ape,
            "segundo_apellido":    _g(fila, "Segundo_apellido"),  # '' si falta (NOT NULL)
            "primer_nombre":       p_nom,
            "segundo_nombre":      _g(fila, "Segundo_nombre") or None,
            "fecha_nacimiento":    _g(fila, "Fecha_nacimiento") or None,
            "sexo":                _g(fila, "Sexo") or None,
            "municipio_residencia":_g(fila, "Municipio_residencia", "Municipio") or None,
            "zona_residencia":     _g(fila, "Zona_residencia", "Zona") or None,
            "telefono":            _g(fila, "Telefono") or None,
            "direccion":           _g(fila, "Direccion") or None,
            "eps_id":              eps_id_fila,
            "tipo_afiliacion_id":  afil_id_fila,
        }

        res = guardar_paciente(ejecutor, entidad_id, datos_fila)

        if res.ok:
            if (res.datos or {}).get("accion") == "actualizado":
                actualizados += 1
            else:
                creados += 1
        else:
            errores_log.append({"fila": idx, "campo": "--", "error": res.mensaje})
            errores_bd.append((lote_id, idx, "--", res.mensaje))

        if on_progreso and idx % 100 == 0:
            on_progreso(idx - 1, total)

    if on_progreso:
        on_progreso(total, total)

    # ── Persistir errores ─────────────────────────────────────
    if lote_id and errores_bd:
        try:
            with Conexion() as conn:
                cur = conn.cursor()
                for lid, fn, campo, desc in errores_bd:
                    if lid is None:
                        continue
                    cur.execute(
                        "INSERT INTO public.carga_masiva_error "
                        "(lote_id, numero_fila, campo, descripcion) VALUES (%s,%s,%s,%s)",
                        (lid, fn, campo, desc)
                    )
        except Exception:
            pass

    # ── Cerrar lote ───────────────────────────────────────────
    if lote_id:
        try:
            with Conexion() as conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE public.carga_masiva_lote "
                    "SET filas_ok=%s, filas_error=%s, "
                    "estado='completado', completado_en=NOW() WHERE id=%s",
                    (creados + actualizados, len(errores_bd), lote_id)
                )
        except Exception:
            pass

    adv_eps    = [e for e in errores_log if e.get("campo") == "Codigo_EPS"]
    err_reales = [e for e in errores_log if e.get("campo") != "Codigo_EPS"]

    return Resultado(
        ok=True,
        mensaje=(
            f"Carga completada: {creados} nuevos, {actualizados} actualizados, "
            f"{len(err_reales)} errores, {len(adv_eps)} advertencias EPS "
            f"de {total} filas."
        ),
        datos={
            "total":           total,
            "creados":         creados,
            "actualizados":    actualizados,
            "errores_bloqueo": len(err_reales),
            "advertencias_eps":len(adv_eps),
            "errores":         errores_log,
            "lote_id":         lote_id,
        },
    )
