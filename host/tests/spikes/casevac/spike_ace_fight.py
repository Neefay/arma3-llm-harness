"""Does the harness run with ACE, what are the medical defaults, and in a real firefight how do men go down under ACE?

The owner's assumption to test: without ACE men die rather than limp, and with ACE they mostly fall unconscious.
"""
import time

from spike_ace_lib import AREA, SQUAD, STATE, game, run, show

SETTINGS = """
private _out = [];
{
    private _name = toLowerANSI _x;
    if (("ace_medical" in _name) and {
        ("fatal" in _name) or ("unconscious" in _name) or ("threshold" in _name) or ("cardiac" in _name)
        or ("wake" in _name) or ("bleed" in _name) or ("medic" in _name) or ("_ai_" in _name) or ("location" in _name)
        or ("coef" in _name)
    }) then {
        _out pushBack [_x, missionNamespace getVariable [_x, "unset"]];
    };
} forEach (uiNamespace getVariable ["cba_settings_allSettings", cba_settings_allSettings]);
_out
"""

harness = game()
show("ace loaded", run(harness, """
["ace_common", "ace_medical", "ace_medical_ai", "ace_dragging"] apply {
    [_x, isClass (configFile >> "CfgPatches" >> _x)]
}
"""))
for name, value in run(harness, SETTINGS) or []:
    print(f"  {name} = {value}", flush=True)

run(harness, f"""
brmh_w = createGroup [west, false];
brmh_e = createGroup [east, false];
for "_i" from 0 to 11 do {{
    brmh_w createUnit ["B_Soldier_F", [{AREA[0]} + _i * 4, {AREA[1]}, 0], [], 0, "CAN_COLLIDE"];
    brmh_e createUnit ["O_Soldier_F", [{AREA[0]} + _i * 4, {AREA[1]} + 150, 0], [], 0, "CAN_COLLIDE"];
}};
brmh_died = [];
{{
    _x addEventHandler ["Killed", {{
        params ["_unit"];
        brmh_died pushBack [time, name _unit, _unit getVariable ["ACE_isUnconscious", false]];
    }}];
}} forEach (units brmh_w + units brmh_e);
brmh_all = units brmh_w + units brmh_e;
["ace_unconscious", {{
    params ["_unit", "_state"];
    brmh_uncon = (missionNamespace getVariable ["brmh_uncon", []]) + [[time, name _unit, _state]];
}}] call CBA_fnc_addEventHandler;
true
""")
for step in range(10):
    time.sleep(15)
    rows = run(harness, f"[brmh_all] call {{ {STATE} }}")
    alive = [row for row in rows if row[1]]
    print(f"{(step + 1) * 15:3d}s alive {len(alive):2d} unconscious {sum(row[2] for row in alive):2d} "
          f"injured {sum(row[3] == 'INJURED' for row in alive):2d} captive {sum(row[4] for row in alive):2d} "
          f"cardiac {sum(row[6] for row in alive):2d} dead {len(rows) - len(alive):2d}", flush=True)
show("final", run(harness, f"[brmh_all] call {{ {STATE} }}"))
show("unconscious events", run(harness, 'missionNamespace getVariable ["brmh_uncon", []]'))
show("deaths", run(harness, "brmh_died"))
harness.stop()
