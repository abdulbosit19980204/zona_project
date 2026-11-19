"""Vazifa eslatmasi (bot o'zi yozadi), skrinshot + alohida izoh = bitta savol, umumiy so'zlar savol emas."""
from unittest import mock

from zona.crypto import encrypt
from zona.models import Department, Member

from . import engine, tasks
from .engine import Decision
from .models import Entry, Group, Message, Settings, SupportTask, TgUser
from .tests import group_msg
from .tests_v6 import FlowBase


class RemindTests(FlowBase):
    def setUp(self):
        super().setUp()
        it = Department.objects.create(name="IT r")
        self.dev = Member.objects.create(name="Dev", role="d", department=it, telegram="dev_user")
        Settings.load()
        Settings.objects.update(tasks_enabled=True, task_departments=[it.id], task_mode="remind")
        TgUser.objects.create(tg_id=777, name="Dev", username="dev_user")
        self.g = Group.objects.create(bot=self.bot, chat_id=-1004410351675, title="VAZIFALAR")
        self.u = TgUser.objects.create(tg_id=5, name="Agent", username="agent1")

    def q(self, mid, text):
        return Message.objects.create(bot=self.bot, group=self.g, chat_id=self.g.chat_id, message_id=mid, user=self.u, text=text)

    def test_bot_reminds_staff_privately_and_briefly_in_group(self):
        q = self.q(1, "1C ga kira olmayapman")
        t = tasks.maybe_create(q, Decision("", None, 0, "", True, [{"id": self.dev.id}]), self.tg)
        self.assertEqual(t.status, SupportTask.REMINDED)
        dm = [x for x in self.tg.sent if x["chat"] == 777]
        group = [x for x in self.tg.sent if x["chat"] == self.g.chat_id]
        self.assertEqual(len(dm), 1)
        self.assertIn("<code>/vazifa", dm[0]["text"])
        self.assertIn("1C ga kira olmayapman", dm[0]["text"])  # tafsilot faqat mas'ulga
        self.assertEqual(dm[0]["buttons"][0][0]["url"], "https://t.me/c/4410351675/1")
        self.assertEqual(len(group), 1)
        self.assertNotIn("1C ga kira", group[0]["text"])  # guruhda faqat qisqa eslatma
        self.assertIn("@dev_user", group[0]["text"])
        # shu mavzudagi keyingi savol — qayta eslatilmaydi
        tasks.maybe_create(self.q(2, "1C ga hali kira olmayapman"), Decision("", None, 0, "", True, [{"id": self.dev.id}]), self.tg)
        self.assertEqual(len([x for x in self.tg.sent if x["chat"] == 777]), 1)

    def test_remind_mode_never_uses_account(self):
        SupportTask.objects.create(status="queued", text="/vazifa @x y")
        with mock.patch.object(tasks, "send_one") as send:
            self.assertFalse(tasks.process_queue())
            send.assert_not_called()


class MergeTests(FlowBase):
    def test_screenshot_then_comment_is_one_question(self):
        with mock.patch("support.runner.ocr.read_text", return_value="Торговая точка \"X\" отправлена на модерацию"):
            h = self.h()
            h.handle(group_msg(1, 10, "", photo=True))
            h.handle(group_msg(2, 10, "Добавьте пжл"))
        self.assertEqual(Message.objects.filter(kind="question").count(), 1)
        self.assertIn("Добавьте пжл", Message.objects.get(kind="question").text)
        self.assertEqual(len([x for x in self.tg.sent if x["chat"] == -100]), 1)

    def test_comment_then_screenshot_is_one_question(self):
        with mock.patch("support.runner.ocr.read_text", return_value="Торговая точка \"X\" отправлена на модерацию"):
            h = self.h()
            h.handle(group_msg(1, 10, "iltimos yordam bering"))
            h.handle(group_msg(2, 10, "", photo=True))
        q = Message.objects.get(kind="question")
        self.assertEqual(q.message_id, 2)
        self.assertIn("iltimos", q.text)

    def test_new_real_question_after_answered_photo_gets_its_own_answer(self):
        Entry.objects.create(kind=Entry.FAQ, title="Parolni tiklash", answer="Parol: Profil → Parolni tiklash.",
                             questions=["parolni unutdim qanday tiklayman"], status=Entry.APPROVED)
        with mock.patch("support.runner.ocr.read_text", return_value="Торговая точка \"X\" отправлена на модерацию"):
            h = self.h()
            h.handle(group_msg(1, 10, "", photo=True))
            h.handle(group_msg(2, 10, "parolni unutdim qanday tiklayman"))
        self.assertEqual(Message.objects.filter(kind="question").count(), 2)


class IsQuestionTests(FlowBase):
    def test_filler_words_are_not_questions(self):
        for t in ["iltimos yordam bering", "Добавьте пжл", "srochno iltimos", "ko'rib bering iltimos"]:
            self.assertFalse(engine.is_question(t), t)
        for t in ["parolni unutdim", "1C ishlamayapti", "dostup?"]:
            self.assertTrue(engine.is_question(t), t)


class TaskModeApiTests(FlowBase):
    def test_settings_mode_saved(self):
        self.login("admin")
        r = self.call("patch", "support/settings/", {"task_mode": "remind", "task_remind_dm": False, "merge_window": 20})
        self.assertEqual(r.status_code, 200, r.content)
        s = Settings.load()
        self.assertEqual((s.task_mode, s.task_remind_dm, s.merge_window), ("remind", False, 20))


_ = encrypt


class RecheckAndUsageTests(FlowBase):
    def test_unapprove_recent_and_usage_summary(self):
        from zona.models import AIUsage
        e = Entry.objects.create(kind=Entry.FAQ, title="T", answer="a", status=Entry.APPROVED)
        Entry.objects.filter(pk=e.pk).update(approved_at=__import__("django.utils.timezone", fromlist=["now"]).now())
        self.login("editor")
        ids = [x["id"] for x in self.call("get", "support/entries/?status=approved&approved_since=24").json()]
        self.assertIn(e.id, ids)
        self.assertEqual(self.call("post", "support/entries/bulk/", {"ids": [e.id], "action": "review"}).json()["done"], 1)
        self.assertEqual(Entry.objects.get(pk=e.pk).status, Entry.REVIEW)
        AIUsage.objects.create(task="support", provider="G", model="m", ok=False, error="HTTP 503: high demand")
        AIUsage.objects.create(task="support", provider="G", model="m", ok=True, input_tokens=10, output_tokens=5)
        self.login("admin")
        d = self.call("get", "admin/ai/usage/summary/?days=7").json()
        self.assertEqual((d["totals"]["calls"], d["error_kinds"].get("busy")), (2, 1))
        self.assertEqual(d["busy_now"][0]["model"], "m")
        self.assertEqual(sum(x["calls"] for x in d["daily"]), 2)
