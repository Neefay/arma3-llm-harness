"""Offline tests for the in-game bridge. Run with Pythia's embedded interpreter (Python 3.10):

    "<Arma>\\!Workshop\\@Pythia\\python-310-embed-amd64\\python.exe" -I python\\tests\\test_bridge.py

A fake game loop thread plays the SQF side (poll -> route -> emit dispatch/res).
"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import bridge  # noqa: E402


class FakeGame(threading.Thread):
    """Executes requests like the SQF hub: dispatch to N owners, each answers with a result."""

    def __init__(self, hub, owners_for=None):
        super().__init__(daemon=True)
        self.hub = hub
        self.owners_for = owners_for or (lambda target: [2])
        self.running = True
        self.seen = []

    def run(self):
        while self.running:
            for raw in self.hub.poll():
                req = json.loads(raw)
                self.seen.append(req)
                owners = self.owners_for(req["target"])
                self.hub.emit(json.dumps({"k": "dispatch", "id": req["id"], "owners": owners}))
                for o in owners:
                    self.hub.emit(json.dumps({"k": "res", "id": req["id"], "ok": True, "o": o,
                                              "r": req["code"][::-1]}))
            time.sleep(0.005)


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        os.environ["BRMH_HOME"] = self.home
        os.makedirs(os.path.join(self.home, "sessions"))
        self.session_file, self.port_file = bridge.session_paths()
        self.hub = bridge.Hub()
        self.game = None

    def tearDown(self):
        if self.game:
            self.game.running = False
        self.hub.stop()

    def write_session(self, **extra):
        session = {"token": "secret", "port": 0}
        session.update(extra)
        with open(self.session_file, "w", encoding="utf-8") as f:
            json.dump(session, f)

    def call(self, method, path, body=None, token="secret", timeout=10):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.hub.port, path), method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-BRMH-Token": token})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_inert_without_session_file(self):
        self.assertEqual(self.hub.start("m", "VR"), [False, 0])
        self.assertEqual(self.hub.poll(), [])
        self.assertFalse(os.path.exists(self.port_file))

    def test_start_writes_port_file_and_rejects_bad_token(self):
        self.write_session()
        active, port = self.hub.start("m", "VR")
        self.assertTrue(active)
        with open(self.port_file, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["port"], port)
        status, _ = self.call("GET", "/status", token="wrong")
        self.assertEqual(status, 403)

    def test_reattach_while_running_adopts_new_token(self):
        # Detach deletes the session and port files; the bridge keeps serving with the old token.
        self.write_session()
        _, port = self.hub.start("m", "VR")
        os.remove(self.session_file)
        os.remove(self.port_file)
        self.hub.poll()
        self.write_session(token="fresh", boot=[{"code": "boot code"}])
        self.hub.last_session_check = 0
        polled = self.hub.poll()
        self.assertTrue(any("boot code" in p for p in polled), polled)
        with open(self.port_file, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["port"], port)
        self.assertEqual(self.call("GET", "/status", token="fresh")[0], 200)
        self.assertEqual(self.call("GET", "/status", token="secret")[0], 403)

    def test_exec_multi_target_collects_all_results(self):
        self.write_session()
        self.hub.start("m", "VR")
        self.game = FakeGame(self.hub, lambda t: [2, 3, 4] if t == "all" else [2])
        self.game.start()
        status, res = self.call("POST", "/exec", {"code": "abc", "target": "all", "timeout": 5})
        self.assertEqual(status, 200, res)
        self.assertTrue(res["ok"])
        self.assertEqual(sorted(r["o"] for r in res["results"]), [2, 3, 4])

    def test_no_target_is_an_error_not_a_timeout(self):
        self.write_session()
        self.hub.start("m", "VR")
        self.game = FakeGame(self.hub, lambda t: [])
        self.game.start()
        t0 = time.time()
        status, res = self.call("POST", "/exec", {"code": "x", "target": "hcs", "timeout": 5})
        self.assertEqual(status, 504)
        self.assertIn("no machine", res["error"])
        self.assertLess(time.time() - t0, 2)

    def test_timeout_when_not_polled(self):
        self.write_session()
        self.hub.start("m", "VR")
        status, res = self.call("POST", "/exec", {"code": "x", "timeout": 0.3})
        self.assertEqual(status, 504)
        self.assertIn("never dispatched", res["error"])

    def test_boot_payload_first_and_requeued_on_mission_restart(self):
        self.write_session(boot=[{"code": "boot_code", "target": "server"}])
        self.hub.start("m", "VR")
        first = [json.loads(x) for x in self.hub.poll()]
        self.assertEqual([r["code"] for r in first], ["boot_code"])
        self.hub.start("m", "VR")  # mission restart
        again = [json.loads(x) for x in self.hub.poll()]
        self.assertEqual([r["id"] for r in again], ["boot2.0"])

    def test_restart_fails_pending_requests(self):
        self.write_session()
        self.hub.start("m", "VR")
        rid, slot = self.hub.submit({"code": "x"})
        self.hub.start("m", "VR")
        res = self.hub.collect(rid, slot, 0.5)
        self.assertEqual(res["results"][0]["error"], "mission restarted")

    def test_events_long_poll_and_cursor(self):
        self.write_session()
        self.hub.start("m", "VR")
        nxt = self.hub.read_events(0, 0, 100)["next"]

        def later():
            time.sleep(0.2)
            self.hub.emit(json.dumps({"k": "evt", "type": "fsm"}))

        threading.Thread(target=later, daemon=True).start()
        t0 = time.time()
        status, res = self.call("GET", "/events?since=%d&wait=3" % nxt)
        self.assertEqual(status, 200)
        self.assertLess(time.time() - t0, 2)
        self.assertEqual(res["events"][0]["type"], "fsm")
        self.assertFalse(res["dropped"])

    def test_bad_envelope_is_recorded_not_raised(self):
        self.write_session()
        self.hub.start("m", "VR")
        self.hub.emit("{not json")
        self.assertEqual(self.hub.events[-1]["k"], "bad")

    def test_entry_points_never_raise(self):
        sys._brmh_hub = None
        self.assertEqual(bridge.poll(), [])
        bridge.emit("garbage")


if __name__ == "__main__":
    unittest.main(verbosity=2)
