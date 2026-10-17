# Unit test render_forecast_script

import pytest

from skforecast_ai.execution.forecast_runner import render_forecast_script
from skforecast_ai.schemas import FutureExogFile

from tests.tests_rendering.fixtures_rendering import (
    plan_baseline,
    plan_foundation_numeric_covariates_no_end_train,
    plan_multi_series_exog,
    plan_multivariate,
    plan_single_predict_exog,
    plan_statistical_exog,
    profile_multi_long_exog,
    profile_multi_wide,
    profile_single,
    profile_single_mixed_exog,
)

# One plan in prediction mode with future exogenous variables per family of
# forecaster, with the profile it is rendered from.
_PLANS_WITH_FUTURE_EXOG = {
    "single series": (plan_single_predict_exog, profile_single),
    "statistical": (
        plan_statistical_exog.model_copy(update={"end_train": None}),
        profile_single_mixed_exog,
    ),
    "foundation": (
        plan_foundation_numeric_covariates_no_end_train,
        profile_single_mixed_exog,
    ),
    "multi series": (
        plan_multi_series_exog.model_copy(update={"end_train": None}),
        profile_multi_long_exog,
    ),
    "multivariate": (
        plan_multivariate.model_copy(update={"end_train": None, "use_exog": True}),
        profile_multi_wide.model_copy(update={"exog_columns": ["promo"]}),
    ),
}


@pytest.mark.parametrize(
    "exog_date_format, exog_format_arg",
    [(None, ""), ("%d/%m/%Y", ", format='%d/%m/%Y'")],
    ids=["exog in iso", "exog day first"],
)
@pytest.mark.parametrize(
    "plan, profile",
    list(_PLANS_WITH_FUTURE_EXOG.values()),
    ids=list(_PLANS_WITH_FUTURE_EXOG),
)
def test_render_forecast_script_output_reads_future_exog_with_its_own_format(
    plan, profile, exog_date_format, exog_format_arg
):
    """
    Test that every family of forecaster reads the dates of the data with
    the format of the profile (month first here) and those of
    `exog_future.csv` with the format of `exog_file`, their own, which may
    be another one or none (ISO 8601, as `to_csv()` writes them).
    """
    profile = profile.model_copy(update={"date_format": "%m/%d/%Y"})

    script = render_forecast_script(
                 profile, plan, FutureExogFile(date_format=exog_date_format)
             ).full_script

    assert (
        "data['date'] = pd.to_datetime(data['date'], format='%m/%d/%Y')\n"
        in script
    )
    assert (
        f"exog_future['date'] = pd.to_datetime(exog_future['date']"
        f"{exog_format_arg})\n" in script
    )


def test_render_forecast_script_output_when_baseline_and_exog_file():
    """
    Test that a baseline, whose script reads no future exogenous variables,
    takes `exog_file` as every renderer does and reads no future exogenous
    variables.
    """
    plan = plan_baseline.model_copy(update={"end_train": None})

    exog_file = FutureExogFile(
                    path        = "futuro.csv",
                    sep         = ";",
                    decimal     = ",",
                    encoding    = "cp1252",
                    date_format = "%d/%m/%Y",
                )

    script = render_forecast_script(profile_single, plan, exog_file).full_script

    assert "exog_future" not in script


@pytest.mark.parametrize(
    "exog_encoding, encoding_arg",
    [("utf-8", ""), ("cp1252", ", encoding='cp1252'")],
    ids=["exog in utf-8", "exog in cp1252"],
)
@pytest.mark.parametrize(
    "plan, profile",
    list(_PLANS_WITH_FUTURE_EXOG.values()),
    ids=list(_PLANS_WITH_FUTURE_EXOG),
)
def test_render_forecast_script_output_reads_future_exog_in_its_own_encoding(
    plan, profile, exog_encoding, encoding_arg
):
    """
    Test that every family of forecaster reads the data file in the
    encoding of the profile (cp1252 here) and `exog_future.csv` in
    the encoding of `exog_file`, its own, which may be UTF-8 (no argument).
    """
    profile = profile.model_copy(
        update={"data_path": "excel.csv", "csv_encoding": "cp1252"}
    )

    script = render_forecast_script(
                 profile, plan, exog_file=FutureExogFile(encoding=exog_encoding)
             ).full_script

    assert "data = pd.read_csv('excel.csv', encoding='cp1252'" in script
    assert f"exog_future = pd.read_csv('exog_future.csv'{encoding_arg}" in script
    assert script.count("encoding='cp1252'") == (2 if encoding_arg else 1)


@pytest.mark.parametrize(
    "plan, profile",
    list(_PLANS_WITH_FUTURE_EXOG.values()),
    ids=list(_PLANS_WITH_FUTURE_EXOG),
)
def test_render_forecast_script_output_reads_future_exog_file_with_its_dialect(
    plan, profile
):
    """
    Test that every family of forecaster reads the future exogenous
    variables from the file they were read from, by its path, with its
    separator, decimal mark, thousands separator, encoding and date format
    (the Excel in Spanish), and not from `exog_future.csv`, also when the
    data file is written as `to_csv()` writes it.
    """
    exog_file = FutureExogFile(
                    path        = "/datos/futuro.csv",
                    sep         = ";",
                    decimal     = ",",
                    thousands   = ".",
                    encoding    = "cp1252",
                    date_format = "%d/%m/%Y",
                    date_column = "date",
                )
    profile = profile.model_copy(update={"data_path": "/datos/ventas.csv"})

    script = render_forecast_script(profile, plan, exog_file).full_script

    text_columns = (
        "'series_id': str, 'date': str" if profile.series_id_column
        else "'date': str"
    )
    assert "data = pd.read_csv('/datos/ventas.csv'" in script
    assert "data = pd.read_csv('/datos/ventas.csv', sep" not in script
    assert (
        f"exog_future = pd.read_csv('/datos/futuro.csv', sep=';', decimal=',', "
        f"thousands='.', encoding='cp1252', dtype={{{text_columns}}})\n"
    ) in script
    assert (
        "exog_future['date'] = pd.to_datetime(exog_future['date'], "
        "format='%d/%m/%Y')\n" in script
    )
    assert "exog_future.csv" not in script
