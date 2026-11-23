from hfs import geometry as g

SRC_W, SRC_H, AR = 3440, 1440, 16 / 9


def test_max_size_is_full_height_16_9():
    assert g.max_size(SRC_W, SRC_H, AR) == (2560, 1440)


def test_size_for_height_clamps():
    assert g.size_for_height(5000, SRC_W, SRC_H, AR, 360) == (2560, 1440)
    w, h = g.size_for_height(10, SRC_W, SRC_H, AR, 360)
    assert h == 360 and round(w) == 640


def test_clamp_keeps_inside():
    r = g.clamp(g.Rect(3000, -50, 2560, 1440), SRC_W, SRC_H)
    assert (r.x, r.y) == (880, 0)


def test_deadzone_still_in_middle():
    cur = g.Rect(0, 0, 2560, 1440)
    t = g.follow_target(cur, 2560, 1440, 1280, 700, "deadzone", 0.22)
    assert (t.x, t.y) == (0, 0)


def test_deadzone_pushes_right():
    cur = g.Rect(0, 0, 2560, 1440)
    hi = 2560 * (1 - 0.22)
    t = g.follow_target(cur, 2560, 1440, hi + 100, 700, "deadzone", 0.22)
    assert abs(t.x - 100) < 1e-9


def test_center_mode():
    t = g.follow_target(g.Rect(0, 0, 1280, 720), 1280, 720, 2000, 800, "center", 0.22)
    assert (t.cx, t.cy) == (2000, 800)


def test_fit_selection_expands_to_aspect():
    r = g.fit_selection(g.Rect(100, 100, 400, 600), SRC_W, SRC_H, AR, 360)
    assert abs(r.w / r.h - AR) < 1e-9 and r.h == 600 and r.cy == 400


def test_smooth_converges():
    a, b = g.Rect(0, 0, 100, 100), g.Rect(100, 0, 100, 100)
    for _ in range(120):
        a = g.smooth(a, b, 1 / 60, 0.12)
    assert g.close_enough(a, b)
