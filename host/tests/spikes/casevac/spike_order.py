"""CARRY through the commander's tools, with the game's state printed as it goes."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from live_commander import Client, begin, finish_turn, in_game  # noqa: E402

from arma_harness.commander import operator  # noqa: E402
from arma_harness.harness import Harness  # noqa: E402

harness = Harness()
operator.start("casevac_rv", "hold", harness, watch=False)
client = Client()
begin(client)
finish_turn(client, "x")
in_game(harness, """
missionNamespace setVariable ["ace_medical_spontaneousWakeUpChance", 0, true];
private _men = (units (brmh_cmd_stations get "Alpha")) - [leader (brmh_cmd_stations get "Alpha")];
{
    [_x, true, 0, false] call ace_medical_fnc_setUnconscious;
} forEach (_men select [0, 2]);
true
""")
time.sleep(5)
print(client.tool("commander_mission")["casualties"], flush=True)
print(client.tool("commander_order", to="Alpha", legs=[{"type": "CARRY", "casualties": ["C1", "C2"], "vehicle": "V1"}]), flush=True)
READ = """
[count brmh_cmd_carries, not isNil "brmh_cmd_carryPfh",
 brmh_cmd_carries apply {
    [_x get "state", _x get "tries", round ((_x get "medic") distance (_x get "casualty")), round speed (_x get "medic"),
     currentCommand (_x get "medic"), unitReady (_x get "medic"), name (_x get "medic"), animationState (_x get "medic"),
     lifeState (_x get "casualty"), str (_x getOrDefault ["to", 0])]
 },
 (brmh_cmd_stations get "Alpha") getVariable ["brmh_cmd_care", []],
 name leader (brmh_cmd_stations get "Alpha")]
"""
for i in range(24):
    time.sleep(5)
    print((i + 1) * 5, json.dumps(in_game(harness, READ))[:520], flush=True)
errors = harness.events(since=0, kinds=["err"]).get("events", [])
print("errors", len(errors), [str(e.get("text"))[:200] + " | " + str(e.get("near"))[:160] for e in errors[:5]], flush=True)
client.close()
harness.stop()
print("done", flush=True)
