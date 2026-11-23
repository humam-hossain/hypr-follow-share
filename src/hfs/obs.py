"""Minimal synchronous obs-websocket v5 client."""

from __future__ import annotations

import base64
import hashlib
import itertools
import json
import os
from pathlib import Path

from websockets.sync.client import connect

OBS_WS_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "obs-studio" / "plugin_config" / "obs-websocket" / "config.json"


class OBSError(RuntimeError):
    pass


def ws_settings() -> dict:
    try:
        return json.loads(OBS_WS_CONFIG.read_text())
    except FileNotFoundError:
        return {}


class OBS:
    def __init__(self, host: str = "127.0.0.1", port: int | None = None, password: str | None = None):
        settings = ws_settings()
        port = port or settings.get("server_port", 4455)
        if password is None and settings.get("auth_required", True):
            password = settings.get("server_password", "")
        self._ids = itertools.count(1)
        self.ws = connect(f"ws://{host}:{port}", max_size=None, open_timeout=3)
        hello = json.loads(self.ws.recv())
        identify: dict[str, object] = {"rpcVersion": 1, "eventSubscriptions": 0}
        auth = hello["d"].get("authentication")
        if auth:
            secret = base64.b64encode(hashlib.sha256(((password or "") + auth["salt"]).encode()).digest())
            identify["authentication"] = base64.b64encode(hashlib.sha256(secret + auth["challenge"].encode()).digest()).decode()
        self.ws.send(json.dumps({"op": 1, "d": identify}))
        msg = json.loads(self.ws.recv())
        if msg.get("op") != 2:
            raise OBSError(f"identify failed: {msg}")

    def call(self, request_type: str, **data):
        rid = str(next(self._ids))
        self.ws.send(json.dumps({"op": 6, "d": {"requestType": request_type, "requestId": rid, "requestData": data}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("op") == 7 and msg["d"]["requestId"] == rid:
                break
        status = msg["d"]["requestStatus"]
        if not status["result"]:
            raise OBSError(f"{request_type}: {status.get('comment') or status['code']}")
        return msg["d"].get("responseData", {})

    def close(self):
        self.ws.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
