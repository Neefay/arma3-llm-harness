"""HTTP client for the in-game bridge (python/bridge.py inside the game process)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


class BridgeError(RuntimeError):
    pass


@dataclass
class Bridge:
    port: int
    token: str
    host: str = "127.0.0.1"

    def _call(self, method: str, path: str, body: dict | None = None, timeout: float = 15) -> tuple[int, dict]:
        req = urllib.request.Request(
            f"http://{self.host}:{self.port}{path}", method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"X-BRMH-Token": self.token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except ValueError:
                return e.code, {"error": f"HTTP {e.code}"}
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            raise BridgeError(f"bridge unreachable on port {self.port}: {e}") from e

    def status(self, timeout: float = 5) -> dict:
        code, res = self._call("GET", "/status", timeout=timeout)
        if code != 200:
            raise BridgeError(f"status: HTTP {code} {res}")
        return res

    def alive(self) -> bool:
        try:
            self.status(timeout=2)
            return True
        except BridgeError:
            return False

    def exec(self, code: str, target: str = "server", timeout: float = 10, scheduled: bool = False,
             args: list | None = None) -> dict:
        """Run SQF; returns {id, ok, target, owners, results:[...], ms, error?}. Never raises on SQF errors."""
        body = {"code": code, "target": target, "timeout": timeout, "scheduled": scheduled, "args": args or []}
        _, res = self._call("POST", "/exec", body, timeout=timeout + 10)
        return res

    def events(self, since: int = 0, wait: float = 0, limit: int = 1000) -> dict:
        _, res = self._call("GET", f"/events?since={since}&wait={wait}&limit={limit}", timeout=wait + 10)
        return res

    def cursor(self) -> int:
        return int(self.events(since=1 << 60).get("next", 0))

    def wait_for(self, predicate, since: int, timeout: float) -> tuple[dict | None, int]:
        """Block until an event satisfies ``predicate``; returns (event or None, next cursor)."""
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            res = self.events(since=since, wait=max(0.0, min(remaining, 20)), limit=1000)
            for e in res.get("events", []):
                if predicate(e):
                    return e, e["seq"] + 1
            since = res.get("next", since)
            if time.time() >= deadline:
                return None, since
