"""Vazifa buyrug'i (/vazifa@prbc_bot reply bilan) va PRBC javobini ushlash, tezlik o'lchovi va tahlili."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from zona.models import Department, Member

from . import tasks
from .engine import Decision
from .models import Group, Message, Settings, SupportTask, TgUser
from .runner import Handler
from .tests import group_msg
from .tests_v6 import FlowBase


class CommandModeTests(FlowBase):
    def setUp(self):
        super().setUp()
        it = Department.objects.create(name="IT c")
        self.said = Member.objects.create(name="Saidabror", role="r", department=it, telegram="StargroupSaid")
        Settings.load()
        Settings.objects.update(tasks_enabled=True, task_departments=[it.id], task_mode="command", task_bot="prbc_bot")
        self.g = Group.objects.create(bot=self.bot, chat_id=-100555, title="VAZIFALAR")
        self.u = TgUser.objects.create(tg_id=5, name="Agent", username="agent1")

    def test_bot_posts_exact_command_as_reply_and_captures_prbc_answer(self):
        q = Message.objects.create(bot=self.bot, group=self.g, chat_id=self.g.chat_id, message_id=40, user=self.u,
                                   text="Perechisleniya   o'tmayapti,\n tekshirib bering")
        t = tasks.maybe_create(q, Decision("", None, 0, "", True, [{"id": self.said.id}]), self.tg)
        sent = self.tg.sent[-1]
        self.assertEqual(sent["text"], "/vazifa@prbc_bot @StargroupSaid Perechisleniya o'tmayapti, tekshirib bering (Agent)")
        self.assertEqual((sent["chat"], sent["reply_to"]), (self.g.chat_id, 40))  # savolga reply — fayllarni PRBC oladi
        self.assertEqual(t.post_id, 1000 + len(self.tg.sent))
        # PRBC botining javobi bot xabari sifatida keladi
        upd = {"update_id": 9, "message": {"message_id": 41, "chat": {"id": self.g.chat_id, "type": "supergroup"},
                                           "from": {"id": 1, "is_bot": True, "username": "prbc_bot"},
                                           "reply_to_message": {"message_id": t.post_id}, "text": "✅ TASK-3091 vazifasi yaratildi."}}
        self.h().handle(upd)
        t.refresh_from_db()
        self.assertEqual((t.status, t.reply), ("sent", "✅ TASK-3091 vazifasi yaratildi."))
        self.assertEqual(Message.objects.filter(kind="question").count(), 1)  # bot xabari savol bo'lmadi

    def test_prbc_error_is_marked_failed(self):
        q = Message.objects.create(bot=self.bot, group=self.g, chat_id=self.g.chat_id, message_id=50, user=self.u, text="1C ishlamayapti")
        t = tasks.maybe_create(q, Decision("", None, 0, "", True, [{"id": self.said.id}]), self.tg)
        tasks.capture_reply({"chat": {"id": self.g.chat_id}, "from": {"username": "prbc_bot", "is_bot": True},
                             "reply_to_message": {"message_id": t.post_id}, "text": "❌ Foydalanuvchi bog'lanmagan"})
        t.refresh_from_db()
        self.assertEqual(t.status, SupportTask.FAILED)

    def test_other_bots_ignored(self):
        upd = {"update_id": 1, "message": {"message_id": 2, "chat": {"id": -100555, "type": "supergroup"},
                                           "from": {"id": 3, "is_bot": True, "username": "spam_bot"}, "text": "1C ishlamayapti bugun"}}
        self.h().handle(upd)
        self.assertEqual(Message.objects.count(), 0)


class SpeedTests(FlowBase):
    def test_timing_recorded_and_speed_endpoint(self):
        from unittest import mock
        with mock.patch("support.runner.ocr.read_text", return_value="Торговая точка \"X\" отправлена на модерацию"):
            self.h().handle(group_msg(1, 10, "Nuqta отправлена на модерацию, qachon tasdiqlanadi?"))
        q = Message.objects.get(kind="question")
        self.assertIn("work", q.timing)
        self.assertIn("decide", q.timing)
        self.login("viewer")
        d = self.call("get", "support/analytics/speed/?days=7").json()
        self.assertEqual(d["answered"], 1)
        self.assertEqual(sum(b["n"] for b in d["buckets"]), 1)
        self.assertEqual(len(d["by_hour"]), 24)

    def test_waiting_questions_do_not_block_workers(self):
        """Rasm kutilayotgan (taymer) savol bo'lsa ham, worker bo'sh — boshqa savol darhol qayta ishlanadi."""
        pool = ThreadPoolExecutor(max_workers=1)
        h = Handler(self.bot, self.tg, executor=pool)
        started = threading.Event()

        def spy(self_, *a, **k):  # rasmli savol 3.5 s kutadi — 2 s ichidagi chaqiruv faqat matnli savolniki
            started.set()
        from unittest import mock
        with mock.patch.object(Handler, "_process_async", spy), mock.patch.object(Handler, "_submit", lambda *a, **k: None),                 mock.patch("support.runner.close_old_connections"):
            h.handle(group_msg(1, 10, "", photo=True))       # izoh kutiladi (taymer, 3.5 s)
            t0 = time.time()
            h.handle(group_msg(2, 11, "Parolni qanday tiklayman, esimdan chiqdi"))  # darhol ishlanishi kerak
            self.assertTrue(started.wait(2))
            self.assertLess(time.time() - t0, 2)
        pool.shutdown(wait=True)
