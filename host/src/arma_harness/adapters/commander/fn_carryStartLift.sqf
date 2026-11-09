params ["_carry"];
private _medic = _carry get "MEDIC";
doStop _medic;
_medic selectWeapon primaryWeapon _medic;
_medic playMoveNow "AcinPknlMstpSnonWnonDnon_AcinPercMrunSnonWnonDnon";
[_carry get "SUBJECT", "AinjPfalMstpSnonWrflDnon_carried_Up"] call brmh_cmd_fnc_carryPose;
