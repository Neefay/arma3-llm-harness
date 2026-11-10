/*
	NAME: brmh_cmd_fnc_onSeat
	DESCRIPTION: A gun's crew only fires when ordered. A crewed gun otherwise opens up by itself at any enemy its crew
		knows of, so its gunner has his targeting off until he next gets out of a vehicle (a GetOutMan handler, added
		once per man). Anyone else, in any other seat, is left alone.
	PARAMETERS:
		0 - Soldier (OBJECT)
		1 - The vehicle he's in (OBJECT)
	USAGE:
		[_man, _vehicle] call brmh_cmd_fnc_onSeat;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_man", "_vehicle"];
if (getNumber (configOf _vehicle >> "artilleryScanner") > 0 and {
	gunner _vehicle isEqualTo _man
}) then {
	_man disableAI "TARGET";
	if (isNil {
		_man getVariable "brmh_cmd_offGunHandler"
	}) then {
		_man setVariable ["brmh_cmd_offGunHandler", _man addEventHandler ["GetOutMan", {
			params ["_unit"];
			_unit enableAI "TARGET";
		}]];
	};
};
