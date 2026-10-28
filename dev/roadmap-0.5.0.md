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

**La 0.5.0 sale después de skforecast 0.27.0** (decidido el 2026-10-17). Lo
que se resuelve mejor en skforecast se arregla allí, con un issue, en vez de
rodearlo aquí; la sección "Dependencia de skforecast 0.27.0" lista lo que
tiene que estar resuelto y publicado antes de la release, y cada hallazgo
nuevo que sea de skforecast se añade a esa lista.

**No habrá 0.4.3** (decidido el 2026-10-18): de la 0.4.2 se pasa
directamente a la 0.5.0, aunque se alargue. V08 (el `.` de miles leído como
decimal sin aviso, introducido por la lectura de `;` de la 0.4.2) queda
arreglado en la 0.5.0 (#86) y no se publica antes. No volver a plantearlo.

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
  enteras que hoy se usan como exógena (V13), las fechas día primero del
  `exog_future` de datos largos, y las fechas con punto junto a miles con
  punto (el Excel alemán, `15.01.2020;1.234,56`): con `thousands='.'` pandas
  las lee como el entero 15012020, así que 1a las rechaza con
  `data_unreadable`; leerlas pide sacar la columna de fechas de `thousands`
  en el `read_csv` del script (`dtype={'date': str}` o similar). *[script]*
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
- **1h. El script lee el fichero de exógenas futuras que corrió, con su
  dialecto (V03, adelantado de la fase 5).** Visto en
  [#97](https://github.com/skforecast/skforecast-ai/pull/97): el script lee
  `exog_future.csv` del directorio de trabajo, con el formato de fecha
  (#96) y la codificación (#97) del fichero que se leyó, pero con el
  separador, el decimal y los miles por defecto, como si fuera un
  `to_csv()`. Unas exógenas del Excel en español (cp1252 y `;`) las lee
  `forecast()` y el script falla: contra el principio 2. Que el script lea la
  ruta que corrió (como los datos) con todo su dialecto, guardado como el de
  los datos pero aparte. *[script]*

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
| 3 bis | 1h (dialecto de las exógenas futuras) | Salió de #97 (1f); toca la lectura de las exógenas, no la inferencia de frecuencia, así que va en paralelo con 1e |

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
  cambia el texto del backtest. En formato ancho el perfil no guarda dónde
  empieza cada serie (sus NaN iniciales): hace falta para nombrar las series
  cortas, y el aviso de residuos de 2c-i (D13) lo usará cuando exista.
- **2c. Intervalos de los backtests multiserie.** Defecto conocido: con un
  intervalo del 80 %, cubren el 56 % con ForecasterRecursiveMultiSeries y el
  14 % con ForecasterDirectMultiVariate en `items_sales`, porque los scripts
  usan residuos dentro de muestra (`store_in_sample_residuals` en
  `rendering/multi_series.py`). En dos PR (decisión D11):
  - **2c-i. Aviso de pocos residuos (V04).** El que ya tiene una sola serie:
    `_RESIDUAL_INTERVAL_FORECASTERS` (`recommendation/backtesting.py`)
    excluye a los multiserie. Contar por serie (el `n_train` de
    `_split_folds` usa `span_index_length`, que sobrestima las series que
    empiezan tarde) e incluir ForecasterDirectMultiVariate.
  - **2c-ii. Cobertura y anchura medidas en el backtest.** Todo backtest con
    intervalo (una serie y multiserie) muestra, por serie, la cobertura real
    y la anchura media del intervalo junto a la nominal, y un aviso salta
    cuando la cobertura queda claramente por debajo. Las da el propio
    backtesting de skforecast 0.27
    ([#1409](https://github.com/skforecast/skforecast/issues/1409)): el
    script no calcula nada propio, las lee de la salida. #1409 está en la
    rama `0.27.x` desde el 2026-10-20
    ([#1420](https://github.com/skforecast/skforecast/pull/1420)): con un
    intervalo de dos límites, las métricas del backtest llevan `coverage` e
    `interval_width` después de las pedidas, por serie y en las filas
    agregadas, en los cuatro backtestings (`backtesting_stats` por
    estimador). Los residuos fuera de muestra van a la 0.6.0. *[script]*
    *[LLM]*
- **2d. `target` como lista (V22, V23).** Con `series_id_column`, la columna
  de ids se descarta en silencio; con una columna repetida, se acepta como
  dos series. Rechazar con `field` el `series_id_column` que pasó el usuario
  (no el que rellena `_normalize_multiindex`).

### Tandas de la fase 2

| Tanda | PR | Por qué así |
|:--|:--|:--|
| A | 2a (estimador de DMV), 2b (serie corta), 2c-i (aviso de residuos), 2d (`target` como lista) | Módulos distintos: la recomendación y la explicación; `_last_window.py` y el resumen del backtest; el aviso de `create_cv`; la validación del perfil |
| B | 2c-ii (cobertura y anchura) | Cambia los scripts de backtest con intervalo, también los de DMV que cambia 2a: va sobre la tanda A mergeada, y sobre skforecast#1409 en la rama `0.27.x` |

Lo que cada sesión necesita saber es lo mismo que en la fase 1 (ver
"Tandas" de la fase 1).

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
  contrato. Desde [#103](https://github.com/skforecast/skforecast-ai/pull/103)
  (D15) se sabe además que una serie cuyas últimas ventanas tienen todas
  algún faltante (con un estimador que no los acepta, o con diferenciación)
  desaparece en silencio de todos los folds del backtest multiserie: la
  comprobación previa de 2b ya replica la regla de skforecast, así que se
  puede ampliar a este caso con el mensaje de los faltantes.
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
- **3f. Avisos menores.** En un PR propio, D24: el panel de métricas por
  defecto lleva RMSE en vez de MSE. El aviso de coste ofrece `refit` para ForecasterStats
  y modelos fundacionales, que no baja su coste (V18). `create_cv` acepta
  `skip_folds` para ForecasterStats y el backtest falla opaco (V17).
  `fixed_train_size` sin `refit`: el esquema dice que es un error y el
  servidor solo avisa (V21). `FutureExogNotice` nombra también las
  categóricas que un modelo fundacional descartaría (hoy no se alcanza).
  Un plan con `use_exog=False` arrastra los avisos de las exógenas de su
  perfil (el 20 % de faltantes y, desde
  [#95](https://github.com/skforecast/skforecast-ai/pull/95), los números
  escritos como texto y los faltantes de cada columna), y con ellos al
  contexto del LLM: un plan que no usa exógenas no debería llevarlos.
  *[LLM]* De la revisión de
  [#104](https://github.com/skforecast/skforecast-ai/pull/104) (D16):
  `compare()` con los candidatos por defecto no avisa de un MAPE sin
  sentido (con candidatos explícitos sale el aviso de cada plan): un aviso
  por comparación. MSLE con un objetivo con valores negativos falla al
  ejecutar (sklearn lo rechaza): error en el plan, no en el script. La
  explicación del plan debe decir por qué quitó MAPE del panel. *[LLM]*
  De la revisión de
  [#105](https://github.com/skforecast/skforecast-ai/pull/105) (D17):
  - `backtest()` comprueba antes de ejecutar el objetivo de cada fold, no
    las exógenas: con Ridge, un faltante de una exógena en una fila que
    predice un fold de test sigue fallando como `execution_failed`.
    Comprobar también las exógenas de cada fold, nombrando columna y
    fechas, como hace `forecast()` con las futuras.
  - La comprobación de que un fold tiene filas de entrenamiento completas
    solo corre en `backtest()`: extenderla a `forecast()` y a
    `forecast(test_size=...)`, donde el mismo "All samples have been
    removed" es menos frecuente.
  - Una serie cuya última ventana tiene un faltante solo en algunos folds
    se queda fuera de esos folds sin decirlo, y sus métricas y la media usan
    menos folds: un aviso en el resumen del backtest. skforecast 0.27 ya lo
    avisa ([#1415](https://github.com/skforecast/skforecast/pull/1415)): un
    `MissingValuesWarning` que nombra los niveles que no se pronostican en
    folds donde tienen valores, pero solo con `suppress_warnings=False`, y
    los scripts corren con `True`. En vez de calcularlo aquí, el runner del
    backtest puede capturar ese aviso concreto (sin dejar pasar los demás
    avisos de skforecast) y convertirlo en el aviso del resumen.
  - Guardar en el perfil los días de cierre que ya calcula para su nota
    (por ejemplo `DataProfile.closed_weekdays`), para que `create_cv` dé el
    consejo exacto en vez de uno condicional. Cambia el esquema del perfil.
  - ForecasterDirectMultiVariate: skforecast nunca descarta una serie de su
    última ventana, así que un faltante da predicciones NaN o un error
    dentro del script. Sin cubrir.
  De la revisión de
  [#107](https://github.com/skforecast/skforecast-ai/pull/107) (D18):
  - `transformer_exog` y `categorical_features` también se pierden en
    silencio al cambiar de forecaster: nombrarlos en el aviso cuando tenían
    efecto en el plan anterior.
  - Los lags que refinó el LLM cuentan como elegidos por el usuario (el
    refinado lo pidió él), así que también se nombran.
  - Un solo aviso, no dos, cuando en la misma llamada hay ediciones a mano
    descartadas y decisiones que el forecaster nuevo no admite.
  - Los lags, las ventanas y el estimador que eligieron las reglas no se
    nombran: la familia nueva los vuelve a decidir y la explicación del
    plan ya lo cuenta.

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

- **5-0. La estrategia sin `differentiation` (skforecast 0.27,
  [#1423](https://github.com/skforecast/skforecast/pull/1423)). Urgente:**
  la suite de `0.5.x` falla contra la cabeza de `0.27.x` (16 tests por el
  `FutureWarning`), y va antes que cualquier otro PR. skforecast toma el
  orden de diferenciación del `window_size` del forecaster y depreca
  `differentiation` en las estrategias. Aquí sobra todo lo que exigía
  repetirlo: el `TimeSeriesFold(differentiation=...)` de la librería y de
  los scripts (`rendering/backtesting.py`), la comprobación de que la
  estrategia y el plan coinciden en `backtest()` y la copia de la
  estrategia por candidato en `compare()` (`assistant.py`) y el campo
  `differentiation` de la estrategia, que copiaba el del plan (`create_cv`
  no tenía un argumento para él: lo que cambia en la API es la clave de
  `cv_config` y del JSON de `CVResult.cv`). Una misma estrategia sirve para
  candidatos con distinta diferenciación (era V07, descartado, y lo que
  pedía FE-05 en skforecast). Hecho en
  [#115](https://github.com/skforecast/skforecast-ai/pull/115) (D26).
  *[script]* *[API]* *[SKILL]*

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
  candidato responde "named None". Unos datos sin fechas (`index_type`
  range) con exógenas futuras desde fichero fallan en la librería:
  `load_exog` toma la primera columna como índice (pregunta 6 de
  [#99](https://github.com/skforecast/skforecast-ai/pull/99), anterior a
  ella).
- **`forecast()` y `forecast_code()` con una ruta en `exog`**, leída con
  `load_exog` (el perfil da la columna de fechas, los ids y el orden de las
  fechas). Hoy solo aceptan un DataFrame o una Series, y el fichero llega al
  script por `exog.attrs['exog_file']`, que pandas arrastra a los frames
  derivados; una ruta sería el canal explícito (preguntas 1 y 5 de #99).
  *[API]*
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
  estrategia, que no carga ningún modelo. (V03, el fichero de exógenas que
  lee el script, pasó a la fase 1 como 1h.)
- **`profile` sin `target` cuando el usuario ya nombró la columna.** Cuesta
  una llamada (9 de 81 con el modelo grande). Con el pequeño, una sesión se
  saltó así el error de la columna inexistente y la sustituyó sin decirlo.
- **`compare` con candidatos** deja fuera el plan refinado de la estrategia
  sin decirlo, y "Strategy plan" no es un nombre reservado (V24). *[SKILL]*
- **La comprobación de series que ningún fold pronostica (D15) en
  `compare()`**: hoy solo la hace `backtest()`, y un candidato
  ForecasterRecursiveMultiSeries de `compare` puede seguir descartando una
  serie en silencio. Un candidato así queda como fallido, con el motivo en
  el ranking y en `get_failure`, como cualquier candidato que falla, sin
  tumbar todo el `compare` (pregunta 1 de
  [#103](https://github.com/skforecast/skforecast-ai/pull/103)).
- **El backtest de ForecasterFoundation** solo rechaza las series sin
  valores: falta mirar si descarta también series sin contexto suficiente
  antes de un fold (pregunta 2 de #103).
- **Series que faltan en algunos folds** (de la revisión de
  [#119](https://github.com/skforecast/skforecast-ai/pull/119), D29): una
  serie que se queda fuera de algunos folds (no de todos) hace que sus
  métricas y la media usen menos folds sin decirlo. Las predicciones de un
  backtest multiserie ya llevan `level` y `fold`: el runner compara en qué
  folds se pronosticó cada serie con aquellos en que tenía valores y lo
  dice en el resumen (y en un notice del MCP), sin `suppress_warnings=False`
  ni pedir nada a skforecast. Es leer el resultado, como la cobertura de
  D22. *[LLM]* si cambia el resumen.
- **Avisos pequeños de faltantes** (de la revisión de #119, D29):
  `backtest()` avisa, sin fallar, de una exógena que falta en un fold con
  un estimador que acepta faltantes, como ya hace `forecast()` con las
  exógenas futuras; y se comprueban por fold las categorías de una
  exógena que la ventana de entrenamiento del fold no tiene (caso raro).
- **Cerrar el `WindowFeature` que devuelve el LLM** (`schemas/plans.py`, de
  la revisión de [#121](https://github.com/skforecast/skforecast-ai/pull/121),
  D30): no tiene `extra='forbid'`, así que una clave que el modelo invente
  (`min_periods`) se descarta sin aviso. Cerrado, pydantic-ai le devuelve el
  error y reintenta, como con `lags`. Cambia el esquema de salida que ve el
  modelo: entra en el chequeo de pago de la fase 7. *[LLM]*
- **pydantic-ai 2.62** (de la revisión de #121): la suite pasa entera salvo
  `test_plan_refinement_agent_reasks_model_when_lags_invalid`, que fija la
  forma del reintento. pydantic-ai 2.62 devuelve el error como
  `ToolReturnPart`, con `loc` como lista, en vez de `RetryPromptPart`; la
  conducta (el modelo recibe el error y reintenta) es la misma. El test
  acepta las dos formas, porque `pydantic-ai>=2,<3` instala 2.62 a un
  usuario nuevo: hecho en
  [#122](https://github.com/skforecast/skforecast-ai/pull/122). 2.62 imprime además un banner de Logfire una vez por
  proceso, por stderr (no rompe el stdio del MCP; no sale bajo pytest ni
  en CI): opcional apagarlo con `pydantic_ai.BANNER_ENABLED = False` en el
  servidor MCP y la CLI.

## Fase 6. Descripciones de las herramientas y SKILL.md

Al final, para que describan el comportamiento definitivo y el golden de
esquemas se regenere una vez: `dev/mcp-tool-descriptions-plan.md`, más las
frases del SKILL.md o de los esquemas que la auditoría vio desfasadas (V06,
V19, V21, V24, V29) y lo que hayan cambiado las fases 3 a 5. *[SKILL]*

## Fase 7. Cierre de la release

1. `/llm-context-change` con todos los PR marcados *[LLM]*: goldens
   revisados y un solo check de pago contra un modelo real
   (`tools/ai/check_ask_context.py`, lo lanzas tú). En el mismo ciclo:
   `ask(context=profile, plan=plan)` explica el script sin la codificación ni
   el formato de fecha de las exógenas (pregunta 4 de #97). El `--dry-run`
   y el check se lanzan en local: `check_ask_context.py` descarga los
   datasets de skforecast con `fetch_dataset`, y la red de una sesión en la
   nube lo bloquea (en #104 se quedó colgado más de una hora). Después,
   volver a grabar las salidas de `ask()` de
   `agentic-forecasting.ipynb` y `agentic-forecasting-step-by-step.ipynb`,
   que llaman porcentaje a MAPE (#104), y las de esos dos y de
   `first-forecast.ipynb`, que muestran MSE en el panel por defecto (3f-1).
2. Check con agentes de `tools/mcp/` (cambian el SKILL, el coste y las
   descripciones: está en "When to run it"), al menos con sonnet y con haiku
   en los escenarios críticos. Debe incluir un escenario con un CSV de Excel
   en español (miles con `.`, fechas día primero, cp1252) y otro multiserie
   con ids numéricos, y uno que vea si un agente lee el aviso de intervalos
   con cotas iguales y lo cuenta (pendiente desde `96f4cdc`). El escenario
   `expensive_run` gana un check que marque un `confirm_cost` pasado antes
   de que el usuario conteste (4b, #113).
3. Los datos de las animaciones de la portada y de la documentación
   (`tools/docs/home_page/generate_home_data.py`, que escribe
   `docs/overrides/partials/home-data.json` y los `*-data.js` de
   `docs/animations/`) no se pueden regenerar: el script para cuando una
   cifra citada en las respuestas de `ask()` escritas a mano ya no cuadra,
   y en `0.5.x` el MAE del backtest pasó de 49.5 a 45.8 (visto en #117,
   también sin ella). La causa probable son los cambios de skforecast 0.27
   (el modelo congelado de ForecasterStats, #1425; los folds saltados,
   #1427) y los de esta release. Hay que volver a escribir a mano esas
   respuestas con las cifras nuevas (no se graban de un modelo) y
   regenerar los datos, también los de `generate_agent_session_data.py` y
   `generate_mcp_overview_data.py` si cambian, después de que el
   comportamiento quede cerrado.
4. Comprobaciones a mano (abajo).
5. skforecast 0.27.0 publicado con todo lo de "Dependencia de skforecast
   0.27.0" resuelto, `/sync-skforecast-assets` (lo lanzas tú) y la suite
   contra la 0.27.0 de PyPI. `pyproject.toml` pide ya `skforecast>=0.27.0`
   (2026-10-18): hasta que esté en PyPI, las sesiones en la nube instalan
   skforecast de su rama `0.27.x` y el entorno local también.
6. `/release-note consolidate`, bump de versión (`/release-bump`) y
   publicación.
7. Tras publicar: Deploy y Make Release en Glama y apuntar el TDQS nuevo
   (paso 8 del plan de descripciones).

## Decisiones tomadas

- **D1. V08: leer el `.` de miles cuando es inequívoco** (2026-10-15): mezcla
  de valores con y sin separador, o con `,` decimal como `1.705,11`. Se
  guarda `thousands` en el perfil y se emite en el script solo cuando no es
  el de hoy. Cuando es ambiguo (todos los valores con tres cifras tras el
  punto), `data_unreadable` con hint. (El rechazo a secas era el plan B de
  una 0.4.3, que no habrá.)
  Concretado en [#86](https://github.com/skforecast/skforecast-ai/pull/86)
  (2026-10-15):
  - Solo `thousands='.'`, con `,` decimal: `thousands=','` (`"10,025.1"` en un
    fichero con `,`) queda fuera; su error nombra el formato, y añadir `,`
    más tarde no rompe nada.
  - La mezcla "con y sin separador" se mira por columna: enteros de hasta tres
    cifras junto a valores como `1.020`; un entero de cuatro cifras sin
    separador la anula. Pistas que se contradicen (esa columna junto a un
    `0.5` en otra) dan `data_unreadable`, nunca se elige una.
  - Con `.` de miles, cualquier otro valor de cifras y puntos (`15.01.2020`,
    `0.5`) da `data_unreadable`: pandas le quitaría todos los puntos. Las
    fechas con punto van a 1d.
  - Más allá de la muestra de 256 KB, si el fichero (con `;` o tabulador y `.`
    decimal detectado) no cabe en ella, se releen como texto las columnas
    leídas como `float` con las mismas reglas: unos datos largos ordenados
    por serie pueden traer los miles solo en series posteriores. Las URL no
    se releen. Solo se releen las columnas con valores de 1 a 999 y tres
    decimales como mucho, y nada si los números ya leídos lo deciden: en un
    fichero de 73 MB con decimales de precisión, 1,3 s frente a 1,0 s de una
    lectura simple; en el peor caso (precios con dos decimales, 35 MB),
    2,7 s frente a 0,6 s.
  - Con `.` de miles (detectado o dado), los valores con punto que no
    separan miles (`0.5`) solo se buscan en la muestra: un fichero
    incoherente, concatenado de dos configuraciones regionales, con un `0.5`
    tras los 256 KB, lo lee pandas como 5. Cubrirlo exigiría releer todas las
    columnas numéricas de cualquier fichero grande con miles.
  - El fichero del que se construyó un perfil (mismo `data_path`) se lee con
    el dialecto del perfil, también cuando se detectaría otro: así un
    `decimal='.'` dado contra la regla de mezcla se mantiene en `forecast()`.
    Otro fichero se detecta, como en la 0.4.2.
  - V15: el error de un objetivo con separador de miles o `%` es del fichero
    (`DataContentError` en `data`), para que el servidor MCP añada
    `DATA_PROBLEM_HINT`.
  - Nota de release sin destacado (se decide al consolidar la fase 1), con
    una línea en "Before upgrading": los ficheros cuyos números con punto
    tienen todos tres decimales ahora dan error.
- **D2. V28: solo detección** (2026-10-15): las filas más largas que la
  cabecera dan `data_unreadable` con hint, sin tocar los scripts.
  `index_col=False` leería bien el separador final, pero tendría que ir
  también en el script y rehacer todos los goldens de renderizado.
  Concretado en [#85](https://github.com/skforecast/skforecast-ai/pull/85)
  (2026-10-15):
  - Cabecera con un campo menos (`to_csv(index_label=False)`): en los datos
    da `data_unreadable`, porque su perfil nunca funcionó (sin fechas ni
    frecuencia); en las exógenas se sigue aceptando, como documentaban 0.3.x
    y 0.4.x, solo si todas las filas tienen exactamente un campo más y la
    última columna no queda vacía.
  - Una columna sin nombre y sin valores (`Unnamed: N`, separador al final
    de todas las líneas) da `data_unreadable` nombrándola, en cualquier
    posición, no solo al final: ignorarla en silencio iría contra el
    principio 3.
  - Un único hint neutro, para personas y agentes, igual en datos y
    exógenas: escribir una copia sin los campos sobrantes y pedir permiso al
    dueño del fichero si no es propio. El servidor MCP no lo sustituye por
    `EXOG_FILE_HINT`: quitar separadores no cambia ningún valor.
  - Nota de release solo en **Fixed**, sin destacado ni "Before upgrading";
    el destacado se decide al consolidar las notas de la fase 1.
- **D5. G02: los ids de serie son texto** (2026-10-16), en la librería y en
  el script, sin esperar a
  [#1357](https://github.com/skforecast/skforecast/issues/1357). Concretado
  en [#90](https://github.com/skforecast/skforecast-ai/pull/90):
  - El `read_csv` de la librería y el del preámbulo leen la columna de ids
    con `dtype={<id>: str}`, después de los argumentos de dialecto, también
    `exog_future.csv` y el fichero de exógenas futuras de la librería. Se
    emite siempre que el perfil tenga `series_id_column`, también con una
    sola serie en formato largo, que no usa la columna: así el script lee el
    fichero como la librería.
  - El cuerpo común convierte los ids antes del `to_datetime`, en `data` y
    en `exog_future`, con `map(str, na_action='ignore')` y no con
    `astype(str)`: con pandas 2, `astype(str)` haría de un id vacío la serie
    `'nan'`, y las filas sin id se quedan fuera como antes.
  - La librería convierte también los ids de un DataFrame (datos y
    exógenas futuras) antes de perfilar, validar y ejecutar, así el perfil
    nombra `'1'` y las comprobaciones ven lo que ve el script; en `exec`, la
    línea del script es la misma conversión. Un DataFrame con ids enteros
    ordena sus series como texto (`'1'`, `'10'`, `'2'`).
  - La columna de ids no cuenta para el dialecto (ni en la muestra ni
    después de ella: un id `1.2.3` no da `data_unreadable`, uno `1.020` no
    decide los miles) ni para buscar la columna de fechas (`'2001'` se lee
    como un año).
  - Exógenas futuras con ids enteros y datos con ids de texto: antes, error
    con la pista "of another type"; ahora se emparejan como texto (`1` es la
    serie `'1'`). La pista pasa a ser la de los mismos números escritos de
    otra forma (`1` frente a `'001'`, `1.0` frente a `'1'`), también con un
    modelo fundacional, que sin ella tomaría todas las series sin valores
    futuros sin avisar.
  - DataFrame ancho con columnas de nombre entero: `InvalidInputError`
    (`field` `target`) con un hint para renombrarlas, en vez de la
    `ValidationError` de Pydantic. No se convierten a texto (pregunta abierta
    en la PR).
  - Nota de release en **Changed** (scripts) y **Fixed**, con una línea en
    "Before upgrading" por el cambio de los scripts; sin destacado, que se
    decide al consolidar la fase 1.
- **D6. 1g: avisos de exógenas sucias en el perfil** (2026-10-16). V12: una
  columna `object` avisa cuando al menos el 90 % de sus valores (sin contar
  faltantes) son números una vez quitados los espacios y un `%` final, o
  celdas solo de `-` o en blanco, y hay al menos un número. No cuentan como
  números los que tienen cero inicial (`007`, un código) ni los separadores
  de miles; se respeta la coma decimal del fichero; las columnas de dtype
  `category` no se miran (se eligieron a propósito). El aviso **no cita
  valores** de la columna, describe el patrón (`%` final, celdas de `-`,
  celdas en blanco, números con espacios): los avisos del perfil llegan al
  contexto del LLM (principio 4). V11: un aviso desde el primer NaN en una
  exógena, con la columna y el recuento (hasta 5 columnas); dice que un
  estimador que no acepta faltantes falla, sin recomendar ninguno (eso es
  3a).
- **D7. 1d: el orden de día y mes de las fechas** (2026-10-16). Concretado
  en [#96](https://github.com/skforecast/skforecast-ai/pull/96):
  - El perfil guarda el formato, `DataProfile.date_format` (`'%d/%m/%Y'`),
    no un `dayfirst`: así cubre también `'%Y%m%d'` y `'%d.%m.%Y'`. Sin
    prefijo `csv_`, porque describe también las fechas de texto de un
    DataFrame. El script lo emite como `format=` en `_emit_index_setup`;
    con `None`, la lectura de antes (pandas adivina por la primera fecha).
  - Se registra siempre que el día y el mes van en números, en los dos
    órdenes: día primero también cuando la primera fecha ya lo dice
    (`13/01/2020`, que pandas leía bien), y mes primero también (revisión
    de la PR), porque el formato de los datos resuelve la ambigüedad de las
    exógenas futuras de un horizonte corto (`01/02` a `07/02`), y con
    `None` un fichero de EE. UU. no la resolvía. Mismas predicciones.
  - Ambiguo es que todas las fechas se lean con los dos formatos. Con el
    año delante (ISO) o con el nombre del mes nunca lo es, y `dayfirst` se
    ignora. Un `dayfirst` que las fechas contradicen da `invalid_argument`
    con `field` `dayfirst`.
  - Fechas ambiguas sin `dayfirst` (revisión de la PR, en vez de dar error
    siempre): se leen en los dos órdenes y, si solo una lectura tiene
    frecuencia regular (`infer_frequency` sobre las fechas únicas
    ordenadas, la inferencia del perfil), se usa, se guarda el formato y
    una nota en `DataProfile.warnings` (`DataProfileWarning` en el MCP)
    dice que el orden se dedujo de la regularidad y cómo dar el otro con
    `dayfirst`. Solo cuando las dos lecturas son regulares, o ninguna,
    `data_unreadable` con el hint de siempre y el motivo en el mensaje.
    Comprobado: un mensual de EE. UU. de 60 filas da `MS` mes primero y
    nada día primero, como en 0.5.x; el español, al revés; uno de 3 filas
    da `D` y `MS` y sigue siendo ambiguo. La línea de "Before upgrading"
    queda solo para lo que sigue fallando: un año o menos de datos
    mensuales y las fechas sin frecuencia regular.
  - El argumento es `dayfirst` (el nombre de pandas, como `sep`, `decimal`
    y `thousands`), `--dayfirst` o `--monthfirst` en la CLI. Se aplica a
    los ficheros y a la `date_column` de texto de un DataFrame (revisión de
    la PR); con fechas que ya son datetime, un `IgnoredArgumentWarning`
    dice que no aplica. El formato de un DataFrame sale de sus propias
    fechas.
  - Al releer con un perfil (mismo fichero u otro), el orden se detecta, y
    el formato del perfil decide solo cuando las fechas se leen en los dos
    órdenes, como el dialecto.
  - Exógenas futuras (revisión de la PR): su formato se detecta por
    separado con las mismas reglas (`load_exog`, y el texto de la columna
    de fechas de un DataFrame en `exog_date_format`); el de los datos solo
    resuelve una ambigüedad del fichero, y si no la resuelve, regularidad
    con aviso (`UserWarning`) o `data_unreadable` con un hint que pide ISO
    8601. `load_exog` lo deja en `exog.attrs['date_format']` y el script lo
    emite en `exog_future.csv`, así que uno guardado en ISO con `to_csv()`
    funciona (sin `format=`).
  - `yyyymmdd`: columna de enteros de 8 cifras, todos fechas válidas, con
    o sin `date_column`, en el orden de columnas de las fechas de texto.
  - Miles: la columna de fechas no cuenta para el dialecto (la dada, o la
    primera de la muestra con todas sus celdas fechas escritas con
    números) y, con `thousands`, se lee como texto (`dtype`) en la
    librería y en el script, que lo emite siempre que haya `date_column`,
    como los ids en D5. Fechas con punto en otra columna siguen dando
    `data_unreadable`.
  - Años de dos cifras (`01/02/18`), para los que pandas no adivina
    formato: mismas reglas, y el formato se registra en los dos órdenes.
    Fechas que se leen igual en los dos (`01/01/2000`, anuales): sin duda.
    Una columna cuyo orden no se sabe es la de fechas: da el error aunque
    otra columna posterior tenga fechas.
  - Un DataFrame de fechas de texto con un perfil guardado (refresco) se
    lee en el orden del perfil cuando sus fechas se leen en los dos.
  - V14: el error de `plan` habla solo del espaciado, y el contexto del LLM
    lista `no regular frequency (irregular spacing or too few timestamps)`
    en vez de `none detected`. La frecuencia más cercana y los huecos
    quedan para 1e.
  - Nota de release en **Added**, **Changed** y **Fixed**, con dos líneas
    en "Before upgrading" (los scripts y el error de las fechas ambiguas
    cuya regularidad no dice el orden); sin destacado. Preguntas 2
    (registrar el formato aunque la primera fecha diga día primero) y 5
    (`dtype={'date': str}` con miles): sí, como estaban.
- **D8. 1f: ficheros en cp1252** (2026-10-16). Concretado en
  [#97](https://github.com/skforecast/skforecast-ai/pull/97):
  - El perfil guarda `DataProfile.csv_encoding`, `'utf-8'` (con o sin BOM)
    o `'cp1252'`, con `'utf-8'` por defecto como `csv_sep` y `csv_decimal`
    llevan el valor por defecto de pandas. El script emite
    `encoding='cp1252'` en el `read_csv` solo en ese caso, tras el dialecto
    y antes de `dtype`; ningún golden UTF-8 cambia.
  - Se detecta siempre, de los primeros 256 KB (la misma muestra del
    dialecto), también cuando `sep` y `decimal` se dan y al releer el
    fichero de un perfil: no hay argumento explícito, así que no hay nada
    dado que conservar, y un fichero guardado de nuevo en UTF-8 (lo que pide
    el aviso) se lee bien sin perfilar otra vez. Si los bytes que no son
    UTF-8 llegan después de la muestra, pandas falla al leer en UTF-8 y se
    relee en cp1252.
  - Rechazos (`data_unreadable`, hint `ENCODING_HINT`: guardar una copia en
    UTF-8, con permiso del dueño): BOM de UTF-16 o UTF-32, un byte nulo en
    la muestra (UTF-16 sin BOM, binarios) y, en un fichero que no es UTF-8,
    uno de los cinco bytes que cp1252 no define (`0x81`, `0x8d`, `0x8f`,
    `0x90`, `0x9d`), en la muestra o después (lo dice pandas al leer en
    cp1252). En UTF-8 esos bytes son legítimos (`Á` es `C3 81`).
  - El aviso va el primero de `DataProfile.warnings` (antes de las notas de
    fechas de D7), no cita valores (principio 4) y dice que el script lee
    igual; `_with_data_path` lo añade al perfil de los flujos que perfilan
    el DataFrame leído, como las notas de fechas.
  - Exógenas: `load_exog` detecta su propia codificación, avisa con
    `UserWarning` (`Exog CSV '...': ...`) y la deja en
    `exog.attrs['encoding']`; el script la emite en `exog_future.csv`
    (`exog_encoding` junto a `exog_date_format` en los renderizadores).
  - `.gz`, `.bz2` y `.xz` se descomprimen para la muestra. Los que pandas
    descomprime y aquí no se abren (`.zip`, `.zst`, `.tar` y sus variantes)
    no se muestrean y se leen como antes, solo UTF-8: sus bytes llevarían
    nulos y se rechazarían. En una URL se reconocen por sus primeros bytes
    (bzip2, xz, zip, zstd, tar), sea cual sea su nombre.
  - URL: la primera lectura sigue siendo la de siempre; si pandas falla al
    decodificar UTF-8, se descarga la muestra (rechaza UTF-16 con BOM) y se
    lee en cp1252. Un UTF-16 sin BOM por URL no se detecta si la primera
    lectura no falla (pregunta en la PR).
  - Nota de release solo en **Fixed**, sin destacado ni "Before upgrading":
    los scripts solo cambian para ficheros que antes fallaban.
- **D9. 1e: frecuencia con huecos regulares o frecuentes** (2026-10-16).
  Concretado en [#98](https://github.com/skforecast/skforecast-ai/pull/98):
  - Cuando ningún tramo de 10 fechas seguidas da frecuencia, se infiere en
    ventanas de 3 (las menos de las que pandas infiere una), en bloques de
    20 ventanas seguidas si el índice es largo: ventanas sueltas a
    intervalos regulares pueden caer todas en la misma fase de un patrón
    semanal. Una candidata vale si su rejilla contiene todas las fechas,
    está observada al menos en `_MIN_FREQUENCY_COVERAGE` (50 %) y el paso
    más común entre fechas seguidas es un periodo: así un dato suelto a
    mediodía entre días no da `'12h'` (los pasos se buscan como fechas,
    así vale cualquier unidad del índice). De las que valen, la más gruesa
    (`'B'` antes que `'D'`), y `'B'` es candidata siempre que lo sea `'D'`
    (pandas no ve `'B'` en tres días que no cruzan un fin de semana: de
    lunes a jueves).
  - Si algún tramo da frecuencia y su rejilla no encaja (un sábado entre
    laborables), sigue sin frecuencia: no se busca otra más fina con
    huecos. Por eso lo que hoy se infiere no cambia: comprobado en toda la
    suite (cada llamada comparada con 0.5.x), en 4000 índices al azar y en
    los goldens de contexto del LLM, que no cambian.
  - Sin domingos es `'D'` con los domingos como fechas que faltan, con el
    tratamiento de los huecos al azar del 10 al 20 %: `forecast` predice
    también los domingos, y `backtest` y `forecast` con `test_size` dan
    `invalid_argument` porque los NaN caen en los folds de test. Nada se
    rellena solo (principio 3).
  - Días de cierre (revisión de la PR): cuando todas las fechas que faltan
    caen en días de la semana sin ninguna fecha, que se repiten al menos
    dos veces en el rango (`regular_gap_weekdays`; en formato largo, cada
    serie en su rango), el aviso de fechas que faltan los nombra, dice que
    `forecast` los predice y que, si el negocio cierra esos días, se pueden
    rellenar con 0 en los datos tras preguntar al usuario. Los errores de
    `backtest` y de `test_size` (una serie, `_check_evaluated_target`;
    varias, `_check_multiseries_evaluation`) dan el mismo consejo cuando
    todas las fechas sin valor evaluadas caen en días en que su serie nunca
    tiene valor (`closed_weekdays`). Con huecos al azar, o con domingos y
    festivos (no todas las fechas caen en los días cerrados), los textos de
    antes. La solución de fondo, `CustomBusinessDay` con `weekmask`, va a la
    0.6.0 (al final de este fichero).
  - Formato largo: una tienda de lunes a sábado junto a una oficina de
    laborables da `'D'` (antes, fechas fuera de la rejilla `'B'`), como ya
    daban series diarias junto a laborables; de acuerdo en la revisión.
    `_coarser_frequency`, que
    infiere una vez por serie dispersa, usa solo los tramos sin huecos
    (`regular_gaps=False`): con las ventanas de 3, mil series dispersas
    pasaban de 1 s a 9 s.
  - D7: en 1166 lecturas de fechas ambiguas (mensuales, trimestrales y
    diarias cortas, con y sin huecos), ninguna lectura equivocada pasa a
    ser la única regular. Los mensuales con huecos de más de un año se
    leen ahora en su orden, y un año o menos con huecos sigue siendo
    ambiguo (las dos lecturas son regulares).
  - V14: el error de `plan` dice que las fechas que faltan se rellenan
    solo cuando las demás siguen una frecuencia regular "and fill at
    least half of its periods". La frecuencia más cercana y los huecos
    en ese error (que D7 dejó para 1e) no se añaden, de acuerdo en la
    revisión: necesitarían un campo nuevo del perfil.
  - Nota de release en **Fixed**, sin destacado ni "Before upgrading", que
    nombra también los textos de los días de cierre.
- **D10. 1h: el script lee el fichero de exógenas futuras que corrió**
  (2026-10-16). Concretado en
  [#99](https://github.com/skforecast/skforecast-ai/pull/99):
  - `load_exog` deja en `exog.attrs['exog_file']` un `FutureExogFile`
    (`schemas/profiles.py`, exportado en `skforecast_ai.schemas`): la ruta
    tal como se leyó (la resuelta dentro de `--allow-dir` en el MCP), `sep`,
    `decimal`, `thousands`, `encoding` y `date_format`, detectados con las
    reglas de los datos. Sustituye a `attrs['date_format']` y
    `attrs['encoding']` sueltos. `future_exog_file` lo da (o
    `exog_future.csv` con los valores por defecto y el formato de sus
    fechas para un DataFrame en memoria) y llega igual a los
    renderizadores, a `validate_future_exog`, a `run_forecast` y a
    `forecast_code()`. Solo cuenta una instancia de `FutureExogFile`: otro
    valor bajo esa clave se ignora.
  - El `read_csv` del fichero emite cada argumento como el de los datos:
    `sep` y `decimal` juntos si no son `','` y `'.'`, `thousands` (con la
    columna de fechas como texto), `encoding` y `dtype`. Con un UTF-8
    separado por `','` solo cambia la ruta.
  - Dos líneas más en el preámbulo de carga (no corre en `exec`), solo
    cuando el fichero las necesita, para que el script lea lo que leyó
    `load_exog`: `dropna(how='all')` si tenía filas solo de separadores
    (con dos o más, el script fallaba por fechas `NaT` repetidas), y
    `rename(columns={...})` si su columna de fechas no se llama como la de
    los datos (la CLI sin `--date-column`). Ningún golden existente cambia.
  - CLI: `forecast-code --exog` nuevo, con la lógica de `forecast --exog`;
    con `--from-plan` sin DATA, el orden de las fechas ambiguas lo decide el
    `date_format` del perfil del bundle.
  - MCP: la descripción de `exog_path` (y el golden de esquemas, solo esa
    frase), `docs/api/mcp.md`, la guía del servidor y la de la CLI. Las
    instrucciones no nombraban `exog_future.csv`; la frase de privacidad del
    SKILL.md (y su copia en `plugin/`) dice ahora que el script de un
    `forecast` nombra también la ruta de `exog_path`.
  - Fuera: `forecast()` no acepta una ruta en `exog` (pregunta en la PR), y
    unos datos sin fechas con exógenas desde fichero siguen fallando en la
    librería, como antes.
  - Nota de release en **Added** (`forecast-code --exog`) y **Fixed**, con
    una línea en "Before upgrading" (el script lee otra ruta).
  - Respuestas de la revisión: se mantienen el `dropna(how='all')` de las
    filas solo de separadores, el `rename` de la columna de fechas y
    `FutureExogFile` público (principio 5); el `attrs` que se arrastra a un
    frame derivado se deja, porque lo resuelve aceptar una ruta en
    `forecast()` (fase 5).
- **D11. 2c: los intervalos multiserie se miden, no se rehacen**
  (2026-10-17). En la 0.5.0, el aviso de pocos residuos (2c-i) y la
  cobertura real y la anchura media de todo backtest con intervalo (2c-ii):
  sin coste añadido, deja de presentar como un 80 % un intervalo que cubre
  el 14 %. La cobertura y la anchura las calcula el backtesting de
  skforecast 0.27 (#1409), no el script: como la 0.5.0 espera a la 0.27.0,
  no hace falta un cálculo propio que luego habría que quitar. Los residuos
  fuera de muestra, que piden un tramo de validación y cambian el coste y
  los scripts, van a la 0.6.0.
- **D12. 2d: `target` como lista se valida en el perfil** (2026-10-17).
  Concretado en [#100](https://github.com/skforecast/skforecast-ai/pull/100):
  una
  lista junto con un `series_id_column` que pasó el usuario da
  `invalid_argument` con `field: "series_id_column"` antes de comprobar las
  columnas, también con una lista de una columna (`["y"]` no se convierte en
  `"y"`); el mensaje dice qué pasar en formato largo y en ancho, sin `hint`.
  Una lista con datos indexados por un MultiIndex `(series_id, date)`, que
  es formato largo, da `invalid_argument` con `field: "target"` y un texto
  propio (pasar el nombre de la columna de valores), con una serie o con
  varias, antes de que el MultiIndex rellene `series_id_column`: en
  `create_data_profile`, en `profile()` y en `forecast()` sin perfil, que
  aplanan el MultiIndex antes. Antes, con varias series salía el error de
  timestamps repetidos (field `data`), o el de `series_id_column`, que el
  usuario no pasó. Una columna
  repetida da `invalid_argument` con `field: "target"` y la nombra, antes de
  comprobar que las columnas existen. Mismo texto en la API, la CLI y el MCP.
- **D13. 2c-i: aviso de pocos residuos con varias series** (2026-10-17).
  Concretado en [#101](https://github.com/skforecast/skforecast-ai/pull/101).
  Solo el aviso de `create_cv` (también notice del MCP); ningún script ni
  plan cambia, y no llega al contexto del LLM:
  - ForecasterRecursiveMultiSeries cuenta por serie lo que skforecast 0.26
    guarda por serie (residuos y binner de cada una): las observaciones de
    la serie en la primera ventana de entrenamiento menos `window_size`. En
    formato largo, cada serie se sitúa en el índice que reparte los folds
    (desde la primera fecha de todas) con sus fechas de inicio y fin, en la
    zona horaria del perfil; si ese índice no se puede rehacer, cuenta la
    ventana entera, como antes. En formato ancho el perfil no sabe dónde
    empieza cada serie (sus NaN iniciales): cuenta la ventana entera.
  - El aviso nombra hasta 5 series con menos de 100 filas, de menos a más
    filas, con "and N more series"; una serie sin filas en la ventana no
    se nombra (no se entrena en ese fold).
  - Con `encoding=None` skforecast junta los residuos de todas las series
    (`_unknown_level`): se suman las filas de todas y el aviso lo dice.
  - ForecasterDirectMultiVariate solo guarda residuos de su `level`: cuenta
    como ForecasterDirect (`steps - 1` filas menos) y el aviso nombra el
    level.
  - Con una sola serie el texto no cambia.
  - Revisión: los forecasters directos cuentan filas, no `steps` por filas,
    porque los residuos de los pasos de una misma fila no son
    independientes; el texto de `encoding=None` se queda. El inicio de cada
    serie en formato ancho lo necesita también 2b (nombrar las series
    cortas): cuando el perfil lo guarde, este aviso lo usará.
- **D14. 2a: el estimador de DMV se dimensiona con las fechas comunes**
  (2026-10-17), en [#102](https://github.com/skforecast/skforecast-ai/pull/102):
  lo decide el `task_type` `"multivariate"`
  (`estimator_n_observations`: `span_index_length`; las demás tareas siguen
  con `n_total_observations`). `refine_plan` ya no arrastra hacia o desde
  DMV un estimador que eligieron las reglas: lo vuelven a elegir. Sí arrastra
  el que eligió el usuario, o aquel para el que escribió `estimator_kwargs`.
  La explicación del perfil sigue siendo la del perfil (recomienda
  ForecasterRecursiveMultiSeries); la del plan añade el estimador, el
  forecaster para el que lo eligieron las reglas y el número que lo decidió,
  solo cuando la tarea del plan no es la del perfil y el estimador no se pasó.
- **D15. 2b: una serie que ningún fold pronostica** (2026-10-17).
  Concretado en [#103](https://github.com/skforecast/skforecast-ai/pull/103):
  - `backtest()` con ForecasterRecursiveMultiSeries da `insufficient_data`
    (field `data`, `data_path` en el MCP) nombrando hasta 5 series que
    ningún fold pronostica, antes de ejecutar, en
    `validate_series_lengths(cv=...)` (sustituye a `whole_data`), después
    de `check_first_window`: una primera ventana demasiado corta para todas
    las series sigue dando su propio error. No en `create_cv`, que no ve
    los datos (V16).
  - La regla replica la de skforecast 0.26 por fold, sobre los folds del
    `TimeSeriesFold` que corre el script (`_cv_in_time_zone`): una serie se
    pronostica en un fold si la ventana de entrenamiento del fold (la del
    último reentrenamiento; la inicial sin `refit`) tiene más observaciones
    de ella que `window_size`, de su primer a su último valor ahí, y si su
    última ventana está dentro de sus fechas (formato largo) o, cuando
    skforecast descarta las últimas ventanas con faltantes (estimador que
    no los acepta, o diferenciación), dentro de su primer y su último valor.
    Comprobado contra el backtest real en 300 configuraciones al azar
    (`refit`, `fixed_train_size`, `gap`, ancho y largo, Ridge y LightGBM,
    diferenciación): las mismas series. Cubre también la serie que empieza
    después de la ventana inicial sin `refit` (la causa más común con la
    estrategia por defecto) y la que acaba antes de los folds. Los
    faltantes intermedios de las últimas ventanas no se miran (3a).
  - El mensaje dice por qué y qué hacer: quitar las series, acortar lags y
    ventanas y, si alguna serie es más larga que la ventana y no ha
    acabado, un `initial_train_size` posterior; con series no más largas
    que la ventana, que `forecast()` las rechaza también. ForecasterFoundation
    y `compare()` no cambian (preguntas en la PR).
  - El perfil de datos anchos guarda en `series_lengths` el inicio, el fin y
    la longitud de cada serie desde su primer hasta su último valor, como el
    largo con sus filas. `span_index_length` sigue siendo el del marco (se
    pasa al construir el perfil y el validador lo respeta), `start_date`
    también, y la tasa de faltantes del perfil se sigue contando sobre las
    filas del marco; `n_total_observations` sí cambia. La comprobación de
    longitudes iguales de ForecasterDirectMultiVariate no mira los datos
    anchos (antes nunca saltaba).
  - El aviso de series cortas, con varias series, nombra las de menos de 50
    observaciones, de menos a más, hasta 5; con una serie, el texto de
    antes. El aviso de pocos residuos de D13 usa ya el inicio de las series
    anchas.
  - Revisión: `compare()` y ForecasterFoundation van a la fase 5; los
    faltantes intermedios de las últimas ventanas, a 3a; `create_cv` no
    avisa, porque el error del backtest ya salta antes de ejecutar nada. El
    caso límite de `window_size` es un bug de skforecast (#1410).
- **D16. 3c-i: MAPE en objetivos que tocan o cruzan el cero, y la unidad de
  MAPE y sMAPE** (2026-10-17), en
  [#104](https://github.com/skforecast/skforecast-ai/pull/104). V10 y V20;
  RMSE y V05 esperan a D4:
  - Una serie está cerca del cero si `min <= 0.01` y `max >= -0.01`
    (`series_near_zero`, en `metric_selection.py`). Basta una serie para
    dejar MAPE fuera del panel por defecto de todas: el panel es uno para
    el plan. Una serie solo negativa, lejos del cero, conserva MAPE. Cambia
    el script de esos objetivos; ningún golden de renderizado cambia
    (sus fixtures ya empezaban en 0).
  - MAPE pedido a mano (primaria o en la lista) con un objetivo así: se
    calcula, con un `UserWarning` que va también a `plan.warnings` (en el
    MCP, un notice del `plan` con source `plan`). El texto da el rango del
    objetivo o, con varias series, las nombra con su rango, hasta 5. Solo
    MAPE: sMAPE y MSLE no avisan (preguntas en la PR).
  - MCP: con un objetivo así, MAPE recibe un `MetricUndefinedNotice` (no
    lo reportes ni lo conviertas; usa una métrica que no divida por el
    valor real) en vez del de unidad. Lo decide el perfil, no el valor de
    la métrica, igual que el panel. El `MetricUnitNotice` es uno solo con
    la unidad de cada métrica presente: MAPE fracción, sMAPE ya en
    porcentaje (0 a 200), sin multiplicar.
  - La regla 9 del prompt de `ask()` decía "MAPE is a percentage": ahora
    dice fracción, que no tiene sentido cerca del cero y que sMAPE ya es
    un porcentaje. Pendiente el check de pago de `check_ask_context.py`
    (fase 7).
- **D17. 3a: los valores faltantes, una sola regla** (2026-10-18), en
  [#105](https://github.com/skforecast/skforecast-ai/pull/105). En la
  revisión se confirmaron el estimador de las reglas que acepta faltantes
  (`RandomForestRegressor` por debajo de 250 observaciones), el aviso de
  `create_cv` también con estimadores que los aceptan, y
  `BacktestMissingValues` como registro interno fuera de `schemas/`:
  - La regla y sus textos viven en `recommendation/missing_values.py`. El
    estimador que se ofrece es el primer candidato de las reglas que acepta
    faltantes (`select_nan_tolerant_estimator`, para la tarea del plan y el
    tamaño de los datos): `RandomForestRegressor` por debajo de 250
    observaciones y `LGBMRegressor` desde 250, en vez de `'LGBMRegressor'`
    escrito a mano. Lo usan el aviso de `create_cv`, los errores con datos
    (lecturas de la ventana, exógenas futuras, `dropna_from_series=False`)
    y el `MissingValuesNotice`; `DATA_VALUES_HINT` ya no nombra ninguno:
    dice que cambiar de estimador solo evita el error cuando el mensaje
    nombra uno.
  - `create_cv` (sin datos) dice cada caso como condición: un faltante
    dentro de un fold de test falla con cualquier estimador; un fold
    predicho desde uno, con un estimador que no los acepta o con
    ForecasterEquivalentDate; con diferenciación, uno de los últimos
    `order` valores antes de un fold, con cualquier estimador (el aviso que
    faltaba con un estimador que los acepta); una exógena con faltantes,
    con un estimador que no los acepta. Avisa también con un estimador que
    acepta faltantes (el primer caso). Objetivo y exógenas van en avisos
    separados, para que cada uno quepa en los 1000 caracteres de un notice.
    Con fechas que faltan en datos diarios o más finos, el consejo de los
    días de cierre va delante, condicionado: el perfil no guarda qué días
    son.
  - El notice dice además que `backtest` comprueba los folds antes de
    ejecutar y que se corra antes de cambiar el plan o preguntar, y ofrece
    el estimador solo cuando el del plan no acepta faltantes, con lo que no
    evita (el fold de test que tiene uno).
  - Con datos, el error de un faltante en los folds de test los numera
    (`test fold 5 of 6`, `all 8 test folds`). El texto de los días de
    cierre de D9 sale de una sola función (`closed_days_remedy`) y manda
    también en el error de una ventana que lee faltantes de días cerrados
    (por ejemplo, `forecast()` de una tienda que cierra los domingos) y en
    los dos errores nuevos.
  - Nuevo en `backtest()` de una serie: `DataContentError` antes de
    ejecutar cuando, con `dropna_from_series=True`, ninguna fila de
    entrenamiento de un fold queda sin leer un faltante (el caso B de c_06,
    que fallaba con "All samples have been removed due to NaNs" y el
    consejo `dropna_from_series=False`, que el plan rechaza con Ridge).
    Replica skforecast: lags y ventanas sobre la serie diferenciada, las
    ventanas con todos sus valores al entrenar (`min_periods`), el objetivo
    de cada paso en ForecasterDirect, las ventanas de entrenamiento de los
    folds que reentrenan. Comprobado contra el backtest real en unas 475
    configuraciones al azar, sin diferencias. Las exógenas no se miran.
  - La comprobación previa de D15 mira ahora los faltantes intermedios de
    las últimas ventanas cuando skforecast las descarta (estimador que no
    los acepta, o diferenciación): una serie que solo por ellos no se
    pronostica en ningún fold da `DataContentError` (`data`, con
    `DATA_VALUES_HINT`) con sus fechas y lo que funciona (el estimador de
    las reglas, un plan sin diferenciación, rellenarlos con permiso o quitar
    la serie). Las series cortas se informan antes. Comprobado contra el
    backtest real en unas 1100 configuraciones al azar, en ancho y largo.
  - El paso `handle_missing_values` del plan dice solo lo que funciona para
    su estimador y nunca propone `dropna_from_series` (dice que solo quita
    filas de entrenamiento): el estimador de las reglas, imputar con
    permiso del usuario y, para una exógena, dejarla fuera de
    `exog_columns`. Sale también con solo fechas que faltan, y
    ForecasterStats tiene el suyo (falla con un faltante del objetivo y
    predice NaN desde una exógena que falta).
- **D18. 3b: `refine_plan()` nombra lo que deja fuera** (2026-10-18), en
  [#107](https://github.com/skforecast/skforecast-ai/pull/107). Con
  un `PlanEditsDiscardedWarning` propio, aparte del de las ediciones a mano
  (su texto va también a `plan.warnings` y al notice del MCP, con source
  `plan`):
  - Se nombra una decisión de `OVERRIDE_NAMES` (no `forecaster` ni
    `metric`) que el plan tenía con efecto y que el plan refinado no tiene,
    cuando la eligió el usuario (`plan.overridden_fields`) o cuando es una
    decisión sobre los datos (`use_exog`, `differentiation`,
    `calendar_features`, `target_transformer`, `dropna_from_series`) que
    pusieron las reglas y el forecaster nuevo no admite (los no
    autorregresivos; `use_exog` solo el baseline). Cada valor dice quién lo
    eligió: `differentiation=1 (chosen by the user)`.
  - No se nombra lo que el plan nuevo vuelve a decidir (una decisión de las
    reglas con un forecaster autorregresivo, el estimador que las reglas
    vuelven a elegir al entrar o salir de DMV, D14), los valores sin efecto
    (None, `False`, `'none'`, `[]`, `{}`: `calendar_features=[]` o
    `target_transformer='none'` no cambian nada con ForecasterStats), las
    claves pasadas en la llamada, ni lo ya nombrado como edición a mano.
  - Los lags, las ventanas y el estimador que eligieron las reglas no se
    nombran al cambiar de familia: son del forecaster que se sustituye y
    el cambio pedido ya lo dice. Sí cuando los eligió el usuario. Tampoco
    `transformer_exog` ni `categorical_features`, que no son decisiones de
    `plan()` (pregunta en la PR).
  - V29: con un estimador nuevo (pasado, o elegido otra vez por cambiar de
    familia) y sin `estimator_kwargs`, los del plan se descartan, como
    hasta ahora (no tienen por qué valer para otro estimador), y el aviso
    los nombra con el estimador para el que se escribieron. Lo dicen la
    descripción de `estimator_kwargs` de `RefinePlanArgs` (el único cambio
    del golden de esquemas), `RefinePlanOverrides`, el paso 3 del SKILL.md
    y `docs/api/mcp.md`.
  - El texto llega al contexto del LLM por `plan.warnings`; los goldens no
    cambian (ningún escenario cambia de familia). El check de pago de
    `check_ask_context.py` queda para la fase 7.
- **D19. 4a: una sola cuenta del coste de una comparación** (2026-10-18).
  Concretado en [#108](https://github.com/skforecast/skforecast-ai/pull/108):
  - `count_comparison_cost` (`execution/comparison.py`) cuenta, sin
    ejecutar nada, los entrenamientos, los ajustes de estimador y las
    ventanas de inferencia de cada candidato a partir de su forecaster y de
    la estrategia compartida, con el baseline incluido (0 ajustes) y con
    candidatos por defecto o explícitos. La usan `compare()` y el
    `create_cv` del MCP (`compare_estimator_fits` y
    `compare_inference_windows`, que ahora cuentan también el baseline); el
    resultado la guarda en `ComparisonResult.cost` (`ComparisonCost`, con
    un `CandidateCost` por candidato, públicos en `skforecast_ai.schemas`).
  - V19: el umbral (50 ajustes, 2000 ventanas) se aplica al total. Un solo
    `LongTrainingWarning` antes del primer candidato, con el total y lo que
    pone cada uno (los directos con entrenamientos x estimadores), en vez
    del aviso por candidato. El aviso de ventanas ya sumaba.
  - V06: `cost.n_fits` de `compare` es el total de entrenamientos, no se
    renombra: así `n_fits`, `estimator_fits` e `inference_windows` de una
    comparación son totales, y `cost` tiene las mismas claves en
    `create_cv`, `backtest` y `compare`. `n_folds` sigue siendo el de la
    estrategia compartida. Un candidato entrena como en skforecast: 0
    veces ForecasterFoundation, una por fold ForecasterStats, y el
    baseline como cualquier otro. `ComparisonResult.cv_config['n_fits']`
    describe la estrategia y no cambia (tampoco el contexto del LLM).
  - El `cost` de la respuesta de `compare` es esa cuenta previa, así que
    un candidato que falla cuenta (antes solo sumaban los que corrían).
  - V18 (de 3f): `cost_remedies` (`_utils.py`) nombra solo lo que baja el
    coste: `refit` entero o `refit=false` si la estrategia entrena más de
    una vez y para un forecaster que no sea ForecasterStats ni
    fundacional; menos folds (con `skip_folds` salvo si corre
    ForecasterStats, que lo rechaza, V17); un horizonte más corto solo para
    un directo que entrena una vez y sin Stats ni fundacional al lado (para
    ellos, con el `fold_stride` por defecto, son más folds); menos series
    para el fundacional. Lo usan el `CostNotice` (separado para `backtest`
    y para `compare`), el `CompareCostNotice` y el aviso de la comparación.
    La regla 2 de las instrucciones remite a los remedios del `CostNotice`.
  - Con candidatos explícitos el agente no ve la cuenta antes de llamar a
    `compare`: llega en su respuesta. Verla antes es 4b (D3).
  - Revisión: el baseline se queda en los desgloses con 0, para que se vea
    que está incluido. Construir todos los planes de los candidatos antes
    de contar (un candidato con plan inválido cuenta hoy el coste de su
    forecaster sin ejecutar nada) va con 4b, que necesita la cuenta antes
    de ejecutar también con candidatos explícitos.
- **D3. La confirmación de coste repite la cifra** (2026-10-18). Por
  encima del umbral, `backtest` y `compare` del servidor MCP exigen
  `confirm_cost` con el número de ajustes que devolvió `create_cv` (el
  total de D19). Si falta o no coincide, error con el coste y la pista de
  preguntar al usuario. Un `confirm_cost=True` a secas lo pasaría siempre
  el modelo pequeño (lanzaba con el aviso leído, 12 de 12); repetir la
  cifra obliga a haberla leído, y una estrategia que cambia invalida la
  confirmación vieja. En la API de Python y en la CLI, que decide una
  persona, basta `confirm_cost=True`. Va en 4b, que también construye los
  planes de los candidatos antes de contar (D19).
- **D4. V05: las columnas del CSV de métricas de `forecast` se renombran**
  (2026-10-18) para que coincidan con las del backtest (nombres de
  skforecast y `levels`), con una línea en "Before upgrading". Va en 3c-ii,
  junto con RMSE como métrica del servidor.
- **D20. 3d: aviso cuando el estimador no es el recomendado** (2026-10-19),
  en [#110](https://github.com/skforecast/skforecast-ai/pull/110). Solo en
  el servidor MCP:
  - El recomendado es el primero de `select_estimator_and_candidates` para
    el `task_type` del plan, con `estimator_n_observations` (D14): el que
    elegiría `plan()` para ese forecaster, no el del perfil. Un plan DMV con
    Ridge no avisa aunque el perfil recomiende LightGBM para
    ForecasterRecursiveMultiSeries. Solo los cuatro forecasters
    autorregresivos: ForecasterStats, los fundacionales y el baseline nunca
    avisan. Vive en `recommendation/estimator_choice.py`
    (`estimator_change`).
  - Solo cuenta un estimador elegido: `estimator` en `overridden_fields`
    (pasado a `plan`, `refine_plan` o los `candidates` de `compare`). El
    ganador de un `compare` sin `candidates` calla: lo eligió una
    comparación entre candidatos de las reglas y quedó medido. "Por un
    consejo de faltantes" se dice como hecho comprobable: el estimador es
    el que nombra el consejo (`select_nan_tolerant_estimator`), el
    recomendado no acepta faltantes y los datos los tienen (objetivo,
    fechas que faltan o exógenas usadas). El plan no guarda por qué se
    cambió, ni lo guardará.
  - MCP: un `EstimatorNotRecommendedNotice` (source `plan`) calculado en el
    servidor en `backtest` y `forecast`. Nombra los dos estimadores, dice
    si es el del consejo de faltantes y pide decir en la respuesta que el
    estimador no es el recomendado, cuál lo es y por qué se cambió. El paso
    3 del SKILL.md lo nombra.
  - La API de Python no avisa: quien cambia el estimador es el propio
    usuario y ya lo sabe, un warning en cada `backtest()` y `forecast()`
    sería ruido, y el contexto de `ask()` ya dice "Chosen by the user
    instead of the rules: estimator". Ese contexto no nombra el estimador
    recomendado y no lo hará: sin cambios en los goldens ni check de pago.
- **D21. 3e: avisos del forecast** (2026-10-18), en
  [#109](https://github.com/skforecast/skforecast-ai/pull/109). H11 y H4
  del check con agentes de la 0.4.0:
  - H11: `forecast` del servidor MCP sin `test_size` lleva un
    `UnmeasuredPlanNotice` (source `runtime`) cuando ningún `backtest` ni
    `compare` del servidor midió su plan: dice que no hay medida de
    precisión, que lo diga, que lo mida (`create_cv` con ese plan y
    `backtest` o `compare`) antes de presentarlo como fiable y que no le dé
    la precisión de otro plan.
  - Un plan está medido cuando un `backtest` de él terminó, o cuando corrió
    como candidato de un `compare` (cualquiera, no solo el ganador: un plan
    reconstruido con las decisiones de otro candidato predice lo que la
    tabla puntuó). Un backtest rechazado o un candidato que falla no miden.
  - Dos planes son el mismo cuando vienen del mismo perfil (`profile_id`:
    las mismas decisiones sobre otros datos u otro objetivo son otro plan)
    y coinciden en todo salvo `interval` e `interval_method`, que no cambian
    las predicciones puntuales, y lo que describe o dice de dónde vienen las
    decisiones (`explanation`, `warnings`, `llm_refined_fields`,
    `overridden_fields`), que un candidato de `compare` registra distinto
    para las mismas decisiones. Se comparan planes, no ids, así que no
    repite el falso aviso del `WARN` de H11 con un plan reconstruido con un
    intervalo ni con el ganador de `compare` que ya era el plan del agente.
    La métrica no cuenta (revisión, abajo).
  - Lo medido vive en el estado del servidor (`measured_plans`, una clave
    SHA-256 por plan), no en el store: sigue valiendo cuando el store
    expulsa el backtest o la comparación. "La sesión" es la vida del
    servidor, como los ids.
  - Un forecast con `test_size` no lleva el aviso (es una medida) y cuenta
    como medida del forecast del futuro de ese plan (revisión, abajo).
  - Solo en el servidor: la API de Python y la CLI no tienen sesión ni
    guardan lo que se midió, y quien llama es una persona que tiene el
    backtest a la vista. `ask()` sobre un forecast del futuro ya recibe
    "No evaluation metrics were computed".
  - H4: `render_metrics_section` recibe el plan; con `end_train` (un
    forecast con `test_size`) dice antes de las métricas que es una
    evaluación hold-out sobre fechas que ya están en los datos, no el
    pronóstico del futuro, con el fin del entrenamiento y los pasos. Llega
    a `describe()` (el resumen del servidor) y al contexto de `ask()`.
    Golden nuevo `forecast_holdout_evaluation`; los demás no cambian. El
    check de pago de `check_ask_context.py` queda para la fase 7.
  - El SKILL.md y el check con agentes no cambian aquí: van a la fase 6 y a
    "Herramientas de mantenimiento" (el `WARN` de H11 puede leer el notice
    en vez de comparar ids).
  - Revisión (2026-10-19): la métrica no cuenta como decisión (no cambia
    las predicciones: un plan medido con otra métrica sí está medido), y un
    forecast con `test_size` del mismo plan cuenta como medida del forecast
    del futuro (es una evaluación hold-out). El aviso no nombra los planes
    medidos, y volver a perfilar el mismo fichero empieza de cero (va por
    `profile_id`).
- **D23. 4b: la confirmación de coste, concretada** (2026-10-20), en
  [#113](https://github.com/skforecast/skforecast-ai/pull/113). Concreta
  D3 y lo que D19 dejó para 4b:
  - En la API de Python es un error, no un aviso: `CostNotConfirmedError`
    (subclase de `InvalidInputError`, código `invalid_argument`, campo
    `confirm_cost`), con `figure`, `cost`, `description` y
    `comparison_cost`. Un aviso llega cuando la ejecución ya empezó y no la
    para, que es lo que 4b corrige; gastar horas de máquina es una decisión
    que la librería no puede tomar por la persona (principio 3: no hay
    automatización silenciosa, y la ejecución no se degrada a otra).
  - `confirm_cost: bool | int = False` en `backtest()` y `compare()`. True
    es el camino que documenta la API para una persona; un entero confirma
    solo esa cifra, y es la forma que el servidor pide al agente. El
    servidor pasa la cifra del agente al núcleo, que hace la comprobación
    una sola vez y antes de ejecutar nada: en `backtest()`, después de todas
    las demás (un backtest que va a fallar no pide antes confirmación); en
    `compare()`, una vez construidos los planes (las comprobaciones del
    backtest de cada candidato van después, y un candidato que falla ahí
    cuenta). La CLI pasa True con `--confirm-cost`, y el tip del error
    nombra la opción.
  - La cifra es la de ajustes de estimador; la de ventanas de inferencia
    cuando solo esas pasan su umbral (un fundacional tiene 0 ajustes). Con
    las dos por encima, en un `compare`, los ajustes.
  - Una ejecución confirmada no avisa con `LongTrainingWarning`: el error
    sustituye al aviso en `backtest()` y `compare()`. `create_cv` del
    servidor sigue dando el `LongTrainingWarning` con el coste del
    backtest, y su `CostNotice` da la cifra de cada ejecución (`backtest` y
    `compare` sin `candidates`). Sin "about" en el coste de `compare`: la
    cifra es exacta.
  - `compare()` construye los planes de todos los candidatos antes de
    contar. Un candidato cuyo plan no se construye falla ahí (su
    `CandidateFailedWarning` antes de contar y de ejecutar nada), no cuenta
    en `cost` y sus dos eventos de progreso llegan en su turno, en el orden
    de los candidatos. Orden de los avisos: los de los planes, el error de
    coste, la ejecución. `failures` sigue el orden de los candidatos. El
    coste de `create_cv` para `compare` sin `candidates` aplica el mismo
    filtro (`buildable_candidates`), para que las dos cuentas coincidan.
  - Error del servidor: código propio, `cost_not_confirmed` (campo
    `confirm_cost`), no `invalid_argument`, que invita al agente a corregir
    el argumento y repetir la llamada con la cifra que trae el propio
    error, sin preguntar al usuario. El mensaje da el coste y el desglose
    (y, con otra cifra, que no es la del coste); la pista, no repetir la
    llamada hasta que el usuario conteste, con las estrategias más baratas;
    `details`, `confirm_cost`, `cost` y, para `compare`, `candidates`. Es
    un código del servidor (`SERVER_ERROR_CODES`): el núcleo sigue con
    `invalid_argument`, porque en Python y en la CLI decide una persona.
    Tiene su fila en la tabla de errores del SKILL.md y en
    `docs/api/mcp.md`; las instrucciones del servidor no nombran códigos y
    el golden de esquemas no cambia.
  - El contexto del LLM no cambia (goldens iguales): sin check de pago.
  - Revisión (2026-10-20): de acuerdo con la cifra de un fundacional (sus
    ventanas) y con el entero en Python, con True como el camino que
    documenta la API para personas; el código del error pasa a
    `cost_not_confirmed` (arriba). Que el check con agentes marque un
    `confirm_cost` pasado antes de que conteste el usuario va a la fase 7.
- **D22. 2c-ii: cobertura y anchura del intervalo medidas en el backtest**
  (2026-10-20), en [#112](https://github.com/skforecast/skforecast-ai/pull/112),
  sin cálculo propio en los scripts: `coverage` e
  `interval_width` salen de skforecast 0.27 (#1409):
  - El resumen de `backtest()` (y lo que leen `describe()`, `ask()` y el
    servidor MCP) ya no las lista con las demás métricas: una frase propia
    las da junto a la cobertura nominal (`upper - lower` de `interval`), con
    el número de predicciones; por serie con varias (las 10 de menor
    cobertura si hay más) y la media de la fila `average`, y la anchura en
    las unidades de cada serie. La sección del plan dice "nominal coverage".
  - Aviso: `IntervalCoverageWarning` (público, en la librería) cuando la
    cobertura de una serie queda por debajo de `nominal - max(2 *
    sqrt(nominal * (1 - nominal) / n), 0.05)`, con `n` las predicciones de
    esa serie con los dos límites. Los dos errores estándar evitan que salte
    por azar con pocas predicciones; los 5 puntos, que salte por una
    diferencia que no cambia cómo se lee el intervalo con muchas. Nombra
    hasta 5 series, de menor a mayor cobertura. No tiene en cuenta la
    autocorrelación de los pasos de un mismo fold (pregunta en la PR).
  - `compare()`: `coverage` e `interval_width` van después de las métricas
    en la tabla (la fila `average` con varias series) y no ordenan; el
    resumen dice qué son. Los avisos de cada candidato se silencian y un
    solo `IntervalCoverageWarning` nombra los candidatos por debajo.
  - MCP: `IntervalCoverageNotice` (source `runtime`) en `backtest` y
    `compare`, en lugar del aviso de la librería: su texto y que dé la
    cobertura medida, también en un `forecast` del mismo plan, sin
    presentar el intervalo con su nivel nominal. SKILL.md y
    `docs/api/mcp.md` lo explican.
  - `forecast` con `test_size` no añade `coverage` ni `interval_width`: una
    sola ventana de `steps` valores no mide una cobertura (con 12 valores,
    dos errores estándar del 80 % son 23 puntos y el valor solo puede ser
    un múltiplo de 1/12). Si se quiere por coherencia, iría en 3c-ii, que
    renombra esas columnas (D4) (pregunta en la PR).
  - Test de skforecast#1416: el intervalo `[0.1, 0.9]` de ForecasterStats
    es más estrecho que el del 95 % en el forecast y en el backtest (la
    razón de las anchuras es z(0.9) / z(0.975)), y la línea en las notas de
    la 0.5.0 va ya en esta PR. El check de pago de `check_ask_context.py`
    queda para la fase 7.
  - Revisión (2026-10-20): basta el suelo de 5 puntos para la
    autocorrelación de los pasos de un fold (`n` sigue contando
    predicciones, no folds); no hace falta issue en skforecast para el `n`
    exacto con valores reales que faltan; `forecast` con `test_size` se
    queda sin cobertura; `compare` da un solo aviso que nombra los
    candidatos, no uno por candidato. Los valores fijos que salen del
    ajuste de un ARIMA se comparan con `rtol=1e-4` (la anchura difiere un
    4.7e-5 relativo en macOS arm).
- **D24. RMSE en vez de MSE en el panel de métricas por defecto**
  (2026-10-20). El MSE va en unidades al cuadrado y cuesta leerlo; el RMSE
  va en las unidades del objetivo, al lado del MAE. skforecast 0.27 lo
  acepta por nombre ([#1424](https://github.com/skforecast/skforecast/pull/1424)),
  así que el script no se complica. La métrica que ordena y elige no
  cambia, solo el panel. Va en su propio PR de 3f, después de 3c-ii
  (#114): cambia todos los scripts por defecto, sus goldens y el contexto
  del LLM. *[script]* *[LLM]*
- **D25. 3c-ii: RMSE como métrica y las columnas de las métricas del
  forecast (V05)** (2026-10-20), en
  [#114](https://github.com/skforecast/skforecast-ai/pull/114). Concreta D4:
  - `root_mean_squared_error` entra en `ALLOWED_METRICS`, en el orden de
    skforecast (detrás de `mean_squared_error`): `metric` de `plan`,
    `refine_plan`, `forecast` y `compare`, `--metric` de la CLI y el enum
    del servidor (golden de `tool_schemas.json`). El script del backtest lo
    pasa por nombre, como las demás métricas: skforecast lo acepta desde
    skforecast/skforecast#1424 (rama `0.27.x`, ver "Dependencia de
    skforecast 0.27.0"). El script del forecast con `test_size`, que
    calcula él mismo las métricas, lo importa de `sklearn.metrics` como las
    demás.
  - La selección automática no cambia: el panel por defecto sigue siendo
    MAE, MSE y MASE (más MAPE lejos del cero). Poner RMSE en lugar de MSE
    en el panel es D24, en un PR propio de 3f.
  - Unidades: el `MetricUnitNotice` de D16 da también la de MSE, en las
    unidades del objetivo al cuadrado, siempre que esté entre las métricas
    (también en el panel por defecto), y la de RMSE, en las del objetivo,
    en un `backtest`, un `forecast` o el leaderboard de `compare`. Orden:
    MAPE, sMAPE, MSE, RMSE. El SKILL.md lo nombra en la regla de no derivar
    cifras (pedir `root_mean_squared_error` en `metric` de `plan` en vez de
    sacar la raíz del MSE) y en "Inputs", con las dos unidades. Las
    instrucciones del servidor no nombran la raíz.
  - V05: las métricas de `forecast` con `test_size` tienen las columnas de
    las del backtest del mismo plan: una por métrica, con su nombre, y
    `levels` cuando skforecast la da (varias series, y
    ForecasterDirectMultiVariate con su única serie). Con una serie no hay
    columna `levels`, como en `backtesting_forecaster`. Llega a
    `ForecastResult.metrics`, al CSV del servidor, a la tabla de la CLI y
    al contexto de `ask()`: las fixtures de los goldens del contexto pasan
    al formato real, y el check de pago queda para la fase 7. Línea en
    "Before upgrading".
  - La tabla la construye el script con varias series (cambian sus goldens
    de renderizado). Con una serie, el script calcula una variable por
    métrica y el runner solo las junta en la tabla; los scripts de una
    serie siguen imprimiendo `MAE  : ...` y no construyen la tabla.
  - Revisión (2026-10-20): con una serie, sin columna `levels`, como el
    backtest; RMSE por nombre, resuelto en skforecast; RMSE en el panel por
    defecto, decisión aparte (D24); el aviso de unidades da la de MSE
    cuando se pide, sin nombrar la raíz en las instrucciones del servidor;
    el runner solo junta lo que calcula el script.
- **D26. 5-0: la estrategia sin `differentiation`** (2026-10-20), en
  [#115](https://github.com/skforecast/skforecast-ai/pull/115), tras
  skforecast/skforecast#1423 (skforecast toma el orden del `window_size`
  del forecaster y lo depreca en `TimeSeriesFold`):
  - `create_cv` no tenía argumento `differentiation` (ni en Python, ni en
    la CLI, ni en el MCP): la estrategia copiaba el orden del plan
    (`derive_cv_defaults`). Se quita ese campo: el `TimeSeriesFold` de la
    librería y de los scripts, la clave de `cv_config` (también en
    `BacktestResult` y `ComparisonResult`, y en el JSON de `CVResult.cv`)
    y "differentiation order N" de la explicación. La API rompe solo ahí:
    línea en "Before upgrading".
  - Sobran la comprobación de `backtest()` (la estrategia y el plan con el
    mismo orden) y la copia de la estrategia por candidato de `compare()`,
    con su frase en la explicación: una estrategia sirve para planes de
    cualquier orden, y los candidatos de un `compare` la comparten tal
    cual.
  - Una estrategia guardada con el campo (un `CVResult` de la 0.4.x
    guardado con pickle, un `TimeSeriesFold` construido a mano con
    `differentiation`) se acepta y su orden se ignora, como hace
    skforecast: no cambia los folds y el que corre es el del plan. Sin
    aviso propio: el `FutureWarning` de skforecast ya sale al construir el
    `TimeSeriesFold`, y un pickle no lo construye. Un script anterior que
    lo pasa se describe sin él (`backtest_cv_from_code`, sin el
    `FutureWarning`). Los bundles de la CLI (perfil y plan) no llevan
    estrategia: no cambian.
  - Lo que se calcula sobre los folds no leía el orden de la estrategia:
    `plan_window_size` (y la ventana de `_read_positions`) ya suma el del
    plan, como `forecaster.window_size`. El único que lo pasaba, el
    splitter de D15 (`_series_never_forecast`, por `set_params`), da los
    mismos folds sin él (`TimeSeriesFold.split` nunca lo usó) y emitía el
    `FutureWarning`. Comprobado contra el backtest real con estrategias
    sin el orden: 300 configuraciones al azar de una serie (recursivo y
    directo, sin orden, 1 y 2) dan la misma ventana, el mismo fallo de la
    primera ventana, los mismos folds y los mismos ajustes del estimador
    (el coste de D19 y D23), y la estrategia por defecto de `create_cv`
    corre cuando no avisa; 600 multiserie (D15) nombran las mismas series
    que faltan en las predicciones. Dos multiserie fallaron dentro del
    script sin que nada lo anunciara: un fold que reentrena con una
    ventana fija en la que ya no queda ninguna serie, igual sin
    diferenciación y con un estimador que acepta faltantes. Es de
    skforecast (nueva fila en "Dependencia de skforecast 0.27.0").
  - El contexto del LLM pierde `- differentiation: None` de
    `<backtesting_strategy>` (10 goldens, contexto y `describe()`); el check
    de pago va en la fase 7. Las salidas guardadas de los dos notebooks
    muestran todavía la fila `differentiation` de la estrategia: cambian
    al volver a grabarlos en la fase 7.
  - El golden de esquemas cambia solo en la descripción de
    `differentiation` de `CandidateArgs`; las instrucciones del servidor no
    lo nombran. SKILL.md, `docs/api/mcp.md` y la guía de la CLI dicen que
    una estrategia sirve para cualquier orden.
- **D27. 3f-1: RMSE en el panel por defecto y lo que quedó de #104**
  (2026-10-21), en
  [#117](https://github.com/skforecast/skforecast-ai/pull/117). Revisión:
  el umbral de MSLE es el de sklearn (un valor `<= -1`, no "cualquier valor
  negativo" como decía 3f); un plan que llega a `backtest()` o `forecast()`
  no se vuelve a comprobar contra las métricas (ya se comprobó al crearlo);
  con ForecasterDirectMultiVariate las reglas de MAPE y MSLE miran todas
  las series aunque solo se evalúe una, y se deja así; no se propone a
  skforecast comprobar el dominio de la métrica en `backtesting_forecaster`
  (skforecast-ai ya lo hace en el plan). Concreta D24 y las preguntas 1, 3 y 4 de la revisión de
  [#104](https://github.com/skforecast/skforecast-ai/pull/104) (D16):
  - Panel por defecto: MAE, `root_mean_squared_error` y MASE, más MAPE
    lejos del cero, en ese orden (RMSE ocupa el sitio del MSE). La métrica
    que ordena y elige no cambia. El script del backtest lo pasa por
    nombre; el del forecast con `test_size` lo importa de
    `sklearn.metrics`. Cambian todos los scripts por defecto (88 líneas de
    los goldens de renderizado, todas MSE por RMSE) y el valor por defecto
    de `ForecastPlan.metrics_to_compute`. El `MetricUnitNotice` del panel
    por defecto da la unidad de RMSE; la de MSE sale solo cuando se pide.
  - La explicación del plan añade, tras la frase de la métrica, "MAPE is
    not computed: it divides each error by the actual value, and ..." con
    el rango que da `describe_series_near_zero`. Llega al contexto del LLM
    (la explicación del plan) y cambia sus goldens; las fixtures de
    métricas de `tests/fixtures_llm.py` pasan a RMSE, como el panel real.
  - `compare()` con MAPE pedido en un objetivo cerca del cero: el aviso de
    cada plan se silencia y `compare()` da uno solo, tras construir los
    planes y antes de contar el coste, con candidatos por defecto y
    explícitos (antes, uno por candidato en los dos casos: los planes se
    construyen otra vez fuera de `resolve_default_candidates`). Los
    `warnings` de cada plan lo conservan. Sigue siendo un `UserWarning`
    (pregunta 5 de #104 sin decidir).
  - MSLE con un objetivo con algún valor `<= -1` (el dominio que rechaza
    sklearn desde 1.6, la mínima): `InvalidInputError` con `field='metric'`
    al construir el plan (`check_metric_domain`, en `metric_selection.py`),
    y en `compare()` una sola vez antes de los candidatos. Valores entre -1
    y 0 se aceptan, como sklearn; una predicción `<= -1` sobre un objetivo
    por encima sigue fallando dentro del script.
  - Pendiente para la fase 7: el check de pago de `check_ask_context.py` y
    volver a grabar las salidas de los tres notebooks, que muestran MSE en
    el panel (`first-forecast.ipynb` también). Su texto ya dice RMSE, como
    el README y la guía de instalación.

- **D28. 3f-3: avisos de planes y estrategias** (2026-10-21), en
  [#118](https://github.com/skforecast/skforecast-ai/pull/118). Revisión:
  el script c_02 de la auditoría no se actualiza (es la prueba de entonces;
  basta la ejecución protegida); "(refined by the LLM)" para lags y
  ventanas que refinó el LLM; el `FutureExogNotice` no nombra las
  categóricas que el modelo descarta, solo las columnas que lee; aceptar
  `skip_folds` con ForecasterStats (o al menos `[]` como `None`) queda a
  criterio de skforecast. V17, V21 y
  lo que quedaba de la revisión de
  [#107](https://github.com/skforecast/skforecast-ai/pull/107) (D18):
  - V17: skforecast 0.27 sigue rechazando `skip_folds` para
    ForecasterStats (cualquier valor que no sea None, `[]` incluido), así
    que `create_cv()` lo rechaza con `InvalidInputError` en `skip_folds`
    (`invalid_argument` en el MCP), y `backtest()` y `backtest_code()` con
    un `TimeSeriesFold` que lo lleva fallan antes de ejecutar (campo `cv`),
    como con el `gap` de un directo. Con `prompt`, una sugerencia del LLM
    con `skip_folds` para Stats se reintenta. Un `compare()` sin
    candidatos sobre una estrategia con `skip_folds` deja fuera a
    ForecasterStats con un `UserWarning` y una frase en la explicación, y
    el coste de `create_cv` (`compare_estimator_fits`) ya no lo cuenta. Un
    candidato explícito de Stats falla con el error de `backtest()`.
  - V21: el comportamiento correcto depende de la interfaz. En Python y la
    CLI se queda el `IgnoredArgumentWarning`: `fixed_train_size=True` con
    `refit=False` es el valor por defecto de `TimeSeriesFold`, y un error
    rompería código que skforecast acepta. El MCP lo rechaza
    (`invalid_argument` en `fixed_train_size`, salvo ForecasterStats, que
    se reentrena en cada fold), como ya decía su esquema: el agente que lo
    pasa espera una ventana que rueda entre reentrenamientos que no hay, y
    un aviso no le impide describir así el backtest. Cambia la descripción
    del esquema (decía que "no correría", y corre), junto con la de
    `skip_folds`: son los dos únicos cambios del golden.
  - `plan_data_warnings` (`profiling/data_profile.py`): un plan con
    `use_exog=False` no lleva los avisos de las exógenas (faltantes por
    columna, números escritos como texto) en `describe()`, el contexto de
    `ask()` (`render_dataset_section` con el plan) ni las notices del
    `plan` del MCP; el 20 % de faltantes se recalcula solo con el objetivo
    (con datos anchos, sobre `span_index_length`, que son sus filas salvo
    que falten fechas). Los datos de un `compare` y del perfil siguen
    teniéndolos todos. Ningún golden cambia; el check de pago de
    `check_ask_context.py` queda para la fase 7.
  - `FutureExogNotice` sí se alcanzaba: con los modelos fundacionales que
    el servidor corre sin `--allow-model` y no aceptan categóricas
    (`soda-inria/tabicl-ts`, `theforecastingcompany/t0`, `Synthefy/Nori`)
    y también con ForecasterStats, que solo lee las numéricas. Pedía la
    columna categórica, que `forecast` rechaza en el fichero de un
    fundacional. Ahora nombra `used_exog_columns`, y sin ninguna no hay
    notice.
  - D18 revisado: los lags y las ventanas que refinó el LLM se nombran
    como "(refined by the LLM)" cuando el plan nuevo los pierde;
    `transformer_exog` y `categorical_features` se nombran "(chosen by the
    rules)" cuando el plan leía columnas numéricas o categóricas y el
    forecaster nuevo no los usa (no autorregresivo; para las categóricas,
    tampoco cuando el modelo nuevo las lee él mismo, como Chronos-2), salvo
    con `use_exog` en la llamada o editados a mano. Las ediciones a mano y
    las decisiones que se pierden van en un solo
    `PlanEditsDiscardedWarning` (y una entrada de `plan.warnings`). Los
    lags, las ventanas y el estimador de las reglas siguen sin nombrarse.

- **D29. 3f-2: los faltantes que quedaron de
  [#105](https://github.com/skforecast/skforecast-ai/pull/105)** (D17)
  (2026-10-21), en
  [#119](https://github.com/skforecast/skforecast-ai/pull/119):
  - Exógenas de cada fold (`validate_backtest_exog`, en `backtest()` tras
    las comprobaciones del objetivo): con un estimador que no acepta
    faltantes, `DataContentError` (`data`, con `DATA_VALUES_HINT` en el MCP)
    cuando una predicción que las métricas puntúan sería NaN por una
    exógena que falta, nombrando columnas (y serie, en largo) y fechas, como
    `validate_future_exog`. Replica skforecast: cada fecha lee su fila; un
    recursivo predice también el gap, y una predicción NaN la leen los lags
    que la alcanzan, una ventana toda NaN y, con diferenciación, todos los
    pasos siguientes; los directos (sin gap, D28) y ForecasterStats solo su
    fila (Stats con un NaN en el gap no falla). Con varias series, solo las
    que el fold pronostica (la regla de D15, ahora `_series_in_folds`) y las
    fechas en que tienen valor; en ancho comparten las exógenas, en largo
    cada serie las suyas; ForecasterDirectMultiVariate se puntúa en su
    nivel. Una fecha que falta (`asfreq`) cuenta como faltante de todas las
    columnas, y el mensaje lo dice. Con una serie el backtest fallaba en las
    métricas ("Input contains NaN"); con varias (también DMV), skforecast
    predice NaN sin error (la vía `np.dot` de los modelos lineales no pasa
    por la comprobación de sklearn) y las métricas los descartaban sin
    avisar: también es error, como en `forecast()` con las futuras. Un
    estimador que acepta faltantes, un fundacional y el baseline no se
    comprueban, y no avisan (pregunta en la PR). Las categorías de un fold
    que su ventana de entrenamiento no tiene (el encoder las lee como NaN)
    no se miran (pregunta en la PR). Contrastado con el backtest real en
    unas 460 configuraciones al azar (una serie, ancho y largo; recursivo,
    directo, Stats, multiserie y DMV; gap, lags, ventanas, diferenciación,
    `refit`, fechas que faltan, series que empiezan tarde), sin diferencias.
  - Filas de entrenamiento en `forecast()` y `forecast(test_size=...)`
    (`validate_training_rows`, antes de `validate_evaluation_partition`): la
    regla de `_check_training_rows` de D17 sobre las filas que entrena el
    script, todos los datos o la partición hasta `end_train` ("Every
    training row of the forecast from ..."). Contrastado con el
    `forecast()` real en unas 450 configuraciones al azar (34 en que falla),
    sin diferencias.
  - El `MissingValuesWarning` de skforecast de las series que se quedan
    fuera de algunos folds (#1415, #1427) no se captura. Para recibirlo, el
    script tendría que correr con `suppress_warnings=False`, y entonces los
    procesos de joblib (`n_jobs='auto'` paraleliza ForecasterRecursiveMultiSeries
    con Ridge o RandomForest) imprimen en stdout los avisos de skforecast de
    los ajustes y las predicciones de sus folds, fuera de cualquier filtro
    del llamante: en el servidor MCP escribirían en el canal stdio del
    protocolo, y en Python saldrían en la terminal. Reproducido con
    skforecast puro. Se resuelve mejor en skforecast (nueva fila en
    "Dependencia de skforecast 0.27.0"); hasta entonces no cambian ni el
    script ni el runner.
  - `DataProfile.closed_weekdays` (días de 0 a 6, vacío por defecto; un
    perfil guardado sin el campo lo lee vacío): los días de
    `regular_gap_weekdays` que ya calculaba la nota de fechas que faltan.
    `create_cv` da el consejo de los días de cierre solo con ellos y los
    nombra ("If the business is closed on Sundays, fill them with 0 in the
    data, after asking the user, or impute the target to backtest every
    fold."); con huecos al azar en datos diarios ya no lo da. ", or" en vez
    de "; otherwise," para que el mensaje más largo (tres días, el máximo
    con `'D'`, que necesita la mitad de sus fechas) quepa en un notice.
  - ForecasterDirectMultiVariate: `validate_backtest_windows` mira cada
    serie en la ventana de cada fold con la regla del modo de predicción
    (la de `_check_wide`, que `forecast()` ya aplicaba): error con un
    estimador que no acepta faltantes, aviso con uno que los acepta y error
    con la diferenciación cuando falta uno de los últimos valores del nivel.
    skforecast predecía NaN sin error y las métricas los descartaban.
    Contrastado en 150 configuraciones al azar, sin diferencias. Sus filas
    de entrenamiento no se miran.
  - El `MissingValuesNotice` dice siempre que `backtest` comprueba los
    folds (antes, solo con faltantes del objetivo), y el aviso de
    `create_cv` de las exógenas, que `backtest()` las comprueba antes de
    ejecutar. Ningún golden del contexto del LLM cambia, ni el de esquemas
    del MCP.

- **D30. 5a: entradas que no se validan y errores** (2026-10-27,
  [#121](https://github.com/skforecast/skforecast-ai/pull/121)). V25, V33,
  G04, V30, V31 y V32:
  - V25: la regla vive en el núcleo (`_validate_window_features` rechaza
    una clave que no sea `stats` ni `window_size`, nombrándola con las
    válidas), así que también la API de Python y la CLI. En el MCP,
    `WindowFeatureArgs` es un `TypedDict` cerrado (golden de esquemas:
    `additionalProperties: false`, el enum de `stats` y `window_size >= 1`)
    con un `BeforeValidator` que aplica antes la comprobación del núcleo,
    para que el agente reciba su mensaje y no el "Extra inputs are not
    permitted" de pydantic. El `WindowFeature` de `PlanOverrides` (lo que
    devuelve el LLM) no se cierra: cambiaría el esquema que ve el modelo
    (pregunta en la PR).
  - V33: `validate_estimator_kwargs` construye el estimador con los
    argumentos y, si es de scikit-learn, llama a `_validate_params()` (API
    privada de scikit-learn, estable desde la 1.2); el constructor de
    `Arima` ya comprueba sus valores. LightGBM, XGBoost y CatBoost solo
    los comprueban al ajustar: siguen dando `execution_failed`. Los tests
    que hacían fallar el script con `solver='no-such-solver'` pasan a
    `solver='lbfgs'` (válido solo, rechazado por Ridge al ajustar con
    `positive=False`), y los de seguridad llevan el valor hostil en el
    `objective` de LightGBM.
  - G04: `resolve_end_train` y `count_test_observations` reciben
    `time_zone` y colocan la fecha como `create_cv` coloca un
    `initial_train_size`: una fecha con zona sobre las fechas en su zona
    (`aware_index`, que pasa de `recommendation/backtesting.py` a
    `_dates.py`), una sin zona sobre las horas locales. Así se arregla
    también un desfase de una hora tras el cambio de hora de primavera
    (con `test_size` entero o fecha sin zona, el test empezaba una hora
    antes). Fecha con zona en datos sin zona: `invalid_argument` en
    `test_size` que pide quitarla. `end_train` sigue siendo una hora
    local sin zona.
  - V30: `training_length_needed` (más que la ventana; un directo, la
    ventana más `steps`) es la regla de `first_window_issue`, ahora
    compartida. Se comprueba al principio de
    `validate_evaluation_partition` sobre la rejilla del perfil, salvo
    ForecasterRecursiveMultiSeries (sus series las mira
    `validate_series_lengths`) y los que no tienen ventana (Stats,
    fundacionales). `insufficient_data` en `test_size`, con el horizonte
    más largo que cabe "keeping the rest of the plan" en el `hint`.
  - V31: `check_default_folds_fit`, en `create_cv()` solo cuando no se
    pasa `initial_train_size` (con uno explícito y un `fold_stride` menor
    sí caben dos folds): `insufficient_data` con `field` `plan`
    (`plan_id` en el MCP), porque lo que hay que cambiar es el horizonte
    del plan (pregunta en la PR). El `hint` da el horizonte más largo cuyos
    dos folds dejan la primera ventana que necesita el forecaster, y
    recuerda `forecast` con `test_size` para una sola ventana.
  - V32: `CandidateFailure.error_type` es la clase real (se quita
    `_reported_type_name`): `InvalidInputError: ...` en la tabla, los
    avisos, `AllCandidatesFailedError` y el contexto del LLM, que nombraba
    `ValueError`. El servidor reconoce así los errores propios y envía su
    mensaje. `get_failure` con el id de una comparación y sin `candidate`
    da `invalid_argument` en `candidate` con la lista de los fallidos; si
    ninguno falló, `invalid_argument` en `object_id`. Línea en "Before
    upgrading" (el tipo cambia) y descripción de `candidate` en el golden
    de esquemas.
  - El contexto del LLM cambia solo en el tipo de los candidatos fallidos;
    ningún golden cambia (la fixture usa `ImportError`). El check de pago
    de `check_ask_context.py` queda para la fase 7.
  - Preguntas de la PR, resueltas al mergear (2026-10-28): el error de V31
    va en `field='plan'`, porque lo que cambia es el horizonte del plan.
    `get_failure` sin candidato da un error con la lista de los fallidos, no
    todos los fallos juntos. `_validate_params()` es privada pero estable
    desde scikit-learn 1.2 (se pide `>=1.6`), y el test de V33 avisa si
    cambia. V30 se salta si `end_train` no cae en la rejilla del perfil: el
    script falla con su propio error, no en silencio. El desfase del cambio
    de hora lleva una línea en "Before upgrading", porque cambian el
    hold-out y sus métricas. Cerrar el `WindowFeature` que devuelve el LLM
    va aparte, en la fase 5.

- **D?. 5b: lo que comprueban y cuentan `backtest()` y `compare()`**
  (2026-10-28, esta PR). D15 en `compare()`, V24, series que faltan en
  algunos folds, avisos pequeños de faltantes, ForecasterFoundation y el
  orden de las filas en datos anchos:
  - `compare()` ya llamaba a `backtest()` por candidato, así que un
    candidato ForecasterRecursiveMultiSeries que no pasaba D15 ya fallaba
    con su motivo; lo que faltaba es cuándo. Las comprobaciones de
    `backtest()` que dependen del plan (`_check_backtest_run`: objetivo
    infinito, gap de un directo, `skip_folds` de Stats, primera ventana,
    D15, ventanas y exógenas de D29, estimador instalado) se hacen para
    cada candidato al construir los planes, con sus avisos silenciados (los
    da el candidato al correr): un candidato que falla una es un fallido
    antes de que corra ninguno, con el error de `backtest()` en la tabla y
    en `get_failure`, sin `generated_code`, y no cuenta en `cost`. Todos
    fallidos: `AllCandidatesFailedError`, como siempre. Un candidato
    fundacional sin backend también falla antes y no cuenta.
  - V24: con `candidates`, el plan de la estrategia no se añade (los
    candidatos son la elección del usuario y corren tal cual). Si un
    candidato toma sus mismas decisiones (las de `add_strategy_candidate`,
    `match_strategy_plan`), el texto de la estrategia nombra su fila ("The
    strategy was created for the plan of row 'x'"); si ninguno, un
    `UserWarning` (notice `UserWarning` en el MCP) y el resumen dicen que no
    se comparó. `strategy_plan_name` sigue siendo None con `candidates`: no
    hay fila añadida, y la frase del contexto del LLM sobre "las filas con
    nombre de forecaster" no vale para candidatos del usuario. `'Strategy
    plan'` es un nombre reservado siempre, con o sin `CVResult`
    (`InvalidInputError` en `candidates`, `invalid_argument` en el MCP). El
    script `d_03` de la auditoría deja de reproducir; `e_02` usa el nombre
    reservado y ahora recibe `invalid_argument`, y con ese candidato
    renombrado el resumen y un notice dicen que el plan refinado no se
    comparó (su comprobación final solo busca "plan of row", así que sigue
    imprimiendo `REPRODUCED`).
  - Series que faltan en algunos folds: `series_left_out_of_folds` lee de
    las predicciones (`level`, `fold`) los folds que pronosticaron cada
    serie y los compara con los folds cuyas fechas puntuadas (tras el gap)
    tienen un valor de ella, sobre los folds que parte el script
    (`_split_span`, compartido con D15). ForecasterRecursiveMultiSeries y
    ForecasterFoundation en varias series. El resumen de `backtest()` lo
    dice al final (`'item_2': in 7 of its 8 folds with values`, hasta 5
    series) y `backtest()` da un `UserWarning` con el mismo texto, que el
    MCP pasa a notice; `compare()` silencia el de cada candidato y da uno
    solo, también en su resumen, que nombra los candidatos. Contrastado con
    las series que skforecast da como no pronosticadas en folds con valores
    (`_warn_levels_not_predicted_multiseries`, espiado en backtests reales)
    en 31 configuraciones al azar (ancho y largo, Ridge, LightGBM e
    HistGradientBoosting, diferenciación, gap, `fold_stride`, `refit`,
    `fixed_train_size`, `skip_folds`), 17 con series fuera de algún fold:
    sin diferencias. Ningún golden del contexto del LLM cambia.
  - Exógenas con un estimador que acepta faltantes: `validate_backtest_exog`
    avisa (`UserWarning`, el texto de `forecast()` con las futuras: "...
    treats them as missing values; check that they are meant to be
    missing.") con las mismas columnas y fechas que daría el error, sin
    fallar. Con varias series, las últimas ventanas con faltantes del
    objetivo solo se descartan con diferenciación. Las categorías por fold
    no se miran (pregunta en la PR).
  - ForecasterFoundation: skforecast pronostica una serie en un fold solo si
    tiene un valor en el test del fold (tras el gap) y otro en su contexto,
    los `context_length` valores antes del fold desde su primer valor
    (`_backtesting_foundation`); si no, la deja fuera sin aviso. D15 lo
    comprueba: `insufficient_data` para una serie que ningún fold
    pronostica (empieza en el último fold, acaba antes de los folds, o un
    tramo de faltantes más largo que el contexto), con "una
    `initial_train_size` posterior" solo si tiene valores que evaluar.
    `context_length` sale de `estimator_kwargs` o del adaptador
    (`foundation_context_length`). Contrastado con `_backtesting_foundation`
    y un forecaster de pega (sin backend) en 400 configuraciones al azar,
    67 con series sin pronosticar, sin diferencias. Las que faltan solo en
    algunos folds las cuenta el punto anterior.
  - Orden de las filas en datos anchos (#1356, #1435): un test en
    `test_integration_standalone_script.py` fija que las predicciones de
    columnas `item_3, item_1, item_2` siguen ese orden en `forecast()` y en
    el script, con los valores del orden alfabético. La línea de "Before
    upgrading" queda para la consolidación, como dice la tabla.

## Decisiones abiertas

Se toman en el PR que las necesita y se pasan a la sección de arriba.
Ninguna abierta ahora.

## Dependencia de skforecast 0.27.0

La 0.5.0 no sale hasta que skforecast 0.27.0 esté publicado con estos issues
resueltos. Cada hallazgo que sea mejor resolver en skforecast se añade aquí
con su issue, y el lado de skforecast-ai se diseña para usar el arreglo de
skforecast, no para rodearlo. Mientras la 0.27.0 no esté en PyPI, el hook de
arranque de las sesiones en la nube instala skforecast desde su rama
`0.27.x`, así que se puede desarrollar contra ella.

| Issue | Qué pide | Qué hace skforecast-ai cuando llegue | Estado |
|:--|:--|:--|:--|
| [#1357](https://github.com/skforecast/skforecast/issues/1357) | Nombres de serie enteros (G02) | Nada que quitar: los ids como texto de 1b se quedan, porque conservan los ceros (`001`) | Resuelto en `0.27.x` ([#1412](https://github.com/skforecast/skforecast/pull/1412), 2026-10-18) |
| [#1406](https://github.com/skforecast/skforecast/issues/1406) | Avisar de una serie que no se pronostica en ningún fold (G03), y, por un comentario de 2026-10-18 (D17), también de la que se descarta de un fold por un faltante en su última ventana | 2b se queda en la comprobación previa y el aviso del perfil: los scripts corren con `suppress_warnings=True` y fallar antes de ejecutar es mejor para un agente. Lo que no cubre la comprobación previa (una serie que falta solo en algunos folds) puede leerse del `MissingValuesWarning` nuevo de skforecast (ver 3f) | Resuelto en `0.27.x` ([#1415](https://github.com/skforecast/skforecast/pull/1415), 2026-10-19) |
| [#1410](https://github.com/skforecast/skforecast/issues/1410) | Una serie con exactamente `window_size` observaciones en la ventana de entrenamiento de un fold multiserie (2b) | Nada: el backtest falla dentro del script con "must be greater than the maximum window size"; con el arreglo, la serie se descarta de ese fold como las más cortas, que es lo que ya supone la comprobación de 2b | Resuelto en `0.27.x` ([#1418](https://github.com/skforecast/skforecast/pull/1418), 2026-10-19) |
| [#1409](https://github.com/skforecast/skforecast/issues/1409) | Cobertura y anchura del intervalo en las métricas del backtesting (D11) | 2c-ii las lee de la salida del backtesting, sin cálculo propio en el script | Resuelto en `0.27.x` ([#1420](https://github.com/skforecast/skforecast/pull/1420), 2026-10-20) |
| [#1411](https://github.com/skforecast/skforecast/issues/1411) | El error "All samples have been removed due to NaNs" aconseja `dropna_from_series = False`, que falla con un estimador que no acepta faltantes (D17, #105) | Nada: la comprobación previa de 3a ya da el consejo que funciona antes de ejecutar; con el arreglo, el error de skforecast dentro de un script también lo dirá | Resuelto en `0.27.x` ([#1422](https://github.com/skforecast/skforecast/pull/1422), 2026-10-20) |
| Sin issue ([#1416](https://github.com/skforecast/skforecast/pull/1416)) | `ForecasterStats.predict_interval` ignoraba `interval` y devolvía siempre el intervalo del 95 % (`alpha=0.05` por defecto ganaba a `interval`) | Afectaba sin aviso a skforecast-ai 0.4.x: el script de un forecast de ForecasterStats con intervalo llama a `predict_interval(steps=..., interval=...)` sin `alpha`, así que un 80 % salía al 95 %. Nada que cambiar en el código; falta un test que lo fije (un intervalo `[10, 90]` de ForecasterStats más estrecho que el del 95 %, en el forecast y en el backtest) y una línea en las notas de la 0.5.0 al consolidar | Resuelto en `0.27.x` (2026-10-19) |
| Sin issue | El skill `metric-selection` describía MAPE como "Percentage error" sin decir que sklearn devuelve una fracción (D16, #104) | Nada: corregido en la rama `0.27.x` de skforecast y sincronizado aquí (2026-10-18) | Hecho |
| Sin issue ([#1424](https://github.com/skforecast/skforecast/pull/1424)) | `root_mean_squared_error` por nombre en el backtesting, como las demás métricas de regresión (3c-ii) | Nada que rodear: el script del backtest lo pasa por nombre, como las demás métricas; el del forecast con `test_size` lo importa de `sklearn.metrics`, como el resto de sus métricas | Resuelto en `0.27.x` ([#1424](https://github.com/skforecast/skforecast/pull/1424), 2026-10-20) |
| Sin issue ([#1423](https://github.com/skforecast/skforecast/pull/1423)) | La estrategia ya no repite la `differentiation` del forecaster: se toma de su `window_size`, y `differentiation` de `TimeSeriesFold` y `OneStepAheadFold` (y `window_size` de `OneStepAheadFold`) quedan deprecados, con un `FutureWarning`, hasta su retirada en 0.29.0. Una misma estrategia sirve para forecasters con distinta diferenciación | 5-0: dejar de pasar `differentiation` a la estrategia, y quitar la exigencia de que coincida con la del plan. Hasta entonces la suite de `0.5.x` falla contra la cabeza de `0.27.x` (16 tests, por el `FutureWarning`) | Resuelto en `0.27.x` (2026-10-20); el lado de skforecast-ai, en [#115](https://github.com/skforecast/skforecast-ai/pull/115) (5-0, D26) |
| Sin issue ([#1425](https://github.com/skforecast/skforecast/pull/1425)) | `freeze_params=True` de `backtesting_stats` no congelaba nada: la selección automática de `Arima` y `Ets` se repetía en cada reentrenamiento (desde 0.20.0) | Los scripts de backtest de ForecasterStats ya pasaban `freeze_params=True`, así que ahora congelan de verdad: con `Arima` o `Ets` automáticos y reentrenamiento, las métricas cambian desde el segundo fold y corre más rápido (en h2o, ForecasterStats pasa a ganar a Ridge en `compare`). Tests con valores fijos actualizados y una línea en "Before upgrading". El coste de D19 y D23 sigue contando un ajuste por fold, que sigue siendo cierto (se reestiman los coeficientes) | Resuelto en `0.27.x` (2026-10-20) |
| Sin issue ([#1427](https://github.com/skforecast/skforecast/pull/1427), encontrado en 5-0) | Un fold de `backtesting_forecaster_multiseries` sin ninguna serie falla con un error que no tiene que ver. Sin series que entrenar (`refit` con `fixed_train_size=True` en una ventana donde todas acabaron antes, o les quedan `window_size` valores o menos): `fit` falla con "all series must have a Pandas RangeIndex or DatetimeIndex with the same step/frequency ... Found frequencies: []", porque `check_preprocess_series` recibe un dict vacío. Sin series que predecir (ninguna tiene última ventana antes del fold): "`last_window` must have as many values as needed to generate the predictors". Reproducido con skforecast puro. Con o sin diferenciación, y también con un estimador que acepta faltantes. Debería saltarse ese fold con el `MissingValuesWarning` de las series descartadas, o fallar con un error que lo diga | Nada que rodear: la comprobación previa de D15 mira las series que ningún fold pronostica, no los folds sin ninguna serie; con el arreglo, el script corre o explica el fallo. skforecast salta ahora el fold sin series, lo nombra en el `MissingValuesWarning` de #1415 y da un `ValueError` claro si ningún fold puede pronosticarse. Su regla de entrenamientos (solo se entrena un fold de reentrenamiento si su bloque pronostica algo, `_select_fit_folds_multiseries`) cuenta menos que la de D19 en esos paneles: la de skforecast-ai sobrestima, lo que es conservador para el aviso y la confirmación de coste. Con `refit` intermitente las dos cuentan igual (skforecast-ai ya contaba los folds marcados para entrenar, no `int(len(folds) / refit)`) | Resuelto en `0.27.x` (2026-10-21) |
| Sin issue ([#1430](https://github.com/skforecast/skforecast/pull/1430)) | `initial_train_size` se validaba contra la serie más larga en vez de contra el tramo de las series de un dict, y el split de un paso adelante de `ForecasterRecursiveMultiSeries` metía en el test series sin valores que evaluar | Nada: skforecast-ai ya trabaja sobre el tramo, y su comprobación previa de D15 rechaza antes de ejecutar el único caso que la validación antigua rechazaba por error (con un `initial_train_size` mayor que todas las series, alguna que empieza al principio del tramo acaba antes y ningún fold la pronostica). skforecast-ai no usa `OneStepAheadFold`; importará en el ajuste de hiperparámetros de la 0.6.0. Suite en verde contra su rama (2026-10-21) | Resuelto en `0.27.x` (2026-10-21) |
| No hace falta (encontrado en 3f-2) | El `MissingValuesWarning` de las series que no se pronostican en algunos folds ([#1415](https://github.com/skforecast/skforecast/pull/1415), [#1427](https://github.com/skforecast/skforecast/pull/1427)) solo sale con `suppress_warnings=False`, y con él los procesos de joblib de `backtesting_forecaster_multiseries` imprimen en stdout los avisos de skforecast de los ajustes y las predicciones de cada fold, fuera de los filtros del llamante (`warnings.catch_warnings` no llega a otro proceso). Que ese aviso, que habla del resultado y no de los datos, salga también con `suppress_warnings=True`, o que el backtest devuelva los niveles que pronostica cada fold | Nada que pedir: las predicciones de un backtest multiserie ya llevan `level` y `fold`, así que skforecast-ai sabe de ellas en qué folds se pronosticó cada serie, sin `suppress_warnings=False` ni el problema de joblib (punto de la fase 5, D29) | Descartado (2026-10-22) |
| Sin issue ([#1432](https://github.com/skforecast/skforecast/pull/1432), encontrado en 3f-2, 2026-10-22) | Con varias series y un estimador lineal, una exógena que falta en la predicción da predicciones NaN sin ningún error: el camino rápido de predicción (`np.dot`) se salta la comprobación de NaN de sklearn, y el NaN se propaga a los pasos recursivos. Después, las métricas multiserie descartan esas predicciones sin avisar. Reproducido con skforecast puro (10 predicciones NaN, métricas sin ellas, ningún aviso ni con `suppress_warnings=False`). Ahora `predict` falla con un predictor que falta, y también con uno de los últimos valores que revierten la diferenciación, con cualquier estimador (encontrado al revisar la PR). El backtesting de una serie falla en las métricas solo si hay predicciones NaN en fechas con valor observado: un faltante en una fila del `gap` que ningún retardo lleva al fold ya no lo rompe (regresión encontrada al revisar la PR, 2026-10-27). El backtesting multiserie sigue con predicciones NaN y un `MissingValuesWarning` | Nada que rodear: la comprobación previa de 3f-2 (D29) ya lo evita antes de ejecutar, así que el usuario sigue viendo el `DataContentError` de skforecast-ai. Los contrastes con skforecast de los tests (`test_read_positions.py`, `test_validate_backtest_exog.py`) fijan el comportamiento nuevo. Suite en verde contra `0.27.x` (2026-10-27) | Resuelto en `0.27.x` (2026-10-27) |
| Sin issue ([#1431](https://github.com/skforecast/skforecast/pull/1431)) | Las búsquedas de hiperparámetros ordenaban los candidatos por la tarea del forecaster (minimizar en regresión) y no por la métrica: con una métrica de "mayor es mejor" (`r2_score`) elegían el peor candidato. Ahora la dirección se deduce de la métrica (`_metric_greater_is_better`) | Nada: skforecast-ai no lanza búsquedas, y todas sus métricas son de "menor es mejor", así que `compare` sigue ordenando ascendente. Suite en verde contra su rama (2026-10-22). Importará en el ajuste de hiperparámetros de la 0.6.0. Cambian los skills `hyperparameter-optimization` y `metric-selection` y `llms-base.txt`: hay que sincronizarlos cuando entre | Se mergea en `0.27.x` (entra en 0.27.0) |
| [#1356](https://github.com/skforecast/skforecast/issues/1356) ([#1435](https://github.com/skforecast/skforecast/pull/1435)) | `X_train_series_names_in_` de ForecasterRecursiveMultiSeries seguía el orden alfabético con `encoding` distinto de `onehot`, y con él las filas de `predict` con `levels=None` y las claves de los residuos | Los scripts de forecast multiserie llaman a `predict` sin `levels`: con datos anchos cuyas columnas no van en orden alfabético, las filas de las predicciones siguen ahora el orden de las columnas (mismos valores); con datos largos no cambia, porque el reshape ya ordena los ids. Ningún test lo fijaba (los datos de los tests van en orden alfabético): falta uno, y una línea en "Before upgrading" al consolidar las notas. Suite en verde contra `0.27.x` (2026-10-26) | Resuelto en `0.27.x` (2026-10-26) |

Detalle de cada uno:

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
- **Serie con `window_size` observaciones en un fold** (2b), resuelto en `0.27.x` (#1410, #1418).
  `_extract_data_folds_multiseries` (`model_selection/_utils.py`) descarta
  del entrenamiento de un fold las series con `< window_size` observaciones
  de su primer a su último valor, pero `fit` exige más de `window_size`: una
  serie con exactamente `window_size` se queda y el backtest falla con
  "Length of 'item_2' must be greater than the maximum window size". Con
  `refit` y una serie que empieza tarde pasa en uno de cada `steps` casos
  (su longitud en la ventana crece de `steps` en `steps`). La comparación
  debería ser `<=`, en DataFrame y en dict.
- **Cobertura y anchura del intervalo en el backtesting** (D11):
  [#1409](https://github.com/skforecast/skforecast/issues/1409), feature
  request. Que `backtesting_forecaster` y
  `backtesting_forecaster_multiseries` con un intervalo de dos límites
  devuelvan en las métricas la cobertura (`calculate_coverage`) y la anchura
  media, por serie y en las filas agregadas. Hoy calculan las métricas solo
  con `pred`.

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
  con un intervalo (está anotado en el README del check). Desde 3e puede
  leer el `UnmeasuredPlanNotice` de la respuesta de `forecast` en vez de
  comparar ids, que quita también el falso aviso del ganador de `compare`.
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
`compare`. Las búsquedas de un paso adelante de skforecast dependen de
arreglos de 0.27 que skforecast-ai aún no ejerce: el split de un paso con
series que acaban o empiezan tarde
([#1430](https://github.com/skforecast/skforecast/pull/1430)), y que un
candidato que no puede evaluar nada se salte en vez de parar la búsqueda
(anotado en el roadmap de skforecast 0.27, `BUG-search-short-series.md`).
Desde skforecast 0.27
([#1431](https://github.com/skforecast/skforecast/pull/1431)) las búsquedas
siguen la dirección de la métrica (maximizan las `*_score`): el ranking de
skforecast-ai, que hoy ordena siempre ascendente porque todas sus métricas
son de "menor es mejor", tendrá que seguir la misma regla si se admite
alguna métrica de "mayor es mejor".

### Intervalos multiserie: residuos fuera de muestra

Lo que D11 dejó fuera de la 0.5.0. Los scripts multiserie usan residuos
dentro de muestra (`store_in_sample_residuals`), y la cobertura real queda
muy por debajo de la nominal (2c-ii la mide y avisa). skforecast admite
residuos fuera de muestra (`set_out_sample_residuals`), pero hace falta un
tramo de validación: cambia el coste del backtest y los scripts.

### pandas 3, cuando skforecast lo soporte

skforecast 0.26 declara `pandas<3.0`, así que hoy el resolvedor nunca
instala pandas 3 junto a skforecast-ai (que pide `pandas>=2.2`, sin cota
superior). Cuando skforecast lo admita, revisar lo que depende del dtype de
las columnas de texto, que en pandas 3 es `str` y no `object`:
`detect_categorical_exog` y `detect_numbers_as_text`
(`profiling/data_profile.py`) solo miran `object`, `category` y `bool`, así
que una exógena de texto no se trataría como categórica. Visto en
[#95](https://github.com/skforecast/skforecast-ai/pull/95). Pasar la suite
con pandas 3 antes de quitar la cota de skforecast.

### Días de cierre con `CustomBusinessDay` y `weekmask`

La solución de fondo para un negocio que cierra los mismos días de la
semana. Desde 1e
([#98](https://github.com/skforecast/skforecast-ai/pull/98), D9), unos
datos diarios sin domingos son `'D'` con los domingos como fechas que
faltan: `forecast` los predice, y `backtest` y `forecast` con `test_size`
fallan porque caen en los folds de test. El aviso y los errores lo dicen y
proponen rellenarlos con 0 pidiendo permiso. Una frecuencia sin esos días
(`pd.offsets.CustomBusinessDay(weekmask='Mon Tue Wed Thu Fri Sat')`) no
tendría huecos. Comprobado el 2026-10-16:

- skforecast 0.26 ajusta, predice (del lunes al sábado) y hace backtest en
  memoria con un índice de esa frecuencia, sin NaN.
- Su `freqstr` es `'C'`, que pierde la `weekmask`: `to_offset('C')` es de
  lunes a viernes, así que el `asfreq('C')` que emitiría el script quita los
  sábados sin avisar (260 filas de 312).
- Hace falta un campo en el perfil (la `weekmask`, o los días de cierre de
  `regular_gap_weekdays`) y emitir el offset en el script en vez de una
  cadena. Revisar también lo que lee la frecuencia como texto: la
  estacionalidad (`estimate_seasonality`), las variables de calendario, las
  exógenas futuras, `count_missing_timestamps` y el contexto del LLM.
- Decidir cuándo se elige: solo cuando los huecos son de días de la semana
  sin ninguna fecha (lo que ya detecta `regular_gap_weekdays`), y si un
  domingo abierto suelto (rebajas) lo descarta.
