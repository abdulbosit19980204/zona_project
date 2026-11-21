"""Xavfsizlik markazi: SSH loglarini tahlil, sshd/portlar/yangilanishlar o'qish, xavf bahosi, API."""
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
import security as S  # noqa: E402

NOW = 1_763_700_000
ISO = lambda dt_s: time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(dt_s))  # noqa: E731
SSH_LINES = [
    f"{ISO(NOW - 100)} vmi sshd[1]: Failed password for root from 77.239.124.147 port 1 ssh2",
    f"{ISO(NOW - 200)} vmi sshd[2]: Invalid user admin from 109.160.32.168 port 2",
    f"{ISO(NOW - 3700)} vmi sshd[3]: Failed password for invalid user oracle from 109.160.32.168 port 3 ssh2",
    f"{ISO(NOW - 50)} vmi sshd[4]: Accepted password for root from 194.93.24.90 port 4 ssh2",
    f"{ISO(NOW - 90000)} vmi sshd[5]: Failed password for root from 1.2.3.4 port 5 ssh2",  # 24 soatdan eski
]
TCP = ("  sl  local_address rem_address   st\n"
       "   0: 00000000:0016 00000000:0000 0A 0\n"      # 0.0.0.0:22
       "   1: 0100007F:1F90 00000000:0000 0A 0\n"      # 127.0.0.1:8080
       "   2: 00000000:18EB 00000000:0000 0A 0\n"      # 0.0.0.0:6379
       "   3: 0100007F:0035 0100007F:1234 01 0\n")     # ESTABLISHED — sanalmaydi
SSHD = "# izoh\nPort 22\nPermitRootLogin yes\nPasswordAuthentication yes\nMatch User git\n  PasswordAuthentication no\n"
UPD = "16 updates can be applied immediately.\n5 of these updates are standard security updates.\n"


class ParseTests(unittest.TestCase):
    def test_ssh_failures_by_ip_user_hour(self):
        r = S.parse_ssh(SSH_LINES, NOW)
        self.assertEqual(r["fails"], 4)  # Accepted sanalmaydi
        self.assertEqual(r["top_ips"][0], ("109.160.32.168", 2))
        self.assertIn(("oracle", 1), r["top_users"])
        self.assertEqual(r["hours"][23], 2)  # oxirgi soat
        self.assertEqual(r["hours"][22], 1)
        self.assertEqual(sum(r["hours"]), 3)  # 24 soatdan eskisi grafikka kirmaydi

    def test_accepted(self):
        rows = S.parse_accepted(SSH_LINES * 2)
        self.assertEqual(rows, [{"ip": "194.93.24.90", "user": "root", "method": "password", "n": 2,
                                 "first": ISO(NOW - 50), "last": ISO(NOW - 50)}])

    def test_sshd_first_value_wins_and_match_ignored(self):
        c = S.parse_sshd("PasswordAuthentication no\n" + SSHD)
        self.assertEqual((c["permitrootlogin"], c["passwordauthentication"]), ("yes", "no"))
        self.assertEqual(S.parse_sshd(SSHD)["passwordauthentication"], "yes")

    def test_listen_ports(self):
        p = S.parse_listen(TCP)
        self.assertEqual(p, [("0.0.0.0", 22), ("127.0.0.1", 8080), ("0.0.0.0", 6379)])
        self.assertTrue(S.is_public("0.0.0.0"))
        self.assertFalse(S.is_public("127.0.0.1"))

    def test_updates(self):
        self.assertEqual(S.parse_updates(UPD), (16, 5))
        self.assertEqual(S.parse_updates(""), (None, None))


class AssessTests(unittest.TestCase):
    def test_bad_server_gets_low_score(self):
        d = {"sshd": {"permitrootlogin": "yes", "passwordauthentication": "yes"}, "ssh": {"fails": 11000, "unique_ips": 40},
             "firewall": {"active": False}, "fail2ban": False,
             "ports": [{"port": 22, "public": True, "name": "SSH"}, {"port": 6379, "public": True, "name": "Redis"}],
             "updates": {"total": 16, "security": 5, "reboot": True}, "certs": {"a.uz": 5}, "sites": [{"name": "A", "ok": False}],
             "backups": {"age_h": 50}, "failed_units": ["cloud-init.service"]}
        risks, score = S.Security.assess(d)
        self.assertEqual(score, 0)
        self.assertEqual(risks[0]["level"], "critical")
        titles = " ".join(r["title"] for r in risks)
        for frag in ("root parol", "11000", "Firewall", "fail2ban", "6379", "xavfsizlik yangilanishi", "qayta yuklanishni",
                     "SSL", "javob bermayapti", "zaxira", "cloud-init"):
            self.assertIn(frag, titles)

    def test_unreadable_sshd_config_is_unknown_not_safe(self):
        sec = S.Security({})
        with mock.patch.object(sec, "_run", return_value=""), \
             mock.patch.object(S.glob, "glob", return_value=["/etc/ssh/sshd_config.d/50-cloud-init.conf"]), \
             mock.patch.object(S.Path, "read_text", side_effect=[PermissionError(), "PasswordAuthentication no\n"]):
            conf = sec._sshd()
        self.assertNotIn("passwordauthentication", conf)
        risks, _score = S.Security.assess({"sshd": conf})
        self.assertIn("to'liq o'qib bo'lmadi", risks[0]["title"])

    def test_sshd_t_output_is_used(self):
        sec = S.Security({})
        with mock.patch.object(sec, "_run", return_value="port 22\npermitrootlogin yes\npasswordauthentication yes\n"):
            conf = sec._sshd()
        self.assertEqual((conf["permitrootlogin"], conf["passwordauthentication"]), ("yes", "yes"))
        self.assertEqual(S.Security.assess({"sshd": conf})[0][0]["level"], "critical")

    def test_good_server(self):
        d = {"sshd": {"permitrootlogin": "prohibit-password", "passwordauthentication": "no"}, "ssh": {"fails": 3},
             "firewall": {"active": True}, "fail2ban": True, "ports": [{"port": 443, "public": True, "name": ""}],
             "updates": {"total": 0, "security": 0, "reboot": False}, "certs": {"a.uz": 60}, "sites": [{"ok": True}],
             "backups": {"age_h": 3}, "failed_units": []}
        risks, score = S.Security.assess(d)
        self.assertEqual((risks, score), ([], 100))


class ApiTests(unittest.TestCase):
    def test_security_endpoint_and_unit_logs_allowlist(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        sup = control.Supervisor({"mode": "process", "services": []})
        auth = control.Auth(Path(tmp.name))
        sec = S.Security({"security": {}})
        sec.data = {"at": NOW, "score": 42, "risks": []}
        srv = control.http.server.ThreadingHTTPServer(("127.0.0.1", 0), control.make_handler(sup, auth, None, None, sec, ["biolab"]))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)  # cleanup teskari tartibda: avval to'xtatiladi, keyin yopiladi
        base = f"http://127.0.0.1:{srv.server_address[1]}/api/"
        hdr = {"Cookie": f"ctl_session={auth.make_cookie()}"}
        d = json.loads(urllib.request.urlopen(urllib.request.Request(base + "security", headers=hdr), timeout=5).read())
        self.assertEqual((d["score"], d["control"]["failed_logins_15m"]), (42, 0))
        with mock.patch.object(control.subprocess, "run", return_value=mock.Mock(stdout="a\nb", stderr="")) as run:
            d = json.loads(urllib.request.urlopen(urllib.request.Request(base + "units/biolab/logs?n=99999", headers=hdr), timeout=5).read())
        self.assertEqual(d["lines"], ["a", "b"])
        self.assertIn("3000", run.call_args[0][0])  # faqat sudoers'dagi qat'iy qiymat
        with self.assertRaises(urllib.error.HTTPError) as e:  # ro'yxatda yo'q servis — 404
            urllib.request.urlopen(urllib.request.Request(base + "units/sshd-secret/logs", headers=hdr), timeout=5)
        self.assertEqual(e.exception.code, 404)
        self.assertEqual((control.log_n(1), control.log_n(301), control.log_n(5000)), (300, 800, 3000))


if __name__ == "__main__":
    unittest.main()
