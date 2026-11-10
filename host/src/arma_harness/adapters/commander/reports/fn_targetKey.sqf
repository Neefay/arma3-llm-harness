/*
	NAME: brmh_cmd_fnc_targetKey
	DESCRIPTION: An enemy weapon or vehicle's key, the one the commander's list follows it by, made the first time it's
		asked for. Every squad that sees it gets the same key: the owner chose one entry per real gun over k entries for
		k reports. It joins the vehicles, so the sightings see it abandoned or wrecked, and the reset between battles
		takes it away.
	PARAMETERS:
		0 - Weapon or vehicle (OBJECT)
	USAGE:
		private _key = [_vehicle] call brmh_cmd_fnc_targetKey;
	RETURNS: Its key: "E" and a number, unless it already had one (STRING)
	ENVIRONMENT: Server, unscheduled
*/
params ["_object"];
private _key = _object getVariable ["brmh_cmd_key", ""];
if (_key isEqualTo "") then {
	brmh_cmd_targetCount = (missionNamespace getVariable ["brmh_cmd_targetCount", 0]) + 1;
	_key = format ["E%1", brmh_cmd_targetCount];
	_object setVariable ["brmh_cmd_key", _key];
	brmh_cmd_vehicles set [_key, _object];
};
_key
