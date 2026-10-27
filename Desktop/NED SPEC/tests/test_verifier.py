"""Verifier: after the model answers, every number it said must exist in the fact sheet.

This is the module that turns 'the LLM said something plausible' into 'the LLM said
something we can point at'.
"""

from __future__ import annotations

import pytest

from src.fact import Fact
from src.verifier import allowed_numbers, numbers_in_text, verify_answer


def F(field="outer_diameter", value=20.0, unit="mm", note=""):
    return Fact(field=field, value=value, unit=unit, source_type="Excel",
                source_file="r.xlsx", location="'S'!A1", note=note)


SHEET = [F(), Fact("length", 45.0, "mm", "PDF", "d.pdf", "page 1"),
         Fact("material", "C45", None, "Excel", "r.xlsx", "'S'!B2"),
         Fact("quantity", 500, None, "Excel", "r.xlsx", "'S'!C2")]


def test_numbers_in_a_cited_answer_are_accepted():
    text = ("The outer diameter is 20 mm [Excel] and the length is 45 mm [PDF]. "
            "500 pieces are on order [Excel].")
    v = verify_answer(text, SHEET)
    assert v.ok, v.message
    assert not v.unverified


def test_an_invented_number_is_flagged_not_swallowed():
    text = "The outer diameter is 25 mm [Excel], machined in 3.7 minutes [Excel]."
    v = verify_answer(text, SHEET)
    assert not v.ok
    assert 25.0 in v.unverified
    assert "25" in v.message


def test_a_radius_derived_from_a_diameter_is_allowed():
    v = verify_answer("radius 10 mm [Excel]", SHEET)
    assert 10.0 in allowed_numbers(SHEET)              # documented derivation
    assert v.ok


def test_a_unit_conversion_of_a_listed_value_is_allowed():
    assert verify_answer("about 0.7874 in [PDF]", SHEET).ok


def test_citation_is_required():
    v = verify_answer("The material is C45.", SHEET)
    assert not v.ok
    assert v.missing_citations


def test_an_honest_refusal_needs_no_citation():
    v = verify_answer("I can't find that in the files.", SHEET)
    assert v.ok, v.message


def test_enum_counts_and_citation_coordinates_are_not_treated_as_values():
    # '2 sources' and a cell address like D5 are not engineering numbers
    text = "Two sources agree: 20 mm [extracted from Excel: r.xlsx, 'S'!A2]."
    assert verify_answer(text, SHEET).ok


def test_a_part_number_taken_from_the_file_name_is_provenance_not_a_claim():
    # a scanned drawing can carry no part_number fact; quoting '8801.pdf' must not be
    # mistaken for an invented number, while a real invention still fails
    sheet = [Fact("outer_diameter", 32.0, None, "PDF", "8801.pdf", "vision transcription")]
    assert verify_answer("the bore is 32 [PDF: 8801.pdf, vision transcription]",
                         sheet).ok
    bad = verify_answer("the bore is 47.5 [PDF: 8801.pdf, vision transcription]", sheet)
    assert not bad.ok and 47.5 in bad.unverified


def test_empty_answer_is_rejected():
    assert not verify_answer("", SHEET).ok


@pytest.mark.parametrize("text,expected", [
    ("45 mm long, +/-0.1 tolerance", [45.0, 0.1]),
    ("1,234.5 mm", [1234.5]),
    ("scale 1:5 on 2026-10-26", []),                 # ratios and dates carry no values
])
def test_number_extraction_from_prose(text, expected):
    got = numbers_in_text(text)
    for value in expected:
        assert value in got, text
