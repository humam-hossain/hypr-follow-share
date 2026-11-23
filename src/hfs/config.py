"""User configuration with defaults. Optional file: ~/.config/hypr-follow-share/config.toml"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "hypr-follow-share" / "config.toml"
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
CONTROL_SOCKET = RUNTIME_DIR / "hfs.sock"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "hypr-follow-share"


@dataclass
class Config:
    # Physical monitor being captured.
    monitor: str = "DP-1"
    # Aspect ratio of the shared crop (and of the OBS canvas / virtual monitor).
    aspect_w: int = 16
    aspect_h: int = 9
    # Update rate of the follow loop.
    fps: int = 60
    # "deadzone" (pan only near edges) or "center" (keep cursor centered).
    mode: str = "deadzone"
    # Fraction of the crop width/height on each side where the cursor pushes the view.
    deadzone_margin: float = 0.22
    # Smoothing time constant in seconds (higher = floatier).
    smoothing: float = 0.12
    # Zoom step multiplier per keypress and smallest crop height in source pixels.
    zoom_step: float = 1.2
    min_height: int = 360
    # OBS names.
    profile: str = "hfs"
    collection: str = "hfs"
    scene: str = "HFS"
    source: str = "HFS Capture"
    # Virtual (headless) monitor that hosts the OBS projector. Placed off-layout so
    # the mouse can never reach it.
    headless_name: str = "HFS"
    headless_position: str = "-2560x-5000"
    # Desktop notifications on toggles.
    notify: bool = True

    @property
    def aspect(self) -> float:
        return self.aspect_w / self.aspect_h


def load() -> Config:
    cfg = Config()
    if CONFIG_PATH.exists():
        data = tomllib.loads(CONFIG_PATH.read_text())
        known = {f.name for f in fields(Config)}
        for key, value in data.items():
            if key not in known:
                raise SystemExit(f"hfs: unknown config key {key!r} in {CONFIG_PATH}")
            setattr(cfg, key, value)
    return cfg
