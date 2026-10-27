"""The part report and the picture helpers.

Nothing here reads ``data/`` - the report is built from the generated corpus and the PDF
page from a file invented inside the test, because the judges bring their own files.
"""

from __future__ import annotations

import re
import shutil

import pytest

from src.pipeline import build_report
from src.ui_report import quality, report_blocks, report_markdown, report_pdf
from src.ui_views import envelope_svg, page_count, page_png


def _report(tmp_path_factory, name: str = "synth"):
    import importlib.util
    from pathlib import Path
    repo = Path(__file__).resolve().parents[1]
    out = tmp_path_factory.mktemp(name)
    spec = importlib.util.spec_from_file_location("make_test_data",
                                                  repo / "scripts" / "make_test_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.build(out)
    return out


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    return _report(tmp_path_factory)


class TestQuality:
    def test_a_part_with_all_three_sources_scores_highly(self, corpus):
        rep = build_report("3002", corpus)
        score, why = quality(rep)
        assert score >= 60, why
        # whatever is taken off must be a real, named gap - never a vague deduction
        for line in why:
            assert re.search(r"-\d+", line), line

    def test_a_missing_source_costs_its_own_points(self, corpus, tmp_path):
        record = next(p for p in corpus.rglob("*")
                      if p.suffix.lower() in (".xlsx", ".xlsm", ".csv") and "3002" in p.name)
        only = tmp_path / "excel-only"
        only.mkdir()
        shutil.copy(record, only / record.name)
        full, _ = quality(build_report("3002", corpus))
        part, why = quality(build_report("3002", only))
        assert full - part == 35, why                     # PDF (20) + IGES (15)
        assert any("no PDF facts" in w for w in why) and any("no IGES facts" in w for w in why)

    def test_an_unreadable_part_scores_zero_without_inventing_a_reason(self, tmp_path):
        rep = build_report("4242", tmp_path)
        score, why = quality(rep)
        assert score == 0
        assert any("nothing was extracted" in w for w in why)


class TestReportBlocks:
    def test_one_line_per_cross_check(self, corpus):
        rep = build_report("3002", corpus)
        text = report_markdown(rep, "test-model")
        for row in rep.rows:
            assert row.label in text
        assert "test-model" in text

    def test_the_report_repeats_no_number_the_files_do_not_state(self, corpus):
        """The report is code-generated, so every value on it must exist in the fact sheet."""
        rep = build_report("3002", corpus)
        allowed = {f"{f.value:g}" for f in rep.facts if isinstance(f.value, (int, float))}
        allowed |= {str(f.value) for f in rep.facts}
        lines = [t for kind, t in report_blocks(rep) if kind == "kv"]
        assert lines
        for line in lines:
            for value in re.findall(r"(?:Excel|PDF|IGES|record/drawing) ([0-9][0-9.,+ ]*)", line):
                for token in re.split(r"[,+]|\s", value):
                    if token:
                        assert token in allowed, (line, token)

    def test_a_part_with_no_disagreement_says_so_instead_of_staying_silent(self, corpus):
        rep = build_report("3002", corpus)
        text = report_markdown(rep)
        assert "Where the files disagree" in text
        bad = [r for r in rep.rows if r.status == "mismatch"]
        assert ("No disagreement was found" in text) == (not bad)

    def test_the_levels_section_matches_what_was_read(self, corpus, tmp_path):
        rep = build_report("3002", corpus)
        text = report_markdown(rep)
        assert "Level 2 - yes" in text and "Level 3 - yes" in text
        record = next(p for p in corpus.rglob("*")
                      if p.suffix.lower() in (".xlsx", ".xlsm", ".csv") and "3002" in p.name)
        only = tmp_path / "only"
        only.mkdir()
        shutil.copy(record, only / record.name)
        thin = report_markdown(build_report("3002", only))
        assert "Level 1 - yes" in thin and "Level 2 - no" in thin


class TestReportPdf:
    def test_the_pdf_is_a_real_multi_page_document(self, corpus):
        rep = build_report("3002", corpus)
        blob = report_pdf(rep, "test-model")
        assert blob[:4] == b"%PDF"
        import pymupdf
        doc = pymupdf.open(stream=blob, filetype="pdf")
        assert doc.page_count >= 2                          # the report is longer than a page
        first = doc[0].get_text()
        assert f"Part {rep.part}" in first and "Files used" in first
        assert doc[-1].get_text().strip()                   # the last page has content

    def test_a_page_break_never_loses_a_block(self, corpus):
        import pymupdf
        doc = pymupdf.open(stream=report_pdf(build_report("3002", corpus)), filetype="pdf")
        joined = " ".join(doc[i].get_text() for i in range(doc.page_count))
        assert joined.count("Data quality for this part") == 1
        assert "How to read this page" in joined


class TestEnvelopeSketch:
    def test_the_three_measured_sizes_appear_on_the_sketch(self):
        svg = envelope_svg([25.0, 16.0, 16.0], "mm", "sorted envelope, axis order unknown")
        assert svg.startswith("<svg")
        for size in ("25 mm", "16 mm"):
            assert size in svg
        assert "Approximate envelope" in svg

    def test_no_numbers_no_picture(self):
        assert envelope_svg([], "mm") == ""
        assert envelope_svg([0.0, 0.0, 0.0], "mm") == ""

    def test_html_in_a_note_cannot_become_markup(self):
        svg = envelope_svg([10, 9, 8], "mm", "<script>alert(1)</script>")
        assert "<script>" not in svg and "&lt;script&gt;" in svg


class TestDrawingPage:
    def test_a_pdf_page_renders_and_a_broken_file_does_not(self, make_pdf, tmp_path):
        path = make_pdf(["PART 3002", "MATERIAL ALUMINIUM", "SCALE 1:2"], name="sheet.pdf")
        assert page_count(path) == 1
        png = page_png(path, 0, 1.4)
        assert png and png[:8] == b"\x89PNG\r\n\x1a\n"
        junk = tmp_path / "not-a-pdf.pdf"
        junk.write_bytes(b"this is not a pdf at all")
        assert page_count(junk) == 0
        assert page_png(junk) is None

    def test_an_out_of_range_page_clamps_instead_of_crashing(self, make_pdf):
        path = make_pdf(["one page only"], name="one.pdf")
        assert page_png(path, 9, 1.0) is not None
