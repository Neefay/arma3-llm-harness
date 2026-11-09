// Everyone stops where he is, facing the cordon's centre if it has one.
params ["_machine"];
private _soldiers = [_machine get "GROUP"] call brmh_cmd_fnc_freeMen;
doStop _soldiers;
if ((_machine get "WATCH") isNotEqualTo []) then {
	_soldiers doWatch (_machine get "WATCH");
};
