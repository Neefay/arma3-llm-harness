/*
	NAME: brmh_cmd_fnc_startFire
	DESCRIPTION: FIRE_MISSION: starts a station's fire mission on its guns, one fire machine per gun. Every way this
		can silently do nothing is checked first or watched for, and comes out in the packet as a state for the host
		to word. A gun that was already firing drops its old mission for the new one.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Order id (STRING)
		2 - [gun keys or [] for all, [x, y], "HE" or "SMOKE", rounds per gun, radius in metres or 0] (ARRAY)
	USAGE:
		[_group, "O-0006", [["V1"], [4150, 3350], "HE", 3, 0]] call brmh_cmd_fnc_startFire;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params [["_group", grpNull, [grpNull]], ["_order", "", [""]], ["_leg", [], [[]], 5]];
_leg params ["_keys", "_aim", "_word", "_want", "_radius"];
private _guns = [_group, _keys] call brmh_cmd_fnc_gunsOf;
private _missions = [];
if (_guns isEqualTo []) then {
	_missions pushBack (createHashMapFromArray [["key", ""], ["order", _order], ["state", "unable"], ["reason", "no gun"], ["word", _word], ["want", _want]]);
};
{
	private _gun = _x;
	private _mission = createHashMapFromArray [["key", _gun getVariable ["brmh_cmd_key", ""]], ["order", _order], ["state", "unable"], ["word", _word], ["want", _want], ["fired", 0], ["inAir", 0], ["aim", (_aim select [0, 2]) + [0]], ["radius", _radius], ["gun", _gun]];
	_missions pushBack _mission;
	private _crew = gunner _gun;
	// The first of the type asked for, or "": no index of -1 that could read from the end.
	private _magazine = ((getArtilleryAmmo [_gun]) select {
		([_x] call brmh_cmd_fnc_ammoWord) isEqualTo _word
	}) param [0, ""];
	if (isNull _gun or {
		not alive _gun
	}) then {
		_mission set ["reason", "destroyed"];
		continue;
	};
	if (isNull _crew or {
		not ([_crew] call brmh_cmd_fnc_able)
	} or {
		group _crew isNotEqualTo _group
	}) then {
		_mission set ["reason", "no gunner"];
		continue;
	};
	if (_magazine isEqualTo "") then {
		_mission set ["reason", "no ammo"];
		continue;
	};
	if (not ((_mission get "aim") inRangeOfArtillery [[_gun], _magazine])) then {
		_mission set ["reason", "out of range"];
		continue;
	};
	[_gun] call brmh_cmd_fnc_trackGun;
	_mission set ["mag", _magazine];
	_mission set ["state", "firing"];
	_mission set ["eta", _gun getArtilleryETA [_mission get "aim", _magazine]];
	_gun setVariable ["brmh_cmd_mission", _mission];
	_gun doWatch (_mission get "aim");
	[_mission] call brmh_cmd_fnc_fireChunk;
	// A mission already running on this gun ends here, through its machine, so a release step would run.
	{
		if ((_x get "GUN") isEqualTo _gun) then {
			_x call ["#END", []];
		};
	} forEach brmh_cmd_fireActive;
	brmh_cmd_fireActive = brmh_cmd_fireActive select {
		(_x get "GUN") isNotEqualTo _gun
	};
	brmh_cmd_fireActive pushBack ([brmh_cmd_fireMachine, [["GROUP", _group], ["ORDER", _order], ["SUBJECT", _mission get "key"], ["GUN", _gun], ["MISSION", _mission]]] call brmh_cmd_fnc_newMachine);
} forEach _guns;
private _kept = (_group getVariable ["brmh_cmd_missions", []]) select {
	private _key = _x get "key";
	(_missions findIf {
		(_x get "key") isEqualTo _key
	}) < 0
};
_group setVariable ["brmh_cmd_missions", _kept + _missions];
if (isNil "brmh_cmd_firePfh" and {
	brmh_cmd_fireActive isNotEqualTo []
}) then {
	brmh_cmd_firePfh = [{
		call brmh_cmd_fnc_stepFire
	}, 0.5] call CBA_fnc_addPerFrameHandler;
};
