"""Runtime geofence monitor: geometry, episode counting, hysteresis, and agreement with the plan-time check."""
import itertools
import math
import random

import pytest

from vatp_core.geofence import GeofenceMonitor
from vatp_core.geometry import oriented_rect, point_rect_distance, polygon_distance, rect_corners, segment_hits_rect
from vatp_core.scenarios import base_world

AISLE = (7.0, 4.5, 8.0, 9.0)


def mon(**kw):
    kw.setdefault("front", 0.30)   # base only, so the geometry tests have simple numbers; the arm envelope has its own test
    return GeofenceMonitor({"restricted_aisle": AISLE}, **kw)


def test_point_and_polygon_distance():
    assert point_rect_distance((6.0, 6.0), AISLE) == pytest.approx(1.0)
    assert point_rect_distance((7.5, 6.0), AISLE) == 0.0                      # inside
    assert point_rect_distance((6.0, 4.0), AISLE) == pytest.approx(math.hypot(1.0, 0.5))
    a, b = rect_corners((0, 0, 1, 1)), rect_corners((3, 0, 4, 1))
    assert polygon_distance(a, b) == pytest.approx(2.0) == polygon_distance(b, a)
    assert polygon_distance(a, rect_corners((0.5, 0.5, 2, 2))) == 0.0          # overlap
    assert polygon_distance(a, rect_corners((0.2, 0.2, 0.4, 0.4))) == 0.0      # containment


def test_footprint_orientation_matters():
    m = mon()
    # robot 0.6 long x 0.4 wide, centre 1.0 m left of the aisle
    assert m.clearances(6.0, 6.0, 0.0)["restricted_aisle"] == pytest.approx((1.0, 0.7))        # long side towards the aisle
    assert m.clearances(6.0, 6.0, math.pi / 2)["restricted_aisle"] == pytest.approx((1.0, 0.8))  # short side towards it
    c = oriented_rect(0, 0, math.pi / 2, 0.3, 0.2)
    assert max(p[0] for p in c) == pytest.approx(0.2) and max(p[1] for p in c) == pytest.approx(0.3)


def test_violation_vs_margin_breach():
    m = mon()
    ev = m.update(6.75, 6.0, math.pi / 2)            # centre 0.25 m away, short side towards the aisle: 0.05 m clear
    assert [e["type"] for e in ev] == ["GEOFENCE_MARGIN"]
    assert (m.stats.violations, m.stats.margin_breaches) == (0, 1)
    ev = m.update(6.75, 6.0, 0.0)                    # long side towards the aisle: footprint now overlaps it
    assert [e["type"] for e in ev] == ["GEOFENCE_VIOLATION"]
    assert (m.stats.violations, m.stats.margin_breaches) == (1, 1)
    assert m.stats.min_footprint_clearance_m == 0.0 and m.stats.min_center_clearance_m == pytest.approx(0.25)


def test_episodes_not_samples():
    m = mon()
    for _ in range(50):                               # sit inside the aisle for many samples
        m.update(7.5, 6.0, 0.0)
    assert m.stats.violations == 1 and m.stats.samples == 50
    for x in (6.0, 5.0):                              # leave...
        m.update(x, 6.0, 0.0)
    m.update(7.5, 6.0, 0.0)                           # ...and come back: a second episode
    assert m.stats.violations == 2


def test_hysteresis_prevents_flicker():
    m = mon(margin=0.30)
    for c in (0.29, 0.31, 0.29, 0.305, 0.29):         # centre clearance jittering around the margin (yaw pi/2: no contact)
        m.update(7.0 - c, 6.0, math.pi / 2)
    assert m.stats.margin_breaches == 1
    m.update(5.0, 6.0, math.pi / 2)                   # clearly away resets
    m.update(7.0 - 0.2, 6.0, math.pi / 2)
    assert m.stats.margin_breaches == 2


def test_clean_run_is_clean():
    m = mon()
    for i in range(100):
        assert m.update(1.5 + 0.04 * i, 2.0, 0.0) == []
    assert (m.stats.violations, m.stats.margin_breaches) == (0, 0)
    assert m.stats.min_center_clearance_m > 2.0


def test_reset_clears_everything():
    m = mon()
    m.update(7.5, 6.0, 0.0)
    m.reset()
    assert m.stats.to_dict() == {"violations": 0, "margin_breaches": 0, "samples": 0, "min_center_clearance_m": None, "min_footprint_clearance_m": None}


def test_runtime_margin_agrees_with_plan_time_check():
    """For every leg between two zone access points, driving the straight line registers a margin breach exactly when the
    validator's segment test (same 0.3 m margin) flags the leg. Plan-time and run-time use one definition of 'too close'."""
    w = base_world(random.Random(0), "w", jitter=False)
    pts = {n: z.access for n, z in w.zones.items()}
    checked = flagged = 0
    for (na, a), (nb, b) in itertools.permutations(pts.items(), 2):
        m = GeofenceMonitor({k.name: k.rect for k in w.keepouts.values()}, margin=w.path_margin)
        yaw = math.atan2(b[1] - a[1], b[0] - a[0])
        n = 400
        for i in range(n + 1):
            m.update(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n, yaw)
        expected = any(segment_hits_rect(a, b, k.rect, w.path_margin) for k in w.keepouts.values())
        assert (m.stats.margin_breaches > 0) == expected, f"{na}->{nb}"
        checked += 1
        flagged += expected
    assert checked == 20 and flagged >= 2             # includes the staging/zone_a -> zone_b legs the validator rejects


def test_contact_tolerance_models_a_physical_barrier():
    """A barrier stops the robot with its footprint ~1 cm short of overlap: that still counts as contact; 5 cm clear does not."""
    m = mon()
    assert m.update(6.69, 6.0, 0.0)[0]["type"] == "GEOFENCE_VIOLATION"   # front edge at 6.99: 0.01 m from the aisle
    m = mon()
    assert m.update(6.65, 6.0, 0.0) == []        # nose 0.05 m clear (beyond the 2 cm tolerance) and centre 0.35 m away (beyond the 0.3 m margin)
    assert (m.stats.violations, m.stats.margin_breaches) == (0, 0)
    assert m.stats.min_footprint_clearance_m == pytest.approx(0.05)


def test_default_envelope_includes_the_stowed_arm():
    """In Gazebo the robot driven at the 0.3 m barrier stops with base_footprint 0.51 m short of it: the arm touches first."""
    m = GeofenceMonitor({"restricted_aisle": AISLE})
    assert m.front == pytest.approx(0.52)
    ev = m.update(6.4885, 6.0, 0.0)                       # the pose measured in the live test
    assert [e["type"] for e in ev] == ["GEOFENCE_VIOLATION"] and m.stats.violations == 1
    assert m.stats.min_center_clearance_m == pytest.approx(0.5115)   # the base-only footprint would have reported ~0.21 m clear
