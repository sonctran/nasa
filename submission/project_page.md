# Project page text (ready to paste)

**Status: DRAFT for Son to approve, field by field.** Every number below was measured from the final build
(`site/assets/data/plan.json`, `docs/screenshots/report.json`, `pytest`). If the plan is re-run and a number
changes, re-run `python scripts/build_deck.py` and update this file.

---

## Project Name

Marswalk Ops

## High-Level Project Summary

Marswalk Ops is a web tool that plans a six-hour, two-astronaut walk on Mars and tells the crew how likely they are to get home on time. It uses real NASA data for Jezero Crater: a 1 m HiRISE elevation model, a 25 cm HiRISE image mosaic, Perseverance's real path and photos, and the Three Forks sample-tube depot. The tool finds where it is safe to walk, picks which science stops to visit and in what order with an exact optimizer, checks nine safety rules, and runs 20,000 simulated EVAs to measure the risk. The recommended plan collects 26 science points and gets home on time in 98.2 % of the simulated runs. A helmet-view mode plays the walk back and re-plans in under a second when a solar storm alert, a slow crew or a suit oxygen fault happens. A map shows the ground. A plan has to answer the planner's real question: which plan is worth the risk?

## Link to Project Demo

https://sonctran.github.io/nasa/demo_slides.pdf

(7 slides. The same file is in the repository at `submission/demo_slides.pdf`, with an editable `submission/demo_slides.pptx`.)

## Link to Final Project

Live app (no login): https://sonctran.github.io/nasa/

Source code: https://github.com/sonctran/nasa

## Detailed Project Description

### What it does

You open the page and see a route on a real image of Jezero Crater, with a GO or NO-GO verdict in the header. The mission: two astronauts leave a habitat on the crater floor, pick up the 10 sample tubes Perseverance left at the Three Forks depot, visit as many good science sites as they can, and walk home inside six hours.

- **Map.** HiRISE image, elevation, slope, roughness, no-go zones, THEMIS infrared, Perseverance's real path, the depot tubes and real rover photos. Each layer is marked real, derived, assumption or proxy.
- **Plan.** A chart shows four candidate plans: more science points against the chance of getting home on time. You can add, remove or reorder stops, drop waypoints, draw keep-out boxes and change the safety rules. The route, timeline, safety checks and a 20,000-run risk simulation are recomputed in the browser in about a third of a second.
- **Schedule.** A timeline for both crew members with roles, an oxygen and battery burn-down, a histogram of simulated EVA lengths, and a chart of what drives the risk.
- **Stops.** Six real Perseverance sites with the NASA description, the science goal, what to look for, and the nearest real rover photo.
- **Safety.** Nine go/no-go checks, the walk-back rule, the solar-storm shelter rule, and a radiation dose estimate.
- **Checks.** The evidence: tests, a comparison with Apollo 14, and a comparison with real Perseverance drives.
- **HUD mode.** A helmet-visor view that plays the walk back and re-plans live when something goes wrong.

### How it works

1. **Terrain.** Slope and roughness are computed from the 1 m HiRISE elevation model on a 10 m planning grid. Ground steeper than 20° is no-go (a NASA lunar suit limit, used as a proxy).
2. **Walking cost.** A human-factors model gives the time, energy and hazard of every step. It uses NASA suit numbers (2 km/h pace, 352 W) and a measured uphill muscle efficiency (Minetti et al. 2002), scaled to Mars gravity.
3. **Route search.** A* finds the best route between any two points on a 16-direction grid. A test proves it gives exactly the same cost as Dijkstra.
4. **Stop selection.** Choosing the stops and their order is a prize-collecting orienteering problem. Google OR-Tools CP-SAT solves it to proven optimality in 3 to 17 milliseconds per plan.
5. **Risk.** Each candidate plan is simulated 20,000 times with random walking speed, task time and metabolic rate. The recommended "Robust" plan is the one with the most science that still gets home on time, with oxygen in reserve, in at least 95 % of runs.
6. **Safety rules.** At every 10 m of the route the tool checks that the crew could still walk home on the oxygen and time left (an Apollo rule), and that shelter is within 60 minutes if a solar storm alert comes.
7. **In the browser.** The whole planner is ported to JavaScript and runs in a Web Worker. A test checks it matches the Python planner cell for cell.

### Results (all modeled)

| Plan | Science points | Planned length | Home on time, oxygen OK |
|---|---|---|---|
| Short | 20 | 230 min | 99.8 % |
| **Recommended** | **26** | **267 min** | **98.2 %** |
| One more stop | 30 | 286 min | 94.96 % (just under the 95 % bar) |
| Maximum science | 36 | 317 min | 79.7 % |

- The recommended plan walks 3.05 km and uses 267 of 360 minutes. All nine go/no-go checks pass.
- Work at the stops is 170 of those 267 minutes. The sensitivity chart shows that task time, not walking, drives the risk (largest single swing: 39 minutes).
- The safest route costs 2.0 more minutes than the fastest one and cuts time on steep or rough ground from 19.3 to 1.7 minutes.
- Tightest walk-back margin: 93 minutes and 36 % of the oxygen tank above reserve. The crew is never more than 39 minutes from shelter.

### How we know it holds up

- 172 automated tests pass. A* equals Dijkstra exactly. The browser planner equals the Python planner.
- With lunar gravity, the walking model predicts Apollo 14's uphill walking speed at 2.11 km/h against 2.13 km/h measured.
- On a real Perseverance drive across the crater floor, 53 % of our planned path lies within 25 m of the rover's path, against 38 % for a straight line. On a second drive (the delta-top climb) the result was inconclusive, and we say so.

### Benefits

- **For mission planners:** a plan that comes with a number for its risk, not only a line on a map.
- **For crews:** a clear go/no-go, the point where the margin is tightest, and a new plan in under a second when the day changes.
- **For students and the public:** a hands-on way to see why a Marswalk is an operations problem.

### Goals

Show that operations research, human-factors cost modeling and risk analysis, the everyday tools of industrial engineering, can turn open NASA data into a decision a crew could act on. And be honest about it: every modeled, assumed or proxy value is labelled in the app.

### Limits

Walking and suit numbers are lunar, Earth or design values applied to Mars, so walking cost is probably underestimated. Work times, the 60-minute shelter limit, the 15 % oxygen reserve and the simulation spreads are assumptions. Radiation is a Gale-crater proxy. The 10 m grid cannot see rocks smaller than a few metres. This is a planning study, not flight software.

### Tools and languages

Python (NumPy, SciPy, rasterio, Shapely, Google OR-Tools, NetworkX, Matplotlib, Pillow, pytest, Playwright, python-pptx), JavaScript (vanilla ES modules, Web Worker), Leaflet 1.9.4, HTML and CSS, GitHub Pages and GitHub Actions.

## Use of Super Intelligence (SI)

AI tools were used, and here is exactly where:

- **Ideas.** Claude (Anthropic) suggested ways to make the concept stronger. Son Tran chose two: the "Robust plan" ranking and the live re-plan.
- **Code.** Most of the code (data pipeline, planner, web app, tests) was written with Claude Code, under Son Tran's direction, then checked by automated tests.
- **Research and writing.** Claude Code helped find and read the data sources and papers and drafted the documentation, the slides and this text. Sources were re-read from the original page or PDF before use. Values that could not be verified are labelled assumptions or were left out.
- **Images.** No AI-generated images are used anywhere. Every picture is real NASA/USGS imagery or a real screenshot of the app.
- No NASA logos, flags or mission insignia are used.

## NASA Data

| Data | How it was used |
|---|---|
| HiRISE Digital Terrain Model mosaic, 1 m, Mars 2020 TRN (USGS Astrogeology; Fergason et al. 2020, doi:10.5066/P9REJ9JN; HiRISE: NASA/JPL-Caltech/University of Arizona) | Elevation, slope, roughness, no-go zones and the planning grid |
| HiRISE orthoimage mosaic, 25 cm (USGS Astrogeology; Fergason et al. 2020, doi:10.5066/P9QJDP48) | Base map and the depot close-up |
| CTX DTM mosaic, 20 m (USGS, doi:10.5066/P906QQT8; CTX: NASA/JPL-Caltech/MSSS) | Independent cross-check of the elevation data |
| THEMIS day and night infrared mosaics (NASA/JPL-Caltech/Arizona State University, via NASA Mars Trek) | Context layer, labelled proxy |
| Perseverance traverse and waypoints (NASA/JPL-Caltech, Mars 2020 MMGIS) | Real path overlay, position check, validation of the route planner |
| Three Forks sample depot bundle (NASA PDS Geosciences Node, `mars2020_sample_depot_three_forks`) | The 10 tube-drop positions and the depot stop |
| Mars 2020 Initial Reports, sample dossier (NASA PDS Geosciences Node) | Position and description of the science stops |
| Mars 2020 raw images (NASA/JPL-Caltech; Mastcam-Z: NASA/JPL-Caltech/ASU) | "What you'll see" photo on each stop card |
| DONKI solar energetic particle events (NASA CCMC) | Solar-storm alert replay, labelled proxy (near-Earth records) |
| Curiosity RAD dose rate, PIA17600, and NASA's account of the May 2024 solar storm | Radiation dose estimate, labelled proxy (Gale crater) |
| NASA xEVA System ConOps (EVA-EXP-0042 Rev B), NASA Life Support Baseline Values and Assumptions Document (TP-2015-218570 Rev 2), Waligora & Horrigan 1975 (Apollo EVA metabolism), Apollo EMU Operations Handbook, Bellcomm 1969 walk-back rule | Slope limit, walking pace, metabolic rates, oxygen per unit energy, suit mass, battery, the walk-back rule |

Exact URLs and access dates: `docs/DATA_SOURCES.md` in the repository, also shown on the app's Methods page.

## Space Agency Partner Data and Other References

**Space agency partner data:** none was used. The ESA/LMD Mars Climate Database was reachable but is not part of this build; it is listed as future work.

**Papers**
- Minetti, Moia, Roi, Susta & Ferretti (2002). *Journal of Applied Physiology* 93:1039-1046. doi:10.1152/japplphysiol.01177.2001 (walking energy on slopes; uphill efficiency 0.243)
- Tobler, W. (1993). Three presentations on geographical analysis and modeling. NCGIA Technical Report 93-1.
- Fergason, R., Galuszka, D., Hare, T., et al. (2020). USGS HiRISE DTM and orthoimage mosaics for Mars 2020 (DOIs above).
- Horn (1981) 3 × 3 slope method, the same method as GDAL `gdaldem slope`.

**Code libraries**
- Google OR-Tools (CP-SAT), NumPy, SciPy, pandas, rasterio, Shapely, PyYAML, NetworkX, Matplotlib, Pillow, requests, pytest, Playwright, python-pptx
- Leaflet 1.9.4 (BSD-2-Clause), vendored in the repository

**AI tool:** Claude Code (Anthropic).

**Images:** all map imagery is NASA/JPL-Caltech/University of Arizona (HiRISE) through the USGS mosaics, and NASA/JPL-Caltech (rover photos). Credits appear on the map, on each photo and in the Methods page.
