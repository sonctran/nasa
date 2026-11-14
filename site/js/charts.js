// Small hand-drawn SVG charts (no chart library). Colours: Okabe-Ito.
export const C = { orange: '#e69f00', sky: '#56b4e9', green: '#009e73', yellow: '#f0e442', blue: '#0072b2',
                   verm: '#d55e00', purple: '#cc79a7', grey: '#8a939e', text: '#e8eaed' };
const NS = 'http://www.w3.org/2000/svg';
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function svg(w, h) {
  const s = document.createElementNS(NS, 'svg');
  s.setAttribute('viewBox', `0 0 ${w} ${h}`);
  s.setAttribute('class', 'chart');
  s.setAttribute('role', 'img');
  return s;
}
function el(parent, tag, attrs = {}, text) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  parent.appendChild(e);
  return e;
}
function niceTicks(lo, hi, n = 5) {
  const span = hi - lo || 1;
  const step0 = span / n, mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0);
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}
function axes(s, X, Y, box, xt, yt, xl, yl, fmtX = String, fmtY = String) {
  const g = el(s, 'g', { class: 'grid' });
  for (const t of yt) el(g, 'line', { x1: box.l, x2: box.r, y1: Y(t), y2: Y(t) });
  const a = el(s, 'g', { class: 'axis' });
  el(a, 'line', { x1: box.l, x2: box.r, y1: box.b, y2: box.b });
  el(a, 'line', { x1: box.l, x2: box.l, y1: box.t, y2: box.b });
  for (const t of xt) el(s, 'text', { x: X(t), y: box.b + 14, 'text-anchor': 'middle' }, fmtX(t));
  for (const t of yt) el(s, 'text', { x: box.l - 5, y: Y(t) + 4, 'text-anchor': 'end' }, fmtY(t));
  if (xl) el(s, 'text', { x: (box.l + box.r) / 2, y: box.b + 30, 'text-anchor': 'middle' }, xl);
  if (yl) el(s, 'text', { x: 12, y: (box.t + box.b) / 2, 'text-anchor': 'middle', transform: `rotate(-90 12 ${(box.t + box.b) / 2})` }, yl);
}
const scale = (d0, d1, r0, r1) => (v) => r0 + (v - d0) / (d1 - d0 || 1) * (r1 - r0);

// ---------------------------------------------------------------- Pareto: walking time vs hazard exposure
export function pareto(target, points, named) {
  const W = 420, H = 250, box = { l: 52, r: W - 12, t: 12, b: H - 40 };
  const s = svg(W, H);
  const xs = points.map((p) => p.walk_min), ys = points.map((p) => p.hazard_min);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y1 = Math.max(...ys) * 1.1;
  const padX = (x1 - x0) * 0.08 || 0.5;
  const X = scale(x0 - padX, x1 + padX, box.l, box.r), Y = scale(0, y1, box.b, box.t);
  axes(s, X, Y, box, niceTicks(x0 - padX, x1 + padX, 4), niceTicks(0, y1, 4), 'Walking time (min)',
       'Hazard exposure (min)', (v) => v.toFixed(1), (v) => v.toFixed(1));
  const front = points.filter((p) => p.pareto).sort((a, b) => a.walk_min - b.walk_min);
  el(s, 'polyline', { points: front.map((p) => `${X(p.walk_min)},${Y(p.hazard_min)}`).join(' '), fill: 'none', stroke: C.blue, 'stroke-width': 1.5 });
  for (const p of points) {
    const c = el(s, 'circle', { cx: X(p.walk_min), cy: Y(p.hazard_min), r: p.pareto ? 4 : 3, fill: p.pareto ? C.sky : 'none', stroke: C.sky });
    el(c, 'title', {}, `weights t/E/H ${p.w.slice(0, 3).join('/')}: ${p.walk_min.toFixed(1)} min walking, ${p.hazard_min.toFixed(2)} hazard-min`);
  }
  const cols = { fastest: C.orange, safest: C.green, balanced: C.sky, shortest: C.grey };
  for (const a of named) {
    if (!cols[a.id]) continue;
    el(s, 'circle', { cx: X(a.walk_min), cy: Y(a.hazard_min), r: 6, fill: 'none', stroke: cols[a.id], 'stroke-width': 2.5 });
    el(s, 'text', { x: X(a.walk_min) + 8, y: Y(a.hazard_min) - 6, fill: cols[a.id], style: `fill:${cols[a.id]}` }, a.name);
  }
  target.replaceChildren(s);
}

// ---------------------------------------------------------------- Gantt: EV1 and EV2 lanes
export function gantt(target, rows, limitMin, colorOf) {
  const W = 430, H = 150, box = { l: 40, r: W - 10, t: 10, b: H - 36 };
  const s = svg(W, H);
  const tmax = Math.max(limitMin, rows.at(-1)?.t1_min ?? 0);
  const X = scale(0, tmax, box.l, box.r);
  const xt = niceTicks(0, tmax, 6);
  const g = el(s, 'g', { class: 'grid' });
  for (const t of xt) el(g, 'line', { x1: X(t), x2: X(t), y1: box.t, y2: box.b });
  for (const t of xt) el(s, 'text', { x: X(t), y: box.b + 14, 'text-anchor': 'middle' }, String(t));
  el(s, 'text', { x: (box.l + box.r) / 2, y: box.b + 30, 'text-anchor': 'middle' }, 'Minutes from leaving the habitat');
  const lanes = ['EV1', 'EV2'], lh = (box.b - box.t) / 2;
  lanes.forEach((ln, li) => {
    const y = box.t + li * lh + 6;
    el(s, 'text', { x: 4, y: y + lh / 2 }, ln);
    for (const r of rows) {
      const rect = el(s, 'rect', { x: X(r.t0_min), y, width: Math.max(1, X(r.t1_min) - X(r.t0_min)), height: lh - 12,
                                   fill: r.kind === 'walk' ? '#5a6573' : colorOf(r), rx: 2 });
      const what = r.kind === 'walk' ? `Walk ${r.from} → ${r.to} (${(r.dist_m / 1000).toFixed(2)} km)` : `${r.name}: ${r.task}`;
      el(rect, 'title', {}, `${what}\n${r.t0_min.toFixed(0)}-${r.t1_min.toFixed(0)} min\n${ln}: ${r[ln] ?? ''}`);
    }
  });
  el(s, 'line', { x1: X(limitMin), x2: X(limitMin), y1: box.t - 4, y2: box.b, stroke: C.verm, 'stroke-width': 2, 'stroke-dasharray': '4 3' });
  el(s, 'text', { x: X(limitMin) - 3, y: box.t + 2, 'text-anchor': 'end', style: `fill:${C.verm}` }, `limit ${limitMin} min`);
  target.replaceChildren(s);
}

// ---------------------------------------------------------------- consumables burn-down
export function burnDown(target, bd, limitMin) {
  const W = 430, H = 210, box = { l: 40, r: W - 10, t: 10, b: H - 36 };
  const s = svg(W, H);
  const tmax = Math.max(limitMin, bd.t_min.at(-1));
  const X = scale(0, tmax, box.l, box.r), Y = scale(0, 100, box.b, box.t);
  axes(s, X, Y, box, niceTicks(0, tmax, 6), [0, 25, 50, 75, 100], 'Minutes', 'Left (%)', String, String);
  const line = (vals, col, dash) => el(s, 'polyline', { points: bd.t_min.map((t, i) => `${X(t)},${Y(vals[i])}`).join(' '),
                                                         fill: 'none', stroke: col, 'stroke-width': 2.2, ...(dash ? { 'stroke-dasharray': dash } : {}) });
  line(bd.o2_pct, C.sky);
  line(bd.battery_pct, C.orange, '6 3');
  el(s, 'line', { x1: box.l, x2: box.r, y1: Y(bd.o2_reserve_pct), y2: Y(bd.o2_reserve_pct), stroke: C.verm, 'stroke-dasharray': '3 3' });
  el(s, 'text', { x: box.r, y: Y(bd.o2_reserve_pct) - 4, 'text-anchor': 'end', style: `fill:${C.verm}` }, `O2 reserve ${bd.o2_reserve_pct}%`);
  el(s, 'line', { x1: X(limitMin), x2: X(limitMin), y1: box.t, y2: box.b, stroke: C.verm, 'stroke-width': 1.5, 'stroke-dasharray': '4 3' });
  target.replaceChildren(s);
}

// ---------------------------------------------------------------- Monte Carlo histogram
export function histogram(target, hist, p50, p95) {
  const W = 430, H = 200, box = { l: 44, r: W - 10, t: 12, b: H - 36 };
  const s = svg(W, H);
  const e = hist.bin_edges_min, c = hist.counts;
  const x0 = Math.min(e[0], hist.limit_min - 10), x1 = Math.max(e.at(-1), hist.limit_min + 10);
  const ymax = Math.max(...c) * 1.1;
  const X = scale(x0, x1, box.l, box.r), Y = scale(0, ymax, box.b, box.t);
  axes(s, X, Y, box, niceTicks(x0, x1, 6), niceTicks(0, ymax, 4), 'EVA duration (min)', 'Runs', String, (v) => String(Math.round(v)));
  c.forEach((n, i) => {
    const over = e[i] >= hist.limit_min;
    el(s, 'rect', { x: X(e[i]), y: Y(n), width: Math.max(0.5, X(e[i + 1]) - X(e[i]) - 0.6), height: box.b - Y(n), fill: over ? C.verm : C.sky });
  });
  const vline = (v, col, lab, dy) => {
    el(s, 'line', { x1: X(v), x2: X(v), y1: box.t, y2: box.b, stroke: col, 'stroke-width': 1.8, 'stroke-dasharray': '4 3' });
    el(s, 'text', { x: X(v) + 3, y: box.t + 10 + dy, style: `fill:${col}` }, lab);
  };
  vline(hist.limit_min, C.verm, `limit ${hist.limit_min}`, 0);
  if (p50 != null) vline(p50, C.yellow, `P50 ${p50.toFixed(0)}`, 14);
  if (p95 != null) vline(p95, C.orange, `P95 ${p95.toFixed(0)}`, 28);
  target.replaceChildren(s);
}

// ---------------------------------------------------------------- tornado (sensitivity)
export function tornado(target, t) {
  const rows = t.rows;
  const W = 430, rowH = 26, H = 40 + rows.length * rowH, box = { l: 170, r: W - 14, t: 8, b: H - 30 };
  const s = svg(W, H);
  const all = rows.flatMap((r) => r.duration_min).concat([t.base_duration_min]);
  const lo = Math.min(...all) - 3, hi = Math.max(...all) + 3;
  const X = scale(lo, hi, box.l, box.r);
  for (const v of niceTicks(lo, hi, 5)) {
    el(s, 'line', { x1: X(v), x2: X(v), y1: box.t, y2: box.b, stroke: '#262c34' });
    el(s, 'text', { x: X(v), y: box.b + 14, 'text-anchor': 'middle' }, String(v));
  }
  el(s, 'text', { x: (box.l + box.r) / 2, y: box.b + 28, 'text-anchor': 'middle' }, 'EVA duration (min) at the 10th / 90th percentile of each input');
  rows.forEach((r, i) => {
    const y = box.t + i * rowH + 4;
    const [a, b] = r.duration_min;
    const name = r.input.length > 30 ? r.input.slice(0, 29) + '…' : r.input;
    el(s, 'text', { x: box.l - 6, y: y + 13, 'text-anchor': 'end' }, name);
    const x0 = X(Math.min(a, b)), x1 = X(Math.max(a, b));
    const shorter = Math.min(a, b), longer = Math.max(a, b);
    el(s, 'rect', { x: X(shorter), y, width: X(t.base_duration_min) - X(shorter), height: rowH - 8, fill: C.sky });
    el(s, 'rect', { x: X(t.base_duration_min), y, width: X(longer) - X(t.base_duration_min), height: rowH - 8, fill: C.orange });
    const tt = el(s, 'rect', { x: x0, y, width: x1 - x0, height: rowH - 8, fill: 'transparent' });
    el(tt, 'title', {}, `${r.input}: ${r.low_label} -> ${a.toFixed(0)} min, ${r.high_label} -> ${b.toFixed(0)} min (swing ${r.swing_min.toFixed(0)} min)`);
  });
  el(s, 'line', { x1: X(t.base_duration_min), x2: X(t.base_duration_min), y1: box.t, y2: box.b, stroke: C.text });
  target.replaceChildren(s);
}
