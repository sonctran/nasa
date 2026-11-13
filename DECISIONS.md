# DECISIONS

One line per decision, with its reason. "Son" = owner decision. "Tech" = technical decision made by Claude Code under SPEC §0.

## Son's decisions (Phase 0 interview, Fri 2026-11-13)

| # | Decision | Reason / note |
|---|---|---|
| S1 | Project name: **Marswalk Ops** | Sounds like an operations tool and fits the IE story. |
| S2 | Team: **solo**. Team name = **Marswalk Ops**. Member: Son Tran. | Slides need a team name and member names. |
| S3 | Mission: **Jezero Crater, Three Forks depot + delta front.** 2 astronauts walk out from a habitat on the flat crater floor, pick up the cached sample tubes, visit 3-6 delta-front science stops, walk back. | Best data coverage (SPEC §2 default). |
| S4 | Concept upgrades: **Live re-plan** and **Robust plan**. Not chosen: supply-cache placement. | Live re-plan: trigger an event during HUD playback (solar storm alert, slow crew, suit problem) and re-plan the way home in < 1 s. Robust plan: rank plans by chance of getting home on time (Monte Carlo), e.g. "95%-on-time plan" vs. "fastest plan". |
| S5 | Science rubric "Ancient-life focus": fine-grained layered rock = 10, delta layer sequence = 6, transported boulders = 4. Tube pickup = required task, not scored. | Stored in `config/params.yaml` as `owner-set`. Actual stops are picked from real data in Phase 1-2. |
| S6 | EVA time limit: **6 h door to door.** | Labeled "assumption" until a NASA source is verified in Phase 2. |
| S7 | Crew: **2 astronauts, walk only.** No rover-assisted route option. | Keeps scope tight. Buddy rule applies. |
| S8 | Feature priority: **1. Stop scheduling + timeline, 2. Safety + risk, 3. HUD helmet view.** | Son added the HUD as #3 during the interview ("I like the concept of a nice HUD display"). These get extra polish and are cut last. |

| S9 | **Plan approved**: the hour-by-hour schedule in PROGRESS.md, plus a new cut order (geology → atmosphere → thermal → live re-plan → HUD playback → MC tornado → robust plan → OR-Tools last). | Matches Son's priorities (S8). Approved 2026-11-13. |

| S10 | **Building before the Sat 9:00 a.m. window is allowed.** | Son confirmed the event rules (2026-11-13). Plan times become latest-start times. |

## Technical decisions

| # | Decision | Reason |
|---|---|---|
| T1 | Project root = this repo (`sonctran/nasa`), not a new `martian-map/` folder. | The user said to work in this folder. Note: the GitHub Pages URL will contain `/nasa/` unless Son renames the repo (his call, Phase 4). |
| T2 | Python **3.12-3.14** supported. 3.11 is not. | Checked with `pip download --platform win_amd64`: numpy 2.5.4, scipy 1.18.1, rasterio 1.5.2 and networkx 3.7 have no Windows build for 3.11. All 13 pins have Windows builds for 3.12, 3.13 and 3.14. The spec says "3.11+", and 3.12+ still meets that. |
| T3 | Pin exact top-level versions (latest on PyPI, 2026-11-13). | Reproducible installs on Son's Windows PC. |
| T4 | `.gitattributes` with `* text=auto`. | Avoids Windows/Linux line-ending churn. |
| T5 | `data/raw/` and `data/processed/` are git-ignored, except small `data/processed/previews/*.png`. Also ignore `*.tif`, `*.img`, `*.vrt`. | SPEC rule 7: never commit raw downloads. Previews are shown to Son in Phase 1. |
| T6 | Claude Code runs in a **Linux cloud container**, not on Son's PC. Windows support: `pathlib` everywhere, Windows wheels checked, PowerShell commands in README. | The SPEC assumes a Windows machine. Risk: I can't run tests on Windows here, so Son should run `pytest` once on his PC (README has the commands). |
| T7 | Created a personal cloud environment **"nasa"** with 20 allowed data/citation hosts (USGS, NASA, PDS, LMD, DOI and journal sites). This session switched to it. Son approved it on the approval card. | The Default environment blocked every data host (proxy 403), so the §5 checks failed. A separate environment keeps Son's other projects unchanged. |
| T8 | GitHub actions (push, Pages) go through git + the GitHub connector. The `gh` CLI here is search-only. | Cloud session limitation. |
| T9 | "Plan mode" for Phase 0 means: no feature code until Son approves the plan. The skeleton, config stub and smoke tests are allowed. | The Phase 0 exit needs "skeleton committed" and "plan approved". |
| T10 | Upgrade placement: **Robust plan** is built in Phase 2 with the Monte Carlo (§6.7). **Live re-plan** is built in Phase 3 on top of the HUD playback + Web Worker A*. | Each reuses a component that already exists. |
| T11 | `tests/test_skeleton.py` checks that every `params.yaml` entry has exactly `value, unit, source_or_assumption, note`. | Enforces SPEC §6 and rule 1 automatically from day one. |
| T12 | Topo source: HiRISE 1 m DTM via windowed `/vsicurl/` read (primary works). CTX 20 m stays as the fallback. | Range requests verified. The 1.8 GB file is never downloaded whole. |
| T13 | Optical source: `soc_007` 25 cm ortho (tiled, LZW), reprojected to the DTM grid. Mars Trek WMTS is the fallback. | Tiled files make windowed reads fast. The `soc_006` equirectangular version is uncompressed strips (slow). |
| T14 | Depot markers come from the PDS `sample_tube_locations.csv`, labeled **"rover position at drop"** unless Phase 1 finds true tube positions in the bundle. | The CSV gives the rover's location, not the tube's. Labeling it avoids overstating accuracy (rule 1). |
| T15 | DONKI SEP events are labeled **"proxy (near-Earth detection)"** and used only for the SEP-alert replay. | They are not measured at Mars. |
| T16 | **Local metric grid**: equirectangular with its standard parallel at the depot (18.4528 N). Origin at the AOI's SW corner, x east, y north, in metres. | The source DTM uses standard parallel 0. At 18.45 N its east-west metres are only 0.949 ground metres, which would bias slopes. The local grid has true scale (test: < 0.03 %). It also matches Leaflet `L.CRS.Simple`. |
| T17 | **AOI** = 4 km x 4 km, x from -2 to +2 km and y from -1.7 to +2.3 km around the depot. | Holds the depot, the delta front, the rover's delta-top climb (sols 708-760) and flat crater floor to the east (start-site candidates). |
| T18 | **Grids**: DTM at 1 m (roughness), analysis at 2 m, browser cost grid at 10 m (400 x 400). | 2 m keeps slope detail and stays fast. 10 m keeps browser A* small. Speed is measured in Phase 3. |
| T19 | **Slope** by Horn (1981) 3 x 3. **Roughness** = detrended RMS relief in a 5 m window on the 1 m DTM. | Horn is the GDAL default and well known. The roughness measure is zero on any plane, so it is not just slope again (both are tested). |
| T20 | **No-go placeholders**: slope 20 deg, roughness 0.2 m (was 0.5 m). Both are labeled "assumption" and will be sliders. | No NASA source verified yet (Phase 2). At 0.5 m, roughness flagged only 0.004 % of cells. At 0.2 m it flags 0.095 %, and 84 % of those cells are also too steep. Roughness from a 1 m DTM sees scarps, not rocks, so in Phase 2 it acts mainly as a soft penalty. |
| T21 | **Browser grid aggregation**: each 10 m cell keeps the 90th-percentile slope and roughness of its 25 cells at 2 m. | Conservative: a cell that is partly steep counts as steep. Measured no-go share: 3.50 % at 2 m and 5.14 % at 10 m. |
| T22 | **Ortho**: 25 cm averaged to 1 m (4 x 4 block mean) for the base map, JPEG, 2.6 MB. The depot close-up stays at 25 cm. | The mosaic has no built-in overviews. 25 cm across 4 km would be 256 Mpx, far too big for the site. |
| T23 | **THEMIS**: Mars Trek WMTS zoom 9 (~81 m/px), both day and night IR, labeled **proxy, qualitative**. | The primary source works. One tile covers the AOI. It is uncalibrated brightness, so it can't be read as temperature. |
| T24 | **Rover photos**: one per rover site in the AOI. Filter: full frame, colour Mastcam-Z first, then Navcam, looking at the ground ahead (mast elevation -20 to +3 deg). Stop cards in Phase 2-3 pick from these. | The first, unfiltered pick took thumbnails and sky shots (4-15 KB files). The filter is deterministic and logged. |
| T25 | **Credits** come from the USGS FGDC metadata (`.xml` next to each `.tif`): Fergason, Galuszka & Hare 2020 + DOIs. | The astrogeology.usgs.gov product pages are JavaScript-only and return no text to scripts. The `.xml` metadata is the official record. |
| T26 | **The rover-vs-DTM elevation match (RMS 0.06 m) is reported as a georeferencing check, not an accuracy check.** | Rover positions are most likely localised on the same orbital data (inference, not checked), so the match is not independent. The independent check is the CTX DTM (std 3.9 m). |
