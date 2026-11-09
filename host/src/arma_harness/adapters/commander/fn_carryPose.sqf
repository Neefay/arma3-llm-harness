// switchMove only changes the machine it runs on. On the server alone, the body stayed on the ground for anyone watching,
// and the server's own state said all was well.
params ["_unit", "_animation"];
[_unit, _animation] remoteExec ["switchMove", 0];
