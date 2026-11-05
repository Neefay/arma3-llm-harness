"""Can AI soldiers actually walk out of, and into, a mission's buildings? Some house models trap them.

    host\\.venv\\Scripts\\python.exe host\\tests\\live_buildings.py [mission] [x y radius]

Boots a headless game if none is running, and shuts down one it booted. For each enterable building, one lone soldier
starts at each sampled position and walks away, and another walks in from outside. A soldier that can't get in or out
makes a poor garrison and an impossible one to clear, so check any building before a scenario relies on it.
"""
from __future__ import annotations

import json
import sys
import time

from arma_harness.harness import Harness

WALK_S = 90
SAMPLES_PER_BUILDING = 6


def run(harness: Harness, code: str, args: list | None = None):
    res = harness.exec(code, "server", timeout=30, args=args, strip=False)
    result = res["results"][0] if res.get("results") else res
    if not res.get("ok") or result.get("errors"):
        raise RuntimeError(json.dumps(result)[:900])
    return result.get("r")


PLACE = """
params ["_centre", "_radius", "_samples"];
brmh_trial = [];
{
	private _building = _x;
	private _spots = _building buildingPos -1;
	private _step = ((count _spots) / _samples) max 1;
	private _i = 0;
	while {_i < count _spots} do {
		private _spot = _spots # floor _i;
		private _bearing = 60 * count brmh_trial;
		private _away = _building getPos [45, _bearing];
		private _out = (createGroup [west, false]) createUnit ["B_Soldier_F", [0, 0, 0], [], 0, "CAN_COLLIDE"];
		_out setPosATL _spot;
		_out doMove _away;
		private _start = _building getPos [35, _bearing];
		private _in = (createGroup [west, false]) createUnit ["B_Soldier_F", _start, [], 0, "NONE"];
		_in doMove _spot;
		brmh_trial pushBack [typeOf _building, (getPosATL _building) apply {round _x}, _spot, _away, _out, _in];
		_i = _i + _step;
	};
} forEach (nearestObjects [_centre + [0], ["House"], _radius] select {
	count (_x buildingPos -1) > 0
});
count brmh_trial
"""
RESULTS = """
brmh_trial apply {
	_x params ["_type", "_at", "_spot", "_away", "_out", "_in"];
	[_type, _at, round (_out distance2D _away), round (_in distance _spot)]
}
"""


def main() -> int:
    mission = sys.argv[1] if len(sys.argv) > 1 else "commander"
    x, y, radius = (float(value) for value in sys.argv[2:5]) if len(sys.argv) >= 5 else (4110.0, 4160.0, 200.0)
    harness = Harness()
    booted = harness.state() is None
    if booted:
        harness.start(mission=mission)
    time.sleep(8)
    try:
        print(f"{run(harness, PLACE, [[x, y], radius, SAMPLES_PER_BUILDING])} soldiers walking", flush=True)
        time.sleep(WALK_S)
        table: dict[str, list[int]] = {}
        for kind, at, out_left, in_left in run(harness, RESULTS):
            entry = table.setdefault(f"{kind} {at[:2]}", [0, 0, 0])
            entry[0] += 1
            entry[1] += out_left <= 15
            entry[2] += in_left <= 3
        bad = 0
        for name, (count, out_ok, in_ok) in sorted(table.items()):
            trapped = out_ok < count * 0.8 or in_ok < count * 0.5
            bad += trapped
            print(f"{'TRAP' if trapped else 'ok  '}  out {out_ok}/{count}  in {in_ok}/{count}  {name}", flush=True)
        return 1 if bad else 0
    finally:
        if booted:
            harness.stop()


if __name__ == "__main__":
    sys.exit(main())
