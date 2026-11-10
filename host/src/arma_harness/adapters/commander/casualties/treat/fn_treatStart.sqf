// To work: how long it takes depends on where he is (brmh_cmd_careTimes). Returns where, for the radio.
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
