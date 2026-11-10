/*
	NAME: brmh_cmd_fnc_getOff
	DESCRIPTION: Gets a man out of whatever he's in, and keeps him out: unassigned, and no longer ordered in. His
		targeting goes back on, in case he was a gun's crew (brmh_cmd_fnc_onSeat). A man on foot is only unassigned.
	PARAMETERS:
		0 - Soldier (OBJECT)
	USAGE:
		[_medic] call brmh_cmd_fnc_getOff;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_man"];
private _vehicle = vehicle _man;
if (_vehicle isNotEqualTo _man) then {
	_man action ["GetOut", _vehicle];
};
unassignVehicle _man;
[_man] orderGetIn false;
_man enableAI "TARGET";
