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
