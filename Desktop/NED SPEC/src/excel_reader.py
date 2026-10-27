"""Excel manufacturing record reader (.xlsx / .xls / .csv).

Design rules, all of them driven by "the judged files are not our files":
  * the header row is DETECTED, never assumed to be row 1;
  * column names are mapped to canonical fields by fuzzy synonym matching, never hard-coded;
  * columns that map to nothing are still emitted as raw key/value facts;
  * every sheet is inspected, and non-tabular sheets (prose/notes) are skipped with a warning;
  * merged cells are filled across their span; blank rows and blank cells are tolerated;
  * units found in the header text are attached to the value and converted to mm in code.

An optional `header_mapper` callback (the LLM one-time header mapping) may add extra
header->field pairs; it is only allowed to rename, never to invent values.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Callable, Optional

from .fact import Fact, SourceResult
from .schema import CANONICAL_FIELDS, KIND_UNITS, header_unit, match_header, normalise_header
from .units import parse_number, to_mm

HeaderMapper = Callable[[list[str], list[list[str]]], dict[str, str]]

# A sheet is "tabular" only if we can find a row of mostly-distinct short text cells.
MIN_HEADER_CELLS = 2
PROSE_RATIO = 0.6      # a row whose single cell is very long is prose, not a header


def _load_rows(path: Path) -> dict[str, list[list[object]]]:
    """Return {sheet_name: rows}. For CSV, one pseudo-sheet. Never raises on odd content."""
    suffix = path.suffix.lower()
    if suffix == ".csv" or suffix == ".txt":
        return {path.stem: _load_csv(path)}
    if suffix in {".xlsx", ".xlsm"}:
        return _load_openpyxl(path)
    if suffix == ".xls":
        return _load_xls(path)
    raise ValueError(f"unsupported spreadsheet type {suffix}")


def _load_csv(path: Path) -> list[list[object]]:
    raw = path.read_bytes().decode("utf-8-sig", errors="replace")
    delim = ","
    if path.suffix.lower() == ".txt":
        counts = {d: raw.count(d) for d in ",;\t|"}
        delim = max(counts, key=counts.get) or ","
    sample = "\n".join(raw.splitlines()[:20])
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        pass
    reader = csv.reader(io.StringIO(raw), delimiter=delim)
    return [[_clean(cell) for cell in row] for row in reader]


def _load_openpyxl(path: Path) -> dict[str, list[list[object]]]:
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=False)
    out: dict[str, list[list[object]]] = {}
    for ws in wb.worksheets:
        grid = [[c.value for c in row] for row in ws.iter_rows()]
        # merged cells: openpyxl reports the value only on the top-left cell; spread it so a
        # merged header ("Diameters" over two columns) or merged title does not create blanks.
        for rng in list(ws.merged_cells.ranges):
            top = grid[rng.min_row - 1][rng.min_col - 1] if rng.min_row - 1 < len(grid) else None
            for r in range(rng.min_row - 1, min(rng.max_row, len(grid))):
                row = grid[r]
                for c in range(rng.min_col - 1, min(rng.max_col, len(row))):
                    if row[c] in (None, ""):
                        row[c] = top
        out[ws.title] = grid
    return out


def _load_xls(path: Path) -> dict[str, list[list[object]]]:
    """Legacy .xls needs xlrd; if absent we degrade with a clear warning instead of crashing."""
    try:
        import xlrd  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(".xls files need the 'xlrd' package (pip install xlrd)") from exc
    book = xlrd.open_workbook(str(path))
    out = {}
    for sheet in book.sheets():
        out[sheet.name] = [[sheet.cell_value(r, c) for c in range(sheet.ncols)]
                           for r in range(sheet.nrows)]
    return out


def _clean(cell: object) -> object:
    if isinstance(cell, str):
        cell = cell.strip()
        return cell if cell else None
    return cell


def _find_header_row(rows: list[list[object]]) -> tuple[int, list[str]]:
    """Pick the row that is the header, and normalise it. May be row 0, 2, 5...

    Heuristic: the row with the most non-empty, distinct, *text* cells, weighted toward rows
    near the top; a row of numbers is data, a row of long sentences is prose.
    """
    best_idx, best_score, best_labels = 0, -1.0, []
    for idx, row in enumerate(rows[:40]):
        cells = [c for c in row if c not in (None, "")]
        if len(cells) < MIN_HEADER_CELLS:
            continue
        texts = [str(c) for c in cells]
        if any(len(t) > 90 for t in texts):        # prose/notes row
            continue
        n_text = sum(1 for t in texts if parse_number(t) is None)
        distinct = len({normalise_header(t) for t in texts})
        if distinct == 1:
            continue
        # header rows are mostly non-numeric labels with few duplicates
        score = (0.6 * (n_text / len(texts)) + 0.4 * (distinct / len(texts))) * min(len(cells), 12)
        score *= 1.0 if idx == 0 else (0.92 if idx <= 5 else 0.8)
        if score > best_score:
            labels = [str(c) if c not in (None, "") else f"column_{i+1}"
                      for i, c in enumerate(row)]
            best_idx, best_score, best_labels = idx, score, labels
    return best_idx, best_labels


def _looks_like_parts_column(values: list[object]) -> bool:
    present = [v for v in values if v not in (None, "")]
    if not present:
        return False
    return sum(1 for v in present if parse_number(v) is None) < PROSE_RATIO * len(present)


def read_spreadsheet(path: Path | str, header_mapper: Optional[HeaderMapper] = None) -> SourceResult:
    """Parse a whole workbook into facts. Facts are tagged with the part number they belong to
    in `Fact.note` so a caller can filter; every value also keeps its cell address."""
    path = Path(path)
    res = SourceResult(source_type="Excel", file=str(path))
    try:
        sheets = _load_rows(path)
    except Exception as exc:                       # corrupt file, wrong extension, missing xlrd
        res.ok = False
        res.warn(f"could not open workbook: {exc}")
        return res

    total_tables = 0
    for sheet_name, rows in sheets.items():
        rows = [r for r in rows if any(c not in (None, "") for c in r)]
        if not rows:
            res.warn(f"sheet '{sheet_name}' is empty")
            continue
        header_idx, labels = _find_header_row(rows)
        if not labels:
            res.warn(f"sheet '{sheet_name}' has no detectable header row - treated as prose, skipped")
            continue
        data_rows = rows[header_idx + 1:]
        if not data_rows:
            res.warn(f"sheet '{sheet_name}' has a header but no data rows")
            continue

        mapped = _map_columns(labels, data_rows, path, res, header_mapper)
        part_col = next((i for i, m in enumerate(mapped) if m == "part_number"), None)
        if part_col is None:
            # No key column: still emit the facts, but warn loudly (an LLM answer over them is
            # only trustworthy if the caller pointed us at a one-part file).
            res.warn(f"sheet '{sheet_name}': no column could be identified as the part number; "
                     "all rows were read")
        total_tables += 1
        for r_off, row in enumerate(data_rows):
            row_no = header_idx + 2 + r_off
            blanks = 0
            row_part = None
            if part_col is not None and part_col < len(row):
                row_part = row[part_col]
            if all(c in (None, "") for c in row):
                continue
            for col_no, (label, field) in enumerate(zip(labels, mapped)):
                if col_no >= len(row):
                    break
                value = row[col_no]
                if value in (None, ""):
                    blanks += 1
                    continue
                cell = f"{_col_letter(col_no)}{row_no}"
                location = f"'{sheet_name}'!{cell}" if "!" in f"{sheet_name}!" else f"{sheet_name}!{cell}"
                for fact in _facts_from_cell(field, label, value, location, path, res, sheet_name):
                    if row_part is not None:
                        fact.note = (fact.note + " | " if fact.note else "") + f"part={_part_key(row_part)}"
                    res.facts.append(fact)
            if blanks == len(labels):
                res.warn(f"sheet '{sheet_name}' row {row_no} is entirely blank")

    res.detail = f"{len(sheets)} sheet(s), {total_tables} table(s), {len(res.facts)} fact(s)"
    return res


def _part_key(value: object) -> str:
    from .part_locator import norm_part
    return norm_part(value)


def _map_columns(labels: list[str], data_rows: list[list[object]], path: Path,
                 res: SourceResult, header_mapper: Optional[HeaderMapper]) -> list[Optional[str]]:
    """Canonical field for each column: fuzzy match first, then optional LLM assist."""
    mapped: list[Optional[str]] = []
    low_conf: list[str] = []
    for label in labels:
        field, score = match_header(label)
        if field is not None and score >= 0.7:
            mapped.append(field)
        elif field is not None:
            mapped.append(field)
            low_conf.append(str(label))
        else:
            mapped.append(None)
    if header_mapper is not None:
        try:
            extra = header_mapper([l for l in labels], [[str(c) if c is not None else ""
                                                        for c in row[:6]] for row in data_rows[:3]])
            for i, label in enumerate(labels):
                if mapped[i] is None and str(label) in extra:
                    mapped[i] = extra[str(label)]
                    res.warn(f"LLM header mapping: '{label}' -> {extra[str(label)]}")
        except Exception as exc:
            res.warn(f"LLM header mapping unavailable ({exc}); fuzzy matching only")
    if low_conf:
        res.warn("low-confidence column matches: " + ", ".join(low_conf[:8]))
    return mapped


def _facts_from_cell(field: Optional[str], label: object, value: object, location: str,
                     path: Path, res: SourceResult, sheet_name: str) -> list[Fact]:
    """One cell -> one or more Facts (a delimited list becomes several)."""
    raw_label = str(label).strip()
    unit_in_header = header_unit(raw_label)
    kind = CANONICAL_FIELDS.get(field or "", {}).get("kind", "text")

    # Unmapped columns are preserved verbatim as raw facts - losing data is not an option.
    if field is None:
        field = f"raw:{raw_label}" if raw_label else "raw:unnamed_column"

    text = str(value).strip() if value is not None else ""
    numeric = parse_number(value)

    facts: list[Fact] = []
    if kind == "length":
        if numeric is None:
            facts.append(Fact(field, text, None, "Excel", str(path), location,
                              confidence="code-high", note="header says length but cell is text"))
        else:
            unit = unit_in_header or _unit_from_text(text) or "mm"
            mm = to_mm(numeric, unit)
            if mm is None:
                facts.append(Fact(field, numeric, unit, "Excel", str(path), location,
                                  confidence="code-low", note=f"unknown unit '{unit}', not converted"))
            else:
                facts.append(Fact(field, mm, "mm", "Excel", str(path), location,
                                  confidence="code-high",
                                  note=f"read '{text}' as {numeric} {unit} -> {mm} mm"))
    elif kind in ("count", "money", "weight"):
        if numeric is None:
            facts.append(Fact(field, text, unit_in_header, "Excel", str(path), location))
        else:
            facts.append(Fact(field, numeric, unit_in_header, "Excel", str(path), location))
    elif kind == "time":
        if numeric is None:
            facts.append(Fact(field, text, None, "Excel", str(path), location))
        else:
            unit = (unit_in_header or "min").lower()
            if unit.startswith("sec"):
                facts.append(Fact(field, round(numeric / 60.0, 4), "min", "Excel", str(path), location,
                                  note=f"converted {numeric} s -> min"))
            elif unit.startswith("h"):
                facts.append(Fact(field, round(numeric * 60.0, 2), "min", "Excel", str(path), location,
                                  note=f"converted {numeric} h -> min"))
            else:
                facts.append(Fact(field, numeric, unit_in_header or "min", "Excel", str(path), location))
    elif kind == "finish":
        if numeric is None:
            facts.append(Fact(field, text, unit_in_header, "Excel", str(path), location))
        else:
            facts.append(Fact(field, numeric, unit_in_header or "um", "Excel", str(path), location,
                              note="Ra value"))
    elif kind == "list":
        parts = [p.strip() for p in re.split(r"[;,\n/|]+", text) if p.strip()]
        if len(parts) > 1:
            facts.append(Fact(field, parts, None, "Excel", str(path), location,
                              note=f"split from '{text}'"))
        else:
            facts.append(Fact(field, text, None, "Excel", str(path), location))
    else:  # text / unknown
        if numeric is not None and field.endswith(("number", "rev", "revision")) is False and \
                _looks_numeric_only(text) and len(text) <= 20 and not raw_label.lower().startswith("part"):
            facts.append(Fact(field, numeric, unit_in_header, "Excel", str(path), location))
        else:
            facts.append(Fact(field, text, unit_in_header, "Excel", str(path), location))

    # Keep the human column name so answers can quote it.
    for f in facts:
        if not f.note:
            f.note = f"column '{raw_label}'"
        else:
            f.note += f" | column '{raw_label}'"
    return facts


_NUMERIC_ONLY = re.compile(r"^[+-]?[\d.,\s]+$")


def _looks_numeric_only(text: str) -> bool:
    return bool(_NUMERIC_ONLY.match(text or ""))


def _unit_from_text(text: str) -> Optional[str]:
    m = re.search(r"\b(mm|cm|inch|in|um|\u00b5m|microns?|m)\b", (text or "").lower())
    if not m:
        return None
    from .units import normalise_units_token
    return normalise_units_token(m.group(1))


def _col_letter(idx: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def rows_for_part(res: SourceResult, part: str) -> list[Fact]:
    """Facts belonging to one part number, using the part tag added during reading."""
    from .part_locator import norm_part, part_tokens
    tokens = part_tokens(part)
    out = []
    for f in res.facts:
        note = f.note or ""
        if "part=" in note:
            key = note.rsplit("part=", 1)[1].strip()
            if key in tokens:
                out.append(f)
        else:
            out.append(f)          # untagged rows (no part column found) stay available
    return out
