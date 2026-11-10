/*
	NAME: brmh_cmd_fnc_setAmmo
	DESCRIPTION: Sets what a gun's main turret carries, by the commander's word for each kind of round
		(brmh_cmd_fnc_ammoWord). A kind's rounds all go to the first magazine type of that kind the gun carries, in full
		magazines and a last part one. Kinds not listed, and any other magazine type of a listed kind, are taken away.
	PARAMETERS:
		0 - Gun, local to this machine (OBJECT)
		1 - Rounds by kind: [[word, rounds], ...], words as brmh_cmd_fnc_ammoWord gives them (ARRAY)
	USAGE:
		[_vehicle, [["HE", 16], ["SMOKE", 4]]] call brmh_cmd_fnc_setAmmo;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
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
