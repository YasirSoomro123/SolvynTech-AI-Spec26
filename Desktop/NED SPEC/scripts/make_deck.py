"""Build presentation/cnc-part-analysis.pptx from the numbers the app really produced.

Every figure on every slide comes from a live run of the pipeline over the reference files
in tests/fixtures/reference/ and the generated corpus (see docs/DEMO_SCRIPT.md), so the deck
cannot say something the software does not.  Re-run after a code change and the deck
regenerates in one command:

    python scripts/make_deck.py

Design: one dark "blueprint" palette, Segoe UI for reading, Consolas for anything that is
literally a field name or a file location.  16:9, 1280x720 px logical grid.
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Emu, Pt

# ------------------------------------------------------------------ palette --
BG = RGBColor(0x0F, 0x1B, 0x2D)          # content pages
BG_COVER = RGBColor(0x0B, 0x15, 0x23)
BG_DATA = RGBColor(0x10, 0x20, 0x3A)
TEXT = RGBColor(0xE8, 0xEE, 0xF7)
MUTED = RGBColor(0x8F, 0xA6, 0xC2)
AMBER = RGBColor(0xF2, 0xA3, 0x3C)       # primary accent
CYAN = RGBColor(0x45, 0xB6, 0xD6)        # secondary accent
CARD = RGBColor(0x17, 0x27, 0x3D)
CARD_HI = RGBColor(0x1E, 0x33, 0x4E)
EDGE = RGBColor(0x2A, 0x3D, 0x57)

SANS = "Segoe UI"
BOLD = "Segoe UI Semibold"
MONO = "Consolas"

W, H = 1280, 720
PX = 9525                                 # one CSS pixel, in EMU, at 96 dpi


def px(value: int) -> Emu:
    return Emu(int(value) * PX)


# --------------------------------------------------------------- primitives --
def slide(prs: Presentation, bg: RGBColor):
    s = prs.slides.add_slide(prs.slide_layouts[6])          # blank
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = bg
    return s


def box(s, x: int, y: int, w: int, h: int, shape=MSO_SHAPE.ROUNDED_RECTANGLE,
        fill: RGBColor | None = CARD, stroke: RGBColor | None = EDGE, radius: float = 0.08):
    sh = s.shapes.add_shape(shape, px(x), px(y), px(w), px(h))
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    if stroke is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = stroke
        sh.line.width = Pt(1)
    sh.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        try:
            sh.adjustments[0] = radius
        except Exception:
            pass
    return sh


def text(s, x: int, y: int, w: int, h: int, paras: list, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP):
    """paras: list of {runs: [(txt, sizePt, font, color, bold)], space_after: px}"""
    tb = s.shapes.add_textbox(px(x), px(y), px(w), px(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = para.get("align", align)
        p.space_after = Pt(para.get("space_after", 6) / 1.333)
        p.line_spacing = para.get("line_spacing", 1.05)
        for (txt, size, font, color, *rest) in para["runs"]:
            r = p.add_run()
            r.text = txt
            r.font.size = Pt(size)
            r.font.name = font
            r.font.color.rgb = color
            r.font.bold = bool(rest[0]) if rest else False
    return tb


def run(txt, size, font=SANS, color=TEXT, bold=False):
    return (txt, size, font, color, bold)


def eyebrow(s, label: str, page_no: int):
    text(s, 80, 46, 900, 30, [{"runs": [run(label.upper(), 14, MONO, CYAN, True)]}])
    text(s, 1100, 46, 100, 30,
         [{"runs": [run(f"{page_no:02d} / 12", 14, MONO, MUTED)], "align": PP_ALIGN.RIGHT}])


def heading(s, title: str, sub: str = "", y: int = 84):
    text(s, 80, y, 1120, 62, [{"runs": [run(title, 31, BOLD, TEXT, True)]}])
    if sub:
        text(s, 80, y + 58, 1120, 60, [{"runs": [run(sub, 16, SANS, MUTED)]}])


# -------------------------------------------------------------------- slides --
def s01_cover(prs):
    s = slide(prs, BG_COVER)
    box(s, 0, 0, W, H, MSO_SHAPE.RECTANGLE, fill=BG_COVER, stroke=None)
    # the part number is the visual anchor: it is what you type into the app
    text(s, 80, 92, 900, 30, [{"runs": [run("SPEC'26   ·   LLM-BASED CNC PART ANALYSIS",
                                            15, MONO, CYAN, True)]}])
    text(s, 80, 118, 560, 150, [{"runs": [run("2280", 78, MONO, AMBER, True)]}])
    text(s, 660, 186, 540, 60, [{"runs": [run("one part number, typed by a person",
                                               17, SANS, MUTED)]}])
    text(s, 80, 296, 1120, 150, [
        {"runs": [run("Ask a part number.", 40, BOLD, TEXT, True)], "space_after": 8},
        {"runs": [run("Get its facts - with receipts.", 40, BOLD, TEXT, True)]},
    ])
    chips = [("Excel record", "how it is made"), ("PDF drawing", "what it must be"),
             ("IGES model", "what it really is")]
    for i, (t1, t2) in enumerate(chips):
        x = 80 + i * 340
        box(s, x, 470, 320, 62, fill=CARD)
        text(s, x, 486, 320, 34, [{"runs": [run(t1 + "   ", 17, BOLD, TEXT, True),
                                            run(t2, 14, SANS, MUTED)],
                                   "align": PP_ALIGN.CENTER}])
    box(s, 80, 574, 1120, 1, MSO_SHAPE.RECTANGLE, fill=EDGE, stroke=None)
    text(s, 80, 596, 1120, 34, [{"runs": [
        run("Level 3 + stretch goal    ·    211 tests, no network    ·    runs with no API "
            "key    ·    tuned to nothing", 15, SANS, MUTED)]}])


def s02_problem(prs):
    s = slide(prs, BG)
    eyebrow(s, "the problem", 2)
    heading(s, "One part, three files, and nobody who can read all three",
            "The record is typed by a planner, the drawing by a designer, the model by "
            "CAD. They disagree more often than anybody admits.")
    cards = [
        ("Excel", "manufacturing_record.xlsx", [
            ("17 columns, 1 row per part", "units live inside the headings"),
            ("'Outer Diameter (mm)' = 8", "the machine, the ops, the cycle time"),
        ], "18 facts for part 2280"),
        ("PDF", "2280.pdf", [
            ("Ø8 +0/-0.05, Ra 1.6, ISO 2768-m", "Ø and ± and callouts, in the drawing"),
            ("SCALE 14:1, A3, rev A", "and a title block with no fixed geometry"),
        ], "21 facts from 1 page"),
        ("IGES", "2280.igs", [
            ("42 entities, units = MM", "an 80-column punch-card format from 1980"),
            ("19 entities that do not validate", "a free-form B-spline export"),
        ], "34 facts, 0 invented sizes"),
    ]
    for i, (kind, fname, rows, note) in enumerate(cards):
        x = 80 + i * 380
        box(s, x, 250, 340, 358, fill=CARD)
        text(s, x + 24, 274, 292, 30, [{"runs": [run(kind, 20, BOLD, AMBER, True)]}])
        text(s, x + 24, 308, 292, 26, [{"runs": [run(fname, 13, MONO, MUTED)]}])
        body = []
        for line, why in rows:
            body.append({"runs": [run(line, 15, BOLD, TEXT, True)], "space_after": 2})
            body.append({"runs": [run(why, 13, SANS, MUTED)], "space_after": 16})
        text(s, x + 24, 344, 292, 200, body)
        text(s, x + 24, 556, 292, 36, [{"runs": [run(note, 14, MONO, CYAN, True)]}])


def s03_rule(prs):
    s = slide(prs, BG)
    eyebrow(s, "the decision everything follows from", 3)
    heading(s, "Code extracts. The language model only talks.")
    left = [
        ("Every number is parsed by a reader", "openpyxl, PyMuPDF, a hand-written "
         "IGES parser - deterministic, debuggable, testable."),
        ("Every fact carries its place", "'Manufacturing_Record'!F2  ·  page 1, title "
         "block  ·  IGES entity #1 (type 502)"),
        ("Every fact carries its confidence", "so 'read from a labelled cell' and 'guessed "
         "from pixels' are never the same claim."),
    ]
    right = [
        ("1. Map unknown headings", "it sees the column names and 3 sample cells, and may "
         "only rename them to a field that exists."),
        ("2. Read a scanned page", "a drawing with no text layer, transcribed - and every "
         "fact from it is labelled llm-vision."),
        ("3. Phrase the answer", "from the fact sheet and nothing else. It is never asked "
         "for a measurement."),
    ]
    box(s, 80, 196, 550, 428, fill=CARD)
    text(s, 108, 220, 494, 34, [{"runs": [run("WHAT CODE DOES", 15, MONO, CYAN, True)]}])
    body = []
    for t, d in left:
        body.append({"runs": [run(t, 17, BOLD, TEXT, True)], "space_after": 2})
        body.append({"runs": [run(d, 14, SANS, MUTED)], "space_after": 18})
    text(s, 108, 264, 494, 340, body)
    box(s, 650, 196, 550, 428, fill=CARD_HI)
    text(s, 678, 220, 494, 34, [{"runs": [run("WHAT THE MODEL DOES", 15, MONO, AMBER, True)]}])
    body = []
    for t, d in right:
        body.append({"runs": [run(t, 17, BOLD, TEXT, True)], "space_after": 2})
        body.append({"runs": [run(d, 14, SANS, MUTED)], "space_after": 18})
    text(s, 678, 264, 494, 340, body)
    text(s, 80, 640, 1120, 34, [{"runs": [
        run("A number from a language model cannot be audited; a number from a parser can.  ",
            15, SANS, MUTED, False),
        run("model used: groq:openai/gpt-oss-120b", 13, MONO, CYAN, True)]}])


def s04_ladder(prs):
    s = slide(prs, BG)
    eyebrow(s, "provenance", 4)
    heading(s, "Five levels of 'how sure are we', carried on every fact",
            "A cross-check row inherits the WORST confidence of the sources it compares.")
    steps = [
        ("code-high", "read from a labelled cell, column or title block",
         "outer_diameter = 8 mm   'Manufacturing_Record'!F2"),
        ("code-medium", "number parsed, unit or entity type inferred",
         "cylinder radius 6 mm   IGES entity #1 (type 502)"),
        ("code-low", "OCR text; characters may be mis-read",
         "Ra 1.6 um   OCR transcription, general note"),
        ("llm-vision", "a model read the pixels of a scan",
         "material: AL 6082   LLM vision transcription"),
        ("inferred", "the weakest trace, used only when nothing else exists",
         "a size inside a part code, not a measurement"),
    ]
    x0, w, gap = 80, 212, 14
    for i, (name, what, ex) in enumerate(steps):
        x = x0 + i * (w + gap)
        shade = CARD if i < 2 else CARD_HI
        box(s, x, 246, w, 300, fill=shade)
        text(s, x + 18, 270, w - 36, 30, [{"runs": [run(name, 17, MONO,
                                                         AMBER if i < 2 else CYAN, True)]}])
        text(s, x + 18, 306, w - 36, 120, [{"runs": [run(what, 14, SANS, TEXT)]}])
        text(s, x + 18, 452, w - 36, 84, [{"runs": [run(ex, 11.5, MONO, MUTED)]}])
        if i < 4:
            box(s, x + w + 1, 388, gap - 2, 2, MSO_SHAPE.RECTANGLE, fill=EDGE, stroke=None)
    text(s, 80, 574, 1120, 40, [{"runs": [
        run("The order is not decoration: it decides what the app is allowed to say, and "
            "what it must warn about instead.", 15, SANS, MUTED)]}])


def s05_excel(prs, image: Path):
    s = slide(prs, BG)
    eyebrow(s, "level 1  ·  any spreadsheet", 5)
    heading(s, "No hard-coded columns. Not one.")
    bullets = [
        ("The header row is found, not assumed", "row 1, row 3 or row 4; every sheet is "
         "judged on its own, and a prose sheet is reported and skipped."),
        ("Heading to field by synonym, fuzziness and the unit in the heading",
         "'id_mm' is the bore, not the part number; 'DIA_OUT', 'matl' and "
         "'Aussendurchmesser' all land on a canonical field."),
        ("Short ambiguous headings only match exactly", "id, no, ref, item are too easy to "
         "guess wrong - and 'operator name' is about the operator."),
        ("A column nobody recognises is kept, not dropped", "stored as raw:<heading>, still "
         "citable, still in the sheet."),
        ("One number parser for cells and prose", "1,234.5 and the European 1.234,5 and "
         "4,3 and 3 1/2 - and M5 or A1 are codes, refused as quantities."),
    ]
    body = []
    for t, d in bullets:
        body.append({"runs": [run("-  ", 15, SANS, AMBER, True),
                              run(t, 16, BOLD, TEXT, True)], "space_after": 2})
        body.append({"runs": [run("    " + d, 13.5, SANS, MUTED)], "space_after": 14})
    text(s, 80, 196, 640, 470, body)
    box(s, 744, 196, 456, 456, fill=CARD)
    s.shapes.add_picture(str(image), px(752), px(204), px(440), px(300))
    text(s, 772, 516, 400, 120, [
        {"runs": [run("proven by files nobody tuned the app for:", 13, SANS, MUTED)],
         "space_after": 6},
        {"runs": [run("DIA_OUT  ·  Temps [min]  ·  finish_ra  ·  Aussendurchmesser  ·  "
                      "header on row 4  ·  ';' CSV", 13.5, MONO, CYAN, True)]},
    ])


def s06_pdf(prs):
    s = slide(prs, BG_DATA)
    eyebrow(s, "level 2  ·  the drawing", 6)
    heading(s, "Reading a real drawing without being fooled by it",
            "Text comes out with coordinates, so a label finds the value beside it or "
            "below it. A rule claims the span it consumed: no number counts twice.")
    cards = [
        ("842 x 595", "the paper is A3. Not a length.", "paper-size guard"),
        ("SCALE 14:1", "a scale is never a dimension, and 14 is not 14 mm.",
         "title-block guard"),
        ("M5  ·  2 x M6 THRU", "threads are designations; the hole callout is separate.",
         "thread guard"),
        ("ISO 2768-m", "a tolerance class - its digits are not measurements. A bare "
         "ISO 1874 is a material spec unless the line says tolerance.", "standard guard"),
        ("4 X DIA 8 THRU", "one hole diameter of 8 mm and one quantity of 4, from one "
         "line, counted once.", "span claiming"),
        ("no text layer", "render at 200 dpi, try OCR, then a vision model - and if "
         "neither exists, warn. Never invent.", "scanned-page path"),
    ]
    for i, (t, d, tag) in enumerate(cards):
        col, row = i % 3, i // 3
        x, y = 80 + col * 380, 250 + row * 196
        box(s, x, y, 340, 176, fill=CARD)
        text(s, x + 20, y + 16, 300, 30, [{"runs": [run(t, 17, MONO, AMBER, True)]}])
        text(s, x + 20, y + 50, 300, 84, [{"runs": [run(d, 13.5, SANS, TEXT)]}])
        text(s, x + 20, y + 140, 300, 26, [{"runs": [run(tag, 12, MONO, MUTED)]}])


def s07_iges(prs):
    s = slide(prs, BG)
    eyebrow(s, "level 3  ·  the 3D model", 7)
    heading(s, "A 1980 file format, parsed in pure Python",
            "Start / Global / Directory / Parameter / Terminate, 80 columns per line, "
            "continuation letters, and nH field separators read from the file itself.")
    cells = [
        ("Units are read, then converted in code",
         "UNIT=1, MDM=IN in the Global section means 1 model unit = 25.4 mm. An inch model "
         "and a metric drawing still end up comparable - and the declared unit stays a "
         "fact of its own."),
        ("Decode only what validates",
         "circle 100, line 110, plane 126, cylinder 502, torus 122, B-spline 128: a "
         "parameter count that does not match the published layout is counted, skipped "
         "and written to warnings."),
        ("The envelope is sorted, never X/Y/Z",
         "exporters reorder axes, so the three extents are compared largest-to-smallest "
         "against the set of listed sizes. Control points make it too big, never too small."),
        ("Refusing is a feature",
         "our own 2280.igs is a free-form B-spline export: 42 entities, 19 that do not "
         "validate - so the app reports NO bounding box and says why, instead of guessing "
         "one."),
    ]
    for i, (t, d) in enumerate(cells):
        col, row = i % 2, i // 2
        x, y = 80 + col * 570, 246 + row * 208
        box(s, x, y, 550, 188, fill=CARD if i != 3 else CARD_HI)
        text(s, x + 24, y + 20, 502, 34, [{"runs": [run(t, 17, BOLD, TEXT, True)]}])
        text(s, x + 24, y + 60, 502, 108, [{"runs": [run(d, 13.5, SANS, MUTED)]}])


def s08_crosscheck(prs):
    s = slide(prs, BG_DATA)
    eyebrow(s, "level 3  ·  the cross-check", 8)
    heading(s, "Part 3004: the drawing was revised. The record was not.")
    rows = [("Excel record", 20.0, "DIA_OUT, 'PROD'!D2"),
            ("IGES model", 20.0, "cylinder entity #1"),
            ("PDF drawing", 22.0, "OD +0/-0.05, and 21.95 alongside it")]
    top, bar_h, gap = 250, 58, 26
    max_v = 24.0
    BAR_X, BAR_MAX = 300, 620
    text(s, 80, 196, 1120, 40, [{"runs": [
        run("Agree within 0.5 mm OR 1 %, whichever is bigger - so a 5 mm spacer is honest "
            "and a 900 mm frame is not flagged for rounding.", 15, SANS, MUTED)]}])
    for i, (src, val, where) in enumerate(rows):
        y = top + i * (bar_h + gap)
        text(s, 80, y + 14, 200, 30, [{"runs": [run(src, 15, BOLD, TEXT, True)]}])
        w = int(BAR_MAX * val / max_v)
        box(s, BAR_X, y, w, bar_h, MSO_SHAPE.RECTANGLE,
            fill=CARD_HI if val < 21 else AMBER, stroke=EDGE)
        text(s, 932, y + 14, 120, 30, [{"runs": [
            run(f"{val:g} mm", 16, MONO, AMBER if val >= 21 else TEXT, True)]}])
        text(s, 1060, y + 18, 210, 30, [{"runs": [run(where, 11, MONO, MUTED)]}])
    box(s, 80, 512, 550, 152, fill=CARD)
    text(s, 104, 532, 502, 120, [
        {"runs": [run("What the app does about it", 15, MONO, CYAN, True)], "space_after": 8},
        {"runs": [run("Reports both values with their locations and refuses to pick. "
                      "Two of three sources agree with the model, so the drawing looks "
                      "revised - but that judgement belongs to the engineer.",
                      14, SANS, TEXT)]},
    ])
    box(s, 650, 512, 550, 152, fill=CARD)
    text(s, 674, 532, 502, 120, [
        {"runs": [run("And the row that is not a conflict", 15, MONO, CYAN, True)],
         "space_after": 8},
        {"runs": [run("Cycle time and quantity appear in the record only: that is an "
                      "information row, never a mismatch. A value present in one file "
                      "is information, not an error.", 14, SANS, TEXT)]},
    ])


def s09_honesty(prs, image: Path):
    s = slide(prs, BG_COVER)
    s.shapes.add_picture(str(image), px(0), px(0), px(1280), px(720))
    box(s, 0, 0, W, H, MSO_SHAPE.RECTANGLE, fill=RGBColor(0x08, 0x11, 0x1E), stroke=None)
    # a translucent-looking panel is built as a solid block over the left two thirds
    box(s, 0, 0, 860, H, MSO_SHAPE.RECTANGLE, fill=RGBColor(0x0B, 0x15, 0x23), stroke=None)
    eyebrow(s, "honesty, enforced by code", 9)
    heading(s, "The 15 % of the brief that is not a feature")
    items = [
        ("The fact sheet is the only source", "the system prompt forbids outside knowledge "
         "and demands [Excel: file!cell] style citations."),
        ("Every finished answer is re-read", "a number that is not in the sheet, and not a "
         "documented derivation like radius to diameter, rejects the answer."),
        ("'I can't find that in the files' is a valid answer", "with the list of fields that "
         "do exist. No price was ever invented, no weather ever forecast."),
        ("Conflicts are quoted on both sides", "never averaged, never silently resolved."),
        ("Instructions inside a file are data", "the synthetic corpus plants a prompt-"
         "injection line in a drawing; it is stored verbatim as a general note and changes "
         "nothing."),
        ("No API key is a supported mode", "same facts, cited bullet answers, printed as "
         "mode: no-llm."),
    ]
    body = []
    for t, d in items:
        body.append({"runs": [run("-  ", 15, SANS, AMBER, True),
                              run(t, 16, BOLD, TEXT, True)], "space_after": 1})
        body.append({"runs": [run("    " + d, 13, SANS, MUTED)], "space_after": 11})
    text(s, 80, 190, 740, 470, body)


def s10_unseen(prs):
    s = slide(prs, BG)
    eyebrow(s, "generality", 10)
    heading(s, "We made our own test files - and made them not match.",
            "The organizers provided no samples, so nothing ships in data/: the corpus is "
            "generated on demand and deliberately breaks our own conventions. Nothing in "
            "src/ contains the string '2280', a column letter, or a page coordinate.")
    cols = [
        ("211 tests, no network", [
            "Most build their input on the spot in a temp directory: a sheet with the "
            "header on row 4, a ';' CSV, an IGES written by an independent test builder, "
            "a drawing that is only an image.",
            "Corrupt, empty, missing and unreadable files are all tested: they produce a "
            "warning, never a crash."]),
        ("5 synthetic extra parts", [
            "Different Excel layouts, units inside the headings, French and abbreviated "
            "column names, six file-naming styles.",
            "One part with no drawing at all, one model exported in inches, one planted "
            "dimension mismatch, one injection line."]),
        ("Discovery on unfamiliar names", [
            "2280.igs, 2280_drawing.pdf, part-2280.iges, '3004  rev C.pdf', 002280.igs and "
            "a folder called 2280 all identify the part.",
            "12280.igs and report-v22801.pdf do not - identity is a whole digit run, and a "
            "workbook must hold the number in a cell, not merely mention it."]),
    ]
    for i, (t, paras) in enumerate(cols):
        x = 80 + i * 380
        box(s, x, 258, 340, 350, fill=CARD)
        text(s, x + 24, 282, 292, 56, [{"runs": [run(t, 18, BOLD, AMBER, True)]}])
        body = [{"runs": [run(p, 13.5, SANS, TEXT)], "space_after": 16} for p in paras]
        text(s, x + 24, 346, 292, 250, body)


def s11_answers(prs):
    s = slide(prs, BG)
    eyebrow(s, "what it answers today", 11)
    heading(s, "Ask it anything about a part it has never been told about",
            "Answers shown with no API key: exact field lookup, cited, with confidence. "
            "With a key the wording becomes prose; the numbers may not change.")
    qa = [
        ("What material is it?",
         "material: Stainless Steel A1 (INOX)  ['Manufacturing_Record'!D2, code-high]  ·  "
         "same value from the PDF title block"),
        ("What is the outer diameter?",
         "8 mm from the record and 8 mm from the drawing, +0/-0.05 as drawn, "
         "agree within 0.5 mm / 1 %"),
        ("What units does the 3D model use?",
         "drawing says mm, IGES says INCH (1 model unit = 25.4 mm) - CAUTION, the sources "
         "disagree"),
        ("What is the price per piece?",
         "I can't find that in the files. The extracted record holds no cost value for this "
         "part. What is available: ..."),
        ("What's the weather today?",
         "refused. Nothing about weather is in a manufacturing record."),
        ("What material is part 9999?",
         "no files could be matched - and here are the part numbers that are in this "
         "folder: 3001, 3002, 3003, 3004, 3005"),
    ]
    for i, (q, a) in enumerate(qa):
        col, row = i % 2, i // 2
        x, y = 80 + col * 570, 246 + row * 140
        box(s, x, y, 550, 124, fill=CARD)
        text(s, x + 22, y + 14, 506, 30, [{"runs": [run(q, 15, BOLD, CYAN, True)]}])
        text(s, x + 22, y + 46, 506, 66, [{"runs": [run(a, 13, SANS, TEXT)]}])


def s12_close(prs):
    s = slide(prs, BG_COVER)
    eyebrow(s, "limits, next, and the one line", 12)
    text(s, 80, 100, 1120, 160, [{"runs": [
        run("Code for every number. A model for the talking.", 34, BOLD, TEXT, True)]},
        {"runs": [run("And a table that shows you where your own paperwork disagrees "
                      "with itself.", 34, BOLD, AMBER, True)], "space_after": 0}])
    box(s, 80, 268, 550, 300, fill=CARD)
    text(s, 104, 292, 502, 30, [{"runs": [run("LIMITS, SAID OUT LOUD", 14, MONO, CYAN,
                                               True)]}])
    lim = [
        "IGES geometry only where an entity type validates; no solids, no assemblies.",
        "A scanned page needs the tesseract binary or a vision model; with neither, a "
        "warning and no facts.",
        "Holes are candidates: circular geometry is not proof of a drilled feature.",
        "The verifier guarantees traceable numbers, not that the sentence answered the "
        "right question.",
    ]
    text(s, 104, 330, 502, 220, [{"runs": [run("-  ", 14, SANS, AMBER, True),
                                            run(l, 14, SANS, TEXT)], "space_after": 12}
                                 for l in lim])
    box(s, 650, 268, 550, 300, fill=CARD)
    text(s, 674, 292, 502, 30, [{"runs": [run("NEXT", 14, MONO, CYAN, True)]}])
    nxt = [
        "GD&T datum frames and feature control blocks in the PDF rule table.",
        "STEP via OpenCascade for real volumes, not envelopes.",
        "Learn a shop's own heading vocabulary once, then reuse it.",
        "Per-row provenance inside the chat answer, clickable to the file and place.",
    ]
    text(s, 674, 330, 502, 220, [{"runs": [run("-  ", 14, SANS, AMBER, True),
                                            run(n, 14, SANS, TEXT)], "space_after": 12}
                                 for n in nxt])
    text(s, 80, 596, 1120, 40, [{"runs": [
        run("python scripts/make_test_data.py --out data/demo        streamlit run app.py",
            14, MONO, MUTED)]}])


BUILDERS = [(s01_cover, None), (s02_problem, None), (s03_rule, None), (s04_ladder, None),
            (s05_excel, "cnc-lathe-spacer.png"), (s06_pdf, None), (s07_iges, None),
            (s08_crosscheck, None), (s09_honesty, "steel-shavings-dark.png"),
            (s10_unseen, None), (s11_answers, None), (s12_close, None)]


def build(out: Path) -> Path:
    prs = Presentation()
    prs.slide_width, prs.slide_height = px(W), px(H)
    imgs = out.parent / "images"
    for fn, image in BUILDERS:
        fn(prs, imgs / image) if image else fn(prs)
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out)
    return out


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "presentation" / "cnc-part-analysis.pptx"
    path = build(target)
    n = len(Presentation(path).slides.__iter__.__self__._sldIdLst)
    print(f"wrote {path}  ({n} slides)")
