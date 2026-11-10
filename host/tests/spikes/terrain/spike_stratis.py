"""What Stratis looks like to a commander: its grid, its places, and what sampling its terrain costs. Read-only."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "move_lag"))
from spike_lib import in_fresh_game  # noqa: E402

harness, run = in_fresh_game("commander_stratis")
print("world", run("[worldName, worldSize, mapGridPosition [3450, 3050, 0], mapGridPosition [3450, 3050, 0] isEqualTo \"034030\"]"))
print("observer", run("private _p = getPosATL ((allUnits select {side _x isEqualTo west}) param [0, objNull]); [_p, surfaceIsWater _p]"))

places = run("""
(nearestLocations [[4096, 4096], ["NameCityCapital", "NameCity", "NameVillage", "NameLocal", "Hill", "NameMarine",
    "Airport", "Mount", "ViewPoint", "StrongpointArea", "FlatArea", "FlatAreaCity", "CityCenter"], 6000]) apply {
    [text _x, type _x, mapGridPosition (locationPosition _x), round (getTerrainHeightASL (locationPosition _x))]
}
""")
print(len(places), "places")
for row in places:
    print("  ", row)

for step, radius in ((25, 600), (50, 1200)):
    started = time.time()
    sample = run(f"""
    private _c = [3900, 5100];
    private _n = round ({radius} * 2 / {step});
    private _h = [];
    for "_j" from 0 to _n - 1 do {{
        for "_i" from 0 to _n - 1 do {{
            private _p = [(_c # 0) - {radius} + (_i + 0.5) * {step}, (_c # 1) - {radius} + (_j + 0.5) * {step}];
            _h pushBack [round (getTerrainHeightASL _p), [0, 1] select (surfaceIsWater _p),
                count (nearestTerrainObjects [_p, ["TREE", "SMALL TREE", "BUSH"], {step} / 2, false, true])];
        }};
    }};
    [_n, count _h, _h select [0, 3]]
    """)
    print(f"sample {step} m over {radius} m radius:", sample[0], "x", sample[0], "cells,", f"{time.time() - started:.1f} s", sample[2])

started = time.time()
roads = run("""
private _roads = [3900, 5100] nearRoads 1200;
private _kinds = createHashMap;
{ private _k = (getRoadInfo _x) # 0; _kinds set [_k, (_kinds getOrDefault [_k, 0]) + 1]; } forEach _roads;
[count _roads, _kinds toArray false, ((_roads select [0, 2]) apply { [getPosATL _x, roadsConnectedTo _x apply { getPosATL _x }] })]
""")
print("roads", roads[0], roads[1], f"{time.time() - started:.1f} s")
print("houses", run("count nearestTerrainObjects [[3900, 5100], [\"HOUSE\", \"BUILDING\", \"CHURCH\", \"CHAPEL\", \"BUNKER\", \"FORTRESS\", \"VIEW-TOWER\", \"LIGHTHOUSE\"], 1200, false, true]"))

# The fog check: something the mission places mustn't show up as terrain.
run('missionNamespace setVariable ["brmh_probe", createVehicle ["Land_i_House_Small_02_V1_F", [3905, 5105, 0], [], 0, "CAN_COLLIDE"]]; true')
print("a placed house, seen as terrain:", run('(nearestTerrainObjects [[3905, 5105], ["HOUSE"], 15, false, true]) apply { typeOf _x }'),
      " as an object:", run('(nearestObjects [[3905, 5105], ["House"], 15]) apply { typeOf _x }'))
print("a placed location, seen:", run('createLocation ["NameVillage", [3905, 5105], 50, 50] setText "Probe"; (nearestLocations [[3905, 5105], ["NameVillage"], 100]) apply { text _x }'))
harness.stop()
print("done")
