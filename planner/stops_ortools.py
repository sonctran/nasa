"""Science-stop selection and order: a prize-collecting Orienteering Problem (SPEC 6.5).

Nodes: 0 = habitat (start and end), the sample depot (MUST visit), science stops
(optional, each worth its rubric score). Constraints: total EVA time (walk + work)
<= time budget, and total oxygen use <= oxygen budget.

Solved EXACTLY with Google OR-Tools CP-SAT (an integer-programming solver that proves
optimality), using the circuit constraint: each node either lies on the single tour
or takes a "skip" self-loop. The routing-library heuristic (guided local search) was
tried first and missed the optimum on 2 of 10 random test instances (DECISIONS T31).

Objective (lexicographic): the most science points; among equal-point plans, the
shortest one. One objective does both:  maximise  BIG * points - total_time_s
with BIG > any EVA length in seconds.

A brute-force solver (all subsets x all orders) is included for tests.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

from ortools.sat.python import cp_model

BIG = 1_000_000          # s per science point; > any EVA length in seconds (6 h = 21,600 s)
O2_SCALE = 10_000        # kg -> integer units of 0.1 g


@dataclass
class Instance:
    names: list[str]
    travel_s: list[list[float]]     # [i][j] walking time, s
    o2_kg: list[list[float]]        # [i][j] oxygen used walking i -> j, kg
    dwell_s: list[float]            # work time at node i, s (0 for the habitat)
    dwell_o2_kg: list[float]        # oxygen used while working at node i, kg
    value: list[int]                # science points (0 for habitat / depot)
    mandatory: list[bool]           # node must be visited (the depot)
    time_budget_s: float
    o2_budget_kg: float


@dataclass
class Plan:
    order: list[int]                # node sequence, starts and ends with 0
    value: int
    time_s: float
    o2_kg: float
    dropped: list[int]
    solver: str
    status: str = ""


def evaluate(inst: Instance, order: list[int]) -> tuple[float, float]:
    t = sum(inst.travel_s[a][b] + inst.dwell_s[a] for a, b in zip(order[:-1], order[1:]))
    o2 = sum(inst.o2_kg[a][b] + inst.dwell_o2_kg[a] for a, b in zip(order[:-1], order[1:]))
    return t, o2


def solve_ortools(inst: Instance, time_limit_s: float = 20.0) -> Plan | None:
    """Exact orienteering solve with CP-SAT. Deterministic (1 worker, fixed seed)."""
    n = len(inst.names)
    m = cp_model.CpModel()
    arcs, x, skip = [], {}, {}
    for i in range(n):
        for j in range(n):
            if i == j:
                if i == 0 or inst.mandatory[i]:
                    continue
                skip[i] = m.NewBoolVar(f"skip_{i}")
                arcs.append((i, i, skip[i]))
            else:
                x[i, j] = m.NewBoolVar(f"x_{i}_{j}")
                arcs.append((i, j, x[i, j]))
    m.AddCircuit(arcs)
    t_int = {k: int(round(inst.travel_s[k[0]][k[1]] + inst.dwell_s[k[0]])) for k in x}
    o_int = {k: int(round((inst.o2_kg[k[0]][k[1]] + inst.dwell_o2_kg[k[0]]) * O2_SCALE)) for k in x}
    total_t = sum(t_int[k] * v for k, v in x.items())
    m.Add(total_t <= int(inst.time_budget_s))
    m.Add(sum(o_int[k] * v for k, v in x.items()) <= int(inst.o2_budget_kg * O2_SCALE))
    points = sum(int(inst.value[i]) * (1 - s) for i, s in skip.items())
    m.Maximize(BIG * points - total_t)

    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = 0
    solver.parameters.max_time_in_seconds = time_limit_s
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    nxt = {i: j for (i, j), v in x.items() if solver.Value(v)}
    order, cur = [0], 0
    while True:
        cur = nxt[cur]
        order.append(cur)
        if cur == 0:
            break
    t, o2 = evaluate(inst, order)
    visited = set(order)
    return Plan(order=order, value=sum(inst.value[k] for k in visited), time_s=t, o2_kg=o2,
                dropped=[k for k in range(1, n) if k not in visited], solver="OR-Tools CP-SAT",
                status=solver.StatusName(status))


def solve_bruteforce(inst: Instance) -> Plan | None:
    """Exact: every subset of optional stops, every order. Only for small n (tests)."""
    n = len(inst.names)
    must = [k for k in range(1, n) if inst.mandatory[k]]
    opt = [k for k in range(1, n) if not inst.mandatory[k]]
    best = None
    for r in range(len(opt) + 1):
        for sub in itertools.combinations(opt, r):
            nodes = must + list(sub)
            for perm in itertools.permutations(nodes):
                order = [0, *perm, 0]
                t, o2 = evaluate(inst, order)
                if t > inst.time_budget_s or o2 > inst.o2_budget_kg:
                    continue
                v = sum(inst.value[k] for k in nodes)
                key = (-v, t)
                if best is None or key < best[0]:
                    best = (key, order, v, t, o2)
    if best is None:
        return None
    _, order, v, t, o2 = best
    return Plan(order=order, value=v, time_s=t, o2_kg=o2,
                dropped=[k for k in range(1, n) if k not in set(order)], solver="brute force")
