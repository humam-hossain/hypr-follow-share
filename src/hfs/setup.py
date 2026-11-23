"""`hfs up` / `hfs down`: OBS profile+scene, headless monitor, projector, daemon."""

from __future__ import annotations

import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from . import hypr
from .config import CONTROL_SOCKET, STATE_DIR, Config
from .geometry import max_size
from .obs import OBS, OBS_WS_CONFIG, OBSError

PROJECTOR_TITLE_RE = r"^(Windowed )?Projector"  # OBS <33: "Windowed Projector (Program)", 33+: "Projector - Program"
OBS_CLASS = "com.obsproject.Studio"
CAPTURE_KINDS = ("pipewire-screen-capture-source", "pipewire-desktop-capture-source")
PREVIOUS = STATE_DIR / "previous.json"
OBS_LAUNCHED = STATE_DIR / "obs-launched"  # pid of an OBS that `hfs up` started
OBS_BASIC = OBS_WS_CONFIG.parents[2] / "basic"
OBS_USER_INI = OBS_BASIC.parent / "user.ini"  # OBS 31+; older versions use global.ini


def say(msg: str) -> None:
    print(f"hfs: {msg}", flush=True)


# ------------------------------------------------------------------ geometry
def canvas_size(cfg: Config) -> tuple[int, int]:
    raw = {m["name"]: m for m in hypr.query("monitors")}
    if cfg.monitor not in raw:
        raise SystemExit(f"hfs: monitor {cfg.monitor!r} not found (have: {', '.join(raw)})")
    m = raw[cfg.monitor]
    w, h = max_size(m["width"], m["height"], cfg.aspect)
    return int(w) // 2 * 2, int(h) // 2 * 2


# ------------------------------------------------------------------ OBS
def obs_running() -> bool:
    return subprocess.run(["pgrep", "-x", "obs"], capture_output=True).returncode == 0


def enable_websocket_config() -> None:
    data = json.loads(OBS_WS_CONFIG.read_text()) if OBS_WS_CONFIG.exists() else {}
    if not data.get("server_enabled"):
        data["server_enabled"] = True
        OBS_WS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        OBS_WS_CONFIG.write_text(json.dumps(data, indent=2))
        say("enabled obs-websocket in OBS config")


def connect_obs(launch: bool = True, cfg: Config | None = None) -> OBS:
    try:
        return OBS()
    except (ConnectionRefusedError, OSError, TimeoutError):
        pass
    if obs_running():
        raise SystemExit(
            "hfs: OBS is running but its websocket is off.\n"
            "     Enable it: OBS > Tools > WebSocket Server Settings > Enable WebSocket server, then rerun."
        )
    if not launch:
        raise SystemExit("hfs: OBS is not running")
    enable_websocket_config()
    say("starting OBS")
    cmd = ["obs", "--minimize-to-tray", "--disable-missing-files-check"]
    if cfg and (OBS_BASIC / "scenes" / f"{cfg.collection}.json").exists():
        # Start straight in our collection so your normal collection's screen
        # captures don't pop share dialogs that get cancelled by the switch.
        cmd += ["--collection", cfg.collection]
    if cfg and (OBS_BASIC / "profiles" / cfg.profile).is_dir():
        cmd += ["--profile", cfg.profile]
    # Remember what OBS would normally open, so `hfs down` can hand it back.
    basic, prev = _ini_basic(), {}
    if cfg and basic.get("Profile", cfg.profile) != cfg.profile:
        prev["profile"] = basic["Profile"]
    if cfg and basic.get("SceneCollection", cfg.collection) != cfg.collection:
        prev["collection"] = basic["SceneCollection"]
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PREVIOUS.unlink(missing_ok=True)
    if prev:
        PREVIOUS.write_text(json.dumps(prev))
    proc = subprocess.Popen(cmd,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    OBS_LAUNCHED.write_text(str(proc.pid))
    for _ in range(60):
        time.sleep(0.5)
        try:
            return OBS()
        except (ConnectionRefusedError, OSError, TimeoutError):
            continue
    raise SystemExit("hfs: OBS started but websocket did not come up")


def ensure_profile_collection(obs: OBS, cfg: Config) -> None:
    profiles = obs.call("GetProfileList")
    collections = obs.call("GetSceneCollectionList")
    prev = {}
    if profiles["currentProfileName"] != cfg.profile:
        prev["profile"] = profiles["currentProfileName"]
        if cfg.profile in profiles["profiles"]:
            obs.call("SetCurrentProfile", profileName=cfg.profile)
        else:
            obs.call("CreateProfile", profileName=cfg.profile)
        say(f"OBS profile -> {cfg.profile}")
    if collections["currentSceneCollectionName"] != cfg.collection:
        prev["collection"] = collections["currentSceneCollectionName"]
        if cfg.collection in collections["sceneCollections"]:
            obs.call("SetCurrentSceneCollection", sceneCollectionName=cfg.collection)
        else:
            obs.call("CreateSceneCollection", sceneCollectionName=cfg.collection)
        say(f"OBS scene collection -> {cfg.collection}")
    if prev:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            # Keep what connect_obs saved when it launched OBS; fill in the rest.
            prev = {**prev, **json.loads(PREVIOUS.read_text())}
        except (OSError, ValueError):
            pass
        PREVIOUS.write_text(json.dumps(prev))


# OBS keeps the last-used profile/collection in user.ini [Basic].
_BASIC_KEYS = ("Profile", "ProfileDir", "SceneCollection", "SceneCollectionFile")


def _user_ini() -> Path:
    return OBS_USER_INI if OBS_USER_INI.exists() else OBS_BASIC.parent / "global.ini"


def _ini_basic() -> dict[str, str]:
    out, section = {}, ""
    try:
        lines = _user_ini().read_text().splitlines()
    except OSError:
        return out
    for line in lines:
        if line.startswith("["):
            section = line.strip()
        elif section == "[Basic]" and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _profile_dir(name: str) -> str:
    for ini in (OBS_BASIC / "profiles").glob("*/basic.ini"):
        try:
            if f"Name={name}" in ini.read_text().splitlines():
                return ini.parent.name
        except OSError:
            continue
    return name


def _collection_file(name: str) -> str:
    for f in (OBS_BASIC / "scenes").glob("*.json"):
        try:
            if json.loads(f.read_text()).get("name") == name:
                return f.name
        except (OSError, ValueError):
            continue
    return f"{name}.json"


def write_startup_selection(prev: dict) -> None:
    """Make OBS open `prev`'s profile/collection on its next launch, without loading them now."""
    want = {}
    if "profile" in prev:
        want |= {"Profile": prev["profile"], "ProfileDir": _profile_dir(prev["profile"])}
    if "collection" in prev:
        want |= {"SceneCollection": prev["collection"],
                 "SceneCollectionFile": _collection_file(prev["collection"])}
    if not want:
        return
    path = _user_ini()
    lines = path.read_text().splitlines() if path.exists() else []
    section, seen, out = "", set(), []
    for line in lines:
        if line.startswith("["):
            if section == "[Basic]":
                out += [f"{k}={v}" for k, v in want.items() if k not in seen]
                seen |= set(want)
            section = line.strip()
        elif section == "[Basic]" and "=" in line and line.split("=", 1)[0].strip() in want:
            k = line.split("=", 1)[0].strip()
            line = f"{k}={want[k]}"
            seen.add(k)
        out.append(line)
    if section == "[Basic]":
        out += [f"{k}={v}" for k, v in want.items() if k not in seen]
    elif not seen:
        out += ["", "[Basic]"] + [f"{k}={v}" for k, v in want.items()]
    path.write_text("\n".join(out) + "\n")


def launched_obs_pid() -> int | None:
    """Pid of the OBS that `hfs up` started, if it is still running."""
    try:
        pid = int(OBS_LAUNCHED.read_text())
        if Path(f"/proc/{pid}/comm").read_text().strip() == "obs":
            return pid
    except (OSError, ValueError):
        pass
    OBS_LAUNCHED.unlink(missing_ok=True)
    return None


def quit_obs(pid: int, timeout: float = 15) -> bool:
    """SIGTERM makes OBS close cleanly (no safe-mode prompt next start)."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not Path(f"/proc/{pid}").exists():
            return True
        time.sleep(0.2)
    return False


def ensure_video(obs: OBS, cfg: Config, w: int, h: int) -> None:
    v = obs.call("GetVideoSettings")
    want = {"baseWidth": w, "baseHeight": h, "outputWidth": w, "outputHeight": h,
            "fpsNumerator": cfg.fps, "fpsDenominator": 1}
    if any(v.get(k) != val for k, val in want.items()):
        obs.call("SetVideoSettings", **want)
        say(f"OBS canvas -> {w}x{h}@{cfg.fps}")


def ensure_scene_source(obs: OBS, cfg: Config) -> None:
    scenes = [s["sceneName"] for s in obs.call("GetSceneList")["scenes"]]
    if cfg.scene not in scenes:
        obs.call("CreateScene", sceneName=cfg.scene)
    obs.call("SetCurrentProgramScene", sceneName=cfg.scene)
    inputs = [i["inputName"] for i in obs.call("GetInputList")["inputs"]]
    if cfg.source not in inputs:
        kinds = obs.call("GetInputKindList")["inputKinds"]
        kind = next((k for k in CAPTURE_KINDS if k in kinds), None)
        if not kind:
            raise SystemExit(f"hfs: no PipeWire screen capture in OBS (kinds: {kinds})")
        obs.call("CreateInput", sceneName=cfg.scene, inputName=cfg.source, inputKind=kind,
                 inputSettings={"ShowCursor": True})
        say(f"A share dialog opened: pick monitor {cfg.monitor} and tick 'remember' / 'allow restore'.")
    item = obs.call("GetSceneItemId", sceneName=cfg.scene, sourceName=cfg.source)["sceneItemId"]
    for i in range(240):
        tr = obs.call("GetSceneItemTransform", sceneName=cfg.scene, sceneItemId=item)["sceneItemTransform"]
        if tr["sourceWidth"]:
            say(f"capture ready: {tr['sourceWidth']:.0f}x{tr['sourceHeight']:.0f}")
            return
        if i == 6:
            # Never press the source's "Reload" button here: it destroys the portal
            # session while the dialog is open and OBS 33 segfaults when it's answered.
            say(f"waiting for capture... pick monitor {cfg.monitor} in the share dialog")
        time.sleep(0.5)
    raise SystemExit("hfs: capture never produced frames. Quit OBS and rerun `hfs up`, "
                     f"or in OBS open '{cfg.source}' properties and press Reload.")


# ------------------------------------------------------------------ Hyprland
def _lua_str(s: str) -> str:
    return json.dumps(s)  # JSON string literal is a valid Lua string literal here


def headless_rules(cfg: Config, w: int, h: int) -> str:
    name = _lua_str(cfg.headless_name)
    title = PROJECTOR_TITLE_RE.replace("\\", "\\\\")
    return (
        f'hl.monitor({{output={name}, mode="{w}x{h}@60", position={_lua_str(cfg.headless_position)}, scale=1}}) '
        f'hl.window_rule({{match={{class="^(com\\\\.obsproject\\\\.Studio)$", title="{title}"}}, monitor={name}}})'
    )


def headless_ok(cfg: Config, w: int, h: int) -> bool | None:
    """None if the output doesn't exist, else whether its geometry matches."""
    for m in hypr.query("monitors"):
        if m["name"] == cfg.headless_name:
            x, y = (int(v) for v in cfg.headless_position.split("x"))
            return (m["width"], m["height"], m["x"], m["y"]) == (w, h, x, y)
    return None


def ensure_headless_layout(cfg: Config, w: int, h: int | None = None) -> None:
    h = h or round(w / cfg.aspect)
    if headless_ok(cfg, w, h) is False:
        hypr.eval_lua(headless_rules(cfg, w, h))


def ensure_headless(cfg: Config, w: int, h: int) -> None:
    if headless_ok(cfg, w, h) is None:
        hypr.hyprctl("output", "create", "headless", cfg.headless_name)
        say(f"created virtual monitor {cfg.headless_name}")
    hypr.eval_lua(headless_rules(cfg, w, h))
    time.sleep(0.3)
    if not headless_ok(cfg, w, h):
        raise SystemExit("hfs: virtual monitor geometry did not apply")


def projector_windows() -> list[dict]:
    return [c for c in hypr.clients() if c["class"] == OBS_CLASS and re.match(PROJECTOR_TITLE_RE, c["title"])]


def ensure_projector(obs: OBS, cfg: Config) -> None:
    if not projector_windows():
        obs.call("OpenVideoMixProjector", videoMixType="OBS_WEBSOCKET_VIDEO_MIX_TYPE_PROGRAM", monitorIndex=-1)
        for _ in range(40):
            time.sleep(0.1)
            if projector_windows():
                break
        else:
            raise SystemExit("hfs: projector window did not appear")
    ws = next(m["activeWorkspace"] for m in hypr.query("monitors") if m["name"] == cfg.headless_name)
    win = projector_windows()[0]
    sel = _lua_str(f"address:{win['address']}")
    if win["workspace"]["name"] != ws["name"]:
        # Must be the workspace *visible* on the headless monitor, or nothing renders it.
        hypr.dispatch(f"hl.dsp.window.move({{workspace={_lua_str(ws["name"])}, follow=false, window={sel}}})")
    win = projector_windows()[0]
    if not win["fullscreen"]:
        hypr.dispatch(f'hl.dsp.window.fullscreen({{mode="fullscreen", action="set", window={sel}}})')
    say(f"projector on {cfg.headless_name} (workspace {ws['name']})")


# ------------------------------------------------------------------ daemon
def send(cmd: str, *args: str, timeout: float = 2) -> dict | None:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(CONTROL_SOCKET))
            s.sendall((json.dumps({"cmd": cmd, "args": list(args)}) + "\n").encode())
            return json.loads(s.makefile().readline())
    except (FileNotFoundError, ConnectionRefusedError):
        return None


def start_daemon() -> None:
    if send("status"):
        say("daemon already running")
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log = open(STATE_DIR / "daemon.log", "ab")
    subprocess.Popen([sys.executable, "-m", "hfs", "daemon"], stdout=log, stderr=log,
                     stdin=subprocess.DEVNULL, start_new_session=True, env=os.environ.copy())
    for _ in range(30):
        time.sleep(0.1)
        if send("status"):
            say(f"daemon started (log: {STATE_DIR / 'daemon.log'})")
            return
    raise SystemExit(f"hfs: daemon did not start, see {STATE_DIR / 'daemon.log'}")


# ------------------------------------------------------------------ up/down
def up(cfg: Config) -> None:
    w, h = canvas_size(cfg)
    with connect_obs(cfg=cfg) as obs:
        ensure_profile_collection(obs, cfg)
        ensure_video(obs, cfg, w, h)
        ensure_scene_source(obs, cfg)
        ensure_headless(cfg, w, h)
        ensure_projector(obs, cfg)
    start_daemon()
    say(f"ready. In Discord/Meet/Zoom share the screen named {cfg.headless_name} ({w}x{h}).")


def down(cfg: Config, restore: bool = True) -> None:
    if send("quit"):
        say("daemon stopped")
    for win in projector_windows():
        hypr.dispatch(f'hl.dsp.window.close({{window={_lua_str("address:" + win["address"])}}})')
    if headless_ok(cfg, 0, 0) is not None:
        hypr.hyprctl("output", "remove", cfg.headless_name)
        say(f"removed virtual monitor {cfg.headless_name}")
    prev = {}
    try:
        prev = json.loads(PREVIOUS.read_text())
    except (OSError, ValueError):
        pass
    pid = launched_obs_pid()
    if pid and restore:
        # hfs started this OBS: quit it rather than switching it back live, which would
        # restart your own collection's screen captures and scripts right after stopping.
        if quit_obs(pid):
            say("OBS closed")
            write_startup_selection(prev)
            if prev:
                say(f"OBS will open {prev} next time")
            OBS_LAUNCHED.unlink(missing_ok=True)
            PREVIOUS.unlink(missing_ok=True)
        else:
            say(f"OBS (pid {pid}) did not close within 15 s")
    elif restore and prev:
        try:
            with connect_obs(launch=False) as obs:
                if "collection" in prev:
                    obs.call("SetCurrentSceneCollection", sceneCollectionName=prev["collection"])
                if "profile" in prev:
                    obs.call("SetCurrentProfile", profileName=prev["profile"])
            say(f"restored OBS {prev}")
            PREVIOUS.unlink()
        except (SystemExit, OBSError) as e:
            say(f"could not restore OBS profile/collection: {e}")
