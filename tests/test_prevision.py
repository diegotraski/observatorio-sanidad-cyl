"""Tests del módulo de previsión."""

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import prevision  # noqa: E402

RUTA_BD = Path(__file__).resolve().parent.parent / "data" / "sanidad_cyl.db"


def test_metricas_de_error():
    real = np.array([100.0, 200.0])
    previsto = np.array([110.0, 180.0])
    assert prevision.mae(real, previsto) == 15.0
    assert prevision.mape(real, previsto) == 10.0  # (10 % + 10 %) / 2


def test_modelos_de_referencia():
    serie = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
                      index=pd.date_range("2020-03-31", periods=8, freq="QE-DEC"))
    assert prevision.ultimo_valor(serie, 2)["prevision"].tolist() == [8.0, 8.0]
    assert prevision.estacional_ingenuo(serie, 4)["prevision"].tolist() == [5.0, 6.0, 7.0, 8.0]
    assert prevision.media_movil_4(serie, 1)["prevision"].tolist() == [6.5]


def test_series_sin_huecos_y_con_10_ambitos():
    series = prevision.cargar_series()
    assert len(series) == 10  # Castilla y León + 9 provincias
    for serie in series.values():
        assert serie.isna().sum() == 0
        assert serie.index.freqstr == "QE-DEC"


def test_prevision_guardada_y_coherente():
    with sqlite3.connect(RUTA_BD) as con:
        df = pd.read_sql("SELECT * FROM prevision", con)
    assert len(df) == 10 * prevision.HORIZONTE
    assert (df["prevision"] >= 0).all()
    assert (df["inferior"] <= df["prevision"]).all()
    assert (df["prevision"] <= df["superior"]).all()


def test_un_modelo_elegido_por_ambito():
    with sqlite3.connect(RUTA_BD) as con:
        ev = pd.read_sql("SELECT * FROM prevision_evaluacion", con)
    assert ev.groupby("ambito")["elegido"].sum().eq(1).all()
