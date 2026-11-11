/*
	NAME: squad_weapons
	DESCRIPTION: Swap the main weapon of everyone in someone's squad, with magazines for it. Pairs:
		arifle_AKM_F with 30Rnd_762x39_Mag_F; LMG_Zafir_F with 150Rnd_762x54_Box; arifle_MX_F with
		30Rnd_65x39_caseless_mag; srifle_LRR_F with 7Rnd_408_Mag. Find others with find_class.
	PARAMETERS:
		0 - weapon (STRING): the weapon's class
		1 - magazine (STRING): its magazine's class
		2 - magazines (NUMBER, default 6): how many each
		3 - who (OBJECT, default "player"): anyone in the squad
	RETURNS: [[name, weapon] for each man] (ARRAY)
	TARGET: server
	TAGS: weapons, rifle, guns, loadout, squad, arm, magazines
	EXAMPLE: {"weapon": "arifle_MX_F", "magazine": "30Rnd_65x39_caseless_mag"}
*/
params ["_weapon", "_magazine", "_magazines", "_who"];
if (not isClass (configFile >> "CfgWeapons" >> _weapon)) exitWith {
	format ["ERROR: there's no weapon class %1: find one with find_class", _weapon]
};
if (not isClass (configFile >> "CfgMagazines" >> _magazine)) exitWith {
	format ["ERROR: there's no magazine class %1", _magazine]
};
if (isNull _who) exitWith {
	"ERROR: no such unit"
};
(units group _who) apply {
	private _man = _x;
	private _old = primaryWeapon _man;
	if (_old isNotEqualTo "") then {
		{
			_man removeMagazines _x;
		} forEach (getArray (configFile >> "CfgWeapons" >> _old >> "magazines"));
		_man removeWeapon _old;
	};
	// Magazines first, so the weapon comes loaded.
	for "_i" from 1 to _magazines do {
		_man addMagazine _magazine;
	};
	_man addWeapon _weapon;
	_man selectWeapon _weapon;
	[name _man, primaryWeapon _man]
}
