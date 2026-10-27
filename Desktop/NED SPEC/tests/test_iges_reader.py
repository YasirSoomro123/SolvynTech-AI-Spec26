"""IGES reader: pure-python 80-column parser.

The models in data/ are real CAD exports and only part of their entities validate, so
these tests check the *promise* the module makes: take units from the Global section,
count what is countable, convert to mm in code, and stay silent about geometry it
cannot trust - never crash.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.iges_reader import read_iges


def fields(res) -> set[str]:
    return {f.field for f in res.facts}


def values(res, field: str) -> list[object]:
    return [f.value for f in res.facts if f.field == field]


def record(data: str, letter: str, number: int) -> str:
    """One physical IGES line: 72 columns of data, section letter, element number."""
    return (data.ljust(72)[:72] + letter + str(number).rjust(7)).ljust(80)[:80]


def lit(text: str) -> str:
    """A Global-section string literal: '<n>H<text>'. A wrong n shifts every later field."""
    return f"{len(text)}H{text}"


def model(unit: str) -> list[str]:
    """A 3-entity part (outer cylinder, end circle, plane) declared in `unit`.

    Geometry is 20 mm across and 12 mm long either way, so the two files must agree
    once the reader has converted both to millimetres.
    """
    k = 1.0 if unit == "MM" else 1.0 / 25.4
    ents = [
        (502, [0, 0, 0, 0, 0, 1, 10 * k, 0, 0, 0, 0, 0, 12 * k]),
        (100, [0, 0, 0, 0, 0, 1, 10 * k]),
        (126, [0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1,
               10 * k, 0, 0, -10 * k, 0, 0, 0, 10 * k, 0, 0, -10 * k, 0]),
    ]
    dirs: list[str] = []
    params: list[str] = []
    for idx, (etype, values_) in enumerate(ents, start=1):
        data = f"{etype}," + ",".join(f"{v:.10g}" for v in values_) + ";"
        first = len(params) + 1
        chunks = [data[i:i + 72] for i in range(0, len(data), 72)] or [data]
        for c_i, chunk in enumerate(chunks):
            params.append(record(chunk, "P", first + c_i))
        n = len(chunks)
        f1 = [str(etype), str(first), "0", "0", "0", "0", "0", "0", "00010000"]
        f2 = [str(etype), "0", "0", str(n), "0", "0", "0", "", "0"]
        dirs.append(record("".join(x.rjust(8) for x in f1), "D", idx * 2 - 1))
        dirs.append(record("".join(x.rjust(8) for x in f2), "D", idx * 2))
    glob = ",".join([lit(","), lit(";"), lit(" "), lit("TEST"), lit("CADTEST"),
                     lit("PARSERTEST"), "32", "38", "6", "308", "15", lit(" "), "1.000", "2",
                     f"{len(unit)}H{unit}", "1",
                     "2.54e+01" if unit == "INCH" else "1.000",
                     lit("20261026.120000"), "1.0e-07", "0.00",
                     lit("Author"), lit("Company"), "11", "0", lit("20261026.120000")]) + ";"
    gchunks = [glob[i:i + 72] for i in range(0, len(glob), 72)]
    out = [record("Test model written by the test suite", "S", 1)]
    out += [record(chunk, "G", i + 1) for i, chunk in enumerate(gchunks)]
    out += dirs + params
    out.append(record(f"S1,G{len(gchunks)},D{len(dirs)},P{len(params)},T1", "T", 1))
    return out


def write(path: Path, lines: list[str]) -> Path:
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("latin-1", "replace"))
    return path


@pytest.fixture
def iges_text(tmp_path):
    def _make(lines: list[str], name: str = "model.igs") -> Path:
        return write(tmp_path / name, lines)
    return _make


def test_a_minimal_model_is_parsed_at_all(iges_text):
    res = read_iges(iges_text(model("MM")))
    assert res.ok, res.warnings
    assert res.source_type == "IGES"
    assert values(res, "cad_units") == ["MM"]
    assert values(res, "iges_entity_total") == [3]


def test_units_are_taken_from_the_global_section_and_applied(iges_text):
    mm = read_iges(iges_text(model("MM"), "mm.igs"))
    inch = read_iges(iges_text(model("INCH"), "in.igs"))
    assert values(mm, "cad_units") == ["MM"] and values(inch, "cad_units") == ["INCH"]
    rad_mm = values(mm, "cylinder_radius")
    rad_in = values(inch, "cylinder_radius")
    assert rad_mm and rad_in
    assert rad_in[0] == pytest.approx(rad_mm[0], rel=1e-6)   # both converted to mm


def test_dimensions_are_reported_in_mm(iges_text):
    res = read_iges(iges_text(model("INCH"), "cyl.igs"))
    geometry = [f for f in res.facts
                if f.field in {"cylinder_radius", "cylinder_height", "outer_diameter",
                               "bounding_box_size"}]
    assert geometry, res.detail
    for f in geometry:
        assert f.unit == "mm", f
        nums = f.value if isinstance(f.value, (list, tuple)) else [f.value]
        assert all(isinstance(v, (int, float)) and v > 0 for v in nums), f


def test_bounding_box_spans_the_validated_geometry(iges_text):
    res = read_iges(iges_text(model("MM"), "mm2.igs"))
    sizes = [f for f in res.facts if f.field == "bounding_box_size"]
    assert sizes, res.detail
    assert max(sizes[0].value) == pytest.approx(20.0, abs=0.01)   # 2 x r=10 cylinder
    assert sorted(sizes[0].value)[0] == pytest.approx(12.0, abs=0.01)


def test_garbage_is_refused_politely(tmp_path):
    path = tmp_path / "junk.igs"
    path.write_bytes(b"\x00\x01not an iges file at all\xff")
    res = read_iges(path)
    assert res.warnings                         # it must say what went wrong
    assert isinstance(res.facts, list)


def test_empty_file_is_not_a_crash(tmp_path):
    path = tmp_path / "empty.igs"
    path.write_text("", encoding="utf-8")
    res = read_iges(path)
    assert not res.ok and res.warnings


def test_missing_file_is_reported(tmp_path):
    res = read_iges(tmp_path / "nope.igs")
    assert not res.ok and res.warnings


# ---------------------------------------------------------------- real exports
REFERENCE_MODELS = ["2280/2280.igs", "2281/2281.igs"]
SYNTH_MODELS = ["3002/3002.igs", "3004  rev C.igs", "models/3001_model.igs",
                "p3005_final.iges", "models/pin-3003.iges"]


def assert_model_decoded(res, name: str) -> None:
    assert res.source_type == "IGES"
    assert values(res, "iges_entity_total"), res.detail      # counting needs no validation
    for f in res.facts:
        assert f.location, f
        assert f.source_file.endswith(Path(name).name)


@pytest.mark.parametrize("name", REFERENCE_MODELS)
def test_the_reference_models_never_crash(data_dir, name):
    assert_model_decoded(read_iges(data_dir / name), name)


@pytest.mark.parametrize("name", SYNTH_MODELS)
def test_the_generated_models_never_crash(synth_dir, name):
    assert_model_decoded(read_iges(synth_dir / name), name)


def test_never_claims_more_geometry_than_it_decoded(data_dir):
    """The honesty rule: decoded <= total, and a partial parse must warn about it."""
    res = read_iges(data_dir / "2280/2280.igs")
    total, decoded = values(res, "iges_entity_total"), values(res, "iges_entities_decoded")
    assert total and decoded
    assert decoded[0] <= total[0]
    if decoded[0] < total[0]:
        assert any("did not" in w or "cannot" in w or "not decoded" in w
                   for w in res.warnings), res.warnings


def test_envelope_is_only_stated_when_it_can_be_trusted(synth_dir):
    res = read_iges(synth_dir / "p3005_final.iges")
    sizes = [f for f in res.facts if f.field == "bounding_box_size"]
    assert sizes, res.detail
    assert sizes[0].unit == "mm"
    assert sizes[0].confidence in {"code-medium", "code-low", "inferred"}


def test_inch_model_is_converted_in_the_real_corpus(synth_dir):
    res = read_iges(synth_dir / "p3005_final.iges")
    assert values(res, "cad_units") == ["INCH"]
    assert all(f.unit != "in" for f in res.facts)            # nothing is left in inches


def test_cylinder_radii_are_sane_positive_lengths(synth_dir):
    res = read_iges(synth_dir / "3002/3002.igs")
    radii = [f for f in res.facts if f.field == "cylinder_radius"]
    assert radii, res.detail
    assert all(0 < f.value < 2000 for f in radii)
    assert all(f.unit == "mm" for f in radii)
