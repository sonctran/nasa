"""A* must return exactly the Dijkstra optimum (SPEC 6.3)."""
import math

import networkx as nx
import numpy as np
import pytest

from planner.astar import astar, dijkstra_tree, min_cost_per_metre, tree_path
from planner.grid import MOVES, Terrain, build_edges, passable_mask, to_csgraph


def random_world(seed: int, H: int = 14, W: int = 17):
    rng = np.random.default_rng(seed)
    elev = np.cumsum(rng.normal(0, 1.5, (H, W)), axis=1) + rng.normal(0, 1, (H, W))
    slope = rng.uniform(0, 30, (H, W))
    rough = rng.uniform(0, 0.3, (H, W))
    t = Terrain(elev=elev, slope=slope, rough=rough, nodata=rng.random((H, W)) < 0.03, cell=10.0)
    ok = passable_mask(t, 24.0, 0.25)
    hazard = rng.uniform(0, 1, (H, W))
    edges = build_edges(t, ok, hazard, max_grade=math.tan(math.radians(25)))
    # random, direction-dependent positive edge weights (stand-in for any cost model)
    weight = edges.length * (1.0 + rng.uniform(0, 2, edges.ok.shape)) + np.abs(edges.dz) * 3.0
    weight = np.where(edges.ok, weight, np.inf)
    return t, edges, weight


def to_networkx(edges, weight, W):
    G = nx.DiGraph()
    K, H, _ = edges.ok.shape
    for k in range(K):
        for r, c in zip(*np.nonzero(edges.ok[k])):
            i = int(r) * W + int(c)
            G.add_edge(i, i + int(edges.offsets[k]), weight=float(weight[k, r, c]))
    return G


@pytest.mark.parametrize("seed", range(12))
def test_astar_equals_networkx_dijkstra_on_random_grids(seed):
    t, edges, weight = random_world(seed)
    H, W = t.shape
    G = to_networkx(edges, weight, W)
    rng = np.random.default_rng(1000 + seed)
    nodes = sorted(G.nodes)
    checked = 0
    for _ in range(60):
        s, g = (int(v) for v in rng.choice(nodes, 2, replace=False))
        cost, path, _ = astar(edges, weight, s, g, t.cell)
        try:
            ref = nx.dijkstra_path_length(G, s, g)
        except nx.NetworkXNoPath:
            assert math.isinf(cost) and path == []
            continue
        assert cost == pytest.approx(ref, rel=1e-12, abs=1e-9)
        # the returned path is real: consecutive cells joined by allowed edges, and its cost adds up
        assert path[0] == s and path[-1] == g
        assert sum(G[a][b]["weight"] for a, b in zip(path[:-1], path[1:])) == pytest.approx(cost, rel=1e-12)
        checked += 1
    assert checked >= 5


def test_astar_equals_scipy_dijkstra_and_predecessor_paths():
    t, edges, weight = random_world(99, H=30, W=30)
    cs = to_csgraph(edges, weight)
    nodes = np.flatnonzero(edges.ok.any(axis=0).ravel())
    s = int(nodes[0])
    dist, pred = dijkstra_tree(cs, [s])
    for g in nodes[::37]:
        g = int(g)
        cost, path, _ = astar(edges, weight, s, g, t.cell)
        if math.isinf(dist[0, g]):
            assert math.isinf(cost)
            continue
        assert cost == pytest.approx(dist[0, g], rel=1e-12)
        p = tree_path(pred[0], s, g)
        assert p[0] == s and p[-1] == g
    # reverse tree = cost from every cell TO the source
    rdist, rpred = dijkstra_tree(cs, [s], reverse=True)
    g = int(nodes[-1])
    if np.isfinite(rdist[0, g]):
        cost, _, _ = astar(edges, weight, g, s, t.cell)
        assert cost == pytest.approx(rdist[0, g], rel=1e-12)
        p = tree_path(rpred[0], s, g, reverse=True)
        assert p[0] == g and p[-1] == s


def test_heuristic_is_admissible_lower_bound():
    t, edges, weight = random_world(5)
    c_min = min_cost_per_metre(edges, weight)
    per_m = np.where(edges.ok, weight / edges.length, np.inf)
    assert c_min > 0 and (per_m[edges.ok] >= c_min).all()


def test_no_corner_cutting_and_no_crossing_blocked_cells():
    H = W = 5
    t = Terrain(elev=np.zeros((H, W)), slope=np.zeros((H, W)), rough=np.zeros((H, W)),
                nodata=np.zeros((H, W), bool), cell=10.0)
    ok = np.ones((H, W), bool)
    ok[2, 2] = False
    edges = build_edges(t, ok, np.zeros((H, W)), max_grade=1.0)
    for k, (dr, dc, cross) in enumerate(MOVES):
        for r in range(H):
            for c in range(W):
                if not edges.ok[k, r, c]:
                    continue
                touched = [(r, c), (r + dr, c + dc)] + [(r + a, c + b) for a, b in cross]
                assert (2, 2) not in touched
    k_diag = [i for i, m in enumerate(MOVES) if m[:2] == (1, 1)][0]
    assert not edges.ok[k_diag, 1, 1]          # (1,1)->(2,2): blocked end cell
    assert not edges.ok[k_diag, 1, 2]          # (1,2)->(2,3): would clip the corner of (2,2)
    assert edges.ok[k_diag, 0, 0]              # (0,0)->(1,1): clear


def test_steep_edges_are_removed():
    H, W = 3, 3
    elev = np.array([[0, 0, 0], [0, 0, 10.0], [0, 0, 0]])
    t = Terrain(elev=elev, slope=np.zeros((H, W)), rough=np.zeros((H, W)), nodata=np.zeros((H, W), bool), cell=10.0)
    edges = build_edges(t, np.ones((H, W), bool), np.zeros((H, W)), max_grade=math.tan(math.radians(20)))
    k_east = [i for i, m in enumerate(MOVES) if m[:2] == (0, 1)][0]
    assert not edges.ok[k_east, 1, 1]          # 10 m rise over 10 m = 45 deg > 20 deg
    assert edges.ok[k_east, 0, 0]
