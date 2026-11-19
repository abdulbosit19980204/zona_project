"""PRBC vazifalari (qaror, bitta mavzu — bitta vazifa, navbat), ish yuklamasi tahlili, sozlamalar saqlanishi."""
from unittest import mock

from django.utils import timezone

from zona.crypto import encrypt
from zona.models import Department, Member
from zona.tests import Base

from . import tasks
from .engine import Decision
from .models import Bot, Entry, Group, Message, Settings, SupportTask, TgUser


class TaskTests(Base):
    def setUp(self):
        self.it = Department.objects.create(name="IT test")
        self.sales = Department.objects.create(name="Savdo test")
        self.dev = Member.objects.create(name="Dev", role="dasturchi", department=self.it, telegram="dev_user", level="L1")
        self.seller = Member.objects.create(name="Sotuvchi", role="savdo", department=self.sales, telegram="seller")
        s = Settings.load()
        Settings.objects.filter(pk=s.pk).update(tasks_enabled=True, task_departments=[self.it.id], task_gap=0, task_mode="account")
        self.bot = Bot.objects.create(name="b", token_enc=encrypt("1:x"))
        self.g = Group.objects.create(bot=self.bot, chat_id=-1004410351675, title="VAZIFALAR")
        self.u = TgUser.objects.create(tg_id=5, name="Agent", username="agent1")
        self.entry = Entry.objects.create(kind=Entry.FAQ, title="Dostup ochish", answer="...", status=Entry.APPROVED,
                                          creates_task=True, task_assignee="@it_admin")

    def q(self, mid, text):
        return Message.objects.create(bot=self.bot, group=self.g, chat_id=self.g.chat_id, message_id=mid, user=self.u, text=text)

    def test_entry_flag_creates_task_with_link(self):
        t = tasks.maybe_create(self.q(1, "dostup kerak"), Decision("faq", self.entry, 90, "...", False))
        self.assertEqual((t.assignee, t.status, t.reason), ("it_admin", "queued", "entry"))
        self.assertTrue(t.text.startswith("/vazifa @it_admin Dostup ochish"))
        self.assertIn("https://t.me/c/4410351675/1", t.text)

    def test_one_task_per_topic(self):
        t1 = tasks.maybe_create(self.q(1, "dostup kerak"), Decision("faq", self.entry, 90, "...", False))
        q2 = self.q(2, "dostup hali ochilmadi")
        t2 = tasks.maybe_create(q2, Decision("faq", self.entry, 90, "...", False))
        self.assertEqual(t1.pk, t2.pk)
        self.assertEqual(SupportTask.objects.count(), 1)
        self.assertIn(q2.pk, SupportTask.objects.get().duplicates)

    def test_responsible_department_rule(self):
        it_q = Decision("", None, 0, "", True, [{"id": self.dev.id}])
        sales_q = Decision("", None, 0, "", True, [{"id": self.seller.id}])
        self.assertEqual(tasks.decide_task(self.q(3, "1C ishlamayapti"), it_q)[:2], (True, "dev_user"))
        self.assertFalse(tasks.decide_task(self.q(4, "aksiya qachon"), sales_q)[0])
        answered = Decision("faq", None, 90, "javob", False, [{"id": self.dev.id}])
        self.assertFalse(tasks.decide_task(self.q(5, "x"), answered)[0])  # bot javob bergan oddiy savol — vazifa emas

    def test_disabled_and_non_question(self):
        Settings.objects.update(tasks_enabled=False)
        self.assertFalse(tasks.decide_task(self.q(6, "x"), Decision("faq", self.entry, 90, "", False))[0])
        Settings.objects.update(tasks_enabled=True)
        info = self.q(7, "x")
        info.kind = Message.INFO
        self.assertFalse(tasks.decide_task(info, Decision("faq", self.entry, 90, "", False))[0])

    def test_queue_sends_and_detects_failure(self):
        tasks.maybe_create(self.q(1, "dostup kerak"), Decision("faq", self.entry, 90, "...", False))
        with mock.patch.object(tasks, "send_one", return_value="✅ Vazifa #512 yaratildi"):
            self.assertTrue(tasks.process_queue())
        t = SupportTask.objects.get()
        self.assertEqual((t.status, t.reply), ("sent", "✅ Vazifa #512 yaratildi"))
        t.status = "queued"
        t.save()
        with mock.patch.object(tasks, "send_one", return_value="Foydalanuvchi topilmadi"):
            tasks.process_queue()
        self.assertEqual(SupportTask.objects.get().status, "failed")

    def test_daily_limit(self):
        Settings.objects.update(task_daily_limit=1)
        SupportTask.objects.create(status="sent", sent_at=timezone.now(), text="x")
        tasks.maybe_create(self.q(1, "dostup kerak"), Decision("faq", self.entry, 90, "...", False))
        with mock.patch.object(tasks, "send_one") as send:
            self.assertFalse(tasks.process_queue())
            send.assert_not_called()

    def test_api(self):
        self.login("admin")
        r = self.call("get", "support/tasks/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("departments", r.json())
        t = self.call("post", "support/tasks/test/", {"assignee": "@me"}).json()
        self.assertEqual(t["status"], "queued")
        r = self.call("post", f"support/tasks/{t['id']}/retry/", {"assignee": "other"})
        self.assertTrue(r.json()["text"].startswith("/vazifa @other"))
        self.login("viewer")
        self.assertEqual(self.call("get", "support/tasks/").status_code, 403)


class WorkloadAndSettingsTests(Base):
    def test_workload_shape(self):
        bot = Bot.objects.create(name="b", token_enc=encrypt("1:x"))
        u = TgUser.objects.create(tg_id=9, name="A")
        q = Message.objects.create(bot=bot, chat_id=-1, message_id=1, user=u, text="savol", status=Message.ESCALATED)
        Message.objects.create(bot=bot, chat_id=-1, message_id=2, kind=Message.STAFF, question=q, user=u, text="javob")
        self.login("viewer")
        d = self.call("get", "support/analytics/workload/?days=7").json()
        self.assertEqual((len(d["heatmap"]), len(d["heatmap"][0])), (7, 24))
        self.assertEqual(d["answered_by_human"], 1)
        self.assertEqual(sum(b["n"] for b in d["buckets"]), 1)

    def test_previously_missing_settings_are_saved(self):
        self.login("admin")
        r = self.call("patch", "support/settings/", {"ai_primary": False, "album_window": 30, "task_members": [1]})
        self.assertEqual(r.status_code, 200, r.content)
        s = Settings.load()
        self.assertEqual((s.ai_primary, s.album_window, s.task_members), (False, 30, [1]))
