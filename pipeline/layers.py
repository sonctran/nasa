"""Step 2: build every analysis layer on the local AOI grid (data/processed/, git-ignored).

Rasters (north-up, local grid, origin = AOI south-west corner):
  dtm_1m, roughness_1m                      1 m   (4000 x 4000)
  dtm, slope, roughness, hillshade, nogo    2 m   (2000 x 2000)  <- analysis grid
  ortho_1m                                  1 m   (display base map)
  ctx_dtm_20m, themis_day, themis_night     20 m  (coarse context / proxy)
Vectors (local metres): rover traverse, waypoints, depot tubes, POV photo spots.
Also checks the DTM against independent elevations (rover, CTX DTM).

Run: python -m pipeline.layers
"""
from __future__ import annotations

import csv
import json

import numpy as np
import rasterio
from rasterio.enums import Resampling

from .common import PROCESSED, RAW, SITE_DATA, Grid, grid_from_params, load_params, pv
from .crop import block_reduce, warp_to_grid
from .derive import hillshade, nogo_mask, roughness_rms, slope_deg


def save_tif(name: str, a: np.ndarray, grid: Grid) -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    dtype = "uint8" if a.dtype == bool else "float32"
    with rasterio.open(PROCESSED / f"{name}.tif", "w", driver="GTiff", width=grid.width, height=grid.height,
                       count=1, dtype=dtype, crs=grid.crs, transform=grid.transform, compress="deflate",
                       nodata=None if dtype == "uint8" else np.nan) as d:
        d.write(a.astype(dtype), 1)


def build_rasters(params: dict) -> dict:
    g2 = grid_from_params(params, "grid.analysis_cell_m")
    g1 = grid_from_params(params, "grid.dtm_cell_m")
    k = int(round(g2.cell / g1.cell))

    dtm1 = warp_to_grid(RAW / "dtm_hirise_1m_aoi_native.tif", g1, Resampling.bilinear)
    win = int(round(pv(params, "terrain.roughness_window_m") / g1.cell)) | 1
    rough1 = roughness_rms(dtm1, win)

    dtm = block_reduce(dtm1, k, "mean")
    dtm[block_reduce(dtm1, k, "anynan")] = np.nan       # any hole in a block -> no data
    rough = block_reduce(rough1, k, "mean")
    rough[np.isnan(dtm)] = np.nan
    slope = slope_deg(dtm, g2.cell)
    hill = hillshade(dtm, g2.cell, pv(params, "terrain.hillshade_azimuth_deg"),
                     pv(params, "terrain.hillshade_altitude_deg"))
    nogo = nogo_mask(slope, rough, pv(params, "terrain.slope_nogo_deg"), pv(params, "terrain.roughness_nogo_m"))

    ortho = warp_to_grid(RAW / "ortho_hirise_1m_aoi_native.tif", g1.with_cell(pv(params, "grid.ortho_display_cell_m")))

    g20 = g2.with_cell(20.0)
    ctx = warp_to_grid(RAW / "dtm_ctx_20m_aoi_native.tif", g20, Resampling.bilinear)
    th_day = warp_to_grid(RAW / "themis_day_ir_aoi.tif", g20, Resampling.bilinear)
    th_night = warp_to_grid(RAW / "themis_night_ir_aoi.tif", g20, Resampling.bilinear)

    out = {"dtm_1m": (dtm1, g1), "roughness_1m": (rough1, g1), "dtm": (dtm, g2), "slope": (slope, g2),
           "roughness": (rough, g2), "hillshade": (hill, g2), "nogo": (nogo, g2), "ortho_1m": (ortho, g1),
           "ctx_dtm_20m": (ctx, g20), "themis_day": (th_day, g20), "themis_night": (th_night, g20)}
    for name, (a, g) in out.items():
        save_tif(name, a, g)
    return out


def _clip_line(coords, grid: Grid):
    W, H = grid.size_m
    pts = [grid.lonlat_to_local(c[0], c[1]) for c in coords]
    inside = [0 <= x <= W and 0 <= y <= H for x, y in pts]
    segs, cur = [], []
    for p, ok in zip(pts, inside):
        if ok:
            cur.append([round(p[0], 2), round(p[1], 2)])
        elif cur:
            segs.append(cur)
            cur = []
    if cur:
        segs.append(cur)
    return [s for s in segs if len(s) >= 2]


def sample(a: np.ndarray, grid: Grid, lx: float, ly: float) -> float:
    r, c = grid.local_to_rowcol(lx, ly)
    if 0 <= r < grid.height and 0 <= c < grid.width:
        return float(a[r, c])
    return float("nan")


def build_vectors(params: dict, rasters: dict) -> dict:
    g = grid_from_params(params)
    dtm1, g1 = rasters["dtm_1m"]
    W, H = g.size_m

    trav = json.loads((RAW / "M20_traverse.json").read_text(encoding="utf-8"))["features"]
    lines = []
    for f in trav:
        geom = f["geometry"]
        parts = geom["coordinates"] if geom["type"] == "MultiLineString" else [geom["coordinates"]]
        for part in parts:
            for seg in _clip_line(part, g):
                lines.append({"sol": f["properties"]["sol"], "from": f["properties"].get("fromRMC"),
                              "to": f["properties"].get("toRMC"), "xy": seg})

    wps = []
    for f in json.loads((RAW / "M20_waypoints.json").read_text(encoding="utf-8"))["features"]:
        p = f["properties"]
        x, y = g.lonlat_to_local(p["lon"], p["lat"])
        if 0 <= x <= W and 0 <= y <= H:
            wps.append({"rmc": p["RMC"], "site": p["site"], "drive": p["drive"], "sol": p["sol"],
                        "x": round(x, 2), "y": round(y, 2), "elev_rover_m": p["elev_geoid"],
                        "elev_dtm_m": round(sample(dtm1, g1, x, y), 3), "note": p.get("Note", "")})

    tubes = []
    with open(RAW / "depot" / "sample_tube_locations.csv", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            x, y = g.lonlat_to_local(float(row["Rover Longitude"]), float(row["Rover Latitude"]))
            tubes.append({"sample": row["Sample Designation"], "name": row["Sample Name"],
                          "drop_sol": int(row["Dropoff Sol"]), "x": round(x, 2), "y": round(y, 2),
                          "elev_rover_m": float(row["Rover Elevation"]),
                          "elev_dtm_m": round(sample(dtm1, g1, x, y), 3),
                          "tube_azimuth_deg": int(row["Sample Tube Azimuth"]),
                          "position_type": "rover position at drop (not the tube itself)"})

    pov_idx = RAW / "pov" / "pov_index.json"
    pov = json.loads(pov_idx.read_text(encoding="utf-8")) if pov_idx.exists() else []

    vec = {"traverse": lines, "waypoints": wps, "depot_tubes": tubes, "pov": pov}
    (PROCESSED / "vectors.json").write_text(json.dumps(vec), encoding="utf-8")
    return vec


def checks(params: dict, rasters: dict, vec: dict) -> dict:
    """Independent cross-checks on the DTM (reported in DATA_SOURCES.md / PROGRESS.md)."""
    dtm, g2 = rasters["dtm"]
    slope, _ = rasters["slope"]
    rough, _ = rasters["roughness"]
    nogo, _ = rasters["nogo"]
    ctx, g20 = rasters["ctx_dtm_20m"]

    def stats(d):
        d = np.asarray([v for v in d if np.isfinite(v)])
        return {"n": int(d.size), "mean_m": round(float(d.mean()), 3), "median_m": round(float(np.median(d)), 3),
                "std_m": round(float(d.std()), 3), "rms_m": round(float(np.sqrt((d ** 2).mean())), 3),
                "max_abs_m": round(float(np.abs(d).max()), 3)} if d.size else {"n": 0}

    wp_diff = [w["elev_dtm_m"] - w["elev_rover_m"] for w in vec["waypoints"]]
    tube_diff = [t["elev_dtm_m"] - t["elev_rover_m"] for t in vec["depot_tubes"]]
    hi20 = block_reduce(dtm, 10, "mean")
    ctx_diff = (hi20 - ctx)[np.isfinite(hi20) & np.isfinite(ctx)]

    valid = np.isfinite(dtm)
    res = {
        "grid": {"analysis_cell_m": g2.cell, "shape": list(g2.shape), "size_m": list(g2.size_m),
                 "corners_lonlat": g2.corners_lonlat()},
        "dtm": {"valid_fraction": round(float(valid.mean()), 5),
                "elev_min_m": round(float(np.nanmin(dtm)), 2), "elev_max_m": round(float(np.nanmax(dtm)), 2)},
        "slope_deg": {p: round(float(np.nanpercentile(slope, q)), 2) for p, q in
                      (("p50", 50), ("p90", 90), ("p99", 99), ("max", 100))},
        "roughness_m": {p: round(float(np.nanpercentile(rough, q)), 3) for p, q in
                        (("p50", 50), ("p90", 90), ("p99", 99), ("max", 100))},
        "nogo_fraction": round(float(nogo.mean()), 4),
        "nogo_fraction_by_cause": {
            "slope": round(float((slope > pv(params, "terrain.slope_nogo_deg")).mean()), 4),
            "roughness": round(float((rough > pv(params, "terrain.roughness_nogo_m")).mean()), 4),
            "nodata": round(float((~valid).mean()), 4)},
        "dtm_minus_rover_elev_waypoints": stats(wp_diff),
        "dtm_minus_rover_elev_depot": stats(tube_diff),
        "hirise_minus_ctx_20m": stats(ctx_diff.tolist()),
        "counts": {"traverse_segments": len(vec["traverse"]), "waypoints": len(vec["waypoints"]),
                   "depot_tubes": len(vec["depot_tubes"]),
                   "pov_photos": sum(1 for p in vec["pov"] if p.get("photo"))},
    }
    (PROCESSED / "checks.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    SITE_DATA.mkdir(parents=True, exist_ok=True)  # committed copy, for the app's Methods page
    (SITE_DATA / "checks.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    return res


def main() -> None:
    params = load_params()
    rasters = build_rasters(params)
    vec = build_vectors(params, rasters)
    res = checks(params, rasters, vec)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
