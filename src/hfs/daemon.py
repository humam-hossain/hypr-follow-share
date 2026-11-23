"""Follow loop: reads the cursor from Hyprland, pans/zooms the OBS capture item."""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field

from . import geometry as g
from . import hypr, setup
from . import notify as notifications
from .config import CONTROL_SOCKET, Config
from .obs import OBS

log = logging.getLogger("hfs")


@dataclass
class State:
    follow: bool = True
    mode: str = "deadzone"
    height: float = 0.0  # desired crop height in source px (0 = max)
    region: tuple[float, float, float, float] | None = None  # pending selection, global layout coords
    recenter: bool = False
    paused: bool = False  # cursor off the captured monitor
    lock: threading.Lock = field(default_factory=threading.Lock)


def notify(cfg: Config, title: str, body: str = "") -> None:
    if cfg.notify:
        notifications.send(title, body)


class Daemon:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.state = State(mode=cfg.mode)
        self.running = True
        self.info: dict = {}

    # ---------------------------------------------------------------- control
    def handle(self, cmd: str, args: list[str]) -> dict:
        s, cfg = self.state, self.cfg
        with s.lock:
            arg = args[0] if args else "toggle"
            if cmd == "follow":
                s.follow = {"on": True, "off": False}.get(arg, not s.follow)
                notify(cfg, "Follow ON" if s.follow else "Follow OFF", "" if s.follow else "View frozen in place")
            elif cmd == "mode":
                s.mode = arg if arg in ("deadzone", "center") else ("center" if s.mode == "deadzone" else "deadzone")
                notify(cfg, f"Mode: {s.mode}",
                       "Pans when the cursor nears an edge" if s.mode == "deadzone" else "Keeps the cursor centered")
            elif cmd == "zoom":
                h = s.height or self.info.get("max_h", 0)
                if arg == "in":
                    s.height = h / cfg.zoom_step
                elif arg == "out":
                    s.height = h * cfg.zoom_step
                elif arg == "reset":
                    s.height = 0
                    s.follow = True
                else:
                    return {"ok": False, "error": "zoom in|out|reset"}
                self._notify_zoom(arg)
            elif cmd == "region":
                x, y, w, h = map(float, args[:4])
                s.region = (x, y, w, h)
            elif cmd == "center":
                s.recenter = True
                notify(cfg, "Centered on cursor")
            elif cmd == "status":
                pass
            elif cmd == "quit":
                self.running = False
            else:
                return {"ok": False, "error": f"unknown command {cmd!r}"}
            return {"ok": True, "follow": s.follow, "mode": s.mode, "height": s.height, "paused": s.paused, **self.info}

    def _notify_zoom(self, arg: str) -> None:
        """Clamp the requested height like the loop does and report the zoom level."""
        s, cfg = self.state, self.cfg
        src = self.info.get("source")
        if not src:
            notify(cfg, "Zoom", "Capture not ready yet")
            return
        max_h = self.info["max_h"]
        w, h = g.size_for_height(s.height or max_h, src[0], src[1], cfg.aspect, cfg.min_height)
        s.height = 0 if h >= max_h else h
        size = f"{w:.0f}×{h:.0f}"
        if s.height == 0:
            body = f"Full height · {size}" + (" · follow ON" if arg == "reset" else "")
            notify(cfg, "Zoom reset" if arg == "reset" else "Zoom 1.00× (widest)", body)
        else:
            limit = " (max)" if h <= min(cfg.min_height, max_h) + 0.5 else ""
            notify(cfg, f"Zoom {max_h / h:.2f}×{limit}", size)

    def serve(self) -> None:
        try:
            CONTROL_SOCKET.unlink()
        except FileNotFoundError:
            pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(CONTROL_SOCKET))
        os.chmod(CONTROL_SOCKET, 0o600)
        srv.listen(8)
        while self.running:
            conn, _ = srv.accept()
            with conn:
                try:
                    req = json.loads(conn.makefile().readline())
                    resp = self.handle(req["cmd"], req.get("args", []))
                except Exception as e:  # keep serving on bad input
                    resp = {"ok": False, "error": str(e)}
                conn.sendall((json.dumps(resp) + "\n").encode())

    # ---------------------------------------------------------------- loop
    def run(self) -> None:
        threading.Thread(target=self.serve, daemon=True).start()
        while self.running:
            try:
                with OBS() as obs:
                    self.loop(obs)
            except Exception as e:
                log.warning("loop error: %s; retrying in 2s", e)
                time.sleep(2)
        try:
            CONTROL_SOCKET.unlink()
        except FileNotFoundError:
            pass

    def loop(self, obs: OBS) -> None:
        cfg, s = self.cfg, self.state
        item = obs.call("GetSceneItemId", sceneName=cfg.scene, sourceName=cfg.source)["sceneItemId"]
        tr = obs.call("GetSceneItemTransform", sceneName=cfg.scene, sceneItemId=item)["sceneItemTransform"]
        src_w, src_h = tr["sourceWidth"], tr["sourceHeight"]
        if not src_w:
            raise RuntimeError("capture source has no size yet (portal not answered?)")
        canvas_w = obs.call("GetVideoSettings")["baseWidth"]
        obs.call("SetSceneItemTransform", sceneName=cfg.scene, sceneItemId=item, sceneItemTransform={
            "alignment": 5, "boundsType": "OBS_BOUNDS_NONE", "rotation": 0,
            "cropLeft": 0, "cropRight": 0, "cropTop": 0, "cropBottom": 0,
        })
        max_w, max_h = g.max_size(src_w, src_h, cfg.aspect)
        self.info = {"source": [src_w, src_h], "canvas_w": canvas_w, "max_h": max_h}
        log.info("following %s: source %sx%s canvas width %s", cfg.monitor, src_w, src_h, canvas_w)

        mon = hypr.monitors()[cfg.monitor]
        sx_scale, sy_scale = src_w / mon.width, src_h / mon.height
        cx, cy = hypr.cursor()
        target = g.clamp(g.Rect((cx - mon.x) * sx_scale - max_w / 2, 0, max_w, max_h), src_w, src_h)
        current = target
        sent: g.Rect | None = None
        period = 1 / cfg.fps
        last = time.monotonic()
        last_check = 0.0

        while self.running:
            now = time.monotonic()
            dt, last = now - last, now
            if now - last_check > 2:  # survive layout changes and config reloads
                last_check = now
                mon = hypr.monitors()[cfg.monitor]
                sx_scale, sy_scale = src_w / mon.width, src_h / mon.height
                setup.ensure_headless_layout(cfg, canvas_w)

            gx, gy = hypr.cursor()
            on_mon = mon.x <= gx < mon.x + mon.width and mon.y <= gy < mon.y + mon.height
            px, py = (gx - mon.x) * sx_scale, (gy - mon.y) * sy_scale

            with s.lock:
                s.paused = not on_mon
                if s.region:
                    rx, ry, rw, rh = s.region
                    s.region = None
                    sel = g.Rect((rx - mon.x) * sx_scale, (ry - mon.y) * sy_scale, rw * sx_scale, rh * sy_scale)
                    target = g.fit_selection(sel, src_w, src_h, cfg.aspect, cfg.min_height)
                    s.height, s.follow = target.h, False
                    notify(cfg, f"Region {target.w:.0f}×{target.h:.0f}", "Follow OFF · 0 resets")
                else:
                    w, h = g.size_for_height(s.height or max_h, src_w, src_h, cfg.aspect, cfg.min_height)
                    s.height = 0 if h >= max_h else h
                    if s.recenter and on_mon:
                        target = g.Rect(px - w / 2, py - h / 2, w, h)
                    elif s.follow and on_mon:
                        target = g.follow_target(target, w, h, px, py, s.mode, cfg.deadzone_margin)
                    else:
                        target = g.Rect(target.cx - w / 2, target.cy - h / 2, w, h)
                    s.recenter = False
                    target = g.clamp(target, src_w, src_h)

            current = g.smooth(current, target, dt, cfg.smoothing)
            if sent is None or not g.close_enough(current, sent):
                scale = canvas_w / current.w
                obs.call("SetSceneItemTransform", sceneName=cfg.scene, sceneItemId=item, sceneItemTransform={
                    "positionX": -current.x * scale, "positionY": -current.y * scale,
                    "scaleX": scale, "scaleY": scale,
                })
                sent = current
            time.sleep(max(0.0, period - (time.monotonic() - now)))


def main(cfg: Config) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    Daemon(cfg).run()
