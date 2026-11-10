/*
	NAME: brmh_cmd_fnc_clearAll
	DESCRIPTION: Ends a battle on a running game, so the next can start clean: every machine called off, and whatever
		the harness made deleted (stations, enemies, its vehicles, the dead and the observers' markers). A vehicle the
		mission placed itself stays. A repeat start reuses the running game, so the old groups are renamed "Retired",
		which keeps them out of the new battle's records. Operator action, never reachable by the commander.
	PARAMETERS: None
	USAGE:
		call brmh_cmd_fnc_clearAll;
	RETURNS: true
	ENVIRONMENT: Server, unscheduled
*/
{
	_x call ["#END", ["called off"]];
} forEach brmh_cmd_carries;
{
	_x call ["#END", ["called off"]];
} forEach (brmh_cmd_builds + brmh_cmd_fireActive);
// A garrison's reachability probe, if one is still walking.
if (not isNil "brmh_cmd_probePfh") then {
	[brmh_cmd_probePfh] call CBA_fnc_removePerFrameHandler;
	brmh_cmd_probePfh = nil;
};
{
	deleteVehicle (_x get "MAN");
} forEach (missionNamespace getVariable ["brmh_cmd_probeWalkers", []]);
brmh_cmd_probeWalkers = [];
// Only what the harness made. A vehicle a squad merely saw is the mission's own, and stays for the next battle.
{
	if (_y getVariable ["brmh_cmd_spawned", false]) then {
		deleteVehicle _y;
	} else {
		_y setVariable ["brmh_cmd_key", nil];
	};
} forEach brmh_cmd_vehicles;
brmh_cmd_vehicles = createHashMap;
brmh_cmd_buildings = createHashMap;
brmh_cmd_fireActive = [];
brmh_cmd_carries = [];
brmh_cmd_treats = [];
brmh_cmd_builds = [];
brmh_cmd_posts = [];
brmh_cmd_down = [];
brmh_cmd_men = createHashMap;
{
	[_x] call brmh_cmd_fnc_deleteStation;
	_y setGroupIdGlobal ["Retired"];
	// Created to outlive their men, so they'd pile up battle after battle towards the engine's cap on groups.
	_y deleteGroupWhenEmpty true;
} forEach brmh_cmd_stations;
brmh_cmd_stations = createHashMap;
{
	private _group = _x;
	{
		deleteVehicle _x;
	} forEach units _group;
	_group setGroupIdGlobal ["Retired"];
	_group deleteGroupWhenEmpty true;
} forEach brmh_cmd_enemies;
brmh_cmd_enemies = [];
{
	deleteVehicle _x;
} forEach allDead;
{
	if ((_x find "brmh_cmd_") isEqualTo 0) then {
		deleteMarker _x;
	};
} forEach allMapMarkers;
true
