// Seconds since the gun last fired, or was last ordered to.
params ["_machine"];
private _mission = _machine get "MISSION";
time - ((_mission getOrDefault ["lastShot", -1]) max (_mission get "issued"))
