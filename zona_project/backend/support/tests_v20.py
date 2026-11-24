"""Savol yakuni: "rahmat" — 👍 va yopiladi, "не помогло" — qayta xodimga, "hal bo'ldimi?" so'rovi, muammo jurnali, tahlil."""
import datetime as dt
from unittest import mock

from django.utils import timezone

from zona.models import Department, Member

from . import resolution
from .models import Group, Message, Settings, SupportTask, TgUser
from .tests import group_msg
from .tests_v6 import FlowBase

UTC = dt.timezone.utc
NOON = dt.datetime(2026, 11, 20, 7, 0, tzinfo=UTC)  # Toshkentda 12:00


def cb(uid, data, n=1):
    return {"update_id": 900 + n, "callback_query": {"id": f"c{n}", "data": data, "from": {"id": uid},
                                                     "message": {"message_id": 1, "chat": {"id": -100}}}}


class FeedbackKindTests(FlowBase):
    def test_words(self):
        for t in ["Rahmat", "raxmat aka", "Спасибо, получилось", "готово", "boldi rahmat", "ishladi 👍", "Thanks"]:
            self.assertEqual(resolution.feedback_kind(t), "yes", t)
        for t in ["не помогло", "ishlamadi", "hali ham chiqmayapti", "всё ещё не работает"]:
            self.assertEqual(resolution.feedback_kind(t), "no", t)
        for t in ["Rahmat, lekin yana bitta savol: zakaz qanday o'chiriladi?", "PRBC da klient qo'shish chiqmayapti nima qilay",
                  "Здравствуйте", ""]:
            self.assertEqual(resolution.feedback_kind(t), "", t)


class ThanksTests(FlowBase):
    def setUp(self):
        super().setUp()
        self.bot.admin_chat_id = 555
        self.bot.save()

    def ask(self):
        self.h().handle(group_msg(40, 1, "Nuqta отправлена на модерацию"))
        q = Message.objects.get(message_id=40)
        self.assertEqual(q.status, Message.ANSWERED)
        return q

    def test_thanks_without_reply_closes_question_and_likes(self):
        q = self.ask()
        self.assertTrue(q.problem)  # har bir savolning muammosi yoziladi
        self.h().handle(group_msg(41, 1, "Rahmat, boldi"))
        q.refresh_from_db()
        self.assertEqual((q.resolution, q.resolved_by, q.feedback), ("yes", "savol egasi", 1))
        self.assertIn((-100, 41, "👍"), self.tg.reactions)
        fb = Message.objects.get(message_id=41)
        self.assertEqual((fb.kind, fb.question_id), (Message.FEEDBACK, q.pk))  # javob zanjirida saqlanadi

    def test_thanks_from_someone_else_is_ignored(self):
        q = self.ask()
        self.h().handle(group_msg(42, 2, "Rahmat"))
        q.refresh_from_db()
        self.assertEqual(q.resolution, "")  # boshqa odamning "rahmat"i savolni yopmaydi
        self.assertIn((-100, 42, "👍"), self.tg.reactions)  # lekin 👍 — hammaga (ko'rildi)

    def test_not_helped_reopens_and_notifies(self):
        q = self.ask()
        self.h().handle(group_msg(43, 1, "не помогло", reply_to=q.bot_reply_id))
        q.refresh_from_db()
        self.assertEqual((q.resolution, q.status), ("no", Message.ESCALATED))
        self.assertTrue(any(m["chat"] == 555 and "Hal bo'lmadi" in m["text"] for m in self.tg.sent))

    def test_not_helped_without_reply_is_a_new_message_not_feedback(self):
        q = self.ask()
        self.h().handle(group_msg(44, 1, "не помогло"))
        q.refresh_from_db()
        self.assertEqual(q.resolution, "")

    def test_thumbs_up_marks_resolved(self):
        q = self.ask()
        self.h().handle(cb(1, f"fb:{q.id}:1"))
        q.refresh_from_db()
        self.assertEqual(q.resolution, "yes")


class ConfirmTests(FlowBase):
    def setUp(self):
        super().setUp()
        Settings.load()
        Settings.objects.update(confirm_resolution=True, confirm_after=10)
        self.g = Group.objects.create(bot=self.bot, chat_id=-100, title="ROP")
        self.u = TgUser.objects.create(tg_id=1, name="Agent", username="agent1")
        it = Department.objects.create(name="IT c")
        self.staff = TgUser.objects.create(tg_id=2, name="S", member=Member.objects.create(name="S", role="r", department=it))

    def q(self, mid, **kw):
        q = Message.objects.create(bot=self.bot, group=self.g, chat_id=-100, message_id=mid, user=self.u, source="live",
                                   kind=Message.QUESTION, text="Kassa chek chiqarmayapti", **kw)
        Message.objects.filter(pk=q.pk).update(created_at=NOON - dt.timedelta(hours=3))
        return q

    def test_asks_after_staff_answer_and_buttons_close(self):
        q = self.q(5, status=Message.ANSWERED, answered_by="S", answered_at=NOON - dt.timedelta(minutes=15))
        fresh = self.q(6, status=Message.ANSWERED, answered_by="S", answered_at=NOON - dt.timedelta(minutes=3))
        botq = self.q(7, status=Message.ANSWERED, answered_by="bot", answered_at=NOON - dt.timedelta(minutes=30))
        self.assertEqual(resolution.ask_pending(self.tg, now=NOON), 1)
        q.refresh_from_db()
        self.assertEqual(q.resolution, "asked")
        prompt = self.tg.sent[-1]
        self.assertEqual(prompt["reply_to"], 5)
        self.assertIn("@agent1", prompt["text"])
        self.assertEqual(prompt["buttons"][0][0]["callback_data"], f"rs:{q.id}:1")
        for x in (fresh, botq):
            x.refresh_from_db()
            self.assertEqual(x.resolution, "")  # hali erta / bot javobida 👍/👎 bor
        self.assertEqual(resolution.ask_pending(self.tg, now=NOON), 0)  # qayta so'ralmaydi
        self.h().handle(cb(2, f"rs:{q.id}:1", 1))  # boshqa odam bosa olmaydi
        q.refresh_from_db()
        self.assertEqual(q.resolution, "asked")
        self.h().handle(cb(1, f"rs:{q.id}:1", 2))
        q.refresh_from_db()
        self.assertEqual(q.resolution, "yes")
        self.assertEqual(self.tg.edits[-1]["id"], q.confirm_msg_id)
        self.assertIn("yopildi", self.tg.edits[-1]["text"])

    def test_task_question_is_asked_later_and_never_at_night(self):
        q = self.q(8, status=Message.ESCALATED)
        t = SupportTask.objects.create(message=q, assignee="x", title="kassa", status=SupportTask.REMINDED)
        SupportTask.objects.filter(pk=t.pk).update(created_at=NOON - dt.timedelta(hours=1))
        self.assertEqual(resolution.ask_pending(self.tg, now=NOON), 0)  # vazifa yangi
        SupportTask.objects.filter(pk=t.pk).update(created_at=NOON - dt.timedelta(hours=2, minutes=5))
        night = dt.datetime(2026, 11, 20, 18, 0, tzinfo=UTC)  # Toshkentda 23:00
        self.assertEqual(resolution.ask_pending(self.tg, now=night), 0)
        self.assertEqual(resolution.ask_pending(self.tg, now=NOON), 1)

    def test_reply_to_prompt_with_thanks(self):
        q = self.q(9, status=Message.ANSWERED, answered_by="S", answered_at=NOON - dt.timedelta(minutes=15))
        resolution.ask_pending(self.tg, now=NOON)
        q.refresh_from_db()
        self.h().handle(group_msg(50, 1, "Ha, rahmat", reply_to=q.confirm_msg_id))
        q.refresh_from_db()
        self.assertEqual(q.resolution, "yes")

    def test_staff_question_is_not_asked(self):
        q = Message.objects.create(bot=self.bot, group=self.g, chat_id=-100, message_id=11, user=self.staff, source="live",
                                   kind=Message.QUESTION, text="x", status=Message.ANSWERED, answered_by="S",
                                   answered_at=NOON - dt.timedelta(minutes=30))
        Message.objects.filter(pk=q.pk).update(created_at=NOON - dt.timedelta(hours=1))
        self.assertEqual(resolution.ask_pending(self.tg, now=NOON), 0)


class AnalyticsResolutionTests(FlowBase):
    def test_summary(self):
        from .views import _resolution
        g = Group.objects.create(bot=self.bot, chat_id=-1, title="G")
        for i, r in enumerate(["yes", "yes", "no", "asked", "", ""]):
            Message.objects.create(bot=self.bot, group=g, chat_id=-1, message_id=i + 1, kind=Message.QUESTION, text="x",
                                   status=Message.ANSWERED, resolution=r, resolved_by="savol egasi" if r == "yes" else "")
        d = _resolution(Message.objects.filter(kind=Message.QUESTION))
        self.assertEqual((d["yes"], d["no"], d["asked"], d["unknown"], d["rate"]), (2, 1, 1, 2, 67))

    def test_panel_resolve(self):
        g = Group.objects.create(bot=self.bot, chat_id=-1, title="G")
        q = Message.objects.create(bot=self.bot, group=g, chat_id=-1, message_id=1, kind=Message.QUESTION, text="x",
                                   status=Message.ANSWERED)
        with mock.patch.object(timezone, "now", return_value=NOON):
            resolution.mark(q, "no", "Panel")
        q.refresh_from_db()
        self.assertEqual((q.resolution, q.status, q.resolved_by), ("no", Message.ESCALATED, "Panel"))
