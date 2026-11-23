"""Desktop notifications with the hfs icon.

Every hfs notification replaces the previous one (notify-send --replace-id, with the id
kept in $XDG_RUNTIME_DIR), so rapid key presses update one popup instead of stacking.
The id is reused only while that popup is still showing: Quickshell updates an expired
notification silently, without a new popup.
The icon is sent as an image-path hint (a PNG file), which works without icon-theme
cache refreshes; it is also installed into the hicolor theme under ICON."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .config import RUNTIME_DIR

APP = "Screen share"
ICON = "hypr-follow-share"
ICON_SRC = Path(__file__).with_name("icon.svg")
_ICONS = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "icons" / "hicolor"
ICON_SVG = _ICONS / "scalable" / "apps" / f"{ICON}.svg"
ICON_PNG = _ICONS / "128x128" / "apps" / f"{ICON}.png"
ID_FILE = RUNTIME_DIR / "hfs-notify-id"
_lock = threading.Lock()


def ensure_icon() -> Path:
    """Install the icon (SVG + 128px PNG) and return the best file to show."""
    try:
        if not ICON_SVG.exists() or ICON_SVG.read_bytes() != ICON_SRC.read_bytes():
            ICON_SVG.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ICON_SRC, ICON_SVG)
            ICON_PNG.unlink(missing_ok=True)
        if not ICON_PNG.exists() and shutil.which("rsvg-convert"):
            ICON_PNG.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["rsvg-convert", "-w", "128", "-h", "128", "-o", str(ICON_PNG), str(ICON_SVG)], check=False)
    except OSError:
        return ICON_SRC
    return ICON_PNG if ICON_PNG.exists() else ICON_SVG


def _send(cmd: list[str], timeout_ms: int) -> None:
    with _lock:
        try:
            last, until = ID_FILE.read_text().split()
            if time.time() < float(until):
                cmd = cmd[:1] + ["-r", last] + cmd[1:]
        except (OSError, ValueError):
            pass
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return
        if out.isdigit():
            try:
                ID_FILE.write_text(f"{out} {time.time() + timeout_ms / 1000 - 0.3:.3f}")
            except OSError:
                pass


def send(title: str, body: str = "", *, urgent: bool = False, timeout_ms: int = 1500, wait: bool = False) -> None:
    image = ensure_icon()
    cmd = ["notify-send", "-p", "-e", "-a", APP, "-t", str(timeout_ms), "-h", f"string:image-path:{image}"]
    if urgent:
        cmd += ["-u", "critical"]
    cmd += [title, body]
    if wait:
        _send(cmd, timeout_ms)
    else:
        threading.Thread(target=_send, args=(cmd, timeout_ms), daemon=True).start()
