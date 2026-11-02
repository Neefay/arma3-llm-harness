"""Mission adapters: mission-specific observers and tools on top of the generic harness core.

An adapter contributes boot items (SQF run by the hub at preInit, before the mission's init.sqf)
and, optionally, MCP tools (see mcp_server.py, which registers ``rounds_*`` tools).
"""
from __future__ import annotations

from importlib import resources

from ..sqf import strip_comments


def load_sqf(name: str) -> str:
    return strip_comments(resources.files(__package__).joinpath(name).read_text(encoding="utf-8"))


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
