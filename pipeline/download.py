"""Step 1: fetch every raw input into data/raw/ (git-ignored). Safe to re-run: skips files it has.

Large rasters are never downloaded whole: only the AOI window is read over HTTP
(GDAL /vsicurl/ range requests) and saved as a small local GeoTIFF.

Run:  python -m pipeline.download            (everything)
      python -m pipeline.download rover dtm  (just some steps)
"""
from __future__ import annotations

import io
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
import requests
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import from_origin

from .common import RAW, SITE, SITE_DATA, grid_from_params, load_params
from .crop import save_native_crop

USGS = "https://planetarymaps.usgs.gov/mosaic/mars2020_trn"
PDS_DEPOT = "https://pds-geosciences.wustl.edu/m2020/urn-nasa-pds-mars2020_sample_depot_three_forks"

SOURCES = {
    "dtm_hirise": f"{USGS}/HiRISE/JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif",
    "dtm_ctx": f"{USGS}/CTX/JEZ_ctx_B_soc_008_DTM_MOLAtopography_DeltaGeoid_20m_Eqc_latTs0_lon0.tif",
    "ortho_hirise": f"{USGS}/HiRISE/JEZ_hirise_soc_007_orthoMosaic_25cm_Ortho_blend120.tif",
    "m20_waypoints": "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json",
    "m20_traverse": "https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json",
    "depot_tube_locations": f"{PDS_DEPOT}/miscellaneous/sample_metadata/sample_tube_locations.csv",
    "depot_tube_locations_label": f"{PDS_DEPOT}/miscellaneous/sample_metadata/sample_tube_locations.xml",
    "depot_tube_event_sols": f"{PDS_DEPOT}/miscellaneous/sample_metadata/sample_tube_event_sols.csv",
    "depot_tube_identifiers": f"{PDS_DEPOT}/miscellaneous/sample_metadata/sample_tube_identifiers.csv",
    "depot_campaign_sols": f"{PDS_DEPOT}/miscellaneous/depot/campaign_sols.csv",
    "themis_day": "https://trek.nasa.gov/tiles/Mars/EQ/THEMIS_DayIR_ControlledMosaics_100m_v2_oct2018/1.0.0",
    "themis_night": "https://trek.nasa.gov/tiles/Mars/EQ/THEMIS_NightIR_ControlledMosaics_100m_v2_oct2018/1.0.0",
    "raw_images_api": "https://mars.nasa.gov/rss/api/?feed=raw_images&category=mars2020&feedtype=json",
    "donki_sep": "https://api.nasa.gov/DONKI/SEP",
}

LOG = RAW / "fetch_log.json"
UA = {"User-Agent": "marswalk-ops-data-pipeline/0.1 (NASA Space Apps 2026 student project)"}


# --- helpers -----------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(key: str, **info) -> None:
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}
    log[key] = {"accessed_utc": _now(), **info}
    LOG.write_text(json.dumps(log, indent=2), encoding="utf-8")


def get(url: str, params: dict | None = None, tries: int = 4, timeout: int = 120) -> requests.Response:
    for k in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code in (403, 404):
                r.raise_for_status()
        except requests.RequestException:
            if k == tries - 1:
                raise
        time.sleep(2 ** k)
    r.raise_for_status()
    return r


def fetch_file(key: str, url: str, out: Path, force: bool = False) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not force:
        return out
    r = get(url)
    out.write_bytes(r.content)
    _log(key, url=url, bytes=len(r.content), path=str(out.relative_to(RAW.parent.parent)))
    print(f"  {key}: {len(r.content):,} B")
    return out


# --- steps -------------------------------------------------------------------------
def step_rover(params):
    fetch_file("m20_waypoints", SOURCES["m20_waypoints"], RAW / "M20_waypoints.json")
    fetch_file("m20_traverse", SOURCES["m20_traverse"], RAW / "M20_traverse.json")


def step_depot(params):
    for key in ("depot_tube_locations", "depot_tube_locations_label", "depot_tube_event_sols",
                "depot_tube_identifiers", "depot_campaign_sols"):
        url = SOURCES[key]
        fetch_file(key, url, RAW / "depot" / url.rsplit("/", 1)[1])


def _raster_step(key: str, params, out: Path, margin: float, decimate: int = 1):
    if out.exists():
        return
    grid = grid_from_params(params)
    t = time.time()
    info = save_native_crop(SOURCES[key], grid, out, margin_m=margin, decimate=decimate)
    info["seconds"] = round(time.time() - t, 1)
    info["bytes_on_disk"] = out.stat().st_size
    _log(key, url=SOURCES[key], **info)
    print(f"  {key}: window {info['source_window']} -> {out.name} ({info['seconds']} s)")


def step_dtm(params):
    _raster_step("dtm_hirise", params, RAW / "dtm_hirise_1m_aoi_native.tif", margin=100.0)


def step_ctx(params):
    _raster_step("dtm_ctx", params, RAW / "dtm_ctx_20m_aoi_native.tif", margin=500.0)


def step_ortho(params):
    # 25 cm -> 1 m by 4 x 4 block mean, in the mosaic's own (orthographic) CRS
    _raster_step("ortho_hirise", params, RAW / "ortho_hirise_1m_aoi_native.tif", margin=50.0, decimate=4)


def step_ortho_closeups(params):
    """Full-resolution (25 cm) crops for close-ups. Phase 1: the depot only (+-60 m)."""
    out = RAW / "ortho_hirise_25cm_depot_native.tif"
    if out.exists():
        return
    from .common import Grid
    g = grid_from_params(params)
    depot = Grid(g.anchor_lon, g.anchor_lat, -60, -60, 60, 60, 0.25)
    info = save_native_crop(SOURCES["ortho_hirise"], depot, out, margin_m=5.0)
    _log("ortho_hirise_depot_25cm", url=SOURCES["ortho_hirise"], **info)


def _themis(key: str, params, out: Path, zoom: int = 9):
    """Mosaic Mars Trek WMTS tiles (geographic, 256 px, TopLeft = -180, 90) over the AOI."""
    if out.exists():
        return
    grid = grid_from_params(params)
    c = grid.corners_lonlat()
    n_cols, n_rows = 2 ** (zoom + 1), 2 ** zoom  # from WMTSCapabilities: MatrixWidth/Height
    tdeg = 360.0 / n_cols
    pad = 0.02  # deg margin
    col0, col1 = math.floor((c["west_lon"] - pad + 180) / tdeg), math.floor((c["east_lon"] + pad + 180) / tdeg)
    row0, row1 = math.floor((90 - c["north_lat"] - pad) / tdeg), math.floor((90 - c["south_lat"] + pad) / tdeg)
    mosaic = np.zeros(((row1 - row0 + 1) * 256, (col1 - col0 + 1) * 256), dtype="uint8")
    urls = []
    for r in range(row0, row1 + 1):
        for cc in range(col0, col1 + 1):
            url = f"{SOURCES[key]}/default/default028mm/{zoom}/{r}/{cc}.png"
            img = Image.open(io.BytesIO(get(url).content))
            arr = np.asarray(img.convert("L"))
            mosaic[(r - row0) * 256:(r - row0 + 1) * 256, (cc - col0) * 256:(cc - col0 + 1) * 256] = arr
            urls.append(url)
    px = tdeg / 256
    crs = CRS.from_proj4("+proj=longlat +R=3396190 +no_defs")
    with rasterio.open(out, "w", driver="GTiff", width=mosaic.shape[1], height=mosaic.shape[0], count=1,
                       dtype="uint8", crs=crs, transform=from_origin(-180 + col0 * tdeg, 90 - row0 * tdeg, px, px),
                       nodata=0) as dst:
        dst.write(mosaic, 1)
    _log(key, url=SOURCES[key], tiles=urls, zoom=zoom, deg_per_px=px,
         m_per_px_at_equator=px * math.pi / 180 * 3396190, path=str(out))
    print(f"  {key}: {len(urls)} tiles")


def step_themis(params):
    _themis("themis_day", params, RAW / "themis_day_ir_aoi.tif")
    _themis("themis_night", params, RAW / "themis_night_ir_aoi.tif")


def _aoi_sites(params) -> dict[int, list[dict]]:
    """Rover waypoints inside the AOI, grouped by rover 'site' number."""
    grid = grid_from_params(params)
    w = json.loads((RAW / "M20_waypoints.json").read_text(encoding="utf-8"))["features"]
    sites: dict[int, list[dict]] = {}
    W, H = grid.size_m
    for f in w:
        p = f["properties"]
        x, y = grid.lonlat_to_local(p["lon"], p["lat"])
        if 0 <= x <= W and 0 <= y <= H:
            sites.setdefault(int(p["site"]), []).append({**p, "x": x, "y": y})
    return sites


PREFERRED_CAMS = ["MCZ_LEFT", "NAVCAM_LEFT"]


def _good_view(img: dict, site: int) -> bool:
    """Full-frame terrain view from this site: no thumbnails, subframes, sky or deck shots."""
    try:
        cam, ext = img["camera"], img["extended"]
        if int(img.get("site", -1)) != site or img.get("sample_type") != "Full":
            return False
        if cam["instrument"] not in PREFERRED_CAMS:
            return False
        if cam["instrument"] == "MCZ_LEFT" and cam.get("filter_name") != "ZCAM_L0_RGB":
            return False  # colour (Bayer RGB) frames only
        w, h = (int(v) for v in ext["dimension"].strip("()").split(","))
        el = float(ext["mastEl"])
    except (KeyError, ValueError):
        return False
    return w >= 1200 and h >= 900 and -20.0 <= el <= 3.0


def step_pov(params):
    """Index of real rover photos for each rover site in the AOI + one 800 px photo per site."""
    out_index = RAW / "pov" / "pov_index.json"
    if out_index.exists():
        return
    (RAW / "pov").mkdir(parents=True, exist_ok=True)
    sites = _aoi_sites(params)
    index = []
    for site, wps in sorted(sites.items()):
        sols = sorted({p["sol"] for p in wps})
        # try the middle sol first, then the others, until a good photo is found
        mid = sols[len(sols) // 2]
        order = [mid] + [s for s in sols if s != mid]
        pick = None
        for sol in order[:6]:
            cache = RAW / "pov" / f"raw_images_sol_{sol:04d}.json"
            if not cache.exists():
                r = get(SOURCES["raw_images_api"], params={"sol": sol})
                cache.write_bytes(r.content)
            imgs = json.loads(cache.read_text(encoding="utf-8")).get("images", [])
            cands = [i for i in imgs if _good_view(i, site)]
            if cands:
                # colour Mastcam-Z first, then Navcam; then the view closest to 8 deg below the
                # horizon (ground plus skyline: "what the crew would see"); imageid breaks ties
                cands.sort(key=lambda i: (PREFERRED_CAMS.index(i["camera"]["instrument"]),
                                          abs(float(i["extended"]["mastEl"]) + 8.0), i["imageid"]))
                pick = cands[0]
                break
        if not pick:
            index.append({"site": site, "sols": [sols[0], sols[-1]], "photo": None})
            continue
        drive = int(pick["drive"])
        wp = min(wps, key=lambda p: abs(int(p["drive"]) - drive))
        img_url = pick["image_files"]["medium"]
        fname = f"site{site:02d}_{pick['imageid']}_800.jpg"
        fetch_file(f"pov_site{site}", img_url, RAW / "pov" / fname)
        index.append({
            "site": site, "sols": [sols[0], sols[-1]], "photo": {
                "file": fname, "imageid": pick["imageid"], "sol": pick["sol"], "drive": drive,
                "instrument": pick["camera"]["instrument"], "credit": pick["credit"],
                "date_taken_utc": pick["date_taken_utc"], "page": pick["link"], "image_url": img_url,
                "nearest_waypoint_rmc": wp["RMC"], "x": wp["x"], "y": wp["y"],
            }})
    out_index.write_text(json.dumps(index, indent=2), encoding="utf-8")
    _log("raw_images_api", url=SOURCES["raw_images_api"], sites=len(index),
         photos=sum(1 for i in index if i["photo"]))
    print(f"  pov: {sum(1 for i in index if i['photo'])} photos for {len(index)} sites")


def step_donki(params):
    """One cached 60-day DONKI SEP window (API limit) for the SEP-alert replay."""
    start, end = "2024-05-01", "2024-06-29"
    out = SITE_DATA / f"donki_sep_{start}_{end}.json"
    if out.exists():
        return
    r = get(SOURCES["donki_sep"], params={"startDate": start, "endDate": end, "api_key": "DEMO_KEY"})
    events = r.json()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "source": f"{SOURCES['donki_sep']}?startDate={start}&endDate={end}",
        "accessed_utc": _now(),
        "label": "proxy: near-Earth SEP detections (NASA CCMC DONKI), not measured at Mars",
        "events": events}, indent=2), encoding="utf-8")
    _log("donki_sep", url=f"{SOURCES['donki_sep']}?startDate={start}&endDate={end}", events=len(events),
         path=str(out.relative_to(SITE.parent)))
    print(f"  donki: {len(events)} SEP events")


STEPS = {
    "rover": step_rover, "depot": step_depot, "dtm": step_dtm, "ctx": step_ctx, "ortho": step_ortho,
    "closeups": step_ortho_closeups, "themis": step_themis, "pov": step_pov, "donki": step_donki,
}


def main(argv: list[str]) -> None:
    params = load_params()
    RAW.mkdir(parents=True, exist_ok=True)
    for name in (argv or list(STEPS)):
        print(f"[download] {name}")
        STEPS[name](params)


if __name__ == "__main__":
    main(sys.argv[1:])
