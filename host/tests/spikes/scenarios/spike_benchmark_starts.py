"""Start each benchmark scenario on a real game and check its battle is set up as drawn: every enemy group there with
men (a gun with its crew), every station enrolled, and no script errors. One seed per hidden spot that's rarely drawn.

    spike_benchmark_starts.py [--stop]
"""
import sys

from arma_harness.commander import operator, scenario
from arma_harness.commander.operator import _read_raw
from arma_harness.harness import Harness

CHECKS = [("llm_hidden_gun", 116), ("llm_hidden_gun", 40), ("llm_two_roads", 7), ("llm_decoy", 4),
          ("llm_silence", 7), ("llm_guns_only", 7), ("llm_guns_only", 5), ("llm_danger_close", 1)]
harness = Harness()
failures = []
for name, seed in CHECKS:
    resolved, _, _ = scenario.draw(_read_raw(name), seed)
    since = harness.bridge().cursor() if harness.state() is not None else 0
    started = operator.start(name, None, harness, seed=seed)
    res = harness.exec("""
    [brmh_cmd_enemies apply { [groupId _x, { alive _x } count units _x, (units _x) apply { typeOf vehicle _x }] },
     (keys brmh_cmd_stations) apply { [_x, { alive _x } count units (brmh_cmd_stations get _x)] }]
    """, "server", timeout=30, strip=False)
    enemies, stations = res["results"][0]["r"]
    errors = harness.events(since=since, kinds=["err"], limit=0).get("events", [])
    wanted = {enemy["id"] for enemy in resolved.get("enemies") or []}
    present = {group for group, men, _ in enemies if men > 0}
    problems = []
    if wanted - present:
        problems.append(f"missing enemies {sorted(wanted - present)}")
    if {s["callsign"] for s in resolved["stations"]} - {name for name, men in stations if men > 0}:
        problems.append("a station has nobody")
    if errors:
        problems.append(f"script errors {errors[:2]}")
    print(f"{name} seed {seed}: {scenario.hidden(resolved)}", flush=True)
    print(f"   enemies {[(g, n, sorted(set(t))) for g, n, t in enemies]}", flush=True)
    print(f"   stations {stations}", flush=True)
    print(f"   {'OK' if not problems else 'PROBLEM: ' + '; '.join(problems)}", flush=True)
    if problems:
        failures.append((name, seed, problems))
print("ALL OK" if not failures else f"FAILED: {failures}")
print(harness.stop() if "--stop" in sys.argv else "game left up")
