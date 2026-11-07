"""The state charts in docs/COMMANDER_MODEL.md against the code they describe.

The game side's machines keep their state as strings. A chart names those with exactly the code's string, as
`state "going off" as going_off`, so a state added or dropped on either side fails here. States the code holds some
other way, as a list or a flag, are drawn without quotes and aren't checked.
"""
import re

import pytest

from arma_harness.commander import reports
from arma_harness.config import REPO_ROOT

SQF = (REPO_ROOT / "host" / "src" / "arma_harness" / "adapters" / "commander_boot.sqf").read_text(encoding="utf-8")
MODEL = (REPO_ROOT / "docs" / "COMMANDER_MODEL.md").read_text(encoding="utf-8")

# Which functions make up each machine, and the patterns that set its state.
STATE_PAIR = r'\["state", "([a-z ]+)"\]'
MACHINES = {
    "carry": (r"startCarry|carry\w+|stepCarries", [STATE_PAIR]),
    "treat": (r"treat\w+|stepTreats", [STATE_PAIR]),
    "post": (r"postOrder|stepBuilds", [STATE_PAIR]),
    "fire": (r"startFire|stepFire|checkFire|fireChunk|trackGun", [STATE_PAIR, r'_finish = "([a-z]+)"']),
    "boarding": (r"startMount|stepMount|stopMount|startDismount|stepDismount",
                 [r'brmh_cmd_mount", \[_key, "([a-z ]+)"', r'\["([a-z ]+)", (?:\[\]|_names)\] call _stop',
                  r'\["none", "going off"\]', r'_status set \[1, "([a-z ]+)"\]']),
}


def functions(pattern: str) -> str:
    """The bodies of the SQF functions whose names match."""
    bodies = re.findall(r"^brmh_cmd_fnc_(\w+) = \{\n(.*?)^\};", SQF, flags=re.M | re.S)
    found = [body for name, body in bodies if re.fullmatch(pattern, name)]
    assert found, f"no functions match {pattern}"
    return "\n".join(found)


def in_code(machine: str) -> set[str]:
    pattern, setters = MACHINES[machine]
    body = functions(pattern)
    states = set()
    for setter in setters:
        if "going off" in setter:
            states |= {"none", "going off"} if re.search(setter, body) else set()
        else:
            states |= set(re.findall(setter, body))
    return states


def in_chart(machine: str) -> set[str]:
    match = re.search(rf"<!-- machine: {machine} -->\n```mermaid\n(.*?)```", MODEL, flags=re.S)
    assert match, f"no chart for {machine}"
    return set(re.findall(r'^\s*state "([^"]+)" as \w+', match[1], flags=re.M))


@pytest.mark.parametrize("machine", sorted(MACHINES))
def test_the_chart_has_exactly_the_states_the_code_sets(machine):
    code, chart = in_code(machine), in_chart(machine)
    assert code, f"found no states in the code for {machine}: the patterns here need updating"
    only_code, only_chart = sorted(code - chart), sorted(chart - code)
    assert code == chart, f"{machine}: only in the code {only_code}, only in the chart {only_chart}"


def test_every_ending_of_boarding_is_said():
    """Anything but the two "still doing it" states ends the job, and someone's waiting to hear how."""
    silent = {"going", "going off"}
    said = {state for state in in_chart("boarding") - silent
            if reports._boarding_words(["V1", state, "", ["Sam Reed"]])}
    assert said == in_chart("boarding") - silent


def test_every_ending_of_a_fire_mission_is_said():
    silent = {"firing", "stopped"}  # firing is still going, and a stopped mission is answered by CHECK_FIRE's row
    row = ["V1", "", "", "no gunner", "HE", 1, 3, 0, 0]
    unsaid = [state for state in in_chart("fire") - silent
              if not reports._mission_words([*row[:2], state, *row[3:]], {})]
    assert unsaid == [] or unsaid == ["checked"]  # with nothing in the air, a check fire has nothing more to add


def test_every_machine_in_the_list_has_a_chart():
    charts = set(re.findall(r"<!-- machine: ([\w-]+) -->", MODEL))
    assert {"carry", "treat", "post", "fire", "boarding", "clearing", "placing", "cba-task", "custody", "busy",
            "battle", "attention", "chain", "objective", "order", "contact", "casualty-list", "apart", "outbox",
            "server"} == charts
