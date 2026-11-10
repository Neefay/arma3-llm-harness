"""An aircraft at the end of its time on station: does brmh_cmd_fnc_airLeave send it off, circling 5 km out, without
script errors, its crew alive and still the station's?"""
import sys
import time

from arma_harness.commander import operator
from arma_harness.harness import Harness

harness = Harness()
operator.start("stratis_cas", None, harness, seed=1)


def run(code: str):
    res = harness.exec(code, "server", timeout=30, strip=False)
    result = res["results"][0] if res.get("results") else res
    if not res.get("ok") or result.get("errors"):
        raise RuntimeError(str(result)[:1500])
    return result.get("r")


since = harness.bridge().cursor()
print("before", run('private _v = vehicle leader (brmh_cmd_stations get "Hawg"); [getPosATL _v apply {round _x}, '
                    'count crew _v]'))
run('["Hawg"] call brmh_cmd_fnc_airLeave; true')
for _ in range(6):
    time.sleep(10)
    print(run("""
    private _g = brmh_cmd_stations get "Hawg"; private _v = vehicle leader _g;
    [getPosATL _v apply {round _x}, round speed _v,
     (waypoints _g) apply { [waypointType _x, waypointPosition _x apply {round _x}] },
     count crew _v, { alive _x } count units _g, combatMode _g]
    """), flush=True)
errors = harness.events(since=since, kinds=["err"], limit=0).get("events", [])
print("script errors:", errors[:2] if errors else "none")
print(harness.stop() if "--stop" in sys.argv else "game left up")
