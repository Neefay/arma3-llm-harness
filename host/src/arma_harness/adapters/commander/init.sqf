/*
	Commander mode, game side (runs on the server, comments are stripped by the host). Safe to re-run.
	The host joins this folder into one program (adapters/__init__.py): this file, the machines' declarations
	(machine_*.sqf), one file per function (fn_<name>.sqf, defined as brmh_cmd_fnc_<name>), then start.sqf.
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
// Strikes: how far out a guided bomb is released, and the drag of the engine's unguided bombs (docs/COMMANDER_CAS.md).
// The game side's own diagnostics (brmh_cmd_fnc_log): the least level written to the RPT, and whether warnings and
// errors also go to the observers' chat. Kept across battles, so they can be set by hand on a running game.
if (isNil "BRMH_CMD_LOG_LEVEL") then {
	BRMH_CMD_LOG_LEVEL = "INFO";
	BRMH_CMD_LOG_SCREEN = false;
};
BRMH_CMD_GUIDED_RELEASE_M = 2400;
BRMH_CMD_BOMB_DRAG = 0.000225;
BRMH_CMD_BOMB_TURN = 6.9;
// How far out a strike's run starts. Out of the turn there, a pilot's track settles onto the grid only slowly: 13° off
// at 4 km, still 5° at 1 km, from a 5 km start.
BRMH_CMD_RUN_IN_M = 9000;
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
