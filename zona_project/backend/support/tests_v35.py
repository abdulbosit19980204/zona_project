"""⭐ xodimni baholash; admin chatiga savol — fayllari va havolalari bilan; bitta savolga panel havolasi."""
import datetime as dt

from . import adminmsg, rating, resolution
from .models import Media, Message, StaffRating, TgUser
from .tests_v20 import NOON
from .tests_v27 import OpenBase, press


class RatingTests(OpenBase):
    def setUp(self):
        super().setUp()
        self.staff = TgUser.objects.create(tg_id=2, username="test_op", name="T", member=self.member)
        self.qq = self.q(status=Message.ANSWERED, answered_by="Test Xodim", answered_at=NOON - dt.timedelta(minutes=15),
                         handler=self.staff)
        resolution.ask_pending(self.tg, now=NOON)
        self.qq.refresh_from_db()

    def test_asker_solved_then_rates_staff(self):
        self.h().handle(press(1, f"rs:{self.qq.id}:1", username="agent1"))
        ask = self.tg.edits[-1]
        self.assertIn("baholang", ask["text"])
        self.assertEqual([b["callback_data"] for b in ask["buttons"][0]], [f"st:{self.qq.id}:{n}" for n in range(1, 6)])
        self.h().handle(press(9, f"st:{self.qq.id}:5", n=2, username="someone"))  # begona baholay olmaydi
        self.assertEqual(StaffRating.objects.count(), 0)
        self.h().handle(press(1, f"st:{self.qq.id}:4", n=3, username="agent1"))
        r = StaffRating.objects.get()
        self.assertEqual((r.stars, r.staff_id, r.source), (4, self.staff.pk, "asker"))
        self.assertIn("⭐⭐⭐⭐", self.tg.edits[-1]["text"])
        self.h().handle(press(1, f"st:{self.qq.id}:2", n=4, username="agent1"))  # qayta bosdi — yangilanadi
        self.assertEqual((StaffRating.objects.count(), StaffRating.objects.get().stars), (1, 2))
        self.assertEqual(rating.summary([self.staff.pk])[self.staff.pk]["avg"], 2)

    def test_panel_rating_and_board(self):
        self.login("editor")
        r = self.call("post", f"support/messages/{self.qq.id}/rate/", {"stars": 5, "comment": "zo'r"})
        self.assertEqual((r.status_code, r.json()["stars"]), (200, 5))
        m = self.call("get", f"support/messages/?id={self.qq.id}").json()
        self.assertEqual((len(m), m[0]["ratings"][0]["stars"]), (1, 5))
        b = self.call("get", "support/analytics/staff/?days=3650").json()
        row = next(x for x in b["staff"] if x["id"] == self.staff.pk)
        self.assertEqual((row["rating"], row["ratings"]), (5, 1))


class AdminCardTests(OpenBase):
    def test_card_has_source_who_link_and_files(self):
        q = self.q()
        Media.objects.create(message=q, kind=Media.PHOTO, path="", tg_file_ids={str(self.bot.id): "FILE1"})
        body = adminmsg.card(q, "⚠️ Xato javob", extra=["🚩 Belgiladi: X"], answer="Bot javobi matni")
        self.assertIn("ROP", body)
        self.assertIn("Skidka yoqib bering", body)
        self.assertIn("1 ta fayl", body)
        self.assertNotIn("OCR", body)
        sent = []
        self.tg.send_media = lambda chat, items, reply_to=None: sent.append(items) or ["FILE1"]
        adminmsg.send(self.tg, 555, q, body)
        self.assertEqual(sent[0][0]["file_id"], "FILE1")
        self.assertEqual(self.tg.sent[-1]["chat"], 555)


class EvaluateTests(OpenBase):
    def test_staff_eval_and_asker_detail(self):
        staff = TgUser.objects.create(tg_id=2, username="test_op", name="T", member=self.member)
        for i in range(4):
            q = self.q(mid=40 + i, status=Message.ANSWERED, resolution="no" if i < 2 else "yes", handler=staff)
            r = Message.objects.create(bot=self.bot, group=self.g, chat_id=-100, message_id=80 + i, kind="staff", text="К Саиду" if i == 0 else "Yoqildi, 10 blokdan",
                                       question=q, user=staff, source="live")
            Message.objects.filter(pk=r.pk).update(created_at=q.created_at + dt.timedelta(minutes=90))
        self.login("viewer")
        d = self.call("get", f"support/analytics/staff/{staff.pk}/?days=3650").json()
        self.assertIn("eval", d)
        self.assertIsNotNone(d["eval"]["score"])
        codes = {(i["kind"], i["code"]) for i in d["eval"]["items"]}
        self.assertIn(("minus", "resolve"), codes)  # 2/4 hal bo'lmadi
        a = self.call("get", f"support/analytics/asker/{self.asker.pk}/?days=3650").json()
        self.assertEqual(a["metrics"]["count"], 4)
        self.assertTrue(any(i["code"] == "help" or i["kind"] == "help" for i in a["insights"]))
        self.assertEqual(self.call("get", "support/analytics/asker/999999/").status_code, 404)
