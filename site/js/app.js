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
const hm = (min) => { const m = Math.round(min); return m % 60 ? `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')} min` : `${m / 60} h`; };
const TAGHELP = { real: 'Measured data', derived: 'Computed from real data by a stated method', modeled: "Output of this project's model",
                  assumption: 'A value chosen without a verified source (listed in ASSUMPTIONS)', proxy: 'Data from somewhere else (Gale crater, the Moon, near-Earth space) standing in for Jezero',
                  'owner-set': 'A mission-design choice by the project owner' };
const B = (k) => `<span class="tag tag-${k === 'owner-set' ? 'owner' : k}" title="${TAGHELP[k] || ''}">${k}</span>`;
const hmm = (min) => `${Math.floor(min / 60)}:${String(Math.round(min % 60)).padStart(2, '0')}`;   // clock time h:mm
const sgn = (v, f) => (v >= 0 ? '+' : '−') + f(Math.abs(v));
const pv = (k) => E.pv(A.params, k);
const LL = (xy) => [xy[1], xy[0]];         // local metres (x east, y north) -> Leaflet [lat, lng]
const CAT = {
  fine_grained_layered_rock: { col: Ch.C.orange, label: 'Fine-grained layered rock' },
  delta_layer_sequence: { col: Ch.C.sky, label: 'Delta layer sequence' },
  transported_boulders: { col: Ch.C.purple, label: 'Transported boulders' },
  depot: { col: Ch.C.green, label: 'Sample depot (required)' },
  waypoint: { col: Ch.C.yellow, label: 'Your waypoint' },
};
const LABEL_DIR = { wildcat_ridge: 'left', amalik: 'left', hidden_harbor: 'left' };
const ROUTE = Ch.C.yellow, SEPCOL = Ch.C.purple;   // plan route / SEP-rule violations
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
  map.attributionControl.addAttribution('HiRISE: NASA/JPL-Caltech/Univ. of Arizona; DTM and image mosaic: USGS (Fergason et al. 2020); rover data: NASA/JPL-Caltech; <a href="methods.html#sources">all credits</a>');
  const b = A.layers.layers[0].bounds;
  map.fitBounds([[700, 1250], [2250, 2800]]);   // habitat (y 965 m) and its label stay in view
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
    .bindTooltip(`Rover waypoint ${esc(p.rmc)}, sol ${p.sol}`).addTo(wp);
  A.vec.waypoints = { title: 'Rover waypoints', kind: 'real', g: wp, on: false };
  const dp = L.layerGroup();
  for (const p of A.vectors.depot_tubes.points) L.circleMarker(LL([p.x, p.y]), { radius: 4, color: '#111', weight: 1, fillColor: Ch.C.green, fillOpacity: 1 })
    .bindTooltip(`${esc(p.name)} (${esc(p.sample)}), dropped sol ${p.drop_sol}<br>rover position at drop, not the tube itself`).addTo(dp);
  A.vec.depot = { title: 'Depot tubes (10)', kind: 'real', g: dp, on: true };
  const pov = L.layerGroup();
  for (const ph of A.vectors.pov.photos) L.circleMarker(LL([ph.x, ph.y]), { radius: 5, color: '#111', weight: 1, fillColor: '#fff', fillOpacity: 0.9 })
    .bindPopup(photoHTML(ph, null)).addTo(pov);
  A.vec.pov = { title: 'Rover photos (22)', kind: 'real', g: pov, on: false };
  A.vec.alts = { title: 'Route options', kind: 'modeled', g: L.layerGroup(), on: true };
  A.vec.route = { title: 'Your plan route', kind: 'modeled', g: L.layerGroup(), on: true };
  A.vec.stops = { title: 'Habitat + stops', kind: 'real', g: L.layerGroup(), on: true };
  A.vec.extra = { title: 'Checks overlay', kind: 'modeled', g: L.layerGroup(), on: true };
  for (const k of ['traverse', 'depot', 'alts', 'route', 'stops', 'extra']) if (A.vec[k].on) A.vec[k].g.addTo(map);
  if (A.vec.waypoints.on) A.vec.waypoints.g.addTo(map);
  A.keepGroup = L.layerGroup().addTo(map);

  L.control.scale({ imperial: false, metric: true, maxWidth: 160, position: 'bottomleft' }).addTo(map);
  layerControl();
  legendControl();
  readoutControl();
  map.on('click', onMapClick);
  map.on('mousemove', (e) => updateReadout(e.latlng));
}

function photoHTML(ph, distM) {
  const d = distM != null ? `<br>Nearest rover photo: taken ${f0(distM)} m from this stop.` : '';
  return `<img class="photo" src="assets/${esc(ph.file)}" alt="Perseverance ${esc(ph.instrument)} image, sol ${ph.sol}" loading="lazy">
    <div class="credit">Image: ${esc(ph.credit)}, ${esc(ph.instrument)}, sol ${ph.sol}, rover site ${ph.site}${d}
    <br><a href="${esc(ph.page)}" target="_blank" rel="noopener">raw image page</a> ${B('real')}</div>`;
}

function layerControl() {
  const Ctl = L.Control.extend({
    onAdd() {
      const d = L.DomUtil.create('div', 'mctl');
      L.DomEvent.disableClickPropagation(d); L.DomEvent.disableScrollPropagation(d);
      let html = '<button class="toggle" type="button" aria-label="Hide layers">–</button><h4>Layers</h4><div class="body"><div class="grp">Images and terrain</div>';
      for (const [id, r] of Object.entries(A.raster)) {
        html += `<div class="lyr"><label title="${esc(r.lyr.processing || '')}"><input type="checkbox" data-r="${id}" ${r.on ? 'checked' : ''}> ${esc(r.lyr.title)} ${B(r.lyr.kind)}</label>
                 <input type="range" min="0" max="1" step="0.05" value="${r.opacity}" data-op="${id}" aria-label="${esc(r.lyr.title)} opacity"></div>`;
      }
      html += '<div class="grp">Mission data</div>';
      for (const [id, v] of Object.entries(A.vec)) {
        if (id === 'extra') continue;
        html += `<div class="lyr"><label><input type="checkbox" data-v="${id}" ${v.on ? 'checked' : ''}> ${esc(v.title)} ${B(v.kind)}</label><span></span></div>`;
      }
      html += '</div>';
      d.innerHTML = html;
      const tg = d.querySelector('.toggle');
      tg.onclick = () => { d.classList.toggle('collapsed'); tg.textContent = d.classList.contains('collapsed') ? '+' : '–'; };
      d.querySelectorAll('[data-r]').forEach((cb) => cb.onchange = () => {
        const r = A.raster[cb.dataset.r]; r.on = cb.checked;
        r.on ? r.o.addTo(A.map) : r.o.remove();
        reorderLayers(); updateLegend();
      });
      d.querySelectorAll('[data-op]').forEach((sl) => sl.oninput = () => {
        const r = A.raster[sl.dataset.op]; r.opacity = +sl.value; r.o.setOpacity(r.opacity);
      });
      d.querySelectorAll('[data-v]').forEach((cb) => cb.onchange = () => {
        const v = A.vec[cb.dataset.v]; v.on = cb.checked; v.on ? v.g.addTo(A.map) : v.g.remove();
      });
      d.classList.add('collapsed'); tg.textContent = '+'; tg.setAttribute('aria-label', 'Show layers');
      return d;
    },
  });
  new Ctl({ position: 'topright' }).addTo(A.map);
}
function reorderLayers() {
  const order = ['ortho', 'hillshade', 'elevation', 'slope', 'roughness', 'themis_day', 'themis_night', 'nogo', 'depot_closeup'];
  for (const id of order) if (A.raster[id]?.on) A.raster[id].o.bringToFront();
}

function legendControl() {
  const Ctl = L.Control.extend({
    onAdd() { const d = L.DomUtil.create('div', 'mctl'); d.id = 'legend'; L.DomEvent.disableClickPropagation(d); if (window.innerWidth < 1100) d.classList.add('collapsed'); return d; },
  });
  new Ctl({ position: 'bottomleft' }).addTo(A.map);
  updateLegend();
}
function updateLegend() {
  const d = $('#legend');
  if (!d) return;
  let html = `<button class="toggle" type="button" aria-label="Show or hide the map key">${d.classList.contains('collapsed') ? '+' : '–'}</button><h4>Map key</h4><div class="mapkey body">`;
  for (const id of ['elevation', 'slope', 'roughness']) {
    const r = A.raster[id];
    if (!r.on || !r.lyr.legend) continue;
    const lg = r.lyr.legend;
    html += `<div>${esc(r.lyr.title)} (${esc(r.lyr.units)}) ${B(r.lyr.kind)}</div><div class="gradbar" style="background:linear-gradient(90deg,${lg.map((x) => x.color).join(',')})"></div>
      <div class="small muted" style="display:flex;justify-content:space-between"><span>${f1(lg[0].value)}</span><span>${f1(lg.at(-1).value)}${id === 'slope' ? '+' : ''}</span></div>`;
  }
  if (A.raster.nogo.on) html += `<div><span class="sw" style="background:${A.raster.nogo.lyr.color}"></span>No-go: slope &gt; ${A.cur ? A.cur.slopeNogo : 20}° or roughness &gt; 0.2 m ${B('assumption')}</div>
    <div class="small muted">Map layer drawn at the default 20°; the planner uses the slider value.</div>`;
  html += `<div><span class="ln"></span>Walking route of the plan ${B('modeled')}</div>
    <div><span class="sw" style="background:${Ch.C.orange};border-radius:50%"></span>Numbered circle: stop, in visit order</div>
    <div><span class="sw" style="background:transparent;border:2px solid #fff;border-radius:50%"></span>Tightest walk-back point</div>
    <div><span class="ln" style="border-top-color:${SEPCOL}"></span>Too far from shelter (storm rule)</div>
    <div><span class="ln" style="border-top:2px dashed #fff"></span>Perseverance's real drive ${B('real')}</div></div>`;
  d.innerHTML = html;
  const tg = d.querySelector('.toggle');
  tg.onclick = () => { d.classList.toggle('collapsed'); tg.textContent = d.classList.contains('collapsed') ? '+' : '–'; };
}

function readoutControl() {
  const Ctl = L.Control.extend({
    onAdd() { const d = L.DomUtil.create('div', 'mctl readout'); d.id = 'readout'; d.innerHTML = '<h4>Point under the cursor</h4><div class="small muted">Move over the map to read height and slope</div>'; return d; },
  });
  new Ctl({ position: 'topleft' }).addTo(A.map);
}
function updateReadout(ll) {
  const x = ll.lng, y = ll.lat, g = A.grid;
  const d = $('#readout');
  if (x < 0 || y < 0 || x >= 4000 || y >= 4000) { d.innerHTML = '<h4>Point under the cursor</h4><div class="small muted">Outside the 4 km study area</div>'; return; }
  const i = E.xyToIdx(g, x, y);
  const nogo = g.nodata[i] || g.slope[i] > A.cur.slopeNogo || g.rough[i] > pv('terrain.roughness_nogo_m');
  d.innerHTML = `<h4>Point under the cursor (10 m cell)</h4>x ${f0(x)} m, y ${f0(y)} m<br>Elevation ${f1(g.elev[i])} m ${B('real')}<br>
    Slope ${f1(g.slope[i])}°, roughness ${f2(g.rough[i])} m ${B('derived')}<br>${nogo ? '<b style="color:#ff9d5c">Too steep or rough to walk</b>' : 'Walkable'}`;
}

// ---------------------------------------------------------------- markers & routes
function stopIcon(s, num) {
  const c = CAT[s.kind === 'depot' ? 'depot' : s.category]?.col || '#fff';
  return L.divIcon({ className: '', html: `<div class="stopicon" style="background:${c}">${num ?? '·'}</div>`, iconSize: [26, 26], iconAnchor: [13, 13] });
}
function drawStops() {
  const g = A.vec.stops.g;
  g.clearLayers();
  const hab = A.plan.sites[0];
  L.marker(LL([hab.x, hab.y]), { icon: L.divIcon({ className: '', html: '<div class="habicon">H</div>', iconSize: [28, 28], iconAnchor: [14, 14] }) })
    .bindTooltip('Habitat and shelter', { permanent: true, direction: 'right', offset: [16, 0], className: 'maplabel' }).addTo(g);
  A.plan.sites.slice(1).forEach((s) => {
    const pos = A.cur.order.indexOf(s.id);
    const short = s.name.replace(/ \(.*\)/, '').replace('Three Forks sample depot', 'Sample depot (10 tubes)');
    const m = L.marker(LL([s.x, s.y]), { icon: stopIcon(s, pos >= 0 ? pos + 1 : null), riseOnHover: true });
    if (pos >= 0) m.bindTooltip(esc(short), { permanent: true, direction: LABEL_DIR[s.id] || 'right', offset: [LABEL_DIR[s.id] === 'left' ? -15 : 15, 0], className: 'maplabel' });
    else m.bindTooltip(`${esc(s.name)}: ${s.value} pts, ${s.dwell_min} min of work, not in the plan`);
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
  const flush = () => { if (run.length > 1) L.polyline(run.map(LL), { color: SEPCOL, weight: 7, opacity: 0.95 }).bindTooltip('More than the SEP shelter limit from the habitat').addTo(g); run = []; };
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
    if (status) status.innerHTML = `<span style="color:#ff9d5c">${esc(err.message)}</span>`;
    $('#poll').innerHTML = `<div class="verdict nogo"><span class="word">NO-GO</span><span class="why">No safe route: ${esc(err.message)}</span></div>`;
  }
}

// ---------------------------------------------------------------- checklist (same rules as run_plan.py)
function checklist() {
  const ev = A.res.eval, s = ev.safety, t = ev.totals, mc = A.res.mc;
  const target = pv('schedule.robust_p_on_time'), resv = 100 * pv('consumables.o2_reserve_fraction');
  const items = [
    ['EVA fits the time limit (planned)', t.duration_min <= A.limitMin, `${f0(t.duration_min)} of ${A.limitMin} min`],
    [`Home on time in ≥ ${Math.round(target * 100)} % of Monte Carlo runs`, mc.p_success >= target, `${pct(mc.p_success)} of ${f0(mc.runs)} runs`],
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
// GO / NO-GO poll board: one station per rule, same rules and order as checklist()
let lastPoll = null;
function renderGo() {
  const c = checklist(), ev = A.res.eval, s = ev.safety, t = ev.totals, mc = A.res.mc;
  const st = [
    ['EVA length', `${f0(t.duration_min)} min`, `limit ${A.limitMin} min`, 'modeled'],
    ['Home on time', pct(mc.p_success), `of ${f0(mc.runs)} runs`, 'modeled'],
    ['Walk-back O2', `${sgn(s.walkback.min_o2_margin_pct_of_capacity, f1)} %`, 'tank spare', 'modeled'],
    ['Walk-back time', `${sgn(s.walkback.min_time_margin_min, f0)} min`, 'spare', 'modeled'],
    ['Storm shelter', `${f0(s.sep.max_walk_home_min)} min`, `limit ${A.cur.shelterMin} min`, 'assumption'],
    ['Steepest step', `${f1(t.max_slope_deg)}°`, `limit ${A.cur.slopeNogo}°`, 'modeled'],
    ['O2 left at return', `${f0(s.consumables.o2_left_pct)} %`, `reserve ${f0(100 * pv('consumables.o2_reserve_fraction'))} %`, 'modeled'],
    ['Battery left', `${f0(s.consumables.battery_left_pct)} %`, 'at return', 'assumption'],
    ['Sample tubes', A.cur.order.includes('depot') ? 'collected' : 'left behind', `${A.vectors.depot_tubes.points.length} tubes`, 'owner-set'],
  ];
  const fails = c.items.filter((i) => !i[1]).length;
  const now = c.items.map((i) => i[1]);
  const ch = (k) => (lastPoll && lastPoll[k] !== now[k] ? ' changed' : '');
  const goCh = lastPoll && lastPoll.every(Boolean) !== c.go ? ' changed' : '';
  $('#poll').innerHTML = `<div class="verdict ${c.go ? 'go' : 'nogo'}${goCh}" role="button" tabindex="0" title="Open the safety rules">
      <span class="word">${c.go ? 'GO' : 'NO-GO'}</span><span class="why">${c.go ? 'for EVA: all 9 safety rules pass' : `${fails} of 9 safety rules fail`} ${B('modeled')}</span></div>` +
    c.items.map(([rule, ok, detail], k) => `<button class="station ${ok ? 'pass' : 'fail'}${ch(k)}" type="button" title="${esc(rule)}: ${esc(detail)}">
      <span class="glyph" aria-label="${ok ? 'pass' : 'fail'}">${ok ? '✓' : '✕'}</span><span class="name">${st[k][0]}</span>
      <span class="val">${st[k][1]}</span><span class="sub">${st[k][2]} ${B(st[k][3])}</span></button>`).join('');
  lastPoll = now;
  $('#poll').querySelectorAll('.station, .verdict').forEach((b) => b.onclick = () => openTab('safety'));
  renderStrip();
}
function renderStrip() {
  const ev = A.res.eval, mc = A.res.mc, t = ev.totals;
  Ch.strip($('#strip-svg'), ev.rows, A.limitMin, colorOfRow, (r) => A.cur.order.indexOf(r.at) + 1, mc.duration_min.p95);
  $('#strip-sub').innerHTML = `planned return at <b>${hm(t.duration_min)}</b> of the ${hm(A.limitMin)} limit; 95 % of ${f0(mc.runs)} simulated EVAs are back by <b>${hm(mc.duration_min.p95)}</b> ${B('modeled')}`;
}

// ---------------------------------------------------------------- tabs
function setupTabs() {
  document.querySelectorAll('nav.tabs button').forEach((b) => b.onclick = () => openTab(b.dataset.tab));
  $('#btn-hud').onclick = () => A.hud?.open();
}
function openTab(id) {
  document.querySelectorAll('nav.tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === id)));
  document.querySelectorAll('.tabpane').forEach((p) => { p.hidden = p.id !== 'tab-' + id; });
}
A.openTab = openTab;
window.addEventListener('resize', () => { if (A.res) renderStrip(); });

function renderStaticPanels() {
  const P = A.plan, rp = P.plan, mc = P.montecarlo;
  const names = rp.order.map((id) => siteById(id).name.replace(/ \(.*\)/, ''));
  $('#tab-plan').innerHTML = `
    <h2>The plan on the map ${B('modeled')}</h2>
    <p class="lede" id="plan-lede">Planning…</p>
    <table class="cuff" id="cuff" aria-label="EVA step by step"></table>
    <div class="ref">The optimizer's pick (Python, OR-Tools CP-SAT, proven optimal in ${f0(P.robust_plan.solve_ms)} ms): ${names.slice(1, -1).map(esc).join(', ')}.
      ${rp.value} science points, ${f0(rp.totals.duration_min)} of ${A.limitMin} min, home on time in ${pct(mc.p_success)} of ${f0(mc.runs)} runs.
      Its rule: the most science whose chance of getting home on time is at least ${Math.round(pv('schedule.robust_p_on_time') * 100)} % ${B('owner-set')}.</div>

    <div class="section"><h2>Change the plan</h2>
    <p class="small muted">Everything on this page, including a new ${f0(pv('montecarlo.runs'))}-run risk simulation, is recomputed in your browser in about 0.3 s.</p>
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
      <option value="balanced">Balanced (equal weights, recommended)</option><option value="fastest">Fastest (= lowest energy)</option>
      <option value="safest">Safest</option><option value="shortest">Shortest distance (naive)</option><option value="custom">Custom</option></select></label></div>
    <div class="slider"><span>Time</span><input type="range" id="w0" min="0" max="1" step="0.05"><output id="w0o"></output></div>
    <div class="slider"><span>Energy</span><input type="range" id="w1" min="0" max="1" step="0.05"><output id="w1o"></output></div>
    <div class="slider"><span>Hazard</span><input type="range" id="w2" min="0" max="1" step="0.05"><output id="w2o"></output></div>
    <h3>Safety rules ${B('assumption')}</h3>
    <div class="slider"><span>No-go slope</span><input type="range" id="slope" min="10" max="25" step="1"><output id="slopeo"></output></div>
    <div class="slider"><span>SEP shelter limit</span><input type="range" id="shelter" min="20" max="90" step="5"><output id="sheltero"></output></div>
    <p class="small muted">No-go slope default 20° (NASA xEVA ConOps walking slope); roughness limit 0.2 m (assumption). SEP limit default 60 min (assumption).</p>
    <div id="live"></div></div>

    <div class="section"><h2>Other ways to walk the same stops ${B('modeled')}</h2>
    <p class="small muted">Precomputed by the Python planner (same stops, different weights). Click a row to show it on the map.</p>
    <div id="alts"></div>
    <h2>Trade-off: walking time against hazard ${B('modeled')}</h2>
    <div id="pareto"></div>
    <p class="small muted">Each dot is the best route for one weight setting (hazard weight 0 → 0.95). Filled dots are not beaten on both axes.
      Hazard exposure = minutes walked × hazard index (0 below 10° and 0.05 m roughness, 1 at the no-go limit). Energy is not a separate axis: with the constant-power pacing rule, walking energy = 352 W × time.</p></div>`;
  // candidates
  const sel = $('#cand');
  const cands = P.candidates.map((c) => ({ ...c, label: `${c.value} pts: ${c.stops.map((id) => siteById(id).name.replace(/ \(.*\)/, '')).join(', ')}, ${pct(c.p_success, 1)} on time${c.value === P.robust_plan.value ? ' (recommended)' : ''}` }));
  sel.innerHTML = cands.map((c, i) => `<option value="${i}" ${c.value === P.robust_plan.value ? 'selected' : ''}>${esc(c.label)}</option>`).join('');
  sel.onchange = () => { const c = cands[+sel.value]; A.cur.order = c.order.slice(1, -1).map((k) => P.sites[k].id).concat(A.cur.waypoints.map((w) => w.id)); renderEditor(); drawStops(); scheduleReplan(); };
  document.querySelectorAll('[data-mode]').forEach((b) => b.onclick = () => setMode(b.dataset.mode));
  $('#clear-keep').onclick = () => { A.cur.keepouts = []; drawKeepouts(); scheduleReplan(true); };
  $('#reset').onclick = () => { A.cur = defaultState(); sel.value = String(cands.findIndex((c) => c.value === P.robust_plan.value)); drawKeepouts(); syncControls(); renderEditor(); drawStops(); scheduleReplan(true); };
  $('#profile').onchange = () => { const v = $('#profile').value; A.cur.profile = v; if (v !== 'custom') A.cur.w = pv('route_options.' + v).slice(0, 3); syncControls(); scheduleReplan(); };
  for (const k of [0, 1, 2]) $('#w' + k).oninput = () => {
    A.cur.w[k] = +$('#w' + k).value; A.cur.profile = 'custom';
    if (A.cur.w[0] + A.cur.w[1] <= 0) { A.cur.w[0] = 0.05; }
    syncControls(); scheduleReplan();
  };
  $('#slope').oninput = () => { A.cur.slopeNogo = +$('#slope').value; syncControls(); updateLegend(); scheduleReplan(true); };
  $('#shelter').oninput = () => { A.cur.shelterMin = +$('#shelter').value; syncControls(); scheduleReplan(); };
  syncControls();
  renderEditor();
  drawStops();
  // alternatives table
  const sel2 = new Set();
  const altHTML = () => `<table><tr><th>Option</th><th>km</th><th>min</th><th>kcal walk</th><th>max slope</th><th>caution min</th><th>min reserve</th><th>P(on time)</th></tr>
    ${P.alternatives.map((a) => `<tr class="click ${sel2.has(a.id) ? 'sel' : ''}" data-alt="${a.id}"><td><span class="sw" style="background:${ROUTE_COL[a.id]}"></span>${esc(a.name)}</td>
      <td>${f2(a.dist_m / 1000)}</td><td>${f1(a.duration_min)}</td><td>${f0(a.walk_energy_kcal)}</td><td>${f1(a.max_slope_deg)}°</td>
      <td>${f1(a.caution_min)}</td><td>${f0(a.min_walkback_margin_min)} min / ${f0(a.min_o2_margin_pct)} % O2</td><td>${pct(a.p_on_time)}</td></tr>`).join('')}</table>
    <p class="small muted">min = whole EVA (walking + ${f0(P.plan.totals.work_min)} min of work). caution min = minutes on cells with any hazard (slope over 10° or roughness over 0.05 m).
      min reserve = tightest walk-back margin along the route, in time and in % of the O2 tank above the reserve. Lowest-energy gives the same route as Fastest (DECISIONS T32).</p>`;
  const drawAlts = () => {
    $('#alts').innerHTML = altHTML();
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
      const extra = s ? `${s.value} pts, ${s.dwell_min} min` : 'pass through';
      return `<li><span class="n" style="background:${c}">${i + 1}</span><span class="nm">${esc(nameOf(id))} <span class="small muted">${extra}</span></span>
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
  const stops = A.cur.order.filter((id) => siteById(id)?.kind === 'stop').length;
  const depot = A.cur.order.includes('depot');
  $('#plan-lede').innerHTML = `<b>${value} science points</b> from ${stops} stop${stops === 1 ? '' : 's'}${depot ? ' plus the sample-tube pickup' : ', <b style="color:#ff9d5c">without the sample-tube pickup</b>'}.
    ${f2(t.dist_m / 1000)} km on foot; back at the habitat after <b>${hm(t.duration_min)}</b> of the ${hm(A.limitMin)} limit.
    <b>${pct(mc.p_success)}</b> of ${f0(mc.runs)} simulated EVAs get home on time ${B('modeled')}.`;
  const num = (id) => A.cur.order.indexOf(id) + 1;
  const last = ev.rows.at(-1);
  $('#cuff').innerHTML = `<tr><th>Time</th><th>What happens</th><th style="text-align:right">Detail</th></tr>` + ev.rows.map((r) => r.kind === 'walk'
    ? `<tr class="walk"><td class="t">${hmm(r.t0_min)}</td><td class="ev">Walk to ${esc(nameOf(r.to).replace(/ \(.*\)/, ''))}</td><td class="d">${f2(r.dist_m / 1000)} km, ${f0(r.t1_min - r.t0_min)} min</td></tr>`
    : `<tr class="work"><td class="t">${hmm(r.t0_min)}</td><td class="ev"><span class="n stopn" style="background:${colorOfRow(r)}">${num(r.at)}</span>${esc(r.name.replace(/ \(.*\)/, ''))}</td><td class="d">${f0(r.t1_min - r.t0_min)} min work</td></tr>`).join('') +
    `<tr class="home"><td class="t">${hmm(last.t1_min)}</td><td class="ev">Back at the habitat</td><td class="d">O2 left ${f0(ev.safety.consumables.o2_left_pct)} %</td></tr>`;
  $('#live').innerHTML = `<h3>Your plan in numbers ${B('modeled')}</h3>${snapped}
    <dl class="facts">
      <dt>Science value</dt><dd>${value} pts ${B('owner-set')}</dd>
      <dt>Duration</dt><dd style="color:${t.duration_min <= A.limitMin ? 'inherit' : '#ff9d5c'}">${f0(t.duration_min)} of ${A.limitMin} min (${f0(t.walk_min)} min walking, ${f0(t.work_min)} min work)</dd>
      <dt>Distance</dt><dd>${f2(t.dist_m / 1000)} km, ${f0(t.gain_m)} m of climbing</dd>
      <dt>Walking energy</dt><dd>${f0(t.walk_energy_kcal)} kcal per person</dd>
      <dt>Steepest 10 m cell</dt><dd>${f1(t.max_slope_deg)}°, ${f1(t.caution_min)} min on caution ground</dd>
      <dt>Home on time</dt><dd>${pct(mc.p_success)} of ${f0(mc.runs)} runs</dd>
    </dl>
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
    <p class="small muted">Each run draws a walking-speed factor (σ ${pv('montecarlo.speed_sigma')}), a metabolic factor (σ ${pv('montecarlo.metabolic_sigma')}) and a work-time factor per stop (σ ${pv('montecarlo.dwell_sigma')}), all log-normal ${B('assumption')}.
      Python reference for the recommended plan: ${pct(P.montecarlo.p_success, 2)} of ${f0(P.montecarlo.runs)} runs.</p>
    <h2>What drives the risk? (tornado, recommended plan) ${B('modeled')}</h2>
    <div id="tornado"></div>
    <div class="legendrow"><span><span class="sw" style="background:${Ch.C.sky}"></span>shorter EVA</span><span><span class="sw" style="background:${Ch.C.orange}"></span>longer EVA</span></div>
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
    <p class="small muted">All six sites are real Perseverance sample or study sites. Positions, quotes and samples come from the NASA PDS Mars 2020 Initial Reports. Science value = Son's rubric ${B('owner-set')}; the category of each site is a science judgement.</p>` +
    stops.map((s) => {
      const pos = A.cur.order.indexOf(s.id);
      const np = nearestPhoto(s);
      const c = CAT[s.kind === 'depot' ? 'depot' : s.category];
      const tubes = s.kind === 'depot' ? `<p class="small">${A.vectors.depot_tubes.points.length} tubes: ${A.vectors.depot_tubes.points.map((t) => esc(t.name)).join(', ')} (dropped sols ${A.vectors.depot_tubes.points[0].drop_sol}-${A.vectors.depot_tubes.points.at(-1).drop_sol}). ${esc(A.vectors.depot_tubes.note)}</p>` : '';
      return `<div class="card" id="card-${s.id}">
        <h3><span class="sw" style="background:${c.col}"></span>${esc(s.name)} ${pos >= 0 ? `<span class="badge modeled">stop ${pos + 1} in your plan</span>` : '<span class="badge derived">not in plan</span>'}</h3>
        <div class="small">${esc(c.label)}, <b>${s.value} pts</b> ${B('owner-set')}, work ${s.dwell_min} min ${B('assumption')}, ${s.work_w} W work rate, walk home ${f0(s.walk_home_min)} min ${B('modeled')}${s.sep_ok ? '' : ', <b style="color:#ff6b5b">outside the SEP shelter limit</b>'}</div>
        ${s.task ? `<p><b>Task:</b> ${esc(s.task)}</p>` : ''}
        ${s.why_category ? `<p><b>Science goal:</b> ${esc(s.why_category)}</p>` : ''}
        ${s.quote ? `<blockquote>"${esc(s.quote)}"</blockquote><div class="credit">${esc(s.source)}${s.samples ? ', samples: ' + esc(s.samples) : ''}</div>` : `<div class="credit">${esc(s.source || '')}</div>`}
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
    <button id="show-tight" type="button">Show the tightest point on the map</button>
    <h2>Solar storm (SEP) shelter rule ${B('assumption')}</h2>
    <p class="small">During a solar particle event alert the crew must reach the habitat within <b>${A.cur.shelterMin} min</b> (slider on the Plan tab). Farthest point of your route: <b>${f0(s.sep.max_walk_home_min)} min</b> from shelter.
      ${s.sep.violating_points ? `<b style="color:#ff6b5b">${s.sep.violating_points} route points break the rule (red on the map).</b>` : 'No route point breaks the rule.'}</p>
    <button id="sep-replay" class="primary" type="button">Replay a solar storm alert in the HUD</button>
    <p class="small muted">The replay plays the EVA and triggers the alert at the point farthest from shelter, then re-plans the way home live.</p>
    <div class="note small">Real alert data ${B('proxy')}: ${donkiN} solar energetic particle events in NASA CCMC DONKI between 2024-05-01 and 2024-06-29 (cached). These are near-Earth detections, not measured at Mars. First: ${esc(A.donki.events[0].eventTime)}, ${esc(A.donki.events[0].instruments.map((i) => i.displayName).join('; '))}.</div>
    <h2>Radiation dose estimate ${B('proxy')}</h2>
    <p><b>${f0(s.dose.background_ugy)} µGy</b> absorbed dose for this ${f0(ev.totals.duration_min)} min EVA, from the Curiosity RAD background of ${rate} µGy/day measured at Gale crater (NASA PIA17600), not Jezero.
      For scale: NASA says astronauts on Mars during the 20 May 2024 storm would have received <b>${may.toLocaleString('en-US')} µGy</b>, about ${f0(may / rate)} days of background, which is why the shelter rule exists. Dose equivalent (mSv) is not estimated.</p>
    <h2>Consumables at return ${B('modeled')}</h2>
    <p>O2 left ${f0(s.consumables.o2_left_pct)} % (${f2(s.consumables.o2_used_kg)} kg used of ${pv('consumables.o2_capacity_kg')} kg), battery left ${f0(s.consumables.battery_left_pct)} %.</p>
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
    <h3>Planned route vs the real Perseverance drive ${B('real')}</h3>
    <p class="small muted">A rover is not a human, but the drivers avoided the same hazards our model sees. Share of the planned path within 25 m of the rover's real path:</p>
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
    L.polyline([LL(d.start_xy), LL(d.end_xy)], { color: '#a9b6c3', weight: 2, dashArray: '5 5' }).bindTooltip('Straight line').addTo(g);
    A.map.fitBounds(L.latLngBounds(d.rover_xy.flat().map(LL)).pad(0.2));
  });
}
A.renderChecksLive = () => {
  const el = $('#chk-live');
  if (el && A.initInfo) el.textContent = `In this browser: model built in ${f0(A.initInfo.build_ms)} ms (${f0(A.initInfo.edges)} edges).`;
};

main().then(() => A.renderChecksLive()).catch((e) => { console.error(e); showError('Could not start: ' + e.message); });
