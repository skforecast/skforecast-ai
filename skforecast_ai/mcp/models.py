################################################################################
#                              MCP server models                               #
#                                                                              #
# What the tools of the MCP server take and return                             #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, with_config
from ..schemas.plans import RefinePlanOverrides

ObjectKind = Literal["profile", "plan", "cv", "backtest", "comparison", "forecast"]
"""Kinds of the objects the server registers, the first part of their id."""


@with_config(ConfigDict(extra="forbid", strict=True))
class RefinePlanArgs(RefinePlanOverrides, total=False):
    """
    Overrides of the `refine_plan` tool.

    The keys of `RefinePlanOverrides`, with unknown keys rejected and no
    type coercion. A key that is omitted keeps the value of the plan; a key
    passed as null asks for the deterministic default, as in
    `ForecastingAssistant.refine_plan()`.
    """


class ToolNotice(BaseModel):
    """
    A warning emitted while a tool call ran.

    Attributes
    ----------
    source : str
        Where the warning comes from: `'data'` (reading or profiling the
        data), `'plan'` (a warning the plan carries in `plan.warnings`) or
        `'runtime'` (any other warning of the call).
    category : str
        Class name of the warning (e.g. `'LongTrainingWarning'`).
    message : str
        Text of the warning, without the suggestion of skforecast on how to
        silence it, cut to 1,000 characters.
    count : int
        Number of times the call emitted it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Literal["data", "plan", "runtime"]
    category: str
    message: str
    count: int = Field(ge=1)


class ToolResult(BaseModel):
    """
    Envelope returned by the tools that create an object, and by
    `describe_object`.

    Attributes
    ----------
    id : str
        Id of the object, to pass to the tools that take it.
    kind : str
        Kind of the object: `'profile'`, `'plan'`, `'cv'`, `'backtest'`,
        `'comparison'` or `'forecast'`.
    links : dict
        Ids of the objects it was built from, keyed by the argument that
        takes them (`profile_id`, `plan_id`, `cv_id`), plus
        `parent_plan_id` for a refined plan.
    summary : str
        Plain-text description of the object (`describe()` of the core),
        cut to 20,000 characters.
    summary_truncated : bool
        Whether `summary` was cut; the full text is then in
        `files['summary']`.
    notices : list of ToolNotice
        Warnings the call emitted, the first 20 distinct ones. Deprecation
        warnings go to the log of the server instead, and the failures of
        the candidates of a comparison are in its result.
    notices_omitted : int
        Number of distinct warnings left out of `notices`.
    files : dict
        Absolute paths of the files written for the object, by role.
    values_included : bool
        Always False: the response holds no rows of the data, the
        predictions or the metrics. The summary carries statistics of the
        predictions and the metrics; the rows are in `files`.
    cost : dict, None
        Cost of a cross-validation strategy: `n_folds`, `n_fits` (trainings
        of the forecaster) and `estimator_fits` (fits of an estimator,
        which a direct forecaster multiplies by `steps`). None for the
        other kinds.
    changeable : list of str
        Arguments of `refine_plan` (for a plan) or of `create_cv` (for a
        cross-validation strategy) that build a variant of the object.
        Empty for the other kinds.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: ObjectKind
    links: dict[str, str] = Field(default_factory=dict)
    summary: str
    summary_truncated: bool = False
    notices: list[ToolNotice] = Field(default_factory=list)
    notices_omitted: int = 0
    files: dict[str, str] = Field(default_factory=dict)
    values_included: Literal[False] = False
    cost: dict[str, int] | None = None
    changeable: list[str] = Field(default_factory=list)


class CodeResult(BaseModel):
    """
    Script of an object, returned by the `get_code` tool.

    Attributes
    ----------
    id : str
        Id of the object.
    kind : str
        Kind of the object.
    code : str
        Python code, cut to 20,000 characters.
    code_truncated : bool
        Whether `code` was cut; the full code is then in `files['code']`.
    files : dict
        Absolute path of the file with the full code, when it was cut.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: ObjectKind
    code: str
    code_truncated: bool = False
    files: dict[str, str] = Field(default_factory=dict)


class ObjectInfo(BaseModel):
    """
    An object registered in the server, as listed by `list_objects`.

    Attributes
    ----------
    id : str
        Id of the object.
    kind : str
        Kind of the object.
    links : dict
        Ids of the objects it was built from.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: ObjectKind
    links: dict[str, str] = Field(default_factory=dict)


class ObjectList(BaseModel):
    """
    Objects registered in the server, returned by `list_objects`.

    Attributes
    ----------
    objects : list of ObjectInfo
        Registered objects, most recently used first.
    max_objects : int
        Most objects the server keeps; the least recently used ones are
        removed beyond it.
    max_memory_mb : int
        Memory, in MB, the objects may take; the least recently used ones
        are removed beyond it.
    removed : int
        Number of objects removed so far to stay within those limits. A
        tool that receives the id of a removed object says so.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    objects: list[ObjectInfo]
    max_objects: int
    max_memory_mb: int
    removed: int = 0
