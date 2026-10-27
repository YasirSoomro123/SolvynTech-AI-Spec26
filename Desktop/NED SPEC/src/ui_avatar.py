"""Maya, the pixel-art assistant avatar.

Drawn in code on a 24x24 grid (no image file to lose or to ship), then returned as an SVG data
URI so the stylesheet can use it as a background. Two frames exist - eyes open and eyes closed -
which the stylesheet alternates to make her blink.

Nothing here touches the analysis: it is paint only.
"""

from __future__ import annotations

import base64

N = 24                      # grid size; the SVG is scaled by the browser
INK = "#442C2C"

PAL = {
    "K": INK,           # outline
    "P": "#6A4673",     # hair
    "p": "#8A5E94",     # hair highlight
    "R": "#F183B4",     # bow / ribbon pink
    "S": "#FBD5B8",     # skin
    "s": "#F2B999",     # skin shade
    "B": "#F5978F",     # blush
    "W": "#FFFFFB",     # eye sparkle
    "M": "#C4505A",     # mouth
    "T": "#7ABBB5",     # headset teal
    "D": "#4F928C",     # headset dark teal
    "Y": "#E8C561",     # top
    "O": "#E07F32",     # top trim
    "C": "#F7E3CB",     # cream
    "L": "#DEE5FF",     # badge background
    "G": "#FFFFFB",     # badge grid / shine
}


def _blank() -> list[list[str]]:
    return [["."] * N for _ in range(N)]


def _ellipse(g, cx, cy, rx, ry, ch, only=None):
    for y in range(N):
        for x in range(N):
            if ((x + .5 - cx) / rx) ** 2 + ((y + .5 - cy) / ry) ** 2 <= 1.0:
                if only is None or only(x, y):
                    g[y][x] = ch


def _rect(g, x0, y0, x1, y1, ch):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if 0 <= x < N and 0 <= y < N:
                g[y][x] = ch


def _put(g, pts, ch):
    for x, y in pts:
        if 0 <= x < N and 0 <= y < N:
            g[y][x] = ch


def _sprite(blink: bool) -> list[list[str]]:
    g = _blank()
    # back hair: a rounded bob
    _ellipse(g, 12, 11.5, 8.6, 9.2, "P")
    _rect(g, 4, 12, 6, 19, "P")
    _rect(g, 17, 12, 19, 19, "P")
    # shoulders / top
    _ellipse(g, 12, 25.5, 10.5, 6.2, "Y")
    _rect(g, 4, 21, 19, 23, "Y")
    _put(g, [(x, 20) for x in range(9, 15)], "O")          # collar line
    _put(g, [(10, 21), (11, 21), (12, 21), (13, 21)], "O")
    # neck
    _rect(g, 10, 17, 13, 19, "S")
    _rect(g, 10, 19, 13, 19, "s")
    # face
    _ellipse(g, 12, 12.2, 6.3, 6.4, "S")
    # bangs: a side-swept fringe across the forehead
    _ellipse(g, 12, 6.6, 7.0, 3.3, "P")
    _put(g, [(x, 9) for x in range(5, 11)], "P")
    _put(g, [(x, 9) for x in range(15, 19)], "P")
    _put(g, [(x, 8) for x in range(6, 12)], "P")
    _put(g, [(x, 10) for x in (5, 6, 18)], "P")
    # hair highlight
    _put(g, [(8, 5), (9, 5), (10, 5), (7, 6)], "p")
    # eyes
    if blink:
        _put(g, [(8, 12), (9, 12), (10, 12), (14, 12), (15, 12), (16, 12)], "K")
    else:
        _rect(g, 8, 11, 9, 13, "K")
        _rect(g, 15, 11, 16, 13, "K")
        _put(g, [(8, 11), (15, 11)], "W")
        _put(g, [(9, 13), (16, 13)], "K")
    # blush and mouth
    _put(g, [(7, 14), (8, 14), (16, 14), (17, 14)], "B")
    _put(g, [(11, 15), (12, 15)], "M")
    _put(g, [(10, 14), (13, 14)], "M")
    # headset: band over the hair, ear cups, mic boom
    for x, y in [(5, 5), (5, 4), (6, 3), (7, 2), (8, 2), (9, 1), (10, 1), (11, 1), (12, 1),
                 (13, 1), (14, 1), (15, 2), (16, 2), (17, 3), (18, 4), (18, 5)]:
        g[y][x] = "T"
    _rect(g, 3, 10, 5, 14, "T")
    _rect(g, 18, 10, 20, 14, "T")
    _put(g, [(3, 14), (4, 14), (5, 14), (18, 14), (19, 14), (20, 14)], "D")
    _put(g, [(4, 15), (4, 16), (5, 17), (6, 17), (7, 17), (8, 16)], "D")
    _put(g, [(8, 16), (9, 16)], "T")
    # bow
    _put(g, [(16, 3), (17, 3), (18, 3), (17, 4), (18, 2), (19, 2), (19, 4), (20, 3)], "R")
    return g


def _outline(g):
    """Ink pixel around every filled pixel, so the sprite reads on any background."""
    out = [row[:] for row in g]
    for y in range(N):
        for x in range(N):
            if g[y][x] != ".":
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < N and 0 <= ny < N and g[ny][nx] != ".":
                    out[y][x] = "K"
                    break
    return out


def _badge(blink: bool) -> list[list[str]]:
    """The sprite inside a round pixel badge."""
    sprite = _outline(_sprite(blink))
    cx = cy = (N - 1) / 2
    out = _blank()
    for y in range(N):
        for x in range(N):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** .5
            if d <= 11.2:
                out[y][x] = "L"
            elif d <= 12.2:
                out[y][x] = "K"
    for y in range(N):
        for x in range(N):
            if sprite[y][x] != "." and out[y][x] in ("L", "G"):
                out[y][x] = sprite[y][x]
    # the sprite may not spill past the ring
    for y in range(N):
        for x in range(N):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** .5
            if d > 12.2:
                out[y][x] = "."
            elif d > 11.2 and out[y][x] not in ("K", "."):
                out[y][x] = "K"
    return out


def svg(blink: bool = False) -> str:
    g = _badge(blink)
    rects = []
    for y, row in enumerate(g):
        x = 0
        while x < N:                       # merge runs of one colour: a smaller file
            ch = row[x]
            if ch == ".":
                x += 1
                continue
            x2 = x
            while x2 + 1 < N and row[x2 + 1] == ch:
                x2 += 1
            rects.append(f'<rect x="{x}" y="{y}" width="{x2 - x + 1}" height="1" fill="{PAL[ch]}"/>')
            x = x2 + 1
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'shape-rendering="crispEdges">' + "".join(rects) + "</svg>")


def data_uri(blink: bool = False) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg(blink).encode()).decode()


if __name__ == "__main__":          # python -m src.ui_avatar  -> writes a preview
    for name, b in (("maya_open", False), ("maya_blink", True)):
        with open(f"{name}.svg", "w") as f:
            f.write(svg(b))
    print("wrote maya_open.svg and maya_blink.svg")
