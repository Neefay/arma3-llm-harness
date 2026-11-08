"""What an audit of the commander found: inputs an LLM can plausibly send, and states a restart or a race can leave."""
from __future__ import annotations

import pytest
from test_commander import ALL_TYPES, BUILDINGS, MARKERS, STATIONS, Battle, chained, with_buildings

from arma_harness.commander import orders, scenario
from arma_harness.commander.orders import Invalid
from arma_harness.commander.runtime import Runtime


def test_one_bad_event_is_skipped_and_the_battle_goes_on(tmp_path):
    """A KeyError in one event used to stop the cursor there for good: the same batch, replayed every second."""
    b = Battle(tmp_path)
    b.start()
    b.game.emit(type="cmd_report", t=102, callsign="Alpha")  # no position, no strength: not a packet at all
    b.advance(104, pos=[3150, 3050])
    assert b.runtime.mission_t == 104 and b.runtime.packets["Alpha"]["pos"] == [3150, 3050]
    assert "event skipped" in (b.records.folder / "operator.log").read_text(encoding="utf-8")


def test_a_station_objective_needs_its_place_and_distance():
    raw = {"name": "t", "mission": "m", "text": "t", "time_limit": "1:00",
           "stations": [{"callsign": "A", "role": "r", "capabilities": [], "at": "000 000"}]}
    with pytest.raises(ValueError, match="of and within_m"):
        scenario.build({**raw, "success": {"station": "A", "of": "040 060"}})


@pytest.mark.parametrize("count", ["3", -1, 2.5, 0, True])
def test_a_schedule_count_is_a_whole_number(tmp_path, count):
    b = chained(tmp_path)
    with pytest.raises(Invalid, match="count must be"):
        b.runtime.schedule({"wake": "check"}, every="1:00", count=count)


def test_a_scheduled_order_can_use_the_vehicle_list(tmp_path):
    b = chained(tmp_path)
    made = b.runtime.schedule({"order": {"to": "Alpha", "legs": [{"type": "MOUNT", "vehicle": "V1"}]}}, after="1:00")
    assert made["id"]


@pytest.mark.parametrize("what", ["Alpha", ["Alpha"]])
def test_a_scheduled_ask_or_order_needs_its_fields(tmp_path, what):
    b = chained(tmp_path)
    with pytest.raises(Invalid, match="needs its fields"):
        b.runtime.schedule({"ask": what}, after="1:00")


def test_a_new_marker_never_takes_an_id_already_used(tmp_path):
    b = with_buildings(tmp_path)
    b.start()
    b.runtime.mark({"id": "M1", "kind": "enemy", "at": "036 031", "label": "First"})
    b.runtime.mark({"kind": "note", "at": "037 031", "label": "Second"})
    assert b.runtime.markers["M1"]["label"] == "First" and b.runtime.markers["M2"]["label"] == "Second"
    b.runtime.mark({"id": 5, "at": "037 032"})  # a number from the LLM is the same id as its text
    assert "5" in b.runtime.markers and 5 not in b.runtime.markers


def test_an_aid_post_never_takes_a_scenario_vehicles_id(tmp_path):
    b = chained(tmp_path)
    b.runtime.vehicles["A1"] = {"id": "A1", "key": "A1", "name": "Ambulance", "at": "031 030", "t": None,
                                "wrecked": False}
    b.advance(102, medical=[["O-1", "post", "post", "", "up", ["P1", "040060"]]])
    assert b.runtime.vehicles["A1"]["name"] == "Ambulance" and b.runtime.vehicles["A2"]["key"] == "P1"


def test_patrol_takes_building_ids_as_its_help_says():
    stations = {"Alpha": {**STATIONS["Alpha"], "capabilities": ["PATROL"]}}
    order = orders.validate({"to": "Alpha", "legs": [{"type": "PATROL", "at": ["B1", "B3"]}]}, stations, MARKERS, 8192,
                            BUILDINGS)
    assert [leg["grid"] for leg in order["route"]["legs"]] == ["034 030", "039 039"]


def test_only_waypoints_are_appended():
    stations = {"Alpha": {**STATIONS["Alpha"], "capabilities": ALL_TYPES}}
    with pytest.raises(Invalid, match="Only MOVE, HOLD, SEARCH and SENTRY can be appended"):
        orders.validate({"to": "Alpha", "mode": "append", "legs": [{"type": "CLEAR", "at": ["B1"]}]}, stations,
                        MARKERS, 8192, BUILDINGS)


def test_nothing_is_appended_after_clearing(tmp_path):
    b = with_buildings(tmp_path)
    b.start()
    b.runtime.order({"to": "Alpha", "legs": [{"type": "CLEAR", "at": ["B1", "B2"]}]})
    with pytest.raises(Invalid, match="CLEAR isn't a route of waypoints"):
        b.runtime.order({"to": "Alpha", "mode": "append", "legs": [{"type": "MOVE", "at": "034 030"}]})


@pytest.mark.parametrize(("call", "words"), [
    (lambda r: r.order({"to": ["Alpha", "Bravo"], "legs": [{"type": "MOVE", "at": "034 030"}]}), "Unknown callsign"),
    (lambda r: r.ask(["Alpha"]), "to is one callsign"),
    (lambda r: r.ask("Alpha", "position"), "topics is a list"),
    (lambda r: r.notes(None), "Notes are text"),
    (lambda r: r.log(limit="ten"), "Bad limit"),
    (lambda r: r.map_image(radius="big"), "Bad radius"),
    (lambda r: r.map_image(radius=float("nan")), "Bad radius"),
    (lambda r: r.order({"to": "Alpha", "legs": [{"type": "CLEAR", "at": "034 030", "radius": "inf"}]}), "Bad radius"),
])
def test_bad_arguments_are_refused_with_words_not_a_crash(tmp_path, call, words):
    b = with_buildings(tmp_path)
    b.start()
    with pytest.raises(Invalid, match=words):
        call(b.runtime)


def test_after_a_restart_nothing_runs_until_the_clock_is_back(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.runtime.save()
    again = b.new_runtime()  # as the server rebuilds it, before the game's first tick
    with pytest.raises(Invalid, match="isn't up yet"):
        again.schedule({"wake": "check"}, after="2:00")
    b.runtime = again
    b.advance(150)
    assert again.schedule({"wake": "check"}, after="2:00")["id"]


def test_ids_carry_on_from_the_records_after_a_crash(tmp_path):
    """Rows are written at once and counters only on save: a crash between used to reuse an order's id."""
    b = chained(tmp_path)
    b.runtime.save()
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOVE", "at": "034 030"}]})  # written, but not saved
    again = Runtime(b.game, b.scenario, b.records, lambda text, meta: None, world_size=8192)
    assert again._id("O") == "O-0002"
