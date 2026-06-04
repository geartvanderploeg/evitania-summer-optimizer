// Realm event optimizer (browser port of optimizers/realm.py).
//
// Model (cleave×3, crit base 1.5):
//   Damage         = 1 + 3·L_dmg
//   AttackSpeed    = 1 + 0.07·L_as
//   crit_chance    = min(1, 0.05·L_cc)
//   crit_mult      = 1.5 + 0.15·L_cd
//   avg_dmg_mult   = (1 - cc) + cc · crit_mult
//   DPS            = Damage · AttackSpeed · avg_dmg_mult
//   EnemyHP        = 10 · (1 + L_eb)
//   parts_per_kill = (1 + 0.10·L_dr) · (1 + L_eb)
//   spawn_cd       = max(0.5, 9 · (1 - 0.10·L_es))
//   K_eff          = min(3 · DPS / EnemyHP, 1/spawn_cd)
//   PartsPerSec    = K_eff · parts_per_kill

const INNER_KEYS = ["Damage-dealt", "Chance-to-Crit", "Crit-Damage", "Attack-Speed"];
const OUTER_KEYS = ["Drop-Rate", "Enemy-Spawn", "Enemy-Buff"];
const RELEVANT_KEYS = [...INNER_KEYS, ...OUTER_KEYS];
const EPS = 1e-12;

// ---- cost expansion ----
function evaluateFormula(spec, x) {
  const m = /^\s*(\d+)\s*x\s*(?:\+\s*(\d+))?\s*$/.exec(spec);
  if (!m) throw new Error(`Unrecognized cost formula: ${spec}`);
  const a = parseInt(m[1], 10);
  const b = parseInt(m[2] || "0", 10);
  return a * x + b;
}

function expandCosts(spec, declaredMaxLevel) {
  if (typeof spec === "string") {
    const out = [];
    for (let x = 1; x <= declaredMaxLevel; x++) out.push(evaluateFormula(spec, x));
    return out;
  }
  if (Array.isArray(spec)) {
    const out = [];
    for (const entry of spec) {
      if (typeof entry === "number") out.push(entry);
      else break;  // "?" or "? x N" caps
    }
    return out;
  }
  throw new Error(`Unsupported cost-per-level type: ${typeof spec}`);
}

function cumulativeCosts(perLevel) {
  const out = [0];
  let running = 0;
  for (const c of perLevel) { running += c; out.push(running); }
  return out;
}

function loadUpgrades(raw) {
  const out = {};
  for (const key of RELEVANT_KEYS) {
    if (!(key in raw)) throw new Error(`data.json missing required key: ${key}`);
    const entry = raw[key];
    const declared = entry["max-level"];
    const expanded = expandCosts(entry["cost-per-level"], declared);
    out[key] = {
      "max-level": expanded.length,
      "max-level-declared": declared,
      "cost-per-level": expanded,
      "cumulative-cost": cumulativeCosts(expanded),
    };
  }
  return out;
}

// ---- math primitives ----
function dps(L_dmg, L_cc, L_cd, L_as) {
  const damage = 1 + 3 * L_dmg;
  const attackSpeed = 1 + 0.07 * L_as;
  const critChance = Math.min(1, 0.05 * L_cc);
  const critMult = 1.5 + 0.15 * L_cd;
  const avg = (1 - critChance) + critChance * critMult;
  return damage * attackSpeed * avg;
}

function steadyStateKillRate(alpha, spawnCd) {
  // Per-slot respawn, cleave×3, map-starts-full.
  // Case B (α < 17/(3τ)): kill_rate = 3α.  Case A: kill_rate = 20α/(1+ατ).
  if (alpha <= 0 || spawnCd <= 0) return 0;
  const threshold = 17 / (3 * spawnCd);
  if (alpha < threshold) return 3 * alpha;
  return 20 * alpha / (1 + alpha * spawnCd);
}

function partsPerSecFor(L_dmg, L_cc, L_cd, L_dr, L_as, L_es, L_eb) {
  const enemyHP = 10 * (1 + L_eb);
  const ppk = (1 + 0.10 * L_dr) * (1 + L_eb);
  const spawnCd = Math.max(0.5, 9 * (1 - 0.10 * L_es));
  const alpha = dps(L_dmg, L_cc, L_cd, L_as) / enemyHP;
  return steadyStateKillRate(alpha, spawnCd) * ppk;
}

function baselinePps() {
  return partsPerSecFor(0, 0, 0, 0, 0, 0, 0);
}

// ---- search (decomposition) ----
function dpsFrontier(upgrades) {
  const dmgCum = upgrades["Damage-dealt"]["cumulative-cost"];
  const ccCum = upgrades["Chance-to-Crit"]["cumulative-cost"];
  const cdCum = upgrades["Crit-Damage"]["cumulative-cost"];
  const asCum = upgrades["Attack-Speed"]["cumulative-cost"];
  const dmgMax = upgrades["Damage-dealt"]["max-level"];
  const ccMax = upgrades["Chance-to-Crit"]["max-level"];
  const cdMax = upgrades["Crit-Damage"]["max-level"];
  const asMax = upgrades["Attack-Speed"]["max-level"];

  const all = [];
  for (let L_dmg = 0; L_dmg <= dmgMax; L_dmg++) {
    for (let L_cc = 0; L_cc <= ccMax; L_cc++) {
      for (let L_cd = 0; L_cd <= cdMax; L_cd++) {
        for (let L_as = 0; L_as <= asMax; L_as++) {
          const cost = dmgCum[L_dmg] + ccCum[L_cc] + cdCum[L_cd] + asCum[L_as];
          all.push([cost, dps(L_dmg, L_cc, L_cd, L_as), L_dmg, L_cc, L_cd, L_as]);
        }
      }
    }
  }
  all.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
  const front = [];
  let best = -1;
  for (const r of all) {
    if (r[1] > best + EPS) { front.push(r); best = r[1]; }
  }
  return front;
}

function allCandidates(upgrades) {
  const front = dpsFrontier(upgrades);
  const drCum = upgrades["Drop-Rate"]["cumulative-cost"];
  const esCum = upgrades["Enemy-Spawn"]["cumulative-cost"];
  const ebCum = upgrades["Enemy-Buff"]["cumulative-cost"];
  const drMax = upgrades["Drop-Rate"]["max-level"];
  const esMax = upgrades["Enemy-Spawn"]["max-level"];
  const ebMax = upgrades["Enemy-Buff"]["max-level"];

  const out = [];
  for (let L_dr = 0; L_dr <= drMax; L_dr++) {
    for (let L_es = 0; L_es <= esMax; L_es++) {
      for (let L_eb = 0; L_eb <= ebMax; L_eb++) {
        const costO = drCum[L_dr] + esCum[L_es] + ebCum[L_eb];
        const spawnCd = Math.max(0.5, 9 * (1 - 0.10 * L_es));
        const partsFactor = (1 + 0.10 * L_dr) * (1 + L_eb);
        const hpFactor = 1 + L_eb;
        for (const [costI, d, L_dmg, L_cc, L_cd, L_as] of front) {
          const alpha = d / (10 * hpFactor);
          const kEff = steadyStateKillRate(alpha, spawnCd);
          const pps = kEff * partsFactor;
          out.push({
            L_dmg, L_cc, L_cd, L_dr, L_as, L_es, L_eb,
            cost: costO + costI,
            partsPerSec: pps,
          });
        }
      }
    }
  }
  return out;
}

function optimalRatioStaircase(upgrades) {
  const cands = allCandidates(upgrades);
  cands.sort((a, b) => a.cost - b.cost || b.partsPerSec - a.partsPerSec);
  const out = [];
  let best = -1;
  for (const c of cands) {
    if (c.partsPerSec > best + EPS) { out.push(c); best = c.partsPerSec; }
  }
  return out;
}

function optimize(upgrades, budget) {
  if (!Number.isInteger(budget) || budget < 0) {
    throw new Error(`budget must be a non-negative integer, got ${budget}`);
  }
  const staircase = optimalRatioStaircase(upgrades);
  let optimum = null;
  for (const c of staircase) {
    if (c.cost <= budget) optimum = c;
    else break;
  }
  if (optimum === null) throw new Error("staircase empty");

  let nextImprovement = null;
  for (const c of staircase) {
    if (c.partsPerSec > optimum.partsPerSec + EPS) {
      nextImprovement = c;
      break;
    }
  }
  return { optimum, nextImprovement, baselinePps: baselinePps(), staircase };
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    INNER_KEYS, OUTER_KEYS, RELEVANT_KEYS,
    expandCosts, evaluateFormula, cumulativeCosts, loadUpgrades,
    dps, steadyStateKillRate, partsPerSecFor, baselinePps,
    dpsFrontier, allCandidates, optimalRatioStaircase, optimize,
  };
}
