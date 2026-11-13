# PROGRESS

## Current status: Phase 0 (setup + plan): done, waiting for Son's plan approval

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
1. **Space Apps rules on early work: not verified.** Phase 0 (setup + planning) happens Friday, before the window opens Sat 9:00 a.m. I couldn't confirm whether the rules allow building before the event starts. **Son: please check the official rules / your local event.** The plan below starts real building (Phase 1) at Sat 9:00 a.m. to be safe.
2. **Windows not tested here.** Claude Code runs in a Linux cloud container. Son should run the 3 README commands once on his PC to confirm `pytest` passes on Windows.
3. **Cloud container is temporary.** Anything not committed and pushed is lost when the session ends. Raw data must be re-downloadable by `pipeline/download.py`.
4. **GitHub push blocked (403).** Claude has no write access to `sonctran/nasa`. It failed twice, so I stopped. Fix: Son reconnects GitHub at https://claude.ai/connect-github and, if needed, installs the Claude GitHub App on the repo. Until then, commits exist only in this cloud session.
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

### Proposed cut order (needs Son's OK; it changes SPEC §10 to match his priorities)
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
Phase 1, after Son approves this plan.
