# Methods

How Marswalk Ops turns real Mars data into an EVA (Marswalk) plan. Plain words first, formulas after.
Every parameter is in `config/params.yaml` and listed with its source or reason in `docs/ASSUMPTIONS.md`.
Data sources: `docs/DATA_SOURCES.md`. Numbers quoted here come from `site/assets/data/plan.json`, made by `python -m planner.run_plan` (Phase 2 run, 2026-11-13).

**Labels.** *Real* = measured data. *Derived* = computed from real data by a stated method. *Modeled* = output of our model. *Assumption* = a value we chose without a verified source. *Proxy* = data from somewhere else (e.g. Gale crater, the Moon) standing in for Jezero.

---

## 1. The problem

Two astronauts leave a habitat on the floor of Jezero Crater. They must pick up the 10 sample tubes Perseverance left at the Three Forks depot, visit as much good science as they can, and walk home safely within 6 hours. The tool answers four questions:

1. **Where is it safe to walk?** (hazard map)
2. **Which way should we walk?** (route search and route options)
3. **Which stops, in which order?** (optimisation)
4. **How likely are we to get home on time, and what could go wrong?** (safety rules and Monte Carlo risk)

## 2. Terrain and hazards

- **Grid.** The planner uses a 10 m grid (400 × 400 cells) built from the 1 m HiRISE DTM. Each 10 m cell keeps the **90th percentile** of the slope and roughness of its 25 cells at 2 m, so a cell that is partly steep counts as steep. The browser uses the same grid file (`site/assets/data/cost_grid.bin`), so the app and the Python planner start from identical numbers.
- **No-go cells**: slope above **20°** (NASA xEVA ConOps: "Walking up/down/across a slope of up to 20°"), roughness above 0.2 m (assumption), or no data. 5.1 % of the grid is no-go.
- **Hazard index** *h* (0 to 1) per cell: 0 below 10° slope and 0.05 m roughness (assumptions), rising in a straight line to 1 at the no-go limit:
  `h = max( clip((slope − 10)/(20 − 10)), clip((rough − 0.05)/(0.2 − 0.05)) )`.
- **Moves.** From each cell the crew can step to 16 neighbours (4 straight, 4 diagonal, 8 "knight" moves). A step is allowed only if both end cells and every cell the straight line crosses are passable, so a route never clips the corner of a no-go cell. A step whose own grade is steeper than 20° is also not allowed.
- Thermal (THEMIS) data is **not** used in the cost: at ~81 m per pixel and uncalibrated, it is too coarse. It is shown as context only.

## 3. Walking cost model (human factors)

The plan of record uses NASA numbers plus a muscle-efficiency value from Minetti et al. (2002). A second model, built from Tobler (1993) and Minetti's energy curve, is run as an independent check (§3b). Both papers were read from PDFs Son supplied, because automated access was blocked (DECISIONS T27, T28).

| Input | Value | Source |
|---|---|---|
| Level walking speed *v₀* | 2 km/h (0.556 m/s) | NASA xEVA ConOps (EVA-EXP-0042 Rev B), lunar planning pace |
| Walking metabolic rate *P₀* | 352 W | NASA BVAD (TP-2015-218570 Rev 2): xEMU average design rate. Apollo 14 walking traverses averaged 354 W (Waligora & Horrigan 1975, Table 4) |
| Mars gravity *g* | 3.710 m/s² | BVAD Table 4-66 |
| Moving mass *M* | 182.7 kg = 82.0 body + 90.7 suit (Apollo A7LB with PLSS) + 10 kit | BVAD Tables 4-67/4-68; kit = assumption |
| Uphill muscle efficiency *η* | 0.243 | Minetti et al. 2002 p.1041: walking, slopes steeper than +0.15 (Earth); applied to all uphill grades (assumption) |

**Energy per metre walked along the ground**

- level or downhill: `e = P₀ / v₀ = 634 J/m` (no energy credit for going downhill: assumption, cautious; on Earth Minetti measured the lowest cost at gradient −0.10)
- uphill: `e = P₀ / v₀ + M · g · sin θ / η` (the extra work of lifting body and suit, θ = slope angle of the step)

**Speed.** The crew paces itself so its metabolic power stays at *P₀* ("constant-power pacing", assumption): `v = min(v₀, P₀ / e)`. So 2.0 km/h on level ground and downhill, 1.4 km/h at a 10 % grade, 1.1 km/h at 20 %, 0.9 km/h at 30 %.

**Check against Apollo 14.** With lunar gravity and Apollo 14's own pace (2.47 km/h) and mean rate (354 W), the model predicts the five uphill walking legs of EVA-2 (grades 4.5–11.3 %) at a mean of **2.11 km/h vs 2.13 km/h measured**, mean absolute error 0.32 km/h per leg (`config/apollo14_table4.csv`, transcribed from Waligora & Horrigan Table 4). Individual legs scatter a lot. The Apollo authors themselves found "a very poor correlation between traverse rate and metabolic rate", which fits a crew that keeps a fairly steady work rate.

**One consequence to know.** Under constant-power pacing, walking energy = *P₀* × walking time. So the **fastest route is also the lowest-energy route**. The real trade-off the planner shows is **time against hazard**. "Lowest-energy" is kept in the table, but it is the same route as "Fastest".

### 3b. Alternative check model: Tobler + Minetti

- Speed: `v = v₀ · T(S)/T(0)` with Tobler's `T(S) = 6·exp(−3.5·|S + 0.05|)` (Tobler 1993, p.4), rescaled so level = 2 km/h. That gives 2.0 km/h on the flat, 1.4 km/h at ±10 % to 20 %, 1.0 km/h at +20 % and 0.7 km/h at +30 %.
- Energy per metre: `P₀/v₀ + (g_Mars/g_Earth)·(Cw(i) − Cw(0))·M`, with Minetti's `Cw = 280.5i⁵ − 58.7i⁴ − 76.8i³ + 51.9i² + 19.6i + 2.5` (Fig. 1). Scaling the grade term by gravity is an assumption. Unlike the main model, downhill is cheaper here (536 J/m at −20 % vs 634 level).
- Both papers measured people on Earth, unsuited. The rescaling to a suited 2 km/h Mars pace is ours.
- **Result:** the full ranking was re-run with this model. Its Robust plan is the **30-point plan** (depot, Wildcat Ridge, Hidden Harbor, Amalik): 282 min planned, **95.9 %** on time. The main model gives that same plan **94.96 %**, just under the 95 % bar (§6). So the two models disagree only about which side of the line the 30-point plan falls.

**Work at stops.** Apollo lunar mean rates (Waligora & Horrigan, Table 2): geology-station work **283 W**; "overhead" work, which includes stowing samples, **312 W** (used for the depot pickup).

**Oxygen.** `O₂ (kg) = metabolic energy (MJ) × 0.0810`, from BVAD Table 4-70 (0.086 kg O₂ per 1.062 MJ, respiratory quotient 0.90). Suit leakage is not modelled.

## 4. Route search

- **Edge cost** (one number per step, in "equivalent level metres"):
  `c = w_t · T/T_ref + w_E · E/E_ref + w_H · (T · h̄)/T_ref + w_D · L`, where *T* = step time, *E* = step energy, *h̄* = mean hazard of the two cells, *L* = map length, and *T_ref*, *E_ref* = time and energy per metre on level ground. On flat safe ground with `w_t + w_E = 1`, a step costs exactly its length.
- **A\*** (Python reference, `planner/astar.py`). Heuristic = straight-line distance × the smallest cost per metre of any step in the graph. It never over-estimates, so A\* returns the true optimum.
- **Tests.** On 12 random grids (60 start/goal pairs each), A\* cost equals networkx Dijkstra exactly. On the real Jezero grid it equals scipy Dijkstra (relative difference **0.0** on all 5 legs of the plan). A plan leg takes A\* 4–19 ms.
- **Route options** (same stops, different weights `w_t, w_E, w_H, w_D`): **Fastest** (1,0,0,0), **Lowest-energy** (0,1,0,0, identical to Fastest, see §3), **Safest** (0.05, 0.05, 0.9, 0), **Balanced** (⅓, ⅓, ⅓, 0, the plan of record) and **Shortest distance** (0,0,0,1), a naive baseline that ignores slope and hazard.
- **Pareto sweep.** The hazard weight goes from 0 to 0.95 in steps of 0.05 (time weight = 1 − w_H). 20 weightings give **14 distinct non-dominated routes** on walking time vs hazard.

## 5. Choosing stops and their order (operations research)

- **Sites.** The habitat sits on the flattest 110 m × 110 m pad of the crater floor 900–1100 m east of the depot (rule: DECISIONS T29). Pad max slope 3.3°, 927 m from the depot. The depot point is the mean rover position over the 10 tube drops (PDS). Science stops are **six real Perseverance sites**: five sample-coring sites, with lat/lon from the PDS *Mars 2020 Initial Reports*, and one boulder-field image site (`config/stops.yaml`). Each core site lands on our 1 m DTM within 0.03–0.28 m of the published elevation.
- **Science value** = Son's rubric: fine-grained layered rock 10, delta layer sequence 6, transported boulders 4. Which category each site gets is our reading of the quoted PDS/NASA text (DECISIONS T30, for Son to review).
- **Work times** (assumptions): depot pickup 50 min, fine-grained rock 45 min, layer sequence 30 min, boulders 20 min.
- **Model.** A prize-collecting **Orienteering Problem**: start and end at the habitat, must visit the depot, choose optional stops to maximise points. Constraints: walking + work time ≤ time budget, and O₂ ≤ tank × (1 − 15 % reserve). Travel times come from the Balanced route between every pair of sites (Dijkstra, 8 × 8 matrix).
- **Solver.** Google **OR-Tools CP-SAT** with a circuit constraint. It proves optimality: every plan is marked `OPTIMAL`, in 3–17 ms. The OR-Tools routing heuristic (guided local search) was tried first. It missed the true optimum on 2 of 10 random test cases, so it was replaced (DECISIONS T31). A test compares CP-SAT with brute force (all subsets × all orders) on 25 random instances, and they match.
- **SEP rule as a filter.** Stops more than 60 min (assumption) from the habitat's shelter are not offered to the optimiser. This removes the two delta-top stops (81 and 88 min away). Turning the rule off does not change the 6-hour optimum: the delta top is out of reach in 6 h anyway.

## 6. Robust plan (Monte Carlo + ranking)

- The optimiser is run with time budgets of 70–100 % of the 6 h limit. Each budget gives one candidate plan.
- Each candidate is simulated **20,000 times**. Each run draws a crew walking-speed factor and a metabolic-rate factor (one each per run), plus a work-time factor for each stop. All are log-normal with median 1, with σ = 0.15, 0.20 and 0.30 (assumptions). A slower crew takes longer to walk but is assumed to use the same walking energy (and O₂) per metre; a task that runs long does use more O₂ (assumptions).
- **Robust plan** = the plan with the most science whose chance of getting home within 6 h, with O₂ above reserve, is at least **95 %** (Son's upgrade S4).

| Budget | Stops (in order) | Points | Planned | P(home on time & O₂ OK) |
|---|---|---|---|---|
| 252 min | Amalik, Hidden Harbor, depot | 20 | 230 min | 99.8 % |
| **270 min** | **Amalik, Wildcat Ridge, Skinner Ridge, depot** | **26** | **267 min** | **98.2 %** ← Robust plan |
| 288 min | Amalik, Hidden Harbor, Wildcat Ridge, depot | 30 | 286 min | 94.96 % (just under 95 %) |
| 324–360 min | Amalik, Hidden Harbor, Wildcat Ridge, Skinner Ridge, depot | 36 | 317 min | 79.7 % ← Max-science plan |

**The 95 % line falls between the 26- and 30-point plans.** With the efficiency at 0.25 (before Minetti was verified), the 30-point plan scored 95.02 %. With the measured 0.243 it scores 94.96 % ± 0.15 %. The Tobler + Minetti check model gives it 95.9 % (§3b). Treat 26 vs 30 points as a close call for Son, not a clear answer. The app should show both. Going to 36 points is clearly risky (80 %).

- **Tornado chart** (each input at its 10th and 90th percentile, the others at median; base 267 min). EVA length swings by: depot work time 39 min; walking speed 38 min; Amalik and Wildcat Ridge work 35 min each; Skinner Ridge work 24 min. Metabolic rate changes O₂ use (0.32–0.53 kg), not time. **Work time, not walking, drives the risk.** Walking is only 97 of the 267 planned minutes.

## 7. Safety rules

- **Walkback rule** (Apollo rule, Bellcomm 1969: "the crewmen shall be able to walk back to the LM on the consumables remaining"). One Dijkstra on the reversed graph gives, for every cell, the time and energy to walk home by the fastest safe route. At every 10 m cell of the plan we check two things. First, O₂ left minus O₂ to walk home stays at or above the 15 % reserve. Second, elapsed time plus walk-home time stays within 6 h. **Tightest point**: near the depot at 242 min, with a 25-min walk home. Margins there: **93 min** of time, and **36 % of the tank** of O₂ above the reserve.
- **SEP shelter rule** (assumption: 60 min). The farthest point of the plan is **39 min** from the habitat. There are 0 violations.
- **Consumables** at return (modeled): O₂ 0.41 kg used, **51 % left** (tank 0.823 kg = 8 h × 352 W, an xEMU-like assumption). Battery 215 Wh of 387.5 Wh used (Apollo PLSS battery; constant 48.4 W draw, assumption), **44 % left**.
- **Radiation (proxy).** Curiosity RAD at Gale measured about 210 µGy/day (NASA PIA17600). For the 267-min EVA that gives **39 µGy** of absorbed dose. For context, the 20 May 2024 solar event would have given an astronaut **8,100 µGy** (NASA), about 39 days of background. Its time profile is not available, so no in-EVA SEP dose is modelled. The SEP replay in the app tests the shelter rule only.
- **Go/No-Go**: 9 checks (time limit, 95 % on-time, both walkback checks, SEP reach, max slope, O₂ reserve, battery, tubes collected). **All pass** for the Robust plan.

## 8. Route options for the Robust plan's stops (Amalik, Wildcat Ridge, Skinner Ridge, depot)

| Option | Distance | Walking | EVA total | Walk energy | Time on caution terrain | Hazard score | Max cell slope | Climb |
|---|---|---|---|---|---|---|---|---|
| Fastest (= Lowest-energy) | 3,046 m | 97.0 min | 267.0 min | 490 kcal | 19.3 min | 2.51 | 19.8° | 42 m |
| Balanced (plan) | 3,046 m | 97.1 min | 267.1 min | 490 kcal | 8.4 min | 0.94 | 15.7° | 43 m |
| Safest | 3,116 m | 99.0 min | 269.0 min | 500 kcal | 1.7 min | 0.22 | 12.6° | 42 m |
| Shortest distance (naive) | 3,038 m | 98.0 min | 268.0 min | 495 kcal | 18.6 min | 2.46 | 19.8° | 52 m |

"Caution terrain" = cells with hazard index > 0 (slope > 10° or roughness > 0.05 m). Hazard score = minutes weighted by the hazard index. **Finding:** compared with Fastest, the Safest route costs only +2.0 min and +70 m, but cuts time on caution terrain from 19.3 to 1.7 min and keeps every cell under 12.6° (Fastest touches 19.8°). The naive shortest route is not faster: it climbs 10 m more and is 1 min slower.

## 9. Validation

- **Slope check.** The plan's steepest 10 m cell is 15.7° (limit 20°). On the finer 2 m grid along the route: median 2.7°, 95th percentile 8.8°, max 20.01°, with 0.07 % of points just above 20° (near Skinner Ridge; the 10 m grid smooths them).
- **Against Perseverance's real drives** (a rover is not a human: supporting evidence only). Our Balanced planner (human limits) routes between the same two waypoints, and we measure how much of the planned path lies near the rover's actual traverse. The naive straight line is the baseline.

| Drive | Rover | Planned | Planned within 25 m of rover | Straight line within 25 m | Median offset (planned / straight) |
|---|---|---|---|---|---|
| Crater floor → delta front (sols 399–409) | 1,995 m | 1,966 m | **53 %** | 38 % | 20 m / 35 m |
| Delta-top climb (sols 708–721) | 1,860 m | 1,447 m | 36 % | 30 % | 55 m / 48 m |

On the crater floor the planner follows the rover clearly better than a straight line. On the delta-top climb, both routes use the same gap through the first scarp. After that, the rover swung far north-east while our planner went direct, through ground our 1 m DTM rates safe. The result is **inconclusive**: the planner is barely better than a straight line within 25 m and slightly worse within 50 m (49 % vs 51 %). Likely reasons, not checked: rover-only limits (sand ripples, rocks smaller than the DTM can show), driving-planning rules, and science targets along the way.

- **DTM accuracy limits** (USGS FGDC metadata for the mosaics). HiRISE orthoimages are co-registered to better than 1.1 m for most pairs and better than 3 m for all pairs. The HiRISE vs CTX median vertical offset is about 0.4 m. In our area, HiRISE minus CTX: mean −1.33 m, std 3.91 m. The DTM's real detail is coarser than its 1 m posting, so rocks smaller than a few metres are invisible. Mosaic seams ("blend40") were not inspected.

## 10. Limitations (honest list)

1. **Walking model on Mars is extrapolated.** Speed and metabolic inputs are lunar or design values. NASA's EVA Walkback Test reports that Mars gravity "required higher metabolic rates than Moon gravity", but its Mars numbers are only in charts we could not read. So our O₂ use is probably low. The Monte Carlo metabolic spread covers only part of that.
2. Both walking models are Earth/lunar data stretched to Mars. Constant-power pacing, no downhill credit, applying Minetti's 0.243 efficiency to all uphill grades, and the gravity scaling in the check model are assumptions.
3. Suit mass is the Apollo A7LB system. The O₂ tank is sized like xEMU (8 h at 352 W). No verified Mars suit numbers exist.
4. Work times, the 60-min SEP shelter limit, the 15 % O₂ reserve and the Monte Carlo spreads are assumptions. The 30-point plan sits right on the 95 % line (94.96 % vs 95.9 % depending on the walking model), so the 26- vs 30-point choice is a close call.
5. Radiation is a Gale-crater proxy, absorbed dose only. The habitat's shielding is not modelled.
6. The 10 m grid with P90 aggregation smooths small obstacles. The 2 m check above finds 0.07 % of route points just over 20° (max 20.01°), and rocks below DTM resolution are invisible.
7. Depot tube positions are the rover's position at each drop, not the tube itself. Pickup is one 50-min task at the depot centre.

## 11. The web app (Phase 3)

The app (`site/`) is a static page: no server code and no build step.

- **Same engine in the browser.** `site/js/engine.js` is a line-by-line port of the Python cost model, A*, walk-home field, timeline, safety checks and Monte Carlo. It runs in a Web Worker (`site/js/worker.js`), so the map stays smooth. The test `tests/test_js_engine.py` runs it in Node.js and checks: on 8 random fixture grids (96 routes) the cost matches Python to 1e-12 and the path is the same cell for cell; on the real grid the 5 legs of the recommended plan match Python A* and the Dijkstra costs in `plan.json`; the whole-plan totals match `plan.json` to 1e-9.
- **Live planning.** When the user changes stops, order, waypoints, weights, the no-go slope or keep-out boxes, the worker re-routes every leg, rebuilds the timeline and the walk-back/SEP checks, and runs a new 20,000-run Monte Carlo. The browser Monte Carlo uses its own random-number generator (mulberry32 + Box-Muller), so its probabilities differ from Python by sampling noise only (recommended plan: 98.3 % in the browser vs 98.2 % in Python; the test allows 4 standard errors).
- **Live re-plan in the HUD (owner upgrade S4).** During playback the user can trigger three events. *Solar storm alert*: the crew stops and walks home by the fastest safe route; the app reports the time to shelter against the limit. *Slow crew* (pace ×0.7, tasks ×1.3) and *Suit O2 fault* (O2 use ×2): the worker tries **every** subset and order of the stops not yet done (at most 326 sequences for 5 stops), keeps the depot if any plan allows it, then the most science points, then the earliest return, subject to the EVA limit and the O2 reserve. The event sizes are **assumptions** (`replan.*` in `config/params.yaml`), chosen to show the mechanism, not failure statistics.
- **What is precomputed.** The route-option table, the Pareto chart, the tornado chart and the validation numbers come from the Python run (`plan.json`) for the recommended stops; the app says so next to each.

## 12. How to reproduce

```powershell
.\.venv\Scripts\python.exe -m pipeline.run_all     # data (Phase 1)
.\.venv\Scripts\python.exe -m planner.run_plan     # plan, results JSON, previews, ASSUMPTIONS.md (about 15 s)
.\.venv\Scripts\python.exe -m pytest               # all tests (the JS parity test needs Node.js, else it is skipped)
.\.venv\Scripts\python.exe -m http.server 8000 --directory site   # then open http://localhost:8000
.\.venv\Scripts\python.exe scripts\screenshot.py   # click-through + screenshots (needs: python -m playwright install chromium)
```

## 13. Use of AI

The pipeline, planner and web-app code, these docs, and the literature search were produced with Claude Code (Anthropic), working under Son Tran's direction. Every source quoted here was re-read from the original page or PDF before use. Values that could not be verified are labelled assumptions, or were left out.
