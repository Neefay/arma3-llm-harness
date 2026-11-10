/*
	NAME: brmh_cmd_fnc_winchester
	DESCRIPTION: Whether an aircraft has nothing left to drop or shoot. Flares and the designator's batteries aren't
		weapons.
	PARAMETERS:
		0 - Aircraft (OBJECT)
	USAGE:
		[_vehicle] call brmh_cmd_fnc_winchester
	RETURNS: Boolean
	ENVIRONMENT: Server, unscheduled
*/
params ["_vehicle"];
((magazinesAllTurrets _vehicle) findIf {
	(_x # 2) > 0 and {
		not ("cmflare" in toLowerANSI (_x # 0))
	} and {
		toLowerANSI (_x # 0) isNotEqualTo "laserbatteries"
	}
}) < 0
