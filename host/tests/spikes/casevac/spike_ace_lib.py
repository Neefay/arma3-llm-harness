"""Shared bits for the CASEVAC spikes. A headless game with ACE on open VR ground, away from the village."""
from __future__ import annotations

import json
import time

from arma_harness.harness import Harness

AREA = [1500.0, 1500.0]


def game() -> Harness:
    harness = Harness()
    harness.forget_dead_run()
    if harness.state() is None:
        print("booting", flush=True)
        harness.start(mission="commander_ace")
        time.sleep(10)
    return harness


def run(harness: Harness, code: str, args: list | None = None, timeout: float = 30):
    res = harness.exec(code, "server", timeout=timeout, args=args, strip=False)
    result = res["results"][0] if res.get("results") else res
    if not res.get("ok") or result.get("errors"):
        raise RuntimeError(json.dumps(result)[:1800])
    return result.get("r")


def show(label: str, value) -> None:
    print(f"{label}: {json.dumps(value, ensure_ascii=False)}", flush=True)


# Soldiers in a group at a place, in a line along x, standing still until told otherwise.
SQUAD = """
params ["_side", "_at", "_count", ["_class", "B_Soldier_F"], ["_spacing", 4]];
private _group = createGroup [[west, east] select (_side isEqualTo "east"), false];
for "_i" from 0 to (_count - 1) do {
    _group createUnit [_class, [(_at # 0) + _i * _spacing, _at # 1, 0], [], 0, "CAN_COLLIDE"];
};
_group
"""

STATE = """
params ["_units"];
private _medical = isClass (configFile >> "CfgPatches" >> "ace_medical");
_units apply {
    [name _x, alive _x, _x getVariable ["ACE_isUnconscious", false], lifeState _x, captive _x,
     round (damage _x * 100) / 100, _x getVariable ["ace_medical_inCardiacArrest", false],
     round (_x getVariable ["ace_medical_bloodVolume", 6]), (getPosATL _x) select [0, 2]]
}
"""
