# MCP: lo que queda después de la 0.4.0

Lo que el check del MCP con un agente real (`tools/mcp/README.md`) dejó
abierto al cerrar la 0.4.0, por prioridad. Sustituye a
`dev/mcp-agent-check-findings-0.4.0.md`, el cuaderno de trabajo de esos
hallazgos, que ya está implementado.

Dónde está lo demás:

- **Qué se encontró, qué se arregló y con qué tasa**: el log de
  `tools/mcp/README.md` y los informes de `tools/mcp/agent_reports/`
  (`0.4.0-final` y `0.4.0-final2`, cada uno con su `-haiku`).
- **El cuaderno completo** (fichas de cada hallazgo, redacción final de cada
  hint con las muestras que la respaldan, decisiones de cada fase): en el
  historial, `git show 3098b6d:dev/mcp-agent-check-findings-0.4.0.md`.
- **El diseño del check**: `dev/mcp-agent-check-plan.md`.

## Códigos que cita el log

| Código | Hallazgo | Estado al publicar |
|:--|:--|:--|
| H1 | `forecast` sin exógenas futuras: el agente las escribe | arreglado |
| H2 | Copia de un fichero de fuera del directorio permitido | arreglado con el modelo grande; aceptado con el pequeño |
| H3 | El error de un valor ausente ordenaba rellenar | arreglado |
| H4 | Un hold-out presentado como el futuro | arreglado |
| H5 | `model_not_allowed` sin la licencia del modelo por defecto | arreglado |
| H6 | La pregunta de privacidad sin el skill | arreglado |
| H7 | MAPE leído 100 veces más pequeño | arreglado |
| H8 | Horizonte acortado sin preguntar | arreglado |
| H9 | `profile` con un target falso para leer las columnas | arreglado |
| H10 | El resumen de `compare` y el baseline | pendiente, punto 2 |
| H11 | La precisión de un plan dada para el forecast de otro | pendiente, punto 4 |
| C1 a C5 | Mejoras del propio check | hechas |

## Pendiente, por prioridad

### Bloquea la versión siguiente

1. **`compare` sobre la estrategia de un plan refinado no evalúa ese plan.**
   Aceptado para la 0.4.0 con su fila en el log. Caso mínimo y causa, abajo.
   Lo correcto: que el plan de la estrategia entre como candidato cuando
   difiere del recomendado. Cambia qué ejecuta `compare`, su coste (los
   números de `CostNotice` y `CompareCostNotice`), los goldens y el texto que
   lee `ask()`: lleva `/llm-context-change` y su check de pago. Alternativa
   más ligera, solo en el servidor: un aviso en `compare` que diga que ese
   plan no entra y cómo incluirlo.
2. **H10, el resumen de `compare` y el baseline.** Dice cuántas
   configuraciones no baten al baseline, no cuántas sí, y algún agente escribe
   que el ganador es "el único que lo bate". Mismo fichero
   (`execution/comparison.py`) y mismo check de pago que el punto 1: hacerlos
   juntos.

### Mejoras del servidor

3. **Confirmación explícita por encima del umbral de coste** en `backtest` y
   `compare`. El `CostNotice` para al modelo grande (6 de 6) y no al pequeño
   (12 de 12 lanza con el aviso leído). Es un cambio de API.
4. **H11**: un aviso en `forecast` cuando su plan no se midió en la sesión.
   Solo con el modelo pequeño (2 de 6); cubre también el forecast sin ninguna
   medida.
5. **Aviso cuando el estimador no es el recomendado**, en `backtest` y
   `forecast`, para que el agente diga que lo cambió. El modelo pequeño lo
   cambia tras el `MissingValuesNotice` y no lo dice en la respuesta final (5
   de 5).
6. **`root_mean_squared_error` como métrica del servidor.** Hoy no se ofrece,
   y los agentes lo derivan del MSE (4 de 6 en `expensive_run`).
7. **El resumen de un forecast con `test_size`** (H4) no dice con palabras
   que es una evaluación. El aviso del servidor lo cubre; el texto vive en
   `llm/context.py` y va por `/llm-context-change`.
8. **Un solo texto para `MissingValuesNotice` y `DATA_VALUES_HINT`**, y el
   `'LGBMRegressor'` escrito a mano en los dos y en el aviso de la librería:
   son tres copias de la misma regla.
9. **`profile` sin `target` cuando el usuario ya nombró la columna.** Cuesta
   una llamada (9 de 81 con el modelo grande). Con el pequeño, una sesión se
   saltó así el error de la columna inexistente y la sustituyó sin decirlo.

### Defectos vistos en la revisión de código

10. `warn_backtest_missing_values` (`create_cv`) no avisa con un estimador
    que acepta valores ausentes y `differentiation`, y `backtest` rechaza
    después porque la inversa de la diferenciación lee un valor ausente.
11. `get_code` calcula `requirements` en el event loop (la primera llamada
    recorre todas las distribuciones instaladas) y añade el backend del
    modelo foundation al script de una estrategia, que no carga ningún modelo.
12. El guard de Bash (`.claude/hooks/pre_bash_guard.py`) resuelve la rama
    desde `CLAUDE_PROJECT_DIR` antes que desde el `cwd` de la llamada: en un
    worktree comprueba la rama del checkout principal.
13. `FutureExogNotice` nombra todas las exógenas del perfil, también las
    categóricas que un modelo foundation descartaría. Hoy no se alcanza.

### El propio check

14. **Tests unitarios de `tools/mcp/check_mcp_agent.py`.** No tiene ninguno,
    y casi todos los defectos de las dos revisiones de código estaban en sus
    heurísticas (redirecciones, fallos falsos, herramientas que se escapaban).
15. **Enmascarar el directorio personal y el usuario del sistema** en lo que
    renderiza el informe, como ya hace con el workspace. Hoy aparecen en
    salidas de `ls -la`, y una ruta se quitó a mano de un informe: un
    `--report-only` la devolvería.
16. Una sesión puede cargar los skills de fábrica de Claude Code con `Skill`.
17. El `WARN` de H11 da un aviso en falso cuando el plan se reconstruye igual
    con un intervalo (está anotado en el README).

### Comprobaciones a mano

18. Lo que el README lista como no cubierto. Comprobado el 2026-10-09 con la
    0.4.0 de PyPI y el marketplace de `main`; las cifras, en la fila de ese
    día del log de `tools/mcp/README.md`.
    - **Hecho**: primer arranque con `uvx` (27,8 s hasta `initialize` con
      la caché vacía; 1,2 a 1,3 s en caliente), `MCP_TIMEOUT` de Claude Code
      (30 s por defecto, medido), el plugin del marketplace con una llamada
      real a `profile` desde una sesión, `npx skills add` (instala la copia
      del plugin, sin conflicto) y Claude Desktop por su log (25,2 s en
      frío, 1,2 s en caliente).
    - **Sin probar**: Cursor y Codex (no están instalados en la máquina) y
      VS Code. Siguen sin comprobar el formato de `~/.codex/config.toml` y
      de `codex mcp add`, los timeouts de arranque de los tres y si Cursor
      interpola `${workspaceFolder}`. De Claude Desktop, su timeout de
      arranque (no se alcanzó), lo que muestra la ventana y una llamada
      desde un chat. De Claude Code, los comandos `/plugin` tecleados en
      una sesión interactiva (se usaron `claude plugin marketplace add` y
      `claude plugin install`).
    - **En la guía** (`docs/user-guides/mcp-server.md`), aplicado: el
      primer arranque son unos 30 s con buena conexión, no un minuto, y en
      Claude Code cabe en el timeout por 2 s, así que el warm up nombra
      `MCP_TIMEOUT`, y Troubleshooting también; tras el warm up, el primer
      arranque del servidor tarda hasta 10 s y los siguientes unos 2; una
      fila de Troubleshooting dice que Claude Desktop arranca el servidor
      dos veces y mantiene los dos procesos hasta que se cierra.
    - **Visto de paso**: `npx skills add skforecast/skforecast-ai --list`
      enseña también los 7 skills de `.claude/skills/`, que son de los
      mantenedores.
19. El hallazgo 4 del piloto (intervalos con cotas iguales), arreglado en
    `96f4cdc`. Ejercitado el 2026-10-09 con llamadas directas al servidor
    publicado: `create_cv` con `initial_train_size=28` para un plan con
    intervalo y una ventana de 24 devuelve el aviso (4 residuos), y 60 de
    las 68 filas del backtest tienen las dos cotas iguales. La respuesta de
    `backtest` no lo repite. Queda por ver, con un escenario del check de
    pago, si un agente lee el aviso y lo cuenta.

## `compare` sobre un plan refinado: caso mínimo

Con la API de Python sobre `h2o` (`x`, 12 pasos):

```python
profile = assistant.profile(data, target="x")
plan    = assistant.plan(profile=profile, steps=12)        # Recursive + Ridge
refined = assistant.refine_plan(
    profile=profile, plan=plan, estimator="LGBMRegressor", lags=[1, 2, 3, 12]
)
cv = assistant.create_cv(profile=profile, plan=refined)
assistant.backtest(data, cv=cv, profile=profile, plan=refined)   # MAE 0.082949
assistant.compare(data, cv=cv, profile=profile)                  # sin candidates
```

La tabla de `compare`: ForecasterFoundation 0.057007, ForecasterRecursive
con **Ridge** 0.061982, ForecasterStats 0.063818, baseline 0.066072,
ForecasterDirect con Ridge 0.076281. La fila `ForecasterRecursive` es el plan
recomendado del perfil, no el refinado, que no está en la tabla. Pasado como
candidato explícito da 0.082949, el último, por debajo del baseline.

La causa: `resolve_compare_candidates` (`execution/comparison.py`) construye
los candidatos por defecto desde `profile.forecaster_candidates` con solo el
nombre del forecaster, y del plan de la estrategia `compare` solo hereda el
intervalo y la métrica. El estimador, los lags y las window features que el
usuario fijó se pierden sin aviso, y el resumen añade `The strategy was
created for the plan (ForecasterRecursive + LGBMRegressor)`, que invita a leer
la fila como ese plan.

En las trazas: 7 sesiones en `0.4.0-final` y 6 en `0.4.0-final2` lo llaman
así tras cambiar a LGBMRegressor por los valores ausentes; 3 de esas 6 dan una
fila ajena por la suya y 1 lo lee bien. Ninguna da un ganador equivocado: el
daño es una comparación que no contiene el plan que el usuario cree comparar.
Mientras no se arregle, pasar el plan refinado en `candidates` funciona.
