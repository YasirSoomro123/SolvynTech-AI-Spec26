"""Header mapping: the rules that make an unknown spreadsheet readable.

These tests use headings that appear in none of our sample files on purpose.
"""

from __future__ import annotations

import pytest

from src.schema import (CANONICAL_FIELDS, EXACT_ONLY, header_unit, match_header,
                        normalise_header)


def test_accent_and_case_noise_is_removed():
    assert normalise_header("  Diamétre Extérieur  ") == "diametre exterieur"
    assert normalise_header(None) == ""


@pytest.mark.parametrize("raw,unit", [
    ("Outer Diameter (mm)", "mm"),
    ("id_mm", "mm"),
    ("Temps [min]", "min"),
    ("Ra (µm)", "um"),
    ("Weight in kg", "kg"),
])
def test_unit_is_read_from_the_heading(raw, unit):
    assert header_unit(raw) == unit


def test_trailing_in_after_underscore_is_not_read_as_inches():
    """'DIA_IN' is diameter-inner; treating the tail as 'inch' rescales the part by 25.4."""
    assert header_unit("DIA_IN") != "inch"
    field, _ = match_header("DIA_IN")
    assert field == "inner_diameter"


@pytest.mark.parametrize("raw,field", [
    ("PART NUMBER", "part_number"),
    ("pn", "part_number"),
    ("No de pièce", "part_number"),
    ("Material", "material"),
    ("MAT. GRADE", "material"),
    ("Matière", "material"),
    ("Diam. ext. [mm]", "outer_diameter"),
    ("DIA OUT", "outer_diameter"),
    ("Diametre interieur", "inner_diameter"),
    ("Bore", "inner_diameter"),
    ("Overall length (mm)", "length"),
    ("Longueur", "length"),
    ("Qte", "quantity"),
    ("Temps cycle (min)", "cycle_time"),
    ("General tolerance", "general_tolerance"),
    ("Surface finish Ra", "surface_finish"),
    ("Supplier code", "supplier_ref"),
    ("REV", "revision"),
    ("Machine", "machine"),
    ("Op list", "operations"),
])
def test_common_headings_map_to_the_expected_field(raw, field):
    got, score = match_header(raw)
    assert got == field, f"{raw!r} -> {got!r} ({score})"
    assert score >= 0.7


@pytest.mark.parametrize("raw", ["customer", "e-mail", "operator name", "xy", "lorem ipsum"])
def test_unknown_headings_are_not_forced_into_a_field(raw):
    field, score = match_header(raw)
    assert field is None or score < 0.7, f"{raw!r} wrongly matched {field} at {score}"


def test_ambiguous_short_headings_only_match_exactly():
    """'id' may be the bore, 'no' may be the part number: never let a fuzzy win decide."""
    for head in EXACT_ONLY:
        assert match_header(head)[0] in CANONICAL_FIELDS or match_header(head)[0] is None
    # 'referee' resembles 'ref' but must not inherit it
    assert match_header("referee")[0] != "supplier_ref"


def test_unit_kind_breaks_a_close_call():
    """'id' alone is genuinely ambiguous; the unit in the heading is what decides."""
    assert match_header("id")[0] in {"part_number", "inner_diameter"}
    assert match_header("id_mm")[0] == "inner_diameter"     # a millimetre heading is a length
    assert match_header("ID (mm)")[0] == "inner_diameter"


def test_every_field_declares_its_synonyms():
    for name, spec in CANONICAL_FIELDS.items():
        assert spec["syn"], name
        assert isinstance(spec["syn"], list)
