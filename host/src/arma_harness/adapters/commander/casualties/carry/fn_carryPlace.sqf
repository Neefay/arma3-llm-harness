/*
	NAME: brmh_cmd_fnc_carryPlace
	DESCRIPTION: Where a carry is going: its place, or where its vehicle is now, since a vehicle can move.
	PARAMETERS:
		0 - The carry's machine (HASHMAP object)
	USAGE:
		_dummy doMove ([_carry] call brmh_cmd_fnc_carryPlace);
	RETURNS: Position, ATL (ARRAY)
	ENVIRONMENT: Server, unscheduled
*/
params ["_carry"];
private _to = _carry get "TO";
if (_to isEqualType objNull) then {
	getPosATL _to
} else {
	_to
}
