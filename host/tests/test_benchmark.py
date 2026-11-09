"""The benchmark's seeds (scenarios/commander/benchmark.yaml) against its scenarios: each seed still hides what the file
says, so every model is compared on the same situations, and an edit that would change that fails here."""
import pytest
import yaml

from arma_harness.commander import operator, scenario
from arma_harness.commander.operator import _read_raw
from arma_harness.config import REPO_ROOT

PLAN = yaml.safe_load((REPO_ROOT / "scenarios" / "commander" / "benchmark.yaml").read_text(encoding="utf-8"))
SEEDS = [(name, seed, hidden) for name, seeds in PLAN["scenarios"].items() for seed, hidden in seeds.items()]


@pytest.mark.parametrize(("name", "seed", "hidden"), SEEDS)
def test_each_seed_hides_what_the_benchmark_says(name, seed, hidden):
    resolved, _, _ = scenario.draw(_read_raw(name), seed)
    assert scenario.hidden(resolved) == (hidden or "")


@pytest.mark.parametrize("name", sorted(PLAN["scenarios"]))
def test_each_benchmark_scenario_loads_and_has_six_seeds(name):
    resolved, _, _ = scenario.draw(_read_raw(name), 1)
    loaded = scenario.load(name)
    assert loaded.mission and loaded.time_limit_s > 0 and loaded.objectives
    assert resolved.get("success") and resolved.get("failure"), "a benchmark battle needs a way to win and to lose"
    assert len(PLAN["scenarios"][name]) == 6


def test_the_list_puts_the_benchmark_first_with_its_seeds():
    listing = operator.list_scenarios()
    benchmark, tests = listing.split("Harness tests")
    for name, seeds in PLAN["scenarios"].items():
        line = next(row for row in benchmark.splitlines() if row.strip().startswith(name + " "))
        assert line.endswith("seeds " + ", ".join(str(seed) for seed in seeds)), line
    assert "take_the_village" in tests and "llm_" not in tests and "benchmark " not in listing
