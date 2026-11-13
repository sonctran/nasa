"""A* route search on the 16-connected planning grid (Python reference implementation).

The browser Web Worker (Phase 3) runs the same algorithm on the same grid and edge costs.

Heuristic: h(n) = c_min * straight-line horizontal distance from n to the goal, where
c_min = the smallest cost per horizontal metre over ALL allowed edges of the graph.
Every edge costs at least c_min * its horizontal length, and any route is at least as
long as the straight line, so h never over-estimates (admissible). It also obeys the
triangle inequality (consistent), so a node's cost is final the first time it is popped.
Tests check A* cost == Dijkstra cost on random grids and on the real grid.
"""
from __future__ import annotations

import heapq
import math

import numpy as np

from .grid import MOVES, EdgeSet


def min_cost_per_metre(edges: EdgeSet, weight: np.ndarray) -> float:
    with np.errstate(invalid="ignore", divide="ignore"):
        per_m = np.where(edges.ok, weight / edges.length, np.inf)
    return float(per_m.min())


def astar(edges: EdgeSet, weight: np.ndarray, start: int, goal: int, cell: float,
          c_min: float | None = None) -> tuple[float, list[int], int]:
    """Return (cost, path as flat cell indices start..goal, nodes expanded).

    cost = inf and path = [] if the goal cannot be reached.
    """
    K, H, W = edges.ok.shape
    if c_min is None:
        c_min = min_cost_per_metre(edges, weight)
    wk = [memoryview(np.ascontiguousarray(np.where(edges.ok[k], weight[k], math.inf)).reshape(-1)) for k in range(K)]
    moves = [(dr, dc, int(edges.offsets[k])) for k, (dr, dc, _) in enumerate(MOVES)]
    gr, gc = divmod(goal, W)
    hscale = c_min * cell

    def h(i: int) -> float:
        r, c = divmod(i, W)
        return hscale * math.hypot(r - gr, c - gc)

    g = {start: 0.0}
    parent = {start: -1}
    closed = set()
    heap = [(h(start), 0.0, start)]
    expanded = 0
    while heap:
        f, gi, i = heapq.heappop(heap)
        if i in closed:
            continue
        if i == goal:
            path = [i]
            while parent[path[-1]] != -1:
                path.append(parent[path[-1]])
            return gi, path[::-1], expanded
        closed.add(i)
        expanded += 1
        for k in range(K):
            w = wk[k][i]
            if w == math.inf:
                continue
            j = i + moves[k][2]
            if j in closed:
                continue
            ng = gi + w
            if ng < g.get(j, math.inf):
                g[j] = ng
                parent[j] = i
                heapq.heappush(heap, (ng + h(j), ng, j))
    return math.inf, [], expanded


def path_edges(edges: EdgeSet, path: list[int]) -> list[tuple[int, int]]:
    """(from_index, move k) for each step of a path."""
    off_to_k = {int(o): k for k, o in enumerate(edges.offsets)}
    return [(a, off_to_k[b - a]) for a, b in zip(path[:-1], path[1:])]


def dijkstra_tree(csgraph, sources, reverse: bool = False):
    """scipy Dijkstra from each source. reverse=True gives cost from every cell TO the source."""
    from scipy.sparse.csgraph import dijkstra

    g = csgraph.T.tocsr() if reverse else csgraph
    return dijkstra(g, directed=True, indices=sources, return_predecessors=True)


def tree_path(pred_row: np.ndarray, source: int, target: int, reverse: bool = False) -> list[int]:
    """Path from a scipy predecessor row. reverse=True: tree built on the transposed graph,
    so following predecessors from `target` walks forward toward `source`."""
    if target != source and pred_row[target] < 0:
        return []
    p = [target]
    while p[-1] != source:
        p.append(int(pred_row[p[-1]]))
    return p if reverse else p[::-1]
