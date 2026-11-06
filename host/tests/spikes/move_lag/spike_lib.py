"""A plain headless game, for measuring things."""
import json
import time

from arma_harness.harness import Harness


def in_fresh_game(mission: str = "commander"):
    harness = Harness()
    harness.forget_dead_run()
    if harness.state() is None:
        harness.start(mission=mission)
        time.sleep(10)

    def run(code: str):
        res = harness.exec(code, "server", timeout=30, strip=False)
        result = res["results"][0] if res.get("results") else res
        if not res.get("ok") or result.get("errors"):
            raise RuntimeError(json.dumps(result)[:1500])
        return result.get("r")

    return harness, run
