# -*- coding: utf-8 -*-
# =============================================================================
# conexion.py - Modulo de conexion a PostgreSQL
# Base de datos: gestion_eventos (Sistema de Gestion de Eventos - Sector Salud)
#
# SINCRONIZACION BIDIRECCIONAL con config_conexion_backend.py:
#   - Al importar, carga la config desde gestion_eventos_db.cfg (si existe).
#   - Se registra como observer: cualquier cambio guardado desde la UI
#     se refleja automaticamente en DB_CONFIG sin reiniciar la app.
#   - Si la UI guarda una nueva config, la proxima llamada a get_conexion()
#     usara los nuevos parametros de forma transparente.
# =============================================================================

import sys
import io
import os
import psycopg2
from psycopg2 import OperationalError
from psycopg2.extras import RealDictCursor

# ── Manejo seguro de stdout/stderr ────────────────────────────
# Con --noconsole (PyInstaller), sys.stdout y sys.stderr son None.
# Cualquier print() crashea con: 'NoneType' has no attribute 'buffer'.
# Solucion: redirigir a devnull si no hay consola, o forzar UTF-8 si si hay.
def _fijar_streams() -> None:
    try:
        # Si no hay consola (exe compilado sin consola): redirigir a devnull
        if sys.stdout is None:
            _null = open(os.devnull, "w", encoding="utf-8")
            sys.stdout = _null
            sys.stderr = _null
            return
        # Si hay consola: garantizar UTF-8 para evitar UnicodeEncodeError
        buf = getattr(sys.stdout, "buffer", None)
        if buf is not None and not getattr(buf, "closed", False):
            enc = getattr(sys.stdout, "encoding", "").lower()
            if enc not in ("utf-8", "utf_8"):
                sys.stdout = io.TextIOWrapper(buf, encoding="utf-8", errors="replace")
    except Exception:
        pass

_fijar_streams()


# ---------------------------------------------------------------------------
# PARAMETROS DE CONEXION
# Valores por defecto. Se sobreescriben automaticamente al cargar
# gestion_eventos_db.cfg (ver bloque de sincronizacion al final del modulo).
# ---------------------------------------------------------------------------
DB_CONFIG: dict = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "gestion_eventos",
    "user":     "postgres",
    "password": "17",
    "options":  "-c search_path=public",
}


# ---------------------------------------------------------------------------
# SINCRONIZACION CON config_conexion_backend.py
# Se ejecuta una sola vez al importar el modulo.
# ---------------------------------------------------------------------------
def _sincronizar_con_cfg_guardada() -> None:
    """
    Lee gestion_eventos_db.cfg (si existe) y actualiza DB_CONFIG.
    Luego registra un observer para que futuros cambios desde la UI
    se apliquen automaticamente en tiempo de ejecucion.
    """
    try:
        import config_conexion_backend as cfg_bk

        # 1. Cargar config actual del archivo
        cfg_guardada = cfg_bk.cargar_config()
        DB_CONFIG.update({
            k: cfg_guardada[k]
            for k in ("host", "port", "dbname", "user", "password")
            if k in cfg_guardada
        })

        # 2. Registrarse como observer: cuando la UI guarde cambios,
        #    DB_CONFIG se actualiza automaticamente sin reiniciar.
        def _on_config_change(nueva_cfg: dict) -> None:
            DB_CONFIG.update({
                k: nueva_cfg[k]
                for k in ("host", "port", "dbname", "user", "password")
                if k in nueva_cfg
            })

        cfg_bk.registrar_observer(_on_config_change)

    except ImportError:
        # config_conexion_backend no disponible -> usar DB_CONFIG con defaults
        pass
    except Exception:
        pass  # error inesperado -> no romper la importacion del modulo


# Ejecutar sincronizacion al importar el modulo
_sincronizar_con_cfg_guardada()


# ---------------------------------------------------------------------------
# FUNCION: obtener conexion simple (filas como tuplas)
# ---------------------------------------------------------------------------
def get_conexion():
    """
    Retorna una conexion activa a la base de datos.
    Usa siempre los valores actuales de DB_CONFIG (se actualiza
    automaticamente si la UI cambia la configuracion).

    Uso:
        conn = get_conexion()
        cur  = conn.cursor()
        cur.execute("SELECT * FROM paciente LIMIT 5")
        filas = cur.fetchall()   # lista de tuplas
        conn.close()
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except OperationalError as e:
        print(f"[ERROR] No se pudo conectar a la base de datos:\n  {e}")
        raise


# ---------------------------------------------------------------------------
# FUNCION: obtener conexion con cursor de diccionario
# Retorna filas como dicts {columna: valor} en lugar de tuplas.
# ---------------------------------------------------------------------------
def get_conexion_dict():
    """
    Retorna una conexion cuyo cursor devuelve filas como diccionarios.

    Uso:
        conn = get_conexion_dict()
        cur  = conn.cursor()
        cur.execute("SELECT * FROM paciente LIMIT 5")
        for fila in cur.fetchall():
            print(fila["primer_nombre"], fila["primer_apellido"])
        conn.close()
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        return conn
    except OperationalError as e:
        print(f"[ERROR] No se pudo conectar a la base de datos:\n  {e}")
        raise


# ---------------------------------------------------------------------------
# CLASE: Gestor de contexto (recomendado)
# Cierra la conexion y hace commit/rollback automaticamente.
# ---------------------------------------------------------------------------
class Conexion:
    """
    Gestor de contexto para manejo seguro de conexiones.

    Uso recomendado:
        with Conexion() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM eps")
            resultados = cur.fetchall()
        # la conexion se cierra y hace commit automaticamente

    Con diccionarios:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            cur.execute("SELECT nombre, nit FROM eps LIMIT 3")
            for fila in cur.fetchall():
                print(fila["nombre"], fila["nit"])

    Manejo de transacciones:
        try:
            with Conexion() as conn:
                cur = conn.cursor()
                cur.execute("INSERT INTO evento ...")
                # si lanza excepcion -> rollback automatico
        except Exception as e:
            print(f"Error: {e}")
    """

    def __init__(self, dict_cursor: bool = False):
        self.dict_cursor = dict_cursor
        self.conn = None

    def __enter__(self):
        if self.dict_cursor:
            self.conn = get_conexion_dict()
        else:
            self.conn = get_conexion()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type is None:
                self.conn.commit()    # confirmar si no hubo error
            else:
                self.conn.rollback()  # revertir si hubo excepcion
            self.conn.close()
        return False  # no suprimir la excepcion


# ---------------------------------------------------------------------------
# FUNCION: probar conexion (verificacion rapida en consola)
# ---------------------------------------------------------------------------
def probar_conexion() -> bool:
    """
    Verifica que la conexion funcione e imprime informacion de diagnostico.
    Retorna True si la conexion es exitosa, False en caso contrario.
    """
    try:
        with Conexion() as conn:
            cur = conn.cursor()
            cur.execute("SELECT version(), current_database(), current_user;")
            version, base_datos, usuario = cur.fetchone()
            print("=" * 60)
            print("  [OK] Conexion exitosa a PostgreSQL")
            print(f"  Base de datos : {base_datos}")
            print(f"  Host          : {DB_CONFIG['host']}:{DB_CONFIG['port']}")
            print(f"  Usuario       : {usuario}")
            print(f"  Version       : {version.split(',')[0]}")
            print("=" * 60)
            return True
    except Exception as e:
        print(f"  [ERROR] No se pudo conectar: {e}")
        print(f"  Host    : {DB_CONFIG.get('host')}:{DB_CONFIG.get('port')}")
        print(f"  Base BD : {DB_CONFIG.get('dbname')}")
        print(f"  Usuario : {DB_CONFIG.get('user')}")
        print(
            "  Tip: Ejecuta la app y configura la conexion desde "
            "Ajustes > Configuracion de base de datos"
        )
        return False


# ---------------------------------------------------------------------------
# FUNCION: llamar funcion RPC almacenada en PostgreSQL
# ---------------------------------------------------------------------------
def llamar_rpc(nombre_funcion: str, **kwargs):
    """
    Llama a una funcion almacenada (RPC) de PostgreSQL y retorna el resultado.

    Ejemplos:
        resultado = llamar_rpc("rpc_dashboard", p_entidad_id=1)
        pacientes = llamar_rpc("buscar_pacientes", p_entidad_id=1, p_texto="garcia")
        resumen   = llamar_rpc("resumen_facturacion",
                               p_entidad_id=1,
                               p_fecha_desde="2024-01-01",
                               p_fecha_hasta="2024-12-31")
        stats     = llamar_rpc("stats_sistema")
    """
    try:
        with Conexion(dict_cursor=True) as conn:
            cur = conn.cursor()
            params_sql = ", ".join(f"{k}=%({k})s" for k in kwargs)
            query = f"SELECT * FROM public.{nombre_funcion}({params_sql})"
            cur.execute(query, kwargs)
            return cur.fetchall()
    except Exception as e:
        print(f"[ERROR] Al llamar RPC '{nombre_funcion}': {e}")
        raise


# ---------------------------------------------------------------------------
# PUNTO DE ENTRADA: prueba directa del modulo
# ---------------------------------------------------------------------------
if __name__ == "__main__":

    # 1. Verificar conexion
    if not probar_conexion():
        sys.exit(1)

    print()

    # 2. Listar tipos de documento
    print("Tipos de documento registrados:")
    print("-" * 40)
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT abreviatura, nombre
            FROM   public.tipo_documento
            WHERE  activo = TRUE
            ORDER  BY abreviatura
        """)
        for fila in cur.fetchall():
            print(f"  {fila['abreviatura']:6}  {fila['nombre']}")

    print()

    # 3. Listar estados de evento
    print("Estados de evento:")
    print("-" * 40)
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, nombre FROM public.estado_evento ORDER BY id")
        for fila in cur.fetchall():
            print(f"  {fila['id']}  {fila['nombre']}")

    print()

    # 4. Stats del sistema via RPC
    print("Estadisticas del sistema:")
    print("-" * 40)
    try:
        resultado = llamar_rpc("stats_sistema")
        if resultado:
            stats = resultado[0]
            if hasattr(stats, "items"):
                for clave, valor in stats.items():
                    print(f"  {clave:<35} {valor}")
    except Exception as e:
        print(f"  No se pudo obtener estadisticas: {e}")