"""
Descarga de las fuentes de datos del Observatorio en data/raw/.

Fuentes:
  1. Lista de espera quirúrgica (Sacyl, Portal de Salud de Castilla y León).
     Un Excel por trimestre con los datos por hospital y por especialidad.
  2. Lista de espera de consultas externas (Sacyl). Un Excel por trimestre con
     una hoja por especialidad y una columna por hospital.
  3. Población residente por provincia (INE, Estadística Continua de Población),
     a través de la API JSON del INE.

Uso:
    python src/descargar.py            # descarga solo lo que falta
    python src/descargar.py --forzar   # vuelve a descargarlo todo
"""

from __future__ import annotations

import argparse
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import unquote

import requests
import truststore

# El servidor de Sacyl no envía la cadena completa de certificados SSL.
# truststore hace que Python use el almacén de certificados del sistema
# operativo (como el navegador), que sí sabe completarla. Así se mantiene
# la verificación SSL activada en lugar de desactivarla (verify=False).
truststore.inject_into_ssl()

# Rutas relativas a la raíz del proyecto (la carpeta que contiene src/)
RAIZ = Path(__file__).resolve().parent.parent
DIR_RAW = RAIZ / "data" / "raw"

URL_SACYL = "https://www.saludcastillayleon.es"
URL_HISTORICO = URL_SACYL + "/es/leq-total-ce-pdt/historico"
URL_ULTIMO_CORTE = URL_SACYL + "/es/leq-total-ce-pdt"

# Cada tipo de lista tiene su sección en el histórico de Sacyl
SECCIONES_SACYL = {
    "quirurgica": "lista-espera-quirurgica-total",
    "consultas": "lista-espera-consultas-externas",
}

# Sacyl publica un corte por trimestre, siempre a final de estos meses
MESES_CORTE = {"marzo": 3, "junio": 6, "septiembre": 9, "diciembre": 12}
PRIMER_ANIO = 2019

# INE: tablas de población residente por provincia (Estadística Continua de Población).
# 56945 = serie histórica (hasta 1 de enero de 2025); 59589 = serie desde 2025.
# Los filtros tv= piden "Todas las edades" (356:15668) y "Ambos sexos" (18:451).
URL_INE = "https://servicios.ine.es/wstempus/js/ES/DATOS_TABLA/{tabla}"
TABLAS_INE = [56945, 59589]
FILTROS_INE = "?tv=356:15668&tv=18:451&date=20190101:20991231"

CABECERAS = {"User-Agent": "Mozilla/5.0 (observatorio-sanidad-cyl; proyecto educativo)"}


def pedir(url: str, intentos: int = 3, espera: float = 3.0) -> requests.Response | None:
    """Hace una petición GET con reintentos.

    Devuelve la respuesta si el servidor contesta 200, None si la página no
    existe (404) y lanza una excepción si falla tras todos los intentos.
    """
    for intento in range(1, intentos + 1):
        try:
            respuesta = requests.get(url, headers=CABECERAS, timeout=60)
            if respuesta.status_code == 404:
                return None
            respuesta.raise_for_status()
            return respuesta
        except requests.RequestException as error:
            print(f"   Intento {intento}/{intentos} fallido: {error}")
            if intento == intentos:
                raise
            time.sleep(espera * intento)  # espera un poco más en cada reintento
    return None


def guardar(destino: Path, contenido: bytes) -> None:
    """Guarda bytes en disco creando la carpeta si no existe."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)


def cortes_posibles(hoy: date | None = None) -> list[tuple[str, int, int]]:
    """Lista los cortes trimestrales (nombre_mes, mes, año) desde 2019 hasta hoy."""
    hoy = hoy or date.today()
    cortes = []
    for anio in range(PRIMER_ANIO, hoy.year + 1):
        for nombre_mes, mes in MESES_CORTE.items():
            if (anio, mes) < (hoy.year, hoy.month):
                cortes.append((nombre_mes, mes, anio))
    return cortes


def enlace_excel(html: str) -> str | None:
    """Busca en el HTML de una página de Sacyl el enlace al fichero .xlsx."""
    coincidencia = re.search(r'href="([^"]+\.ficheros/[^"]+\.xlsx?)"', html)
    return coincidencia.group(1) if coincidencia else None


def descargar_sacyl(tipo: str, forzar: bool) -> int:
    """Descarga todos los cortes trimestrales de un tipo de lista de espera.

    Recorre las páginas del histórico (una por trimestre). Si un trimestre no
    tiene página, lo indica y continúa. Devuelve el número de ficheros nuevos.
    """
    seccion = SECCIONES_SACYL[tipo]
    carpeta = DIR_RAW / tipo
    nuevos = 0
    print(f"\n== Sacyl · lista de espera {tipo}")

    for nombre_mes, mes, anio in cortes_posibles():
        destino = carpeta / f"{tipo}_{anio}_{mes:02d}.xlsx"
        if destino.exists() and not forzar:
            continue
        pagina = pedir(f"{URL_HISTORICO}/{seccion}/{nombre_mes}-{anio}")
        if pagina is None:
            print(f"   {nombre_mes} {anio}: sin página en el histórico")
            continue
        enlace = enlace_excel(pagina.text)
        if enlace is None:
            print(f"   {nombre_mes} {anio}: la página no tiene Excel")
            continue
        guardar(destino, pedir(URL_SACYL + enlace).content)
        print(f"   {nombre_mes} {anio}: descargado -> {destino.name}")
        nuevos += 1
        time.sleep(0.5)  # no saturar el servidor público

    nuevos += descargar_ultimo_corte(tipo, forzar)
    return nuevos


def descargar_ultimo_corte(tipo: str, forzar: bool) -> int:
    """Descarga el corte más reciente desde la página principal de Sacyl.

    A veces el último trimestre aparece en la portada antes que en el
    histórico. La fecha se lee del propio nombre del fichero
    (por ejemplo "...a 30 de junio de 2026.xlsx").
    """
    claves = {"quirurgica": "quir", "consultas": "consultas externas"}
    pagina = pedir(URL_ULTIMO_CORTE)
    if pagina is None:
        return 0
    for enlace in re.findall(r'href="([^"]+\.ficheros/[^"]+\.xlsx?)"', pagina.text):
        nombre = unquote(enlace).lower()
        if claves[tipo] not in nombre:
            continue
        fecha = re.search(r"de (" + "|".join(MESES_CORTE) + r") (?:de )?(\d{4})", nombre)
        if not fecha:
            continue
        mes, anio = MESES_CORTE[fecha.group(1)], int(fecha.group(2))
        destino = DIR_RAW / tipo / f"{tipo}_{anio}_{mes:02d}.xlsx"
        if destino.exists() and not forzar:
            return 0
        guardar(destino, pedir(URL_SACYL + enlace).content)
        print(f"   último corte {fecha.group(1)} {anio}: descargado -> {destino.name}")
        return 1
    return 0


def descargar_ine(forzar: bool) -> int:
    """Descarga la población residente por provincia desde la API del INE."""
    print("\n== INE · población residente por provincia")
    nuevos = 0
    for tabla in TABLAS_INE:
        destino = DIR_RAW / "ine" / f"poblacion_{tabla}.json"
        if destino.exists() and not forzar:
            continue
        respuesta = pedir(URL_INE.format(tabla=tabla) + FILTROS_INE)
        if respuesta is None:
            print(f"   Tabla {tabla}: no encontrada")
            continue
        guardar(destino, respuesta.content)
        print(f"   Tabla {tabla}: descargada -> {destino.name}")
        nuevos += 1
    return nuevos


def main(forzar: bool = False) -> None:
    """Descarga todas las fuentes y muestra un resumen."""
    total = descargar_sacyl("quirurgica", forzar)
    total += descargar_sacyl("consultas", forzar)
    total += descargar_ine(forzar)
    print(f"\nDescarga terminada: {total} ficheros nuevos en {DIR_RAW.relative_to(RAIZ)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Descarga las fuentes de datos.")
    parser.add_argument("--forzar", action="store_true", help="vuelve a descargar aunque ya existan")
    main(forzar=parser.parse_args().forzar)
