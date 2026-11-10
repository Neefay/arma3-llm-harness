// switchMove only changes the machine it runs on. On the server alone, the body stayed on the ground for anyone watching,
// and the server's own state said all was well. @brmh's BRMH_fnc_commanderEvents plays it on every machine.
params ["_unit", "_animation"];
["brmh_cmd_pose", [_unit, _animation]] call CBA_fnc_globalEvent;
