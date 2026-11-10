"""Spike 3: crewing. Slots, mounting by order, timing, what reports could see, how men leave, and what breaks a crew."""
from __future__ import annotations

import time

from spike_arty_lib import TRACK, game, run, show

h = game()
run(h, TRACK)

# --- the slots each kind of vehicle really has
show("slots", run(h, """
private _out = [];
{
	private _class = _x;
	private _v = createVehicle [_class, [7000, 7000, 0], [], 0, "NONE"];
	_out pushBack [_class, getText (configOf _v >> "displayName"), fullCrew [_v, "", true] apply {[_x # 1, _x # 2, _x # 3, _x # 4]},
		["driver", "gunner", "commander", "cargo"] apply {[_x, _v emptyPositions _x]}, isKindOf_static = _v isKindOf "StaticWeapon"];
	deleteVehicle _v;
} forEach ["B_Mortar_01_F", "B_HMG_01_high_F", "B_MRAP_01_hmg_F", "B_MBT_01_arty_F", "C_Offroad_01_F"];
_out
""".replace("isKindOf_static = ", "")))

SQUAD = """
brmh_spike_fnc_squad = {
	params ["_at", ["_side", west], ["_size", 4]];
	private _group = createGroup [_side, false];
	for "_i" from 1 to _size do {
		_group createUnit [["B_Soldier_F", "O_Soldier_F"] select (_side isEqualTo east), _at, [], 4, "NONE"];
	};
	_group
};
brmh_spike_fnc_seen = {
	params ["_man"];
	[alive _man, typeOf vehicle _man, assignedVehicleRole _man, (vehicle _man) isEqualTo _man, currentCommand _man, unitReady _man, _man == leader group _man]
};
true
"""
run(h, SQUAD)

# --- mounting: how to order it, how long it takes, leader against subordinate, and from how far
MOUNT = """
params ["_name", "_at", "_distance", "_who", "_how"];
private _group = [_at] call brmh_spike_fnc_squad;
private _gun = createVehicle ["B_Mortar_01_F", _at vectorAdd [_distance, 0, 0], [], 0, "NONE"];
[_gun] call brmh_spike_fnc_track;
sleep 2;
private _man = if (_who isEqualTo "leader") then {leader _group} else {(units _group) # 2};
private _start = time;
switch (_how) do {
	case "order": { _man assignAsGunner _gun; [_man] orderGetIn true; };
	case "allowed": { _group addVehicle _gun; _man assignAsGunner _gun; [_man] orderGetIn true; };
	case "moveto": { _man assignAsGunner _gun; _man doMove (getPos _gun); [_man] orderGetIn true; };
};
private _deadline = _start + 120;
waitUntil {sleep 0.5; (vehicle _man isEqualTo _gun) or time > _deadline};
private _took = time - _start;
private _mounted = vehicle _man isEqualTo _gun;
sleep 3;
private _settled = [_man] call brmh_spike_fnc_seen;
private _result = [_who, _how, _distance, _mounted, _took, _settled, gunner _gun isEqualTo _man, (units _group) apply {_x distance2D _gun}];
_gun doArtilleryFire [_gun getPos [800, 90], "8Rnd_82mm_Mo_shells", 2];
sleep 12;
_result pushBack count (_gun getVariable "brmh_shells");
missionNamespace setVariable ["brmh_spike_" + _name, _result];
missionNamespace setVariable ["brmh_mount_" + _name, [_group, _gun, _man]];
"""
# --- what happens when the squad gets a new order while a man is on the gun
LEAVE = """
params ["_name", "_case"];
(missionNamespace getVariable ("brmh_mount_" + _case)) params ["_group", "_gun", "_man"];
private _start = time;
private _before = [_man] call brmh_spike_fnc_seen;
private _wp = _group addWaypoint [(getPos _gun) vectorAdd [0, 150, 0], 0];
_wp setWaypointType "MOVE";
_group setCurrentWaypoint _wp;
sleep 35;
private _moved = [[_man] call brmh_spike_fnc_seen, _man distance2D _gun, (leader _group) distance2D _gun];
_man action ["GetOut", _gun];
unassignVehicle _man;
[_man] orderGetIn false;
sleep 8;
private _ordered = [[_man] call brmh_spike_fnc_seen, assignedVehicle _man isEqualTo objNull, currentCommand _man];
[_man] joinSilent _group;
_man doFollow leader _group;
sleep 15;
missionNamespace setVariable ["brmh_spike_" + _name, [_before, _moved, _ordered, [_man] call brmh_spike_fnc_seen, _man distance2D _gun]];
"""
# --- what breaks a crew: ammunition, a dead gunner, a destroyed gun, enemies, a full seat, a doStop
BREAK = """
params ["_name", "_at", "_how"];
private _group = [_at] call brmh_spike_fnc_squad;
private _gun = createVehicle ["B_Mortar_01_F", _at vectorAdd [8, 0, 0], [], 0, "NONE"];
[_gun] call brmh_spike_fnc_track;
private _man = (units _group) # 2;
private _other = (units _group) # 3;
_man assignAsGunner _gun;
_man moveInGunner _gun;
_group addVehicle _gun;
sleep 3;
private _out = [_how, [_man] call brmh_spike_fnc_seen];
private _start = time;
switch (_how) do {
	case "noammo": {
		_gun setVehicleAmmo 0;
		sleep 30;
		_out pushBack [[_man] call brmh_spike_fnc_seen, someAmmo _gun, canFire _gun, getArtilleryAmmo [_gun]];
	};
	case "killed": {
		_man setDamage 1;
		sleep 20;
		_out pushBack [alive gunner _gun, isNull gunner _gun, _gun emptyPositions "gunner", fullCrew [_gun, "", true] apply {[alive (_x # 0), _x # 1]}, canFire _gun, (units _group) apply {[_x distance2D _gun, typeOf vehicle _x]}];
		_other assignAsGunner _gun;
		[_other] orderGetIn true;
		sleep 25;
		_out pushBack [[_other] call brmh_spike_fnc_seen, gunner _gun isEqualTo _other, count (_gun getVariable "brmh_shells")];
		_gun doArtilleryFire [_gun getPos [800, 90], "8Rnd_82mm_Mo_shells", 2];
		sleep 10;
		_out pushBack count (_gun getVariable "brmh_shells");
	};
	case "destroyed": {
		_gun setDamage 1;
		sleep 15;
		_out pushBack [alive _gun, canFire _gun, someAmmo _gun, alive _man, typeOf vehicle _man];
	};
	case "damaged": {
		_gun setDamage 0.8;
		sleep 3;
		_out pushBack [damage _gun, canFire _gun, canMove _gun, someAmmo _gun, typeOf vehicle _man];
		_gun doArtilleryFire [_gun getPos [800, 90], "8Rnd_82mm_Mo_shells", 2];
		sleep 10;
		_out pushBack count (_gun getVariable "brmh_shells");
	};
	case "enemy": {
		private _bad = [_at vectorAdd [8, 25, 0], east, 2] call brmh_spike_fnc_squad;
		_bad setCombatMode "BLUE";
		{ _x setCaptive false; _x disableAI "ALL"; } forEach units _bad;
		sleep 30;
		_out pushBack [[_man] call brmh_spike_fnc_seen, behaviour _man, (units _group) apply {typeOf vehicle _x}, {alive _x} count units _bad, count (_gun getVariable "brmh_shells")];
	};
	case "taken": {
		_other assignAsGunner _gun;
		[_other] orderGetIn true;
		sleep 20;
		_out pushBack [[_other] call brmh_spike_fnc_seen, gunner _gun isEqualTo _other, gunner _gun isEqualTo _man, _other distance2D _gun];
	};
	case "stop_then_fire": {
		_gun doArtilleryFire [_gun getPos [800, 90], "8Rnd_82mm_Mo_shells", 8];
		sleep 5;
		doStop _gun;
		private _stopped = count (_gun getVariable "brmh_shells");
		sleep 6;
		_out pushBack [_stopped, count (_gun getVariable "brmh_shells"), unitReady _gun, currentCommand _man];
		_gun doArtilleryFire [_gun getPos [800, 90], "8Rnd_82mm_Mo_shells", 2];
		sleep 8;
		_out pushBack [count (_gun getVariable "brmh_shells"), unitReady _gun, currentCommand _man];
		_man doFollow leader _group;
		sleep 3;
		_out pushBack [unitReady _gun, currentCommand _man];
		_gun doArtilleryFire [_gun getPos [800, 90], "8Rnd_82mm_Mo_shells", 2];
		sleep 8;
		_out pushBack [count (_gun getVariable "brmh_shells"), unitReady _gun, currentCommand _man];
	};
	case "weapons_tight": {
		_group setCombatMode "GREEN";
		sleep 1;
		_gun doArtilleryFire [_gun getPos [800, 90], "8Rnd_82mm_Mo_shells", 3];
		sleep 12;
		_out pushBack [count (_gun getVariable "brmh_shells"), unitReady _gun, currentCommand _man];
		_group setCombatMode "YELLOW";
		sleep 12;
		_out pushBack [count (_gun getVariable "brmh_shells"), unitReady _gun, currentCommand _man];
	};
};
missionNamespace setVariable ["brmh_spike_" + _name, _out];
"""


def launch(name: str, code: str, *args) -> None:
    run(h, f"brmh_spike_{name} = nil; _this spawn {{{code}}}; true", [name, *args])


def wait(names, seconds):
    deadline = time.time() + seconds
    out = {}
    while time.time() < deadline:
        for name in names:
            if name not in out:
                value = run(h, f'if (isNil "brmh_spike_{name}") then {{""}} else {{brmh_spike_{name}}}')
                if value:
                    out[name] = value
        if len(out) == len(names):
            break
        time.sleep(4)
    return out


mounts = [("m_sub50", 6500, 50, "sub", "order"), ("m_lead50", 6500, 50, "leader", "order"), ("m_sub200", 6500, 200, "sub", "order"),
          ("m_lead200", 6500, 200, "leader", "order"), ("m_add50", 6500, 50, "sub", "allowed")]
for index, (name, x, distance, who, how) in enumerate(mounts):
    launch(name, MOUNT, [x, 500 + 600 * index], distance, who, how)
mounted = wait([m[0] for m in mounts], 170)
for m in mounts:
    show(m[0], mounted.get(m[0], "NOT FINISHED"))

leaves = [("l_sub", "m_sub50"), ("l_lead", "m_lead50"), ("l_add", "m_add50")]
for name, case in leaves:
    if case in mounted:
        launch(name, LEAVE, case)
left = wait([n for n, c in leaves if c in mounted], 90)
for name, _ in leaves:
    show(name, left.get(name, "NOT FINISHED"))

breaks = ["noammo", "killed", "destroyed", "damaged", "enemy", "taken", "stop_then_fire", "weapons_tight"]
for index, how in enumerate(breaks):
    launch(f"b_{how}", BREAK, [7000, 500 + 500 * index], how)
broken = wait([f"b_{how}" for how in breaks], 110)
for how in breaks:
    show(how, broken.get(f"b_{how}", "NOT FINISHED"))
