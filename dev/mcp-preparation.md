# Preparativos para el servidor MCP de skforecast-ai

Estado a 30/09/2026. Base: rama `0.4.x`, con la sección 2 commiteada en `f87e89f`. La auditoría de la fase 1 (resultados en las secciones 4, 5, 7 y 9, y propuestas en la 10) está en la rama `feature/mcp-audit` y no toca `skforecast_ai/`. Este documento sirve para retomar el trabajo en otra sesión: qué se decidió, qué está hecho, qué falta y en qué orden, y cómo verificarlo.

**Cómo leerlo.** Las secciones 1 a 8 son el plan original. Cada punto pendiente lleva ahora el resultado de contrastarlo con el código, marcado como **Verificado**, **Corregido** o **Nuevo**. La sección 9 recoge lo que la auditoría encontró fuera de ese plan. La sección 10 propone decisiones y un orden de PRs, y está pendiente de revisión.

**Cómo se hizo la fase 1.**
- Once auditores independientes contrastaron cada punto con el código y reprodujeron los casos con scripts propios. Un segundo agente intentó refutar cada resultado; de unas 200 comprobaciones solo corrigió seis, y la más importante es la de `ForecasterStats` (sección 2).
- Siete diseñadores propusieron una solución por tema, eligiendo siempre la opción más conservadora. Después, un agente ordenó los PRs y otro revisó el conjunto.
- Los experimentos y prototipos se hicieron en el scratchpad de la sesión o en copias del repo, nunca en esta rama. Las pruebas de concepto de inyección solo crean un fichero marcador.
- Las líneas citadas son las de `0.4.x` en `4331e2c`. Los tiempos se midieron en una máquina compartida de 4 CPU con otros agentes en marcha: sirven como orden de magnitud.

## 1. Objetivo y decisiones de fondo

- **El objetivo es que skforecast-ai sea la herramienta que llaman los agentes de código** (Claude Code, Cursor, Claude Desktop, ChatGPT) cuando se les pide un forecast. El agente pone el LLM; skforecast-ai pone las decisiones deterministas (perfil, plan, CV, backtest, comparación) y el script que se ejecutó.
- **El MCP vive en skforecast-ai, no en skforecast.**
  - skforecast es una librería flexible basada en objetos de Python, y llega mejor a los agentes con skills y documentación, que ya existen.
  - MCP encaja con operaciones completas, con estado y validadas, que es lo que ofrece skforecast-ai.
  - Se presenta desde skforecast (README, documentación, registros de MCP con "skforecast" en el nombre), porque ahí está la comunidad.
- **Requisito de fondo antes del servidor: que el núcleo no falle sin avisar.** Un agente se cree un resultado `ok`, así que todo lo que hoy pasa sin error o falla tarde hay que convertirlo en un error claro o en un aviso dentro del resultado.

## 2. Hecho en la sesión del 30/09/2026

Commiteado en `f87e89f` (rama `0.4.x`). Los tres bloques tienen tests y entrada en `docs/releases/releases.md` (0.4.0).

1. **Fallos silenciosos del núcleo (punto 1).**
   - `profile()` lanza `ValueError` cuando un timestamp tiene varias filas con valores distintos. Antes, los datos en formato largo sin `series_id_column` perdían todas las series menos una. El mensaje propone la columna candidata. Las filas idénticas se eliminan con una nota en `DataProfile.warnings`, y el formato largo con fechas repetidas genera un script correcto.
   - `plan()` omite las variables de calendario cuyo nombre de columna ya existe como exógena (por ejemplo `month` y `hour` en `bike_sharing`) y lo dice en la explicación.
2. **Coste del backtesting.**
   - `create_cv()` entrena una vez por defecto (`refit=False`, como skforecast).
   - La explicación del CV y `cv_config['n_fits']` dicen cuántas veces se entrena, y con Direct también el total de ajustes de estimador.
   - `backtest()` y `compare()` emiten `LongTrainingWarning` por encima de 50 ajustes, porque los scripts silencian el de skforecast.
   - `compare()` sin `candidates` deja fuera las alternativas por encima de 500 ajustes, sin excluir nunca el forecaster recomendado.
   - Constantes: `LONG_TRAINING_FITS` y `COMPARE_FIT_BUDGET` en `_constants.py`.
3. **Validación temprana de entradas (punto 2).** Nuevo módulo `skforecast_ai/_validation.py`, usado por `plan()` y por el validador de `ForecastPlan`:
   - lista blanca de estimadores (`SUPPORTED_ESTIMATORS`);
   - claves de `estimator_kwargs` que sean identificadores válidos de Python (cierra la inyección de código por nombre de estimador o por clave);
   - nombres de kwargs comprobados contra el constructor: error, salvo en LightGBM y XGBoost, que avisan (los alias de LightGBM salen de `lightgbm.basic._ConfigAliases`);
   - intervalo `[lower, upper]` en (0, 1), simétrico para ForecasterStats y el baseline;
   - las 8 métricas de regresión (`ALLOWED_METRICS`), también en `forecast()`;
   - en evaluación, el test debe tener exactamente `steps` observaciones;
   - un `date_column` que no contiene fechas lanza error;
   - `plan()` lanza error si el índice datetime no tiene frecuencia, con la pista de `dayfirst`;
   - `lightgbm` pasa a ser dependencia obligatoria.

**Corregido (auditoría).**
- **`refit=False` no se aplica a `ForecasterStats`.** El backtesting de skforecast fuerza `refit=True` para cualquier estimador que no sea `skforecast.stats.Sarimax` (`skforecast/model_selection/_validation.py`, en torno a la línea 2004), y skforecast-ai siempre usa `Arima` con ForecasterStats. El `IgnoredArgumentWarning` queda silenciado por `suppress_warnings=True` ([rendering/backtesting.py:521](../skforecast_ai/rendering/backtesting.py#L521)).
  - Resultado: `cv_config['n_fits']` dice 1 y la explicación dice "trained once (no refit)", pero Auto-ARIMA se ajusta en cada fold (6 ajustes con el CV por defecto de h2o, comprobado contando llamadas a `Arima.fit`).
  - Además, la ventana de entrenamiento es de tamaño fijo, no creciente. El renderer solo escribe `fixed_train_size` cuando `refit` es verdadero ([rendering/backtesting.py:57](../skforecast_ai/rendering/backtesting.py#L57)), y el valor por defecto de `TimeSeriesFold` es `fixed_train_size=True`. `cv_config` dice `False`, pero cada ajuste usa 142 observaciones en h2o.
  - `count_estimator_fits` ([recommendation/backtesting.py:338](../skforecast_ai/recommendation/backtesting.py#L338)) también cuenta 1, así que ni el aviso ni el presupuesto de `compare()` lo ven. Ver 10.6.
- **El validador de `ForecastPlan` no comprueba los nombres de kwargs.** `validate_estimator_kwargs` solo se llama desde `plan()` ([assistant.py:520](../skforecast_ai/assistant.py#L520)). Un plan cargado desde JSON con `{'alpah': 1.0}` valida y falla dentro del script, y una errata en LightGBM no avisa.

## 3. Pendiente por parte del autor

- ~~Revisar y hacer commit de lo anterior.~~ Hecho en `f87e89f`.
- **Revisar esta auditoría**: las correcciones de las secciones 2, 4, 5 y 7, los hallazgos de la sección 9 y las decisiones y preguntas abiertas de la sección 10.
- **Antes de la release, lanzar `python tools/ai/check_ask_context.py` con un modelo real.** Cambiaron `llm/prompts.py` (regla 4 del CV: `refit=False` por defecto) y las explicaciones del plan y del CV. El informe se guarda según `tools/ai/ask_context_reports/README.md`. Con `--dry-run`, que no cuesta nada, ya se comprobó que los contextos se generan. Si se aceptan los PRs de la sección 10 que cambian explicaciones, conviene agruparlos antes de esa ejecución para pagarla una sola vez (10.8).
- **Entorno `skforecast_ai_py13`:** trae skforecast 0.25.0 (el proyecto exige `>=0.26`) y su instalación editable apunta a `skforecast-ai-home-page`, no a este checkout. Hasta arreglarlo, ejecuta siempre con `PYTHONPATH=.` (ver la sección 8).

## 4. Trabajo pendiente

El orden de esta sección era el recomendado antes de la auditoría. El orden propuesto ahora está en 10.8.

### 4.1 Seguridad: código ejecutable dentro de un plan (bloquea el MCP)

**Verificado, y el problema es mayor de lo que decía la auditoría.**

**Lo confirmado.**
- `ForecastPlan.preprocessing_steps[].code_snippet` se inserta en el script con `format_map` y se ejecuta con `exec`. Está en `_emit_preprocessing_steps`, [rendering/_helpers.py:170](../skforecast_ai/rendering/_helpers.py#L170): el snippet se escribe en la línea 193, y el `exec` está en [execution/_exec.py:50](../skforecast_ai/execution/_exec.py#L50), con todos los builtins.
- Solo se emiten los pasos con `blocking=True` (`_helpers.py:176`).
- `ForecastPlan.model_validate` acepta cualquier snippet, incluso un paso nuevo inventado.
- Se reprodujo creando un fichero:
  - con `forecast()`;
  - con `skforecast-ai forecast --from-plan` y `skforecast-ai backtest --from-plan`, que lo ejecutan;
  - con `forecast-code` y `backtest-code --from-plan`, que no lo ejecutan pero lo devuelven dentro del script.
- `transformer_y` ([rendering/single_series.py:64](../skforecast_ai/rendering/single_series.py#L64)) y `transformer_series` ([rendering/multi_series.py:73](../skforecast_ai/rendering/multi_series.py#L73)) se escriben como `f"{name}()"`, sin validar. `transformer_exog` no es un vector: el renderer ignora su valor y siempre escribe `StandardScaler`.
- `encoding` (`multi_series.py:70`) y `categorical_features` (`single_series.py:68`, `multi_series.py:79`) se escriben entre comillas simples sin escapar. Con una comilla en el valor se sale de la cadena: el forecast termina con normalidad y el código inyectado se ejecuta sin dejar rastro. `encoding` de las variables de calendario sí usa `repr` y es seguro.

**Vectores que la auditoría no listaba** (todos reproducidos creando un fichero marcador, salvo donde se indica):

| Origen | Vector | Dónde se escribe | Cómo llega |
|---|---|---|---|
| Plan | `forecaster_kwargs['differentiation']`, con `str()` | `single_series.py:70`, `multi_series.py:82` | plan en JSON |
| Plan | `forecaster_kwargs['dropna_from_series']`, con `str()` | `single_series.py:72`, `multi_series.py:84` | plan en JSON |
| Plan | `forecaster_kwargs['calendar_features']['features']` cuando es una cadena | `_helpers.py:355` | plan en JSON |
| Plan | `offset` y `n_offsets` del baseline, con `str()` | `rendering/baseline.py:29-37` | plan en JSON |
| Plan | `ForecastPlan.forecaster`, que no se valida: `'ForecasterRecursive\n<código>'` compila y se ejecuta | import en `_helpers.py:706` y `:776`, y el constructor | plan en JSON |
| Perfil | `DataProfile.frequency`, dentro de `asfreq('{frequency}')` | `_helpers.py:204`, `:311` y `:1083` | perfil en JSON: `--from-profile` y el perfil del bundle de `--from-plan`. Lo ejecutan `forecast --from-plan`, `backtest --from-plan` y `compare --from-profile` |
| **Datos** | Nombre de la columna de fecha o de serie con una comilla, en formato largo con filas duplicadas idénticas | la plantilla `drop_duplicates(subset=['{series_id_column}', '{date_column}'])` ([recommendation/preprocessing.py:326-328](../skforecast_ai/recommendation/preprocessing.py#L326)), rellenada sin comillas por `format_map` | **solo un CSV**. `profile()` incluso sugiere esa columna en su mensaje de error |
| **Datos** | Nombre de una exógena categórica con un salto de línea (un CSV lo admite entre comillas) | comentario `# Categorical exog excluded (...)` en [rendering/statistical.py:51](../skforecast_ai/rendering/statistical.py#L51) y `foundation.py:78` | **solo un CSV** y ForecasterStats o Foundation. `compare()` incluye ForecasterStats por defecto en datos mensuales. Reproducido con el CLI normal, sin JSON |
| **Override** | Id de modelo de Foundation con un salto de línea: `'autogluon/chronos-2-small\n<código>'` | comentario `# Create foundation model (...)` en [rendering/foundation.py:104](../skforecast_ai/rendering/foundation.py#L104) | `plan(estimator=...)`, `refine_plan()` y `--estimator`. skforecast valida el id solo por prefijo (`startswith`) |

Notas:
- `lags` también se escribe sin comillas (`_format_lags`, `_helpers.py:146-167`), pero en los métodos públicos lo frena, por casualidad, `_normalize_lags` ([_utils.py:321](../skforecast_ai/_utils.py#L321)), que lanza un `ValueError` de Python poco claro.
- Una comilla benigna rompe el script: una columna `store's id` en formato largo con duplicados da `SyntaxError` al ejecutar (reproducido de nuevo en esta sesión). Como `compile()` está fuera del `try` de `exec_rendered` ([execution/_exec.py:46](../skforecast_ai/execution/_exec.py#L46)), sale un `SyntaxError` sin envolver.
- Un `model_copy(update=...)` o una asignación sobre un plan guardado no pasa por el validador: el código inyectado se ejecuta antes de que falle la validación del resultado. En ese caso tampoco son seguros las claves de `estimator_kwargs` (`f"{k}={repr(v)}"` en `_helpers.py:936`, `statistical.py:69` y `foundation.py:105-108`), `interval_method` ni `steps`: solo lo son si el plan pasó el validador.
- Un `TimeSeriesFold` del usuario con `initial_train_size=pd.Timestamp(...)` genera una línea que no compila (`str()` en `rendering/backtesting.py:52`) y un `TypeError` sin envolver. Solo afecta a Python.
- Con un salto de línea en un nombre de columna o en un id de serie también se pueden falsificar etiquetas de sección (`</dataset>`, `<forecast_plan>`) en el contexto que recibe el LLM de `ask()`. Pasaría lo mismo con el futuro `describe()`.

**Lo que ya es seguro (verificado).**
- `data_path`, el target, las exógenas y los nombres de serie en las líneas de código normales, `end_train`, `interval` y los valores de `estimator_kwargs` se escriben con `repr`.
- `window_features` se escribe como literal de lista.
- `estimator` está en lista blanca, las claves de kwargs son identificadores, las métricas son un conjunto cerrado e `interval_method` es un `Literal`.
- En el CV, `TimeSeriesFold` rechaza tipos incorrectos, así que `differentiation` no es un vector por esa vía.
- No hay `eval` ni imports dinámicos con cadenas del usuario.

**Qué protege hoy y qué no.**
- `refine_plan()` y `plan()` reconstruyen el plan y descartan los vectores que vienen del plan (snippet, transformers, `differentiation`, `dropna`, calendario, `categorical_features`, `forecaster`).
- La regla de 4.5 ("nunca aceptar planes completos en JSON") es necesaria, **pero no suficiente**: no cubre los nombres de columna del CSV, el id de Foundation ni un perfil cargado desde JSON.
- La propuesta original de "regenerar el snippet desde `action`" tampoco basta, porque la propia plantilla de `drop_duplicates` es un sumidero.

**Propuesta**: ver 10.1.

### 4.2 Punto 3: que los avisos lleguen en el resultado

**Verificado, con dos correcciones importantes.**

- **`ForecastPlan.warnings` existe pero nadie lo rellena** ([schemas/plans.py:434](../skforecast_ai/schemas/plans.py#L434)).
  - El único constructor está en `assistant.py:731-746` y no pasa `warnings`.
  - Tampoco se muestra en ningún sitio (ni en el display ni en el contexto del LLM).
  - Un plan cargado desde JSON conserva la lista tal cual: cualquier texto viaja con él.
- **Fuentes que deberían ir ahí**, todas confirmadas:
  - `UnrecommendedForecasterWarning` en [assistant.py:447](../skforecast_ai/assistant.py#L447);
  - baseline con valores faltantes en `assistant.py:491` (un `UserWarning`);
  - kwargs desconocidos de LightGBM o XGBoost en [_validation.py:226](../skforecast_ai/_validation.py#L226), que no avisa si el paquete no está instalado.

  Las tres se vuelven a emitir cada vez que `refine_plan`, `compare`, `forecast*` o `backtest*` llaman a `plan()`.
- **Corregido: las variables de calendario omitidas no son un warning.** Son una frase en la explicación (`recommendation/explanation.py:117-122`), como decidió la sección 6. Si pasan a `plan.warnings`, que sea sin `warnings.warn`, o que salgan de esta lista (10.2).
- **Los backtests silencian los warnings de skforecast**: confirmado en [rendering/backtesting.py:107](../skforecast_ai/rendering/backtesting.py#L107), 139, 403 y 521. `suppress_warnings=True` ignora solo las 15 categorías de skforecast; los de sklearn, LightGBM o pandas sí salen.
- **Corregido: `forecast()` no deja salir los warnings de skforecast: los pierde.**
  - skforecast sustituye `warnings.showwarning` al importarse por un manejador de rich que escribe en `sys.stdout`.
  - Dentro de `exec_rendered`, `sys.stdout` es un `StringIO` que se descarta ([execution/_exec.py:49](../skforecast_ai/execution/_exec.py#L49)), así que el aviso desaparece.
  - Caso real: un NaN en la exógena futura da 9 de 12 predicciones NaN sin ninguna señal. `describe()` con `send_data=False` diría "Missing values: none".
  - Solo quien envuelve la llamada en `catch_warnings(record=True)` los ve.
- **Nuevo: esos mismos avisos de skforecast rompen `--format json` del CLI.**
  - Fuera de `exec_rendered` el manejador de rich los escribe en stdout, delante del JSON.
  - Reproducido con `profile` sobre un target con NaN intercalados (`MissingValuesWarning` del PACF, en [recommendation/autoregressive.py:222](../skforecast_ai/recommendation/autoregressive.py#L222)) y con `backtest` por encima de 50 ajustes (`LongTrainingWarning`): `json.load` falla en el carácter 0.
  - mcp 2.2 desvía el fd 1 a stderr mientras sirve, así que el protocolo no se rompe, pero el aviso no llega al agente.
- **`DataProfile.warnings`** ([schemas/profiles.py:198](../skforecast_ai/schemas/profiles.py#L198)) no aparece en `profile.explanation`, pero **sí** llega al contexto del LLM (`llm/context.py:303-304`), al display y a `model_dump`. Un `describe()` basado en ese contexto ya lo llevaría.
- **Precedente útil**, confirmado: `compare()` guarda los fallos en `failures: dict[str, CandidateFailure]` (con `error_type`, `message`, `traceback` y `generated_code`), en la columna `error` y en el contexto (`<failed_candidates>`).
- **Nuevo: los warnings de Python no sirven como canal en un servidor.**
  - Con los filtros por defecto, un aviso idéntico se muestra una sola vez por proceso.
  - `catch_warnings` es global al proceso (hasta Python 3.13, y en 3.14 solo deja de serlo en builds free-threaded). Con dos llamadas concurrentes, un filtro `ignore` puede quedarse puesto para siempre (sección 9).
- **Inventario**: hay 18 sitios con `warnings.warn` en el paquete.
  - Los que decide el núcleo y hoy se pierden en MCP o en JSON: los tres de `plan()` citados arriba y `LongTrainingWarning`.
  - Los que ya quedan guardados: los fallos y las exclusiones de `compare()`, que llegan a la explicación.
  - Los de los modos con LLM (`refine_plan`, `create_cv` con `prompt`) tampoco dejan rastro en el resultado, pero no se exponen por MCP.
- **Nuevo: `docs/api/exceptions.md` dice listar todos los avisos, pero le faltan** `LongTrainingWarning` y los `UserWarning` de `plan()`.

### 4.3 Punto 4: más decisiones del plan que se puedan cambiar

**Verificado, con matices.**
- Las claves son exactamente las que dice el documento: `plan()` ([assistant.py:340](../skforecast_ai/assistant.py#L340)) y `RefinePlanOverrides` ([schemas/plans.py:252](../skforecast_ai/schemas/plans.py#L252)) aceptan forecaster, estimator, estimator_kwargs, steps, interval, lags y window_features.
- Además:
  - `backtest()` y `backtest_code()` no aceptan `lags` ni `window_features`;
  - en el CLI, `forecast` y `backtest` no tienen `--lags` ni `--window-features`;
  - `compare()` solo admite las 5 claves de `CandidateConfig` más `metric`.
- **Cada override que falta está confirmado**, con dónde se decide hoy:
  - `use_exog` sale de `check_exog_usage` (`assistant.py:555-569`). Las columnas no se guardan en el plan: los renderers leen `profile.exog_columns`. Hoy es todo o nada, y la única forma de elegir columnas es quitarlas de los datos antes de `profile()`.
  - `calendar_features`: los nombres salen de `profile()` y la codificación de `plan()`, en `assistant.py:618-640`.
  - `differentiation`: ninguna regla lo activa nunca (no hay detección de tendencia). El renderer y `create_cv` ya lo consumen.
  - El transformer del target sale de `select_transformer_series` (`preprocessing.py:26-63`): `StandardScaler` para estimadores que no son árboles. El import de `StandardScaler` está fijo en `_helpers.py:689` y `:753`.
  - `dropna_from_series` sale de `select_dropna_from_series` (`preprocessing.py:120-164`). Cuenta las exógenas con NaN aunque el plan no las use.
  - `metric` solo existe en `compare()`: `plan()`, `refine_plan()`, `forecast*` y `backtest*` no la aceptan.
- **`refine_plan()` descarta las ediciones manuales sin avisar** (reproducido).
  - Solo conserva `steps`, `forecaster`, `interval`, el estimador dentro de la misma familia, `estimator_kwargs` si el estimador no cambia, y `lags` y `window_features` en los forecasters ML.
  - Todo lo demás se recalcula: `differentiation` se pierde, `end_train` se pone a `None` y `warnings` se vacía.
  - Una llamada sin overrides no deja el plan como estaba.
  - El CLI hereda el problema: `forecast`, `forecast-code`, `backtest` y `backtest-code` con `--from-plan` más cualquier override (incluso un simple `--interval`) pasan por `refine_plan()` y pierden lo editado en el JSON. La API de Python, en cambio, aplica `interval` sobre el plan sin rehacerlo.
- **`CandidateConfig`** ([schemas/plans.py:297](../skforecast_ai/schemas/plans.py#L297)): confirmado, 5 claves. Además, `compare()` no tiene parámetro `plan`, así que un plan refinado solo se puede comparar copiando sus lags y window features en un candidato.
- **Documentación**: [docs/user-guides/cli-usage.md:108](../docs/user-guides/cli-usage.md#L108) es falso (el calendario y la métrica no se pueden cambiar), y la línea 122 también (`forecast` y `backtest` no aceptan `--lags`).
- **Nuevo, relacionado:**
  - El CLI ignora `--steps` sin avisar cuando se usa con `--from-plan` (en `forecast-code`, `backtest-code`, `forecast` y `backtest`), mientras que Python lanza error.
  - Un CV queda atado a la `differentiation` del plan con que se creó: reutilizarlo con otro plan falla dentro del script. `compare()` con un candidato que diferencia falla hoy en todos los candidatos.
  - Con `ForecasterDirectMultiVariate` y `use_exog=False` (editando el plan), el script de forecast ajusta las exógenas como series; el de backtest lo hace bien.
  - Con ForecasterStats y solo exógenas categóricas: el plan dice `use_exog=True` y "Exogenous variables included", el script no usa ninguna, y `forecast()` exige exógenas futuras que luego descarta.
  - Cualquier override nuevo que se escriba en `forecaster_kwargs` cae en claves que hoy son vectores de inyección (4.1), así que la validación cerrada de 10.1 es un requisito previo.

### 4.4 Punto 5: resumen público para agentes

**Verificado, con correcciones.**
- **Las líneas de `_build_llm_context()` son exactas** (`schemas/results.py:123`, 214, 405 y 760; `schemas/profiles.py:345`). La implementan `CodeGenerationResult`, `SingleRunResult` (y con ella `ForecastResult` y `BacktestResult`), `CVResult`, `ComparisonResult` y `ForecastingProfile`.
- **Corregido: ya existe un método público**, `ExplainableResult.to_llm_context(send_data=False)` ([schemas/explainable.py:36](../skforecast_ai/schemas/explainable.py#L36)). Está exportado, pero no documentado. Lo que falta no es visibilidad, es contenido:
  - **El texto lleva instrucciones para el LLM de `ask()`** que confundirían a un agente de código: "Do not generate code yourself" (`llm/context.py:407-411`), "available to the user as `result.code`" (`:468-469`), "Do not re-rank" (`:640-646`) y "Do not name, count, or score" (`:685-687`).
  - **No hay nada para encadenar llamadas**: ni ids, ni siguientes pasos, ni qué se puede cambiar. `render_plan_section` omite `estimator_kwargs`, los transformers, `encoding`, `use_exog`, `dropna`, `end_train` y hasta el forecaster como línea propia.
  - **El coste está a medias**: `n_folds` y `n_fits` aparecen, pero el total de ajustes de estimador de Direct solo está en prosa, y en `compare()` no hay coste por candidato.
  - `backtest_code()` se describe como un script de predicción (modo `prediction`, sin métricas) y sin la estrategia de CV.
- **`ForecastPlan` no es un `ExplainableResult`.** `ask()` lo describe envolviéndolo en `CodeGenerationResult(profile, plan, code)` (`assistant.py:2426-2435`).
- **`send_data`**: `ask()` siempre usa `send_data=True` (`assistant.py:2449`). La ruta con `False`, que es la que usaría un tool, no tiene ningún golden ni ningún uso en producción. Además resume la columna `fold` como si fuera un dato y junta todas las series.
- **Corregido: los límites de tamaño existen, pero cubren poco.**
  - Los valores son correctos: 30 filas de predicciones, 5 series en estadísticas y PACF, 15 lags de PACF y 15 filas en el leaderboard.
  - Sin límite quedan la tabla de métricas (una fila por serie), la línea `Target` en formato ancho, las listas de exógenas, `missing_target`, `missing_exog`, los fallos y los lags del plan.
  - Con 200 series el contexto de un backtest llega a 29k caracteres, 24k de ellos de métricas; con 500 series, 42k en un forecast y 75k en un backtest.
- **Goldens**: hay 15 en `tests/tests_llm/golden/`, todos con `send_data=True` y como mucho 2 series.
- **Tamaños medidos**: ver la sección 7.

### 4.5 El servidor MCP

**Verificado, con correcciones.**
- **Paquete: corregido.**
  - Todavía no existen el extra `[mcp]` ni el comando `mcp`.
  - **`fastmcp` no está instalado**: solo `fastmcp-slim` 4.0.10 (cliente), que llega por `pydantic-ai`, y `from fastmcp import FastMCP` falla.
  - Sí está `mcp` 2.2.0, en el que `FastMCP` pasa a llamarse `mcp.server.mcpserver.MCPServer`. Se comprobó que funcionan el decorador de tools, `Context.report_progress` (también desde un tool síncrono), el `Client` en memoria y stdio, incluido un backtest de h2o a través de un servidor stdio real.
- **Tools, sin `ask()` ni modos con `prompt`: confirmado.** Sin LLM, `refine_plan` y `create_cv` están completos respecto a lo que decidiría el LLM, pero no respecto a los overrides que faltan (4.3).
- **Estado en el servidor: confirmado.** `CVResult`, `BacktestResult`, `ForecastResult` y `ComparisonResult` fallan al reconstruirse desde JSON (`needs_python_object`). `ForecastingProfile` y `ForecastPlan` sí se reconstruyen, y justo por eso son un vector de inyección (4.1).
- **Planes en JSON**: hay que ampliar la regla a los perfiles (4.1).
- **Datos por ruta o URL: corregido.**
  - Las URL las descarga el propio proceso con `pd.read_csv`, sin timeout, sin límite de tamaño y siguiendo redirecciones ([_utils.py:627-633](../skforecast_ai/_utils.py#L627)). Es un riesgo de SSRF, y un host que no responde bloquea la llamada para siempre.
  - Las rutas relativas se resuelven contra el directorio del servidor, no contra el del agente.
  - `exog` no acepta rutas: una cadena pasa la comprobación de longitud, porque mide la longitud de la cadena, y falla después con `AttributeError`.
- **Progreso: confirmado.**
  - `compare()` ya acepta `show_progress`.
  - El bucle por candidato está en `ForecastingAssistant.compare` (`assistant.py:2186-2244`), no en `execution/comparison.py`, y no tiene ningún hook.
  - La granularidad posible es por candidato: un solo candidato Auto-ARIMA tarda de 30 a 50 s en h2o sin ningún evento.
- **stdout: corregido.**
  - 0 bytes en el fd 1 solo en llamadas secuenciales sin avisos de skforecast; con avisos, el manejador de rich escribe en stdout (4.2).
  - mcp 2.2 protege el protocolo desviando el fd 1 a stderr mientras sirve.
  - **Con llamadas concurrentes, el `redirect_stdout` de `exec_rendered` deja `sys.stdout` apuntando a un `StringIO` y llega a tumbar CPython 3.11 con un segfault** (3 de 3 ejecuciones con un servidor stdio real y 8 backtests concurrentes). `MCPServer` ejecuta los tools síncronos en hilos concurrentes, así que **un lock de proceso es obligatorio** (sección 9).
- **Servidor vivo entre llamadas: no se pudo verificar lo de Foundation**, porque no hay backend instalado.
  - El arranque cuesta de 1,5 a 2,0 s importando `skforecast_ai`, más 0,6 a 1,0 s de `mcp`.
  - Las llamadas baratas no se aceleran en la segunda vuelta, y el ajuste de Auto-ARIMA (unos 13 s en h2o) tampoco.
- **Mensajes escritos para Python: confirmado, y la lista es mayor.** Además de `exc.failures[...]`, `refine_plan()` y `llm=`, hay unos 20 sitios con remedios de pandas (`to_datetime`, `dayfirst`, `asfreq`), `plan.use_exog`, `ComparisonResult.failures[...]` e instrucciones de `pip install`.
- **Nuevo: `MCPServer` oculta el texto de cualquier excepción que no sea `ToolError`.** El agente solo recibe "Error executing tool <name>". La capa del tool tiene que convertir todas las excepciones.
- **Nuevo: con parámetros opcionales planos no se distingue "omitido" de `null`**, que es justo la semántica de `refine_plan`. Hace falta un objeto `overrides` anidado.
- **Nuevo: cancelar una llamada no detiene el hilo**, que sigue hasta terminar (sección 9).
- **Skill para agentes**: es una propuesta de diseño, sin nada que verificar. Nota: un skill sobre el CLI enseñaría el ida y vuelta de `--from-plan`, que hoy ejecuta código (4.1), y sufriría la salida JSON rota (4.2).

## 5. Seguimientos menores

- **Formato largo, rutas que ya fallaban al generar el script.**
  - **Verificado (5.a).** El literal `'datetime'` está en [rendering/_helpers.py:1111](../skforecast_ai/rendering/_helpers.py#L1111); la línea 1087 es la de la definición. El mismo literal está en `:1070` (pivot a ancho, multivariante) y en `:1247` (exógenas en largo).
    - Falla `forecast()`, `backtest()` y `compare()`, no solo la generación.
    - Pasar `date_column` igual al nombre del índice no sirve: se registra como `None` y luego choca con `_match_profile_column`.
    - **Corregido: también se llega desde un CSV.** Un CSV largo con una celda de fecha vacía, o con un tiempo entero, deja `date_column=None`, la fecha pasa a ser una exógena y se acaba en el mismo literal. Falta un error cuando el formato es largo y no hay fecha.
  - **Verificado (5.b).** Con un `MultiIndex` el script falla en su primera línea (`data['date'] = ...`). Con niveles sin nombre, `profile()` lanza un `KeyError: 'series_id'` sin envolver desde `compute_series_pacf`, y con 3 niveles un error de pandas. Solo afecta a datos en memoria.
- **Choques de nombres entre lags o window features (`lag_1`, `roll_mean_7`) y exógenas: verificado.**
  - No es silencioso: skforecast falla al ajustar con "Duplicated feature names detected in X_train". Pero falla tarde, y ni el perfil ni el plan lo avisan.
  - Afecta a todos los forecasters con lags, y en el multivariante a `<serie>_lag_<k>`.
  - **Nuevo:** en `compare()` todos los candidatos con lags fallan y **el baseline sale ganador con estado `ok`**. Por MCP solo lo delatan `failures` y la explicación.
- **El coste de inferencia de ForecasterFoundation no entra en el presupuesto de `compare()`: verificado** (`recommendation/backtesting.py:365-366` devuelve 0).
  - Tampoco dispara `LongTrainingWarning` en `backtest()`.
  - **Nuevo, más grave:** ForecasterStats cuenta 1 ajuste con `refit=False`, pero skforecast reajusta en cada fold (sección 2).
- **`compute_series_pacf` lee los datos sin deduplicar: verificado, y es más amplio.**
  - Recibe el frame original: sin deduplicar, sin ordenar por fecha y sin aplanar el `MultiIndex`.
  - Con duplicados cambian los lags: en h2o, `[1, 9..14]` pasa a `[1, 12, 13, 15, ..., 27]`.
  - Con filas desordenadas el PACF sale vacío y se usan los lags por defecto, sin aviso.
  - Todo esto también ocurre por ruta CSV.
- **El alias `result` de `ask()`: verificado** (`assistant.py:2395`, docstring en `:2340-2342`, nota de la 0.3.0 en `docs/releases/releases.md:131`, test en `tests/test_assistant_ask.py:305`). Matiz: sin LLM, `ask(result=...)` lanza `LLMRequiredError` antes que el `DeprecationWarning`.
- **Oportunidad aparte del MCP, `diagnose()`: verificado lo que haría falta.**
  - `BacktestResult` guarda las predicciones con `fold` (y `level` en multiserie) y las métricas agregadas.
  - No guarda los valores reales, así que `diagnose()` necesita los datos otra vez. El horizonte se deriva de la posición dentro de cada fold.

## 6. Decisiones tomadas (no reabrir sin motivo)

- **Timestamps duplicados:** error si las filas difieren; si son idénticas, se eliminan con una nota.
- **Colisión entre calendario y exógenas:** se omite la variable generada, gana la columna del usuario, y se dice en la explicación. Sin warning.
- **`refit=False` por defecto,** alineado con el skill `backtesting-configuration`.
- **El coste se cuenta en ajustes de estimador, no en tiempo medido,** para que la decisión sea exacta, conocida antes de ejecutar y reproducible.
- **Umbrales:** 50 ajustes para el warning (el de skforecast) y 500 para excluir candidatos automáticos. `LongTrainingWarning` es la clase de skforecast, reutilizada.
- **Qué hacer depende de quién decidió:**
  - lo que decide el asistente (CV por defecto, candidatos automáticos) se puede cambiar;
  - lo que decide el usuario (su CV, candidatos explícitos) se respeta y solo se avisa.
- **Estimadores:** lista blanca; nada de rutas de import arbitrarias.
- **`test_size` debe coincidir con `steps`.** Para periodos más largos, `backtest()`.
- **Métricas:** las 8 de regresión de skforecast en todos los métodos.
- **`lightgbm`** es dependencia obligatoria.
- **Los validadores viven en `_validation.py`** para evitar el import circular con `_utils.py`.

La auditoría no reabre ninguna de estas decisiones. Dos matices:
- El coste "exacto y conocido antes de ejecutar" hoy no se cumple con ForecasterStats (sección 2). Contar un ajuste por fold aplica la decisión, no la cambia (10.6).
- La regla de colisión de calendario cubre las variables que genera la regla. Para las que pida el usuario de forma explícita, la sección 10.4 propone un error.

## 7. Datos medidos (para dimensionar el servidor)

Con `bike_sharing` (horario, 17.544 filas, `steps=24`, 220 folds):

| Caso | Tiempo |
|---|---|
| `compare()` con el CV por defecto (`refit=False`) | 66 s |
| `compare()` con `refit=True` (excluye Direct) | 145 s |
| Direct con `refit=True`, 5.280 ajustes (extrapolado, sin ejecutar) | ~64 min |
| Direct con `refit=False` | 17 s |

Con `h2o` (mensual, 204 filas), `compare()` tarda 51 s, de los que 30 s son Auto-ARIMA reentrenando en 6 folds. ~~Con el nuevo valor por defecto, `refit=False`, Auto-ARIMA se ajusta una vez.~~ (Falso: ver la verificación más abajo.)

| Tamaño (`store_sales`: 500 series, 913k filas) | Valor |
|---|---|
| `model_dump` del perfil | 259 KB |
| `model_dump` del backtest | 25 MB |
| Resumen para LLM del backtest | 48k caracteres |
| Backtest | 25 s |
| Import de `skforecast_ai` en frío | ~1,2 s |

**Verificación (fase 1).**
- **No se volvieron a medir** los tiempos de `bike_sharing` ni `store_sales`: la auditoría evitó esas ejecuciones por los límites de CPU.
  - Se confirmaron los 220 folds con `refit=False` del CV por defecto y los 5.280 ajustes de Direct con `refit=True`.
  - La exclusión de Direct se confirmó con `exclude_costly_candidates`.
- **Corregido: "Con `refit=False`, Auto-ARIMA se ajusta una vez" es falso.** Se reajusta en cada fold (sección 2).
  - Un solo ajuste automático sobre h2o tarda de 13 a 15 s, y un backtest con el CV por defecto (6 folds) de 30 a 50 s con la máquina cargada.
  - Por eso `compare()` en h2o sigue tardando de 25 a 50 s.
- **Import de `skforecast_ai`**: de 1,5 a 2,0 s en esta máquina. El grueso es `skforecast.model_selection` → sklearn → scipy.stats, cerca de 1 s. `mcp.server.mcpserver` añade de 0,6 a 1,0 s.

**Nuevas medidas.**

| Qué | Valor |
|---|---|
| `model_dump_json`, h2o: perfil / plan / CV / forecast en evaluación / backtest / compare de 4 candidatos | 1,8 KB / 1,1 KB / 3,6 KB / 7 KB / 9,4 KB / 33-45 KB |
| `model_dump_json`, items_sales (3 series): backtest de 990 filas / compare de 2 candidatos | 91 KB / 186 KB |
| `model_dump_json`, bike_sharing: backtest con las 5.280 filas de los 220 folds | 387 KB |
| `model_dump_json`, sintético de 500 series x 300 días: perfil / backtest de 45.000 filas | 228 KB / 4,6 MB |
| Extrapolado a `store_sales`: predicciones del backtest / con intervalo | ~26 MB / ~41 MB |
| `ComparisonResult` en JSON | incluye N+1 copias del perfil y las predicciones completas de cada candidato |
| Texto de `to_llm_context()` en h2o, items_sales y bike_sharing | de 1 a 5k caracteres |
| El mismo texto con muchas series | 29k (backtest, 200 series); 42k (forecast) y 75k (backtest) con 500 series |
| Prototipo de `describe()` con límites (10.5) | ~5,4k caracteres con 8, 200 o 500 series |
| `create_data_profile` sobre 913k filas y 500 series | 1,2 s |
| sha256 de un CSV de 158 MB (frente a `read_csv`) | 0,14 s (1,8 s) |
| Primer backtest con HistGradientBoosting (`n_jobs='auto'`) | de 5 a 25 s, y deja 3 procesos loky de ~170 MB cada uno |
| Memoria retenida por resultado | ~10 a 50 KiB en items_sales. Los resultados no guardan los datos de entrada ni el modelo ajustado |

## 8. Entorno y verificación

```bash
conda env list                      # confirmar el entorno con el autor (regla de CLAUDE.md)
E=/opt/homebrew/Caskroom/miniconda/base/envs/skforecast_ai_py13/bin
PYTHONPATH=. $E/python -c "import skforecast_ai; print(skforecast_ai.__file__)"   # debe ser este repo
PYTHONPATH=. $E/python -m pytest -n auto -q -p no:cacheprovider
$E/ruff check skforecast_ai tests
PYTHONPATH=. $E/mkdocs build -q -d <scratchpad>/site
PYTHONPATH=. $E/python tools/ai/check_ask_context.py --dry-run
```

- Los experimentos de reproducción se escriben en el scratchpad de la sesión, nunca en el repo.
- Los datasets de skforecast (`fetch_dataset("bike_sharing")`, `"h2o"`, `"items_sales"`, `"store_sales"`) cubren los casos útiles:
  - `bike_sharing`: exógenas con nombres de calendario, datos horarios largos;
  - `items_sales`: multi-series, también en formato largo con `melt`;
  - `store_sales`: escala.
- Estado de la suite al terminar la sesión: 1718 tests, todos en verde.
- **En una sesión en la nube** (claude.ai/code):
  - el hook de inicio instala el paquete con `[test,llm,docs]` y ruff, mediante pip o uv;
  - exporta `SKFORECAST_AI_DOCS_PRIVACY=false`, de modo que `mkdocs build` funciona sin el plugin de privacidad, cuyas descargas (unpkg.com, avatares de GitHub) bloquea la política de red por defecto;
  - se usa `python -m pytest -n auto` directamente, sin conda;
  - los hooks tienen sus propios tests: `python -m pytest .claude/hooks -q -p no:cacheprovider`.

## 9. Hallazgos nuevos de la auditoría (fase 1)

Lo que no estaba en las secciones 4 y 5. Severidad para el MCP: **B** = bloquea el servidor; **A** = alta (resultado incorrecto con estado `ok`, o no hay forma de recuperarse); **M** = media (falla tarde o con un mensaje engañoso); **Bj** = baja. Todo lo marcado como reproducido se ejecutó; lo demás sale de leer el código.

### 9.1 Seguridad

- **B**: ejecución de código **a partir de un CSV**, sin JSON:
  - comillas en los nombres de columna dentro de la plantilla de `drop_duplicates`;
  - un salto de línea en el nombre de una exógena categórica, dentro de un comentario del script.

  Detalle en 4.1; ambos reproducidos.
- **A**: ejecución de código con un override legítimo, el id de modelo de Foundation (4.1). Es la prueba de que "solo overrides" no basta.
- **A**: ejecución de código desde un perfil en JSON (`frequency`) y desde el nombre del forecaster o cualquier clave de `forecaster_kwargs` de un plan en JSON (4.1). Hoy afecta a `--from-plan` y `--from-profile` del CLI.
- **M**: el script se ejecuta en el propio proceso con todos los builtins. No es un sandbox, y un subproceso tampoco lo sería (mismo usuario, mismos ficheros). Hay que documentar la frontera de confianza.
- **M**: las URL se descargan en el servidor (SSRF, sin timeout ni límite de tamaño), y una ruta local puede ser cualquier fichero legible. Cuando falla la validación, el error devuelve la primera línea del fichero.

### 9.2 Resultados incorrectos con estado `ok`

- **A: datos que no coinciden con el perfil guardado.** `_resolve_inputs_with_profile` ([_utils.py:680](../skforecast_ai/_utils.py#L680)) solo comprueba los nombres de columna.
  - Datos diarios con un perfil mensual se remuestrean en silencio con `asfreq('MS')`, perdiendo el 97 % de las filas.
  - Una exógena nueva no se usa.
  - `end_train`, `cv_config` y la explicación describen los datos antiguos: "6 folds" cuando se ejecutaron 2.
  - Con un perfil antiguo se saltan las comprobaciones tempranas de la sección 2.
- **A: el script devuelto no es el que se ejecutó**, lo que rompe el principio 2.
  - `forecast()`, `backtest()` y `compare()` con una ruta generan `read_csv('data.csv')`, porque perfilan el DataFrame ya cargado.
  - Con un perfil guardado, el script lee `profile.data_path` y no los datos pasados.
  - En memoria las fechas se leen con `format='mixed'`, pero el script usa `pd.to_datetime` sin formato: un CSV con fechas mezcladas funciona en `forecast()` y falla como script.
  - Un CSV sin fecha genera `index_col=0`, que convierte la primera columna de datos en índice.
  - Los tests de determinismo solo usan DataFrames, y por eso nada de esto se detectó.
- **A: fechas en orden descendente o desordenadas.** `infer_frequency` corre sobre filas sin ordenar: sale una frecuencia `'-1MS'`, un span de 0, `start_date` igual a la última fecha y lags `[1]`, sin ningún aviso. Con filas barajadas cambian los lags. Los scripts sí ordenan, así que el problema está solo en el perfil.
- **A: formato largo con varias frecuencias.** La frecuencia y los huecos se infieren solo con la primera serie. Una serie diaria junto a una semanal se submuestrea, y los huecos de las demás series no se cuentan.
- **A: series que terminan antes que las demás, o con NaN al final.** `forecast()` devuelve N-1 series sin avisar y el promedio del backtest las excluye. Con un NaN en la última ventana, las predicciones salen NaN con estado `ok`.
- **A: exógenas futuras.** Solo se comprueba el número de filas.
  - Un NaN, una categoría nueva, un mes que falta o datos diarios para un modelo mensual dan predicciones NaN o incorrectas con estado `ok`.
  - En formato largo, a una serie sin exógenas futuras se le ponen NaN.
- **A: un `CVResult` pasado a `backtest()` sin plan ignora su plan** y ejecuta un plan por defecto nuevo (otro estimador, otros lags, sin intervalo).
- **M: `end_train` es estado oculto.** Reutilizar el plan de un forecast en modo evaluación vuelve a evaluar fechas antiguas aunque se pida el futuro.
- **M:** los backtests multiserie usan intervalos `conformal` (el valor por defecto de skforecast), mientras que el plan y `forecast()` dicen `bootstrapping`.
- **M: ForecasterStats con frecuencias ancladas** (`QS-OCT`, `QE-DEC`, `W-WED`): ARIMA sin periodo estacional (`m=1`), mientras que los lags y el baseline sí lo usan.
- **M: `ForecasterDirectMultiVariate`** predice solo la primera serie de `target` sin decirlo; en formato largo falla siempre.
- **M:** un CSV con una sola celda de fecha vacía, o con cambios de huso horario (horario de verano), no se reconoce como fechas. La columna pasa a ser una exógena con una categoría por fila.
- **M:** `initial_train_size='2000'` y `test_size='2000'` se leen como fechas. Un agente que envíe números como cadenas obtiene otra partición sin aviso.
- **Bj:**
  - MAPE en series que cruzan el cero;
  - target booleano tratado como regresión;
  - `fixed_train_size` con `refit=False` se ignora;
  - fechas enteras `yyyymmdd` no reconocidas;
  - `skip_folds` fuera de rango aceptado;
  - lags de reserva (PACF vacío) presentados como si los hubiera elegido el PACF.

### 9.3 Errores

- **A: no hay modelo de errores.**
  - Hay unos 90 `ValueError` y `TypeError` sin clase base, sin código y sin campo.
  - El mismo tipo de fallo lanza clases distintas: `test_size=True` da `TypeError`, pero `lags='12'` da `ValueError`.
- **A: `plan(steps=0)` deja escapar un `ValidationError` de pydantic** después de derivar todo. En fastmcp eso llega como error de protocolo, sin mensaje. `steps=True` produce un plan de 1 paso, y `steps='12'` con Direct un `TypeError`.
- **A: salen excepciones de terceros sin envolver**:
  - un `series_id_column` que no existe da `KeyError: 'sid'`;
  - un CSV vacío o binario da `EmptyDataError` o `UnicodeDecodeError`;
  - un target no numérico, "could not convert string to float";
  - `target=[]`, "min() arg is an empty sequence";
  - parámetros de CV inválidos, errores de skforecast;
  - `cv` o `data` de un tipo incorrecto, `AttributeError`.
- **M: fallos tardíos** que se pueden detectar antes:
  - un forecaster multiserie sobre una sola serie devuelve un script roto y falla dentro de `exec`;
  - los valores de `estimator_kwargs` y los nombres de los kwargs de ARIMA no se comprueban;
  - si falta el backend de Foundation, se detecta dentro de `exec`;
  - `compare()` solo ve los candidatos inválidos cuando llega a ellos, y puede devolver `ok` con el baseline como único superviviente;
  - particiones demasiado cortas para la ventana o para Direct.
- **M: `ForecastExecutionError`** no dice qué sentencia falló, y su traceback lleva rutas del servidor. Además, `compile()` está fuera del `try`.
- **M: el CLI con `--format json`** escribe los errores en stdout con markup de rich, que se come el texto entre corchetes: `[lower, upper]` desaparece. Siempre sale con código 1, y algunos consejos son falsos (`--output-code` solo se escribe si todo va bien).
- **M: los mensajes de error no tienen límite de tamaño.** Un target mal escrito en 2.000 columnas produce 69 KB de mensaje.

### 9.4 Proceso de larga duración y concurrencia

- **B: segfault con llamadas concurrentes** por el `redirect_stdout` global de `exec_rendered`. Reproducido con un servidor stdio real de mcp 2.2 y 8 backtests concurrentes: 3 de 3 ejecuciones terminaron en "Fatal Python error: Segmentation fault". También queda `sys.stdout` apuntando a un `StringIO`, y se cuela salida del script en el fd 1.
- **A: los filtros de warnings se quedan cambiados para siempre** cuando se solapan los `catch_warnings`: los de skforecast (`manage_warnings`) y el `simplefilter('ignore')` global de `_utils.py:850-851`. Después de eso se pierden `LongTrainingWarning`, `CandidateFailedWarning` y compañía.
- **M: el SDK de MCP tiene trampas.**
  - Devolver un resultado del paquete no genera `outputSchema` y se serializa con sangría: +49 %.
  - Devolver `model_dump()` en modo Python recorta los DataFrames a su `repr`, con "...", sin ningún error.
  - Un modelo tipado se envía dos veces: como texto y como `structuredContent`.
- **M:** `cv_config` puede llevar enteros de numpy (con un `TimeSeriesFold` hecho a mano), y entonces `model_dump_json` falla después de todo el trabajo.
- **M:** `n_jobs='auto'` en los backtests arranca 3 procesos loky con HistGradientBoosting o RandomForest (5 a 25 s la primera vez, ~170 MB cada uno). Con llamadas concurrentes se sobrecargan las CPU.
- **M:** CatBoost escribe `catboost_info/` en el directorio de trabajo del servidor, normalmente el repo del usuario.
- **M:** cancelar no detiene el hilo. Una descarga de URL colgada bloquea el lock para todas las sesiones.
- **Bj:**
  - los resultados comparten objetos con el perfil y el plan guardados, y los modelos no son inmutables;
  - las excepciones retienen el namespace del script (una copia de los datos y el modelo);
  - Stats escribe la caché de numba en `site-packages`;
  - el primer ajuste de ARIMA importa statsmodels, numba y llvmlite.

### 9.5 Entradas y estado

- **M: no hay opciones de lectura** (`sep`, `decimal`, `encoding`, `dayfirst`). Un CSV europeo llega como una sola columna, y el único error es "target not found".
- **M:** no hay identificadores, versión de esquema ni huella en ningún objeto. El bundle de `--from-plan` solo contiene el perfil y el plan, con una ruta relativa.
- **Bj:** el comando `mcp` y la carga de exógenas por ruta tienen que reutilizar el cargador de exógenas del CLI (`cli.py:550-591`), que usa un tercer parser de fechas distinto.

## 10. Decisiones propuestas, pendientes de revisión

Nada de esta sección está implementado: es una propuesta para revisar. Los números de PR remiten a la tabla de 10.8.

**Criterio de "la opción más conservadora"**, aplicado en este orden:
1. Cerrar en caso de duda todo lo que toca la seguridad.
2. Nada silencioso (principio 3 de `AGENTS.md`).
3. El menor cambio posible en el comportamiento público, en los scripts generados y en sus goldens byte a byte.
4. Compatibilidad hacia atrás en Python: los `pytest.raises(ValueError)` y `pytest.warns` existentes siguen pasando.
5. Reutilizar lo que ya existe.
6. Ninguna dependencia nueva que no haga falta.
7. Evitar cambios en `llm/context.py`, `llm/prompts.py` y las explicaciones, porque obligan al check de pago.
8. No reabrir la sección 6.

Cuando dos opciones empatan, gana la que cambia menos resultados.

Los prototipos citados (render, validadores, avisos, errores y `describe()`) se probaron con la suite completa sobre copias del repo y la dejaron en verde, salvo lo que se indica.

### 10.1 Seguridad (4.1): dos capas

**Propuesta.**
- **La capa de render es la frontera** (PR 1). Ningún valor de un plan, un perfil o un CV entra en el script salvo de estas formas:
  - con `repr()`;
  - como constante de un mapa cerrado: import del forecaster, constructor del transformer, plantillas de preprocesado;
  - como `str()` de un int, bool o `Literal` ya validado;
  - dentro de un comentario a través de `_comment_text()`, que escapa los caracteres de las categorías Unicode Cc, Zl y Zp (saltos de línea, NUL y otros de control).

  En concreto:
  - `_emit_preprocessing_steps` solo acepta pares `(action, code_snippet)` de un conjunto cerrado (`BLOCKING_PREPROCESSING_TEMPLATES`). La plantilla larga pasa a `subset=[{series_id_column}, {date_column}]`, con los valores rellenados con `repr()`.
  - `asfreq({frequency!r})` en los tres sitios.
  - `repr` en las features de calendario, los lags, `categorical_features`, `encoding`, `differentiation`, `dropna_from_series`, `offset` y `n_offsets`.
  - Mapas cerrados `_FORECASTER_IMPORTS` y `_TRANSFORMER_CONSTRUCTORS`.
  - `_comment_text` en `statistical.py:51`, `foundation.py:78-79` y `:104`.
  - **Añadido tras la revisión crítica**:
    - comprobación en el render de que cada clave de `estimator_kwargs` es un identificador;
    - `interval_method` a través de un mapa cerrado;
    - `int(plan.steps)`;
    - `repr()` de un `initial_train_size` que no sea entero.
  - Con nombres normales, los scripts no cambian ni un byte. En el prototipo, la suite completa pasó salvo los 2 tests que fijan la plantilla larga, que no se ha publicado.
- **Los validadores son la compuerta que cierra** (PR 2 y PR 3):
  - `validate_forecaster`: lista blanca y coherencia con `task_type`;
  - `validate_forecaster_kwargs`: claves cerradas por familia y valores cerrados o tipados;
  - `validate_preprocessing_step`;
  - `validate_frequency`: regex `[A-Za-z0-9-]+`. Se descarta `to_offset` porque acepta `'D\n'` y emite `FutureWarning` con alias antiguos;
  - sintaxis `owner/name` del id de Foundation, comprobada en `resolve_foundation_model`, que es el punto por el que pasan todos los caminos;
  - `_validate_lags` y `_validate_window_features` se mueven a `_validation.py`, reexportados desde `_utils.py`;
  - **añadido tras la revisión crítica**:
    - revalidar el plan recibido (`ForecastPlan.model_validate(plan.model_dump())`) en `_prepare_forecast`, `_prepare_backtest`, `forecast_code` y `backtest_code` antes de renderizar, porque `model_copy` salta el validador;
    - `steps` enteros aunque lleguen como float (`12.0` pasa a `12`); solo se rechazan `bool`, valores no enteros y valores menores que 1. `plan(steps=12.0, forecaster='ForecasterDirect')` funciona hoy y seguirá funcionando.
- **Nombres de columna**:
  - no se rechazan comillas ni barras invertidas: se citan en el render;
  - los saltos de línea tampoco se rechazan en el núcleo: una cabecera de Excel con Alt+Intro (`'Temperature\n(C)'`) funciona hoy como exógena numérica;
  - se rechazan **en la frontera del MCP**, en el tool `profile`, que es donde el texto de `describe()` llega a un agente;
  - `_comment_text` protege el script en todos los casos.
- **El `exec` sigue en el proceso**, con un lock de proceso en el servidor. Ni los builtins restringidos ni un subproceso son un sandbox; un ejecutor en subproceso queda para más adelante, para timeouts y aislamiento de caídas, y hay que documentarlo como tal.
- **CLI**: `--from-plan` y `--from-profile` se mantienen, ahora validados al cargar. Un bundle manipulado sale con código 1 y "Invalid input data", y no se ejecuta.
- **`compile()` dentro del `try`**, y `ForecastExecutionError` indica `failed_line` y `failed_statement` (PR 4).
- **MCP**: nunca acepta planes, perfiles, CVs ni resultados en JSON; solo ids y argumentos tipados estrictos. Es una defensa adicional, no la única.

**Por qué es la más conservadora.** Cierra en las dos capas, porque ninguna basta sola:
- los validadores no alcanzan los nombres que vienen de los datos sin romper CSVs válidos;
- el render solo deja pasar basura semántica: con `repr`, `dropna_from_series='False or ...'` se convertía en una cadena "verdadera" y el forecast terminaba bien.

Además rechaza en lugar de sanear en silencio, mantiene el campo `code_snippet` (los bundles de la 0.3.1 cargan sin cambios), no añade dependencias y no toca `llm/context.py`.

**Descartado:**
- regenerar el snippet desde `action`: silencioso;
- eliminar `code_snippet`: rompe la API;
- rechazar comillas: rompe datos válidos;
- pasar siempre `--from-plan` por `refine_plan()`: sanea en silencio y pierde `end_train`;
- quitar `--from-plan`: rompe el flujo documentado.

### 10.2 Avisos en el resultado (4.2)

**Propuesta.**
- **PR 16.** `plan()` rellena `ForecastPlan.warnings` con el texto exacto de los tres avisos que emite, y el aviso de Python se mantiene. Invariante: `plan.warnings` es igual a los avisos emitidos por la llamada. `validate_estimator_kwargs` devuelve la lista de mensajes. El display muestra un panel "Plan Warnings". Las variables de calendario omitidas siguen siendo una frase (decisión 6). El validador no toca la lista.
- **PR 20.** El CLI manda todos los avisos a stderr con un envoltorio de `showwarning`, instalado en el callback `main()` y que conserva el formato de skforecast. Esto arregla `--format json`. Se descarta `set_warnings_style('default')` porque cambia el aspecto para todos.
- **PR 22.** `exec_rendered` registra los avisos del script y los reemite con `warn_explicit` al restaurar stdout, sin `simplefilter`: mandan los filtros de quien llama, así que `error` sigue fallando.
- **En el servidor (PR 18).** Captura por llamada dentro del lock, con `catch_warnings(record=True)` y `simplefilter('always')`:
  - sobre `ToolNotice {source: data | plan | runtime, category, message, count}`;
  - deduplica por (categoría, texto) y quita el sufijo "You can suppress..." de skforecast;
  - fuera quedan `CandidateFailedWarning`, porque ya lo cubre `failures`, y los `DeprecationWarning`, que van al log;
  - límites de 20 entradas y 1.000 caracteres, con un recuento de omitidos.
- **PR 35.** Líneas "- Plan warning:" en el contexto compartido por `ask()` y `describe()`, dentro del lote de pago.
- No hay campos nuevos en los resultados: los hechos de `LongTrainingWarning` están en `cv_config`, y las exclusiones de `compare()` en la explicación.

**Por qué.** No cambia tipos públicos, ni scripts, ni el esquema JSON del CLI, ni `llm/context.py` hasta el PR 35. El prototipo de los PRs 15, 20 y 22 pasó la suite completa (1.720 tests) cambiando una sola aserción. Capturar en cada método público del núcleo se descarta porque altera el estado global en cada llamada y rompe `filterwarnings = error`.

### 10.3 Modelo de errores

**Propuesta (PR 5).**
- **Jerarquía mínima:**
  - `SkforecastAIError(Exception)` con `code`, `field` y `hint`; `hint` no forma parte de `str(exc)`;
  - `InvalidInputError(SkforecastAIError, ValueError)`;
  - `InvalidInputTypeError(InvalidInputError, TypeError)`, donde antes había `TypeError`;
  - `DataNotFoundError(SkforecastAIError, FileNotFoundError)`;
  - las cuatro excepciones existentes pasan a heredar de la base.
- Unos 95 sitios cambian de clase con **el mismo mensaje**. El prototipo pasó la suite completa sin tocar un test.
- **10 códigos cerrados en el núcleo:** `invalid_argument`, `insufficient_data`, `data_not_found`, `data_unreadable`, `missing_dependency`, `execution_failed`, `all_candidates_failed`, `llm_required`, `llm_call_failed` e `internal_error`. Los del servidor viven en el servidor.
- **`ErrorInfo.from_exception()`**, un modelo pydantic compartido por el CLI y el MCP:
  - desenvuelve el `ValidationError` a través de `ctx['error']` para recuperar el campo;
  - reescribe el mensaje de `AllCandidatesFailedError` sin `exc.failures`;
  - nunca incluye tracebacks ni código;
  - `internal_error` lleva el tipo y la primera línea, con un máximo de 200 caracteres.
- Los remedios que un agente con rutas no puede aplicar (pandas, `dayfirst`) van en `hint`, no en el mensaje.
- **Comprobaciones tempranas (PR 23):**
  - `series_id_column` debe existir y ser distinta del target y de la fecha;
  - el target no puede ser una lista vacía, debe tener observaciones y debe ser numérico (comprobado en `profile()`);
  - `estimator_kwargs` debe ser un dict;
  - se comprueban los nombres de los kwargs de ARIMA;
  - el backend de Foundation se comprueba antes del `exec`;
  - `read_csv` se envuelve como `data_unreadable`;
  - también se envuelven la fecha de `test_size` y los errores de `TimeSeriesFold`;
  - `fixed_train_size` con `refit=False` es un error;
  - `skip_folds` fuera de rango es un error;
  - `compare()` con un intervalo asimétrico omite el baseline automático con una nota, en lugar de dejar que falle.
- **Contrato del CLI (PR 21), fuera del camino del MCP:**
  - errores en stderr, con el markup escapado;
  - con `--format json`, un objeto `{"error": {...}}` en stderr;
  - `--format` pasa a `click.Choice`;
  - los códigos de salida no cambian;
  - `--steps` con `--from-plan` distinto de `plan.steps` lanza error, como en Python.

**Por qué.** Da a los agentes un código y un campo estables sin cambiar `str(exc)` ni la clase que captura el código existente (todas siguen siendo `ValueError`, `TypeError` o `FileNotFoundError`). Se descartan tres alternativas:
- mapear por regex en el servidor: frágil;
- una clase por código: mucha API para la misma información;
- reescribir los mensajes: rompe tests y cambia lo que ven los usuarios de Python.

### 10.4 Overrides y coherencia entre objetos (4.3)

**Propuesta.**
- **Seis overrides nuevos, keyword-only**, en `plan()`, `refine_plan()`, `forecast*()` y `backtest*()`:
  - `use_exog: bool | None`;
  - `calendar_features: list[CalendarFeatureName] | None`, donde `[]` significa ninguna;
  - `differentiation: int >= 1 | None`;
  - `target_transformer: 'StandardScaler' | 'none' | None`, una sola clave que se traduce a `transformer_y` o `transformer_series` según la familia;
  - `dropna_from_series: bool | None`;
  - `metric: str | list[str] | None`, con la semántica de `compare()`.

  `None` es siempre la regla determinista; para desactivar hay que pasarlo explícitamente (`False`, `[]` o `'none'`). `backtest*()` gana además `lags` y `window_features`.
- **`CandidateConfig`** gana todas menos `metric`: la métrica, el intervalo y `steps` son de la comparación, no del candidato.
- **Procedencia (PR 30).** Un nuevo campo `ForecastPlan.overridden_fields` registra qué decidió el usuario.
  - `refine_plan()` vuelve a pasar esos valores por `plan()`, así que se revalidan y `refine_plan()` sigue saneando.
  - Las ediciones a mano que descarta se avisan con `PlanEditsDiscardedWarning`, que también queda en `plan.warnings`. No lanza error: los bundles de la 0.3 siguen funcionando.
  - En la comparación se ignoran `end_train`, `explanation`, `warnings` y las demás marcas.
- **`differentiation` y el CV:**
  - `backtest()` lanza error antes de ejecutar si el CV y el plan no coinciden;
  - `compare()` da a cada candidato una copia del CV con su valor, y **lo dice en la explicación** (añadido tras la revisión crítica, por la sección 6);
  - el presupuesto de ventana y el tamaño mínimo de entrenamiento suman la diferenciación.
- **Coherencia (PR 26):**
  - `_check_plan_matches_profile` comprueba la frecuencia, el tipo de tarea, que las exógenas sean viables y que haya índice de fechas si hay calendario;
  - un `CVResult` sin plan ni argumentos de modelo usa `cv.plan`: arregla SIL-5 sin romper nada. Con argumentos explícitos se construye el plan con ellos y solo se comprueba que el CV sea compatible (cambio tras la revisión crítica: la síntesis lanzaba error, y eso rompía llamadas que hoy funcionan);
  - un `CVResult` de otro perfil lanza error;
  - `forecast()` sin `test_size` con un plan que trae `end_train` lanza error, en lugar de volver a evaluar sin avisar.
- **Otras piezas:**
  - `ForecasterDirectMultiVariate` nombra en la explicación la serie que predice y se rechaza en formato largo;
  - el script multivariante deja de ajustar como series las exógenas no usadas;
  - las variables de calendario explícitas que chocan con exógenas lanzan error (la regla de la sección 6 sigue igual para las automáticas);
  - SIL-8 (ForecasterStats con exógenas solo categóricas) se deja para el autor, porque rompe a quien pasa exógenas;
  - el subconjunto de columnas exógenas llega después, como `profile(exog_columns=...)`;
  - `docs/user-guides/cli-usage.md:108` y `:122` se corrigen ya (PR 0).

**Por qué.**
- Un solo sitio para cada valor: `overridden_fields` solo guarda nombres, así que no hay una segunda fuente de verdad que pueda desincronizarse ni un canal sin validar hacia el script.
- Todo es opcional, así que los planes por defecto no cambian.
- Las frases nuevas de la explicación solo aparecen cuando se usa el override. Aun así, cuentan para el check de pago, que se agrupa en un solo lote.
- Se descarta guardar los valores en un dict (dos fuentes de verdad), heredar por valor (congela valores de la regla) y lanzar error con las ediciones (rompe la compatibilidad).

### 10.5 `describe()` (4.4)

**Propuesta (PR 12 y PR 14).**
- `ExplainableResult.describe() -> str`, sin parámetros. Equivale a `_build_llm_context(send_data=False, for_describe=True).text`.
  - La palabra clave privada `for_describe` recorre las 5 implementaciones y los renderers igual que `send_data`. Con `False`, la salida no cambia ni un byte.
  - Las 4 frases dirigidas al LLM de `ask()` pasan a ser constantes, y se omiten en `describe()`.
  - Un plan se describe con `forecast_code(profile=, plan=).describe()`.
  - Nunca incluye valores fila a fila.
- `to_llm_context()` sigue como interfaz de `ask()` y sin documentar.
- **Añadido:**
  - la ruta `send_data=False` deja de resumir la columna `fold` y da un bloque por serie, como `_serialize_dataframe`;
  - el contexto de `backtest_code()` deja de describirse como predicción. Es obligatorio antes de publicar `describe()`, o como mínimo hay que avisar en la docstring.
- **Límites solo en `describe()` (PR 14)**:
  - las 5 primeras series más las filas agregadas en las métricas;
  - 15 elementos por lista, con "(first N of M)" y recuentos;
  - con 500 series ronda los 5,4k caracteres.
  - `ask()` no cambia; aplicarle los mismos límites es el PR 36, opcional y de pago.
- **Goldens nuevos** en `tests/tests_llm/golden_describe/`, más un test de que `describe()` coincide con `to_llm_context(send_data=False)` sin esas frases.
- **El coste va en el sobre del MCP**, calculado con `count_estimator_fits`; ni `cv_config` ni la tabla de `compare()` cambian.
- Los ids, los ficheros, los avisos y lo que se puede cambiar van en el sobre del tool, no en `describe()`.

**Por qué.** Hay un solo pipeline de texto, así que las dos salidas no pueden separarse. El prototipo mantuvo los 15 goldens del LLM idénticos y pasó los 315 tests de `tests/tests_llm`.

### 10.6 Datos correctos por ruta CSV, y el coste de ForecasterStats

**Propuesta.**
- **PR 6.** El perfil ordena las filas por fecha antes de inferir, con una nota en `DataProfile.warnings`. `compute_series_pacf` deduplica y ordena. Los scripts ya ordenan, así que no cambian.
- **PR 7.** Formato de fechas en CSV:
  - **cierran** las celdas de fecha vacías y los husos horarios mezclados, que hoy son silenciosos;
  - los formatos mezclados (hoy `forecast()` funciona y el script falla) y el formato largo sin fecha (hoy falla dentro del `exec`) se separan en un PR aparte, que no bloquea;
  - para los formatos mezclados decide el autor, porque rechazarlos rompe llamadas que hoy funcionan.
- **PR 8.** En formato largo, la frecuencia se infiere por serie y lanza error si difieren o si hay timestamps fuera de la rejilla. Los huecos se suman sobre todas las series, y una nota avisa de las series que terminan antes.
- **PR 9: ForecasterStats cuenta y enseña lo que se ejecuta.**
  - Con un plan estadístico, el script del backtest escribe `refit=True` y `fixed_train_size=True`, que es lo que ya ejecuta skforecast hoy. `cv_config` y la explicación lo dicen, y `n_fits` pasa a ser igual a `n_folds`.
  - `count_estimator_fits` cuenta un ajuste por fold, y el aviso y el presupuesto de `compare()` usan esa cifra: `compare()` puede dejar fuera ForecasterStats como alternativa automática.
  - Las métricas no cambian. No se reabre la sección 6: el valor por defecto de `create_cv` sigue siendo `refit=False`.
  - Pasar ForecasterStats a ventana creciente cambiaría las métricas: es una pregunta abierta.
- **PR 10: exógenas futuras.** Se comprueban las columnas, las fechas esperadas (inicio, frecuencia, sin huecos ni filas fuera de la rejilla), los tipos, las categorías nuevas y, en formato largo, que estén todas las series.
  - Los NaN lanzan error si el estimador no los tolera, o si esa columna no tenía NaN en el entrenamiento. Con LightGBM y similares se mantiene el comportamiento actual con aviso (cambio tras la revisión crítica).
  - La fecha final se calcula con los datos pasados.
  - El cargador del CLI se mueve a `_utils` y usa el mismo parser de fechas que los datos.
- **PR 11: última ventana del target.**
  - Filas finales sin target siempre dan error.
  - Los NaN dentro de la ventana que leen los lags siguen la misma regla que las exógenas.
  - Se comprueba antes que las exógenas futuras.
- **PR 13.** Los backtests multiserie escriben `interval_method` a partir del plan, así que dejan de usar `conformal` cuando el plan dice `bootstrapping`. Solo añade goldens nuevos. Es bloqueante tras la revisión crítica, porque hoy es un desajuste silencioso alcanzable por MCP.
- **PR 17: el script es el que se ejecutó, también con rutas.**
  - Se sella en el perfil la ruta ya conocida con `model_copy`, sin leer el CSV dos veces.
  - Con un perfil guardado se escribe la ruta de los datos realmente usados, o se rechaza una ruta distinta.
  - `index_col=0` solo cuando corresponde.
  - La sustitución de `show_progress` se ancla a su línea.
  - Los tests de determinismo pasan a usar también CSV.
- **Después:**
  - PR 24: planes que no pueden ejecutarse (forecaster multiserie sobre una serie, choques de nombres con lags o window features, longitud mínima, baseline sin frecuencia);
  - PR 25: la partición de evaluación, y NaN en la historia que lee un fold;
  - PR 27: datos frente a perfil guardado. Se vuelve a perfilar: error si la estructura difiere, y una nota si solo cambian los valores, para mantener el flujo documentado de volver a ejecutar un plan con datos nuevos;
  - PR 28: estacionalidad de ARIMA con frecuencias ancladas;
  - PR 29: el alias `result` de `ask()` pasa a eliminarse en la 0.5.0.

**Por qué.** Cada caso silencioso pasa a ser un error temprano, o una nota que viaja en `result.profile`. Solo cambian scripts en los PRs 9, 13, 17 y 28, siempre acotados. Ordenar las fechas no cambia ninguna decisión de modelado: solo alinea el perfil con lo que el script ya hacía.

### 10.7 El servidor MCP (4.5)

**Propuesta (PR 18 y PR 19).**
- **Librería y paquete:**
  - el SDK oficial, `mcp>=2.2,<3`, con `MCPServer`, en un extra `[mcp]` que también entra en `test`;
  - comando `skforecast-ai mcp --allow-dir DIR [--output-dir DIR] [--max-objects 256] [--max-memory-mb 1024]`, solo stdio, con import perezoso: `import skforecast_ai` no carga `mcp`;
  - todo vive en el subpaquete `skforecast_ai/mcp/` (`server`, `_store`, `_inputs`, `_errors`, `_runtime` y `models`).
- **Tools**, con los mismos nombres que los métodos:
  - `profile(data_path, target, date_column, series_id_column)`;
  - `plan(profile_id, steps, ...)`: parámetros planos, porque ahí `None` es la regla;
  - `refine_plan(plan_id, overrides)`: `overrides` es una subclase de `RefinePlanOverrides` con `extra='forbid'` y `strict=True`, que conserva la diferencia entre "omitido" y `null`;
  - `create_cv(plan_id, ...)`, que devuelve el coste;
  - `backtest(cv_id, plan_id=None)`, que por defecto usa el plan del CV;
  - `compare(cv_id, candidates, interval, baseline)`: los candidatos inválidos quedan como fallos, igual que en Python, y **sin `metric` en la v1** hasta que llegue el override de métrica (PR 31), para que el resumen no se contradiga;
  - `forecast(plan_id, test_size, exog_path)`;
  - `get_code`, `get_failure`, `list_objects` y `describe_object`.
- **Qué devuelven:**
  - un sobre `ToolResult {id, kind, links, summary, summary_truncated, notices, notices_omitted, files, values_included=False}`, donde `summary` es `describe()`, con un máximo de 20.000 caracteres y el texto completo en un fichero si se corta;
  - las predicciones, las métricas y el leaderboard van a CSV en el directorio de salida;
  - `metrics_summary` de un forecast multiserie no se calcula con `aggregate_metrics`, porque devolvería la primera serie.
- **Estado por id:**
  - entradas inmutables con referencias directas a sus antecesores;
  - ids `kind-seq-token`, con un token por proceso;
  - LRU por número de objetos y por bytes, con errores explícitos al pedir un id eliminado;
  - sha256 del CSV antes y después de cada llamada que lee datos: si cambia, `data_changed` y no se registra nada;
  - el plan de un resultado en modo evaluación nunca se registra como plan.
- **Entradas:**
  - solo rutas absolutas `.csv` dentro de `--allow-dir`, comprobadas antes de mirar si existen y otra vez tras resolver los enlaces simbólicos;
  - ninguna URL;
  - la exógena por ruta, con la misma política;
  - se rechazan las cadenas numéricas en `test_size` e `initial_train_size`, porque el núcleo las leería como fechas;
  - el tool `profile` rechaza nombres con saltos de línea (10.1).
- **Errores:**
  - `ToolError` con un JSON `{code, message, field, hint, details}`, que es la vía documentada del SDK;
  - los campos se renombran a `profile_id`, `plan_id`, `cv_id`, `data_path` y `exog_path`;
  - códigos propios del servidor: `unknown_id`, `inconsistent_ids`, `invalid_path`, `path_not_allowed`, `url_not_allowed` y `data_changed`;
  - los mensajes tienen un límite de tamaño;
  - los fallos se guardan como texto y se consultan con `get_failure`, nunca en la respuesta.
- **Concurrencia:**
  - tools `async` con un único `anyio.Lock`, ejecutando el núcleo en un hilo (`to_thread.run_sync`);
  - dentro del lock se capturan los avisos;
  - la cancelación es cooperativa entre candidatos, mediante `compare(progress_callback=...)` (PR 15), que también envía el progreso.
  - No hay timeout duro. El peor caso documentado es un candidato Auto-ARIMA de 30 a 50 s en h2o sin ningún evento.
- **Seguridad:**
  - el `exec` corre en el mismo proceso, con los privilegios del usuario: la frontera de confianza queda documentada;
  - `os.chdir(output_dir)` antes de servir, para que CatBoost no escriba `catboost_info/` en el repo del usuario;
  - la descarga de pesos de Hugging Face queda documentada (`HF_HUB_OFFLINE`).
- **Skill (PR 19b):** un SKILL.md con el flujo, la escala de confianza, el coste, las fechas ISO 8601, los códigos de error y la privacidad. No se publica un skill sobre el CLI, porque enseñaría el ida y vuelta de `--from-plan`.
- **Tests:** `Client` en memoria, sin red. Incluyen deriva de esquemas, rutas, store, errores, cada tool, ausencia de mutaciones, regresiones de seguridad (nunca se crea el marcador), concurrencia (sin solapes, avisos aislados, `sys.stdout` restaurado) y una integración stdio marcada como lenta.

**Por qué.** `mcp` ya llega instalado a través de `[llm]` y se verificó aquí. En cambio, `fastmcp` como servidor necesita paquetes que no están, y convierte un `ValidationError` interno en un error de protocolo sin mensaje. El servidor es una capa fina: los únicos cambios en el núcleo son el `progress_callback` y el cargador de exógenas.

### 10.8 Orden de PRs

Leyenda: **Blq** = bloquea el servidor; **Scr** = cambia scripts generados (goldens de render); **Pago** = toca `llm/context.py`, `llm/prompts.py` o una explicación, y por tanto entra en la ejecución real de `check_ask_context.py`.

| # | PR | Tam. | Blq | Scr | Pago | Depende de |
|---|---|---|---|---|---|---|
| 0 | docs: corregir `cli-usage.md:108` y `:122` (directo sobre `0.4.x`) | S | | | | |
| 1 | fix(rendering): frontera de render (10.1) | M | Sí | Solo nombres raros | | |
| 2 | fix(validation): frecuencia y sintaxis del id de Foundation | S | Sí | | | 1 |
| 3 | feat(validation): validación cerrada de `ForecastPlan` y revalidación del plan recibido | M | Sí | | | 1 |
| 4 | fix(execution): `compile()` dentro del `try` y sentencia que falla | S | | | | |
| 5 | feat(exceptions): jerarquía, códigos y `ErrorInfo` | M | | | | 2, 3 |
| 6 | fix(profiling): filas en orden de fecha y entrada del PACF | S | Sí | | | |
| 7 | fix(profiling): fechas CSV vacías y husos mezclados (formatos mezclados y largo sin fecha, aparte) | M | Sí | | | 6 |
| 8 | fix(profiling): frecuencia por serie en largo y series que acaban antes | M | Sí | | | 6 |
| 9 | fix(cv): ForecasterStats enseña y cuenta el CV que se ejecuta | S | Sí | Sí (backtest Stats) | Sí | |
| 10 | fix(forecast): validar las exógenas futuras y compartir el cargador | M | Sí | | | |
| 11 | fix(forecast): última ventana del target | M | Sí | | | 8 |
| 12 | feat: `describe()` sin instrucciones del LLM de `ask()` | M | Sí | | Según la regla (10.9) | |
| 13 | fix(rendering): `interval_method` en los backtests multiserie | S | Sí | Sí (goldens nuevos) | | |
| 14 | feat: límites de `describe()` | M | Sí | | Según la regla | 12 |
| 15 | feat(compare): `progress_callback` y `CompareProgress` | S | Sí | | | |
| 16 | feat: `ForecastPlan.warnings` y el panel "Plan Warnings" | S | | | | |
| 17 | fix: el script carga el mismo fichero que la ejecución (rutas) | M | | Sí (rutas) | | 1 |
| 18 | feat(mcp): base del servidor y tools de planificación | L | Servidor | | | 1-3, 6-9, 12, 14 |
| 19 | feat(mcp): tools de ejecución, ficheros, progreso y cancelación; 19b: skill y guía | L | Servidor | | | 18, 10, 11, 13, 15 |
| 20 | fix(cli): avisos a stderr | S | | | | |
| 21 | fix(cli): contrato de errores y `--steps` con `--from-plan` | M | | | | 5, 20 |
| 22 | fix(execution): reemitir los avisos del script | S | | | | 4 |
| 23 | feat: comprobaciones tempranas de entradas (10.3) | M | | | | 5 |
| 24 | fix(plan): rechazar planes que no pueden ejecutarse | M | | | | 8, 11 |
| 25 | fix(forecast): comprobaciones de la partición de evaluación | S | | | | 8, 24 |
| 26 | fix: `CVResult`, plan contra perfil y `end_train` | M | | | | 24 |
| 27 | fix: datos frente a perfil guardado (SIL-1) | M | | | | 6, 8, 26 |
| 28 | fix: estacionalidad con frecuencias ancladas | S | | Sí | | |
| 29 | chore: alias `result` de `ask()` hasta 0.5.0 | S | | | | |
| 30 | feat(plans): `overridden_fields` y aviso de ediciones descartadas | M | | | | 3, 16 |
| 31 | feat: override `metric` | M | | | Sí | 30 |
| 32 | feat: override `use_exog` y arreglos multivariante | M | | Sí | Sí | 30, 24 |
| 33 | feat: override `differentiation` | M | | Sí | Sí | 30, 26, 24 |
| 34 | feat: overrides `calendar_features`, `target_transformer`, `dropna_from_series` | M | | | Sí | 30, 3 |
| 35 | feat: avisos del plan (y campos elegidos) en el contexto | M | | | Sí | 12, 16, 31-34 |
| 36 | (opcional) límites de `describe()` también en `ask()` | S | | | Sí | 14 |
| 37 | feat(cli): paridad del CLI con los nuevos overrides | M | | | | 31-34, 21 |
| 38 | feat: `profile(exog_columns=...)` | M | | | | 32, 27 |

**Mínimo antes del servidor:** 1, 2, 3, 6, 7, 8, 9, 12, 13 y 14 antes del PR 18; además 10, 11 y 15 antes del 19. Muy recomendables antes: 4, 5, 16 y 17.

El PR 5 toca unos 95 sitios de los mismos ficheros que los PRs 6 a 11. O entra rápido justo después de la seguridad, o se deja para después del servidor para evitar conflictos. La síntesis lo ponía en medio.

**Check de pago.** Una sola ejecución antes de la release, cuando hayan entrado todos los PRs marcados. La ejecución pendiente de la sección 3 no debe lanzarse antes. Si el lote 31 a 36 va en otra versión, habrá dos ejecuciones.

**Otras dependencias de orden:**
- el PR 26 compara con el perfil guardado antes de que el PR 27 lo refresque;
- el PR 1 construye sus datos hostiles con `model_construct`;
- los PRs 6 y 8, y los 10 y 11, pueden fusionarse si se prefiere revisar menos PRs.

### 10.9 Cambios sobre la síntesis tras la revisión crítica

La síntesis propuso 40 PRs y un revisor la contrastó con el código. Se aplicaron estas correcciones, todas en la dirección más conservadora:
- **Los saltos de línea** en los nombres se rechazan en la frontera del MCP, no en `DataProfile`: el núcleo habría roto CSVs de Excel que hoy funcionan.
- **Huecos en la frontera de render** para planes sin validar (claves de kwargs, `interval_method`, `steps`), y **revalidación del plan recibido**. La síntesis afirmaba que el render bastaba; el revisor lo refutó creando un fichero marcador.
- **ForecasterStats**: además del número de ajustes, la ventana fija. Se propone escribir el CV que realmente se ejecuta en lugar de solo corregir el recuento.
- **`steps=12.0`** se normaliza en lugar de rechazarse.
- **NaN en exógenas futuras y en la última ventana**: error solo si el estimador no los tolera.
- **`CVResult` con argumentos explícitos**: se comprueba que el CV sea compatible, sin rechazar la llamada.
- **La ruta** se sella con `model_copy`, sin leer el CSV dos veces.
- **El PR de fechas se divide**: solo los casos silenciosos bloquean.
- **CatBoost**: `os.chdir(output_dir)` en el servidor.
- Nota en `compare()` cuando cambia la `differentiation` del CV.
- Los PRs de `interval_method` y de los límites de `describe()` pasan a bloquear.
- `compare` en MCP v1 sin `metric`.
- La corrección de `cli-usage.md` va directa a `0.4.x`.

### 10.10 Preguntas abiertas para el autor

Ordenadas por impacto, con la propuesta entre paréntesis.
1. **Versión:** ¿el servidor y el lote de overrides en 0.4.0, con un único check de pago, o el servidor en 0.4.0 y el lote en 0.5.0? (Propuesta: servidor y bloqueantes en 0.4.0; lote en 0.5.0 si retrasa la release.)
2. **Criterio del check de pago:** ¿aplicar la regla literal de `AGENTS.md` (cualquier cambio en `llm/context.py`) o cambiarla a "un cambio en lo que recibe el LLM"?
   - Con la regla literal, los PRs 12 y 14 entran en la ejecución pendiente.
   - Con la otra redacción, también la necesitan los PRs que añaden avisos o cambian el resumen de fallos para algunos datos: 5, 6, 8 y 27.

   (Propuesta: mantener la regla literal y una sola ejecución.)
3. **ForecasterStats:** ¿mantener la ventana fija que se ejecuta hoy, escrita explícitamente (no cambian las métricas), o pasar a ventana creciente como dice `cv_config`, lo que cambia las métricas? (Propuesta: mantener, y decidir aparte.)
4. **Nombres con saltos de línea:** ¿rechazarlos solo en MCP (propuesto) o también en el núcleo? ¿Rechazar también `<` y `>`?
5. **CSV con formatos de fecha mezclados:** ¿rechazar (rompe `forecast()` que hoy funciona) o escribir `format='mixed'` en el script? ¿Opciones de lectura (`sep`, `decimal`, `encoding`, `dayfirst`) en `profile()`, el CLI y el MCP? (Propuesta: rechazar en la v1 y pedir ISO 8601 en el skill; las opciones de lectura, después.)
6. **NaN en exógenas futuras o en la última ventana con estimadores que los toleran:** ¿aviso (propuesto) o error?
7. **Datos frente a perfil guardado (SIL-1):** ¿refrescar con nota (propuesto) o error ante cualquier diferencia? ¿Una exógena nueva es error (propuesto)?
8. **Series que terminan antes, en modo predicción:** ¿nota (propuesto) o error?
9. **SIL-8:** ¿`use_exog=False` para ForecasterStats con solo exógenas categóricas? (Propuesto: aplazar.)
10. **Variables de calendario explícitas que chocan con exógenas:** ¿error (propuesto) o ampliar la regla de la sección 6?
11. **Frases nuevas en la explicación por cada override:** ¿sí, pagando el check, o solo `overridden_fields` más `describe()`?
12. **Valores por defecto del servidor:**
    - `--allow-dir` obligatorio (propuesto);
    - directorio de salida temporal (propuesto) o dentro del proyecto;
    - límites de 256 objetos y 1 GB, y tamaño máximo de fichero;
    - URL rechazadas (propuesto), con un opt-in futuro;
    - descargas de Hugging Face;
    - `mcp` en los extras `all`, `full` y `dev`;
    - nombre y registros del servidor.
13. **Candidatos inválidos en el `compare` de MCP:** ¿como fallos (propuesto, igual que en Python) o rechazados antes de ejecutar?
14. **Entrega de errores:** ¿`ToolError` con JSON (propuesto) o `CallToolResult(is_error=True)` con `structured_content`?
15. **Alias `result` de `ask()`:** ¿hasta 0.5.0 (propuesto) o eliminarlo ya, como anunció la 0.3.0?
16. **Validador de `ForecastPlan`:**
    - ¿los conjuntos de codificación de skforecast (propuesto) o solo lo que genera `plan()`?
    - ¿`categorical_features` como lista?
    - ¿un baseline con estimador?
17. **Texto de planes en JSON** (`explanation`, `reason`, `warnings`) que llega al prompt de `ask()`: ¿escaparlo o rechazar saltos de línea? Riesgo bajo: solo afecta a `--from-plan`.
18. **SKILL.md:** ¿dónde se publica, y se hace la prueba interna con el CLI?

Más preguntas menores:
- `PlanEditsDiscardedWarning` como clase propia;
- valores de `target_transformer` más allá de `StandardScaler`;
- un nivel explícito para `ForecasterDirectMultiVariate`;
- `--steps` con `--from-plan` como override, y cómo escribir los valores de tres estados en el CLI;
- exportar `ErrorInfo` desde la raíz;
- `describe(include_values=True)`: nunca, como opción, o como flag del servidor;
- que el script lea el fichero real de exógenas en lugar de `exog_future.csv`;
- `--format summary` en el CLI;
- la estacionalidad de frecuencias multiplicadas (`'3h'`, `'2W'`);
- `ComparisonResult.excluded`;
- los avisos del plan en las tablas del CLI.

### 10.11 Sin PR asignado (backlog)

- **Hallazgos de impacto bajo o solo en Python:**
  - MAPE en series que cruzan el cero;
  - target booleano;
  - fechas enteras `yyyymmdd`;
  - lags de reserva presentados como elegidos por el PACF (es un cambio de explicación, de pago);
  - nombres de kwargs de Foundation sin validar;
  - `test_size` entero sin fechas;
  - texto de `CandidateFailedWarning` (menciona `ComparisonResult.failures` aunque no haya resultado, y acaba en "..");
  - `date_column` igual al nombre del `DatetimeIndex`;
  - `MultiIndex` sin nombres o con 3 niveles;
  - enteros de numpy en `cv_config` en el núcleo (el servidor ya los convierte).
- **Runtime:**
  - `n_jobs='auto'` en los backtests (procesos loky residentes en el servidor): valorar `n_jobs=1` en el servidor;
  - la caché de numba en `site-packages` para instalaciones de solo lectura.
- **Estado:**
  - ids, versión de esquema y huella en los bundles (STA-14);
  - timeout y lista de hosts permitidos para las URL de la API de Python;
  - ejecutor en subproceso;
  - `diagnose()`.

Los scripts de reproducción de la fase 1 estaban en el scratchpad de la sesión y no se conservan. Cada hallazgo de este documento indica los datos y la llamada con que se reprodujo, para poder repetirlo.
