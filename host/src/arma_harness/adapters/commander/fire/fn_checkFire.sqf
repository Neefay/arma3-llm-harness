// The one thing that stops a mission once it's running. Combat modes and disableAI don't.
params ["_group", "_order", "_keys"];
private _guns = [_group, _keys] call brmh_cmd_fnc_gunsOf;
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
