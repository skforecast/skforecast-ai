# Roadmap de skforecast-ai

## Cómo se usa

- **Una fila por elemento**, con un ID estable. Aquí va lo necesario para
  priorizar y empezar; el detalle largo vive en el documento que enlaza la
  columna "Detalle" (un plan de `dev/` o un documento del historial, ver
  las abreviaturas).
- **Sin versión objetivo**: cada versión sale con lo que esté hecho al
  publicarla. Lo que sí depende de una publicación está en la sección 1,
  con su momento en lugar de prioridad.
- **Prioridad**, la misma escala que el roadmap de skforecast:
  - `P1`: resultados erróneos sin aviso en un uso habitual, y regresiones
    frente a la última versión publicada (bloquean la publicación).
  - `P2`: errores visibles en usos plausibles, resultados erróneos en
    configuraciones poco habituales y textos incorrectos que el usuario o
    el agente siguen.
  - `P3`: funcionalidades nuevas, mejoras y mantenimiento.
  - `P4`: solo si aparece demanda.

  Lo bloqueado por algo externo conserva su nivel y lo dice en "Estado".
  Dentro de cada tabla, las filas van por nivel y, dentro del nivel, en el
  orden en que conviene hacerlas.
- **Al terminar un elemento**, su fila pasa a la sección 2 con el número de
  la PR. Al publicar una versión, la sección 2 se vacía: lo publicado queda
  en `docs/releases/releases.md`.
- **Un documento de `dev/` existe solo mientras tenga alguna fila abierta
  aquí.** La PR que cierra la última fila lo borra, y después se cita por
  commit.
- Las líneas de código citadas en los documentos de detalle son de su
  fecha: buscar por nombre de clase o función.
- Esfuerzo: XS (menos de una hora), S (horas a 1 día, con tests y docs), M
  (2 a 5 días), L (más de una semana).
- Lo que se resuelve mejor en skforecast se arregla allí, con su ID en el
  roadmap de skforecast, en vez de rodearlo aquí (sección 7).

### Abreviaturas de la columna "Detalle"

| Abreviatura | Documento |
|:--|:--|
| R05 | `056692b:dev/roadmap-0.5.0.md`: plan de la 0.5.0, con las decisiones D01 a D40 |
| AUD | `056692b:dev/mcp-blackbox-audit.md`: auditoría de caja negra del servidor MCP (hallazgos `Vnn` y `Gnn`) |
| R06 "X" | `82a3b99:dev/roadmap-0.6.0.md`, sección "X": el roadmap anterior a esta reorganización, con el análisis de pandas 3, la tabla de TDQS de Glama y el texto completo de cada candidato |

Se leen con `git show <commit>:<ruta>`. Las referencias `Hn` son las del
check con agentes de la 0.4.0.

## 1. Ligado a una publicación

skforecast 0.28.0 y skforecast-ai 0.6.0 salen el mismo día (D41). La fecha
la pone skforecast. Hasta entonces, `skforecast>=0.28.0` no se resuelve
desde PyPI: en local se instala antes skforecast desde git
(`pip install "skforecast @ git+https://github.com/skforecast/skforecast@0.28.x"`),
y el hook de inicio de las sesiones en la nube lo hace solo
(`skforecast_dev_branch` en `.claude/hooks/session_start.py`).

| ID | Qué | Cuándo | Esfuerzo | Estado | Detalle |
|:--|:--|:--|:-:|:--|:--|
| REL-anthropic-directory | La ficha del directorio de plugins de Anthropic rechazó la 0.5.0 por dos bloqueos: solo admite servidores MCP locales de organizaciones verificadas, y una versión de PyPI no cuenta como fijación (pide un wheel en el plugin, git con el commit completo o un `uv.lock` con `uv run --locked`). Sigue en la 0.4.2, que se rompe el día que salga skforecast 0.28 (D41). Opciones: (A) pedir la verificación y fijar con el `uv.lock`; (B) dejarla en la 0.4.2; (C) quitar el servidor del plugin del directorio (no recomendado) | Ya: la A tarda lo que tarde Anthropic | S | Decisión pendiente (Joaquín) | R06 "Lo que queda de la 0.5.0", punto 2 |
| REL-sync-028 | Sincronizar `skills/` y `llms-base.txt` desde `0.28.x`: cambian 10 ficheros de 8 skills y `llms-base.txt`, sin skills nuevos ni borrados (`troubleshooting-common-errors` gana secciones de pandas 3). Otra vez con la `0.28.x` final | Ahora, y con la `0.28.x` final | S | Pendiente: lo lanza Joaquín con `/sync-skforecast-assets`. Texto que lee el LLM: `/llm-context-change` | |
| REL-paid-check | Una sola pasada de `tools/ai/check_ask_context.py` con todos los cambios de texto de la release: REL-sync-028 y las filas de la sección 4 que estén listas. Renueva las 6 respuestas guardadas que citan "(last training value)" (`backtest_code`, `plan`, `cv_defaults`). Falta un escenario: si `ask(context=profile, plan=plan)` explica el script sin la codificación ni el formato de fecha de las exógenas (pregunta 4 de #97) | Con la `0.28.x` congelada | S | Pendiente: la lanza Joaquín | R06 "Checks de la release" |
| REL-notebooks | Volver a ejecutar `agentic-forecasting` y `agentic-forecasting-step-by-step`, que guardan "(last training value)". Desde una sesión de Claude Code, con `PYDANTIC_AI_NO_BANNER=1` | Después de REL-paid-check | S | Pendiente | |
| REL-final-028-review | Repetir la revisión de compatibilidad sobre la `0.28.x` final: la suite con pandas 2.3.3 y 3.1.1 | Con el código final de skforecast 0.28.0 | S | La última, el 2026-11-24 sobre `d42a411` | R06 "Compatibilidad con skforecast 0.28" |
| REL-publish-060 | Publicar: `skforecast-ai` y `skforecast-ai-mcp` 0.6.0 en PyPI, la ficha del registro de MCP, el comando del plugin (`uvx skforecast-ai-mcp==0.6.0`) en nuestro marketplace, y Deploy y Make Release en Glama. El PR de la release a `main`, con merge commit (la 0.5.0 entró con squash y hubo que mergear `main` de vuelta). Al mergear, el README choca en las filas del badge de Glama: quedarse con las de `0.6.x` | El día que salga skforecast 0.28.0 | S | | R06 "Lo que queda de la 0.5.0", punto 1 |
| REL-notify-skforecast-py311 | Avisar a skforecast de que la 0.6.0 pide Python 3.11 (#151), para cerrar su `REL-skforecast-ai-python311` y actualizar `docs/skforecast-ai/skforecast-ai.md` | Al publicar | XS | Pendiente | |

## 2. Hecho desde la última versión publicada (0.5.0)

| Qué | PR |
|:--|:--|
| Rama `0.6.x` y versión 0.6.0; `typer<0.29` en el extra `docs` para que `mkdocs-typer2` 0.4.1 construya la documentación | [#149](https://github.com/skforecast/skforecast-ai/pull/149), [#150](https://github.com/skforecast/skforecast-ai/pull/150) |
| Mínimos de skforecast 0.28 (`skforecast>=0.28.0`, `numpy>=2.0`, `pandas>=2.3`, `scipy>=1.13`, `statsmodels>=0.14.6,<0.16`) y Python 3.11 | [#151](https://github.com/skforecast/skforecast-ai/pull/151) |
| Badge de Glama en el README | [#153](https://github.com/skforecast/skforecast-ai/pull/153) |
| pandas 3: la suite en verde con pandas 2.3.3 y 3.1.1, y los dos en la matriz de CI. De paso, las fechas a predecir tras un cambio de hora y las exógenas de texto de dtype `string` en memoria | [#152](https://github.com/skforecast/skforecast-ai/pull/152) |
| La CLI quita el banner de pydantic-ai en `ask`, `check-llm --test-call`, `refine-plan --prompt` y `backtest --prompt` | [#155](https://github.com/skforecast/skforecast-ai/pull/155) |
| El SKILL.md y las instrucciones del servidor dicen que el resumen de un `backtest` da las 5 primeras series | [#156](https://github.com/skforecast/skforecast-ai/pull/156) |
| D42: el `astype(str)` de las fechas de enteros se queda en la lectura del CSV | Directo en `0.6.x` (`f4f0149`) |

## 3. Funcionalidades

| ID | Qué | Prioridad | Requiere | Esfuerzo | Estado | Detalle |
|:--|:--|:-:|:--|:-:|:--|:--|
| FEAT-error-by-horizon | El error por paso del horizonte en `BacktestResult` y en su resumen, con la columna `step` que skforecast da desde la 0.27. Hoy el contexto del LLM solo dice "Steps of the horizon: 1 to N" | P3 | | S a M | No empezado. Cambia lo que lee el LLM: si entra antes de REL-paid-check, va en esa pasada | |
| FEAT-hpo | Un paso acotado de búsqueda de hiperparámetros con las funciones de skforecast, con su coste en `CostNotice` como los backtests. Hoy `compare()` solo ordena configuraciones fijas. Las búsquedas de un paso adelante dependen de arreglos de skforecast 0.27 que aún no se ejercen aquí (series que acaban o empiezan tarde, skforecast#1430; un candidato que no puede evaluar nada se salta). Si se admite una métrica en la que mayor es mejor, el ranking (hoy siempre ascendente) sigue su dirección, como skforecast desde #1431 | P3 | | L | Desbloqueado desde skforecast 0.27; la 0.28 acelera las búsquedas en paralelo (skforecast#1503) | R06 "Ajuste de hiperparámetros" |
| FEAT-ms-out-of-sample-residuals | Intervalos multiserie con residuos fuera de muestra (`set_out_sample_residuals`). Hoy usan residuos dentro de muestra y la cobertura real queda muy por debajo de la nominal (lo mide y avisa 2c-ii). Hace falta un tramo de validación: cambia el coste del backtest y los scripts | P3 | | M | Lo que D11 dejó fuera de la 0.5.0 | R05 (D11) |
| FEAT-parquet-excel | Leer Parquet y Excel por ruta en la CLI y el servidor MCP; la API ya los admite como DataFrame. Toca el script (`pd.read_parquet`, `pd.read_excel`), la lectura de la librería, `resolve_csv_path` del servidor, sus textos y el SKILL.md. Decisiones: extras (no en el lanzador), hoja de Excel y fechas como número de serie, seguridad del `.xlsx` (`/security-review`), URLs | P3 | | L | Alcance comprobado el 2026-10-11 sobre `0.4.x`: revisarlo | R06 "Leer Parquet y Excel por ruta" |
| FEAT-custom-business-day | Días de cierre fijos con `CustomBusinessDay` y `weekmask`: unos datos diarios sin domingos no tendrían huecos. skforecast ya ajusta, predice y hace backtest con ese índice; el `freqstr` `'C'` pierde la `weekmask`, así que el script tiene que emitir el offset y el perfil guardarla. Revisar todo lo que lee la frecuencia como texto | P3 | | M | Comprobado el 2026-10-16 con skforecast 0.26 | R06 "Días de cierre con `CustomBusinessDay` y `weekmask`" |
| FEAT-classifier | Un objetivo categórico con `ForecasterRecursiveClassifier` y métricas de clasificación. Hoy el plan lleva un paso `encode_target` que bloquea (no es silencioso, como dice el issue). Es un tipo de tarea nuevo en el perfil, el plan, las métricas, los scripts, el baseline y el MCP | P3 | | L | Pendiente de contestar [#14](https://github.com/skforecast/skforecast-ai/issues/14) (julio de 2026; el PR que anunció su autor no llegó) | |
| FEAT-exog-range-warning | Avisar cuando las exógenas futuras caen fuera del rango de entrenamiento (los árboles no extrapolan), con `RangeDriftDetector` de skforecast | P3 | | S a M | Sin comprobar si su API encaja | |
| FEAT-holidays | Festivos en las variables de calendario, que ya usan `CalendarFeatures` (`recommendation/calendar.py`). El país no sale de los datos: hace falta una opción | P3 | `FE-06` de skforecast | S | Bloqueado: hasta que skforecast lo publique | |

## 4. Capa LLM y textos

Cada fila cambia lo que lee el LLM: goldens con `/llm-context-change` y
check de pago. Conviene agruparlas en REL-paid-check.

| ID | Qué | Prioridad | Requiere | Esfuerzo | Estado | Detalle |
|:--|:--|:-:|:--|:-:|:--|:--|
| LLM-test-dates-phrases | El paso de `plan` ("a backtest leaves those dates out of its metrics") y el aviso de `create_cv` ("Impute the target to backtest every fold") salen siempre que faltan valores, también cuando ninguna fecha de test falta. En `0.5.0-final-haiku`, 3 de 9 respuestas lo cuentan como algo que pasó. O las frases se escriben como condición, o lo dice el resumen de `backtest`, que ya cuenta las fechas que quedan fuera. "Impute..." sobra con un estimador que acepta valores que faltan | P3 | | S | Aceptado para la 0.5.0 (2026-11-11) | R06 "Las frases sobre las fechas de test sin valor" |
| LLM-baseline-period | El resumen de `compare` llama al baseline "seasonal naive" sin su periodo (24 en horarios, 12 en mensuales): la frase de `select_baseline_config` no llega. En el check con agentes de la 0.5.0, cuatro sesiones lo dedujeron bien solas | P3 | | XS a S | No empezado | R06 "El periodo del baseline en el resumen de `compare`" |

## 5. Servidor MCP y distribución

| ID | Qué | Prioridad | Requiere | Esfuerzo | Estado | Detalle |
|:--|:--|:-:|:--|:-:|:--|:--|
| MCP-output-schema-size | Las descripciones de los esquemas de salida ocupan unos 30.800 caracteres, más que todo lo demás junto, porque el docstring de `ToolResult` se repite en nueve herramientas (#126, D34). Primero medir si Claude Code y los demás clientes pasan el `outputSchema` al modelo: si no, no cuesta nada | P3 | | S | No empezado | R06 "Las descripciones de los esquemas de salida del MCP" |
| DIST-manual-checks | Comprobaciones a mano sin hacer: Cursor y Codex (formato de su configuración, timeouts de arranque, `${workspaceFolder}`); en Claude Code, los comandos `/plugin` en una sesión interactiva y el plugin en Cowork y Windows; el timeout real de un cliente y los objetos huérfanos; instalar desde la galería de VS Code y llamar a `profile` | P3 | | S | Cursor y Codex no están instalados en la máquina | R06 "Lo que queda de la 0.5.0", punto 4 |
| MCP-tool-descriptions | Lo más bajo del TDQS de Glama: `describe_object` no dice cuándo usarla en vez de `get_code` o `get_failure`, ni qué pasa si la respuesta que creó el objeto ya no está; `plan` no dice si llamarla dos veces da dos planes | P4 | | XS | Las 11 herramientas en A (2026-11-11) | R06 "Lo que queda de la 0.5.0", punto 3 |
| DIST-directories | awesome-mcp-servers ([punkpeye/awesome-mcp-servers#16493](https://github.com/punkpeye/awesome-mcp-servers/pull/16493)) a la espera del bot `glama-check` y de la fusión; cursor.directory, después de DIST-manual-checks; que la ficha de mcprush.com siga la versión publicada | P4 | | XS | Abierto el 2026-11-11 | |

## 6. Ejecución, scripts y fechas

| ID | Qué | Prioridad | Requiere | Esfuerzo | Estado | Detalle |
|:--|:--|:-:|:--|:-:|:--|:--|
| BUG-forecast-test-missing | `forecast()` con `test_size` rechaza las fechas de test sin valor, que `backtest()` deja fuera de las métricas desde D38. Alinearlo es escribir en el script la máscara de las fechas con valor (y `n_evaluated`), lo que cambia todos los scripts de evaluación. Con varias series, `validate_evaluation_partition` tiene la misma regla | P2 | | M | No empezado | R06 "Los valores que faltan en el tramo de test de `forecast()`" |
| BUG-text-dates-spaces | Dos divergencias entre `forecast()` y el script ejecutado como fichero, con espacios alrededor de fechas leídas como texto: con separador de miles, la fecha se lee con `dtype={'date': str}` y conserva los espacios; con datos fechados por el índice y un CSV de exógenas futuras con `" 20200501 "`, `read_csv(..., index_col=..., date_format=...)` no las lee como fechas | P3 | | S | Ya estaban con pandas 2.3 y 3.1 | R06 "Lo que queda de pandas 3" |
| MAINT-quarterly-text-dates | Las fechas trimestrales de texto (`'2005Q1'`) avisan con `Pandas4Warning` desde `parse_text_dates` en `profile()` y `forecast()` (una versión futura dejará de leerlas). El arreglo cambia el script (`pd.Period('2005Q1').to_timestamp()` o un `PeriodIndex`). Sin comprobar si el script también avisa | P3 | | S | Los floats con `date_format` avisan igual: límite aceptado | R06 "Lo que queda de pandas 3" |
| BUG-utc-midnight-dst-remedy | El error de los datos diarios anclados a medianoche UTC cuyo horizonte cruza un cambio de hora (límite aceptado) propone "Drop the rows before ..." con la primera fila del propio `exog`, que no se puede seguir. Un mensaje correcto pide detectar ese caso | P3 | | S | | R06 "Lo que queda de pandas 3" |

## 7. Dependencias de skforecast

| Qué | En skforecast | Estado | Efecto aquí |
|:--|:--|:--|:--|
| `RollingFeatures`: `transform_batch` (entrenamiento) da NaN en toda ventana con un valor que falta y `transform` (predicción) lo salta, sin leer `min_periods` | `BUG-rollingfeatures-nan` (P2) | Sin empezar | Con huecos y un estimador que no acepta NaN, el forecast de Ridge del check con agentes de la 0.5.0 entrenó con 15 de 84 filas; con uno que los acepta, predice con un estadístico que nunca vio |
| Los forecasters de ML deciden si las fechas avanzan en hora local o en pasos de UTC (`_is_utc_anchored_index`) con `last_window.index`, solo las filas de la ventana | Sin ID (otro caso del mismo helper que `BUG-utc-midnight-anchored-freq`) | Borrador del issue escrito el 2026-11-27; lo abre Joaquín | `_forecast_dates` reconstruye las fechas desde la primera de los datos, y difieren con datos a una hora local que solo es medianoche UTC parte del año (diarios a las 20:00 de Nueva York) y un horizonte que cruza un cambio de hora. Con pandas 3.1.1 ningún `exog` pasa las dos comprobaciones; con pandas 2.3 el forecast fecha las predicciones a las 19:00 tras el cambio |
| `_pandas_compat.infer_freq` pone `future.infer_freq_returns_offset` con `pd.option_context`, global para todos los hilos | Sin ID | Borrador del issue escrito el 2026-11-27; lo abre Joaquín | `infer_freq_name` usa el mismo patrón y el servidor MCP ejecuta las herramientas en hilos: con dos hilos entrelazados, uno recibe el `Pandas4Warning` y la opción puede quedar en `True` para todo el proceso. Reproducido con el entrelazado en un solo hilo. Un lock aquí no cubre las llamadas de skforecast |

## 8. Herramientas de mantenimiento y checks con agentes

| ID | Qué | Prioridad | Requiere | Esfuerzo | Estado | Detalle |
|:--|:--|:-:|:--|:-:|:--|:--|
| CHECK-missing-month-in-folds | Un fichero con un mes ausente dentro de los folds de test, para medir D38 en el check con agentes: en `h2o_dirty` los tres meses caen antes del primer fold, y ninguna sesión lo ejercita | P3 | | S | No empezado | R06 "Checks de la release" |
| CHECK-dirty-data-denied | En `dirty_data` y `dirty_data_keep_gaps` el cliente deniega el comando de shell que escribe la copia acordada (10 de 12 sesiones con sonnet, 3 de 12 con haiku): sin cambiarlo, esos escenarios no concluyen | P3 | | S | Visto en `0.5.0-final` | R06 "Checks de la release" |
| TOOL-check-mcp-agent-tests | Tests unitarios de `tools/mcp/check_mcp_agent.py`: no tiene, y casi todos los defectos de sus dos revisiones estaban en sus heurísticas (redirecciones, fallos falsos, herramientas que se escapaban) | P3 | | M | No empezado | |
| TOOL-bash-guard-worktree | El guard de Bash (`.claude/hooks/pre_bash_guard.py`) resuelve la rama desde `CLAUDE_PROJECT_DIR` antes que desde el `cwd` de la llamada: en un worktree comprueba la rama del checkout principal | P3 | | S | | |
| TOOL-h11-false-warn | El `WARN` de H11 avisa en falso cuando el plan se reconstruye igual con un intervalo. Leer el `UnmeasuredPlanNotice` de la respuesta de `forecast` en vez de comparar ids, que quita también el falso aviso del ganador de `compare` | P4 | | S | Anotado en el README del check | |
| TOOL-check-builtin-skills | Una sesión del check puede cargar los skills de fábrica de Claude Code con `Skill` | P4 | | XS | | |
| AUD-leftovers | Restos de la auditoría sin script, por confirmar: `00:00:00` en `HoldoutEvaluationNotice`, MASE NaN con "Mean of empty slice", DMV con `refit: true` | P4 | | S | Sin confirmar | AUD |

## 9. Decisiones

Siguen la numeración de R05 (D01 a D40). La siguiente es D43. Abiertas:
REL-anthropic-directory.

- **D41 (2026-11-25): sin 0.5.1; skforecast 0.28.0 y skforecast-ai 0.6.0
  salen a la vez**, y la 0.6.0 pide los mínimos de skforecast 0.28 desde el
  primer día. Así, `pip install skforecast-ai` y `uvx skforecast-ai-mcp`
  sin versión reciben una versión que funciona con pandas 3. Aceptado: la
  0.4.2 y la 0.5.0 piden `pandas>=2.2` y skforecast sin cota superior, así
  que se rompen con pandas 3. Afecta a las instalaciones nuevas con la
  versión fijada (`uvx skforecast-ai-mcp==0.5.0`, y la `==0.4.2` de la
  ficha de Anthropic mientras siga ahí, ver REL-anthropic-directory) y a
  los entornos con la 0.5.0 que actualizan solo skforecast. Una 0.5.1 con
  `pandas<3` queda como reserva si aparecen usuarios afectados; no
  arreglaría la ficha de Anthropic.
- **D42 (2026-11-27): el `astype(str)` de las fechas de enteros se queda
  en la lectura del CSV.** El script pasa las fechas a texto al leer el CSV
  (`_emit_data_loading`) y la ejecución convierte los datos en memoria
  (`compact_dates_as_text` en `run_forecast`, `run_backtest` y
  `exog_as_injected`), como `series_ids_as_text` con los ids: la ejecución
  recibe lo que daría el preámbulo. La alternativa, un `.astype(str)`
  dentro del `pd.to_datetime(..., format='%Y%m%d')` del código común,
  falla en 15 de 22 escenarios con CSV reales: la ejecución inyecta las
  fechas ya leídas por `load_data` y `load_exog`, el `astype(str)` las
  vuelve `'2020-01-01'` y el formato no casa. Además perdía el mensaje de
  c48630f (`_exog_dates` leería los enteros como nanosegundos).

## 10. Aparcado y descartado

| Qué | Por qué | Detalle |
|:--|:--|:--|
| Referencias de los skills a demanda: `ask()` leería con una herramienta una sección de `references/` | Aparcado hasta que un check con un modelo real muestre respuestas a las que les falten esos detalles. En contra: ayuda poco a los modelos alojados, Ollama es donde peor van las herramientas, lo que ve el modelo deja de ser reproducible y puede no leer la sección que importa | R06 "Referencias de los skills a demanda" (D39, D40) |
| Renombrar las herramientas del MCP para que sigan un mismo patrón (Glama puntúa los nombres con 3) | Descartado: rompe la API | R06 "Lo que queda de la 0.5.0", punto 3 |
| Una 0.5.1 con `pandas<3` | Reserva, ver D41 | |
| `ForecasterRnn`, `select_features` y guardar el modelo entrenado | Aparcado: sin demanda, y poco valor para un asistente determinista frente a su coste | |
