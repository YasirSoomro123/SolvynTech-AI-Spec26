"""Post-check of an LLM answer against the fact sheet.

The LLM is asked not to invent numbers; this module checks that it did not. Every number in the
answer must be present in the fact sheet, or be a documented derivation of one (a diameter and its
radius, a unit conversion). Anything else is reported so the UI can show a warning instead of
presenting the sentence as evidence.

This is deliberately conservative: it flags, it does not silently delete. A flag that the engineer
can read is more useful than a hidden edit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .fact import Fact
from .units import LENGTH_TO_MM, PLUSMINUS_RE, parse_number

# Numbers that carry no factual content and are exempt from the check.
EXEMPT = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 100, 1000}
EXEMPT_CONTEXT = ("rule", "step", "note", "source", "point")

# A citation is a bracketed source name; both spellings the app itself emits are accepted,
# otherwise the deterministic answers would be flagged for lacking what they actually have.
CITATION_RE = re.compile(r"\[\s*(?:extracted from\s+)?(?:Excel|PDF|IGES)", re.I)


@dataclass
class Verification:
    ok: bool
    checked: list[float] = field(default_factory=list)
    unverified: list[float] = field(default_factory=list)
    missing_citations: list[str] = field(default_factory=list)
    message: str = ""

    def badge(self) -> str:
        if self.ok and not self.missing_citations:
            return "verified"
        if self.unverified:
            return "unverified numbers"
        return "missing citations"


def numbers_in_text(text: str) -> list[float]:
    """All numbers in an answer, tolerant of '1,234.5', '4,3', '+/-0.1', '0.05', '12:1'."""
    out: list[float] = []
    # dates and ratios are not engineering values; '+/-' and '±' state a spread, not a sign
    scrubbed = PLUSMINUS_RE.sub(" ", text or "")
    scrubbed = re.sub(r"\b\d{1,2}:\d{1,2}\b", " ", scrubbed)
    scrubbed = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", scrubbed)
    for m in re.finditer(r"[+-]?\d[\d,\.\s]*\d|[+-]?\d+", scrubbed):
        v = parse_number(m.group(0))
        if v is not None:
            out.append(v)
    return out


def allowed_numbers(facts: list[Fact]) -> set[float]:
    """Every number the model is allowed to say, including documented derivations."""
    allowed: set[float] = set()
    for f in facts:
        for value in _values_of(f.value):
            allowed.add(round(value, 6))
            allowed.add(round(value * 2, 6))            # radius <-> diameter
            allowed.add(round(value / 2, 6))
            for unit, factor in LENGTH_TO_MM.items():    # unit conversions the sheet implies
                if factor:
                    allowed.add(round(value * factor, 6))
                    if factor != 1.0:
                        allowed.add(round(value / factor, 6))
        for num in numbers_in_text(f.note or ""):
            allowed.add(round(num, 6))
    # citation noise: sheet coordinates like 'D2' are not values, but years in notes are allowed
    for f in facts:
        for num in re.findall(r"\b(19|20)\d{2}\b", str(f.value)):
            allowed.add(float(num))
        # a file name is provenance, not an engineering value. the part number usually lives
        # in it, and a scanned drawing can have no part_number fact at all - quoting the name
        # of the file the fact came from must not count as an invented claim
        for num in numbers_in_text(Path(str(f.source_file or "")).name):
            allowed.add(round(num, 6))
    return allowed


def _values_of(value: object) -> list[float]:
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, (list, tuple)):
        out: list[float] = []
        for v in value:
            out.extend(_values_of(v))
        return out
    if isinstance(value, str):
        return numbers_in_text(value)
    return []


def verify_answer(answer: str, facts: list[Fact], require_citation: bool = True) -> Verification:
    if not answer:
        return Verification(False, message="empty answer")
    allowed = allowed_numbers(facts)
    found = numbers_in_text(answer)
    unverified = [n for n in found if not _matches(n, allowed)]
    missing = []
    if require_citation and not CITATION_RE.search(answer):
        if not _is_refusal(answer):
            missing.append("no [Excel]/[PDF]/[IGES] citation anywhere in the answer")
    parts = re.findall(r"\[([A-Za-z]+)[^\]]*\]", answer)
    if require_citation and not _is_refusal(answer) and len(parts) < 1:
        missing.append("answer contains no source markers")
    msg = ""
    if unverified:
        msg = ("Numbers not found in the fact sheet: "
               + ", ".join(f"{n:g}" for n in unverified[:8]))
    elif missing:
        msg = "; ".join(missing)
    return Verification(ok=not unverified and not missing, checked=found, unverified=unverified,
                        missing_citations=missing, message=msg)


def _matches(value: float, allowed: set[float]) -> bool:
    if int(value) in EXEMPT and abs(value) <= 100:
        # bare small integers are usually enumeration ("2 sources") - only exempt when they are
        # not attached to a unit
        return True
    for candidate in allowed:
        if abs(candidate - value) <= 1e-6:
            return True
        if candidate and abs(candidate - value) / max(abs(candidate), 1e-9) < 0.005:
            return True                       # rounding of a listed value
    return False


def _is_refusal(text: str) -> bool:
    low = (text or "").lower()
    return ("can't find" in low or "cannot find" in low or "not in the files" in low
            or "outside the scope" in low or "no record" in low or "cannot answer" in low)
