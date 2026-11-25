"""Geofence-aware routing over the zone visibility graph.

Used by the reference/offline planner and by tests as an *independent oracle*
for "does a legal route exist" (the validator itself never routes; it only checks).
"""
from __future__ import annotations

import heapq
import math

from .geometry import Point, point_in_rect, segment_hits_rect
from .world import World


def _inflate(r, m):
    return (r[0] - m, r[1] - m, r[2] + m, r[3] + m)


def edge_clear(w: World, a: Point, b: Point) -> bool:
    return not any(segment_hits_rect(a, b, k.rect, w.path_margin) for k in w.keepouts.values())


def route(w: World, start: Point, target_zone: str) -> list[str] | None:
    """Shortest list of zone names to NavigateTo (ending at target_zone) with every leg
    keep-out-free, or None if unreachable. Zones inside keep-outs are excluded."""
    nodes = {
        n: z.access
        for n, z in w.zones.items()
        if z.navigable and not any(point_in_rect(z.access, _inflate(k.rect, w.path_margin)) for k in w.keepouts.values())
    }
    if target_zone not in nodes:
        return None
    dist = {n: math.inf for n in nodes}
    prev: dict[str, str | None] = {}
    pq: list[tuple[float, str]] = []
    for n, p in nodes.items():
        if edge_clear(w, start, p):
            dist[n] = math.dist(start, p)
            prev[n] = None
            heapq.heappush(pq, (dist[n], n))
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]:
            continue
        if u == target_zone:
            path = [u]
            while prev[path[-1]] is not None:
                path.append(prev[path[-1]])
            return path[::-1]
        for v, pv in nodes.items():
            if v == u or not edge_clear(w, nodes[u], pv):
                continue
            nd = d + math.dist(nodes[u], pv)
            if nd < dist[v]:
                dist[v], prev[v] = nd, u
                heapq.heappush(pq, (nd, v))
    return None
