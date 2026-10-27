"""Excel reader: no column index is hard-coded anywhere, so this file is the proof.

Everything here invents a workbook shape that is not present in data/ - header deep in
the sheet, odd synonyms, units in the heading, blank rows, prose sheets, CSV.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.excel_reader import read_spreadsheet, rows_for_part
from src.fact import Fact


def by_field(facts: list[Fact]) -> dict[str, list[Fact]]:
    out: dict[str, list[Fact]] = {}
    for f in facts:
        out.setdefault(f.field, []).append(f)
    return out


# ---------------------------------------------------------------- header row
def test_header_row_is_found_when_it_is_not_the_first_row(make_xlsx):
    path = make_xlsx([
        ["ACME Workshop - machining record", None, None, None],
        ["printed 2026-10-01", None, None, None],
        [None, None, None, None],
        ["Part", "Material", "OD (mm)", "Cycle"],
        [7120, "Aluminium 6082", 25, 1.9],
    ])
    res = read_spreadsheet(path)
    got = by_field(res.facts)
    assert res.ok
    assert got["part_number"][0].value == 7120 or str(got["part_number"][0].value) == "7120"
    assert got["material"][0].value == "Aluminium 6082"
    assert got["outer_diameter"][0].value == pytest.approx(25.0)
    assert got["cycle_time"][0].value == pytest.approx(1.9)
    assert got["outer_diameter"][0].unit == "mm"


def test_location_points_at_the_cell_so_a_human_can_check_it(make_xlsx):
    path = make_xlsx([["part number", "material"], ["A-9", "POM"]], sheet="Ops",
                     filename="ops.xlsx")
    f = by_field(read_spreadsheet(path).facts)["material"][0]
    assert f.location == "'Ops'!B2"


def test_blank_cells_produce_no_fact(make_xlsx):
    path = make_xlsx([["part number", "material", "quantity"], ["1", "", None]])
    got = by_field(read_spreadsheet(path).facts)
    assert "material" not in got
    assert "quantity" not in got


def test_blank_rows_between_data_are_ignored(make_xlsx):
    path = make_xlsx([
        ["part no", "material"],
        ["11", "steel"],
        [None, None],
        ["12", "brass"],
    ])
    res = read_spreadsheet(path)
    parts = [str(f.value) for f in by_field(res.facts)["part_number"]]
    assert parts == ["11", "12"]


# ---------------------------------------------------------------- mapping
def test_units_written_in_the_heading_are_applied_and_recorded(make_xlsx):
    path = make_xlsx([
        ["Part", "Length [inch]", "Ra (µm)", "Time (s)"],
        [500, 1.0, 0.8, 90],
    ])
    got = by_field(read_spreadsheet(path).facts)
    assert got["length"][0].value == pytest.approx(25.4)      # converted in code, not by an LLM
    assert got["length"][0].unit == "mm"
    assert got["surface_finish"][0].unit == "um"
    assert got["cycle_time"][0].unit == "min"                 # seconds -> minutes
    assert "converted" in (got["cycle_time"][0].note or "")


def test_unmapped_columns_survive_as_raw_facts(make_xlsx):
    path = make_xlsx([["part number", "operator name", "shift"], ["7", "Zoé", "night"]])
    got = by_field(read_spreadsheet(path).facts)
    assert got["raw:operator name"][0].value == "Zoé"
    assert got["raw:shift"][0].value == "night"
    assert got["part_number"][0].value in (7, "7")


def test_a_delimited_operation_list_becomes_a_real_list(make_xlsx):
    path = make_xlsx([["part number", "operations"], ["3", "Turn; Drill; Chamfer"]])
    ops = by_field(read_spreadsheet(path).facts)["operations"][0].value
    assert isinstance(ops, list) and len(ops) == 3


def test_text_value_in_a_numeric_column_is_kept_with_a_warning(make_xlsx):
    path = make_xlsx([["part number", "outer diameter mm"], ["3", "as drawing"]])
    f = by_field(read_spreadsheet(path).facts)["outer_diameter"][0]
    assert isinstance(f.value, str)
    assert "text" in (f.note or "").lower()


def test_header_mapper_may_only_rename_known_fields(make_xlsx):
    path = make_xlsx([["part number", "weird column"], ["3", "x"]])

    def mapper(headers, samples):
        return {"weird column": "material", "part number": "invented_field"}

    got = by_field(read_spreadsheet(path, header_mapper=mapper).facts)
    assert "material" in got
    assert "invented_field" not in got


# ---------------------------------------------------------------- formats
def test_csv_is_read_like_a_sheet(tmp_path):
    path = tmp_path / "parts.csv"
    path.write_text("part number;material;qty\n42;POM;10\n", encoding="utf-8", newline="")
    got = by_field(read_spreadsheet(path).facts)
    assert got["material"][0].value == "POM"


def test_multiple_sheets_are_all_examined(tmp_path):
    from openpyxl import Workbook
    wb = Workbook()
    for old in list(wb.worksheets):
        wb.remove(old)
    data = wb.create_sheet("Data")
    data.append(["part number", "material"])
    data.append([1, "steel"])
    notes = wb.create_sheet("Notes")
    notes.append(["these are prose notes about the factory, not a table at all"])
    p = tmp_path / "multi.xlsx"
    wb.save(p)
    res = read_spreadsheet(p)
    assert any(f.field == "material" for f in res.facts)
    assert any("Notes" in w for w in res.warnings)         # the prose sheet is reported, not guessed


# ---------------------------------------------------------------- per-part
def test_rows_for_part_selects_only_its_own_row(make_xlsx):
    path = make_xlsx([
        ["part number", "material", "outer diameter (mm)"],
        [100, "steel", 12],
        [200, "brass", 20],
    ])
    res = read_spreadsheet(path)
    assert len(res.facts) == 6                               # both rows are read
    mine = rows_for_part(res, "200")
    assert mine and all("part=200" in (f.note or "") for f in mine)
    assert [f.value for f in mine if f.field == "material"] == ["brass"]


def test_rows_for_part_returns_nothing_for_an_unknown_part(make_xlsx):
    path = make_xlsx([["part number", "material"], [100, "steel"]])
    assert rows_for_part(read_spreadsheet(path), "999") == []


# ---------------------------------------------------------------- real files
def test_the_shipped_record_is_read_without_hardcoded_columns(data_dir):
    path = data_dir / "manufacturing_record.xlsx"
    if not path.is_file():
        pytest.skip("real record not shipped")
    res = read_spreadsheet(path)
    assert res.ok and res.facts
    parts = {str(f.value) for f in res.facts if f.field == "part_number"}
    assert "2280" in parts or "2280.0" in parts
    # every fact must be traceable
    for f in res.facts:
        assert f.location and f.source_type == "Excel"


def test_corrupt_file_is_reported_not_raised(tmp_path):
    path = tmp_path / "broken.xlsx"
    path.write_bytes(b"this is not a spreadsheet")
    res = read_spreadsheet(path)
    assert not res.ok
    assert res.warnings


def test_missing_file_is_reported_not_raised(tmp_path):
    res = read_spreadsheet(tmp_path / "nope.xlsx")
    assert not res.ok and res.warnings
