"""Look and feel: the pixel-window theme, the intro animation and Maya's floating dock.

Paint only. Nothing in this module reads a part, a file or a model answer, so it cannot change
what the app says - it only changes how the screen is dressed.

Palette (sampled from the reference picture):
    lavender grid #DEE5FF  cream window #F7E3CB  ink #442C2C   teal #7ABBB5   orange #E07F32
    yellow #E8C561         pink #F183B4          red #D95A61   green #9AD277  blue #8BA1EC
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from src import ui_avatar

ROOT = Path(__file__).resolve().parent.parent
VIDEO_NAMES = ("intro.mp4", "intro.webm", "intro.mov", "intro.m4v")


# ---------------------------------------------------------------- tiny pixel icons
_ICON_PAL = {"R": "#D95A61", "Y": "#E8C561", "O": "#E07F32", "W": "#FFFFFB", "K": "#442C2C",
             "P": "#F183B4", "T": "#7ABBB5"}
_ICONS = {
    "heart": [".RR...RR.", "RWRR.RRRR", "RRRRRRRRR", "RRRRRRRRR", ".RRRRRRR.", "..RRRRR..",
              "...RRR...", "....R...."],
    "star": ["....Y....", "....Y....", "...YYY...", "..YYWYY..", "YYYYWYYYY", "..YYYYY..",
             "...YYY...", "....Y....", "....Y...."],
    "mail": ["YYYYYYYYYY", "YOYYYYYYOY", "YYOYYYYOYY", "YYYOOOOYYY", "YYYYYYYYYY", "YYYYYYYYYY"],
    "gem": ["..PPPP..", ".PWPPPP.", "PPPPPPPP", ".PPPPPP.", "..PPPP..", "...PP..."],
}


def pixel_icon(name: str) -> str:
    """A small pixel-art icon (ink outline included) as an SVG data URI."""
    rows = _ICONS[name]
    h, w = len(rows), max(len(r) for r in rows)
    pad = [["."] * (w + 2) for _ in range(h + 2)]
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            pad[y + 1][x + 1] = ch
    out = [row[:] for row in pad]
    for y in range(h + 2):
        for x in range(w + 2):
            if pad[y][x] == ".":
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w + 2 and 0 <= ny < h + 2 and pad[ny][nx] != ".":
                        out[y][x] = "K"
                        break
    rects = "".join(f'<rect x="{x}" y="{y}" width="1" height="1" fill="{_ICON_PAL[c]}"/>'
                    for y, row in enumerate(out) for x, c in enumerate(row) if c != ".")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w + 2} {h + 2}" '
           f'shape-rendering="crispEdges">{rects}</svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


# ---------------------------------------------------------------- the stylesheet
_CSS = r"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@300;400;500;600;700;800&family=Pixelify+Sans:wght@400;600;700&display=swap');

:root {
  --bg:#DEE5FF; --grid:#FFFFFB; --cream:#F7E3CB; --cream-l:#FFF6EA; --ink:#442C2C;
  --teal:#7ABBB5; --teal-d:#4F928C; --teal-l:#CFE6E2; --orange:#E07F32; --yellow:#E8C561;
  --pink:#F183B4; --red:#D95A61; --red-l:#F4A7A9; --green:#9AD277; --blue:#8BA1EC; --blue-l:#C9D5FA;
  --sans:'Sora','Segoe UI',system-ui,-apple-system,sans-serif;
  --px:'Pixelify Sans','Courier New',monospace;
  --mono:'Cascadia Mono','Consolas','Courier New',monospace;
  --hard:4px 4px 0 rgba(68,44,44,.28);
}

/* ---------------------------------------------------------------- type: Sora everywhere,
   except the one main heading, which keeps the pixel face */
.stApp, .stApp * {font-family: var(--sans) !important;}
[data-testid="stIconMaterial"], .material-symbols-rounded, .material-symbols-outlined,
[class*="material-symbols"] {font-family: "Material Symbols Rounded" !important;}
code, pre, kbd, samp, [data-testid="stCode"] * {font-family: var(--mono) !important;}
.qd-title, .qd-title * {font-family: var(--px) !important;}
.qd-intro-title {font-family: var(--px) !important;}

/* ---------------------------------------------------------------- page: lavender graph paper */
.stApp, [data-testid="stAppViewContainer"] {
  background-color: var(--bg);
  background-image: linear-gradient(var(--grid) 2px, transparent 2px),
                    linear-gradient(90deg, var(--grid) 2px, transparent 2px);
  background-size: 30px 30px; background-position: -1px -1px;
}
[data-testid="stMain"] {background: transparent;}
header[data-testid="stHeader"] {background: transparent;}
#MainMenu, footer {visibility: hidden;}
html {font-size: 16px; scroll-behavior: smooth;}
::selection {background: var(--yellow); color: var(--ink);}

/* the app itself is one big window with a teal title bar */
.block-container {
  position: relative; z-index: 2; max-width: 1240px;
  margin: 3.7rem auto 6.5rem !important; padding: 0 2rem 2.2rem !important;
  background: var(--cream); border: 3px solid var(--ink); border-radius: 0;
  box-shadow: 7px 7px 0 rgba(68,44,44,.25);
}
.block-container::before {
  content: "CNC_PART_ANALYSIS.EXE"; display: block; margin: 0 -2rem 1.3rem; padding: .42rem .95rem;
  background: var(--teal); border-bottom: 3px solid var(--ink); color: var(--ink);
  font: 600 .85rem var(--sans); letter-spacing: .08em;
}
.block-container::after {
  content: "_  \25A1  \D7"; position: absolute; top: .42rem; right: .95rem; color: var(--ink);
  font: 600 .85rem var(--sans); letter-spacing: .2em; white-space: pre;
}
@media (max-width: 760px) {
  .block-container {margin: 3.3rem .45rem 6rem !important; padding: 0 1rem 1.5rem !important;
                    box-shadow: 4px 4px 0 rgba(68,44,44,.25);}
  .block-container::before {margin: 0 -1rem 1rem;}
}

/* ---------------------------------------------------------------- header */
.qd-hdr {display: flex; align-items: flex-end; justify-content: space-between; gap: 1rem;
         margin-bottom: 1rem; flex-wrap: wrap;}
.qd-title {font: 700 clamp(1.7rem, 4.2vw, 2.7rem)/1.05 var(--px); color: var(--ink);
           letter-spacing: .02em; text-shadow: 3px 3px 0 var(--pink); text-transform: uppercase;}
.qd-title::before {content: ""; display: inline-block; width: .85em; height: .85em; margin-right: .4em;
                   background: url("__HEART__") center/contain no-repeat; image-rendering: pixelated;
                   vertical-align: -.08em;}
.qd-sub {font-size: .95rem; color: var(--ink); opacity: .85; margin-top: .5rem; max-width: 62ch;}
.qd-pill {font: 600 .82rem var(--sans); padding: .36rem .8rem; white-space: nowrap;
          border: 2px solid var(--ink); box-shadow: 3px 3px 0 rgba(68,44,44,.28); letter-spacing: .03em;}
.qd-on  {background: var(--green); color: var(--ink);}
.qd-off {background: var(--yellow); color: var(--ink);}

/* ---------------------------------------------------------------- mini-window cards */
.qd-cards {display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem;
           margin: .3rem 0 1.1rem;}
.qd-card {background: var(--cream-l); border: 2px solid var(--ink); padding: 0 .85rem .7rem;
          box-shadow: var(--hard); transition: transform .12s ease, box-shadow .12s ease;}
.qd-card::before {content: ""; display: block; height: 11px; margin: 0 -.85rem .6rem;
                  background: var(--teal); border-bottom: 2px solid var(--ink);}
.qd-card:nth-child(4n+2)::before {background: var(--orange);}
.qd-card:nth-child(4n+3)::before {background: var(--pink);}
.qd-card:nth-child(4n+4)::before {background: var(--blue);}
.qd-card:hover {transform: translate(-2px, -2px); box-shadow: 6px 6px 0 rgba(68,44,44,.28);}
.qd-k {font: 600 .74rem var(--sans); text-transform: uppercase; letter-spacing: .08em; opacity: .8;}
.qd-v {font-size: 1.08rem; font-weight: 700; margin-top: .15rem; word-break: break-word;}

/* ---------------------------------------------------------------- chips and badges */
.qd-chips {display: flex; gap: .5rem; flex-wrap: wrap; align-items: center; margin: .2rem 0 .75rem;}
.qd-chip {font: 600 .8rem var(--sans); padding: .24rem .7rem; border: 2px solid var(--ink);
          color: var(--ink); background: var(--cream-l); letter-spacing: .02em;}
.qd-ok, .qd-badge-ok {background: var(--green);}
.qd-miss {background: var(--cream); border-style: dashed; opacity: .9;}
.qd-badge-warn {background: var(--yellow);}
.qd-badge-bad {background: var(--red-l);}
.qd-src-excel {background: var(--green);}
.qd-src-pdf   {background: var(--red-l);}
.qd-src-iges  {background: var(--blue);}

.qd-steps {background: var(--cream-l); border: 2px solid var(--ink); border-left: 10px solid var(--teal);
           padding: .3rem 1.2rem; box-shadow: var(--hard);}
.qd-steps h4 {margin: .8rem 0 .1rem; font: 700 1.05rem var(--sans); letter-spacing: .02em;}
.qd-steps p {margin: 0 0 .6rem; opacity: .9; font-size: .93rem;}
.qd-note {border: 2px solid var(--ink); border-left: 8px solid var(--pink); background: #FFE3EE;
          padding: .5rem .8rem; font-size: .88rem; margin: .35rem 0;}
.qd-chat-hint {display: inline-block; margin: .1rem 0 1rem; padding: .32rem .75rem;
               background: var(--teal-l); border: 2px solid var(--ink); font-size: .84rem;
               box-shadow: 3px 3px 0 rgba(68,44,44,.22);}

/* ---------------------------------------------------------------- headings, text */
h1, h2, h3, h4 {font-family: var(--sans) !important; letter-spacing: .01em;}
a {color: #2F6F9F;}
a:hover {color: var(--orange);}

/* ---------------------------------------------------------------- tabs = window tabs */
div[data-testid="stTabs"] [role="tablist"] {gap: .4rem; border-bottom: 3px solid var(--ink);
                                            flex-wrap: wrap; overflow: visible;}
button[role="tab"] {font-family: var(--sans); font-weight: 600; background: var(--cream-l);
                    border: 2px solid var(--ink); border-bottom: none; border-radius: 0;
                    padding: .45rem 1rem; margin-bottom: -3px; min-height: 2.5rem;
                    transition: background .12s ease;}
button[role="tab"]:hover {background: var(--yellow);}
button[role="tab"][aria-selected="true"] {background: var(--teal);}
button[role="tab"][aria-selected="true"], button[role="tab"][aria-selected="true"] * {color: var(--ink) !important;}
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {display: none;}
button[role="tab"]:focus-visible {outline: 3px solid var(--orange); outline-offset: 2px;}
@media (max-width: 760px) {
  div[data-testid="stTabs"] [role="tablist"] {flex-wrap: nowrap; overflow-x: auto;}
  button[role="tab"] {white-space: nowrap;}
}

/* ---------------------------------------------------------------- buttons = the "OK" button */
.stButton > button, .stDownloadButton > button, [data-testid="stFileUploader"] button {
  position: relative; background: var(--cream-l); color: var(--ink); font: 600 .95rem var(--sans);
  border: 2px solid var(--ink); border-radius: 0; min-height: 2.6rem; letter-spacing: .02em;
  box-shadow: 3px 3px 0 rgba(68,44,44,.3); outline: 2px dotted rgba(68,44,44,.55); outline-offset: -6px;
  transition: transform .1s ease, box-shadow .1s ease, background .1s ease;}
.stButton > button:hover, .stDownloadButton > button:hover, [data-testid="stFileUploader"] button:hover {
  background: var(--yellow); color: var(--ink); border-color: var(--ink);
  transform: translate(-1px, -1px); box-shadow: 4px 4px 0 rgba(68,44,44,.3);}
.stButton > button:active, .stDownloadButton > button:active {
  transform: translate(3px, 3px); box-shadow: 0 0 0 rgba(68,44,44,.3);}
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible {
  outline: 3px solid var(--orange); outline-offset: 3px;}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {background: var(--orange);}
.stButton > button:disabled, .stDownloadButton > button:disabled {
  background: var(--cream); color: rgba(68,44,44,.5); border-color: rgba(68,44,44,.45);
  box-shadow: none; outline-color: transparent;}

/* ---------------------------------------------------------------- inputs */
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="base-input"], textarea {
  background: var(--cream-l) !important; border: 2px solid var(--ink) !important; border-radius: 0 !important;}
[data-baseweb="input"]:focus-within, [data-baseweb="select"]:focus-within > div, textarea:focus {
  box-shadow: 0 0 0 3px var(--yellow) !important; border-color: var(--teal-d) !important;}
[data-testid="stWidgetLabel"] p, label p {font-family: var(--sans); font-weight: 600; letter-spacing: .02em;}
[data-testid="stFileUploaderDropzone"] {background: var(--cream-l); border: 2px dashed var(--ink); border-radius: 0;}

/* ---------------------------------------------------------------- sidebar = a second window */
section[data-testid="stSidebar"] {background: var(--cream); border-right: 3px solid var(--ink);}
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {background: transparent;}
section[data-testid="stSidebar"] h2 {background: var(--teal); border: 2px solid var(--ink); padding: .35rem .7rem !important;
                                     font-size: 1.05rem !important; box-shadow: 3px 3px 0 rgba(68,44,44,.25);}

/* ---------------------------------------------------------------- expanders, alerts, metrics, tables */
[data-testid="stExpander"] details {background: var(--cream-l); border: 2px solid var(--ink); border-radius: 0;
                                    box-shadow: 3px 3px 0 rgba(68,44,44,.25); margin-bottom: .6rem;}
[data-testid="stExpander"] summary {font-family: var(--sans); font-weight: 600; background: var(--teal-l);}
[data-testid="stExpander"] summary:hover {background: var(--yellow);}
[data-testid="stExpander"] details[open] > summary {border-bottom: 2px solid var(--ink);}
[data-testid="stAlert"] {border: 2px solid var(--ink); border-radius: 0; box-shadow: 3px 3px 0 rgba(68,44,44,.2);}
[data-testid="stMetric"] {background: var(--blue-l); border: 2px solid var(--ink); padding: .6rem .9rem;
                          box-shadow: var(--hard);}
[data-testid="stDataFrame"] {border: 2px solid var(--ink); border-radius: 0; box-shadow: 3px 3px 0 rgba(68,44,44,.2);}
[data-testid="stProgress"] [role="progressbar"], [data-testid="stProgress"] [role="progressbar"] > div {
  border-radius: 0 !important;}
[data-testid="stProgress"] [role="progressbar"] {border: 2px solid var(--ink); background: var(--cream-l) !important;}
[data-testid="stProgress"] [role="progressbar"] > div > div {
  background: repeating-linear-gradient(90deg, #8F9FF4 0 11px, transparent 11px 14px) !important;}
[data-testid="stImage"] img {border: 2px solid var(--ink);}

/* ---------------------------------------------------------------- chat */
div[data-testid="stChatMessage"] {background: var(--cream-l); border: 2px solid var(--ink); border-radius: 0;
                                  margin-bottom: .6rem; box-shadow: 3px 3px 0 rgba(68,44,44,.22);}
div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {background: var(--blue-l);}
div[data-testid="stChatMessageContent"] p {margin-bottom: .35rem;}
[data-testid="stChatMessageAvatarAssistant"] {
  background: url("__MAYA_OPEN__") center/cover no-repeat !important; image-rendering: pixelated;
  font-size: 0 !important; color: transparent !important; border-radius: 0 !important;}
[data-testid="stChatMessageAvatarAssistant"] * {display: none !important;}
[data-testid="stChatMessageAvatarUser"] {background: var(--blue) !important; border: 2px solid var(--ink);
                                         border-radius: 0 !important;}
[data-testid="stBottom"], [data-testid="stBottom"] > div {background: transparent !important;}
[data-testid="stChatInput"] {border: 2px solid var(--ink); border-radius: 0; background: var(--cream-l);
                             box-shadow: var(--hard);}
[data-testid="stChatInput"] textarea {box-shadow: none !important; border: 0 !important;}

/* ---------------------------------------------------------------- Maya: floating assistant */
.st-key-maya_fab, .st-key-maya_fab_open {position: fixed !important; right: 22px; bottom: 22px;
  z-index: 1002; width: auto !important; height: auto; margin: 0 !important;}
.st-key-maya_fab button, .st-key-maya_fab_open button {
  width: 88px; height: 88px; min-height: 88px; padding: 0 !important; border: 0 !important;
  border-radius: 0; outline: none; box-shadow: none !important; cursor: pointer;
  background: transparent url("__MAYA_OPEN__") center/contain no-repeat !important;
  image-rendering: pixelated; filter: drop-shadow(4px 4px 0 rgba(68,44,44,.35));
  font-size: 0 !important; color: transparent !important;
  animation: mayaBob 3.2s ease-in-out infinite, mayaBlink 5.5s steps(1, end) infinite;
  transition: filter .15s ease;}
.st-key-maya_fab button *, .st-key-maya_fab_open button * {font-size: 0 !important; color: transparent !important;}
.st-key-maya_fab:hover, .st-key-maya_fab_open:hover {transform: scale(1.08); transition: transform .18s cubic-bezier(.2,1.5,.4,1);}
.st-key-maya_fab:active, .st-key-maya_fab_open:active {transform: scale(.96);}
.st-key-maya_fab button:hover, .st-key-maya_fab_open button:hover {
  filter: drop-shadow(4px 4px 0 rgba(68,44,44,.35)) brightness(1.06);}
.st-key-maya_fab button:focus-visible, .st-key-maya_fab_open button:focus-visible {
  outline: 4px solid var(--orange) !important; outline-offset: 3px; border-radius: 50%;}
/* a ring that pings to say "I'm here" - only while the window is closed */
.st-key-maya_fab::before {content: ""; position: absolute; inset: 6px; border: 3px solid var(--pink);
  border-radius: 50%; pointer-events: none; animation: mayaPing 2.8s ease-out infinite;}
/* a speech bubble that greets once, then gets out of the way */
.st-key-maya_fab::after {content: "Hi! Need a hand?"; position: absolute; right: 98px; top: 10px;
  white-space: nowrap; background: var(--cream-l); border: 2px solid var(--ink); padding: .3rem .6rem;
  font: 600 .82rem var(--sans); color: var(--ink); box-shadow: 3px 3px 0 rgba(68,44,44,.25);
  pointer-events: none; opacity: 0; animation: mayaHello 11s ease 2.5s 1 both;}
.st-key-maya_fab_open::before {content: ""; position: absolute; right: 0; top: 2px; width: 22px; height: 22px;
  background: var(--green); border: 2px solid var(--ink); border-radius: 50%; pointer-events: none; z-index: 2;}

.st-key-maya_win {position: fixed !important; right: 22px; bottom: 122px; z-index: 1001;
  width: min(478px, calc(100vw - 28px)) !important; height: min(700px, calc(100vh - 142px));
  max-height: calc(100vh - 142px); display: flex !important; flex-direction: column;
  overflow: hidden; background: var(--cream); border: 3px solid var(--ink);
  box-shadow: 7px 7px 0 rgba(68,44,44,.32); padding: 0 .9rem .9rem !important;
  transform-origin: bottom right; animation: mayaPop .34s cubic-bezier(.2,1.35,.4,1) both;}
.st-key-maya_win::before {content: "MAYA.EXE  -  Part assistant"; display: block; position: sticky; top: 0;
  z-index: 3; margin: 0 -.9rem .5rem; padding: .42rem .9rem; background: var(--teal);
  border-bottom: 3px solid var(--ink); font: 600 .85rem var(--sans); letter-spacing: .06em; white-space: pre;}
.st-key-maya_win [data-testid="stCaptionContainer"], .st-key-maya_win .qd-sub {font-size: .8rem;}
/* the conversation takes the free space and scrolls; the controls and input stay visible */
.st-key-maya_win > div {flex: 0 0 auto; min-width: 0;}
.st-key-maya_win > div:has(.st-key-m_chat_scroll) {flex: 1 1 auto !important; height: auto !important;
  min-height: 0;}
.st-key-maya_win .st-key-m_chat_scroll {height: 100% !important; max-height: none !important;
  overflow-y: auto !important; min-height: 0 !important;}
.st-key-maya_win [data-testid="stColumn"] {min-width: 0 !important;}
.st-key-maya_win [data-testid="stHorizontalBlock"] {flex-wrap: nowrap !important;}
.st-key-maya_win .stButton > button {white-space: normal; line-height: 1.15; padding: .35rem .5rem;}
.st-key-maya_win .stChatInput {flex: 0 0 auto; margin-top: .35rem;}
.st-key-maya_close {position: absolute !important; top: 5px; right: 8px; z-index: 4; width: auto !important;}
.st-key-maya_close button {min-height: 1.7rem !important; padding: 0 .55rem !important; font-size: .78rem !important;
  background: var(--red-l) !important; outline-offset: -4px;}
.st-key-maya_win .stButton > button {min-height: 2.3rem;}
@media (max-width: 640px) {
  .st-key-maya_win {right: 8px; left: 8px; width: auto !important; bottom: 108px;
                    height: calc(100vh - 128px); max-height: calc(100vh - 128px);}
  .st-key-maya_fab, .st-key-maya_fab_open {right: 12px; bottom: 14px;}
  .st-key-maya_fab::after {display: none;}
}

@keyframes mayaBob {0%,100% {transform: translateY(0);} 50% {transform: translateY(-6px);}}
@keyframes mayaBlink {0%,91%,100% {background-image: url("__MAYA_OPEN__");}
                      92%,96% {background-image: url("__MAYA_BLINK__");}}
@keyframes mayaPing {0% {transform: scale(.8); opacity: .9;} 70%,100% {transform: scale(1.35); opacity: 0;}}
@keyframes mayaHello {0% {opacity: 0; transform: translateX(10px);} 8%,86% {opacity: 1; transform: none;}
                      100% {opacity: 0; transform: translateX(10px);}}
@keyframes mayaPop {0% {opacity: 0; transform: translateY(22px) scale(.88);} 100% {opacity: 1; transform: none;}}

/* ---------------------------------------------------------------- intro animation (first visit only) */
.qd-intro {position: fixed; inset: 0; z-index: 2147483000; display: flex; align-items: center;
  justify-content: center; pointer-events: none; background-color: var(--bg);
  background-image: linear-gradient(var(--grid) 2px, transparent 2px), linear-gradient(90deg, var(--grid) 2px, transparent 2px);
  background-size: 30px 30px; animation: qdOut 3.9s ease-in forwards;}
.qd-intro-win {width: min(470px, 88vw); background: var(--cream); border: 3px solid var(--ink);
  box-shadow: 8px 8px 0 rgba(68,44,44,.3); animation: qdIn .55s cubic-bezier(.2,1.4,.4,1) both;}
.qd-intro-bar {display: flex; justify-content: space-between; background: var(--orange); color: var(--ink);
  border-bottom: 3px solid var(--ink); padding: .35rem .8rem; font: 600 .9rem var(--sans); letter-spacing: .08em;}
.qd-intro-body {padding: 1.1rem 1.3rem 1.4rem; text-align: center;}
.qd-intro-maya {width: 104px; height: 104px; margin: 0 auto .4rem; image-rendering: pixelated;
  background: url("__MAYA_OPEN__") center/contain no-repeat; filter: drop-shadow(4px 4px 0 rgba(68,44,44,.3));
  animation: mayaBob 1.6s ease-in-out infinite, mayaBlink 3.2s steps(1, end) infinite;}
.qd-intro-title {font: 700 clamp(1.4rem, 5vw, 1.9rem)/1.1 var(--px); color: var(--ink);
  text-shadow: 3px 3px 0 var(--pink); letter-spacing: .03em; text-transform: uppercase;}
.qd-intro-lines {position: relative; height: 1.5rem; margin: .8rem 0 .6rem; font: 600 .95rem var(--sans);}
.qd-intro-lines span {position: absolute; inset: 0; opacity: 0; animation: qdLine .85s linear both;}
.qd-intro-lines span:nth-child(1) {animation-delay: .5s;}
.qd-intro-lines span:nth-child(2) {animation-delay: 1.3s;}
.qd-intro-lines span:nth-child(3) {animation-delay: 2.1s;}
.qd-intro-lines span:nth-child(4) {animation: qdLineLast .3s linear 2.9s both;}
.qd-intro-track {display: grid; grid-template-columns: repeat(20, 1fr); gap: 3px; padding: 4px;
  background: var(--cream-l); border: 2px solid var(--ink);}
.qd-intro-track i {display: block; height: 16px; background: #8F9FF4; opacity: 0;
  animation: qdSeg .05s linear forwards;}
.qd-fl {position: absolute; width: 46px; height: 46px; image-rendering: pixelated; background-size: contain;
  background-repeat: no-repeat; animation: mayaBob 2.4s ease-in-out infinite;}

@keyframes qdOut {0%,84% {opacity: 1; visibility: visible;} 100% {opacity: 0; visibility: hidden;}}
@keyframes qdIn {0% {opacity: 0; transform: scale(.7);} 100% {opacity: 1; transform: none;}}
@keyframes qdSeg {to {opacity: 1;}}
@keyframes qdLine {0% {opacity: 0;} 12%,88% {opacity: 1;} 100% {opacity: 0;}}
@keyframes qdLineLast {to {opacity: 1;}}

/* ---------------------------------------------------------------- video intro stage (optional) */
.st-key-intro_stage {max-width: 760px; margin: 4rem auto 0; background: var(--cream);
  border: 3px solid var(--ink); box-shadow: 8px 8px 0 rgba(68,44,44,.3); padding: 0 1rem 1.2rem !important;}
.st-key-intro_stage::before {content: "WELCOME.EXE"; display: block; margin: 0 -1rem .8rem; padding: .4rem .9rem;
  background: var(--orange); border-bottom: 3px solid var(--ink); font: 600 .9rem var(--sans); letter-spacing: .08em;}

/* ---------------------------------------------------------------- reduced motion */
@media (prefers-reduced-motion: reduce) {
  .qd-intro {display: none !important;}
  .st-key-maya_fab button, .st-key-maya_fab_open button, .st-key-maya_win,
  .qd-card, .qd-fl, .st-key-maya_fab::before, .st-key-maya_fab::after {animation: none !important; transition: none !important;}
  .st-key-maya_fab::before {display: none;}
  html {scroll-behavior: auto;}
}
</style>
"""


def css() -> str:
    """The whole stylesheet, with the generated pixel art spliced in."""
    return (_CSS.replace("__MAYA_OPEN__", ui_avatar.data_uri(False))
                .replace("__MAYA_BLINK__", ui_avatar.data_uri(True))
                .replace("__HEART__", pixel_icon("heart")))


# ---------------------------------------------------------------- intro
def intro_enabled() -> bool:
    """Tests and kiosks can switch the intro off with SPEC_SKIP_INTRO=1."""
    return os.environ.get("SPEC_SKIP_INTRO", "").strip().lower() not in ("1", "true", "yes")


def intro_video() -> Path | None:
    """assets/intro.mp4 (or .webm/.mov/.m4v): if you drop a file there it becomes the intro."""
    folder = ROOT / "assets"
    for name in VIDEO_NAMES:
        p = folder / name
        if p.is_file():
            return p
    return None


def intro_overlay_html() -> str:
    """The built-in intro: a pixel 'Loading...' window. Pure CSS, so it needs no script, never
    blocks a click (pointer-events: none) and removes itself after ~4 seconds."""
    segs = "".join(f'<i style="animation-delay:{0.6 + i * 0.115:.3f}s"></i>' for i in range(20))
    icons = "".join(
        f'<span class="qd-fl" style="{pos}animation-delay:{d}s;background-image:url({pixel_icon(n)})"></span>'
        for n, pos, d in (("heart", "left:12%;top:20%;", 0), ("star", "right:13%;top:16%;", .6),
                          ("mail", "left:16%;bottom:18%;", 1.1), ("gem", "right:15%;bottom:20%;", .3)))
    return (
        '<div class="qd-intro" aria-hidden="true">' + icons +
        '<div class="qd-intro-win">'
        '<div class="qd-intro-bar"><span>Loading...</span><span>_ &#9633; &times;</span></div>'
        '<div class="qd-intro-body"><div class="qd-intro-maya"></div>'
        '<div class="qd-intro-title">CNC Part Analysis</div>'
        '<div class="qd-intro-lines">'
        '<span>Reading Excel records...</span><span>Parsing PDF drawings...</span>'
        '<span>Measuring IGES models...</span><span>Ready! Welcome in.</span></div>'
        f'<div class="qd-intro-track">{segs}</div></div></div></div>')
