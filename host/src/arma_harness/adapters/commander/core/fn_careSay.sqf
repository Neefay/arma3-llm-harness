// A radio line for the host to word. One row for each man, job and order, whatever its latest state is.
params ["_group", "_order", "_kind", "_man", "_state", ["_detail", ""]];
if (isNull _group) exitWith {};
private _key = if (_man isEqualType objNull) then {
	if (isNull _man) then {
		""
	} else {
		[_man] call brmh_cmd_fnc_manKey
	}
} else {
	_man
};
private _name = if (_man isEqualType objNull and {
	not isNull _man
}) then {
	name _man
} else {
	""
};
private _rows = _group getVariable ["brmh_cmd_care", []];
private _at = _rows findIf {
	(_x # 0) isEqualTo _order and {
		(_x # 1) isEqualTo _kind
	} and {
		(_x # 2) isEqualTo _key
	}
};
private _row = [_order, _kind, _key, _name, _state, _detail];
if (_at < 0) then {
	_rows pushBack _row;
} else {
	_rows set [_at, _row];
};
_group setVariable ["brmh_cmd_care", _rows select [(count _rows - 40) max 0, 40]];
