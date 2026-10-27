"""Orchestration: part number + data folder -> fact sheet -> cross-check -> answer.

Level order matters here. Everything up to ``build_report`` is pure code and works with
no LLM and no network: file discovery, the three parsers, per-part filtering and the
cross-check table. The LLM is only used on top of that, and only in three places
(header mapping, scanned-drawing transcription, phrasing the final answer).

The report object is what the CLI and the Streamlit app render, so both show exactly
the same evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .crosscheck import CheckRow, crosscheck
from .excel_reader import read_spreadsheet, rows_for_part
from .fact import Fact, SourceResult
from .iges_reader import read_iges
from .part_locator import PartFiles, discover_parts, locate
from .pdf_reader import read_pdf
from .prompts import (HEADER_MAP_SYSTEM, SYSTEM_PROMPT, build_answer_prompt,
                      header_map_prompt, render_crosscheck, render_fact_sheet)
from .schema import CANONICAL_FIELDS, normalise_header
from .verifier import Verification, verify_answer
from .llm_client import LLMClient, LLMError, parse_json_object

PARSERS = {"Excel": read_spreadsheet, "PDF": read_pdf, "IGES": read_iges}


@dataclass
class Report:
    """Everything known about one part, before any language model is involved."""

    part: str
    root: Path
    files: Optional[PartFiles] = None
    results: list[SourceResult] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    rows: list[CheckRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.facts)

    def by_source(self) -> dict[str, list[Fact]]:
        out: dict[str, list[Fact]] = {}
        for f in self.facts:
            out.setdefault(f.source_type, []).append(f)
        return out

    def fact_sheet(self) -> str:
        return render_fact_sheet(self.facts)

    def table(self) -> str:
        return render_crosscheck(self.rows)

    def sources(self) -> str:
        """Human-readable 'what was used, what was rejected' block."""
        lines: list[str] = []
        if self.files is None:
            lines.append(f"No files could be matched to part {self.part} under {self.root}.")
        else:
            for kind, path in self.files.paths().items():
                lines.append(f"{kind}: {path.name}  ({path})")
            for miss in self.files.missing_kinds:
                lines.append(f"{miss}: NOT FOUND - continuing without it")
            if self.files.rejected:
                lines.append(f"rejected candidates: "
                             + ", ".join(c.path.name for c in self.files.rejected[:8]))
        for res in self.results:
            lines.append(f"  {res.source_type} {Path(res.file).name}: {res.detail}")
        for w in self.all_warnings():
            lines.append(f"WARN: {w}")
        return "\n".join(lines)

    def all_warnings(self) -> list[str]:
        return self.warnings + [w for res in self.results for w in res.warnings]


def _header_mapper(llm: Optional[LLMClient]):
    """One-time LLM help for unreadable column headings. It may only rename a header."""
    if llm is None or not llm.available:
        return None

    def map_headers(headers: list[str], samples: list[list[str]]) -> dict[str, str]:
        reply = llm.chat(HEADER_MAP_SYSTEM, header_map_prompt(headers, samples))
        data = parse_json_object(reply) or {}
        known = set(CANONICAL_FIELDS)
        return {str(k): str(v) for k, v in data.items()
                if str(v) in known}                      # reject invented field names

    return map_headers


def build_report(part: str, root: Path | str, *, llm: Optional[LLMClient] = None,
                 use_llm_headers: bool = True) -> Report:
    """Find, parse and cross-check every file that belongs to ``part``."""
    root = Path(root)
    rep = Report(part=part, root=root)
    if not root.is_dir():
        rep.warnings.append(f"data folder '{root}' does not exist")
        return rep
    rep.files = locate(part, root)
    paths = rep.files.paths()
    if not paths:
        rep.warnings.append(f"no Excel/PDF/IGES file for part '{part}' was found under {root}; "
                            f"parts seen here: {', '.join(discover_parts(root)[:20]) or 'none'}")
        return rep
    if rep.files.missing_kinds:
        rep.warnings.append("missing file type(s): " + ", ".join(rep.files.missing_kinds)
                            + " - the analysis continues with what exists")

    mapper = _header_mapper(llm) if use_llm_headers else None
    vision = None
    if llm is not None and llm.available and llm.supports_vision():
        vision = llm.read_images

    for kind in ("Excel", "PDF", "IGES"):
        path = paths.get(kind)
        if path is None:
            continue
        try:
            if kind == "Excel":
                res = read_spreadsheet(path, header_mapper=mapper)
            elif kind == "PDF":
                res = read_pdf(path, vision=vision)
            else:
                res = read_iges(path)
        except Exception as exc:                      # a broken file must not kill the run
            res = SourceResult(kind, str(path), ok=False)
            res.warn(f"parser failed ({type(exc).__name__}: {exc})")
        rep.results.append(res)

        facts = res.facts
        if kind == "Excel" and res.facts:
            mine = rows_for_part(res, part)
            if mine:
                facts = mine
            else:
                rep.warnings.append(f"{path.name}: no row matched part '{part}', "
                                    "using every row of this workbook")
        rep.facts.extend(facts)
        if not res.ok:
            rep.warnings.append(f"{kind} file {path.name} could not be read")

    # a drawing/record that names a different part is a discovery error worth reporting
    for f in rep.facts:
        if f.field == "part_number" and _norm_str(f.value) != _norm_str(part):
            rep.warnings.append(f"{f.source_type} file {Path(f.source_file).name} states part "
                                f"{f.value} although its name matched '{part}'")
    rep.rows = crosscheck(rep.facts)
    return rep


def _norm_str(value: object) -> str:
    return normalise_header(str(value if value is not None else ""))


@dataclass
class Answer:
    """One question answered from one report."""

    question: str
    text: str
    mode: str                          # "llm" | "code" | "no-llm" | "error"
    model: str = ""
    verification: Optional[Verification] = None


FIELD_PHRASES: dict[str, tuple[str, ...]] = {
    # words a human types, mapped to the canonical field they mean
    "material": ("material", "matl", "made of", "grade", "alloy"),
    "outer_diameter": ("outer diameter", "od", "outside diameter", "diameter"),
    "inner_diameter": ("inner diameter", "bore", "hole size", "inside diameter"),
    "length": ("length", "long", "height", "overall"),
    "quantity": ("quantity", "qty", "how many", "pieces"),
    "cycle_time": ("cycle time", "cycle", "machining time", "how long to machine", "run time"),
    "general_tolerance": ("tolerance", "tol"),
    "surface_finish": ("finish", "roughness", "ra", "surface quality"),
    "operations": ("operation", "ops", "process", "routing", "steps", "machining"),
    "machine": ("machine", "cnc", "equipment"),
    "cost": ("cost", "price"),
    "weight": ("weight", "mass"),
    "revision": ("revision", "rev"),
    "supplier_ref": ("supplier", "vendor", "catalogue", "order code"),
    "part_name": ("name", "description", "part name"),
    "drawing_no": ("drawing number", "drawing no"),
    "bounding_box_size": ("bounding box", "envelope", "overall size", "3d model"),
    "dimension": ("main dimensions", "dimension", "size", "how big"),
    "scale": ("scale",),
    "units": ("unit", "units"),
    "cad_units": ("cad units", "model units"),
}

# A drawing declares its units in the title block and the model declares its own in the
# IGES header; asking about units should show both spellings of the same question.
FIELD_TWINS: dict[str, tuple[str, ...]] = {
    "units": ("cad_units",),
    "cad_units": ("units",),
    "dimension": ("outer_diameter", "inner_diameter", "length"),
    "bounding_box_size": ("cylinder_radius", "cylinder_height"),
}

# 'what are its dimensions?' is asked about the named sizes, not about the unlabelled
# numbers lying around on the view, so those fields are printed first for this group.
TWIN_FIRST = frozenset({"dimension"})

# questions about the sources agreeing, not about one field
CHECK_PHRASES = ("agree", "agreement", "consistent", "match", "disagree", "conflict",
                 "mismatch", "cross check", "cross-check", "compare", "verify")


FALLBACK_FIELDS = {                      # asked for X, the files only carry Y
    "outer_diameter": ("diameter",),
    "inner_diameter": ("hole_diameter",),
}


def _phrase_hit(phrase: str, q: str) -> bool:
    """Whole-word match that forgives a plural: 'which machines' means 'machine'."""
    pat = r"(?:^| )" + r"\s+".join(re.escape(w) + r"(?:s|es)?" for w in phrase.split())
    pat += r"(?:$| )"
    return re.search(pat, q) is not None


def _field_list(rep: Report, limit: int = 14) -> str:
    """'what we do have', for honest not-found answers."""
    fields = sorted({f.field.replace("_", " ") for f in rep.facts})
    shown = ", ".join(fields[:limit])
    return shown + (f", +{len(fields) - limit} more" if len(fields) > limit else "")


def code_answer(rep: Report, question: str) -> Optional[str]:
    """Deterministic answer for the no-API-key path (and a sanity check for the LLM).

    Picks the canonical fields the question mentions and prints their facts with the
    same citations the LLM is required to use. Returns None when the question names
    nothing we know how to look up.
    """
    q = " " + normalise_header(re.sub(r"[^0-9A-Za-z]+", " ", str(question))) + " "
    asked_check = any(_phrase_hit(p, q) for p in CHECK_PHRASES)
    wanted = [fld for fld, phrases in FIELD_PHRASES.items()
              if any(_phrase_hit(p, q) for p in phrases)]
    # 'bore / inner diameter' also says 'diameter': the specific wording wins the order
    wanted.sort(key=lambda f: -max((len(p) for p in FIELD_PHRASES[f]
                                    if _phrase_hit(p, q)), default=0))
    if not wanted and not asked_check:
        return None
    expanded: list[str] = []
    for fld in wanted:
        alts = FIELD_TWINS.get(fld, ())
        order = alts + (fld,) if fld in TWIN_FIRST else (fld,) + alts
        for alt in order:
            if alt not in expanded and any(x.field == alt for x in rep.facts):
                expanded.append(alt)
    lines: list[str] = []
    missing: list[str] = []
    for fld in expanded or wanted:
        got = [x for x in rep.facts if x.field == fld]
        if not got:
            got = [x for x in rep.facts if x.field in FALLBACK_FIELDS.get(fld, ())]
        if not got:
            missing.append(fld.replace("_", " "))
            continue
        for f in got:
            lines.append(f"- {fld.replace('_', ' ')}: {f.display_value()} "
                         f"[extracted from {f.source_type}: {Path(f.source_file).name}, "
                         f"{f.location}; confidence {f.confidence}"
                         + (f"; {f.note}" if f.note else "") + "]")
    conflicts = [r for r in rep.rows if r.status == "mismatch"]
    verdict = ""
    if asked_check and rep.rows:
        # asked 'do the sources agree?': answer from the cross-check, not from the fields
        rel = [r for r in rep.rows
               if any(_phrase_hit(w, q) for w in re.findall(r"[a-z]+", normalise_header(r.label)))]
        verdict = ("When cross-checked: "
                   + "; ".join(f"{r.icon()} {r.label} - {r.detail}" for r in (rel or rep.rows)))
    if not lines:
        if verdict:
            return verdict
        have = _field_list(rep)
        return (f"I can't find that in the files. The extracted record holds no "
                f"{' / '.join(missing)} value for this part. What is available: {have}.")
    out = "\n".join(dict.fromkeys(lines))
    if verdict:
        out += "\n" + verdict
    elif conflicts:
        out += "\n" + "\n".join(
            f"CAUTION: the sources disagree about '{r.label}': {r.detail}" for r in conflicts)
    return out


SMALLTALK = {"hi", "hii", "hey", "hello", "yo", "hola", "namaste", "thanks", "thank you",
             "ok", "okay", "cool"}


def _is_smalltalk(question: str) -> bool:
    words = normalise_header(re.sub(r"[^0-9A-Za-z]+", " ", str(question))).split()
    return " ".join(words) in SMALLTALK


def _model_name(llm: object) -> str:
    """The model that actually answered, which may be a fallback."""
    return getattr(llm, "model_used", "") or llm.describe()


def _llm_reason(exc: Exception) -> str:
    """A short human reason; the provider's raw JSON never reaches the user."""
    text = str(exc).lower()
    if "429" in text or "rate limit" in text or "quota" in text or "tokens per" in text:
        return "its usage limit is reached"
    if "401" in text or "api key" in text or "unauthorized" in text:
        return "the API key was rejected"
    if "timeout" in text or "timed out" in text:
        return "it did not answer in time"
    return "it could not be reached"


def ask(rep: Report, question: str, *, llm: Optional[LLMClient] = None) -> Answer:
    """Answer one question from the fact sheet only, then verify its numbers."""
    if not rep.facts:
        return Answer(question, "I can't find that in the files. No facts could be extracted "
                      "for this part - see the warnings.", "code")
    if _is_smalltalk(question):
        # a greeting is not a question about the part: answer it here instead of spending a
        # model call that would have no fact to cite (and would fail when quota is out)
        sources = ", ".join(sorted(rep.by_source()))
        return Answer(question,
                      f"I'm ready with part {rep.part} - {len(rep.facts)} extracted facts from "
                      f"{sources}. Ask me about a size, material, tolerance, or whether the "
                      "files agree.", "local")
    direct = code_answer(rep, question)
    if llm is None or not llm.available:
        if direct is not None:
            return Answer(question, direct, "no-llm")
        have = _field_list(rep)
        return Answer(question,
                      "I can't find that in the files. (No language model is configured, so this "
                      "app answers only by exact field lookup in the extracted fact sheet; the "
                      f"fields it does hold for this part are: {have}.)", "no-llm")
    prompt = build_answer_prompt(rep.part, rep.facts, question, rep.rows)
    try:
        text = llm.chat(SYSTEM_PROMPT, prompt)
    except LLMError as exc:
        # the deterministic answer is still an answer, and it is honest about its source
        why, used = _llm_reason(exc), _model_name(llm)
        if direct is not None:
            return Answer(question, direct + f"\n\n_Language model unavailable: {why}. "
                          "The lines above are the exact lookup from the extracted fact sheet._",
                          "limited", model=used)
        have = _field_list(rep)
        return Answer(question,
                      f"The language model is unavailable right now ({why}), and this question "
                      "is not an exact field lookup, so I will not guess. The extracted fields "
                      f"I can answer from are: {have}.", "limited", model=used)
    ver = verify_answer(text, rep.facts)
    if not ver.ok and direct is not None:
        return Answer(question, direct + f"\n\n(model answer rejected: {ver.message})",
                      "code", model=_model_name(llm), verification=ver)
    return Answer(question, text, "llm", model=_model_name(llm), verification=ver)
