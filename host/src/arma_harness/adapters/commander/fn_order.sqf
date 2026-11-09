/*
	NAME: brmh_cmd_fnc_order
	DESCRIPTION: Applies a validated order. The result never says whether the group exists, so the commander can't learn it from here.
	PARAMETERS:
		0 - Callsign (STRING)
		1 - Order id (STRING)
		2 - Mode: "replace", "append", "halt" or "posture" (STRING)
		3 - Legs: [[waypoint type, [x, y], radius, completion, hold for], ...] (ARRAY)
		4 - Posture: [speed, formation, behaviour, combat mode], "" leaves a setting alone (ARRAY)
	USAGE:
		["Alpha", "O-0001", "replace", [["MOVE", [3450, 3050], 0, 0, 0]], ["", "", "", ""]] call brmh_cmd_fnc_order;
	RETURNS: true
	ENVIRONMENT: Server
*/
params [["_callsign", "", [""]], ["_order", "", [""]], ["_mode", "replace", [""]], ["_legs", [], [[]]], ["_posture", [], [[]], 4]];
private _group = brmh_cmd_stations getOrDefault [_callsign, grpNull];
if (isNull _group) exitWith {
	true
};
_group setVariable ["brmh_cmd_order", _order];
_group setVariable ["brmh_cmd_unable", ""];
// These only concern the gun, and leave the squad's own orders as they were.
if (_mode isEqualTo "fire") exitWith {
	[_group, _order, _legs # 0] call brmh_cmd_fnc_startFire;
	true
};
if (_mode isEqualTo "checkfire") exitWith {
	[_group, _order, _legs # 0 # 0] call brmh_cmd_fnc_checkFire;
	true
};
if (_mode isEqualTo "cas") exitWith {
	([_group, _order] + (_legs # 0)) call brmh_cmd_fnc_casOrder;
	true
};
if (_mode isEqualTo "strike") exitWith {
	([_group, _order] + (_legs # 0)) call brmh_cmd_fnc_strikeOrder;
	true
};
if (_mode in ["carry", "unload", "treat", "post"]) exitWith {
	([_group, _order] + (_legs # 0)) call (missionNamespace getVariable format ["brmh_cmd_fnc_%1Order", _mode]);
	true
};
private _oneSeat = _mode isEqualTo "mount" and {
	(_legs # 0 # 1) isNotEqualTo ""
};
if (_mode isNotEqualTo "posture" and {
	not _oneSeat
}) then {
	[_group, ["placing", "clearing"]] call brmh_cmd_fnc_endMachines;
	{
		_x enableAI "PATH";
		// A cordon turns each man to watch its centre, and nothing else turns him back.
		_x doWatch objNull;
	} forEach units _group;
	{
		if ((_x get "GROUP") isEqualTo _group and {
			((_x get "SPEC") get "KIND") isEqualTo "task"
		}) then {
			_x set ["REPLACED", true];
		};
	} forEach brmh_cmd_builds;
};
// One man sent to a named seat leaves the squad's orders alone. Otherwise, it's where the whole squad is going now.
if (_mode isEqualTo "mount") exitWith {
	if ((_legs # 0 # 1) isEqualTo "") then {
		[_group] call brmh_cmd_fnc_callOffCare;
		[_group] call brmh_cmd_fnc_clearRoute;
		[_group] call brmh_cmd_fnc_stopMount;
	};
	[_group, _legs # 0 # 0, _legs # 0 # 1] call brmh_cmd_fnc_startMount;
	true
};
if (_mode isEqualTo "dismount") exitWith {
	[_group] call brmh_cmd_fnc_clearRoute;
	[_group, _legs # 0 # 0] call brmh_cmd_fnc_startDismount;
	true
};
if ((_legs findIf {
	not ((_x # 0) in ["CYCLE", "CLEAR"]) and {
		surfaceIsWater (_x # 1)
	}
}) >= 0) exitWith {
	_group setVariable ["brmh_cmd_unable", "water"];
	true
};
if (_mode in ["replace", "halt"]) then {
	[_group] call brmh_cmd_fnc_callOffCare;
	[_group] call brmh_cmd_fnc_stopMount;
};
[_group, _posture] call brmh_cmd_fnc_posture;
if (_mode isEqualTo "posture") exitWith {
	true
};
if (_mode isEqualTo "halt") exitWith {
	[_group] call brmh_cmd_fnc_clearRoute;
	// Clearing waypoints doesn't stop a walking group, and doFollow and doMove don't either. doStop does.
	doStop (units _group);
	true
};
// A leader on a gun won't go anywhere by waypoint, and neither will his squad. Anyone else stays on theirs.
private _leader = leader _group;
if (vehicle _leader isKindOf "StaticWeapon") then {
	[_leader] call brmh_cmd_fnc_getOff;
};
private _finished = currentWaypoint _group >= count waypoints _group;
if (_mode isEqualTo "replace") then {
	[_group] call brmh_cmd_fnc_clearRoute;
};
// A man in a seat told to follow climbs out to do it, and back in a few seconds later, so not when his leader is
// riding too. It's still needed when he isn't: a squad on foot barely moves while a man it left on a gun hasn't had it.
private _riding = vehicle (leader _group) isNotEqualTo (leader _group) and {
	not (vehicle (leader _group) isKindOf "StaticWeapon")
};
{
	if ([_x] call brmh_cmd_fnc_able and {
		not (_x getVariable ["brmh_cmd_busy", false])
	} and {
		not _riding or {
			vehicle _x isEqualTo _x
		}
	}) then {
		_x doFollow leader _group;
	};
} forEach units _group;
private _first = [];
{
	_x params ["_type", "_at", "_radius", "_completion", "_holdFor"];
	if (_type isEqualTo "CLEAR") then {
		[_group, _at] call brmh_cmd_fnc_startClearing;
		continue;
	};
	if (_type isEqualTo "OCCUPY") then {
		private _spots = nearestObject [_at + [0], "House"] buildingPos -1;
		[_group, _spots, []] call brmh_cmd_fnc_startPlacing;
		continue;
	};
	if (_type isEqualTo "CORDON") then {
		private _count = ({
			[_x] call brmh_cmd_fnc_able
		} count units _group) max 1;
		private _ring = [];
		for "_i" from 0 to (_count - 1) do {
			_ring pushBack ((_at + [0]) getPos [_radius, 360 * _i / _count]);
		};
		[_group, _ring, _at + [0]] call brmh_cmd_fnc_startPlacing;
		continue;
	};
	if (_type in ["ATTACK", "DEFEND", "PATROL_AREA", "SWEEP"]) then {
		[_group, _type, _at, _radius] call brmh_cmd_fnc_startTask;
		continue;
	};
	private _waypoint = _group addWaypoint [_at + [0], _radius];
	_waypoint setWaypointType _type;
	if (_completion > 0) then {
		_waypoint setWaypointCompletionRadius _completion;
	};
	if (_holdFor > 0) then {
		_waypoint setWaypointTimeout [_holdFor, _holdFor, _holdFor];
	};
	if (_first isEqualTo []) then {
		_first = _waypoint;
	};
} forEach _legs;
if (_first isNotEqualTo [] and {
	_mode isEqualTo "replace" or _finished
}) then {
	_group setCurrentWaypoint _first;
};
true
