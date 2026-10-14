"""
Estilo visual común para los gráficos de Plotly (notebook y dashboard).

La paleta se ha comprobado con un validador de accesibilidad: los tres
colores principales se distinguen entre sí también con daltonismo
(protanopia, deuteranopia, tritanopia) y contrastan con el fondo.
"""

import plotly.graph_objects as go
import plotly.io as pio

# Colores con significado fijo en todo el proyecto
PRINCIPAL = "#009688"   # verde azulado sanitario: la serie principal (Castilla y León)
DESTACADO = "#e8590c"   # naranja: el elemento que queremos resaltar (p. ej. Burgos)
TERCERO = "#3b5bdb"     # añil: un tercer elemento de comparación
CONTEXTO = "#b4b2ab"    # gris: el resto de elementos, como contexto
INTERVALO = "rgba(0, 150, 136, 0.18)"  # banda de incertidumbre de la previsión

TEXTO = "#1f2a30"
TEXTO_SECUNDARIO = "#5b6770"
REJILLA = "#e6e8e6"
FONDO = "#ffffff"

plantilla = go.layout.Template(
    layout=dict(
        font=dict(family="Inter, Segoe UI, Arial, sans-serif", size=13, color=TEXTO),
        title=dict(font=dict(size=17, color=TEXTO), x=0, xanchor="left"),
        paper_bgcolor=FONDO,
        plot_bgcolor=FONDO,
        colorway=[PRINCIPAL, DESTACADO, TERCERO],
        xaxis=dict(showgrid=False, linecolor=REJILLA, ticks="outside", tickcolor=REJILLA,
                   title_font=dict(color=TEXTO_SECUNDARIO)),
        yaxis=dict(gridcolor=REJILLA, zeroline=False, title_font=dict(color=TEXTO_SECUNDARIO)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    title_text=""),
        hoverlabel=dict(bgcolor="white", font_size=13),
        margin=dict(l=10, r=10, t=70, b=10),
        hovermode="x unified",
    ),
    data=dict(
        scatter=[go.Scatter(line=dict(width=2.5), marker=dict(size=8))],
        bar=[go.Bar(marker=dict(line=dict(width=0)))],
    ),
)

pio.templates["observatorio"] = plantilla
pio.templates.default = "observatorio"
