"""Records the demo: overview + chase cameras composed with a live overlay of the executor's event stream.

Frames are written as JPEGs (frame_000123.jpg) plus events.json; assemble with scripts/make_video.py.
Everything shown comes from the real system (cameras + /vatp/events) — nothing is synthesised.
"""
import json
import time
from pathlib import Path

import matplotlib
import numpy as np
import rclpy
from PIL import Image as PILImage, ImageDraw, ImageFont
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image

from vatp_interfaces.msg import MissionEvent

FONT_DIR = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
COLORS = {"ok": (120, 220, 130), "bad": (255, 110, 100), "warn": (255, 190, 80), "info": (225, 225, 225), "plan": (130, 190, 255)}


def _img(msg: Image) -> np.ndarray:
    return np.frombuffer(bytes(msg.data), np.uint8).reshape(msg.height, msg.width, 3)


def describe(e: dict):
    """(text, colour) for the events worth showing, else None."""
    t, node = e["type"], e["node"]
    try:
        d = json.loads(e["detail"]) if e["detail"].startswith("{") else {}
    except ValueError:
        d = {}
    if t == "PLAN_READY":
        m = d.get("metrics", {})
        return (f"PLAN validated: {m.get('nodes', '?')} nodes, {m.get('repairs', 0)} repairs, "
                f"validator {m.get('validation_ms', 0):.1f} ms", "plan")
    if t == "SKILL_START":
        a = ", ".join(f"{k}={v}" for k, v in d.get("args", {}).items())
        return (f"> {d.get('skill', node)}({a})", "info")
    if t == "SKILL_FAILED":
        return (f"x {d.get('skill')} FAILED: {d.get('code')}", "bad")
    if t == "FAULT_INJECTED":
        return (f"! FAULT INJECTED: {e['detail']}", "warn")
    if t == "FALLBACK_TRIGGERED":
        return ("~ recovery fallback triggered -> re-perceive + replan", "warn")
    if t == "REPLAN_READY":
        m = d.get("metrics", {})
        return (f"REPLAN validated: {m.get('nodes', '?')} nodes, {m.get('latency_s', d.get('latency_s', 0))}s", "plan")
    if t == "TREE_SWAPPED":
        return ("~ behavior tree swapped (patched subtree)", "warn")
    if t == "MISSION_END":
        return (f"MISSION {'SUCCESS' if d.get('success') else 'FAILED'}  (replans={d.get('replans')})",
                "ok" if d.get("success") else "bad")
    return None


class Recorder(Node):
    def __init__(self):
        super().__init__("frame_recorder")
        self.declare_parameter("out_dir", "runs/recording")
        self.declare_parameter("fps", 4.0)
        self.declare_parameter("title", "Verifiable Agentic Task Planner")
        self.declare_parameter("subtitle", "")
        self.out = Path(self.get_parameter("out_dir").value)
        self.out.mkdir(parents=True, exist_ok=True)
        self.over = self.chase = None
        self.lines: list = []
        self.log: list = []
        self.n = 0
        self.t0 = time.time()
        self.f_b = ImageFont.truetype(str(FONT_DIR / "DejaVuSans-Bold.ttf"), 22)
        self.f_s = ImageFont.truetype(str(FONT_DIR / "DejaVuSans.ttf"), 17)
        self.f_m = ImageFont.truetype(str(FONT_DIR / "DejaVuSansMono.ttf"), 16)
        self.create_subscription(Image, "/overview_cam/image", lambda m: setattr(self, "over", _img(m)), qos_profile_sensor_data)
        self.create_subscription(Image, "/chase_cam/image", lambda m: setattr(self, "chase", _img(m)), qos_profile_sensor_data)
        self.create_subscription(MissionEvent, "/vatp/events", self._ev, 200)
        self.create_timer(1.0 / float(self.get_parameter("fps").value), self._tick)

    def _ev(self, m: MissionEvent):
        e = {"t": time.time() - self.t0, "type": m.type, "node": m.node, "detail": m.detail}
        self.log.append(e)
        d = describe(e)
        if d:
            self.lines.append((e["t"], *d))
            self.lines = self.lines[-9:]

    def _tick(self):
        if self.over is None:
            return
        im = PILImage.fromarray(self.over).convert("RGBA")
        im = im.crop((71, 80, 1209, 720)).resize((1280, 720), PILImage.LANCZOS)   # drop empty sky, keep the arena
        W, H = im.size
        PX, PY, PW, PH = W - 14 - 600, 78, 600, 14 + 26 + 9 * 25
        ov = PILImage.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        d.rectangle([0, 0, W, 64], fill=(15, 20, 30, 215))                                   # title bar
        d.rectangle([PX, PY, PX + PW, PY + PH], fill=(15, 20, 30, 205))   # event panel (top-right, over empty floor)
        im = PILImage.alpha_composite(im, ov)
        d = ImageDraw.Draw(im)
        d.text((16, 8), self.get_parameter("title").value, font=self.f_b, fill=(255, 255, 255))
        d.text((16, 36), self.get_parameter("subtitle").value, font=self.f_s, fill=(170, 200, 255))
        el = time.time() - self.t0
        d.text((W - 150, 20), f"t = {el:6.1f} s", font=self.f_b, fill=(255, 220, 120))
        d.text((PX + 10, PY + 6), "executor events (live)", font=self.f_s, fill=(150, 160, 175))
        for i, (_, txt, col) in enumerate(self.lines):
            d.text((PX + 10, PY + 32 + i * 25), txt[:62], font=self.f_m, fill=COLORS[col])
        if self.chase is not None:
            c = PILImage.fromarray(self.chase).resize((448, 252))
            x, y = 14, H - 252 - 14   # bottom-left
            d.rectangle([x - 3, y - 3, x + 448 + 3, y + 252 + 3], fill=(15, 20, 30))
            im.paste(c, (x, y))
            d.text((x + 8, y + 6), "robot chase camera", font=self.f_s, fill=(255, 255, 255))
        im.convert("RGB").save(self.out / f"frame_{self.n:05d}.jpg", quality=88)
        self.log.append({"t": el, "type": "FRAME", "node": str(self.n), "detail": ""})
        self.n += 1

    def finish(self):
        (self.out / "events.json").write_text(json.dumps(self.log))


def main(args=None):
    rclpy.init(args=args)
    n = Recorder()
    try:
        rclpy.spin(n)
    except KeyboardInterrupt:
        pass
    finally:
        n.finish()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
