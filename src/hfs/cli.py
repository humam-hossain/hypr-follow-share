"""hfs command line. Every control command talks to the running daemon."""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys

from . import config, setup

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
    elif cmd == "select":
        res = subprocess.run(["slurp", "-f", "%x %y %w %h", "-d"], capture_output=True, text=True)
        if res.returncode != 0:
            return  # cancelled
        _print(setup.send("region", *res.stdout.split()))
    elif cmd in ("follow", "mode", "zoom", "center", "status"):
        _print(setup.send(cmd, *args))
    else:
        print(USAGE, end="", file=sys.stderr)
        sys.exit(2)


def _notify(title: str, body: str, urgent: bool = False) -> None:
    subprocess.run(
        ["notify-send", "-a", "hfs", "-t", "4000", "-u", "critical" if urgent else "normal",
         "-h", "string:x-canonical-private-synchronous:hfs", title, body],
        check=False,
    )


@contextlib.contextmanager
def _notifying(enabled: bool, cmd: str):
    if not enabled:
        yield
        return
    _notify("Screen share", "Starting..." if cmd == "up" else "Stopping...")
    try:
        yield
    except SystemExit as e:
        if e.code not in (None, 0):
            _notify(f"hfs {cmd} failed", str(e.code), urgent=True)
        raise
    except Exception as e:
        _notify(f"hfs {cmd} failed", f"{type(e).__name__}: {e}", urgent=True)
        raise
    _notify("Screen share", 'Ready. Share screen "HFS".' if cmd == "up" else "Stopped.")


def _print(resp: dict | None) -> None:
    if resp is None:
        sys.exit("hfs: daemon not running (run `hfs up`)")
    if not resp.get("ok"):
        sys.exit(f"hfs: {resp.get('error')}")
    print(json.dumps(resp))
