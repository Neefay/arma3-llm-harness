"""Losing: casualties over a share of the starting strength, or a critical station or vehicle lost. Stated in the
briefing from the same settings the harness checks, and said when it happens."""
from __future__ import annotations

import pytest
from test_commander import Battle

from arma_harness.commander import scenario

BASE = {"name": "t", "mission": "m", "text": "t", "time_limit": "10:00",
        "stations": [{"callsign": "Alpha", "role": "r", "capabilities": ["MOVE"], "at": "030 030", "units": 8},
                     {"callsign": "Recon", "role": "r", "capabilities": ["MOVE"], "at": "031 030", "units": 2}],
        "vehicles": [{"id": "V1", "class": "B_Truck_01_transport_F", "at": "032 030"}]}


@pytest.mark.parametrize(("failure", "words"), [
    ({"casualties": 50}, "unknown failure conditions"),
    ({"casualties_pct": 0}, "percentage"),
    ({"casualties_pct": "half"}, "percentage"),
    ({"critical": ["Bravo"]}, "critical must list"),
    ({"critical": "Recon"}, "critical must list"),
])
def test_bad_failure_conditions_are_refused(failure, words):
    with pytest.raises(ValueError, match=words):
        scenario.build({**BASE, "failure": failure})


def battle(tmp_path, **failure) -> Battle:
    b = Battle(tmp_path, stations=BASE["stations"], vehicles=BASE["vehicles"], failure=failure,
               success={"station": "Alpha", "within_m": 50, "of": "060 060"})
    b.start()
    return b


def truth(b: Battle, t: float, alpha=8, recon=2, recon_down=(), vehicles=(("V1", True),)) -> None:
    b.game.emit(type="cmd_truth", t=t, vehicles=[list(v) for v in vehicles], groups=[
        {"group": "Alpha", "side": "WEST", "able": alpha, "down": [], "units": [], "pos": [3050, 3050]},
        {"group": "Recon", "side": "WEST", "able": recon, "down": list(recon_down), "units": [], "pos": [3150, 3050]}])
    b.runtime.step(0)


def test_the_briefing_says_how_the_mission_can_fail(tmp_path):
    b = battle(tmp_path, casualties_pct=40, critical=["Recon", "V1"])
    assert b.runtime.mission()["fails_if"] == [
        "40% or more of your men are dead or down at the same time, out of the 10 you start with.",
        "Recon is lost: every one of its men dead.", "V1 is destroyed."]
    assert "THE MISSION FAILS IF\n40% or more" in b.runtime.briefing()
    assert "fails_if" in battle(tmp_path / "plain").runtime.mission()
    assert "FAILS IF" not in battle(tmp_path / "plain2").runtime.briefing()


def test_too_many_casualties_fail_the_mission(tmp_path):
    b = battle(tmp_path, casualties_pct=40)
    truth(b, 110, alpha=6, recon=1)  # 3 of 10: not yet
    assert not b.runtime.ended
    truth(b, 120, alpha=5, recon=1)  # 4 of 10
    assert b.runtime.ended == "Mission failed: 4 of your 10 men are dead or down."
    assert b.records.read("radio_events")[-1]["mission_end"] == "Mission failed: 4 of your 10 men are dead or down."


def test_a_critical_station_is_lost_only_when_all_its_men_are_dead(tmp_path):
    b = battle(tmp_path, critical=["Recon"])
    truth(b, 110, recon=0, recon_down=([3150, 3050],))  # down, still alive: not lost
    assert not b.runtime.ended
    truth(b, 120, recon=0)
    assert b.runtime.ended == "Mission failed: Recon has been lost."


def test_a_critical_vehicle_destroyed_fails_the_mission(tmp_path):
    b = battle(tmp_path, critical=["V1"])
    truth(b, 110)
    assert not b.runtime.ended
    truth(b, 120, vehicles=(("V1", False),))
    assert b.runtime.ended == "Mission failed: V1 has been destroyed."
    assert b.records.read_truth()[-1]["vehicles"] == [["V1", False]]


def test_men_at_a_place_counts_soldiers_not_squads(tmp_path):
    b = Battle(tmp_path, stations=BASE["stations"], success={"men": 6, "within_m": 100, "of": "040 040"})
    b.start()
    there = [[4050, 4050, 0]] * 5
    b.game.emit(type="cmd_truth", t=110, groups=[
        {"group": "Alpha", "side": "WEST", "able": 8, "down": [], "units": there + [[3000, 3000, 0]] * 3},
        {"group": "Recon", "side": "WEST", "able": 2, "down": [], "units": [[3000, 3000, 0]] * 2}])
    b.runtime.step(0)
    assert not b.runtime.objectives_due
    b.game.emit(type="cmd_truth", t=112, groups=[
        {"group": "Alpha", "side": "WEST", "able": 8, "down": [], "units": there + [[3000, 3000, 0]] * 3},
        {"group": "Recon", "side": "WEST", "able": 2, "down": [], "units": [[4060, 4040, 0]] + [[3000, 3000, 0]]}])
    b.runtime.step(0)
    assert b.runtime.objectives_due["OBJ1"]["met"] == "6 men are at grid 040 040"
