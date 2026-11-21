"""Server resurslari: /proc o'qish, servislar (systemd), tarix, prognoz va API."""
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import control  # noqa: E402
import resources as R  # noqa: E402

MEMINFO = "MemTotal:       12247040 kB\nMemFree:  7000000 kB\nMemAvailable:    9947136 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n"
STAT1 = "cpu  100 0 100 700 100 0 0 0 0 0\ncpu0 1 1 1 1\n"
STAT2 = "cpu  200 0 200 1300 100 0 0 0 0 0\n"
NET = ("Inter-|   Receive | Transmit\n face |bytes packets errs drop fifo frame compressed multicast|bytes\n"
       "    lo: 999 0 0 0 0 0 0 0 999 0 0 0 0 0 0 0\n  eth0: 1000 0 0 0 0 0 0 0 4000 0 0 0 0 0 0 0\n")
SHOW = ("Id=foydali-backend.service\nMemoryCurrent=209715200\nCPUUsageNSec=5000000000\nActiveState=active\n\n"
        "Id=biolab.service\nMemoryCurrent=[not set]\nCPUUsageNSec=[not set]\nActiveState=inactive\n")


class ParseTests(unittest.TestCase):
    def test_meminfo(self):
        m = R.parse_meminfo(MEMINFO)
        self.assertEqual(m["total"], 12247040 * 1024)
        self.assertEqual(m["used"], (12247040 - 9947136) * 1024)
        self.assertEqual(m["swap_total"], 0)

    def test_cpu_delta(self):
        b1, t1 = R.parse_cpu(STAT1)
        b2, t2 = R.parse_cpu(STAT2)
        self.assertAlmostEqual(100 * (b2 - b1) / (t2 - t1), 25.0)  # 200 band / 800 jami

    def test_net_skips_loopback(self):
        self.assertEqual(R.parse_net(NET), (1000, 4000))

    def test_systemd_show_blocks(self):
        p = R.parse_systemd_show(SHOW)
        self.assertEqual(p["foydali-backend"]["MemoryCurrent"], "209715200")
        self.assertEqual(R._num(p["biolab"]["MemoryCurrent"]), 0)

    def test_growth_and_percentile(self):
        t0 = 1_700_000_000
        pts = [(t0 + i * 3600, 1000 + i * 100) for i in range(12)]  # soatiga +100 -> kuniga +2400
        self.assertAlmostEqual(R.growth_per_day(pts), 2400, delta=1)
        self.assertIsNone(R.growth_per_day(pts[:2]))
        self.assertEqual(R.pct([1, 2, 3, 4, 100], 0.5), 3)

    def test_dir_size(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a").write_bytes(b"x" * 10)
            (Path(d) / "s").mkdir()
            (Path(d) / "s" / "b").write_bytes(b"y" * 5)
            self.assertEqual(R.dir_size(Path(d)), 15)


class Svc:
    def __init__(self, name, unit="", group="G", label=None):
        self.name, self.unit, self.group, self.label, self.ext_pid, self.proc = name, unit, group, label or name, None, None


class FakeProc(R.Resources):
    stat = STAT1

    def _read(self, name):
        return {"stat": self.stat, "meminfo": MEMINFO, "net/dev": NET}.get(name, "")


class ResourcesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        cfg = {"resources": {"extra_units": [{"unit": "biolab", "label": "BioLab", "group": "Boshqa loyihalar"}],
                             "paths": [{"label": "data", "path": self.tmp.name}]}}
        self.r = FakeProc(cfg, [Svc("backend", "foydali-backend", "Platforma")], Path(self.tmp.name))

    def run_show(self):
        return mock.patch.object(R.subprocess, "run", return_value=mock.Mock(stdout=SHOW)), \
            mock.patch.object(R.shutil, "which", return_value="/bin/systemctl")

    def test_sample_groups_and_rest(self):
        a, b = self.run_show()
        with a, b:
            self.r.sample()
            self.r.stat = STAT2
            self.r.sample()
        snap = self.r.snapshot()
        cur = snap["current"]
        self.assertAlmostEqual(cur["cpu"], 25.0)
        self.assertEqual({s["key"] for s in cur["services"]}, {"foydali-backend", "biolab"})
        groups = {g["group"]: g for g in snap["groups"]}
        self.assertEqual(groups["Platforma"]["mem"], 209715200)
        self.assertIn("Tizim va boshqalar", groups)  # jami ishlatilgan RAM - ma'lum servislar
        self.assertEqual(cur["sizes"][0]["label"], "data")

    def test_history_persist_and_forecast(self):
        now = time.time()
        total = 100 * 2 ** 30
        for i in range(96):  # 24 soat, 15 daqiqalik; disk kuniga 2 GB o'sadi
            self.r.quarters.append({"t": int(now - (95 - i) * 900), "cpu": 30, "cpu_max": 50, "mem": 2e9, "disk": 50 * 2 ** 30 + i * 900 * 2 * 2 ** 30 / 86400, "load": 1, "s": {}})
        self.r.current = {"cores": 6, "mem": {"total": 12 * 2 ** 30, "used": 2e9, "swap_total": 0}, "disk": {"total": total, "used": 52 * 2 ** 30}}
        f = self.r.forecast()
        self.assertAlmostEqual(f["disk_growth_day"] / 2 ** 30, 2, delta=0.05)
        self.assertAlmostEqual(f["disk_days_to_90"], 19, delta=1)  # (90 - 52) GB / 2 GB
        self.assertTrue(any("Disk" in n[1] for n in f["notes"]))
        self.assertTrue(any("Swap" in n[1] for n in f["notes"]))
        self.r.save()
        again = FakeProc({}, [], Path(self.tmp.name))
        self.assertEqual(len(again.quarters), 96)

    def test_memory_leak_note(self):
        now = time.time()
        for i in range(24 * 60 // 10):
            self.r.minutes.append({"t": int(now - 86400 + i * 600), "cpu": 5, "cpu_max": 5, "mem": 1e9, "disk": 1, "load": 0.5,
                                   "s": {"foydali-backend": [200e6 + i * 4e6, 1]}})  # ~576 MB/kun o'sish
        self.r.current = {"cores": 6, "services": [{"key": "foydali-backend", "label": "Backend"}], "mem": {}, "disk": {}}
        self.assertTrue(any("Backend" in n[1] and "sizib" in n[1] for n in self.r.forecast()["notes"]))

    def test_minute_and_quarter_buckets(self):
        a, b = self.run_show()
        with a, b, mock.patch.object(R.time, "time") as t:
            for i in range(0, 1900, 10):
                t.return_value = 1_700_000_000 + i
                self.r.sample()
        self.assertGreaterEqual(len(self.r.minutes), 30)
        self.assertGreaterEqual(len(self.r.quarters), 2)


class ApiTests(unittest.TestCase):
    def test_resources_endpoint_requires_login(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        sup = control.Supervisor({"mode": "process", "services": []})
        auth = control.Auth(Path(tmp.name))
        res = FakeProc({}, [], Path(tmp.name))
        res.sample()
        srv = control.http.server.ThreadingHTTPServer(("127.0.0.1", 0), control.make_handler(sup, auth, res))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        url = f"http://127.0.0.1:{srv.server_address[1]}/api/resources"
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(url, timeout=5)
        self.assertEqual(e.exception.code, 401)
        req = urllib.request.Request(url + "?range=30d", headers={"Cookie": f"ctl_session={auth.make_cookie()}"})
        data = json.loads(urllib.request.urlopen(req, timeout=5).read())
        self.assertEqual(data["range"], "30d")
        self.assertIn("forecast", data)


if __name__ == "__main__":
    unittest.main()
