"""Run the terrain sampler around Camp Maxwell, and keep its output for building the map offline."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "move_lag"))
from spike_lib import in_fresh_game  # noqa: E402

from arma_harness.commander.operator import load_sqf  # noqa: E402

harness, run = in_fresh_game("commander_stratis")
run(load_sqf("commander_boot.sqf"))
started = time.time()
raw = run("[[3150, 2550], 1500, 50] call brmh_cmd_fnc_terrain")
took = time.time() - started
head, cells, roads, houses, places = raw
print("took", round(took, 1), "s;", head, len(cells), "cells,", len(roads), "road stretches,", len(houses), "houses,",
      len(places), "places", [p[0] for p in places])
heights = [c[0] for c in cells]
print("heights", min(heights), "to", max(heights), "; water cells", sum(c[1] for c in cells),
      "; trees per cell max", max(c[2] for c in cells))
out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("terrain_maxwell.json")
out.write_text(json.dumps(raw), encoding="utf-8")
print("saved", out, out.stat().st_size, "bytes")
harness.stop()
