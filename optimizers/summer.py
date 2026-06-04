"""Summer event upgrade optimizer.

Given a coin budget, find the upgrade distribution that maximizes
drops-per-kill relative to the no-ghost baseline (100%).

Model:
    ratio(g, e, d) = 1 + 0.03*g * (1 + e) * (1 + 0.05*d)
Integer form (used for all comparisons to avoid float ties):
    ratio_num     = 2000 + 3*g*(1+e)*(20+d)   # ratio = ratio_num / 2000
    secondary_num = 3*g*(1+e)                 # ghosts per kill, scaled (tiebreaker)

More-Elites is intentionally excluded from the formula and the cost search
(the user's "1 point in More-Ghosts -> 103%" example contains no elite term).
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


GHOST_UPGRADE_KEYS = ("More-Ghosts", "Even-More-Ghosts", "More-Drops")
GLOBAL_MAX_COST = 2042  # sum of all per-level costs across the three ghost upgrades


@dataclass(frozen=True)
class Config:
    g: int
    e: int
    d: int
    cost: int
    ratio_num: int
    secondary_num: int

    @property
    def ratio(self) -> float:
        return self.ratio_num / 2000


@dataclass
class Result:
    optimum: Config
    tied_optima: list[Config]
    next_improvement: Config | None


def load_upgrades(path: Path) -> dict:
    with path.open() as f:
        data = json.load(f)
    for key in GHOST_UPGRADE_KEYS:
        if key not in data:
            raise ValueError(f"data.json missing required key: {key}")
        entry = data[key]
        if len(entry["cost-per-level"]) != entry["max-level"]:
            raise ValueError(
                f"{key}: cost-per-level length ({len(entry['cost-per-level'])}) "
                f"!= max-level ({entry['max-level']})"
            )
    return data


def cumulative_costs(per_level: list[int]) -> list[int]:
    """cum[i] = cost to reach level i. cum[0] = 0."""
    cum = [0]
    running = 0
    for c in per_level:
        running += c
        cum.append(running)
    return cum


def enumerate_configs(upgrades: dict) -> Iterable[Config]:
    g_cum = cumulative_costs(upgrades["More-Ghosts"]["cost-per-level"])
    e_cum = cumulative_costs(upgrades["Even-More-Ghosts"]["cost-per-level"])
    d_cum = cumulative_costs(upgrades["More-Drops"]["cost-per-level"])
    g_max = upgrades["More-Ghosts"]["max-level"]
    e_max = upgrades["Even-More-Ghosts"]["max-level"]
    d_max = upgrades["More-Drops"]["max-level"]
    for g, e, d in itertools.product(range(g_max + 1), range(e_max + 1), range(d_max + 1)):
        cost = g_cum[g] + e_cum[e] + d_cum[d]
        ratio_num = 2000 + 3 * g * (1 + e) * (20 + d)
        secondary_num = 3 * g * (1 + e)
        yield Config(g=g, e=e, d=d, cost=cost, ratio_num=ratio_num, secondary_num=secondary_num)


def optimize(upgrades: dict, budget: int) -> Result:
    if not isinstance(budget, int) or budget < 0:
        raise ValueError(f"budget must be a non-negative integer, got {budget!r}")

    all_configs = list(enumerate_configs(upgrades))
    affordable = [c for c in all_configs if c.cost <= budget]

    # Resolution order: max ratio_num -> min cost -> max secondary_num.
    best_key = max((c.ratio_num, -c.cost, c.secondary_num) for c in affordable)
    optimum_ratio_num, neg_cost, optimum_secondary = best_key
    optimum_cost = -neg_cost
    tied = [
        c for c in affordable
        if c.ratio_num == optimum_ratio_num
        and c.cost == optimum_cost
        and c.secondary_num == optimum_secondary
    ]
    optimum = tied[0]

    # Next improvement: cheapest config with strictly greater ratio_num.
    # On ties: max ratio_num, then max secondary_num.
    better = [c for c in all_configs if c.ratio_num > optimum.ratio_num]
    if not better:
        next_improvement = None
    else:
        min_cost = min(c.cost for c in better)
        candidates = [c for c in better if c.cost == min_cost]
        max_ratio = max(c.ratio_num for c in candidates)
        candidates = [c for c in candidates if c.ratio_num == max_ratio]
        max_sec = max(c.secondary_num for c in candidates)
        candidates = [c for c in candidates if c.secondary_num == max_sec]
        next_improvement = candidates[0]

    return Result(optimum=optimum, tied_optima=tied, next_improvement=next_improvement)


def optimal_ratio_staircase(configs: Iterable[Config]) -> list[Config]:
    """Sorted-by-cost configs whose ratio_num strictly exceeds the running max
    of all strictly-cheaper configs. At equal (cost, ratio_num), tiebreak by
    max secondary_num — matches optimize()'s precedence."""
    ordered = sorted(configs, key=lambda c: (c.cost, -c.ratio_num, -c.secondary_num))
    out: list[Config] = []
    best_ratio = -1
    for c in ordered:
        if c.ratio_num > best_ratio:
            out.append(c)
            best_ratio = c.ratio_num
    return out


def format_pct(ratio_num: int) -> str:
    pct_times_100 = ratio_num * 5
    whole, frac = divmod(pct_times_100, 100)
    if frac == 0:
        return f"{whole}%"
    s = f"{whole}.{frac:02d}"
    return s.rstrip("0").rstrip(".") + "%"


def render(result: Result, budget: int) -> str:
    opt = result.optimum
    lines = []
    lines.append(f"Budget: {budget} coins")
    lines.append("Optimal configuration:")
    lines.append(f"  More-Ghosts        : {opt.g:>2} / 20")
    lines.append(f"  Even-More-Ghosts   : {opt.e:>2} /  3")
    lines.append(f"  More-Drops         : {opt.d:>2} / 20")
    lines.append("  (More-Elites omitted -- out of formula scope)")
    lines.append(f"Cost: {opt.cost} coins  ({budget - opt.cost} unspent of {budget})")
    pct = format_pct(opt.ratio_num)
    bonus = format_pct(opt.ratio_num - 2000)
    lines.append(f"Drops vs. baseline: {pct}  (+{bonus} over baseline)")

    if len(result.tied_optima) > 1:
        lines.append("")
        lines.append(f"!! DEGENERACY FLAG: {len(result.tied_optima)} optimal configurations tied on")
        lines.append("   (ratio, cost, secondary). All tied configs:")
        for c in result.tied_optima:
            lines.append(f"   g={c.g:>2} e={c.e} d={c.d:>2}  cost={c.cost}  ratio={format_pct(c.ratio_num)}")

    lines.append("")
    lines.append("Next improvement:")
    nxt = result.next_improvement
    if nxt is None:
        lines.append("  (already at global maximum -- no strictly better configuration exists)")
    else:
        lines.append(f"  More-Ghosts        : {nxt.g:>2} / 20")
        lines.append(f"  Even-More-Ghosts   : {nxt.e:>2} /  3")
        lines.append(f"  More-Drops         : {nxt.d:>2} / 20")
        lines.append(f"Cost: {nxt.cost} coins")
        lines.append(f"  +{nxt.cost - opt.cost} coins beyond current optimum")
        delta_budget = nxt.cost - budget
        if delta_budget > 0:
            lines.append(f"  +{delta_budget} coins beyond your current budget (need to farm {delta_budget} more)")
        else:
            lines.append(f"  affordable within current budget ({-delta_budget} coins to spare)")
        pct_nxt = format_pct(nxt.ratio_num)
        bonus_nxt = format_pct(nxt.ratio_num - 2000)
        lines.append(f"New drops vs. baseline: {pct_nxt}  (+{bonus_nxt} over baseline)")

    return "\n".join(lines)


def plot_curve(
    staircase: list[Config],
    result: Result,
    budget: int,
    out_path: Path,
    show: bool,
) -> None:
    """Render the optimal-ratio staircase to out_path (and optionally show)."""
    try:
        import matplotlib

        if not show:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib required for --plot; install with: pip install matplotlib")
        raise SystemExit(1)

    x_max = GLOBAL_MAX_COST
    xs = [c.cost for c in staircase] + [x_max]
    ys = [c.ratio_num / 20.0 for c in staircase] + [staircase[-1].ratio_num / 20.0]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.step(xs, ys, where="post", color="tab:blue", linewidth=1.8, label="Achievable drops %")

    opt = result.optimum
    opt_pct = opt.ratio_num / 20.0
    budget_line_x = min(budget, x_max)
    ax.axvline(budget_line_x, color="grey", linestyle="--", linewidth=1.0,
               label=f"Current budget ({budget} coins)")
    ax.plot([budget_line_x], [opt_pct], "o", color="tab:blue", markersize=9,
            label=f"Current optimum ({opt.cost} coins, {format_pct(opt.ratio_num)})")

    if result.next_improvement is not None:
        nxt = result.next_improvement
        nxt_pct = nxt.ratio_num / 20.0
        ax.plot([nxt.cost], [nxt_pct], "o", markerfacecolor="none",
                markeredgecolor="tab:red", markersize=11, markeredgewidth=2,
                label=f"Next improvement ({nxt.cost} coins, {format_pct(nxt.ratio_num)})")

    ax.set_xlim(0, x_max)
    ax.set_ylim(95, 600)
    ax.set_xlabel("Coins available")
    ax.set_ylabel("Drops (% of baseline, 100% = no ghosts)")

    title = f"Optimal drops vs. coin budget — current: {budget} coins → {format_pct(opt.ratio_num)}"
    if result.next_improvement is None:
        title += " (at global max)"
    if budget > x_max:
        title += " (budget exceeds 2042)"
    ax.set_title(title)

    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left")

    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    if show:
        plt.show()
    plt.close(fig)
