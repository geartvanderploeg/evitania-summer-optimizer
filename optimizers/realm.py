"""Realm event upgrade optimizer.

Objective: maximize Card Parts per second (UI displays per-minute = 60 × pps).

Spawn model: **per-slot respawn**. The map has 20 spawn slots; when an enemy
dies, its slot enters a `spawn_cd`-second cooldown before respawning.
Effective spawn rate at any time is `N_dead / spawn_cd`, not `1/spawn_cd`.

Combat: cleave hits up to 3 enemies per attack. Per-target kill rate
α = DPS / EnemyHP. Assumes map starts full (N_alive = 20).

Steady-state derivation. Let τ = spawn_cd. Set spawn_rate = kill_rate:
  (20 - N_alive) / τ = α · min(N_alive, 3)
- **Case B** (α < 17/(3τ), low-DPS): cleave stays saturated. N_alive = 20 - 3ατ > 3.
  kill_rate = 3α (independent of τ).
- **Case A** (α ≥ 17/(3τ), high-DPS): cleave de-saturates. N_alive = 20/(1+ατ) ≤ 3.
  kill_rate = 20α / (1 + ατ); asymptotes to 20/τ.

The boundary is continuous: both branches give 17/τ at α = 17/(3τ).

PartsPerSec = kill_rate · (1 + 0.10·L_dr) · (1 + L_eb)

In Case B, L_eb cancels (HP doubles, parts/kill doubles → net zero) and L_es is
irrelevant (τ doesn't appear). L_eb and L_es only help once DPS pushes α past
the Case A threshold.

Other model parameters (crit base 1.5):
    Damage         = 1 + 3·L_dmg
    AttackSpeed    = 1 + 0.07·L_as
    crit_chance    = min(1, 0.05·L_cc)
    crit_mult      = 1.5 + 0.15·L_cd
    avg_dmg_mult   = (1 - cc) + cc · crit_mult
    DPS            = Damage · AttackSpeed · avg_dmg_mult
    EnemyHP        = 10 · (1 + L_eb)
    spawn_cd       = max(0.5, 9 · (1 - 0.10·L_es))

Search space (~1.5B) is solved by decomposition:
  inner: (L_dmg, L_cc, L_cd, L_as) → DPS Pareto frontier
  outer: (L_dr, L_es, L_eb) discrete enumeration
  combine: cross-product of outer × inner frontier, then staircase sweep.

Movespeed is excluded — no contribution to parts/sec in this model.
"""

from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# Keys we use from data.json. Others (e.g. Movespeed) are read but ignored.
INNER_KEYS = ("Damage-dealt", "Chance-to-Crit", "Crit-Damage", "Attack-Speed")
OUTER_KEYS = ("Drop-Rate", "Enemy-Spawn", "Enemy-Buff")
RELEVANT_KEYS = INNER_KEYS + OUTER_KEYS

EPS = 1e-12


@dataclass(frozen=True)
class Config:
    L_dmg: int
    L_cc: int
    L_cd: int
    L_dr: int
    L_as: int
    L_es: int
    L_eb: int
    cost: int
    parts_per_sec: float

    @property
    def parts_per_min(self) -> float:
        return 60.0 * self.parts_per_sec


@dataclass
class Result:
    optimum: Config
    next_improvement: Config | None
    baseline_pps: float

    def ratio(self, cfg: Config) -> float:
        return cfg.parts_per_sec / self.baseline_pps


# ---------- Cost expansion ----------

_FORMULA_RE = re.compile(r"^\s*(\d+)\s*x\s*(?:\+\s*(\d+))?\s*$")


def _evaluate_formula(spec: str, x: int) -> int:
    m = _FORMULA_RE.match(spec)
    if not m:
        raise ValueError(f"Unrecognized cost-per-level formula: {spec!r}")
    a = int(m.group(1))
    b = int(m.group(2) or 0)
    return a * x + b


def expand_costs(spec, declared_max_level: int) -> list[int]:
    """Expand a cost-per-level spec into a list, capping at unknown entries.

    Forms supported:
      - formula string e.g. "14x", "10x + 5" → full array up to declared_max_level
      - explicit list of ints, possibly with "?" or "? x N" entries → cap at first unknown
    """
    if isinstance(spec, str):
        return [_evaluate_formula(spec, x) for x in range(1, declared_max_level + 1)]
    if isinstance(spec, list):
        out: list[int] = []
        for entry in spec:
            if isinstance(entry, int):
                out.append(entry)
            elif isinstance(entry, str):
                # "?" or "? x N" both indicate unknown — cap here.
                break
            else:
                raise ValueError(f"Unsupported cost entry: {entry!r}")
        return out
    raise ValueError(f"Unsupported cost-per-level type: {type(spec).__name__}")


def cumulative_costs(per_level: list[int]) -> list[int]:
    cum = [0]
    running = 0
    for c in per_level:
        running += c
        cum.append(running)
    return cum


# ---------- Load ----------

def load_upgrades(path: Path) -> dict:
    with path.open() as f:
        raw = json.load(f)
    out: dict[str, dict] = {}
    for key in RELEVANT_KEYS:
        if key not in raw:
            raise ValueError(f"data.json missing required key: {key}")
        entry = raw[key]
        declared = entry["max-level"]
        spec = entry["cost-per-level"]
        expanded = expand_costs(spec, declared)
        effective = len(expanded)
        out[key] = {
            "max-level": effective,
            "max-level-declared": declared,
            "cost-per-level": expanded,
            "cumulative-cost": cumulative_costs(expanded),
        }
    return out


# ---------- Math primitives ----------

def dps(L_dmg: int, L_cc: int, L_cd: int, L_as: int) -> float:
    damage = 1 + 3 * L_dmg
    attack_speed = 1 + 0.07 * L_as
    crit_chance = min(1.0, 0.05 * L_cc)
    crit_mult = 1.5 + 0.15 * L_cd
    avg = (1 - crit_chance) + crit_chance * crit_mult
    return damage * attack_speed * avg


def steady_state_kill_rate(alpha: float, spawn_cd: float) -> float:
    """Per-slot respawn steady state with cleave×3, map-starts-full.
    Case B (α < 17/(3τ)): kill_rate = 3α.  Case A: kill_rate = 20α/(1+ατ).
    """
    if alpha <= 0 or spawn_cd <= 0:
        return 0.0
    threshold = 17.0 / (3 * spawn_cd)
    if alpha < threshold:
        return 3 * alpha
    return 20 * alpha / (1 + alpha * spawn_cd)


def parts_per_sec_for(
    L_dmg: int, L_cc: int, L_cd: int, L_dr: int, L_as: int, L_es: int, L_eb: int
) -> float:
    """Direct computation used for tests and the cross-check brute force."""
    enemy_hp = 10.0 * (1 + L_eb)
    parts_per_kill = (1 + 0.10 * L_dr) * (1 + L_eb)
    spawn_cd = max(0.5, 9.0 * (1 - 0.10 * L_es))
    alpha = dps(L_dmg, L_cc, L_cd, L_as) / enemy_hp
    return steady_state_kill_rate(alpha, spawn_cd) * parts_per_kill


def baseline_pps() -> float:
    return parts_per_sec_for(0, 0, 0, 0, 0, 0, 0)


# ---------- Search ----------

def _enumerate_inner(upgrades: dict):
    """Yield (cost_inner, dps_val, (L_dmg, L_cc, L_cd, L_as))."""
    dmg_cum = upgrades["Damage-dealt"]["cumulative-cost"]
    cc_cum = upgrades["Chance-to-Crit"]["cumulative-cost"]
    cd_cum = upgrades["Crit-Damage"]["cumulative-cost"]
    as_cum = upgrades["Attack-Speed"]["cumulative-cost"]
    dmg_max = upgrades["Damage-dealt"]["max-level"]
    cc_max = upgrades["Chance-to-Crit"]["max-level"]
    cd_max = upgrades["Crit-Damage"]["max-level"]
    as_max = upgrades["Attack-Speed"]["max-level"]
    for L_dmg, L_cc, L_cd, L_as in itertools.product(
        range(dmg_max + 1), range(cc_max + 1), range(cd_max + 1), range(as_max + 1)
    ):
        cost = dmg_cum[L_dmg] + cc_cum[L_cc] + cd_cum[L_cd] + as_cum[L_as]
        yield cost, dps(L_dmg, L_cc, L_cd, L_as), (L_dmg, L_cc, L_cd, L_as)


def _dps_frontier(inner_iter) -> list[tuple[int, float, tuple]]:
    """Pareto frontier: (cost asc, DPS strictly increasing)."""
    ordered = sorted(inner_iter, key=lambda x: (x[0], -x[1]))
    out: list[tuple[int, float, tuple]] = []
    best = -1.0
    for cost, d, cfg in ordered:
        if d > best + EPS:
            out.append((cost, d, cfg))
            best = d
    return out


def _enumerate_outer(upgrades: dict):
    """Yield (cost_outer, spawn_cd, parts_factor, hp_factor, (L_dr, L_es, L_eb))."""
    dr_cum = upgrades["Drop-Rate"]["cumulative-cost"]
    es_cum = upgrades["Enemy-Spawn"]["cumulative-cost"]
    eb_cum = upgrades["Enemy-Buff"]["cumulative-cost"]
    dr_max = upgrades["Drop-Rate"]["max-level"]
    es_max = upgrades["Enemy-Spawn"]["max-level"]
    eb_max = upgrades["Enemy-Buff"]["max-level"]
    for L_dr, L_es, L_eb in itertools.product(
        range(dr_max + 1), range(es_max + 1), range(eb_max + 1)
    ):
        cost = dr_cum[L_dr] + es_cum[L_es] + eb_cum[L_eb]
        spawn_cd = max(0.5, 9.0 * (1 - 0.10 * L_es))
        parts_factor = (1 + 0.10 * L_dr) * (1 + L_eb)
        hp_factor = 1 + L_eb
        yield cost, spawn_cd, parts_factor, hp_factor, (L_dr, L_es, L_eb)


def _all_candidates(upgrades: dict) -> list[Config]:
    """Cross-product of outer × inner DPS frontier — every Pareto-optimal candidate."""
    inner_front = _dps_frontier(_enumerate_inner(upgrades))
    candidates: list[Config] = []
    for cost_o, spawn_cd, parts_factor, hp_factor, outer_cfg in _enumerate_outer(upgrades):
        L_dr, L_es, L_eb = outer_cfg
        for cost_i, dps_val, inner_cfg in inner_front:
            L_dmg, L_cc, L_cd, L_as = inner_cfg
            alpha = dps_val / (10 * hp_factor)
            k_eff = steady_state_kill_rate(alpha, spawn_cd)
            pps = k_eff * parts_factor
            candidates.append(Config(
                L_dmg=L_dmg, L_cc=L_cc, L_cd=L_cd, L_dr=L_dr,
                L_as=L_as, L_es=L_es, L_eb=L_eb,
                cost=cost_o + cost_i, parts_per_sec=pps,
            ))
    return candidates


def optimal_ratio_staircase(upgrades: dict) -> list[Config]:
    """Configs sorted by ascending cost where parts_per_sec strictly increases."""
    candidates = _all_candidates(upgrades)
    ordered = sorted(candidates, key=lambda c: (c.cost, -c.parts_per_sec))
    out: list[Config] = []
    best = -1.0
    for c in ordered:
        if c.parts_per_sec > best + EPS:
            out.append(c)
            best = c.parts_per_sec
    return out


def optimize(upgrades: dict, budget: int) -> Result:
    if not isinstance(budget, int) or budget < 0:
        raise ValueError(f"budget must be a non-negative integer, got {budget!r}")

    staircase = optimal_ratio_staircase(upgrades)
    # Last step with cost <= budget.
    optimum: Config | None = None
    for c in staircase:
        if c.cost <= budget:
            optimum = c
        else:
            break
    if optimum is None:
        # staircase always starts at (0, baseline) so this can only happen if empty.
        raise RuntimeError("staircase is empty")

    # Next improvement: cheapest step with parts_per_sec > optimum's.
    next_improvement: Config | None = None
    for c in staircase:
        if c.parts_per_sec > optimum.parts_per_sec + EPS:
            next_improvement = c
            break

    return Result(
        optimum=optimum,
        next_improvement=next_improvement,
        baseline_pps=baseline_pps(),
    )


# ---------- CLI render ----------

def _row(name: str, lvl: int, upgrades: dict) -> str:
    declared = upgrades[name]["max-level-declared"]
    effective = upgrades[name]["max-level"]
    if effective < declared:
        return f"  {name:<18}: {lvl:>2} / {effective}  (cap; unknown cost above)"
    return f"  {name:<18}: {lvl:>2} / {effective}"


def _ratio_str(cfg: Config, baseline_pps_val: float) -> str:
    ratio = cfg.parts_per_sec / baseline_pps_val
    return f"{ratio * 100:.1f}%"


def render(result: Result, budget: int) -> str:
    opt = result.optimum
    base = result.baseline_pps
    lines = []
    lines.append(f"Budget: {budget} Card Parts")
    lines.append("Optimal configuration:")
    name_to_lvl = {
        "Damage-dealt": opt.L_dmg, "Chance-to-Crit": opt.L_cc,
        "Crit-Damage": opt.L_cd, "Drop-Rate": opt.L_dr,
        "Attack-Speed": opt.L_as, "Enemy-Spawn": opt.L_es,
        "Enemy-Buff": opt.L_eb,
    }
    # Re-load upgrades isn't available here, so caller passes nothing.
    # The simplest: just list levels with their L value; caller can format
    # detailed caps. For CLI use we pass upgrades through render via a wrapper.
    for n, l in name_to_lvl.items():
        lines.append(f"  {n:<18}: {l:>2}")
    lines.append("  (Movespeed omitted -- excluded from objective)")
    lines.append(f"Cost: {opt.cost} ({budget - opt.cost} unspent of {budget})")
    lines.append(f"Card Parts gained: {_ratio_str(opt, base)} of baseline "
                 f"(absolute {opt.parts_per_sec:.4f}/s)")

    lines.append("")
    lines.append("Next improvement:")
    nxt = result.next_improvement
    if nxt is None:
        lines.append("  (already at global maximum)")
    else:
        nxt_levels = {
            "Damage-dealt": nxt.L_dmg, "Chance-to-Crit": nxt.L_cc,
            "Crit-Damage": nxt.L_cd, "Drop-Rate": nxt.L_dr,
            "Attack-Speed": nxt.L_as, "Enemy-Spawn": nxt.L_es,
            "Enemy-Buff": nxt.L_eb,
        }
        for n, l in nxt_levels.items():
            lines.append(f"  {n:<18}: {l:>2}")
        lines.append(f"Cost: {nxt.cost} (+{nxt.cost - opt.cost} beyond current optimum)")
        delta_b = nxt.cost - budget
        if delta_b > 0:
            lines.append(f"  +{delta_b} beyond current budget (need to farm {delta_b} more)")
        else:
            lines.append(f"  affordable within current budget ({-delta_b} to spare)")
        lines.append(f"New gain: {_ratio_str(nxt, base)} of baseline")

    return "\n".join(lines)


def plot_curve(staircase: list[Config], result: Result, budget: int,
               out_path: Path, show: bool) -> None:
    """Render the Realm staircase to PNG."""
    try:
        import matplotlib
        if not show:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib required for --plot; install with: pip install matplotlib")
        raise SystemExit(1)

    base = result.baseline_pps
    x_max = staircase[-1].cost
    xs = [c.cost for c in staircase] + [x_max]
    ys = [(c.parts_per_sec / base) * 100 for c in staircase]
    ys.append(ys[-1])

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.step(xs, ys, where="post", color="tab:blue", linewidth=1.8, label="Achievable gain %")

    opt = result.optimum
    bx = min(budget, x_max)
    opt_pct = (opt.parts_per_sec / base) * 100
    ax.axvline(bx, color="grey", linestyle="--", linewidth=1.0,
               label=f"Current budget ({budget})")
    ax.plot([bx], [opt_pct], "o", color="tab:blue", markersize=9,
            label=f"Current optimum ({opt.cost}, {opt_pct:.0f}%)")

    if result.next_improvement is not None:
        nxt = result.next_improvement
        nxt_pct = (nxt.parts_per_sec / base) * 100
        ax.plot([nxt.cost], [nxt_pct], "o", markerfacecolor="none",
                markeredgecolor="tab:red", markersize=11, markeredgewidth=2,
                label=f"Next improvement ({nxt.cost}, {nxt_pct:.0f}%)")

    ax.set_xlim(0, x_max)
    ax.set_xlabel("Card Parts available")
    ax.set_ylabel("Card Parts gained (% of baseline)")
    ax.set_title(f"Realm optimum vs. Card Parts budget — {budget} → {opt_pct:.1f}%")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    if show:
        plt.show()
    plt.close(fig)
