# Plan: lo que va a la 0.5.0

## Contexto

La 0.4.2 se queda en arreglos: `compare` sobre un plan refinado y H10
(`dev/mcp-pending-after-0.4.0.md`, puntos 1 y 2), el primer arranque del
servidor MCP, el notebook de Colab con el GIF de una sesión, y la lectura de
CSV con `;` o tabuladores y coma decimal. Lo que es funcionalidad nueva, o
cambia la API, va a la 0.5.0. Este fichero lo apunta para no perderlo.

## 1. Leer Parquet y Excel por ruta

### Por qué

La API de Python ya los admite de hecho: quien tiene un Parquet hace
`pd.read_parquet()` y pasa el DataFrame. Lo que falta es la lectura por
ruta, en la CLI y en el servidor MCP, que es el canal de los agentes. Un
usuario de negocio que habla con un agente tiene sus datos en Excel; un
equipo de datos, en Parquet.

### Qué toca (comprobado el 2026-10-11 sobre `0.4.x`)

La lectura de CSV está en unos 40 sitios de 10 módulos. Los que deciden el
alcance:

- **El script generado lee con `pd.read_csv`** (`rendering/_helpers.py`). Por
  el principio 2 de `AGENTS.md`, el script tiene que leer el mismo formato
  que la librería: `pd.read_parquet` o `pd.read_excel` con los mismos
  argumentos. Cambian los tests byte a byte de `tests/tests_rendering/` y
  hay que ejecutar los scripts nuevos en
  `tests/test_integration_standalone_script.py`.
- **La lectura de la librería**: `read_csv_file`
  (`profiling/data_profile.py`), `_resolve_data_and_target` (rutas y URLs) y
  `load_exog` (`_utils.py`).
- **El servidor MCP rechaza lo que no termina en `.csv`**
  (`resolve_csv_path` en `mcp/_inputs.py`). Las instrucciones del servidor
  (`mcp/server.py`), los hints de error y el SKILL.md (con su copia byte a
  byte en `plugin/`) dicen "CSV" por todas partes. Las exógenas futuras se
  escriben y se leen como `exog_future.csv`.
- **Lo que recibe el LLM**: `llm/context.py` nombra el formato en un sitio;
  si cambia el texto, va por `/llm-context-change` y su check de pago.
- **El check con agentes** (`tools/mcp/scenarios.py`): un escenario con un
  Excel y otro con un Parquet.

### Decisiones a tomar

- **Dependencias opcionales**: pyarrow pesa decenas de MB y openpyxl es
  pequeño. Un extra por formato (`[parquet]`, `[excel]`) o uno solo
  (`[formats]`). Sin el paquete, error `missing_dependency` con el hint de
  `pip install` y del `--with` de `uvx`, como los modelos foundation. No
  deben entrar en el lanzador `skforecast-ai-mcp`: alargarían el primer
  arranque.
- **Excel**: qué hoja leer (la primera por defecto y una opción `sheet` en la
  API, la CLI y el MCP), fechas guardadas como número de serie, filas de
  cabecera que no son la primera. Si la hoja no es una tabla limpia, error
  con hint, no adivinar.
- **Seguridad**: un `.xlsx` es un zip con XML. Revisar el lector frente a
  ficheros manipulados (bombas zip, entidades XML) además del límite de
  tamaño que ya aplica `--max-file-mb`. Pasar `/security-review`.
- **URLs**: si `profile()` acepta una URL de Parquet o Excel como acepta la
  de un CSV, o solo rutas.

### Fuera de este alcance

- El CSV con `;` o tabuladores y coma decimal, `.tsv` y `.csv.gz`: van en la
  0.4.2 porque hoy fallan y el resto de ficheros no cambia.
- Bases de datos y DuckDB.

## 2. Otros candidatos de la 0.5.0

- **Ajuste de hiperparámetros**: hoy `compare()` solo ordena configuraciones
  fijas. Un paso acotado de búsqueda con las funciones de skforecast, con
  su coste en `CostNotice` como los backtests.
- **Confirmación explícita por encima del umbral de coste** en `backtest` y
  `compare` del servidor MCP (punto 3 de
  `dev/mcp-pending-after-0.4.0.md`). Es un cambio de API.
