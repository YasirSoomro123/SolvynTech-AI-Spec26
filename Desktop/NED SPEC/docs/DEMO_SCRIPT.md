# 5-minute demo script

Everything below is live: real files, no pre-baked screenshots, no key required for
0:00-3:30. Have a terminal on the left and the browser on the right, both at 110 %+ font.

**Pre-flight (before you start talking):**

The organizers supplied no sample files, so the repo ships no parts. Either use your own
folder, or generate the test corpus - it is built on demand and never committed:

```bash
pip install -r requirements.txt          # once
python scripts/make_test_data.py --out data/demo    # 5 parts + the planted traps
streamlit run app.py                     # browser -> http://localhost:8501
```

In the sidebar set **Data folder** to the folder holding the parts (default `data`, which
contains `data/demo`), or drag the Excel/PDF/IGES files onto **Add part files** - they are
saved under the folder and appear in the part list on the same run. If the folder is empty
you get the three-step start screen; that screen is itself part of the demo, because it says
the app expects the shop's own files.

---

## 0:00 - 0:30  What is on the screen

> "This is a CNC shop's folder: a manufacturing record in Excel, an engineering drawing
> in PDF, a 3D model in IGES. Nobody typed the columns into the app, and the app was
> never told what these files look like. I pick a part number."

Pick `3001` in the **Part** box (it is searchable; the last option is *enter a part number
manually*, which is what you use when the folder is not indexed yet). Point at the summary
cards and the three source chips while they fill:

- each chip says **found** or **missing** for Excel / PDF / IGES, and the cross-check badge
  already says whether the three agree;
- open *Which file was chosen for each source, and why* to see the reasons (`'3001' appears
  1x in content`, `'3001' as a word in the filename`) and the candidates it rejected.

## 0:30 - 1:30  Level 1 + 2: the fact sheet, with provenance

Open **Extracted facts**. Filter eyes to one line:

> "outer_diameter = 12 mm - `factory_master.csv`, `'factory_master'!D2`, confidence
> **code-high**, note `column 'od_mm'` - a heading nobody told it about."

> "Every number here was read by code. The language model never extracts a value - it can
> only talk about this table. Look at the notes column: `read '12.0' as 12.0 mm`, and
> `split from 'Facing; Turning OD; Drilling...'` - the app tells you what it interpreted."

Open **Maya**, the floating avatar in the bottom-right corner, and ask (or press the
**Material** suggestion): **"What material is it?"**

> "Answer with two citations - the Excel cell and the PDF title block - shown as tags under
> the answer. `mode: no-llm`: that is the app with **no API key at all**. The extraction and
> the answers are code; the model only changes the wording."

## 1:30 - 2:30  Level 3: the cross-check table

Show the table for 3001:

> "Three sources for the same part disagree routinely - the record is typed by a planner,
> the drawing is drawn by a designer, the model is exported by CAD. So the app compares
> them: agree within half a millimetre **or** one percent. ✅ agree, ⚠️ disagree,
> ℹ️ only present in one source - and a value in one source is *not* a mismatch, it is
> just missing elsewhere. Cycle time is a manufacturing fact, so of course it is only in
> Excel."

Now switch the part to **3004** (a part nobody named for it - the generator writes it in a
different naming style and a different spreadsheet layout). Switch back to **3001** and then
to **3004** again: Maya comes back with *that* part's questions and answers, and the
3001 conversation is gone from the screen. Chat history is keyed by folder + part, so no
answer is ever phrased from another part's facts.

> "Watch the outer diameter row."

⚠️ **Outer diameter**: `Excel 20 vs PDF 21.95; IGES 20 vs PDF 21.95`.

> "That is a planted inconsistency: somebody revised the drawing and not the record. The
> app does not pick a winner and it does not average - it shows both, quotes where each
> came from, and the answer text carries the same CAUTION line. Two of the three sources
> agree with the model, so the drawing is the odd one out; the app never says that, and
> that is deliberate - deciding which is wrong is the engineer's job."

Ask **"Is the drawing consistent with the Excel record?"** and read the ✅/⚠️ verdict line.

## 2:30 - 3:10  Units, and a model that lies about them

Switch to **3005** - its IGES is in **inches**, its drawing says mm.

> "The parser reads the unit out of the IGES Global section and converts every coordinate
> to millimetres in code. So the geometry still matches the drawing - ✅ on the sizes -
> but the *declared units* row goes ⚠️, because a planner who does not notice that gets
> a part 2.54 times too big."

Show the answer to **"What units does the 3D model use?"**: drawing mm, model INCH, and
the CAUTION line. Then the **Warnings** expander for any part: `sheet 'Notes' has no
detectable header row - treated as prose, skipped`.

> "When it can't read something it says so instead of guessing."

## 3:10 - 3:45  Honesty, on purpose

Ask the three questions a judge will try to break it with:

1. **"What is the price per piece?"** -> *"I can't find that in the files"* + the list of
   fields that do exist. No currency invented.
2. **"What's the weather today?"** -> refusal. It does not have a opinion.
3. **`9999`** as the part number -> *"no files could be matched"*, and it names the parts
   that **are** in the folder: 3001...3005.

> "There is also a prompt-injection line written *inside* one of the synthetic drawings.
> It is captured as a general note, verbatim, marked as data, and it changes nothing about
> the answer - the model is never given instructions from a file."

## 3:45 - 4:30  With a language model (optional, if the key is set)

Flip **Use a language model for answers** on and ask:

> "Summarise this part for someone who has to machine it on Monday."

Point at the footer: `answered by llm (groq:openai/gpt-oss-120b)` and
**Verification OK - every number in this answer is in the fact sheet**. Then, if time:
turn the model off and on again to show the *same facts* arrive in different clothes.

## 4:30 - 5:00  Close

```bash
python main.py --part 3002 --data data/demo -q "What surface finish is required?" --quiet
python -m pytest tests -q            # 211 passed
```

> "The same engine behind a CLI and a web UI, 211 tests - most of which invent their own
> files in a temp directory, because the real test is 'does it work on a file nobody tuned
> it for'. Code extraction for every number, language model for judgement-free phrasing,
> and a table that shows you where the shop's own paperwork disagrees with itself."

> "And note what is *not* in this repository: no sample parts. The organizers gave us none,
> so everything on screen came out of the generator or from the sidebar uploader, which
> writes into the data folder and re-scans it on the same run."

---

## If something goes wrong

| Symptom | Say this |
|---|---|
| Streamlit not started | the CLI does everything the UI does: `python main.py --part 3004 --data data/demo --question ...` |
| No key / provider down | it is the demo's *feature*: `mode: no-llm`, everything still answers |
| A part shows no geometry | open Warnings - it says which entities didn't validate; that's the honest branch |
| Judge asks for a file we don't have | drag it onto **Add part files** (or put it in the data folder) and type its part number; discovery is by name *and* content, on the same run |
