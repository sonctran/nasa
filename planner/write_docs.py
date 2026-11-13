"""Write docs/ASSUMPTIONS.md straight from config/params.yaml, so the doc always matches the code.

Run: python -m planner.write_docs   (run_plan also calls it)
"""
from __future__ import annotations

from pipeline.common import CONFIG, ROOT, load_params

OUT = ROOT / "docs" / "ASSUMPTIONS.md"

INTRO = """# Assumptions and parameters

**This file is generated from `config/params.yaml` by `python -m planner.write_docs`. Do not edit it by hand.**

Every number the planner uses is listed here, in one of three groups:

1. **Assumption**: a value we chose because no source could be verified. The app labels results that depend on these as **"assumption"** or **"modeled"**.
2. **Owner-set**: a mission-design choice made by Son (the project owner), not a fact about Mars.
3. **Sourced**: a value read from a NASA/USGS/PDS document. The source column quotes where it came from. Some sourced values are lunar or Gale-crater numbers applied to Jezero: their notes say so, and the app labels them **"proxy"** where that applies.

Tobler (1993) and Minetti et al. (2002) were blocked for automated access and were read from PDFs supplied by Son (2026-11-13). The dose-equivalent numbers of Hassler et al. (2014) could not be read and are **not used**. See DECISIONS T27.
"""


def _leaves(node, path=()):
    if isinstance(node, dict) and "value" in node:
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _leaves(v, path + (k,))


def _cell(x) -> str:
    s = str(x).replace("|", "/").replace("\n", " ")
    return s


def build() -> str:
    p = load_params()
    groups = {"assumption": [], "owner-set": [], "sourced": []}
    for path, e in _leaves(p):
        src = str(e["source_or_assumption"]).strip()
        low = src.lower()
        g = "assumption" if low.startswith("assumption") else "owner-set" if low.startswith("owner-set") else "sourced"
        groups[g].append((".".join(path), e))
    out = [INTRO]
    titles = {"assumption": "1. Assumptions (no verified source)", "owner-set": "2. Owner-set mission choices",
              "sourced": "3. Sourced values"}
    for g in ("assumption", "owner-set", "sourced"):
        out.append(f"\n## {titles[g]} ({len(groups[g])})\n")
        if g == "sourced":
            out.append("| Parameter | Value | Unit | Source | Note |\n|---|---|---|---|---|")
            for name, e in groups[g]:
                out.append(f"| `{name}` | {_cell(e['value'])} | {_cell(e['unit'])} | {_cell(e['source_or_assumption'])} | {_cell(e['note'])} |")
        else:
            out.append("| Parameter | Value | Unit | Reason / note |\n|---|---|---|---|")
            for name, e in groups[g]:
                extra = "" if str(e["source_or_assumption"]).strip().lower() in ("assumption", "owner-set") else \
                    f" ({_cell(e['source_or_assumption'])})"
                out.append(f"| `{name}` | {_cell(e['value'])} | {_cell(e['unit'])} | {_cell(e['note'])}{extra} |")
    out.append(f"\nSource file: `{CONFIG.relative_to(ROOT).as_posix()}`. Science-stop sites and their quotes: `config/stops.yaml`.\n")
    return "\n".join(out)


def main() -> None:
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
