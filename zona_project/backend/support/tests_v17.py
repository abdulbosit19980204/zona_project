"""Uzilishlarga chidamlilik: kechikkan animatsiya kadri javobni bosib ketmaydi; qayta ishga tushganda chala savol davom etadi."""
import threading
import time

from .models import MODE_LIVE, Group, Message, Settings, TgUser
from .runner import BotWorker, Progress
from .tests import FakeClient
from .tests_v6 import FlowBase


class SlowFrames(FakeClient):
    """Animatsiya kadri tarmoqda sekin ketadi (yakuniy javob kelgan paytda hali yo'lda)."""

    def __init__(self):
        super().__init__()
        self.frame_started = threading.Event()

    def edit_text(self, chat_id, message_id, text, buttons=None, html=True, quiet=False):
        if quiet:
            self.frame_started.set()
            time.sleep(1.0)
        return super().edit_text(chat_id, message_id, text, buttons=buttons, html=html, quiet=quiet)


class InlineExecutor:
    def submit(self, fn, *a, **k):
        return fn(*a, **k)


class ProgressOrderTests(FlowBase):
    def test_late_frame_never_overwrites_answer(self):
        tg = SlowFrames()
        q = Message(chat_id=-100, message_id=5, lang="ru")
        pg = Progress(tg, q, True, every=0.01)
        pg.begin()
        self.assertTrue(tg.frame_started.wait(2))  # kadr yo'lda
        pg.finish("ANSWER")
        time.sleep(1.2)
        self.assertEqual(tg.edits[-1]["text"], "ANSWER")
        self.assertEqual(tg.sent[0]["text"], "ANSWER")


class ResumeTests(FlowBase):
    def test_unfinished_question_is_resumed_in_same_placeholder(self):
        Settings.load()
        g = Group.objects.create(bot=self.bot, chat_id=-100, title="G", mode=MODE_LIVE)
        u = TgUser.objects.create(tg_id=10, name="Ali")
        q = Message.objects.create(bot=self.bot, group=g, chat_id=-100, message_id=7, user=u, source="live",
                                   kind=Message.QUESTION, text="Nuqta отправлена на модерацию, qachon tasdiqlanadi?",
                                   timing={"ph": 1001})
        self.tg.sent.append({"chat": -100, "text": "🕐 …", "reply_to": 7, "buttons": None})  # uzilgan oraliq xabar
        Message.objects.create(bot=self.bot, group=g, chat_id=-100, message_id=8, user=u, source="live",
                               kind=Message.QUESTION, text="eski", status=Message.ANSWERED, stage="faq")
        w = BotWorker(self.bot.id, "1:x")
        w._resume(self.tg, InlineExecutor())
        q.refresh_from_db()
        self.assertEqual(q.status, Message.ANSWERED)
        self.assertEqual(q.bot_reply_id, 1001)  # yangi xabar emas — o'sha xabar javobga aylandi
        self.assertNotIn("🕐", self.tg.sent[0]["text"])
        self.assertEqual(len([x for x in self.tg.sent if x["reply_to"] == 8]), 0)  # javob berilgani qayta ishlanmaydi


class TagPeopleTests(FlowBase):
    def test_named_responsible_is_tagged_once(self):
        from zona.models import Department, Member

        from . import engine
        it = Department.objects.create(name="IT t")
        Member.objects.create(name="Saidabror", role="r", department=it, telegram="StargroupSaid")
        Member.objects.create(name="Supervayzerlar", role="r", department=it, telegram="sv_team", is_team=True)
        out = engine.tag_people("Этот вопрос решает Saidabror — Saidabror ответит.\nЕсли нет ответа: Supervayzerlar")
        self.assertEqual(out.count("@StargroupSaid"), 1)
        self.assertIn("Saidabror (@StargroupSaid)", out)
        self.assertNotIn("@sv_team", out)
        self.assertEqual(engine.tag_people(out), out)  # qayta belgilanmaydi


class StaffListTests(FlowBase):
    def test_recognized_staff_without_answers_listed(self):
        from zona.models import Department, Member

        from . import engine
        it = Department.objects.create(name="IT s")
        team = Member.objects.create(name="Pro-target", role="r", department=it, is_team=True, level="EXT")
        team.contacts.create(name="Eldar", telegram_id=555)
        u = engine.identify(555, "", "Eldar")  # username yo'q — Telegram ID bo'yicha taniladi
        self.assertTrue(u.is_staff)
        self.login("viewer")
        names = [s["name"] for s in self.call("get", "support/analytics/?days=30").json()["staff"]]
        self.assertIn("Eldar", names)
