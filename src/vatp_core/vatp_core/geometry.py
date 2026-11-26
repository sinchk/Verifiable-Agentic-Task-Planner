"""Tiny 2-D geometry helpers (no external deps) for geofence checks."""
from __future__ import annotations

Point = tuple[float, float]
Rect = tuple[float, float, float, float]  # xmin, ymin, xmax, ymax


def point_in_rect(p: Point, r: Rect) -> bool:
    return r[0] <= p[0] <= r[2] and r[1] <= p[1] <= r[3]


def rect_center(r: Rect) -> Point:
    return ((r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0)


def rects_overlap(a: Rect, b: Rect) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _orient(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_seg(a: Point, b: Point, c: Point) -> bool:
    return min(a[0], b[0]) <= c[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= c[1] <= max(a[1], b[1])


def segments_intersect(p1: Point, p2: Point, q1: Point, q2: Point) -> bool:
    o1, o2 = _orient(p1, p2, q1), _orient(p1, p2, q2)
    o3, o4 = _orient(q1, q2, p1), _orient(q1, q2, p2)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0) and 0 not in (o1, o2, o3, o4):
        return True
    return (
        (o1 == 0 and _on_seg(p1, p2, q1))
        or (o2 == 0 and _on_seg(p1, p2, q2))
        or (o3 == 0 and _on_seg(q1, q2, p1))
        or (o4 == 0 and _on_seg(q1, q2, p2))
    )


def segment_hits_rect(a: Point, b: Point, r: Rect, margin: float = 0.0) -> bool:
    """True if segment a-b touches the (margin-inflated) rectangle."""
    r = (r[0] - margin, r[1] - margin, r[2] + margin, r[3] + margin)
    if point_in_rect(a, r) or point_in_rect(b, r):
        return True
    corners = [(r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])]
    return any(
        segments_intersect(a, b, corners[i], corners[(i + 1) % 4]) for i in range(4)
    )


# ------------------------------------------------------------------ footprint clearance (runtime geofence monitor)
Poly = list[Point]


def rect_corners(r: Rect) -> Poly:
    return [(r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])]


def oriented_box(x: float, y: float, yaw: float, front: float, rear: float, half_wid: float) -> Poly:
    """Corners of a box at pose (x, y, yaw): `front` metres ahead of the origin, `rear` behind it, `half_wid` to each side."""
    import math
    c, s = math.cos(yaw), math.sin(yaw)
    return [(x + c * dx - s * dy, y + s * dx + c * dy)
            for dx, dy in ((front, half_wid), (-rear, half_wid), (-rear, -half_wid), (front, -half_wid))]


def oriented_rect(x: float, y: float, yaw: float, half_len: float, half_wid: float) -> Poly:
    """Symmetric special case of oriented_box: centred at (x, y), half_len along the heading, half_wid across it."""
    return oriented_box(x, y, yaw, half_len, half_len, half_wid)


def _point_in_poly(p: Point, poly: Poly) -> bool:
    inside, n = False, len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]:
            inside = not inside
    return inside


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    import math
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def polygon_distance(p: Poly, q: Poly) -> float:
    """Euclidean distance between two convex polygons; 0.0 when they touch or overlap."""
    n, m = len(p), len(q)
    for i in range(n):
        for j in range(m):
            if segments_intersect(p[i], p[(i + 1) % n], q[j], q[(j + 1) % m]):
                return 0.0
    if _point_in_poly(p[0], q) or _point_in_poly(q[0], p):
        return 0.0
    best = float("inf")
    for i in range(n):
        for j in range(m):
            best = min(best, point_segment_distance(p[i], q[j], q[(j + 1) % m]), point_segment_distance(q[j], p[i], p[(i + 1) % n]))
    return best


def point_rect_distance(p: Point, r: Rect) -> float:
    """Distance from a point to an axis-aligned rectangle (0.0 inside)."""
    import math
    return math.hypot(max(r[0] - p[0], 0.0, p[0] - r[2]), max(r[1] - p[1], 0.0, p[1] - r[3]))
