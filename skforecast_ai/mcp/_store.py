################################################################################
#                              MCP server store                                #
#                                                                              #
# Objects the server keeps between calls, addressed by id                      #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
import re
import secrets
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Literal
import pandas as pd
from pydantic import BaseModel
from ._errors import ServerError
from .models import ObjectKind, ToolResult

# Most removed ids remembered, to tell "removed" from "never existed".
_MAX_REMOVED_IDS = 10_000

_ID_PATTERN = re.compile(r"(?P<kind>[a-z]+)-(?P<seq>\d+)-(?P<token>[0-9a-f]+)")

# Tools that create each kind of object, named by the errors.
_CREATED_BY = {
    "profile": "profile",
    "plan": "plan or refine_plan",
    "cv": "create_cv",
    "backtest": "backtest",
    "comparison": "compare",
    "forecast": "forecast",
}


@dataclass(frozen=True)
class Entry:
    """
    An object registered in the server.

    Entries never change once registered. Each holds direct references to
    the objects it was built from, so removing an older entry does not break
    the ones built from it.

    Attributes
    ----------
    id : str
        Id of the object.
    kind : str
        Kind of the object.
    obj : object
        The object of the core (`ForecastingProfile`, `ForecastPlan`,
        `CVResult`, `BacktestResult`, `ComparisonResult` or
        `ForecastResult`).
    envelope : ToolResult
        What the tool that created it returned, also returned by
        `describe_object`.
    profile : ForecastingProfile, None
        Profile the object was built from (the object itself for a
        profile).
    profile_id : str, None
        Id of that profile.
    data_path : str, None
        Path of the CSV file the profile was read from.
    data_sha256 : str, None
        SHA-256 of that file when it was profiled.
    data_warnings : tuple of str
        Texts of the warnings emitted when the data was profiled, so the
        same warnings of a later call are given the source `'data'`.
    code : str, None
        Script of the object, returned by `get_code`.
    code_file : str, None
        File with the whole script, written when it is longer than a
        response of `get_code` may be.
    candidate_code_files : dict
        For a comparison, the files with the whole script of the candidates
        whose script is that long, by candidate.
    candidate_failures : dict
        For a comparison, the failures of its candidates by name: their text
        cut to the limit of `get_failure`, and the file with the full text,
        if any.
    nbytes : int
        Estimated memory the entry takes.
    """

    id: str
    kind: ObjectKind
    obj: Any
    envelope: ToolResult
    profile: Any = None
    profile_id: str | None = None
    data_path: str | None = None
    data_sha256: str | None = None
    data_warnings: tuple[str, ...] = ()
    code: str | None = None
    code_file: str | None = None
    candidate_code_files: dict[str, str] = field(default_factory=dict)
    candidate_failures: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    nbytes: int = 0


class Store:
    """
    Registry of the objects created by the tools, with a limit on their
    number and on the memory they take.

    When a new object goes over a limit, the least recently used objects
    are removed until it fits (the new object is always kept). A tool that
    receives the id of a removed object raises `unknown_id` saying so.

    Parameters
    ----------
    max_objects : int
        Most objects kept.
    max_bytes : int
        Most memory, in bytes, the objects may take (an estimate).

    Attributes
    ----------
    token : str
        Random part of every id, different in each server process, so an id
        of a previous process is recognized as such.
    max_objects : int
        Most objects kept.
    max_bytes : int
        Most memory, in bytes, the objects may take.
    removed : int
        Number of objects removed to stay within the limits.
    """

    def __init__(self, max_objects: int, max_bytes: int) -> None:
        self.token = secrets.token_hex(3)
        self.max_objects = max_objects
        self.max_bytes = max_bytes
        self.removed = 0
        self._entries: OrderedDict[str, Entry] = OrderedDict()
        self._removed_ids: OrderedDict[str, None] = OrderedDict()
        self._seq = 0
        self._bytes = 0
        self._lock = threading.RLock()

    def new_id(self, kind: ObjectKind | Literal["failure"]) -> str:
        """
        Reserve the id of a new object, or of a failure.

        Parameters
        ----------
        kind : str
            Kind of the object, or `'failure'`.

        Returns
        -------
        object_id : str
            `'<kind>-<sequence>-<token>'`.
        """

        with self._lock:
            self._seq += 1
            return f"{kind}-{self._seq}-{self.token}"

    def add(self, entry: Entry) -> None:
        """
        Register an entry, removing the least recently used ones beyond the
        limits.

        Parameters
        ----------
        entry : Entry
            Entry to register.

        Returns
        -------
        None
        """

        with self._lock:
            self._entries[entry.id] = entry
            self._bytes += entry.nbytes
            while len(self._entries) > 1 and (
                len(self._entries) > self.max_objects
                or self._bytes > self.max_bytes
            ):
                old_id, old = self._entries.popitem(last=False)
                self._bytes -= old.nbytes
                self.removed += 1
                self._removed_ids[old_id] = None
                if len(self._removed_ids) > _MAX_REMOVED_IDS:
                    self._removed_ids.popitem(last=False)

    def get(
        self,
        object_id: str,
        field: str,
        kinds: tuple[ObjectKind, ...] | None = None,
    ) -> Entry:
        """
        Return a registered entry and mark it as recently used.

        Parameters
        ----------
        object_id : str
            Id given by the agent.
        field : str
            Argument of the tool that holds the id, named by the errors.
        kinds : tuple of str, default None
            Kinds the argument accepts. None accepts any kind.

        Returns
        -------
        entry : Entry
            The registered entry.
        """

        with self._lock:
            entry = self._entries.get(object_id)
            if entry is not None:
                self._entries.move_to_end(object_id)
            removed = object_id in self._removed_ids

        if entry is None:
            raise self._unknown(object_id, field, removed)
        if kinds is not None and entry.kind not in kinds:
            expected = " or ".join(kinds)
            tools = " or ".join(_CREATED_BY[kind] for kind in kinds)
            raise ServerError(
                f"{object_id!r} is the id of a {entry.kind}, and `{field}` takes "
                f"the id of a {expected} (returned by {tools}).",
                code    = "invalid_argument",
                field   = field,
                details = {"id": object_id, "kind": entry.kind},
            )

        return entry

    def entries(self) -> list[Entry]:
        """
        Return the registered entries, most recently used first.

        Returns
        -------
        entries : list of Entry
            Registered entries.
        """

        with self._lock:
            return list(reversed(self._entries.values()))

    def _unknown(self, object_id: str, field: str, removed: bool) -> ServerError:
        """
        Build the error of an id that is not registered, saying why.
        """

        match = _ID_PATTERN.fullmatch(object_id)
        if removed:
            message = (
                f"{object_id!r} was removed to keep the server within its limits "
                f"({self.max_objects} objects, "
                f"{self.max_bytes // (1024 * 1024)} MB): create it again."
            )
        elif match is not None and match["token"] != self.token:
            message = (
                f"{object_id!r} comes from another run of the server: ids do not "
                f"survive a restart. Create the object again."
            )
        else:
            message = f"No object has the id {object_id!r}."

        return ServerError(
            message,
            code    = "unknown_id",
            field   = field,
            hint    = "Call `list_objects` to see the ids registered now.",
            details = {"id": object_id, "removed": removed},
        )


def estimate_nbytes(obj: Any, _seen: set[int] | None = None) -> int:
    """
    Estimate the memory an object of the core takes.

    DataFrames are measured with `memory_usage(deep=True)`; models, lists and
    dicts are walked; anything else counts its shallow size. Shared objects
    are counted once per call.

    Parameters
    ----------
    obj : object
        Object to measure.

    Returns
    -------
    nbytes : int
        Estimated size in bytes.
    """

    seen = set() if _seen is None else _seen
    if id(obj) in seen:
        return 0
    seen.add(id(obj))

    if isinstance(obj, pd.DataFrame):
        return int(obj.memory_usage(deep=True).sum())
    if isinstance(obj, pd.Series):
        return int(obj.memory_usage(deep=True))
    if isinstance(obj, BaseModel):
        values = [getattr(obj, name) for name in type(obj).model_fields]
        return sys.getsizeof(obj) + sum(estimate_nbytes(v, seen) for v in values)
    if isinstance(obj, dict):
        return sys.getsizeof(obj) + sum(
            estimate_nbytes(k, seen) + estimate_nbytes(v, seen) for k, v in obj.items()
        )
    if isinstance(obj, (list, tuple, set, frozenset)):
        return sys.getsizeof(obj) + sum(estimate_nbytes(v, seen) for v in obj)

    return sys.getsizeof(obj)
