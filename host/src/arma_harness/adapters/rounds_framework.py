"""Rounds framework adapter tools: read framework state through its own accessors (never mutate,
except the explicit context_set / fire_event)."""
from __future__ import annotations

import json

STATE_SQF = """
if (isNil "GAME_CONTROLLER") exitWith {createHashMapFromArray [["error", "GAME_CONTROLLER not created yet"]]};
private _c = GAME_CONTROLLER;
createHashMapFromArray [
    ["controller", _c getOrDefault ["ID", ""]],
    ["fsm_state", (_c get "FSM") call fnc_getFSMState],
    ["context", _c call ["#GET_CONTEXT_TRIM"]],
    ["controllers", if (isNil "BRM_CONTROLLERS") then {[]} else {keys BRM_CONTROLLERS}],
    ["command_count", count (_c getOrDefault ["COMMANDS", []])],
    ["throttled", if (isNil "THROTTLED_EVAL_DICT") then {0} else {count THROTTLED_EVAL_DICT}],
    ["mission_time", CBA_missionTime]
]
"""

CONTEXT_GET_SQF = """
params ["_key"];
if (isNil "GAME_CONTROLLER") exitWith {"$error:GAME_CONTROLLER not created yet"};
GAME_CONTROLLER call ["#GET_CONTEXT_VALUE", [_key]]
"""

# The value travels as a one-element JSON array: fromJSON returns nil for a top-level scalar ("5")
# on 2.22, despite the wiki's example.
CONTEXT_SET_SQF = """
params ["_key", "_json"];
if (isNil "GAME_CONTROLLER") exitWith {"$error:GAME_CONTROLLER not created yet"};
GAME_CONTROLLER call ["#SET_CONTEXT_VALUE", [_key, (fromJSON _json) # 0]];
GAME_CONTROLLER call ["#GET_CONTEXT_VALUE", [_key]]
"""

FIRE_EVENT_SQF = """
params ["_alias", "_event", "_args"];
[_alias, _event, _args] call BRM_fnc_controllerEvent;
true
"""

GUI_SQF = """
if (isNil "BRM_SimpleGUIGroups") exitWith {[]};
private _out = [];
{
    private _group = _y;
    private _controls = [];
    {
        if (not isNull _y) then {
            _controls pushBack [_x, ctrlText _y, ctrlShown _y, round ((ctrlFade _y) * 100) / 100];
        };
    } forEach (_group getOrDefault ["CONTROLS", createHashMap]);
    _out pushBack createHashMapFromArray [
        ["group", _x],
        ["controls", _controls],
        ["data", _group getOrDefault ["DATA", createHashMap]]
    ];
} forEach BRM_SimpleGUIGroups;
_out
"""


def state(h) -> dict:
    return h.exec(STATE_SQF, "server")


def context_get(h, key: str) -> dict:
    return h.exec(CONTEXT_GET_SQF, "server", args=[key])


def context_set(h, key: str, value) -> dict:
    return h.exec(CONTEXT_SET_SQF, "server", args=[key, json.dumps([value])])


def fire_event(h, event: str, args: list | None = None, alias: str = "GameController") -> dict:
    return h.exec(FIRE_EVENT_SQF, "server", args=[alias, event, args or []])


def gui(h, target: str = "interface") -> dict:
    return h.exec(GUI_SQF, target)
