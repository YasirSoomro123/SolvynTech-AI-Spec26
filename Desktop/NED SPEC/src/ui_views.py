"""Picture helpers for the Views tab: the drawing page and the model envelope.

Both are deliberately modest. A PDF page is rendered exactly as the file stores it, and the
model is drawn as the box the IGES reader could actually verify - never as a shaded render,
because the reader keeps no surface tessellation and a convincing picture of geometry the
parser did not read would be the one place this app could lie.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

ACCENT = "#7C4318"
INK = "#442C2C"


def page_count(path: Path | str) -> int:
    """How many pages the drawing has, or 0 when the file cannot be opened."""
    try:
        import pymupdf
        with pymupdf.open(str(path)) as doc:
            return doc.page_count
    except Exception:
        return 0


def page_png(path: Path | str, page: int = 0, zoom: float = 1.6) -> Optional[bytes]:
    """One page of the PDF as PNG bytes, or None if it cannot be read.

    Nothing is interpreted here: the pixels are the page. A rotated or vector-heavy drawing
    comes out exactly as the file says, which is the point of showing it.
    """
    try:
        import pymupdf
    except Exception:                                       # pragma: no cover
        return None
    try:
        with pymupdf.open(str(path)) as doc:
            if not doc.page_count:
                return None
            idx = min(max(int(page), 0), doc.page_count - 1)
            pix = doc[idx].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            return pix.tobytes("png")
    except Exception:
        return None


# ------------------------------------------------------------------ envelope sketch
def _pt(x: float, y: float) -> str:
    return f"{x:.1f},{y:.1f}"


def envelope_svg(sizes: list[float], unit: str = "mm", note: str = "") -> str:
    """An axonometric box for the three envelope sizes the IGES reader measured.

    The sizes arrive SORTED (largest last in the reader, reversed here) because the axis
    order depends on the exporter - so the sketch labels the edges long / wide / thick and
    never claims which axis is which.
    """
    a, b, c = (list(sorted((float(s) for s in sizes), reverse=True)) + [0.0, 0.0, 0.0])[:3]
    if c <= 0:
        return ""
    longest = max(a, b, c)
    scale = 190.0 / longest
    A, B, C = max(a * scale, 26.0), max(b * scale, 26.0), max(c * scale, 26.0)
    ux, uy = 0.866, 0.500                       # edge going down-right
    vx, vy = -0.866, 0.500                      # edge going down-left
    ox, oy = 210.0, 70.0                        # the back-top corner

    t0 = (ox, oy)
    t1 = (ox + ux * A, oy + uy * A)
    t2 = (ox + ux * A + vx * B, oy + uy * A + vy * B)
    t3 = (ox + vx * B, oy + vy * B)
    bot = [(x, y + C) for x, y in (t1, t2, t3)]
    b1, b2, b3 = bot

    def fmt(v: float) -> str:
        return f"{v:g}"

    faces = [
        ((t0, t1, t2, t3), "#C9D5FA"),          # top
        ((t1, t2, b2, b1), "#E8C561"),          # right
        ((t3, t2, b2, b3), "#F183B4"),          # left
    ]
    polys = "".join(
        f'<polygon points="{" ".join(_pt(x, y) for x, y in pts)}" fill="{fill}" '
        f'stroke="{INK}" stroke-width="1.1" stroke-linejoin="round" opacity="0.95"/>'
        for pts, fill in faces)
    b0 = (ox, oy + C)                             # the hidden bottom-back corner
    hidden = "".join(
        f'<line x1="{b0[0]:.1f}" y1="{b0[1]:.1f}" x2="{p[0]:.1f}" y2="{p[1]:.1f}" '
        f'stroke="{INK}" stroke-width="0.8" stroke-dasharray="3 3" opacity="0.4"/>'
        for p in (b1, b3)) + (
        f'<line x1="{ox:.1f}" y1="{oy:.1f}" x2="{b0[0]:.1f}" y2="{b0[1]:.1f}" '
        f'stroke="{INK}" stroke-width="0.8" stroke-dasharray="3 3" opacity="0.4"/>')
    labels = (
        f'<text x="{(t0[0] + t1[0]) / 2 + 6:.1f}" y="{(t0[1] + t1[1]) / 2 + 16:.1f}" '
        f'fill="{INK}" font-size="12">longest edge {fmt(a)} {unit}</text>'
        f'<text x="{(t0[0] + t3[0]) / 2 - 6:.1f}" y="{(t0[1] + t3[1]) / 2 + 16:.1f}" '
        f'fill="{INK}" font-size="12" text-anchor="end">next edge {fmt(b)} {unit}</text>'
        f'<text x="{b2[0] + 8:.1f}" y="{(b2[1] + t2[1]) / 2:.1f}" '
        f'fill="{INK}" font-size="12">third edge {fmt(c)} {unit}</text>')
    caption = (f'<text x="16" y="300" fill="{ACCENT}" font-size="11.5">'
               f'Approximate envelope of the model, not a rendering of it.</text>'
               + (f'<text x="16" y="318" fill="{INK}" font-size="10.5" opacity="0.75">'
                  f'{_escape(note)}</text>' if note else ""))
    return (f'<svg viewBox="0 0 420 330" width="100%" height="auto" role="img" '
            f'aria-label="bounding box sketch" '
            f'style="max-width:460px;background:#FFF6EA;border:2px solid #442C2C;border-radius:0">{polys}{hidden}'
            f'{labels}{caption}</svg>')


def _escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
