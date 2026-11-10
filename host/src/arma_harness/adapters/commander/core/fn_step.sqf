/*
	NAME: brmh_cmd_fnc_step
	DESCRIPTION: The monitor's tick, every 2 s from start.sqf's per-frame handler: the mission clock, the treatments'
		and the machines' steps, one squad's look around, every squad's report, and every 5 s the real positions for the
		after-action review.
	PARAMETERS: None
	USAGE:
		call brmh_cmd_fnc_step;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
["evt", createHashMapFromArray [["type", "cmd_tick"]]] call BRMH_fnc_emit;
// ACE raises no event when a man dies while down, so the dead leave the list here.
brmh_cmd_down = brmh_cmd_down select {
	alive _x
};
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
