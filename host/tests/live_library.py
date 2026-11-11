"""Live check of the command library: every command's example, run in a real game.

    host\\.venv\\Scripts\\python.exe host\\tests\\live_library.py

It boots the demo_vr mission headless if nothing is running (LIVE_WATCH=1 adds a game window, which unit_in_view
needs: without one it's skipped), stands a test soldier in for the player, and runs each example with "player"
meaning him. list_made and delete_made run last, and clean up everything the others made. It never touches a game
you attached to: it stops if one is.
"""
from __future__ import annotations

import json
import os
import sys

from arma_harness import library
from arma_harness.harness import Harness

LAST = ["list_made", "delete_made"]
STAND_IN = """
private _group = createGroup [west, true];
private _man = _group createUnit ["B_Soldier_F", [4100, 4120, 0], [], 0, "NONE"];
_man setName "Tester";
netId _man
"""


def stand_in(value, man: str):
    if value == "player":
        return man
    if isinstance(value, dict):
        return {key: stand_in(item, man) for key, item in value.items()}
    return value


def main() -> int:
    h = Harness()
    h.forget_dead_run()
    state = h.state()
    if state is not None and state.mode == "attached":
        print("A game you attached to is running: this test won't touch it. Detach (arma-harness stop) first.")
        return 1
    watching = bool(os.environ.get("LIVE_WATCH")) and not os.environ.get("LIVE_NO_WATCH")
    if state is None:
        print("booting demo_vr" + (" with a game window" if watching else ", headless"))
        h.start(mission="demo_vr", client=watching)
    made = h.exec(STAND_IN, "server", timeout=15)
    man = made["results"][0]["r"]
    print(f"stand-in for the player: {man}")
    names = [name for name in library.commands() if name not in LAST] + LAST
    failed = []
    for name in names:
        command = library.commands()[name]
        if command.target == "interface" and not watching:
            print(f"  skip  {name} (needs a game window: LIVE_WATCH=1)")
            continue
        # After the defaults are filled in: most commands mean the player by default, and there's none headless.
        args = library.bind(command, command.example)
        if command.target == "server":
            args = [stand_in(value, man) for value in args]
        result = library.run(h, name, args)
        mark = "ok  " if result["ok"] else "FAIL"
        shown = json.dumps(result.get("result") if result["ok"] else result, default=str)
        print(f"  {mark}  {name}: {shown[:160]}")
        if not result["ok"]:
            failed.append(name)
    print(f"\n{len(names) - len(failed)} of {len(names)} ran" + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
