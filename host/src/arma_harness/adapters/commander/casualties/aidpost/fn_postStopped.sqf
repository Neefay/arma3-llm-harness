// The medic has stopped, short of the place or at it.
params ["_machine"];
unitReady (_machine get "MEDIC") and {
	(time - (_machine get "ORDERED")) >= 3
}
