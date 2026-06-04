// Summer event UI: load data.json, run optimize() on input, render results + plot.

let upgrades = null;
let staircase = null;

const $ = (id) => document.getElementById(id);

function showError(msg) {
  const el = $("error");
  el.textContent = msg;
  el.classList.remove("hidden");
}

function renderResults(result, budget) {
  $("results").classList.remove("hidden");
  $("plot-section").classList.remove("hidden");

  const opt = result.optimum;
  const tbody = $("optimal-table").querySelector("tbody");
  tbody.innerHTML = "";
  const rows = [
    ["More-Ghosts", opt.g, upgrades["More-Ghosts"]["max-level"]],
    ["Even-More-Ghosts", opt.e, upgrades["Even-More-Ghosts"]["max-level"]],
    ["More-Drops", opt.d, upgrades["More-Drops"]["max-level"]],
  ];
  for (const [name, lvl, max] of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${name}</td><td>${lvl} / ${max}</td>`;
    tbody.appendChild(tr);
  }

  const unspent = budget - opt.cost;
  const overBudget = budget > GLOBAL_MAX_COST ? " (budget exceeds 2042)" : "";
  $("cost-line").textContent = `Cost: ${opt.cost} coins (${unspent} unspent of ${budget})${overBudget}`;
  const pct = formatPct(opt.ratioNum);
  const bonus = formatPct(opt.ratioNum - 2000);
  $("ratio-line").textContent = `Drops vs. baseline: ${pct} (+${bonus} over baseline)`;

  const nextBlock = $("next-block");
  nextBlock.innerHTML = "";
  if (result.nextImprovement === null) {
    const p = document.createElement("p");
    p.textContent = "Already at global maximum — no strictly better configuration exists.";
    nextBlock.appendChild(p);
  } else {
    const nxt = result.nextImprovement;
    const tbl = document.createElement("table");
    tbl.innerHTML = `
      <thead><tr><th>Upgrade</th><th>Level</th></tr></thead>
      <tbody>
        <tr><td>More-Ghosts</td><td>${nxt.g} / ${upgrades["More-Ghosts"]["max-level"]}</td></tr>
        <tr><td>Even-More-Ghosts</td><td>${nxt.e} / ${upgrades["Even-More-Ghosts"]["max-level"]}</td></tr>
        <tr><td>More-Drops</td><td>${nxt.d} / ${upgrades["More-Drops"]["max-level"]}</td></tr>
      </tbody>`;
    nextBlock.appendChild(tbl);

    const deltaOpt = nxt.cost - opt.cost;
    const deltaBudget = nxt.cost - budget;
    const p1 = document.createElement("p");
    p1.textContent = `Cost: ${nxt.cost} coins (+${deltaOpt} beyond current optimum)`;
    nextBlock.appendChild(p1);
    const p2 = document.createElement("p");
    if (deltaBudget > 0) {
      p2.textContent = `Need ${deltaBudget} more coins to reach this.`;
    } else {
      p2.textContent = `Already affordable within your budget (${-deltaBudget} coins to spare).`;
    }
    nextBlock.appendChild(p2);
    const p3 = document.createElement("p");
    p3.textContent = `New drops vs. baseline: ${formatPct(nxt.ratioNum)} (+${formatPct(nxt.ratioNum - 2000)} over baseline)`;
    nextBlock.appendChild(p3);
  }
}

function renderPlot(result, budget) {
  const xs = staircase.map(c => c.cost).concat([GLOBAL_MAX_COST]);
  const ys = staircase.map(c => c.ratioNum / 20).concat([staircase[staircase.length - 1].ratioNum / 20]);

  const opt = result.optimum;
  const budgetX = Math.min(budget, GLOBAL_MAX_COST);

  const traces = [
    {
      x: xs, y: ys, mode: "lines",
      line: { shape: "hv", color: "#1f77b4", width: 2 },
      name: "Achievable drops %",
      hovertemplate: "%{x} coins → %{y:.2f}%<extra></extra>",
    },
    {
      x: [budgetX], y: [opt.ratioNum / 20], mode: "markers",
      marker: { color: "#1f77b4", size: 12 },
      name: `Current optimum (${opt.cost} coins)`,
      hovertemplate: "Optimum at " + opt.cost + " coins: %{y:.2f}%<extra></extra>",
    },
  ];

  if (result.nextImprovement !== null) {
    const nxt = result.nextImprovement;
    traces.push({
      x: [nxt.cost], y: [nxt.ratioNum / 20], mode: "markers",
      marker: {
        color: "rgba(0,0,0,0)", size: 14,
        line: { color: "#d62728", width: 2.5 },
      },
      name: `Next improvement (${nxt.cost} coins)`,
      hovertemplate: "Next: " + nxt.cost + " coins → %{y:.2f}%<extra></extra>",
    });
  }

  const layout = {
    title: `Optimal drops vs. coin budget — ${budget} coins → ${formatPct(opt.ratioNum)}`,
    xaxis: { title: "Coins available", range: [0, GLOBAL_MAX_COST], gridcolor: "#eee" },
    yaxis: { title: "Drops (% of baseline)", range: [95, 600], gridcolor: "#eee" },
    shapes: [{
      type: "line",
      x0: budgetX, x1: budgetX, y0: 95, y1: 600,
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
    upgrades = await resp.json();
  } catch (err) {
    showError(`Could not load data.json — try refreshing. (${err.message})`);
    return;
  }
  staircase = optimalRatioStaircase(enumerateConfigs(upgrades));
  $("budget").addEventListener("input", compute);
  compute();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
