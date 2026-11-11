/*
	NAME: heal
	DESCRIPTION: Heal someone fully, or their whole squad, and refill their fatigue. With ACE, it uses ACE's full
		heal, which also wakes the unconscious and stops bleeding.
	PARAMETERS:
		0 - who (OBJECT, default "player"): who
		1 - squad (BOOL, default true): their whole squad too
	RETURNS: how many were healed (NUMBER)
	TARGET: server
	TAGS: heal, medic, health, revive, wounds, damage, squad
	EXAMPLE: {}
*/
params ["_who", "_squad"];
if (isNull _who) exitWith {
	"ERROR: no such unit"
};
private _ace = not isNil "ace_medical_treatment_fnc_fullHealLocal";
private _patients = ([[_who], units group _who] select _squad) select {
	alive _x
};
{
	if (_ace) then {
		// ACE's heal must run where the patient is local.
		[_x] remoteExecCall ["ace_medical_treatment_fnc_fullHealLocal", _x];
	} else {
		_x setDamage 0;
	};
	_x setFatigue 0;
} forEach _patients;
count _patients
