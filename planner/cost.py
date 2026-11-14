"""Traverse cost model: walking time, metabolic energy and hazard for every grid edge (SPEC 6.1-6.2).

Every number comes from config/params.yaml, where each value carries its source or is
labelled "assumption". Tobler (1993) and Minetti et al. (2002) were read from PDFs the owner
supplied (DECISIONS T39): Minetti's measured uphill efficiency is used in the plan of record,
and Tobler + Minetti together form the alternative check model below.

Notation: g = grade of an edge (rise / run), theta = atan(g), L_h = horizontal length,
L_s = L_h * sqrt(1 + g^2) = length along the ground, M = body + suit + kit mass,
g_M = Mars gravity, P0 = level-walking metabolic rate, v0 = level walking speed.

Energy per metre along the ground
    level / downhill:  e(g) = P0 / v0                          (no downhill credit: assumption)
    uphill:            e(g) = P0 / v0 + M * g_M * sin(theta) / eta
    The uphill term is the work of lifting body + suit in Mars gravity, divided by the
    muscle efficiency eta (0.243, Minetti et al. 2002; applied to all uphill grades: assumption).
    Edge energy E = e(g) * L_s.
Speed (constant-power pacing, assumption)
    v(g) = min(v0, P0 / e(g))   ->  v0 on level ground and downhill, slower uphill.
    Walking power therefore never goes above P0. Edge time T = L_s / v(g).
Alternative check model ("tobler_minetti", not the plan of record)
    speed  = v0 * Tobler(g) / Tobler(0)        (Tobler 1993 shape, rescaled to 2 km/h)
    energy = P0/v0 + (Mars/Earth gravity) * (Cw(g) - Cw(0)) * M   per metre (Minetti 2002 Cw)
Hazard
    index h in [0, 1] per cell: 0 below the caution slope/roughness, rising linearly to 1
    at the no-go limit (slope from NASA's 20 deg, roughness 0.2 m). Edge hazard = T * mean h.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .grid import EdgeSet, Terrain


def pv(params: dict, dotted: str):
    node = params
    for key in dotted.split("."):
        node = node[key]
    return node["value"]


@dataclass(frozen=True)
class HumanModel:
    v0: float            # m/s, level speed
    p0: float            # W, level-walking metabolic rate
    mass: float          # kg, body + suit + kit
    gravity: float       # m/s^2
    eta: float           # uphill muscle efficiency
    down_credit: float   # fraction of released potential energy recovered downhill (0 = none)
    kind: str = "nasa"   # "nasa" (plan of record) or "tobler_minetti" (alternative check)
    tobler: tuple = (6.0, 3.5, 0.05)
    minetti: tuple = (280.5, -58.7, -76.8, 51.9, 19.6, 2.5)
    g_ratio: float = 3.710 / 9.798

    @classmethod
    def from_params(cls, p: dict, gravity_key: str = "human_factors.mars_gravity_mps2", kind: str = "nasa") -> "HumanModel":
        mass = sum(pv(p, f"human_factors.{k}") for k in ("crew_body_mass_kg", "suit_mass_kg", "carried_kit_kg"))
        return cls(v0=pv(p, "human_factors.level_speed_mps"), p0=pv(p, "human_factors.level_metabolic_rate_w"),
                   mass=mass, gravity=pv(p, gravity_key), eta=pv(p, "human_factors.uphill_muscle_efficiency"),
                   down_credit=pv(p, "human_factors.downhill_energy_credit"), kind=kind,
                   tobler=tuple(pv(p, "human_factors.tobler_hiking_function")),
                   minetti=tuple(pv(p, "human_factors.minetti_walk_coeffs")),
                   g_ratio=pv(p, gravity_key) / pv(p, "human_factors.earth_gravity_mps2"))

    # --- per-grade functions (numpy-friendly) ------------------------------------------
    def e_per_m(self, g):
        """Metabolic energy per metre along the ground, J/m."""
        g = np.asarray(g, float)
        if self.kind == "tobler_minetti":
            gi = np.clip(g, -0.45, 0.45)                  # Minetti's tested range
            extra = np.polyval(self.minetti, gi) - np.polyval(self.minetti, 0.0)
            return self.p0 / self.v0 + self.g_ratio * extra * self.mass
        sin_t = g / np.sqrt(1.0 + g * g)
        lift = self.mass * self.gravity * sin_t
        return self.p0 / self.v0 + np.where(sin_t > 0, lift / self.eta, self.down_credit * lift)

    def speed(self, g):
        """Walking speed along the ground, m/s."""
        if self.kind == "tobler_minetti":
            a, b, c = self.tobler
            g = np.asarray(g, float)
            return self.v0 * np.exp(-b * np.abs(g + c)) / np.exp(-b * abs(c))
        return np.minimum(self.v0, self.p0 / self.e_per_m(g))

    def ground_length(self, g, horizontal_m):
        g = np.asarray(g, float)
        return horizontal_m * np.sqrt(1.0 + g * g)

    def energy_j(self, g, horizontal_m):
        return self.e_per_m(g) * self.ground_length(g, horizontal_m)

    def time_s(self, g, horizontal_m):
        return self.ground_length(g, horizontal_m) / self.speed(g)

    def power_w(self, g):
        return self.e_per_m(g) * self.speed(g)


def hazard_index(t: Terrain, slope_caution: float, slope_nogo: float, rough_caution: float, rough_nogo: float) -> np.ndarray:
    hs = np.clip((t.slope - slope_caution) / (slope_nogo - slope_caution), 0.0, 1.0)
    hr = np.clip((t.rough - rough_caution) / (rough_nogo - rough_caution), 0.0, 1.0)
    return np.maximum(hs, hr)


@dataclass
class EdgeCosts:
    time_s: np.ndarray       # (16, rows, cols), inf where no edge
    energy_j: np.ndarray
    hazard_s: np.ndarray     # hazard-weighted seconds
    caution_s: np.ndarray    # seconds on edges whose mean hazard > 0 ("hazard-exposure time")
    length_m: np.ndarray     # length along the ground
    grade: np.ndarray
    t_ref: float             # s per metre, level ground (normaliser)
    e_ref: float             # J per metre, level ground (normaliser)


def edge_costs(edges: EdgeSet, hm: HumanModel) -> EdgeCosts:
    ok = edges.ok
    with np.errstate(invalid="ignore", divide="ignore"):
        g = np.where(ok, edges.dz / edges.length, 0.0)
    t = np.where(ok, hm.time_s(g, edges.length), np.inf)
    e = np.where(ok, hm.energy_j(g, edges.length), np.inf)
    if (e[ok] <= 0).any():
        raise ValueError("model gives non-positive walking energy on some edge: check parameters")
    with np.errstate(invalid="ignore"):
        hz = np.where(ok, t * edges.hz_mean, np.inf)
    caution = np.where(ok, np.where(edges.hz_mean > 0, t, 0.0), np.inf)
    ls = np.where(ok, hm.ground_length(g, edges.length), np.inf)
    return EdgeCosts(time_s=t, energy_j=e, hazard_s=hz, caution_s=caution, length_m=ls, grade=g,
                     t_ref=float(1.0 / hm.v0), e_ref=float(hm.p0 / hm.v0))


def scalar_weight(ec: EdgeCosts, w_time: float, w_energy: float, w_hazard: float, w_dist: float = 0.0) -> np.ndarray:
    """One number per edge, in 'equivalent level metres':
        w_t * time / t_ref + w_E * energy / e_ref + w_H * hazard_time / t_ref + w_D * horizontal length
    On flat safe ground with w_t + w_E = 1 an edge costs exactly its length. w_D alone gives the
    plain shortest-distance route (the naive baseline). Edges that do not exist get inf."""
    if w_time + w_energy + w_dist <= 0:
        raise ValueError("time + energy (or distance) weight must be > 0, otherwise safe edges cost 0")
    ok = np.isfinite(ec.time_s)
    with np.errstate(invalid="ignore"):
        w = w_time * ec.time_s / ec.t_ref + w_energy * ec.energy_j / ec.e_ref + w_hazard * ec.hazard_s / ec.t_ref
        if w_dist:
            w = w + w_dist * ec.length_m / np.sqrt(1.0 + ec.grade ** 2)
    return np.where(ok, w, np.inf)
