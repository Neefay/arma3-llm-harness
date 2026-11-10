"""Spike 1: what guns exist, their ranges, and what a fire mission really does."""
from __future__ import annotations

import math
import time

from spike_arty_lib import AREA, TRACK, game, run, show

h = game()
show("version", run(h, "productVersion"))
run(h, TRACK)

# --- what exists
show("artillery classes", run(h, """
private _out = [];
{
	if (getNumber (_x >> "scope") isEqualTo 2 and {getNumber (_x >> "artilleryScanner") > 0}) then {
		_out pushBack [configName _x, getText (_x >> "displayName"), configName inheritsFrom _x];
	};
} forEach ("true" configClasses (configFile >> "CfgVehicles"));
_out select {(_x # 0) select [0, 2] in ["B_", "O_", "I_"]}
"""))

# --- ranges, ETAs and ammunition, with and without a gunner
PROBE = """
params ["_class", "_at"];
private _gun = [_class, _at] call brmh_spike_fnc_gun;
private _empty = createVehicle [_class, _at vectorAdd [200, 0, 0], [], 0, "NONE"];
sleep 1;
private _ammo = getArtilleryAmmo [_gun];
private _rows = [];
{
	private _mag = _x;
	private _table = [50, 100, 200, 400, 800, 1200, 2000, 3000, 4000, 6000, 8000, 12000, 20000, 40000] apply {
		private _p = _gun getPos [_x, 90];
		[_x, _p inRangeOfArtillery [[_gun], _mag], round (_gun getArtilleryETA [_p, _mag])]
	};
	_rows pushBack [_mag, _table];
} forEach _ammo;
brmh_spike_probe = [
	_ammo,
	magazinesAllTurrets _gun apply {[_x # 0, _x # 1, _x # 2]},
	_rows,
	getArtilleryAmmo [_empty],
	(_gun getPos [800, 90]) inRangeOfArtillery [[_empty], "8Rnd_82mm_Mo_shells"],
	_empty getArtilleryETA [_gun getPos [800, 90], "8Rnd_82mm_Mo_shells"],
	canFire _gun, canFire _empty, someAmmo _gun, unitReady _gun, side _empty
];
deleteVehicle _empty;
{deleteVehicle _x} forEach crew _gun;
deleteVehicle _gun;
"""
for klass, at in (("B_Mortar_01_F", [1500, 1000]), ("B_MBT_01_arty_F", [1500, 700]), ("B_MBT_01_mlrs_F", [1500, 400])):
    run(h, f"brmh_spike_probe = nil; _this spawn {{{PROBE}}}; true", [klass, at])
    deadline = time.time() + 20
    result = None
    while time.time() < deadline:
        result = run(h, 'if (isNil "brmh_spike_probe") then {""} else {brmh_spike_probe}')
        if result:
            break
        time.sleep(1)
    show(f"probe {klass}", result)

# --- does a mission fire what it's told to, and where do the rounds land?
FIRE = """
params ["_name", "_at", "_range", "_mag", "_rounds", "_how"];
private _gun = ["B_Mortar_01_F", _at] call brmh_spike_fnc_gun;
sleep 2;
private _target = _gun getPos [_range, 90];
private _start = time;
private _before = _gun magazinesTurret [0];
private _countBefore = count brmh_spike_shells;
private _ready = [];
if (_how isEqualTo "command") then {
	_gun commandArtilleryFire [_target, _mag, _rounds];
} else {
	_gun doArtilleryFire [_target, _mag, _rounds];
};
private _deadline = time + 75;
private _wasReady = unitReady _gun;
_ready pushBack [0, _wasReady];
while {time < _deadline} do {
	sleep 0.5;
	if (unitReady _gun isNotEqualTo _wasReady) then {
		_wasReady = unitReady _gun;
		_ready pushBack [round (time - _start), _wasReady];
	};
};
sleep 1;
private _shells = (brmh_spike_shells select [_countBefore]) apply {
	[(_x getOrDefault ["fired", -1]) - _start, (_x getOrDefault ["landed", -1]) - _start, _x getOrDefault ["pos", _x getOrDefault ["lastPos", []]]]
};
missionNamespace setVariable ["brmh_spike_" + _name, [_target, _before, _gun magazinesTurret [0], _ready, _shells, magazinesAllTurrets _gun apply {[_x # 0, _x # 2]}]];
{deleteVehicle _x} forEach crew _gun;
deleteVehicle _gun;
"""
cases = [
    ("six", [1000, 1000], 800, "8Rnd_82mm_Mo_shells", 6, "do"),
    ("twelve", [1000, 1200], 800, "8Rnd_82mm_Mo_shells", 12, "do"),
    ("zero", [1000, 1400], 800, "8Rnd_82mm_Mo_shells", 0, "do"),
    ("command", [1000, 1600], 800, "8Rnd_82mm_Mo_shells", 4, "command"),
    ("near", [1000, 1800], 150, "8Rnd_82mm_Mo_shells", 4, "do"),
    ("far", [1000, 2000], 3000, "8Rnd_82mm_Mo_shells", 4, "do"),
]
for case in cases:
    run(h, f"brmh_spike_{case[0]} = nil; _this spawn {{{FIRE}}}; true", list(case))
time.sleep(85)
for case in cases:
    r = run(h, f'if (isNil "brmh_spike_{case[0]}") then {{""}} else {{brmh_spike_{case[0]}}}')
    if not r:
        show(case[0], "not finished")
        continue
    target, before, after, ready, shells, left = r
    landed = [s for s in shells if s[2]]
    errors = [round(math.dist(s[2][:2], target[:2])) for s in landed]
    show(case[0], {"asked": case[4], "fired": len(shells), "ready": ready, "first_fired": round(shells[0][0], 1) if shells else None,
                   "flight": [round(s[1] - s[0], 1) for s in shells][:4], "errors_m": errors, "mags": left})
