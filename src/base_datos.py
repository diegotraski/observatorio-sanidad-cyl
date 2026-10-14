"""
Creación de la base de datos SQLite data/sanidad_cyl.db a partir de data/processed/.

Esquema (modelo en estrella sencillo):

    provincias ──< hospitales ──< lista_espera_quirurgica_hospital
        │               └───────< consultas_externas >── especialidades
        └──< poblacion                                       │
                          lista_espera_quirurgica_especialidad >┘
                          lista_espera_quirurgica_region

Uso:
    python src/base_datos.py
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
DIR_PROCESADO = RAIZ / "data" / "processed"
RUTA_BD = RAIZ / "data" / "sanidad_cyl.db"

# ---------------------------------------------------------------------------
# Esquema
# ---------------------------------------------------------------------------
# SQLite no tiene un tipo DATE propio: las fechas se guardan como texto
# 'AAAA-MM-DD', que se ordena bien y funciona con las funciones date() de SQLite.

ESQUEMA = """
CREATE TABLE provincias (
    provincia_id   INTEGER PRIMARY KEY,
    nombre         TEXT NOT NULL UNIQUE
);

CREATE TABLE poblacion (
    provincia_id   INTEGER NOT NULL REFERENCES provincias(provincia_id),
    fecha          DATE    NOT NULL,
    habitantes     INTEGER NOT NULL CHECK (habitantes > 0),
    PRIMARY KEY (provincia_id, fecha)
);

CREATE TABLE hospitales (
    hospital_id     INTEGER PRIMARY KEY,
    nombre          TEXT NOT NULL UNIQUE,
    nombre_completo TEXT NOT NULL,
    area_salud      TEXT NOT NULL,
    localidad       TEXT NOT NULL,
    provincia_id    INTEGER NOT NULL REFERENCES provincias(provincia_id)
);

CREATE TABLE especialidades (
    especialidad_id INTEGER PRIMARY KEY,
    nombre          TEXT NOT NULL UNIQUE
);

CREATE TABLE lista_espera_quirurgica_hospital (
    fecha                                DATE    NOT NULL,
    hospital_id                          INTEGER NOT NULL REFERENCES hospitales(hospital_id),
    pacientes_total                      INTEGER CHECK (pacientes_total >= 0),
    pacientes_estructurales              INTEGER CHECK (pacientes_estructurales >= 0),
    pacientes_no_programables            INTEGER CHECK (pacientes_no_programables >= 0),
    pacientes_rechazo_centro_alternativo INTEGER CHECK (pacientes_rechazo_centro_alternativo >= 0),
    demora_media_dias                    REAL    CHECK (demora_media_dias >= 0),
    demora_media_rechazo_dias            REAL    CHECK (demora_media_rechazo_dias >= 0),
    PRIMARY KEY (fecha, hospital_id)
);

CREATE TABLE lista_espera_quirurgica_especialidad (
    fecha                                DATE    NOT NULL,
    especialidad_id                      INTEGER NOT NULL REFERENCES especialidades(especialidad_id),
    pacientes_total                      INTEGER CHECK (pacientes_total >= 0),
    pacientes_estructurales              INTEGER CHECK (pacientes_estructurales >= 0),
    pacientes_no_programables            INTEGER CHECK (pacientes_no_programables >= 0),
    pacientes_rechazo_centro_alternativo INTEGER CHECK (pacientes_rechazo_centro_alternativo >= 0),
    demora_media_dias                    REAL    CHECK (demora_media_dias >= 0),
    demora_media_rechazo_dias            REAL    CHECK (demora_media_rechazo_dias >= 0),
    PRIMARY KEY (fecha, especialidad_id)
);

CREATE TABLE lista_espera_quirurgica_region (
    fecha                                DATE PRIMARY KEY,
    pacientes_total                      INTEGER CHECK (pacientes_total >= 0),
    pacientes_estructurales              INTEGER CHECK (pacientes_estructurales >= 0),
    pacientes_no_programables            INTEGER CHECK (pacientes_no_programables >= 0),
    pacientes_rechazo_centro_alternativo INTEGER CHECK (pacientes_rechazo_centro_alternativo >= 0),
    demora_media_dias                    REAL    CHECK (demora_media_dias >= 0),
    demora_media_rechazo_dias            REAL    CHECK (demora_media_rechazo_dias >= 0)
);

CREATE TABLE consultas_externas (
    fecha                   DATE    NOT NULL,
    hospital_id             INTEGER NOT NULL REFERENCES hospitales(hospital_id),
    especialidad_id         INTEGER NOT NULL REFERENCES especialidades(especialidad_id),
    pacientes_total         INTEGER CHECK (pacientes_total >= 0),
    pacientes_estructurales INTEGER CHECK (pacientes_estructurales >= 0),
    demora_media_dias       REAL    CHECK (demora_media_dias >= 0),
    PRIMARY KEY (fecha, hospital_id, especialidad_id)
);

-- Índices en las columnas por las que más se filtra.
-- (Las claves primarias ya crean un índice que empieza por fecha.)
CREATE INDEX idx_leq_hospital_hospital ON lista_espera_quirurgica_hospital(hospital_id);
CREATE INDEX idx_leq_especialidad_esp  ON lista_espera_quirurgica_especialidad(especialidad_id);
CREATE INDEX idx_consultas_hospital    ON consultas_externas(hospital_id);
CREATE INDEX idx_consultas_especialidad ON consultas_externas(especialidad_id);
CREATE INDEX idx_hospitales_provincia  ON hospitales(provincia_id);
"""

VISTAS = """
-- Lista quirúrgica por hospital con los nombres ya unidos (cómoda para consultar)
CREATE VIEW v_quirurgica_hospital AS
SELECT l.fecha,
       h.nombre       AS hospital,
       h.area_salud,
       p.nombre       AS provincia,
       l.pacientes_total,
       l.pacientes_estructurales,
       l.pacientes_no_programables,
       l.pacientes_rechazo_centro_alternativo,
       l.demora_media_dias,
       l.demora_media_rechazo_dias
FROM lista_espera_quirurgica_hospital l
JOIN hospitales h ON h.hospital_id = l.hospital_id
JOIN provincias p ON p.provincia_id = h.provincia_id;

-- Lista quirúrgica por especialidad (total de Castilla y León)
CREATE VIEW v_quirurgica_especialidad AS
SELECT l.fecha,
       e.nombre AS especialidad,
       l.pacientes_total,
       l.pacientes_estructurales,
       l.pacientes_no_programables,
       l.pacientes_rechazo_centro_alternativo,
       l.demora_media_dias,
       l.demora_media_rechazo_dias
FROM lista_espera_quirurgica_especialidad l
JOIN especialidades e ON e.especialidad_id = l.especialidad_id;

-- Lista quirúrgica por provincia y trimestre, con tasa por 10.000 habitantes.
-- La demora provincial es la media de los hospitales PONDERADA por sus
-- pacientes estructurales (un hospital con más pacientes pesa más).
-- La población es la cifra del INE más reciente en la fecha de corte
-- (por ejemplo, para el corte del 31-mar se usa la del 1-abr o la anterior).
CREATE VIEW v_quirurgica_provincia AS
WITH agregado AS (
    SELECT l.fecha,
           h.provincia_id,
           SUM(l.pacientes_total)          AS pacientes_total,
           SUM(l.pacientes_estructurales)  AS pacientes_estructurales,
           SUM(l.demora_media_dias * l.pacientes_estructurales)
             / SUM(CASE WHEN l.demora_media_dias IS NOT NULL THEN l.pacientes_estructurales END)
                                           AS demora_media_dias
    FROM lista_espera_quirurgica_hospital l
    JOIN hospitales h ON h.hospital_id = l.hospital_id
    GROUP BY l.fecha, h.provincia_id
),
con_poblacion AS (
    SELECT a.*,
           (SELECT po.habitantes
              FROM poblacion po
             WHERE po.provincia_id = a.provincia_id
               AND po.fecha <= date(a.fecha, '+1 day')
             ORDER BY po.fecha DESC
             LIMIT 1) AS habitantes
    FROM agregado a
)
SELECT c.fecha,
       p.nombre AS provincia,
       c.pacientes_total,
       c.pacientes_estructurales,
       ROUND(c.demora_media_dias, 1) AS demora_media_dias,
       c.habitantes,
       ROUND(c.pacientes_estructurales * 10000.0 / c.habitantes, 1) AS estructurales_por_10000_hab
FROM con_poblacion c
JOIN provincias p ON p.provincia_id = c.provincia_id;

-- Consultas externas con todos los nombres unidos
CREATE VIEW v_consultas_detalle AS
SELECT c.fecha,
       h.nombre AS hospital,
       h.area_salud,
       p.nombre AS provincia,
       e.nombre AS especialidad,
       c.pacientes_total,
       c.pacientes_estructurales,
       c.demora_media_dias
FROM consultas_externas c
JOIN hospitales h     ON h.hospital_id = c.hospital_id
JOIN provincias p     ON p.provincia_id = h.provincia_id
JOIN especialidades e ON e.especialidad_id = c.especialidad_id;
"""


def leer(nombre: str) -> pd.DataFrame:
    """Lee un CSV de data/processed/."""
    return pd.read_csv(DIR_PROCESADO / f"{nombre}.csv")


def construir_maestras(con: sqlite3.Connection) -> tuple[dict, dict, dict]:
    """Inserta provincias, hospitales y especialidades. Devuelve los mapas nombre -> id."""
    provincias = leer("provincias")
    provincias["provincia_id"] = range(1, len(provincias) + 1)
    provincias = provincias.rename(columns={"provincia": "nombre"})
    provincias[["provincia_id", "nombre"]].to_sql("provincias", con, if_exists="append", index=False)
    id_provincia = dict(zip(provincias["nombre"], provincias["provincia_id"]))

    hospitales = leer("hospitales")
    hospitales["hospital_id"] = range(1, len(hospitales) + 1)
    hospitales["provincia_id"] = hospitales["provincia"].map(id_provincia)
    hospitales = hospitales.rename(columns={"hospital": "nombre"})
    hospitales[["hospital_id", "nombre", "nombre_completo", "area_salud", "localidad",
                "provincia_id"]].to_sql("hospitales", con, if_exists="append", index=False)
    id_hospital = dict(zip(hospitales["nombre"], hospitales["hospital_id"]))

    especialidades = leer("especialidades")
    especialidades["especialidad_id"] = range(1, len(especialidades) + 1)
    especialidades = especialidades.rename(columns={"especialidad": "nombre"})
    especialidades[["especialidad_id", "nombre"]].to_sql("especialidades", con, if_exists="append", index=False)
    id_especialidad = dict(zip(especialidades["nombre"], especialidades["especialidad_id"]))

    return id_provincia, id_hospital, id_especialidad


def cargar_hechos(con: sqlite3.Connection, id_provincia: dict, id_hospital: dict,
                  id_especialidad: dict) -> None:
    """Inserta las tablas de datos sustituyendo los nombres por sus ids."""
    poblacion = leer("poblacion")
    poblacion["provincia_id"] = poblacion.pop("provincia").map(id_provincia)
    poblacion[["provincia_id", "fecha", "habitantes"]].to_sql("poblacion", con, if_exists="append", index=False)

    quir_hosp = leer("quirurgica_hospital")
    quir_hosp.insert(1, "hospital_id", quir_hosp.pop("hospital").map(id_hospital))
    quir_hosp.to_sql("lista_espera_quirurgica_hospital", con, if_exists="append", index=False)

    quir_esp = leer("quirurgica_especialidad")
    quir_esp.insert(1, "especialidad_id", quir_esp.pop("especialidad").map(id_especialidad))
    quir_esp.to_sql("lista_espera_quirurgica_especialidad", con, if_exists="append", index=False)

    leer("quirurgica_region").to_sql("lista_espera_quirurgica_region", con, if_exists="append", index=False)

    consultas = leer("consultas_externas")
    consultas.insert(1, "hospital_id", consultas.pop("hospital").map(id_hospital))
    consultas.insert(2, "especialidad_id", consultas.pop("especialidad").map(id_especialidad))
    consultas.to_sql("consultas_externas", con, if_exists="append", index=False)


def main() -> None:
    """Crea la base de datos desde cero (borra la anterior si existe)."""
    RUTA_BD.unlink(missing_ok=True)
    con = sqlite3.connect(RUTA_BD)
    try:
        con.execute("PRAGMA foreign_keys = ON")  # SQLite no comprueba las FK si no se activa
        con.executescript(ESQUEMA)
        ids = construir_maestras(con)
        cargar_hechos(con, *ids)
        con.executescript(VISTAS)
        # Metadatos: cuándo se generó la base de datos y cuál es el último corte
        ultimo_corte = con.execute("SELECT MAX(fecha) FROM lista_espera_quirurgica_region").fetchone()[0]
        con.execute("CREATE TABLE metadatos (clave TEXT PRIMARY KEY, valor TEXT NOT NULL)")
        con.executemany("INSERT INTO metadatos VALUES (?, ?)", [
            ("fecha_generacion", date.today().isoformat()),
            ("ultimo_corte", ultimo_corte),
        ])
        con.commit()

        # Comprobación final: ninguna clave foránea rota
        rotas = con.execute("PRAGMA foreign_key_check").fetchall()
        if rotas:
            raise RuntimeError(f"Claves foráneas rotas: {rotas[:5]}")

        print(f"\n== Base de datos creada: {RUTA_BD.relative_to(RAIZ)}")
        tablas = [t for (t,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        for tabla in tablas:
            n = con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]
            print(f"   {tabla}: {n} filas")
        con.execute("VACUUM")  # compacta el fichero (útil porque se sube al repo)
    finally:
        con.close()


if __name__ == "__main__":
    main()
