/*
	NAME: brmh_cmd_fnc_carryLift
	DESCRIPTION: He's on the bearer's shoulder, and they set off. A hidden civilian dummy that can't be hurt or shot at
		walks to the place, with the bearer attached to it and his own animations off, and the man attached to him where
		ACE puts a carried man. brmh_cmd_fnc_carryRelease deletes the dummy.
	PARAMETERS:
		0 - Carry (HASHMAP object)
	USAGE:
		[_carry] call brmh_cmd_fnc_carryLift;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled. The bearer and the man have to be local
*/
params ["_carry"];
private _medic = _carry get "MEDIC";
private _casualty = _carry get "SUBJECT";
private _group = createGroup [civilian, true];
private _dummy = _group createUnit ["C_man_polo_1_F", [0, 0, 20], [], 0, "FORM"];
_dummy forceWalk true;
hideObjectGlobal _dummy;
_dummy allowDamage false;
_dummy setCaptive true;
_dummy setBehaviour "CARELESS";
{
	_dummy disableAI _x;
} forEach ["FSM", "SUPPRESSION", "AUTOTARGET", "TARGET"];
_dummy setPosATL (getPosATL _medic);
_dummy setDir (_medic getDir ([_carry] call brmh_cmd_fnc_carryPlace));
_medic disableAI "ANIM";
_medic attachTo [_dummy, [0, 0, 0]];
_medic setDir 0;
_casualty attachTo [_medic, [0.4, -0.1, -1.25], "LeftShoulder"];
_casualty setDir 195;
[_casualty, "AinjPfalMstpSnonWnonDf_carried_dead"] call brmh_cmd_fnc_carryPose;
_dummy doMove ([_carry] call brmh_cmd_fnc_carryPlace);
_medic playMove "AcinPercMrunSnonWnonDf";
_carry set ["DUMMY", _dummy];
_carry set ["MOVED", time];
_carry set ["LAST", getPosATL _dummy];
