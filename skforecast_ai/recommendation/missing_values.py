################################################################################
#                      Recommendations: missing values                         #
#                                                                              #
# Who cannot use a missing value, what avoids the error, and the text of it   #
# This work by skforecast team is licensed under the Apache License 2.0        #
################################################################################

from __future__ import annotations
from typing import NamedTuple
from .._constants import AUTOREG_FORECASTERS, NAN_TOLERANT_ESTIMATORS
from ..profiling.data_profile import weekday_names
from ..schemas import DataProfile, ForecastPlan
from .forecaster_selection import (
    estimator_n_observations,
    select_estimator_and_candidates,
)

# What an estimator that accepts missing values changes in a backtest of a
# single series. The warning of `create_cv()`, the notice and the hint of
# the MCP server say it with these words: the advice of 0.4 promised that
# it let every fold run, and a missing value inside a test fold fails with
# any estimator.
TOLERANT_ESTIMATOR_SCOPE = (
    "avoids the error of a fold predicted from a missing value, not of a fold "
    "that holds one"
)

# Columns an exogenous advice names before "(first 5 of N)".
_SHOWN_COLUMNS = 5


def select_nan_tolerant_estimator(
    task_type: str,
    n_observations: int,
) -> str | None:
    """
    Select the estimator to recommend when the missing values of the data
    make the estimator of a plan fail: the first candidate of the rules
    that accepts missing values.

    Parameters
    ----------
    task_type : str
        Forecasting task category.
    n_observations : int
        Number of observations that sizes the estimator, see
        `estimator_n_observations`.

    Returns
    -------
    estimator : str, None
        Name of the estimator class, the first of
        `select_estimator_and_candidates` in `NAN_TOLERANT_ESTIMATORS`.
        None when no candidate of the task accepts missing values (the
        statistical, foundation and baseline tasks).

    Notes
    -----
    The candidates are ranked for the size of the data, so the estimator
    changes with it: `'RandomForestRegressor'` below 250 observations,
    where the rules prefer it to `'LGBMRegressor'`, and `'LGBMRegressor'`
    from 250 on.
    """

    _, candidates = select_estimator_and_candidates(task_type, n_observations)

    return next(
        (name for name in candidates if name in NAN_TOLERANT_ESTIMATORS), None
    )


def nan_tolerant_estimator(
    plan: ForecastPlan,
    profile: DataProfile,
) -> str | None:
    """
    Return the estimator that avoids the error of a plan whose estimator
    cannot use a missing value (see `select_nan_tolerant_estimator`).

    Parameters
    ----------
    plan : ForecastPlan
        Plan whose estimator cannot use the missing values.
    profile : DataProfile
        Profile of the data.

    Returns
    -------
    estimator : str, None
        Name of the estimator class. None when the forecaster has no
        estimator to replace (it reads no lags) or its estimator already
        accepts missing values.
    """

    if (
        plan.forecaster not in AUTOREG_FORECASTERS
        or plan.estimator in NAN_TOLERANT_ESTIMATORS
    ):
        return None

    return select_nan_tolerant_estimator(
        task_type      = plan.task_type,
        n_observations = estimator_n_observations(plan.task_type, profile),
    )


def tolerant_estimator_phrase(estimator: str | None) -> str:
    """
    Name an estimator that accepts missing values, the one of the rules when
    there is one.

    Parameters
    ----------
    estimator : str, None
        Estimator of the rules (see `nan_tolerant_estimator`), or None.

    Returns
    -------
    phrase : str
        `"an estimator that accepts missing values (such as
        'LGBMRegressor')"`, without the parenthesis when `estimator` is
        None.
    """
    such_as = f" (such as {estimator!r})" if estimator is not None else ""

    return f"an estimator that accepts missing values{such_as}"


def _capitalized(text: str) -> str:
    """Return `text` with its first letter in upper case, the rest as it is."""
    return text[:1].upper() + text[1:]


def closed_days_remedy(days: str) -> str:
    """
    Return the advice for missing values that all fall on days of the week
    without any value (a shop closed on them), which nothing fills in
    without the user (D9 of the roadmap of 0.5.0).

    Parameters
    ----------
    days : str
        The days, as the message names them (`'Sundays'`, see
        `weekday_names`).

    Returns
    -------
    remedy : str
        `"If the business is closed on Sundays, fill them with 0 in the
        data, after asking the user"`, without a final stop so that the
        message can go on.
    """

    return (
        f"If the business is closed on {days}, fill them with 0 in the data, "
        f"after asking the user"
    )


def _target_missing_phrase(values: bool, gaps: bool) -> str:
    """
    Name what is missing in the target: `"missing values"`, `"missing
    timestamps (asfreq() restores them as missing values)"`, or both.
    """
    if not gaps:
        return "missing values"
    restored = "(asfreq() restores them as missing values)"
    if not values:
        return f"missing timestamps {restored}"

    return f"missing values and missing timestamps {restored}"


def _exog_columns_phrase(columns: list[str]) -> str:
    """
    Name exogenous columns: `"column 'x'"`, `"columns 'x', 'z'"`, up to 5
    and then `"(first 5 of N)"`.
    """
    shown = ", ".join(repr(column) for column in columns[:_SHOWN_COLUMNS])
    if len(columns) > _SHOWN_COLUMNS:
        shown += f" (first {_SHOWN_COLUMNS} of {len(columns)})"
    noun = "column" if len(columns) == 1 else "columns"

    return f"{noun} {shown}"


class BacktestMissingValues(NamedTuple):
    """
    What can make the backtest of a single series fail on missing values,
    as known from the profile alone (see `backtest_missing_values`).

    Attributes
    ----------
    values : bool
        Whether the target has missing values.
    gaps : bool
        Whether the target has missing timestamps, which `asfreq()`
        restores as missing values.
    closed_days : list of int
        Days of the week (0 for Monday) that every missing timestamp falls
        on when the target never has a date on them, the days a business
        closed on them would fill with 0 (`DataProfile.closed_weekdays`).
        Empty otherwise.
    cannot_predict : str, None
        Why the forecaster cannot predict from a missing value of the
        target (`"ForecasterRecursive with Ridge cannot predict from a
        missing value"`), or None when its estimator accepts them.
    order : int
        Order of the differentiation, 0 without it.
    exog : list of str
        Exogenous columns of the plan with missing values that its estimator
        cannot predict from.
    estimator : str, None
        Estimator of the rules that accepts missing values, when the one of
        the plan does not (see `nan_tolerant_estimator`).
    """

    values: bool
    gaps: bool
    closed_days: list[int]
    cannot_predict: str | None
    order: int
    exog: list[str]
    estimator: str | None

    @property
    def target(self) -> bool:
        """Whether the target has missing values or missing timestamps."""
        return self.values or self.gaps


def backtest_missing_values(
    plan: ForecastPlan,
    profile: DataProfile,
) -> BacktestMissingValues | None:
    """
    Find what can make the backtest of a single series fail on its missing
    values, before the strategy is run and without the data: the profile
    holds how many values are missing, not where.

    - A missing value of the target inside a test fold fails with any
      estimator: the metrics cannot be computed on it. Every forecaster that
      predicts from past values (the lag forecasters and
      ForecasterEquivalentDate) is concerned.
    - A test fold predicted from a missing value fails when the estimator
      does not accept missing values, and with ForecasterEquivalentDate,
      which repeats it. So does a training window whose rows all read one,
      since the plan drops them (`dropna_from_series`).
    - With the differentiation, a missing value among the last `order`
      values before a test fold fails whatever the estimator: the inverse of
      the differentiation starts from them.
    - A missing value of an exogenous column in a row that a test fold
      predicts fails when the estimator does not accept missing values;
      `dropna_from_series` only drops the training rows.

    `backtest()` checks every fold before running: the target (see
    `validate_backtest_windows`) and the exogenous columns (see
    `validate_backtest_exog`). Several series drop the missing values per
    series and are not concerned, nor ForecasterStats and
    ForecasterFoundation.

    Parameters
    ----------
    plan : ForecastPlan
        Plan a strategy is built for.
    profile : DataProfile
        Profile of the data.

    Returns
    -------
    missing_values : BacktestMissingValues, None
        None when the backtest cannot fail on missing values.
    """

    if profile.n_series != 1 or not isinstance(profile.target, str):
        return None
    lags = plan.forecaster in AUTOREG_FORECASTERS
    if not lags and plan.forecaster != "ForecasterEquivalentDate":
        return None

    target = bool(profile.missing_target) or profile.has_gaps
    tolerant = plan.estimator in NAN_TOLERANT_ESTIMATORS
    cannot_predict = None
    if target and not lags:
        cannot_predict = f"{plan.forecaster} repeats it as a missing prediction"
    elif target and not tolerant:
        cannot_predict = (
            f"{plan.forecaster} with {plan.estimator} cannot predict from a "
            f"missing value"
        )
    exog = [
        column for column in profile.exog_columns
        if profile.missing_exog.get(column)
    ] if lags and plan.use_exog and not tolerant else []
    if not target and not exog:
        return None

    order = int(plan.forecaster_kwargs.get("differentiation") or 0) if lags else 0

    return BacktestMissingValues(
        values         = bool(profile.missing_target),
        gaps           = profile.has_gaps,
        closed_days    = list(profile.closed_weekdays),
        cannot_predict = cannot_predict,
        order          = order,
        exog           = exog,
        estimator      = (
            nan_tolerant_estimator(plan, profile)
            if lags and not tolerant else None
        ),
    )


def backtest_missing_values_messages(
    missing_values: BacktestMissingValues,
    plan: ForecastPlan,
) -> list[str]:
    """
    Describe when the backtest of a plan fails on the missing values of the
    data and what avoids it, without the data: each case is worded as a
    condition, since where the values are is not known. The target and the
    exogenous columns get a message each, which keeps every one within the
    length of a notice of the MCP server.

    Parameters
    ----------
    missing_values : BacktestMissingValues
        What can make the backtest fail (see `backtest_missing_values`).
    plan : ForecastPlan
        Plan a strategy is built for.

    Returns
    -------
    messages : list of str
        Texts of the warnings of `create_cv()`: the one of the target, then
        the one of the exogenous columns, each when it applies.
    """

    messages = []
    sentences = []
    if missing_values.target:
        when = [
            "a test fold holds one, whatever the estimator, since no metric is "
            "computed on it"
        ]
        if missing_values.cannot_predict is not None:
            when.append(
                f"a test fold is predicted from one, since "
                f"{missing_values.cannot_predict}"
            )
        if missing_values.order:
            when.append(
                f"one of the last {missing_values.order} value(s) before a test "
                f"fold is missing, whatever the estimator, since the inverse of "
                f"the differentiation starts from them"
            )
        listed = (
            when[0] if len(when) == 1
            else "; when ".join(when[:-1]) + "; and when " + when[-1]
        )
        what = _target_missing_phrase(missing_values.values, missing_values.gaps)
        sentences.append(
            f"The target has {what}, and `backtest()` checks every test fold "
            f"before running: it raises, naming the dates, when {listed}."
        )
        if missing_values.cannot_predict is not None and missing_values.estimator:
            sentences.append(
                f"`dropna_from_series` only drops the training rows that read "
                f"one, and a training window left without rows raises too. "
                f"{_capitalized(tolerant_estimator_phrase(missing_values.estimator))} "
                f"{TOLERANT_ESTIMATOR_SCOPE}."
            )
        impute = "impute the target to backtest every fold."
        if missing_values.closed_days:
            # The days of the profile, which every missing timestamp falls
            # on: the longest message still fits in a notice of the server.
            sentences.append(
                f"{closed_days_remedy(weekday_names(missing_values.closed_days))}"
                f", or {impute}"
            )
        else:
            sentences.append(_capitalized(impute))
        messages.append(" ".join(sentences))
    if missing_values.exog:
        columns = _exog_columns_phrase(missing_values.exog)
        them = "it" if len(missing_values.exog) == 1 else "them"
        messages.append(
            f"The exogenous {columns} {'has' if them == 'it' else 'have'} "
            f"missing values, and {plan.forecaster} with {plan.estimator} cannot "
            f"predict from them: `backtest()` checks every test fold before "
            f"running and raises, naming the dates, when the rows it predicts "
            f"have one, and `dropna_from_series` only drops them from the "
            f"training data. "
            f"{_capitalized(tolerant_estimator_phrase(missing_values.estimator))} "
            f"predicts from them; otherwise, fill them in the data, after asking "
            f"the user, or leave {them} out of `exog_columns` when profiling."
        )

    return messages


def missing_values_advice(
    profile: DataProfile,
    forecaster: str,
    estimator: str | None,
    task_type: str,
    differentiation: int | None = None,
) -> tuple[str, str] | None:
    """
    Advise on the missing values of the data for a forecaster that predicts
    from lags (the reason and the code snippet of the preprocessing step
    `handle_missing_values`), saying only what works.

    `dropna_from_series` drops the training rows that read a missing value,
    which the plan already sets for an estimator that does not accept them:
    it neither predicts from a missing value nor scores one. What does: an
    estimator that accepts missing values (the one of the rules), filling
    the values in (after asking the user, who owns them) and, for the
    exogenous columns, leaving them out. A missing value on a date that an
    evaluation scores fails with any estimator (a backtest of several
    series drops them per series), and with the differentiation a missing
    value among the last values before a prediction too.

    Parameters
    ----------
    profile : DataProfile
        Profile the plan is built from (without the exogenous columns when
        the plan does not use them).
    forecaster : str
        Name of the skforecast forecaster class.
    estimator : str, None
        Name of the estimator of the plan.
    task_type : str
        Forecasting task category of the plan.
    differentiation : int, default None
        Order of the differentiation of the plan.

    Returns
    -------
    advice : tuple, None
        The reason and the code snippet, or None when nothing is missing.
    """

    target = bool(profile.missing_target) or profile.has_gaps
    exog = [
        column for column in profile.exog_columns
        if profile.missing_exog.get(column)
    ]
    if not target and not exog:
        return None
    single = profile.n_series == 1

    if forecaster == "ForecasterStats":
        # No estimator or `dropna_from_series` to choose: the model fails
        # on a missing value of the target and predicts a missing value
        # from a missing exogenous value.
        parts = []
        if target:
            parts.append("fails on a missing value of the target")
        if exog:
            parts.append(
                f"gives missing predictions from a missing value of the "
                f"exogenous {_exog_columns_phrase(exog)}"
            )
        leave = (
            ", or leave the exogenous columns out of `exog_columns` when "
            "profiling" if exog else ""
        )
        reason = (
            f"{forecaster} {' and '.join(parts)}. Impute them in the data, "
            f"after asking the user{leave}."
        )
        snippet = (
            "# Impute the missing values in the data, after asking the user,\n"
            "# for example: data[column] = data[column].interpolate()"
        )
        return reason, snippet

    tolerant = estimator in NAN_TOLERANT_ESTIMATORS
    suggested = None if tolerant else select_nan_tolerant_estimator(
        task_type, estimator_n_observations(task_type, profile)
    )
    phrase = tolerant_estimator_phrase(suggested)
    # Without the estimator of the plan, what the forecaster cannot do is
    # said of the estimators that do not accept missing values.
    who = (
        f"{forecaster} with {estimator}" if estimator is not None
        else f"{forecaster} with an estimator that does not accept them"
    )
    sentences = []
    if target:
        what = _target_missing_phrase(bool(profile.missing_target), profile.has_gaps)
        # A backtest of several series drops them per series; `test_size`
        # scores each series on every test date.
        scorers = "a backtest or `test_size`" if single else "`test_size`"
        scored = (
            f" A missing value on a date that {scorers} scores fails with any "
            f"estimator."
        )
        if tolerant:
            sentences.append(
                f"The target has {what}: {estimator} trains and predicts with "
                f"them.{scored}"
            )
        else:
            dropped = (
                "" if single else
                " (a backtest leaves a series out of the folds predicted from "
                "one)"
            )
            sentences.append(
                f"The target has {what}: {who} cannot "
                f"predict from them{dropped}, and `dropna_from_series` only "
                f"drops the training rows that read one. {_capitalized(phrase)} "
                f"predicts from them.{scored}"
            )
        if differentiation:
            sentences.append(
                f"With the differentiation, a missing value among the last "
                f"{differentiation} value(s) before a prediction gives missing "
                f"predictions whatever the estimator."
            )
        sentences.append(
            "Imputing the target, after asking the user, avoids these errors."
        )
    if exog:
        columns = _exog_columns_phrase(exog)
        if tolerant:
            sentences.append(
                f"The exogenous {columns} {'has' if len(exog) == 1 else 'have'} "
                f"missing values: {estimator} trains and predicts with them."
            )
        else:
            sentences.append(
                f"The exogenous {columns} {'has' if len(exog) == 1 else 'have'} "
                f"missing values: {who} cannot predict from them, and "
                f"`dropna_from_series` only drops the training rows that have "
                f"one. {_capitalized(phrase)} predicts from them; otherwise, fill "
                f"them in the data, after asking the user, or leave "
                f"{'it' if len(exog) == 1 else 'them'} out of `exog_columns` when "
                f"profiling."
            )

    if tolerant:
        snippet = (
            f"# {estimator} accepts missing values. Impute them only if needed,\n"
            f"# after asking the user, for example:\n"
            f"# data[column] = data[column].interpolate()"
        )
    else:
        snippet = (
            f"# Option 1: an estimator that accepts missing values, "
            f"estimator={suggested!r}\n"
            f"# Option 2: impute them in the data, after asking the user"
        )
        if exog:
            snippet += (
                "\n# Option 3: leave the exogenous columns with missing values "
                "out of exog_columns"
            )

    return " ".join(sentences), snippet
