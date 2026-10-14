"""
Observatorio de la Sanidad en Castilla y León · dashboard de Streamlit.

Ejecutar en local (desde la raíz del proyecto):
    streamlit run app/dashboard.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

import asistente  # noqa: E402
import estilo  # noqa: E402  (registra la plantilla de Plotly)
from estilo import CONTEXTO, DESTACADO, INTERVALO, PRINCIPAL, TEXTO_SECUNDARIO  # noqa: E402

RUTA_BD = RAIZ / "data" / "sanidad_cyl.db"
RUTA_MAPA = RAIZ / "data" / "processed" / "provincias_cyl.geojson"

AUTOR = "Diego Trascasa García"
LINKEDIN = "https://www.linkedin.com/in/diego-trascasa-garc%C3%ADa-b171382b2/"
GITHUB = "https://github.com/diegotraski"
REPO = "https://github.com/diegotraski/observatorio-sanidad-cyl"

st.set_page_config(page_title="Observatorio de la Sanidad en CyL", page_icon="🩺",
                   # "auto": barra lateral abierta en escritorio y plegada en el móvil
                   layout="wide", initial_sidebar_state="auto")

# Pequeños ajustes de estilo: tarjetas de indicadores y textos secundarios
st.markdown("""
<style>
  [data-testid="stMetric"] {background: #f1f5f4; border-radius: 8px; padding: 12px 16px;}
  [data-testid="stMetricLabel"] p {font-size: 0.9rem; color: #5b6770;}
  .block-container {padding-top: 2rem;}
  .nota {color: #5b6770; font-size: 0.88rem;}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Datos (cacheados: cada consulta se ejecuta una sola vez por sesión del servidor)
# ---------------------------------------------------------------------------

@st.cache_data
def consultar(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Ejecuta una consulta en modo solo lectura y convierte la columna fecha."""
    con = sqlite3.connect(f"file:{RUTA_BD.as_posix()}?mode=ro", uri=True)
    try:
        df = pd.read_sql(sql, con, params=params)
    finally:
        con.close()
    if "fecha" in df:
        df["fecha"] = pd.to_datetime(df["fecha"])
    return df


@st.cache_data
def cargar_mapa() -> dict:
    """GeoJSON con el contorno de las 9 provincias."""
    return json.loads(RUTA_MAPA.read_text(encoding="utf-8"))


@st.cache_data
def esquema_asistente() -> str:
    """Descripción del esquema para el asistente (se calcula una vez)."""
    return asistente.describir_esquema(RUTA_BD)


def num(valor: float, decimales: int = 0) -> str:
    """Formato español: punto para los miles y coma para los decimales."""
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def demora_ponderada(df: pd.DataFrame) -> float:
    """Demora media ponderada por pacientes estructurales (ignora demoras nulas)."""
    validos = df.dropna(subset=["demora_media_dias"])
    if validos["pacientes_estructurales"].sum() == 0:
        return float("nan")
    return (validos["demora_media_dias"] * validos["pacientes_estructurales"]).sum() \
        / validos["pacientes_estructurales"].sum()


def grafico(fig: go.Figure, alto: int = 420) -> None:
    """Muestra un gráfico de Plotly con el alto indicado y sin barra de herramientas."""
    fig.update_layout(height=alto, margin=dict(l=10, r=20, t=60, b=40))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


hospitales = consultar("""
    SELECT h.nombre AS hospital, h.nombre_completo, h.area_salud, h.localidad, p.nombre AS provincia
    FROM hospitales h JOIN provincias p ON p.provincia_id = h.provincia_id
    ORDER BY p.nombre, h.nombre
""")
quir_hosp = consultar("SELECT * FROM v_quirurgica_hospital")
quir_prov = consultar("SELECT * FROM v_quirurgica_provincia")
quir_esp = consultar("SELECT * FROM v_quirurgica_especialidad")
region = consultar("SELECT * FROM lista_espera_quirurgica_region ORDER BY fecha")
metadatos = consultar("SELECT * FROM metadatos").set_index("clave")["valor"]
fechas = sorted(region["fecha"].dt.date.unique())


# ---------------------------------------------------------------------------
# Barra lateral: filtros
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### Filtros")
    provincias_sel = st.multiselect("Provincia", sorted(hospitales["provincia"].unique()),
                                    placeholder="Todas")
    opciones_hosp = hospitales[hospitales["provincia"].isin(provincias_sel)] if provincias_sel else hospitales
    hospitales_sel = st.multiselect("Hospital", opciones_hosp["hospital"].tolist(), placeholder="Todos")
    especialidades_sel = st.multiselect("Especialidad", sorted(quir_esp["especialidad"].unique()),
                                        placeholder="Todas")
    desde, hasta = st.select_slider(
        "Periodo (cortes trimestrales)", options=fechas, value=(fechas[0], fechas[-1]),
        format_func=lambda d: d.strftime("%m/%Y"))
    st.markdown(
        "<p class='nota'>Provincia y hospital filtran la lista por hospital. La lista quirúrgica "
        "por especialidad solo se publica para toda la comunidad; el detalle hospital × "
        "especialidad está en las consultas externas (pestaña Especialidades).</p>",
        unsafe_allow_html=True)

# Hospitales que cumplen los filtros de provincia y hospital
seleccion = hospitales.copy()
if provincias_sel:
    seleccion = seleccion[seleccion["provincia"].isin(provincias_sel)]
if hospitales_sel:
    seleccion = seleccion[seleccion["hospital"].isin(hospitales_sel)]
hay_filtro_lugar = bool(provincias_sel or hospitales_sel)

en_periodo = lambda df: df[(df["fecha"].dt.date >= desde) & (df["fecha"].dt.date <= hasta)]  # noqa: E731
qh = en_periodo(quir_hosp[quir_hosp["hospital"].isin(seleccion["hospital"])])
qp = en_periodo(quir_prov)
qe = en_periodo(quir_esp)
if especialidades_sel:
    qe = qe[qe["especialidad"].isin(especialidades_sel)]
ultima = pd.Timestamp(hasta)

# Etiqueta del ámbito seleccionado, para los títulos
if hospitales_sel:
    ambito = ", ".join(hospitales_sel) if len(hospitales_sel) <= 2 else f"{len(hospitales_sel)} hospitales"
elif provincias_sel:
    ambito = ", ".join(provincias_sel)
else:
    ambito = "Castilla y León"


# ---------------------------------------------------------------------------
# Cabecera
# ---------------------------------------------------------------------------

st.title("Observatorio de la Sanidad en Castilla y León")
st.markdown(
    f"Listas de espera de los 14 hospitales públicos de Sacyl con datos oficiales "
    f"trimestrales. **Último dato: {pd.Timestamp(metadatos['ultimo_corte']):%d/%m/%Y}.**")

pestanas = st.tabs(["Resumen", "Comparativa", "Especialidades", "Previsión",
                    "Pregúntale a los datos", "Acerca de"])


# ---------------------------------------------------------------------------
# Pestaña 1 · Resumen
# ---------------------------------------------------------------------------

with pestanas[0]:
    st.subheader(f"Lista de espera quirúrgica · {ambito}")
    serie = (qh.groupby("fecha")
             .apply(lambda g: pd.Series({
                 "pacientes_estructurales": g["pacientes_estructurales"].sum(),
                 "pacientes_total": g["pacientes_total"].sum(),
                 "demora_media_dias": demora_ponderada(g)}), include_groups=False)
             .reset_index())
    if not hay_filtro_lugar:
        # Sin filtros, la demora regional es la oficial publicada por Sacyl
        serie = serie.drop(columns="demora_media_dias").merge(
            region[["fecha", "demora_media_dias"]], on="fecha")

    if serie.empty:
        st.warning("No hay datos para los filtros elegidos.")
    else:
        actual = serie.iloc[-1]
        hace_un_anio = serie[serie["fecha"] == ultima - pd.DateOffset(years=1)]
        variacion = None
        if not hace_un_anio.empty:
            variacion = (actual["pacientes_estructurales"]
                         / hace_un_anio["pacientes_estructurales"].iloc[0] - 1) * 100
        prov_ult = qp[qp["fecha"] == ultima].sort_values("estructurales_por_10000_hab", ascending=False)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Pacientes en espera", num(actual["pacientes_estructurales"]),
                  help="Pacientes cuya espera se debe a la organización del sistema (RD 605/2003). "
                       f"Incluyendo aplazamientos y rechazos: {num(actual['pacientes_total'])}.")
        c2.metric("Demora media", f"{num(actual['demora_media_dias'])} días",
                  help="Días que llevan esperando, de media, los pacientes en espera estructural.")
        c3.metric("Variación en un año",
                  f"{variacion:+.1f} %".replace(".", ",") if variacion is not None else "—",
                  help="Pacientes en espera estructural frente al mismo trimestre del año anterior.")
        if not prov_ult.empty:
            peor = prov_ult.iloc[0]
            c4.metric("Mayor espera", peor["provincia"],
                      help="Provincia con la mayor tasa de pacientes en espera estructural por 10.000 habitantes.")
            c4.caption(f"{num(peor['estructurales_por_10000_hab'])} por 10.000 hab.")
        st.caption(f"Datos a {ultima:%d/%m/%Y}.")

        fig = go.Figure()
        fig.add_scatter(x=serie["fecha"], y=serie["pacientes_estructurales"], mode="lines+markers",
                        line_color=PRINCIPAL, name="Pacientes",
                        hovertemplate="%{x|%m/%Y}: %{y:,.0f} pacientes<extra></extra>")
        fig.update_layout(title="Evolución de los pacientes en espera estructural",
                          yaxis_title="pacientes", yaxis_rangemode="tozero", separators=",.",
                          showlegend=False)
        grafico(fig, 380)

        fig = go.Figure()
        fig.add_scatter(x=serie["fecha"], y=serie["demora_media_dias"], mode="lines+markers",
                        line_color=estilo.TERCERO, name="Demora",
                        hovertemplate="%{x|%m/%Y}: %{y:.0f} días<extra></extra>")
        fig.update_layout(title="Evolución de la demora media", yaxis_title="días",
                          yaxis_rangemode="tozero", showlegend=False)
        grafico(fig, 340)


# ---------------------------------------------------------------------------
# Pestaña 2 · Comparativa
# ---------------------------------------------------------------------------

with pestanas[1]:
    st.subheader(f"Comparativa a {ultima:%d/%m/%Y}")
    indicador = st.segmented_control(
        "Indicador", ["Pacientes por 10.000 hab.", "Demora media (días)"],
        default="Pacientes por 10.000 hab.", key="indicador_comparativa")
    columna = "estructurales_por_10000_hab" if indicador != "Demora media (días)" else "demora_media_dias"
    unidad = "por 10.000 hab." if columna != "demora_media_dias" else "días"

    prov = qp[qp["fecha"] == ultima].sort_values(columna)
    resaltadas = set(seleccion["provincia"]) if hay_filtro_lugar else set()

    col_mapa, col_barras = st.columns([1, 1])
    with col_mapa:
        fig = px.choropleth(prov, geojson=cargar_mapa(), locations="provincia",
                            featureidkey="properties.provincia", color=columna,
                            color_continuous_scale=["#e0f2f1", "#4db6ac", "#00796b", "#004d40"],
                            hover_name="provincia",
                            hover_data={columna: ":.1f", "provincia": False})
        # Nombre de cada provincia sobre el mapa (posición calculada en limpiar.py)
        etiquetas = pd.DataFrame([f["properties"] for f in cargar_mapa()["features"]])
        fig.add_scattergeo(lon=etiquetas["lon"], lat=etiquetas["lat"], text=etiquetas["provincia"],
                           mode="text",
                           # Texto blanco con halo oscuro: se lee sobre colores claros y oscuros
                           textfont=dict(size=11, color="white", shadow="0px 0px 3px #1f2a30"),
                           hoverinfo="skip", showlegend=False)
        fig.update_geos(fitbounds="locations", visible=False)
        fig.update_traces(marker_line_color="white", marker_line_width=1.5)
        fig.update_layout(title=f"Mapa por provincia ({unidad})",
                          coloraxis_colorbar=dict(title="", thickness=12, len=0.7))
        grafico(fig, 430)
    with col_barras:
        colores = [DESTACADO if p in resaltadas else PRINCIPAL for p in prov["provincia"]]
        fig = go.Figure(go.Bar(x=prov[columna], y=prov["provincia"], orientation="h",
                               marker_color=colores, text=prov[columna].round(0),
                               textposition="outside",
                               hovertemplate="%{y}: %{x:.1f} " + unidad + "<extra></extra>"))
        fig.update_layout(title=f"Provincias ordenadas ({unidad})", hovermode="closest",
                          xaxis_range=[0, prov[columna].max() * 1.18])
        grafico(fig, 430)

    st.markdown("##### Hospitales")
    hosp = quir_hosp[quir_hosp["fecha"] == ultima].copy()
    hosp_anio = quir_hosp[quir_hosp["fecha"] == ultima - pd.DateOffset(years=1)].set_index("hospital")
    hosp["variacion"] = hosp["demora_media_dias"] - hosp["hospital"].map(hosp_anio["demora_media_dias"])
    hosp = hosp.sort_values("demora_media_dias")
    destacados = set(seleccion["hospital"]) if hay_filtro_lugar else set()
    fig = go.Figure(go.Bar(
        x=hosp["demora_media_dias"], y=hosp["hospital"], orientation="h",
        marker_color=[DESTACADO if h in destacados else PRINCIPAL for h in hosp["hospital"]],
        customdata=hosp[["pacientes_estructurales", "variacion", "provincia"]],
        text=hosp["demora_media_dias"].round(0), textposition="outside",
        hovertemplate="%{y} (%{customdata[2]})<br>Demora: %{x:.1f} días<br>"
                      "Pacientes: %{customdata[0]:,.0f}<br>Cambio en un año: %{customdata[1]:+.1f} días"
                      "<extra></extra>"))
    media = region.loc[region["fecha"] == ultima, "demora_media_dias"]
    if not media.empty:
        fig.add_vline(x=media.iloc[0], line_dash="dot", line_color=TEXTO_SECUNDARIO,
                      annotation_text=f"Media CyL: {media.iloc[0]:.0f}", annotation_position="top")
    fig.update_layout(title="Demora media quirúrgica por hospital (días)", hovermode="closest",
                      xaxis_range=[0, hosp["demora_media_dias"].max() * 1.15])
    grafico(fig, 520)
    st.caption("En naranja, los elementos que coinciden con los filtros. La demora depende también "
               "de la complejidad de los casos de cada hospital: no es un ranking de calidad.")


# ---------------------------------------------------------------------------
# Pestaña 3 · Especialidades
# ---------------------------------------------------------------------------

with pestanas[2]:
    fuente = st.segmented_control(
        "Lista", ["Quirúrgica (toda CyL)", "Primeras consultas externas"],
        default="Quirúrgica (toda CyL)", key="fuente_especialidades")

    if fuente == "Primeras consultas externas":
        st.subheader(f"Consultas externas por especialidad · {ambito}")
        ce = consultar("SELECT * FROM v_consultas_detalle")
        ce = en_periodo(ce[ce["hospital"].isin(seleccion["hospital"])])
        if especialidades_sel:
            ce = ce[ce["especialidad"].isin(especialidades_sel)]
        datos = (ce.groupby(["fecha", "especialidad"])
                 .apply(lambda g: pd.Series({"pacientes": g["pacientes_total"].sum(),
                                             "demora_media_dias": demora_ponderada(g)}),
                        include_groups=False).reset_index())
        st.caption("Pacientes que esperan una primera consulta con el especialista. Aquí sí hay "
                   "detalle por hospital, así que se aplican todos los filtros.")
    else:
        st.subheader("Lista quirúrgica por especialidad · Castilla y León")
        datos = qe.rename(columns={"pacientes_estructurales": "pacientes"})
        if hay_filtro_lugar:
            st.info("Sacyl no publica la lista quirúrgica por especialidad y hospital: aquí se "
                    "muestra el total de la comunidad. Cambia a «Primeras consultas externas» "
                    "para ver el detalle de los hospitales elegidos.")

    if datos.empty:
        st.warning("No hay datos para los filtros elegidos.")
    else:
        ult = datos[datos["fecha"] == datos["fecha"].max()].sort_values("pacientes").tail(15)
        col1, col2 = st.columns([1, 1])
        with col1:
            fig = go.Figure(go.Bar(
                x=ult["pacientes"], y=ult["especialidad"], orientation="h", marker_color=PRINCIPAL,
                customdata=ult[["demora_media_dias"]],
                hovertemplate="%{y}<br>%{x:,.0f} pacientes<br>Demora: %{customdata[0]:.0f} días"
                              "<extra></extra>"))
            fig.update_layout(title=f"Ranking por pacientes ({datos['fecha'].max():%m/%Y})",
                              hovermode="closest", separators=",.")
            grafico(fig, 500)
        with col2:
            ult_d = ult.sort_values("demora_media_dias")
            fig = go.Figure(go.Bar(
                x=ult_d["demora_media_dias"], y=ult_d["especialidad"], orientation="h",
                marker_color=estilo.TERCERO,
                hovertemplate="%{y}: %{x:.0f} días<extra></extra>"))
            fig.update_layout(title="Demora media (días)", hovermode="closest")
            grafico(fig, 500)

        opciones = ult.sort_values("pacientes", ascending=False)["especialidad"].tolist()
        elegidas = st.multiselect("Especialidades a comparar en el tiempo (máx. 3)", opciones,
                                  default=opciones[:3], max_selections=3)
        medida = st.segmented_control("Medida", ["Pacientes", "Demora media (días)"],
                                      default="Pacientes", key="medida_esp")
        col = "pacientes" if medida != "Demora media (días)" else "demora_media_dias"
        evo = datos[datos["especialidad"].isin(elegidas)]
        fig = px.line(evo, x="fecha", y=col, color="especialidad", markers=True,
                      color_discrete_sequence=[PRINCIPAL, DESTACADO, estilo.TERCERO],
                      labels={col: "pacientes" if col == "pacientes" else "días", "fecha": ""})
        fig.update_layout(title="Evolución por especialidad", yaxis_rangemode="tozero",
                          separators=",.")
        grafico(fig, 420)


# ---------------------------------------------------------------------------
# Pestaña 4 · Previsión
# ---------------------------------------------------------------------------

with pestanas[3]:
    st.subheader("Previsión a 12 meses de los pacientes en espera estructural")
    prevision = consultar("SELECT * FROM prevision")
    evaluacion = consultar("SELECT * FROM prevision_evaluacion")
    ambitos = ["Castilla y León"] + sorted(a for a in prevision["ambito"].unique() if a != "Castilla y León")
    por_defecto = provincias_sel[0] if len(provincias_sel) == 1 else "Castilla y León"
    ambito_prev = st.selectbox("Ámbito", ambitos, index=ambitos.index(por_defecto))

    if ambito_prev == "Castilla y León":
        historico = region[["fecha", "pacientes_estructurales"]]
    else:
        historico = quir_prov.loc[quir_prov["provincia"] == ambito_prev, ["fecha", "pacientes_estructurales"]]
    historico = historico[historico["fecha"] >= "2019-09-30"]
    prev = prevision[prevision["ambito"] == ambito_prev]
    ultimo_real = historico.iloc[-1]
    # La línea y la banda de la previsión parten del último dato real
    enlace = pd.DataFrame({"fecha": [ultimo_real["fecha"]], **{
        c: [ultimo_real["pacientes_estructurales"]] for c in ("prevision", "inferior", "superior")}})
    prev_g = pd.concat([enlace, prev[["fecha", "prevision", "inferior", "superior"]]])

    fig = go.Figure()
    fig.add_scatter(x=list(prev_g["fecha"]) + list(prev_g["fecha"][::-1]),
                    y=list(prev_g["superior"]) + list(prev_g["inferior"][::-1]),
                    mode="lines", fill="toself", fillcolor=INTERVALO, line_width=0,
                    hoverinfo="skip", name="Intervalo del 80 %")
    fig.add_scatter(x=historico["fecha"], y=historico["pacientes_estructurales"],
                    mode="lines+markers", line_color=PRINCIPAL, name="Dato real",
                    hovertemplate="%{x|%m/%Y}: %{y:,.0f}<extra></extra>")
    fig.add_scatter(x=prev_g["fecha"], y=prev_g["prevision"], mode="lines+markers",
                    line=dict(color=PRINCIPAL, dash="dash"), name="Previsión",
                    customdata=prev_g[["inferior", "superior"]],
                    hovertemplate="%{x|%m/%Y}: %{y:,.0f} (%{customdata[0]:,.0f} – "
                                  "%{customdata[1]:,.0f})<extra></extra>")
    fig.update_layout(title=f"{ambito_prev}", yaxis_title="pacientes", yaxis_rangemode="tozero",
                      separators=",.", hovermode="closest")
    grafico(fig, 440)

    ev = evaluacion[evaluacion["ambito"] == ambito_prev].copy()
    elegido = ev.loc[ev["elegido"] == 1, "modelo"].iloc[0]
    nombres = {"ultimo_valor": "Último valor", "estacional_ingenuo": "Estacional ingenuo",
               "media_movil_4": "Media móvil 4 trimestres", "ets_holt_winters": "ETS (Holt-Winters)"}
    ev["Modelo"] = ev["modelo"].map(nombres)
    ev["Elegido"] = ev["elegido"].map({1: "✔", 0: ""})
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown(f"**Error en los 4 trimestres de prueba** (modelo elegido: {nombres[elegido]})")
        st.dataframe(ev[["Modelo", "mae", "mape", "Elegido"]].rename(
                         columns={"mae": "MAE (pacientes)", "mape": "MAPE (%)"}),
                     hide_index=True, width="stretch",
                     column_config={"MAE (pacientes)": st.column_config.NumberColumn(format="%.0f"),
                                    "MAPE (%)": st.column_config.NumberColumn(format="%.1f")})
    with col2:
        st.markdown("**Cómo leer esta previsión**")
        st.markdown(
            "- Se comparan tres modelos muy simples con un modelo ETS (Holt-Winters) y se elige el "
            "que menos se equivocó en el último año, reservado como prueba.\n"
            "- En la mayoría de provincias **ganan los modelos simples**: la serie es corta "
            "(28 trimestres) y la pandemia la distorsiona.\n"
            "- La banda es un **intervalo del 80 %**: lo razonable es que el dato real caiga dentro.\n"
            "- Es una extrapolación estadística: no conoce planes de choque, plantillas ni huelgas.")


# ---------------------------------------------------------------------------
# Pestaña 5 · Pregúntale a los datos
# ---------------------------------------------------------------------------

def clave_api() -> str | None:
    """Busca la clave de API en st.secrets (nube) o en el entorno / .env (local)."""
    try:
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:  # no existe secrets.toml en local: no es un error
        pass
    try:
        from dotenv import load_dotenv
        load_dotenv(RAIZ / ".env")
    except ImportError:
        pass
    return os.getenv("GEMINI_API_KEY") or None


def grafico_automatico(datos: pd.DataFrame) -> go.Figure | None:
    """Dibuja un gráfico si el resultado tiene una forma sencilla; si no, devuelve None.

    - Una columna de fecha y una numérica -> línea.
    - Una columna de texto y una numérica, con 2-30 filas -> barras horizontales.
    """
    if datos.empty or len(datos) < 2:
        return None
    numericas = datos.select_dtypes("number").columns.tolist()
    # Etiqueta: la primera columna de texto que distingue cada fila (descarta, por
    # ejemplo, una fecha que es igual en todas las filas)
    textos = [c for c in datos.columns if c not in numericas and datos[c].nunique() == len(datos)]
    if not numericas or not textos:
        return None
    x = textos[0]
    # Valor: la columna numérica por la que viene ordenada la tabla (la del ORDER BY);
    # si no hay ninguna ordenada, la última numérica
    ordenadas = [c for c in numericas
                 if datos[c].is_monotonic_decreasing or datos[c].is_monotonic_increasing]
    y = ordenadas[0] if ordenadas else numericas[-1]
    fechas_posibles = pd.to_datetime(datos[x], errors="coerce", format="%Y-%m-%d")
    if fechas_posibles.notna().all() and datos[x].nunique() == len(datos):
        fig = go.Figure(go.Scatter(x=fechas_posibles, y=datos[y], mode="lines+markers",
                                   line_color=PRINCIPAL))
    elif len(datos) <= 30 and datos[x].nunique() == len(datos):
        ordenado = datos.sort_values(y)
        fig = go.Figure(go.Bar(x=ordenado[y], y=ordenado[x].astype(str), orientation="h",
                               marker_color=PRINCIPAL))
    else:
        return None
    fig.update_layout(title=y.replace("_", " ").capitalize(), hovermode="closest", separators=",.")
    return fig


EJEMPLOS = [
    "¿Qué hospital de Burgos tiene más demora en traumatología?",
    "¿Qué provincia tiene más pacientes en espera quirúrgica por habitante?",
    "¿Cómo ha evolucionado la demora media quirúrgica en León desde 2022?",
    "¿Qué 5 especialidades tienen más demora en la lista quirúrgica?",
    "¿Cuántos pacientes esperan una primera consulta de dermatología en Valladolid?",
]

with pestanas[4]:
    st.subheader("Pregúntale a los datos")
    st.markdown("Escribe una pregunta en español. Un modelo de lenguaje (Gemini, de Google) la "
                "convierte en una consulta SQL, que se ejecuta **en modo solo lectura** sobre la "
                "base de datos. Verás la respuesta, los datos y la consulta usada.")
    clave = clave_api()
    if not clave:
        st.warning("El asistente no está disponible: falta la clave de API (`GEMINI_API_KEY`) "
                   "en el fichero `.env` o en los *Secrets* de Streamlit. El resto del dashboard "
                   "funciona con normalidad.")
    else:
        st.markdown("**Prueba con un ejemplo:**")
        ejemplo_elegido = None
        columnas = st.columns(len(EJEMPLOS))
        for col, ejemplo in zip(columnas, EJEMPLOS):
            if col.button(ejemplo, width="stretch"):
                ejemplo_elegido = ejemplo
                st.session_state["pregunta"] = ejemplo  # se ve en la caja de texto
        with st.form("formulario_pregunta"):
            pregunta = st.text_input("Tu pregunta", key="pregunta",
                                     placeholder="Por ejemplo: ¿qué hospital tiene menos demora?")
            enviar = st.form_submit_button("Preguntar", type="primary")

        pregunta = ejemplo_elegido or pregunta
        if (enviar or ejemplo_elegido) and pregunta.strip():
            with st.spinner("Generando la consulta y buscando en los datos…"):
                try:
                    cliente = asistente.crear_cliente(clave)
                    st.session_state["resultado"] = asistente.responder(
                        pregunta.strip(), cliente, esquema_asistente(), RUTA_BD)
                except Exception as error:  # error de red, clave inválida, límite de uso…
                    st.session_state["resultado"] = asistente.Resultado(
                        pregunta=pregunta, error="El servicio del modelo de lenguaje no está "
                        f"disponible en este momento. Inténtalo de nuevo más tarde. ({type(error).__name__})")

        resultado = st.session_state.get("resultado")
        if resultado:
            st.markdown(f"#### {resultado.pregunta}")
            if resultado.error:
                st.error(resultado.error)
            else:
                st.success(resultado.respuesta)
                figura = grafico_automatico(resultado.datos)
                if figura is not None:
                    grafico(figura, 380)
                st.dataframe(resultado.datos, hide_index=True, width="stretch")
                if len(resultado.datos) == asistente.LIMITE_FILAS:
                    st.caption(f"Se muestran como máximo {asistente.LIMITE_FILAS} filas.")
            if resultado.sql:
                with st.expander("Ver la consulta SQL utilizada"):
                    st.code(resultado.sql, language="sql")
                    if resultado.intentos > 1:
                        st.caption("La primera consulta falló y el modelo la corrigió en un segundo intento.")
        st.caption("Las respuestas las genera un modelo de lenguaje y pueden contener errores: "
                   "revisa siempre la tabla y la consulta.")


# ---------------------------------------------------------------------------
# Pestaña 6 · Acerca de
# ---------------------------------------------------------------------------

with pestanas[5]:
    st.subheader("Acerca de este proyecto")
    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown(f"""
**Qué es.** Un observatorio con datos públicos reales de las listas de espera de la sanidad
pública de Castilla y León. Incluye análisis exploratorio, una previsión a 12 meses y un
asistente que responde a preguntas en lenguaje natural convirtiéndolas en SQL.

**Fuentes de datos**
- [Lista de espera quirúrgica](https://www.saludcastillayleon.es/es/leq-total-ce-pdt/historico/lista-espera-quirurgica-total) y
  [consultas externas](https://www.saludcastillayleon.es/es/leq-total-ce-pdt/historico/lista-espera-consultas-externas):
  Portal de Salud de la Junta de Castilla y León (Sacyl). Reutilización permitida citando la fuente.
- [Estadística Continua de Población](https://www.ine.es/dynt3/inebase/es/index.htm?padre=10358):
  INE, tablas 56945 y 59589. Reutilización libre citando la fuente.
- [Mapa de zonas básicas de salud](https://analisis.datosabiertos.jcyl.es/explore/dataset/mapas-de-areas-de-salud-de-castilla-y-leon/):
  Datos Abiertos de la Junta de Castilla y León (CC BY 4.0).

**Actualización.** Último corte de datos: **{pd.Timestamp(metadatos['ultimo_corte']):%d/%m/%Y}**.
Base de datos generada el {pd.Timestamp(metadatos['fecha_generacion']):%d/%m/%Y}.
Sacyl publica un corte por trimestre.

**Metodología**
1. `descargar.py` localiza y descarga los Excel trimestrales de Sacyl (desde 2019) y la población del INE.
2. `limpiar.py` normaliza los nombres de hospitales y especialidades con diccionarios explícitos,
   elimina los duplicados (comprobando que eran idénticos) y verifica que la suma de los
   hospitales coincide con el total regional.
3. `base_datos.py` crea una base de datos SQLite con claves, índices y vistas, incluida la tasa
   por 10.000 habitantes.
4. `prevision.py` compara modelos simples con un ETS (Holt-Winters) y elige por error en la prueba.
5. El asistente valida que la consulta generada sea un único `SELECT` y la ejecuta en solo lectura.

**Conceptos.** *Espera estructural*: pacientes que esperan por causas atribuibles al sistema
(RD 605/2003). *Demora media*: días que llevan esperando, de media, en la fecha del corte.
""")
    with col2:
        st.markdown(f"""
**Autor**

{AUTOR}
Ingeniero de la Salud (Universidad de Burgos)
IBM Data Analyst Professional Certificate

- [LinkedIn]({LINKEDIN})
- [GitHub]({GITHUB})
- [Código del proyecto]({REPO})

**Tecnologías.** Python, pandas, SQLite/SQL, Plotly, Streamlit, statsmodels y la API de Gemini.

**Limitaciones.** Los datos son agregados por trimestre, sin el cruce hospital × especialidad
en la lista quirúrgica. La demora media depende de la complejidad de los casos y no mide la calidad.
""")
