"""Guruh tarixi: sana oralig'i, to'liq o'qish (cheklovsiz), joyidan davom etish, tungi rejim va rejalashtirish,
suhbat sifatida o'rganish, skrinshotdagi asosiy (xato) xabar."""
import datetime as dt
from datetime import timedelta
from unittest import mock

from django.utils import timezone as tz

from zona.crypto import encrypt
from zona.models import Department, Member

from . import history, ocr, resolution
from .models import Entry, Group, HistoryJob, Message, Settings
from .tests_controls import ControlsBase, fake_stream

UTC = dt.timezone.utc
AGENT = {"id": 10, "username": "agent1", "first_name": "Agent", "last_name": "", "is_bot": False}
STAFF = {"id": 77, "username": "test_op", "first_name": "Test", "last_name": "", "is_bot": False}
OCR_ERR = ("15:06 7 156 22\nPRBC v i\nНовый контрагент\nДанные контрагента не получены. Сохранение\n"
           "отменено; попробуйте ещё раз.\nВизиты Каталог Задачи Корзина Профиль")


def item(mid, when, text, who=AGENT, reply_to=None, photo=None, **kw):
    return {"message_id": mid, "_date": when, "text": text, "from": who, "reply_to": reply_to, "photo": photo, **kw}


class HistBase(ControlsBase):
    def setUp(self):
        super().setUp()
        self.group = Group.objects.create(bot=self.bot, chat_id=-1001234567890, title="Support")
        s = Settings.load()
        s.api_id, s.api_hash_enc, s.mtproto_session_enc = "1", encrypt("h"), encrypt("sess")
        s.thread_window = 15
        s.save()
        it = Department.objects.create(name="IT h")
        Member.objects.create(name="Test Xodim", role="r", department=it, telegram="test_op")

    def run_job(self, job, items):
        with mock.patch.object(history, "stream", fake_stream(items)), \
             mock.patch("support.history.asyncio.run", side_effect=lambda r: r), \
             mock.patch("support.runner.ocr.read_text", return_value=OCR_ERR):
            return history.run_job(job.id)


class ConversationHistoryTests(HistBase):
    def test_follow_ups_are_one_question_and_staff_answer_learns_whole_conversation(self):
        t0 = tz.now() - timedelta(days=3)
        items = [
            item(1, t0, "Do'konning lokatsiyasi xaritada noto'g'ri ko'rsatilyapti"),
            item(2, t0 + timedelta(minutes=1), "", location={"latitude": 41.3, "longitude": 69.2}),
            item(3, t0 + timedelta(minutes=2), "", photo=b"img"),
            item(4, t0 + timedelta(minutes=3), "eski manzil Chilonzor 5 kvartal turibdi"),
            item(5, t0 + timedelta(minutes=8), "Manzilni kartochkada qayta saqlab, sinxronlang — yangilanadi",
                 who=STAFF, reply_to=1),
        ]
        job = HistoryJob.objects.create(group=self.group, days=7)
        stats = self.run_job(job, items)
        self.assertEqual(Message.objects.filter(kind=Message.QUESTION).count(), 1)  # bitta mavzu — bitta savol
        q = Message.objects.get(kind=Message.QUESTION)
        infos = Message.objects.filter(kind=Message.INFO, question=q).order_by("message_id")
        self.assertEqual([m.message_id for m in infos], [2, 3, 4])  # hech bir xabar tashlanmadi
        self.assertTrue(all(m.created_at < tz.now() - timedelta(days=2) for m in infos))  # Telegram vaqti bilan
        self.assertIn("Chilonzor", q.text)  # davom matni savolga qo'shildi
        self.assertIn("Данные контрагента не получены", q.ocr_text)  # qo'shimcha rasm ham o'qildi
        e = Entry.objects.get(source="history")
        self.assertIn("Chilonzor", " ".join(e.questions))
        self.assertEqual((q.status, stats["processed"]), (Message.ANSWERED, 5))


class HistoryAiQuotaTests(HistBase):
    def test_history_does_not_spend_ai(self):
        Settings.objects.update(ai_enabled=True)
        t0 = tz.now() - timedelta(days=2)
        job = HistoryJob.objects.create(group=self.group, days=7)
        with mock.patch("support.engine.ai_answer") as ai:
            self.run_job(job, [item(1, t0, "Kassa apparati chek chiqarmayapti nima qilish kerak")])
        ai.assert_not_called()  # AI limiti jonli guruhlar uchun qoladi
        self.assertEqual(Message.objects.filter(kind=Message.QUESTION).count(), 1)


class ResumeTests(HistBase):
    def items(self, n=120):
        t0 = tz.now() - timedelta(days=5)
        return [item(i, t0 + timedelta(hours=i), f"Savol {i}: zakaz {i} raqamli buyurtma o'tmayapti nima qilay")
                for i in range(1, n + 1)]

    def test_cursor_saved_and_restart_continues_without_repeating(self):
        job = HistoryJob.objects.create(group=self.group, days=10)
        items = self.items()
        calls = {"n": 0}

        def stop_after_first_batch(*a, **k):  # 1-50 talikdan keyin tun, 2-sidan keyin — tong
            calls["n"] += 1
            return calls["n"] <= 1
        job.night_only = True
        job.save()
        with mock.patch.object(history, "is_night", side_effect=stop_after_first_batch):
            self.run_job(job, items)
        job.refresh_from_db()
        # tungi oyna tugadi — vazifa navbatga qaytdi, keyingi tun shu joydan davom etadi
        self.assertEqual((job.status, job.cursor), (HistoryJob.QUEUED, 100))
        self.assertIsNotNone(job.run_after)
        self.assertIn("tungi", job.progress["paused"])
        n_after_first = Message.objects.filter(kind=Message.QUESTION).count()
        with mock.patch.object(history, "is_night", return_value=True):
            stats = self.run_job(job, items)
        job.refresh_from_db()
        self.assertEqual(job.status, HistoryJob.DONE)
        self.assertEqual(stats["messages"], 120)
        self.assertGreater(Message.objects.filter(kind=Message.QUESTION).count(), n_after_first)

    def test_already_learned_messages_are_skipped(self):
        job = HistoryJob.objects.create(group=self.group, days=10)
        self.run_job(job, self.items(10))
        before = Message.objects.count()
        job2 = HistoryJob.objects.create(group=self.group, days=10)
        stats = self.run_job(job2, self.items(10))
        self.assertEqual(Message.objects.count(), before)
        self.assertGreaterEqual(stats["skipped"], 1)

    def test_cancel_stops_after_current_batch(self):
        job = HistoryJob.objects.create(group=self.group, days=10)
        items = self.items(120)

        def go(session, api_id, api_hash, chat_id, start, end, cursor, photos, hooks):
            hooks["process"](items[:50], 0)
            HistoryJob.objects.filter(pk=job.pk).update(status=HistoryJob.CANCELED)  # paneldan "bekor qilish"
            hooks["process"](items[50:100], 0)
            hooks["process"](items[100:], 0)
        with mock.patch.object(history, "stream", go), \
             mock.patch("support.history.asyncio.run", side_effect=lambda r: r):
            history.run_job(job.id)
        job.refresh_from_db()
        self.assertEqual((job.status, job.cursor), (HistoryJob.CANCELED, 100))


class ScheduleTests(HistBase):
    def test_next_job_respects_schedule_and_night_window(self):
        s = Settings.load()
        day = dt.datetime(2026, 11, 20, 7, 0, tzinfo=UTC)     # Toshkentda 12:00
        night = dt.datetime(2026, 11, 20, 18, 30, tzinfo=UTC)  # Toshkentda 23:30
        self.assertFalse(history.is_night(day, s))
        self.assertTrue(history.is_night(night, s))
        j_night = HistoryJob.objects.create(group=self.group, night_only=True)
        g2 = Group.objects.create(bot=self.bot, chat_id=-1002, title="G2")
        j_later = HistoryJob.objects.create(group=g2, run_after=day + timedelta(hours=3))
        self.assertIsNone(history.next_job(day))
        self.assertEqual(history.next_job(night), j_night)
        HistoryJob.objects.filter(pk=j_night.pk).update(status=HistoryJob.DONE)
        self.assertEqual(history.next_job(day + timedelta(hours=4)), j_later)
        start = history.next_night_start(day, s)
        self.assertEqual((start.hour, start.date()), (22, dt.date(2026, 11, 20)))

    def test_api_all_groups_date_range_and_night_schedule(self):
        Group.objects.create(bot=self.bot, chat_id=-1003, title="G3")
        self.login("admin")
        r = self.call("post", "support/history/", {"groups": "all", "date_from": "2026-01-01", "date_to": "2026-03-31",
                                                   "schedule": "night"})
        self.assertEqual(r.status_code, 200, r.content)
        jobs = list(HistoryJob.objects.all())
        self.assertEqual(len(jobs), 2)
        j = jobs[0]
        self.assertTrue(j.night_only)
        self.assertEqual((j.date_from.astimezone(history.TZ).date(), (j.date_to - timedelta(seconds=1)).astimezone(history.TZ).date()),
                         (dt.date(2026, 1, 1), dt.date(2026, 3, 31)))
        self.assertEqual(self.call("post", "support/history/", {"groups": "all"}).status_code, 400)  # takror emas
        r = self.call("post", f"support/history/{j.id}/", {"action": "cancel"})
        self.assertEqual(r.status_code, 200)
        j.refresh_from_db()
        self.assertEqual(j.status, HistoryJob.CANCELED)
        self.call("post", f"support/history/{j.id}/", {"action": "resume"})
        j.refresh_from_db()
        self.assertEqual(j.status, HistoryJob.QUEUED)
        bad = self.call("post", "support/history/", {"groups": [j.group_id], "date_from": "2026-05-01", "date_to": "2026-04-01"})
        self.assertEqual(bad.status_code, 400)

    def test_date_range_is_used_by_job(self):
        job = HistoryJob.objects.create(group=self.group, date_from=dt.datetime(2026, 1, 1, tzinfo=UTC),
                                        date_to=dt.datetime(2026, 2, 1, tzinfo=UTC))
        seen = {}

        def go(session, api_id, api_hash, chat_id, start, end, cursor, photos, hooks):
            seen.update(start=start, end=end)
        with mock.patch.object(history, "stream", go), mock.patch("support.history.asyncio.run", side_effect=lambda r: r):
            history.run_job(job.id)
        self.assertEqual((seen["start"].month, seen["end"].month), (1, 2))


class ScreenshotMessageTests(ControlsBase):
    def test_main_message_skips_status_bar_and_menu(self):
        self.assertEqual(ocr.main_message(OCR_ERR), "Данные контрагента не получены. Сохранение отменено; попробуйте ещё раз.")
        self.assertEqual(ocr.main_message("12:01 ull 40%\nInactive user account\nПопробовать снова"),
                         "Inactive user account Попробовать снова")
        self.assertEqual(ocr.main_message(""), "")

    def test_problem_uses_screenshot_message(self):
        q = Message(text="", ocr_text=OCR_ERR, photo_file_id="x", kind=Message.QUESTION)
        self.assertIn("Данные контрагента не получены", resolution.problem_of(q))
