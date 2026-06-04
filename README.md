# Evitania Optimizer

Optimisers for upgrade distributions in the events of the game Evitania.

**Live tool:** https://geartvanderploeg.github.io/evitania/

## Events

### Summer event
Given a coin budget, picks the upgrade distribution that maximises drops from ghosts per kill.

Model: `ratio(g, e, d) = 1 + 0.03·g · (1 + e) · (1 + 0.05·d)` where `g` = More-Ghosts (0–20), `e` = Even-More-Ghosts (0–3), `d` = More-Drops (0–20). More-Elites is excluded.

### Realm event
Given a Card Parts budget, picks the upgrade distribution that maximises Card Parts gained per run.

Model (cleave × 3, crit base 1.5×, single-target spawn-vs-kill steady state):
```
PartsPerSec = min(3 · DPS / EnemyHP, 1/spawn_cd) · (1 + 0.10·L_dr) · (1 + L_eb)
```
Movespeed is excluded (no contribution to parts/sec in this model). UI shows ratio vs. the no-upgrade baseline.

## Web tool
Source in `docs/`. Static HTML + vanilla JS + Plotly. No build step. One HTML page per event under its own subpath.

Local preview:
```
python -m http.server 8000
# open http://localhost:8000/docs/
```

## Python CLI
```
python cli.py --event summer --budget 800
python cli.py --event realm  --budget 500
python cli.py --event summer --budget 800 --plot         # save PNG
python cli.py --event summer --budget 800 --plot --show  # also display
python -m pytest                                          # full suite
```

## Layout
```
docs/                      static web tool, deployed via GitHub Pages from /docs
├── index.html             landing page
├── style.css              shared styles
├── shared/menu.js         top-left menu toggle + active highlight
├── summer-event/          per-event folder: index.html, data.json, optimizer.js, view.js
└── realm-event/           same shape
optimizers/                Python math
├── summer.py
└── realm.py
cli.py                     dispatch on --event
tests/                     pytest test suite
```

Each event's `data.json` is the single source of truth — consumed by both the Python CLI and the browser tool.
