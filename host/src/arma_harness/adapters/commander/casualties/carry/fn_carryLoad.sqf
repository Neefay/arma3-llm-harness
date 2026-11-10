// At the vehicle: he's let go of and put aboard, carried there or placed beside it.
params ["_carry", "_how"];
[_carry] call brmh_cmd_fnc_carryRelease;
[_carry get "SUBJECT", _carry get "TO"] call brmh_cmd_fnc_loadMan;
_carry set ["HOW", _how];
