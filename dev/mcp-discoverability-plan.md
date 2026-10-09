# Plan: que la gente encuentre el servidor MCP

## Contexto

La 0.4.0 está en PyPI con el servidor MCP (`skforecast-ai mcp`), el plugin de
Claude Code y la guía. Lo que falta es que alguien que no conoce skforecast-ai
lo encuentre. Este plan ordena los pasos para publicarlo en el registro
oficial de MCP y en los directorios que más pesan, y dice quién hace cada
uno.

Comprobado el 2026-10-09:

- La API del registro (`registry.modelcontextprotocol.io`) devuelve 0
  resultados para `skforecast`. De los 14 de `forecast`, ninguno es una
  librería de series temporales.
- El registro pide un `server.json` y la línea `mcp-name: <nombre>` en el
  README del paquete publicado en PyPI. Se publica con la CLI
  `mcp-publisher`.
- El `identifier` de la ficha debe ser el nombre literal de un paquete de
  PyPI: no admite extras. `skforecast-ai` sin `[mcp]` no arranca el servidor.
- `mcp` 2.3.0 arrastra starlette, uvicorn, httpx2, pyjwt con cryptography,
  opentelemetry-api, jsonschema y sse-starlette: demasiado para dependencia
  base de quien solo usa la API de Python.
- El registro sigue en preview, sin garantías de disponibilidad. Está pensado
  para agregadores; el consumidor mejor documentado es el GitHub MCP Registry
  (Copilot y VS Code).

## Decisiones tomadas

| Decisión | Elegido | Por qué |
|:--|:--|:--|
| Cómo resolver el extra | Paquete puente `skforecast-ai-mcp` | La librería no engorda, no hace falta una 0.4.1 y reserva el nombre en PyPI |
| Nombre en el registro | `io.github.skforecast/skforecast-ai` | El login de GitHub no necesita tocar el DNS de `skforecast.org` |
| Versión del puente | La misma que `skforecast-ai`, con pin exacto | Una ficha del registro nunca instala otro servidor, como el plugin |
| Dónde vive el puente | En este repo, `packages/skforecast-ai-mcp/` | Un solo bump de versión y un test que ata las dos |

## Decisiones abiertas

- **A1. Publicar en el registro a mano o con un workflow.** La propuesta es a
  mano (`mcp-publisher publish`, un paso más de la release), porque hasta
  ahora no se toca el CI y las releases las publicas tú. El workflow con OIDC
  (sin secretos) queda como mejora si el paso manual se olvida.
- **A2. Cambiar el plugin y la guía al comando corto.** El plugin arranca hoy
  `uvx --from "skforecast-ai[mcp]==0.4.0" skforecast-ai mcp`, medido y
  comprobado. La propuesta es no tocarlo en esta ronda y que la guía nombre
  `uvx skforecast-ai-mcp` como alternativa solo después del paso 2.4.
- **A3. Bajo qué versión va la nota de release.** El puente y la ficha no
  cambian el paquete `skforecast-ai`. Propuesta: una entrada en la sección de
  la versión en desarrollo cuando exista.

## Fase 1: paquete puente y ficha, en esta rama (yo)

Estado, 2026-10-09: hechos 1.1 a 1.7, salvo `mcp-publisher validate`, que no
está instalado en la máquina y queda para el paso 2.3 (`server.json` valida
contra el esquema `2025-12-11` con `jsonschema`). El wheel del puente,
instalado con `uvx --isolated` contra la 0.4.0 de PyPI, responde a
`initialize` como `skforecast-ai` 0.4.0. `claude plugin validate --strict`
pasa para el plugin y para el marketplace (paso 3.1). Los comandos de la
fase 2 están en `packages/README.md`.

1.1. **Crear `packages/skforecast-ai-mcp/`**:

```
packages/skforecast-ai-mcp/
  pyproject.toml            name skforecast-ai-mcp, version 0.4.0,
                            dependencies ["skforecast-ai[mcp]==0.4.0"],
                            script skforecast-ai-mcp
  README.md                 qué es, cómo se usa, enlace a la guía y la línea
                            <!-- mcp-name: io.github.skforecast/skforecast-ai -->
  LICENSE                   copia de la del repo
  skforecast_ai_mcp/
    __init__.py             main(): llama a la app de Typer con
                            ["mcp", *sys.argv[1:]]
```

El paquete no tiene lógica: las opciones (`--allow-dir`, `--output-dir`,
`--allow-model`...) son las de `skforecast-ai mcp`. Hay que comprobar que el
`find` de setuptools de la raíz (`include = ["skforecast_ai*"]`) no lo mete
en el wheel de `skforecast-ai`.

1.2. **Crear `server.json` en la raíz**: esquema `2025-12-11`, nombre
`io.github.skforecast/skforecast-ai`, descripción de 100 caracteres como
máximo, repositorio, versión 0.4.0 y un paquete `pypi` con identificador
`skforecast-ai-mcp`, `runtimeHint` `uvx`, transporte `stdio` y `--allow-dir`
como argumento con nombre y obligatorio, para que el cliente lo pida.

1.3. **Test `tests/test_mcp_registry_distribution.py`**, hermano de
`test_plugin_distribution.py`: la versión del puente, su pin de
`skforecast-ai[mcp]`, la versión de `server.json` y la de su paquete son la
de `pyproject.toml`; el nombre de `server.json` es el de la línea `mcp-name`
del README del puente; la descripción no pasa de 100 caracteres.

1.4. **Test del puente**: `main()` pasa sus argumentos a `skforecast-ai mcp`
(con la app simulada, sin arrancar un servidor).

1.5. **Añadir a `/release-bump`** las tres referencias nuevas (versión y pin
del puente, las dos versiones de `server.json`) y el paso de publicar el
puente y la ficha.

1.6. **Documentar la release**: en `tools/README.md` o donde esté el
procedimiento, los comandos de la fase 2. Una fila en la tabla de `Layout` de
`AGENTS.md` para `packages/`.

1.7. **Comprobar en local antes de publicar nada**: construir el wheel del
puente, instalarlo en un entorno limpio con `uv` y arrancar
`skforecast-ai-mcp --allow-dir <dir>` hasta `initialize`;
`mcp-publisher validate` sobre `server.json`.

1.8. `/verify`, commit, y tras tu visto bueno push y PR contra `0.4.x`.

## Fase 2: publicar (tú, yo te doy los comandos)

2.1. **Hacer pública tu pertenencia a la organización `skforecast`** en
GitHub. Sin eso, `mcp-publisher` falla con un 403.

2.2. **Publicar `skforecast-ai-mcp` 0.4.0 en PyPI** (`python -m build` y
`twine upload` desde `packages/skforecast-ai-mcp/`). Comprobar en la página
del proyecto que el README lleva la línea `mcp-name`.

2.3. **Publicar la ficha**: instalar `mcp-publisher` (Homebrew o binario),
`mcp-publisher login github` con la cuenta que pertenece a la organización y
`mcp-publisher publish` desde la raíz.

2.4. **Verificar**:

- `curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=skforecast"`
  devuelve la ficha.
- `uvx skforecast-ai-mcp --allow-dir <dir>` arranca con la caché vacía; medir
  el primer arranque como en la fila del 2026-10-09 del log de
  `tools/mcp/README.md`.
- Instalar desde VS Code con la ficha del registro y hacer una llamada a
  `profile`. Es lo que no está comprobado: qué comando construye el cliente
  con `packageArguments`.
- Apuntar las cifras y lo visto en el log de `tools/mcp/README.md`.

2.5. **Según 2.4, cerrar A2**: si el comando corto arranca igual, la guía lo
nombra (yo, en otra rama `docs/`).

Estado, 2026-10-09: 2.1 y 2.2 hechos (`skforecast-ai-mcp` 0.4.0 en PyPI, con
la línea `mcp-name` en su descripción; `JavierEscobarOrtiz` es miembro
público de la organización). Queda añadir a Joaquín como Owner del puente
en PyPI y que él añada a Javier en `skforecast-ai`. 2.3 hecho: la ficha
`io.github.skforecast/skforecast-ai` 0.4.0 está publicada desde las 10:54
UTC. El paso 2.1 estaba mal planteado: el registro ya no mira la pertenencia
pública, sino el rol de Owner, y lo lee con un token que necesita
`read:org`; el login por navegador dio 403 dos veces y funcionó
`login github --token` con un token clásico de solo `read:org`
(`packages/README.md`). De 2.4, medido el arranque del comando corto (24 a
33 s en frío en cuatro arranques, igual que el del plugin; 1,2 s en
caliente), la API devuelve la ficha y el comando que un cliente construiría
con ella arranca; todo apuntado en el log de `tools/mcp/README.md`.
La instalación desde la ventana de VS Code no se puede probar: `@mcp
skforecast` no encuentra nada, porque su galería lee el GitHub MCP Registry
(394 servidores, una selección del oficial) y la ficha no está en él; queda
en el paso 3.5. A cambio, el README y la guía tienen un botón "Install in
VS Code" (enlace `vscode:mcp/install`), probado en VS Code 1.141.0: añade el
servidor, pide el directorio y arranca el comando corto. 2.5 hecho: la guía
nombra el comando corto en una nota de `Install`; el plugin no cambia (A2).

## Fase 3: directorios (en paralelo con las fases 1 y 2)

No dependen del puente ni del registro.

3.1. **Directorio de Anthropic** (llega a claude.ai, Cowork y Claude Code).
Yo: `claude plugin validate --strict ./plugin`, la lista de comprobación
previa de claude.com y la tabla de qué componentes cargan en cada app. Tú: el
envío en `claude.ai/directory/manage` (pide un plan de pago de claude.ai).

Estado, 2026-10-09, leída la lista de comprobación del portal
(`claude.com/docs/plugins/pre-submission-checklist`):

- **Bloqueaba**: la carpeta del plugin no tenía README (mínimo 40 palabras
  fuera de bloques de código). Añadido `plugin/README.md`, con lo que el
  plugin ejecuta, lee, escribe y descarga, que es lo que mira el escaneo de
  seguridad.
- **Cumple**: `license` en `plugin.json`, nombre propio, paquete fijado a una
  versión exacta, sin credenciales, repositorio de 4 MiB y 575 ficheros.
- **Dudoso, lo dirá el `Validate` del portal**: la lista pide que las rutas
  del comando de un servidor MCP salgan de `${CLAUDE_PLUGIN_ROOT}` "sin otra
  variable" cuando el plugin es una subcarpeta, y el nuestro pasa
  `${CLAUDE_PROJECT_DIR}` a `--allow-dir`; y el ejemplo de pin es
  `uvx <paquete>==1.2.3`, no `uvx --from "paquete[extra]==1.2.3"`. Si alguno
  bloquea, la salida es el comando corto: `uvx skforecast-ai-mcp==X.Y.Z`.
  Resuelto: el `Validate` bloqueó por `${CLAUDE_PROJECT_DIR}` ("Command path
  can't be followed"). Claude Code da esa variable en el entorno a los
  servidores de un plugin (comprobado con una sonda en 2.1.272 y 2.1.294),
  así que el servidor la lee él mismo con la opción nueva
  `--allow-project-dir` y el plugin arranca
  `uvx skforecast-ai-mcp==X.Y.Z --allow-project-dir`, sin ninguna ruta. Eso
  cierra A2 para el plugin y exige publicar una 0.4.1 antes de fusionar en
  `main`. Sin comprobar: Cowork y Windows.
  Enviado el 2026-10-09 con la 0.4.1 en `main`, desde la organización de
  claude.ai de la cuenta personal de Javier, que queda como dueña de la
  ficha. Dos decisiones del envío: publicación automática desactivada (hay
  que pulsar "Publish" en cada versión, tras comprobar que el lanzador está
  en PyPI) y comprobación programada sin webhook (cada 6 horas, o "Check
  for new commits"). Los pasos de cada release están en
  `packages/README.md`. Pendiente: el escaneo y la revisión de Anthropic.
- **Seguro**: un lanzador con paquete fijado siempre queda retenido para un
  revisor de Anthropic (`Runs a pinned npx or uvx package`). No es un
  rechazo.
- **Alcance**: el servidor local carga en Claude Code y en Cowork cuando la
  sesión corre en el ordenador del usuario; en el chat de claude.ai se
  ignora y solo carga el skill.
- El directorio lee una rama: la de por defecto, `main`, salvo que se le dé
  otra. El README tiene que estar en ella antes de enviar.

3.2. **Glama**. Tú: el formulario "Add MCP Server". Yo: los textos y revisar
qué pide su revisión (licencia y README ya están).

Estado, 2026-10-09: formulario enviado. Un repo de una organización solo se
reclama con un `glama.json` en la raíz que nombre a los mantenedores por su
usuario de GitHub: añadido, valida contra el esquema de Glama. Pendiente,
cuando esté en `main`: "Claim ownership" en la ficha y configurar cómo
arranca el servidor en su imagen Docker (necesita `--allow-dir`; ahí no
vale `--allow-project-dir`).

3.3. **awesome-mcp-servers**, después de 3.2: un PR de una línea en la
categoría que toque. Comprobar antes en su `CONTRIBUTING` si exige la ficha
de Glama (lo dice una guía de terceros, sin verificar).

Estado, 2026-10-09: sí la exige, aunque su `CONTRIBUTING` no lo diga. Un bot
(`glama-check`) comenta en cada PR que el servidor debe estar en Glama y
pasar sus comprobaciones (arrancar y responder a la introspección, con un
Dockerfile dado en Glama), y que la línea lleve la insignia
`[![OWNER/REPO MCP server](https://glama.ai/mcp/servers/OWNER/REPO/badges/score.svg)](https://glama.ai/mcp/servers/OWNER/REPO)`.
El PR espera a que la ficha de Glama exista y pase (3.2). Categoría: Data
Science Tools. Un agente que abre el PR añade `🤖🤖🤖` al final del título,
que además lo acelera.

3.4. **cursor.directory** (opcional): ficha autogestionada. Antes conviene
cerrar lo que el punto 18 de `dev/mcp-pending-after-0.4.0.md` deja sin probar
en Cursor.

3.5. **GitHub MCP Registry** (`github.com/mcp`): no hay vía de envío
documentada. Mirar una semana después de 2.3 si la ficha aparece sola.

## Fase 4: el canal propio

4.1. **Sección del servidor MCP en skforecast**: README y documentación del
repo `skforecast`, con enlace a la guía. Es la audiencia que ya existe.
Decidís vosotros dónde; yo redacto el texto.

Estado, 2026-10-09: texto propuesto, sin llevar todavía al repo
`skforecast`. Versión para el README, corta:

```markdown
### Use skforecast from your coding agent

[skforecast-ai](https://github.com/skforecast/skforecast-ai) brings
skforecast to coding agents such as Claude Code, Cursor or VS Code through
an [MCP server](https://ai.skforecast.org/stable/user-guides/mcp-server.html).
Ask in plain language ("Forecast the next 12 months of `data/sales.csv` and
tell me how accurate it is") and the agent profiles the file, plans a
forecaster, backtests it and forecasts. Every decision comes from
deterministic rules, not from the language model, and every result comes
with the skforecast script that produced it.

In Claude Code:

    /plugin marketplace add skforecast/skforecast-ai
    /plugin install skforecast-ai@skforecast-ai

With any other MCP client (it needs [uv](https://docs.astral.sh/uv/)):

    uvx skforecast-ai-mcp --allow-dir /absolute/path/to/project
```

Versión para la documentación: el mismo texto, más un párrafo con lo que el
servidor hace con los datos (solo lee los CSV del directorio permitido y
nunca devuelve filas al agente) y el enlace a la guía para el resto.

4.2. **Badge del registro en el README** de este repo, cuando la ficha esté
publicada.

Estado, 2026-10-09: hecho. El badge "MCP Registry" está en la fila
`Package`, junto al de "MCP server", y enlaza a la búsqueda de la web del
registro (`registry.modelcontextprotocol.io/?q=skforecast`): el registro no
tiene una página por ficha ni un badge propio.

4.3. **Revisión a los 14 días de 2.3**: en qué directorios aparece la ficha
sin haberla enviado (Glama, PulseMCP, Smithery, mcp.so) y enviar a mano solo
donde falte y merezca la pena.

## Lo que no está verificado

- Qué comando construyen VS Code y otros clientes a partir de la ficha
  (paso 2.4).
- Que el GitHub MCP Registry sincronice ya con el registro oficial.
- Qué directorios leen del registro: las fuentes se contradicen para Glama,
  PulseMCP y Smithery.
- Que awesome-mcp-servers exija la ficha de Glama.

## Fuentes

- Publicación: `docs/modelcontextprotocol-io/quickstart.mdx`,
  `package-types.mdx`, `versioning.mdx` y `github-actions.mdx` del repo
  `modelcontextprotocol/registry`.
- Esquema:
  `https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json`.
- Plugins: `https://code.claude.com/docs/en/plugins/publish`.
