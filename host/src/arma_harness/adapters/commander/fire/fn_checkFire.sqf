/*
	NAME: brmh_cmd_fnc_checkFire
	DESCRIPTION: CHECK_FIRE: stops a station's guns and ends their fire missions. doStop is the one thing that stops a
		mission once it's running; combat modes and disableAI don't. Each gun's record in the packet becomes
		"checked", keeping the rounds it fired and those still in the air. With no gun at all, one keyless row says so.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Order id (STRING)
		2 - Gun keys, or [] for every gun the station crews (ARRAY)
	USAGE:
		[_group, "O-0007", ["V1"]] call brmh_cmd_fnc_checkFire;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params [["_group", grpNull, [grpNull]], ["_order", "", [""]], ["_keys", [], [[]]]];
// Only its own guns: one crewed by another station is that station's to stop.
private _guns = ([_group, _keys] call brmh_cmd_fnc_gunsOf) select {
	not isNull _x and {
		isNull gunner _x or {
			group gunner _x isEqualTo _group
		}
	}
};
private _rows = [];
{
	private _gun = _x;
	if (alive _gun) then {
		doStop _gun;
	};
	private _mission = _gun getVariable ["brmh_cmd_mission", createHashMap];
	{
		if ((_x get "GUN") isEqualTo _gun) then {
			[_x, "stopped"] call brmh_cmd_fnc_fireFinish;
			_x call ["#END", []];
		};
	} forEach brmh_cmd_fireActive;
	_rows pushBack (createHashMapFromArray [["key", _gun getVariable ["brmh_cmd_key", ""]], ["order", _order], ["state", "checked"], ["word", ""], ["want", 0], ["fired", _mission getOrDefault ["fired", 0]], ["inAir", _mission getOrDefault ["inAir", 0]]]);
} forEach _guns;
brmh_cmd_fireActive = brmh_cmd_fireActive select {
	(_x get "STATE") isNotEqualTo ""
};
if (_rows isEqualTo []) then {
	_rows pushBack (createHashMapFromArray [["key", ""], ["order", _order], ["state", "checked"], ["word", ""], ["want", 0], ["fired", 0], ["inAir", 0]]);
};
private _kept = (_group getVariable ["brmh_cmd_missions", []]) select {
	private _key = _x get "key";
	(_rows findIf {
		(_x get "key") isEqualTo _key
	}) < 0
};
_group setVariable ["brmh_cmd_missions", _kept + _rows];
