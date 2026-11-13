"""The browser engine (site/js/engine.js, run in Node) must give the SAME answers as the Python planner.

SPEC 6.3: "Python and JS must return the same route cost on a fixture grid."
  1. Random fixture grids (nodata, steep and rough cells, every weight profile): A* cost equal to
     within 1e-12 relative, and the same path cell for cell.
  2. The real 10 m Jezero grid, the plan-of-record legs: equal to Python A* and to the costs in plan.json.
  3. Whole-plan evaluation in JS (timeline, walkback, SEP, consumables) matches plan.json; the JS
     Monte Carlo (different random generator) agrees within sampling noise.
Skipped when Node.js is not installed (it is only needed for this test, not to use the app).
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from pipeline.common import load_params
from planner.astar import astar, min_cost_per_metre
from planner.cost import HumanModel, edge_costs, hazard_index, pv, scalar_weight
from planner.grid import Terrain, build_edges, passable_mask

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "js" / "parity.mjs"
DATA = ROOT / "site" / "assets" / "data"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js not installed (only needed for the JS parity test)")

PROFILES = ["fastest", "safest", "balanced", "shortest"]


def run_node(fixture: dict, tmp_path: Path) -> dict:
    f = tmp_path / "fixture.json"
    f.write_text(json.dumps(fixture), encoding="utf-8")
    r = subprocess.run([NODE, str(RUNNER), str(f)], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def py_world(t: Terrain, p: dict):
    sn, rn = pv(p, "terrain.slope_nogo_deg"), pv(p, "terrain.roughness_nogo_m")
    hz = hazard_index(t, pv(p, "hazard.slope_caution_deg"), sn, pv(p, "hazard.roughness_caution_m"), rn)
    ok = passable_mask(t, sn, rn)
    edges = build_edges(t, ok, hz, math.tan(math.radians(sn)))
    ec = edge_costs(edges, HumanModel.from_params(p))
    return ok, edges, ec


def random_terrain(seed: int, rows: int = 28, cols: int = 34) -> Terrain:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:rows, 0:cols]
    elev = -2550 + 3.0 * np.sin(xx / 4.0 + seed) + 2.0 * np.cos(yy / 3.0) + rng.normal(0, 0.6, (rows, cols))
    slope = np.round(rng.gamma(2.0, 4.5, (rows, cols)), 2)
    rough = np.round(rng.gamma(2.0, 0.03, (rows, cols)), 3)
    nodata = rng.random((rows, cols)) < 0.03
    return Terrain(elev=elev, slope=slope, rough=rough, nodata=nodata, cell=10.0)


def test_random_fixture_grids_python_equals_js(tmp_path):
    p = load_params()
    cases, expected = [], []
    for seed in range(8):
        t = random_terrain(seed)
        ok, edges, ec = py_world(t, p)
        rng = np.random.default_rng(100 + seed)
        cells = np.flatnonzero(ok)
        qs, exp = [], []
        for prof in PROFILES:
            w = pv(p, f"route_options.{prof}")
            wt = scalar_weight(ec, *w)
            cmin = min_cost_per_metre(edges, wt)
            for _ in range(3):
                a, b = (int(v) for v in rng.choice(cells, 2, replace=False))
                cost, path, _ = astar(edges, wt, a, b, t.cell, cmin)
                qs.append({"start": a, "goal": b, "w": w})
                exp.append((cost, path, cmin))
        cases.append({"grid": {"rows": t.shape[0], "cols": t.shape[1], "cell": t.cell, "elev": t.elev.ravel().tolist(),
                               "slope": t.slope.ravel().tolist(), "rough": t.rough.ravel().tolist(),
                               "nodata": t.nodata.ravel().astype(int).tolist()}, "queries": qs})
        expected.append((int(edges.ok.sum()), int(ok.sum()), exp))
    out = run_node({"params": p, "cases": cases}, tmp_path)
    n_q = n_unreach = 0
    for res, (n_edges, n_pass, exp) in zip(out["cases"], expected):
        assert res["edges"] == n_edges and res["passable"] == n_pass
        for q, (cost, path, cmin) in zip(res["queries"], exp):
            n_q += 1
            assert q["c_min"] == pytest.approx(cmin, rel=1e-15)
            if not math.isfinite(cost):
                n_unreach += 1
                assert q["cost"] is None and q["path"] == []
                continue
            assert q["cost"] == pytest.approx(cost, rel=1e-12, abs=1e-9)
            assert q["path"] == path
    assert n_q == 8 * len(PROFILES) * 3
    assert n_unreach < n_q // 4            # the fixtures must mostly test real routes


@pytest.fixture(scope="module")
def plan():
    return json.loads((DATA / "plan.json").read_text(encoding="utf-8"))


def test_real_grid_plan_legs_python_equals_js(tmp_path, plan):
    from planner.grid import load_terrain

    p = load_params()
    t = load_terrain()
    ok, edges, ec = py_world(t, p)
    w = pv(p, "route_options.balanced")
    wt = scalar_weight(ec, *w)
    cmin = min_cost_per_metre(edges, wt)
    sites = {s["id"]: s for s in plan["sites"]}
    order = plan["plan"]["order"]
    idx = [t.idx(*t.xy_to_rc(*sites[k]["cell_xy"])) for k in order]
    qs, exp = [], []
    for a, b in zip(idx[:-1], idx[1:]):
        cost, path, _ = astar(edges, wt, a, b, t.cell, cmin)
        qs.append({"start": a, "goal": b, "w": w})
        exp.append((cost, path))
    out = run_node({"cases": [{"grid": "real", "queries": qs}]}, tmp_path)
    res = out["cases"][0]
    assert res["edges"] == plan["grid"]["edges"] == int(edges.ok.sum())
    recorded = plan["validation"]["astar_vs_dijkstra"]["legs"]
    for q, (cost, path), rec in zip(res["queries"], exp, recorded):
        assert q["cost"] == pytest.approx(cost, rel=1e-12)
        assert q["cost"] == pytest.approx(rec["dijkstra_cost"], rel=1e-12)
        assert q["path"] == path
        assert q["ms"] < 1000                                  # SPEC 7: browser A* under 1 s


def test_js_plan_evaluation_matches_plan_json(tmp_path, plan):
    p = load_params()
    roles = json.loads((DATA / "roles.json").read_text(encoding="utf-8"))
    ids = [s["id"] for s in plan["sites"]]
    order = [ids.index(k) for k in plan["plan"]["order"]]
    case = {"grid": "real", "queries": [],
            "plan": {"sites": plan["sites"], "order": order, "w": pv(p, "route_options.balanced"), "roles": roles}}
    out = run_node({"cases": [case]}, tmp_path)
    js = out["cases"][0]["plan"]
    py = plan["plan"]["totals"]
    for k in ("duration_min", "walk_min", "work_min", "dist_m", "walk_energy_kcal", "o2_kg", "hazard_min",
              "caution_min", "max_slope_deg", "gain_m"):
        assert js["totals"][k] == pytest.approx(py[k], rel=1e-9, abs=1e-9), k
    s, ps = js["safety"], plan["safety"]
    assert s["walkback"]["min_time_margin_min"] == pytest.approx(ps["walkback"]["min_time_margin_min"], abs=0.05)
    assert s["walkback"]["min_o2_margin_pct_of_capacity"] == pytest.approx(ps["walkback"]["min_o2_margin_pct_of_capacity"], abs=0.05)
    assert s["sep"]["max_walk_home_min"] == pytest.approx(ps["sep"]["max_walk_home_min"], abs=0.05)
    assert s["sep"]["violating_points"] == ps["sep"]["violating_points"]
    assert s["consumables"]["o2_left_pct"] == pytest.approx(ps["consumables"]["o2_left_pct"], abs=1e-6)
    assert s["consumables"]["battery_left_pct"] == pytest.approx(ps["consumables"]["battery_left_pct"], abs=1e-6)
    assert s["dose"]["background_ugy"] == pytest.approx(ps["dose"]["background_ugy"], rel=1e-9)
    assert js["rows"] == len(plan["plan"]["timeline"])
    assert js["burn_last_o2"] == pytest.approx(plan["plan"]["burn_down"]["o2_pct"][-1], abs=0.01)
    # Monte Carlo: same model, different random numbers -> within 4 standard errors
    se = math.sqrt(plan["montecarlo"]["p_success"] * (1 - plan["montecarlo"]["p_success"]) / plan["montecarlo"]["runs"])
    assert abs(js["mc"]["p_success"] - plan["montecarlo"]["p_success"]) < 4 * math.sqrt(2) * se
    assert js["mc"]["p50"] == pytest.approx(plan["montecarlo"]["duration_min"]["p50"], abs=1.5)
    # live re-plan answers in well under 1 s and keeps the depot
    assert js["replan"]["depot_kept"]
    assert js["ms"]["replan"] < 1000
