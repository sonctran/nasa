// Marswalk Ops - Web Worker: runs the planning engine off the main thread so the map stays smooth.
// Messages in:  {id, type, ...}   Messages out: {id, ok, result | error}
import * as E from './engine.js';

const S = { grid: null, params: null, model: null, tables: new Map(), fields: new Map(), rules: null };

function table(w) {
  const key = w.join(',');
  if (!S.tables.has(key)) S.tables.set(key, E.weightTable(S.model, w));
  return S.tables.get(key);
}
function field(home) {
  if (!S.fields.has(home)) S.fields.set(home, E.walkHomeField(S.model, home));
  return S.fields.get(home);
}
function keepoutMask(rects) {
  if (!rects || !rects.length) return null;
  const g = S.grid, m = new Uint8Array(g.n);
  for (const [x0, y0, x1, y1] of rects) {
    const [ra, ca] = E.xyToRC(g, Math.min(x0, x1), Math.max(y0, y1));
    const [rb, cb] = E.xyToRC(g, Math.max(x0, x1), Math.min(y0, y1));
    for (let r = ra; r <= rb; r++) for (let c = ca; c <= cb; c++) m[r * g.cols + c] = 1;
  }
  return m;
}
function rebuild(rules) {
  S.rules = rules;
  S.model = E.buildModel(S.grid, S.params, { slopeNogo: rules.slopeNogo, keepout: keepoutMask(rules.keepouts) });
  S.tables.clear();
  S.fields.clear();
}
const slim = (leg, f) => ({ back_s: f ? Array.from(leg.path, (i) => f.time_s[i]) : null, xy: leg.xy, path: leg.path, time_s: leg.time_s, energy_j: leg.energy_j, dist_m: leg.dist_m,
                         hazard_s: leg.hazard_s, caution_s: leg.caution_s, max_slope_deg: leg.max_slope_deg,
                         cum_time_s: leg.cum_time_s, cum_energy_j: leg.cum_energy_j });

// Nearest passable cell that can reach home (used when a waypoint is dropped on a no-go cell).
function snapIdx(i, f) {
  if (S.model.passable[i] && Number.isFinite(f.time_s[i])) return i;
  const g = S.grid, r0 = Math.floor(i / g.cols), c0 = i % g.cols;
  for (let rad = 1; rad < 60; rad++) {
    let best = -1, bd = Infinity;
    for (let r = r0 - rad; r <= r0 + rad; r++) for (let c = c0 - rad; c <= c0 + rad; c++) {
      if (r < 0 || c < 0 || r >= g.rows || c >= g.cols) continue;
      const j = r * g.cols + c;
      if (!S.model.passable[j] || !Number.isFinite(f.time_s[j])) continue;
      const d = (r - r0) ** 2 + (c - c0) ** 2;
      if (d < bd) { bd = d; best = j; }
    }
    if (best >= 0) return best;
  }
  return -1;
}

const handlers = {
  init({ meta, buffer, params, rules }) {
    const t0 = performance.now();
    S.grid = E.decodeGrid(meta, buffer);
    S.params = params;
    rebuild(rules);
    const edges = S.model.ok.reduce((a, b) => a + b, 0);
    return { build_ms: performance.now() - t0, edges, cells: S.grid.n,
             passable_share: S.model.passable.reduce((a, b) => a + b, 0) / S.grid.n };
  },
  rules({ rules }) {
    const t0 = performance.now();
    rebuild(rules);
    return { build_ms: performance.now() - t0, nogo_share: 1 - S.model.passable.reduce((a, b) => a + b, 0) / S.grid.n };
  },
  // Full plan: route every leg, then timeline, safety rules and a Monte Carlo run.
  plan({ sites, order, w, roles, shelterMin, mcRuns, seed }) {
    const T = {}, t0 = performance.now();
    const home = E.xyToIdx(S.grid, sites[0].x, sites[0].y);
    const f = field(home);
    T.field_ms = performance.now() - t0;
    const snapped = [];
    sites.forEach((s) => {
      const i0 = E.xyToIdx(S.grid, s.cell_xy ? s.cell_xy[0] : s.x, s.cell_xy ? s.cell_xy[1] : s.y);
      const i = snapIdx(i0, f);
      s.idx = i;
      if (i !== i0) snapped.push(s.id);
    });
    const bad = order.filter((k) => sites[k].idx < 0).map((k) => sites[k].id);
    if (bad.length) throw new Error('No safe cell near: ' + bad.join(', '));
    const wt = table(w);
    const t1 = performance.now();
    const legs = [];
    let expanded = 0;
    for (let k = 0; k + 1 < order.length; k++) {
      const r = E.astar(S.model, wt, sites[order[k]].idx, sites[order[k + 1]].idx);
      if (!r.path.length) throw new Error(`No safe route from ${sites[order[k]].name} to ${sites[order[k + 1]].name}`);
      expanded += r.expanded;
      legs.push(E.legOf(S.model, r.path));
    }
    T.astar_ms = performance.now() - t1;
    T.expanded = expanded;
    const P = shelterMin != null ? Object.assign(Object.create(S.params), { __shelterMin: shelterMin }) : S.params;
    const ev = E.evaluatePlan(S.model, P, sites, order, legs, f, roles);
    const t2 = performance.now();
    const pv = (k) => E.pv(S.params, k);
    const mc = E.monteCarlo(E.mcProfile(S.model, sites, order, legs, f), {
      runs: mcRuns ?? pv('montecarlo.runs'), sigSpeed: pv('montecarlo.speed_sigma'), sigMet: pv('montecarlo.metabolic_sigma'),
      sigDwell: pv('montecarlo.dwell_sigma'), limitS: pv('mission.eva_time_limit') * 3600,
      capKg: pv('consumables.o2_capacity_kg'), reserveKg: pv('consumables.o2_capacity_kg') * pv('consumables.o2_reserve_fraction'),
      seed: seed ?? 1 });
    T.mc_ms = performance.now() - t2;
    T.total_ms = performance.now() - t0;
    return { legs: legs.map((l) => slim(l, f)), eval: ev, mc, timing: T, snapped, site_idx: sites.map((s) => s.idx) };
  },
  // Live re-plan from the crew's current cell after an event.
  replan({ ctx, w, mode }) {
    const t0 = performance.now();
    const home = ctx.homeIdx;
    if (mode === 'sep') {
      const wt = table(E.pv(S.params, 'route_options.fastest'));
      const r = E.astar(S.model, wt, ctx.here, home);
      const leg = E.legOf(S.model, r.path);
      return { mode, stops: [], legs: [slim(leg, field(home))], walk_home_min: leg.time_s / 60 / (ctx.speedF || 1),
               ms: performance.now() - t0 };
    }
    const wt = table(w);
    const rp = E.replan(S.model, S.params, ctx, (a, b) => E.legOf(S.model, E.astar(S.model, wt, a, b).path));
    rp.legs = rp.legs.map((l) => slim(l, field(home)));
    rp.ms = performance.now() - t0;
    rp.mode = mode;
    return rp;
  },
  cellInfo({ x, y }) {
    const i = E.xyToIdx(S.grid, x, y);
    return { elev: S.grid.elev[i], slope: S.grid.slope[i], rough: S.grid.rough[i], passable: !!S.model.passable[i] };
  },
};

self.onmessage = (ev) => {
  const { id, type } = ev.data;
  try {
    const result = handlers[type](ev.data);
    self.postMessage({ id, ok: true, result });
  } catch (err) {
    self.postMessage({ id, ok: false, error: String(err && err.message || err) });
  }
};
