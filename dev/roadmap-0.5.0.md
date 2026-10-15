# Plan: lo que va a la 0.5.0

## Contexto

La 0.4.2 se quedó en arreglos: `compare` sobre un plan refinado y H10, el
primer arranque del servidor MCP, el notebook de Colab con el GIF de una
sesión, y la lectura de CSV con `;` o tabuladores y coma decimal. Lo que es
funcionalidad nueva, o cambia la API, va a la 0.5.0. Este fichero lo apunta
para no perderlo.

Absorbe la lista de lo que quedó abierto tras la 0.4.0. Lo ya hecho (los
dos arreglos de `compare` de la 0.4.2 y su caso mínimo) y la tabla de los
códigos H1 a H11 que cita el log de `tools/mcp/README.md` están en el
historial: `git show ab1270e:dev/mcp-pending-after-0.4.0.md`.

Va en un plan aparte, por su tamaño: las descripciones de las herramientas
del servidor MCP, a partir de la nota que les pone Glama
(`dev/mcp-tool-descriptions-plan.md`).

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

### Pendiente del CSV de una hoja de cálculo (antes de la 0.5.0)

La 0.4.2 lee el separador y el decimal, pero un CSV exportado desde Excel en
español suele traer dos cosas más que siguen fallando. Cada una en su PR:

- **Fechas con el día primero (`dd/mm/yyyy`)**: hoy se leen mes primero, o se
  rechazan cuando una fecha posterior no encaja. Los datos mensuales
  (`01/02/2020`) valen en los dos órdenes en todas las filas: se perfilan
  con frecuencia `None` y `forecast()` falla. Diseño como el del dialecto:
  el formato de fecha en el perfil, emitido en el script solo cuando no es
  el de hoy; detectado cuando es inequívoco (algún día mayor que 12) y, si
  no, error con hint y un argumento explícito. Cambia los scripts generados.
- **Codificación cp1252**: el "CSV (delimitado por comas)" de Excel en
  Windows no es UTF-8 y una `ñ` o una tilde en una cabecera da
  `data_unreadable`. Propuesta: si el fichero no es UTF-8, leerlo como
  cp1252, guardarlo en el perfil, emitir `encoding=` en el script y avisar
  en `warnings`, porque no se puede validar. UTF-16 queda fuera.

## 2. Servidor MCP

Del check con agentes de la 0.4.0 (`tools/mcp/README.md`), con la tasa que
se vio:

- **Confirmación explícita por encima del umbral de coste** en `backtest` y
  `compare`. El `CostNotice` para al modelo grande (6 de 6) y no al pequeño
  (12 de 12 lanza con el aviso leído). Es un cambio de API.
- **H11: un aviso en `forecast` cuando su plan no se midió en la sesión.**
  Solo con el modelo pequeño (2 de 6); cubre también el forecast sin ninguna
  medida.
- **Aviso cuando el estimador no es el recomendado**, en `backtest` y
  `forecast`, para que el agente diga que lo cambió. El modelo pequeño lo
  cambia tras el `MissingValuesNotice` y no lo dice en la respuesta final (5
  de 5).
- **`root_mean_squared_error` como métrica del servidor.** Hoy no se ofrece,
  y los agentes lo derivan del MSE (4 de 6 en `expensive_run`).
- **El resumen de un forecast con `test_size`** (H4) no dice con palabras
  que es una evaluación. El aviso del servidor lo cubre; el texto vive en
  `llm/context.py` y va por `/llm-context-change`.
- **Un solo texto para `MissingValuesNotice` y `DATA_VALUES_HINT`**, y el
  `'LGBMRegressor'` escrito a mano en los dos y en el aviso de la librería:
  son tres copias de la misma regla.
- **`profile` sin `target` cuando el usuario ya nombró la columna.** Cuesta
  una llamada (9 de 81 con el modelo grande). Con el pequeño, una sesión se
  saltó así el error de la columna inexistente y la sustituyó sin decirlo.
- **Las descripciones de las herramientas**: `dev/mcp-tool-descriptions-plan.md`.

## 3. Defectos conocidos

Que ven los usuarios. Vienen de la revisión anterior a la 0.4.0 (`git show
28ba4ba:dev/mcp-preparation.md`, secciones 13.1 y 19.1) y siguen abiertos
(comprobado el 2026-10-15 sobre la 0.4.2):

- **Los intervalos de los backtests multiserie cubren mucho menos de lo
  nominal**: con un intervalo del 80 %, el 56 % con
  ForecasterRecursiveMultiSeries y el 14 % con ForecasterDirectMultiVariate
  en `items_sales`, porque los scripts usan residuos dentro de muestra
  (`store_in_sample_residuals` en `rendering/multi_series.py`). Quien se fía
  del intervalo se lleva una falsa seguridad. Opciones: residuos fuera de
  muestra, o al menos un aviso con la cobertura que mide el backtest.
- **`refine_plan()` descarta sin avisar** la diferenciación, el calendario y
  el transformador al cambiar a ForecasterStats, al baseline o a
  ForecasterFoundation, que no los usan. Va contra el principio 3 de
  `AGENTS.md`: tiene que avisar de lo que deja fuera.

Vistos en la revisión de código del servidor:

- `warn_backtest_missing_values` (`create_cv`) no avisa con un estimador
  que acepta valores ausentes y `differentiation`, y `backtest` rechaza
  después porque la inversa de la diferenciación lee un valor ausente.
- `get_code` calcula `requirements` en el event loop (la primera llamada
  recorre todas las distribuciones instaladas) y añade el backend del
  modelo foundation al script de una estrategia, que no carga ningún modelo.
- `FutureExogNotice` nombra todas las exógenas del perfil, también las
  categóricas que un modelo foundation descartaría. Hoy no se alcanza.

## 4. Herramientas de mantenimiento

- **Tests unitarios de `tools/mcp/check_mcp_agent.py`.** No tiene ninguno,
  y casi todos los defectos de las dos revisiones de código estaban en sus
  heurísticas (redirecciones, fallos falsos, herramientas que se escapaban).
- **Enmascarar el directorio personal y el usuario del sistema** en lo que
  renderiza el informe del check, como ya hace con el workspace. Hoy
  aparecen en salidas de `ls -la`, y una ruta se quitó a mano de un informe:
  un `--report-only` la devolvería.
- Una sesión del check puede cargar los skills de fábrica de Claude Code con
  `Skill`.
- El `WARN` de H11 da un aviso en falso cuando el plan se reconstruye igual
  con un intervalo (está anotado en el README del check).
- El guard de Bash (`.claude/hooks/pre_bash_guard.py`) resuelve la rama
  desde `CLAUDE_PROJECT_DIR` antes que desde el `cwd` de la llamada: en un
  worktree comprueba la rama del checkout principal.

## 5. Comprobaciones a mano

Lo que el README del check lista como no cubierto y sigue sin probar:

- **Cursor y Codex** (no están instalados en la máquina): el formato de
  `~/.codex/config.toml` y de `codex mcp add`, sus timeouts de arranque y si
  Cursor interpola `${workspaceFolder}`.
- **Claude Desktop**: su timeout de arranque (no se alcanzó), lo que muestra
  la ventana y una llamada desde un chat.
- **Claude Code**: los comandos `/plugin` tecleados en una sesión
  interactiva (se usaron `claude plugin marketplace add` y `claude plugin
  install`), y el plugin en Cowork y en Windows.
- **Intervalos con cotas iguales** (hallazgo 4 del piloto, arreglado en
  `96f4cdc`): `create_cv` avisa, pero falta un escenario del check que vea si
  un agente lee el aviso y lo cuenta.

## 6. Otros candidatos

- **Ajuste de hiperparámetros**: hoy `compare()` solo ordena configuraciones
  fijas. Un paso acotado de búsqueda con las funciones de skforecast, con
  su coste en `CostNotice` como los backtests.
