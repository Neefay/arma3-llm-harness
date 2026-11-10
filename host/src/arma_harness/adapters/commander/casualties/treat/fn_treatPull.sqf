// The man is put beside the medic, as if he'd been dragged the last few metres.
params ["_job"];
private _medic = _job get "MEDIC";
private _man = _job get "SUBJECT";
_man setPosATL (_medic getPos [1.2, getDir _medic]);
[_man, "UnconsciousReviveDefault"] call brmh_cmd_fnc_carryPose;
