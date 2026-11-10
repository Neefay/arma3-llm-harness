/*
	NAME: brmh_cmd_fnc_bombWeapon
	DESCRIPTION: The weapon that drops the aircraft's bombs on a grid, and how they're guided. ACE's guided bombs go
		first, then dumb bombs, which fall where they're released. The engine's own laser bombs can't be used: with
		nothing locked they glide on for kilometres (spike_bomb_drag.py), so an aircraft with only those is told apart,
		for the pilot to say so. Only pylons with rounds left count.
	PARAMETERS:
		0 - Aircraft (OBJECT)
	USAGE:
		private _bomb = [_vehicle] call brmh_cmd_fnc_bombWeapon;
	RETURNS: (ARRAY) one of
		[weapon, seeker, 0]         - an ACE guided bomb, with ACE's seeker type for it: "SALH" (laser) or "GPS"
		[weapon, "", side friction] - a dumb bomb, with its ammo's maneuvrability for brmh_cmd_fnc_bombImpact
		["", "laser"]               - only the engine's own laser bombs
		[]                          - no bombs left
	ENVIRONMENT: Server, unscheduled
*/
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
			// ACE guides an AI's bomb only at its missile guidance setting 2, its default. Below that, its bombs are
			// laser bombs like the engine's own.
			case (getNumber (_ace >> "enabled") isEqualTo 1 and {
				(missionNamespace getVariable ["ace_missileguidance_enabled", 0]) >= 2
			}): {
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
