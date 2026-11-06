"""The rest of what CASEVAC depends on, on the real game with ACE.

F: Three firefights at ACE's defaults: how many go down, die, get up. And what happens to the downed afterwards.
H: A rescue under fire: does the enemy shoot a downed man, or the medic dragging him?
I: A forward carry: the medic attached to a walking dummy, in ACE's carrying animation, at a quicker pace than a drag.
J: How long an untreated casualty lasts, and how many wake up alone.
L: Loading into a vehicle the squad's own man is driving: does the casualty stay in the group?
K: Killing a share of those who go down, by a handler.
"""
import math
import time

from spike_ace_lib import game, run, show

SETUP = """
brmh_fights = [];
brmh_fnc_fight = {
    params ["_x0", "_y0"];
    private _w = createGroup [west, false];
    private _e = createGroup [east, false];
    for "_i" from 0 to 11 do {
        _w createUnit ["B_Soldier_F", [_x0 + _i * 4, _y0, 0], [], 0, "CAN_COLLIDE"];
        _e createUnit ["O_Soldier_F", [_x0 + _i * 4, _y0 + 150, 0], [], 0, "CAN_COLLIDE"];
    };
    brmh_fights pushBack (units _w + units _e);
};
brmh_ever_down = createHashMap;
brmh_down_at = createHashMap;
brmh_up_at = createHashMap;
["ace_unconscious", {
    params ["_unit", "_state"];
    if (_state) then {
        brmh_ever_down set [name _unit, true];
        brmh_down_at set [name _unit, time];
    } else {
        brmh_up_at set [name _unit, time];
    };
}] call CBA_fnc_addEventHandler;
brmh_fnc_tally = {
    params ["_men"];
    private _alive = _men select {alive _x};
    private _downed = _alive select {_x getVariable ["ACE_isUnconscious", false]};
    [count _men, count _alive, count _downed, {_x getVariable ["ace_medical_inCardiacArrest", false]} count _alive,
     {lifeState _x isEqualTo "INJURED"} count _alive,
     {name _x in brmh_ever_down} count (_men select {not alive _x}), {name _x in brmh_ever_down} count _men]
};
true
"""

harness = game()
run(harness, SETUP)
started = time.time()

print("=== F: firefights, and J: casualties left untreated", flush=True)
for x, y in ((3000, 1000), (3000, 2000), (3000, 3000)):
    run(harness, f"[{x}, {y}] call brmh_fnc_fight; true")
run(harness, """
brmh_j = [];
private _group = createGroup [west, false];
for "_i" from 0 to 11 do {
    private _man = _group createUnit ["B_Soldier_F", [5000 + _i * 6, 5000, 0], [], 0, "CAN_COLLIDE"];
    _man setVariable ["ace_medical_ai_lastFired", CBA_missionTime + 86400];
    _man disableAI "PATH";
    brmh_j pushBack _man;
};
{
    [_x, 0.5 + (_forEachIndex mod 4) * 0.2, "body", "bullet"] call ace_medical_fnc_addDamageToUnit;
    [_x, true, 0, false] call ace_medical_fnc_setUnconscious;
} forEach brmh_j;
brmh_j_start = time;
brmh_j_died = [];
{
    _x addEventHandler ["Killed", {
        params ["_unit"];
        brmh_j_died pushBack [round (time - brmh_j_start), name _unit];
    }];
} forEach brmh_j;
true
""")

print("=== H: a rescue under fire", flush=True)
run(harness, """
brmh_h_shots = [];
private _group = createGroup [west, false];
private _boss = _group createUnit ["B_Soldier_F", [1500, 1000, 0], [], 0, "CAN_COLLIDE"];
_boss disableAI "ALL";
_boss setPosATL [1500, 800, 0];
brmh_h_medic = _group createUnit ["B_medic_F", [1500, 950, 0], [], 0, "CAN_COLLIDE"];
brmh_h_hurt = _group createUnit ["B_Soldier_F", [1500, 1000, 0], [], 0, "CAN_COLLIDE"];
{
    _x setVariable ["ace_medical_ai_lastFired", CBA_missionTime + 86400];
    _x addEventHandler ["Hit", {
        params ["_unit", "_source"];
        brmh_h_shots pushBack [round time, name _unit, name _source];
    }];
} forEach [brmh_h_medic, brmh_h_hurt];
brmh_h_medic disableAI "AUTOCOMBAT";
brmh_h_medic setBehaviour "CARELESS";
[brmh_h_hurt, true, 0, false] call ace_medical_fnc_setUnconscious;
private _east = createGroup [east, false];
for "_i" from 0 to 3 do {
    private _man = _east createUnit ["O_Soldier_F", [1490 + _i * 6, 1130, 0], [], 0, "CAN_COLLIDE"];
    _man disableAI "PATH";
};
brmh_h_east = units _east;
true
""")
H_READ = """
[round (brmh_h_hurt distance2D [1500, 1000]), alive brmh_h_medic, alive brmh_h_hurt, lifeState brmh_h_medic,
 brmh_h_hurt getVariable ["ACE_isUnconscious", false], count brmh_h_shots,
 {(_x targetKnowledge brmh_h_hurt) # 0} count brmh_h_east, {(_x targetKnowledge brmh_h_medic) # 0} count brmh_h_east,
 {_x targetKnowledge brmh_h_hurt isNotEqualTo [] and {currentCommand _x isEqualTo "FIRE"}} count brmh_h_east,
 {alive _x} count brmh_h_east, round (brmh_h_medic distance2D brmh_h_hurt)]
"""
print("  [body moved, medic alive, body alive, medic state, body uncon, hits, enemies knowing body, "
      "knowing medic, firing, enemies alive, medic to body]", flush=True)
print("  downed man alone, in sight of 4 enemies at 130 m", flush=True)
for _ in range(5):
    time.sleep(6)
    show("   alone", run(harness, H_READ))
print("  medic runs in, from 50 m", flush=True)
run(harness, "brmh_h_medic doMove (getPosATL brmh_h_hurt); true")
for _ in range(6):
    time.sleep(3)
    away = run(harness, "brmh_h_medic distance2D brmh_h_hurt")
    if away < 3:
        break
show("   arrived", run(harness, H_READ))
run(harness, """
[brmh_h_medic, brmh_h_hurt] spawn {
    params ["_medic", "_target"];
    _medic setUnitPos "MIDDLE";
    _medic playAction "grabDrag";
    sleep 3;
    _target switchMove "AinjPpneMrunSnonWnonDb";
    _medic disableAI "ANIM";
    private _group = createGroup [civilian, true];
    private _dummy = _group createUnit ["C_man_polo_1_F", [0, 0, 20], [], 0, "FORM"];
    _dummy setUnitPos "MIDDLE";
    _dummy forceWalk true;
    _dummy switchMove "AmovPknlMstpSlowWnonDnon";
    hideObjectGlobal _dummy;
    _dummy allowDamage false;
    _dummy setBehaviour "CARELESS";
    _dummy disableAI "FSM";
    _dummy disableAI "SUPPRESSION";
    _dummy setPosATL (getPosATL _medic);
    _medic attachTo [_dummy, [0, -0.2, 0]];
    _medic setDir 180;
    _target attachTo [_dummy, [0, -1.1, 0.092]];
    _target setDir 0;
    _dummy doMove [1500, 930, 0];
    brmh_h_dummy = _dummy;
    sleep 1;
    _medic playMove "AcinPknlMwlkSrasWrflDb";
};
true
""")
for _ in range(10):
    time.sleep(6)
    show("   drag", run(harness, H_READ))
show("  shots", run(harness, "brmh_h_shots"))

print("=== I: a forward carry on a dummy", flush=True)
run(harness, """
private _group = createGroup [west, false];
brmh_i_medic = _group createUnit ["B_medic_F", [1500, 4000, 0], [], 0, "CAN_COLLIDE"];
brmh_i_hurt = _group createUnit ["B_Soldier_F", [1502, 4000, 0], [], 0, "CAN_COLLIDE"];
{_x setVariable ["ace_medical_ai_lastFired", CBA_missionTime + 86400]} forEach [brmh_i_medic, brmh_i_hurt];
[brmh_i_hurt, true, 0, false] call ace_medical_fnc_setUnconscious;
true
""")
time.sleep(4)
run(harness, """
[brmh_i_medic, brmh_i_hurt] spawn {
    params ["_medic", "_target"];
    _medic playMoveNow "AcinPknlMstpSnonWnonDnon_AcinPercMrunSnonWnonDnon";
    _target switchMove "AinjPfalMstpSnonWrflDnon_carried_Up";
    sleep 9;
    _medic disableAI "ANIM";
    private _group = createGroup [civilian, true];
    private _dummy = _group createUnit ["C_man_polo_1_F", [0, 0, 20], [], 0, "FORM"];
    _dummy forceWalk true;
    hideObjectGlobal _dummy;
    _dummy allowDamage false;
    _dummy setBehaviour "CARELESS";
    _dummy disableAI "FSM";
    _dummy setPosATL (getPosATL _medic);
    _medic attachTo [_dummy, [0, 0, 0]];
    _medic setDir 0;
    _target attachTo [_medic, [0.4, -0.1, -1.25], "LeftShoulder"];
    _target setDir 195;
    _target switchMove "AinjPfalMstpSnonWnonDf_carried_dead";
    _dummy doMove [1500, 4100, 0];
    brmh_i_dummy = _dummy;
    sleep 0.5;
    _medic playMove "AcinPercMrunSnonWnonDf";
};
true
""")
time.sleep(10)
for _ in range(6):
    time.sleep(5)
    show("  carry [moved, attached, medic anim, body anim, dummy speed]", run(harness, """
    [round (brmh_i_medic distance2D [1500, 4000]), str attachedTo brmh_i_hurt, animationState brmh_i_medic,
     animationState brmh_i_hurt, round speed brmh_i_dummy]
    """))

print("=== L: load into a vehicle the squad's own man drives", flush=True)
run(harness, """
private _group = createGroup [west, false];
brmh_l_boss = _group createUnit ["B_Soldier_F", [1500, 4500, 0], [], 0, "CAN_COLLIDE"];
brmh_l_medic = _group createUnit ["B_medic_F", [1503, 4500, 0], [], 0, "CAN_COLLIDE"];
brmh_l_hurt = _group createUnit ["B_Soldier_F", [1506, 4500, 0], [], 0, "CAN_COLLIDE"];
{_x setVariable ["ace_medical_ai_lastFired", CBA_missionTime + 86400]} forEach units _group;
brmh_l_hunter = createVehicle ["B_MRAP_01_F", [1500, 4510, 0], [], 0, "CAN_COLLIDE"];
brmh_l_boss moveInDriver brmh_l_hunter;
[brmh_l_hurt, true, 0, false] call ace_medical_fnc_setUnconscious;
true
""")
time.sleep(4)
show("  load", run(harness, """
private _back = [brmh_l_medic, brmh_l_hurt, brmh_l_hunter] call ace_common_fnc_loadPerson;
[str _back, typeOf vehicle brmh_l_hurt]
"""))
time.sleep(4)
show("  [in the hunter, same group, seat]", run(harness, """
[vehicle brmh_l_hurt isEqualTo brmh_l_hunter, group brmh_l_hurt isEqualTo group brmh_l_medic,
 assignedVehicleRole brmh_l_hurt, group brmh_l_boss isEqualTo group brmh_l_hurt]
"""))

while time.time() - started < 210:
    time.sleep(5)
print("=== F, after a few minutes", flush=True)
print("  [men, alive, unconscious, arrest, injured, dead who'd been down, ever down]", flush=True)
for index in range(3):
    show(f"  fight {index}", run(harness, f"[brmh_fights # {index}] call brmh_fnc_tally"))
show("  all", run(harness, "[brmh_fights # 0 + (brmh_fights # 1) + (brmh_fights # 2)] call brmh_fnc_tally"))

print("=== J, until 5 minutes", flush=True)
while time.time() - started < 330:
    time.sleep(10)
show("  died untreated [s, name]", run(harness, "brmh_j_died"))
show("  [alive, unconscious, arrest]", run(harness, """
private _alive = brmh_j select {alive _x};
[count _alive, {_x getVariable ["ACE_isUnconscious", false]} count _alive,
 {_x getVariable ["ace_medical_inCardiacArrest", false]} count _alive,
 _alive apply {round (_x getVariable ["ace_medical_bloodVolume", 6] * 10) / 10}]
"""))

print("=== K: a share of the downed die at once, by a handler", flush=True)
run(harness, """
brmh_k_killed = 0;
["ace_unconscious", {
    params ["_unit", "_state"];
    if (_state and {local _unit} and {not isPlayer _unit} and {random 1 < 0.5}) then {
        brmh_k_killed = brmh_k_killed + 1;
        _unit setDamage 1;
    };
}] call CBA_fnc_addEventHandler;
brmh_k = [];
private _group = createGroup [west, false];
for "_i" from 0 to 11 do {
    private _man = _group createUnit ["B_Soldier_F", [6000 + _i * 6, 1000, 0], [], 0, "CAN_COLLIDE"];
    _man setVariable ["ace_medical_ai_lastFired", CBA_missionTime + 86400];
    brmh_k pushBack _man;
    [_man, true, 0, false] call ace_medical_fnc_setUnconscious;
};
true
""")
time.sleep(6)
show("  [killed by the handler, dead, still down]", run(harness, """
[brmh_k_killed, {not alive _x} count brmh_k, {alive _x and {_x getVariable ["ACE_isUnconscious", false]}} count brmh_k]
"""))
errors = harness.events(since=0, kinds=["err"]).get("events", [])
print("script errors", len(errors), [str(e)[:220] for e in errors[:6]], flush=True)
harness.stop()
print("done", flush=True)
assert math.pi
