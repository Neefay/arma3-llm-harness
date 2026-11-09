"""Mission adapters: mission-specific observers and tools on top of the generic harness core.

An adapter contributes boot items (SQF run by the hub at preInit, before the mission's init.sqf)
and, optionally, MCP tools (see mcp_server.py, which registers ``rounds_*`` tools).
"""
from __future__ import annotations

from importlib import resources

from ..sqf import strip_comments


def load_sqf(name: str) -> str:
    if name == "commander_boot.sqf":  # the name it had as one file, still used by spikes
        return load_commander()
    return strip_comments(resources.files(__package__).joinpath(name).read_text(encoding="utf-8"))


def commander_files() -> list:
    """Commander mode's game side, in the order it's run: its state, the machines' declarations (data), one file per
    function, and the monitor that starts it all."""
    folder = resources.files(__package__).joinpath("commander")
    files = sorted((entry for entry in folder.iterdir() if entry.name.endswith(".sqf")), key=lambda entry: entry.name)
    machines = [entry for entry in files if entry.name.startswith("machine_")]
    functions = [entry for entry in files if entry.name.startswith("fn_")]
    return [folder.joinpath("init.sqf"), *machines, *functions, folder.joinpath("start.sqf")]


def commander_source() -> str:
    """The game side as one program, comments kept. A function's file holds its header and body, as a CfgFunctions
    file would, and is defined here as brmh_cmd_fnc_<name>."""
    parts = []
    for entry in commander_files():
        text = entry.read_text(encoding="utf-8").rstrip("\n")
        if entry.name.startswith("fn_"):
            body = "\n".join("\t" + line if line else line for line in text.split("\n"))
            text = f"brmh_cmd_fnc_{entry.name[3:-4]} = {{\n{body}\n}};"
        parts.append(text)
    return "\n\n".join(parts) + "\n"


def load_commander() -> str:
    return strip_comments(commander_source())


def boot_items(adapters: list[str], overrides: dict) -> list[dict]:
    items = []
    for name in adapters:
        if name == "rounds_framework":
            pairs = [[k, v] for k, v in overrides.items()]
            items.append({"code": load_sqf("rounds_framework_boot.sqf"), "target": "server",
                          "args": [pairs], "label": "rounds_framework"})
        else:
            raise ValueError(f"unknown adapter {name!r} (known: rounds_framework)")
    return items
