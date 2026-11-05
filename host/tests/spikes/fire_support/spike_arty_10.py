"""Spike 10: the daytime control for spike 9. Do soldiers set up the same way notice each other by day at these ranges?"""
from __future__ import annotations

import time

from spike_arty_lib import game, run, show

h = game()
run(h, "setDate [2035, 6, 10, 12, 0]; 0 setOvercast 0; forceWeatherChange; true")
time.sleep(6)
SITE = """
params ["_name", "_at", "_gap", "_hold", "_nvg"];
private _bad = createGroup [east, false];
private _good = createGroup [west, false];
for "_i" from 1 to 4 do {
	private _b = _bad createUnit ["O_Soldier_F", _at vectorAdd [0, _gap / 2, 0], [], 5, "NONE"];
	private _g = _good createUnit ["B_Soldier_F", _at vectorAdd [0, -_gap / 2, 0], [], 5, "NONE"];
	{
		_x disableAI "PATH"; _x allowDamage false; _x setUnitPos "UP";
		if (_hold) then { _x disableAI "FIREWEAPON"; _x setUnitCombatMode "BLUE"; };
		if (not _nvg) then { _x unlinkItem hmd _x; };
	} forEach [_b, _g];
	_g setDir 0; _b setDir 180;
};
private _start = time;
private _first = -1;
private _fired = 0;
for "_i" from 1 to 40 do {
	sleep 2.5;
	private _knows = selectMax ((units _good) apply {_x knowsAbout (units _bad # 0)});
	if (_first < 0 and {_knows > 0}) then { _first = round (time - _start); };
};
missionNamespace setVariable ["brmh_spike_" + _name, [_gap, _hold, _first, selectMax ((units _good) apply {_x knowsAbout (units _bad # 0)}), behaviour leader _good]];
"""
names = []
for index, (gap, hold) in enumerate(((60, True), (120, True), (200, True), (60, False), (120, False))):
    name = f"day_{index}"
    names.append(name)
    run(h, f"brmh_spike_{name} = nil; _this spawn {{{SITE}}}; true", [name, [800 + 1500 * index, 2000, 0], gap, hold, False])
deadline = time.time() + 130
out = {}
while time.time() < deadline and len(out) < len(names):
    for name in names:
        if name not in out:
            value = run(h, f'if (isNil "brmh_spike_{name}") then {{""}} else {{brmh_spike_{name}}}')
            if value:
                out[name] = value
    time.sleep(4)
print("gap, weapons held, first noticed at (-1 never), knowsAbout, behaviour", flush=True)
for name in names:
    show(name, out.get(name, "NOT FINISHED"))
h.stop()
print("stopped", flush=True)
