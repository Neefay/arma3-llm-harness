"""Draws the commander's map as a PNG, from what it already has: the ground, buildings, its markers, reported positions.

A pure function of its inputs, and nothing about the live game is one of them. The picture can't show more than the
commander has been told, which is the point.
"""
from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageFont

from .terrain import Terrain

SIZE = 1000
_COLOURS = {"enemy": (190, 40, 30), "danger": (225, 120, 20), "hypothesis": (150, 70, 170), "objective": (30, 130, 70),
            "friendly": (25, 90, 170), "note": (90, 90, 90), "phase_line": (150, 100, 30), "area": (150, 100, 30)}
_PAPER, _GRID, _INK = (238, 240, 228), (205, 210, 195), (35, 40, 45)
_BUILDING, _CHECKED = (150, 145, 135), (120, 175, 125)
# The ground, as on a paper map: low land pale, high land darker, water blue, woods green.
_LOW, _HIGH, _WATER, _WOODS = (240, 238, 222), (214, 200, 168), (196, 216, 230), (176, 206, 160)
_COAST = (110, 150, 185)
_CONTOUR, _ROAD, _TRACK, _HOUSE, _PLACE = (196, 160, 118), (205, 120, 60), (140, 105, 70), (120, 115, 108), (60, 55, 50)
_SHEET_EDGE = (150, 150, 140)
BUILDING_IDS_FROM = 0.8  # pixels a metre: zoomed out further than this, building ids are a clump nobody can read
CAPTION_H, GRID_LABEL_H = 26, 16
PLACE_OFF_SHEET_M = 300
# Where a label may go around its symbol, in order of preference: right, left, above, below, then the corners.
AROUND = ((15, 0, "lm"), (-15, 0, "rm"), (0, -14, "md"), (0, 14, "ma"),
          (12, -12, "ld"), (-12, -12, "rd"), (12, 12, "la"), (-12, 12, "ra"))
CENTRED = ((0, 0, "mm"), (0, -14, "md"), (0, 14, "ma"), (15, 0, "lm"), (-15, 0, "rm"))


def render(center: list[float], radius: float, buildings: list[dict], markers: list[dict], positions: dict[str, dict],
           checked: dict[str, float], caption: str, destroyed: dict[str, float] | None = None,
           vehicles: list[dict] | None = None, terrain: Terrain | None = None) -> bytes:
    """A square map around ``center``. Markers and positions hold grids in their spoken form, such as "041 041"."""
    image = _ground(terrain, center, radius) if terrain else Image.new("RGB", (SIZE, SIZE), _PAPER)
    draw = ImageDraw.Draw(image)
    scale = SIZE / (2 * radius)

    def xy(x: float, y: float) -> tuple[float, float]:
        return (x - center[0] + radius) * scale, SIZE - (y - center[1] + radius) * scale

    if terrain:
        _features(draw, terrain, center, radius, xy)
    small, medium = _font(13), _font(15)
    labels = _Labels(draw)
    grid_labels = _grid(draw, center, radius, xy, labels)
    if terrain:
        _sheet_edge(draw, terrain, center, radius, xy)
    # Symbols first, then their labels from the most needed down, each where it fits.
    for building in buildings:
        corners = _footprint(building)
        fill = _CHECKED if building["id"] in checked else _BUILDING
        draw.polygon([xy(*corner) for corner in corners], fill=fill, outline=_INK)
        if building["id"] in (destroyed or {}):  # a cross through what's left of it
            points = [xy(*corner) for corner in corners]
            draw.line((points[0], points[2]), fill=_INK, width=3)
            draw.line((points[1], points[3]), fill=_INK, width=3)
    texts = []  # (anchor point, text, colour, font, where it may go, whether it has to be drawn)
    for callsign, place in positions.items():
        x, y = xy(*_grid_centre(place["grid"]))
        labels.reserve((x - 14, y - 10, x + 14, y + 10))
        draw.rectangle((x - 13, y - 9, x + 13, y + 9), outline=_COLOURS["friendly"], width=3)
        draw.line((x - 13, y - 9, x + 13, y + 9), fill=_COLOURS["friendly"], width=2)
        draw.line((x - 13, y + 9, x + 13, y - 9), fill=_COLOURS["friendly"], width=2)
        texts.append(((x, y), f"{callsign} ({place['age']})", _COLOURS["friendly"], small,
                      ((0, 12, "ma"), (0, -12, "md"), (17, 0, "lm"), (-17, 0, "rm")), True))
    for marker in markers:
        texts.append(_marker(draw, marker, xy, medium, labels))
    for vehicle in vehicles or []:
        x, y = xy(*_grid_centre(vehicle["at"]))
        labels.reserve((x - 8, y - 8, x + 8, y + 8))
        draw.rectangle((x - 7, y - 7, x + 7, y + 7), outline=_INK, width=3 if not vehicle.get("wrecked") else 1)
        texts.append(((x, y), vehicle["id"] + (" wrecked" if vehicle.get("wrecked") else ""), _INK, small, AROUND,
                      True))
    if terrain:
        texts += _place_names(terrain, center, radius, xy)
    if scale >= BUILDING_IDS_FROM:
        texts += [(xy(*building["pos"]), building["id"], _INK, small, CENTRED, False) for building in buildings]
    if terrain:
        texts += _spot_heights(draw, terrain, center, radius, xy, labels)
    for at, text, colour, font, where, needed in texts:
        if _in_view(at):  # a symbol off the map takes its label with it
            labels.put(at, text, colour, font, where, needed)
    for at, text in grid_labels:  # on top, so nothing hides which square is which
        draw.text(at, text, fill=_INK, font=_font(12))
    draw.rectangle((0, 0, SIZE, CAPTION_H), fill=_INK)
    draw.text((8, 13), caption, fill=_PAPER, font=small, anchor="lm")
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _ground(terrain: Terrain, center, radius) -> Image.Image:
    """Height tint, hillshade, water and woods, one pixel a cell, stretched over the map's window."""
    n, step = terrain.n, terrain.step
    cells = Image.new("RGB", (n, n))
    pixels = cells.load()
    top = max((cell[0] for cell in terrain.cells), default=1) or 1
    for j in range(n):
        for i in range(n):
            cell = terrain.cells[j * n + i]
            if cell[1]:
                colour = _WATER
            else:
                rise = min(max(cell[0] / top, 0), 1)
                colour = _mix(_LOW, _HIGH, rise)
                east = terrain.cells[j * n + min(i + 1, n - 1)][0] - terrain.cells[j * n + max(i - 1, 0)][0]
                north = terrain.cells[min(j + 1, n - 1) * n + i][0] - terrain.cells[max(j - 1, 0) * n + i][0]
                # Lit from the north-west, as maps are: slopes facing it lighter, the far ones darker.
                shade = max(-1.0, min(1.0, (north - east) / (2 * step) * 2.5))
                colour = _mix(colour, (255, 255, 255) if shade > 0 else (120, 105, 80), abs(shade) * 0.45)
                trees, _ = terrain.per_ha(cell)
                colour = _mix(colour, _WOODS, min(max(trees - 10, 0) / 140, 1) * 0.8)
            pixels[i, n - 1 - j] = colour
    span = n * step

    def pixel(x, y):
        return (x - terrain.x0) / step, (terrain.y0 + span - y) / step

    box = (*pixel(center[0] - radius, center[1] + radius), *pixel(center[0] + radius, center[1] - radius))
    return cells.transform((SIZE, SIZE), Image.Transform.EXTENT, box, Image.Resampling.BILINEAR, fillcolor=_PAPER)


def _mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b, strict=True))


def _in_view(point) -> bool:
    return 0 <= point[0] <= SIZE and CAPTION_H <= point[1] <= SIZE


class _Labels:
    """Puts each label in the first free place around its symbol, so none is drawn over another."""

    def __init__(self, draw):
        self.draw = draw
        self.taken: list[tuple[float, float, float, float]] = [(0, 0, SIZE, CAPTION_H)]

    def reserve(self, box) -> None:
        self.taken.append(box)

    def free(self, box) -> bool:
        inside = box[0] >= 0 and box[1] >= CAPTION_H and box[2] <= SIZE and box[3] <= SIZE
        return inside and not any(box[0] < b[2] and b[0] < box[2] and box[1] < b[3] and b[1] < box[3]
                                  for b in self.taken)

    def put(self, at, text, colour, font, where, needed: bool) -> bool:
        """Draws it in the first free place. A label that has to be there goes in the first place if none is free."""
        stroke = 2
        for dx, dy, anchor in where:
            spot = (at[0] + dx, at[1] + dy)
            box = self.draw.textbbox(spot, text, font=font, anchor=anchor, stroke_width=stroke)
            if self.free(box):
                break
        else:
            if not needed:
                return False
            # Over something else, then, but on the map: the first place that isn't cut off at an edge.
            for dx, dy, anchor in (*where, *AROUND):
                spot = (at[0] + dx, at[1] + dy)
                box = self.draw.textbbox(spot, text, font=font, anchor=anchor, stroke_width=stroke)
                if box[0] >= 0 and box[1] >= CAPTION_H and box[2] <= SIZE and box[3] <= SIZE:
                    break
        self.draw.text(spot, text, fill=colour, font=font, anchor=anchor, stroke_width=stroke, stroke_fill=_PAPER)
        self.taken.append(box)
        return True


def _features(draw, terrain: Terrain, center, radius, xy) -> None:
    """Contours, roads and the world's own buildings, and the edge of the sheet if it's in view. Nothing is drawn
    beyond the edge: the sheet is all the commander has."""
    interval = 10 if radius <= 800 else 20
    high = max((cell[0] for cell in terrain.cells), default=0)
    for level, segments in _contours(terrain, [0, *range(interval, high + 1, interval)]):
        index = level % (interval * 5) == 0
        colour, width = (_COAST, 2) if level == 0 else (_CONTOUR, 2 if index else 1)
        for (ax, ay), (bx, by) in segments:
            draw.line((xy(ax, ay), xy(bx, by)), fill=colour, width=width)
    width = 1 if radius > 1500 else 2
    for x1, y1, x2, y2, kind in terrain.roads:
        if not (terrain.covers(x1, y1) and terrain.covers(x2, y2)):
            continue
        if kind in ("MAIN ROAD", "ROAD"):
            draw.line((xy(x1, y1), xy(x2, y2)), fill=_ROAD, width=width + 2)
        elif kind == "TRACK":
            draw.line((xy(x1, y1), xy(x2, y2)), fill=_TRACK, width=width)
        else:
            draw.line((xy(x1, y1), xy(x2, y2)), fill=_HOUSE, width=1)
    for x, y, w, length, direction in terrain.houses:
        if abs(x - center[0]) > radius + 30 or abs(y - center[1]) > radius + 30 or not terrain.covers(x, y):
            continue
        corners = _footprint({"pos": [x, y], "width": max(w, 4), "length": max(length, 4), "dir": direction})
        draw.polygon([xy(*corner) for corner in corners], fill=_HOUSE)


def _sheet_edge(draw, terrain: Terrain, center, radius, xy) -> None:
    """Where the commander's map ends, if that's in view. Drawn over the grid, which carries on past it."""
    span = terrain.n * terrain.step
    if not (terrain.covers(center[0] - radius, center[1] - radius)
            and terrain.covers(center[0] + radius, center[1] + radius)):
        (left, top), (right, bottom) = xy(terrain.x0, terrain.y0 + span), xy(terrain.x0 + span, terrain.y0)
        draw.rectangle((left, top, right, bottom), outline=_SHEET_EDGE, width=2)


def _spot_heights(draw, terrain: Terrain, center, radius, xy, labels: _Labels) -> list[tuple]:
    """A triangle on each hilltop, the way a map prints them, with its height where there's room."""
    out = []
    for x, y, h in terrain.spot_heights(limit=20, apart_m=radius / 4):
        if abs(x - center[0]) < radius and abs(y - center[1]) < radius:
            px, py = xy(x, y)
            draw.polygon([(px, py - 5), (px + 5, py + 4), (px - 5, py + 4)], fill=_PLACE)
            labels.reserve((px - 6, py - 6, px + 6, py + 5))
            out.append(((px, py), str(h), _PLACE, _font(12), ((8, 0, "lm"), (-8, 0, "rm"), (0, -7, "md"),
                                                                   (0, 7, "ma")), False))
    return out


def _place_names(terrain: Terrain, center, radius, xy) -> list[tuple]:
    """A place just off the sheet is still named, at its edge, as a printed map names a town half on it."""
    span, out = terrain.n * terrain.step, []
    for place, _kind, x, y in terrain.places:
        inside = (min(max(x, terrain.x0 + 1), terrain.x0 + span - 1),
                  min(max(y, terrain.y0 + 1), terrain.y0 + span - 1))
        in_view = abs(inside[0] - center[0]) < radius and abs(inside[1] - center[1]) < radius
        if in_view and math.dist((x, y), inside) <= PLACE_OFF_SHEET_M:
            out.append((xy(*inside), place, _PLACE, _font(16), CENTRED + AROUND, False))
    return out


def _contours(terrain: Terrain, levels):
    """Marching squares over the cell centres: for each height, the line segments where the ground crosses it."""
    n, step = terrain.n, terrain.step
    heights = [[terrain.cells[j * n + i][0] for i in range(n)] for j in range(n)]
    for level in levels:
        segments = []
        for j in range(n - 1):
            for i in range(n - 1):
                corners = ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))
                values = [heights[cj][ci] for ci, cj in corners]
                crossings = []
                for k in range(4):
                    (ai, aj), (bi, bj) = corners[k], corners[(k + 1) % 4]
                    a, b = values[k], values[(k + 1) % 4]
                    if (a < level) != (b < level):
                        t = (level - a) / (b - a)
                        crossings.append((terrain.x0 + (ai + t * (bi - ai) + 0.5) * step,
                                          terrain.y0 + (aj + t * (bj - aj) + 0.5) * step))
                if len(crossings) == 2:
                    segments.append((crossings[0], crossings[1]))
                elif len(crossings) == 4:
                    segments += [(crossings[0], crossings[1]), (crossings[2], crossings[3])]
        yield level, segments


def _font(size: int):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default(size)


def _grid(draw, center, radius, xy, labels: _Labels) -> list[tuple[tuple[float, float], str]]:
    """The grid lines, and where their numbers go, with that room kept clear of other labels."""
    step = 100 if radius <= 800 else 500 if radius <= 3000 else 1000
    font = _font(12)
    low_x, high_x = center[0] - radius, center[0] + radius
    low_y, high_y = center[1] - radius, center[1] + radius
    out = []
    for x in range(int(low_x // step) * step, int(high_x) + step, step):
        draw.line((xy(x, low_y), xy(x, high_y)), fill=_GRID)
        out.append(((xy(x, low_y)[0] + 3, SIZE - GRID_LABEL_H), f"{x // 100:03d}"))
    for y in range(int(low_y // step) * step, int(high_y) + step, step):
        draw.line((xy(low_x, y), xy(high_x, y)), fill=_GRID)
        out.append(((3, xy(low_x, y)[1] - 15), f"{y // 100:03d}"))
    for at, text in out:
        labels.reserve(draw.textbbox(at, text, font=font))
    return out


def _footprint(building: dict) -> list[tuple[float, float]]:
    x, y = building["pos"]
    half_w, half_l = building.get("width", 8) / 2, building.get("length", 8) / 2
    angle = math.radians(building.get("dir", 0))
    cos, sin = math.cos(angle), math.sin(angle)
    return [(x + dx * cos + dy * sin, y - dx * sin + dy * cos)
            for dx, dy in ((-half_w, -half_l), (half_w, -half_l), (half_w, half_l), (-half_w, half_l))]


def _grid_centre(grid: str) -> list[float]:
    digits = grid.replace(" ", "")
    if len(digits) == 8:  # a commander's own working, down to a 10 m square
        return [int(digits[:4]) * 10 + 5, int(digits[4:]) * 10 + 5]
    return [int(digits[:3]) * 100 + 50, int(digits[3:]) * 100 + 50]


def _marker(draw, marker: dict, xy, font, labels: _Labels) -> tuple:
    """Draws the marker's symbol, and returns its label for placing."""
    colour = _COLOURS.get(marker["kind"], _INK)
    at = marker["at"]
    pinned = f"in {marker['building']}" if marker.get("building") else ""
    parts = (marker["id"], pinned, marker.get("label"), marker.get("confidence"))
    label = " ".join(str(part) for part in parts if part)
    if isinstance(at, list):
        points = [xy(*_grid_centre(grid)) for grid in at]
        if marker["kind"] == "area":
            points.append(points[0])
        draw.line(points, fill=colour, width=3)
        start = next((point for point in points if _in_view(point)), points[0])  # where the line comes into view
        return start, label, colour, font, ((0, -4, "ld"), (0, 4, "la"), (0, -4, "rd"), (0, 4, "ra")), True
    x, y = xy(*(marker.get("pos") or _grid_centre(at)))
    size = 13 if marker["kind"] == "objective" else 11 if marker["kind"] in ("enemy", "danger") else 6
    labels.reserve((x - size, y - size, x + size, y + size))
    if marker["kind"] == "enemy" or marker["kind"] == "danger":
        draw.polygon([(x, y - 11), (x + 11, y), (x, y + 11), (x - 11, y)], outline=colour, width=3)
    elif marker["kind"] == "objective":
        draw.ellipse((x - 13, y - 13, x + 13, y + 13), outline=colour, width=3)
    else:
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), outline=colour, width=3)
    where = tuple((dx + (size - 11 if dx > 0 else 11 - size if dx < 0 else 0), dy, anchor) for dx, dy, anchor in AROUND)
    return (x, y), label, colour, font, where, True
