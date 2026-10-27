"""Tests for the chat panel's content helpers (src/ui_chat.py).

These are the parts of the new chatbot UI that decide what the judge *reads*: which files
an answer claims to come from, which evidence rows appear under it, and what a suggested
next question is allowed to ask. Nothing here touches data/, Streamlit, or a network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.fact import Fact
from src.pipeline import Report, ask, build_report
from src.ui_chat import (chat_markdown, cited_kinds, evidence_for, evidence_rows, followups,
                         greeting, is_not_found, mode_label)


def fact(field_: str, value: object, kind: str, file: str, location: str,
         confidence: str = "code-high", note: str = "", unit: str | None = None) -> Fact:
    return Fact(field=field_, value=value, unit=unit, source_type=kind, source_file=file,
                location=location, confidence=confidence, note=note)


def report(facts: list[Fact], part: str = "123") -> Report:
    return Report(part=part, root=Path("."), facts=facts)


MAT_XLS = fact("material", "Steel C45", "Excel", "records\\m_123.xlsx", "'Sheet1'!C2",
               note="column 'matl'")
MAT_PDF = fact("material", "Steel C45", "PDF", "drawings\\d_123.pdf", "page 1, title block",
               note="title block label 'MATERIAL'")
REV_PDF = fact("revision", "A", "PDF", "drawings\\d_123.pdf", "page 1, title block",
               note="title block label 'REV'")
OD_IGS = fact("outer_diameter", 32.0, "IGES", "models\\m.igs", "entity 126 (bounding box)",
              confidence="code-low", unit="mm", note="approximate")


def _quoted(f: Fact) -> str:
    """The citation string this app's own code answers print for a fact."""
    return (f"[extracted from {f.source_type}: {Path(f.source_file).name}, {f.location}; "
            f"confidence {f.confidence}" + (f"; {f.note}" if f.note else "") + "]")


class TestCitedKinds:
    def test_all_three_sources_survive_one_answer(self):
        """Regression: 'PDF'.title() is 'Pdf', which matched no source_type at all."""
        text = (f"- material: Steel C45 {_quoted(MAT_XLS)}\n"
                f"- material: Steel C45 {_quoted(MAT_PDF)}\n"
                f"- outer diameter: 32 mm {_quoted(OD_IGS)}")
        assert cited_kinds(text) == ["Excel", "PDF", "IGES"]

    def test_order_is_excel_pdf_iges_not_text_order(self):
        assert cited_kinds("[IGES: a.igs, x] then [Excel: a.xlsx, y]") == ["Excel", "IGES"]

    def test_answer_without_citation_claims_no_source(self):
        assert cited_kinds("I can't find that in the files.") == []
        assert cited_kinds("") == []


class TestEvidence:
    def test_full_citation_selects_exactly_that_fact(self):
        rep = report([MAT_PDF, REV_PDF, MAT_XLS])
        text = f"Material is Steel C45 {_quoted(MAT_XLS)}."
        assert [f.source_type for f in evidence_for(rep, text)] == ["Excel"]

    def test_multi_source_answer_shows_every_cited_fact(self):
        rep = report([MAT_XLS, MAT_PDF, REV_PDF])
        text = (f"Material: Steel C45 {_quoted(MAT_XLS)} and also {_quoted(MAT_PDF)}.")
        got = evidence_for(rep, text)
        assert [(f.source_type, f.field) for f in got] == [("Excel", "material"),
                                                           ("PDF", "material")]

    def test_short_citation_also_needs_the_value_in_the_sentence(self):
        # two PDF facts share one location; only the one whose value is stated is evidence
        rep = report([MAT_PDF, REV_PDF])
        text = "Material is Steel C45 [PDF: d_123.pdf, page 1, title block]."
        assert [(f.field, f.value) for f in evidence_for(rep, text)] == [("material",
                                                                         "Steel C45")]

    def test_short_citation_with_an_unusual_value_is_not_forced(self):
        rep = report([MAT_PDF, REV_PDF])
        text = "The title block says it [PDF: d_123.pdf, page 1, title block]."
        assert evidence_for(rep, text) == []

    def test_a_copied_value_with_a_no_break_space_still_counts_as_quoted(self):
        """Models retype values with odd spaces; that must not lose the evidence row."""
        alloy = fact("material", "Aluminium 6060 T6", "PDF", "drawings\\d_123.pdf",
                     "page 1, title block")
        rep = report([alloy, REV_PDF])
        text = "Material is Aluminium\u202f6060\u00a0T6 [PDF: d_123.pdf, page 1, title block]."
        got = evidence_for(rep, text)
        assert [(f.field, f.value) for f in got] == [("material", "Aluminium 6060 T6")]

    def test_unknown_citation_yields_no_evidence(self):
        """A citation to a file we never read is shown as nothing, not as a near-miss."""
        rep = report([MAT_XLS])
        assert evidence_for(rep, "Weight 12 kg [IGES: phantom.igs, entity 9].") == []

    def test_a_one_letter_value_is_not_found_everywhere(self):
        # two facts share this location, so the value has to be quoted - and a bare 'A'
        # must not count as quoted just because 'aluminium' contains one
        rep = report([REV_PDF, MAT_PDF])
        assert [f.field for f in
                evidence_for(rep, "The revision letter is A [PDF: d_123.pdf, page 1, title "
                                  "block].")] == ["revision"]
        assert evidence_for(rep, "It is aluminium [PDF: d_123.pdf, page 1, title block].") == []

    def test_a_citation_that_can_only_mean_one_fact_is_accepted(self):
        rep = report([REV_PDF, OD_IGS])
        got = evidence_for(rep, "See [PDF: d_123.pdf, page 1, title block].")
        assert [f.field for f in got] == ["revision"]

    def test_evidence_rows_carry_file_place_and_confidence(self):
        rows = evidence_rows(evidence_for(report([OD_IGS]), _quoted(OD_IGS)))
        assert rows == [{"Fact": "outer diameter", "Value": "32 mm", "Source": "IGES",
                         "File": "m.igs", "Where": "entity 126 (bounding box)",
                         "Confidence": "code-low",
                         "Note": "approximate"}]


class TestNotFoundStyle:
    def test_the_codes_own_refusal_is_detected(self):
        assert is_not_found("I can't find that in the files. The record holds no cost value.")

    def test_a_real_answer_is_not_flagged(self):
        assert not is_not_found("Material is Steel C45 [Excel: a.xlsx, C2].")


class TestGreeting:
    def test_names_every_source_that_was_read(self):
        rep = report([MAT_XLS, MAT_PDF, OD_IGS], part="123")
        rep.files = _Files({"Excel": Path("a.xlsx"), "PDF": Path("b.pdf"), "IGES": Path("c.igs")})
        text = greeting(rep)
        assert "123" in text and "Excel" in text and "PDF" in text and "IGES" in text

    def test_says_which_source_is_missing(self):
        rep = report([MAT_XLS], part="7")
        rep.files = _Files({"Excel": Path("a.xlsx")})
        text = greeting(rep)
        assert "PDF" in text and "IGES" in text and "not found" in text

    def test_counts_come_from_the_report_not_from_imagination(self):
        rep = report([MAT_XLS, MAT_PDF], part="7")
        rep.files = _Files({"Excel": Path("a.xlsx")})
        assert f"{len(rep.facts)} facts" in greeting(rep)


class _Files:
    def __init__(self, paths: dict[str, Path]):
        self._paths = paths

    def paths(self) -> dict[str, Path]:
        return self._paths


class TestFollowups:
    def test_only_three_and_only_answerable_ones(self):
        rep = report([MAT_XLS])
        tips = followups(rep)
        assert len(tips) <= 3
        assert all("cost" not in t.lower() and "price" not in t.lower() for t in tips)

    def test_a_question_about_a_missing_field_is_never_suggested(self):
        rep = report([MAT_XLS])                       # no machine, no operations, no tolerance
        tips = " ".join(followups(rep, limit=9)).lower()
        assert "machine" not in tips and "tolerance" not in tips

    def test_dimensions_are_suggested_only_when_present(self):
        rep = report([OD_IGS])
        assert any("dimension" in t.lower() for t in followups(rep, limit=9))

    def test_what_was_just_asked_is_not_offered_back(self):
        rep = report([MAT_XLS, MAT_PDF, OD_IGS])
        tips = followups(rep, asked="What surface finish is required?", limit=9)
        assert "What surface finish is required?" not in tips


class TestLabels:
    def test_a_code_answer_is_never_labelled_an_llm_answer(self):
        assert mode_label("no-llm").startswith("Code answer")
        assert mode_label("code").startswith("Code answer")
        assert mode_label("limited").startswith("Code answer")
        assert mode_label("llm") == "LLM answer"

    def test_the_label_says_when_no_model_was_used_or_could_answer(self):
        assert "no LLM in use" in mode_label("no-llm")
        assert "model unavailable" in mode_label("limited")
        assert mode_label("local") != "LLM answer"

    def test_a_failed_answer_says_so(self):
        assert "failed" in mode_label("error").lower()


class TestTranscript:
    def test_transcript_keeps_citations_and_the_rejection(self):
        hist = [{"role": "user", "text": "material?"},
                {"role": "assistant", "text": f"Steel C45 {_quoted(MAT_XLS)}", "mode": "no-llm",
                 "model": "", "v_ok": False, "v_msg": "no citation", "rating": 1}]
        md = chat_markdown("123", "data/demo", hist)
        assert "# Chat - part 123" in md and "data/demo" in md
        assert "extracted from Excel" in md
        assert "Rejected by the verifier" in md
        assert "rated helpful" in md

    def test_an_empty_chat_still_exports(self):
        assert "part 123" in chat_markdown("123", "data/demo", [])


class TestAgainstTheGeneratedCorpus:
    """The real parsers, so the citation strings above are checked against what ships."""

    def test_a_code_answers_own_citations_resolve(self, synth_dir):
        rep = build_report("3002", synth_dir)
        ans = ask(rep, "What material is it?", llm=None)
        kinds = cited_kinds(ans.text)
        assert kinds, "the answer must name its sources"
        ev = evidence_for(rep, ans.text)
        assert ev and {f.source_type for f in ev} == set(kinds)
        assert all(f.field == "material" for f in ev)

    def test_an_unrecorded_field_is_refused_without_fake_evidence(self, synth_dir):
        rep = build_report("3002", synth_dir)
        ans = ask(rep, "What is the weight?", llm=None)
        assert is_not_found(ans.text)
        assert cited_kinds(ans.text) == []
        assert evidence_for(rep, ans.text) == []

    def test_an_off_topic_question_is_refused_too(self, synth_dir):
        rep = build_report("3002", synth_dir)
        assert is_not_found(ask(rep, "What is the weather today?", llm=None).text)
