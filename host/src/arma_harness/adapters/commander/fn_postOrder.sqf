/*
	NAME: brmh_cmd_fnc_postOrder
	DESCRIPTION: A medic goes to a place and sets up an aid post, a real tent that can be destroyed. One per station.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Order id (STRING)
		2 - Position (ARRAY)
	ENVIRONMENT: Server
*/
params [["_group", grpNull, [grpNull]], ["_order", "", [""]], ["_at", [], [[]], [2, 3]]];
if (alive (_group getVariable ["brmh_cmd_post", objNull]) or {
	(brmh_cmd_builds findIf {
		(_x get "GROUP") isEqualTo _group and {
			((_x get "SPEC") get "KIND") isEqualTo "post"
		}
	}) >= 0
}) exitWith {
	[_group, _order, "post", "post", "have one"] call brmh_cmd_fnc_careSay;
};
private _medics = (units _group) select {
	[_x] call brmh_cmd_fnc_able and {
		[_x] call brmh_cmd_fnc_isMedic
	} and {
		not (_x getVariable ["brmh_cmd_busy", false])
	}
};
if (_medics isEqualTo []) exitWith {
	[_group, _order, "post", "post", "no medic"] call brmh_cmd_fnc_careSay;
};
private _medic = _medics # 0;
_medic setVariable ["brmh_cmd_busy", true];
_medic enableAI "PATH";
if (vehicle _medic isNotEqualTo _medic) then {
	[_medic] call brmh_cmd_fnc_getOff;
};
_medic doMove _at;
brmh_cmd_builds pushBack ([brmh_cmd_postMachine, [["GROUP", _group], ["ORDER", _order], ["SUBJECT", "post"], ["MEDIC", _medic], ["AT", _at], ["ORDERED", time]]] call brmh_cmd_fnc_newMachine);
[_group, _order, "post", "post", "going"] call brmh_cmd_fnc_careSay;
