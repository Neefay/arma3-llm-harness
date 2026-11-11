/*
	NAME: squad_nvg
	DESCRIPTION: Give night vision goggles to everyone in someone's squad who has none.
	PARAMETERS:
		0 - who (OBJECT, default "player"): anyone in the squad
		1 - goggles (STRING, default "NVGoggles"): the goggles' class (NVGoggles_OPFOR, NVGoggles_INDEP...)
	RETURNS: how many got goggles (NUMBER)
	TARGET: server
	TAGS: night vision, nvg, goggles, night, squad, equipment
	EXAMPLE: {}
*/
params ["_who", "_goggles"];
if (isNull _who) exitWith {
	"ERROR: no such unit"
};
if (not isClass (configFile >> "CfgWeapons" >> _goggles)) exitWith {
	format ["ERROR: there's no class %1", _goggles]
};
private _given = 0;
{
	if (hmd _x isEqualTo "") then {
		_x linkItem _goggles;
		_given = _given + 1;
	};
} forEach units group _who;
_given
