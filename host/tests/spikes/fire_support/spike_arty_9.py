"""Spike 9: redoes what spike 8 couldn't settle. Guns on a headless client, on a mission with a slot for one, and whether light
helps the AI see at night, at a range where it can see at all. Boots its own game, and stops it."""
from __future__ import annotations

import time

from arma_harness.harness import Harness
from spike_arty_lib import TRACK, run, show

h = Harness()
if h.state() is not None:
    raise SystemExit("stop the running game first")
print("booting with a headless client", flush=True)
h.start(mission="demo_vr", hcs=1)
time.sleep(12)
run(h, TRACK)
machines = run(h, "allPlayers apply {[name _x, owner _x, _x isKindOf 'HeadlessClient_F']}")
show("machines", machines)
owner = next((m[1] for m in machines if m[2]), None)
show("headless client owner", owner)
if owner is not None:
    run(h, """
    brmh_hc_gun = createVehicle ["B_Mortar_01_F", [1500, 3000, 0], [], 0, "NONE"];
    [brmh_hc_gun] call brmh_spike_fnc_track;
    brmh_hc_group = createGroup [west, false];
    brmh_hc_man = brmh_hc_group createUnit ["B_Soldier_F", [1500, 3000, 0], [], 3, "NONE"];
    brmh_hc_man moveInGunner brmh_hc_gun;
    true
    """)
    time.sleep(3)
    show("moved", run(h, "params ['_owner']; brmh_hc_group setGroupOwner _owner", [owner]))
    time.sleep(5)
    show("after the move", run(h, "[groupOwner brmh_hc_group, owner brmh_hc_man, owner brmh_hc_gun, local brmh_hc_gun, gunner brmh_hc_gun isEqualTo brmh_hc_man, canFire brmh_hc_gun]"))
    target = "brmh_hc_gun getPos [800, 90]"
    run(h, f'brmh_hc_gun doArtilleryFire [{target}, "8Rnd_82mm_Mo_shells", 2]; true')
    time.sleep(12)
    show("ordered from the server: [server's Fired count, ready, ammo]", run(h, '[count (brmh_hc_gun getVariable "brmh_shells"), unitReady brmh_hc_gun, magazinesAmmo brmh_hc_gun select [0, 1]]'))
    run(h, f'[brmh_hc_gun, [{target}, "8Rnd_82mm_Mo_shells", 2]] remoteExec ["doArtilleryFire", brmh_hc_gun]; true')
    time.sleep(12)
    show("ordered where the gun is local", run(h, '[count (brmh_hc_gun getVariable "brmh_shells"), unitReady brmh_hc_gun, magazinesAmmo brmh_hc_gun select [0, 1]]'))
    time.sleep(30)
    show("what the server saw land", run(h, '(brmh_hc_gun getVariable "brmh_shells") apply {[_x getOrDefault ["pos", []], _x getOrDefault ["gone", -1] > 0, _x getOrDefault ["lastPos", []]]}'))
    run(h, 'brmh_hc_man disableAI "TARGET"; true')
    show("TARGET off from the server, read where it counts", run(h, "brmh_hc_man checkAIFeature 'TARGET'"))
    time.sleep(1)
    run(h, '[brmh_hc_man, "TARGET"] remoteExec ["disableAI", brmh_hc_man]; true')
    time.sleep(1)
    show("TARGET off by remoteExec", run(h, "brmh_hc_man checkAIFeature 'TARGET'"))
    run(h, "doStop brmh_hc_gun; true")
    time.sleep(2)
    show("doStop from the server: [command, ready]", run(h, "[currentCommand brmh_hc_man, unitReady brmh_hc_gun]"))

# Night, with light. Soldiers keep their positions, weapons held, and can't be hurt. Sites are far apart, so one flare doesn't light another's.
run(h, 'setDate [2035, 1, 1, 1, 0]; 0 setOvercast 0.8; forceWeatherChange; true')
time.sleep(8)
SITE = """
params ["_name", "_at", "_how", "_gap"];
private _gun = ["B_Mortar_01_F", [_at # 0, (_at # 1) - 800]] call brmh_spike_fnc_gun;
(gunner _gun) disableAI "TARGET";
private _bad = createGroup [east, false];
private _good = createGroup [west, false];
for "_i" from 1 to 4 do {
	private _b = _bad createUnit ["O_Soldier_F", _at vectorAdd [0, _gap / 2, 0], [], 5, "NONE"];
	private _g = _good createUnit ["B_Soldier_F", _at vectorAdd [0, -_gap / 2, 0], [], 5, "NONE"];
	{ _x disableAI "PATH"; _x disableAI "FIREWEAPON"; _x setUnitCombatMode "BLUE"; _x unlinkItem hmd _x; _x allowDamage false; _x setUnitPos "UP"; } forEach [_b, _g];
	_g setDir 0; _b setDir 180;
};
private _start = time;
private _first = -1;
private _rows = [];
if (_how isNotEqualTo "none") then { _gun doArtilleryFire [_at, _how, 4]; };
for "_i" from 1 to 22 do {
	sleep 5;
	private _knows = selectMax ((units _good) apply {_x knowsAbout (units _bad # 0)});
	if (_first < 0 and {_knows > 0}) then { _first = round (time - _start); };
	private _l = getLightingAt (units _good # 0);
	_rows pushBack [round (time - _start), (round (_l # 3)), (round (10 * _knows)) / 10];
};
missionNamespace setVariable ["brmh_spike_" + _name, [_how, _gap, _first, _rows select [0, 22] select {(_x # 0) % 20 < 5}]];
"""
names = []
CASES = [("none", 60), ("none", 120), ("8Rnd_82mm_Mo_Flare_white", 60), ("8Rnd_82mm_Mo_Flare_white", 120),
         ("8Rnd_82mm_Mo_Flare_white_illumination", 60), ("8Rnd_82mm_Mo_Flare_white_illumination", 120)]
for index, (how, gap) in enumerate(CASES):
    name = f"site_{index}"
    names.append(name)
    run(h, f"brmh_spike_{name} = nil; _this spawn {{{SITE}}}; true", [name, [800 + 2200 * (index % 3), 1500 + 3000 * (index // 3), 0], how, gap])
deadline = time.time() + 140
out = {}
while time.time() < deadline and len(out) < len(names):
    for name in names:
        if name not in out:
            value = run(h, f'if (isNil "brmh_spike_{name}") then {{""}} else {{brmh_spike_{name}}}')
            if value:
                out[name] = value
    time.sleep(4)
for name in names:
    show(name, out.get(name, "NOT FINISHED"))
h.stop()
print("stopped", flush=True)
