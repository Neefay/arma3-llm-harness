"""The command library, offline: every header reads, matches its code, and its example would run; arguments are
checked before anything reaches the game; and results come back plainly. tools/lint_library.py lints the SQF with
HEMTT, and tests/live_library.py runs every example in a real game."""
import re

import pytest

from arma_harness import library

COMMANDS = library.commands()


def camel(name: str) -> str:
    head, *rest = name.split("_")
    return "_" + head + "".join(part.capitalize() for part in rest)


def test_the_library_has_its_commands():
    assert len(COMMANDS) >= 19
    assert {"spawn_vehicle", "spawn_group", "garrison", "set_time_weather", "bombard", "delete_made"} <= set(COMMANDS)


@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_each_header_matches_its_code(name):
    """The header is what the assistant is told; params is what the code reads. They must be the same list."""
    command = COMMANDS[name]
    declared = re.search(r"^params \[(.*?)\];", command.body, flags=re.M | re.S)
    names = re.findall(r'"(_\w+)"', declared[1]) if declared else []
    assert names == [camel(param.name) for param in command.params], name
    assert command.tags, f"{name} has no tags, so a search by what it does can miss it"
    assert len(command.description) >= 30, f"{name}'s description is too short to choose it by"


@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_each_example_passes_the_argument_checks(name):
    command = COMMANDS[name]
    assert len(library.bind(command, command.example)) == len(command.params)


@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_each_failure_is_said_as_an_error(name):
    """A command that refuses says ERROR: ..., which comes back as ok: false, never a bare false or nil."""
    body = COMMANDS[name].body
    # Only the command's own checks, at the top level: an exitWith inside a loop just leaves the loop.
    for refusal in re.findall(r"^if \([^\n]*\) exitWith \{\s*(.*?)\s*\};", body, flags=re.M | re.S):
        assert refusal.startswith(('"ERROR: ', 'format ["ERROR: ', '"nobody"')), (name, refusal)


def test_a_search_finds_a_command_by_what_it_does():
    assert library.search("spawn a car")["commands"][0]["name"] == "spawn_vehicle"
    assert library.search("this guy")["commands"][0]["name"] == "unit_in_view"
    assert library.search("night fog")["commands"][0]["name"] == "set_time_weather"
    assert library.search("put soldiers in the houses")["commands"][0]["name"] == "garrison"
    assert library.search("artillery")["commands"][0]["name"] == "bombard"
    assert library.search("zzzz")["count"] == 0 and "arma_exec" in library.search("zzzz")["hint"]


def test_no_query_gives_the_index_by_area():
    index = library.search()
    assert index["count"] == len(COMMANDS)
    assert {c["name"] for c in index["areas"]["spawn"]} >= {"spawn_vehicle", "spawn_group"}


def test_a_searched_command_shows_how_to_run_it():
    found = library.search("spawn_vehicle")["commands"][0]
    assert found["example"] == 'arma_run("spawn_vehicle", {"class": "C_Offroad_01_F"})'
    assert found["params"][0] == {"name": "class", "type": "STRING", "text": "the vehicle's class", "required": True}
    assert found["params"][1]["default"] == "player"


@pytest.mark.parametrize(("args", "error"), [
    ({}, "needs class"),
    ({"class": "x", "speed": 3}, "no parameter speed"),
    ({"class": 3}, "class must be a string"),
    ({"class": "x", "distance": "far"}, "distance must be a number"),
    ({"class": "x", "flying": 1}, "flying must be true or false"),
    ({"class": "x", "near": [1, 2]}, "near must be a reference"),
    (["x", "player", 15, False, "extra"], "takes 4 arguments"),
])
def test_bad_arguments_are_refused_before_the_game(args, error):
    with pytest.raises(library.LibraryError, match=error):
        library.bind(COMMANDS["spawn_vehicle"], args)


def test_arguments_by_name_or_in_order_fill_in_defaults():
    command = COMMANDS["spawn_vehicle"]
    assert library.bind(command, {"class": "C_Offroad_01_F"}) == ["C_Offroad_01_F", "player", 15, False]
    assert library.bind(command, ["C_Offroad_01_F", "Nife"]) == ["C_Offroad_01_F", "Nife", 15, False]


@pytest.mark.parametrize(("value", "ok"), [
    ([100, 200], True), ([100, 200, 5], True), ("034 030", True), ("player", True),
    ([1], False), (["a", "b"], False), (True, False),
])
def test_a_position_is_a_place_or_a_reference(value, ok):
    command = COMMANDS["teleport"]
    if ok:
        library.bind(command, {"to": value})
    else:
        with pytest.raises(library.LibraryError, match="to must be a position"):
            library.bind(command, {"to": value})


def test_the_code_resolves_references_before_the_command_reads_them():
    code = library.code(COMMANDS["spawn_vehicle"])
    assert code.startswith(library.prelude())
    assert "_this set [1, [_this # 1] call brmh_lib_fnc_object];" in code
    assert "_this set [0," not in code  # the class is a plain string
    assert code.endswith(COMMANDS["spawn_vehicle"].body)
    side = library.code(COMMANDS["spawn_group"])
    assert "brmh_lib_fnc_position];" in side and "_this set [1, [_this # 1] call brmh_lib_fnc_side];" in side


class Game:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def exec(self, code, target, timeout, args):
        self.calls.append((target, timeout, args))
        return self.reply


def test_a_run_goes_to_the_commands_machine_with_its_arguments():
    game = Game({"ok": True, "results": [{"r": ["made:1", "Offroad", 15]}]})
    assert library.run(game, "spawn_vehicle", {"class": "C_Offroad_01_F"}) == {
        "ok": True, "command": "spawn_vehicle", "result": ["made:1", "Offroad", 15]}
    assert game.calls == [("server", 10.0, ["C_Offroad_01_F", "player", 15, False])]
    library.run(game, "unit_in_view")
    assert game.calls[-1][0] == "interface"


def test_a_refusal_or_a_script_error_comes_back_as_not_ok():
    refused = library.run(Game({"ok": True, "results": [{"r": "ERROR: there's no vehicle class x"}]}),
                          "spawn_vehicle", {"class": "x"})
    assert refused == {"ok": False, "command": "spawn_vehicle", "error": "there's no vehicle class x",
                       "args": ["x", "player", 15, False]}
    broken = library.run(Game({"ok": True, "results": [{"r": None, "errors": [{"text": "Error Undefined"}]}]}),
                         "player_info")
    assert not broken["ok"] and broken["errors"] == [{"text": "Error Undefined"}]


def test_an_unknown_command_suggests_one():
    with pytest.raises(library.LibraryError, match="Did you mean: spawn_vehicle"):
        library.find("spawn_vehicles")


def test_the_mcp_tools_reach_the_library(tmp_path, monkeypatch):
    import json

    import anyio
    from mcp import Client

    from arma_harness import mcp_server

    monkeypatch.setenv("BRMH_HOME", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_harness", None)

    async def go():
        async with Client(mcp_server.server, mode="legacy") as session:
            index = json.loads((await session.call_tool("arma_commands", {})).content[0].text)
            wrong = json.loads((await session.call_tool("arma_run", {"name": "spawn_vehicle",
                                                                     "args": {"speed": 1}})).content[0].text)
            return index, wrong

    index, wrong = anyio.run(go)
    assert index["count"] == len(COMMANDS)
    assert wrong == {"ok": False, "error": "spawn_vehicle has no parameter speed; it takes: class, near, distance, "
                                          "flying"}


def test_agents_md_indexes_every_command():
    """The cheat sheet's index is how an agent first hears of a command. A new one must be added there too."""
    from arma_harness.config import REPO_ROOT

    guide = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    index = guide[guide.index("## The command library"):guide.index("## Building with objects")]
    missing = [name for name in COMMANDS if f"`{name}`" not in index]
    assert not missing, f"add these to AGENTS.md's command index: {missing}"
