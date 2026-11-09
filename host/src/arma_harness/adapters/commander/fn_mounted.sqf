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
