# Unit test read_row_lengths

import gzip

import pytest

from skforecast_ai.profiling.csv_dialect import read_row_lengths


@pytest.mark.parametrize(
    "text, sep, expected",
    [
        ("date,y\n2020-01-01,1,\n2020-01-02,2\n", ",", [3, 2]),
        ("y\n\n2020-01-01,1\n\n2020-01-02,2\n", ",", [2, 2]),
        ('y\n"2020,01",1\n"a;b",2\n', ",", [2, 2]),
        ("date;y\n2020-01-01;1,5;\n2020-01-02;2,5\n", ";", [3, 2]),
        ("date\ty\n2020-01-01\t1\n", "\t", [2]),
        ("date,y\n", ",", []),
    ],
    ids=["comma", "blank lines", "quoted separators", "semicolon", "tabulator",
         "header only"],
)
def test_read_row_lengths_output(tmp_path, text, sep, expected):
    """
    Test that the fields of every row after the header are counted as pandas
    splits them: blank lines left out, separators within quotes not counted.
    """
    path = tmp_path / "data.csv"
    path.write_text(text)

    assert read_row_lengths(path, sep) == expected


def test_read_row_lengths_output_when_file_is_gzip(tmp_path):
    """
    Test that a gzip file is decompressed before counting.
    """
    path = tmp_path / "data.csv.gz"
    with gzip.open(path, "wt") as handle:
        handle.write("y\n2020-01-01,1\n2020-01-02,2,3\n")

    assert read_row_lengths(path, ",") == [2, 3]


@pytest.mark.parametrize(
    "name, content",
    [
        ("missing.csv", None),
        ("latin.csv", "y\ncaf\xe9,1\n".encode("latin-1")),
        ("broken.csv.gz", b"not gzip"),
    ],
    ids=["missing", "not utf-8", "damaged gzip"],
)
def test_read_row_lengths_output_None_when_file_cannot_be_read(
    tmp_path, name, content
):
    """
    Test that a file that cannot be opened, decoded or decompressed gives
    None, left for pandas to report.
    """
    path = tmp_path / name
    if content is not None:
        path.write_bytes(content)

    assert read_row_lengths(path, ",") is None
