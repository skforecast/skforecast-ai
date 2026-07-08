## Code Style

- NumPy-style docstrings
- Type hints for function signatures
- PEP 8 compliant (max line length 88, enforced by ruff)
- Double quotes for strings (ruff `quote-style = "double"`)
- Relative imports within package
- When generating code comments, docstrings, and documentation, do not use en dashes (–), or em dashes (—). Use commas, colons, semicolons, or parentheses for punctuation instead.

## Python environment

Before running any Python command (tests, scripts, notebooks, `pip install`, etc.)
for the first time in a session, run `conda env list` and ask which environment to
use. Do not assume the active environment. Once the user confirms an environment,
reuse it for the rest of the session without asking again.