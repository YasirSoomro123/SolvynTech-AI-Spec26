#!/usr/bin/env python3
"""Command line entry point.

    python scripts/make_test_data.py --out data/demo   # nothing ships; generate a corpus
    python main.py --list --data data/demo
    python main.py --part 3004 --data data/demo --question "What material is it?"
    python main.py --part 2280 --data /path/to/customer/files --json

Works with no API key: it always prints the fact sheet and the cross-check table,
and answers questions by exact field lookup instead of by language model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.llm_client import LLMClient
from src.pipeline import Answer, Report, ask, build_report
from src.part_locator import discover_parts


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="LLM-based CNC part analysis (SPEC'26).")
    ap.add_argument("--part", help="part number to analyse, e.g. 2280")
    ap.add_argument("--data", default="data", help="folder that holds the files (default: data)")
    ap.add_argument("--question", "-q", action="append", default=[],
                    help="question to answer; repeat for several questions")
    ap.add_argument("--list", action="store_true", help="list part numbers found in --data and exit")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--no-llm", action="store_true", help="skip the language model entirely")
    ap.add_argument("--quiet", action="store_true", help="answer only, no fact sheet")
    return ap


def print_human(rep: Report, answers: list[Answer], quiet: bool) -> None:
    bar = "=" * 78
    print(f"{bar}\nPART {rep.part}   data folder: {rep.root}\n{bar}")
    print("\nSOURCES\n-------")
    if rep.files is not None:
        for kind, path in rep.files.paths().items():
            cand = rep.files.chosen.get(kind)
            why = "; ".join(cand.reasons) if cand else ""
            print(f"  {kind:5s} {path}   <- {why}")
        for kind in rep.files.missing_kinds:
            print(f"  {kind:5s} (not found - analysis continues without it)")
        if rep.files.rejected:
            print("  other candidates considered:")
            for c in rep.files.rejected:
                print(f"    - {c.kind} {c.path.name} (score {c.score:g}: "
                      f"{'; '.join(c.reasons) or 'no identity match'})")
    for res in rep.results:
        print(f"  {res.source_type} {Path(res.file).name}: {res.detail}")
    if not quiet:
        print("\nFACT SHEET\n----------")
        print(rep.fact_sheet())
        print("\nCROSS-CHECK (Excel vs PDF vs IGES)\n------------------------------")
        print(rep.table())
    for a in answers:
        print("\nQUESTION\n--------")
        print(f"  {a.question}")
        print("\nANSWER\n------")
        # the answer is multi-line; every line has to keep the column indent
        print("\n".join("  " + line for line in a.text.splitlines()))
        if a.verification is not None:
            v = a.verification
            note = v.message or "every number in the answer appears in the fact sheet"
            print(f"  [{v.badge()}] {note}")
        print(f"  (mode: {a.mode}{', model: ' + a.model if a.model else ''})")
    warnings = rep.all_warnings()
    if warnings:
        print("\nWARNINGS\n--------")
        for w in warnings:
            print(f"  ! {w}")


def main(argv: list[str] | None = None) -> int:
    # the cross-check table uses ✅/⚠️/ℹ️; a Windows console defaults to cp1252 and would
    # crash on them, so the CLI prints UTF-8 instead
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    args = build_parser().parse_args(argv)
    root = Path(args.data)
    if args.list:
        parts = discover_parts(root)
        print(json.dumps(parts) if args.json else "\n".join(parts) or "(no part numbers found)")
        return 0
    if not args.part:
        print("give --part <number> (or --list). Try: python main.py --part 2280 --data data",
              file=sys.stderr)
        return 2

    llm = None if args.no_llm else LLMClient.from_env()
    rep = build_report(args.part, root, llm=llm)
    questions = args.question or ["What is this part, what is it made of, and what are its "
                                  "main dimensions?"]
    answers = [ask(rep, q, llm=llm) for q in questions]

    if args.json:
        print(json.dumps({
            "part": rep.part,
            "root": str(root),
            "files": {k: str(p) for k, p in rep.files.paths().items()} if rep.files else {},
            "missing_kinds": rep.files.missing_kinds if rep.files else [],
            "facts": [f.as_dict() for f in rep.facts],
            "crosscheck": [{"status": r.status, "label": r.label, "values": r.values,
                            "detail": r.detail} for r in rep.rows],
            "answers": [{"question": a.question, "text": a.text, "mode": a.mode,
                         "verification": None if a.verification is None
                         else a.verification.__dict__} for a in answers],
            "warnings": rep.all_warnings(),
        }, indent=2, default=str))
    else:
        if llm is not None:
            print(f"[llm] {llm.describe()}" if llm.available
                  else "[llm] none configured - fact sheet, table and exact field lookup only")
        print_human(rep, answers, args.quiet)
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
