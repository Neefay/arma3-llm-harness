params ["_group", "_key", "_kind"];
private _vehicle = brmh_cmd_vehicles getOrDefault [_key, objNull];
// One man sent to a seat while others are still boarding: they're no longer watched, as before.
[_group, ["boarding"]] call brmh_cmd_fnc_endMachines;
_group setVariable ["brmh_cmd_mount", []];
if (isNull _vehicle or {
	not alive _vehicle
}) exitWith {
	_group setVariable ["brmh_cmd_mount", [_key, "wrecked", _kind, []]];
};
private _leader = leader _group;
// The newest first, and the leader last: a leader on a gun stays there and holds the squad with him.
private _newestFirst = +(units _group);
reverse _newestFirst;
// Not a man carrying someone, or one who's too far off to be part of this.
private _free = _newestFirst select {
	[_x] call brmh_cmd_fnc_able and {
		_x isNotEqualTo _leader
	} and {
		vehicle _x isEqualTo _x
	} and {
		not (_x getVariable ["brmh_cmd_busy", false])
	} and {
		(_x distance2D _vehicle) < 500
	}
};
if ([_leader] call brmh_cmd_fnc_able and {
	vehicle _leader isEqualTo _leader
} and {
	not (_leader getVariable ["brmh_cmd_busy", false])
}) then {
	_free pushBack _leader;
};
private _seats = [];
if (_kind isEqualTo "") then {
	{
		_seats append ([_vehicle, _x] call brmh_cmd_fnc_freeSeats);
	} forEach ["driver", "gunner", "commander", "cargo", "turret"];
} else {
	if ((_kind select [0, 7]) isEqualTo "turret:") then {
		private _all = (fullCrew [_vehicle, "", true]) select {
			(_x # 1) isEqualTo "turret"
		};
		private _index = parseNumber (_kind select [7]);
		_seats = (_all select [_index, 1]) select {
			isNull (_x # 0) or {
				not alive (_x # 0)
			}
		};
	} else {
		if (((fullCrew [_vehicle, "", true]) findIf {
			(_x # 1) isEqualTo _kind
		}) < 0) exitWith {
			_group setVariable ["brmh_cmd_mount", [_key, "noseat", _kind, []]];
		};
		_seats = ([_vehicle, _kind] call brmh_cmd_fnc_freeSeats) select [0, 1];
	};
};
if ((_group getVariable ["brmh_cmd_mount", []]) isEqualTo [_key, "noseat", _kind, []]) exitWith {};
if (_seats isEqualTo []) exitWith {
	_group setVariable ["brmh_cmd_mount", [_key, "taken", _kind, []]];
};
if (_free isEqualTo []) exitWith {
	_group setVariable ["brmh_cmd_mount", [_key, "nobody", _kind, []]];
};
private _list = [];
{
	if (_forEachIndex < count _free) then {
		private _man = _free # _forEachIndex;
		[_man, _vehicle, _x] call brmh_cmd_fnc_seatMan;
		_list pushBack [_man, _x # 1, _x # 2, _x # 3];
	};
} forEach _seats;
if (not (_vehicle isKindOf "StaticWeapon")) then {
	_group addVehicle _vehicle;
};
(_list apply {
	_x # 0
}) orderGetIn true;
_group setVariable ["brmh_cmd_mount", [_key, "going", _kind, []]];
// Only when it asked for everyone who fits. A named seat is for one man.
private _spare = [0, ((count _free) - (count _seats)) max 0] select (_kind isEqualTo "");
brmh_cmd_builds pushBack ([brmh_cmd_boardingMachine, [["GROUP", _group], ["ORDER", _group getVariable ["brmh_cmd_order", ""]], ["SUBJECT", _key], ["VEHICLE", _vehicle], ["KEY", _key], ["SEAT", _kind], ["LIST", _list], ["SPARE", _spare], ["WITHIN", 60 + ((_leader distance2D _vehicle) / 1.5)]]] call brmh_cmd_fnc_newMachine);
