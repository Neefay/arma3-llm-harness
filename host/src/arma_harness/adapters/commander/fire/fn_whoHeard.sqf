/*
	NAME: brmh_cmd_fnc_whoHeard
	DESCRIPTION: How far a burst was from each station's nearest able man, and whether any of its four nearest could
		see it land. It has to be right then, because dust and smoke hide the next one for free. Seen means within
		1,500 m and with a clear view of a point 1 m above the burst.
	PARAMETERS:
		0 - Where it burst, ASL [x, y, z] (ARRAY)
	USAGE:
		[_pos] call brmh_cmd_fnc_whoHeard;
	RETURNS: [[callsign, metres, dx, dy, seen], ...], dx and dy from that man to the burst; one row per station with
		an able man (ARRAY)
	ENVIRONMENT: Server, unscheduled (a shell's Explode handler)
*/
params ["_pos"];
private _ground = [_pos # 0, _pos # 1];
private _point = _pos vectorAdd [0, 0, 1];
private _rows = [];
{
	private _alive = (units _y) select {
		[_x] call brmh_cmd_fnc_able
	};
	if (_alive isNotEqualTo []) then {
		private _near = [_alive, [], {
			_x distance2D _ground
		}] call BIS_fnc_sortBy;
		private _from = getPosATL (_near # 0);
		private _metres = (_near # 0) distance2D _ground;
		private _seen = _metres < 1500 and {
			[_near select [0, 4], objNull, _point] call brmh_cmd_fnc_canSee
		};
		_rows pushBack [_x, _metres, (_ground # 0) - (_from # 0), (_ground # 1) - (_from # 1), _seen];
	};
} forEach brmh_cmd_stations;
_rows
