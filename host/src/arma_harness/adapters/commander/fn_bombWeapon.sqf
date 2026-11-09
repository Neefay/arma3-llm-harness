// The weapon that drops the aircraft's bombs on a grid, how they're guided: "SALH" (laser) or "GPS" for ACE's own,
// "" for a dumb bomb that falls where it's released, and a dumb bomb's side friction for brmh_cmd_fnc_bombImpact. ACE's go first. The engine's own laser bombs can't be used: with
// nothing locked they glide on for kilometres (spike_bomb_drag.py), so an aircraft with only those gets "laser". Empty
// when it has no bombs left.
params ["_vehicle"];
private _guided = [];
private _dumb = [];
private _laser = false;
{
	private _ammo = getText (configFile >> "CfgMagazines" >> _x >> "ammo");
	if (_x isNotEqualTo "" and {
		(_vehicle ammoOnPylon (_forEachIndex + 1)) > 0
	} and {
		_ammo isKindOf ["BombCore", configFile >> "CfgAmmo"]
	}) then {
		private _weapon = getText (configFile >> "CfgMagazines" >> _x >> "pylonWeapon");
		private _ace = configFile >> "CfgAmmo" >> _ammo >> "ace_missileguidance";
		switch (true) do {
			case (getNumber (_ace >> "enabled") isEqualTo 1): {
				_guided = [_weapon, getText (_ace >> "defaultSeekerType"), 0];
			};
			case (getNumber (configFile >> "CfgAmmo" >> _ammo >> "laserLock") isEqualTo 0 and {
				getNumber (configFile >> "CfgAmmo" >> _ammo >> "irLock") isEqualTo 0
			}): {
				_dumb = [_weapon, "", getNumber (configFile >> "CfgAmmo" >> _ammo >> "maneuvrability")];
			};
			default {
				_laser = true;
			};
		};
	};
} forEach getPylonMagazines _vehicle;
switch (true) do {
	case (_guided isNotEqualTo []): {
		_guided
	};
	case (_dumb isNotEqualTo []): {
		_dumb
	};
	case (_laser): {
		["", "laser"]
	};
	default {
		[]
	};
}
