"""Number parsing and unit conversion - the places where a wrong comma means a 10x error."""

from __future__ import annotations

import pytest

from src.units import (LENGTH_TO_MM, extract_numbers, fmt, normalise_units_token,
                       parse_number, to_mm, unit_factor)


@pytest.mark.parametrize("token,expected", [
    ("8", 8.0),
    ("4,3", 4.3),                 # European decimal comma
    ("1,234.5", 1234.5),          # thousands grouping
    ("1.234,5", 1234.5),          # European grouping
    ("-0.05", -0.05),
    ("+0.1", 0.1),
    ("12", 12.0),
    ("3 1/2", 3.5),               # imperial mixed fraction, e.g. '3 1/2 FILL'
    ("1/2", 0.5),
    ("-3 1/2", -3.5),
    ("+/-0.1", 0.1),              # a spread, not a negative
    ("50+/-0.1", 50.0),           # the nominal value, not a glued '500.1'
])
def test_ambiguous_decimal_marks(token, expected):
    assert parse_number(token) == pytest.approx(expected)


@pytest.mark.parametrize("token", ["", "mm", "A1", "ISO", None, "M5"])
def test_non_numbers_are_refused(token):
    assert parse_number(token) is None


def test_extract_numbers_agrees_with_parse_number():
    """One pattern for both, or a callout and a cell would read the same text differently."""
    assert extract_numbers("50 +/- 0.1") == [50.0, 0.1]
    assert extract_numbers("3 1/2") == [3.5]
    assert extract_numbers("1,234.5") == [1234.5]


def test_units_token_normalisation():
    assert normalise_units_token("MM") == "mm"
    assert normalise_units_token("(mm)") == "mm"
    assert normalise_units_token("µm") == "um"
    assert normalise_units_token("banana") is None
    # aliases are recognised by their factor, whatever spelling the file used
    assert unit_factor("inches") == pytest.approx(25.4)
    assert unit_factor("millimetres") == pytest.approx(1.0)


def test_conversion_to_mm():
    assert to_mm(1.0, "inch") == pytest.approx(25.4)
    assert to_mm(10.0, "mm") == pytest.approx(10.0)
    assert to_mm(1.0, None) is None                 # an unknown unit is never guessed
    for unit, factor in LENGTH_TO_MM.items():
        assert factor is None or factor > 0, unit


def test_extract_numbers_from_a_callout_line():
    # order is the reading order of the line, so only membership is asserted
    assert set(extract_numbers("2 X DIA 8 THRU, R 1.5")) >= {8.0, 1.5}


def test_fmt_is_compact():
    assert fmt(8.0) == "8"
    assert fmt(4.35) == "4.35"
