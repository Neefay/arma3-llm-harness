"""Stratis's named places, from the world's own config, which no mission can add to. And what kinds of road it has."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "move_lag"))
from spike_lib import in_fresh_game  # noqa: E402

harness, run = in_fresh_game("commander_stratis")
places = run("""
("true" configClasses (configFile >> "CfgWorlds" >> worldName >> "Names")) apply {
    private _p = getArray (_x >> "position");
    [getText (_x >> "name"), getText (_x >> "type"), mapGridPosition _p, round getTerrainHeightASL _p]
} select { (_x # 0) isNotEqualTo "" }
""")
print(len(places), "named places")
for row in sorted(places, key=lambda r: r[2]):
    print("  ", row)
kinds = run("""
private _kinds = createHashMap;
{ private _k = (getRoadInfo _x) # 0; _kinds set [_k, (_kinds getOrDefault [_k, 0]) + 1]; } forEach ([4096, 4096] nearRoads 6000);
_kinds toArray false
""")
print("roads by kind, whole island:", kinds)
print("highest ground:", run("""
private _best = [0, [0, 0]];
for "_y" from 500 to 7700 step 100 do { for "_x" from 500 to 7700 step 100 do {
    private _h = getTerrainHeightASL [_x, _y]; if (_h > (_best # 0)) then { _best = [_h, [_x, _y]] }; }; };
[round (_best # 0), mapGridPosition (_best # 1)]
"""))
harness.stop()
print("done")
