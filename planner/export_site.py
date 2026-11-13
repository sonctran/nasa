"""Copy what the web app needs from config/ and docs/ into site/ (no build step in the browser).

Writes
  site/assets/data/params.json   every parameter of config/params.yaml, with its unit, source and note
                                 (the browser engine reads its model numbers from here, and the
                                 Methods page renders the assumptions table from it)
  site/assets/data/roles.json    crew roles per task (config/stops.yaml, labelled assumption there)
  site/assets/docs/*.md          METHODS, ASSUMPTIONS, DATA_SOURCES (rendered by methods.html)

Run: python -m planner.export_site   (run_plan also calls it)
"""
from __future__ import annotations

import json
import shutil

import yaml

from pipeline.common import ROOT, load_params

SITE = ROOT / "site"
DOCS = ("METHODS.md", "ASSUMPTIONS.md", "DATA_SOURCES.md")


def main() -> None:
    p = load_params()
    out = SITE / "assets" / "data" / "params.json"
    out.write_text(json.dumps(p, indent=1, ensure_ascii=False), encoding="utf-8")
    roles = yaml.safe_load((ROOT / "config" / "stops.yaml").read_text(encoding="utf-8"))["roles"]
    (SITE / "assets" / "data" / "roles.json").write_text(json.dumps(roles, indent=1), encoding="utf-8")
    ddir = SITE / "assets" / "docs"
    ddir.mkdir(parents=True, exist_ok=True)
    for name in DOCS:
        shutil.copyfile(ROOT / "docs" / name, ddir / name)
    print(f"wrote {out.relative_to(ROOT)} and {len(DOCS)} docs in {ddir.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
