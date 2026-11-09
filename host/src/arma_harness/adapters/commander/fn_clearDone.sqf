// Out of a building: checked if every position was stood on, and blocked, with how many, if not.
params ["_machine"];
if ((_machine get "REACHED") >= (_machine get "OF")) then {
	(_machine get "CLEARED") pushBack (_machine get "CURRENT");
} else {
	(_machine get "BLOCKED") pushBack [_machine get "CURRENT", _machine get "REACHED", _machine get "OF"];
};
_machine set ["CURRENT", ""];
