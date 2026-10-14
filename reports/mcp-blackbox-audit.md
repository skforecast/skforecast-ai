# Auditoría de caja negra del servidor MCP de skforecast-ai

Base: `0.4.x` (rama `chore/mcp-blackbox-audit`). Objeto: `skforecast-ai mcp`
(código en `skforecast_ai/mcp/`), usado desde fuera como lo usaría un agente
cliente. Solo informe: no se ha tocado nada bajo `skforecast_ai/`, `tests/` ni
`plugin/`. Scripts, datasets y datos crudos de cada fase en
`reports/mcp-blackbox-audit/` (ver su `README.md`).

## Resumen ejecutivo

El servidor aguanta bien el uso normal de un agente. El flujo feliz (serie
única, multiserie larga y ancha, exógenas con fichero futuro) encadena ids,
ficheros, notices y costes como promete el SKILL.md, y los scripts de
`get_code` reproducen exactamente los números del servidor. La frontera de
seguridad de rutas resistió todo lo probado (prefijos hermanos, `..`,
symlinks a fichero y a directorio, URLs, caracteres de control, `/proc`), los
errores de esquema llegan en el JSON documentado con `field`, y los umbrales
de coste (50 ajustes, 2000 ventanas) caen exactamente donde dice el skill.

Lo que los 62 ficheros de `tests/tests_mcp/` no ven está casi todo en tres
sitios: **la lectura de CSV reales**, **los casos multiserie menos comunes** y
**los consejos que el servidor da al agente**.

- **Dos fallos graves**:
  - En un CSV con `;` y cantidades enteras con punto de miles (`1.020`),
    `profile` lee `1.020` como `1.02` sin error ni notice; el agente pronostica
    y reporta sobre un objetivo errado en un factor 1000 (V08). Es la
    exportación típica de Excel en España.
  - En datos largos con ids de serie numéricos (`001`, `1`), todo `backtest`,
    `forecast` y `compare` falla con un `KeyError: 1` interno de skforecast, y
    los ceros a la izquierda se pierden (G02). Los ids de tienda o SKU suelen
    ser así; el agente queda bloqueado sin pista de la causa.
- **Resultados incorrectos sin aviso en multiserie**: ForecasterDirectMultiVariate
  hereda el estimador elegido para las series agrupadas y su backtest repite un
  modelo constante (G01); una serie demasiado corta desaparece del backtest y
  de su media "across series" sin notice, y luego `forecast` falla por ella
  (G03).
- **Un `internal_error` con una entrada normal**: `forecast` con `test_size`
  como fecha con zona horaria (`...Z`) responde "do not retry" (G04).
- **Ficheros mal formados que no dan `data_unreadable`**: filas con un campo
  más que la cabecera (separador final, o campo extra solo en la primera fila)
  producen un error falso ("el objetivo no tiene valores") o un perfil basura
  con éxito (V28).
- **Exógenas sucias que pasan sin aviso** y revientan tarde como
  `execution_failed` opaco: NaN en una exógena (V11) y números escritos como
  texto (`12%`, `-`) que se convierten en categóricas (V12). Para el objetivo,
  en cambio, el servidor avisa o rechaza con precisión.
- **Consejos que no funcionan**: `create_cv` promete que LGBMRegressor deja
  correr el backtest con valores faltantes cuando un NaN cae en un fold de test
  (V16); el aviso de coste ofrece `refit` para ForecasterStats y modelos
  fundacionales, que no baja su coste (V18); el error de fechas irregulares en
  ISO 8601 pide escribirlas en ISO 8601 (V14).
- **Métricas engañosas**: MAPE de 3e13 en objetivos que cruzan el cero, con un
  notice que dice que se multiplique por 100 (V10); sMAPE en porcentaje junto a
  MAPE en fracción sin aviso (V20).
- **Promesas del contrato que no se cumplen**: `missing_dependency` sin `hint`
  para XGBoost y CatBoost (V02), un `compare` por defecto multiserie que
  casi siempre lleva un candidato XGBoost que no puede instalarse (V01), claves
  desconocidas de `window_features` ignoradas y además mostradas como elegidas
  (V25), `refine_plan` que descarta `estimator_kwargs` omitidos (V29), y varias
  frases del SKILL.md o de los esquemas que ya no describen el comportamiento
  (V06, V19, V21, V24).

Cifras: 6 ejes explorados por agentes cliente de caja negra, 45 hallazgos
brutos, 34 tras deduplicar, 28 confirmados por mayoría de 3 escépticos
independientes (6 refutados); el crítico de completitud abrió 8 huecos y su
ronda añadió 5 hallazgos, los 5 confirmados por 2 de 2 escépticos. **Total: 33
confirmados**: 13 bugs, 8 fricciones para agentes, 8 desajustes del skill o
los esquemas, 4 mejoras; 2 de prioridad alta, 13 media y 18 baja.

Si solo se arreglan cinco cosas: V08 y G02 (datos reales que rompen el flujo o
lo falsean), V28 (ficheros mal formados), G01 y G03 (números multiserie
incorrectos sin aviso). Los arreglos de redacción del SKILL.md y de los
esquemas (V06, V19, V21, V24, V29) son baratos y evitan que el agente afirme
cosas falsas.

## Método

1. **Scout** (inline): `dump_catalog.py` vuelca lo que ve un cliente
   (instrucciones del servidor, 11 herramientas, esquemas) en
   `tool_catalog.md`; con el `SKILL.md` es la única descripción que usaron los
   exploradores. `_client.py` arranca el servidor por stdio en su propio
   proceso, con el patrón de `tests/tests_mcp/test_stdio_integration.py`.
2. **Exploración** (6 agentes, uno por eje: flujo feliz, datos difíciles,
   avisos y coste, límites y seguridad, coherencia skill y herramientas,
   calidad de errores). Cada agente actuó como cliente sin leer `server.py`,
   con datasets sintéticos propios (numpy y pandas, semillas fijas), y dejó un
   script por hallazgo que imprime entrada, salida observada, salida esperada y
   `REPRODUCED` (código 0) o `NOT REPRODUCED` (código 1).
3. **Deduplicación** (inline): 45 a 34 (`findings_explored.json`).
4. **Verificación adversarial** (esfuerzo xhigh): 3 escépticos independientes
   por lote, cada uno con una óptica (reproducción y minimalidad; intención
   documentada y cobertura de tests; impacto real en un agente), todos
   ejecutando los scripts y con permiso para leer el código. Sobrevive lo que
   la mayoría no refuta (`verdicts_round1.json`).
5. **Crítico de completitud** y ronda corta de exploración y verificación de
   los huecos relevantes (sección "Segunda ronda").

Entorno: 4 CPU, sin red, sin el backend `chronos` de los modelos
fundacionales; nada llamó a un LLM.

## Hallazgos confirmados

Cada hallazgo indica herramienta, categoría, prioridad, votos (no refutado /
total), script de reproducción (ejecutar desde la raíz del repositorio con
`python <script>`), lo observado frente a lo esperado, el impacto para un
agente, la propuesta de arreglo (no aplicada) y dónde encajaría el test. Las
líneas citadas son de `0.4.x` en el momento de la auditoría.

### Prioridad alta

#### V08. `.` de miles en un CSV con `;` se lee como decimal, sin aviso

- Herramienta: `profile` (y todo lo que sigue). Categoría: bug. Votos: 3/3.
- Reproducción: `reports/mcp-blackbox-audit/b_hard_data/b_01_dot_thousands_silently_decimal.py`.
  Fichero `;` de 60 meses con importes entre 870 y 2050; los menores de 1000
  sin separador y el resto con punto de miles (`2015-04-01;1.020`).
  `profile {data_path, target: "y"}`, luego `plan {steps: 6}` y `forecast`.
- Observado: `profile` responde con éxito, "Target statistics: min 1.01, max
  990", `notices: []`; `forecast` predice entre -2.8 y 979.9, `notices: []`.
  Un escéptico comprobó que también es silencioso si todos los valores son de
  miles (`1.870;1.020;2.987`).
- Esperado: leer `1.020` como 1020 o, como ya se hace para `1,841` en un
  fichero con tabuladores, `data_unreadable` ("decimal mark cannot be told")
  para que el agente pase `sep` y `decimal`. Como mínimo, un
  `DataProfileWarning`.
- Impacto: el SKILL.md dice que `profile` detecta el decimal y que solo se
  pase `decimal` cuando un error lo pida. El agente no recibe ninguna señal y
  reporta un pronóstico y una precisión calculados sobre datos errados en un
  factor 1000. Ninguna entrada del agente lo arregla (`decimal: ","` deja el
  objetivo como texto).
- Causa: `skforecast_ai/profiling/csv_dialect.py:346-371` solo busca
  ambigüedad cuando la muestra tiene `,`; no hay análogo de `THOUSANDS`
  (línea 54) para el punto.
- Arreglo propuesto: en ficheros con `;` o tabulador, si los números con `.`
  encajan todos en `[1-9]\d{0,2}(\.\d{3})+` (junto a enteros sin separador),
  tratarlo como ambiguo y lanzar `data_unreadable`, igual que
  `only_thousands_error` hace para la coma.
- Test: `tests/tests_profiling/test_detect_csv_dialect.py` (caso `.` de miles
  en `;`), y uno de extremo a extremo en `tests/tests_mcp/test_tool_profile.py`.
- Nota: la parte del hallazgo original sobre `"1,020"` entrecomillado en `;`
  leído como 1.02 es la regla prevista y está fijada por
  `test_detect_csv_dialect_decimal_comma_when_semicolon_and_only_thousands`;
  no forma parte del hallazgo confirmado.

### Prioridad media

#### V28. Filas con un campo más que la cabecera no dan `data_unreadable`

- Herramienta: `profile`. Categoría: bug. Votos: 3/3.
- Reproducción: `reports/mcp-blackbox-audit/e_skill_coherence/e_01_extra_field_rows_misparsed.py`
  (mínima: `reports/mcp-blackbox-audit/verify/V28_trailing_sep.py`). Tres
  ficheros de 120 meses: todas las filas de datos terminan en `,`
  (`2015-01-01,100.126,`); solo la primera fila tiene un tercer campo; control
  con un tercer campo en la fila 51.
- Observado: separador final: `insufficient_data` "Target column 'y' has no
  values: every row is missing" (falso). Campo extra en la primera fila: éxito,
  "Exogenous columns: date", objetivo con min = max = 9, 119 de 120 valores
  faltantes, sin índice de fechas. Fila 51: `data_unreadable` "Expected 2
  fields in line 51, saw 3" (correcto).
- Esperado: `data_unreadable` en los tres casos, como dice la tabla de errores
  del SKILL.md ("rows with more fields than the header").
- Impacto: el agente le dice al usuario que la columna no tiene valores, o
  sigue con un perfil sin fechas y con el objetivo casi vacío.
- Causa: `skforecast_ai/profiling/data_profile.py:3205` y `:3214` llaman a
  `pd.read_csv` sin `index_col=False`; pandas convierte la primera columna en
  índice y desplaza las demás.
- Arreglo propuesto: pasar `index_col=False` (y lo mismo en el `read_csv`
  generado, `skforecast_ai/rendering/_helpers.py:540`), y convertir el
  `ParserWarning` de pérdida de datos en `data_unreadable`.
- Test: `tests/tests_profiling/test_read_csv_file.py` (solo cubre la fila
  intermedia) y `tests/tests_rendering/` para el script.

#### V10. MAPE de 3e13 en objetivos que cruzan el cero, con un notice que pide multiplicar por 100

- Herramientas: `plan`, `backtest`. Categoría: bug. Votos: 3/3.
- Reproducción: `reports/mcp-blackbox-audit/b_hard_data/b_03_mape_with_zero_targets.py`.
  Caso A: objetivo mensual entre -10 y 10 con ceros exactos, métrica por
  defecto. Caso B: ventas con meses a cero y `metric:
  "mean_absolute_percentage_error"`.
- Observado: caso A, el panel por defecto incluye MAPE:
  `mean_absolute_percentage_error: 33109663727881.2148` junto a un MAE de
  0.1254; los notices son `MetricReferenceNotice` y `MetricUnitNotice` ("is a
  fraction ... Multiply it by 100"). Caso B: `plan` sin notices, backtest
  6.76e15.
- Esperado: dejar MAPE fuera del panel por defecto si el objetivo toca el cero
  (no solo si el mínimo es 0); con MAPE pedido explícitamente, un notice en
  `plan` de que no está definido; ningún notice que invite a convertir 3e13 en
  porcentaje.
- Impacto: el agente reporta un MAPE de 3e15 % o lo descarta sin una razón del
  servidor, que el skill prohíbe inventar.
- Causa: `skforecast_ai/recommendation/metric_selection.py:80-83`
  (`_target_has_zeros_or_near_zero`) solo mira `abs(min) <= 0.01`.
- Arreglo propuesto: considerar que hay ceros si `min <= 0.01` y `max >= -0.01`;
  añadir el notice en `plan` y no emitir el de "multiplica por 100" cuando el
  valor no tiene sentido.
- Test: `tests/tests_recommendation/test_select_metric.py` (objetivo que cruza
  el cero) y `tests/tests_mcp/test_mape_notices.py`.

#### V11. NaN en una exógena: ningún aviso y luego `execution_failed` que el consejo del plan no arregla

- Herramientas: `profile`, `plan`, `create_cv`, `backtest`. Categoría: bug.
  Votos: 3/3.
- Reproducción: `reports/mcp-blackbox-audit/b_hard_data/b_04_missing_exog_values_fail_late.py`
  (y `verify/V11_where_nan.py`). Exógena `x_na` numérica con 8 celdas `N/A`;
  `profile {exog_columns: ["x_na"]}`, `plan {steps: 6}`, `create_cv`,
  `backtest`; después lo mismo con `dropna_from_series: true`.
- Observado: el resumen del perfil dice "Missing in exog: {'x_na': 8}", pero no
  hay `DataProfileWarning`; `create_cv` sin notices; `backtest` da
  `execution_failed` y `get_failure` "ValueError: Input contains NaN." sin
  nombrar la columna. Con `dropna_from_series: true` (lo primero que sugiere el
  consejo del plan) falla igual. Con un NaN en el fichero de `exog_path` de
  `forecast`, en cambio, el error es preciso y nombra la columna.
- Esperado: `DataProfileWarning` en `profile`, un notice en `create_cv` que
  diga que con este estimador el backtest fallará y qué estimadores aceptan NaN
  (o un `invalid_argument` antes de ejecutar), y que el consejo del plan no
  proponga `dropna_from_series`.
- Impacto: el agente sigue el consejo, gasta ejecuciones y acaba con un error
  que no sabe atribuir.
- Causa: `skforecast_ai/profiling/data_profile.py:3021-3033` solo avisa por
  encima del 20 % de faltantes; los avisos de faltantes de `create_cv`
  (`skforecast_ai/mcp/server.py:366-418`) y `_check_evaluated_target`
  (`skforecast_ai/_utils.py:1961`) solo miran el objetivo.
- Arreglo propuesto: aviso de faltantes en exógenas desde el primer valor, y
  comprobación previa en `create_cv`/`backtest` que nombre la columna.
- Test: `tests/tests_mcp/test_missing_values_notices.py` (hoy solo objetivo) y
  `tests/tests_profiling/test_generate_warnings.py`.

#### V12. Números escritos como texto en una exógena (`12%`, `-`) se vuelven categóricos sin aviso

- Herramientas: `profile`, `backtest`. Categoría: fricción. Votos: 3/3.
- Reproducción: `reports/mcp-blackbox-audit/b_hard_data/b_05_numeric_text_exog_becomes_categorical.py`.
  `x_pct` con `0%`, `1%`, ...; `x_dash` con `1.5`, `2.5` y `-` cada 11 filas.
- Observado: el perfil dice "Categorical exogenous columns: x_pct" sin notice;
  el backtest falla como `execution_failed` ("Input contains NaN", categorías
  no vistas en los folds de test). El mismo `-` en el objetivo da un
  `invalid_argument` claro con `hint`.
- Esperado: tratar la exógena como al objetivo: error o, al menos,
  `DataProfileWarning` "la columna contiene números escritos como texto
  (valores como '12%', '-') y se usa como categórica con N niveles".
- Impacto: un regresor numérico se convierte en una categórica de un nivel por
  valor sin que el agente lo sepa, y el fallo llega tarde y opaco.
- Causa: `skforecast_ai/profiling/data_profile.py:2757-2766`
  (`detect_categorical_exog`) marca como categórica toda columna `object`.
- Arreglo propuesto: reutilizar la detección de `validate_target_numeric`
  (`data_profile.py:3354`) para exógenas y emitir el aviso citando valores.
- Test: `tests/tests_profiling/test_detect_categorical_exog.py`.

#### V16. `create_cv` promete que LGBMRegressor deja correr el backtest, pero un NaN del objetivo en un fold de test falla con cualquier estimador

- Herramientas: `create_cv`, `backtest`. Categoría: bug. Votos: 3/3 (incluye
  el hallazgo duplicado c-06).
- Reproducción: `reports/mcp-blackbox-audit/c_notices/c_01_missing_value_advice_cannot_work.py`
  (y `c_06_missing_value_warning_not_from_folds.py`). 120 meses con `y`
  faltante en 2013-05, 2013-06 y 2017-07 (este dentro de los folds de test).
- Observado: `create_cv` del plan con Ridge: `MissingValuesNotice` "an
  estimator that accepts missing values (such as 'LGBMRegressor', with
  `refine_plan` and a new `create_cv`) lets `backtest` run on every fold". Tras
  `refine_plan {estimator: "LGBMRegressor"}` y `create_cv`: `notices: []`.
  `backtest`: `invalid_argument` "The target has 1 missing value(s) in the test
  folds (2017-07-01) ... whatever the estimator".
- Esperado: `create_cv` ya conoce los folds y las fechas faltantes: debe decir
  que un fold de test contiene un objetivo faltante que ningún estimador evita
  y dar los remedios reales (un `initial_train_size` posterior, o preguntar al
  usuario), sin prometer LGBMRegressor.
- Impacto: el agente cambia de estimador, se lo cuenta al usuario como la
  solución que le dio el servidor y solo después descubre que no servía.
- Causa: `skforecast_ai/mcp/server.py:400-406` (`_missing_values_notices`)
  promete sin condición.
- Arreglo propuesto: ejecutar en `create_cv` la comprobación de
  `_check_evaluated_target` (`skforecast_ai/_utils.py:1961`) contra la nueva
  estrategia y condicionar el texto.
- Test: `tests/tests_mcp/test_missing_values_notices.py` y
  `tests/tests_mcp/test_tool_create_cv.py` (hoy fijan el texto solo con datos
  en los que LGBMRegressor sí ayuda).

#### V22. `target` como lista junto con `series_id_column`: la columna de ids se descarta en silencio

- Herramienta: `profile`. Categoría: bug. Votos: 3/3.
- Reproducción: `reports/mcp-blackbox-audit/d_limits_security/d_01_target_list_drops_series_id.py`.
  `long.csv` con 3 series apiladas (`date, sid, y, y2`):
  `profile {target: ["y"], series_id_column: "sid"}`; control con `target:
  "y"`. Segundo caso: `wide.csv` con `{target: ["y","y2"], series_id_column:
  "x"}`.
- Observado: con `"y"` funciona (3 series). Con `["y"]`: `invalid_argument` en
  `data_path` "Found 72 timestamps with more than one row ... Aggregate or
  remove the repeated rows", con el `hint` "This is a problem of the file of
  the user ... ask before writing a corrected copy". En el fichero ancho, éxito
  con 2 series y `x` no aparece en ningún sitio.
- Esperado: `invalid_argument` en `target`/`series_id_column` para la
  combinación contradictoria, o tratar una lista de un elemento como la cadena;
  nunca culpar al fichero del usuario.
- Impacto: el agente le dice al usuario que su fichero está roto y le ofrece
  escribir una copia corregida de datos que estaban bien.
- Causa: `skforecast_ai/profiling/data_profile.py:1433-1434`
  (`_resolve_data_format`) devuelve `wide` para cualquier lista sin mirar
  `series_id_column`.
- Arreglo propuesto: rechazar la combinación con `field: "series_id_column"`.
- Test: `tests/tests_mcp/test_tool_profile.py` o
  `tests/test_assistant_profile.py`.

#### V02. `missing_dependency` de XGBoost o CatBoost llega sin `hint` ni `details`, y solo al ejecutar

- Herramientas: `plan`, `backtest`, `forecast`. Categoría: desajuste del
  skill. Votos: 3/3 (incluye d-08 y e-03).
- Reproducción: `reports/mcp-blackbox-audit/a_happy_path/a_02_missing_dependency_without_hint.py`
  (también `d_limits_security/d_08_missing_dependency_hint.py` y
  `e_skill_coherence/e_03_missing_dependency_ml_estimator.py`).
  `plan {steps: 12, estimator: "XGBRegressor"}` (lo ofrece el esquema), luego
  `create_cv`, `backtest` y `forecast`.
- Observado: `plan` y `create_cv` sin notices. `backtest`/`forecast`:
  `{"code": "missing_dependency", "message": "XGBRegressor needs the 'xgboost'
  package, which is not installed (pip install xgboost).", "field":
  "estimator", "hint": null, "details": null}`. Para un modelo fundacional, en
  cambio: `hint` con pip y `uvx --with`, reinicio, `details {model_id,
  package}`, `field: "plan_id"`.
- Esperado: el mismo contrato que para los fundacionales (la tabla de errores
  del SKILL.md dice "`hint` says how, for pip and for uvx"), y a ser posible un
  aviso ya en `plan`.
- Impacto: el plugin arranca el servidor con `uvx`; "pip install xgboost" no
  sirve ahí ni menciona el reinicio. `field: "estimator"` no es argumento de
  `forecast` ni de `backtest`.
- Causa: `skforecast_ai/_validation.py:412-422` lanza sin `hint`; el servidor
  solo envuelve los backends fundacionales
  (`skforecast_ai/mcp/_foundation.py:408-441`,
  `skforecast_ai/mcp/server.py:2107-2116`).
- Arreglo propuesto: en `_run_plan_locally` comprobar también los paquetes de
  `SUPPORTED_ESTIMATORS` y lanzar el mismo `ServerError` que para los
  fundacionales; aviso en `plan`.
- Test: `tests/tests_mcp/test_tool_backtest.py` y `test_tool_forecast.py`
  (caso de estimador ML).

#### V01. Un `compare` por defecto con varias series siempre incluye XGBRegressor, que ninguna instalación trae

- Herramientas: `profile`, `create_cv`, `compare`. Categoría: fricción.
  Votos: 3/3 (dos medias, una baja).
- Reproducción: `reports/mcp-blackbox-audit/a_happy_path/a_01_default_compare_runs_uninstallable_xgboost.py`.
  3 series mensuales de 96 filas: `profile`, `plan {steps: 12}`, `create_cv`,
  `compare` sin candidatos.
- Observado: el perfil propone "Alternative estimators: ['XGBRegressor',
  'Ridge']"; `compare_estimator_fits` lo cuenta; el leaderboard pone
  `ForecasterRecursiveMultiSeries+XGBRegressor` en último lugar con "needs the
  'xgboost' package". En la misma respuesta, ForecasterFoundation sin backend
  se deja fuera con `MissingBackendWarning`. `xgboost` no está en ninguna
  dependencia ni extra de `pyproject.toml`. Solo ocurre con 250 o más
  observaciones en total (`forecaster_selection.py:177`), lo habitual en
  multiserie.
- Esperado: el mismo tratamiento que el backend fundacional: dejar fuera el
  candidato cuyo paquete no está instalado, con aviso, y no contarlo en el
  coste.
- Impacto: todo `compare` multiserie por defecto reporta "1 configuration
  failed"; el agente gasta una llamada a `get_failure` y recomienda instalar un
  paquete que el usuario no pidió (con el consejo de pip de V02).
- Causa: `skforecast_ai/execution/comparison.py:484`
  (`resolve_default_candidates`) solo comprueba `missing_foundation_backend`.
- Arreglo propuesto: comprobar `find_spec` del paquete de cada estimador
  candidato por defecto, o no proponer en el perfil estimadores no instalados.
- Test: `tests/tests_mcp/test_tool_compare.py::test_tool_compare_default_candidates_of_the_profile`
  hoy acepta el fallo ("A candidate whose library is not installed (XGBoost)
  fails, as it may"); habría que cambiar esa expectativa.

#### V04. Un plan multiserie con intervalo no recibe el aviso de pocos residuos

- Herramientas: `create_cv`, `backtest`. Categoría: fricción. Votos: 3/3 (dos
  medias, una baja).
- Reproducción: `reports/mcp-blackbox-audit/a_happy_path/a_04_multiseries_interval_without_residual_notice.py`.
  Mismo plan `{steps: 12, interval: [0.1, 0.9], estimator: "Ridge",
  window_features: [{stats: ["mean"], window_size: 24}]}` para una serie y para
  tres.
- Observado: con una serie, `create_cv` avisa "leaves 43 row(s) to train on
  ... intervals tend to be too narrow". Con tres series, `notices: []`, y 5 de
  87 filas del backtest tienen la predicción fuera de su propio intervalo.
- Esperado: el mismo aviso, contando filas por serie en la primera ventana.
- Impacto: el skill manda reportar intervalos desde `files.predictions` leyendo
  antes los notices; con varias series el agente pierde la advertencia de que
  son demasiado estrechos.
- Causa: `skforecast_ai/recommendation/backtesting.py:1508-1510`:
  `_RESIDUAL_INTERVAL_FORECASTERS` excluye ForecasterRecursiveMultiSeries,
  aunque también usa residuos in-sample por bins.
- Arreglo propuesto: incluir los forecasters multiserie con bootstrapping.
- Test: `tests/tests_recommendation/test_warn_interval_residuals.py`.

#### V25. Claves desconocidas en una entrada de `window_features` se ignoran y el resumen las muestra como elegidas

- Herramientas: `plan`, `refine_plan`, `compare`. Categoría: desajuste del
  skill. Votos: 3/3 (incluye f-02).
- Reproducción: `reports/mcp-blackbox-audit/d_limits_security/d_04_window_features_unknown_key.py`
  y `f_errors/f_02_window_features_unknown_keys_ignored.py`.
  `plan {window_features: [{stats: ["mean"], window_size: 3, min_periods: 2},
  {stats: ["max"], window_size: 6, windows_size: 24}]}`.
- Observado: plan correcto, `notices: []`; el resumen dice "Window features:
  [{... 'min_periods': 1}]" bajo "Chosen by the user instead of the rules"; el
  script de `get_code` no tiene `min_periods` ni 24. Una clave desconocida en
  `candidates[0].config` sí se rechaza.
- Esperado: `invalid_argument` en `window_features` nombrando las claves.
- Impacto: el SKILL.md promete "an unknown argument ... is an error, never
  ignored"; el agente reporta una configuración que nunca corrió.
- Causa: `skforecast_ai/_validation.py:943-1000` no comprueba claves extra;
  `skforecast_ai/mcp/models.py:117` (`list[dict[str, list[str] | int]]`)
  admite cualquiera.
- Arreglo propuesto: `TypedDict` cerrado o validación explícita.
- Test: `tests/tests_mcp/test_tool_plan.py`.

### Prioridad baja

#### V17. `create_cv` acepta `skip_folds` para ForecasterStats y el backtest falla opaco

- Herramientas: `create_cv`, `backtest`, `compare`. Categoría: bug. Votos: 3/3
  (una media).
- Reproducción: `reports/mcp-blackbox-audit/c_notices/c_02_stats_skip_folds_accepted_then_fails.py`.
  `plan {steps: 6, forecaster: "ForecasterStats"}`, `create_cv
  {initial_train_size: 84, skip_folds: 2}`, `backtest`.
- Observado: `create_cv` sin notices y con coste reducido; `backtest`:
  `execution_failed` sin `field`; `get_failure`: "`skip_folds` is not allowed
  for ForecasterStats". Un `compare` por defecto sobre esa estrategia ejecuta
  Stats y lo pone último. El servidor conoce la regla (su propio
  `LongTrainingWarning` la cita).
- Esperado: `invalid_argument` en `skip_folds`, como ya hace con otras
  estrategias que no podrían correr; en `compare` por defecto, dejar Stats
  fuera con aviso.
- Arreglo propuesto: validar en `build_cv`
  (`skforecast_ai/recommendation/backtesting.py:968`) y en
  `resolve_default_candidates`.
- Test: `tests/tests_mcp/test_tool_create_cv.py`.

#### V18. El aviso de coste ofrece `refit` para ForecasterStats y modelos fundacionales, que no baja su coste

- Herramienta: `create_cv`. Categoría: fricción. Votos: 3/3.
- Reproducción: `reports/mcp-blackbox-audit/c_notices/c_03_cost_notice_refit_advice_for_stats.py`.
- Observado: Stats con 51 ajustes: `CostNotice` "tell the user ... the cheaper
  strategies (an integer `refit`, fewer folds, `refit=false`)" con `refit` ya
  en false; `refit: false` y `refit: 5` siguen costando 51. El
  `LongTrainingWarning` de la misma respuesta dice "refits it in every fold
  whatever `refit` says". Igual para un plan fundacional con 2050 ventanas.
- Esperado: ofrecer solo remedios que bajan el coste (menos folds, menos
  series) y no proponer `refit=false` cuando ya lo es.
- Arreglo propuesto: pasar forecaster y `refit` a `_cost_notices`
  (`skforecast_ai/mcp/server.py:470-480`) y alinear la regla 2 de las
  instrucciones del servidor.
- Test: `tests/tests_mcp/test_tool_create_cv.py::test_tool_create_cv_cost_and_notices_of_inference_windows`
  fija hoy el texto genérico.

#### V19. `compare` con candidatos que suman 78 ajustes corre sin aviso de coste

- Herramienta: `compare`. Categoría: desajuste del skill. Votos: 3/3.
- Reproducción: `reports/mcp-blackbox-audit/c_notices/c_04_compare_candidates_cost_unannounced.py`.
  `create_cv {initial_train_size: 84, refit: true}` y `compare` con dos
  ForecasterDirect y un recursivo.
- Observado: `create_cv` da `compare_estimator_fits: 48` (solo vale sin
  candidatos); `compare` reporta `estimator_fits: 78` y solo
  `MetricUnitNotice`. El umbral se aplica por candidato, no al total (las
  ventanas de inferencia sí se suman).
- Esperado: el SKILL.md dice que un `compare` "above those thresholds" debe
  pararse antes; o se avisa sobre el total, o el skill dice que el umbral es
  por candidato y que con candidatos no hay estimación previa.
- Arreglo propuesto: avisar sobre la suma en `skforecast_ai/assistant.py:3649-3662`,
  o una estimación previa del coste de una lista de candidatos.
- Test: `tests/test_assistant_compare.py` y `tests/tests_mcp/test_tool_compare.py`.

#### V14. Fechas ISO 8601 irregulares reciben el consejo de escribirlas en ISO 8601

- Herramienta: `plan`. Categoría: fricción. Votos: 3/3.
- Reproducción: `reports/mcp-blackbox-audit/b_hard_data/b_07_irregular_iso_dates_get_dayfirst_hint.py`.
  Diario en ISO con 40 días al azar faltantes.
- Observado: perfil "Frequency: unknown", "Index irregularities: none
  detected"; `plan`: `invalid_argument` sobre fechas día-primero y `hint`
  "Write the dates in ISO 8601 (such as '2023-02-13'), so they are not read
  month-first."
- Esperado: mencionar día-primero solo si las fechas no son ISO; si no,
  describir el espaciado irregular (frecuencia más cercana y huecos).
- Arreglo propuesto: condicionar el texto en
  `skforecast_ai/assistant.py:388-410` (`_check_frequency_known`) y registrar
  la irregularidad en `data_profile.py:2970-2974`.
- Test: `tests/test_assistant_plan.py` (hoy solo fechas no ISO).

#### V29. `refine_plan` con un estimador nuevo descarta en silencio los `estimator_kwargs` omitidos

- Herramienta: `refine_plan`. Categoría: desajuste del skill. Votos: 3/3.
- Reproducción: `reports/mcp-blackbox-audit/e_skill_coherence/e_04_refine_estimator_drops_kwargs.py`.
- Observado: `LGBMRegressor(n_estimators=50, verbose=-1)` refinado con
  `{estimator: "RandomForestRegressor"}` da `RandomForestRegressor(random_state=123)`,
  sin notice.
- Esperado: el SKILL.md y la descripción de `overrides` dicen "An omitted key
  keeps the value of the plan" sin excepción. El descarte es intencionado en la
  API de Python (y está en `releases.md`), pero el agente no lo sabe.
- Arreglo propuesto: documentar la excepción en
  `skforecast_ai/mcp/models.py:133-135` y en el paso 3 del SKILL.md, o un
  notice que nombre los kwargs descartados.
- Test: `tests/tests_mcp/test_tool_refine_plan.py`.

#### V24. `compare` con candidatos deja fuera el plan refinado de la estrategia sin decirlo, y "Strategy plan" no es un nombre reservado

- Herramienta: `compare`. Categoría: desajuste del skill. Votos: 2/3.
- Reproducción: `reports/mcp-blackbox-audit/e_skill_coherence/e_02_compare_candidates_drop_strategy_plan.py`
  y `d_limits_security/d_03_candidate_named_strategy_plan.py`.
- Observado: estrategia de un plan con `lags: 2` y candidatos `ridge` y uno
  llamado `Strategy plan` (RandomForest). El plan refinado no corre (su MAE en
  ese cv es 1.8939 y no está en ninguna fila); el resumen dice "The strategy
  was created for the plan (ForecasterRecursive + Ridge)", que coincide con la
  etiqueta de `ridge`, y una fila "Strategy plan" que no es el plan del
  usuario.
- Por qué sobrevive pese a estar documentado en el esquema: la frase del paso 6
  del SKILL.md ("When the strategy was created for another plan ... that plan
  runs too") no se condiciona a "sin candidatos", y el skill manda reportar la
  fila "Strategy plan" como el plan del usuario.
- Arreglo propuesto: reservar `STRATEGY_PLAN_NAME` como los nombres del
  baseline, decir en el resumen que el plan de la estrategia no se comparó, y
  condicionar la frase del skill.
- Test: `tests/tests_mcp/test_tool_compare.py`.

#### V21. `fixed_train_size` sin `refit`: el esquema dice que es un error, el servidor solo avisa

- Herramienta: `create_cv`. Categoría: desajuste del skill. Votos: 2/3
  (incluye d-07 y e-07).
- Reproducción: `reports/mcp-blackbox-audit/c_notices/c_07_fixed_train_size_warning_not_error.py`.
- Observado: éxito con `IgnoredArgumentWarning` "has no effect"; la
  descripción del esquema (`skforecast_ai/mcp/server.py:1945-1950`) dice "with
  `refit` false or null it is an error, as it would not run".
- Arreglo propuesto: corregir la descripción y regenerar
  `tests/tests_mcp/golden/tool_schemas.json`, que hoy fija el texto erróneo.

#### V06. `cost.n_fits` de `compare` es el de la estrategia, no el total

- Herramienta: `compare`. Categoría: desajuste del skill. Votos: 2/3.
- Reproducción: `reports/mcp-blackbox-audit/a_happy_path/a_06_compare_cost_n_fits_not_total.py`.
- Observado: dos candidatos Ridge: `{n_fits: 1, estimator_fits: 2}`; con
  `refit: true` y tres candidatos: `{n_fits: 3, estimator_fits: 42}`.
- Por qué sobrevive: el esquema de salida lo documenta ("trainings of the
  forecaster in the shared strategy") y un test lo fija, pero el SKILL.md dice
  "its response reports the totals" y define `n_fits` como entrenamientos del
  forecaster. Solo cambia la redacción del skill.
- Arreglo propuesto: precisarlo en la sección Cost del SKILL.md (o sumar
  `n_fits`).

#### V03. `get_code` de un forecast con `exog_path` lee `exog_future.csv` del directorio de trabajo

- Herramienta: `get_code`. Categoría: desajuste del skill. Votos: 2/3.
- Reproducción: `reports/mcp-blackbox-audit/a_happy_path/a_03_get_code_exog_reads_another_file.py`.
- Observado: el script lee los datos por ruta absoluta pero
  `pd.read_csv('exog_future.csv')`; ejecutado tal cual falla con
  `FileNotFoundError`. La respuesta de `get_code` no lo dice; solo la
  descripción de `forecast.exog_path`.
- Por qué sobrevive: el SKILL.md manda entregar el script "as it is" para
  reproducir sin el servidor.
- Arreglo propuesto: renderizar la ruta que corrió
  (`skforecast_ai/rendering/_helpers.py:766`) o añadir una nota en la
  respuesta de `get_code` y en el skill.
- Test: `tests/test_integration_standalone_script.py`.

#### V05. El CSV de métricas de `forecast` con `test_size` usa abreviaturas y la columna `series`

- Herramienta: `forecast`. Categoría: fricción. Votos: 2/3 (incluye e-05).
- Reproducción: `reports/mcp-blackbox-audit/a_happy_path/a_05_holdout_metrics_csv_other_names.py`.
- Observado: `['series', 'MAE', 'MSE', 'MASE', 'MAPE']` (y `MedAE`) frente a
  los nombres de skforecast y `levels` del backtest; el `MetricReferenceNotice`
  de la misma respuesta nombra `mean_absolute_scaled_error`.
- Arreglo propuesto: usar los nombres de skforecast y `levels` en
  `skforecast_ai/rendering/_helpers.py:80-140`, o documentar la tabla en el
  skill.
- Test: `tests/tests_mcp/test_tool_forecast.py`.

#### V20. sMAPE sale en porcentaje y MAPE en fracción; solo MAPE tiene aviso de unidad

- Herramientas: `backtest`, `forecast`, `compare`. Categoría: mejora.
  Votos: 2/3.
- Reproducción: `reports/mcp-blackbox-audit/c_notices/c_05_smape_unit_without_notice.py`.
- Observado: mismo backtest, MAPE 0.011278 y sMAPE 1.136376; solo el notice
  de MAPE ("multiply it by 100").
- Arreglo propuesto: añadir sMAPE a `_mape_notices`
  (`skforecast_ai/mcp/server.py:586-615`) diciendo que ya es un porcentaje.
- Test: `tests/tests_mcp/test_mape_notices.py`.

#### V23. Una lista de `target` con una columna repetida se acepta como dos series

- Herramienta: `profile`. Categoría: bug. Votos: 2/3 (incluye f-01).
- Reproducción: `reports/mcp-blackbox-audit/d_limits_security/d_02_duplicate_target_list.py`.
- Observado: `target: ["y", "y"]` da "Series: 2" y recomienda multiserie;
  `exog_columns: ["x", "x"]` se rechaza con "names a column more than once".
- Arreglo propuesto: la misma comprobación en `_validate_target_exists`
  (`skforecast_ai/profiling/data_profile.py:3413`).
- Test: `tests/test_assistant_profile.py`.

#### V30. Un hold-out cuyo tramo de entrenamiento es más corto que la ventana falla como `execution_failed`

- Herramienta: `forecast`. Categoría: fricción. Votos: 2/3.
- Reproducción: `reports/mcp-blackbox-audit/f_errors/f_03_holdout_short_train_execution_failed.py`.
- Observado: 120 meses, `plan {steps: 90}` aceptado, `forecast {test_size:
  90}`: `execution_failed` sin `field` ni `hint`; `get_failure`: "Length `y`:
  30. Max window size: 36". La tabla de errores del skill dice que una serie
  demasiado corta llega como `insufficient_data`.
- Arreglo propuesto: comprobar la partición de entrenamiento en
  `skforecast_ai/_last_window.py:754-800` y lanzar `insufficient_data` con
  `field: "test_size"`.
- Test: `tests/test_validate_evaluation_partition.py`.

#### V31. `create_cv` solo con `plan_id` culpa a `initial_train_size`, que el agente no envió

- Herramienta: `create_cv`. Categoría: fricción. Votos: 2/3 (incluye f-05).
- Reproducción: `reports/mcp-blackbox-audit/f_errors/f_04_create_cv_default_blames_unset_initial_train_size.py`
  y `f_05_create_cv_gap_skip_folds_wrong_field.py`.
- Observado: con `steps: 90` sobre 120 filas, `invalid_argument` en
  `initial_train_size` "If `initial_train_size` is a date, it must be within
  the index range"; con `steps: 80`, el `insufficient_data` claro con el
  consejo del hold-out. `gap` y `skip_folds` grandes dan `field: null` y un
  `hint` que no los nombra.
- Arreglo propuesto: en `_strategy_error`
  (`skforecast_ai/recommendation/backtesting.py:1066-1110`) reconocer todos
  los nombres de la expresión entre comillas invertidas, no culpar a un
  argumento por defecto y citar `gap`/`skip_folds` en el `hint`.
- Test: `tests/tests_mcp/test_tool_create_cv.py`.

#### V15. El error de objetivo no numérico por separadores de miles o `%` da el consejo de marcadores de faltantes

- Herramienta: `profile`. Categoría: mejora. Votos: 2/3.
- Reproducción: `reports/mcp-blackbox-audit/b_hard_data/b_08_not_numeric_target_hint.py`.
- Observado: para `"10,025.1"` y `10.0%`, `field: "target"` y `hint` "Leave
  the cells of missing values empty instead of marking them with text such as
  '-' or '?'".
- Arreglo propuesto: `hint` específico del formato, y aplicar el
  `DATA_PROBLEM_HINT` del servidor (`skforecast_ai/mcp/server.py:1680-1684`).
- Test: `tests/tests_profiling/test_validate_target_numeric.py`.

#### V13. Una columna de fechas `yyyymmdd` entera se usa como exógena

- Herramientas: `profile`, `plan`. Categoría: mejora. Votos: 2/3.
- Reproducción: `reports/mcp-blackbox-audit/b_hard_data/b_06_compact_integer_dates.py`.
- Observado: "Exogenous columns: date", "Frequency: unknown"; el plan pide al
  usuario valores futuros de `date`; con `date_column: "date"`, "could not be
  parsed as timestamps". Hay un `DataProfileWarning` "No datetime index
  detected" que un agente cuidadoso reportaría.
- Arreglo propuesto: probar `%Y%m%d` en columnas enteras de 8 cifras
  (`skforecast_ai/profiling/data_profile.py:1303-1356`) o avisar de que una
  columna con nombre de fecha se usa como exógena.
- Test: `tests/tests_profiling/test_detect_date_column.py`.

#### V33. `plan` valida los nombres de `estimator_kwargs` pero no sus valores

- Herramientas: `plan`, `forecast`. Categoría: mejora. Votos: 2/3.
- Reproducción: `reports/mcp-blackbox-audit/f_errors/f_07_estimator_kwargs_values_not_validated.py`.
- Observado: `{alpha: "abc"}` en Ridge se acepta; `forecast` da
  `execution_failed` (InvalidParameterError); una clave desconocida sí se
  rechaza en `plan`.
- Arreglo propuesto: para estimadores de scikit-learn, instanciar y llamar a
  `_validate_params()` en `plan` (`skforecast_ai/_validation.py:299-375`).
- Test: `tests/tests_mcp/test_tool_plan.py`.

## Segunda ronda: crítico de completitud

El crítico revisó cobertura, notas de "no cubierto" de cada explorador y los
tests, y marcó 8 huecos relevantes y sondeables aquí: ForecasterDirectMultiVariate
de extremo a extremo, codificaciones y dialectos no UTF-8, progreso y
cancelación en ejecuciones largas reales, fechas con zona horaria y
frecuencias no diarias, `data_changed` más allá de lo que cubren los tests,
datos largos multiserie difíciles, límites del almacén de objetos y
combinaciones de argumentos de `compare`. Un explorador de caja negra los
sondeó todos (scripts en `reports/mcp-blackbox-audit/g_gaps/`) y 2 escépticos
xhigh verificaron sus 5 hallazgos; ninguno quedó empatado, así que no hizo
falta desempate. Los 5 sobreviven (2/2). Datos crudos en `gaps_round2.json`.

### Prioridad alta

#### G02. Ids de serie numéricos (`001`, `1`) hacen fallar todo backtest, forecast y compare con `KeyError: 1`

- Herramientas: `profile`, `backtest`, `forecast`, `compare`, `get_code`.
  Categoría: bug. Votos: 2/2.
- Reproducción: `reports/mcp-blackbox-audit/g_gaps/g_02_numeric_series_ids_fail_every_run.py`.
  Datos largos `store,date,sales` con tiendas `001`, `002`, `010` (96 meses
  cada una): `profile {target: "sales", series_id_column: "store"}`, `plan
  {steps: 12}`, `create_cv`, `backtest`, `forecast`, `compare`; control con
  ids `S01`, `S02`, `S10`.
- Observado: el perfil llama a las series `1`, `2`, `10` (se pierden los
  ceros) sin notices. `backtest` y `forecast`: `execution_failed`, `field` y
  `hint` nulos; `compare`: `all_candidates_failed`; `get_failure`: `KeyError:
  1` dentro de skforecast (`encoding_mapping_[series_name_k]`). El script de
  `get_code` falla igual fuera del servidor. Con ids enteros sin ceros
  (`1`, `2`, `10`) pasa lo mismo; con letras funciona.
- Esperado: conservar los ids como texto del fichero y ejecutar como con
  letras; como mínimo, un error previo con `field: "series_id_column"` y un
  `hint`.
- Impacto: los ids de tienda, SKU o sensor suelen ser numéricos o con ceros a
  la izquierda. El flujo entero queda bloqueado: la traza que el skill manda
  leer no apunta a los ids, el agente no puede proponer el arreglo y además
  reporta `1` y `2` a un usuario que conoce `001` y `002`.
- Causa: la columna de ids se lee sin `dtype` al perfilar
  (`skforecast_ai/_utils.py:894`, `:1026`) y en el `read_csv` generado
  (`skforecast_ai/rendering/_helpers.py:540`, reshape en `:1395-1430`);
  skforecast 0.26 construye `encoding_mapping_` con claves `str` y busca con
  el entero.
- Arreglo propuesto: leer `series_id_column` con `dtype=str` en el perfil y en
  el script (o emitir `astype(str)` antes del reshape), con su golden de
  renderizado.
- Test: `tests/tests_rendering/` (script byte a byte),
  `tests/test_integration_standalone_script.py` y
  `tests/tests_mcp/test_tool_backtest.py` con ids `001`.

### Prioridad media

#### G01. ForecasterDirectMultiVariate hereda el estimador elegido para las series agrupadas y su backtest repite un modelo constante

- Herramientas: `plan`, `backtest`. Categoría: bug. Votos: 2/2.
- Reproducción: `reports/mcp-blackbox-audit/g_gaps/g_01_direct_multivariate_keeps_pooled_estimator.py`.
  3 series mensuales anchas de 96 fechas: `profile {target: [a, b, c]}`,
  `plan {steps: 12, forecaster: "ForecasterDirectMultiVariate"}`,
  `create_cv`, `backtest`, `compare` con el estimador del plan frente a Ridge.
- Observado: el plan mantiene "Estimator: LGBMRegressor" con la razón "288
  observations" (las tres series agrupadas), aunque DMV entrena con una fila
  por fecha (96, 67 en la primera ventana); la misma serie sola recibe Ridge
  por ser pequeña. Las predicciones del backtest son idénticas en todos los
  folds (LGBM no encuentra ningún corte): MASE 3.587, frente a 0.488 de DMV
  con Ridge en los mismos folds. Ningún notice.
- Esperado: la regla del estimador debe usar las filas con las que entrena DMV
  (daría Ridge), y la explicación no debe dar una razón falsa.
- Impacto: el agente deja el estimador a las reglas, como manda el skill,
  reporta MASE 3.59 como la precisión de DMV y repite al usuario una razón que
  no se aplica.
- Causa: `skforecast_ai/assistant.py:1088-1095` recalcula el estimador al
  cambiar a la tarea `multivariate` con `data_profile.n_total_observations`;
  la razón sale de `skforecast_ai/recommendation/explanation.py:306`.
- Arreglo propuesto: para `multivariate`, pasar `span_index_length` a
  `select_estimator_and_candidates` y a la explicación.
- Test: `tests/test_assistant_plan.py` (hoy solo comprueba el forecaster).

#### G03. Una serie demasiado corta desaparece en silencio de un backtest multiserie, y luego `forecast` falla por ella

- Herramientas: `profile`, `create_cv`, `backtest`, `forecast`. Categoría:
  bug. Votos: 2/2 (una media, una baja).
- Reproducción: `reports/mcp-blackbox-audit/g_gaps/g_03_short_series_dropped_from_backtest.py`
  (y `verify/g03_summaries.py`). Datos largos con S01 y S10 de 96 meses y S02
  con los últimos 20.
- Observado: perfil y plan dicen "Short series: only 20 observations" sin
  nombrar la serie; `create_cv` sin notices; el backtest termina con "Results
  (average across series): ... mean_absolute_scaled_error: 0.4715", una fila
  de S02 toda NaN en `files.metrics` y ninguna fila de S02 en las predicciones.
  `forecast` del mismo plan: `insufficient_data` "('S02': 20)".
- Esperado: nombrar la serie corta en el perfil y que `create_cv` o el
  backtest digan que S02 no se pronostica en ningún fold y que un `forecast`
  fallará; no presentar una media "across series" que la excluye.
- Impacto: siguiendo el skill (sin baseline, leer las filas por serie y
  nombrar la peor), el agente reporta la precisión de las tres tiendas y no
  puede nombrar la peor, que es la que nunca se pronosticó.
- Causa: `skforecast_ai/_last_window.py:816` salta la comprobación de
  longitud en backtesting (intencionado para series que empiezan tarde, pero
  también deja pasar series que nunca superan la ventana);
  `skforecast_ai/execution/backtesting_runner.py:212` promedia ignorando NaN.
- Arreglo propuesto: en backtesting, detectar series cuyo tramo nunca supera
  la ventana y lanzar `insufficient_data` o emitir un notice que las nombre.
- Test: `tests/test_validate_series_lengths.py` y
  `tests/tests_mcp/test_tool_backtest.py`.

#### G04. `forecast` con `test_size` como fecha ISO con zona horaria da `internal_error`

- Herramienta: `forecast`. Categoría: bug. Votos: 2/2.
- Reproducción: `reports/mcp-blackbox-audit/g_gaps/g_04_test_size_with_time_zone_internal_error.py`.
  Serie horaria con fechas `2024-03-20T00:00:00Z`: `plan {steps: 24,
  estimator: "Ridge"}`, `forecast {test_size: "2024-04-09T00:00:00Z"}`, luego
  `+00:00`, luego sin zona; lo mismo sobre una copia sin zona.
- Observado: con `Z` o `+00:00`, `internal_error` (TypeError), `hint` "Report
  it to the user with the id; do not retry with the same inputs"; el log del
  servidor dice "Cannot compare tz-naive and tz-aware timestamps"
  (`resolve_end_train`). Sin zona funciona. `create_cv` acepta
  `initial_train_size` con zona en datos UTC, y en datos sin zona responde un
  `invalid_argument` claro.
- Esperado: el mismo tratamiento que `create_cv`; nunca `internal_error` para
  una entrada del usuario.
- Impacto: el skill manda pasar la fecha ISO en la que empieza el test; con
  datos UTC el agente la escribe con `Z`, recibe "no reintentes" y reporta un
  fallo del servidor en vez de quitar la zona.
- Causa: `skforecast_ai/assistant.py:4498-4503` llama a `resolve_end_train`
  sin la zona de los datos; `skforecast_ai/profiling/data_profile.py:4043-4047`
  compara fuera del `try`.
- Arreglo propuesto: pasar `DataProfile.time_zone` y construir el índice como
  en `create_cv` (`_aware_index`); en datos sin zona, `InvalidInputError` en
  `test_size`.
- Test: `tests/tests_profiling/test_resolve_end_train.py` y
  `tests/test_assistant_forecast.py`.

### Prioridad baja

#### G05. El primer `get_code` de la sesión bloquea el bucle de eventos durante una ejecución larga

- Herramienta: `get_code` (y, de rebote, las demás de lectura). Categoría: bug.
  Votos: 2/2.
- Reproducción: `reports/mcp-blackbox-audit/g_gaps/g_05_first_get_code_waits_for_stats_run.py`
  (y `verify/g05_event_loop_blocked.py`). Backtest de ForecasterStats de 10
  folds (unos 20 s) y, 2 s después, en paralelo `list_objects`,
  `describe_object` y `get_code`; control con un `get_code` previo.
- Observado: `list_objects` y `describe_object` responden en 0.1 s;
  `get_code` tarda unos 19 a 22 s (el backtest termina a los 21 a 24 s), sin
  progreso. Un escéptico mostró que es peor: un `list_objects` enviado 1 s
  después de ese `get_code` también espera, porque se bloquea todo el bucle de
  eventos. En el control responde en 0.1 s.
- Esperado: el SKILL.md dice que durante una ejecución larga responden las
  herramientas de lectura, `get_code` incluida.
- Impacto: riesgo de timeout del cliente en una llamada que el agente espera
  instantánea, y bloqueo del resto de lecturas.
- Causa: `get_code` es asíncrona y llama a `_requirements` en el bucle de
  eventos (`skforecast_ai/mcp/server.py:2673`); la primera vez,
  `_distributions()` hace un `importlib.metadata.packages_distributions()` en
  frío (`server.py:1293`) que, compitiendo por el GIL con el hilo de
  ForecasterStats, tarda decenas de segundos.
- Arreglo propuesto: precalentar `_distributions()` en el hilo de precarga
  (`skforecast_ai/mcp/_preload.py`) o ejecutar `_requirements` con
  `anyio.to_thread.run_sync`.
- Test: `tests/tests_mcp/test_concurrency.py` (una lectura durante una
  ejecución, con la caché de `_distributions` vacía).


## Descartados

| Clave | Hallazgo | Votos | Por qué se descartó |
|---|---|---|---|
| V07 | El error de `differentiation` distinta ofrece "pass the same `differentiation`", que `create_cv` no acepta | 0/3 | Las dos opciones del mensaje funcionan con las herramientas (`create_cv` del plan, o `refine_plan` de la diferenciación), y el paso 2 del skill ya indica crear la estrategia desde ese plan (`verify/V07_both_options.py`). |
| V09 | Un `decimal` explícito que no encaja se acepta y luego se sustituye en la ejecución | 1/3 | Lo dispara un `decimal` que el skill dice no pasar sin error previo; la redetección del dialecto al ejecutar es diseño documentado, y el script del plan da las mismas predicciones (`verify/V09_same_numbers.py`). |
| V26 | El coste ignora el tamaño del estimador (`n_estimators=1e8`) y la cancelación no detiene el trabajo | 0/3 | El coste se define como recuentos, no tiempo, y el skill documenta que cancelar espera a que termine la herramienta; la entrada no es realista. |
| V27 | `url_not_allowed` manda descargar el fichero incluso para un `file://` dentro del directorio | 0/3 | Coincide con "No URLs: download the file first" del skill y la tabla de errores manda pasar la ruta absoluta; un `file://` interno no es una entrada realista. |
| V32 | `compare` ejecuta candidatos que `plan` rechazaría y `all_candidates_failed` solo nombra la clase | 1/3 | Con el baseline por defecto el resumen y el leaderboard muestran el mensaje completo; `get_failure` lo da en el caso de todos fallidos. Un escéptico sí encontró un bug real en la segunda parte: `InvalidInputError` se reporta como `ValueError` (`skforecast_ai/exceptions.py:141-169`), así que `skforecast_ai/mcp/_errors.py:304-307` no reconoce el mensaje propio y lo omite, y el test `test_failure_text.py` construye a mano un `CandidateFailure` que `compare` nunca produce. Queda anotado como observación, no como hallazgo confirmado. |
| V34 | Un id con un carácter mal escrito se atribuye a "otra ejecución del servidor" | 1/3 | El `hint` manda a `list_objects` y la tabla del skill pone esa acción primero; rehacer el objeto es inofensivo porque todo es determinista. |

En la segunda ronda no se descartó ningún hallazgo. El explorador sí anotó,
sin registrarlos como hallazgos, el comportamiento de una petición encolada
tras una ejecución larga (no recibe progreso mientras espera su turno, lo que
el skill documenta) y `get_failure(comparison_id)` sin candidato, que responde
"has no failed candidate named None" con la lista de candidatos fallidos
(filtra un `None` de Python y `hint` nulo, pero el agente puede recuperarse).

## Qué no se pudo cubrir

- **Modelos fundacionales en ejecución**: sin `chronos` ni red solo se
  observaron `missing_dependency`, `model_not_allowed` y el
  `ModelDownloadNotice` del plan. No se probaron la inferencia, el
  `ModelLicenseNotice`, `--allow-model` con prefijos restringidos ni
  `HF_HUB_OFFLINE`.
- **XGBoost y CatBoost funcionando**: no están instalados; solo se vio su
  camino de fallo (V01, V02).
- **Límites de truncado**: resumen de 20.000 caracteres (120 candidatos con
  nombres largos dieron 12.132), notice de 1.000, `hint` de 1.000 y texto de
  `details` de 500. El servidor resume las listas ("first 5 of N") antes de
  llegar ahí, así que ninguna entrada de caja negra los alcanzó. Sí se vio el
  corte del mensaje a 4.000 y `notices_omitted` con más de 20 notices.
- **`internal_error`** provocado por una entrada normal: solo G04. No se pudo
  observar la forma de `details.error_id` en otro caso.
- **Expulsión por memoria** (`--max-memory-mb 1`): no expulsó nada ni con un
  perfil de 100.000 filas y un backtest de 1.600 folds; el caso de un objeto
  mayor que el límite queda sin observar. La expulsión por número sí se probó.
- **Ficheros de cientos de MB** y `--max-file-mb 0` con un fichero grande real;
  un cliente que se desconecta durante el perfil de un `.gz` grande; un cliente
  que deja de leer stdout (contrapresión); carrera de symlink entre la
  comprobación y la lectura; hosts Windows.
- **Un cliente con timeout real**: se midió el silencio de una llamada encolada
  y el de G05, pero no se provocó un timeout ni un objeto huérfano.
- **Restos menores sin script**: fechas `00:00:00` en el
  `HoldoutEvaluationNotice`, `mean_absolute_scaled_error` NaN con "Mean of
  empty slice", fechas día-primero en el `exog_future` de datos largos, DMV con
  `refit: true`.

Presupuesto de agentes: el encargo pedía unos 12; se usaron 16 (6
exploradores, 6 escépticos en la primera ronda, crítico, explorador de huecos y
2 escépticos). La diferencia viene de verificar los 34 hallazgos en dos lotes
para que cada escéptico pudiera ejecutar todos los scripts de su lote.


## Comportamientos comprobados como correctos

Para que el informe no se lea como "todo está mal", lo que los exploradores
probaron y funcionó como promete el contrato:

- **Flujo feliz** (serie única, multiserie larga y ancha, exógenas): ids y
  `links` encadenados (incluido `best_plan_id` y `parent_plan_id`), ficheros
  existentes con las columnas esperadas (`pred`, `lower_bound`,
  `upper_bound`, `level`, `fold`), métricas por serie con media, media
  ponderada y pooling, `FutureExogNotice`, `HoldoutEvaluationNotice`,
  `MetricReferenceNotice`, fila "Strategy plan" tras `refine_plan` sin
  candidatos, baselines correctos (estacional mensual, naive semanal, ninguno
  multiserie con el motivo en el resumen), `test_size` entero, fecha y
  fracción. Los scripts de `get_code` ejecutados fuera del servidor
  reproducen exactamente los números (por ejemplo MAE 1.4999 del backtest,
  0.9018 del mejor de `compare`, 6.0162 del baseline).
- **Datos**: `.tsv`, `.csv.gz` y `.tsv.gz` dan el mismo perfil; `;` con decimal
  `,` se detecta y se conserva en los scripts; mezclas de decimales dan
  `data_unreadable` con buen `hint`; BOM, líneas en blanco finales, nombres con
  espacios, acentos y `€`; días hábiles detectados como `B`; fechas día-primero
  y formatos mezclados con errores precisos; NaN en el objetivo con avisos en
  `profile`, `plan` y `create_cv`.
- **Coste**: frontera de `LongTrainingWarning` exacta (49 y 50 ajustes sin
  aviso, 51 y 52 con aviso, en `create_cv` y en `backtest`); 2000 ventanas sin
  aviso y 2050 con aviso; `n_folds`, `n_fits` y `estimator_fits` coinciden con
  lo que se ejecuta para Recursive, Direct y Stats con todas las variantes de
  `refit`, `skip_folds` y `allow_incomplete_fold`; `compare_estimator_fits`
  coincide con el coste real del `compare` por defecto, incluida la exclusión
  por encima de 500 ajustes.
- **Seguridad de rutas**: prefijo hermano, `..` que sale, symlinks a fichero o
  directorio externos, rutas relativas, `~`, rutas de Windows y UNC, URLs
  (`file`, `http`, `https`, `ftp`) sin petición de red, NUL y saltos de línea,
  extensiones no CSV y directorios; un fichero inexistente fuera del
  directorio da `path_not_allowed` sin revelar su existencia; `/etc/passwd` y
  `/proc/self/environ` se rechazan antes de leer. Mismo resultado para
  `exog_path`. Arranque con `--allow-dir` a un fichero, inexistente o
  relativo: error claro. Un cliente que muere (SIGKILL o SIGTERM) a mitad de
  un backtest no deja procesos huérfanos.
- **Segunda ronda**: ForecasterDirectMultiVariate dice qué serie predice y
  reordenar `target` la cambia de forma coherente; `compare` rechaza mezclar
  familias con un mensaje claro. cp1252 y UTF-16 dan `data_unreadable` con
  `hint` de UTF-8; CRLF, cabeceras entrecomilladas con el separador y
  cabeceras con espacios funcionan. El latido de progreso sale cada 5 s con el
  texto prometido; un `compare` cancelado no deja ficheros. Días hábiles con
  `test_size` en sábado, DST con desfases mezclados, UTC `Z`, fin de mes y
  trimestres funcionan o dan errores claros. `data_changed` no da falsos
  positivos con `touch` ni reescritura atómica idéntica y salta en `backtest`,
  `compare` y `forecast` tras añadir una fila. Un `compare` registra 2 objetos
  sea cual sea el número de candidatos, y los ids que el agente sigue usando
  sobreviven a la expulsión.
- **Errores**: unos 150 errores provocados en las 11 herramientas. Las
  violaciones de esquema (argumentos que faltan, desconocidos, tipos, enums,
  `candidates: []`) llegan como JSON documentado con `field`; los ids del tipo
  equivocado nombran el tipo y la herramienta correcta; los ids desconocidos
  dan `unknown_id` con `hint` a `list_objects`.
