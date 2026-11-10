/*
	NAME: brmh_cmd_fnc_trackGun
	DESCRIPTION: Watches a gun's rounds, once per gun, for its life. Each shot counts on the gun's current mission
		(fired, in the air, last shot), and its burst is a cmd_impact event: where, from which gun and order, and how
		each station heard or saw it (brmh_cmd_fnc_whoHeard). A burst also damages any aid post near it.
	PARAMETERS:
		0 - Gun (OBJECT)
	USAGE:
		[_vehicle] call brmh_cmd_fnc_trackGun;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled. Its handlers run there too, where the gun and its shells are local
*/
params ["_gun"];
if (_gun getVariable ["brmh_cmd_tracked", false]) exitWith {};
_gun setVariable ["brmh_cmd_tracked", true];
_gun addEventHandler ["Fired", {
	params ["_gun", "", "", "", "_ammo", "", "_shell"];
	private _mission = _gun getVariable ["brmh_cmd_mission", createHashMap];
	if (count _mission > 0) then {
		_mission set ["fired", (_mission getOrDefault ["fired", 0]) + 1];
		_mission set ["inAir", (_mission getOrDefault ["inAir", 0]) + 1];
		_mission set ["lastShot", time];
	};
	_shell setVariable ["brmh_cmd_from", [_gun getVariable ["brmh_cmd_key", ""], _mission getOrDefault ["order", ""], side group gunner _gun]];
	_shell setVariable ["brmh_cmd_mission", _mission];
	_shell addEventHandler ["Explode", {
		params ["_shell", "_pos"];
		private _mission = _shell getVariable ["brmh_cmd_mission", createHashMap];
		if (count _mission > 0) then {
			_mission set ["inAir", ((_mission getOrDefault ["inAir", 1]) - 1) max 0];
		};
		[_pos, typeOf _shell] call brmh_cmd_fnc_shellOnPosts;
		(_shell getVariable ["brmh_cmd_from", ["", "", sideUnknown]]) params ["_key", "_order", "_side"];
		["evt", createHashMapFromArray [
			["type", "cmd_impact"],
			["gun", _key],
			["order", _order],
			["side", str _side],
			["ammo", typeOf _shell],
			["pos", [_pos # 0, _pos # 1]],
			["heard", [_pos] call brmh_cmd_fnc_whoHeard]
		]] call BRMH_fnc_emit;
	}];
}];
