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
