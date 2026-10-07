# Unit test tool profile

import pandas as pd
import pytest

from skforecast_ai import ForecastingAssistant
from skforecast_ai.mcp import create_server, server as server_module
from skforecast_ai.mcp.models import ToolNotice

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
    path = write_csv(tmp_path, "names.csv", frame)
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


def test_tool_profile_invalid_argument_when_dates_day_first(tmp_path):
    """
    Test that day-first dates whose first date also reads month-first are
    `invalid_argument` on `data_path`, with a hint that asks for ISO 8601
    and needs no Python.
    """
    frame = df_h2o_csv.assign(
        fecha=pd.date_range("2023-01-01", periods=len(df_h2o_csv), freq="D")
        .strftime("%d/%m/%Y")
    )
    path = write_csv(tmp_path, "dayfirst.csv", frame)
    server = create_server(allow_dir=tmp_path, output_dir=tmp_path / "out")

    error = error_of(
        call(server, "profile", {"data_path": path, "target": "x"}), "profile"
    )

    assert (error["code"], error["field"]) == ("invalid_argument", "data_path")
    assert error["message"].startswith(
        "The dates of column 'fecha' are written day first, but the first "
        "one, '01/01/2023', also reads month first ('%m/%d/%Y')"
    )
    assert error["hint"] == (
        "Write the dates of the column in ISO 8601, such as '2023-01-13'."
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
