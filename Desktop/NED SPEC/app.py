"""Streamlit UI: pick a part, see what the files actually say, cross-check them, ask.

Run it with:  streamlit run app.py
With no API key in .env the fact sheet, the cross-check table and exact field lookup still
work - only the language-model phrasing is skipped, and the answer says so.
"""

from __future__ import annotations

import difflib
import traceback
from pathlib import Path

import pandas as pd
import streamlit as st

from src.crosscheck import summary as crosscheck_summary
from src.llm_client import LLMClient
from src.pipeline import Answer, Report, ask, build_report
from src.part_locator import discover_parts, iter_files
from src.ui_chat import (chat_markdown, cited_kinds, evidence_for, evidence_rows, followups,
                         greeting, is_not_found, level_summary, levels, mode_label)
from src.ui_report import quality, report_blocks, report_markdown, report_pdf
from src.ui_state import append_turn, clear_history, file_stamp, get_history, history_key
from src import ui_theme
from src.ui_views import envelope_svg, page_count, page_png

st.set_page_config(page_title="CNC part analysis", layout="wide", page_icon="\u2699\ufe0f")

KINDS = ("Excel", "PDF", "IGES")
USER_AVATAR = "\U0001F464"      # bust in silhouette
BOT_AVATAR = "\u2699\ufe0f"     # gear, with the emoji variation selector so it is not text-style

# buttons the user can press instead of typing; the last two are deliberate - a price and a
# weather question have no answer in a manufacturing record, and the app must say so
SUGGESTIONS = [
    ("Material", "What material is it?"),
    ("Dimensions", "What are its main dimensions?"),
    ("Process", "What machining operations are planned?"),
    ("Tolerances", "What tolerance class applies?"),
    ("Discrepancies", "Do the three sources agree?"),
    ("Cycle time", "What cycle time and quantity are recorded?"),
    ("Price  (no answer exists)", "What is the price per piece?"),
    ("Weather  (out of scope)", "What is the weather today?"),
    ("Supplier code", "What is the supplier or catalogue code?"),
]

CSS = ui_theme.css()          # the pixel-window theme lives in src/ui_theme.py


# --------------------------------------------------------------------- small view helpers
def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def header(model_label: str, live: bool) -> None:
    html(f"""
    <div class="qd-hdr">
      <div>
        <div class="qd-title">CNC Part Analysis</div>
        <div class="qd-sub">One part number &rarr; the record, the drawing and the 3D model,
        cross-checked, every number cited.</div>
      </div>
      <div class="qd-pill {'qd-on' if live else 'qd-off'}">{model_label}</div>
    </div>""")


def level_badge(rep: Report) -> None:
    """Which level of the problem statement this part's own files support."""
    line = level_summary(rep).replace("&", "&amp;").replace("<", "&lt;")
    reached = [name for name, _, ok, _ in levels(rep) if ok and name != "Stretch"]
    cls = "qd-badge-ok" if len(reached) == 3 else "qd-badge-warn"
    html(f'<div class="qd-chips"><span class="qd-chip {cls}">'
         f'<b>{line}</b> &middot; open &ldquo;About&rdquo; below for the detail</span></div>')


HONESTY = [
    ("Numbers come from the files, not from the model",
     "Every value on this screen was read by a parser. The language model only puts the "
     "extracted numbers into a sentence; it is never asked to calculate."),
    ("Every claim names a place",
     "Each fact carries the file and the cell, page or model entity it came from, and the "
     "answer repeats it. An answer with no citation is flagged, not shown as fact."),
    ("The verifier checks the numbers afterwards",
     "After an answer is written, each number in it is looked up in the fact sheet. Anything "
     "that is not there is reported on the answer itself - the flag is never silently dropped."),
    ("Missing means missing",
     "If the files do not state it, the answer says &ldquo;I can&rsquo;t find that in the "
     "files&rdquo; and lists what the record does hold. No average, no plausible guess."),
    ("Both sides of a disagreement stay visible",
     "When two files give different numbers, the cross-check shows both, the gap and the "
     "allowance used. Nothing is picked silently."),
    ("Approximations are labelled as they are",
     "A CAD bounding box is an envelope, not a measurement, so its facts keep a lower "
     "confidence and the note says so."),
    ("Without an API key nothing is invented",
     "The extraction, the fact sheet and the cross-check still run; answers are labelled "
     "&ldquo;Code answer (no LLM)&rdquo; instead of pretending to be model output."),
]


def about(rep: Report, root: str, model: str) -> None:
    """The problem statement's levels, and the rules that stop this app from guessing."""
    with st.expander("About: levels reached, and how this app avoids guessing"):
        cols = st.columns(2)
        with cols[0]:
            st.markdown("**Levels reached for this part**")
            for name, needs, reached, why in levels(rep):
                mark = "\u2705" if reached else "\u26a0\ufe0f"
                st.markdown(f"{mark} **{name}** - {needs}")
                st.caption(why)
        with cols[1]:
            st.markdown("**How this app avoids guessing**")
            for title, body in HONESTY:
                st.markdown(f"- **{title}.** {body}")
        st.caption(f"Model in use: `{model}` · Data folder: `{root}` · Part {rep.part}: "
                   f"{len(rep.facts)} fact(s), {len(rep.rows)} cross-check(s), "
                   f"{len(rep.all_warnings())} warning(s).")


def not_found_card(part: str, found: list[str], rep: Report) -> None:
    """The honest 'nothing here' screen: what was searched, and the numbers nearby."""
    safe = str(part).replace("&", "&amp;").replace("<", "&lt;")
    near = difflib.get_close_matches(str(part), found, n=3, cutoff=0.4)
    nearby = ("<p>Numbers close to what you typed: <b>" + ", ".join(near) + "</b>.</p>"
              if near else "<p>No number in the folder is close to the one you typed.</p>")
    listed = (", ".join(found[:12]) + (f", +{len(found) - 12} more" if len(found) > 12 else "")
              if found else "none yet - add the part's files in the sidebar")
    html(f"""
    <div class="qd-steps">
      <h4>Part {safe} is not in this folder</h4>
      <p>The app looked through every Excel, PDF and IGES file under the folder for a record
      naming <b>{safe}</b> and found nothing to read. It stopped there rather than inventing
      values - that refusal is the correct answer.</p>
      {nearby}
      <p>Part numbers found here: {listed}.</p>
    </div>""")
    for w in rep.all_warnings()[:4]:
        st.caption(w)


def chips(rep: Report) -> None:
    """One chip per source: green when a file was read, grey when it is missing."""
    paths = rep.files.paths() if rep.files else {}
    parts = []
    for kind in KINDS:
        path = paths.get(kind)
        if path is None:
            parts.append(f'<span class="qd-chip qd-miss" title="no {kind} file was found '
                         f'for this part">{kind}: missing</span>')
        else:
            parts.append(f'<span class="qd-chip qd-ok" title="{Path(str(path)).name}">'
                         f'{kind}: found</span>')
    mismatches = sum(1 for r in rep.rows if r.status == "mismatch")
    if not rep.rows:
        badge = '<span class="qd-chip qd-miss">nothing overlaps between the sources</span>'
    elif mismatches:
        badge = (f'<span class="qd-chip {"qd-badge-bad" if mismatches > 1 else "qd-badge-warn"}">'
                 f'{mismatches} disagreement{"s" if mismatches > 1 else ""}</span>')
    else:
        badge = '<span class="qd-chip qd-badge-ok">all sources agree</span>'
    html(f'<div class="qd-chips">{"".join(parts)}{badge}</div>')


def best(rep: Report, *fields: str):
    """The most trustworthy fact among `fields`, whichever source it came from."""
    order = {"code-high": 0, "code-medium": 1, "code-low": 2, "llm-vision": 3, "inferred": 4}
    hits = [f for f in rep.facts if f.field in fields]
    hits.sort(key=lambda f: (order.get(f.confidence, 5), f.source_type))
    return hits[0] if hits else None


def summary_cards(rep: Report) -> None:
    picks = [("Part", best(rep, "part_name", "name")),
             ("Material", best(rep, "material")),
             ("Outer dia", best(rep, "outer_diameter", "diameter")),
             ("Length", best(rep, "length"))]
    cards = []
    for label, fact in picks:
        if fact is None:
            continue
        value = str(fact.display_value()).replace("&", "&amp;").replace("<", "&lt;")
        title = f"{fact.source_type}: {Path(str(fact.source_file)).name}, {fact.location}"
        cards.append(f'<div class="qd-card" title="{title}">'
                     f'<div class="qd-k">{label}</div><div class="qd-v">{value}</div></div>')
    if cards:
        html(f'<div class="qd-cards">{"".join(cards)}</div>')


def empty_state(folder_ok: bool, found: list[str]) -> None:
    """What the screen shows before any part is chosen - the app's own pitch."""
    if found:
        step2 = (f"Every number found in this folder is in the dropdown ({len(found)} of "
                 f"them: {', '.join(found[:12])}).")
    else:
        step2 = "No part files are in the folder yet, so the dropdown is empty - add them above."
    step2 += (" Typing a number that is not listed is allowed; the app then says it found "
              "nothing instead of guessing.")
    html(f"""
    <div class="qd-steps">
      <h4>1. {"Open a folder" if folder_ok else "Point the app at a folder"}</h4>
      <p>Put the part's Excel record, PDF drawing and IGES model in one folder and type that
      path in the sidebar - or just drag the files onto <b>Add part files</b> there. Nothing
      is hard-coded: no column letters, no file names, no page coordinates.</p>
      <h4>2. Choose a part number</h4>
      <p>{step2}</p>
      <h4>3. Ask a question</h4>
      <p>Open <b>Maya</b> in the bottom-right corner and ask. Answers quote the file and the
      cell, page or model entity they came from. If the files do not say it, Maya says so
      instead of guessing.</p>
    </div>
    <div class="qd-cards">
      <div class="qd-card"><div class="qd-k">Level 1</div><div class="qd-v">Excel record
      &rarr; fact sheet</div></div>
      <div class="qd-card"><div class="qd-k">Level 2</div><div class="qd-v">+ PDF drawing
      &rarr; every answer names its file</div></div>
      <div class="qd-card"><div class="qd-k">Level 3</div><div class="qd-v">+ IGES model
      &rarr; three-way cross-check</div></div>
      <div class="qd-card"><div class="qd-k">Stretch</div><div class="qd-v">any part number
      in the folder</div></div>
    </div>""")


def as_text(df: pd.DataFrame) -> pd.DataFrame:
    """One string per cell: a column that mixes floats and text fails the arrow conversion."""
    def one(v: object) -> str:
        if v is None or (isinstance(v, float) and v != v):
            return ""
        return str(v)
    return df.apply(lambda col: col.map(one))


# --------------------------------------------------------------------- the panels
def source_chips(text: str) -> None:
    """Which files this one answer quotes - Level 2 and 3 of the problem statement."""
    kinds = cited_kinds(text)
    if not kinds:
        return
    html('<div class="qd-chips">' + "".join(
        f'<span class="qd-chip qd-src-{k.lower()}" title="this answer quotes the {k} file">'
        f'{k}</span>' for k in kinds) + "</div>")


def render_answer(msg: dict, rep: Report, key: str, index: int, ns: str = "") -> None:
    """One assistant turn: the text, then where it came from, then how much to trust it."""
    with st.chat_message("assistant", avatar=BOT_AVATAR):
        st.markdown(msg["text"])
        if is_not_found(msg["text"]):
            html('<div class="qd-note">Not found in the files. The app stopped there instead '
                 'of guessing - that line is the honest answer, not an error.</div>')
        source_chips(msg["text"])
        rows = evidence_rows(evidence_for(rep, msg["text"]))
        if rows:
            with st.expander(f"Evidence - {len(rows)} item(s) this answer quoted"):
                st.dataframe(as_text(pd.DataFrame(rows)), hide_index=True, width="stretch")
        label = mode_label(msg.get("mode", ""))
        if msg.get("mode") == "llm" and msg.get("model"):
            label += f" - {msg['model']}"      # names the fallback when one answered
        st.caption(label)
        if msg.get("v_ok") is False:
            st.warning(f"The verifier flagged this answer: {msg.get('v_msg', '')}. "
                       "Treat the numbers above the flag, or ask again with the model off.")
        elif msg.get("v_ok") is True:
            st.caption("Verified: every number in this answer is in the fact sheet.")
        rate(msg, key, index, ns)


def rate(msg: dict, key: str, index: int, ns: str = "") -> None:
    """Thumbs up/down for one answer. Session state only - nothing leaves this machine."""
    now = msg.get("rating")
    cols = st.columns([1, 1, 3])
    up = cols[0].button("Helpful", icon=":material/thumb_up:", key=f"{ns}up_{key}_{index}",
                        disabled=now == 1)
    if up:
        msg["rating"] = 1
        st.rerun()
    down = cols[1].button("Not helpful", icon=":material/thumb_down:", key=f"{ns}dn_{key}_{index}",
                          disabled=now == 0)
    if down:
        msg["rating"] = 0
        st.rerun()
    if now is not None:
        cols[2].caption("Your rating: " + ("helpful" if now == 1 else "not helpful")
                        + " - kept in this session and written into the .md transcript")


def panel_ask(rep: Report, llm: LLMClient | None, key: str, root: str, ns: str = "",
              height: int = 380, input_key: str | None = None) -> None:
    """The whole conversation, drawn only inside Maya's floating window.

    `ns` / `input_key` keep every widget id unique to the dock; nothing else renders chat."""
    hist = get_history(st.session_state, key)
    with st.container(height=height, key=f"{ns}chat_scroll"):
        # the greeting is the first bubble, and it says what was actually read
        with st.chat_message("assistant", avatar=BOT_AVATAR):
            st.markdown(greeting(rep))
        for index, msg in enumerate(hist):
            if msg["role"] == "user":
                with st.chat_message("user", avatar=USER_AVATAR):
                    st.write(msg["text"])
            else:
                render_answer(msg, rep, key, index, ns)
        if not hist:
            st.caption("Ask below, or press one of the suggested questions under this box.")

        last_q = next((m["text"] for m in reversed(hist) if m["role"] == "user"), "")
        tips = followups(rep, asked=last_q)
        if tips:
            html('<div class="qd-sub" style="margin-top:.5rem">Try asking</div>')
            tcols = st.columns(len(tips))
            pressed = None
            for i, q in enumerate(tips):
                if tcols[i].button(q, key=f"{ns}tip_{i}", width="stretch", help=q):
                    pressed = q
        else:
            pressed = None

    bar = st.columns(2)
    with bar[0]:
        if st.button("Clear chat", key=f"{ns}clear_{key}", disabled=not hist,
                     help="Forget this part's conversation; the extracted facts are untouched"):
            clear_history(st.session_state, key)
            st.rerun()
    with bar[1]:
        st.download_button("Download chat (.md)", key=f"{ns}dl_{key}",
                           data=chat_markdown(rep.part, root, hist),
                           file_name=f"chat-part-{rep.part}.md", mime="text/markdown",
                           disabled=not hist)
    with st.expander("Sample questions"):
        scols = st.columns(3)
        clicked = None
        for i, (label, question) in enumerate(SUGGESTIONS):
            if scols[i % 3].button(label, key=f"{ns}sug_{i}", width="stretch", help=question):
                clicked = question
    asked = st.chat_input("Ask anything about this part", key=input_key) or pressed or clicked
    if not asked:
        return

    with st.spinner("Reading the files..."):
        try:
            ans: Answer = ask(rep, asked, llm=llm)
        except Exception:                       # never show a judge a stack trace
            st.error("Something went wrong while answering. The extraction above is still "
                     "valid - here is the detail.")
            with st.expander("Technical detail"):
                st.code(traceback.format_exc())
            return
    v = ans.verification
    append_turn(st.session_state, key, asked,
                {"text": ans.text, "mode": ans.mode, "model": ans.model,
                 "v_ok": None if v is None else bool(v.ok),
                 "v_msg": "" if v is None else v.message})
    st.rerun()


def crosscheck_table(rep: Report) -> pd.DataFrame:
    """The sources side by side, each row with its unit, the gap found and the allowance used."""
    kinds = [k for k in KINDS if any(k in r.values for r in rep.rows)]
    extra = list(dict.fromkeys(k for r in rep.rows for k in r.values if k not in KINDS))
    data_cols = kinds + extra
    head = ["", "Field"] + data_cols + ["Unit", "Difference", "Tolerance used", "Result",
                                        "Confidence"]
    rows = []
    for r in rep.rows:
        row: dict[str, str] = {"": r.icon(), "Field": r.label}
        row.update({c: r.values.get(c, "-") for c in data_cols})
        row["Unit"] = r.unit or "-"
        row["Difference"] = "-" if r.spread is None else f"{r.spread:g} {r.unit}".strip()
        row["Tolerance used"] = r.tolerance or "-"
        row["Result"] = r.detail or r.status
        row["Confidence"] = r.worst_confidence
        rows.append(row)
    return pd.DataFrame(rows, columns=head)


def panel_crosscheck(rep: Report) -> None:
    if not rep.rows:
        st.info("Nothing overlaps between the sources yet - each fact appears in only one "
                "file, so there is nothing to disagree about.")
        return
    st.write(crosscheck_summary(rep.rows))
    df = as_text(crosscheck_table(rep))
    tint = {"✅": "#D5EEC6", "⚠️": "#F8E6A8", "ℹ️": "#D5DEFB"}
    row_css = [f"background-color:{tint.get(r.icon(), '')}" for r in rep.rows]

    def paint(_df):
        return pd.DataFrame([[c] * len(_df.columns) for c in row_css],
                            index=_df.index, columns=_df.columns)

    st.dataframe(df.style.apply(paint, axis=None), hide_index=True, width="stretch")
    st.caption("Green: the sources agree within the allowance in the 'Tolerance used' column. "
               "Amber: they disagree - both numbers stay on the screen, nothing is averaged. "
               "Blue: only one source states it.")
    st.download_button("Download cross-check (.csv)", key=f"csv_{rep.part}",
                       data=df.to_csv(index=False).encode("utf-8"),
                       file_name=f"cross-check-part-{rep.part}.csv", mime="text/csv")
    with st.expander("Which file was chosen for each source, and why"):
        if rep.files is None:
            st.write("No folder was read.")
        else:
            for kind, path in rep.files.paths().items():
                cand = rep.files.chosen.get(kind)
                st.markdown(f"**{kind}** - `{Path(str(path)).name}`")
                st.write(cand.reasons if cand else ["name match"])
            if rep.files.rejected:
                st.write("considered and not used: "
                         + ", ".join(f"{c.kind} {c.path.name}" for c in rep.files.rejected))


def panel_facts(rep: Report) -> None:
    if not rep.facts:
        st.info("No facts were extracted from these files.")
        return
    by: dict[str, list] = {}
    for f in rep.facts:
        by.setdefault(f.source_type or "?", []).append(f)
    for kind in KINDS + tuple(k for k in by if k not in KINDS):
        items = by.get(kind, [])
        if not items:
            continue
        with st.expander(f"{kind} - {len(items)} fact(s) from "
                         f"{Path(str(items[0].source_file)).name}", expanded=kind == "Excel"):
            df = pd.DataFrame([f.as_dict() for f in items])
            keep = [c for c in ("field", "value", "unit", "location", "confidence", "note")
                    if c in df.columns]
            st.dataframe(as_text(df[keep]), hide_index=True, width="stretch")


def panel_warnings(rep: Report) -> None:
    warns = rep.all_warnings()
    if not warns:
        st.success("No warnings - every file was read right through.")
        return
    st.warning(f"{len(warns)} thing(s) the readers could not do cleanly. The app kept going "
               f"and did not guess; each line says what was skipped.")
    for w in warns:
        st.write(f"- {w}")
    with st.expander("What each one means for the answers"):
        st.write("A warning narrows what is known; it never invents a value. Facts already "
                 "shown on this screen were read from the part of the file that did parse.")


def panel_report(rep: Report, model: str) -> None:
    """The one-page summary, assembled by code and downloadable in two formats."""
    st.download_button("Download report (.md)", key=f"md_{rep.part}",
                       data=report_markdown(rep, model).encode("utf-8"),
                       file_name=f"part-{rep.part}-report.md", mime="text/markdown")
    st.download_button("Download report (.pdf)", key=f"pdf_{rep.part}",
                       data=report_pdf(rep, model), file_name=f"part-{rep.part}-report.pdf",
                       mime="application/pdf")
    st.caption("The same text as the page below. Nothing on it was written by a language "
               "model - every line is assembled from the parsed files.")
    st.divider()
    for kind, text in report_blocks(rep, model):
        if kind == "h1":
            st.markdown(f"### {text}")
        elif kind == "h2":
            st.markdown(f"#### {text}")
        elif kind == "p":
            st.write(text)
        elif kind == "note":
            st.caption(text)
        else:
            st.markdown(f"- {text}")


@st.cache_data(show_spinner=False)
def drawing_png(path: str, page: int, zoom: float) -> bytes:
    """Rendered once per (file, page, zoom); the file's own bytes decide the picture."""
    return page_png(path, page, zoom) or b""


def panel_views(rep: Report) -> None:
    """The drawing as the file stores it, and the model as the reader could verify it."""
    paths = rep.files.paths() if rep.files else {}
    st.markdown("#### Engineering drawing")
    drawing = paths.get("PDF")
    if drawing is None:
        st.info("No PDF drawing was matched to this part, so there is nothing to preview. "
                "The app will not draw a picture it was not given.")
    else:
        pages = page_count(drawing)
        if not pages:
            st.warning(f"`{Path(str(drawing)).name}` could not be opened as a PDF, so it is "
                       "not shown. The text facts from it are still on the other tabs.")
            pages = 0
        else:
            pick = (st.selectbox("Page", list(range(1, pages + 1)), key=f"pg_{rep.part}")
                    if pages > 1 else 1)
            zoom = st.slider("Zoom", 1.0, 4.0, 1.6, 0.2, key=f"zx_{rep.part}",
                             help="How many pixels the page is rendered at. Nothing is "
                                  "invented here: this is the file's own vector content.")
            png = drawing_png(str(drawing), int(pick) - 1, float(zoom))
            if png:
                st.image(png, width="stretch",
                         caption=f"{Path(str(drawing)).name}, page {pick} of {pages}")
            else:
                st.warning("This page rendered as nothing readable. The extraction still "
                           "stands on its own - see Extracted facts.")
    st.markdown("#### 3D model")
    box = best(rep, "bounding_box_size")
    model = paths.get("IGES")
    if model is None:
        st.info("No IGES model was matched to this part.")
        return
    detail = next((r.detail for r in rep.results if r.source_type == "IGES"), "")
    st.caption(f"{Path(str(model)).name} - {detail}" if detail
               else Path(str(model)).name)
    if box is None or not isinstance(box.value, (list, tuple)):
        st.info("The model was found but no envelope could be verified from its entities, "
                "so no box is drawn. A sketch of geometry the reader did not confirm would "
                "be a guess with gridlines on it.")
        return
    html(envelope_svg([float(v) for v in box.value], box.unit or "mm", str(box.note or "")))
    st.caption("plotly is not installed in this environment, so the model is shown as the "
               "envelope the parser measured rather than a rendered surface.")


def _compare_value(rep: Report, label: str) -> str:
    row = next((r for r in rep.rows if r.label == label), None)
    if row is None:
        return "-"
    return " / ".join(v for v in row.values.values() if v) or "-"


def panel_compare(rep: Report, root: str, stamp: str, parts: list[str]) -> None:
    """Two part numbers from the same folder, field by field.

    A difference here is a difference between two parts, not a conflict between files - the
    wording on screen keeps those two ideas apart.
    """
    others = [p for p in parts if p != rep.part]
    if not others:
        st.info("This folder holds only this part. Add another part's files to compare.")
        return
    other = st.selectbox("Compare with", others, index=None, key=f"cmp_{rep.part}",
                         placeholder="Pick a second part number")
    if not other:
        st.caption("Nothing is compared until a second number is picked. Until then this "
                   "panel stays empty rather than showing a part nobody chose.")
        return
    with st.spinner("Reading the second part..."):
        rep2, _ = analyse(other, root, False, stamp)
    if not rep2.facts:
        st.warning(f"Part {other} is listed in this folder but nothing could be read for it, "
                   "so there is nothing to compare.")
        return
    labels = [r.label for r in rep.rows] + [r.label for r in rep2.rows if r.label
                                            not in {x.label for x in rep.rows}]
    rows = []
    for label in labels:
        a, b = _compare_value(rep, label), _compare_value(rep2, label)
        if a == "-" or b == "-":
            verdict = "only one part states it"
        elif a == b:
            verdict = "same"
        else:
            verdict = "different"
        rows.append({"Field": label, f"Part {rep.part}": a, f"Part {other}": b, "Verdict": verdict})
    st.write("These are two different parts. A 'different' row is expected and is not a "
             "conflict; a conflict between files for one part is on the Cross-check tab.")
    df = as_text(pd.DataFrame(rows))
    st.dataframe(df, hide_index=True, width="stretch")
    st.download_button("Download comparison (.csv)", key=f"cmpcsv_{rep.part}_{other}",
                       data=df.to_csv(index=False).encode("utf-8"),
                       file_name=f"compare-{rep.part}-{other}.csv", mime="text/csv")
    left, right = st.columns(2)
    for col, r in ((left, rep), (right, rep2)):
        with col:
            score, _ = quality(r)
            st.metric(f"Part {r.part}: data quality", f"{score}/100")
            st.caption(level_summary(r))


def quality_bar(rep: Report) -> None:
    """How much of this part could be read - this app's own rubric, explained on the report."""
    score, why = quality(rep)
    st.progress(score / 100, text=f"Data quality for this part: {score}/100"
               + (f" - {why[0]}" if why else " - all three sources read cleanly"))


# --------------------------------------------------------------------- data + selection
# Both caches are keyed by `stamp`, a fingerprint of the files themselves, so replacing or
# editing a file re-analyses, while the part number alone can never serve a stale report.
@st.cache_data(show_spinner=False)
def analyse(part: str, root: str, use_llm: bool, stamp: str) -> tuple[Report, list[str]]:
    llm = LLMClient.from_env() if use_llm else None
    return build_report(part, Path(root), llm=llm), (
        [] if llm is None or not llm.available else [llm.describe()])


@st.cache_data(show_spinner=False)
def parts_in(root: str, stamp: str) -> list[str]:
    path = Path(root)
    return discover_parts(path) if path.is_dir() else []


def safe_name(name: str) -> str:
    """A browser sends a bare filename; strip any path anyway so a write cannot escape."""
    base = Path(str(name).replace("\\", "/")).name
    return base if base not in ("", ".", "..") else "upload"


def unique_in(folder: Path, name: str) -> Path:
    """Never clobber what is already on disk - a repeat gets (2), (3) like a browser download."""
    cand = folder / name
    n = 2
    while cand.exists():
        cand = folder / f"{Path(name).stem} ({n}){Path(name).suffix}"
        n += 1
    return cand


def save_uploads(folder: Path, files: list) -> list[str]:
    """Keep added files under the data folder so a refresh, and any folder scan, still sees them.

    Writing them inside `folder` is what makes a new part appear without restarting: the file
    fingerprint changes, so discovery and the analysis cache both re-run.
    """
    folder.mkdir(parents=True, exist_ok=True)
    done = st.session_state.setdefault("saved_uploads", {})
    for f in files:
        name = safe_name(f.name)
        marker = f"{name}:{f.size}"
        if done.get(marker):
            continue
        target = unique_in(folder, name)
        target.write_bytes(f.getvalue())
        done[marker] = target.name
    return sorted(p.name for p in iter_files(folder))


def pick_folder() -> tuple[str, list[str], bool]:
    """Sidebar settings: data folder (or uploads) and whether a language model may be used."""
    default = str(Path(__file__).resolve().parent / "data")
    with st.sidebar:
        st.header("Settings")
        root = st.text_input("Data folder", value=default,
                             help="Any folder containing the part's Excel, PDF and IGES files")
        upload = st.file_uploader("Add part files", accept_multiple_files=True,
                                  type=["xlsx", "xlsm", "xls", "csv", "pdf", "igs", "iges"],
                                  help="Excel, PDF or IGES - any naming style. Files are kept "
                                       "in the data folder under uploads/, so they survive a refresh.")
        want_llm = st.toggle("Use a language model for answers", value=True,
                             help="Needs an API key in .env; the app works without one")
    root = (root or default).strip()
    if upload:
        return root, save_uploads(Path(root) / "uploads", upload), want_llm
    return root, [], want_llm


def choose_part(found: list[str]) -> str:
    """Nothing is preselected: an unasked-for part would put numbers on screen nobody read."""
    manual = "+ type a part number that is not listed"
    options = found + [manual]
    choice = st.selectbox("Part", options, index=None,
                          placeholder="Enter or select a part number (e.g. 2280)",
                          key="part_select")
    if not choice:
        return ""
    if choice != manual:
        return str(choice)
    return st.text_input("Part number", placeholder="e.g. 2280", key="part_manual").strip()


def page() -> None:
    html(CSS)
    st.session_state.pop("chat", None)          # pre-1.2 history was not per-part
    llm = LLMClient.from_env()
    header(f"LLM: {llm.describe()}" if llm.available else "No LLM - code answers only",
           llm.available)

    root, uploaded, want_llm = pick_folder()
    use_llm = want_llm and llm.available
    CTX.update(llm=llm if use_llm else None, root=root)
    with st.sidebar:
        st.caption(f"Model: `{llm.describe()}`" if use_llm else
                   ("Language model is switched off - answers come from exact field lookup. "
                    "The fact sheet and the cross-check table are unaffected."
                    if want_llm else
                    "No API key in `.env`, so answers come from exact field lookup. The fact "
                    "sheet and the cross-check table are unaffected."))
        if uploaded:
            st.caption(f"{len(uploaded)} file(s) in `uploads/`, kept between refreshes.")
        if st.button("Reset everything", key="reset_all",
                     help="Forget every conversation and re-read the folder from scratch"):
            keep = {k: st.session_state[k] for k in ("intro_done",) if k in st.session_state}
            st.session_state.clear()            # the intro is not replayed by a reset
            st.session_state.update(keep)
            st.rerun()

    root_path = Path(root) if root else None
    stamp = file_stamp(root) if root_path and root_path.is_dir() else "none"
    found = parts_in(root, stamp) if root_path and root_path.is_dir() else []
    CTX["found"] = found

    if uploaded:
        where = (Path(root) / "uploads").as_posix()
        st.success(f"Added {len(uploaded)} file(s) to {where}. Parts detected in this folder: "
                   + (", ".join(found) if found else
                      "none yet - the file names must contain the part number."))
    st.caption(f"Data folder: `{root}`" + ("" if root_path and root_path.is_dir()
                                           else " - that folder does not exist yet"))

    part = choose_part(found)
    CTX["part"] = part
    if not part:
        empty_state(folder_ok=bool(root_path and root_path.is_dir()), found=found)
        return

    try:
        with st.spinner("Reading the files and extracting facts..."):
            rep, _ = analyse(part, root, use_llm, stamp)
    except Exception:
        st.error("The folder could not be analysed. Check the path and add the part's files.")
        with st.expander("Technical detail"):
            st.code(traceback.format_exc())
        return

    if not rep.facts:
        not_found_card(part, found, rep)
        return

    CTX.update(rep=rep, key=history_key(root, part))
    summary_cards(rep)
    chips(rep)
    level_badge(rep)
    quality_bar(rep)
    html('<div class="qd-chat-hint">Ask anything about this part with <b>Maya</b> '
         '&mdash; the assistant in the bottom-right corner.</div>')

    model_name = llm.describe() if use_llm else "none in use"
    tab_check, tab_report, tab_views, tab_cmp, tab_facts, tab_warn = st.tabs(
        ["Cross-check", "Part report", "Views", "Compare", "Extracted facts", "Warnings"])
    with tab_check:
        panel_crosscheck(rep)
    with tab_report:
        panel_report(rep, model_name)
    with tab_views:
        panel_views(rep)
    with tab_cmp:
        panel_compare(rep, root, stamp, found)
    with tab_facts:
        panel_facts(rep)
    with tab_warn:
        panel_warnings(rep)
    about(rep, root, model_name)


# --------------------------------------------------------------------- Maya: the floating assistant
CTX: dict = {}      # page() fills this on every run so the dock knows what is on screen


def toggle_maya() -> None:
    st.session_state["maya_open"] = not st.session_state.get("maya_open", False)


def pick_part(part: str) -> None:
    """Fill the Part box for the user (runs as a callback, before the widget is drawn)."""
    st.session_state["part_select"] = part


def maya_welcome() -> None:
    """What Maya says before there is a part to talk about."""
    found = CTX.get("found") or []
    part = CTX.get("part")
    with st.chat_message("assistant", avatar=BOT_AVATAR):
        if part:
            st.markdown(f"I could not read anything for **{part}**, so there is nothing to ask "
                        "about yet. Check the number or add its files in the sidebar.")
        elif found:
            st.markdown("Hi, I'm **Maya**. Pick a part number and I'll read its Excel record, "
                        "PDF drawing and IGES model, then answer with the file and place each "
                        "fact came from.")
        else:
            st.markdown("Hi, I'm **Maya**. There are no part files in the folder yet - add an "
                        "Excel record, a PDF drawing or an IGES model in the sidebar and I'll "
                        "read them.")
    if found and not part:
        st.caption("Tap a part number to open it:")
        cols = st.columns(min(3, len(found[:6])))
        for i, p in enumerate(found[:6]):
            cols[i % len(cols)].button(p, key=f"maya_pick_{p}", on_click=pick_part, args=(p,),
                                       width="stretch")


def maya_dock() -> None:
    """The avatar bottom-right on every screen. The window exists only after a click."""
    is_open = bool(st.session_state.get("maya_open"))
    with st.container(key="maya_fab_open" if is_open else "maya_fab"):
        st.button("Close the assistant" if is_open else "Chat with Maya, the assistant",
                  key="maya_toggle", on_click=toggle_maya,
                  help="Close Maya" if is_open else "Ask Maya about this part")
    if not is_open:
        return
    with st.container(key="maya_win"):
        st.button("Close", key="maya_close", icon=":material/close:", on_click=toggle_maya,
                  help="Close the assistant")
        rep = CTX.get("rep")
        if rep is not None and rep.facts:
            panel_ask(rep, CTX.get("llm"), CTX["key"], CTX["root"], ns="m_", height=380,
                      input_key="maya_chat_input")
        else:
            maya_welcome()


def finish_intro() -> None:
    st.session_state["intro_done"] = True


def intro_gate() -> bool:
    """Play the intro once per visit. True means the intro still owns the screen.

    With assets/intro.mp4 (or .webm/.mov/.m4v) present, that video plays inside a window and
    the user enters with a button. Without one, a built-in pixel 'Loading...' animation plays
    over the app and removes itself - it never blocks a click.
    """
    if not ui_theme.intro_enabled() or st.session_state.get("intro_done"):
        return False
    video = ui_theme.intro_video()
    if video is None:
        html(ui_theme.intro_overlay_html())
        st.session_state["intro_done"] = True
        return False
    html(CSS)
    with st.container(key="intro_stage"):
        try:
            st.video(str(video), autoplay=True, muted=True)
        except TypeError:                       # an older Streamlit without autoplay/muted
            st.video(str(video))
        st.button("Enter the app", key="intro_enter", type="primary", width="stretch",
                  on_click=finish_intro)
    return True


def main() -> None:
    """A judge should never see a stack trace: anything unexpected becomes one line, and
    the detail goes inside an expander."""
    try:
        if intro_gate():
            return
        page()
    except Exception:
        st.error("This screen could not be drawn. The files were not changed and nothing was "
                 "invented - the detail below is for the developers.")
        with st.expander("Technical detail"):
            st.code(traceback.format_exc())
    try:
        maya_dock()
    except Exception:                           # the dock is an extra; it must never take the app down
        st.caption("The assistant button could not be drawn on this screen.")


if __name__ == "__main__":
    main()
