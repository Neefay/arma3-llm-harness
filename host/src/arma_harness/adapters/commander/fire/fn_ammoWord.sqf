/*
	NAME: brmh_cmd_fnc_ammoWord
	DESCRIPTION: What the commander calls a magazine, read from its class name: smoke first, then shells. Anything
		else a gun carries, such as mines or flares, isn't offered yet.
	PARAMETERS:
		0 - Magazine class (STRING)
	USAGE:
		[_magazine] call brmh_cmd_fnc_ammoWord; // "8Rnd_82mm_Mo_shells" gives "HE"
	RETURNS: "HE", "SMOKE", or "" for anything else (STRING)
	ENVIRONMENT: Server, unscheduled
*/
params ["_magazine"];
private _name = toLowerANSI _magazine;
private _simulation = toLowerANSI getText (configFile >> "CfgAmmo" >> getText (configFile >> "CfgMagazines" >> _magazine >> "ammo") >> "simulation");
if ("smoke" in _name or {
	"smoke" in _simulation
}) exitWith {
	"SMOKE"
};
// The engine's are "...shells"; ACE's and RHS's say HE ("ACE_1Rnd_82mm_Mo_HE", "rhs_12Rnd_m821_HE").
if ("shells" in _name or {
	(_name select [count _name - 3]) isEqualTo "_he"
} or {
	"_he_" in _name
}) exitWith {
	"HE"
};
""
