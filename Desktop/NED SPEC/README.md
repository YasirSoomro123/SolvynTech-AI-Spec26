# LLM-based CNC part analysis (SPEC'26)

Type a part number - get its facts, from three sources, with the file and the exact
place each fact came from, and an answer that cannot contain a number nobody extracted.

```
python main.py --part 1234 --data "C:\path\to\your\files" --question "What material is it?"
streamlit run app.py
```

**The organizers supplied no sample files, so this project ships no parts.** `data/`
contains a README only. Point the app at any folder that holds a part's Excel record,
PDF drawing and IGES model, or drag those files onto **Add part files** in the sidebar -
they are saved under `data/uploads/`, re-discovered, and appear in the part list on the
same run. For a smoke test without your own data, generate the synthetic corpus (below).

## What it does

| | |
|---|---|
| **Inputs** | an Excel manufacturing record, a PDF engineering drawing, an IGES 3D model - in any naming style, in any folder layout |
| **Extraction** | 100 % by code. The language model is never asked to read a number. |
| **Language model** | maps unfamiliar column headings, reads scanned drawings, and phrases answers |
| **Output** | a fact sheet (`field, value, unit, source, file, location, confidence`), a cross-check table (✅ agree / ⚠️ disagree / ℹ️ only one source), and cited answers |
| **Level reached** | Level 3 (Excel + PDF + IGES cross-check) + the stretch goal of answering any part number it finds by itself |

**Nothing is tuned to our files.** There is no `if part == 2280`, no hard-coded column
letter, no page-coordinate assumption from one drawing. The generated corpus
(`python scripts/make_test_data.py --out data/demo`) deliberately breaks our own
conventions (header on row 3, French and
abbreviated headings, `DIA_OUT` instead of "Outer Diameter", a model in inches, files
named `pin-3003.iges` and `3004  rev C.pdf`, one part with no drawing) and the tests use
files invented on the spot in `tmp_path`, so an unseen file is the normal case, not the
lucky one.

## Install and run

```bash
python -m venv .venv
.venv\Scripts\activate                 # Windows   (mac/linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env                 # optional: no key is needed to run the app
```

```bash
python scripts/make_test_data.py --out data/demo   # a corpus to try it on: 5 parts + traps
python -m pytest tests -q                          # 293 tests, no network, no key, no data/
python main.py --list --data data/demo             # which part numbers live in this folder?
streamlit run app.py
```

Tests never read `data/`: the reference files they check live in `tests/fixtures/reference/`
and the synthetic corpus is generated into a temporary directory at test time.

On a shared network (a hackathon floor, a campus Wi-Fi) bind the app to this machine only,
so nobody else can drive it: `streamlit run app.py --server.address 127.0.0.1`.

### Without an API key

This is a supported mode, not an error. The fact sheet, the sources panel, the
cross-check table and exact field lookup all work; answers are printed as cited bullet
lines instead of prose, and the answer says `mode: no-llm`.

### With a key

Set one of `GROQ_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY`, or point
`OLLAMA_BASE_URL` at a local model. The provider is picked from whichever key exists;
`LLM_PROVIDER` overrides. Groq or Gemini free tier is the fastest demo path.

**The model used for this build is Groq's `openai/gpt-oss-120b`** - set it explicitly,
because Groq's model list is account-specific and the built-in default
(`llama-3.3-70b-versatile`) is not offered on ours:

```
LLM_PROVIDER=groq
GROQ_API_KEY=<your key>
LLM_MODEL=openai/gpt-oss-120b
```

Free-tier Groq allows 8,000 tokens a minute and one asked question costs about 5,000, so
leave ~40 s between questions. When the configured model is out of quota the client hands
over to the next one on the same key (`LLM_FALLBACK_MODELS=model-a,model-b`; Groq defaults
to `openai/gpt-oss-20b`, `none` switches it off), and the answer names the model that
actually replied. If every model is out, the answer is the deterministic lookup plus
"Language model unavailable: its usage limit is reached" (`mode: limited`) - never the
provider's raw error. A bare "hi" is answered locally without spending a model call.

## How a part is found

`src/part_locator.py` walks the folder recursively (skipping `~$` temp files and hidden
directories), scores every candidate by filename **and** by content, and reports the
winner *and* the rejects:

Example folder: `tests\fixtures\reference\` (the one reference set the repo keeps for smoke
tests). Yours can be laid out any way at all:

```
SOURCES
  Excel tests\fixtures\reference\manufacturing_record.xlsx   <- a cell holds exactly '2280'
  PDF   tests\fixtures\reference\2280\2280.pdf   <- filename exactly '2280'; folder named '2280'
  IGES  tests\fixtures\reference\2280\2280.igs   <- filename exactly '2280'; folder named '2280'
```

The identity test is a whole digit run, so `002280.igs` is part 2280 but `12280.igs` is
not, and a workbook counts as a match only when a cell *equals* the number - a remark
that happens to mention "see 4412" does not claim that part.

## How each format is read

**Excel** (`src/excel_reader.py`) - the header row is *found*, not assumed (it may be
row 3 or 4); merged cells and blank rows are tolerated; each sheet is judged on its own.
Headings are matched by synonym list + fuzzy similarity + the unit hidden in the heading
(`id_mm` is the bore, not the part number), and short ambiguous headings (`id`, `no`,
`ref`) only match exactly. A column nobody recognises is kept as a `raw:` fact rather
than dropped. Optionally the LLM is shown the headings and two sample cells and may
*rename* them to known fields - it cannot invent a value, and a rename to a field the
schema does not know is discarded.

**PDF** (`src/pdf_reader.py`) - text comes out with coordinates, so a label finds the
value beside it or below it. A declarative rule table reads callouts (Ø, R, depth,
chamfer, counterbores, threads, `4 X DIA 8 THRU`, Ra, ±, limit tolerances, general
tolerance standards, revision, scale, units, title block). Guards stop the classics: a
scale `14:1` is not a dimension, A3's `842 x 595` is not a size, `ISO 1874` is a material
spec unless the line says "tolerance", and `M5` is a thread, not a length. If the page has
no usable text layer it is rendered and OCR is tried; if a vision model is configured it
transcribes the page and every fact from it is labelled `llm-vision`.

**IGES** (`src/iges_reader.py`) - a hand-written 80-column parser (Start / Global /
Directory / Parameter / Terminate), no external CAD library. Units come from the Global
section and every number is converted to mm in code. Entity counts, the author, the
post-processor, circle/cylinder/torus/B-spline/plane geometry are decoded where the
parameters match the published layout; a `122` torus can size a ring, a `126` plane cannot
tell you anything about a turned part. The bounding box is built from validated geometry
only, and if the file's entities do not validate the parser says so and reports **no**
envelope instead of guessing one. Anything it cannot handle is counted, skipped and
written to `warnings`.

## Cross-check (Level 3)

`src/crosscheck.py` compares the same field across sources: numbers agree within
0.5 mm **or** 1 % (bigger wins, so it works on a 5 mm spacer and a 900 mm frame), text
ignores case and separators, and a model envelope is compared **sorted** because exporters
reorder axes. A value present in one source is `ℹ️ only-one-source`, never a mismatch, and
each row inherits the *lowest* confidence of the sources it compares.

## Honesty rules the code enforces

- the system prompt allows only the fact sheet as a source, and demands `[Excel:file!cell]`
  style citations;
- `src/verifier.py` re-reads the finished answer: any number that is not in the fact sheet
  (and not a documented derivation such as radius↔diameter or an inch→mm conversion)
  rejects the answer, which falls back to the deterministic one;
- missing data answers "I can't find that in the files" plus what *is* available;
- conflicting values are reported on both sides, never silently averaged;
- instructions found inside a file are stored verbatim as a `general_note` and treated as
  data (there is a real injection line in the synthetic corpus, and a test that it is
  never obeyed);
- an unrelated question is not answered from general knowledge.

## Layout

```
app.py                  Streamlit UI: part box, sources, cross-check, fact sheet; chat lives in Maya
main.py                 CLI: --part --data --question --list --json --no-llm --quiet
src/excel_reader.py     record -> facts (header detection, fuzzy mapping, units)
src/pdf_reader.py       drawing -> facts (rule table, scanned/vision path)
src/iges_reader.py      model -> facts (80-column parser, validated geometry)
src/part_locator.py     which file belongs to which part, and why
src/crosscheck.py       the ✅ / ⚠️ / ℹ️ table
src/schema.py           canonical fields, synonyms, heading matching
src/units.py            one number parser for cells and prose ('1.234,5', '3 1/2', '4,3')
src/ui_state.py         per-part chat history and file fingerprints (Streamlit-free, tested)
src/llm_client.py       swappable provider over plain HTTP
src/prompts.py          the fact sheet is the only allowed source
src/verifier.py         every number in an answer must exist in the sheet
src/pipeline.py         part number -> report -> answer, and the no-key deterministic path
scripts/make_test_data.py  builds the synthetic corpus, and can verify it
data/                   README only - add your own files (or use the sidebar uploader)
tests/                  293 tests + tests/test_questions.md
tests/fixtures/reference   the one reference part set, kept for smoke tests only
docs/                   FILE_ANALYSIS.md, TECHNICAL_DOCUMENT.md, DEMO_SCRIPT.md
```

## Known limits (said out loud, not hidden)

- A drawing whose text layer is missing *and* no vision model is configured yields a
  warning, not facts.
- The IGES parser reads the entity types it can validate; a heavy free-form surface
  export (our 2280 model is one) gives entity counts and units but no envelope.
- Hole counting is "candidates": a circle in a plane at one height suggests a hole, it is
  not proof of a drilled feature.
- `.xls` needs `xlrd`, which is not installed by default; the app reports the file as
  unreadable instead of crashing.
- OCR needs the `tesseract` binary on PATH; without it the vision path is the only route
  for a scan.
- The verifier checks *numbers*; a wrong-but-existing number ("the length is 5 mm" asked
  about the diameter) is the model's phrasing problem, and the citation tells you where
  to look.

## Look and feel

The pixel-window theme (lavender grid, cream windows, teal / orange / pink accents) lives in
`src/ui_theme.py` and `.streamlit/config.toml`; the assistant avatar is drawn in code by
`src/ui_avatar.py`. None of it touches extraction or answers.

- **Intro:** a pixel "Loading..." animation plays once per visit. Put `intro.mp4` (or
  `.webm/.mov/.m4v`) in `assets/` and that video is played instead, with an *Enter the app* button.
  `SPEC_SKIP_INTRO=1` switches the intro off (the tests do this).
- **Maya:** a floating avatar bottom-right on every screen. The chat lives only in her window:
  click her to open the greeting, suggested questions, evidence, ratings, clear/download and the
  per-part conversation; close her and the window gets out of the way.
