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
from .._foundation import missing_foundation_backend, resolve_foundation_model
from ..exceptions import InvalidInputError
from ._errors import ServerError
from .models import ToolNotice

# Category of the notice that a model will download its weights: a notice of
# the server, not a Python warning.
MODEL_DOWNLOAD_NOTICE = "ModelDownloadNotice"

# Category of the notice with the license of the foundation model of a
# response, given when no download is announced in it.
MODEL_LICENSE_NOTICE = "ModelLicenseNotice"

# Values of HF_HUB_OFFLINE that huggingface_hub reads as true.
_TRUE_VALUES = frozenset({"1", "on", "yes", "true"})


# Fields of `FoundationModelInfo` that decide whether a model needs
# `--allow-model`: the server runs a model by default only when skforecast
# says, with a bool, that none of them applies. A missing field (an older or
# newer skforecast) counts as applying, so the model is blocked by default.
_RESTRICTING_FIELDS = (
    "commercial_use_restricted",
    "requires_hf_auth",
    "requires_provider_auth",
)


def is_permissive(info: FoundationModelInfo) -> bool:
    """
    Whether the server runs a foundation model without `--allow-model`:
    skforecast registers its license and says that the license does not
    restrict commercial use, that its weights are not gated on the Hugging
    Face Hub and that its provider asks for no account of its own.

    Parameters
    ----------
    info : FoundationModelInfo
        Capabilities of the model.

    Returns
    -------
    permissive : bool
        Whether the server runs it without `--allow-model`. False when
        skforecast does not give one of these facts.
    """

    if not getattr(info, "license", None):
        return False

    return all(
        getattr(info, name, None) is False for name in _RESTRICTING_FIELDS
    )


def permissive_adapters() -> list[FoundationModelInfo]:
    """
    Adapters of skforecast whose models the server runs by default, read
    from the information skforecast registers for each one.

    Returns
    -------
    adapters : list of FoundationModelInfo
        Adapters for which `is_permissive` holds, in the order of
        skforecast.
    """

    return [info for info in list_adapters() if is_permissive(info)]


def restricted_adapters() -> list[FoundationModelInfo]:
    """
    Adapters of skforecast whose models need `--allow-model`.

    Returns
    -------
    adapters : list of FoundationModelInfo
        Adapters for which `is_permissive` does not hold, in the order of
        skforecast.
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


# skforecast registers a license for each family of models, found by the
# start of the model id: the notice of a model says so, since the server
# does not check that a repository of that name exists nor read its card.
_LICENSE_LEAD = "License (by the name of the model, as skforecast registers it):"


def _license_text(info: FoundationModelInfo) -> str:
    """
    The license of a model as skforecast registers it, and what else a user
    must accept before running it.
    """

    license_name = getattr(info, "license", None)
    if not license_name:
        text = (
            "skforecast gives no license information for it, so the server "
            "cannot tell which uses its license permits"
        )
    else:
        text = f"its license is {license_name}"
        license_url = getattr(info, "license_url", None)
        if license_url:
            text += f" ({license_url})"
        restricted = getattr(info, "commercial_use_restricted", None)
        if restricted is True:
            text += ", which restricts commercial use"
        elif restricted is not False:
            text += (
                ", and skforecast does not say whether it restricts "
                "commercial use"
            )
    gated = getattr(info, "requires_hf_auth", None)
    if gated is True:
        text += (
            "; its weights are gated on the Hugging Face Hub and need a login "
            "with an account that accepted the license"
        )
    elif gated is not False:
        text += "; skforecast does not say whether its weights are gated"
    provider = getattr(info, "requires_provider_auth", None)
    if provider is True:
        text += (
            "; its provider requires its own account and accepting its "
            "license, outside the Hugging Face Hub, before the weights can be "
            "used"
        )
    elif provider is not False:
        text += (
            "; skforecast does not say whether its provider requires an "
            "account"
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


def weights_cached(repo_id: str) -> bool:
    """
    Whether the local cache of Hugging Face holds a snapshot of a model
    repository.

    Parameters
    ----------
    repo_id : str
        Hugging Face repository of the weights, `'owner/name'`.

    Returns
    -------
    cached : bool
        Whether `models--owner--name/snapshots` of the cache holds at least
        one snapshot with a file in it (an interrupted download leaves an
        empty snapshot).
    """

    folder = "models--" + repo_id.replace("/", "--")
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
        # ValueError: an ID with a NUL byte, which no cache holds.
        return False

    return False


def _weights_repo(info: FoundationModelInfo, model_id: str) -> str:
    """
    Hugging Face repository the backend downloads the weights of a model
    from: `weights_repo_id` of skforecast, or the model ID when it gives
    none.
    """

    repo_id = getattr(info, "weights_repo_id", None)

    return repo_id if isinstance(repo_id, str) and repo_id else model_id


@dataclass
class ModelPolicy:
    """
    Foundation models a server runs, and the models whose download it
    already announced.

    Attributes
    ----------
    allowed_prefixes : tuple of str
        Prefixes given to `--allow-model`: models that need it (see
        `is_permissive`) run when their ID starts with one of them.
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
        Reject a foundation model that needs `--allow-model` (see
        `is_permissive`) when the option does not allow it.

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
            f"Foundation models whose license restricts commercial use, "
            f"whose weights are gated or whose provider requires an account "
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
                "license": getattr(info, "license", None),
                "license_url": getattr(info, "license_url", None),
                "commercial_use_restricted": getattr(
                    info, "commercial_use_restricted", None
                ),
                "requires_hf_auth": getattr(info, "requires_hf_auth", None),
                "requires_provider_auth": getattr(
                    info, "requires_provider_auth", None
                ),
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

        # The rule of the core, with a message and a hint for the server.
        package = missing_foundation_backend(model_id)
        if package is None:
            return
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

        Checked before anything runs, since a run fills the cache. The
        cache is looked up under the repository skforecast registers for
        the weights (`weights_repo_id`). A model whose weights skforecast
        does not keep in the Hugging Face cache (`weights_in_hf_cache` is
        False, as for TabPFN) cannot be looked up, so it is listed too.

        Parameters
        ----------
        model_ids : iterable of str, None
            Model IDs a call may run; None is skipped.

        Returns
        -------
        model_ids : list of str
            Those without weights in the cache, or whose cache cannot be
            looked up, in order, without repetitions. A model ID that
            skforecast does not serve is skipped.
        """

        with self.lock:
            announced = set(self.announced)
        found: list[str] = []
        for model_id in model_ids:
            if model_id is None or model_id in announced or model_id in found:
                continue
            try:
                info = resolve_foundation_model(model_id)
            except InvalidInputError:
                continue
            if getattr(info, "weights_in_hf_cache", None) is not True:
                found.append(model_id)
            elif not weights_cached(_weights_repo(info, model_id)):
                found.append(model_id)

        return found

    def announce(
        self, model_ids: Iterable[str], ran: bool = False
    ) -> list[ToolNotice]:
        """
        Notices that models download their weights, once per model and
        server.

        The notice says that the weights were not found and may be
        downloaded, not that they will: a backend may keep a copy of its
        own. For a model whose weights skforecast does not keep in the
        Hugging Face cache, it says nothing about that cache.

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
            in_hf_cache = getattr(info, "weights_in_hf_cache", None) is True
            if in_hf_cache:
                repo_id = _weights_repo(info, model_id)
                repository = (
                    f" (repository '{repo_id}')" if repo_id != model_id else ""
                )
                message = (
                    f"The weights of '{model_id}'{repository} were not found "
                    f"in the local Hugging Face cache: {when} from the Hugging "
                    f"Face Hub. {_LICENSE_LEAD} {_license_text(info)}."
                )
            else:
                where = (
                    "its backend keeps them in a cache of its own"
                    if getattr(info, "weights_in_hf_cache", None) is False
                    else "skforecast does not say where they are cached"
                )
                message = (
                    f"The server cannot tell whether the weights of "
                    f"'{model_id}' are already downloaded: {where}, so "
                    f"{when}. {_LICENSE_LEAD} {_license_text(info)}."
                )
            if offline and not ran and in_hf_cache:
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

    def notices(
        self,
        model_ids: Iterable[str | None],
        uncached: Iterable[str] = (),
        ran: bool = False,
    ) -> list[ToolNotice]:
        """
        Notices about the foundation models of a response: for each one, the
        announcement of its download (see `announce`), which carries its
        license, or else its license alone.

        The license is given in every response that names a foundation
        model, not only the first time its weights are downloaded: without
        it, an agent asked to tell the user the license states one from its
        own memory.

        Parameters
        ----------
        model_ids : iterable of str, None
            Model IDs of the plans of the response; None is skipped.
        uncached : iterable of str, default ()
            Those found by `uncached` before the call ran.
        ran : bool, default False
            Whether the call already ran the models (a comparison).

        Returns
        -------
        notices : list of ToolNotice
            One notice (source `'plan'`) per model that skforecast serves,
            without repetitions, in order.
        """

        uncached = set(uncached)
        notices = []
        for model_id in dict.fromkeys(model_ids):
            if model_id is None:
                continue
            download = self.announce([model_id], ran=ran) if model_id in uncached else []
            if download:
                notices.extend(download)
                continue
            try:
                info = resolve_foundation_model(model_id)
            except InvalidInputError:
                continue
            notices.append(
                ToolNotice(
                    source   = "plan",
                    category = MODEL_LICENSE_NOTICE,
                    message  = (
                        f"Foundation model '{model_id}'. {_LICENSE_LEAD} "
                        f"{_license_text(info)}."
                    ),
                    count    = 1,
                )
            )

        return notices
