/*
	NAME: brmh_cmd_fnc_aceBombs
	DESCRIPTION: With ACE loaded, an aircraft's bombs are swapped for ACE's guided versions of the same bombs, pylon by
		pylon, so a strike can be guided onto a bare grid. ACE's version is the "ace_missile..." magazine the pylon
		takes whose parent class is the bomb it carries. Anything ACE has no version of stays as it is, and without ACE
		nothing changes.
	PARAMETERS:
		0 - Aircraft, local to this machine (OBJECT)
	USAGE:
		[_vehicle] call brmh_cmd_fnc_aceBombs;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled. Called by brmh_cmd_fnc_spawnVehicle once the aircraft has its pylons.
*/
params ["_vehicle"];
if (not isClass (configFile >> "CfgPatches" >> "ace_missileguidance")) exitWith {};
{
	private _magazine = _x;
	private _pylon = _forEachIndex + 1;
	if (_magazine isNotEqualTo "" and {
		(getText (configFile >> "CfgMagazines" >> _magazine >> "ammo")) isKindOf ["BombCore", configFile >> "CfgAmmo"]
	}) then {
		private _guided = (_vehicle getCompatiblePylonMagazines _pylon) select {
			"ace_missile" in toLowerANSI _x and {
				toLowerANSI configName inheritsFrom (configFile >> "CfgMagazines" >> _x) isEqualTo toLowerANSI _magazine
			}
		};
		if (_guided isNotEqualTo []) then {
			[_vehicle, _pylon, _guided # 0] call brmh_cmd_fnc_setPylon;
		};
	};
} forEach getPylonMagazines _vehicle;
