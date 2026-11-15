// Marswalk Ops - main page: map, panels and the link to the planning Web Worker.
import * as E from './engine.js';
import * as Ch from './charts.js';
import { initHUD } from './hud.js';

const $ = (s, r = document) => r.querySelector(s);
const esc = Ch.esc;
const A = { cur: null, res: null, overlays: {}, rpc: { seq: 0, pending: new Map() } };
window.__marswalk = A;   // for the screenshot script and for debugging

// ---------------------------------------------------------------- formatting
const f0 = (v) => (v == null || !Number.isFinite(v) ? '-' : Math.round(v).toLocaleString('en-US'));
const f1 = (v) => (v == null || !Number.isFinite(v) ? '-' : v.toFixed(1));
const f2 = (v) => (v == null || !Number.isFinite(v) ? '-' : v.toFixed(2));
const pct = (v, d = 1) => (v == null || !Number.isFinite(v) ? '-' : (100 * v).toFixed(d) + ' %');
const hm = (min) => `${Math.floor(min / 60)} h ${String(Math.round(min % 60)).padStart(2, '0')} min`;
const B = (k) => `<span class="badge ${k === 'owner-set' ? 'owner' : k}">${k}</span>`;
const pv = (k) => E.pv(A.params, k);
const LL = (xy) => [xy[1], xy[0]];         // local metres (x east, y north) -> Leaflet [lat, lng]
const CAT = {
  fine_grained_layered_rock: { col: Ch.C.orange, label: 'Fine-grained layered rock' },
  delta_layer_sequence: { col: Ch.C.sky, label: 'Delta layer sequence' },
  transported_boulders: { col: Ch.C.purple, label: 'Transported boulders' },
  depot: { col: Ch.C.green, label: 'Sample depot (required)' },
  waypoint: { col: Ch.C.yellow, label: 'Your waypoint' },
};
const ROUTE = Ch.C.yellow, SEPCOL = '#ff6b5b';     // plan route / SEP-rule violations (the NO-GO red)
const ROUTE_COL = { fastest: Ch.C.orange, lowest_energy: Ch.C.blue, safest: Ch.C.green, balanced: Ch.C.sky, shortest: Ch.C.grey };

// ---------------------------------------------------------------- worker RPC
function call(type, payload = {}, transfer = []) {
  return new Promise((resolve, reject) => {
    const id = ++A.rpc.seq;
    A.rpc.pending.set(id, { resolve, reject });
    A.worker.postMessage({ id, type, ...payload }, transfer);
  });
}
A.call = call;

async function getJSON(u) { const r = await fetch(u); if (!r.ok) throw new Error(`${u}: HTTP ${r.status}`); return r.json(); }
async function getBin(u) { const r = await fetch(u); if (!r.ok) throw new Error(`${u}: HTTP ${r.status}`); return r.arrayBuffer(); }

// ---------------------------------------------------------------- start
async function main() {
  const D = 'assets/data/';
  const [layers, plan, params, roles, vectors, gridMeta, gridBuf, donki] = await Promise.all([
    getJSON(D + 'layers.json'), getJSON(D + 'plan.json'), getJSON(D + 'params.json'), getJSON(D + 'roles.json'),
    getJSON(D + 'vectors.json'), getJSON(D + 'cost_grid.json'), getBin(D + 'cost_grid.bin'),
    getJSON(D + 'donki_sep_2024-05-01_2024-06-29.json')]);
  Object.assign(A, { layers, plan, params, roles, vectors, gridMeta, donki });
  A.grid = E.decodeGrid(gridMeta, gridBuf);
  A.limitMin = pv('mission.eva_time_limit') * 60;
  setupMap();
  drawPrecomputedRoute();          // a route on screen right away (from plan.json)
  A.cur = defaultState();
  setupTabs();
  renderStaticPanels();

  A.worker = new Worker('js/worker.js', { type: 'module' });
  A.worker.onmessage = (ev) => {
    const p = A.rpc.pending.get(ev.data.id);
    if (!p) return;
    A.rpc.pending.delete(ev.data.id);
    ev.data.ok ? p.resolve(ev.data.result) : p.reject(new Error(ev.data.error));
  };
  A.worker.onerror = (e) => showError('Planner worker failed: ' + (e.message || e));
  const copy = gridBuf.slice(0);
  A.initInfo = await call('init', { meta: gridMeta, buffer: copy, params, rules: rulesNow() }, [copy]);
  A.hud = initHUD(A);
  await replan();
  document.body.dataset.ready = '1';
}

function showError(msg) {
  const d = document.createElement('div');
  d.className = 'warn';
  d.style.cssText = 'position:fixed;bottom:10px;left:10px;z-index:3000;max-width:520px';
  d.textContent = msg;
  document.body.appendChild(d);
}

// ---------------------------------------------------------------- state
function siteById(id) { return A.plan.sites.find((s) => s.id === id); }
function defaultState() {
  const ids = A.plan.plan.order.slice(1, -1);
  return { order: ids, waypoints: [], profile: 'balanced', w: pv('route_options.balanced').slice(0, 3),
           slopeNogo: pv('terrain.slope_nogo_deg'), shelterMin: pv('sep.shelter_time_limit_min'), keepouts: [], nWp: 0 };
}
function rulesNow() { return { slopeNogo: A.cur ? A.cur.slopeNogo : pv('terrain.slope_nogo_deg'), keepouts: A.cur ? A.cur.keepouts : [] }; }
function siteList() {
  const base = A.plan.sites.map((s) => ({ ...s }));
  for (const w of A.cur.waypoints) base.push({ id: w.id, name: w.name, kind: 'waypoint', category: 'waypoint', value: 0,
                                               dwell_min: 0, work_w: 0, x: w.x, y: w.y, task: 'Waypoint (pass through)' });
  return base;
}

// ---------------------------------------------------------------- map
function setupMap() {
  const map = L.map('map', { crs: L.CRS.Simple, minZoom: -3, maxZoom: 3, zoomSnap: 0.25, zoomDelta: 0.5,
                             attributionControl: true, preferCanvas: false });
  A.map = map;
  map.attributionControl.setPrefix(false);
  map.attributionControl.addAttribution('HiRISE: NASA/JPL-Caltech/Univ. of Arizona · DTM/ortho mosaic: USGS (Fergason et al. 2020) · Rover data: NASA/JPL-Caltech · <a href="methods.html#sources">all credits</a>');
  const b = A.layers.layers[0].bounds;
  map.fitBounds([[760, 1250], [2250, 2800]]);
  map.setMaxBounds([[-600, -600], [b[1][0] + 600, b[1][1] + 600]]);
  // raster layers
  const defaults = { ortho: 1, hillshade: 0, elevation: 0, slope: 0, roughness: 0, nogo: 0.55, themis_day: 0, themis_night: 0 };
  A.raster = {};
  for (const lyr of A.layers.layers) {
    const op = defaults[lyr.id] ?? 0;
    const o = L.imageOverlay('assets/' + lyr.file, lyr.bounds, { opacity: op || 0.7, interactive: false, className: 'lyr-' + lyr.id });
    A.raster[lyr.id] = { lyr, o, on: op > 0, opacity: op || 0.7 };
    if (op > 0) o.addTo(map);
  }
  const dc = A.layers.closeups[0];
  A.raster.depot_closeup = { lyr: { ...dc, title: 'Depot close-up (25 cm)' }, o: L.imageOverlay('assets/' + dc.file, dc.bounds, { opacity: 1 }), on: false, opacity: 1 };
  // vector layers
  A.vec = {};
  const tr = L.layerGroup();
  for (const ln of A.vectors.traverse.lines) L.polyline(ln.xy.map(LL), { color: '#ffffff', weight: 1.5, opacity: 0.55, dashArray: '3 4', interactive: false }).addTo(tr);
  A.vec.traverse = { title: 'Perseverance traverse', kind: 'real', g: tr, on: true };
  const wp = L.layerGroup();
  for (const p of A.vectors.waypoints.points) L.circleMarker(LL([p.x, p.y]), { radius: 2, color: '#fff', weight: 1, fillOpacity: 0.8 })
    .bindTooltip(`Rover waypoint ${esc(p.rmc)} · sol ${p.sol}`).addTo(wp);
  A.vec.waypoints = { title: 'Rover waypoints', kind: 'real', g: wp, on: false };
  const dp = L.layerGroup();
  for (const p of A.vectors.depot_tubes.points) L.circleMarker(LL([p.x, p.y]), { radius: 4, color: '#111', weight: 1, fillColor: Ch.C.green, fillOpacity: 1 })
    .bindTooltip(`${esc(p.name)} (${esc(p.sample)}) · dropped sol ${p.drop_sol}<br>rover position at drop, not the tube itself`).addTo(dp);
  A.vec.depot = { title: 'Depot tubes (10)', kind: 'real', g: dp, on: true };
  const pov = L.layerGroup();
  for (const ph of A.vectors.pov.photos) L.circleMarker(LL([ph.x, ph.y]), { radius: 5, color: '#111', weight: 1, fillColor: '#fff', fillOpacity: 0.9 })
    .bindPopup(photoHTML(ph, null)).addTo(pov);
  A.vec.pov = { title: 'Rover photos (22)', kind: 'real', g: pov, on: false };
  A.vec.alts = { title: 'Route options', kind: 'modeled', g: L.layerGroup(), on: true };
  A.vec.route = { title: 'Your plan route', kind: 'modeled', g: L.layerGroup(), on: true };
  A.vec.stops = { title: 'Science stops + habitat site', kind: 'real', kind2: 'assumption', g: L.layerGroup(), on: true };
  A.vec.extra = { title: 'Checks overlay', kind: 'modeled', g: L.layerGroup(), on: true };
  for (const k of ['traverse', 'depot', 'alts', 'route', 'stops', 'extra']) if (A.vec[k].on) A.vec[k].g.addTo(map);
  if (A.vec.waypoints.on) A.vec.waypoints.g.addTo(map);
  A.keepGroup = L.layerGroup().addTo(map);

  L.control.scale({ imperial: false, metric: true, maxWidth: 160, position: 'bottomleft' }).addTo(map);
  layerControl();
  legendControl();
  readoutControl();
  map.on('click', onMapClick);
  map.on('zoomend', () => { if (A.cur) drawStops(); });      // marker spacing depends on the zoom
  map.on('mousemove', (e) => updateReadout(e.latlng));
}

function photoHTML(ph, distM) {
  const d = distM != null ? `<br>Nearest rover photo: taken ${f0(distM)} m from this stop${distM > 50 ? ', so it shows the area, not this exact outcrop' : ''}.` : '';
  return `<img class="photo" src="assets/${esc(ph.file)}" alt="Perseverance ${esc(ph.instrument)} image, sol ${ph.sol}" loading="lazy">
    <div class="credit">Image: ${esc(ph.credit)} · ${esc(ph.instrument)} · sol ${ph.sol} · rover site ${ph.site}${d}
    <br><a href="${esc(ph.page)}" target="_blank" rel="noopener">raw image page</a> <span class="badge real">real</span></div>`;
}

function layerControl() {
  const Ctl = L.Control.extend({
    onAdd() {
      const d = L.DomUtil.create('div', 'mctl');
      L.DomEvent.disableClickPropagation(d); L.DomEvent.disableScrollPropagation(d);
      let html = '<button class="toggle" type="button" aria-label="Hide layers">-</button><h4>Layers</h4><div class="body">';
      for (const [id, r] of Object.entries(A.raster)) {
        html += `<div class="lyr"><label title="${esc(r.lyr.processing || '')}"><input type="checkbox" data-r="${id}" ${r.on ? 'checked' : ''}> ${esc(r.lyr.title)} ${B(r.lyr.kind)}</label>
                 <input type="range" min="0" max="1" step="0.05" value="${r.opacity}" data-op="${id}" aria-label="${esc(r.lyr.title)} opacity"></div>`;
      }
      html += '<hr style="border-color:#2c333d">';
      for (const [id, v] of Object.entries(A.vec)) {
        if (id === 'extra') continue;
        html += `<div class="lyr"><label><input type="checkbox" data-v="${id}" ${v.on ? 'checked' : ''}> ${esc(v.title)} ${B(v.kind)}${v.kind2 ? ' ' + B(v.kind2) : ''}</label><span></span></div>`;
      }
      html += '</div>';
      d.innerHTML = html;
      const tg = d.querySelector('.toggle');
      tg.onclick = () => { d.classList.toggle('collapsed'); tg.textContent = d.classList.contains('collapsed') ? '+' : '-'; };
      d.querySelectorAll('[data-r]').forEach((cb) => cb.onchange = () => {
        const r = A.raster[cb.dataset.r]; r.on = cb.checked;
        r.on ? r.o.addTo(A.map) : r.o.remove();
        reorderLayers(); updateLegend(); updateAttribution();
      });
      d.querySelectorAll('[data-op]').forEach((sl) => sl.oninput = () => {
        const r = A.raster[sl.dataset.op]; r.opacity = +sl.value; r.o.setOpacity(r.opacity);
      });
      d.querySelectorAll('[data-v]').forEach((cb) => cb.onchange = () => {
        const v = A.vec[cb.dataset.v]; v.on = cb.checked; v.on ? v.g.addTo(A.map) : v.g.remove();
      });
      d.classList.add('collapsed'); tg.textContent = '+';   // collapsed by default so the route is visible
      return d;
    },
  });
  new Ctl({ position: 'topright' }).addTo(A.map);
}
const THEMIS_CREDIT = 'THEMIS IR: NASA/JPL-Caltech/Arizona State Univ., via NASA Mars Trek';
function updateAttribution() {
  const on = A.raster.themis_day.on || A.raster.themis_night.on, ac = A.map.attributionControl;
  ac.removeAttribution(THEMIS_CREDIT);
  if (on) ac.addAttribution(THEMIS_CREDIT);
}
// The no-go picture file is drawn for the default 20 deg rule. When the user moves the slope slider,
// draw the planner's own 10 m no-go cells instead, so the map always shows the rule in use.
function nogoMaskURL() {
  const g = A.grid, cv = document.createElement('canvas');
  cv.width = g.cols; cv.height = g.rows;
  const ctx = cv.getContext('2d'), im = ctx.createImageData(g.cols, g.rows);
  const hex = A.raster.nogo.lyr.color || '#d55e00';
  const [cr, cg, cb] = [1, 3, 5].map((k) => parseInt(hex.slice(k, k + 2), 16));
  const sn = A.cur.slopeNogo, rn = pv('terrain.roughness_nogo_m');
  for (let i = 0; i < g.n; i++) {
    if (!(g.nodata[i] || g.slope[i] > sn || g.rough[i] > rn)) continue;
    im.data[4 * i] = cr; im.data[4 * i + 1] = cg; im.data[4 * i + 2] = cb; im.data[4 * i + 3] = 255;
  }
  ctx.putImageData(im, 0, 0);
  return cv.toDataURL();
}
function nogoIsLive() { return !!A.cur && A.cur.slopeNogo !== pv('terrain.slope_nogo_deg'); }
function updateNogoLayer() {
  const r = A.raster.nogo;
  const want = nogoIsLive() ? 'live' + A.cur.slopeNogo : 'file';
  if (r.shown === want) return;
  r.shown = want;
  r.o.setUrl(nogoIsLive() ? nogoMaskURL() : 'assets/' + r.lyr.file);
}
function reorderLayers() {
  const order = ['ortho', 'hillshade', 'elevation', 'slope', 'roughness', 'themis_day', 'themis_night', 'nogo', 'depot_closeup'];
  for (const id of order) if (A.raster[id]?.on) A.raster[id].o.bringToFront();
}

function legendControl() {
  const Ctl = L.Control.extend({
    onAdd() { const d = L.DomUtil.create('div', 'mctl'); d.id = 'legend'; L.DomEvent.disableClickPropagation(d); L.DomEvent.disableScrollPropagation(d); return d; },
  });
  A.legendFolded = window.innerWidth < 1100;      // on a tablet the legend would cover a third of the map
  new Ctl({ position: 'bottomleft' }).addTo(A.map);
  updateLegend();
}
function updateLegend() {
  const d = $('#legend');
  if (!d) return;
  let html = `<button class="toggle" type="button" aria-expanded="${!A.legendFolded}" aria-label="${A.legendFolded ? 'Show' : 'Hide'} the legend">${A.legendFolded ? '+' : '-'}</button><h4>Legend</h4><div class="body">`;
  for (const id of ['elevation', 'slope', 'roughness']) {
    const r = A.raster[id];
    if (!r.on || !r.lyr.legend) continue;
    const lg = r.lyr.legend;
    html += `<div>${esc(r.lyr.title)} (${esc(r.lyr.units)}) ${B(r.lyr.kind)}</div><div class="gradbar" style="background:linear-gradient(90deg,${lg.map((x) => x.color).join(',')})"></div>
      <div class="small muted" style="display:flex;justify-content:space-between"><span>${f1(lg[0].value)}</span><span>${f1(lg.at(-1).value)}${id === 'slope' ? '+' : ''}</span></div>`;
  }
  if (A.raster.nogo.on) html += `<div><span class="sw" style="background:${A.raster.nogo.lyr.color}"></span>No-go: slope &gt; ${A.cur ? A.cur.slopeNogo : 20}° or roughness &gt; 0.2 m ${B('assumption')}</div>
    <div class="small muted">${nogoIsLive() ? 'Drawn from the planner\'s own 10 m cells for your slope rule.' : 'Drawn at 2 m detail. The planner works on 10 m cells (90th-percentile slope).'}</div>`;
  if (A.raster.themis_day.on || A.raster.themis_night.on) html += `<div>THEMIS IR ${B('proxy')}</div><div class="small muted">Relative brightness only (not calibrated temperature), ~81 m/px.</div>`;
  html += `<div><span class="habicon sm">H</span> Habitat: start, finish, shelter</div>
    <div>${['fine_grained_layered_rock', 'delta_layer_sequence', 'transported_boulders', 'depot'].map((k) => `<span class="sw" style="background:${CAT[k].col};border-radius:50%"></span>${CAT[k].label}`).join('<br>')}</div>
    <div class="small muted">Number = stop order in your plan; · = site not in your plan (click a stop for its card).</div>
    <div><span class="sw" style="background:${ROUTE}"></span>Your plan route ${B('modeled')}</div>
    <div><span class="sw" style="background:#fff;border-radius:50%"></span>Tightest walk-back point</div>
    <div><span class="sw line" style="background:${SEPCOL}"></span>Too far from shelter (SEP rule)</div>
    <div><span class="sw" style="background:#fff"></span>Perseverance traverse ${B('real')}</div></div>`;
  d.innerHTML = html;
  d.classList.toggle('collapsed', !!A.legendFolded);
  d.querySelector('.toggle').onclick = () => { A.legendFolded = !A.legendFolded; updateLegend(); };
}

function readoutControl() {
  const Ctl = L.Control.extend({
    onAdd() { const d = L.DomUtil.create('div', 'mctl readout'); d.id = 'readout'; d.innerHTML = '<h4>Cursor</h4><div class="small muted">Move the mouse over the map</div>'; return d; },
  });
  new Ctl({ position: 'topleft' }).addTo(A.map);
}
function updateReadout(ll) {
  const x = ll.lng, y = ll.lat, g = A.grid;
  const d = $('#readout');
  if (x < 0 || y < 0 || x >= 4000 || y >= 4000) { d.innerHTML = '<h4>Cursor</h4><div class="small muted">outside the study area</div>'; return; }
  const i = E.xyToIdx(g, x, y);
  const nogo = g.nodata[i] || g.slope[i] > A.cur.slopeNogo || g.rough[i] > pv('terrain.roughness_nogo_m');
  d.innerHTML = `<h4>Cursor (10 m cell)</h4>x ${f0(x)} m · y ${f0(y)} m<br>Elevation ${f1(g.elev[i])} m ${B('real')}<br>
    Slope ${f1(g.slope[i])}° · roughness ${f2(g.rough[i])} m ${B('derived')}<br>${nogo ? '<b style="color:#ff6b5b">No-go cell</b>' : 'Walkable'}`;
}

// ---------------------------------------------------------------- markers & routes
// Screen-pixel offsets that push overlapping stop markers apart at the current zoom.
// The marker stays anchored at its true position; only the round badge is nudged.
function declutter(sites) {
  const MIN = 27;
  const q = sites.map((s) => { const p = A.map.latLngToContainerPoint(LL([s.x, s.y])); return { id: s.id, x: p.x, y: p.y, dx: 0, dy: 0 }; });
  for (let pass = 0; pass < 6; pass++) for (let i = 1; i < q.length; i++) for (let j = 0; j < i; j++) {
    const a = q[i], b = q[j];
    let vx = (a.x + a.dx) - (b.x + b.dx), vy = (a.y + a.dy) - (b.y + b.dy), d = Math.hypot(vx, vy);
    if (d >= MIN) continue;
    if (d < 1e-6) { vx = 1; vy = 0; d = 1; }
    const k = (MIN - d) / 2 / d;
    a.dx += vx * k; a.dy += vy * k; b.dx -= vx * k; b.dy -= vy * k;
  }
  return Object.fromEntries(q.map((o) => [o.id, [o.dx, o.dy]]));
}
const shortName = (n) => n.replace(/ \(.*\)/, '').replace('sample depot', 'depot');
function stopIcon(s, num, off = [0, 0]) {
  const c = CAT[s.kind === 'depot' ? 'depot' : s.category]?.col || '#fff';
  const tr = `transform:translate(${off[0].toFixed(1)}px,${off[1].toFixed(1)}px)`;
  // name label: on the side the badge was pushed to, so two close stops read left and right
  const lab = `<span class="maplabel ${off[0] < -0.5 ? 'left' : ''} ${num == null ? 'off' : ''}" style="${tr}">${esc(shortName(s.name))}</span>`;
  return L.divIcon({ className: '', html: `<div class="stopicon" style="background:${c};${tr}">${num ?? '·'}</div>${lab}`, iconSize: [24, 24], iconAnchor: [12, 12] });
}
function drawStops() {
  const g = A.vec.stops.g;
  g.clearLayers();
  const hab = A.plan.sites[0];
  L.marker(LL([hab.x, hab.y]), { icon: L.divIcon({ className: '', html: '<div class="habicon">H</div><span class="maplabel hab">Habitat</span>', iconSize: [26, 26], iconAnchor: [13, 13] }) })
    .bindTooltip('Habitat (start, finish and the only shelter). Site picked by a stated rule: the flattest 110 m pad on the crater floor about 1 km east of the depot (assumption).').addTo(g);
  const off = declutter(A.plan.sites.slice(1));
  A.plan.sites.slice(1).forEach((s) => {
    const pos = A.cur.order.indexOf(s.id);
    const m = L.marker(LL([s.x, s.y]), { icon: stopIcon(s, pos >= 0 ? pos + 1 : null, off[s.id]), riseOnHover: true })
      .bindTooltip(`${esc(s.name)} · ${s.value} pts · ${s.dwell_min} min${pos < 0 ? ' · not in plan' : ''}`);
    m.on('click', () => { openTab('stops'); const el = document.getElementById('card-' + s.id); el?.scrollIntoView({ behavior: 'smooth' }); });
    m.addTo(g);
  });
  A.cur.waypoints.forEach((w) => {
    const m = L.marker(LL([w.x, w.y]), { draggable: true, icon: L.divIcon({ className: '', html: '<div class="wpicon"></div>', iconSize: [16, 16], iconAnchor: [8, 8] }) })
      .bindTooltip(`${esc(w.name)} (drag to move)`);
    m.on('dragend', () => { const p = m.getLatLng(); w.x = p.lng; w.y = p.lat; scheduleReplan(); });
    m.addTo(g);
  });
}
function drawPrecomputedRoute() {
  const g = A.vec.route.g;
  g.clearLayers();
  for (const leg of A.plan.plan.legs_xy) L.polyline(leg.map(LL), { color: ROUTE, weight: 5, opacity: 0.9 }).addTo(g);
}
function drawRoute() {
  const g = A.vec.route.g;
  g.clearLayers();
  const ev = A.res.eval;
  for (const leg of A.res.legs) L.polyline(leg.xy.map(LL), { color: '#111', weight: 8, opacity: 0.6, interactive: false }).addTo(g);
  for (const leg of A.res.legs) L.polyline(leg.xy.map(LL), { color: ROUTE, weight: 4.5, opacity: 0.95 })
    .bindTooltip(`Leg: ${f0(leg.dist_m)} m, ${f1(leg.time_s / 60)} min walking (modeled)`).addTo(g);
  // SEP-violating stretches
  let run = [];
  const flush = () => {
    if (run.length > 1) {
      L.polyline(run.map(LL), { color: SEPCOL, weight: 7, opacity: 0.95 }).bindTooltip('More than the SEP shelter limit from the habitat').addTo(g);
      L.polyline(run.map(LL), { color: '#111', weight: 2, dashArray: '2 7', interactive: false }).addTo(g);   // dashes: not colour alone
    }
    run = [];
  };
  ev.pts.forEach((p, i) => { if (ev.safety.sep.flags[i]) run.push(p.xy); else flush(); });
  flush();
  const wb = ev.safety.walkback;
  if (wb.at_time_xy) L.circleMarker(LL(wb.at_time_xy), { radius: 10, color: '#ffffff', weight: 3, fill: false })
    .bindTooltip(`Tightest walk-back point: ${f0(wb.min_time_margin_min)} min spare, ${f1(wb.min_o2_margin_pct_of_capacity)} % of O2 tank above reserve (modeled)`).addTo(g);
}
function drawAlternatives(selected) {
  const g = A.vec.alts.g;
  g.clearLayers();
  for (const a of A.plan.alternatives) {
    if (!selected.has(a.id)) continue;
    for (const leg of a.legs_xy) L.polyline(leg.map(LL), { color: ROUTE_COL[a.id], weight: 3, opacity: 0.95, dashArray: a.id === 'shortest' ? '6 5' : null })
      .bindTooltip(`${esc(a.name)} (precomputed by the Python planner)`).addTo(g);
  }
}

// ---------------------------------------------------------------- map clicks: waypoints and keep-out boxes
function setMode(mode) {
  A.mode = A.mode === mode ? null : mode;
  A.keepFirst = null;
  document.querySelectorAll('[data-mode]').forEach((b) => b.classList.toggle('on', b.dataset.mode === A.mode));
  $('#mapmode')?.remove();
  if (A.mode) {
    const d = document.createElement('div');
    d.id = 'mapmode'; d.className = 'mapmode';
    d.textContent = A.mode === 'wp' ? 'Click the map to add a waypoint (Esc to stop)' : 'Click two corners of a keep-out box (Esc to stop)';
    $('#map').appendChild(d);
  }
}
function onMapClick(e) {
  const x = e.latlng.lng, y = e.latlng.lat;
  if (x < 0 || y < 0 || x > 4000 || y > 4000) return;
  if (A.mode === 'wp') {
    A.cur.nWp += 1;
    const w = { id: 'wp' + A.cur.nWp, name: 'Waypoint ' + A.cur.nWp, x, y };
    A.cur.waypoints.push(w);
    A.cur.order.push(w.id);
    renderEditor(); drawStops(); scheduleReplan();
  } else if (A.mode === 'keep') {
    if (!A.keepFirst) { A.keepFirst = [x, y]; L.circleMarker(e.latlng, { radius: 4, color: Ch.C.verm }).addTo(A.keepGroup); return; }
    A.cur.keepouts.push([A.keepFirst[0], A.keepFirst[1], x, y]);
    A.keepFirst = null;
    drawKeepouts(); renderEditor(); scheduleReplan(true);
  }
}
function drawKeepouts() {
  A.keepGroup.clearLayers();
  for (const [x0, y0, x1, y1] of A.cur.keepouts) L.rectangle([[y0, x0], [y1, x1]], { color: Ch.C.verm, weight: 2, fillOpacity: 0.25, dashArray: '5 4' })
    .bindTooltip('User keep-out zone').addTo(A.keepGroup);
}
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && A.mode) setMode(A.mode); });

// ---------------------------------------------------------------- re-plan (worker)
let timer = null, rulesDirty = false, reqNo = 0;
function scheduleReplan(rules = false) {
  rulesDirty = rulesDirty || rules;
  clearTimeout(timer);
  timer = setTimeout(replan, 120);
}
async function replan() {
  const my = ++reqNo;
  const status = $('#live-status');
  if (status) status.textContent = 'Planning…';
  try {
    let rinfo = null;
    if (rulesDirty) { rulesDirty = false; rinfo = await call('rules', { rules: rulesNow() }); }
    const sites = siteList();
    const ids = sites.map((s) => s.id);
    const order = [0, ...A.cur.order.map((id) => ids.indexOf(id)), 0];
    const res = await call('plan', { sites, order, w: [...A.cur.w, 0], roles: A.roles, shelterMin: A.cur.shelterMin,
                                     mcRuns: pv('montecarlo.runs'), seed: 20261114 });
    if (my !== reqNo) return;
    res.sites = sites; res.order = order; res.rules = rinfo;
    res.sites.forEach((s, i) => { s.idx = res.site_idx[i]; });
    A.res = res;
    drawRoute(); drawStops(); renderLive(); renderSchedule(); renderSafety(); renderStops(); renderGo();
  } catch (err) {
    if (my !== reqNo) return;
    if (status) status.innerHTML = `<span style="color:#ff6b5b">${esc(err.message)}</span>`;
    $('#gochip').className = 'gochip nogo'; $('#gochip').textContent = 'NO-GO (no route)';
  }
}

// ---------------------------------------------------------------- checklist (same rules as run_plan.py)
function checklist() {
  const ev = A.res.eval, s = ev.safety, t = ev.totals, mc = A.res.mc;
  const target = pv('schedule.robust_p_on_time'), resv = 100 * pv('consumables.o2_reserve_fraction');
  const items = [
    ['EVA fits the time limit (planned)', t.duration_min <= A.limitMin, `${f0(t.duration_min)} of ${A.limitMin} min`],
    [`Home on time in ≥ ${Math.round(target * 100)} % of Monte Carlo runs`, mc.p_success >= target, `${pct(mc.p_success)} of ${f0(mc.runs)} runs in this browser (Python reference for the recommended plan: ${pct(A.plan.montecarlo.p_success)})`],
    ['Walkback rule: can always walk home with reserve O2', s.walkback.min_o2_margin_kg >= 0, `tightest O2 margin ${f1(s.walkback.min_o2_margin_pct_of_capacity)} % of tank above reserve`],
    ['Walkback rule: can always walk home within the EVA limit', s.walkback.min_time_margin_min >= 0, `tightest time margin ${f0(s.walkback.min_time_margin_min)} min`],
    [`SEP shelter reachable within ${A.cur.shelterMin} min everywhere`, s.sep.violating_points === 0, `farthest point ${f0(s.sep.max_walk_home_min)} min from shelter`],
    [`No route cell steeper than ${A.cur.slopeNogo}° (10 m grid)`, t.max_slope_deg <= A.cur.slopeNogo, `max ${f1(t.max_slope_deg)}°`],
    ['O2 left at return above reserve', s.consumables.o2_left_pct >= resv, `${f0(s.consumables.o2_left_pct)} % left (reserve ${resv} %)`],
    ['Battery left at return above 0', s.consumables.battery_left_pct > 0, `${f0(s.consumables.battery_left_pct)} % left`],
    ['Sample tubes collected (depot visited)', A.cur.order.includes('depot'), A.cur.order.includes('depot') ? 'Three Forks depot is on the route' : 'depot is NOT on the route'],
  ];
  return { go: items.every((i) => i[1]), items };
}
function renderGo() {
  const c = checklist();
  const chip = $('#gochip');
  chip.className = 'gochip ' + (c.go ? 'go' : 'nogo');
  chip.textContent = c.go ? 'GO · all 9 checks pass' : `NO-GO · ${c.items.filter((i) => !i[1]).length} check(s) fail`;
}

// ---------------------------------------------------------------- tabs
function setupTabs() {
  document.querySelectorAll('nav.tabs button').forEach((b) => b.onclick = () => openTab(b.dataset.tab));
  $('#btn-hud').onclick = () => A.hud?.open({ autoplay: true });
}
function openTab(id) {
  document.querySelectorAll('nav.tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === id)));
  document.querySelectorAll('.tabpane').forEach((p) => { p.hidden = p.id !== 'tab-' + id; });
}
A.openTab = openTab;

function renderStaticPanels() {
  const P = A.plan, rp = P.plan, mc = P.montecarlo;
  const names = rp.order.map((id) => siteById(id).name.replace(/ \(.*\)/, ''));
  $('#tab-plan').innerHTML = `
    <h2>Recommended plan ${B('modeled')}</h2>
    <p class="lead">Two astronauts visit ${rp.order.filter((id) => siteById(id).kind === 'stop').length} science sites, collect the ${A.vectors.depot_tubes.points.length} cached sample tubes and are home in ${hm(rp.totals.duration_min)}, inside the ${pv('mission.eva_time_limit')} h limit.</p>
    <p class="routeline">${names.map(esc).join(' → ')}</p>
    <div class="kpis">
      <div class="kpi"><div class="v">${rp.value} pts</div><div class="l">science value ${B('owner-set')}</div></div>
      <div class="kpi"><div class="v">${f0(rp.totals.duration_min)} min</div><div class="l">of ${A.limitMin} min limit</div></div>
      <div class="kpi"><div class="v">${pct(mc.p_success)}</div><div class="l">home on time, ${f0(mc.runs)} runs</div></div>
      <div class="kpi"><div class="v">${f2(rp.totals.dist_m / 1000)} km</div><div class="l">walked</div></div>
      <div class="kpi"><div class="v">${f0(rp.totals.walk_min)} + ${f0(rp.totals.work_min)}</div><div class="l">min walking + work</div></div>
      <div class="kpi"><div class="v">${f0(P.safety.walkback.min_time_margin_min)} min</div><div class="l">tightest walk-back margin</div></div>
    </div>
    <p class="small muted">The "Robust" rule: the most science points whose chance of getting home on time (with O2 above reserve) is at least ${Math.round(pv('schedule.robust_p_on_time') * 100)} % ${B('owner-set')}.
      Stop choice and order solved exactly with OR-Tools CP-SAT (${P.robust_plan.solver_status.toLowerCase()}, ${f0(P.robust_plan.solve_ms)} ms) by the Python planner.</p>

    <h3>Why this plan: science against risk ${B('modeled')}</h3>
    <div id="cands"></div>
    <div class="legendrow"><span><span class="sw" style="background:${Ch.C.sky};border-radius:50%"></span>meets the bar</span><span><span class="sw" style="background:${Ch.C.verm};border-radius:50%"></span>under the bar</span><span>◇ second walking model (check)</span></div>
    <p class="why" id="why-cands"></p>
    <details class="formulation"><summary>How the stops are chosen (the optimization)</summary>
      <table>
        <tr><td>Decide</td><td>which stops to visit and in which order: one closed tour from the habitat</td></tr>
        <tr><td>Maximise</td><td>science points; among equal plans, the shortest EVA</td></tr>
        <tr><td>Time</td><td>walking + work ≤ the time budget (one plan per budget: ${pv('schedule.budget_fractions').map((f) => Math.round(f * 100)).join(', ')} % of ${A.limitMin} min)</td></tr>
        <tr><td>Oxygen</td><td>O2 used ≤ tank minus the ${Math.round(100 * pv('consumables.o2_reserve_fraction'))} % reserve ${B('assumption')}</td></tr>
        <tr><td>Must do</td><td>the depot (sample tubes) is on every tour</td></tr>
        <tr><td>Shelter</td><td>stops more than ${pv('sep.shelter_time_limit_min')} min from the habitat are not offered ${B('assumption')}${P.sites.some((x) => x.sep_ok === false) ? ': ' + P.sites.filter((x) => x.sep_ok === false).map((x) => `${esc(x.name.replace(/ \(.*\)/, ''))} (${f0(x.walk_home_min)} min)`).join(', ') : ''}</td></tr>
        <tr><td>Travel times</td><td>the Balanced route between every pair of sites (${P.sites.length} × ${P.sites.length} matrix, A* / Dijkstra on the 10 m grid)</td></tr>
        <tr><td>Solver</td><td>Google OR-Tools CP-SAT, an exact solver: every candidate proven ${P.robust_plan.solver_status.toLowerCase()} in ${f0(Math.min(...P.candidates.map((c) => c.solve_ms)))}-${f0(Math.max(...P.candidates.map((c) => c.solve_ms)))} ms; checked against brute force in the tests</td></tr>
        <tr><td>Then</td><td>each candidate is simulated ${f0(mc.runs)} times; the rule above picks the plan</td></tr>
      </table>
      <p class="small muted">This is a prize-collecting orienteering problem. Full description: <a href="methods.html">Methods</a>, section 5.</p>
    </details>

    <h2>Your plan (live) ${B('modeled')}</h2>
    <p class="small muted">Change anything below: the route, timeline, safety checks and a ${f0(pv('montecarlo.runs'))}-run Monte Carlo are recomputed in your browser (Web Worker).</p>
    <div class="row"><label>Start from a candidate plan <select id="cand"></select></label></div>
    <ul class="stoplist" id="stoplist"></ul>
    <div class="row" id="addstops"></div>
    <div class="row">
      <button data-mode="wp" type="button">+ Waypoint on map</button>
      <button data-mode="keep" type="button">Draw keep-out box</button>
      <button id="clear-keep" type="button">Clear keep-outs</button>
      <button id="reset" type="button">Reset</button>
    </div>
    <h3>Route weights ${B('assumption')}</h3>
    <div class="row"><label>Profile <select id="profile">
      <option value="balanced">Balanced (equal weights)</option><option value="fastest">Fastest (= lowest energy)</option>
      <option value="safest">Safest</option><option value="shortest">Shortest distance (naive)</option><option value="custom">Custom</option></select></label></div>
    <div class="slider"><span>Time</span><input type="range" id="w0" min="0" max="1" step="0.05"><output id="w0o"></output></div>
    <div class="slider"><span>Energy</span><input type="range" id="w1" min="0" max="1" step="0.05"><output id="w1o"></output></div>
    <div class="slider"><span>Hazard</span><input type="range" id="w2" min="0" max="1" step="0.05"><output id="w2o"></output></div>
    <h3>Safety rules ${B('assumption')}</h3>
    <div class="slider"><span>No-go slope</span><input type="range" id="slope" min="10" max="25" step="1"><output id="slopeo"></output></div>
    <div class="slider"><span>SEP shelter limit</span><input type="range" id="shelter" min="20" max="90" step="5"><output id="sheltero"></output></div>
    <p class="small muted">No-go slope default 20°: the NASA xEVA ConOps walking-slope limit, a lunar suit value applied to Mars ${B('proxy')}. Roughness limit 0.2 m (fixed, assumption). SEP (solar particle event, i.e. solar storm) shelter limit default 60 min (assumption).
      Walking pace and power come from NASA lunar and Apollo suit data ${B('proxy')}, scaled to Mars gravity.</p>
    <div id="live"></div>

    <h2>Route options for the recommended stops ${B('modeled')}</h2>
    <p class="small muted">Precomputed by the Python planner (same stops, different weights). Click a row to show it on the map.</p>
    <div id="alts"></div>
    <h2>Trade-off: time vs hazard (Pareto set) ${B('modeled')}</h2>
    <div id="pareto"></div>
    <p class="small muted">Each dot is the best route for one weight setting (hazard weight 0 → 0.95). Filled dots are not beaten on both axes.
      Hazard exposure = minutes walked × hazard index (0 below 10° and 0.05 m roughness, 1 at the no-go limit). Energy is not a separate axis: with the constant-power pacing rule, walking energy = 352 W × time.</p>`;
  // candidates
  const sel = $('#cand');
  const cands = P.candidates.map((c) => ({ ...c, label: `${c.value} pts: ${c.stops.map((id) => siteById(id).name.replace(/ \(.*\)/, '')).join(', ')} · ${pct(c.p_success + 1e-9, 2)} on time${c.value === P.robust_plan.value ? ' (recommended)' : (c.p_success < pv('schedule.robust_p_on_time') ? ` (under the ${Math.round(100 * pv('schedule.robust_p_on_time'))} % bar)` : '')}` }));
  sel.innerHTML = cands.map((c, i) => `<option value="${i}" ${c.value === P.robust_plan.value ? 'selected' : ''}>${esc(c.label)}</option>`).join('');
  sel.onchange = () => { const c = cands[+sel.value]; A.cur.order = c.order.slice(1, -1).map((k) => P.sites[k].id).concat(A.cur.waypoints.map((w) => w.id)); renderEditor(); drawStops(); scheduleReplan(); };
  // science-vs-risk chart of the candidate plans (click a dot to load that plan below)
  const tgt = pv('schedule.robust_p_on_time');
  const altP = Object.fromEntries((P.alt_model_check?.candidates || []).map((c) => [c.value, c.p_success]));
  Ch.candidates($('#cands'), P.candidates, { bar: tgt, pick: P.robust_plan.value, alt: altP,
                                             onPick: (i) => { sel.value = String(i); sel.onchange(); $('#stoplist').scrollIntoView({ behavior: 'smooth', block: 'center' }); } });
  const under = P.candidates.filter((c) => c.p_success < tgt).sort((a, b) => a.value - b.value)[0];
  const top = P.max_science_plan;
  $('#why-cands').innerHTML = `<b>Why this matters.</b> Each extra stop buys science and spends the time buffer. The rule keeps the last plan above the ${Math.round(100 * tgt)} % line: ${rp.value} points at ${pct(mc.p_success)}.
    ${under ? `The ${under.value}-point plan ${tgt - under.p_success < 0.01 ? 'sits right on the line' : 'falls short'} (${pct(under.p_success + 1e-9, 2)}${altP[under.value] != null ? `; the second walking model gives ${pct(altP[under.value])}` : ''}), so that choice is a close call.` : ''}
    ${top && top.value !== rp.value && top.value !== under?.value ? `Taking all ${top.value} points gets the crew home on time in only ${pct(top.p_success, 0)} of runs.` : ''} Click a dot to load that plan.`;
  document.querySelectorAll('[data-mode]').forEach((b) => b.onclick = () => setMode(b.dataset.mode));
  $('#clear-keep').onclick = () => { A.cur.keepouts = []; drawKeepouts(); scheduleReplan(true); };
  $('#reset').onclick = () => { A.cur = defaultState(); sel.value = String(cands.findIndex((c) => c.value === P.robust_plan.value)); drawKeepouts(); syncControls(); updateNogoLayer(); updateLegend(); renderEditor(); drawStops(); scheduleReplan(true); };
  $('#profile').onchange = () => { const v = $('#profile').value; A.cur.profile = v; if (v !== 'custom') A.cur.w = pv('route_options.' + v).slice(0, 3); syncControls(); scheduleReplan(); };
  for (const k of [0, 1, 2]) $('#w' + k).oninput = () => {
    A.cur.w[k] = +$('#w' + k).value; A.cur.profile = 'custom';
    if (A.cur.w[0] + A.cur.w[1] <= 0) { A.cur.w[0] = 0.05; }
    syncControls(); scheduleReplan();
  };
  $('#slope').oninput = () => { A.cur.slopeNogo = +$('#slope').value; syncControls(); updateNogoLayer(); updateLegend(); scheduleReplan(true); };
  $('#shelter').oninput = () => { A.cur.shelterMin = +$('#shelter').value; syncControls(); scheduleReplan(); };
  syncControls();
  renderEditor();
  drawStops();
  // alternatives table
  const sel2 = new Set();
  const altName = { shortest: 'Shortest (naive)', balanced: 'Balanced (plan)' };
  const altHTML = () => `<table class="alts"><tr><th>Option</th><th>km</th><th>EVA min</th><th>kcal</th><th>max slope</th><th>caution min</th><th>reserve</th><th>home OK</th></tr>
    ${P.alternatives.map((a) => `<tr class="click ${sel2.has(a.id) ? 'sel' : ''}" data-alt="${a.id}"><td><span class="sw" style="background:${ROUTE_COL[a.id]}"></span>${esc(altName[a.id] || a.name)}</td>
      <td>${f2(a.dist_m / 1000)}</td><td>${f1(a.duration_min)}</td><td>${f0(a.walk_energy_kcal)}</td><td>${f1(a.max_slope_deg)}°</td>
      <td>${f1(a.caution_min)}</td><td>${f0(a.min_walkback_margin_min)} min<br><span class="muted">${f0(a.min_o2_margin_pct)} % O2</span></td><td>${pct(a.p_success ?? a.p_on_time)}</td></tr>`).join('')}</table>
    <p class="small muted">EVA min = whole EVA (walking + ${f0(P.plan.totals.work_min)} min of work). kcal = walking energy per person. caution min = minutes on cells with any hazard (slope over 10° or roughness over 0.05 m).
      reserve = tightest walk-back margin along the route, in time and in % of the O2 tank above the reserve. Lowest-energy gives the same route as Fastest: with constant-power pacing, walking energy = 352 W × time.
      home OK = share of ${f0(P.montecarlo.runs)} Python Monte Carlo runs home within ${A.limitMin} min with O2 above reserve (same measure as the headline).</p>`;
  const aF = P.alternatives.find((a) => a.id === 'fastest'), aS = P.alternatives.find((a) => a.id === 'safest'), aB = P.alternatives.find((a) => a.id === 'balanced');
  const whyAlts = aF && aS && aB ? `<p class="why"><b>Why this matters.</b> Compared with Fastest, the Safest route costs only +${f1(aS.duration_min - aF.duration_min)} min and +${f0(aS.dist_m - aF.dist_m)} m,
    but cuts time on caution terrain from ${f1(aF.caution_min)} to ${f1(aS.caution_min)} min and the steepest cell from ${f1(aF.max_slope_deg)}° to ${f1(aS.max_slope_deg)}°. A small detour buys a large cut in exposure.
    The plan uses Balanced: ${f1(aB.caution_min)} caution min for +${f1(aB.duration_min - aF.duration_min)} min.</p>` : '';
  const drawAlts = () => {
    $('#alts').innerHTML = altHTML() + whyAlts;
    document.querySelectorAll('[data-alt]').forEach((tr) => tr.onclick = () => {
      const id = tr.dataset.alt; sel2.has(id) ? sel2.delete(id) : sel2.add(id); drawAlternatives(sel2); drawAlts();
    });
  };
  drawAlts();
  Ch.pareto($('#pareto'), P.pareto, P.alternatives);
  renderChecks();
}
function syncControls() {
  $('#profile').value = A.cur.profile;
  for (const k of [0, 1, 2]) { $('#w' + k).value = A.cur.w[k]; $('#w' + k + 'o').textContent = A.cur.w[k].toFixed(2); }
  $('#slope').value = A.cur.slopeNogo; $('#slopeo').textContent = A.cur.slopeNogo + '°';
  $('#shelter').value = A.cur.shelterMin; $('#sheltero').textContent = A.cur.shelterMin + ' min';
}
function nameOf(id) { return siteById(id)?.name ?? A.cur.waypoints.find((w) => w.id === id)?.name ?? id; }
function renderEditor() {
  const ul = $('#stoplist');
  ul.innerHTML = `<li><span class="n" style="background:${Ch.C.sky}">H</span><span class="nm">Habitat (start)</span></li>` +
    A.cur.order.map((id, i) => {
      const s = siteById(id);
      const c = s ? CAT[s.kind === 'depot' ? 'depot' : s.category].col : Ch.C.yellow;
      const extra = s ? `${s.value} pts · ${s.dwell_min} min` : 'pass through';
      return `<li><span class="n" style="background:${c}">${i + 1}</span><span class="nm" title="${esc(nameOf(id))}">${esc(shortName(nameOf(id)))} <span class="small muted">${extra}</span></span>
        <button data-up="${i}" title="Move earlier" aria-label="Move ${esc(nameOf(id))} earlier">↑</button><button data-dn="${i}" title="Move later" aria-label="Move later">↓</button><button data-rm="${i}" title="Remove" aria-label="Remove">✕</button></li>`;
    }).join('') + `<li><span class="n" style="background:${Ch.C.sky}">H</span><span class="nm">Habitat (finish)</span></li>`;
  ul.querySelectorAll('[data-up]').forEach((b) => b.onclick = () => { const i = +b.dataset.up; if (i > 0) { const o = A.cur.order; [o[i - 1], o[i]] = [o[i], o[i - 1]]; after(); } });
  ul.querySelectorAll('[data-dn]').forEach((b) => b.onclick = () => { const i = +b.dataset.dn, o = A.cur.order; if (i < o.length - 1) { [o[i + 1], o[i]] = [o[i], o[i + 1]]; after(); } });
  ul.querySelectorAll('[data-rm]').forEach((b) => b.onclick = () => {
    const id = A.cur.order.splice(+b.dataset.rm, 1)[0];
    A.cur.waypoints = A.cur.waypoints.filter((w) => w.id !== id);
    after();
  });
  const missing = A.plan.sites.slice(1).filter((s) => !A.cur.order.includes(s.id));
  $('#addstops').innerHTML = missing.length ? '<span class="small muted">Add:</span> ' + missing.map((s) => `<button data-add="${s.id}" type="button">+ ${esc(s.name.replace(/ \(.*\)/, ''))}</button>`).join(' ') : '';
  $('#addstops').querySelectorAll('[data-add]').forEach((b) => b.onclick = () => { A.cur.order.push(b.dataset.add); after(); });
  function after() { renderEditor(); drawStops(); scheduleReplan(); }
}

function renderLive() {
  const ev = A.res.eval, t = ev.totals, mc = A.res.mc, T = A.res.timing;
  const value = A.cur.order.reduce((a, id) => a + (siteById(id)?.value || 0), 0);
  const snapped = A.res.snapped.length ? `<p class="warn">Moved to the nearest safe cell: ${A.res.snapped.map((id) => esc(nameOf(id))).join(', ')}.</p>` : '';
  $('#live').innerHTML = `<h3>Result ${B('modeled')}</h3>${snapped}
    <div class="kpis">
      <div class="kpi"><div class="v">${value} pts</div><div class="l">science value</div></div>
      <div class="kpi"><div class="v" style="color:${t.duration_min <= A.limitMin ? 'inherit' : '#ff6b5b'}">${f0(t.duration_min)} min</div><div class="l">of ${A.limitMin} min (${f0(t.walk_min)} walk)</div></div>
      <div class="kpi"><div class="v">${pct(mc.p_success)}</div><div class="l">home on time, ${f0(mc.runs)} browser runs</div></div>
      <div class="kpi"><div class="v">${f2(t.dist_m / 1000)} km</div><div class="l">walked, +${f0(t.gain_m)} m climb</div></div>
      <div class="kpi"><div class="v">${f0(t.walk_energy_kcal)} kcal</div><div class="l">walking energy (per person)</div></div>
      <div class="kpi"><div class="v">${f1(t.max_slope_deg)}°</div><div class="l">max cell slope · ${f1(t.caution_min)} caution min</div></div>
    </div>
    <p class="small muted" id="live-status">Computed in your browser in ${f0(T.total_ms)} ms: A* ${f0(T.astar_ms)} ms (${f0(T.expanded)} cells expanded), walk-home field ${f0(T.field_ms)} ms, Monte Carlo ${f0(T.mc_ms)} ms.
    ${A.res.rules ? `Rules rebuilt in ${f0(A.res.rules.build_ms)} ms (no-go share ${pct(A.res.rules.nogo_share)}).` : ''}
    The browser Monte Carlo uses its own random numbers, so it can differ from the Python result by about ±0.3 %.</p>`;
}

// ---------------------------------------------------------------- schedule tab
function colorOfRow(r) {
  const s = A.res.sites.find((x) => x.id === r.at);
  return CAT[s?.kind === 'depot' ? 'depot' : s?.category]?.col || Ch.C.yellow;
}
function renderSchedule() {
  const ev = A.res.eval, mc = A.res.mc, P = A.plan;
  const pane = $('#tab-schedule');
  pane.innerHTML = `
    <h2>EVA timeline (your plan) ${B('modeled')}</h2>
    <div id="gantt"></div>
    <div class="legendrow"><span><span class="sw" style="background:#5a6573"></span>walk</span>${Object.values(CAT).slice(0, 4).map((c) => `<span><span class="sw" style="background:${c.col}"></span>${c.label}</span>`).join('')}</div>
    <p class="why"><b>Why this matters.</b> Work at the stops is ${f0(ev.totals.work_min)} of the ${f0(ev.totals.duration_min)} planned minutes (${f0(100 * ev.totals.work_min / ev.totals.duration_min)} %); walking is ${f0(ev.totals.walk_min)}.
      So the lever on this EVA is task time, not route length.</p>
    <p class="small muted">Buddy rule: EV1 and EV2 walk the same route and work at the same stop. Roles are this project's operational plan ${B('assumption')}. Work times ${B('assumption')}.</p>
    <table><tr><th>Block</th><th>start</th><th>end</th><th>EV1</th><th>EV2</th></tr>
    ${ev.rows.map((r) => `<tr><td>${r.kind === 'walk' ? `Walk to ${esc(nameOf(r.to))} <span class="muted">(${f2(r.dist_m / 1000)} km)</span>` : `<b>${esc(r.name)}</b>`}</td>
      <td>${f0(r.t0_min)}</td><td>${f0(r.t1_min)}</td><td class="small" style="text-align:left">${esc(r.EV1 || '')}</td><td class="small" style="text-align:left">${esc(r.EV2 || '')}</td></tr>`).join('')}</table>
    <h2>Consumables burn-down ${B('modeled')}</h2>
    <div id="burn"></div>
    <div class="legendrow"><span><span class="sw" style="background:${Ch.C.sky}"></span>O2 left</span><span><span class="sw" style="background:${Ch.C.orange}"></span>Battery left</span><span><span class="sw" style="background:${Ch.C.verm}"></span>O2 reserve / time limit</span></div>
    <p class="small muted">O2 from metabolic energy (0.081 kg per MJ, from NASA BVAD). Tank ${pv('consumables.o2_capacity_kg')} kg ${B('assumption')}. Battery ${pv('consumables.battery_capacity_wh')} W h (Apollo PLSS) at a constant ${pv('consumables.battery_draw_w')} W ${B('assumption')}.</p>
    <h2>Risk: Monte Carlo (your plan) ${B('modeled')}</h2>
    <div id="hist"></div>
    <p><b>${pct(mc.p_success)}</b> of ${f0(mc.runs)} runs get home on time with O2 above reserve. Median ${f0(mc.duration_min.p50)} min, P95 ${f0(mc.duration_min.p95)} min (limit ${A.limitMin}).</p>
    <p class="why"><b>Why this matters.</b> On paper this plan has ${f0(A.limitMin - ev.totals.duration_min)} min to spare. In the simulation, 1 run in 20 still takes longer than ${f0(mc.duration_min.p95)} min.
      A plan that only "fits the limit" is not enough; the rule asks for ${Math.round(100 * pv('schedule.robust_p_on_time'))} % of runs.</p>
    <p class="small muted">Each run draws a walking-speed factor (σ ${pv('montecarlo.speed_sigma')}), a metabolic factor (σ ${pv('montecarlo.metabolic_sigma')}) and a work-time factor per stop (σ ${pv('montecarlo.dwell_sigma')}), all log-normal ${B('assumption')}.
      Python reference for the recommended plan: ${pct(P.montecarlo.p_success, 2)} of ${f0(P.montecarlo.runs)} runs.</p>
    <h2>What drives the risk? (tornado, recommended plan) ${B('modeled')}</h2>
    <div id="tornado"></div>
    <div class="legendrow"><span><span class="sw" style="background:${Ch.C.sky}"></span>shorter EVA</span><span><span class="sw" style="background:${Ch.C.orange}"></span>longer EVA</span></div>
    <p class="why"><b>Why this matters.</b> ${(() => { const r = P.montecarlo.tornado.rows, work = r.filter((x) => x.input.startsWith('Work time')).length, top = r[0];
      return `The biggest single driver is ${esc(top.input.replace(/ \(.*\)/, '').replace('Work time: ', 'work time at '))} (${f0(top.swing_min)} min swing); ${work} of the ${r.length} inputs are task times. To cut risk, tighten or shorten tasks first; a shorter route helps less.`; })()}</p>
    <p class="small muted">Each input moved to its 10th and 90th percentile, all others at their median. Computed by the Python planner for the recommended plan.</p>`;
  Ch.gantt($('#gantt'), ev.rows, A.limitMin, colorOfRow);
  Ch.burnDown($('#burn'), ev.burn_down, A.limitMin);
  Ch.histogram($('#hist'), mc.histogram, mc.duration_min.p50, mc.duration_min.p95);
  Ch.tornado($('#tornado'), P.montecarlo.tornado);
}

// ---------------------------------------------------------------- stops tab
function nearestPhoto(s) {
  const ph = A.vectors.pov.photos.map((p) => ({ p, d: Math.hypot(p.x - s.x, p.y - s.y) }));
  const color = ph.filter((q) => q.p.instrument.startsWith('MCZ') && q.d < 150).sort((a, b) => a.d - b.d)[0];
  return color || ph.sort((a, b) => a.d - b.d)[0];
}
function renderStops() {
  const pane = $('#tab-stops');
  const stops = A.plan.sites.slice(1);
  pane.innerHTML = `<h2>Science stops and the depot</h2>
    <p class="small muted">All six sites are real Perseverance sample or study sites. Positions, quotes and samples come from the NASA PDS Mars 2020 Initial Reports (boulder field: NASA Science blog and a rover waypoint). Science value = the team's rubric (fine-grained layered rock 10, delta layer sequence 6, transported boulders 4) ${B('owner-set')}; the category of each site is a science judgement.</p>` +
    stops.map((s) => {
      const pos = A.cur.order.indexOf(s.id);
      const np = nearestPhoto(s);
      const c = CAT[s.kind === 'depot' ? 'depot' : s.category];
      const tubes = s.kind === 'depot' ? `<p class="small">${A.vectors.depot_tubes.points.length} tubes: ${A.vectors.depot_tubes.points.map((t) => esc(t.name)).join(', ')} (dropped sols ${A.vectors.depot_tubes.points[0].drop_sol}-${A.vectors.depot_tubes.points.at(-1).drop_sol}). ${esc(A.vectors.depot_tubes.note)}</p>` : '';
      return `<div class="card" id="card-${s.id}">
        <h3><span class="sw" style="background:${c.col}"></span>${esc(s.name)} ${pos >= 0 ? `<span class="badge modeled">stop ${pos + 1} in your plan</span>` : '<span class="badge derived">not in plan</span>'}</h3>
        <div class="small muted">${esc(c.label)}</div>
        <div class="facts">
          <div><span>Science value</span><b>${s.kind === 'depot' ? 'required task' : s.value + ' pts'}</b> ${B('owner-set')}</div>
          <div><span>Work time</span><b>${s.dwell_min} min</b> ${B('assumption')}</div>
          <div title="Apollo lunar EVA metabolic rate for this kind of task"><span>Work rate</span><b>${s.work_w} W</b> ${B('proxy')}</div>
          <div><span>Walk home</span><b>${f0(s.walk_home_min)} min</b> ${B('modeled')}</div>
        </div>${s.sep_ok ? '' : '<p class="warn">Outside the SEP shelter limit: the optimizer does not offer this stop.</p>'}
        ${s.task ? `<p><b>Task:</b> ${esc(s.task)}</p>` : ''}
        ${s.why_category ? `<p><b>Science goal:</b> ${esc(s.why_category)}</p>` : ''}
        ${s.quote ? `<blockquote>"${esc(s.quote)}"</blockquote><div class="credit">${esc(s.source)}${s.samples ? ' · samples: ' + esc(s.samples) : ''}</div>` : `<div class="credit">${esc(s.source || '')}</div>`}
        ${s.look_for ? `<p><b>What to look for:</b> ${esc(s.look_for)}</p>` : ''}
        ${tubes}
        ${np ? `<details ${s.kind !== 'depot' ? 'open' : ''}><summary class="small">What you'll see (rover photo)</summary>${photoHTML(np.p, np.d)}</details>` : ''}
        <p class="credit">Position: ${esc(s.position_source)}. Planning cell ${f1(s.snap_m)} m from it. Elevation ${f1(s.elev_m)} m ${B('real')}.</p>
        <div class="row"><button data-zoom="${s.id}" type="button">Show on map</button>
          ${pos >= 0 ? `<button data-out="${s.id}" type="button">Remove from plan</button>` : `<button data-in="${s.id}" type="button">Add to plan</button>`}</div>
      </div>`;
    }).join('');
  pane.querySelectorAll('[data-zoom]').forEach((b) => b.onclick = () => { const s = siteById(b.dataset.zoom); A.map.setView(LL([s.x, s.y]), 0.5); });
  pane.querySelectorAll('[data-out]').forEach((b) => b.onclick = () => { A.cur.order = A.cur.order.filter((id) => id !== b.dataset.out); renderEditor(); drawStops(); scheduleReplan(); });
  pane.querySelectorAll('[data-in]').forEach((b) => b.onclick = () => { A.cur.order.push(b.dataset.in); renderEditor(); drawStops(); scheduleReplan(); });
}

// ---------------------------------------------------------------- safety tab
function renderSafety() {
  const ev = A.res.eval, s = ev.safety, c = checklist(), P = A.plan;
  const donkiN = A.donki.events.length;
  const isModel = (e) => e.instruments.some((i) => i.displayName.startsWith('MODEL'));
  const donkiDet = A.donki.events.filter((e) => !isModel(e));
  const donkiDays = new Set(A.donki.events.map((e) => e.eventTime.slice(0, 10))).size;
  const may = pv('sep.may2024_event_dose_ugy'), rate = pv('sep.background_dose_rate_ugy_per_day');
  $('#tab-safety').innerHTML = `
    <div class="gobanner ${c.go ? 'go' : 'nogo'}">${c.go ? 'GO: all 9 checks pass' : 'NO-GO: ' + c.items.filter((i) => !i[1]).length + ' check(s) fail'} <span class="badge modeled">modeled</span></div>
    <ul class="checklist">${c.items.map(([r, ok, d]) => `<li><span class="${ok ? 'ok' : 'bad'}">${ok ? '✔' : '✖'}</span><span>${esc(r)}<br><span class="small muted">${esc(d)}</span></span></li>`).join('')}</ul>
    <h2>Walk-back rule ${B('modeled')}</h2>
    <p class="small">At every 10 m cell of the route the crew must be able to walk home by the fastest safe route, arrive within the ${A.limitMin} min limit, and still have the O2 reserve (${Math.round(100 * pv('consumables.o2_reserve_fraction'))} % ${B('assumption')}). Rule from Apollo: "the crewmen shall be able to walk back … on the consumables remaining".</p>
    <div class="kpis">
      <div class="kpi"><div class="v">${f0(s.walkback.min_time_margin_min)} min</div><div class="l">tightest time margin</div></div>
      <div class="kpi"><div class="v">${f1(s.walkback.min_o2_margin_pct_of_capacity)} %</div><div class="l">tightest O2 margin (of tank)</div></div>
      <div class="kpi"><div class="v">${f0(s.walkback.at_time_elapsed_min)} min</div><div class="l">into the EVA, ${f0(s.walkback.at_time_walk_home_min)} min from home</div></div>
    </div>
    <p class="why"><b>Why this matters.</b> This is the point-of-no-return check. The tightest moment is ${f0(s.walkback.at_time_elapsed_min)} min into the EVA, ${f0(s.walkback.at_time_walk_home_min)} min from home${s.walkback.at_time_walk_home_min < s.sep.max_walk_home_min - 1 ? `, not at the farthest point (${f0(s.sep.max_walk_home_min)} min from home)` : ''}: late in the day the clock runs out before the distance does.</p>
    <button id="show-tight" type="button">Show the tightest point on the map</button>
    <h2>Solar storm (SEP) shelter rule ${B('assumption')}</h2>
    <p class="small">During a solar particle event alert the crew must reach the habitat within <b>${A.cur.shelterMin} min</b> (slider on the Plan tab). Farthest point of your route: <b>${f0(s.sep.max_walk_home_min)} min</b> from shelter.
      ${s.sep.violating_points ? `<b style="color:#ff6b5b">${s.sep.violating_points} route points break the rule (red on the map).</b>` : 'No route point breaks the rule.'}</p>
    <button id="sep-replay" class="primary" type="button">Replay a solar storm alert in the HUD</button>
    <p class="small muted">The replay plays the EVA and triggers the alert at the point farthest from shelter, then re-plans the way home live.</p>
    <div class="note small">Real alert data ${B('proxy')}: ${donkiN} solar energetic particle (SEP) records in NASA CCMC DONKI between 2024-05-01 and 2024-06-29 (cached), on ${donkiDays} days: ${donkiDet.length} instrument detections and ${donkiN - donkiDet.length} model forecasts (one storm can have several records). They are near-Earth records, not measured at Mars. First detection: ${esc(donkiDet[0].eventTime)}, ${esc(donkiDet[0].instruments.map((i) => i.displayName).join('; '))}.</div>
    <h2>Radiation dose estimate ${B('proxy')}</h2>
    <p><b>${f0(s.dose.background_ugy)} µGy</b> absorbed dose for this ${f0(ev.totals.duration_min)} min EVA, from the Curiosity RAD background of ${rate} µGy/day measured at Gale crater (NASA PIA17600), not Jezero.
      For scale: NASA says astronauts on Mars during the 20 May 2024 storm would have received <b>${may.toLocaleString('en-US')} µGy</b>, about ${f0(may / rate)} days of background, which is why the shelter rule exists. Dose equivalent (mSv) is not estimated.</p>
    <h2>Consumables at return ${B('modeled')}</h2>
    <p>O2 left ${f0(s.consumables.o2_left_pct)} % (${f2(s.consumables.o2_used_kg)} kg used of ${pv('consumables.o2_capacity_kg')} kg) · battery left ${f0(s.consumables.battery_left_pct)} %.</p>
    <p class="small muted">Python reference for the recommended plan: tightest margin ${f0(P.safety.walkback.min_time_margin_min)} min / ${f1(P.safety.walkback.min_o2_margin_pct_of_capacity)} % O2, farthest from shelter ${f0(P.safety.sep.max_walk_home_min)} min.</p>`;
  $('#show-tight').onclick = () => { const xy = s.walkback.at_time_xy; if (xy) A.map.setView(LL(xy), 1); };
  $('#sep-replay').onclick = () => A.hud.open({ sepReplay: true });
}

// ---------------------------------------------------------------- checks tab (validation)
function renderChecks() {
  const V = A.plan.validation, ax = V.astar_vs_dijkstra, ap = V.apollo14_speed_check, s2 = V.route_slope_on_2m_grid;
  const drives = V.rover_drives;
  $('#tab-checks').innerHTML = `
    <h2>Does the planner work? ${B('modeled')}</h2>
    <p class="small muted">Results of the automatic checks (pytest) and of the comparison with real rover drives. Judges: this is the evidence behind the numbers.</p>
    <div class="card"><b>A* = Dijkstra, exactly.</b> On the ${ax.legs.length} legs of the recommended plan, A* and scipy Dijkstra give the same cost (max relative difference ${ax.max_rel_diff}). Also checked on random grids in the tests.</div>
    <div class="card"><b>Browser = Python.</b> This page re-implements the planner in JavaScript (Web Worker). A test runs both on random fixture grids and on this grid: same route cost (to 1e-12), same cells, same plan totals. <span id="chk-live"></span></div>
    <div class="card"><b>Slope check.</b> Recommended route: max 10 m cell slope ${f1(A.plan.plan.totals.max_slope_deg)}° (limit 20°). On the finer 2 m grid: median ${f1(s2.p50_deg)}°, P95 ${f1(s2.p95_deg)}°, max ${f1(s2.max_deg)}°; ${f2(100 * s2.share_above_20_deg)} % of points are just over 20°.</div>
    <div class="card"><b>Walking model vs Apollo 14.</b> On ${ap.legs.length} uphill legs (lunar gravity, Apollo 14's own pace and metabolic rate) the model predicts a mean ${f2(ap.mean_model_kmh)} km/h vs ${f2(ap.mean_measured_kmh)} km/h measured (mean error per leg ${f2(ap.mean_abs_error_kmh)} km/h).</div>
    <h3>Planned route vs the real Perseverance drive ${B('real')} ${B('modeled')}</h3>
    <p class="small muted">A rover is not a human, but its drivers also had to avoid steep and rough ground, so a planner that sees hazards should stay closer to the rover's real path than a straight line does. Share of the planned path within 25 m of the rover's real path:</p>
    <table><tr><th>Drive</th><th>Balanced</th><th>Safest</th><th>Straight line</th><th></th></tr>
    ${drives.map((d, i) => `<tr><td>${esc(d.name)}<br><span class="small muted">sols ${d.rover_sols.join('-')}</span></td>
      <td>${pct(d.options.balanced.share_of_planned_within_m['25'], 0)}</td><td>${pct(d.options.safest.share_of_planned_within_m['25'], 0)}</td>
      <td>${pct(d.straight_line.share_of_planned_within_m['25'], 0)}</td><td><button data-drive="${i}" type="button">Map</button></td></tr>`).join('')}</table>
    <div class="row"><button id="drive-clear" type="button">Clear the comparison from the map</button></div>
    <p class="small">Crater floor drive: the planner follows the rover clearly better than a straight line. Delta-top climb: inconclusive (the rover took a longer path the 10 m grid cannot explain). Reported as measured.</p>
    <p class="small"><a href="methods.html">Full methods, assumptions and data sources →</a></p>`;
  $('#drive-clear').onclick = () => A.vec.extra.g.clearLayers();
  document.querySelectorAll('[data-drive]').forEach((b) => b.onclick = () => {
    const d = drives[+b.dataset.drive], g = A.vec.extra.g;
    g.clearLayers();
    for (const ln of d.rover_xy) L.polyline(ln.map(LL), { color: '#fff', weight: 4 }).bindTooltip('Real rover path').addTo(g);
    L.polyline(d.options.balanced.xy.map(LL), { color: Ch.C.sky, weight: 3 }).bindTooltip('Planned (Balanced)').addTo(g);
    L.polyline([LL(d.start_xy), LL(d.end_xy)], { color: Ch.C.purple, weight: 2, dashArray: '5 5' }).bindTooltip('Straight line').addTo(g);
    A.map.fitBounds(L.latLngBounds(d.rover_xy.flat().map(LL)).pad(0.2));
  });
}
A.renderChecksLive = () => {
  const el = $('#chk-live');
  if (el && A.initInfo) el.textContent = `In this browser: model built in ${f0(A.initInfo.build_ms)} ms (${f0(A.initInfo.edges)} edges).`;
};

main().then(() => A.renderChecksLive()).catch((e) => { console.error(e); showError('Could not start: ' + e.message); });
