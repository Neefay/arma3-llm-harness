// Those still on their way to a seat stop, and the record says how it ended. Anyone already in his seat stays there.
params ["_machine", "_word", "_names"];
{
	unassignVehicle (_x # 0);
	[_x # 0] orderGetIn false;
} forEach ([_machine] call brmh_cmd_fnc_boardWaiting);
(_machine get "GROUP") setVariable ["brmh_cmd_mount", [_machine get "KEY", _word, _machine get "SEAT", _names, _machine get "SPARE"]];
