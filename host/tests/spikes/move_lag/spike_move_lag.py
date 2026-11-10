"""Why did squads "acknowledge a withdrawal and stay put" in the mortar battle? Four questions, on the real game:

- Does reissuing the same MOVE reset a squad, out of contact and under fire?
- Does a leader with hurt legs set the whole squad's pace? Alpha walked at 0.8 m/s for 8 minutes.
- Is a squad slow after CLEAR?
- Does a lone survivor under fire move at all? Recon's last man didn't, for 100 s.
"""
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from live_commander import Client, begin, finish_turn, in_game  # noqa: E402

from arma_harness.commander import operator  # noqa: E402
from arma_harness.harness import Harness  # noqa: E402

SCENARIO = str(Path(__file__).parent / "move_lag.yaml")
QUIET = ["Once", "Again", "Limp"]
CLEARED = "Cleared"
FIRE = ["FireOnce", "FireAgain", "Lone"]
LOOK = """
_this apply {
    private _group = brmh_cmd_stations get _x;
    private _leader = leader _group;
    [_x, (getPosATL _leader) select [0, 2], behaviour _leader, {alive _x} count units _group, currentCommand _leader,
     round (speed _leader), unitPos _leader, damage _leader]
}
"""


def track(harness, names, seconds, reissue=None, every=15):
    """Each squad's leader every 5 s, printed as metres from its start."""
    start, begun, last = {}, time.time(), time.time()
    while time.time() - begun < seconds:
        rows = in_game(harness, LOOK, names)
        now = round(time.time() - begun)
        cells = []
        for name, pos, behaviour, alive, command, speed, stance, damage in rows:
            start.setdefault(name, pos)
            cells.append(f"{name} {round(math.dist(pos, start[name])):4d}m {behaviour[:3]} n{alive} {speed:2d}km/h "
                         f"{command[:6]} d{damage:.1f}")
        print(f"{now:3d}s | " + " | ".join(cells), flush=True)
        if reissue and time.time() - last >= every:
            reissue()
            last = time.time()
        time.sleep(5)
    return {name: round(math.dist(pos, start[name])) for name, pos, *_ in rows}


def main():
    harness = Harness()
    operator.start(SCENARIO, "hold", harness, watch=False)
    client = Client()
    brief = begin(client)
    finish_turn(client, "x")
    results = {}

    print("\n=== 1. Reissuing, out of contact", flush=True)

    def order(name, at, **extra):
        return client.tool("commander_order", to=name, legs=[{"type": "MOVE", "at": at}], **extra)

    in_game(harness, 'leader (brmh_cmd_stations get "Limp") setHitPointDamage ["hitLegs", 0.6]; true')
    order("Once", "020 026")
    order("Again", "024 026")
    order("Limp", "028 026")
    results["quiet"] = track(harness, QUIET, 60, reissue=lambda: order("Again", "024 026"))

    print("\n=== 2. Slow after CLEAR?", flush=True)
    building = brief["buildings"][0]
    client.tool("commander_order", to=CLEARED, legs=[{"type": "CLEAR", "at": [building["id"]]}])
    time.sleep(45)
    order(CLEARED, "036 020")
    results["cleared"] = track(harness, [CLEARED], 50)

    print("\n=== 3. Under fire, ordered back: once, reissued, and a lone man", flush=True)
    time.sleep(1)
    posture = {"behaviour": "SAFE", "combat_mode": "GREEN", "speed": "FULL"}
    # let the firefight start
    print(in_game(harness, LOOK, FIRE), flush=True)
    time.sleep(25)
    print(in_game(harness, LOOK, FIRE), flush=True)
    order("FireOnce", "060 050", **posture)
    order("FireAgain", "064 050", **posture)
    order("Lone", "068 050", **posture)
    results["fire"] = track(harness, FIRE, 75, reissue=lambda: order("FireAgain", "064 050", **posture))
    print("\nRESULTS", json.dumps(results), flush=True)
    client.close()
    harness.stop()


if __name__ == "__main__":
    main()
