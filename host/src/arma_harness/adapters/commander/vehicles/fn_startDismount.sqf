/*
	NAME: brmh_cmd_fnc_startDismount
	DESCRIPTION: DISMOUNT: the squad's able men get off one vehicle, or everything they're in, and the group gives it
		up. A boarding under way stops first. The boarding machine, started in "going off", watches them out; with
		nobody aboard there's no machine, and the mount record says "none".
	PARAMETERS:
		0 - Group (GROUP)
		1 - Vehicle id, or "" for any (STRING)
	USAGE:
		[_group, "V2"] call brmh_cmd_fnc_startDismount;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params [["_group", grpNull, [grpNull]], ["_key", "", [""]]];
[_group] call brmh_cmd_fnc_stopMount;
private _men = (units _group) select {
	[_x] call brmh_cmd_fnc_able and {
		not isNull objectParent _x
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
