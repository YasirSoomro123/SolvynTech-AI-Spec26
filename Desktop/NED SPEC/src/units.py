"""Unit handling and number parsing.

All numeric facts are converted to a canonical unit (millimetres for length) IN CODE,
never by the LLM. Nothing in this file is specific to our two reference parts.
"""

from __future__ import annotations

import re
from typing import Optional

# Length units -> millimetres. Keys lower-case, matched after normalising.
LENGTH_TO_MM = {
    "mm": 1.0, "millimeter": 1.0, "millimeters": 1.0, "millimetre": 1.0,
    "millimetres": 1.0, "mms": 1.0,
    "cm": 10.0, "centimeter": 10.0, "centimeters": 10.0,
    "m": 1000.0, "meter": 1000.0, "meters": 1000.0, "metre": 1000.0,
    "um": 0.001, "micron": 0.001, "microns": 0.001,
    "in": 25.4, "inch": 25.4, "inches": 25.4, '"': 25.4,
    "ft": 304.8, "feet": 304.8, "foot": 304.8,
    "degrees": None,  # placeholder to keep lookups honest
}

# IGES global section may spell units with trailing/leading spaces or as an integer code.
IGES_UNIT_CODES = {1: "in", 2: "mm", 3: "ft", 4: "m", 5: "cm", 6: "microin", 7: "decimeter",
                   8: "decameter", 9: "hectometer", 10: "km", 11: "megameter"}

TEXT_FIELDS = {"part_number", "name", "material", "machine", "revision", "supplier_ref",
               "drawing_no", "operations", "remarks", "finish", "general_tolerance"}


def normalise_units_token(raw: str) -> Optional[str]:
    """' (mm)' / '[mm]' / ' Ra um' -> 'mm' / 'um'. Returns None if unknown."""
    if not raw:
        return None
    tok = re.sub(r"[\[\]\(\)]", "", raw).strip().lower()
    tok = tok.replace("µ", "u").replace("μ", "u")
    tok = re.sub(r"\s+", " ", tok)
    if tok in LENGTH_TO_MM and LENGTH_TO_MM[tok] is not None:
        return tok
    # common decorations: "mm" inside "dia mm", "ra um", "0.001mm"
    for word in reversed(re.split(r"[\s/,]+", tok)):
        if word in LENGTH_TO_MM and LENGTH_TO_MM[word] is not None:
            return word
    if "um" in tok or "micron" in tok:
        return "um"
    return None


def to_mm(value: float, unit: Optional[str]) -> Optional[float]:
    """Convert a length to mm. Returns None if the unit is unknown / not a length."""
    if unit is None:
        return None
    factor = LENGTH_TO_MM.get(unit.lower().strip())
    if factor is None:
        return None
    return round(value * factor, 6)


def unit_factor(unit: Optional[str]) -> Optional[float]:
    if unit is None:
        return None
    return LENGTH_TO_MM.get(unit.lower().strip())


# '+/-0.1' and '±0.1' state a spread, not a negative value. One definition, used by
# parse_number and by the answer verifier, so the two can never disagree. It must NOT
# swallow the space after the sign: in prose '50±0.1' has to stay two numbers.
PLUSMINUS_RE = re.compile(r"[+-]\s*/\s*[+-]|[±]")


# One pattern for 'what counts as a number here', shared by parse_number and
# extract_numbers so the two can never disagree about the same drawing callout.
NUMBER_RE = re.compile(r"""
    (?P<num>
        [+-]?\d+\s+\d{1,3}/\d{1,3}                                    # 3 1/2  imperial mixed
      | [+-]?\d{1,3}/\d{1,3}                                          # 1/2
      | [+-]?(?:\d[\d,.]*\d|\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?         # 1,234.5 / 4,3 / 2.5E-3
    )
""", re.VERBOSE)
_MIXED_RE = re.compile(r"^([+-]?\d+)\s+(\d{1,3})/(\d{1,3})$")
_FRAC_RE = re.compile(r"^([+-]?)(\d{1,3})/(\d{1,3})$")


def parse_number(token: str) -> Optional[float]:
    """Parse one numeric token tolerantly.

    Handles: '8', '4.3', '.75', '+0', '-0.05', '1,000', '1,234.5', '4,3' (European decimal),
    '3 1/2' (imperial fraction), '2.5E-3', '1.0e-06'. Returns None for non-numeric input,
    including codes such as 'A1' or 'M5'. Never raises.
    """
    if token is None:
        return None
    if isinstance(token, (int, float)):
        return float(token)
    s = str(token).strip().replace("\u00a0", " ")
    if not s:
        return None
    s = s.replace("−", "-").replace("–", "-")  # unicode minus/en-dash
    s = PLUSMINUS_RE.sub(" ", s)                # '50±0.1' is a nominal value plus a spread
    if re.match(r"[A-Za-z]", s):
        return None                     # 'A1', 'M5', 'ISO 2768' are codes, not quantities
    # Grouping spaces: "1 234.5"
    s = re.sub(r"(?<=\d)[  ](?=\d{3}\b)", "", s)
    m = NUMBER_RE.search(s)
    if not m:
        return None
    raw = m.group("num")
    mixed = _MIXED_RE.match(raw)
    if mixed:
        whole, num, den = (float(g) for g in mixed.groups())
        if not den:
            return None
        # '-3 1/2' is -3.5: the sign belongs to the whole number and the fraction is added to it
        return round(whole + num / den if whole >= 0 else whole - num / den, 6)
    frac = _FRAC_RE.match(raw)
    if frac:
        sign, num, den = frac.group(1), float(frac.group(2)), float(frac.group(3))
        return round(-num / den if sign == "-" else num / den, 6) if den else None
    if "e" in raw.lower():
        raw = raw.replace(",", "")
        try:
            return float(raw)
        except ValueError:
            return None
    # Decide what the separators mean. The right-most one is the decimal separator and the
    # others are thousands grouping, which covers both '1,234.5' and the European '1.234,5'.
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.find("."):       # '1.234,5' -> dots group, comma is decimal
            raw = raw.replace(".", "").replace(",", ".")
        else:                                    # '1,234.5' -> commas group
            raw = raw.replace(",", "")
    elif "," in raw:
        parts = raw.split(",")
        if len(parts) > 2 and all(len(p) == 3 for p in parts[1:]):
            raw = raw.replace(",", "")                     # 1,234,567
        elif len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) > 3:
            raw = raw.replace(",", "")                     # 1234,567 -> grouping is the safer read
        else:
            raw = raw.replace(",", ".")                    # 4,3 -> 4.3 ; 0,05 -> 0.05
    try:
        return float(raw)
    except ValueError:
        return None


def extract_numbers(text: str) -> list[float]:
    """All numbers in a string, left to right, using the same reading as parse_number."""
    out: list[float] = []
    for m in NUMBER_RE.finditer(text or ""):
        v = parse_number(m.group("num"))
        if v is not None:
            out.append(v)
    return out


def fmt(value: float) -> str:
    """Compact, deterministic number formatting for prompts and tables."""
    if isinstance(value, float) and value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return f"{value:g}"
