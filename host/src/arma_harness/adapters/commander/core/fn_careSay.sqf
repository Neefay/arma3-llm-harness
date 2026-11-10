/*
	NAME: brmh_cmd_fnc_careSay
	DESCRIPTION: A radio line for the host to word, kept on the squad (brmh_cmd_care) for its packet's "medical"
		field. One row for each man, job and order, whatever its latest state is: a new state replaces the row's old
		one. Only the last 40 rows are kept.
	PARAMETERS:
		0 - Squad (GROUP)
		1 - Order id (STRING)
		2 - Job, the machine's KIND such as "carry", "treat" or "strike" (STRING)
		3 - Who it's about: a man, objNull for the squad as a whole, or a subject key such as "post" (OBJECT or STRING)
		4 - State, the word the host turns into the line, such as "going" or "he died" (STRING)
		5 - (OPTIONAL) Detail the word needs, such as a vehicle's key (STRING) - Default: ""
	USAGE:
		[_group, _order, "carry", _man, "going"] call brmh_cmd_fnc_careSay;
		[_group, _order, "unload", objNull, "nobody aboard", _key] call brmh_cmd_fnc_careSay;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
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
