/*
	Commander mode, game side (runs on the server, comments are stripped by the host). Safe to re-run.
	This code reads engine state and applies orders. Deciding what is worth reporting, and how to say it,
	is left to the host (commander/reports.py), so that part can be tested without the game.

	Emits "evt" with type:
		cmd_tick   every 2 s, the mission clock.
		cmd_report every 2 s per enrolled group with a living member, the group's perception packet.
		           A wiped-out group sends nothing, which is the point.
		cmd_truth  every 5 s, real positions, for the after-action review. Never reaches the commander.
*/
if (not isNil "brmh_cmd_pfh") then {
	[brmh_cmd_pfh] call CBA_fnc_removePerFrameHandler;
};
if (isNil "brmh_cmd_stations") then {
	brmh_cmd_stations = createHashMap;
};
if (isNil "brmh_cmd_enemies") then {
	brmh_cmd_enemies = [];
};
brmh_cmd_nextTruth = 0;

brmh_cmd_fnc_rounds = {
	params ["_unit"];
	private _compatible = (compatibleMagazines primaryWeapon _unit) apply {
		toLowerANSI _x
	};
	private _rounds = 0;
	// magazinesAmmo leaves out the loaded magazine; magazinesAmmoFull includes it.
	{
		if (toLowerANSI (_x # 0) in _compatible) then {
			_rounds = _rounds + (_x # 1);
		};
	} forEach magazinesAmmoFull _unit;
	_rounds
};

brmh_cmd_fnc_kind = {
	params ["_type"];
	if (_type isKindOf "CAManBase") exitWith {
		"infantry"
	};
	if (_type isKindOf "Tank") exitWith {
		"armour"
	};
	if (_type isKindOf "Air") exitWith {
		"aircraft"
	};
	if (_type isKindOf "LandVehicle" or {
		_type isKindOf "Ship"
	}) exitWith {
		"vehicle"
	};
	"unknown"
};

brmh_cmd_fnc_contacts = {
	params ["_leader"];
	private _near = _leader nearTargets 2000;
	(_leader targets [true, 2000]) apply {
		private _object = _x;
		private _knowledge = _leader targetKnowledge _object;
		private _entry = _near findIf {
			(_x # 4) isEqualTo _object
		};
		private _type = if (_entry < 0) then {
			""
		} else {
			(_near # _entry) # 1
		};
		// Position and type here are what the group believes. The true object must not leave this function.
		createHashMapFromArray [
			["pos", [(_knowledge # 6) # 0, (_knowledge # 6) # 1]],
			["kind", [_type] call brmh_cmd_fnc_kind],
			["age_s", (time - (_knowledge # 2)) max 0],
			["accuracy_m", if (_entry < 0) then {
				-1
			} else {
				(_near # _entry) # 5
			}]
		]
	}
};

brmh_cmd_fnc_packet = {
	params ["_callsign", "_group"];
	private _alive = (units _group) select {
		alive _x
	};
	if (_alive isEqualTo []) exitWith {
		nil
	};
	// For several seconds after a leader dies, leader still returns the body.
	private _leader = if (alive leader _group) then {
		leader _group
	} else {
		_alive # 0
	};
	private _rounds = 0;
	{
		_rounds = _rounds + ([_x] call brmh_cmd_fnc_rounds);
	} forEach _alive;
	private _position = getPosATL _leader;
	createHashMapFromArray [
		["type", "cmd_report"],
		["callsign", _callsign],
		["pos", [_position # 0, _position # 1]],
		["grid", mapGridPosition _position],
		["dir", getDir _leader],
		["speed", speed _leader],
		["alive", count _alive],
		["wounded", {
			lifeState _x isEqualTo "INJURED"
		} count _alive],
		["baseline", _group getVariable ["brmh_cmd_baseline", count _alive]],
		["leader", name _leader],
		["rounds", _rounds],
		["rounds_baseline", _group getVariable ["brmh_cmd_roundsBaseline", _rounds]],
		["behaviour", behaviour _leader],
		["combat_mode", combatMode _group],
		["order", _group getVariable ["brmh_cmd_order", ""]],
		["unable", _group getVariable ["brmh_cmd_unable", ""]],
		["leg", currentWaypoint _group],
		["legs", count waypoints _group],
		["clearing", _group getVariable ["brmh_cmd_clearLeft", -1]],
		["cleared", _group getVariable ["brmh_cmd_cleared", []]],
		["placed", _group getVariable ["brmh_cmd_placed", -1]],
		["contacts", [_leader] call brmh_cmd_fnc_contacts]
	]
};

brmh_cmd_fnc_truth = {
	private _groups = (allGroups select {
		side _x in [west, east, independent]
	}) apply {
		private _alive = (units _x) select {
			alive _x
		};
		createHashMapFromArray [
			["group", groupId _x],
			["side", str side _x],
			["alive", count _alive],
			["pos", if (_alive isEqualTo []) then {
				[]
			} else {
				(getPosATL (_alive # 0)) select [0, 2]
			}]
		]
	};
	["evt", createHashMapFromArray [["type", "cmd_truth"], ["groups", _groups]]] call BRMH_fnc_emit;
};

// Commander orders that aren't waypoints work from here, on each monitor step.
brmh_cmd_fnc_startClearing = {
	params ["_group", "_buildings"];
	private _total = 0;
	{
		_total = _total + count (nearestObject [(_x # 1) + [0], "House"] buildingPos -1);
	} forEach _buildings;
	_group setVariable ["brmh_cmd_clearQueue", +_buildings];
	_group setVariable ["brmh_cmd_clearSpots", []];
	_group setVariable ["brmh_cmd_clearCurrent", ""];
	_group setVariable ["brmh_cmd_clearLeft", _total max 1];
	_group setVariable ["brmh_cmd_cleared", []];
	{
		_x setVariable ["brmh_cmd_clearBy", 0];
	} forEach units _group;
};

// AI won't register an enemy it walks past. Only what a soldier could plainly see from here counts, so it isn't a cheat.
brmh_cmd_fnc_noticeNearby = {
	params ["_soldier"];
	private _side = side group _soldier;
	{
		if (alive _x and {
			(_side getFriend side group _x) < 0.6
		} and {
			([_soldier, "VIEW", _x] checkVisibility [eyePos _soldier, eyePos _x]) > 0.3
		}) then {
			_soldier reveal [_x, 4];
		};
	} forEach (_soldier nearEntities ["CAManBase", 10]);
};

// AI won't enter buildings to look for enemies it can't see, so soldiers are walked through every position in turn.
brmh_cmd_fnc_stepClearing = {
	params ["_group"];
	private _spots = _group getVariable ["brmh_cmd_clearSpots", []];
	private _queue = _group getVariable ["brmh_cmd_clearQueue", []];
	private _busy = 0;
	{
		private _soldier = _x;
		[_soldier] call brmh_cmd_fnc_noticeNearby;
		// A position can be unreachable, so nobody waits for one for long.
		if (time < (_soldier getVariable ["brmh_cmd_clearBy", 0]) and {
			not unitReady _soldier
		}) then {
			_busy = _busy + 1;
		} else {
			if (_spots isNotEqualTo []) then {
				_soldier doMove (_spots deleteAt 0);
				_soldier setVariable ["brmh_cmd_clearBy", time + 45];
				_busy = _busy + 1;
			};
		};
	} forEach ((units _group) select {
		alive _x
	});
	if (_spots isEqualTo [] and {
		_busy isEqualTo 0
	}) then {
		private _current = _group getVariable ["brmh_cmd_clearCurrent", ""];
		if (_current isNotEqualTo "") then {
			(_group getVariable ["brmh_cmd_cleared", []]) pushBack _current;
			_group setVariable ["brmh_cmd_clearCurrent", ""];
		};
		if (_queue isNotEqualTo []) then {
			private _next = _queue deleteAt 0;
			_group setVariable ["brmh_cmd_clearCurrent", _next # 0];
			_group setVariable ["brmh_cmd_clearSpots", nearestObject [(_next # 1) + [0], "House"] buildingPos -1];
		} else {
			_group setVariable ["brmh_cmd_clearQueue", nil];
			_group setVariable ["brmh_cmd_clearLeft", 0];
			{
				_x doFollow leader _group;
			} forEach units _group;
		};
	};
	if (not isNil {
		_group getVariable "brmh_cmd_clearQueue"
	}) then {
		private _left = _busy + count (_group getVariable ["brmh_cmd_clearSpots", []]);
		{
			_left = _left + count (nearestObject [(_x # 1) + [0], "House"] buildingPos -1);
		} forEach _queue;
		_group setVariable ["brmh_cmd_clearLeft", _left max 1];
	};
};

// OCCUPY and CORDON: each soldier gets a spot, walks there and stays.
brmh_cmd_fnc_startPlacing = {
	params ["_group", "_spots", "_watch"];
	_group setVariable ["brmh_cmd_placeSpots", _spots];
	_group setVariable ["brmh_cmd_placeWatch", _watch];
	_group setVariable ["brmh_cmd_placeBy", time + 90];
	_group setVariable ["brmh_cmd_placed", 0];
	private _count = count _spots;
	{
		if (_count > 0) then {
			_x doMove (_spots # (_forEachIndex mod _count));
		};
	} forEach ((units _group) select {
		alive _x
	});
};

brmh_cmd_fnc_stepPlacing = {
	params ["_group"];
	private _soldiers = (units _group) select {
		alive _x
	};
	private _waiting = {
		not unitReady _x
	} count _soldiers;
	if (_waiting isEqualTo 0 or time > (_group getVariable ["brmh_cmd_placeBy", 0])) then {
		private _watch = _group getVariable ["brmh_cmd_placeWatch", []];
		doStop _soldiers;
		if (_watch isNotEqualTo []) then {
			_soldiers doWatch _watch;
		};
		_group setVariable ["brmh_cmd_placed", 1];
	};
};

// CBA's tasks handle the behaviour. They run until replaced, so the commander's next order has to undo them cleanly.
brmh_cmd_fnc_startTask = {
	params ["_group", "_type", "_at", "_radius"];
	private _centre = _at + [0];
	_group setVariable ["brmh_cmd_task", true];
	switch (_type) do {
		case "ATTACK": {
			[_group, _centre, _radius, true] call CBA_fnc_taskAttack;
		};
		case "DEFEND": {
			[_group, _centre, _radius, 3, false, 1] call CBA_fnc_taskDefend;
		};
		case "PATROL_AREA": {
			[_group, _centre, _radius, 4] call CBA_fnc_taskPatrol;
		};
		case "SWEEP": {
			[_group, [_centre, _radius, _radius, 0, false]] call CBA_fnc_taskSearchArea;
		};
	};
};

brmh_cmd_fnc_listBuildings = {
	params [["_at", [], [[]], 2], ["_radius", 400, [0]]];
	private _centre = _at + [0];
	(nearestObjects [_centre, ["House"], _radius] select {
		count (_x buildingPos -1) > 0
	}) apply {
		private _box = boundingBoxReal _x;
		private _size = (_box # 1) vectorDiff (_box # 0);
		private _position = getPosATL _x;
		[_position # 0, _position # 1, mapGridPosition _position, getText (configOf _x >> "displayName"), count (_x buildingPos -1), _size # 0, _size # 1, getDir _x]
	}
};

brmh_cmd_fnc_step = {
	["evt", createHashMapFromArray [["type", "cmd_tick"]]] call BRMH_fnc_emit;
	{
		if (not isNil {
			_y getVariable "brmh_cmd_clearQueue"
		}) then {
			[_y] call brmh_cmd_fnc_stepClearing;
		};
		if ((_y getVariable ["brmh_cmd_placed", -1]) isEqualTo 0) then {
			[_y] call brmh_cmd_fnc_stepPlacing;
		};
	} forEach brmh_cmd_stations;
	{
		private _packet = [_x, _y] call brmh_cmd_fnc_packet;
		if (not isNil "_packet") then {
			["evt", _packet] call BRMH_fnc_emit;
		};
	} forEach brmh_cmd_stations;
	if (CBA_missionTime >= brmh_cmd_nextTruth) then {
		brmh_cmd_nextTruth = CBA_missionTime + 5;
		call brmh_cmd_fnc_truth;
	};
};

/*
	NAME: brmh_cmd_fnc_enroll
	DESCRIPTION: Spawns one station's group and puts it on the command net. Operator action, never reachable by the commander.
	PARAMETERS:
		0 - Callsign (STRING)
		1 - Side (SIDE)
		2 - Number of soldiers (NUMBER)
		3 - Unit class (STRING)
		4 - Position [x, y] (ARRAY)
	USAGE:
		["Alpha", west, 4, "B_Soldier_F", [3050, 3050]] call brmh_cmd_fnc_enroll;
	RETURNS: Number of soldiers created
	ENVIRONMENT: Server
*/
brmh_cmd_fnc_enroll = {
	params [["_callsign", "", [""]], ["_side", west, [west]], ["_count", 1, [0]], ["_class", "", [""]], ["_at", [], [[]], 2]];
	private _group = createGroup [_side, false];
	for "_i" from 1 to _count do {
		_group createUnit [_class, (_at + [0]) getPos [3 * _i, 90], [], 0, "NONE"];
	};
	_group setGroupIdGlobal [_callsign];
	private _rounds = 0;
	{
		_rounds = _rounds + ([_x] call brmh_cmd_fnc_rounds);
	} forEach units _group;
	_group setVariable ["brmh_cmd_baseline", count units _group];
	_group setVariable ["brmh_cmd_roundsBaseline", _rounds];
	brmh_cmd_stations set [_callsign, _group];
	count units _group
};

brmh_cmd_fnc_clearRoute = {
	params ["_group"];
	for "_i" from (count waypoints _group - 1) to 0 step -1 do {
		deleteWaypoint [_group, _i];
	};
};

brmh_cmd_fnc_posture = {
	params ["_group", "_posture"];
	_posture params ["_speed", "_formation", "_behaviour", "_combatMode"];
	if (_speed isNotEqualTo "") then {
		_group setSpeedMode _speed;
	};
	if (_formation isNotEqualTo "") then {
		_group setFormation _formation;
	};
	if (_behaviour isNotEqualTo "") then {
		_group setBehaviour _behaviour;
	};
	if (_combatMode isNotEqualTo "") then {
		_group setCombatMode _combatMode;
	};
};

/*
	NAME: brmh_cmd_fnc_order
	DESCRIPTION: Applies a validated order. The result never says whether the group exists, so the commander can't learn it from here.
	PARAMETERS:
		0 - Callsign (STRING)
		1 - Order id (STRING)
		2 - Mode: "replace", "append", "halt" or "posture" (STRING)
		3 - Legs: [[waypoint type, [x, y], radius, completion, hold for], ...] (ARRAY)
		4 - Posture: [speed, formation, behaviour, combat mode], "" leaves a setting alone (ARRAY)
	USAGE:
		["Alpha", "O-0001", "replace", [["MOVE", [3450, 3050], 0, 0, 0]], ["", "", "", ""]] call brmh_cmd_fnc_order;
	RETURNS: true
	ENVIRONMENT: Server
*/
brmh_cmd_fnc_order = {
	params [["_callsign", "", [""]], ["_order", "", [""]], ["_mode", "replace", [""]], ["_legs", [], [[]]], ["_posture", [], [[]], 4]];
	private _group = brmh_cmd_stations getOrDefault [_callsign, grpNull];
	if (isNull _group) exitWith {
		true
	};
	_group setVariable ["brmh_cmd_order", _order];
	_group setVariable ["brmh_cmd_unable", ""];
	if (_mode isNotEqualTo "posture") then {
		_group setVariable ["brmh_cmd_clearQueue", nil];
		_group setVariable ["brmh_cmd_clearLeft", -1];
		_group setVariable ["brmh_cmd_cleared", []];
		_group setVariable ["brmh_cmd_placed", -1];
		// DEFEND disables pathing and ATTACK leaves a group crawling in COMBAT. Spike-tested: without this, they ignore new orders.
		{
			_x enableAI "PATH";
		} forEach units _group;
		if (_group getVariable ["brmh_cmd_task", false]) then {
			_group setVariable ["brmh_cmd_task", false];
			_group setBehaviour "AWARE";
		};
	};
	if ((_legs findIf {
		not ((_x # 0) in ["CYCLE", "CLEAR"]) and {
			surfaceIsWater (_x # 1)
		}
	}) >= 0) exitWith {
		_group setVariable ["brmh_cmd_unable", "water"];
		true
	};
	[_group, _posture] call brmh_cmd_fnc_posture;
	if (_mode isEqualTo "posture") exitWith {
		true
	};
	if (_mode isEqualTo "halt") exitWith {
		[_group] call brmh_cmd_fnc_clearRoute;
		// Clearing waypoints doesn't stop a walking group, and doFollow and doMove don't either. doStop does.
		doStop (units _group);
		true
	};
	private _finished = currentWaypoint _group >= count waypoints _group;
	if (_mode isEqualTo "replace") then {
		[_group] call brmh_cmd_fnc_clearRoute;
	};
	{
		_x doFollow leader _group;
	} forEach units _group;
	private _first = [];
	{
		_x params ["_type", "_at", "_radius", "_completion", "_holdFor"];
		if (_type isEqualTo "CLEAR") then {
			[_group, _at] call brmh_cmd_fnc_startClearing;
			continue;
		};
		if (_type isEqualTo "OCCUPY") then {
			private _spots = nearestObject [_at + [0], "House"] buildingPos -1;
			[_group, _spots, []] call brmh_cmd_fnc_startPlacing;
			continue;
		};
		if (_type isEqualTo "CORDON") then {
			private _count = ({
				alive _x
			} count units _group) max 1;
			private _ring = [];
			for "_i" from 0 to (_count - 1) do {
				_ring pushBack ((_at + [0]) getPos [_radius, 360 * _i / _count]);
			};
			[_group, _ring, _at + [0]] call brmh_cmd_fnc_startPlacing;
			continue;
		};
		if (_type in ["ATTACK", "DEFEND", "PATROL_AREA", "SWEEP"]) then {
			[_group, _type, _at, _radius] call brmh_cmd_fnc_startTask;
			continue;
		};
		private _waypoint = _group addWaypoint [_at + [0], _radius];
		_waypoint setWaypointType _type;
		if (_completion > 0) then {
			_waypoint setWaypointCompletionRadius _completion;
		};
		if (_holdFor > 0) then {
			_waypoint setWaypointTimeout [_holdFor, _holdFor, _holdFor];
		};
		if (_first isEqualTo []) then {
			_first = _waypoint;
		};
	} forEach _legs;
	if (_first isNotEqualTo [] and {
		_mode isEqualTo "replace" or _finished
	}) then {
		_group setCurrentWaypoint _first;
	};
	true
};

brmh_cmd_fnc_deleteStation = {
	params [["_callsign", "", [""]]];
	private _group = brmh_cmd_stations getOrDefault [_callsign, grpNull];
	{
		deleteVehicle _x;
	} forEach units _group;
	true
};

brmh_cmd_fnc_killStation = {
	params [["_callsign", "", [""]]];
	private _group = brmh_cmd_stations getOrDefault [_callsign, grpNull];
	{
		_x setDamage 1;
	} forEach units _group;
	true
};

/*
	NAME: brmh_cmd_fnc_spawnEnemy
	DESCRIPTION: Spawns an opposing group for a scenario. Operator action. Enemies are never on the net.
	PARAMETERS:
		0 - Group id (STRING)
		1 - Side (SIDE)
		2 - Number of soldiers (NUMBER)
		3 - Unit class (STRING)
		4 - Position [x, y] (ARRAY)
		5 - Mode: "hold" stays put, "garrison" takes positions in nearby buildings, "patrol" walks the area (STRING)
		6 - Radius in metres (NUMBER)
	USAGE:
		["East 1", east, 6, "O_Soldier_F", [4100, 4160], "garrison", 120] call brmh_cmd_fnc_spawnEnemy;
	RETURNS: Number of soldiers created
	ENVIRONMENT: Server
*/
brmh_cmd_fnc_spawnEnemy = {
	params [["_id", "", [""]], ["_side", east, [east]], ["_count", 1, [0]], ["_class", "", [""]], ["_at", [], [[]], 2], ["_mode", "hold", [""]], ["_radius", 100, [0]]];
	private _centre = _at + [0];
	private _group = createGroup [_side, false];
	for "_i" from 1 to _count do {
		_group createUnit [_class, _centre getPos [3 * _i, 90], [], 0, "NONE"];
	};
	_group setGroupIdGlobal [_id];
	brmh_cmd_enemies pushBack _group;
	if (_mode isEqualTo "garrison") then {
		private _spots = [];
		{
			_spots append (_x buildingPos -1);
		} forEach nearestObjects [_centre, ["House"], _radius];
		{
			if (_spots isNotEqualTo []) then {
				_x setPosATL (_spots deleteAt floor random count _spots);
				_x disableAI "PATH";
			};
		} forEach units _group;
	};
	if (_mode isEqualTo "patrol") then {
		[_group, _centre, _radius] call BIS_fnc_taskPatrol;
	};
	count units _group
};

// A repeat start reuses the running game. Renaming keeps old empty groups out of the new battle's records.
brmh_cmd_fnc_clearAll = {
	{
		[_x] call brmh_cmd_fnc_deleteStation;
		_y setGroupIdGlobal ["Retired"];
	} forEach brmh_cmd_stations;
	brmh_cmd_stations = createHashMap;
	{
		private _group = _x;
		{
			deleteVehicle _x;
		} forEach units _group;
		_group setGroupIdGlobal ["Retired"];
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
};

/*
	Two one-way feeds for a human observer. They write to the game's chat and map, and nothing reads them back,
	so they can't help the commander.
*/
brmh_cmd_fnc_show = {
	params [["_text", "", [""]]];
	[_text] remoteExec ["systemChat", 0];
	true
};

brmh_cmd_fnc_mirror = {
	params [["_id", "", [""]], ["_kind", "note", [""]], ["_points", [], [[]]], ["_label", "", [""]], ["_confidence", "", [""]], ["_removed", false, [false]]];
	private _name = "brmh_cmd_" + _id;
	deleteMarker _name;
	if (_removed) exitWith {
		true
	};
	private _marker = createMarker [_name, (_points # 0) + [0]];
	_marker setMarkerType (createHashMapFromArray [["enemy", "mil_warning"], ["friendly", "mil_dot"], ["objective", "mil_objective"], ["danger", "mil_warning"], ["hypothesis", "mil_unknown"]] getOrDefault [_kind, "mil_dot"]);
	_marker setMarkerColor (createHashMapFromArray [["enemy", "ColorOPFOR"], ["friendly", "ColorBLUFOR"], ["objective", "ColorGreen"], ["danger", "ColorOrange"]] getOrDefault [_kind, "ColorWhite"]);
	_marker setMarkerText (([_id, _label, _confidence] select {
		_x isNotEqualTo ""
	}) joinString " ");
	true
};

brmh_cmd_pfh = [{
	call brmh_cmd_fnc_step;
}, 2] call CBA_fnc_addPerFrameHandler;
true
