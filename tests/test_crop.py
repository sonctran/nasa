"""Phase 1 exit test: the AOI crop lands exactly where it should on the local grid."""
import math

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin

from pipeline.common import MARS_RADIUS_M, Grid, grid_from_params, great_circle_m, load_params
from pipeline.crop import aoi_bounds_in, save_native_crop, warp_to_grid

# Same CRS as the USGS Mars 2020 TRN DTM: equirectangular, standard parallel 0, sphere.
USGS_EQC = CRS.from_proj4(f"+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +R={MARS_RADIUS_M:.0f} +units=m +no_defs")
K = math.pi / 180.0 * MARS_RADIUS_M  # metres per degree on the sphere


def small_grid(cell=10.0):
    return Grid(anchor_lon=77.408207, anchor_lat=18.452829,
                west=-500.0, south=-300.0, east=500.0, north=700.0, cell=cell)


def synthetic_source(path, value_fn, res=5.0):
    """A USGS-like eqc raster around the anchor whose value is a known function of (lon, lat)."""
    lon0, lat0 = 77.408207, 18.452829
    x0, y0 = (lon0 - 0.05) * K, (lat0 + 0.05) * K
    n = int(0.1 * K / res)
    rows, cols = np.mgrid[0:n, 0:n]
    lon = (x0 + (cols + 0.5) * res) / K
    lat = (y0 - (rows + 0.5) * res) / K
    data = value_fn(lon, lat).astype("float32")
    with rasterio.open(path, "w", driver="GTiff", width=n, height=n, count=1, dtype="float32",
                       crs=USGS_EQC, transform=from_origin(x0, y0, res, res), nodata=-3.4028226550889045e38) as d:
        d.write(data, 1)
    return path


def lin(lon, lat):
    return 1000.0 * (lat - 18.0) + 300.0 * (lon - 77.0)


def test_project_aoi_grid_matches_params():
    params = load_params()
    g = grid_from_params(params)
    assert (g.width, g.height) == (2000, 2000)            # 4 km / 2 m
    assert g.size_m == (4000.0, 4000.0)
    # the depot anchor sits at local (2000, 1700)
    lx, ly = g.lonlat_to_local(g.anchor_lon, g.anchor_lat)
    assert (lx, ly) == (2000.0, 1700.0)


def test_grid_bounds_and_transform():
    g = small_grid()
    assert g.shape == (100, 100)
    t = g.transform
    assert (t.c, t.f, t.a, t.e) == (-500.0, 700.0, 10.0, -10.0)
    # round trip local <-> lon/lat
    lon, lat = g.local_to_lonlat(123.0, 456.0)
    assert np.allclose(g.lonlat_to_local(lon, lat), (123.0, 456.0), atol=1e-6)


def test_local_grid_has_true_ground_scale():
    """1 local metre = 1 ground metre (unlike the source grid, where E-W is 0.949 m at 18.45 N)."""
    g = small_grid()
    lon_a, lat_a = g.local_to_lonlat(0.0, 0.0)
    lon_b, lat_b = g.local_to_lonlat(1000.0, 1000.0)
    gc = great_circle_m(lon_a, lat_a, lon_b, lat_b)
    assert abs(gc - math.hypot(1000.0, 1000.0)) / gc < 3e-4


def test_warp_puts_values_at_the_right_place(tmp_path):
    src = synthetic_source(tmp_path / "src.tif", lin)
    g = small_grid()
    a = warp_to_grid(src, g)
    assert a.shape == g.shape and np.isfinite(a).all()
    # every cell centre: value must equal the function at that centre's lon/lat
    rows, cols = np.mgrid[0:g.height, 0:g.width]
    lx, ly = (cols + 0.5) * g.cell, (g.height - rows - 0.5) * g.cell
    lon, lat = g.local_to_lonlat(lx, ly)
    expect = lin(lon, lat)
    assert np.max(np.abs(a - expect)) < 0.05             # metres; bilinear on a linear field


def test_native_crop_window_covers_aoi_with_margin(tmp_path):
    src = synthetic_source(tmp_path / "src.tif", lin)
    g = small_grid()
    out = tmp_path / "crop.tif"
    save_native_crop(str(src), g, out, margin_m=50.0)
    need = aoi_bounds_in(USGS_EQC, g, 50.0)
    with rasterio.open(out) as c:
        b = c.bounds
        assert b.left <= need[0] and b.bottom <= need[1] and b.right >= need[2] and b.top >= need[3]
        # not wildly bigger than asked (one source pixel of slack per side)
        assert b.left > need[0] - 5.0 and b.right < need[2] + 5.0
        assert b.bottom > need[1] - 5.0 and b.top < need[3] + 5.0


def test_native_crop_decimation_averages_blocks(tmp_path):
    src = synthetic_source(tmp_path / "src.tif", lin, res=1.0)
    g = small_grid()
    out = tmp_path / "crop4.tif"
    save_native_crop(str(src), g, out, margin_m=10.0, decimate=4)
    with rasterio.open(src) as s, rasterio.open(out) as c:
        assert c.res == (4.0, 4.0)
        # block mean of a linear field = value at the block centre
        cx, cy = c.xy(10, 10)
        lon, lat = cx / K, cy / K
        assert abs(c.read(1)[10, 10] - lin(lon, lat)) < 1e-3
