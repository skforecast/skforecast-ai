# Rediseño de la home de la documentación: pendientes

Rama: `docs-redesign_home_page`. Documento de trabajo para revisar y terminar la
nueva home de https://ai.skforecast.org desde el Mac con Claude Code. No forma
parte de la documentación: bórralo (o no lo incluyas) antes de abrir la PR.


## Prompt para Claude Code

Pega esto al empezar la sesión:

> Lee `dev/home-page-pending.md` y `tools/home_page/README.md`. Estamos
> terminando el rediseño de la home de la documentación en la rama
> `docs-redesign_home_page`. Sigue las tareas del documento en orden, marca
> cada casilla al terminarla y, en las que dicen "Decidir", pregúntame antes de
> cambiar nada. Respeta CLAUDE.md (entorno conda, sin commits, sin guiones
> largos).


## 0. Antes de nada: traer el trabajo al Mac

El trabajo está en GitHub, en la rama `docs-redesign_home_page`, con una PR
abierta contra `0.4.x` (sin mergear). La rama no puede llamarse
`docs/redesign_home_page`: ya existe una rama `docs` en el repositorio (la
que usa mike para publicar) y git no admite `docs` y `docs/...` a la vez.

```bash
git fetch origin docs-redesign_home_page
git switch docs-redesign_home_page
git log --oneline -5
```

- [ ] La rama existe en local y contiene los ficheros del mapa de abajo.


## Contexto

Nueva home con el estilo de la de skforecast 0.26.x (plantilla Material, CSS y
JS propios, datos generados). Es una animación en cuatro pasos (Profile, Plan,
Run, Ask) con **salidas reales** de skforecast-ai sobre `bike_sharing`.

- Pitch: "The forecasting assistant that shows its work". Tres mensajes, en
  este orden: una llamada de los datos al forecast; decisiones auditables (el
  script que se ejecutó); un LLM que explica y nunca decide.
- Código de color: naranja para el motor determinista, violeta para la capa
  LLM.
- El razonamiento completo y el mantenimiento están en
  `tools/home_page/README.md`.

### Mapa de ficheros

| Fichero | Estado | Qué es |
|:--|:--|:--|
| `docs/overrides/home.html` | nuevo | La página: secciones y textos |
| `docs/stylesheets/home.css` | nuevo | Estilos, todos bajo `.sk-home` |
| `docs/javascripts/home.js` | nuevo | Animación, leaderboard, script y snippets |
| `docs/overrides/partials/home-data.json` | nuevo, generado | Datos reales de la animación |
| `docs/overrides/partials/announce.html` | nuevo | Texto de la barra de avisos |
| `docs/img/social-card-home.png` | nuevo, generado | Imagen al compartir en redes (1200 x 630) |
| `tools/home_page/generate_home_data.py` | nuevo | Genera `home-data.json` |
| `tools/home_page/make_social_card.mjs` | nuevo | Genera la tarjeta social |
| `tools/home_page/social_card.html` | nuevo | Maqueta de la tarjeta social |
| `tools/home_page/README.md` | nuevo | Cómo funciona y cómo mantenerla |
| `docs/README.md` | modificado | Solo front matter `template: home.html` |
| `docs/overrides/main.html` | modificado | Bloque `announce` |
| `docs/stylesheets/extra.css` | modificado | Esquema `default` + `light` heredado, barra de avisos |
| `mkdocs.yml` | modificado | Ver tarea 7 |
| `docs/javascripts/mathjax.js` | borrado | No había fórmulas en ninguna página |
| `docs/releases/releases.md` | modificado | Entrada "Unreleased" |

### Qué se verificó en la nube (y qué no)

Verificado:

- `mkdocs build` sin avisos (con `validation` de enlaces y anclas activada).
- Capturas en claro, oscuro, móvil (400 px, sin scroll horizontal) y con
  movimiento reducido; navegación instantánea ida y vuelta.
- Enlaces naranja en los esquemas `default`, `slate` y el antiguo `light`.
- La barra de avisos se cierra y no reaparece al recargar.
- `ruff check skforecast_ai tests tools/home_page` limpio.
- `pytest -n auto`: 1356 pasan con `[llm]` instalado; 1 falla por falta del
  paquete `groq` en aquel entorno (ajeno a estos cambios).
- Los datos coinciden con el informe de `ask()`: MAE 45.8216, MASE 0.616892.

No verificado:

- Las fuentes reales (Poppins, Open Sans, Ubuntu Mono) en la página: el
  Chromium de la nube no podía descargar Google Fonts.
- `make_social_card.mjs` de principio a fin: la imagen se generó con un script
  equivalente de Playwright.
- El plugin `privacy` de Material (ver tarea 8).
- Entorno: skforecast 0.25.0, lightgbm 4.7.0, mkdocs 1.6.1,
  mkdocs-material 9.7.7, Python 3.11, en un venv (no había conda).


## Tareas

### 1. Entorno

Según CLAUDE.md: `conda env list` y preguntar qué entorno usar.

```bash
pip install -e ".[docs,llm]" lightgbm pytest pytest-xdist
node --version          # 22 o superior, para make_social_card.mjs
```

- [ ] Entorno elegido y dependencias instaladas.

### 2. Revisar el diff completo

```bash
git status
git diff
git diff --stat
```

- [ ] Leído el diff de `mkdocs.yml`, `extra.css`, `main.html` y
  `releases.md`, y los ficheros nuevos.

### 3. Revisar la home en el navegador

```bash
PYTHONPATH=. mkdocs serve
```

Abrir http://127.0.0.1:8000/ y comprobar:

- [ ] Modo claro y modo oscuro (botón de paleta de la cabecera).
- [ ] Con Ubuntu Mono real, los tres snippets de "One call, or every step in
  your hands" caben sin scroll horizontal (en la nube el de "Step by step" se
  cortaba, pero por la fuente de sustitución, más ancha). Si no caben, reducir
  `.sk-home .snip { font-size }` en `home.css` o partir líneas en `home.html`.
- [ ] Animación: los cuatro pasos se reproducen solos; pausa y play; clic en
  cada paso con la animación en marcha (reinicia el paso) y en pausa (lo
  muestra completo).
- [ ] Paso 1: arcos de los lags 25 y 169 y barras del PACF.
- [ ] Paso 2: zona "HELD OUT, 36 HOURS", corchetes de las ventanas móviles y
  las siete decisiones.
- [ ] Paso 3: forecast e intervalo; la franja inferior desplaza el script real
  completo.
- [ ] Paso 4: se escribe la respuesta de `ask()`.
- [ ] La leyenda "LightGBM forecast" no se sale por la derecha y el punto queda
  pegado al texto (se recoloca cuando carga Poppins).
- [ ] Leaderboard de `compare()`: las barras crecen al entrar en pantalla.
- [ ] Botones de copiar (pip install y script).
- [ ] Ir a otra página y volver: la animación se reinicia y la consola no
  muestra errores de `home.js`. (Los errores "Failed to construct 'URL'" del
  selector de versiones de mike salen en local también en `main`; se pueden
  ignorar.)
- [ ] Ancho de móvil (unos 400 px, herramientas de desarrollo): sin scroll
  horizontal de la página.
- [ ] Movimiento reducido activado en macOS (Ajustes, Accesibilidad,
  Pantalla, Reducir movimiento): se ve el último paso completo, sin animar.

### 4. Revisar los textos de la home (Decidir)

- [ ] Titular, entradilla y los tres mensajes: ¿es así como queremos vender el
  paquete?
- [ ] "Grounded in the skforecast agent skills, not in the model's memory"
  (tarjeta "The LLM explains"): las skills se envían al modelo, pero decir que
  no usa su memoria es tajante. Alternativa: "Grounded in the skforecast agent
  skills sent with every question."
- [ ] "Your dataset is never sent: profiles carry summary statistics, and a
  result passed to `ask()` only its own predictions and metrics, with a
  warning." Se corrigió en la nube (antes decía "only summary statistics", que
  era falso para los resultados; ver principio 4 de CLAUDE.md). Confirmar la
  redacción.
- [ ] "Runs fully offline, the LLM is optional" (fila de confianza): es cierto
  para `profile`, `plan`, `forecast`, `backtest` y `compare` con datos locales.
- [ ] Lista de proveedores ("Works with"): coincide con la tabla de
  `docs/user-guides/llm-configuration.md`.
- [ ] Nota "How this animation was made" bajo la animación.

### 5. Regenerar los datos y comprobar que no cambian

Necesita red (descarga `bike_sharing`) y `lightgbm`.

```bash
python tools/home_page/generate_home_data.py
git diff --stat docs/overrides/partials/home-data.json
```

- [ ] El script termina sin el error de la comprobación del MASE.
- [ ] `home-data.json` no cambia, o los cambios se entienden.

Si el MASE ya no es 0.616892 (por ejemplo con otra versión de skforecast o de
lightgbm), la respuesta de `ask()` citada en el paso 4 dejaría de corresponder
a los resultados. Opciones: fijar las versiones con las que se genera, o
relanzar `tools/ask_context_check.py --dataset bike_sharing` con un modelo
real (cuesta dinero), guardar el informe revisado según
`tools/ask_context_reports/README.md` y actualizar en `home.html` la
respuesta, el enlace al informe de la nota bajo la animación y `QUOTED_MASE`
en el generador.

### 6. Tarjeta social

Con `mkdocs serve` en marcha:

```bash
node tools/home_page/make_social_card.mjs
open docs/img/social-card-home.png
```

- [ ] El script corre de principio a fin (Chrome en la ruta por defecto de
  macOS; si no, `CHROME_PATH=...`).
- [ ] La imagen muestra la cabecera con el logo, el titular en Poppins y el
  paso 4 de la animación (forecast y respuesta de `ask()`).
- [ ] Decidir si también queremos una imagen para el README de GitHub, como
  hace skforecast con `images/skforecast-backtesting-comparison.png` (ahora el
  README usa el banner).

### 7. `mkdocs.yml` y estilos (ya aplicado, confirmar)

Cambios alineados con skforecast 0.26.x:

- `site_name: skforecast-ai Docs` (antes `skforecast-AI Docs`).
- `copyright: Copyright &copy; 2026-present ...`. El año sale del primer commit
  del repositorio (29-04-2026).
- `scheme: default` en vez de `light`. `extra.css` mantiene también `light`
  para los visitantes que lo tienen guardado en el navegador.
- `primary: custom` y `accent: custom`: sin esto Material aplicaba indigo y los
  enlaces salían azules en modo oscuro.
- `validation` de enlaces y anclas como avisos.
- Separador de búsqueda de skforecast (parte por mayúsculas, respeta `0.3.1`).
- `announce.dismiss` y barra de avisos.
- Fuera `pymdownx.arithmatex`, MathJax 3 desde unpkg y el fence de mermaid:
  no se usaban.
- mike: fuera las opciones que tenían su valor por defecto.
- `exclude_docs: /overrides/` y `javascripts/home.js`.
- Discord en los iconos sociales.

Decidir:

- [ ] Año del copyright: 2026, salvo que el proyecto empezara antes en otro
  repositorio.
- [ ] Texto de `docs/overrides/partials/announce.html` (inventado siguiendo el
  de skforecast). No lleva el emoji de skforecast porque CLAUDE.md prohíbe
  emojis en el código; añadirlo si se quiere.
- [ ] Color de los enlaces en modo claro: skforecast usa `#b35e07` para tener
  contraste 4.5:1 sobre blanco (WCAG AA); el naranja `#f79939` solo da 2.2:1.
  Si se quiere igualar, es `--md-typeset-a-color` del bloque `default` de
  `extra.css`.

### 8. Plugin `privacy` de Material (Decidir)

skforecast lo usa para servir Google Fonts y los scripts externos desde el
propio sitio y no conectar con terceros antes de aceptar las cookies (RGPD).
En la nube el build fallaba porque el proxy bloqueaba unpkg.com y los avatares
`github.com/*.png` de la página About. Probar en el Mac:

```yaml
  - privacy:
      assets_exclude:
        - cdn.plot.ly/*
        - cdnjs.cloudflare.com/ajax/libs/mathjax/*
        - img.shields.io/*
        - zenodo.org/badge/*
```

(después de `search` en `plugins`)

- [ ] `mkdocs build` termina sin errores.
- [ ] La home, los notebooks (Plotly y widgets) y la página About se ven bien.
- [ ] Añadir `.cache/` al `.gitignore` (el plugin descarga ahí).
- [ ] Si funciona, quitar la tarea de `tools/home_page/README.md` y añadirlo a
  la entrada de `releases.md`.

### 9. Contenido que desaparece de la web (Decidir)

`docs/README.md` ahora solo selecciona la plantilla. Lo que tenía (badges,
instalación, quickstart en Python y CLI, diagramas de "How it works" con
`compare()` y `ask()`, citación) ya no sale en la web; sigue en el README de
GitHub.

- [ ] Confirmar que no se echa en falta, o mover lo útil (por ejemplo los
  diagramas de "How it works") a la guía de usuario.

### 10. Tests y lint

```bash
ruff check skforecast_ai tests tools/home_page
pytest -n auto
PYTHONPATH=. mkdocs build -q -d /tmp/site
```

- [ ] Todo limpio.

### 11. Commit y PR

- [ ] Borrar este fichero (`dev/home-page-pending.md`) o dejarlo fuera del
  commit.
- [ ] Revisar la entrada "Unreleased" de `docs/releases/releases.md` y ponerle
  la versión que toque.
- [ ] Los cambios nuevos van a la misma rama; la PR contra `0.4.x` ya está abierta.

### 12. Después del despliegue

- [ ] https://ai.skforecast.org/stable/ muestra la nueva home.
- [ ] https://ai.skforecast.org/stable/img/social-card-home.png existe (las
  etiquetas Open Graph apuntan ahí; el alias que despliega mike es `stable`, no
  `latest` como en skforecast).
- [ ] La vista previa en LinkedIn (Post Inspector) y en Slack muestra la
  tarjeta.
- [ ] Opcional: enlazar la nueva home desde la sección de skforecast-ai de la
  home de skforecast.
