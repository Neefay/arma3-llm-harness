// Lets go of him here, whatever's happened. Safe to call before he's been picked up, and twice.
params ["_carry"];
private _medic = _carry get "MEDIC";
private _casualty = _carry get "SUBJECT";
private _dummy = _carry getOrDefault ["DUMMY", objNull];
if (not isNull attachedTo _casualty) then {
	detach _casualty;
	_casualty setPosATL (getPosATL _medic);
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
