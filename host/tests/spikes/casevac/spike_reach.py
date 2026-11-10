"""In the demo a medic stood still for good, going to a casualty whose body had settled at this spot inside a house.
Why, and what gets him there? Each test is a fresh medic and casualty, starting 55 m away as he did.
"""
import time

from spike_ace_lib import game, run, show

SPOT = [4147.46, 4128.64, 0.190602]
START = [4200, 4110, 0]

SETUP = """
missionNamespace setVariable ["ace_medical_spontaneousWakeUpChance", 0, true];
brmh_fnc_pair = {
    params ["_alone", "_lying"];
    private _group = createGroup [west, false];
    private _medic = _group createUnit ["B_medic_F", _this # 2, [], 0, "CAN_COLLIDE"];
    private _hurt = (createGroup [west, false]) createUnit ["B_Soldier_F", _lying, [], 0, "CAN_COLLIDE"];
    if (not _alone) then {
        [_hurt] joinSilent _group;
    };
    _group selectLeader _medic;
    _hurt setPosATL _lying;
    [_hurt, true, 0, false] call ace_medical_fnc_setUnconscious;
    {
        _x setVariable ["ace_medical_ai_lastFired", CBA_missionTime + 86400];
    } forEach [_medic, _hurt];
    [_medic, _hurt]
};
true
"""
READ = """
private _m = brmh_pair # 0;
private _h = brmh_pair # 1;
[round (_m distance2D brmh_start), round ((_m distance _h) * 10) / 10, round speed _m, currentCommand _m, unitReady _m,
 animationState _m]
"""


def trial(harness, title, alone, lying, go, seconds=40):
    print(f"\n=== {title}", flush=True)
    run(harness, f"""
    brmh_start = {START};
    brmh_pair = [{str(alone).lower()}, {lying}, {START}] call brmh_fnc_pair;
    true
    """)
    time.sleep(4)
    show("  body", run(harness, "[getPosATL (brmh_pair # 1), lifeState (brmh_pair # 1), animationState (brmh_pair # 1)]"))
    run(harness, go)
    begun = time.time()
    last = None
    while time.time() - begun < seconds:
        time.sleep(5)
        row = run(harness, READ)
        print(f"  {time.time() - begun:3.0f}s moved {row[0]:3d} m, {row[1]:5.1f} m from body, speed {row[2]:2d}, "
              f"{row[3]}, ready {row[4]}, {row[5][:32]}", flush=True)
        last = row
    run(harness, "{deleteVehicle _x} forEach brmh_pair; true")
    return last


def main():
    harness = game()
    run(harness, SETUP)
    print("paths", flush=True)
    run(harness, f"""
    brmh_paths = [];
    private _house = nearestObject [{SPOT}, "House"];
    {{
        private _agent = calculatePath ["man", "careless", {START}, _x];
        _agent setVariable ["label", str _x];
        _agent addEventHandler ["PathCalculated", {{
            params ["_agent", "_path"];
            brmh_paths pushBack [_agent getVariable "label", count _path, _path # (count _path - 1)];
        }}];
    }} forEach ([{SPOT}] + ((_house buildingPos -1) select {{(_x # 2) < 1}}));
    true
    """)
    time.sleep(8)
    show("  [to, steps, ends at]", run(harness, "brmh_paths"))
    show("  ground floor spots", run(harness, f"""
    (nearestObject [{SPOT}, "House"] buildingPos -1) select {{(_x # 2) < 1}}
    """))

    trial(harness, "1. As in the demo: doMove to where the body lies, in his group", False, SPOT,
          "(brmh_pair # 0) doMove (getPosATL (brmh_pair # 1)); true")
    trial(harness, "2. The same, with the casualty not in his group", True, SPOT,
          "(brmh_pair # 0) doMove (getPosATL (brmh_pair # 1)); true")
    near = """
    private _h = brmh_pair # 1;
    private _spots = (nearestObject [_h, "House"] buildingPos -1) select {(_x # 2) < 1};
    _spots = _spots apply {[_x distance _h, _x]};
    _spots sort true;
    (brmh_pair # 0) doMove ((_spots # 0) # 1);
    true
    """
    trial(harness, "3. doMove to the nearest ground floor position of the house", False, SPOT, near)
    trial(harness, "4. On open ground: doMove to him, in his group", False, [4240, 4000, 0],
          "(brmh_pair # 0) doMove (getPosATL (brmh_pair # 1)); true")
    trial(harness, "5. Open ground, 30 m away, with him in the group", False, SPOT,
          "(brmh_pair # 0) doMove [4170, 4110, 0]; true", 25)
    trial(harness, "6. LEADER DIRECT, to where the body lies", False, SPOT,
          """(brmh_pair # 0) setDestination [getPosATL (brmh_pair # 1), "LEADER DIRECT", true];
          (brmh_pair # 0) doMove (getPosATL (brmh_pair # 1)); true""")
    errors = harness.events(since=0, kinds=["err"]).get("events", [])
    print("\nscript errors", len(errors), [str(e.get("text"))[:160] for e in errors[:4]], flush=True)
    harness.stop()
    print("done", flush=True)


if __name__ == "__main__":
    main()
