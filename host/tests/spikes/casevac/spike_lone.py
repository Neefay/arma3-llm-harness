"""A man whose squad's gone, treated by medics from another station, with the game's state printed as it goes."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from live_commander import Client, begin, finish_turn, in_game  # noqa: E402

from arma_harness.commander import operator  # noqa: E402
from arma_harness.harness import Harness  # noqa: E402

harness = Harness()
operator.start("casevac_cases", "hold", harness, watch=False)
client = Client()
begin(client)
finish_turn(client, "x")
lone = in_game(harness, """
missionNamespace setVariable ["ace_medical_spontaneousWakeUpChance", 0, true];
private _group = brmh_cmd_stations get "Lone";
private _men = units _group;
{ _x setDamage 1; } forEach (_men select [1, 3]);
[_men # 0, true, 0, false] call ace_medical_fnc_setUnconscious;
{ _x setPosATL ((getPosATL (_men # 0)) getPos [15 + random 5, random 360]); }
    forEach units (brmh_cmd_stations get "Medics");
name (_men # 0)
""")
time.sleep(6)
print("mission", client.tool("commander_mission")["casualties"], flush=True)
print(client.tool("commander_order", to="Medics", legs=[{"type": "TREAT"}]), flush=True)
READ = """
private _group = brmh_cmd_stations get "Medics";
[brmh_cmd_treats apply {
    [count (_x get "queue"), (_x get "jobs") apply {
        [_x get "state", _x get "tries", name (_x get "medic"), round ((_x get "medic") distance (_x get "casualty")),
         lifeState (_x get "casualty"), round speed (_x get "medic"), currentCommand (_x get "medic")]
    }]
 },
 (units _group) apply {[name _x, [_x] call brmh_cmd_fnc_isMedic, _x getVariable ["brmh_cmd_busy", false]]},
 _group getVariable ["brmh_cmd_care", []],
 brmh_cmd_down apply {[name _x, round (_x distance2D leader _group), lifeState _x]}]
"""
for i in range(14):
    time.sleep(5)
    print((i + 1) * 5, json.dumps(in_game(harness, READ))[:600], flush=True)
print(in_game(harness, 'units (brmh_cmd_stations get "Medics") apply {name _x}'), flush=True)
errors = harness.events(since=0, kinds=["err"]).get("events", [])
print("errors", len(errors), [str(e.get("text"))[:200] + " | " + str(e.get("near"))[:160] for e in errors[:5]], flush=True)
client.close()
harness.stop()
print("done", flush=True)
