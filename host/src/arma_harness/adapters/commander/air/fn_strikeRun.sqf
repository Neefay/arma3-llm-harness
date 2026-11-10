/*
	NAME: brmh_cmd_fnc_strikeRun
	DESCRIPTION: Lined up: the route runs through the grid and 6 km on, and an ACE laser bomb gets its laser, shone
		straight down on the grid by nobody, as a designator would. The release is checked every frame from here on, by
		a per-frame handler that the machine's RELEASE removes, with the laser a minute later. Run again after going
		around, it keeps the laser and the handler it has.
	PARAMETERS:
		0 - Strike machine (HASHMAP object)
	USAGE:
		[_this] call brmh_cmd_fnc_strikeRun;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled. The strike machine's "in hot" action.
*/
params ["_machine"];
private _group = _machine get "GROUP";
private _aim = _machine get "AIM";
// Through the grid and on: with the grid as his last waypoint, a pilot starts turning to circle it from 5 km out, and
// his track drifts 11° off by the release.
[_group] call brmh_cmd_fnc_clearRoute;
(_group addWaypoint [ASLToAGL _aim, 0]) setWaypointType "MOVE";
(_group addWaypoint [_aim getPos [6000, _machine get "HEADING"], 0]) setWaypointType "MOVE";
if ((_machine get "GUIDANCE") isEqualTo "SALH" and {
	(_machine getOrDefault ["LASER", []]) isEqualTo []
}) then {
	// Each strike its own code: a seeker takes any laser on its code that it can see, and a finished strike's stays on
	// for a minute. ACE's codes run from 1111 to 1788, and it reads the shooter's when the bomb is fired.
	private _index = brmh_cmd_laserCount mod 64;
	brmh_cmd_laserCount = brmh_cmd_laserCount + 1;
	private _code = 1111 + 10 * floor (_index / 8) + (_index mod 8);
	(_machine get "VEHICLE") setVariable ["ace_laser_code", _code];
	private _emitter = createVehicle ["Land_HelipadEmpty_F", ASLToAGL _aim, [], 0, "CAN_COLLIDE"];
	// The aim goes as the method's own argument: ACE keeps the emitter on every machine, and a variable on the helper
	// would exist only here.
	private _uuid = [_emitter, _emitter, {
		[(_this # 6) vectorAdd [0, 0, 150], [0, 0, -1]]
	}, 1550, _code, 1, _aim] call ace_laser_fnc_laserOn;
	_machine set ["LASER", [_uuid, _emitter]];
};
// Long enough to arrive: a direct run starts wherever the aircraft is, which can be far.
_machine set ["RUN_S", 120 + (((_machine get "VEHICLE") distance2D _aim) / 60)];
if ((_machine getOrDefault ["PFH", -1]) < 0) then {
	_machine set ["PFH", [{
		(_this # 0) params ["_machine"];
		if ((_machine get "STATE") isNotEqualTo "run") exitWith {};
		[_machine] call brmh_cmd_fnc_strikeRelease;
	}, 0, [_machine]] call CBA_fnc_addPerFrameHandler];
};
