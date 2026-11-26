"""Runtime geofence monitor: measures, from the robot's actual pose, how close it gets to each keep-out.

The validator proves *plans* keep clear of keep-outs; this checks what the robot *did*. Two measures, deliberately
separate so they can be compared with the plan-time guarantee:

  * violation  - the robot ENVELOPE (base + stowed arm, an oriented box) touches, or comes within ``contact_tol`` (2 cm) of, a keep-out
                 rectangle. The tolerance matters in Gazebo, where a physical barrier stops the robot just short of overlap.
  * margin breach - the robot CENTRE comes closer than ``margin`` to a keep-out. This is the same definition the
    validator uses for a leg (``path_margin``, 0.3 m), so plan-time flags and run-time breaches are comparable.

Events are counted per *episode* (entering the state), not per sample, with a little hysteresis so a pose that
jitters around a threshold is not counted repeatedly.  Pure Python: no ROS, no simulator.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .geometry import Rect, oriented_box, point_rect_distance, polygon_distance, rect_corners

HYSTERESIS_M = 0.02


@dataclass
class GeofenceStats:
    violations: int = 0                     # episodes of footprint contact with a keep-out
    margin_breaches: int = 0                # episodes of the centre path closer than the margin
    min_center_clearance_m: float | None = None
    min_footprint_clearance_m: float | None = None
    samples: int = 0

    def to_dict(self) -> dict:
        return {"violations": self.violations, "margin_breaches": self.margin_breaches, "samples": self.samples,
                "min_center_clearance_m": None if self.min_center_clearance_m is None else round(self.min_center_clearance_m, 3),
                "min_footprint_clearance_m": None if self.min_footprint_clearance_m is None else round(self.min_footprint_clearance_m, 3)}


@dataclass
class GeofenceMonitor:
    keepouts: dict[str, Rect]
    # swept envelope in the base_footprint frame: the 0.60 x 0.40 m base PLUS the stowed arm, which overhangs the front by ~0.2 m.
    # front = 0.52 m is measured: in Gazebo the robot driven at the 0.3 m barrier stops with base_footprint 0.51 m short of it.
    front: float = 0.52
    rear: float = 0.30
    half_wid: float = 0.20
    margin: float = 0.30
    contact_tol: float = 0.02               # footprint within this of a keep-out counts as contact (a physical barrier stops the robot short of overlap)
    stats: GeofenceStats = field(default_factory=GeofenceStats)
    # the two conditions are independent (a diagonal robot touches a keep-out before its centre is within the margin),
    # so each keep-out has one flag per condition
    _in_margin: dict[str, bool] = field(default_factory=dict)
    _in_violation: dict[str, bool] = field(default_factory=dict)

    def reset(self, keepouts: dict[str, Rect] | None = None) -> None:
        if keepouts is not None:
            self.keepouts = keepouts
        self.stats, self._in_margin, self._in_violation = GeofenceStats(), {}, {}

    def clearances(self, x: float, y: float, yaw: float) -> dict[str, tuple[float, float]]:
        """{keepout: (centre clearance, footprint clearance)} in metres."""
        foot = oriented_box(x, y, yaw, self.front, self.rear, self.half_wid)
        return {n: (point_rect_distance((x, y), r), polygon_distance(foot, rect_corners(r))) for n, r in self.keepouts.items()}

    def update(self, x: float, y: float, yaw: float) -> list[dict]:
        """Feed one pose sample. Returns the events for episodes that STARTED with this sample."""
        events: list[dict] = []
        st = self.stats
        st.samples += 1
        for name, (cc, fc) in self.clearances(x, y, yaw).items():
            st.min_center_clearance_m = cc if st.min_center_clearance_m is None else min(st.min_center_clearance_m, cc)
            st.min_footprint_clearance_m = fc if st.min_footprint_clearance_m is None else min(st.min_footprint_clearance_m, fc)
            # hysteresis: an episode ends only once the robot is clearly outside it
            was_v, was_m = self._in_violation.get(name, False), self._in_margin.get(name, False)
            now_v = fc <= self.contact_tol or (was_v and fc <= self.contact_tol + HYSTERESIS_M)
            now_m = cc < self.margin or (was_m and cc < self.margin + HYSTERESIS_M)
            if now_v and not was_v:
                st.violations += 1
                events.append({"type": "GEOFENCE_VIOLATION",
                               "detail": f"robot footprint touches keep-out '{name}' at ({x:.2f}, {y:.2f}); centre clearance {cc:.2f} m"})
            if now_m and not was_m:
                st.margin_breaches += 1
                events.append({"type": "GEOFENCE_MARGIN",
                               "detail": f"robot centre {cc:.2f} m from keep-out '{name}' (margin {self.margin:.2f} m) at ({x:.2f}, {y:.2f})"})
            self._in_violation[name], self._in_margin[name] = now_v, now_m
        return events
