"""The command library: tested SQF commands the assistant finds by what they do and runs by name, with checked
arguments, instead of writing SQF for every common job.

Each command is one file under library/<area>/<name>.sqf, starting with a header the library reads:

    /*
        NAME: spawn_vehicle
        DESCRIPTION: Spawn a vehicle next to someone, facing the way they face.
        PARAMETERS:
            0 - class (STRING): the vehicle's class, such as B_MRAP_01_hmg_F
            1 - near (OBJECT, default "player"): who it appears next to
        RETURNS: [handle, display name, distance in m] (ARRAY)
        TARGET: server
        TAGS: spawn, vehicle, car
        EXAMPLE: {"class": "C_Offroad_01_F"}
    */

A default is JSON, and a parameter without one is required. The types are STRING, NUMBER, BOOL and ARRAY, and four
that take references an assistant can say, resolved in the game by library/_prelude.sqf: OBJECT ("player", a player's
or unit's name, a net id such as "2:345", or a "made:N" handle), GROUP (the same, meaning that one's group), POSITION
([x, y], [x, y, z], a grid such as "034 030", or any OBJECT reference) and SIDE ("east", "west", "independent",
"civilian"). A command that fails returns a string starting "ERROR: ", which comes back as ok: false.
"""
from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).parent / "library"
TYPES = {"STRING", "NUMBER", "BOOL", "ARRAY", "POSITION", "OBJECT", "GROUP", "SIDE"}
REFERENCES = {"POSITION": "position", "OBJECT": "object", "GROUP": "group", "SIDE": "side"}
TARGETS = {"server", "interface"}
SIDES = {"east", "west", "independent", "resistance", "guer", "civilian", "civ"}
FIELDS = {"NAME", "DESCRIPTION", "PARAMETERS", "RETURNS", "TARGET", "TAGS", "EXAMPLE", "TIMEOUT"}
_PARAM = re.compile(r"^(\d+) - (\w+) \((\w+)(?:, default (.+?))?\): (.+)$")
_NOTHING = object()


class LibraryError(ValueError):
    """A command or its arguments are wrong. The message says what to do instead."""


@dataclass
class Param:
    name: str
    type: str
    text: str
    default: object = _NOTHING

    @property
    def required(self) -> bool:
        return self.default is _NOTHING

    def describe(self) -> dict:
        return {"name": self.name, "type": self.type, "text": self.text,
                **({"required": True} if self.required else {"default": self.default})}


@dataclass
class Command:
    name: str
    area: str
    description: str
    params: list[Param]
    returns: str
    target: str
    tags: list[str]
    example: dict
    body: str
    path: Path
    timeout: float = 10.0
    words: set[str] = field(default_factory=set)

    def describe(self, full: bool = True) -> dict:
        if not full:
            return {"name": self.name, "area": self.area, "description": self.description}
        return {"name": self.name, "area": self.area, "description": self.description, "target": self.target,
                "params": [param.describe() for param in self.params], "returns": self.returns, "tags": self.tags,
                "example": f"arma_run(\"{self.name}\", {json.dumps(self.example)})"}


def _header(path: Path) -> tuple[dict[str, list[str]], str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A/\*(.*?)\*/[ \t]*\r?\n", text, flags=re.S)
    if not match:
        raise LibraryError(f"{path.name}: no header comment at the top")
    fields: dict[str, list[str]] = {}
    key = None
    for line in match[1].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        found = re.match(r"^([A-Z]+):\s*(.*)$", stripped)
        if found and found[1] in FIELDS and line.startswith("\t") and not line.startswith("\t\t"):
            key = found[1]
            fields[key] = [found[2]] if found[2] else []
        elif key is not None:
            fields[key].append(stripped)
        else:
            raise LibraryError(f"{path.name}: header line outside any field: {stripped!r}")
    return fields, text[match.end():]


def _parse(path: Path) -> Command:
    fields, body = _header(path)
    missing = {"NAME", "DESCRIPTION", "RETURNS", "TARGET", "EXAMPLE"} - set(fields)
    if missing:
        raise LibraryError(f"{path.name}: header lacks {', '.join(sorted(missing))}")
    name = " ".join(fields["NAME"])
    if name != path.stem:
        raise LibraryError(f"{path.name}: NAME is {name!r}, but the file is {path.stem}")
    params = []
    for line in fields.get("PARAMETERS", []):
        found = _PARAM.match(line)
        if not found:
            raise LibraryError(f"{path.name}: parameter line isn't '<n> - <name> (<TYPE>[, default <json>]): "
                               f"<text>': {line!r}")
        index, pname, ptype, default, text = found.groups()
        if int(index) != len(params):
            raise LibraryError(f"{path.name}: parameter {pname} is numbered {index}, expected {len(params)}")
        if ptype not in TYPES:
            raise LibraryError(f"{path.name}: {pname} has type {ptype}, not one of {', '.join(sorted(TYPES))}")
        try:
            value = json.loads(default) if default is not None else _NOTHING
        except ValueError as exc:
            raise LibraryError(f"{path.name}: {pname}'s default isn't JSON: {default!r}") from exc
        params.append(Param(pname, ptype, text, value))
    target = " ".join(fields["TARGET"])
    if target not in TARGETS:
        raise LibraryError(f"{path.name}: TARGET is {target!r}, not one of {', '.join(sorted(TARGETS))}")
    try:
        example = json.loads(" ".join(fields["EXAMPLE"]))
    except ValueError as exc:
        raise LibraryError(f"{path.name}: EXAMPLE isn't a JSON object of arguments") from exc
    tags = [tag.strip().lower() for tag in " ".join(fields.get("TAGS", [])).split(",") if tag.strip()]
    description = " ".join(fields["DESCRIPTION"])
    command = Command(name, path.parent.name, description, params, " ".join(fields["RETURNS"]), target, tags,
                      example, body, path, float(" ".join(fields.get("TIMEOUT", ["10"]))))
    command.words = set(re.findall(r"[a-z0-9]+", " ".join([name.replace("_", " "), description, *tags]).lower()))
    return command


@functools.cache
def commands() -> dict[str, Command]:
    """Every command, by name. Read once per process: the files ship with the harness."""
    found: dict[str, Command] = {}
    for path in sorted(ROOT.glob("*/*.sqf")):
        command = _parse(path)
        if command.name in found:
            raise LibraryError(f"two commands are called {command.name}: {found[command.name].path} and {path}")
        found[command.name] = command
    return found


@functools.cache
def prelude() -> str:
    return (ROOT / "_prelude.sqf").read_text(encoding="utf-8")


def search(query: str = "") -> dict:
    """Commands matching the words in ``query``, best first, each with its parameters and an example. With no query,
    the whole index: every command's name and what it does, by area."""
    every = commands()
    words = set(re.findall(r"[a-z0-9]+", query.lower()))
    if not words:
        areas: dict[str, list[dict]] = {}
        for command in every.values():
            areas.setdefault(command.area, []).append(command.describe(full=False))
        return {"count": len(every), "areas": areas,
                "next": "arma_commands(\"<words>\") shows matching commands in full; arma_run(name, args) runs one"}

    def score(command: Command) -> int:
        exact = 10 if query.strip().lower() == command.name else 0
        stems = sum(1 for word in words if any(known.startswith(word) for known in command.words))
        return exact + stems * 2 + sum(3 for word in words if word in command.name)

    ranked = sorted((c for c in every.values() if score(c) > 0), key=lambda c: (-score(c), c.name))
    return {"count": len(ranked), "commands": [command.describe() for command in ranked[:8]],
            **({} if ranked else {"hint": "Nothing matched. arma_commands() lists everything; arma_exec runs your "
                                          "own SQF for anything the library doesn't do."})}


def _check(command: Command, param: Param, value) -> object:
    kind = param.type

    def wrong(expected: str) -> LibraryError:
        return LibraryError(f"{command.name}: {param.name} must be {expected}, got {json.dumps(value)}")

    if kind == "NUMBER" and (isinstance(value, bool) or not isinstance(value, int | float)):
        raise wrong("a number")
    if kind == "BOOL" and not isinstance(value, bool):
        raise wrong("true or false")
    if kind == "STRING" and not isinstance(value, str):
        raise wrong("a string")
    if kind == "ARRAY" and not isinstance(value, list):
        raise wrong("an array")
    if kind in ("OBJECT", "GROUP") and not isinstance(value, str):
        raise wrong('a reference: "player", a name, a net id or a "made:N" handle')
    if kind == "SIDE" and (not isinstance(value, str) or value.lower() not in SIDES):
        raise wrong('a side: "east", "west", "independent" or "civilian"')
    if kind == "POSITION" and not (isinstance(value, str) or (
            isinstance(value, list) and len(value) in (2, 3)
            and all(isinstance(n, int | float) and not isinstance(n, bool) for n in value))):
        raise wrong('a position: [x, y], [x, y, z], a grid such as "034 030", or a reference such as "player"')
    return value


def bind(command: Command, args: dict | list | None) -> list:
    """The arguments in parameter order, with defaults filled in, each checked against its type."""
    args = {} if args is None else args
    if isinstance(args, list):
        if len(args) > len(command.params):
            raise LibraryError(f"{command.name} takes {len(command.params)} arguments, got {len(args)}")
        args = {param.name: value for param, value in zip(command.params, args, strict=False)}
    if not isinstance(args, dict):
        raise LibraryError(f"{command.name}: arguments must be an object of name: value")
    known = {param.name for param in command.params}
    unknown = sorted(set(args) - known)
    if unknown:
        raise LibraryError(f"{command.name} has no parameter {', '.join(unknown)}; it takes: "
                           f"{', '.join(param.name for param in command.params) or 'nothing'}")
    bound = []
    for param in command.params:
        if param.name in args:
            bound.append(_check(command, param, args[param.name]))
        elif param.required:
            raise LibraryError(f"{command.name} needs {param.name} ({param.type}): {param.text}")
        else:
            bound.append(param.default)
    return bound


def code(command: Command) -> str:
    """What runs in the game: the prelude, the references resolved in place, then the command itself."""
    resolve = [f"_this set [{index}, [_this # {index}] call brmh_lib_fnc_{REFERENCES[param.type]}];"
               for index, param in enumerate(command.params) if param.type in REFERENCES]
    return "\n".join([prelude(), *resolve, command.body])


def find(name: str) -> Command:
    every = commands()
    if name in every:
        return every[name]
    near = [known for known in every if name.lower() in known or known in name.lower()][:5]
    raise LibraryError(f"no command {name!r}." + (f" Did you mean: {', '.join(near)}?" if near else "")
                       + " arma_commands(\"<words>\") finds one by what it does.")


def run(harness, name: str, args: dict | list | None = None) -> dict:
    """Run a command in the game and say plainly whether it worked: ok, its result, or what went wrong."""
    command = find(name)
    bound = bind(command, args)
    reply = harness.exec(code(command), command.target, timeout=command.timeout, args=bound)
    results = reply.get("results") or []
    first = results[0] if results else {}
    errors = [error for result in results for error in result.get("errors") or []]
    if not reply.get("ok") or errors or first.get("aborted"):
        return {"ok": False, "command": name, "error": reply.get("error") or "the command raised a script error",
                "errors": errors, "args": bound}
    value = first.get("r")
    if isinstance(value, str) and value.startswith("ERROR: "):
        return {"ok": False, "command": name, "error": value[len("ERROR: "):], "args": bound}
    return {"ok": True, "command": name, "result": value}
