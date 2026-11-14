# PROGRESS

## Current status: Phase 4 (validate, polish, deploy): DONE. Next: Phase 5 (submission package), when Son says so.

**Live app:** https://sonctran.github.io/nasa/ · **Repo:** https://github.com/sonctran/nasa (public)

### Done in Phase 4 (Sat 2026-11-14, ~1 h)
- **Deploy:** `.github/workflows/pages.yml` publishes `site/` to GitHub Pages on every push to `claude/serene-sagan-hlltkr` (the repo's default branch). Son switched Pages on (Settings → Pages → Source: GitHub Actions); the workflow could not do it itself ("Resource not accessible by integration").
- **Independent review:** a subagent with no build context clicked through the local and live site at 4 screen sizes, checked numbers against plan.json/params/docs, labels, insignia, credits, AI disclosure, links and the first 10 seconds. Result: **0 blockers, 9 high, 17 low.** All 9 high and 13 of the 17 low are fixed (table below).
- `scripts/screenshot.py` now takes `--url` and `--out`, so the same full click-through runs against the live site.
- Network: added `sonctran.github.io` to the "nasa" cloud environment (approved by Son) so the live site can be tested from here.

### Phase 4 exit checks (evidence)
| Exit check | Result | Evidence |
|---|---|---|
| Live URL works, fresh browser profile, no login | **PASS** | `scripts/screenshot.py --url https://sonctran.github.io/nasa/` in a new Chromium context: all 15 panels clicked, **0 console errors, 0 page errors, 0 failed requests, 0 HTTP errors**. Before the fixes: route 0.85 s, ready 1.66 s. **After the final deploy (commit d4bf8d7): route on the map 0.75 s, plan ready 1.55 s, add-a-stop re-plan 231 ms, 0 errors.** |
| Repo URL works, public | **PASS** | GitHub search API: `sonctran/nasa`, `visibility: public`. |
| Reviewer findings fixed or listed | **PASS** | Table below. |
| Tests | **PASS** | pytest **166 passed**. Local click-through after fixes: 0 errors, route 0.17 s, ready 0.98 s, tablet overflow 0 px. Site 11 MB. |

### Reviewer findings
| # | Finding | Status |
|---|---|---|
| H1 | Three "on time" numbers for one plan (98.2 / 99.1 / 98.3 %) | **Fixed.** Route table now uses the same measure as the headline (home on time AND O2 above reserve; new `p_success` in plan.json, Balanced = 98.2 %). Browser values say "browser run" and show the Python reference. |
| H2 | 30-pt candidate showed "95.0 %" but fails the 95 % bar | **Fixed.** Shows 94.96 % "(under the 95 % bar)". |
| H3 | METHODS said 12 Pareto routes; data has 14 | **Fixed** (14). |
| H4 | Docs promised a roughness slider that does not exist | **Fixed** the text (params note, DATA_SOURCES, methods.html). |
| H5 | DONKI "27 events, detections" overstated | **Fixed.** "27 records on 6 days: 17 detections, 10 model forecasts"; example is now a real detection. |
| H6 | Lunar/Apollo values without "proxy" | **Fixed.** Proxy badge on the 20° slope limit, stop-card work rates and the walking model. |
| H7 | No on-screen THEMIS credit; HUD had none | **Fixed.** THEMIS credit appears while a THEMIS layer is on; HUD footer credits HiRISE/USGS. |
| H8 | README stale, no live link, 3.0 km | **Fixed.** |
| H9 | First 10 seconds: no "what to try", markers unexplained, Layers panel covers the map, jargon | **Fixed:** "Try: press HUD mode then Play…" line, map legend for habitat/stop colours/numbers, Layers panel starts collapsed, EVA/SEP/HUD spelled out. |
| L10-L22 | Habitat badged "real"; rover table badge; overstated rover sentence; tornado 36→35 min; HUD "60" without unit; "DECISIONS T29/T32" and "Son's rubric" in the UI; stop-card source line; far rover photos; Methods page `A\*` and Tobler `|`; DONKI URL missing `api_key`; HiRISE citation → "Fergason et al."; O2 tank arithmetic basis; no THEMIS legend | **Fixed.** |
| L23 | HUD events pressed at T+0:00 show "EVA complete" | Open (harmless). |
| L24 | Phone width (390 px) overflows by 16 px | Open (phones are not a SPEC target). |
| L25 | `submission/` empty; "Use of SI" text not written | Phase 5. |
| L26 | Header says "Plans a **safe** … Marswalk", a strong word for a modeled study | Open: Son's call (it changes what judges read first). |

### Phase 4 known issues (for Son)
1. **Firefox is still untested.** This container only has Chromium. Please open the live link in Firefox once (needs Firefox 114+); Chrome and Edge are covered.
2. **Windows still untested here.** The live site does not care about Windows; the Python pipeline still needs one `pytest` run on your PC.
3. In the map legend, "Transported boulders" and "Too far from shelter" share the same reddish-purple colour (one is a dot, one is a route line). Cosmetic.
4. The open review items L23, L24, L26 above.

### Phase 3 record (web app: COMPLETE; Son's click-through accepted when he started Phase 4)

### Done in Phase 3 (Fri 2026-11-13, ~2 h 30 min)
**Run it (Windows PowerShell, from the project folder):**
```powershell
.\.venv\Scripts\python.exe -m http.server 8000 --directory site
```
then open http://localhost:8000 in Chrome or Edge. (Opening `index.html` by double-click will NOT work: browsers block data loading from `file://`.)

Files: `site/index.html`, `site/methods.html`, `site/css/app.css`, `site/js/engine.js` (browser port of the planner), `site/js/worker.js` (Web Worker), `site/js/app.js` (map + panels), `site/js/charts.js` (SVG charts), `site/js/hud.js` (HUD + live re-plan), `site/vendor/leaflet/` (Leaflet 1.9.4, vendored). New Python: `planner/export_site.py` (params/roles/docs into `site/`, also called by `run_plan`). Tests: `tests/test_js_engine.py` + `tests/js/parity.mjs`; params-sync test in `tests/test_web_assets.py`. Script: `scripts/screenshot.py`. New labelled assumptions: `replan.*` in `config/params.yaml`. DECISIONS T40-T47. METHODS §11 (web app) added; DATA_SOURCES Phase 3 table (Leaflet credit).

What is in the app (SPEC §7):
- **Map:** HiRISE base image, hillshade, elevation, slope, roughness, no-go, THEMIS day/night, 25 cm depot close-up (each with toggle + opacity + real/derived/assumption/proxy badge); rover traverse, waypoints, depot tubes, rover photos, stops; legend; metre scale bar; cursor readout (x, y, elevation, slope, roughness, walkable).
- **Plan tab:** recommended plan; live editor (candidate plans 20/26/30/36 pts, add/remove/reorder stops, click-to-add + drag waypoints, keep-out boxes, weight sliders, no-go slope and SEP sliders); route-option table; Pareto chart.
- **Schedule tab:** EV1/EV2 Gantt with roles, O2 + battery burn-down, live Monte Carlo histogram, tornado (Python, recommended plan).
- **Stops tab:** 6 cards (science goal, value, work time, PDS quote + source, what to look for, nearest real rover photo with credit and distance) + depot card with the 10 tubes.
- **Safety tab:** live 9-item Go/No-Go, walk-back margin (+ show on map), SEP rule + replay button, DONKI events (proxy), dose (proxy), consumables.
- **Checks tab:** A* = Dijkstra, browser = Python, slope check, Apollo 14 check, rover-drive comparison drawn on the map.
- **HUD mode:** full-screen visor view: next target, distance, bearing, EVA time left, walk-home time, O2 above reserve, battery, terrain/slope caution, task; play/pause/speed/scrub; events **Solar storm alert, Slow crew, Suit O2 fault** → live re-plan.
- **Methods page:** problem, labels, AI use, limitations, future work, and METHODS / ASSUMPTIONS / DATA_SOURCES rendered from the repo files.

### Phase 3 exit checks (evidence)
| Exit check | Result | Evidence |
|---|---|---|
| A* ported to a Web Worker, matches Python on a fixture | **PASS** | `pytest tests/test_js_engine.py`: 8 random fixture grids, 96 routes: same cost (≤ 1e-12 relative) and same path cells; real grid: 5/5 plan legs equal Python A* and `plan.json` Dijkstra; plan totals equal `plan.json` to 1e-9; walk-back 92.94 min both; SEP max 39.23 min both |
| Screenshots of every panel | **PASS** | 15 images in `docs/screenshots/` (plan, route options + Pareto, Gantt + burn-down, Monte Carlo + tornado, stop cards, safety, checks, slope layer + legend + readout, live re-plan, custom waypoint + 15° rule, HUD, HUD slow-crew re-plan, HUD SEP replay, methods, tablet) |
| Map + route + timeline + HUD shown | **PASS** | `01_first_screen_plan.jpg`, `03_schedule_gantt_burndown.jpg`, `11_hud_visor.jpg`, `12_...`, `13_...` |
| No console errors | **PASS** | `docs/screenshots/report.json`: 0 console errors, 0 page errors, 0 failed requests, 0 HTTP errors, 0 warnings (Chromium, desktop 1440×900 and tablet 820×1180) |
| Son has clicked through it locally | **OPEN** | Needs Son (steps above) |

### Phase 3 measured numbers (Chromium in the cloud container; `report.json`)
- First route on the map: **0.19 s** after page open. Live plan ready (worker built, all checks, 20,000-run MC): **1.0 s**. SPEC targets: route < 3 s, load < 5 s.
- One live re-plan of the whole plan: **~290 ms** (A* all legs 9-20 ms, walk-home field ~170 ms, Monte Carlo ~30 ms). Adding a stop, click to updated screen: **213 ms**. No-go slope change rebuilds the model in **95 ms**.
- HUD re-plan after "Slow crew": **20 ms** (16 sequences checked exactly; keeps Wildcat Ridge, Skinner Ridge, depot; home at T+5:30 of 6:00, O2 44 % left). SEP replay: **113 ms**; alert at the farthest point (T+1:41), 39 min to shelter vs 60 min limit → rule met. Target < 1 s.
- Browser Monte Carlo for the recommended plan: **98.3 %** (Python: 98.2 %, difference = sampling noise).
- Example of the live check catching a bad plan: adding Hidden Harbor at the end of the recommended order → 36 pts, 345 min, **52.7 %** on time → NO-GO (1 check fails).
- Site size **11 MB** (limit 40 MB). Tablet width: no horizontal scrolling.
- **Tests: pytest 166 passed** (162 before + 3 JS parity + 1 params sync).

### Phase 3 known issues (for Son)
1. **Only Chromium was tested** (that is the browser in the cloud container). Edge is Chromium, so it should behave the same; **Firefox is untested** (module Web Workers need Firefox 114+). Phase 4 should check Firefox.
2. **Windows not tested here.** The app is plain static files, so it should not care; please run the command above on your PC.
3. The JS parity test needs **Node.js**; on a PC without Node it is skipped (the app itself does not need Node).
4. The re-plan event sizes (pace ×0.7, tasks ×1.3, O2 ×2) are **assumptions** chosen to demonstrate the mechanism. They are labelled in the HUD and in ASSUMPTIONS.md.
5. Route-option table, Pareto and tornado do not change when you edit the plan: they are the Python results for the recommended stops (labelled in the app).
6. Skinner Ridge and Wildcat Ridge are 24 m apart, so their map markers overlap at the default zoom (zoom in to separate them).
7. Fixed in passing: METHODS.md limitation 6 said "no 2 m route point steeper than 20°"; the measured result is 0.07 % of points just over 20° (max 20.01°). Now consistent.

### Phase 2 record (planning engine: COMPLETE)

### Done in Phase 2 (Fri 2026-11-13, ~3 h 15 min incl. the paper update)
**One command:** `python -m planner.run_plan` (about 11 s). It writes `site/assets/data/plan.json` (81 KB, for the app), `data/processed/plan_full.json`, previews `data/processed/previews/20_plan_map.png`, `21_plan_charts.png`, `22_validation_rover.png`, and regenerates `docs/ASSUMPTIONS.md` from `config/params.yaml`.

Code (`planner/`): `grid.py` (10 m browser grid, 16-connected moves, no corner cutting), `cost.py` (walking time/energy/hazard), `astar.py` (A* + Dijkstra helpers), `stops_ortools.py` (OR-Tools CP-SAT orienteering + brute-force checker), `montecarlo.py` (20,000-run risk model + tornado), `safety.py` (walk-home field, O2), `validate.py` (vs rover traverse), `run_plan.py` (everything end to end), `plots.py`, `write_docs.py`. Config: `config/stops.yaml` (6 real science sites with quotes), `config/apollo14_table4.csv`. Docs: `docs/METHODS.md`, `docs/ASSUMPTIONS.md` (generated), new Phase 2 section in `docs/DATA_SOURCES.md`, DECISIONS T27-T38.

### Phase 2 update (Fri 2026-11-13, after Son supplied the two papers)
- Read Tobler (1993, p.4) and Minetti et al. (2002, Fig. 1 and p.1041) from Son's PDFs, and checked the formulas against the pages.
- Uphill muscle efficiency 0.25 (assumption) → **0.243** (Minetti, measured for walking). Tobler + Minetti added as a second walking model, used as a check (DECISIONS T39).
- This flipped the recommendation, as known issue 3 warned: the 30-point plan now scores 94.96 % (bar: 95 %).

### Phase 2 results (plain English, all MODELED; real numbers from `plan.json`)
- **Recommended ("Robust") plan:** Habitat → Amalik → Wildcat Ridge → Skinner Ridge → Three Forks depot (pick up the 10 tubes) → Habitat. **26 points, 3.05 km, 267 min planned** (97 walking + 170 work) of 360. **98.2 %** get home on time (20,000 runs). Median 274 min, P95 331 min.
- **Close call, Son's judgement:** the 30-point plan (Amalik, Hidden Harbor, Wildcat Ridge, depot; 286 min) scores **94.96 %** with the main model and **95.9 %** with the Tobler + Minetti check model. It sits right on the 95 % line. The 36-point plan is clearly risky (79.7 %).
- **What drives risk:** work time, not walking (tornado: depot work 39 min, walking speed 38 min, each 45-min stop 36 min).
- **Route options (same stops):** Fastest 267.0 min, Balanced 267.1, Safest 269.0, Shortest-distance 268.0. Safest: +2 min, +70 m, but caution-terrain time goes from 19.3 to 1.7 min and the max cell slope from 19.8° to 12.6°. Fastest = Lowest-energy (T32). 14 distinct Pareto routes.
- **Tightest reserve point:** near the depot, 242 min in, 25 min from home. Margins: **93 min** of time and **36 % of the O₂ tank** above the reserve. At return: 51 % O₂, 44 % battery.
- **SEP rule (60 min):** farthest point 39 min from shelter, 0 violations. Delta-top stops excluded (81 and 88 min).
- **Radiation (Gale proxy):** 39 µGy for the EVA; the May 2024 event would have been 8,100 µGy.
- **Go/No-Go:** all 9 pass.
- **Validation:**
  - A* = Dijkstra exactly; CP-SAT = brute force on 25 cases; every plan solved to proven optimality in 3–17 ms.
  - Slope: 10 m max 15.7°. On the 2 m grid the max is 20.01°, with 0.07 % of points just over 20° (near Skinner Ridge).
  - Rover drives: crater floor 53 % within 25 m (straight line 38 %); delta-top 36 % (straight 30 %): inconclusive.
  - Apollo 14 uphill speeds: model 2.11 vs measured 2.13 km/h.
- **Tests: pytest 162 passed.**

### Phase 2 known issues (for Son)
1. **26 vs 30 points is a close call** (see above). The rule picks 26 today. Decide whether 95 % is the right bar, or let the app show both.
2. **Mars walking cost is probably underestimated.** Inputs are lunar, Earth or design values, and NASA reports higher rates in Mars gravity (charts only).
3. **Please review** the science categories of the 6 sites (DECISIONS T30) and the work times (45/30/20 min, depot 50 min).
4. Many safety values are assumptions (SEP 60 min, O₂ reserve 15 %, tank 0.823 kg, battery draw). All are listed in ASSUMPTIONS.md.
5. Delta-top rover comparison inconclusive. Radiation is absorbed dose only. DONKI has no cached 20 May 2024 entry (HTTP 429).
6. Skinner Ridge stop sits 11.6 m from its core site (nearest safe 10 m cell); 0.07 % of 2 m route points are just over 20°.

### Phase 1 record (data pipeline: COMPLETE)

### Done in Phase 1 (Fri 2026-11-13, ~1 h 20 min)
**One command rebuilds everything:** `python -m pipeline.run_all` (download → layers → web export → previews). Tested from an empty `data/raw/`.

Code: `pipeline/common.py` (grid + coordinates), `download.py`, `crop.py`, `derive.py`, `layers.py`, `export_web.py`, `previews.py`, `run_all.py`. Sources and credits: `docs/DATA_SOURCES.md`.

Data in hand (all real, all from the §5 **primary** sources, no fallbacks needed):
| Layer | What we have |
|---|---|
| Elevation | HiRISE 1 m DTM, AOI window only (24.7 MB local; the 1.8 GB file is not downloaded) |
| Slope, roughness, hillshade, no-go | derived on a 2 m grid (2000 × 2000) |
| Base image | HiRISE 25 cm ortho → 1 m (2.6 MB JPEG) + 25 cm depot close-up |
| Thermal | THEMIS day + night IR, ~81 m/px (**proxy**) |
| Rover | 130 traverse segments, 181 waypoints in the AOI |
| Depot | 10 tube-drop positions (rover position at drop), sols 653-690 |
| Rover photos | 22 real photos (one per rover site, 22 of 24 sites), with per-image credit |
| Space weather | 27 DONKI SEP events (May-Jun 2024), cached (**proxy**) |
| Cross-check | CTX 20 m DTM |

Web assets for Phase 3 (`site/assets/`): image overlays + `layers.json` manifest (bounds, units, label, legend, credit), a 10 m cost grid (`cost_grid.bin` + header, 1.44 MB), `vectors.json`, and the photos. **Total ~10 MB** (limit 40 MB).

### Real measured numbers (from `data/processed/checks.json`)
- AOI: 4 km × 4 km, 77.3726-77.4438° E, 18.4241-18.4916° N. Elevation −2578.96 to −2395.58 m. No data gaps (100 % valid).
- Slope (2 m): median 4.16°, P90 13.19°, P99 26.96°, max 69.28°.
- Roughness (2 m): median 0.021 m, P90 0.046 m, P99 0.094 m.
- **No-go share: 3.50 %** of the 2 m grid (slope > 20°: 3.49 %; roughness > 0.2 m: 0.10 %, and only 0.015 % from roughness alone). On the 10 m browser grid (P90 rule): 5.14 %.
- **Placement check:** our DTM vs rover elevation at 181 waypoints: RMS **0.059 m** (depot: 0.015 m). This proves the crop and coordinates are right. It is *not* an independent accuracy test (see DECISIONS T26).
- **Independent check:** HiRISE vs CTX DTM: mean −1.33 m, std 3.91 m (USGS reports ~0.4 m median over the whole mosaic, same sign).
- Tests: **pytest 106 passed** (tilted-plane slope 0-60° in 4 directions and 3 cell sizes; crop bounds; reprojection puts values in the right place; true ground scale; roughness = 0 on planes; hillshade; no-go; web-asset consistency).
- Timing: DTM window read 40 s (first run) / 213 s (clean rebuild, slower server); ortho window 55 s / 183 s; layers ~8 s; export + previews ~15 s. Clean rebuild from empty `data/raw/`: exit 0, identical numbers.

### Phase 1 known issues
1. **No-go thresholds are placeholders** (20°, 0.2 m). Phase 2 looks for a NASA EVA slope source (NASA-STD-3001 / HIDH). Roughness from a 1 m DTM can't see rocks, so it will mainly be a soft penalty.
2. **Navcam photos look greenish**: raw, uncalibrated browse images. Phase 3 can prefer the colour Mastcam-Z ones for stop cards.
3. **Site 9 photo shows part of the rover arm.** It's a real image; swap it if it's used on a stop card.
4. Sites 35 and 38 have no photo that passes the filter.
5. DTM mosaic seams ("blend40") were not inspected for artificial steps.
6. Radiation dose numbers (Hassler 2014) are still not verified. Phase 2.

### Phase 0 record


### Done in Phase 0 (Fri 2026-11-13)
- Copied the spec from Google Drive (`MARTIAN_MAP_SPEC.md`, 20,192 bytes, same size as on Drive) to `SPEC.md`.
- Tools checked: git 2.43.0 OK; Python 3.13.18 runs OK; `gh` 2.89.0 present, but this cloud session only allows it for search, so GitHub work goes through git + the GitHub connector.
- Made a `.venv` and installed all 13 pinned packages. Checked that each pin has a Windows build for Python 3.12-3.14 (3.11 not supported; see DECISIONS T2).
- Repo skeleton (SPEC §4), `.gitignore`, `.gitattributes`, MIT `LICENSE`, README stub with an AI-use section, `config/params.yaml` with Son's mission choices.
- Smoke tests: `pytest` → **3 passed** (libraries import; every params entry has value/unit/source/note; raw data is git-ignored).
- Interviewed Son (8 questions). Answers are in `DECISIONS.md` (S1-S8).
- Data-source reachability check (below). The first try was blocked by this session's network settings. Son approved a new "nasa" environment, and the check was rerun.

### Data-source reachability (Phase 0 check, nothing large downloaded)
Checked 2026-11-13 by a subagent using HEAD/range requests and small GETs (≤ 5 MB each). I re-checked rows marked ✔︎ myself. "Inferred" = not directly observed.

| SPEC §5 layer | Source checked | Result | Key facts |
|---|---|---|---|
| Topographic (primary) | USGS HiRISE DTM mosaic `JEZ_hirise_soc_006_DTM_..._1m_...blend40.tif` (redirects to `asc-pds-services.s3.us-west-2.amazonaws.com`) | **OK** ✔︎ | 1,839,545,409 B. Range requests work, so a windowed `/vsicurl/` read works. 21400 × 21488 px, 1 m, float32, equirectangular Mars 2000 sphere. Covers 77.2229-77.5840 E, 18.3068-18.6693 N. Uncompressed strips (a crop downloads whole rows, ~86 KB each). |
| Topographic (fallback) | USGS CTX DTM `JEZ_ctx_B_soc_008_DTM_..._20m_...tif` | **OK** | 9.7 MB, 20 m, same projection. |
| Optical (primary) | USGS HiRISE ortho `JEZ_hirise_soc_007_orthoMosaic_25cm_Ortho_blend120.tif` | **OK** | 3.4 GB, 0.25 m, tiled 256 px + LZW (good for windowed reads). Orthographic projection centred 18.4663 N, 77.4298 E, so it needs reprojecting to the DTM grid. A soc_006 equirectangular version also exists (7.4 GB, strips). |
| Optical (fallback) | Mars Trek WMTS layer `JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd` | **OK** | Real layer ID from GetCapabilities. A 256 px PNG tile was fetched at zoom 17. |
| Thermal | Mars Trek `THEMIS_DayIR_ControlledMosaics_100m_v2_oct2018` / `..._NightIR_...` | **OK** | Tiles fetched over Jezero, ~81 m/px at max zoom (inferred). TES thermal inertia is too coarse to use. |
| Ground truth | `M20_waypoints.json`, `M20_traverse.json` | **OK** | GeoJSON. 708 waypoints (sol 13 → 2022), 559 traverse lines (CRS84). |
| Depot | PDS `mars2020_sample_depot_three_forks` `sample_tube_locations.csv` | **OK** ✔︎ | **10 tubes**, sols 653-690, Site 32, ~18.4525 N 77.4078 E (inside the DTM). ⚠️ The coordinates are the **rover's position at each drop**, not the tube's own position. Must be labeled as such, or use the bundle's per-sample ortho mosaics in Phase 1. |
| Depot reference | Photojournal PIA25682 | **OK** | "Perseverance's Three Forks Sample Depot Map" (now on science.nasa.gov). |
| POV imagery | `mars.nasa.gov/rss/api/?feed=raw_images&category=mars2020&feedtype=json` | **OK** | JSON with image URLs, sol, **site + drive** (joins to the waypoints), camera and a credit line. The api.nasa.gov Mars Photos API is not verified (rate-limited). |
| Space weather | DONKI SEP via `api.nasa.gov` | **PARTIAL** | Works, but max 60 days per request, and DEMO_KEY allows ~10 calls/hour. One window (May-Jun 2024) returned 27 events. The kauai mirror failed (connection reset at the remote end). Events are near-Earth detections, not measured at Mars (inferred), so they get a **"proxy"** label. |
| Radiation baseline | Hassler et al. 2014, *Science* 343(6169) (NTRS record 20180007641) | **PARTIAL** | Citation confirmed. **Dose-rate numbers NOT verified**: the publisher, PubMed and ADS pages all show bot checks. |
| Atmosphere (bonus) | ESA/LMD Mars Climate Database v6.2 web interface | **OK** | Reachable. PDS Atmospheres (MEDA) not verified: certificate-trust failure / blocked host. |
| Human-factors refs | Tobler 1993, Minetti et al. 2002 | **NOT VERIFIED** | The source pages block automated access, so the formulas aren't checked yet. Must not be written from memory (SPEC §6.2). |
| Human-factors refs | NTRS: Waligora & Horrigan, "Metabolism and heat dissipation during Apollo EVA periods" (19760005584). NASA-STD-3001 Vol 2 Rev E (20250004555). | **OK (exists)** | PDFs reachable (3.0 MB, 5.8 MB). Contents not read yet. |

**Bottom line:** the five core data kinds are all reachable (topo, optical, thermal, ground truth/depot, POV imagery). The "≥ 3 kinds" rule is safe. The open items are citations and DONKI volume, not data.

### Known issues / risks
1. ~~**Space Apps rules on early work.**~~ **Resolved 2026-11-13:** Son confirmed that building before Sat 9:00 a.m. is allowed. (Son's confirmation; I didn't check the rules myself.) Phases can start early. The times in the plan below are now latest-start times, not earliest.
2. **Windows not tested here.** Claude Code runs in a Linux cloud container. Son should run the 3 README commands once on his PC to confirm `pytest` passes on Windows.
3. **Cloud container is temporary.** Anything not committed and pushed is lost when the session ends. Raw data must be re-downloadable by `pipeline/download.py`.
4. ~~**GitHub push blocked (403).**~~ **Fixed 2026-11-13:** Son installed the Claude GitHub App. Branch `claude/serene-sagan-hlltkr` now pushes to `sonctran/nasa`.
5. **Cost-model citations not yet readable.** Tobler and Minetti formulas and the Hassler dose numbers are behind bot checks. Phase 2 plan: try other open copies (author PDFs, NTRS, the bundle docs). If they can't be checked, use NASA NTRS Apollo EVA metabolic data where it is readable, and label anything unverified "assumption".
6. **DONKI volume.** Covering 2021-2024 needs about 25 calls and a free personal api.nasa.gov key. Fallback (SPEC §5): replay one cached SEP event (the May-Jun 2024 window is already fetched).

## Hour-by-hour plan (local event time)

Submission window: Sat Nov 14 9:00 a.m. → Sun Nov 15 11:59 p.m. Internal target: **submitted by Sun 9:00 p.m.** Feature freeze: **Sun 6:00 p.m.**

### Saturday Nov 14
| Time | Phase | Work | Check-in with Son |
|---|---|---|---|
| 9:00-9:15 | - | Re-read SPEC/PROGRESS/DECISIONS. Confirm the data hosts still respond. | Son says "do Phase 1" |
| 9:15-12:45 | **1 Data** | Windowed read of HiRISE DTM → AOI crop (~4×4 km) → slope, roughness, hillshade, no-go mask. Orthomosaic crop. Rover traverse + waypoints, Three Forks tube locations, POV photos, DONKI SEP cache, thermal layer. Export PNG overlays + bounds JSON + web cost grid. `docs/DATA_SOURCES.md`. | - |
| 12:45-13:15 | 1 exit | `pytest` (tilted-plane slope test, crop bounds). Layer previews in `data/processed/previews/`. | **Son reviews previews** |
| 13:15-13:45 | - | Lunch | |
| 13:45-18:30 | **2 Engine** | Cost model (speed + metabolic vs. grade, cited), A* + Dijkstra test, Pareto routes, OR-Tools stop scheduling (#1 priority), walkback + SEP shelter rules, consumables, dose, Monte Carlo + **Robust plan** ranking (upgrade), validation vs. rover traverse. METHODS.md + ASSUMPTIONS.md. Results JSON. | - |
| 18:30-19:00 | 2 exit | All tests pass. Plain-English results summary with real numbers. | **Son reads results** |
| 19:00-19:45 | - | Dinner | |
| 19:45-22:45 | **3 App (part 1)** | Map + layer toggles + legend + scale + cursor readout. A* Web Worker (must match Python on fixture). Plan panel, route list, comparison table, Pareto chart. | - |
| 22:45 | - | Commit + push. Sleep. | |

### Sunday Nov 15
| Time | Phase | Work | Check-in with Son |
|---|---|---|---|
| 8:00-10:30 | **3 App (part 2)** | Schedule panel (Gantt, burn-down, MC histogram, tornado). Stop cards. Safety panel. **HUD mode** (#3 priority) + **Live re-plan** (upgrade). About/Methods page. Playwright screenshots of every panel. | - |
| 10:30-11:00 | 3 exit | No console errors; screenshots. | **Son clicks through locally** |
| 11:00-14:00 | **4 Validate + deploy** | Independent reviewer subagent (numbers vs. sources, labels, no NASA insignia, first-10-seconds test). Fix gaps. Public repo + GitHub Pages. Test live URL in a fresh browser. | Son decides repo name/URL |
| 14:00-14:30 | - | Lunch | |
| 14:30-17:30 | **5 Submission** | project_page.md, ≤7-slide deck (pptx + pdf), video script, README results, resume bullets, CHECKLIST.md. | **Son approves text field by field** |
| 17:30-18:00 | - | Buffer | |
| **18:00** | **Feature freeze** | Bug fixes and submission text only from here. | |
| 18:00-20:30 | - | Final fixes. Re-test public links in a private window. | |
| 20:30-21:00 | - | **Son submits** (Terms box, "Confirm All Work is Original", Submit for Judging, banner, certificate). | **Son** |
| 21:00-23:59 | - | Emergency buffer only. | |

### Cut order (approved by Son 2026-11-13; replaces the "Cut first" list in SPEC §10)
Cut first → last. The "Keep" list in SPEC §10 is unchanged.
1. Geology/spectral layer
2. Atmosphere layer
3. Thermal layer (moved up: not one of Son's priorities; we still have ≥3 data kinds)
4. Live re-plan (upgrade; needs HUD playback anyway)
5. HUD playback animation (keep the static HUD view; HUD is priority #3)
6. Monte Carlo tornado chart (keep the histogram)
7. Robust plan ranking (upgrade)
8. OR-Tools scheduling (cut last: priority #1; fallback = fixed stop order with timing)

## Next
Phase 5 (submission package, SPEC §8): project_page.md, ≤7-slide deck, video script, README results, resume bullets, CHECKLIST.md.
