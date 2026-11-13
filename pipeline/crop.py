"""Crop source rasters to the AOI and reproject them onto the local metric grid."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

from .common import Grid, gdal_env


def aoi_bounds_in(crs, grid: Grid, margin_m: float = 0.0) -> tuple[float, float, float, float]:
    """AOI bounding box (+ margin) expressed in another CRS (west, south, east, north)."""
    return transform_bounds(
        grid.crs, crs,
        grid.west - margin_m, grid.south - margin_m, grid.east + margin_m, grid.north + margin_m,
        densify_pts=50,
    )


def source_window(src, grid: Grid, margin_m: float) -> Window:
    """Integer pixel window of `src` that covers the AOI (+ margin), clipped to the raster."""
    b = aoi_bounds_in(src.crs, grid, margin_m)
    win = from_bounds(*b, transform=src.transform)
    col0, row0 = math.floor(win.col_off), math.floor(win.row_off)
    col1, row1 = math.ceil(win.col_off + win.width), math.ceil(win.row_off + win.height)
    col0, row0 = max(col0, 0), max(row0, 0)
    col1, row1 = min(col1, src.width), min(row1, src.height)
    if col1 <= col0 or row1 <= row0:
        raise ValueError("AOI does not overlap the source raster")
    return Window(col0, row0, col1 - col0, row1 - row0)


def save_native_crop(url_or_path: str, grid: Grid, out_path: Path, margin_m: float = 100.0,
                     decimate: int = 1, chunk_rows: int = 2048) -> dict:
    """Read the AOI window of a (possibly remote) raster in its own CRS and save it locally.

    `decimate` > 1 block-averages d x d source pixels into one (ignoring nodata), which is
    how the 25 cm orthomosaic (no internal overviews) is brought down to 1 m.
    Reads in row chunks so memory stays small. Returns a small info dict.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    src_name = url_or_path if "://" not in url_or_path else "/vsicurl/" + url_or_path
    with rasterio.Env(**gdal_env()), rasterio.open(src_name) as src:
        win = source_window(src, grid, margin_m)
        d = int(decimate)
        # trim to a multiple of d so blocks line up
        w_cols, w_rows = (int(win.width) // d) * d, (int(win.height) // d) * d
        win = Window(win.col_off, win.row_off, w_cols, w_rows)
        out_w, out_h = w_cols // d, w_rows // d
        src_t = src.window_transform(win)
        out_t = src_t @ Affine.scale(d, d)
        nodata = src.nodata
        dtype = "float32" if d > 1 or src.dtypes[0].startswith("float") else src.dtypes[0]
        profile = {
            "driver": "GTiff", "width": out_w, "height": out_h, "count": 1, "dtype": dtype,
            "crs": src.crs, "transform": out_t, "nodata": np.nan if dtype == "float32" else nodata,
            "tiled": True, "blockxsize": 256, "blockysize": 256, "compress": "deflate",
            "predictor": 3 if dtype == "float32" else 2, "BIGTIFF": "IF_SAFER",
        }
        chunk_rows = max(d, (chunk_rows // d) * d)
        with rasterio.open(out_path, "w", **profile) as dst:
            for r0 in range(0, w_rows, chunk_rows):
                nr = min(chunk_rows, w_rows - r0)
                sub = Window(win.col_off, win.row_off + r0, w_cols, nr)
                raw = src.read(1, window=sub)
                if dtype != "float32":  # integer source, no decimation: copy as-is
                    dst.write(raw, 1, window=Window(0, r0, out_w, nr))
                    continue
                a = raw.astype("float32")
                bad = ~np.isfinite(a)
                if nodata is not None and not math.isnan(nodata):
                    bad |= a == np.float32(nodata)
                if src.dtypes[0].startswith("float"):
                    bad |= a < -1e30  # USGS float nodata is -3.4e38
                a[bad] = np.nan
                if d > 1:
                    a = a.reshape(nr // d, d, w_cols // d, d)
                    with np.errstate(invalid="ignore"):
                        a = np.nanmean(a, axis=(1, 3))  # all-nan blocks -> nan (warning muted)
                dst.write(a.astype(dtype), 1, window=Window(0, r0 // d, out_w, a.shape[0]))
        return {
            "source": url_or_path, "source_crs": src.crs.to_proj4(), "source_window": [
                int(win.col_off), int(win.row_off), int(win.width), int(win.height)],
            "source_res": list(src.res), "saved_res": [src.res[0] * d, src.res[1] * d],
            "saved_shape": [out_h, out_w], "out": str(out_path),
        }


def warp_to_grid(path: Path | str, grid: Grid, resampling: Resampling = Resampling.bilinear,
                 src_nodata=None) -> np.ndarray:
    """Reproject a local raster onto `grid`. Returns float32 with NaN where there is no data."""
    with rasterio.Env(**gdal_env()), rasterio.open(path) as src:
        nod = src.nodata if src_nodata is None else src_nodata
        with WarpedVRT(src, crs=grid.crs, transform=grid.transform, width=grid.width,
                       height=grid.height, resampling=resampling, src_nodata=nod,
                       nodata=np.nan, dtype="float32") as vrt:
            a = vrt.read(1).astype("float32")
    return a


def block_reduce(a: np.ndarray, k: int, how: str = "mean") -> np.ndarray:
    """Aggregate k x k blocks (array dims must be multiples of k). NaN-aware."""
    h, w = a.shape
    if h % k or w % k:
        raise ValueError(f"shape {a.shape} not divisible by {k}")
    b = a.reshape(h // k, k, w // k, k).transpose(0, 2, 1, 3).reshape(h // k, w // k, k * k)
    with np.errstate(invalid="ignore"), _quiet():
        if how == "mean":
            return np.nanmean(b, axis=2)
        if how == "max":
            return np.nanmax(b, axis=2)
        if how.startswith("p"):
            return np.nanpercentile(b, float(how[1:]), axis=2)
        if how == "anynan":
            return np.isnan(b).any(axis=2)
    raise ValueError(how)


class _quiet:
    def __enter__(self):
        import warnings
        self._w = warnings.catch_warnings()
        self._w.__enter__()
        warnings.simplefilter("ignore", RuntimeWarning)

    def __exit__(self, *exc):
        return self._w.__exit__(*exc)
