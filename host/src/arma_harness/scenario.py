"""Scenario runner: declarative YAML tests against a running mission.

    name: timeout round
    mission: rounds_framework          # profile used when the runner starts its own run
    start: {hcs: 0, client: false, overrides: {ROUND_DURATION: 4}}
    expect: pass                       # or "fail" for a known failure
    steps:
      - wait_for: {match: {k: evt, type: fsm, dir: enter, state: GAME}, timeout_s: 90}
      - exec: {code: "1 + 1", target: server, expect: 2}
      - assert: {context: {key: TEAM_WINS, equals: {DRAW: 1}}}
      - assert: {sequence: {match: {type: fsm, dir: enter}, field: state, expect: [SETUP, READY, GAME]}}
      - assert: {event: {k: evt, type: ctx, key: ENDING_REASON}}
      - assert: {sqf: "time > 0"}
      - assert: {no_errors: true}

Step kinds: wait_for, exec, assert, sleep, snapshot, hc_start, client_start, fire_event,
context_set, reload. Event-based steps look at everything since the scenario started.
"""
from __future__ import annotations

import contextlib
import json
import time
from pathlib import Path

import yaml

from .adapters import rounds_framework as rounds
from .config import REPO_ROOT
from .harness import Harness, HarnessError
from .matching import get_path, matcher, matches

SCENARIO_DIR = REPO_ROOT / "scenarios"


class StepFailed(AssertionError):
    pass


def _first(res: dict):
    rs = res.get("results") or []
    return rs[0].get("r") if rs else None


def _events_since(h: Harness, since: int) -> list[dict]:
    out, cursor = [], since
    while True:
        res = h.bridge().events(since=cursor, limit=5000)
        evs = res.get("events", [])
        out.extend(evs)
        if not res.get("more"):
            return out
        cursor = evs[-1]["seq"] + 1


def _check_exec(res: dict, expect, label: str):
    if not res.get("ok"):
        raise StepFailed(f"{label}: {res.get('error') or [r.get('errors') for r in res.get('results', [])]}")
    if expect is not None and _first(res) != expect:
        raise StepFailed(f"{label}: expected {expect!r}, got {_first(res)!r}")
    return _first(res)


def _assert(h: Harness, spec: dict, since: int) -> str:
    if "no_errors" in spec:
        ignore = spec.get("ignore", [])
        errs = [e for e in _events_since(h, since) if e.get("k") == "err"
                and not any(pat in (e.get("text") or "") for pat in ignore)]
        if spec["no_errors"] and errs:
            raise StepFailed(f"{len(errs)} script error(s): " + "; ".join(
                f"{e.get('m')} {e.get('file') or '<exec>'}:{e.get('line')} {e.get('text')}" for e in errs[:5]))
        return f"{len(errs)} errors"
    if "context" in spec:
        c = spec["context"]
        value = _first(rounds.context_get(h, c["key"]))
        if "equals" in c and value != c["equals"]:
            raise StepFailed(f"context {c['key']} = {value!r}, expected {c['equals']!r}")
        if "match" in c and not matches({"value": value}, {f"value.{k}": v for k, v in c["match"].items()}):
            raise StepFailed(f"context {c['key']} = {json.dumps(value)[:300]} does not match {c['match']}")
        return f"{c['key']} = {json.dumps(value)[:200]}"
    if "sqf" in spec:
        value = _check_exec(h.exec(spec["sqf"], spec.get("target", "server")), None, "sqf")
        if value is not True:
            raise StepFailed(f"sqf predicate returned {value!r}: {spec['sqf']}")
        return "true"
    if "event" in spec:
        pred = matcher(spec["event"])
        hits = [e for e in _events_since(h, since) if pred(e)]
        want = spec.get("count")
        if (want is None and not hits) or (want is not None and len(hits) != want):
            raise StepFailed(f"{len(hits)} event(s) match {spec['event']} (wanted {want or '>=1'})")
        return f"{len(hits)} matching event(s)"
    if "sequence" in spec:
        s = spec["sequence"]
        pred = matcher(s["match"])
        seen = [get_path(e, s["field"]) for e in _events_since(h, since) if pred(e)]
        expected = list(s["expect"])
        it = iter(seen)
        if not all(any(v == want for v in it) for want in expected):
            raise StepFailed(f"sequence {expected} not found in order; saw {seen}")
        return f"saw {seen}"
    raise StepFailed(f"unknown assertion {list(spec)}")


def _step(h: Harness, kind: str, spec, since: int) -> str:
    if kind == "sleep":
        time.sleep(float(spec))
        return f"{spec}s"
    if kind == "wait_for":
        res = h.wait_for(spec["match"], since=spec.get("since", since), timeout=float(spec.get("timeout_s", 30)))
        if not res["found"]:
            raise StepFailed(f"timed out waiting for {spec['match']}")
        ev = res["event"]
        return f"seq {ev['seq']} t={ev.get('t')}"
    if kind == "exec":
        res = h.exec(spec["code"], spec.get("target", "server"), timeout=float(spec.get("timeout_s", 10)),
                     scheduled=bool(spec.get("scheduled", False)), args=spec.get("args"))
        if "expect_error" in spec:
            texts = [e.get("text", "") for r in res.get("results", []) for e in r.get("errors", [])]
            if not any(spec["expect_error"] in t for t in texts):
                raise StepFailed(f"expected an error containing {spec['expect_error']!r}, got {texts}")
            if "expect_aborted" in spec and any(r.get("aborted") for r in res["results"]) != spec["expect_aborted"]:
                raise StepFailed(f"aborted != {spec['expect_aborted']}")
            return f"error attributed: {texts[0]}"
        if "expect_owners" in spec and len(res.get("owners") or []) != spec["expect_owners"]:
            raise StepFailed(f"expected {spec['expect_owners']} machine(s), got owners {res.get('owners')}")
        return json.dumps(_check_exec(res, spec.get("expect"), "exec"))[:200]
    if kind == "assert":
        return _assert(h, spec, since)
    if kind == "snapshot":
        opts = dict(spec or {})
        allow_black = bool(opts.pop("allow_black", False))
        snap = h.snapshot(**opts)
        if "warning" in snap and not allow_black:
            raise StepFailed(f"{snap['warning']} ({snap['path']})")
        return f"{snap['path']} ({snap['width']}x{snap['height']}, luma {snap['mean_luma']})"
    if kind == "hc_start":
        return json.dumps(h.hc_start())
    if kind == "client_start":
        return json.dumps(h.client_start())
    if kind == "fire_event":
        res = rounds.fire_event(h, spec["event"], spec.get("args"), spec.get("alias", "GameController"))
        return json.dumps(_check_exec(res, None, "fire_event"))
    if kind == "context_set":
        res = rounds.context_set(h, spec["key"], spec["value"])
        return json.dumps(_check_exec(res, None, "context_set"))[:200]
    if kind == "reload":
        res = h.reload(spec["path"], target=spec.get("target", "all"), function=spec.get("function"),
                       force=bool(spec.get("force", False)))
        _check_exec(res, None, "reload")
        return spec["path"]
    raise StepFailed(f"unknown step kind {kind!r}")


def load(path: str | Path) -> tuple[Path, dict]:
    p = Path(path)
    if not p.is_absolute() and not p.exists():
        p = SCENARIO_DIR / p
    if p.suffix not in (".yaml", ".yml") and not p.exists():
        p = p.with_suffix(".yaml")
    return p, yaml.safe_load(p.read_text(encoding="utf-8"))


def run(h: Harness, path: str | Path, keep_running: bool = False) -> dict:
    p, sc = load(path)
    name = sc.get("name", p.stem)
    expect_fail = sc.get("expect", "pass") == "fail"
    started_here = False
    t0 = time.time()
    results: list[dict] = []
    failure = None
    try:
        if h.state() is None:
            start = sc.get("start", {})
            h.start(mission=sc.get("mission"), hcs=int(start.get("hcs", 0)),
                    client=bool(start.get("client", False)), overrides=start.get("overrides"))
            started_here = True
            since = 0  # a fresh run: everything since the bridge came up belongs to this scenario
        else:
            since = h.bridge().cursor()
        for i, step in enumerate(sc.get("steps", []), 1):
            (kind, spec), = step.items()
            s0 = time.time()
            try:
                detail = _step(h, kind, spec, since)
                results.append({"step": i, "kind": kind, "ok": True, "s": round(time.time() - s0, 2),
                                "detail": detail})
            except (StepFailed, HarnessError) as e:
                results.append({"step": i, "kind": kind, "ok": False, "s": round(time.time() - s0, 2),
                                "detail": str(e)})
                failure = i
                break
    except HarnessError as e:
        results.append({"step": 0, "kind": "start", "ok": False, "s": round(time.time() - t0, 2), "detail": str(e)})
        failure = 0
    passed = failure is None
    excerpt = []
    if not passed:
        with contextlib.suppress(Exception):
            excerpt = _events_since(h, 0)[-40:]
    run_dir = Path(h.state().run_dir) if h.state() and h.state().run_dir else h.home.runs
    report_path = run_dir / f"scenario-{p.stem}.md"
    report = _report(name, p, passed, expect_fail, results, excerpt, time.time() - t0)
    report_path.write_text(report, encoding="utf-8")
    if started_here and not keep_running:
        h.stop()
    verdict = "pass" if passed else "fail"
    return {"scenario": name, "verdict": verdict, "expected": "fail" if expect_fail else "pass",
            "as_expected": (verdict == "fail") == expect_fail, "seconds": round(time.time() - t0, 1),
            "steps": results, "report": str(report_path)}


def _report(name, path, passed, expect_fail, results, excerpt, seconds) -> str:
    verdict = "PASS" if passed else "FAIL"
    note = " (known failure: expected)" if expect_fail and not passed else (
        " (UNEXPECTED PASS of a known failure)" if expect_fail and passed else "")
    lines = [f"# Scenario: {name}", "", f"**{verdict}**{note} in {seconds:.1f}s - `{path}`", "",
             "| # | step | ok | s | detail |", "|---|---|---|---|---|"]
    for r in results:
        detail = str(r["detail"]).replace("|", "\\|").replace("\n", " ")[:300]
        lines.append(f"| {r['step']} | {r['kind']} | {'✓' if r['ok'] else '✗'} | {r['s']} | {detail} |")
    if excerpt:
        lines += ["", "## Last events before the failure", "", "```"]
        lines += [json.dumps({k: v for k, v in e.items() if k not in ("v", "tt", "f")})[:300] for e in excerpt]
        lines.append("```")
    return "\n".join(lines) + "\n"
