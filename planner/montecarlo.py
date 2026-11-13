"""Monte Carlo risk model for one EVA plan (SPEC 6.7) and the "Robust plan" ranking (owner upgrade S4).

Each run draws:
  speed factor S      one per run (the whole crew walks faster or slower all day)
  metabolic factor M  one per run (harder- or easier-working crew)
  dwell factor D_i    one per work stop (each task can run long or short on its own)
All three are log-normal with median 1 and a spread taken from params.yaml (assumptions).

Per run:  walk time = planned / S ;  work time = planned * D_i
          oxygen    = planned walking O2 * M + planned work O2 * M * D_i
(Walking energy per metre barely depends on pace near the preferred speed, so a slower
crew takes longer but burns about the same energy per metre: assumption, see ASSUMPTIONS.md.)
The walkback margin is checked at every cell of the route (vectorised).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class PlanProfile:
    """A plan as the Monte Carlo sees it. Arrays over route points (cells) in time order."""
    walk_s: np.ndarray              # planned walking time of each walk leg, s
    walk_o2: np.ndarray             # planned walking O2 of each leg, kg
    work_s: np.ndarray              # planned work time at each stop, s (one per stop, in order)
    work_o2: np.ndarray             # planned work O2 at each stop, kg
    # route points: which leg each point lies on, planned walk time and O2 since the leg start,
    # and the planned time / O2 to walk back to the habitat from that point
    pt_leg: np.ndarray
    pt_walk_s: np.ndarray
    pt_walk_o2: np.ndarray
    pt_back_s: np.ndarray
    pt_back_o2: np.ndarray
    # leg k is walked after work at stops 0..k-1 (leg 0 starts at the habitat)


def lognormal(rng, sigma: float, size):
    return np.exp(rng.normal(0.0, sigma, size))


def simulate(p: PlanProfile, n_runs: int, sig_speed: float, sig_met: float, sig_dwell: float,
             eva_limit_s: float, o2_capacity_kg: float, o2_reserve_kg: float, seed: int = 0,
             fixed: dict | None = None) -> dict:
    """Run the model. `fixed` overrides draws with constants (used for the tornado chart):
    {"speed": S, "met": M, "dwell": array or scalar}."""
    rng = np.random.default_rng(seed)
    n_legs, n_stops = len(p.walk_s), len(p.work_s)
    S = lognormal(rng, sig_speed, n_runs)
    M = lognormal(rng, sig_met, n_runs)
    D = lognormal(rng, sig_dwell, (n_runs, n_stops))
    if fixed:
        if "speed" in fixed:
            S = np.full(n_runs, fixed["speed"])
        if "met" in fixed:
            M = np.full(n_runs, fixed["met"])
        if "dwell" in fixed:
            D = np.broadcast_to(np.asarray(fixed["dwell"], float), (n_runs, n_stops)).copy()

    walk_t = p.walk_s[None, :] / S[:, None]                       # (runs, legs)
    work_t = p.work_s[None, :] * D                                # (runs, stops)
    walk_o = p.walk_o2[None, :] * M[:, None]
    work_o = p.work_o2[None, :] * M[:, None] * D
    duration = walk_t.sum(1) + work_t.sum(1)
    o2_used = walk_o.sum(1) + work_o.sum(1)

    # time and O2 already used when each leg starts: legs before it + work at stops before it
    leg_t0 = np.zeros((n_runs, n_legs))
    leg_o0 = np.zeros((n_runs, n_legs))
    for k in range(1, n_legs):
        leg_t0[:, k] = leg_t0[:, k - 1] + walk_t[:, k - 1] + work_t[:, k - 1]
        leg_o0[:, k] = leg_o0[:, k - 1] + walk_o[:, k - 1] + work_o[:, k - 1]
    t_at = leg_t0[:, p.pt_leg] + p.pt_walk_s[None, :] / S[:, None]
    o_at = leg_o0[:, p.pt_leg] + p.pt_walk_o2[None, :] * M[:, None]
    # walkback margin at each point: what is left after walking straight home from there
    time_margin = eva_limit_s - (t_at + p.pt_back_s[None, :] / S[:, None])
    o2_margin = o2_capacity_kg - o2_reserve_kg - (o_at + p.pt_back_o2[None, :] * M[:, None])
    return {
        "duration_s": duration, "o2_used_kg": o2_used,
        "min_time_margin_s": time_margin.min(1), "min_o2_margin_kg": o2_margin.min(1),
        "on_time": duration <= eva_limit_s,
        "o2_ok": o2_used <= o2_capacity_kg - o2_reserve_kg,
        "S": S, "M": M, "D": D,
    }


def summarise(res: dict, eva_limit_s: float, o2_capacity_kg: float, bins: int = 40) -> dict:
    d = res["duration_s"] / 60.0
    ok = res["on_time"] & res["o2_ok"]
    hist, edges = np.histogram(d, bins=bins)
    reserve_pct = 100.0 * (o2_capacity_kg - res["o2_used_kg"]) / o2_capacity_kg
    return {
        "runs": int(d.size),
        "p_on_time": float(res["on_time"].mean()),
        "p_o2_ok": float(res["o2_ok"].mean()),
        "p_success": float(ok.mean()),
        "p_success_se": float(np.sqrt(ok.mean() * (1 - ok.mean()) / d.size)),
        "duration_min": {"p05": float(np.percentile(d, 5)), "p50": float(np.percentile(d, 50)),
                         "p95": float(np.percentile(d, 95)), "mean": float(d.mean()),
                         "max": float(d.max())},
        "o2_reserve_pct_at_return": {"p05": float(np.percentile(reserve_pct, 5)),
                                     "p50": float(np.percentile(reserve_pct, 50))},
        "min_walkback_time_margin_min": {"p05": float(np.percentile(res["min_time_margin_s"], 5) / 60),
                                         "p50": float(np.percentile(res["min_time_margin_s"], 50) / 60)},
        "histogram": {"bin_edges_min": [round(float(e), 2) for e in edges], "counts": hist.tolist(),
                      "limit_min": eva_limit_s / 60.0},
    }


def tornado(p: PlanProfile, stop_names: list[str], sig: dict, q: float, **kw) -> dict:
    """One-at-a-time sensitivity: each input at its low and high quantile (q, 1-q), all others at
    their median (1.0). Output: EVA duration (min) and O2 used (kg). Sorted by duration swing."""
    from scipy.stats import norm

    z = norm.ppf(1 - q)
    base = simulate(p, 1, 0, 0, 0, fixed={"speed": 1.0, "met": 1.0, "dwell": 1.0}, **kw)
    b_d, b_o = float(base["duration_s"][0] / 60), float(base["o2_used_kg"][0])
    rows = []

    def run(fixed):
        r = simulate(p, 1, 0, 0, 0, fixed={"speed": 1.0, "met": 1.0, "dwell": 1.0, **fixed}, **kw)
        return float(r["duration_s"][0] / 60), float(r["o2_used_kg"][0])

    lo, hi = np.exp(-z * sig["speed"]), np.exp(z * sig["speed"])
    a, b = run({"speed": lo}), run({"speed": hi})           # slow crew -> longer EVA
    rows.append({"input": "Walking speed", "low_label": f"x{lo:.2f}", "high_label": f"x{hi:.2f}",
                 "duration_min": [a[0], b[0]], "o2_kg": [a[1], b[1]]})
    lo, hi = np.exp(-z * sig["met"]), np.exp(z * sig["met"])
    a, b = run({"met": lo}), run({"met": hi})
    rows.append({"input": "Metabolic rate", "low_label": f"x{lo:.2f}", "high_label": f"x{hi:.2f}",
                 "duration_min": [a[0], b[0]], "o2_kg": [a[1], b[1]]})
    lo, hi = np.exp(-z * sig["dwell"]), np.exp(z * sig["dwell"])
    for i, name in enumerate(stop_names):
        dl = np.ones(len(stop_names)); dh = np.ones(len(stop_names))
        dl[i], dh[i] = lo, hi
        a, b = run({"dwell": dl}), run({"dwell": dh})
        rows.append({"input": f"Work time: {name}", "low_label": f"x{lo:.2f}", "high_label": f"x{hi:.2f}",
                     "duration_min": [a[0], b[0]], "o2_kg": [a[1], b[1]]})
    for r in rows:
        r["swing_min"] = abs(r["duration_min"][1] - r["duration_min"][0])
        r["swing_o2_kg"] = abs(r["o2_kg"][1] - r["o2_kg"][0])
    rows.sort(key=lambda r: -r["swing_min"])
    return {"base_duration_min": b_d, "base_o2_kg": b_o, "quantiles": [q, 1 - q], "rows": rows}
