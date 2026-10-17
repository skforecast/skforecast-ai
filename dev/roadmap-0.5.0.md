# Plan: lo que va a la 0.5.0

## Contexto

La 0.4.2 se quedó en arreglos: `compare` sobre un plan refinado y H10, el
primer arranque del servidor MCP, el notebook de Colab con el GIF de una
sesión, y la lectura de CSV con `;` o tabuladores y coma decimal.

La auditoría de caja negra del servidor MCP (`dev/mcp-blackbox-audit.md`,
PR #83) confirmó 33 hallazgos. Casi todos son fallos de comportamiento ya
publicado, y varios están por debajo de lo que este plan iba a construir
encima. Por eso la 0.5.0 cambia de alcance: **es la release de robustez**.
Entra lo que la auditoría encontró, lo que quedaba pendiente del CSV de una
hoja de cálculo y los defectos conocidos. La lectura de Parquet y Excel y el
ajuste de hiperparámetros pasan a la 0.6.0 (al final de este fichero).

No hay 0.4.3 salvo que la 0.5.0 se alargue: entonces, una 0.4.3 solo con el
rechazo de V08 (el `.` de miles leído como decimal, introducido por la
lectura de `;` de la 0.4.2) y como mucho G04, que no tocan scripts ni
contexto del LLM.

Las referencias `Vnn` y `Gnn` son las de la auditoría; las `Hn`, las del check
con agentes de la 0.4.0 (su tabla está en `git show
ab1270e:dev/mcp-pending-after-0.4.0.md`). Lo que vino de la revisión anterior
a la 0.4.0 está en `git show 28ba4ba:dev/mcp-preparation.md`, secciones 13.1
y 19.1. Va en un plan aparte, por su tamaño: las descripciones de las
herramientas (`dev/mcp-tool-descriptions-plan.md`), que aquí es la fase 6.

## Cómo está ordenado

Las fases van por dependencias, no por prioridad: cada una deja la base que
la siguiente da por buena. Dentro de una fase, los PR son independientes,
salvo el orden que fije la propia fase (la 1 va en tandas).

Tres costes fijos marcan cómo agrupar:

- **Scripts generados**: un cambio rehace los tests byte a byte de
  `tests/tests_rendering/` y hay que ejecutar los scripts nuevos en
  `tests/test_integration_standalone_script.py`. La fase 1 concentra casi
  todos.
- **Contexto del LLM**: va por `/llm-context-change`, y el check de pago
  contra un modelo real se hace **una sola vez**, en el cierre (fase 7), con
  todos los PR que lo tocan. Los que lo tocan llevan la marca *[LLM]*.
- **Golden de los esquemas MCP** (`tests/tests_mcp/golden/tool_schemas.json`):
  V25 y V29 lo cambian en la fase 5; la fase 6 lo regenera al final.

Marcas: *[script]* cambia los scripts generados, *[LLM]* cambia el contexto del
LLM, *[API]* cambia la API pública o el contrato del servidor, *[SKILL]* cambia
el SKILL.md (con su copia byte a byte en `plugin/`).

## Fase 1. Lectura de datos

Va primero: los dos hallazgos de prioridad alta (V08, G02) están aquí, todo
lo demás lee datos a través de esto, y concentra los cambios de scripts.
Mismo diseño que el dialecto de la 0.4.2 para todo lo que se detecta: se
guarda en el perfil, se emite en el script solo cuando no es el valor por
defecto, se detecta cuando es inequívoco y, si no, error con hint y un
argumento explícito.

- **1a. `.` de miles en ficheros `;` o con tabulador (V08, V15).** Hoy `1.020`
  se lee como `1.02` sin aviso. Tres casos más vistos en la verificación:
  todos los valores con miles (`1.705`) también pasan; con `decimal: ","`
  explícito el objetivo queda categórico, sin estadísticas y sin aviso
  (`validate_target_numeric` lo acepta porque `pd.to_numeric("1.705")`
  funciona); y `1.705,11`, la forma más común del Excel en español, falla
  con el consejo de marcadores de faltantes (V15). Se lee cuando es
  inequívoco (decisión D1). Ojo: el patrón `[1-9]\d{0,2}(\.\d{3})+` también
  encaja con valores de tres decimales exactos (`12.345`), que es el caso
  ambiguo, y su error no puede usar `DIALECT_HINT` porque ningún `sep` ni
  `decimal` lo arregla. *[script]*
- **1b. Ids de serie como texto (G02).** Con ids numéricos (`001`, `1`), todo
  `backtest`, `forecast` y `compare` falla con `KeyError: 1` y se pierden los
  ceros. Dos causas: aquí, `read_csv` sin `dtype` (`_utils.py:894`,
  `rendering/_helpers.py:540`); en skforecast, el issue
  [#1357](https://github.com/skforecast/skforecast/issues/1357). Pasar los
  ids a `str` en el cuerpo común del script (no solo en el `read_csv` del
  preámbulo, que no corre con un DataFrame) conserva los ceros y esquiva el
  bug, se arregle o no upstream. Parquet (0.6.0) traerá los ids como enteros
  de por sí, así que tiene que ir en el reshape. *[script]* *[LLM]* (nombres
  de serie).
- **1c. Filas con un campo más que la cabecera (V28).** Un separador final o
  un campo extra en la primera fila dan "el objetivo no tiene valores" o un
  perfil basura con éxito. Solo detección, sin tocar los scripts (decisión
  D2).
- **1d. Fechas con el día primero (`dd/mm/yyyy`).** Hoy se leen mes primero, o
  se rechazan cuando una fecha posterior no encaja. Los datos mensuales
  (`01/02/2020`) valen en los dos órdenes en todas las filas: se perfilan
  con frecuencia `None` y `forecast()` falla. El formato de fecha va en el
  perfil, detectado cuando es inequívoco (algún día mayor que 12) y, si no,
  error con hint y un argumento explícito. En el mismo PR: el mensaje de V14
  (hoy pide "escribirlas en ISO 8601" a fechas que ya lo están: separar
  "espaciado irregular" de "ambigüedad día y mes"), las fechas `yyyymmdd`
  enteras que hoy se usan como exógena (V13), y las fechas día primero del
  `exog_future` de datos largos. *[script]*
- **1e. Frecuencia con huecos regulares (V14, de fondo).**
  `_infer_frequency_with_gaps` (`data_profile.py:129-171`) exige ventanas de
  10 sin huecos: datos diarios sin domingos (una tienda que cierra) dan
  frecuencia `None` y el error de 1d. Cambia perfiles, y con ellos planes y
  scripts: necesita los tests de determinismo. *[script]*
- **1f. Codificación cp1252.** El "CSV (delimitado por comas)" de Excel en
  Windows no es UTF-8 y una `ñ` o una tilde en una cabecera da
  `data_unreadable` (la auditoría lo vio igual). Si el fichero no es UTF-8,
  leerlo como cp1252, guardarlo en el perfil, emitir `encoding=` en el script
  y avisar en `warnings`, porque no se puede validar. UTF-16 queda fuera.
  *[script]*
- **1g. Exógenas sucias (V12, V11 en el perfil).** Números escritos como texto
  (`12%`, `-`) se vuelven categóricas sin aviso, y un NaN en una exógena no
  avisa hasta un `execution_failed` opaco. Aviso en el perfil, nunca imputar.
  Para V12 no vale `validate_target_numeric` tal cual: hace falta un umbral
  de "casi todo números una vez quitados `%` y `-`", o se marcarían
  categóricas de verdad. *[LLM]* probable (avisos del perfil).

### Tandas

Una sesión (local o en la nube) por PR, cada una en su rama desde `0.5.x`.
Varios PR tocan los mismos sitios (el dialecto, los campos del perfil, el
`read_csv` que emite `rendering/_helpers.py` y los goldens de renderizado),
así que van en tres tandas; dentro de una tanda, en paralelo, y la siguiente
empieza cuando la anterior está mergeada.

| Tanda | PR | Por qué así |
|:--|:--|:--|
| 1 | 1a (miles), 1b (ids como texto), 1c (filas largas) | 1a es de prioridad alta; 1b toca el reshape multiserie, otra zona; 1c solo detecta y no toca scripts |
| 2 | 1d (fechas día primero), 1g (exógenas sucias) | 1d añade, como 1a, un campo al perfil y un argumento al `read_csv` del script: va sobre 1a mergeado. 1g solo cambia avisos del perfil |
| 3 | 1f (cp1252), 1e (frecuencia con huecos) | 1f sigue el mismo patrón que 1a y 1d; 1e va después de 1d porque toca la misma inferencia |

Lo que cada sesión necesita saber (en la nube no hay a quién preguntar):

- Base `0.5.x`, rama `feature/<slug>` o `fix/<slug>`, y abrir la PR al
  terminar.
- Seguir el diseño de este fichero y de las decisiones tomadas. Una decisión
  que no esté cubierta va como pregunta en el cuerpo de la PR, no se adivina.
- Comprobar el arreglo con el script de la auditoría (`git checkout b400a11
  -- reports/mcp-blackbox-audit`, sin commitearlo): debe pasar a imprimir
  `NOT REPRODUCED`. Cada hallazgo lleva su test en `tests/`, en el fichero
  que propone el informe, y su nota de release.
- Los PR con *[LLM]* (1b, 1g) regeneran y revisan los goldens de contexto con
  `/llm-context-change`; el check de pago queda pendiente para la fase 7.

## Fase 2. Multiserie correcta

Resultados incorrectos sin aviso, el peor tipo de fallo después de la fase 1.

- **2a. ForecasterDirectMultiVariate hereda el estimador de las series
  agrupadas (G01).** Con pocos datos por paso, LightGBM no parte y el backtest
  repite un modelo constante (MASE 3.59 frente a 0.49 con Ridge). Solo cuando
  se pide DMV a mano: nunca se elige solo. Pasar `span_index_length` cuando
  `task_type == "multivariate"` en `assistant.py:1088` y en
  `explanation.py:306`, que además dice que se recomienda
  ForecasterRecursiveMultiSeries con un plan DMV. *[script]* *[LLM]*
- **2b. Una serie demasiado corta desaparece del backtest (G03).** Nunca se
  pronostica en ningún fold, la media "across series" la excluye y luego
  `forecast` falla por ella. `insufficient_data` que la nombre (como
  `forecast`), y el perfil debe nombrar la serie corta. skforecast también la
  descarta sin avisar:
  [#1406](https://github.com/skforecast/skforecast/issues/1406). *[LLM]* si
  cambia el texto del backtest.
- **2c. Intervalos de los backtests multiserie.** Defecto conocido: con un
  intervalo del 80 %, cubren el 56 % con ForecasterRecursiveMultiSeries y el
  14 % con ForecasterDirectMultiVariate en `items_sales`, porque los scripts
  usan residuos dentro de muestra (`store_in_sample_residuals` en
  `rendering/multi_series.py`). Primero el aviso de pocos residuos que ya
  tiene una sola serie (V04: `_RESIDUAL_INTERVAL_FORECASTERS` excluye a los
  multiserie; contar por serie e incluir DMV); después, residuos fuera de
  muestra o un aviso con la cobertura que mide el backtest. *[script]* si
  cambian los residuos.
- **2d. `target` como lista (V22, V23).** Con `series_id_column`, la columna
  de ids se descarta en silencio; con una columna repetida, se acepta como
  dos series. Rechazar con `field` el `series_id_column` que pasó el usuario
  (no el que rellena `_normalize_multiindex`).

## Fase 3. Avisos y consejos que funcionan

Un consejo que no funciona es peor que ninguno: el agente lo sigue y se lo
cuenta al usuario.

- **3a. Valores faltantes: una sola regla.** Hoy son tres copias del mismo
  texto (`MissingValuesNotice`, `DATA_VALUES_HINT` y el aviso de la librería,
  con `'LGBMRegressor'` escrito a mano en los tres), y la regla falla en tres
  sitios: promete que LightGBM deja correr el backtest aunque un NaN caiga en
  un fold de test, que falla con cualquier estimador (V16); propone
  `dropna_from_series` para un NaN en una exógena, que no lo arregla (V11,
  `recommendation/preprocessing.py:441-454`); y `warn_backtest_missing_values`
  no avisa con un estimador que acepta faltantes y `differentiation`, que
  falla al invertir la diferenciación. `create_cv` no conoce las fechas de los
  huecos (el perfil solo guarda recuentos): el arreglo de esta fase es
  condicionar el texto; el chequeo por fold necesita los datos y cambia el
  contrato.
- **3b. `refine_plan()` avisa de lo que descarta.** Defecto conocido: al
  cambiar a ForecasterStats, al baseline o a ForecasterFoundation, descarta
  sin avisar la diferenciación, el calendario y el transformador. Con un
  estimador nuevo, también los `estimator_kwargs` omitidos (V29). Principio 3
  de `AGENTS.md`. *[SKILL]* (V29 cambia `models.py:133` y el golden).
- **3c. Métricas.** MAPE de 3e13 en objetivos que cruzan el cero, con un aviso
  que dice que se multiplique por 100 (V10: `metric_selection.py:80-83` mira
  `abs(min)`; usar `min <= 0.01 and max >= -0.01`). sMAPE sale en porcentaje y
  MAPE en fracción sin aviso (V20). `root_mean_squared_error` como métrica del
  servidor: los agentes lo derivan del MSE (4 de 6 en `expensive_run`). V05:
  el CSV de métricas de `forecast` con `test_size` usa abreviaturas y la
  columna `series`, distintas de las del backtest. Decisión D4. *[script]*
  (V10 cambia el panel por defecto) *[LLM]* *[API]* (V05).
- **3d. Aviso cuando el estimador no es el recomendado**, en `backtest` y
  `forecast`, para que el agente diga que lo cambió (el modelo pequeño lo
  cambia tras el `MissingValuesNotice` y no lo dice, 5 de 5). Después de 2a y
  3a: sin 2a, el aviso empujaría de vuelta al LightGBM roto de DMV; sin 3a, el
  cambio que quiere señalar lo provoca un consejo que a veces no sirve.
- **3e. Avisos del forecast.** H11: un aviso en `forecast` cuando su plan no
  se midió en la sesión (solo con el modelo pequeño, 2 de 6; cubre también el
  forecast sin ninguna medida). H4: el resumen de un forecast con
  `test_size` no dice con palabras que es una evaluación; el aviso del
  servidor lo cubre y el texto vive en `llm/context.py`. *[LLM]*
- **3f. Avisos menores.** El aviso de coste ofrece `refit` para ForecasterStats
  y modelos fundacionales, que no baja su coste (V18). `create_cv` acepta
  `skip_folds` para ForecasterStats y el backtest falla opaco (V17).
  `fixed_train_size` sin `refit`: el esquema dice que es un error y el
  servidor solo avisa (V21). `FutureExogNotice` nombra también las
  categóricas que un modelo fundacional descartaría (hoy no se alcanza).

## Fase 4. Coste

El `CostNotice` para al modelo grande (6 de 6) y no al pequeño (12 de 12
lanza con el aviso leído). La confirmación explícita por encima del umbral
estaba en el plan, pero se apoya en una contabilidad que hoy está mal:

- **4a. Contar bien.** Con candidatos, `compare` aplica el umbral a cada uno y
  no al total, y corre 78 ajustes sin aviso (V19); `cost.n_fits` de `compare`
  es el de la estrategia, no el total (V06). Definir `n_fits` como total, o
  renombrarlo, y estimar el total antes de ejecutar. *[API]* *[SKILL]*
- **4b. Confirmación explícita por encima del umbral** en `backtest` y
  `compare`, sobre la cuenta de 4a. Decisión D3. *[API]* *[SKILL]*

## Fase 5. Contrato de las herramientas y errores

Fallos opacos o contratos que no se cumplen. Independientes entre sí y
pequeños; se pueden agrupar en dos o tres PR.

- **Entradas que no se validan**: claves desconocidas de `window_features` se
  ignoran y el resumen las muestra como elegidas (V25, cierra el `TypedDict`
  y cambia el golden de esquemas); `plan` valida los nombres de
  `estimator_kwargs` pero no sus valores (V33).
- **Errores**: `forecast` con `test_size` como fecha con zona horaria da
  `internal_error` con "do not retry" (G04: pasar `time_zone` del perfil a
  `resolve_end_train`, `assistant.py:4498`). Un hold-out con el tramo de
  entrenamiento más corto que la ventana falla como `execution_failed` (V30:
  el chequeo va en `validate_evaluation_partition`, `_last_window.py:921`).
  `create_cv` solo con `plan_id` culpa a `initial_train_size`, que el agente
  no envió (V31: `default_initial_train_size` se salta la cota de dos folds
  cuando `n - 2*steps <= 0`; mejor un `insufficient_data` previo). Un
  `InvalidInputError` se reporta como `ValueError`, así que
  `mcp/_errors.py:304-307` omite el mensaje propio (V32, descartado en la
  auditoría por otra razón pero real), y `get_failure(comparison_id)` sin
  candidato responde "named None".
- **Dependencias opcionales**: `missing_dependency` de XGBoost o CatBoost
  llega sin `hint` ni `details` (V02: el mismo contrato que los modelos
  fundacionales, con `pip install` y el `--with` de `uvx`); un `compare` por
  defecto multiserie sin backend fundacional incluye XGBRegressor, que
  ningún extra instala (V01: excluirlo en `resolve_default_candidates` con un
  aviso, como `missing_foundation_backend`; no en el perfil, que debe seguir
  sin depender del entorno). *[LLM]* (V01, `execution/comparison.py`)
- **`get_code`**: la primera llamada calcula `requirements` en el event loop
  y lo bloquea mientras dura una ejecución (G05: medido, todo el servidor
  espera); añade el backend del modelo fundacional al script de una
  estrategia, que no carga ningún modelo; y el script de un forecast con
  `exog_path` lee `exog_future.csv` del directorio de trabajo, no el fichero
  que corrió (V03). *[script]* (V03)
- **`profile` sin `target` cuando el usuario ya nombró la columna.** Cuesta
  una llamada (9 de 81 con el modelo grande). Con el pequeño, una sesión se
  saltó así el error de la columna inexistente y la sustituyó sin decirlo.
- **`compare` con candidatos** deja fuera el plan refinado de la estrategia
  sin decirlo, y "Strategy plan" no es un nombre reservado (V24). *[SKILL]*

## Fase 6. Descripciones de las herramientas y SKILL.md

Al final, para que describan el comportamiento definitivo y el golden de
esquemas se regenere una vez: `dev/mcp-tool-descriptions-plan.md`, más las
frases del SKILL.md o de los esquemas que la auditoría vio desfasadas (V06,
V19, V21, V24, V29) y lo que hayan cambiado las fases 3 a 5. *[SKILL]*

## Fase 7. Cierre de la release

1. `/llm-context-change` con todos los PR marcados *[LLM]*: goldens
   revisados y un solo check de pago contra un modelo real
   (`tools/ai/check_ask_context.py`, lo lanzas tú).
2. Check con agentes de `tools/mcp/` (cambian el SKILL, el coste y las
   descripciones: está en "When to run it"), al menos con sonnet y con haiku
   en los escenarios críticos. Debe incluir un escenario con un CSV de Excel
   en español (miles con `.`, fechas día primero, cp1252) y otro multiserie
   con ids numéricos, y uno que vea si un agente lee el aviso de intervalos
   con cotas iguales y lo cuenta (pendiente desde `96f4cdc`).
3. Comprobaciones a mano (abajo).
4. `/release-note consolidate`, bump de versión (`/release-bump`) y
   publicación.
5. Tras publicar: Deploy y Make Release en Glama y apuntar el TDQS nuevo
   (paso 8 del plan de descripciones).

## Decisiones tomadas

- **D1. V08: leer el `.` de miles cuando es inequívoco** (2026-10-15): mezcla
  de valores con y sin separador, o con `,` decimal como `1.705,11`. Se
  guarda `thousands` en el perfil y se emite en el script solo cuando no es
  el de hoy. Cuando es ambiguo (todos los valores con tres cifras tras el
  punto), `data_unreadable` con hint. El rechazo a secas solo es el plan B de
  una 0.4.3.
- **D2. V28: solo detección** (2026-10-15): las filas más largas que la
  cabecera dan `data_unreadable` con hint, sin tocar los scripts.
  `index_col=False` leería bien el separador final, pero tendría que ir
  también en el script y rehacer todos los goldens de renderizado.
- **D?. 2a: el estimador de DMV se dimensiona con las fechas comunes**
  (2026-10-17): lo decide el `task_type` `"multivariate"`
  (`estimator_n_observations`: `span_index_length`; las demás tareas siguen
  con `n_total_observations`). `refine_plan` ya no arrastra hacia o desde
  DMV un estimador que eligieron las reglas: lo vuelven a elegir. Sí arrastra
  el que eligió el usuario, o aquel para el que escribió `estimator_kwargs`.
  La explicación del perfil sigue siendo la del perfil (recomienda
  ForecasterRecursiveMultiSeries); la del plan añade el estimador, el
  forecaster para el que lo eligieron las reglas y el número que lo decidió,
  solo cuando la tarea del plan no es la del perfil y el estimador no se pasó.

## Decisiones abiertas

Se toman en el PR que las necesita y se pasan a la sección de arriba.

- **D3. Forma de la confirmación de coste**: un argumento `confirm_cost` (o
  similar) que el servidor exige por encima del umbral, o un `cost_id` que
  devuelve la estimación y que la ejecución tiene que citar. Afecta a la API
  de Python, a la CLI y al SKILL.
- **D4. V05: renombrar las columnas del CSV de métricas de `forecast`** para
  que coincidan con las del backtest (rompe a quien ya lo lee) o documentar
  la diferencia. Propuesta: renombrar, con nota de release; la API puede
  romperse en una minor temprana.

## Issues a skforecast

- **G02**: ya abierto,
  [#1357](https://github.com/skforecast/skforecast/issues/1357). Se le
  añadieron dos cosas en un comentario (2026-10-15): que
  `reshape_series_long_to_dict` con ids enteros
  produce exactamente ese dict, y que las rutas de `predict` también buscan
  con el nombre sin convertir (`.get(level, np.nan)` en 2994 y 3149,
  `.get(level, None)` en 3377 y un índice directo en 2928, en
  `_forecaster_recursive_multiseries.py`), así que arreglar solo el `fit`
  podría dar codificaciones NaN en silencio; normalizar a `str` en
  `check_preprocess_series` es más seguro.
- **G03**: [#1406](https://github.com/skforecast/skforecast/issues/1406).
  `backtesting_forecaster_multiseries` no emite ningún aviso,
  ni con `suppress_warnings=False`, cuando una serie no se puede pronosticar
  en ningún fold: su fila de métricas sale NaN, no aparece en las
  predicciones y la fila `average` se calcula sin ella.

## Comprobaciones a mano

Lo que el README del check y la auditoría listan como no cubierto:

- **Cursor y Codex** (no están instalados en la máquina): el formato de
  `~/.codex/config.toml` y de `codex mcp add`, sus timeouts de arranque y si
  Cursor interpola `${workspaceFolder}`.
- **Claude Desktop**: su timeout de arranque (no se alcanzó), lo que muestra
  la ventana y una llamada desde un chat.
- **Claude Code**: los comandos `/plugin` tecleados en una sesión
  interactiva (se usaron `claude plugin marketplace add` y `claude plugin
  install`), y el plugin en Cowork y en Windows.
- **De la auditoría**: inferencia con modelos fundacionales (`chronos`):
  `ModelLicenseNotice`, los prefijos de `--allow-model` y `HF_HUB_OFFLINE`;
  XGBoost y CatBoost instalados, tras V02; la expulsión de un objeto mayor
  que `--max-memory-mb`; ficheros grandes y `--max-file-mb`; el timeout real
  de un cliente y los objetos huérfanos; el truncado del resumen a 20000
  caracteres.

## Herramientas de mantenimiento

No bloquean la release; se hacen cuando haya hueco.

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
- Restos de la auditoría sin script, por confirmar: `00:00:00` en
  `HoldoutEvaluationNotice`, MASE NaN con "Mean of empty slice", DMV con
  `refit: true`.

Cuando todos los hallazgos de `dev/mcp-blackbox-audit.md` estén arreglados
(cada uno con su test en `tests/`), se borra ese fichero, como se hizo con
`dev/mcp-pending-after-0.4.0.md`.

## A la 0.6.0

### Leer Parquet y Excel por ruta

#### Por qué

La API de Python ya los admite de hecho: quien tiene un Parquet hace
`pd.read_parquet()` y pasa el DataFrame. Lo que falta es la lectura por
ruta, en la CLI y en el servidor MCP, que es el canal de los agentes. Un
usuario de negocio que habla con un agente tiene sus datos en Excel; un
equipo de datos, en Parquet.

Va después de la 0.5.0 porque se apoya en lo que arregla: los ids de serie
como texto en el reshape (1b; en Parquet llegan como enteros), el contrato
de `missing_dependency` con hint (fase 5, V02), la ruta de las exógenas
futuras (V03, que si no se multiplicaría por formato) y un solo detector de
formatos de fecha (1d, donde entrarían las fechas de Excel como número de
serie).

#### Qué toca (comprobado el 2026-10-11 sobre `0.4.x`)

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

#### Decisiones a tomar

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
  tamaño que ya aplica `--max-file-mb`. Pasar `/security-review`. La
  auditoría dejó bien probada la frontera de rutas; lo pendiente es solo lo
  propio del `.xlsx`.
- **URLs**: si `profile()` acepta una URL de Parquet o Excel como acepta la
  de un CSV, o solo rutas.

Fuera de este alcance: bases de datos y DuckDB.

### Ajuste de hiperparámetros

Hoy `compare()` solo ordena configuraciones fijas. Un paso acotado de
búsqueda con las funciones de skforecast, con su coste en `CostNotice` como
los backtests. Después de la fase 4, que deja bien contado el coste de
`compare`.
