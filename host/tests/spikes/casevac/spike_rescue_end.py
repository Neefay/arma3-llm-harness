"""The end of spike_rescue.py, on the game it left running, after a typo stopped it."""
import time

from spike_ace_lib import run, show

from arma_harness.harness import Harness

harness = Harness()
print("minutes up", round(run(harness, "time") / 60, 1), flush=True)
show("hits [time, who, by]", run(harness, "brmh_h_shots"))
show("who's who [medic, body]", run(harness, "[name brmh_h_medic, name brmh_h_hurt]"))
READ = """
private _alive = brmh_j select {alive _x};
[round (time - brmh_j_start), count _alive, {_x getVariable ["ACE_isUnconscious", false]} count _alive,
 {_x getVariable ["ace_medical_inCardiacArrest", false]} count _alive, brmh_j_died,
 _alive apply {round ((_x getVariable ["ace_medical_bloodVolume", 6]) * 10) / 10},
 _alive apply {round (_x getVariable ["ace_medical_heartRate", 0])},
 _alive apply {round ((_x getVariable ["ace_medical_woundBleeding", 0]) * 100) / 100}]
"""
show("untreated [s, alive, down, arrest, died, blood, heart, bleeding]", run(harness, READ))
print("  [men, alive, unconscious, arrest, injured, dead who'd been down, ever down]", flush=True)
show("fights", run(harness, "[brmh_fights # 0 + (brmh_fights # 1) + (brmh_fights # 2)] call brmh_fnc_tally"))
run(harness, """
brmh_k_killed = 0;
["ace_unconscious", {
    params ["_unit", "_state"];
    if (_state and {local _unit} and {not isPlayer _unit} and {random 1 < 0.5}) then {
        brmh_k_killed = brmh_k_killed + 1;
        _unit setDamage 1;
    };
}] call CBA_fnc_addEventHandler;
brmh_k = [];
private _group = createGroup [west, false];
for "_i" from 0 to 11 do {
    private _man = _group createUnit ["B_Soldier_F", [6000 + _i * 6, 1000, 0], [], 0, "CAN_COLLIDE"];
    _man setVariable ["ace_medical_ai_lastFired", CBA_missionTime + 86400];
    brmh_k pushBack _man;
    [_man, true, 0, false] call ace_medical_fnc_setUnconscious;
};
true
""")
time.sleep(8)
show("handler [killed by it, dead, still down]", run(harness, """
[brmh_k_killed, {not alive _x} count brmh_k, {alive _x and {_x getVariable ["ACE_isUnconscious", false]}} count brmh_k]
"""))
errors = harness.events(since=0, kinds=["err"]).get("events", [])
print("script errors", len(errors), [str(e)[:220] for e in errors[:6]], flush=True)
time.sleep(120)
show("untreated, later", run(harness, READ))
harness.stop()
print("done", flush=True)
