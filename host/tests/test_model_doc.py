"""docs/COMMANDER_MODEL.md against the code it describes: its order table, and its state charts.

The game side's machines keep their state as strings. A chart names those with exactly the code's string, as
`state "going off" as going_off`, so a state added or dropped on either side fails here. States the code holds some
other way, as a list or a flag, are drawn without quotes and aren't checked.
"""
import re

import pytest

from arma_harness.commander import orders, reports
from arma_harness.config import REPO_ROOT

SQF = (REPO_ROOT / "host" / "src" / "arma_harness" / "adapters" / "commander_boot.sqf").read_text(encoding="utf-8")
MODEL = (REPO_ROOT / "docs" / "COMMANDER_MODEL.md").read_text(encoding="utf-8")

# Which functions make up each machine, and the patterns that set its state.
STATE_PAIR = r'\["state", "([a-z ]+)"\]'
MACHINES = {
    "carry": (r"startCarry|carry\w+|stepCarries", [STATE_PAIR]),
    "treat": (r"treat\w+|stepTreats", [STATE_PAIR]),
    "post": (r"postOrder|stepBuilds", [STATE_PAIR]),
    "sortie": (r"casOrder", [STATE_PAIR]),
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


def declaration(machine: str) -> str | None:
    """A machine declared for brmh_cmd_fnc_newMachine, as brmh_cmd_<machine>Machine, if it has been converted."""
    match = re.search(rf"^brmh_cmd_{machine}Machine = \[\n(.*?)^\];", SQF, flags=re.M | re.S)
    return match[1] if match else None


STATE_LINE = r'^\t\t\["(\w[\w ]*)", \[$'  # a state's own line in a declaration, two tabs in


def declared_states(body: str) -> list[str]:
    return re.findall(STATE_LINE, body, flags=re.M)


def in_code(machine: str) -> set[str]:
    body = declaration(machine)
    if body is not None:
        return set(declared_states(body))
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
    assert {"carry", "treat", "post", "sortie", "fire", "boarding", "clearing", "placing", "cba-task", "custody",
            "busy", "battle", "attention", "chain", "objective", "order", "contact", "casualty-list", "apart", "outbox",
            "server"} == charts


# -- the order table in section 7.2 --------------------------------------------------------------------------------

def order_table() -> dict[str, dict[str, str]]:
    """Each order's lane, ending, claims and realisation, as the model's table gives them."""
    section = MODEL[MODEL.index("<!-- order-table -->"):MODEL.index("### 7.3")]
    rows = re.findall(r"^\| `(\w+)` \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$", section, flags=re.M)
    return {name: {"lane": lane.split(",")[0].strip(), "ending": ending.strip(), "claims": claims.strip(),
                   "real": real.strip()}
            for name, lane, ending, claims, real in rows}


def test_the_code_has_the_models_order_table():
    """The code's ORDER_TABLE is the single source of the order-type sets, and has to say what the model does."""
    in_code = {name: {"lane": kind.lane, "ending": kind.ending, "claims": kind.claims, "real": kind.realisation}
               for name, kind in orders.ORDER_TABLE.items()}
    assert in_code == order_table()


def where(**want) -> set[str]:
    return {name for name, row in order_table().items() if all(row[key] == value for key, value in want.items())}


def test_the_table_has_every_order_type_once():
    assert set(order_table()) == orders.ORDER_TYPES
    assert len(order_table()) == len(orders.ORDER_TYPES) == 23


@pytest.mark.parametrize("name, in_the_code, from_the_table", [
    ("ENDLESS", lambda: orders.ENDLESS, lambda: where(ending="Standing")),
    ("STANDS_ALONE", lambda: orders.STANDS_ALONE, lambda: where(ending="Instant")),
    ("CARE_ORDERS", lambda: set(orders.CARE_ORDERS), lambda: where(lane="Detail")),
    ("PLACING_ORDERS", lambda: reports.PLACING_ORDERS, lambda: where(real="Placing")),
    ("TASK_ORDERS", lambda: reports.TASK_ORDERS, lambda: where(real="CBA")),
    ("LEG_TYPES", lambda: set(orders.LEG_TYPES), lambda: where(real="Waypoint") - {"PATROL"}),
    ("SINGLE_LEG", lambda: orders.SINGLE_LEG,
     lambda: where(real="Clearing") | where(real="Placing") | where(real="CBA")),
    ("SINGLE_LEG_ORDERS", lambda: reports.SINGLE_LEG_ORDERS, lambda: orders.SINGLE_LEG),
])
def test_each_set_in_the_code_is_the_table_seen_one_way(name, in_the_code, from_the_table):
    assert set(in_the_code()) == set(from_the_table()), name


def test_every_declared_machine_waits_with_a_deadline_and_ends_aloud():
    """What brmh_cmd_fnc_machineProblems checks in the game, checked here too, so it fails before anyone plays."""
    declared = re.findall(r"^brmh_cmd_(\w+)Machine = \[\n(.*?)^\];", SQF, flags=re.M | re.S)
    assert declared, "no declared machines found"
    for machine, body in declared:
        states = re.split(STATE_LINE.replace("(", "(?:"), body, flags=re.M)[1:]
        assert len(states) == len(declared_states(body)) > 0, machine
        for name, state in zip(declared_states(body), states, strict=True):
            assert '["DEADLINE", [' in state, f"{machine}: {name} waits with no deadline"
        silent_endings = re.findall(r'\}, "", ""\]', body)
        assert not silent_endings, f"{machine} can end without a word"
