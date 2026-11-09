"""The strike machine on a real game, watched from inside: its state, bombs released, and where the aircraft is against
the grid, every few seconds. For when the live scene's radio lines aren't enough to see what went wrong.

    spike_strike.py [scenario] [bombs] [heading] [--no-enemy] [--stop]
"""
import sys
import time

from arma_harness.commander import operator
from arma_harness.harness import Harness

args = [a for a in sys.argv[1:] if not a.startswith("--")]
scenario = args[0] if args else "stratis_strike"
bombs = int(args[1]) if len(args) > 1 else 2
heading = float(args[2]) if len(args) > 2 else -1
AIM = [3750, 2450]
harness = Harness()
operator.start(scenario, None, harness, seed=1)


def run(code: str, args: list | None = None):
    res = harness.exec(code, "server", timeout=30, args=args, strip=False)
    result = res["results"][0] if res.get("results") else res
    if not res.get("ok") or result.get("errors"):
        raise RuntimeError(str(result)[:1500])
    return result.get("r")


since = harness.bridge().cursor()
if "--no-enemy" in sys.argv:  # does the pilot's run bend around the enemy on the grid?
    print("enemy removed", run("""
    private _gone = allUnits select { side group _x isEqualTo east };
    private _guns = (values brmh_cmd_vehicles) select { crew _x findIf { side group _x isEqualTo east } >= 0 };
    { deleteVehicle _x } forEach _guns;
    { deleteVehicle _x } forEach _gone; count _gone
    """))
print("bomb weapon", run('[vehicle leader (brmh_cmd_stations get "Hog")] call brmh_cmd_fnc_bombWeapon'))
run("""
spike_impacts = [];
private _hog = vehicle leader (brmh_cmd_stations get "Hog");
_hog addEventHandler ["Fired", {
    params ["", "", "", "", "_ammo", "", "_projectile"];
    _projectile addEventHandler ["Explode", {
        params ["_projectile", "_pos"];
        spike_impacts pushBack [round time, typeOf _projectile, round (_pos distance2D [3750, 2450])];
    }];
}];
[brmh_cmd_stations get "Hog", "S-1", _this # 0, _this # 1, _this # 2] call brmh_cmd_fnc_strikeOrder; true
""", [AIM, bombs, heading])
started = time.time()
while time.time() - started < 360:
    time.sleep(4)
    row = run("""
    private _m = brmh_cmd_builds select { ((_x get "SPEC") get "KIND") isEqualTo "strike" };
    private _v = vehicle leader (brmh_cmd_stations get "Hog");
    private _aim = [3750, 2450, 0];
    [round time, if (_m isEqualTo []) then { "ended" } else { (_m # 0) get "STATE" },
     if (_m isEqualTo []) then { -1 } else { [_m # 0] call brmh_cmd_fnc_strikeReleased },
     round ([_v, ATLToASL _aim] call brmh_cmd_fnc_offTrack),
     round (_v distance2D _aim), round (((_v getRelDir _aim) + 180) mod 360 - 180), round ((getPosATL _v) # 2),
     round speed _v, (waypoints group driver _v) apply { (waypointPosition _x) apply { round _x } },
     currentWaypoint group driver _v, (brmh_cmd_fnc_careSay isEqualType {}) and true,
     ((group driver _v) getVariable ["brmh_cmd_care", []]) apply { [_x # 4, _x # 5] }]
    """)
    print(row, flush=True)
    if row[1] == "ended":
        break
time.sleep(25)
print("impacts", run("spike_impacts"))
errors = harness.events(since=since, kinds=["err"], limit=0).get("events", [])
print("script errors:", errors[:3] if errors else "none")
print(harness.stop() if "--stop" in sys.argv else "game left up")
