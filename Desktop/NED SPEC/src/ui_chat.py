"""The chat panel's content, computed in code so it can be tested without a browser.

Nothing here calls a language model. The greeting states which files were read, the
evidence rows are the facts the answer actually cited, and the follow-up questions are
picked from the fields this part really has - a suggested question must never ask for
something the files do not contain, because that would train the user to distrust the
honest "not found" answers.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from src.fact import Fact
from src.pipeline import Report

KINDS = ("Excel", "PDF", "IGES")
# 'PDF'.title() is 'Pdf', which matches no source_type - every source has to come back
# in the exact spelling the facts use.
KIND_BY_LOWER = {k.lower(): k for k in KINDS}

# `[Excel: file, location; confidence code-high; note]` / `[extracted from PDF: ...]`
CITATION = re.compile(r"\[\s*(?:extracted from\s+)?(Excel|PDF|IGES|\?)\s*:\s*([^\]]*)\]", re.I)

NOT_FOUND = ("i can't find", "cannot find", "not in the files", "no value", "not stated",
             "nothing in the files", "does not appear", "not available for this part",
             "i could not find", "not recorded")

# asked-about words that must not come back as a suggestion
_STOP = ("what", "which", "the", "is", "of", "and", "for", "this", "part", "tell")


def cited_kinds(text: str) -> list[str]:
    """Which sources this answer quotes, in Excel/PDF/IGES order."""
    found = {KIND_BY_LOWER.get(m.group(1).lower(), "") for m in CITATION.finditer(text or "")}
    return [k for k in KINDS if k in found]


def _citations(f: Fact) -> tuple[str, str]:
    """The two citation strings that can name this fact.

    `full` is what this app's own code answers print (file, place, confidence and note), so
    it identifies exactly one fact. `sheet` is the shorter form the language model is given,
    where two facts can share one place - it is only safe with a second check.
    """
    name = Path(str(f.source_file or "")).name
    full = (f"[extracted from {f.source_type}: {name}, {f.location}; confidence {f.confidence}"
            + (f"; {f.note}" if f.note else "") + "]")
    return full, f"[{f.source_type}: {name}, {f.location}]"


BRACKET = re.compile(r"\[[^\]]*\]")

# a model often copies a value back with a no-break or thin space inside it; that is still
# the same value, so comparing them has to ignore which space character was used
ODD_SPACES = {c: " " for c in ("\u00a0", "\u2007", "\u2009", "\u200a", "\u202f", "\u2060")}


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).translate(ODD_SPACES)).strip().lower()


def _quoted(value: str, prose: str) -> bool:
    """Is this value stated in the answer itself, not merely inside a citation?

    Without the word boundary, a one-letter value ('A' = revision) would 'appear' in almost
    any sentence, and a part number would appear through the file name in the citation.
    """
    v = flat(value)
    if not v:
        return False
    return re.search(r"(?<![\w.])" + re.escape(v) + r"(?![\w])", prose) is not None


def evidence_for(rep: Report, text: str) -> list[Fact]:
    """The facts this answer quoted, found by their citation string rather than by guesswork.

    A citation that names no known fact is dropped instead of padded with a plausible
    substitute, and where the short citation covers several facts the answer must also state
    the value - otherwise the Evidence panel would claim proof the answer never had.
    """
    t = flat(text or "")
    prose = BRACKET.sub(" ", t)
    shared: dict[str, int] = {}
    for f in rep.facts:
        shared[_citations(f)[1]] = shared.get(_citations(f)[1], 0) + 1
    scored: list[tuple[int, int, Fact]] = []
    for index, f in enumerate(rep.facts):
        full, sheet = _citations(f)
        if flat(full) in t:
            scored.append((2, index, f))
        elif flat(sheet) in t and (_quoted(f.display_value(), prose) or shared[sheet] == 1):
            scored.append((1, index, f))
    scored.sort(key=lambda s: (-s[0], s[1]))
    out: list[Fact] = []
    seen: set[tuple[str, str]] = set()
    for _, _, f in scored:
        mark = (_citations(f)[1], str(f.display_value()))
        if mark in seen:
            continue
        seen.add(mark)
        out.append(f)
    return out


def is_not_found(text: str) -> bool:
    low = (text or "").lower()
    return any(p in low for p in NOT_FOUND)


def greeting(rep: Report) -> str:
    """What the assistant says the moment a part is opened: what it read, what it did not."""
    paths = rep.files.paths() if rep.files else {}
    got = [k for k in KINDS if paths.get(k) is not None]
    missing = [k for k in KINDS if paths.get(k) is None]
    line = (f"Hi! I've loaded part **{rep.part}** from "
            f"{', '.join(got) if got else 'no source I could read'}. Ask me anything about it.")
    if missing:
        line += (f" {' and '.join(missing)} "
                 f"{'was' if len(missing) == 1 else 'were'} not found for this part, so "
                 f"anything only {'they' if len(missing) == 1 else 'it'} would have said is "
                 f"marked as missing rather than guessed.")
    line += f" I have {len(rep.facts)} facts and compared them in {len(rep.rows)} ways."
    return line


def _fields_present(rep: Report) -> set[str]:
    return {f.field for f in rep.facts}


def followups(rep: Report, asked: str = "", limit: int = 3) -> list[str]:
    """Short next questions, chosen from the fields this part actually has."""
    have = _fields_present(rep)
    pool = [
        ("What are its main dimensions?", ("outer_diameter", "length", "dimension")),
        ("What tolerance class applies?", ("general_tolerance", "tolerance")),
        ("What surface finish is required?", ("surface_finish",)),
        ("Which machine and operations?", ("machine", "operations")),
        ("How many are needed, and what cycle time?", ("quantity", "cycle_time")),
        ("Compare dimensions across sources", ()),
        ("What does the 3D model add?", ("bounding_box_size", "cad_units", "cylinder_radius")),
        ("What is the revision and supplier code?", ("revision", "supplier_ref")),
        ("What is it made of?", ("material",)),
    ]
    asked_words = {w for w in re.findall(r"[a-z]+", asked.lower()) if w not in _STOP}
    out: list[str] = []
    for question, needs in pool:
        if needs and not any(n in have for n in needs):
            continue
        topic = {w for w in re.findall(r"[a-z]+", question.lower())
                 if w not in _STOP and len(w) > 4}
        if topic and asked_words >= topic:
            continue                        # this is what was just asked
        out.append(question)
        if len(out) >= limit:
            break
    return out


def levels(rep: Report) -> list[tuple[str, str, bool, str]]:
    """What the problem statement asks for, and whether THIS part reaches it right now.

    Deliberately counted from what was extracted, never claimed because the app has the
    feature: if no PDF was found for this part, the level that needs a drawing is not reached.
    """
    have = {f.source_type for f in rep.facts if f.source_type in KINDS}
    rows = len(rep.rows)
    out = [("Level 1", "Excel record read, facts extracted by code, plain-language answers",
            "Excel" in have, f"{sum(1 for f in rep.facts if f.source_type == 'Excel')} fact(s)"
            " from the record" if "Excel" in have else "no Excel/CSV facts for this part")]
    out.append(("Level 2", "+ PDF drawing, every answer states which file it came from",
                "PDF" in have,
                f"{sum(1 for f in rep.facts if f.source_type == 'PDF')} fact(s) from the drawing"
                if "PDF" in have else "no PDF facts for this part"))
    out.append(("Level 3", "+ IGES geometry, three-way cross-check with disagreements flagged",
                "IGES" in have and rows > 0,
                f"{sum(1 for f in rep.facts if f.source_type == 'IGES')} model fact(s), "
                f"{rows} cross-check(s)" if "IGES" in have else "no IGES facts for this part"))
    out.append(("Stretch", "any part number in the folder, chosen at run time",
                rep.files is not None and bool(rep.files.paths()),
                f"part {rep.part} was located by scanning the folder"
                if rep.files is not None and rep.files.paths() else "no file matched this number"))
    return out


def level_summary(rep: Report) -> str:
    """'Level 3 data available' for the current part - counted, never claimed."""
    got = [name for name, _, reached, _ in levels(rep) if reached and name != "Stretch"]
    missing = [name for name, _, reached, _ in levels(rep)
               if not reached and name != "Stretch"]
    line = f"{got[-1] if got else 'Level 0'} data available for part {rep.part}"
    if missing:
        line += f" - {', '.join(missing)} not reached: this part's files do not carry that source"
    return line


def mode_label(mode: str) -> str:
    return {"llm": "LLM answer",
            "local": "Local reply (no model call)",
            "code": "Code answer (deterministic)",
            "no-llm": "Code answer (no LLM in use)",
            "limited": "Code answer (model unavailable)",
            "error": "Answer failed (no LLM)"}.get(mode, mode)


RATING = {0: "not helpful", 1: "helpful"}


def evidence_rows(facts: Iterable[Fact]) -> list[dict]:
    """The Evidence panel: what was claimed, and the exact place it was claimed in."""
    rows = []
    for f in facts:
        name = str(f.source_file or "").replace("\\", "/").rsplit("/", 1)[-1]
        rows.append({"Fact": f.field.replace("_", " "), "Value": f.display_value(),
                     "Source": f.source_type, "File": name, "Where": f.location,
                     "Confidence": f.confidence, "Note": f.note or "-"})
    return rows


def chat_markdown(part: str, root: str, history: Iterable[dict]) -> str:
    """The conversation as a plain-text transcript, citations included."""
    lines = [f"# Chat - part {part}", "", f"Data folder: `{root}`", ""]
    for msg in history:
        if msg["role"] == "user":
            lines += [f"**You:** {msg['text']}", ""]
            continue
        head = f"**Assistant** ({msg.get('mode', '?')}"
        if msg.get("model"):
            head += f", {msg['model']}"
        if msg.get("rating") in RATING:
            head += f", rated {RATING[msg['rating']]}"
        lines += [f"{head}): {msg['text']}", ""]
        if msg.get("v_ok") is False:
            lines += [f"> Rejected by the verifier: {msg.get('v_msg', '')}", ""]
    return "\n".join(lines)
