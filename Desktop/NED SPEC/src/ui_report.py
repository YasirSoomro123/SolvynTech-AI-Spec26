"""The one-page part report and the data-quality score, both computed in code.

No language model is used here on purpose: the report is the document a judge or a planner
would put in a folder, so every line has to be traceable back to a parser. A model that
"improved" one number on this page would make the page worth less than nothing.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from src.crosscheck import STATUS_MATCH, STATUS_MISMATCH, STATUS_ONLY
from src.pipeline import Report
from src.ui_chat import KINDS, levels

# the report is printed and read on paper, so it uses words instead of emoji
WORD = {STATUS_MATCH: "AGREE", STATUS_MISMATCH: "DIFFER", STATUS_ONLY: "ONE SOURCE"}

STRONG_CONFIDENCE = ("code-high", "code-medium")
# what each part of the score is worth: the files first, then how well they were read
WEIGHTS = (("Excel", 25), ("PDF", 20), ("IGES", 15))


def quality(rep: Report) -> tuple[int, list[str]]:
    """0-100 for how much of this part could actually be read, with the reasons.

    This is *this app's* rubric and the UI says so: it measures the evidence in front of
    it, not the quality of the part, and every point taken off names a real gap.
    """
    have = {f.source_type for f in rep.facts}
    if not rep.facts:
        # an empty part must not earn marks for having nothing to disagree about
        return 0, ["nothing was extracted for this part, so there is no evidence to score"]
    score = 0
    why: list[str] = []
    for kind, pts in WEIGHTS:
        if kind in have:
            score += pts
        else:
            why.append(f"no {kind} facts were extracted for this part (-{pts})")

    weak = [f for f in rep.facts if f.confidence not in STRONG_CONFIDENCE]
    got = round(15 * (len(rep.facts) - len(weak)) / len(rep.facts))
    if got < 15:
        why.append(f"{len(weak)} of {len(rep.facts)} fact(s) came from a weaker read - "
                   f"vision, inference or a low-confidence code match (-{15 - got})")
    score += got

    bad = [r for r in rep.rows if r.status == STATUS_MISMATCH]
    if bad:
        lost = min(15, 5 * len(bad))
        score += 15 - lost
        why.append(f"{len(bad)} cross-check(s) found two files disagreeing (-{lost})")
    else:
        score += 15

    warn = rep.all_warnings()
    if warn:
        lost = min(10, 3 * len(warn))
        score += 10 - lost
        why.append(f"{len(warn)} warning(s) about how the files were read (-{lost})")
    else:
        score += 10
    return max(0, min(100, score)), why


def _line(r) -> str:
    """One cross-check as a sentence: the values, then how far apart they are and what
    was allowed."""
    vals = ", ".join(f"{source} {value}" for source, value in r.values.items() if value)
    notes = []
    if r.unit:
        notes.append(f"unit {r.unit}")
    if r.spread is not None:
        notes.append(f"largest gap {r.spread:g} {r.unit}".rstrip())
    if r.tolerance:
        notes.append(f"allowance {r.tolerance}")
    tail = f" - {'; '.join(notes)}" if notes else ""
    return f"{WORD[r.status]} - {r.label}: {vals or 'nothing to show'}{tail}. {r.detail}."


def report_blocks(rep: Report, model: str = "none in use") -> list[tuple[str, str]]:
    """The report as (kind, text) blocks - one source of truth for the screen and the PDF."""
    paths = rep.files.paths() if rep.files else {}
    counts: Counter[str] = Counter(f.source_type for f in rep.facts)
    blocks: list[tuple[str, str]] = [(
        "h1", f"Part {rep.part} - record, drawing and model report")]
    blocks.append(("p", f"Data folder {rep.root}. {len(rep.facts)} fact(s) read by code from "
                        f"{len(paths)} file(s), compared in {len(rep.rows)} way(s), "
                        f"{len(rep.all_warnings())} warning(s)."))

    blocks.append(("h2", "Files used"))
    for kind in KINDS:
        path = paths.get(kind)
        if path is None:
            blocks.append(("li", f"{kind}: no file was matched to this part"))
        else:
            blocks.append(("li", f"{kind}: {Path(str(path)).name} - {counts.get(kind, 0)} "
                                 f"fact(s) extracted"))
    blocks.append(("h2", "How each file was read"))
    detail = _result_lines(rep)
    blocks.extend(("li", f"{kind}: {text}") for kind, text in detail)
    if not detail:
        blocks.append(("li", "No extraction detail was recorded."))

    blocks.append(("h2", "What the sources say"))
    if rep.rows:
        blocks.extend(("kv", _line(r)) for r in rep.rows)
    else:
        blocks.append(("li", "No two files state the same item, so there is nothing to "
                             "compare. The facts are listed below instead."))

    blocks.append(("h2", "Fields only one file states"))
    only = [r.label for r in rep.rows if r.status == STATUS_ONLY]
    blocks.append(("li", ", ".join(only) if only else "None - every compared item appears "
                                                      "in more than one file."))

    blocks.append(("h2", "Where the files disagree"))
    bad = [r for r in rep.rows if r.status == STATUS_MISMATCH]
    if bad:
        blocks.extend(("li", f"{r.label}: {r.detail}") for r in bad)
        blocks.append(("note", "Both numbers are kept. The app does not average them and "
                               "does not choose one silently."))
    else:
        blocks.append(("li", "No disagreement was found between the files for this part."))

    blocks.append(("h2", "Other fields read from the files"))
    compared = {f for r in rep.rows for f in _row_fields(r)}
    spare = [f for f in rep.facts if f.field not in compared]
    if spare:
        blocks.extend(("li", f"{f.field.replace('_', ' ')}: {f.display_value()} "
                             f"[{f.source_type}, {f.location}, {f.confidence}]")
                      for f in spare[:40])
        if len(spare) > 40:
            blocks.append(("li", f"...and {len(spare) - 40} more on the Extracted facts tab."))
    else:
        blocks.append(("li", "Every extracted field is already in the comparison above."))

    blocks.append(("h2", "Warnings"))
    warn = rep.all_warnings()
    blocks.extend(("li", w) for w in warn[:20])
    if len(warn) > 20:
        blocks.append(("li", f"...and {len(warn) - 20} more on the Warnings tab."))
    if not warn:
        blocks.append(("li", "None."))

    blocks.append(("h2", "Levels reached for this part"))
    for name, needs, reached, why in levels(rep):
        blocks.append(("li", f"{name} - {'yes' if reached else 'no'}: {needs}. Evidence: {why}."))

    score, why = quality(rep)
    blocks.append(("h2", f"Data quality for this part: {score}/100"))
    blocks.extend(("li", w) for w in why)
    if not why:
        blocks.append(("li", "Nothing was taken off: all three sources were read, every fact "
                             "came from a confident code read, and nothing disagreed."))
    blocks.append(("note", "This score is this app's own rubric - 60 points for which files "
                           "were readable, 15 for how confidently they were parsed, 15 for "
                           "agreement between them and 10 for a clean run. It describes the "
                           "evidence, not the part."))

    blocks.append(("h2", "How to read this page"))
    blocks.append(("note", f"Every number above was produced by the parsers; the language "
                           f"model ({model}) is only used to put extracted numbers into "
                           f"sentence form when a question is asked, and its answers are "
                           f"checked against the fact sheet afterwards. A value that no file "
                           f"states is reported as missing rather than estimated."))
    return blocks


def _result_lines(rep: Report) -> list[tuple[str, str]]:
    """Per-source extraction detail, so the report says how much of each file was read."""
    return [(res.source_type, res.detail) for res in rep.results if res.detail]


def _row_fields(r) -> list[str]:
    """The field names behind one cross-check row (used to avoid listing them twice)."""
    from src.crosscheck import SYNONYM_GROUPS
    for label, fields in SYNONYM_GROUPS:
        if label == r.label:
            return fields
    return []


def report_markdown(rep: Report, model: str = "none in use") -> str:
    """Markdown for the Download button - opens in any editor, prints as a page."""
    out: list[str] = []
    for kind, text in report_blocks(rep, model):
        if kind == "h1":
            out += [f"# {text}", ""]
        elif kind == "h2":
            out += [f"## {text}", ""]
        elif kind == "p":
            out += [text, ""]
        elif kind == "note":
            out += [f"> {text}", ""]
        else:
            out.append(f"- {text}")
    return "\n".join(out).rstrip() + "\n"


# --------------------------------------------------------------------------- PDF
PAGE = (595.0, 842.0)                          # A4 portrait, points
MARGIN = 48.0
STYLE = {                                      # kind -> (font, size, leading, indent, gap)
    "h1": ("hebo", 16.0, 20.0, 0.0, 8.0),
    "h2": ("hebo", 11.5, 16.0, 0.0, 9.0),
    "p": ("helv", 9.5, 13.0, 0.0, 5.0),
    "li": ("helv", 9.5, 13.0, 14.0, 1.5),
    "kv": ("helv", 9.5, 13.0, 14.0, 1.5),
    "note": ("helv", 9.0, 12.5, 14.0, 5.0),
}


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    """Greedy word wrap measured with the font the PDF will actually use."""
    import pymupdf
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = f"{line} {w}".strip()
        if line and pymupdf.get_text_length(trial, fontname=font, fontsize=size) > width:
            lines.append(line)
            line = w
        else:
            line = trial
    if line:
        lines.append(line)
    return lines or [""]


def report_pdf(rep: Report, model: str = "none in use") -> bytes:
    """The same blocks laid out on A4. Text only - no screenshot of the browser."""
    import pymupdf
    doc = pymupdf.open()
    usable = PAGE[0] - 2 * MARGIN
    page, y = None, 0.0

    def new_page() -> None:
        nonlocal page, y
        page = doc.new_page(width=PAGE[0], height=PAGE[1])
        y = MARGIN

    def put(font: str, size: float, text: str, x: float) -> None:
        page.insert_text((x, y), text, fontname=font, fontsize=size, color=(0.08, 0.09, 0.11))

    for kind, text in report_blocks(rep, model):
        font, size, leading, indent, gap = STYLE.get(kind, STYLE["p"])
        body = ("\u2022 " if kind in ("li", "kv") else "") + text
        lines = _wrap(body, font, size, usable - indent)
        if page is None or y + gap + len(lines) * leading > PAGE[1] - MARGIN:
            new_page()
        y += gap
        for ln in lines:
            put(font, size, ln, MARGIN + indent)
            y += leading
    if page is None:
        new_page()
    data = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return data
