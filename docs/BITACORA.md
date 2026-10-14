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
