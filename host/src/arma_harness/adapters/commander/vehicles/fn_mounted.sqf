/*
	NAME: brmh_cmd_fnc_mounted
	DESCRIPTION: Which of these men are in a vehicle, and where, for the packet's "mounted" field. A man the engine
		lists in no seat counts as cargo.
	PARAMETERS:
		0 - Soldiers, the squad's able men (ARRAY)
	USAGE:
		[_able] call brmh_cmd_fnc_mounted;
	RETURNS: [[vehicle id or "", seat role, name, on a static weapon], ...] (ARRAY)
	ENVIRONMENT: Server, unscheduled
*/
params ["_alive"];
private _out = [];
{
	private _soldier = _x;
	private _vehicle = vehicle _soldier;
	if (_vehicle isNotEqualTo _soldier) then {
		private _seat = (fullCrew _vehicle) select {
			(_x # 0) isEqualTo _soldier
		};
		_out pushBack [_vehicle getVariable ["brmh_cmd_key", ""], if (_seat isEqualTo []) then {
			"cargo"
		} else {
			_seat # 0 # 1
		}, name _soldier, _vehicle isKindOf "StaticWeapon"];
	};
} forEach _alive;
_out
