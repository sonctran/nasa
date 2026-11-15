"""Walking cost model behaves as documented in planner/cost.py and METHODS.md."""
import math

import numpy as np
import pytest

from pipeline.common import load_params
from planner.cost import HumanModel, edge_costs, hazard_index, scalar_weight
from planner.grid import Terrain, build_edges

P = load_params()
HM = HumanModel.from_params(P)


def test_level_walking_matches_nasa_inputs():
    assert HM.speed(0.0) == pytest.approx(P["human_factors"]["level_speed_mps"]["value"])
    assert HM.power_w(0.0) == pytest.approx(P["human_factors"]["level_metabolic_rate_w"]["value"])
    assert HM.mass == pytest.approx(82.0 + 90.7 + 10.0)


def test_uphill_is_slower_and_costlier_downhill_is_not_faster():
    g = np.array([0.0, 0.05, 0.1, 0.2, 0.3])
    v = HM.speed(g)
    e = HM.e_per_m(g)
    assert np.all(np.diff(v) < 0) and np.all(np.diff(e) > 0)
    assert np.allclose(HM.speed(-g), HM.v0)                    # capped at the level pace
    assert np.allclose(HM.e_per_m(-g), HM.p0 / HM.v0)          # no downhill credit (assumption)
    assert HM.time_s(0.2, 10) != HM.time_s(-0.2, 10)           # direction-dependent


def test_uphill_energy_by_hand():
    g = 0.10
    sin_t = g / math.sqrt(1 + g * g)
    hand = 352 / 0.5556 + 182.7 * 3.710 * sin_t / 0.243
    assert HM.e_per_m(g) == pytest.approx(hand, rel=1e-9)


def test_constant_power_pacing_means_energy_is_power_times_time():
    for g in (-0.3, -0.1, 0.0, 0.05, 0.15, 0.3):
        assert HM.energy_j(g, 10.0) == pytest.approx(HM.p0 * HM.time_s(g, 10.0), rel=1e-12)


def test_hazard_index_ramps_from_caution_to_nogo():
    s = np.array([[0, 10, 15, 20, 30.0]])
    t = Terrain(elev=np.zeros_like(s), slope=s, rough=np.zeros_like(s), nodata=np.zeros(s.shape, bool), cell=10.0)
    h = hazard_index(t, 10, 20, 0.05, 0.2)
    assert h.tolist() == [[0.0, 0.0, 0.5, 1.0, 1.0]]


def test_scalar_weight_equals_length_on_flat_safe_ground():
    H = W = 4
    t = Terrain(elev=np.zeros((H, W)), slope=np.zeros((H, W)), rough=np.zeros((H, W)), nodata=np.zeros((H, W), bool), cell=10.0)
    e = build_edges(t, np.ones((H, W), bool), np.zeros((H, W)), max_grade=1.0)
    ec = edge_costs(e, HM)
    w = scalar_weight(ec, 0.5, 0.5, 0.0)
    assert np.allclose(w[e.ok], e.length[e.ok])
    assert np.isinf(w[~e.ok]).all()
    d = scalar_weight(ec, 0, 0, 0, 1.0)
    assert np.allclose(d[e.ok], e.length[e.ok])
    with pytest.raises(ValueError):
        scalar_weight(ec, 0, 0, 1.0)


def test_alternative_model_uses_the_verified_tobler_and_minetti_formulas():
    alt = HumanModel.from_params(P, kind="tobler_minetti")
    # Tobler 1993 p.4: W = 6 exp(-3.5 |S + 0.05|) km/h -> 5.04 km/h on the flat; peak at S = -0.05
    assert 6 * math.exp(-3.5 * 0.05) == pytest.approx(5.036, abs=1e-3)
    assert alt.speed(0.0) == pytest.approx(alt.v0)                              # rescaled to the suited pace
    assert alt.speed(-0.05) > alt.speed(0.0) > alt.speed(0.10)
    assert alt.speed(0.10) / alt.speed(0.0) == pytest.approx(math.exp(-3.5 * 0.15) / math.exp(-3.5 * 0.05))
    # Minetti 2002 Fig. 1: Cw(0) = 2.5 J/kg/m; Cw(0.1) by hand
    cw = lambda i: 280.5 * i**5 - 58.7 * i**4 - 76.8 * i**3 + 51.9 * i**2 + 19.6 * i + 2.5
    hand = 352 / 0.5556 + (3.710 / 9.798) * (cw(0.1) - 2.5) * 182.7
    assert alt.e_per_m(0.1) == pytest.approx(hand, rel=1e-9)
    assert alt.e_per_m(-0.1) < alt.e_per_m(0.0)                                 # downhill credit exists here
