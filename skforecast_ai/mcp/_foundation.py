################################################################################
#                       MCP server foundation models                           #
#                                                                              #
# Which foundation models the server runs and what it says about their weights #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import os
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from skforecast.foundation import FoundationModelInfo, list_adapters
from .._constants import DEFAULT_FOUNDATION_MODEL_ID, FORECASTER_TASK_TYPES
from .._foundation import foundation_backend_installed, resolve_foundation_model
from ..exceptions import InvalidInputError
from ._errors import ServerError
from .models import ToolNotice

# Category of the notice that a model will download its weights: a notice of
# the server, not a Python warning.
MODEL_DOWNLOAD_NOTICE = "ModelDownloadNotice"

# Values of HF_HUB_OFFLINE that huggingface_hub reads as true.
_TRUE_VALUES = frozenset({"1", "on", "yes", "true"})


# Adapters of skforecast whose models the server runs by default: those
# whose license was checked to allow any use when this list was written.
# skforecast registers a license restriction only when it knows of one
# (None "does not confirm that the license permits commercial use"), so an
# adapter added by a later skforecast is not run until it is reviewed and
# added here; meanwhile it needs `--allow-model`, like a restricted one.
REVIEWED_ADAPTERS = frozenset({
    "ChronosAdapter",
    "TimesFM25Adapter",
    "TabICLAdapter",
    "NoriAdapter",
})


def is_permissive(info: FoundationModelInfo) -> bool:
    """
    Whether the server runs a foundation model without `--allow-model`:
    its adapter is one of `REVIEWED_ADAPTERS`, and skforecast registers
    neither a license restriction nor gated weights for the model.

    Parameters
    ----------
    info : FoundationModelInfo
        Capabilities of the model.

    Returns
    -------
    permissive : bool
        Whether the server runs it without `--allow-model`.
    """

    return (
        info.adapter in REVIEWED_ADAPTERS
        and info.license_restriction is None
        and not info.requires_hf_auth
    )


def permissive_adapters() -> list[FoundationModelInfo]:
    """
    Adapters of skforecast whose models the server runs by default, read
    from the information skforecast registers for each one.

    Returns
    -------
    adapters : list of FoundationModelInfo
        Adapters without a license restriction or gated weights, in the
        order of skforecast.
    """

    return [info for info in list_adapters() if is_permissive(info)]


def restricted_adapters() -> list[FoundationModelInfo]:
    """
    Adapters of skforecast whose models need `--allow-model`.

    Returns
    -------
    adapters : list of FoundationModelInfo
        Adapters with a license restriction or gated weights, in the order
        of skforecast.
    """

    return [info for info in list_adapters() if not is_permissive(info)]


def check_allow_models(prefixes: Iterable[str]) -> tuple[str, ...]:
    """
    Check the prefixes given to `--allow-model`.

    A prefix must start with the model ID prefix of an adapter of
    skforecast (`'google/timesfm-3.0'`, or a longer one such as a whole
    model ID), so it never allows more than one family of models.

    Parameters
    ----------
    prefixes : iterable of str
        Prefixes as given.

    Returns
    -------
    prefixes : tuple of str
        The same prefixes, without repetitions, in the order given.
    """

    known = [
        prefix for info in list_adapters() for prefix in info.model_id_prefixes
    ]
    checked: list[str] = []
    for prefix in prefixes:
        if not isinstance(prefix, str) or not any(
            prefix.startswith(adapter) for adapter in known
        ):
            raise InvalidInputError(
                f"`--allow-model {prefix}` does not start with the model ID "
                f"prefix of a foundation model of skforecast. Prefixes: "
                f"{known}.",
                field = "allow_model",
            )
        if prefix not in checked:
            checked.append(prefix)

    return tuple(checked)


def _license_text(info: FoundationModelInfo) -> str:
    """
    The license of a model as skforecast registers it.
    """

    if info.license_restriction is None and info.adapter not in REVIEWED_ADAPTERS:
        text = (
            "its license has not been reviewed for this server (skforecast "
            "registers no restriction for it, which does not confirm that it "
            "permits every use)"
        )
    elif info.license_restriction is None:
        text = "skforecast registers no license restriction for it"
    else:
        text = f"its license is {info.license_restriction}"
        if info.license_url is not None:
            text += f" ({info.license_url})"
    if info.requires_hf_auth:
        text += (
            "; its weights are gated on the Hugging Face Hub and need a login "
            "with an account that accepted the license"
        )

    return text


def hf_hub_cache() -> str:
    """
    Directory of the local cache of Hugging Face, resolved as
    `huggingface_hub` resolves it, without importing it.

    Returns
    -------
    path : str
        `HF_HUB_CACHE`, else `HUGGINGFACE_HUB_CACHE`, else `hub` under
        `HF_HOME` (by default `~/.cache/huggingface`, or under
        `XDG_CACHE_HOME`).
    """

    home = os.getenv(
        "HF_HOME",
        os.path.join(os.getenv("XDG_CACHE_HOME", "~/.cache"), "huggingface"),
    )
    default = os.path.join(os.path.expanduser(home), "hub")

    return os.path.expanduser(
        os.getenv("HF_HUB_CACHE", os.getenv("HUGGINGFACE_HUB_CACHE", default))
    )


def weights_cached(model_id: str) -> bool:
    """
    Whether the local cache of Hugging Face holds a snapshot of a model
    repository.

    Parameters
    ----------
    model_id : str
        Hugging Face model ID, `'owner/name'`.

    Returns
    -------
    cached : bool
        Whether `models--owner--name/snapshots` of the cache holds at least
        one snapshot with a file in it (an interrupted download leaves an
        empty snapshot).
    """

    folder = "models--" + model_id.replace("/", "--")
    snapshots = os.path.join(hf_hub_cache(), folder, "snapshots")
    try:
        with os.scandir(snapshots) as entries:
            for entry in entries:
                if not entry.is_dir():
                    continue
                with os.scandir(entry.path) as files:
                    if any(True for _ in files):
                        return True
    except (OSError, ValueError):
        # ValueError: a model ID with a NUL byte, which no cache holds.
        return False

    return False


@dataclass
class ModelPolicy:
    """
    Foundation models a server runs, and the models whose download it
    already announced.

    Attributes
    ----------
    allowed_prefixes : tuple of str
        Prefixes given to `--allow-model`: models with a license
        restriction or gated weights whose ID starts with one of them run.
    announced : set of str
        Model IDs whose download a notice already announced.
    lock : threading.Lock
        Guards `announced`.
    """

    allowed_prefixes: tuple[str, ...] = ()
    announced: set[str] = field(default_factory=set)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def model_of(self, forecaster: str | None, estimator: str | None) -> str | None:
        """
        Model ID a plan or a candidate runs, if it is a foundation one.

        Parameters
        ----------
        forecaster : str, None
            Forecaster of the plan or the candidate.
        estimator : str, None
            Its estimator; None for the default foundation model.

        Returns
        -------
        model_id : str, None
            The model ID, or None when the forecaster is not
            `ForecasterFoundation`.
        """

        if FORECASTER_TASK_TYPES.get(forecaster) != "foundation":
            return None

        return estimator if estimator is not None else DEFAULT_FOUNDATION_MODEL_ID

    def check(self, model_id: str | None, argument: str) -> None:
        """
        Reject a foundation model with a license restriction or gated
        weights that `--allow-model` does not allow.

        A model ID that skforecast does not serve is left to the core,
        which reports it (or ranks the candidate last in a comparison).

        Parameters
        ----------
        model_id : str, None
            Model ID of the plan or the candidate; None does nothing.
        argument : str
            Argument of the tool that names it.

        Returns
        -------
        None
        """

        if model_id is None:
            return
        try:
            info = resolve_foundation_model(model_id)
        except InvalidInputError:
            return
        if is_permissive(info) or any(
            model_id.startswith(prefix) for prefix in self.allowed_prefixes
        ):
            return
        prefix = next(
            (p for p in info.model_id_prefixes if model_id.startswith(p)),
            info.model_id_prefixes[0],
        )
        raise ServerError(
            f"The server does not run '{model_id}': {_license_text(info)}. "
            f"Foundation models with a license restriction or gated weights "
            f"only run when the server is started with `--allow-model`.",
            code    = "model_not_allowed",
            field   = argument,
            hint    = (
                f"Tell the user about the license and, if they accept it, ask "
                f"them to restart the server with `--allow-model {prefix}`. "
                f"Otherwise leave `estimator` out for the default model, "
                f"'{DEFAULT_FOUNDATION_MODEL_ID}'."
            ),
            details = {
                "model_id": model_id,
                "allow_model": prefix,
                "license": info.license_restriction,
                "license_url": info.license_url,
                "requires_hf_auth": info.requires_hf_auth,
            },
        )

    def check_backend(self, model_id: str | None, argument: str) -> None:
        """
        Reject running a foundation model whose backend package is not
        installed where the server runs, before any script runs.

        Parameters
        ----------
        model_id : str, None
            Model ID of the plan; None does nothing.
        argument : str
            Argument of the tool that names the plan.

        Returns
        -------
        None
        """

        if model_id is None:
            return
        try:
            info = resolve_foundation_model(model_id)
        except InvalidInputError:
            return
        if foundation_backend_installed(info):
            return
        package = info.backend_package
        raise ServerError(
            f"'{model_id}' needs the '{package}' package, which is not "
            f"installed where the server runs. Nothing was run.",
            code    = "missing_dependency",
            field   = argument,
            hint    = (
                f"Ask the user to install it where the server runs and to "
                f"restart the server: `pip install \"{package}\"` in its "
                f"Python environment, or `--with \"{package}\"` added to the "
                f"uvx command that starts it."
            ),
            details = {"model_id": model_id, "package": package},
        )

    def uncached(self, model_ids: Iterable[str | None]) -> list[str]:
        """
        Models not announced yet whose weights are not in the local cache.

        Checked before anything runs, since a run fills the cache.

        Parameters
        ----------
        model_ids : iterable of str, None
            Model IDs a call may run; None is skipped.

        Returns
        -------
        model_ids : list of str
            Those without weights in the cache, in order, without
            repetitions.
        """

        with self.lock:
            announced = set(self.announced)
        found: list[str] = []
        for model_id in model_ids:
            if model_id is None or model_id in announced or model_id in found:
                continue
            if not weights_cached(model_id):
                found.append(model_id)

        return found

    def announce(
        self, model_ids: Iterable[str], ran: bool = False
    ) -> list[ToolNotice]:
        """
        Notices that models download their weights, once per model and
        server.

        The cache is looked up by the model ID, while some adapters keep
        their weights in another repository, so the notice says that the
        weights were not found and may be downloaded, not that they will.

        Parameters
        ----------
        model_ids : iterable of str
            Models found by `uncached` that the call used.
        ran : bool, default False
            Whether the call already ran the models (a comparison), so the
            download, if any, has happened.

        Returns
        -------
        notices : list of ToolNotice
            One notice (source `'plan'`) per model not announced before.
        """

        notices = []
        offline = os.getenv("HF_HUB_OFFLINE", "").strip().lower() in _TRUE_VALUES
        for model_id in model_ids:
            try:
                info = resolve_foundation_model(model_id)
            except InvalidInputError:
                continue
            with self.lock:
                if model_id in self.announced:
                    continue
                self.announced.add(model_id)
            # The cache is not named: its path holds the home directory of
            # the user.
            when = (
                "this call may have downloaded them" if ran
                else "the first run may download them"
            )
            message = (
                f"The weights of '{model_id}' were not found in the local "
                f"Hugging Face cache: {when} from the Hugging Face Hub. "
                f"License: {_license_text(info)}."
            )
            if offline and not ran:
                message += (
                    " HF_HUB_OFFLINE is set, so they cannot be downloaded and "
                    "the run fails until they are in the cache."
                )
            notices.append(
                ToolNotice(
                    source   = "plan",
                    category = MODEL_DOWNLOAD_NOTICE,
                    message  = message,
                    count    = 1,
                )
            )

        return notices
