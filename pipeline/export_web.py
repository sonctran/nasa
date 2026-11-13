"""Step 3: turn processed layers into small web assets for the static site.

Outputs (all committed; total kept small):
  site/assets/layers/*.png|jpg    image overlays (local grid, north-up)
  site/assets/data/layers.json    manifest: file, bounds, units, label, legend, credit
  site/assets/data/cost_grid.bin  + cost_grid.json   10 m grid for browser A*
  site/assets/data/vectors.json   traverse, waypoints, depot, POV photo spots (local metres)
  site/assets/pov/*.jpg           real rover photos (credited)

Leaflet (L.CRS.Simple) bounds are [[y_min, x_min], [y_max, x_max]] in local metres.
Run: python -m pipeline.export_web
"""
from __future__ import annotations

import json
import shutil

import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image
from rasterio.enums import Resampling

from .common import PROCESSED, RAW, SITE, SITE_DATA, SITE_LAYERS, Grid, grid_from_params, load_params, pv
from .crop import block_reduce, warp_to_grid

HIRISE = "HiRISE data: NASA/JPL-Caltech/University of Arizona"
DTM_CREDIT = f"DTM mosaic: Fergason, Galuszka & Hare 2020, USGS, doi:10.5066/P9REJ9JN. {HIRISE}"
ORTHO_CREDIT = f"Orthomosaic: Fergason, Galuszka & Hare 2020, USGS, doi:10.5066/P9QJDP48. {HIRISE}"
THEMIS_CREDIT = "THEMIS IR mosaic: NASA/JPL-Caltech/Arizona State University, via NASA Mars Trek"
NOGO_RGB = (213, 94, 0)  # Okabe-Ito vermillion: visible to common colour-vision deficiencies


def read(name: str) -> np.ndarray:
    with rasterio.open(PROCESSED / f"{name}.tif") as s:
        return s.read(1)


def bounds(grid: Grid) -> list:
    w, h = grid.size_m
    return [[0.0, 0.0], [h, w]]


def palette_png(a: np.ndarray, vmin: float, vmax: float, cmap: str, n: int, path, alpha: int = 255):
    """Quantise to n colour bins + 1 transparent index (NaN). Small files, exact legend."""
    idx = np.clip(((a - vmin) / (vmax - vmin) * n).astype("int32"), 0, n - 1)
    idx = np.where(np.isfinite(a), idx + 1, 0).astype("uint8")
    cm = colormaps[cmap].resampled(n)
    pal = [0, 0, 0] + [int(round(c * 255)) for i in range(n) for c in cm(i)[:3]]
    im = Image.fromarray(idx, mode="P")
    im.putpalette(pal + [0] * (768 - len(pal)))
    trans = bytes([0] + [alpha] * n)
    im.save(path, optimize=True, transparency=trans)
    stops = [{"value": round(vmin + (vmax - vmin) * i / n, 4), "color": "#%02x%02x%02x" % tuple(pal[3 + 3 * i:6 + 3 * i])}
             for i in range(n)]
    return stops


def stretch(a: np.ndarray, lo=0.5, hi=99.5) -> tuple[np.ndarray, list]:
    p0, p1 = np.nanpercentile(a, [lo, hi])
    out = np.clip((a - p0) / (p1 - p0) * 255.0, 0, 255)
    return np.where(np.isfinite(a), out, 0).astype("uint8"), [float(p0), float(p1)]


def export_layers(params: dict) -> dict:
    SITE_LAYERS.mkdir(parents=True, exist_ok=True)
    g2 = grid_from_params(params, "grid.analysis_cell_m")
    b = bounds(g2)
    man = {"crs": "local metres, origin at AOI south-west corner, x east, y north",
           "aoi": {"size_m": list(g2.size_m), "anchor_lonlat": [g2.anchor_lon, g2.anchor_lat],
                   "anchor_local": list(g2.lonlat_to_local(g2.anchor_lon, g2.anchor_lat)),
                   "corners_lonlat": g2.corners_lonlat(),
                   "projection": g2.crs.to_proj4()},
           "layers": []}

    def add(**kw):
        man["layers"].append({"bounds": b, **kw})

    ortho = read("ortho_1m")
    o8, rng = stretch(ortho)
    Image.fromarray(o8, mode="L").save(SITE_LAYERS / "ortho.jpg", quality=80, optimize=True, progressive=True)
    add(id="ortho", title="HiRISE image (base map)", file="layers/ortho.jpg", kind="real", units="brightness (DN)",
        cell_m=pv(params, "grid.ortho_display_cell_m"), credit=ORTHO_CREDIT,
        processing=f"25 cm mosaic averaged to 1 m, reprojected, linear stretch DN {rng[0]:.0f}-{rng[1]:.0f}")

    dtm = read("dtm")
    lo, hi = float(np.nanmin(dtm)), float(np.nanmax(dtm))
    stops = palette_png(dtm, lo, hi, "cividis", 32, SITE_LAYERS / "elevation.png")
    add(id="elevation", title="Elevation", file="layers/elevation.png", kind="real", units="m (areoid)",
        cell_m=g2.cell, credit=DTM_CREDIT, legend=stops)

    hill = read("hillshade")
    Image.fromarray((np.nan_to_num(hill) * 255).astype("uint8"), mode="L").save(SITE_LAYERS / "hillshade.png", optimize=True)
    add(id="hillshade", title="Hillshade", file="layers/hillshade.png", kind="derived", units="-",
        cell_m=g2.cell, credit=DTM_CREDIT, processing="Lambertian, sun azimuth 315 deg, altitude 45 deg")

    slope = read("slope")
    stops = palette_png(slope, 0.0, 40.0, "viridis", 40, SITE_LAYERS / "slope.png")
    add(id="slope", title="Slope", file="layers/slope.png", kind="derived", units="deg", cell_m=g2.cell,
        credit=DTM_CREDIT, legend=stops, processing="Horn (1981) 3x3 on the 2 m grid; values above 40 deg shown as 40")

    rough = read("roughness")
    stops = palette_png(rough, 0.0, 0.3, "magma", 30, SITE_LAYERS / "roughness.png")
    add(id="roughness", title="Roughness", file="layers/roughness.png", kind="derived", units="m RMS",
        cell_m=g2.cell, credit=DTM_CREDIT, legend=stops,
        processing=f"Detrended RMS relief, {pv(params, 'terrain.roughness_window_m')} m window on 1 m DTM, averaged to 2 m; above 0.3 m shown as 0.3")

    nogo = read("nogo").astype(bool)
    im = Image.fromarray(nogo.astype("uint8"), mode="P")  # index 0 = clear, 1 = no-go
    im.putpalette([0, 0, 0, *NOGO_RGB] + [0] * (768 - 6))
    im.save(SITE_LAYERS / "nogo.png", optimize=True, transparency=bytes([0, 255]))
    add(id="nogo", title="No-go zones", file="layers/nogo.png", kind="assumption", units="-", cell_m=g2.cell,
        credit=DTM_CREDIT, color="#%02x%02x%02x" % NOGO_RGB,
        processing=(f"slope > {pv(params, 'terrain.slope_nogo_deg')} deg OR roughness > "
                    f"{pv(params, 'terrain.roughness_nogo_m')} m OR no data (thresholds are assumptions)"))

    for key, title in (("themis_day", "THEMIS daytime IR"), ("themis_night", "THEMIS night-time IR")):
        a = read(key)
        a8, rng = stretch(a, 1, 99)
        Image.fromarray(a8, mode="L").save(SITE_LAYERS / f"{key}.png", optimize=True)
        add(id=key, title=title, file=f"layers/{key}.png", kind="proxy", units="relative brightness",
            cell_m=20.0, native_m_per_px=81.4, credit=THEMIS_CREDIT,
            processing=f"WMTS zoom 9 tile (~81 m/px), resampled to 20 m; stretch DN {rng[0]:.0f}-{rng[1]:.0f}",
            note="Qualitative mosaic, not calibrated temperature or thermal inertia. Proxy for loose vs. rocky ground.")

    # 25 cm depot close-up
    cx, cy = g2.lonlat_to_local(g2.anchor_lon, g2.anchor_lat)
    close = Grid(g2.anchor_lon, g2.anchor_lat, -50, -50, 50, 50, 0.25)
    c = warp_to_grid(RAW / "ortho_hirise_25cm_depot_native.tif", close, Resampling.bilinear)
    c8, rng = stretch(c)
    Image.fromarray(c8, mode="L").save(SITE_LAYERS / "depot_closeup.jpg", quality=85, optimize=True)
    man["closeups"] = [{"id": "depot_closeup", "file": "layers/depot_closeup.jpg", "cell_m": 0.25, "kind": "real",
                        "bounds": [[cy - 50, cx - 50], [cy + 50, cx + 50]], "credit": ORTHO_CREDIT,
                        "processing": f"25 cm, reprojected; stretch DN {rng[0]:.0f}-{rng[1]:.0f}"}]
    return man


def export_cost_grid(params: dict) -> dict:
    """10 m grid for browser A*: elevation mean, P90 slope and roughness, no-data flag."""
    g2 = grid_from_params(params, "grid.analysis_cell_m")
    gw = grid_from_params(params, "grid.web_cell_m")
    k = int(round(gw.cell / g2.cell))
    pct = f"p{pv(params, 'terrain.web_aggregate_percentile')}"
    dtm, slope, rough = read("dtm"), read("slope"), read("roughness")
    elev = block_reduce(dtm, k, "mean").astype("<f4")
    s90 = block_reduce(slope, k, pct)
    r90 = block_reduce(rough, k, pct)
    nod = (block_reduce(dtm, k, "anynan") | ~np.isfinite(s90) | ~np.isfinite(r90)).astype("u1")
    s_q = np.round(np.nan_to_num(s90) * 100).clip(0, 65535).astype("<u2")      # 0.01 deg
    r_q = np.round(np.nan_to_num(r90) * 1000).clip(0, 65535).astype("<u2")     # 1 mm
    blob = elev.tobytes() + s_q.tobytes() + r_q.tobytes() + nod.tobytes()
    (SITE_DATA / "cost_grid.bin").write_bytes(blob)
    n = elev.size
    meta = {
        "format": "little-endian, row-major, row 0 = NORTH edge",
        "rows": gw.height, "cols": gw.width, "cell_m": gw.cell, "bounds": bounds(gw),
        "arrays": [
            {"name": "elev_m", "dtype": "float32", "offset": 0, "count": n, "scale": 1.0,
             "how": f"mean of {k}x{k} analysis cells"},
            {"name": "slope_deg", "dtype": "uint16", "offset": 4 * n, "count": n, "scale": 0.01,
             "how": f"{pct} of {k}x{k} analysis-cell slopes"},
            {"name": "rough_m", "dtype": "uint16", "offset": 6 * n, "count": n, "scale": 0.001,
             "how": f"{pct} of {k}x{k} analysis-cell roughness"},
            {"name": "nodata", "dtype": "uint8", "offset": 8 * n, "count": n, "scale": 1,
             "how": "1 if any analysis cell in the block has no data"}],
        "defaults": {"slope_nogo_deg": pv(params, "terrain.slope_nogo_deg"),
                     "roughness_nogo_m": pv(params, "terrain.roughness_nogo_m")},
        "bytes": len(blob),
    }
    nogo = (s90 > meta["defaults"]["slope_nogo_deg"]) | (r90 > meta["defaults"]["roughness_nogo_m"]) | nod.astype(bool)
    meta["nogo_fraction_at_defaults"] = round(float(nogo.mean()), 4)
    (SITE_DATA / "cost_grid.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    np.savez_compressed(PROCESSED / "cost_grid_web.npz", elev=elev, slope=s90, rough=r90, nodata=nod)
    return meta


def export_vectors(params: dict) -> dict:
    vec = json.loads((PROCESSED / "vectors.json").read_text(encoding="utf-8"))
    pov_dir = SITE / "assets" / "pov"
    pov_dir.mkdir(parents=True, exist_ok=True)
    pov = []
    for p in vec["pov"]:
        ph = p.get("photo")
        if not ph:
            continue
        shutil.copy2(RAW / "pov" / ph["file"], pov_dir / ph["file"])
        pov.append({"site": p["site"], "sols": p["sols"], **ph, "file": f"pov/{ph['file']}"})
    out = {
        "traverse": {"credit": "Perseverance traverse: NASA/JPL-Caltech (MMGIS M20_traverse.json)", "kind": "real",
                     "lines": [{"sol": t["sol"], "xy": t["xy"]} for t in vec["traverse"]]},
        "waypoints": {"credit": "Perseverance waypoints: NASA/JPL-Caltech (MMGIS M20_waypoints.json)", "kind": "real",
                      "points": vec["waypoints"]},
        "depot_tubes": {"credit": "Three Forks depot: NASA PDS Geosciences Node, mars2020_sample_depot_three_forks",
                        "kind": "real", "note": "Positions are the ROVER's location at each drop, not the tube's own position.",
                        "points": vec["depot_tubes"]},
        "pov": {"credit": "Rover photos: NASA/JPL-Caltech (Mastcam-Z: NASA/JPL-Caltech/ASU)", "kind": "real",
                "note": "One photo per rover site; x, y = nearest waypoint of that drive.", "photos": pov},
    }
    (SITE_DATA / "vectors.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    return out


def main() -> None:
    params = load_params()
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    man = export_layers(params)
    man["cost_grid"] = export_cost_grid(params)
    export_vectors(params)
    (SITE_DATA / "layers.json").write_text(json.dumps(man, indent=2), encoding="utf-8")
    total = sum(f.stat().st_size for f in (SITE / "assets").rglob("*") if f.is_file())
    print(f"site/assets total: {total / 1e6:.2f} MB")
    for f in sorted((SITE / "assets").rglob("*")):
        if f.is_file() and f.stat().st_size > 200_000:
            print(f"  {f.relative_to(SITE)}: {f.stat().st_size / 1e6:.2f} MB")
    print(f"web grid no-go fraction: {man['cost_grid']['nogo_fraction_at_defaults']}")


if __name__ == "__main__":
    main()
