from vatp_sim import gz_perception as gp

SAMPLE = '''pose {
  name: "crate_1"
  id: 12
  position {
    x: 3.18
    y: 4.5
    z: 0.1
  }
  orientation {
    w: 1
  }
}
pose {
  name: "vatp_amr"
  position {
    x: 1.5
  }
}
pose {
  name: "small_box_1"
  position {
    y: -2.5e-1
    x: 5.7
  }
}
'''


def test_parse(monkeypatch):
    class R:  # noqa: D401
        stdout = SAMPLE
    monkeypatch.setattr(gp.subprocess, "run", lambda *a, **k: R)
    p = gp.object_poses()
    assert set(p) == {"crate_1", "small_box_1"}
    assert p["crate_1"] == (3.18, 4.5, 0.1)
    assert p["small_box_1"] == (5.7, -0.25, 0.0)


def test_grasp_height_clears_palm_and_floor():
    from vatp_sim.world_gen import grasp_height
    assert abs(grasp_height("crate_1", 0.1) - 0.16) < 1e-9      # top 0.20 -> palm bottom 0.22 > top
    assert abs(grasp_height("small_box_1", 0.05) - 0.075) < 1e-9  # clamped: fingertips above floor
