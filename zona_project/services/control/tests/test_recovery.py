"""'Parolni unutdim': parol (yoki bir martalik kod) faqat sozlangan egasining Telegram'iga; soatiga 3 marta."""
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
        with mock.patch.dict(os.environ, env, clear=False):
            auth = control.Auth(Path(tmp.name))
            rec = control.Recovery(auth)
        sup = control.Supervisor({"mode": "process", "services": []})
        srv = control.http.server.ThreadingHTTPServer(("127.0.0.1", 0), control.make_handler(sup, auth, None, rec))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)  # cleanup teskari tartibda: avval to'xtatiladi, keyin yopiladi
        return f"http://127.0.0.1:{srv.server_address[1]}/", auth, rec

    def test_not_configured_hides_button(self):
        base, _a, _r = self.start({"CONTROL_PASSWORD": "Secret-123", "CONTROL_TG_TOKEN": "", "CONTROL_TG_CHAT_ID": ""})
        html = urllib.request.urlopen(base + "login", timeout=5).read().decode()
        self.assertNotIn("Parolni unutdim", html)
        code, body = post(base + "recover")
        self.assertIn("sozlanmagan", body)

    def test_sends_password_only_to_owner_with_limit(self):
        base, _a, rec = self.start({"CONTROL_PASSWORD": "Secret-123", "CONTROL_TG_TOKEN": "1:x", "CONTROL_TG_CHAT_ID": "4242"})
        self.assertIn("Parolni unutdim", urllib.request.urlopen(base + "login", timeout=5).read().decode())
        with mock.patch.object(control.Recovery, "_call", return_value=True) as call:
            # sahifadan boshqa chat_id yuborilsa ham — faqat sozlangan egasiga
            code, body = post(base + "recover", b"chat_id=999&password=")
            self.assertIn("yuborildi", body)
            method, params = call.call_args[0]
            self.assertEqual((method, params["chat_id"], params["protect_content"]), ("sendMessage", "4242", True))
            self.assertIn("Secret-123", params["text"])
            post(base + "recover")
            post(base + "recover")
            code, body = post(base + "recover")
            self.assertIn("3 martadan", body)
            self.assertEqual(call.call_count, 3)

    def test_one_time_code_when_password_is_only_hashed(self):
        base, auth, rec = self.start({"CONTROL_PASSWORD": "", "CONTROL_TG_TOKEN": "1:x", "CONTROL_TG_CHAT_ID": "4242"})
        self.assertIsNone(auth.plain)
        with mock.patch.object(control.Recovery, "_call", return_value=True) as call:
            post(base + "recover")
        text = call.call_args[0][1]["text"]
        code = text.split("<code>")[1].split("</code>")[0]
        self.assertEqual(len(code), 6)
        self.assertIsNone(auth.check_password("1.1.1.1", code))      # kod bilan kirish
        self.assertIsNotNone(auth.check_password("1.1.1.1", code))   # bir martalik


if __name__ == "__main__":
    unittest.main()
