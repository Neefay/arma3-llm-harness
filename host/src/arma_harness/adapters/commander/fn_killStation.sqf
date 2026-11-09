params [["_callsign", "", [""]]];
private _group = brmh_cmd_stations getOrDefault [_callsign, grpNull];
{
	_x setDamage 1;
} forEach units _group;
true
