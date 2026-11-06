"""How fast does a squad really go, for the estimates in its replies? Eight men, on open ground, for a minute of each."""
import math
import time

from spike_lib import in_fresh_game

SPEEDS = ["LIMITED", "NORMAL", "FULL"]
BEHAVIOURS = ["CARELESS", "SAFE", "AWARE", "COMBAT", "STEALTH"]


def main():
    harness, run = in_fresh_game()
    run("""
    brmh_rows = [];
    private _y = 1000;
    {
        private _speed = _x;
        {
            private _group = createGroup [west, true];
            for "_i" from 0 to 7 do {
                _group createUnit ["B_Soldier_F", [1000 + _i * 4, _y, 0], [], 0, "NONE"];
            };
            _group setSpeedMode _speed;
            _group setBehaviour _x;
            _group setFormation "WEDGE";
            private _wp = _group addWaypoint [[7000, _y, 0], 0];
            _group setCurrentWaypoint _wp;
            brmh_rows pushBack [_speed, _x, _group, getPosATL leader _group];
            _y = _y + 120;
        } forEach %s;
    } forEach %s;
    true
    """ % (str(BEHAVIOURS).replace("'", '"'), str(SPEEDS).replace("'", '"')))
    time.sleep(20)
    first = run("brmh_rows apply {getPosATL leader (_x # 2)}")
    time.sleep(120)
    last = run("brmh_rows apply {[_x # 0, _x # 1, behaviour leader (_x # 2), getPosATL leader (_x # 2)]}")
    for start, (speed, behaviour, became, end) in zip(first, last, strict=True):
        print(f"{speed:8} {behaviour:8} became {became:8} {math.dist(start[:2], end[:2]) / 120:4.1f} m/s", flush=True)
    harness.stop()


if __name__ == "__main__":
    main()
