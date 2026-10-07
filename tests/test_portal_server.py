import pytest

from zvideo.portal.server import RangeError, parse_range


def test_no_range_header_means_whole_file():
    assert parse_range(None, 1000) is None
    assert parse_range("", 1000) is None


def test_closed_range():
    assert parse_range("bytes=0-99", 1000) == (0, 99)


def test_open_ended_range_runs_to_last_byte():
    assert parse_range("bytes=500-", 1000) == (500, 999)


def test_suffix_range_takes_last_bytes():
    assert parse_range("bytes=-200", 1000) == (800, 999)


def test_end_beyond_size_is_clipped():
    assert parse_range("bytes=900-5000", 1000) == (900, 999)


def test_start_beyond_size_is_unsatisfiable():
    with pytest.raises(RangeError):
        parse_range("bytes=1000-", 1000)


def test_multiple_ranges_use_the_first():
    assert parse_range("bytes=0-9, 20-29", 1000) == (0, 9)


def test_malformed_range_is_ignored():
    assert parse_range("items=0-9", 1000) is None
    assert parse_range("bytes=abc", 1000) is None
