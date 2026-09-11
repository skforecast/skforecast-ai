################################################################################
#                              llm: diagnostics                                #
#                                                                              #
# Static checks of an LLM configuration: how a provider string resolves,      #
# where credentials come from, what base_url means, installed extras.         #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

import importlib.util
import os

from ..schemas.results import LLMCheckResult
from .provider import (
    BEDROCK_CREDENTIAL_ENV_VARS,
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_REQUIRED_MODULES,
    PROVIDER_ENV_VARS,
    PROVIDER_REQUIRED_MODULES,
    PROVIDERS_IGNORING_BASE_URL,
    ensure_ollama_reachable,
    parse_model_string,
)

# pip extra that installs each module a provider may need.
_MODULE_EXTRAS: dict[str, str] = {
    "pydantic_ai": "skforecast-ai[llm]",
    "boto3": "skforecast-ai[bedrock]",
}


def _is_importable(module: str) -> bool:
    """
    Return whether a module can be imported, without importing it.

    Parameters
    ----------
    module : str
        Top-level module name, for example `'pydantic_ai'`.

    Returns
    -------
    importable : bool
        True when the module is installed.
    """
    return importlib.util.find_spec(module) is not None


def _missing_dependencies(provider: str | None) -> list[str]:
    """
    List the modules a provider needs that are not installed.

    Parameters
    ----------
    provider : str, None
        Provider prefix. None checks the base requirement only.

    Returns
    -------
    missing : list of str
        Entries formatted as `'<module> (pip install "<extra>")'`.
    """
    required = PROVIDER_REQUIRED_MODULES.get(provider, DEFAULT_REQUIRED_MODULES)
    return [
        f'{module} (pip install "{_MODULE_EXTRAS[module]}")'
        for module in required
        if not _is_importable(module)
    ]


def check_llm_config(
    llm: str,
    base_url: str | None = None,
    api_key: str | None = None,
) -> LLMCheckResult:
    """
    Check how an LLM configuration resolves, without calling the model.

    Mirrors the decisions `create_model()` takes so the report describes
    what the assistant would actually do: which provider and model the
    string names, where the credentials come from and whether the
    environment variable is set, what `base_url` means for the provider,
    whether the required modules are installed and, for Ollama, whether
    the server answers. Nothing is raised on a failed check; the first
    failure is reported in `error`. Credential values are never stored.

    Parameters
    ----------
    llm : str
        Provider string in the format `'provider:model_name'`.
    base_url : str, default None
        Custom endpoint, as given to `ForecastingAssistant`.
    api_key : str, default None
        Explicit API key, as given to `ForecastingAssistant`. Only its
        presence is recorded.

    Returns
    -------
    result : LLMCheckResult
        Outcome of every check. `result.ok` is True when none failed.
    """
    try:
        provider, model_name = parse_model_string(llm)
    except ValueError as exc:
        missing = _missing_dependencies(None)
        return LLMCheckResult(
            llm                  = llm,
            dependencies_ok      = not missing,
            missing_dependencies = missing,
            error                = str(exc),
        )

    result = LLMCheckResult(llm=llm, provider=provider, model_name=model_name)
    result = _check_credentials(result, provider, api_key)
    result = _check_base_url(result, provider, base_url, api_key)

    missing = _missing_dependencies(provider)
    result = result.model_copy(
        update={"dependencies_ok": not missing, "missing_dependencies": missing}
    )
    if missing and result.error is None:
        result = result.model_copy(
            update={"error": "Missing dependencies: " + ", ".join(missing)}
        )

    if provider == "ollama" and result.dependencies_ok:
        try:
            ensure_ollama_reachable(result.base_url)
            result = result.model_copy(update={"reachable": True})
        except ConnectionError as exc:
            result = result.model_copy(
                update={"reachable": False, "error": result.error or str(exc)}
            )

    return result


def _check_credentials(
    result: LLMCheckResult,
    provider: str,
    api_key: str | None,
) -> LLMCheckResult:
    """
    Fill the credential fields of a check result.

    Parameters
    ----------
    result : LLMCheckResult
        Result being built.
    provider : str
        Provider prefix.
    api_key : str, None
        Explicit API key, if any. Only its presence is used.

    Returns
    -------
    result : LLMCheckResult
        Copy with `credential_source`, `env_var`, `env_var_set`,
        `credential_note` and, on failure, `error` filled.
    """
    env_var = PROVIDER_ENV_VARS.get(provider)
    update: dict = {"env_var": env_var}

    if provider == "ollama":
        update["credential_source"] = "none"
        update["credential_note"] = (
            "Ollama needs no credentials; api_key is ignored."
        )
    elif api_key is not None:
        update["credential_source"] = "api_key"
        update["credential_note"] = "Explicit api_key given; the environment is not consulted."
    elif provider == "bedrock":
        aws_set = any(name in os.environ for name in BEDROCK_CREDENTIAL_ENV_VARS)
        update["credential_source"] = "aws_credential_chain"
        update["env_var_set"] = True if aws_set else None
        update["credential_note"] = (
            "Resolved by boto3: AWS_BEARER_TOKEN_BEDROCK, AWS_ACCESS_KEY_ID and "
            "AWS_SECRET_ACCESS_KEY, a profile, or an instance role."
        )
    elif env_var is not None:
        is_set = env_var in os.environ
        update["credential_source"] = "env_var"
        update["env_var_set"] = is_set
        update["credential_note"] = f"pydantic-ai reads {env_var}."
        if not is_set:
            update["error"] = (
                f"{env_var} is not set and no api_key was given."
            )
    else:
        update["credential_source"] = "unknown"
        update["credential_note"] = (
            f"'{provider}' is not a built-in provider. With base_url it is "
            "treated as an OpenAI-compatible endpoint; otherwise pydantic-ai "
            "resolves it (and its credentials) at call time."
        )

    return result.model_copy(update=update)


def _check_base_url(
    result: LLMCheckResult,
    provider: str,
    base_url: str | None,
    api_key: str | None,
) -> LLMCheckResult:
    """
    Fill the endpoint fields of a check result.

    Parameters
    ----------
    result : LLMCheckResult
        Result being built.
    provider : str
        Provider prefix.
    base_url : str, None
        Endpoint as given.
    api_key : str, None
        Explicit API key, if any.

    Returns
    -------
    result : LLMCheckResult
        Copy with `base_url` and `base_url_note` filled.
    """
    if provider == "ollama":
        effective = base_url or DEFAULT_OLLAMA_BASE_URL
        note = "Ollama server URL." if base_url else "Ollama server URL (default)."
    elif provider == "bedrock":
        effective = base_url
        note = (
            "AWS region." if base_url
            else "AWS region; AWS_DEFAULT_REGION or the AWS profile when None."
        )
    elif provider in PROVIDERS_IGNORING_BASE_URL:
        effective = None
        note = (
            f"base_url is ignored for '{provider}'; its client takes no endpoint."
            if base_url else None
        )
    elif base_url is not None:
        effective = base_url
        note = "OpenAI-compatible endpoint."
    elif provider == "openai":
        effective = None
        note = "Provider default (OPENAI_BASE_URL when set)."
    else:
        effective = None
        note = None

    return result.model_copy(update={"base_url": effective, "base_url_note": note})
