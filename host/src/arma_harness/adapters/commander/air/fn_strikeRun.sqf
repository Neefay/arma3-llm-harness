// Lined up: the route runs to the grid, and an ACE laser bomb gets its laser, shone down on the grid by
// nobody, as a designator would. The release is checked every frame from here on.
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
	private _emitter = createVehicle ["Land_HelipadEmpty_F", ASLToAGL _aim, [], 0, "CAN_COLLIDE"];
	_emitter setVariable ["brmh_cmd_aim", _aim];
	private _uuid = [_emitter, _emitter, {
		params ["_emitter"];
		[(_emitter getVariable "brmh_cmd_aim") vectorAdd [0, 0, 150], [0, 0, -1]]
	}, 1550, 1111, 1] call ace_laser_fnc_laserOn;
	_machine set ["LASER", [_uuid, _emitter]];
};
if ((_machine getOrDefault ["PFH", -1]) < 0) then {
	_machine set ["PFH", [{
		(_this # 0) params ["_machine"];
		if ((_machine get "STATE") isNotEqualTo "run") exitWith {};
		[_machine] call brmh_cmd_fnc_strikeRelease;
	}, 0, [_machine]] call CBA_fnc_addPerFrameHandler];
};
