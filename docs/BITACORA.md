# Bitácora del proyecto

Diario de decisiones, fase a fase. Cada entrada resume qué se hizo y por qué.

## Fase 0 · Preparar el entorno

- Comprobado: git 2.55 y GitHub CLI 2.102, con sesión iniciada como `diegotraski`.
- Python no estaba instalado en el equipo.
- Creada la estructura de carpetas del proyecto e inicializado git en la rama `main`.
- `.gitignore`: excluye el entorno virtual, cachés de Python y Jupyter, el `.env` con las claves,
  y la guía personal de entrevista. (En la fase 2 se decidió subir los datos crudos: solo pesan 6,5 MB.)
- Python 3.12.10 instalado con `winget` (ámbito de usuario) y entorno virtual creado en `venv/`.

## Fase 1 · Encontrar los datos

**Candidatos revisados**

| Fuente | Conjunto | Resultado |
|---|---|---|
| Datos Abiertos JCyL (API Opendatasoft) | Búsquedas "lista de espera", "quirúrgica", "demora" | **0 resultados.** El portal no publica listas de espera. |
| Datos Abiertos JCyL | Catálogo de hospitales: hospitales y camas por provincia | Descartado: los números están mal exportados (por ejemplo `1.106` camas leído como decimal, o Burgos con "1" cama general en 2026). |
| Datos Abiertos JCyL | Urgencias hospitalarias atendidas, altas hospitalarias por diagnóstico | Reales y abiertos, pero no son listas de espera. Quedan como ampliación futura. |
| Portal de Salud de CyL (Sacyl) | **Lista de espera quirúrgica total**: un Excel por trimestre, por hospital y por especialidad | **Elegido como conjunto principal.** |
| Portal de Salud de CyL (Sacyl) | **Lista de espera de consultas externas**: un Excel por trimestre, hospital × especialidad | **Elegido como complementario 1.** |
| Portal de Salud de CyL (Sacyl) | Lista de espera de técnicas diagnósticas | Disponible, pero se deja fuera para acotar el alcance. |
| Ministerio de Sanidad (SISLE-SNS) | Listas de espera por comunidad autónoma, semestral | Solo da el total de la comunidad, sin hospitales: menos detalle que Sacyl. |
| INE · Padrón continuo (tabla 2852) | Población por provincia | Termina en 2021: el INE la sustituyó por la Estadística Continua de Población. |
| INE · Estadística Continua de Población (tablas 56945 y 59589) | Población residente por provincia, trimestral | **Elegido como complementario 2**, para calcular tasas por 10.000 habitantes. |

**Por qué estos conjuntos**

- Son datos oficiales de Sacyl y del INE, sin intermediarios.
- La serie quirúrgica es trimestral y continua desde septiembre de 2019 (más diciembre de 2018) hasta junio de 2026: unos 30 puntos.
- Tienen desglose por los 14 hospitales públicos de Sacyl y por especialidad.
- La descarga se puede automatizar: cada trimestre tiene su página en el histórico de Sacyl, y el INE tiene una API JSON.
- Licencias: el Portal de Salud permite reutilizar sus contenidos citando la fuente. El INE publica sus datos para reutilización libre citando la fuente (Licencia de uso del INE, compatible con CC BY 4.0).

**Fuentes (URL)**

- Lista de espera quirúrgica: https://www.saludcastillayleon.es/es/leq-total-ce-pdt/historico/lista-espera-quirurgica-total
- Consultas externas: https://www.saludcastillayleon.es/es/leq-total-ce-pdt/historico/lista-espera-consultas-externas
- INE, Estadística Continua de Población: https://www.ine.es/dynt3/inebase/es/index.htm?padre=10358 (API `servicios.ine.es/wstempus/js/ES/DATOS_TABLA/56945` y `.../59589`)

## Fase 2 · Descarga y limpieza

**Descarga (`src/descargar.py`)**

- Para cada trimestre, el script abre la página del histórico de Sacyl (`.../historico/<seccion>/<mes>-<año>`) y busca en ella el enlace al Excel. No hay URLs fijas escritas a mano: si Sacyl publica un trimestre nuevo, el script lo encuentra.
- Reintentos con espera creciente y mensajes por fichero. Si un fichero ya existe no se vuelve a bajar, salvo con `--forzar`.
- Problema encontrado: el servidor de Sacyl no envía la cadena completa de certificados SSL y `requests` rechazaba la conexión. **No** se desactivó la verificación (`verify=False` sería inseguro). Se usó `truststore`, que valida con el almacén de certificados del sistema, igual que el navegador.
- Junio de 2019 solo existe en PDF y marzo de 2019 no existe, así que la serie empieza en septiembre de 2019.
- Los datos crudos pesan 6,5 MB: se suben al repo, para que el proyecto siga funcionando aunque Sacyl cambie su web.

**Lo que se vio en los datos crudos**

- Son Excel `.xlsx`, sin problemas de codificación: las tildes se leen bien porque `.xlsx` es UTF-8 por dentro. Los únicos problemas de tildes estaban en la consola de Windows, no en los datos.
- **Quirúrgica:** una hoja con dos bloques, uno por hospitales y otro por especialidades. Cada indicador es una fila y cada hospital una columna. El formato es estable de 2019 a 2026, aunque algunos años tienen una fila menos. Por eso las filas se reconocen **por su etiqueta**, no por su posición.
- Varios ficheros traen una segunda hoja con el corte de diciembre del año anterior. Así se recupera **diciembre de 2018**, pero también aparecen duplicados.
- **Consultas externas:** una hoja por especialidad (33-34) con 14 hospitales en columnas. **Cambio de formato en diciembre de 2022:** se añade la fila "pacientes en espera estructural". Antes solo venían el total y el porcentaje estructural.
- Valores especiales: `-` (sin pacientes), celdas con un espacio `' '` o `'_'` (vacías) y un texto suelto (`'Fecha: 31/12/2023'`) en una celda de datos.
- **Nombres inconsistentes entre fuentes**, aunque estables dentro de cada una:
  - "CA Avila" frente a "CA Ávila".
  - "H. Universitario Rio Hortega" frente a "HURH Valladolid".
  - "CIRUGÍA GENERAL Y DIGESTIVO" frente a "…DIGESTIVA".
  - "TRAUMATOLOGÍA" frente a "TRAUMATOLOGÍA Y CIRUGÍA ORTOPÉDICA".
  - Erratas como "PEDIÁTRIA" o "CIRUGÍA PEDIATRÍCA".
- INE: la tabla antigua (56945) es semestral en 2019-2020 y trimestral desde 2021. La nueva (59589) empieza en abril de 2025.

**Decisiones de limpieza (`src/limpiar.py`)**

- **Normalización de nombres:** función `clave()` (mayúsculas, sin tildes, sin puntos) más diccionarios explícitos `MAPA_HOSPITALES` y `MAPA_ESPECIALIDADES`. Si aparece un nombre nuevo, el script **falla a propósito** en lugar de adivinar.
- **Área de salud y provincia** de cada hospital: tabla fija `HOSPITALES` (14 hospitales, 11 áreas, 9 provincias).
- El guion `-` vale **0 en los recuentos** y **nulo en las demoras**: la media de un grupo vacío no existe.
- **Duplicados:** 168 filas por hospital, 168 por especialidad y 12 regionales, todas repetidas entre la hoja principal y la de "año anterior". Antes de quitarlas se comprobó que **eran idénticas (0 discrepancias)**.
- **Comprobación de coherencia:** la suma de los 14 hospitales coincide exactamente con el total regional publicado en los 29 cortes (diferencia máxima: 0 pacientes).
- **Consultas externas:**
  - Se quitaron 3.597 combinaciones hospital × especialidad sin lista de espera: 3.422 celdas vacías y 175 con 0 pacientes. Las de 0 pacientes vienen de junio de 2020, cuando Segovia y Soria rellenaron con ceros lo que otros trimestres dejan en blanco.
  - Antes de diciembre de 2022, los pacientes estructurales se calculan como `total × porcentaje` (4.234 valores). Está documentado en el diccionario.
  - Quedan 616 demoras nulas, en casos en que Sacyl publicó el número de pacientes pero no la demora. No se rellenan: inventar una demora falsearía el análisis.
  - Hay demoras extremas reales (Rehabilitación en El Bierzo, 814 días en marzo de 2022; Neumología en Soria, ~700 días en 2021). Se mantienen y se comentan en el análisis.
- Las columnas pasan a `snake_case` sin tildes, los recuentos a enteros y las demoras se redondean a 1 decimal.
- Salida: 8 CSV en `data/processed/`. El diccionario completo está en `docs/DICCIONARIO_DATOS.md`.

## Fase 3 · Base de datos SQL

- `src/base_datos.py` crea `data/sanidad_cyl.db` (0,9 MB) desde cero con un esquema SQL escrito a mano y visible en el código.
- **Esquema en estrella:**
  - Tablas maestras: `provincias`, `hospitales` (con área de salud y FK a provincia) y `especialidades`.
  - Tablas de hechos: `lista_espera_quirurgica_hospital`, `..._especialidad`, `..._region`, `consultas_externas` y `poblacion`.
  - En los hechos se guardan ids, no nombres, para no repetir texto y evitar incoherencias.
- **Integridad:**
  - Claves primarias compuestas, como `(fecha, hospital_id)`, para que no pueda haber dos filas del mismo hospital en el mismo corte.
  - FK con `PRAGMA foreign_keys = ON`, que SQLite no aplica si no se activa, y comprobación final con `PRAGMA foreign_key_check`.
  - `CHECK` que impiden pacientes o demoras negativos.
- **Índices** en `hospital_id`, `especialidad_id` y `provincia_id`. La fecha ya está indexada porque es la primera columna de la clave primaria.
- **Vistas:**
  - `v_quirurgica_provincia`: agrega los hospitales por provincia. La demora es una **media ponderada** por los pacientes estructurales, porque una media simple daría el mismo peso a Medina del Campo que al Clínico. Se une a la población más reciente del INE en la fecha de corte para calcular la **tasa por 10.000 habitantes**.
  - `v_quirurgica_hospital`, `v_quirurgica_especialidad` y `v_consultas_detalle`: los hechos con los nombres ya unidos. Hacen más fáciles las consultas del dashboard y del asistente de IA.
- **Por qué SQLite:** es un único fichero, no necesita servidor, viene con Python y se puede subir al repo para que Streamlit Cloud lo use tal cual. Para menos de un millón de filas es más que suficiente.
- `ejecutar_todo.py` lanza descarga → limpieza → base de datos con un solo comando.
- **Tests (`tests/test_base_datos.py`, 33 tests):**
  - Que la base de datos existe y que las tablas tienen filas.
  - Que no hay demoras ni pacientes negativos, ni fechas futuras o con formato inválido.
  - Que las FK son coherentes.
  - Que la suma de los hospitales es igual al total regional y que el total es la suma de sus tres componentes.
  - Que la vista provincial tiene las 9 provincias y población en todos los cortes.

## Fase 4 · Análisis exploratorio

- `notebooks/analisis_exploratorio.ipynb` está escrito como un informe: siete secciones con su pregunta, la consulta SQL (`pd.read_sql`), el tratamiento en pandas, un gráfico de Plotly y una conclusión con cifras.
- Los gráficos se guardan como interactivos y también como PNG (renderer `plotly_mimetype+png`), porque GitHub no ejecuta JavaScript y sin la imagen el notebook se vería vacío allí.
- **Paleta propia validada** (`src/estilo.py`), la misma para el notebook y el dashboard:
  - Verde azulado sanitario para la serie principal, naranja para destacar (Burgos o "empeora") y añil como tercer color.
  - Los tres se comprobaron con un validador de accesibilidad para que se distingan también con daltonismo.
  - Nunca se usan dos ejes Y en un mismo gráfico: pacientes y demora van en gráficos separados.
- Decisiones de análisis:
  - **Tasa por 10.000 habitantes** para comparar provincias de tamaños muy distintos.
  - La tasa regional se calcula como total de pacientes entre total de población, no como media de las tasas provinciales.
  - **Estacionalidad:** al tener datos trimestrales, se compara el cambio entre cortes consecutivos según el trimestre. Se excluyen 2019-2020 por la pandemia.
  - Se avisa de que la demora no mide la calidad de un hospital.
- **Hallazgos con cifras reales:**
  - La lista quirúrgica creció un 33 % en el primer semestre de 2026, hasta 33.034 pacientes estructurales.
  - Burgos tiene la mayor tasa: 176 por 10.000 habitantes, +29 % sobre la media, y está por encima de la media en los 29 cortes.
  - El Bierzo tiene la mayor demora: 201 días, +84 en un año.
  - Traumatología concentra el 32 % de la lista.
  - La demora sube en el corte de septiembre en 5 de 5 años (+9,5 días de media).
- Detectado un probable cambio de registro en consultas externas en septiembre de 2022 (+33 % en un trimestre). Se documenta como limitación en lugar de presentarlo como un hallazgo.

## Fase 5 · Previsión

- `src/prevision.py` trabaja con la serie trimestral de pacientes estructurales, de septiembre de 2019 a junio de 2026: 28 puntos sin huecos. Hay 10 series: la comunidad y las 9 provincias.
- **Validación:** se reservan los 4 últimos trimestres (septiembre de 2025 a junio de 2026) como prueba. Se mide el MAE (pacientes) y el MAPE (%) y se elige el modelo de menor MAE.
- **Modelos:**
  - Tres referencias: último valor, estacional ingenuo y media móvil de 4 trimestres.
  - Un ETS (Holt-Winters) con tendencia amortiguada y estacionalidad trimestral, con `statsmodels.ETSModel`. Se eligió este y no ARIMA porque su intervalo de predicción es nativo y porque es fácil de explicar: nivel, tendencia que se frena y efecto de cada trimestre.
- **Resultado honesto:** el ETS **solo gana en Burgos** (MAPE 4,7 %). En Castilla y León gana la media móvil (MAPE 10,2 %, frente al 20,6 % del ETS) y en el resto de provincias ganan también modelos simples. No se fuerza el modelo complejo.
- **Intervalos del 80 %:**
  - ETS: los da el propio modelo.
  - Modelos simples: a partir de la desviación típica de sus errores históricos, creciendo con la raíz del horizonte.
  - Se mide también la cobertura del intervalo en la prueba.
- **Limitaciones:**
  - Solo 4 puntos de prueba, así que la elección del modelo es frágil (sería mejor validar con origen móvil).
  - Series cortas y alteradas por la pandemia.
  - La media móvil va por detrás de los cambios bruscos, como el salto de 2026.
  - Los modelos no conocen las causas: planes de choque, plantillas, huelgas.
- Los resultados van a la base de datos (tablas `prevision` y `prevision_evaluacion`), para que el dashboard y el asistente puedan consultarlos. `ejecutar_todo.py` ya incluye este paso, y hay 5 tests nuevos (38 en total).

## Fase 6 · Dashboard en Streamlit

- `app/dashboard.py` tiene seis pestañas:
  - **Resumen:** 4 indicadores y la evolución de pacientes y de demora, en gráficos separados.
  - **Comparativa:** mapa, provincias ordenadas y hospitales ordenados.
  - **Especialidades:** ranking y evolución.
  - **Previsión:** gráfico con el intervalo, la tabla de errores y una nota de limitaciones.
  - **Pregúntale a los datos.**
  - **Acerca de:** fuentes, fecha de actualización, metodología y autor.
- **Filtros** de la barra lateral: provincia, hospital (las opciones dependen de la provincia elegida), especialidad y periodo con un deslizador de cortes trimestrales.
  - Como Sacyl no publica la lista quirúrgica por hospital y especialidad, la pestaña Especialidades permite cambiar a las **primeras consultas externas**, que sí tienen ese cruce y respetan todos los filtros. Un aviso lo explica.
- Si no hay filtros, la demora es la regional oficial. Con filtros, es una media ponderada por pacientes.
- **Mapa:** se descarga el GeoJSON oficial de zonas básicas de salud (Datos Abiertos JCyL, CC BY 4.0) y en `limpiar.py` las 247 zonas se unen en 9 provincias con `shapely`. Se pasa de 5,7 MB a 137 KB, y el dashboard no necesita librerías geográficas.
- Tema sobrio en `.streamlit/config.toml`, con el verde azulado sanitario. Se usa la misma paleta validada que en el notebook.
- `st.cache_data` en todas las consultas. La base de datos se abre siempre en solo lectura.
- **Móvil:** la barra lateral está plegada por defecto y las columnas se apilan. Comprobado a 375 px de ancho.
- Probado en el navegador:
  - Arranca sin errores.
  - Los filtros funcionan: con Burgos sale 6.483 pacientes y 136 días, igual que en el análisis.
  - El mapa, la previsión y la vista en móvil se ven bien.
  - Sin clave de API, el asistente muestra un aviso y el resto sigue funcionando.
- Dependencias:
  - `requirements.txt`: dashboard y pipeline, lo que instala Streamlit Cloud.
  - `requirements-dev.txt`: notebook, kaleido y pytest.
  - Todas con la versión fijada.

## Fase 7 · Asistente de IA (texto a SQL)

- **Proveedor:** al principio, Claude (Anthropic). Después se cambió a **Gemini (Google)** para que el proyecto fuera gratuito; ver la nota de la fase 8.
- **Flujo (`src/asistente.py`):**
  1. Se describe el esquema: tablas y vistas, columnas, tipos y 3 filas de ejemplo.
  2. El modelo devuelve SOLO una consulta SQL.
  3. La consulta se valida y se ejecuta.
  4. El modelo redacta una respuesta de 2-4 frases basada solo en los resultados.
  - Las instrucciones explican el contexto: qué significa "espera estructural", que las fechas son cortes trimestrales y que no hay cruce hospital × especialidad en la lista quirúrgica.
- **Seguridad en tres capas:**
  1. `validar_sql()`:
     - Quita los comentarios.
     - Exige una sola sentencia, que empiece por `SELECT` o `WITH`.
     - Rechaza INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, ATTACH, PRAGMA, `load_extension`, etc. Ignora los textos entre comillas para no dar falsos positivos.
  2. Conexión de **solo lectura** (`file:...?mode=ro`).
  3. **Autorizador de SQLite** (`set_authorizer`), que solo permite operaciones de lectura. Aunque algo escapara al validador, SQLite lo bloquearía.
  - Además, la consulta se envuelve en `SELECT * FROM (...) LIMIT 500`.
- **Reintento:** si la consulta falla, se le pasa el error al modelo una vez. Si vuelve a fallar, se muestra un mensaje amable.
- **Interfaz:**
  - Respuesta redactada, gráfico automático (línea si hay fechas, barras si hay categorías), tabla y la consulta SQL en un desplegable.
  - 5 preguntas de ejemplo como botones.
- **Clave de API:** `.env` con `python-dotenv` en local y `st.secrets` en la nube. Sin clave, la pestaña avisa y el resto del dashboard funciona.
- **Tests (`tests/test_asistente.py`):**
  - El validador rechaza 15 consultas peligrosas y acepta 6 válidas, entre ellas un `'DROP TABLE'` dentro de un texto.
  - La conexión es de solo lectura, el límite de filas se aplica y el esquema incluye tablas y vistas.
  - En total hay 64 tests y todos pasan.

## Fase 8 · Publicación

- **README** en español, pensado para un lector con prisa:
  - Una frase que explica el proyecto y el enlace a la demo.
  - Una tabla de "qué responde" con cifras reales.
  - 7 capturas del dashboard: 6 pestañas y la vista móvil.
  - Un diagrama Mermaid del flujo de datos, cómo ejecutarlo, fuentes con su licencia, limitaciones y autor.
- Las capturas se generaron con Playwright usando el Edge del sistema, sin descargar ningún navegador.
- **Prueba de reproducibilidad en una carpeta limpia:** se extrajo el repo sin ningún dato, se creó un entorno virtual nuevo con `requirements-dev.txt` y se ejecutó `python ejecutar_todo.py`.
  - Descarga de las 59 fuentes originales y pipeline completo en 212 s.
  - **64/64 tests** pasan.
  - Los **11 ficheros generados son idénticos byte a byte** a los del repo.
- **Antes de publicar:** búsqueda de claves en todo el repo (ninguna), `.env` y guía de entrevista fuera del control de versiones.
- **Repositorio público** creado y subido: https://github.com/diegotraski/observatorio-sanidad-cyl
  - Descripción en español.
  - Topics: data-analysis, python, sql, streamlit, healthcare, castilla-y-leon, llm, text-to-sql y plotly.
- **Preparado para Streamlit Community Cloud:**
  - Rutas relativas con `pathlib`.
  - La base de datos (0,9 MB) va incluida en el repo.
  - `requirements.txt` en la raíz.
  - La clave se lee de `st.secrets`.
- **Pendiente:**
  - Desplegar desde share.streamlit.io con la cuenta de GitHub del autor y añadir el enlace al README.
  - Probar el asistente con una clave real y rehacer la captura de su pestaña.

## Fase 9 · Preparación para la entrevista

- `docs/GUIA_ENTREVISTA.md` (en el `.gitignore`, no se publica) incluye:
  - El proyecto contado en 30 segundos y en 2 minutos.
  - Las decisiones técnicas y su porqué.
  - Los hallazgos con cifras para citar de memoria.
  - Limitaciones y mejoras.
  - Una frase para el CV y una publicación para LinkedIn.
  - 12 preguntas de entrevista con sus respuestas.
  - Un mini examen de 10 preguntas sobre el código, con soluciones.

### Cambio de proveedor del asistente: de Claude a Gemini (coste cero)

- **Motivo:** la API de Claude se paga por uso y no tiene plan gratuito. Para una demo pública de portfolio se prefirió que el proyecto costara **0 €**.
- **Nuevo proveedor:** Google Gemini, con su plan gratuito.
  - La clave se obtiene en Google AI Studio sin tarjeta.
  - El modelo por defecto es `gemini-3.8-flash`, uno de los que la página oficial de precios lista como gratuitos. Se puede cambiar con `ASISTENTE_MODELO`.
  - SDK oficial `google-genai`, API `client.interactions.create`, con `system_instruction` (instrucciones y esquema), `input` (pregunta) y `thinking_level` (medio para escribir SQL, bajo para redactar).
- **Qué no cambia:** las tres capas de seguridad, el reintento con el error, el límite de 500 filas y los tests. El cambio afecta solo a dos funciones (`crear_cliente` y `_llamar`) gracias a que el resto del código no depende del proveedor.
- **Contrapartidas asumidas:**
  - En el plan gratuito Google puede usar las peticiones para mejorar sus productos. Aquí no importa: los datos son públicos y no se piden datos personales.
  - Hay límites de peticiones por minuto y por día. Si se superan, el asistente muestra un mensaje amable y el resto del dashboard sigue funcionando.
- La variable de entorno pasa a llamarse `GEMINI_API_KEY`, tanto en `.env` como en los *Secrets* de Streamlit.
