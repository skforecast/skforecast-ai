# Unit test check_unchanged

import pytest

from skforecast_ai.mcp._errors import ServerError
from skforecast_ai.mcp._inputs import check_unchanged, file_sha256


def test_check_unchanged_passes_and_raises_data_changed(tmp_path):
    """
    Test that a file with its fingerprint passes, and that a file that
    changed raises `data_changed` naming the argument.
    """
    path = tmp_path / "data.csv"
    path.write_text("date,y\n2020-01-01,1\n")
    digest = file_sha256(str(path))

    check_unchanged(str(path), digest, "data_path")
    path.write_text("date,y\n2020-01-01,2\n")
    with pytest.raises(ServerError) as excinfo:
        check_unchanged(str(path), digest, "exog_path")

    assert digest == "fccc6e599b960d79f12a072e45c55acdb1286a846b09655152cdf861f82fc712"
    assert excinfo.value.code == "data_changed"
    assert excinfo.value.field == "exog_path"
    assert excinfo.value.details == {"path": str(path)}
