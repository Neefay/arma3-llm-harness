"""Enemy weapons and vehicles: said by kind, then by model as squads come to know them, listed once per real one (T1...)
whoever reports it, and marked abandoned or destroyed only when someone sees it."""
from __future__ import annotations

import pytest
from test_commander import Battle, said

from arma_harness.commander import reports
from arma_harness.commander.orders import Invalid

STATIONS = [{"callsign": "Alpha", "role": "r", "capabilities": ["MOVE", "MOUNT", "HOLD"], "at": "030 030"},
            {"callsign": "Bravo", "role": "r", "capabilities": ["MOVE", "HOLD"], "at": "031 030"}]


def gun(name="Mk30 HMG .50", key="E1", age=1.0, x=3250.0, y=3350.0, kind="emplacement") -> dict:
    return {"pos": [x, y], "kind": kind, "name": name, "key": key, "age_s": age, "accuracy_m": 5}


def settle(b: Battle, t: float, **fields) -> list[str]:
    """Let a squad in contact get its words out: they go after a delay, as on a real net."""
    for step in range(0, 70, 10):
        b.advance(t + step, **fields)
    return said(b)


def battle(tmp_path) -> Battle:
    b = Battle(tmp_path, stations=STATIONS, success={"station": "Alpha", "within_m": 50, "of": "060 060"},
               time_limit="20:00")
    b.start()
    return b


def test_kinds_are_said_apart_and_models_once_known():
    group = {"kinds": {"infantry": 4, "tank": 1}, "names": {"tank": ["T-100 Varsuk"]}, "ids": [], "count": 5,
             "offset": (0, 300), "accuracy_m": 0, "range": 300, "nearest": None}
    assert reports.contact_phrase(group).startswith("one tank (T-100 Varsuk) and a few infantry, ")
    two = {**group, "kinds": {"emplacement": 2}, "names": {}, "count": 2}
    assert reports.contact_phrase(two).startswith("a couple of emplacements, ")
    assert reports.contact_phrase({**two, "kinds": {"infantry": 2}}).startswith("a couple of infantry, ")


def test_a_gun_is_listed_when_first_reported(tmp_path):
    b = battle(tmp_path)
    heard = settle(b, 102, contacts=[gun(name="")])
    first = next(line for line in heard if line.startswith("Contact,"))
    assert first.startswith("Contact, one emplacement, ") and first.endswith("Listed as T1.")
    entry = b.runtime.vehicles["T1"]
    assert entry["enemy"] and entry["state"] == "active" and entry["where"] == "about 350 metres north-east of Alpha"
    assert b.runtime.mission()["enemy_materiel"] == [{"id": "T1", "type": "emplacement", "state": "active",
                                                      "seen_by": "Alpha",
                                                      "where": "about 350 metres north-east of Alpha"}]
    assert "ENEMY WEAPONS AND VEHICLES\nT1  enemy emplacement  active, about 350 metres north-east of Alpha" \
        in b.runtime.briefing()


def test_a_model_known_later_is_an_update(tmp_path):
    b = battle(tmp_path)
    settle(b, 102, contacts=[gun(name="")])
    heard = settle(b, 180, contacts=[gun()])
    assert any(line.startswith("Contact update, one emplacement (Mk30 HMG .50), T1, ") for line in heard), heard
    assert b.runtime.vehicles["T1"]["name"] == "emplacement (Mk30 HMG .50)"


def test_another_squad_seeing_the_same_gun_names_it(tmp_path):
    b = battle(tmp_path)
    settle(b, 102, contacts=[gun()])
    settle(b, 180, callsign="Bravo", pos=[3150.0, 3050.0], contacts=[gun()])
    bravo = [row["text"] for row in b.records.read("radio") if row["from"] == "Bravo"]
    assert bravo and ", T1, " in bravo[-1] and "Listed as" not in bravo[-1]
    assert [one for one in b.runtime.vehicles if one.startswith("T")] == ["T1"]


def test_abandoned_then_destroyed_only_as_seen(tmp_path):
    b = battle(tmp_path)
    settle(b, 102, contacts=[gun()])
    heard = settle(b, 300, seen_vehicles=[["E1", "Mk30 HMG .50", "032033", True]])
    assert "T1, emplacement (Mk30 HMG .50), abandoned, nobody on it, grid 032 033." in heard
    assert b.runtime.vehicles["T1"]["state"] == "abandoned"
    settle(b, 400, contacts=[gun()])  # manned again
    assert b.runtime.vehicles["T1"]["state"] == "active"
    heard = settle(b, 600, seen_vehicles=[["E1", "Mk30 HMG .50", "032033", False]])
    assert "T1 is destroyed, grid 032 033." in heard
    assert b.runtime.vehicles["T1"]["state"] == "destroyed"


def test_nothing_unannounced_shows_on_the_list(tmp_path):
    b = battle(tmp_path)
    b.runtime.trackers["Alpha"] = reports.Tracker()
    b.runtime._target_rows("Alpha", {"pos": [3050.0, 3050.0], "t": 102.0, "contacts": [gun()]})
    assert "T1" in b.runtime.vehicles and "ENEMY WEAPONS" not in b.runtime.briefing()
    assert b.runtime.mission()["enemy_materiel"] == []


def test_the_enemys_vehicle_isnt_ours_to_order(tmp_path):
    b = battle(tmp_path)
    b.advance(102, contacts=[gun()])
    with pytest.raises(Invalid, match="T1 is the enemy's"):
        b.runtime.order({"to": "Alpha", "legs": [{"type": "MOUNT", "vehicle": "T1"}]})
    with pytest.raises(Invalid, match="T1 is the enemy's"):
        b.runtime.order({"to": "Alpha", "legs": [{"type": "MOVE", "at": "T1"}]})


def test_a_gun_destroyed_mid_fight_is_said_then(tmp_path):
    b = battle(tmp_path)
    infantry = {"pos": [3200.0, 3300.0], "kind": "infantry", "age_s": 1.0, "accuracy_m": 5}
    settle(b, 102, contacts=[gun(), infantry])
    heard = settle(b, 170, contacts=[infantry], seen_vehicles=[["E1", "Mk30 HMG .50", "032033", False],
                                                               ["U9", "Offroad", "031031", True]])
    assert "T1 is destroyed, grid 032 033." in heard
    assert not any("Offroad" in line for line in heard)  # an empty car can wait till the shooting stops


HAWG = {"callsign": "Hawg", "role": "attack helicopter", "capabilities": ["CAS"], "at": "025 018",
        "on_station": "2:00"}


def test_a_pilot_gives_contacts_from_the_grid_he_was_sent_to(tmp_path):
    b = Battle(tmp_path, stations=[HAWG], success={"station": "Hawg", "within_m": 50, "of": "060 060"},
               time_limit="20:00")
    b.start()
    b.runtime.order({"to": "Hawg", "legs": [{"type": "CAS", "at": "037 024"}]})
    infantry = {"pos": [3850.0, 2550.0], "kind": "infantry", "age_s": 1.0, "accuracy_m": 5}
    heard = settle(b, 102, callsign="Hawg", pos=[2550.0, 1850.0], contacts=[infantry])
    contact = next(line for line in heard if line.startswith("Contact,"))
    assert "one infantry, roughly 150 metres north-east of the target grid" in contact, contact
    assert "bearing" not in contact


def test_an_aircraft_leaves_when_its_time_on_station_is_up(tmp_path):
    from arma_harness.commander.runtime import LEAVE_CODE

    b = Battle(tmp_path, stations=[HAWG], success={"station": "Hawg", "within_m": 50, "of": "060 060"},
               time_limit="20:00")
    b.start()
    assert b.runtime.roster()["stations"][0]["on_station_until"] == "T+02:00"
    b.advance(230, callsign="Hawg", pos=[2550.0, 1850.0])  # 2:10 into the battle
    assert "Bingo fuel, leaving the area." in said(b)
    assert any(call[0] == LEAVE_CODE and call[1] == ["Hawg"] for call in b.game.calls)
    assert b.runtime.roster()["stations"][0]["left_the_area"]
    with pytest.raises(Invalid, match="Hawg has left the area"):
        b.runtime.order({"to": "Hawg", "legs": [{"type": "CAS", "at": "037 024"}]})
