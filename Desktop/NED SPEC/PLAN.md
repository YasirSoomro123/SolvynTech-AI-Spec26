# SPEC'26 Plan

## Decision record (from Step 0)
- Excel: single sheet `Manufacturing_Record`, header row 1, 18 cols, units in headers, part number INTEGER.
  Second sheet `Notes` must be ignored as data. `Drawing No.` = `2280-DWG` links row to files.
- PDF: digitally generated (ReportLab), selectable text, A4 landscape, title block is label/value pairs,
  dims also appear in GENERAL NOTES with ± and +0/-0.05 tolerances, comma decimals (`4,3`).
- IGES: 80-col fixed width, CRLF, `MM` units, 42 entities (314/128/126/502/504/508/510/514/186).
  3D InterOp (Spatial)/TraceParts export. Cylinder 502 validates standard layout:
  `502,T,xo,yo,zo,ax,ay,az,r,...` with |axis|=1 and r=4 -> OD 8. Planes 126 carry variable point lists.
  Part number is NOT in the IGES (model name = supplier code `219656-4_3x5.igs`) -> filename/folder must win.
- Verified geometry 2280: envelope X -4..4, Y -4..4, Z 0..5 -> OD 8, L 5, matches Excel/PDF.

## Architecture
part_locator -> readers (excel/pdf/iges) -> facts (Fact dataclass) -> normalise+units -> crosscheck
-> prompts -> llm_client (swappable) -> verifier (numbers must exist in fact sheet).
No API key => still show fact sheet + cross-check table.

## Generalization invariants
- No hard-coded column names: header-row detection + fuzzy synonym mapping + raw passthrough.
- Never trust LLM for numbers. Code does all extraction and unit conversion.
- Every fact carries source_file + location + confidence.

## Levels
1. Excel -> LLM answers. 2. +PDF with per-claim citation. 3. +IGES cross-check table.
Stretch: auto-discovered part list.

## Deliverables
app.py, main.py, src/*, tests/*, scripts/make_test_data.py, docs/{FILE_ANALYSIS,TECHNICAL_DOCUMENT,DEMO_SCRIPT}.md,
presentation/outline.md (+ .pptx), README.md, requirements.txt, .env.example.
