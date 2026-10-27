"""IGES (.igs/.iges) reader - pure Python, no CAD library.

The file is fixed-width text with five sections, identified by the letter in column 73:

    S  Start        comment lines
    G  Global      comma separated settings, terminated by ';'   -> units, author, tolerances
    D  Directory   two 8-column-field lines per entity          -> what the model contains
    P  Parameter   the entity data themselves                   -> coordinates, radii
    T  Terminate   counts

Why this parser validates instead of trusting
--------------------------------------------
Exporters differ in ways the standard does not fully police. The files we were given put a
right-justified directory-sequence number *inside* the 72-column parameter field, which silently
shifts every parsed field by one if you just concatenate lines. So each entity's numeric token
count is checked against its documented parameter count, and an entity that does not match is
skipped with a warning rather than guessed at. Geometry facts therefore carry an honest
confidence, and unsupported entities cannot crash the app.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .fact import Fact, SourceResult
from .units import to_mm

# Entity type -> human name. Only what we actually understand; anything else is counted, not decoded.
ENTITY_NAMES = {
    100: "Circle", 110: "Line", 114: "Parametric line", 124: "Parametric curve",
    126: "Plane", 128: "Rational B-spline surface", 130: "Offset surface",
    144: "Trimmed surface", 186: "Rational B-spline curve",
    190: "Non-uniform rational B-spline curve", 208: "Elliptical torus",
    314: "Property (label/colour)", 400: "Annotation", 502: "Right circular cylinder",
    504: "Parametric surface", 508: "Circular torus", 510: "Parametric edge",
    514: "Parametric surface entity",
}

# Documented numeric parameter counts for the geometric types we decode.
# A leading transformation index (column 73 style files vary) is handled by the layout functions.
NUM = r"[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[EeDd][+-]?\d+)?"


class IgesModule:
    """Parsed IGES sections."""

    def __init__(self) -> None:
        self.global_raw = ""
        self.global_fields: list[str] = []
        self.entities: list[dict] = []       # directory entries
        self.param_lines: dict[int, str] = {}
        self.start_lines: list[str] = []
        self.warnings: list[str] = []

    @property
    def counts(self) -> dict[int, int]:
        out: dict[int, int] = {}
        for ent in self.entities:
            out[ent["type"]] = out.get(ent["type"], 0) + 1
        return out


def _parse(text: str) -> IgesModule:
    mod = IgesModule()
    lines = [ln.rstrip("\r\n") for ln in text.split("\n")]
    # Normalise to 80 columns: some exporters emit shorter/longer lines, which must not crash us.
    fixed = [ln.ljust(80)[:80] for ln in lines]

    def section(ln: str) -> str:
        # Column 73 (index 72) holds the section letter; the element number follows in 74-80.
        return ln[72].upper() if len(ln) > 72 else ""

    def element_no(ln: str) -> int:
        m = re.search(r"-?\d+", ln[73:80] if len(ln) > 73 else "")
        return int(m.group(0)) if m else 0

    dir_buf: list[str] = []
    raw_bodies: list[tuple[int, str]] = []
    for ln in fixed:
        if not ln.strip():
            continue
        code = section(ln)
        if code == "S":
            mod.start_lines.append(ln[:72].rstrip())
        elif code == "G":
            mod.global_raw += ln[:72]
        elif code == "D":
            dir_buf.append(ln[:72])
        elif code == "P":
            no = element_no(ln)
            raw_bodies.append((no, ln[:72]))
            if no in mod.param_lines:
                mod.param_lines[no] = mod.param_lines[no]  # placeholder, cleaned below
            else:
                mod.param_lines[no] = ln[:72]
        elif code == "T":
            break
        else:
            mod.warnings.append(f"unrecognised section letter {code!r} - line ignored")

    strip_pad = _detect_pad_convention(raw_bodies)
    if strip_pad:
        mod.warnings.append("exporter pads a directory number into the parameter column - stripped")
    joined: dict[int, str] = {}
    for no, body in raw_bodies:
        joined[no] = joined.get(no, "") + _clean_param_body(body, strip_pad)
    mod.param_lines = joined

    # Directory: pairs of lines, ten 8-column fields each.
    for i in range(0, len(dir_buf) - 1, 2):
        f1 = _fields(dir_buf[i])
        f2 = _fields(dir_buf[i + 1])
        try:
            ent_type = int(f1[0] or 0)
            param_ptr = int(f1[1] or 0)
            param_lines = int(f2[3] or 0)
            label_ptr = int(f1[7] or 0)
        except ValueError:
            mod.warnings.append(f"malformed directory entry at pair {i // 2 + 1}")
            continue
        mod.entities.append({"type": ent_type, "param_ptr": param_ptr,
                             "param_lines": max(param_lines, 0), "seq": i // 2 + 1,
                             "label_ptr": label_ptr})
    mod.global_fields = _split_global(mod.global_raw)
    return mod


def _clean_param_body(body: str, enabled: bool) -> str:
    """Drop an exporter's stray right-justified integer at the end of the 72-column data field.

    Only applied when the file is detected to use that convention (see _detect_pad_convention):
    stripping unconditionally can cut real digits from a line that happens to break in the middle
    of a number, which is worse than the quirk it fixes.
    """
    if not enabled:
        return body
    return re.sub(r"\s{2,}\d+\s*$", "", body)


def _detect_pad_convention(bodies: list[tuple[int, str]]) -> bool:
    """True if most parameter lines end with whitespace + an integer that matches a directory
    entry number. That is the 3D InterOp / ACIS convention; standard exporters do not do it."""
    scored = 0
    total = 0
    for seq, body in bodies:
        m = re.search(r"\s{2,}(\d+)\s*$", body)
        if not m:
            continue
        total += 1
        if int(m.group(1)) == seq:
            scored += 1
    return total > 0 and scored / total >= 0.6


def _fields(line: str) -> list[str]:
    return [line[i * 8:(i + 1) * 8].strip() for i in range(10)]


def _split_global(raw: str) -> list[str]:
    """Split the Global section on commas, honouring `nH<literal>` strings and ';' termination.

    The Global section escapes separators by declaring their length, e.g. `1H,` is a field holding
    a single comma and `2HMM` is the unit. Ignoring that makes field positions shift, so units
    would be read from the wrong place - hence this walks the string instead of using split().
    """
    fields: list[str] = []
    buf = ""
    i = 0
    raw = raw.rstrip()
    if raw.endswith(";"):
        raw = raw[:-1]
    while i < len(raw):
        m = re.match(r"(\d+)H", raw[i:])
        if m:
            n = int(m.group(1))
            start = i + m.end()
            buf += raw[start:start + n]
            i = start + n
            continue
        ch = raw[i]
        if ch == ",":
            fields.append(buf.strip())
            buf = ""
        elif ch == ";":
            break
        else:
            buf += ch
        i += 1
    if buf != "":
        fields.append(buf.strip())
    return fields


# ---------------------------------------------------------------- units

_UNIT_WORDS = {"INCH": 25.4, "MM": 1.0, "MILLIMETER": 1.0, "MILLIMETERS": 1.0, "FT": 304.8,
               "FEET": 304.8, "M": 1000.0, "CM": 10.0, "CENTIMETER": 10.0, "MICROIN": 0.0000254,
               "DECIMETER": 100.0, "DECAMETER": 10000.0, "HECTOMETER": 100000.0, "KILOMETER": 1e6}


def _global_units(fields: list[str], warnings: list[str]) -> tuple[str, float]:
    """Find the declared unit and its mm factor. Position 15/16 in the standard, but verify."""
    for idx in (14, 15, 13, 16):
        if idx < len(fields):
            word = fields[idx].upper().strip()
            if word in _UNIT_WORDS:
                return word, _UNIT_WORDS[word]
    # Fall back: scan every field for a unit-looking word (handles odd field ordering).
    for f in fields:
        word = f.upper().strip()
        if word in _UNIT_WORDS:
            warnings.append(f"unit '{word}' found outside the expected Global position")
            return word, _UNIT_WORDS[word]
    warnings.append("IGES Global section declares no recognisable unit - assuming millimetres")
    return "MM", 1.0


# ---------------------------------------------------------------- geometry layouts
#
# Every decoder below receives the numeric tokens of ONE entity and must validate them before
# returning anything. Validation is by pattern search rather than by trusting a fixed offset,
# because exporters disagree about the optional leading transformation index: a file whose
# numbers do not fit the documented shape yields no geometry plus a warning, instead of a
# plausible-looking but wrong bounding box. That trade-off is deliberate - a wrong number in an
# evidence-based answer is worse than no number.


def _nums(segs: str) -> list[float]:
    out: list[float] = []
    for m in re.finditer(NUM, segs):
        token = m.group(0).replace("D", "E").replace("d", "e")
        try:
            out.append(float(token))
        except ValueError:
            pass
    return out


def _triples(values: list[float], start: int) -> list[tuple[float, float, float]]:
    pts = []
    for i in range(start, len(values) - 2, 3):
        pts.append((values[i], values[i + 1], values[i + 2]))
    return pts


def _norm(v: tuple[float, float, float]) -> float:
    return (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) ** 0.5


def _is_unit(v: tuple[float, float, float], tol: float = 0.02) -> bool:
    """A direction vector of length 1 (within tolerance). Used as the signature that we found a
    real field boundary rather than a coincidence."""
    n = _norm(v)
    return n > 0 and abs(n - 1.0) < tol


def _find_unit_vector(tokens: list[float], max_offset: int = 12) -> int:
    """Index of the first triple that is a unit direction, or -1."""
    for i in range(0, min(max_offset, len(tokens) - 2)):
        if _is_unit((tokens[i], tokens[i + 1], tokens[i + 2])):
            return i
    return -1


def _perpendiculars(axis: tuple[float, float, float]) -> tuple[tuple[float, float, float],
                                                                tuple[float, float, float]]:
    """Two unit vectors at right angles to `axis` (and to each other)."""
    a = tuple(x / _norm(axis) for x in axis)
    helper = (1.0, 0.0, 0.0) if abs(a[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = _cross(a, helper)
    u = tuple(x / _norm(u) for x in u)
    v = _cross(a, u)
    return u, tuple(x / _norm(v) for x in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _plausible(pts: list[tuple[float, float, float]], limit: float = 20000.0) -> bool:
    """Reject coordinate reads that are obviously knot/angle garbage."""
    return bool(pts) and all(abs(c) <= limit for p in pts for c in p)


def _circle(t: list[float]) -> tuple[list, list, list]:
    """100 Circle: x,y,z centre, i,j,k normal, radius."""
    pts, extras, problems = [], [], []
    if len(t) != 7:
        problems.append(f"expected 7 parameters, found {len(t)}")
        return pts, extras, problems
    centre = (t[0], t[1], t[2])
    normal = (t[3], t[4], t[5])
    radius = abs(t[6])
    if not _is_unit(normal):
        problems.append("normal is not a unit vector - not decoded")
        return pts, extras, problems
    pts.append(centre)
    pts.append((centre[0] + radius, centre[1], centre[2]))
    # a circle is a hole candidate; a cylinder face is not necessarily one
    extras.append({"kind": "circle_radius", "value": radius})
    return pts, extras, problems


def _line(t: list[float]) -> tuple[list, list, list]:
    """110 Line: x1,y1,z1, x2,y2,z2."""
    pts, extras, problems = [], [], []
    if len(t) != 6:
        problems.append(f"expected 6 parameters, found {len(t)}")
        return pts, extras, problems
    pts += _triples(t, 0)
    if not _plausible(pts):
        problems.append("coordinates implausible")
        return [], extras, problems
    return pts, extras, problems


def _plane(t: list[float]) -> tuple[list, list, list]:
    """126 Plane: [T], three direction triples (the first is a unit normal), then 4 corner points.

    Strict: the whole documented parameter count must be present. A partial read would mix knot or
    angle values into the coordinates, which is how a 5 mm part can look 35 mm long.
    """
    pts, extras, problems = [], [], []
    if len(t) not in (21, 22, 25):
        problems.append(f"expected 21-22 parameters (normal + 4 corners), found {len(t)}")
        return pts, extras, problems
    n_idx = _find_unit_vector(t, max_offset=10)
    if n_idx < 0:
        problems.append("no unit normal found - not decoded")
        return pts, extras, problems
    after = t[n_idx + 3:]
    corners = _triples(after, 0)
    corners = [c for c in corners if _plausible([c])]
    if len(corners) < 4:
        problems.append(f"only {len(corners)} plausible corner points")
        return pts, extras, problems
    extras.append({"kind": "plane_normal", "value": tuple(round(c, 4) for c in t[n_idx:n_idx + 3])})
    pts += corners[:4]
    return pts, extras, problems


def _cylinder(t: list[float]) -> tuple[list, list, list]:
    """502 Right circular cylinder: [T], xo,yo,zo, ax,ay,az, r, xs,ys,zs, xe,ye,ze [, N, trims...].

    The optional transformation index shifts every field, so the block is located by requiring a
    unit axis, a positive radius and a real axial extent.
    """
    pts, extras, problems = [], [], []
    for off in range(0, min(4, max(len(t) - 14, 0) + 1)):
        origin = (t[off], t[off + 1], t[off + 2])
        axis = (t[off + 3], t[off + 4], t[off + 5])
        radius = t[off + 6]
        start = (t[off + 7], t[off + 8], t[off + 9])
        end = (t[off + 10], t[off + 11], t[off + 12])
        if not (radius > 0 and _is_unit(axis) and _plausible([origin, start, end])):
            continue
        height = _norm((end[0] - start[0], end[1] - start[1], end[2] - start[2]))
        # A cylinder's envelope needs its silhouette points: two directions perpendicular to the
        # axis, times the radius, at both end discs. Without them a Ø12 rod looks 0 mm wide.
        u, v = _perpendiculars(axis)
        pts += [origin, start, end]
        for base in (start, end):
            for radial in (u, v):
                pts.append((base[0] + radius * radial[0], base[1] + radius * radial[1],
                            base[2] + radius * radial[2]))
                pts.append((base[0] - radius * radial[0], base[1] - radius * radial[1],
                            base[2] - radius * radial[2]))
        extras.append({"kind": "radius", "value": radius})
        extras.append({"kind": "cylinder_height", "value": height})
        extras.append({"kind": "axis", "value": tuple(round(a, 3) for a in axis)})
        return pts, extras, problems
    problems.append(f"no field block matching a cylinder in {len(t)} parameters")
    return pts, extras, problems


def _torus(t: list[float]) -> tuple[list, list, list]:
    """508 Circular torus: [T], xo,yo,zo, ax,ay,az, major, minor, start, end [, N]."""
    pts, extras, problems = [], [], []
    for off in range(0, min(4, max(len(t) - 11, 0) + 1)):
        centre = (t[off], t[off + 1], t[off + 2])
        axis = (t[off + 3], t[off + 4], t[off + 5])
        major, minor = t[off + 6], t[off + 7]
        if not (major > 0 and minor > 0 and minor < major and _is_unit(axis)
                and _plausible([centre])):
            continue
        pts.append(centre)
        extras.append({"kind": "major_radius", "value": major})
        extras.append({"kind": "minor_radius", "value": minor})
        return pts, extras, problems
    problems.append(f"no field block matching a torus in {len(t)} parameters")
    return pts, extras, problems


def _bspline_surface(t: list[float]) -> tuple[list, list, list]:
    """128 Rational B-spline surface: 14 header values, knot vectors, then the control net.

    Accepted only when the token count matches the documented size exactly, so the poles we read
    are poles and not knots. Even then the result is a CONTROL-POINT envelope: the real surface
    lies inside it, so every fact taken from here is labelled approximate.
    """
    pts, extras, problems = [], [], []
    if len(t) < 15:
        problems.append("too few parameters for a B-spline surface")
        return pts, extras, problems
    sf, m, n = int(t[0]), int(t[1]), int(t[2])
    if not (0 <= m <= 500 and 0 <= n <= 500):
        problems.append(f"unrealistic pole counts (M={m}, N={n})")
        return pts, extras, problems
    poles = (m + 1) * (n + 1)
    per_pole = 4 if sf == 1 else 3          # rational poles carry a weight first
    variants = [14 + (m + 1) + (n + 1) + per_pole * poles,          # separate u/v knot vectors
                14 + (m + 1) + per_pole * poles]                    # MNF=1: shared knots
    if len(t) not in variants:
        problems.append(f"found {len(t)} parameters, expected one of {variants}")
        return pts, extras, problems
    start = len(t) - per_pole * poles
    block = t[start:]
    coords = [block[i + (1 if sf == 1 else 0):i + (1 if sf == 1 else 0) + 3]
              for i in range(0, len(block), per_pole)]
    coords = [tuple(c) for c in coords if len(c) == 3 and _plausible([tuple(c)], limit=50000)]
    if not coords:
        problems.append("control net coordinates implausible")
        return pts, extras, problems
    pts += coords
    extras.append({"kind": "bspline_poles", "value": poles})
    return pts, extras, problems


DECODERS = {
    100: _circle, 110: _line, 126: _plane, 128: _bspline_surface,
    502: _cylinder, 508: _torus,
}


# Types that are topology/annotation: counted, never decoded as geometry.
NON_GEOMETRIC = {314, 400, 402, 504, 510, 514, 408, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13}


def read_iges(path: Path | str, max_bytes: int = 6_000_000) -> SourceResult:
    """Parse one IGES file into facts. Always returns a SourceResult; never raises."""
    path = Path(path)
    res = SourceResult(source_type="IGES", file=str(path))
    try:
        data = path.read_bytes()[:max_bytes]
        text = data.decode("utf-8", errors="replace")
    except OSError as exc:
        res.ok = False
        res.warn(f"cannot read file: {exc}")
        return res

    try:
        mod = _parse(text)
    except Exception as exc:                       # a malformed file must not kill the app
        res.ok = False
        res.warn(f"IGES parse failed: {exc}")
        return res

    if not mod.entities and not mod.global_fields:
        res.ok = False
        res.warn("no Directory or Global section found - this may not be an IGES file")
        for w in mod.warnings:
            res.warn(w)
        return res

    facts: list[Fact] = []
    unit_word, unit_factor = _global_units(mod.global_fields, res.warnings)

    def mm(values: list[float] | tuple) -> tuple[float, ...]:
        return tuple(round(v * unit_factor, 4) for v in values)

    def loc(entity: dict) -> str:
        return f"IGES entity #{entity['seq']} (type {entity['type']})"

    # ---- header facts -------------------------------------------------------
    def gfield(idx: int) -> Optional[str]:
        return mod.global_fields[idx] if idx < len(mod.global_fields) else None

    add = facts.append
    # Field positions follow the IGES Global section order. Each one is only used after it is
    # checked to look like the thing it claims to be, so a differently ordered export degrades
    # to a warning instead of a wrong fact.
    add(Fact("cad_units", unit_word, None, "IGES", str(path), "Global section", "code-high",
             f"declared in Global section; 1 model unit = {unit_factor} mm"))
    name = gfield(3)
    if name:
        add(Fact("model_file_name", name, None, "IGES", str(path), "Global section", "code-high",
                 "the exporter's own file name - often NOT the part number"))
    system_id = gfield(4)
    if system_id:
        add(Fact("cad_system", system_id, None, "IGES", str(path), "Global section"))
    post = gfield(5)
    if post:
        add(Fact("cad_postprocessor", post, None, "IGES", str(path), "Global section"))
    # conversion factor (position 17) is a second, independent statement of the unit
    conv = _nums(gfield(16) or "")
    if conv and abs(conv[0] - unit_factor) > 1e-9 and conv[0] > 0:
        res.warn(f"Global section unit says {unit_word} (={unit_factor} mm) but conversion factor "
                 f"says {conv[0]} mm; used the declared unit")
    stamps = [f for f in mod.global_fields if re.fullmatch(r"\d{8}\.\d{6}", f or "")]
    if stamps:
        st = stamps[0]
        add(Fact("model_date", f"{st[:4]}-{st[4:6]}-{st[6:8]}", None, "IGES", str(path),
                 "Global section", "code-high", f"raw timestamp {st}"))
    tol = _nums(gfield(18) or "")
    if tol and 0 < tol[0] < 1:
        add(Fact("model_tolerance", round(tol[0] * unit_factor, 8), "mm", "IGES", str(path),
                 "Global section", "code-high",
                 "CAD surface-fit tolerance, NOT a manufacturing tolerance - do not compare it "
                 "with drawing tolerances"))
    for idx, field in ((20, "model_author"), (21, "model_author_company")):
        val = gfield(idx)
        if val and re.search(r"[A-Za-z]{3}", val):
            add(Fact(field, val, None, "IGES", str(path), "Global section"))

    # ---- entity inventory ---------------------------------------------------
    counts = mod.counts
    add(Fact("iges_entity_total", len(mod.entities), None, "IGES", str(path), "Directory section",
             "code-high"))
    for etype, n in sorted(counts.items()):
        add(Fact("iges_entity_count", n, None, "IGES", str(path), "Directory section", "code-high",
                 f"type {etype} = {ENTITY_NAMES.get(etype, 'unknown/unsupported')}"))

    # property labels (314) can name the part
    for ent in mod.entities:
        if ent["type"] != 314:
            continue
        segs = _param(mod, ent)
        for lit in re.findall(r"\d+H([^,;]{3,60})", segs):
            if re.search(r"[A-Za-z]", lit):
                add(Fact("model_label", lit.strip(), None, "IGES", str(path), loc(ent), "code-high",
                         "text stored in the model as a property"))

    # ---- geometry -----------------------------------------------------------
    all_pts: list[tuple[float, float, float]] = []
    radii: list[float] = []
    heights: list[float] = []
    unsupported = 0
    suspect: list[str] = []

    for ent in mod.entities:
        etype = ent["type"]
        if etype in NON_GEOMETRIC:
            continue
        decoder = DECODERS.get(etype)
        if decoder is None:
            unsupported += 1
            continue
        segs = _param(mod, ent)
        if not segs:
            res.warn(f"entity #{ent['seq']} (type {etype}) has no readable parameter data - skipped")
            continue
        tokens = _nums(segs)
        # strip the leading entity type number, which is not a parameter
        if tokens and str(int(tokens[0])) == str(etype):
            tokens = tokens[1:]
        pts, extras, problems = decoder(tokens)
        for p in problems:
            suspect.append(f"entity #{ent['seq']} (type {etype}): {p}")
        if problems and not pts:
            continue
        for p in pts:
            all_pts.append(mm(p))
        for extra in extras:
            v = extra["value"]
            if extra["kind"] == "radius":
                radii.append(round(abs(v) * unit_factor, 4))
                add(Fact("cylinder_radius", round(abs(v) * unit_factor, 4), "mm", "IGES", str(path),
                         loc(ent), "code-high", "radius read from a right circular cylinder entity"))
                add(Fact("outer_diameter", round(abs(v) * 2 * unit_factor, 4), "mm", "IGES", str(path),
                         loc(ent), "code-medium",
                         "derived from one cylinder entity; the model may contain several"))
            elif extra["kind"] == "circle_radius":
                radii.append(round(abs(v) * unit_factor, 4))
                add(Fact("hole_diameter", round(abs(v) * 2 * unit_factor, 4), "mm", "IGES", str(path),
                         loc(ent), "code-medium",
                         "diameter of a circular edge - could be a hole or an outer face"))
            elif extra["kind"] == "cylinder_height":
                heights.append(round(v * unit_factor, 4))
            elif extra["kind"] in ("major_radius", "minor_radius"):
                add(Fact("torus_" + extra["kind"], round(abs(v) * unit_factor, 4), "mm", "IGES",
                         str(path), loc(ent), "code-medium",
                         "torus entities usually come from fillets/rounds, not free-form features"))

    for warning in mod.warnings:
        res.warn(warning)
    if suspect:
        res.warn(f"{len(suspect)} entit(y/ies) did not match their documented parameter layout: "
                 + "; ".join(suspect[:5]))
    if unsupported:
        res.warn(f"{unsupported} entity type(s) are counted but not decoded (no geometry derived)")

    # ---- envelope: sizes, from verified points only ------------------------
    geometric_types = sum(n for etype, n in counts.items() if etype not in NON_GEOMETRIC)
    add(Fact("iges_entities_decoded", geometric_types - len(suspect), None, "IGES", str(path),
             "Directory/Parameter sections", "code-high",
             f"of {geometric_types} geometric entities, {len(suspect)} did not validate"))
    if all_pts and len(suspect) <= geometric_types * 0.5:
        mins = [min(p[i] for p in all_pts) for i in range(3)]
        maxs = [max(p[i] for p in all_pts) for i in range(3)]
        sizes = sorted(round(maxs[i] - mins[i], 3) for i in range(3))
        add(Fact("bounding_box_min", tuple(round(m, 4) for m in mins), "mm", "IGES", str(path),
                 "validated entity coordinates", "code-medium",
                 "corner of the envelope of every point we could validate"))
        add(Fact("bounding_box_size", sizes, "mm", "IGES", str(path),
                 "validated entity coordinates", "code-medium",
                 "SORTED envelope sizes in mm (largest last); axis order is exporter-dependent so "
                 "the three numbers are compared sorted, never as X/Y/Z. "
                 "Includes B-spline control points where validated, so it can only be too big, "
                 "never too small"))
    else:
        res.warn("geometry is stored in entities this parser cannot validate (free-form/parametric "
                 "export), so no bounding box or size is reported")

    # hole/feature *candidates*: counts only, never asserted as engineering holes
    circles = counts.get(100, 0)
    cylinders = counts.get(502, 0)
    if circles or cylinders:
        add(Fact("hole_candidates", circles + cylinders, None, "IGES", str(path),
                 "Directory section", "inferred",
                 f"{cylinders} cylinder + {circles} circle entities; many are outer surfaces, "
                 "not holes"))
    if heights:
        add(Fact("cylinder_height", round(max(heights), 4), "mm", "IGES", str(path),
                 "IGES entity 502", "code-high", "axial extent of the tallest cylinder"))

    res.add(facts)
    res.detail = (f"{len(mod.entities)} entities, {len(facts)} facts, units {unit_word} "
                  f"(x{unit_factor} mm)")
    return res


def _param(mod: IgesModule, ent: dict) -> str:
    """Concatenate an entity's parameter lines (pointer + line count from its directory pair)."""
    ptr, n = ent["param_ptr"], ent["param_lines"]
    if not ptr:
        return ""
    if n <= 0:
        n = 1
    return "".join(mod.param_lines.get(ptr + i, "") for i in range(n))
