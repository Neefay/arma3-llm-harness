"""What can a squad know about its wounded? Leg damage slowed a leader while damage read 0 and nobody counted as wounded.

Part 1 gives each squad's leader a set wound and walks it 40 s. Part 2 is a real firefight, listing every wound bullets
really leave, because a set wound may not look like one.
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

SCENARIO = str(Path(__file__).parent / "wounds.yaml")
SET_WOUNDS = {
    "Fit": "true",
    "Legs3": '_this setHitPointDamage ["hitLegs", 0.3]',
    "Legs5": '_this setHitPointDamage ["hitLegs", 0.5]',
    "Legs6": '_this setHitPointDamage ["hitLegs", 0.6]',
    "Legs9": '_this setHitPointDamage ["hitLegs", 0.9]',
    "Whole4": "_this setDamage 0.4",
    "Whole7": "_this setDamage 0.7",
    "Body": '_this setHitPointDamage ["hitBody", 0.6]',
}
ONE = """
private _m = _this;
[name _m, round (damage _m * 100) / 100, round ((_m getHitPointDamage "hitLegs") * 100) / 100,
 round ((_m getHitPointDamage "hitArms") * 100) / 100, round ((_m getHitPointDamage "hitBody") * 100) / 100,
 lifeState _m, canStand _m, round (speed _m), behaviour _m]
"""
READ = f"""
_this apply {{
    private _leader = leader (brmh_cmd_stations get _x);
    private _row = _leader call {{ {ONE} }};
    [_x, (getPosATL _leader) select [0, 2], _row]
}}
"""
EVERYONE = f"""
private _out = [];
{{
    private _callsign = _x;
    {{
        private _row = _x call {{ {ONE} }};
        _out pushBack ([_callsign, leader group _x isEqualTo _x] + _row);
    }} forEach ((units (brmh_cmd_stations get _callsign)) select {{ alive _x }});
}} forEach _this;
_out
"""


def main():
    harness = Harness()
    operator.start(SCENARIO, "hold", harness, watch=False)
    client = Client()
    begin(client)
    finish_turn(client, "x")
    names = list(SET_WOUNDS)
    for name, wound in SET_WOUNDS.items():
        in_game(harness, f'(leader (brmh_cmd_stations get "{name}")) call {{ {wound} }}; true')
    print("WOUNDS AS SET", flush=True)
    for name, _, row in in_game(harness, READ, names):
        print(f"  {name:7}", row, flush=True)
    for index, name in enumerate(names):
        client.tool("commander_order", to=name, legs=[{"type": "MOVE", "at": f"{20 + index * 4:03d} 030"}])
    start = {name: pos for name, pos, _ in in_game(harness, READ, names)}
    time.sleep(40)
    print("AFTER 40 s", flush=True)
    for name, pos, row in in_game(harness, READ, names):
        print(f"  {name:7} {round(math.dist(pos, start[name])):4d} m", row, flush=True)

    fighters = ["FightA", "FightB"]
    print("REAL BULLETS", flush=True)
    seen = {}
    for _ in range(14):
        time.sleep(6)
        for row in in_game(harness, EVERYONE, fighters):
            who = row[2]
            if row[3] or row[4] or row[5] or row[6] or row[7] != "HEALTHY":
                seen[who] = row
    for row in seen.values():
        print("  ", json.dumps(row), flush=True)
    print("hurt men seen", len(seen), flush=True)
    client.close()
    harness.stop()


if __name__ == "__main__":
    main()
