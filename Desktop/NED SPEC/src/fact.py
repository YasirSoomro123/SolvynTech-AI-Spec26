"""Fact sheet data model - the single currency of this app.

Every parser (Excel, PDF, IGES) produces a list of Fact objects. The cross-check,
the prompt builder and the verifier all consume the same structure, so a claim can
always be traced back to a file and a location inside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Confidence levels, ordered. Parsers must never inflate these.
CONFIDENCE_ORDER = ["code-high", "code-medium", "code-low", "llm-vision", "inferred"]


@dataclass
class Fact:
    """One atomic statement taken from one file."""

    field: str                 # canonical field name, e.g. "outer_diameter"
    value: Any                 # number, string or list (already converted to mm where relevant)
    unit: Optional[str] = None # unit of *value*, e.g. "mm", "min", "Ra um"; None for text
    source_type: str = ""      # "Excel" | "PDF" | "IGES"
    source_file: str = ""      # path or name of the file it came from
    location: str = ""         # where in the file: "Sheet1!D5", "page 1, title block", "IGES entity #17 (type 126)"
    confidence: str = "code-high"
    note: str = ""             # caveats, e.g. "bounding box of control points, approximate"

    def display_value(self) -> str:
        """Value with unit, the way it should appear in prompts and tables."""
        if self.value is None:
            return "(empty)"
        if isinstance(self.value, float):
            txt = f"{self.value:g}"
        elif isinstance(self.value, (list, tuple)):
            txt = ", ".join(f"{v:g}" if isinstance(v, float) else str(v) for v in self.value)
        else:
            txt = str(self.value)
        return f"{txt} {self.unit}".strip() if self.unit else txt

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "unit": self.unit,
            "source_type": self.source_type,
            "source_file": self.source_file,
            "location": self.location,
            "confidence": self.confidence,
            "note": self.note,
        }


@dataclass
class SourceResult:
    """What one parser found in one file, plus the things that went wrong."""

    source_type: str                       # "Excel" | "PDF" | "IGES"
    file: str                              # path
    facts: list[Fact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ok: bool = True
    detail: str = ""                       # human summary, e.g. "3 sheets, 41 rows"

    def add(self, facts: list[Fact]) -> None:
        self.facts.extend(facts)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def fact_index(facts: list[Fact]) -> dict[str, list[Fact]]:
    """Group facts by canonical field name, preserving order."""
    out: dict[str, list[Fact]] = {}
    for f in facts:
        out.setdefault(f.field, []).append(f)
    return out
