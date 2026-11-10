/*
	NAME: brmh_cmd_fnc_setPylon
	DESCRIPTION: Loads a magazine on one of an aircraft's pylons, for the seat that owns that pylon: on a Blackfoot the
		gunner's pylons would otherwise move to the pilot. As ACE's pylons addon does it. A magazine the pylon can't take
		is logged, and the pylon left as it was.
	PARAMETERS:
		0 - Aircraft (OBJECT)
		1 - Pylon, from 1 (NUMBER)
		2 - Magazine class (STRING)
	USAGE:
		[_vehicle, 8, "PylonMissile_1Rnd_Mk82_F"] call brmh_cmd_fnc_setPylon;
	RETURNS: Whether it was loaded (BOOL)
	ENVIRONMENT: Server, where the aircraft is local
*/
params [["_vehicle", objNull, [objNull]], ["_pylon", 1, [0]], ["_magazine", "", [""]]];
private _turret = ((getAllPylonsInfo _vehicle) param [_pylon - 1, []]) param [2, [-1]];
if (_turret isEqualTo [-1]) then {
	_turret = [];
};
private _done = _vehicle setPylonLoadout [_pylon, _magazine, true, _turret];
if (not _done) then {
	["Spawn", "WARNING", "%1 can't take %2 on pylon %3", [typeOf _vehicle, _magazine, _pylon]] call brmh_cmd_fnc_log;
};
_done
