params ["_unit"];
private _compatible = (compatibleMagazines primaryWeapon _unit) apply {
	toLowerANSI _x
};
private _rounds = 0;
// magazinesAmmo leaves out the loaded magazine; magazinesAmmoFull includes it.
{
	if (toLowerANSI (_x # 0) in _compatible) then {
		_rounds = _rounds + (_x # 1);
	};
} forEach magazinesAmmoFull _unit;
_rounds
