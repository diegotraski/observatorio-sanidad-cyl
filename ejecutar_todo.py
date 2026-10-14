"""
Ejecuta el pipeline completo con un solo comando:

    descarga  ->  limpieza  ->  base de datos SQLite  ->  previsión

Uso:
    python ejecutar_todo.py            # descarga solo lo que falta
    python ejecutar_todo.py --forzar   # vuelve a descargarlo todo
"""

import argparse
import sys
import time
from pathlib import Path

# Para poder importar los módulos de src/ desde la raíz del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import base_datos  # noqa: E402
import descargar  # noqa: E402
import limpiar  # noqa: E402
import prevision  # noqa: E402


def main(forzar: bool) -> None:
    """Lanza los cuatro pasos en orden y muestra el tiempo total."""
    inicio = time.time()
    print("=" * 60, "\n PASO 1/4 · Descarga\n" + "=" * 60)
    descargar.main(forzar=forzar)
    print("=" * 60, "\n PASO 2/4 · Limpieza\n" + "=" * 60)
    limpiar.main()
    print("=" * 60, "\n PASO 3/4 · Base de datos\n" + "=" * 60)
    base_datos.main()
    print("=" * 60, "\n PASO 4/4 · Previsión\n" + "=" * 60)
    prevision.main()
    print(f"\nPipeline completado en {time.time() - inicio:.0f} segundos.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline completo del Observatorio.")
    parser.add_argument("--forzar", action="store_true", help="vuelve a descargar las fuentes")
    main(forzar=parser.parse_args().forzar)
