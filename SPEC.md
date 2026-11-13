# MARTIAN MAP — Build Spec for Claude Code

NASA Space Apps Challenge 2026 · Challenge: "Interplanetary Survival Guide: Martian Map"
Owner: Son Tran (UH Industrial Engineering). Solo team unless Son says otherwise.
Submission window: opens Sat Nov 14, 9:00 a.m.; closes Sun Nov 15, 11:59 p.m. (local event time). Internal target: submitted by Sun 9:00 p.m.

---

## 0. How to use this file (read first, every session)

- This file is the source of truth. Son will tell you which **Phase** to do. Do only that phase, then stop and report.
- At the start of every phase: read `SPEC.md`, `PROGRESS.md`, `DECISIONS.md` (if they exist). At the end: update `PROGRESS.md` (what's done, what's left, known issues, real measured numbers), commit to git, and show evidence (test output, screenshots, commands + results). Do not just say "done."
- Explain things to Son in plain words, short sentences, no jargon. He is an IE student, not a web developer.
- Ask Son only about decisions that are truly his (project name, mission story, science priorities, team info, anything that changes what judges see). Decide technical details yourself and log them in `DECISIONS.md` with a one-line reason.
- Use subagents for web research and data discovery so the main context stays clean.
- If any step fails twice, stop, explain the problem simply, and propose the fallback in this spec.

## 1. Goal

Build a **working, public, web-based EVA (Marswalk) planning tool** that:
1. Wins on the five judging criteria: **Impact, Creativity, Validity, Relevance, Presentation.**
2. Reads as a strong **Industrial Engineering / operations / supply-chain** portfolio project for summer 2027 internship recruiters. The story: *"I applied operations research, human-factors cost modeling, and risk analysis to plan safe, efficient human work on Mars."*

The IE angle is the differentiator. Most teams will build a pretty map. This one is a **decision-support system**: it optimizes the route and the work schedule, quantifies risk, and shows trade-offs.

## 2. Product concept (starting point: Son's concept — improve it freely)

Son's stated idea: combine NASA Mars imagery, elevation, and geology data into an interactive terrain-analysis and mission-planning tool with **hazard identification, science-site mapping, terrain-aware route optimization, and comparison of navigation alternatives.**

**Default mission scenario (confirm or change with Son in Phase 0):**
- Location: **Jezero Crater**, near the **Three Forks sample depot** at the base of the delta (Perseverance's area; best data coverage: 1 m HiRISE elevation model, 25 cm imagery, real rover traverse, real rover photos).
- Mission: a **two-astronaut EVA** from a habitat/pressurized rover parked on flat crater floor → retrieve cached sample tubes at Three Forks → visit 3–6 delta-front science stops → return safely within the EVA time limit.
- Formats: a **planning view** (habitat/tablet) and a **HUD mode** (simplified helmet-visor view that plays back the route).

AI may be used for ideas as well as building. In Phase 0, suggest 2–3 ways to make the concept more original or higher-impact (one line each), let Son pick, and record the choice in `DECISIONS.md`.

## 3. Hard rules (never break these)

1. **No fabricated anything.** No invented data, URLs, coordinates, citations, quotes, statistics, or results. Every number shown in the app must trace to `DATA_SOURCES.md` (real data) or `ASSUMPTIONS.md` (labeled planning assumption with reason and source if one exists). If you cannot verify something, say so and label it.
2. Label every modeled or assumed value in the UI as **"modeled"** or **"assumption."** Proxy data (e.g., radiation measured at Gale, not Jezero) must be labeled **"proxy."**
3. **No NASA logos, the "meatball," the "worm," flags, mission patches, or mission insignia** in anything you generate (app, slides, images). Credit lines like "Image: NASA/JPL-Caltech" are fine and required for NASA imagery.
4. **AI disclosure:** README, Methods page, and the submission text must say clearly where AI tools were used (ideation, code generation with Claude Code, writing, etc.). Any AI-generated image must carry a visible "AI-generated" watermark. Prefer real screenshots and real NASA imagery over generated images.
5. No images, video, or audio of anyone under 18.
6. All text in English.
7. Repo stays small: **never commit raw downloads.** Raw data goes in `data/raw/` (git-ignored). Commit only processed web assets. Keep total deployed site under ~40 MB and any single file under 50 MB.
8. Must run on **Windows** (Son's machine). Use `pathlib`, avoid shell-specific tricks, give PowerShell commands when Son must run something.
9. Only work inside the project folder. Don't touch other folders.

## 4. Tech stack and repo layout

- **Python 3.11+** for the data pipeline and the reference optimizer: `numpy, scipy, pandas, rasterio, shapely, pyyaml, ortools, networkx (tests only), matplotlib, pillow, requests, pytest, playwright` (screenshots). Use a virtual env (`.venv`). Pin versions in `requirements.txt`.
- **Front end:** static site, no build step. `index.html` + vanilla JS modules + CSS. Vendor **Leaflet** locally (no CDN dependency at judging time). Use `L.CRS.Simple` with a local metric grid (meters, origin at AOI corner) — avoids Mars projection headaches. Live re-routing runs **A\* in a Web Worker** on a downsampled cost grid. Charts: lightweight (vendored Chart.js or hand-drawn SVG/canvas).
- **Hosting:** GitHub Pages from the `/site` folder via a GitHub Actions Pages workflow (or `docs/` on main if simpler). Public repo.

```
martian-map/
  SPEC.md  PROGRESS.md  DECISIONS.md  README.md  LICENSE (MIT)
  requirements.txt  .gitignore
  config/params.yaml          # every model parameter: value, unit, source-or-assumption, note
  pipeline/                   # download.py, crop.py, derive.py, layers.py, export_web.py
  planner/                    # cost.py, astar.py, pareto.py, stops_ortools.py, montecarlo.py, safety.py
  tests/                      # pytest
  data/raw/  (git-ignored)    data/processed/  (git-ignored if large)
  site/                       # index.html, js/, css/, assets/layers/*.png, assets/data/*.json, vendor/
  docs/METHODS.md  docs/DATA_SOURCES.md  docs/ASSUMPTIONS.md
  submission/                 # project_page.md, demo_slides.pptx/.pdf, video_script.md, resume_bullets.md, CHECKLIST.md
  scripts/screenshot.py       # Playwright screenshots of the running site
```

## 5. Data layers (need ≥3 kinds; aim for 5)

For each source: try the primary, verify it actually works, **time-box to 30 minutes**, then use the fallback and log it in `DECISIONS.md`. Record every source in `docs/DATA_SOURCES.md` as a table: layer · provider · exact URL fetched · resolution · date accessed · credit line · processing done.

| Kind | Primary | Fallback | Use in app |
|---|---|---|---|
| **Topographic** | USGS Mars 2020 TRN HiRISE DTM mosaic, 1 m: `https://planetarymaps.usgs.gov/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif` (~1.8 GB). Try a **windowed read over HTTP** with rasterio (`/vsicurl/`) to pull only the AOI; else download once. | USGS Mars 2020 CTX DTM mosaic (20 m) from the same USGS Astrogeology product family; or a single HiRISE DTM from uahirise.org covering the AOI | Elevation, hillshade, **slope**, **roughness** (detrended std-dev or terrain ruggedness index), no-go mask |
| **Optical** | USGS Mars 2020 TRN HiRISE orthomosaic, 25 cm (find exact file on astrogeology.usgs.gov product page; windowed read; resample to the analysis grid for display, keep a sharper crop for stop close-ups) | JPL Mars Trek WMTS tiles (docs: `https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars`; read GetCapabilities, don't guess layer names) | Base map |
| **Thermal** | THEMIS day/night IR or thermal inertia via Mars Trek WMTS or USGS | Skip with note | Proxy for loose sand vs. rocky ground (coarse, ~100 m — label it) |
| **Ground truth / mission** | Perseverance waypoints + traverse GeoJSON: `https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json` and `.../M20_traverse.json`. Three Forks tube locations: PDS Geosciences archive `mars2020_sample_depot_three_forks` (sample_tube_locations product). | Digitize from NASA PIA25682 depot map only if the archive fails — label "approximate" | Depot markers, real traverse overlay, validation |
| **Point-of-view imagery** | Mars 2020 raw image API / gallery (discover the current JSON endpoint; filter by sol near each stop's location) | Curated NASA Photojournal images | "What you'll see" photo on each stop card, with credit |
| **Radiation / space weather** | Surface radiation baseline from peer-reviewed MSL RAD results (find the paper, cite it, **label as Gale-crater proxy**). Solar particle events from NASA DONKI SEP (verify current working endpoint — `api.nasa.gov/DONKI/SEP` or `kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get/SEP`; cache JSON in repo) | Hard-code a cited historical SEP event as a replay scenario | Safety panel: dose estimate for the EVA, "SEP alert replay" that triggers the shelter rule |
| **Atmosphere (bonus, partner data)** | ESA/LMD **Mars Climate Database** for Jezero at a chosen season (ESA is a 2026 Space Agency Partner → bonus points) or Perseverance MEDA data (PDS Atmospheres node) | Skip with note | Temperature/dust context for the chosen EVA time |
| **Geology/spectral (optional, time-box 45 min)** | Published Jezero geologic map or CRISM mineral product | Skip | Context layer for science stops |

AOI: about 4 km × 4 km containing the start site, Three Forks, and the delta front. Analysis grid: 2–5 m cells (pick for speed; document). Web cost grid: downsample so A\* in the browser finishes in < 1 s.

## 6. Planning engine (the IE core — this is what goes on the resume)

All parameters live in `config/params.yaml`. Each row: `value, unit, source_or_assumption, note`. If a published source exists, find it and cite it; if not, mark it `assumption` with a short reason.

### 6.1 Hazard model
- **No-go cells:** slope above a suited-walking limit, roughness above a threshold, DTM no-data, and optional user-drawn keep-out zones. Look for a NASA/EVA human-factors source for slope limits; otherwise label the threshold an assumption and expose it as a slider.
- **Soft penalties:** slope, roughness, sand (thermal proxy), distance from shelter.

### 6.2 Traverse cost model (human factors)
- Walking **speed vs. grade** and **metabolic cost vs. grade**, **direction-dependent** (uphill ≠ downhill). Candidate published models to evaluate and cite: Tobler's hiking function (speed), Minetti et al. 2002 (energy cost of walking on gradients), plus Apollo/NASA reduced-gravity EVA metabolic data for scaling to Mars gravity (0.38 g) and suit load. Verify the formulas from the papers; do not write them from memory without checking.
- Edge cost = weighted sum of **time, metabolic energy, hazard exposure** on an 8- or 16-connected grid.

### 6.3 Route search
- A\* in Python (reference) and the same algorithm in JS (Web Worker). Admissible heuristic.
- **Tests:** on small random grids, A\* cost must equal Dijkstra (networkx/scipy) cost exactly; Python and JS must return the same route cost on a fixture grid.

### 6.4 Navigation alternatives (multi-objective)
- Sweep the weights (or use an epsilon-constraint) to build a **Pareto set** of routes on time vs. energy vs. hazard. Present 3–5 named options: **Fastest, Lowest-energy, Safest, Balanced** (+ "Rover-assisted" if a rover option is in scope).
- Show a Pareto chart and a comparison table (distance, duration, energy kcal, max slope, hazard-exposure minutes, minimum reserve margin).

### 6.5 Science-stop scheduling (operations research)
- Model stop selection and order as an **Orienteering Problem / prize-collecting routing problem** with Google **OR-Tools**: each stop has a science value (from a transparent rubric Son sets in Phase 0) and a dwell time; constraints are the EVA time limit, return-to-start, and the safety rules below. Pairwise stop-to-stop travel times come from the A\* cost model.
- Output an **EVA timeline (Gantt)**: travel segments, task blocks, and roles for EV1/EV2 (buddy rule: crew stays together, or within a set distance).

### 6.6 Safety constraints
- **Walkback rule:** at every point on the route, the crew must be able to walk back to the habitat/rover with consumables left above a reserve margin. Show where on the route the margin is tightest.
- **SEP shelter rule:** during an SEP alert, crew must be able to reach shelter within a set time. Highlight route segments that violate it.
- **Consumables burn-down** chart (O2 and battery modeled from metabolic rate; parameters labeled).
- **Radiation dose estimate** for the EVA (proxy baseline × duration; labeled).
- **Go/No-Go checklist** that turns red when any rule fails.

### 6.7 Uncertainty and risk (Monte Carlo)
- 2,000+ runs varying walking speed, dwell times, and metabolic rate (distributions in params.yaml, labeled).
- Outputs: **P(return within EVA limit)**, P50/P95 duration, minimum reserve distribution, and a **sensitivity (tornado) chart** showing which input drives risk most.

### 6.8 Validation (judges score "Validity")
- Unit tests (above), plus slope check: route's max slope must stay under the no-go limit.
- Compare a planned route between two real Perseverance waypoints against the rover's actual traverse. Report the result honestly (e.g., share of the planned path within X m of the real traverse, path-length ratio). A rover is not a human — say so — but it is real evidence the hazard model avoids what drivers avoided.
- Note DTM accuracy limits from the USGS metadata in METHODS.md.

## 7. App requirements

- **Map:** layer toggles + opacity (ortho, hillshade, slope, roughness, thermal, hazard/no-go, rover traverse, depot, stops), legend, meter scale bar, cursor readout (x, y, elevation, slope).
- **Plan panel:** pick start/end and stops; click-to-add/drag waypoints → live re-route in the worker; weight sliders; route alternatives list; comparison table; Pareto chart.
- **Schedule panel:** Gantt timeline, consumables burn-down, Monte Carlo histogram, tornado chart.
- **Stop cards:** science goal, dwell time, value score, real rover photo with credit, "what to look for."
- **Safety panel:** go/no-go checklist, walkback margin, SEP replay button, dose estimate.
- **HUD mode:** full-screen, high-contrast, minimal visor view: bearing/distance to next waypoint, time remaining, reserve %, hazard warning; "play" button that animates the crew along the route.
- **About/Methods page:** problem, methods in plain words, assumptions table, data sources with credits, AI-use disclosure, limitations, future work.
- **Quality bar:** loads in < 5 s on normal broadband; works in Chrome/Edge/Firefox desktop and on a tablet-size screen; colorblind-safe palettes; no console errors; every number has a unit.
- First screen must explain the project in one sentence and show a route on the map within 3 seconds — judges have no context.

## 8. Submission package (Phase 5)

Space Apps form fields and limits:
- `submission/project_page.md` with ready-to-paste text for: **Project Name · High-Level Project Summary · Link to Project Demo · Link to Final Project · Detailed Project Description** (what it does, how it works, benefits, goals, tools/languages) **· Use of Super Intelligence (SI)** (honest, specific) **· NASA Data** (each source and how it was used) **· Space Agency Partner Data and Other References** (all data, code libraries, images, papers).
- **Demo:** a **7-slide max** deck including title and intro slides, with team name, team member names, and the challenge name; real screenshots; the user experience; how NASA data makes it possible. Build `demo_slides.pptx` and `demo_slides.pdf` (python-pptx; screenshots from `scripts/screenshot.py`). Readable fonts, few words. Optional `video_script.md` for a **≤30-second** video following the official beat sheet (0:00 intro, 0:02 challenge, 0:05 name + tagline, 0:10 how it works, 0:20–0:30 future).
- `README.md`: one-line pitch, GIF/screenshots, live link, the problem, the IE methods, results with real numbers, how to run locally, data credits, AI disclosure, limitations.
- `submission/resume_bullets.md`: project title line + 3 resume bullets (action + method + measured result; **only numbers measured from the final build**) aimed at IE / operations / supply-chain internships, plus a 30-second interview pitch and 3 likely interview questions with short answers.
- `submission/CHECKLIST.md`: exact submit steps (public links tested in a private window, Terms box, "Confirm All Work is Original" box, Submit for Judging, confirmation banner, download participant certificate).

## 9. Phases (each ends with something that works)

**Phase 0 — Setup + plan (plan mode, ~45 min)**
Check tools (git, Python, gh, Claude can run Python). Create venv, repo skeleton, `.gitignore`, MIT license. Interview Son (use the AskUserQuestion tool, ≤8 questions, plain words, each with a recommended default he can just accept): project name, team name/members, mission story (confirm Jezero/Three Forks or change), the 2–3 concept upgrades from §2, top 3 science goals and their value scores, EVA time limit and crew setup (walk only vs. rover-assisted), which 2 features he cares most about. Use a subagent to verify the data sources in §5 are reachable (HEAD/range request, sizes) — don't download big files yet. Write `DECISIONS.md` and an hour-by-hour plan in `PROGRESS.md`. **Exit:** skeleton committed; plan approved by Son.

**Phase 1 — Data pipeline (~3–4 h)**
Download/crop, derive slope/roughness/hillshade/no-go, fetch rover traverse + depot + POV images + other layers, export web assets (PNG overlays with bounds JSON, cost grid as compact binary or JSON). Write DATA_SOURCES.md. **Exit:** `pytest` passes (slope on a synthetic tilted plane equals the known angle; crop bounds correct); a matplotlib preview image of every layer saved in `data/processed/previews/` and shown to Son.

**Phase 2 — Planning engine (~4–5 h)**
Implement §6 in Python: cost model, A\*, Pareto alternatives, OR-Tools stop scheduling, safety rules, Monte Carlo, validation vs. rover traverse. Write METHODS.md and ASSUMPTIONS.md. Export results JSON for the site. **Exit:** all tests pass; a short plain-English results summary with real numbers (route options, P(on-time), tightest reserve point, validation result).

**Phase 3 — Web app (~4–5 h)**
Build §7. Port A\* to a Web Worker; test it matches Python on the fixture. Run a local server and take Playwright screenshots of every panel. **Exit:** screenshots show map + route + timeline + HUD mode; no console errors; Son has clicked through it locally.

**Phase 4 — Validate, polish, deploy (~3 h)**
Use a subagent as an independent reviewer with no build context: check every number in the UI against DATA_SOURCES/ASSUMPTIONS, check labels (modeled/assumption/proxy), check for NASA insignia, check the "first 10 seconds" experience. Fix gaps that affect correctness or judging. Push public repo, deploy GitHub Pages, verify the live URL loads in a fresh browser profile with no login. **Exit:** live URL + repo URL work; reviewer findings fixed or listed.

**Phase 5 — Submission package (~2–3 h)**
Build §8. Show Son the project-page text field by field for approval. **Exit:** all files in `submission/`; slides ≤7; links tested; checklist ready.

**Feature freeze:** Sunday 6:00 p.m. After that, only bug fixes and submission text.

## 10. If time runs short — cut in this order (keep the top items)

Keep: real DTM-based hazard map → A\* route with time/energy → 3 route alternatives + comparison table → walkback rule → EVA timeline → live site + submission text.
Cut first: geology/spectral layer → atmosphere layer → HUD playback animation → Monte Carlo tornado chart (keep the histogram) → OR-Tools scheduling (fall back to a fixed stop order with timing) → thermal layer.
