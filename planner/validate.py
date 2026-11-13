"""Validation helpers (SPEC 6.8): compare a planned route with Perseverance's real traverse.

A rover is not a human: it has its own slope and rock limits, and its drivers also had
science and engineering goals. So agreement is supporting evidence that the terrain model
"sees" what the drivers avoided, not proof that the human route is right.
"""
from __future__ import annotations

import numpy as np
from shapely.geometry import LineString, MultiLineString, Point


def densify(xy: np.ndarray, step: float) -> np.ndarray:
    """Points every `step` metres along a polyline (so long straight edges are not under-sampled)."""
    line = LineString(xy)
    n = max(2, int(np.ceil(line.length / step)) + 1)
    return np.array([line.interpolate(d).coords[0] for d in np.linspace(0, line.length, n)])


def compare(planned_xy: np.ndarray, rover_lines: list[np.ndarray], buffers=(10, 25, 50), step: float = 5.0) -> dict:
    rover = MultiLineString([LineString(l) for l in rover_lines])
    pts = densify(np.asarray(planned_xy), step)
    d = np.array([rover.distance(Point(p)) for p in pts])
    rpts = np.vstack([densify(np.asarray(l), step) for l in rover_lines])
    plan_line = LineString(planned_xy)
    d_back = np.array([plan_line.distance(Point(p)) for p in rpts])
    straight = float(np.hypot(*(np.asarray(planned_xy[-1]) - np.asarray(planned_xy[0]))))
    return {
        "planned_length_m": float(plan_line.length),
        "rover_length_m": float(rover.length),
        "straight_line_m": straight,
        "length_ratio_planned_over_rover": float(plan_line.length / rover.length),
        "share_of_planned_within_m": {str(b): float((d <= b).mean()) for b in buffers},
        "share_of_rover_within_m": {str(b): float((d_back <= b).mean()) for b in buffers},
        "median_offset_m": float(np.median(d)),
        "p90_offset_m": float(np.percentile(d, 90)),
        "max_offset_m": float(d.max()),
    }


def straight_line_baseline(a, b, rover_lines, buffers=(10, 25, 50), step: float = 5.0) -> dict:
    """Same metrics for the naive straight line: the planner should beat this."""
    return compare(np.array([a, b], float), rover_lines, buffers, step)
