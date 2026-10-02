# Preparativos para el servidor MCP de skforecast-ai

Estado a 30/09/2026, actualizado el 01/10/2026 con la fase 2 (sección 11) y el 02/10/2026 con las fases 3a, 3b y 3c (secciones 12, 13 y 14). Base: rama `0.4.x`, con la sección 2 commiteada en `f87e89f`. La auditoría de la fase 1 (resultados en las secciones 4, 5, 7 y 9, y propuestas en la 10) está en la rama `feature/mcp-audit` y no toca `skforecast_ai/`. Este documento sirve para retomar el trabajo en otra sesión: qué se decidió, qué está hecho, qué falta y en qué orden, y cómo verificarlo.

**Cómo leerlo.** Las secciones 1 a 8 son el plan original. Cada punto pendiente lleva ahora el resultado de contrastarlo con el código, marcado como **Verificado**, **Corregido** o **Nuevo**. La sección 9 recoge lo que la auditoría encontró fuera de ese plan. La sección 10 propone decisiones y un orden de PRs, y está pendiente de revisión. La sección 11 recoge lo implementado en la fase 2 (PRs 0 a 4) y sus desviaciones respecto a la 10; la sección 12 lo mismo para la fase 3a (PRs 5, 6, 7, 8, 10 y 11), la 13 para la fase 3b (PRs 9, 12, 13 y 14) y la 14 para la fase 3c (PRs 15, 16 y 17 y los pendientes de `describe()` de 13.1).

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

Salvo los PRs 0 a 4, hechos en la fase 2 (sección 11), los PRs 5, 6, 7, 8, 10 y 11, hechos en la fase 3a (sección 12), los PRs 9, 12, 13 y 14, hechos en la fase 3b (sección 13), y los PRs 15, 16 y 17, hechos en la fase 3c (sección 14), nada de esta sección está implementado: es una propuesta para revisar. Los números de PR remiten a la tabla de 10.8.

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
4. **Nombres con saltos de línea:** ¿rechazarlos solo en MCP (propuesto) o también en el núcleo? ¿Rechazar también `<` y `>`? (Primera parte decidida en la fase 2: solo en MCP, ver la sección 11. La de `<` y `>` sigue abierta.)
5. **CSV con formatos de fecha mezclados:** ¿rechazar (rompe `forecast()` que hoy funciona) o escribir `format='mixed'` en el script? ¿Opciones de lectura (`sep`, `decimal`, `encoding`, `dayfirst`) en `profile()`, el CLI y el MCP? (Propuesta: rechazar en la v1 y pedir ISO 8601 en el skill; las opciones de lectura, después.) (Para la fase 3a se decidió que el PR 7 cubre solo las celdas de fecha vacías y los husos mezclados; los formatos mezclados y el formato largo sin fecha siguen abiertos. Ver la sección 12.)
6. **NaN en exógenas futuras o en la última ventana con estimadores que los toleran:** ¿aviso (propuesto) o error? (Decidida antes de la fase 3a: aviso, y error con el resto; ver la sección 12.)
7. **Datos frente a perfil guardado (SIL-1):** ¿refrescar con nota (propuesto) o error ante cualquier diferencia? ¿Una exógena nueva es error (propuesto)?
8. **Series que terminan antes, en modo predicción:** ¿nota (propuesto) o error? (Decidida antes de la fase 3a: nota; ver la sección 12.)
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
16. **Validador de `ForecastPlan`:** (decidida en la fase 2, ver la sección 11)
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

## 11. Fase 2: hecho

Bloque de seguridad del MCP: los PRs 0 a 4 de la tabla 10.8, en la rama `fix/mcp-security`, creada desde `0.4.x` (`307de25`, que ya incluye `feature/mcp-audit`). Un commit por PR, en orden. Cada commit lleva su código, sus tests y su entrada en `docs/releases/releases.md` (0.4.0), salvo el PR 0, que es solo documentación. Antes de cada commit se pasaron `/verify` y el subagente `conventions-reviewer`, y en los PRs 1 a 3 también `/security-review`; cualquier prefijo de la rama se puede mergear.

Decisiones del autor aplicadas (10.10):
- pregunta 4: los nombres de columna no se rechazan en el núcleo; los saltos de línea se rechazarán en el tool `profile` del MCP (PR 18). La segunda parte (rechazar también `<` y `>`) no se decidió y sigue abierta;
- pregunta 16: los conjuntos de codificación de skforecast, `categorical_features` solo `'auto'` o None, y un baseline con estimador no se rechaza.

| Commit | PR | Contenido |
|---|---|---|
| `bd2863e` | 0 | `docs/user-guides/cli-usage.md:108` y `:122` dicen lo que se puede cambiar hoy |
| `717f209` | 1 | Frontera de render (10.1) |
| `c81c15c` | 2 | `validate_frequency` en `DataProfile` y sintaxis `owner/name` del id de Foundation |
| `ffe2165` | 3 | Validación cerrada de `ForecastPlan`, revalidación del plan recibido y `steps` |
| `eef1da5` | 4 | `compile()` dentro del `try`; `failed_line` y `failed_statement` |
| `4d68cfa` | 1 (corrección) | Docstring de `_format_initial_train_size` |

Lo que encontraron las revisiones de cada PR se corrigió antes de subirlo. Solo hubo una corrección posterior, `4d68cfa`: la revisión de esta sección vio que el docstring de `_format_initial_train_size` (PR 1) decía que el `repr()` de un Timestamp escribe el nombre del huso sin comillas, cuando lo escribe entre comillas sin escaparlo. El mensaje de `717f209` repite esa frase y no se reescribe, porque ya estaba subido.

**Qué cubre cada capa.**
- Render (PR 1): ningún valor de un plan, un perfil o un CV llega al script salvo de estas formas:
  - con `repr()`;
  - como constante de un mapa cerrado: imports de forecaster por familia de renderer, constructores de transformer, métodos de intervalo y plantillas de preprocesado;
  - como entero o bool comprobado (`steps` y los campos de `TimeSeriesFold`);
  - dentro de un comentario, con `_comment_text()`.

  Lo que no está en un mapa lanza `ValueError` al renderizar.
- Validadores (PRs 2 y 3): un perfil o un plan inválido cargado desde JSON se rechaza al cargarlo. `forecast()`, `forecast_code()`, `backtest()`, `backtest_code()` y `ask()` vuelven a validar el plan recibido.
- Ejecución (PR 4): un script que no compila también sale como `ForecastExecutionError`, con la línea y la sentencia que fallan.
- Regresiones: `tests/test_integration_code_injection.py` tiene una por cada vector de ejecución de código de 4.1 y 9.1, en cada plantilla, con datos hostiles construidos con `model_construct`. El payload crea un fichero marcador en `tmp_path`, y el test comprueba que no existe y que el error es el esperado.
  - Contra `0.4.x` sin parches fallan 78 de sus 80 tests, y 57 crean el marcador.
  - El resto, sin marcador: los métodos y comandos que solo devuelven el script (lo devolvían con el payload dentro), los casos que en `0.4.x` fallaban antes por otro motivo y la comprobación de rigor `steps=2.9`.
  - Los 2 que pasan en `0.4.x` son la clave de `estimator_kwargs` en `forecast_code()` y `backtest_code()`, que ya cerraba la validación del resultado.

**Desviaciones respecto a la sección 10, con su motivo.**
- PR 0: va como primer commit de `fix/mcp-security`, no directo sobre `0.4.x` como decían 10.8 y 10.9, porque el encargo de esta fase pedía un commit por PR, en orden, en una sola rama.
- PR 1, `initial_train_size` como `pd.Timestamp`: se escribe `pd.Timestamp(<repr de su texto>)` en lugar de `repr()` a secas. El `repr()` de un Timestamp es `Timestamp(...)`, que no existe en el script, y escribe el nombre del huso entre comillas sin escaparlo, así que un nombre con una comilla cierra la cadena (lo señaló `/security-review`; solo se alcanza desde Python). Así la línea compila y sigue siendo un literal.
- PR 1, campos de `TimeSeriesFold` (`steps`, `fold_stride`, `refit`, `fixed_train_size`, `gap`, `skip_folds`, `differentiation`): pasan por formateadores estrictos de entero y bool, no por `str()`. El fold solo valida en su constructor, y un atributo asignado después llegaba al script (`conventions-reviewer`). Para valores válidos la salida es idéntica byte a byte.
- PR 1, `int(plan.steps)`: se hace con un formateador estricto, que acepta `12.0` pero rechaza `'5'` y `2.9` en lugar de truncar en silencio.
- PR 1, imports de forecaster: además del mapa cerrado, cada familia de renderer solo acepta sus forecasters. Cierra más sin cambiar ningún script.
- PR 1, `interval_method`: el mapa solo tiene `'bootstrapping'` y `'conformal'`, los que se escriben; `'native'` nunca se escribe como método y lanza error si le llega a una plantilla ML.
- PR 1, plantillas de preprocesado: las cuatro viven como constantes en `_constants.py` y el recomendador las usa, de modo que la generación, el render y el validador comparten una sola fuente.
- PR 2: la sintaxis `owner/name` se comprueba después del prefijo de skforecast, para que un id no soportado (`'Chronos-2'`) conserve su mensaje. Un test usaba la frecuencia ficticia `'unknown_freq'`, que no es sintaxis de alias; pasa a `'unknown'`, con la misma intención.
- PR 3, revalidación: el plan se valida a partir de su volcado. Si la validación no cambia ningún valor (comparando también los tipos), se sigue usando el objeto recibido, y `result.plan is plan` se mantiene. Si convierte alguno (`steps=12.0`, un intervalo en cadenas o pasos de preprocesado como dicts, puestos con `model_copy`), se usa la copia validada, para que el script ejecute lo que se comprobó.
- PR 3, `ask()` con perfil y plan también revalida antes de renderizar: devuelve el script igual que `forecast_code()`.
- PR 3, `forecaster_kwargs` solo acepta enteros de Python donde espera un entero: un entero de numpy se escribiría como `np.int64(...)` y el plan no se podría guardar en JSON.
- PR 3, `forecaster_kwargs['steps']` de los forecasters directos se comprueba como entero, pero no se exige que coincida con `plan.steps`: ningún código lo lee, y exigirlo rechazaría bundles que hoy funcionan.
- PR 3, `steps` como cadena (`'12'`) se rechaza por no ser un entero. Antes pydantic la convertía en `ForecastPlan`, mientras `plan()` fallaba con Direct.
- PR 3, ajustes de tests que no son goldens: `tests/test_display.py` usaba el nombre antiguo `'ForecasterAutoreg'` en un plan, y el helper de `tests/tests_recommendation/test_backtesting.py` construía planes deliberadamente incoherentes para un helper defensivo; ahora con `model_construct`. Los tests de `_validate_lags` y `_validate_window_features` pasan a `tests/test_validation.py`, y la reexportación desde `_utils.py` tiene un test propio.
- PR 4: `str(exc)` no cambia; la línea y la sentencia van solo en atributos (criterio 3).
  - `failed_statement` es la sentencia entera, o solo la cabecera de un `for`, `if` o `with`.
  - Es solo la línea cuando el código no compila, cuando la línea tiene varias sentencias o en una cláusula de `try` o `match`.
  - El código se analiza una sola vez, y el árbol se reutiliza para localizar la sentencia.

**Tests.**
- Suite completa: de 1714 tests (más 1 omitido) en `0.4.x` a 1952 (más 1 omitido), es decir, 238 más.
- Por commit, con `/verify`: 1714 (PR 0), 1803 (PR 1), 1829 (PR 2), 1934 (PR 3) y 1952 (PR 4).
- `tests/test_integration_code_injection.py`: 80 tests.
- Los goldens del LLM no cambian. De los scripts generados solo cambiaron los 2 tests que fijaban la plantilla larga de `drop_duplicates`, que no se había publicado.

**Pendiente o anotado, fuera de esta fase.**
- `_comment_text` no escapa la categoría Cf (controles bidireccionales). Solo cambia cómo se ve la línea del comentario, no lo que se ejecuta; lo señalaron `/security-review` y `conventions-reviewer`, y el encargo nombra Cc, Zl y Zp.
- Frontera de confianza (para la documentación del servidor, 10.7): los validadores cubren datos (JSON, CSV, overrides tipados), no objetos de Python hostiles. Una subclase de `str` con `__eq__` y `__repr__` propios pasa por `model_copy`, pero exige ya poder ejecutar Python en el proceso.
- `backtest()` y `compare()` con un `TimeSeriesFold` cuyo `initial_train_size` es un `pd.Timestamp` siguen fallando antes de renderizar, con un `TypeError` sin envolver de `build_cv_explanation`. `backtest_code()` ya escribe una línea válida. Es de las comprobaciones tempranas (PR 23).
- El tool `profile` del MCP debe rechazar los saltos de línea en los nombres (pregunta 4; PR 18).
- La última nota de 4.1 no se cubre en esta fase: un salto de línea en un nombre de columna o en un id de serie puede falsificar etiquetas de sección (`</dataset>`) en el contexto que recibe el LLM de `ask()`. No ejecuta código, y tocarlo exige cambiar `llm/context.py`, que esta fase no debía tocar; va con la pregunta 17 de 10.10 y con el rechazo en el tool `profile`.
- El PR 5 (jerarquía de excepciones) no se hizo. Sigue abierto cuándo entra: justo después de este bloque o después del servidor, porque toca unos 95 sitios de los mismos ficheros que los PRs 6 a 11 (10.8).

**Pendiente para la fase 3** (PRs 6 a 13 de la tabla 10.8):
- PR 6: el perfil ordena las filas por fecha antes de inferir, y la entrada del PACF se deduplica y ordena;
- PR 7: fechas CSV vacías y husos horarios mezclados (los formatos mezclados y el largo sin fecha, aparte);
- PR 8: frecuencia por serie en formato largo y series que acaban antes;
- PR 9: ForecasterStats escribe, explica y cuenta el CV que se ejecuta;
- PR 10: validar las exógenas futuras y compartir el cargador del CLI;
- PR 11: última ventana del target;
- PR 12: `describe()` sin las instrucciones del LLM de `ask()`;
- PR 13: `interval_method` en los backtests multiserie (usará el mapa cerrado de métodos del PR 1).

## 12. Fase 3a: hecho

Datos correctos y modelo de errores: los PRs 5, 6, 7, 8, 10 y 11 de la tabla 10.8, en ese orden, en la rama `fix/mcp-data`, creada desde `0.4.x` (`fd31618`, que ya incluye `fix/mcp-security`). Un commit por PR, cada uno con su código, sus tests y su entrada en `docs/releases/releases.md` (0.4.0); cualquier prefijo de la rama se puede mergear. Antes de cada PR de datos (6, 7, 8, 10 y 11), un workflow buscó y reprodujo los casos límite de los datos que toca (CSV, formato largo, husos, NaN, exógenas); el mensaje del PR 11 no lo nombra, pero sus casos están en las secciones "Reproduced at the base" y "Left for section 12" de ese mensaje. Antes de cada commit se pasaron `/verify`, el subagente `conventions-reviewer`, `/code-review` y un workflow de revisión adversarial que intenta demostrar que el PR rompe una llamada que funcionaba o deja un caso silencioso; el PR 10 pasó también `/security-review`. La corrección `b1b9dea`, solo de documentación, pasó el build de la documentación. Las plantillas de render y sus goldens no cambian en ningún commit, ni los goldens del LLM; el script de unos datos concretos sí puede cambiar cuando cambia su perfil o su plan (PRs 6 y 8).

Decisiones del autor aplicadas:
- PR 5 (que 10.8 dejaba abierto): entra antes que los PRs 6 a 11;
- pregunta 5 de 10.10: el PR 7 cubre solo las celdas de fecha vacías y los husos mezclados; los formatos mezclados y el formato largo sin fecha quedan fuera de esta fase;
- pregunta 6: aviso con los estimadores que toleran NaN, error con el resto (exógenas futuras y última ventana);
- pregunta 8: una serie que termina antes que las demás recibe una nota en el resultado, no un error.

| Commit | PR | Contenido |
|---|---|---|
| `8402466` | 5 | Jerarquía de excepciones con `code`, `field` y `hint`; `ErrorInfo` |
| `9f44166` | 6 | El perfil ordena las filas por fecha; la entrada del PACF se lee como la ajusta el script |
| `f275cd1` | 7 | Fechas CSV con celdas vacías o husos UTC mezclados dan un error claro |
| `09248da` | 8 | Frecuencia por serie en formato largo, huecos de todas las series y nota de series que terminan antes |
| `44612b7` | 10 | Validación de las exógenas futuras de `forecast()` y cargador de `--exog` compartido |
| `2a397a6` | 11 | Última ventana del target |
| `7c024e5` | 8 (corrección) | La nota de series que terminan antes también en formato ancho |
| `b1b9dea` | 10 (corrección) | La entrada del PR 10 en las notas de versión ya no promete leer un separador al final de cada fila |

Lo que encontraron las revisiones de cada PR se corrigió antes de subirlo, o quedó anotado en su mensaje como decisión, limitación o pendiente (los pendientes, abajo). Hubo dos correcciones posteriores, cada una en un commit nuevo al final:
- `7c024e5`: al revisar el PR 11 se vio que el PR 8 solo daba la nota de series que terminan antes en formato largo; en ancho, `forecast()` seguía devolviendo N-1 series sin aviso (9.2). La nota pasa a darse también en ancho, y en largo dice lo que hace de verdad un modelo foundation con una serie cuyas últimas filas no tienen valor.
- `b1b9dea`: la entrada del PR 10 decía que el CLI lee un separador al final de cada fila de `--exog`, un cambio que se revirtió durante sus revisiones (se lee como en 0.3.1).

**Qué cubre cada PR.**
- PR 5: `SkforecastAIError` con `code` estable, `field` y `hint`; `InvalidInputError`, `InvalidInputTypeError` y `DataNotFoundError` siguen siendo `ValueError`, `TypeError` y `FileNotFoundError` con los mismos mensajes; `ErrorInfo.from_exception()` convierte cualquier error en datos. `tests/test_source_conventions.py` falla con cualquier otro `raise` desnudo de esas clases en el paquete, salvo los invariantes internos y los recursos del paquete, que conservan su clase y salen como `internal_error` (los tres `FileNotFoundError` de `llm/skills.py` y la comprobación de `foundation_model` en `recommendation/preprocessing.py`). Un JSON de `--from-plan` o `--from-profile` que no se puede leer, y una URL que se descarga pero no es un CSV, son `data_unreadable`; una URL inalcanzable es `data_not_found`. `ask()` lleva las preguntas que citan `InvalidInputError` o `DataNotFoundError` al skill de resolución de problemas, como hacía con `ValueError`.
- PR 6: filas fuera de orden de fecha se ordenan antes de perfilar, con una nota en `DataProfile.warnings` (`index_is_monotonic` y `frequency_is_set` describen la entrada tal como llegó, y son False en ese caso); las fechas de texto se leen como las lee el script (el formato de la primera fecha), y las filas repetidas o sin fecha no cuentan para los lags.
- PR 7: una columna de fechas de un CSV con celdas vacías (también las filas hechas solo de separadores) o con desplazamientos UTC que cambian lanza un error que nombra la columna y las filas o los desplazamientos, también con un perfil guardado; si una columna posterior tiene fechas completas, se usa como antes con un aviso (sin aviso cuando se da `date_column`).
- PR 8: en formato largo se lee la frecuencia de cada serie (también con fechas con huso); frecuencias distintas o timestamps fuera de la rejilla lanzan error; los huecos se suman sobre todas las series; una nota nombra las series cuyo último valor es anterior a la última fecha con valor. Coste: `create_data_profile` es entre un 5 y un 37 % más lento (0,2 a 0,6 s) en paneles largos de un millón de filas, y más rápido en 20.000 series semanales con huecos.
- PR 10: `forecast()` comprueba las exógenas futuras antes de ejecutar: columnas, fechas leídas como las lee el script (las `steps` fechas tras la última de los datos, sin huecos ni filas fuera de la rejilla, en el huso de los datos o en otro cuya rejilla contenga esas fechas), en formato largo todas las series que el forecaster predice, tipos, categorías nuevas y valores NaN o infinitos (error si el estimador no los tolera, aviso si los tolera). El cargador de `--exog` pasa a `_utils.load_exog` y lee las fechas con el mismo parser que los datos.
- PR 11: `forecast()` en modo predicción, antes de exigir o comprobar `exog`:
  - las filas finales sin valor del target (en ninguna serie) lanzan error con cualquier forecaster y estimador, nombrando el último valor y las filas a quitar;
  - los NaN que leen de verdad las predicciones (los lags en cada paso, la diferenciación, una ventana móvil con todos sus valores NaN y las fechas equivalentes de `ForecasterEquivalentDate`), calculados como los lee skforecast y contrastados con él en los tests, siguen la regla de la pregunta 6; los que solo leen las estadísticas móviles, que los saltan, no cambian nada;
  - `ForecasterStats` (que ya falla con cualquier NaN) y los modelos foundation (que los reciben tal cual) solo pasan la comprobación de filas finales.

**Desviaciones respecto a la sección 10, con su motivo.**
- PR 5:
  - `hint` existe pero ningún sitio lo rellena todavía: sacar de los mensajes los remedios de pandas (`dayfirst`, `to_datetime`), como quería 10.3, cambiaría `str(exc)`.
  - `compare()` sigue registrando un candidato rechazado como `ValueError: ...` (`CandidateFailure`), porque registrar el nombre nuevo cambiaba `str(AllCandidatesFailedError)` y el contexto de `ask()`.
  - `ErrorInfo` se exporta desde `skforecast_ai.schemas`; exportarlo también desde la raíz sigue siendo una de las preguntas menores de 10.10.
  - `field` sigue unas convenciones (el argumento que hay que cambiar; `data` para el contenido de los datos; `profile` para un perfil sin frecuencia en `plan()`) descritas en el mensaje del commit.
- PR 6: el PACF no se pone en la rejilla de la frecuencia: el workflow de casos límite mostró que cambiaría los lags de toda entrada ordenada con huecos. Una entrada ya ordenada se devuelve como el mismo objeto.
- PR 7: un error en vez de un arreglo (quitar las filas sin fecha haría que el perfil no coincidiera con el script; pasar a UTC mueve fechas diarias a medianoche local al día anterior). Una columna posterior de fechas completas se sigue usando, con aviso, porque rechazarla rompería CSVs que funcionan en 0.3.1; una columna posterior que solo tiene horas del día no ocupa su lugar. Para una columna sin nombrar solo cuentan fechas claras (día, mes y año de cuatro cifras); los nombres de huso distintos de UTC se dejan a pandas, y los desplazamientos constantes siguen funcionando en cualquier escritura.
- PR 8: un error en vez de remuestrear, porque cualquier elección cambiaría los datos de alguna serie; las series con menos de 10 fechas, o con dos fechas a un paso de la rejilla, se toman como de la frecuencia de la rejilla con huecos.
- PR 10:
  - `forecast_code()` no comprueba su `exog` (devolvía el código para cualquier `exog` en 0.3.1 y el documento no lo decide).
  - Los NaN siguen la pregunta 6 tal como se decidió; 10.6 proponía además un error cuando la columna no tenía NaN en el entrenamiento, que la decisión no mantiene.
  - La comprobación del inicio de las fechas solo se aplica a los forecasters que leen las exógenas por posición: los que seleccionan por fecha ignoran las filas anteriores, y rechazarlas rompía llamadas que funcionaban.
  - Los valores infinitos y las categorías nuevas siguen la regla de los NaN; las categorías no se comprueban con un modelo foundation, que toma los valores tal cual (su aviso dice que los recibe tal cual).
  - Días naturales para datos de días laborables (y horas naturales para horas laborables) se aceptan, porque `asfreq` los reduce.
  - El cargador de `--exog` mantiene la lectura de 0.3.1 donde el lector de los datos no encuentra columna de fechas.
- PR 11:
  - "La ventana que leen los lags" es el conjunto de valores que leen las predicciones (depende de `steps` y del forecaster), no toda la última ventana (`window_size`): un NaN que no lee ningún lag daba predicciones finitas con Ridge, y un error ahí rompería esa llamada.
  - Las filas finales son fechas de los datos, no filas de cada serie: una serie que termina antes es la nota de la pregunta 8 aunque sus últimas filas existan sin valor.
  - `ForecasterEquivalentDate` sigue la regla de un estimador que no tolera NaN (no tiene estimador y los repite como predicciones NaN), y un NaN que lee la inversa de la diferenciación lanza error también con LightGBM (principio 3 de `AGENTS.md`: sus predicciones serían todas NaN).
  - Solo `forecast()`: `forecast_code()` no cambia, y el modo evaluación queda para el PR 25. Los valores infinitos del target no se comprueban (PR 23).

**Cambios para quien usa la librería** (llamadas que funcionaban en 0.3.1):
- PR 5: `InvalidInputTypeError` también es un `ValueError`, así que un `except ValueError` captura los antiguos `TypeError` de validación; las trazas muestran los nombres de clase nuevos.
- PR 6:
  - datos con filas fuera de orden de fecha dan el perfil, los lags, el plan, el script y las predicciones de los datos ordenados, con una nota (antes, el orden descendente fallaba dentro del script y las filas barajadas daban otros lags); en formato largo, la nota aparece también cuando la serie desordenada no es la primera;
  - filas idénticas repetidas o sin fecha pueden cambiar los lags;
  - fechas de texto con el día primero se leen así en todo el fichero cuando la primera fecha no es ambigua (y como mes primero cuando lo es, como el script); en memoria, una `date_column` así infiere ahora la frecuencia (era None y `plan()` fallaba) y desaparece el aviso de pandas.
- PR 7: un CSV cuya columna de fechas tiene celdas vacías, o cuyas fechas mezclan desplazamientos UTC, lanza error (también con un perfil guardado) donde las fechas pasaban a ser una exógena; una columna así antes de otra de fechas completas da un aviso; `profile()` ya no emite el `FutureWarning` de pandas sobre husos mezclados.
- PR 8: datos largos con series de distinta frecuencia o con timestamps fuera de la rejilla lanzan error donde se remuestreaban o se perdían filas; los huecos de todas las series cuentan para `has_gaps` (y para las reglas del plan que lo leen); una primera serie demasiado irregular junto a otras regulares tiene ahora frecuencia (era None y `plan()` fallaba); la nota de series que terminan antes (en ancho desde `7c024e5`).
- PR 10: `forecast()` lanza error con unas exógenas futuras:
  - con fechas que faltan, de otra frecuencia o fuera de la rejilla;
  - con filas antes de la primera fecha a predecir, en los forecasters que leen por posición;
  - con fechas de texto en el índice de datos indexados por fecha, o en formato largo;
  - sin fecha, con fechas repetidas o con un huso cuya rejilla no contiene las fechas a predecir;
  - con una serie que el forecaster predice y que falta, en formato largo;
  - con categorías nuevas, texto donde los datos tienen números, o NaN o infinitos y un estimador que no los tolera; con LightGBM y los demás que los toleran, un aviso con las mismas predicciones.

  `exog` debe ser un DataFrame o una Series con nombre.
- PR 10, en el CLI: en `--exog`, las celdas de fecha vacías y los desplazamientos UTC que cambian lanzan error, como en los datos, y los formatos de fecha mezclados lanzan error antes de ejecutar; se encuentran las fechas en una columna posterior, se deja fuera una primera columna de números de fila y se nombra una `--date-column` que el fichero no tiene; las filas con dos o más campos más que la cabecera lanzan error.
- PR 11: `forecast()` en modo predicción con filas finales sin target lanza error con cualquier estimador; con un NaN que leen las predicciones, error con Ridge (y con `ForecasterEquivalentDate`) donde las predicciones salían NaN, y aviso con LightGBM y los demás, con las mismas predicciones.
- Previstos por el documento, pero rompen llamadas que daban un resultado correcto (pregunta abierta abajo): con `ForecasterRecursiveMultiSeries`, unas filas futuras añadidas sin target a todas las series (que skforecast descarta) daban las predicciones correctas, y ahora lanzan error porque 10.6 dice "siempre"; lo mismo LightGBM con datos diarios cuyos fines de semana están siempre vacíos y que terminan en domingo.
- No previstos palabra por palabra por el documento (cada mensaje de commit los explica):
  - PR 7: una columna de fechas dispersa de un CSV (al menos la mitad llena) se toma por columna de fechas con celdas vacías y lanza error;
  - PR 8: datos diarios junto a una serie de días laborables son `'D'` con huecos sea cual sea el orden; una serie de 10 o más fechas exactamente cada dos días entre series diarias lanza error; los datos largos con huso también se comprueban;
  - PR 10: un modelo foundation con datos anchos rechaza columnas sin historia; `pd.NA` lanza error donde el script fallaba; se leen una Series con nombre y un índice de fechas de Python; una exógena del CLI con las fechas en una columna posterior conserva su primera columna salvo que numere las filas;
  - PR 11: `ForecasterEquivalentDate` y la inversa de la diferenciación, como se dice en las desviaciones.

**Tests.**
- Suite completa: de 1952 tests (más 1 omitido) en `0.4.x` a 2680 (más 1 omitido), es decir, 728 más.
- Por commit, con `/verify`: 2023 (PR 5), 2104 (PR 6), 2260 (PR 7), 2398 (PR 8), 2541 (PR 10), 2669 (PR 11) y 2680 (corrección del PR 8); la corrección del PR 10 es solo documentación.
- Una regresión por cada hallazgo de 9.2 y 10.6 cubierto, con los datos de su reproducción, y una por cada hallazgo confirmado de las revisiones.
- Con un CSV, un test ejecuta el script como fichero y lo compara con `forecast()` en los PRs 6, 8 y 11 (`tests/test_integration_standalone_script.py`). En los PRs 7 y 10 no se añadió ese test: en el 7, los casos nuevos lanzan error antes de ejecutar; en el 10, los workflows de casos límite compararon el script ejecutado como fichero con `forecast()` y encontraron la excepción anotada abajo (el script de formato largo con `exog_future.csv`).
- Los goldens del LLM y los de render no cambian en ningún commit.
- Paridad, en cada PR y otra vez al final de la rama (`b1b9dea`), con `bike_sharing`, `h2o` e `items_sales` (ancho y largo, este con `melt`): el perfil, el plan, el script y las predicciones de `forecast()`, en modo predicción y en modo evaluación, son idénticos a los de `0.4.x` antes de esta fase (`fd31618`). Ningún cambio buscado afecta a estos datos.

**Para el check de pago** (no se lanzó en esta fase): llegan al contexto de `ask()` por `DataProfile.warnings`, sin cambiar ningún golden:
- la nota de filas ordenadas (PR 6);
- la nota de series que terminan antes (PR 8), que desde `7c024e5` dice "la última fecha con un valor" en lugar de "la última fecha de los datos", tiene una redacción nueva en largo y otra propia en ancho, y se da también con datos anchos de dos o más columnas objetivo con fechas;
- el recuento de huecos sumado sobre todas las series (PR 8);
- la nota de fechas fuera de los años 1677 a 2262 en formato largo (PR 8).

Los avisos de los PRs 7, 10 y 11 son avisos de Python, no llegan al contexto.

**Preguntas nuevas para el autor.**
1. Filas finales sin target con `ForecasterRecursiveMultiSeries` (que las descarta y predecía bien) y con periodos siempre vacíos (fines de semana) y estimadores que toleran NaN: ¿error siempre, como dice 10.6 y como está implementado, o eximirlos?
2. NaN dentro de `window_size` que solo leen las estadísticas móviles (que los saltan) o que ningún lag lee para los `steps` pedidos: ¿siguen sin error con Ridge (implementado, con el aviso propio de skforecast) o deben seguir la regla de la pregunta 6?
3. `forecast_code()`: ¿debe comprobar `exog` y la última ventana como `forecast()`? Hoy devuelve el código para cualquier entrada, como en 0.3.1.
4. Los mensajes de error y los avisos nombran categorías, fechas e ids de series de los datos: decidir antes del PR 18 si el MCP los reenvía tal cual (principio 4 de `AGENTS.md`).
5. PR 7: la heurística que toma una columna de fechas dispersa (al menos la mitad llena) de un CSV por columna de fechas con celdas vacías; las fechas con año de dos cifras no se comprueban salvo en la columna nombrada; las columnas datetime en memoria y los `DatetimeIndex` con `NaT` no se tocan.
6. PR 10: una categoría vista solo en las primeras filas que ocupan los lags se codifica como NaN sin aviso; un separador al final de cada fila de `--exog` se lee como una cabecera con un campo menos, como en 0.3.1.

**Pendiente o anotado, fuera de esta fase.** Sale de los mensajes de commit y de los workflows de casos límite del PR 11.
- El script de formato largo lee `exog_future.csv` sin parsear sus fechas: ejecutado como fichero, sus predicciones usan exógenas NaN (PR 17, que cambia scripts).
- Modo evaluación (PR 25):
  - un NaN en la última ventana de la partición de entrenamiento falla tarde en las métricas con Ridge y es silencioso con LightGBM;
  - una partición de entrenamiento cuya última fecha no tiene target en ninguna serie desplaza las predicciones una fecha, y las métricas las comparan por posición;
  - en multiserie, un NaN de la partición de test falla tarde (`_check_evaluated_target` no mira multiserie), y una serie que termina antes de `end_train` falla con un error poco claro;
  - con un índice con huso, algunos casos lanzan un `TypeError` sin envolver.
- PR 24: una serie más corta que la ventana o sin ningún valor falla tarde dentro del script; una serie que skforecast deja fuera del entrenamiento (sin ninguna fila completa) se sigue comprobando en el PR 11; el plan de `ForecasterStats` aconseja `dropna_from_series`, que no tiene.
- PR 23: los valores infinitos del target (silenciosos con `ForecasterStats` y `ForecasterEquivalentDate`); un target no numérico (`'-'`, `'?'`) hace fallar `profile()` dentro del PACF de skforecast con un `ValueError` sin envolver; los errores de lectura de pandas de un CSV local como `data_unreadable`; rellenar `hint` con los remedios que hoy van en los mensajes.
- PR 8, limitaciones que se mantienen como en la base (huecos silenciosos): una serie en el día 15 de cada mes o quincenal entre series diarias, días laborables con festivos tomados por `'D'` entre series horarias, y las series exactamente regulares por azar en paneles dispersos muy grandes.
- La nota de series que terminan antes escribe la medianoche sin hora ni huso y las demás horas con ellos (`_fmt_timestamp`), lo que en datos con huso y frecuencia inferior al día mezcla formatos; `series_lengths` sigue dando como fin de cada columna ancha la última fecha del índice.
- Con un perfil guardado de otros datos, solo se comprueban las filas que el script lee; la comparación del perfil con los datos es el PR 27.

**Pendiente para la fase 3b** (PRs 9, 12, 13 y 14 de la tabla 10.8):
- PR 9: ForecasterStats escribe, explica y cuenta el CV que se ejecuta (cambia el script del backtest Stats y entra en el check de pago);
- PR 12: `describe()` sin las instrucciones del LLM de `ask()`;
- PR 13: `interval_method` en los backtests multiserie (goldens nuevos);
- PR 14: límites de `describe()`.

### 12.1 Revisión del autor y correcciones

Antes de mergear la fase 3a, una verificación independiente comparó `0.4.x` antes de la fase (`fd31618`), la rama y `v0.3.1`, y el autor decidió las preguntas abiertas. Las correcciones van como commits nuevos al final de `fix/mcp-data`; ninguno subido se reescribió.

**Verificación.**
- Ejemplos de la documentación que no necesitan LLM: 30 pasos de Python y 34 comandos del CLI, con el dataset de demo, `h2o`, `bike_sharing` (fechas en texto y ya leídas), `items_sales` y `store_sales` en formato largo. Perfil, plan, código, explicaciones, predicciones, métricas, ficheros escritos y salida del CLI idénticos a la base, sin avisos nuevos. Quien sigue la documentación no nota la fase.
- Las dos llamadas de la pregunta 1 se reprodujeron: (a) con `ForecasterRecursiveMultiSeries` las predicciones eran exactamente las de los datos sin las filas finales (diferencia 0,0); (b) con fines de semana vacíos y LightGBM no eran las correctas (empezaban otro día; jueves y viernes difieren hasta 131).
- La tarea adicional de render tenía dos bugs reales que ya fallaban en `v0.3.1`. El `KeyError: None` que atribuía al PR 10 no se reproduce.

**Decisiones del autor.**

| Pregunta | Decisión | Commit |
|---|---|---|
| 1a | Aviso, no error, para `ForecasterRecursiveMultiSeries`: descarta las filas finales y predice como sin ellas; la ventana se comprueba desde el último valor | `4b7761f` |
| 1b | Se mantiene el error; el mensaje propone quitar todos los fines de semana (datos de días laborables) cuando nunca tienen valor | `4b7761f` |
| 2 | Sin error; el docstring de `forecast()` lo dice (skforecast ya avisa) | `3d34630` |
| 3 | `forecast_code()` no comprueba los datos; su docstring lo dice y la anotación de `exog` coincide con `forecast()`, sin cambiar el comportamiento | `3d34630` |
| 4 | El MCP reenvía los mensajes tal cual, con un máximo de 5 valores y el límite de tamaño del servidor. Antes del PR 18, el SKILL.md y la documentación del servidor lo dicen, y `values_included` se refiere solo a predicciones, métricas y filas | (PR 18) |
| 5 | Se mantiene el error del PR 7; cuando ninguna columna tiene las fechas, el mensaje añade cómo pasar una exógena de fechas dispersas (leer el CSV con pandas y pasar el DataFrame). 5b y 5c, sin cambios | `fc9e5f9` |
| 6a | Aviso (nunca error) para una categoría que solo aparece en las primeras filas, que ocupan los lags: el estimador no se entrena con ella | `3bb0263` |
| 6b | Una cabecera con un campo menos cuya última columna queda vacía es un separador al final de cada fila: error en `load_exog` | `3bb0263` |

**Otros commits.**
- `2f4c8a9` (parte del PR 24): `plan()` rechaza `ForecasterDirectMultiVariate` con datos largos de varias series y los datos largos de varias series fechados por el índice, cuyos scripts fallaban siempre. Hacer que el multivariante funcione con datos largos sigue en el PR 32.
- `e0487b2`: las entradas de la fase 3a en `docs/releases/releases.md` se acortan a lo que nota quien usa la librería; las de los PRs 10 y 11 se acortaron en sus commits.

**Omisiones de la sección 12, completadas.**
- API pública nueva no citada: `ErrorCode` y `ERROR_CODES` en `skforecast_ai.exceptions`, y que `LLMRequiredError`, `LLMCallError`, `ForecastExecutionError` y `AllCandidatesFailedError` heredan ahora de `SkforecastAIError` (ganan `code`, `field` y `hint`). La entrada del PR 5 lo dice.
- `forecast_code()` aceptaba en `exog` lo que `forecast()` rechaza (un array de numpy); se documenta, sin cambiar el comportamiento.

**Tests.** De 2680 a 2698 (más 1 omitido), todos en verde con `TZ=UTC`.

**Pendiente o anotado.**
- `profile.forecaster_candidates` sigue ofreciendo `ForecasterDirectMultiVariate` con datos largos, que `plan()` ya rechaza. Quitarlo cambia los goldens del contexto del LLM: va con el PR 24 y el check de pago.
- El MCP solo acepta rutas, así que un CSV sin fechas con una exógena de fechas dispersas no se puede perfilar ahí hasta que existan las opciones de lectura (pregunta 5 de 10.10).
- Entorno de tests, resuelto en `b186b4d`:
  - con numpy 2.5 y pandas 2.3.3, `pd.Timedelta(days=1)` emitía un `DeprecationWarning` que, con `filterwarnings = error`, paraba la recogida de los tests: ahora hay un `ignore` específico en `pyproject.toml`;
  - tres tests de `tests/tests_profiling` dependían de la zona horaria de la máquina (con `Europe/Madrid` pandas lee `'CET'` como hora local): `tests/conftest.py` ejecuta la suite en UTC.
- Los tests no se ejecutan en GitHub para las PRs a las ramas de versión (`unit-tests.yml` solo se lanza en PRs a `main`), y el autor decidió no cambiar CI: la suite se ejecuta en local o en las sesiones remotas, con `/verify`.

## 13. Fase 3b: hecho

CV de ForecasterStats, `describe()` e `interval_method`: los PRs 9, 13, 12 y 14 de la tabla 10.8, en ese orden, y un commit que quita `ForecasterDirectMultiVariate` de `profile.forecaster_candidates` para datos largos de varias series (pendiente de 12.1), en la rama `feature/mcp-describe`, creada desde `0.4.x` (`39825dc`, que ya incluye `fix/mcp-data`). Un commit por PR, cada uno con su código, sus tests y su entrada en `docs/releases/releases.md` (0.4.0); cualquier prefijo de la rama se puede mergear. Antes de cada commit se pasaron `/verify` (lint, tests afectados, suite completa y, según el caso, build de la documentación, goldens del LLM y `check_ask_context.py --dry-run`), el subagente `conventions-reviewer` y `/code-review`; lo que encontraron se corrigió antes del commit o quedó anotado en su mensaje y aquí. Ningún commit subido se reescribió y ninguno necesitó una corrección posterior.

Decisiones del autor aplicadas:
- pregunta 2 de 10.10: regla literal de `AGENTS.md` y una sola ejecución del check de pago antes de la release; no se lanzó en esta fase (los cambios para ese check, abajo);
- pregunta 3: `ForecasterStats` mantiene la ventana fija que ya ejecutaba, escrita de forma explícita en el script; las métricas no cambian.

| Commit | PR | Contenido |
|---|---|---|
| `2405a60` | 9 | ForecasterStats escribe, explica y cuenta el CV que ejecuta skforecast |
| `8b21529` | 13 | Los backtests multiserie escriben el `interval_method` del plan |
| `513fd11` | 12 | `describe()` sin las frases dirigidas al LLM de `ask()` |
| `0de31af` | 14 | Límites de `describe()` |
| `e8bd99e` | (12.1, parte del PR 24) | Sin `ForecasterDirectMultiVariate` entre los candidatos de datos largos de varias series |

**Qué cubre cada PR.**
- PR 9: `recommendation.backtesting.cv_as_executed(cv, forecaster)` devuelve, para `ForecasterStats` con un `refit` distinto de `True` (o 1), una copia con `refit=True` y `fixed_train_size=True` tras un `refit` falso (el valor del usuario tras un `refit` entero, que el script ya escribía); en cualquier otro caso, el mismo `cv`. La usan el script del backtest Stats, `resolve_cv_config` (`cv_config` con `refit` True, la ventana que se ejecuta y `n_fits == n_folds`), `build_cv_explanation` (frase nueva), el fragmento `code` de `create_cv()` y, a través de `count_estimator_fits(n_folds=...)`, el presupuesto y el aviso de `compare()` y `backtest()`. `CVResult.cv` conserva los parámetros dados. El aviso `LongTrainingWarning` de Stats propone menos folds en lugar de `refit=False`, y la explicación de `compare()` añade una frase cuando corre un candidato Stats.
- PR 13: `_emit_backtesting_call_multiseries` escribe `interval_method` cuando el plan tiene intervalo y su método no es el valor por defecto de `backtesting_forecaster_multiseries` (`'conformal'`); los planes multiserie y multivariante tienen `'bootstrapping'`.
- PR 12: `ExplainableResult.describe()` es `_build_llm_context(send_data=False, for_describe=True).text`; `for_describe` recorre las 5 implementaciones y los renderers que tienen una instrucción; las 4 frases dirigidas al LLM son constantes de `llm/context.py` (`PLAN_CODE_NOTE`, `SCRIPT_NOTE`, `RANKING_NOTE`, `LEADERBOARD_NOTE`); `tools/ai/update_golden_contexts.py` escribe también los goldens de `describe()`, y `docs/api/schemas/results.md` muestra su docstring.
- PR 14: solo con `for_describe=True`, 15 elementos por lista con "(first N of M)" (columnas objetivo, exógenas y categóricas, lags y window features del plan, avisos de datos, candidatos fallidos), los valores ausentes por serie o columna con los totales, y las métricas de las 5 primeras series más las filas agregadas (`average`, `weighted_average`, `pooling`), con una línea que lo dice; las estadísticas y los lags significativos, ya limitados a 5 series en `ask()`, dicen en `describe()` cuántas series hay. Con 500 series (ancho, 20 exógenas, 30 lags) `describe()` de un backtest ocupa 4.105 caracteres frente a 30.281 del contexto de `ask()`.
- Candidatos (`e8bd99e`): `select_forecaster_and_candidates` deja fuera `ForecasterDirectMultiVariate` con varias series en formato largo; `plan()` emite `UnrecommendedForecasterWarning` después de `_validate_task_input`, para no anunciar como usado un forecaster que rechaza a continuación.

**Desviaciones respecto a la sección 10, con su motivo.**
- PR 9:
  - `create_cv()` con un plan Stats: `cv_config`, la explicación y `code` describen el CV que se ejecuta, pero `CVResult.cv` conserva los parámetros dados. Pasarlo a `refit=True` haría reajustar en cada fold a cualquier otro forecaster con el que se reutilice (por ejemplo en `compare()`), lo que cambia resultados de llamadas que funcionan (criterio 3). Los docstrings de `CVResult` y `create_cv()` lo dicen.
  - Sin aviso de Python cuando el usuario pide `refit=False` o `fixed_train_size=False` para Stats: el documento no lo pide; el script, `cv_config` y la explicación ya dicen lo que se ejecuta (pregunta abajo).
  - No previsto por el documento: una frase en la explicación de `compare()` cuando corre un candidato Stats (la estrategia compartida decía "trained once"), y el remedio propio de Stats en `LongTrainingWarning`, porque `refit=False` no reduce sus ajustes.
- PR 13: `interval_method` solo se escribe cuando difiere del valor por defecto de skforecast, como en la llamada de una serie, para que ningún script existente cambie.
- PR 12: los dos añadidos de 10.5 (la ruta `send_data=False` deja de resumir la columna `fold` y da un bloque por serie; el contexto de `backtest_code()` deja de describirse como predicción) cambiarían el contexto de `ask()` con `send_data=False`, que el autor exige idéntico byte a byte, y el test de que `describe()` es ese contexto sin las frases. Se aplicó la alternativa que permite 10.5: las Notes de `describe()` avisan de las dos limitaciones, y un test fija la de `backtest_code()` para que su arreglo se note (pregunta abajo).
- PR 14: los textos de las explicaciones (perfil, plan, CV, comparación) no se recortan: habría que analizar texto libre. La explicación del plan nombra todos los lags; el docstring de `describe()` lo dice. El golden de 500 series sale de `GOLDEN_DESCRIBE_SCENARIOS` (los escenarios de siempre más ese backtest), para no añadir un golden de `ask()` en un PR que no debe cambiarlos.
- Candidatos: el cambio de orden del aviso no lo pide 12.1, pero sin él la llamada que rechaza el PR 24 avisaría "used as requested" justo antes del error, y con avisos como errores el aviso sustituiría al `InvalidInputError`.

**Cambios para quien usa la librería** (respecto a 0.3.1):
- PR 9, con un plan `ForecasterStats`:
  - el script del backtest (`backtest()`, `backtest_code()`, `compare()`, CLI) escribe `refit = True` y `fixed_train_size = True` cuando el CV no reajusta (0.3.1 escribía `refit = False` sin `fixed_train_size`; su CV por defecto reajustaba con ventana creciente, que `refit=True` sigue dando);
  - `cv_config` de `create_cv()` y `backtest()`: `refit` True, la ventana que se ejecuta y `n_fits == n_folds`; `CVResult.code` con ese `TimeSeriesFold`; `CVResult.cv` sin cambios;
  - una frase más en la explicación del CV, y en la de `compare()` cuando corre un candidato Stats;
  - `compare()` sin `candidates` deja fuera ForecasterStats por encima de 500 folds, con el aviso y la nota del presupuesto, y `LongTrainingWarning` por encima de 50 folds;
  - métricas y predicciones idénticas (comprobado con h2o y cuatro CV distintos; `Arima.fit` se llama `n_fits` veces).
- PR 13: los backtests de `ForecasterRecursiveMultiSeries` y `ForecasterDirectMultiVariate` con intervalo escriben `interval_method = 'bootstrapping'`; cambian `lower_bound` y `upper_bound`, no `pred` ni las métricas (comprobado con items_sales ancho y largo; el backtest no es más lento).
- PR 12 y 14: método público nuevo `describe()` en `ForecastingProfile`, `CodeGenerationResult`, `CVResult`, `ForecastResult`, `BacktestResult` y `ComparisonResult`; el contexto de `ask()` no cambia.
- Candidatos: `profile.forecaster_candidates` (y la tabla del perfil en el CLI) ya no lista `ForecasterDirectMultiVariate` para datos largos de varias series, y la explicación del perfil tampoco lo nombra; `plan()` con un forecaster rechazado por la forma de los datos lanza el error sin el `UnrecommendedForecasterWarning` previo.

**Tests.**
- Suite completa: de 2698 tests (más 1 omitido) en `0.4.x` a 2790 (más 1 omitido), es decir, 92 más.
- Por commit, con `/verify`: 2724 (PR 9), 2729 (PR 13), 2776 (PR 12), 2786 (PR 14) y 2790 (candidatos).
- Goldens de render: solo cambia el del backtest de ForecasterStats (PR 9); el PR 13 añade tres (multiserie ancho y largo y multivariante, con intervalo).
- Goldens del LLM: no cambian en los PRs 9, 13, 12 y 14 (en el PR 9 porque ninguno cubre ForecasterStats; en los PRs 12 y 14 porque el contexto de `ask()` no cambia); cambian 3 en el commit de los candidatos. El PR 12 añade 15 goldens de `describe()` en `tests/tests_llm/golden_describe/` y el PR 14 uno más (500 series); el commit de los candidatos cambia 3 de ellos.
- El contexto de `ask()` de los 15 escenarios y de los 6 constructores por defecto, con `send_data` True y False, es idéntico byte a byte al de `0.4.x` en los PRs 12 y 14.

**Para el check de pago** (no se lanzó en esta fase). Lista completa de lo que cambia en lo que recibe el LLM:
- PR 9 (sin golden, porque ninguno cubre ForecasterStats):
  - `<backtesting_strategy>` de `CVResult` y `BacktestResult` con un plan Stats: `refit: True`, `fixed_train_size: True` tras un `refit` falso, `n_fits` igual a `n_folds`;
  - `<deterministic_summary>` de esos resultados: la frase "ForecasterStats is refitted in every fold whatever `refit` says: skforecast requires it for ARIMA models.";
  - `<deterministic_summary>` de `ComparisonResult` cuando corre un candidato Stats: "ForecasterStats is refitted in every fold on a fixed (o expanding) window (N trainings): skforecast requires it for ARIMA models."; la nota "Applied identically to every candidate." de `<backtesting_strategy>` no cambia (pregunta abajo).
- PR 13: ningún texto; con intervalo, las estadísticas de `lower_bound` y `upper_bound` en `<predictions>` de un backtest multiserie salen de otros intervalos.
- PRs 12 y 14: cambia `llm/context.py` (las 4 frases pasan a constantes, y los renderers reciben `for_describe`), sin cambiar ni un byte de lo que envía `ask()`. Entran por la regla literal.
- Candidatos: en `<profile_decision>` de datos largos de varias series, "Alternative forecasters: ['ForecasterFoundation']" en lugar de "['ForecasterDirectMultiVariate', 'ForecasterFoundation']".
- Siguen pendientes los de las secciones 3 y 12 (notas de `DataProfile.warnings` de los PRs 6 y 8).

**Preguntas nuevas para el autor.**
1. PR 9: cuando el usuario pide `refit=False` (o `fixed_train_size=False`) para ForecasterStats, ¿basta con que el script, `cv_config` y la explicación digan lo que se ejecuta (implementado), o también un aviso de Python?
2. PR 12: los dos añadidos de 10.5 (columna `fold` y un bloque por serie con `send_data=False`; `backtest_code()` descrito como predicción). Arreglarlos cambia el contexto de `ask()` (de pago). ¿Se arreglan en ambos a la vez, junto al PR 36, o solo en `describe()`, renunciando a que sea el contexto de `ask()` sin las frases?
3. `compare()` con un candidato Stats: ¿cambiar también la nota "Applied identically to every candidate." del contexto (de pago), o basta con la frase de la explicación?
4. `describe()`: ¿recortar también las listas dentro de los textos de explicación (por ejemplo los lags del plan), que hoy crecen con los lags pedidos? Cambia explicaciones (de pago).
5. Un plan escrito a mano o cargado de JSON con `interval` e `interval_method=None`: el backtest multiserie usa conformal y el script de predicción no calcula intervalos. ¿El validador de `ForecastPlan` exige `interval_method` cuando hay `interval` (rechaza planes que hoy cargan) o el render toma el método de la tarea?
6. `UnrecommendedForecasterWarning` sigue saliendo antes de otros rechazos de `plan()` (`lags` con ForecasterStats, un id de modelo foundation, un intervalo), como en 0.3.1. ¿Se mueve al final de `plan()`, cambiando su orden respecto a los demás avisos?

**Pendiente o anotado, fuera de esta fase.**
- Las preguntas 2 a 6 de arriba.
- El check de pago, con todo lo de la lista anterior más lo de las secciones 3 y 12.
- La fixture `plan_multivariate` de `tests/tests_rendering` (y la nueva con intervalo) tiene `steps=5` y se renderiza con un CV de 10 pasos: solo se compara como texto, no se ejecuta.

**Lo que falta antes del servidor.** Con esta fase entran todos los PRs mínimos antes del PR 18 (1, 2, 3, 6, 7, 8, 9, 12, 13 y 14) y, de los mínimos antes del 19, el 10 y el 11. Faltan:
- PR 15: `progress_callback` y `CompareProgress` en `compare()` (mínimo antes del PR 19);
- PR 16: `ForecastPlan.warnings` y el panel "Plan Warnings" (muy recomendable);
- PR 17: el script carga el mismo fichero que la ejecución con rutas (muy recomendable; cambia scripts, y arregla el `exog_future.csv` de formato largo anotado en 12).

### 13.1 Revisión del autor y correcciones

Antes de mergear la fase 3b, una verificación independiente comparó `0.4.x` antes de la fase (`39825dc`) con la rama, y el autor decidió las preguntas abiertas. Las correcciones van como commits nuevos al final de `feature/mcp-describe`; ninguno subido se reescribió.

**Verificación.**
- Ejemplos de la documentación que no necesitan LLM (Python y CLI): predicciones y métricas idénticas a la base. Solo cambia lo que lista la sección 13: la frase de ForecasterStats en `compare()`, los candidatos de datos largos y `refit=True` de Stats en el script y en `cv_config`.
- PR 9: predicciones y métricas idénticas en 15 variantes de CV; `n_fits` coincide con las llamadas reales a `Arima.fit`; cada `backtest_code()` ejecutado como fichero da lo mismo que `backtest()`. El presupuesto de 500 ajustes solo excluye Stats en casos extremos (datos diarios con `steps=1` y 907 folds, donde Stats no terminó en 40 minutos).
- PR 13: `pred` y métricas idénticas; solo cambian las cotas, y `forecast()` coincide ahora con un backtest de un fold.
- PRs 12 y 14: el contexto de `ask()` es idéntico a la base en 82 contextos reales, salvo lo listado en la sección 13; `describe()` no tiene valores fila a fila y ocupa de 1,8k a 5,5k caracteres con 500 series.

**Decisiones del autor.**

| Pregunta | Decisión | Commit |
|---|---|---|
| 1 | `create_cv()` avisa con `IgnoredArgumentWarning` cuando un `refit` o `fixed_train_size` explícito no se ejecuta con ForecasterStats; los valores por defecto y `backtest()` con un `TimeSeriesFold` no avisan | `bdab512` |
| 3 | La nota "Applied identically to every candidate." se ajusta cuando corre Stats, en el bloque de `describe()` previo al servidor (cambia el contexto de `ask()`) | (pendiente) |
| 5 | El validador de `ForecastPlan` exige `interval_method` cuando hay `interval`; ningún plan generado por ninguna versión se ve afectado | `1186e57` |
| 6 | `UnrecommendedForecasterWarning` se emite al final de `plan()`, con el plan construido | `808cb9f` |

**Otros commits.**
- `6260207`: el `LongTrainingWarning` de Stats ya no propone `skip_folds`, que skforecast rechaza para ForecasterStats.
- `0a54cda`: la entrada de `create_cv()` decía que las métricas de Stats no cambiaban. Respecto a 0.3.1 sí cambian (su CV por defecto era `refit=True` con ventana creciente y ahora es fija); la entrada lo dice y cómo mantener lo anterior. Se acortan las entradas de `describe()` y de `n_fits`, y `bdab512` añade el Fix del síntoma de 0.3.1.

**Tests.** De 2790 a 2803 (con `chronos` instalado no hay omitidos).

**Pendiente antes del servidor (PR 18)**, en un bloque de `describe()` que cambia el contexto de `ask()` y entra en el único check de pago:
- La razón del paso de preprocesado "Categorical exogenous variables detected" lista todas las columnas: con 500 columnas categóricas `describe()` llega a 24k caracteres, por encima del límite de 20k de 10.7. Recortarla en origen con el mismo "(first N of M)".
- `describe()` (y `ask()`) describen el script de `backtest_code()` como una predicción, sin folds ni ajustes (pregunta 2 de la sección 13), y resumen la columna `fold` como una medida. Arreglarlo en el pipeline común.
- Pregunta 3 (arriba), "were not provided" en la tabla de clasificación, y marcadores de recorte con una sola forma.
- Goldens de ForecasterStats y de formato largo, que hoy no cubre ninguno.
- En la documentación del servidor: `values_included=False` significa sin filas; las estadísticas de las predicciones y las métricas sí van.

**Backlog (no lo causó esta fase).**
- Las cotas de los backtests multiserie cubren mucho menos de lo nominal (80 %): 56 % con ForecasterRecursiveMultiSeries y 14 % con ForecasterDirectMultiVariate en `items_sales`, por usar residuos dentro de muestra.
- skforecast falla en un backtest de ForecasterStats con `gap > 0` sin intervalo (`IndexingError` en `pred.iloc[forecaster.n_estimators * gap:, :]`): para reportar en skforecast.

## 14. Fase 3c: hecho

Requisitos previos al servidor: los PRs 15, 16 y 17 de la tabla 10.8 y los cuatro pendientes de `describe()` de 13.1 (4a a 4d), en ese orden, en la rama `feature/mcp-prereqs`, creada desde `0.4.x` (`a253a93`, que ya incluye `feature/mcp-describe`). Un commit por punto, cada uno con su código, sus tests y, si el cambio se ve, su entrada en `docs/releases/releases.md` (0.4.0); cualquier prefijo de la rama se puede mergear. Antes de cada commit se pasaron `/verify` (lint, tests afectados, suite completa, build de la documentación y, en 4a a 4d, goldens del LLM y `check_ask_context.py --dry-run`), el subagente `conventions-reviewer` y `/code-review`; el PR 17, que lee ficheros por ruta, también `/security-review` (sin hallazgos). Lo que encontraron se corrigió antes del commit; ningún commit subido se reescribió y ninguno necesitó una corrección posterior. El check de pago no se lanzó.

Decisiones del autor aplicadas: las de las secciones 6, 12.1 y 13.1 (en particular la pregunta 3 de 13: la nota "Applied identically to every candidate." se ajusta cuando corre ForecasterStats), y el orden de `UnrecommendedForecasterWarning` al final de `plan()` (`808cb9f`), que el invariante del PR 16 respeta.

| Commit | Punto | Contenido |
|---|---|---|
| `1d7c915` | PR 15 | `compare(progress_callback=...)` y `CompareProgress` |
| `8840782` | PR 16 | `ForecastPlan.warnings` y el panel "Plan Warnings" |
| `8753613` | PR 17 | El script carga el fichero que se ejecutó, también con rutas; `exog_future.csv` en formato largo |
| `a5ec6a8` | 4a | La razón del paso de categóricas nombra 15 columnas y "(first 15 of N)" |
| `eb7c613` | 4b | El script de `backtest_code()` se describe como backtest; la columna `fold` no se resume como medida |
| `c7d5c90` | 4c | Nota de ForecasterStats en la estrategia de `compare()`, clasificación recortada sin "were not provided" y una sola forma de marcador |
| `cdfd0e4` | 4d | Goldens de ForecasterStats y de formato largo multiserie para `ask()` y `describe()` |

**Qué cubre cada commit.**
- PR 15: `compare()` llama a `progress_callback` con un `CompareProgress(candidate, status, completed, total, error)` congelado al empezar cada candidato (`'started'`) y al terminar (`'succeeded'` o `'failed'`, con el mismo texto que la columna `error`). `total` cuenta los candidatos que corren (tras el presupuesto y con el baseline). Una excepción del callback no se registra como fallo de candidato: sale de `compare()` sin correr el siguiente, que es la cancelación cooperativa del PR 19, y antes se cierra la barra de progreso. Un callback que no es invocable lanza `InvalidInputTypeError` (`field='progress_callback'`) antes de perfilar. `CompareProgress` se exporta desde `skforecast_ai` y `skforecast_ai.schemas`.
- PR 16: `plan()` guarda en `plan.warnings` el texto exacto de los tres avisos que emite (baseline con valores ausentes, kwargs de LightGBM o XGBoost que la librería puede ignorar, `UnrecommendedForecasterWarning`), en el orden en que se emiten; el aviso de Python se mantiene. `validate_estimator_kwargs` devuelve la lista de sus mensajes. El display de un plan (y de los resultados que lo llevan) muestra el panel "Plan Warnings"; el validador no toca la lista y el contexto del LLM no la lee (PR 35).
- PR 17:
  - `_utils._with_data_path` sella en el perfil, con `model_copy` y sin leer el CSV otra vez, la ruta o URL con que se llamó a `forecast_code()`, `forecast()`, `backtest_code()`, `backtest()` y `compare()` (una vez, para todos sus candidatos). Con un perfil guardado y otra ruta, el script carga la ruta pasada.
  - `index_col=0, parse_dates=True` solo cuando el índice está en el fichero: exógenas futuras, índice de fechas o datos en memoria (la ruta marcador `data.csv`, ahora `PLACEHOLDER_DATA_PATH`). Un CSV sin fechas leído por ruta se lee tal cual.
  - En formato largo, `exog_future.csv` recibe `to_datetime` y `sort_values` como los datos (ForecasterRecursiveMultiSeries y ForecasterFoundation), en el código común, así que el script ejecutado y el fichero corren las mismas líneas.
  - La sustitución de `show_progress` se ancla a la línea de la llamada de backtesting.
  - Tests de determinismo con CSV y de scripts ejecutados como fichero.
- 4a: la razón del paso `handle_categorical_exog` se recorta donde se construye (`recommendation/preprocessing.py`), con el mismo límite y la misma forma que `describe()` (`MAX_DESCRIBE_ITEMS`, que pasa a `_constants.py`). Con 500 columnas categóricas, `describe()` del plan baja de 7.855 a 2.538 caracteres.
- 4b: `llm.context.backtest_cv_from_code` lee con `ast` (sin ejecutar nada) los literales del `TimeSeriesFold` que escribe el script, y `CodeGenerationResult` lo cuenta con `resolve_cv_config`, como `backtest()`. El contexto gana la sección `<backtesting_strategy>` y el modo "backtesting: predicts N folds of S steps, training the forecaster K times...". Con `send_data=False` (`describe()` y `ask()` sin datos), la columna `fold` da "Folds: N" en lugar de sus estadísticas.
- 4c: `_shared_cv_note` dice "Applied to every candidate, except ForecasterStats: skforecast refits it in every fold, on a fixed window (N trainings)." cuando un candidato Stats corrió con otro `refit`, otra ventana u otro número de ajustes que la estrategia compartida. La clasificación recortada dice "Rows shown (first N of M): the K lower-ranked rows are omitted." una sola vez. Todos los marcadores de recorte usan la forma "(first N of M[ noun])".
- 4d: siete escenarios nuevos en `GOLDEN_SCENARIOS`, cada uno con golden de `ask()` y de `describe()`: `cv_strategy_stats`, `backtest_stats`, `code_generation_stats_backtest`, `comparison_with_stats` (ForecasterStats sobre h2o con la estrategia de `create_cv()`, sin ajustar ningún ARIMA), y `profile_multi_series_long_exog`, `code_generation_multi_series_long_exog`, `backtest_multi_series_long_exog` (tres series en largo con una exógena numérica y una categórica y una serie que termina antes).

**Desviaciones respecto a la sección 10, con su motivo.**
- PR 15: 10.7 solo nombra el callback y la cancelación. Se eligieron dos eventos por candidato (el de inicio es el que permite cancelar antes de un candidato caro como Auto-ARIMA), la cancelación por excepción sin envolver (el servidor decide qué excepción lanza) y el parámetro al final de la firma (las llamadas posicionales de 0.3.1 siguen igual). El tiempo de `compare()` con callback queda dentro del ruido (h2o, tres candidatos: 0,49 a 0,54 s sin callback y 0,49 a 0,58 s con él) y los resultados son idénticos.
- PR 16:
  - La tabla del CLI (`plan`, `refine-plan`) no muestra el panel: el CLI ya imprime cada aviso, y los avisos del plan en las tablas del CLI son una pregunta menor abierta de 10.10, así que su salida en tabla queda como en 0.3.1 (criterio 3). `--format json` sí lleva la lista, porque vuelca el plan.
  - `refine_plan()` reconstruye el plan con `plan()`, así que sus avisos son los de esa llamada; los suyos sobre el `prompt` (modos con LLM, fuera del MCP) no se añaden. Docstring y test lo dicen.
- PR 17:
  - El sello se aplica también en `forecast_code()` y `backtest_code()` con un perfil guardado y otra ruta: 10.6 decía "se escribe la ruta de los datos realmente usados" y era el único caso en que estos métodos escribían otra.
  - Con un DataFrame y un perfil guardado, el script sigue cargando la ruta del perfil, como en 0.3.1: un DataFrame no tiene ruta y escribir el marcador cambiaría el script de una llamada que funciona (pregunta abajo).
  - El marcador `data.csv` decide la lectura con índice: los datos en memoria con índice de filas conservan `index_col=0` (lo encontró `/code-review`: quitarlo rompía el script de un DataFrame guardado con `to_csv()`). Un CSV real llamado exactamente `data.csv` y sin fechas se toma por el marcador y conserva la lectura de 0.3.1 (falla con `KeyError`, como antes; pregunta abajo).
  - El script sigue leyendo `exog_future.csv`, no el fichero real de exógenas (pregunta menor de 10.10), y los formatos de fecha mezclados quedan fuera (pregunta 5 de 10.10).
- 4b: se lee la estrategia del script en lugar de añadir un campo `cv_config` a `CodeGenerationResult`, para no cambiar el esquema público ni su JSON (criterio 3); la sección ya leía su contrato del código. Sin refits el script no escribe `fixed_train_size` (no tiene efecto), así que esa línea se omite en lugar de suponer un valor; las demás coinciden con las de `backtest()`. Un `initial_train_size` de tipo `pd.Timestamp`, que ya falla en `build_cv_explanation` (PR 23), da el modo backtest con "(its folds could not be counted from the script)" en lugar de fallar. El bloque por serie del resumen sin datos (10.5) no entra en el punto: con varias series el resumen sigue sumándolas, como dicen las Notes de `describe()`.
- 4c: la nota de ForecasterStats solo cambia cuando su estrategia difiere de la compartida; con una estrategia que ya reajusta en cada fold sigue "Applied identically...". El aviso de cabeza y cola de las predicciones con `send_data=True` ("interior rows were not provided") no es un recorte "first N" y queda como estaba (solo en `ask()`).
- 4d: un escenario más de lo previsto, `code_generation_multi_series_long_exog`, para fijar también el contexto del script real de formato largo con exógenas.

**Cambios para quien usa la librería** (respecto a 0.3.1):
- PR 15: argumento nuevo `compare(progress_callback=None)` y modelo público `CompareProgress`; sin callback nada cambia.
- PR 16: `ForecastPlan.warnings`, siempre vacío antes, lleva los avisos de `plan()` en todo plan construido por `plan()`, `refine_plan()`, `forecast()`, `backtest()`, `compare()` y el CLI, y en su JSON; dos planes que solo difieren en ella ya no son iguales. El display de un plan (y de los resultados que lo llevan) muestra el panel "Plan Warnings".
- PR 17:
  - scripts: `forecast()`, `backtest()`, `compare()` (cada candidato) y el CLI con una ruta o URL cargan ese fichero en lugar de `'data.csv'`; cualquier método con un perfil guardado y otra ruta carga la ruta pasada; un CSV sin fechas se lee sin `index_col`; los scripts de predicción en formato largo con exógenas parsean las fechas de `exog_future.csv` (dos líneas nuevas);
  - resultados: `result.profile.data_profile.data_path` es la ruta que se ejecutó;
  - ejecutados como fichero, esos scripts dan ahora las predicciones de la llamada;
  - `backtest(show_progress=False)` con una columna llamada como la línea de la llamada ya no falla.
- 4a: la razón del paso de categóricas nombra como mucho 15 columnas y "(first 15 of N)" (display del plan, tabla del CLI, `describe()` y `ask()`).
- 4b: `ask()` y `describe()` de un resultado de `backtest_code()` lo describen como backtest, con su estrategia, folds y ajustes; `describe()` da "Folds: N" en lugar de estadísticas de `fold` (`ask()` envía siempre las filas, así que no le afecta).
- 4c: `ask()` y `describe()` de un `compare()` en que corrió ForecasterStats con una estrategia que no reajusta dicen que se reajustó en cada fold; la clasificación recortada de `ask()` se dice una vez; los marcadores de `describe()` (nuevo en 0.4.0) usan "(first N of M ...)".
- 4d: ninguno (solo tests).

**Tests.**
- Suite completa: de 2802 pasados y 1 omitido en `0.4.x` (2803 con `chronos` instalado, como dice 13.1) a 2891 pasados y 1 omitido, es decir, 89 más.
- Por commit, con `/verify` (tests pasados, más 1 omitido): 2809 (PR 15), 2820 (PR 16), 2842 (PR 17), 2845 (4a), 2868 (4b), 2870 (4c) y 2891 (4d). El mensaje de `1d7c915` dice "2803 -> 2809": la base son 2802 pasados más el omitido.
- Goldens de render: solo cambia `test_render_forecast_foundation_output_when_multi_series_long_format_prediction_mode` (PR 17, dos líneas que parsean las fechas de `exog_future`); se añaden el mismo caso para ForecasterRecursiveMultiSeries y la lectura sin fechas por ruta y en memoria.
- Goldens del LLM: no cambian en los PRs 15, 16 y 17 ni en 4a; en 4b se añade `code_generation_backtest` y cambian dos de `describe()` (`backtest_foundation_multi_series_quantiles` y `backtest_many_series`, "Folds: N"); en 4c cambia uno de `describe()` (`backtest_many_series`, marcadores); en 4d se añaden siete escenarios. Ningún golden de `ask()` existente cambia en la fase.
- Paridad del PR 17 con los datasets de la documentación: h2o (ForecasterRecursive y ForecasterStats), bike_sharing (`users`, `holiday`, `weather`, `temp`), items_sales ancho y largo (`melt`), items_sales largo con una exógena en largo, y store_sales largo (tienda 1, artículos 1 a 5) con y sin exógena en largo. En cada uno, `forecast()` en predicción (con `exog_future.csv` si hay exógenas) y en evaluación, y `backtest()` con el CV de `create_cv()`: el script devuelto por la llamada, ejecutado como fichero, da las mismas predicciones y es idéntico al de `forecast_code()` y `backtest_code()`, 24 de 24. En la base fallan los 24 (leen `'data.csv'`), y con los scripts de `forecast_code()` la predicción en largo con exógenas da otras predicciones.

**Para el check de pago** (no se lanzó en esta fase). Lista completa de lo que cambia en lo que recibe el LLM en esta fase:
- PR 17: la sección `<script>` de un `CodeGenerationResult` lista el fichero que lee el script, así que con un perfil guardado y otra ruta nombra esa ruta (ningún golden lo cubre).
- 4a: la razón del paso de categóricas en `<forecast_plan>` cuando hay más de 15 columnas categóricas.
- 4b: el contexto de un resultado de `backtest_code()` gana `<backtesting_strategy>` y el modo backtesting en `<script>`. "Folds: N" en `<predictions>` solo aparece en `describe()`: `ask()` envía siempre el contexto con `send_data=True` (con `send_data_to_llm=False` solo avisa), así que no entra en el check de pago.
- 4c: la nota de `<backtesting_strategy>` de un `compare()` en que corrió ForecasterStats con otra estrategia, y la frase de la clasificación recortada en `<leaderboard>` (con más de 15 candidatos).
- PRs 15 y 16 y 4d: nada.

Suma con lo pendiente de las secciones anteriores, que no cambia: la regla 4 de `llm/prompts.py` y las explicaciones del plan y del CV (sección 3); las notas de `DataProfile.warnings` de los PRs 6 y 8 (sección 12); y lo de la sección 13 (estrategia y frases de ForecasterStats del PR 9, cotas del PR 13, `llm/context.py` de los PRs 12 y 14, candidatos de datos largos). Una sola ejecución antes de la release, como decidió el autor.

**Preguntas nuevas para el autor.**
1. PR 17: con un DataFrame y un perfil guardado de un fichero, el script carga la ruta del perfil, como en 0.3.1, aunque se ejecutó el DataFrame. ¿Se mantiene (implementado), se escribe el marcador `data.csv` o se avisa?
2. PR 17: un CSV real llamado exactamente `data.csv` (ruta relativa) y sin fechas se confunde con el marcador de datos en memoria y su script falla como en 0.3.1. ¿Basta así, o se añade al perfil un campo que distinga los datos leídos por ruta (cambia el esquema y su JSON)?
3. PR 16: los avisos del plan no aparecen en la tabla del CLI porque el CLI ya los imprime (pregunta menor de 10.10). ¿Se confirma?
4. PR 15: ¿se confirman dos eventos por candidato y la cancelación lanzando una excepción desde el callback, que sale de `compare()` tal cual, como contrato para el PR 19?
5. 4b: el resumen sin datos de las predicciones multiserie sigue sumando las series; ¿un bloque por serie, como 10.5 proponía, en el lote de pago?
6. 4c: "Applied identically to every candidate." sigue cuando corre un candidato que no se entrena (ForecasterFoundation, baseline); la explicación de `compare()` ya lo dice para foundation. ¿Se ajusta también la nota?

**Pendiente o anotado, fuera de esta fase.**
- Las preguntas de arriba y las abiertas de 10.10 y de las secciones 11 a 13.
- `describe()` de un `backtest_code()` con `initial_train_size` de tipo `pd.Timestamp` no cuenta los folds mientras `build_cv_explanation` falle con ese tipo (PR 23).
- El comentario del script de ForecasterStats y foundation ("# Categorical exog excluded (...)") y la línea del perfil de `ask()` siguen nombrando todas las columnas categóricas; 4a solo recorta la razón del paso.
- El backlog de 13.1 sobre el fallo de skforecast con `gap > 0` queda resuelto en origen: está corregido en la rama `0.26.x` de skforecast (comprobado con su punta: h2o, `gap=2`, sin error) y lo incluirá la 0.26.0, aún en desarrollo, así que basta con `skforecast>=0.26.0`. El skforecast instalado en el entorno de la sesión es anterior a la corrección y sigue fallando; se arregla al reinstalarlo desde la rama.

**Qué queda para empezar el servidor (PRs 18 y 19).** Con esta fase entran todos los PRs mínimos (1, 2, 3, 6, 7, 8, 9, 12, 13 y 14 antes del 18; 10, 11 y 15 antes del 19) y los muy recomendables (4, 5, 16 y 17). Para empezar:
- PR 18: la decisión 4 de 12.1 (el MCP reenvía los mensajes tal cual, con un máximo de 5 valores y el límite de tamaño del servidor, y lo dicen el SKILL.md y la documentación del servidor); `values_included=False` significa sin filas, mientras las estadísticas de las predicciones y las métricas sí van (13.1); el tool `profile` rechaza saltos de línea en los nombres (pregunta 4 de 10.10). Siguen abiertas para el autor las preguntas 1 (versión), 12 (valores por defecto del servidor), 13, 14 y 18 de 10.10.
- PR 19: usa `progress_callback` para `Context.report_progress` y la cancelación entre candidatos, y `plan.warnings` junto a la captura de avisos por llamada de 10.2 para los `ToolNotice` de origen `plan`.
- El check de pago, una sola vez antes de la release, con la lista de arriba.

### 14.1 Revisión del autor y correcciones

Antes de mergear la fase 3c, una verificación independiente comparó `0.4.x` antes de la fase (`a253a93`) con la rama, y el autor decidió las preguntas abiertas. Las correcciones van como commits nuevos al final de `feature/mcp-prereqs`; ninguno subido se reescribió.

**Verificación.**
- Ejemplos de la documentación (98 pasos de Python y los comandos del CLI): predicciones, métricas, avisos y scripts idénticos a la base, salvo lo que lista la sección 14.
- PR 17: con rutas absolutas, `Path`, URL, nombres con comillas, espacios o acentos, y perfiles guardados usados con otro fichero, el script devuelto da las mismas predicciones ejecutado desde cualquier directorio; en la base fallaban todos o leían otro fichero. Las rutas relativas se escriben tal cual y fallan con un error claro desde otro directorio (como en 0.3.1); `~` no se expande, en ninguna versión.
- PR 15: sin callback, `compare()` es idéntico a la base; dos eventos por candidato con el total conocido desde el primero; cancelar no deja rastro (barra cerrada, filtros de avisos intactos, el siguiente `compare()` da lo mismo) y solo actúa entre candidatos.
- PR 16: `plan.warnings` coincide con los avisos emitidos en unos 70 casos; sobrevive al JSON y los planes de 0.3.1 cargan.
- 4a a 4d: el contexto de `ask()` solo cambia en lo que lista la sección 14; la lectura del CV desde el script es correcta en 72 combinaciones y nunca ejecuta su código; con 500 columnas `describe()` baja de 24k a 14,4k caracteres como mucho.

**Decisiones del autor.**

| Pregunta | Decisión | Commit |
|---|---|---|
| 1 | Con un DataFrame y un perfil guardado de un fichero, el script escribe el marcador `data.csv`, no la ruta del perfil (que daba otras predicciones sin error) | `5b3a40f` |
| 2 | Un fichero real llamado `data.csv` se registra como `./data.csv`; sin cambiar el esquema | `5b3a40f` |
| 3 | Confirmada: sin panel "Plan Warnings" en la tabla del CLI (ya imprime los avisos; `--format json` los lleva). Revisar con el PR 20 | |
| 4 | Confirmada: dos eventos por candidato y cancelación lanzando una excepción desde el callback, que sale tal cual | |
| 5 | Un bloque por serie en el resumen de predicciones de `describe()`; solo afecta a `describe()` (ver abajo), así que no entra en el check de pago | (pendiente) |
| 6 | Ajustar la nota "Applied identically..." cuando corre ForecasterFoundation, que no se entrena; entra en el check de pago | (pendiente) |

**Otros commits.**
- `a389407`: `ask()` construye siempre su contexto con `send_data=True` (con `send_data_to_llm=False` solo avisa, por diseño), así que el camino `send_data=False` solo lo usa `describe()`. Se corrigen el docstring de `describe()`, `docs/api/schemas/results.md`, dos entradas de las release notes y la lista de pago de la sección 14: "Folds: N" no llega a `ask()` ni entra en el check.
- `89e50eb`: `forecast-code DATA --from-plan` ignoraba `DATA` y escribía la ruta del bundle, a diferencia de `backtest-code` y de la API.
- `9984625`: los scripts de datos sin fechas fallaban ejecutados como fichero (en memoria y `exog_future.csv`, con un índice entero que skforecast rechaza; ya ocurría en 0.3.1). Una línea `pd.RangeIndex(...)` tras la lectura, solo en el bloque de carga del script independiente, los arregla: 5 de 5 casos con las mismas predicciones y posiciones.
- `fb9d791`: una fecha editada a mano que no se lee rompía `describe()` de un `backtest_code()`; "of 1 steps"; el plan copiado por `forecast(plan=..., interval=...)` compartía `warnings` y `forecaster_kwargs` con el original.

**Tests.** De 2891 a 2905 (con `chronos` instalado no hay omitidos).

**Pendiente antes del check de pago.**
- `tools/ai/check_ask_context.py` no recorre casi nada de la lista de pago: añadirle escenarios de ForecasterStats (PR 9 y 4c), un resultado de `backtest_code()` (4b), formato largo (candidatos de 12.1), más de 15 candidatos (4c) y más de 15 columnas categóricas (4a).
- Las preguntas 5 y 6 de arriba.

**Notas para el servidor (PRs 18 y 19).**
- Versión de `mcp`: 10.7 da por verificado `mcp>=2.2,<3`, pero el entorno local tiene `mcp` 1.29.0. Comprobarlo antes del PR 18.
- Progreso (PR 19): el valor debe crecer en cada notificación y el evento `started` repite el `completed` del anterior; usar `progress = 2*completed + (status == 'started')` con `total = 2*total`. Los candidatos excluidos por el presupuesto no generan eventos. Hay tramos largos sin eventos (Foundation al cargar, Stats).
- Cancelación (PR 19): lanzar desde el callback una excepción propia del servidor, que no sea `SkforecastAIError`, activada por un `threading.Event`; solo actúa entre candidatos, y cancelar en el último evento descarta una comparación terminada.
- Hilos: el callback corre en el hilo de trabajo; informar con `anyio.from_thread.run` y no tomar el lock del servidor dentro (bloqueo). El lock único es imprescindible: varios `compare()` simultáneos dejan `sys.stdout` redirigido (también en la base).
- Avisos (PR 18): con los filtros por defecto, llamadas repetidas muestran un aviso una vez, pero cada plan lo lleva; capturar con `simplefilter('always')` y deduplicar contra `plan.warnings` por texto para darles origen `plan`.
- Privacidad: el JSON de los resultados (`model_dump_json`) y `result.code` llevan ahora la ruta absoluta o la URL de los datos (que puede llevar un token). `describe()` no la lleva; decirlo en la documentación del servidor.
- Tamaños: `ask()` y los scripts pueden pasar de 20k caracteres con cientos de columnas (la línea de exógenas categóricas del perfil, `exog = data[[...]]`); `describe()` no. El tool `get_code` necesita su propio límite.
