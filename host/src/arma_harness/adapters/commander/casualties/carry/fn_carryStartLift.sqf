/*
	NAME: brmh_cmd_fnc_carryStartLift
	DESCRIPTION: The bearer stops and starts ACE's lift: his animation and the man's. ACE selects the rifle first
		too, as the carry animations don't play without it.
	PARAMETERS:
		0 - The carry's machine (HASHMAP object)
	USAGE:
		[_carry] call brmh_cmd_fnc_carryStartLift;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_carry"];
private _medic = _carry get "MEDIC";
doStop _medic;
_medic selectWeapon primaryWeapon _medic;
_medic playMoveNow "AcinPknlMstpSnonWnonDnon_AcinPercMrunSnonWnonDnon";
[_carry get "SUBJECT", "AinjPfalMstpSnonWrflDnon_carried_Up"] call brmh_cmd_fnc_carryPose;
