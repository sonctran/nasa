"""Phase 2 planning engine: one command builds every result the web app shows.

Run:  python -m planner.run_plan
Out:  site/assets/data/plan.json        (committed; read by the web app)
      data/processed/plan_full.json     (local; full-resolution, for checks)
      data/processed/previews/2*_*.png  (pictures for Son)

Steps
 1. Terrain, hazard index, no-go mask and the 16-connected edge graph (10 m browser grid).
 2. Habitat site, depot and science stops (real Perseverance sample sites, config/stops.yaml).
 3. Leg matrix between all sites for each route option (Dijkstra; A* cross-checked).
 4. Stop scheduling (OR-Tools CP-SAT) for several time budgets; Monte Carlo on each;
    Robust plan = most science with P(home on time) >= 95 %.
 5. Route alternatives + Pareto sweep for the plan's stop order.
 6. Safety: walkback field, SEP shelter reach, consumables burn-down, dose, go/no-go.
 7. Validation: planned routes vs Perseverance's real drives; walking model vs Apollo 14.
"""
from __future__ import annotations

import csv
import itertools
import json
import math
import time
from pathlib import Path

import numpy as np
import yaml

from pipeline.common import PREVIEWS, PROCESSED, ROOT, SITE_DATA, grid_from_params, load_params

from . import validate
from .astar import astar, dijkstra_tree, min_cost_per_metre, path_edges, tree_path
from .cost import HumanModel, edge_costs, hazard_index, pv, scalar_weight
from .grid import build_edges, load_terrain, passable_mask, to_csgraph
from .montecarlo import PlanProfile, simulate, summarise, tornado
from .safety import checklist, o2_kg, walkback_field
from .stops_ortools import Instance, evaluate, solve_ortools

STOPS_FILE = ROOT / "config" / "stops.yaml"
APOLLO_FILE = ROOT / "config" / "apollo14_table4.csv"
PROFILE_NAMES = {"fastest": "Fastest", "lowest_energy": "Lowest-energy", "safest": "Safest", "balanced": "Balanced",
                 "shortest": "Shortest distance"}


# ----------------------------------------------------------------------------------------
class World:
    """Terrain + graph + cost model for one set of parameters."""

    def __init__(self, params: dict):
        self.p = params
        self.t = load_terrain()
        self.slope_nogo = pv(params, "terrain.slope_nogo_deg")
        self.rough_nogo = pv(params, "terrain.roughness_nogo_m")
        self.hz = hazard_index(self.t, pv(params, "hazard.slope_caution_deg"), self.slope_nogo,
                               pv(params, "hazard.roughness_caution_m"), self.rough_nogo)
        self.ok = passable_mask(self.t, self.slope_nogo, self.rough_nogo)
        self.edges = build_edges(self.t, self.ok, self.hz, math.tan(math.radians(self.slope_nogo)))
        self.hm = HumanModel.from_params(params)
        self.ec = edge_costs(self.edges, self.hm)
        self.o2_per_j = pv(params, "consumables.o2_kg_per_mj") / 1e6
        self._cs = {}

    def weights(self, w):
        return scalar_weight(self.ec, *w)

    def csgraph(self, key, w):
        if key not in self._cs:
            self._cs[key] = to_csgraph(self.edges, self.weights(w))
        return self._cs[key]

    def leg(self, path: list[int]) -> dict:
        """Totals and geometry of a path (list of flat cell indices)."""
        t, ec = self.t, self.ec
        if len(path) < 2:
            x, y = t.xy_of_idx(path[0])
            return {"time_s": 0.0, "energy_j": 0.0, "hazard_s": 0.0, "caution_s": 0.0, "dist_m": 0.0,
                    "max_slope_deg": float(t.slope.flat[path[0]]), "max_grade_deg": 0.0, "gain_m": 0.0,
                    "loss_m": 0.0, "path": path, "xy": [[x, y]], "cum_time_s": [0.0], "cum_energy_j": [0.0]}
        steps = path_edges(self.edges, path)
        ks = np.array([k for _, k in steps])
        rr, cc = np.divmod(np.array([a for a, _ in steps]), t.shape[1])
        tt = ec.time_s[ks, rr, cc]
        ee = ec.energy_j[ks, rr, cc]
        dz = self.edges.dz[ks, rr, cc]
        cells = np.array(path)
        xs, ys = t.rc_to_xy(*np.divmod(cells, t.shape[1]))
        return {
            "time_s": float(tt.sum()), "energy_j": float(ee.sum()),
            "hazard_s": float(ec.hazard_s[ks, rr, cc].sum()), "caution_s": float(ec.caution_s[ks, rr, cc].sum()),
            "dist_m": float(ec.length_m[ks, rr, cc].sum()),
            "max_slope_deg": float(t.slope.flat[cells].max()),
            "max_grade_deg": float(np.degrees(np.arctan(np.abs(ec.grade[ks, rr, cc]).max()))),
            "gain_m": float(dz[dz > 0].sum()), "loss_m": float(-dz[dz < 0].sum()),
            "path": [int(i) for i in path], "xy": np.column_stack([xs, ys]).tolist(),
            "cum_time_s": np.r_[0, np.cumsum(tt)].tolist(), "cum_energy_j": np.r_[0, np.cumsum(ee)].tolist(),
        }


def snap(world: World, x: float, y: float, reach: np.ndarray) -> tuple[int, float]:
    """Nearest passable cell reachable from the habitat (exact cell if already fine)."""
    t = world.t
    r, c = t.xy_to_rc(x, y)
    i = t.idx(r, c)
    if reach.flat[i]:
        return i, float(np.hypot(*(np.array(t.xy_of_idx(i)) - (x, y))))
    rr, cc = np.nonzero(reach)
    X, Y = t.rc_to_xy(rr, cc)
    j = int(np.argmin((X - x) ** 2 + (Y - y) ** 2))
    i = t.idx(int(rr[j]), int(cc[j]))
    return i, float(np.hypot(X[j] - x, Y[j] - y))


def choose_habitat(world: World, depot_xy) -> dict:
    from scipy import ndimage

    p, t = world.p, world.t
    lo, hi = pv(p, "habitat.distance_from_depot_m")
    size = int(round(pv(p, "habitat.pad_size_m") / t.cell)) | 1
    pad_max = ndimage.maximum_filter(np.where(world.ok, t.slope, 90.0), size=size, mode="nearest")
    rr, cc = np.mgrid[0:t.shape[0], 0:t.shape[1]]
    X, Y = t.rc_to_xy(rr, cc)
    d = np.hypot(X - depot_xy[0], Y - depot_xy[1])
    cand = (d >= lo) & (d <= hi) & (X > depot_xy[0]) & world.ok
    order = np.lexsort((np.abs(d - (lo + hi) / 2)[cand], pad_max[cand]))
    k = order[0]
    r, c = int(rr[cand][k]), int(cc[cand][k])
    x, y = t.rc_to_xy(r, c)
    return {"idx": t.idx(r, c), "x": float(x), "y": float(y), "pad_max_slope_deg": float(pad_max[r, c]),
            "dist_to_depot_m": float(d[r, c]), "candidates": int(cand.sum())}


# ----------------------------------------------------------------------------------------
def build_sites(world: World, params: dict) -> tuple[list[dict], dict]:
    grid = grid_from_params(params)
    cfg = yaml.safe_load(STOPS_FILE.read_text(encoding="utf-8"))
    vec = json.loads((SITE_DATA / "vectors.json").read_text(encoding="utf-8"))
    depot_xy = grid.lonlat_to_local(grid.anchor_lon, grid.anchor_lat)
    hab = choose_habitat(world, depot_xy)
    # cells reachable from the habitat (and back) on the safe graph
    cs = world.csgraph("fastest", pv(params, "route_options.fastest"))
    d_out, _ = dijkstra_tree(cs, [hab["idx"]])
    d_in, _ = dijkstra_tree(cs, [hab["idx"]], reverse=True)
    reach = (np.isfinite(d_out[0]) & np.isfinite(d_in[0])).reshape(world.t.shape)

    sites = [{"id": "habitat", "name": "Habitat", "kind": "habitat", "x": hab["x"], "y": hab["y"],
              "idx": hab["idx"], "snap_m": 0.0, "value": 0, "dwell_s": 0.0, "work_w": 0.0,
              "category": None, "position_source": "chosen by rule (DECISIONS T29)", **{k: hab[k] for k in ("pad_max_slope_deg", "dist_to_depot_m")}}]
    i, s = snap(world, *depot_xy, reach)
    sites.append({"id": "depot", "name": cfg["depot"]["name"], "kind": "depot", "x": depot_xy[0], "y": depot_xy[1],
                  "idx": i, "snap_m": s, "value": 0, "dwell_s": pv(params, "schedule.depot_pickup_min") * 60,
                  "work_w": pv(params, "work_metabolic_rate.depot_pickup_w"), "category": "depot",
                  "task": cfg["depot"]["task"], "position_source": cfg["depot"]["position_rule"],
                  "source": cfg["depot"]["source"]})
    for st in cfg["stops"]:
        if "lat" in st:
            x, y = grid.lonlat_to_local(st["lon"], st["lat"])
            pos = "core site lat/lon from the PDS Initial Report"
        else:
            wps = [w for w in vec["waypoints"]["points"] if w["sol"] <= st["waypoint_sol"]]
            w = max(wps, key=lambda w: (w["sol"], w["drive"]))
            x, y = w["x"], w["y"]
            pos = f"{st['position_rule']} -> waypoint {w['rmc']} (sol {w['sol']})"
        i, s = snap(world, x, y, reach)
        cat = st["category"]
        sites.append({"id": st["id"], "name": st["name"], "kind": "stop", "x": float(x), "y": float(y), "idx": i,
                      "snap_m": s, "category": cat, "value": int(pv(params, f"science_value.{cat}")),
                      "dwell_s": pv(params, f"schedule.dwell_{cat}_min") * 60,
                      "work_w": pv(params, "work_metabolic_rate.science_stop_w"),
                      "samples": st["samples"], "quote": st["quote"], "source": st["source"],
                      "why_category": st["why_category"], "look_for": st["look_for"], "position_source": pos,
                      "elev_pds_m": st.get("elev_m")})
    dtm1 = _dtm_1m()
    for s_ in sites:
        s_["elev_m"] = float(world.t.elev.flat[s_["idx"]])          # 10 m cell mean (planning grid)
        s_["cell_xy"] = list(world.t.xy_of_idx(s_["idx"]))
        if dtm1 is not None:                                          # 1 m DTM at the exact point
            r = min(max(int((dtm1.shape[0] - s_["y"]) // 1.0), 0), dtm1.shape[0] - 1)
            c = min(max(int(s_["x"] // 1.0), 0), dtm1.shape[1] - 1)
            s_["elev_dtm1m_m"] = float(dtm1[r, c])
    return sites, {"habitat": hab, "roles": cfg["roles"], "reach_cells": int(reach.sum())}


def _dtm_1m():
    import rasterio

    f = PROCESSED / "dtm_1m.tif"
    if not f.exists():
        return None
    with rasterio.open(f) as s:
        return s.read(1)


def leg_matrix(world: World, sites: list[dict], key: str, w) -> list[list[dict]]:
    cs = world.csgraph(key, w)
    src = [s["idx"] for s in sites]
    dist, pred = dijkstra_tree(cs, src)
    n = len(sites)
    M = [[None] * n for _ in range(n)]
    for a in range(n):
        for b in range(n):
            if a == b:
                continue
            path = tree_path(pred[a], src[a], src[b])
            if not path:
                raise RuntimeError(f"no safe route {sites[a]['id']} -> {sites[b]['id']}")
            leg = world.leg(path)
            leg["cost"] = float(dist[a, src[b]])
            M[a][b] = leg
    return M


def tour_legs(M, order):
    return [M[a][b] for a, b in zip(order[:-1], order[1:])]


def totals(legs, sites, order, world: World) -> dict:
    walk_t = sum(l["time_s"] for l in legs)
    walk_e = sum(l["energy_j"] for l in legs)
    work_t = sum(sites[k]["dwell_s"] for k in order[1:-1])
    work_e = sum(sites[k]["dwell_s"] * sites[k]["work_w"] for k in order[1:-1])
    return {"walk_min": walk_t / 60, "work_min": work_t / 60, "duration_min": (walk_t + work_t) / 60,
            "dist_m": sum(l["dist_m"] for l in legs), "walk_energy_kcal": walk_e / 4184.0,
            "total_energy_kcal": (walk_e + work_e) / 4184.0, "o2_kg": (walk_e + work_e) * world.o2_per_j,
            "hazard_min": sum(l["hazard_s"] for l in legs) / 60,
            "caution_min": sum(l["caution_s"] for l in legs) / 60,
            "max_slope_deg": max(l["max_slope_deg"] for l in legs),
            "max_grade_deg": max(l["max_grade_deg"] for l in legs),
            "gain_m": sum(l["gain_m"] for l in legs)}


def make_instance(world: World, sites, M, budget_s, eligible) -> tuple[Instance, list[int]]:
    keep = [k for k in range(len(sites)) if k < 2 or eligible[k]]
    n = len(keep)
    tr = [[0.0 if a == b else M[keep[a]][keep[b]]["time_s"] for b in range(n)] for a in range(n)]
    ox = [[0.0 if a == b else M[keep[a]][keep[b]]["energy_j"] * world.o2_per_j for b in range(n)] for a in range(n)]
    p = world.p
    inst = Instance(names=[sites[k]["id"] for k in keep], travel_s=tr, o2_kg=ox,
                    dwell_s=[sites[k]["dwell_s"] for k in keep],
                    dwell_o2_kg=[sites[k]["dwell_s"] * sites[k]["work_w"] * world.o2_per_j for k in keep],
                    value=[sites[k]["value"] for k in keep], mandatory=[False, True] + [False] * (n - 2),
                    time_budget_s=budget_s,
                    o2_budget_kg=pv(p, "consumables.o2_capacity_kg") * (1 - pv(p, "consumables.o2_reserve_fraction")))
    return inst, keep


def profile_for(world: World, sites, legs, order, home_field) -> PlanProfile:
    pts_leg, pts_t, pts_o, back_t, back_o = [], [], [], [], []
    for k, leg in enumerate(legs):
        cells = np.array(leg["path"])
        pts_leg.append(np.full(cells.size, k))
        pts_t.append(np.array(leg["cum_time_s"]))
        pts_o.append(np.array(leg["cum_energy_j"]) * world.o2_per_j)
        back_t.append(home_field["time_s"].flat[cells])
        back_o.append(home_field["energy_j"].flat[cells] * world.o2_per_j)
    stops = order[1:-1]
    return PlanProfile(
        walk_s=np.array([l["time_s"] for l in legs]), walk_o2=np.array([l["energy_j"] for l in legs]) * world.o2_per_j,
        work_s=np.array([sites[k]["dwell_s"] for k in stops]),
        work_o2=np.array([sites[k]["dwell_s"] * sites[k]["work_w"] for k in stops]) * world.o2_per_j,
        pt_leg=np.concatenate(pts_leg), pt_walk_s=np.concatenate(pts_t), pt_walk_o2=np.concatenate(pts_o),
        pt_back_s=np.concatenate(back_t), pt_back_o2=np.concatenate(back_o))


def mc_kwargs(p):
    return dict(eva_limit_s=pv(p, "mission.eva_time_limit") * 3600, o2_capacity_kg=pv(p, "consumables.o2_capacity_kg"),
                o2_reserve_kg=pv(p, "consumables.o2_capacity_kg") * pv(p, "consumables.o2_reserve_fraction"))


def run_mc(p, prof, n=None, seed=None):
    return simulate(prof, n or pv(p, "montecarlo.runs"), pv(p, "montecarlo.speed_sigma"), pv(p, "montecarlo.metabolic_sigma"),
                    pv(p, "montecarlo.dwell_sigma"), seed=pv(p, "montecarlo.seed") if seed is None else seed, **mc_kwargs(p))


# ----------------------------------------------------------------------------------------
def timeline(world: World, sites, legs, order, roles) -> tuple[list[dict], dict]:
    """Gantt rows + 1-minute consumables burn-down for the plan of record."""
    p = world.p
    cap = pv(p, "consumables.o2_capacity_kg")
    bat = pv(p, "consumables.battery_capacity_wh")
    draw = pv(p, "consumables.battery_draw_w")
    rows, t0, o2 = [], 0.0, 0.0
    samples_t, samples_o2 = [0.0], [0.0]
    for k, leg in enumerate(legs):
        a, b = order[k], order[k + 1]
        ct = np.array(leg["cum_time_s"])
        co = np.array(leg["cum_energy_j"]) * world.o2_per_j
        rows.append({"kind": "walk", "from": sites[a]["id"], "to": sites[b]["id"], "t0_min": t0 / 60,
                     "t1_min": (t0 + leg["time_s"]) / 60, "dist_m": leg["dist_m"],
                     "energy_kcal": leg["energy_j"] / 4184, "o2_kg": leg["energy_j"] * world.o2_per_j,
                     "EV1": roles["walk"]["EV1"], "EV2": roles["walk"]["EV2"]})
        samples_t += list(t0 + ct[1:])
        samples_o2 += list(o2 + co[1:])
        t0 += leg["time_s"]
        o2 += leg["energy_j"] * world.o2_per_j
        if b != 0:
            s = sites[b]
            role = roles["depot" if s["kind"] == "depot" else s["category"]]
            w_o2 = s["dwell_s"] * s["work_w"] * world.o2_per_j
            rows.append({"kind": "work", "at": s["id"], "name": s["name"], "t0_min": t0 / 60,
                         "t1_min": (t0 + s["dwell_s"]) / 60, "energy_kcal": s["dwell_s"] * s["work_w"] / 4184,
                         "o2_kg": w_o2, "EV1": role["EV1"], "EV2": role["EV2"],
                         "task": s.get("task", f"Science stop ({s['category'].replace('_', ' ')})")})
            t0 += s["dwell_s"]
            o2 += w_o2
            samples_t.append(t0)
            samples_o2.append(o2)
    tm = np.arange(0, math.ceil(t0 / 60) + 1)
    o2_used = np.interp(tm * 60, samples_t, samples_o2)
    burn = {"t_min": tm.tolist(),
            "o2_pct": np.round(100 * (1 - o2_used / cap), 2).tolist(),
            "battery_pct": np.round(100 * (1 - draw * tm / 60 / bat), 2).tolist(),
            "o2_reserve_pct": 100 * pv(p, "consumables.o2_reserve_fraction"),
            "o2_capacity_kg": cap, "battery_capacity_wh": bat}
    return rows, burn


def safety_checks(world: World, sites, legs, order, home, prof: PlanProfile, rows) -> dict:
    p = world.p
    limit_s = pv(p, "mission.eva_time_limit") * 3600
    cap = pv(p, "consumables.o2_capacity_kg")
    reserve = cap * pv(p, "consumables.o2_reserve_fraction")
    shelter_s = pv(p, "sep.shelter_time_limit_min") * 60
    # elapsed time / O2 at every route point, planned (no randomness)
    leg_t0 = np.cumsum([0] + [prof.walk_s[k] + prof.work_s[k] for k in range(len(prof.work_s))])
    leg_o0 = np.cumsum([0] + [prof.walk_o2[k] + prof.work_o2[k] for k in range(len(prof.work_o2))])
    t_at = leg_t0[prof.pt_leg] + prof.pt_walk_s
    o_at = leg_o0[prof.pt_leg] + prof.pt_walk_o2
    time_margin = limit_s - (t_at + prof.pt_back_s)
    o2_margin = cap - reserve - (o_at + prof.pt_back_o2)
    cells = np.concatenate([np.array(l["path"]) for l in legs])
    xy = np.vstack([np.array(l["xy"]) for l in legs])
    k_t, k_o = int(np.argmin(time_margin)), int(np.argmin(o2_margin))
    sep_bad = prof.pt_back_s > shelter_s
    # SEP violation segments as runs of consecutive bad points
    segs, cur = [], []
    for ok_, pt in zip(sep_bad, xy):
        if ok_:
            cur.append([round(float(pt[0]), 1), round(float(pt[1]), 1)])
        elif cur:
            segs.append(cur)
            cur = []
    if cur:
        segs.append(cur)
    duration_s = rows[-1]["t1_min"] * 60
    o2_used = sum(r["o2_kg"] for r in rows)
    bat_used = pv(p, "consumables.battery_draw_w") * duration_s / 3600
    dose = pv(p, "sep.background_dose_rate_ugy_per_day") * duration_s / 86400
    return {
        "walkback": {
            "min_time_margin_min": float(time_margin[k_t] / 60), "at_time_xy": xy[k_t].round(1).tolist(),
            "at_time_elapsed_min": float(t_at[k_t] / 60), "at_time_walk_home_min": float(prof.pt_back_s[k_t] / 60),
            "min_o2_margin_kg": float(o2_margin[k_o]), "min_o2_margin_pct_of_capacity": float(100 * o2_margin[k_o] / cap),
            "at_o2_xy": xy[k_o].round(1).tolist(), "at_o2_elapsed_min": float(t_at[k_o] / 60),
            "at_o2_walk_home_min": float(prof.pt_back_s[k_o] / 60),
            "rule": "At every 10 m cell: O2 left - O2 to walk home >= reserve, and elapsed + walk-home time <= EVA limit",
        },
        "sep": {"shelter_limit_min": shelter_s / 60, "max_walk_home_min": float(prof.pt_back_s.max() / 60),
                "max_at_xy": xy[int(np.argmax(prof.pt_back_s))].round(1).tolist(),
                "violating_points": int(sep_bad.sum()), "violating_segments": segs,
                "walk_home_min_along_route": np.round(prof.pt_back_s / 60, 2).tolist()},
        "consumables": {"o2_used_kg": o2_used, "o2_left_pct": 100 * (1 - o2_used / cap),
                        "battery_used_wh": bat_used,
                        "battery_left_pct": 100 * (1 - bat_used / pv(p, "consumables.battery_capacity_wh"))},
        "dose": {"background_ugy": dose, "rate_ugy_per_day": pv(p, "sep.background_dose_rate_ugy_per_day"),
                 "label": "proxy (Curiosity RAD at Gale crater), absorbed dose",
                 "may2024_event_total_ugy": pv(p, "sep.may2024_event_dose_ugy"),
                 "may2024_event_in_background_days": pv(p, "sep.may2024_event_dose_ugy") / pv(p, "sep.background_dose_rate_ugy_per_day")},
        "route_cells": int(cells.size),
        "_time_margin": time_margin, "_o2_margin": o2_margin,
    }


def pareto_sweep(world: World, sites, order, step: float) -> list[dict]:
    """Sweep the hazard weight (time weight = 1 - w_H). Energy is proportional to walking time
    under constant-power pacing, so the real trade-off is walking time vs hazard exposure."""
    pts = []
    n = int(round(1 / step))
    for i in range(n):                     # w_H = 0 ... 1 - step (time weight must stay > 0)
        w = (round(1 - i * step, 10), 0.0, round(i * step, 10), 0.0)
        legs = leg_matrix_for_order(world, sites, order, f"h{i}", w)
        tot = totals(legs, sites, order, world)
        pts.append({"w": list(w), **{k: tot[k] for k in
                    ("walk_min", "duration_min", "walk_energy_kcal", "hazard_min", "caution_min", "dist_m", "max_slope_deg")}})
    keys = ("walk_min", "hazard_min")
    seen = {}
    for a in pts:                          # same route found by several weightings -> one 'distinct' id
        key = (round(a["walk_min"], 4), round(a["hazard_min"], 5), round(a["dist_m"], 2))
        a["route_id"] = seen.setdefault(key, len(seen))
    for a in pts:
        a["pareto"] = not any(all(b[k] <= a[k] + 1e-9 for k in keys) and any(b[k] < a[k] - 1e-9 for k in keys)
                              for b in pts if b is not a)
    return pts


def leg_matrix_for_order(world: World, sites, order, key, w) -> list[dict]:
    cs = to_csgraph(world.edges, world.weights(w)) if key not in world._cs else world._cs[key]
    src = sorted({order[k] for k in range(len(order) - 1)})
    dist, pred = dijkstra_tree(cs, [sites[k]["idx"] for k in src])
    row = {k: r for r, k in enumerate(src)}
    legs = []
    for a, b in zip(order[:-1], order[1:]):
        path = tree_path(pred[row[a]], sites[a]["idx"], sites[b]["idx"])
        leg = world.leg(path)
        leg["cost"] = float(dist[row[a], sites[b]["idx"]])
        legs.append(leg)
    return legs


def astar_crosscheck(world: World, sites, order, w) -> dict:
    """Re-solve each leg with the Python A* and compare to Dijkstra's optimum."""
    wt = world.weights(w)
    c_min = min_cost_per_metre(world.edges, wt)
    legs = leg_matrix_for_order(world, sites, order, "balanced", w)
    out, worst = [], 0.0
    for (a, b), leg in zip(zip(order[:-1], order[1:]), legs):
        t0 = time.perf_counter()
        cost, path, expanded = astar(world.edges, wt, sites[a]["idx"], sites[b]["idx"], world.t.cell, c_min)
        dt = time.perf_counter() - t0
        rel = abs(cost - leg["cost"]) / leg["cost"]
        worst = max(worst, rel)
        out.append({"from": sites[a]["id"], "to": sites[b]["id"], "astar_cost": cost, "dijkstra_cost": leg["cost"],
                    "rel_diff": rel, "expanded": expanded, "astar_ms": dt * 1000})
    return {"legs": out, "max_rel_diff": worst, "c_min_per_m": c_min}


def validation_drives(world: World, params: dict) -> list[dict]:
    vec = json.loads((SITE_DATA / "vectors.json").read_text(encoding="utf-8"))
    lines = vec["traverse"]["lines"]
    wps = {w["rmc"]: w for w in vec["waypoints"]["points"]}
    drives = [("Delta-top climb (Hawksbill Gap to Tenby)", "33_612", "34_5120", 708, 721),
              ("Crater floor to delta front", "18_1622", "22_0", 399, 409)]
    t = world.t
    out = []
    for name, a, b, s0, s1 in drives:
        A, B = wps[a], wps[b]
        rover = [np.array(l["xy"]) for l in lines if s0 <= l["sol"] <= s1]
        ia, sa = snap(world, A["x"], A["y"], world.ok)
        ib, sb = snap(world, B["x"], B["y"], world.ok)
        res = {"name": name, "from_waypoint": a, "to_waypoint": b, "rover_sols": [s0, s1],
               "start_xy": [A["x"], A["y"]], "end_xy": [B["x"], B["y"]], "snap_m": [sa, sb], "options": {}}
        for key in ("balanced", "safest", "fastest"):
            w = pv(params, f"route_options.{key}")
            cs = world.csgraph(key, w)
            dist, pred = dijkstra_tree(cs, [ia])
            path = tree_path(pred[0], ia, ib)
            if not path:
                res["options"][key] = {"error": "no safe route"}
                continue
            leg = world.leg(path)
            xy = np.array(leg["xy"])
            xy[0], xy[-1] = (A["x"], A["y"]), (B["x"], B["y"])
            cmp_ = validate.compare(xy, rover)
            res["options"][key] = {**cmp_, "max_slope_deg": leg["max_slope_deg"],
                                   "xy": np.round(xy, 1).tolist()}
        res["straight_line"] = validate.straight_line_baseline((A["x"], A["y"]), (B["x"], B["y"]), rover)
        # how steep is the straight line? (share of its 10 m cells that are no-go)
        sl = validate.densify(np.array([[A["x"], A["y"]], [B["x"], B["y"]]]), 5.0)
        rc = [t.xy_to_rc(x, y) for x, y in sl]
        res["straight_line"]["nogo_share"] = float(np.mean([not world.ok[r, c] for r, c in rc]))
        res["rover_xy"] = [np.round(l, 1).tolist() for l in rover]
        out.append(res)
    return out


def apollo14_check(params: dict) -> dict:
    """Walking model with LUNAR gravity vs Apollo 14 EVA-2 uphill legs (Waligora & Horrigan Table 4)."""
    rows = [r for r in csv.DictReader(line for line in APOLLO_FILE.read_text(encoding="utf-8").splitlines()
                                       if not line.startswith("#"))]
    total = [r for r in rows if r["leg"].startswith("LM to LM")][0]
    v0 = float(total["rate_kmh"]) / 3.6
    p0 = (float(total["cdr_kj_per_h"]) + float(total["lmp_kj_per_h"])) / 2 * 1000 / 3600
    hm = HumanModel.from_params(params, gravity_key="human_factors.moon_gravity_mps2")
    hm = HumanModel(v0=v0, p0=p0, mass=hm.mass, gravity=hm.gravity, eta=hm.eta, down_credit=hm.down_credit)
    legs = []
    for r in rows:
        g = float(r["net_slope_pct"]) / 100
        if r["leg"].startswith("LM to LM") or g < 0.04:
            continue
        legs.append({"leg": r["leg"], "slope_pct": float(r["net_slope_pct"]), "measured_kmh": float(r["rate_kmh"]),
                     "model_kmh": float(hm.speed(g) * 3.6)})
    meas = np.array([l["measured_kmh"] for l in legs])
    mod = np.array([l["model_kmh"] for l in legs])
    return {"v0_kmh": v0 * 3.6, "p0_w": p0, "legs": legs,
            "mean_abs_error_kmh": float(np.abs(meas - mod).mean()),
            "mean_measured_kmh": float(meas.mean()), "mean_model_kmh": float(mod.mean()),
            "note": "Uphill legs (net slope >= 4 %). Model uses Apollo 14's own level pace and mean metabolic rate, lunar gravity, A7LB mass + 10 kg kit."}


def route_slope_2m(xy: np.ndarray) -> dict:
    """Slope on the 2 m analysis grid along a route (finer than the 10 m planning grid)."""
    import rasterio

    f = PROCESSED / "slope.tif"
    if not f.exists():
        return {"available": False}
    with rasterio.open(f) as src:
        s = src.read(1)
    pts = validate.densify(np.asarray(xy), 2.0)
    H = s.shape[0]
    r = np.clip(((H * 2.0 - pts[:, 1]) // 2).astype(int), 0, H - 1)
    c = np.clip((pts[:, 0] // 2).astype(int), 0, s.shape[1] - 1)
    v = s[r, c]
    return {"available": True, "p50_deg": float(np.nanpercentile(v, 50)), "p95_deg": float(np.nanpercentile(v, 95)),
            "max_deg": float(np.nanmax(v)), "share_above_20_deg": float(np.mean(v > 20))}


# ----------------------------------------------------------------------------------------
def r1(x, n=1):
    return round(float(x), n)


def simplify_xy(xy, tol=0.01):
    """Drop points that lie on a straight line (keeps every corner): smaller JSON, same route."""
    xy = np.asarray(xy)
    if len(xy) <= 2:
        return xy
    keep = [0]
    for i in range(1, len(xy) - 1):
        a, b, c = xy[keep[-1]], xy[i], xy[i + 1]
        cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if abs(cross) > tol:
            keep.append(i)
    keep.append(len(xy) - 1)
    return xy[keep]


def main() -> dict:
    T0 = time.perf_counter()
    p = load_params()
    world = World(p)
    log = {"cells": world.t.n, "passable_share": float(world.ok.mean()), "edges": int(world.edges.ok.sum())}
    sites, meta = build_sites(world, p)
    limit_s = pv(p, "mission.eva_time_limit") * 3600
    shelter_s = pv(p, "sep.shelter_time_limit_min") * 60
    opts = {k: pv(p, f"route_options.{k}") for k in PROFILE_NAMES}

    # walk-home field (fastest safe route home from every cell)
    home = walkback_field(world.edges, world.ec.time_s, world.ec.energy_j, sites[0]["idx"])
    for s in sites:
        s["walk_home_min"] = float(home["time_s"].flat[s["idx"]] / 60)
    eligible = [s["kind"] != "stop" or s["walk_home_min"] * 60 <= shelter_s for s in sites]

    M = {k: leg_matrix(world, sites, k, w) for k, w in opts.items()}
    Mb = M["balanced"]

    # --- schedule: one optimal plan per time budget, each scored by Monte Carlo -------
    cands, seen = [], set()
    for frac in pv(p, "schedule.budget_fractions"):
        inst, keep = make_instance(world, sites, Mb, frac * limit_s, eligible)
        t0 = time.perf_counter()
        plan = solve_ortools(inst)
        dt = time.perf_counter() - t0
        if plan is None:
            continue
        order = [keep[k] for k in plan.order]
        if tuple(order) in seen:
            continue
        seen.add(tuple(order))
        legs = tour_legs(Mb, order)
        prof = profile_for(world, sites, legs, order, home)
        summ = summarise(run_mc(p, prof), limit_s, pv(p, "consumables.o2_capacity_kg"))
        cands.append({"budget_frac": frac, "budget_min": frac * limit_s / 60, "order": order,
                      "stops": [sites[k]["id"] for k in order[1:-1]], "value": plan.value,
                      "planned_min": plan.time_s / 60, "o2_kg": plan.o2_kg, "solver": plan.solver,
                      "solver_status": plan.status, "solve_ms": dt * 1000, "p_on_time": summ["p_on_time"],
                      "p_success": summ["p_success"], "p95_min": summ["duration_min"]["p95"]})
    target = pv(p, "schedule.robust_p_on_time")
    robust = max((c for c in cands if c["p_success"] >= target), key=lambda c: (c["value"], c["p_success"]), default=None)
    maxsci = max(cands, key=lambda c: (c["value"], -c["planned_min"]))
    if robust is None:
        robust = max(cands, key=lambda c: c["p_success"])
    order = robust["order"]

    # the same optimizer with the SEP rule switched off: what does the rule cost?
    inst, keep = make_instance(world, sites, Mb, limit_s, [True] * len(sites))
    nosep = solve_ortools(inst)
    nosep_info = {"stops": [sites[keep[k]]["id"] for k in nosep.order[1:-1]], "value": nosep.value,
                  "planned_min": nosep.time_s / 60} if nosep else None

    # --- plan of record ------------------------------------------------------------------
    legs = tour_legs(Mb, order)
    prof = profile_for(world, sites, legs, order, home)
    mc = run_mc(p, prof)
    mc_sum = summarise(mc, limit_s, pv(p, "consumables.o2_capacity_kg"))
    sig = {"speed": pv(p, "montecarlo.speed_sigma"), "met": pv(p, "montecarlo.metabolic_sigma"),
           "dwell": pv(p, "montecarlo.dwell_sigma")}
    torn = tornado(prof, [sites[k]["name"] for k in order[1:-1]], sig, pv(p, "montecarlo.tornado_quantile"), **mc_kwargs(p))
    rows, burn = timeline(world, sites, legs, order, meta["roles"])
    safe = safety_checks(world, sites, legs, order, home, prof, rows)
    tot_b = totals(legs, sites, order, world)

    # --- route alternatives for this stop order ------------------------------------------
    alts = []
    for k, name in PROFILE_NAMES.items():
        L = tour_legs(M[k], order)
        tt = totals(L, sites, order, world)
        pr = profile_for(world, sites, L, order, home)
        su = summarise(run_mc(p, pr), limit_s, pv(p, "consumables.o2_capacity_kg"))
        ss = safety_checks(world, sites, L, order, home, pr, timeline(world, sites, L, order, meta["roles"])[0])
        alts.append({"id": k, "name": name, "weights": opts[k], **tt,
                     "min_walkback_margin_min": ss["walkback"]["min_time_margin_min"],
                     "min_o2_margin_pct": ss["walkback"]["min_o2_margin_pct_of_capacity"],
                     "p_on_time": su["p_on_time"], "sep_violating_points": ss["sep"]["violating_points"],
                     "legs_xy": [simplify_xy(l["xy"]).round(1).tolist() for l in L]})
    pareto = pareto_sweep(world, sites, order, pv(p, "route_options.pareto_hazard_step"))

    # --- checks ---------------------------------------------------------------------------
    xcheck = astar_crosscheck(world, sites, order, opts["balanced"])
    vdr = validation_drives(world, p)
    ap14 = apollo14_check(p)
    route_xy = np.vstack([np.array(l["xy"]) for l in legs])
    slope2 = route_slope_2m(route_xy)
    cap = pv(p, "consumables.o2_capacity_kg")
    checks = checklist([
        ("EVA fits the time limit (planned)", tot_b["duration_min"] <= limit_s / 60,
         f"{tot_b['duration_min']:.0f} of {limit_s / 60:.0f} min"),
        (f"Home on time in >= {target:.0%} of Monte Carlo runs", mc_sum["p_success"] >= target,
         f"{mc_sum['p_success']:.1%} of {mc_sum['runs']} runs"),
        ("Walkback rule: can always walk home with reserve O2", safe["walkback"]["min_o2_margin_kg"] >= 0,
         f"tightest O2 margin {safe['walkback']['min_o2_margin_pct_of_capacity']:.1f}% of tank above reserve"),
        ("Walkback rule: can always walk home within the EVA limit", safe["walkback"]["min_time_margin_min"] >= 0,
         f"tightest time margin {safe['walkback']['min_time_margin_min']:.0f} min"),
        (f"SEP shelter reachable within {shelter_s / 60:.0f} min everywhere", safe["sep"]["violating_points"] == 0,
         f"farthest point {safe['sep']['max_walk_home_min']:.0f} min from shelter"),
        (f"No route cell steeper than {world.slope_nogo:.0f} deg (10 m grid)", tot_b["max_slope_deg"] <= world.slope_nogo,
         f"max {tot_b['max_slope_deg']:.1f} deg"),
        ("O2 left at return above reserve", safe["consumables"]["o2_left_pct"] >= 100 * pv(p, "consumables.o2_reserve_fraction"),
         f"{safe['consumables']['o2_left_pct']:.0f}% left (reserve {100 * pv(p, 'consumables.o2_reserve_fraction'):.0f}%)"),
        ("Battery left at return above 0", safe["consumables"]["battery_left_pct"] > 0,
         f"{safe['consumables']['battery_left_pct']:.0f}% left"),
        ("Sample tubes collected (depot visited)", 1 in order, "Three Forks depot is on the route"),
    ])

    # --- export ---------------------------------------------------------------------------
    def site_out(s):
        keys = ("id", "name", "kind", "category", "value", "samples", "quote", "source", "why_category", "look_for",
                "position_source", "task")
        o = {k: s[k] for k in keys if k in s and s[k] is not None}
        o.update({"x": r1(s["x"]), "y": r1(s["y"]), "cell_xy": [r1(v) for v in s["cell_xy"]], "snap_m": r1(s["snap_m"]),
                  "elev_m": r1(s["elev_m"], 2), "dwell_min": s["dwell_s"] / 60, "work_w": s["work_w"],
                  "walk_home_min": r1(s["walk_home_min"]), "sep_ok": s["walk_home_min"] * 60 <= shelter_s})
        if s.get("elev_pds_m") is not None:
            o["elev_pds_m"] = s["elev_pds_m"]
        if s.get("elev_dtm1m_m") is not None:
            o["elev_dtm1m_m"] = r1(s["elev_dtm1m_m"], 3)
        return o

    out = {
        "generated_by": "python -m planner.run_plan",
        "labels": "All results are MODELED from real terrain data plus labelled parameters (config/params.yaml).",
        "params_used": {k: pv(p, k) for k in [
            "mission.eva_time_limit", "terrain.slope_nogo_deg", "terrain.roughness_nogo_m", "hazard.slope_caution_deg",
            "hazard.roughness_caution_m", "human_factors.level_speed_mps", "human_factors.level_metabolic_rate_w",
            "human_factors.uphill_muscle_efficiency", "human_factors.mars_gravity_mps2", "consumables.o2_capacity_kg",
            "consumables.o2_reserve_fraction", "consumables.o2_kg_per_mj", "consumables.battery_capacity_wh",
            "consumables.battery_draw_w", "sep.shelter_time_limit_min", "sep.background_dose_rate_ugy_per_day",
            "schedule.robust_p_on_time", "montecarlo.runs"]},
        "model": {"mass_kg": world.hm.mass, "level_energy_j_per_m": world.hm.p0 / world.hm.v0,
                  "speed_kmh_by_grade": {f"{g:+.2f}": r1(world.hm.speed(g) * 3.6, 2) for g in (-0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3)},
                  "energy_j_per_m_by_grade": {f"{g:+.2f}": r1(world.hm.e_per_m(g), 1) for g in (-0.3, -0.2, -0.1, 0, 0.1, 0.2, 0.3)}},
        "sites": [site_out(s) for s in sites],
        "habitat_rule": meta["habitat"],
        "candidates": cands, "robust_plan": robust, "max_science_plan": maxsci, "without_sep_rule": nosep_info,
        "plan": {"order": [sites[k]["id"] for k in order], "value": robust["value"], "totals": tot_b,
                 "legs_xy": [simplify_xy(l["xy"]).round(1).tolist() for l in legs],
                 "timeline": rows, "burn_down": burn},
        "alternatives": alts, "pareto": pareto,
        "safety": {k: v for k, v in safe.items() if not k.startswith("_")},
        "checklist": checks,
        "montecarlo": {**mc_sum, "sigmas": sig, "tornado": torn},
        "validation": {"astar_vs_dijkstra": xcheck, "rover_drives": vdr, "apollo14_speed_check": ap14,
                       "route_slope_on_2m_grid": slope2},
        "runtime_s": None, "grid": log,
    }
    out["runtime_s"] = time.perf_counter() - T0
    PROCESSED.mkdir(parents=True, exist_ok=True)
    (PROCESSED / "plan_full.json").write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    web = json.loads(json.dumps(out, default=float))
    web["safety"]["sep"].pop("walk_home_min_along_route", None)
    for d in web["validation"]["rover_drives"]:
        for o in d["options"].values():
            if "xy" in o:
                o["xy"] = simplify_xy(o["xy"]).round(1).tolist()
        d["rover_xy"] = [simplify_xy(l).round(1).tolist() for l in d["rover_xy"]]
    (SITE_DATA / "plan.json").write_text(json.dumps(web, separators=(",", ":"), default=float), encoding="utf-8")
    from .plots import make_previews
    from .write_docs import main as write_docs

    make_previews(world, out, home)
    write_docs()
    print(summary_text(out))
    return out


def summary_text(o: dict) -> str:
    pl, mc, s = o["plan"], o["montecarlo"], o["safety"]
    lines = [f"runtime {o['runtime_s']:.1f} s; grid {o['grid']}",
             f"habitat at ({o['habitat_rule']['x']:.0f}, {o['habitat_rule']['y']:.0f}) m, "
             f"{o['habitat_rule']['dist_to_depot_m']:.0f} m from depot, pad max slope {o['habitat_rule']['pad_max_slope_deg']:.1f} deg",
             "sites: " + "; ".join(f"{x['id']} {x['walk_home_min']:.0f} min home{' (SEP-excluded)' if not x['sep_ok'] else ''}" for x in o["sites"]),
             "candidates (budget -> stops, points, planned min, P on time):"]
    for c in o["candidates"]:
        lines.append(f"  {c['budget_min']:.0f} min -> {c['stops']} {c['value']} pts {c['planned_min']:.0f} min "
                     f"P={c['p_success']:.3f} [{c['solver_status']}, {c['solve_ms']:.0f} ms]")
    lines.append(f"ROBUST plan: {pl['order']} {pl['value']} pts; totals {json.dumps({k: round(v, 1) for k, v in pl['totals'].items()})}")
    lines.append(f"without SEP rule: {o['without_sep_rule']}")
    lines.append(f"MC: P(on time)={mc['p_on_time']:.3f} P(success)={mc['p_success']:.4f} +/- {mc['p_success_se']:.4f} (1 s.e.) P50={mc['duration_min']['p50']:.0f} P95={mc['duration_min']['p95']:.0f} min")
    lines.append(f"tornado top: {[(r['input'], round(r['swing_min'], 1)) for r in mc['tornado']['rows'][:3]]}")
    lines.append(f"walkback: {json.dumps({k: v for k, v in s['walkback'].items() if k != 'rule'})}")
    lines.append(f"SEP: max {s['sep']['max_walk_home_min']:.1f} min, violations {s['sep']['violating_points']}")
    lines.append(f"consumables: {json.dumps({k: round(v, 3) for k, v in s['consumables'].items()})}; dose {s['dose']['background_ugy']:.1f} uGy")
    for a in o["alternatives"]:
        lines.append(f"  {a['name']:14s} walk {a['walk_min']:.0f} min, total {a['duration_min']:.0f} min, {a['dist_m']:.0f} m, "
                     f"{a['walk_energy_kcal']:.0f} kcal walk, hazard {a['hazard_min']:.1f}, caution {a['caution_min']:.1f} min, "
                     f"max slope {a['max_slope_deg']:.1f}, P={a['p_on_time']:.3f}")
    lines.append(f"pareto: {len({x['route_id'] for x in o['pareto'] if x['pareto']})} distinct non-dominated routes from {len(o['pareto'])} weightings")
    lines.append(f"A* vs Dijkstra max rel diff {o['validation']['astar_vs_dijkstra']['max_rel_diff']:.2e}")
    for d in o["validation"]["rover_drives"]:
        b = d["options"]["balanced"]
        lines.append(f"  {d['name']}: planned {b['planned_length_m']:.0f} m vs rover {b['rover_length_m']:.0f} m, "
                     f"within 25 m {b['share_of_planned_within_m']['25']:.0%}, within 50 m {b['share_of_planned_within_m']['50']:.0%}; "
                     f"straight line within 25 m {d['straight_line']['share_of_planned_within_m']['25']:.0%}, no-go share {d['straight_line']['nogo_share']:.0%}")
    ap = o["validation"]["apollo14_speed_check"]
    lines.append(f"Apollo 14 uphill: model {ap['mean_model_kmh']:.2f} vs measured {ap['mean_measured_kmh']:.2f} km/h, MAE {ap['mean_abs_error_kmh']:.2f}")
    lines.append(f"2 m slope along route: {o['validation']['route_slope_on_2m_grid']}")
    lines.append(f"checklist GO={o['checklist']['go']}: " + "; ".join(f"{'PASS' if i['pass'] else 'FAIL'} {i['rule']}" for i in o["checklist"]["items"]))
    return "\n".join(lines)


if __name__ == "__main__":
    main()
