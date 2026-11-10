"""Random draws in a scenario: resolved once when a battle starts, the same for the same seed, and recorded."""
from __future__ import annotations

import math

import pytest

from arma_harness.commander import scenario
from arma_harness.commander.orders import parse_grid, parse_time

TEMPLATE = {
    "name": "t", "mission": "m", "text": "Hold the crossroads.", "time_limit": "25:00",
    "stations": [{"callsign": "Alpha", "role": "r", "capabilities": ["MOVE"], "at": "030 030"}],
    "enemies": [{"one_of": [
        {"id": "Road", "at": "040 030", "units": {"between": [4, 8]}, "mode": "hold"},
        {"id": "Ridge", "at": {"around": "030 040", "within_m": 300}, "units": 6, "mode": "patrol"},
    ]}],
    "events": [{"at": {"between": ["8:00", "14:00"]}, "action": "kill_station", "station": "Alpha"}],
}


def test_the_same_seed_draws_the_same_battle():
    first, seed, drawn = scenario.draw(TEMPLATE, 7)
    again, _, drawn_again = scenario.draw(TEMPLATE, 7)
    assert seed == 7 and first == again and drawn == drawn_again
    assert TEMPLATE["enemies"][0].keys() == {"one_of"}  # the template itself is left alone


def test_every_kind_of_draw_lands_in_range():
    ids = set()
    for seed in range(60):
        raw, _, drawn = scenario.draw(TEMPLATE, seed)
        enemy = raw["enemies"][0]
        ids.add(enemy["id"])
        if enemy["id"] == "Road":
            assert 4 <= enemy["units"] <= 8
        else:
            assert math.dist(parse_grid(enemy["at"], 0)[0], parse_grid("030 040", 0)[0]) <= 300 + 142
        assert parse_time("8:00") <= parse_time(raw["events"][0]["at"]) <= parse_time("14:00")
        assert ["enemies[0]", enemy] in drawn or ["enemies[0]", {**enemy}] in drawn
    assert ids == {"Road", "Ridge"}  # both turn up


def test_a_scenario_with_draws_still_builds():
    built = scenario.build(TEMPLATE)
    assert built.enemies[0]["id"] in {"Road", "Ridge"}


@pytest.mark.parametrize(("bad", "words"), [
    ({"one_of": []}, "one_of needs a list"),
    ({"between": [1]}, "between needs"),
])
def test_bad_draws_are_refused(bad, words):
    with pytest.raises(ValueError, match=words):
        scenario.draw({**TEMPLATE, "time_limit": bad})


def test_a_variant_adds_its_entries_together():
    raw = {**TEMPLATE, "variant": {"one_of": [
        {"events": [{"at": "6:00", "action": "kill_station", "station": "Alpha"}],
         "enemies": [{"id": "Raiders", "at": "019 024", "units": 6, "mode": "hold"}]},
        {"events": [], "enemies": [{"id": "Raiders", "at": "021 031", "units": 6, "mode": "hold"}]}]}}
    seen = set()
    for seed in range(20):
        resolved, _, _ = scenario.draw(raw, seed)
        assert "variant" not in resolved and len(resolved["enemies"]) == 2
        raiders = resolved["enemies"][1]["at"]
        assert (raiders == "019 024") == (len(resolved["events"]) == 2)  # drawn together, or not at all
        seen.add(raiders)
    assert seen == {"019 024", "021 031"}
