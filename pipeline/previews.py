"""Step 4: a matplotlib preview of every layer -> data/processed/previews/ (committed, small).

Run: python -m pipeline.previews
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from PIL import Image  # noqa: E402

from .common import PREVIEWS, PROCESSED, RAW, SITE, SITE_DATA, grid_from_params, load_params, pv  # noqa: E402

TAGS = {"real": "REAL DATA", "derived": "DERIVED FROM REAL DATA", "assumption": "USES ASSUMED THRESHOLDS",
        "proxy": "PROXY (coarse, qualitative)"}
DPI = 100


def read(name):
    with rasterio.open(PROCESSED / f"{name}.tif") as s:
        return s.read(1)


def _frame(title, tag, credit, figsize=(7.4, 6.6)):
    fig, ax = plt.subplots(figsize=figsize, dpi=DPI)
    ax.set_title(title, fontsize=11, loc="left", fontweight="bold")
    ax.text(0.99, 0.99, TAGS[tag], transform=ax.transAxes, ha="right", va="top", fontsize=8, zorder=10,
            color="white", bbox=dict(boxstyle="round,pad=0.25", fc={"real": "#0072B2", "derived": "#009E73",
                                                                     "assumption": "#D55E00", "proxy": "#CC79A7"}[tag]))
    ax.set_xlabel("x east (km, local grid)")
    ax.set_ylabel("y north (km)")
    fig.text(0.01, 0.005, credit, fontsize=6.5, color="#444")
    return fig, ax


def _save(fig, name):
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    fig.savefig(PREVIEWS / f"{name}.png", dpi=DPI)
    plt.close(fig)


def _depot(ax, depot_km, **kw):
    ax.plot(*depot_km, marker="*", ms=13, mfc="#F0E442", mec="black", ls="none", label="Three Forks depot", **kw)


def make_all(params):
    man = json.loads((SITE_DATA / "layers.json").read_text(encoding="utf-8"))
    L = {l["id"]: l for l in man["layers"]}
    g = grid_from_params(params)
    W, H = (v / 1000 for v in g.size_m)
    ext = [0, W, 0, H]
    depot = [v / 1000 for v in man["aoi"]["anchor_local"]]
    vec = json.loads((SITE_DATA / "vectors.json").read_text(encoding="utf-8"))

    def simple(name, layer_id, arr, cmap, vmin=None, vmax=None, cbar=None, interp="nearest"):
        l = L[layer_id]
        fig, ax = _frame(f"{l['title']}  ({l['cell_m']:g} m cells)", l["kind"], l["credit"])
        im = ax.imshow(arr, extent=ext, cmap=cmap, vmin=vmin, vmax=vmax, interpolation=interp)
        if cbar:
            fig.colorbar(im, ax=ax, shrink=0.8, label=cbar)
        _depot(ax, depot)
        ax.legend(loc="lower left", fontsize=8)
        _save(fig, name)

    ortho = np.asarray(Image.open(SITE / "assets" / L["ortho"]["file"]))
    simple("01_ortho", "ortho", ortho, "gray", 0, 255)
    dtm = read("dtm")
    simple("02_elevation", "elevation", dtm, "cividis", cbar="elevation (m, relative to areoid)")
    hill = read("hillshade")
    simple("03_hillshade", "hillshade", hill, "gray", 0, 1)
    slope = read("slope")
    simple("04_slope", "slope", slope, "viridis", 0, 40, cbar="slope (deg); 40 = 40 or more")
    rough = read("roughness")
    simple("05_roughness", "roughness", rough, "magma", 0, 0.3, cbar="detrended RMS relief (m); 0.3 = 0.3 or more")

    # no-go over hillshade
    nogo = read("nogo").astype(bool)
    l = L["nogo"]
    fig, ax = _frame(f"No-go: slope > {pv(params, 'terrain.slope_nogo_deg')} deg or rough > "
                     f"{pv(params, 'terrain.roughness_nogo_m')} m", "assumption", l["credit"])
    ax.imshow(hill, extent=ext, cmap="gray", vmin=0, vmax=1)
    ax.imshow(np.where(nogo, 1.0, np.nan), extent=ext, cmap=ListedColormap([l["color"]]), interpolation="nearest")
    _depot(ax, depot)
    ax.text(0.99, 0.01, f"no-go: {nogo.mean() * 100:.1f}% of area", transform=ax.transAxes, ha="right",
            fontsize=9, bbox=dict(fc="white", alpha=0.8))
    ax.legend(loc="lower left", fontsize=8)
    _save(fig, "06_nogo")

    for i, key in enumerate(("themis_day", "themis_night")):
        simple(f"0{7 + i}_{key}", key, np.asarray(Image.open(SITE / "assets" / L[key]["file"])), "inferno", 0, 255,
               cbar="relative IR brightness (stretched DN, not temperature)", interp="nearest")

    # rover traverse, waypoints, depot, photo spots
    fig, ax = _frame("Perseverance traverse, waypoints, depot and photo spots", "real", vec["traverse"]["credit"]
                     + "; " + vec["depot_tubes"]["credit"])
    ax.imshow(hill, extent=ext, cmap="gray", vmin=0, vmax=1)
    for t in vec["traverse"]["lines"]:
        xy = np.asarray(t["xy"]) / 1000
        ax.plot(xy[:, 0], xy[:, 1], color="#56B4E9", lw=1.2)
    wp = np.asarray([[p["x"], p["y"]] for p in vec["waypoints"]["points"]]) / 1000
    ax.plot(wp[:, 0], wp[:, 1], ".", color="#0072B2", ms=3, label=f"waypoints ({len(wp)})")
    ph = np.asarray([[p["x"], p["y"]] for p in vec["pov"]["photos"]]) / 1000
    ax.plot(ph[:, 0], ph[:, 1], "s", mfc="none", mec="#E69F00", ms=6, label=f"rover photo spots ({len(ph)})")
    _depot(ax, depot)
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.legend(loc="lower left", fontsize=8)
    _save(fig, "09_rover_traverse_depot")

    # depot close-up with the 10 tube-drop rover positions
    c = man["closeups"][0]
    (y0, x0), (y1, x1) = c["bounds"]
    fig, ax = _frame("Three Forks depot close-up (25 cm) + tube-drop rover positions", "real", c["credit"],
                     figsize=(7.0, 6.6))
    ax.imshow(np.asarray(Image.open(SITE / "assets" / c["file"])), extent=[x0, x1, y0, y1], cmap="gray")
    for t in vec["depot_tubes"]["points"]:
        ax.plot(t["x"], t["y"], "o", mfc="#F0E442", mec="black", ms=6)
        ax.annotate(t["name"], (t["x"], t["y"]), xytext=(4, 3), textcoords="offset points", fontsize=7, color="#F0E442")
    ax.set_xlabel("x east (m, local grid)")
    ax.set_ylabel("y north (m)")
    ax.text(0.01, 0.01, "dots = ROVER position at drop, not the tube itself", transform=ax.transAxes, fontsize=8,
            bbox=dict(fc="white", alpha=0.85))
    _save(fig, "10_depot_closeup")

    # rover photo contact sheet
    photos = vec["pov"]["photos"]
    cols = 6
    rows = int(np.ceil(len(photos) / cols))
    fig, axs = plt.subplots(rows, cols, figsize=(12, 2.1 * rows), dpi=DPI)
    for ax in axs.ravel():
        ax.axis("off")
    for ax, p in zip(axs.ravel(), photos):
        ax.imshow(Image.open(SITE / "assets" / p["file"]))
        ax.set_title(f"site {p['site']} · sol {p['sol']} · {p['instrument'].replace('_LEFT', '')}", fontsize=7)
    fig.suptitle("Real rover photos, one per rover site in the study area (raw images)", fontsize=11, x=0.01, ha="left")
    fig.text(0.01, 0.005, vec["pov"]["credit"], fontsize=7, color="#444")
    fig.tight_layout(rect=(0, 0.02, 1, 0.97))
    fig.savefig(PREVIEWS / "11_pov_photos.png", dpi=DPI)
    plt.close(fig)

    # HiRISE vs CTX
    ctx = read("ctx_dtm_20m")
    k = 10
    hi20 = np.nanmean(dtm.reshape(dtm.shape[0] // k, k, dtm.shape[1] // k, k), axis=(1, 3))
    d = hi20 - ctx
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.8), dpi=DPI, gridspec_kw={"width_ratios": [1.2, 1]})
    im = a1.imshow(d, extent=ext, cmap="RdBu_r", vmin=-10, vmax=10)
    fig.colorbar(im, ax=a1, shrink=0.85, label="HiRISE minus CTX (m)")
    a1.set_title("Check: HiRISE 1 m DTM vs CTX 20 m DTM", loc="left", fontweight="bold", fontsize=11)
    a1.set_xlabel("x east (km)")
    a1.set_ylabel("y north (km)")
    dd = d[np.isfinite(d)]
    a2.hist(dd, bins=80, color="#0072B2")
    a2.set_xlabel("HiRISE minus CTX (m), 20 m cells")
    a2.set_ylabel("cells")
    a2.set_title(f"mean {dd.mean():.2f} m · std {dd.std():.2f} m · n {dd.size:,}", fontsize=10)
    fig.text(0.01, 0.005, "HiRISE DTM: USGS doi:10.5066/P9REJ9JN (HiRISE: NASA/JPL-Caltech/UArizona). CTX DTM: USGS doi:10.5066/P906QQT8 (CTX: NASA/JPL-Caltech/MSSS)",
             fontsize=6.5, color="#444")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(PREVIEWS / "12_check_hirise_vs_ctx.png", dpi=DPI)
    plt.close(fig)

    # web cost grid
    cg = np.load(PROCESSED / "cost_grid_web.npz")
    meta = man["cost_grid"]
    fig, ax = _frame(f"Browser cost grid ({meta['cell_m']:g} m, {meta['rows']}x{meta['cols']}): P90 slope + no-go",
                     "assumption", L["slope"]["credit"])
    im = ax.imshow(cg["slope"], extent=ext, cmap="viridis", vmin=0, vmax=40, interpolation="nearest")
    ng = (cg["slope"] > meta["defaults"]["slope_nogo_deg"]) | (cg["rough"] > meta["defaults"]["roughness_nogo_m"]) | cg["nodata"].astype(bool)
    ax.imshow(np.where(ng, 1.0, np.nan), extent=ext, cmap=ListedColormap([L["nogo"]["color"]]), interpolation="nearest")
    fig.colorbar(im, ax=ax, shrink=0.8, label="P90 slope in cell (deg)")
    ax.text(0.99, 0.01, f"no-go (orange): {ng.mean() * 100:.1f}% of cells", transform=ax.transAxes, ha="right",
            fontsize=9, bbox=dict(fc="white", alpha=0.8))
    _depot(ax, depot)
    ax.legend(loc="lower left", fontsize=8)
    _save(fig, "13_web_cost_grid")

    # overview sheet of the six main layers
    names = ["01_ortho", "04_slope", "06_nogo", "09_rover_traverse_depot", "08_themis_night", "10_depot_closeup"]
    ims = [Image.open(PREVIEWS / f"{n}.png").convert("RGB") for n in names]
    w, h = 560, 500
    sheet = Image.new("RGB", (w * 3, h * 2), "white")
    for i, im in enumerate(ims):
        im.thumbnail((w, h))
        sheet.paste(im, ((i % 3) * w, (i // 3) * h))
    sheet.quantize(colors=192).save(PREVIEWS / "00_overview.png", optimize=True)


def main():
    make_all(load_params())
    for f in sorted(PREVIEWS.glob("*.png")):
        print(f"{f.name}: {f.stat().st_size / 1e3:.0f} KB")


if __name__ == "__main__":
    main()
