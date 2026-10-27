"""Cross-check the three sources for one part and flag disagreements.

Rules that keep the table honest
--------------------------------
* Only numbers that are already converted to millimetres are compared; unit differences are the
  parser's job, not this one's.
* Tolerance is absolute OR relative, whichever is more forgiving (default 0.5 mm / 1%), because a
  0.05 mm difference on a 40 mm length is noise while the same difference on a 0.3 mm shim is not.
* A CAD bounding box is compared as a SORTED list of the three sizes: the axis order depends on
  how the part was modelled, so matching "Z of the model" to "length of the record" is meaningless.
* Values that exist in only one source are ℹ️ informational, never an error. Missing data must not
  look like a conflict.
* Confidence is respected: a `code-low` fact can raise a ⚠️ but the note says so, because the
  drawing/record may be right and the approximation wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from .fact import Fact

# Fields that describe the same physical quantity, possibly under different names per source.
SYNONYM_GROUPS: list[tuple[str, list[str]]] = [
    ("Outer diameter", ["outer_diameter", "diameter", "od"]),
    ("Bore / inner diameter", ["inner_diameter", "bore_diameter", "hole_diameter"]),
    ("Length", ["length", "overall_length", "height", "cylinder_height"]),
    ("Width", ["width"]),
    ("Surface finish Ra", ["surface_finish", "finish"]),
    ("Cycle time", ["cycle_time"]),
    ("Quantity", ["quantity"]),
    ("Revision", ["revision", "rev"]),
    ("Material", ["material"]),
    ("General tolerance", ["general_tolerance"]),
    ("Part name", ["part_name", "name"]),
    ("Supplier reference", ["supplier_ref", "supplier_code"]),
    ("Machine", ["machine"]),
    ("Units declared", ["units", "cad_units"]),
]


STATUS_MATCH = "match"
STATUS_MISMATCH = "mismatch"
STATUS_ONLY = "only-one-source"


@dataclass
class CheckRow:
    label: str
    values: dict[str, str]                 # source type -> displayed value
    status: str                            # match | mismatch | only-one-source
    detail: str = ""
    sources: list[str] = field(default_factory=list)
    worst_confidence: str = "code-high"
    unit: str = ""                         # what the numbers are in: "mm", "min", "" for counts
    spread: Optional[float] = None         # largest closest-pair difference, in that unit
    tolerance: str = ""                    # what this app allowed, e.g. "0.5 mm or 1 %"

    def icon(self) -> str:
        return {STATUS_MATCH: "✅", STATUS_MISMATCH: "⚠️", STATUS_ONLY: "ℹ️"}[self.status]


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _close(a: float, b: float, abs_tol: float, rel_tol: float) -> bool:
    if a == b:
        return True
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))


def _text_equal(a: str, b: str) -> bool:
    """Loose text comparison: case, punctuation and whitespace are not disagreements."""
    import re
    na = re.sub(r"[^0-9a-z]+", " ", (a or "").lower()).strip().split()
    nb = re.sub(r"[^0-9a-z]+", " ", (b or "").lower()).strip().split()
    if not na or not nb:
        return False
    if na == nb:
        return True
    # "Stainless A1" vs "Stainless Steel A1": one describing the other is not a conflict
    if set(na) <= set(nb) or set(nb) <= set(na):
        return True
    return "".join(na) == "".join(nb)


def collect_values(facts: Iterable[Fact], fields: list[str]) -> dict[str, list[Fact]]:
    """Facts for these field names, grouped by source type (Excel/PDF/IGES)."""
    out: dict[str, list[Fact]] = {}
    wanted = set(fields)
    for f in facts:
        if f.field in wanted:
            out.setdefault(f.source_type, []).append(f)
    return out


def _specific_bore_sizes(facts: list[Fact]) -> list[float]:
    return [f.value for f in facts
            if f.field in {"inner_diameter", "bore_diameter", "hole_diameter"}
            and _is_number(f.value)]


def crosscheck(facts: list[Fact], abs_tol_mm: float = 0.5, rel_tol: float = 0.01,
               bbox_field: str = "bounding_box_size") -> list[CheckRow]:
    """Compare every shared quantity across sources. Never raises."""
    rows: list[CheckRow] = []

    # 1) plain quantity comparison, mm-normalised
    for label, fields in SYNONYM_GROUPS:
        grouped = collect_values(facts, fields)
        if "diameter" in fields:
            # a bare "DIA x" that repeats the bore is the bore, not the outside
            bores = _specific_bore_sizes(facts)
            grouped = {s: [f for f in items if not (
                f.field == "diameter" and any(_close(f.value, b, abs_tol_mm, rel_tol)
                                              for b in bores))] for s, items in grouped.items()}
            grouped = {s: items for s, items in grouped.items() if items}
        if not grouped:
            continue
        rows.append(_row_for_group(label, grouped, abs_tol_mm, rel_tol))

    # 2) IGES envelope vs record/drawing sizes, sorted so axis order cannot matter
    bbox = next((f for f in facts if f.field == bbox_field and isinstance(f.value, (list, tuple))),
                None)
    if bbox:
        rows.append(_bbox_row(bbox, facts, abs_tol_mm, rel_tol))
    return rows


def _unit_of(items: list[Fact]) -> str:
    units = [f.unit for f in items if f.unit]
    if not units:
        return ""
    top = max(set(units), key=units.count)
    if units.count(top) == len(units):
        return top
    return "several: " + ", ".join(sorted(set(units)))


def _row_for_group(label: str, grouped: dict[str, list[Fact]], abs_tol: float,
                   rel_tol: float) -> CheckRow:
    per_source: dict[str, str] = {}
    numbers: dict[str, list[tuple[float, Fact]]] = {}
    texts: dict[str, list[tuple[str, Fact]]] = {}
    for source, items in grouped.items():
        nums = [(f.value, f) for f in items if _is_number(f.value)]
        strs = [(str(f.value), f) for f in items if not _is_number(f.value) and f.value]
        if nums:
            numbers[source] = nums
            per_source[source] = " + ".join(
                f"{v:g}{' ' + (f.unit or '') if f.unit and f.unit != 'mm' else ''}"
                for v, f in nums[:3])
        elif strs:
            texts[source] = strs
            per_source[source] = strs[0][0][:40]

    all_facts = [f for items in grouped.values() for f in items]
    # the row is only as trustworthy as its least trustworthy source
    worst = max((f.confidence for f in all_facts),
                key=lambda c: ["code-high", "code-medium", "code-low", "llm-vision",
                               "inferred"].index(c) if c in
                ["code-high", "code-medium", "code-low", "llm-vision", "inferred"] else 9)

    if numbers:
        # any pair from different sources that agrees is enough to call the group consistent
        disagree: list[str] = []
        closest: list[float] = []
        sources = sorted(numbers)
        for i, s_a in enumerate(sources):
            for s_b in sources[i + 1:]:
                best = None
                for v_a, f_a in numbers[s_a]:
                    for v_b, f_b in numbers[s_b]:
                        d = abs(v_a - v_b)
                        if best is None or d < best[0]:
                            best = (d, v_a, v_b, f_a, f_b)
                if best:
                    closest.append(best[0])
                    if not _close(best[1], best[2], abs_tol, rel_tol):
                        disagree.append(f"{s_a} {best[1]:g} vs {s_b} {best[2]:g}")
        unit = _unit_of(all_facts)
        # the absolute allowance is a raw number compared against the values in this row,
        # so it has to be named in the row's own unit - calling a 0.5 µm allowance
        # "0.5 mm" would tell the judge the app is looser than it actually is
        tol = f"{abs_tol:g} {unit or 'mm'} or {rel_tol * 100:g} %"
        spread = max(closest) if closest else None
        if len(sources) == 1:
            return CheckRow(label, per_source, STATUS_ONLY,
                            f"only present in {sources[0]}", sources, worst, unit, None,
                            "nothing to compare it with")
        if disagree:
            return CheckRow(label, per_source, STATUS_MISMATCH, "; ".join(disagree),
                            sources, worst, unit, spread, tol)
        return CheckRow(label, per_source, STATUS_MATCH,
                        f"agree within {abs_tol:g} {unit or 'mm'} / {rel_tol * 100:g} %",
                        sources, worst, unit, spread, tol)

    if texts:
        sources = sorted(texts)
        if len(sources) == 1:
            return CheckRow(label, per_source, STATUS_ONLY,
                            f"only present in {sources[0]}", sources, worst, "", None,
                            "nothing to compare it with")
        # two sources agree when ANY of their spellings agree: one file often states
        # a material twice (title block + note, or with the standard number)
        disagree: list[str] = []
        for i, s_a in enumerate(sources):
            for s_b in sources[i + 1:]:
                if not any(_text_equal(a, b) for a, _ in texts[s_a] for b, _ in texts[s_b]):
                    disagree.append(f"{s_a} '{texts[s_a][0][0][:32]}' vs "
                                    f"{s_b} '{texts[s_b][0][0][:32]}'")
        tol = "case, punctuation and a shorter full spelling ignored"
        return CheckRow(label, per_source, STATUS_MATCH if not disagree else STATUS_MISMATCH,
                        "text values match" if not disagree else "; ".join(disagree),
                        sources, worst, "", None, tol)
    return CheckRow(label, per_source, STATUS_ONLY, "no comparable value", sources, worst,
                    "", None, "no comparable value")


def _bbox_row(bbox: Fact, facts: list[Fact], abs_tol: float, rel_tol: float) -> CheckRow:
    """Compare the model's sorted envelope with the record's/drawing's diameters and length."""
    sizes = sorted([s for s in (bbox.value or []) if _is_number(s)], reverse=True)
    tol = f"{abs_tol:g} mm or {rel_tol * 100:g} %"
    if not sizes:
        return CheckRow("Model envelope vs listed sizes", {"IGES": "(none)"}, STATUS_ONLY,
                        "bounding box not available", ["IGES"], bbox.confidence, "", None,
                        "nothing to compare it with")
    model = {"IGES": ", ".join(f"{s:g}" for s in sizes)}
    listed: list[tuple[str, float, Fact]] = []
    for f in facts:
        if f.source_type == "IGES":
            continue
        if f.field in ("outer_diameter", "length", "width", "diameter", "height") and _is_number(f.value):
            listed.append((f.source_type, float(f.value), f))
    if not listed:
        return CheckRow("Model envelope vs listed sizes", model, STATUS_ONLY,
                        "no sizes listed in the other sources", ["IGES"], bbox.confidence,
                        bbox.unit or "mm", None, "nothing to compare it with")
    unmatched: list[str] = []
    matched: list[str] = []
    gaps: list[float] = []
    for source, value, f in listed:
        # a diameter matches either the largest or the second-largest envelope size, since a
        # turned part's box is (OD, OD, length) in some order
        pool = sizes[:2] + sizes[-1:]
        hit = min(pool, key=lambda s: abs(s - value))
        gaps.append(abs(hit - value))
        if _close(hit, value, abs_tol, rel_tol):
            matched.append(f"{source} {value:g} ~ model {hit:g}")
        else:
            unmatched.append(f"{source} says {value:g} mm, closest model extent is {hit:g} mm")
    per_source = dict(model)
    per_source["record/drawing"] = ", ".join(f"{v:g}" for _, v, _ in listed)
    detail = "; ".join(matched) if not unmatched else "; ".join(unmatched)
    spread = max(gaps) if gaps else None
    unit = bbox.unit or "mm"
    if unmatched:
        return CheckRow("Model envelope vs listed sizes", per_source, STATUS_MISMATCH,
                        detail + f"  ({bbox.note})", ["IGES", "Excel", "PDF"], bbox.confidence,
                        unit, spread, tol)
    return CheckRow("Model envelope vs listed sizes", per_source, STATUS_MATCH,
                    detail + " - envelope is approximate, so agreement is a sanity check, "
                             "not a measurement", list(per_source), bbox.confidence,
                    unit, spread, tol + " (envelope is approximate)")


def summary(rows: list[CheckRow]) -> str:
    """One plain-language sentence about what agrees and what does not."""
    if not rows:
        return ("Nothing overlaps between the files, so there is no agreement to report and "
                "no disagreement to hide.")
    bad = [r for r in rows if r.status == STATUS_MISMATCH]
    only = sum(1 for r in rows if r.status == STATUS_ONLY)
    ok = len(rows) - len(bad) - only
    line = f"{ok} of {len(rows)} checks agree. "
    if not bad:
        line += ("No two files give a different number for the same item"
                 + (f"; {only} item(s) are stated by only one file, so nothing conflicts."
                    if only else "."))
        return line
    parts = []
    for r in bad:
        gap = ""
        if r.spread is not None:
            gap = f" - about {r.spread:g}{(' ' + r.unit) if r.unit else ''} apart"
            if r.tolerance:
                gap += f", over the {r.tolerance} allowance"
        parts.append(f"{r.label} ({r.detail}{gap})")
    line += (f"{len(bad)} do{'es' if len(bad) == 1 else ''} not: " + "; ".join(parts) + ". "
             "Both numbers are kept; nothing is averaged or picked silently.")
    return line
