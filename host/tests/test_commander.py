"""Commander mode, offline: report wording, wake timing, orders, and above all that the fog holds."""
from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pytest
import yaml

from arma_harness.commander import orders, reports, scenario
from arma_harness.commander.orders import Invalid
from arma_harness.commander.records import Records
from arma_harness.commander.reports import Tracker
from arma_harness.commander.runtime import Runtime
from arma_harness.commander.server import (
    DOCTRINE,
    EARLIER_BATTLE,
    LEGS_HELP,
    NO_BATTLE,
    ORDER_TYPES_HELP,
    TOOL_NAMES,
    TOOLS,
    Server,
)
from arma_harness.commander.wake import DELIVER, HOLD, WakeLogic
from arma_harness.config import REPO_ROOT, Home
from arma_harness.harness import HarnessError


@pytest.fixture(autouse=True)
def exact_bearings(monkeypatch):
    """Bearings carry a random error, tested on its own below. Everywhere else, the words need to be predictable."""
    monkeypatch.setattr(reports, "_wobble", lambda spread: 0)


def packet(**over) -> dict:
    base = {"callsign": "Alpha", "pos": [3050.0, 3050.0], "grid": "030030", "dir": 90, "speed": 0, "able": 4,
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
    text = reports.answer(packet(wounded=1, able=3, rounds=190, contacts=[contact()]), None)
    assert "Grid 030 030, stationary." in text and "3 of 4 effective, 1 wounded" in text
    assert "Sam Reed has command" in text and "Ammo amber, about half." in text and "No current orders." in text
    assert "One infantry, bearing 045, roughly 300 metres, seen now." in text
    assert reports.answer(packet(), None, ["ammo"]) == "Ammo green, good."
    trip = route(("MOVE", (3450, 3050), "034 030"))
    assert "About 2 minutes to grid 034 030" in reports.answer(packet(), trip, ["eta"])
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
    assert [r.text for r in said] == ["Copy, moving to grid 034 030. That's 400 m on foot, about 2 minutes."]
    assert said[0].grid is None
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
    assert [r.text for r in said] == ["Copy, checking B1, B3. That's 1.5 km on foot, about 6 minutes."]
    assert reports.answer(packet(order="O-1", clearing=30, cleared=["B1"]), trip, ["task"]) == "Checking B3."
    said = tracker.update(packet(order="O-1", clearing=12, cleared=["B1"]), trip, 200)  # slow isn't stuck
    assert [(r.text, r.checked) for r in said] == [("B1 checked, nothing seen.", "B1")]
    assert tracker.update(packet(order="O-1", clearing=12, cleared=["B1"]), trip, 202) == []
    said = tracker.update(packet(order="O-1", clearing=0, cleared=["B1", "B3"], grid="041041",
                                 contacts=[contact(3060, 3060)]), trip, 300)
    assert "B3 checked, enemy still in the area." in [r.text for r in said]
    assert "Finished checking B1, B3." in [r.text for r in said]  # no grid: there's an enemy about
    assert tracker.update(packet(order="O-1", clearing=0, cleared=["B1", "B3"]), trip, 302) == []


def test_clear_with_no_buildings_says_so():
    said = Tracker().update(packet(order="O-1", clearing=0), clear_route(), 0)
    assert "No known buildings there." in [r.text for r in said]


def test_contacts_near_a_numbered_building_say_which():
    buildings = [{"id": "B3", "pos": [3260.0, 3260.0]}, {"id": "B4", "pos": [3700.0, 3700.0]}]
    said = Tracker().update(packet(contacts=[contact(3250, 3250)]), None, 0, buildings)
    assert said[0].text == "Contact, one infantry, bearing 045, roughly 300 metres, near B3. Engaging."
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
    assert tracker.update(packet(order="O-1", leg=2, legs=5), trip, 0)[0].text == \
        "Copy, sweeping around grid 036 030. That's 600 m on foot, about 2 minutes."
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


def test_contact_reports_dont_state_the_squads_own_grid(tmp_path):
    """Under fire, nobody's checking a map or a GPS. A squad gives its grid when asked, and on arrival."""
    seen = packet(contacts=[contact()])
    said = Tracker().update(seen, None, 0)[0]
    assert said.grid is None and "grid" not in said.text
    assert "grid" not in reports.answer(seen, None, ["contacts"]).lower()
    assert reports.answer(seen, None, ["position", "contacts"]).startswith("Grid 030 030, stationary. One infantry")
    b = Battle(tmp_path)
    b.start()
    b.advance(102, contacts=[contact()], pos=[3250, 3050], grid="032030")
    assert "Alpha" not in b.runtime.positions


def test_what_counts_as_being_in_combat():
    tracker = Tracker()
    assert not tracker.in_combat(packet(), 100)
    assert not tracker.in_combat(packet(behaviour="COMBAT"), 100)  # a commander can order this, and it lingers
    assert not tracker.in_combat(packet(suppression=0.04), 100)
    assert tracker.in_combat(packet(suppression=0.05), 100)
    assert tracker.in_combat(packet(contacts=[contact()]), 100)
    assert not tracker.in_combat(packet(contacts=[contact(age=31)]), 100)
    tracker.update(packet(able=4), None, 100)
    tracker.update(packet(able=3), None, 110)
    assert tracker.in_combat(packet(able=3), 139) and not tracker.in_combat(packet(able=3), 141)


def test_the_harder_a_squad_is_hit_the_slower_it_talks():
    delay = reports.report_delay
    assert [delay(packet(suppression=s)) for s in (0, 0.09, 0.1, 0.39, 0.4, 1.3)] == [5, 5, 15, 15, 30, 30]
    assert delay(packet(suppression=0.5), reports.FLASH) == 15
    assert delay({"suppression": None}) == 5


def test_delays_vary_within_a_range(monkeypatch):
    monkeypatch.undo()
    said = [reports.report_delay(packet(suppression=0.5)) for _ in range(200)]
    assert 21 <= min(said) < 27 and 33 < max(said) <= 39


def test_in_combat_reports_drop_the_squads_own_grid_but_not_places_they_were_told():
    grid = "041 041"
    for words, expect in (
        (f"Arrived, grid {grid}.", "Arrived."),
        (f"On station, grid {grid}.", "On station."),
        (f"Halted at grid {grid}.", "Halted."),
        (f"Holding at grid {grid}.", "Holding."),
        (f"In position, occupying B1, at grid {grid}.", "In position, occupying B1."),
        (f"Passing grid 040 040, at grid {grid}.", "Passing grid 040 040."),
        (f"Not making progress toward grid 050 050, at grid {grid}.", "Not making progress toward grid 050 050."),
        (f"Finished searching around grid {grid}, at grid {grid}.", f"Finished searching around grid {grid}."),
    ):
        report = reports._without_own_grid(reports.Report(reports.ROUTINE, words, grid))
        assert report.text == expect and report.grid is None
    said = Tracker().update(packet(order="O-1", pos=[3050, 3050], leg=1, contacts=[contact()]),
                            route(("MOVE", (3050, 3050), "030 030")), 0)
    assert not [r for r in said if r.grid]


def test_a_squad_in_combat_gives_its_grid_only_when_asked_for_its_position():
    seen = packet(contacts=[contact()])
    calm_answer = reports.answer(seen, None)
    assert calm_answer.startswith("Grid 030 030")
    sitrep = reports.answer(seen, None, None, None, in_combat=True)
    assert "030 030" not in sitrep and "One infantry" in sitrep
    assert reports.answer(seen, None, ["position"], None, in_combat=True).startswith("Grid 030 030")
    held = route(("HOLD", (3050, 3050), "030 030"))
    assert reports.answer(packet(), held, ["task"], None, in_combat=True) == "Holding."
    assert reports.answer(packet(), held, ["task"]) == "Holding at grid 030 030."


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
    assert said[0].text == "Contact, one infantry, bearing 045, roughly 300 metres. Engaging."
    assert tracker.update(packet(contacts=[contact()]), None, 2) == []
    two_more = [contact(), contact(3260, 3260), contact(3270, 3270)]
    assert tracker.update(packet(contacts=two_more), None, 30) == []  # within the repeat limit
    assert "a few" in tracker.update(packet(contacts=two_more), None, 95)[0].text
    assert tracker.update(packet(contacts=[contact(age=60)]), None, 100) == []
    assert [r.text for r in tracker.update(packet(contacts=[contact(age=200)]), None, 220)] == ["Lost contact."]


def test_holding_fire_is_said_when_the_group_cant_engage():
    said = Tracker().update(packet(contacts=[contact()], combat_mode="BLUE"), None, 0)
    assert said[0].text.endswith("Holding fire.")


def test_casualties_group_then_leader_and_ammo_report():
    tracker = Tracker()
    tracker.update(packet(), None, 0)
    assert tracker.update(packet(able=3), None, 2) == []
    assert tracker.update(packet(able=2), None, 20) == []
    said = tracker.update(packet(able=2, wounded=1), None, 33)
    assert [r.text for r in said] == ["Taking casualties, 2 of 4 effective, 1 wounded."]
    assert [r.text for r in tracker.update(packet(able=2, leader="Ana Cole"), None, 40)] == [
        "Leader down, Ana Cole has command."]
    assert [r.text for r in tracker.update(packet(able=2, leader="Ana Cole", rounds=150), None, 42)] == [
        "Ammo amber, about half."]
    assert tracker.update(packet(able=2, leader="Ana Cole", rounds=300), None, 44) == []  # only when worsening


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
    assert wide(legs=[{"type": "CLEAR", "at": "B"}, {"type": "MOVE", "at": "B"}])["mode"] == "chain"


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
    with pytest.raises(Invalid, match="runs until replaced"):
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
    b.game.emit(type="cmd_truth", t=165, groups=[{"group": "Alpha", "side": "WEST", "able": 4, "pos": [3450, 3050]}])
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
    b.game.emit(type="cmd_truth", t=104, groups=[{"group": "Alpha", "side": "WEST", "able": 4, "pos": [3447, 3050]}])
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
    alive = {"group": "Alpha", "side": "WEST", "able": 4, "pos": [3060, 3050]}
    gone = {"group": "Alpha", "side": "WEST", "able": 0, "pos": []}
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
    b.silent(223)
    b.silent(227)
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


def test_timed_order_whose_marker_was_retired_isnt_sent(tmp_path):
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
    return [{"group": "Alpha", "side": "WEST", "able": alpha, "pos": [3050, 3050] if alpha else []},
            {"group": "East 1", "side": "EAST", "able": east1, "pos": [4100, 4100] if east1 else []},
            {"group": "East 2", "side": "EAST", "able": east2, "pos": [4100, 3900] if east2 else []}]


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
    b.game.emit(type="cmd_truth", t=100, groups=[{"group": "East 1", "side": "EAST", "able": 9, "pos": [3400, 3000]}])
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
        b.game.emit(type="cmd_truth", t=102, groups=[{"group": "East 1", "side": "EAST", "able": 9, "pos": truth}])
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
    b.silent(110)
    seen = b.wakes[0][0] + json.dumps(b.runtime.ask("Alpha")) + json.dumps(b.runtime.roster())
    b.game.emit(type="cmd_report", t=128, **packet(**fields))
    b.silent(128)
    b.game.emit(type="cmd_report", t=132, **packet(**fields))
    b.silent(132)
    seen += json.dumps(b.records.read("radio"))
    for banned in ("O_Soldier_F", "2:113", "3250", "3050", "AWARE", "YELLOW", "cmd_report"):
        assert banned not in seen, banned


def with_a_gun(tmp_path) -> Battle:
    b = with_buildings(tmp_path)
    b.runtime = Runtime(b.game, b.scenario, b.records, lambda text, meta: b.wakes.append((text, meta)), world_size=8192,
                        clock=lambda: b.wall, buildings=BUILDINGS,
                        vehicles=[{"id": "V1", "name": "Mk6 Mortar", "at": "041 033", "known": True},
                                  {"id": "V9", "name": "Mk6 Mortar", "at": "050 050", "known": False}])
    b.start()
    b.runtime.end_turn("x", messages_only=True)
    return b


def said_by(b: Battle) -> list[str]:
    return [row["text"] for row in b.records.read("radio")]


def test_the_commander_starts_knowing_only_the_vehicles_it_was_told_about(tmp_path):
    b = with_a_gun(tmp_path)
    assert list(b.runtime.vehicles) == ["V1"]
    assert b.runtime.mission()["vehicles"] == [{"id": "V1", "type": "Mk6 Mortar", "grid": "041 033"}]
    assert "VEHICLES\nV1  Mk6 Mortar  grid 041 033  as briefed" in b.runtime.briefing()


def test_a_squad_reports_an_abandoned_gun_once_and_it_gets_an_id(tmp_path):
    b = with_a_gun(tmp_path)
    seen = [["V9", "Mk6 Mortar", "039035", True]]
    b.advance(102, seen_vehicles=seen)
    b.advance(104, seen_vehicles=seen)
    assert said_by(b) == ["Mk6 Mortar, nobody on it, grid 039 035. Listed as V2."]
    assert b.runtime.vehicles["V2"]["at"] == "039 035"
    assert "V2  Mk6 Mortar  grid 039 035  reported" in b.runtime.briefing()
    assert "V9" not in b.runtime.briefing() and "U1" not in json.dumps(b.runtime.mission())


def test_nobody_takes_stock_of_abandoned_guns_in_a_firefight(tmp_path):
    b = with_a_gun(tmp_path)
    seen = [["U1", "Mk6 Mortar", "039035", True]]
    b.advance(102, seen_vehicles=seen, suppression=0.5)
    assert said_by(b) == [] and list(b.runtime.vehicles) == ["V1"]
    b.advance(104, seen_vehicles=seen)
    assert said_by(b) == ["Mk6 Mortar, nobody on it, grid 039 035. Listed as V2."]


def test_a_known_gun_found_wrecked_or_moved_is_news_once(tmp_path):
    b = with_a_gun(tmp_path)
    moved = [["V1", "Mk6 Mortar", "042033", True]]
    b.advance(102, seen_vehicles=moved)
    b.advance(104, seen_vehicles=moved)
    wreck = [["V1", "Mk6 Mortar", "042033", False]]
    b.advance(106, seen_vehicles=wreck)
    b.advance(108, seen_vehicles=wreck)
    assert said_by(b) == ["V1, Mk6 Mortar, nobody on it, is at grid 042 033.", "V1 is wrecked, grid 042 033."]
    assert "V1  Mk6 Mortar  wrecked  grid 042 033" in b.runtime.briefing()


def test_an_unknown_wreck_isnt_news(tmp_path):
    b = with_a_gun(tmp_path)
    b.advance(102, seen_vehicles=[["U1", "Mk6 Mortar", "039035", False]])
    assert said_by(b) == [] and list(b.runtime.vehicles) == ["V1"]


def test_a_gun_stays_listed_as_it_was_until_someone_sees_otherwise(tmp_path):
    b = with_a_gun(tmp_path)
    b.advance(102)
    assert not b.runtime.vehicles["V1"]["wrecked"]  # truly destroyed or not, nobody's said


def test_a_destroyed_building_is_news_only_once_seen(tmp_path):
    b = with_a_gun(tmp_path)
    assert "BUILDINGS DESTROYED" not in b.runtime.briefing()
    b.advance(102, seen_ruins=["B2"])
    b.advance(104, seen_ruins=["B2"])
    assert said_by(b) == ["B2 is destroyed."]
    assert "BUILDINGS DESTROYED\nB2" in b.runtime.briefing()


def test_clearing_a_ruin_says_so_and_moves_on():
    tracker, trip = Tracker(), clear_route("B1", "B3")
    tracker.update(packet(order="O-1", clearing=30, cleared=[]), trip, 0)
    said = tracker.update(packet(order="O-1", clearing=12, cleared=[], ruined=["B1"]), trip, 20)
    assert [(r.text, r.destroyed, r.checked) for r in said] == [("B1 is a ruin, nothing to check.", "B1", None)]
    assert tracker.update(packet(order="O-1", clearing=12, cleared=[], ruined=["B1"]), trip, 22) == []


def test_a_building_nobody_got_into_is_not_reported_checked():
    """Stratis, Camp Maxwell: AI stop 3 m outside a cargo house, and a man inside survived two "checked" reports."""
    tracker, trip = Tracker(), clear_route("B1", "B3")
    tracker.update(packet(order="O-1", clearing=30, cleared=[]), trip, 0)
    said = tracker.update(packet(order="O-1", clearing=12, cleared=[], blocked=[["B1", 0, 1]]), trip, 20)
    assert [(r.text, r.checked) for r in said] == [("Couldn't get into B1.", None)]
    said = tracker.update(packet(order="O-1", clearing=0, cleared=[], blocked=[["B1", 0, 1], ["B3", 2, 5]]), trip, 40)
    assert [(r.text, r.checked) for r in said][0] == ("B3 checked, nothing seen, but we couldn't get into all of it.",
                                                      "B3")
    assert said[-1].text.startswith("Finished checking B3; couldn't get into B1, at grid")


def test_a_ruin_found_during_a_fight_arrives_late_but_still_counts(tmp_path):
    b = with_a_gun(tmp_path)
    b.runtime.routes["Alpha"] = clear_route("B1", "B3")
    b.advance(102, order="O-1", clearing=30, cleared=[], suppression=0.5)
    b.advance(104, order="O-1", clearing=30, cleared=[], ruined=["B1"], suppression=0.5)
    assert "B1" not in b.runtime.destroyed
    for t in (110, 116, 122, 128, 134, 140, 146, 152):
        b.advance(t, order="O-1", clearing=30, cleared=[], ruined=["B1"], suppression=0.5)
    assert "B1" in b.runtime.destroyed


def test_vehicles_in_a_sitrep_and_the_vehicles_topic():
    on_gun = packet(mounted=[["V1", "gunner", "Sam Reed", "B_Mortar_01_F"]])
    assert reports.answer(on_gun, None, ["vehicles"]) == "On V1: Sam Reed as gunner. 3 on foot."
    assert reports.answer(packet(), None, ["vehicles"]) == "All on foot."
    assert "on foot" not in reports.answer(packet(), None)
    assert "On V1: Sam Reed as gunner." in reports.answer(on_gun, None)
    all_in = packet(able=2, mounted=[["V3", "driver", "A B", "x"], ["V3", "cargo", "C D", "x"]])
    assert reports.answer(all_in, None, ["vehicles"]) == "On V3: A B as driver, C D as cargo."
    assert reports.answer(packet(mounted=[["", "gunner", "A B", "x"]]), None, ["vehicles"]).startswith("On a vehicle:")


def test_engine_keys_become_the_commanders_ids_in_answers(tmp_path):
    b = with_a_gun(tmp_path)
    b.advance(102, mounted=[["V1", "gunner", "Sam Reed", "B_Mortar_01_F"]])
    assert "On V1: Sam Reed as gunner" in b.runtime.ask("Alpha", ["vehicles"])["replies"][0]["text"]
    b.advance(104, mounted=[["U7", "gunner", "Sam Reed", "B_Mortar_01_F"]])
    answer = b.runtime.ask("Alpha", ["vehicles"])["replies"][0]["text"]
    assert "U7" not in answer and "B_Mortar" not in answer and "On a vehicle" in answer


def test_vehicle_knowledge_survives_a_server_restart(tmp_path):
    b = with_a_gun(tmp_path)
    b.advance(102, seen_vehicles=[["U1", "Mk6 Mortar", "039035", True]], seen_ruins=["B2"])
    b.runtime.save()
    again = Runtime(b.game, b.scenario, b.records, lambda text, meta: None, world_size=8192, clock=lambda: b.wall,
                    buildings=BUILDINGS, vehicles=[{"id": "V1", "name": "Mk6 Mortar", "at": "041 033", "known": True}])
    assert set(again.vehicles) == {"V1", "V2"} and again.vehicles["V2"]["key"] == "U1" and "B2" in again.destroyed


def test_the_map_draws_vehicles_and_ruins(tmp_path):
    b = with_a_gun(tmp_path)
    b.advance(102, seen_vehicles=[["V1", "Mk6 Mortar", "041033", False]], seen_ruins=["B1"])
    assert b.runtime.map_image(center="034 030", radius=400)["png"].startswith(b"\x89PNG")


def test_a_scenario_cant_crew_a_vehicle_it_doesnt_have():
    raw = {"name": "t", "mission": "m", "text": "x", "time_limit": "5:00",
           "vehicles": [{"id": "V1", "class": "B_Mortar_01_F", "at": "041 033", "ammo": {"8Rnd_82mm_Mo_shells": 16}}],
           "stations": [{"callsign": "Hammer", "role": "mortars", "capabilities": ["MOVE"], "at": "041 033",
                         "crew": {"V1": "gunner"}, "spotter": False}]}
    built = scenario.build(raw)
    assert built.vehicles[0]["known"] and built.stations["Hammer"]["crew"] == {"V1": "gunner"}
    raw["stations"][0]["crew"] = {"V2": "gunner"}
    with pytest.raises(ValueError, match="unknown vehicles"):
        scenario.build(raw)


BOARDING = {"Alpha": {**STATIONS["Alpha"], "capabilities": ["MOVE", "MOUNT", "DISMOUNT"]}}
LIST = {"V1": {"id": "V1", "key": "V1"}, "V2": {"id": "V2", "key": "U7"}}


def boarding(**leg) -> dict:
    return orders.validate({"to": "Alpha", "legs": [leg]}, BOARDING, MARKERS, 8192, BUILDINGS, LIST)


def test_mount_orders_go_by_the_commanders_own_list():
    order = boarding(type="MOUNT", vehicle="V2", seat="Gunner")
    assert order["mode"] == "mount" and order["engine_legs"] == [["U7", "gunner"]]  # the game's key, never shown
    assert order["route"] == {"kind": "mount", "legs": [], "vehicle": "V2", "seat": "gunner"}
    assert boarding(type="MOUNT", vehicle="V1")["engine_legs"] == [["V1", ""]]
    assert boarding(type="MOUNT", vehicle="V1", seat="turret:2")["engine_legs"] == [["V1", "turret:2"]]
    assert boarding(type="DISMOUNT")["engine_legs"] == [["", ""]]
    assert boarding(type="DISMOUNT", vehicle="V1")["route"]["vehicle"] == "V1"


@pytest.mark.parametrize("leg, words", [
    ({"type": "MOUNT", "vehicle": "V9"}, "from your list"),
    ({"type": "MOUNT"}, "from your list"),
    ({"type": "DISMOUNT", "vehicle": "V9"}, "from your list"),
    ({"type": "MOUNT", "vehicle": "V1", "seat": "roof"}, "Bad seat"),
])
def test_bad_mount_orders_are_refused(leg, words):
    with pytest.raises(Invalid, match=words):
        boarding(**leg)


def test_mount_needs_the_capability():
    with pytest.raises(Invalid, match="can't do MOUNT"):
        one = [{"type": "MOUNT", "vehicle": "V1"}]
        orders.validate({"to": "Alpha", "legs": one}, STATIONS, MARKERS, 8192, [], LIST)


def mount_route(vehicle="V1", seat="gunner") -> dict:
    return {"kind": "mount", "legs": [], "vehicle": vehicle, "seat": seat}


def test_mounting_acknowledges_then_reports_how_it_went():
    tracker, trip = Tracker(), mount_route()
    said = tracker.update(packet(order="O-1", mount=["V1", "going", "gunner", []]), trip, 0)
    assert [r.text for r in said] == ["Copy, mounting V1 as gunner."]
    said = tracker.update(packet(order="O-1", mount=["V1", "on", "gunner", ["Sam Reed"], 0]), trip, 16)
    assert [r.text for r in said] == ["Sam Reed on V1 as gunner."]
    assert tracker.update(packet(order="O-1", mount=["V1", "on", "gunner", ["Sam Reed"], 0]), trip, 18) == []


@pytest.mark.parametrize("status, words", [
    (["V1", "wrecked", "gunner", []], "V1 is wrecked. Not mounting."),
    (["V1", "noseat", "driver", []], "Unable, V1 has no driver seat."),
    (["V1", "taken", "gunner", []], "Unable, V1's gunner seat is taken."),
    (["V1", "taken", "", []], "Unable, V1 is full."),
    (["V1", "nobody", "", []], "Unable, nobody free to mount V1."),
    (["V1", "unreachable", "gunner", []], "Unable, can't reach V1."),
    (["V3", "on", "", ["A B", "C D"], 4], "A B, C D on V3. 4 didn't fit."),
    (["V3", "off", "", ["A B"]], "Off V3."),
    (["", "none", "", []], "Nobody's on a vehicle."),
])
def test_how_boarding_is_said(status, words):
    assert reports._boarding_words(status) == words


def test_a_squad_moving_off_says_who_stays_on_the_gun():
    trip = route(("MOVE", (3450, 3050), "034 030"))
    seated = [["V1", "gunner", "Pat Vane", True]]
    assert Tracker().update(packet(order="O-1", mounted=seated), trip, 0)[0].text == \
        "Copy, moving to grid 034 030. Pat Vane stays on V1. That's 400 m on foot, about 2 minutes."
    # A leader's taken off by the game side, and a man in a truck goes with it.
    leader = [["V1", "gunner", "Sam Reed", True]]
    assert "stays" not in Tracker().update(packet(order="O-1", mounted=leader), trip, 0)[0].text
    truck = [["V2", "driver", "Pat Vane", False]]
    assert "stays" not in Tracker().update(packet(order="O-1", mounted=truck), trip, 0)[0].text


def test_losing_a_gunner_is_reported_but_getting_off_isnt():
    tracker = Tracker()
    seated = [["V1", "gunner", "Pat Vane", True]]
    tracker.update(packet(mounted=seated), None, 0)
    said = tracker.update(packet(able=3, mounted=[]), None, 2)
    assert [r.text for r in said] == ["Gunner down on V1."] and said[0].precedence == reports.PRIORITY
    tracker = Tracker()
    tracker.update(packet(mounted=seated), None, 0)
    assert tracker.update(packet(mounted=[]), None, 2) == []


def test_the_runtime_sends_the_games_key_and_reports_the_commanders_id(tmp_path):
    station = {"callsign": "Alpha", "role": "x", "capabilities": ["MOVE", "MOUNT", "DISMOUNT"], "at": "030 030"}
    b = Battle(tmp_path, stations=[station])
    b.runtime = Runtime(b.game, b.scenario, b.records, lambda text, meta: b.wakes.append((text, meta)), world_size=8192,
                        clock=lambda: b.wall, vehicles=[{"id": "V1", "name": "Mk6 Mortar", "at": "041 033"}])
    b.start()
    b.runtime.vehicles["V2"] = {"id": "V2", "key": "U7", "name": "Hunter", "at": "030 030", "t": 100, "wrecked": False}
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOUNT", "vehicle": "V2", "seat": "driver"}]})
    assert b.game.calls[-1][1][:4] == ["Alpha", "O-0001", "mount", [["U7", "driver"]]]
    assert "O-0001: MOUNT V2" in said_by(b)[-1]
    b.advance(102, order="O-0001", mount=["U7", "on", "driver", ["Sam Reed"], 0],
              mounted=[["U7", "driver", "Sam Reed", False]])
    assert "Sam Reed on V2 as driver." in said_by(b)
    assert "U7" not in " ".join(said_by(b)) and "On V2" in b.runtime.ask("Alpha", ["vehicles"])["replies"][0]["text"]


FIRING = {"Hammer": {"capabilities": ["FIRE_MISSION", "CHECK_FIRE"]},
          "Recon": {"capabilities": ["MOVE"], "spotter": True}}


def fire(**leg) -> dict:
    request = {"to": "Hammer", "legs": [{"type": "FIRE_MISSION", **leg}]}
    return orders.validate(request, FIRING, MARKERS, 8192, BUILDINGS, LIST)


def test_fire_missions_take_six_or_eight_figures():
    six = fire(at="041 041")
    assert six["mode"] == "fire" and six["engine_legs"] == [[[], [4150.0, 4150.0], "HE", 3, 0.0]]
    eight = fire(at="0412 0415", ammo="smoke", rounds=6, radius=30, observer="Recon", guns=["V2"])
    assert eight["engine_legs"] == [[["U7"], [4125.0, 4155.0], "SMOKE", 6, 30.0]]  # the game's key, never shown
    assert eight["mission"]["observer"] == "Recon" and eight["mission"]["grid"] == "0412 0415"
    assert eight["words"] == "Copy, fire mission, 6 SMOKE at grid 0412 0415."


@pytest.mark.parametrize("at", ["B1", "B", "E1", None, "", "04 04", ["041 041", "042 042"], "04120415x"])
def test_a_fire_mission_cant_be_called_on_a_token(at):
    """An RTO can't call fire on "that house": the commander has to work out the grid."""
    with pytest.raises(Invalid, match="grid reference"):
        fire(at=at)


@pytest.mark.parametrize("leg, words", [
    ({"ammo": "MINE"}, "Bad ammo"),
    ({"rounds": 0}, "rounds must be"),  # the engine fires a burst of 4 if asked for none
    ({"rounds": -1}, "rounds must be"),
    ({"rounds": 33}, "rounds must be"),
    ({"rounds": 1.5}, "rounds must be"),
    ({"rounds": True}, "rounds must be"),
    ({"radius": 151}, "radius"),
    ({"observer": "Nobody"}, "Unknown observer"),
    ({"observer": "Hammer"}, "isn't trained"),
    ({"guns": ["V9"]}, "vehicle list"),
])
def test_bad_fire_missions_are_refused(leg, words):
    with pytest.raises(Invalid, match=words):
        fire(at="041 041", **leg)


def test_other_orders_stay_at_six_figures():
    with pytest.raises(Invalid, match="six digits"):
        wide(legs=[{"type": "MOVE", "at": "0412 0415"}])
    assert orders.parse_grid("0412 0415", 8192, precise=True) == ([4125.0, 4155.0], "0412 0415")


def test_check_fire_and_needing_the_capability():
    order = orders.validate({"to": "Hammer", "legs": [{"type": "CHECK_FIRE"}]}, FIRING, MARKERS, 8192, [], LIST)
    assert order["mode"] == "checkfire" and order["engine_legs"] == [[[]]] and order["words"] == "Copy, check fire."
    with pytest.raises(Invalid, match="can't do FIRE_MISSION"):
        orders.validate({"to": "Recon", "legs": [{"type": "FIRE_MISSION", "at": "041 041"}]},
                        FIRING, MARKERS, 8192, [], LIST)
    with pytest.raises(Invalid, match="only leg"):
        orders.validate({"to": "Hammer", "legs": [{"type": "FIRE_MISSION", "at": "041 041"}, {"type": "CHECK_FIRE"}]},
                        FIRING, MARKERS, 8192, [], LIST)


AIR = {"Hawg": {"capabilities": ["CAS"]}, "Recon": {"capabilities": ["MOVE"]}}


def cas(**leg) -> dict:
    return orders.validate({"to": "Hawg", "legs": [{"type": "CAS", **leg}]}, AIR, MARKERS, 8192, [], LIST)


def test_air_support_goes_by_grid_with_a_radius():
    order = cas(at="037 024")
    assert order["mode"] == "cas" and order["engine_legs"] == [[[3750.0, 2450.0], 150]]
    assert order["words"] == "Copy, grid 037 024, on the way." and order["route"] is None
    assert cas(at="0375 0245", radius=300)["engine_legs"] == [[[3755.0, 2455.0], 300]]


@pytest.mark.parametrize(("leg", "words"), [
    ({"at": "B"}, "Markers and building ids can't be passed to a pilot"),
    ({}, "grid reference"),
    ({"at": "037 024", "radius": 20}, "between 50 and 500"),
    ({"at": "037 024", "radius": 900}, "between 50 and 500"),
])
def test_bad_air_support_is_refused(leg, words):
    with pytest.raises(Invalid, match=words):
        cas(**leg)


def test_air_support_goes_alone_and_needs_the_capability():
    with pytest.raises(Invalid, match="CAS must be the only leg"):
        orders.validate({"to": "Hawg", "legs": [{"type": "CAS", "at": "037 024"}, {"type": "CAS", "at": "038 024"}]},
                        AIR, MARKERS, 8192, [], LIST)
    with pytest.raises(Invalid, match="can't do CAS"):
        orders.validate({"to": "Recon", "legs": [{"type": "CAS", "at": "037 024"}]}, AIR, MARKERS, 8192, [], LIST)


def test_the_pilot_reads_back_the_grid_and_how_long(tmp_path):
    hawg = {"callsign": "Hawg", "role": "attack helicopter", "capabilities": ["CAS"], "at": "025 018"}
    b = Battle(tmp_path, stations=[hawg], success={"station": "Hawg", "within_m": 50, "of": "034 030"})
    b.start()
    b.advance(102, callsign="Hawg", pos=[2550, 1850])
    b.runtime.order({"to": "Hawg", "legs": [{"type": "CAS", "at": "037 024"}]})
    assert b.game.calls[-1][1][2:4] == ["cas", [[[3750.0, 2450.0], 150]]]
    b.advance(104, callsign="Hawg", pos=[2550, 1850], order="O-0001")
    assert said(b)[-1] == "Copy, grid 037 024, on the way. Under a minute out."  # 1.3 km at 60 m/s


def test_what_the_pilot_says_through_a_sortie(tmp_path):
    b = Battle(tmp_path)
    b.start()
    for t, state, detail in ((102, "over", "037 024"), (104, "engaging", "guns"), (106, "off target", "")):
        b.advance(t, medical=[["O-1", "sortie", "V1", "", state, detail]])
    assert said(b) == ["Over grid 037 024, looking.", "Engaging, guns.", "Off target, returning to hold."]
    b.advance(108, medical=[["O-2", "sortie", "V1", "", "nothing seen", "037 024"]])
    assert said(b)[-1] == "Nothing seen around grid 037 024, returning to hold."


def mission(state="firing", fired=0, want=6, reason="", word="HE", eta=27.6, in_air=0, gun="V1", order="O-1"):
    return [gun, order, state, reason, word, fired, want, eta, in_air]


def firing_at(tracker, row, t=0, **over):
    return [r.text for r in tracker.update(packet(order="O-1", missions=[row], **over), None, t)]


def test_a_mission_reports_shot_then_rounds_complete_once_each():
    tracker = Tracker()
    tracker.order = "O-1"
    assert firing_at(tracker, mission()) == []
    assert firing_at(tracker, mission(fired=1), 2) == ["Shot, 6 rounds, splash in about 30 seconds."]
    assert firing_at(tracker, mission(fired=4), 4) == []
    left = [["V1", [["HE", 10], ["SMOKE", 4]]]]
    assert firing_at(tracker, mission("done", fired=6), 6, gun_ammo=left) == ["Rounds complete. 10 HE left."]
    assert firing_at(tracker, mission("done", fired=6), 8, gun_ammo=left) == []


def test_a_short_mission_still_says_shot_before_it_says_done():
    tracker = Tracker()
    tracker.order = "O-1"
    said = firing_at(tracker, mission("done", fired=2, want=2), gun_ammo=[["V1", [["HE", 6]]]])
    assert said == ["Shot, 2 rounds, splash in about 30 seconds.", "Rounds complete. 6 HE left."]


@pytest.mark.parametrize("row, words", [
    (mission("unable", reason="out of range"), "Unable, out of range."),
    (mission("unable", reason="no gunner"), "Unable, no gunner on V1."),
    (mission("unable", reason="no ammo", word="SMOKE"), "Unable, out of SMOKE."),
    (mission("unable", reason="no gun", gun=""), "Unable, no gun crewed."),
    (mission("unable", reason="destroyed"), "Unable, V1 is destroyed."),
    (mission("cantlay"), "Unable, can't lay on that target."),
    (mission("holding"), "Holding, weapons tight. Mission waiting."),
])
def test_every_way_a_mission_can_fail_is_said_aloud(row, words):
    tracker = Tracker()
    tracker.order = "O-1"
    assert firing_at(tracker, row) == [words]


def test_a_mission_cut_short_says_how_many_went():
    tracker = Tracker()
    tracker.order = "O-1"
    assert firing_at(tracker, mission("out", fired=2)) == ["Shot, 6 rounds, splash in about 30 seconds.",
                                                          "Out of HE, 2 of 6 fired."]
    tracker = Tracker()
    tracker.order = "O-1"
    assert firing_at(tracker, mission("gunner", fired=2))[-1] == "2 of 6 fired, no gunner on V1."
    tracker = Tracker()
    tracker.order = "O-1"
    assert firing_at(tracker, mission("destroyed", fired=2))[-1] == "V1 destroyed, 2 of 6 fired."


def test_check_fire_says_whats_still_coming():
    tracker = Tracker()
    tracker.order = "O-1"
    assert firing_at(tracker, mission("checked", fired=2, in_air=2, want=0, word="")) == \
        ["2 rounds still in the air."]
    tracker = Tracker()
    tracker.order = "O-1"
    assert firing_at(tracker, mission("checked", fired=1, in_air=1, want=0, word="")) == ["1 round still in the air."]
    tracker = Tracker()
    tracker.order = "O-1"
    assert firing_at(tracker, mission("checked", want=0, word="")) == []


def test_one_round_is_one_round():
    tracker = Tracker()
    tracker.order = "O-1"
    assert firing_at(tracker, mission(fired=1, want=1)) == ["Shot, 1 round, splash in about 30 seconds."]


def test_a_squad_leaving_a_fight_cant_get_ahead_of_itself(tmp_path):
    b = in_the_fight(tmp_path)
    b.advance(102, contacts=[contact()], suppression=0.5, missions=[mission(fired=1, order="O-9")])
    assert radio_words(b) == []
    b.advance(104, contacts=[], suppression=0, missions=[mission("done", fired=6, order="O-9")])
    assert radio_words(b) == []  # it isn't in combat now, but it has things waiting to be said first
    b.advance(200, contacts=[], suppression=0)
    words = radio_words(b)
    assert words.index("Shot, 6 rounds, splash in about 30 seconds.") < words.index("Rounds complete.")


def test_no_script_ever_makes_a_shell():
    """Rounds always come from a real gun. Scripted fire is how the mods this was compared with do it."""
    code = (Path(reports.__file__).parent.parent / "adapters" / "commander_boot.sqf").read_text(encoding="utf-8")
    assert "doArtilleryFire" in code
    for banned in ("fireSupportVirtual", "BIS_fnc_fireSupport", "Sh_82mm", "Sh_155mm", "Smoke_82mm"):
        assert banned not in code


def test_holding_then_firing_is_each_reported_once():
    tracker = Tracker()
    tracker.order = "O-1"
    assert firing_at(tracker, mission("holding")) == ["Holding, weapons tight. Mission waiting."]
    assert firing_at(tracker, mission("holding"), 2) == []
    assert firing_at(tracker, mission(fired=1), 4) == ["Shot, 6 rounds, splash in about 30 seconds."]


def test_a_new_mission_reports_afresh():
    tracker = Tracker()
    tracker.order = "O-1"
    firing_at(tracker, mission("done", fired=6))
    next_one = packet(order="O-1", missions=[mission("done", fired=6, order="O-2")])
    said = [r.text for r in tracker.update(next_one, None, 2)]
    assert "Rounds complete." in said


def test_the_squads_gun_ammo_comes_with_its_own():
    answer = reports.answer(packet(gun_ammo=[["V1", [["HE", 16], ["SMOKE", 4]]]]), None, ["ammo"])
    assert answer == "Ammo green, good. V1: 16 HE, 4 SMOKE."
    assert reports.answer(packet(gun_ammo=[["V1", []]]), None, ["ammo"]).endswith("V1: empty.")


def gunnery(tmp_path) -> Battle:
    capabilities = ["MOVE", "FIRE_MISSION", "CHECK_FIRE"]
    station = {"callsign": "Alpha", "role": "x", "capabilities": capabilities, "at": "030 030", "spotter": True}
    b = Battle(tmp_path, stations=[station])
    b.runtime = Runtime(b.game, b.scenario, b.records, lambda text, meta: b.wakes.append((text, meta)), world_size=8192,
                        clock=lambda: b.wall, vehicles=[{"id": "V1", "name": "Mk6 Mortar", "at": "030 030"}])
    b.start()
    return b


def test_fire_orders_leave_the_squads_route_alone(tmp_path):
    b = gunnery(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOVE", "at": "034 030"}]})
    route_before = b.runtime.routes["Alpha"]["legs"]
    b.advance(102, order="O-0001")
    b.runtime.order({"to": "Alpha", "legs": [{"type": "FIRE_MISSION", "at": "041 041", "rounds": 2}]})
    assert b.game.calls[-1][1][:4] == ["Alpha", "O-0002", "fire", [[[], [4150.0, 4150.0], "HE", 2, 0.0]]]
    assert b.runtime.routes["Alpha"]["legs"] == route_before
    b.advance(104, order="O-0002", leg=0)
    assert "Copy, fire mission, 2 HE at grid 041 041." in said_by(b)
    assert not [w for w in said_by(b) if w.startswith("Copy, moving") and said_by(b).count(w) > 1]


def test_a_fire_mission_records_what_the_commander_believed(tmp_path):
    b = gunnery(tmp_path)
    b.runtime.mark({"id": "E1", "kind": "enemy", "at": "041 041"})
    b.advance(102, order="", pos=[3050, 3050])
    b.runtime.ask("Alpha", ["position"])
    b.runtime.order({"to": "Alpha", "legs": [{"type": "FIRE_MISSION", "at": "0412 0415", "observer": "Alpha"}]})
    row = b.records.read("fire_missions")[0]
    assert row["id"] == "O-0001" and row["grid"] == "0412 0415" and row["aim"] == [4125.0, 4155.0]
    assert row["markers"][-1]["id"] == "E1" and row["positions"]["Alpha"]["grid"] == "030 030"
    assert row["observer"] == "Alpha" and "Alpha" in row["last_heard"]


def test_missions_never_show_the_games_keys(tmp_path):
    b = gunnery(tmp_path)
    b.advance(102, order="", missions=[["U7", "O-1", "unable", "no gunner", "HE", 0, 3, 0, 0]],
              gun_ammo=[["U7", [["HE", 8]]]])
    assert "U7" not in json.dumps(said_by(b)) and "Unable, no gunner on the gun." in said_by(b)
    assert "U7" not in b.runtime.ask("Alpha", ["ammo"])["replies"][0]["text"]


def test_a_marker_can_hold_a_commanders_eight_figure_working(tmp_path):
    b = gunnery(tmp_path)
    b.runtime.mark({"id": "E1", "kind": "enemy", "at": "0412 0415"})
    assert b.runtime.markers["E1"]["at"] == "0412 0415"
    assert "grid 0412 0415" in b.runtime.briefing()
    assert b.runtime.map_image(center="E1", radius=100)["png"].startswith(b"\x89PNG")
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOVE", "at": "E1"}]})
    assert b.game.calls[-1][1][3][0][1] == [4125.0, 4155.0]


def land(b, t, pos=(3050, 3350), distance=300, dx=0, dy=300, seen=False, order="", who="Alpha", ammo="Sh_82mm_AMOS"):
    b.t = t
    b.game.emit(type="cmd_impact", t=t, pos=list(pos), gun="V1", order=order, side="WEST", ammo=ammo,
                heard=[[who, distance, dx, dy, seen]])


def spotting(tmp_path, spotter=True) -> Battle:
    capabilities = ["MOVE", "FIRE_MISSION", "CHECK_FIRE"]
    station = {"callsign": "Alpha", "role": "x", "capabilities": capabilities, "at": "030 030", "spotter": spotter}
    b = Battle(tmp_path, stations=[station])
    b.start()
    b.runtime.end_turn("x", messages_only=True)
    return b


def latest(b) -> list[str]:
    return [row["text"] for row in b.records.read("radio") if row["from"] != "HQ"]


def test_shells_close_by_are_under_fire_once_per_burst(tmp_path):
    b = spotting(tmp_path, spotter=False)
    land(b, 102, distance=52, dx=0, dy=52)
    b.advance(102)
    land(b, 104, distance=30, dx=30, dy=0)
    b.advance(104)
    assert b.runtime._in_combat("Alpha")  # shells landing move nothing else the engine measures
    b.advance(120)
    land(b, 150, distance=60, dx=-60, dy=0)  # long enough to be a new burst
    b.advance(150)
    b.advance(190)
    said = latest(b)
    assert said == ["Under indirect fire, explosions about 50 m north.",
                    "Under indirect fire, explosions about 60 m west."]
    assert not b.runtime._in_combat("Alpha")  # and it's over, 40 s on


def test_shells_further_off_are_mentioned_at_most_once_a_minute(tmp_path):
    b = spotting(tmp_path, spotter=False)
    land(b, 102, distance=210, dx=0, dy=-210)
    b.advance(102)
    land(b, 120, distance=210, dx=0, dy=-210)
    b.advance(120)
    land(b, 170, distance=390, dx=390, dy=0)
    b.advance(170)
    assert latest(b) == ["Explosions to the south, roughly 200 metres.", "Explosions to the east, roughly 400 metres."]
    assert not b.runtime._in_combat("Alpha")


def test_shells_further_than_earshot_and_smoke_say_nothing(tmp_path):
    b = spotting(tmp_path, spotter=False)
    land(b, 102, distance=420, dx=0, dy=420)
    land(b, 103, distance=40, dx=0, dy=40, ammo="Smoke_82mm_AMOS_White")
    b.advance(103)
    b.advance(120)
    assert latest(b) == [] and not b.runtime._in_combat("Alpha")


def test_nobody_says_whose_shells_they_were(tmp_path):
    b = spotting(tmp_path, spotter=False)
    b.runtime.order({"to": "Alpha", "legs": [{"type": "FIRE_MISSION", "at": "030 030"}]})
    land(b, 102, distance=40, order="O-0001")
    b.advance(102, order="O-0001")
    b.advance(150, order="O-0001")
    for words in latest(b):
        assert "friendly" not in words.lower() and "our" not in words.lower().split()


def test_a_commanders_observer_calls_the_fall_of_shot_against_the_grid(tmp_path):
    b = spotting(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [{"type": "FIRE_MISSION", "at": "030 030", "observer": "Alpha"}]})
    b.advance(102, order="O-0001")
    land(b, 110, pos=(3112, 3027), order="O-0001", seen=True)
    land(b, 112, pos=(3088, 3033), order="O-0001", seen=True)
    land(b, 113, pos=(3400, 3400), order="O-0001", seen=False)  # lost in the dust of the others
    b.advance(114, order="O-0001")
    assert not [w for w in latest(b) if "Splash" in w]
    b.advance(118, order="O-0001")
    assert "Splash 20 m south, 50 m east of your grid. 2 rounds seen." in latest(b)


def test_an_observer_calls_against_the_enemy_it_can_see(tmp_path):
    b = spotting(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [{"type": "FIRE_MISSION", "at": "030 030", "observer": "Alpha"}]})
    land(b, 110, pos=(3150, 3240), order="O-0001", seen=True)
    near, far = contact(3120, 3200), contact(2000, 2000)
    b.advance(115, order="O-0001", contacts=[far, near])
    b.advance(200, order="O-0001", contacts=[])
    assert "Splash 40 m north, 30 m east of the enemy at bearing 025. 1 round seen." in latest(b)


def test_an_observer_can_be_dead_on(tmp_path):
    b = spotting(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [{"type": "FIRE_MISSION", "at": "030 030", "observer": "Alpha"}]})
    land(b, 110, pos=(3052, 3047), order="O-0001", seen=True)
    b.advance(115, order="O-0001")
    assert "Splash on your grid. 1 round seen." in latest(b)


def test_offsets_are_called_by_eye():
    assert [reports._offset(m) for m in (4, 6, 94, 96, 122, 138, -67)] == [0, 10, 90, 100, 100, 150, 70]


def test_an_observer_with_no_view_says_so_once(tmp_path):
    b = spotting(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [{"type": "FIRE_MISSION", "at": "030 030", "observer": "Alpha"}]})
    land(b, 110, order="O-0001", distance=900, seen=False)
    b.advance(115, order="O-0001")
    land(b, 130, order="O-0001", distance=900, seen=False)
    b.advance(135, order="O-0001")
    assert latest(b).count("Can't observe. No view of the fall of shot.") == 1


def test_a_spotter_not_assigned_says_what_it_saw(tmp_path):
    b = spotting(tmp_path)
    land(b, 110, pos=(3160, 3370), distance=340, dx=110, dy=320, seen=True)
    b.advance(111)
    assert latest(b) == []  # it won't say "explosions" as well
    b.advance(115)
    assert latest(b) == ["Splash seen, grid 031 033, about 350 m north of us."]


def test_only_a_spotter_reports_where_a_round_fell(tmp_path):
    b = spotting(tmp_path, spotter=False)
    land(b, 110, distance=340, dx=0, dy=340, seen=True)
    b.advance(111)
    b.advance(120)
    assert latest(b) == ["Explosions to the north, roughly 350 metres."]


def test_shells_land_in_the_truth_not_on_the_radio(tmp_path):
    b = spotting(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [{"type": "FIRE_MISSION", "at": "030 030", "observer": "Alpha"}]})
    land(b, 110, pos=(3112, 3027), order="O-0001", seen=True)
    b.advance(115, order="O-0001")
    row = b.records.read_shells()[0]
    assert row["pos"] == [3112, 3027] and row["aim"] == [3050.0, 3050.0] and row["order"] == "O-0001"
    assert row["gun"] == "V1" and row["t"] == 110 - b.runtime.t0 and row["heard"][0][0] == "Alpha"
    assert "Sh_82mm" not in json.dumps(b.records.read("radio"))


def test_the_roster_says_who_can_correct_fire(tmp_path):
    assert spotting(tmp_path).runtime.roster()["stations"][0]["corrects_fire"] is True


def test_impact_reports_survive_a_restart_of_the_host(tmp_path):
    b = spotting(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [{"type": "FIRE_MISSION", "at": "030 030", "observer": "Alpha"}]})
    land(b, 110, order="O-0001", pos=(3050, 3050), seen=True)
    b.advance(111, order="O-0001")
    b.runtime.save()
    b.runtime = b.new_runtime()
    assert b.runtime.trackers["Alpha"].spotter is True and b.runtime.fire_orders["O-0001"]["observer"] == "Alpha"
    b.advance(116, order="O-0001")
    assert "Splash on your grid. 1 round seen." in latest(b)


def test_the_mortar_scenario_is_a_real_battle():
    raw = yaml.safe_load((Path(__file__).parents[2] / "scenarios/commander/village_with_mortar.yaml").read_text())
    built = scenario.build(raw)
    assert built.stations["Recon"]["spotter"] and not built.stations["Alpha"]["spotter"]
    assert built.stations["Hammer"]["crew"] == {"V1": "gunner"}
    assert built.vehicles[0]["ammo"] == {"HE": 16, "SMOKE": 4}
    assert {"FIRE_MISSION", "CHECK_FIRE"} <= set(built.stations["Hammer"]["capabilities"])


def marching(tmp_path) -> Battle:
    teams = [{"callsign": name, "role": "x", "capabilities": ["MOVE"], "at": "029 029"} for name in ("Alpha", "Bravo")]
    b = Battle(tmp_path, stations=teams, success={"stations": ["Alpha", "Bravo"], "on_foot": True, "within_m": 100,
                                                  "of": "052 044"})
    b.start()
    return b


def team(name, x=5250, y=4450, mounted=0, able=4) -> dict:
    return {"group": name, "side": "WEST", "able": able, "mounted": mounted, "pos": [x, y],
            "units": [[x, y, 0]] * able}


def truth(b, t, *groups) -> None:
    b.t = t
    b.game.emit(type="cmd_truth", t=t, groups=list(groups))
    b.runtime.step(0)


def met(b) -> list[str]:
    return [due["met"] for due in b.runtime.objectives_due.values()]


@pytest.mark.parametrize("groups", [
    [team("Alpha", mounted=4), team("Bravo", mounted=4)],  # there, but still aboard
    [team("Alpha"), team("Bravo", mounted=1)],  # someone's still getting out
    [team("Alpha"), team("Bravo", x=4000)],  # one team's elsewhere
    [team("Alpha")],  # the other isn't on the net at all
    [team("Alpha"), team("Bravo", able=0)],  # wiped out
])
def test_a_march_isnt_over_until_both_teams_are_on_foot_there(tmp_path, groups):
    b = marching(tmp_path)
    truth(b, 110, *groups)
    assert met(b) == []


def test_one_man_short_of_the_grid_isnt_there(tmp_path):
    b = marching(tmp_path)
    straggler = team("Bravo")
    straggler["units"][3] = [4000, 4450, 0]
    truth(b, 110, team("Alpha"), straggler)
    assert met(b) == []


def test_a_man_down_somewhere_else_means_theyre_not_all_there(tmp_path):
    """Sonnet was told all six were on foot at the objective, with four there and two unconscious 900 m back."""
    b = marching(tmp_path)
    truth(b, 110, team("Alpha"), {**team("Bravo"), "down": [[4100, 4000]]})
    assert met(b) == []
    b.advance(125)
    assert not b.runtime.ended


def test_a_man_down_at_the_grid_isnt_on_foot_there(tmp_path):
    b = marching(tmp_path)
    truth(b, 110, team("Alpha"), {**team("Bravo"), "down": [[5250, 4450]]})
    assert met(b) == []


def test_a_team_at_the_grid_counts_a_man_down_there_unless_it_has_to_be_on_foot(tmp_path):
    objective = {"stations": ["Alpha"], "of": "034 030", "within_m": 80}
    b = Battle(tmp_path, success=objective)
    b.start()
    here = {"group": "Alpha", "side": "WEST", "able": 3, "mounted": 0, "pos": [3450, 3050],
            "units": [[3450, 3050, 0]] * 3}
    truth(b, 110, {**here, "down": [[3000, 3050]]})
    assert met(b) == []
    truth(b, 112, {**here, "down": [[3460, 3050]]})
    assert met(b) == ["Alpha is at grid 034 030"]


def test_higher_command_looks_again_before_saying_so(tmp_path):
    """A man going down in the seconds before the word was given still got "all six on foot"."""
    b = marching(tmp_path)
    truth(b, 110, team("Alpha"), team("Bravo"))
    assert met(b) == ["Alpha and Bravo are on foot at grid 052 044"]
    truth(b, 115, team("Alpha"), {**team("Bravo"), "down": [[5250, 4450]]})
    assert met(b) == []
    b.advance(125)
    assert not b.runtime.ended


def test_a_march_ends_with_both_teams_on_foot_at_the_grid(tmp_path):
    b = marching(tmp_path)
    truth(b, 110, team("Alpha"), team("Bravo", x=5290, y=4470))
    assert met(b) == ["Alpha and Bravo are on foot at grid 052 044"]
    b.advance(125)
    assert b.runtime.ended == "Objective achieved: Alpha and Bravo are on foot at grid 052 044."


TWO_TASKS = [{"id": "T1", "text": "Get Alpha to the bridge.",
              "success": {"station": "Alpha", "within_m": 50, "of": "034 030"}},
             {"id": "T2", "text": "Clear the enemy.", "success": {"enemy_cleared": True}}]
EAST = [{"id": "East", "at": "060 060", "units": 4}]


def two_tasks(tmp_path) -> Battle:
    raw = {"objectives": TWO_TASKS, "enemies": EAST, "success": None}
    b = Battle(tmp_path, **raw)
    b.start()
    return b


def alpha_at(x=3450, y=3050) -> dict:
    return {"group": "Alpha", "side": "WEST", "able": 4, "pos": [x, y], "units": [[x, y, 0]] * 4}


def enemy(alive) -> dict:
    return {"group": "East", "side": "EAST", "able": alive, "pos": [6050, 6050], "units": []}


def test_an_objective_done_is_its_own_event_and_the_battle_goes_on(tmp_path):
    b = two_tasks(tmp_path)
    b.runtime.end_turn("x", messages_only=True)
    truth(b, 110, alpha_at(), enemy(4))
    b.wall = 1000
    b.advance(125)
    text = "\n".join(wake[0] for wake in b.wakes)
    assert "OBJECTIVE COMPLETE: Get Alpha to the bridge." in text and "MISSION END" not in text
    assert "Higher command confirms that Alpha reached grid 034 030. This is certain" in text
    assert not b.runtime.ended and list(b.runtime.objectives_done) == ["T1"]
    assert b.records.read("radio_events")[-1]["objective_complete"] == "T1"


def test_the_briefing_shows_whats_done_and_whats_left(tmp_path):
    b = two_tasks(tmp_path)
    truth(b, 110, alpha_at(), enemy(4))
    b.advance(125)
    brief = b.runtime.briefing()
    assert "OBJECTIVES, 04:35 left" in brief and "Done: Get Alpha to the bridge.\nClear the enemy." in brief
    assert b.runtime.mission()["objectives"] == [{"text": "Get Alpha to the bridge.", "done": True},
                                                 {"text": "Clear the enemy.", "done": False}]


def test_the_mission_ends_only_when_all_are_done(tmp_path):
    b = two_tasks(tmp_path)
    b.runtime.end_turn("x", messages_only=True)
    truth(b, 110, alpha_at(), enemy(4))
    b.advance(125)
    assert not b.runtime.ended
    truth(b, 130, alpha_at(3000, 3000), enemy(0))
    b.advance(145)
    assert b.runtime.ended == "Objective achieved: all objectives are complete."
    assert "OBJECTIVE COMPLETE: Clear the enemy." in "\n".join(wake[0] for wake in b.wakes)


def test_a_done_objective_stays_done_if_they_leave(tmp_path):
    b = two_tasks(tmp_path)
    truth(b, 110, alpha_at(), enemy(4))
    b.advance(125)
    truth(b, 130, alpha_at(3000, 3000), enemy(4))
    b.advance(150)
    assert list(b.runtime.objectives_done) == ["T1"]


def test_running_out_of_time_says_how_far_it_got(tmp_path):
    b = two_tasks(tmp_path)
    truth(b, 110, alpha_at(), enemy(4))
    b.advance(125)
    b.silent(100 + 301)
    assert b.runtime.ended == "Time limit reached. 1 of 2 objectives complete."


def test_objectives_survive_a_restart_of_the_host(tmp_path):
    b = two_tasks(tmp_path)
    truth(b, 110, alpha_at(), enemy(4))
    b.runtime.save()
    b.runtime = b.new_runtime()
    b.advance(125)
    assert list(b.runtime.objectives_done) == ["T1"]


def test_one_objective_gets_both_events_in_one_wake(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.runtime.end_turn("x", messages_only=True)
    truth(b, 110, alpha_at())
    b.advance(125)
    text = "\n".join(wake[0] for wake in b.wakes)
    assert "OBJECTIVE COMPLETE: Get Alpha to B." in text and "MISSION END. Objective achieved: Alpha reached" in text
    assert text.index("OBJECTIVE COMPLETE") < text.index("MISSION END")


@pytest.mark.parametrize("raw, words", [
    ({"objectives": [{"text": "No id"}]}, "needs an id"),
    ({"objectives": [{"id": "T1"}]}, "needs an id"),
    ({"objectives": [{"id": "T1", "text": "a"}, {"id": "T1", "text": "b"}]}, "unique"),
    ({"objectives": [{"id": "T1", "text": "a", "success": {"dance": True}}]}, "unknown success"),
    ({"objectives": [{"id": "T1", "text": "a"}], "success": {"enemy_cleared": True}}, "not both"),
])
def test_bad_objectives_are_refused(raw, words):
    base = {"name": "t", "mission": "m", "text": "x", "time_limit": "5:00", "stations": []}
    with pytest.raises(ValueError, match=words):
        scenario.build({**base, **raw})


def test_two_calls_against_different_enemies_say_so(tmp_path):
    """What misled the first commander to use this: the patrol died, and the next call was from someone else."""
    b = spotting(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [{"type": "FIRE_MISSION", "at": "030 030", "observer": "Alpha"}]})
    land(b, 110, pos=(3150, 3240), order="O-0001", seen=True)
    b.advance(115, order="O-0001", contacts=[contact(3120, 3200)])
    land(b, 130, pos=(3150, 3240), order="O-0001", seen=True)
    b.advance(135, order="O-0001", contacts=[contact(2950, 3400)])
    b.advance(200, order="O-0001")  # it's in contact, so its reports take a while
    said = [words for words in latest(b) if words.startswith("Splash")]
    assert "of the enemy at bearing 025." in said[0] and "of the enemy at bearing 345." in said[1]


def test_every_briefing_says_what_the_objective_is_and_how_long_is_left(tmp_path):
    b = Battle(tmp_path, objective="Get Alpha to B.", text="A long story about Alpha and how it got here.")
    b.start()
    b.advance(100 + 60)
    text = b.runtime.briefing()
    assert "OBJECTIVE, 04:00 left\nGet Alpha to B." in text and "long story" not in text


def test_the_objective_falls_back_to_the_mission_text(tmp_path):
    b = Battle(tmp_path)
    b.start()
    assert "\nGet Alpha to B.\n" in b.runtime.briefing()


def test_no_objective_is_left_once_its_over(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.runtime._end("Done.")
    assert "OBJECTIVE" not in b.runtime.briefing()


def walking(tracker, t, y, speed=0.0, leader="Sam Reed"):
    fields = packet(pos=[3050, y], speed=speed, leader=leader)
    fields["t"] = t
    tracker.note_movement(fields)
    return fields


def test_a_squad_going_in_stops_and_starts_is_moving_though_paused_right_now():
    """Alpha walked 400 m like this, saying "stationary" each time, and the commander reissued the order three times."""
    tracker = Tracker()
    for t, y in ((100, 4000), (106, 3995), (112, 3990), (118, 3985)):
        now = walking(tracker, t, y)
    assert now["under_way"] and reports.answer(now, None, ["position"]) == "Grid 030 030, moving south."


def test_a_halted_squad_is_stationary_however_it_got_there():
    """It said "moving east" for half a minute after "Halted", from the walk before the halt."""
    tracker = Tracker()
    for t, y in ((100, 4000), (106, 3990), (112, 3980)):
        walking(tracker, t, y)
    fields = packet(pos=[3050, 3980], speed=0.0, leader="Sam Reed")
    fields["t"] = 118
    tracker.note_movement(fields, {"kind": "halt", "legs": []})
    assert not fields["under_way"] and reports.answer(fields, None, ["position"]) == "Grid 030 030, stationary."


def test_soldiers_shuffling_about_are_stationary():
    tracker = Tracker()
    for t, y in ((100, 4000), (110, 4006), (120, 3998), (130, 4005)):
        now = walking(tracker, t, y)
    assert not now["under_way"] and reports.answer(now, None, ["position"]) == "Grid 030 030, stationary."


def test_a_squad_that_has_stopped_soon_says_so():
    tracker = Tracker()
    walking(tracker, 100, 4000)
    walking(tracker, 110, 3950)
    assert walking(tracker, 120, 3950)["under_way"]
    assert not walking(tracker, 145, 3950)["under_way"]


def test_a_new_leader_elsewhere_isnt_the_squad_moving():
    tracker = Tracker()
    walking(tracker, 100, 4000)
    assert not walking(tracker, 106, 3950, leader="Someone Else")["under_way"]


def test_the_trail_survives_a_restart_of_the_host(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.advance(102, pos=[3050, 3050])
    b.runtime.save()
    b.runtime = b.new_runtime()
    b.advance(106, pos=[3050, 3000], speed=0)
    assert "moving south" in b.runtime.ask("Alpha", ["position"])["replies"][0]["text"]


def test_a_leader_hit_in_the_legs_says_why_the_squad_is_slow():
    tracker = Tracker()
    fields = packet(limping=["Sam Reed"], leader="Sam Reed", order="")
    said = tracker.update(fields, None, 100)
    assert [(r.precedence, r.text) for r in said] == [(reports.PRIORITY, "Slow going, Sam Reed's hit in the legs.")]
    assert tracker.update(fields, None, 102) == []  # and says so once


def test_anyone_else_hit_in_the_legs_is_mentioned():
    tracker = Tracker()
    said = tracker.update(packet(limping=["Ann Cole"], leader="Sam Reed", order=""), None, 100)
    assert [(r.precedence, r.text) for r in said] == [(reports.ROUTINE, "Ann Cole's hit in the legs.")]


def test_being_hit_again_after_being_treated_is_news():
    tracker = Tracker()
    tracker.update(packet(limping=["Ann Cole"], leader="Sam Reed", order=""), None, 100)
    assert tracker.update(packet(limping=[], leader="Sam Reed", order=""), None, 102) == []
    said = tracker.update(packet(limping=["Ann Cole"], leader="Sam Reed", order=""), None, 104)
    assert [r.text for r in said] == ["Ann Cole's hit in the legs."]


def test_asking_for_strength_names_who_cant_walk():
    answer = reports.answer(packet(wounded=2, limping=["Sam Reed", "Ann Cole"]), None, ["strength"])
    assert answer.startswith("4 of 4 effective, 2 wounded. Sam Reed and Ann Cole hit in the legs. ")
    assert "legs" not in reports.answer(packet(wounded=1), None, ["strength"])


def test_a_limp_reaches_the_radio_through_the_runtime(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.advance(102, limping=["Sam Reed"], leader="Sam Reed")
    assert "Slow going, Sam Reed's hit in the legs." in radio_words(b)


CARE_LIST = {"V1": {"id": "V1", "key": "V1"}, "A1": {"id": "A1", "key": "P1"}}
HURT = {"C1": {"id": "C1", "key": "m7", "name": "Sam Reed", "pos": [4100, 4100]},
        "C2": {"id": "C2", "key": "m8", "name": "Ann Cole", "pos": [4110, 4100]}}
CARERS = {"Alpha": {"capabilities": ["CARRY", "UNLOAD", "TREAT", "AID_POST", "MOVE"]},
          "Bravo": {"capabilities": ["MOVE"]}}


def care(kind="CARRY", to="Alpha", **leg) -> dict:
    request = {"to": to, "legs": [{"type": kind, **leg}]}
    return orders.validate(request, CARERS, MARKERS, 8192, BUILDINGS, CARE_LIST, HURT)


def test_carry_to_a_vehicle_or_a_place_or_a_post():
    to_truck = care(casualties=["C1", "C2"], vehicle="V1")
    assert to_truck["mode"] == "carry"
    assert to_truck["engine_legs"] == [[[["m7", [4100, 4100]], ["m8", [4110, 4100]]], "V1"]]
    assert to_truck["words"] == "Copy, carrying Sam Reed and Ann Cole to V1."
    to_grid = care(casualties=["C1"], at="041 041")
    assert to_grid["engine_legs"] == [[[["m7", [4100, 4100]]], [4150.0, 4150.0, 0]]]
    assert care(at="A1")["engine_legs"] == [[[], "P1"]]
    assert care(at="A1")["words"] == "Copy, carrying our casualties to A1."


@pytest.mark.parametrize("kind, leg, words", [
    ("CARRY", {}, "CARRY needs"),
    ("CARRY", {"casualties": ["C9"], "vehicle": "V1"}, "aren't"),
    ("CARRY", {"casualties": "C1", "vehicle": "V1"}, "list of ids"),
    ("CARRY", {"vehicle": "V9"}, "isn't on it"),
    ("UNLOAD", {}, "isn't on it"),
    ("TREAT", {"casualties": ["C9"]}, "aren't"),
    ("AID_POST", {}, "needs at"),
])
def test_bad_orders_about_the_wounded_are_refused(kind, leg, words):
    with pytest.raises(Invalid, match=words):
        care(kind, **leg)


def test_unload_treat_and_post():
    assert care("UNLOAD", vehicle="V1")["engine_legs"] == [[[], "V1"]]
    assert care("UNLOAD", vehicle="V1", casualties=["C2"])["words"] == "Copy, getting Ann Cole off V1."
    assert care("TREAT", casualties=["C1"])["engine_legs"] == [[[["m7", [4100, 4100]]]]]
    assert care("TREAT")["words"] == "Copy, treating our casualties."
    post = care("AID_POST", at="041 041")
    assert post["mode"] == "post" and post["engine_legs"] == [[[4150.0, 4150.0, 0]]]
    assert post["words"] == "Copy, setting up an aid post at grid 041 041."


def test_they_need_the_capability():
    with pytest.raises(Invalid, match="can't do CARRY"):
        care(to="Bravo", vehicle="V1")


def down_row(key="m7", name="Sam Reed", x=3080, y=3050, vehicle="", aboard=False, own=True, handled=""):
    return [key, name, x, y, vehicle, aboard, own, handled]


def wounded_battle(tmp_path, **raw) -> Battle:
    capabilities = ["MOVE", "CARRY", "UNLOAD", "TREAT", "AID_POST"]
    station = {"callsign": "Alpha", "role": "x", "capabilities": capabilities, "at": "030 030"}
    b = Battle(tmp_path, stations=[station], **raw)
    b.start()
    b.runtime.end_turn("x", messages_only=True)
    return b


def said(b) -> list[str]:
    return [row["text"] for row in b.records.read("radio") if row["from"] != "HQ"]


def test_a_man_going_down_is_reported_and_listed_once(tmp_path):
    b = wounded_battle(tmp_path)
    b.advance(102, casualties=[down_row()], able=3)
    b.advance(104, casualties=[down_row()], able=3)
    assert said(b).count("Sam Reed's down, grid 030 030. Listed as C1.") == 1
    assert "C1  Sam Reed  Alpha's  grid 030 030" in b.runtime.briefing()


def test_going_down_in_a_fight_gives_no_grid(tmp_path):
    b = wounded_battle(tmp_path)
    b.advance(102, casualties=[down_row()], contacts=[contact()], suppression=0.5)
    b.advance(200)
    assert "Sam Reed's down. Listed as C1." in said(b)


def test_getting_up_and_dying_are_different(tmp_path):
    b = wounded_battle(tmp_path)
    b.advance(102, casualties=[down_row(), down_row("m8", "Ann Cole", 3090)])
    b.advance(104, casualties=[down_row("m8", "Ann Cole", 3090)], up=["m7"])
    assert "Sam Reed's back on their feet." in said(b)
    b.advance(106, casualties=[])
    assert "Ann Cole's dead." in said(b)
    assert "CASUALTIES" not in b.runtime.briefing()


def test_going_down_again_is_news(tmp_path):
    b = wounded_battle(tmp_path)
    b.advance(102, casualties=[down_row()])
    b.advance(104, casualties=[], up=["m7"])
    b.advance(106, casualties=[down_row()])
    assert said(b).count("Sam Reed's down, grid 030 030. Listed as C1.") == 2  # the same man keeps his id


def test_leaving_a_man_behind_is_said_and_then_nothing_is_known(tmp_path):
    b = wounded_battle(tmp_path)
    b.advance(102, casualties=[down_row()])
    b.advance(150, casualties=[down_row()], pos=[3050, 3300])
    assert "We've left Sam Reed, about 250 m south of us." in said(b)
    b.advance(152, casualties=[], pos=[3050, 3300])
    assert "Sam Reed's dead." not in said(b)  # it isn't there to see


def test_a_man_on_the_truck_with_them_isnt_left_behind(tmp_path):
    b = wounded_battle(tmp_path, vehicles=[{"id": "V1", "class": "x", "at": "030 030"}])
    b.runtime.vehicles = {"V1": {"id": "V1", "key": "V1", "name": "Truck", "at": "030 030", "t": None,
                                 "wrecked": False}}
    b.advance(102, casualties=[down_row(vehicle="V1", aboard=True, x=5000)])
    assert not [words for words in said(b) if "left" in words]
    assert b.runtime.ask("Alpha", ["casualties"])["replies"][0]["text"] == "C1 Sam Reed, down, on V1."


def test_someone_elses_man_is_found_only_if_nobody_had_listed_him(tmp_path):
    b = wounded_battle(tmp_path)
    b.advance(102, casualties=[down_row(own=False)])
    assert "Found Sam Reed down, grid 030 030. Listed as C1." in said(b)
    b.advance(104, casualties=[down_row(own=False)])
    assert said(b).count("Found Sam Reed down, grid 030 030. Listed as C1.") == 1


def test_strength_and_the_casualties_topic(tmp_path):
    answer = reports.answer(packet(able=2, wounded=1, casualties=[
        {"id": "C1", "name": "Sam Reed", "dx": 40, "dy": 0, "grid": "030 030", "vehicle": "", "own": True, "new": False,
         "handled": ""},
        {"id": "C2", "name": "Ann Cole", "dx": 2, "dy": 0, "grid": "030 030", "vehicle": "", "own": False, "new": False,
         "handled": ""}]), None, ["strength", "casualties"])
    assert answer.startswith("2 of 4 effective, 1 down, 1 wounded.")
    assert "C1 Sam Reed, down, about 40 m east. C2 Ann Cole, down, right here." in answer
    assert reports.answer(packet(), None, ["casualties"]) == "No casualties."
    assert "casualties" not in reports.answer(packet(), None).lower()


def test_orders_use_the_commanders_list_and_leave_the_route_alone(tmp_path):
    b = wounded_battle(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOVE", "at": "034 030"}]})
    route = b.runtime.routes["Alpha"]["legs"]
    b.advance(102, casualties=[down_row()], order="O-0001")
    b.runtime.order({"to": "Alpha", "legs": [{"type": "CARRY", "casualties": ["C1"], "at": "035 030"}]})
    assert b.game.calls[-1][1][:4] == ["Alpha", "O-0002", "carry", [[[["m7", [3080, 3050]]], [3550.0, 3050.0, 0]]]]
    assert b.runtime.routes["Alpha"]["legs"] == route
    b.advance(104, casualties=[down_row()], order="O-0002")
    assert "Copy, carrying Sam Reed to grid 035 030. That's 500 m carrying them, about 5 minutes." in said(b)
    with pytest.raises(Invalid, match="aren't"):
        b.runtime.order({"to": "Alpha", "legs": [{"type": "CARRY", "casualties": ["C2"], "at": "035 030"}]})


@pytest.mark.parametrize("kind, state, detail, words", [
    ("carry", "carrying", "", "Got Sam Reed, on the way."),
    ("carry", "loaded", "", "Sam Reed's loaded."),
    ("carry", "he died", "", "Sam Reed's dead."),
    ("carry", "medic down", "", "Lost the man carrying Sam Reed."),
    ("carry", "aboard", "V1", "Sam Reed's on V1. Get them off first."),
    ("unload", "off", "V1", "Sam Reed's off V1."),
    ("unload", "moving", "V1", "V1 has to stop first."),
    ("treat", "treating", "", "Treating Sam Reed."),
    ("treat", "up", "", "Sam Reed's back up."),
    ("treat", "no medic", "", "Unable, no medic here."),
    ("treat", "can't find", "", "Can't find Sam Reed."),
    ("post", "have one", "", "Unable, we've already got a post up."),
])
def test_how_each_part_of_it_sounds(tmp_path, kind, state, detail, words):
    b = wounded_battle(tmp_path)
    b.runtime.vehicles = {"V1": {"id": "V1", "key": "K1", "name": "Truck", "at": "030 030", "t": None,
                                 "wrecked": False}}
    row = ["O-1", kind, "m7", "Sam Reed", state, "K1" if detail else ""]
    b.advance(102, medical=[row])
    b.advance(104, medical=[row])
    assert said(b).count(words) == 1


def test_a_post_going_up_joins_the_list(tmp_path):
    b = wounded_battle(tmp_path)
    b.advance(102, medical=[["O-1", "post", "post", "", "up", ["P1", "040060"]]])
    assert "Aid post up, grid 040 060. Listed as A1." in said(b)
    assert b.runtime.vehicles["A1"]["key"] == "P1"
    b.runtime.order({"to": "Alpha", "legs": [{"type": "CARRY", "at": "A1"}]})
    assert b.game.calls[-1][1][3] == [[[], "P1"]]


def test_the_downed_dont_count_as_enemy_or_block_the_end(tmp_path):
    b = Battle(tmp_path, success={"enemy_cleared": True}, enemies=[{"id": "East", "at": "060 060", "units": 2}])
    b.start()
    truth(b, 110, {"group": "East", "side": "EAST", "able": 0, "pos": [], "units": [], "down": [[6050, 6050]]})
    assert met(b) == ["the enemy has been cleared"]


def test_a_scenario_can_put_men_down_at_a_set_time(tmp_path):
    b = Battle(tmp_path, events=[{"at": "0:20", "action": "knock_down", "station": "Alpha", "count": 2}])
    b.start()
    b.silent(100 + 21)
    assert b.game.calls[-1][1] == ["Alpha", 2] and "knockDown" in b.game.calls[-1][0]


def test_a_medical_scenario_loads():
    raw = yaml.safe_load((Path(__file__).parents[2] / "scenarios/commander/casevac_rv.yaml").read_text())
    built = scenario.build(raw)
    assert built.mission == "commander_ace" and built.stations["Angel"]["medics"] == 2
    assert built.medical["facility_s"] == 10 and built.objectives[0]["success"]["on_foot"]


def said_for(route_legs, **fields) -> str:
    tracker = Tracker()
    route = {"kind": "route", "legs": route_legs}
    tracker.update(packet(order="", **fields), None, 90)
    reports_said = tracker.update(packet(order="O-1", **fields), route, 100)
    return reports_said[0].text


def leg_to(x, y=3050, kind="MOVE"):
    return {"type": kind, "pos": [x, y], "grid": f"{x // 100:03d} {y // 100:03d}", "completion": 0}


@pytest.mark.parametrize("metres, words", [
    (50, "Copy, moving to grid 031 030."),  # too near to bother
    (150, "That's 200 m on foot, under a minute."),
    (300, "That's 300 m on foot, about a minute."),
    (420, "That's 400 m on foot, about 2 minutes."),
    (2100, "That's 2 km on foot, about 9 minutes."),
    (5250, "That's 5 km on foot, about 20 minutes."),
])
def test_a_move_says_how_far_and_how_long(metres, words):
    assert words in said_for([leg_to(3050 + metres)])


def test_a_long_route_is_the_whole_of_it():
    words = said_for([leg_to(3550), leg_to(3550, 3550), leg_to(3050, 3550)])
    assert "That's 1.5 km on foot, about 6 minutes." in words


def test_a_squad_in_a_vehicle_gives_a_drive():
    rows = [["V1", "driver", "Ann Cole", False], ["V1", "cargo", "Sam Reed", False]]
    words = said_for([leg_to(5050)], mounted=rows, leader="Sam Reed")
    assert "That's 2 km by vehicle, about 2 minutes." in words


def test_a_squad_still_climbing_in_gives_a_drive():
    assert "That's 2 km by vehicle, about 2 minutes." in said_for([leg_to(5050)], mount=["V1", "going", "", []])


def test_one_man_sent_to_a_seat_leaves_the_squad_on_foot():
    assert "on foot" in said_for([leg_to(5050)], mount=["V1", "going", "gunner", []])


def test_a_man_on_a_gun_isnt_a_squad_in_a_vehicle():
    words = said_for([leg_to(5050)], mounted=[["V1", "gunner", "Sam Reed", True]], leader="Sam Reed")
    assert "on foot" in words


def test_a_leader_hit_in_the_legs_says_it_will_be_slow():
    words = said_for([leg_to(3550)], limping=["Sam Reed"], leader="Sam Reed")
    assert "That's 500 m on foot, with Sam Reed hit in the legs, about 8 minutes." in words


def test_under_fire_is_only_a_lower_bound():
    words = said_for([leg_to(5050)], contacts=[contact()], suppression=0.5)
    assert "At least 8 minutes on foot, under fire." in words and "That's" not in words
    assert "030 030" not in words.split("grid 050 030.")[1]


@pytest.mark.parametrize("behaviour, speed, minutes", [
    ("AWARE", "NORMAL", 8),
    ("AWARE", "FULL", 8),  # really no faster
    ("AWARE", "LIMITED", 25),
    ("SAFE", "NORMAL", 20),
    ("COMBAT", "NORMAL", 20),
    ("STEALTH", "NORMAL", 35),
])
def test_how_it_moves_changes_the_estimate(behaviour, speed, minutes):
    words = said_for([leg_to(5050)], behaviour=behaviour, speed_mode=speed)
    assert f"That's 2 km on foot, about {minutes} minutes." in words


def test_asked_how_long_it_says_the_same(tmp_path):
    trip = {"kind": "route", "legs": [leg_to(5050)]}
    fields = {"pos": [3050.0, 3050.0], "order": "O-1", "leg": 0, "legs": 1}
    assert reports.answer(packet(**fields), trip, ["eta"]) == "About 8 minutes to grid 050 030, if unopposed."
    assert reports.answer(packet(behaviour="SAFE", **fields), trip, ["eta"]) == \
        "About 20 minutes to grid 050 030, if unopposed."


def test_a_long_way_off_isnt_distant(tmp_path):
    trip = {"kind": "route", "legs": [leg_to(5050)]}
    assert reports.answer(packet(), trip, ["task"]) == "Moving to grid 050 030, about 2 km out."


def test_an_order_that_sets_how_it_moves_is_estimated_by_that(tmp_path):
    b = wounded_battle(tmp_path, medical={"build_s": 60})
    b.advance(102)
    b.runtime.order({"to": "Alpha", "behaviour": "STEALTH", "legs": [{"type": "AID_POST", "at": "040 030"}]})
    b.advance(104, order="O-0001")
    assert "That's 1 km on foot, about 17 minutes." in " ".join(said(b))


@pytest.mark.parametrize("kind, state, words", [
    ("carry", "put down", "Put Sam Reed down."),
    ("carry", "left", "Leaving Sam Reed where they are."),
    ("treat", "called off", "Stopped treating Sam Reed."),
    ("post", "called off", "Stopped setting up the aid post."),
])
def test_a_squad_says_what_a_new_order_called_off(kind, state, words):
    rows = [["O-1", kind, "m7", "Sam Reed", state, "", ""]]
    assert [r.text for r in Tracker()._care(packet(medical=rows))] == [words]


def test_the_commander_is_told_the_newest_order_wins():
    assert "the newest order wins" in ORDER_TYPES_HELP
    assert "order the squad first and these second" in ORDER_TYPES_HELP
    assert "An order takes the men it needs." in DOCTRINE and "How far to trust what you hear" in DOCTRINE


def test_the_speed_setting_gets_as_far_as_the_estimate(tmp_path):
    """It was dropped on the way in, so LIMITED and FULL changed nothing, and STEALTH's 1 m/s at both hid that."""
    b = Battle(tmp_path)
    b.start()
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOVE", "at": "050 030"}], "speed": "LIMITED"})
    b.advance(102, order="O-0001", speed_mode="LIMITED")
    assert any("That's 2 km on foot, about 25 minutes." in line for line in said(b)), said(b)


def owen(dx=-300, dy=0, busy=False):
    return ["Owen King", dx, dy, busy]


def test_a_full_count_says_who_isnt_there():
    words = reports.answer(packet(spread=[owen(), ["Cal Roy", -20, 0, False]]), None, ["strength"])
    assert "Not with us: Owen King, about 300 m west." in words and "Cal Roy" not in words


def test_several_men_apart_are_each_named():
    words = reports.answer(packet(spread=[owen(), ["Cal Roy", 0, 250, False]]), None, ["strength"])
    assert "Not with us: Owen King, about 300 m west, and Cal Roy, about 250 m north." in words


def test_arriving_says_who_hasnt_yet():
    tracker, trip = Tracker(), route(("MOVE", (3450, 3050), "034 030"))
    tracker.update(packet(order="O-1"), trip, 10)
    arrived = tracker.update(packet(order="O-1", pos=[3450, 3050], grid="034030", leg=1, spread=[owen()]), trip, 14)
    assert [r.text for r in arrived] == ["Arrived, grid 034 030. Not with us: Owen King, about 300 m west."]


def apart_said(tracker, now, **fields):
    return [r.text for r in tracker.update(packet(**fields), None, now)]


def test_someone_who_stays_apart_is_reported_and_so_is_their_return():
    tracker = Tracker()
    assert apart_said(tracker, 10, spread=[owen()]) == []  # strung out for a moment isn't news
    assert apart_said(tracker, 39, spread=[owen()]) == []
    assert apart_said(tracker, 40, spread=[owen()]) == ["Owen King's away from the squad, about 300 m west of us."]
    assert apart_said(tracker, 50, spread=[owen()]) == []
    assert apart_said(tracker, 60, spread=[owen(-70)]) == []  # closing, but not with them yet
    assert apart_said(tracker, 70, spread=[owen(-40)]) == ["Owen King's back with the squad."]
    assert apart_said(tracker, 80, spread=[owen(-40)]) == []


def test_a_brief_straggler_is_never_mentioned():
    tracker = Tracker()
    assert apart_said(tracker, 10, spread=[owen()]) == []
    assert apart_said(tracker, 20, spread=[owen(-40)]) == []
    assert tracker.apart == {}


def test_a_man_sent_on_a_job_isnt_news_until_its_done():
    tracker = Tracker()
    assert apart_said(tracker, 10, spread=[owen(busy=True)]) == []
    assert apart_said(tracker, 100, spread=[owen(busy=True)]) == []
    assert apart_said(tracker, 110, spread=[owen()]) == []
    assert apart_said(tracker, 140, spread=[owen()]) == ["Owen King's away from the squad, about 300 m west of us."]


def test_an_order_that_spreads_them_out_isnt_news():
    tracker = Tracker()
    garrison = route(("DEFEND", (3050, 3050), "030 030"))
    tracker.update(packet(order="O-1"), garrison, 0)
    assert [r.text for r in tracker.update(packet(order="O-1", spread=[owen()]), garrison, 10)] == []
    assert [r.text for r in tracker.update(packet(order="O-1", spread=[owen()]), garrison, 100)] == []


def test_someone_gone_from_the_list_isnt_said_to_be_back():
    tracker = Tracker()
    apart_said(tracker, 10, spread=[owen()])
    apart_said(tracker, 40, spread=[owen()])
    assert apart_said(tracker, 50, spread=[]) == []  # down, or in a vehicle
    assert tracker.apart == {}


def test_getting_up_a_long_way_off_says_so_once(tmp_path):
    b = wounded_battle(tmp_path)
    b.advance(102, casualties=[down_row(x=3050, y=3050)])
    b.advance(104, up=["m7"], casualties=[], spread=[["Sam Reed", -300, 0, False]])
    assert "Sam Reed's back on their feet, about 300 m west of us." in said(b)
    b.advance(160, spread=[["Sam Reed", -300, 0, False]])
    assert not any("away from the squad" in line for line in said(b))
    b.advance(170, spread=[["Sam Reed", -30, 0, False]])
    assert "Sam Reed's back with the squad." in said(b)


def test_carrying_says_so_in_the_order_itself():
    assert "A man carrying walks about 100 m a minute, doesn't take cover and can't shoot back" in ORDER_TYPES_HELP


def test_appended_legs_are_estimated_too(tmp_path):
    b = Battle(tmp_path)
    b.start()
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOVE", "at": "050 030"}]})
    b.advance(102, order="O-0001")
    b.runtime.order({"to": "Alpha", "mode": "append", "legs": [{"type": "MOVE", "at": "070 030"}]})
    b.advance(104, order="O-0002")
    assert "Copy, then moving to grid 070 030. That's 4 km on foot, about 16 minutes." in said(b)


def test_medics_say_theyll_wait_for_a_man_on_a_truck():
    """Sonnet took "Get them off first" as sorted once he was off, and waited 80 s for a treatment nobody was doing."""
    rows = [["O-1", "treat", "m7", "Sam Reed", "aboard", "V1", ""]]
    assert [r.text for r in Tracker()._care(packet(medical=rows))] == [
        "Sam Reed's on V1, which isn't a medical vehicle. We'll treat them when they're off."]


def test_a_squad_already_on_the_truck_doesnt_walk_to_where_it_used_to_be(tmp_path):
    """Sonnet's squad, sitting in V1, was told 2 km on foot, because that's where the commander's list last had it."""
    b = wounded_battle(tmp_path)
    b.runtime.vehicles = {"V1": {"id": "V1", "key": "V1", "name": "Truck", "at": "040 030", "t": None,
                                 "wrecked": False}}
    b.scenario.stations["Alpha"]["capabilities"].append("MOUNT")
    b.advance(102, order="")
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOUNT", "vehicle": "V1"}]})
    b.advance(104, order="O-0001", mounted=[["V1", "driver", "Ann Cole", False]])
    assert "Copy, mounting V1." in said(b)


def test_boarding_says_how_far_the_vehicle_is(tmp_path):
    b = wounded_battle(tmp_path)
    b.runtime.vehicles = {"V1": {"id": "V1", "key": "V1", "name": "Truck", "at": "040 030", "t": None,
                                 "wrecked": False}}
    b.scenario.stations["Alpha"]["capabilities"].append("MOUNT")
    b.advance(102, order="")
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOUNT", "vehicle": "V1"}]})
    b.advance(104, order="O-0001")
    assert "Copy, mounting V1. That's 1 km on foot, about 4 minutes." in said(b)


def test_carrying_says_how_long_that_really_is(tmp_path):
    """Haiku, told nothing, had two men carried 2 km and expected them there in 90 s. It's 20 minutes."""
    b = wounded_battle(tmp_path)
    b.advance(102, casualties=[down_row(x=6050, y=6050)], pos=[6050, 6050])
    b.runtime.order({"to": "Alpha", "legs": [{"type": "CARRY", "casualties": ["C1"], "at": "040 060"}]})
    b.advance(104, casualties=[down_row(x=6050, y=6050)], pos=[6050, 6050], order="O-0001")
    assert "Copy, carrying Sam Reed to grid 040 060. That's 2 km carrying them, about 20 minutes." in said(b)


def test_carrying_to_a_vehicle_alongside_is_quick(tmp_path):
    b = wounded_battle(tmp_path)
    b.runtime.vehicles = {"V1": {"id": "V1", "key": "V1", "name": "Truck", "at": "031 030", "t": None,
                                 "wrecked": False}}
    b.advance(102, casualties=[down_row(x=3050, y=3050)])
    b.runtime.order({"to": "Alpha", "legs": [{"type": "CARRY", "casualties": ["C1"], "vehicle": "V1"}]})
    b.advance(104, casualties=[down_row(x=3050, y=3050)], order="O-0001")
    assert "Copy, carrying Sam Reed to V1. That's 100 m carrying them, about a minute." in said(b)


def test_medics_say_how_far_off_they_are(tmp_path):
    b = wounded_battle(tmp_path)
    b.advance(102, casualties=[down_row(x=3050, y=4050)])
    b.runtime.order({"to": "Alpha", "legs": [{"type": "TREAT", "casualties": ["C1"]}]})
    b.advance(104, casualties=[down_row(x=3050, y=4050)], order="O-0001")
    assert "Copy, treating Sam Reed. That's 1 km on foot to reach them, about 4 minutes." in said(b)


def test_a_post_says_how_long_to_get_there_and_set_up(tmp_path):
    b = wounded_battle(tmp_path, medical={"build_s": 60})
    b.advance(102)
    b.runtime.order({"to": "Alpha", "legs": [{"type": "AID_POST", "at": "040 030"}]})
    b.advance(104, order="O-0001")
    assert ("Copy, setting up an aid post at grid 040 030. That's 1 km on foot, about 4 minutes. "
            "Then about a minute to set up.") in said(b)


# -- whole tasks in one order -----------------------------------------------------------------------------

def chained(tmp_path, **raw) -> Battle:
    capabilities = ["MOVE", "HOLD", "HALT", "POSTURE", "MOUNT", "DISMOUNT", "CARRY", "UNLOAD", "TREAT", "DEFEND",
                    "FIRE_MISSION", "SENTRY", "PATROL"]
    b = Battle(tmp_path, stations=[{"callsign": "Alpha", "role": "x", "capabilities": capabilities, "at": "030 030"}],
               **raw)
    b.runtime.vehicles = {"V1": {"id": "V1", "key": "V1", "name": "Truck", "at": "031 030", "t": None,
                                 "wrecked": False}}
    b.start()
    b.runtime.end_turn("x", messages_only=True)
    b.advance(101, order="")
    return b


def sent(b) -> list[str]:
    return [row["request"]["legs"][0]["type"] for row in b.records.read("orders")]


MOUNT, DISMOUNT = {"type": "MOUNT", "vehicle": "V1"}, {"type": "DISMOUNT"}
DRIVE = {"type": "MOVE", "at": "050 030"}
RIDING = [["V1", "cargo", "Sam Reed", False]]


def test_a_chain_sends_only_its_first_step_and_says_the_whole_of_it(tmp_path):
    b = chained(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [MOUNT, DRIVE, DISMOUNT]})
    assert sent(b) == ["MOUNT"]
    b.advance(102, order="O-0001", mount=["V1", "going", "", []])
    assert "Copy, mounting V1, then moving to grid 050 030, then getting off. About 2 minutes in all." in said(b)
    assert sent(b) == ["MOUNT"]


def test_each_step_starts_when_the_last_has_really_finished(tmp_path):
    b = chained(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [MOUNT, DRIVE, DISMOUNT]})
    b.advance(102, order="O-0001", mount=["V1", "going", "", []])
    b.advance(104, order="O-0001", mount=["V1", "on", "", ["Sam Reed"]], mounted=RIDING, leader="Sam Reed")
    assert sent(b) == ["MOUNT", "MOVE"]
    b.advance(106, order="O-0002", mounted=RIDING, leader="Sam Reed", leg=0, legs=1)
    assert "Now moving to grid 050 030. That's 2 km by vehicle, about 2 minutes." in said(b)
    assert sent(b) == ["MOUNT", "MOVE"]  # it's on its way, not there
    b.advance(108, order="O-0002", mounted=RIDING, leader="Sam Reed", leg=1, legs=1, pos=[5050, 3050], grid="050030")
    assert sent(b) == ["MOUNT", "MOVE", "DISMOUNT"]
    b.advance(110, order="O-0003", mounted=RIDING, leader="Sam Reed", mount=["V1", "going off", "", []])
    assert "Now getting off." in said(b)
    assert b.runtime.chains == {}


def test_a_chain_says_who_stays_on_a_gun(tmp_path):
    b = chained(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [DRIVE, {"type": "FIRE_MISSION", "at": "041 041"}]})
    b.advance(102, order="O-0001", mounted=[["V1", "gunner", "Pat Vane", True]])
    assert any(line.startswith("Copy, moving to grid 050 030, then fire mission") and "Pat Vane stays on V1." in line
               for line in said(b)), said(b)


def test_a_chain_is_finished_with_after_its_last_step_is_sent(tmp_path):
    b = chained(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [MOUNT, DRIVE]})
    b.advance(102, order="O-0001", mount=["V1", "on", "", ["Sam Reed"]], mounted=RIDING, leader="Sam Reed")
    assert sent(b) == ["MOUNT", "MOVE"]
    assert b.runtime.chains == {}


def test_the_total_counts_unloading_where_they_are_not_where_the_truck_was(tmp_path):
    """It came to "At least 35 minutes": back to the truck's old grid on foot, then a 2 km carry from there."""
    b = chained(tmp_path)
    b.advance(102, casualties=[down_row()])
    b.runtime.order({"to": "Alpha", "legs": [{"type": "CARRY", "casualties": ["C1"], "vehicle": "V1"}, MOUNT, DRIVE,
                                             DISMOUNT, {"type": "UNLOAD", "vehicle": "V1"},
                                             {"type": "CARRY", "casualties": ["C1"], "at": "050 030"}]})
    b.advance(104, casualties=[down_row()], order="O-0001")
    assert any("At least 3 minutes in all." in line for line in said(b)), said(b)


def test_the_list_doesnt_follow_a_man_being_carried(tmp_path):
    """Every packet used to rewrite his grid, so the briefing tracked his carriers live, even in a fight."""
    b = wounded_battle(tmp_path)
    b.advance(102, casualties=[down_row(x=3050, y=3050)])
    assert "C1  Sam Reed  Alpha's  grid 030 030" in b.runtime.briefing()
    b.advance(104, casualties=[down_row(x=4550, y=3050, handled="carried")], pos=[4550, 3050])
    assert "grid 045 030" not in b.runtime.briefing()
    assert "C1  Sam Reed  Alpha's  grid 030 030" in b.runtime.briefing()
    assert b.runtime.mission()["casualties"][0]["grid"] == "030 030"


def test_how_long_since_a_report_is_since_someone_said_something(tmp_path):
    b = wounded_battle(tmp_path)
    b.advance(102, casualties=[down_row(x=3050, y=3050)])
    b.advance(160, casualties=[down_row(x=3050, y=3050)])
    assert "reported 58 s ago" in b.runtime.briefing() or "reported a minute ago" in b.runtime.briefing()


def test_setting_him_down_tells_the_commander_where_he_is(tmp_path):
    b = wounded_battle(tmp_path)
    b.advance(102, casualties=[down_row(x=3050, y=3050)])
    b.advance(104, casualties=[down_row(x=4550, y=3050)], medical=[["O-1", "carry", "m7", "Sam Reed", "carried", ""]])
    assert "C1  Sam Reed  Alpha's  grid 045 030" in b.runtime.briefing()


def test_going_down_in_a_fight_puts_no_grid_on_the_list(tmp_path):
    b = wounded_battle(tmp_path)
    b.advance(102, casualties=[down_row(x=3050, y=3050)], suppression=0.5, contacts=[contact()])
    assert "Sam Reed  Alpha's  place not given" in b.runtime.briefing()
    assert b.runtime.mission()["casualties"][0]["grid"] is None


def test_a_man_left_behind_who_dies_stays_on_the_list(tmp_path):
    """His vanishing from it was the commander being told something nobody near him could know."""
    b = wounded_battle(tmp_path)
    b.advance(102, casualties=[down_row(x=3050, y=3050)])
    b.advance(104, casualties=[down_row(x=3050, y=3050)], pos=[6050, 3050])
    b.advance(106, casualties=[], pos=[6050, 3050])
    assert "Sam Reed's dead." not in said(b)
    assert "C1  Sam Reed" in b.runtime.briefing()


def test_a_timed_order_that_cant_go_out_says_so(tmp_path):
    b = Battle(tmp_path, markers=[{"id": "O1", "kind": "objective", "at": "034 030"}])
    b.start()
    b.runtime.schedule({"order": {"to": "Alpha", "legs": [{"type": "MOVE", "at": "O1"}]}}, after="0:05")
    b.runtime.unmark("O1")
    b.runtime.end_turn("x")
    b.advance(110)
    told = [text for text, _ in b.wakes] + list(b.runtime.wake.notices)
    assert "couldn't go out" in " ".join(told), told


def test_appending_to_nothing_takes_over_from_a_chain(tmp_path):
    """The chain's next step would otherwise have overridden the newer order."""
    b = chained(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [MOUNT, DRIVE]})
    b.advance(102, order="O-0001", mount=["V1", "going", "", []])
    b.runtime.order({"to": "Alpha", "mode": "append", "legs": [{"type": "MOVE", "at": "034 030"}]})
    b.advance(104, order="O-0002", mount=["V1", "on", "", ["Sam Reed"]])
    assert sent(b) == ["MOUNT", "MOVE"] and b.records.read("orders")[1]["request"]["legs"][0]["at"] == "034 030"
    assert b.runtime.chains == {}


def test_nothing_can_be_appended_after_what_never_ends(tmp_path):
    b = chained(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [{"type": "HOLD", "at": "034 030"}]})
    with pytest.raises(Invalid, match="HOLD runs until replaced"):
        b.runtime.order({"to": "Alpha", "mode": "append", "legs": [{"type": "MOVE", "at": "036 030"}]})


def test_one_man_sent_to_a_seat_leaves_the_chain_running(tmp_path):
    b = chained(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [DRIVE, DISMOUNT]})
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOUNT", "vehicle": "V1", "seat": "gunner"}]})
    assert "Alpha" in b.runtime.chains


def test_one_man_sent_to_a_seat_leaves_the_squads_route_and_its_reports(tmp_path):
    b = chained(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [DRIVE]})
    b.advance(102, order="O-0001", leg=0, legs=1)
    b.runtime.order({"to": "Alpha", "legs": [{"type": "MOUNT", "vehicle": "V1", "seat": "gunner"}]})
    b.advance(104, order="O-0002", leg=0, legs=1)
    assert "Copy, mounting V1 as gunner." in said(b)
    b.advance(106, order="O-0002", leg=1, legs=1, pos=[5050, 3050], grid="050030")
    assert "Arrived, grid 050 030." in said(b)


def test_a_step_that_fails_stops_the_rest_and_says_so(tmp_path):
    b = chained(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [MOUNT, DRIVE, DISMOUNT]})
    b.advance(102, order="O-0001", mount=["V1", "wrecked", "", []])
    assert "V1 is wrecked. Not mounting." in said(b) and "Stopping there, waiting for orders." in said(b)
    assert sent(b) == ["MOUNT"] and b.runtime.chains == {}


@pytest.mark.parametrize("cancel, words", [
    ({"legs": [{"type": "HALT"}]}, "Halted at grid"),
    ({"legs": [{"type": "MOVE", "at": "034 030"}]}, "Copy, moving to grid 034 030."),
    ({"legs": [DRIVE, DISMOUNT]}, "Copy, moving to grid 050 030, then getting off."),
])
def test_a_new_squad_order_cancels_the_rest_and_says_what_it_dropped(tmp_path, cancel, words):
    b = chained(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [MOUNT, DRIVE, DISMOUNT]})
    b.advance(102, order="O-0001", mount=["V1", "going", "", []])
    b.runtime.order({"to": "Alpha", **cancel})
    b.advance(104, order="O-0002", mount=["V1", "on", "", ["Sam Reed"]])
    line = next(line for line in said(b) if words in line)
    assert "Dropping the rest: moving to grid 050 030, then getting off." in line
    assert sent(b)[2:] == []  # nothing more than the two orders


def test_posture_and_fire_leave_a_chain_running(tmp_path):
    b = chained(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [MOUNT, DRIVE, DISMOUNT]})
    b.advance(102, order="O-0001", mount=["V1", "going", "", []])
    b.runtime.order({"to": "Alpha", "legs": [{"type": "POSTURE"}], "behaviour": "SAFE"})
    b.advance(104, order="O-0002", mount=["V1", "going", "", []])
    assert "Alpha" in b.runtime.chains
    b.advance(106, order="O-0002", mount=["V1", "on", "", ["Sam Reed"]], mounted=RIDING, leader="Sam Reed")
    assert sent(b) == ["MOUNT", "POSTURE", "MOVE"]


def test_an_order_about_the_wounded_is_a_step_and_waits_for_every_man(tmp_path):
    b = chained(tmp_path)
    down = [down_row(key="m7", name="Sam Reed", x=3080, y=3050), down_row(key="m8", name="Ann Cole", x=3090, y=3050)]
    b.advance(102, casualties=down)
    b.runtime.order({"to": "Alpha", "legs": [{"type": "CARRY", "casualties": ["C1", "C2"], "vehicle": "V1"}, MOUNT]})
    assert sent(b) == ["CARRY"]
    b.advance(104, casualties=down, order="O-0001", medical=[["O-0001", "carry", "m7", "Sam Reed", "going", ""],
                                                             ["O-0001", "carry", "m8", "Ann Cole", "going", ""]])
    assert any(line.startswith("Copy, carrying Sam Reed and Ann Cole to V1, then mounting V1. At least") for line in
               said(b))
    b.advance(106, casualties=down, order="O-0001", medical=[["O-0001", "carry", "m7", "Sam Reed", "loaded", ""],
                                                             ["O-0001", "carry", "m8", "Ann Cole", "carrying", ""]])
    assert sent(b) == ["CARRY"]
    b.advance(108, casualties=down, order="O-0001", medical=[["O-0001", "carry", "m7", "Sam Reed", "loaded", ""],
                                                             ["O-0001", "carry", "m8", "Ann Cole", "loaded", ""]])
    assert sent(b) == ["CARRY", "MOUNT"]


def test_a_carry_that_fails_stops_the_chain(tmp_path):
    b = chained(tmp_path)
    b.advance(102, casualties=[down_row()])
    b.runtime.order({"to": "Alpha", "legs": [{"type": "CARRY", "casualties": ["C1"], "vehicle": "V1"}, MOUNT, DRIVE]})
    b.advance(104, order="O-0001", medical=[["O-0001", "carry", "m7", "Sam Reed", "no bearer", ""]])
    assert sent(b) == ["CARRY"] and "Stopping there, waiting for orders." in said(b)


def test_a_boarding_stopped_by_a_new_order_is_said():
    assert reports._boarding_words(["V1", "stopped", "", []]) == "Stopped getting on V1."


def test_men_who_cant_get_off_are_named_and_stop_a_chain():
    status = ["V1", "stuck", "", ["Sam Reed"]]
    assert reports._boarding_words(status) == "Can't get Sam Reed off V1."
    assert reports.step_outcome("dismount", "O", {"mount": status}, False) == "failed"
    assert reports.step_outcome("dismount", "O", {"mount": ["V1", "going off", "", []]}, False) is None


@pytest.mark.parametrize("mode, rows, outcome", [
    ("treat", [["O", "treat", "a", "A", "queued", "", ""]], None),
    ("treat", [["O", "treat", "a", "A", "aboard", "V1", ""]], None),  # they wait for him
    ("treat", [["O", "treat", "a", "A", "up", "", ""], ["O", "treat", "b", "B", "queued", "", ""]], None),
    ("treat", [["O", "treat", "a", "A", "up", "", ""], ["O", "treat", "b", "B", "he died", "", ""]], "done"),
    ("treat", [["O", "treat", "", "", "no medic", "", ""]], "failed"),
    ("unload", [["O", "unload", "a", "A", "going", "V1", ""]], None),
    ("unload", [["O", "unload", "a", "A", "off", "V1", ""]], "done"),
    ("unload", [["O", "unload", "", "", "nobody there", "V1", ""]], "failed"),
    ("post", [["O", "post", "post", "", "building", "", ""]], None),
    ("post", [["O", "post", "post", "", "up", "A1", "040 060"]], "done"),
    ("carry", [["Other", "carry", "a", "A", "loaded", "", ""]], None),  # another order's
    ("carry", [], None),
])
def test_when_a_step_about_the_wounded_is_over(mode, rows, outcome):
    assert reports.step_outcome(mode, "O", {"medical": rows}, False) == outcome


def test_a_chain_survives_a_restart(tmp_path):
    b = chained(tmp_path)
    b.runtime.order({"to": "Alpha", "legs": [MOUNT, DRIVE, DISMOUNT]})
    b.runtime.save()
    assert b.records.load_state()["chains"]["Alpha"]["left"] == ["moving to grid 050 030", "getting off"]


CHAINERS = {"Alpha": {"capabilities": ["MOVE", "HOLD", "SENTRY", "SEARCH", "MOUNT", "DISMOUNT", "DEFEND", "OCCUPY",
                                       "CARRY", "HALT", "POSTURE", "FIRE_MISSION", "CHECK_FIRE", "PATROL"],
                      "at": "030 030"}}


def chain_check(*legs, **fields):
    return orders.validate({"to": "Alpha", "legs": list(legs), **fields}, CHAINERS, MARKERS, 8192, BUILDINGS, LIST)


def test_waypoints_in_a_row_are_one_step():
    checked = chain_check(MOUNT, {"type": "MOVE", "at": "034 030"}, {"type": "MOVE", "at": "036 030"}, DISMOUNT)
    assert [one["mode"] for one in checked["checked"]] == ["mount", "replace", "dismount"]
    assert len(checked["checked"][1]["route"]["legs"]) == 2


def test_a_plain_route_is_still_not_a_chain():
    assert chain_check({"type": "MOVE", "at": "034 030"}, {"type": "HOLD"})["mode"] == "replace"


@pytest.mark.parametrize("kind", ["DEFEND", "PATROL"])
def test_what_runs_until_replaced_has_to_go_last(kind):
    with pytest.raises(Invalid, match=f"{kind} runs until replaced, so nothing can follow it.*Put it last"):
        chain_check({"type": kind, "at": ["034 030", "036 030"] if kind == "PATROL" else "034 030"}, MOUNT)
    assert chain_check(MOUNT, {"type": "DEFEND", "at": "034 030"})["mode"] == "chain"


@pytest.mark.parametrize("after", [DISMOUNT, {"type": "MOVE", "at": "036 030"}])
def test_hold_can_only_go_last_and_says_how_to_wait_instead(after):
    with pytest.raises(Invalid, match="use MOVE with hold_for"):
        chain_check({"type": "HOLD", "at": "034 030"}, after)


def test_hold_partway_along_a_trip_is_refused_too():
    """Only the last leg of each step used to be looked at, so this would have hung at the HOLD for good."""
    with pytest.raises(Invalid, match="use MOVE with hold_for"):
        chain_check({"type": "HOLD", "at": "034 030"}, {"type": "MOVE", "at": "036 030"}, DISMOUNT)


def test_hold_after_getting_off_means_there():
    checked = chain_check({"type": "MOVE", "at": "034 030"}, DISMOUNT, {"type": "HOLD"})
    assert checked["checked"][2]["route"]["legs"][0]["grid"] == "034 030"


def test_a_mistake_in_a_later_step_is_refused_at_once():
    with pytest.raises(Invalid, match="needs a vehicle from your list"):
        chain_check(MOUNT, DRIVE, {"type": "DISMOUNT", "vehicle": "V9"})


def test_check_fire_goes_alone_and_a_fire_mission_can_be_a_step():
    with pytest.raises(Invalid, match="CHECK_FIRE must be the only leg"):
        chain_check(MOUNT, {"type": "CHECK_FIRE"})
    checked = chain_check(MOUNT, {"type": "MOVE", "at": "034 030"}, {"type": "FIRE_MISSION", "at": "041 041"})
    assert [one["mode"] for one in checked["checked"]] == ["mount", "replace", "fire"]


def fire_row(order, state, gun="V1"):
    return [gun, order, state, "", "HE", 3, 3, 30, 0]


@pytest.mark.parametrize("rows, outcome", [
    ([fire_row("O", "firing")], None),
    ([fire_row("O", "holding")], None),
    ([fire_row("O", "done")], "done"),
    ([fire_row("O", "done"), fire_row("O", "firing", "V2")], None),
    ([fire_row("O", "done"), fire_row("O", "out", "V2")], "failed"),
    ([fire_row("O", "cantlay")], "failed"),
    ([fire_row("O", "unable")], "failed"),
    ([fire_row("Other", "done")], None),
])
def test_when_a_fire_step_is_over(rows, outcome):
    assert reports.step_outcome("fire", "O", {"missions": rows}, False) == outcome


def test_a_chain_cant_be_appended():
    with pytest.raises(Invalid, match="Only MOVE, HOLD, SEARCH and SENTRY can be appended"):
        chain_check(MOUNT, DRIVE, mode="append")


def test_the_commander_is_told_to_give_whole_tasks():
    assert "Give whole tasks, not single steps" in DOCTRINE and "Dropping" not in LEGS_HELP
    assert "Each leg starts when the one before has finished" in LEGS_HELP
    assert "Each stands alone" not in ORDER_TYPES_HELP
    order_tool = next(tool for tool in TOOLS if tool["name"] == "commander_order")
    assert order_tool["inputSchema"]["properties"]["legs"]["description"] == LEGS_HELP


def in_the_fight(tmp_path) -> Battle:
    b = Battle(tmp_path)
    b.start()
    b.runtime.end_turn("x", messages_only=True)
    return b


def radio_words(b: Battle) -> list[str]:
    return [row["text"] for row in b.records.read("radio")]


def test_reports_from_a_squad_in_combat_arrive_late_and_in_order(tmp_path):
    b = in_the_fight(tmp_path)
    b.advance(102, contacts=[contact()], suppression=0.5)
    assert radio_words(b) == []  # nothing yet
    b.advance(104, contacts=[contact()], suppression=0.5, able=3)
    b.advance(110, contacts=[contact()], suppression=0.5, able=3)
    assert radio_words(b) == []  # under heavy fire, even a flash report takes about 15 s
    for t in (114, 117, 120):
        b.advance(t, contacts=[contact()], suppression=0.5, able=3)
    assert radio_words(b)[0].startswith("Contact, one infantry, bearing 045")
    assert b.records.read("radio")[0]["t"] == 17  # logged when it was heard, and T+0 is mission time 100
    for t in (125, 131, 137, 143, 149, 155, 161, 167, 170):  # casualties are grouped for 30 s, then take 30 s to report
        b.advance(t, contacts=[contact()], suppression=0.5, able=3)
    words = radio_words(b)
    assert words[1].startswith("Taking casualties, 3 of 4 effective")


def test_a_calm_squad_still_reports_at_once(tmp_path):
    b = in_the_fight(tmp_path)
    b.advance(102, order="", able=3)
    b.advance(104, order="", able=2)
    assert b.runtime.outbox == []


def test_asking_a_squad_in_combat_gets_wait_one_then_the_answer_later(tmp_path):
    b = in_the_fight(tmp_path)
    b.advance(102, contacts=[contact()], suppression=0.5)
    assert b.runtime.ask("Alpha", ["position", "strength"])["replies"] == [{"from": "Alpha", "text": "Wait one."}]
    assert b.runtime.ask("Alpha", ["position", "strength"])["replies"] == [{"from": "Alpha", "text": "Wait one."}]
    assert len([e for e in b.runtime.outbox if "topics" in e]) == 1  # asking again changes nothing
    assert "Grid" not in " ".join(radio_words(b))
    for t in (110, 118, 125, 131, 133):
        b.advance(t, contacts=[contact()], suppression=0.5, pos=[3350, 3050], grid="033030")
    answers = [w for w in radio_words(b) if w.startswith("Grid")]
    assert answers == ["Grid 033 030, stationary. 4 of 4 effective. Sam Reed has command."]  # as it is by then
    assert b.runtime.positions["Alpha"]["grid"] == "033 030"


def test_a_general_sitrep_in_combat_gives_no_grid_and_doesnt_move_the_map(tmp_path):
    b = in_the_fight(tmp_path)
    b.advance(102, contacts=[contact()], suppression=0.5)
    b.runtime.ask("Alpha")
    for t in (110, 118, 125, 131, 133):
        b.advance(t, contacts=[contact()], suppression=0.5)
    answer = [w for w in radio_words(b) if "effective" in w][0]
    assert "030 030" not in answer and "Alpha" not in b.runtime.positions


def test_a_squad_wiped_out_never_sends_what_it_was_waiting_to_say(tmp_path):
    b = in_the_fight(tmp_path)
    b.advance(102, contacts=[contact()], suppression=0.5)
    b.runtime.ask("Alpha", ["strength"])
    for t in (110, 120, 130, 140):
        b.silent(t)  # no more packets: nobody left to send them
    assert radio_words(b).count("Wait one.") == 1
    assert not [w for w in radio_words(b) if w.startswith("Contact") or "effective" in w]
    assert b.runtime.outbox == [] and b.wakes == []


def test_a_checkin_during_a_fight_arrives_late_too(tmp_path):
    b = in_the_fight(tmp_path)
    b.runtime.schedule({"ask": {"to": "Alpha", "topics": ["strength"]}}, after="0:10")
    b.advance(105, contacts=[contact()], suppression=0.5)
    b.advance(111, contacts=[contact()], suppression=0.5)
    assert [e for e in b.runtime.outbox if e.get("checkin")]
    for t in (118, 124, 130, 136, 142):
        b.advance(t, contacts=[contact()], suppression=0.5)
    assert "4 of 4 effective. Sam Reed has command." in radio_words(b)


def test_messages_waiting_to_be_sent_survive_a_server_restart_and_die_with_the_battle(tmp_path):
    b = in_the_fight(tmp_path)
    b.advance(102, contacts=[contact()], suppression=0.5)
    b.runtime.save()
    assert b.new_runtime().outbox == b.runtime.outbox != []
    b.runtime._end("Time limit reached.")
    assert b.runtime.outbox == []


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
               "commander_mark", "commander_unmark", "commander_map", "commander_ground"}
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


def tool_reply(server: Server, stdout: io.BytesIO) -> str:
    server._tool({"id": 1, "params": {"name": "commander_roster"}})
    return json.loads(stdout.getvalue().splitlines()[-1])["result"]["content"][0]["text"]


def test_a_session_opened_while_the_game_boots_gets_the_battle_once_its_ready():
    """It used to find the last battle, finished, and report the mission as already over."""
    ready = []

    def factory(deliver):
        if not ready:
            raise HarnessError("no commander scenario is set up")
        return StubRuntime()

    stdout = io.BytesIO()
    server = Server(io.BytesIO(), stdout, runtime_factory=factory)
    server.stop.set()
    assert tool_reply(server, stdout) == NO_BATTLE
    ready.append(True)
    assert tool_reply(server, stdout) != NO_BATTLE


def test_a_session_from_an_earlier_battle_is_told_so_and_stops_running():
    current = [True]
    stdout = io.BytesIO()
    steps = []

    class Counting(StubRuntime):
        def step(self):
            steps.append(1)
            time.sleep(0.01)

    server = Server(io.BytesIO(), stdout, runtime_factory=lambda deliver: Counting(),
                    still_current=lambda runtime: current[0])
    assert tool_reply(server, stdout) != EARLIER_BATTLE
    current[0] = False
    assert tool_reply(server, stdout) == EARLIER_BATTLE
    time.sleep(0.05)
    counted = len(steps)
    time.sleep(0.05)
    assert len(steps) == counted
    server.stop.set()


def test_is_current_goes_by_the_records_folder(tmp_path):
    from types import SimpleNamespace

    from arma_harness.commander import operator
    home = Home(tmp_path)
    file = operator._current_file(home)
    mine = SimpleNamespace(records=SimpleNamespace(folder=tmp_path / "one"))
    assert not operator.is_current(mine, home)  # none set up
    file.write_text(json.dumps({"folder": str(tmp_path / "one")}), encoding="utf-8")
    assert operator.is_current(mine, home)
    file.write_text(json.dumps({"folder": str(tmp_path / "two")}), encoding="utf-8")
    assert not operator.is_current(mine, home)
    file.write_text('{"fold', encoding="utf-8")
    assert operator.is_current(mine, home)  # being written just now, so it can't be told


def starting(tmp_path, state):
    from types import SimpleNamespace

    from arma_harness.commander import operator

    def boot(mission):
        assert not operator._current_file(home).exists()  # already gone by the time anything takes long
        raise HarnessError("stopping here")

    home = Home(tmp_path)
    operator._current_file(home).write_text("{}", encoding="utf-8")
    harness = SimpleNamespace(home=home, forget_dead_run=lambda: None, state=lambda: state, start=boot)
    with pytest.raises(HarnessError) as caught:
        operator.start(str(REPO_ROOT / "scenarios" / "commander" / "casevac_rv.yaml"), harness=harness)
    return operator._current_file(home).exists(), str(caught.value)


def test_starting_forgets_the_last_battle_before_booting(tmp_path):
    assert starting(tmp_path, None) == (False, "stopping here")


def test_a_start_that_was_refused_leaves_the_running_battle_alone(tmp_path):
    from types import SimpleNamespace
    exists, why = starting(tmp_path, SimpleNamespace(mission="something_else", run_id="r1"))
    assert exists and "Stop it first" in why


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
