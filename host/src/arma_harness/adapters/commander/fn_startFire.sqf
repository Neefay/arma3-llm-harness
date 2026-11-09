/*
	NAME: brmh_cmd_fnc_startFire
	DESCRIPTION: Starts a station's fire mission on its guns. Every way this can silently do nothing is checked first or
		watched for, and comes out in the packet as a state for the host to word.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Order id (STRING)
		2 - [gun keys, [x, y], "HE" or "SMOKE", rounds, radius] (ARRAY)
	ENVIRONMENT: Server
*/
params ["_group", "_order", "_leg"];
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
	private _magazine = (getArtilleryAmmo [_gun]) param [(getArtilleryAmmo [_gun]) findIf {
		([_x] call brmh_cmd_fnc_ammoWord) isEqualTo _word
	}, ""];
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
