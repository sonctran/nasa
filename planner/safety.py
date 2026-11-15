"""Safety rules (SPEC 6.6): walkback, SEP shelter reach, consumables, radiation dose, go/no-go.

Walkback field: for EVERY cell, the time, energy and oxygen to walk home to the habitat by
the fastest safe route (one Dijkstra on the reversed graph). The plan is then checked at every
cell of the route:
  walkback rule     O2 left at that point - O2 to walk home >= reserve, and
                    elapsed time + time to walk home <= EVA limit
  SEP shelter rule  time to walk home <= shelter time limit (the habitat is the only shelter)
"""
from __future__ import annotations

import numpy as np

from .astar import dijkstra_tree
from .grid import EdgeSet, to_csgraph


def walkback_field(edges: EdgeSet, time_w: np.ndarray, energy_w: np.ndarray, home: int) -> dict:
    """Fastest-route time (s) and that route's energy (J) from every cell to `home`."""
    cs = to_csgraph(edges, np.where(edges.ok, time_w, 1.0))
    dist, pred = dijkstra_tree(cs, [home], reverse=True)
    dist, nxt = dist[0], pred[0]                 # nxt[i] = next cell on the way home from i
    K, H, W = edges.ok.shape
    off_to_k = {int(o): k for k, o in enumerate(edges.offsets)}
    e_flat = energy_w.reshape(K, -1)
    energy = np.full(dist.size, np.inf)
    energy[home] = 0.0
    order = np.argsort(dist, kind="stable")
    for i in order:
        if i == home or not np.isfinite(dist[i]):
            continue
        j = nxt[i]
        energy[i] = e_flat[off_to_k[int(j - i)], i] + energy[j]
    return {"time_s": dist.reshape(H, W), "energy_j": energy.reshape(H, W)}


def checklist(items: list[tuple[str, bool, str]]) -> dict:
    rows = [{"rule": r, "pass": bool(ok), "detail": d} for r, ok, d in items]
    return {"go": all(r["pass"] for r in rows), "items": rows}
