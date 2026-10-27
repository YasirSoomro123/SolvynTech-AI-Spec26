"""Canonical field names and the vocabulary used to recognise them.

Nothing here is specific to our reference spreadsheet: the synonym lists cover the ways a
manufacturing record might label a quantity (P/N, Partno, Item, Reference...). Any column that
matches nothing is still kept verbatim as a raw key/value fact, so no data is lost.
"""

from __future__ import annotations

import re
from typing import Optional

# field -> (synonyms, expected unit in header, value kind)
CANONICAL_FIELDS: dict[str, dict] = {
    "part_number":      {"syn": ["part number", "partno", "part no", "pn", "p/n", "part", "item number",
                                "item no", "item", "component number", "comp no", "ref", "reference",
                                "article", "material number", "mat no", "number", "id", "no",
                                "no de piece", "n de piece", "numero de piece", "piece number"],
                         "kind": "text", "key": True},
    "part_name":        {"syn": ["part name", "description", "desc", "title", "name", "component",
                                "designation", "nomenclature"], "kind": "text"},
    "drawing_no":       {"syn": ["drawing no", "drawing number", "dwg no", "dwg", "drawing",
                                "print no", "shop drawing"], "kind": "text"},
    "material":         {"syn": ["material", "matl", "mat", "material grade", "alloy", "substance",
                                "raw material", "body material", "matiere", "materiau"],
                         "kind": "text"},
    "material_standard": {"syn": ["material standard", "specification", "spec", "grade", "standard",
                                  "aisi", "din", "norm"], "kind": "text"},
    "outer_diameter":   {"syn": ["outer diameter", "od", "dia outer", "diameter outer", "d1",
                                "outside dia", "od mm", "big dia", "dia out", "diameter out",
                                "diam ext", "exterior diameter", "diam exterieur",
                                "diametre exterieur", "diameter exterior"], "kind": "length"},
    "inner_diameter":   {"syn": ["inner diameter", "id", "bore", "bore diameter", "d2",
                                "inside dia", "hole diameter", "pilot hole", "dia in",
                                "diameter in", "diam int", "interior diameter", "diam interieur",
                                "diametre interieur", "diameter interior"], "kind": "length"},
    "diameter":         {"syn": ["diameter", "dia", "size dia"], "kind": "length"},
    "length":           {"syn": ["length", "overall length", "oal", "l", "len", "height", "depth",
                                "thickness", "long", "longueur"], "kind": "length"},
    "width":            {"syn": ["width", "across flats", "af", "w"], "kind": "length"},
    "dimension":        {"syn": ["dimension", "size", "main dimension", "critical dimension"],
                         "kind": "length"},
    "quantity":         {"syn": ["quantity", "qty", "qte", "quantite", "no of pieces",
                                "number of pieces", "pieces",
                                "batch size", "lot size", "order qty"], "kind": "count"},
    "stock_size":       {"syn": ["stock size", "raw stock", "blank size", "bar size", "material size",
                                "stock", "blank"], "kind": "text"},
    "machine":          {"syn": ["machine", "machine tool", "cnc", "equipment", "workcenter",
                                "cell", "process route", "machining center", "mach"],
                         "kind": "text"},
    "operations":       {"syn": ["operations", "op list", "operation list", "process", "routing",
                                "routine", "steps", "sequence", "jobs", "work content",
                                "machining steps"], "kind": "list"},
    "cycle_time":       {"syn": ["cycle time", "run time", "machining time", "time per part",
                                "ct", "cycle", "time", "setup time", "production time", "takt"],
                         "kind": "time"},
    "general_tolerance": {"syn": ["general tolerance", "tolerance", "tol", "iso 2768", "tol class",
                                  "general tolerances", "gt", "fit"], "kind": "text"},
    "surface_finish":   {"syn": ["surface finish", "finish", "ra", "surface roughness", "roughness",
                                "texture", "n6", "micro finish", "fin"], "kind": "finish"},
    "supplier_ref":     {"syn": ["supplier ref", "vendor code", "catalogue", "catalog", "order code",
                                "supplier", "vendor", "manufacturer part", "mpn", "commercial ref"],
                         "kind": "text"},
    "revision":         {"syn": ["revision", "rev", "version", "issue", "edicion", "level"],
                         "kind": "text"},
    "cost":             {"syn": ["cost", "price", "unit cost", "rate", "cost per piece", "value",
                                "amount", "cout", "euro", "usd"], "kind": "money"},
    "weight":           {"syn": ["weight", "mass"], "kind": "weight"},
    "heat_treatment":   {"syn": ["heat treatment", "hardening", "ht", "coating", "plating",
                                "anodizing", "treatment", "traitement", "surface treatment"],
                         "kind": "text"},
    "lead_time":        {"syn": ["lead time", "delivery", "days"], "kind": "time"},
    "remarks":          {"syn": ["remarks", "notes", "comment", "note", "observations"],
                         "kind": "text"},
}

# Which unit is expected per kind, used to sanity-check a header's own unit text.
KIND_UNITS = {"length": "mm", "time": "min", "count": None, "money": None,
              "finish": "um", "weight": "g"}

# Column-name noise we strip before matching.
_STOP = re.compile(r"[^a-z0-9]+")


def normalise_header(raw: object) -> str:
    s = str(raw or "").lower()
    s = s.replace("µ", "u").replace("é", "e").replace("è", "e").replace("ü", "u").replace("ö", "o")
    return _STOP.sub(" ", s).strip()


# Spelled-out units seen in headings, canonicalised so the reader can convert the value:
# without this 'Cycle time (s)' would be reported as 90 minutes.
_WORD_UNIT = {"min": "min", "mins": "min", "minute": "min", "minutes": "min",
              "sec": "sec", "secs": "sec", "second": "sec", "seconds": "sec", "s": "sec",
              "h": "h", "hr": "h", "hrs": "h", "hour": "h", "hours": "h",
              "kg": "kg", "g": "g", "pcs": "pcs", "pc": "pcs", "ea": "pcs"}


def header_unit(raw: object) -> Optional[str]:
    """Pull a unit out of header text: 'Outer Diameter (mm)' -> 'mm', 'Temps (min)' -> 'min'."""
    from .units import normalise_units_token
    s = str(raw or "")
    for group in re.findall(r"[\[\(\{]([^\]\)\}]{}|)[\]\)\}]", s) + re.findall(r"[\[\(\{]([^()\[\]]+)[\]\)\}]", s):
        u = normalise_units_token(group)
        if u:
            return u
        for word in reversed(re.split(r"[\s/,]+", group.lower())):
            if word in _WORD_UNIT:
                return _WORD_UNIT[word]
    # NOTE: '_' is deliberately NOT a separator here - 'DIA_IN' is diameter-inner, and
    # reading its tail as 'inch' silently rescales the bore by 25.4.  A bare 'in' is not
    # matched at all either: in a heading it is almost always the word 'in', not inches.
    m = re.search(r"(?:^|[\s/,(-])(mm|cm|inch|um|min|sec|kg|g)\b", s.lower())
    if m:
        return m.group(1)
    # 'id_mm' / 'cycle_min': the unit is glued to the name with an underscore, which
    # normalise_header turns into a space, so the unit is looked for in that form too.
    m = re.search(r"\b(mm|cm|um|inch|min|sec|kg|pcs)\b", normalise_header(s))
    return m.group(1) if m else None


# A unit found in a heading tells us what KIND of quantity the column holds.
UNIT_KIND = {"mm": "length", "cm": "length", "m": "length", "inch": "length", "ft": "length",
             "um": "finish", "min": "time", "sec": "time", "h": "time", "kg": "weight",
             "g": "weight", "pcs": "count", "eur": "money", "usd": "money"}

# Headings too short or too generic to trust anything but an exact match.
EXACT_ONLY = {"id", "no", "number", "ref", "reference", "item", "part", "size", "spec",
              "grade", "norm", "t", "l", "w", "ct", "ht", "af", "value", "dq", "key"}

# A heading that names a person or a company describes that party, not the part, so it must
# not claim an identity field: 'operator name' is not the part's name, it stays a raw column.
OWNER_WORDS = {"operator", "customer", "client", "supplier", "vendor", "company", "user",
               "author", "preparer", "checker", "reviewer", "approver", "buyer", "purchaser",
               "contact", "sales", "shop", "workstation", "file", "folder", "page", "print"}
OWNER_BLOCKS = {"part_number", "part_name", "drawing_no", "revision"}


def _header_variants(raw: object) -> tuple[str, list[str], Optional[str]]:
    """(normalised heading, heading with/without its unit token, kind that unit implies)."""
    norm = normalise_header(raw)
    unit = header_unit(raw)
    variants = [norm]
    if unit:
        bare = " ".join(t for t in norm.split() if t != unit).strip()
        if bare and bare != norm:
            variants.append(bare)
    return norm, variants, UNIT_KIND.get(unit)


def match_header(raw: object) -> tuple[Optional[str], float]:
    """Fuzzy-map a header to a canonical field. Returns (field or None, score 0..1).

    Three rules keep unseen spreadsheets honest:
      * the unit is taken out of the heading first, so 'ID (mm)' and 'id_mm' both read 'id';
      * a heading that carries a unit prefers a field of that kind, which is why 'id_mm'
        is the bore and not the part number;
      * short, genuinely ambiguous headings (id, no, ref, item...) only match exactly -
        they are never allowed to win by fuzzy similarity.
    """
    from difflib import SequenceMatcher
    norm, variants, unit_kind = _header_variants(raw)
    if not norm:
        return None, 0.0
    owned = bool(OWNER_WORDS & set(norm.split()))
    best: tuple[Optional[str], float] = (None, 0.0)
    for field_name, spec in CANONICAL_FIELDS.items():
        if owned and field_name in OWNER_BLOCKS:
            continue                    # 'operator name' is about the operator, not the part
        for syn in spec["syn"]:
            s = normalise_header(syn)
            if not s:
                continue
            for variant in variants:
                if s in EXACT_ONLY and variant != s:
                    continue
                if variant == s:
                    score = 1.0
                elif re.search(rf"(^| ){re.escape(s)}( |$)", variant):
                    score = 0.82
                elif s in variant or variant in s:
                    shorter = min(len(s), len(variant))
                    longer = max(len(s), len(variant))
                    score = 0.55 * shorter / longer + 0.15
                else:
                    ratio = SequenceMatcher(None, s, variant).ratio()
                    if ratio < 0.86:
                        continue
                    score = 0.5 + 0.3 * (ratio - 0.86) / 0.14
                if unit_kind and spec.get("kind") == unit_kind:
                    score += 0.1          # 'Diam. exterieur [mm]' -> a length field
                if score > best[1]:
                    best = (field_name, score)
    score = round(min(best[1], 1.0), 3)
    return (best[0], score) if score >= 0.45 else (None, score)
