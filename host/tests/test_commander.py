"""Commander mode, offline: report wording, wake timing, orders, and above all that the fog holds."""
from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pytest

from arma_harness.commander import orders, reports, scenario
from arma_harness.commander.orders import Invalid
from arma_harness.commander.records import Records
from arma_harness.commander.reports import Tracker
from arma_harness.commander.runtime import Runtime
from arma_harness.commander.server import TOOL_NAMES, Server
from arma_harness.commander.wake import DELIVER, HOLD, WakeLogic
from arma_harness.config import REPO_ROOT


@pytest.fixture(autouse=True)
def exact_bearings(monkeypatch):
    """Bearings carry a random error, tested on its own below. Everywhere else, the words need to be predictable."""
    monkeypatch.setattr(reports, "_wobble", lambda spread: 0)


def packet(**over) -> dict:
    base = {"callsign": "Alpha", "pos": [3050.0, 3050.0], "grid": "030030", "dir": 90, "speed": 0, "alive": 4,
            "wounded": 0, "baseline": 4, "leader": "Sam Reed", "rounds": 400, "rounds_baseline": 400,
            "behaviour": "AWARE", "combat_mode": "YELLOW", "order": "", "unable": "", "leg": 0, "legs": 1,
            "contacts": []}
    return {**base, **over}


def contact(x=3250.0, y=3250.0, age=2.0, kind="infantry") -> dict:
    return {"pos": [x, y], "kind": kind, "age_s": age, "accuracy_m": 1}


def route(*legs, kind="route") -> dict:
    return {"kind": kind, "legs": [{"type": t, "pos": list(p), "grid": g, "completion": 0} for t, p, g in legs]}


# -- wording --------------------------------------------------------------------------------------


def test_rounding_and_buckets():
    assert reports.format_grid("052191") == "052 191"
    assert reports.compass(0, 10) == "north" and reports.compass(10, 10) == "north-east"
    assert reports.compass(-10, 0) == "west"
    assert reports.rough_range(287) == "roughly 300 metres" and reports.rough_range(730) == "roughly 700 metres"
    assert reports.rough_range(2000) == "distant"
    assert [reports.count_word(n) for n in (1, 2, 4, 8, 12, 40)] == ["one", "a couple of", "a few", "about 8",
                                                                     "a dozen", "many"]
    assert [reports.ammo_band(r, 100) for r in (100, 48, 20, 1)] == ["green", "amber", "red", "black"]


def test_sitrep_and_specific_answers():
    text = reports.answer(packet(wounded=1, alive=3, rounds=190, contacts=[contact()]), None)
    assert "Grid 030 030, stationary." in text and "3 of 4 effective, 1 wounded" in text
    assert "Sam Reed has command" in text and "Ammo amber, about half." in text and "No current orders." in text
    assert "One infantry, bearing 045, roughly 300 metres, seen now." in text
    assert reports.answer(packet(), None, ["ammo"]) == "Ammo green, good."
    trip = route(("MOVE", (3450, 3050), "034 030"))
    assert "About 3 minutes to grid 034 030" in reports.answer(packet(), trip, ["eta"])
    assert reports.answer(packet(), trip, ["task"]) == "Moving to grid 034 030, about 400 metres out."


def test_contacts_group_by_direction_and_drop_when_forgotten():
    groups = reports.contact_groups(packet(contacts=[contact(), contact(3260, 3260), contact(3050, 2900, age=60)]))
    assert [(g["direction"], g["count"]) for g in groups] == [("north-east", 2), ("south", 1)]
    assert reports.contact_groups(packet(contacts=[contact(age=400)])) == []
    assert reports.answer(packet(contacts=[contact(age=70)]), None, ["contacts"]).endswith("last seen a minute ago.")


# -- what is worth saying ---------------------------------------------------------------------------


def test_move_is_acknowledged_once_and_arrival_reported_once():
    tracker, trip = Tracker(), route(("MOVE", (3450, 3050), "034 030"))
    said = tracker.update(packet(order="O-1"), trip, 10)
    assert [r.text for r in said] == ["Copy, moving to grid 034 030."] and said[0].grid is None
    assert tracker.update(packet(order="O-1", pos=[3200, 3050]), trip, 12) == []
    arrived = tracker.update(packet(order="O-1", pos=[3450, 3050], grid="034030", leg=1), trip, 14)
    assert [r.text for r in arrived] == ["Arrived, grid 034 030."] and arrived[0].grid == "034 030"
    assert tracker.update(packet(order="O-1", pos=[3450, 3050], grid="034030", leg=1), trip, 16) == []


def test_hold_reports_on_station_by_distance_because_it_never_completes():
    tracker, trip = Tracker(), route(("HOLD", (3450, 3050), "034 030"))
    tracker.update(packet(order="O-1"), trip, 0)
    assert tracker.update(packet(order="O-1", pos=[3400, 3050]), trip, 2) == []
    near = tracker.update(packet(order="O-1", pos=[3430, 3050], grid="034030"), trip, 4)
    assert [r.text for r in near] == ["On station, grid 034 030."]
    assert tracker.update(packet(order="O-1", pos=[3430, 3050], grid="034030"), trip, 6) == []


def test_multi_leg_route_passes_then_arrives():
    tracker = Tracker()
    trip = route(("MOVE", (3200, 3050), "032 030"), ("MOVE", (3450, 3050), "034 030"))
    tracker.update(packet(order="O-1"), trip, 0)
    assert [r.text for r in tracker.update(packet(order="O-1", leg=1, grid="032030"), trip, 2)] == [
        "Passing grid 032 030, at grid 032 030."]
    assert [r.text for r in tracker.update(packet(order="O-1", leg=2, grid="034030"), trip, 4)] == [
        "Arrived, grid 034 030."]


def test_move_then_hold_at_the_same_grid_doesnt_report_passing_it():
    tracker = Tracker()
    trip = route(("MOVE", (3450, 3050), "034 030"), ("HOLD", (3450, 3050), "034 030"))
    tracker.update(packet(order="O-1"), trip, 0)
    said = tracker.update(packet(order="O-1", leg=1, pos=[3450, 3050], grid="034030"), trip, 2)
    assert [r.text for r in said] == ["On station, grid 034 030."]


def clear_route(*ids) -> dict:
    return {"kind": "route", "legs": [{"type": "CLEAR", "pos": [4150, 4150], "grid": "041 041", "completion": 0,
                                       "ids": list(ids)}]}


def test_clear_reports_each_building_and_never_claims_all_clear():
    tracker, trip = Tracker(), clear_route("B1", "B3")
    said = tracker.update(packet(order="O-1", clearing=30, cleared=[]), trip, 0)
    assert [r.text for r in said] == ["Copy, checking B1, B3."]
    assert reports.answer(packet(order="O-1", clearing=30, cleared=["B1"]), trip, ["task"]) == "Checking B3."
    said = tracker.update(packet(order="O-1", clearing=12, cleared=["B1"]), trip, 200)  # slow isn't stuck
    assert [(r.text, r.checked) for r in said] == [("B1 checked, nothing seen.", "B1")]
    assert tracker.update(packet(order="O-1", clearing=12, cleared=["B1"]), trip, 202) == []
    said = tracker.update(packet(order="O-1", clearing=0, cleared=["B1", "B3"], grid="041041",
                                 contacts=[contact(3060, 3060)]), trip, 300)
    assert "B3 checked, enemy still in the area." in [r.text for r in said]
    assert "Finished checking B1, B3, at grid 041 041." in [r.text for r in said]
    assert tracker.update(packet(order="O-1", clearing=0, cleared=["B1", "B3"]), trip, 302) == []


def test_clear_with_no_buildings_says_so():
    said = Tracker().update(packet(order="O-1", clearing=0), clear_route(), 0)
    assert "No known buildings there." in [r.text for r in said]


def test_contacts_near_a_numbered_building_say_which():
    buildings = [{"id": "B3", "pos": [3260.0, 3260.0]}, {"id": "B4", "pos": [3700.0, 3700.0]}]
    said = Tracker().update(packet(contacts=[contact(3250, 3250)]), None, 0, buildings)
    assert said[0].text == "Contact, one infantry, bearing 045, roughly 300 metres, near B3. Engaging, at grid 030 030."
    assert "near" not in Tracker().update(packet(contacts=[contact(3500, 3100)]), None, 0, buildings)[0].text
    assert "near B3" in reports.answer(packet(contacts=[contact(3250, 3250)]), None, ["contacts"], buildings)


def test_occupy_and_cordon_report_once_in_position():
    leg = {"type": "OCCUPY", "pos": [3050, 3050], "grid": "030 030", "completion": 0, "radius": 0, "building": "B2"}
    tracker, trip = Tracker(), {"kind": "route", "legs": [leg]}
    assert tracker.update(packet(order="O-1", placed=0), trip, 0)[0].text == "Copy, occupying B2."
    assert reports.answer(packet(order="O-1", placed=0), trip, ["task"]) == "Moving into B2."
    assert tracker.update(packet(order="O-1", placed=0), trip, 5) == []
    said = tracker.update(packet(order="O-1", placed=1), trip, 8)
    assert [r.text for r in said] == ["In position, occupying B2, at grid 030 030."]
    assert tracker.update(packet(order="O-1", placed=1), trip, 10) == []
    ring = {"kind": "route", "legs": [{**leg, "type": "CORDON", "building": None}]}
    said = Tracker().update(packet(order="O-1", placed=0), ring, 0)
    assert said[0].text == "Copy, setting a cordon around grid 030 030."


def test_cba_tasks_report_arriving_and_then_stay_quiet():
    far = {"type": "SWEEP", "pos": [3650, 3050], "grid": "036 030", "completion": 0, "radius": 120, "building": None}
    tracker, trip = Tracker(), {"kind": "route", "legs": [far]}
    assert tracker.update(packet(order="O-1", leg=2, legs=5), trip, 0)[0].text == "Copy, sweeping around grid 036 030."
    assert reports.answer(packet(order="O-1", leg=3, legs=5), trip, ["task"]) == "Sweeping around grid 036 030."
    assert tracker.update(packet(order="O-1", leg=4, legs=5), trip, 300) == []  # not stuck: this order wanders
    said = tracker.update(packet(order="O-1", leg=4, legs=5, pos=[3550, 3050], grid="035030"), trip, 310)
    assert [r.text for r in said] == ["On the objective, sweeping around grid 036 030, at grid 035 030."]
    assert tracker.update(packet(order="O-1", leg=5, legs=5, pos=[3550, 3050], grid="035030"), trip, 312) == []


def test_unknown_contacts_read_properly():
    west = {"direction": "west", "range": 100, "offset": (-100, 0), "accuracy_m": 0}
    assert reports.contact_phrase({**west, "count": 1, "kinds": {"unknown": 1}}) == \
        "one contact, bearing 270, roughly 100 metres"
    assert reports.contact_phrase({**west, "count": 2, "kinds": {"unknown": 2}}) == \
        "a couple of contacts, bearing 270, roughly 100 metres"


def test_bearings_are_estimates_and_vaguer_targets_get_wider_error(monkeypatch):
    spreads = []
    monkeypatch.setattr(reports, "_wobble", lambda spread: spreads.append(spread) or 0)
    assert reports.spoken_bearing(0, 100) == "bearing 000"
    assert reports.spoken_bearing(100, 0, accuracy_m=10) == "bearing 090"
    assert reports.spoken_bearing(-1, -100, accuracy_m=500) == "bearing 180"
    assert spreads[0] == 5 and 5 < spreads[1] < 11 and spreads[2] == 20
    monkeypatch.setattr(reports, "_wobble", lambda spread: spread)
    assert reports.spoken_bearing(0, 100) == "bearing 005"
    monkeypatch.setattr(reports, "_wobble", lambda spread: -spread)
    assert reports.spoken_bearing(0, 100) == "bearing 355"  # round the top of the compass


def test_real_bearings_stay_within_their_error(monkeypatch):
    monkeypatch.undo()
    said = {reports.spoken_bearing(100, 0) for _ in range(300)}
    assert said <= {"bearing 085", "bearing 090", "bearing 095"} and len(said) == 3


def test_a_bearing_always_comes_with_where_its_measured_from():
    seen = packet(contacts=[contact()])
    assert reports.answer(seen, None, ["contacts"]).startswith("At grid 030 030. One infantry, bearing 045")
    assert reports.answer(packet(), None, ["contacts"]) == "No contacts."
    both = reports.answer(seen, None, ["position", "contacts"])
    assert both.count("030 030") == 1 and both.startswith("Grid 030 030, stationary. One infantry")
    assert reports.answer(seen, None).count("Grid 030 030") == 1


def test_contact_reports_and_answers_put_the_reporter_on_the_map(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.advance(102, contacts=[contact()], pos=[3250, 3050], grid="032030")
    assert b.runtime.positions["Alpha"]["grid"] == "032 030"
    b.advance(150, contacts=[contact()], pos=[3350, 3050], grid="033030")
    assert b.runtime.ask("Alpha", ["contacts"])["replies"][0]["text"].startswith("At grid 033 030.")
    assert b.runtime.positions["Alpha"]["grid"] == "033 030"


def test_posture_doesnt_restart_the_route():
    tracker, trip = Tracker(), route(("MOVE", (3200, 3050), "032 030"), ("MOVE", (3450, 3050), "034 030"))
    tracker.update(packet(order="O-1"), trip, 0)
    tracker.update(packet(order="O-1", leg=1), trip, 2)
    keeping = {**trip, "keeps_progress": "O-2", "acknowledge": "Copy."}
    assert [r.text for r in tracker.update(packet(order="O-2", leg=1), keeping, 4)] == ["Copy."]
    assert tracker.leg == 1


def test_unable_is_reported_by_the_unit():
    said = Tracker().update(packet(order="O-1", unable="water"), route(("MOVE", (1, 1), "000 000")), 0)
    assert [r.text for r in said] == ["Unable, that grid is open water."]


def test_contact_flashes_once_then_goes_quiet_then_is_lost():
    tracker = Tracker()
    said = tracker.update(packet(contacts=[contact()]), None, 0)
    assert said[0].precedence == reports.FLASH
    assert said[0].text == "Contact, one infantry, bearing 045, roughly 300 metres. Engaging, at grid 030 030."
    assert said[0].grid == "030 030"
    assert tracker.update(packet(contacts=[contact()]), None, 2) == []
    two_more = [contact(), contact(3260, 3260), contact(3270, 3270)]
    assert tracker.update(packet(contacts=two_more), None, 30) == []  # within the repeat limit
    assert "a few" in tracker.update(packet(contacts=two_more), None, 95)[0].text
    assert tracker.update(packet(contacts=[contact(age=60)]), None, 100) == []
    assert [r.text for r in tracker.update(packet(contacts=[contact(age=200)]), None, 220)] == ["Lost contact."]


def test_holding_fire_is_said_when_the_group_cant_engage():
    said = Tracker().update(packet(contacts=[contact()], combat_mode="BLUE"), None, 0)
    assert "Holding fire, at grid 030 030." in said[0].text


def test_casualties_group_then_leader_and_ammo_report():
    tracker = Tracker()
    tracker.update(packet(), None, 0)
    assert tracker.update(packet(alive=3), None, 2) == []
    assert tracker.update(packet(alive=2), None, 20) == []
    said = tracker.update(packet(alive=2, wounded=1), None, 33)
    assert [r.text for r in said] == ["Taking casualties, 2 of 4 effective, 1 wounded."]
    assert [r.text for r in tracker.update(packet(alive=2, leader="Ana Cole"), None, 40)] == [
        "Leader down, Ana Cole has command."]
    assert [r.text for r in tracker.update(packet(alive=2, leader="Ana Cole", rounds=150), None, 42)] == [
        "Ammo amber, about half."]
    assert tracker.update(packet(alive=2, leader="Ana Cole", rounds=300), None, 44) == []  # only when worsening


def test_stuck_group_says_so_and_repeats_slowly():
    tracker, trip = Tracker(), route(("MOVE", (3450, 3050), "034 030"))
    tracker.update(packet(order="O-1"), trip, 0)
    assert tracker.update(packet(order="O-1"), trip, 100) == []
    said = tracker.update(packet(order="O-1"), trip, 121)
    assert said[0].text == "Not making progress toward grid 034 030, at grid 030 030."
    assert tracker.update(packet(order="O-1"), trip, 200) == []
    assert tracker.update(packet(order="O-1"), trip, 302)
    assert tracker.update(packet(order="O-1", pos=[3100, 3050]), trip, 304) == []


# -- waking -----------------------------------------------------------------------------------------


def asleep(**over) -> WakeLogic:
    return WakeLogic(**over)


def test_debounce_waits_for_quiet_and_each_message_resets_it():
    wake = asleep()
    wake.message(100)
    assert wake.poll(102) is None
    wake.message(102)
    assert wake.poll(104.5) is None
    got = wake.poll(105)
    assert got.messages == 2 and got.reason() == "2 messages"
    assert wake.poll(106) is None


def test_debounce_ceiling_stops_constant_traffic_locking_it_out():
    wake = asleep()
    for t in range(100, 115, 2):
        wake.message(t)
        assert wake.poll(t) is None
    wake.message(115)
    assert wake.poll(115).messages == 9


def test_timer_fires_alone_and_joins_a_debounce():
    wake = asleep()
    wake.add_timer("W1", 50, "check")
    assert wake.poll(49) is None
    assert [t["id"] for t in wake.poll(50).timers] == ["W1"]
    wake.end_turn(True)
    wake.add_timer("W2", 60, "check")
    wake.message(59)
    assert wake.poll(60) is None
    got = wake.poll(62)
    assert got.messages == 1 and [t["id"] for t in got.timers] == ["W2"]


def test_hold_keeps_messages_until_the_turn_ends_then_wakes_at_once():
    wake = asleep(mode=HOLD)
    wake.turn_started(100)
    wake.message(101)
    wake.add_timer("W1", 102, "check")
    wake.tool_used(103)
    assert wake.poll(110) is None
    wake.end_turn()
    got = wake.poll(110)
    assert got.messages == 1 and len(got.timers) == 1 and not got.fallback


def test_hold_treats_a_silent_turn_as_over():
    wake = asleep(mode=HOLD, idle_s=20)
    wake.turn_started(100)
    wake.message(101)
    wake.tool_used(105)
    assert wake.poll(124) is None
    got = wake.poll(125)
    assert got.messages == 1 and got.fallback


def test_deliver_pushes_during_a_turn_using_the_same_debounce():
    wake = asleep(mode=DELIVER)
    wake.turn_started(100)
    wake.message(101)
    assert wake.poll(102) is None
    assert wake.poll(104).messages == 1
    assert wake.in_turn


def test_deliver_mode_keeps_a_record_of_the_interrupted_turn(tmp_path):
    b = Battle(tmp_path, mode=DELIVER)
    b.start()
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOVE", "at": "B"}]})
    b.advance(101, order="O-0001")
    b.silent(105)
    assert len(b.wakes) == 1
    b.runtime.end_turn("done", messages_only=True)
    turns = b.records.read("turns")
    assert [t["turn"] for t in turns] == [1, 2] and turns[0]["note"].startswith("interrupted")


def test_ending_a_turn_with_no_follow_up_needs_an_explicit_choice():
    wake = asleep()
    assert not wake.can_end_turn(False) and wake.can_end_turn(True)
    wake.add_timer("W1", 50, "check")
    assert wake.can_end_turn(False)
    assert wake.cancel_timer("W1") and not wake.cancel_timer("W1")


def test_notices_cut_through_a_debounce():
    wake = asleep()
    wake.message(100)
    wake.notice("mission end")
    got = wake.poll(100)
    assert got.notices == ["mission end"] and got.messages == 1 and wake.pending == 0


# -- orders -----------------------------------------------------------------------------------------

STATIONS = {"Alpha": {"callsign": "Alpha", "role": "infantry",
                      "capabilities": ["MOVE", "HOLD", "HALT", "POSTURE", "PATROL"]}}
MARKERS = {"B": {"id": "B", "at": "034 030"}}


def order(**over) -> dict:
    request = {"to": "Alpha", "legs": [{"type": "MOVE", "at": "034 030"}], **over}
    return orders.validate(request, STATIONS, MARKERS, 8192)


def test_grids_times_and_markers():
    assert orders.parse_grid("034 030", 8192) == ([3450.0, 3050.0], "034 030")
    assert orders.parse_grid("034030", 8192)[1] == "034 030"
    assert orders.parse_time("2:30") == 150 and orders.parse_time("T+15:45") == 945
    assert orders.format_time(945) == "T+15:45"
    built = orders.validate({"to": "Alpha", "legs": [{"type": "HOLD", "at": "B"}]}, STATIONS, MARKERS, 8192)
    assert built["engine_legs"][0][:2] == ["HOLD", [3450.0, 3050.0]]
    for bad in ("3,4", "99", "12 34"):
        with pytest.raises(Invalid):
            orders.parse_grid(bad, 8192)
    with pytest.raises(Invalid, match="outside"):
        orders.parse_grid("090 030", 8192)


@pytest.mark.parametrize("request_, message", [
    ({"to": "Bravo"}, "Unknown callsign"),
    ({"legs": []}, "at least one leg"),
    ({"legs": [{"type": "DESTROY", "at": "034 030"}]}, "Bad order type"),
    ({"legs": [{"type": "SEARCH", "at": "034 030"}]}, "can't do SEARCH"),
    ({"speed": "WARP"}, "Bad speed"),
    ({"mode": "maybe"}, "Bad mode"),
    ({"legs": [{"type": "HALT"}, {"type": "MOVE", "at": "034 030"}]}, "only leg"),
    ({"legs": [{"type": "POSTURE"}]}, "at least one setting"),
])
def test_orders_rejected_only_for_what_the_roster_and_map_show(request_, message):
    with pytest.raises(Invalid, match=message):
        order(**request_)


ALL_TYPES = ["MOVE", "CLEAR", "OCCUPY", "CORDON", "ATTACK", "DEFEND", "PATROL_AREA", "SWEEP"]
BUILDINGS = [{"id": "B1", "pos": [3460.0, 3060.0], "at": "034 030", "name": "House", "positions": 8},
             {"id": "B2", "pos": [3500.0, 3060.0], "at": "035 030", "name": "Shop", "positions": 4},
             {"id": "B3", "pos": [3900.0, 3900.0], "at": "039 039", "name": "House", "positions": 6}]


def wide(**over) -> dict:
    stations = {"Alpha": {**STATIONS["Alpha"], "capabilities": ALL_TYPES}}
    return orders.validate({"to": "Alpha", **over}, stations, MARKERS, 8192, BUILDINGS)


def test_holding_without_a_grid_means_where_the_last_leg_ended():
    route = wide_hold(legs=[{"type": "MOVE", "at": "034 030"}, {"type": "HOLD"}])["route"]["legs"]
    assert route[1]["type"] == "HOLD" and route[1]["grid"] == "034 030" and route[1]["pos"] == route[0]["pos"]


def test_a_leg_with_no_place_says_what_it_needs():
    with pytest.raises(Invalid, match="needs at: a grid, marker or building id"):
        wide_hold(legs=[{"type": "HOLD"}])
    with pytest.raises(Invalid, match="needs at: a grid, marker or building id"):
        wide_hold(legs=[{"type": "MOVE"}])


def wide_hold(**over) -> dict:
    stations = {"Alpha": {**STATIONS["Alpha"], "capabilities": [*ALL_TYPES, "HOLD"]}}
    return orders.validate({"to": "Alpha", **over}, stations, MARKERS, 8192, BUILDINGS)


def test_clear_works_from_numbered_buildings():
    assert wide(legs=[{"type": "CLEAR", "at": "B1"}])["route"]["legs"][0]["ids"] == ["B1"]
    assert wide(legs=[{"type": "CLEAR", "at": ["B3", "B1"]}])["route"]["legs"][0]["ids"] == ["B3", "B1"]
    near = wide(legs=[{"type": "CLEAR", "at": "034 030", "radius": 100}])
    assert near["route"]["legs"][0]["ids"] == ["B1", "B2"]  # nearest first, and B3 is out of range
    assert near["engine_legs"][0][0] == "CLEAR" and near["engine_legs"][0][1][0] == ["B1", [3460.0, 3060.0]]
    assert wide(legs=[{"type": "CLEAR", "at": "010 010"}])["route"]["legs"][0]["ids"] == []
    with pytest.raises(Invalid, match="aren't"):
        wide(legs=[{"type": "CLEAR", "at": ["B9"]}])
    with pytest.raises(Invalid, match="at most 300"):
        wide(legs=[{"type": "CLEAR", "at": "B", "radius": 900}])
    with pytest.raises(Invalid, match="only leg"):
        wide(legs=[{"type": "CLEAR", "at": "B"}, {"type": "MOVE", "at": "B"}])


def test_buildings_can_be_used_as_places_in_any_order():
    assert wide(legs=[{"type": "MOVE", "at": "B2"}])["engine_legs"][0][1] == [3500.0, 3060.0]
    occupy = wide(legs=[{"type": "OCCUPY", "at": "B2"}])
    assert occupy["engine_legs"][0][0] == "OCCUPY" and occupy["route"]["legs"][0]["building"] == "B2"
    with pytest.raises(Invalid, match="building id"):
        wide(legs=[{"type": "OCCUPY", "at": "034 030"}])
    assert wide(legs=[{"type": "CORDON", "at": "B3"}])["engine_legs"][0][2] == 30
    sweep = wide(legs=[{"type": "SWEEP", "at": "B", "radius": 200}])
    assert sweep["engine_legs"][0][:3] == ["SWEEP", [3450.0, 3050.0], 200]
    assert wide(legs=[{"type": "DEFEND", "at": "B"}])["route"]["legs"][0]["radius"] == 100
    with pytest.raises(Invalid, match="only leg"):
        wide(legs=[{"type": "ATTACK", "at": "B"}, {"type": "MOVE", "at": "B"}])


def test_patrol_adds_a_cycle_waypoint_and_halt_has_no_legs():
    patrol = {"to": "Alpha", "legs": [{"type": "PATROL", "at": ["030 030", "034 030"]}]}
    built = orders.validate(patrol, STATIONS, MARKERS, 8192)
    assert [leg[0] for leg in built["engine_legs"]] == ["MOVE", "MOVE", "CYCLE"]
    halt = orders.validate({"to": "Alpha", "legs": [{"type": "HALT"}]}, STATIONS, MARKERS, 8192)
    assert halt["mode"] == "halt" and halt["engine_legs"] == []


# -- the whole thing, with a fake game ----------------------------------------------------------------


class FakeGame:
    def __init__(self):
        self.queue: list[dict] = []
        self.seq = 0
        self.calls: list[tuple] = []
        self.fail_exec = False

    def emit(self, **event) -> None:
        self.seq += 1
        self.queue.append({"seq": self.seq, "k": "evt", **event})

    def events(self, since: int, wait: float) -> dict:
        if since > self.seq + 1000:  # the runtime asking where the stream ends
            return {"events": [], "next": self.seq + 1}
        events, self.queue = self.queue, []
        return {"events": events, "next": self.seq + 1}

    def exec(self, code: str, args: list) -> dict:
        self.calls.append((code, args))
        if self.fail_exec:
            raise RuntimeError("no such group: Group B Alpha 1-1 (O_Soldier_F at 3050,3050)")
        return {"ok": True}


class Battle:
    def __init__(self, tmp_path: Path, mode=HOLD, **raw):
        self.game = FakeGame()
        self.wakes: list[tuple[str, dict]] = []
        self.wall = 0.0
        base = {"name": "t", "mission": "demo_vr", "text": "Get Alpha to B.", "time_limit": "5:00",
                "stations": [{"callsign": "Alpha", "role": "infantry", "capabilities": ["MOVE", "HOLD", "HALT"],
                              "at": "030 030"}],
                "markers": [{"id": "B", "kind": "objective", "label": "Point B", "at": "034 030"}],
                "success": {"station": "Alpha", "within_m": 50, "of": "034 030"}, "mid_turn_messages": mode, **raw}
        self.scenario = scenario.build(base)
        self.records = Records(tmp_path / "commander-1" / "west")
        self.runtime = self.new_runtime()
        self.t = 100.0

    def new_runtime(self) -> Runtime:
        return Runtime(self.game, self.scenario, self.records, lambda text, meta: self.wakes.append((text, meta)),
                       world_size=8192, clock=lambda: self.wall)

    def advance(self, to: float, **packet_fields) -> None:
        """Move mission time, with the station reporting if fields are given."""
        self.t = to
        self.game.emit(type="cmd_tick", t=to)
        if packet_fields is not None and packet_fields.get("report", True):
            packet_fields.pop("report", None)
            self.game.emit(type="cmd_report", t=to, **packet(**packet_fields))
        self.runtime.step(0)

    def silent(self, to: float) -> None:
        self.t = to
        self.game.emit(type="cmd_tick", t=to)
        self.runtime.step(0)

    def start(self) -> dict:
        self.silent(self.t)
        return self.runtime.mission()


def test_proof_of_concept_flow(tmp_path):
    b = Battle(tmp_path)
    brief = b.start()
    assert brief["mission"] == "Get Alpha to B." and brief["roster"][0]["callsign"] == "Alpha"
    assert b.runtime.order({"to": "Alpha", "legs": [{"type": "MOVE", "at": "B"}]}) == {"order": "O-0001", "sent": True}
    assert b.game.calls[-1][1][:3] == ["Alpha", "O-0001", "replace"]
    b.runtime.schedule({"wake": "Has Alpha arrived?"}, after="1:00")
    assert b.runtime.end_turn("Sent Alpha")["ended"]
    b.advance(102, order="O-0001")
    assert b.wakes == []  # debouncing
    b.silent(105)
    assert len(b.wakes) == 1
    text, meta = b.wakes[0]
    assert meta == {"turn": "2", "woke_on": "1 message"} and "Copy, moving to grid 034 030." in text
    assert 'W1  T+01:00  wake: "Has Alpha arrived?"' in text
    b.runtime.end_turn("Fine")
    b.advance(110, order="O-0001", pos=[3450, 3050], grid="034030", leg=1)
    b.silent(113)
    assert "Arrived, grid 034 030." in b.wakes[1][0] and "Alpha  grid 034 030  reported 3 s ago" in b.wakes[1][0]
    b.runtime.end_turn("Arrived")
    b.silent(160)
    assert 'W1  due T+01:00: "Has Alpha arrived?"' in b.wakes[2][0] and b.wakes[2][1]["woke_on"] == "1 timer"
    b.runtime.end_turn("Nothing to do", messages_only=True)
    b.game.emit(type="cmd_truth", t=165, groups=[{"group": "Alpha", "side": "WEST", "alive": 4, "pos": [3450, 3050]}])
    b.silent(165)
    assert len(b.wakes) == 3  # a report on its way still gets through
    b.silent(176)
    assert "MISSION END. Objective achieved" in b.wakes[3][0]
    assert b.runtime.end_turn("Done") == {"ended": True, "mission_over": True}
    turns = b.records.read("turns")
    assert [t["woke_on"] for t in turns] == ["mission start", "1 message", "1 message", "1 timer", "notice"]
    assert [r["kind"] for r in b.records.read("radio")] == ["order", "report", "report"]
    assert len(b.records.read_truth()) == 1


def test_arrival_report_isnt_lost_when_true_position_gets_there_first(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOVE", "at": "B"}]})
    b.runtime.end_turn("Sent", messages_only=True)
    b.advance(102, order="O-0001")
    b.game.emit(type="cmd_truth", t=104, groups=[{"group": "Alpha", "side": "WEST", "alive": 4, "pos": [3447, 3050]}])
    b.silent(104)
    b.advance(108, order="O-0001", pos=[3450, 3050], grid="034030", leg=1)
    b.silent(120)
    delivered = "\n".join(text for text, _ in b.wakes)
    assert "Arrived, grid 034 030." in delivered and "MISSION END. Objective achieved" in delivered


def test_lost_group_is_only_caught_by_the_commanders_own_timer(tmp_path):
    b = Battle(tmp_path, events=[{"at": "0:30", "action": "delete_station", "station": "Alpha"}])
    b.start()
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOVE", "at": "B"}]})
    b.runtime.schedule({"wake": "Has Alpha arrived?"}, after="1:00")
    b.runtime.end_turn("Sent")
    b.advance(102, order="O-0001")
    b.silent(105)
    b.runtime.end_turn("ok")
    assert len(b.wakes) == 1
    b.silent(131)
    assert b.game.calls[-1][1] == ["Alpha"]
    b.silent(150)
    assert len(b.wakes) == 1  # silence wakes nobody
    b.silent(160)
    assert len(b.wakes) == 2 and "Has Alpha arrived?" in b.wakes[1][0] and "Arrived" not in b.wakes[1][0]
    assert b.runtime.ask("Alpha") == {"replies": [{"from": "Alpha", "text": "No answer."}]}


def test_review_shows_a_group_dying_though_the_commander_never_hears(tmp_path):
    from arma_harness.commander import operator
    from arma_harness.config import Home

    b = Battle(tmp_path, events=[{"at": "0:10", "action": "kill_station", "station": "Alpha"}])
    b.start()
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOVE", "at": "B"}]})
    alive = {"group": "Alpha", "side": "WEST", "alive": 4, "pos": [3060, 3050]}
    gone = {"group": "Alpha", "side": "WEST", "alive": 0, "pos": []}
    for t, group in ((102, alive), (112, gone), (117, gone)):
        b.game.emit(type="cmd_truth", t=t, groups=[group])
        b.silent(t)
    current = operator._current_file(Home(tmp_path))
    current.write_text(json.dumps({"folder": str(b.records.folder)}), encoding="utf-8")
    review = operator.aar(Home(tmp_path))
    assert "EVENT  kill_station Alpha" in review and review.count("Alpha 0 alive") == 1
    assert "0 alive" not in json.dumps(b.records.read("radio"))


def test_killed_group_says_nothing_about_it(tmp_path):
    b = Battle(tmp_path, events=[{"at": "0:10", "action": "kill_station", "station": "Alpha"}])
    b.start()
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOVE", "at": "B"}]})
    b.runtime.end_turn("Sent", messages_only=True)
    b.advance(102, order="O-0001")
    b.silent(111)
    assert b.game.calls[-1] == ("_this call brmh_cmd_fnc_killStation", ["Alpha"])
    b.silent(200)
    assert len(b.wakes) == 1 and "Copy" in b.wakes[0][0]
    assert b.runtime.ask("Alpha")["replies"][0]["text"] == "No answer."
    with pytest.raises(ValueError, match="bad scenario event"):
        scenario.build({"name": "t", "mission": "m", "text": "t", "time_limit": "1:00",
                        "stations": [{"callsign": "A", "role": "r", "capabilities": [], "at": "000 000"}],
                        "events": [{"at": "0:10", "action": "explode", "station": "A"}]})


def test_time_limit_ends_the_mission_and_wakes_the_commander(tmp_path):
    b = Battle(tmp_path, time_limit="0:10")
    b.start()
    b.runtime.end_turn("wait", messages_only=True)
    b.silent(111)
    assert "MISSION END. Time limit reached." in b.wakes[0][0]


def test_end_turn_refused_with_nothing_scheduled(tmp_path):
    b = Battle(tmp_path)
    b.start()
    result = b.runtime.end_turn("done")
    assert result["ended"] is False and "No wake is scheduled" in result["error"]
    assert b.runtime.end_turn("done", messages_only=True)["ended"]


# -- markers ----------------------------------------------------------------------------------------


def test_markers_show_with_age_and_can_be_updated_and_retired(tmp_path):
    b = Battle(tmp_path)
    b.start()
    made = b.runtime.mark({"id": "E1", "kind": "enemy", "at": "056045", "label": "Infantry", "confidence": "medium",
                           "sources": ["R-0001"], "expires": "T+00:20"})
    assert made["id"] == "E1" and made["time_now"] == "T+00:00"
    b.silent(110)
    text = b.runtime.brief()["briefing"]
    assert "E1  enemy Infantry  grid 056 045  medium  10 s old" in text and "B  objective Point B  grid 034 030" in text
    b.silent(125)
    assert "STALE" in b.runtime.brief()["briefing"]
    b.runtime.mark({"id": "E1", "at": "057 045", "confidence": "HIGH", "expires": "T+10:00"})
    text = b.runtime.brief()["briefing"]
    assert "E1  enemy Infantry  grid 057 045  high  0 s old" in text and "STALE" not in text
    assert b.runtime.mark({"at": "040 040"})["id"] == "M1"
    assert b.runtime.mark({"kind": "phase_line", "at": ["040 040", "050 040"], "id": "Rose"})["id"] == "Rose"
    assert "Rose  phase_line  grids 040 040; 050 040" in b.runtime.brief()["briefing"]
    assert b.runtime.unmark("E1") == {"retired": "E1"} and "E1" not in b.runtime.brief()["briefing"]
    history = b.records.read("markers")
    assert [h["at"] for h in history if h["id"] == "E1" and "at" in h] == ["056 045", "057 045"]
    assert history[-1] == {"id": "E1", "t": 25.0, "retired": True}


@pytest.mark.parametrize("args, message", [
    ({"id": "E1"}, "needs at"),
    ({"id": "bad id!", "at": "040 040"}, "marker id"),
    ({"at": "99"}, "Bad grid"),
    ({"at": ["040 040"]}, "at least 2"),
    ({"at": "040 040", "kind": "tank"}, "Bad kind"),
    ({"at": "040 040", "confidence": "sure"}, "Bad confidence"),
])
def test_bad_markers_are_refused(tmp_path, args, message):
    b = Battle(tmp_path)
    b.start()
    with pytest.raises(Invalid, match=message):
        b.runtime.mark(args)


def test_orders_can_aim_at_the_commanders_own_markers(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.runtime.mark({"id": "Farm", "at": "036 030"})
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOVE", "at": "Farm"}]})
    assert b.game.calls[-1][1][3][0][1] == [3650.0, 3050.0]
    b.runtime.mark({"id": "Rose", "kind": "phase_line", "at": ["040 040", "050 040"]})
    with pytest.raises(Invalid, match="line or area"):
        b.runtime.order({"to": "Alpha", "legs": [{"type": "MOVE", "at": "Rose"}]})


# -- schedules --------------------------------------------------------------------------------------


def test_timed_order_goes_out_on_time_without_a_wake_even_during_a_turn(tmp_path):
    b = Battle(tmp_path)
    b.start()
    move = {"to": "Alpha", "legs": [{"type": "MOVE", "at": "B"}]}
    made = b.runtime.schedule({"order": move}, at="T+00:30")
    assert made["id"] == "S1" and made["first"] == "T+00:30"
    assert "S1  T+00:30  Alpha: MOVE B" in b.runtime.brief()["briefing"]
    calls = len(b.game.calls)
    b.silent(129)
    assert len(b.game.calls) == calls
    b.wall = 0
    b.silent(130)  # the turn is still open
    assert b.game.calls[-1][1][0:2] == ["Alpha", "O-0001"] and b.wakes == []
    assert "S1" not in b.runtime.schedules
    assert "(timed, S1)" in b.records.read("radio")[-1]["text"]
    assert b.records.read("orders")[-1]["via"] == "S1"


def test_coordinated_attack_fires_together(tmp_path):
    b = Battle(tmp_path, stations=[{"callsign": c, "role": "infantry", "capabilities": ["MOVE"], "at": "030 030"}
                                   for c in ("Alpha", "Bravo", "Charlie")], success={})
    b.start()
    for callsign in ("Alpha", "Bravo", "Charlie"):
        b.runtime.schedule({"order": {"to": callsign, "legs": [{"type": "MOVE", "at": "B"}]}}, at="T+01:00")
    b.silent(160)
    assert [call[1][0] for call in b.game.calls] == ["Alpha", "Bravo", "Charlie"]


def test_timed_question_reply_wakes_and_silence_shows_as_overdue(tmp_path):
    b = Battle(tmp_path)
    b.start()
    made = b.runtime.schedule({"ask": {"to": "Alpha", "topics": ["position"]}}, every="1:00")
    assert made["first"] == "T+01:00"
    b.runtime.schedule({"wake": "check"}, at="T+04:30")
    b.runtime.end_turn("x")
    b.advance(160, order="")
    b.silent(164)
    assert "Grid 030 030, stationary." in b.wakes[0][0] and "Alpha  grid 030 030" in b.wakes[0][0]
    b.runtime.end_turn("fine")
    b.silent(220)  # no packets for a minute: Alpha can't answer
    b.silent(280)
    assert len(b.wakes) == 1  # silence wakes nobody
    b.silent(370)
    assert "OVERDUE\nAlpha: missed 3 scheduled check-ins." in b.wakes[1][0]
    b.runtime.end_turn("hm", messages_only=True)
    b.advance(400, order="")
    b.runtime.ask("Alpha", ["ammo"])
    assert "OVERDUE" not in b.runtime.brief()["briefing"]


def test_check_in_with_nothing_new_doesnt_wake_the_commander(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.runtime.schedule({"ask": {"to": "Alpha", "topics": ["position", "contacts"]}}, every="0:30")
    b.runtime.end_turn("x", messages_only=True)
    b.advance(130, order="")
    b.silent(134)
    assert len(b.wakes) == 1  # the first answer is news
    b.runtime.end_turn("x", messages_only=True)
    b.advance(160, order="")
    b.silent(164)
    b.advance(190, order="")
    b.silent(194)
    assert len(b.wakes) == 1  # the same words again aren't
    assert b.records.read("radio")[-1]["kind"] == "checkin_unchanged"
    assert b.runtime.last_heard["Alpha"] == 190
    b.advance(220, order="", contacts=[contact()])
    b.silent(224)
    assert len(b.wakes) == 2 and "Contact" in b.wakes[1][0]


def test_repeating_wake_comes_back_until_its_count_runs_out(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.runtime.schedule({"wake": "look around"}, every="0:30", count=2)
    b.runtime.end_turn("x")
    b.silent(130)
    assert "look around" in b.wakes[0][0] and "W1  T+01:00, every 0:30" in b.wakes[0][0]
    b.runtime.end_turn("x")
    b.silent(160)
    assert len(b.wakes) == 2 and "W1" not in b.runtime.schedules and not b.runtime.wake.timers


def test_schedules_are_cancelled_and_validated_up_front(tmp_path):
    b = Battle(tmp_path)
    b.start()
    with pytest.raises(Invalid, match="Unknown callsign"):
        b.runtime.schedule({"order": {"to": "Zulu", "legs": [{"type": "MOVE", "at": "B"}]}}, after="1:00")
    with pytest.raises(Invalid, match="Unknown topics"):
        b.runtime.schedule({"ask": {"to": "Alpha", "topics": ["vibes"]}}, after="1:00")
    with pytest.raises(Invalid, match="at most every"):
        b.runtime.schedule({"wake": "x"}, every="0:05")
    with pytest.raises(Invalid, match="do needs one of"):
        b.runtime.schedule({"dance": True}, after="1:00")
    with pytest.raises(Invalid, match="Give after or at"):
        b.runtime.schedule({"wake": "x"}, after="1:00", at="T+02:00")
    made = b.runtime.schedule({"order": {"to": "Alpha", "legs": [{"type": "MOVE", "at": "B"}]}}, after="1:00")
    assert b.runtime.unschedule(made["id"]) == {"cancelled": True}
    b.silent(200)
    assert b.game.calls == []
    wake = b.runtime.schedule({"wake": "x"}, after="1:00")
    assert b.runtime.unschedule(wake["id"]) == {"cancelled": True} and not b.runtime.wake.timers


def test_timed_order_whose_marker_was_retired_only_troubles_the_operator(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.runtime.mark({"id": "Farm", "at": "036 030"})
    b.runtime.schedule({"order": {"to": "Alpha", "legs": [{"type": "MOVE", "at": "Farm"}]}}, after="0:10")
    b.runtime.unmark("Farm")
    b.silent(115)
    assert b.game.calls == [] and "couldn't fire" in (b.records.folder / "operator.log").read_text(encoding="utf-8")


# -- enemies and how battles end ----------------------------------------------------------------------


def village(tmp_path, **over) -> Battle:
    return Battle(tmp_path, enemies=[{"id": "East 1", "at": "041 041", "units": 4, "mode": "garrison"},
                                     {"id": "East 2", "at": "041 039", "units": 2, "mode": "patrol"}],
                  success={"enemy_cleared": True}, failure={"all_stations_lost": True}, **over)


def groups(alpha=4, east1=4, east2=2) -> list[dict]:
    return [{"group": "Alpha", "side": "WEST", "alive": alpha, "pos": [3050, 3050] if alpha else []},
            {"group": "East 1", "side": "EAST", "alive": east1, "pos": [4100, 4100] if east1 else []},
            {"group": "East 2", "side": "EAST", "alive": east2, "pos": [4100, 3900] if east2 else []}]


def test_clearing_the_enemy_wins_and_the_commander_only_hears_at_the_end(tmp_path):
    b = village(tmp_path)
    b.start()
    b.runtime.end_turn("x", messages_only=True)
    b.game.emit(type="cmd_truth", t=102, groups=groups(east1=0))
    b.silent(102)
    assert b.wakes == [] and not b.runtime.ended
    b.game.emit(type="cmd_truth", t=107, groups=groups(east1=0, east2=0))
    b.silent(107)
    assert b.wakes == []
    b.silent(118)
    assert "MISSION END. Objective achieved: the enemy has been cleared." in b.wakes[0][0]


def test_losing_every_station_ends_it_at_once(tmp_path):
    b = village(tmp_path)
    b.start()
    b.runtime.schedule({"wake": "check"}, after="9:00")
    b.runtime.end_turn("x")
    b.game.emit(type="cmd_truth", t=102, groups=groups(alpha=0))
    b.silent(102)
    assert "MISSION END. All stations have been lost." in b.wakes[0][0] and "check" not in b.wakes[0][0]
    assert not b.runtime.schedules


def test_enemies_stay_out_of_everything_the_commander_sees(tmp_path):
    b = village(tmp_path)
    brief = b.start()
    b.game.emit(type="cmd_truth", t=102, groups=groups())
    b.silent(102)
    seen = json.dumps(brief) + b.runtime.brief()["briefing"] + json.dumps(b.runtime.roster())
    assert "East 1" not in seen and "East 2" not in seen and "garrison" not in seen


def with_buildings(tmp_path) -> Battle:
    station = {"callsign": "Alpha", "role": "infantry", "capabilities": ALL_TYPES, "at": "030 030"}
    b = Battle(tmp_path, stations=[station], ao={"at": "034 030", "radius": 400})
    b.runtime.buildings = BUILDINGS
    return b


def test_a_marker_can_be_pinned_to_a_building(tmp_path):
    b = with_buildings(tmp_path)
    b.start()
    b.runtime.mark({"id": "E1", "kind": "enemy", "at": "B3", "label": "Sniper", "confidence": "high"})
    marker = b.runtime.markers["E1"]
    assert marker["building"] == "B3" and marker["at"] == "039 039" and marker["pos"] == [3900.0, 3900.0]
    assert "E1  enemy Sniper  in B3, grid 039 039  high" in b.runtime.briefing()
    assert b.records.read("markers")[-1]["building"] == "B3"  # the review needs it too


def test_orders_naming_a_pinned_marker_mean_that_building(tmp_path):
    b = with_buildings(tmp_path)
    b.start()
    b.runtime.mark({"id": "E1", "kind": "enemy", "at": "B1"})
    b.runtime.mark({"id": "N1", "at": "034 030"})  # same square, not pinned
    known = b.runtime.buildings

    def order(at, kind="CLEAR"):
        return orders.validate({"to": "Alpha", "legs": [{"type": kind, "at": at}]}, b.scenario.stations,
                               b.runtime.markers, 8192, known)["route"]["legs"][0]

    assert order("E1")["ids"] == ["B1"]
    assert order(["E1", "B2"])["ids"] == ["B1", "B2"]
    assert order("N1")["ids"] == ["B1", "B2"]  # a plain marker still clears around itself
    assert order("E1", "OCCUPY")["building"] == "B1"
    assert order("E1", "CORDON")["building"] == "B1"
    assert order("E1", "MOVE")["pos"] == [3460.0, 3060.0]  # the building's place, not the middle of its grid square
    with pytest.raises(Invalid, match="OCCUPY needs a building"):
        order("N1", "OCCUPY")


def test_updating_a_pinned_marker_keeps_the_pin_until_it_moves(tmp_path):
    b = with_buildings(tmp_path)
    b.start()
    b.runtime.mark({"id": "E1", "kind": "enemy", "at": "B3"})
    b.runtime.mark({"id": "E1", "confidence": "low"})
    assert b.runtime.markers["E1"]["building"] == "B3" and b.runtime.markers["E1"]["kind"] == "enemy"
    b.runtime.mark({"id": "E1", "at": "040 040"})
    assert "building" not in b.runtime.markers["E1"] and "pos" not in b.runtime.markers["E1"]
    assert b.runtime.markers["E1"]["at"] == "040 040"


def test_marking_a_building_that_doesnt_exist_says_so(tmp_path):
    b = with_buildings(tmp_path)
    b.start()
    with pytest.raises(Invalid, match="no building B9"):
        b.runtime.mark({"at": "B9"})
    with pytest.raises(Invalid, match="no building B9"):
        b.runtime.mark({"at": ["B1", "B9"]})


def test_a_line_can_run_between_buildings(tmp_path):
    b = with_buildings(tmp_path)
    b.start()
    b.runtime.mark({"id": "L1", "kind": "phase_line", "at": ["B1", "039 039"]})
    assert b.runtime.markers["L1"]["at"] == ["034 030", "039 039"] and "building" not in b.runtime.markers["L1"]


def test_the_map_draws_a_pinned_marker_on_its_building(tmp_path):
    b = with_buildings(tmp_path)
    b.scenario.spectator = True
    b.start()
    b.runtime.mark({"id": "E1", "kind": "enemy", "at": "B1", "label": "Sniper"})
    assert b.runtime.map_image(center="E1", radius=100)["png"].startswith(b"\x89PNG")
    mirrored = [args for code, args in b.game.calls if args and args[0] == "E1"]
    assert mirrored[-1][2] == [[3460.0, 3060.0]]  # the in-game map shows it on the building too


def test_buildings_appear_in_the_brief_and_checked_ones_are_remembered(tmp_path):
    b = with_buildings(tmp_path)
    brief = b.start()
    assert brief["buildings"][0] == {"id": "B1", "type": "House", "grid": "034 030", "positions": 8}
    b.runtime.order({"to": "Alpha", "legs": [{"type": "CLEAR", "at": ["B1", "B2"]}]})
    assert b.game.calls[-1][1][3][0][1] == [["B1", [3460.0, 3060.0]], ["B2", [3500.0, 3060.0]]]
    b.runtime.end_turn("x", messages_only=True)
    b.advance(102, order="O-0001", clearing=10, cleared=["B1"])
    b.silent(106)
    assert "B1 checked, nothing seen." in b.wakes[0][0] and "BUILDINGS CHECKED\nB1 4 s" in b.wakes[0][0]
    with pytest.raises(Invalid, match="building's id"):
        b.runtime.mark({"id": "B1", "at": "040 040"})


def test_map_image_shows_only_what_the_commander_has(tmp_path):
    from io import BytesIO

    from PIL import Image

    b = with_buildings(tmp_path)
    b.start()
    b.runtime.mark({"id": "E1", "kind": "enemy", "at": "036 031", "label": "Infantry", "confidence": "low"})
    made = b.runtime.map_image()
    image = Image.open(BytesIO(made["png"]))
    assert image.size == (1000, 1000) and "not live" in made["text"]
    assert Image.open(BytesIO(b.runtime.map_image(center="B3", radius=100)["png"])).size == (1000, 1000)
    with pytest.raises(Invalid, match="radius"):
        b.runtime.map_image(radius=5)
    # Facts about the real battle change nothing in the picture.
    before = b.runtime.map_image()["png"]
    b.game.emit(type="cmd_truth", t=100, groups=[{"group": "East 1", "side": "EAST", "alive": 9, "pos": [3400, 3000]}])
    b.runtime.step(0)
    assert b.runtime.map_image()["png"] == before


def test_bad_enemy_mode_is_refused():
    with pytest.raises(ValueError, match="mode must be"):
        scenario.build({"name": "t", "mission": "m", "text": "t", "time_limit": "1:00",
                        "stations": [{"callsign": "A", "role": "r", "capabilities": [], "at": "000 000"}],
                        "enemies": [{"id": "E", "at": "000 000", "mode": "dance"}]})


# -- the human observer -------------------------------------------------------------------------------


def test_observer_sees_radio_and_markers_only_when_the_scenario_has_one(tmp_path):
    b = village(tmp_path / "a", spectator=True)
    b.start()
    b.advance(101, order="")
    b.runtime.ask("Alpha", ["ammo"])
    b.runtime.mark({"id": "E1", "kind": "enemy", "at": "041 041", "label": "Infantry", "confidence": "low"})
    b.runtime.unmark("E1")
    calls = b.game.calls
    shown = [args[0] for code, args in calls if "fnc_show" in code]
    assert "The battle has started." in shown and "Alpha: Ammo green, good." in shown
    mirrors = [args for code, args in calls if "fnc_mirror" in code]
    assert mirrors[-2][:2] == ["E1", "enemy"] and mirrors[-2][2] == [[4150.0, 4150.0]] and mirrors[-1][-1] is True
    quiet = village(tmp_path / "b")
    quiet.start()
    quiet.runtime.mark({"id": "E1", "at": "041 041"})
    assert quiet.game.calls == []


# -- the lockdown check ---------------------------------------------------------------------------------


def transcript(*loaded, deferred=()) -> list[dict]:
    return [{"type": "api-request-shape", "shape": {"tools": [{"name": name} for name in loaded]}},
            {"type": "attachment", "attachment": {"type": "deferred_tools_delta", "addedNames": list(deferred)}}]


def commander_tools() -> list[str]:
    return [f"mcp__commander__{name}" for name in TOOL_NAMES]


def test_lockdown_passes_with_exactly_the_allowed_tools():
    from arma_harness.commander.operator import judge_lockdown, tools_received

    verdict = judge_lockdown(tools_received(transcript("ToolSearch", "advisor", deferred=commander_tools())))
    assert verdict["ok"] and verdict["unexpected"] == [] and verdict["commander_tools"] == len(TOOL_NAMES)


@pytest.mark.parametrize("extra", ["Read", "Bash", "SendMessage", "mcp__arma__arma_exec", "mcp__new_connector__x"])
def test_lockdown_fails_on_anything_extra_loaded_or_deferred(extra):
    from arma_harness.commander.operator import judge_lockdown, tools_received

    for rows in (transcript("ToolSearch", extra, deferred=commander_tools()),
                 transcript("ToolSearch", deferred=[*commander_tools(), extra])):
        verdict = judge_lockdown(tools_received(rows))
        assert not verdict["ok"] and verdict["unexpected"] == [extra]


def test_lockdown_fails_if_it_cant_read_the_transcript_or_tools_are_missing():
    from arma_harness.commander.operator import judge_lockdown, tools_received

    assert not judge_lockdown(tools_received([{"type": "user"}]))["ok"]
    verdict = judge_lockdown(tools_received(transcript("ToolSearch", deferred=commander_tools()[1:])))
    assert not verdict["ok"] and len(verdict["missing"]) == 1


# -- the fog ----------------------------------------------------------------------------------------


def test_orders_to_live_and_dead_groups_look_identical(tmp_path):
    live, dead = Battle(tmp_path / "a"), Battle(tmp_path / "b")
    live.start()
    dead.start()
    live.advance(101, order="")
    dead.game.fail_exec = True  # the worst case: the engine errors with details about the group
    request = {"to": "Alpha", "legs": [{"type": "MOVE", "at": "B"}]}
    assert live.runtime.order(request) == dead.runtime.order(request) == {"order": "O-0001", "sent": True}
    assert "O_Soldier_F" in (dead.records.folder / "operator.log").read_text(encoding="utf-8")
    assert "O_Soldier_F" not in json.dumps(dead.records.read("radio"))


def test_unperceived_facts_change_nothing_the_commander_sees(tmp_path):
    """The leak test: the true battle differs, the group's perception doesn't, so the text must be byte-identical."""
    outputs = []
    for folder, truth, killed in (("a", [3100, 3100], "Bob"), ("b", [6000, 6000], "Eve")):
        b = Battle(tmp_path / folder)
        b.start()
        b.runtime.schedule({"wake": "check"}, after="0:30")
        b.runtime.end_turn("x")
        b.game.emit(type="cmd_truth", t=102, groups=[{"group": "East 1", "side": "EAST", "alive": 9, "pos": truth}])
        b.game.emit(type="killed", t=102, victim=killed, victimType="O_Soldier_F", killer="X", weapon="arifle_MX_F")
        b.game.queue.append({"seq": 99, "k": "err", "text": f"error in {killed}"})
        b.advance(102, contacts=[contact()])
        b.silent(106)
        outputs.append((b.wakes, b.runtime.ask("Alpha", ["contacts"]), b.runtime.log()))
    assert outputs[0] == outputs[1]


def test_nothing_engine_shaped_reaches_the_commander(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.runtime.schedule({"wake": "check"}, after="0:30")
    b.runtime.end_turn("x")
    fields = dict(contacts=[contact()], order="", leader="Sam Reed")
    b.game.emit(type="cmd_report", t=102, secret_class="O_Soldier_F", netId="2:113", **packet(**fields))
    b.silent(102)
    b.silent(106)
    seen = b.wakes[0][0] + json.dumps(b.runtime.ask("Alpha")) + json.dumps(b.runtime.roster())
    for banned in ("O_Soldier_F", "2:113", "3250", "3050", "AWARE", "YELLOW", "cmd_report"):
        assert banned not in seen, banned


def test_game_outage_is_a_plain_fault_notice(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.runtime.end_turn("x", messages_only=True)

    def boom(since, wait):
        raise OSError("bridge unreachable on port 38715")

    b.game.events = boom
    b.wall = 0
    b.runtime.step(0)
    b.wall = 16
    b.runtime.step(0)
    assert "System fault" in b.wakes[0][0] and "38715" not in b.wakes[0][0]


def test_mission_restart_clears_the_net_and_says_so(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.runtime.schedule({"wake": "check"}, after="1:00")
    b.runtime.end_turn("x")
    b.game.queue.append({"seq": 5, "k": "mission", "state": "start"})
    b.silent(103)
    assert "The mission has restarted" in b.wakes[0][0] and "check" not in b.wakes[0][0]


def test_state_survives_a_server_restart(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOVE", "at": "B"}]})
    b.runtime.schedule({"wake": "Has Alpha arrived?"}, after="0:20")
    b.runtime.notes("Plan: wait for Alpha.")
    b.runtime.end_turn("Sent")
    b.advance(101, order="O-0001")
    b.runtime = b.new_runtime()
    b.silent(101.5)
    assert b.runtime.turn == 1 and b.runtime.routes["Alpha"]["legs"][0]["grid"] == "034 030"
    b.advance(103, order="O-0001")
    assert not any("Copy" in text for text, _ in b.wakes[1:])  # not acknowledged a second time
    b.silent(125)
    assert "Has Alpha arrived?" in b.wakes[-1][0] and "Plan: wait for Alpha." in b.wakes[-1][0]


# -- the server ---------------------------------------------------------------------------------------


def test_tool_list_is_exactly_the_allowlist():
    allowed = {"commander_mission", "commander_roster", "commander_order", "commander_ask", "commander_schedule",
               "commander_unschedule", "commander_end_turn", "commander_brief", "commander_notes", "commander_log",
               "commander_mark", "commander_unmark", "commander_map"}
    assert allowed == TOOL_NAMES


def test_server_has_no_way_to_reach_general_harness_tools():
    source = (REPO_ROOT / "host/src/arma_harness/commander/server.py").read_text(encoding="utf-8")
    assert "mcp_server" not in source and "arma_exec" not in source


class StubRuntime:
    records = None

    def mission(self):
        return {"mission": "Go."}

    def roster(self):
        return {"stations": []}

    def order(self, args):
        raise RuntimeError("Group B Alpha 1-1 O_Soldier_F exploded at 3050,3050")

    def step(self):
        pass

    def end_turn(self, note, messages_only):
        raise Invalid("Call commander_mission first.")


def run_server(*requests) -> list[dict]:
    stdin = io.BytesIO("".join(json.dumps(r) + "\n" for r in requests).encode())
    stdout = io.BytesIO()
    server = Server(stdin, stdout, runtime_factory=lambda deliver: StubRuntime())
    server.stop.set()
    server.serve()
    deadline = time.time() + 3  # tool calls answer on their own threads
    want = sum(1 for r in requests if "id" in r)
    while time.time() < deadline and stdout.getvalue().count(b"\n") < want:
        time.sleep(0.01)
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


def by_id(rows: list[dict]) -> dict:
    return {r["id"]: r for r in rows}


def test_server_declares_the_channel_and_keeps_errors_clean():
    rows = by_id(run_server(
        {"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"method": "notifications/initialized"},
        {"id": 2, "method": "tools/list"},
        {"id": 3, "method": "tools/call", "params": {"name": "commander_roster"}},
        {"id": 4, "method": "tools/call", "params": {"name": "commander_order", "arguments": {}}},
        {"id": 5, "method": "tools/call", "params": {"name": "commander_end_turn", "arguments": {}}},
        {"id": 6, "method": "tools/call", "params": {"name": "arma_exec", "arguments": {"code": "allUnits"}}},
        {"id": 7, "method": "no/such"},
    ))
    assert rows[1]["result"]["capabilities"]["experimental"] == {"claude/channel": {}}
    assert rows[1]["result"]["protocolVersion"] == "2025-06-18"
    assert {t["name"] for t in rows[2]["result"]["tools"]} == TOOL_NAMES
    assert not rows[3]["result"]["isError"]
    assert rows[4]["result"]["content"][0]["text"] == "That request couldn't be processed."
    assert rows[4]["result"]["isError"]
    assert rows[5]["result"]["content"][0]["text"] == "Call commander_mission first."
    assert "Unknown tool" in rows[6]["result"]["content"][0]["text"]
    assert "error" in rows[7]


def test_wakes_are_channel_notifications():
    stdout = io.BytesIO()
    Server(io.BytesIO(), stdout).wake("briefing", {"turn": "2", "woke_on": "1 timer"})
    message = json.loads(stdout.getvalue())
    assert message["method"] == "notifications/claude/channel"
    assert message["params"] == {"content": "briefing", "meta": {"turn": "2", "woke_on": "1 timer"}}
    assert all(key.replace("_", "").isalnum() for key in message["params"]["meta"])


# -- files ----------------------------------------------------------------------------------------------


def test_shipped_scenarios_load():
    good = scenario.load(REPO_ROOT / "scenarios/commander/poc_a_to_b.yaml")
    assert good.time_limit_s == 300 and good.quiet_s == 3 and good.ceiling_s == 15 and good.mid_turn_messages == HOLD
    assert set(good.stations["Alpha"]["capabilities"]) == {"MOVE", "HOLD", "HALT", "POSTURE"}
    lost = scenario.load("poc_a_to_b_lost")
    assert lost.events[0]["at_s"] == 30 and lost.events[0]["action"] == "delete_station"


def test_workspace_locks_the_commander_down(tmp_path, monkeypatch):
    from arma_harness.commander import operator
    from arma_harness.config import Home

    folder = operator.write_workspace(Home(tmp_path))
    settings = json.loads((folder / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert settings["permissions"]["allow"] == ["mcp__commander"]
    denied = set(settings["permissions"]["deny"])
    assert {"Bash", "Read", "mcp__arma", "SendMessage", "ListAgents", "Workflow"} <= denied
    assert json.loads((folder / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["commander"]["args"][-1] == \
        "arma_harness.commander.server"
    assert not (folder / "CLAUDE.md").exists()  # the Read deny would block it: the server delivers the doctrine


def test_server_delivers_the_doctrine_itself():
    rows = by_id(run_server({"id": 1, "method": "initialize", "params": {}},
                            {"id": 2, "method": "tools/call", "params": {"name": "commander_mission"}}))
    assert "commander_end_turn" in rows[1]["result"]["instructions"]
    assert 'When the user says "start"' in rows[1]["result"]["instructions"]
    assert "commander_end_turn" in json.loads(rows[2]["result"]["content"][0]["text"])["doctrine"]
