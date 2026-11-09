params [["_callsign", "", [""]]];
private _group = brmh_cmd_stations getOrDefault [_callsign, grpNull];
{
	deleteVehicle _x;
} forEach units _group;
true
