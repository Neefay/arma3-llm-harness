"""What hurts soldiers going through VR's big houses with no enemy anywhere? Eight soldiers are walked through every
position of the village's two biggest houses, the way CLEAR does, and every wound ACE records is logged with its cause,
the body part, and where the man was standing.

    spike_wounds.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "move_lag"))
from spike_lib import in_fresh_game  # noqa: E402

harness, run = in_fresh_game("commander")


def run_args(code: str, args: list):
    res = harness.exec(code, "server", timeout=30, args=args, strip=False)
    result = res["results"][0] if res.get("results") else res
    if not res.get("ok") or result.get("errors"):
        raise RuntimeError(str(result)[:1500])
    return result.get("r")


time.sleep(10)
only = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].lstrip("-").isdigit() else -1
print("houses", run_args("""
{ deleteVehicle _x } forEach (missionNamespace getVariable ["spike_men", []]);
spike_wounds = [];
if (isNil "spike_woundHandler") then {
    spike_woundHandler = ["ace_medical_woundReceived", {
        params ["_unit", "_damages", "_shooter", "_type"];
        if (_unit in (missionNamespace getVariable ["spike_men", []])) then {
            spike_wounds pushBack [round time, name _unit, _type,
                _damages apply { [_x # 1, round ((_x # 0) * 100) / 100] },
                round (((getPosATL _unit) # 2) * 10) / 10, round ((speed _unit) * 10) / 10,
                typeOf (nearestBuilding _unit), isNull _shooter, _shooter isEqualTo _unit];
        };
    }] call CBA_fnc_addEventHandler;
};
spike_houses = ((nearestObjects [[4150, 4150], ["House"], 250]) select { count (_x buildingPos -1) > 0 }) apply {
    [count (_x buildingPos -1), _x] };
spike_houses sort false;
spike_houses = (spike_houses select [0, 2]) apply { _x # 1 };
if (_this # 0 >= 0) then { spike_houses = [spike_houses # (_this # 0)] };
private _g = createGroup [west, true];
for "_i" from 1 to 8 do { _g createUnit ["B_Soldier_F", (spike_houses # 0) getPos [30, 180 + 5 * _i], [], 0, "NONE"] };
spike_men = units _g;
spike_spots = [];
{ spike_spots append (_x buildingPos -1) } forEach spike_houses;
spike_houses apply { [typeOf _x, count (_x buildingPos -1), (getPosATL _x) apply { round _x }] }
""", [only]))
started = time.time()
while time.time() - started < 300:
    time.sleep(3)
    run("""
    {
        if (alive _x and { unitReady _x or { time > (_x getVariable ["spike_by", 0]) } }
            and { spike_spots isNotEqualTo [] }) then {
            private _spot = spike_spots deleteAt 0;
            _x doMove _spot;
            _x setVariable ["spike_spot", _spot];
            _x setVariable ["spike_by", time + 45];
        };
        private _legs = _x getHitPointDamage "hitLegs";
        if (_legs > (_x getVariable ["spike_legs", 0]) + 0.01) then {
            spike_wounds pushBack [round time, name _x, "legs", round (_legs * 100) / 100,
                round (((getPosATL _x) # 2) * 10) / 10, (_x getVariable ["spike_spot", []]) apply { round (_x * 10) / 10 },
                round ((velocity _x # 2) * 10) / 10];
        };
        _x setVariable ["spike_legs", _legs];
    } forEach spike_men;
    true
    """)
    wounds = run("spike_wounds")
    if wounds:
        print(round(time.time() - started), "wounds so far", len(wounds), flush=True)
print("spots left", run("count spike_spots"))
for row in run("spike_wounds"):
    print("  ", row)
print("state", run("""spike_men apply { [name _x, alive _x, lifeState _x,
    round ((_x getHitPointDamage "hitLegs") * 100) / 100] }"""))
print(harness.stop() if "--stop" in sys.argv else "game left up")
