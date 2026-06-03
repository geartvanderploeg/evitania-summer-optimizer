// Summer event upgrade optimizer (browser port of optimizer.py).
//
// Model (matches Python exactly):
//   ratio(g, e, d) = 1 + 0.03*g * (1 + e) * (1 + 0.05*d)
// Integer form for all comparisons:
//   ratioNum     = 2000 + 3*g*(1+e)*(20+d)
//   secondaryNum = 3*g*(1+e)

const GHOST_KEYS = ["More-Ghosts", "Even-More-Ghosts", "More-Drops"];
const GLOBAL_MAX_COST = 2042;

function cumulativeCosts(perLevel) {
  const out = [0];
  let running = 0;
  for (const c of perLevel) {
    running += c;
    out.push(running);
  }
  return out;
}

function enumerateConfigs(upgrades) {
  const gCum = cumulativeCosts(upgrades["More-Ghosts"]["cost-per-level"]);
  const eCum = cumulativeCosts(upgrades["Even-More-Ghosts"]["cost-per-level"]);
  const dCum = cumulativeCosts(upgrades["More-Drops"]["cost-per-level"]);
  const gMax = upgrades["More-Ghosts"]["max-level"];
  const eMax = upgrades["Even-More-Ghosts"]["max-level"];
  const dMax = upgrades["More-Drops"]["max-level"];
  const out = [];
  for (let g = 0; g <= gMax; g++) {
    for (let e = 0; e <= eMax; e++) {
      for (let d = 0; d <= dMax; d++) {
        const cost = gCum[g] + eCum[e] + dCum[d];
        const ratioNum = 2000 + 3 * g * (1 + e) * (20 + d);
        const secondaryNum = 3 * g * (1 + e);
        out.push({ g, e, d, cost, ratioNum, secondaryNum });
      }
    }
  }
  return out;
}

function optimize(upgrades, budget) {
  if (!Number.isInteger(budget) || budget < 0) {
    throw new Error(`budget must be a non-negative integer, got ${budget}`);
  }
  const all = enumerateConfigs(upgrades);
  const affordable = all.filter(c => c.cost <= budget);

  // Resolution order: max ratioNum -> min cost -> max secondaryNum.
  let best = affordable[0];
  for (const c of affordable) {
    if (
      c.ratioNum > best.ratioNum ||
      (c.ratioNum === best.ratioNum && c.cost < best.cost) ||
      (c.ratioNum === best.ratioNum && c.cost === best.cost && c.secondaryNum > best.secondaryNum)
    ) {
      best = c;
    }
  }
  const tied = affordable.filter(c =>
    c.ratioNum === best.ratioNum &&
    c.cost === best.cost &&
    c.secondaryNum === best.secondaryNum
  );

  // Next improvement: cheapest config with strictly greater ratioNum.
  // Ties: max ratioNum, then max secondaryNum.
  const better = all.filter(c => c.ratioNum > best.ratioNum);
  let nextImprovement = null;
  if (better.length > 0) {
    let pick = better[0];
    for (const c of better) {
      if (
        c.cost < pick.cost ||
        (c.cost === pick.cost && c.ratioNum > pick.ratioNum) ||
        (c.cost === pick.cost && c.ratioNum === pick.ratioNum && c.secondaryNum > pick.secondaryNum)
      ) {
        pick = c;
      }
    }
    nextImprovement = pick;
  }

  return { optimum: best, tiedOptima: tied, nextImprovement };
}

function optimalRatioStaircase(configs) {
  // Sort by cost asc; on equal cost, prefer higher ratio, then higher secondary
  // (matches optimize() tiebreak).
  const ordered = [...configs].sort((a, b) =>
    a.cost - b.cost ||
    b.ratioNum - a.ratioNum ||
    b.secondaryNum - a.secondaryNum
  );
  const out = [];
  let bestRatio = -1;
  for (const c of ordered) {
    if (c.ratioNum > bestRatio) {
      out.push(c);
      bestRatio = c.ratioNum;
    }
  }
  return out;
}

function formatPct(ratioNum) {
  // ratioNum / 20 percent, up to 2 decimals, trim trailing zeros.
  const pctTimes100 = ratioNum * 5;
  const whole = Math.trunc(pctTimes100 / 100);
  const frac = pctTimes100 - whole * 100;
  if (frac === 0) return `${whole}%`;
  let s = `${whole}.${String(frac).padStart(2, "0")}`;
  s = s.replace(/0+$/, "").replace(/\.$/, "");
  return s + "%";
}

// Allow Node import for cross-validation against Python.
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    GHOST_KEYS,
    GLOBAL_MAX_COST,
    cumulativeCosts,
    enumerateConfigs,
    optimize,
    optimalRatioStaircase,
    formatPct,
  };
}
