"""hfs command line. Every control command talks to the running daemon."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

from . import config, setup

USAGE = """\
hfs up                       start OBS scene, virtual monitor, projector and follow daemon
hfs down [--keep-profile]    tear everything down (restores your previous OBS profile/collection)
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

    if cmd == "up":
        setup.up(cfg)
    elif cmd == "down":
        p = argparse.ArgumentParser(prog="hfs down")
        p.add_argument("--keep-profile", action="store_true")
        setup.down(cfg, restore=not p.parse_args(args).keep_profile)
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


def _print(resp: dict | None) -> None:
    if resp is None:
        sys.exit("hfs: daemon not running (run `hfs up`)")
    if not resp.get("ok"):
        sys.exit(f"hfs: {resp.get('error')}")
    print(json.dumps(resp))
