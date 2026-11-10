/*
	NAME: brmh_cmd_fnc_treatWork
	DESCRIPTION: While he works: the man stops getting worse once they've got to work on him, the same as ACE's own
		treatments without the items, and the medic keeps at it. After half the time, 5 s at most, his wounds stop
		bleeding, his blood is brought up to 4.5 l, and a heart that's stopped is started again.
	PARAMETERS:
		0 - Treat job (HASHMAP object)
	USAGE:
		[_job] call brmh_cmd_fnc_treatWork;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled. The man has to be local: ACE keeps his medical state where he is
*/
params ["_job"];
private _man = _job get "SUBJECT";
if (not (_job get "STABLE") and {
	(time - (_job get "SINCE")) >= (5 min ((_job get "NEED") / 2))
}) then {
	_job set ["STABLE", true];
	_man setVariable ["ace_medical_openWounds", createHashMap, true];
	if (isNil "ace_medical_status_fnc_updateWoundBloodLoss") then {
		_man setVariable ["ace_medical_woundBleeding", 0, true];
	} else {
		[_man] call ace_medical_status_fnc_updateWoundBloodLoss;
	};
	_man setVariable ["ace_medical_bloodVolume", (_man getVariable ["ace_medical_bloodVolume", 6]) max 4.5, true];
	if (_man getVariable ["ace_medical_inCardiacArrest", false]) then {
		// As ACE's own CPR does: with too little oxygen, his heart rate puts him straight back into arrest.
		_man setVariable ["ace_medical_spo2", (_man getVariable ["ace_medical_spo2", 97]) max 48.5, true];
		["ace_medical_CPRSucceeded", _man] call CBA_fnc_localEvent;
	};
};
if ((time - (_job get "ANIM")) >= 8) then {
	_job set ["ANIM", time];
	[_job get "MEDIC", "AinvPknlMstpSlayWrflDnon_medicOther"] call brmh_cmd_fnc_carryPose;
};
