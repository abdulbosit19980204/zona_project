"""Boshqaruv markazi testlari (faqat standart kutubxona): python -m unittest discover services/control/tests"""
from __future__ import annotations

import http.client
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import control  # noqa: E402

PY = sys.executable


def wait(cond, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.2)
    return False


def config(port_busy: int | None = None):
    return {"mode": "process", "services": [
        {"name": "ok", "label": "Barqaror", "cmd": [PY, "-c", "import time; print('salom', flush=True); time.sleep(120)"], "cwd": "."},
        {"name": "crash", "label": "Yiqiladigan", "cmd": [PY, "-c", "import sys; print('yiqildim', flush=True); sys.exit(3)"], "cwd": "."},
        {"name": "busy", "label": "Port band", "cmd": [PY, "-c", "import time; time.sleep(120)"], "cwd": ".", "port": port_busy},
    ]}


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.busy_port = self.listener.getsockname()[1]
        self.sup = control.Supervisor(config(self.busy_port))
        control.RESTART_MAX = 3

    def tearDown(self):
        self.sup.stop_all()
        self.listener.close()

    def test_start_stop_logs(self):
        s = self.sup.by_name["ok"]
        self.assertEqual(self.sup.start(s), "ok")
        self.assertTrue(wait(lambda: (self.sup.watch_once(), s.state == "running")[1]))
        self.assertTrue(wait(lambda: any("salom" in line for line in s.logs)))
        st = {x["name"]: x for x in self.sup.status()["services"]}["ok"]
        self.assertEqual(st["state"], "running")
        self.assertIsNotNone(st["pid"])
        pid = st["pid"]
        self.sup.stop(s)
        self.assertEqual(s.state, "stopped")
        self.assertIsNone(s.proc)
        self.assertTrue(pid)

    def test_crash_autorestart_then_gives_up(self):
        s = self.sup.by_name["crash"]
        self.sup.start(s)
        self.assertTrue(wait(lambda: (self.sup.watch_once(), s.state == "crashed")[1], timeout=30))
        self.assertEqual(s.total_restarts, control.RESTART_MAX)
        self.assertEqual(s.last_exit, 3)
        self.assertIn("yiqildi", s.last_error)
        self.assertTrue(any("avtomatik" in e["text"] for e in self.sup.events))

    def test_port_busy_is_external(self):
        s = self.sup.by_name["busy"]
        msg = self.sup.start(s)
        self.assertEqual(s.state, "external")
        self.assertIn("band", msg)
        self.assertIsNone(s.proc)

    def test_start_all_stop_all(self):
        self.sup.start_all()
        self.assertTrue(wait(lambda: (self.sup.watch_once(), self.sup.by_name["ok"].state == "running")[1]))
        self.sup.stop_all()
        self.assertTrue(all(x["state"] in ("stopped", "external") for x in self.sup.status()["services"]))


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ.pop("CONTROL_PASSWORD", None)
        cls.sup = control.Supervisor({"mode": "process", "services": [
            {"name": "ok", "label": "Barqaror", "cmd": [PY, "-c", "import time; time.sleep(120)"], "cwd": "."}]})
        cls.auth = control.Auth(Path(cls.tmp.name))
        cls.password = cls.auth.generated_password
        cls.server = control.http.server.ThreadingHTTPServer(("127.0.0.1", 0), control.make_handler(cls.sup, cls.auth))
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.sup.stop_all()
        cls.server.shutdown()
        cls.tmp.cleanup()

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse()
        return r.status, dict(r.getheaders()), r.read()

    def login(self) -> str:
        status, headers, _ = self.req("POST", "/login", f"password={self.password}", {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(status, 303)
        return headers["Set-Cookie"].split(";")[0]

    def test_password_generated_and_saved(self):
        self.assertTrue(self.password)
        self.assertEqual((Path(self.tmp.name) / "initial-password.txt").read_text().strip(), self.password)
        stored = json.loads((Path(self.tmp.name) / "control-auth.json").read_text())
        self.assertNotIn(self.password, json.dumps(stored))

    def test_requires_login(self):
        self.assertEqual(self.req("GET", "/api/status")[0], 401)
        self.assertEqual(self.req("GET", "/")[0], 303)
        self.assertEqual(self.req("POST", "/login", "password=xato", {"Content-Type": "application/x-www-form-urlencoded"})[0], 401)

    def test_status_and_actions(self):
        cookie = self.login()
        status, _, body = self.req("GET", "/api/status", headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["services"][0]["name"], "ok")
        # CSRF: X-Control sarlavhasisiz POST rad etiladi
        self.assertEqual(self.req("POST", "/api/services/ok/start", headers={"Cookie": cookie})[0], 403)
        status, _, body = self.req("POST", "/api/services/ok/start", headers={"Cookie": cookie, "X-Control": "1"})
        self.assertEqual(json.loads(body)["result"], "ok")
        status, _, body = self.req("GET", "/api/services/ok/logs", headers={"Cookie": cookie})
        self.assertIn("ishga tushirildi", "\n".join(json.loads(body)["lines"]))
        status, _, body = self.req("POST", "/api/all/stop", headers={"Cookie": cookie, "X-Control": "1"})
        self.assertEqual(json.loads(body)["services"][0]["state"], "stopped")
        # sahifa prefiks ostida ham ishlaydi (nginx: /control/)
        self.assertEqual(self.req("GET", "/control/api/status", headers={"Cookie": cookie})[0], 200)
        status, _, page = self.req("GET", "/", headers={"Cookie": cookie})
        self.assertIn("Servislar boshqaruv markazi".encode(), page)


if __name__ == "__main__":
    unittest.main()
