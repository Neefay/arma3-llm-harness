"""The after-action review page's data, offline. See also the truth-recording tests at the end."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_commander import Battle

from arma_harness.commander import aar
from arma_harness.config import Home

START = 1_800_000_000.0  # any fixed moment: transcripts are matched to battles by time
SCENARIO = {
    "name": "take_the_village", "text": "Clear the village.", "mid_turn_messages": "hold",
    "stations": [{"callsign": "Alpha", "units": 8, "role": "infantry squad"}],
    "enemies": [{"id": "East Garrison", "units": 8}, {"id": "East Patrol", "units": 6}],
    "markers": [{"id": "O1", "kind": "objective", "label": "The village", "at": "041 041"}],
}
BUILDINGS = [{"id": "B1", "pos": [4000, 4210], "at": "040 042", "name": "Tower", "positions": 18, "width": 14,
              "length": 13, "dir": 160}]


def rows(path: Path, *items: dict) -> None:
    path.write_text("".join(json.dumps(item) + "\n" for item in items), encoding="utf-8")


def stamp(seconds: float) -> str:
    return datetime.fromtimestamp(START + seconds, UTC).isoformat().replace("+00:00", "Z")


@pytest.fixture
def battle(tmp_path) -> Path:
    folder = tmp_path / "runs" / "20261105-043541" / "commander-2" / "west"
    folder.mkdir(parents=True)
    (folder.parent / "battle.json").write_text(json.dumps({
        "scenario": SCENARIO, "buildings": BUILDINGS, "world_size": 8192, "run": "20261105-043541", "attempt": 2}))
    rows(folder.parent / "truth.jsonl",
         {"t": 5, "groups": [{"group": "Alpha 1-1", "side": "WEST", "able": 1, "pos": [4100, 3800],
                              "units": [[4100, 3800, 0]]},
                             {"group": "Alpha", "side": "WEST", "able": 8, "pos": [3950, 3550],
                              "units": [[3950, 3550, 0]]}]},
         {"t": 90, "groups": [{"group": "East Patrol", "side": "EAST", "able": 6, "pos": [4250, 3950]}]},
         {"t": 130, "groups": []},  # past the end
         {"t": -120, "groups": [{"group": "Alpha", "side": "WEST", "able": 8, "pos": [1, 1]}]})  # the next mission
    rows(folder.parent / "kills.jsonl",
         {"t": 20, "victim": "Owen King", "side": "WEST", "victimPos": [4100, 3700, 0], "killer": "Khalil Amani",
          "killerSide": "EAST", "weapon": "AK", "distance": 208},
         {"t": 76, "victim": "Habib Noori", "side": "EAST", "victimPos": [4250, 3950, 0], "killer": "Kyle Smith",
          "killerSide": "WEST", "weapon": "MX", "distance": 337})
    rows(folder / "radio.jsonl",
         {"t": 1, "from": "HQ", "to": "Alpha", "text": "O-0001: MOVE 041 040", "kind": "order"},
         {"t": 2, "from": "Alpha", "to": "HQ", "text": "Copy, moving to grid 041 040.", "kind": "report",
          "precedence": "routine"},
         {"t": 50, "from": "Alpha", "to": "HQ", "text": "On the objective, attacking grid 041 041, at grid 041 040.",
          "kind": "report", "precedence": "routine"},
         {"t": 60, "from": "Alpha", "to": "HQ", "text": "B1 checked, nothing seen.", "kind": "report"})
    rows(folder / "radio_events.jsonl", {"t": 100, "mission_end": "Objective achieved."})
    rows(folder / "turns.jsonl",
         {"turn": 1, "start": 0.0, "woke_on": "mission start", "end": 1.0, "note": "Orders out", "duration": 1.0},
         {"turn": 2, "start": 5.0, "woke_on": "1 message", "end": 6.0, "note": "Fine", "duration": 1.0})
    rows(folder / "orders.jsonl",
         {"id": "O-0001", "t": 1, "request": {"to": "Alpha", "legs": [{"type": "MOVE", "at": "041 040"}]}},
         {"id": "O-0002", "t": 2, "request": {"to": "Alpha", "legs": [{"type": "CLEAR", "at": "B1"}]}},
         {"id": "O-0003", "t": 3, "request": {"to": "Alpha", "legs": [{"type": "MOVE", "at": "O1"}]}})
    rows(folder / "markers.jsonl", {"id": "E1", "kind": "enemy", "at": "042 039", "label": "Seen", "t": 30},
         {"id": "E1", "t": 80, "retired": True},
         {"id": "L1", "kind": "phase_line", "at": ["040 040", "042 040"], "label": "", "t": 31})
    (folder / "state.json").write_text(json.dumps({"ended": "Objective achieved.", "turn": 3, "turn_row": {
        "turn": 3, "start": 100.0, "woke_on": "notice"}}))
    return folder


@pytest.mark.parametrize("text, grid", [
    ("Copy, moving to grid 041 034.", None),
    ("Copy, defending grid 041 041.", None),
    ("Copy, sweeping around grid 041 041.", None),
    ("Arrived, grid 034 030.", "034 030"),
    ("On station, grid 040 041.", "040 041"),
    ("Holding at grid 040 041.", "040 041"),
    ("On the objective, attacking grid 041 041, at grid 041 040.", "041 040"),
    ("Passing grid 038 038, at grid 039 039.", "039 039"),
    ("Not making progress toward grid 041 041, at grid 040 035.", "040 035"),
    ("Grid 043 042, moving south-east. Patrolling around grid 043 041.", "043 042"),
    ("Contact, a few infantry, north, roughly 400 metres. Engaging.", None),
    ("Contact, a few infantry, bearing 045, roughly 400 metres. Engaging.", None),
    ("Contact update, one infantry, bearing 310, roughly 50 metres, near B3.", None),
])
def test_only_a_stations_own_position_goes_on_the_belief_map(text, grid):
    assert aar.reported_position(text) == grid


@pytest.mark.parametrize("text", [
    "Mk6 Mortar, nobody on it, grid 041 035. Listed as V5.",
    "V1 is wrecked, grid 039 040.",
    "Splash seen, grid 028 020, about 200 m east of us.",
    "Copy, fire mission, 2 HE at grid 028 020.",
])
def test_grids_of_other_things_arent_where_the_sender_is(battle, text):
    rows(battle / "radio.jsonl", {"t": 2, "from": "Alpha", "text": text, "kind": "report", "grid": None},
         {"t": 3, "from": "Alpha", "text": "Holding at grid 040 041.", "kind": "report", "grid": "040 041"})
    positions = [row["pos"] for row in aar.battle_data(battle)["radio"]]
    assert positions == [None, [4050.0, 4150.0]]


def shelled(battle, *groups, position=None, order="O-0009", victim_at=(4100, 4100), landed=(4105, 4100),
            aim=(4110, 4100)):
    """One friendly dead, 2 s after a friendly shell, with a mission fired at t=30."""
    rows(battle.parent / "truth.jsonl", {"t": 30, "groups": list(groups)}, {"t": 50, "groups": list(groups)})
    rows(battle.parent / "kills.jsonl",
         {"t": 50, "victim": "Owen King", "side": "WEST", "victimPos": [*victim_at, 0], "killer": "x"})
    rows(battle.parent / "shells.jsonl",
         {"t": 48, "order": order, "gun": "V1", "side": "WEST", "ammo": "Sh_82mm_AMOS", "pos": list(landed),
          "aim": list(aim)})
    rows(battle / "fire_missions.jsonl",
         {"id": "O-0009", "t": 30, "by": "Hammer", "aim": list(aim), "grid": "041 041", "ammo": "HE", "rounds": 2,
          "positions": {"Alpha": position} if position else {}})
    data = aar.battle_data(battle)
    return data, data["kills"][0]


def alpha(x, y):
    return {"group": "Alpha", "side": "WEST", "able": 8, "pos": [x, y], "units": [[x, y, 0]]}


def test_shelling_a_position_it_was_told_about_is_the_commanders_decision(battle):
    _, kill = shelled(battle, alpha(4100, 4100), position={"grid": "041 041", "t": 20})
    assert kill["shell"] == {"gun": "V1", "order": "O-0009"} and kill["verdict"]["kind"] == "decision"
    assert kill["verdict"]["why"] == "Alpha's last report, 10 s before firing, was 64 m from the aim."


def test_shelling_a_station_that_moved_since_its_last_report_is_fog(battle):
    _, kill = shelled(battle, alpha(4100, 4100), position={"grid": "030 030", "t": 5})
    assert kill["verdict"]["kind"] == "fog" and "It had moved" in kill["verdict"]["why"]


def test_shelling_a_station_that_never_reported_is_fog(battle):
    _, kill = shelled(battle, alpha(4100, 4100))
    assert kill["verdict"]["kind"] == "fog" and "hadn't reported" in kill["verdict"]["why"]


def test_a_gun_firing_by_itself_is_a_bug(battle):
    _, kill = shelled(battle, alpha(4100, 4100), order=None)
    assert kill["verdict"]["kind"] == "bug" and "no order" in kill["verdict"]["why"]


def test_a_report_the_commander_didnt_get_is_a_bug(battle):
    rows(battle / "radio.jsonl", {"t": 25, "from": "Alpha", "text": "At grid 041 041.", "kind": "report",
                                  "grid": "041 041"})
    _, kill = shelled(battle, alpha(4100, 4100), position={"grid": "020 020", "t": 5})
    assert kill["verdict"]["kind"] == "bug" and "wasn't the place" in kill["verdict"]["why"]


def test_a_station_shelled_where_it_said_it_was_is_fog_too(battle):
    _, kill = shelled(battle, alpha(3700, 3700), position={"grid": "037 037", "t": 25}, victim_at=(3700, 3700),
                      landed=(3695, 3700))
    assert kill["verdict"]["kind"] == "fog" and "was where it said" in kill["verdict"]["why"]


def test_deaths_nowhere_near_a_shell_are_just_deaths(battle):
    _, kill = shelled(battle, alpha(4100, 4100), landed=(4300, 4100))
    assert "shell" not in kill and "verdict" not in kill


def test_an_enemy_killed_by_a_shell_says_so_with_no_verdict(battle):
    shelled(battle, alpha(4100, 4100))
    rows(battle.parent / "kills.jsonl",
         {"t": 50, "victim": "Habib", "side": "EAST", "victimPos": [4100, 4100, 0], "killer": "x"})
    kill = aar.battle_data(battle)["kills"][0]
    assert kill["shell"]["gun"] == "V1" and "verdict" not in kill


def test_the_page_shows_missions_shells_and_a_score_for_them(battle):
    data, _ = shelled(battle, alpha(4100, 4100), position={"grid": "041 041", "t": 20})
    assert data["missions"][0]["aim"] == [4110, 4100] and data["missions"][0]["until"] == 63
    assert data["shells"][0] == {"t": 48, "pos": [4105, 4100], "aim": [4110, 4100], "gun": "V1", "order": "O-0009",
                                 "smoke": False, "friendly": True}
    assert data["score"]["rounds_fired"] == 1 and data["score"]["own_fire_deaths"] == 1
    assert aar.render(data).count("fireKey") >= 4


def test_a_battle_is_over_even_if_the_session_closed_before_saving_that(battle):
    """The state file is only saved now and then. A commander whose session closed at the end still won."""
    (battle / "state.json").write_text(json.dumps({"ended": None, "turn": 3}))
    data = aar.battle_data(battle)
    assert data["ended"] == "Objective achieved." and data["score"]["ended"] == "Objective achieved."


def test_an_objective_done_is_on_the_radio_log_and_the_page(battle):
    rows(battle / "radio_events.jsonl", {"t": 40, "objective_complete": "T1", "text": "Take the bridge.", "met": "x"},
         {"t": 100, "mission_end": "Objective achieved."})
    data = aar.battle_data(battle)
    assert data["objectives_done"] == [{"t": 40, "id": "T1", "text": "Take the bridge."}]
    row = next(row for row in data["radio"] if row.get("kind") == "objective")
    assert row["text"] == "Objective complete: Take the bridge." and row["t"] == 40
    assert [row["t"] for row in data["radio"]] == sorted(row["t"] for row in data["radio"])
    assert data["score"]["questions"] == 0


def test_the_page_holds_this_battle_and_nothing_else(battle):
    data = aar.battle_data(battle)
    assert data["name"] == "Take the village" and data["attempt"] == 2 and data["enemy_total"] == 14
    assert [frame["t"] for frame in data["frames"]] == [5, 90]  # not past the end, and not the next mission
    assert [group["group"] for group in data["frames"][0]["groups"]] == ["Alpha"]  # no observer
    assert data["frames"][1]["groups"][0]["units"] == [[4250, 3950]]  # one position stands in for missing soldiers
    assert data["duration"] == 100 and data["ended_at"] == 100
    assert data["commander"] == {}


def test_belief_comes_from_the_words_alone(battle):
    radio = aar.battle_data(battle)["radio"]
    assert radio[1]["pos"] is None  # a destination isn't a position
    assert radio[2]["pos"] == [4150.0, 4050.0]
    assert radio[3]["checked"] == "B1"
    assert "pos" not in radio[0]  # HQ isn't plotted


def test_orders_and_markers_resolve_to_places(battle):
    data = aar.battle_data(battle)
    assert [order["target"] for order in data["orders"]] == [[4150.0, 4050.0], [4000, 4210], [4150.0, 4150.0]]
    assert data["markers"][0]["id"] == "O1" and data["markers"][0]["pos"] == [4150.0, 4150.0]
    line = next(marker for marker in data["markers"] if marker["id"] == "L1")
    assert line["points"] == [[4050.0, 4050.0], [4250.0, 4050.0]]


def test_a_pinned_marker_keeps_its_exact_place_in_the_review(battle):
    rows(battle / "markers.jsonl", {"id": "E2", "kind": "enemy", "at": "040 042", "building": "B1",
                                    "pos": [4000, 4210], "t": 40})
    rows(battle / "orders.jsonl", {"id": "O-0001", "t": 41, "request": {"to": "Alpha", "legs": [{"type": "CLEAR",
                                                                                               "at": "E2"}]}})
    data = aar.battle_data(battle)
    marker = next(row for row in data["markers"] if row["id"] == "E2")
    assert marker["pos"] == [4000, 4210] and marker["building"] == "B1"
    assert data["orders"][0]["target"] == [4000, 4210]


def test_kills_know_which_side_they_hurt(battle):
    assert [kill["friendly"] for kill in aar.battle_data(battle)["kills"]] == [True, False]


def test_the_observer_slots_soldier_isnt_one_of_the_battles_deaths(battle):
    with (battle.parent / "kills.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps({"t": 80, "victim": "Observer", "side": "WEST", "victimPos": [4100, 3800, 0]}) + "\n")
    rows(battle.parent / "truth.jsonl",
         {"t": 5, "groups": [{"group": "Alpha 1-1", "side": "WEST", "able": 1, "pos": [4100.2, 3800.1]},
                             {"group": "Alpha", "side": "WEST", "able": 8, "pos": [4100, 3700]}]})
    assert [kill["victim"] for kill in aar.battle_data(battle)["kills"]] == ["Owen King", "Habib Noori"]


def test_a_turn_still_open_at_the_end_is_kept(battle):
    assert [turn["turn"] for turn in aar.battle_data(battle)["turns"]] == [1, 2, 3]


def transcript(projects: Path, name: str = "session") -> None:
    projects.mkdir(parents=True, exist_ok=True)
    def said(seconds, message_id, *blocks, output=10):
        return {"type": "assistant", "timestamp": stamp(seconds), "message": {
            "id": message_id, "model": "claude-haiku-5-5", "content": list(blocks),
            "usage": {"output_tokens": output, "input_tokens": 5, "cache_read_input_tokens": 100}}}

    def use(tool, **data):
        return {"type": "tool_use", "name": f"mcp__commander__commander_{tool}", "input": data}

    rows(projects / f"{name}.jsonl",
         said(-100, "old", use("order", to="Bravo")),  # another battle
         {"type": "attachment", "timestamp": stamp(1), "attachment": {
             "type": "session_context", "context": {"userEmail": "someone@example.com"}}},
         {"type": "attachment", "timestamp": stamp(1), "attachment": {
             "type": "model", "identity": {"marketingName": "Haiku 5.5"}}},
         {"type": "user", "timestamp": stamp(2), "message": {"content": "start"}},
         said(3, "m1", {"type": "thinking", "thinking": ""}),
         said(3, "m1", use("mission")),
         said(4, "m2", use("order", to="Alpha", legs=[{"type": "MOVE", "at": "041 040"}])),
         said(5, "m3", {"type": "text", "text": "Alpha has its order."}),
         {"type": "user", "timestamp": stamp(6), "message": {"content":
          '<channel source="commander" turn="2" woke_on="1 message">\nT+00:05 | turn 2'}},
         said(7, "m4", use("notes", text="Alpha moving.")),
         said(7, "m5", {"type": "text", "text": "Waiting."}),
         {"type": "user", "timestamp": stamp(8), "message": {"content": "Are you enjoying this?"}},
         said(9, "m6", {"type": "text", "text": "I can't talk about the battle."}),
         {"type": "user", "timestamp": stamp(10), "message": {"content":
          '<channel source="commander" turn="3" woke_on="notice">\nMISSION END'}},
         said(11, "m7", {"type": "text", "text": "Done."}))


def in_window(battle: Path, end_s: float = 12) -> None:
    os.utime(battle.parent / "battle.json", (START, START))
    os.utime(battle / "state.json", (START + end_s, START + end_s))


def test_the_commanders_own_words_and_actions_are_found_per_turn(battle, tmp_path):
    projects = tmp_path / "projects"
    transcript(projects)
    in_window(battle)
    session = aar.commander_session(battle, projects)
    assert session["model"] == "Haiku 5.5"
    assert session["turns"][1]["said"] == [{"t": 2.0, "text": "Alpha has its order."}]
    assert [action["tool"] for action in session["turns"][1]["actions"]] == ["order"]
    assert session["turns"][1]["actions"][0]["input"]["to"] == "Alpha"
    assert session["turns"][2]["actions"][0]["input"] == {"text": "Alpha moving."}
    assert session["turns"][3]["said"] == [{"t": 8.0, "text": "Done."}]
    assert session["turns"][1]["actions"][0]["t"] == 1.0  # counted from its first look at the mission
    assert session["requests"] == 6 and session["output_tokens"] == 60  # each request once, however many blocks


def test_a_wake_during_a_busy_turn_is_placed_by_time(battle, tmp_path):
    """A wake that arrives while the model is busy leaves only a queue row, with no channel message to go by."""
    projects = tmp_path / "projects"
    projects.mkdir()
    rows(projects / "session.jsonl",
         {"type": "user", "timestamp": stamp(2), "message": {"content": "start"}},
         {"type": "assistant", "timestamp": stamp(3), "message": {"id": "a", "content": [
             {"type": "tool_use", "name": "mcp__commander__commander_mission", "input": {}}]}},
         {"type": "queue-operation", "timestamp": stamp(8), "operation": "enqueue"},
         {"type": "assistant", "timestamp": stamp(9), "message": {"id": "b", "content": [
             {"type": "tool_use", "name": "mcp__commander__commander_notes", "input": {"text": "Later."}},
             {"type": "text", "text": "Six seconds in."}]}})
    in_window(battle)
    turns = aar.commander_session(battle, projects)["turns"]  # the battle's turn 2 starts at T+5
    assert turns[2]["said"] == [{"t": 6.0, "text": "Six seconds in."}]
    assert turns[2]["actions"][0]["t"] == 6.0 and not turns[1]["said"]


def test_the_page_shows_only_what_was_said_by_each_moment(battle):
    page = aar.render(aar.battle_data(battle))
    assert "const by = item => item.t <= now || now >= duration;" in page
    assert "if (t.start > now) break;\n    if (t.said" not in page


def test_tools_the_session_was_really_offered_are_checked(battle, tmp_path):
    projects = tmp_path / "projects"
    transcript(projects)
    with (projects / "session.jsonl").open("a", encoding="utf-8") as file:
        shape = {"type": "api-request-shape", "tools": [{"name": "SendFeedback"}, {"name": "ToolSearch"}]}
        file.write(json.dumps(shape) + "\n")
    in_window(battle)
    session = aar.commander_session(battle, projects)
    assert session["tools_outside_lockdown"] == ["SendFeedback"]
    assert aar.battle_data(battle, session)["commander"]["tools_outside_lockdown"] == ["SendFeedback"]


def test_a_chat_with_a_person_during_the_battle_is_left_out(battle, tmp_path):
    projects = tmp_path / "projects"
    transcript(projects)
    in_window(battle)
    turns = aar.commander_session(battle, projects)["turns"].values()
    words = [item["text"] for turn in turns for item in turn["said"]]
    assert "Waiting." in words and "I can't talk about the battle." not in words


def test_only_the_commanders_words_reach_the_page(battle, tmp_path):
    projects = tmp_path / "projects"
    transcript(projects)
    in_window(battle)
    data = aar.battle_data(battle, aar.commander_session(battle, projects))
    assert "someone@example.com" not in aar.render(data)
    assert [item["text"] for item in data["turns"][0]["said"]] == ["Alpha has its order."]
    assert data["commander"]["model"] == "Haiku 5.5" and "turns" not in data["commander"]


def test_no_session_means_the_page_says_nobody_commanded(battle, tmp_path):
    in_window(battle)
    assert aar.commander_session(battle, tmp_path / "nothing") is None
    other_time = tmp_path / "projects"
    transcript(other_time)
    os.utime(battle.parent / "battle.json", (START + 5000, START + 5000))
    os.utime(battle / "state.json", (START + 6000, START + 6000))
    assert aar.commander_session(battle, other_time) is None


def test_a_broken_transcript_line_doesnt_stop_the_review(battle, tmp_path):
    projects = tmp_path / "projects"
    transcript(projects)
    with (projects / "session.jsonl").open("a", encoding="utf-8") as file:
        file.write('{"type": "assistant", "timest\n')
    in_window(battle)
    assert aar.commander_session(battle, projects)["model"] == "Haiku 5.5"


def test_text_in_the_data_cant_break_out_of_the_page(battle):
    rows(battle / "radio.jsonl", {"t": 1, "from": "Alpha", "to": "HQ", "text": "</script><script>alert(1)</script>",
                                  "kind": "report"})
    page = aar.render(aar.battle_data(battle))
    assert "</script><script>alert" not in page
    assert aar.DATA_SLOT not in page


def test_write_puts_the_page_beside_the_records(battle, tmp_path):
    result = aar.write(battle, projects=tmp_path / "nothing")
    assert Path(result["review"]) == battle.parent / "review.html"
    assert result["commander"] == "no model session found" and Path(result["review"]).stat().st_size > 1000


def test_scorecard(battle):
    score = aar.battle_data(battle)["score"]
    assert score["ended"] == "Objective achieved." and score["duration_s"] == 100
    assert score["friendly_total"] == 8 and score["enemy_total"] == 14
    assert score["orders"] == 3 and score["turns"] == 3 and score["enemy_markers"] == 1
    assert score["first_contact_s"] is None
    assert score["marker_error_m"] == 0  # marker E1 is on the patrol the first truth frame after it shows


def test_the_enemy_is_counted_from_truth_so_a_crewed_gun_is_its_crew():
    """A gun's entry has no units: the scenario's default of 4 would count one gunner as four men."""
    frames = [{"t": 5, "groups": [{"group": "East Gun", "alive": 1}, {"group": "East Section", "alive": 6}]},
              {"t": 10, "groups": [{"group": "East Gun", "alive": 0}, {"group": "East Section", "alive": 5}]}]
    enemies = [{"id": "East Gun", "vehicle": "O_HMG_01_high_F"}, {"id": "East Section", "units": 6},
               {"id": "Never Seen", "units": 3}, {"id": "Unseen Gun", "vehicle": "O_HMG_01_F"}]
    assert aar._strength(frames, enemies) == 1 + 6 + 3 + 1


@pytest.mark.parametrize("ended, word", [
    ("Objective achieved: the enemy has been cleared.", "won"),
    ("Mission failed: 9 of your 17 men are dead or down.", "failed"),
    ("All stations have been lost.", "failed"),
    ("Time limit reached.", "time limit"),
    (None, "unfinished"),
    ("", "unfinished"),
])
def test_each_ending_is_one_outcome(ended, word):
    assert aar.outcome(ended) == word


def test_a_silenced_station_is_noticed_when_the_commander_speaks_to_it():
    data = {"events": [{"t": 400, "event": "kill_station Kilo"}],
            "orders": [{"t": 300, "to": "Kilo"}, {"t": 520, "to": "Reserve"}, {"t": 700, "to": "Kilo"}],
            "radio": [{"t": 650, "kind": "question", "to": "Kilo"}, {"t": 410, "kind": "report", "from": "Kilo"}]}
    assert aar._silence(data) == {"silenced": "Kilo", "silence_noticed_s": 250}
    assert aar._silence({**data, "orders": [], "radio": []}) == {"silenced": "Kilo", "silence_noticed_s": None}
    assert aar._silence({"events": [], "orders": [], "radio": []}) == {"silenced": None, "silence_noticed_s": None}


def test_the_scorecard_has_each_benchmark_measure(battle):
    radio = (battle / "radio.jsonl").read_text(encoding="utf-8")
    (battle / "radio.jsonl").write_text(radio + json.dumps(
        {"t": 70, "from": "Alpha", "to": "HQ", "text": "Contact, one emplacement, north, roughly 300 metres. Listed as "
         "T1.", "kind": "report"}) + "\n", encoding="utf-8")
    info = json.loads((battle.parent / "battle.json").read_text(encoding="utf-8"))
    drawn = [["enemies[1].at", "033 027"]]
    (battle.parent / "battle.json").write_text(json.dumps({**info, "seed": 116, "drawn": drawn}))
    data = aar.battle_data(battle)
    score = data["score"]
    assert score["outcome"] == "won" and score["seed"] == 116
    assert score["threat_reported_s"] == 70 and score["rounds_per_kill"] is None and score["silenced"] is None
    # 8 killed: the garrison is gone from the last frame, and the patrol's 6 are still standing.
    assert aar.scorecard({**data, "shells": [{"friendly": True}] * 9})["rounds_per_kill"] == 1.1


def test_a_friendly_killed_by_his_own_side_counts_whatever_the_weapon(battle):
    rows(battle.parent / "kills.jsonl",
         {"t": 20, "victim": "Owen King", "side": "WEST", "victimPos": [4100, 3700, 0], "killer": "Hawg gunner",
          "killerSide": "WEST", "weapon": "gatling_30mm", "distance": 900},
         {"t": 30, "victim": "Sam Reed", "side": "WEST", "victimPos": [4100, 3700, 0], "killer": "Khalil Amani",
          "killerSide": "EAST", "weapon": "AK", "distance": 208},
         {"t": 40, "victim": "Leo Hart", "side": "WEST", "victimPos": [4100, 3700, 0], "killer": "Leo Hart",
          "killerSide": "WEST", "weapon": "", "distance": 0},
         {"t": 50, "victim": "Habib Noori", "side": "EAST", "victimPos": [4250, 3950, 0], "killer": "Kyle Smith",
          "killerSide": "WEST", "weapon": "MX", "distance": 337})
    assert aar.battle_data(battle)["score"]["friendly_fire_deaths"] == 1  # not the enemy's, not his own fall


def test_compare_writes_one_csv_row_per_battle_with_its_seed_and_what_it_hid(battle, tmp_path):
    info = json.loads((battle.parent / "battle.json").read_text(encoding="utf-8"))
    scenario = {**info["scenario"], "enemies": [{"id": "East Gun", "at": "033 028", "vehicle": "O_HMG_01_high_F"}],
                "events": [{"action": "kill_station", "station": "Kilo", "at": "8:25"}]}
    (battle.parent / "battle.json").write_text(json.dumps({**info, "seed": 7, "scenario": scenario}))
    lines = aar.compare(Home(tmp_path), scenario="take_the_village", as_csv=True).splitlines()
    assert lines[0].split(",")[:6] == ["battle", "scenario", "model", "seed", "hidden", "outcome"]
    row = dict(zip(lines[0].split(","), lines[1].split(","), strict=True))
    assert row["battle"] == "20261105-043541:2" and row["seed"] == "7" and row["model"] == "Scripted"
    assert row["hidden"] == "East Gun 033 028; kill_station Kilo at 8:25" and row["enemy_total"] == "1"


def test_position_error_compares_the_last_report_with_where_the_station_was(tmp_path):
    data = {"radio": [{"t": 10, "from": "Alpha", "pos": [100.0, 100.0]}], "markers": [], "stations": {}, "enemies": [],
            "frames": [
                {"t": 5, "groups": [{"group": "Alpha", "able": 4, "pos": [0, 0], "units": []}]},  # nothing heard yet
                {"t": 20, "groups": [{"group": "Alpha", "able": 4, "pos": [100, 130], "units": []}]},
                {"t": 30, "groups": [{"group": "Alpha", "able": 4, "pos": [100, 150], "units": []}]},
                {"t": 40, "groups": [{"group": "Alpha", "able": 0, "pos": [], "units": []}]}]}  # dead: no position
    assert aar._position_error(data) == 40


def test_compare_lines_up_battles_of_one_scenario(battle, tmp_path):
    home = Home(tmp_path)
    second = battle.parent.parent / "commander-3" / "west"
    second.parent.mkdir()
    for name in ("battle.json", "truth.jsonl", "kills.jsonl"):
        (second.parent / name).write_bytes((battle.parent / name).read_bytes())
    second.mkdir()
    for name in ("radio.jsonl", "radio_events.jsonl", "turns.jsonl", "orders.jsonl", "markers.jsonl", "state.json"):
        (second / name).write_bytes((battle / name).read_bytes())
    table = aar.compare(home)
    assert "20261105-043541:2" in table and "20261105-043541:3" in table
    assert "Friendly lost" in table and "Scripted" in table
    named = aar.compare(home, ["20261105-043541:2"])
    assert "20261105-043541:3" not in named


def test_compare_skips_battles_that_never_finished(battle, tmp_path):
    (battle / "state.json").write_text("{}")
    (battle / "radio_events.jsonl").unlink()
    with pytest.raises(ValueError, match="no finished battle"):
        aar.compare(Home(tmp_path))


def another_attempt(battle: Path, attempt: int, scenario: dict | None = None) -> Path:
    folder = battle.parent.parent / f"commander-{attempt}" / "west"
    folder.parent.mkdir()
    for name in ("battle.json", "truth.jsonl", "kills.jsonl"):
        (folder.parent / name).write_bytes((battle.parent / name).read_bytes())
    folder.mkdir()
    for name in ("radio.jsonl", "radio_events.jsonl", "turns.jsonl", "orders.jsonl", "markers.jsonl", "state.json"):
        (folder / name).write_bytes((battle / name).read_bytes())
    info = json.loads((folder.parent / "battle.json").read_text())
    info["attempt"] = attempt
    if scenario:
        info["scenario"] = scenario
    (folder.parent / "battle.json").write_text(json.dumps(info))
    return folder


def embedded(page: Path) -> dict:
    text = page.read_text(encoding="utf-8")
    start = text.index('type="application/json">') + len('type="application/json">')
    return json.loads(text[start:text.index("</script>", start)])


def test_a_site_holds_each_battle_under_its_label_and_opens_on_the_first(battle, tmp_path):
    another_attempt(battle, 3)
    out = tmp_path / "site.html"
    battles = ["20261105-043541:3=Rigid script", "20261105-043541:2"]
    result = aar.site(Home(tmp_path), battles, out, tmp_path / "nothing")
    assert result["opens_on"] == "Rigid script" and [row["id"] for row in result["battles"]] == [
        "20261105-043541-3", "20261105-043541-2"]
    page = embedded(out)
    assert [b["id"] for b in page["battles"]] == ["20261105-043541-3", "20261105-043541-2"]
    assert [b["label"] for b in page["battles"]] == ["Rigid script", "Script"]  # nobody's named, so nobody's implied
    assert all(b["commander"] == {} for b in page["battles"])
    assert aar.DATA_SLOT not in out.read_text(encoding="utf-8")


def test_the_page_opens_at_the_start_on_the_commander_tab(battle):
    page = aar.render(aar.battle_data(battle))
    assert 'tab = "commander"' in page and "now = t == null ? 0 :" in page
    assert page.index('data-pane="commander"') < page.index('data-pane="reality"')
    assert 'id="pane-reality" role="tabpanel" hidden' in page


def test_the_page_chooses_battles_from_a_dropdown_under_the_owners_labels(battle):
    page = aar.render(aar.battle_data(battle))
    assert '<select id="picker"' in page and 'class="pick"' not in page
    for label in ("INTERNAL BELIEF", "IN-GAME", "THOUGHTS", "NOTES", "MARKERS", "Requests", "Tokens written"):
        assert label in page
    for gone in ("<header", "What the commander believed", "What was really happening", "Extra access"):
        assert gone not in page


def test_a_site_compares_with_the_same_measures_as_the_terminal(battle, tmp_path):
    another_attempt(battle, 3)
    out = tmp_path / "site.html"
    aar.site(Home(tmp_path), ["20261105-043541:2=One", "20261105-043541:3=Two"], out, tmp_path / "nothing")
    table = embedded(out)["compare"]
    assert table["ids"] == ["20261105-043541-2", "20261105-043541-3"]
    assert table["rows"][0] == ["", "One", "Two"]
    measures = [row[0] for row in table["rows"]]
    assert measures == ["", "Scenario", "Commander", *[label for label, _ in aar.COMPARED], "Tokens written"]
    terminal = aar.compare(Home(tmp_path), ["20261105-043541:2", "20261105-043541:3"])
    assert all(measure in terminal for measure in measures)
    assert next(row for row in table["rows"] if row[0] == "Commander")[1:] == ["Script, no AI", "Script, no AI"]


def test_a_site_leaves_a_different_mission_out_of_the_comparison(battle, tmp_path):
    another_attempt(battle, 3, {**SCENARIO, "name": "something_else"})
    out = tmp_path / "site.html"
    result = aar.site(Home(tmp_path), ["20261105-043541:2", "20261105-043541:3=Other"], out, tmp_path / "nothing")
    page = embedded(out)
    assert len(page["battles"]) == 2 and page["compare"]["ids"] == ["20261105-043541-2"]
    assert [row["compared"] for row in result["battles"]] == [True, False]


def test_a_site_can_read_a_records_folder_directly(battle, tmp_path):
    out = tmp_path / "site.html"
    aar.site(Home(tmp_path / "empty"), [f"{battle}=From a folder"], out, tmp_path / "nothing")
    assert embedded(out)["battles"][0]["id"] == "20261105-043541-2"


def test_a_site_needs_a_battle(tmp_path):
    with pytest.raises(ValueError, match="at least one"):
        aar.site(Home(tmp_path), [], tmp_path / "site.html")


def test_a_site_keeps_private_text_out_and_cant_be_broken_out_of(battle, tmp_path):
    projects = tmp_path / "projects"
    transcript(projects)
    in_window(battle)
    rows(battle / "radio.jsonl", {"t": 1, "from": "Alpha", "to": "HQ", "text": "</script><script>alert(1)</script>",
                                  "kind": "report"})
    out = tmp_path / "site.html"
    aar.site(Home(tmp_path), ["20261105-043541:2"], out, projects)
    text = out.read_text(encoding="utf-8")
    assert "someone@example.com" not in text and "</script><script>alert" not in text
    assert embedded(out)["battles"][0]["label"] == "Haiku 5.5"


def test_how_often_a_tool_outside_the_lockdown_was_used_is_counted(battle, tmp_path):
    projects = tmp_path / "projects"
    transcript(projects)
    with (projects / "session.jsonl").open("a", encoding="utf-8") as file:
        for row in ({"type": "assistant", "timestamp": stamp(11), "message": {"id": "m8", "content": [
                         {"type": "tool_use", "name": "SendFeedback", "input": {"title": "A private bug report"}}]}},
                    {"type": "api-request-shape", "tools": [{"name": "SendFeedback"}, {"name": "Artifact"}]}):
            file.write(json.dumps(row) + "\n")
    in_window(battle)
    session = aar.commander_session(battle, projects)
    assert session["tools_outside_lockdown"] == ["Artifact", "SendFeedback"]
    assert session["outside_lockdown_used"] == {"SendFeedback": 1}
    assert "A private bug report" not in aar.render(aar.battle_data(battle, session))  # that it was used, not its words


def test_finding_a_battle(battle, tmp_path):
    home = Home(tmp_path)
    assert aar.find_battle(home) == battle
    later = tmp_path / "runs" / "20261105-043541" / "commander-11" / "west"
    later.mkdir(parents=True)
    rows(later / "radio.jsonl")
    assert aar.find_battle(home) == later  # 11 comes after 2
    assert aar.find_battle(home, "20261105-043541", 2) == battle
    with pytest.raises(ValueError, match="no run called"):
        aar.find_battle(home, "nope")
    with pytest.raises(ValueError, match="no commander battle"):
        aar.find_battle(home, "20261105-043541", 5)


# -- what gets recorded in the first place ---------------------------------------------------------------------------

GROUP = {"group": "Alpha", "side": "WEST", "able": 4, "pos": [3050, 3050]}


def test_truth_stops_soon_after_the_battle_ends(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.game.emit(type="cmd_truth", t=110, groups=[GROUP])
    b.silent(110)
    b.runtime._end("Time limit reached.")
    b.game.emit(type="cmd_truth", t=112, groups=[GROUP])
    b.game.emit(type="killed", t=113, victim="Late", side="WEST")
    b.silent(113)
    b.game.emit(type="cmd_truth", t=140, groups=[GROUP])
    b.game.emit(type="killed", t=141, victim="Next battle", side="WEST")
    b.silent(141)
    assert [row["t"] for row in b.records.read_truth()] == [10.0, 12.0]
    assert [row["victim"] for row in b.records.read_kills()] == ["Late"]


def test_truth_from_the_next_mission_isnt_recorded(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.game.emit(type="cmd_truth", t=110, groups=[GROUP])
    b.silent(110)
    b.game.emit(type="cmd_truth", t=20, groups=[GROUP])  # a new mission's clock, seen by a server still running
    b.silent(20)
    b.game.queue.append({"seq": 99, "k": "mission", "state": "start"})
    b.game.emit(type="cmd_truth", t=150, groups=[GROUP])
    b.silent(150)
    assert [row["t"] for row in b.records.read_truth()] == [10.0]


def test_a_saved_battle_remembers_it_has_ended(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.silent(110)
    b.runtime._end("Time limit reached.")
    b.runtime.save()
    resumed = b.new_runtime()
    assert resumed.ended_at == 10 and resumed.restarted is False


def test_old_truth_records_still_read():
    """Before the rename, the truth record called the able members "alive", and old battles are still reviewed."""
    from arma_harness.commander.aar import _able
    assert _able({"group": "Alpha", "alive": 3}) == 3 and _able({"group": "Alpha", "able": 2}) == 2
