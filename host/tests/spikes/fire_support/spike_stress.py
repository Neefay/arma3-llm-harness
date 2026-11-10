"""What can be measured of a group's stress? Samples a real firefight, a squad under mortar fire, and a calm squad far off."""
from __future__ import annotations

import time

from spike_arty_lib import TRACK, game, run

h = game()
run(h, TRACK)
SETUP = """
brmh_s_groups = createHashMap;
private _squad = {
	params ["_name", "_at", "_side", "_count"];
	private _group = createGroup [_side, false];
	for "_i" from 1 to _count do {
		private _man = _group createUnit [["B_Soldier_F", "O_Soldier_F"] select (_side isEqualTo east), _at, [], 6, "NONE"];
		_man disableAI "PATH";
		_man setVariable ["brmh_s_group", _name];
		_man addEventHandler ["Fired", { private _n = (_this # 0) getVariable "brmh_s_group"; brmh_s_fired set [_n, (brmh_s_fired getOrDefault [_n, 0]) + 1]; }];
		_man addEventHandler ["FiredNear", { private _n = (_this # 0) getVariable "brmh_s_group"; brmh_s_near set [_n, (brmh_s_near getOrDefault [_n, 0]) + 1]; }];
		_man addEventHandler ["Suppressed", { private _n = (_this # 0) getVariable "brmh_s_group"; brmh_s_supp set [_n, (brmh_s_supp getOrDefault [_n, 0]) + 1]; }];
		_man addEventHandler ["Explosion", { private _n = (_this # 0) getVariable "brmh_s_group"; brmh_s_boom set [_n, (brmh_s_boom getOrDefault [_n, 0]) + 1]; }];
		_man addEventHandler ["Hit", { private _n = (_this # 0) getVariable "brmh_s_group"; brmh_s_hit set [_n, (brmh_s_hit getOrDefault [_n, 0]) + 1]; }];
	};
	brmh_s_groups set [_name, _group];
	_group
};
brmh_s_fired = createHashMap; brmh_s_near = createHashMap; brmh_s_supp = createHashMap; brmh_s_boom = createHashMap; brmh_s_hit = createHashMap;
["west", [1500, 1500, 0], west, 8] call _squad;
["east", [1500, 1650, 0], east, 8] call _squad;
{ _x reveal [leader (brmh_s_groups get "east"), 4]; } forEach units (brmh_s_groups get "west");
{ _x reveal [leader (brmh_s_groups get "west"), 4]; } forEach units (brmh_s_groups get "east");
["calm", [3500, 1500, 0], west, 4] call _squad;
["shelled", [5500, 1500, 0], west, 4] call _squad;
brmh_s_gun = ["B_Mortar_01_F", [5500, 700]] call brmh_spike_fnc_gun;
true
"""
SAMPLE = """
private _out = [];
{
	private _men = units _y select {alive _x};
	private _name = _x;
	private _fresh = 0;
	if (_men isNotEqualTo []) then {
		private _leader = _men # 0;
		{ if (time - ((_leader targetKnowledge _x) # 2) < 15) then { _fresh = _fresh + 1; }; } forEach (_leader targets [true, 1000]);
	};
	_out pushBack [_name, count _men,
		if (_men isEqualTo []) then {""} else {behaviour (_men # 0)},
		if (_men isEqualTo []) then {0} else {round (100 * selectMax (_men apply {getSuppression _x}))},
		if (_men isEqualTo []) then {0} else {round (100 * ((_men apply {getSuppression _x}) call BIS_fnc_arithmeticMean))},
		_fresh,
		brmh_s_fired getOrDefault [_name, 0], brmh_s_near getOrDefault [_name, 0], brmh_s_supp getOrDefault [_name, 0], brmh_s_boom getOrDefault [_name, 0], brmh_s_hit getOrDefault [_name, 0]];
} forEach brmh_s_groups;
_out
"""
run(h, SETUP)
time.sleep(4)
print("group alive behaviour maxSupp% meanSupp% freshTargets | fired near suppressed explosions hits (running totals)", flush=True)
started = time.time()
fired = False
while time.time() < started + 100:
    now = round(time.time() - started)
    if now >= 30 and not fired:
        # The west/east fight is well on by now. Now shell the squad that's been calm so far.
        run(h, 'brmh_s_gun doArtilleryFire [(getPos leader (brmh_s_groups get "shelled")) vectorAdd [90, 0, 0], "8Rnd_82mm_Mo_shells", 8]; true')
        fired = True
    rows = {row[0]: row for row in run(h, SAMPLE)}
    print(f"t={now:>3}  " + "  ".join(
        f"{name[:4]} {rows[name][1]} {rows[name][2][:4]} s{rows[name][3]}/{rows[name][4]} k{rows[name][5]} f{rows[name][6]} n{rows[name][7]} S{rows[name][8]} E{rows[name][9]} H{rows[name][10]}"
        for name in ("west", "east", "calm", "shelled")), flush=True)
    time.sleep(5)
h.stop()
print("stopped", flush=True)
