################################################################################
#                            JSON-aware field types                            #
#                                                                              #
# Annotated types that let results holding DataFrames serialize to JSON        #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from typing import Annotated, Any
import pandas as pd
from pydantic import PlainSerializer
from skforecast.model_selection import TimeSeriesFold

_FOLD_PARAMS = (
    "steps",
    "initial_train_size",
    "refit",
    "fixed_train_size",
    "gap",
    "fold_stride",
    "skip_folds",
    "allow_incomplete_fold",
    "differentiation",
)


def _json_value(value: Any) -> Any:
    """
    Coerce a scalar to something the JSON encoder accepts.

    Parameters
    ----------
    value : object
        Value read from a `TimeSeriesFold` attribute.

    Returns
    -------
    value : object
        Primitives and lists pass through; anything else (for example a
        pandas Timestamp) is rendered as a string.
    """

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return str(value)


def frame_to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Serialize a DataFrame as a list of row records, index included.

    The index becomes a leading column (named after the index, or
    `'index'` when it has no name), which is the layout the CLI has
    always emitted for predictions and metrics.

    Parameters
    ----------
    frame : pandas DataFrame
        Frame to serialize.

    Returns
    -------
    records : list of dict
        One dict per row.
    """

    return frame.reset_index().to_dict(orient="records")


def fold_to_params(cv: TimeSeriesFold) -> dict[str, Any]:
    """
    Serialize a `TimeSeriesFold` as its constructor parameters.

    Parameters
    ----------
    cv : TimeSeriesFold
        Cross-validation fold splitter.

    Returns
    -------
    params : dict
        Parameter name to JSON-compatible value.
    """

    return {name: _json_value(getattr(cv, name)) for name in _FOLD_PARAMS}


# Serialization applies in JSON mode only (`model_dump(mode="json")`,
# `model_dump_json()`), so `model_dump()` keeps returning the live objects.
JSONFrame = Annotated[
    pd.DataFrame,
    PlainSerializer(
        frame_to_records, return_type=list[dict[str, Any]], when_used="json"
    ),
]
OptionalJSONFrame = JSONFrame | None
JSONTimeSeriesFold = Annotated[
    TimeSeriesFold,
    PlainSerializer(fold_to_params, return_type=dict[str, Any], when_used="json"),
]
