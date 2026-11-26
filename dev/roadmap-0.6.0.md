# Plan: lo que va a la 0.6.0

## Contexto

La 0.5.0, la release de robustez, se cerró el 2026-11-11 sobre skforecast
0.27.0. Su plan, el informe de la auditoría de caja negra del servidor MCP
(sus 33 hallazgos, arreglados con su test) y los dos planes del servidor
(visibilidad en directorios y descripciones de las herramientas) salieron
de `dev/` al abrir este fichero; siguen en el historial:

```bash
git show 056692b:dev/roadmap-0.5.0.md
git show 056692b:dev/mcp-blackbox-audit.md
git show 056692b:dev/mcp-discoverability-plan.md
git show 056692b:dev/mcp-tool-descriptions-plan.md
```

Las decisiones siguen la numeración de la 0.5.0: las `Dnn` hasta D40 que
se citan aquí son las de su plan, y la siguiente es D41. Las referencias
`Vnn` y `Gnn` son las de la auditoría; las `Hn`, las del check con agentes
de la 0.4.0.

Lo que se resuelve mejor en skforecast se arregla allí, con un issue, en vez
de rodearlo aquí (sección "Dependencia de skforecast").

## Lo que queda de la 0.5.0

1. **Publicar**: hecho el 2026-11-11. La primera pasada de CI contra
   `main` (#147) falló en los 15 jobs de tests: los tests de la rama no
   corren en CI hasta el PR a `main`. Lo arregló
   [#148](https://github.com/skforecast/skforecast-ai/pull/148): la CLI
   escribía los scripts en la codificación del sistema (cp1252 en
   Windows) y el resto eran tests que dependían de la plataforma o de una
   versión (python-dateutil 3.0 con pandas 2.3, scikit-learn 1.7, Python
   3.14). Ensayo en TestPyPI (`0.5.0.dev20261111192811`) y release
   `v0.5.0` sobre `34da4d9`, los dos con todos sus jobs en verde;
   `skforecast-ai` y `skforecast-ai-mcp` 0.5.0 en PyPI, la ficha 0.5.0 del
   registro de MCP como `isLatest`, y el comando del plugin
   (`uvx skforecast-ai-mcp==0.5.0 --allow-project-dir`) arranca desde PyPI
   con skforecast 0.27.0. #147 entró en `main` con squash (`0b471b6`);
   `main` se mergeó de vuelta en `0.5.x` (`90c9c6a`, sin cambiar ningún
   fichero) para que `0.6.x` tenga una base común con `main`. La próxima
   vez, el PR de la release a `main` con merge commit.
2. **El directorio de plugins de Anthropic rechazó la 0.5.0**
   (`0b471b6`, 2026-11-11), por dos motivos de su política que no
   existían cuando aceptó la 0.4.x; el plugin solo cambió las dos
   versiones. Mientras tanto, la ficha sigue sirviendo la 0.4.2; quien
   instala desde nuestro marketplace, el registro de MCP o PyPI tiene la
   0.5.0.
   - **Bloqueo: servidores MCP locales solo de organizaciones
     verificadas** ("Verified" quiere decir que Anthropic sabe que la
     organización es una empresa real). `skforecast` no lo es. No se
     arregla con código.
   - **Bloqueo: una versión de PyPI no cuenta como fijación.** Pide un
     wheel dentro del plugin
     (`uvx --from ${CLAUDE_PLUGIN_ROOT}/vendor/<wheel> <nombre>`), una
     fuente git con el commit completo de 40 caracteres, o un proyecto uv
     en el plugin con su `uv.lock` versionado, arrancado con
     `uv run --locked`. Se arregla cambiando solo `plugin/`, sin otra
     release en PyPI; el `uv.lock` fijaría además todas las dependencias
     con su hash.
   - Avisos que no bloquean: una credencial de la máquina del usuario (la
     confirma un revisor si no se manda a ningún sitio), 3 campos de
     `plugin.json` sin reconocer (probablemente `displayName`,
     `documentationUrl` y `supportUrl`), y que el servidor es local.
   - Opciones, por decidir con Joaquín: (A) pedir la verificación de la
     organización y, si la dan, arreglar la fijación con el `uv.lock`;
     (B) dejar la ficha en la 0.4.2 y distribuir por los demás canales,
     con la ficha anclada en una versión con fallos conocidos; (C)
     quitar el servidor del plugin del directorio, que deja un skill sin
     servidor (no recomendado).
3. **Tras publicar**:
   - Glama: Deploy y Make Release hechos el 2026-11-12. Glama no aceptó
     `0.5.0` como versión y publicó la release como `0.1.1` (su
     numeración, no la del paquete; la imagen toma la última de PyPI).
   - TDQS recalculado por Glama el 2026-11-11 (23:43 UTC) sobre las
     descripciones de la 0.5.0: se cumplen los tres criterios del plan de
     descripciones ("cuándo usarla" en 3 o más, ninguna por debajo de B,
     concisión en 4 o más). Las 11 en A; media 4.2 (antes 3.5), mínima
     3.6 (antes 2.9). Sacado de los datos incrustados en
     `/tools/<nombre>` de la ficha; entre paréntesis, la 0.4.2 del
     2026-10-15 (`git show 056692b:dev/mcp-tool-descriptions-plan.md`):

     | Herramienta | Nota | TDQS | Propósito | Cuándo usarla | Parámetros | Comportamiento | Concisión | Completitud |
     |:--|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
     | `plan` | A (A) | 4.5 (3.6) | 5 | 5 (2) | 5 | 3 | 5 | 4 |
     | `forecast` | A (A) | 4.5 (3.7) | 5 | 5 (3) | 3 | 4 | 5 | 5 |
     | `get_failure` | A (B) | 4.5 (3.2) | 5 | 5 (2) | 3 | 4 | 5 | 5 |
     | `compare` | A (A) | 4.4 (4.0) | 5 | 5 (3) | 3 | 4 | 5 | 4 |
     | `refine_plan` | A (A) | 4.4 (3.8) | 5 | 5 (3) | 3 | 4 | 5 | 4 |
     | `profile` | A (A) | 4.2 (3.7) | 5 | 4 (3) | 3 | 4 | 5 | 4 |
     | `create_cv` | A (B) | 4.2 (3.2) | 5 | 4 (2) | 3 | 4 | 5 | 4 |
     | `backtest` | A (A) | 4.1 (3.5) | 5 | 4 (3) | 3 | 4 | 4 | 4 |
     | `list_objects` | A (C) | 4.1 (2.9) | 4 | 4 (2) | 3 | 5 | 5 | 4 |
     | `get_code` | A (A) | 3.9 (3.5) | 4 | 4 (3) | 3 | 3 | 5 | 5 |
     | `describe_object` | A (B) | 3.6 (3.2) | 4 | 3 (2) | 4 | 3 | 4 | 4 |

     Del conjunto (nuevo en la ficha): coherencia A, 4; nombres 3 (mezcla
     sustantivos, `plan`, con verbo y sustantivo, `get_code`; renombrar
     rompe la API, no compensa); completitud 4 (no hay forma de borrar
     objetos ni de cancelar `compare` desde una herramienta). Lo más bajo
     que queda, por si se toca: `describe_object` no dice cuándo usarla en
     vez de `get_code` o `get_failure`, ni qué pasa si la respuesta que
     creó el objeto ya no está; `plan` no dice si llamarla dos veces da
     dos planes.
4. **Comprobaciones a mano sin hacer** (las hechas, el 2026-10-31, están
   en el plan de la 0.5.0):
   - Cursor y Codex, que no están instalados en la máquina: el formato de
     `~/.codex/config.toml` y de `codex mcp add`, sus timeouts de arranque y
     si Cursor interpola `${workspaceFolder}`.
   - Claude Code: los comandos `/plugin` tecleados en una sesión
     interactiva, y el plugin en Cowork y en Windows.
   - El timeout real de un cliente y los objetos huérfanos (piden un
     cliente que corte).
   - VS Code: instalar desde la galería con el botón del README y llamar a
     `profile` (el comando que escribe solo está leído en su código).
5. **Directorios**: el PR de awesome-mcp-servers
   ([punkpeye/awesome-mcp-servers#16493](https://github.com/punkpeye/awesome-mcp-servers/pull/16493))
   sigue abierto el 2026-11-11, a la espera del bot `glama-check` y de la
   fusión. cursor.directory, opcional, después de probar Cursor. Mirar que
   la ficha de mcprush.com siga la versión publicada.

## Compatibilidad con skforecast 0.28

skforecast tiene la rama `0.28.x` como candidata (en desarrollo, sin fecha).
Revisada el 2026-11-24 sobre su commit `d42a411`: la suite de skforecast-ai
de `0.5.x` (`3fc58f2`, 7.107 tests, con `filterwarnings = error`), con
Python 3.13 en Linux:

| skforecast | pandas | Resultado |
|:--|:--|:--|
| 0.27.0 | 2.3.3 | Verde (CI de la 0.5.0) |
| 0.28.0 (`0.28.x`) | 2.3.3 | Verde: 7107 passed, 2 skipped |
| 0.28.0 (`0.28.x`) | 3.1.1 | 339 fallos; sin rebajar `Pandas4Warning`, 111 errores al recoger los tests |

Los 339 tests pasan con skforecast 0.28 y pandas 2.3, y con skforecast 0.27:
todo lo que falla es de pandas 3. Lo propio de la 0.28 (`n_jobs=0`, que
skforecast-ai no usa; `n_jobs='auto'` en paralelo sin refit;
`reshape_series_wide_to_long`; el `exog` con `RangeIndex` en multiserie;
`ForecasterRnn`) no rompe nada, y los tests de determinismo siguen en
verde.

### Lo que falla con pandas 3

Cinco causas, no 339 problemas:

1. **Fechas en microsegundos.** pandas 3 lee las fechas de texto en `[us]`,
   y varias funciones de `profiling/data_profile.py` leen `.asi8` como
   nanosegundos (`_DAY_NANOS`, `_HOUR_NANOS`): unos datos diarios salen con
   frecuencia `'86400ms'` en vez de `'D'`, y con ello fallan los días de
   cierre (`regular_gap_weekdays`), la frecuencia más gruesa
   (`'W-SUN'`), las variables de calendario y las window features. Algunas
   ya hacen `as_unit("ns")` antes (`data_profile.py`, hacia las líneas
   2637 y 5758): hacerlo en todas, o calcular en la unidad del índice.
2. **Texto como `str`, no `object`.** `detect_categorical_exog`,
   `detect_numbers_as_text` y el tipo del objetivo (`data_profile.py`) y el
   hash de `assistant.py` solo miran `is_object_dtype`: una exógena de
   texto no es categórica y el script generado falla con `could not
   convert string to float: 'Cádiz'` (ya visto en
   [#95](https://github.com/skforecast/skforecast-ai/pull/95)). Los ids de serie y las columnas de
   texto de las salidas pasan a `str` (tests de `series_ids_as_text`,
   `exog_as_injected`, `sort_rows_by_date`).
3. **Copy-on-Write.** `repeated &= codes >= 0` en `_future_exog.py`
   (`.to_numpy()` de pandas 3 es de solo lectura): `output array is
   read-only` en `forecast` con exógenas futuras en formato largo (36
   tests).
4. **Deprecaciones de pandas 3.1** (`Pandas4Warning`): `.dayofweek`
   (`_last_window.py`, `_utils.py`, `recommendation/calendar.py`,
   `data_profile.py` y los fixtures), `pd.infer_freq` que devuelve texto
   (skforecast lo resuelve con `skforecast/utils/_pandas_compat.py::infer_freq`)
   y `DataFrame.rename(inplace=...)` en un test.
5. **Tests atados a pandas 2**: los mensajes de `pd.to_datetime` ya no
   dicen "at position N" (`parse_text_dates`,
   `try_parse_first_date_column`), un `FutureWarning` que pandas 3 ya no
   emite, y dtypes esperados `object`. Los 53 goldens de contexto que
   fallan (`test_golden_context.py`, `test_describe.py`) son consecuencia
   de 1 y 2: deberían volver a coincidir sin regenerarlos.

### Plan

skforecast 0.28.0 y skforecast-ai 0.6.0 se publican a la vez (D41), así
que la 0.6.0 solo tiene que funcionar con skforecast 0.28: nada de admitir
también la 0.27. El trabajo sale de la rama `0.6.x` (creada el
2026-11-25 desde `0.5.x`), en este orden:

1. **Hecho**: `0.6.x` desde `0.5.x` y `/release-bump 0.6.0`
   ([#149](https://github.com/skforecast/skforecast-ai/pull/149)). `mkdocs build` fallaba con typer 0.29
   y `mkdocs-typer2` 0.4.1, su última versión: `typer<0.29` en el extra
   `docs` ([#150](https://github.com/skforecast/skforecast-ai/pull/150)).
2. **Hecho** ([#151](https://github.com/skforecast/skforecast-ai/pull/151)): `chore/skforecast-028`, los
   mínimos de skforecast 0.28 desde el primer día: `skforecast>=0.28.0`,
   `numpy>=2.0`, `pandas>=2.3`, `scipy>=1.13`, `statsmodels>=0.14.6,<0.16`
   y `requires-python = ">=3.11"` (fuera 3.10 de la matriz de CI y de los
   classifiers, fuera la dependencia de `tomli` y los apaños de 3.10:
   `_undeclared_distributions()`, el backport de `ExceptionGroup` y un
   `QUOTE_NONNUMERIC` en un test). Hasta que skforecast
   publique, `skforecast>=0.28.0` no se resuelve desde PyPI: en local se
   instala antes skforecast desde git
   (`pip install "skforecast @ git+https://github.com/skforecast/skforecast@0.28.x"`),
   y el hook de inicio de las sesiones en la nube ya lo hace solo
   (`skforecast_dev_branch` en `.claude/hooks/session_start.py`). La CI
   solo corre en el PR a `main`, ya con skforecast publicado. Pendiente:
   avisar a skforecast (`REL-skforecast-ai-python311` de su roadmap).
3. **Hecho** ([#152](https://github.com/skforecast/skforecast-ai/pull/152)): `feature/pandas3`, las cinco causas de arriba, con la suite
   en verde con pandas 2.3.3 y con pandas 3.1.1 (los dos contra skforecast
   0.28) y los dos en la matriz de CI: una celda con `pandas<3` (Python
   3.11, Linux), el resto instala pandas 3. Por el camino, dos fallos de
   la 0.5.0 que también se daban con pandas 2.3: las fechas a predecir
   tras el día de un cambio de hora (ahora las de `expand_index` de
   skforecast) y las exógenas de texto de dtype `string` en memoria.
4. La sincronización de `skills/` y `llms-base.txt` desde `0.28.x`
   (cambian 10 ficheros de 8 skills y `llms-base.txt`, sin skills nuevos
   ni borrados; en `troubleshooting-common-errors` entran secciones de
   pandas 3), y otra vez con la `0.28.x` final. Es texto que lee el LLM:
   `/llm-context-change` y check de pago.
5. Las features de "Candidatos".
6. El día de la publicación, a la vez que skforecast 0.28: `skforecast-ai`
   y `skforecast-ai-mcp` 0.6.0 en PyPI, la ficha del registro de MCP y el
   comando del plugin (`uvx skforecast-ai-mcp==0.6.0`) en nuestro
   marketplace y, si se puede, en el directorio de Anthropic (D41).

Antes de publicar, repetir esta revisión sobre la `0.28.x` final.

### Lo que queda de pandas 3

De la revisión final de `feature/pandas3` (2026-11-26, con pandas 2.3.3 y
3.1.1 contra skforecast 0.28). Nada bloquea la release; lo que depende de
skforecast está en la tabla de la sección siguiente.

- **Decidir antes de publicar: el `astype(str)` de las fechas de enteros,
  en el código común.** Hoy el script las pasa a texto al leer el CSV
  (`_emit_data_loading`, que decide por `date_format`) y la ejecución
  convierte los datos en memoria en tres sitios (`compact_dates_as_text`
  en `run_forecast`, `run_backtest` y `exog_as_injected`, que decide por
  el contenido). Un `.astype(str)` dentro de la línea
  `pd.to_datetime(..., format='%Y%m%d')` del código común quitaría la
  función y sus tres llamadas. Cambia los scripts generados otra vez:
  después de publicar la 0.6.0 serían dos cambios para el usuario. Solo
  razonado, sin probar; obliga a regenerar los scripts esperados byte a
  byte.
- **Lecturas de fechas que pandas 3.1 depreca y siguen avisando**
  (`Pandas4Warning`; una versión futura dejará de leerlas). Los floats
  con `date_format`, límite ya aceptado, y las fechas trimestrales de
  texto (`'2005Q1'`): avisan desde `parse_text_dates` en `profile()` y
  `forecast()`, y con pandas 2.3 no. El arreglo cambia el script generado
  (pandas propone `pd.Period('2005Q1').to_timestamp()` o un
  `PeriodIndex`). Sin comprobar si el script también avisa: falla antes
  por el `UserWarning` "Could not infer format", que ya daba.
- **El error de los datos diarios anclados a medianoche UTC cuyo
  horizonte cruza un cambio de hora** (límite ya aceptado) propone un
  remedio que no se puede seguir: "Drop the rows before ..." con la
  primera fila del propio `exog`. Un mensaje correcto pide detectar ese
  caso, que es lógica nueva.

## Dependencia de skforecast

Lo que tiene que estar resuelto en skforecast, y publicado, antes de la
release que lo necesita.

| Qué | Estado | Efecto aquí |
|:--|:--|:--|
| `RollingFeatures`: `transform_batch` (entrenamiento) da NaN en toda ventana con un valor que falta (`min_periods = window_sizes`) y `transform` (predicción) lo salta con `np.nanmean` y similares, sin leer `min_periods` | Por reportar (borrador del issue del 2026-11-11). Sigue igual en `0.28.x` (`d42a411`): es `BUG-rollingfeatures-nan` del roadmap de skforecast, P2, sin empezar | Con huecos y un estimador que no acepta NaN, el forecast de Ridge del check con agentes de la 0.5.0 entrenó con 15 de 84 filas; con uno que los acepta, predice con un estadístico que nunca vio |
| Python 3.10: skforecast 0.27.0 lo depreca y la 0.28.0 pide 3.11 | Hecho en `0.28.x` (skforecast#1496), sin publicar | `requires-python = ">=3.11"` en la `0.6.x` ([#151](https://github.com/skforecast/skforecast-ai/pull/151)) |
| pandas 3: skforecast 0.28 pide `pandas>=2.3, <4.0`, y un entorno nuevo recibe pandas 3 | Hecho en `0.28.x` (skforecast#1501), sin publicar | skforecast-ai falla con pandas 3 (339 tests): es lo primero de la 0.6.0 (sección "Compatibilidad con skforecast 0.28") |
| Mínimos de skforecast 0.28: `numpy>=2.0`, `pandas>=2.3`, `scipy>=1.13` | Hecho en `0.28.x` (skforecast#1500), sin publicar | Mínimos igualados en la `0.6.x`, con `skforecast>=0.28.0` (D41, [#151](https://github.com/skforecast/skforecast-ai/pull/151)) |
| Fechas con zona horaria: skforecast decide si avanzan en hora local o en pasos de UTC (`_is_utc_anchored_index`) con `last_window.index`, solo las filas de la ventana, en los forecasters de ML | Por reportar. Visto el 2026-11-26 con la 0.28.0 de los entornos de prueba | `_forecast_dates` las reconstruye desde la primera fecha de los datos, y difieren con datos a una hora local que es medianoche UTC solo parte del año (diarios a las 20:00 de Nueva York) y un horizonte que cruza un cambio de hora. Con pandas 3.1.1 ningún `exog` pasa las dos comprobaciones; con pandas 2.3 el forecast corre y fecha las predicciones a las 19:00 tras el cambio |
| `_pandas_compat.infer_freq` pone la opción `future.infer_freq_returns_offset` con `pd.option_context`, que es global y la comparten todos los hilos | Por reportar | `infer_freq_name` usa el mismo patrón y el servidor MCP ejecuta las herramientas en hilos: con dos hilos entrelazados, uno recibe el `Pandas4Warning` y la opción puede quedar en `True` para todo el proceso. Reproducido con el entrelazado en un solo hilo, no con hilos reales. Un lock aquí no cubre las llamadas de skforecast |

## Checks de la release

Lo que el cierre de la 0.5.0 dejó para el siguiente check de pago y el
siguiente check con agentes:

- **Check de pago de `ask()`**: 6 respuestas guardadas de escenarios que
  no se repitieron en la pasada parcial del 2026-11-11 (`backtest_code`,
  `plan`, `cv_defaults`) citan el paréntesis del prompt anterior del MASE,
  "(last training value)"; las renueva la próxima pasada completa. Las
  salidas de los notebooks `agentic-forecasting` y
  `agentic-forecasting-step-by-step` guardan el mismo texto y se corrigen
  al volver a ejecutarlos, no a mano. Sin comprobar: si
  `ask(context=profile, plan=plan)` explica el script sin la codificación
  ni el formato de fecha de las exógenas (pregunta 4 de #97); el check no
  tiene ese escenario.
- **Check con agentes**: un fichero con un mes ausente dentro de los folds
  de test, para medir D38 (en `h2o_dirty` los tres meses caen antes del
  primer fold). Ninguna sesión de `0.5.0-final` nombró Timestral ni
  TiRex-2. En `dirty_data` y `dirty_data_keep_gaps` el cliente deniega el
  comando de shell que escribe la copia acordada (10 de 12 sesiones con
  sonnet, 3 de 12 con haiku): sin cambiar eso, esos escenarios no
  concluyen.

## Decisiones tomadas

- **D41 (2026-11-25): sin 0.5.1; skforecast 0.28.0 y skforecast-ai 0.6.0
  salen a la vez.** La 0.6.0 pide los mínimos de skforecast 0.28 desde el
  primer día (plan de la sección "Compatibilidad con skforecast 0.28").
  Con eso, `pip install skforecast-ai` y `uvx skforecast-ai-mcp` sin
  versión reciben la 0.6.0, que funciona con pandas 3. Lo que no arregla,
  aceptado: la 0.4.2 y la 0.5.0 piden `pandas>=2.2` y
  `skforecast>=0.26.0`/`>=0.27.0` sin cota superior, así que se rompen
  con pandas 3 (comprobado en la 0.5.0; en la 0.4.2 es el mismo código de
  detección de categóricas, sin probar):
  - Las instalaciones nuevas con la versión fijada: `uvx
    skforecast-ai-mcp==0.5.0` (el plugin de nuestro marketplace y la ficha
    0.5.0 del registro de MCP hasta que se actualicen) y `uvx
    skforecast-ai-mcp==0.4.2`, el comando de la ficha del directorio de
    Anthropic, que sigue en la 0.4.2 hasta que se resuelva el punto 2 de
    "Lo que queda de la 0.5.0". Mientras no se resuelva, esa ficha queda
    rota desde el día de la publicación.
  - Los entornos con skforecast-ai 0.5.0 que actualizan solo skforecast:
    `pip install -U skforecast` sube a pandas 3 un pandas anterior a 2.3.

  La 0.5.1 con `pandas<3` arreglaría los dos casos de la 0.5.0 (con pandas
  2.3 la suite pasa también con skforecast 0.28), pero no la ficha de
  Anthropic: queda como reserva si skforecast se adelanta o si aparecen
  usuarios afectados.

La siguiente es D42.

## Decisiones abiertas

Se toman en el PR que las necesita y se pasan a la sección de arriba.
Ninguna abierta ahora.

## Herramientas de mantenimiento

No bloquean la release; se hacen cuando haya hueco.

- **Tests unitarios de `tools/mcp/check_mcp_agent.py`.** No tiene ninguno,
  y casi todos los defectos de las dos revisiones de código estaban en sus
  heurísticas (redirecciones, fallos falsos, herramientas que se escapaban).
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

## Candidatos

Lo que la 0.5.0 dejó fuera, sin orden de prioridad todavía.

### Las descripciones de los esquemas de salida del MCP

Ocupan unos 30.800 caracteres, más que las descripciones, los parámetros,
las instrucciones y el SKILL.md juntos, porque el docstring de `ToolResult`
se repite en el `outputSchema` de nueve herramientas (#126, D34). Antes de
acortarlas, medir si Claude Code y los demás clientes pasan el
`outputSchema` al modelo: si no lo pasan, no cuestan nada. Si lo pasan,
dejar en cada herramienta lo suyo y el resto en las instrucciones.

### El periodo del baseline en el resumen de `compare`

El resumen llama al baseline "seasonal naive" sin su periodo (24 en datos
horarios, 12 en mensuales; `select_baseline_seasonal_period`): la frase
de `select_baseline_config` que lo dice no llega al resumen, y en el check
con agentes de la 0.5.0 cuatro sesiones lo dedujeron solas (bien). Cambia
lo que recibe el LLM: goldens y check de pago.

### Los valores que faltan en el tramo de test de `forecast()`

Desde D38, `backtest()` deja fuera de las métricas las fechas de test sin
valor (skforecast 0.27, #1458), pero `forecast()` con `test_size` las sigue
rechazando: su script calcula las métricas con scikit-learn sobre
`actual` tal cual. Alinearlo es escribir en el script la máscara de las
fechas con valor (y `n_evaluated` en sus métricas), lo que cambia todos los
scripts de evaluación (esperados byte a byte, tests standalone y
determinismo). Con varias series, `validate_evaluation_partition` tiene la
misma regla.

### Las frases sobre las fechas de test sin valor

El paso de `plan` ("a backtest leaves those dates out of its metrics",
`missing_values_advice`) y el aviso de `create_cv` ("The metrics leave
out the test dates without a value. ... Impute the target to backtest
every fold", `backtest_missing_values_messages`), los dos de #139 (D38),
son reglas generales escritas sin los datos: salen siempre que el objetivo
tiene valores o fechas que faltan, también cuando ninguna fecha de test
falta. En `0.5.0-final-haiku`, 3 de 9 respuestas las repiten como algo que
pasó (se midieron 36 de 36 predicciones); 0 de 2 con sonnet. Aceptado para
la 0.5.0 (2026-11-11): solo lo muestra el modelo débil, no toca datos del
usuario y las frases son ciertas como regla.

Precisarlo: `create_cv()` no recibe los datos (el perfil dice cuántos
valores faltan, no dónde), así que o las frases se escriben como condición
explícita ("if a test fold holds a missing date, the metrics leave it
out"), o lo dice quien sí lo sabe, el resumen de `backtest`, que ya cuenta
las fechas que quedan fuera y podría decir también que no quedó ninguna.
"Impute the target to backtest every fold" sobra cuando el estimador
acepta los valores que faltan. Cambia textos que lee el LLM (la explicación
del plan y el resumen del backtest): goldens y check de pago. De paso, el
check con agentes necesita un fichero con un mes ausente dentro de los
folds de test: en `h2o_dirty` los tres caen antes del primero, y ninguna
sesión ejercita D38.

### Las métricas por serie en el SKILL.md del servidor

El paso 1 de la lectura de resultados dice "The summary only gives the
average, so the worst series is not in it": vale para el leaderboard de
`compare`, pero el resumen de un `backtest` lista hasta 5 series (con su
`n_evaluated`). En `0.5.0-fix3` los agentes nombran bien la peor serie (3
de 3), así que solo es precisión del texto: decir que el resumen de
`compare` da la media y el de un backtest hasta 5 series, y que con más
se leen las filas del fichero. Cambia el SKILL.md y su copia del plugin.

### El banner de pydantic-ai en la CLI

Desde la 2.62, pydantic-ai imprime en stderr un banner con publicidad de
Logfire en la primera llamada a un agente de cada proceso, cuando stderr es
un terminal o detecta un agente de código (`CLAUDECODE`, `CODEX_*`...). Lo
ve quien usa `skforecast-ai ask` o `ask()` desde un terminal; no sale en
Jupyter, CI ni pytest. Salió en los notebooks de la 0.5.0 porque el kernel
heredó las variables de Claude Code, y se quitó a mano de las salidas.

La CLI pone `pydantic_ai.BANNER_ENABLED = False` antes de la primera
llamada: es el interruptor que pydantic-ai documenta para un programa que
gestiona su propia salida. En la API de Python no: sería un global de una
librería del usuario y le quitaría también el banner de sus propios agentes.
Al volver a ejecutar los notebooks desde una sesión de Claude Code, con
`PYDANTIC_AI_NO_BANNER=1`. Lleva test y nota de release.

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

### Referencias de los skills a demanda

Solo si la comprobación con un modelo real muestra respuestas a las que les
faltan detalles de `references/` (D39, D40). `ask()` mandaría el SKILL.md
de los skills elegidos, igual que hoy de forma determinista, y una
herramienta de pydantic-ai devolvería una sección `##` de una referencia,
apoyada en el `## Contents` que exige el validador de skforecast; las
secciones leídas quedarían en `AskResult`. En contra, y por eso no entra
en la 0.5.0: ayuda poco a los alojados (ventanas de 128k o más, el límite
es el coste), Ollama es donde peor funcionan las herramientas y su
`num_ctx` se fija antes de la llamada, lo que ve el modelo deja de ser
reproducible, y el modelo puede no leer la sección que importa (las tablas
comunes de `adapter-parameters.md` comparan todos los adaptadores). No hace
falta partir los ficheros en skforecast: se lee por secciones.

### Ajuste de hiperparámetros

Desbloqueado con skforecast 0.27 (los arreglos citados abajo están
publicados); la 0.28 hace además más rápidas las búsquedas en paralelo
(skforecast#1503) y rechaza `n_jobs=0` con un `ValueError` (skforecast#1513).

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

### Días de cierre con `CustomBusinessDay` y `weekmask`

La solución de fondo para un negocio que cierra los mismos días de la
semana. Desde 1e
([#98](https://github.com/skforecast/skforecast-ai/pull/98), D9), unos
datos diarios sin domingos son `'D'` con los domingos como fechas que
faltan: `forecast` los predice, `forecast` con `test_size` falla porque
caen en el tramo de test, y `backtest` los deja fuera de las métricas (D38)
pero falla con un estimador que no acepta valores que faltan, porque los
lags los leen. El aviso y los errores lo dicen y proponen rellenarlos con 0
pidiendo permiso. Una frecuencia sin esos días
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
