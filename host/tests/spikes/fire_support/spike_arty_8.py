"""Spike 8: what spike 7 left open. Scorcher ranges, rocket impacts, guns on a headless client, then flares at night. Run it after
spike 7, in the same game or a fresh one. It stops the game when it's done."""
from __future__ import annotations

import time

from spike_arty_lib import TRACK, game, run, show

h = game()
run(h, TRACK)
for label, name in (("assault alone, TARGET off", "assault_alone_off"), ("assault alone, TARGET on", "assault_alone_on"), ("assault with squad, TARGET off", "assault_squad_off"),
                    ("long fight, subordinate on gun", "long_subordinate"), ("long fight, leader on gun", "long_leader_on_gun")):
    show(f"second run of spike 7: {label}", run(h, f'if (isNil "brmh_spike_{name}") then {{"not in this game"}} else {{brmh_spike_{name}}}'))

SWEEP = """
params ["_name", "_at", "_class", "_range"];
private _gun = [_class, _at] call brmh_spike_fnc_gun;
sleep 3;
private _mag = (getArtilleryAmmo [_gun]) # 0;
private _target = _gun getPos [_range, 90];
private _before = [_target inRangeOfArtillery [[_gun], _mag], _gun getArtilleryETA [_target, _mag]];
private _start = time;
_gun doArtilleryFire [_target, _mag, 2];
sleep 40;
private _mid = [count (_gun getVariable "brmh_shells"), unitReady _gun, currentCommand gunner _gun];
missionNamespace setVariable ["brmh_spike_" + _name, [_class, _range, _before, _mid, weaponState [_gun, [0]] select [0, 3]]];
"""
ROCKET = """
params ["_name", "_at", "_class"];
private _gun = [_class, _at] call brmh_spike_fnc_gun;
sleep 3;
private _mag = (getArtilleryAmmo [_gun]) # 0;
private _target = _gun getPos [3000, 90];
private _eta = _gun getArtilleryETA [_target, _mag];
private _start = time;
_gun doArtilleryFire [_target, _mag, 2];
sleep 75;
missionNamespace setVariable ["brmh_spike_" + _name, [_class, _eta, (_gun getVariable "brmh_shells") apply {[_x get "ammo", ((_x get "fired") - _start), ((_x getOrDefault ["landed", -1]) - _start), ((_x getOrDefault ["gone", -1]) - _start), _x getOrDefault ["pos", []], _x getOrDefault ["lastPos", []]]}, _target]];
"""
names: list[str] = []


def launch(name: str, code: str, *args) -> None:
    names.append(name)
    run(h, f"brmh_spike_{name} = nil; _this spawn {{{code}}}; true", [name, *args])


def collect(wanted, seconds) -> dict:
    deadline = time.time() + seconds
    out: dict = {}
    while time.time() < deadline and len(out) < len(wanted):
        for name in wanted:
            if name not in out:
                value = run(h, f'if (isNil "brmh_spike_{name}") then {{""}} else {{brmh_spike_{name}}}')
                if value:
                    out[name] = value
        time.sleep(4)
    return out


for index, rng in enumerate((1000, 1300, 1600, 2000, 2200, 2500, 3000, 4000)):
    launch(f"sweep_{rng}", SWEEP, [300 + 800 * index, 1800], "B_MBT_01_arty_F", rng)
launch("rocket_a", ROCKET, [300, 3300], "B_MBT_01_mlrs_F")
launch("rocket_b", ROCKET, [1200, 3300], "I_Truck_02_MRL_F")
out = collect(names, 110)
for name in names:
    show(name, out.get(name, "NOT FINISHED"))

# --- a headless client: a gun and crew owned by another machine
try:
    joined = h.hc_start()
    show("headless client", {key: joined.get(key) for key in ("name", "owner", "pid")})
    owner = joined.get("owner")
    time.sleep(5)
    run(h, """
    params ["_owner"];
    brmh_hc_gun = createVehicle ["B_Mortar_01_F", [4500, 1000, 0], [], 0, "NONE"];
    [brmh_hc_gun] call brmh_spike_fnc_track;
    brmh_hc_group = createGroup [west, false];
    brmh_hc_man = brmh_hc_group createUnit ["B_Soldier_F", [4500, 1000, 0], [], 3, "NONE"];
    brmh_hc_man moveInGunner brmh_hc_gun;
    true
    """, [owner])
    time.sleep(3)
    moved = run(h, "params ['_owner']; [brmh_hc_group setGroupOwner _owner, _owner]", [owner])
    time.sleep(4)
    show("moved to the headless client", {"moved": moved, "state": run(h, "[groupOwner brmh_hc_group, owner brmh_hc_man, owner brmh_hc_gun, local brmh_hc_gun, gunner brmh_hc_gun isEqualTo brmh_hc_man, canFire brmh_hc_gun]")})
    run(h, 'brmh_hc_gun doArtilleryFire [brmh_hc_gun getPos [800, 90], "8Rnd_82mm_Mo_shells", 2]; true')
    time.sleep(15)
    show("ordered from the server", run(h, '[count (brmh_hc_gun getVariable "brmh_shells"), unitReady brmh_hc_gun, currentCommand brmh_hc_man, magazinesAmmo brmh_hc_gun select [0, 2]]'))
    run(h, """
    [brmh_hc_gun, [brmh_hc_gun getPos [800, 90], "8Rnd_82mm_Mo_shells", 2]] remoteExec ["doArtilleryFire", brmh_hc_gun];
    true
    """)
    time.sleep(15)
    show("ordered where the gun is local", run(h, '[count (brmh_hc_gun getVariable "brmh_shells"), unitReady brmh_hc_gun, magazinesAmmo brmh_hc_gun select [0, 2]]'))
    time.sleep(30)
    show("what the server saw land", run(h, '(brmh_hc_gun getVariable "brmh_shells") apply {[_x getOrDefault ["pos", []], _x getOrDefault ["gone", -1] > 0, _x getOrDefault ["lastPos", []]]}'))
    show("watching on the headless client", run(h, """
    [{ brmh_hc_seen = 0; brmh_hc_gun addEventHandler ["Fired", { brmh_hc_seen = brmh_hc_seen + 1; publicVariableServer "brmh_hc_seen"; }]; }] remoteExec ["call", brmh_hc_gun];
    true
    """))
    time.sleep(2)
    run(h, '[brmh_hc_gun, [brmh_hc_gun getPos [800, 90], "8Rnd_82mm_Mo_shells", 1]] remoteExec ["doArtilleryFire", brmh_hc_gun]; true')
    time.sleep(10)
    show("rounds the headless client's own handler saw", run(h, 'if (isNil "brmh_hc_seen") then {"nothing reported"} else {brmh_hc_seen}'))
except Exception as exc:  # the headless client is optional here: the night tests still matter
    show("headless client test failed", str(exc)[:600])

# --- flares at night
run(h, """
setDate [2035, 1, 1, 1, 0];
0 setOvercast 0.8;
forceWeatherChange;
true
""")
time.sleep(8)
show("night", run(h, '[date, sunOrMoon, moonIntensity, overcast]'))
FLARE = """
params ["_name", "_at", "_how"];
private _gun = ["B_Mortar_01_F", [_at # 0, (_at # 1) - 800]] call brmh_spike_fnc_gun;
(gunner _gun) disableAI "TARGET";
private _spot = _at;
private _bad = createGroup [east, false];
private _good = createGroup [west, false];
for "_i" from 1 to 4 do {
	private _b = _bad createUnit ["O_Soldier_F", _at vectorAdd [0, 100, 0], [], 8, "NONE"];
	private _g = _good createUnit ["B_Soldier_F", _at vectorAdd [0, -100, 0], [], 8, "NONE"];
	{ _x disableAI "PATH"; _x setUnitCombatMode "BLUE"; _x unlinkItem hmd _x; _x allowDamage false; } forEach [_b, _g];
	_g setDir 0; _b setDir 180;
};
private _start = time;
private _light = {
	private _l = getLightingAt (units _good # 0);
	[round (time - _start), (round ((_l # 1) * 100)) / 100, (round ((_l # 3) * 100)) / 100, (round ((_x getVariable ["none", 0]) * 100)) / 100]
};
private _rows = [];
private _fired = false;
for "_i" from 1 to 24 do {
	if (not _fired and {time - _start > 30}) then {
		_fired = true;
		if (_how isNotEqualTo "none") then { _gun doArtilleryFire [_at, _how, 2]; };
	};
	private _l = getLightingAt (units _good # 0);
	private _knows = (units _good) apply {_x knowsAbout (units _bad # 0)};
	private _seen = {_x > 0} count ((units _good # 0) targets [true, 400] apply {1});
	_rows pushBack [round (time - _start), (round ((_l # 1) * 100)) / 100, (round ((_l # 3) * 100)) / 100, (round (10 * selectMax _knows)) / 10, _seen];
	sleep 5;
};
private _shells = (_gun getVariable "brmh_shells") apply {[(_x get "fired") - _start, (_x getOrDefault ["landed", -1]) - _start, (_x getOrDefault ["gone", -1]) - _start, _x getOrDefault ["pos", []], _x getOrDefault ["lastPos", []], _x get "ammo"]};
missionNamespace setVariable ["brmh_spike_" + _name, [_how, _rows, _shells]];
"""
names.clear()
for index, how in enumerate(("none", "8Rnd_82mm_Mo_Flare_white", "8Rnd_82mm_Mo_Flare_white_illumination")):
    launch(f"flare_{index}", FLARE, [1000 + 1500 * index, 6500, 0], how)
out = collect(names, 150)
for name in names:
    show(name, out.get(name, "NOT FINISHED"))
h.stop()
print("stopped", flush=True)
