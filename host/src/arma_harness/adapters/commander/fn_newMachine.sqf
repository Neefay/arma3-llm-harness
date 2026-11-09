/*
	NAME: brmh_cmd_fnc_newMachine
	DESCRIPTION: A declared state machine, stepped by its owner. The declaration names every state, and on creation it's
		checked for the two faults that hand-written machines kept having: a state that waits with no deadline, and a way
		to end that says nothing. Either is logged as an error. See docs/COMMANDER_MODEL.md, the appendix.
	PARAMETERS:
		0 - Declaration (ARRAY): [KEY, value] pairs:
			KIND     - what the radio calls the job, as brmh_cmd_fnc_careSay takes it (STRING)
			SAYS     - false for a machine whose state reaches the host in its own packet field, not as radio words;
			           its words are then never said, and an ending needs none (BOOL, default true)
			INITIAL  - the state it starts in (STRING)
			ALWAYS   - transitions checked in every state, before the state's own (ARRAY)
			STATES   - [[name, [["ON", transitions], ["DEADLINE", [seconds or {seconds}, action, next, word]],
			           ["EVERY", code run each step while in the state (optional)]]], ...]. A state that lasts
			           until the machine is ended from outside, such as a squad holding where it was placed, has
			           ["STANDING", true] in place of a deadline.
			RELEASE  - run once, however it ends (CODE)
			A transition is [guard, action, next state, word]. Guards and actions get the machine as _this, and an
			action may return the detail its word needs. A next state of "" ends the machine, and has to have a word.
		1 - Data: [KEY, value] pairs, such as GROUP, ORDER, SUBJECT and whatever its code reads. START, if given, is the
		    state it starts in instead of INITIAL (ARRAY)
	USAGE:
		private _job = [brmh_cmd_postMachine, [["GROUP", _group], ["ORDER", _order], ["SUBJECT", "post"]]] call brmh_cmd_fnc_newMachine;
		brmh_cmd_builds = brmh_cmd_builds select { _x call ["#STEP", []] };
		_job call ["#END", ["called off"]];
	RETURNS: The machine (HASHMAP object). #STEP returns whether it's still running
	ENVIRONMENT: Server, unscheduled
*/
params [["_declaration", [], [[]]], ["_data", [], [[]]]];
private _MachineDeclaration = [
	["#type", "CommanderMachine"],
	["#create", {
		params ["_declaration", "_data"];
		private _spec = createHashMapFromArray _declaration;
		private _states = createHashMap;
		{
			_states set [_x # 0, createHashMapFromArray (_x # 1)];
		} forEach (_spec getOrDefault ["STATES", []]);
		_spec set ["STATES", _states];
		{
			["Machines", "ERROR", "machine %1: %2", [_spec getOrDefault ["KIND", "?"], _x]] call brmh_cmd_fnc_log;
		} forEach ([_spec] call brmh_cmd_fnc_machineProblems);
		_self set ["SPEC", _spec];
		{
			_self set [_x # 0, _x # 1];
		} forEach _data;
		// A machine with more than one way in, such as boarding's getting on and getting off, names where it starts.
		_self set ["STATE", _self getOrDefault ["START", _spec get "INITIAL"]];
		_self set ["SINCE", time];
	}],
	["#STEP", {
		private _spec = _self get "SPEC";
		private _state = _self get "STATE";
		if (_state isEqualTo "") exitWith {
			false
		};
		private _here = (_spec get "STATES") get _state;
		// What a state keeps doing while it lasts, such as a pilot searching. It decides nothing: transitions do.
		_self call (_here getOrDefault ["EVERY", {}]);
		private _transitions = (_spec getOrDefault ["ALWAYS", []]) + (_here getOrDefault ["ON", []]);
		private _taken = _transitions findIf {
			_self call (_x # 0)
		};
		if (_taken >= 0) then {
			_self call ["#GO", _transitions # _taken];
		} else {
			if ("DEADLINE" in _here) then {
				(_here get "DEADLINE") params ["_after", "_action", "_next", "_word"];
				private _limit = if (_after isEqualType {}) then {
					_self call _after
				} else {
					_after
				};
				if ((time - (_self get "SINCE")) >= _limit) then {
					_self call ["#GO", [{
						true
					}, _action, _next, _word]];
				};
			};
		};
		(_self get "STATE") isNotEqualTo ""
	}],
	["#GO", {
		params ["", "_action", "_next", "_word"];
		private _detail = _self call _action;
		if (isNil "_detail") then {
			_detail = "";
		};
		if (_word isNotEqualTo "" and {
			(_self get "SPEC") getOrDefault ["SAYS", true]
		}) then {
			[_self get "GROUP", _self get "ORDER", (_self get "SPEC") get "KIND", _self get "SUBJECT", _word, _detail] call brmh_cmd_fnc_careSay;
		};
		_self set ["STATE", _next];
		_self set ["SINCE", time];
		if (_next isEqualTo "") then {
			_self call ((_self get "SPEC") getOrDefault ["RELEASE", {}]);
		};
	}],
	// Called off from outside, such as by a squad order taking its men back.
	["#END", {
		params [["_word", "called off", [""]]];
		if ((_self get "STATE") isNotEqualTo "") then {
			_self call ["#GO", [{
				true
			}, {}, "", _word]];
		};
	}]
];
createHashMapObject [_MachineDeclaration, [_declaration, _data]]
