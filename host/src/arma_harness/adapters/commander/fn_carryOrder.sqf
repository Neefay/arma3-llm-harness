/*
	NAME: brmh_cmd_fnc_carryOrder
	DESCRIPTION: A squad's free men each pick up a downed man, and carry him to a place or into a vehicle. The rest of the
		squad carries on with its orders. With no list, it's everyone down within 100 m. A man it's already carrying goes
		to the new place instead.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Order id (STRING)
		2 - Who: [[man key, place], ...] (ARRAY)
		3 - To: a position, or a vehicle's key (ARRAY or STRING)
	ENVIRONMENT: Server
*/
params ["_group", "_order", "_who", "_to"];
private _target = if (_to isEqualType "") then {
	brmh_cmd_vehicles getOrDefault [_to, objNull]
} else {
	_to
};
if (_target isEqualType objNull and {
	isNull _target or {
		not alive _target
	}
}) exitWith {
	[_group, _order, "carry", objNull, "wrecked", _to] call brmh_cmd_fnc_careSay;
};
// A post isn't something to get into: it's somewhere to put him down. Clear of it, or nobody can walk up to him.
private _post = objNull;
if (_target isEqualType objNull and {
	_target in brmh_cmd_posts
}) then {
	_post = _target;
};
private _men = [_who] call brmh_cmd_fnc_targets;
if (_who isEqualTo []) then {
	_men = (brmh_cmd_down + ((units _group) select {
		alive _x and {
			not ([_x] call brmh_cmd_fnc_able)
		}
	})) arrayIntersect (brmh_cmd_down + units _group);
	_men = _men select {
		(_x distance2D leader _group) < 100 and {
			[_group, _x] call brmh_cmd_fnc_friendly
		}
	};
};
if (_men isEqualTo []) exitWith {
	[_group, _order, "carry", objNull, "nobody down"] call brmh_cmd_fnc_careSay;
};
private _bearers = (units _group) select {
	[_x] call brmh_cmd_fnc_able and {
		vehicle _x isEqualTo _x
	} and {
		not (_x getVariable ["brmh_cmd_busy", false])
	}
};
{
	private _man = _x;
	private _place = if (isNull _post) then {
		_target
	} else {
		_post getPos [11, (_post getDir _man) + (_forEachIndex * 35) - 35]
	};
	switch (true) do {
		case (not alive _man): {
			[_group, _order, "carry", _man, "he died"] call brmh_cmd_fnc_careSay;
		};
		case ([_man] call brmh_cmd_fnc_able): {
			[_group, _order, "carry", _man, "he woke"] call brmh_cmd_fnc_careSay;
		};
		case (vehicle _man isNotEqualTo _man): {
			[_group, _order, "carry", _man, "aboard", (vehicle _man) getVariable ["brmh_cmd_key", ""]] call brmh_cmd_fnc_careSay;
		};
		case ((_man getVariable ["brmh_cmd_handled", ""]) isNotEqualTo ""): {
			// This squad's own carry takes the new place. Another squad's has to be called off first.
			private _held = brmh_cmd_carries select {
				(_x get "SUBJECT") isEqualTo _man and {
					(_x get "GROUP") isEqualTo _group
				} and {
					(_x get "STATE") in ["going", "fetching", "lifting", "carrying"]
				}
			};
			if (_held isEqualTo []) then {
				[_group, _order, "carry", _man, "already"] call brmh_cmd_fnc_careSay;
			} else {
				[_held # 0, _place, _order] call brmh_cmd_fnc_carryRedirect;
				[_group, _order, "carry", _man, "going"] call brmh_cmd_fnc_careSay;
			};
		};
		case (_bearers isEqualTo []): {
			[_group, _order, "carry", _man, "no bearer"] call brmh_cmd_fnc_careSay;
		};
		default {
			private _nearest = [_bearers, [_man], {
				// The leader last: the squad's orders go through him.
				(_x distance _input0) + ([0, 1000] select (_x isEqualTo leader group _x))
			}] call BIS_fnc_sortBy;
			private _bearer = _nearest # 0;
			_bearers = _bearers - [_bearer];
			[_group, _order, "carry", _man, "going"] call brmh_cmd_fnc_careSay;
			[_bearer, _man, _place, _group, _order] call brmh_cmd_fnc_startCarry;
		};
	};
} forEach _men;
