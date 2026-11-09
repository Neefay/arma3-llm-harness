// How far an impact was from each station's nearest man, and whether it could see it land. It has to be right then,
// because dust and smoke hide the next one for free. Rows are [callsign, metres, dx, dy, seen].
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
