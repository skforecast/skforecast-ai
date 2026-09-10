# Plan de acción: skforecast-ai (rama 0.3.x)

Documento de trabajo interno. Recoge las tareas de mantenimiento identificadas en
la revisión de septiembre de 2026 de `ForecastingAssistant` y sus módulos de
apoyo. Cada tarea está escrita para poder abordarse en una sesión independiente
sin necesidad de más contexto: qué se cambia, dónde, cómo y cuándo se considera
terminada.

Prioridad acordada:

1. **Fase 1**: bugs e inconsistencias cuya corrección no cambia (o apenas cambia)
   el comportamiento visible para el usuario.
2. **Fase 2**: adelgazar código. No cambia el comportamiento, facilita la lectura.
   Empieza por `assistant.py` pero se extiende al resto del paquete.
3. **Fase 3**: cambios de API. Se listan para no perderlos, pero cada uno requiere
   una decisión explícita antes de abordarlo y una entrada en `releases.md`.

Las tareas dentro de cada fase están ordenadas por relación coste/beneficio.
Las referencias a líneas corresponden al commit `8075dfa` y pueden desplazarse.


## Protocolo por sesión

- Antes de tocar nada: `pytest -n auto` en el entorno acordado (ver `AGENTS.md`:
  preguntar qué entorno conda usar la primera vez). Anotar el número de tests que
  pasan. Baseline en el momento de escribir esto: 740 tests.
- Los cambios se dejan sin commitear en el árbol de trabajo: los revisa el
  autor y decide él cómo agruparlos en commits antes de subirlos. Claude no
  hace commits. Si una tarea destapa otra, apuntarla aquí en vez de
  encadenarla.
- Al terminar: `pytest -n auto` y `ruff check skforecast_ai tests`. En Fase 1 y 2
  los tests existentes deben pasar sin modificar sus aserciones; si hay que
  cambiar una aserción, la tarea está cambiando comportamiento y hay que
  justificarlo en el commit.
- Ruff no está limpio en la baseline: 37 errores preexistentes (29 `E741` por
  variables llamadas `l` en tests, 7 `F401` imports sin usar en tests, 1 `F541`
  en `profiling/data_profile.py`). Comparar contra ese número, no contra cero.
  Limpiarlos es una tarea de Fase 2 (añadida como 2.7).
- Los tests golden de `tests/tests_llm/golden/` son el detector de regresión de la
  capa LLM. Si cambian, regenerar con `tools/update_golden_llm_contexts.py` solo
  cuando el cambio de contexto sea intencionado.
- Nada de guiones largos (em dash, en dash) en código, docstrings ni mensajes.
  Es una regla de `AGENTS.md` y se incumple en varios sitios (ver tarea 1.6).
- Marcar cada tarea como hecha en este documento con la fecha; el commit lo
  rellena el autor al subirlo.


## Fase 1: bugs e inconsistencias

### 1.1 `forecast()` y `forecast_code()` descartan `lags` y `window_features` en silencio cuando se pasa `plan`

**Qué.** `_warn_if_plan_overrides_ignored` (`_utils.py:356`) solo avisa de
`forecaster`, `estimator`, `estimator_kwargs` e `interval`. Sin embargo
`forecast()` y `forecast_code()` también aceptan `lags` y `window_features`, que
con un `plan` prefabricado se ignoran sin ningún aviso.

**Cómo.** Añadir `lags` y `window_features` a la firma y a la lista de
comprobación del helper. Actualizar las tres llamadas (`forecast_code`,
`forecast`, `_prepare_backtest`); en `_prepare_backtest` pasar `None` porque
`backtest()` no acepta esos argumentos.

**Hecho cuando.** Un test en `test_assistant_forecast.py` comprueba que pasar
`plan=...` junto con `lags=[1, 2]` emite `IgnoredArgumentWarning` nombrando
`lags`. Comportamiento nuevo: un warning donde antes no había nada.

---

### 1.2 `refine_plan()` pierde `end_train` y `llm_refined_fields`

**Qué.** `refine_plan()` (`assistant.py:514`) reconstruye el plan llamando a
`self.plan()`, que crea un `ForecastPlan` nuevo. Se pierden dos campos:

- `end_train`: si el plan venía de `forecast(test_size=...)`, el plan refinado
  vuelve a modo predicción sin avisar.
- `llm_refined_fields`: si el plan original fue refinado por el LLM y ahora se
  refina de forma determinista (por ejemplo, cambiando `estimator_kwargs`), los
  `lags` LLM se conservan (se leen de `plan.forecaster_kwargs`) pero el marcador
  desaparece. El display deja de señalarlos como sugeridos por el LLM.

**Cómo.** Tras obtener `refined_plan`, aplicar `model_copy(update=...)` con
`end_train=plan.end_train` y con los `llm_refined_fields` heredados del plan
original para los campos que no se hayan sobreescrito explícitamente ni
reasignado por el LLM en esta llamada. El bloque que ya asigna
`refined_plan.llm_refined_fields = llm_applied_fields` debe fusionar, no
reemplazar.

**Hecho cuando.** Dos tests nuevos en `test_assistant_refine_plan.py`:
`end_train` sobrevive a un `refine_plan(steps=...)`, y `llm_refined_fields`
sobrevive a un refinado determinista que no toca `lags`.

---

### 1.3 `CodeGenerationResult` no es `ExplainableResult`

**Qué.** `CodeGenerationResult` (`schemas/results.py`) tiene `profile`, `plan` y
`code`, pero no hereda de `ExplainableResult`, así que
`ask(result=code_result)` lanza `TypeError`. Es el único resultado del
asistente que no se puede explicar. Para explicar un script generado hoy hay
que pasar `profile=` y `plan=` por separado, que es justo lo que el resultado ya
contiene.

**Cómo.** Hacer que herede de `ExplainableResult` e implementar
`_build_llm_context` con `render_dataset_section`,
`render_profile_decision_section` y `render_plan_section` (las mismas que usa
`SingleRunResult`, sin métricas ni predicciones). En `ask()`, el
`DataSentToLLMWarning` de modo resultados no aplica aquí porque no hay
predicciones: añadir a `LLMContext` un campo `contains_data: bool` que cada
resultado rellene, y emitir el warning solo cuando sea `True`.

**Hecho cuando.** `ask(result=assistant.forecast_code(...))` funciona, el
contrato de `tests_llm/test_explainable_result_contract.py` cubre
`CodeGenerationResult`, y no se emite `DataSentToLLMWarning` para él.

---

### 1.4 `cv_config` se construye a mano en dos sitios

**Qué.** El diccionario con `steps`, `initial_train_size`, `refit`, ...,
`n_folds` se monta idénticamente en `backtest()` (`assistant.py:1568`) y en
`compare()` (`assistant.py:1761`), junto con la llamada a `_count_cv_folds` y
`build_cv_explanation`. Un campo nuevo de `TimeSeriesFold` habría que añadirlo
en dos sitios.

**Cómo.** Extraer `_resolve_cv_config(cv, profile) -> tuple[dict, str]` (config
más explicación) en `_utils.py` o en `recommendation/backtesting.py`, y usarlo
en ambos métodos. `create_cv()` construye algo muy parecido a partir de
`defaults`; comprobar si puede usar la misma función.

**Hecho cuando.** Una única definición del diccionario; tests sin cambios.

---

### 1.5 `_exec_rendered_code` está duplicada en los dos runners

**Qué.** `execution/forecast_runner.py:184` y
`execution/backtesting_runner.py:133` contienen la misma función (compilar,
capturar stdout, envolver en `ForecastExecutionError`). Difieren solo en el
nombre del fichero virtual (`<forecast>` / `<backtesting>`), en la inyección de
`exog_future` y en el parche por regex de `show_progress`.

**Cómo.** Crear `execution/_exec.py` con
`exec_rendered(rendered, namespace, filename) -> dict`. Cada runner prepara su
`namespace` y, en el caso del backtesting, aplica el parche de `show_progress`
antes de llamar. Valorar sustituir el parche por regex por un parámetro del
renderer (`show_progress` ya es un argumento de `render_backtesting_*`... si no
lo es, añadirlo es más limpio que reescribir el código generado).

**Hecho cuando.** Una única función de ejecución; `tests_execution` sin cambios.

---

### 1.6 Guiones largos en mensajes, comentarios y código generado

**Qué.** `AGENTS.md` prohíbe em/en dashes. Aparecen en 11 sitios de
`skforecast_ai/` (excluyendo `skills/`, que se sincroniza desde skforecast).
Cuatro son visibles para el usuario:

- `assistant.py:2258` (mensaje de `ValueError` en `_prepare_backtest`)
- `cli.py:522` (mensaje de error de validación)
- `execution/backtesting_runner.py:220` (texto de `BacktestResult.explanation`)
- `rendering/foundation.py:122` (comentario dentro del script generado)

El resto son comentarios de código en `assistant.py`, `provider.py`,
`autoregressive.py`, `explanation.py` y `data_profile.py`.

**Cómo.** `grep -rn "—\|–" skforecast_ai --include='*.py' | grep -v skills/`
y sustituir por coma, dos puntos o paréntesis. Añadir un test que falle si
vuelven a aparecer fuera de `skills/` (uno de una línea en `test_utils.py` o
similar).

**Hecho cuando.** El grep devuelve cero líneas y el test lo garantiza.

---

### 1.7 `_display_n_observations` vive en `_utils` y se importa perezosamente desde `_display`

**Qué.** `_display.py:412` hace `from ._utils import _display_n_observations`
dentro de una función para evitar un import circular; `llm/context.py` la
importa también. Es una propiedad del `DataProfile`, no una utilidad del
asistente.

**Cómo.** Mover la lógica de `_series_span_length` y `_display_n_observations`
a `schemas/profiles.py` como propiedad `DataProfile.n_observations_display` (o
nombre similar). Eliminar el import perezoso.

**Hecho cuando.** Ninguna función de `_utils` la reexporta y no quedan imports
dentro de funciones en `_display.py` por esta causa.

---

### 1.8 Limpieza de `pyproject.toml` y del árbol

- El extra `test` lista `pydantic-ai>=2,<3` y `pydantic-ai[groq]>=2,<3` (la
  segunda incluye a la primera) y repite `statsmodels`, que ya es dependencia
  base. Dejar solo `pydantic-ai[groq]` y quitar `statsmodels`.
- `dev/deprecated user guides/` son 15 guías antiguas. Decidir si se borran (están
  en el historial de git) o se mueven a una rama `archive`.
- `dev/compare_forecasters_demo.ipynb` y `dev/h2o_exog.csv`: si el notebook ya
  no aporta nada frente a `docs/user-guides/`, borrar.


### 1.9 `forecast()` ignora `steps` cuando se pasa `plan`

**Qué.** `forecast(data, steps=3, plan=plan_con_steps_5)` predice 5 pasos
sin avisar: con un `plan`, `steps` solo alimenta `_validate_forecast_mode` y
el script usa `plan.steps`. `_prepare_backtest` en cambio lanza `ValueError`
cuando `cv.steps != plan.steps`. Los dos puntos de entrada deberían aplicar
la misma regla (lanzar, o al menos incluir `steps` en el aviso).

**Decisión (2026-09-10): implementada.** Con `plan`, `steps` es opcional en
`forecast()` y `forecast_code()` (toma `plan.steps`) y un valor distinto
lanza `ValueError`, como `backtest()` con `cv.steps`. `forecast()` pasa a
`steps: int | None = None`; sin plan y sin `steps` lanza un `ValueError`
claro en lugar de fallar dentro de la validación del plan.

### 1.10 `docstrings.instructions.md` no aplica a este paquete

Su cabecera dice `applyTo: 'skforecast/**/*.py'`, que no casa con
`skforecast_ai/`. Tras borrar las instrucciones de proyecto, las reglas de
docstrings (backticks simples, sin secciones `Raises`/`Warns`, tipos como
`pandas Series`) no tienen ningún fichero vivo que las aplique. Cambiar el
glob a `skforecast_ai/**/*.py`. Relacionado: `AGENTS.md` prohíbe los guiones
largos en comentarios, docstrings y documentación, pero
`tests/test_source_conventions.py` los prohíbe también en cadenas y mensajes;
ampliar la frase de `AGENTS.md` para que coincida.

**Decisión (2026-09-10): implementada.** `docstrings.instructions.md` apunta
a `skforecast_ai/**/*.py`. `AGENTS.md` reescrito como documento de
convenciones completo y actualizado al layout actual (principios, layout,
entorno, comandos, estilo, docstrings, tests, trabajo con el autor), con la
regla de guiones ampliada a cadenas y mensajes. `CLAUDE.md` nuevo con el
mismo contenido; `tests/test_source_conventions.py` comprueba que los dos
ficheros son idénticos. `.github/copilot-instructions.md` y
`.github/instructions/testing.instructions.md` no se tocan: vienen del
repositorio skforecast.

### 1.11 Entrada de releases

Hecha el 2026-09-10 como sección `0.3.0 (Unreleased)` de
`docs/releases/releases.md` (la etiqueta más reciente es `v0.2.0` y
`pyproject.toml` ya declara `0.3.0`). Recoge lo siguiente, más los cambios
de API de 3.1 y 3.2:

- `forecast()` y `forecast_code()` emiten `IgnoredArgumentWarning` también
  para `lags` y `window_features` cuando se pasa un `plan` prefabricado.
- `refine_plan()` conserva las marcas `llm_refined_fields` de los campos cuyo
  valor se mantiene.
- `ask(result=...)` acepta `CodeGenerationResult`. `LLMContext` gana
  `sends_result_values` (default `True`); `DataSentToLLMWarning` solo se emite
  para resultados que envían valores propios.
- Nuevas API públicas: `recommendation.resolve_cv_config` y
  `DataProfile.n_observations_display`.
- El script generado para `ForecasterFoundation` cambia un comentario
  (`# Fit (stores context only, no training)`).
- Con `profile`, `target`, `date_column` y `series_id_column` son opcionales
  en `forecast()`, `forecast_code()`, `backtest()`, `backtest_code()` y
  `compare()`: se toman del profile. Un valor distinto al del profile, o un
  `data` sin las columnas del profile, lanza `ValueError` (antes se ignoraba
  o fallaba dentro del script ejecutado).


## Fase 2: adelgazar código

Objetivo general: que cada fichero se lea de una pasada y que la lógica viva
junto al subpaquete al que pertenece. Ningún cambio de comportamiento; los
tests existentes son la red.

### 2.1 `assistant.py`: reducir a orquestación

**Estado.** 2.921 líneas. La clase debería ser una fachada, pero contiene lógica
real en sus helpers privados (líneas 2170 a 2921, unas 750 líneas):

| Helper | Líneas aprox. | Destino propuesto |
|---|---|---|
| `_resolve_compare_candidates`, `_aggregate_metrics`, `_compare_sort_key`, `_build_comparison_table`, `_build_comparison_explanation` | 2265 a 2520 | `execution/comparison.py` (nuevo) |
| `_resolve_model`, `_resolve_agent`, `_resolve_cv_agent`, `_resolve_plan_refinement_agent` | 2521 a 2595 | `llm/runtime.py` (nuevo), ver abajo |
| `_refine_features_with_llm`, `_configure_cv_with_llm`, `_validate_cv_defaults` | 2596 a 2871 | `llm/refinement.py` (nuevo) |
| `_build_ollama_settings` | 2872 a 2921 | `llm/provider.py` |

**Cómo.**

1. Crear `llm/runtime.py` con una clase pequeña `LLMRuntime(llm, base_url,
   api_key)` que posea el modelo y la caché de los tres agentes (hoy son cuatro
   atributos `_model`, `_agent`, `_cv_agent`, `_plan_refinement_agent` en el
   asistente). El asistente crea una instancia en `__init__` y la expone como
   `self._llm_runtime`. Debe seguir siendo importable sin `pydantic-ai`
   instalado (importaciones perezosas dentro de los métodos, como ahora).
2. Mover los helpers de comparación a `execution/comparison.py` como funciones
   de módulo. El bucle principal de `compare()` puede quedarse en el asistente
   (necesita `self.plan` y `self.backtest`) o convertirse en
   `run_comparison(assistant, ...)`; preferible lo primero para que la fachada
   siga siendo el único sitio que encadena métodos públicos.
3. Mover `_refine_features_with_llm` y `_configure_cv_with_llm` a
   `llm/refinement.py` como funciones que reciben el `LLMRuntime`.
4. Los tests que hoy parchean `ForecastingAssistant._resolve_agent` y similares
   (`test_assistant_ask.py`, `test_assistant_refine_plan_llm.py`,
   `test_assistant_create_cv.py`, `fixtures_llm.py`) tendrán que parchear el
   nuevo destino. Es el único cambio esperado en tests.

**Hecho cuando.** `assistant.py` baja de 2.000 líneas (el resto son docstrings,
ver 2.3), ningún helper privado del asistente supera las 40 líneas, y los
tests pasan.

---

### 2.2 `forecast()` y `forecast_code()`: extraer la preparación común

**Qué.** Ambos métodos repiten el mismo bloque de unas 50 líneas: avisar de
overrides ignorados, perfilar si falta `profile`, calcular `evaluate`, validar
modo, planificar si falta `plan`, y estampar `end_train` con `resolve_end_train`
(`assistant.py:837-897` y `1050-1103`). `_prepare_backtest` ya hace este papel
para `backtest()` y `backtest_code()`.

**Cómo.** Extraer `_prepare_forecast(...) -> tuple[ForecastingProfile,
ForecastPlan]` con la misma forma que `_prepare_backtest`. La única diferencia
entre los dos métodos es `require_exog` en `_validate_forecast_mode`; pasarlo
como parámetro.

**Hecho cuando.** Cada uno de los dos métodos públicos queda en menos de 30
líneas de cuerpo.

---

### 2.3 Docstrings repetidos en la fachada

**Qué.** Los parámetros `data`, `target`, `date_column`, `series_id_column`,
`forecaster`, `estimator`, `estimator_kwargs`, `lags`, `window_features`,
`profile` y `plan` se documentan literalmente igual en cinco métodos. Son unas
600 líneas de `assistant.py`. `test_assistant_docstrings.py` ya comprueba que
la sección `Returns` coincide con los atributos del resultado.

**Decisión pendiente.** Dos opciones:

- Mantener los docstrings completos (mkdocstrings los renderiza por método y el
  usuario los lee en el IDE) y ampliar el test para que compruebe que los
  párrafos compartidos son idénticos entre métodos. Coste cero, evita
  divergencias.
- Acortar los docstrings de los métodos secundarios (`forecast_code`,
  `backtest_code`) con una frase que remita al método principal. Ahorra
  líneas, empeora la experiencia en el IDE.

Recomendación: la primera. La tarea es solo añadir el test de consistencia.

---

### 2.4 `rendering/`: el preámbulo se repite entre forecast y backtesting

**Qué.** Para cada `task_type` hay un renderer de forecast y otro de backtesting
(`rendering/backtesting.py`, 626 líneas) que repiten el mismo preámbulo:
imports, carga de datos, index setup, preprocessing, window features, calendar
features, transformer exog y creación del forecaster. Solo cambia la cola
(split + predict + métricas frente a `TimeSeriesFold` + `backtesting_forecaster`).
Cinco pares, cinco copias. Además `render_forecast_multi_series` y
`render_forecast_multivariate` (`multi_series.py`) comparten gran parte del
cuerpo.

**Cómo.** Por cada task type, extraer `_emit_setup_<task>(plan, profile,
mode)` que devuelva `(import_lines, loading_lines, core_lines)` con el
preámbulo, y que tanto el renderer de forecast como el de backtesting lo llamen
y añadan solo su cola. Empezar por `single_series`, que es el más sencillo, y
validar con `tests_rendering` (los tests comparan el script generado, así que
cualquier cambio de espacio en blanco aparecerá).

**Hecho cuando.** `backtesting.py` baja a menos de 300 líneas y los scripts
generados son byte a byte idénticos (los tests de rendering lo garantizan).

---

### 2.5 `cli.py`: opciones repetidas y serializadores a medida

**Qué.** 1.595 líneas. Dos fuentes de repetición:

- Las opciones Typer `--target`, `--date-column`, `--series-id-column`,
  `--forecaster`, `--estimator`, `--estimator-kwargs`, `--interval`,
  `--format`, `--quiet` se declaran completas (tipo, flags, help) en siete
  comandos.
- `_forecast_result_to_json`, `_backtest_result_to_dict`,
  `_comparison_result_to_json` (`cli.py:992-1420`) serializan a mano los
  resultados porque los DataFrames están tipados como `Any` en los schemas.

**Cómo.**

- Declarar alias a nivel de módulo (`TargetOption = Annotated[str | None,
  typer.Option("--target", "-t", help=...)]`) y usarlos en las firmas. Typer lo
  soporta y `mkdocs-typer2` sigue generando la misma documentación.
- Mover la serialización a los propios resultados: un método `to_dict()` en
  `SingleRunResult` y `ComparisonResult` (y `to_json()` que llame a
  `json.dumps` con `default=str`). El CLI se limita a imprimir. Esto prepara la
  tarea 3.5 sin depender de ella.

**Hecho cuando.** Ninguna opción común se declara más de una vez y el CLI no
contiene funciones `_*_to_json` ni `_*_to_dict`. `test_cli.py` y
`test_cli_pipe.py` sin cambios.

---

### 2.6 `_utils.py`: separar por responsabilidad

**Qué.** 715 líneas que mezclan validadores de plan (`_validate_*`,
`_max_window_size`), resolución de entrada (`_resolve_data_and_target`),
helpers de aviso (`_warn_if_*`), cuenta de folds (`_count_cv_folds`) y el bucle
asyncio para los agentes (`_get_agent_loop`, `_run_agent_sync`).

**Cómo.** Mover `_get_agent_loop` y `_run_agent_sync` a `llm/runtime.py` (junto
a la tarea 2.1). Mover `_count_cv_folds` a `recommendation/backtesting.py`
junto a `derive_cv_defaults`. Lo que quede en `_utils.py` son validadores y
resolución de entrada, que es coherente.

**Hecho cuando.** `_utils.py` no importa `asyncio` ni `threading`.

---

### 2.7 Dejar ruff a cero

**Qué.** 37 errores preexistentes: 29 `E741` (variables de una letra `l` en
tests), 7 `F401` (imports sin usar en tests) y 1 `F541` (f-string sin
placeholders en `profiling/data_profile.py:1208`). Sin ellos, `ruff check`
puede pasar a ser un paso de CI en `unit-tests.yml`, que hoy no lo ejecuta.

**Cómo.** `ruff check --fix` para los 8 automáticos; renombrar `l` a mano.
Añadir el paso de ruff al workflow.

**Hecho cuando.** `ruff check skforecast_ai tests` devuelve cero y CI lo
ejecuta.


## Fase 3: cambios de API (requieren decisión)

Cada punto cambia el comportamiento o la firma pública. No abordar sin decidirlo
explícitamente, y cada uno lleva su entrada en `docs/releases/releases.md`.
Ordenados por impacto en la experiencia de uso frente a coste.

### 3.1 Derivar `target`, `date_column` y `series_id_column` del `profile`

Hoy `forecast(data, profile=profile, ...)` sigue exigiendo `target` porque
`_resolve_data_and_target` corre antes de mirar el profile; el notebook paso a
paso lo muestra (se pasan `target` y `date_column` otra vez junto al
`profile`). `profile.data_profile` ya tiene los tres valores. Propuesta: cuando
se pasa `profile`, los tres argumentos son opcionales, se toman del profile, y
si se pasan y no coinciden se lanza `ValueError`. Es un cambio que solo
relaja la API, no rompe llamadas existentes.

**Decisión (2026-09-10): implementada.** Helper `_resolve_inputs_with_profile`
en `_utils.py`, usado por `forecast()`, `forecast_code()` (cuando se pasa
`data` junto al profile), `backtest()`, `backtest_code()` y `compare()`. Un
valor que no coincide con el profile lanza `ValueError`; las columnas del
profile deben existir en `data` (comprobación temprana). El CLI pasa los
valores del usuario tal cual con `--from-plan`/`--from-profile` para que la
librería los reconcilie. El notebook paso a paso ya no repite `target` ni
`date_column` junto a `profile`.

### 3.2 `create_cv()` devuelve un objeto resultado

Es el único método que devuelve una tupla `(TimeSeriesFold, str)`. Propuesta:
`CVResult` con `cv`, `explanation` y `cv_config` (el diccionario de la tarea
1.4), con `DisplayMixin` y `ExplainableResult`, de modo que
`ask(result=cv_result)` funcione. `backtest(cv=...)` y `compare(cv=...)`
aceptarían `TimeSeriesFold | CVResult`. Cambio de tipo de retorno: rompe el
desempaquetado `cv, explanation = assistant.create_cv(...)` de la
documentación. Se puede suavizar haciendo `CVResult` iterable de dos elementos
durante una versión, con `DeprecationWarning`.

Al hacerlo, dos ajustes en `resolve_cv_config`: añadir `skip_folds` y
`allow_incomplete_fold` al diccionario (afectan a `n_folds` y hoy no se
muestran; cambia `cv_config`, el display, el contexto LLM y los golden, por
eso no se hizo en Fase 1), y evitar contar los folds dos veces (`create_cv` y
luego `backtest`, o N+1 veces en `compare`) pasando el `cv_config` ya
resuelto. El mensaje de error de `create_cv` cuando hay menos de 2 folds
imprime `defaults` con la clave interna `_reasoning`; usar `cv_config`.

**Decisión (2026-09-10): implementada con rotura limpia.** `CVResult` en
`schemas/results.py` con `profile`, `plan`, `cv`, `cv_config`, `code`
(el snippet que construye el `TimeSeriesFold`) y `explanation`;
`DisplayMixin` y `ExplainableResult`. Su `__iter__` lanza `TypeError` con un
mensaje que apunta a `.cv` y `.explanation`, porque un modelo pydantic
iteraría sobre sus campos y el desempaquetado antiguo fallaría con un
mensaje confuso. `backtest()`, `backtest_code()` y `compare()` aceptan
`TimeSeriesFold | CVResult`. `cv_config` incluye `skip_folds` y
`allow_incomplete_fold`; el error de menos de 2 folds ya no imprime
`_reasoning`. No se eliminó el doble recuento de folds: es una llamada a
`cv.split` sobre un `RangeIndex`, despreciable frente al backtest. Los dos
notebooks y el CLI actualizados; las salidas de las celdas que mostraban
el `repr` del `TimeSeriesFold` se han vaciado y requieren reejecución.

### 3.3 `ask(prompt, context=...)` con un único argumento polimórfico

`ask()` tiene once parámetros y tres modos decididos por cuáles son `None`, más
`_warn_if_result_inputs_ignored` para avisar de los que se ignoran. Una vez
hecha la tarea 1.3, todo lo explicable es un `ExplainableResult` (perfil solo,
perfil más plan vía `CodeGenerationResult`, resultados). Propuesta: `ask(prompt,
context: ExplainableResult | ForecastingProfile | None = None, skills=None,
include_reference=False)`. El modo "pásame `data` y yo perfilo y planifico" se
mantiene como `ask(prompt, context=assistant.forecast_code(data, ...))`, que es
más explícito. Cambio de firma: requiere periodo de deprecación de `data`,
`profile`, `plan`, `result` y `steps`.

**Decisión (2026-09-10): implementada** con la variante revisada tras
la crítica: `ask(prompt, context=None, *, plan=None, skills=None,
include_reference=False, result=None)`. `context` acepta cualquier
`ExplainableResult`; `ForecastingProfile` implementa el protocolo (que se
movió a `schemas/explainable.py` para evitar el ciclo de imports), así que
un profile se explica solo, sin `steps` ni plan implícito. `plan` acompaña
a un profile y los dos se explican como el `CodeGenerationResult` que
`forecast_code()` produciría. Un `ForecastPlan` suelto lanza `TypeError`
con la indicación `context=profile, plan=plan`. `data`, `target`,
`date_column`, `series_id_column` y `steps` desaparecen (el CLI perfila y
planifica por su cuenta con `--data`, y gana `--from-profile` y
`--from-plan`). `result=` sigue como alias con `DeprecationWarning` hasta
0.4.0. Se eliminó `_warn_if_result_inputs_ignored`.

### 3.4 `refine_plan()` con parámetros explícitos en vez de `**overrides`

Las claves válidas se validan en tiempo de ejecución contra un conjunto fijo.
Parámetros keyword-only explícitos dan autocompletado y comprobación de tipos.
Compatible hacia atrás si se mantienen los mismos nombres; solo cambia la firma
en la documentación.

**Decisión (2026-09-10): implementada como `**overrides: Unpack[RefinePlanOverrides]`**,
no como parámetros explícitos. Pasar una clave a `None` tiene significado
(`interval=None` quita los intervalos, `lags=None` recalcula por PACF), así
que parámetros con default `None` habrían cambiado el comportamiento o
exigido un centinela. `RefinePlanOverrides` y `CandidateConfig` (para los
candidatos de `compare()`) viven en `schemas/plans.py` como `TypedDict`
opcionales; la validación en ejecución lee sus claves
(`REFINE_PLAN_OVERRIDE_KEYS`, `CANDIDATE_CONFIG_KEYS`), así que no pueden
divergir. `typing-extensions` pasa a dependencia explícita en Python < 3.12
(ya venía con pydantic). Sin cambio de comportamiento.

### 3.5 DataFrames serializables en los schemas

`predictions`, `metrics` y `results` están tipados como `Any`, así que
`model_dump(mode="json")` no funciona en resultados y el CLI (tarea 2.5) lleva
serializadores propios. Propuesta: un tipo `Annotated[pd.DataFrame,
PlainSerializer(...), PlainValidator(...)]` en `schemas/_types.py` que
serialice a `records` con el índice reseteado. Habilita `model_dump_json()` en
todos los resultados y es el prerrequisito para exponer el asistente como
herramientas de agente o servidor MCP más adelante.

**Decisión (2026-09-10): implementada.** `schemas/_types.py` define
`JSONFrame`, `OptionalJSONFrame` y `JSONTimeSeriesFold` con
`PlainSerializer(..., when_used="json")`: `model_dump()` en modo Python
sigue devolviendo los objetos vivos y solo el modo JSON convierte
(DataFrames a registros con el índice como columna, `TimeSeriesFold` a sus
parámetros). Sin validador de entrada: el round-trip desde JSON queda para
cuando haya un caso de uso y se puede añadir sin romper nada.
`ComparisonResult.best_name` es `computed_field`. El CLI sustituye sus
serializadores por `model_dump(mode="json")` (mismas claves; cambia el
orden y `ask` incluye `skills` y valores `null`).

### 3.6 `ask()` cuando el LLM falla

Hoy captura cualquier excepción, emite `UserWarning` y devuelve un `AskResult`
cuya explicación empieza por `[LLM unavailable]`. En un pipeline ese texto pasa
desapercibido. Opciones: lanzar siempre (más honesto para una librería), o un
parámetro `on_error: Literal["raise", "warn"] = "raise"` en el constructor.
Cambio de comportamiento; requiere entrada en releases y ajustar
`test_assistant_ask.py`.

**Decisión (2026-09-10): implementada, lanzando siempre.** Nueva
`LLMCallError` (con `llm` y `original_error`, encadenada con `from`), que
`ask()` lanza tanto cuando falla la llamada como cuando el chequeo previo
de Ollama no llega al servidor. Sin parámetro `on_error`: quien quiera
degradar lo hace con `try/except LLMCallError`. `refine_plan()` y
`create_cv()` no cambian, porque su salida determinista es válida por sí
misma; ese es el criterio: degradar solo cuando hay una salida válida. El
CLI captura la excepción y termina con exit 1.

## Fase 4: tests

Revisión de la suite tras las tres fases (2026-09-10). Huecos encontrados y
cerrados en la misma sesión:

### 4.1 Ejecución del script standalone

`run_forecast` ejecuta `imports + core`; el preámbulo de carga
(`pd.read_csv`, `exog_future.csv`, `set_index`) solo se comparaba como texto.
Nuevo `tests/test_integration_standalone_script.py`: escribe el CSV, guarda
`result.code`, lo ejecuta en un intérprete aparte (`subprocess` +
`runpy`) y compara las predicciones con las de `forecast()`/`backtest()`.
Siete casos: single con exógenas (evaluación), single sin exógenas
(predicción), single con `exog_future.csv` (predicción), multi largo, multi
ancho, statistical y `backtest_code()`.

Evaluación posterior (2026-09-10): se mantiene. Cuesta unos 10 s en total
(1,3 a 1,9 s por caso, casi todo arranque del intérprete con skforecast) y
es determinista (Ridge en los casos ML, Auto-ARIMA en el statistical). Dos
correcciones tras la evaluación: la aserción sobre la ruta del CSV compara
`repr(str(csv_path))` porque el script la embebe como literal Python y en
Windows `repr` duplica las barras; y el caso statistical pierde el marcador
`slow` (1,9 s). Sin caso para `ForecasterFoundation`: exige descargar
Chronos-2, como en el resto de la suite.

Destapó un bug: `backtest_code(data=ruta)` perfilaba el DataFrame ya cargado
y el script leía `data.csv` en lugar de la ruta dada (`forecast_code()` la
conservaba). Corregido en `_prepare_backtest` y anotado en releases.

### 4.2 Comando `backtest-code` del CLI

Cero tests y 94 líneas sin cubrir. Tres tests nuevos en `test_cli_pipe.py`
(`TestBacktestCode`): con `DATA`, con `--from-plan`, y `--output` más
`--format json`.

### 4.3 Golden de los contextos nuevos

`profile_only`, `code_generation_result` y `cv_strategy` añadidos a
`GOLDEN_SCENARIOS`; sin ellos un cambio en su bloque de contexto no se veía
en ningún diff.

### 4.4 Proveedor LLM

`ensure_ollama_reachable` (servidor arriba y abajo, con `urlopen`
parcheado), `build_ollama_settings` (proveedor cloud, tamaño de ventana,
aviso y recorte al exceder) y `create_model` con `api_key` más `base_url`.

### 4.5 Limpieza

`test_role_prompt_uses_plain_ascii_punctuation` eliminado (lo cubre
`test_source_conventions.py`). Cinco tests cuya única aserción era
`isinstance` o "no falla" ganan aserciones sobre el contenido.

### 4.6 Ramas restantes

Hechas el 2026-09-10: `_position_to_date` (fichero propio),
`build_plan_explanation` (manejo de NaN) y `_build_profile_explanation`
(fichero nuevo: familias multivariate, foundation y statistical, índice no
datetime, estimador de boosting, exógenas categóricas), y un fichero por
función para los helpers de `profiling/data_profile.py` (detección de columna
de fecha, parseo, límites del índice, extracción del índice, fecha de inicio,
exógenas categóricas, estadísticas, avisos, dtype del target, huecos,
frecuencia fijada, target constante, formato del corte, `TypeError` de
`resolve_end_train`, `start_date` con hora). Hallazgo: en
`generate_warnings` la rama `if n_cols == 0: n_cols = 1` es inalcanzable
(con los dos diccionarios vacíos no hay valores ausentes que contar); se
deja como está y se anota aquí. Lo mismo en `detect_target_dtype`: la rama
`is_bool_dtype` es inalcanzable porque pandas trata `bool` como numérico y
esa comprobación va antes; un target booleano se clasifica `numeric`. Si
se quiere `categorical`, hay que comprobar `bool` antes que `numeric`
(cambio de comportamiento; decidir aparte).

### 4.7 Avisos como errores

`filterwarnings = ["error", ...]` en `pyproject.toml`, con cuatro `ignore`
dirigidos y justificados (bucle de eventos de pydantic-graph, ajuste de bins
de skforecast dentro de los scripts ejecutados, convergencia de Auto-ARIMA,
`DataTransformationWarning` de skforecast en multi-series lineal). Lo que
destapó: pandas 2.3 con NumPy 2.5 emite `DeprecationWarning` al construir
`pd.Timedelta(days=1)` (un fixture y un test usaban esa forma; ahora
`pd.Timedelta(1, unit="D")`); `_resolve_start_date` usaba
`groupby().apply` sobre las columnas de agrupación (FutureWarning de
pandas; reescrito sobre el índice, sin cambio de comportamiento); cinco
tests de `ask()` provocaban `DataSentToLLMWarning` sin esperarlo (ahora
usan `send_data_to_llm=True`, que no es lo que prueban); un test de
`backtest()` llamaba a `cv.split` sin forecaster y otro perfilaba datos con
NaN sin esperar el `MissingValuesWarning` del PACF.

### 4.8 Importación sin el extra `[llm]`

`tests/test_import_without_llm_extra.py`: importa el paquete y construye un
`ForecastingAssistant` en un intérprete aparte y comprueba que `pydantic_ai`
no está en `sys.modules`. La garantía completa sería un job de CI que instale
sin extras y ejecute los tests no LLM; queda como opción.

### 4.9 Determinismo

`tests/test_integration_determinism.py`: dos asistentes independientes sobre
el mismo dato (single y multi largo) producen el mismo profile, plan, script,
predicciones y métricas; y `forecast_code()` devuelve exactamente el script
que `forecast()` ejecuta.

Fuera de la suite, sin hacer: ejecutar los notebooks de documentación en un
job periódico (`nbclient`) para detectar desviaciones entre docs y API;
requiere decidir qué hacer con las celdas que necesitan LLM.


## Fase 5: contexto del LLM

Herramienta: `tools/ask_context_check.py` ejecuta el flujo determinista sobre
`bike_sharing` o `items_sales`, pasa por `ask()` ocho tipos de contexto con
preguntas "grounded" y "probe", y escribe un informe con el contexto exacto,
las respuestas, una lista de comprobación y los campos de los objetos que el
contexto no envía. `--dry-run` no llama al LLM; `--extra-context` permite
probar hechos adicionales antes de tocar la librería. Los informes
intermedios de esta fase (contexto original, experimento con contexto
extra, contexto enriquecido) se borraron; quedan los finales en
`tools/ask_context_reports/`.

Resultado con `google:gemini-3.5-flash` (2026-09-10): el modelo respeta las
reglas (no inventa números, declina los probes, MASE contra el naive, no
re-rankea) y el límite estaba en el contexto: con el `<dataset>` original
(150 tokens) no podía decir si había valores ausentes ni matizar un MAPE de
108 % porque no sabía que el target tiene mínimo 1. Cambios en
`llm/context.py`:

- `<dataset>`: rango de fechas, estadísticas del target, exógenas
  categóricas, valores ausentes (también cuando son cero), irregularidades
  del índice y avisos del perfilado.
- `<profile_decision>`: lags PACF significativos (hasta 15) y features de
  ventana y calendario sugeridas, para explicar un profile sin plan.
- `<script>` nuevo para `CodeGenerationResult`: modo, ficheros leídos,
  variables definidas, paquetes importados, longitud. El script no se envía.
- `<comparison_overview>`: pide no sugerir causas del ranking (el modelo lo
  hacía con hedging).

Verificado con la tercera pasada sin `--extra-context`: valores ausentes
respondidos, estacionalidad diaria y semanal inferida de los lags con
cautela, MAPE matizado por el mínimo del target, ficheros del script
identificados, y ninguna especulación causal en la comparación. Los 11
golden se regeneraron. Queda sin hacer, anotado: métrica por fold en el
backtest (unos 300 tokens) para responder "cómo evolucionó el error".

Pasada multi-serie (`items_sales`, tres series en formato ancho,
`run4_multi`): el modelo trata bien las métricas por serie y la fila
`average`, y declina lo que no está. Destapó tres cosas de la librería:

- `_build_backtest_explanation` promediaba todas las filas de la tabla de
  métricas, incluidas `average`, `weighted_average` y `pooling`, y daba
  0.9612 donde la fila `average` dice 0.9617. Corregido: usa
  `aggregate_metrics` (la fila `average`) y lo etiqueta.
- `<dataset>` decía "Observations: 1097" y la explicación del profile
  "3291 observations": el primero es la longitud del índice y el segundo el
  total agrupado. Ahora ambos textos dicen "pooled across N series" donde
  corresponde.
- `compare()` con candidatos automáticos en multi-serie enfrenta
  `ForecasterRecursiveMultiSeries` (puntuado con la media de las series)
  con `ForecasterDirectMultiVariate` (puntuado solo sobre el primer target).
  El leaderboard mostraba 0.73 frente a 0.96 y "23.8 % ahead" sin avisar.
  Decisión del autor: no deben compararse (son técnicas distintas;
  `ForecasterDirectMultiVariate.level` es "la serie a predecir", una sola).
  `compare()` lanza `ValueError` si `candidates` mezcla familias, los
  candidatos automáticos se quedan en la familia del forecaster
  recomendado, y en multi-serie, donde eso deja un único forecaster, se
  comparan sus estimadores candidatos (`Forecaster+Estimator`).
- Segunda pasada multi-serie (`tools/ask_context_reports/0.3.0_items_sales.md`,
  Gemini 3.5 Flash, dataset `items_sales`): todas las respuestas quedan
  ancladas al contexto (MASE contra el baseline, sin causas del ranking,
  sin tendencia entre folds, RMSE y estacionalidad declarados como no
  disponibles). Huecos corregidos en `llm/context.py`: el resumen por
  columna de `<predictions>` omite `fold` (un identificador cuya media
  se citaba como dato) y añade un resumen de `pred` por serie (hasta
  `MAX_STATS_SERIES`), con el que el modelo ya responde "cuál es la
  previsión media de item_2" en lugar de "no disponible". Verificado con
  una llamada real. Pendiente y no implementado: métricas por fold.
- La evaluación pasa a ser una herramienta de pre-release:
  `tools/ask_context_check.py`, con un informe revisado por release y
  dataset en `tools/ask_context_reports/` (README con criterios de
  aceptación y registro). Los informes intermedios de esta sesión se han
  borrado; se conservan `0.3.0_items_sales.md` y `0.3.0_bike_sharing.md`,
  generados con el código final. Las instrucciones de `AGENTS.md` y
  `CLAUDE.md` piden pasarla cuando cambien `llm/context.py`,
  `llm/prompts.py` o las explicaciones renderizadas.

Punto 2 (métrica por fold) no implementado: exige un campo nuevo en
`BacktestResult` (`fold_metrics`) calculado en el runner, porque el
resultado no guarda los valores reales con los que comparar; se deja como
propuesta con ese diseño.


## Registro

Todo el trabajo se hizo en la rama `0.3.x` con el entorno conda
`skforecast_ai_py13`, y quedó sin commitear para revisión del autor.

| Fase | Fecha | Tests antes | Tests después | Ruff |
|---|---|---|---|---|
| 1 (bugs e inconsistencias) | 2026-09-09 | 1005 | 1020 | 37 preexistentes, ninguno nuevo |
| Revisión de la Fase 1 | 2026-09-10 | 1020 | 1021 | igual |
| 2 (adelgazar código) | 2026-09-10 | 1021 | 1037 | 0 |

| Tarea | Estado | Fecha |
|---|---|---|
| 1.1 | hecha, sin commit | 2026-09-09 |
| 1.2 | hecha, sin commit | 2026-09-09 |
| 1.3 | hecha, sin commit | 2026-09-09 |
| 1.4 | hecha, sin commit | 2026-09-09 |
| 1.5 | hecha, sin commit | 2026-09-09 |
| 1.6 | hecha, sin commit | 2026-09-09 |
| 1.7 | hecha, sin commit | 2026-09-09 |
| 1.8 | hecha, sin commit | 2026-09-09 |
| 1.9 | hecha, sin commit | 2026-09-10 |
| 1.10 | hecha, sin commit | 2026-09-10 |
| 1.11 | hecha, sin commit | 2026-09-10 |
| 2.1 | hecha, sin commit | 2026-09-10 |
| 2.2 | hecha, sin commit | 2026-09-10 |
| 2.3 | hecha, sin commit | 2026-09-10 |
| 2.4 | hecha, sin commit | 2026-09-10 |
| 2.5 | hecha, sin commit | 2026-09-10 |
| 2.6 | hecha, sin commit | 2026-09-10 |
| 2.7 | hecha, sin commit | 2026-09-10 |
| 3.1 | hecha, sin commit | 2026-09-10 |
| 3.2 | hecha, sin commit | 2026-09-10 |
| 3.3 | hecha, sin commit | 2026-09-10 |
| 3.4 | hecha, sin commit | 2026-09-10 |
| 3.5 | hecha, sin commit | 2026-09-10 |
| 3.6 | hecha, sin commit | 2026-09-10 |
| 4.1 a 4.9 | hechas, sin commit | 2026-09-10 |
| 5 (contexto LLM) | hecha, sin commit | 2026-09-10 |

### Notas de la Fase 1 (2026-09-09)

- La tarea 1.6 se extendió también a `tests/` (33 cabeceras de comentario y
  4 cadenas), y el test guardián cubre ambos directorios.
- La revisión posterior (2026-09-10) retiró el traspaso de `end_train` en
  `refine_plan()` (cambiaba el modo de ejecución del plan refinado),
  condicionó la herencia de marcas LLM a que el valor se conserve, dio
  default `True` al flag de `LLMContext` (renombrado `sends_result_values`)
  y corrigió el test guardián de guiones (encoding y exclusión de rutas).
  De las mejoras pequeñas propuestas se aplicaron las que no cambian salida
  visible; `skip_folds`/`allow_incomplete_fold` en `cv_config` se pospuso a
  la tarea 3.2.

### Notas de la Fase 2 (2026-09-10)

- 2.1: `_resolve_model` y los tres `_resolve_*_agent` se quedan en el
  asistente porque los tests los parchean (`monkeypatch.setattr(assistant,
  "_resolve_model", ...)` y `_cv_agent`). Se movieron las funciones con
  lógica: `llm/refinement.py` (`refine_features_with_llm`,
  `configure_cv_with_llm`), `llm/provider.py` (`build_ollama_settings`),
  `execution/comparison.py` (candidatos, agregación, tabla y explicación
  de `compare()`). `assistant.py` pasa de 2.961 a 2.381 líneas; lo que
  queda es en su mayoría docstrings. El paquete sigue importando sin cargar
  `pydantic_ai`.
- 2.2: `_prepare_forecast` espeja a `_prepare_backtest`. `forecast_code`
  sigue pasando el `data` original a `profile()` (una ruta CSV se conserva
  en el script generado) y `forecast` pasa el DataFrame, como antes.
- 2.3: `test_shared_parameter_docstrings_are_identical` fija los 16 grupos
  de parámetros cuyas descripciones son idénticas hoy.
- 2.4: se extrajeron solo los bloques idénticos entre forecast y backtesting
  (`_emit_loading_and_index`, `_emit_feature_setup`, `_emit_pivot_to_wide`,
  `_emit_reshape_series_long_to_dict`, `_emit_reshape_exog_long_to_dict`).
  Los bloques de exógenas y de split difieren entre los dos y se dejaron.
  `backtesting.py` baja de 626 a 539 líneas, no a menos de 300 como decía
  el criterio: ese objetivo requeriría unificar los bloques que difieren, y
  el riesgo no compensa. Los scripts generados son idénticos byte a byte
  (tests de rendering).
- 2.5: 24 alias `Annotated` para las opciones con declaración idéntica; la
  ayuda de los 10 comandos se comparó con `CliRunner` antes y después y es
  idéntica. Los serializadores de forecast y backtest se unificaron en
  `_single_run_result_to_dict` dentro del CLI, sin añadir API pública (la
  serialización nativa queda para 3.5). `cli.py` gana 14 líneas por el
  bloque de alias, aunque cada opción se define una sola vez.
- 2.6: `run_agent_sync` vive en `llm/runtime.py` y `count_cv_folds` en
  `recommendation/backtesting.py`; `_utils.py` ya no importa `asyncio`
  (715 a 522 líneas). Los tests se movieron con el código
  (`tests_llm/test_run_agent_sync.py`).
- 2.7: ruff a cero (66 renombrados de `l`, 8 auto-fix) y job `lint` nuevo
  en `unit-tests.yml`.

### Ficheros nuevos

`skforecast_ai/execution/_exec.py`, `skforecast_ai/execution/comparison.py`,
`skforecast_ai/llm/refinement.py`, `skforecast_ai/llm/runtime.py`,
`tests/test_source_conventions.py`, `tests/tests_llm/test_run_agent_sync.py`,
`tests/tests_recommendation/test_resolve_cv_config.py`.
