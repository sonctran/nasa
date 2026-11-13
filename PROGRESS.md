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
_(filled in below)_

### Known issues / risks
1. **Space Apps rules on early work: not verified.** Phase 0 (setup + planning) happens Friday, before the window opens Sat 9:00 a.m. I couldn't confirm whether the rules allow building before the event starts. **Son: please check the official rules / your local event.** The plan below starts real building (Phase 1) at Sat 9:00 a.m. to be safe.
2. **Windows not tested here.** Claude Code runs in a Linux cloud container. Son should run the 3 README commands once on his PC to confirm `pytest` passes on Windows.
3. **Cloud container is temporary.** Anything not committed and pushed is lost when the session ends. Raw data must be re-downloadable by `pipeline/download.py`.

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
