# Unit test _display

import io
import re
import pytest
import numpy as np
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.console import Group

from skforecast_ai._display import (
    _format_value,
    _format_metric,
    _format_cell,
    render_code,
    render_explanation,
    render_dataframe,
    render_metrics,
    render_profile,
    render_plan,
    render_cv_config,
    DisplayMixin,
)
from skforecast_ai.schemas.profiles import ForecastingProfile, DataProfile
from skforecast_ai.schemas.plans import ForecastPlan
from skforecast_ai.schemas.results import (
    CodeGenerationResult,
    AskResult,
    ForecastResult,
    BacktestResult,
)


@pytest.fixture
def sample_dataframe():
    return pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})


@pytest.fixture
def sample_metrics():
    return pd.DataFrame({"MAE": [1.5], "MSE": [2.5]})


@pytest.fixture
def sample_profile():
    return ForecastingProfile(
        data_profile=DataProfile(
            target="target_col",
            date_column="date",
            frequency="D",
            rows=100,
            columns=2,
            missing_values=0,
            exog_columns=["exog1"],
            n_series=1,
            series_lengths={"target_col": 100},
            index_type="datetime",
        ),
        task_type="single_series",
        forecaster="ForecasterAutoreg",
        estimator="RandomForestRegressor",
        estimator_kwargs={"n_estimators": 100},
        lag_selection="lags=10",
        preprocessing=["StandardScaler()"],
        explanation="Sample explanation",
    )


@pytest.fixture
def sample_plan():
    return ForecastPlan(
        forecaster="ForecasterAutoreg",
        estimator="RandomForestRegressor",
        estimator_kwargs={"n_estimators": 100},
        steps=10,
        interval=[0.1, 0.9],
        lag_selection="lags=10",
        preprocessing=["StandardScaler()"],
        explanation="Sample explanation",
        task_type="single_series",
    )


def _render_to_text(renderable):
    """
    Render a Rich renderable to plain text (no colour, wide terminal).

    Rendering to text lets the tests assert on the actual displayed content
    instead of only the renderable type.
    """
    console = Console(width=200, color_system=None)
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


@pytest.mark.parametrize(
    "value, expected",
    [
        (True, "[green]True[/]"),
        (False, "[red]False[/]"),
        (None, "[dim]None[/]"),
        (10, "10"),
    ],
    ids=["bool_true", "bool_false", "none", "int"],
)
def test_format_value_returns_expected_markup(value, expected):
    """
    Test that _format_value applies the colour markup for booleans and None
    and leaves other values as their escaped string.
    """
    assert _format_value(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        (np.nan, "N/A"),
        (1.23456, "1.2346"),
        (2, "2.0000"),
        (True, "True"),
        ("abc", "abc"),
    ],
    ids=["nan", "float", "int", "bool", "str"],
)
def test_format_metric_returns_expected(value, expected):
    """
    Test that _format_metric renders NaN as 'N/A', numbers (including ints)
    with 4 decimals, and non-numeric values as their escaped string.
    """
    assert _format_metric(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        (np.nan, "N/A"),
        (1.23456, "1.2346"),
        (2, "2"),
        (np.int64(5), "5"),
        (np.float64(1.5), "1.5000"),
    ],
    ids=["nan", "float", "int", "np_int", "np_float"],
)
def test_format_cell_formats_floats_and_preserves_integers(value, expected):
    """
    Test that _format_cell renders NaN as 'N/A' and floats with 4 decimals
    while leaving integers untouched.
    """
    assert _format_cell(value) == expected


def test_render_code_wraps_in_titled_panel():
    """
    Test that render_code returns a Panel whose rendered output shows the
    title and the highlighted source.
    """
    result = render_code("print('marker')", title="My code")
    assert isinstance(result, Panel)
    text = _render_to_text(result)
    assert "My code" in text
    assert "marker" in text


def test_render_code_returns_bare_syntax_when_title_none():
    """
    Test that render_code returns the bare Syntax renderable (no panel) when
    title is None.
    """
    result = render_code("print('hello')", title=None)
    assert isinstance(result, Syntax)
    assert result.code == "print('hello')"


def test_render_explanation_renders_markdown_in_titled_panel():
    """
    Test that render_explanation returns a Panel showing the title and the
    rendered Markdown text.
    """
    result = render_explanation("Hello **world**", title="Notes")
    assert isinstance(result, Panel)
    text = _render_to_text(result)
    assert "Notes" in text
    assert "Hello" in text
    assert "world" in text


def test_render_dataframe_formats_floats_nan_and_preserves_integers():
    """
    Test that render_dataframe rounds floats to 4 decimals, renders NaN as
    'N/A', and leaves integer columns unformatted.
    """
    df = pd.DataFrame({"f": [0.123456789, np.nan], "i": [10, 20], "s": ["x", "y"]})
    text = _render_to_text(render_dataframe(df))
    assert "0.1235" in text
    assert "N/A" in text
    assert "10" in text
    assert "10.0000" not in text
    assert "x" in text


def test_render_dataframe_escapes_markup_in_cells():
    """
    Test that render_dataframe escapes Rich markup in cell values so literal
    brackets are shown verbatim instead of being interpreted as styles.
    """
    df = pd.DataFrame({"c": ["[red]hack[/]"]})
    text = _render_to_text(render_dataframe(df))
    assert "[red]hack[/]" in text


@pytest.mark.parametrize(
    "n_rows, truncated",
    [(10, False), (11, True)],
    ids=["boundary_not_truncated", "above_boundary_truncated"],
)
def test_render_dataframe_truncation_and_row_count_share_boundary(n_rows, truncated):
    """
    Test that the head/tail truncation and the '(N rows)' title label are
    driven by the same boundary: both appear only when the frame is longer
    than the previewable head plus tail.
    """
    df = pd.DataFrame({"v": range(n_rows)})
    text = _render_to_text(render_dataframe(df))
    assert ("..." in text) is truncated
    assert (f"({n_rows} rows)" in text) is truncated


def test_render_metrics_with_series_column_and_nan():
    """
    Test that render_metrics renders the 'Series' header for the series/levels
    column, formats metric floats, and shows NaN metrics as 'N/A'.
    """
    metrics = pd.DataFrame({"levels": ["a", "b"], "mae": [1.23456, np.nan]})
    text = _render_to_text(render_metrics(metrics))
    assert "Series" in text
    assert "a" in text
    assert "b" in text
    assert "1.2346" in text
    assert "N/A" in text


def test_render_metrics_metric_only_layout():
    """
    Test that render_metrics omits the 'Series' column when no series/levels
    column is present and formats every metric value.
    """
    metrics = pd.DataFrame({"mae": [1.5], "rmse": [2.5]})
    text = _render_to_text(render_metrics(metrics))
    assert "Series" not in text
    assert "1.5000" in text
    assert "2.5000" in text


def test_render_cv_config_renders_key_value_pairs():
    """
    Test that render_cv_config renders each parameter name with its formatted
    value, including booleans.
    """
    text = _render_to_text(render_cv_config({"initial_train_size": 50, "refit": False}))
    assert "initial_train_size" in text
    assert "50" in text
    assert "False" in text


def test_render_profile_includes_profile_recommendation_and_explanation(sample_profile):
    """
    Test that render_profile returns a Group whose rendered output shows the
    dataset profile, the recommendation, and the explanation.
    """
    result = render_profile(sample_profile)
    assert isinstance(result, Group)
    text = _render_to_text(result)
    assert "Dataset Profile" in text
    assert "Recommendation" in text
    assert "target_col" in text
    assert "ForecasterAutoreg" in text
    assert "Sample explanation" in text


def test_render_plan_includes_fields_and_explanation(sample_plan):
    """
    Test that render_plan returns a Group whose rendered output shows the plan
    fields and the explanation.
    """
    result = render_plan(sample_plan)
    assert isinstance(result, Group)
    text = _render_to_text(result)
    assert "Forecast Plan" in text
    assert "ForecasterAutoreg" in text
    assert "Sample explanation" in text


def test_render_plan_shows_na_when_estimator_missing(sample_plan):
    """
    Test that render_plan renders 'N/A' for the estimator when it is None.
    """
    plan = sample_plan.model_copy(update={"estimator": None})
    text = _render_to_text(render_plan(plan))
    assert "N/A" in text


def test_render_plan_shows_calendar_features_row(sample_plan):
    """
    Test that render_plan surfaces calendar features from forecaster_kwargs as
    a dedicated table row, including the feature names and encoding.
    """
    plan = sample_plan.model_copy(
        update={
            "forecaster_kwargs": {
                "calendar_features": {
                    "features": ["hour", "day_of_week"],
                    "encoding": "cyclical",
                }
            }
        }
    )
    text = _render_to_text(render_plan(plan))
    assert "Calendar features" in text
    assert "hour" in text
    assert "day_of_week" in text
    assert "cyclical" in text


def test_render_plan_shows_none_when_no_calendar_features(sample_plan):
    """
    Test that render_plan renders 'none' for calendar features when none are
    present in forecaster_kwargs.
    """
    text = _render_to_text(render_plan(sample_plan))
    assert "Calendar features" in text


def test_render_plan_marks_llm_refined_fields(sample_plan):
    """
    Test that render_plan flags lags and window features as LLM-suggested when
    they are listed in llm_refined_fields.
    """
    plan = sample_plan.model_copy(
        update={
            "forecaster_kwargs": {
                "lags": [1, 2, 7],
                "window_features": [{"stats": ["mean"], "window_size": 7}],
            },
            "llm_refined_fields": ["lags", "window_features"],
        }
    )
    text = _render_to_text(render_plan(plan))
    assert "LLM-suggested" in text


def test_render_plan_no_llm_marker_without_refined_fields(sample_plan):
    """
    Test that render_plan does not flag any field as LLM-suggested when
    llm_refined_fields is empty (deterministic plan).
    """
    plan = sample_plan.model_copy(
        update={"forecaster_kwargs": {"lags": [1, 2, 7]}}
    )
    text = _render_to_text(render_plan(plan))
    assert "LLM-suggested" not in text


class TestDisplayMixin:
    """
    Tests for the shared DisplayMixin rich-display protocol.
    """

    @staticmethod
    def _build_result(key, profile, plan, metrics, df):
        """
        Build a result object of the requested kind using the shared fixtures.
        """
        results = {
            "plan": plan,
            "profile": profile,
            "code_generation": CodeGenerationResult(
                code="print('x')", profile=profile, plan=plan
            ),
            "ask": AskResult(
                explanation="answer", code="print('x')", profile=profile, plan=plan
            ),
            "forecast": ForecastResult(
                code="print('x')",
                profile=profile,
                plan=plan,
                metrics=metrics,
                predictions=df,
            ),
            "backtest": BacktestResult(
                explanation="backtest",
                cv_config={"initial_train_size": 50, "steps": 10, "refit": False},
                metrics=metrics,
                predictions=df,
                code="print('x')",
                profile=profile,
                plan=plan,
            ),
        }
        return results[key]

    @pytest.mark.parametrize(
        "key",
        ["plan", "profile", "code_generation", "ask", "forecast", "backtest"],
    )
    def test_display_renders_to_console_and_jupyter(
        self, key, sample_profile, sample_plan, sample_metrics, sample_dataframe
    ):
        """
        Test that every result kind renders non-empty output to a console via
        show() and returns an HTML Jupyter mimebundle.
        """
        result = self._build_result(
            key, sample_profile, sample_plan, sample_metrics, sample_dataframe
        )

        console = Console(file=io.StringIO(), width=200, color_system=None)
        result.show(console=console)
        assert console.file.getvalue().strip() != ""

        mimebundle = result._repr_mimebundle_(include=[], exclude=[])
        assert "text/html" in mimebundle
        assert "<pre" in mimebundle["text/html"]

    def test_show_code_prints_highlighted_code(self, sample_profile, sample_plan):
        """
        Test that show_code prints the generated source to the console.
        """
        result = CodeGenerationResult(
            code="print('marker_code')", profile=sample_profile, plan=sample_plan
        )
        console = Console(file=io.StringIO(), width=200, color_system=None)
        result.show_code(console=console)
        assert "marker_code" in console.file.getvalue()

    def test_show_code_fallback_when_no_code(self):
        """
        Test that show_code prints a fallback message when the result has no
        code (e.g. an AskResult without generated code).
        """
        console = Console(file=io.StringIO(), width=200, color_system=None)
        AskResult(explanation="no code here").show_code(console=console)
        assert "No code available" in console.file.getvalue()

    def test_show_explanation_prints_rendered_explanation(self):
        """
        Test that show_explanation prints the explanation text to the console.
        """
        console = Console(file=io.StringIO(), width=200, color_system=None)
        AskResult(explanation="marker_explanation").show_explanation(console=console)
        assert "marker_explanation" in console.file.getvalue()

    def test_show_explanation_fallback_when_no_explanation(
        self, sample_profile, sample_plan
    ):
        """
        Test that show_explanation prints a fallback message when the result
        has no explanation (e.g. a CodeGenerationResult).
        """
        result = CodeGenerationResult(
            code="print('x')", profile=sample_profile, plan=sample_plan
        )
        console = Console(file=io.StringIO(), width=200, color_system=None)
        result.show_explanation(console=console)
        assert "No explanation available" in console.file.getvalue()

    def test_rich_console_not_implemented_in_base_mixin(self):
        """
        Test that a subclass which does not override __rich_console__ raises
        NotImplementedError when rendered.
        """
        class Dummy(DisplayMixin):
            pass

        err_msg = re.escape("Dummy must implement __rich_console__")
        with pytest.raises(NotImplementedError, match=err_msg):
            Console(file=io.StringIO()).print(Dummy())
