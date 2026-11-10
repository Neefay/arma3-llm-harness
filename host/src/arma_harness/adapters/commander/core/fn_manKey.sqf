/*
	NAME: brmh_cmd_fnc_manKey
	DESCRIPTION: A man's key, such as "m12", made the first time it's asked for and kept on him (brmh_cmd_man). It's
		what the host and the commander's casualty list call him by, and brmh_cmd_men turns it back into the man.
	PARAMETERS:
		0 - The man (OBJECT)
	USAGE:
		private _key = [_man] call brmh_cmd_fnc_manKey;
	RETURNS: His key (STRING)
	ENVIRONMENT: Server, unscheduled
*/
params ["_man"];
private _key = _man getVariable ["brmh_cmd_man", ""];
if (_key isEqualTo "") then {
	brmh_cmd_manCount = brmh_cmd_manCount + 1;
	_key = format ["m%1", brmh_cmd_manCount];
	_man setVariable ["brmh_cmd_man", _key];
};
// Back on the list under his old key after a battle cleared it: the count isn't reset, so it's still his alone.
brmh_cmd_men set [_key, _man];
_key
