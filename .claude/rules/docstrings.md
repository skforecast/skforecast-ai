---
paths:
  - "skforecast_ai/**/*.py"
---

# Docstrings

Every public class, method and function has a NumPy-style docstring that
follows `.github/instructions/docstrings.instructions.md` (shared with
skforecast). Read it before writing a new public API. The essentials:

- Single backticks for code, readable type names (`pandas DataFrame`,
  `list of str`), `name : type, default value`.
- Sections in the documented order: Summary, Parameters, Attributes
  (classes only), Returns, Notes, References. Omit what does not apply.
- Read the neighbouring docstrings first and match their style; do not
  reformat text you are not changing.
- Line length 88 (ruff `max-doc-length`), no en dashes or em dashes.
- Private helpers get a short docstring when the why is not obvious.
