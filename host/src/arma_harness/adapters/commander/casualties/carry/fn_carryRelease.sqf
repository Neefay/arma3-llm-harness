/*
	NAME: brmh_cmd_fnc_carryRelease
	DESCRIPTION: Lets go of him here, whatever's happened. Safe to call before he's been picked up, and twice. He's put
		down at the bearer's feet and laid out if he's still unconscious. The dummy's deleted, and the bearer gets his
		animations back and kneels, unless he's down himself.
	PARAMETERS:
		0 - Carry (HASHMAP object)
	USAGE:
		[_carry] call brmh_cmd_fnc_carryRelease;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_carry"];
private _medic = _carry get "MEDIC";
private _casualty = _carry get "SUBJECT";
private _dummy = _carry getOrDefault ["DUMMY", objNull];
if (not isNull attachedTo _casualty) then {
	detach _casualty;
	_casualty setPosATL ((getPosATL _medic) vectorAdd [sin getDir _medic, cos getDir _medic, 0]);
	["ace_common_fixCollision", _casualty] call CBA_fnc_localEvent;
};
if (alive _casualty and {
	lifeState _casualty isEqualTo "INCAPACITATED"
}) then {
	[_casualty, "UnconsciousReviveDefault"] call brmh_cmd_fnc_carryPose;
};
if (not isNull _dummy) then {
	detach _medic;
	deleteVehicle _dummy;
	_carry deleteAt "DUMMY";
};
if (alive _medic) then {
	_medic enableAI "ANIM";
	if (lifeState _medic isNotEqualTo "INCAPACITATED") then {
		[_medic, "AmovPknlMstpSrasWrflDnon"] call brmh_cmd_fnc_carryPose;
	};
};
