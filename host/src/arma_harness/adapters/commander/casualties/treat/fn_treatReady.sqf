// He's stopped where he was sent, at least 3 s after being sent.
params ["_job"];
unitReady (_job get "MEDIC") and {
	(time - (_job get "ORDERED")) >= 3
}
