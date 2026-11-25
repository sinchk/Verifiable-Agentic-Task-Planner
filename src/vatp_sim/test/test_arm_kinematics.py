import math
import pytest
from vatp_sim.arm_kinematics import Unreachable, forward, topdown_ik


@pytest.mark.parametrize("x,y,z", [(0.62, 0.0, 0.075), (0.62, 0.30, 0.075), (0.62, -0.30, 0.10),
                                   (0.62, 0.0, 0.25), (0.70, 0.0, 0.10)])
def test_ik_roundtrip(x, y, z):
    q = topdown_ik(x, y, z)
    fx, fy, fz = forward(q)
    assert math.dist((fx, fy, fz), (x, y, z)) < 1e-6
    assert abs(q[1] + q[2] + q[4] - math.pi / 2) < 1e-9  # gripper points straight down


def test_unreachable():
    with pytest.raises(Unreachable):
        topdown_ik(1.6, 0.0, 0.1)
