"""Planning grid: the SAME 10 m terrain grid the browser uses, and its move graph.

The terrain arrays are decoded from site/assets/data/cost_grid.bin, so the Python
reference planner and the browser Web Worker (Phase 3) start from identical numbers.

Conventions (same as the pipeline): row 0 = NORTH edge, x east, y north, metres,
origin at the AOI south-west corner. Cell (r, c) has its centre at
x = (c + 0.5) * cell, y = (rows - r - 0.5) * cell.

Moves: 16-connected (4 straight, 4 diagonal, 8 "knight" moves). More directions
than 8 means routes are less zig-zag (smaller "metrication" error), at little cost.
An edge is allowed only if both end cells AND every cell the straight segment
crosses are passable, so a route can never cut a corner of a no-go cell.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "site" / "assets" / "data"

# (dr, dc, cells crossed between the two ends) - rows grow southward.
MOVES: list[tuple[int, int, tuple[tuple[int, int], ...]]] = []
for _dr, _dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
    MOVES.append((_dr, _dc, ()))
for _dr, _dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
    MOVES.append((_dr, _dc, ((_dr, 0), (0, _dc))))            # no corner cutting
for _dr, _dc in [(-1, -2), (-1, 2), (1, -2), (1, 2)]:
    s = 1 if _dc > 0 else -1
    MOVES.append((_dr, _dc, ((0, s), (_dr, s))))               # segment crosses these two cells
for _dr, _dc in [(-2, -1), (-2, 1), (2, -1), (2, 1)]:
    s = 1 if _dr > 0 else -1
    MOVES.append((_dr, _dc, ((s, 0), (s, _dc))))


@dataclass
class Terrain:
    elev: np.ndarray      # m, float64 (rows, cols)
    slope: np.ndarray     # deg, P90 of the 2 m cells inside each 10 m cell
    rough: np.ndarray     # m RMS, P90 likewise
    nodata: np.ndarray    # bool
    cell: float           # m

    @property
    def shape(self) -> tuple[int, int]:
        return self.elev.shape

    @property
    def n(self) -> int:
        return self.elev.size

    # --- coordinates ------------------------------------------------------------
    def rc_to_xy(self, r, c):
        rows = self.shape[0]
        return (np.asarray(c) + 0.5) * self.cell, (rows - np.asarray(r) - 0.5) * self.cell

    def xy_to_rc(self, x: float, y: float) -> tuple[int, int]:
        rows, cols = self.shape
        r = int(math.floor((rows * self.cell - y) / self.cell))
        c = int(math.floor(x / self.cell))
        return min(max(r, 0), rows - 1), min(max(c, 0), cols - 1)

    def idx(self, r: int, c: int) -> int:
        return r * self.shape[1] + c

    def rc(self, i: int) -> tuple[int, int]:
        return divmod(int(i), self.shape[1])

    def xy_of_idx(self, i: int) -> tuple[float, float]:
        r, c = self.rc(i)
        x, y = self.rc_to_xy(r, c)
        return float(x), float(y)


def load_terrain(data_dir: Path = SITE_DATA) -> Terrain:
    meta = json.loads((data_dir / "cost_grid.json").read_text(encoding="utf-8"))
    blob = (data_dir / "cost_grid.bin").read_bytes()
    shape = (meta["rows"], meta["cols"])
    arrs = {}
    for a in meta["arrays"]:
        v = np.frombuffer(blob, dtype=np.dtype(a["dtype"]).newbyteorder("<"), count=a["count"], offset=a["offset"])
        arrs[a["name"]] = v.reshape(shape).astype("float64") * a["scale"]
    return Terrain(elev=arrs["elev_m"], slope=arrs["slope_deg"], rough=arrs["rough_m"],
                   nodata=arrs["nodata"].astype(bool), cell=float(meta["cell_m"]))


def passable_mask(t: Terrain, slope_limit_deg: float, rough_limit_m: float, keepout: np.ndarray | None = None) -> np.ndarray:
    ok = ~t.nodata & (t.slope <= slope_limit_deg) & (t.rough <= rough_limit_m)
    if keepout is not None:
        ok &= ~keepout
    return ok


def _shift(a: np.ndarray, dr: int, dc: int, fill) -> np.ndarray:
    """out[r, c] = a[r + dr, c + dc] (fill where that is outside the grid)."""
    out = np.full_like(a, fill)
    H, W = a.shape
    r0, r1 = max(0, -dr), min(H, H - dr)
    c0, c1 = max(0, -dc), min(W, W - dc)
    out[r0:r1, c0:c1] = a[r0 + dr:r1 + dr, c0 + dc:c1 + dc]
    return out


@dataclass
class EdgeSet:
    """Directed edges for every move k: arrays of shape (16, rows, cols), from cell (r, c)."""
    ok: np.ndarray        # bool: edge exists
    length: np.ndarray    # horizontal length, m
    dz: np.ndarray        # elevation change end - start, m
    hz_mean: np.ndarray   # mean hazard index of the two end cells (0-1)
    offsets: np.ndarray   # flat-index offset per move (int64, 16)


def build_edges(t: Terrain, passable: np.ndarray, hazard: np.ndarray, max_grade: float) -> EdgeSet:
    """All allowed directed edges. `max_grade` = tan(slope limit): steeper edges are not allowed
    either, so the energy/speed formulas are never used outside the range they were fitted on."""
    H, W = t.shape
    K = len(MOVES)
    ok = np.zeros((K, H, W), bool)
    length = np.zeros((K, H, W))
    dz = np.zeros((K, H, W))
    hz = np.zeros((K, H, W))
    offsets = np.zeros(K, "int64")
    for k, (dr, dc, cross) in enumerate(MOVES):
        e_ok = passable & _shift(passable, dr, dc, False)
        for cr, cc in cross:
            e_ok &= _shift(passable, cr, cc, False)
        d = t.cell * math.hypot(dr, dc)
        z = _shift(t.elev, dr, dc, np.nan) - t.elev
        with np.errstate(invalid="ignore"):
            e_ok &= np.isfinite(z) & (np.abs(z) / d <= max_grade)
        ok[k] = e_ok
        length[k] = d
        dz[k] = np.where(e_ok, z, 0.0)
        hz[k] = 0.5 * (hazard + _shift(hazard, dr, dc, 0.0))
        offsets[k] = dr * W + dc
    return EdgeSet(ok=ok, length=length, dz=dz, hz_mean=hz, offsets=offsets)


def to_csgraph(edges: EdgeSet, weight: np.ndarray):
    """scipy sparse matrix (N x N) of the given per-edge weight (shape like edges.ok)."""
    from scipy.sparse import csr_matrix

    K, H, W = edges.ok.shape
    N = H * W
    src_all, dst_all, w_all = [], [], []
    base = np.arange(N, dtype="int64").reshape(H, W)
    for k in range(K):
        m = edges.ok[k]
        src = base[m]
        src_all.append(src)
        dst_all.append(src + edges.offsets[k])
        w_all.append(weight[k][m])
    src = np.concatenate(src_all)
    dst = np.concatenate(dst_all)
    w = np.concatenate(w_all)
    if (w <= 0).any():
        raise ValueError("edge weights must be > 0 (scipy drops explicit zeros)")
    return csr_matrix((w, (src, dst)), shape=(N, N))
