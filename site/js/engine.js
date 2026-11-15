// Marswalk Ops - browser planning engine (pure functions, no DOM).
// Runs inside the Web Worker (worker.js) and in Node for the Python-vs-JS parity test.
//
// It is a line-by-line port of the Python reference planner:
//   planner/grid.py   (10 m grid, 16-connected moves, no corner cutting)
//   planner/cost.py   (NASA walking model: time, energy, hazard; scalar weights)
//   planner/astar.py  (A* with the admissible heuristic c_min * straight-line distance)
//   planner/safety.py (walk-home field), planner/run_plan.py (timeline, safety checks),
//   planner/montecarlo.py (risk model)
// Floating-point operations are written in the same order as numpy evaluates them, so the
// costs match Python exactly (tests/test_js_engine.py checks this).
// Grid convention: row 0 = NORTH edge; x east, y north, metres; cell (r, c) centre at
// x = (c + 0.5) * cell, y = (rows - r - 0.5) * cell.

// ---------------------------------------------------------------- moves (same order as grid.py)
export const MOVES = [];
for (const [dr, dc] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) MOVES.push([dr, dc, []]);
for (const [dr, dc] of [[-1, -1], [-1, 1], [1, -1], [1, 1]]) MOVES.push([dr, dc, [[dr, 0], [0, dc]]]);
for (const [dr, dc] of [[-1, -2], [-1, 2], [1, -2], [1, 2]]) {
  const s = dc > 0 ? 1 : -1;
  MOVES.push([dr, dc, [[0, s], [dr, s]]]);
}
for (const [dr, dc] of [[-2, -1], [-2, 1], [2, -1], [2, 1]]) {
  const s = dr > 0 ? 1 : -1;
  MOVES.push([dr, dc, [[s, 0], [s, dc]]]);
}
const K = MOVES.length;

const DEG2RAD = Math.PI / 180.0;   // same constant CPython's math.radians uses

// ---------------------------------------------------------------- params helpers
export function pv(params, dotted) {
  let node = params;
  for (const k of dotted.split('.')) node = node[k];
  return node.value;
}

// ---------------------------------------------------------------- grid
export function decodeGrid(meta, buffer) {
  const n = meta.rows * meta.cols;
  const out = { rows: meta.rows, cols: meta.cols, cell: meta.cell_m, n };
  for (const a of meta.arrays) {
    let src;
    if (a.dtype === 'float32') src = new Float32Array(buffer, a.offset, a.count);
    else if (a.dtype === 'uint16') src = new Uint16Array(buffer, a.offset, a.count);
    else if (a.dtype === 'uint8') src = new Uint8Array(buffer, a.offset, a.count);
    else throw new Error('unknown dtype ' + a.dtype);
    const v = new Float64Array(n);
    for (let i = 0; i < n; i++) v[i] = src[i] * a.scale;   // numpy: astype(float64) * scale
    out[a.name] = v;
  }
  return { rows: out.rows, cols: out.cols, cell: out.cell, n,
           elev: out.elev_m, slope: out.slope_deg, rough: out.rough_m, nodata: out.nodata };
}

export function rcToXY(grid, r, c) {
  return [(c + 0.5) * grid.cell, (grid.rows - r - 0.5) * grid.cell];
}
export function xyToRC(grid, x, y) {
  let r = Math.floor((grid.rows * grid.cell - y) / grid.cell);
  let c = Math.floor(x / grid.cell);
  r = Math.min(Math.max(r, 0), grid.rows - 1);
  c = Math.min(Math.max(c, 0), grid.cols - 1);
  return [r, c];
}
export function xyToIdx(grid, x, y) { const [r, c] = xyToRC(grid, x, y); return r * grid.cols + c; }
export function idxToXY(grid, i) { return rcToXY(grid, Math.floor(i / grid.cols), i % grid.cols); }

// ---------------------------------------------------------------- human model (cost.py, kind="nasa")
export function humanModel(params) {
  const hf = (k) => pv(params, 'human_factors.' + k);
  let mass = 0;
  for (const k of ['crew_body_mass_kg', 'suit_mass_kg', 'carried_kit_kg']) mass += hf(k);   // python sum()
  return { v0: hf('level_speed_mps'), p0: hf('level_metabolic_rate_w'), mass,
           gravity: hf('mars_gravity_mps2'), eta: hf('uphill_muscle_efficiency'),
           downCredit: hf('downhill_energy_credit') };
}
export function ePerM(hm, g) {
  const sinT = g / Math.sqrt(1.0 + g * g);
  const lift = hm.mass * hm.gravity * sinT;
  return hm.p0 / hm.v0 + (sinT > 0 ? lift / hm.eta : hm.downCredit * lift);
}

// ---------------------------------------------------------------- model = terrain + rules + edges
// opts: {slopeNogo, roughNogo, slopeCaution, roughCaution, keepout (Uint8Array or null)}
export function buildModel(grid, params, opts = {}) {
  const slopeNogo = opts.slopeNogo ?? pv(params, 'terrain.slope_nogo_deg');
  const roughNogo = opts.roughNogo ?? pv(params, 'terrain.roughness_nogo_m');
  const slopeCaution = opts.slopeCaution ?? pv(params, 'hazard.slope_caution_deg');
  const roughCaution = opts.roughCaution ?? pv(params, 'hazard.roughness_caution_m');
  const { rows: H, cols: W, n } = grid;
  const passable = new Uint8Array(n);
  const hazard = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    passable[i] = (!grid.nodata[i] && grid.slope[i] <= slopeNogo && grid.rough[i] <= roughNogo
                   && !(opts.keepout && opts.keepout[i])) ? 1 : 0;
    let hs = (grid.slope[i] - slopeCaution) / (slopeNogo - slopeCaution);
    hs = hs < 0 ? 0 : hs > 1 ? 1 : hs;
    let hr = (grid.rough[i] - roughCaution) / (roughNogo - roughCaution);
    hr = hr < 0 ? 0 : hr > 1 ? 1 : hr;
    hazard[i] = Math.max(hs, hr);
  }
  const maxGrade = Math.tan(slopeNogo * DEG2RAD);
  const ok = new Uint8Array(K * n);
  const offsets = new Int32Array(K);
  const length = new Float64Array(K);
  for (let k = 0; k < K; k++) {
    const [dr, dc, cross] = MOVES[k];
    offsets[k] = dr * W + dc;
    const d = grid.cell * Math.sqrt(dr * dr + dc * dc);
    length[k] = d;
    const base = k * n;
    for (let r = 0; r < H; r++) {
      const r2 = r + dr;
      if (r2 < 0 || r2 >= H) continue;
      for (let c = 0; c < W; c++) {
        const c2 = c + dc;
        if (c2 < 0 || c2 >= W) continue;
        const i = r * W + c;
        if (!passable[i] || !passable[r2 * W + c2]) continue;
        let fine = true;
        for (const [cr, cc] of cross) {
          const r3 = r + cr, c3 = c + cc;
          if (r3 < 0 || r3 >= H || c3 < 0 || c3 >= W || !passable[r3 * W + c3]) { fine = false; break; }
        }
        if (!fine) continue;
        const z = grid.elev[r2 * W + c2] - grid.elev[i];
        if (!Number.isFinite(z) || !(Math.abs(z) / d <= maxGrade)) continue;
        ok[base + i] = 1;
      }
    }
  }
  return { grid, params, hm: humanModel(params), passable, hazard, ok, offsets, length, maxGrade,
           slopeNogo, roughNogo, o2PerJ: pv(params, 'consumables.o2_kg_per_mj') / 1e6 };
}

// One edge (move k from cell i): the same numbers as cost.edge_costs.
export function edge(model, k, i) {
  const j = i + model.offsets[k];
  const L = model.length[k];
  const z = model.grid.elev[j] - model.grid.elev[i];
  const g = z / L;
  const hm = model.hm;
  const e = ePerM(hm, g);
  const v = Math.min(hm.v0, hm.p0 / e);
  const ls = L * Math.sqrt(1.0 + g * g);
  const t = ls / v;
  const hzMean = 0.5 * (model.hazard[i] + model.hazard[j]);
  return { j, g, dz: z, ls, L, t, e: e * ls, hz: t * hzMean, caution: hzMean > 0 ? t : 0.0 };
}

// cost.scalar_weight: (w_t*t)/t_ref + (w_e*E)/e_ref + (w_h*hz)/t_ref [+ (w_d*ls)/sqrt(1+g^2)]
export function makeWeight(model, w) {
  const [wt, we, wh, wd] = [w[0] || 0, w[1] || 0, w[2] || 0, w[3] || 0];
  if (wt + we + wd <= 0) throw new Error('time + energy (or distance) weight must be > 0');
  const tRef = 1.0 / model.hm.v0;
  const eRef = model.hm.p0 / model.hm.v0;
  return function (k, i) {
    const ed = edge(model, k, i);
    let x = wt * ed.t / tRef + we * ed.e / eRef + wh * ed.hz / tRef;
    if (wd) x = x + wd * ed.ls / Math.sqrt(1.0 + ed.g * ed.g);
    return x;
  };
}

// Precompute every edge weight once (Float64Array K*n, Infinity where no edge) and c_min.
export function weightTable(model, w) {
  const n = model.grid.n;
  const f = makeWeight(model, w);
  const tab = new Float64Array(K * n).fill(Infinity);
  let cMin = Infinity;
  for (let k = 0; k < K; k++) {
    const base = k * n, L = model.length[k];
    for (let i = 0; i < n; i++) {
      if (!model.ok[base + i]) continue;
      const x = f(k, i);
      tab[base + i] = x;
      const pm = x / L;
      if (pm < cMin) cMin = pm;
    }
  }
  return { w: w.slice(), tab, cMin };
}

// ---------------------------------------------------------------- binary heap of [f, g, i]
// Pops the lexicographically smallest tuple, like Python's heapq on (f, g, i).
class Heap {
  constructor() { this.a = []; }
  get size() { return this.a.length; }
  static less(x, y) { return x[0] < y[0] || (x[0] === y[0] && (x[1] < y[1] || (x[1] === y[1] && x[2] < y[2]))); }
  push(x) {
    const a = this.a; a.push(x);
    let i = a.length - 1;
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (!Heap.less(a[i], a[p])) break;
      [a[i], a[p]] = [a[p], a[i]]; i = p;
    }
  }
  pop() {
    const a = this.a, top = a[0], last = a.pop();
    if (a.length) {
      a[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1, r = l + 1;
        let m = i;
        if (l < a.length && Heap.less(a[l], a[m])) m = l;
        if (r < a.length && Heap.less(a[r], a[m])) m = r;
        if (m === i) break;
        [a[i], a[m]] = [a[m], a[i]]; i = m;
      }
    }
    return top;
  }
}

// ---------------------------------------------------------------- A* (astar.py)
export function astar(model, wt, start, goal) {
  const { rows: H, cols: W, n, cell } = model.grid;
  const tab = wt.tab;
  const gr = Math.floor(goal / W), gc = goal % W;
  const hscale = wt.cMin * cell;
  const h = (i) => { const dr = Math.floor(i / W) - gr, dc = (i % W) - gc; return hscale * Math.hypot(dr, dc); };
  const g = new Float64Array(n).fill(Infinity);
  const parent = new Int32Array(n).fill(-2);
  const closed = new Uint8Array(n);
  g[start] = 0; parent[start] = -1;
  const heap = new Heap();
  heap.push([h(start), 0.0, start]);
  let expanded = 0;
  while (heap.size) {
    const [, gi, i] = heap.pop();
    if (closed[i]) continue;
    if (i === goal) {
      const path = [i];
      while (parent[path[path.length - 1]] !== -1) path.push(parent[path[path.length - 1]]);
      path.reverse();
      return { cost: gi, path, expanded };
    }
    closed[i] = 1;
    expanded++;
    for (let k = 0; k < K; k++) {
      const w = tab[k * n + i];
      if (w === Infinity) continue;
      const j = i + model.offsets[k];
      if (closed[j]) continue;
      const ng = gi + w;
      if (ng < g[j]) { g[j] = ng; parent[j] = i; heap.push([ng + h(j), ng, j]); }
    }
  }
  return { cost: Infinity, path: [], expanded };
}

// Totals and geometry of a path (run_plan.World.leg)
export function legOf(model, path) {
  const grid = model.grid;
  if (path.length < 2) {
    const [x, y] = idxToXY(grid, path[0]);
    return { time_s: 0, energy_j: 0, hazard_s: 0, caution_s: 0, dist_m: 0, max_slope_deg: grid.slope[path[0]],
             max_grade_deg: 0, gain_m: 0, path: path.slice(), xy: [[x, y]], cum_time_s: [0], cum_energy_j: [0] };
  }
  let T = 0, E = 0, HZ = 0, C = 0, D = 0, gain = 0, maxG = 0, maxS = -Infinity;
  const cumT = [0], cumE = [0], xy = [];
  for (const i of path) { if (grid.slope[i] > maxS) maxS = grid.slope[i]; xy.push(idxToXY(grid, i)); }
  for (let s = 0; s + 1 < path.length; s++) {
    const a = path[s], b = path[s + 1];
    const off = b - a;
    let k = -1;
    for (let q = 0; q < K; q++) if (model.offsets[q] === off) { k = q; break; }
    if (k < 0 || !model.ok[k * grid.n + a]) throw new Error('path step is not an allowed edge');
    const ed = edge(model, k, a);
    T += ed.t; E += ed.e; HZ += ed.hz; C += ed.caution; D += ed.ls;
    if (ed.dz > 0) gain += ed.dz;
    if (Math.abs(ed.g) > maxG) maxG = Math.abs(ed.g);
    cumT.push(T); cumE.push(E);
  }
  return { time_s: T, energy_j: E, hazard_s: HZ, caution_s: C, dist_m: D, max_slope_deg: maxS,
           max_grade_deg: Math.atan(maxG) / DEG2RAD, gain_m: gain, path: path.slice(), xy, cum_time_s: cumT, cum_energy_j: cumE };
}

// ---------------------------------------------------------------- walk-home field (safety.walkback_field)
// Fastest-route time (s) and that route's energy (J) from every cell to `home` (Dijkstra on the
// reversed graph, time weights).
export function walkHomeField(model, home) {
  const { n } = model.grid;
  const time = new Float64Array(n).fill(Infinity);
  const energy = new Float64Array(n).fill(Infinity);
  const next = new Int32Array(n).fill(-1);
  const nextK = new Int8Array(n).fill(-1);
  const done = new Uint8Array(n);
  time[home] = 0; energy[home] = 0;
  const heap = new Heap();
  heap.push([0, 0, home]);
  while (heap.size) {
    const [d, , j] = heap.pop();
    if (done[j]) continue;
    done[j] = 1;
    for (let k = 0; k < K; k++) {
      const i = j - model.offsets[k];        // edge i -> j by move k
      if (i < 0 || i >= n || done[i] || !model.ok[k * n + i]) continue;
      const ed = edge(model, k, i);
      const nd = d + ed.t;
      if (nd < time[i]) { time[i] = nd; next[i] = j; nextK[i] = k; heap.push([nd, 0, i]); }
    }
  }
  // energy along each cell's fastest route home, in order of increasing time
  const order = Array.from({ length: n }, (_, i) => i).filter((i) => Number.isFinite(time[i]));
  order.sort((a, b) => time[a] - time[b]);
  for (const i of order) {
    if (i === home) continue;
    energy[i] = edge(model, nextK[i], i).e + energy[next[i]];
  }
  return { time_s: time, energy_j: energy, next };
}

// ---------------------------------------------------------------- plan evaluation (run_plan.timeline + safety_checks)
// sites: [{id, name, kind, category, dwell_min, work_w, idx}], order: site indices (start and end = habitat)
export function evaluatePlan(model, params, sites, order, legs, field, roles) {
  const o2PerJ = model.o2PerJ;
  const cap = pv(params, 'consumables.o2_capacity_kg');
  const reserve = cap * pv(params, 'consumables.o2_reserve_fraction');
  const bat = pv(params, 'consumables.battery_capacity_wh');
  const draw = pv(params, 'consumables.battery_draw_w');
  const limit = pv(params, 'mission.eva_time_limit') * 3600;
  const shelter = (params.__shelterMin ?? pv(params, 'sep.shelter_time_limit_min')) * 60;
  const rows = [];
  let t0 = 0, o2 = 0;
  const sT = [0], sO = [0];
  const pts = [];        // every route point: {xy, t, o2, back_t, back_o2, leg, idx}
  let walkT = 0, walkE = 0, workT = 0, workE = 0, dist = 0, hz = 0, caut = 0, maxS = -Infinity, maxG = 0, gain = 0;
  for (let k = 0; k < legs.length; k++) {
    const leg = legs[k], a = order[k], b = order[k + 1];
    walkT += leg.time_s; walkE += leg.energy_j; dist += leg.dist_m; hz += leg.hazard_s; caut += leg.caution_s;
    maxS = Math.max(maxS, leg.max_slope_deg); maxG = Math.max(maxG, leg.max_grade_deg); gain += leg.gain_m;
    rows.push({ kind: 'walk', from: sites[a].id, to: sites[b].id, t0_min: t0 / 60, t1_min: (t0 + leg.time_s) / 60,
                dist_m: leg.dist_m, energy_kcal: leg.energy_j / 4184, o2_kg: leg.energy_j * o2PerJ,
                EV1: roles?.walk?.EV1, EV2: roles?.walk?.EV2 });
    for (let q = 0; q < leg.path.length; q++) {
      const cellI = leg.path[q];
      pts.push({ leg: k, idx: cellI, xy: leg.xy[q], t: t0 + leg.cum_time_s[q], o2: o2 + leg.cum_energy_j[q] * o2PerJ,
                 back_t: field.time_s[cellI], back_o2: field.energy_j[cellI] * o2PerJ });
      if (q > 0) { sT.push(t0 + leg.cum_time_s[q]); sO.push(o2 + leg.cum_energy_j[q] * o2PerJ); }
    }
    t0 += leg.time_s; o2 += leg.energy_j * o2PerJ;
    if (sites[b].kind !== 'habitat') {
      const s = sites[b];
      const dwell = s.dwell_min * 60;
      const wO = dwell * s.work_w * o2PerJ;
      const role = roles ? (roles[s.kind === 'depot' ? 'depot' : s.category] || roles.waypoint || {}) : {};
      rows.push({ kind: 'work', at: s.id, name: s.name, t0_min: t0 / 60, t1_min: (t0 + dwell) / 60,
                  energy_kcal: dwell * s.work_w / 4184, o2_kg: wO, EV1: role.EV1, EV2: role.EV2,
                  task: s.task || (s.category ? 'Science stop (' + s.category.replace(/_/g, ' ') + ')' : 'Waypoint') });
      workT += dwell; workE += dwell * s.work_w;
      t0 += dwell; o2 += wO;
      sT.push(t0); sO.push(o2);
    }
  }
  // burn-down, 1-minute samples (np.interp)
  const tm = [], o2pct = [], batpct = [];
  const nMin = Math.ceil(t0 / 60);
  let p = 0;
  for (let m = 0; m <= nMin; m++) {
    const ts = m * 60;
    while (p + 1 < sT.length && sT[p + 1] < ts) p++;
    let used;
    if (ts <= sT[0]) used = sO[0];
    else if (p + 1 >= sT.length) used = sO[sO.length - 1];
    else { const f = (sT[p + 1] - sT[p]) > 0 ? (ts - sT[p]) / (sT[p + 1] - sT[p]) : 1; used = sO[p] + f * (sO[p + 1] - sO[p]); }
    tm.push(m); o2pct.push(100 * (1 - used / cap)); batpct.push(100 * (1 - draw * m / 60 / bat));
  }
  // walkback + SEP at every route point
  let minT = Infinity, minTi = -1, minO = Infinity, minOi = -1, maxBack = -Infinity, maxBackI = -1, sepBad = 0;
  const sepFlags = [];
  pts.forEach((q, i) => {
    const tm_ = limit - (q.t + q.back_t);
    const om = cap - reserve - (q.o2 + q.back_o2);
    if (tm_ < minT) { minT = tm_; minTi = i; }
    if (om < minO) { minO = om; minOi = i; }
    if (q.back_t > maxBack) { maxBack = q.back_t; maxBackI = i; }
    const bad = q.back_t > shelter;
    sepFlags.push(bad);
    if (bad) sepBad++;
  });
  const o2Used = (walkE + workE) * o2PerJ;
  const batUsed = draw * t0 / 3600;
  const totals = { walk_min: walkT / 60, work_min: workT / 60, duration_min: t0 / 60, dist_m: dist,
                   walk_energy_kcal: walkE / 4184, total_energy_kcal: (walkE + workE) / 4184, o2_kg: o2Used,
                   hazard_min: hz / 60, caution_min: caut / 60, max_slope_deg: maxS, max_grade_deg: maxG, gain_m: gain };
  const safety = {
    walkback: { min_time_margin_min: minT / 60, at_time_xy: pts[minTi]?.xy, at_time_elapsed_min: pts[minTi]?.t / 60,
                at_time_walk_home_min: pts[minTi]?.back_t / 60,
                min_o2_margin_kg: minO, min_o2_margin_pct_of_capacity: 100 * minO / cap, at_o2_xy: pts[minOi]?.xy },
    sep: { shelter_limit_min: shelter / 60, max_walk_home_min: maxBack / 60, max_at_xy: pts[maxBackI]?.xy,
           violating_points: sepBad, flags: sepFlags },
    consumables: { o2_used_kg: o2Used, o2_left_pct: 100 * (1 - o2Used / cap), battery_used_wh: batUsed,
                   battery_left_pct: 100 * (1 - batUsed / bat) },
    dose: { background_ugy: pv(params, 'sep.background_dose_rate_ugy_per_day') * t0 / 86400,
            rate_ugy_per_day: pv(params, 'sep.background_dose_rate_ugy_per_day') },
  };
  return { rows, totals, safety, pts,
           burn_down: { t_min: tm, o2_pct: o2pct, battery_pct: batpct,
                        o2_reserve_pct: 100 * pv(params, 'consumables.o2_reserve_fraction') } };
}

// ---------------------------------------------------------------- Monte Carlo (montecarlo.simulate)
// Same model as Python; a different random generator, so results differ by sampling noise only.
export function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function normalGen(rand) {
  let spare = null;
  return function () {
    if (spare !== null) { const s = spare; spare = null; return s; }
    let u = 0; while (u === 0) u = rand();
    const v = rand();
    const r = Math.sqrt(-2 * Math.log(u));
    spare = r * Math.sin(2 * Math.PI * v);
    return r * Math.cos(2 * Math.PI * v);
  };
}

// plan: {walk_s[], walk_o2[], work_s[], work_o2[], pts:[{leg, walk_s, walk_o2, back_s, back_o2}]}
export function monteCarlo(plan, opts) {
  const { runs, sigSpeed, sigMet, sigDwell, limitS, capKg, reserveKg, seed = 1, bins = 40 } = opts;
  const rand = mulberry32(seed), nrm = normalGen(rand);
  const nL = plan.walk_s.length, nS = plan.work_s.length;
  const dur = new Float64Array(runs), o2u = new Float64Array(runs), minTM = new Float64Array(runs);
  let onTime = 0, o2ok = 0, success = 0;
  const legT0 = new Float64Array(nL), legO0 = new Float64Array(nL);
  for (let r = 0; r < runs; r++) {
    const S = Math.exp(sigSpeed * nrm()), M = Math.exp(sigMet * nrm());
    let t = 0, o = 0;
    for (let k = 0; k < nL; k++) {
      legT0[k] = t; legO0[k] = o;
      t += plan.walk_s[k] / S; o += plan.walk_o2[k] * M;
      if (k < nS) { const D = Math.exp(sigDwell * nrm()); t += plan.work_s[k] * D; o += plan.work_o2[k] * M * D; }
    }
    let mt = Infinity, mo = Infinity;
    for (const q of plan.pts) {
      const tm = limitS - (legT0[q.leg] + q.walk_s / S + q.back_s / S);
      const om = capKg - reserveKg - (legO0[q.leg] + q.walk_o2 * M + q.back_o2 * M);
      if (tm < mt) mt = tm;
      if (om < mo) mo = om;
    }
    dur[r] = t / 60; o2u[r] = o; minTM[r] = mt / 60;
    const a = t <= limitS, b = o <= capKg - reserveKg;
    if (a) onTime++;
    if (b) o2ok++;
    if (a && b) success++;
  }
  const sorted = Float64Array.from(dur).sort();
  const pct = (arr, q) => { const pos = (arr.length - 1) * q / 100, lo = Math.floor(pos), hi = Math.ceil(pos);
                             return arr[lo] + (arr[hi] - arr[lo]) * (pos - lo); };
  const lo = sorted[0], hi = sorted[sorted.length - 1];
  const counts = new Array(bins).fill(0), edges = [];
  for (let b = 0; b <= bins; b++) edges.push(lo + (hi - lo) * b / bins);
  for (const d of dur) { let b = Math.floor((d - lo) / (hi - lo) * bins); if (b >= bins) b = bins - 1; if (b < 0) b = 0; counts[b]++; }
  const ps = success / runs;
  return { runs, p_on_time: onTime / runs, p_o2_ok: o2ok / runs, p_success: ps, p_success_se: Math.sqrt(ps * (1 - ps) / runs),
           duration_min: { p05: pct(sorted, 5), p50: pct(sorted, 50), p95: pct(sorted, 95) },
           min_walkback_time_margin_min: { p05: pct(Float64Array.from(minTM).sort(), 5) },
           histogram: { bin_edges_min: edges, counts, limit_min: limitS / 60 } };
}

// Build the Monte Carlo input from an evaluated plan (run_plan.profile_for)
export function mcProfile(model, sites, order, legs, field) {
  const o2PerJ = model.o2PerJ;
  const stops = order.slice(1, -1);
  const pts = [];
  legs.forEach((leg, k) => leg.path.forEach((cellI, q) => pts.push({
    leg: k, walk_s: leg.cum_time_s[q], walk_o2: leg.cum_energy_j[q] * o2PerJ,
    back_s: field.time_s[cellI], back_o2: field.energy_j[cellI] * o2PerJ })));
  return { walk_s: legs.map((l) => l.time_s), walk_o2: legs.map((l) => l.energy_j * o2PerJ),
           work_s: stops.map((k) => sites[k].dwell_min * 60),
           work_o2: stops.map((k) => sites[k].dwell_min * 60 * sites[k].work_w * o2PerJ), pts };
}

// ---------------------------------------------------------------- live re-plan
// From the crew's current cell, choose which remaining stops to keep and in which order, so that
// the EVA still ends at home within the time limit with O2 above the reserve, under the event's
// speed / work-time / O2 factors. The depot (tubes) is kept if at all possible. Exact: every
// subset and order of the remaining stops is tried (at most 5 stops -> 326 sequences).
// legFn(a, b) returns a leg (from legOf) between two cells.
export function replan(model, params, ctx, legFn) {
  const { here, elapsedS, o2UsedKg, remaining, sites, homeIdx, speedF = 1, workF = 1, o2F = 1 } = ctx;
  const cap = pv(params, 'consumables.o2_capacity_kg');
  const reserve = cap * pv(params, 'consumables.o2_reserve_fraction');
  const limit = pv(params, 'mission.eva_time_limit') * 3600;
  const o2PerJ = model.o2PerJ;
  const nodes = [here, ...remaining.map((k) => sites[k].idx), homeIdx];
  const cache = new Map();
  const L = (a, b) => {
    const key = a + ',' + b;
    if (!cache.has(key)) cache.set(key, legFn(nodes[a], nodes[b]));
    return cache.get(key);
  };
  const m = remaining.length, homeN = m + 1;
  let best = null;
  const seqs = [];
  const used = new Array(m).fill(false);
  (function rec(seq) {
    seqs.push(seq.slice());
    for (let q = 0; q < m; q++) if (!used[q]) { used[q] = true; seq.push(q); rec(seq); seq.pop(); used[q] = false; }
  })([]);
  const depotPos = remaining.findIndex((k) => sites[k].kind === 'depot');
  for (const seq of seqs) {
    let t = elapsedS, o = o2UsedKg, prev = 0, value = 0, feasible = true;
    for (const q of seq) {
      const leg = L(prev, q + 1);
      if (!Number.isFinite(leg.time_s)) { feasible = false; break; }
      const s = sites[remaining[q]];
      t += leg.time_s / speedF + s.dwell_min * 60 * workF;
      o += (leg.energy_j + s.dwell_min * 60 * workF * s.work_w) * o2PerJ * o2F;
      value += s.value;
      prev = q + 1;
    }
    if (!feasible) continue;
    const back = L(prev, homeN);
    if (!Number.isFinite(back.time_s)) continue;
    t += back.time_s / speedF;
    o += back.energy_j * o2PerJ * o2F;
    if (t > limit || o > cap - reserve) continue;
    const hasDepot = depotPos < 0 || seq.includes(depotPos);
    const score = [hasDepot ? 1 : 0, value, -t];
    if (!best || score[0] > best.score[0] || (score[0] === best.score[0] && (score[1] > best.score[1]
        || (score[1] === best.score[1] && score[2] > best.score[2])))) {
      best = { score, seq: seq.slice(), end_s: t, o2_end_kg: o, value, hasDepot };
    }
  }
  // fallback: nothing fits -> straight home (reported as such)
  if (!best) {
    const back = L(0, homeN);
    best = { score: [0, 0, 0], seq: [], end_s: elapsedS + back.time_s / speedF,
             o2_end_kg: o2UsedKg + back.energy_j * o2PerJ * o2F, value: 0, hasDepot: depotPos < 0, infeasible: true };
  }
  const stopsOut = best.seq.map((q) => remaining[q]);
  const legs = [];
  let prev = 0;
  for (const q of best.seq) { legs.push(L(prev, q + 1)); prev = q + 1; }
  legs.push(L(prev, homeN));
  return { stops: stopsOut, legs, end_min: best.end_s / 60, o2_end_kg: best.o2_end_kg,
           o2_left_pct: 100 * (1 - best.o2_end_kg / cap), value: best.value, depot_kept: best.hasDepot,
           infeasible: !!best.infeasible, sequences_tried: seqs.length, limit_min: limit / 60 };
}
