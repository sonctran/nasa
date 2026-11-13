"""Shared paths, grid definition and coordinate helpers for the data pipeline.

The study area (AOI) lives on a *local metric grid*:
  * Projection: equirectangular on the Mars 2000 sphere (R = 3,396,190 m), with the
    standard parallel and central meridian set to the AOI anchor point. Near the
    anchor this has true scale in both directions (error < 0.03 % over 4 km), so
    1 grid metre = 1 ground metre. The source DTM uses standard parallel 0 deg,
    where 1 projected metre east-west is only cos(18.45 deg) = 0.949 ground metres
    at Jezero; slopes computed on that grid would be wrong, so we reproject.
  * Local coordinates: x east, y north, in metres, origin (0, 0) at the AOI's
    south-west corner. This is what the web app uses (Leaflet L.CRS.Simple).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import yaml
from rasterio.crs import CRS
from rasterio.transform import Affine, from_origin

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
PREVIEWS = PROCESSED / "previews"
SITE = ROOT / "site"
SITE_LAYERS = SITE / "assets" / "layers"
SITE_DATA = SITE / "assets" / "data"
CONFIG = ROOT / "config" / "params.yaml"

MARS_RADIUS_M = 3_396_190.0  # Mars 2000 sphere (IAU), as used by every USGS product here


def load_params(path: Path = CONFIG) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def pv(params: dict, dotted: str):
    """Return params[...]['value'] for a dotted key such as 'grid.analysis_cell_m'."""
    node = params
    for key in dotted.split("."):
        node = node[key]
    return node["value"]


@dataclass(frozen=True)
class Grid:
    """A north-up raster grid in the local AOI CRS."""

    anchor_lon: float
    anchor_lat: float
    # AOI extent in projected metres, relative to the anchor (anchor = projected 0,0)
    west: float
    south: float
    east: float
    north: float
    cell: float

    @property
    def crs(self) -> CRS:
        return local_crs(self.anchor_lon, self.anchor_lat)

    @property
    def width(self) -> int:
        return int(round((self.east - self.west) / self.cell))

    @property
    def height(self) -> int:
        return int(round((self.north - self.south) / self.cell))

    @property
    def shape(self) -> tuple[int, int]:
        return self.height, self.width

    @property
    def transform(self) -> Affine:
        return from_origin(self.west, self.north, self.cell, self.cell)

    @property
    def size_m(self) -> tuple[float, float]:
        return self.east - self.west, self.north - self.south

    def with_cell(self, cell: float) -> "Grid":
        return Grid(self.anchor_lon, self.anchor_lat, self.west, self.south, self.east, self.north, cell)

    # --- coordinate conversions -------------------------------------------------
    def lonlat_to_proj(self, lon, lat):
        """Lon/lat (deg, planetocentric, east-positive) -> projected metres (anchor = 0,0)."""
        k = math.pi / 180.0 * MARS_RADIUS_M
        x = (lon - self.anchor_lon) * k * math.cos(math.radians(self.anchor_lat))
        y = (lat - self.anchor_lat) * k
        return x, y

    def proj_to_local(self, x, y):
        """Projected metres -> local metres (origin at the AOI south-west corner)."""
        return x - self.west, y - self.south

    def lonlat_to_local(self, lon, lat):
        return self.proj_to_local(*self.lonlat_to_proj(lon, lat))

    def local_to_lonlat(self, lx, ly):
        k = math.pi / 180.0 * MARS_RADIUS_M
        x, y = lx + self.west, ly + self.south
        lon = self.anchor_lon + x / (k * math.cos(math.radians(self.anchor_lat)))
        lat = self.anchor_lat + y / k
        return lon, lat

    def local_to_rowcol(self, lx, ly):
        """Local metres -> (row, col) of the cell containing that point (row 0 = north edge)."""
        col = int(math.floor(lx / self.cell))
        row = int(math.floor((self.height * self.cell - ly) / self.cell))
        return row, col

    def corners_lonlat(self) -> dict:
        w, s = self.local_to_lonlat(0.0, 0.0)
        e, n = self.local_to_lonlat(*self.size_m)
        return {"west_lon": w, "south_lat": s, "east_lon": e, "north_lat": n}


def local_crs(anchor_lon: float, anchor_lat: float) -> CRS:
    return CRS.from_proj4(
        f"+proj=eqc +lat_ts={anchor_lat:.8f} +lat_0={anchor_lat:.8f} +lon_0={anchor_lon:.8f} "
        f"+x_0=0 +y_0=0 +R={MARS_RADIUS_M:.0f} +units=m +no_defs"
    )


def grid_from_params(params: dict, cell_key: str = "grid.analysis_cell_m", anchor=None) -> Grid:
    """Build the AOI grid. `anchor` = (lon, lat); default = the value stored in params."""
    if anchor is None:
        anchor = (pv(params, "aoi.anchor_lon"), pv(params, "aoi.anchor_lat"))
    return Grid(
        anchor_lon=float(anchor[0]),
        anchor_lat=float(anchor[1]),
        west=float(pv(params, "aoi.west_m")),
        south=float(pv(params, "aoi.south_m")),
        east=float(pv(params, "aoi.east_m")),
        north=float(pv(params, "aoi.north_m")),
        cell=float(pv(params, cell_key)),
    )


def great_circle_m(lon1, lat1, lon2, lat2) -> float:
    """Haversine distance on the Mars 2000 sphere, metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * MARS_RADIUS_M * math.asin(math.sqrt(a))


def gdal_env() -> dict:
    """GDAL settings for fast windowed HTTP reads (used with rasterio.Env)."""
    return {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "GDAL_HTTP_MULTIRANGE": "YES",
        "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
        "CPL_VSIL_CURL_CHUNK_SIZE": str(4 * 1024 * 1024),
        "CPL_VSIL_CURL_CACHE_SIZE": str(256 * 1024 * 1024),
        "GDAL_HTTP_MAX_RETRY": "4",
        "GDAL_HTTP_RETRY_DELAY": "2",
        "VSI_CACHE": "TRUE",
    }
