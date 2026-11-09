/*
	NAME: brmh_cmd_fnc_treatOrder
	DESCRIPTION: A station's medics go to downed men, one at a time each, and treat them. The time depends on where the man
		is: see brmh_cmd_careTimes. Early on it stops him dying, and at the end he gets up.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Order id (STRING)
		2 - Who: [[man key, place], ...], or nobody for everyone down within 100 m (ARRAY)
	ENVIRONMENT: Server
*/
params ["_group", "_order", "_who"];
private _medics = (units _group) select {
	[_x] call brmh_cmd_fnc_able and {
		[_x] call brmh_cmd_fnc_isMedic
	}
};
if (_medics isEqualTo []) exitWith {
	[_group, _order, "treat", objNull, "no medic"] call brmh_cmd_fnc_careSay;
};
private _men = [_who] call brmh_cmd_fnc_targets;
if (_who isEqualTo []) then {
	_men = brmh_cmd_down select {
		alive _x and {
			(_x distance2D leader _group) < 100
		} and {
			[_group, _x] call brmh_cmd_fnc_friendly
		}
	};
};
if (_men isEqualTo []) exitWith {
	[_group, _order, "treat", objNull, "nobody down"] call brmh_cmd_fnc_careSay;
};
private _queue = [];
{
	private _man = _x;
	private _places = _who select {
		(_x # 0) isEqualTo ([_man] call brmh_cmd_fnc_manKey)
	};
	switch (true) do {
		case (not alive _man): {
			[_group, _order, "treat", _man, "he died"] call brmh_cmd_fnc_careSay;
		};
		case ([_man] call brmh_cmd_fnc_able): {
			[_group, _order, "treat", _man, "up"] call brmh_cmd_fnc_careSay;
		};
		// He may be coming off right now. UNLOAD and TREAT sent together got one man treated and the other forgotten.
		case (vehicle _man isNotEqualTo _man and {
			not ([vehicle _man] call brmh_cmd_fnc_isMedicalVehicle)
		}): {
			[_group, _order, "treat", _man, "aboard", (vehicle _man) getVariable ["brmh_cmd_key", ""]] call brmh_cmd_fnc_careSay;
			_queue pushBack _man;
		};
		// Sent to where he was last reported. If he isn't anywhere near it, they won't find him.
		case (_places isNotEqualTo [] and {
			(_man distance2D ((_places # 0) # 1)) > 150
		}): {
			[_group, _order, "treat", _man, "can't find"] call brmh_cmd_fnc_careSay;
		};
		default {
			[_group, _order, "treat", _man, "queued"] call brmh_cmd_fnc_careSay;
			_queue pushBack _man;
		};
	};
} forEach _men;
if (_queue isEqualTo []) exitWith {};
// Told again about someone it's still waiting on: this order has him now, or he'd get two medics.
{
	if ((_x get "group") isEqualTo _group) then {
		_x set ["queue", (_x get "queue") - _queue];
	};
} forEach brmh_cmd_treats;
brmh_cmd_treats pushBack (createHashMapFromArray [["group", _group], ["order", _order], ["queue", _queue]]);
