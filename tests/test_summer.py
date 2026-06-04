"""Tests for the summer event upgrade optimizer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from optimizers.summer import (
    Config,
    cumulative_costs,
    enumerate_configs,
    load_upgrades,
    optimal_ratio_staircase,
    optimize,
    render,
)


REPO_ROOT = Path(__file__).parent.parent
UPGRADES = load_upgrades(REPO_ROOT / "docs" / "summer-event" / "data.json")


# ---------- Pure-math sanity checks against the spec example ----------

def test_baseline_is_100pct():
    cfgs = {(c.g, c.e, c.d): c for c in enumerate_configs(UPGRADES)}
    base = cfgs[(0, 0, 0)]
    assert base.ratio_num == 2000
    assert base.ratio == 1.0
    assert base.cost == 0


def test_user_example_one_point_in_more_ghosts_is_103pct():
    """Spec: 1 point in More-Ghosts -> 103%."""
    cfgs = {(c.g, c.e, c.d): c for c in enumerate_configs(UPGRADES)}
    c = cfgs[(1, 0, 0)]
    assert c.ratio_num == 2060  # 1.03 * 2000
    assert c.ratio == pytest.approx(1.03)
    assert c.cost == 20


def test_global_max_is_580pct():
    cfgs = {(c.g, c.e, c.d): c for c in enumerate_configs(UPGRADES)}
    c = cfgs[(20, 3, 20)]
    # 1 + 0.03*20 * 4 * 2 = 1 + 4.8 = 5.8
    assert c.ratio_num == 2000 + 3 * 20 * 4 * 40  # = 2000 + 9600 = 11600
    assert c.ratio == pytest.approx(5.8)


def test_global_max_cost_is_2042():
    g_cost = sum(UPGRADES["More-Ghosts"]["cost-per-level"])
    e_cost = sum(UPGRADES["Even-More-Ghosts"]["cost-per-level"])
    d_cost = sum(UPGRADES["More-Drops"]["cost-per-level"])
    assert g_cost == 671
    assert e_cost == 700
    assert d_cost == 671
    assert g_cost + e_cost + d_cost == 2042


# ---------- cumulative_costs ----------

def test_cumulative_costs_basic():
    assert cumulative_costs([10, 20, 30]) == [0, 10, 30, 60]


def test_cumulative_costs_empty():
    assert cumulative_costs([]) == [0]


# ---------- optimize: edge cases ----------

def test_budget_zero_optimum_is_baseline():
    r = optimize(UPGRADES, 0)
    assert (r.optimum.g, r.optimum.e, r.optimum.d) == (0, 0, 0)
    assert r.optimum.cost == 0
    assert r.optimum.ratio_num == 2000


def test_budget_zero_next_improvement_is_one_point_more_ghosts():
    r = optimize(UPGRADES, 0)
    assert r.next_improvement is not None
    nxt = r.next_improvement
    assert (nxt.g, nxt.e, nxt.d) == (1, 0, 0)
    assert nxt.cost == 20
    assert nxt.ratio_num == 2060


def test_budget_at_global_max_has_no_next_improvement():
    r = optimize(UPGRADES, 2042)
    assert (r.optimum.g, r.optimum.e, r.optimum.d) == (20, 3, 20)
    assert r.next_improvement is None


def test_budget_above_global_max_pins_to_global_max():
    r = optimize(UPGRADES, 10_000)
    assert (r.optimum.g, r.optimum.e, r.optimum.d) == (20, 3, 20)
    assert r.next_improvement is None


# ---------- optimize: optimality invariants over all configs ----------

def test_optimum_is_truly_optimal_at_various_budgets():
    """The reported optimum must be the max-ratio config among affordable."""
    for budget in [0, 20, 50, 100, 200, 400, 800, 1500, 2042]:
        r = optimize(UPGRADES, budget)
        for c in enumerate_configs(UPGRADES):
            if c.cost <= budget:
                # No affordable config may have a strictly greater ratio.
                assert c.ratio_num <= r.optimum.ratio_num, (
                    f"budget={budget}: config (g={c.g},e={c.e},d={c.d}) "
                    f"has ratio_num={c.ratio_num} > optimum={r.optimum.ratio_num}"
                )


def test_optimum_cost_within_budget():
    for budget in [0, 20, 50, 100, 200, 400, 800, 1500, 2042]:
        r = optimize(UPGRADES, budget)
        assert r.optimum.cost <= budget


def test_next_improvement_strictly_beats_optimum():
    for budget in [0, 20, 50, 100, 200, 400, 800, 1500]:
        r = optimize(UPGRADES, budget)
        if r.next_improvement is None:
            # Only legal at global max.
            assert r.optimum.ratio_num == 11600
        else:
            assert r.next_improvement.ratio_num > r.optimum.ratio_num


def test_next_improvement_is_cheapest_strict_improver():
    """No strictly better config should cost less than the reported next improvement."""
    for budget in [0, 20, 50, 100, 200, 400, 800, 1500]:
        r = optimize(UPGRADES, budget)
        if r.next_improvement is None:
            continue
        for c in enumerate_configs(UPGRADES):
            if c.ratio_num > r.optimum.ratio_num:
                assert c.cost >= r.next_improvement.cost


# ---------- Tiebreak resolution order ----------

def test_optimum_prefers_min_cost_among_equal_ratios():
    """If two configs have equal ratio, the cheaper one should win."""
    r = optimize(UPGRADES, 2042)
    # Among affordable configs with the optimum's ratio, optimum.cost must be min.
    same_ratio = [c for c in enumerate_configs(UPGRADES)
                  if c.cost <= 2042 and c.ratio_num == r.optimum.ratio_num]
    assert r.optimum.cost == min(c.cost for c in same_ratio)


# ---------- Input validation ----------

def test_negative_budget_raises():
    with pytest.raises(ValueError):
        optimize(UPGRADES, -1)


def test_non_int_budget_raises():
    with pytest.raises(ValueError):
        optimize(UPGRADES, 100.0)


def test_load_upgrades_rejects_mismatched_cost_length(tmp_path):
    bad = {
        "More-Ghosts": {"max-level": 3, "cost-per-level": [10, 20]},  # mismatch
        "Even-More-Ghosts": {"max-level": 1, "cost-per-level": [100]},
        "More-Drops": {"max-level": 1, "cost-per-level": [10]},
    }
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        load_upgrades(p)


def test_load_upgrades_rejects_missing_key(tmp_path):
    bad = {"More-Ghosts": {"max-level": 0, "cost-per-level": []}}
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        load_upgrades(p)


# ---------- Render smoke test ----------

def test_render_includes_key_sections():
    r = optimize(UPGRADES, 800)
    out = render(r, 800)
    assert "Budget: 800 coins" in out
    assert "Optimal configuration" in out
    assert "Next improvement" in out
    assert "Drops vs. baseline" in out


def test_render_handles_global_max():
    r = optimize(UPGRADES, 2042)
    out = render(r, 2042)
    assert "already at global maximum" in out


# ---------- Manual ratio cross-check ----------

# ---------- Optimal-ratio staircase ----------

@pytest.fixture(scope="module")
def staircase():
    return optimal_ratio_staircase(enumerate_configs(UPGRADES))


def test_staircase_starts_at_baseline(staircase):
    first = staircase[0]
    assert (first.g, first.e, first.d) == (0, 0, 0)
    assert first.cost == 0
    assert first.ratio_num == 2000


def test_staircase_ends_at_global_max(staircase):
    last = staircase[-1]
    assert (last.g, last.e, last.d) == (20, 3, 20)
    assert last.cost == 2042
    assert last.ratio_num == 11600


def test_staircase_strictly_monotonic(staircase):
    for prev, curr in zip(staircase, staircase[1:]):
        assert curr.cost > prev.cost
        assert curr.ratio_num > prev.ratio_num


def test_staircase_consistent_with_optimize_exhaustive(staircase):
    """For every step, optimize() at that exact cost returns that ratio;
    and budgets just below the next step return the previous step's ratio."""
    for i, step in enumerate(staircase):
        r = optimize(UPGRADES, step.cost)
        assert r.optimum.ratio_num == step.ratio_num, (
            f"step {i}: optimize({step.cost}) gave {r.optimum.ratio_num}, "
            f"expected {step.ratio_num}"
        )
        if i + 1 < len(staircase):
            mid_budget = staircase[i + 1].cost - 1
            r_mid = optimize(UPGRADES, mid_budget)
            assert r_mid.optimum.ratio_num == step.ratio_num, (
                f"step {i}: optimize({mid_budget}) (just below next step) gave "
                f"{r_mid.optimum.ratio_num}, expected {step.ratio_num}"
            )


@pytest.mark.parametrize("g,e,d,expected_ratio", [
    (0, 0, 0, 1.00),
    (1, 0, 0, 1.03),
    (10, 0, 0, 1.30),
    (10, 1, 0, 1.60),       # 1 + 0.3*2 = 1.6
    (10, 0, 10, 1.45),      # 1 + 0.3 * 1 * 1.5 = 1.45
    (10, 1, 10, 1.90),      # 1 + 0.3 * 2 * 1.5 = 1.9
    (20, 3, 20, 5.80),
])
def test_formula_matches_manual_calculation(g, e, d, expected_ratio):
    cfgs = {(c.g, c.e, c.d): c for c in enumerate_configs(UPGRADES)}
    c = cfgs[(g, e, d)]
    assert c.ratio == pytest.approx(expected_ratio)
