"""Cross-check: the table that compares record, drawing and model.

Rules under test: absolute OR relative tolerance, unit differences, sorted envelopes,
text compared spelling-wise, and above all - 'only one source says it' is never a
mismatch, because that is the normal case, not an error.
"""

from __future__ import annotations

import pytest

from src.crosscheck import (STATUS_MATCH, STATUS_MISMATCH, STATUS_ONLY, crosscheck)


def od(fact, value, source, unit=None):
    return fact("outer_diameter", value, source, unit=unit)


def test_two_sources_that_agree_within_half_a_millimetre(fact):
    rows = crosscheck([od(fact, 20.0, "Excel"), od(fact, 20.3, "PDF")])
    row = next(r for r in rows if r.label.startswith("Outer"))
    assert row.status == STATUS_MATCH


def test_a_plant_difference_is_reported_as_a_mismatch(fact):
    rows = crosscheck([od(fact, 20.0, "Excel"), od(fact, 22.0, "PDF")])
    row = next(r for r in rows if r.label.startswith("Outer"))
    assert row.status == STATUS_MISMATCH
    assert "20" in row.detail and "22" in row.detail        # both values are shown


def test_a_larger_part_may_agree_relatively_but_not_absolutely(fact):
    """1 mm apart is noise on a 5 mm part and real on a 900 mm one - the tolerance says so."""
    rows = crosscheck([od(fact, 5.0, "Excel"), od(fact, 6.0, "PDF")])
    assert next(r for r in rows if r.label.startswith("Outer")).status == STATUS_MISMATCH
    rows = crosscheck([od(fact, 900.0, "Excel"), od(fact, 909.0, "PDF")])
    assert next(r for r in rows if r.label.startswith("Outer")).status == STATUS_MATCH


def test_inches_and_millimetres_are_not_compared_as_equal_numbers(fact):
    """A source that says 20 in is not the same part as one that says 20 mm."""
    rows = crosscheck([od(fact, 20.0, "Excel", "mm"), od(fact, 20.0, "PDF", "inch")])
    row = next(r for r in rows if r.label.startswith("Outer"))
    assert row.status != STATUS_ONLY


def test_one_sided_data_is_only_one_source(fact):
    rows = crosscheck([od(fact, 20.0, "Excel")])
    row = next(r for r in rows if r.label.startswith("Outer"))
    assert row.status == STATUS_ONLY
    assert "Excel" in row.detail


def test_text_values_match_heritage_and_case(fact):
    a = fact("material", "Stainless Steel A1 (INOX)", "Excel")
    b = fact("material", "STAINLESS STEEL A1 (INOX)", "PDF")
    row = next(r for r in crosscheck([a, b]) if r.label.startswith("Material"))
    assert row.status == STATUS_MATCH


def test_different_materials_are_a_mismatch(fact):
    a = fact("material", "Stainless Steel A1", "Excel")
    b = fact("material", "Brass CuZn39Pb3", "PDF")
    row = next(r for r in crosscheck([a, b]) if r.label.startswith("Material"))
    assert row.status == STATUS_MISMATCH


def test_conflicting_units_declared_by_the_sources_are_flagged(fact):
    rows = crosscheck([fact("cad_units", "INCH", "IGES"), fact("units", "mm", "PDF")])
    row = next(r for r in rows if "Unit" in r.label)
    assert row.status == STATUS_MISMATCH


def test_row_carries_the_worst_confidence_of_the_group(fact):
    a = od(fact, 20.0, "Excel")
    b = fact("outer_diameter", 20.0, "PDF", confidence="llm-vision")
    row = next(r for r in crosscheck([a, b]) if r.label.startswith("Outer"))
    assert row.worst_confidence == "llm-vision"


def test_envelope_is_compared_sorted_against_listed_sizes(fact):
    bbox = fact("bounding_box_size", [8.0, 20.0, 5.0], "IGES", unit="mm")
    listed = [od(fact, 20.0, "Excel"), fact("length", 8.0, "Excel")]
    rows = crosscheck([bbox] + listed)
    row = next(r for r in rows if "envelope" in r.label.lower())
    assert row.status in (STATUS_MATCH, STATUS_MISMATCH)
    assert "IGES" in row.values


def test_envelope_disagreement_is_visible(fact):
    bbox = fact("bounding_box_size", [8.0, 20.0, 5.0], "IGES", unit="mm")
    rows = crosscheck([bbox, od(fact, 42.0, "PDF")])
    row = next(r for r in rows if "envelope" in r.label.lower())
    assert row.status == STATUS_MISMATCH


def test_no_facts_produce_no_rows(fact):
    assert crosscheck([]) == []


def test_empty_values_do_not_create_a_phantom_mismatch(fact):
    rows = crosscheck([fact("material", "", "Excel"), fact("material", "POM", "PDF")])
    row = next(r for r in rows if r.label.startswith("Material"))
    assert row.status != STATUS_MISMATCH


@pytest.mark.parametrize("abs_tol,rel_tol,expected", [
    (0.5, 0.01, STATUS_MISMATCH),
    (5.0, 0.01, STATUS_MATCH),
])
def test_tolerances_are_configurable(fact, abs_tol, rel_tol, expected):
    rows = crosscheck([od(fact, 20.0, "Excel"), od(fact, 22.0, "PDF")],
                      abs_tol_mm=abs_tol, rel_tol=rel_tol)
    assert next(r for r in rows if r.label.startswith("Outer")).status == expected
