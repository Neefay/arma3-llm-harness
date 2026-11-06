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
if (isNil "brmh_cmd_vehicles") then {
	brmh_cmd_vehicles = createHashMap;
};
if (isNil "brmh_cmd_buildings") then {
	brmh_cmd_buildings = createHashMap;
};
if (isNil "brmh_cmd_fireActive") then {
	brmh_cmd_fireActive = [];
};
if (isNil "brmh_cmd_carries") then {
	brmh_cmd_carries = [];
};
if (isNil "brmh_cmd_treats") then {
	brmh_cmd_treats = [];
};
if (isNil "brmh_cmd_builds") then {
	brmh_cmd_builds = [];
};
if (isNil "brmh_cmd_posts") then {
	brmh_cmd_posts = [];
};
if (isNil "brmh_cmd_down") then {
	brmh_cmd_down = [];
};
if (isNil "brmh_cmd_men") then {
	brmh_cmd_men = createHashMap;
	brmh_cmd_manCount = 0;
};
if (isNil "brmh_cmd_careTimes") then {
	brmh_cmd_careTimes = createHashMapFromArray [["field_s", 120], ["facility_s", 60], ["build_s", 60]];
};
// A leader who wakes takes command back, and his squad runs back to him, wherever it's been sent. So whoever's got it keeps it.
if (isNil "brmh_cmd_downHandler") then {
	brmh_cmd_downHandler = ["ace_unconscious", {
		params ["_unit", "_down"];
		if (_down) then {
			brmh_cmd_down pushBackUnique _unit;
		} else {
			brmh_cmd_down = brmh_cmd_down - [_unit];
			private _group = group _unit;
			private _acting = _group getVariable ["brmh_cmd_acting", objNull];
			if (not isNull _acting and {
				_acting isNotEqualTo _unit
			}) then {
				{
					[{
						params ["_group", "_acting"];
						if ([_acting] call brmh_cmd_fnc_able and {
							group _acting isEqualTo _group
						}) then {
							_group selectLeader _acting;
						};
					}, [_group, _acting], _x] call CBA_fnc_waitAndExecute;
				} forEach [0.2, 1, 3];
			};
		};
	}] call CBA_fnc_addEventHandler;
};
brmh_cmd_sightTurn = 0;
brmh_cmd_nextTruth = 0;

// Who can do anything. Under ACE a downed man is alive, and stays in his group, lying where he fell.
brmh_cmd_fnc_able = {
	params ["_man"];
	alive _man and {
		lifeState _man isNotEqualTo "INCAPACITATED"
	}
};

brmh_cmd_fnc_manKey = {
	params ["_man"];
	private _key = _man getVariable ["brmh_cmd_man", ""];
	if (_key isEqualTo "") then {
		brmh_cmd_manCount = brmh_cmd_manCount + 1;
		_key = format ["m%1", brmh_cmd_manCount];
		_man setVariable ["brmh_cmd_man", _key];
		brmh_cmd_men set [_key, _man];
	};
	_key
};

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
	// A fire mission makes the engine put a hidden ArtilleryTarget at the aim point, on the other side. It isn't an enemy
	// to anyone, and once it's gone, what's known of it is a place at the map's origin.
	((_leader targets [true, 2000]) select {
		not isNull _x and {
			not ("ArtilleryTarget" in typeOf _x)
		}
	}) apply {
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

// A numbered building, if it's still standing. A destroyed one becomes a ruin that isn't a House. The search has to be wide,
// because it measures in 3D from the model's centre, which is high up on a tower, but only what's directly here counts,
// or it would find a neighbour instead.
brmh_cmd_fnc_building = {
	params ["_pos"];
	private _here = (_pos select [0, 2]) + [0];
	private _found = (nearestObjects [_here, ["House"], 40]) select {
		alive _x and {
			(_x distance2D _here) < 6
		} and {
			(_x buildingPos -1) isNotEqualTo []
		}
	};
	if (_found isEqualTo []) then {
		objNull
	} else {
		_found # 0
	}
};

brmh_cmd_fnc_canSee = {
	params ["_soldiers", "_object", "_point", ["_through", "VIEW"]];
	(_soldiers findIf {
		([_x, _through, _object] checkVisibility [eyePos _x, _point]) > 0.3
	}) >= 0
};

// What a squad can see of vehicles and destroyed buildings. The host decides what's news. Only worked out now and then,
// because it's the most expensive thing here.
brmh_cmd_fnc_sightings = {
	params ["_group"];
	private _alive = (units _group) select {
		[_x] call brmh_cmd_fnc_able
	};
	if (_alive isEqualTo []) exitWith {};
	private _lookers = _alive select [0, 4];
	private _leader = _alive # 0;
	private _vehicles = (_leader nearEntities [["StaticWeapon", "LandVehicle"], 800]) select {
		({
			alive _x
		} count crew _x) isEqualTo 0
	};
	{
		if (not alive _y and {
			_leader distance2D _y < 800
		}) then {
			_vehicles pushBackUnique _y;
		};
	} forEach brmh_cmd_vehicles;
	private _seen = [];
	{
		private _vehicle = _x;
		private _top = (getPosASL _vehicle) vectorAdd [0, 0, 1];
		// A burning wreck's own smoke blocks VIEW, even from beside it. FIRE ignores smoke.
		if ([_lookers, _vehicle, _top, ["FIRE", "VIEW"] select alive _vehicle] call brmh_cmd_fnc_canSee) then {
			private _key = _vehicle getVariable ["brmh_cmd_key", ""];
			if (_key isEqualTo "") then {
				_key = format ["U%1", count brmh_cmd_vehicles + 1];
				_vehicle setVariable ["brmh_cmd_key", _key];
				brmh_cmd_vehicles set [_key, _vehicle];
			};
			_seen pushBack [_key, getText (configOf _vehicle >> "displayName"), mapGridPosition _vehicle, alive _vehicle];
		};
	} forEach _vehicles;
	_group setVariable ["brmh_cmd_seenVehicles", _seen];
	private _ruins = [];
	{
		if (_leader distance2D _y < 800 and {
			isNull ([_y] call brmh_cmd_fnc_building)
		}) then {
			private _ground = [_y # 0, _y # 1, (getTerrainHeightASL _y) + 1];
			if ([_lookers, objNull, _ground, "FIRE"] call brmh_cmd_fnc_canSee) then {
				_ruins pushBack _x;
			};
		};
	} forEach brmh_cmd_buildings;
	_group setVariable ["brmh_cmd_seenRuins", _ruins];
};

brmh_cmd_fnc_mounted = {
	params ["_alive"];
	private _out = [];
	{
		private _soldier = _x;
		private _vehicle = vehicle _soldier;
		if (_vehicle isNotEqualTo _soldier) then {
			private _seat = (fullCrew _vehicle) select {
				(_x # 0) isEqualTo _soldier
			};
			_out pushBack [_vehicle getVariable ["brmh_cmd_key", ""], if (_seat isEqualTo []) then {
				"cargo"
			} else {
				_seat # 0 # 1
			}, name _soldier, _vehicle isKindOf "StaticWeapon"];
		};
	} forEach _alive;
	_out
};

// Free seats of a kind, in the game's own order. A seat with a dead man in it counts as free. The engine lets someone take it.
brmh_cmd_fnc_freeSeats = {
	params ["_vehicle", "_kind"];
	(fullCrew [_vehicle, "", true]) select {
		(_x # 1) isEqualTo _kind and {
			isNull (_x # 0) or {
				not alive (_x # 0)
			}
		}
	}
};

brmh_cmd_fnc_seatMan = {
	params ["_man", "_vehicle", "_seat"];
	_seat params ["", "_role", "_cargo", "_turret"];
	switch (_role) do {
		case "driver": {
			_man assignAsDriver _vehicle;
		};
		case "gunner": {
			_man assignAsGunner _vehicle;
		};
		case "commander": {
			_man assignAsCommander _vehicle;
		};
		case "cargo": {
			_man assignAsCargoIndex [_vehicle, _cargo];
		};
		default {
			_man assignAsTurret [_vehicle, _turret];
		};
	};
};

// A gun's crew only fires when ordered. A crewed gun otherwise opens up by itself at any enemy its crew knows of.
brmh_cmd_fnc_onSeat = {
	params ["_man", "_vehicle"];
	if (getNumber (configOf _vehicle >> "artilleryScanner") > 0 and {
		gunner _vehicle isEqualTo _man
	}) then {
		_man disableAI "TARGET";
	};
};

brmh_cmd_fnc_startMount = {
	params ["_group", "_key", "_kind"];
	private _vehicle = brmh_cmd_vehicles getOrDefault [_key, objNull];
	_group setVariable ["brmh_cmd_mountList", []];
	_group setVariable ["brmh_cmd_mount", []];
	if (isNull _vehicle or {
		not alive _vehicle
	}) exitWith {
		_group setVariable ["brmh_cmd_mount", [_key, "wrecked", _kind, []]];
	};
	private _leader = leader _group;
	// The newest first, and the leader last: a leader on a gun stays there and holds the squad with him.
	private _newestFirst = +(units _group);
	reverse _newestFirst;
	// Not a man carrying someone, or one who's too far off to be part of this.
	private _free = _newestFirst select {
		[_x] call brmh_cmd_fnc_able and {
			_x isNotEqualTo _leader
		} and {
			vehicle _x isEqualTo _x
		} and {
			not (_x getVariable ["brmh_cmd_busy", false])
		} and {
			(_x distance2D _vehicle) < 500
		}
	};
	if ([_leader] call brmh_cmd_fnc_able and {
		vehicle _leader isEqualTo _leader
	} and {
		not (_leader getVariable ["brmh_cmd_busy", false])
	}) then {
		_free pushBack _leader;
	};
	private _seats = [];
	if (_kind isEqualTo "") then {
		{
			_seats append ([_vehicle, _x] call brmh_cmd_fnc_freeSeats);
		} forEach ["driver", "gunner", "commander", "cargo", "turret"];
	} else {
		if ((_kind select [0, 7]) isEqualTo "turret:") then {
			private _all = (fullCrew [_vehicle, "", true]) select {
				(_x # 1) isEqualTo "turret"
			};
			private _index = parseNumber (_kind select [7]);
			_seats = (_all select [_index, 1]) select {
				isNull (_x # 0) or {
					not alive (_x # 0)
				}
			};
		} else {
			if (((fullCrew [_vehicle, "", true]) findIf {
				(_x # 1) isEqualTo _kind
			}) < 0) exitWith {
				_group setVariable ["brmh_cmd_mount", [_key, "noseat", _kind, []]];
			};
			_seats = ([_vehicle, _kind] call brmh_cmd_fnc_freeSeats) select [0, 1];
		};
	};
	if ((_group getVariable ["brmh_cmd_mount", []]) isEqualTo [_key, "noseat", _kind, []]) exitWith {};
	if (_seats isEqualTo []) exitWith {
		_group setVariable ["brmh_cmd_mount", [_key, "taken", _kind, []]];
	};
	if (_free isEqualTo []) exitWith {
		_group setVariable ["brmh_cmd_mount", [_key, "nobody", _kind, []]];
	};
	private _list = [];
	{
		if (_forEachIndex < count _free) then {
			private _man = _free # _forEachIndex;
			[_man, _vehicle, _x] call brmh_cmd_fnc_seatMan;
			_list pushBack [_man, _x # 1, _x # 2, _x # 3];
		};
	} forEach _seats;
	if (not (_vehicle isKindOf "StaticWeapon")) then {
		_group addVehicle _vehicle;
	};
	(_list apply {
		_x # 0
	}) orderGetIn true;
	_group setVariable ["brmh_cmd_mountList", _list];
	_group setVariable ["brmh_cmd_mountBy", time + 60 + ((_leader distance2D _vehicle) / 1.5)];
	// Only when it asked for everyone who fits. A named seat is for one man.
	_group setVariable ["brmh_cmd_mountSpare", [0, ((count _free) - (count _seats)) max 0] select (_kind isEqualTo "")];
	_group setVariable ["brmh_cmd_mountVehicle", _vehicle];
	_group setVariable ["brmh_cmd_mount", [_key, "going", _kind, []]];
};

brmh_cmd_fnc_stepMount = {
	params ["_group"];
	private _list = _group getVariable ["brmh_cmd_mountList", []];
	if (_list isEqualTo []) exitWith {};
	private _vehicle = _group getVariable ["brmh_cmd_mountVehicle", objNull];
	private _status = _group getVariable ["brmh_cmd_mount", []];
	_status params ["_key", "", "_kind"];
	private _stop = {
		params ["_word", "_names"];
		{
			if (alive (_x # 0) and {
				vehicle (_x # 0) isNotEqualTo _vehicle
			}) then {
				unassignVehicle (_x # 0);
				[_x # 0] orderGetIn false;
			};
		} forEach _list;
		_group setVariable ["brmh_cmd_mountList", []];
		_group setVariable ["brmh_cmd_mount", [_key, _word, _kind, _names, _group getVariable ["brmh_cmd_mountSpare", 0]]];
	};
	if (not alive _vehicle) exitWith {
		["wrecked", []] call _stop;
	};
	private _on = [];
	private _waiting = [];
	{
		_x params ["_man", "_role", "_cargo", "_turret"];
		if (alive _man) then {
			if (vehicle _man isEqualTo _vehicle) then {
				[_man, _vehicle] call brmh_cmd_fnc_onSeat;
				_on pushBack _man;
			} else {
				_waiting pushBack _x;
			};
		};
	} forEach _list;
	private _names = _on apply {
		name _x
	};
	if (_waiting isEqualTo []) exitWith {
		if (_on isEqualTo []) then {
			["nobody", []] call _stop;
		} else {
			["on", _names] call _stop;
		};
	};
	// The engine has a man wait beside a seat someone else has taken, with no error.
	private _taken = (_waiting findIf {
		_x params ["_man", "_role", "_cargo", "_turret"];
		((fullCrew [_vehicle, "", true]) findIf {
			alive (_x # 0) and {
				(_x # 0) isNotEqualTo _man
			} and {
				(_x # 1) isEqualTo _role
			} and {
				(_x # 2) isEqualTo _cargo
			} and {
				(_x # 3) isEqualTo _turret
			}
		}) >= 0
	}) >= 0;
	if (_taken) exitWith {
		["taken", _names] call _stop;
	};
	if (time > (_group getVariable ["brmh_cmd_mountBy", 0])) exitWith {
		["unreachable", _names] call _stop;
	};
};

brmh_cmd_fnc_getOff = {
	params ["_man"];
	private _vehicle = vehicle _man;
	if (_vehicle isNotEqualTo _man) then {
		_man action ["GetOut", _vehicle];
	};
	unassignVehicle _man;
	[_man] orderGetIn false;
	_man enableAI "TARGET";
};

brmh_cmd_fnc_startDismount = {
	params ["_group", "_key"];
	_group setVariable ["brmh_cmd_mountList", []];
	private _men = (units _group) select {
		[_x] call brmh_cmd_fnc_able and {
			vehicle _x isNotEqualTo _x
		} and {
			_key isEqualTo "" or {
				(vehicle _x getVariable ["brmh_cmd_key", ""]) isEqualTo _key
			}
		}
	};
	{
		_group leaveVehicle (vehicle _x);
		[_x] call brmh_cmd_fnc_getOff;
	} forEach _men;
	_group setVariable ["brmh_cmd_mount", [_key, ["none", "going off"] select (_men isNotEqualTo []), "", _men apply {
		name _x
	}]];
};

brmh_cmd_fnc_stepDismount = {
	params ["_group"];
	private _status = _group getVariable ["brmh_cmd_mount", []];
	if ((_status param [1, ""]) isNotEqualTo "going off") exitWith {};
	private _still = (units _group) select {
		[_x] call brmh_cmd_fnc_able and {
			vehicle _x isNotEqualTo _x
		} and {
			(_status # 0) isEqualTo "" or {
				(vehicle _x getVariable ["brmh_cmd_key", ""]) isEqualTo (_status # 0)
			}
		}
	};
	if (_still isEqualTo []) then {
		_status set [1, "off"];
	};
};

/*
	NAME: brmh_cmd_fnc_crew
	DESCRIPTION: Starts a scenario with a soldier already in a seat. Operator action, never reachable by the commander.
	PARAMETERS:
		0 - Callsign (STRING)
		1 - Vehicle id (STRING)
		2 - Seat: gunner, driver, commander or cargo (STRING)
	USAGE:
		["Hammer", "V1", "gunner"] call brmh_cmd_fnc_crew;
	RETURNS: Whether anybody got on
	ENVIRONMENT: Server
*/
brmh_cmd_fnc_crew = {
	params [["_callsign", "", [""]], ["_key", "", [""]], ["_kind", "gunner", [""]]];
	private _group = brmh_cmd_stations getOrDefault [_callsign, grpNull];
	private _vehicle = brmh_cmd_vehicles getOrDefault [_key, objNull];
	private _seat = ([_vehicle, _kind] call brmh_cmd_fnc_freeSeats) param [0, []];
	private _free = (+(units _group)) select {
		vehicle _x isEqualTo _x
	};
	reverse _free;
	if (_seat isEqualTo [] or {
		_free isEqualTo []
	}) exitWith {
		false
	};
	private _man = _free # 0;
	[_man, _vehicle, _seat] call brmh_cmd_fnc_seatMan;
	switch (_kind) do {
		case "driver": {
			_man moveInDriver _vehicle;
		};
		case "commander": {
			_man moveInCommander _vehicle;
		};
		case "cargo": {
			_man moveInCargo _vehicle;
		};
		default {
			_man moveInGunner _vehicle;
		};
	};
	[_man, _vehicle] call brmh_cmd_fnc_onSeat;
	true
};

// Who a squad knows is down: its own, wherever they are, and anyone else's within sight of its leader.
brmh_cmd_fnc_casualties = {
	params ["_group", "_leader"];
	private _down = (units _group) select {
		alive _x and {
			not ([_x] call brmh_cmd_fnc_able)
		}
	};
	private _others = brmh_cmd_down select {
		alive _x and {
			group _x isNotEqualTo _group
		} and {
			(_x distance2D _leader) < 30
		}
	};
	(_down + _others) apply {
		private _position = getPosATL _x;
		[[_x] call brmh_cmd_fnc_manKey, name _x, _position # 0, _position # 1, (vehicle _x) getVariable ["brmh_cmd_key", ""],
		 vehicle _x isNotEqualTo _x, group _x isEqualTo _group, _x getVariable ["brmh_cmd_handled", ""]]
	}
};

brmh_cmd_fnc_packet = {
	params ["_callsign", "_group"];
	private _alive = (units _group) select {
		[_x] call brmh_cmd_fnc_able
	};
	if (_alive isEqualTo []) exitWith {
		nil
	};
	// For several seconds after a leader dies, leader still returns the body. A downed one takes a moment to pass it on too.
	private _leader = if ([leader _group] call brmh_cmd_fnc_able) then {
		leader _group
	} else {
		_alive # 0
	};
	_group setVariable ["brmh_cmd_acting", _leader];
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
		["limping", (_alive select {
			(_x getHitPointDamage "hitLegs") >= 0.5
		}) apply {
			name _x
		}],
		["baseline", _group getVariable ["brmh_cmd_baseline", count _alive]],
		["leader", name _leader],
		["rounds", _rounds],
		["rounds_baseline", _group getVariable ["brmh_cmd_roundsBaseline", _rounds]],
		["behaviour", behaviour _leader],
		["combat_mode", combatMode _group],
		["suppression", (_alive apply {
			getSuppression _x
		}) call BIS_fnc_arithmeticMean],
		["order", _group getVariable ["brmh_cmd_order", ""]],
		["unable", _group getVariable ["brmh_cmd_unable", ""]],
		["leg", currentWaypoint _group],
		["legs", count waypoints _group],
		["clearing", _group getVariable ["brmh_cmd_clearLeft", -1]],
		["cleared", _group getVariable ["brmh_cmd_cleared", []]],
		["ruined", _group getVariable ["brmh_cmd_ruined", []]],
		["seen_vehicles", _group getVariable ["brmh_cmd_seenVehicles", []]],
		["seen_ruins", _group getVariable ["brmh_cmd_seenRuins", []]],
		["mounted", [_alive] call brmh_cmd_fnc_mounted],
		["mount", _group getVariable ["brmh_cmd_mount", []]],
		["missions", (_group getVariable ["brmh_cmd_missions", []]) apply {
			[_x get "key", _x get "order", _x get "state", _x getOrDefault ["reason", ""], _x get "word", _x getOrDefault ["fired", 0], _x get "want", _x getOrDefault ["eta", 0], _x getOrDefault ["inAir", 0]]
		}],
		["gun_ammo", ([_group, []] call brmh_cmd_fnc_gunsOf) apply {
			[_x getVariable ["brmh_cmd_key", ""], [_x] call brmh_cmd_fnc_gunAmmo]
		}],
		["placed", _group getVariable ["brmh_cmd_placed", -1]],
		["casualties", [_group, _leader] call brmh_cmd_fnc_casualties],
		["up", _alive apply {
			[_x] call brmh_cmd_fnc_manKey
		}],
		["medical", _group getVariable ["brmh_cmd_care", []]],
		["contacts", [_leader] call brmh_cmd_fnc_contacts]
	]
};

brmh_cmd_fnc_truth = {
	private _groups = (allGroups select {
		side _x in [west, east, independent]
	}) apply {
		private _alive = (units _x) select {
			[_x] call brmh_cmd_fnc_able
		};
		createHashMapFromArray [
			["group", groupId _x],
			["side", str side _x],
			["alive", count _alive],
			["down", ((units _x) select {
				alive _x and {
					not ([_x] call brmh_cmd_fnc_able)
				}
			}) apply {
				private _position = getPosATL _x;
				[round (_position # 0), round (_position # 1)]
			}],
			["mounted", {
				vehicle _x isNotEqualTo _x
			} count _alive],
			["limping", {
				(_x getHitPointDamage "hitLegs") >= 0.5
			} count _alive],
			["leader_limping", ((leader _x) getHitPointDamage "hitLegs") >= 0.5],
			["pos", if (_alive isEqualTo []) then {
				[]
			} else {
				(getPosATL (_alive # 0)) select [0, 2]
			}],
			["units", _alive apply {
				private _position = getPosATL _x;
				[round (_position # 0), round (_position # 1), round (_position # 2)]
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
		_total = _total + count (([_x # 1] call brmh_cmd_fnc_building) buildingPos -1);
	} forEach _buildings;
	_group setVariable ["brmh_cmd_clearQueue", +_buildings];
	_group setVariable ["brmh_cmd_clearSpots", []];
	_group setVariable ["brmh_cmd_clearCurrent", ""];
	_group setVariable ["brmh_cmd_clearLeft", _total max 1];
	_group setVariable ["brmh_cmd_cleared", []];
	_group setVariable ["brmh_cmd_ruined", []];
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
		[_x] call brmh_cmd_fnc_able
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
			private _building = [_next # 1] call brmh_cmd_fnc_building;
			if (isNull _building) then {
				(_group getVariable ["brmh_cmd_ruined", []]) pushBack (_next # 0);
			} else {
				_group setVariable ["brmh_cmd_clearCurrent", _next # 0];
				_group setVariable ["brmh_cmd_clearSpots", _building buildingPos -1];
			};
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
			_left = _left + count (([_x # 1] call brmh_cmd_fnc_building) buildingPos -1);
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
		[_x] call brmh_cmd_fnc_able
	});
};

brmh_cmd_fnc_stepPlacing = {
	params ["_group"];
	private _soldiers = (units _group) select {
		[_x] call brmh_cmd_fnc_able
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
	_group setVariable ["brmh_cmd_releaseUntil", 0];
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
		[_y] call brmh_cmd_fnc_stepMount;
		[_y] call brmh_cmd_fnc_stepDismount;
		if (time < (_y getVariable ["brmh_cmd_releaseUntil", 0])) then {
			{
				_x enableAI "PATH";
			} forEach units _y;
		};
	} forEach brmh_cmd_stations;
	call brmh_cmd_fnc_stepTreats;
	call brmh_cmd_fnc_stepBuilds;
	// One squad per step looks around, so nobody's sight checks pile up.
	private _names = keys brmh_cmd_stations;
	if (_names isNotEqualTo []) then {
		brmh_cmd_sightTurn = (brmh_cmd_sightTurn + 1) % count _names;
		[brmh_cmd_stations get (_names # brmh_cmd_sightTurn)] call brmh_cmd_fnc_sightings;
	};
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
	// These only concern the gun, and leave the squad's own orders as they were.
	if (_mode isEqualTo "fire") exitWith {
		[_group, _order, _legs # 0] call brmh_cmd_fnc_startFire;
		true
	};
	if (_mode isEqualTo "checkfire") exitWith {
		[_group, _order, _legs # 0 # 0] call brmh_cmd_fnc_checkFire;
		true
	};
	if (_mode in ["carry", "unload", "treat", "post"]) exitWith {
		([_group, _order] + (_legs # 0)) call (missionNamespace getVariable format ["brmh_cmd_fnc_%1Order", _mode]);
		true
	};
	if (_mode isNotEqualTo "posture") then {
		_group setVariable ["brmh_cmd_clearQueue", nil];
		_group setVariable ["brmh_cmd_clearLeft", -1];
		_group setVariable ["brmh_cmd_cleared", []];
		_group setVariable ["brmh_cmd_placed", -1];
		{
			_x enableAI "PATH";
		} forEach units _group;
		if (_group getVariable ["brmh_cmd_task", false]) then {
			_group setVariable ["brmh_cmd_task", false];
			// ATTACK leaves a group crawling in COMBAT, and DEFEND at LIMITED speed. Both tested on a real game.
			_group setBehaviour "AWARE";
			_group setSpeedMode "NORMAL";
			// DEFEND's scripts keep running, and disable each soldier's pathing as he reaches his post. See the monitor step.
			_group setVariable ["brmh_cmd_releaseUntil", time + 150];
		};
	};
	if (_mode isEqualTo "mount") exitWith {
		[_group, _legs # 0 # 0, _legs # 0 # 1] call brmh_cmd_fnc_startMount;
		true
	};
	if (_mode isEqualTo "dismount") exitWith {
		[_group, _legs # 0 # 0] call brmh_cmd_fnc_startDismount;
		true
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
	// A leader on a gun won't go anywhere by waypoint, and neither will his squad. Anyone else stays on theirs.
	private _leader = leader _group;
	if (vehicle _leader isKindOf "StaticWeapon") then {
		[_leader] call brmh_cmd_fnc_getOff;
	};
	private _finished = currentWaypoint _group >= count waypoints _group;
	if (_mode isEqualTo "replace") then {
		[_group] call brmh_cmd_fnc_clearRoute;
	};
	// A man in a seat told to follow climbs out to do it, and back in a few seconds later, so not when his leader is
	// riding too. It's still needed when he isn't: a squad on foot barely moves while a man it left on a gun hasn't had it.
	private _riding = vehicle (leader _group) isNotEqualTo (leader _group) and {
		not (vehicle (leader _group) isKindOf "StaticWeapon")
	};
	{
		if ([_x] call brmh_cmd_fnc_able and {
			not (_x getVariable ["brmh_cmd_busy", false])
		} and {
			not _riding or {
				vehicle _x isEqualTo _x
			}
		}) then {
			_x doFollow leader _group;
		};
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
				[_x] call brmh_cmd_fnc_able
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
/*
	NAME: brmh_cmd_fnc_spawnVehicle
	DESCRIPTION: Places a scenario's vehicle or gun. Operator action, never reachable by the commander.
	PARAMETERS:
		0 - Scenario id (STRING)
		1 - Class (STRING)
		2 - Position [x, y] (ARRAY)
		3 - Ammunition [magazine, rounds] pairs, empty to leave it as it comes (ARRAY)
	USAGE:
		["V1", "B_Mortar_01_F", [4150, 3350], [["8Rnd_82mm_Mo_shells", 16]]] call brmh_cmd_fnc_spawnVehicle;
	RETURNS: Its display name
	ENVIRONMENT: Server
*/
brmh_cmd_fnc_spawnVehicle = {
	params [["_key", "", [""]], ["_class", "", [""]], ["_at", [], [[]], 2], ["_ammo", [], [[]]]];
	private _vehicle = createVehicle [_class, _at + [0], [], 0, "NONE"];
	_vehicle setVariable ["brmh_cmd_key", _key];
	brmh_cmd_vehicles set [_key, _vehicle];
	if (getNumber (configOf _vehicle >> "artilleryScanner") > 0) then {
		[_vehicle] call brmh_cmd_fnc_trackGun;
	};
	if (_ammo isNotEqualTo []) then {
		[_vehicle, _ammo] call brmh_cmd_fnc_setAmmo;
	};
	getText (configOf _vehicle >> "displayName")
};

// What the commander calls a magazine. Anything else a gun carries, such as mines or flares, isn't offered yet.
brmh_cmd_fnc_ammoWord = {
	params ["_magazine"];
	private _name = toLowerANSI _magazine;
	if ("smoke" in _name) exitWith {
		"SMOKE"
	};
	if ("shells" in _name) exitWith {
		"HE"
	};
	""
};

// Sets what a gun's main turret carries, from [["HE", 16], ["SMOKE", 4]]. Types not listed are taken away.
brmh_cmd_fnc_setAmmo = {
	params ["_vehicle", "_ammo"];
	private _wanted = createHashMapFromArray _ammo;
	private _carried = [];
	{
		if ((_x # 1) isEqualTo [0]) then {
			_carried pushBackUnique (_x # 0);
		};
	} forEach magazinesAllTurrets _vehicle;
	{
		private _magazine = _x;
		private _rounds = _wanted getOrDefault [[_magazine] call brmh_cmd_fnc_ammoWord, 0];
		private _size = getNumber (configFile >> "CfgMagazines" >> _magazine >> "count");
		_vehicle removeMagazinesTurret [_magazine, [0]];
		while {
			_rounds > 0 and {
				_size > 0
			}
		} do {
			_vehicle addMagazineTurret [_magazine, [0], _rounds min _size];
			_rounds = _rounds - _size;
		};
		_wanted deleteAt ([_magazine] call brmh_cmd_fnc_ammoWord);
	} forEach _carried;
};

brmh_cmd_fnc_gunAmmo = {
	params ["_gun"];
	private _counts = createHashMap;
	{
		if ((_x # 1) isEqualTo [0]) then {
			private _word = [_x # 0] call brmh_cmd_fnc_ammoWord;
			if (_word isNotEqualTo "") then {
				_counts set [_word, (_counts getOrDefault [_word, 0]) + (_x # 2)];
			};
		};
	} forEach magazinesAllTurrets _gun;
	_counts toArray false
};

brmh_cmd_fnc_trackGun = {
	params ["_gun"];
	if (_gun getVariable ["brmh_cmd_tracked", false]) exitWith {};
	_gun setVariable ["brmh_cmd_tracked", true];
	_gun addEventHandler ["Fired", {
		params ["_gun", "", "", "", "_ammo", "", "_shell"];
		private _mission = _gun getVariable ["brmh_cmd_mission", createHashMap];
		if (count _mission > 0) then {
			_mission set ["fired", (_mission getOrDefault ["fired", 0]) + 1];
			_mission set ["inAir", (_mission getOrDefault ["inAir", 0]) + 1];
			_mission set ["lastShot", time];
			if ((_mission getOrDefault ["state", ""]) isEqualTo "holding") then {
				_mission set ["state", "firing"];
			};
		};
		_shell setVariable ["brmh_cmd_from", [_gun getVariable ["brmh_cmd_key", ""], _mission getOrDefault ["order", ""], side group gunner _gun]];
		_shell setVariable ["brmh_cmd_mission", _mission];
		_shell addEventHandler ["Explode", {
			params ["_shell", "_pos"];
			private _mission = _shell getVariable ["brmh_cmd_mission", createHashMap];
			if (count _mission > 0) then {
				_mission set ["inAir", ((_mission getOrDefault ["inAir", 1]) - 1) max 0];
			};
			(_shell getVariable ["brmh_cmd_from", ["", "", sideUnknown]]) params ["_key", "_order", "_side"];
			["evt", createHashMapFromArray [
				["type", "cmd_impact"],
				["gun", _key],
				["order", _order],
				["side", str _side],
				["ammo", typeOf _shell],
				["pos", [_pos # 0, _pos # 1]],
				["heard", [_pos] call brmh_cmd_fnc_whoHeard]
			]] call BRMH_fnc_emit;
		}];
	}];
};

// How far an impact was from each station's nearest man, and whether it could see it land. It has to be right then,
// because dust and smoke hide the next one for free. Rows are [callsign, metres, dx, dy, seen].
brmh_cmd_fnc_whoHeard = {
	params ["_pos"];
	private _ground = [_pos # 0, _pos # 1];
	private _point = _pos vectorAdd [0, 0, 1];
	private _rows = [];
	{
		private _alive = (units _y) select {
			[_x] call brmh_cmd_fnc_able
		};
		if (_alive isNotEqualTo []) then {
			private _near = [_alive, [], {
				_x distance2D _ground
			}] call BIS_fnc_sortBy;
			private _from = getPosATL (_near # 0);
			private _metres = (_near # 0) distance2D _ground;
			private _seen = _metres < 1500 and {
				[_near select [0, 4], objNull, _point] call brmh_cmd_fnc_canSee
			};
			_rows pushBack [_x, _metres, (_ground # 0) - (_from # 0), (_ground # 1) - (_from # 1), _seen];
		};
	} forEach brmh_cmd_stations;
	_rows
};

brmh_cmd_fnc_gunsOf = {
	params ["_group", "_keys"];
	if (_keys isNotEqualTo []) exitWith {
		_keys apply {
			brmh_cmd_vehicles getOrDefault [_x, objNull]
		}
	};
	private _guns = [];
	{
		private _vehicle = vehicle _x;
		if (_vehicle isNotEqualTo _x and {
			gunner _vehicle isEqualTo _x
		} and {
			getNumber (configOf _vehicle >> "artilleryScanner") > 0
		}) then {
			_guns pushBackUnique _vehicle;
		};
	} forEach units _group;
	_guns
};

brmh_cmd_fnc_fireChunk = {
	params ["_mission"];
	private _gun = _mission get "gun";
	private _aim = _mission get "aim";
	private _left = (_mission get "want") - (_mission getOrDefault ["fired", 0]);
	private _radius = _mission get "radius";
	// A spread is one round to a point. A mission can't outrun its magazine, so the step sends the rest.
	private _at = if (_radius > 0) then {
		_aim getPos [random _radius, random 360]
	} else {
		_aim
	};
	_gun doArtilleryFire [_at, _mission get "mag", [_left, 1] select (_radius > 0)];
	_mission set ["issued", time];
	_mission set ["firedAtIssue", _mission getOrDefault ["fired", 0]];
};

// switchMove only changes the machine it runs on. On the server alone, the body stayed on the ground for anyone watching,
// and the server's own state said all was well.
brmh_cmd_fnc_carryPose = {
	params ["_unit", "_animation"];
	[_unit, _animation] remoteExec ["switchMove", 0];
};

/*
	NAME: brmh_cmd_fnc_startCarry
	DESCRIPTION: Sends a medic to pick up a downed man and carry him somewhere. An AI can't walk in ACE's carrying state, so
		a hidden dummy does the walking, with the medic attached to it. The idea is Antistasi's, for a drag. If the dummy
		stops getting anywhere and the place isn't far, the medic stays where he is, works on the man for a while, and the
		man is then put there directly, so a bad spot can't leave a medic stuck.
	PARAMETERS:
		0 - Medic (OBJECT)
		1 - Casualty (OBJECT)
		2 - Where to: a position, or a vehicle to load him into (ARRAY or OBJECT)
	RETURNS: The carry (HASHMAP). "state" ends as "done", and "result" says how
	ENVIRONMENT: Server
*/
brmh_cmd_fnc_startCarry = {
	params ["_medic", "_casualty", "_to", ["_group", grpNull], ["_order", ""]];
	private _carry = createHashMapFromArray [["group", _group], ["order", _order], ["medic", _medic], ["casualty", _casualty], ["to", _to], ["state", "going"], ["since", time], ["tries", 0], ["result", ""], ["moved", time], ["last", getPosATL _medic]];
	{
		_x forceSpeed -1;
	} forEach [_medic, _casualty];
	_medic setVariable ["brmh_cmd_busy", true];
	_casualty setVariable ["brmh_cmd_handled", "carried"];
	[_carry] call brmh_cmd_fnc_carryApproach;
	brmh_cmd_carries pushBack _carry;
	if (isNil "brmh_cmd_carryPfh") then {
		brmh_cmd_carryPfh = [{
			call brmh_cmd_fnc_stepCarries
		}, 0.5] call CBA_fnc_addPerFrameHandler;
	};
	_carry
};

brmh_cmd_fnc_carryPlace = {
	params ["_carry"];
	private _to = _carry get "to";
	if (_to isEqualType objNull) then {
		getPosATL _to
	} else {
		_to
	}
};

/*
	Where to send someone who has to reach a downed man, best first. The pathfinder often can't get to him. With a body at
	some spots in a house, nowhere in or right beside that house can be planned to, though it's fine with the body elsewhere,
	and open ground is fine either way. A man told to go there stands still for 12 s, then reports himself ready. So: the
	nearest position of the house at his level, the man himself, then a ring clear of the house, nearest the rescuer first.
*/
brmh_cmd_fnc_nearBody = {
	params ["_body", "_from"];
	private _at = getPosATL _body;
	private _level = ((nearestObject [_body, "House"]) buildingPos -1) select {
		(_x distance _at) < 6 and {
			abs ((_x # 2) - (_at # 2)) < 1.5
		}
	};
	_level = _level apply {
		[_x distance _at, _x]
	};
	_level sort true;
	// 14 m wasn't enough from the middle of the largest house here, and 26 m was.
	private _clear = [12, 25] select (_level isNotEqualTo []);
	private _ring = [0, 45, 90, 135, 180, 225, 270, 315] apply {
		private _spot = _at getPos [_clear, _x];
		[_spot distance2D _from, [_spot # 0, _spot # 1, 0]]
	};
	_ring sort true;
	((_level select [0, 1]) apply {
		_x # 1
	}) + [_at] + (_ring apply {
		_x # 1
	})
};

// Tries the next place. False when they've all been tried.
brmh_cmd_fnc_carryApproach = {
	params ["_carry"];
	private _tries = _carry get "tries";
	private _spots = [_carry get "casualty", getPosATL (_carry get "medic")] call brmh_cmd_fnc_nearBody;
	if (_tries >= count _spots) exitWith {
		false
	};
	(_carry get "medic") doMove (_spots # _tries);
	_carry set ["tries", _tries + 1];
	_carry set ["ordered", time];
	_carry set ["moved", time];
	true
};

brmh_cmd_fnc_carryStartLift = {
	params ["_carry"];
	private _medic = _carry get "medic";
	doStop _medic;
	_medic selectWeapon primaryWeapon _medic;
	_medic playMoveNow "AcinPknlMstpSnonWnonDnon_AcinPercMrunSnonWnonDnon";
	[_carry get "casualty", "AinjPfalMstpSnonWrflDnon_carried_Up"] call brmh_cmd_fnc_carryPose;
	_carry set ["state", "lifting"];
	_carry set ["since", time];
};

brmh_cmd_fnc_carryLift = {
	params ["_carry"];
	private _medic = _carry get "medic";
	private _casualty = _carry get "casualty";
	private _group = createGroup [civilian, true];
	private _dummy = _group createUnit ["C_man_polo_1_F", [0, 0, 20], [], 0, "FORM"];
	_dummy forceWalk true;
	hideObjectGlobal _dummy;
	_dummy allowDamage false;
	_dummy setCaptive true;
	_dummy setBehaviour "CARELESS";
	{
		_dummy disableAI _x;
	} forEach ["FSM", "SUPPRESSION", "AUTOTARGET", "TARGET"];
	_dummy setPosATL (getPosATL _medic);
	_dummy setDir (_medic getDir ([_carry] call brmh_cmd_fnc_carryPlace));
	_medic disableAI "ANIM";
	_medic attachTo [_dummy, [0, 0, 0]];
	_medic setDir 0;
	_casualty attachTo [_medic, [0.4, -0.1, -1.25], "LeftShoulder"];
	_casualty setDir 195;
	[_casualty, "AinjPfalMstpSnonWnonDf_carried_dead"] call brmh_cmd_fnc_carryPose;
	_dummy doMove ([_carry] call brmh_cmd_fnc_carryPlace);
	_medic playMove "AcinPercMrunSnonWnonDf";
	_carry set ["dummy", _dummy];
	_carry set ["moved", time];
	_carry set ["last", getPosATL _dummy];
};

// Lets go of him here, whatever's happened. Safe to call before he's been picked up.
brmh_cmd_fnc_carryRelease = {
	params ["_carry"];
	private _medic = _carry get "medic";
	private _casualty = _carry get "casualty";
	private _dummy = _carry getOrDefault ["dummy", objNull];
	if (not isNull attachedTo _casualty) then {
		detach _casualty;
		_casualty setPosATL (getPosATL _medic);
	};
	if (alive _casualty and {
		lifeState _casualty isEqualTo "INCAPACITATED"
	}) then {
		[_casualty, "UnconsciousReviveDefault"] call brmh_cmd_fnc_carryPose;
	};
	if (not isNull _dummy) then {
		detach _medic;
		deleteVehicle _dummy;
		_carry deleteAt "dummy";
	};
	if (alive _medic) then {
		_medic enableAI "ANIM";
		if (lifeState _medic isNotEqualTo "INCAPACITATED") then {
			[_medic, "AmovPknlMstpSrasWrflDnon"] call brmh_cmd_fnc_carryPose;
		};
	};
};

brmh_cmd_fnc_carryFinish = {
	params ["_carry", "_result"];
	private _medic = _carry get "medic";
	[_carry] call brmh_cmd_fnc_carryRelease;
	if ([_medic] call brmh_cmd_fnc_able) then {
		_medic doFollow leader group _medic;
	};
	_medic setVariable ["brmh_cmd_busy", nil];
	(_carry get "casualty") setVariable ["brmh_cmd_handled", nil];
	_carry set ["state", "done"];
	_carry set ["result", _result];
	[_carry get "group", _carry get "order", "carry", _carry get "casualty", _result] call brmh_cmd_fnc_careSay;
};

// A vehicle, or the place. The man's either loaded, or laid down there.
brmh_cmd_fnc_carryDeliver = {
	params ["_carry", "_how"];
	private _to = _carry get "to";
	private _casualty = _carry get "casualty";
	private _medic = _carry get "medic";
	[_carry] call brmh_cmd_fnc_carryRelease;
	if (_to isEqualType objNull) then {
		[_casualty, _to] call brmh_cmd_fnc_loadMan;
		_carry set ["state", "loading"];
		_carry set ["since", time];
		_carry set ["how", _how];
	} else {
		if (_how isEqualTo "placed") then {
			_casualty setPosATL _to;
		};
		[_carry, _how] call brmh_cmd_fnc_carryFinish;
	};
};

brmh_cmd_fnc_stepCarries = {
	{
		private _carry = _x;
		private _medic = _carry get "medic";
		private _casualty = _carry get "casualty";
		private _state = _carry get "state";
		private _in = time - (_carry get "since");
		switch (true) do {
			case (not alive _medic or {
				lifeState _medic isEqualTo "INCAPACITATED"
			}): {
				[_carry, "medic down"] call brmh_cmd_fnc_carryFinish;
			};
			case (not alive _casualty): {
				[_carry, "he died"] call brmh_cmd_fnc_carryFinish;
			};
			case (lifeState _casualty isNotEqualTo "INCAPACITATED"): {
				[_carry, "he woke"] call brmh_cmd_fnc_carryFinish;
			};
			case (_state isEqualTo "going"): {
				private _away = _medic distance _casualty;
				private _ready = unitReady _medic and {
					(time - (_carry get "ordered")) >= 3
				};
				// A house position can stop him a few metres short, through a wall or not. He snaps the man to him when he lifts.
				if (_away <= 2.5 or {
					_ready and {
						_away <= 8
					}
				}) exitWith {
					[_carry] call brmh_cmd_fnc_carryStartLift;
				};
				// As close as he can get. The owner's way: he works for a while, and the man is then with him.
				if (_ready and {
					_away <= 35
				}) exitWith {
					[_medic, "AinvPknlMstpSlayWrflDnon_medicOther"] call brmh_cmd_fnc_carryPose;
					_carry set ["state", "fetching"];
					_carry set ["since", time];
				};
				if ((_medic distance2D (_carry get "last")) >= 1) then {
					_carry set ["last", getPosATL _medic];
					_carry set ["moved", time];
				};
				if (_ready or {
					(time - (_carry get "moved")) >= 20
				}) then {
					if (not ([_carry] call brmh_cmd_fnc_carryApproach)) then {
						[_carry, "can't reach him"] call brmh_cmd_fnc_carryFinish;
					};
				};
			};
			case (_state isEqualTo "fetching"): {
				if (_in >= 8) then {
					_casualty setPosATL (_medic getPos [1.2, getDir _medic]);
					[_casualty, "UnconsciousReviveDefault"] call brmh_cmd_fnc_carryPose;
					[_medic, "AmovPercMstpSrasWrflDnon"] call brmh_cmd_fnc_carryPose;
					[_carry] call brmh_cmd_fnc_carryStartLift;
				};
			};
			case (_state isEqualTo "lifting"): {
				if (_in >= 9) then {
					[_carry] call brmh_cmd_fnc_carryLift;
					_carry set ["state", "carrying"];
					_carry set ["since", time];
					[_carry get "group", _carry get "order", "carry", _casualty, "carrying"] call brmh_cmd_fnc_careSay;
				};
			};
			case (_state isEqualTo "carrying"): {
				private _dummy = _carry get "dummy";
				private _place = [_carry] call brmh_cmd_fnc_carryPlace;
				private _left = _dummy distance2D _place;
				// A vehicle's own bulk stops the dummy short of its middle
				if (_left <= ([5, 8] select ((_carry get "to") isEqualType objNull))) exitWith {
					[_carry, "carried"] call brmh_cmd_fnc_carryDeliver;
				};
				if ((_dummy distance2D (_carry get "last")) >= 1) then {
					_carry set ["last", getPosATL _dummy];
					_carry set ["moved", time];
				};
				if ((time - (_carry get "moved")) >= 8) exitWith {
					// Not far: the owner's way, of working on him a while and then putting him there
					if (_left <= 60) then {
						[_carry] call brmh_cmd_fnc_carryRelease;
						_medic disableAI "ANIM";
						[_medic, "AinvPknlMstpSlayWrflDnon_medicOther"] call brmh_cmd_fnc_carryPose;
						_carry set ["state", "working"];
						_carry set ["since", time];
					} else {
						[_carry, "stuck"] call brmh_cmd_fnc_carryFinish;
					};
				};
			};
			case (_state isEqualTo "working"): {
				if (_in >= 8) then {
					[_carry, "placed"] call brmh_cmd_fnc_carryDeliver;
				};
			};
			case (_state isEqualTo "loading"): {
				private _to = _carry get "to";
				if (vehicle _casualty isEqualTo _to) exitWith {
					[_carry, ["loaded", "loaded directly"] select ((_carry get "how") isEqualTo "placed")] call brmh_cmd_fnc_carryFinish;
				};
				if (_in >= 5) exitWith {
					[_carry, "couldn't load him"] call brmh_cmd_fnc_carryFinish;
				};
			};
		};
	} forEach brmh_cmd_carries;
	brmh_cmd_carries = brmh_cmd_carries select {
		(_x get "state") isNotEqualTo "done"
	};
	if (brmh_cmd_carries isEqualTo [] and {
		not isNil "brmh_cmd_carryPfh"
	}) then {
		[brmh_cmd_carryPfh] call CBA_fnc_removePerFrameHandler;
		brmh_cmd_carryPfh = nil;
	};
};

// A radio line for the host to word. One row for each man, job and order, whatever its latest state is.
brmh_cmd_fnc_careSay = {
	params ["_group", "_order", "_kind", "_man", "_state", ["_detail", ""]];
	if (isNull _group) exitWith {};
	private _key = if (_man isEqualType objNull) then {
		if (isNull _man) then {
			""
		} else {
			[_man] call brmh_cmd_fnc_manKey
		}
	} else {
		_man
	};
	private _name = if (_man isEqualType objNull and {
		not isNull _man
	}) then {
		name _man
	} else {
		""
	};
	private _rows = _group getVariable ["brmh_cmd_care", []];
	private _at = _rows findIf {
		(_x # 0) isEqualTo _order and {
			(_x # 1) isEqualTo _kind
		} and {
			(_x # 2) isEqualTo _key
		}
	};
	private _row = [_order, _kind, _key, _name, _state, _detail];
	if (_at < 0) then {
		_rows pushBack _row;
	} else {
		_rows set [_at, _row];
	};
	_group setVariable ["brmh_cmd_care", _rows select [(count _rows - 40) max 0, 40]];
};

// ACE's own loading moves a man to a new group if the vehicle is empty, and he'd vanish from his squad until unloaded.
brmh_cmd_fnc_loadMan = {
	params ["_man", "_vehicle"];
	private _seats = (fullCrew [_vehicle, "cargo", true]) select {
		isNull (_x # 0)
	};
	if (_seats isEqualTo []) exitWith {
		false
	};
	_man assignAsCargoIndex [_vehicle, _seats # 0 # 2];
	_man moveInCargo [_vehicle, _seats # 0 # 2];
	true
};

brmh_cmd_fnc_targets = {
	params ["_rows"];
	(_rows apply {
		brmh_cmd_men getOrDefault [_x # 0, objNull]
	}) select {
		not isNull _x
	}
};

/*
	NAME: brmh_cmd_fnc_carryOrder
	DESCRIPTION: A squad's free men each pick up a downed man, and carry him to a place or into a vehicle. The rest of the
		squad carries on with its orders. With no list, it's everyone down within 100 m.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Order id (STRING)
		2 - Who: [[man key, place], ...] (ARRAY)
		3 - To: a position, or a vehicle's key (ARRAY or STRING)
	ENVIRONMENT: Server
*/
brmh_cmd_fnc_carryOrder = {
	params ["_group", "_order", "_who", "_to"];
	private _target = if (_to isEqualType "") then {
		brmh_cmd_vehicles getOrDefault [_to, objNull]
	} else {
		_to
	};
	if (_target isEqualType objNull and {
		isNull _target or {
			not alive _target
		}
	}) exitWith {
		[_group, _order, "carry", objNull, "wrecked", _to] call brmh_cmd_fnc_careSay;
	};
	// A post isn't something to get into: it's somewhere to put him down.
	if (_target isEqualType objNull and {
		_target in brmh_cmd_posts
	}) then {
		_target = getPosATL _target;
	};
	private _men = [_who] call brmh_cmd_fnc_targets;
	if (_who isEqualTo []) then {
		_men = (brmh_cmd_down + ((units _group) select {
			alive _x and {
				not ([_x] call brmh_cmd_fnc_able)
			}
		})) arrayIntersect (brmh_cmd_down + units _group);
		_men = _men select {
			(_x distance2D leader _group) < 100
		};
	};
	if (_men isEqualTo []) exitWith {
		[_group, _order, "carry", objNull, "nobody down"] call brmh_cmd_fnc_careSay;
	};
	private _bearers = (units _group) select {
		[_x] call brmh_cmd_fnc_able and {
			vehicle _x isEqualTo _x
		} and {
			not (_x getVariable ["brmh_cmd_busy", false])
		}
	};
	{
		private _man = _x;
		switch (true) do {
			case (not alive _man): {
				[_group, _order, "carry", _man, "he died"] call brmh_cmd_fnc_careSay;
			};
			case ([_man] call brmh_cmd_fnc_able): {
				[_group, _order, "carry", _man, "he woke"] call brmh_cmd_fnc_careSay;
			};
			case (vehicle _man isNotEqualTo _man): {
				[_group, _order, "carry", _man, "aboard", (vehicle _man) getVariable ["brmh_cmd_key", ""]] call brmh_cmd_fnc_careSay;
			};
			case ((_man getVariable ["brmh_cmd_handled", ""]) isNotEqualTo ""): {
				[_group, _order, "carry", _man, "already"] call brmh_cmd_fnc_careSay;
			};
			case (_bearers isEqualTo []): {
				[_group, _order, "carry", _man, "no bearer"] call brmh_cmd_fnc_careSay;
			};
			default {
				private _nearest = [_bearers, [_man], {
					// The leader last: the squad's orders go through him.
					(_x distance _input0) + ([0, 1000] select (_x isEqualTo leader group _x))
				}] call BIS_fnc_sortBy;
				private _bearer = _nearest # 0;
				_bearers = _bearers - [_bearer];
				[_group, _order, "carry", _man, "going"] call brmh_cmd_fnc_careSay;
				[_bearer, _man, _target, _group, _order] call brmh_cmd_fnc_startCarry;
			};
		};
	} forEach _men;
};

/*
	NAME: brmh_cmd_fnc_unloadOrder
	DESCRIPTION: Takes downed men out of a stopped vehicle, by a squad that has someone there.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Order id (STRING)
		2 - Who: [[man key, place], ...], or nobody for all of them (ARRAY)
		3 - Vehicle's key (STRING)
	ENVIRONMENT: Server
*/
brmh_cmd_fnc_unloadOrder = {
	params ["_group", "_order", "_who", "_key"];
	private _vehicle = brmh_cmd_vehicles getOrDefault [_key, objNull];
	if (isNull _vehicle or {
		not alive _vehicle
	}) exitWith {
		[_group, _order, "unload", objNull, "wrecked", _key] call brmh_cmd_fnc_careSay;
	};
	if ((abs speed _vehicle) > 1) exitWith {
		[_group, _order, "unload", objNull, "moving", _key] call brmh_cmd_fnc_careSay;
	};
	if (((units _group) findIf {
		[_x] call brmh_cmd_fnc_able and {
			(_x distance2D _vehicle) < 25
		}
	}) < 0) exitWith {
		[_group, _order, "unload", objNull, "nobody there", _key] call brmh_cmd_fnc_careSay;
	};
	private _aboard = (crew _vehicle) select {
		alive _x and {
			not ([_x] call brmh_cmd_fnc_able)
		}
	};
	private _men = if (_who isEqualTo []) then {
		_aboard
	} else {
		[_who] call brmh_cmd_fnc_targets
	};
	if (_men isEqualTo []) exitWith {
		[_group, _order, "unload", objNull, "nobody aboard", _key] call brmh_cmd_fnc_careSay;
	};
	{
		if (_x in _aboard) then {
			[_x] call ace_common_fnc_unloadPerson;
			[{
				params ["_man", "_group", "_order", "_key"];
				if (alive _man and {
					not ([_man] call brmh_cmd_fnc_able)
				}) then {
					[_man, "UnconsciousReviveDefault"] call brmh_cmd_fnc_carryPose;
				};
				[_group, _order, "unload", _man, ["stuck", "off"] select (vehicle _man isEqualTo _man), _key] call brmh_cmd_fnc_careSay;
			}, [_x, _group, _order, _key], 3] call CBA_fnc_waitAndExecute;
		} else {
			[_group, _order, "unload", _x, "not aboard", _key] call brmh_cmd_fnc_careSay;
		};
	} forEach _men;
};

// A medical vehicle or an aid post close enough to make a difference. ACE itself makes no treatment faster for being in one.
brmh_cmd_fnc_atFacility = {
	params ["_man"];
	private _inside = vehicle _man;
	if (_inside isNotEqualTo _man and {
		[_inside] call brmh_cmd_fnc_isMedicalVehicle
	}) exitWith {
		true
	};
	(brmh_cmd_posts findIf {
		alive _x and {
			(_x distance2D _man) < 30
		}
	}) >= 0 or {
		(((_man nearEntities [["Car", "Tank", "Air"], 15]) findIf {
			alive _x and {
				[_x] call brmh_cmd_fnc_isMedicalVehicle
			}
		}) >= 0)
	}
};

brmh_cmd_fnc_isMedicalVehicle = {
	params ["_vehicle"];
	_vehicle getVariable ["ace_medical_isMedicalVehicle", getNumber (configOf _vehicle >> "attendant") > 0]
};

brmh_cmd_fnc_isMedic = {
	params ["_man"];
	(_man getVariable ["ace_medical_medicClass", parseNumber (_man getUnitTrait "medic")]) > 0
};

/*
	NAME: brmh_cmd_fnc_treatOrder
	DESCRIPTION: A station's medics go to downed men, one at a time each, and treat them. The time depends on where the man
		is: see brmh_cmd_careTimes. Early on it stops him dying, and at the end he gets up.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Order id (STRING)
		2 - Who: [[man key, place], ...], or nobody for everyone down within 100 m (ARRAY)
	ENVIRONMENT: Server
*/
brmh_cmd_fnc_treatOrder = {
	params ["_group", "_order", "_who"];
	private _medics = (units _group) select {
		[_x] call brmh_cmd_fnc_able and {
			[_x] call brmh_cmd_fnc_isMedic
		}
	};
	if (_medics isEqualTo []) exitWith {
		[_group, _order, "treat", objNull, "no medic"] call brmh_cmd_fnc_careSay;
	};
	private _men = [_who] call brmh_cmd_fnc_targets;
	if (_who isEqualTo []) then {
		_men = brmh_cmd_down select {
			alive _x and {
				(_x distance2D leader _group) < 100
			}
		};
	};
	if (_men isEqualTo []) exitWith {
		[_group, _order, "treat", objNull, "nobody down"] call brmh_cmd_fnc_careSay;
	};
	private _queue = [];
	{
		private _man = _x;
		private _places = _who select {
			(_x # 0) isEqualTo ([_man] call brmh_cmd_fnc_manKey)
		};
		switch (true) do {
			case (not alive _man): {
				[_group, _order, "treat", _man, "he died"] call brmh_cmd_fnc_careSay;
			};
			case ([_man] call brmh_cmd_fnc_able): {
				[_group, _order, "treat", _man, "up"] call brmh_cmd_fnc_careSay;
			};
			case (vehicle _man isNotEqualTo _man and {
				not ([vehicle _man] call brmh_cmd_fnc_isMedicalVehicle)
			}): {
				[_group, _order, "treat", _man, "aboard", (vehicle _man) getVariable ["brmh_cmd_key", ""]] call brmh_cmd_fnc_careSay;
			};
			// Sent to where he was last reported. If he isn't anywhere near it, they won't find him.
			case (_places isNotEqualTo [] and {
				(_man distance2D ((_places # 0) # 1)) > 150
			}): {
				[_group, _order, "treat", _man, "can't find"] call brmh_cmd_fnc_careSay;
			};
			default {
				_queue pushBack _man;
			};
		};
	} forEach _men;
	if (_queue isEqualTo []) exitWith {};
	brmh_cmd_treats pushBack (createHashMapFromArray [["group", _group], ["order", _order], ["queue", _queue], ["jobs", []]]);
};

brmh_cmd_fnc_stepTreats = {
	{
		private _treat = _x;
		private _group = _treat get "group";
		private _order = _treat get "order";
		private _queue = _treat get "queue";
		// A finished job frees a medic for the next man in the queue.
		private _jobs = (_treat get "jobs") select {
			private _job = _x;
			private _medic = _job get "medic";
			private _man = _job get "casualty";
			private _left = true;
			switch (true) do {
				case (not ([_medic] call brmh_cmd_fnc_able)): {
					[_group, _order, "treat", _man, "medic down"] call brmh_cmd_fnc_careSay;
					[_job] call brmh_cmd_fnc_treatRelease;
					_queue pushBack _man;
					_left = false;
				};
				case (not alive _man): {
					[_group, _order, "treat", _man, "he died"] call brmh_cmd_fnc_careSay;
					[_job] call brmh_cmd_fnc_treatRelease;
					_left = false;
				};
				case ((_job get "state") isEqualTo "going"): {
					_left = [_job, _group, _order] call brmh_cmd_fnc_treatGo;
				};
				default {
					_left = [_job, _group, _order] call brmh_cmd_fnc_treatWork;
				};
			};
			_left
		};
		_treat set ["jobs", _jobs];
		private _free = (units _group) select {
			[_x] call brmh_cmd_fnc_able and {
				[_x] call brmh_cmd_fnc_isMedic
			} and {
				not (_x getVariable ["brmh_cmd_busy", false])
			}
		};
		_queue = _queue select {
			alive _x and {
				not ([_x] call brmh_cmd_fnc_able)
			}
		};
		while {
			_free isNotEqualTo [] and {
				_queue isNotEqualTo []
			}
		} do {
			private _medic = _free deleteAt 0;
			private _man = _queue deleteAt 0;
			private _job = createHashMapFromArray [["medic", _medic], ["casualty", _man], ["state", "going"], ["tries", 0], ["last", getPosATL _medic], ["moved", time], ["ordered", time], ["since", time]];
			_medic setVariable ["brmh_cmd_busy", true];
			_man setVariable ["brmh_cmd_handled", "treated"];
			if (vehicle _medic isNotEqualTo _medic) then {
				[_medic] call brmh_cmd_fnc_getOff;
			};
			[_job] call brmh_cmd_fnc_treatApproach;
			_jobs pushBack _job;
			[_group, _order, "treat", _man, "going"] call brmh_cmd_fnc_careSay;
		};
		_treat set ["queue", _queue];
		_treat set ["jobs", _jobs];
	} forEach brmh_cmd_treats;
	brmh_cmd_treats = brmh_cmd_treats select {
		(_x get "jobs") isNotEqualTo [] or {
			(_x get "queue") isNotEqualTo []
		}
	};
};

brmh_cmd_fnc_treatRelease = {
	params ["_job"];
	private _medic = _job get "medic";
	_medic setVariable ["brmh_cmd_busy", nil];
	(_job get "casualty") setVariable ["brmh_cmd_handled", nil];
	if ([_medic] call brmh_cmd_fnc_able) then {
		_medic enableAI "ANIM";
		[_medic, "AmovPknlMstpSrasWrflDnon"] call brmh_cmd_fnc_carryPose;
		_medic doFollow leader group _medic;
	};
};

brmh_cmd_fnc_treatApproach = {
	params ["_job"];
	private _man = _job get "casualty";
	private _medic = _job get "medic";
	private _tries = _job get "tries";
	if (vehicle _man isNotEqualTo _man) exitWith {
		_medic doMove ((vehicle _man) getPos [4, random 360]);
		_job set ["tries", _tries + 1];
		_job set ["ordered", time];
		_job set ["moved", time];
		_tries < 4
	};
	private _spots = [_man, getPosATL _medic] call brmh_cmd_fnc_nearBody;
	if (_tries >= count _spots) exitWith {
		false
	};
	_medic doMove (_spots # _tries);
	_job set ["tries", _tries + 1];
	_job set ["ordered", time];
	_job set ["moved", time];
	true
};

// True while he's still getting there, or starts working.
brmh_cmd_fnc_treatGo = {
	params ["_job", "_group", "_order"];
	private _medic = _job get "medic";
	private _man = _job get "casualty";
	private _away = _medic distance (vehicle _man);
	private _aboard = vehicle _man isNotEqualTo _man;
	private _ready = unitReady _medic and {
		(time - (_job get "ordered")) >= 3
	};
	if (_away <= ([3, 8] select _aboard) or {
		_ready and {
			_away <= 8
		}
	}) exitWith {
		[_job, _group, _order] call brmh_cmd_fnc_treatStart;
		true
	};
	if (not _aboard and {
		_ready
	} and {
		_away <= 35
	}) exitWith {
		// As with a carry: as close as he can get. He works for a while, and the man is then with him.
		_man setPosATL (_medic getPos [1.2, getDir _medic]);
		[_man, "UnconsciousReviveDefault"] call brmh_cmd_fnc_carryPose;
		[_job, _group, _order] call brmh_cmd_fnc_treatStart;
		true
	};
	if ((_medic distance2D (_job get "last")) >= 1) then {
		_job set ["last", getPosATL _medic];
		_job set ["moved", time];
	};
	if (_ready or {
		(time - (_job get "moved")) >= 20
	}) exitWith {
		if ([_job] call brmh_cmd_fnc_treatApproach) then {
			true
		} else {
			[_group, _order, "treat", _man, "can't reach"] call brmh_cmd_fnc_careSay;
			[_job] call brmh_cmd_fnc_treatRelease;
			false
		}
	};
	true
};

brmh_cmd_fnc_treatStart = {
	params ["_job", "_group", "_order"];
	private _medic = _job get "medic";
	private _man = _job get "casualty";
	private _fast = [_man] call brmh_cmd_fnc_atFacility;
	private _need = brmh_cmd_careTimes get (["field_s", "facility_s"] select _fast);
	doStop _medic;
	_medic setDir (_medic getDir _man);
	_medic disableAI "ANIM";
	[_medic, "AinvPknlMstpSlayWrflDnon_medicOther"] call brmh_cmd_fnc_carryPose;
	_job set ["state", "working"];
	_job set ["since", time];
	_job set ["need", _need];
	_job set ["stable", false];
	_job set ["anim", time];
	[_group, _order, "treat", _man, "treating", ["field", "facility"] select _fast] call brmh_cmd_fnc_careSay;
};

// False when it's over.
brmh_cmd_fnc_treatWork = {
	params ["_job", "_group", "_order"];
	private _medic = _job get "medic";
	private _man = _job get "casualty";
	private _in = time - (_job get "since");
	private _need = _job get "need";
	if ([_man] call brmh_cmd_fnc_able) exitWith {
		[_group, _order, "treat", _man, "up"] call brmh_cmd_fnc_careSay;
		[_job] call brmh_cmd_fnc_treatRelease;
		false
	};
	if (_in >= _need) exitWith {
		[_man] call ace_medical_fnc_fullHeal;
		[_man, _group] call brmh_cmd_fnc_treated;
		[_group, _order, "treat", _man, "up"] call brmh_cmd_fnc_careSay;
		[_job] call brmh_cmd_fnc_treatRelease;
		false
	};
	// He stops getting worse once they've got to work on him. It's the same as ACE's own treatments, without the items.
	if (not (_job get "stable") and {
		_in >= (5 min (_need / 2))
	}) then {
		_job set ["stable", true];
		_man setVariable ["ace_medical_openWounds", createHashMap, true];
		_man setVariable ["ace_medical_woundBleeding", 0, true];
		_man setVariable ["ace_medical_bloodVolume", (_man getVariable ["ace_medical_bloodVolume", 6]) max 4.5, true];
		if (_man getVariable ["ace_medical_inCardiacArrest", false]) then {
			["ace_medical_CPRSucceeded", _man] call CBA_fnc_localEvent;
		};
	};
	if ((time - (_job get "anim")) >= 8) then {
		_job set ["anim", time];
		[_medic, "AinvPknlMstpSlayWrflDnon_medicOther"] call brmh_cmd_fnc_carryPose;
	};
	true
};

// If he's nobody left to go back to, he stays with whoever saved him.
brmh_cmd_fnc_treated = {
	params ["_man", "_rescuers"];
	private _home = group _man;
	if (_home isEqualTo _rescuers) exitWith {};
	if ((((units _home) - [_man]) findIf {
		[_x] call brmh_cmd_fnc_able
	}) < 0) then {
		[_man] joinSilent _rescuers;
		_rescuers setVariable ["brmh_cmd_baseline", (_rescuers getVariable ["brmh_cmd_baseline", 0]) + 1];
		[_rescuers, "", "joined", _man, "joined"] call brmh_cmd_fnc_careSay;
	};
};

/*
	NAME: brmh_cmd_fnc_postOrder
	DESCRIPTION: A medic goes to a place and sets up an aid post, a real tent that can be destroyed. One per station.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Order id (STRING)
		2 - Position (ARRAY)
	ENVIRONMENT: Server
*/
brmh_cmd_fnc_postOrder = {
	params ["_group", "_order", "_at"];
	if (alive (_group getVariable ["brmh_cmd_post", objNull])) exitWith {
		[_group, _order, "post", "post", "have one"] call brmh_cmd_fnc_careSay;
	};
	private _medics = (units _group) select {
		[_x] call brmh_cmd_fnc_able and {
			[_x] call brmh_cmd_fnc_isMedic
		} and {
			not (_x getVariable ["brmh_cmd_busy", false])
		}
	};
	if (_medics isEqualTo []) exitWith {
		[_group, _order, "post", "post", "no medic"] call brmh_cmd_fnc_careSay;
	};
	private _medic = _medics # 0;
	_medic setVariable ["brmh_cmd_busy", true];
	if (vehicle _medic isNotEqualTo _medic) then {
		[_medic] call brmh_cmd_fnc_getOff;
	};
	_medic doMove _at;
	brmh_cmd_builds pushBack (createHashMapFromArray [["group", _group], ["order", _order], ["medic", _medic], ["at", _at], ["state", "going"], ["since", time], ["ordered", time]]);
	[_group, _order, "post", "post", "going"] call brmh_cmd_fnc_careSay;
};

brmh_cmd_fnc_stepBuilds = {
	brmh_cmd_builds = brmh_cmd_builds select {
		private _build = _x;
		private _group = _build get "group";
		private _order = _build get "order";
		private _medic = _build get "medic";
		private _keep = true;
		switch (true) do {
			case (not ([_medic] call brmh_cmd_fnc_able)): {
				[_group, _order, "post", "post", "medic down"] call brmh_cmd_fnc_careSay;
				_medic setVariable ["brmh_cmd_busy", nil];
				_keep = false;
			};
			case ((_build get "state") isEqualTo "going"): {
				private _away = _medic distance2D (_build get "at");
				if (_away <= 8 or {
					unitReady _medic and {
						(time - (_build get "ordered")) >= 3
					} and {
						_away <= 40
					}
				}) then {
					doStop _medic;
					_medic disableAI "ANIM";
					[_medic, "AinvPknlMstpSlayWrflDnon_medicOther"] call brmh_cmd_fnc_carryPose;
					_build set ["state", "building"];
					_build set ["since", time];
					[_group, _order, "post", "post", "building"] call brmh_cmd_fnc_careSay;
				} else {
					if (unitReady _medic and {
						(time - (_build get "ordered")) >= 3
					}) then {
						_medic setVariable ["brmh_cmd_busy", nil];
						[_group, _order, "post", "post", "can't reach"] call brmh_cmd_fnc_careSay;
						_keep = false;
					};
				};
			};
			default {
				if ((time - (_build get "since")) >= (brmh_cmd_careTimes get "build_s")) then {
					private _tent = createVehicle ["Land_MedicalTent_01_MTP_closed_F", _medic getPos [8, getDir _medic], [], 6, "NONE"];
					brmh_cmd_postCount = (missionNamespace getVariable ["brmh_cmd_postCount", 0]) + 1;
					private _key = format ["P%1", brmh_cmd_postCount];
					_tent setVariable ["brmh_cmd_key", _key];
					_tent setVariable ["ace_medical_isMedicalFacility", true, true];
					brmh_cmd_vehicles set [_key, _tent];
					brmh_cmd_posts pushBack _tent;
					_group setVariable ["brmh_cmd_post", _tent];
					_medic setVariable ["brmh_cmd_busy", nil];
					_medic enableAI "ANIM";
					[_medic, "AmovPknlMstpSrasWrflDnon"] call brmh_cmd_fnc_carryPose;
					_medic doFollow leader group _medic;
					[_group, _order, "post", "post", "up", [_key, mapGridPosition _tent]] call brmh_cmd_fnc_careSay;
					_keep = false;
				};
			};
		};
		_keep
	};
};

/*
	NAME: brmh_cmd_fnc_startFire
	DESCRIPTION: Starts a station's fire mission on its guns. Every way this can silently do nothing is checked first or
		watched for, and comes out in the packet as a state for the host to word.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Order id (STRING)
		2 - [gun keys, [x, y], "HE" or "SMOKE", rounds, radius] (ARRAY)
	ENVIRONMENT: Server
*/
brmh_cmd_fnc_startFire = {
	params ["_group", "_order", "_leg"];
	_leg params ["_keys", "_aim", "_word", "_want", "_radius"];
	private _guns = [_group, _keys] call brmh_cmd_fnc_gunsOf;
	private _missions = [];
	if (_guns isEqualTo []) then {
		_missions pushBack (createHashMapFromArray [["key", ""], ["order", _order], ["state", "unable"], ["reason", "no gun"], ["word", _word], ["want", _want]]);
	};
	{
		private _gun = _x;
		private _mission = createHashMapFromArray [["key", _gun getVariable ["brmh_cmd_key", ""]], ["order", _order], ["state", "unable"], ["word", _word], ["want", _want], ["fired", 0], ["inAir", 0], ["aim", (_aim select [0, 2]) + [0]], ["radius", _radius], ["gun", _gun]];
		_missions pushBack _mission;
		private _crew = gunner _gun;
		private _magazine = (getArtilleryAmmo [_gun]) param [(getArtilleryAmmo [_gun]) findIf {
			([_x] call brmh_cmd_fnc_ammoWord) isEqualTo _word
		}, ""];
		if (isNull _gun or {
			not alive _gun
		}) then {
			_mission set ["reason", "destroyed"];
			continue;
		};
		if (isNull _crew or {
			not alive _crew
		} or {
			group _crew isNotEqualTo _group
		}) then {
			_mission set ["reason", "no gunner"];
			continue;
		};
		if (_magazine isEqualTo "") then {
			_mission set ["reason", "no ammo"];
			continue;
		};
		if (not ((_mission get "aim") inRangeOfArtillery [[_gun], _magazine])) then {
			_mission set ["reason", "out of range"];
			continue;
		};
		[_gun] call brmh_cmd_fnc_trackGun;
		_mission set ["mag", _magazine];
		_mission set ["state", "firing"];
		_mission set ["eta", _gun getArtilleryETA [_mission get "aim", _magazine]];
		_gun setVariable ["brmh_cmd_mission", _mission];
		_gun doWatch (_mission get "aim");
		[_mission] call brmh_cmd_fnc_fireChunk;
		brmh_cmd_fireActive = brmh_cmd_fireActive select {
			(_x get "gun") isNotEqualTo _gun
		};
		brmh_cmd_fireActive pushBack _mission;
	} forEach _guns;
	private _kept = (_group getVariable ["brmh_cmd_missions", []]) select {
		private _key = _x get "key";
		(_missions findIf {
			(_x get "key") isEqualTo _key
		}) < 0
	};
	_group setVariable ["brmh_cmd_missions", _kept + _missions];
	if (isNil "brmh_cmd_firePfh" and {
		brmh_cmd_fireActive isNotEqualTo []
	}) then {
		brmh_cmd_firePfh = [{
			call brmh_cmd_fnc_stepFire
		}, 0.5] call CBA_fnc_addPerFrameHandler;
	};
};

brmh_cmd_fnc_stepFire = {
	{
		private _mission = _x;
		private _gun = _mission get "gun";
		private _crew = gunner _gun;
		private _fired = _mission getOrDefault ["fired", 0];
		private _finish = "";
		private _sinceShot = time - ((_mission getOrDefault ["lastShot", -1]) max (_mission get "issued"));
		switch (true) do {
			case (not alive _gun): {
				_finish = "destroyed";
			};
			case (isNull _crew or {
				not alive _crew
			}): {
				_finish = "gunner";
			};
			case (_fired >= (_mission get "want")): {
				_finish = "done";
			};
			case (unitReady _gun and {
				(time - (_mission get "issued")) >= 1
			}): {
				if (_fired > (_mission get "firedAtIssue")) then {
					// That order's rounds are away. If that's all this type has, it's out.
					if ((([_gun] call brmh_cmd_fnc_gunAmmo) findIf {
						(_x # 0) isEqualTo (_mission get "word") and {
							(_x # 1) > 0
						}
					}) < 0) then {
						_finish = "out";
					} else {
						[_mission] call brmh_cmd_fnc_fireChunk;
					};
				} else {
					// The engine says it can reach, and it doesn't fire. A Scorcher did this at 2,000 m, every time.
					if (_sinceShot >= 15) then {
						_finish = "cantlay";
					};
				};
			};
			case (_sinceShot >= 10 and {
				_fired isEqualTo (_mission get "firedAtIssue")
			} and {
				(currentCommand _crew) isEqualTo "FIRE AT POSITION"
			}): {
				_mission set ["state", "holding"];
			};
		};
		if (_finish isNotEqualTo "") then {
			_mission set ["state", _finish];
		};
	} forEach brmh_cmd_fireActive;
	brmh_cmd_fireActive = brmh_cmd_fireActive select {
		(_x get "state") in ["firing", "holding"]
	};
	if (brmh_cmd_fireActive isEqualTo [] and {
		not isNil "brmh_cmd_firePfh"
	}) then {
		[brmh_cmd_firePfh] call CBA_fnc_removePerFrameHandler;
		brmh_cmd_firePfh = nil;
	};
};

// The one thing that stops a mission once it's running. Combat modes and disableAI don't.
brmh_cmd_fnc_checkFire = {
	params ["_group", "_order", "_keys"];
	private _guns = [_group, _keys] call brmh_cmd_fnc_gunsOf;
	private _rows = [];
	{
		private _gun = _x;
		if (alive _gun) then {
			doStop _gun;
		};
		private _mission = _gun getVariable ["brmh_cmd_mission", createHashMap];
		_mission set ["state", "stopped"];
		_rows pushBack (createHashMapFromArray [["key", _gun getVariable ["brmh_cmd_key", ""]], ["order", _order], ["state", "checked"], ["word", ""], ["want", 0], ["fired", _mission getOrDefault ["fired", 0]], ["inAir", _mission getOrDefault ["inAir", 0]]]);
	} forEach _guns;
	brmh_cmd_fireActive = brmh_cmd_fireActive select {
		(_x get "state") in ["firing", "holding"]
	};
	if (_rows isEqualTo []) then {
		_rows pushBack (createHashMapFromArray [["key", ""], ["order", _order], ["state", "checked"], ["word", ""], ["want", 0], ["fired", 0], ["inAir", 0]]);
	};
	private _kept = (_group getVariable ["brmh_cmd_missions", []]) select {
		private _key = _x get "key";
		(_rows findIf {
			(_x get "key") isEqualTo _key
		}) < 0
	};
	_group setVariable ["brmh_cmd_missions", _kept + _rows];
};

// Which of a squad are medics, from the end of its list. Operator action, from the scenario.
brmh_cmd_fnc_makeMedics = {
	params [["_callsign", "", [""]], ["_count", 0, [0]]];
	private _men = +(units (brmh_cmd_stations get _callsign));
	reverse _men;
	{
		_x setVariable ["ace_medical_medicClass", 1, true];
		_x setUnitTrait ["medic", true];
	} forEach (_men select [0, _count]);
	true
};

brmh_cmd_fnc_clearAll = {
	{
		deleteVehicle _y;
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
