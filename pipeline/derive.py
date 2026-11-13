"""Terrain derivatives on a north-up grid with square cells.

Conventions: array row 0 is the NORTH edge; x = east, y = north; elevations in metres.
NaN = no data. A NaN cell makes every derivative that touches it NaN.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage


def _pad(z: np.ndarray) -> np.ndarray:
    return np.pad(z, 1, mode="edge")


def gradients_horn(z: np.ndarray, cell: float) -> tuple[np.ndarray, np.ndarray]:
    """dz/dx (east) and dz/dy (north) with Horn's (1981) 3x3 weighted differences.

    Neighbourhood (row 0 = north):   a b c
                                     d e f
                                     g h i
    dz/dx = ((c + 2f + i) - (a + 2d + g)) / (8 * cell)
    dz/dy = ((a + 2b + c) - (g + 2h + i)) / (8 * cell)     (north minus south)
    Same method as GDAL `gdaldem slope` (default algorithm).
    Edge cells use replicated edges, so slopes on the outer ring are biased low.
    """
    p = _pad(z.astype("float64"))
    a, b, c = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
    d, f = p[1:-1, :-2], p[1:-1, 2:]
    g, h, i = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8.0 * cell)
    dzdy = ((a + 2 * b + c) - (g + 2 * h + i)) / (8.0 * cell)
    hole = ~np.isfinite(z)  # Horn ignores the centre cell; a no-data centre must stay no-data
    dzdx[hole] = np.nan
    dzdy[hole] = np.nan
    return dzdx, dzdy


def slope_deg(z: np.ndarray, cell: float) -> np.ndarray:
    dzdx, dzdy = gradients_horn(z, cell)
    return np.degrees(np.arctan(np.hypot(dzdx, dzdy))).astype("float32")


def aspect_deg(z: np.ndarray, cell: float) -> np.ndarray:
    """Downslope direction, degrees clockwise from north (0 = faces north). NaN on flats."""
    dzdx, dzdy = gradients_horn(z, cell)
    asp = (np.degrees(np.arctan2(-dzdx, -dzdy)) + 360.0) % 360.0
    asp[(dzdx == 0) & (dzdy == 0)] = np.nan
    return asp.astype("float32")


def hillshade(z: np.ndarray, cell: float, azimuth_deg: float = 315.0, altitude_deg: float = 45.0,
              z_factor: float = 1.0) -> np.ndarray:
    """Lambertian hillshade in [0, 1]. Sun azimuth clockwise from north, altitude above horizon."""
    dzdx, dzdy = gradients_horn(z * z_factor, cell)
    az, alt = np.radians(azimuth_deg), np.radians(altitude_deg)
    sun = np.array([np.sin(az) * np.cos(alt), np.cos(az) * np.cos(alt), np.sin(alt)])  # E, N, Up
    norm = np.sqrt(dzdx ** 2 + dzdy ** 2 + 1.0)
    hs = (-dzdx * sun[0] - dzdy * sun[1] + sun[2]) / norm
    return np.clip(hs, 0.0, 1.0).astype("float32")


def _nan_uniform(z: np.ndarray, size: int) -> np.ndarray:
    """Mean over a size x size window, ignoring NaNs (NaN where the window is all NaN)."""
    valid = np.isfinite(z)
    zf = np.where(valid, z, 0.0).astype("float64")
    s = ndimage.uniform_filter(zf, size=size, mode="nearest")
    n = ndimage.uniform_filter(valid.astype("float64"), size=size, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        out = s / n
    out[n < 1e-9] = np.nan
    return out


def roughness_rms(z: np.ndarray, window_cells: int) -> np.ndarray:
    """Detrended RMS relief (metres) in a square window.

    residual = z - (window mean of z); roughness = sqrt(window mean of residual^2).
    For a perfect plane the window mean equals the centre value, so roughness = 0
    whatever the slope: this measures bumps and steps, not tilt.
    Cells that are NaN stay NaN.
    """
    if window_cells < 3 or window_cells % 2 == 0:
        raise ValueError("window_cells must be odd and >= 3")
    m = _nan_uniform(z, window_cells)
    r2 = (z - m) ** 2
    rough = np.sqrt(np.clip(_nan_uniform(r2, window_cells), 0.0, None))  # clip float round-off
    rough[~np.isfinite(z)] = np.nan
    return rough.astype("float32")


def nogo_mask(slope: np.ndarray, rough: np.ndarray, slope_limit_deg: float,
              rough_limit_m: float) -> np.ndarray:
    """True where a suited walker must not go: too steep, too rough, or no data."""
    nodata = ~np.isfinite(slope) | ~np.isfinite(rough)
    with np.errstate(invalid="ignore"):
        return nodata | (slope > slope_limit_deg) | (rough > rough_limit_m)
