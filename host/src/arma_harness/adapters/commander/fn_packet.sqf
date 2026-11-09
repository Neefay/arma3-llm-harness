params ["_callsign", "_group"];
private _able = (units _group) select {
	[_x] call brmh_cmd_fnc_able
};
if (_able isEqualTo []) exitWith {
	nil
};
// For several seconds after a leader dies, leader still returns the body. A downed one takes a moment to pass it on too.
private _leader = if ([leader _group] call brmh_cmd_fnc_able) then {
	leader _group
} else {
	_able # 0
};
_group setVariable ["brmh_cmd_acting", _leader];
private _rounds = 0;
{
	_rounds = _rounds + ([_x] call brmh_cmd_fnc_rounds);
} forEach _able;
private _position = getPosATL _leader;
private _clearing = [_group] call brmh_cmd_fnc_clearingState;
createHashMapFromArray [
	["type", "cmd_report"],
	["callsign", _callsign],
	["pos", [_position # 0, _position # 1]],
	["grid", mapGridPosition _position],
	["dir", getDir _leader],
	["speed", speed _leader],
	["able", count _able],
	["wounded", {
		lifeState _x isEqualTo "INJURED"
	} count _able],
	["limping", (_able select {
		(_x getHitPointDamage "hitLegs") >= 0.5
	}) apply {
		name _x
	}],
	["baseline", _group getVariable ["brmh_cmd_baseline", count _able]],
	["leader", name _leader],
	["rounds", _rounds],
	["rounds_baseline", _group getVariable ["brmh_cmd_roundsBaseline", _rounds]],
	["behaviour", behaviour _leader],
	["speed_mode", speedMode _group],
	["spread", ((_able - [_leader]) select {
		vehicle _x isEqualTo _x
	}) apply {
		private _at = getPosATL _x;
		[name _x, round ((_at # 0) - (_position # 0)), round ((_at # 1) - (_position # 1)), _x getVariable ["brmh_cmd_busy", false]]
	}],
	["combat_mode", combatMode _group],
	["suppression", (_able apply {
		getSuppression _x
	}) call BIS_fnc_arithmeticMean],
	["order", _group getVariable ["brmh_cmd_order", ""]],
	["unable", _group getVariable ["brmh_cmd_unable", ""]],
	["leg", currentWaypoint _group],
	["legs", count waypoints _group],
	["clearing", _clearing # 0],
	["cleared", _clearing # 1],
	["ruined", _clearing # 2],
	["blocked", _clearing # 3],
	["seen_vehicles", _group getVariable ["brmh_cmd_seenVehicles", []]],
	["seen_ruins", _group getVariable ["brmh_cmd_seenRuins", []]],
	["mounted", [_able] call brmh_cmd_fnc_mounted],
	["mount", _group getVariable ["brmh_cmd_mount", []]],
	["missions", (_group getVariable ["brmh_cmd_missions", []]) apply {
		[_x get "key", _x get "order", _x get "state", _x getOrDefault ["reason", ""], _x get "word", _x getOrDefault ["fired", 0], _x get "want", _x getOrDefault ["eta", 0], _x getOrDefault ["inAir", 0]]
	}],
	["gun_ammo", ([_group, []] call brmh_cmd_fnc_gunsOf) apply {
		[_x getVariable ["brmh_cmd_key", ""], [_x] call brmh_cmd_fnc_gunAmmo]
	}],
	["placed", [_group] call brmh_cmd_fnc_placedState],
	["casualties", [_group, _leader] call brmh_cmd_fnc_casualties],
	["up", _able apply {
		[_x] call brmh_cmd_fnc_manKey
	}],
	["medical", _group getVariable ["brmh_cmd_care", []]],
	["contacts", [_leader] call brmh_cmd_fnc_contacts]
]
