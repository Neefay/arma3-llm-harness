// He's stopped where he was sent, at least 3 s after being sent.
params ["_carry"];
unitReady (_carry get "MEDIC") and {
	(time - (_carry get "ORDERED")) >= 3
}
