# Unit test tool profile

import csv

import pandas as pd
import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp import create_server, server as server_module
from skforecast_ai.mcp.models import ToolNotice
from skforecast_ai.profiling.data_profile import DAYFIRST_HINT

from ..fixtures_csv_dialect import (
    df_dialect,
    df_dialect_thousands,
    write_dialect,
    write_thousands,
)
from ..fixtures_assistant import df_multi_long_numeric_ids
from ..fixtures_datasets import df_items_sales_long, df_mixed_date_formats
from .fixtures_mcp import (
    DATA_WARNING,
    GAPS_WARNING,
    ID_PATTERN,
    call,
    content_of,
    df_data_warning,
    df_h2o_csv,
    df_h2o_gaps_csv,
    error_of,
    h2o_server,
    run_session,
    write_csv,
)


def test_tool_profile_output_matches_python_api(tmp_path):
    """
    Test that `profile` registers a profile whose summary is `describe()` of
    the profile the Python API builds from the same file, with no links,
    notices, files, cost or changeable arguments, and no values.
    """
    path = write_csv(tmp_path, "h2o.csv", df_h2o_csv)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    result = content_of(call(server, "profile", {"data_path": path, "target": "x"}))
    expected = ForecastingAssistant().profile(path, target="x").describe()

    assert ID_PATTERN.fullmatch(result["id"])
    assert result["id"].startswith("profile-1-")
    assert result == {
        "id": result["id"],
        "kind": "profile",
        "links": {},
        "summary": expected,
        "summary_truncated": False,
        "notices": [],
        "notices_omitted": 0,
        "files": {},
        "values_included": False,
        "cost": None,
        "changeable": [],
    }


def test_tool_profile_summary_of_h2o(tmp_path):
    """
    Test the summary of the h2o profile: statistics, decisions and suggested
    features, without any value of the data.
    """
    path = write_csv(tmp_path, "h2o.csv", df_h2o_csv)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    result = content_of(call(server, "profile", {"data_path": path, "target": "x"}))

    assert result["summary"] == (
        "<forecast_context>\n"
        "<dataset>\n"
        "- Observations: 204\n"
        "- Series: 1\n"
        "- Frequency: MS\n"
        "- Date range: 1991-07-01 to 2008-06-01\n"
        "- Target: x\n"
        "- Exogenous columns: none\n"
        "- Target statistics: min 0.3362, max 1.257, mean 0.7682, std 0.2251\n"
        "- Missing values: none\n"
        "- Index irregularities: none detected\n"
        "</dataset>\n"
        "<profile_decision>\n"
        "A single-series ML forecaster (ForecasterRecursive) is recommended. "
        "Data: 204 observations, 'MS' frequency. Alternative forecasters: "
        "['ForecasterDirect', 'ForecasterFoundation', 'ForecasterStats']. "
        "Estimator: Ridge. A linear model is preferred because the dataset is "
        "small (204 observations < 250); gradient boosting is offered as an "
        "alternative once more data is available. Alternative estimators: "
        "['RandomForestRegressor', 'LGBMRegressor'].\n"
        "- Significant lags (partial autocorrelation, strongest first): 1, 13, "
        "12, 11, 10, 14, 9\n"
        "- Suggested window features: mean(window=3), std(window=3), "
        "mean(window=12), mean(window=36)\n"
        "- Suggested calendar features: month, quarter\n"
        "</profile_decision>\n"
        "</forecast_context>"
    )


def test_tool_profile_output_long_format(tmp_path):
    """
    Test that long-format data is profiled with its series id column, as by
    the Python API.
    """
    path = write_csv(tmp_path, "items.csv", df_items_sales_long)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    result = content_of(
        call(
            server,
            "profile",
            {
                "data_path": path,
                "target": "value",
                "series_id_column": "series",
            },
        )
    )
    expected = (
        ForecastingAssistant()
        .profile(path, target="value", series_id_column="series")
        .describe()
    )

    assert result["summary"] == expected


def test_tool_profile_notices_of_the_data(tmp_path):
    """
    Test that a warning emitted while profiling is a notice with source
    'data'.
    """
    path = write_csv(tmp_path, "warning.csv", df_data_warning)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    result = content_of(call(server, "profile", {"data_path": path, "target": "y"}))

    assert [ToolNotice(**n) for n in result["notices"]] == [
        ToolNotice(source="data", category="UserWarning", message=DATA_WARNING, count=1)
    ]


def test_tool_profile_summary_cut_with_full_text_in_a_file(tmp_path, monkeypatch):
    """
    Test that a summary longer than the limit is cut and its full text is
    written to a file in the output directory.
    """
    monkeypatch.setattr(server_module, "MAX_SUMMARY_CHARS", 100)
    path = write_csv(tmp_path, "h2o.csv", df_h2o_csv)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    result = content_of(call(server, "profile", {"data_path": path, "target": "x"}))
    expected = ForecastingAssistant().profile(path, target="x").describe()
    summary_path = tmp_path / "out" / f"{result['id']}-summary.txt"

    assert result["summary"] == expected[:100]
    assert result["summary_truncated"] is True
    assert result["files"] == {"summary": str(summary_path)}
    assert summary_path.read_text(encoding="utf-8") == expected


@pytest.mark.parametrize(
    "arguments, field, message",
    [
        (
            {"target": "nope"},
            "target",
            "Target column(s) ['nope'] not found in the DataFrame. Available "
            "columns: ['fecha', 'x']",
        ),
        (
            {"target": "x\n"},
            "target",
            "`target` holds a line break or another control character: 'x\\n'.",
        ),
        (
            {"target": ["x"], "date_column": "fe\u2028cha"},
            "date_column",
            "`date_column` holds a line break or another control character: "
            "'fe\\u2028cha'.",
        ),
        ({"target": 1}, "target", None),
        ({"target": "x", "date": "fecha"}, "date", "Extra inputs are not permitted"),
        (
            {"target": "x", "exog_columns": ["nope"]},
            "exog_columns",
            "`exog_columns` names columns that are not in the data: ['nope']. "
            "Columns of the data: ['fecha', 'x'].",
        ),
        (
            {"target": "x", "exog_columns": ["x"]},
            "exog_columns",
            "`exog_columns` names the target, the date or the series id "
            "column: ['x']. An exogenous variable is any other column of the "
            "data.",
        ),
        (
            {"target": "x", "exog_columns": ["a\nb"]},
            "exog_columns",
            "`exog_columns` holds a line break or another control character: "
            "'a\\nb'.",
        ),
        ({"target": "x", "exog_columns": "z"}, "exog_columns", None),
    ],
    ids=lambda dt: f"{dt}",
)
def test_tool_profile_invalid_argument(tmp_path, arguments, field, message):
    """
    Test that an invalid argument is `invalid_argument` naming the argument:
    a target the data does not have, a control character in a column name,
    a wrong type and an unknown argument.
    """
    path = write_csv(tmp_path, "h2o.csv", df_h2o_csv)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    error = error_of(
        call(server, "profile", {"data_path": path, **arguments}), "profile"
    )

    assert error["code"] == "invalid_argument"
    assert error["field"] == field
    if message is not None:
        assert error["message"] == message


def test_tool_profile_rejects_column_names_with_line_breaks(tmp_path):
    """
    Test that data whose column names or series ids hold a line break is
    rejected, since those names reach the agent in every summary, and that
    nothing is registered.
    """
    frame = df_h2o_csv.assign(**{"Temperature\n(C)": 1.0, "exog\r": 2.0})
    # Every text between quotes: Python 3.10 does not quote a name that
    # ends in a carriage return, which then reads as the end of the line.
    path = str(tmp_path / "names.csv")
    frame.to_csv(path, index=False, quoting=csv.QUOTE_NONNUMERIC)
    long = df_items_sales_long.replace({"series": {"item_1": "item\u20291"}})
    long_path = write_csv(tmp_path, "long.csv", long)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    error = error_of(
        call(server, "profile", {"data_path": path, "target": "x"}), "profile"
    )
    error_long = error_of(
        call(
            server,
            "profile",
            {
                "data_path": long_path,
                "target": "value",
                "series_id_column": "series",
            },
        ),
        "profile",
    )

    assert error["code"] == "invalid_argument"
    assert error["field"] == "data_path"
    assert error["message"].startswith(
        "The data has column names or series ids with a line break or another "
        "control character: 'Temperature\\n(C)', 'exog\\r'."
    )
    assert error_long == {
        "code": "invalid_argument",
        "message": (
            "The data has column names or series ids with a line break or "
            "another control character: 'item\\u20291'. The server does not "
            "accept them, since they reach the agent as text."
        ),
        "field": "data_path",
        "hint": "Rename those columns (or series) in the CSV file.",
        "details": None,
    }
    assert content_of(call(server, "list_objects", {}))["objects"] == []


def test_tool_profile_output_when_dates_day_first(tmp_path):
    """
    Test that day-first dates whose first date also reads month-first
    ('01/01/2023', then '13/01/2023') are profiled day first, daily, as the
    Python API profiles them.
    """
    frame = df_h2o_csv.assign(
        fecha=pd.date_range("2023-01-01", periods=len(df_h2o_csv), freq="D")
        .strftime("%d/%m/%Y")
    )
    path = write_csv(tmp_path, "dayfirst.csv", frame)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    result = content_of(call(server, "profile", {"data_path": path, "target": "x"}))
    expected = ForecastingAssistant().profile(path, target="x")

    assert expected.data_profile.date_format == "%d/%m/%Y"
    assert result["summary"] == expected.describe()
    assert "- Frequency: D\n" in result["summary"]
    assert "- Date range: 2023-01-01 to 2023-07-23\n" in result["summary"]


def test_tool_profile_end_to_end_when_dates_read_day_first_and_month_first(tmp_path):
    """
    Test the session of a long-format file whose dates all read both day
    first and month first (monthly, on the first day): `profile` fails with
    `data_unreadable` and the hint that names `dayfirst`; with `dayfirst`
    true the data are monthly, `forecast` reads the future values of the
    series written in the same order, and the script of `get_code` reads
    the dates of both files with the day-first format.
    """
    dates = pd.date_range("2018-01-01", periods=36, freq="MS")
    frame = pd.DataFrame({
        "store": ["a"] * 36 + ["b"] * 36,
        "date": list(dates.strftime("%d/%m/%Y")) * 2,
        "promo": [float(i % 2) for i in range(72)],
        "y": [100.0 + i % 12 + 3 * (i >= 36) for i in range(72)],
    })
    path = write_csv(tmp_path, "monthly.csv", frame)
    future = pd.DataFrame({
        "store": ["a"] * 3 + ["b"] * 3,
        "date": ["01/01/2021", "01/02/2021", "01/03/2021"] * 2,
        "promo": [1.0, 0.0, 1.0, 1.0, 0.0, 1.0],
    })
    exog_path = write_csv(tmp_path, "future.csv", future)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    arguments = {"data_path": path, "target": "y", "series_id_column": "store"}

    error = error_of(call(server, "profile", arguments), "profile")

    async def steps(client):
        profile = content_of(
            await client.call_tool("profile", {**arguments, "dayfirst": True})
        )
        plan = content_of(
            await client.call_tool("plan", {"profile_id": profile["id"], "steps": 3})
        )
        forecast = content_of(
            await client.call_tool(
                "forecast", {"plan_id": plan["id"], "exog_path": exog_path}
            )
        )
        code = content_of(
            await client.call_tool("get_code", {"object_id": forecast["id"]})
        )
        return profile, forecast, code

    profile, forecast, code = run_session(server, steps)

    assert (error["code"], error["field"]) == ("data_unreadable", "data_path")
    assert error["message"].startswith(
        "The dates of column 'date' read both day first and month first: no "
        "day is after the 12th, so '01/02/2018' may be '2018-02-01' or "
        "'2018-01-02'"
    )
    assert error["hint"] == DAYFIRST_HINT
    assert "- Frequency: MS\n" in profile["summary"]
    predictions = pd.read_csv(forecast["files"]["predictions"])
    assert sorted(set(predictions.iloc[:, 0])) == [
        "2021-01-01", "2021-02-01", "2021-03-01"
    ]
    assert (
        "data['date'] = pd.to_datetime(data['date'], format='%d/%m/%Y')\n"
        in code["code"]
    )
    assert (
        "exog_future['date'] = pd.to_datetime(exog_future['date'], "
        "format='%d/%m/%Y')\n" in code["code"]
    )


def test_tool_profile_output_when_exog_columns(tmp_path):
    """
    Test that `exog_columns` reaches `profile()`: the summary is `describe()`
    of the profile the Python API builds with it, and the note naming the
    columns left out is a notice with source 'data'.
    """
    frame = df_h2o_csv.assign(z=1.0, w=2.0)
    path = write_csv(tmp_path, "h2o.csv", frame)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    result = content_of(
        call(
            server,
            "profile",
            {"data_path": path, "target": "x", "exog_columns": ["w"]},
        )
    )
    expected = ForecastingAssistant().profile(path, target="x", exog_columns=["w"])

    assert expected.data_profile.exog_columns == ["w"]
    assert result["summary"] == expected.describe()
    assert result["notices"] == [
        ToolNotice(
            source   = "data",
            category = "DataProfileWarning",
            message  = (
                "Columns of the data that the profile leaves out are not "
                "used: ['z']."
            ),
            count    = 1,
        ).model_dump()
    ]


def test_tool_profile_rejects_left_out_column_names_with_line_breaks(tmp_path):
    """
    Test that a column with a line break in its name is rejected also when
    `exog_columns` leaves it out, since the note of the profile names it.
    """
    frame = df_h2o_csv.assign(**{"Temperature\n(C)": 1.0, "w": 2.0})
    path = write_csv(tmp_path, "names.csv", frame)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    error = error_of(
        call(
            server,
            "profile",
            {"data_path": path, "target": "x", "exog_columns": ["w"]},
        ),
        "profile",
    )

    assert (error["code"], error["field"]) == ("invalid_argument", "data_path")
    assert content_of(call(server, "list_objects", {}))["objects"] == []


def test_tool_profile_invalid_argument_when_dates_in_more_than_one_format(tmp_path):
    """
    Test that a CSV whose dates are written in more than one format is
    `invalid_argument` with the remedy as `hint`, and that nothing is
    registered.
    """
    path = write_csv(tmp_path, "mixed.csv", df_mixed_date_formats)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    error = error_of(
        call(
            server,
            "profile",
            {"data_path": path, "target": "y", "date_column": "date"},
        ),
        "profile",
    )

    assert error == {
        "code": "invalid_argument",
        "message": (
            "The dates of column 'date' do not all follow the format of the "
            "first one ('%Y-%m-%d', read from '2015-01-01'), such as "
            "'2017/07/01 00:00': the generated script reads every date with "
            "the format of the first one. Write every date in the same "
            "format, such as '2017-07-01'."
        ),
        "field": "data_path",
        "hint": (
            "Write every date of the column in the same format, such as "
            "'2017-07-01'."
        ),
        "details": None,
    }
    assert content_of(call(server, "list_objects", {}))["objects"] == []


def test_tool_profile_data_changed_while_profiling(tmp_path, monkeypatch):
    """
    Test that a file that changes while it is profiled raises `data_changed`
    and registers nothing.
    """
    path = write_csv(tmp_path, "h2o.csv", df_h2o_csv)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    profile = ForecastingAssistant.profile

    def profile_and_append(self, *args, **kwargs):
        result = profile(self, *args, **kwargs)
        with open(path, "a") as handle:
            handle.write("2008-07-01,0.5\n")
        return result

    monkeypatch.setattr(ForecastingAssistant, "profile", profile_and_append)

    error = error_of(
        call(server, "profile", {"data_path": path, "target": "x"}), "profile"
    )

    assert error["code"] == "data_changed"
    assert error["field"] == "data_path"
    assert error["hint"] == "Call `profile` again on the file as it is now."
    assert content_of(call(server, "list_objects", {}))["objects"] == []


def test_tool_profile_text_arguments_are_never_decoded_as_json(tmp_path):
    """
    Test that a text argument is taken as written: a column named 'null' is
    the target (not a missing argument), and text that looks like a JSON list
    is one column name, not a list of columns.
    """
    frame = df_h2o_csv.rename(columns={"x": "null"})
    path = write_csv(tmp_path, "null.csv", frame)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    result = content_of(call(server, "profile", {"data_path": path, "target": "null"}))
    error = error_of(
        call(server, "profile", {"data_path": path, "target": '["null", "fecha"]'}),
        "profile",
    )

    assert "- Target: null\n" in result["summary"]
    assert error["field"] == "target"
    assert error["message"].startswith(
        'Target column(s) [\'["null", "fecha"]\'] not found in the DataFrame.'
    )


def test_tool_profile_file_too_large_before_reading_it(tmp_path, monkeypatch):
    """
    Test that a CSV file larger than `max_file_mb` is `file_too_large` before
    it is read (neither hashed nor profiled), and that 0 lifts the limit.
    """
    from skforecast_ai.mcp import _inputs

    path = write_csv(tmp_path, "h2o.csv", df_h2o_csv)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\n" * (1024 * 1024))
    limited = create_server(
        allow_dir=tmp_path, output_dir=tmp_path / "out", max_file_mb=1
    )
    unlimited = create_server(
        allow_dir=tmp_path, output_dir=tmp_path / "out", max_file_mb=0
    )
    read = []
    original = _inputs.file_sha256
    monkeypatch.setattr(
        _inputs, "file_sha256", lambda p: read.append(p) or original(p)
    )

    error = error_of(
        call(limited, "profile", {"data_path": path, "target": "x"}), "profile"
    )
    assert read == []
    result = call(unlimited, "profile", {"data_path": path, "target": "x"})

    assert (error["code"], error["field"]) == ("file_too_large", "data_path")
    assert content_of(result)["kind"] == "profile"


def test_tool_profile_notices_of_the_data_profile_warnings(tmp_path):
    """
    Test that the warnings the profile records without emitting them
    (`data_profile.warnings`, here three missing months) reach the agent as
    notices with source 'data' and the category 'DataProfileWarning'.
    """
    path = write_csv(tmp_path, "gaps.csv", df_h2o_gaps_csv)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    result = content_of(call(server, "profile", {"data_path": path, "target": "x"}))

    assert [ToolNotice(**n) for n in result["notices"]] == [
        ToolNotice(
            source   = "data",
            category = "DataProfileWarning",
            message  = GAPS_WARNING,
            count    = 1,
        )
    ]


def test_tool_profile_and_plan_notice_when_the_target_has_missing_values(tmp_path):
    """
    Test that a target with a few missing values (its last 3 rows, below the
    20 % the profile warns about) gives a 'DataProfileWarning' notice on
    profile and again on plan: without it both returned no notice, and the
    problem only showed when `forecast` failed.
    """
    data = df_h2o_csv.copy()
    data.loc[data.index[-3:], "x"] = None
    path = write_csv(tmp_path, "trailing.csv", data)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    profile = content_of(call(server, "profile", {"data_path": path, "target": "x"}))
    plan = content_of(call(server, "plan", {"profile_id": profile["id"], "steps": 12}))

    message = (
        "Missing values in the target: 'x': 3. `forecast` needs the data to end "
        "with a value of the target, and an estimator that does not accept "
        "missing values fails when its lags read one. Fill them in, or remove "
        "the rows at the end without a target, in a copy of the file."
    )
    for result in (profile, plan):
        assert message in [
            notice["message"] for notice in result["notices"]
            if notice["category"] == "DataProfileWarning"
        ]


def test_tool_profile_invalid_argument_names_every_problem_of_the_dates(tmp_path):
    """
    Test that a file with a date repeated with different values is rejected
    with a message that also counts the identical repeated rows and the
    missing dates, and with a hint that leaves the fix to the user: without
    it an agent writes a corrected copy without asking.
    """
    dates = pd.date_range("2015-01-01", periods=60, freq="MS").delete([10, 11, 30])
    frame = pd.DataFrame(
        {"date": dates.strftime("%Y-%m-%d"), "y": [float(i) for i in range(57)]}
    )
    frame = pd.concat(
        [frame, frame.iloc[[2]], frame.iloc[[9]].assign(y=99.0)], ignore_index=True
    )
    path = write_csv(tmp_path, "dirty.csv", frame)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    error = error_of(
        call(server, "profile", {"data_path": path, "target": "y"}), "profile"
    )

    assert (error["code"], error["field"]) == ("invalid_argument", "data_path")
    assert error["message"] == (
        "Found 1 timestamp with more than one row and different values, for "
        "example '2015-10-01'. A single series needs one row per timestamp, "
        "and keeping only one of them would silently discard data. Aggregate "
        "or remove the repeated rows before profiling, or pass "
        "`series_id_column` if a column identifies different series. The same "
        "data also has 1 other timestamp repeated in identical rows (profiling "
        "keeps one of them) and 3 timestamps missing at the 'MS' frequency, "
        "which will still be missing once the repeated rows are solved."
    )
    assert error["hint"] == (
        "This is a problem of the file of the user, and how to solve it is "
        "their decision. Tell them every problem the message names and ask "
        "before writing a corrected copy; never change their file."
    )


def test_tool_profile_without_target_lists_the_columns(tmp_path):
    """
    Test that `profile` without `target` (omitted or null) is
    `invalid_argument` on `target` with the columns of the file and a hint
    to pass one or ask the user, so an agent need not make up a target to
    read them, and that nothing is registered.
    """
    server, path = h2o_server(tmp_path)

    omitted = error_of(call(server, "profile", {"data_path": path}), "profile")
    null = error_of(
        call(server, "profile", {"data_path": path, "target": None}), "profile"
    )
    objects = content_of(call(server, "list_objects", {}))["objects"]

    assert omitted == null == {
        "code": "invalid_argument",
        "message": "`target` was not given. Columns of the file: ['fecha', 'x'].",
        "field": "target",
        "hint": (
            "Pass the column to forecast as `target`. If more than one could "
            "be it, ask the user."
        ),
        "details": None,
    }
    assert objects == []


def test_tool_profile_without_target_checks_the_path_and_the_file_first(tmp_path):
    """
    Test that `profile` without `target` checks the file as with one before
    reading its columns: a file outside the allowed directory is
    `path_not_allowed`, a missing one `data_not_found`, one above the limit
    `file_too_large` and one that is not a CSV `data_unreadable`.
    """
    allowed = tmp_path / "data"
    allowed.mkdir()
    outside = write_csv(tmp_path, "outside.csv", df_h2o_csv)
    large = write_csv(allowed, "large.csv", df_h2o_csv)
    with open(large, "a", encoding="utf-8") as handle:
        handle.write("\n" * (1024 * 1024))
    binary = allowed / "binary.csv"
    binary.write_bytes(b"\xff\xfe\x00\x01")
    server = create_server(
        allow_dir=allowed, output_dir=tmp_path / "out", max_file_mb=1
    )

    codes = [
        error_of(call(server, "profile", {"data_path": str(path)}), "profile")["code"]
        for path in (outside, allowed / "missing.csv", large, binary)
    ]

    assert codes == [
        "path_not_allowed", "data_not_found", "file_too_large", "data_unreadable",
    ]


@pytest.mark.parametrize(
    "name",
    ["semicolon_comma", "semicolon_dot", "tab_dot", "tab_comma", "tsv",
     "gz_comma_dot", "gz_semicolon_comma"],
)
def test_tool_profile_output_when_file_has_another_dialect(tmp_path, name):
    """
    Test that `profile` reads a ';' or tab file, with a decimal comma, a
    '.tsv' file and gzip files as the Python API does, and that its summary is
    that of the comma file.
    """
    path = write_dialect(tmp_path, df_dialect, name)
    comma_path = write_csv(tmp_path, "us.csv", df_dialect)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    result = content_of(call(server, "profile", {"data_path": path, "target": "y"}))
    expected = content_of(
        call(server, "profile", {"data_path": comma_path, "target": "y"})
    )

    assert result["kind"] == "profile"
    assert result["summary"] == expected["summary"]
    assert result["summary"] == ForecastingAssistant().profile(
        path, target="y"
    ).describe()
    assert result["notices"] == []


@pytest.mark.parametrize(
    "arguments",
    [{"sep": ";", "decimal": ","}, {"sep": ";"}, {"decimal": ","}],
    ids=["both", "sep", "decimal"],
)
def test_tool_profile_output_when_sep_and_decimal_given(tmp_path, arguments):
    """
    Test that `sep` and `decimal` are passed to the profile, the one not given
    being detected.
    """
    path = write_dialect(tmp_path, df_dialect, "semicolon_comma")
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    result = content_of(
        call(server, "profile", {"data_path": path, "target": "y", **arguments})
    )

    assert result["summary"] == ForecastingAssistant().profile(
        path, target="y"
    ).describe()


def test_tool_profile_error_when_dialect_is_ambiguous(tmp_path):
    """
    Test that a file whose separator cannot be told is `data_unreadable`,
    naming `data_path`, with the hint of the library that says how to give
    `sep` and `decimal`, also when `target` is not given; giving `sep` reads
    it.
    """
    path = tmp_path / "ambiguous.csv"
    df_dialect.rename(columns={"y": "y,x"}).to_csv(
        path, sep=";", decimal=",", index=False
    )
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    errors = [
        error_of(call(server, "profile", {"data_path": str(path), **target}), "profile")
        for target in ({"target": "y,x"}, {})
    ]
    result = content_of(
        call(server, "profile", {"data_path": str(path), "target": "y,x", "sep": ";"})
    )

    for error in errors:
        assert error == {
            "code": "data_unreadable",
            "message": (
                f"The separator of the CSV file '{path.resolve()}' cannot be "
                f"told: its header reads with ',' (2 columns) and ';' "
                f"(2 columns)."
            ),
            "field": "data_path",
            "hint": (
                "Profile the file saying how it is written, with `sep` (',', "
                "';' or a tabulator) and `decimal` ('.' or ',') in "
                "`profile()`, `--sep` and `--decimal` in the `profile` "
                "command, or `sep` and `decimal` in the `profile` tool of the "
                "MCP server, and use that profile."
            ),
            "details": None,
        }
    assert result["kind"] == "profile"


@pytest.mark.parametrize(
    "arguments, field",
    [
        ({"sep": "|"}, "sep"),
        ({"decimal": ";"}, "decimal"),
        ({"sep": ",", "decimal": ","}, "decimal"),
    ],
    ids=["sep", "decimal", "decimal comma with sep comma"],
)
def test_tool_profile_error_when_sep_or_decimal_not_valid(tmp_path, arguments, field):
    """
    Test that a `sep` or `decimal` that is not accepted, or a decimal comma
    with `sep` ',', is `invalid_argument` naming the argument.
    """
    path = write_dialect(tmp_path, df_dialect, "semicolon_comma")
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    error = error_of(
        call(server, "profile", {"data_path": path, "target": "y", **arguments}),
        "profile",
    )

    assert error["code"] == "invalid_argument"
    assert error["field"] == field


def test_tool_profile_without_target_lists_the_columns_of_a_semicolon_file(tmp_path):
    """
    Test that `profile` without `target` reads the columns of a ';' file with
    its dialect, and so names 'date' and 'y' instead of one column.
    """
    path = write_dialect(tmp_path, df_dialect, "semicolon_comma")
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    error = error_of(call(server, "profile", {"data_path": path}), "profile")

    assert error["code"] == "invalid_argument"
    assert error["field"] == "target"
    assert "'date'" in error["message"]
    assert "'y'" in error["message"]
    assert "date;y" not in error["message"]


def _monthly_lines(n: int = 36) -> list[str]:
    """
    Lines of a monthly CSV file with a date and a target column.
    """
    dates = pd.date_range("2015-01-01", periods=n, freq="MS").strftime("%Y-%m-%d")
    return ["date,y"] + [f"{date},{100 + i * 0.5}" for i, date in enumerate(dates)]


_LINES = _monthly_lines()


@pytest.mark.parametrize(
    "lines, message",
    [
        (
            [_LINES[0]] + [line + "," for line in _LINES[1:]],
            "its header has 2 fields and its first row 3, so the first column "
            "would be read as the row labels and every other column would move "
            "one place (the rows end with separators that the header does not "
            "have).",
        ),
        (
            _LINES[:1] + [_LINES[1] + ",9"] + _LINES[2:],
            "its header has 2 fields and its first row 3, so the first column "
            "would be read as the row labels and every other column would move "
            "one place (a field too many in the first row, or a header without "
            "a name for the first column).",
        ),
        (
            _LINES[:20] + [_LINES[20] + ",9"] + _LINES[21:],
            "Error tokenizing data. C error: Expected 2 fields in line 21, saw 3",
        ),
        (
            [line + "," for line in _LINES],
            "column 'Unnamed: 2' has no name in the header and no values (often "
            "a separator at the end of every line, the header included).",
        ),
    ],
    ids=["separator at the end of every row", "field too many in the first row",
         "field too many in a middle row", "separator at the end of every line"],
)
def test_tool_profile_data_unreadable_when_rows_longer_than_header(
    tmp_path, lines, message
):
    """
    Test that a file whose rows have more fields than its header is
    `data_unreadable` naming `data_path`, with or without `target`, instead
    of a target without values or a profile with the dates as an exogenous
    variable, and that the same file without the extra fields is profiled.
    """
    path = tmp_path / "data.csv"
    path.write_text("\n".join(lines) + "\n")
    fixed = tmp_path / "fixed.csv"
    fixed.write_text("\n".join(_LINES) + "\n")
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    errors = [
        error_of(call(server, "profile", {"data_path": str(path), **target}), "profile")
        for target in ({"target": "y"}, {})
    ]
    result = content_of(
        call(server, "profile", {"data_path": str(fixed), "target": "y"})
    )

    for error in errors:
        assert error["code"] == "data_unreadable"
        assert error["field"] == "data_path"
        assert error["message"] == (
            f"The CSV file '{path.resolve()}' could not be read: {message}"
        )
        assert error["hint"]
    assert result["kind"] == "profile"
    assert "- Frequency: MS" in result["summary"]
    assert "- Exogenous columns: none" in result["summary"]


@pytest.mark.parametrize(
    "decimals",
    [True, False],
    ids=["thousands and decimal comma", "whole numbers with and without separator"],
)
def test_tool_profile_plan_and_forecast_when_point_separates_thousands(
    tmp_path, decimals
):
    """
    Test that `profile` reads a ';' file with '.' between thousands
    ('1.020,50', or '870' next to '1.020') as the same amounts written with
    ',' and '.': the same summary and notices, and a plan and a forecast with
    the same predictions.
    """
    path = write_thousands(tmp_path, df_dialect_thousands, decimals=decimals)
    amounts = df_dialect_thousands.assign(
        y=df_dialect_thousands["y"] if decimals else df_dialect_thousands["y"].round()
    )
    comma_path = write_csv(tmp_path, "us.csv", amounts)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    results = {}
    for data_path in (path, comma_path):
        profile = content_of(
            call(server, "profile", {"data_path": data_path, "target": "y"})
        )
        plan = content_of(
            call(server, "plan", {"profile_id": profile["id"], "steps": 6})
        )
        forecast = content_of(call(server, "forecast", {"plan_id": plan["id"]}))
        results[data_path] = (profile, forecast)

    profile, forecast = results[path]
    expected_profile, expected_forecast = results[comma_path]
    assert profile["summary"] == expected_profile["summary"]
    assert profile["notices"] == expected_profile["notices"]
    assert forecast["notices"] == expected_forecast["notices"]
    pd.testing.assert_frame_equal(
        pd.read_csv(forecast["files"]["predictions"]),
        pd.read_csv(expected_forecast["files"]["predictions"]),
    )


def test_tool_profile_error_when_thousands_are_ambiguous(tmp_path):
    """
    Test that a ';' file whose only numbers with a '.' read both as
    thousands and as numbers with three decimals is `data_unreadable`,
    naming `data_path`, with the hint that asks for `thousands` or
    `decimal`; giving `thousands` reads the amounts as thousands and giving
    `decimal` '.' as numbers with three decimals.
    """
    path = tmp_path / "thousands.csv"
    path.write_text(
        "date;y\n" + "".join(
            f"2020-{month:02d}-01;{1 + month % 3}.{month:03d}\n"
            for month in range(1, 13)
        )
    )
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    error = error_of(
        call(server, "profile", {"data_path": str(path), "target": "y"}), "profile"
    )
    with_thousands = content_of(
        call(
            server, "profile",
            {"data_path": str(path), "target": "y", "thousands": "."},
        )
    )
    with_decimals = content_of(
        call(server, "profile", {"data_path": str(path), "target": "y", "decimal": "."})
    )

    assert error == {
        "code": "data_unreadable",
        "message": (
            f"The thousands separator of the CSV file '{path.resolve()}' cannot "
            f"be told: its numbers with a '.' (such as '2.001') read both as "
            f"thousands and as numbers with three decimals."
        ),
        "field": "data_path",
        "hint": (
            "Profile the file saying what its '.' is: `thousands` '.' when it "
            "separates the thousands, or `decimal` '.' when it is the decimal "
            "mark, in `profile()`, `--thousands` or `--decimal` in the "
            "`profile` command, or `thousands` or `decimal` in the `profile` "
            "tool of the MCP server, and use that profile."
        ),
        "details": None,
    }
    assert "Target statistics: min 1003, max 3011," in with_thousands["summary"]
    assert "Target statistics: min 1.003, max 3.011," in with_decimals["summary"]


@pytest.mark.parametrize(
    "arguments",
    [
        {"thousands": ","},
        {"thousands": ".", "sep": ","},
        {"thousands": ".", "decimal": "."},
    ],
    ids=["comma", "with sep comma", "with decimal point"],
)
def test_tool_profile_error_when_thousands_not_valid(tmp_path, arguments):
    """
    Test that a `thousands` that is not accepted, or '.' with `sep` ',' or
    `decimal` '.', is `invalid_argument` naming `thousands`.
    """
    path = write_dialect(tmp_path, df_dialect, "semicolon_comma")
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    error = error_of(
        call(server, "profile", {"data_path": path, "target": "y", **arguments}),
        "profile",
    )

    assert error["code"] == "invalid_argument"
    assert error["field"] == "thousands"


@pytest.mark.parametrize(
    "values, written",
    [
        (["10,025.1", "11,023.6"], "with a thousands separator"),
        (["10.0%", "11.0%"], "with '%'"),
    ],
    ids=["thousands separator", "percent"],
)
def test_tool_profile_error_when_target_numbers_are_written_in_another_format(
    tmp_path, values, written
):
    """
    Test that a target whose numbers are written with a thousands separator
    or with '%' is an error of the file: it names `data_path`, says the
    format, and carries the hint that leaves the file to the user.
    """
    path = tmp_path / "formatted.csv"
    pd.DataFrame(
        {"date": ["2020-01-01", "2020-02-01"], "y": values}
    ).to_csv(path, index=False)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    error = error_of(
        call(server, "profile", {"data_path": str(path), "target": "y"}), "profile"
    )

    assert error == {
        "code": "invalid_argument",
        "message": (
            f"Target column 'y' is not numeric: values such as {values} are "
            f"numbers written {written}, a format that is not read. Write them "
            f"as plain numbers."
        ),
        "field": "data_path",
        "hint": server_module.DATA_PROBLEM_HINT,
        "details": None,
    }


def test_tool_profile_output_when_series_ids_are_numbers(tmp_path):
    """
    Test that the series ids of long-format data written as numbers ('001',
    '1', '10') name the series as written in the file, as by the Python API:
    '001' keeps its zeros and is not the series '1'.
    """
    path = write_csv(tmp_path, "stores.csv", df_multi_long_numeric_ids)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")
    arguments = {"target": "value", "series_id_column": "series_id"}

    result = content_of(call(server, "profile", {"data_path": path, **arguments}))
    expected = ForecastingAssistant().profile(path, **arguments)

    assert result["summary"] == expected.describe()
    assert list(expected.data_profile.series_lengths) == ["001", "1", "10"]
    assert [
        line.split("(")[1].split(")")[0]
        for line in result["summary"].splitlines()
        if line.startswith("- Target statistics (")
    ] == ["001", "1", "10"]
