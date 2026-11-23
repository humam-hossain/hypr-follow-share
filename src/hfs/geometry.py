"""Pure crop-region math: aspect-locked sizing, deadzone/center follow, smoothing."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


def max_size(src_w: float, src_h: float, aspect: float) -> tuple[float, float]:
    """Largest aspect-locked crop that fits the source (full height on an ultrawide)."""
    h = min(src_h, src_w / aspect)
    return h * aspect, h


def size_for_height(h: float, src_w: float, src_h: float, aspect: float, min_h: float) -> tuple[float, float]:
    _, max_h = max_size(src_w, src_h, aspect)
    h = max(min(h, max_h), min(min_h, max_h))
    return h * aspect, h


def clamp(r: Rect, src_w: float, src_h: float) -> Rect:
    return Rect(min(max(r.x, 0.0), src_w - r.w), min(max(r.y, 0.0), src_h - r.h), r.w, r.h)


def _deadzone_axis(pos: float, size: float, cursor: float, margin: float) -> float:
    lo = pos + size * margin
    hi = pos + size * (1 - margin)
    if cursor < lo:
        return pos - (lo - cursor)
    if cursor > hi:
        return pos + (cursor - hi)
    return pos


def follow_target(current: Rect, w: float, h: float, cx: float, cy: float, mode: str, margin: float) -> Rect:
    """Where the crop should go for cursor (cx, cy), given the new size (w, h)."""
    if mode == "center":
        return Rect(cx - w / 2, cy - h / 2, w, h)
    # Resize around the current center first, then push by the deadzone.
    x = current.cx - w / 2
    y = current.cy - h / 2
    return Rect(_deadzone_axis(x, w, cx, margin), _deadzone_axis(y, h, cy, margin), w, h)


def fit_selection(sel: Rect, src_w: float, src_h: float, aspect: float, min_h: float) -> Rect:
    """Grow a free-form selection to the aspect ratio around its center, then clamp."""
    h = max(sel.h, sel.w / aspect)
    w, h = size_for_height(h, src_w, src_h, aspect, min_h)
    return clamp(Rect(sel.cx - w / 2, sel.cy - h / 2, w, h), src_w, src_h)


def smooth(current: Rect, target: Rect, dt: float, tau: float) -> Rect:
    """Frame-rate independent exponential smoothing."""
    if tau <= 0:
        return target
    a = 1 - math.exp(-dt / tau)
    return Rect(*(c + (t - c) * a for c, t in ((current.x, target.x), (current.y, target.y), (current.w, target.w), (current.h, target.h))))


def close_enough(a: Rect, b: Rect, eps: float = 0.05) -> bool:
    return abs(a.x - b.x) < eps and abs(a.y - b.y) < eps and abs(a.w - b.w) < eps and abs(a.h - b.h) < eps
