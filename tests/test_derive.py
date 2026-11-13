"""Phase 1 exit test: terrain derivatives on synthetic surfaces with known answers."""
import math

import numpy as np
import pytest

from pipeline.crop import block_reduce
from pipeline.derive import aspect_deg, hillshade, nogo_mask, roughness_rms, slope_deg


def tilted_plane(angle_deg, direction_deg, n=41, cell=2.0):
    """Plane rising at `angle_deg` toward compass `direction_deg` (0 = north, 90 = east)."""
    rows, cols = np.mgrid[0:n, 0:n]
    x = cols * cell                 # east
    y = (n - 1 - rows) * cell       # north (row 0 = north edge)
    d = math.radians(direction_deg)
    along = x * math.sin(d) + y * math.cos(d)
    return along * math.tan(math.radians(angle_deg))


INTERIOR = (slice(1, -1), slice(1, -1))  # edge ring uses replicated edges


@pytest.mark.parametrize("angle", [0.0, 2.0, 10.0, 20.0, 30.0, 45.0, 60.0])
@pytest.mark.parametrize("direction", [0.0, 90.0, 30.0, 225.0])
@pytest.mark.parametrize("cell", [1.0, 2.0, 10.0])
def test_slope_of_tilted_plane_equals_known_angle(angle, direction, cell):
    z = tilted_plane(angle, direction, cell=cell)
    s = slope_deg(z, cell)
    assert np.allclose(s[INTERIOR], angle, atol=1e-6)


@pytest.mark.parametrize("direction", [0.0, 90.0, 180.0, 270.0, 30.0])
def test_aspect_points_downhill(direction):
    z = tilted_plane(15.0, direction)          # rises toward `direction`
    downhill = (direction + 180.0) % 360.0
    a = aspect_deg(z, 2.0)[INTERIOR]
    diff = (a - downhill + 180.0) % 360.0 - 180.0
    assert np.allclose(diff, 0.0, atol=1e-6)


def test_roughness_is_zero_on_any_plane_and_positive_on_bumps():
    z = tilted_plane(25.0, 60.0, n=61, cell=1.0)
    r = roughness_rms(z, 5)
    assert np.nanmax(r[6:-6, 6:-6]) < 1e-6     # slope alone is not roughness (1 micrometre = float round-off)
    h = 0.4
    bumps = z + h * np.where((np.indices(z.shape).sum(axis=0) % 2) == 0, 1.0, -1.0)
    rb = roughness_rms(bumps, 5)[6:-6, 6:-6]
    assert np.allclose(rb, h, rtol=0.06)        # +-h checkerboard -> RMS relief ~ h


def test_hillshade_flat_and_facing():
    flat = np.zeros((21, 21))
    assert np.allclose(hillshade(flat, 2.0, 315, 45), math.sin(math.radians(45)))
    toward_sun = tilted_plane(20.0, 135.0)      # rises to the SE -> faces NW (toward a 315 sun)
    away = tilted_plane(20.0, 315.0)            # faces SE
    assert hillshade(toward_sun, 2.0)[INTERIOR].mean() > hillshade(away, 2.0)[INTERIOR].mean()
    # analytic: normal tilted 20 deg toward the sun at altitude 45 -> cos(45 - 20)
    assert np.allclose(hillshade(toward_sun, 2.0)[INTERIOR], math.cos(math.radians(25)), atol=1e-6)


def test_nogo_mask_thresholds_and_nodata():
    slope = np.array([[5.0, 25.0], [5.0, np.nan]])
    rough = np.array([[0.1, 0.1], [0.9, 0.1]])
    m = nogo_mask(slope, rough, slope_limit_deg=20.0, rough_limit_m=0.5)
    assert m.tolist() == [[False, True], [True, True]]


def test_nan_propagates_to_neighbours():
    z = tilted_plane(10.0, 0.0, n=11)
    z[5, 5] = np.nan
    s = slope_deg(z, 2.0)
    assert np.isnan(s[4:7, 4:7]).all() and np.isfinite(s[0, 0])


def test_block_reduce():
    a = np.arange(16, dtype=float).reshape(4, 4)
    assert block_reduce(a, 2, "mean").tolist() == [[2.5, 4.5], [10.5, 12.5]]
    assert block_reduce(a, 2, "max").tolist() == [[5.0, 7.0], [13.0, 15.0]]
    a[0, 0] = np.nan
    assert block_reduce(a, 2, "anynan").tolist() == [[True, False], [False, False]]
