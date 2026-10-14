"""
Previsión de la lista de espera quirúrgica (pacientes en espera estructural)
para Castilla y León y para cada provincia, a 4 trimestres (12 meses) vista.

Método:
  1. Se reservan los 4 últimos trimestres como conjunto de prueba.
  2. Se comparan tres modelos de referencia muy simples con un modelo ETS
     (suavizado exponencial con tendencia amortiguada y estacionalidad
     trimestral, la familia Holt-Winters):
       - ultimo_valor:       el próximo trimestre será igual que el último.
       - estacional_ingenuo: igual que el mismo trimestre del año anterior.
       - media_movil_4:      media de los 4 últimos trimestres.
       - ets_holt_winters:   statsmodels ETSModel(trend="add", damped, seasonal="add").
  3. Se mide el error en la prueba con MAE y MAPE.
  4. Para cada serie se elige el modelo con menor MAE. Si el ETS no gana a
     los modelos simples, se dice: no se vende un modelo complejo que no aporta.
  5. Se reentrena el modelo elegido con todos los datos y se prevén 4
     trimestres con un intervalo de predicción del 80 %.

Los resultados se guardan en la base de datos (tablas `prevision` y
`prevision_evaluacion`) y en data/processed/.

Uso:
    python src/prevision.py
"""

from __future__ import annotations

import sqlite3
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm
from statsmodels.tsa.exponential_smoothing.ets import ETSModel

RAIZ = Path(__file__).resolve().parent.parent
RUTA_BD = RAIZ / "data" / "sanidad_cyl.db"
DIR_PROCESADO = RAIZ / "data" / "processed"

INICIO_SERIE = "2019-09-30"  # desde aquí la serie trimestral no tiene huecos
TRIMESTRES_PRUEBA = 4
HORIZONTE = 4                # 4 trimestres = 12 meses
NIVEL_INTERVALO = 0.80       # intervalo de predicción del 80 %


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------

def cargar_series(ruta_bd: Path = RUTA_BD) -> dict[str, pd.Series]:
    """Devuelve las series trimestrales de pacientes estructurales.

    Claves: "Castilla y León" y el nombre de cada provincia. El índice es la
    fecha de corte con frecuencia trimestral (fin de trimestre).
    """
    with sqlite3.connect(ruta_bd) as con:
        region = pd.read_sql(
            "SELECT fecha, pacientes_estructurales FROM lista_espera_quirurgica_region", con,
            parse_dates=["fecha"])
        provincias = pd.read_sql(
            "SELECT fecha, provincia, pacientes_estructurales FROM v_quirurgica_provincia", con,
            parse_dates=["fecha"])

    series = {"Castilla y León": region.set_index("fecha")["pacientes_estructurales"]}
    for nombre, grupo in provincias.groupby("provincia"):
        series[nombre] = grupo.set_index("fecha")["pacientes_estructurales"]

    resultado = {}
    for nombre, serie in series.items():
        serie = serie.sort_index().loc[INICIO_SERIE:].astype(float)
        serie.index = pd.DatetimeIndex(serie.index).to_period("Q").to_timestamp("Q").normalize()
        serie = serie.asfreq("QE-DEC")
        assert serie.isna().sum() == 0, f"{nombre}: la serie tiene huecos"
        resultado[nombre] = serie
    return resultado


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------
# Todos reciben la serie de entrenamiento y el número de trimestres a prever,
# y devuelven un DataFrame con columnas: prevision, inferior, superior.

def _fechas_futuras(serie: pd.Series, h: int) -> pd.DatetimeIndex:
    """Fechas de los h trimestres siguientes al último de la serie."""
    return pd.date_range(serie.index[-1], periods=h + 1, freq="QE-DEC")[1:]


def _intervalo_ingenuo(serie: pd.Series, puntos: np.ndarray, h: int, paso: int) -> pd.DataFrame:
    """Intervalo para los modelos simples a partir del error histórico del método.

    Se calcula la desviación típica de los cambios entre trimestres (o entre
    años, si paso=4). La incertidumbre crece con la raíz del horizonte, como
    en un paseo aleatorio.
    """
    sigma = serie.diff(paso).dropna().std()
    z = norm.ppf(0.5 + NIVEL_INTERVALO / 2)
    pasos = np.ceil(np.arange(1, h + 1) / paso)  # cuántos "saltos" del método hay hasta h
    margen = z * sigma * np.sqrt(pasos)
    return pd.DataFrame({"prevision": puntos, "inferior": puntos - margen,
                         "superior": puntos + margen}, index=_fechas_futuras(serie, h))


def ultimo_valor(serie: pd.Series, h: int) -> pd.DataFrame:
    """Modelo de referencia: repite el último valor observado."""
    return _intervalo_ingenuo(serie, np.repeat(serie.iloc[-1], h), h, paso=1)


def estacional_ingenuo(serie: pd.Series, h: int) -> pd.DataFrame:
    """Modelo de referencia: cada trimestre igual que el mismo trimestre del año anterior."""
    puntos = np.array([serie.iloc[-4 + (i % 4)] for i in range(h)])
    return _intervalo_ingenuo(serie, puntos, h, paso=4)


def media_movil_4(serie: pd.Series, h: int) -> pd.DataFrame:
    """Modelo de referencia: la media de los últimos 4 trimestres (un año)."""
    return _intervalo_ingenuo(serie, np.repeat(serie.iloc[-4:].mean(), h), h, paso=1)


def ets_holt_winters(serie: pd.Series, h: int) -> pd.DataFrame:
    """Suavizado exponencial (ETS) con tendencia amortiguada y estacionalidad trimestral.

    - Tendencia aditiva amortiguada: sigue la dirección reciente, pero la va
      frenando, para no extrapolar una subida o bajada indefinidamente.
    - Estacionalidad aditiva de periodo 4: recoge el patrón que se repite cada año.
    El intervalo sale del propio modelo estadístico.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # avisos de convergencia habituales con series cortas
        modelo = ETSModel(serie, error="add", trend="add", damped_trend=True,
                          seasonal="add", seasonal_periods=4).fit(disp=False)
        pred = modelo.get_prediction(start=len(serie), end=len(serie) + h - 1)
        tabla = pred.summary_frame(alpha=1 - NIVEL_INTERVALO)
    return pd.DataFrame({"prevision": tabla["mean"].values,
                         "inferior": tabla["pi_lower"].values,
                         "superior": tabla["pi_upper"].values}, index=_fechas_futuras(serie, h))


MODELOS = {
    "ultimo_valor": ultimo_valor,
    "estacional_ingenuo": estacional_ingenuo,
    "media_movil_4": media_movil_4,
    "ets_holt_winters": ets_holt_winters,
}
MODELOS_REFERENCIA = ["ultimo_valor", "estacional_ingenuo", "media_movil_4"]


# ---------------------------------------------------------------------------
# Evaluación y previsión
# ---------------------------------------------------------------------------

def mae(real: np.ndarray, previsto: np.ndarray) -> float:
    """Error absoluto medio: cuántos pacientes nos equivocamos, de media."""
    return float(np.mean(np.abs(real - previsto)))


def mape(real: np.ndarray, previsto: np.ndarray) -> float:
    """Error porcentual absoluto medio: cuánto nos equivocamos, en % del valor real."""
    return float(np.mean(np.abs((real - previsto) / real)) * 100)


def evaluar(serie: pd.Series, n_prueba: int = TRIMESTRES_PRUEBA) -> pd.DataFrame:
    """Entrena con todo menos los últimos n_prueba trimestres y mide el error en ellos."""
    entrenamiento, prueba = serie.iloc[:-n_prueba], serie.iloc[-n_prueba:]
    filas = []
    for nombre, modelo in MODELOS.items():
        resultado = modelo(entrenamiento, n_prueba)
        # Cobertura: % de trimestres de prueba cuyo valor real cayó dentro del intervalo
        cobertura = ((prueba.values >= resultado["inferior"].values)
                     & (prueba.values <= resultado["superior"].values)).mean() * 100
        filas.append({"modelo": nombre,
                      "mae": mae(prueba.values, resultado["prevision"].values),
                      "mape": mape(prueba.values, resultado["prevision"].values),
                      "cobertura_intervalo_pct": cobertura})
    return pd.DataFrame(filas)


def elegir_modelo(evaluacion: pd.DataFrame) -> tuple[str, bool]:
    """Elige el modelo de menor MAE. Devuelve (modelo, si el ETS gana a todas las referencias)."""
    ganador = evaluacion.sort_values("mae").iloc[0]["modelo"]
    mejor_referencia = evaluacion[evaluacion["modelo"].isin(MODELOS_REFERENCIA)]["mae"].min()
    mae_ets = evaluacion.loc[evaluacion["modelo"] == "ets_holt_winters", "mae"].iloc[0]
    return ganador, bool(mae_ets < mejor_referencia)


def ejecutar(ruta_bd: Path = RUTA_BD) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evalúa los modelos para cada serie, elige el mejor y genera la previsión."""
    evaluaciones, previsiones = [], []
    for ambito, serie in cargar_series(ruta_bd).items():
        evaluacion = evaluar(serie)
        ganador, ets_gana = elegir_modelo(evaluacion)
        evaluacion.insert(0, "ambito", ambito)
        evaluacion["elegido"] = evaluacion["modelo"] == ganador
        evaluaciones.append(evaluacion)

        futuro = MODELOS[ganador](serie, HORIZONTE)
        # Una lista de espera no puede ser negativa
        futuro = futuro.clip(lower=0).round(0)
        futuro.index.name = "fecha"
        futuro = futuro.reset_index()
        futuro.insert(0, "ambito", ambito)
        futuro["modelo"] = ganador
        previsiones.append(futuro)

        mape_ganador = evaluacion.loc[evaluacion["elegido"], "mape"].iloc[0]
        print(f"   {ambito:<16} modelo elegido: {ganador:<19} MAPE prueba {mape_ganador:5.1f} %"
              f"   (¿ETS gana a las referencias? {'sí' if ets_gana else 'no'})")

    evaluacion = pd.concat(evaluaciones, ignore_index=True).round(2)
    prevision = pd.concat(previsiones, ignore_index=True)
    prevision["fecha"] = prevision["fecha"].dt.strftime("%Y-%m-%d")
    return evaluacion, prevision


def main() -> None:
    """Calcula la previsión y la guarda en la base de datos y en CSV."""
    print("\n== Previsión de la lista de espera quirúrgica (pacientes estructurales)")
    evaluacion, prevision = ejecutar()
    with sqlite3.connect(RUTA_BD) as con:
        evaluacion.to_sql("prevision_evaluacion", con, if_exists="replace", index=False)
        prevision.to_sql("prevision", con, if_exists="replace", index=False)
    evaluacion.to_csv(DIR_PROCESADO / "prevision_evaluacion.csv", index=False, lineterminator="\n")
    prevision.to_csv(DIR_PROCESADO / "prevision.csv", index=False, lineterminator="\n")
    print("   Guardado en las tablas prevision y prevision_evaluacion")


if __name__ == "__main__":
    main()
