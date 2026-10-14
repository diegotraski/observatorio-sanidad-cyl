"""
Asistente "Pregúntale a los datos": convierte una pregunta en español en una
consulta SQL, la ejecuta de forma segura sobre la base de datos y redacta la
respuesta.

Flujo:
  1. El modelo de lenguaje (Gemini, de Google, en su plan gratuito) recibe el esquema de la base
     de datos (tablas, columnas, tipos y 3 filas de ejemplo) y la pregunta, y
     devuelve SOLO una consulta SQL.
  2. La consulta pasa por tres capas de seguridad antes de tocar los datos:
       a) validar_sql(): un único SELECT, sin palabras prohibidas.
       b) La base de datos se abre en modo SOLO LECTURA (?mode=ro).
       c) Un "autorizador" de SQLite rechaza cualquier operación que no sea leer.
     Además, el resultado se limita a 500 filas.
  3. Si la consulta falla, se le devuelve el error al modelo UNA vez para que
     la corrija. Si vuelve a fallar, se muestra un mensaje amable.
  4. El modelo redacta una respuesta corta en español a partir de los resultados.

La clave de API se lee de la variable de entorno GEMINI_API_KEY (fichero
.env en local, st.secrets en Streamlit Cloud). Nunca se escribe en el código.
El modelo se elige con ASISTENTE_MODELO (por defecto, un modelo Flash del plan
gratuito de la API de Gemini).
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
RUTA_BD = RAIZ / "data" / "sanidad_cyl.db"

MODELO = os.getenv("ASISTENTE_MODELO", "gemini-3.8-flash")
LIMITE_FILAS = 500

# Palabras que nunca pueden aparecer en la consulta (fuera de textos entre comillas)
PALABRAS_PROHIBIDAS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "ATTACH", "DETACH",
    "PRAGMA", "VACUUM", "REINDEX", "TRUNCATE", "GRANT", "REVOKE", "BEGIN", "COMMIT",
    "ROLLBACK", "SAVEPOINT", "LOAD_EXTENSION",
]


class SQLNoPermitida(ValueError):
    """La consulta generada no supera las comprobaciones de seguridad."""


# ---------------------------------------------------------------------------
# Seguridad
# ---------------------------------------------------------------------------

def limpiar_respuesta_sql(texto: str) -> str:
    """Quita el envoltorio ```sql ... ``` si el modelo lo añade, y espacios sobrantes."""
    bloque = re.search(r"```(?:sql)?\s*(.*?)```", texto, re.DOTALL | re.IGNORECASE)
    if bloque:
        texto = bloque.group(1)
    return texto.strip()


def validar_sql(sql: str) -> str:
    """Comprueba que `sql` es una única consulta de lectura y la devuelve limpia.

    Reglas:
      - No vacía.
      - Una sola sentencia: se admite un ';' final, pero no varios.
      - Empieza por SELECT o WITH (para las consultas con subconsultas con nombre).
      - No contiene palabras de escritura o administración (INSERT, DROP, PRAGMA...).
    Lanza SQLNoPermitida si algo no se cumple.
    """
    # Quitar comentarios (-- hasta fin de línea y /* ... */)
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL).strip()
    if not sql:
        raise SQLNoPermitida("La consulta está vacía.")

    sql = sql.rstrip().rstrip(";").strip()
    # Los textos entre comillas no cuentan (por ejemplo, un nombre que contenga "Update")
    sin_textos = re.sub(r"'(?:[^']|'')*'", "''", sql)

    if ";" in sin_textos:
        raise SQLNoPermitida("Solo se permite una sentencia SQL.")
    if not re.match(r"^\s*(SELECT|WITH)\b", sin_textos, re.IGNORECASE):
        raise SQLNoPermitida("Solo se permiten consultas SELECT.")
    for palabra in PALABRAS_PROHIBIDAS:
        if re.search(rf"\b{palabra}\b", sin_textos, re.IGNORECASE):
            raise SQLNoPermitida(f"La consulta contiene una operación no permitida: {palabra}.")
    return sql


def _autorizador(accion: int, *_args) -> int:
    """Autorizador de SQLite: solo permite leer (SELECT, leer columnas y funciones)."""
    permitidas = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    # SQLITE_RECURSIVE (33) aparece con WITH RECURSIVE; no escribe nada
    permitidas.add(getattr(sqlite3, "SQLITE_RECURSIVE", 33))
    return sqlite3.SQLITE_OK if accion in permitidas else sqlite3.SQLITE_DENY


def conectar_solo_lectura(ruta_bd: Path = RUTA_BD, autorizador: bool = True) -> sqlite3.Connection:
    """Abre la base de datos en modo solo lectura y, por defecto, con el autorizador activado.

    El autorizador solo se desactiva para el código propio de confianza
    (describir_esquema necesita PRAGMA), nunca para las consultas del modelo.
    """
    con = sqlite3.connect(f"file:{ruta_bd.as_posix()}?mode=ro", uri=True)
    if autorizador:
        con.set_authorizer(_autorizador)
    return con


def ejecutar_consulta(sql: str, ruta_bd: Path = RUTA_BD) -> pd.DataFrame:
    """Valida y ejecuta la consulta, devolviendo como mucho LIMITE_FILAS filas."""
    sql = validar_sql(sql)
    # Envolver la consulta garantiza el límite aunque el modelo no ponga LIMIT
    limitada = f"SELECT * FROM (\n{sql}\n) LIMIT {LIMITE_FILAS}"
    con = conectar_solo_lectura(ruta_bd)
    try:
        return pd.read_sql(limitada, con)
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Esquema para el modelo
# ---------------------------------------------------------------------------

def describir_esquema(ruta_bd: Path = RUTA_BD, filas_ejemplo: int = 3) -> str:
    """Describe tablas y vistas (columnas, tipos y filas de ejemplo) en texto plano."""
    con = conectar_solo_lectura(ruta_bd, autorizador=False)  # código propio: usa PRAGMA
    try:
        objetos = con.execute(
            "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') "
            "ORDER BY type DESC, name").fetchall()
        partes = []
        for nombre, tipo in objetos:
            columnas = con.execute(f"SELECT * FROM {nombre} LIMIT 0").description
            ejemplo = pd.read_sql(f"SELECT * FROM {nombre} LIMIT {filas_ejemplo}", con)
            tipos = pd.read_sql(
                f"SELECT name, type FROM pragma_table_info('{nombre}')", con)
            tipo_de = dict(zip(tipos["name"], tipos["type"]))
            cols = ", ".join(f"{c[0]} {tipo_de.get(c[0]) or ''}".strip() for c in columnas)
            partes.append(f"{'TABLA' if tipo == 'table' else 'VISTA'} {nombre}({cols})\n"
                          f"Ejemplo:\n{ejemplo.to_string(index=False)}")
        return "\n\n".join(partes)
    finally:
        con.close()


INSTRUCCIONES = """Eres un analista de datos que traduce preguntas en español a SQL para SQLite.

La base de datos contiene datos públicos reales de listas de espera de los 14 hospitales
públicos de Sacyl (Castilla y León), por trimestre, y la población del INE.

Contexto importante:
- Las fechas son texto 'AAAA-MM-DD' y corresponden al último día de cada trimestre
  (31-mar, 30-jun, 30-sep, 31-dic). El dato más reciente es MAX(fecha).
- "Lista de espera", "pacientes en espera" sin más detalle se refiere a la lista
  QUIRÚRGICA y a pacientes_estructurales (la cifra oficial). "Demora" es demora_media_dias.
- La lista quirúrgica NO tiene cruce hospital × especialidad. Para preguntas de un hospital
  y una especialidad concretos usa consultas_externas / v_consultas_detalle (primeras
  consultas con el especialista) y dilo en la respuesta.
- Prefiere las vistas (v_...), que ya traen los nombres unidos.
- Para buscar nombres usa LIKE con comodines y sin depender de tildes cuando haya duda,
  por ejemplo especialidad LIKE '%Traumatolog%'.
- Si la pregunta no indica fecha, usa el último corte disponible.
- Las provincias son: Ávila, Burgos, León, Palencia, Salamanca, Segovia, Soria, Valladolid, Zamora.

Responde SOLO con una consulta SQL (un único SELECT, puede empezar por WITH), sin
explicaciones y sin texto adicional. Pon alias claros en español a las columnas calculadas.

ESQUEMA DE LA BASE DE DATOS:
"""


# ---------------------------------------------------------------------------
# Llamadas al modelo
# ---------------------------------------------------------------------------

def _llamar(cliente, instrucciones: str, mensaje: str, razonamiento: str) -> str:
    """Hace una llamada al modelo y devuelve el texto de la respuesta.

    Usa la API "Interactions" del SDK google-genai: `system_instruction` lleva
    las instrucciones fijas (y el esquema) e `input` la pregunta concreta.
    `thinking_level` regula cuánto "piensa" el modelo antes de responder:
    más para escribir SQL, menos para redactar la respuesta.
    """
    respuesta = cliente.interactions.create(
        model=MODELO,
        system_instruction=instrucciones,
        input=mensaje,
        generation_config={"thinking_level": razonamiento},
    )
    texto = (respuesta.output_text or "").strip()
    if not texto:
        raise RuntimeError("El modelo no ha devuelto ninguna respuesta.")
    return texto


def generar_sql(cliente, esquema: str, pregunta: str,
                sql_fallida: str | None = None, error: str | None = None) -> str:
    """Pide al modelo la consulta SQL. Si se pasa un error, le pide que la corrija."""
    mensaje = f"Pregunta: {pregunta}"
    if error:
        mensaje += (f"\n\nEsta consulta anterior falló:\n{sql_fallida}\n\nError: {error}\n\n"
                    "Corrígela y devuelve solo la consulta SQL corregida.")
    return limpiar_respuesta_sql(_llamar(cliente, INSTRUCCIONES + esquema, mensaje,
                                         razonamiento="medium"))


def redactar_respuesta(cliente, pregunta: str, sql: str, datos: pd.DataFrame) -> str:
    """Pide al modelo una respuesta breve en español basada SOLO en los resultados."""
    instrucciones = (
        "Eres un analista de datos sanitarios. Respondes en español, en 2-4 frases claras, "
        "a partir EXCLUSIVAMENTE de los resultados de la consulta que se te dan. "
        "No inventes cifras. Usa separador de miles con punto y redondea las demoras a días "
        "enteros. Si los resultados están vacíos, dilo. Si los datos proceden de consultas "
        "externas y no de la lista quirúrgica, acláralo. No uses encabezados ni listas.")
    muestra = datos.head(50).to_string(index=False) if not datos.empty else "(sin resultados)"
    mensaje = (f"Pregunta: {pregunta}\n\nConsulta SQL usada:\n{sql}\n\n"
               f"Resultados ({len(datos)} filas, se muestran hasta 50):\n{muestra}")
    return _llamar(cliente, instrucciones, mensaje, razonamiento="low")


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

@dataclass
class Resultado:
    """Lo que el dashboard necesita mostrar tras una pregunta."""
    pregunta: str
    sql: str | None = None
    datos: pd.DataFrame = field(default_factory=pd.DataFrame)
    respuesta: str | None = None
    error: str | None = None
    intentos: int = 0


def crear_cliente(clave: str | None = None):
    """Crea el cliente de la API de Gemini. Devuelve None si no hay clave."""
    clave = clave or os.getenv("GEMINI_API_KEY")
    if not clave:
        return None
    from google import genai  # importación aquí: el resto del proyecto funciona sin el paquete
    return genai.Client(api_key=clave)


def responder(pregunta: str, cliente, esquema: str | None = None,
              ruta_bd: Path = RUTA_BD) -> Resultado:
    """Responde a una pregunta: genera SQL, la ejecuta (con un reintento) y redacta."""
    resultado = Resultado(pregunta=pregunta)
    esquema = esquema or describir_esquema(ruta_bd)
    sql, error = None, None

    for intento in (1, 2):  # un intento y, si falla, un único reintento
        resultado.intentos = intento
        try:
            sql = generar_sql(cliente, esquema, pregunta, sql_fallida=sql, error=error)
            resultado.sql = sql
            resultado.datos = ejecutar_consulta(sql, ruta_bd)
            error = None
            break
        except (SQLNoPermitida, sqlite3.Error, pd.errors.DatabaseError) as e:
            error = str(e)

    if error:
        resultado.error = ("No he podido responder a esa pregunta con los datos disponibles. "
                           "Prueba a formularla de otra manera, por ejemplo indicando la "
                           f"provincia, el hospital o la especialidad. (Detalle técnico: {error})")
        return resultado

    resultado.respuesta = redactar_respuesta(cliente, pregunta, resultado.sql, resultado.datos)
    return resultado


if __name__ == "__main__":
    # Prueba rápida desde la terminal: python src/asistente.py "tu pregunta"
    import sys

    from dotenv import load_dotenv

    load_dotenv(RAIZ / ".env")
    cliente = crear_cliente()
    if cliente is None:
        sys.exit("Falta GEMINI_API_KEY en el fichero .env")
    r = responder(" ".join(sys.argv[1:]) or "¿Qué provincia tiene más demora quirúrgica?", cliente)
    print(r.sql, "\n", r.datos.head(10), "\n", r.respuesta or r.error)
