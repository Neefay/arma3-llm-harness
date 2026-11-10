// Sets what a gun's main turret carries, from [["HE", 16], ["SMOKE", 4]]. Types not listed are taken away.
params ["_vehicle", "_ammo"];
private _wanted = createHashMapFromArray _ammo;
private _carried = [];
{
	if ((_x # 1) isEqualTo [0]) then {
		_carried pushBackUnique (_x # 0);
	};
} forEach magazinesAllTurrets _vehicle;
{
	private _magazine = _x;
	private _rounds = _wanted getOrDefault [[_magazine] call brmh_cmd_fnc_ammoWord, 0];
	private _size = getNumber (configFile >> "CfgMagazines" >> _magazine >> "count");
	_vehicle removeMagazinesTurret [_magazine, [0]];
	while {
		_rounds > 0 and {
			_size > 0
		}
	} do {
		_vehicle addMagazineTurret [_magazine, [0], _rounds min _size];
		_rounds = _rounds - _size;
	};
	_wanted deleteAt ([_magazine] call brmh_cmd_fnc_ammoWord);
} forEach _carried;
