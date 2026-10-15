# Plan: descripciones de las herramientas del servidor MCP

Para la próxima versión con cambios en el servidor (0.4.3 o 0.5.0). Nada de
esto se ha implementado todavía.

## Contexto

Glama puntúa cada herramienta de un servidor MCP con su TDQS (Tool
Definition Quality Score): seis criterios de 1 a 5 y una nota de A a F. Lo
evalúa leyendo cada descripción por separado, con su esquema y sus
anotaciones; no lee las instrucciones que el servidor manda al conectarse
ni el skill.

Medido el 2026-10-15 sobre la 0.4.2 (la ficha
<https://glama.ai/mcp/servers/skforecast/skforecast-ai>, sección "Available
Tools"; la página no lo muestra como texto, se sacó de los datos
incrustados en `/tools/<nombre>`):

| Herramienta | Nota | TDQS | Propósito | Cuándo usarla | Parámetros | Comportamiento | Concisión | Completitud |
|:--|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `compare` | A | 4.0 | 5 | 3 | 3 | 4 | 5 | 4 |
| `refine_plan` | A | 3.8 | 4 | 3 | 3 | 4 | 5 | 4 |
| `forecast` | A | 3.7 | 4 | 3 | 3 | 4 | 4 | 4 |
| `profile` | A | 3.7 | 4 | 3 | 3 | 3 | 5 | 5 |
| `plan` | A | 3.6 | 5 | 2 | 3 | 3 | 5 | 4 |
| `backtest` | A | 3.5 | 4 | 3 | 3 | 3 | 4 | 4 |
| `get_code` | A | 3.5 | 4 | 3 | 3 | 3 | 4 | 4 |
| `create_cv` | B | 3.2 | 4 | 2 | 3 | 3 | 4 | 4 |
| `describe_object` | B | 3.2 | 4 | 2 | 3 | 3 | 4 | 3 |
| `get_failure` | B | 3.2 | 4 | 2 | 3 | 3 | 4 | 4 |
| `list_objects` | C | 2.9 | 3 | 2 | 3 | 3 | 4 | 3 |

Lo que dice, en resumen:

- **Cuándo usarla (2 o 3 en todas):** cada descripción dice qué hace la
  herramienta, pero no qué va antes, qué va después ni cuándo usarla en vez
  de una hermana. Glama marca este criterio como problema en las cinco con
  2. Ejemplos literales: `create_cv`, "nothing explains when to create a CV
  versus calling 'backtest' or 'forecast'"; `plan`, no dice que antes va
  `profile` ni que `forecast` consume el id del plan; `list_objects`,
  "never identifies the object domain or routes to describe_object".
- **Comportamiento (3 o 4):** las anotaciones ya cubren la seguridad. Echa
  en falta casos límite: qué pasa si `get_failure` recibe algo que no ha
  fallado, si `backtest` sobrescribe ficheros, cuánto duran los objetos.
- **Parámetros (3 en todas):** es la nota base cuando el esquema documenta
  todos los parámetros. No penaliza; subirla exigiría repetir en la
  descripción lo que ya dice el esquema, y no compensa.
- **Concisión (4 o 5):** está bien; no hay que perderla.

Para un agente real el hueco es menor: el flujo completo está en las
instrucciones del servidor (`_instructions` en
`skforecast_ai/mcp/server.py`) y en el skill, y la comprobación con agentes
de la 0.4.0 lo midió así. Pero hay clientes que muestran o seleccionan
herramientas por su descripción, sin las instrucciones, y la nota de Glama
es pública.

## Objetivo

Que cada descripción diga, en una frase como mucho, su lugar en el flujo
(qué id necesita y quién usa el suyo) y la alternativa con la que se puede
confundir. Llevar "Cuándo usarla" a 3 o 4 en todas, sin bajar la
concisión ni cambiar el comportamiento del servidor.

No es objetivo subir "Parámetros", ni explicar en las descripciones lo que
ya explican las instrucciones (reglas de confianza, coste, privacidad).

## Lo que hace hoy el servidor en las preguntas de Glama

Comprobado en el código de la 0.4.2, para no prometer en las descripciones
nada que no sea cierto:

- **Ficheros:** cada fichero se nombra con el id del objeto
  (`<id>-<rol>.csv`, `write_frame`), así que una ejecución nunca
  sobrescribe la de otra.
- **Vida de los objetos:** el servidor guarda como mucho `--max-objects`
  (256) y `--max-memory-mb` (1024); al pasar el límite borra los menos
  usados, y un id borrado da un error que lo dice. Nada sobrevive a un
  reinicio.
- **`get_failure`:** recibe el `details.failure_id` de un error o el id de
  una comparación con algún candidato fallido. Hay que comprobar al
  implementar qué responde con el id de un objeto que no ha fallado, y
  escribirlo tal cual.

## Propuesta de texto

Cada descripción actual más una frase de flujo. Borrador, a revisar al
implementarlo (los nombres de los campos de las respuestas, contra el
código):

| Herramienta | Frase que se añade |
|:--|:--|
| `profile` | First step of the workflow: `plan` takes its id. |
| `plan` | Needs a profile id from `profile`; `create_cv` and `forecast` take its id. To change a decision afterwards, use `refine_plan`. |
| `refine_plan` | Use it instead of `plan` to keep the other decisions of a plan. |
| `create_cv` | Needs a plan id; `backtest` and `compare` take its id. Read `cost` before running them. |
| `backtest` | Needs a cv id from `create_cv`; use `compare` to rank several configurations. Each run writes new files and never overwrites another. |
| `compare` | Needs a cv id from `create_cv`; use `backtest` for one configuration. |
| `forecast` | Needs a plan id; backtest the plan first to know how accurate it is. |
| `get_code` | Takes the id of a plan, a strategy or a run (not of a profile); `get_failure` gives the code of a run that failed. |
| `get_failure` | Use it after an error that gives a `details.failure_id`; `get_code` gives the code of a run that worked. (Más lo que responde con un objeto que no ha fallado.) |
| `list_objects` | The objects are the profiles, plans, strategies and runs of this session; the least recently used are removed beyond the limits of the server. Use `describe_object` to read one. |
| `describe_object` | Takes an id from any response or from `list_objects`. |

Coste: las descripciones suman hoy 1310 caracteres y viajan en cada
petición del agente. La propuesta añade unos 1100 (unos 280 tokens por
petición). Si parece mucho, las de `profile`, `refine_plan` y
`describe_object` son las que menos aportan.

## Pasos

1. Rama `feature/mcp-tool-descriptions` desde la rama de la versión.
2. Comprobar en el código los dos puntos abiertos: qué responde
   `get_failure` con un objeto que no ha fallado, y que todos los
   nombres y campos citados en la tabla existen.
3. Cambiar las descripciones en `_build_tools` (las llamadas a
   `_StrictTool.build`, al final de `skforecast_ai/mcp/server.py`).
4. Regenerar el golden de los esquemas y revisar el diff: solo deben
   cambiar las descripciones.
   `python -c "from tests.tests_mcp.fixtures_mcp import write_golden_schemas; write_golden_schemas('/tmp')"`
   (`tests/tests_mcp/golden/tool_schemas.json`, que comprueba
   `tests/tests_mcp/test_create_server.py`).
5. Revisar si las instrucciones del servidor o el skill
   (`skforecast_ai/mcp/skills/`, y su copia en `plugin/skills/`) repiten
   algo que ahora dice la descripción, por si conviene acortarlos.
6. `/verify`, nota de release (las descripciones son lo que ven los
   agentes) y PR.
7. Antes de la release, la comprobación con agentes de `tools/mcp/`: un
   cambio de descripciones está en "When to run it" de
   `tools/mcp/README.md`, y tiene que cumplir sus criterios de aceptación.
   Al menos con sonnet y con haiku, en los escenarios críticos.
8. Tras publicar: Deploy y Make Release en Glama (con el número de la
   versión del paquete), esperar a que recalcule el TDQS y apuntar las
   notas nuevas en este fichero y en el log de `tools/mcp/README.md`.

## Criterios de aceptación

- "Cuándo usarla" en 3 o más en todas las herramientas, y ninguna por
  debajo de B.
- Concisión sin bajar de 4 en ninguna.
- La comprobación con agentes cumple sus criterios, sin empeorar frente a
  la de la 0.4.0 en los escenarios críticos.
- El golden solo cambia en las descripciones.

## Sin verificar

- Que Glama recalcule el TDQS al hacer una release nueva; puede hacerlo
  con su propio calendario.
- Cuánto pesa la nota de Glama en otros directorios. awesome-mcp-servers
  solo exige la insignia, no una nota mínima.
- Si otros clientes (Cursor, VS Code) usan la descripción para elegir
  herramientas cuando hay muchas conectadas.
