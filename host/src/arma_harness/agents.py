"""Project-scoped MCP configuration for agent clients other than (and including) Claude Code.

Each client wants the same thing, the harness MCP server as a stdio command, in its own file and
format. The files hold absolute paths to this clone, so they are personal (git-ignored) and written
by `arma-harness setup-agents` rather than checked in. Existing files are never overwritten: a file
that already says the same thing is left alone, one that differs is reported (use --force to replace
it; the old content is kept next to it as <name>.bak).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .config import REPO_ROOT

GUIDE = REPO_ROOT / "AGENTS.md"

# Seconds a single tool call may run. arma_listen defaults to 25 s and is capped at 300 s; give
# clients room above that so a long listen is never cut off by the client.
TOOL_TIMEOUT_S = 330


def _server_exe() -> str:
    exe = Path(sys.executable).with_name("arma-harness-mcp.exe")
    if not exe.exists():
        exe = REPO_ROOT / "host" / ".venv" / "Scripts" / "arma-harness-mcp.exe"
    return exe.as_posix()


def _toml_str(s: str) -> str:
    return "'" + s.replace("'", "") + "'"


def configs() -> dict[str, tuple[Path, str]]:
    """client -> (file, content) for every supported client."""
    exe, root = _server_exe(), REPO_ROOT.as_posix()
    stdio = {"command": exe, "args": [], "cwd": root}
    return {
        # Claude Code: project .mcp.json; reads CLAUDE.md, which imports AGENTS.md.
        "claude": (REPO_ROOT / ".mcp.json", json.dumps({"mcpServers": {"arma": stdio}}, indent=2) + "\n"),
        # Codex: project .codex/config.toml (trusted projects only); reads AGENTS.md natively.
        "codex": (REPO_ROOT / ".codex" / "config.toml",
                  "[mcp_servers.arma]\n"
                  f"command = {_toml_str(exe)}\n"
                  f"cwd = {_toml_str(root)}\n"
                  f"tool_timeout_sec = {TOOL_TIMEOUT_S}\n"),
        # Gemini CLI: project .gemini/settings.json; told to read AGENTS.md as its context file.
        "gemini": (REPO_ROOT / ".gemini" / "settings.json", json.dumps({
            "context": {"fileName": ["AGENTS.md", "GEMINI.md"]},
            "mcpServers": {"arma": {**stdio, "timeout": TOOL_TIMEOUT_S * 1000}},
        }, indent=2) + "\n"),
        # Cursor: project .cursor/mcp.json; reads AGENTS.md natively.
        "cursor": (REPO_ROOT / ".cursor" / "mcp.json", json.dumps({"mcpServers": {"arma": stdio}}, indent=2) + "\n"),
        # OpenCode: project opencode.json (current, flat "mcp" schema); reads AGENTS.md natively.
        # "timeout" covers requests including tool calls (ms). OpenCode 2 nests servers under
        # mcp.servers instead; see the README for that form.
        "opencode": (REPO_ROOT / "opencode.json", json.dumps({
            "$schema": "https://opencode.ai/config.json",
            "mcp": {"arma": {"type": "local", "command": [exe], "cwd": root, "enabled": True,
                             "timeout": TOOL_TIMEOUT_S * 1000}},
        }, indent=2) + "\n"),
        # VS Code (Copilot agent mode): .vscode/mcp.json uses "servers" and an explicit type.
        "vscode": (REPO_ROOT / ".vscode" / "mcp.json",
                   json.dumps({"servers": {"arma": {"type": "stdio", **stdio}}}, indent=2) + "\n"),
    }


def setup(clients: list[str] | None = None, force: bool = False, dry_run: bool = False) -> dict:
    """Write the config files for ``clients`` (default: all). Returns what happened per client."""
    table = configs()
    chosen = clients or list(table)
    unknown = [c for c in chosen if c not in table]
    if unknown:
        raise ValueError(f"unknown client(s) {unknown}; known: {sorted(table)}")
    out = {}
    for name in chosen:
        path, content = table[name]
        rel = path.relative_to(REPO_ROOT).as_posix()
        backed_up = False
        if path.exists():
            current = path.read_text(encoding="utf-8")
            if current.replace("\r\n", "\n") == content:
                out[name] = {"file": rel, "result": "already up to date"}
                continue
            if not force:
                out[name] = {"file": rel, "result": "exists and differs: left alone (use --force to replace; "
                             "the old file is kept as .bak)", "would_write": content}
                continue
            if not dry_run:
                path.with_name(path.name + ".bak").write_text(current, encoding="utf-8")
                backed_up = True
        if dry_run:
            out[name] = {"file": rel, "result": "would write", "content": content}
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        out[name] = {"file": rel, "result": "written" + (" (old file kept as .bak)" if backed_up else "")}
    return {"guide": GUIDE.as_posix(), "server": _server_exe(), "clients": out}


def guide() -> str:
    try:
        return GUIDE.read_text(encoding="utf-8")
    except OSError:
        return "AGENTS.md not found next to the harness package; see the repository README."
