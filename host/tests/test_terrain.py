"""The commander's terrain: a synthetic island with one hill, a wood, a road and a village, read in words and drawn."""
from __future__ import annotations

import math
from io import BytesIO

import pytest
from PIL import Image
from test_commander import Battle

from arma_harness.commander import map as map_mod
from arma_harness.commander import scenario
from arma_harness.commander.operator import terrain_window
from arma_harness.commander.orders import Invalid
from arma_harness.commander.terrain import Terrain

STEP, N, X0, Y0 = 50, 40, 2000, 2000  # 2 km square from 020 020 to 040 040
HILL = (3000, 3200)  # grid 030 032


def island() -> Terrain:
    cells = []
    for j in range(N):
        for i in range(N):
            x, y = X0 + (i + 0.5) * STEP, Y0 + (j + 0.5) * STEP
            water = x < 2200  # the sea along the west edge
            height = -10 if water else round(10 + 150 * math.exp(-math.dist((x, y), HILL) ** 2 / 300 ** 2))
            wood = 3300 <= x <= 3600 and 2300 <= y <= 2600  # around 034 024
            cells.append([height, int(water), 20 if wood else 0, 0])
    roads = [[2400, 2100, 2400, 3900, "ROAD"], [2400, 2500, 3600, 2500, "TRACK"]]
    houses = [[2450, 2550, 8, 10, 0], [2460, 2600, 8, 10, 90], [2350, 2520, 6, 6, 45]]
    places = [["Pyrgos", "NameVillage", 2420, 2560], ["Hill 160", "Hill", 3000, 3200]]
    return Terrain(X0, Y0, STEP, N, cells, roads, houses, places)


def grid(x: float, y: float) -> str:
    return f"{int(x // 100):03d} {int(y // 100):03d}"


def test_heights_interpolate_and_the_hill_is_found():
    t = island()
    assert t.height(*HILL) == pytest.approx(160, abs=3)
    assert t.height(3500, 2000) < 20
    top = t.spot_heights(limit=3)[0]
    assert math.dist(top[:2], HILL) < 50 and top[2] >= 155


def test_a_point_in_words():
    t = island()
    assert t.describe(2100, 3000, "021 030") == "Grid 021 030: water."
    summit = t.describe(3025, 3225, "030 032")
    assert summit.startswith("Grid 030 032: 15") and "hilltop" in summit and "Hill 160: here." in summit
    flank = t.describe(3000, 2950, "030 029")
    assert "a steep slope (40%), falling to the south" in flank
    village = t.describe(2410, 2550, "024 025")
    assert "Nearest road: on it." in village and "3 buildings within 150 m." in village and "Pyrgos: here." in village
    assert "Woods." in t.describe(3450, 2450, "034 024")
    assert "Open ground." in t.describe(3800, 3800, "038 038")
    assert t.describe(5000, 5000, "050 050") == "Grid 050 050 is off your map."


def test_the_hill_hides_one_side_from_the_other():
    t = island()
    hidden = t.sight_words((3000, 2700), "030 027", (3000, 3700), "030 037", grid)
    assert "the ground hides one from the other, rising to" in hidden and "at grid 030 03" in hidden
    assert hidden.endswith("Trees and buildings aren't counted.")
    # From the foot, the hill's own shoulder hides its top, as it would.
    assert "hides" in t.sight_words((3000, 2700), "030 027", (3000, 3200), "030 032", grid)
    assert "doesn't hide" in t.sight_words((3800, 2200), "038 022", (3800, 3800), "038 038", grid)


def test_ground_ignores_mission_objects_and_roads_it_cannot_name():
    t = island()
    t.roads.append([3800, 3800, 3810, 3810, "HIDE"])  # an airfield's own strip, not something to name
    assert "Nearest" not in t.describe(3805, 3805, "038 038")


def test_round_trip_through_the_saved_file():
    t = island()
    again = Terrain.load(t.to_dict())
    assert again == t and Terrain.load(None) is None
    raw = [[X0, Y0, STEP, N], t.cells, t.roads, t.houses, t.places]
    assert Terrain.from_game(raw) == t


def test_the_map_draws_the_ground_under_the_beliefs():
    t = island()
    bare = map_mod.render([2800, 3000], 800, [], [], {}, {}, "test")
    drawn = map_mod.render([2800, 3000], 800, [], [], {}, {}, "test", terrain=t)
    sea = Image.open(BytesIO(drawn)).convert("RGB").getpixel((20, 530))  # x 2032, on neither a grid line nor the coast
    assert sea == map_mod._WATER
    assert Image.open(BytesIO(bare)).convert("RGB").getpixel((20, 530)) == map_mod._PAPER
    # Off the sampled square, the map is blank paper.
    far = map_mod.render([5000, 5000], 400, [], [], {}, {}, "test", terrain=t)
    assert Image.open(BytesIO(far)).convert("RGB").getpixel((510, 490)) == map_mod._PAPER


def flat(n=20, step=10, bumps=()) -> Terrain:
    """Level ground at 0 m, 200 m across, with some cells raised: [(i, j, height)]."""
    cells = [[0, 0, 0, 0] for _ in range(n * n)]
    for i, j, h in bumps:
        cells[j * n + i][0] = h
    return Terrain(0, 0, step, n, cells)


def test_a_crest_within_a_grid_square_of_either_end_is_not_in_the_way():
    """Stratis: a 2 m lip in the target's own square was called the ground hiding it, but a grid only puts someone
    within 100 m, so he could be standing on that lip."""
    near_the_end = flat(bumps=[(18, 10, 3)])  # x 185, 10 m short of the end
    assert near_the_end.line_of_sight((5, 105), (195, 105))[0]
    in_the_middle = flat(bumps=[(10, 10, 3)])
    clear, (x, _, h) = in_the_middle.line_of_sight((5, 105), (195, 105))
    assert not clear and 95 <= x <= 115 and h > 2


def test_a_slope_names_the_hilltop_it_rises_to():
    t = island()
    t.places.remove(["Hill 160", "Hill", 3000, 3200])
    assert "Hilltop 158 m: 250 m north." in t.describe(3000, 2950, "030 029")
    t.places.append(["Hill 160", "Hill", 3000, 3200])  # named, it's said once, by its name
    named = t.describe(3000, 2950, "030 029")
    assert "Hilltop" not in named and "Hill 160: 250 m north." in named
    assert "Hilltop" not in t.describe(3025, 3225, "030 032")  # on it already
    assert "Hilltop" not in t.describe(3800, 3800, "038 038")  # flat, and the hill is too far to be this one's


def test_labels_never_land_on_each_other():
    from PIL import ImageDraw

    labels = map_mod._Labels(ImageDraw.Draw(Image.new("RGB", (map_mod.SIZE, map_mod.SIZE))))
    font = map_mod._font(15)
    for text in ("E1 MG in the HQ", "O1 Camp Maxwell", "H1 patrol?"):
        assert labels.put((500, 500), text, (0, 0, 0), font, map_mod.AROUND, True)
    placed = labels.taken[1:]
    assert all(not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3])
               for k, a in enumerate(placed) for b in placed[k + 1:])
    # A label that doesn't have to be there is left out rather than drawn over the others.
    crowded = [(500, 500)] * 12
    dropped = [labels.put(at, "B12", (0, 0, 0), font, map_mod.CENTRED, False) for at in crowded]
    assert False in dropped


def test_nothing_is_drawn_past_the_edge_of_the_sheet():
    t = island()
    t.roads.append([4100, 3030, 4500, 3030, "ROAD"])  # off the sheet, which ends at 040
    drawn = Image.open(BytesIO(map_mod.render([4200, 3000], 400, [], [], {}, {}, "test", terrain=t))).convert("RGB")
    assert drawn.getpixel((662, 462)) == map_mod._PAPER  # x 4330, on that road
    assert drawn.getpixel((250, 300)) == map_mod._SHEET_EDGE  # x 4000: the sheet's edge, over the grid line there


def terrain_battle(tmp_path) -> Battle:
    b = Battle(tmp_path, ao={"at": "030 030", "radius": 600})
    b.runtime.terrain = island()
    b.runtime.buildings = [{"id": "B1", "pos": [2450, 2550], "at": "024 025", "name": "House", "positions": 4}]
    return b


def test_the_ground_tool(tmp_path):
    b = terrain_battle(tmp_path)
    with pytest.raises(Invalid):
        b.runtime.ground("030 032")  # the battle hasn't started
    b.start()
    assert "Hill 160: here." in b.runtime.ground("030 032")["text"]
    assert "Pyrgos: here." in b.runtime.ground("B1")["text"]
    b.runtime.mark({"id": "E1", "kind": "enemy", "at": "030 037"})
    assert "hides one from the other" in b.runtime.ground("030 027", "E1")["text"]
    with pytest.raises(Invalid, match="Bad grid"):
        b.runtime.ground("somewhere")
    b.runtime.terrain = None
    with pytest.raises(Invalid, match="no terrain"):
        b.runtime.ground("030 032")


def test_places_come_with_the_mission_nearest_first(tmp_path):
    b = terrain_battle(tmp_path)
    b.start()
    places = b.runtime.mission()["places"]
    assert places == [{"name": "Hill 160", "kind": "hill", "grid": "030 032"},
                      {"name": "Pyrgos", "kind": "village", "grid": "024 025"}]
    b.runtime.terrain = None
    assert "places" not in b.runtime.mission()


def test_the_map_caption_gives_the_contour_interval(tmp_path):
    b = terrain_battle(tmp_path)
    b.start()
    assert "Contours every 10 m." in b.runtime.map_image()["text"]
    assert "Contours every 20 m." in b.runtime.map_image(radius=2000)["text"]


def test_the_terrain_window_covers_the_scenario():
    raw = {"name": "t", "mission": "m", "text": "t", "time_limit": "1:00",
           "stations": [{"callsign": "A", "role": "r", "capabilities": [], "at": "030 021"}],
           "enemies": [{"id": "E", "at": "032 029", "units": 4, "mode": "garrison", "radius": 100}]}
    centre, radius = terrain_window(scenario.build(raw), 8192)
    assert centre == [3150, 2550] and radius == 1100
    with_ao = scenario.build({**raw, "ao": {"at": "031 025", "radius": 400}})
    centre, radius = terrain_window(with_ao, 8192)
    assert centre == [3150, 2550] and 1000 <= radius <= 1200
    far = scenario.build({**raw, "enemies": [{**raw["enemies"][0], "at": "080 080"}]})
    assert terrain_window(far, 8192)[1] == 3000
