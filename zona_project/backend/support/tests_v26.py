"""Bot javoblarini baholash: guruhda 👍/👎 va ⚠️ Xato javob (xodim), panelda xatolar ro'yxati, to'g'ri javobni
bitta tugma bilan guruhga yuborish va bilim bazasiga qo'shish; test rejimi yozuvi; skrinshotlarni saqlash muddati."""
from unittest import mock

from django.utils import timezone

from zona.models import Department, Member

from . import vision
from .models import Entry, Media, Message, Settings
from .tests import group_msg
from .tests_v6 import FlowBase
from .tests_v20 import cb


class ReviewTests(FlowBase):
    def setUp(self):
        super().setUp()
        Settings.load()
        Settings.objects.update(feedback_buttons=True, review_button=True, answer_test_note=True)
        self.bot.admin_chat_id = 555
        self.bot.save()
        dep = Department.objects.create(name="IT r")
        Member.objects.create(name="Test Xodim", role="r", department=dep, telegram="test_op")
        self.h().handle(group_msg(40, 1, "Nuqta отправлена на модерацию"))
        self.q = Message.objects.get(message_id=40)
        self.assertEqual(self.q.answered_by, "bot")

    def answer_msg(self):
        return next(m for m in self.tg.sent if m.get("buttons") and any("bad:" in b.get("callback_data", "") for r in m["buttons"] for b in r))

    def test_answer_has_buttons_and_test_note(self):
        m = self.answer_msg()
        datas = [b["callback_data"] for r in m["buttons"] for b in r]
        self.assertEqual(datas, [f"fb:{self.q.id}:1", f"fb:{self.q.id}:-1", f"bad:{self.q.id}"])
        texts = " ".join(x["text"] for x in self.tg.sent) + " ".join(e["text"] for e in getattr(self.tg, "edits", []))
        self.assertIn("тестовый режим", texts.lower())  # savol ruscha — yozuv ham ruscha
        self.assertEqual(texts.lower().count("🤖"), texts.lower().count("тестовый режим"))  # eski imzo takrorlanmaydi

    def test_anyone_can_press_wrong_and_staff_gets_original(self):
        self.h().handle(cb(1, f"bad:{self.q.id}", 1))  # agent (savol egasi) ham bosa oladi
        self.q.refresh_from_db()
        self.assertEqual((self.q.review, self.q.review_by, self.q.answer_hidden), ("wrong", "U1 (agent)", True))
        self.assertFalse(any(m["chat"] == 1 and "yashirildi" in m["text"] for m in self.tg.sent))  # agentga asl javob yo'q
        Message.objects.filter(pk=self.q.pk).update(review="", answer_hidden=False)
        upd = cb(2, f"bad:{self.q.id}", 2)
        upd["callback_query"]["from"]["username"] = "test_op"
        self.h().handle(upd)
        self.q.refresh_from_db()
        self.assertEqual((self.q.review, self.q.review_by), ("wrong", "Test Xodim"))
        self.assertTrue(any(m["chat"] == 555 and "Xato javob" in m["text"] for m in self.tg.sent))

    def test_asker_thumbs_go_to_review(self):
        self.h().handle(cb(1, f"fb:{self.q.id}:1", 3))
        self.q.refresh_from_db()
        self.assertEqual(self.q.review, "check")  # 👍 — to'g'riligini tasdiqlash uchun ko'rib chiqiladi

    def test_staff_thumbs_down_is_wrong(self):
        upd = cb(2, f"fb:{self.q.id}:-1", 4)
        upd["callback_query"]["from"]["username"] = "test_op"
        self.h().handle(upd)
        self.q.refresh_from_db()
        self.assertEqual(self.q.review, "wrong")

    def test_panel_list_fix_send_and_learn(self):
        Message.objects.filter(pk=self.q.pk).update(review="wrong", review_by="Test Xodim")
        Media.objects.create(kind=Media.PHOTO, path="x.jpg", message=self.q)
        self.login("editor")
        r = self.call("get", "support/reviews/?status=open").json()
        self.assertEqual((r["count"], r["counts"]["wrong"]), (1, 1))
        row = r["results"][0]
        self.assertEqual((row["id"], len(row["media"])), (self.q.id, 1))
        self.assertEqual(self.call("post", f"support/reviews/{self.q.id}/", {"action": "fix", "text": ""}).status_code, 400)
        fake = mock.Mock()
        fake.send.return_value = {"message_id": 777}
        with mock.patch("support.telegram.Client", return_value=fake):
            r = self.call("post", f"support/reviews/{self.q.id}/", {"action": "fix", "text": "Moderatsiya 1 kun", "send": True, "learn": True})
        self.assertEqual(r.status_code, 200, r.content)
        args, kw = fake.send.call_args
        self.assertEqual((args[0], kw["reply_to"]), (self.q.chat_id, self.q.bot_reply_id))  # bot javobiga reply
        self.q.refresh_from_db()
        self.assertEqual((self.q.review, self.q.fixed_msg_id, self.q.fixed_text), ("fixed", 777, "Moderatsiya 1 kun"))
        self.assertTrue(Entry.objects.filter(pk=r.json()["kb_entry"], priority=True).exists())  # tasdiqlash navbatida
        self.login("viewer")
        self.assertEqual(self.call("post", f"support/reviews/{self.q.id}/", {"action": "ok"}).status_code, 403)

    def test_media_kept_for_review_and_answer_days(self):
        old = timezone.now() - timezone.timedelta(days=40)
        Settings.objects.update(answer_keep_days=90)
        m = Media.objects.create(kind=Media.PHOTO, path="nope.jpg", message=self.q, source="question")
        Media.objects.filter(pk=m.pk).update(created_at=old)
        vision.cleanup(30)
        self.assertEqual(Media.objects.get(pk=m.pk).path, "nope.jpg")  # bot javobi — 90 kun saqlanadi
        Settings.objects.update(answer_keep_days=0)
        Message.objects.filter(pk=self.q.pk).update(review="wrong")
        vision.cleanup(30)
        self.assertEqual(Media.objects.get(pk=m.pk).path, "nope.jpg")  # tuzatilmagan xato — o'chmaydi
        Message.objects.filter(pk=self.q.pk).update(review="fixed")
        vision.cleanup(30)
        self.assertEqual(Media.objects.get(pk=m.pk).path, "")


class HideWrongAnswerTests(ReviewTests):
    def press_bad(self, n=10):
        upd = cb(2, f"bad:{self.q.id}", n)
        upd["callback_query"]["from"]["username"] = "test_op"
        self.h().handle(upd)
        self.q.refresh_from_db()

    def test_staff_mark_hides_answer_in_group_and_dms_staff(self):
        self.press_bad()
        self.assertTrue(self.q.answer_hidden)
        edit = [e for e in self.tg.edits if e["id"] == self.q.bot_reply_id][-1]
        self.assertIn("обновление", edit["text"])  # savol ruscha — yozuv ham ruscha
        self.assertIsNone(edit["buttons"])  # tugmalar olib tashlandi
        self.assertTrue(any(m["chat"] == 2 and "yashirildi" in m["text"] for m in self.tg.sent))  # xodimga asl javob
        self.assertTrue(self.q.answer_text)  # asl javob bazada saqlanadi

    def test_asker_thumbs_down_does_not_hide(self):
        self.h().handle(cb(1, f"fb:{self.q.id}:-1", 11))
        self.q.refresh_from_db()
        self.assertEqual((self.q.review, self.q.answer_hidden), ("wrong", False))

    def test_fix_replaces_hidden_message_and_ok_restores(self):
        self.press_bad()
        self.login("editor")
        with mock.patch("support.telegram.Client", return_value=self.tg):
            r = self.call("post", f"support/reviews/{self.q.id}/", {"action": "fix", "text": "Moderatsiya 1 kun davom etadi", "send": True})
        self.assertEqual(r.status_code, 200, r.content)
        self.q.refresh_from_db()
        self.assertEqual((self.q.fixed_msg_id, self.q.answer_hidden), (self.q.bot_reply_id, False))  # o'sha xabar o'rnida
        self.assertIn("Moderatsiya 1 kun davom etadi", self.tg.edits[-1]["text"])
        # boshqa javob: xato deb yashirildi, keyin "aslida to'g'ri" — qayta ko'rsatiladi
        Message.objects.filter(pk=self.q.pk).update(review="wrong", answer_hidden=True, fixed_msg_id=None)
        with mock.patch("support.telegram.Client", return_value=self.tg):
            self.call("post", f"support/reviews/{self.q.id}/", {"action": "ok"})
        self.q.refresh_from_db()
        self.assertFalse(self.q.answer_hidden)
        self.assertTrue(self.tg.edits[-1]["buttons"])  # 👍/👎 qaytdi


class HideAfterStaffAnswerTests(ReviewTests):
    def test_hidden_even_if_staff_answered_after_the_bot(self):
        # bot javob berdi, keyin xodim ham javob yozdi (answered_by — xodim nomi), so'ng bot javobi xato deb belgilandi
        Message.objects.filter(pk=self.q.pk).update(answered_by="Test Xodim", stage="staff")
        upd = cb(2, f"bad:{self.q.id}", 20)
        upd["callback_query"]["from"]["username"] = "test_op"
        self.h().handle(upd)
        self.q.refresh_from_db()
        self.assertTrue(self.q.answer_hidden)

    def test_escalation_ack_is_not_hidden(self):
        from . import review
        Message.objects.filter(pk=self.q.pk).update(status=Message.ESCALATED, answered_by="")
        self.q.refresh_from_db()
        self.assertFalse(review.hide(self.tg, self.q))
