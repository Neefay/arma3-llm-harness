"""Why does the Blackfoot crewed as a station fly over a squad in the open and never fire, when the same helicopter
with its own crew engaged within 45 s? Sets up stratis_cas, sends the sortie directly, and watches the crew."""
import sys
import time

from arma_harness.commander import operator
from arma_harness.harness import Harness

harness = Harness()
operator.start("stratis_cas", None, harness)


def run(code: str):
    res = harness.exec(code, "server", timeout=30, strip=False)
    result = res["results"][0] if res.get("results") else res
    if not res.get("ok") or result.get("errors"):
        raise RuntimeError(str(result)[:1500])
    return result.get("r")


print("crew", run("""
private _g = brmh_cmd_stations get "Hawg"; private _v = vehicle leader _g;
[typeOf _v, (fullCrew _v) apply { [name (_x # 0), _x # 1] }, name leader _g, name effectiveCommander _v,
 behaviour leader _g, combatMode _g, captive leader _g, side _g]
"""))
run('[brmh_cmd_stations get "Hawg", "O-T", [3750, 2450], 200] call brmh_cmd_fnc_casOrder; true')
for _ in range(14):
    time.sleep(15)
    print(run("""
    private _g = brmh_cmd_stations get "Hawg"; private _v = vehicle leader _g;
    private _e = (brmh_cmd_enemies select { groupId _x isEqualTo "East Squad" }) # 0;
    [round (_v distance2D [3750, 2450]), round ((getPosATL _v) # 2), behaviour leader _g, combatMode _g,
     currentCommand driver _v, currentCommand gunner _v, round (((gunner _v) knowsAbout (leader _e)) * 10) / 10,
     round (((driver _v) knowsAbout (leader _e)) * 10) / 10, assignedTarget gunner _v,
     _v getVariable ["brmh_cmd_shots", 0],
     {alive _x} count units _e, (waypoints _g) apply { waypointType _x }, currentWaypoint _g,
     ["TARGET", "AUTOTARGET", "FSM", "WEAPONAIM"] apply { (gunner _v) checkAIFeature _x }]
    """), flush=True)
print(harness.stop() if "--stop" in sys.argv else "game left up")
