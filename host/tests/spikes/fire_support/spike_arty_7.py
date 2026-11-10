"""Spike 7: the design's unverified list, by day. Crews under assault, long fights, smoke, dust, lethality, vehicle guns, check
fire and costs. Leaves the game running, so spike_arty_8.py can use it and script errors can be read."""
from __future__ import annotations

import math
import time

from spike_arty_lib import TRACK, game, run, show

h = game()
run(h, TRACK)
run(h, """
brmh_x_men = {
	params ["_at", "_side", "_count", ["_spread", 4]];
	private _group = createGroup [_side, false];
	for "_i" from 1 to _count do {
		_group createUnit [["B_Soldier_F", "O_Soldier_F"] select (_side isEqualTo east), _at, [], _spread, "NONE"];
	};
	_group
};
true
""")

ASSAULT = """
params ["_name", "_at", "_how"];
private _gun = createVehicle ["B_Mortar_01_F", _at, [], 0, "NONE"];
[_gun] call brmh_spike_fnc_track;
private _count = [4, 1] select (_how in ["alone_off", "alone_on"]);
private _group = [_at vectorAdd [8, 0, 0], west, _count] call brmh_x_men;
private _man = (units _group) select (_count - 1);
_man moveInGunner _gun;
_man assignAsGunner _gun;
if (_how in ["alone_off", "squad_off"]) then { _man disableAI "TARGET"; };
private _bad = [_at vectorAdd [0, 300, 0], east, 6, 8] call brmh_x_men;
private _wp = _bad addWaypoint [_at, 0];
_wp setWaypointType "SAD";
_bad setCombatMode "RED";
private _rows = [];
private _start = time;
private _last = [];
for "_i" from 1 to 28 do {
	sleep 5;
	private _left = units _bad select {alive _x};
	private _row = [alive _man, vehicle _man isEqualTo _gun, behaviour _man, {alive _x} count units _group, count _left, count (_gun getVariable "brmh_shells"), alive _gun];
	if (_row isNotEqualTo _last) then {
		_rows pushBack ([round (time - _start), if (_left isEqualTo []) then {-1} else {round selectMin (_left apply {_x distance2D _gun})}] + _row);
		_last = _row;
	};
};
missionNamespace setVariable ["brmh_spike_" + _name, [_how, _rows]];
"""
LONG = """
params ["_name", "_at", "_how"];
private _gun = createVehicle ["B_Mortar_01_F", _at, [], 0, "NONE"];
[_gun] call brmh_spike_fnc_track;
private _group = [_at vectorAdd [6, 0, 0], west, 2] call brmh_x_men;
private _lead = leader _group;
private _man = if (_how isEqualTo "leader_on_gun") then {_lead} else {(units _group - [_lead]) # 0};
private _other = (units _group - [_man]) # 0;
_man moveInGunner _gun;
_man assignAsGunner _gun;
_man disableAI "TARGET";
private _bad = [_at vectorAdd [0, 200, 0], east, 4] call brmh_x_men;
{ _x allowDamage false; _x disableAI "PATH"; } forEach (units _bad + units _group);
_gun allowDamage false;
private _rows = [];
for "_i" from 1 to 18 do {
	{ _other reveal [_x, 4]; _man reveal [_x, 4]; } forEach units _bad;
	sleep 10;
	if (_i % 3 isEqualTo 0) then {
		_rows pushBack [count (_lead targets [true, 1000]), count (_man targets [true, 1000]), _man knowsAbout (units _bad # 0), _other knowsAbout (units _bad # 0), behaviour _lead, count (_gun getVariable "brmh_shells"), vehicle _man isEqualTo _gun];
	};
};
missionNamespace setVariable ["brmh_spike_" + _name, [_how, leader _group isEqualTo _man, _rows]];
"""
SMOKE = """
params ["_name", "_at", "_how"];
private _gun = ["B_Mortar_01_F", _at vectorAdd [0, -800, 0]] call brmh_spike_fnc_gun;
(gunner _gun) disableAI "TARGET";
private _a = [_at vectorAdd [0, -90, 0], west, 4] call brmh_x_men;
private _b = [_at vectorAdd [0, 90, 0], east, 4] call brmh_x_men;
brmh_s_counts = missionNamespace getVariable ["brmh_s_counts", createHashMap];
private _counts = [0, 0];
private _key = _name;
brmh_s_counts set [_key, [0, 0]];
{
	_x setVariable ["brmh_key", _key];
	_x allowDamage false;
	_x disableAI "PATH";
	_x addEventHandler ["Fired", { params ["_u"]; (brmh_s_counts get (_u getVariable "brmh_key")) set [0, ((brmh_s_counts get (_u getVariable "brmh_key")) # 0) + 1]; }];
	_x addEventHandler ["HitPart", { private _u = (_this # 0) # 0; (brmh_s_counts get (_u getVariable "brmh_key")) set [1, ((brmh_s_counts get (_u getVariable "brmh_key")) # 1) + 1]; }];
} forEach (units _a + units _b);
{ { _x reveal [leader _b, 4]; } forEach units _a; { _x reveal [leader _a, 4]; } forEach units _b; } forEach [0];
private _start = time;
private _rows = [];
private _fired = false;
for "_i" from 1 to 24 do {
	sleep 5;
	if (not _fired and {time - _start > 25}) then {
		_fired = true;
		if (_how isEqualTo "smoke") then { _gun doArtilleryFire [_at, "8Rnd_82mm_Mo_Smoke_white", 6]; };
	};
	private _one = leader _a; private _two = leader _b;
	_rows pushBack [round (time - _start), (brmh_s_counts get _key) # 0, (brmh_s_counts get _key) # 1, [_one, "VIEW", _two] checkVisibility [eyePos _one, eyePos _two], [_one, "FIRE", _two] checkVisibility [eyePos _one, eyePos _two], _one knowsAbout _two];
};
missionNamespace setVariable ["brmh_spike_" + _name, [_how, _rows]];
"""
DUST = """
params ["_name", "_at"];
private _gun = ["B_Mortar_01_F", _at vectorAdd [0, -800, 0]] call brmh_spike_fnc_gun;
(gunner _gun) disableAI "TARGET";
private _lookers = [100, 330, 800] apply {
	private _m = createGroup [west, false] createUnit ["B_recon_F", _at vectorAdd [_x, 0, 0], [], 0, "CAN_COLLIDE"];
	_m disableAI "PATH"; _m
};
sleep 2;
private _series = [];
{
	_x params ["_count", "_label"];
	private _before = count (_gun getVariable "brmh_shells");
	_gun doArtilleryFire [_at, "8Rnd_82mm_Mo_shells", _count];
	waitUntil { sleep 0.2; (count (_gun getVariable "brmh_shells") >= _before + _count) and {((_gun getVariable "brmh_shells") select [_before]) findIf {not ("pos" in _x)} < 0} };
	private _list = (_gun getVariable "brmh_shells") select [_before];
	private _pos = (_list # (_count - 1)) get "pos";
	private _from = (_list # (_count - 1)) get "landed";
	private _rows = [];
	for "_s" from 1 to 16 do {
		_rows pushBack [(round ((time - _from) * 10)) / 10, _lookers apply { round (100 * ([_x, "VIEW"] checkVisibility [eyePos _x, _pos vectorAdd [0, 0, 1]])) }, _lookers apply { round (100 * ([_x, "VIEW"] checkVisibility [eyePos _x, _pos vectorAdd [0, 0, 8]])) }];
		sleep ([0.3, 0.3, 0.5, 0.5, 1, 1, 1, 2, 2, 2, 3, 3, 3, 3, 3, 3] # (_s - 1));
	};
	_series pushBack [_label, _rows];
	sleep 5;
} forEach [[1, "single"], [1, "single again"], [3, "three"]];
missionNamespace setVariable ["brmh_spike_" + _name, _series];
"""
LETHAL = """
params ["_name", "_at", "_how"];
private _gun = ["B_Mortar_01_F", _at vectorAdd [0, -800, 0]] call brmh_spike_fnc_gun;
(gunner _gun) disableAI "TARGET";
private _rings = [15, 40, 75];
private _groups = _rings apply {
	private _r = _x;
	private _g = createGroup [west, false];
	for "_i" from 0 to 3 do {
		private _spot = _at getPos [_r, 45 + 90 * _i];
		private _m = _g createUnit ["B_Soldier_F", _spot, [], 0, "CAN_COLLIDE"];
		_m setPosATL _spot;
		_m setDir (90 * _i);
		switch (_how) do {
			case "stand": { _m disableAI "PATH"; _m setUnitPos "UP"; };
			case "prone": { _m disableAI "PATH"; _m setUnitPos "DOWN"; };
			case "fence": {
				_m disableAI "PATH"; _m setUnitPos "MIDDLE";
				private _fence = createVehicle ["Land_BagFence_Round_F", _spot, [], 0, "CAN_COLLIDE"];
				_fence setPosATL _spot;
				_fence setDir (getDir _m + 180);
			};
			case "moving": { _m doMove (_at getPos [_r, 225 + 90 * _i]); _m setUnitPos "UP"; };
		};
	};
	_g setCombatMode "BLUE";
	_g
};
sleep 3;
_gun doArtilleryFire [_at, "8Rnd_82mm_Mo_shells", 8];
sleep 50;
missionNamespace setVariable ["brmh_spike_" + _name, [_how, _groups apply {{alive _x} count units _x}, (_groups apply {{damage _x > 0.05 and alive _x} count units _x})]];
"""
VEHICLE = """
params ["_name", "_at", "_class", "_rounds"];
private _east = (_class select [0, 2]) isEqualTo "O_";
private _gun = [_class, _at, [west, east] select _east] call brmh_spike_fnc_gun;
private _ammo = getArtilleryAmmo [_gun];
private _mag = _ammo # 0;
sleep 3;
private _target = _gun getPos [2500, 90];
private _start = time;
private _ready = [];
_gun doArtilleryFire [_target, _mag, _rounds];
private _was = unitReady _gun;
for "_i" from 1 to 140 do {
	sleep 0.5;
	if (unitReady _gun isNotEqualTo _was) then { _was = unitReady _gun; _ready pushBack [round (time - _start), _was]; };
};
private _shells = (_gun getVariable "brmh_shells") apply {[(_x get "fired") - _start, (_x getOrDefault ["landed", -1]) - _start, _x getOrDefault ["pos", []]]};
missionNamespace setVariable ["brmh_spike_" + _name, [_class, _mag, _ammo, _target, _ready, _shells, magazinesAllTurrets _gun select {_x # 1 isEqualTo [0]} apply {[_x # 0, _x # 2]}, currentCommand gunner _gun]];
"""
MOVING = """
params ["_name", "_at"];
private _gun = createVehicle ["B_MBT_01_arty_F", _at, [], 0, "NONE"];
[_gun] call brmh_spike_fnc_track;
private _group = [_at vectorAdd [10, 0, 0], west, 2] call brmh_x_men;
private _lead = leader _group;
private _other = (units _group - [_lead]) # 0;
_lead moveInGunner _gun;
_other moveInDriver _gun;
sleep 3;
private _mag = (getArtilleryAmmo [_gun]) # 0;
private _start = time;
_gun doMove (_at vectorAdd [0, 600, 0]);
sleep 12;
private _speed = speed _gun;
private _before = count (_gun getVariable "brmh_shells");
_gun doArtilleryFire [_gun getPos [2500, 90], _mag, 3];
sleep 25;
private _pos = getPos _gun;
sleep 25;
missionNamespace setVariable ["brmh_spike_" + _name, [_speed, count (_gun getVariable "brmh_shells"), round (_pos distance2D _at), round (_gun distance2D _at), speed _gun, currentCommand _lead, currentCommand _other, unitReady _gun]];
"""
CHECK = """
params ["_name", "_at", "_class", "_afterRounds"];
private _gun = [_class, _at] call brmh_spike_fnc_gun;
sleep 3;
private _mag = (getArtilleryAmmo [_gun]) # 0;
private _start = time;
_gun doArtilleryFire [_gun getPos [2000, 90], _mag, 8];
if (_afterRounds isEqualTo 0) then { sleep 0.3; } else {
	waitUntil { sleep 0.05; count (_gun getVariable "brmh_shells") >= _afterRounds or time > _start + 60 };
};
private _when = count (_gun getVariable "brmh_shells");
doStop _gun;
sleep 25;
private _end = count (_gun getVariable "brmh_shells");
_gun doArtilleryFire [_gun getPos [2000, 90], _mag, 1];
sleep 15;
missionNamespace setVariable ["brmh_spike_" + _name, [_class, _afterRounds, _when, _end, count (_gun getVariable "brmh_shells")]];
"""
RIDE = """
params ["_name", "_at", "_class", "_count"];
private _group = [_at, west, _count, 6] call brmh_x_men;
private _car = createVehicle [_class, _at vectorAdd [25, 0, 0], [], 0, "NONE"];
private _men = units _group;
private _lead = leader _group;
private _rest = _men - [_lead];
sleep 1;
private _seats = fullCrew [_car, "", true] apply {[_x # 1, _x # 2]};
(_rest # 0) assignAsDriver _car;
private _cargo = count (fullCrew [_car, "cargo", true]);
private _riders = [_lead] + (_rest select [1]);
private _hasGun = (fullCrew [_car, "gunner", true]) isNotEqualTo [];
if (_hasGun) then { (_rest # 1) assignAsGunner _car; _riders = _riders - [_rest # 1]; };
{ if (_forEachIndex < _cargo) then { _x assignAsCargoIndex [_car, _forEachIndex]; }; } forEach _riders;
_group addVehicle _car;
_men orderGetIn true;
private _start = time;
sleep 40;
private _in = _men select {vehicle _x isEqualTo _car};
private _out = _men - _in;
private _state = [count _in, count _out, time - _start, _out apply {[currentCommand _x, round (_x distance2D _car), assignedVehicle _x isEqualTo _car]}];
private _wp = _group addWaypoint [_at vectorAdd [25, 500, 0], 0];
_wp setWaypointType "MOVE";
_group setCurrentWaypoint _wp;
private _from = getPos _car;
sleep 40;
missionNamespace setVariable ["brmh_spike_" + _name, [_class, _seats, _state, round (_car distance2D _from), {vehicle _x isEqualTo _car} count _men, round selectMax (_men apply {_x distance2D _car})]];
"""
COST = """
params ["_name"];
private _men = (allUnits select {side group _x isEqualTo west}) select [0, 30];
private _pos = (getPosASL (_men # 0)) vectorAdd [40, 40, 1];
private _see = diag_codePerformance [{ params ["_men", "_pos"]; { [_x, "VIEW"] checkVisibility [eyePos _x, _pos] } forEach _men; }, [_men, _pos], 200];
private _near = diag_codePerformance [{ params ["_men", "_pos"]; { _x nearEntities [["StaticWeapon", "LandVehicle"], 800] } forEach _men; }, [_men, _pos], 200];
private _crew = diag_codePerformance [{ params ["_men"]; { fullCrew [vehicle _x, "", true] } forEach _men; }, [_men, _pos], 200];
missionNamespace setVariable ["brmh_spike_" + _name, [count _men, _see, _near, _crew]];
"""
names: list[str] = []


def launch(name: str, code: str, *args) -> None:
    names.append(name)
    run(h, f"brmh_spike_{name} = nil; _this spawn {{{code}}}; true", [name, *args])


for index, how in enumerate(("alone_off", "alone_on", "squad_off")):
    launch(f"assault_{how}", ASSAULT, [400 + 900 * index, 7600, 0], how)
for index, how in enumerate(("subordinate", "leader_on_gun")):
    launch(f"long_{how}", LONG, [400 + 900 * index, 6800, 0], how)
for index, how in enumerate(("control", "smoke")):
    launch(f"smoke_{how}", SMOKE, [400 + 900 * index, 6100, 0], how)
launch("dust", DUST, [2700, 6100, 0])
for index, how in enumerate(("stand", "stand", "prone", "prone", "moving", "moving", "fence", "fence")):
    launch(f"lethal_{how}_{index % 2}", LETHAL, [400 + 800 * index, 4300, 0], how)
for index, (klass, rounds) in enumerate((("B_MBT_01_arty_F", 6), ("B_MBT_01_mlrs_F", 4), ("O_MBT_02_arty_F", 6), ("I_Truck_02_MRL_F", 4))):
    launch(f"veh_{index}", VEHICLE, [7700, 500 + 900 * index, 0], klass, rounds)
launch("moving_gun", MOVING, [6500, 500, 0])
for index, (klass, after) in enumerate((("B_Mortar_01_F", 0), ("B_Mortar_01_F", 4), ("B_Mortar_01_F", 8), ("B_MBT_01_arty_F", 0), ("B_MBT_01_arty_F", 3), ("B_MBT_01_mlrs_F", 2))):
    launch(f"check_{index}", CHECK, [300 + 700 * index, 600, 0], klass, after)
for index, (klass, count) in enumerate((("B_MRAP_01_hmg_F", 8), ("B_Truck_01_transport_F", 8))):
    launch(f"ride_{index}", RIDE, [300 + 900 * index, 2300, 0], klass, count)

deadline = time.time() + 280
out: dict = {}
while time.time() < deadline and len(out) < len(names):
    for name in names:
        if name not in out:
            value = run(h, f'if (isNil "brmh_spike_{name}") then {{""}} else {{brmh_spike_{name}}}')
            if value:
                out[name] = value
    time.sleep(5)
for name in names:
    value = out.get(name, "NOT FINISHED")
    if name.startswith("veh_") and value != "NOT FINISHED":
        klass, mag, ammo, target, ready, shells, mags, command = value
        shells = shells or []
        points = [s[2] for s in shells if s[2]]
        misses = [round(math.dist(p[:2], target[:2])) for p in points]
        show(name, {"class": klass, "mag": mag, "ammo": ammo, "fired": len(shells), "ready": ready, "first": round(shells[0][0], 1) if shells else None,
                    "span": round(shells[-1][0] - shells[0][0], 1) if shells else None, "flight": round(shells[0][1] - shells[0][0], 1) if shells else None,
                    "miss": misses, "mags": mags, "command": command})
    else:
        show(name, value)
run(h, f"brmh_spike_cost = nil; _this spawn {{{COST}}}; true", ["cost"])
time.sleep(6)
show("cost", run(h, 'if (isNil "brmh_spike_cost") then {""} else {brmh_spike_cost}'))
