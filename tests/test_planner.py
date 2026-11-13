"""End-to-end checks on the real Jezero grid and on the exported results (site/assets/data/plan.json)."""
import json
import math
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "site" / "assets" / "data" / "plan.json"
needs_plan = pytest.mark.skipif(not PLAN.exists(), reason="run python -m planner.run_plan first")


@pytest.fixture(scope="module")
def plan():
    return json.loads(PLAN.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def world():
    from pipeline.common import load_params
    from planner.run_plan import World

    return World(load_params())


def test_astar_equals_dijkstra_on_the_real_grid(world):
    from planner.astar import astar, dijkstra_tree

    rng = np.random.default_rng(7)
    w = world.weights((0.3333, 0.3333, 0.3334, 0.0))
    cs = world.csgraph("test_balanced", (0.3333, 0.3333, 0.3334, 0.0))
    cells = np.flatnonzero(world.ok.ravel())
    src = int(rng.choice(cells))
    dist, _ = dijkstra_tree(cs, [src])
    for g in rng.choice(cells, 6, replace=False):
        cost, path, _ = astar(world.edges, w, src, int(g), world.t.cell)
        if math.isinf(dist[0, g]):
            assert math.isinf(cost)
        else:
            assert cost == pytest.approx(dist[0, g], rel=1e-12)
            assert max(world.t.slope.flat[path]) <= world.slope_nogo     # never through a too-steep cell


@needs_plan
def test_go_no_go_and_robust_target(plan):
    assert plan["checklist"]["go"] is True
    assert plan["montecarlo"]["runs"] >= 2000                            # SPEC 6.7
    assert plan["montecarlo"]["p_success"] >= plan["params_used"]["schedule.robust_p_on_time"]
    assert plan["validation"]["astar_vs_dijkstra"]["max_rel_diff"] < 1e-9


@needs_plan
def test_timeline_is_continuous_and_adds_up(plan):
    rows = plan["plan"]["timeline"]
    assert rows[0]["t0_min"] == 0
    for a, b in zip(rows[:-1], rows[1:]):
        assert b["t0_min"] == pytest.approx(a["t1_min"], abs=1e-9)
    assert rows[-1]["t1_min"] == pytest.approx(plan["plan"]["totals"]["duration_min"], rel=1e-9)
    assert rows[-1]["t1_min"] <= plan["params_used"]["mission.eva_time_limit"] * 60
    assert sum(r["o2_kg"] for r in rows) == pytest.approx(plan["safety"]["consumables"]["o2_used_kg"], rel=1e-9)
    # buddy rule: EV1 and EV2 share every row (same route, same clock)
    assert all(r["EV1"] and r["EV2"] for r in rows)


@needs_plan
def test_route_joins_the_sites_in_order(plan):
    sites = {s["id"]: s for s in plan["sites"]}
    order = plan["plan"]["order"]
    assert order[0] == order[-1] == "habitat" and "depot" in order
    for (a, b), xy in zip(zip(order[:-1], order[1:]), plan["plan"]["legs_xy"]):
        assert xy[0] == pytest.approx(sites[a]["cell_xy"], abs=0.05)
        assert xy[-1] == pytest.approx(sites[b]["cell_xy"], abs=0.05)
    assert plan["plan"]["totals"]["max_slope_deg"] <= plan["params_used"]["terrain.slope_nogo_deg"]


@needs_plan
def test_every_stop_is_sourced_and_scored_by_the_rubric(plan):
    params = yaml.safe_load((ROOT / "config" / "params.yaml").read_text(encoding="utf-8"))
    for s in plan["sites"]:
        if s["kind"] != "stop":
            continue
        assert s["source"] and s["quote"] and s["position_source"]
        assert s["value"] == params["science_value"][s["category"]]["value"]
        assert s["snap_m"] < 15                                        # site sits on (or next to) a safe cell
    # PDS core sites land on our 1 m DTM within half a metre of the published elevation (georeferencing
    # check; the 10 m planning-cell mean can differ by metres on a scarp, so it is not used here)
    checked = [s for s in plan["sites"] if "elev_pds_m" in s and "elev_dtm1m_m" in s]
    assert len(checked) >= 4
    for s in checked:
        assert abs(s["elev_dtm1m_m"] - s["elev_pds_m"]) < 0.5, s["id"]


@needs_plan
def test_alternatives_and_pareto(plan):
    alts = {a["id"]: a for a in plan["alternatives"]}
    assert {"fastest", "lowest_energy", "safest", "balanced", "shortest"} <= set(alts)
    assert alts["fastest"]["walk_min"] <= min(a["walk_min"] for a in alts.values()) + 1e-6
    assert alts["safest"]["hazard_min"] <= min(a["hazard_min"] for a in alts.values()) + 1e-6
    assert alts["shortest"]["dist_m"] <= min(a["dist_m"] for a in alts.values()) + 0.5
    assert any(p["pareto"] for p in plan["pareto"])


@needs_plan
def test_plan_json_is_small():
    assert PLAN.stat().st_size < 2_000_000
