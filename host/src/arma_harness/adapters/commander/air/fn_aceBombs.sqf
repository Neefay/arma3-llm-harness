// With ACE loaded, an aircraft's bombs are swapped for ACE's guided versions of the same bombs, pylon by pylon, so a
// strike can be guided onto a bare grid. Anything ACE has no version of stays as it is.
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
				(configName inheritsFrom (configFile >> "CfgMagazines" >> _x)) isEqualTo _magazine
			}
		};
		if (_guided isNotEqualTo []) then {
			_vehicle setPylonLoadout [_pylon, _guided # 0, true];
		};
	};
} forEach getPylonMagazines _vehicle;
