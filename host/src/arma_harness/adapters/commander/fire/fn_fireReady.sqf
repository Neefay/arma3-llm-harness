// The gun has had its last order for at least a second, and has nothing left of it to do.
params ["_machine"];
unitReady (_machine get "GUN") and {
	(time - ((_machine get "MISSION") get "issued")) >= 1
}
