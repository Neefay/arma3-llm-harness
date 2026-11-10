// Counts what an aircraft fires, and what with, for the machines that report it.
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
