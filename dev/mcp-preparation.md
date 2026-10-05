# Preparativos para el servidor MCP de skforecast-ai

Estado a 30/09/2026, actualizado el 01/10/2026 con la fase 2 (sección 11) el 02/10/2026 con las fases 3a, 3b y 3c (secciones 12, 13 y 14), con la fase 4, el servidor (sección 16), y el 03/10/2026 con la fase 4b, endurecimiento y distribución del servidor (sección 17). Base: rama `0.4.x`, con la sección 2 commiteada en `f87e89f`. La auditoría de la fase 1 (resultados en las secciones 4, 5, 7 y 9, y propuestas en la 10) está en la rama `feature/mcp-audit` y no toca `skforecast_ai/`. Este documento sirve para retomar el trabajo en otra sesión: qué se decidió, qué está hecho, qué falta y en qué orden, y cómo verificarlo.

**Cómo leerlo.** Las secciones 1 a 8 son el plan original. Cada punto pendiente lleva ahora el resultado de contrastarlo con el código, marcado como **Verificado**, **Corregido** o **Nuevo**. La sección 9 recoge lo que la auditoría encontró fuera de ese plan. La sección 10 propone decisiones y un orden de PRs, y está pendiente de revisión. La sección 11 recoge lo implementado en la fase 2 (PRs 0 a 4) y sus desviaciones respecto a la 10; la sección 12 lo mismo para la fase 3a (PRs 5, 6, 7, 8, 10 y 11), la 13 para la fase 3b (PRs 9, 12, 13 y 14) la 14 para la fase 3c (PRs 15, 16 y 17 y los pendientes de `describe()` de 13.1), la 15 para la fase 3d (cierre del contexto del LLM) la 16 para la fase 4 (el servidor MCP, PRs 18, 19 y 19b) y la 17 para la fase 4b (endurecimiento y distribución del servidor).

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

Salvo los PRs 0 a 4, hechos en la fase 2 (sección 11), los PRs 5, 6, 7, 8, 10 y 11, hechos en la fase 3a (sección 12), los PRs 9, 12, 13 y 14, hechos en la fase 3b (sección 13), los PRs 15, 16 y 17, hechos en la fase 3c (sección 14), y los PRs 18, 19 y 19b, hechos en la fase 4 (sección 16), nada de esta sección está implementado: es una propuesta para revisar. Los números de PR remiten a la tabla de 10.8.

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

### 10.12 Fase 6: rendimiento y limpieza (antes del check de pago)

Última fase antes de la release, después de los overrides (PRs 30 a 38). Cada fase añadió comprobaciones (el perfil ordena filas y lee fechas como texto, `forecast()` valida la última ventana y las exógenas futuras, cada método revalida el plan, el servidor calcula la huella del CSV antes y después de cada llamada) y ninguna midió su coste. El tiempo grande es de skforecast al ajustar modelos, así que lo que se busca es un cuello de botella inesperado en el código propio y los restos que dejaron las fases, no grandes mejoras.

- **Medir primero, por función** (`cProfile` o `pyinstrument`): cada llamada pública (`profile`, `plan`, `forecast`, `backtest`, `compare` y los tools del servidor) con datos pequeños, medianos y grandes (h2o, bike_sharing, store_sales con 913 mil filas). Se informa de la parte del tiempo que es código propio frente a skforecast, pandas y el estimador.
- **Después, línea a línea** (`line_profiler`), solo en las funciones propias que señale el paso anterior.
- **También:** `python -X importtime` (importación y arranque del servidor) y la memoria de `profile()` en store_sales.
- **Optimizar solo lo medido:** código propio por encima del 10 % de una llamada, o un coste que crece con el tamaño de los datos sin necesidad. Ya anotado en la sección 18: `validate_series_lengths` calcula `_series_spans` otra vez, y un perfil guardado se vuelve a perfilar en cada llamada (dos veces si los datos cambiaron).
- **Limpieza:** código muerto y duplicados que quedaron entre fases (conjuntos de forecasters repetidos, helpers pequeños en varios módulos, las dos tablas de periodos estacionales de la pregunta 5 de la sección 18). Sin reorganizar los ficheros grandes (`assistant.py`, `mcp/server.py`): eso es para la 0.5.0.
- **Regla:** todo se comporta igual. Goldens de render y de contexto idénticos byte a byte, predicciones idénticas en los conjuntos de paridad, ningún cambio de API ni de mensajes. Si algo cambia, se para.
- **Opcional:** comparar tiempos con la v0.3.1 como caja negra, solo si corre sin esfuerzo (apunta a skforecast 0.25 y el código cambió mucho).

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

## 15. Fase 3d: hecho

Cierre del contexto del LLM antes del servidor, en la rama `fix/describe-closing`, creada desde `0.4.x` (`73c5cde`). Hecha en una sesión local, un commit por punto.

| Commit | Contenido |
|---|---|
| `fd30ed1` | Pregunta 5 de 14.1: el resumen de predicciones de `describe()` añade el bloque por serie (las 5 primeras) que ya daba `ask()`; solo cambian 5 goldens de `describe()`, ninguno de `ask()` |
| `3113be9` | Pregunta 6: la nota de la estrategia compartida de `compare()` nombra a ForecasterFoundation, que no se entrena, junto a la excepción de ForecasterStats |
| `689186b` | Encontrado al añadir escenarios: valores de numpy en `estimator_kwargs` (por ejemplo de `np.logspace`) se escribían como `np.float64(...)` en un script sin numpy y fallaban con `NameError`, y el plan no se podía guardar en JSON (también en 0.3.1). El validador de `ForecastPlan` los convierte en valores de Python |
| `20bba94` | `check_ask_context.py` cubre la lista de pago: datasets `items_sales_long` y `h2o`, y los escenarios `backtest_code`, `stats_backtest`, `compare_default`, `compare_many` y `many_categorical` |
| `1edd266` | El hook de Bash ya no comprueba como comandos las líneas de un heredoc (bloqueaba un README que citaba `check_ask_context.py`) |

**Decisiones del autor para 0.4.0 (preguntas de 10.10).**
- Pregunta 1: el servidor y el lote de overrides (PRs 30 a 38) salen en 0.4.0. El check de pago se lanza una sola vez, al final, cuando hayan entrado todos los PRs de pago (también los overrides).
- Pregunta 12: los valores por defecto del servidor de 10.7.
- Preguntas 13 y 14: candidatos inválidos como fallos; errores como `ToolError` con JSON.
- Pregunta 18: el SKILL.md vive en skforecast-ai, dentro del paquete y en la documentación.

**Para el check de pago.** Esta fase añade a la lista la nota de ForecasterFoundation en `<backtesting_strategy>` (pregunta 6). La pregunta 5 solo afecta a `describe()`. Antes de lanzarlo, ejecutar los cuatro datasets de `check_ask_context.py` (ver su README).

**Tests.** De 2905 a 2907. `mcp` 2.2.0 está en PyPI, como asume 10.7; el entorno local tiene 1.29.0, instalado antes, y hay que actualizarlo para probar el servidor en local.

**Siguiente:** la fase 4, el servidor (PRs 18, 19 y 19b), y después los PRs 20 a 38 de 0.4.0.

## 16. Fase 4: hecho

El servidor MCP: los PRs 18, 19 y 19b de la tabla 10.8, en ese orden, en la rama `feature/mcp-server`, creada desde `0.4.x` (`766618b`, que ya incluye la fase 3d). Un commit por PR, cada uno con su código, sus tests, su documentación y su entrada en `docs/releases/releases.md` (0.4.0), y cada uno subido al terminar; cualquier prefijo de la rama se puede mergear. Un último commit añade esta sección. Antes de cada commit se pasaron `/verify` (lint, tests afectados, suite completa con los tests lentos y build de la documentación), el subagente `conventions-reviewer`, `/code-review` y `/security-review`; lo que encontraron se corrigió antes de subir el commit. Ningún commit subido se reescribió; el del PR 19b corrige una frase de la referencia del PR 18 (abajo). El núcleo en Python no cambia en ningún commit: el servidor es una capa sobre `ForecastingAssistant()` sin LLM, y ni los scripts generados, ni los goldens de render o del LLM, ni `llm/context.py`, `llm/prompts.py` o las explicaciones cambian, así que la fase no añade nada al check de pago.

Decisiones del autor aplicadas (10.10, 12.1, 13.1 y 15):
- pregunta 1: el servidor sale en 0.4.0 con el lote de overrides; el check de pago, una sola vez al final;
- pregunta 12: los valores por defecto de 10.7 (`--allow-dir` obligatorio, salida en un directorio temporal, 256 objetos y 1 GB, URLs rechazadas, descargas de Hugging Face documentadas con `HF_HUB_OFFLINE`, `mcp` en `all`, `full` y `dev`, comando `skforecast-ai mcp`);
- preguntas 13 y 14: los candidatos inválidos de `compare` son fallos, como en Python, y los errores salen como `ToolError` con el JSON `{code, message, field, hint, details}`;
- pregunta 18: el SKILL.md vive en skforecast-ai, dentro del paquete y en la documentación;
- pregunta 4 de 12.1: los mensajes y los avisos se reenvían tal cual (el núcleo ya muestra como mucho 5 valores), con el límite de tamaño del servidor; el SKILL.md y la guía lo dicen;
- 13.1 y 14.1: `values_included=False` significa sin filas, y las estadísticas de las predicciones y las métricas sí van; el JSON de los resultados y los scripts llevan la ruta de los datos, el resumen no, salvo el de un plan: es el `describe()` de su script (10.5), cuya sección `<script>` lista el fichero que lee (PR 17). El servidor no lo quita (la ruta la pasó el propio agente) y la referencia, la guía y el SKILL.md lo dicen;
- pregunta 4 de 10.10: el tool `profile` rechaza nombres con saltos de línea;
- `compare` sin `metric` en esta fase (10.7).

| Commit | PR | Contenido |
|---|---|---|
| `1f1a745` | 18 | Base del servidor y tools de planificación |
| `a44734d` | 19 | Tools de ejecución, ficheros de salida, progreso y cancelación |
| `add4600` | 19b | SKILL.md para agentes y guía de usuario del servidor |

**Qué cubre cada commit.**
- PR 18: subpaquete `skforecast_ai/mcp/` (`server`, `_store`, `_inputs`, `_errors`, `_runtime`, `models`), comando `skforecast-ai mcp` (importa `mcp` dentro del comando; sin el extra sale con código 1 y dice qué instalar), extra `mcp` (`mcp>=2.2,<3`, también en `all` y en `test`) y los tools `profile`, `plan`, `refine_plan`, `create_cv`, `get_code`, `list_objects` y `describe_object`.
  - Store: ids `kind-seq-token` con un token por proceso; LRU por número de objetos y por memoria estimada, que siempre conserva el último; un id eliminado, de otra ejecución o inexistente da `unknown_id` diciendo cuál; un id de otro tipo, `invalid_argument`. Las entradas no cambian y guardan referencias directas al perfil del que vienen.
  - Entradas: rutas absolutas `.csv` dentro de `--allow-dir`, comprobadas sobre la ruta escrita antes de mirar el sistema de ficheros y otra vez tras resolver los enlaces; ninguna URL (cualquier `scheme://`); sha256 antes y después de perfilar (`data_changed`); los textos numéricos en `initial_train_size` se rechazan; `profile` rechaza nombres de columna y, en formato largo, ids de serie con caracteres de las categorías Cc, Zl y Zp.
  - Errores: `ToolError` con el JSON, códigos del núcleo más `unknown_id`, `invalid_path`, `path_not_allowed`, `url_not_allowed` y `data_changed`; campos renombrados (`data` a `data_path`, `profile` a `profile_id`, etc., y las claves de `refine_plan` a `overrides.<clave>`); mensaje de 4.000 caracteres, pista de 1.000 y textos de `details` de 500.
  - Avisos: por llamada, dentro del lock, con `simplefilter('always')`, solo los del hilo de trabajo; deduplicados por (categoría, texto), sin la línea "You can suppress..." de skforecast, sin `CandidateFailedWarning` y con los de obsolescencia al log; origen `plan` si el texto está en `plan.warnings`, `data` en `profile` (y para los mismos textos en llamadas posteriores), `runtime` en otro caso; 20 avisos de 1.000 caracteres con el recuento de omitidos.
  - Sobre `ToolResult {id, kind, links, summary, summary_truncated, notices, notices_omitted, files, values_included=False, cost, changeable}`; el resumen es `describe()` (el de un plan, `forecast_code(profile, plan).describe()`), de 20.000 caracteres como mucho con el texto completo en un fichero; `cost` (`n_folds`, `n_fits`, `estimator_fits` con `count_estimator_fits`) y `changeable` (argumentos de `refine_plan` o de `create_cv`) son el coste y "lo que se puede cambiar" de 10.5.
- PR 19: tools `backtest(cv_id, plan_id=None)`, `compare(cv_id, candidates, interval, baseline)`, `forecast(plan_id, test_size, exog_path)` y `get_failure`, y `candidate` en `get_code`.
  - Antes de leer el CSV otra vez se comprueba de nuevo la ruta y que su sha256 sea el del perfil (`data_changed` si cambió desde que se perfiló); después de la ejecución, otra vez, también el de `exog_path` (leído con `load_exog`, como `--exog` del CLI).
  - Predicciones, métricas y la clasificación van a CSV en el directorio de salida; los resúmenes, scripts y fallos largos se escriben una vez, al crear el objeto; una llamada cancelada borra los ficheros que escribió.
  - `compare`: progreso `2*completed + started` sobre `2*total` (monótono) enviado con `anyio.from_thread.run` sin tomar ningún lock; cancelación cooperativa con un `threading.Event` y una excepción propia (`CallCancelled`, que no es `SkforecastAIError`) lanzada desde el `progress_callback`; el plan del ganador se registra (`links.best_plan_id`); `cost.estimator_fits` suma los candidatos que se ejecutaron, cada uno con su estrategia.
  - Fallos: un `ForecastExecutionError` o un `AllCandidatesFailedError` guarda su traceback y su código con un id (`details.failure_id`), y los candidatos fallidos de una comparación guardan los suyos; `get_failure` los devuelve, nunca el error.
  - El plan de una evaluación (con `end_train`) nunca se registra como plan.
- PR 19b: `skforecast_ai/mcp/skills/skforecast-ai-forecasting/SKILL.md` (estándar Agent Skills, en los datos del paquete), escrito para el agente que llama al servidor: el flujo, la escala de confianza (comparación contra la referencia, backtest, evaluación de una ventana, predicción del futuro), el coste (`cost` de `create_cv` para un plan, la suma de los candidatos en `compare`, `LongTrainingWarning` por encima de 50 ajustes del estimador, `compare` sin candidatos deja fuera los de más de 500, `refit=false` no ayuda a ForecasterStats), las fechas ISO 8601, las respuestas, los códigos de error y la privacidad; la guía `docs/user-guides/mcp-server.md` (cómo arrancarlo y conectarlo a Claude Code, Claude Desktop y Cursor, el skill, una sesión, errores, qué ve el agente, seguridad y límites), que incluye el SKILL.md entero con `pymdownx.snippets`; enlaces desde la guía del CLI, la referencia y la nota de versión.
  - Decisión 4 de 12.1: el SKILL.md y la guía dicen que los mensajes y avisos se reenvían como los escribe la librería, con 5 valores como mucho, y dan los límites de tamaño del servidor (mensaje de 4.000 caracteres, pista de 1.000, textos de `details` de 500, 20 avisos de 1.000 con `notices_omitted`, 200 para la primera línea de un error inesperado). 13.1 y 14.1: `values_included=False` significa sin filas, y los resúmenes de un backtest o un forecast llevan las métricas y estadísticas de las predicciones, y el de una comparación la clasificación.
  - Corrección del PR 18: su referencia decía que ningún resumen nombra la ruta de los datos; el de un plan sí la nombra (arriba).
  - `test_skill_md.py` comprueba el front matter (la regla de nombres de Agent Skills), que el SKILL.md llama a cada tool del servidor y nombra cada código de error que puede devolver y cada argumento permitido de foundation, que los límites que dan el SKILL.md y la guía son las constantes del servidor y del núcleo, y que el SKILL.md está en los datos del paquete, no tiene rayas y se incluye en la guía.

**API de `mcp` usada** (2.2.0 instalada; comprobada en el código del paquete antes de escribir el servidor, como pedía 14.1, que dudaba de la versión):
- `mcp.server.mcpserver.MCPServer(name, title, instructions, version, tools=[...])` y `MCPServer.run("stdio")`, que desvía el fd 1 a stderr mientras sirve;
- `mcp.server.mcpserver.tools.Tool.from_function` y `Tool.run`, subclase `_StrictTool`; `mcp.server.mcpserver.utilities.func_metadata.FuncMetadata`, subclase `_StrictFuncMetadata`;
- `mcp.server.mcpserver.Context` (inyectado en `compare`) y `Context.report_progress`;
- `mcp.server.mcpserver.exceptions.ToolError` y `UnexpectedToolError`; `mcp.types.ToolAnnotations`;
- en los tests, `mcp.Client(server)` en memoria (sin red ni modelos), `mcp.Client(StdioServerParameters(...))` para la integración por stdio, y `call_tool(..., progress_callback=...)`; la cancelación del cliente (un `CancelScope`) llega al servidor en memoria y por stdio (`notifications/cancelled`).

**Desviaciones respecto a 10.7, con su motivo.**
- Lock: 10.7 nombraba un `anyio.Lock`. Hay un `threading.Lock` por proceso que toma el propio hilo de trabajo (14.1: un único lock por proceso; lo comparten todos los servidores y bucles de eventos, y una llamada cancelada lo conserva hasta que su hilo termina) y un `anyio.Lock` por bucle de eventos (en un `RunVar`, porque un lock de anyio no puede cruzar bucles) que deja pasar una llamada cada vez al hilo, para que las que esperan no ocupen los hilos de anyio que el transporte stdio necesita (lo encontró `/code-review`).
- El SDK ignora los argumentos desconocidos y convierte tipos: `_StrictTool` rechaza los desconocidos y no convierte nada (`extra='forbid'`, `strict=True`), así que `compare(metric=...)` es un error en vez de clasificar en silencio con otra métrica. El SDK decodificaba cualquier texto JSON en un argumento que no fuera exactamente `str` (`'null'` pasaba a None): `_StrictFuncMetadata` solo decodifica listas y objetos, y solo en argumentos que no aceptan texto. Los errores de argumentos del SDK salen con el JSON de los demás.
- El texto de un `ToolError` llega al agente con el prefijo "Error executing tool <name>: " delante del JSON; se documenta.
- `create_cv`: los límites que comprueba `TimeSeriesFold` (`gap >= 0`, `fold_stride`, `initial_train_size` y `skip_folds >= 1`, `refit >= 0`) van en el esquema, para que salgan como `invalid_argument` y no como error interno de skforecast.
- Modelos foundation (encontrado por `/security-review` en el PR 18, como nota para el PR 19): los adaptadores de skforecast aceptan `estimator_kwargs` que sacan los datos de la máquina (TabPFN `mode='client'`) o descargan ficheros (TSICL `checkpoint_version`), y el núcleo los pasa todos. El servidor solo acepta `context_length`, `cross_learning`, `point_estimate`, `max_horizon`, `add_calendar_features` y `n_fourier_terms`, comprobados al construir un plan o un candidato y otra vez antes de ejecutar (criterio 1; el núcleo no cambia, pregunta abajo).
- `data_changed` también cuando el fichero cambió desde que se perfiló (10.7 solo pedía antes y después de cada llamada): el perfil y los objetos ya no lo describirían.
- El directorio de salida temporal se conserva al parar el servidor (contiene lo que el servidor escribió para el usuario), y su ruta va al log.
- `metrics_summary` (10.7): el servidor no calcula ninguno; las métricas van en el resumen y en el CSV.
- Ficheros: además de 10.7, los fallos largos y los scripts largos se escriben en el directorio de salida; los nombres solo llevan ids y posiciones, nunca nombres que elige el agente.

**Tests.** De 2903 pasados (más 1 omitido) en `0.4.x` a 3146 (más 1 omitido): 3074 tras el PR 18, 3126 tras el 19 y 3146 tras el 19b, con los tests lentos, medidos en la sesión en la nube con `pytest -n auto`. Todo con el `Client` en memoria, sin red ni modelos, salvo las integraciones por stdio (marcadas como lentas, con el servidor en otro proceso) y la de paridad (lenta). Cubren la deriva de esquemas (golden de los tools), rutas, store, errores, avisos, el runtime (sin solapes, avisos aislados, `sys.stdout` restaurado, cancelación esperando el turno, borrado de ficheros), cada tool contra la API de Python, que ningún tool modifica objetos registrados, concurrencia de perfiles y de ejecuciones, progreso, cancelación entre candidatos (determinista: el primer candidato espera a que el cliente cancele) y por stdio, una regresión de seguridad por vector (URL nunca pedida a un servidor local que crearía el marcador; rutas con `..`, absolutas, enlaces simbólicos y relativas para `data_path` y `exog_path`; cargas de inyección en cada argumento, en los nombres, en el nombre del fichero y en los valores, ejecutadas por `forecast`, `backtest` y `compare` y como script sin crear el marcador; la lista de argumentos de foundation), el comando del CLI, el import sin el extra y el SKILL.md.

**Paridad de extremo a extremo.** Con los datasets de skforecast descargados (h2o; bike_sharing horario con `users` y las exógenas `holiday`, `weather` y `temp`, con las últimas 24 horas como fichero de exógenas futuras; items_sales ancho; items_sales largo con `melt`), el flujo profile, plan, create_cv, backtest, compare (candidatos por defecto, eventos de progreso monótonos), forecast del mejor plan (con `exog_path` en bike_sharing) y una evaluación, por el servidor, da los mismos resúmenes, predicciones, métricas y clasificaciones que la API de Python (los CSV byte a byte), 4 de 4; y los scripts de `get_code` del backtest, del forecast y de la evaluación, ejecutados como fichero en un intérprete nuevo, reproducen las predicciones, 12 de 12. El mismo flujo con candidatos explícitos sobre las fixtures sin red (h2o, items_sales largo y ancho) es el test lento `test_integration_parity`.

**Preguntas nuevas para el autor.**
1. Argumentos de los modelos foundation: el servidor solo deja pasar seis. ¿Debe el núcleo validar los nombres de los `estimator_kwargs` de foundation (pendiente de 10.11) y rechazar los que sacan los datos de la máquina, como `mode='client'` de TabPFN, también en Python? Cambia el comportamiento del núcleo.
2. Un error que skforecast-ai no lanzó (`internal_error`) lleva la primera línea de su mensaje, que puede citar un valor de los datos (por ejemplo "could not convert string to float: '...'"). Se reenvía como dice la decisión 4 de 12.1. ¿Basta, o el servidor debe enviar solo el tipo en esos errores?
3. Tamaño máximo del CSV: 10.10 lo listaba en la pregunta 12, y los valores de 10.7 no tienen ninguno, así que no hay límite. ¿Se añade una opción?
4. El directorio de salida temporal se conserva al parar el servidor. ¿Se confirma, o se borra al salir (perdiendo los CSV que el usuario no haya copiado)?
5. `data_changed` cuando el CSV cambió desde que se perfiló: en Python, un perfil guardado con datos nuevos funciona (y el PR 27 propone refrescarlo con una nota). ¿Se mantiene el error en el servidor?
6. El script de un forecast con `exog_path` lee `exog_future.csv` (pregunta menor de 10.10). Por el servidor es más visible: ¿se prioriza que el script lea la ruta real?
7. Progreso y cancelación solo en `compare`: un `backtest` largo (o un único candidato Auto-ARIMA) no informa ni se puede parar, y no hay timeout (10.7). ¿Basta para 0.4.0?
8. `<` y `>` en los nombres (segunda parte de la pregunta 4 de 10.10) siguen aceptados.
9. El SKILL.md se copia a mano (la guía da la línea que lo encuentra en la instalación). ¿Lo sirve también el servidor (un recurso o un prompt de MCP), o lo instala un comando del CLI (`skforecast-ai mcp --install-skill DIR`)? Se dejó fuera porque escribiría en el proyecto del usuario o añadiría superficie al servidor.

**Pendiente o anotado.**
- Los PRs 23 (que envuelve los errores de `TimeSeriesFold` y de lectura) y 27 reducirán los `internal_error` que hoy llegan al agente; el PR 31 (override `metric`) añade `metric` a `compare`.
- Los overrides de los PRs 30 a 38 llegan solos a `refine_plan` y a los candidatos de `compare`, porque sus modelos son subclases de `RefinePlanOverrides` y `CandidateConfig` (cambiará el golden de los esquemas); `plan` y `create_cv` necesitan sus argumentos nuevos a mano, y el SKILL.md y la guía, sus frases.
- Los registros de MCP con "skforecast" en el nombre (pregunta 12) y la presentación desde skforecast (sección 1) quedan para el autor.

**Qué queda para 0.4.0.**
- PRs 20 a 29: avisos y errores del CLI (20, 21), reemitir los avisos del script (22), comprobaciones tempranas (23), planes que no pueden ejecutarse (24), partición de evaluación (25), coherencia de `CVResult`, plan y `end_train` (26), datos frente a perfil guardado (27), estacionalidad con frecuencias ancladas (28) y el alias `result` de `ask()` (29).
- PRs 30 a 38: overrides (`overridden_fields`, `metric`, `use_exog`, `differentiation`, `calendar_features`, `target_transformer`, `dropna_from_series`), avisos del plan en el contexto, límites de `describe()` en `ask()` (opcional), paridad del CLI y `profile(exog_columns=...)`; con cada uno, su exposición en el servidor.
- El check de pago, una sola vez al final, con la lista de las secciones 3, 12, 13, 14 y 15 más lo que añadan los PRs 30 a 36. Esta fase no añade nada.

**Siguiente:** los PRs 20 a 38 de 0.4.0 y, al final, el check de pago.

## 17. Fase 4b: hecho

Endurecimiento y distribución del servidor MCP, con los hallazgos de la verificación independiente de la fase 4 (PR #35, sin nada bloqueante) y las decisiones del autor, en la rama `fix/mcp-hardening`, creada desde `0.4.x` (`396c7e6`, que ya incluye `feature/mcp-server`). Un commit por punto, en el orden pedido, cada uno con su código, sus tests, su documentación y, si se ve, su entrada en `docs/releases/releases.md` (0.4.0), y cada uno subido al terminar; cualquier prefijo de la rama se puede mergear. Antes de cada commit se pasaron `/verify` (lint, tests afectados, suite completa con los lentos y build de la documentación), el subagente `conventions-reviewer` y `/code-review`, y en los puntos 1, 2, 3 y 5 también `/security-review` (sin hallazgos en ninguno); lo que encontraron se corrigió antes de subir el commit. Ningún commit subido se reescribió y ninguno necesitó una corrección posterior. Cada mensaje de commit lleva su lista "Cambios para el usuario" y las elecciones conservadoras con su criterio de la sección 10.

El núcleo en Python no cambia salvo `skforecast_ai/__main__.py` (nuevo) y la guarda `__main__` de `cli.py`, más dos opciones del comando `mcp` de `cli.py` (abajo). Ni los scripts generados, ni los goldens de render o del LLM, ni `llm/context.py`, `llm/prompts.py` o las explicaciones cambian, así que la fase no añade nada al check de pago. El golden de los esquemas de los tools (`tests/tests_mcp/golden/tool_schemas.json`) cambia en los puntos 1 y 7, a propósito.

| Commit | Punto | Contenido |
|---|---|---|
| `3e32ae6` | 1 | Modelos foundation: `--allow-model`, `model_not_allowed` y aviso de descarga |
| `11f7292` | 2 | `internal_error` solo con el tipo y un id; el mensaje y el traceback, al log |
| `d17b1d9` | 3 | `--max-file-mb` (`file_too_large`) y `steps` no mayor que la serie más larga |
| `c22f63d` | 4 | Progreso cada 5 s mientras corre una llamada |
| `08f2ddc` | 5 | Arranque y parada: directorio de salida, `python -m`, desconexión del cliente, log de una línea |
| `f172d3c` | 6 | Avisos de los datos y del plan, intervalo de `compare`, coste en `create_cv`, `missing_dependency` |
| `937083b` | 7 | SKILL.md, instrucciones del servidor y esquemas de los tools |
| `78dac0d` | 8 | Plugin de Claude Code, guía con pestañas y README |
| `dddd24f` | 9 | Entrada de 0.4.0 del servidor, más corta |

**Qué cubre cada commit.**
- Punto 1 (`skforecast_ai/mcp/_foundation.py`, nuevo):
  - Por defecto el servidor solo ejecuta los modelos de ForecasterFoundation cuya información de skforecast (`list_adapters()`, `get_model_info()`) no tiene `license_restriction` ni `requires_hf_auth`: hoy Chronos-2, TimesFM 2.5, TabICL y Nori. La lista se deriva de esa información (`permissive_adapters()`, `restricted_adapters()`); un test fija cuáles son hoy.
  - TimesFM 3.0, Moirai, TabPFN, t0 y TS-ICL solo con `--allow-model PREFIJO` (repetible; `create_server(allow_models=...)`). Sin ella, `plan` (`field='estimator'`), `refine_plan` (`overrides.estimator`) y `compare` (`candidates[i].config.estimator`, antes de correr ningún candidato) devuelven `model_not_allowed`, con la licencia en el mensaje y en `details` y una pista que dice qué `--allow-model` pedir al usuario; `backtest` y `forecast` lo comprueban otra vez antes de ejecutar. La lista blanca de los seis `estimator_kwargs` se mantiene.
  - La primera vez que un plan, o un candidato cuyo script corrió, usa un modelo sin pesos en la caché local de Hugging Face, la respuesta lleva un `ModelDownloadNotice` (source `plan`) con su licencia, una vez por modelo y servidor; con `HF_HUB_OFFLINE` dice que la ejecución fallará. Va delante de los avisos, así que el límite de 20 nunca lo deja fuera.
  - Regresiones: una por cada modelo restringido y por cada vía (plan, refine_plan y compare), y otra que comprueba que `--allow-model` los permite y que el prefijo de otro modelo no.
- Punto 2: un error que no lanzaron ni el servidor ni skforecast-ai llega al agente como `internal_error` con `details.error_type` y `details.error_id` (aleatorio) y una pista; el mensaje completo y el traceback van al log del servidor (stderr) con ese id. Se decide por el tipo, no por el código: un `SkforecastAIError`, un `ServerError` (llamada cancelada) o un `ValidationError` conservan su mensaje. Los códigos del núcleo no cambian.
- Punto 3:
  - `--max-file-mb` (256 por defecto, 0 sin límite) se comprueba con `os.path.getsize` sobre la ruta ya resuelta y permitida, antes de calcular su sha256 o leerla: los datos en `profile` y el fichero de exógenas en `forecast` (`file_too_large`, con el tamaño y el límite en `details`).
  - En el servidor, `plan` y `refine_plan` rechazan como `invalid_argument` un `steps` mayor que la longitud de la serie más larga del perfil (con `details.longest_series`).
- Punto 4: mientras el hilo de trabajo está ocupado, cualquier tool que ejecuta el núcleo (profile, plan, refine_plan, create_cv, backtest, compare, forecast) envía cada 5 s (`HEARTBEAT_SECONDS`) una notificación de progreso si la llamada trae progressToken (sin él, el SDK no envía nada). `k` notificaciones después de un evento real de progreso `p` envían `p + k/(k+1)`: crecen sin alcanzar el siguiente evento (desde 0 y sin total en una llamada sin eventos). El mensaje dice qué corre y cuánto lleva: el forecaster de un backtest o un forecast, el candidato de una comparación ("ForecasterStats: running (35 s)"). La documentación y el SKILL.md dicen que cancelar espera a que termine el candidato o el backtest en curso y que, mientras, solo responden los tools de lectura.
- Punto 5:
  - `create_server` comprueba que puede escribir en el directorio de salida (un fichero temporal con `O_EXCL`); si no, `InvalidInputError` y el CLI sale con 1.
  - `python -m skforecast_ai` (nuevo `__main__.py`) y `python -m skforecast_ai.cli` ejecutan el CLI.
  - Si el cliente se desconecta durante una ejecución, `run_server` reconoce la desconexión (BrokenPipeError, ConnectionResetError y los recursos rotos o cerrados de anyio, solos o como todas las hojas de un grupo), escribe una línea en el log, apunta la salida estándar a `/dev/null` y vuelve: el proceso sale con 0 sin el traceback.
  - Mientras sirve, el logger `skforecast_ai.mcp` escribe líneas simples en stderr y no propaga (el SDK configura un RichHandler que partía la línea del directorio de salida); se restaura al volver.
- Punto 6:
  - `profile.data_profile.warnings` llega como notices (source `data`, categoría `DataProfileWarning`); un plan (también el de `refine_plan` y el ganador de `compare`) los lleva otra vez, con cualquier texto de `plan.warnings` que la llamada no emitió (source `plan`, categoría `PlanWarning`).
  - `compare` sin `interval` usa el del plan del CV.
  - `create_cv` emite, con `warn_long_training` del núcleo, el `LongTrainingWarning` que emitirá el backtest (más de 50 ajustes del estimador).
  - `backtest` y `forecast` de un plan de ForecasterFoundation cuyo backend no está instalado devuelven `missing_dependency` antes de ejecutar, con un solo consejo: `pip install "<paquete>"` en el entorno del servidor o `--with "<paquete>"` en el comando de uvx, como dice la guía.
- Punto 7:
  - SKILL.md: el caso sin baseline (métricas por serie de `files.best_metrics`, MASE por debajo de 1, la peor serie no está en el resumen); los problemas del CSV (informar y, solo con permiso, una copia corregida dentro del directorio permitido, nunca sobrescribir); los modelos foundation (el de por defecto, licencia y tamaño propios, decírselo al usuario antes); `test_size` como fracción; qué ejecuta `compare` sin candidatos; los nombres de Python en los mensajes.
  - Las `instructions` del servidor llevan seis reglas: escala de confianza con el caso sin baseline, coste, avisos, intervalo de `compare`, no tocar los datos sin permiso y modelos foundation.
  - Esquemas: `refine_plan.overrides` y los candidatos son TypedDicts del servidor con una descripción por clave y sin texto de docstrings (un test compara sus claves con `RefinePlanOverrides` y `CandidateConfig`); `forecaster` es un enum comprobado contra `FORECASTER_TASK_TYPES`; la descripción de `estimator` sale de `SUPPORTED_ESTIMATORS` y de los prefijos de skforecast; `steps` con mínimo 1 e `interval` con dos elementos; los valores por defecto de `create_cv`; `skip_folds` numerado desde 0, con los de la lista desde 1; los dos nombres reservados del baseline; `get_failure` de solo lectura.
  - `values_included=False` significa sin filas de los datos ni de las predicciones; los resúmenes sí llevan métricas y clasificación. Se corrigen el SKILL.md, la guía, la referencia y los docstrings de `ToolResult` y `FailureResult`, y las frases que decían que los fallos y el JSON nombran la ruta de los datos: solo la nombran los scripts de `get_code` y el resumen de un plan (comprobado: el código de un fallo lee los datos en memoria).
- Punto 8:
  - `.claude-plugin/marketplace.json` (marketplace "skforecast-ai", un plugin con source `./plugin`), `plugin/.claude-plugin/plugin.json`, `plugin/.mcp.json` (`uvx --from "skforecast-ai[mcp]==0.4.0" skforecast-ai mcp --allow-dir ${CLAUDE_PROJECT_DIR}`) y `plugin/skills/skforecast-ai-forecasting/SKILL.md`, copia byte a byte del del paquete, que sigue siendo la fuente. `tests/test_plugin_distribution.py` comprueba la copia y que `__version__`, plugin.json, el marketplace (y su entrada) y el pin de `.mcp.json` son la versión de pyproject. `AGENTS.md` lista `plugin/`.
  - Comprobado en la sesión (Claude Code 2.1.288): `claude plugin validate --strict` pasa con los dos manifiestos; `${CLAUDE_PROJECT_DIR}` se expande en el `.mcp.json` de un plugin (un servidor de prueba escribió el valor recibido: el directorio del proyecto); el plugin, apuntando a este checkout con la caché caliente, conecta (`claude --plugin-dir ... mcp list`: Connected); `claude mcp add -s user NOMBRE -e K=V -- CMD ...` escribe la configuración esperada; el primer arranque de `uvx` tarda unos 60 s y los siguientes unos 2 s.
  - Guía con pestañas: Claude Code (los dos comandos `/plugin`, requiere uv, precalentar con la versión del plugin, y un servidor añadido a mano para otras opciones); Cursor, Codex y otros (`npx skills add ... --skill skforecast-ai-forecasting` más el fragmento de `.cursor/mcp.json`, `~/.codex/config.toml` y `claude mcp add -s user`); pip o pipx con copia manual del skill. Después, el comando para precalentar uvx, que `--allow-dir` debe ser absoluto y `--allow-model` y `HF_HUB_OFFLINE` en la configuración del cliente. El README menciona el servidor y enlaza la guía.
- Punto 9: la entrada de 0.4.0 del servidor dice lo que nota el usuario (qué es, cómo se instala, que las respuestas nunca llevan filas de los datos, las opciones `--allow-dir`, `--max-file-mb` y `--allow-model`, el skill y la guía), con el enlace a la PR #35. `python -m skforecast_ai` tiene su propia entrada, porque es del CLI.

**Desviaciones, con su motivo.**
- `cli.py`: además de la guarda `__main__`, el comando `mcp` gana `--allow-model` y `--max-file-mb`. Es el comando del servidor, añadido en la fase 4, y los puntos 1 y 3 piden esas opciones; ningún otro comando cambia.
- Punto 1:
  - Un prefijo de `--allow-model` debe empezar por el prefijo de un adaptador de skforecast (`google/timesfm-3.0`, o un id completo), para que una opción nunca abra varias familias (`google/` se rechaza al arrancar). Criterio 1.
  - Un id de modelo que skforecast no sirve se deja al núcleo: en `compare` el candidato sigue fallando y quedando el último, como en Python (criterio 3).
  - La caché se comprueba como `huggingface_hub` la localiza (`HF_HUB_CACHE`, `HF_HOME`...), sin importarlo, buscando `models--owner--name/snapshots`. Para un adaptador cuyos pesos están en otro repositorio que su id, el aviso puede salir una vez sin hacer falta (pregunta abajo). El aviso no imprime la ruta de la caché, que lleva el directorio del usuario.
  - En `compare` el aviso solo sale para los candidatos cuyo script corrió (también si después fallaron); con `all_candidates_failed` no hay respuesta que lo lleve.
- Punto 3: un fichero de datos que creció por encima del límite después de perfilarse es `data_changed`, sin leerlo, y no `file_too_large` (lo encontró `/code-review`: `backtest`, `compare` y `forecast` no toman una ruta, así que el agente no podría pasar otra). `/code-review` señaló también que el núcleo predice un `steps` mayor que la serie (`forecast` da 300 pasos con 204 observaciones); la regla se aplica igual porque es la decisión del autor, y queda como pregunta.
- Punto 4: el latido va en todos los tools que ejecutan el núcleo, no solo en backtest, forecast y compare (un `profile` de un fichero grande también tarda). Una revisión encontró una carrera: un latido calculado sobre un evento aún no enviado hacía descartar ese evento por no crecer. Un evento pasa a ser la base de los latidos solo en el bucle de eventos, ya registrado como enviado. Tras el último evento de una comparación (progreso igual al total) no hay latidos, para no pasar del 100 %.
- Punto 5: el cambio del log se limita a `run_server` y se deshace al volver, así que un programa que use `create_server` conserva su configuración (criterio 3). Un cliente que cierra solo su extremo de lectura y deja abierto stdin sigue dejando al servidor esperando, como antes; una desconexión real cierra los dos.
- Punto 6: los avisos de los datos se repiten en el plan, no en todas las herramientas posteriores. Un candidato de `compare` sin backend sigue fallando y quedando el último, como en Python. Con el intervalo del plan, un agente ya no puede comparar sin intervalo si el plan lo tiene (debe crear el CV desde un plan sin intervalo); un intervalo asimétrico hace fallar al baseline y a ForecasterStats, igual que en Python con ese intervalo (documentado; preguntas abajo).
- Punto 7: `estimator` sigue siendo texto con los valores válidos en la descripción: un enum rechazaría los ids de Hugging Face. `candidates` exige al menos un elemento (el núcleo ya rechazaba la lista vacía). `skip_folds` con 0 era un `internal_error` de skforecast y ahora es `invalid_argument` del esquema.
- Punto 8:
  - La página de skforecast con pestañas no se pudo consultar: skforecast.org está bloqueado por la política de red de la sesión y la página "AI-assisted forecasting" de las ramas `0.26.x` y `master` no tiene pestañas ni plugin. La estructura sigue la descripción del encargo y las pestañas de `how-to-install.md`.
  - skforecast 0.26.0 y skforecast-ai 0.4.0 no están en PyPI, así que el comando con el pin no se pudo ejecutar tal cual: se comprobó con el paquete local y skforecast desde git. El plugin no se puede instalar hasta que 0.4.0 esté en PyPI.
  - Los fragmentos de Codex y Cursor dicen que se compruebe la documentación del cliente; lo no comprobado va a las preguntas.

**Tests.** De 3146 recogidos en `0.4.x` (`396c7e6`) a 3257, es decir, 111 más; en cada `/verify`, todos pasados salvo el omitido de siempre. Por commit (recogidos): 3197 (punto 1), 3201 (2), 3213 (3), 3223 (4), 3232 (5), 3237 (6), 3254 (7), 3257 (8) y 3257 (9). Todo con el `Client` en memoria, sin red ni modelos, salvo las integraciones por stdio, marcadas como lentas: el latido durante un backtest largo, la desconexión del cliente durante una ejecución (salida 0, dos líneas de log y ningún traceback) y `python -m`. Para no depender de la carga de la máquina, el test de progreso exacto en memoria fija un latido de una hora y el de stdio solo compara los eventos enteros.

**Preguntas de la sección 16 que esta fase resuelve.** 2 (un `internal_error` envía solo el tipo y un id), 3 (`--max-file-mb`), 7 (progreso en las llamadas largas; la cancelación dura y los timeouts quedan para después de 0.4.0) y 9 (el skill se distribuye con el plugin y `npx skills`). La 1 (argumentos de foundation en el núcleo) sigue abierta; el servidor añade ahora la política de licencias por encima.

**Preguntas nuevas para el autor.**
1. `execution_failed` y `all_candidates_failed` siguen citando el mensaje del error original (de pandas, por ejemplo), que puede llevar un valor de los datos, como decidió 12.1. El punto 2 solo cubre `internal_error`. ¿Se envía también ahí solo el tipo y el `failure_id`?
2. `compare` sin `interval` usa el del plan del CV, así que no hay forma de comparar sin intervalo desde ese CV. ¿Se añade una forma explícita (por ejemplo `interval: []`), o basta con crear el CV desde un plan sin intervalo?
3. `steps` mayor que la serie más larga se rechaza aunque `forecast` lo resuelva. ¿Se mantiene en todos los tools, o solo para backtest y compare, donde falla tarde?
4. El aviso de descarga busca la carpeta del id del modelo en la caché de Hugging Face, sin importar `huggingface_hub`. ¿Se usa `huggingface_hub.try_to_load_from_cache` cuando está instalado, o se pide a skforecast el repositorio real de los pesos de cada adaptador?
5. Con `all_candidates_failed`, un modelo que se descargó y después falló no se anuncia, y la siguiente llamada ya lo encuentra en la caché. ¿Se añade el aviso a los `details` del error?
6. Distribución, sin comprobar en la sesión:
   - el formato de `~/.codex/config.toml` (`[mcp_servers.<nombre>]` con `command`, `args` y `env`) y la sintaxis de `codex mcp add` (Codex no está instalado);
   - si Cursor interpola `${workspaceFolder}` en `.cursor/mcp.json` (la guía pide una ruta absoluta);
   - los timeouts de arranque de Cursor, Codex y Claude Desktop, y si el primer arranque de uvx (unos 60 s) los supera; para Claude Code, la documentación que consultó un subagente da `MCP_TIMEOUT` con 30 s por defecto, no medido aquí;
   - qué copia del skill instala `npx skills add skforecast/skforecast-ai --skill skforecast-ai-forecasting` ahora que el repositorio tiene dos con el mismo nombre (paquete y plugin): no se pudo ejecutar porque la rama por defecto aún no las tiene.
7. El plugin no deja pasar opciones (`--allow-model`, otro directorio, `HF_HUB_OFFLINE`): la guía manda añadir el servidor a mano y desactivar el plugin. ¿Se usan las opciones de configuración de plugins de Claude Code (`userConfig`) para ello?
8. El marketplace se lee de la rama por defecto: ¿se publica solo en `main` con la release, para que el pin nunca apunte a una versión que no está en PyPI? La subida de versión toca ahora cinco sitios (pyproject, `__version__`, plugin.json, marketplace.json dos veces y `.mcp.json`); el test los compara, pero ¿se añade al procedimiento de release?
9. Los avisos de los datos se repiten en el plan. ¿También en `create_cv`, `backtest` y `forecast`, o basta así?

**Qué queda para 0.4.0.**
- PRs 20 a 29 de la tabla 10.8: avisos y errores del CLI (20, 21), reemitir los avisos del script (22), comprobaciones tempranas (23), planes que no pueden ejecutarse (24), partición de evaluación (25), coherencia de `CVResult`, plan y `end_train` (26), datos frente a perfil guardado (27), estacionalidad con frecuencias ancladas (28) y el alias `result` de `ask()` (29).
- PRs 30 a 38: overrides (`overridden_fields`, `metric`, `use_exog`, `differentiation`, `calendar_features`, `target_transformer`, `dropna_from_series`), avisos del plan en el contexto, límites de `describe()` en `ask()` (opcional), paridad del CLI y `profile(exog_columns=...)`; con cada uno, su exposición en el servidor (los TypedDicts de `refine_plan` y de los candidatos ya no heredan de los del núcleo: un test avisa cuando sus claves cambian, y hay que añadir cada clave con su descripción).
- El check de pago, una sola vez al final, con la lista de las secciones 3, 12, 13, 14 y 15 más lo que añadan los PRs 30 a 36. Esta fase no añade nada.
- Publicar skforecast 0.26.0 y skforecast-ai 0.4.0 en PyPI antes de anunciar el plugin, y las preguntas de arriba.

**Siguiente:** los PRs 20 a 38 de 0.4.0 y, al final, el check de pago.

### 17.1 Revisión del autor y correcciones

Antes de mergear la fase 4b, una verificación independiente comparó `0.4.x` (`396c7e6`, con el servidor de la fase 4) con la rama, y el autor decidió las preguntas abiertas. Las correcciones van como commits nuevos al final de `fix/mcp-hardening`; ninguno subido se reescribió.

**Verificación.**
- El núcleo solo cambia en `skforecast_ai/__main__.py`, la guarda `__main__` y las dos opciones del comando `mcp` en `cli.py` (más `AGENTS.md` y `README.md`).
- Paridad exacta con la API de Python por stdio en h2o, h2o con exógenas, bike_sharing e items_sales ancho y largo; la salida estándar sigue siendo solo JSON-RPC, también con las notificaciones de progreso periódicas. Cada diferencia frente al servidor de la fase 4 es una de las previstas.
- El bloqueo de modelos foundation aguantó por todas las vías probadas (plan, `refine_plan`, candidatos, mayúsculas, espacios, Unicode, prefijos parciales); `internal_error` ya no lleva valores ni rutas; la tabla de ataques de la fase 4 da lo mismo.
- Como agente, las cinco tareas se resuelven en 4 a 6 llamadas sin puntos muertos.
- Un test fallaba en macOS (la sesión remota, en Linux, lo veía pasar): ver `554b71f`.

**Decisiones del autor.**

| Pregunta | Decisión | Commit |
|---|---|---|
| 1 | `execution_failed` y `all_candidates_failed` envían solo el tipo del error cuando no es de skforecast-ai, como `internal_error`; el texto completo queda en `get_failure` | `5044ab0` |
| 2 | `compare` sin intervalo: se deja como está (crear el CV desde un plan sin intervalo) | |
| 3 | `steps` mayor que la serie más larga: se mantiene el rechazo en `plan` y `refine_plan` | |
| 4 | El aviso de descarga dice que los pesos "no se encontraron" y "pueden" descargarse; la caché exige un fichero dentro de un snapshot. Pedir a skforecast el repositorio real de cada adaptador queda para después | `65849a2` |
| 5 | El aviso de descarga va también en `details.notices` de `all_candidates_failed` | `65849a2` |
| 6 | `npx skills add` instala la copia del plugin, sin conflicto (comprobado en una copia local). Cursor y Codex siguen sin probar en real | |
| 7 | `userConfig` en el plugin: después de 0.4.0 | |
| 8 | Publicar primero en PyPI y después mergear a `main`; la subida de versión en cinco sitios va a la lista de la release (abajo) | |
| 9 | Los avisos de datos no se repiten en más tools; en su lugar, el aviso de valores ausentes del target | `8b5d365` |

**Otros commits.**
- `554b71f`: al desconectarse el cliente durante una llamada, el servidor salía con 0 pero dejaba "Exception ignored ... BrokenPipeError" en stderr en macOS, por el duplicado privado de stdout con el que escribe el SDK. Ahora se apuntan al dispositivo nulo todos los descriptores abiertos sobre esa tubería.
- `08b5bd6`: `--allow-dir` debe ser una ruta absoluta; vacío o relativo se resolvía contra el directorio de arranque (alcanzable si un cliente expande `${CLAUDE_PROJECT_DIR}` a vacío).
- `9102d2b`: solo corren sin `--allow-model` los adaptadores revisados (`REVIEWED_ADAPTERS`: Chronos, TimesFM 2.5, TabICL, Nori). Un adaptador que añada una versión futura de skforecast necesita la opción hasta que se revise su licencia.
- `31b0e66`: una estrategia que skforecast rechaza (`initial_train_size` fuera de los datos, `gap` demasiado grande) y un `test_size` de texto que no es fecha vuelven a ser `invalid_argument` con su motivo; desde `11f7292` llegaban como `internal_error` sin pista.
- `5044ab0`: `get_failure` ya no devuelve rutas absolutas de instalación (llevan el nombre del usuario).
- `89f460b`: `create_cv` da en `cost.compare_estimator_fits` los ajustes de un `compare` sin candidatos con esa estrategia, y un `CompareCostNotice` cuando superan los del plan (12 ajustes del plan frente a 432 del `compare`, 185 s, en el caso medido).
- `8db06b7`: timeouts en el fragmento de Codex, la frase sobre candidatos rechazados, el aviso de que el plugin expone todos los CSV del proyecto y la entrada de la release.

**Tests.** De 3257 a 3277 (más 1 omitido), en macOS con el entorno conda local. Probado con `mcp` 2.2.0 y 2.3.0.

**Plan de release (decisión del autor).**
1. El autor publica skforecast 0.26.0 la semana del 5 de octubre de 2026. Lo que skforecast-ai necesite de skforecast, o un fallo que se encuentre en él, se le comunica antes para que entre en esa versión.
2. Después, el autor publica skforecast-ai 0.4.0 en PyPI.
3. Solo entonces se mergea `0.4.x` a `main`: el marketplace del plugin se lee de la rama por defecto, y su pin (`skforecast-ai[mcp]==0.4.0`) no debe apuntar a una versión que no esté en PyPI.
4. La versión se sube en cinco sitios (pyproject, `__version__`, `plugin/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` dos veces y `plugin/.mcp.json`); `tests/test_plugin_distribution.py` falla si alguno no coincide.

**Para skforecast 0.26.0** (sugerencias, no bloquean):
- Exponer en `FoundationModelInfo` el repositorio real de los pesos de cada adaptador: TabICL los guarda en `jingang/TabICL`, no bajo su id, así que el aviso de descarga del servidor no puede saber si están en la caché.
- Registrar `license_restriction` para todo adaptador nuevo; el servidor ya no asume que `None` significa permisivo.

**Pendiente o anotado.**
- El check de pago, una sola vez al final. Esta fase no añade nada al contexto del LLM.
- Cancelación dura y timeouts (un candidato en curso no se puede parar), `userConfig` del plugin, y Cursor y Codex probados en real: después de 0.4.0.
- Un CSV por debajo de `--max-file-mb` pero con cientos de miles de columnas aún consume mucha memoria y tiempo; documentado como límite de bytes, no de memoria.
- Los PRs 20 a 38 de la tabla 10.8; el PR 23 (comprobaciones tempranas) quitará los `internal_error` que quedan por CSV ilegibles.

## 18. Fase 5a: hecho

Arreglos del núcleo y del CLI que quedaban para 0.4.0 (PRs 20 a 29 de la tabla 10.8, más los puntos 11 y 12 de las preguntas de 10.10), en la rama `fix/core-checks`, creada desde `0.4.x` (`4047bfa`). Un commit por punto, en el orden pedido, cada uno con su código, sus tests, su documentación y, si se ve, su entrada en `docs/releases/releases.md` (0.4.0), y cada uno subido al terminar. Antes de cada commit se pasaron `/verify` (lint, tests afectados, suite completa y build de la documentación), el subagente `conventions-reviewer` y `/code-review`, y en el PR 23, el PR 27 y el punto 12 también `/security-review`, sin hallazgos en ninguno. Lo que encontraron las revisiones se corrigió antes de subir cada commit. Ningún commit subido se reescribió y ninguno necesitó una corrección posterior. Cada mensaje de commit lleva su lista "Cambios para el usuario" y las elecciones conservadoras con su criterio de la sección 10.

Goldens: los de render y los de contexto del LLM (`ask()` y `describe()`) no cambian en ningún commit. El PR 28 podía cambiar los de render, pero ninguno usa una frecuencia anclada. El PR 27 y el punto 12 podían cambiar los del LLM, pero solo cambian para datos distintos del perfil o para textos con saltos de línea o etiquetas, que no salen en ningún golden. El golden de los esquemas de los tools del MCP cambia en 3 líneas: dos descripciones de `create_cv` en el PR 23 y la de `gap` en el PR 24.

| Commit | Punto | Contenido |
|---|---|---|
| `fd868ad` | PR 20 | Los avisos del CLI van a stderr |
| `b712ddc` | PR 21 | Contrato de errores del CLI y `--steps` con `--from-plan` |
| `7b41d90` | PR 22 | `exec_rendered` muestra los avisos del script |
| `86bb0ad` | PR 23 | Comprobaciones tempranas de entradas (10.3) |
| `2be3853` | PR 24 | Rechazar planes que no pueden ejecutarse |
| `961984a` | PR 25 | Comprobaciones de la partición de evaluación |
| `ea4f9bd` | PR 26 | `CVResult`, plan contra perfil y `end_train` |
| `e5c3773` | PR 27 | Datos frente a perfil guardado (SIL-1) |
| `c81e5e3` | PR 28 | Periodo estacional con frecuencias ancladas |
| `24953b0` | PR 29 | Se elimina el alias `result` de `ask()` |
| `49d99f0` | Punto 11 | Fechas escritas en más de un formato |
| `93ef36f` | Punto 12 | Texto libre del plan escapado en el contexto del LLM |

**Qué cubre cada commit.**
- PR 20: el callback del CLI envuelve el manejador de avisos de skforecast para que escriba en stderr con el mismo formato; se restaura al terminar el comando. `--format json` vuelve a dar un JSON que se puede leer aunque haya avisos.
- PR 21:
  - Los errores van a stderr, escapados (el texto entre corchetes ya no se pierde).
  - Con `--format json` son un objeto `{"error": {...}}` con los campos de `ErrorInfo`.
  - `--format` solo acepta los valores de cada comando (código de salida 2).
  - `--steps` con `--from-plan` distinto del plan sale con 1, como en Python.
  - Un bundle de `--from-plan` mal formado dice qué falta (`field='from_plan'`).
  - El texto imprime `Tip: <hint>` cuando el error trae uno.
- PR 22: `exec_rendered` guarda los avisos que el script emite en el hilo actual y los muestra al terminar, por el manejador que encontró (también si el script falla). Los filtros no se tocan y el manejador se cambia a mano, sin `catch_warnings`, para no reiniciar los registros de avisos ya mostrados.
- PR 23 (10.3):
  - Comprobaciones de `series_id_column` y de `target`: vacío, sin valores (`insufficient_data`) o con texto que no es número.
  - CSV ilegibles como `data_unreadable`; `end_train` que no es fecha.
  - `estimator_kwargs` que no es un dict, y los nombres de `Arima`.
  - Los errores de `TimeSeriesFold` envueltos con su argumento en `field`; `skip_folds` fuera de los folds; `fixed_train_size` sin reentrenar.
  - El backend de un modelo foundation, antes de ejecutar (`missing_dependency`).
  - Valores infinitos del target; `compare()` sin baseline con un intervalo asimétrico.
  - `data` y `cv` de un tipo incorrecto.
  - `hint` en los remedios que los mensajes daban con llamadas de pandas.
  - En el servidor se quitó `_cv_argument_error`, porque el núcleo da lo mismo o más; el control propio del backend se queda porque su pista nombra `uvx --with`.
- PR 24:
  - Forecasters multiserie sobre una serie; ForecasterDirectMultiVariate en formato largo con una serie.
  - Exógenas con el nombre de un lag o de una window feature.
  - Baseline sin frecuencia.
  - Forecaster directo con `gap` en `backtest()`.
  - Series sin valores o no más largas que la ventana en ForecasterRecursiveMultiSeries (`insufficient_data`).
  - `refine_plan()` vuelve a los valores anteriores, con un aviso, cuando la sugerencia del LLM queda rechazada.
- PR 25:
  - En modo evaluación (`validate_evaluation_partition`), cada serie de ForecasterRecursiveMultiSeries necesita valor en el último día de entrenamiento y en las fechas de test.
  - La partición de entrenamiento pasa por la regla de valores ausentes de la última ventana.
  - `_check_evaluated_target` con `level` y huso horario.
  - Un `end_train` subdiario a medianoche conserva la hora. Antes entrenaba con todo el día y comparaba predicciones desplazadas con estado ok; el fallo ya estaba en la base.
- PR 26:
  - `backtest()` y `backtest_code()` con un `CVResult` y sin plan ejecutan el plan del `CVResult`.
  - Un `CVResult` de otra estructura falla en `backtest()`, `backtest_code()` y `compare()`.
  - Un plan recibido se compara con el perfil: frecuencia, forma, exógenas que usa y calendario.
  - `forecast()` sin `test_size` con un plan de evaluación falla.
- PR 27 (decisión del autor, pregunta 7):
  - Con `data` y un `profile` guardado, los datos se perfilan otra vez con el target, la fecha y la serie del perfil.
  - Otra estructura (frecuencia, series, target o exógenas) da `InvalidInputError` con `field='profile'` y una pista.
  - Mismos valores: se devuelve el perfil guardado, sin repetir sus avisos.
  - Otros valores (filas nuevas): se usa el perfil nuevo, con una nota en `DataProfile.warnings` que nombra los campos que cambiaron.
  - La comparación deja fuera `data_path` y `warnings`, ordena las columnas y trata NaN como igual a NaN. Un perfil refrescado vuelve igual si se le pasan los mismos datos.
- PR 28: `tabulated_seasonal_period` lee una frecuencia anclada como su alias base. Lo usan el `m` de Auto-ARIMA, la regla que deja Auto-ARIMA fuera de los candidatos y el baseline. Afecta a todo dato trimestral (`QS-OCT`, `QE-DEC`), al semanal que no acaba en domingo o lunes (`W-WED`) y al anual (`YE-DEC`, que escribe `m=1`, su valor por defecto).
- PR 29 (decisión del autor, pregunta 15): `ask(result=...)` da `TypeError`; los docstrings de `create_cv()` y `CVResult` dicen `context`. La fila 29 de la tabla 10.8 y la lista de 10.6, que decían "hasta 0.5.0", quedan superadas por esta decisión.
- Punto 11 (decisión del autor, pregunta 5):
  - `_read_date_column`, común a la detección de fechas del CSV, a `detect_date_column` y al cargador de exógenas futuras, lee la columna como el script.
  - Solo si falla, lee las fechas una a una para decir por qué no puede ser la columna de fechas.
  - El error cita la primera fecha y otra que no encaja con ninguna lectura de esa primera, y pide un solo formato.
  - `format='mixed'` no se escribe en el script, y `parse_text_dates` pierde su opción `mixed`, que ya no usaba nadie.
- Punto 12 (decisión del autor, pregunta 17):
  - `_free_text` escribe la explicación del plan y la razón de cada paso de preprocesado en una línea.
  - Los caracteres Cc, Zl, Zp y Cf pasan a su secuencia de escape, y el `<` que abre texto con forma de etiqueta pasa a `&lt;`.
  - No se rechaza ningún plan. `plan.warnings` no llega al contexto (solo a la pantalla), así que no hay nada que escapar.

**Desviaciones respecto a la sección 10, con su motivo.**
- PR 20: el comando `mcp` conserva su manejador, porque el servidor registra los avisos por llamada en un hilo y `redirect_stdout` no es seguro entre hilos (criterio 3). No hay panel "Plan Warnings" en las tablas del CLI: cada aviso ya sale en stderr y `--format json` lleva `plan.warnings`.
- PR 21: un valor rechazado por el parser de una opción mantiene el código 2 y el texto de uso de click; solo con `--format json` es el objeto JSON. Los errores que click da antes de que el comando conozca su formato (opción desconocida, `--format xml`) siguen siendo texto.
- PR 22: los avisos se pasan al manejador guardado en lugar de reemitirse con `warn_explicit`, como decía 10.2. Reemitidos, los filtros verían un módulo derivado del nombre del fichero, y un filtro `error` lanzaría fuera del script.
- PR 23:
  - 10.3 no decide si los valores infinitos son error o aviso. En la base todos los forecasters entrenados ya fallaban o daban NaN, así que se rechazan antes; el baseline solo cuando sus predicciones leen el valor.
  - El rango de `skip_folds` solo se comprueba en las estrategias de `create_cv()`; un `TimeSeriesFold` directo funcionaba en 0.3.1.
  - La comprobación numérica del target está en `profile()` y no en `create_data_profile`, que es pública y describe un target categórico.
- PR 24:
  - `backtest_code()` y `create_cv()` no rechazan un forecaster directo con `gap`: devolvían su resultado en 0.3.1 y el documento no los decide. Va a las preguntas.
  - El plan de ForecasterStats que aconseja `dropna_from_series` (sección 12) es un cambio de explicación, no un plan que no se pueda ejecutar: queda para después.
- PR 25: las reglas multiserie solo se aplican en modo evaluación; en predicción siguen las decisiones de la sección 12.
- PR 26:
  - Un plan sin frecuencia (hecho a mano) no se compara.
  - Las exógenas del plan no se comparan con las del perfil, para no romper planes reutilizados con datos nuevos (de eso se ocupa el PR 27).
  - `forecast_code()` sigue generando el split de un plan con `end_train`.
  - `interval` con un `CVResult` construye un plan nuevo, como los demás argumentos del modelo.
- PR 27:
  - Si cambian los valores, se rehace todo el `ForecastingProfile`, porque la decisión dice "re-perfilar". Un plan recibido se ejecuta tal cual aunque el perfil nuevo recomiende otro forecaster.
  - Los datos que difieren se perfilan dos veces (el `DataProfile` silenciado y después `profile()`), para no reemitir avisos a mano.
  - En el servidor, un CSV que cambió sigue dando `data_changed`, porque su comprobación de huella va antes que el núcleo.
- PR 28: la regla de candidatos lee el mismo periodo que el script. Con solo el script arreglado, los datos semanales anclados de martes a sábado habrían seguido proponiendo ForecasterStats con `m=52`, cuya búsqueda tardó 47 s por ajuste frente a 2 s con `m=1` (260 filas; unos 5 minutos en un `compare()` por defecto). La regla `MAX_STATS_SEASONAL_PERIOD` ya lo hacía con `W-SUN`. Es un cambio para el usuario que el documento no nombra; está justificado en el commit.
- PR 29: no se deja un error más amable, porque exigiría conservar el argumento, en contra de la decisión. La nota de la release da la migración.
- Punto 11:
  - Las fechas día-primero cuya primera fecha se lee mes-primero (`01/02/2023` y después `13/02/2023`) están en un solo formato. Se leen como en 0.3.1 y `plan()` da el error de frecuencia con el consejo de día-primero, porque rechazarlas en `profile()` rompería una llamada que funcionaba sin que el documento lo decida.
  - Los nombres de zona que cambian (CET, CEST), con los que el script ya fallaba, dan el mensaje existente de varias zonas horarias.
  - El control propio del cargador de exógenas se queda, para lo que el control común deja pasar.
- Punto 12:
  - Solo se escapan los textos del plan que nombra la decisión.
  - El razonamiento que `refine_plan()` añade con un LLM tiene saltos de línea, así que sus párrafos se leen como `\n`; la nota de la release lo dice.
  - La función no se comparte con `_comment_text` del render, que no escapa Cf, porque la capa `llm` no importa el render.

**Cambios para el usuario.**
- Python:
  - Fallan antes de ejecutar, con código y campo, las llamadas de 0.3.1 que fallaban dentro del script o devolvían un resultado erróneo con estado ok. Son los casos de los PRs 23 a 26 y el punto 11: estructura, series cortas o sin valores, `gap` directo, infinitos, partición de evaluación, `CVResult` o plan de otros datos, fechas en varios formatos.
  - Además dan `ValueError` llamadas que funcionaban:
    - `create_cv(fixed_train_size=...)` sin `refit`;
    - `skip_folds` fuera de rango;
    - `series_id_column` igual al target o a la fecha;
    - `forecast()` sin `test_size` con un plan de evaluación;
    - datos de otra estructura con un perfil guardado;
    - `ask(result=...)`, que da `TypeError`.
  - Otros resultados:
    - `backtest()` con un `CVResult` y sin plan ejecuta su plan;
    - con un perfil guardado y datos con otros valores se usa el perfil nuevo, con una nota;
    - Auto-ARIMA usa `m=4` o `m=52` con frecuencias ancladas, y deja de ser candidato con las semanas ancladas de martes a sábado;
    - `end_train` subdiario a medianoche conserva la hora y da las métricas correctas;
    - `compare()` con un intervalo asimétrico no tiene fila de baseline.
  - Avisos nuevos:
    - los avisos del script de skforecast se muestran;
    - un valor ausente que lee un estimador tolerante en la partición de entrenamiento avisa;
    - `refine_plan()` avisa cuando rechaza la sugerencia del LLM;
    - `plan(forecaster='ForecasterStats')` con semanas ancladas de martes a sábado da `UnrecommendedForecasterWarning`.
- CLI:
  - Los avisos y los errores van a stderr; un error es JSON con `--format json`.
  - `--steps` con `--from-plan` distinto del plan sale con 1, y un `--format` inválido con 2.
  - Hay `Tip: <hint>`.
  - `--fixed-train-size` necesita `--refit`.
  - Los cambios de Python se ven igual, también con `--from-plan` y `--from-profile` frente a datos de otra estructura.
- Servidor MCP:
  - Los mismos errores llegan antes de ejecutar, con su código; los errores de `create_cv` llevan `field`.
  - Un candidato foundation sin backend falla antes de correr.
  - Los avisos del script llegan como notices después de los de la llamada.
  - Un CSV con fechas en varios formatos es `invalid_argument` en `profile`.
  - Los resúmenes (`describe()`) escapan el texto libre de un plan.
  - El SKILL.md, su copia del plugin, `docs/api/mcp.md` y las descripciones de los tools lo dicen.

**Tests.** De 3274 pasados en `0.4.x` (`4047bfa`) a 3735, es decir, 461 más; en cada `/verify`, todos pasados salvo el omitido de siempre. Por commit (pasados): 3279 (PR 20), 3298 (21), 3307 (22), 3477 (23), 3557 (24), 3628 (25), 3669 (26), 3701 (27), 3726 (28), 3726 (29), 3732 (punto 11) y 3735 (punto 12).

**Paridad final.** Con `4047bfa` como base y el último commit de la rama, los cinco escenarios dan resultados idénticos, sin ningún aviso en ninguno de los dos lados: h2o desde CSV, h2o desde DataFrame, bike_sharing con exógenas futuras, e items_sales ancho y largo. Se compararon el perfil, el plan, el script de `forecast_code()`, las predicciones y el script de `forecast()`, las predicciones, métricas y script del modo evaluación, el CV, el script de `backtest_code()` y las predicciones, métricas y script de `backtest()`. También coincidía tras el punto 11, el último cambio de la lectura de datos. Ningún PR cambia a propósito estos escenarios: el PR 28 solo afecta a frecuencias ancladas y el PR 27 a datos distintos de su perfil.

**Para la lista del check de pago.**
- PR 23: la nota "No baseline: ..." de la explicación de `compare()` con un intervalo asimétrico.
- PR 27: la nota de `DataProfile.warnings` cuando los datos difieren del perfil (llega a `ask()` y `describe()`).
- Punto 12: el cambio de `llm/context.py`. Un plan con saltos de línea o etiquetas, y un plan refinado con LLM, cuyos párrafos llegan como `\n`.

**Preguntas nuevas para el autor.**
1. `backtest_code()` y `create_cv()` con un forecaster directo y `gap`: `backtest()` lo rechaza (PR 24), pero estos dos devuelven un resultado que fallará. ¿Se rechazan también? Un CV de `create_cv()` puede servir a otros forecasters en `compare()`.
2. Texto libre de otros objetos en el contexto del LLM, sin escapar: la explicación del perfil y `DataProfile.warnings`, que un JSON de `--from-plan` o `--from-profile` también trae, y la explicación del CV, que incluye el razonamiento del LLM de `create_cv()`. ¿Se les aplica `_free_text`? Los goldens no cambiarían.
3. Planes refinados con LLM: sus párrafos se leen como `\n` en el contexto. ¿Se aceptan así, o se renderizan con sangría en varias líneas, con las etiquetas escapadas?
4. Fechas día-primero cuya primera fecha se lee mes-primero: `profile()` las acepta sin frecuencia y `plan()` falla después. ¿Se rechazan ya en `profile()` con el consejo de día-primero?
5. Frecuencias multiplicadas (`2W`, `3h`): Auto-ARIMA sigue sin `m` mientras el baseline usa `estimate_seasonality`. Los alias antiguos de pandas 2.1 (`Q-DEC`, `H`) no están en la tabla, como antes. ¿Se unifican las dos tablas de periodos (`FREQUENCY_TO_SEASONAL_PERIOD` y la de `estimate_seasonality`)?
6. PR 27: un plan recibido se ejecuta aunque el perfil refrescado recomiende otro forecaster. ¿Se avisa? Y en el servidor, ¿se mantiene `data_changed` (pregunta 5 de la sección 16) ahora que Python refresca el perfil?
7. ForecasterStats que aconseja `dropna_from_series` (sección 12): pendiente desde el PR 24, porque es un cambio de explicación (check de pago).

**Pendiente o anotado.**
- `backtest()` de datos con huso horario y un `initial_train_size` de fecha falla dentro del script ("Cannot compare tz-naive and tz-aware"), como en 0.3.1.
- `compare()` con un target infinito no falla antes de empezar: un baseline que no lee el valor aún puede ganar, como en 0.3.1.
- El `start_date` de series en formato largo que empiezan en fechas distintas es el inicio más tardío.
- Rendimiento: `validate_series_lengths` calcula `_series_spans` otra vez; un perfil guardado se vuelve a perfilar en cada llamada (y dos veces si los datos cambiaron).
- El escape del punto 12 no cubre los corchetes de ancho completo (`＜`); un `\n` literal en el texto se lee igual que un salto escapado.

**Qué queda para 0.4.0.**
- PRs 30 a 38 de la tabla 10.8: overrides (`overridden_fields`, `metric`, `use_exog`, `differentiation`, `calendar_features`, `target_transformer`, `dropna_from_series`), avisos del plan en el contexto, límites de `describe()` en `ask()` (opcional), paridad del CLI y `profile(exog_columns=...)`; cada uno con su exposición en el servidor.
- El check de pago, una sola vez al final, con la lista de las secciones 3, 12, 13, 14 y 15, lo de esta fase (arriba) y lo que añadan los PRs 30 a 36.
- Las preguntas de arriba.
- El plan de release de 17.1: skforecast 0.26.0, después skforecast-ai 0.4.0 en PyPI y solo entonces el merge de `0.4.x` a `main`.

**Siguiente:** los PRs 30 a 38 y, al final, el check de pago.

### 18.1 Revisión del autor y correcciones

Antes de mergear la fase 5a, una verificación independiente comparó `0.4.x` (`4047bfa`) con la rama (`1073c15`) en cuatro frentes: los comandos documentados, las comprobaciones nuevas (unas 330 llamadas en las dos versiones), los PRs 22, 28, 29 y el punto 12, y el servidor MCP por stdio. Las correcciones van como commits nuevos al final de `fix/core-checks`; ninguno subido se reescribió.

**Verificación.**
- Suite: 3735 pasados y 1 omitido en macOS, como dice la sección 18; ruff limpio; `check_ask_context.py --dry-run` bien en los cuatro conjuntos.
- Documentación: de los comandos documentados en la base solo dejaba de funcionar `backtest --fixed-train-size --no-refit` (corregido abajo).
- Servidor: paridad exacta con la API de Python en 5 conjuntos (45 resúmenes, 30 scripts, 55 CSV); frente a la base solo cambia lo que la sección 18 anuncia. 13 entradas que daban `internal_error` ya no lo dan. Los vectores de seguridad de las fases 2 y 4b se comportan igual.
- PR 28: confirmado. Con datos trimestrales cambian las predicciones y el ganador de `compare()` (MAE de 1234 a 547 en el caso medido); la nota de versión no lo decía.

**Regresiones encontradas y corregidas.**

| Qué fallaba | Corrección | Commit |
|---|---|---|
| El punto 12 solo escapaba dos textos del plan: la explicación del perfil, `DataProfile.warnings` y los nombres de columnas y series aún podían cerrar o abrir secciones en `ask()` y `describe()` | Las etiquetas se escapan al cerrar cada sección (`_tag`), los nombres van en una línea (`_one_line`) y el texto libre de varias líneas va con sangría bajo su elemento (`_free_text`). Los goldens no cambian | `763080f` |
| `create_cv(fixed_train_size=...)` sin `refit` daba error, también con `False` y con `--fixed-train-size` o `--expanding-train` en la CLI | Corre como antes y avisa con `IgnoredArgumentWarning` | `f3f9704` |
| Un perfil guardado con una columna de más en los datos, o con una serie añadida o quitada en formato largo, era "otra estructura" | La columna que el perfil no nombra no se usa (nota en `DataProfile.warnings`); el cambio de series refresca el perfil con nota. Una exógena que falta sigue siendo error | `4b8cbca` |
| Un plan o un perfil `MS` con datos `ME` (o `W-SUN` con `W-MON`) daba error | Las frecuencias se comparan por periodo (`same_period`) | `4b8cbca` |

**Otros commits.**
- `f4f3558`: el error de fechas que el script no puede leer decía "más de un formato", falso para `01 May 2015` y `01 Jun 2015` (pandas lee un nombre de mes completo de la primera). Ahora cita el formato leído de la primera fecha y un ejemplo en ISO 8601.
- `acbad9a`: los alias que infiere pandas 2.1 (`M`, `Q-DEC`, `A-DEC`, `H`, `15T`) tienen periodo estacional.
- `832099b`: la pista de una estrategia que `TimeSeriesFold` rechaza nombra el argumento cuando el problema no son los folds; la lista de `skip_folds` se corta en 5; unos datos cuyo índice perdió el atributo `freq` ya no añaden la nota de "valores distintos".
- `dbdfe14`: notas de versión. Siete entradas reescritas (más cortas y con su migración), la del PR 22 limitada a `forecast()`, fuera la frase sobre `test_size` con huso horario, y las entradas que faltaban (`refine_plan()` y los `Tip:` de la CLI).
- `7b18a59`: el SKILL.md dice al agente que siga el `hint` antes que un consejo que necesita Python; `docs/api/mcp.md` explica por qué el servidor pide `profile` de nuevo.

**Decisiones del autor sobre las preguntas de la sección 18.**

| Pregunta | Decisión | Estado |
|---|---|---|
| 1 | Forecaster directo con `gap`: rechazarlo en `backtest_code()` y avisar en `create_cv()` | Fase 5b |
| 2 | Escapar también el perfil, sus avisos y los nombres | Hecho (`763080f`) |
| 3 | Texto de varias líneas con sangría, no `\n` literal | Hecho (`763080f`) |
| 4 | Fechas día-primero: rechazar en `profile()` solo las lecturas erróneas demostrables | Fase 5b |
| 5 | Alias antiguos ahora; unificar las dos tablas de periodos en la fase 6 | Alias hechos (`acbad9a`) |
| 6 | Sin aviso de Python cuando el perfil refrescado recomienda otro forecaster; el servidor mantiene `data_changed` | Hecho (`7b18a59`) |
| 7 | ForecasterStats y `dropna_from_series` | Check de pago |

**No se hizo, y por qué.**
- Aceptar las variantes ISO 8601 mezcladas (medianoche sin hora como exporta R, segundos que faltan, `T` y espacio, microsegundos en algunas filas). El script generado lee las fechas con `pd.to_datetime(columna)`, que falla con todas ellas; aceptarlas pide que el script lea con `format='ISO8601'`, que es un cambio de renderizado y un campo nuevo del perfil. Queda como decisión para la fase 5b. De momento el error da el ejemplo ISO que hay que escribir.

**Pendiente para la fase 5b (ya existía en la base).**
- `internal_error` en `profile` con un target casi todo infinito o que desborda, y en `plan` con un `context_length` de texto.
- `plan(steps=100)` sobre 204 filas pasa `create_cv` y falla en `backtest`.
- Ningún CSV con huso horario se puede evaluar con `backtest` desde el servidor: la fecha por defecto de `create_cv` falla dentro del script.
- `end_train` de series en formato largo que empiezan en fechas distintas cae fuera de los datos, y el error de evaluación cita esa fecha.
- `compare()` con un intervalo asimétrico no emite aviso (solo la frase de la explicación).
- Los mensajes de la CLI usan los nombres de Python (`refit=True`) en lugar de las opciones (`--refit`).

**Para la lista del check de pago.** El contexto de `ask()` cambia solo con textos de varias líneas o con etiquetas: la explicación de un plan refinado con LLM llega ahora con sus párrafos en líneas con sangría.

**Tests.** De 3735 a 3763 (más 1 omitido), en macOS con el entorno conda local.

## 19. Fase 5b: hecho

Adaptación a skforecast 0.26, los overrides (PRs 30 a 35, 37 y 38 de la tabla 10.8) y los pendientes de 18.1, en la rama `feature/overrides`, creada desde `0.4.x` (`36babee`). Un commit por punto, en el orden pedido, cada uno con su código, sus tests, su documentación y, si se ve, su entrada en `docs/releases/releases.md` (0.4.0, escrita con `/release-note`; cuando el cambio tocaba algo nuevo de esta versión se corrigió su entrada en lugar de añadir otra), y cada uno subido al terminar. Antes de cada commit se pasaron `/verify` (lint, tests afectados, suite completa y build de la documentación), el subagente `conventions-reviewer` y `/code-review`, y en el commit 0 y los PRs 35 y 38 también `/security-review`, que no encontró nada en ninguno de los tres. Lo que encontraron `conventions-reviewer` y `/code-review` se corrigió antes de subir cada commit; los mensajes de los commits lo dicen. Ningún commit subido se reescribió y ninguno necesitó una corrección posterior. El PR 36 no se hizo, ni la fase 6. Cada mensaje de commit lleva su lista "Cambios para el usuario" y las elecciones conservadoras con su criterio de la sección 10. En el mensaje de `b363cf7` se perdió un nombre (`_read_dates_one_by_one`, en la línea de las revisiones) por una sustitución de la shell; no se reescribió.

Goldens:
- Render: los existentes no cambian en ningún commit. Los overrides añaden casos nuevos, comparados byte a byte: métrica, sin exógenas, diferenciación, calendario, escalado y NaN (PRs 31 a 34), y columnas dejadas fuera en foundation (PR 38); el caso multivariante sin exógenas se parametriza con un perfil que deja columnas fuera, con el mismo script esperado. Los scripts de los PRs 31 a 34 y 38 se ejecutan además como ficheros en `tests/test_integration_standalone_script.py`.
- Contexto del LLM (`ask()` y `describe()`): solo cambian en el commit 0 (el nombre de la licencia de TimesFM 3.0 en `forecast_foundation_numeric_covariates`) y en el PR 35 (13 ficheros ganan la línea "Chosen by the user instead of the rules: ...", y un escenario nuevo, `code_generation_overrides_and_warnings`). Regenerados con `/llm-context-change` y revisados; `check_ask_context.py --dry-run` construye todos los contextos.
- Esquemas de los tools del MCP: cambian a propósito en los PRs 31 a 34 y 38 (los argumentos y claves nuevos y la descripción de `RefinePlanArgs`).

| Commit | Punto | Contenido |
|---|---|---|
| `654ea8b` | 0 | Política de licencias desde `FoundationModelInfo` de skforecast 0.26 |
| `141d51a` | PR 30 | `overridden_fields` y `PlanEditsDiscardedWarning` |
| `9785f16` | PR 31 | Override `metric` |
| `ee561b0` | PR 32 | Override `use_exog` y arreglos multivariante |
| `6669873` | PR 33 | Override `differentiation` |
| `b854712` | PR 34 | Overrides `calendar_features`, `target_transformer`, `dropna_from_series` |
| `e3d44d1` | PR 35 | Avisos del plan y decisiones del usuario en el contexto |
| `a6239a5` | PR 37 | Paridad del CLI con los overrides |
| `d553ac5` | PR 38 | `profile(exog_columns=...)` |
| `4c7d070` | 18.1, decisión 1 | Forecaster directo con `gap` en `backtest_code()` y `create_cv()` |
| `b363cf7` | 18.1, decisión 4 | Fechas día-primero que se leen mes-primero, en `profile()` |
| `c99a649` | 18.1 | `internal_error` de un target casi infinito y de `context_length` de texto |
| `6d76d0b` | 18.1 | Primera ventana de entrenamiento más corta que la del forecaster |
| `8a0a10b` | 18.1 | `backtest` de fechas con huso horario |
| `39570a0` | 18.1 | `end_train` de series largas que empiezan en fechas distintas |

**Qué cubre cada commit.**
- Commit 0: skforecast 0.26 cambia `FoundationModelInfo` (sin `license_restriction`; con `license`, `commercial_use_restricted`, `license_url`, `weights_repo_id`, `weights_in_hf_cache`, `requires_provider_auth`). En la base, todo `plan()` de ForecasterFoundation daba `AttributeError` y la suite paraba al recoger los tests.
  - La explicación del plan nombra la licencia como la registra skforecast, y para TabPFN añade la frase de la cuenta del proveedor.
  - Servidor: `--allow-model` se exige cuando `commercial_use_restricted`, `requires_hf_auth` o `requires_provider_auth` son verdaderos, o cuando skforecast no da alguno como booleano o no da licencia. Se quita `REVIEWED_ADAPTERS`.
  - La caché se busca en `weights_repo_id`. Con `weights_in_hf_cache=False` (TabPFN), el aviso de descarga no habla de la caché de Hugging Face.
  - Un test fija el reparto actual: sin la opción, Chronos-2, TimesFM 2.5, TabICL, Nori y T0; con ella, TimesFM 3.0, Moirai, TabPFN y TS-ICL.
- PR 30 (10.4, procedencia):
  - `ForecastPlan.overridden_fields` es un `Literal` cerrado, en el orden canónico de `OVERRIDE_NAMES`.
  - `refine_plan()` mantiene un nombre mientras el plan refinado conserva su valor.
  - `refine_plan()` reconstruye el plan recibido y avisa con `PlanEditsDiscardedWarning` de las ediciones a mano que no conserva; el texto va también a `plan.warnings`.
- PR 31: `metric` (una o una lista, la primera ordena) en `plan()`, `refine_plan()`, `forecast*()`, `backtest*()` y `compare()`, que lo pasa por `plan()`.
  - `backtest*()` toman también `lags` y `window_features`.
  - `compare()` con una métrica repetida falla antes de correr.
  - MCP: `plan`, `refine_plan` y `compare` toman `metric`. `compare` sin ella ordena por la métrica elegida en el plan de la estrategia.
- PR 32: `use_exog`. `False` deja fuera las exógenas; `True` falla sin exógenas, con el baseline, con un foundation sin covariables y con ForecasterStats con solo categóricas.
  - El script multivariante selecciona `series_cols` cuando hay exógenas.
  - La explicación del multivariante nombra la serie que predice.
- PR 33: `differentiation` (entero de al menos 1, solo forecasters de ML).
  - Los lags y la ventana mínima de `create_cv()` reservan el orden; las window features por defecto sin sitio se dejan fuera y se explica.
  - `backtest*()` fallan antes de correr si el CV tiene otro orden.
  - `compare()` corre cada candidato con su orden sobre una copia del CV, y la explicación lo dice.
- PR 34: `calendar_features` (lista de CalendarFeatures, `[]` para ninguna), `target_transformer` (`'StandardScaler'` o `'none'`) y `dropna_from_series`, solo forecasters de ML.
  - Una variable de calendario que choca con una exógena usada falla, y también una elegida sin índice de fechas.
  - `dropna_from_series=False` falla si el estimador no acepta NaN.
  - Una decisión arrastrada por `refine_plan()` que ya no aplica falla diciendo su origen.
- PR 35: `render_plan_section` añade, tras los pasos de preprocesado, "Chosen by the user instead of the rules: ..." y "Plan warnings:", cada aviso por `_free_text`. `describe()` recorta los avisos a 15.
- PR 37: el CLI toma `--metric`, `--use-exog`, `--differentiation`, `--calendar-features`, `--target-transformer` y `--dropna-from-series` (`auto` para la regla) en `plan`, `refine-plan`, `forecast-code`, `backtest-code`, `forecast` y `backtest`, con y sin `--from-plan`; `forecast` y `backtest` toman también `--lags` y `--window-features`.
- PR 38: `profile(exog_columns=...)` elige las exógenas (en el orden de los datos, `[]` para ninguna).
  - Las demás columnas van al campo nuevo `DataProfile.unused_columns`, con una nota en `DataProfile.warnings`.
  - El chequeo de fechas repetidas ignora esas columnas.
  - Con un perfil guardado, `_refresh_profile` rellena `unused_columns`.
  - El script multivariante selecciona las series cuando el perfil deja columnas fuera, y el de foundation selecciona las exógenas futuras del perfil.
  - MCP: argumento `exog_columns` del tool `profile`, y `check_profile_names` revisa también las columnas dejadas fuera. CLI: `--exog-columns` en `profile` y `plan`.
- 18.1, decisión 1: `backtest_code()` rechaza un forecaster directo con `gap` con el error de `backtest()`. `create_cv()` avisa (`UserWarning`), porque su CV puede servir a los demás candidatos de `compare()`.
- 18.1, decisión 4: `profile()` rechaza las fechas día-primero cuya primera fecha también se lee mes-primero solo cuando una fecha posterior no encaja en la lectura mes-primero. El error da el consejo de día-primero, y su `hint` pide ISO 8601. Las que encajan en las dos lecturas se siguen leyendo mes-primero, como el script.
- 18.1, `internal_error`:
  - Un target casi todo infinito (o escrito fuera del rango de un float, que se lee como infinito) se queda sin PACF; `forecast()` y `backtest()` dan después el error de valores infinitos.
  - `context_length` debe ser un entero de al menos 1, como exige `FoundationModel`.
- 18.1, `plan(steps=100)` sobre 204 filas: `backtest()` falla antes de correr (`insufficient_data`, campo `cv`) cuando la primera ventana de entrenamiento no supera la ventana del forecaster, o no llega a ventana más `steps` en un forecaster directo. `create_cv()` y `backtest_code()` avisan. Los límites se comprobaron contra skforecast en el borde.
- 18.1, huso horario: cuando las fechas de los datos tienen zona y `initial_train_size` es una fecha sin ella (el valor por defecto de `create_cv()`), el script que ejecuta `backtest()` y devuelve `backtest_code()` lleva el número de observaciones hasta esa fecha, contado en la hora local de los datos. `cv_config` conserva la fecha.
- 18.1, `end_train` de series largas: la propiedad `DataProfile.span_start_date` (la primera fecha de la serie que empieza antes, si el tramo de `span_index_length` llega desde ella a la última fecha) sustituye a `start_date` al resolver `test_size` en `forecast()`.

**Desviaciones respecto a la sección 10, con su motivo.**
- Commit 0: no está en la sección 10. Lo exigía skforecast 0.26, sin el cual la suite no corría. Los datos que faltan o no son booleanos bloquean el modelo (criterio 1). El aviso de descarga mantiene "were not found" y "may download" (decisión 4 de 17.1), porque un backend puede guardar su propia copia (criterio 3).
- PR 30:
  - Un aviso, nunca un error, para que los bundles de 0.3 sigan funcionando (criterio 4).
  - Solo se comparan las claves de `forecaster_kwargs` que trae el plan recibido: una clave que solo tiene el plan reconstruido añade un valor, no lo descarta.
- PR 31: una métrica pasada con un plan debe coincidir con toda la lista que calcula (criterio 2). En el MCP, `compare` sigue la métrica del plan de la estrategia solo si se eligió (criterio 3). `compare()` en Python mantiene su valor por defecto, porque no recibe plan (criterio 4).
- PR 32:
  - ForecasterDirectMultiVariate en formato largo sigue rechazado: hacerlo funcionar cambia scripts y no está decidido.
  - El `compare` del MCP no lleva el `use_exog` del plan de la estrategia a los candidatos (documentado).
- PR 33: ForecasterStats y ForecasterFoundation siguen corriendo con un CV que tiene orden, porque skforecast no lo comprueba para ellos y corrían en la base (criterio 4). Las window features por defecto sin sitio se dejan fuera con explicación, en lugar de rechazar la llamada. El baseline que añade `compare()` corre sobre una copia sin orden, pero la nota de la explicación no lo nombra.
- PR 34: una variable de calendario más fina que la frecuencia (`hour` en datos diarios) se acepta, como en skforecast. `target_transformer` solo acepta el conjunto cerrado del render.
- PR 35: las dos líneas van después de los pasos de preprocesado, para que un paso no se lea como aviso.
- PR 37: opciones de texto con `auto` en lugar de pares de flags, porque un par de flags no puede pedir a `refine-plan` que vuelva a decidir.
- PR 38:
  - Un campo nuevo, `DataProfile.unused_columns`, que la sección 10 no preveía: sin él, los scripts multivariante y foundation no saben que hay otras columnas. Con él se arregla también el multivariante con un perfil guardado y una columna de más (10.4: "el script multivariante deja de ajustar como series las exógenas no usadas").
  - `--exog-columns` con `--from-profile` falla en lugar de ignorarse.
  - Un plan ejecutado sin su perfil se perfila de nuevo con todas las columnas: documentado, sin cambiar (pregunta abajo).
- 18.1, decisión 1: el aviso es un `UserWarning`, no una clase nueva.
- 18.1, `context_length`: un entero de numpy se acepta, porque el plan lo guarda como `int` de Python y funcionaba. `True` se acepta como en skforecast. No hay comprobación de varianza desbordada, porque `pacf` la calcula sin error y ningún caso llegaba a `internal_error`.
- 18.1, ventana: `backtest_code()` avisa en lugar de fallar. Fallar rompería una llamada que hoy devuelve un script, y el documento no lo decide (pregunta abajo).
- 18.1, huso horario: el script lleva un entero en lugar de la fecha, porque una fecha con desfase (`+02:00`) falla contra una zona con nombre (`Europe/Madrid`). Sin datos (`backtest_code()` con solo el perfil) y con una fecha que ya trae zona, todo queda como antes.
- 18.1, `end_train`: solo cambia `forecast()`. Los demás sitios que combinan `start_date` con `span_index_length` cambiarían resultados de llamadas que funcionan (pregunta abajo). Cuando el tramo no llega de la primera fecha a la última (datos horarios largos con zona cuyo tramo se cuenta como la serie más larga), se usa `start_date`, que falla como antes, en lugar de evaluar otra ventana sin error.

**Cambios para el usuario.**
- Python:
  - Argumentos nuevos, todos opcionales y keyword-only:
    - `metric`, `use_exog`, `differentiation`, `calendar_features`, `target_transformer` y `dropna_from_series` en `plan()`, `refine_plan()`, `forecast*()` y `backtest*()`; todos salvo `metric` en los candidatos de `compare()`, que toma `metric` como argumento propio;
    - `lags` y `window_features` en `backtest*()`;
    - `exog_columns` en `profile()`.
  - Campos nuevos: `ForecastPlan.overridden_fields` y `DataProfile.unused_columns`; ambos se guardan vacíos en el JSON de un plan o perfil por defecto.
  - Fallan antes de ejecutar, con código y campo, llamadas que fallaban dentro del script:
    - `backtest*()` con otro orden de diferenciación que el CV;
    - `backtest_code()` de un forecaster directo con `gap`;
    - `backtest()` con una primera ventana demasiado corta;
    - `compare()` con una métrica repetida;
    - `plan()` con un `context_length` que no es un entero positivo.
  - `profile()` falla con fechas día-primero que se leen mes-primero cuando se puede demostrar (antes fallaba `plan()`).
  - Funcionan llamadas que fallaban:
    - `profile()` de un target casi infinito, que ahora llega al error de infinitos;
    - `backtest()` de fechas con zona;
    - `forecast(test_size=...)` de series largas que empiezan en fechas distintas.
  - Otros resultados:
    - el multivariante con un plan guardado con `use_exog=False`, o con un perfil guardado y una columna de más, ajusta solo las series objetivo;
    - las explicaciones de un plan TimesFM 3.0, Moirai, TS-ICL, TabPFN o T0 nombran la licencia como skforecast;
    - el multivariante explica qué serie predice;
    - `compare(metric=...)` da a los planes de los candidatos la frase de la métrica elegida;
    - el contexto de `ask()` y `describe()` lleva las decisiones del usuario y los avisos del plan.
  - Avisos nuevos:
    - `PlanEditsDiscardedWarning` en `refine_plan()` de un plan editado a mano;
    - `create_cv()` con un forecaster directo y `gap`, o con una primera ventana demasiado corta;
    - `backtest_code()` con una primera ventana demasiado corta.
- CLI: las opciones de los overrides (`auto` para la regla) y `--exog-columns`; `backtest-code` de un directo con `--gap` y `backtest` con una ventana corta salen con 1 y su mensaje, sin repetir el aviso de `create_cv()`; `refine-plan --from-plan` de un bundle editado a mano imprime `PlanEditsDiscardedWarning` en stderr; los demás cambios de Python se ven igual.
- Servidor MCP:
  - Argumentos nuevos: `metric`, `use_exog`, `differentiation`, `calendar_features`, `target_transformer` y `dropna_from_series` en `plan` y `refine_plan`; todos salvo `metric` en los candidatos de `compare`; `metric` en `compare`; `exog_columns` en `profile`. La descripción de `exog_path` dice que hace falta cuando el plan usa exógenas.
  - Los resúmenes de planes y resultados llevan las líneas "Chosen by the user instead of the rules" y "Plan warnings" (PR 35).
  - `backtest` con un plan de otro orden de diferenciación que su estrategia es `invalid_argument` en `cv_id`.
  - T0 corre sin `--allow-model`; `model_not_allowed` lleva los datos nuevos de licencia; el aviso de descarga nombra el repositorio de los pesos.
  - Dejan de ser `internal_error`: `profile` de un target casi infinito y `plan` con `context_length` de texto.
  - `backtest` de un CSV con fechas en una zona funciona; `backtest` con una ventana corta es `insufficient_data`.
  - `profile` de fechas día-primero demostrables es `invalid_argument`.
  - `create_cv` lleva como notices los avisos del directo con `gap` y de la ventana corta.
  - El SKILL.md, su copia del plugin, `docs/api/mcp.md` y la guía del servidor lo dicen.

**Tests.** De 3763 pasados en `0.4.x` (`36babee`, ya con skforecast 0.26 fallaba al recoger; 3763 es la cifra de 18.1) a 4037, es decir, 274 más; en cada `/verify`, todos pasados salvo el omitido de siempre. Por commit (pasados): 3772 (commit 0), 3788 (PR 30), 3825 (31), 3846 (32), 3868 (33), 3891 (34), 3896 (35), 3904 (37), 3951 (38), 3972 (decisión 1), 3976 (decisión 4), 3987 (`internal_error`), 4014 (ventana), 4028 (huso horario) y 4037 (`end_train`).

**Paridad final.** Con `36babee` como base y el último commit de la rama, los cinco escenarios sin overrides dan resultados idénticos, sin ningún aviso en ninguno de los dos lados: h2o desde CSV, h2o desde DataFrame, bike_sharing con exógenas futuras, e items_sales ancho y largo. Se compararon el perfil, el plan, el script de `forecast_code()`, las predicciones y el script de `forecast()`, el CV, el script de `backtest_code()` y las predicciones, métricas y script de `backtest()`, y en modo evaluación (`test_size` igual a `steps`) las predicciones, métricas, script y `end_train`. La única diferencia son las dos claves nuevas, vacías: `"overridden_fields": []` en el JSON del plan y `"unused_columns": []` en el del perfil (también dentro del CV).

**Para el check de pago.** Lista completa, para una sola ejecución de `tools/ai/check_ask_context.py` con un modelo real antes de la release:
- Sección 3: la regla 4 de `llm/prompts.py` (`refit=False` por defecto) y las explicaciones del plan y del CV.
- Sección 12: las notas de `DataProfile.warnings` de los PRs 6 y 8 (filas ordenadas, series que terminan antes, huecos sumados en todas las series, fechas fuera de los años 1677 a 2262 en formato largo).
- Sección 13:
  - PR 9: la estrategia y las frases de ForecasterStats en `<backtesting_strategy>`, `<deterministic_summary>` y `compare()`;
  - PR 13: las cotas de intervalo de un backtest multiserie;
  - PRs 12 y 14: `llm/context.py`;
  - los candidatos de datos largos.
- Sección 14:
  - PR 17: el fichero que lee el script en `<script>`;
  - 4a: la razón del paso de categóricas con más de 15 columnas;
  - 4b: `<backtesting_strategy>` y el modo backtesting de un `backtest_code()`;
  - 4c: la nota de ForecasterStats en un `compare()` y la clasificación recortada.
- Sección 15: la nota de ForecasterFoundation en `<backtesting_strategy>`. Ejecutar los cuatro datasets de `check_ask_context.py`.
- Sección 18:
  - PR 23: la nota "No baseline: ..." con un intervalo asimétrico;
  - PR 27: la nota de `DataProfile.warnings` cuando los datos difieren del perfil;
  - punto 12: `llm/context.py`;
  - pregunta 7, pendiente: ForecasterStats que aconseja `dropna_from_series` (sección 12), un cambio de explicación que la tabla de 18.1 dejó para el check de pago y que esta fase no hizo.
- 18.1: la explicación de un plan refinado con LLM llega con sus párrafos en líneas con sangría.
- Esta fase:
  - Commit 0: el nombre de la licencia como lo registra skforecast, la frase de la cuenta del proveedor (TabPFN) y T0 sin pesos restringidos.
  - PR 30: el texto de `PlanEditsDiscardedWarning`, que va a `plan.warnings` y, desde el PR 35, al contexto.
  - PR 31: las dos frases de la métrica elegida.
  - PR 32: la frase de exógenas no usadas y la de la serie que predice el multivariante (en todo plan ForecasterDirectMultiVariate).
  - PR 33: las frases del orden de diferenciación y de las window features dejadas fuera, y la nota de diferenciación de `compare()`.
  - PR 34: las cuatro frases de calendario, escalado y NaN.
  - PR 35: `llm/context.py`, con las líneas "Chosen by the user instead of the rules" y "Plan warnings".
  - PR 38: la nota de `DataProfile.warnings` que nombra las columnas dejadas fuera, y la de un perfil guardado con columnas de más, que ahora lleva también `unused_columns`.
  - Los puntos de 18.1 no cambian lo que recibe el LLM: son errores y avisos de Python.
- Antes de lanzarlo: `check_ask_context.py` ya recorre ForecasterStats, `backtest_code()`, el formato largo y más de 15 candidatos o columnas categóricas (sección 15), pero ningún escenario suyo usa los overrides ni avisos del plan; solo los cubre el golden `code_generation_overrides_and_warnings` de los tests. Falta añadirle un escenario con ellos.

**Preguntas nuevas para el autor.**
1. Ventana corta (18.1): `backtest_code()` avisa y devuelve el script, mientras el directo con `gap` falla en `backtest_code()` por tu decisión. ¿Se rechaza también aquí?
2. Series largas que empiezan en fechas distintas: siguen contando desde la primera fecha más tardía (`start_date`) con la longitud del tramo completo:
   - el `initial_train_size` por defecto de `create_cv()` (`derive_cv_defaults`), que puede caer después de los datos (`'2023-05-10'` con datos que acaban el 2023-04-10);
   - el recuento de folds de `build_cv`, de la comprobación de `skip_folds` y de `resolve_cv_config`;
   - la fecha que recibe el LLM al refinar el CV.

   ¿Pasan a `span_start_date`? Cambia el CV por defecto y `n_folds` de esos datos.
3. PR 38: un plan ejecutado sin su perfil se perfila otra vez con todas las columnas, también las que `exog_columns` dejó fuera. ¿Se guarda la selección en el plan (una segunda fuente de verdad), o se avisa cuando el plan viene de un perfil con columnas dejadas fuera?
4. Fechas día-primero que encajan en las dos lecturas (ningún día pasa de 12, como inicios de mes `01/MM/YYYY`): se leen mes-primero sin aviso, como el script. ¿Una nota en `DataProfile.warnings`? Añadiría un aviso a llamadas que funcionan.
5. Una variable de calendario más fina que la frecuencia (`hour` en datos diarios) se acepta (PR 34). ¿Se rechaza o se avisa?
6. ForecasterDirectMultiVariate en formato largo sigue rechazado (PR 32). ¿Se implementa?
7. El `compare` del MCP no lleva el `use_exog` del plan de la estrategia a los candidatos (PR 32). ¿Se mantiene?
8. Huso horario: `backtest_code()` sin datos de un perfil con zona y una fecha `initial_train_size` que ya trae zona siguen fallando dentro de skforecast (mensaje de `8a0a10b`), y la revisión encontró que el fragmento de `create_cv().code` también, si se ejecuta solo. ¿Se guarda la zona en el perfil (sería un campo nuevo)?

**Pendiente o anotado.**
- El PR 36 (opcional) y la fase 6 (10.12), fuera de esta fase por indicación.
- Pendientes de 18.1 que esta fase no tocó:
  - `compare()` con un intervalo asimétrico no emite aviso (solo la frase de la explicación);
  - los mensajes de la CLI usan los nombres de Python (`refit=True`) en lugar de las opciones (`--refit`);
  - las variantes ISO 8601 mezcladas en una columna de fechas se siguen rechazando, por decisión del autor para esta fase;
  - unificar las dos tablas de periodos (pregunta 5 de la sección 18) queda para la fase 6.
- Encontrado por las revisiones de esta fase, ya en la base, sin cambiar:
  - un `initial_train_size` de tipo `pd.Timestamp` sin zona hace fallar `backtest()` con `TypeError` en `build_cv_explanation` (la sección 14 anotaba lo mismo para `describe()` de un `backtest_code()`);
  - perfilar datos subdiarios largos con zona cuyas series empiezan unas a medianoche y otras no da `TypeError` en `_resolve_observation_counts`;
  - un target `Float64` (nullable) con un infinito da `TypeError` en `_check_target_is_constant`;
  - `profile()` con valores infinitos emite el `RuntimeWarning` de numpy.
- También de las revisiones: con zona horaria y cambio de hora, `end_train` se escribe con el desfase de la primera fecha (`11:00:00+01:00` para un corte a las 12:00 locales en verano); el instante es correcto.
- `_compute_min_train_size` (CV por defecto) y `plan_window_size` (ventana de 18.1) calculan la ventana por separado; unificarlas cambiaría el CV por defecto, así que se propone para la fase 6.

**Qué queda para 0.4.0.**
- La fase 6 (10.12): rendimiento y limpieza, antes del check de pago.
- El check de pago, una sola vez al final, con la lista de arriba (secciones 3, 12, 13, 14, 15, 18, 18.1 y esta fase), después de añadir a `check_ask_context.py` un escenario con overrides y avisos del plan.
- Las preguntas de arriba y las abiertas de las secciones anteriores.
- El plan de release de 17.1: skforecast 0.26.0, después skforecast-ai 0.4.0 en PyPI y solo entonces el merge de `0.4.x` a `main`.

**Siguiente:** la fase 6 y, al final, el check de pago.

### 19.1 Revisión del autor y correcciones

Antes de mergear la fase 5b, una verificación independiente comparó la base (`36babee`) con la rama (`17fb098`) en cuatro frentes: los overrides, `exog_columns` y los seis arreglos de 18.1, el servidor MCP con el bloqueo de modelos foundation y el contexto del LLM, y la suite con la documentación. La rama se ejecutó con skforecast instalado desde `0.26.x` (con los campos nuevos de `FoundationModelInfo`); ningún modelo foundation se ejecutó de verdad, porque no hay backend instalado. Las correcciones van como commits nuevos al final de `feature/overrides`; ninguno subido se reescribió.

**Verificación.**
- Suite: 4037 pasados y 1 omitido, como dice la sección 19; ruff limpio; la documentación construye sin avisos. De 58 mutaciones hechas a mano, los tests detectaron 54.
- Sin overrides, perfil, plan, scripts, predicciones, métricas y avisos son idénticos a la base en 10 conjuntos; 181 backtests que corrían en la base dan lo mismo.
- Overrides: 114 casos por familia de forecaster con el script igual al ejecutado y ejecutable como fichero; 543 valores inválidos rechazados con su campo; ningún intento de inyección de código llegó a ejecutarse (tampoco por la CLI ni el servidor).
- Bloqueo por licencia: sin forma de saltárselo en 34 variantes del identificador. Corren sin `--allow-model` Chronos-2, TimesFM 2.5, TabICL, Nori y T0; necesitan la opción TimesFM 3.0, Moirai, TabPFN y TS-ICL.
- Servidor: los 96 CSV y scripts de la paridad por stdio son idénticos a la base; los vectores de seguridad anteriores se comportan igual.

**Fallos encontrados y corregidos.**

| Qué fallaba | Corrección | Commit |
|---|---|---|
| `compare()` sin candidatos marcaba los planes de sus candidatos con `overridden_fields=['forecaster']`, y `describe()`, el servidor y el contexto de `ask()` decían "Chosen by the user instead of the rules: forecaster" | Los candidatos automáticos y el baseline solo conservan `metric` cuando se pasó a `compare()`. Los nombres se escriben en una línea en el contexto | `3b90f83` |
| Un plan hecho con `exog_columns` y ejecutado sin su perfil volvía a usar todas las columnas, sin aviso (MAE 20.8 con el perfil frente a 0.98 sin él en el caso medido) | El plan guarda la selección (`ForecastPlan.exog_columns`, `None` cuando el perfil no dejó nada fuera) y los datos se perfilan con ella (pregunta 3) | `943e2f2` |
| Con series largas que empiezan en fechas distintas, el CV por defecto podía caer después de los datos y `cv_config` anunciaba más folds de los que corrían; `backtest()` daba un `ValueError` crudo (`internal_error` en el servidor) | El CV por defecto, los recuentos de folds y las fechas que recibe el LLM cuentan desde `span_start_date` (pregunta 2). Una estrategia que skforecast no puede partir es un `InvalidInputError` | `5e9ec78` |
| `backtest_code()` devolvía un script que falla cuando la primera ventana es más corta que la del forecaster | Lo rechaza, como `backtest()` (pregunta 1). El remedio solo nombra lags y window features para los forecasters que los tienen | `5e9ec78` |
| Datos horarios en una zona con cambio de hora: `cv_config` decía 5 folds y el script ejecutaba 6, y podía mostrar una hora que no existe (`2023-03-26 02:00:00`) | El perfil guarda el nombre de la zona (`DataProfile.time_zone`) y las posiciones y fechas de una estrategia se cuentan sobre las horas locales (pregunta 8). Sin zona, en UTC o con desfase fijo no cambia nada | `ff8ddd5` |
| `plan(differentiation=67)` culpaba a `lags`, que el usuario no pasó; `refine_plan(differentiation=32)` fallaba donde `plan()` funciona | El error nombra `differentiation`; `refine_plan()` vuelve a elegir los lags y ventanas que eligieron las reglas, dejando sitio al orden | `22f10eb` |
| Notas de versión demasiado largas y tres entradas que describían mal la 0.3.1; el SKILL.md no describía los avisos nuevos de `create_cv`; la descripción del tool `compare` seguía diciendo que ordena por la métrica del perfil | Reescritas | `8a0263b` |

**Decisiones del autor sobre las preguntas de la sección 19.**

| Pregunta | Decisión | Estado |
|---|---|---|
| 1 | Ventana corta: `backtest_code()` la rechaza | Hecho (`5e9ec78`) |
| 2 | Series que empiezan en fechas distintas: pasar a `span_start_date` | Hecho (`5e9ec78`) |
| 3 | Plan sin su perfil tras `exog_columns`: el plan guarda la selección | Hecho (`943e2f2`) |
| 4 | Fechas día-primero ambiguas: sin nota | Sin cambios |
| 5 | Variable de calendario más fina que la frecuencia: avisar, no rechazar | Pendiente (impacto bajo: la columna es constante) |
| 6 | ForecasterDirectMultiVariate en formato largo: no en 0.4.0 | Sin cambios |
| 7 | `use_exog` en el `compare` del servidor | No se lleva a los candidatos (abajo) |
| 8 | Zona horaria en el perfil | Hecho (`ff8ddd5`) |

**No se hizo, y por qué.**
- Pregunta 7. Llevar `use_exog=False` solo a los candidatos explícitos dejaría fuera a los automáticos, que `compare()` resuelve dentro del núcleo, y hacerlo bien pide un argumento nuevo en `compare()` (API, CLI y documentación). Con el commit `943e2f2` la vía que ya existe es completa: `profile` con `exog_columns: []` compara sin exógenas en todos los candidatos y el plan del ganador lo mantiene. El SKILL.md lo dice ahora.
- Con la hora repetida del cambio de otoño, una fecha que cae en ella se coloca en su segunda aparición: `cv_config` y el script coinciden, con una observación más de entrenamiento que el tamaño calculado.

**Pendiente.**
- Con una build de skforecast anterior a su PR #1332 (también numerada 0.26.0), un plan foundation falla con un `AttributeError` crudo.
- Test inestable: en 3 de 7 ejecuciones completas de la verificación falló un test distinto de `tests/tests_mcp` por un `ResourceWarning` de un socket sin cerrar. No se reprodujo en las ejecuciones locales de esta revisión; queda para la fase 6 ver si viene de la base.
- Tests que las mutaciones no cubren: los lags que reservan el orden de diferenciación, la nota de diferenciación de `compare()` con el baseline, y el recurso de `span_start_date` cuando el tramo no cuadra.
- Mensajes: un valor inválido en un candidato de `compare()` no se rechaza al principio (el candidato falla y queda el último); cambiar a Stats, baseline o Foundation en `refine_plan()` descarta sin aviso la diferenciación, el calendario y el transformador; `exog_columns` con nombres de columna enteros; las fechas día-primero con año de dos cifras escapan a la comprobación de 18.1.
- Sin página de usuario para los overrides de Python: solo la referencia de la API, la guía de la CLI y las páginas del MCP.

**Sincronización con skforecast.** El skill `foundation-forecasting` y `llms-base.txt` enseñaban `info.license_restriction`, que la 0.26 eliminó. Corregido en skforecast y sincronizado desde `0.26.x` (7 ficheros de skills y `llms-base.txt`; el inventario de 17 skills no cambia, las estimaciones de tokens sí).

**Para la lista del check de pago.** Los skills sincronizados son parte de lo que `ask()` envía. Además de la lista de la sección 19: el escenario `compare_default` ya no lleva la línea "Chosen by the user"; con datos con zona horaria, el `<script>` lleva un `initial_train_size` entero mientras la estrategia muestra la fecha.

**Tests.** De 4037 a 4055 (más 1 omitido), en macOS con el entorno conda local y skforecast instalado desde `0.26.x`.

## 20. Fase 6: hecho

Rendimiento y limpieza (10.12), lo último de código antes de la release 0.4.0, en la rama `chore/performance-cleanup`, creada desde `0.4.x` (`8deb000`). Un commit por punto, en el orden pedido, cada uno subido al terminar. Antes de cada commit se pasaron `/verify` (lint, tests afectados, suite completa y, si había documentación, el build), el script de paridad contra la línea base, el subagente `conventions-reviewer` y `/code-review`; lo que encontraron se corrigió antes de subir, y los mensajes de los commits lo dicen. Ningún commit subido se reescribió y ninguno necesitó una corrección posterior. GitHub no ejecuta los tests de esta rama: la única comprobación es la de la sesión (Linux, Python 3.11.15, 4 CPU, skforecast 0.26.0, pandas 2.3.3; sin `chronos-forecasting` ni `xgboost`, así que el candidato foundation queda fuera de `compare()` y el de XGBoost falla en los conjuntos multiserie, igual en la base y al final).

Goldens: los de render (`tests/tests_rendering`), los del contexto del LLM (`golden` y `golden_describe`) y los de esquemas del MCP no cambian en ningún commit.

| Commit | Punto | Contenido |
|---|---|---|
| `9cecadb` | Base | Un test de `compare()` que dependía de tener instalado el backend foundation |
| `1aa13f1` | 1 | Scripts de paridad y de tiempos (`tools/perf/`) y la línea base |
| `7828763` | 3 | `perf`: no reconvertir una columna que ya es de fechas |
| `05e7ae3` | 3 | `perf`: colocar los valores de cada serie en su rejilla por posición |
| `81d8909` | 1 | El perfil del servidor sigue los hilos de trabajo |
| `7d0ba79` | 3 | `perf`: perfilar una vez los mismos datos con un perfil guardado |
| `a319da7` | 4 | Código muerto |
| `f97b8e2` | 4 | Una sola definición de los conjuntos de forecasters y de tipos de tarea |
| `c56c4fd` | 4 | Un solo cálculo de la ventana del forecaster |
| `ad1cc83` | 5 | Listado de los periodos estacionales de las dos tablas (no se unifican) |
| `4912b1c` | 4 | Comentarios y docstrings que describían un comportamiento anterior |
| `5c3908e` | 6a | Plugin para encontrar el test que deja un recurso abierto |
| `5cedfbc` | 6b | Tests de lo que las mutaciones de 19.1 no cubrían |
| `03c9fa1` | 6c | Aviso por una variable de calendario más fina que la frecuencia |
| `788aeb6` | 6d | Escenarios con overrides, avisos del plan y zona horaria en `check_ask_context.py` |
| `dc7d8a1` | 3 | Nota de versión conjunta del rendimiento |
| `0d1483a` | 1 | Mediciones finales (`tools/perf/results/final_*.json`) |
| `4f147f4`, `be45f88` | 5 | Docstring del listado de periodos (multiplicadores y longitud de línea) |

**Commit previo a la línea base.** En la base (`8deb000`) la suite daba 4051 pasados, 1 fallado y 1 omitido en esta sesión: `test_compare_overridden_fields_of_automatic_candidates_and_baseline` dependía de tener instalado `chronos-forecasting` (sin él, `compare()` emite `MissingBackendWarning`, que la suite convierte en error). `9cecadb` lo hace independiente del backend, como el test vecino de `MissingBackendWarning`, sin tocar el paquete.

### 20.1 Línea base y herramientas

`tools/perf/` (README propio) tiene dos scripts que se pueden volver a ejecutar en cualquier revisión:
- `parity.py dump` guarda, para 8 conjuntos (h2o desde CSV y desde DataFrame, h2o con exógenas, bike_sharing con exógenas futuras, items_sales ancho y largo, datos largos con series que empiezan en fechas distintas y datos horarios en Europe/Madrid que cruzan el cambio de hora de primavera), el perfil, el plan, los scripts de `forecast_code()` y `backtest_code()`, `create_cv()`, las predicciones y métricas de `forecast()` (predicción y `test_size`), `backtest()` y `compare()` por defecto, con los avisos de Python de cada llamada; `parity.py compare` lista cada diferencia. Dos volcados de la base dieron 0 diferencias (determinismo comprobado), y una alteración de 1e-12 en una predicción o un aviso de más se detectan.
- `timing.py` mide cada llamada pública y cada tool del servidor por stdio (con el arranque) en h2o (204 filas), bike_sharing (17 520 filas horarias con 6 exógenas) y store_sales (913 000 filas en formato largo, 500 series; la descarga funcionó, no hizo falta el sintético), con la parte de cada paquete según cProfile (tiempo propio sumado por directorio de instalación), `-X importtime` y el pico de memoria de `profile()` con tracemalloc.

Además: `seasonal_periods.py` (punto 5) y `gc_after_test.py` (punto 6a). Los resultados están en `tools/perf/results/` (`baseline_*` y `final_*`). El volcado de paridad de la base no se guarda en el repo (2,5 MB): se rehace con `parity.py dump` sobre `9cecadb`.

Máquina: 4 CPU, Linux, sin otra carga durante las mediciones. Mediana de 5 ejecuciones (1 cuando la llamada pasa de 60 s: `compare` en store_sales). Los tiempos de llamadas por debajo de 20 ms varían de una tanda a otra tanto como entre versiones (la propia base dio `create_cv` de h2o entre 10 y 17 ms en dos tandas), así que no se comparan.

### 20.2 Tiempos: línea base y final

Segundos (mediana); "propio" es el tiempo de las funciones de `skforecast_ai` según cProfile, que ralentiza el código Python, así que es una cota superior (la línea base se midió con la primera versión del script, que atribuía por la ruta del fichero; la subida en `1aa13f1`, por el directorio de instalación; para el paquete coinciden). `plan`, `refine_plan` y `forecast_code` tardan menos de 1 ms, salvo `plan` en store_sales (1,2 ms en la base y 1,3 ms al final).

| Llamada | h2o base | h2o final | bike_sharing base | bike_sharing final | store_sales base (propio) | store_sales final (propio) |
|---|---|---|---|---|---|---|
| `profile` | 0,005 | 0,009 | 0,009 | 0,008 | 3,530 (0,250) | 3,045 (0,253) |
| `create_cv` | 0,010 | 0,018 | 0,004 | 0,004 | 0,008 (0,005) | 0,008 (0,005) |
| `backtest_code` | 0,007 | 0,005 | 0,006 | 0,005 | 1,700 (0,191) | 0,161 (0,015) |
| `forecast` | 0,022 | 0,020 | 0,336 | 0,335 | 8,526 (0,258) | 7,266 (0,076) |
| `backtest` | 0,060 | 0,061 | 1,667 | 1,725 | 26,170 (0,261) | 24,799 (0,086) |
| `compare` | 34,659 | 36,673 | 8,032 | 9,052 | 65,442 (0,926) | 62,820 (0,303) |

En store_sales, `backtest_code`, `forecast`, `backtest` y `compare` se miden con el mismo asistente y el mismo perfil guardado, como en un flujo de trabajo: desde la segunda llamada, el perfil de los datos ya está calculado (`7d0ba79`). La primera llamada de un asistente nuevo paga la huella (unos 0,2 s en store_sales). Medidos intercalados con la base (`9cecadb` en un worktree, mediana de 5, dos tandas): `backtest_code` 1,728 y 1,813 s frente a 0,175 y 0,145 s; `forecast` 10,286 y 9,792 s frente a 7,941 y 7,746 s; `forecast(test_size=7)` 13,326 y 14,263 s frente a 12,863 y 12,055 s. En h2o y bike_sharing las diferencias son ruido: el código propio no pasa del 10 % en ninguna llamada de más de 20 ms, y el tiempo está en skforecast (Auto-ARIMA de `compare` en h2o), pandas y el estimador.

Servidor MCP por stdio (mediana de 5 sesiones; 1 en store_sales). Arranque: 2,59, 2,62 y 2,61 s en la base; 2,69, 2,62 y 2,61 s al final. Las herramientas sin datos (`get_code`, `get_failure`, `list_objects`, `describe_object`) tardan 6 a 10 ms en las dos.

| Tool | bike_sharing base | bike_sharing final | store_sales base | store_sales final |
|---|---|---|---|---|
| `profile` | 0,182 | 0,090 | 3,964 | 3,541 |
| `create_cv` | 0,019 | 0,129 | 0,056 | 0,055 |
| `backtest` | 1,817 | 1,863 | 28,014 | 27,199 |
| `compare` | 9,303 | 8,650 | 68,343 | 63,659 |
| `forecast` | 0,430 | 0,534 | 8,869 | 7,858 |

El `create_cv` de bike_sharing no es una regresión: en un proceso nuevo, una recolección completa del recolector de basura (0,10 a 0,12 s con el montón del servidor) caía en la base dentro de `profile` y ahora dentro de `create_cv`. Con `gc` desactivado, las dos versiones dan `profile` 0,11 s y `create_cv` 0,02 s; la recolección se vio con `gc.callbacks`. En proceso, con el mismo servidor y 9 repeticiones intercaladas, `create_cv` da 8 a 10 ms en las dos. El código del propio servidor (`mcp/server.py`, envoltorios y registro) pesa menos del 0,1 % de una sesión.

Importación (mediana de 5): `import skforecast_ai` 1,71 s en la base y 1,79 s al final; `import skforecast_ai.mcp` 2,41 y 2,61 s. Los módulos propios suman 0,13 s; el resto es scipy (0,71 s), mcp_types (0,67 s), numpy, pandas, sklearn y skforecast. Pico de memoria de `profile()` en store_sales: 83,2 MiB para 68,7 MiB de datos, igual en la base y al final.

### 20.3 Optimizaciones

Las tres, con paridad sin diferencias en los 8 conjuntos y los goldens intactos.

| Commit | Qué | Medida (store_sales, misma máquina, mediana de 5) |
|---|---|---|
| `7828763` | `_frame_index_bounds` llamaba a `pd.to_datetime` sobre la columna de fechas de cada serie, aunque ya fuera de fechas (89 % de la función según line_profiler; 22 % de `profile()` y 42 % de `backtest_code()`). Se salta cuando la columna ya es datetime64 (con o sin zona, cualquier unidad), que devuelve los mismos valores | `profile` 3,507 a 2,801 s (-20 %); `backtest_code` 1,822 a 1,208 s (-34 %); `forecast` 9,012 a 7,888 s (-12 %); `backtest` 26,120 a 25,142 s (-4 %) |
| `05e7ae3` | `_series_spans` construía un frame por serie y lo reindexaba sobre la rejilla. Ahora toma las posiciones de cada serie y coloca los valores con `get_indexer`; mismo resultado (comprobado en las 500 series y en 1200 casos aleatorios en la revisión) | `_series_spans` 0,681 a 0,385 s; `forecast(test_size=7)` 12,38 y 12,18 a 11,34 y 11,72 s (-4 a -8 %); en modo predicción, dentro del ruido |
| `7d0ba79` | `_refresh_profile` volvía a perfilar los datos en cada llamada con un perfil guardado (85 % de `backtest_code`, 12 % de `forecast`). El asistente guarda los perfiles de datos que calculó (los 8 usados por última vez), por una huella de los datos (`_frame_fingerprint`) y las columnas del perfil | Llamada repetida: `backtest_code` 1,034 a 0,149 s (-86 %), `forecast` 8,132 a 7,125 s (-12 %). Primera llamada: `backtest_code` 1,054 a 1,265 s (la huella), `forecast` igual |

Detalles de `7d0ba79`: la huella no se da (y se perfila como antes) para valores de objeto que no sean todo texto (pandas trata igual `1` y `'1'`), MultiIndex, valores que no se pueden hashear o texto que no se puede codificar; distingue las categorías completas, `None` de `NaN`, la frecuencia y el nombre del índice. La caché no lleva lock para que el asistente se pueda seguir copiando y serializando con `pickle` (un lock lo rompía; lo encontró `/code-review`). El perfil guardado solo se compara, nunca se devuelve.

### 20.4 Medido y dejado como está

| Qué | Medida | Motivo |
|---|---|---|
| PACF de `profile()` | 1,9 s de 2,8 s en store_sales | El 80 % es `pacf` de skforecast; el bucle propio por serie, 0,15 s |
| Resto de `create_data_profile` | Cada parte por debajo del 10 % de `profile()` tras `7828763`: estadísticos del target 0,2 s, fechas repetidas 0,2 s, fechas por serie 0,15 s, orden 0,1 s, índice de muestra 0,09 s | Bajo el umbral. El TODO de `_extract_datetime_index` (máscaras) sigue: mide un 3 % |
| Bucle por serie de `_compute_series_metrics` | 0,18 s (7 % de `profile()`) | Bajo el umbral; un `groupby().agg()` daría 0,05 s |
| Segundo `_series_spans` en modo evaluación | 0,39 s (3 % de la llamada) | Bajo el umbral tras `05e7ae3` |
| Perfil de datos que difieren del guardado | Se perfilan dos veces (datos y `profile()`) | Reusar el primero obliga a reemitir sus avisos a mano, que cambia de dónde vienen (filtros por módulo y registro de avisos ya mostrados) |
| Huella SHA-256 del CSV en el servidor | 21 ms por cálculo en 20 MiB, dos por llamada (1 % de `profile`) | Bajo el umbral |
| Código del servidor | Menos del 0,1 % de una sesión | Bajo el umbral |
| Importación y arranque del servidor | 1,7 y 2,4 s; propio 0,13 s | El resto es de dependencias |
| `plan`, `refine_plan` y `forecast_code` (1,3 ms como mucho) | El código propio es casi toda la llamada | Nada que ganar en tiempo absoluto |
| `create_cv` (4 a 18 ms) | El tiempo está en pandas y skforecast (`TimeSeriesFold.split`); lo propio, un 3 a 6 % | Bajo el umbral |
| `backtest` y `compare` | Más del 98 % dentro del script (skforecast, pandas, el estimador) | No es código propio |
| v0.3.1 como caja negra (opcional de 10.12) | No se midió | Apunta a skforecast 0.25 y pediría otro entorno; 10.12 lo deja como opcional |

### 20.5 Limpieza

- Código muerto (`a319da7`): `MULTI_SERIES_FORECASTERS`, `MULTIVARIATE_FORECASTERS`, `SINGLE_ML_FORECASTERS` y `STATS_FORECASTERS` de `_constants.py`; `_lazy_import_cv_agent` de `llm/__init__.py`; el parámetro `api_key` de `_check_base_url`; `detect_gaps`, que solo usaba su test (los huecos los cuenta `count_missing_timestamps`; su test pasa a `test_count_missing_timestamps.py` con los dos casos que solo él cubría). Cada nombre se buscó en el paquete, los tests, `tools`, `docs`, `plugin` y `mkdocs.yml`, también como texto.
- Duplicados (`f97b8e2`, `c56c4fd`): los `_DIRECT_FORECASTERS` y `_LAG_FORECASTERS` de `_last_window.py` y `_future_exog.py` pasan a `DIRECT_FORECASTERS` y `AUTOREG_FORECASTERS`; la tupla de tipos de tarea de ML, escrita en cinco sitios, es `ML_TASK_TYPES`; el `"Direct" in fc` del presupuesto de lags es `fc in DIRECT_FORECASTERS`; `_compute_min_train_size` usa `plan_window_size` (mismo valor en 1350 planes construidos con `plan()` y en 8640 combinaciones de `forecaster_kwargs`; solo difieren argumentos que la validación rechaza). Los conjuntos de candidatos de `forecaster_selection.py` (listas ordenadas) y el `Literal` del MCP (esquema) se quedan.
- Comentarios y docstrings (`4912b1c`), encontrados con un barrido del paquete y comprobados contra el código: `start_date` frente a `span_start_date`, `_cv_in_time_zone`, la comprobación de fechas de `load_exog`, el parámetro `overrides`, las Notes de `backtest()` y `backtest_code()` (ya toman `lags` y `window_features`), el rechazo de la primera ventana corta también en `backtest_code()`, `DataProfile.time_zone`, las columnas de `ForecastResult.metrics`, `exog_columns` fuera de la comparación de `refine_plan()`, los errores de fechas de `create_data_profile` y el TODO de `format="mixed"`.
- No se reorganizó `assistant.py` ni `mcp/server.py`, no se movió código entre módulos y no cambió ningún nombre público.

### 20.6 Tablas de periodos estacionales (punto 5)

`tools/perf/seasonal_periods.py` recorre las 218 frecuencias que infiere pandas (cada alias, anclado, sin multiplicar y multiplicado por 2, 3, 4, 5, 6, 7, 10, 12, 14, 15, 20 y 30) y los 20 alias de pandas 2.1: **104 de 238 dan un periodo distinto** en `FREQUENCY_TO_SEASONAL_PERIOD` (Auto-ARIMA, la regla de ForecasterStats y el baseline) y en `estimate_seasonality` (horizonte del PACF, window features y el baseline cuando la tabla no tiene la frecuencia). Unificar cambiaría periodos, así que no se unificaron. Muestra:

| Frecuencia | Tabla | `estimate_seasonality` | Baseline |
|---|---|---|---|
| `5min`, `10min`, `15min`, `30min` (y `5T` a `30T`) | 288, 144, 96, 48 (un día) | [12, 288], [6, 144], [4, 96], [2, 48] (primero la hora) | el de la tabla |
| `2D` | 7 | [3, 182] | 7 |
| `3D`, `2MS`, `2QS-OCT`, `2W-SUN`, `3h`, `s`, `10s`, ... | ninguno: Auto-ARIMA sin `m` | 2, 6, 2, 26, 8, 3600, 360 (el primero) | el de `estimate_seasonality` |
| `AS-JAN` | 1 | ninguno | 1 |

### 20.7 Pendientes de 19.1 (punto 6)

- 6a, test inestable de `tests/tests_mcp` (`5c3908e`): **no se reproduce en Linux**. 10 ejecuciones completas con `-n auto` limpias, y `tests/tests_mcp` (dos veces) y la suite completa (una) con un plugin que ejecuta `gc.collect()` tras cada test, `-X dev` y `ResourceWarning` como error, también limpias; el plugin sí detecta un socket o un bucle sin cerrar en un test de prueba. No hay recurso que cerrar y no se añadió ningún filtro. `tools/perf/gc_after_test.py` queda para repetirlo en macOS, donde se vio: hace fallar al test que deja el recurso, con la línea que lo creó si se usa `PYTHONTRACEMALLOC`. Sin entrada en la release.
- 6b, tests de las mutaciones (`5cedfbc`): los lags que reservan el orden de diferenciación (df_single: [1, 2, 3, 4, 5, 7] sin orden y [1, 2, 3, 4] con `differentiation=29`), la nota de diferenciación de `compare()` que no nombra al baseline, el recurso de `span_start_date` con un tramo más corto o más largo, y la frase de exógenas no usadas cuando la regla no usaba ninguna. Cada test se comprobó contra su mutación; `conventions-reviewer` encontró dos mutaciones que aún pasaban y quedaron cubiertas.
- 6c, aviso de calendario (`03c9fa1`, con entrada en la release dentro de la de los overrides, que son de esta versión): una variable elegida más fina que la frecuencia con columna constante (`hour` en datos diarios, `day_of_week` o `weekend` en semanales, `day_of_month` en `MS`) se mantiene y avisa con un `UserWarning` cuyo texto va también a `plan.warnings`. Se calcula con `CalendarFeatures` sobre la rejilla del perfil; `/code-review` encontró un falso aviso en datos con zona que no empiezan a medianoche, corregido con su test.
- 6d, `check_ask_context.py` (`788aeb6`): escenarios `overrides_plan` y `time_zone_backtest_code`, construidos en los cuatro conjuntos con `--dry-run` (no se lanzó sin él).

### 20.8 Paridad y tests

**Paridad final.** `parity.py compare` entre la base y el último commit: **sin diferencias** en los 8 conjuntos (perfil, plan, scripts, CV, predicciones, métricas y avisos de cada llamada). Se pasó también antes de cada commit de código.

**Tests.** De 4051 pasados, 1 fallado y 1 omitido en `8deb000` a **4087 pasados y 1 omitido**: 4052 (`9cecadb`), 4074 (`7d0ba79`, 22 de la huella y la caché), 4070 (`a319da7`, fuera los casos de `detect_gaps`), 4074 (`5cedfbc`) y 4087 (`03c9fa1`).

### 20.9 Preguntas nuevas para el autor

1. Tablas de periodos (20.6): ¿se unifican, y en qué sentido? Si `estimate_seasonality` manda, Auto-ARIMA recibe `m` en las frecuencias multiplicadas (26 en `2W-SUN`, 8 en `3h`) y el baseline de datos de 5 a 30 minutos repite la hora en vez del día; si manda la tabla, el PACF y las window features de esos datos cambian. Cualquiera de las dos cambia scripts y resultados.
2. Datos con zona horaria cuya primera fecha no es medianoche: `start_date` se escribe con el desfase de esa fecha (el contexto de bike_sharing empieza en `2012-10-09 18:00:00+02:00`), `create_cv()` arrastra ese desfase a fechas de otra estación (`initial_train_size: 2012-12-07 01:00:00+02:00`, una hora antes de la hora local que parece) y las posiciones se cuentan en la rejilla regular, no en la local. Lo encontró la revisión del punto 4 y se ve en el escenario `time_zone_backtest_code` de bike_sharing. Arreglarlo (escribir `start_date` en hora local sin desfase) cambia perfiles, CV y scripts de esos datos: ¿para 0.4.0 o 0.5.0?
3. Datos que difieren de un perfil guardado: se siguen perfilando dos veces (20.4). ¿Se acepta, o se reemiten los avisos del primer perfil?
4. `refine_plan()` no compara `ForecastPlan.exog_columns`: una edición a mano de ese campo se pierde sin `PlanEditsDiscardedWarning`. ¿Se compara (el campo viene del perfil)?
5. 6a: ¿se ejecuta `tools/perf/gc_after_test.py` en macOS para ver si el aviso vuelve a salir y en qué test?
6. La primera llamada de un asistente nuevo con un perfil guardado paga la huella de los datos (0,2 s en store_sales). ¿Se acepta, o se calcula también en `profile()` (que la pagaría siempre)?

### 20.10 Para el check de pago

Además de la lista de 19 y 19.1:
- El texto del aviso de calendario de 6c, que llega al contexto en "Plan warnings".
- Los dos escenarios nuevos de `check_ask_context.py`; en `time_zone_backtest_code` de bike_sharing, la fecha con desfase de la pregunta 2 (la lista de comprobación dice que no se marque a ciegas).
- Ningún otro cambio de esta fase toca lo que recibe el LLM: los goldens de contexto no cambiaron.

### 20.11 Qué queda para 0.4.0

- El check de pago, una sola vez, con la lista de las secciones 3, 12, 13, 14, 15, 18, 18.1, 19, 19.1 y 20.10, y los cuatro conjuntos de `check_ask_context.py` (`overrides_plan` y `time_zone_backtest_code` ya están).
- Las preguntas de arriba y las abiertas de las secciones anteriores.
- El plan de release de 17.1: skforecast 0.26.0, después skforecast-ai 0.4.0 en PyPI y solo entonces el merge de `0.4.x` a `main`.

**Siguiente:** el check de pago.

### 20.12 Revisión del autor y correcciones

Antes de mergear la fase 6, una verificación independiente comparó la base (`8deb000`) con la rama (`d65fcf1`) en macOS, con numpy 2.5.3 y `chronos-forecasting` instalado: la paridad y la memoria de perfiles, los tiempos con el test inestable, y el aviso nuevo con los tests y la documentación. Las correcciones van como commits nuevos al final de `chore/performance-cleanup`; ninguno subido se reescribió.

**Verificación.**
- Paridad: 17 escenarios y 258 llamadas por lado sin ninguna diferencia en perfiles, planes, scripts, predicciones, métricas, `describe()` ni avisos; tampoco en store_sales real (913 000 filas, 500 series). Ningún golden cambió. Los nombres públicos y las firmas son los mismos, salvo `constant_calendar_features`, que se añade.
- Tiempos, medidos de forma intercalada en esta máquina (unas tres veces más rápida que la de la sesión): `profile` 1,11 a 0,94 s, `backtest_code` con perfil guardado repetido 0,52 a 0,05 s, `forecast` repetido 2,72 a 2,19 s. Ninguna llamada es más lenta más allá del ruido. La huella de los datos cuesta 0,04 s en store_sales y se paga en cada llamada, no solo en la primera. Importación, memoria y servidor por stdio, sin cambios; el salto de `create_cv` de 19 a 129 ms que anota 20.2 no aparece aquí.
- La memoria de perfiles resistió más de cien ataques (valores, columnas, tipos, filas reordenadas, marcadores de ausencia, categóricas, 8 hilos, copias del asistente): guarda 8 perfiles y ningún dato, y los resultados no comparten objetos con ella.
- De 46 mutaciones hechas a mano, los tests detectaron 34.

**Fallos encontrados y corregidos.**

| Qué fallaba | Corrección | Commit |
|---|---|---|
| Con numpy 2.5, la comprobación de calendario emitía un `DeprecationWarning` propio en `plan(calendar_features=[...])` y su test fallaba (1 fallo en 6 de 6 ejecuciones en macOS; la sesión, en Linux, no lo veía). `weekend` en días laborables, columna constante, solo se avisaba si la primera fecha era viernes | Los intervalos son `datetime.timedelta`; `weekend` se avisa cuando la rejilla no llega a un fin de semana | `cf690ac` |
| Datos con zona horaria cuya primera fecha no es medianoche: el perfil la escribía con su desfase, la estrategia por defecto lo arrastraba y `backtest()` fallaba ("Start and end cannot both be tz-aware with different timezones"). La pregunta 2 de 20.9 lo daba por una fecha mal mostrada; ya pasaba en la base | Con una zona que el perfil nombra, `start_date` se escribe como hora local, igual que a medianoche; las estrategias y `end_train` son horas locales y el backtest corre | `19468e6` |
| La huella nombraba la zona horaria sin sus reglas: los mismos instantes en `CET` y en un desfase fijo llamado `CET` la compartían, y un asistente con la memoria cargada devolvía el perfil del otro | Se incluyen las horas locales de las fechas con zona | `1860c0c` |
| Una subclase cuyo `__init__` no llama al de la clase, y un asistente guardado con pickle en una versión anterior, daban `AttributeError` | El atributo de la memoria se crea al usarlo | `1860c0c` |
| `refine_plan()` reemplazaba un `exog_columns` editado a mano sin `PlanEditsDiscardedWarning` (pregunta 4) | Se compara, como el resto de campos | `3e27e92` |

**Otros commits.**
- `1860c0c` añade además los tests que las mutaciones no cubrían: la clave de la memoria (target, columna de fecha y de serie) y `_series_spans` con filas desordenadas.
- `901650d`: una fixture cierra el bucle de eventos que crea `run_sync` de un agente en `tests/tests_llm/test_llm_agent.py`. Es la causa probable, no probada, del `ResourceWarning` de 19.1: el bucle queda sin cerrar y avisa al recogerse, dentro del test que esté corriendo. No se reprodujo en 6 ejecuciones completas de la rama ni en 3 de la base (pregunta 5). El plugin `gc_after_test.py` culpaba al test siguiente; ahora recoge dentro de la llamada del test.
- `3e27e92`: la nota de rendimiento dice "about 15 %" (lo que dan los tiempos guardados y esta revisión) en lugar de "about 20 %"; el escenario `overrides_plan` de `check_ask_context.py` lleva el aviso de calendario, que ningún escenario enviaba.

**Decisiones del autor sobre las preguntas de 20.9.**

| Pregunta | Decisión | Estado |
|---|---|---|
| 1 | Tablas de periodos: se decide al terminar esta revisión | Abierta |
| 2 | Zona horaria con inicio que no es medianoche: en 0.4.0 | Hecho (`19468e6`) |
| 3 | Perfilar dos veces los datos que difieren del perfil guardado: se acepta | Sin cambios |
| 4 | `refine_plan()` compara `exog_columns` | Hecho (`3e27e92`) |
| 5 | El test inestable en macOS | No reproducido; fixture en `901650d` |
| 6 | Coste de la huella: se acepta | Sin cambios |

**Correcciones a esta sección.**
- 20 dice que ningún commit necesitó una corrección posterior: dos la necesitaron, de docstring (`4f147f4` corrige `ad1cc83` y `be45f88` corrige `4f147f4`).
- "4087 pasados" es de la sesión en Linux. En macOS con numpy 2.5 la rama daba 1 fallo y 4089 pasados antes de `cf690ac`.
- 20.2 da por ruido el `compare` de bike_sharing (+12,7 %) y el `forecast` del servidor (0,43 a 0,53 s) sin medición intercalada; en esta máquina, intercalado, no hay diferencia.

**Pendiente.**
- En skforecast: con datos diarios sellados a medianoche UTC y leídos en `Europe/Madrid` (01:00 en invierno, 02:00 en verano), `backtest()` falla dentro de `ForecasterRecursive.predict` con `AmbiguousTimeError` al cruzar la hora repetida de octubre. `forecast()` funciona. Antes fallaba por el motivo de `19468e6`.
- Siguen abiertos de 19.1: la build de skforecast anterior a su PR #1332, los cuatro puntos de "Mensajes" y la página de usuario de los overrides.
- `compare()` sin candidatos incluye ForecasterFoundation cuando su backend está instalado, y los modelos foundation cuentan 0 ajustes en el presupuesto de coste: con 500 series en CPU o MPS, la comparación de store_sales no terminó en 25 minutos. Queda por decidir un límite para ese candidato, como el de 500 ajustes de los demás.
- Mutaciones que siguen sin test: el orden de desalojo de la memoria, el límite exacto (`<`) del aviso de calendario y la reserva de lags del forecaster directo.

**Para el check de pago.** `overrides_plan` lleva ahora dos avisos del plan (el argumento mal escrito y la variable de calendario). En `time_zone_backtest_code`, las fechas de la estrategia son horas locales sin desfase; solo el rango de fechas de `<dataset>` muestra los desfases de la primera y la última fecha.

**Tests.** De 4090 (1 fallado) a 4101 pasados, más 1 omitido, en macOS con el entorno conda local.

## 21. Fase 7: hecho

Periodos estacionales y coste de los modelos foundation, lo último de código antes de la release 0.4.0, en la rama `feature/periods-and-foundation-cost`, creada desde `0.4.x` (`c70e62b`). Un commit por punto, en el orden pedido, cada uno subido al terminar. Antes de cada commit se pasaron `/verify` (lint, tests afectados, suite completa, goldens y build de la documentación), la paridad contra la línea base, el subagente `conventions-reviewer` y `/code-review`; lo que encontraron se corrigió antes de subir y cada mensaje lo dice. Ningún commit subido se reescribió ni necesitó una corrección posterior.

GitHub no ejecuta los tests de esta rama: la única comprobación es la de la sesión (Linux, Python 3.11.15, 4 CPU, skforecast 0.26.0, pandas 2.3.3, numpy 2.4.6). numpy 2.5 no está en el índice de paquetes de la sesión, así que la suite no corrió con él: el código nuevo no usa `pd.Timedelta`, y `_seasonal_cycles` conserva el `pd.Timedelta(offset)` que ya tenía `estimate_seasonality` (pregunta 7). `chronos-forecasting` se instaló solo en un entorno aparte para las medidas; el entorno de la suite y de la paridad no lo tiene, como en la fase 6.

| Commit | Punto | Contenido |
|---|---|---|
| `84ed17a` | 1a | `m` de Auto-ARIMA y regla de ForecasterStats desde `estimate_seasonality` para las frecuencias que la tabla no tiene; 17 escenarios de frecuencia en la paridad |
| `c44a727` | 1b | Medida de la hora frente al día en datos de 5 a 30 minutos (`tools/perf/subhourly_periods.py`); sin cambios de comportamiento |
| `6cbd194` | 2 | Coste de los modelos foundation en ventanas de inferencia, con su `LongTrainingWarning`, en Python y en el servidor |
| este | | Esta sección |

### 21.1 Línea base y paridad

La línea base se tomó antes de tocar código, con `tools/perf/parity.py` y 25 escenarios: los 8 de la fase 6 (que cubren `D`, `h` y `MS`) más una serie sintética por frecuencia (`FREQUENCY_SCENARIOS` de `tools/perf/_datasets.py`): `ME`, `W-SUN`, `QS-OCT`, `YS-JAN`, `B` y `min`, que no debían cambiar, y `2W-SUN`, `3D`, `5D`, `2MS`, `3h`, `7h`, `14h`, `10s`, `5min`, `15min` y `30min`.

| Comparación | Resultado |
|---|---|
| Base frente a `84ed17a` (1a) | Sin diferencias en los 8 conjuntos ni en `ME`, `W-SUN`, `QS-OCT`, `YS-JAN`, `B`, `min`, `3D`, `7h`, `5min`, `15min` y `30min`. Diferencias, todas explicadas: `2W-SUN`, `5D` y `10s` pierden ForecasterStats de los candidatos (la explicación y la lista de candidatos del perfil, y `compare()` sin él; en `10s` ForecasterStats era el ganador y ahora lo es ForecasterRecursive); en `2MS`, `3h` y `14h` el candidato ForecasterStats de `compare()` corre con `m` (6, 8 y 12): otras métricas y, en `3h`, otro ganador (MAE de 2,34 a 0,97) |
| `84ed17a` frente a `c44a727` (1b) | Sin diferencias |
| `c44a727` frente a `6cbd194` (2) | Sin diferencias: ningún escenario ejecuta un modelo foundation (sin backend, `compare()` lo deja fuera, como antes) |

Con el backend instalado se comprobó a mano el punto 2: un backtest de 50 series y 41 folds de store_sales (2050 ventanas) tardó 62 s, emitió el aviso nuevo, y su `cv_config` y su explicación llevan las ventanas.

### 21.2 Punto 1a: frecuencias que la tabla no tiene

**Regla.** `arima_seasonal_period` (nuevo, en `recommendation/autoregressive.py`) da el periodo de `FREQUENCY_TO_SEASONAL_PERIOD` si la frecuencia está en la tabla; si no, el primer periodo de `estimate_seasonality` (el que los lags incluyen siempre y el baseline repite) cuando es un ciclo entero de al menos 2 pasos. Lo leen el script de Auto-ARIMA y la regla que deja a ForecasterStats fuera de los candidatos (24 o más). Motivo:
- Un periodo que no es un ciclo entero (`3D`: 2 pasos son 6 días, no una semana; el 121 del año tampoco es exacto) haría que los términos estacionales modelen un ciclo que los datos no tienen, y encarece la búsqueda.
- Un periodo de 1 es el modelo sin estacionalidad que Auto-ARIMA ajusta sin `m` (su valor por defecto): escribirlo no cambia nada.
- Solo se lee el primer periodo, así que `m`, cuando existe, es siempre el periodo del baseline: una sola fuente. En `7h` el segundo periodo (24, la semana) es entero pero el primero (3) no: sin `m`, como antes.
- "Entero" se decide con nanosegundos enteros (`_seasonal_cycles`); para un alias de longitud variable, cuando el multiplicador divide el periodo de la tabla (`2MS`: 6 de 12; `5MS` no). `/code-review` encontró dos casos, corregidos antes del commit: `ms` (milisegundos) se leía como `MS` y daba `m=12`, y el periodo de `L` que la división en coma flotante deja un paso corto (3599999) se marcaba entero. Los dos dan ahora ningún `m`.

`estimate_seasonality`, la tabla y el periodo del baseline dan lo mismo que antes en las 238 frecuencias de `tools/perf/seasonal_periods.py` (y en 975 en la revisión de convenciones). El `m` cambia en 38 de las 238, ninguna de las que pandas infiere para datos corrientes:

| Frecuencias | `estimate_seasonality` | `m` antes | `m` después | ForecasterStats entre los candidatos | Baseline |
|---|---|---|---|---|---|
| `2MS`, `2ME`, `2M` | [6] | ninguno | 6 | sí (sigue) | 6 (igual) |
| `4MS`, `4ME` | [3] | ninguno | 3 | sí (sigue) | 3 (igual) |
| `2QS-OCT`, `2QS-NOV`, `2QE-DEC`, `2QE-OCT` | [2] | ninguno | 2 | sí (sigue) | 2 (igual) |
| `4W-SUN`, `4W-MON`, `4W-WED` | [13] | ninguno | 13 | sí (sigue) | 13 (igual) |
| `3h`, `3H` | [8, 56] | ninguno | 8 | sí (sigue) | 8 (igual) |
| `12h` | [2, 14] | ninguno | 2 | sí (sigue) | 2 (igual) |
| `14h` | [12, 625] | ninguno | 12 | sí (sigue) | 12 (igual) |
| `3min`, `4min`, `6min`, `12min`, `20min` | [20, 480] a [3, 72] | ninguno | 20, 15, 10, 5 y 3 | sí (sigue) | igual |
| `2W-SUN`, `2W-MON`, `2W-WED` | [26] | ninguno | 26 | **no** (antes sí) | 26 (igual) |
| `5D` | [73] | ninguno | 73 | **no** (antes sí) | 73 (igual) |
| `2min` | [30, 720] | ninguno | 30 | **no** (antes sí) | 30 (igual) |
| `s`, `S`, de `2s` a `30s` | [3600, 86400] a [120, 2880] | ninguno | de 3600 a 120 | **no** (antes sí) | igual |

Siguen sin `m`, con ForecasterStats entre los candidatos y el mismo baseline, las de primer periodo no entero o de 1: `3D`, `4D`, `6D`, de `10D` a `30D`, `3W` y de `5W` a `30W`, `5MS`, `7MS`, `10MS` (y sus `ME`), `3QS`, `3QE`, `5h`, `7h`, `10h`, `15h`, `20h`, `30h`, `7min`, `14min`, `7s` y `14s`. Las de la tabla (`D`, `h`, `MS`, `ME`, `W-SUN`, `QS`, `YS`, `B`, `min`, `2D`, `2h`, `4h`, `6h` y de 5 a 30 minutos) no cambian.

Con ForecasterStats pedido a mano en datos por segundos, el script lleva ahora `m=3600`, como `5min` ya llevaba `m=288`. Medido: con menos de dos periodos de datos, Auto-ARIMA ajusta un modelo sin estacionalidad en menos de 1 s y sin error.

Diferencias que quedan entre las fuentes (10 de 238 en `seasonal_periods.py`): las ocho de 5 a 30 minutos (21.3), `2D` (la tabla dice 7, los lags [3, 182]) y `AS-JAN` (`estimate_seasonality` no conoce el alias `AS` de pandas 2.1; la tabla le da 1, como a `YS`). Las dos últimas son frecuencias de la tabla y no entraban en 1a (preguntas 2 y 3).

### 21.3 Punto 1b: datos de 5 a 30 minutos

`tools/perf/subhourly_periods.py`, con los resultados en `tools/perf/results/phase7_subhourly.json`. Conjuntos reales de `skforecast.datasets` (la descarga funcionó): `vic_electricity` (30 minutos, `Demand`), `ett_m1` (15 minutos, `OT` y `HUFL`) y `ett_m2` (15 minutos, `OT`), los últimos 60 días de cada uno. No hay ninguno de 5 o 10 minutos, así que se añadieron dos sintéticos: 5 minutos con ciclo diario y horario, y 10 minutos solo con ciclo diario. Test: los últimos 14 días, entrenando una vez, con horizontes de una hora y de un día.

"Día solo" es lo que daría la tabla: `estimate_seasonality` devolviendo [288], [96] o [48]; el horizonte del PACF es el mismo, y cambian el lag que se incluye siempre y las ventanas. Auto-ARIMA corre en su propia estrategia: 14 días de entrenamiento y los 2 últimos días como test, reajustado en cada fold (skforecast lo hace con ARIMA), solo con el horizonte de un día (con el de una hora, 48 reajustes no terminaron en 15 minutos) y parado a los 600 s.

MASE / MAE (media de los folds), tiempo del backtest y número de predictores (lags más ventanas, hora / día). Los backtests del baseline tardan menos de 0,2 s con los dos periodos.

| Conjunto | Horizonte | Lags y ventanas: hora primero (hoy) | día solo | Predictores | Baseline: día (hoy) | hora |
|---|---|---|---|---|---|---|
| vic_electricity, 30min, Demand | una hora | 0.920 / 88.045 (1.04 s) | 0.920 / 88.045 (1.1 s) | 27 / 27 | 3.176 / 303.235 | 1.607 / 153.061 |
| vic_electricity, 30min, Demand | un día | 4.574 / 437.859 (0.25 s) | 4.574 / 437.859 (0.27 s) | 27 / 27 | 3.176 / 303.235 | 4.543 / 432.604 |
| ett_m1, 15min, OT | una hora | 1.304 / 0.289 (1.16 s) | 1.363 / 0.304 (1.05 s) | 9 / 10 | 6.658 / 1.475 | 1.746 / 0.385 |
| ett_m1, 15min, OT | un día | 4.849 / 1.074 (0.26 s) | 5.221 / 1.164 (0.38 s) | 9 / 10 | 6.658 / 1.475 | 5.377 / 1.184 |
| ett_m2, 15min, OT | una hora | 1.551 / 0.359 (1.03 s) | 1.619 / 0.372 (0.96 s) | 8 / 9 | 15.434 / 3.573 | 4.110 / 0.961 |
| ett_m2, 15min, OT | un día | 15.596 / 3.610 (0.27 s) | 17.088 / 3.931 (0.3 s) | 8 / 9 | 15.434 / 3.573 | 19.665 / 4.597 |
| ett_m1, 15min, HUFL | una hora | 1.326 / 1.724 (1.17 s) | 1.354 / 1.730 (1.27 s) | 10 / 10 | 2.259 / 2.935 | 2.147 / 2.781 |
| ett_m1, 15min, HUFL | un día | 2.071 / 2.692 (0.32 s) | 2.301 / 2.941 (0.32 s) | 10 / 10 | 2.259 / 2.935 | 5.581 / 7.230 |
| sintético, 5min, día y hora | una hora | 0.698 / 1.158 (1.55 s) | 0.655 / 1.087 (1.49 s) | 24 / 25 | 0.687 / 1.139 | 1.166 / 1.932 |
| sintético, 5min, día y hora | un día | 0.968 / 1.606 (0.63 s) | 0.660 / 1.096 (0.59 s) | 24 / 25 | 0.687 / 1.139 | 3.873 / 6.419 |
| sintético, 10min, solo día | una hora | 0.913 / 1.045 (0.99 s) | 0.911 / 1.042 (1.2 s) | 18 / 19 | 0.973 / 1.113 | 1.684 / 1.934 |
| sintético, 10min, solo día | un día | 1.255 / 1.436 (0.35 s) | 1.061 / 1.213 (0.39 s) | 18 / 19 | 0.973 / 1.113 | 5.661 / 6.500 |

| Conjunto | Auto-ARIMA `m` = día | `m` = hora |
|---|---|---|
| vic_electricity, 30min, Demand | parado a 600 s | 3.998 / 337.357 (3.13 s) |
| ett_m1, 15min, OT | 5.299 / 0.992 (445.75 s) | 5.270 / 0.986 (0.88 s) |
| ett_m2, 15min, OT | parado a 600 s | 20.999 / 5.528 (4.98 s) |
| ett_m1, 15min, HUFL | parado a 600 s | 5.837 / 7.993 (5.8 s) |
| sintético, 5min, día y hora | parado a 600 s | 6.891 / 11.390 (103.34 s) |

**Lectura.**
- Lags y ventanas: con datos reales gana la hora primero (lo de hoy) en los 6 casos de ETT y empata en `vic_electricity` (a 30 minutos la hora, 2, es más corta que la ventana mínima y los lags salen iguales); con datos sintéticos gana el día en los 4. Mismo tiempo; el día da los mismos predictores o uno más.
- Baseline: con horizonte de una hora gana la hora en los 4 conjuntos reales y el día en los 2 sintéticos; con horizonte de un día gana el día en 5 de 6 (en `ett_m1` OT, la hora).
- Auto-ARIMA: con `m` el día no es practicable (4 de 5 pasan de 10 minutos para 2 folds; `ett_m1` OT, 446 s); con `m` la hora tarda de 1 a 6 s (103 s con 5 minutos) y en el único caso comparable da lo mismo (MASE 5,27 frente a 5,30).

**Decisión: todo queda como está para esas frecuencias.** Ninguna opción gana en todos los conjuntos ni empata sin coste: los lags prefieren la hora con datos reales y el día con sintéticos, y el baseline depende del horizonte. Pasar `m` a la hora sería practicable, pero metería a ForecasterStats entre los candidatos automáticos de estos datos (12, 6, 4 y 2 están por debajo de 24) y cambiaría el baseline, que con horizonte de un día pierde. Un comentario sobre `FREQUENCY_TO_SEASONAL_PERIOD` lo deja escrito; la tabla va como pregunta 1.

### 21.4 Punto 2: coste de los modelos foundation

**Medidas** (`tools/perf/foundation_cost.py`, resultados en `tools/perf/results/phase7_foundation_*.json`). En la CPU de la sesión (4 núcleos, torch 2.14.1 sin GPU, `chronos-forecasting` 2.3.2; los pesos se descargaron sin problema), backtest de series diarias de store_sales con horizonte 7, ajustando segundos = fijo + coste por ventana:

| Modelo | Fijo | Por ventana | Ventanas por minuto | Casos (series x folds) |
|---|---|---|---|---|
| `autogluon/chronos-2-small` (por defecto) | 1 a 4 s | 27 ms | unas 2100 | 1x1: 3,9 s; 1x10: 1,1 s; 10x10: 2,8 s; 50x10: 15,2 s; 100x10: 30,7 s; 500x2: 40,9 s; 100x50: 134,9 s |
| `autogluon/chronos-2-small`, store_sales con la estrategia por defecto | | 29 ms | | 500x79 (39 500 ventanas): **1157 s, 19 minutos** |
| `amazon/chronos-2` | 1 a 4 s | 116 ms | unas 500 | 10x10: 8,6 s; 50x10: 52,6 s; 100x10: 119 s |

El coste es lineal en las ventanas, también al cambiar series por folds (500x2 y 100x10 dan 41 y 31 s para 1000 ventanas). Frente a las cifras del autor en un Mac con GPU (4 s fijos y 3 ms por ventana; store_sales en 121 s), esta CPU es unas 10 veces más lenta por ventana, y el modelo grande es 4 veces más lento que el pequeño (2 veces en GPU). Unas primeras medidas se descartaron: corrieron a la vez que otros procesos y torch, con sus 4 hilos compitiendo por la CPU, llegó a dar 30 veces más tiempo por ventana.

**Medida y aviso.** `count_inference_windows` cuenta series por folds (0 para cualquier otro forecaster). Un plan `ForecasterFoundation` lleva `inference_windows` en `cv_config` (`create_cv()`, `backtest()` y su candidato en `compare()`), y la explicación de su estrategia termina con "The model forecasts each series in each fold (N inference windows in all)." Por encima de `LONG_INFERENCE_WINDOWS` = **2000** ventanas, `backtest()` y `compare()` (una vez por candidato, antes de ejecutar) emiten `LongTrainingWarning` con su propio texto, que propone menos folds o menos series. El umbral es un minuto, más o menos, con el modelo por defecto en CPU (2050 ventanas, 62 s de punta a punta); en GPU son unos 10 s y con `amazon/chronos-2` en CPU unos 4 minutos (pregunta 5).

**No se excluye el candidato foundation de `compare()`.** Con tamaños corrientes cuesta segundos (una serie con 50 folds, 2,8 s; 10 series con 10 folds, 2,8 s) o un par de minutos (100 series con 50 folds, 2,3 minutos); los muchos minutos llegan con cientos de series y muchos folds (store_sales con la estrategia por defecto, 19 minutos en CPU). El aviso llega antes de ejecutar, así que se puede cancelar o pasar `candidates`. Queda como pregunta 4.

**Servidor MCP.** `cost` gana `inference_windows` (en la estrategia, el backtest y, sumado, los candidatos de una comparación; 0 salvo un modelo foundation) y, en `create_cv`, `compare_inference_windows` (el candidato foundation de un `compare` sin candidatos; 0 si su backend no está instalado, porque `compare()` lo deja fuera). `create_cv` de un plan foundation por encima del umbral lleva la notice `LongTrainingWarning` que emitirá el backtest, y una `CompareCostNotice` cuando un `compare` sin candidatos correría el modelo foundation por encima del umbral. Lo describen el SKILL.md (y su copia de `plugin/`, idéntica), `docs/api/mcp.md`, la guía y el docstring de `ToolResult`.

### 21.5 Cambios para el usuario

**Python.**
- Frecuencias multiplicadas y por segundos fuera de la tabla (21.2): el script de Auto-ARIMA lleva `m`; las de periodo 24 o más (`2W`, `5D`, `2min`, segundos) dejan a ForecasterStats fuera de los candidatos, así que `compare()` sin candidatos ya no lo ejecuta y `plan(forecaster="ForecasterStats")` avisa con `UnrecommendedForecasterWarning`. Las predicciones, las métricas y el ganador de `compare()` pueden cambiar en esos datos.
- Planes `ForecasterFoundation`: `inference_windows` en `cv_config`, una frase más en la explicación de la estrategia y `LongTrainingWarning` por encima de 2000 ventanas en `backtest()` y `compare()`.
- Nada más: las frecuencias de datos corrientes (`D`, `h`, `MS`, `ME`, `W-SUN`, `QS`, `YS`, `B`, `min`) y los datos de 5 a 30 minutos no cambian (paridad, 21.1). En la release 0.4.0, una entrada nueva (Enhancement, Auto-ARIMA) y una frase añadida a la existente sobre el coste de los backtests.

**Servidor MCP.** Lo mismo, a través de los mismos planes y candidatos, más los campos nuevos de `cost` y las notices de 21.4.

### 21.6 Goldens

- Render (`tests/tests_rendering`): ningún golden cambió. Cambió la expectativa de un caso de un test parametrizado: `'2W'` escribe ahora `m=26` en `test_render_forecast_statistical_output_seasonal_period_when_anchored_or_multiplied_frequency` (más los casos nuevos `3h`, `3D` y `7MS`).
- Contexto del LLM: `backtest_foundation_multi_series_quantiles` (en `golden` y `golden_describe`), una línea añadida, `- inference_windows: 12`; su fixture lleva ahora la clave como la da `resolve_cv_config`. Regenerados con `/llm-context-change`; ningún valor de los datos.
- Esquemas del MCP (`tool_schemas.json`): solo el docstring de `ToolResult`, que describe los campos nuevos de `cost` (8 apariciones, una por tool).

### 21.7 Tests

De 4097 pasados y 1 omitido en la base a **4178 pasados y 1 omitido**: 4162 tras 1a (`arima_seasonal_period`, los candidatos, el render y `plan()` con datos quincenales), 4162 tras 1b y 4178 tras 2 (`count_inference_windows`, `warn_long_inference`, `cv_config` y la explicación, `backtest()`, `compare()` y `create_cv` del servidor). En Linux, con numpy 2.4.6.

### 21.8 Para el check de pago

Además de la lista de 20.10 y 20.12:
- El contexto de un backtest foundation: la línea `- inference_windows` en `<backtesting_strategy>`, y la frase nueva de la explicación de la estrategia en los resultados foundation. Ningún escenario de `check_ask_context.py` ejecuta un modelo foundation (la sesión no tenía el backend en el entorno principal): conviene uno donde esté instalado.
- La explicación del perfil de datos multiplicados o por segundos lista otros candidatos (sin ForecasterStats en `2W`, `5D`, `2min` y segundos).
- `--dry-run` construyó los contextos de los cuatro conjuntos sin problemas; no se lanzó sin él.

### 21.9 Preguntas nuevas para el autor

1. Datos de 5 a 30 minutos (21.3): ¿se quedan como están, o se elige una fuente? Opciones: `m` de la hora para Auto-ARIMA (practicable, pero ForecasterStats entra en los candidatos automáticos), un baseline que repita la hora cuando el horizonte no pasa de una hora, o el día para los lags.
2. `2D`: la tabla le da `m=7` (14 días, que no es un ciclo) y los lags [3, 182]. ¿Se quita de la tabla para que lea `estimate_seasonality` (3 no es entero: sin `m`)?
3. `estimate_seasonality('ms')` lee los milisegundos como `MS` y da [12] a los lags, y `AS-JAN` da []. ¿Se corrige en 0.5.0? Cambia los lags de esos datos.
4. Candidato foundation en `compare()` sin candidatos: ¿un presupuesto de ventanas, como el de 500 ajustes (por ejemplo 20 000, unos 10 minutos en CPU), con el mismo mecanismo de `exclude_costly_candidates`? store_sales con la estrategia por defecto tarda 19 minutos en CPU con el modelo pequeño.
5. Umbral del aviso por modelo: 2000 ventanas son un minuto con `chronos-2-small` en CPU, 4 minutos con `amazon/chronos-2` y unos 10 s en GPU. ¿Fijo, o escalado por modelo (skforecast no da su tamaño)?
6. Baseline de frecuencias con primer periodo no entero (`3D` repite el valor de 6 días antes y dice "one seasonal period"): ¿se deja, o pasa a naive como el `m` de Auto-ARIMA?
7. numpy 2.5: ¿se pasa la suite en macOS para confirmar que `_seasonal_cycles` (que conserva el `pd.Timedelta(offset)` de antes) no avisa?

### 21.10 Qué queda para 0.4.0

- El check de pago, una sola vez, con la lista de las secciones 3, 12, 13, 14, 15, 18, 18.1, 19, 19.1, 20.10, 20.12 y 21.8, y los cuatro conjuntos de `check_ask_context.py`.
- Las preguntas de arriba y las abiertas de las secciones anteriores.
- El plan de release de 17.1: skforecast 0.26.0, después skforecast-ai 0.4.0 en PyPI y solo entonces el merge de `0.4.x` a `main`.

**Siguiente:** el check de pago.

### 21.11 Revisión del autor y correcciones

Antes de mergear la fase 7, una verificación independiente comparó la base (`c70e62b`) con la rama (`aea0dce`) en macOS, con numpy 2.5.3 y `chronos-forecasting` instalado: los periodos estacionales, el coste de los modelos foundation con el servidor MCP, y la suite con los tests y la documentación. Es la primera revisión en la que un modelo foundation se ejecuta de verdad. Las correcciones van como commits nuevos al final de `feature/periods-and-foundation-cost`; ninguno subido se reescribió.

**Verificación.**
- Suite: 4181 pasados y 1 omitido en tres ejecuciones con numpy 2.5 (4 tests más que en la sesión, los de integración foundation). Ningún aviso nuevo de numpy 2.5 en esta fase: la pregunta 7 queda cerrada, `_seasonal_cycles` no avisa.
- Periodos: las frecuencias corrientes no cambian en 34 escenarios; 38 de 238 cambian, y 61 de las 693 distintas de un barrido más amplio. Ningún ciclo no entero se redondea a un `m`. Donde hay un ciclo real el MAE de backtest de Auto-ARIMA baja de 1,61 a 0,95 (`2MS`), de 2,95 a 0,87 (`3h`) y de 9,91 a 0,93 (`14h`).
- Coste foundation: en 61 backtests reales, `inference_windows` coincide con los pares (fold, serie) ejecutados, salvo cuando una serie no está en un fold (28 contadas frente a 23). Los planes que no son foundation quedan idénticos byte a byte en 40 casos. El aviso sale a partir de 2001 ventanas, una vez.
- Con un modelo real por el servidor: ninguna línea ajena al protocolo en la salida estándar en 9 procesos que cargaron pesos; el script de `get_code` reproduce el backtest (180 predicciones idénticas); sin fugas de memoria tras cinco backtests (de 330 a 370 MB; el modelo se recarga en cada llamada); latido de progreso cada 5 s; los modelos restringidos dan `model_not_allowed`.
- Tiempos en esta máquina (GPU de portátil): 1,1 s fijos y 2,9 ms por ventana con Chronos-2 small, 10,4 ms con `amazon/chronos-2`. 2000 ventanas son 7 s (unos 14 s forzando CPU), no un minuto.
- De 37 mutaciones, los tests detectaron 32.

**Corregido.**

| Qué | Corrección | Commit |
|---|---|---|
| `compare()` avisaba una vez por candidato foundation con el mismo texto, y tres candidatos de 700 ventanas (2100) no avisaban. El recuento se daba por exacto. La nota y la guía prometían "about a minute on a CPU" | Las ventanas de los candidatos foundation se suman en un solo aviso, que dice cuántos son. La explicación, el aviso y los notices dicen "up to". La nota y la guía dicen un minuto o más en CPU y segundos en GPU; el coste foundation es una entrada propia de la release, y la de Auto-ARIMA dice que solo `compare()` sin candidatos deja fuera a ForecasterStats y que el ganador puede cambiar | `f6b0a36` |
| Con numpy 2.5, `profile()` de datos en formato largo emitía un `DeprecationWarning` atribuido al paquete (`pd.Timedelta(days=1)`); ya pasaba en la base. Lo ve quien ejecuta con avisos como errores | Las duraciones son constantes en nanosegundos. El filtro de `pyproject.toml` se queda para los tests y para pandas, con un comentario exacto | `961afae` |
| El aviso de descarga afirmaba "its license is Apache-2.0" de un identificador de un prefijo permitido cuyo repositorio no existe | Dice que la licencia es la que skforecast registra para el nombre del modelo. La guía y el SKILL.md dicen además que, con los pesos en caché, el backend sigue contactando con el Hub en cada ejecución salvo con `HF_HUB_OFFLINE=1` | `23ef78a` |
| Cinco mutaciones sin test | Tests: un ciclo entero de un solo paso (`12MS`) sin `m`; las ventanas con varias series y con el último fold incompleto; el `cost` del servidor con varias series; el notice justo en el umbral | `575c38a` |

**Correcciones a esta sección.**
- 21.3: Auto-ARIMA con el día como `m` en vic_electricity terminó aquí en 197 s con MASE 1,858, frente a 3,998 con la hora y 3,176 del baseline; la sesión lo dio por impracticable porque no terminaba en 10 minutos en su máquina. Respalda lo que la tabla hace hoy, y la decisión de no tocar esos datos.
- 21.5 no dice que un plan o un candidato ForecasterStats pedido explícitamente con datos de `2W`, `5D`, `2min` o segundos se ejecuta ahora con `m` de 26, 73, 30 o 3600 (solo está en 21.2).
- 21.8 dice que ningún escenario de `check_ask_context.py` incluye un modelo foundation. Con el backend instalado existe `foundation_plan` y `compare` ejecuta ForecasterFoundation; lo que no hay es un backtest foundation, así que `inference_windows` no aparece en ningún contexto.
- Pregunta 3: además, `250L` recibe `m=14400` mientras `250ms` y `L` no reciben ninguno, y `14D`, `7D` y `168h` no reciben el que sí tienen `2W` y `W`.

**Pendiente de decidir por el autor.**
- Frecuencias fuera de la tabla con periodo de 24 o más (`2W`, `5D`, `2min`, `40min`, `45min`, segundos): ForecasterStats sale de los candidatos automáticos (en datos sin ciclo era el ganador de `compare()` en cuatro de cinco casos medidos, y ni `compare()` ni la explicación dicen por qué falta), y pedido explícitamente recibe un `m` grande: el ajuste de `5D` con 5000 observaciones pasa de 3,4 a 253 s, el de `10s` con 1000 de 1,3 a 285 s, y el de `s` con 8000 no termina en 7 minutos y ocupa 1,6 GB. Solo avisa el `UnrecommendedForecasterWarning` genérico. Alternativa: fuera de la tabla, dar `m` solo por debajo de 24 y dejar el resto como estaba.
- `forecast()` con `test_size` y un plan foundation sobre datos largos donde una serie acaba antes falla dentro del script ("Found input variables with inconsistent numbers of samples: [0, 7]"); el plan por defecto da un `invalid_argument` claro con los mismos datos. Ya pasaba en la base.

**Cerrado.**
- El pendiente de 20.12 en skforecast (`AmbiguousTimeError` en `backtest()` de datos diarios a medianoche UTC leídos en `Europe/Madrid`): corregido en skforecast (PR #1343, en `0.26.x`). El backtest corre con las siete familias de forecaster.

**Para el check de pago.** La explicación del CV de un plan foundation dice ahora "(up to N inference windows)". Sigue faltando un escenario con un backtest foundation, que necesita el backend instalado.

**Tests.** De 4181 a 4192 pasados, más 1 omitido, en macOS con el entorno conda local.

**Evaluación foundation con series incompletas (pendiente cerrado, `60a1ade`).** Rama `fix/foundation-evaluation-partition`, que sale de la punta de esta. Causa: el fallo no está en skforecast sino en las métricas del script generado. `ForecasterFoundation` predice cada serie desde su propia última fecha, y el script compara `series_dict_test[level].iloc[:steps]` con las predicciones por posición: una serie en formato largo que acaba antes del test llega vacía a `mean_absolute_error` ("inconsistent numbers of samples: [0, 7]"; [4, 7] si acaba dentro del test), y en formato ancho llega con NaN ("Input contains NaN"). Casos ejecutados con Chronos-2 y con el plan por defecto, en largo y ancho, 3 series diarias y `test_size=7`:

| Caso (una serie de tres) | Foundation antes | Foundation ahora | Plan por defecto |
|---|---|---|---|
| Completa | Correcto (MAE igual al calculado a mano) | Igual | Correcto |
| Acaba antes del fin de entrenamiento | `execution_failed`: [0, 7] en largo, "Input contains NaN" en ancho | `invalid_argument`, campo `data` | `invalid_argument`, campo `test_size` |
| Acaba dentro del test, o tiene huecos o NaN en el test | `execution_failed`: [4, 7] o "Input contains NaN" | `invalid_argument`, campo `data` | `invalid_argument`, campo `data` |
| Empieza tarde, dentro del entrenamiento | Correcto | Igual | Correcto |
| Empieza después del fin de entrenamiento | `execution_failed`: "All values of series 'c' are NaN" | `insufficient_data` | `insufficient_data` |
| NaN o fila ausente en la última fecha de entrenamiento | Correcto (predice las fechas del test) | Igual | `invalid_argument`, campo `test_size` |

`test_size` como entero, fracción o fecha da lo mismo en todos. El modo predicción y `backtest()` con un plan foundation funcionan en todos los casos y no cambian (el backtesting de skforecast omite los valores ausentes por serie); solo una serie sin ningún valor en formato largo fallaba dentro del script en los tres modos ("All values of series ... are NaN") y ahora da `insufficient_data`. Arreglo: una comprobación previa, sin tocar el script ni los goldens. `validate_evaluation_partition` exige a un plan foundation con varias series un valor en cada fecha de test, con el mensaje de ForecasterRecursiveMultiSeries más una frase que nombra las series sin ningún valor en el test y aconseja quitarlas; no le exige valor en la última fecha de entrenamiento, que el modelo tolera. `validate_series_lengths` rechaza las series sin valores también para foundation. Por el servidor llega como `invalid_argument` con campo `data_path`. Las predicciones y métricas de los casos que funcionaban son idénticas. Sin tocar: en modo predicción con datos largos, la serie que acaba antes se predice desde su propia última fecha (otras fechas que las demás), como hace skforecast, y solo lo dice la nota "Series ending early" del perfil, sin aviso; evaluar la serie corta solo donde tiene valores cambiaría el script y lo que hacen los demás forecasters, y no se ha hecho. Suite: de 4192 a 4217 pasados, más 1 omitido.

**Decisión sobre el `m` de las frecuencias fuera de la tabla (`3d4dce2`).** Cierra el primer pendiente de arriba, con un corte más bajo que la alternativa que proponía: fuera de la tabla, `arima_seasonal_period` da `m` solo cuando el primer periodo es un ciclo entero de 2 a 12 pasos (`MAX_UNTABULATED_ARIMA_PERIOD`, constante nueva). Por encima no hay `m` y ForecasterStats sigue entre los candidatos, como en la base (`c70e62b`). El motivo del 12 y no del 24: la tabla no tiene ningún periodo entre 13 y 23 (el mayor de un candidato automático es 12: `2h`, `MS`, `ME`), así que `MAX_STATS_SEASONAL_PERIOD` nunca se había medido en ese hueco, y `84ed17a` fue lo primero que puso frecuencias en él, como candidatas automáticas con `m`. Medido, `3min` (20) cuesta lo que los datos horarios. Las frecuencias de la tabla no se tocan, y quien quiera el periodo largo lo pide con `estimator_kwargs={'m': 26}` (lo dice la nota de la release y lo fija un test).

Sobre 275 frecuencias (las 238 de `tools/perf/seasonal_periods.py` más 37 añadidas alrededor del corte), `estimate_seasonality` y el periodo del baseline son idénticos en la base, la rama y el código nuevo, y ninguna frecuencia de la tabla ni corriente cambia:

| Frecuencias fuera de la tabla | Periodo | `m` en la base | `m` en la rama (`84ed17a`) | `m` ahora | ForecasterStats candidato (base, rama, ahora) |
|---|---|---|---|---|---|
| `2MS`, `2ME`, `2M`, `3MS`, `4MS`, `4ME`, `6MS`, `2QS`, `2QE`, `13W`, `26W`, `3h`, `8h`, `12h`, `14h`, `21h`, `6min`, `12min`, `20min` | 2 a 12 | ninguno | el periodo | el periodo (igual que la rama) | sí, sí, sí |
| `4W`, `4min`, `240s`, `96min`, `90min`, `225s`, `80min`, `200s`, `3min`, `180s`, `72min` | 13 a 20 | ninguno | el periodo | ninguno (igual que la base) | sí, sí, sí |
| `60min`, `150s`, `144s`, `2W`, `2min`, `48min`, `45min`, `40min`, `100s`, `36min`, `90s`, `5D`, `s` y de `2s` a `30s`, `us`, `250L`, `365h`, `292h` | 24 o más | ninguno | el periodo | ninguno (igual que la base) | sí, **no**, sí |

Medidas en macOS, un caso cada vez, con la serie sintética de la revisión (nivel, paseo aleatorio, ruido y, con ciclo, dos senos del periodo): `forecast()` de un plan ForecasterStats con `test_size=12` y `compare()` sin candidatos (con el modelo foundation en caché). La máquina tenía otra carga, así que vale el orden de magnitud. "Antes" es la rama (`f6086ef`), "después" `3d4dce2`.

| Datos | Observaciones | `m` antes | `forecast()` antes | `forecast()` después | MAE antes | MAE después | `compare()` antes | `compare()` después |
|---|---|---|---|---|---|---|---|---|
| `2W-SUN`, ciclo de 26 | 130 | 26 | 2,2 s | 0,4 s | 1,08 | 5,60 | 5 s, sin Stats | 5 s, Stats 3,68 |
| `2W-SUN`, ciclo de 26 | 260 | 26 | 16,6 s | 0,6 s | 1,19 | 6,07 | 6 s, sin Stats | 20 s, Stats 3,88 |
| `2W-SUN`, ciclo de 26 | 1000 | 26 | 54,5 s | 0,8 s | 1,17 | 4,89 | 8 s, sin Stats | 15 s, Stats 3,64 |
| `5D`, ciclo de 73 | 1000 | 73 | más de 300 s | 0,9 s | sin terminar | 1,79 | 7 s, sin Stats | 18 s, Stats 2,04 |
| `2min`, ciclo de 30 | 1000 | 30 | 99,2 s | 0,6 s | 1,02 | 3,26 | 8 s, sin Stats | 17 s, Stats 4,67 |
| `10s`, ciclo de 360 | 1000 | 360 | 128,1 s | 0,6 s | 1,48 | 1,37 | 7 s, sin Stats | 9 s, Stats 1,24 |
| `4W-SUN`, ciclo de 13 | 260 | 13 | 6,8 s | 0,7 s | 1,52 | 4,87 | 28 s, gana Stats (1,19) | 6 s, gana Foundation (Stats 3,68) |
| `4min`, ciclo de 15 | 1000 | 15 | 18,9 s | 0,8 s | 1,15 | 2,87 | 135 s | 16 s |
| `4min`, ciclo de 15 | 5000 | 15 | 67,4 s | 1,0 s | 1,10 | 4,02 | más de 400 s | 63 s |
| `3min`, ciclo de 20 | 1000 | 20 | 40,0 s | 0,8 s | 1,20 | 8,21 | 336 s | 15 s |
| `3min`, ciclo de 20 | 5000 | 20 | 63,1 s | 1,8 s | 1,02 | 3,20 | más de 400 s | 95 s |
| `3min`, ciclo de 20 | 20000 | 20 | 230,4 s | 4,7 s | 0,91 | 5,43 | no medido | no medido |
| `2MS`, `3h`, `14h`, `6min`, con ciclo | 1000 | 6, 8, 12, 10 | 2,2 a 3,8 s | igual | 1,86 a 2,74 | igual | 68 a 83 s | igual |
| `3h` y `6min`, con ciclo | 20000 | 8, 10 | 34 y 12 s | igual | 1,03 y 1,62 | igual | no medido | no medido |

Sin ciclo real (`2W-SUN`, `5D`, `2min`, `10s`, `3min`, `2MS`, `3h` y `14h` con 1000 observaciones, `4W-SUN` con 260), `forecast()` tarda menos de 1 s antes y después con el mismo MAE (salvo `5D`, 5,7 s antes), y `compare()` de 5 a 12 s; en los cuatro primeros ForecasterStats vuelve a competir (MAE 1,05).

Lo que se gana: `compare()` sin candidatos sobre datos de `3min` o `4min` vuelve de minutos a segundos, nadie pierde ForecasterStats, y pedirlo a mano no dispara el ajuste. Lo que se pierde, sabido y aceptado: con un ciclo real de más de 12 pasos, ForecasterStats corre sin estacionalidad, como en 0.3, y su error es de 3 a 7 veces mayor que con `m`; `4W` (13) es el único caso medido donde además cambia el ganador de `compare()`, y subir el corte a 13 es cambiar la constante y dos tests. Los datos de la tabla tienen el mismo coste de siempre (`h` con 5000 observaciones no termina un ajuste en 4 minutos) y no se han tocado.

Para 0.5.0: el coste de Auto-ARIMA depende de `m`, de la longitud y de si hay ciclo (sin ciclo, `m=26` cuesta lo mismo que no darlo), y el presupuesto de `compare()` cuenta un ajuste de ForecasterStats como uno cualquiera. Una regla sobre `m` y longitud serviría para los candidatos, para un aviso propio y para unificar la tabla con el resto, pero cambia frecuencias corrientes.

**Tests.** De 4192 a 4211 pasados con este cambio solo, más 1 omitido. Ningún golden del contexto del LLM ni de los esquemas del MCP cambió. Con la evaluación foundation de `60a1ade` integrada en la misma rama, la suite completa da 4236 pasados y 1 omitido.

---

## 22. Check de pago: hecho

La comprobación de `ask()` con un modelo real, la única de 0.4.0, en la rama `chore/ask-context-check`, creada desde `0.4.x` (`00a9391`). El autor lanzó los comandos; la sesión preparó el script, revisó los informes y propuso los dos cambios de `llm/context.py`, que el autor aprobó antes de aplicarlos.

- **Modelo y fecha:** `google:gemini-3.8-flash`, 2026-10-05. Tres pasadas completas de los cuatro conjuntos (la tercera, sobre el código final, es la que se guarda; ver 22.7) y dos repeticiones sueltas de `time_zone_cv` en bike_sharing entre las dos primeras.
- **Informes guardados:** `tools/ai/ask_context_reports/0.4.0_<conjunto>.md`, los cuatro de la tercera pasada. Los contextos de los informes son idénticos, byte a byte, a los de un `--dry-run` del mismo código.

| Commit | Contenido |
|---|---|
| `0fd65fe` | `check_ask_context.py`: escenarios `foundation_backtest`, `data_warnings`, `free_text_plan` y `time_zone_cv`; lista de `time_zone_backtest_code` corregida |
| `b5071e8` | `llm/context.py`: "index not sorted as given (the generated code sorts it)" cuando el perfil ya ordenó las filas |
| `b94a06f` | `llm/context.py`: rango de fechas en hora local sin desfase con datos con zona horaria |
| este | Los cuatro informes, la fila del registro del README y esta sección |

### 22.1 Preparación

Lista consolidada de las secciones 3, 12, 13, 14, 15, 18, 18.1, 19, 19.1, 20.10, 20.12, 21.8 y 21.11, por escenario. Cuatro escenarios nuevos cubren lo que ninguno enviaba:

- `foundation_backtest`: backtest de Chronos-2 small con la estrategia por defecto (17, 72, 72 y 6 ventanas de inferencia); lleva `n_fits: 0`, `inference_windows` y "(up to N inference windows)". Se salta con un mensaje sin el backend o sin los pesos.
- `data_warnings`: perfil de los mismos datos con tres fechas quitadas, filas desordenadas, una serie que acaba antes (multiserie, redacción de ancho y de largo) y columnas dejadas fuera con `exog_columns` (bike_sharing).
- `free_text_plan`: explicación del plan con párrafos, una línea escrita como item (`- Steps: 999`) y etiquetas que cerrarían el plan y abrirían un `<dataset>`.
- `time_zone_cv`: la estrategia de `create_cv()` con datos en Europe/Madrid, que conserva la fecha local. El contexto de un `backtest_code()` lee la estrategia del script y muestra el número de observaciones (`initial_train_size: 1400`), no la fecha, al contrario de lo que decía 19.1; la lista de `time_zone_backtest_code` lo recoge.

| Conjunto | Escenarios | Preguntas | Se saltan |
|---|---|---|---|
| bike_sharing | 18 | 38 | `stats_backtest`, `compare_default` |
| items_sales | 16 | 39 | los dos anteriores, `compare_many`, `many_categorical` |
| items_sales_long | 16 | 39 | los mismos |
| h2o | 20 | 40 | ninguno |

Ningún contexto vacío ni cortado, y ninguna fila del dataset en ninguno: solo estadísticas de resumen y los valores propios de cada resultado. Los avisos del perfil nombran una serie y su última fecha, como se decidió en 12.1.

### 22.2 Primera pasada: lo que se encontró y se cambió

140 correctas, 14 mejorables y 2 incorrectas de 156. Dos hallazgos venían del contexto:

1. **Filas desordenadas, 3 de 4 conjuntos.** A "Is there anything wrong with my data that I should know about or fix before forecasting?" el modelo mandaba ordenar los datos ("Time series data must be sorted chronologically before fitting a forecaster", "They must be sorted chronologically before profiling or fitting", "Sort the data: Sort the DataFrame chronologically by its date index"), aunque la nota del perfil dice que ya se ordenaron y que el código generado las ordena. La línea "Index irregularities: ..., index not sorted" era una bandera sin matiz junto a esa nota. Cambio (`b5071e8`): con la nota del perfil presente, la bandera dice "index not sorted as given (the generated code sorts it)". Ningún golden cambia.
2. **Desfase de la primera fecha tomado por la zona de todos los datos, 3 de 3 ejecuciones** (bike_sharing, el único conjunto cuyo contexto mostraba un desfase). Con "Date range: 2012-10-09 18:00:00+02:00 to 2013-01-01" y una estrategia hasta 2012-12-07, respondía "The dates in this strategy are recorded with a UTC offset of +02:00", "The timestamps in the dataset carry a UTC offset of +02:00" y "The dates in the dataset carry a +02:00 time zone offset"; en diciembre es +01:00. El rango salía de `series_lengths`, con el desfase de una fecha que no es medianoche y sin él a medianoche, mientras la estrategia va en hora local. Cambio (`b94a06f`): con zona horaria en el perfil, los dos extremos del rango se escriben en hora local sin desfase. Ningún golden cambia. Corrige además lo que decía 20.12 (que el rango mostraba los desfases de las dos fechas).

La otra incorrecta era del modelo: en items_sales, "Lags 1 through 6 consistently appear as strong partial autocorrelations across all three targets" (el lag 4 no está en item_1 ni el 2 en item_2). Vista una vez; no se repitió en items_sales_long ni en la segunda pasada. Es el mismo tipo de desliz que el README anotó con gemini-3.5.

### 22.3 Segunda pasada

Sobre el código de `b94a06f`. Lo que dejó mejorable motivó los cambios de 22.7, que la tercera pasada comprueba.

| Conjunto | Preguntas | Correctas | Mejorables | Incorrectas |
|---|---|---|---|---|
| bike_sharing | 38 | 36 | 2 | 0 |
| items_sales | 39 | 37 | 2 | 0 |
| items_sales_long | 39 | 35 | 4 | 0 |
| h2o | 40 | 36 | 4 | 0 |
| Total | 156 | 144 | 12 | 0 |

Sin fallo en los cuatro conjuntos: ningún código Python cuando hay un script validado (comprobado también por programa); MASE siempre contra el naive de un paso, nunca contra la fila del baseline; ninguna tendencia deducida de una tabla recortada; todas las preguntas trampa declinadas (tiempos, RMSE, importancia de variables, fechas que faltan, error por fold, candidato peor, precisión futura, desfase de una fecha); `overrides_plan` con sus seis decisiones y sus dos avisos; `free_text_plan` con los pasos y las observaciones reales, no 999 ni 5; ForecasterStats y ForecasterFoundation bien contados en `stats_backtest` y `compare_default`; la licencia de Chronos-2 sin restricción inventada ni nombre de licencia. Por programa, todo decimal de las respuestas está literalmente en su contexto, con la excepción que sigue.

Los dos hallazgos de la primera pasada:
- Zona horaria: resuelto. `time_zone_cv` y `time_zone_backtest_code` no dan ningún desfase ni nombre de zona en ningún conjunto ("Information about the time zone of the dates is not available in the provided context").
- Filas desordenadas: de 3 de 4 a 1 de 4. bike_sharing, items_sales e items_sales_long lo dicen bien ("While the code handles sorting", "though they were sorted before profiling", "which is also handled by the generated code"). h2o sigue: "In time series analysis, observations must be strictly chronological, so the dataset must be sorted by date" y "Sort the index: Ensure the DataFrame is sorted chronologically by its date index". Con el contexto diciéndolo dos veces, es del modelo; la pregunta del escenario ("or fix before forecasting") invita a recetar.

Mejorables (12), todas vistas en la segunda pasada:
- `foundation_backtest`, 4 de 4 en la pregunta principal: se pierde "up to" ("17 folds (17 inference windows)", "resulting in 72 total inference windows", "executed 72 inference windows", "6 folds across 6 inference windows"). En las dos pasadas. Con estos datos el número es exacto.
- `foundation_backtest`, "Was every series forecast in every fold?", 2 de 2: "Yes, every series was forecast in every fold". Cierto con estos datos (series completas); el contexto solo da una cota.
- `backtest_code`, pregunta trampa, 3 de 4: declina bien, pero remite a `result.code` o a nada, no a `assistant.backtest()` (items_sales sí lo hace).
- items_sales_long, `forecast`: redondea a seis decimales ("predicted values average 20.191796", "minimum is 17.468051"); el contexto da 20.191795936620537. Una vez; el redondeo es correcto.
- h2o, `data_warnings`: lo de arriba.
- h2o, `profile`, pregunta trampa: "significant partial autocorrelation at annual intervals, specifically lags 1, 13, 12, 11, 10, 14, and 9"; ni el 1 ni el 9 son anuales. Una vez.

Mediocres aunque pasan la lista: en `cv`, a "Why this initial training size and refit setting" responde con los parámetros, sin razones, en los cuatro conjuntos y en las dos pasadas; en `compare`, items_sales e items_sales_long no citan el "17.1% ahead" del resumen (bike_sharing y h2o sí citan el suyo).

### 22.4 Frente a 0.3.0

Las 38 preguntas comunes de bike_sharing e items_sales, contra `0.3.0_*.md` (gemini-3.5-flash). Ninguna es peor en exactitud. Mejoran: ya no dice "the model is good enough to deploy" ni "partially ready for deployment", no redondea ("approximately 17.47 to 24.27"), no adivina tiempos ("a fraction of a second"), y no dice "naive baseline" a secas. Más pobres en información: `cv` (0.3.0 daba razones, algunas sin apoyo en el contexto) y `compare` en items_sales (0.3.0 citaba el porcentaje del resumen). El desliz de los lags de items_sales ya estaba en 0.3.0 con otras cifras.

### 22.5 Puntos de la lista sin comprobar

Estado tras la segunda pasada; 22.7 dice cuáles cubre la tercera. Ningún escenario los enviaba; quedaban cubiertos solo por los tests:
- fechas fuera de los años 1677 a 2262 en formato largo (12);
- `<script>` con la ruta de un perfil guardado de un CSV (14): solo se ve `data.csv`;
- "No baseline" con un intervalo asimétrico (18) y la nota de datos distintos del perfil (18);
- licencia restringida, cuenta del proveedor de TabPFN y T0 (19): el escenario usa Chronos-2 a propósito, como dejó anotado el README; la pregunta trampa de licencia lo cubre en parte;
- `PlanEditsDiscardedWarning` (19), que necesita un `refine_plan()` con ediciones a mano;
- la frase de la serie que predice ForecasterDirectMultiVariate, las window features dejadas fuera, la nota de diferenciación de `compare()` y las frases de escalado y de NaN (19);
- los candidatos del perfil con frecuencias multiplicadas o por segundos (21.8): ningún conjunto tiene esa frecuencia;
- "up to N inference windows" con una serie que acaba antes, el único caso en que la cota no es exacta: ningún conjunto lo tiene con un backtest foundation.

ForecasterStats que aconseja `dropna_from_series` (18) no llegó a implementarse: no hay nada que comprobar. Los cambios que tocan `llm/context.py` sin cambiar un byte de lo enviado (13) no se comprueban por respuesta.

### 22.6 Conclusión tras la segunda pasada

El check pasaba. Los dos fallos que venían del contexto estaban corregidos y repetidos; los que quedaban eran aislados o no daban ninguna afirmación falsa con estos datos. Lo que se anotó aquí para 0.5.0 (que `inference_windows` diga que es una cota, con un escenario de serie incompleta) se hizo en esta misma release por decisión del autor, junto con lo demás de 22.7.

El aviso `DeprecationWarning: The 'generic' unit for NumPy timedelta is deprecated` que imprime el script no es del proyecto: lo emite pandas 2.3 con numpy 2.5 al construir cualquier `pd.Timedelta`, y `pyproject.toml` ya lo ignora en la suite.

**Tests.** De 4236 a 4239 pasados, más 1 omitido, en macOS con el entorno conda local. Ningún golden del contexto del LLM cambió.

### 22.7 Ampliación y tercera pasada (código final)

Con margen antes de la release, el autor pidió corregir lo que la segunda pasada dejó mejorable en lugar de anotarlo para 0.5.0.

| Commit | Contenido |
|---|---|
| `1fd6e2b` | `llm/context.py`: `inference_windows: up to N` en `<backtesting_strategy>` (también en `describe()`), y en el `<script>` de un `backtest_code()` la frase "It has not been run: for its metrics, the user runs it or calls `assistant.backtest()`." |
| `4b29dfa` | `check_ask_context.py`: escenarios `foundation_incomplete`, `restricted_license_plan`, `multivariate_plan` y `compare_no_baseline` |
| `d3c9932` | Procedencia de la estrategia (abajo) |
| `b0baf2a` | `check_ask_context.py`: escenario `cv_defaults` y listas de `cv`, `backtest` y `compare` |
| este | Los cuatro informes de la tercera pasada, el registro del README y esta sección |

**Procedencia de la estrategia (`d3c9932`).** A "Why this initial training size and refit setting?" el modelo solo repetía los parámetros, porque el contexto no daba ninguna razón ni decía qué había elegido el usuario. Ahora el resultado de `create_cv()` lo dice, como `ForecastPlan.overridden_fields` para el plan:
- `overridden_fields`: los argumentos pasados con valor distinto de None (uno igual al valor por defecto cuenta);
- `fields_without_effect`: los que no cambian lo que se ejecuta (`fixed_train_size` sin refit; `refit` y `fixed_train_size` con ForecasterStats cuando skforecast ejecuta otro valor, o con un modelo foundation);
- `llm_configured`: si el LLM de `create_cv(prompt=...)` puso el resto (False en el fallback);
- `defaults_explanation`: la regla que fijó `initial_train_size` (70 % de las observaciones, subido a lo que necesita el forecaster, bajado para que queden dos folds) y por qué se entrena una vez. Va aparte de `explanation`, que no cambia ni un byte y sigue igual a la que reconstruye `backtest()`.

`backtest()` y `compare()` llevan lo mismo cuando reciben ese resultado (`cv_overridden_fields`, que es None con un `TimeSeriesFold`, y los otros tres con el prefijo `cv_`), calculado para el plan que se ejecuta: si no es el de la estrategia, el texto lo dice. La CLI y el servidor MCP pasan ya el resultado completo. Decisiones tomadas durante la implementación:
- un cuarto campo, `fields_without_effect`, que el plan aprobado no tenía: sin él un backtest no puede decir qué argumento no tuvo efecto, porque no guarda el splitter como se dio;
- en una comparación nada se informa como "sin efecto" y la frase es "The shared strategy trains once by default": el efecto depende de cada candidato (ForecasterStats se reentrena en cada fold, sobre la ventana que para los demás no hace nada);
- "otro plan" se decide por lo que afecta al valor por defecto (forecaster, estimador, tipo de tarea, pasos y argumentos del forecaster), no por igualdad completa: cambiar la métrica no es otro plan;
- no se da la razón de un valor por defecto cuando el splitter ya no lo tiene (un `CVResult` editado después de `create_cv()`);
- `backtest_code()` no lleva procedencia: su contexto lee la estrategia del script;
- el aviso `IgnoredArgumentWarning` de ForecasterStats queda como estaba.

Revisiones: `conventions-reviewer` (encontró las frases falsas en comparaciones con ForecasterStats o foundation) y `/code-review` (el `CVResult` editado y `skip_folds=[]`, que se aplicaba sin registrarse); el subagente de tests encontró que `create_cv()` y `backtest()` nombraban los argumentos en distinto orden. Todo corregido antes del commit. Goldens: `cv_strategy_stats`, `backtest_foundation_multi_series_quantiles`, `code_generation_backtest` y `code_generation_stats_backtest`. La portada (`home-data.json`) y los esquemas de los tools del MCP no cambian.

**Tercera pasada**, 2026-10-05, `google:gemini-3.8-flash`, contextos idénticos a los de un `--dry-run` del código final.

| Conjunto | Escenarios | Preguntas | Correctas | Mejorables | Incorrectas |
|---|---|---|---|---|---|
| bike_sharing | 21 | 43 | 41 | 2 | 0 |
| items_sales | 19 | 45 | 43 | 2 | 0 |
| items_sales_long | 19 | 45 | 44 | 1 | 0 |
| h2o | 23 | 45 | 43 | 2 | 0 |
| Total | | 178 | 171 | 7 | 0 |

Alcance de la lectura: bike_sharing e items_sales, todas las respuestas; items_sales_long y h2o, enteras las de los escenarios nuevos o cambiados y el comienzo de las demás, cuyos contextos son los de la segunda pasada. Por programa, en los cuatro: ningún bloque de código fuera de `qa` y todo decimal de las respuestas está literalmente en su contexto (el redondeo de la segunda pasada no se repitió).

Lo que la segunda pasada dejó mejorable:
- El "por qué" de la estrategia: resuelto, 4 de 4 en `cv` y 4 de 4 en `cv_defaults`. "This cutoff corresponds to the default baseline of 70% of the 2000 dataset observations, which equals 1400 observations"; "This configuration was chosen by the user rather than determined by default rules"; "Training once by default avoids multiplying the computational cost by the 24 backtesting folds". `backtest` también lo recoge cuando lo menciona ("`refit` is set to False (a user-specified choice)").
- "up to" de las ventanas de inferencia: resuelto, se conserva en 4 de 4. A "Was every series forecast in every fold?" ya no responde "Yes": "it cannot be definitively confirmed whether every series was forecast in every single fold".
- Serie incompleta (`foundation_incomplete`, 69 ventanas reales frente a la cota de 72): "Not every series was forecast in every fold: the model only forecasts each series in folds where it has data, and item_3 ends early on 2014-11-22", y declina dar el número de ventanas de esa serie.
- Métrica de un script de backtest: resuelto, 4 de 4 remiten a `assistant.backtest()`.
- Filas desordenadas: sigue en 2 de 4, ahora bike_sharing y h2o ("Time series models require data to be sorted chronologically by date"; "Sorting them chronologically is required for time series forecasting"), sin decir que el código ya las ordena; los dos items_sales lo dicen bien. Es del modelo: cambia de conjunto entre pasadas con el mismo contexto.

Escenarios nuevos:
- `multivariate_plan`: correcto. Predice solo item_1 con los lags de todas, y no promete nada para las otras series.
- `compare_no_baseline`: correcto en los dos conjuntos. Dice que no hay baseline y por qué (intervalo `[0.1, 0.8]`), cómo obtenerlo, y no confunde el MASE con el baseline.
- `restricted_license_plan`: nombra la licencia y su enlace en 4 de 4 y declina el precio en 4 de 4. En 2 de 4 endurece "restricts commercial use" del plan: "No, you cannot use this model in a commercial product because its weights are released under a non-commercial license" (items_sales) y "which prohibits commercial deployment" (items_sales_long). bike_sharing ("cannot use this model in a commercial product without restriction") y h2o ("without reviewing its terms") se quedan en lo que dice el contexto. Es lo mismo que el README anotó con gemini-3.5; va en la dirección prudente y remite al texto de la licencia.
- `cv_defaults`, pregunta trampa (por qué el gap es 0 y se permiten folds incompletos): en 3 de 4 presenta como motivo lo que el parámetro hace ("The parameter `gap` is set to 0 to simulate real-time forecasting"); el contexto no da ninguna razón para esos dos. items_sales_long lo describe sin atribuirlo a una regla.

**Puntos de 22.5 que la tercera pasada sí cubre:** la licencia restringida, la frase de la serie que predice ForecasterDirectMultiVariate, "No baseline" con un intervalo asimétrico y la cota de las ventanas con una serie que acaba antes. Siguen sin escenario: las fechas fuera de 1677 a 2262, la ruta de un perfil guardado en `<script>`, la nota de datos distintos del perfil, `PlanEditsDiscardedWarning`, las window features dejadas fuera, la nota de diferenciación de `compare()`, las frases de escalado y de NaN, y los candidatos con frecuencias multiplicadas.

**Conclusión.** El check pasa sobre el código final: ninguna respuesta incorrecta en 178. Las 7 mejorables son del modelo (ordenar datos que el código ya ordena, endurecer una licencia, dar por motivo la función de un parámetro) y ninguna inventa una cifra. Fuera de alcance, anotado: los notebooks de la documentación tienen salidas anteriores a esta versión.

**Tests.** De 4239 a 4401 pasados, más 1 omitido, en macOS con el entorno conda local.

### 22.8 Mínimo de la primera ventana en `create_cv(prompt=...)`

Encontrado al revisar el prompt, no en el check (que solo ejercita `ask()`). La regla 2 de `_CV_ROLE_PROMPT` daba como mínimo "2 * max_lag", y el contexto del agente lo calculaba así desde los lags, mientras las reglas usan la ventana del forecaster (que cuenta también las window features y el orden de diferenciación) más los pasos. Además el bucle de reintentos solo validaba con `build_cv` (dos folds, fecha localizable): una primera ventana demasiado corta pasaba, `create_cv()` avisaba y `backtest()` fallaba.

Cambios (`llm/refinement.py`, `llm/agent.py`, `llm/prompts.py`):
- el agente recibe el mínimo que calculan las reglas (`_compute_min_train_size`) y la regla 2 remite a esa línea del contexto;
- una sugerencia cuya primera ventana no alcanza lo que el forecaster necesita (`first_window_issue`, lo mismo que haría fallar el backtest) se reintenta con el motivo y el mínimo, y tras tres intentos se cae a los valores deterministas con el aviso de siempre.

Queda sin cambiar, porque se sincroniza desde skforecast: el skill `backtesting-configuration`, que el agente recibe como referencia, sigue dando "2 * max_lag" como regla general. El contexto da el número concreto y la validación lo respalda. Este camino no tiene comprobación con modelo real en el repositorio; el autor lo prueba a mano.

**Tests.** De 4401 a 4404 pasados, más 1 omitido.
