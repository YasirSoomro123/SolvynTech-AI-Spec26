"""Part discovery: given a part number, find the files that describe it.

Two independent signals are used, because neither is reliable alone:
  * filename / folder-name match   (e.g. 2280.igs, part-2280.iges, "2280 rev B.pdf")
  * content match                  (part number inside an Excel cell, PDF text or IGES text)

Candidates are scored and ranked; the caller gets the winner *and* the runners-up so the UI can
say "I picked 2280_revB.pdf over 2280_old.pdf". Nothing here knows the naming convention of our
sample data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

EXCEL_EXTS = {".xlsx", ".xls", ".xlsm", ".csv", ".txt"}
PDF_EXTS = {".pdf"}
IGES_EXTS = {".igs", ".iges", ".iges5"}
KIND_BY_EXT: dict[str, str] = {}
for _e in EXCEL_EXTS:
    KIND_BY_EXT[_e] = "Excel"
for _e in PDF_EXTS:
    KIND_BY_EXT[_e] = "PDF"
for _e in IGES_EXTS:
    KIND_BY_EXT[_e] = "IGES"

IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "docs", "build",
               "presentation"}


def norm_part(value: object) -> str:
    """Canonical form of a part number for comparison: 'PN-2280 rev B' -> '2280'.

    Integers, floats (2280.0), padded strings and numbers embedded in longer labels all reduce to
    the same key. Keeps letters, since unseen part numbers may be alphanumeric (AB-104-C).
    """
    if value is None:
        return ""
    s = str(value).strip().lower().replace("\u00a0", " ")
    if s.endswith(".0"):
        s = s[:-2]
    # Collapse separators so 2280-001 and 2280001 do not fight; keep alphanumerics.
    s = re.sub(r"[^0-9a-z]+", "", s)
    return s


def part_tokens(value: object) -> set[str]:
    """Every plausible key for a part number, so both exact and embedded matches are found."""
    raw = str(value or "").strip()
    out = {norm_part(raw)}
    out |= {t for t in re.split(r"[^0-9A-Za-z]+", raw) if t}
    # numeric core, e.g. '002280' -> '2280'
    digits = re.sub(r"\D", "", raw)
    if digits:
        out.add(digits.lstrip("0") or "0")
    out.discard("")
    return out


@dataclass
class Candidate:
    path: Path
    kind: str                 # Excel | PDF | IGES
    score: float
    reasons: list[str] = field(default_factory=list)

    def label(self) -> str:
        return f"{self.kind}: {self.path}"


@dataclass
class PartFiles:
    part: str
    chosen: dict[str, Candidate] = field(default_factory=dict)   # kind -> winner
    rejected: list[Candidate] = field(default_factory=list)      # other candidates, for transparency
    missing_kinds: list[str] = field(default_factory=list)

    def paths(self) -> dict[str, Path]:
        return {k: c.path for k, c in self.chosen.items()}


def _names_this_number(stem: str, token: str) -> bool:
    """Does the filename name this number, or only contain it inside a longer number?

    Digit runs are compared instead of substrings, so '2280revb' and '002280' qualify
    (a revision suffix and a zero-padded number are the same part) while '12280' and
    'v22801' do not - those are different parts that happen to share digits.
    """
    if not token.isdigit():
        return token in stem
    return any(run == token or run.lstrip("0") == token.lstrip("0")
               for run in re.findall(r"\d+", stem))


def _score_name(path: Path, folder: Path, tokens: set[str]) -> tuple[float, float, list[str]]:
    """(total, identity, reasons). `identity` is the part of the score that comes from
    the file actually naming this part; the rest is a tie-breaker. A file with no
    identity points is not a candidate for this part at all."""
    reasons: list[str] = []
    identity = 0.0
    stem = path.stem.lower()
    parent = path.parent.name.lower()
    for tok in tokens:
        t = tok.lower()
        if not t:
            continue
        if stem == t:
            identity += 60
            reasons.append(f"filename exactly '{t}'")
        elif re.search(rf"(^|[^0-9a-z]){t}([^0-9a-z]|$)", stem):
            identity += 45
            reasons.append(f"'{t}' as a word in the filename")
        elif _names_this_number(stem, t):
            # '2280revb' and '002280' name the part; '12280' and 'v22801' name another one.
            identity += 20
            reasons.append(f"'{t}' as a whole number in the filename")
        if parent == t:
            identity += 30
            reasons.append(f"folder named '{t}'")
        elif t in parent and not t.isdigit():
            identity += 12
            reasons.append(f"'{t}' in folder name")
    # Prefer files that look current, but never let this outrank an identity match.
    score = identity
    name = path.name.lower()
    if re.search(r"(old|obsolete|draft|bak|copy|~|\bdo not\b)", name):
        score -= 25
        reasons.append("name says old/draft")
    if re.search(r"(rev[- _]?[a-z0-9]+|final|latest|v[0-9]+)", name):
        score += 3
        reasons.append("looks like a revisioned/final file")
    return score, identity, reasons


def _read_snippet(path: Path, limit: int = 400_000) -> tuple[str, list[str]]:
    """Cheap (raw text, individual cell values) for content matching.

    Never raises: no text simply means no hint.  The two channels are scored
    differently on purpose - a spreadsheet cell whose whole value is the part number
    identifies the file, while a part number inside a sentence does not.

    A .xlsx is a zip, so raw bytes carry nothing; the stored XML holds every header,
    every cell string and every number, which is what a part number can live in.
    """
    suffix = path.suffix.lower()
    try:
        if suffix in {".xlsx", ".xlsm"}:
            import zipfile
            out: list[str] = []
            with zipfile.ZipFile(path) as zf:
                for name in zf.namelist():
                    if not (name.startswith("xl/") and name.endswith(".xml")):
                        continue
                    xml = zf.read(name)[:limit].decode("utf-8", "replace")
                    # element text and stored cell values only: attribute ids would
                    # otherwise "find" part numbers that are nowhere in the data.
                    # Long strings are remarks/prose, which mention OTHER parts -
                    # a part number found inside a sentence is not evidence of identity.
                    out.extend(v for v in re.findall(r"<(?:t\b[^>]*|v)>([^<>]+)</(?:t|v)>", xml)
                               if len(v) <= 60)
            return " ".join(out), out
        if suffix == ".xls":
            try:
                import xlrd
                book = xlrd.open_workbook(str(path), on_demand=True)
                cells: list[str] = []
                for sheet in book.get_sheet_names()[:8]:
                    ws = book.sheet_by_name(sheet)
                    for r in range(min(ws.nrows, 300)):
                        cells.extend(str(ws.cell_value(r, c)) for c in range(ws.ncols))
                return " ".join(cells), [c for c in cells if len(c) <= 60]
            except Exception:
                pass                      # fall through to the raw-bytes guess
        data = path.read_bytes()[:limit]
    except Exception:
        return "", []
    if suffix in {".xlsx", ".xls", ".xlsm"}:
        # an old/odd workbook we could not unzip: printable runs still give a hint
        return re.sub(rb"[^\x20-\x7e]+", b" ", data).decode("latin-1", "replace"), []
    return data.decode("latin-1", "replace"), []


def _score_content(path: Path, tokens: set[str], text: str,
                   cells: Optional[list[str]] = None) -> tuple[float, list[str]]:
    """Points for numbers found *inside* a file, and why.

    A workbook only counts when a cell's whole value is the part number: 'Remark: see
    4412' in a sentence is prose about another part, not this part's record.
    """
    reasons: list[str] = []
    score = 0.0
    low = text.lower()
    if cells:
        keys = {norm_part(c) for c in cells}
        hit = [t for t in tokens if norm_part(t) in keys]
        if hit:
            score += 40
            reasons.append(f"a cell holds exactly '{hit[0]}'")
        return score, reasons
    for tok in tokens:
        t = tok.lower()
        if len(t) < 3 and not t.isdigit():
            continue
        hits = len(re.findall(rf"(?<![0-9a-z]){re.escape(t)}(?![0-9a-z])", low))
        if hits:
            # cap: a file that repeats the number 500 times is not 500x more certain
            score += min(hits, 5) * 6
            reasons.append(f"'{t}' appears {hits}x in content")
    return score, reasons


def iter_files(root: Path, kinds: Iterable[str] | None = None) -> Iterable[Path]:
    wanted = None
    if kinds:
        wanted = {e for e, k in KIND_BY_EXT.items() if k in set(kinds)}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORE_DIRS or part.startswith(".")
               for part in path.relative_to(root).parts[:-1]):
            continue
        if path.suffix.lower() not in KIND_BY_EXT:
            continue
        if wanted and path.suffix.lower() not in wanted:
            continue
        if path.name.startswith(("~$", ".")):
            continue
        yield path


def locate(part: str, root: Path, want: Iterable[str] = ("Excel", "PDF", "IGES")) -> PartFiles:
    """Find the best file of each kind for `part` under `root`."""
    want = list(want)
    tokens = part_tokens(part) | {norm_part(part)}
    # a one or two digit query is not a search term, it is noise: '0' appears as a lone
    # zero in almost every dimension table and tolerance cell, so a short numeric query
    # has to be *named* by a file to count. unknown short numbers then answer "not found"
    # instead of quietly pairing one part's workbook with another part's drawing.
    key = norm_part(part)
    core = key.lstrip("0")
    exact_named_only = key.isdigit() and len(core) < 3
    result = PartFiles(part=part)
    scored: dict[str, list[Candidate]] = {k: [] for k in want}

    for path in iter_files(root):
        kind = KIND_BY_EXT.get(path.suffix.lower())
        if kind not in scored:
            continue
        name_score, identity, name_reasons = _score_name(path, root, tokens)
        content_score: float = 0.0
        content_reasons: list[str] = []
        # Content check only matters when the name did not already identify the file,
        # and only for files we can cheaply read.
        if identity < 45 and not exact_named_only:
            text, cells = _read_snippet(path)
            content_score, content_reasons = _score_content(
                path, tokens, text,
                cells if path.suffix.lower() in EXCEL_EXTS else None)
        if identity + content_score <= 0:
            continue        # neither the name nor the content claims this part number
        scored[kind].append(Candidate(path=path, kind=kind,
                                      score=round(name_score + content_score, 1),
                                      reasons=name_reasons + content_reasons))

    for kind in want:
        cands = sorted(scored[kind], key=lambda c: (-c.score, str(c.path)))
        if not cands:
            result.missing_kinds.append(kind)
            continue
        result.chosen[kind] = cands[0]
        result.rejected.extend(cands[1:6])
    return result


def discover_parts(root: Path, *, read_records: bool = True) -> list[str]:
    """Stretch goal: every part number this folder appears to describe, unasked.

    Two signals, both generic: identifier-looking number runs inside file and folder
    names, and - when the Excel reader is available - the values of whatever column
    maps to 'part number'. Numbers are reported without leading zeros (002280 = 2280).
    """
    found: set[str] = set()
    for path in iter_files(root):
        for token in re.split(r"[^0-9A-Za-z]+", f"{path.stem} {path.parent.name}"):
            for run in re.findall(r"\d{3,}", token):
                found.add(run.lstrip("0") or "0")
    if read_records:
        try:
            from .excel_reader import read_spreadsheet
        except Exception:                      # keep discovery working without openpyxl
            read_records = False
    if read_records:
        for path in iter_files(root, ["Excel"]):
            try:
                res = read_spreadsheet(path)
            except Exception:
                continue
            for f in res.facts:
                if f.field == "part_number":
                    key = norm_part(f.value)
                    if re.fullmatch(r"\d{2,}[0-9a-z]{0,12}", key):
                        found.add(key.lstrip("0") or key)
    return sorted(x for x in found if x and x != "0")
