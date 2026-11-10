/*
	NAME: brmh_cmd_fnc_countShots
	DESCRIPTION: Counts what an aircraft fires, and what with, for the machines that report it. One Fired handler per
		aircraft, kept for its life: the counts only grow, and each machine keeps the count it started from. On the
		aircraft: brmh_cmd_shots (every shot), brmh_cmd_bombs (bombs only) and brmh_cmd_lastShot
		([time, "bombs", "missiles", "rockets" or "guns"]).
	PARAMETERS:
		0 - Aircraft (OBJECT)
	USAGE:
		[_vehicle] call brmh_cmd_fnc_countShots;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_vehicle"];
if (not isNil {
	_vehicle getVariable "brmh_cmd_shotsHandler"
}) exitWith {};
_vehicle setVariable ["brmh_cmd_shotsHandler", _vehicle addEventHandler ["Fired", {
	params ["_vehicle", "", "", "", "_ammo"];
	private _word = switch (true) do {
		case (_ammo isKindOf ["BombCore", configFile >> "CfgAmmo"]): {
			"bombs"
		};
		case (_ammo isKindOf ["MissileCore", configFile >> "CfgAmmo"]): {
			"missiles"
		};
		case (_ammo isKindOf ["RocketCore", configFile >> "CfgAmmo"]): {
			"rockets"
		};
		default {
			"guns"
		};
	};
	_vehicle setVariable ["brmh_cmd_lastShot", [time, _word]];
	_vehicle setVariable ["brmh_cmd_shots", (_vehicle getVariable ["brmh_cmd_shots", 0]) + 1];
	if (_word isEqualTo "bombs") then {
		_vehicle setVariable ["brmh_cmd_bombs", (_vehicle getVariable ["brmh_cmd_bombs", 0]) + 1];
	};
}]];
