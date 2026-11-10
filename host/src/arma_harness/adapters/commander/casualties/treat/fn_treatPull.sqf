// The man is put beside the medic, as if he'd been dragged the last few metres.
params ["_job"];
private _medic = _job get "MEDIC";
private _man = _job get "SUBJECT";
_man setPosATL ((getPosATL _medic) vectorAdd ([sin getDir _medic, cos getDir _medic, 0] vectorMultiply 1.2));
[_man, "UnconsciousReviveDefault"] call brmh_cmd_fnc_carryPose;
