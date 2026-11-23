"""hfs command line. Every control command talks to the running daemon."""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys

from . import config, setup
from . import notify as notifications

USAGE = """\
hfs up [--notify]            start OBS scene, virtual monitor, projector and follow daemon
hfs down [--keep-profile] [--notify]
                             tear everything down (restores your previous OBS profile/collection)
hfs follow [on|off|toggle]   cursor follow
hfs mode [deadzone|center|toggle]
hfs zoom in|out|reset        shrink/grow the shared region (reset = full height, follow on)
hfs select                   drag a region with slurp (follow turns off)
hfs center                   jump region to the cursor
hfs status
hfs keys on|off              notification for entering/leaving the SUPER+ALT+Y key mode
hfs daemon                   run the follow loop in the foreground
"""


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE, end="")
        return
    cfg = config.load()
    cmd, args = argv[0], argv[1:]

    if cmd in ("up", "down"):
        p = argparse.ArgumentParser(prog=f"hfs {cmd}")
        p.add_argument("--notify", action="store_true", help="desktop notification with the result (for keybinds)")
        if cmd == "down":
            p.add_argument("--keep-profile", action="store_true")
        opts = p.parse_args(args)
        with _notifying(opts.notify, cmd):
            if cmd == "up":
                setup.up(cfg)
            else:
                setup.down(cfg, restore=not opts.keep_profile)
    elif cmd == "daemon":
        from . import daemon
        daemon.main(cfg)
    elif cmd == "keys":
        if args[:1] == ["off"]:
            notifications.send("Keys off", timeout_ms=1000, wait=True)
        else:
            notifications.send("Keys on", KEYS_HELP, timeout_ms=4000, wait=True)
    elif cmd == "select":
        if setup.send("status") is None:
            _print(None)
        notifications.send("Select region", "Drag a box · Esc cancels", timeout_ms=3000)
        res = subprocess.run(["slurp", "-f", "%x %y %w %h", "-d"], capture_output=True, text=True)
        if res.returncode != 0:
            notifications.send("Selection cancelled")
            return
        _print(setup.send("region", *res.stdout.split()))
    elif cmd in ("follow", "mode", "zoom", "center", "status"):
        _print(setup.send(cmd, *args))
    else:
        print(USAGE, end="", file=sys.stderr)
        sys.exit(2)


KEYS_HELP = """= / −  zoom   ·   0  reset   ·   C  center
F  follow   ·   M  mode   ·   S  select
U  start   ·   D  stop   ·   Esc  exit"""


def _notify(title: str, body: str, urgent: bool = False) -> None:
    notifications.send(title, body, urgent=urgent, timeout_ms=8000 if urgent else 4000, wait=True)


@contextlib.contextmanager
def _notifying(enabled: bool, cmd: str):
    if not enabled:
        yield
        return
    if cmd == "up":
        _notify("Starting…", "OBS · virtual monitor · projector (~10 s)")
    else:
        _notify("Stopping…", "")
    try:
        yield
    except SystemExit as e:
        if e.code not in (None, 0):
            _notify(f"hfs {cmd} failed", str(e.code), urgent=True)
        raise
    except Exception as e:
        _notify(f"hfs {cmd} failed", f"{type(e).__name__}: {e}", urgent=True)
        raise
    if cmd == "up":
        _notify("Ready to share", 'In Discord / Meet / Zoom share the screen "HFS"')
    else:
        _notify("Stopped", "")


def _print(resp: dict | None) -> None:
    # Keybinds have no terminal: report errors as notifications too.
    interactive = sys.stdout.isatty()
    if resp is None:
        if not interactive:
            _notify("Screen share is off", "SUPER+ALT+Y then U to start", urgent=True)
        sys.exit("hfs: daemon not running (run `hfs up`)")
    if not resp.get("ok"):
        if not interactive:
            _notify("hfs error", str(resp.get("error")), urgent=True)
        sys.exit(f"hfs: {resp.get('error')}")
    print(json.dumps(resp))
