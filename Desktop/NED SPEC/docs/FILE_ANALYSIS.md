# FILE ANALYSIS (Step 0)

Everything below was produced by opening the reference files programmatically (pandas/openpyxl,
PyMuPDF/pdfplumber, and a hand-written 80-column IGES walk). Findings are tagged:
**[G]** = likely general (any CNC dataset will show this) · **[O]** = specific to OUR files only, the
app must not depend on it.

## 1. The folder layout

```
data/
├── manufacturing_record.xlsx      one row per part, 18 columns
├── 2280/  2280.pdf  2280.igs
└── 2281/  2281.pdf  2281.igs
```

**[G]** One folder per part number, files named after the part number — the most common convention.
**[O]** Only 2 parts, and exactly one file of each type per part. Real/unseen data may put every
drawing in one flat directory, use suffixes (`2280_revB.pdf`, `part-2280.iges`, `2280_model.igs`),
have several Excel files, or one Excel per part. Discovery therefore has to be recursive and
filename-**and**-content based, never `<part>/<part>.ext`.

## 2. `manufacturing_record.xlsx`

Two sheets:

| Sheet | Shape | Role |
|---|---|---|
| `Manufacturing_Record` | A1:R3 → 18 columns, 2 data rows | the actual record |
| `Notes` | 4 single-cell rows | provenance/disclaimer text, **not** part data |

**[G]** Sheet 2 is prose, not tabular — a naive "read every sheet as a table" loop turns it into
garbage rows. **[O]** the specific text of those notes.

Header row (row 1, no merged cells, no blank rows):

`Part Number · Part Name · Drawing No. · Material · Material Standard · Outer Diameter (mm) ·
Inner Diameter (mm) · Length (mm) · Quantity · Stock Size · Machine · Operations ·
Cycle Time (min) · General Tolerance · Surface Finish (Ra um) · Supplier Ref · Revision · Remarks`

Observed quirks and what they force us to do:

1. **[G] Units live inside the header text** (`Outer Diameter (mm)`, `Cycle Time (min)`,
   `Surface Finish (Ra um)`). Units must be parsed out of the header and attached to the value.
2. **[G] `Part Number` is stored as an INTEGER (2280), not text.** Any comparison must be
   numeric-normalised: `"2280"`, `2280`, `2280.0`, ` 2280 `, `PN-2280` must all match.
3. **[G] `Drawing No.` (`2280-DWG`) is a foreign key** to the drawing file — a second, independent
   join path besides the filename. Use it as a candidate search term.
4. **[G] Delimited multi-values**: `Operations` = `Facing; Turning OD; Drilling; Tapping M5; Parting`
   (`;`). Must be split into a list but the raw string kept.
5. **[G] Free text embeds facts**: `Remarks` = `Threaded internal hole (D2 = 4.3 mm)` repeats the
   inner diameter; `Part Name` = `Cylindrical Spacer 219656-4,3x5` encodes the supplier code
   `4,3x5` (OD-less bore x length) with a **comma decimal separator**.
6. **[G] Mixed types in one column** (Quantity `500` int, Cycle Time `3.5` float) and empty cells are
   expected in unseen data → never assume a dtype, never crash on `None`.
7. **[O]** `Notes` sheet admits Quantity/Machine/Operations/Cycle Time/Tolerance/Finish/Revision were
   *assumed* (only dimensions/material/supplier ref come from the real TraceParts datasheet). Good
   honesty demo, but the app must not read that sheet as data.
8. **[G]** No cost/price column at all. The app must answer "I can't find that in the files" for
   cost questions rather than inventing one.

## 3. PDFs: `2280/2280.pdf`, `2281/2281.pdf`

Both are **vector, digitally generated** (Producer `ReportLab`, PDF 1.3, page 842x595 pt = A4
landscape), 573 characters of extractable text, 0 raster images, ~33 vector drawings each.

**[G]** Text extraction with PyMuPDF/pdfplumber works — no OCR needed *for these*.
**[O]** That they are clean digital PDFs. Unseen drawings are very likely CAD exports; scanned/
photographed drawings are plausible, so the app must detect "little or no text" and fall back to OCR
or a vision LLM instead of silently returning an empty fact sheet.

Text layout (important): PyMuPDF returns the title block as **alternating label and value lines**,
not as table rows:

```
PART NAME                       ← label
CYLINDRICAL SPACER 219656-4,3X5 ← value
PART NUMBER / 2280
MATERIAL / STAINLESS STEEL A1 (INOX)
SCALE / 14:1   UNITS / mm   REVISION / A   DRAWN BY / SPEC26 TEAM
SUPPLIER REF / 219656-4,3X5 (BENE INOX)
```

**[G]** Title-block label→value pairs are the standard structure on any drawing, but reading them by
*line adjacency* is fragile (PDF text order follows draw order, not visual layout). Mitigation used:
group words into text blocks with their coordinates and pair a label with the value found nearest it
(below/right), falling back to adjacency.

Content that must be regex-extracted, all present here:

- **[G] General notes carrying dimensions + tolerances**:
  `4. OUTER DIAMETER DIA 8 +0/-0.05 mm; LENGTH 5 +/-0.1 mm`,
  `5. INTERNAL THREAD M5 THROUGH; DEBURR ALL EDGES`
- **[G] Tolerance notation varies within one file**: `+/-0.1` **and** `+0/-0.05` **and** (elsewhere)
  `±0.1`. A parser that handles only one form fails.
- **[G] General tolerance standard reference**: `ISO 2768-m` (a *class*, not a number — must not be
  parsed as a dimension).
- **[G] Surface finish** `Ra 1.6 um`, **thread callouts** `M5`/`DIA 4.3 (THREADED M5)`,
  **scale** `14:1` (a scale is not a dimension — must never be read as a size), **units** `mm`,
  **revision** `A`.
- **[G] View labels and note headers** (`FRONT VIEW (SECTION SHOWN AS HIDDEN LINES)`, `SIDE VIEW`,
  `GENERAL NOTES:`) are noise that a naive number scan would happily turn into "facts".
- **[O]** Comma decimals appear in `PART NAME` (`219656-4,3x5`) while dimension callouts use points
  (`DIA 8`). European drawings use comma decimals throughout → comma/point must be decided per token
  with a plausibility test, and 128 must not become "12,8".

## 4. IGES models: `2280/2280.igs`, `2281/2281.igs`

Physical format (both files, verified): pure ASCII, **every line exactly 80 columns**, CRLF
(238 / 214 lines), sections by column 73 letter: `S`×1, `G`×3, `D`×84 (42 entity directory pairs),
`P`×149 / 125, `T`×1.

**[G]** 80-column fixed width, the section letter in column 73, directory entries as *pairs*, and a
`,`-separated Global section. Our parser must key off the column-73 letter and never assume a line
count.
**[O]** TraceParts / `3D InterOp ACIS/IGES` (Spatial Corp.) as the exporter, and its one nasty quirk
(see 4.2).

### 4.1 Global section — reliably readable facts

```
1H,, 1H;, 1H , 16H219656-4_3x5.igs, 13HSpatial Corp., 20H3D InterOp ACIS/IGES,
32, 38, 6, 308, 15, 1H , 1.000, 2, 2HMM, 1, 1.000, 15H20261026.144822, 1.0e-06, 0.00,
10HTraceParts, 17HTraceParts S.A.S., 11, 0, 15H20261026.144822;
```

**[G]** Field 5 = model/file name, 6 = author, 7 = post processor, 13/14 = line weight factor /
**units** (`2HMM` → 2 = count of following chars), 15/16 = terminal conv factor / **grid conversion**
(1 = mm), 17 = transparency, 18 = timestamp, 19 = **record size 32/64**, 20 = **float digits**,
21 = maximum error, 23 = product name, 24 = company, 26 = start of section flag.
**[G]** Units are `MM` here but `INCH`/`CM`/`FEET` are equally common. Conversion to mm must happen in
code (see §5). **[O]** These specific values (Tolerance `1.0e-06`, `TraceParts`).

**[G] Critical:** the model's own name is the *supplier* code (`219656-4_3x5.igs`), **not** the part
number — so a part-number search inside the IGES content finds nothing here. The part number lives
only in the **filename** and **folder name**. Discovery must therefore rank filename/folder matches
above content matches, and must not reject a file just because the part number is absent from its
interior. **[O]** That these two files lack the part number; unseen files may or may not have it.

### 4.2 Entity inventory (both files: 42 entities, identical type histogram)

| Type | Count | Meaning | Geometry we can take |
|---|---|---|---|
| 314 | 6 | Property ( colour `MixedColor;` ) | none (skip, it is not geometry) |
| 128 | 6 | Rational B-spline surface | control-point coordinates → bbox, **approximate** |
| 126 | 12 | Plane (normal + point list) | points → bbox |
| 502 | 1 | Right circular cylinder | radius → OD, axis, height |
| 504 | 1 | Parametric surface (patch list) | references only |
| 508 | 8 | Torus (fillets/rounds/chamfer arcs) | major/minor radius → fillet candidates |
| 510 | 6 | Parametric edge | topology only |
| 514 | 1 | Parametric surface entity (the shell) | topology only |
| 186 | 1 | Rational B-spline curve | control points |

**[G]** Exported B-rep IGES from a STEP/ACIS pipeline looks like this: splines everywhere instead of
clean analytic entities, property/colour entities (314) mixed in, topology entities (504/510/514) that
carry *indices*, not coordinates. A parser that only understands circles/lines (as most IGES
"geometry extraction" tutorials assume) yields nothing useful here. **[G]** Entity *counts* are
reliable facts; the mix of types is exporter-dependent, so counts must be reported as counts, not
translated into engineering claims ("8 tori" must not become "8 fillets" — say "torus entities, often
fillets/rounds").

**Verified geometry facts we can honestly derive for 2280:**
- Units `MM`, scale 1 → no conversion.
- 1 cylinder, radius **4.0** → outer diameter **8.0 mm** (matches Excel `F2=8`, PDF `DIA 8`).
- Coordinate envelope over plane/cylinder/BSpline points: **X −4…4, Y −4…4, Z 0…5** → Ø8 × 5 long,
  i.e. the spacer's OD and length, with the bore NOT visible from the envelope (it is a spline surface).
- 2281 follows the same pattern with Ø6 × 8 long (cylinder radius 3, envelope Z 0…8).

Confidence rules we adopt: cylinder radius / plane corner coordinates = `code-high` *as coordinates*;
derived diameters = `code-medium` (derived from one entity); BSpline control-point bbox = `code-low`
with the note "bounding box of control points, approximate — true surface lies inside it";
"hole candidates" = count of circles/cylinders, never asserted as a hole count.

### 4.3 The exporter quirk that broke the first parser

This file's Parameter lines put the **directory sequence number right-justified inside the 72-column
data field**, *in addition* to the standard section letter + element number in columns 73–80:

```
"502,8,-2.5,-0.,2.15000000000001,2.5,0.,-4.,2.5,-0.,…   " + "P      7"
                                                            ^^^^^^^^ element number (standard)
                                       ^^^^^^^^^^^^^^^^ stray "7" = directory entry number (non-standard)
```

Naive concatenation of the 72-column fields inserts stray integers into the number stream and shifts
every field by one — which is exactly how the first draft produced `radius = -4` and a phantom
"X up to 233 mm". **Fix:** strip a trailing right-justified integer that follows whitespace, and
validate each entity against its documented parameter count before trusting it (type 502 checks out
with `T,xo,yo,zo,ax,ay,az,r,…`, |axis| = 1.000, r = 4.0).
**[O]** this quirk. **[G]** "column 73–80 conventions differ between exporters, and line data may be
padded" — expect variants; parse by section letter + validate, and on mismatch record a warning and
skip the entity instead of crashing or guessing.

## 5. Cross-file relationships (what Level 3 must reconcile)

| Concept | Excel | PDF | IGES |
|---|---|---|---|
| Identity | `Part Number` 2280 (int), `Drawing No.` `2280-DWG` | title block `PART NUMBER / 2280` | none — filename `2280.igs` only |
| Outer dia | `Outer Diameter (mm)` 8 | `DIA 8`, `+0/-0.05` | cylinder radius 4 → Ø8; envelope 8 wide |
| Bore | `Inner Diameter (mm)` 4.3 | `DIA 4.3 (THREADED M5)` | *not* envelope-derivable (spline surface) |
| Length | `Length (mm)` 5 | `LENGTH 5 +/-0.1` | envelope 5 tall |
| Material | `Stainless Steel A1 (INOX)` + standard | note 1, same string | never present |
| Finish | `Surface Finish (Ra um)` 1.6 | `Ra 1.6 um` | never present |
| Tolerance | `ISO 2768-m` (class) | `ISO 2768-m` + explicit ± values | `1.0e-06` model tolerance (a CAD tessellation tolerance, **not** a manufacturing tolerance — must not be compared) |
| Revision | `A` | `A` | timestamp only |
| Process | `CNC Lathe`, 5 operations, 3.5 min/part, qty 500 | absent | absent |

**[G]** The three sources agree on purpose for dimensions but each holds facts the others do not
(material/process only in Excel; tolerances as *numbers* only in the PDF; the *actual 3D envelope* only
in IGES). A cross-check must therefore report "only in one source" (ℹ️) as a normal outcome, not an
error, and must compare dimensions on a unit-normalised mm basis.
**[G]** Bounding-box axes come out in whichever order the CAD coordinate system used, so dimension
comparison must sort each source's three sizes and compare sorted lists — not assume Z is the length.
**[G]** Expected true disagreement: Excel `Inner Diameter 4.3` vs PDF `M5 thread` — the pilot/ drilled
diameter (4.3 mm) and the thread designation (M5) are *different quantities that look like the same
one*. Reporting that as a mismatch is a false alarm; the app should present both and explain.

## 6. What we must NOT hard-code

Column names, sheet names, header row index, `<part>/<part>.<ext>`, "units are mm", "IGES units are
always in field 15", tolerance glyph `±` only, PDF title-block line positions, the assumption that all
three files exist, the assumption that a PDF is text-based, the assumption that IGES uses analytic
circle/line entities, and any expectation that a part number appears inside the IGES.
