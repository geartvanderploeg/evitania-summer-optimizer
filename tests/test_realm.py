"""Tests for the realm event upgrade optimizer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from optimizers import realm
from optimizers.realm import (
    Config,
    baseline_pps,
    dps,
    expand_costs,
    load_upgrades,
    optimal_ratio_staircase,
    optimize,
    parts_per_sec_for,
)


REPO_ROOT = Path(__file__).parent.parent
UPGRADES = load_upgrades(REPO_ROOT / "docs" / "realm-event" / "data.json")


# ---------- Cost expansion ----------

def test_expand_formula_14x():
    assert expand_costs("14x", 5) == [14, 28, 42, 56, 70]


def test_expand_formula_10x_plus_5():
    assert expand_costs("10x + 5", 3) == [15, 25, 35]


def test_expand_array_with_question_caps():
    assert expand_costs([60, 84, 118, 165, "?", "?"], 6) == [60, 84, 118, 165]


def test_expand_array_with_question_x_n_caps():
    assert expand_costs([80, 112, 157, "? x 47"], 50) == [80, 112, 157]


def test_expand_full_array():
    assert expand_costs([10, 20, 30], 3) == [10, 20, 30]


def test_load_caps_drop_rate_to_4():
    """Drop-Rate has 4 known + 6 unknown — effective max-level should be 4."""
    assert UPGRADES["Drop-Rate"]["max-level"] == 4
    assert UPGRADES["Drop-Rate"]["max-level-declared"] == 10


# ---------- Pure-math sanity ----------

def test_dps_baseline():
    # L_dmg=0, L_cc=0, L_cd=0, L_as=0 → DPS = 1·1·1 = 1
    assert dps(0, 0, 0, 0) == pytest.approx(1.0)


def test_dps_one_damage_level():
    # L_dmg=1: damage = 4, AS=1, crit term=1 → DPS = 4
    assert dps(1, 0, 0, 0) == pytest.approx(4.0)


def test_dps_full_crit_full_cd():
    # L_cc=20 → cc=1.0; L_cd=10 → crit_mult = 1.5+1.5=3
    # avg = 0 + 1·3 = 3; DPS = 1·1·3 = 3
    assert dps(0, 20, 10, 0) == pytest.approx(3.0)


def test_baseline_pps_matches_spec():
    # baseline: DPS=1, EnemyHP=10, 3·K_cleave=0.3, spawn≈1/9 → spawn-limited
    # PartsPerSec ≈ 1/9 ≈ 0.111
    assert baseline_pps() == pytest.approx(1 / 9, rel=1e-9)


@pytest.mark.parametrize("L_dmg,L_cc,L_cd,L_dr,L_as,L_es,L_eb,expected_ratio,why", [
    (0, 0, 0, 0, 0, 0, 0, 1.0, "baseline"),
    (1, 0, 0, 0, 0, 0, 0, 1.0, "L_dmg=1 alone: still spawn-limited"),
    (0, 0, 0, 0, 0, 10, 0, 2.7, "L_es=10: spawn_cd=0.5, kill-limited at 0.3/s"),
    (0, 0, 0, 0, 0, 0, 1, 2.0, "L_eb=1: spawn-limited, parts/kill doubles"),
    (0, 20, 10, 0, 0, 0, 0, 1.0, "Full crits but still spawn-limited"),
])
def test_pps_ratio_spot_checks(L_dmg, L_cc, L_cd, L_dr, L_as, L_es, L_eb, expected_ratio, why):
    pps = parts_per_sec_for(L_dmg, L_cc, L_cd, L_dr, L_as, L_es, L_eb)
    ratio = pps / baseline_pps()
    assert ratio == pytest.approx(expected_ratio, rel=1e-6), (
        f"{why}: got ratio={ratio:.4f}, expected {expected_ratio}"
    )


# ---------- Optimization smoke ----------

def test_optimum_at_budget_zero_is_baseline():
    r = optimize(UPGRADES, 0)
    assert r.optimum.cost == 0
    assert r.optimum.parts_per_sec == pytest.approx(r.baseline_pps)
    assert r.next_improvement is not None
    assert r.next_improvement.cost > 0
    assert r.next_improvement.parts_per_sec > r.baseline_pps


def test_negative_budget_raises():
    with pytest.raises(ValueError):
        optimize(UPGRADES, -1)


def test_non_int_budget_raises():
    with pytest.raises(ValueError):
        optimize(UPGRADES, 100.0)


def test_staircase_is_strictly_monotonic():
    s = optimal_ratio_staircase(UPGRADES)
    assert len(s) >= 2
    for a, b in zip(s, s[1:]):
        assert b.cost > a.cost
        assert b.parts_per_sec > a.parts_per_sec


def test_staircase_starts_at_baseline():
    s = optimal_ratio_staircase(UPGRADES)
    first = s[0]
    assert first.cost == 0
    assert first.parts_per_sec == pytest.approx(baseline_pps())


def test_optimum_is_actually_optimal_among_affordable():
    """At a fixed budget, no enumerated config should exceed the optimum's pps."""
    budget = 500
    r = optimize(UPGRADES, budget)
    dmg_cum = UPGRADES["Damage-dealt"]["cumulative-cost"]
    cc_cum = UPGRADES["Chance-to-Crit"]["cumulative-cost"]
    cd_cum = UPGRADES["Crit-Damage"]["cumulative-cost"]
    as_cum = UPGRADES["Attack-Speed"]["cumulative-cost"]
    dr_cum = UPGRADES["Drop-Rate"]["cumulative-cost"]
    es_cum = UPGRADES["Enemy-Spawn"]["cumulative-cost"]
    eb_cum = UPGRADES["Enemy-Buff"]["cumulative-cost"]
    # Brute-force a *reduced* search (cap each at <=3) and verify optimum from
    # decomposed search is at least as good for any affordable reduced-space config.
    for L_dmg in range(min(3, len(dmg_cum) - 1) + 1):
        for L_cc in range(min(3, len(cc_cum) - 1) + 1):
            for L_cd in range(min(3, len(cd_cum) - 1) + 1):
                for L_dr in range(min(3, len(dr_cum) - 1) + 1):
                    for L_as in range(min(3, len(as_cum) - 1) + 1):
                        for L_es in range(min(3, len(es_cum) - 1) + 1):
                            for L_eb in range(min(3, len(eb_cum) - 1) + 1):
                                cost = (dmg_cum[L_dmg] + cc_cum[L_cc] + cd_cum[L_cd]
                                        + dr_cum[L_dr] + as_cum[L_as]
                                        + es_cum[L_es] + eb_cum[L_eb])
                                if cost > budget:
                                    continue
                                pps = parts_per_sec_for(
                                    L_dmg, L_cc, L_cd, L_dr, L_as, L_es, L_eb
                                )
                                assert pps <= r.optimum.parts_per_sec + 1e-9, (
                                    f"reduced ({L_dmg},{L_cc},{L_cd},{L_dr},{L_as},{L_es},{L_eb})"
                                    f" cost={cost} pps={pps} beats optimum pps={r.optimum.parts_per_sec}"
                                )


def test_next_improvement_strictly_beats_optimum():
    for budget in [0, 50, 200, 500, 1000, 2000]:
        r = optimize(UPGRADES, budget)
        if r.next_improvement is not None:
            assert r.next_improvement.parts_per_sec > r.optimum.parts_per_sec
            assert r.next_improvement.cost > 0
