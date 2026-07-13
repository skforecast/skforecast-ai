################################################################################
#                               Config                                         #
#                                                                              #
# Persistent configuration for skforecast-ai CLI                               #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import os
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

CONFIG_DIR: Path = (
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "skforecast-ai"
)
CONFIG_FILE: Path = CONFIG_DIR / "config.toml"

VALID_KEYS: set[str] = {
    "llm.provider",
    "llm.base_url",
    "llm.api_key",
    "llm.send_data_to_llm",
    "output.format",
}


def load_config() -> dict:
    """
    Read the config TOML file; return empty dict if missing.

    Returns
    -------
    config : dict
        Parsed configuration dictionary.
    """
    if not CONFIG_FILE.is_file():
        return {}
    with open(CONFIG_FILE, "rb") as f:
        return tomllib.load(f)


def save_config(config: dict) -> None:
    """
    Write config dict to TOML file, creating directories as needed.

    Parameters
    ----------
    config : dict
        Configuration dictionary with section keys mapping to value dicts.

    Returns
    -------
    None
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = []
    for section, values in sorted(config.items()):
        if not isinstance(values, dict):
            continue
        lines.append(f"[{section}]")
        for key, val in sorted(values.items()):
            if isinstance(val, bool):
                lines.append(f"{key} = {str(val).lower()}")
            elif isinstance(val, str):
                escaped = val.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{key} = "{escaped}"')
            else:
                lines.append(f"{key} = {val}")
        lines.append("")
    CONFIG_FILE.write_text("\n".join(lines))
    CONFIG_FILE.chmod(0o600)


def get_config_value(key: str) -> str | None:
    """
    Get a config value by dot-notation key (e.g. `'llm.provider'`).

    Parameters
    ----------
    key : str
        Dot-notation key (e.g. `'llm.provider'`).

    Returns
    -------
    value : str, None
        Config value as string, or None if not found.
    """
    parts = key.split(".", 1)
    if len(parts) != 2:
        return None
    config = load_config()
    section = config.get(parts[0], {})
    val = section.get(parts[1])
    if val is None:
        return None
    return str(val)


def set_config_value(key: str, value: str) -> None:
    """
    Set a config value by dot-notation key and persist.

    Parameters
    ----------
    key : str
        Dot-notation key (e.g. `'llm.provider'`). Must be in `VALID_KEYS`.
    value : str
        Value to set. Boolean strings (`'true'`, `'false'`) are stored as
        booleans.

    Returns
    -------
    None
    """
    if key not in VALID_KEYS:
        raise ValueError(
            f"Unknown config key: '{key}'. "
            f"Valid keys: {', '.join(sorted(VALID_KEYS))}"
        )
    parts = key.split(".", 1)
    config = load_config()
    if parts[0] not in config:
        config[parts[0]] = {}
    if value.lower() in ("true", "false"):
        config[parts[0]][parts[1]] = value.lower() == "true"
    else:
        config[parts[0]][parts[1]] = value
    save_config(config)
