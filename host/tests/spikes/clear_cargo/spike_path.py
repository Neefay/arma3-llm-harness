"""Can the engine's own path planner tell which building positions AI can reach? At Camp Maxwell, soldiers got into
B5's position and stood 3 m outside B3's and B4's (same cargo house, placed differently). For each position, plan a
path from 40 m away and see how close its end comes.

    spike_path.py commander_stratis 3250 2950 150
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "move_lag"))
from spike_lib import in_fresh_game  # noqa: E402

mission, x, y, radius = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
harness, run = in_fresh_game(mission)
time.sleep(5)
count = run(f"""
spike_paths = [];
spike_jobs = [];
{{
    private _house = _x;
    {{
        private _spot = _x;
        private _from = _house getPos [40, (_house getDir _spot) + 180];
        private _agent = calculatePath ["man", "SAFE", _from, _spot];
        _agent setVariable ["spike_job", [typeOf _house, getPosATL _house apply {{round _x}}, _forEachIndex, _spot]];
        _agent addEventHandler ["PathCalculated", {{
            params ["_agent", "_path"];
            if (isNil {{_agent getVariable "spike_done"}}) then {{
                _agent setVariable ["spike_done", true];
                (_agent getVariable "spike_job") params ["_type", "_at", "_index", "_spot"];
                private _end = _path param [count _path - 1, [0, 0, 0]];
                spike_paths pushBack [_type, _at, _index, round ((_end distance2D _spot) * 10) / 10,
                    round ((((_end # 2) - (_spot # 2))) * 10) / 10, count _path];
            }};
        }}];
        spike_jobs pushBack _agent;
    }} forEach (_house buildingPos -1);
}} forEach (nearestObjects [[{x}, {y}], ["House"], {radius}] select {{ count (_x buildingPos -1) > 0 }});
count spike_jobs
""")
print("planning", count, "paths", flush=True)
time.sleep(15)
rows = run("spike_paths")
for row in sorted(rows, key=lambda r: (r[1], r[2])):
    print("  ", row)
print(len(rows), "of", count, "answered")
print(harness.stop() if "--stop" in sys.argv else "game left up")
