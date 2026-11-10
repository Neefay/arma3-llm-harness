/*
	NAME: brmh_cmd_fnc_carryRedirect
	DESCRIPTION: A new place, and the new order that gave it, for a man already on the way or on someone's shoulder. A
		walking dummy is sent there at once; a bearer still going to him learns it when he lifts him.
	PARAMETERS:
		0 - Carry (HASHMAP object)
		1 - Where to: a position, or a vehicle (ARRAY or OBJECT)
		2 - Order id (STRING)
	USAGE:
		[_held # 0, _place, _order] call brmh_cmd_fnc_carryRedirect;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_carry", "_place", "_order"];
_carry set ["TO", _place];
_carry set ["ORDER", _order];
_carry set ["MOVED", time];
private _dummy = _carry getOrDefault ["DUMMY", objNull];
if (not isNull _dummy) then {
	_dummy doMove ([_carry] call brmh_cmd_fnc_carryPlace);
};
