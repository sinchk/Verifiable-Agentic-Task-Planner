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
