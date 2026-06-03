# Evitania Summer Optimizer

Given a coin budget, pick the upgrade distribution that maximises drops per kill in the Evitania summer event.

**Live tool:** https://geartvanderploeg.github.io/evitania-summer-optimizer/

## What it does
For each input coin amount, computes:
- the optimal levels of More-Ghosts, Even-More-Ghosts, and More-Drops;
- the resulting drops-per-kill ratio vs. the no-ghost baseline (100%);
- the cheapest configuration that strictly improves on that, and how many more coins you need.

Plus a staircase plot from 0 → 2042 coins (the cost of maxing every ghost-affecting upgrade) showing the achievable ratio at every budget.

## Web tool
Source in `docs/`. Static HTML + vanilla JS + Plotly. No build step.

Local preview:
```
python -m http.server 8000
# open http://localhost:8000/docs/
```

## Python CLI
```
python optimizer.py --budget 800
python optimizer.py --budget 800 --plot         # save PNG
python optimizer.py --budget 800 --plot --show  # also display
python -m pytest                                # 32 tests
```

## Model
```
ratio(g, e, d) = 1 + 0.03·g · (1 + e) · (1 + 0.05·d)
```
- `g` = More-Ghosts (0–20): spawn chance = 3·g %
- `e` = Even-More-Ghosts (0–3): ghosts per spawn = 1 + e
- `d` = More-Drops (0–20): per-ghost drop multiplier = 1 + 0.05·d

More-Elites is excluded — the spec's example "1 point in More-Ghosts → 103%" contains no elite term.

Upgrade data lives in `docs/upgrades.json` (single source consumed by both Python and JS).
