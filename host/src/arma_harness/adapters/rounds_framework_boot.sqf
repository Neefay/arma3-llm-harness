/*
	Adapter boot code for the rounds framework (runs on the server at preInit, via the bridge's boot
	payload, before the mission's init.sqf). Comments are stripped by the host before sending.

	Waits for GAME_CONTROLLER, then:
		1. applies context overrides (_this # 0: [[key, value], ...]), e.g. ROUND_DURATION, before any
		   round starts (selectors such as @ROUND_DURATION resolve when the timer starts);
		2. attaches observers, changing no framework behaviour:
		   - CBA listeners on <FSM>_EVENT_STATE_ENTER/LEAVE_<STATE> -> "evt" type "fsm";
		   - a wrapper around #SET_CONTEXT_VALUE -> "evt" type "ctx";
		3. emits "evt" type "attached" with the FSM state and the trimmed context at attach time.
*/
params [["_overrides", [], [[]]]];

brmh_roundsOverrides = _overrides;
if (not isNil "brmh_roundsWaiter") then {
	removeMissionEventHandler ["EachFrame", brmh_roundsWaiter];
};

brmh_rounds_fnc_attach = {
	private _controller = GAME_CONTROLLER;

	{
		_x params ["_key", "_value"];
		_controller call ["#SET_CONTEXT_VALUE", [_key, _value]];
	} forEach brmh_roundsOverrides;

	if (isNil "brmh_roundsHooks") then {
		brmh_roundsHooks = [];
	};
	{
		_x call CBA_fnc_removeEventHandler;
	} forEach brmh_roundsHooks;
	brmh_roundsHooks = [];

	private _fsmId = [_controller get "FSM"] call fnc_getFSMIdAlias;
	{
		private _state = _x # 0;
		private _enter = format ["%1_EVENT_STATE_ENTER_%2", _fsmId, _state];
		private _leave = format ["%1_EVENT_STATE_LEAVE_%2", _fsmId, _state];
		brmh_roundsHooks pushBack [_enter, [_enter, {
			["evt", createHashMapFromArray [
				["type", "fsm"],
				["dir", "enter"],
				["state", _this # 2]
			]] call BRMH_fnc_emit;
		}] call CBA_fnc_addEventHandler];
		brmh_roundsHooks pushBack [_leave, [_leave, {
			["evt", createHashMapFromArray [
				["type", "fsm"],
				["dir", "leave"],
				["from", _this # 2],
				["to", _this # 3]
			]] call BRMH_fnc_emit;
		}] call CBA_fnc_addEventHandler];
	} forEach (_controller get "STATES");

	if (isNil "brmh_roundsOriginalSetContext") then {
		brmh_roundsOriginalSetContext = _controller get "#SET_CONTEXT_VALUE";
	};
	_controller set ["#SET_CONTEXT_VALUE", {
		private _return = _this call brmh_roundsOriginalSetContext;
		params ["_key", "_value"];
		if (not isNil "_value" and {
			not (_key in ["STATE_TIMERS", "TRANSITION_COND"])
		}) then {
			["evt", createHashMapFromArray [
				["type", "ctx"],
				["key", _key],
				["value", [_value] call BRMH_fnc_sanitize]
			]] call BRMH_fnc_emit;
		};
		// The original usually returns nothing; reading an undefined local would be a script error.
		if (isNil "_return") then {
			nil
		} else {
			_return
		}
	}];

	private _controllerEvent = format ["CTRL_EVENT_SEQ:%1", _controller getOrDefault ["EVENT_ID", ""]];
	brmh_roundsHooks pushBack [_controllerEvent, [_controllerEvent, {
		params [["_event", ""], ["_args", []]];
		["evt", createHashMapFromArray [
			["type", "ctrl_evt"],
			["event", _event],
			["args", [_args] call BRMH_fnc_sanitize]
		]] call BRMH_fnc_emit;
	}] call CBA_fnc_addEventHandler];

	// Commands run on the machine they are dispatched to, and GUI calls on interface machines, so
	// these hooks go to every machine through the JIP queue. JIP code runs before init.sqf, hence the
	// waiter for the framework's GUI functions.
	private _machineHooks = {
		params ["_commandEvent"];
		if (not isNil "brmh_roundsCommandHook") then {
			[_commandEvent, brmh_roundsCommandHook] call CBA_fnc_removeEventHandler;
		};
		brmh_roundsCommandHook = [_commandEvent, {
			params ["_command", ["_args", []], "_isJIP"];
			["evt", createHashMapFromArray [
				["type", "cmd"],
				["name", _command],
				["jip", not isNil "_isJIP" and {
					isRemoteExecutedJIP
				}]
			]] call BRMH_fnc_emit;
		}] call CBA_fnc_addEventHandler;

		if (hasInterface and {
			isNil "brmh_roundsGuiWaiter"
		}) then {
			brmh_roundsGuiWaiter = addMissionEventHandler ["EachFrame", {
				if (isNil "fnc_GUIAction" or {
					isNil "fnc_GUIEvent"
				}) exitWith {};
				removeMissionEventHandler ["EachFrame", _thisEventHandler];
				if (isNil "brmh_roundsGuiActionOriginal") then {
					brmh_roundsGuiActionOriginal = fnc_GUIAction;
					brmh_roundsGuiEventOriginal = fnc_GUIEvent;
					fnc_GUIAction = {
						params [["_controllerId", ""], ["_method", ""]];
						["evt", createHashMapFromArray [
							["type", "gui"],
							["controller", _controllerId],
							["method", _method]
						]] call BRMH_fnc_emit;
						_this call brmh_roundsGuiActionOriginal
					};
					fnc_GUIEvent = {
						params [["_controllerId", ""], ["_guiId", ""], ["_method", ""]];
						["evt", createHashMapFromArray [
							["type", "gui"],
							["controller", _controllerId],
							["gui", _guiId],
							["method", _method]
						]] call BRMH_fnc_emit;
						_this call brmh_roundsGuiEventOriginal
					};
				};
			}];
		};
	};
	[[_controller call ["#GET_COMMAND_REGISTRY_EVENT"]], _machineHooks] remoteExec ["call", 0, "brmh_rounds_machineHooks"];

	["evt", createHashMapFromArray [
		["type", "attached"],
		["adapter", "rounds_framework"],
		["controller", _controller getOrDefault ["ID", ""]],
		["state", (_controller get "FSM") call fnc_getFSMState],
		["overrides", brmh_roundsOverrides apply {
			_x # 0
		}],
		["context", [_controller call ["#GET_CONTEXT_TRIM"]] call BRMH_fnc_sanitize]
	]] call BRMH_fnc_emit;
};

brmh_roundsWaiter = addMissionEventHandler ["EachFrame", {
	if (isNil "GAME_CONTROLLER" or {
		isNil "fnc_getFSMIdAlias"
	}) exitWith {};
	removeMissionEventHandler ["EachFrame", _thisEventHandler];
	brmh_roundsWaiter = nil;
	call brmh_rounds_fnc_attach;
}];
true
