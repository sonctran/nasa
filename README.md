# Marswalk Ops

**A decision-support tool that plans a safe, efficient two-astronaut Marswalk in Jezero Crater. It optimizes the route and the work schedule, measures the risk, and shows the trade-offs.**

NASA Space Apps Challenge 2026 · Challenge: *Interplanetary Survival Guide: Martian Map* · Team: Marswalk Ops (Son Tran)

> Status: **Phase 1 (data pipeline) done.** Real NASA/USGS data is processed into map layers. The planner and the app come next. See `PROGRESS.md`.

## Run it locally (Windows PowerShell)

Needs **Python 3.12, 3.13 or 3.14** (64-bit). Python 3.11 will not work (see `DECISIONS.md`).

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest
```

(Change `3.12` to the version you have. Run `py --list` to see installed versions.)

Rebuild all the map data from NASA/USGS sources (about 3 minutes, needs internet, about 55 MB in `data\raw`):

```powershell
.\.venv\Scripts\python.exe -m pipeline.run_all
```

Preview images of every layer are saved in `data\processed\previews\`.

## Data credits

Full list with exact URLs: `docs/DATA_SOURCES.md`.
- HiRISE DTM and orthomosaic: Fergason, Galuszka & Hare 2020, USGS Astrogeology (doi:10.5066/P9REJ9JN, doi:10.5066/P9QJDP48). HiRISE data: NASA/JPL-Caltech/University of Arizona.
- CTX DTM (cross-check): USGS (doi:10.5066/P906QQT8). CTX data: NASA/JPL-Caltech/MSSS.
- THEMIS IR: NASA/JPL-Caltech/Arizona State University, via NASA Mars Trek.
- Perseverance traverse, waypoints and raw images: NASA/JPL-Caltech (Mastcam-Z: NASA/JPL-Caltech/ASU).
- Three Forks depot data: NASA PDS Geosciences Node.
- Solar particle events: NASA CCMC DONKI.

## Use of AI

This project uses AI tools, and says so openly:
- **Ideation:** Claude (Anthropic) suggested concept upgrades. Son Tran chose which to keep.
- **Code generation:** most code is written with Claude Code, then reviewed and tested.
- **Research and writing:** Claude Code helped find and check data sources and draft docs.

Any AI-generated image will carry a visible "AI-generated" watermark. The app prefers real NASA imagery and real screenshots.

## License

MIT. See `LICENSE`.
