params ["_job"];
private _medic = _job get "MEDIC";
_medic setVariable ["brmh_cmd_busy", nil];
(_job get "SUBJECT") setVariable ["brmh_cmd_handled", nil];
// Down or not: a medic left with his animations off would be frozen when he wakes.
if (alive _medic) then {
	_medic enableAI "ANIM";
};
if ([_medic] call brmh_cmd_fnc_able) then {
	[_medic, "AmovPknlMstpSrasWrflDnon"] call brmh_cmd_fnc_carryPose;
	_medic doFollow leader group _medic;
};
