/*
	NAME: brmh_cmd_fnc_treatStart
	DESCRIPTION: To work: the medic stops, faces the man and kneels over him. How long it takes depends on where the
		man is (brmh_cmd_careTimes).
	PARAMETERS:
		0 - Treat job (HASHMAP object)
	USAGE:
		[_job] call brmh_cmd_fnc_treatStart;
	RETURNS: Where, for the radio: "field" or "facility" (STRING)
	ENVIRONMENT: Server, unscheduled
*/
params ["_job"];
private _medic = _job get "MEDIC";
private _man = _job get "SUBJECT";
private _fast = [_man] call brmh_cmd_fnc_atFacility;
doStop _medic;
_medic setDir (_medic getDir _man);
_medic disableAI "ANIM";
[_medic, "AinvPknlMstpSlayWrflDnon_medicOther"] call brmh_cmd_fnc_carryPose;
_job set ["NEED", brmh_cmd_careTimes get (["field_s", "facility_s"] select _fast)];
_job set ["STABLE", false];
_job set ["ANIM", time];
["field", "facility"] select _fast
