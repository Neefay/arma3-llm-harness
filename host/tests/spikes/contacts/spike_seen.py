"""After setting up contacts_check: what can Alpha's leader see of each enemy vehicle, what does he know of it, and what
do the contacts say? Separates "nothing visible" from "contacts broken"."""
import sys
import time

from arma_harness.commander import operator
from arma_harness.harness import Harness

harness = Harness()
operator.start("contacts_check", None, harness, seed=1)


def run(code: str):
    res = harness.exec(code, "server", timeout=30, strip=False)
    result = res["results"][0] if res.get("results") else res
    if not res.get("ok") or result.get("errors"):
        raise RuntimeError(str(result)[:1500])
    return result.get("r")


if "--as-scene" in sys.argv:  # as the live scene sets the squad up: holding fire, ignored, and pinned
    run('private _g = brmh_cmd_stations get "Alpha"; _g setCombatMode "BLUE"; _g allowFleeing 0; '
        '{ _x setCaptive true; _x disableAI "PATH" } forEach units _g; true')
for _ in range(5):
    time.sleep(15)
    print(run("""
    private _l = leader (brmh_cmd_stations get "Alpha");
    [((values brmh_cmd_vehicles) select { _x getVariable ["brmh_cmd_spawned", false] }) apply {
        [typeOf _x, round (_l distance _x),
         round (([_l, "VIEW", _x] checkVisibility [eyePos _l, (getPosASL _x) vectorAdd [0, 0, 1.2]]) * 100) / 100,
         round ((_l knowsAbout _x) * 10) / 10, count crew _x, behaviour _l, combatMode _l]
    }, ([_l] call brmh_cmd_fnc_contacts) apply { [_x get "kind", _x get "name", _x get "key", round (_x get "age_s")] },
     count (_l targets [true, 2000])]
    """), flush=True)
print(harness.stop() if "--stop" in sys.argv else "game left up")
