"""Sets up a garrisoned scenario and reports what the reachability probe found and where the garrison went.

    spike_probe.py stratis_maxwell
"""
import sys
import time

from arma_harness.commander import operator
from arma_harness.harness import Harness

harness = Harness()
started = time.time()
operator.start(sys.argv[1] if len(sys.argv) > 1 else "stratis_maxwell", None, harness)
print(f"setup took {time.time() - started:.0f} s", flush=True)


def run(code: str):
    res = harness.exec(code, "server", timeout=30, strip=False)
    result = res["results"][0] if res.get("results") else res
    if not res.get("ok") or result.get("errors"):
        raise RuntimeError(str(result)[:1500])
    return result.get("r")


print("probe", run("""
brmh_cmd_probe params ["_done", "_reachable"];
[_done, count _reachable]
"""))
print("by house", run("""
private _byHouse = createHashMap;
{
    private _house = nearestBuilding _x;
    private _key = format ["%1 %2", typeOf _house, (getPosATL _house) apply { round _x }];
    _byHouse set [_key, (_byHouse getOrDefault [_key, 0]) + 1];
} forEach (brmh_cmd_probe # 1);
_byHouse toArray false
"""))
print("garrison", run("""
private _g = (brmh_cmd_enemies select { groupId _x isEqualTo "East Garrison" }) # 0;
(units _g) apply {
    private _h = nearestBuilding _x;
    [typeOf _h, (getPosATL _h) apply { round _x }, round ((getPosATL _x) # 2 * 10) / 10]
}
"""))
print("walkers left", run("count (allUnits select { side _x isEqualTo civilian })"))
print(harness.stop() if "--stop" in sys.argv else "game left up")
