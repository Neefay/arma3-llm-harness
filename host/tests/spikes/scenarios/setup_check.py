"""Sets up each commander-test scenario with a few seeds and checks it places: stations, enemies (garrisons only where
soldiers can reach), vehicles and crews. Nothing is played. A setup check, not a test of anybody's command.

    setup_check.py llm_guns_only llm_danger_close ...
"""
import json
import sys
import time
from pathlib import Path

from arma_harness.commander import operator
from arma_harness.harness import Harness

harness = Harness()


def run(code: str):
    res = harness.exec(code, "server", timeout=30, strip=False)
    result = res["results"][0] if res.get("results") else res
    if not res.get("ok") or result.get("errors"):
        raise RuntimeError(str(result)[:1500])
    return result.get("r")


failed = []
for name in [arg for arg in sys.argv[1:] if not arg.startswith("--")]:
    for seed in (5, 6):
        started = time.time()
        try:
            out = operator.start(name, None, harness, seed=seed)
        except Exception as exc:  # report and carry on with the rest
            failed.append(f"{name} seed {seed}: {exc}")
            print(f"FAIL {name} seed {seed}: {exc}", flush=True)
            continue
        battle = json.loads((Path(out["records"]).parent / "battle.json").read_text(encoding="utf-8"))
        placed = run("""
        [brmh_cmd_stations toArray false apply { [_x # 0, count units (_x # 1)] },
         brmh_cmd_enemies apply { [groupId _x, count units _x] },
         brmh_cmd_vehicles toArray false apply {
             [_x # 0, typeOf (_x # 1), count crew (_x # 1), round ((getPosATL (_x # 1)) # 2)] }]
        """)
        print(f"ok {name} seed {seed} in {time.time() - started:.0f} s; drawn {battle['drawn']}", flush=True)
        print("   stations", placed[0], "\n   enemies", placed[1], "\n   vehicles", placed[2], flush=True)
print("\nFAILED:\n" + "\n".join(failed) if failed else "\nALL SET UP")
print(harness.stop() if "--stop" in sys.argv else "game left up")
