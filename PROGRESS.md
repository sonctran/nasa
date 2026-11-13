# PROGRESS

## Current status: Phase 2 (planning engine): COMPLETE. Next: Phase 3 (web app), when Son says so.

### Done in Phase 2 (Fri 2026-11-13, ~2 h 45 min)
**One command:** `python -m planner.run_plan` (about 11 s). It writes `site/assets/data/plan.json` (81 KB, for the app), `data/processed/plan_full.json`, previews `data/processed/previews/20_plan_map.png`, `21_plan_charts.png`, `22_validation_rover.png`, and regenerates `docs/ASSUMPTIONS.md` from `config/params.yaml`.

Code (`planner/`): `grid.py` (10 m browser grid, 16-connected moves, no corner cutting), `cost.py` (walking time/energy/hazard), `astar.py` (A* + Dijkstra helpers), `stops_ortools.py` (OR-Tools CP-SAT orienteering + brute-force checker), `montecarlo.py` (20,000-run risk model + tornado), `safety.py` (walk-home field, O2), `validate.py` (vs rover traverse), `run_plan.py` (everything end to end), `plots.py`, `write_docs.py`. Config: `config/stops.yaml` (6 real science sites with quotes), `config/apollo14_table4.csv`. Docs: `docs/METHODS.md`, `docs/ASSUMPTIONS.md` (generated), new Phase 2 section in `docs/DATA_SOURCES.md`, DECISIONS T27-T38.

### Phase 2 results (plain English, all MODELED; real numbers from `plan.json`)
- **The recommended ("Robust") plan:** Habitat → Amalik → Hidden Harbor → Wildcat Ridge → Three Forks depot (pick up the 10 tubes) → Habitat. **30 science points, 3.17 km, 286 min planned** (100 min walking + 185 min work) out of a 6 h (360 min) limit.
- **Chance of getting home on time** (with O2 above the reserve): **95.0 %** (± 0.15 %, 20,000 Monte Carlo runs). This *just* meets Son's 95 % target. Median EVA 293 min, P95 354 min.
- **The trade-off:** adding Skinner Ridge (+6 points, only 23 m from Wildcat Ridge) gives the 36-point "Max-science" plan: 317 min planned, but only **79.8 %** chance of getting home on time. A smaller plan (depot, Skinner Ridge, Wildcat Ridge, Amalik: 26 points, 267 min) gets home on time in 98.2 % of runs.
- **What drives the risk:** work time, not walking. Tornado swing on EVA length: depot work 39 min, walking speed 39 min, each science stop 36 min.
- **Route options for the same stops:** Fastest 285.4 min, Balanced 285.5 min, Safest 286.4 min, Shortest-distance 286.4 min. The Safest route costs +0.9 min and +27 m versus Fastest, but cuts time on caution terrain (slope > 10° or rough) from **15.6 to 1.0 min**. Fastest = Lowest-energy in this model (see DECISIONS T32). Pareto sweep: 12 distinct non-dominated routes.
- **Tightest reserve point:** near the depot, 259 min into the EVA, 26 min walk from home. Margins there: **74 min** of time, and **32 % of the O2 tank** above the 15 % reserve. At return: 47 % O2 and 41 % battery left (modeled).
- **SEP shelter rule (60 min, assumption):** the farthest point of the plan is 41 min from the habitat, so there are 0 violations. The two delta-top stops (81 and 88 min away) are excluded. Without the rule, the 6 h optimum doesn't change.
- **Radiation (Gale proxy):** 42 µGy absorbed for the EVA (210 µGy/day). The 20 May 2024 solar event would have been 8,100 µGy (NASA).
- **Go/No-Go:** all 9 checks pass.
- **Validation:**
  - A* = Dijkstra exactly (0.0 relative difference on all 5 legs).
  - CP-SAT = brute force on 25 random cases; every real plan was proven optimal in 2-12 ms.
  - Max cell slope on the route is 14.3° (10 m grid); on the 2 m grid the max is 17.4°, with 0 % above 20°.
  - Rover drives: crater floor → delta front, **53 %** of the planned path is within 25 m of Perseverance's real path (straight line 38 %). Delta-top climb: 36 % (straight line 30 %): **inconclusive**.
  - Walking model vs Apollo 14 uphill legs: 2.12 vs 2.13 km/h mean.
- **Tests: pytest 161 passed** (was 106). New: A* vs networkx on 12 random grids; A* vs scipy on the real grid; CP-SAT vs brute force on 25 instances; the cost model by hand; plan.json consistency (timeline continuous, totals add up, route joins the sites, rubric scores, 1 m DTM within 0.5 m of PDS core elevations).

### Phase 2 known issues (for Son)
1. **Tobler and Minetti could not be verified** (bot checks), so they are not used. The walking model uses NASA numbers plus 3 labelled assumptions (muscle efficiency 0.25, constant-power pacing, no downhill credit). If Son can open the two papers in a browser, we can add them as a second model (Phase 4).
2. **Mars walking cost is probably underestimated.** The inputs are lunar/design values, and NASA reports higher rates in Mars gravity (charts only). The Monte Carlo spread covers part of this.
3. **The Robust plan is borderline** (95.0 % vs a 95 % target). Small parameter changes can flip the recommendation to the 26-point plan (98.2 %). The app should show both.
4. **Son should review the science categories** given to the 6 sites (DECISIONS T30) and the assumed work times (45/30/20 min, depot 50 min).
5. Many safety values are assumptions: SEP 60 min, O2 reserve 15 %, O2 tank 0.823 kg, battery draw. All are listed in ASSUMPTIONS.md, and the app will expose the key ones as sliders.
6. The delta-top rover comparison is inconclusive (see METHODS §9).
7. Radiation: absorbed dose only (the mSv numbers could not be verified). No SEP dose is modelled during the EVA.
8. DONKI has no cached 20 May 2024 entry (API rate limit, HTTP 429). The SEP replay can use a cached May 2024 near-Earth event (proxy), or retry with a personal api.nasa.gov key.
9. Skinner Ridge's core site cell is not passable on the 10 m grid, so the stop sits on the nearest safe cell, 11.6 m away. All other sites are ≤ 7.1 m away.

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
Phase 3 (web app): map + layers, A* Web Worker (must match Python on a fixture), plan/schedule/safety panels, HUD mode. Inputs are ready in `site/assets/data/` (`plan.json`, `cost_grid.bin`, `layers.json`, `vectors.json`).
