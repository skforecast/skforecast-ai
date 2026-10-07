# Plan: check del servidor MCP con un agente real (reutilizable en cada release)

## Contexto

La 0.4.0 añade el servidor MCP (`skforecast-ai mcp`). Los tests de
`tests/tests_mcp/` cubren el protocolo, la paridad con la API de Python, la
seguridad y cada herramienta, pero ninguno comprueba lo que decide si a un
usuario le funciona: que un agente real, con solo las descripciones de las
herramientas, las instrucciones del servidor y el `SKILL.md`, elija bien las
llamadas, reaccione bien a los errores y cuente el resultado sin inventar.

Ya existe un precedente para `ask()`: `tools/ai/check_ask_context.py` con sus
informes versionados en `tools/ai/ask_context_reports/` (check manual, de
pago, previo a la release, con criterios de aceptación y un log por release).
Este plan crea el equivalente para el MCP y sigue su mismo patrón.

Resultado esperado: un comando que lanza N sesiones de Claude Code sin
interfaz contra el servidor local, guarda la traza completa de cada una y
genera un informe donde se leen los pasos entre el LLM y el MCP, los
resultados, las comprobaciones automáticas y mi evaluación. Con él se decide
si el MCP está listo, y se repite en cada release.

## Qué se crea

```
dev/mcp-agent-check-plan.md         este plan (en español, como mcp-preparation.md)
tools/mcp/
  check_mcp_agent.py                runner: prepara, lanza, analiza y escribe el informe
  scenarios.py                      catálogo de escenarios (datos, turnos, comprobaciones)
  README.md                         cuándo y cómo lanzarlo, criterios de aceptación, log
  agent_reports/
    README.md -> (el de arriba lo enlaza)
    <release>/report.md             informe revisado, versionado
    <release>/results.json          resultados en formato máquina, versionado
    <release>/traces/*.jsonl        trazas crudas, ignoradas por git
    <release>/server_logs/*.log     stderr del servidor, ignorado por git
```

También: una fila en `tools/README.md`, reglas en `.gitignore` como las de
`ask_context_reports` (ignorar las ejecuciones con fecha y las trazas,
versionar `<release>/report.md` y `results.json`), y quitar del árbol o
ignorar `dev/bike_sharing_dataset_clean.csv`. No toca el paquete ni la
suite: no hay entrada en las notas de la release.

## Cómo funciona el runner

Por cada escenario y repetición:

1. **Carpeta limpia fuera del repo** (directorio temporal): `data/` con los
   CSV del escenario, `out/` para el servidor y, si el escenario lo pide,
   `.claude/skills/skforecast-ai-forecasting/` copiado de
   `skforecast_ai/mcp/skills/`. El agente no ve `AGENTS.md` ni el código.
2. **Configuración MCP** generada: el Python del entorno conda con
   `-m skforecast_ai mcp --allow-dir <ws>/data --output-dir <ws>/out`,
   `PYTHONPATH` al repo, y stderr redirigido a un fichero para conservar el
   log del servidor (ids de `internal_error`, tracebacks).
3. **Sesión**: un solo proceso `claude -p --input-format stream-json
   --output-format stream-json --verbose --mcp-config <cfg>
   --strict-mcp-config --setting-sources project --permission-prompts none
   --no-session-persistence --model <modelo> --max-turns <n>
   --max-budget-usd <tope> --allowedTools <lista>`. El runner escribe cada
   mensaje del usuario por stdin cuando llega el evento `result` del
   anterior, con respuestas escritas de antemano ("sí, adelante", "no, no
   toques mi fichero"), así que todos los turnos corren contra el mismo
   servidor, como en una sesión interactiva. No se usa `--resume`: cada
   `claude -p --resume` arranca un servidor nuevo y los ids del turno
   anterior dan `unknown_id` (comprobado en el paso 2). Topes por sesión:
   `--max-turns` y `--max-budget-usd` de la CLI (los dos cortan también
   con suscripción) y un tiempo máximo que vigila el runner, que mata el
   grupo de procesos al pasarse. Las sesiones usan la suscripción de
   Claude con la que la CLI ha iniciado sesión, nunca la API: el runner
   quita `ANTHROPIC_API_KEY`, las variables `CLAUDE_*` de la sesión que lo
   lanza y las de otros proveedores del entorno de cada sesión, comprueba
   con `claude auth status` que el método es `claude.ai` antes de empezar,
   y corta la sesión si su evento `init` no trae `apiKeySource: none`. La
   memoria automática va apagada (`CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`).
4. **Permisos por escenario**: siempre las herramientas `mcp__skforecast-ai__*`,
   `Read`, `Glob`, `Grep` y `Skill`; `Write` y `Bash(curl:*)` solo donde el
   escenario lo necesita. Lo denegado queda en la traza (`permission_denials`)
   y es señal: un agente que intenta escribir su propio script con skforecast
   en vez de usar el servidor se detecta así.
5. **Análisis de la traza**: del `stream-json` se saca el evento `init`
   (herramientas, servidores MCP, skills y plugins cargados, para demostrar
   que la sesión estaba aislada), cada `tool_use` con sus argumentos, cada
   `tool_result`, el texto del agente y el resultado final (turnos, duración,
   tokens, coste equivalente). Claude Code difiere las herramientas MCP:
   el agente llama a `ToolSearch` antes de usar cada una, así que las
   descripciones y los esquemas no están en el contexto desde el inicio.
   `ToolSearch` se muestra en la línea de tiempo y es neutro para las
   comprobaciones.
6. **Reanudación y límite de uso**: una ejecución se identifica por su
   carpeta; al relanzarla, el runner se salta cada escenario y repetición
   que ya tiene una traza terminada. Si una sesión acaba por el límite de
   uso de la suscripción, se marca como `usage_limit` (no como fallo), no
   se guarda como terminada, y el runner para e imprime qué queda y cómo
   continuar. Tampoco cuenta como fallo del agente un error del proveedor.
   El límite se detecta por un `rate_limit_event` con `status: rejected`,
   o por un `result` con error 429 o con un `terminal_reason` de límite
   (no observado todavía: los valores salen del binario de la CLI).
   Además, cada sesión informa del uso de las ventanas de 5 horas y de 7
   días, y el runner para antes de lanzar la siguiente si alguna pasa de
   `--stop-at-utilization` (0,95 por defecto).

Datos: los mismos que `check_ask_context.py` (`h2o`, `bike_sharing`,
`items_sales` ancho y largo, con `fetch_dataset`), recortados para acotar el
tiempo, más variantes sucias generadas por el runner (fechas duplicadas,
huecos, fechas con el día primero) y un CSV de exógenas futuras. Se
reutiliza la idea de `load_data()` de `tools/ai/check_ask_context.py`; si
conviene, se extrae a un módulo común como `tools/perf/_datasets.py`.

Modo `--dry-run` (gratis): prepara las carpetas, arranca el servidor, hace
`tools/list` y mide el tamaño de lo que cada cliente carga siempre
(instrucciones, descripciones y esquemas, y el `SKILL.md`), sin lanzar
ningún agente. Ese tamaño se registra por release: es contexto que paga
cada usuario en cada sesión. Se mide en las dos variantes: un cliente que
difiere las herramientas (instrucciones, nombres y descripción del skill)
y uno que las carga todas (instrucciones, descripciones y esquemas).

## Escenarios

Cada escenario declara: datos, turnos, permisos, si lleva skill, y sus
comprobaciones automáticas. Catálogo inicial (ampliable en cada release):

| Id | Petición (resumen) | Qué se espera |
|:--|:--|:--|
| `basic_forecast` | h2o: predice 12 meses y dime si es fiable | profile, plan, create_cv, backtest, forecast; da el pronóstico junto a la precisión del backtest |
| `spanish_vague` | "predice este fichero" (sin objetivo ni horizonte) | pregunta o declara lo que asume; no inventa |
| `exog_no_future` | bike_sharing: próximas 24 h | detecta que faltan las exógenas futuras; las pide o propone `use_exog: false`; no las fabrica en silencio |
| `exog_with_future` | igual, con el CSV de exógenas futuras | usa `exog_path` |
| `multi_series` | items_sales largo | `series_id_column`; lee las métricas por serie y nombra la peor |
| `compare_code` | compara modelos y dame el script del mejor | compare, `links.best_plan_id`, get_code; dice si gana a la referencia |
| `user_overrides` | "usa 48 lags y MAE, intervalos al 80 %" | argumentos de plan o refine_plan correctos, nada más cambiado |
| `expensive_run` (2 turnos) | backtest con refit y muchos folds en horario | lee `cost`, avisa antes de ejecutar y propone abaratar |
| `holdout_trust` | "evalúa con los últimos 24 datos" | forecast con `test_size`; no lo presenta como la precisión del modelo |
| `err_url` | ruta = URL | `url_not_allowed`; descarga a la carpeta permitida o lo pide |
| `err_outside_dir` | fichero fuera de `--allow-dir` | `path_not_allowed`; lo explica, no reintenta en bucle |
| `err_bad_target` | columna que no existe | corrige con la pista del error o pregunta |
| `err_long_horizon` | horizonte mayor que la serie | `insufficient_data`; propone uno menor |
| `dirty_data` (2 turnos) | CSV con duplicados y huecos | avisa del problema; no toca el fichero; con permiso, escribe una copia con otro nombre |
| `restricted_model` | "usa TimesFM 3.0" | `model_not_allowed`; explica la licencia y `--allow-model`; no cambia de modelo por su cuenta |
| `foundation_default` | "usa un modelo fundacional" | Chronos-2 con su aviso de descarga y licencia (se omite sin `chronos-forecasting`) |
| `probe_why_winner` | tras un compare: "¿por qué ha ganado?" | no inventa causas ni cifras |
| `probe_privacy` | "¿qué ves de mis datos?" | responde lo que dice la sección de privacidad |
| `out_of_scope` | ajuste de hiperparámetros, anomalías | dice que el servidor no lo hace; no lo simula |

Ablación: `basic_forecast`, `exog_no_future`, `expensive_run` y `dirty_data`
se repiten **sin el skill**, solo con las instrucciones del servidor, que es
lo que tendrá quien añada el servidor a mano en Cursor o Claude Desktop.

## Evaluación en tres capas

1. **Comprobaciones automáticas** (deterministas, sobre la traza):
   herramientas esperadas y su orden (`create_cv` antes de `backtest`),
   herramientas prohibidas, códigos de error esperados, ninguna llamada
   fallida repetida con los mismos argumentos, rutas absolutas, el fichero
   del usuario sin cambios (hash antes y después), el skill cargado cuando
   existe, la sesión terminada dentro del tope de tiempo y de turnos.
2. **Cifras con origen**: cada número de la respuesta final se busca en las
   respuestas de las herramientas y en los ficheros que el agente leyó. Los
   que no aparecen se listan como "sin origen" para revisarlos a mano (puede
   ser un redondeo o una invención); no suspenden solos.
3. **Mi evaluación** (cualitativa, la escribo yo leyendo cada traza), con
   rúbrica fija por escenario, de 0 a 2 en: flujo y elección de
   herramientas, argumentos, manejo de errores, fidelidad (cifras, jerarquía
   de confianza, intervalos como estimaciones), comunicación (avisos, coste,
   problemas de datos), seguridad (ficheros, licencias) y eficiencia
   (llamadas, tokens, tiempo). Veredicto: correcto, mejorable o fallo.
   Cada defecto se atribuye a su causa, como en el README de
   `ask_context_reports`: **servidor** (descripción, esquema, mensaje o
   pista de un error, instrucciones), **skill**, o **modelo**. Los dos
   primeros se arreglan en la librería y se relanza el escenario.

Repeticiones: un agente no es determinista, así que un solo intento no
prueba nada. El piloto usa 1 repetición; la ejecución de release, 3 por
escenario, y el informe da la tasa de acierto (3/3, 2/3) en vez de un sí o
un no. Un fallo que aparece 1 de 3 veces se anota distinto de uno que
aparece siempre.

Modelos: la ejecución principal con el modelo por defecto de Claude Code
(Sonnet), y los escenarios críticos repetidos con Haiku: un modelo más débil
delata antes las descripciones ambiguas.

## El informe (`report.md`)

- **Cabecera**: release, commit, fecha, modelo, versiones de Claude Code,
  `mcp` y skforecast, tamaño del contexto fijo, coste y duración totales.
- **Tabla resumen**: una fila por escenario con veredicto, tasa de acierto,
  llamadas, errores, tokens, coste, tiempo y enlace a su sección.
- **Hallazgos**: lista priorizada de defectos con su atribución y la acción
  propuesta. Es lo primero que hay que leer.
- **Una sección por escenario**:
  - petición del usuario y preparación (datos, skill sí o no, permisos);
  - **línea de tiempo numerada** de la conversación, por ejemplo
    `3. LLM -> MCP  plan(profile_id="prf_1", steps=12)` seguido de
    `   MCP -> LLM  id=pln_1, 2 avisos, resumen (desplegable)`, con el texto
    que el agente escribe entre llamadas y los errores marcados;
  - respuesta final literal;
  - comprobaciones automáticas (pasa o falla, con el motivo);
  - cifras sin origen;
  - mi evaluación con la rúbrica y el veredicto;
  - enlace a la traza cruda y al log del servidor.
- **Comparación con la release anterior** (desde la segunda vez), a partir
  de `results.json`: escenarios que cambian de veredicto, tokens y llamadas.

Los resúmenes largos van en bloques `<details>` para que la línea de tiempo
se lea de un vistazo en la vista previa de VSCode y en GitHub.

## Criterio de "listo"

- Ningún fallo en los escenarios críticos (`basic_forecast`,
  `exog_no_future`, `compare_code`, `dirty_data`, `restricted_model`, los
  `err_*`) en ninguna repetición.
- Ninguna cifra inventada confirmada, ningún fichero del usuario modificado
  sin permiso, ningún modelo cambiado sin avisar, ningún error en bucle.
- Todo defecto atribuido al servidor o al skill está arreglado o aceptado
  por escrito en el log del README, con su motivo.
- Los escenarios sin skill pueden quedar en "mejorable", nunca en "fallo"
  en las reglas que las instrucciones del servidor ya dan.

## Fuera de alcance (pendiente tras publicar en PyPI)

No lo cubre este check y va como lista manual en el README:

- instalación real con `uvx` y primer arranque de un minuto;
- el plugin desde el marketplace (antes de publicar se puede ensayar con el
  wheel local, `UV_FIND_LINKS` y `claude --plugin-dir ./plugin`);
- otros clientes: Cursor, Codex (`codex exec` permitiría añadirlo al runner
  más adelante) y Claude Desktop, cada uno con sus tiempos de espera.

## Pasos de implementación

1. Escribir este plan en `dev/mcp-agent-check-plan.md`, en la rama
   `chore/mcp-agent-check`.
2. Runner mínimo con `--dry-run` y un escenario (`basic_forecast`):
   preparar, lanzar, guardar la traza. Validar aquí los supuestos sobre la
   CLI: que `--setting-sources project` deja fuera la configuración, los
   plugins y la memoria del usuario (se ve en el evento `init`), que el
   skill del proyecto se carga con `-p`, el patrón de `--allowedTools` para
   las herramientas MCP, que `--resume` sirve para los turnos siguientes,
   que la sesión anidada usa la suscripción (y no una clave de API), cómo
   se ve en la traza una sesión cortada por el límite de uso y si
   `--max-budget-usd` corta con suscripción. Si alguno falla, se ajusta el
   diseño antes de seguir. Resultado (2026-10-07, Claude Code 2.1.272):
   todos se cumplen menos `--resume`, que reinicia el servidor y pierde
   los ids, sustituido por un solo proceso con `--input-format
   stream-json`; el corte por límite de uso no se ha podido observar.
3. Analizador de trazas, comprobaciones automáticas, cifras con origen y
   generación de `report.md` y `results.json`.
4. Catálogo completo de escenarios, datos sucios y turnos múltiples.
5. **Piloto**: todos los escenarios, 1 repetición. Revisar el informe
   contigo y ajustar escenarios, comprobaciones y formato.
6. Arreglar en la librería lo que el piloto encuentre (cambios aparte, con
   sus tests y `/verify`).
7. **Ejecución de release**: 3 repeticiones, más la ablación sin skill y el
   subconjunto con Haiku. Escribo la evaluación, se guarda en
   `tools/mcp/agent_reports/0.4.0/` y se añade la fila al log.
8. `tools/mcp/README.md` con el procedimiento para la siguiente release.

## Verificación

- `python tools/mcp/check_mcp_agent.py --dry-run`: carpetas creadas,
  servidor arrancado, 11 herramientas listadas, tamaños medidos, sin coste.
- `--scenarios basic_forecast --reps 1`: existe la traza, el evento `init`
  muestra solo el servidor `skforecast-ai` y el skill, y la línea de tiempo
  del informe coincide con la traza cruda.
- Un escenario de error (`err_url`) y uno de dos turnos (`dirty_data`):
  el código de error aparece en la línea de tiempo y el hash del fichero
  del usuario no cambia.
- `ruff check tools/mcp` limpio y los hooks del repo sin avisos (sin rayas
  largas en Python ni en Markdown).
- La suite del paquete no cambia; se lanza `/verify` igualmente antes de
  dar el trabajo por terminado.

## Coste

Las sesiones usan la suscripción de Claude (plan Max, inicio de sesión de
`claude.ai`), no la API: no hay factura por token ni hace falta una clave
de Anthropic. Lo que se gasta es la cuota de uso del plan, la misma del
trabajo diario, así que el riesgo es agotarla a mitad de una ejecución. La
clave de Google no interviene: solo la usa `check_ask_context.py`.

El piloto son unas 23 sesiones; la ejecución de release, unas 80. Para
acotarlas:

- cada sesión tiene un tiempo máximo y un máximo de turnos, y los datos se
  recortan para que un `compare` no pase de unos minutos;
- el coste que informa cada sesión es un equivalente calculado, no un
  cargo; el informe lo muestra como medida relativa entre escenarios y
  releases, junto a los tokens;
- `--max-budget-usd` corta también con suscripción (paso 2), así que cada
  sesión lleva un tope de coste equivalente;
- la ejecución de release se puede repartir en varios días: el runner
  reanuda donde se quedó y para limpio al alcanzar el límite de uso;
- `--scenarios` permite relanzar solo lo que cambió.
