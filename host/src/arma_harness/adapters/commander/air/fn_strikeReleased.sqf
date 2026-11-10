// Bombs that have left the aircraft since the strike began. Counted as they're fired, which is a frame or more after
// fireAtTarget asks for them.
params ["_machine"];
((_machine get "VEHICLE") getVariable ["brmh_cmd_bombs", 0]) - (_machine get "BOMBS_BEFORE")
