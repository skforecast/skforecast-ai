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

## Fase 3: directorios (en paralelo con las fases 1 y 2)

No dependen del puente ni del registro.

3.1. **Directorio de Anthropic** (llega a claude.ai, Cowork y Claude Code).
Yo: `claude plugin validate --strict ./plugin`, la lista de comprobación
previa de claude.com y la tabla de qué componentes cargan en cada app. Tú: el
envío en `claude.ai/directory/manage` (pide un plan de pago de claude.ai).

3.2. **Glama**. Tú: el formulario "Add MCP Server". Yo: los textos y revisar
qué pide su revisión (licencia y README ya están).

3.3. **awesome-mcp-servers**, después de 3.2: un PR de una línea en la
categoría que toque. Comprobar antes en su `CONTRIBUTING` si exige la ficha
de Glama (lo dice una guía de terceros, sin verificar).

3.4. **cursor.directory** (opcional): ficha autogestionada. Antes conviene
cerrar lo que el punto 18 de `dev/mcp-pending-after-0.4.0.md` deja sin probar
en Cursor.

3.5. **GitHub MCP Registry** (`github.com/mcp`): no hay vía de envío
documentada. Mirar una semana después de 2.3 si la ficha aparece sola.

## Fase 4: el canal propio

4.1. **Sección del servidor MCP en skforecast**: README y documentación del
repo `skforecast`, con enlace a la guía. Es la audiencia que ya existe.
Decidís vosotros dónde; yo redacto el texto.

4.2. **Badge del registro en el README** de este repo, cuando la ficha esté
publicada.

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
