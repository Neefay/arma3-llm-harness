/*
	NAME: brmh_cmd_fnc_posture
	DESCRIPTION: Sets a squad's speed, formation, behaviour and combat mode, each only if given.
	PARAMETERS:
		0 - Squad (GROUP)
		1 - Posture: [speed, formation, behaviour, combat mode], in the engine's own words; "" leaves a setting
		    alone (ARRAY)
	USAGE:
		[_group, ["LIMITED", "", "STEALTH", ""]] call brmh_cmd_fnc_posture;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_group", "_posture"];
_posture params ["_speed", "_formation", "_behaviour", "_combatMode"];
if (_speed isNotEqualTo "") then {
	_group setSpeedMode _speed;
};
if (_formation isNotEqualTo "") then {
	_group setFormation _formation;
};
if (_behaviour isNotEqualTo "") then {
	_group setBehaviour _behaviour;
};
if (_combatMode isNotEqualTo "") then {
	_group setCombatMode _combatMode;
};
