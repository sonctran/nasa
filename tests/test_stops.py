"""OR-Tools stop scheduling finds the true optimum on small instances (checked by brute force)."""
import numpy as np
import pytest

from planner.stops_ortools import Instance, evaluate, solve_bruteforce, solve_ortools


def random_instance(seed: int, n_opt: int = 6) -> Instance:
    rng = np.random.default_rng(seed)
    n = 2 + n_opt                                    # habitat, depot, optional stops
    xy = rng.uniform(0, 3000, (n, 2))
    d = np.hypot(*(xy[:, None, :] - xy[None, :, :]).transpose(2, 0, 1))
    asym = rng.uniform(0.9, 1.3, (n, n))             # uphill != downhill
    travel = d / 0.9 * asym
    np.fill_diagonal(travel, 0)
    o2 = travel * rng.uniform(1.0e-5, 1.6e-5, (n, n))
    dwell = np.r_[0, 1800, rng.uniform(600, 2400, n_opt)]
    return Instance(
        names=["habitat", "depot"] + [f"s{i}" for i in range(n_opt)],
        travel_s=travel.tolist(), o2_kg=o2.tolist(), dwell_s=dwell.tolist(),
        dwell_o2_kg=(dwell * 1.2e-5).tolist(),
        value=[0, 0] + [int(v) for v in rng.choice([4, 6, 10], n_opt)],
        mandatory=[False, True] + [False] * n_opt,
        time_budget_s=float(rng.uniform(9000, 21600)), o2_budget_kg=float(rng.uniform(0.25, 0.6)))


@pytest.mark.parametrize("seed", range(25))
def test_ortools_matches_bruteforce(seed):
    inst = random_instance(seed)
    ref = solve_bruteforce(inst)
    got = solve_ortools(inst)
    if ref is None:
        assert got is None or got.value == 0
        return
    assert got is not None
    assert got.value == ref.value                    # same science points
    assert got.time_s <= ref.time_s + 5.0            # same (shortest) time; OR-Tools rounds to 1 s
    t, o2 = evaluate(inst, got.order)
    assert t <= inst.time_budget_s + len(got.order) and o2 <= inst.o2_budget_kg * 1.001
    assert got.order[0] == 0 and got.order[-1] == 0 and 1 in got.order   # depot visited


def test_mandatory_depot_is_kept_even_with_zero_value():
    inst = random_instance(3)
    inst.time_budget_s = 1e6
    inst.o2_budget_kg = 1e6
    got = solve_ortools(inst)
    assert 1 in got.order and got.dropped == []      # unlimited budget -> everything visited
