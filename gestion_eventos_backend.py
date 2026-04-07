# -*- coding: utf-8 -*-
# =============================================================================
# gestion_eventos_backend.py  --  Modulo de Eventos CAOR (v3 - BD real)
#
# CORRECCION COMPLETA contra el schema real (1_gestion_eventos_salud.sql):
#
#   Conexion:
#     * Usa conexion.Conexion(dict_cursor=True) directamente (sin puente)
#     * Patron: with Conexion(dict_cursor=True) as conn: cur = conn.cursor()
#
#   Vistas / RPCs que NO existen en BD (no usar):
#     * v_evento_detalle          -> SQL directo sobre tablas
#     * v_paciente_evento         -> SQL directo sobre tablas
#     * rpc_form_evento           -> Python puro + queries
#     * rpc_guardar_evento        -> INSERT/UPDATE directo
#     * rpc_desactivar_evento     -> UPDATE directo
#     * reactivar_ventana_evento  -> UPDATE directo
#
#   RPCs que SI existen en BD (usar):
#     * buscar_pacientes(entidad_id, texto, limite)
#     * buscar_eps(entidad_id, texto, limite)
#     * buscar_eventos(entidad_id, ops_id, texto, estado_id,
#                      fecha_desde, fecha_hasta, solo_sin_contrato,
#                      limite, offset, incluir_inactivos)
#     * resumen_facturacion(entidad_id, ops_id, fecha_desde, fecha_hasta)
#     * eps_tiene_contrato(entidad_id, eps_id, fecha)
#
#   tipo_afiliacion NO tiene columna creado_por_entidad -> catalogo global
#   evento.tiene_contrato lo calcula el trigger trg_verificar_contrato_eps
#   editable_hasta lo calcula el trigger trg_calcular_editable_hasta
#
# Roles:
#   ops              -> filtra creado_por_ops = ops_id
#   maestro/entidad/admin -> ops_id=None en filtro (ve todos)
#
# Estados: 1=Pendiente  2=Terminado
# Regla:   valor > 0 -> estado=2 y numero_factura obligatorio
# =============================================================================
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from conexion import Conexion


_ROLES_VER_TODO = {"admin", "maestro", "entidad"}


@dataclass
class Resultado:
    ok:      bool
    mensaje: str
    datos:   object = field(default=None)


def _ops_safe(ops_id) -> int | None:
    if ops_id is None or ops_id == 0 or str(ops_id) == "":
        return None
    return int(ops_id)


def _ops_para_filtro(rol: str, ops_id) -> int | None:
    """ops -> su ID; maestro/entidad/admin -> None (ve todos)."""
    if rol in _ROLES_VER_TODO:
        return None
    return _ops_safe(ops_id)


# ============================================================
# CATALOGOS
# ============================================================

def obtener_tipos_afiliacion(entidad_id: int = None) -> list[dict]:
    """
    Catalogo global. tipo_afiliacion no tiene creado_por_entidad.
    """
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, nombre, codigo "
            "FROM public.tipo_afiliacion "
            "WHERE activo = TRUE ORDER BY nombre"
        )
        return [dict(r) for r in cur.fetchall()]


def obtener_eps_entidad(entidad_id: int) -> list[dict]:
    """
    EPS de la entidad usando buscar_eps() RPC que SI existe en BD.
    Tambien calcula tiene_contrato para el aviso en el formulario.
    """
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT eps_id, codigo, nombre, nit, municipio, tiene_contrato "
                "FROM public.buscar_eps(%s::integer, ''::text, 500)",
                (entidad_id,)
            )
            return [dict(r) for r in cur.fetchall()]
        except Exception:
            pass

        # Fallback directo si la RPC falla
        cur.execute(
            """SELECT e.id AS eps_id, e.codigo, e.nombre, e.nit,
                      e.municipio,
                      public.eps_tiene_contrato(%s::integer, e.id, CURRENT_DATE)
                          AS tiene_contrato
               FROM   public.eps e
               WHERE  e.entidad_id = %s AND e.activo = TRUE
               ORDER  BY e.nombre""",
            (entidad_id, entidad_id)
        )
        return [dict(r) for r in cur.fetchall()]


def cargar_formulario(entidad_id: int,
                      evento_id: int | None = None) -> dict:
    """
    Reemplaza rpc_form_evento (no existe en BD).
    Devuelve catalogos y, si se pide, datos del evento para edicion.
    """
    resultado = {
        "eps_lista":        obtener_eps_entidad(entidad_id),
        "tipos_afiliacion": obtener_tipos_afiliacion(),
        "es_editable":      True,
    }
    if evento_id:
        ev = obtener_evento(entidad_id, evento_id)
        if ev:
            resultado["evento"]      = ev
            resultado["es_editable"] = bool(ev.get("es_editable", True))
    return resultado


# ============================================================
# PACIENTES
# ============================================================

def buscar_pacientes(entidad_id: int, texto: str,
                     limite: int = 30) -> list[dict]:
    """
    Usa buscar_pacientes() RPC que SI existe en BD.
    La RPC devuelve: paciente_id(=id), nombre_completo, tipo_doc,
                     numero_documento, eps_nombre, tipo_afiliacion, activo
    El fallback agrega eps_id y tipo_afiliacion_id para el auto-completado.
    """
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT * FROM public.buscar_pacientes"
                "(%s::integer, %s::text, %s::integer)",
                (entidad_id, texto, limite)
            )
            rows = [dict(r) for r in cur.fetchall()]
            # Normalizar: la funcion puede exponer "id" en vez de "paciente_id"
            for r in rows:
                if "paciente_id" not in r and "id" in r:
                    r["paciente_id"] = r["id"]
            # La RPC no tiene eps_id ni tipo_afiliacion_id;
            # si el UI los necesita para auto-completar, usar fallback
            if rows and "eps_id" not in rows[0]:
                raise Exception("sin eps_id")
            return rows
        except Exception:
            pass

        # Fallback con todos los campos necesarios para auto-completado
        cur.execute(
            """SELECT p.id AS paciente_id,
                      CONCAT_WS(' ', p.primer_nombre, p.segundo_nombre,
                                p.primer_apellido, p.segundo_apellido)
                          AS nombre_completo,
                      td.abreviatura        AS tipo_doc,
                      p.numero_documento,
                      p.eps_id,
                      ep.nombre             AS eps_nombre,
                      p.tipo_afiliacion_id,
                      ta.nombre             AS tipo_afiliacion_nombre,
                      p.activo
               FROM   public.paciente       p
               JOIN   public.tipo_documento td ON td.id = p.tipo_documento_id
               LEFT   JOIN public.eps            ep ON ep.id = p.eps_id
               LEFT   JOIN public.tipo_afiliacion ta ON ta.id = p.tipo_afiliacion_id
               WHERE  p.entidad_id = %s
                 AND  p.activo = TRUE
                 AND (
                       p.numero_documento ILIKE '%%' || %s || '%%'
                    OR p.primer_apellido  ILIKE %s || '%%'
                    OR p.primer_nombre    ILIKE %s || '%%'
                    OR CONCAT_WS(' ', p.primer_nombre, p.segundo_nombre,
                                 p.primer_apellido, p.segundo_apellido)
                       ILIKE '%%' || %s || '%%'
                 )
               ORDER  BY p.primer_apellido, p.primer_nombre
               LIMIT  %s""",
            (entidad_id, texto, texto, texto, texto, limite)
        )
        return [dict(r) for r in cur.fetchall()]


def obtener_datos_paciente(entidad_id: int,
                           paciente_id: int) -> dict | None:
    """Datos del paciente para auto-completar EPS y tipo de afiliacion."""
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT p.id AS paciente_id,
                      CONCAT_WS(' ', p.primer_nombre, p.segundo_nombre,
                                p.primer_apellido, p.segundo_apellido)
                          AS nombre_completo,
                      td.abreviatura        AS tipo_doc,
                      p.numero_documento,
                      p.eps_id,
                      ep.nombre             AS eps_nombre,
                      p.tipo_afiliacion_id,
                      ta.nombre             AS tipo_afiliacion_nombre
               FROM   public.paciente       p
               JOIN   public.tipo_documento td ON td.id = p.tipo_documento_id
               LEFT   JOIN public.eps            ep ON ep.id = p.eps_id
               LEFT   JOIN public.tipo_afiliacion ta ON ta.id = p.tipo_afiliacion_id
               WHERE  p.id = %s AND p.entidad_id = %s""",
            (paciente_id, entidad_id)
        )
        row = cur.fetchone()
        return dict(row) if row else None


# ============================================================
# LISTADO DE EVENTOS
# ============================================================

def listar_eventos(entidad_id: int, ops_id=None, texto: str = "",
                   estado_id: int | None = None,
                   fecha_desde: str | None = None,
                   fecha_hasta: str | None = None,
                   limite: int = 200, offset: int = 0,
                   incluir_inactivos: bool = False,
                   rol: str = "ops") -> list[dict]:
    """
    Usa buscar_eventos() RPC con la firma correcta del SQL:
      buscar_eventos(p_entidad_id, p_ops_id, p_texto, p_estado_id,
                     p_fecha_desde, p_fecha_hasta, p_solo_sin_contrato,
                     p_limite, p_offset, p_incluir_inactivos)
    Fallback a SQL directo si la RPC falla.
    """
    oid_filtro    = _ops_para_filtro(rol, ops_id)
    ver_inactivos = incluir_inactivos and rol in _ROLES_VER_TODO
    txt           = texto.strip() or None
    fd            = fecha_desde or None
    fh            = fecha_hasta or None

    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                """SELECT * FROM public.buscar_eventos(
                       %s::integer,
                       %s::integer,
                       %s::text,
                       %s::smallint,
                       %s::date,
                       %s::date,
                       FALSE,
                       %s::integer,
                       %s::integer,
                       %s::boolean
                   )""",
                (entidad_id, oid_filtro, txt,
                 estado_id, fd, fh,
                 limite, offset, ver_inactivos)
            )
            return [dict(r) for r in cur.fetchall()]
        except Exception:
            pass

        # Fallback SQL directo
        conds  = ["e.entidad_id = %s"]
        params = [entidad_id]

        if oid_filtro is not None:
            conds.append("e.creado_por_ops = %s")
            params.append(oid_filtro)
        if not ver_inactivos:
            conds.append("e.activo = TRUE")
        if estado_id is not None:
            conds.append("e.estado_id = %s")
            params.append(int(estado_id))
        if fd:
            conds.append("e.fecha_evento >= %s::date")
            params.append(fd)
        if fh:
            conds.append("e.fecha_evento <= %s::date")
            params.append(fh)
        if txt:
            like = f"%{txt}%"
            conds.append(
                "(p.numero_documento ILIKE %s"
                " OR CONCAT_WS(' ', p.primer_nombre, p.segundo_nombre,"
                "   p.primer_apellido, p.segundo_apellido) ILIKE %s"
                " OR e.motivo          ILIKE %s"
                " OR e.numero_admision ILIKE %s"
                " OR e.numero_factura  ILIKE %s)"
            )
            params += [like, like, like, like, like]

        where = " AND ".join(conds)
        params += [limite, offset]

        cur.execute(
            "SELECT"
            "  e.id                                           AS evento_id,"
            "  e.fecha_evento,"
            "  ee.nombre                                      AS estado,"
            "  (e.editable_hasta >= NOW())                    AS es_editable,"
            "  e.activo,"
            "  CONCAT_WS(' ', p.primer_nombre, p.segundo_nombre,"
            "    p.primer_apellido, p.segundo_apellido)       AS nombre_paciente,"
            "  td.abreviatura                                 AS tipo_doc,"
            "  p.numero_documento                             AS numero_doc,"
            "  ep.nombre                                      AS eps_nombre,"
            "  ta.nombre                                      AS tipo_afiliacion,"
            "  e.afiliado_eps,"
            "  e.tiene_contrato,"
            "  e.motivo,"
            "  e.valor,"
            "  e.numero_admision,"
            "  e.codigo_evento,"
            "  e.numero_factura,"
            "  u.nombre_completo                              AS ops_nombre,"
            "  COUNT(*) OVER()::bigint                        AS total_registros,"
            "  SUM(e.valor) OVER()                            AS total_facturado,"
            "  e.eps_id,"
            "  e.tipo_afiliacion_id,"
            "  e.estado_id,"
            "  e.paciente_id"
            " FROM  public.evento          e"
            " JOIN  public.paciente        p  ON p.id  = e.paciente_id"
            " JOIN  public.tipo_documento  td ON td.id = p.tipo_documento_id"
            " JOIN  public.tipo_afiliacion ta ON ta.id = e.tipo_afiliacion_id"
            " JOIN  public.estado_evento   ee ON ee.id = e.estado_id"
            " LEFT  JOIN public.eps             ep ON ep.id = e.eps_id"
            " LEFT  JOIN public.usuario_ops     u  ON u.id  = e.creado_por_ops"
            f" WHERE {where}"
            " ORDER BY e.fecha_evento DESC, e.id DESC"
            " LIMIT %s OFFSET %s",
            params
        )
        return [dict(r) for r in cur.fetchall()]


def obtener_evento(entidad_id: int, evento_id: int) -> dict | None:
    """
    Devuelve datos completos de un evento para edicion o visualizacion.
    No existe v_evento_detalle en BD; se consulta directamente.
    """
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT
                  e.id                                            AS evento_id,
                  e.entidad_id,
                  e.paciente_id,
                  e.fecha_evento,
                  e.eps_id,
                  e.tiene_contrato,
                  e.tipo_afiliacion_id,
                  e.afiliado_eps,
                  e.motivo,
                  e.diagnostico_principal,
                  e.valor,
                  e.numero_admision,
                  e.codigo_evento,
                  e.numero_factura,
                  e.estado_id,
                  e.activo,
                  e.creado_en,
                  e.creado_por_ops,
                  e.editable_hasta,
                  e.ventana_reactivada_en,
                  (e.editable_hasta >= NOW())                    AS es_editable,
                  ee.nombre                                      AS estado,
                  CONCAT_WS(' ', p.primer_nombre, p.segundo_nombre,
                            p.primer_apellido, p.segundo_apellido)
                                                                 AS paciente_nombre,
                  td.abreviatura                                 AS paciente_tipo_doc,
                  p.numero_documento                             AS paciente_numero_doc,
                  ep.nombre                                      AS eps_nombre,
                  ta.nombre                                      AS tipo_afiliacion,
                  u.nombre_completo                              AS ops_nombre
               FROM  public.evento          e
               JOIN  public.paciente        p  ON p.id  = e.paciente_id
               JOIN  public.tipo_documento  td ON td.id = p.tipo_documento_id
               JOIN  public.tipo_afiliacion ta ON ta.id = e.tipo_afiliacion_id
               JOIN  public.estado_evento   ee ON ee.id = e.estado_id
               LEFT  JOIN public.eps             ep ON ep.id = e.eps_id
               LEFT  JOIN public.usuario_ops     u  ON u.id  = e.creado_por_ops
               WHERE e.id = %s AND e.entidad_id = %s""",
            (evento_id, entidad_id)
        )
        row = cur.fetchone()
        return dict(row) if row else None


# ============================================================
# GUARDAR (INSERT / UPDATE)
# ============================================================

def guardar_evento(entidad_id: int, ops_id, datos: dict,
                   evento_id: int | None = None) -> Resultado:
    """
    Crea o actualiza un evento directamente en la tabla evento.
    No existe rpc_guardar_evento en BD.

    Triggers en BD que se disparan automaticamente:
      trg_verificar_contrato_eps -> calcula tiene_contrato
      trg_calcular_editable_hasta -> calcula editable_hasta
      trg_auditar -> registra en auditoria
    """
    # Validacion de campos obligatorios
    requeridos = ["paciente_id", "fecha_evento", "tipo_afiliacion_id"]
    for c in requeridos:
        if datos.get(c) is None or str(datos.get(c, "")).strip() == "":
            return Resultado(False, f"El campo '{c}' es obligatorio.")

    # Motivo: usar valor por defecto si no se provee
    motivo = (datos.get("motivo") or "").strip() or "Atencion registrada"

    # Valor
    try:
        valor = float(datos.get("valor") or 0)
    except (ValueError, TypeError):
        return Resultado(False, "El valor debe ser un numero.")
    if valor < 0:
        return Resultado(False, "El valor no puede ser negativo.")

    # Regla de negocio: valor > 0 -> Terminado (2)
    estado_id = 2 if valor > 0 else int(datos.get("estado_id") or 1)

    num_admision = (datos.get("numero_admision") or "").strip() or None
    num_codigo   = (datos.get("codigo_evento")   or "").strip() or None
    num_factura  = (datos.get("numero_factura")  or "").strip() or None

    # Al registrar por primera vez: solo numero_admision es obligatorio
    if evento_id is None:
        if not num_admision:
            return Resultado(False, "El numero de admision es obligatorio al registrar el evento.")

    # Al terminar (estado=2 / valor>0): los tres campos son obligatorios
    if estado_id == 2:
        if not num_admision:
            return Resultado(False, "El numero de admision es obligatorio para terminar el evento.")
        if not num_codigo:
            return Resultado(False, "El codigo del evento es obligatorio para terminar el evento.")
        if not num_factura:
            return Resultado(False, "El numero de factura es obligatorio para terminar el evento.")

    oid      = _ops_safe(ops_id)
    eps_id   = int(datos["eps_id"]) if datos.get("eps_id") else None
    afil_id  = int(datos["tipo_afiliacion_id"])
    pac_id   = int(datos["paciente_id"])
    fecha_ev = str(datos["fecha_evento"])[:10]
    afiliado = bool(datos.get("afiliado_eps", False))

    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            if evento_id is None:
                # ------ INSERT ------
                cur.execute(
                    """INSERT INTO public.evento (
                           entidad_id, paciente_id, fecha_evento,
                           eps_id, tipo_afiliacion_id, afiliado_eps,
                           motivo, valor, numero_admision, codigo_evento,
                           numero_factura, estado_id, creado_por_ops,
                           tiene_contrato
                       ) VALUES (
                           %s, %s, %s::date,
                           %s, %s, %s,
                           %s, %s, %s, %s,
                           %s, %s, %s,
                           COALESCE(
                               public.eps_tiene_contrato(%s::integer, %s::integer, %s::date),
                               FALSE
                           )
                       )
                       RETURNING id""",
                    (
                        entidad_id, pac_id, fecha_ev,
                        eps_id, afil_id, afiliado,
                        motivo, valor, num_admision, num_codigo,
                        num_factura, estado_id, oid,
                        entidad_id, eps_id, fecha_ev
                    )
                )
                row = cur.fetchone()
                nuevo_id = row["id"] if row else None
                return Resultado(
                    True, "Evento registrado correctamente.",
                    {"evento_id": nuevo_id, "accion": "creado",
                     "estado_id": estado_id}
                )

            else:
                # ------ UPDATE ------
                # Verificar ventana de edicion
                cur.execute(
                    "SELECT (editable_hasta >= NOW()) AS editable "
                    "FROM public.evento "
                    "WHERE id = %s AND entidad_id = %s",
                    (evento_id, entidad_id)
                )
                chk = cur.fetchone()
                if not chk:
                    return Resultado(False, "Evento no encontrado.")
                if not chk["editable"]:
                    return Resultado(
                        False,
                        "La ventana de edicion ha vencido. "
                        "Solicita al administrador que la reactive."
                    )

                cur.execute(
                    """UPDATE public.evento SET
                           fecha_evento        = %s::date,
                           eps_id              = %s,
                           tipo_afiliacion_id  = %s,
                           afiliado_eps        = %s,
                           motivo              = %s,
                           valor               = %s,
                           numero_admision     = %s,
                           codigo_evento       = %s,
                           numero_factura      = %s,
                           estado_id           = %s,
                           actualizado_por_ops = %s,
                           tiene_contrato      = COALESCE(
                               public.eps_tiene_contrato(%s::integer, %s::integer, %s::date),
                               FALSE
                           )
                       WHERE id = %s AND entidad_id = %s""",
                    (
                        fecha_ev, eps_id, afil_id, afiliado,
                        motivo, valor, num_admision, num_codigo,
                        num_factura, estado_id, oid,
                        entidad_id, eps_id, fecha_ev,
                        evento_id, entidad_id
                    )
                )
                if cur.rowcount == 0:
                    return Resultado(
                        False, "Evento no encontrado o sin permiso para editarlo."
                    )
                return Resultado(
                    True, "Evento actualizado correctamente.",
                    {"evento_id": evento_id, "accion": "actualizado",
                     "estado_id": estado_id}
                )

    except Exception as e:
        return Resultado(False, f"Error al guardar el evento: {e}")


# ============================================================
# DESACTIVAR (soft-delete)
# ============================================================

def desactivar_evento(entidad_id: int, evento_id: int,
                      ops_id) -> Resultado:
    """
    Marca activo=FALSE (nunca elimina fisicamente).
    OPS: solo puede desactivar sus propios eventos dentro de la ventana.
    Admin/maestro/entidad: pueden desactivar cualquier evento.
    """
    oid = _ops_safe(ops_id)
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            if oid is not None:
                # OPS: debe ser el creador y estar en ventana
                cur.execute(
                    """UPDATE public.evento SET activo = FALSE
                       WHERE  id            = %s
                         AND  entidad_id    = %s
                         AND  creado_por_ops = %s
                         AND  editable_hasta >= NOW()""",
                    (evento_id, entidad_id, oid)
                )
            else:
                # Admin/maestro/entidad: sin restriccion de ventana
                cur.execute(
                    """UPDATE public.evento SET activo = FALSE
                       WHERE id = %s AND entidad_id = %s""",
                    (evento_id, entidad_id)
                )
            if cur.rowcount == 0:
                return Resultado(
                    False,
                    "No se pudo desactivar. El evento no existe, "
                    "no es tuyo o ya vencio la ventana de edicion."
                )
        return Resultado(True, "Evento desactivado correctamente.")
    except Exception as e:
        return Resultado(False, f"Error: {e}")


# ============================================================
# ACTIVAR (reverso del soft-delete)
# ============================================================

def activar_evento(entidad_id: int, evento_id: int) -> Resultado:
    """Reactiva un evento desactivado. Solo el administrador debe usar esto."""
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                """UPDATE public.evento SET activo = TRUE
                   WHERE id = %s AND entidad_id = %s""",
                (evento_id, entidad_id)
            )
            if cur.rowcount == 0:
                return Resultado(False, "Evento no encontrado.")
        return Resultado(True, "Evento activado correctamente.")
    except Exception as e:
        return Resultado(False, f"Error: {e}")


# ============================================================
# REACTIVAR VENTANA DE EDICION (solo admin)
# ============================================================

def reactivar_ventana(entidad_id: int, evento_id: int) -> Resultado:
    """
    Reactiva la ventana de edicion del evento.
    Actualiza ventana_reactivada_en = NOW(); el trigger
    trg_calcular_editable_hasta recalcula editable_hasta = NOW() + 7 dias.
    No existe RPC reactivar_ventana_evento en BD.
    """
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute(
                """UPDATE public.evento
                   SET    ventana_reactivada_en = NOW()
                   WHERE  id = %s AND entidad_id = %s
                   RETURNING editable_hasta""",
                (evento_id, entidad_id)
            )
            row = cur.fetchone()
            if not row:
                return Resultado(False, "Evento no encontrado.")
            nueva = str(row["editable_hasta"])[:16] \
                    if row["editable_hasta"] else "--"
        return Resultado(
            True, f"Ventana reactivada. Editable hasta: {nueva}.",
            {"editable_hasta": nueva}
        )
    except Exception as e:
        return Resultado(False, f"Error: {e}")


# ============================================================
# KPIs / RESUMEN DE FACTURACION
# ============================================================

def resumen_facturacion(entidad_id: int, ops_id=None,
                        fecha_desde: str | None = None,
                        fecha_hasta: str | None = None,
                        rol: str = "ops") -> dict:
    """
    Usa resumen_facturacion() RPC que SI existe en BD.
    Fallback a query directa si la RPC falla.
    """
    oid_filtro = _ops_para_filtro(rol, ops_id)

    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                """SELECT * FROM public.resumen_facturacion(
                       %s::integer,
                       %s::integer,
                       %s::date,
                       %s::date
                   )""",
                (entidad_id, oid_filtro,
                 fecha_desde or None, fecha_hasta or None)
            )
            row = cur.fetchone()
            return dict(row) if row else {}
        except Exception:
            pass

        # Fallback directo
        conds  = ["e.entidad_id = %s", "e.activo = TRUE"]
        params = [entidad_id]
        if oid_filtro is not None:
            conds.append("e.creado_por_ops = %s"); params.append(oid_filtro)
        if fecha_desde:
            conds.append("e.fecha_evento >= %s::date"); params.append(fecha_desde)
        if fecha_hasta:
            conds.append("e.fecha_evento <= %s::date"); params.append(fecha_hasta)

        where = " AND ".join(conds)
        cur.execute(
            f"""SELECT
                    COUNT(*)                                      AS total_eventos,
                    COALESCE(SUM(valor), 0)                       AS total_facturado,
                    COUNT(*) FILTER (WHERE estado_id = 1)         AS eventos_pendientes,
                    COUNT(*) FILTER (WHERE estado_id = 2)         AS eventos_terminados,
                    COUNT(*) FILTER (WHERE tiene_contrato = TRUE)  AS eventos_con_contrato,
                    COUNT(*) FILTER (WHERE tiene_contrato = FALSE
                                      AND  eps_id IS NOT NULL)    AS eventos_sin_contrato,
                    COALESCE(SUM(valor) FILTER (WHERE tiene_contrato = TRUE), 0)
                                                                  AS facturado_con_contrato,
                    COALESCE(SUM(valor) FILTER (WHERE tiene_contrato = FALSE
                                                 AND  eps_id IS NOT NULL), 0)
                                                                  AS facturado_sin_contrato
                FROM public.evento e
               WHERE {where}""",
            params
        )
        row = cur.fetchone()
        return dict(row) if row else {}


# ============================================================
# HELPER FECHAS
# ============================================================

def fechas_filtro(periodo: str) -> tuple[str | None, str | None]:
    """'hoy'|'semana'|'mes'|'todos' -> (fecha_desde, fecha_hasta)"""
    hoy = date.today()
    if periodo == "hoy":
        s = str(hoy); return s, s
    if periodo == "semana":
        lunes = hoy - timedelta(days=hoy.weekday())
        return str(lunes), str(hoy)
    if periodo == "mes":
        return str(hoy.replace(day=1)), str(hoy)
    return None, None