"""After setting up contacts_check: is each enemy vehicle's crew on board, and how does it sit on the ground?"""
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


for _ in range(4):
    print(run("""
    ((values brmh_cmd_vehicles) select { _x getVariable ["brmh_cmd_spawned", false] }) apply {
        [typeOf _x, count crew _x, (crew _x) apply { [typeOf _x, alive _x, typeOf vehicle _x] },
         (vectorUp _x) apply { round (_x * 100) / 100 }, round ((getPosATL _x) # 2 * 10) / 10, damage _x]
    }
    """), flush=True)
    print("   on foot nearby:", run("""
    (allUnits select { side group _x isEqualTo east and { vehicle _x isEqualTo _x } }) apply {
        [typeOf _x, groupId group _x, (getPosATL _x) apply { round _x }]
    }
    """), flush=True)
    time.sleep(5)
print(harness.stop() if "--stop" in sys.argv else "game left up")
