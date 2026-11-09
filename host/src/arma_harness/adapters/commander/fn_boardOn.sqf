// Those boarding who are in the vehicle, and those still on their way.
params ["_machine"];
((_machine get "LIST") apply {
	_x # 0
}) select {
	alive _x and {
		vehicle _x isEqualTo (_machine get "VEHICLE")
	}
}
