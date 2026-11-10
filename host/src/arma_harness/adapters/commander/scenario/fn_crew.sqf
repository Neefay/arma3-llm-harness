/*
	NAME: brmh_cmd_fnc_crew
	DESCRIPTION: Starts a scenario with a soldier already in a seat: the last of the station's men on foot, in the first
		free seat of that kind. Called once a seat, so a helicopter can get a pilot and a gunner. Operator action, never
		reachable by the commander.
	PARAMETERS:
		0 - Callsign (STRING)
		1 - Vehicle id, the scenario's (STRING)
		2 - (OPTIONAL) Seat: gunner, driver, commander or cargo (STRING) - Default: "gunner"
	USAGE:
		["Hammer", "V1", "gunner"] call brmh_cmd_fnc_crew;
	RETURNS: Whether anybody got on (BOOL)
	ENVIRONMENT: Server, unscheduled
*/
params [["_callsign", "", [""]], ["_key", "", [""]], ["_kind", "gunner", [""]]];
private _group = brmh_cmd_stations getOrDefault [_callsign, grpNull];
private _vehicle = brmh_cmd_vehicles getOrDefault [_key, objNull];
private _seat = ([_vehicle, _kind] call brmh_cmd_fnc_freeSeats) param [0, []];
private _free = (units _group) select {
	isNull objectParent _x
};
reverse _free;
if (_seat isEqualTo [] or {
	_free isEqualTo []
}) exitWith {
	false
};
private _man = _free # 0;
[_man, _vehicle, _seat] call brmh_cmd_fnc_seatMan;
switch (_kind) do {
	case "driver": {
		_man moveInDriver _vehicle;
	};
	case "commander": {
		_man moveInCommander _vehicle;
	};
	case "cargo": {
		_man moveInCargo [_vehicle, _seat # 2];
	};
	default {
		_man moveInGunner _vehicle;
	};
};
[_man, _vehicle] call brmh_cmd_fnc_onSeat;
true
