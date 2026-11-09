// How far the dummy still has to walk.
params ["_carry"];
(_carry get "DUMMY") distance2D ([_carry] call brmh_cmd_fnc_carryPlace)
