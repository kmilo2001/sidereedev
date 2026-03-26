# -*- coding: utf-8 -*-
# =============================================================================
# conexion.py - Modulo de conexion a PostgreSQL
# Base de datos: gestion_eventos (Sistema de Gestion de Eventos - Sector Salud)
# =============================================================================

import sys
import io
import psycopg2
from psycopg2 import OperationalError, sql
from psycopg2.extras import RealDictCursor

# Forzar salida UTF-8 en Windows (evita UnicodeEncodeError con cp1252)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# PARÁMETROS DE CONEXIÓN
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host":     "localhost",       # servidor local
    "port":     5432,              # puerto por defecto de PostgreSQL
    "dbname":   "gestion_eventos", # nombre de la base de datos
    "user":     "postgres",        # usuario de PostgreSQL
    "password": "17",              # contraseña
    "options":  "-c search_path=public"  # esquema por defecto
}


# ---------------------------------------------------------------------------
# FUNCIÓN: obtener conexión simple
# ---------------------------------------------------------------------------
def get_conexion():
    """
    Retorna una conexión activa a la base de datos gestion_eventos.

    Uso:
        conn = get_conexion()
        cursor = conn.cursor()
        ...
        conn.close()
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except OperationalError as e:
        print(f"[ERROR] No se pudo conectar a la base de datos:\n  {e}")
        raise


# ---------------------------------------------------------------------------
# FUNCIÓN: obtener conexión con cursor de diccionario
# Retorna filas como diccionarios {columna: valor} en lugar de tuplas.
# ---------------------------------------------------------------------------
def get_conexion_dict():
    """
    Retorna una conexión cuyo cursor devuelve filas como diccionarios.

    Uso:
        conn = get_conexion_dict()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM paciente LIMIT 5")
        filas = cursor.fetchall()  # lista de dicts
        conn.close()
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        return conn
    except OperationalError as e:
        print(f"[ERROR] No se pudo conectar a la base de datos:\n  {e}")
        raise


# ---------------------------------------------------------------------------
# CLASE: Gestor de contexto (with ... as ...)
# Cierra la conexión automáticamente al salir del bloque.
# ---------------------------------------------------------------------------
class Conexion:
    """
    Gestor de contexto para manejo seguro de conexiones.

    Uso recomendado:
        with Conexion() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM eps")
            resultados = cursor.fetchall()
        # la conexión se cierra automáticamente aquí

    Con diccionarios:
        with Conexion(dict_cursor=True) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nombre, nit FROM eps LIMIT 3")
            for fila in cursor.fetchall():
                print(fila["nombre"], fila["nit"])
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
                self.conn.commit()   # confirmar cambios si no hubo error
            else:
                self.conn.rollback() # revertir si hubo excepción
            self.conn.close()
        return False  # no suprime la excepción


# ---------------------------------------------------------------------------
# FUNCIÓN: probar conexión (verificación rápida)
# ---------------------------------------------------------------------------
def probar_conexion():
    """
    Verifica que la conexión funcione correctamente.
    Imprime la versión de PostgreSQL y el nombre de la base de datos.
    """
    try:
        with Conexion() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version(), current_database(), current_user;")
            version, base_datos, usuario = cursor.fetchone()
            print("=" * 60)
            print("  [OK] Conexion exitosa a PostgreSQL")
            print(f"  Base de datos : {base_datos}")
            print(f"  Usuario       : {usuario}")
            print(f"  Version       : {version.split(',')[0]}")
            print("=" * 60)
            return True
    except Exception as e:
        print(f"  [ERROR] No se pudo conectar: {e}")
        return False


# ---------------------------------------------------------------------------
# FUNCIÓN: llamar una función RPC de la base de datos
# ---------------------------------------------------------------------------
def llamar_rpc(nombre_funcion: str, **kwargs):
    """
    Llama a una función almacenada (RPC) de PostgreSQL y retorna el resultado.

    Ejemplos:
        # Dashboard general de una entidad
        resultado = llamar_rpc("rpc_dashboard", p_entidad_id=1)

        # Buscar pacientes por texto
        pacientes = llamar_rpc("buscar_pacientes",
                               p_entidad_id=1, p_texto="garcia")

        # Resumen de facturación
        resumen = llamar_rpc("resumen_facturacion",
                             p_entidad_id=1,
                             p_fecha_desde="2024-01-01",
                             p_fecha_hasta="2024-12-31")
    """
    try:
        with Conexion(dict_cursor=True) as conn:
            cursor = conn.cursor()

            # Construir llamada: SELECT * FROM funcion(param1=%s, param2=%s, ...)
            params_sql  = ", ".join(f"{k}=%({k})s" for k in kwargs)
            query       = f"SELECT * FROM public.{nombre_funcion}({params_sql})"

            cursor.execute(query, kwargs)
            return cursor.fetchall()

    except Exception as e:
        print(f"[ERROR] Al llamar RPC '{nombre_funcion}': {e}")
        raise


# ---------------------------------------------------------------------------
# EJEMPLOS DE USO (se ejecutan solo al correr este archivo directamente)
# ---------------------------------------------------------------------------
if __name__ == "__main__":

    # 1. Verificar conexión
    if not probar_conexion():
        exit(1)

    print()

    # 2. Consulta directa de ejemplo — listar tipos de documento
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

    # 3. Consulta directa de ejemplo — estados de evento
    print("Estados de evento:")
    print("-" * 40)
    with Conexion(dict_cursor=True) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, nombre FROM public.estado_evento ORDER BY id")
        for fila in cur.fetchall():
            print(f"  {fila['id']}  {fila['nombre']}")

    print()

    # 4. Llamada RPC — stats globales del sistema
    print("Estadísticas del sistema:")
    print("-" * 40)
    resultado = llamar_rpc("stats_sistema")
    if resultado:
        stats = resultado[0]
        for clave, valor in stats.items() if hasattr(stats, "items") else []:
            print(f"  {clave:<35} {valor}")