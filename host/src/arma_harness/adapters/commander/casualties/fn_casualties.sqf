/*
	NAME: brmh_cmd_fnc_casualties
	DESCRIPTION: Who a squad knows is down, for its report: its own, wherever they are, and anyone else's on its side
		within 30 m of its leader and in his sight. Each man gets a key the first time he's listed.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Its leader, whose sight counts (OBJECT)
	USAGE:
		["casualties", [_group, _leader] call brmh_cmd_fnc_casualties]
	RETURNS: [[man key, name, x, y, vehicle key or "", aboard, ours, "", "carried" or "treated"], ...] (ARRAY)
	ENVIRONMENT: Server, unscheduled
*/
params ["_group", "_leader"];
private _down = (units _group) select {
	alive _x and {
		not ([_x] call brmh_cmd_fnc_able)
	}
};
// Within sight: near isn't enough, and a man down behind a wall can't be reported.
private _others = brmh_cmd_down select {
	alive _x and {
		group _x isNotEqualTo _group
	} and {
		[_group, _x] call brmh_cmd_fnc_friendly
	} and {
		(_x distance2D _leader) < 30
	} and {
		[[_leader], vehicle _x, (getPosASL _x) vectorAdd [0, 0, 0.4]] call brmh_cmd_fnc_canSee
	}
};
(_down + _others) apply {
	private _position = getPosATL _x;
	[[_x] call brmh_cmd_fnc_manKey, name _x, _position # 0, _position # 1, (vehicle _x) getVariable ["brmh_cmd_key", ""],
	 vehicle _x isNotEqualTo _x, group _x isEqualTo _group, _x getVariable ["brmh_cmd_handled", ""]]
}
