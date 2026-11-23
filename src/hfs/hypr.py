"""Hyprland IPC over the command socket (no hyprctl process per call)."""

from __future__ import annotations

import json
import os
import socket
import subprocess
from dataclasses import dataclass


def _socket_path() -> str:
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not sig:
        raise RuntimeError("HYPRLAND_INSTANCE_SIGNATURE not set: not running under Hyprland?")
    return f"{os.environ['XDG_RUNTIME_DIR']}/hypr/{sig}/.socket.sock"


def request(cmd: str) -> bytes:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(_socket_path())
        s.sendall(cmd.encode())
        chunks = []
        while chunk := s.recv(65536):
            chunks.append(chunk)
    return b"".join(chunks)


def query(what: str):
    return json.loads(request(f"j/{what}"))


def cursor() -> tuple[float, float]:
    pos = query("cursorpos")
    return float(pos["x"]), float(pos["y"])


@dataclass
class Monitor:
    name: str
    x: int
    y: int
    width: int  # logical (layout) size
    height: int


def monitors() -> dict[str, Monitor]:
    out = {}
    for m in query("monitors"):
        scale = m["scale"] or 1
        w, h = m["width"] / scale, m["height"] / scale
        if m["transform"] % 2 == 1:  # rotated 90/270
            w, h = h, w
        out[m["name"]] = Monitor(m["name"], m["x"], m["y"], round(w), round(h))
    return out


def clients() -> list[dict]:
    return query("clients")


def hyprctl(*args: str) -> str:
    res = subprocess.run(["hyprctl", *args], capture_output=True, text=True)
    out = (res.stdout + res.stderr).strip()
    if res.returncode != 0 or out not in ("", "ok"):
        raise RuntimeError(f"hyprctl {' '.join(args)}: {out}")
    return out


def eval_lua(code: str) -> str:
    return hyprctl("eval", code)


def dispatch(lua_dispatcher: str) -> str:
    return hyprctl("dispatch", lua_dispatcher)
