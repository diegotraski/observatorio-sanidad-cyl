# Diccionario de datos

Todas las tablas están en `data/sanidad_cyl.db` (SQLite) y, en CSV, en `data/processed/`.
Las fechas son fechas reales en formato `AAAA-MM-DD`.

**Fuentes**

- **Sacyl LEQ:** Lista de espera quirúrgica total, Portal de Salud de la Junta de Castilla y León.
  https://www.saludcastillayleon.es/es/leq-total-ce-pdt/historico/lista-espera-quirurgica-total
- **Sacyl CE:** Lista de espera de consultas externas, mismo portal.
  https://www.saludcastillayleon.es/es/leq-total-ce-pdt/historico/lista-espera-consultas-externas
- **INE ECP:** Estadística Continua de Población, tablas 56945 y 59589. https://www.ine.es
- **Elaboración propia:** tablas maestras construidas en `src/limpiar.py` a partir del mapa sanitario de Sacyl.

Las definiciones de "espera estructural", "transitoriamente no programable" y "rechazo de
centro alternativo" son las del **Real Decreto 605/2003**, que recogen los propios Excel de Sacyl.

---

## `provincias`

| Columna | Tipo | Descripción | Unidad | Fuente |
|---|---|---|---|---|
| `provincia_id` | INTEGER (PK) | Identificador | — | Elaboración propia |
| `nombre` | TEXT | Nombre oficial de la provincia (Ávila, Burgos…) | — | INE |

## `poblacion`

| Columna | Tipo | Descripción | Unidad | Fuente |
|---|---|---|---|---|
| `provincia_id` | INTEGER (FK) | Provincia | — | — |
| `fecha` | DATE | Fecha de referencia de la cifra: día 1 de enero, abril, julio u octubre. En 2019 y 2020 solo hay 1 de enero y 1 de julio. | — | INE ECP |
| `habitantes` | INTEGER | Población residente, todas las edades, ambos sexos | personas | INE ECP |

## `hospitales`

| Columna | Tipo | Descripción | Unidad | Fuente |
|---|---|---|---|---|
| `hospital_id` | INTEGER (PK) | Identificador | — | Elaboración propia |
| `nombre` | TEXT | Nombre corto normalizado (p. ej. "CAU Burgos") | — | Sacyl, normalizado |
| `nombre_completo` | TEXT | Nombre completo del centro | — | Sacyl |
| `area_salud` | TEXT | Área de salud de Sacyl (hay 11) | — | Sacyl |
| `localidad` | TEXT | Municipio donde está el hospital | — | Sacyl |
| `provincia_id` | INTEGER (FK) | Provincia del hospital | — | — |

## `especialidades`

| Columna | Tipo | Descripción | Unidad | Fuente |
|---|---|---|---|---|
| `especialidad_id` | INTEGER (PK) | Identificador | — | Elaboración propia |
| `nombre` | TEXT | Nombre normalizado de la especialidad | — | Sacyl, normalizado |

## `lista_espera_quirurgica_hospital`

Una fila por **hospital y corte trimestral**. Es la foto de la lista de espera el último día del trimestre.

| Columna | Tipo | Descripción | Unidad | Fuente |
|---|---|---|---|---|
| `fecha` | DATE | Fecha de corte (31-mar, 30-jun, 30-sep, 31-dic) | — | Sacyl LEQ |
| `hospital_id` | INTEGER (FK) | Hospital | — | — |
| `pacientes_total` | INTEGER | Pacientes pendientes de intervención quirúrgica (suma de las tres columnas siguientes) | pacientes | Sacyl LEQ |
| `pacientes_estructurales` | INTEGER | Pacientes en espera estructural: su espera se debe a la organización y los recursos del sistema. **Es la cifra oficial de comparación.** | pacientes | Sacyl LEQ |
| `pacientes_no_programables` | INTEGER | Transitoriamente no programables, por motivo clínico o porque el paciente pidió aplazar la operación | pacientes | Sacyl LEQ |
| `pacientes_rechazo_centro_alternativo` | INTEGER | Esperan porque rechazaron operarse en otro centro | pacientes | Sacyl LEQ |
| `demora_media_dias` | REAL | Tiempo medio que llevan esperando los pacientes en espera estructural | días | Sacyl LEQ |
| `demora_media_rechazo_dias` | REAL | Tiempo medio de espera de los que rechazaron el centro alternativo. Nulo si no hay pacientes. | días | Sacyl LEQ |

## `lista_espera_quirurgica_especialidad`

Mismas columnas que la tabla anterior, pero con `especialidad_id` en lugar de `hospital_id`.
Es el total de Castilla y León para cada especialidad quirúrgica (14). **Sacyl no publica el cruce hospital × especialidad en la lista quirúrgica.**

## `lista_espera_quirurgica_region`

Mismas columnas, una fila por corte, con el total de Castilla y León tal como lo publica Sacyl.
La demora regional es la oficial (media sobre todos los pacientes), no una media de los hospitales.

## `consultas_externas`

Una fila por **hospital, especialidad y corte trimestral**, para pacientes que esperan una **primera consulta** con el especialista.

| Columna | Tipo | Descripción | Unidad | Fuente |
|---|---|---|---|---|
| `fecha` | DATE | Fecha de corte | — | Sacyl CE |
| `hospital_id` | INTEGER (FK) | Hospital | — | — |
| `especialidad_id` | INTEGER (FK) | Especialidad (34 posibles) | — | — |
| `pacientes_total` | INTEGER | Pacientes en espera de primera consulta | pacientes | Sacyl CE |
| `pacientes_estructurales` | INTEGER | Pacientes en espera estructural. Hasta sep-2022 se calcula como total × porcentaje estructural publicado. | pacientes | Sacyl CE (calculado) |
| `demora_media_dias` | REAL | Tiempo medio de espera estructural para primera consulta. Nulo si Sacyl no lo publica. | días | Sacyl CE |

Solo hay filas para las combinaciones con lista de espera. Si un hospital no tiene un servicio, no hay fila.

---

## Vistas SQL

| Vista | Qué devuelve |
|---|---|
| `v_quirurgica_provincia` | Pacientes y demora media quirúrgica por provincia y trimestre, con la población y la **tasa por 10.000 habitantes**. La demora provincial se pondera por los pacientes estructurales de cada hospital. |
| `v_quirurgica_hospital` | Lista quirúrgica por hospital, con su nombre, área y provincia ya unidos (sin necesidad de joins). |
| `v_consultas_detalle` | Consultas externas con los nombres de hospital, especialidad y provincia ya unidos. |
| `v_quirurgica_especialidad` | Lista quirúrgica por especialidad con su nombre ya unido. |
