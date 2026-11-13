# Marswalk Ops

**A decision-support tool that plans a safe, efficient two-astronaut Marswalk in Jezero Crater. It optimizes the route and the work schedule, measures the risk, and shows the trade-offs.**

NASA Space Apps Challenge 2026 · Challenge: *Interplanetary Survival Guide: Martian Map* · Team: Marswalk Ops (Son Tran)

> Status: **Phase 0 (setup + plan).** Nothing is built yet. See `PROGRESS.md` for the plan and `SPEC.md` for the full build spec.

## Run it locally (Windows PowerShell)

Needs **Python 3.12, 3.13 or 3.14** (64-bit). Python 3.11 will not work (see `DECISIONS.md`).

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest
```

(Change `3.12` to the version you have. Run `py --list` to see installed versions.)

## Data credits

Filled in during Phase 1. Every source will be listed in `docs/DATA_SOURCES.md`. NASA imagery will carry credit lines such as "Image: NASA/JPL-Caltech".

## Use of AI

This project uses AI tools, and says so openly:
- **Ideation:** Claude (Anthropic) suggested concept upgrades. Son Tran chose which to keep.
- **Code generation:** most code is written with Claude Code, then reviewed and tested.
- **Research and writing:** Claude Code helped find and check data sources and draft docs.

Any AI-generated image will carry a visible "AI-generated" watermark. The app prefers real NASA imagery and real screenshots.

## License

MIT. See `LICENSE`.
