"""Preview pictures of the Phase 2 results (data/processed/previews/2*_*.png).

Colours: Okabe-Ito palette (safe for common colour-vision deficiencies).
"""
from __future__ import annotations

import numpy as np

from pipeline.common import PREVIEWS, PROCESSED

OI = {"orange": "#E69F00", "sky": "#56B4E9", "green": "#009E73", "yellow": "#F0E442", "blue": "#0072B2",
      "vermillion": "#D55E00", "purple": "#CC79A7", "black": "#000000", "grey": "#999999"}
ALT_STYLE = {"fastest": (OI["orange"], "--"), "lowest_energy": (OI["green"], ":"), "safest": (OI["sky"], "-."),
             "balanced": (OI["blue"], "-"), "shortest": (OI["purple"], (0, (5, 1, 1, 1)))}
CAT_COLOR = {"fine_grained_layered_rock": OI["vermillion"], "delta_layer_sequence": OI["purple"],
             "transported_boulders": OI["yellow"], "depot": OI["black"]}
CREDIT = ("Terrain: HiRISE DTM mosaic, Fergason et al. 2020, USGS (doi:10.5066/P9REJ9JN); HiRISE data NASA/JPL-Caltech/UofA. "
          "Sites: NASA PDS Mars 2020 sample dossier. Routes and numbers: MODELED.")


def _hillshade():
    import rasterio

    with rasterio.open(PROCESSED / "hillshade.tif") as s:
        return s.read(1)


def _base(ax, world, hs, extent=(0, 4000, 0, 4000)):
    ax.imshow(hs, cmap="gray", extent=(0, 4000, 0, 4000), vmin=0, vmax=1, interpolation="bilinear")
    nogo = np.ma.masked_where(world.ok, np.ones(world.ok.shape))
    ax.imshow(nogo, cmap=__import__("matplotlib.colors", fromlist=["x"]).ListedColormap([OI["vermillion"]]),
              extent=(0, 4000, 0, 4000), alpha=0.45, interpolation="nearest")
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_xlabel("x east (m, local grid)")
    ax.set_ylabel("y north (m)")


def make_previews(world, out: dict, home: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    PREVIEWS.mkdir(parents=True, exist_ok=True)
    hs = _hillshade()
    sites = {s["id"]: s for s in out["sites"]}
    on_plan = set(out["plan"]["order"])

    # ---- 20: map of the plan + alternatives ----------------------------------------------
    fig, ax = plt.subplots(figsize=(11, 10))
    _base(ax, world, hs, (250, 3150, 800, 3150))
    X, Y = np.meshgrid((np.arange(world.t.shape[1]) + 0.5) * 10, 4000 - (np.arange(world.t.shape[0]) + 0.5) * 10)
    lim = out["safety"]["sep"]["shelter_limit_min"]
    cs = ax.contour(X, Y, home["time_s"] / 60, levels=[30, lim, 90], colors=[OI["grey"], OI["purple"], OI["grey"]],
                    linewidths=[0.8, 1.8, 0.8], linestyles=["dotted", "solid", "dotted"])
    ax.clabel(cs, fmt=lambda v: f"{v:.0f} min walk home", fontsize=7)
    for a in out["alternatives"]:
        if a["id"] == "lowest_energy":      # same route as Fastest
            continue
        col, ls = ALT_STYLE[a["id"]]
        for i, xy in enumerate(a["legs_xy"]):
            xy = np.array(xy)
            ax.plot(xy[:, 0], xy[:, 1], linestyle=ls, color=col, lw=2.6 if a["id"] == "balanced" else 1.6,
                    label=f"{a['name']} ({a['duration_min']:.0f} min)" if i == 0 else None, zorder=4)
    for s in out["sites"]:
        if s["kind"] == "habitat":
            ax.plot(s["x"], s["y"], "s", ms=12, color=OI["blue"], mec="white", zorder=6)
            ax.annotate("Habitat", (s["x"], s["y"]), xytext=(-62, 8), textcoords="offset points", fontsize=9, weight="bold")
            continue
        col = CAT_COLOR[s.get("category", "depot")]
        filled = s["id"] in on_plan
        ax.plot(s["x"], s["y"], "*" if s["kind"] == "depot" else "o", ms=15 if s["kind"] == "depot" else 11,
                color=col if filled else "white", mec="black", mew=1.2, zorder=6)
        lab = s["name"] + (f"  [{s['value']} pts]" if s["kind"] == "stop" else "")
        if not s["sep_ok"]:
            lab += "\n(excluded: > SEP limit)"
        off = {"wildcat_ridge": (-150, -18), "skinner_ridge": (8, 8), "melyn": (8, -26), "boulder_field": (-10, 14),
               "depot": (10, -4), "amalik": (10, -12), "hidden_harbor": (-170, 8)}.get(s["id"], (8, 6))
        ax.annotate(lab, (s["x"], s["y"]), xytext=off, textcoords="offset points", fontsize=8,
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.8, lw=0))
    pl = out["plan"]
    ax.set_title(f"Robust plan: {pl['value']} science points, {pl['totals']['duration_min']:.0f} min planned, "
                 f"P(home on time) = {out['montecarlo']['p_success']:.0%}  (MODELED)", fontsize=11)
    ax.legend(loc="upper right", fontsize=8, title="Route options, same stops", framealpha=0.9)
    ax.text(0.01, 0.01, "Orange-red = no-go (slope > 20 deg or rough > 0.2 m). Purple line = SEP shelter limit.",
            transform=ax.transAxes, fontsize=8, bbox=dict(fc="white", alpha=0.85, lw=0))
    fig.text(0.01, 0.005, CREDIT, fontsize=6)
    fig.tight_layout(rect=(0, 0.015, 1, 1))
    fig.savefig(PREVIEWS / "20_plan_map.png", dpi=110)
    plt.close(fig)

    # ---- 21: charts ------------------------------------------------------------------------
    fig = plt.figure(figsize=(15, 10))
    gs = fig.add_gridspec(2, 3, height_ratios=[1, 1])
    # Pareto (walking time vs hazard; energy is proportional to walking time in this model)
    ax = fig.add_subplot(gs[0, 0])
    P = out["pareto"]
    pt = np.array([[q["walk_min"], q["hazard_min"], q["w"][2]] for q in P])
    dom = np.array([q["pareto"] for q in P])
    sc = ax.scatter(pt[:, 0], pt[:, 1], c=pt[:, 2], cmap="viridis", s=np.where(dom, 46, 14),
                    edgecolors=np.where(dom, "black", "none"), zorder=3)
    for a in out["alternatives"]:
        if a["id"] == "lowest_energy":
            continue
        col, _ = ALT_STYLE[a["id"]]
        ax.plot(a["walk_min"], a["hazard_min"], "D", ms=10, mfc="none", mec=col, mew=2, zorder=4)
        ax.annotate(a["name"], (a["walk_min"], a["hazard_min"]), xytext=(6, 4), textcoords="offset points", fontsize=8)
    fig.colorbar(sc, ax=ax, label="hazard weight w_H")
    ax.set_xlabel("walking time (min)  [energy is proportional]")
    ax.set_ylabel("hazard exposure (hazard-weighted min)")
    nd = len({q["route_id"] for q in P if q["pareto"]})
    ax.set_title(f"Pareto: {nd} distinct best routes ({len(P)} weightings)", fontsize=10)
    # Gantt
    ax = fig.add_subplot(gs[0, 1:])
    for r in pl["timeline"]:
        for lane, who in ((1, "EV1"), (0, "EV2")):
            col = OI["grey"] if r["kind"] == "walk" else CAT_COLOR.get(sites[r["at"]].get("category", "depot"), OI["black"])
            ax.barh(lane, r["t1_min"] - r["t0_min"], left=r["t0_min"], color=col, edgecolor="white", height=0.6)
        if r["kind"] == "work":
            ax.text((r["t0_min"] + r["t1_min"]) / 2, 1.45, sites[r["at"]]["name"].split(" (")[0], ha="center", fontsize=7, rotation=0)
    ax.axvline(out["params_used"]["mission.eva_time_limit"] * 60, color=OI["vermillion"], lw=2)
    ax.text(out["params_used"]["mission.eva_time_limit"] * 60, -0.55, " EVA limit", color=OI["vermillion"], fontsize=8)
    ax.set_yticks([0, 1], ["EV2", "EV1"])
    ax.set_ylim(-0.7, 1.8)
    ax.set_xlabel("minutes after leaving the habitat")
    ax.set_title("EVA timeline (grey = walking together; colour = work at a stop)", fontsize=10)
    # burn-down
    ax = fig.add_subplot(gs[1, 0])
    b = pl["burn_down"]
    ax.plot(b["t_min"], b["o2_pct"], color=OI["blue"], lw=2, label="O2 left (modeled)")
    ax.plot(b["t_min"], b["battery_pct"], color=OI["orange"], lw=2, ls="--", label="battery left (assumption)")
    ax.axhline(b["o2_reserve_pct"], color=OI["vermillion"], lw=1, ls=":", label="O2 reserve")
    ax.set_ylim(0, 100)
    ax.set_xlabel("minutes")
    ax.set_ylabel("% of capacity")
    ax.legend(fontsize=8)
    ax.set_title("Consumables burn-down", fontsize=10)
    # MC histogram
    ax = fig.add_subplot(gs[1, 1])
    h = out["montecarlo"]["histogram"]
    e = np.array(h["bin_edges_min"])
    ax.bar(e[:-1], h["counts"], width=np.diff(e), align="edge", color=OI["sky"], edgecolor="white")
    ax.axvline(h["limit_min"], color=OI["vermillion"], lw=2, label="EVA limit")
    d = out["montecarlo"]["duration_min"]
    ax.axvline(d["p50"], color="black", lw=1, ls="--", label=f"P50 {d['p50']:.0f} min")
    ax.axvline(d["p95"], color="black", lw=1, ls=":", label=f"P95 {d['p95']:.0f} min")
    ax.set_xlabel("EVA duration (min)")
    ax.set_ylabel("runs")
    ax.legend(fontsize=8)
    ax.set_title(f"Monte Carlo, {out['montecarlo']['runs']} runs: P(home on time) = {out['montecarlo']['p_success']:.1%}", fontsize=10)
    # tornado
    ax = fig.add_subplot(gs[1, 2])
    tr = out["montecarlo"]["tornado"]
    rows = tr["rows"][:8][::-1]
    base = tr["base_duration_min"]
    for i, r in enumerate(rows):
        lo, hi = r["duration_min"]
        ax.barh(i, hi - base, left=base, color=OI["vermillion"], height=0.6)
        ax.barh(i, lo - base, left=base, color=OI["blue"], height=0.6)
    ax.axvline(base, color="black", lw=1)
    ax.set_yticks(range(len(rows)), [r["input"].replace("Work time: ", "Work: ").replace("Metabolic rate", "Metabolic rate (O2 only)")
                                     for r in rows], fontsize=8)
    ax.set_xlabel("EVA duration (min) at P10 / P90 of each input")
    ax.set_title("What drives the risk? (one input at a time)", fontsize=10)
    fig.suptitle("Marswalk Ops - Phase 2 planning results (all MODELED; parameters in config/params.yaml)", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(PREVIEWS / "21_plan_charts.png", dpi=100)
    plt.close(fig)

    # ---- 22: validation vs rover ----------------------------------------------------------
    drives = out["validation"]["rover_drives"]
    fig, axs = plt.subplots(1, len(drives), figsize=(7 * len(drives), 6.5))
    for ax, d in zip(np.atleast_1d(axs), drives):
        allxy = np.vstack([np.array(l) for l in d["rover_xy"]] + [np.array(d["options"]["balanced"]["xy"])])
        pad = 150
        ext = (allxy[:, 0].min() - pad, allxy[:, 0].max() + pad, allxy[:, 1].min() - pad, allxy[:, 1].max() + pad)
        _base(ax, world, hs, ext)
        for i, l in enumerate(d["rover_xy"]):
            l = np.array(l)
            ax.plot(l[:, 0], l[:, 1], color="white", lw=4.5, zorder=3)
            ax.plot(l[:, 0], l[:, 1], color=OI["black"], lw=2.2, zorder=4, label="Perseverance actual traverse (real)" if i == 0 else None)
        b = d["options"]["balanced"]
        xy = np.array(b["xy"])
        ax.plot(xy[:, 0], xy[:, 1], color=OI["blue"], lw=2.4, zorder=5, label="Planned, Balanced (modeled)")
        s = np.array([d["start_xy"], d["end_xy"]])
        ax.plot(s[:, 0], s[:, 1], color=OI["orange"], lw=1.5, ls="--", zorder=4, label="Straight line")
        ax.set_aspect("equal")
        ax.set_title(f"{d['name']} (sols {d['rover_sols'][0]}-{d['rover_sols'][1]})\n"
                     f"planned within 25 m of rover path: {b['share_of_planned_within_m']['25']:.0%} "
                     f"(straight line {d['straight_line']['share_of_planned_within_m']['25']:.0%}); "
                     f"length ratio {b['length_ratio_planned_over_rover']:.2f}", fontsize=9)
        ax.legend(fontsize=8, loc="best")
    fig.text(0.01, 0.005, "Rover traverse: NASA/JPL-Caltech (MMGIS). A rover is not a human: agreement is supporting evidence only. "
             + CREDIT, fontsize=6)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(PREVIEWS / "22_validation_rover.png", dpi=100)
    plt.close(fig)
