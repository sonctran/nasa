// Node runner for tests/test_js_engine.py: runs the BROWSER engine (site/js/engine.js) on a
// fixture written by the Python test and prints the results as JSON.
//   node tests/js/parity.mjs <fixture.json>
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import * as E from '../../site/js/engine.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const site = path.resolve(here, '../../site/assets/data');
const fx = JSON.parse(readFileSync(process.argv[2], 'utf-8'));

function realGrid() {
  const meta = JSON.parse(readFileSync(path.join(site, 'cost_grid.json'), 'utf-8'));
  const buf = readFileSync(path.join(site, 'cost_grid.bin'));
  const ab = buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
  return E.decodeGrid(meta, ab);
}

const params = fx.params ?? JSON.parse(readFileSync(path.join(site, 'params.json'), 'utf-8'));
const out = { cases: [] };
const t0 = performance.now();

for (const c of fx.cases) {
  let grid;
  if (c.grid === 'real') grid = realGrid();
  else {
    const g = c.grid;
    grid = { rows: g.rows, cols: g.cols, cell: g.cell, n: g.rows * g.cols,
             elev: Float64Array.from(g.elev), slope: Float64Array.from(g.slope),
             rough: Float64Array.from(g.rough), nodata: Uint8Array.from(g.nodata) };
  }
  const tb = performance.now();
  const model = E.buildModel(grid, params);
  const build_ms = performance.now() - tb;
  const res = { build_ms, edges: model.ok.reduce((a, b) => a + b, 0), passable: model.passable.reduce((a, b) => a + b, 0),
                queries: [] };
  const tables = new Map();
  for (const q of c.queries) {
    const key = q.w.join(',');
    if (!tables.has(key)) tables.set(key, E.weightTable(model, q.w));
    const wt = tables.get(key);
    const ta = performance.now();
    const r = E.astar(model, wt, q.start, q.goal);
    const ms = performance.now() - ta;
    const leg = r.path.length ? E.legOf(model, r.path) : null;
    res.queries.push({ cost: Number.isFinite(r.cost) ? r.cost : null, path: r.path, expanded: r.expanded, ms,
                       c_min: wt.cMin, time_s: leg?.time_s ?? null, energy_j: leg?.energy_j ?? null,
                       hazard_s: leg?.hazard_s ?? null, dist_m: leg?.dist_m ?? null });
  }
  if (c.plan) {
    // evaluate a whole plan: legs by A* between consecutive sites, then timeline + safety + MC
    const sites = c.plan.sites;
    sites.forEach((s) => { s.idx = E.xyToIdx(grid, s.cell_xy[0], s.cell_xy[1]); });
    const wt = E.weightTable(model, c.plan.w);
    const tl = performance.now();
    const legs = [];
    for (let k = 0; k + 1 < c.plan.order.length; k++) {
      const r = E.astar(model, wt, sites[c.plan.order[k]].idx, sites[c.plan.order[k + 1]].idx);
      legs.push(E.legOf(model, r.path));
    }
    const legs_ms = performance.now() - tl;
    const tf = performance.now();
    const field = E.walkHomeField(model, sites[0].idx);
    const field_ms = performance.now() - tf;
    const ev = E.evaluatePlan(model, params, sites, c.plan.order, legs, field, c.plan.roles);
    const tm = performance.now();
    const mc = E.monteCarlo(E.mcProfile(model, sites, c.plan.order, legs, field), {
      runs: E.pv(params, 'montecarlo.runs'), sigSpeed: E.pv(params, 'montecarlo.speed_sigma'),
      sigMet: E.pv(params, 'montecarlo.metabolic_sigma'), sigDwell: E.pv(params, 'montecarlo.dwell_sigma'),
      limitS: E.pv(params, 'mission.eva_time_limit') * 3600, capKg: E.pv(params, 'consumables.o2_capacity_kg'),
      reserveKg: E.pv(params, 'consumables.o2_capacity_kg') * E.pv(params, 'consumables.o2_reserve_fraction'), seed: 7 });
    const mc_ms = performance.now() - tm;
    // live re-plan from the start of leg 2 with the "slow crew" event
    const tr = performance.now();
    const rp = E.replan(model, params, {
      here: legs[1].path[0], elapsedS: ev.rows[2].t0_min * 60, o2UsedKg: ev.pts.find((p) => p.leg === 1).o2,
      remaining: c.plan.order.slice(2, -1), sites, homeIdx: sites[0].idx,
      speedF: E.pv(params, 'replan.slow_crew_speed_factor'), workF: E.pv(params, 'replan.slow_crew_work_factor'),
    }, (a, b) => E.legOf(model, E.astar(model, wt, a, b).path));
    const replan_ms = performance.now() - tr;
    delete ev.safety.sep.flags;
    res.plan = { totals: ev.totals, safety: ev.safety, rows: ev.rows.length, burn_last_o2: ev.burn_down.o2_pct.at(-1),
                 mc: { p_success: mc.p_success, p_on_time: mc.p_on_time, p50: mc.duration_min.p50, p95: mc.duration_min.p95 },
                 replan: { stops: rp.stops, end_min: rp.end_min, sequences_tried: rp.sequences_tried, depot_kept: rp.depot_kept },
                 ms: { legs: legs_ms, field: field_ms, mc: mc_ms, replan: replan_ms } };
  }
  out.cases.push(res);
}
out.total_ms = performance.now() - t0;
process.stdout.write(JSON.stringify(out));
