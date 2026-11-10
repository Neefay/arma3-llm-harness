/*
	NAME: brmh_cmd_fnc_seatMan
	DESCRIPTION: Assigns a man to one seat, by the engine's own seat assignment, so that orderGetIn sends him to that
		seat and no other. It doesn't move or order him.
	PARAMETERS:
		0 - Soldier (OBJECT)
		1 - Vehicle (OBJECT)
		2 - Seat, a fullCrew row [unit, role, cargo index, turret path, ...] (ARRAY)
	USAGE:
		[_man, _vehicle, ([_vehicle, "gunner"] call brmh_cmd_fnc_freeSeats) # 0] call brmh_cmd_fnc_seatMan;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_man", "_vehicle", "_seat"];
_seat params ["", "_role", "_cargo", "_turret"];
switch (_role) do {
	case "driver": {
		_man assignAsDriver _vehicle;
	};
	case "gunner": {
		_man assignAsGunner _vehicle;
	};
	case "commander": {
		_man assignAsCommander _vehicle;
	};
	case "cargo": {
		_man assignAsCargoIndex [_vehicle, _cargo];
	};
	default {
		_man assignAsTurret [_vehicle, _turret];
	};
};
