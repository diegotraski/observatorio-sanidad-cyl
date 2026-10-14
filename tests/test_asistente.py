"""Tests de seguridad del asistente de IA (no llaman a ninguna API)."""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from asistente import (  # noqa: E402
    LIMITE_FILAS, SQLNoPermitida, conectar_solo_lectura, describir_esquema,
    ejecutar_consulta, limpiar_respuesta_sql, validar_sql,
)

CONSULTAS_PELIGROSAS = [
    "DROP TABLE hospitales",
    "DELETE FROM consultas_externas",
    "INSERT INTO provincias VALUES (99, 'Madrid')",
    "UPDATE hospitales SET nombre = 'x'",
    "ATTACH DATABASE 'otra.db' AS otra",
    "PRAGMA table_info(hospitales)",
    "SELECT * FROM hospitales; DROP TABLE hospitales",
    "SELECT 1; SELECT 2",
    "CREATE TABLE t (x INT)",
    "ALTER TABLE hospitales ADD COLUMN x INT",
    "WITH x AS (SELECT 1) DELETE FROM hospitales",
    "SELECT load_extension('malicioso')",
    "VACUUM",
    "",
    "-- solo un comentario",
]

CONSULTAS_VALIDAS = [
    "SELECT * FROM hospitales",
    "select nombre from provincias;",
    "SELECT COUNT(*) AS n FROM consultas_externas WHERE fecha = '2026-06-30'",
    "WITH ult AS (SELECT MAX(fecha) AS f FROM lista_espera_quirurgica_region) "
    "SELECT * FROM lista_espera_quirurgica_region, ult WHERE fecha = ult.f",
    # Una palabra prohibida dentro de un texto entre comillas no es una orden
    "SELECT * FROM hospitales WHERE nombre = 'DROP TABLE'",
    "SELECT nombre FROM hospitales -- comentario al final",
]


@pytest.mark.parametrize("sql", CONSULTAS_PELIGROSAS)
def test_validador_rechaza_consultas_peligrosas(sql):
    with pytest.raises(SQLNoPermitida):
        validar_sql(sql)


@pytest.mark.parametrize("sql", CONSULTAS_VALIDAS)
def test_validador_acepta_select_validos(sql):
    assert validar_sql(sql)


def test_quita_envoltorio_markdown():
    assert limpiar_respuesta_sql("```sql\nSELECT 1\n```") == "SELECT 1"
    assert limpiar_respuesta_sql("  SELECT 1  ") == "SELECT 1"


def test_conexion_es_de_solo_lectura():
    """Aunque una escritura saltara el validador, SQLite la bloquearía."""
    con = conectar_solo_lectura()
    try:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("DELETE FROM hospitales")
    finally:
        con.close()


def test_ejecutar_consulta_limita_filas():
    datos = ejecutar_consulta("SELECT * FROM consultas_externas")
    assert len(datos) == LIMITE_FILAS


def test_ejecutar_consulta_devuelve_datos():
    datos = ejecutar_consulta("SELECT COUNT(*) AS n FROM hospitales")
    assert datos["n"].iloc[0] == 14


def test_esquema_incluye_tablas_y_vistas():
    esquema = describir_esquema()
    assert "TABLA hospitales" in esquema
    assert "VISTA v_quirurgica_provincia" in esquema
    assert "Ejemplo:" in esquema


def test_esquema_incluye_nombres_exactos():
    """El modelo recibe los nombres exactos para filtrar con '=' (evita que 'León' encaje con 'Palencia')."""
    esquema = describir_esquema()
    assert "VALORES EXACTOS DE PROVINCIAS" in esquema
    assert "León" in esquema and "Palencia" in esquema
    assert "VALORES EXACTOS DE HOSPITALES" in esquema
