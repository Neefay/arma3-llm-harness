/*
	NAME: brmh_cmd_fnc_truth
	DESCRIPTION: Where everyone really is, for the after-action review and the objectives: every west, east and
		independent group, and whether each vehicle the harness spawned is still alive. Never reaches the commander.
	PARAMETERS: None
	USAGE:
		call brmh_cmd_fnc_truth;
	RETURNS: Nothing. Emits "evt" with type "cmd_truth"
	ENVIRONMENT: Server, unscheduled (every 5 s, from brmh_cmd_fnc_step)
*/
private _groups = (allGroups select {
	side _x in [west, east, independent]
}) apply {
	private _able = (units _x) select {
		[_x] call brmh_cmd_fnc_able
	};
	createHashMapFromArray [
		["group", groupId _x],
		["side", str side _x],
		["able", count _able],
		["down", ((units _x) select {
			alive _x and {
				not ([_x] call brmh_cmd_fnc_able)
			}
		}) apply {
			private _position = getPosATL _x;
			[round (_position # 0), round (_position # 1)]
		}],
		["mounted", {
			vehicle _x isNotEqualTo _x
		} count _able],
		["limping", {
			(_x getHitPointDamage "hitLegs") >= 0.5
		} count _able],
		["leader_limping", ((leader _x) getHitPointDamage "hitLegs") >= 0.5],
		["pos", if (_able isEqualTo []) then {
			[]
		} else {
			(getPosATL (_able # 0)) select [0, 2]
		}],
		["units", _able apply {
			private _position = getPosATL _x;
			[round (_position # 0), round (_position # 1), round (_position # 2)]
		}]
	]
};
private _vehicles = [];
{
	if (_y getVariable ["brmh_cmd_spawned", false]) then {
		_vehicles pushBack [_x, alive _y];
	};
} forEach brmh_cmd_vehicles;
["evt", createHashMapFromArray [["type", "cmd_truth"], ["groups", _groups], ["vehicles", _vehicles]]] call BRMH_fnc_emit;
