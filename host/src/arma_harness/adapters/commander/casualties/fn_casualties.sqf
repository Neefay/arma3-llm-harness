// Who a squad knows is down: its own, wherever they are, and anyone else's on its side within sight of its leader.
params ["_group", "_leader"];
private _down = (units _group) select {
	alive _x and {
		not ([_x] call brmh_cmd_fnc_able)
	}
};
// Within sight, as the comment above says: near isn't enough, and a man down behind a wall can't be reported.
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
