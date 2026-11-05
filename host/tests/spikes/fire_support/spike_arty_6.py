"""Spike 6: a crewed gun fires on its own at enemies it knows of. What stops that, while still letting ordered missions through?"""
from __future__ import annotations

import time

from spike_arty_lib import TRACK, game, run, show

h = game()
run(h, TRACK)

TEST = """
params ["_name", "_at", "_how"];
private _gun = ["B_Mortar_01_F", _at] call brmh_spike_fnc_gun;
private _man = gunner _gun;
private _group = group _man;
switch (_how) do {
	case "none": {};
	case "unitGreen": { _man setUnitCombatMode "GREEN"; };
	case "unitBlue": { _man setUnitCombatMode "BLUE"; };
	case "groupGreen": { _group setCombatMode "GREEN"; };
	case "autotarget": { _man disableAI "AUTOTARGET"; };
	case "target": { _man disableAI "TARGET"; };
	case "bothTarget": { _man disableAI "AUTOTARGET"; _man disableAI "TARGET"; };
	case "careless": { _group setBehaviourStrong "CARELESS"; };
	case "carelessUnit": { _man setCombatBehaviour "CARELESS"; };
	case "doStop": { doStop _gun; };
	case "weaponaim": { _man disableAI "WEAPONAIM"; };
};
private _bad = createGroup [east, false];
private _spot = _gun getPos [250, 0];
for "_i" from 1 to 3 do {
	private _enemy = _bad createUnit ["O_Soldier_F", _spot, [], 6, "NONE"];
	_enemy setCaptive false;
	_enemy disableAI "PATH";
	_enemy disableAI "FIREWEAPON";
	_enemy setUnitCombatMode "BLUE";
	_enemy allowDamage false;
};
private _start = time;
for "_i" from 1 to 8 do {
	{ _man reveal [_x, 4]; } forEach units _bad;
	sleep 5;
};
private _self = count (_gun getVariable "brmh_shells");
private _mode = [combatMode _man, unitCombatMode _man, behaviour _man, _man knowsAbout (units _bad # 0), currentCommand _man, unitReady _gun];
private _target = _gun getPos [800, 90];
_gun doArtilleryFire [_target, "8Rnd_82mm_Mo_shells", 3];
sleep 10;
private _ordered = (count (_gun getVariable "brmh_shells")) - _self;
private _state = [unitReady _gun, currentCommand _man];
private _flipped = -1;
if (_ordered isEqualTo 0) then {
	switch (_how) do {
		case "unitGreen": { _man setUnitCombatMode "YELLOW"; };
		case "unitBlue": { _man setUnitCombatMode "YELLOW"; };
		case "groupGreen": { _group setCombatMode "YELLOW"; };
	};
	sleep 10;
	_flipped = (count (_gun getVariable "brmh_shells")) - _self;
};
sleep 25;
private _landed = (_gun getVariable "brmh_shells") select [_self] apply {round ((_x getOrDefault ["pos", [0, 0, 0]]) distance2D _target)};
missionNamespace setVariable ["brmh_spike_" + _name, [_how, _self, _mode, _ordered, _state, _flipped, _landed]];
"""
names = []


def launch(name: str, code: str, *args) -> None:
    names.append(name)
    run(h, f"brmh_spike_{name} = nil; _this spawn {{{code}}}; true", [name, *args])


CASES = ("none", "unitGreen", "unitBlue", "groupGreen", "autotarget", "target", "bothTarget", "careless", "carelessUnit", "doStop", "weaponaim")
for index, how in enumerate(CASES):
    launch(f"t_{how}", TEST, [500 + 700 * (index % 4), 500 + 900 * (index // 4)], how)


def collect(wanted, seconds):
    deadline = time.time() + seconds
    out = {}
    while time.time() < deadline and len(out) < len(wanted):
        for name in wanted:
            if name not in out:
                value = run(h, f'if (isNil "brmh_spike_{name}") then {{""}} else {{brmh_spike_{name}}}')
                if value:
                    out[name] = value
        time.sleep(4)
    return out


out = collect(names, 130)
for name in names:
    show(name, out.get(name, "NOT FINISHED"))

# The global switch last, because it affects every gun on the server.
names.clear()
run(h, "enableEngineArtillery false; true")
show("engine artillery enabled", run(h, 'getArtilleryComputerSettings'))
launch("t_engineOff", TEST, [6000, 500], "none")
out = collect(names, 130)
show("t_engineOff", out.get("t_engineOff", "NOT FINISHED"))
h.stop()
print("stopped", flush=True)
