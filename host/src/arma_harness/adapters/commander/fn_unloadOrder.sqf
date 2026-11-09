/*
	NAME: brmh_cmd_fnc_unloadOrder
	DESCRIPTION: Takes downed men out of a stopped vehicle, by a squad that has someone there.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Order id (STRING)
		2 - Who: [[man key, place], ...], or nobody for all of them (ARRAY)
		3 - Vehicle's key (STRING)
	ENVIRONMENT: Server
*/
params ["_group", "_order", "_who", "_key"];
private _vehicle = brmh_cmd_vehicles getOrDefault [_key, objNull];
if (isNull _vehicle or {
	not alive _vehicle
}) exitWith {
	[_group, _order, "unload", objNull, "wrecked", _key] call brmh_cmd_fnc_careSay;
};
if ((abs speed _vehicle) > 1) exitWith {
	[_group, _order, "unload", objNull, "moving", _key] call brmh_cmd_fnc_careSay;
};
if (((units _group) findIf {
	[_x] call brmh_cmd_fnc_able and {
		(_x distance2D _vehicle) < 25
	}
}) < 0) exitWith {
	[_group, _order, "unload", objNull, "nobody there", _key] call brmh_cmd_fnc_careSay;
};
private _aboard = (crew _vehicle) select {
	alive _x and {
		not ([_x] call brmh_cmd_fnc_able)
	}
};
private _men = if (_who isEqualTo []) then {
	_aboard
} else {
	[_who] call brmh_cmd_fnc_targets
};
if (_men isEqualTo []) exitWith {
	[_group, _order, "unload", objNull, "nobody aboard", _key] call brmh_cmd_fnc_careSay;
};
{
	if (_x in _aboard) then {
		[_group, _order, "unload", _x, "going", _key] call brmh_cmd_fnc_careSay;
		[_x] call ace_common_fnc_unloadPerson;
		[{
			params ["_man", "_group", "_order", "_key"];
			if (alive _man and {
				not ([_man] call brmh_cmd_fnc_able)
			}) then {
				[_man, "UnconsciousReviveDefault"] call brmh_cmd_fnc_carryPose;
			};
			[_group, _order, "unload", _man, ["stuck", "off"] select (vehicle _man isEqualTo _man), _key] call brmh_cmd_fnc_careSay;
		}, [_x, _group, _order, _key], 3] call CBA_fnc_waitAndExecute;
	} else {
		[_group, _order, "unload", _x, "not aboard", _key] call brmh_cmd_fnc_careSay;
	};
} forEach _men;
