# Preparativos para el servidor MCP de skforecast-ai

Estado a 30/09/2026, rama `0.4.x`. Este documento sirve para retomar el trabajo en otra sesión: qué se decidió, qué está hecho, qué falta y en qué orden, y cómo verificarlo.

## 1. Objetivo y decisiones de fondo

- **El objetivo es que skforecast-ai sea la herramienta que llaman los agentes de código** (Claude Code, Cursor, Claude Desktop, ChatGPT) cuando se les pide un forecast. El agente pone el LLM; skforecast-ai pone las decisiones deterministas (perfil, plan, CV, backtest, comparación) y el script que se ejecutó.
- **El MCP vive en skforecast-ai, no en skforecast.**
  - skforecast es una librería flexible basada en objetos de Python, y llega mejor a los agentes con skills y documentación, que ya existen.
  - MCP encaja con operaciones completas, con estado y validadas, que es lo que ofrece skforecast-ai.
  - Se presenta desde skforecast (README, documentación, registros de MCP con "skforecast" en el nombre), porque ahí está la comunidad.
- **Requisito de fondo antes del servidor: que el núcleo no falle sin avisar.** Un agente se cree un resultado `ok`, así que todo lo que hoy pasa sin error o falla tarde hay que convertirlo en un error claro o en un aviso dentro del resultado.

## 2. Hecho en la sesión del 30/09/2026

Está en el working tree **sin commitear**; comprueba `git status` antes de seguir. Los tres bloques tienen tests y entrada en `docs/releases/releases.md` (0.4.0).

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

## 3. Pendiente por parte del autor

- **Revisar y hacer commit** de lo anterior.
- **Antes de la release, lanzar `python tools/ai/check_ask_context.py` con un modelo real.** Cambiaron `llm/prompts.py` (regla 4 del CV: `refit=False` por defecto) y las explicaciones del plan y del CV. El informe se guarda según `tools/ai/ask_context_reports/README.md`. Con `--dry-run`, que no cuesta nada, ya se comprobó que los contextos se generan.
- **Entorno `skforecast_ai_py13`:** trae skforecast 0.25.0 (el proyecto exige `>=0.26`) y su instalación editable apunta a `skforecast-ai-home-page`, no a este checkout. Hasta arreglarlo, ejecuta siempre con `PYTHONPATH=.` (ver la sección 8).

## 4. Trabajo pendiente, en orden recomendado

### 4.1 Seguridad: código ejecutable dentro de un plan (bloquea el MCP)

**El problema.** `ForecastPlan.preprocessing_steps[].code_snippet` se inserta en el script con `format_map` y se ejecuta con `exec`. Está en `_emit_preprocessing_steps`, [rendering/_helpers.py:170](../skforecast_ai/rendering/_helpers.py#L170): el snippet se escribe en la línea 193. Un plan cargado desde JSON puede, por tanto, ejecutar código arbitrario; se comprobó creando un fichero. Hoy ya afecta a la CLI con `--from-plan`.

**Otros campos que acaban en el script sin validar**, según una auditoría que conviene confirmar:
- `forecaster_kwargs["transformer_y"]` y `["transformer_series"]`, que se renderizan como `f"{name}()"`;
- `encoding` y `categorical_features`.

**Propuesta:**
- No confiar nunca en el `code_snippet` que trae un plan. Regenerarlo desde `action` con un mapa cerrado (acción → plantilla, las mismas que emite `derive_preprocessing_steps` en `recommendation/preprocessing.py`), o que el validador de `ForecastPlan` rechace cualquier snippet que no coincida con la plantilla de su acción.
- Validar contra listas cerradas todas las cadenas de `forecaster_kwargs` que llegan al script.
- Test: un plan JSON con un snippet o un transformer inyectado no valida, o no ejecuta nada.

### 4.2 Punto 3: que los avisos lleguen en el resultado

- **`ForecastPlan.warnings` existe pero nadie lo rellena** ([schemas/plans.py:434](../skforecast_ai/schemas/plans.py#L434)). Es el sitio para:
  - forecaster no recomendado (`UnrecommendedForecasterWarning`, en `plan()`);
  - baseline con valores faltantes;
  - kwargs de LightGBM o XGBoost desconocidos;
  - variables de calendario omitidas.
- **Los warnings de skforecast se tratan distinto según el método:**
  - los backtests pasan `suppress_warnings=True` ([rendering/backtesting.py:107](../skforecast_ai/rendering/backtesting.py#L107), también en las líneas 139, 403 y 521);
  - `forecast()` los deja salir como warnings de Python normales, sin guardarlos.

  Decidir un criterio común, por ejemplo capturarlos en la ejecución y guardarlos en el resultado.
- **`DataProfile.warnings`** ([schemas/profiles.py:198](../skforecast_ai/schemas/profiles.py#L198)) no aparece en `profile.explanation`.
- **Precedente útil:** `compare()` ya registra los fallos de candidatos en el resultado (`failures`, columna `error`).
- **Objetivo:** en MCP y en la CLI con `--format json` los warnings de Python se pierden. Todo aviso relevante debe estar en el resultado.

### 4.3 Punto 4: más decisiones del plan que se puedan cambiar

Hoy `plan()` ([assistant.py:340](../skforecast_ai/assistant.py#L340)) y `RefinePlanOverrides` ([schemas/plans.py:252](../skforecast_ai/schemas/plans.py#L252)) solo aceptan forecaster, estimator, estimator_kwargs, steps, interval, lags y window_features.

**Faltan overrides para:**
- `use_exog` y qué columnas exógenas usar (hoy son todas o ninguna);
- `calendar_features` (lista o None);
- `differentiation` (ninguna regla lo activa nunca);
- `transformer_y` y `transformer_series`;
- `dropna_from_series`;
- `metric` en `backtest()` (hoy solo en `compare()`).

**Otros cambios del mismo bloque:**
- `refine_plan()` ([assistant.py:748](../skforecast_ai/assistant.py#L748)) reconstruye el plan desde cero y descarta las ediciones manuales. Debe conservar los overrides nuevos.
- `CandidateConfig` ([schemas/plans.py:297](../skforecast_ai/schemas/plans.py#L297)) solo varía 5 claves, así que no permite comparar con y sin exógenas o con y sin diferenciación.
- Corregir [docs/user-guides/cli-usage.md:108](../docs/user-guides/cli-usage.md#L108), que dice que todas las decisiones, incluidas las variables de calendario, se pueden sobrescribir.

Por qué importa: si el agente no puede corregir una decisión desde la API, deja la herramienta y escribe el código de skforecast directamente, que es justo lo que se quiere evitar.

### 4.4 Punto 5: resumen público para agentes

- Pasar `_build_llm_context()` (en `schemas/results.py`, líneas 123, 214, 405 y 760, y en `schemas/profiles.py:345`) a un método público y estable, por ejemplo `result.describe()`.
- Ya tiene límites de tamaño (30 filas, 5 series, 15 lags) y goldens en `tests/tests_llm/golden/`.
- Revisar que incluya lo que un agente necesita para decidir el siguiente paso: los warnings del punto 4.2, el coste (`n_fits`) y qué se puede cambiar.
- Es lo que devolverán los tools, en lugar de `model_dump()`, que llega a 25 MB (ver la sección 7).

### 4.5 El servidor MCP

- **Paquete:** extra `skforecast-ai[mcp]` y comando `skforecast-ai mcp` (transporte stdio). `fastmcp` y `mcp` ya están instalados en el entorno de desarrollo.
- **Tools:** `profile`, `plan`, `refine_plan`, `create_cv`, `backtest`, `compare` y `forecast`. No se exponen `ask()` ni los modos con `prompt`, porque el agente es el LLM y los caminos sin LLM ya están completos.
- **Estado en el servidor:** perfiles, planes, CV y resultados se guardan con un id y el agente se refiere a ellos por id. `CVResult`, `BacktestResult`, `ForecastResult` y `ComparisonResult` no se pueden reconstruir desde JSON (`JSONFrame` solo serializa), así que no se intenta.
- **Nunca aceptar planes completos en JSON:** solo overrides sobre un plan guardado (ver la sección 4.1).
- **Datos por ruta o URL,** nunca por el contexto del agente. Las predicciones completas van a un fichero y el tool devuelve la ruta y el resumen.
- **Progreso:** `compare()` puede tardar más de 60 s (ver los tiempos en la sección 7). Añadir un callback por candidato para enviar notificaciones de progreso de MCP. Pasar `show_progress=False`.
- **stdout:** verificado limpio a nivel de descriptor (0 bytes en todos los flujos). `exec_rendered` redirige stdout y la barra de progreso escribe en stderr.
- **Un servidor que siga vivo entre llamadas sale ganando:** Foundation tarda 5 s en la primera llamada y 0,8 s en las siguientes.
- **Mensajes de error escritos para Python:** algunos mencionan `exc.failures[...]`, `refine_plan()` o `llm=`. Adaptarlos en la capa del tool.
- **Skill para agentes:** "forecasting con skforecast-ai", con el orden de uso y cuándo fiarse de cada resultado. Una opción barata para validar la idea antes del servidor es un skill que use la CLI.

## 5. Seguimientos menores

- **Formato largo, rutas que ya fallaban al generar el script:**
  - datos en memoria con DatetimeIndex y sin columna de fecha: el reshape usa `'datetime'` (`_emit_reshape_series_long_to_dict`, [rendering/_helpers.py:1087](../skforecast_ai/rendering/_helpers.py#L1087));
  - entrada con MultiIndex: la ejecución recibe el frame original.
- **Choques de nombres entre lags o window features (`lag_1`, `roll_mean_7`) y columnas exógenas.** Solo se resolvió el caso del calendario.
- **El coste de inferencia de ForecasterFoundation no entra en el presupuesto de `compare()`:** cuenta 0 ajustes. En `bike_sharing`, con 220 folds, es la mayor parte de los 66 s que quedan.
- **`compute_series_pacf`** ([recommendation/autoregressive.py:116](../skforecast_ai/recommendation/autoregressive.py#L116)) lee los datos sin deduplicar.
- **El alias `result` de `ask()`** dice que se elimina "in 0.4.0" ([assistant.py:2395](../skforecast_ai/assistant.py#L2395)), pero sigue existiendo en 0.4.0.
- **Oportunidad aparte del MCP:** un paso `diagnose()` determinista (error por horizonte, fold y serie, sesgo, autocorrelación de residuos) que proponga overrides a `refine_plan()` y candidatos a `compare()`. Encaja después como un tool más.

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

## 7. Datos medidos (para dimensionar el servidor)

Con `bike_sharing` (horario, 17.544 filas, `steps=24`, 220 folds):

| Caso | Tiempo |
|---|---|
| `compare()` con el CV por defecto (`refit=False`) | 66 s |
| `compare()` con `refit=True` (excluye Direct) | 145 s |
| Direct con `refit=True`, 5.280 ajustes (extrapolado, sin ejecutar) | ~64 min |
| Direct con `refit=False` | 17 s |

Con `h2o` (mensual, 204 filas), `compare()` tarda 51 s, de los que 30 s son Auto-ARIMA reentrenando en 6 folds. Con el nuevo valor por defecto, `refit=False`, Auto-ARIMA se ajusta una vez.

| Tamaño (`store_sales`: 500 series, 913k filas) | Valor |
|---|---|
| `model_dump` del perfil | 259 KB |
| `model_dump` del backtest | 25 MB |
| Resumen para LLM del backtest | 48k caracteres |
| Backtest | 25 s |
| Import de `skforecast_ai` en frío | ~1,2 s |

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
