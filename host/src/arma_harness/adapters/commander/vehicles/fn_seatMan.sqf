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
