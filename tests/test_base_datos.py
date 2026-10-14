"""Tests de la base de datos SQLite (se ejecutan con: pytest)."""

import sqlite3
from datetime import date
from pathlib import Path

import pytest

RUTA_BD = Path(__file__).resolve().parent.parent / "data" / "sanidad_cyl.db"

TABLAS = [
    "provincias", "poblacion", "hospitales", "especialidades",
    "lista_espera_quirurgica_hospital", "lista_espera_quirurgica_especialidad",
    "lista_espera_quirurgica_region", "consultas_externas",
]
TABLAS_CON_FECHA = [t for t in TABLAS if t not in ("provincias", "hospitales", "especialidades")]
TABLAS_CON_DEMORA = [
    "lista_espera_quirurgica_hospital", "lista_espera_quirurgica_especialidad",
    "lista_espera_quirurgica_region", "consultas_externas",
]


@pytest.fixture(scope="module")
def con():
    """Conexión de solo lectura a la base de datos."""
    assert RUTA_BD.exists(), "La base de datos no existe: ejecuta python ejecutar_todo.py"
    conexion = sqlite3.connect(f"file:{RUTA_BD.as_posix()}?mode=ro", uri=True)
    yield conexion
    conexion.close()


def test_base_de_datos_existe():
    assert RUTA_BD.exists()


@pytest.mark.parametrize("tabla", TABLAS)
def test_tablas_tienen_filas(con, tabla):
    n = con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
    assert n > 0, f"{tabla} está vacía"


@pytest.mark.parametrize("tabla", TABLAS_CON_DEMORA)
def test_no_hay_demoras_negativas(con, tabla):
    n = con.execute(f"SELECT COUNT(*) FROM {tabla} WHERE demora_media_dias < 0").fetchone()[0]
    assert n == 0


@pytest.mark.parametrize("tabla", TABLAS_CON_DEMORA)
def test_no_hay_pacientes_negativos(con, tabla):
    n = con.execute(
        f"SELECT COUNT(*) FROM {tabla} WHERE pacientes_total < 0 OR pacientes_estructurales < 0"
    ).fetchone()[0]
    assert n == 0


@pytest.mark.parametrize("tabla", TABLAS_CON_FECHA)
def test_no_hay_fechas_futuras(con, tabla):
    hoy = date.today().isoformat()
    n = con.execute(f"SELECT COUNT(*) FROM {tabla} WHERE fecha > ?", (hoy,)).fetchone()[0]
    assert n == 0


@pytest.mark.parametrize("tabla", TABLAS_CON_FECHA)
def test_fechas_tienen_formato_valido(con, tabla):
    # date(x) devuelve NULL si x no es una fecha válida 'AAAA-MM-DD'
    n = con.execute(f"SELECT COUNT(*) FROM {tabla} WHERE date(fecha) IS NULL").fetchone()[0]
    assert n == 0


def test_claves_foraneas_coherentes(con):
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []


def test_hospitales_tienen_provincia_valida(con):
    huerfanos = con.execute("""
        SELECT COUNT(*) FROM hospitales h
        LEFT JOIN provincias p ON p.provincia_id = h.provincia_id
        WHERE p.provincia_id IS NULL
    """).fetchone()[0]
    assert huerfanos == 0


def test_suma_hospitales_igual_a_total_regional(con):
    """La suma de los 14 hospitales debe coincidir con el total publicado por Sacyl."""
    diferencias = con.execute("""
        SELECT r.fecha, r.pacientes_total, SUM(h.pacientes_total)
        FROM lista_espera_quirurgica_region r
        JOIN lista_espera_quirurgica_hospital h ON h.fecha = r.fecha
        GROUP BY r.fecha
        HAVING r.pacientes_total <> SUM(h.pacientes_total)
    """).fetchall()
    assert diferencias == []


def test_total_es_suma_de_sus_componentes(con):
    """Total = estructurales + no programables + rechazo de centro alternativo."""
    n = con.execute("""
        SELECT COUNT(*) FROM lista_espera_quirurgica_hospital
        WHERE pacientes_total <> pacientes_estructurales + pacientes_no_programables
                                 + pacientes_rechazo_centro_alternativo
    """).fetchone()[0]
    assert n == 0


def test_vista_provincia_tiene_las_9_provincias(con):
    n = con.execute("SELECT COUNT(DISTINCT provincia) FROM v_quirurgica_provincia").fetchone()[0]
    assert n == 9


def test_vista_provincia_tiene_poblacion_para_todos_los_cortes(con):
    n = con.execute("SELECT COUNT(*) FROM v_quirurgica_provincia WHERE habitantes IS NULL").fetchone()[0]
    assert n == 0
