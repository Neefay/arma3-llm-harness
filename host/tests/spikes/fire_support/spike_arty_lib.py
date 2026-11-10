"""Shared bits for the fire support spikes. They run on a headless game in open VR ground, far from the village."""
from __future__ import annotations

import json
import time

from arma_harness.harness import Harness

AREA = [1500.0, 1500.0]


def game() -> Harness:
    harness = Harness()
    if harness.state() is None:
        print("booting", flush=True)
        harness.start(mission="commander")
        time.sleep(10)
    return harness


def run(harness: Harness, code: str, args: list | None = None, timeout: float = 30):
    res = harness.exec(code, "server", timeout=timeout, args=args, strip=False)
    result = res["results"][0] if res.get("results") else res
    if not res.get("ok") or result.get("errors"):
        raise RuntimeError(json.dumps(result)[:1500])
    return result.get("r")


def show(label: str, value) -> None:
    print(f"{label}: {json.dumps(value, ensure_ascii=False)}", flush=True)


# Every shell's life, kept in missionNamespace: fired time and place, then where it ended.
TRACK = """
brmh_spike_shells = [];
brmh_spike_fnc_track = {
	params ["_gun"];
	_gun setVariable ["brmh_shells", []];
	_gun addEventHandler ["Fired", {
		params ["_gun", "_weapon", "_muzzle", "_mode", "_ammo", "_magazine", "_shell", "_gunner"];
		private _entry = createHashMapFromArray [["fired", time], ["ammo", _ammo], ["magazine", _magazine], ["gun", netId _gun]];
		brmh_spike_shells pushBack _entry;
		(_gun getVariable "brmh_shells") pushBack _entry;
		_shell setVariable ["brmh_entry", _entry];
		_shell addEventHandler ["Explode", {
			params ["_shell", "_pos"];
			private _entry = _shell getVariable ["brmh_entry", createHashMap];
			_entry set ["landed", time];
			_entry set ["pos", _pos];
		}];
		_shell addEventHandler ["Deleted", {
			params ["_shell"];
			private _entry = _shell getVariable ["brmh_entry", createHashMap];
			if (not ("gone" in _entry)) then {
				_entry set ["gone", time];
				_entry set ["lastPos", getPosATL _shell];
			};
		}];
	}];
};
brmh_spike_fnc_shells = {
	brmh_spike_shells apply {
		[_x getOrDefault ["fired", -1], _x getOrDefault ["landed", -1], _x getOrDefault ["pos", []], _x getOrDefault ["ammo", ""], _x getOrDefault ["lastPos", []], _x getOrDefault ["gone", -1]]
	}
};
brmh_spike_fnc_gun = {
	params ["_class", "_pos", ["_side", west]];
	private _gun = createVehicle [_class, (_pos select [0, 2]) + [0], [], 0, "NONE"];
	_gun setDir 0;
	private _group = createGroup [_side, false];
	private _man = _group createUnit [["B_Soldier_F", "O_Soldier_F"] select (_side isEqualTo east), _pos, [], 3, "NONE"];
	_man moveInGunner _gun;
	[_gun] call brmh_spike_fnc_track;
	_gun
};
true
"""
