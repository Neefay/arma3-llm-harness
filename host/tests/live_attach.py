"""Live check (needs the game): attach to an Arma process the harness did not launch.

Starts a dedicated server by hand (as a user would start their game), verifies the probe stays inert
without a session file, then attaches, executes SQF, detaches, and kills the server.
Run: host/.venv/Scripts/python host/tests/live_attach.py
"""
from __future__ import annotations

import secrets
import time

from arma_harness import missions, procutil, serverroot
from arma_harness.config import load_config
from arma_harness.harness import SERVER_EXE, Harness, _pick_game_port, _server_cfg


def main() -> None:
    h = Harness()
    cfg = load_config()
    assert h.state() is None, "stop the current run first"
    profile = cfg.mission("selftest")
    root = h.home.server_root
    serverroot.ensure(cfg.arma_dir, root)
    missions.stage(profile.source, root / "MPMissions")
    run_dir = h.home.runs / ("manual-" + time.strftime("%H%M%S"))
    (run_dir / "server").mkdir(parents=True)
    (run_dir / "server.cfg").write_text(_server_cfg(profile.folder_name, secrets.token_hex(4)), encoding="utf-8")
    mods = ";".join(str(cfg.mod_path(m)) for m in profile.mods)
    pid = procutil.spawn([str(root / SERVER_EXE), f"-port={_pick_game_port()}", f"-config={run_dir / 'server.cfg'}",
                          f"-profiles={run_dir / 'server'}", "-autoInit", "-noSound", f"-mod={mods}"], root)
    print("manual server pid", pid)
    try:
        time.sleep(25)  # mission loaded; the probe has been retrying start() every 2 s
        port_file = h.home.sessions / f"{pid}.port.json"
        assert not port_file.exists(), "bridge must stay inert without a session file"
        print("inert without session file: OK")
        t0 = time.time()
        res = h.attach(pid=pid)
        print(f"attached in {time.time() - t0:.1f}s, bridge port {res['bridge_port']}")
        r = h.exec("[worldName, missionName, isServer]")
        print("exec:", r["results"][0]["r"])
        assert r["ok"]
        st = h.stop()
        assert st["mode"] == "attached" and st["stopped"] == [], st
        assert procutil.alive(pid), "detach must not kill a game the harness did not launch"
        print("detached, game still running: OK")
    finally:
        procutil.kill_tree(pid)


if __name__ == "__main__":
    main()
