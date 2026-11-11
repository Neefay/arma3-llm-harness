"""Pre-flight for a commander battle: is everything in place for this client, and if not, what to do about it.

Each check says passed, failed, warn (works, but something's off) or info, with a fix for anything that isn't passed.
Only failures stop a battle. Nothing here calls a model, and nothing boots the game.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable

from .. import procutil
from ..config import Home
from ..harness import Harness
from . import opencode, operator

OK, FAIL, WARN, INFO = "ok", "fail", "warn", "info"


def _check(name: str, status: str, detail: str, fix: str = "", where: str = "") -> dict:
    return {"name": name, "status": status, "detail": detail, **({"where": where} if where else {}),
            **({"fix": fix} if fix else {})}


def _version(command: list[str]) -> str:
    try:
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
    except OSError:
        return ""
    found = re.search(r"\d+\.\d+(?:\.\d+)?", done.stdout + done.stderr)
    return found[0] if found else ""


def _game(harness: Harness | None) -> dict:
    try:
        state = (harness or Harness()).state()
    except Exception as exc:
        return _check("Game", WARN, f"couldn't be checked: {exc}")
    booting = "`commander start` boots one, which takes a minute or two"
    if state is None:
        return _check("Game", INFO, f"not running: {booting}")
    # The run stays on record after its server exits, until the next start clears it: only the process says.
    server = next((proc for proc in state.procs if proc.kind == "server"), None)
    if state.mode == "launched" and server is not None and not procutil.alive(server.pid, server.exe or None):
        return _check("Game", INFO, f"not running (the last run's server has exited): {booting}")
    return _check("Game", INFO, f"running ({state.mission}, run {state.run_id}): `commander start` reuses it")


def check_opencode(home: Home | None = None, model: str | None = None, harness: Harness | None = None,
                   service_factory: Callable[[str], opencode.Service] = opencode.Service) -> list[dict]:
    checks = []
    cli = opencode.find_cli()
    if cli is None:
        checks.append(_check("OpenCode", FAIL, "not found", "Install OpenCode 2 (the desktop app, or the CLI from "
                             "opencode.ai). If it's installed somewhere unusual, set BRMH_OPENCODE_CLI to its "
                             "opencode or opencode-cli executable."))
        return checks + [_game(harness)]
    version = _version([cli, "--version"])
    if not version or int(version.split(".")[0]) < 2:
        checks.append(_check("OpenCode", FAIL, f"version {version or 'unknown'} at {cli}",
                             "Commander mode needs OpenCode 2 or later: update it (opencode upgrade)."))
        return checks + [_game(harness)]
    checks.append(_check("OpenCode", OK, version, where=cli))

    service = service_factory(cli)
    try:
        info = service.call("GET", "/api/info")
        checks.append(_check("Background server", OK, f"running at {service.url}, signed in"
                             + (f" (server {info.get('version')})" if info.get("version") else "")))
    except Exception as exc:
        checks.append(_check("Background server", FAIL, f"not reachable: {exc}",
                             "Open the OpenCode desktop app, or run: opencode service start"))
        return checks + [_game(harness)]

    try:
        available = opencode.models(service)
    except Exception as exc:
        available = []
        checks.append(_check("Models", FAIL, f"couldn't be listed: {exc}"))
    if available:
        providers = sorted({m["provider"] for m in available})
        shown = ", ".join(m["ref"] for m in available[:6]) + (", ..." if len(available) > 6 else "")
        checks.append(_check("Models", OK, f"{len(available)} that can call tools, from {', '.join(providers)}: "
                             f"{shown}"))
        if model:
            try:
                opencode.model_ref(model, available)
                checks.append(_check("Chosen model", OK, model))
            except ValueError as exc:
                checks.append(_check("Chosen model", FAIL, str(exc), "Pick one from the list above."))
    elif not any(c["name"] == "Models" for c in checks):
        checks.append(_check("Models", FAIL, "none that can call tools", "Sign in to a provider: in the app's "
                             "settings, or run: opencode auth login"))

    try:
        lockdown = operator.check_opencode_lockdown(home, service)
        if lockdown["ok"]:
            checks.append(_check("Lockdown", OK, "the commander's session gets its own tools and nothing else"))
        else:
            checks.append(_check("Lockdown", FAIL, f"allowed outside the commander's tools: "
                                 f"{', '.join(lockdown['allowed_outside']) or 'none'}; commander tools allowed: "
                                 f"{lockdown['commander_tools_allowed']}",
                                 "Don't run a battle like this. A newer OpenCode may have changed how permissions "
                                 "work: see docs/COMMANDER_OPENCODE.md, Troubleshooting."))
    except Exception as exc:
        checks.append(_check("Lockdown", FAIL, f"couldn't be checked: {exc}"))
    return checks + [_game(harness)]


def check_claude(harness: Harness | None = None) -> list[dict]:
    checks = []
    claude = shutil.which("claude")
    if claude is None:
        checks.append(_check("Claude Code", FAIL, "not on the PATH", "Install Claude Code, or use --client opencode."))
    else:
        checks.append(_check("Claude Code", OK, _version([claude, "--version"]) or "version unknown", where=claude))
    if os.environ.get("ANTHROPIC_API_KEY"):
        checks.append(_check("Login", WARN, "ANTHROPIC_API_KEY is set, so some modes bill API credits instead of "
                             "your subscription", "Clear it in the shell you launch from: "
                             "Remove-Item Env:ANTHROPIC_API_KEY"))
    checks.append(_check("Lockdown", INFO, "not checked here: Claude Code's check costs one small model call",
                         "Run once per Claude Code version: arma-harness commander check-lockdown"))
    return checks + [_game(harness)]


def run(client: str = "claude", model: str | None = None, home: Home | None = None,
        harness: Harness | None = None) -> dict:
    if client not in operator.CLIENTS:
        raise ValueError(f"client must be one of {', '.join(operator.CLIENTS)}")
    checks = check_opencode(home, model, harness) if client == "opencode" else check_claude(harness)
    ok = not any(check["status"] == FAIL for check in checks)
    start = "arma-harness commander start <scenario> --client opencode" + (f" --model {model}" if model else "") \
        if client == "opencode" else "arma-harness commander start <scenario>"
    return {"ok": ok, "client": client, "checks": checks,
            "next": f"Ready. List the scenarios with `arma-harness commander list`, then: {start}" if ok
            else "Fix what failed above, then run this again."}
