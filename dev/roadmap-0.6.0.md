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
     Falta esperar a que recalcule el TDQS y apuntar las notas por
     herramienta en el log de `tools/mcp/README.md`. Criterios del plan de
     descripciones: "cuándo usarla" en 3 o más y ninguna herramienta por
     debajo de B; concisión sin bajar de 4. Sin verificar que Glama lo
     recalcule al hacer la release.
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

## Dependencia de skforecast

Lo que tiene que estar resuelto en skforecast, y publicado, antes de la
release que lo necesita.

| Qué | Estado | Efecto aquí |
|:--|:--|:--|
| `RollingFeatures`: `transform_batch` (entrenamiento) da NaN en toda ventana con un valor que falta (`min_periods = window_sizes`) y `transform` (predicción) lo salta con `np.nanmean` y similares, sin leer `min_periods` | Por reportar (borrador del issue del 2026-11-11) | Con huecos y un estimador que no acepta NaN, el forecast de Ridge del check con agentes de la 0.5.0 entrenó con 15 de 84 filas; con uno que los acepta, predice con un estadístico que nunca vio |
| Python 3.10: skforecast 0.27.0 lo depreca y la 0.28.0 pedirá 3.11 | Anunciado | `requires-python = ">=3.10"` en `pyproject.toml`: subir a 3.11 con la release que pida skforecast 0.28 |

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

Ninguna todavía. La siguiente es D41.

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

skforecast 0.27 declara `pandas<3.0`, así que hoy el resolvedor nunca
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
