/*
	NAME: brmh_cmd_fnc_probePositions
	DESCRIPTION: Finds the building positions AI can really get to, by sending a soldier to each. The engine's own path
		planner says every one is reachable, and on Stratis soldiers stopped 3 m outside cargo houses it had planned
		paths into. A garrison placed where nobody can reach can't be cleared, so garrisons only go where these got,
		and only in buildings where they got to two positions or more. The walkers are hidden, captive and can't be
		hurt, and are deleted when done. Operator action, before anyone else is placed.
	PARAMETERS:
		0 - Centre [x, y] (ARRAY)
		1 - Radius, metres (NUMBER)
	USAGE:
		[[3250, 2950], 120] call brmh_cmd_fnc_probePositions;
		brmh_cmd_probe params ["_done", "_reachable"];
	RETURNS: Nothing. brmh_cmd_probe becomes [true, positions reached] when every walker has finished
	ENVIRONMENT: Server, unscheduled. The walk goes on in a per-frame handler, once a second (brmh_cmd_fnc_stepProbe)
*/
params [["_centre", [], [[]], 2], ["_radius", 100, [0]]];
brmh_cmd_probe = [false, []];
// A probe before this one, finished or not, leaves its hidden walkers in the world.
{
	deleteVehicle (_x get "MAN");
} forEach (missionNamespace getVariable ["brmh_cmd_probeWalkers", []]);
brmh_cmd_probeWalkers = [];
{
	private _house = _x;
	private _outside = _house getPos [((boundingBoxReal _house) # 2) + 4, random 360];
	{
		private _group = createGroup [civilian, true];
		private _man = _group createUnit ["C_man_1", _outside, [], 4, "NONE"];
		_man setCaptive true;
		_man allowDamage false;
		hideObjectGlobal _man;
		// Those for one building set off a few seconds apart, so they don't jam its doorway.
		brmh_cmd_probeWalkers pushBack (createHashMapFromArray [["MAN", _man], ["HOUSE", _house], ["SPOT", _x], ["START", time + 4 * _forEachIndex], ["BEST", 1e9], ["GAIN", time + 4 * _forEachIndex]]);
	} forEach ([_house] call brmh_cmd_fnc_safePositions);
} forEach (nearestObjects [_centre + [0], ["House"], _radius] select {
	(_x buildingPos -1) isNotEqualTo []
});
if (not isNil "brmh_cmd_probePfh") then {
	[brmh_cmd_probePfh] call CBA_fnc_removePerFrameHandler;
};
brmh_cmd_probePfh = [{
	call brmh_cmd_fnc_stepProbe
}, 1] call CBA_fnc_addPerFrameHandler;
