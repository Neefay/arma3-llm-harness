"""Draws the commander's map as a PNG, from what it already has: buildings, its markers, reported positions.

A pure function of its inputs, and nothing about the live game is one of them. The picture can't show more than the
commander has been told, which is the point.
"""
from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageFont

SIZE = 1000
_COLOURS = {"enemy": (190, 40, 30), "danger": (225, 120, 20), "hypothesis": (150, 70, 170), "objective": (30, 130, 70),
            "friendly": (25, 90, 170), "note": (90, 90, 90), "phase_line": (150, 100, 30), "area": (150, 100, 30)}
_PAPER, _GRID, _INK = (238, 240, 228), (205, 210, 195), (35, 40, 45)
_BUILDING, _CHECKED = (150, 145, 135), (120, 175, 125)


def render(center: list[float], radius: float, buildings: list[dict], markers: list[dict], positions: dict[str, dict],
           checked: dict[str, float], caption: str) -> bytes:
    """A square map around ``center``. Markers and positions hold grids in their spoken form, such as "041 041"."""
    image = Image.new("RGB", (SIZE, SIZE), _PAPER)
    draw = ImageDraw.Draw(image)
    scale = SIZE / (2 * radius)

    def xy(x: float, y: float) -> tuple[float, float]:
        return (x - center[0] + radius) * scale, SIZE - (y - center[1] + radius) * scale

    _grid(draw, center, radius, xy)
    small, medium = _font(13), _font(15)
    for building in buildings:
        corners = _footprint(building)
        fill = _CHECKED if building["id"] in checked else _BUILDING
        draw.polygon([xy(*corner) for corner in corners], fill=fill, outline=_INK)
    for building in buildings:
        draw.text(xy(*building["pos"]), building["id"], fill=_INK, font=small, anchor="mm", stroke_width=2,
                  stroke_fill=_PAPER)
    for marker in markers:
        _marker(draw, marker, xy, medium)
    for callsign, place in positions.items():
        x, y = xy(*_grid_centre(place["grid"]))
        draw.rectangle((x - 13, y - 9, x + 13, y + 9), outline=_COLOURS["friendly"], width=3)
        draw.line((x - 13, y - 9, x + 13, y + 9), fill=_COLOURS["friendly"], width=2)
        draw.line((x - 13, y + 9, x + 13, y - 9), fill=_COLOURS["friendly"], width=2)
        draw.text((x, y + 12), f"{callsign} ({place['age']})", fill=_COLOURS["friendly"], font=small, anchor="ma",
                  stroke_width=2, stroke_fill=_PAPER)
    draw.rectangle((0, 0, SIZE, 26), fill=_INK)
    draw.text((8, 13), caption, fill=_PAPER, font=small, anchor="lm")
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _font(size: int):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default(size)


def _grid(draw, center, radius, xy) -> None:
    step = 100 if radius <= 800 else 500 if radius <= 3000 else 1000
    label = _font(12)
    low_x, high_x = center[0] - radius, center[0] + radius
    low_y, high_y = center[1] - radius, center[1] + radius
    for x in range(int(low_x // step) * step, int(high_x) + step, step):
        draw.line((xy(x, low_y), xy(x, high_y)), fill=_GRID)
        draw.text((xy(x, low_y)[0] + 3, SIZE - 16), f"{x // 100:03d}", fill=_INK, font=label)
    for y in range(int(low_y // step) * step, int(high_y) + step, step):
        draw.line((xy(low_x, y), xy(high_x, y)), fill=_GRID)
        draw.text((3, xy(low_x, y)[1] - 15), f"{y // 100:03d}", fill=_INK, font=label)


def _footprint(building: dict) -> list[tuple[float, float]]:
    x, y = building["pos"]
    half_w, half_l = building.get("width", 8) / 2, building.get("length", 8) / 2
    angle = math.radians(building.get("dir", 0))
    cos, sin = math.cos(angle), math.sin(angle)
    return [(x + dx * cos + dy * sin, y - dx * sin + dy * cos)
            for dx, dy in ((-half_w, -half_l), (half_w, -half_l), (half_w, half_l), (-half_w, half_l))]


def _grid_centre(grid: str) -> list[float]:
    digits = grid.replace(" ", "")
    return [int(digits[:3]) * 100 + 50, int(digits[3:]) * 100 + 50]


def _marker(draw, marker: dict, xy, font) -> None:
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
        draw.text(points[0], label, fill=colour, font=font, anchor="ld", stroke_width=2, stroke_fill=_PAPER)
        return
    x, y = xy(*(marker.get("pos") or _grid_centre(at)))
    if marker["kind"] == "enemy" or marker["kind"] == "danger":
        draw.polygon([(x, y - 11), (x + 11, y), (x, y + 11), (x - 11, y)], outline=colour, width=3)
    elif marker["kind"] == "objective":
        draw.ellipse((x - 13, y - 13, x + 13, y + 13), outline=colour, width=3)
    else:
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), outline=colour, width=3)
    draw.text((x + 15, y), label, fill=colour, font=font, anchor="lm", stroke_width=2, stroke_fill=_PAPER)
