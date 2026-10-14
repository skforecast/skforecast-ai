# Tools

Development scripts and notebooks. They are not part of the skforecast-ai
package.

| Path | Purpose |
|:-----|:--------|
| [`ai/`](ai/) | Syncs the AI assets from skforecast and checks the context sent to the LLM. See its README. |
| [`docs/`](docs/) | Scripts and notebooks used to build and maintain the documentation (see below). |
| [`mcp/`](mcp/) | Checks the MCP server with a real agent (headless Claude Code sessions) and keeps one reviewed report per release. Manual, pre-release. See its README. |
| [`perf/`](perf/) | Parity and timing scripts for performance and cleanup changes. See its README. |

## docs/

| Path | Purpose |
|:-----|:--------|
| [`home_page/`](docs/home_page/) | Generates the data and social card of the documentation home page, the data of the animations in `docs/animations/` and the GIF of a real agent session. See its README. |
| [`how_it_works/`](docs/how_it_works/) | Generates the light and dark "How it works" diagram of the README and the user guides. |
| [`hooks/`](docs/hooks/) | MkDocs hooks, loaded from `mkdocs.yml`. `page_meta.yml` holds the search engine title and description of every page; `python tools/docs/hooks/page_meta.py` checks them (CI runs it on pull requests that touch the docs). |
| `robots.txt` | robots.txt of the site, with the sitemap of the stable release. Copied by hand to the root of the branch that Netlify publishes. |
| `check_release_notes.py` | Reports, for the version in development of `docs/releases/releases.md`, the undefined link references, the entries over the length ceiling and those without a pull request link. Used by the `release-note` skill. |
| `check_published_links.ipynb` | Crawls the published website and reports broken links. |
