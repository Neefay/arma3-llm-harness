"""The fields the game sends and the fields the host reads, kept in step.

A packet field the host doesn't list is dropped on arrival without an error: that is how the speed setting once
stopped reaching the estimates. These read the game's own code, so a field added on one side alone fails here.
"""
import re
from pathlib import Path

from arma_harness.commander import runtime
from arma_harness.config import REPO_ROOT

SQF = (REPO_ROOT / "host" / "src" / "arma_harness" / "adapters" / "commander_boot.sqf").read_text(encoding="utf-8")
HOST = REPO_ROOT / "host" / "src" / "arma_harness" / "commander"


def sent_by(function: str, indent: int) -> set[str]:
    """The keys of the hashmap a game-side function builds, at the indent its fields sit at."""
    body = re.search(rf"^brmh_cmd_fnc_{function} = \{{\n(.*?)^\}};", SQF, flags=re.M | re.S)
    assert body, f"no {function} in the game's code"
    return set(re.findall(rf'^\t{{{indent}}}\["(\w+)",', body[1], flags=re.M))


def read_by(name: str, *files: str) -> set[str]:
    """The keys the host reads from a dict called `name`, as name["x"] or name.get("x")."""
    text = "\n".join((HOST / file).read_text(encoding="utf-8") for file in files)
    return set(re.findall(rf'\b{name}(?:\.get\(|\[)"(\w+)"', text))


def test_the_host_keeps_every_field_the_game_sends():
    sent = sent_by("packet", 2) - {"type"}  # "type" says what kind of event it is, and isn't part of the report
    assert sent == set(runtime.PACKET_FIELDS), (sorted(sent - set(runtime.PACKET_FIELDS)),
                                                sorted(set(runtime.PACKET_FIELDS) - sent))


def test_every_field_the_host_reads_is_kept_or_added():
    reads = read_by("packet", "reports.py", "runtime.py", "aar.py")
    missing = reads - set(runtime.PACKET_FIELDS) - set(runtime.PACKET_HOST_FIELDS)
    assert not missing, f"read but never kept, so always missing: {sorted(missing)}"


def test_the_truth_record_has_what_the_objectives_and_review_read():
    sent = sent_by("truth", 3)
    assert sent == set(runtime.TRUTH_GROUP_FIELDS), sorted(sent ^ set(runtime.TRUTH_GROUP_FIELDS))
    missing = read_by("group", "runtime.py", "aar.py", "operator.py") - sent - {"alive"}  # older records' name for able
    assert not missing, f"read from truth but never sent: {sorted(missing)}"


def test_the_checks_can_fail():
    """They read code with patterns, so make sure the patterns still find something."""
    assert len(sent_by("packet", 2)) > 30 and len(sent_by("truth", 3)) > 5
    assert {"pos", "leader", "mounted"} <= read_by("packet", "reports.py")
    assert Path(HOST / "runtime.py").exists()
