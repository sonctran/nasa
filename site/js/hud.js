// Marswalk Ops - HUD mode: a simplified helmet-visor view that plays the plan back and re-plans live
// when an event happens (solar storm alert, slow crew, suit O2 fault). Owner upgrade S4 "Live re-plan".
import * as E from './engine.js';

const $ = (s) => document.querySelector(s);

export function initHUD(A) {
  const pv = (k) => E.pv(A.params, k);
  const cap = pv('consumables.o2_capacity_kg');
  const reserve = cap * pv('consumables.o2_reserve_fraction');
  const draw = pv('consumables.battery_draw_w'), bat = pv('consumables.battery_capacity_wh');
  const limitS = pv('mission.eva_time_limit') * 3600;
  const o2PerJ = pv('consumables.o2_kg_per_mj') / 1e6;
  const slopeCaution = pv('hazard.slope_caution_deg');
  const img = new Image();
  img.src = 'assets/layers/ortho.jpg';
  const H = { open: false, playing: false, T: 0, speed: 180, last: null, track: null, events: [], f: { speed: 1, work: 1, o2: 1 } };

  // ------------------------------------------------------------ track = keyframes {t, xy, o2, back_s, idx}
  function trackFromPlan() {
    const ev = A.res.eval;
    const kf = ev.pts.map((p) => ({ t: p.t, xy: p.xy, o2: p.o2, back_s: p.back_t, idx: p.idx }));
    const rows = ev.rows.map((r) => ({ ...r, t0: r.t0_min * 60, t1: r.t1_min * 60 }));
    return { kf, rows, end: kf.at(-1).t, color: '#3fbf8f', replanned: null };
  }
  function stateAt(tr, T) {
    const kf = tr.kf;
    if (T <= kf[0].t) return { ...kf[0], k: 0 };
    if (T >= kf.at(-1).t) return { ...kf.at(-1), k: kf.length - 1 };
    let lo = 0, hi = kf.length - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (kf[m].t <= T) lo = m; else hi = m; }
    const a = kf[lo], b = kf[hi], f = b.t > a.t ? (T - a.t) / (b.t - a.t) : 0;
    return { t: T, xy: [a.xy[0] + f * (b.xy[0] - a.xy[0]), a.xy[1] + f * (b.xy[1] - a.xy[1])], o2: a.o2 + f * (b.o2 - a.o2),
             back_s: a.back_s + f * (b.back_s - a.back_s), idx: f < 0.5 ? a.idx : b.idx, k: lo };
  }
  const rowAt = (tr, T) => tr.rows.find((r) => T >= r.t0 && T < r.t1) || tr.rows.at(-1);

  // Build the rest of the track from a re-plan result, starting at time T0 with O2 used O0.
  function extendTrack(tr, T0, st, rp) {
    const kf = tr.kf.filter((p) => p.t < T0);
    kf.push({ t: T0, xy: st.xy, o2: st.o2, back_s: st.back_s, idx: st.idx });
    const rows = tr.rows.filter((r) => r.t0 < T0).map((r) => ({ ...r, t1: Math.min(r.t1, T0), t1_min: Math.min(r.t1, T0) / 60 }));
    let t = T0, o = st.o2;
    const sites = A.res.sites;
    rp.legs.forEach((leg, li) => {
      const t0 = t;
      leg.xy.forEach((xy, q) => {
        if (q === 0) return;
        kf.push({ t: t + leg.cum_time_s[q] / H.f.speed, xy, o2: o + leg.cum_energy_j[q] * o2PerJ * H.f.o2, back_s: leg.back_s[q] / H.f.speed, idx: leg.path[q] });
      });
      t += leg.time_s / H.f.speed; o += leg.energy_j * o2PerJ * H.f.o2;
      const to = li < rp.stops.length ? sites[rp.stops[li]] : sites[0];
      rows.push({ kind: 'walk', to: to.id, t0, t1: t, t0_min: t0 / 60, t1_min: t / 60 });
      if (li < rp.stops.length) {
        const dw = to.dwell_min * 60 * H.f.work;
        const last = kf.at(-1);
        rows.push({ kind: 'work', at: to.id, name: to.name, task: to.task || 'Science stop', t0: t, t1: t + dw });
        t += dw; o += dw * to.work_w * o2PerJ * H.f.o2;
        kf.push({ ...last, t, o2: o });
      }
    });
    return { kf, rows, end: t, color: '#56b4e9', replanned: rp };
  }

  // ------------------------------------------------------------ events -> live re-plan in the worker
  async function event(kind) {
    if (!H.track) return;
    H.playing = false; syncPlay();
    let T = H.T;
    const st0 = stateAt(H.track, T);
    const row = rowAt(H.track, T);
    const sites = A.res.sites;
    // which stops are still ahead?
    const doneIds = new Set(H.track.rows.filter((r) => r.kind === 'work' && r.t1 <= T).map((r) => r.at));
    let finishing = null;
    if (kind !== 'sep' && row.kind === 'work' && T < row.t1) { finishing = row; T = row.t1; doneIds.add(row.at); }
    const st = finishing ? stateAt(H.track, T) : st0;
    const planned = H.track.rows.filter((r) => r.kind === 'work').map((r) => r.at);
    const remaining = planned.filter((id) => !doneIds.has(id)).map((id) => sites.findIndex((s) => s.id === id));
    if (kind === 'slow') { H.f.speed *= pv('replan.slow_crew_speed_factor'); H.f.work *= pv('replan.slow_crew_work_factor'); }
    if (kind === 'o2') H.f.o2 *= pv('replan.suit_fault_o2_factor');
    const here = st.idx;
    const t0 = performance.now();
    const res = await A.call('replan', {
      mode: kind === 'sep' ? 'sep' : 'event', w: pv('replan.replan_weights'),
      ctx: { here, elapsedS: T, o2UsedKg: st.o2, remaining, sites, homeIdx: sites[0].idx,
             speedF: H.f.speed, workF: H.f.work, o2F: H.f.o2 } });
    const wall = performance.now() - t0;
    if (kind === 'sep') res.stops = [];
    H.track = extendTrack(H.track, T, st, res);
    H.T = T;
    const name = (k) => sites[k].name.replace(/ \(.*\)/, '');
    const dropped = remaining.filter((k) => !res.stops.includes(k)).map(name);
    let msg;
    if (kind === 'sep') {
      const lim = A.cur.shelterMin;
      const walk = res.legs[0].time_s / 60 / H.f.speed;
      msg = `<b>SOLAR PARTICLE EVENT ALERT</b> (replay; alert type from NASA DONKI, proxy) at T+${fmtT(T)}.<br>
        Re-planned in <b>${wall.toFixed(0)} ms</b>: stop work, walk straight to the habitat by the fastest safe route.
        Time to shelter <b>${walk.toFixed(0)} min</b> (limit ${lim} min) → <b style="color:${walk <= lim ? '#3fbf8f' : '#ff6b5b'}">${walk <= lim ? 'rule met' : 'RULE BROKEN'}</b>.
        ${dropped.length ? 'Left for a later EVA: ' + dropped.join(', ') + '.' : ''}`;
      showAlert('danger', 'SOLAR STORM ALERT: GO TO SHELTER');
    } else {
      const what = kind === 'slow' ? `Slow crew: pace ×${H.f.speed.toFixed(2)}, tasks ×${H.f.work.toFixed(2)}` : `Suit O2 fault: O2 use ×${H.f.o2.toFixed(1)}`;
      msg = `<b>${what}</b> (assumption) at T+${fmtT(T)}${finishing ? ', after finishing ' + finishing.name : ''}.<br>
        Re-planned in <b>${wall.toFixed(0)} ms</b> (${res.sequences_tried} stop sequences checked exactly).
        ${res.infeasible ? '<b style="color:#ff6b5b">No plan fits the limits: go home now.</b>' : `New plan: ${res.stops.length ? res.stops.map(name).join(' → ') + ' → ' : ''}Habitat.`}
        ${dropped.length ? '<br>Dropped: ' + dropped.join(', ') + '.' : ''} ${res.depot_kept ? '' : '<b style="color:#ff6b5b">Depot tubes left behind.</b>'}
        <br>Home at T+${fmtT(res.end_min * 60)} (limit ${fmtT(limitS)}), O2 left ${res.o2_left_pct.toFixed(0)} % (reserve ${Math.round(100 * reserve / cap)} %).`;
      showAlert('info', 'RE-PLANNED');
    }
    H.events.push({ kind, at: T, ms: wall });
    const box = $('#hud-replan'); box.innerHTML = msg; box.hidden = false;
    A.lastReplan = { kind, ms: wall, worker_ms: res.ms, stops: res.stops };
    draw_();
  }
  function showAlert(cls, text) { const a = $('#hud-alert'); a.className = 'alert ' + cls; a.textContent = text; a.hidden = false; }

  // ------------------------------------------------------------ drawing
  const fmtT = (s) => { const m = Math.max(0, Math.round(s / 60)); return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}`; };
  function draw_() {
    const cv = $('#hud-canvas'), stage = $('#hud-stage');
    const w = stage.clientWidth, h = stage.clientHeight, dpr = window.devicePixelRatio || 1;
    if (cv.width !== Math.round(w * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
    const ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = '#000'; ctx.fillRect(0, 0, w, h);
    const tr = H.track, st = stateAt(tr, H.T);
    const R = 260;                                      // metres from centre to the shorter edge
    const sc = Math.min(w, h) / 2 / R;
    const P = (xy) => [w / 2 + (xy[0] - st.xy[0]) * sc, h / 2 - (xy[1] - st.xy[1]) * sc];
    if (img.complete && img.naturalWidth) {
      const mpp = 4000 / img.naturalWidth;            // metres per image pixel
      const hw = w / 2 / sc, hh = h / 2 / sc;
      ctx.globalAlpha = 0.55;
      ctx.drawImage(img, (st.xy[0] - hw) / mpp, (4000 - st.xy[1] - hh) / mpp, 2 * hw / mpp, 2 * hh / mpp, 0, 0, w, h);
      ctx.globalAlpha = 1;
    }
    ctx.fillStyle = 'rgba(0,40,20,0.35)'; ctx.fillRect(0, 0, w, h);
    // range rings
    ctx.strokeStyle = 'rgba(120,255,190,0.35)'; ctx.lineWidth = 1;
    for (const r of [100, 200]) { ctx.beginPath(); ctx.arc(w / 2, h / 2, r * sc, 0, 2 * Math.PI); ctx.stroke();
      ctx.fillStyle = 'rgba(160,255,200,0.7)'; ctx.font = '12px system-ui'; ctx.fillText(r + ' m', w / 2 + r * sc + 4, h / 2 - 4); }
    ctx.fillStyle = 'rgba(160,255,200,0.9)'; ctx.font = 'bold 14px system-ui'; ctx.fillText('N', w / 2 - 5, 18);
    // route: walked (dim) and ahead (bright)
    const kf = tr.kf;
    const line = (pts, col, wd) => { if (pts.length < 2) return; ctx.strokeStyle = col; ctx.lineWidth = wd; ctx.lineJoin = 'round'; ctx.beginPath();
      pts.forEach((p, i) => { const [x, y] = P(p.xy); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke(); };
    line(kf.filter((p) => p.t <= H.T).concat([st]), 'rgba(200,200,200,0.5)', 3);
    line([st].concat(kf.filter((p) => p.t > H.T)), tr.replanned ? '#56b4e9' : '#3fbf8f', 5);
    // sites
    for (const s of A.res.sites) {
      const [x, y] = P([s.x, s.y]);
      if (x < -20 || y < -20 || x > w + 20 || y > h + 20) continue;
      ctx.fillStyle = s.kind === 'habitat' ? '#56b4e9' : s.kind === 'depot' ? '#009e73' : '#e69f00';
      ctx.beginPath(); ctx.arc(x, y, 8, 0, 2 * Math.PI); ctx.fill();
      ctx.fillStyle = '#eafff4'; ctx.font = 'bold 13px system-ui'; ctx.fillText(s.name.replace(/ \(.*\)/, ''), x + 11, y + 4);
    }
    // crew
    ctx.fillStyle = '#f0e442'; ctx.strokeStyle = '#000'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(w / 2, h / 2, 9, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
    // readouts
    const row = rowAt(tr, H.T);
    const nextRow = tr.rows.find((r) => r.kind === 'work' && r.t1 > H.T);
    const target = nextRow ? A.res.sites.find((s) => s.id === nextRow.at) : A.res.sites[0];
    const tgtXY = row.kind === 'work' && H.T < row.t1 ? st.xy : [target.x, target.y];
    const dx = tgtXY[0] - st.xy[0], dy = tgtXY[1] - st.xy[1];
    const dist = Math.hypot(dx, dy);
    const brg = (Math.atan2(dx, dy) * 180 / Math.PI + 360) % 360;
    $('#hud-next').textContent = (row.kind === 'work' && H.T < row.t1) ? 'At ' + row.name.replace(/ \(.*\)/, '') : (nextRow ? target.name.replace(/ \(.*\)/, '') : 'Habitat');
    $('#hud-dist').textContent = dist < 15 ? 'here' : `${Math.round(dist)} m`;
    $('#hud-brg').textContent = dist < 15 ? '' : `bearing ${String(Math.round(brg)).padStart(3, '0')}° (straight line)`;
    $('#hud-left').textContent = fmtT(limitS - H.T);
    $('#hud-home').textContent = `${Math.round(st.back_s / 60)} min (storm-shelter limit ${A.cur.shelterMin} min)`;
    const o2pct = 100 * (cap - reserve - st.o2) / cap;
    const el = $('#hud-o2'); el.textContent = `${Math.max(0, o2pct).toFixed(0)} %`; el.style.color = o2pct < 10 ? '#ff6b5b' : '';
    $('#hud-bat').textContent = `${Math.max(0, 100 * (1 - draw * H.T / 3600 / bat)).toFixed(0)} %`;
    const g = A.grid, i = E.xyToIdx(g, st.xy[0], st.xy[1]);
    const tEl = $('#hud-terrain');
    tEl.textContent = `slope ${g.slope[i].toFixed(0)}°, height ${g.elev[i].toFixed(0)} m`;
    tEl.style.color = g.slope[i] > slopeCaution ? '#f0e442' : '';
    $('#hud-task').textContent = row.kind === 'work' && H.T < row.t1 ? (row.task || '').slice(0, 42) : (H.T >= tr.end ? 'EVA complete' : 'walking');
    $('#hud-clock').textContent = `T+${fmtT(H.T)} of ${fmtT(limitS)}`;
    const a = $('#hud-alert');
    if (a.hidden || a.dataset.auto) {
      if (g.slope[i] > slopeCaution && row.kind === 'walk') { a.className = 'alert caution'; a.textContent = `CAUTION: SLOPE ${g.slope[i].toFixed(0)}°`; a.hidden = false; a.dataset.auto = '1'; }
      else if (a.dataset.auto) { a.hidden = true; delete a.dataset.auto; }
    }
    $('#hud-scrub').value = String(Math.round(1000 * H.T / Math.max(tr.end, 1)));
  }

  function frame(ts) {
    if (!H.open) return;
    if (H.playing) {
      if (H.last != null) H.T = Math.min(H.track.end, H.T + (ts - H.last) / 1000 * H.speed);
      if (H.sepAt != null && H.T >= H.sepAt) { H.sepAt = null; H.last = ts; event('sep'); }
      if (H.T >= H.track.end) { H.playing = false; syncPlay(); }
    }
    H.last = ts;
    draw_();
    requestAnimationFrame(frame);
  }
  function syncPlay() { $('#hud-play').textContent = H.playing ? 'Pause' : (H.track && H.T >= H.track.end ? 'Replay' : 'Play'); }
  function reset() {
    H.track = trackFromPlan(); H.T = 0; H.f = { speed: 1, work: 1, o2: 1 }; H.events = [];
    $('#hud-replan').hidden = true; $('#hud-alert').hidden = true; H.sepAt = null;
  }

  $('#hud-play').onclick = () => {
    if (H.T >= H.track.end) { reset(); }
    H.playing = !H.playing; H.last = null; syncPlay();
  };
  $('#hud-speed').onchange = () => { H.speed = +$('#hud-speed').value; };
  $('#hud-scrub').oninput = () => { H.T = +$('#hud-scrub').value / 1000 * H.track.end; draw_(); };
  $('#hud-exit').onclick = () => close();
  $('#hud-reset').onclick = () => { reset(); syncPlay(); draw_(); };
  $('#hud-ev-sep').onclick = () => event('sep');
  $('#hud-ev-slow').onclick = () => event('slow');
  $('#hud-ev-o2').onclick = () => event('o2');
  document.addEventListener('keydown', (e) => { if (H.open && e.key === 'Escape') close(); if (H.open && e.key === ' ') { e.preventDefault(); $('#hud-play').click(); } });
  window.addEventListener('resize', () => H.open && draw_());

  function open(opts = {}) {
    if (!A.res) return;
    $('#hud').hidden = false; H.open = true;
    reset();
    if (opts.sepReplay) {
      // trigger the alert at the route point farthest from shelter
      const far = H.track.kf.reduce((a, b) => (b.back_s > a.back_s ? b : a));
      H.sepAt = far.t;
      H.T = Math.max(0, far.t - 15 * 60);
      H.playing = true;
    }
    if (opts.at != null) H.T = opts.at;
    H.last = null; syncPlay();
    requestAnimationFrame(frame);
  }
  function close() { H.open = false; H.playing = false; $('#hud').hidden = true; }
  return { open, close, event, state: H, draw: draw_ };
}
