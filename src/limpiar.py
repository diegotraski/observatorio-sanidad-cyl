"""
Limpieza y normalización de los datos crudos (data/raw) -> data/processed.

Genera estos ficheros CSV, en formato "largo" (una fila por observación):
  - quirurgica_hospital.csv      Lista de espera quirúrgica por hospital y trimestre
  - quirurgica_especialidad.csv  Lista de espera quirúrgica por especialidad (toda CyL)
  - quirurgica_region.csv        Total de Castilla y León por trimestre
  - consultas_externas.csv       Primeras consultas externas por hospital × especialidad
  - poblacion.csv                Población residente por provincia y fecha (INE)
  - hospitales.csv / especialidades.csv / provincias.csv  Tablas maestras

Uso:
    python src/limpiar.py
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
DIR_RAW = RAIZ / "data" / "raw"
DIR_PROCESADO = RAIZ / "data" / "processed"

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}


# ---------------------------------------------------------------------------
# Diccionarios de normalización
# ---------------------------------------------------------------------------
# Cada fuente escribe los nombres a su manera ("CA Avila" en un fichero,
# "CA Ávila" en otro; "TRAUMATOLOGÍA" frente a "TRAUMATOLOGÍA Y CIRUGÍA
# ORTOPÉDICA"...). Para unificarlos, primero se pasa cada texto por clave():
# mayúsculas, sin tildes y sin puntos ni espacios repetidos. Después se busca
# esa clave en estos diccionarios, que dan el nombre oficial.
# Si aparece un nombre nuevo que no está aquí, el script se detiene con un
# error, en lugar de inventar una equivalencia.

def clave(texto: str) -> str:
    """Convierte un texto a una forma comparable: MAYÚSCULAS, sin tildes ni puntos."""
    sin_tildes = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    sin_puntos = sin_tildes.upper().replace(".", " ")
    return re.sub(r"\s+", " ", sin_puntos).strip()


# clave del nombre en los Excel -> nombre corto oficial del hospital
MAPA_HOSPITALES = {
    "CA AVILA": "CA Ávila",
    "CAU BURGOS": "CAU Burgos",
    "H SANTIAGO APOSTOL": "H. Santiago Apóstol",
    "H SANTOS REYES": "H. Santos Reyes",
    "H BIERZO": "H. El Bierzo",
    "H EL BIERZO": "H. El Bierzo",
    "CAU LEON": "CAU León",
    "CAU PALENCIA": "CAU Palencia",
    "CAU SALAMANCA": "CAU Salamanca",
    "CA SEGOVIA": "CA Segovia",
    "CA SORIA": "CA Soria",
    "H UNIVERSITARIO RIO HORTEGA": "H.U. Río Hortega",
    "HURH VALLADOLID": "H.U. Río Hortega",
    "H MEDINA DEL CAMPO": "H. Medina del Campo",
    "H CLINICO UNIVERSITARIO DE VALLADOLID": "H. Clínico Universitario de Valladolid",
    "HCU VALLADOLID": "H. Clínico Universitario de Valladolid",
    "CA ZAMORA": "CA Zamora",
}

# Columnas que son el total regional, no un hospital
TOTALES_REGION = {"TOTAL C Y L", "CASTILLA Y LEON"}

# Datos fijos de cada hospital: nombre completo, área de salud y provincia.
# Fuente: mapa sanitario de Sacyl (11 áreas de salud, 14 hospitales públicos).
HOSPITALES = [
    # (nombre_corto, nombre_completo, area_salud, provincia, localidad)
    ("CA Ávila", "Complejo Asistencial de Ávila", "Ávila", "Ávila", "Ávila"),
    ("CAU Burgos", "Complejo Asistencial Universitario de Burgos", "Burgos", "Burgos", "Burgos"),
    ("H. Santiago Apóstol", "Hospital Santiago Apóstol", "Burgos", "Burgos", "Miranda de Ebro"),
    ("H. Santos Reyes", "Hospital Santos Reyes", "Burgos", "Burgos", "Aranda de Duero"),
    ("H. El Bierzo", "Hospital El Bierzo", "El Bierzo", "León", "Ponferrada"),
    ("CAU León", "Complejo Asistencial Universitario de León", "León", "León", "León"),
    ("CAU Palencia", "Complejo Asistencial Universitario de Palencia", "Palencia", "Palencia", "Palencia"),
    ("CAU Salamanca", "Complejo Asistencial Universitario de Salamanca", "Salamanca", "Salamanca", "Salamanca"),
    ("CA Segovia", "Complejo Asistencial de Segovia", "Segovia", "Segovia", "Segovia"),
    ("CA Soria", "Complejo Asistencial de Soria", "Soria", "Soria", "Soria"),
    ("H.U. Río Hortega", "Hospital Universitario Río Hortega", "Valladolid Oeste", "Valladolid", "Valladolid"),
    ("H. Medina del Campo", "Hospital de Medina del Campo", "Valladolid Oeste", "Valladolid", "Medina del Campo"),
    ("H. Clínico Universitario de Valladolid", "Hospital Clínico Universitario de Valladolid", "Valladolid Este", "Valladolid", "Valladolid"),
    ("CA Zamora", "Complejo Asistencial de Zamora", "Zamora", "Zamora", "Zamora"),
]

# clave del nombre en los Excel -> nombre oficial de la especialidad
MAPA_ESPECIALIDADES = {
    "ALERGOLOGIA": "Alergología",
    "ANESTESIA Y REANIMACION": "Anestesiología y Reanimación",
    "ANGIOLOGIA Y CIRUGIA VASCULAR": "Angiología y Cirugía Vascular",
    "CARDIOLOGIA": "Cardiología",
    "CIRUGIA CARDIACA": "Cirugía Cardiaca",
    "CIRUGIA GENERAL Y DIGESTIVO": "Cirugía General y Digestiva",
    "CIRUGIA GENERAL Y DIGESTIVA": "Cirugía General y Digestiva",
    "CIRUGIA MAXILOFACIAL": "Cirugía Oral y Maxilofacial",
    "CIRUGIA PEDIATRICA": "Cirugía Pediátrica",
    "CIRUGIA PLASTICA": "Cirugía Plástica y Reparadora",
    "CIRUGIA PLASTICA Y REPARADORA": "Cirugía Plástica y Reparadora",
    "CIRUGIA TORACICA": "Cirugía Torácica",
    "DERMATOLOGIA": "Dermatología",
    "DIGESTIVO": "Aparato Digestivo",
    "ENDOCRINOLOGIA": "Endocrinología",
    "GERIATRIA": "Geriatría",
    "GINECOLOGIA": "Ginecología",
    "HEMATOLOGIA": "Hematología",
    "MEDICINA INTERNA": "Medicina Interna",
    "MEDICINA PREVENTIVA": "Medicina Preventiva",
    "NEFROLOGIA": "Nefrología",
    "NEUROFISIOLOGIA CLINICA": "Neurofisiología Clínica",
    "NEUMOLOGIA": "Neumología",
    "NEUROCIRUGIA": "Neurocirugía",
    "NEUROLOGIA": "Neurología",
    "OBSTETRICIA": "Obstetricia",
    "OFTALMOLOGIA": "Oftalmología",
    "ONCOLOGIA MEDICA": "Oncología Médica",
    "ONCOLOGIA RADIOTERAPICA": "Oncología Radioterápica",
    "OTORRINOLARINGOLOGIA": "Otorrinolaringología",
    "PEDIATRIA": "Pediatría",
    "PSIQUIATRIA": "Psiquiatría",
    "REHABILITACION": "Rehabilitación",
    "REUMATOLOGIA": "Reumatología",
    "TRAUMATOLOGIA": "Traumatología y Cirugía Ortopédica",
    "TRAUMATOLOGIA Y CIRUGIA ORTOPEDICA": "Traumatología y Cirugía Ortopédica",
    "UROLOGIA": "Urología",
}

# Nombre de provincia en el INE (clave) -> nombre oficial
MAPA_PROVINCIAS = {
    "AVILA": "Ávila", "BURGOS": "Burgos", "LEON": "León", "PALENCIA": "Palencia",
    "SALAMANCA": "Salamanca", "SEGOVIA": "Segovia", "SORIA": "Soria",
    "VALLADOLID": "Valladolid", "ZAMORA": "Zamora",
}


def normalizar(texto: str, mapa: dict[str, str], tipo: str) -> str:
    """Devuelve el nombre oficial de `texto` según `mapa`, o lanza un error si no está."""
    k = clave(texto)
    if k not in mapa:
        raise KeyError(f"{tipo} desconocido: {texto!r} (clave {k!r}). Añádelo al diccionario.")
    return mapa[k]


# ---------------------------------------------------------------------------
# Utilidades de lectura
# ---------------------------------------------------------------------------

def fecha_desde_texto(texto: str) -> date:
    """Extrae la fecha de un texto del tipo '30 de Septiembre de 2019' o '31 DE MARZO de 2021'."""
    m = re.search(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+(?:de\s+)?(\d{4})", str(texto), re.IGNORECASE)
    if not m:
        raise ValueError(f"No encuentro una fecha en: {texto!r}")
    return date(int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1)))


def a_numero(valor, guion_es_cero: bool) -> float:
    """Convierte una celda a número.

    En los Excel de Sacyl el guion '-' significa "no hay pacientes". Para los
    recuentos eso es un 0; para las demoras es un nulo (no existe la media de
    un grupo vacío). Las celdas vacías, con espacios o con '_' son nulos.
    """
    if isinstance(valor, str):
        valor = valor.strip()
        if valor == "-":
            return 0.0 if guion_es_cero else float("nan")
        if valor in ("", "_"):
            return float("nan")
        return float(valor.replace(",", "."))
    if valor is None or pd.isna(valor):
        return float("nan")
    return float(valor)


# ---------------------------------------------------------------------------
# Lista de espera quirúrgica
# ---------------------------------------------------------------------------

# Etiqueta de cada fila en el Excel (en forma clave) -> columna final
FILAS_QUIRURGICA = {
    "NUMERO DE PACIENTES PENDIENTES DE INTERVENCION QUIRURGICA (IQ)": "pacientes_total",
    "NUMERO DE PACIENTES EN ESPERA ESTRUCTURAL": "pacientes_estructurales",
    "NUMERO DE PACIENTES TRANSITORIAMENTE NO PROGRAMABLES": "pacientes_no_programables",
    "NUMERO DE PACIENTES EN ESPERA TRAS RECHAZO DE CENTRO ALTERNATIVO": "pacientes_rechazo_centro_alternativo",
    "TIEMPO MEDIO DE ESPERA DE LOS PACIENTES EN ESPERA ESTRUCTURAL": "demora_media_dias",
    "TIEMPO MEDIO DE ESPERA DE LOS PACIENTES EN ESPERA TRAS RECHAZO DE CENTRO ALTERNATIVO": "demora_media_rechazo_dias",
}
COLUMNAS_DEMORA = {"demora_media_dias", "demora_media_rechazo_dias"}


def leer_bloque_quirurgica(hoja: pd.DataFrame, fila_inicio: int, fila_fin: int) -> pd.DataFrame:
    """Lee un bloque (por hospitales o por especialidades) de una hoja quirúrgica.

    El bloque empieza con una fila de título, que trae la fecha en la columna 3,
    seguida de una fila con los nombres de las columnas (hospitales o
    especialidades) y de las filas de indicadores. Las filas se reconocen por
    su etiqueta, no por su posición, porque algunos años tienen una fila menos.
    """
    fecha = fecha_desde_texto(hoja.iloc[fila_inicio, 3])
    # La fila de cabecera es la primera, tras el título, con texto en la columna 3
    fila_cabecera = next(
        r for r in range(fila_inicio + 1, fila_fin) if isinstance(hoja.iloc[r, 3], str)
    )
    nombres = hoja.iloc[fila_cabecera, 3:].tolist()

    registros = []
    for r in range(fila_cabecera + 1, fila_fin):
        columna = FILAS_QUIRURGICA.get(clave(hoja.iloc[r, 1]))
        if columna is None:
            continue  # fila de título ("DEMORA MEDIA"), vacía o nota al pie
        for nombre, valor in zip(nombres, hoja.iloc[r, 3:].tolist()):
            if pd.isna(nombre):
                continue
            registros.append({
                "fecha": fecha,
                "nombre": nombre,
                "indicador": columna,
                "valor": a_numero(valor, guion_es_cero=columna not in COLUMNAS_DEMORA),
            })
    largo = pd.DataFrame(registros)
    # Pasamos de una fila por indicador a una columna por indicador
    ancho = largo.pivot_table(index=["fecha", "nombre"], columns="indicador",
                              values="valor", aggfunc="first", dropna=False).reset_index()
    ancho.columns.name = None
    return ancho


def leer_quirurgica() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lee todos los Excel quirúrgicos. Devuelve (bloque hospitales, bloque especialidades).

    Se leen todas las hojas, también la del año anterior que traen algunos
    ficheros: así se recupera el corte de diciembre de 2018. Los cortes que
    aparecen repetidos en varios ficheros se eliminan después.
    """
    hospitales, especialidades = [], []
    for fichero in sorted((DIR_RAW / "quirurgica").glob("*.xlsx")):
        for nombre_hoja in pd.ExcelFile(fichero).sheet_names:
            hoja = pd.read_excel(fichero, sheet_name=nombre_hoja, header=None)
            etiquetas = hoja.iloc[:, 1].map(clave)
            ini_hosp = etiquetas[etiquetas.str.contains("POR HOSPITALES")].index[0]
            ini_esp = etiquetas[etiquetas.str.contains("POR ESPECIALIDADES")].index[0]
            for df, destino in [
                (leer_bloque_quirurgica(hoja, ini_hosp, ini_esp), hospitales),
                (leer_bloque_quirurgica(hoja, ini_esp, len(hoja)), especialidades),
            ]:
                df["fichero_origen"] = f"{fichero.name}:{nombre_hoja}"
                destino.append(df)
    return pd.concat(hospitales, ignore_index=True), pd.concat(especialidades, ignore_index=True)


def quitar_duplicados(df: pd.DataFrame, claves: list[str], nombre: str) -> pd.DataFrame:
    """Quita filas repetidas para las mismas claves, comprobando antes que coinciden.

    Si dos ficheros dan valores distintos para el mismo corte, se queda el
    del fichero más reciente (la última publicación de Sacyl) y se avisa.
    """
    columnas_valor = [c for c in df.columns if c not in claves + ["fichero_origen"]]
    repetidas = df[df.duplicated(claves, keep=False)]
    discrepancias = (
        repetidas.groupby(claves)[columnas_valor]
        .nunique(dropna=False).gt(1).any(axis=1).sum()
    )
    df = df.sort_values("fichero_origen")
    sin_duplicados = df.drop_duplicates(claves, keep="last")
    quitadas = len(df) - len(sin_duplicados)
    print(f"   {nombre}: {quitadas} filas duplicadas eliminadas "
          f"({discrepancias} grupos con valores distintos entre ficheros)")
    return sin_duplicados.drop(columns="fichero_origen").reset_index(drop=True)


ORDEN_QUIRURGICA = [
    "pacientes_total", "pacientes_estructurales", "pacientes_no_programables",
    "pacientes_rechazo_centro_alternativo", "demora_media_dias", "demora_media_rechazo_dias",
]


def limpiar_quirurgica() -> dict[str, pd.DataFrame]:
    """Limpia la lista de espera quirúrgica y la separa en hospital, especialidad y región."""
    print("\n== Lista de espera quirúrgica")
    bruto_hosp, bruto_esp = leer_quirurgica()

    # El total regional viene como una columna más ("TOTAL C Y L"): se separa
    es_total_h = bruto_hosp["nombre"].map(clave).isin(TOTALES_REGION)
    es_total_e = bruto_esp["nombre"].map(clave).isin(TOTALES_REGION)
    region = bruto_hosp[es_total_h].drop(columns="nombre")

    hosp = bruto_hosp[~es_total_h].copy()
    hosp["hospital"] = hosp["nombre"].map(lambda n: normalizar(n, MAPA_HOSPITALES, "Hospital"))
    esp = bruto_esp[~es_total_e].copy()
    esp["especialidad"] = esp["nombre"].map(lambda n: normalizar(n, MAPA_ESPECIALIDADES, "Especialidad"))

    hosp = quitar_duplicados(hosp.drop(columns="nombre"), ["fecha", "hospital"], "por hospital")
    esp = quitar_duplicados(esp.drop(columns="nombre"), ["fecha", "especialidad"], "por especialidad")
    region = quitar_duplicados(region, ["fecha"], "total regional")

    # Comprobación de coherencia: la suma de hospitales debe dar el total regional
    suma = hosp.groupby("fecha")["pacientes_total"].sum()
    diferencia = (suma - region.set_index("fecha")["pacientes_total"]).abs().max()
    print(f"   Máxima diferencia entre suma de hospitales y total regional: {diferencia:.0f} pacientes")

    return {
        "quirurgica_hospital": hosp[["fecha", "hospital"] + ORDEN_QUIRURGICA].sort_values(["fecha", "hospital"]),
        "quirurgica_especialidad": esp[["fecha", "especialidad"] + ORDEN_QUIRURGICA].sort_values(["fecha", "especialidad"]),
        "quirurgica_region": region[["fecha"] + ORDEN_QUIRURGICA].sort_values("fecha"),
    }


# ---------------------------------------------------------------------------
# Consultas externas
# ---------------------------------------------------------------------------

# Etiqueta de fila (clave) -> columna final
FILAS_CONSULTAS = {
    "NUMERO DE PACIENTES EN ESPERA PARA PRIMERA CONSULTA EXTERNA": "pacientes_total",
    "NUMERO DE PACIENTES EN ESPERA ESTRUCTURAL PARA PRIMERA CONSULTA EXTERNA": "pacientes_estructurales",
    "PORCENTAJE DE PACIENTES EN ESPERA ESTRUCTURAL SOBRE EL TOTAL DE PACIENTES EN ESPERA PARA UNA PRIMERA CONSULTA": "porcentaje_estructural",
    "TIEMPO MEDIO (DIAS) DE ESPERA ESTRUCTURAL PARA PRIMERAS CONSULTAS": "demora_media_dias",
}
HOJAS_NO_ESPECIALIDAD = {"TOTAL", "Pendientes"}


def limpiar_consultas() -> pd.DataFrame:
    """Lee los Excel de consultas externas (una hoja por especialidad).

    Cambio de formato detectado: hasta septiembre de 2022 cada hoja trae el
    total de pacientes y el porcentaje de estructurales, pero no el número de
    estructurales. Desde diciembre de 2022 trae también ese número. Para que
    la serie sea homogénea, en los cortes antiguos se calcula como
    total × porcentaje, redondeado a entero.
    """
    print("\n== Consultas externas")
    registros = []
    for fichero in sorted((DIR_RAW / "consultas").glob("*.xlsx")):
        for nombre_hoja in pd.ExcelFile(fichero).sheet_names:
            if nombre_hoja in HOJAS_NO_ESPECIALIDAD:
                continue
            hoja = pd.read_excel(fichero, sheet_name=nombre_hoja, header=None)
            fecha = fecha_desde_texto(hoja.iloc[0, 0])
            especialidad = normalizar(hoja.iloc[1, 0], MAPA_ESPECIALIDADES, "Especialidad")
            hospitales = hoja.iloc[1, 1:].tolist()
            valores: dict[str, list] = {}
            for r in range(2, len(hoja)):
                columna = FILAS_CONSULTAS.get(clave(hoja.iloc[r, 0]))
                if columna:
                    valores[columna] = hoja.iloc[r, 1:].tolist()
            for i, nombre in enumerate(hospitales):
                if pd.isna(nombre) or clave(nombre) in TOTALES_REGION:
                    continue  # el total regional se recalcula en SQL
                fila = {"fecha": fecha, "hospital": normalizar(nombre, MAPA_HOSPITALES, "Hospital"),
                        "especialidad": especialidad, "fichero_origen": fichero.name}
                for columna, lista in valores.items():
                    fila[columna] = a_numero(lista[i], guion_es_cero=False)
                registros.append(fila)

    df = pd.DataFrame(registros)
    # Combinaciones hospital-especialidad que no existen (el hospital no tiene
    # ese servicio): todas las medidas vacías. No son datos perdidos: se quitan.
    # En junio de 2020 Segovia y Soria rellenaron esas celdas con 0 en vez de
    # dejarlas vacías; para que todos los trimestres se traten igual, una fila
    # con 0 pacientes también se considera "sin lista de espera" y se quita.
    sin_datos = df[["pacientes_total", "demora_media_dias"]].isna().all(axis=1)
    sin_pacientes = df["pacientes_total"].fillna(0).eq(0)
    print(f"   {(sin_datos | sin_pacientes).sum()} combinaciones hospital-especialidad sin lista "
          f"de espera eliminadas ({sin_datos.sum()} vacías y {(sin_pacientes & ~sin_datos).sum()} con 0 pacientes)")
    df = df[~(sin_datos | sin_pacientes)].copy()

    # Rellenar estructurales en los cortes antiguos (ver docstring)
    calcular = df["pacientes_estructurales"].isna() & df["porcentaje_estructural"].notna()
    df.loc[calcular, "pacientes_estructurales"] = (
        df.loc[calcular, "pacientes_total"] * df.loc[calcular, "porcentaje_estructural"]
    ).round()
    print(f"   {calcular.sum()} valores de pacientes estructurales calculados como total × porcentaje")

    df = quitar_duplicados(df, ["fecha", "hospital", "especialidad"], "consultas externas")
    columnas = ["fecha", "hospital", "especialidad", "pacientes_total",
                "pacientes_estructurales", "demora_media_dias"]
    return df[columnas].sort_values(["fecha", "hospital", "especialidad"])


# ---------------------------------------------------------------------------
# Población (INE)
# ---------------------------------------------------------------------------

# Código de periodo del INE -> mes del día 1 al que se refiere la cifra
PERIODOS_INE = {19: 1, 20: 4, 21: 7, 22: 10}


def limpiar_poblacion() -> pd.DataFrame:
    """Lee los JSON del INE y devuelve la población por provincia y fecha.

    Las dos tablas se solapan en 2025. Si una fecha aparece en ambas, se usa
    la de la tabla nueva (59589), que es la vigente.
    """
    print("\n== Población (INE)")
    filas = []
    for tabla in [56945, 59589]:  # en este orden, para que la nueva quede la última
        series = json.loads((DIR_RAW / "ine" / f"poblacion_{tabla}.json").read_text(encoding="utf-8"))
        for serie in series:
            # Nombre típico: "Total. Todas las edades. Burgos. Población. Número."
            partes = [p.strip() for p in serie["Nombre"].split(".")]
            provincia = MAPA_PROVINCIAS.get(clave(partes[2])) if len(partes) > 2 else None
            if provincia is None:
                continue  # provincia de fuera de Castilla y León
            for dato in serie["Data"]:
                filas.append({
                    "fecha": date(dato["Anyo"], PERIODOS_INE[dato["FK_Periodo"]], 1),
                    "provincia": provincia,
                    "habitantes": int(dato["Valor"]),
                    "tabla": tabla,
                })
    df = pd.DataFrame(filas).sort_values("tabla")
    antes = len(df)
    df = df.drop_duplicates(["fecha", "provincia"], keep="last")
    print(f"   {antes - len(df)} filas repetidas entre las dos tablas del INE (se queda la más reciente)")
    return df.drop(columns="tabla").sort_values(["fecha", "provincia"])


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------

def tablas_maestras() -> dict[str, pd.DataFrame]:
    """Construye las tablas de provincias, hospitales y especialidades."""
    hospitales = pd.DataFrame(HOSPITALES, columns=["hospital", "nombre_completo", "area_salud",
                                                   "provincia", "localidad"])
    provincias = pd.DataFrame({"provincia": sorted(MAPA_PROVINCIAS.values())})
    especialidades = pd.DataFrame({"especialidad": sorted(set(MAPA_ESPECIALIDADES.values()))})
    return {"hospitales": hospitales, "provincias": provincias, "especialidades": especialidades}


def comprobar(tablas: dict[str, pd.DataFrame]) -> None:
    """Comprobaciones básicas de calidad antes de guardar."""
    for nombre, df in tablas.items():
        numericas = df.select_dtypes("number")
        assert (numericas.fillna(0) >= 0).all().all(), f"{nombre}: hay valores negativos"
        if "fecha" in df:
            assert pd.to_datetime(df["fecha"]).max() <= pd.Timestamp.today(), f"{nombre}: fechas futuras"


def main() -> None:
    """Ejecuta toda la limpieza y guarda los CSV en data/processed/."""
    tablas = {}
    tablas.update(limpiar_quirurgica())
    tablas["consultas_externas"] = limpiar_consultas()
    tablas["poblacion"] = limpiar_poblacion()
    tablas.update(tablas_maestras())
    comprobar(tablas)

    DIR_PROCESADO.mkdir(parents=True, exist_ok=True)
    print("\n== Guardando en data/processed/")
    for nombre, df in tablas.items():
        # Los recuentos de pacientes son enteros; Int64 admite nulos
        for col in df.columns:
            if col.startswith("pacientes_") or col == "habitantes":
                df[col] = df[col].round().astype("Int64")
            elif col.startswith("demora_"):
                df[col] = df[col].round(1)
        # lineterminator="\n" para que el CSV sea idéntico en Windows y en Linux
        df.to_csv(DIR_PROCESADO / f"{nombre}.csv", index=False, encoding="utf-8", lineterminator="\n")
        print(f"   {nombre}.csv: {len(df)} filas")


if __name__ == "__main__":
    main()
