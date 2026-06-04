// Realm event UI: load data.json, run optimize() on input, render results + plot.

let upgrades = null;
let staircase = null;
let baseline = null;
let xMax = null;

const $ = (id) => document.getElementById(id);

const UPGRADE_DISPLAY = [
  ["Damage-dealt", "L_dmg"],
  ["Chance-to-Crit", "L_cc"],
  ["Crit-Damage", "L_cd"],
  ["Drop-Rate", "L_dr"],
  ["Attack-Speed", "L_as"],
  ["Enemy-Spawn", "L_es"],
  ["Enemy-Buff", "L_eb"],
];

function showError(msg) {
  const el = $("error");
  el.textContent = msg;
  el.classList.remove("hidden");
}

function pct(ratio) {
  return `${(ratio * 100).toFixed(1)}%`;
}

function levelCell(name, lvl) {
  const u = upgrades[name];
  const declared = u["max-level-declared"];
  const effective = u["max-level"];
  if (effective < declared) {
    return `${lvl} / ${effective} <span class="note">(cap; unknown cost above)</span>`;
  }
  return `${lvl} / ${effective}`;
}

function buildLevelTable(cfg) {
  const tbl = document.createElement("table");
  tbl.innerHTML = "<thead><tr><th>Upgrade</th><th>Level</th></tr></thead>";
  const tbody = document.createElement("tbody");
  for (const [name, key] of UPGRADE_DISPLAY) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${name}</td><td>${levelCell(name, cfg[key])}</td>`;
    tbody.appendChild(tr);
  }
  tbl.appendChild(tbody);
  return tbl;
}

function renderResults(result, budget) {
  $("results").classList.remove("hidden");
  $("plot-section").classList.remove("hidden");

  const opt = result.optimum;
  const optBlock = $("optimal-block");
  optBlock.innerHTML = "";
  optBlock.appendChild(buildLevelTable(opt));
  const movespeedNote = document.createElement("p");
  movespeedNote.className = "note";
  movespeedNote.textContent = "Movespeed omitted — excluded from objective.";
  optBlock.appendChild(movespeedNote);

  const unspent = budget - opt.cost;
  $("cost-line").textContent = `Cost: ${opt.cost} Card Parts (${unspent} unspent of ${budget})`;
  const optRatio = opt.partsPerSec / baseline;
  $("ratio-line").textContent =
    `Card Parts gained: ${pct(optRatio)} of baseline (+${pct(optRatio - 1)} over baseline)`;

  const nextBlock = $("next-block");
  nextBlock.innerHTML = "";
  if (result.nextImprovement === null) {
    const p = document.createElement("p");
    p.textContent = "Already at global maximum — no strictly better configuration exists.";
    nextBlock.appendChild(p);
  } else {
    const nxt = result.nextImprovement;
    nextBlock.appendChild(buildLevelTable(nxt));
    const deltaOpt = nxt.cost - opt.cost;
    const deltaBudget = nxt.cost - budget;
    const p1 = document.createElement("p");
    p1.textContent = `Cost: ${nxt.cost} Card Parts (+${deltaOpt} beyond current optimum)`;
    nextBlock.appendChild(p1);
    const p2 = document.createElement("p");
    if (deltaBudget > 0) {
      p2.textContent = `Need ${deltaBudget} more Card Parts to reach this.`;
    } else {
      p2.textContent = `Already affordable within your budget (${-deltaBudget} to spare).`;
    }
    nextBlock.appendChild(p2);
    const nxtRatio = nxt.partsPerSec / baseline;
    const p3 = document.createElement("p");
    p3.textContent = `New gain: ${pct(nxtRatio)} of baseline (+${pct(nxtRatio - 1)} over baseline)`;
    nextBlock.appendChild(p3);
  }
}

function renderPlot(result, budget) {
  const xs = staircase.map(c => c.cost).concat([xMax]);
  const ys = staircase.map(c => (c.partsPerSec / baseline) * 100);
  ys.push(ys[ys.length - 1]);

  const opt = result.optimum;
  const budgetX = Math.min(budget, xMax);
  const optPct = (opt.partsPerSec / baseline) * 100;

  const traces = [
    {
      x: xs, y: ys, mode: "lines",
      line: { shape: "hv", color: "#1f77b4", width: 2 },
      name: "Achievable gain %",
      hovertemplate: "%{x} Card Parts → %{y:.1f}%<extra></extra>",
    },
    {
      x: [budgetX], y: [optPct], mode: "markers",
      marker: { color: "#1f77b4", size: 12 },
      name: `Current optimum (${opt.cost} Card Parts)`,
      hovertemplate: "Optimum at " + opt.cost + ": %{y:.1f}%<extra></extra>",
    },
  ];

  if (result.nextImprovement !== null) {
    const nxt = result.nextImprovement;
    const nxtPct = (nxt.partsPerSec / baseline) * 100;
    traces.push({
      x: [nxt.cost], y: [nxtPct], mode: "markers",
      marker: {
        color: "rgba(0,0,0,0)", size: 14,
        line: { color: "#d62728", width: 2.5 },
      },
      name: `Next improvement (${nxt.cost} Card Parts)`,
      hovertemplate: "Next: " + nxt.cost + " → %{y:.1f}%<extra></extra>",
    });
  }

  const yMax = Math.max(...ys, 200) * 1.05;

  const layout = {
    title: `Realm — ${budget} Card Parts → ${pct(opt.partsPerSec / baseline)} of baseline`,
    xaxis: { title: "Card Parts available", range: [0, xMax], gridcolor: "#eee" },
    yaxis: { title: "Card Parts gained (% of baseline)", range: [95, yMax], gridcolor: "#eee" },
    shapes: [{
      type: "line",
      x0: budgetX, x1: budgetX, y0: 95, y1: yMax,
      line: { color: "grey", width: 1, dash: "dash" },
    }],
    legend: { x: 0, y: 1 },
    margin: { l: 60, r: 30, t: 60, b: 50 },
    plot_bgcolor: "#fff",
  };

  Plotly.react("plot", traces, layout, { responsive: true, displayModeBar: false });
}

function compute() {
  const budget = parseInt($("budget").value, 10);
  if (!Number.isInteger(budget) || budget < 0) return;
  const result = optimize(upgrades, budget);
  renderResults(result, budget);
  renderPlot(result, budget);
}

async function init() {
  try {
    const resp = await fetch("data.json");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const raw = await resp.json();
    upgrades = loadUpgrades(raw);
  } catch (err) {
    showError(`Could not load data.json — try refreshing. (${err.message})`);
    return;
  }
  staircase = optimalRatioStaircase(upgrades);
  baseline = baselinePps();
  xMax = staircase[staircase.length - 1].cost;
  $("budget").addEventListener("input", compute);
  compute();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
