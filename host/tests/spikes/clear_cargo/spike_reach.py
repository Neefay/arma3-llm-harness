"""How close does a soldier sent to each position of a building really get? Min distance across and height difference.

    spike_reach.py commander 4030 4120        (the VR village's B2, House (Small, Stone))
    spike_reach.py commander_stratis 3318 2940
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "move_lag"))
from spike_lib import in_fresh_game  # noqa: E402

mission, x, y = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
harness, run = in_fresh_game(mission)
time.sleep(5)
house = run(f"""
spike_house = (nearestObjects [[{x}, {y}], ["House"], 8] select {{ count (_x buildingPos -1) > 0 }}) # 0;
[typeOf spike_house, (spike_house buildingPos -1) apply {{ _x apply {{ round (_x * 10) / 10 }} }}]
""")
print("house", house, flush=True)
for index, spot in enumerate(house[1]):
    run(f"""
    {{ deleteVehicle _x }} forEach (missionNamespace getVariable ["spike_men", []]);
    private _w = (createGroup [west, true]) createUnit ["B_Soldier_F", spike_house getPos [15, 180], [], 0, "NONE"];
    spike_men = [_w]; spike_spot = {spot}; spike_best = [99, 99];
    _w doMove spike_spot; true
    """)
    started = time.time()
    while time.time() - started < 50:
        time.sleep(2)
        state = run("""
        private _w = spike_men # 0;
        private _d = [_w distance2D spike_spot, abs (((getPosATL _w) # 2) - (spike_spot # 2))];
        if ((_d # 0) < (spike_best # 0)) then { spike_best = _d };
        [unitReady _w, spike_best apply { round (_x * 100) / 100 }]
        """)
        if state[0] and time.time() - started > 6:
            break
    took = round(time.time() - started)
    print(f"  spot {index} {spot}: ready={state[0]} best [across, dz] = {state[1]} after {took} s",
          flush=True)
print(harness.stop() if "--stop" in sys.argv else "game left up")
