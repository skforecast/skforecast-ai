# Unit test _unwrap_cv

import re

import pytest

from skforecast.model_selection import TimeSeriesFold

from skforecast_ai import ForecastingAssistant
from skforecast_ai._utils import _unwrap_cv
from skforecast_ai.exceptions import InvalidInputTypeError

from tests.fixtures_assistant import df_single


def test_unwrap_cv_output_when_time_series_fold():
    """
    Test that a TimeSeriesFold is returned as it is.
    """
    cv = TimeSeriesFold(steps=5, initial_train_size=70, verbose=False)

    assert _unwrap_cv(cv) is cv


def test_unwrap_cv_output_when_cv_result():
    """
    Test that the CVResult of create_cv() gives the splitter it holds.
    """
    assistant = ForecastingAssistant()
    profile = assistant.profile(data=df_single, target="sales", date_column="date")
    plan = assistant.plan(profile, steps=5)
    cv_result = assistant.create_cv(profile, plan)

    assert _unwrap_cv(cv_result) is cv_result.cv


@pytest.mark.parametrize(
    "cv, type_name",
    [({"steps": 5}, "dict"), (None, "NoneType"), (5, "int")],
    ids=["dict", "None", "int"],
)
def test_unwrap_cv_InvalidInputTypeError_when_wrong_type(cv, type_name):
    """
    Test that a `cv` that is not a TimeSeriesFold nor a CVResult raises
    InvalidInputTypeError (a TypeError) with the field 'cv'.
    """
    err_msg = re.escape(
        f"`cv` must be a skforecast TimeSeriesFold or the CVResult of "
        f"create_cv(), got {type_name}."
    )
    with pytest.raises(InvalidInputTypeError, match=err_msg) as exc_info:
        _unwrap_cv(cv)

    assert isinstance(exc_info.value, TypeError)
    assert exc_info.value.code == "invalid_argument"
    assert exc_info.value.field == "cv"
