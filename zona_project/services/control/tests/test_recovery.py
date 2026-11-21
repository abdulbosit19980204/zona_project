"""Kirish faqat bir martalik kod bilan: kod faqat egasining Telegram'iga, doimiy parol yo'q va yuborilmaydi."""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import control  # noqa: E402

OTP = {"CONTROL_AUTH": "otp", "CONTROL_PASSWORD": "", "CONTROL_TG_TOKEN": "1:x", "CONTROL_TG_CHAT_ID": "4242"}


def post(url, data=b""):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


class RecoveryTests(unittest.TestCase):
    def start(self, env):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        with mock.patch.dict(os.environ, env, clear=False):
            auth = control.Auth(self.dir)
            rec = control.Recovery(auth)
        sup = control.Supervisor({"mode": "process", "services": []})
        srv = control.http.server.ThreadingHTTPServer(("127.0.0.1", 0), control.make_handler(sup, auth, None, rec))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)  # cleanup teskari tartibda: avval to'xtatiladi, keyin yopiladi
        return f"http://127.0.0.1:{srv.server_address[1]}/", auth, rec

    def sent_code(self, call):
        return call.call_args[0][1]["text"].split("<code>")[1].split("</code>")[0]

    def test_otp_mode_has_no_permanent_password(self):
        base, auth, _rec = self.start(OTP)
        self.assertTrue(auth.otp_only)
        self.assertFalse(auth.hash)
        stored = json.loads((self.dir / "control-auth.json").read_text())
        self.assertEqual(set(stored), {"secret"})  # parol xeshi ham saqlanmaydi
        self.assertFalse((self.dir / "initial-password.txt").exists())
        html = urllib.request.urlopen(base + "login", timeout=5).read().decode()
        self.assertIn("one-time-code", html)
        self.assertIn("kod yuborish", html)
        self.assertIsNotNone(auth.check_password("1.1.1.1", "Secret-123"))  # har qanday "parol" — rad

    def test_code_goes_only_to_owner_works_once_and_expires(self):
        base, auth, _rec = self.start(OTP)
        with mock.patch.object(control.Recovery, "_call", return_value=True) as call:
            code, body = post(base + "recover", b"chat_id=999&password=")  # sahifadan boshqa chat berilsa ham — egasiga
            self.assertIn("yuborildi", body)
        method, params = call.call_args[0]
        self.assertEqual((method, params["chat_id"], params["protect_content"]), ("sendMessage", "4242", True))
        code = self.sent_code(call)
        self.assertEqual(len(code), 6)
        self.assertNotIn(code, (self.dir / "otp.json").read_text())  # diskda faqat xesh
        self.assertIsNone(auth.check_password("1.1.1.1", code))
        self.assertIsNotNone(auth.check_password("1.1.1.1", code))  # ikkinchi marta — yo'q
        code2 = auth.new_code()
        with mock.patch.object(control, "now", return_value=control.time.time() + 301):
            self.assertIsNotNone(auth.check_password("2.2.2.2", code2))  # 5 daqiqadan keyin — eskirgan

    def test_login_with_code_sets_session(self):
        base, auth, _rec = self.start(OTP)
        code = auth.new_code()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        r = opener.open(urllib.request.Request(base + "login", data=f"password={code}".encode(), method="POST"), timeout=5)
        self.assertIn("Kuzatuv", r.read().decode())

    def test_rate_limit_and_global_brute_force_wipes_codes(self):
        base, auth, rec = self.start(OTP)
        with mock.patch.object(control.Recovery, "_call", return_value=True) as call:
            for _ in range(5):
                post(base + "recover")
            code, body = post(base + "recover")
        self.assertIn("5 tadan", body)
        self.assertEqual(call.call_count, 5)
        live = auth.new_code()
        for i in range(30):  # 30 ta turli IP'dan xato — barcha kodlar bekor
            auth.check_password(f"10.0.0.{i}", "000000" if live != "000000" else "111111")
        self.assertIsNotNone(auth.check_password("9.9.9.9", live))

    def test_password_mode_never_sends_password(self):
        base, auth, _rec = self.start({"CONTROL_AUTH": "", "CONTROL_PASSWORD": "Secret-123", "CONTROL_TG_TOKEN": "1:x",
                                       "CONTROL_TG_CHAT_ID": "4242"})
        with mock.patch.object(control.Recovery, "_call", return_value=True) as call:
            post(base + "recover")
        self.assertNotIn("Secret-123", call.call_args[0][1]["text"])
        self.assertIsNone(auth.check_password("1.1.1.1", self.sent_code(call)))

    def test_not_configured_hides_button(self):
        base, _a, _r = self.start({"CONTROL_AUTH": "otp", "CONTROL_TG_TOKEN": "", "CONTROL_TG_CHAT_ID": ""})
        self.assertNotIn("kod yuborish", urllib.request.urlopen(base + "login", timeout=5).read().decode())

    def test_emergency_cli_code(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch.dict(os.environ, {"CONTROL_AUTH": "otp"}), mock.patch("builtins.print") as pr:
            control.main(["--data", tmp.name, "--issue-code"])
            code = pr.call_args[0][0]
            auth = control.Auth(Path(tmp.name))
        self.assertIsNone(auth.check_password("1.1.1.1", code))  # boshqa jarayon chiqargan kod ham ishlaydi


if __name__ == "__main__":
    unittest.main()
