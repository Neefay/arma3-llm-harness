/*
	NAME: brmh_cmd_fnc_startCarry
	DESCRIPTION: Sends a bearer to pick up a downed man and carry him somewhere. An AI can't walk in ACE's carrying
		state, so a hidden dummy does the walking, with the bearer attached to it. The idea is Antistasi's, for a drag.
		If the dummy stops getting anywhere and the place isn't far, the bearer stays where he is, works on the man for
		a while, and the man is then put there directly, so a bad spot can't leave a bearer stuck.
	PARAMETERS:
		0 - Bearer (OBJECT)
		1 - Casualty (OBJECT)
		2 - Where to: a position, or a vehicle to load him into (ARRAY or OBJECT)
		3 - (OPTIONAL) Group whose radio reports it; with none, nothing is said (GROUP) - Default: grpNull
		4 - (OPTIONAL) Order id (STRING) - Default: ""
	USAGE:
		[_bearer, _man, [3410, 2980, 0], _group, "O-0007"] call brmh_cmd_fnc_startCarry;
	RETURNS: The carry, a brmh_cmd_carryMachine (HASHMAP object). Its "STATE" is "" once it's ended
	ENVIRONMENT: Server, unscheduled
*/
params [["_medic", objNull, [objNull]], ["_casualty", objNull, [objNull]], ["_to", [], [[], objNull]], ["_group", grpNull, [grpNull]], ["_order", "", [""]]];
{
	_x forceSpeed -1;
} forEach [_medic, _casualty];
_medic setVariable ["brmh_cmd_busy", true];
// DEFEND turns off a soldier's pathing when he reaches his post, and a job has to be able to walk.
_medic enableAI "PATH";
_casualty setVariable ["brmh_cmd_handled", "carried"];
private _carry = [brmh_cmd_carryMachine, [["GROUP", _group], ["ORDER", _order], ["SUBJECT", _casualty], ["MEDIC", _medic], ["TO", _to], ["TRIES", 0], ["ORDERED", time], ["MOVED", time], ["LAST", getPosATL _medic], ["HOW", ""]]] call brmh_cmd_fnc_newMachine;
[_carry] call brmh_cmd_fnc_carryApproach;
brmh_cmd_carries pushBack _carry;
if (isNil "brmh_cmd_carryPfh") then {
	brmh_cmd_carryPfh = [{
		call brmh_cmd_fnc_stepCarries
	}, 0.5] call CBA_fnc_addPerFrameHandler;
};
_carry
