"""Offline tests: everything that can be verified without the game."""
from __future__ import annotations

import importlib.util
import json
import threading
import time
from pathlib import Path

import pytest

from arma_harness import missions, rap, sqf
from arma_harness.adapters import boot_items
from arma_harness.bridge import Bridge
from arma_harness.config import REPO_ROOT, load_config
from arma_harness.harness import _server_cfg, _svg_locations
from arma_harness.matching import matcher, matches, validate
from arma_harness.scenario import load as load_scenario

# -- sqf ----------------------------------------------------------------------------------------


def test_strip_comments_keeps_strings_and_lines():
    src = 'a = "// not a comment"; // gone\nb = 1; /* x\ny */ c = \'/*k*/\';'
    out = sqf.strip_comments(src)
    assert '"// not a comment"' in out and "gone" not in out and "'/*k*/'" in out
    assert out.count("\n") == src.count("\n")


def test_strip_comments_doubled_quotes():
    assert sqf.strip_comments('x = "he said ""hi"" // ok"; // c') == 'x = "he said ""hi"" // ok"; '


def test_side_effects_only_flags_non_definitions():
    src = "fnc_a = {1};\nfnc_b = compileFinal {2};\nGLOBAL = 3;\n[] spawn {sleep 1};"
    effects = sqf.side_effects(src)
    assert effects == ["GLOBAL = 3;", "[] spawn {sleep 1};"]


def test_preprocess_include_and_refuse_define(tmp_path: Path):
    (tmp_path / "inc.sqf").write_text("fnc_inc = {2}; // c", encoding="utf-8")
    (tmp_path / "main.sqf").write_text('#include "inc.sqf"\nfnc_main = {1};', encoding="utf-8")
    out = sqf.preprocess(tmp_path / "main.sqf", tmp_path)
    assert "fnc_inc = {2};" in out and "fnc_main" in out and "//" not in out
    (tmp_path / "bad.sqf").write_text("#define X 1\nX", encoding="utf-8")
    with pytest.raises(sqf.PreprocessError):
        sqf.preprocess(tmp_path / "bad.sqf", tmp_path)


# -- matching -----------------------------------------------------------------------------------


def test_matching_operators_and_paths():
    ev = {"k": "evt", "type": "ctx", "key": "ROUNDS_DATA", "value": {"0": {"ROUND_WINNER": "DRAW"}}, "t": 12.5}
    assert matches(ev, {"k": "evt", "value.0.ROUND_WINNER": "DRAW"})
    assert matches(ev, {"key": {"$in": ["A", "ROUNDS_DATA"]}, "t": {"$gt": 10, "$lt": 13}})
    assert matches(ev, {"key": {"$re": "^ROUNDS"}, "missing": {"$exists": False}})
    assert not matches(ev, {"type": "fsm"})
    assert matcher({"k": "evt"})(ev)
    with pytest.raises(ValueError):
        validate({"k": {"$bogus": 1}})


# -- missions / rap / config ------------------------------------------------------------------------


def test_selftest_mission_inspect():
    info = missions.inspect(REPO_ROOT / "missions" / "brmh_selftest.VR")
    assert info["playable"] >= 2 and info["hc_slots"] == 1 and info["world"] == "VR"


def test_stage_copies_and_appends_dev_settings(tmp_path: Path):
    dest = missions.stage(REPO_ROOT / "missions" / "brmh_selftest.VR", tmp_path)
    desc = (dest / "description.ext").read_text(encoding="utf-8")
    assert "skipLobby = 1;" in desc and "briefing = 0;" in desc and "allowFunctionsRecompile = 1;" in desc
    assert desc.startswith('onLoadName = "arma-harness self-test";')


def test_stage_replaces_only_its_own_copy(tmp_path: Path):
    src = REPO_ROOT / "missions" / "brmh_selftest.VR"
    missions.stage(src, tmp_path)
    missions.stage(src, tmp_path)  # replacing our own staged copy is fine
    foreign = tmp_path / "foreign" / src.name
    foreign.mkdir(parents=True)
    (foreign / "description.ext").write_text("// someone else's mission", encoding="utf-8")
    (foreign / "keep.sqf").write_text("precious", encoding="utf-8")
    with pytest.raises(missions.StagingError):
        missions.stage(src, tmp_path / "foreign")
    assert (foreign / "keep.sqf").read_text(encoding="utf-8") == "precious"


def test_derapify_roundtrip_values():
    import struct
    # class body: parent "", 2 entries: value int x=7; array a[]={"s",1.5}
    body = b"\0" + bytes([2]) + b"\x01\x02x\0" + struct.pack("<i", 7)
    body += b"\x02a\0" + bytes([2]) + b"\x00s\0" + b"\x01" + struct.pack("<f", 1.5)
    data = b"\0raP" + struct.pack("<II", 0, 8) + struct.pack("<I", 0) + body
    text = rap.derapify(data)
    assert "x=7;" in text and 'a[]={"s",1.5};' in text


@pytest.fixture
def no_arma(monkeypatch):
    """Config loading without an Arma install (CI)."""
    monkeypatch.setattr("arma_harness.config.find_arma_dir", lambda: Path("C:/Arma3"))


def test_repo_config_has_selftest_default(no_arma):
    cfg = load_config([REPO_ROOT / "harness.toml"])
    assert cfg.default_mission == "selftest"
    assert cfg.mission().source == REPO_ROOT / "missions" / "brmh_selftest.VR"
    assert "@brmh" in cfg.mission().mods


def test_local_config_overrides_by_profile(no_arma, tmp_path: Path):
    local = tmp_path / "harness.local.toml"
    local.write_text('[harness]\ndefault_mission = "mine"\n[missions.mine]\nsource = "m.VR"\n'
                     '[missions.selftest]\nsource = "other.VR"\nmods = ["@CBA_A3"]\n', encoding="utf-8")
    cfg = load_config([REPO_ROOT / "harness.toml", local])
    assert cfg.mission().name == "mine" and cfg.mission().source == tmp_path / "m.VR"
    assert cfg.missions["selftest"].source == tmp_path / "other.VR"  # replaced, relative to its own file
    with pytest.raises(KeyError):
        cfg.mission("nope")


def test_versions_agree():
    """One version everywhere: Python package, host project, HEMTT project, SQF probe, Rust crate, in-game bridge."""
    import re
    import tomllib

    from arma_harness import __version__
    hemtt = tomllib.loads((REPO_ROOT / ".hemtt" / "project.toml").read_text(encoding="utf-8"))["version"]
    def read(rel: str) -> str:
        return (REPO_ROOT / rel).read_text(encoding="utf-8")

    versions = {
        "package": __version__,
        "pyproject": tomllib.loads(read("host/pyproject.toml"))["project"]["version"],
        "hemtt": f"{hemtt['major']}.{hemtt['minor']}.{hemtt['patch']}",
        "probe": re.search(r'BRMH_VERSION = "([^"]+)"', read("addons/main/functions/fn_preInit.sqf"))[1],
        "rust": tomllib.loads(read("brmh_ext/Cargo.toml"))["package"]["version"],
    }
    assert len(set(versions.values())) == 1, versions


def test_server_cfg_is_loopback_without_battleye():
    cfg = _server_cfg("m.VR", "pw")
    assert "loopback = 1;" in cfg and "BattlEye = 0;" in cfg and 'template = "m.VR";' in cfg


def test_boot_items_carry_overrides_and_strip_comments():
    items = boot_items(["rounds_framework"], {"ROUND_DURATION": 3})
    assert items[0]["args"] == [[["ROUND_DURATION", 3]]]
    assert "/*" not in items[0]["code"] and "brmh_rounds_fnc_attach" in items[0]["code"]


def test_svg_locations(tmp_path: Path):
    svg = tmp_path / "m.svg"
    svg.write_text('<svg><text x="100" y="900" font-size="10">Agia Marina</text>'
                   '<text x="5" y="5">042</text></svg>', encoding="utf-8")
    assert _svg_locations(svg, 1000) == [{"name": "Agia Marina", "x": 100, "y": 100}]


def test_seed_scenarios_parse():
    for p in (REPO_ROOT / "scenarios").glob("*.yaml"):
        _, sc = load_scenario(p)
        assert sc.get("steps"), p.name
        for step in sc["steps"]:
            assert len(step) == 1, (p.name, step)


# -- host Bridge client against the real in-game bridge module (fake game loop) ----------------------


def _load_game_bridge():
    spec = importlib.util.spec_from_file_location("game_bridge", REPO_ROOT / "python" / "bridge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_host_client_against_game_bridge(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRMH_HOME", str(tmp_path))
    gb = _load_game_bridge()
    (tmp_path / "sessions").mkdir()
    session, _ = gb.session_paths()
    Path(session).write_text(json.dumps({"token": "t0k", "port": 0, "boot": [{"code": "boot!"}]}))
    hub = gb.Hub()
    active, port = hub.start("m", "VR")
    assert active
    stop = threading.Event()

    def game():
        while not stop.is_set():
            for raw in hub.poll():
                req = json.loads(raw)
                hub.emit(json.dumps({"k": "dispatch", "id": req["id"], "owners": [2]}))
                hub.emit(json.dumps({"k": "res", "id": req["id"], "ok": True, "o": 2, "r": len(req["code"])}))
            time.sleep(0.005)

    threading.Thread(target=game, daemon=True).start()
    try:
        b = Bridge(port, "t0k")
        assert b.status()["active"]
        res = b.exec("12345", "server", timeout=5)
        assert res["ok"] and res["results"][0]["r"] == 5
        ev, nxt = b.wait_for(lambda e: e.get("k") == "res" and e.get("r") == 5, 0, 5)
        assert ev is not None and nxt > ev["seq"]
        boot_res = [e for e in b.events(since=0)["events"] if e.get("id") == "boot1.0"]
        assert boot_res, "boot payload should have been executed first"
    finally:
        stop.set()
        hub.stop()


def test_setup_agents_never_overwrites(tmp_path, monkeypatch):
    from arma_harness import agents

    monkeypatch.setattr(agents, "REPO_ROOT", tmp_path)
    mine = tmp_path / ".mcp.json"
    mine.write_text('{"mine": true}', encoding="utf-8")
    out = agents.setup()["clients"]
    assert "left alone" in out["claude"]["result"]
    assert mine.read_text(encoding="utf-8") == '{"mine": true}'
    assert out["codex"]["result"] == "written"
    assert "tool_timeout_sec" in (tmp_path / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert agents.setup(["codex"])["clients"]["codex"]["result"] == "already up to date"
    import json
    oc = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert oc["mcp"]["arma"]["type"] == "local" and oc["mcp"]["arma"]["command"][0].endswith("arma-harness-mcp.exe")
    forced = agents.setup(["claude"], force=True)["clients"]["claude"]["result"]
    assert "kept as .bak" in forced
    assert (tmp_path / ".mcp.json.bak").read_text(encoding="utf-8") == '{"mine": true}'


def test_agent_names_and_addressing():
    from arma_harness.harness import HarnessError, _address_rx, agent_color, check_agent_name

    assert check_agent_name(" Zeus ") == "Zeus"
    for bad in ["", "two words", "9lives", "everyone", "x" * 25]:
        with pytest.raises(HarnessError):
            check_agent_name(bad)
    rx = _address_rx("Zeus")
    for text in ["Zeus, spawn me a car", "zeus spawn", "@zeus hi", "hey Zeus, hi", "everyone, report"]:
        assert rx.search(text), text
    for text in ["zeusy, hi", "claude, hi", "tell zeus hi", "everyones"]:
        assert not rx.search(text), text
    assert agent_color("Claude") == [0.95, 0.55, 0.15, 1]
    assert agent_color("Zeus") == agent_color("zeus") != agent_color("Claude")


def test_claim_name_refuses_live_holder(tmp_path, monkeypatch, no_arma):
    import json
    import os

    from arma_harness.harness import Harness, HarnessError

    monkeypatch.setenv("BRMH_HOME", str(tmp_path))
    h = Harness()
    assert h.claim_name("Zeus")["name"] == "Zeus"
    assert h.claim_name("Zeus")["name"] == "Zeus"  # same process: fine
    held = h._listener_file("Zeus")
    state = json.loads(held.read_text(encoding="utf-8"))
    state["pid"] = os.getppid()  # a different, live process
    held.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(HarnessError, match="taken"):
        h.claim_name("zeus")
    assert h.claim_name("Zeus", force=True)["name"] == "Zeus"
    state["pid"] = 999999  # a dead process: free to take
    held.write_text(json.dumps(state), encoding="utf-8")
    assert h.claim_name("Zeus")["name"] == "Zeus"
    assert h.claim_name("Athena")["others"] == ["Zeus"]


def run_with_server(harness, pid, mode="launched", kind="server"):
    from arma_harness.harness import Proc, RunState

    harness._save(RunState(run_id="r", mode=mode, mission="commander", folder="", token="t", bridge_pid=pid,
                           adapters=[], overrides={}, procs=[Proc(pid, kind, "server", "", "")], started=0.0))


def test_a_run_whose_server_has_gone_doesnt_block_the_next(tmp_path, monkeypatch, no_arma):
    from arma_harness.harness import Harness

    monkeypatch.setenv("BRMH_HOME", str(tmp_path))
    h = Harness()
    run_with_server(h, 999999)
    assert h.forget_dead_run() is True and h.state() is None
    assert h.forget_dead_run() is False  # and nothing to do with no run at all


def test_a_run_whose_server_is_up_is_left_alone(tmp_path, monkeypatch, no_arma):
    import os

    from arma_harness.harness import Harness

    monkeypatch.setenv("BRMH_HOME", str(tmp_path))
    h = Harness()
    run_with_server(h, os.getpid())
    assert h.forget_dead_run() is False and h.state() is not None


def test_a_game_the_user_started_is_left_alone_while_it_runs(tmp_path, monkeypatch, no_arma):
    import os

    from arma_harness.harness import Harness

    monkeypatch.setenv("BRMH_HOME", str(tmp_path))
    h = Harness()
    run_with_server(h, os.getpid(), mode="attached", kind="attached")
    assert h.forget_dead_run() is False and h.state() is not None


def test_a_game_the_user_has_closed_is_forgotten(tmp_path, monkeypatch, no_arma):
    """Or the next attach is refused, as "a run is already active", for a game that's gone."""
    from arma_harness.harness import Harness

    monkeypatch.setenv("BRMH_HOME", str(tmp_path))
    h = Harness()
    run_with_server(h, 999999, mode="attached", kind="attached")
    assert h.forget_dead_run() is True and h.state() is None


def test_status_clears_a_run_whose_game_has_gone_and_says_so(tmp_path, monkeypatch, no_arma):
    """It used to report the last battle as running, with only a bridge error, and an agent took that as true."""
    from arma_harness.harness import Harness

    monkeypatch.setenv("BRMH_HOME", str(tmp_path))
    h = Harness()
    run_with_server(h, 999999)
    status = h.status()
    assert status["running"] is False
    assert "run r (launched, commander) had ended" in status["ended_run"]
    assert "ended_run" not in h.status()


def test_claimed_names_get_distinct_colors(tmp_path, monkeypatch, no_arma):
    from arma_harness.harness import Harness, agent_color

    monkeypatch.setenv("BRMH_HOME", str(tmp_path))
    h = Harness()
    names = ["Zeus", "Hermes", "Athena", "Ares", "Apollo"]
    colors = [h.claim_name(n)["color"] for n in names]
    assert len({tuple(c) for c in colors}) == len(names)
    assert h.agent_color("Hermes") == colors[1]
    assert h.agent_color("Unclaimed") == agent_color("Unclaimed")
