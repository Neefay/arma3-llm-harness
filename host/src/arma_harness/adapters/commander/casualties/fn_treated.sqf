// If he's nobody left to go back to, he stays with whoever saved him.
params ["_man", "_rescuers"];
private _home = group _man;
if (_home isEqualTo _rescuers) exitWith {};
if ((((units _home) - [_man]) findIf {
	[_x] call brmh_cmd_fnc_able
}) < 0) then {
	[_man] joinSilent _rescuers;
	_rescuers setVariable ["brmh_cmd_baseline", (_rescuers getVariable ["brmh_cmd_baseline", 0]) + 1];
	[_rescuers, "", "joined", _man, "joined"] call brmh_cmd_fnc_careSay;
};
