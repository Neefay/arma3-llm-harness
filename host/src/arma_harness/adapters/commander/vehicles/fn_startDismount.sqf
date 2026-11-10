params ["_group", "_key"];
[_group] call brmh_cmd_fnc_stopMount;
private _men = (units _group) select {
	[_x] call brmh_cmd_fnc_able and {
		vehicle _x isNotEqualTo _x
	} and {
		_key isEqualTo "" or {
			(vehicle _x getVariable ["brmh_cmd_key", ""]) isEqualTo _key
		}
	}
};
{
	_group leaveVehicle (vehicle _x);
	[_x] call brmh_cmd_fnc_getOff;
} forEach _men;
_group setVariable ["brmh_cmd_mount", [_key, ["none", "going off"] select (_men isNotEqualTo []), "", _men apply {
	name _x
}]];
if (_men isNotEqualTo []) then {
	brmh_cmd_builds pushBack ([brmh_cmd_boardingMachine, [["GROUP", _group], ["ORDER", _group getVariable ["brmh_cmd_order", ""]], ["SUBJECT", _key], ["KEY", _key], ["START", "going off"]]] call brmh_cmd_fnc_newMachine);
};
