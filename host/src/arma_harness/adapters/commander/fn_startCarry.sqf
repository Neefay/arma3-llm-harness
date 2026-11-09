/*
	NAME: brmh_cmd_fnc_startCarry
	DESCRIPTION: Sends a medic to pick up a downed man and carry him somewhere. An AI can't walk in ACE's carrying state, so
		a hidden dummy does the walking, with the medic attached to it. The idea is Antistasi's, for a drag. If the dummy
		stops getting anywhere and the place isn't far, the medic stays where he is, works on the man for a while, and the
		man is then put there directly, so a bad spot can't leave a medic stuck.
	PARAMETERS:
		0 - Medic (OBJECT)
		1 - Casualty (OBJECT)
		2 - Where to: a position, or a vehicle to load him into (ARRAY or OBJECT)
	RETURNS: The carry (HASHMAP). "state" ends as "done", and "result" says how
	ENVIRONMENT: Server
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
