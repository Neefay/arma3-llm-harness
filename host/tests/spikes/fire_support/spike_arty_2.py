"""Spike 2: accuracy, check fire, postures, retargeting, reloads, other shell types. One gun per test, each run by its own script."""
from __future__ import annotations

import math
import time

from spike_arty_lib import TRACK, game, run, show

h = game()
run(h, TRACK)
run(h, """
brmh_spike_fnc_report = {
	params ["_gun", "_target", "_start"];
	private _shells = (_gun getVariable ["brmh_shells", []]) apply {
		[(_x get "fired") - _start, (_x getOrDefault ["landed", -1]) - _start, _x getOrDefault ["pos", _x getOrDefault ["lastPos", []]], _x get "ammo"]
	};
	[_target, _shells, magazinesAllTurrets _gun apply {[_x # 0, _x # 2]}, alive gunner _gun, vehicle gunner _gun isEqualTo _gun]
};
true
""")

HE = "8Rnd_82mm_Mo_shells"
# Tests run together on separate ground, each writing its result to a named variable.
ACCURACY = """
params ["_name", "_at", "_range"];
private _gun = ["B_Mortar_01_F", _at] call brmh_spike_fnc_gun;
sleep 2;
private _target = _gun getPos [_range, 90];
private _start = time;
_gun doArtilleryFire [_target, "8Rnd_82mm_Mo_shells", 8];
sleep 60;
missionNamespace setVariable ["brmh_spike_" + _name, [_gun, _target, _start] call brmh_spike_fnc_report];
"""
CHECK = """
params ["_name", "_at", "_how"];
private _gun = ["B_Mortar_01_F", _at] call brmh_spike_fnc_gun;
private _man = gunner _gun;
sleep 2;
private _target = _gun getPos [800, 90];
private _start = time;
_gun doArtilleryFire [_target, "8Rnd_82mm_Mo_shells", 8];
waitUntil {count (_gun getVariable "brmh_shells") >= 2 or time > _start + 30};
private _at2 = time - _start;
private _fired2 = count (_gun getVariable "brmh_shells");
switch (_how) do {
	case "none": {};
	case "doStopGun": { doStop _gun; };
	case "doStopMan": { doStop _man; };
	case "blue": { group _man setCombatMode "BLUE"; };
	case "careless": { group _man setBehaviour "CARELESS"; };
	case "disableAim": { _man disableAI "WEAPONAIM"; };
	case "disableFire": { _man disableAI "FIREWEAPON"; };
	case "disableAll": { _man disableAI "ALL"; };
	case "zero": { _gun doArtilleryFire [_gun getPos [800, 90], "8Rnd_82mm_Mo_shells", 1]; };
	case "getOut": { _man action ["GetOut", _gun]; };
	case "doMove": { _man doMove (getPos _man); };
	case "watch": { _gun doWatch objNull; _man doWatch objNull; };
	case "switchMag": { _gun loadMagazine [[0], "mortar_82mm", "8Rnd_82mm_Mo_Smoke_white"]; };
	case "sideChat": { _man commandWatch objNull; };
};
private _fireTime = time;
sleep 25;
private _all = _gun getVariable "brmh_shells";
private _after = {((_x get "fired") - _fireTime) > 0.1} count _all;
missionNamespace setVariable ["brmh_spike_" + _name, [_how, _fired2, _at2, count _all, _after, unitReady _gun, vehicle _man isEqualTo _gun, currentCommand _man, currentMagazine _gun]];
"""
POSTURE = """
params ["_name", "_at", "_kind", "_value"];
private _gun = ["B_Mortar_01_F", _at] call brmh_spike_fnc_gun;
private _man = gunner _gun;
if (_kind isEqualTo "mode") then { group _man setCombatMode _value; } else { group _man setBehaviour _value; };
sleep 3;
private _start = time;
_gun doArtilleryFire [_gun getPos [800, 90], "8Rnd_82mm_Mo_shells", 3];
sleep 18;
missionNamespace setVariable ["brmh_spike_" + _name, [_kind, _value, count (_gun getVariable "brmh_shells"), unitReady _gun, combatMode _man, behaviour _man]];
"""
RETARGET = """
params ["_name", "_at"];
private _gun = ["B_Mortar_01_F", _at] call brmh_spike_fnc_gun;
sleep 2;
private _first = _gun getPos [800, 90];
private _second = _gun getPos [800, 180];
private _start = time;
_gun doArtilleryFire [_first, "8Rnd_82mm_Mo_shells", 8];
waitUntil {count (_gun getVariable "brmh_shells") >= 3 or time > _start + 30};
private _switched = time - _start;
_gun doArtilleryFire [_second, "8Rnd_82mm_Mo_shells", 2];
sleep 50;
missionNamespace setVariable ["brmh_spike_" + _name, [_first, _second, _switched, [_gun, _first, _start] call brmh_spike_fnc_report]];
"""
RELOAD = """
params ["_name", "_at"];
private _gun = ["B_Mortar_01_F", _at] call brmh_spike_fnc_gun;
sleep 2;
private _start = time;
private _target = _gun getPos [800, 90];
private _marks = [];
_gun doArtilleryFire [_target, "8Rnd_82mm_Mo_shells", 8];
sleep 1;
waitUntil {unitReady _gun or time > _start + 40};
_marks pushBack ["first mag ready", time - _start, count (_gun getVariable "brmh_shells")];
_gun doArtilleryFire [_target, "8Rnd_82mm_Mo_shells", 3];
sleep 1;
waitUntil {unitReady _gun or time > _start + 80};
_marks pushBack ["second mag ready", time - _start, count (_gun getVariable "brmh_shells")];
_gun doArtilleryFire [_target, "8Rnd_82mm_Mo_Smoke_white", 2];
sleep 1;
waitUntil {unitReady _gun or time > _start + 120};
_marks pushBack ["smoke ready", time - _start, count (_gun getVariable "brmh_shells")];
_gun doArtilleryFire [_target, "8Rnd_82mm_Mo_Flare_white", 1];
sleep 1;
waitUntil {unitReady _gun or time > _start + 150};
_marks pushBack ["flare ready", time - _start, count (_gun getVariable "brmh_shells")];
_gun doArtilleryFire [_target, "8Rnd_82mm_Mo_Flare_white_illumination", 1];
sleep 1;
waitUntil {unitReady _gun or time > _start + 170};
_marks pushBack ["illum ready", time - _start, count (_gun getVariable "brmh_shells")];
sleep 60;
missionNamespace setVariable ["brmh_spike_" + _name, [_marks, [_gun, _target, _start] call brmh_spike_fnc_report]];
"""
EACH = """
params ["_name", "_at"];
private _gun = ["B_Mortar_01_F", _at] call brmh_spike_fnc_gun;
sleep 2;
private _centre = _gun getPos [800, 90];
private _start = time;
private _aims = [];
for "_i" from 1 to 6 do {
	private _aim = _centre getPos [40, 60 * _i];
	_aims pushBack _aim;
	_gun doArtilleryFire [_aim, "8Rnd_82mm_Mo_shells", 1];
	sleep 0.5;
	waitUntil {unitReady _gun or time > _start + 60};
};
private _done = time - _start;
sleep 40;
missionNamespace setVariable ["brmh_spike_" + _name, [_centre, _aims, _done, [_gun, _centre, _start] call brmh_spike_fnc_report]];
"""
tests = []


def launch(name: str, code: str, *args) -> None:
    tests.append(name)
    run(h, f"brmh_spike_{name} = nil; _this spawn {{{code}}}; true", [name, *args])


# Spread out in rows, so nobody hits anybody. Guns fire east, and guns in a column sit 500 m apart.
for index, rng in enumerate((100, 300, 800, 2000, 3500)):
    launch(f"acc{rng}", ACCURACY, [800, 800 + 500 * index], rng)
for index, how in enumerate(("none", "doStopGun", "doStopMan", "blue", "careless", "disableAim", "disableFire", "disableAll",
                             "zero", "getOut", "doMove", "watch", "switchMag")):
    launch(f"check_{how}", CHECK, [2400, 500 + 300 * index], how)
for index, (kind, value) in enumerate((("mode", "BLUE"), ("mode", "GREEN"), ("mode", "RED"), ("beh", "CARELESS"), ("beh", "SAFE"),
                                       ("beh", "STEALTH"), ("beh", "COMBAT"))):
    launch(f"post_{value}", POSTURE, [4200, 500 + 300 * index], kind, value)
launch("retarget", RETARGET, [5800, 800])
launch("reload", RELOAD, [5800, 1800])
launch("each", EACH, [5800, 2800])


def wait(names, seconds):
    deadline = time.time() + seconds
    out = {}
    while time.time() < deadline:
        for name in names:
            if name not in out:
                value = run(h, f'if (isNil "brmh_spike_{name}") then {{""}} else {{brmh_spike_{name}}}')
                if value:
                    out[name] = value
        if len(out) == len(names):
            break
        time.sleep(5)
    return out


results = wait(tests, 330)
for name in tests:
    r = results.get(name)
    if r is None:
        show(name, "NOT FINISHED")
    elif name.startswith("acc"):
        target, shells, mags, *_ = r
        points = [s[2] for s in shells if s[2]]
        centre = [sum(p[i] for p in points) / len(points) for i in (0, 1)]
        show(name, {"fired": len(shells), "flight": round(shells[0][1] - shells[0][0], 1), "span_s": round(shells[-1][0] - shells[0][0], 1),
                    "mean_miss_m": round(sum(math.dist(p[:2], target[:2]) for p in points) / len(points), 1),
                    "max_miss_m": round(max(math.dist(p[:2], target[:2]) for p in points), 1),
                    "centre_off_m": round(math.dist(centre, target[:2]), 1)})
    elif name == "retarget":
        first, second, switched, (target, shells, mags, *_) = r
        rows = [(round(s[0], 1), round(math.dist(s[2][:2], first[:2])), round(math.dist(s[2][:2], second[:2]))) for s in shells if s[2]]
        show(name, {"switched_at": round(switched, 1), "fired_time_miss1_miss2": rows, "mags": mags})
    elif name == "reload":
        marks, (target, shells, mags, *_) = r
        rows = [(round(s[0], 1), round(s[1], 1), s[3]) for s in shells]
        show(name, {"marks": marks, "shells": rows, "mags": mags})
    elif name == "each":
        centre, aims, done, (target, shells, mags, *_) = r
        rows = [(round(s[0], 1), round(math.dist(s[2][:2], centre[:2])), round(math.dist(s[2][:2], aims[i][:2]))) for i, s in enumerate(shells) if s[2] and i < len(aims)]
        show(name, {"done": round(done, 1), "fired_time_from_centre_from_aim": rows})
    else:
        show(name, r)
