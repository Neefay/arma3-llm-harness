// While he works: the man stops getting worse once they've got to work on him, the same as ACE's own treatments
// without the items, and the medic keeps at it.
params ["_job"];
private _man = _job get "SUBJECT";
if (not (_job get "STABLE") and {
	(time - (_job get "SINCE")) >= (5 min ((_job get "NEED") / 2))
}) then {
	_job set ["STABLE", true];
	_man setVariable ["ace_medical_openWounds", createHashMap, true];
	_man setVariable ["ace_medical_woundBleeding", 0, true];
	_man setVariable ["ace_medical_bloodVolume", (_man getVariable ["ace_medical_bloodVolume", 6]) max 4.5, true];
	if (_man getVariable ["ace_medical_inCardiacArrest", false]) then {
		["ace_medical_CPRSucceeded", _man] call CBA_fnc_localEvent;
	};
};
if ((time - (_job get "ANIM")) >= 8) then {
	_job set ["ANIM", time];
	[_job get "MEDIC", "AinvPknlMstpSlayWrflDnon_medicOther"] call brmh_cmd_fnc_carryPose;
};
