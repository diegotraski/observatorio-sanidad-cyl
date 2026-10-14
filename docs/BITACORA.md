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
