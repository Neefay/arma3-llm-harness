"""The ground, as a commander's paper map shows it: heights, water, woods, roads, buildings and named places.

Collected once when a battle starts, by brmh_cmd_fnc_terrain, which sees only the world itself and never what a mission
placed. Everything here is a pure function of that, so the commander can ask about the ground without the live game
being read at all. It's common knowledge, in every stratum of the model (docs/COMMANDER_MODEL.md).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .reports import compass

EYE_M = 1.8  # a man standing, for line of sight
# Trees and bushes per hectare, as a man would describe the ground there. On Stratis half the land has fewer than 15
# trees a hectare and a tenth has more than 75.
SCATTERED_PER_HA = 20
WOODS_PER_HA = 80
SCRUB_PER_HA = 50
COVER_AROUND_M = 50  # cover is judged over the ground around a point, not one tree's worth of it
# A grid only puts someone within its 100 m square, so ground this close to either end of a sight line can't be said to
# be in the way: he could be standing on it, or past it.
SIGHT_SLACK_M = 50
HILLTOP_NEAR_M = 600  # a higher top within this, from a slope, is worth naming
_ROAD_WORDS = {"MAIN ROAD": "main road", "ROAD": "road", "TRACK": "track", "TRAIL": "trail"}
_PLACE_KINDS = {"NameCityCapital": "town", "NameCity": "town", "NameVillage": "village", "NameLocal": "place",
                "NameMarine": "bay", "Airport": "airfield", "Hill": "hill"}


@dataclass
class Terrain:
    x0: float
    y0: float
    step: float
    n: int
    cells: list[list[int]] = field(default_factory=list)  # [height, water, trees, bushes], rows from the south-west
    roads: list[list] = field(default_factory=list)  # [x1, y1, x2, y2, kind]
    houses: list[list] = field(default_factory=list)  # [x, y, width, length, direction]
    places: list[list] = field(default_factory=list)  # [name, type, x, y]
    # Worked out once from the above, never saved: contour segments by height.
    contours: dict = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_game(cls, raw: list) -> Terrain:
        """From what brmh_cmd_fnc_terrain returns."""
        (x0, y0, step, n), cells, roads, houses, places = raw
        return cls(x0, y0, step, int(n), cells, roads, houses, places)

    @classmethod
    def load(cls, saved: dict | None) -> Terrain | None:
        return cls(**saved) if saved else None

    def to_dict(self) -> dict:
        return {"x0": self.x0, "y0": self.y0, "step": self.step, "n": self.n, "cells": self.cells, "roads": self.roads,
                "houses": self.houses, "places": self.places}

    # -- what's at a point ---------------------------------------------------------------------------------------

    def covers(self, x: float, y: float) -> bool:
        span = self.step * self.n
        return self.x0 <= x <= self.x0 + span and self.y0 <= y <= self.y0 + span

    def _cell(self, i: int, j: int) -> list[int]:
        i, j = min(max(i, 0), self.n - 1), min(max(j, 0), self.n - 1)
        return self.cells[j * self.n + i]

    def height(self, x: float, y: float) -> float:
        """Between the sampled cell centres, interpolated."""
        fx, fy = (x - self.x0) / self.step - 0.5, (y - self.y0) / self.step - 0.5
        i, j = math.floor(fx), math.floor(fy)
        tx, ty = fx - i, fy - j
        h = [self._cell(i + di, j + dj)[0] for dj in (0, 1) for di in (0, 1)]
        return (h[0] * (1 - tx) + h[1] * tx) * (1 - ty) + (h[2] * (1 - tx) + h[3] * tx) * ty

    def _nearest(self, x: float, y: float) -> list[int]:
        return self._cell(int((x - self.x0) // self.step), int((y - self.y0) // self.step))

    def water(self, x: float, y: float) -> bool:
        return bool(self._nearest(x, y)[1])

    def per_ha(self, cell: list[int]) -> tuple[float, float]:
        """Trees and bushes per hectare in a cell, which counts them within half a step of its centre."""
        area_ha = math.pi * (self.step / 2) ** 2 / 10_000
        return cell[2] / area_ha, (cell[3] if len(cell) > 3 else 0) / area_ha

    def cover(self, x: float, y: float) -> tuple[float, float]:
        """Trees and bushes per hectare, averaged over the cells around a point."""
        reach = max(0, round(COVER_AROUND_M / self.step))
        i, j = int((x - self.x0) // self.step), int((y - self.y0) // self.step)
        rows = [self.per_ha(self._cell(i + di, j + dj)) for di in range(-reach, reach + 1)
                for dj in range(-reach, reach + 1)]
        return sum(row[0] for row in rows) / len(rows), sum(row[1] for row in rows) / len(rows)

    def ground(self, x: float, y: float) -> str:
        if self.water(x, y):
            return "water"
        trees, bushes = self.cover(x, y)
        if trees >= WOODS_PER_HA:
            return "woods"
        if bushes >= SCRUB_PER_HA:
            return "scrub with scattered trees" if trees >= SCATTERED_PER_HA else "scrub"
        return "scattered trees" if trees >= SCATTERED_PER_HA else "open ground"

    def slope(self, x: float, y: float) -> tuple[float, float]:
        """Rise over run, and the bearing the ground falls away towards."""
        d = self.step
        dx = (self.height(x + d, y) - self.height(x - d, y)) / (2 * d)
        dy = (self.height(x, y + d) - self.height(x, y - d)) / (2 * d)
        return math.hypot(dx, dy), math.degrees(math.atan2(-dx, -dy)) % 360

    # -- what's near it -------------------------------------------------------------------------------------------

    def nearest_road(self, x: float, y: float) -> tuple[float, str, float, float] | None:
        """Distance, kind and the offset to the nearest point on a road or track, ignoring the airfield's own strips."""
        best = None
        for x1, y1, x2, y2, kind in self.roads:
            if kind not in _ROAD_WORDS:
                continue
            vx, vy = x2 - x1, y2 - y1
            length = vx * vx + vy * vy
            t = 0.0 if length == 0 else max(0.0, min(1.0, ((x - x1) * vx + (y - y1) * vy) / length))
            px, py = x1 + t * vx, y1 + t * vy
            distance = math.hypot(px - x, py - y)
            if best is None or distance < best[0]:
                best = (distance, _ROAD_WORDS[kind], px - x, py - y)
        return best

    def nearest_place(self, x: float, y: float) -> tuple[float, str, float, float] | None:
        best = None
        for name, _kind, px, py in self.places:
            distance = math.hypot(px - x, py - y)
            if best is None or distance < best[0]:
                best = (distance, name, px - x, py - y)
        return best

    def houses_within(self, x: float, y: float, radius: float) -> int:
        return sum(1 for hx, hy, *_ in self.houses if math.hypot(hx - x, hy - y) <= radius)

    def spot_heights(self, limit: int = 12, apart_m: float = 400) -> list[tuple[float, float, int]]:
        """Hilltops: cells higher than every neighbour, highest first, kept apart so a ridge doesn't fill the map."""
        tops = []
        for j in range(1, self.n - 1):
            for i in range(1, self.n - 1):
                h, water = self._cell(i, j)[:2]
                if water or any(self._cell(i + di, j + dj)[0] > h for di in (-1, 0, 1) for dj in (-1, 0, 1)):
                    continue
                tops.append((self.x0 + (i + 0.5) * self.step, self.y0 + (j + 0.5) * self.step, h))
        kept: list[tuple[float, float, int]] = []
        for top in sorted(tops, key=lambda t: -t[2]):
            if all(math.hypot(top[0] - k[0], top[1] - k[1]) >= apart_m for k in kept):
                kept.append(top)
            if len(kept) == limit:
                break
        return kept

    # -- in words -------------------------------------------------------------------------------------------------

    def describe(self, x: float, y: float, grid: str) -> str:
        """What a map and a look at the ground would tell you about a grid."""
        if not self.covers(x, y):
            return f"Grid {grid} is off your map."
        h = round(self.height(x, y))
        if self.water(x, y):
            return f"Grid {grid}: water."
        rise, falls = self.slope(x, y)
        steepness = "gentle" if rise < 0.10 else "moderate" if rise < 0.25 else "steep"
        lie = ("flat" if rise < 0.03
               else f"a {steepness} slope ({round(rise * 100)}%), falling to the {compass_word(falls)}")
        top = None
        if rise < 0.15 and self._is_top(x, y):
            lie = "a hilltop"
        else:
            top = self.nearest_top(x, y, h)
        words = [f"Grid {grid}: {h} m, {lie}. {self.ground(x, y).capitalize()}."]
        if top:
            words.append(f"Hilltop {top[2]} m: {_rough(math.dist((x, y), top[:2]))} m "
                         f"{compass(top[0] - x, top[1] - y)}.")
        road = self.nearest_road(x, y)
        if road and road[0] <= 400:
            where = "on it" if road[0] < 15 else f"{_rough(road[0])} m {compass(road[2], road[3])}"
            words.append(f"Nearest {road[1]}: {where}.")
        count = self.houses_within(x, y, 150)
        if count:
            words.append(f"{count} building{'s' if count != 1 else ''} within 150 m.")
        place = self.nearest_place(x, y)
        if place and place[0] <= 1500:
            where = "here" if place[0] < 150 else f"{_rough(place[0])} m {compass(place[2], place[3])}"
            words.append(f"{place[1]}: {where}.")
        return " ".join(words)

    def nearest_top(self, x: float, y: float, h: float) -> tuple[float, float, int] | None:
        """The nearest hilltop higher than here, if one is close enough to be the hill this is on."""
        tops = [top for top in self.spot_heights(limit=200, apart_m=150)
                if top[2] >= h + 5 and 60 <= math.dist((x, y), top[:2]) <= HILLTOP_NEAR_M
                and self._uphill_to(x, y, h, top)]
        top = min(tops, key=lambda top: math.dist((x, y), top[:2]), default=None)
        named = top and any(math.dist(top[:2], (px, py)) <= 100 for _, _, px, py in self.places)
        return None if named else top  # a named hill is said by its name, with the places

    def _uphill_to(self, x: float, y: float, h: float, top: tuple[float, float, int]) -> bool:
        """Whether the way to a top never drops below here: a top across a valley is another hill."""
        return all(self.height(x + (top[0] - x) * k / 8, y + (top[1] - y) * k / 8) >= h - 2 for k in range(1, 8))

    def _is_top(self, x: float, y: float) -> bool:
        h = self.height(x, y)
        around = [self.height(x + dx * self.step, y + dy * self.step) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                  if dx or dy]
        return max(around) <= h + 1 and sum(around) / len(around) <= h - 2  # and not just flat

    def line_of_sight(self, a: tuple[float, float], b: tuple[float, float]) -> tuple[bool, tuple[float, float, float]]:
        """Whether the ground alone hides b from a man standing at a, and the highest point in the way if it does.
        Trees and buildings aren't counted: the ground is all a map shows."""
        (ax, ay), (bx, by) = a, b
        eye_a, eye_b = self.height(ax, ay) + EYE_M, self.height(bx, by) + EYE_M
        length = math.hypot(bx - ax, by - ay)
        steps = max(2, int(length / (self.step / 4)))
        slack = min(SIGHT_SLACK_M, length / 4) / length if length else 0
        worst = None
        for k in range(1, steps):
            t = k / steps
            if t < slack or t > 1 - slack:
                continue
            x, y = ax + t * (bx - ax), ay + t * (by - ay)
            above = self.height(x, y) - (eye_a + t * (eye_b - eye_a))
            if above > 0 and (worst is None or above > worst[0]):
                worst = (above, (x, y, self.height(x, y)))
        return (worst is None), (worst[1] if worst else (0.0, 0.0, 0.0))

    def sight_words(self, a: tuple[float, float], a_grid: str, b: tuple[float, float], b_grid: str,
                    grid_of) -> str:
        if not (self.covers(*a) and self.covers(*b)):
            return "One of those grids is off your map."
        clear, (x, y, h) = self.line_of_sight(a, b)
        start = (f"From grid {a_grid} ({round(self.height(*a))} m) to grid {b_grid} ({round(self.height(*b))} m), "
                 f"{_rough(math.dist(a, b))} m:")
        tail = " Trees and buildings aren't counted."
        if clear:
            return f"{start} the ground doesn't hide one from the other.{tail}"
        return f"{start} the ground hides one from the other, rising to {round(h)} m at grid {grid_of(x, y)}.{tail}"


def compass_word(bearing: float) -> str:
    return compass(math.sin(math.radians(bearing)), math.cos(math.radians(bearing)))


def _rough(metres: float) -> int:
    step = 10 if metres < 100 else 50
    return int(round(metres / step) * step)


def place_kind(kind: str) -> str:
    return _PLACE_KINDS.get(kind, "place")
