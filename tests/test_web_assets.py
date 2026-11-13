"""Exported web assets are self-consistent (skipped until the pipeline has been run)."""
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "assets" / "data"

pytestmark = pytest.mark.skipif(not (DATA / "cost_grid.json").exists(), reason="run python -m pipeline.run_all first")


def test_cost_grid_binary_matches_its_header():
    meta = json.loads((DATA / "cost_grid.json").read_text(encoding="utf-8"))
    blob = (DATA / "cost_grid.bin").read_bytes()
    assert len(blob) == meta["bytes"]
    n = meta["rows"] * meta["cols"]
    sizes = {"float32": 4, "uint16": 2, "uint8": 1}
    end = 0
    for a in meta["arrays"]:
        assert a["count"] == n and a["offset"] == end
        end += n * sizes[a["dtype"]]
    assert end == len(blob)
    elev = np.frombuffer(blob, dtype="<f4", count=n)
    assert np.isfinite(elev).all() and -3000 < elev.min() < elev.max() < -2000  # Jezero floor/delta, metres


def test_every_layer_file_exists_and_bounds_cover_the_aoi():
    man = json.loads((DATA / "layers.json").read_text(encoding="utf-8"))
    w, h = man["aoi"]["size_m"]
    for layer in man["layers"]:
        assert (ROOT / "site" / "assets" / layer["file"]).exists(), layer["id"]
        assert layer["bounds"] == [[0.0, 0.0], [h, w]]
        assert layer["kind"] in {"real", "derived", "assumption", "proxy"}
        assert layer["credit"]


def test_site_assets_stay_small():
    total = sum(f.stat().st_size for f in (ROOT / "site").rglob("*") if f.is_file())
    assert total < 40e6                                                      # SPEC rule 7
    assert max(f.stat().st_size for f in (ROOT / "site").rglob("*") if f.is_file()) < 50e6


def test_site_params_match_config():
    """site/assets/data/params.json (read by the browser engine) must equal config/params.yaml."""
    from pipeline.common import load_params

    assert json.loads((DATA / "params.json").read_text(encoding="utf-8")) == load_params(), \
        "run python -m planner.export_site"
