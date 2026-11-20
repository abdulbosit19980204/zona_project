"""Tasdiqlashda savol fayllari; javob emas xabarlar o'rganilmaydi; sekin tarmoqda javob oxirigacha yetadi;
PRBC javob bermasa — guruhda g'alati buyruq qolmaydi."""
import threading
import time

from django.utils import timezone

from zona.models import Department, Member

from . import engine, tasks
from .engine import Decision
from .models import Entry, Group, Media, Message, Settings, SupportTask, TgUser
from .runner import Progress, learn
from .telegram import TelegramError
from .tests import FakeClient, group_msg
from .tests_v6 import FlowBase


class NotAnAnswerTests(FlowBase):
    def test_handoffs_and_rewrite_requests_are_not_answers(self):
        for t in ["@TEST_OPERATOR", "Vali \nПоможите", "@test_lead Vali", "Правильно напишите вопрос",
                  "Подробнее опишите проблему", "Tekwiring", "@test_said"]:
            self.assertTrue(engine.not_an_answer(t), t)
        for t in ["qayta tekshiring botni restart qilib", "Klientni qayta ulang, keyin sinxron qiling",
                  "Проверил, у всех агентов время визита корректно отображается", "Напишите оператору"]:
            self.assertFalse(engine.not_an_answer(t), t)
        # "Готово" — savol hal qilindi (javob), lekin bilim bazasi uchun qayta ishlatiladigan javob emas
        self.assertFalse(engine.is_handoff("Готово"))
        self.assertTrue(engine.not_an_answer("Готово"))
        self.assertTrue(engine.is_handoff("@test_lead Vali"))
        self.assertFalse(engine.is_handoff("Tekwiring"))

    def test_staff_handoff_does_not_close_question_or_create_candidate(self):
        Settings.load()
        Settings.objects.update(learn_from_staff=True)
        Group.objects.create(bot=self.bot, chat_id=-10, title="G")
        it = Department.objects.create(name="IT n")
        m = Member.objects.create(name="Test Xodim", role="r", department=it, telegram="said")
        TgUser.objects.create(tg_id=77, name="Test Xodim", username="said", member=m)
        self.h().handle(group_msg(1, 10, "Rich chay aksiyasi ilovada ko'rinmayapti", chat=-10))
        q = Message.objects.get(message_id=1)
        Message.objects.filter(pk=q.pk).update(status=Message.ESCALATED)
        before = Entry.objects.count()
        reply = group_msg(2, 77, "@TEST_OPERATOR", chat=-10, username="said")
        reply["message"]["reply_to_message"] = {"message_id": 1}
        self.h().handle(reply)
        q.refresh_from_db()
        self.assertEqual(q.status, Message.ESCALATED)  # yo'naltirish — javob emas, savol javob kutadi
        self.assertEqual(Entry.objects.count(), before)


class SourceFilesTests(FlowBase):
    def test_candidate_shows_all_question_files(self):
        g = Group.objects.create(bot=self.bot, chat_id=-11, title="ROP")
        u = TgUser.objects.create(tg_id=5, name="Agent Ali")
        q = Message.objects.create(bot=self.bot, group=g, chat_id=-11, message_id=3, user=u, text="Tovar ilovada ko'rinmayapti",
                                   media_group_id="alb1")
        for i in range(3):  # albomdagi uchta rasm
            Media.objects.create(kind=Media.PHOTO, path=f"p{i}", message=q, name=f"album:{i}")
        info = Message.objects.create(bot=self.bot, group=g, chat_id=-11, message_id=9, user=u, kind=Message.INFO,
                                      question=q, text="mana skrin")
        Media.objects.create(kind=Media.PHOTO, path="extra", message=info)  # aniqlashtirishdan keyin yuborilgan rasm
        Media.objects.create(kind=Media.DOCUMENT, path="doc", message=info, name="hisobot.xlsx")
        e, new = learn(q, "Omborni sinxronlang, keyin ilovani qayta oching", "Test Xodim")
        self.assertTrue(new)
        self.assertEqual(e.sources, [q.pk])
        from .views import EntrySerializer
        src = EntrySerializer(e).data["sources_info"]
        self.assertEqual(len(src), 1)
        self.assertEqual(src[0]["text"], "Tovar ilovada ko'rinmayapti")
        self.assertEqual(src[0]["group"], "ROP")
        self.assertEqual(src[0]["info"], ["mana skrin"])
        self.assertEqual(len(src[0]["media"]), 5)  # 3 ta albom rasmi + qo'shimcha rasm + fayl
        # o'xshash ikkinchi savol shu nomzodga qo'shiladi — manbalar ham
        q2 = Message.objects.create(bot=self.bot, group=g, chat_id=-11, message_id=4, user=u, text="Tovar ilovada ko'rinmayapti")
        e2, new2 = learn(q2, "Omborni sinxronlang", "Test Xodim")
        self.assertFalse(new2)
        self.assertEqual(Entry.objects.get(pk=e.pk).sources, [q.pk, q2.pk])

    def test_non_answer_is_not_learned(self):
        u = TgUser.objects.create(tg_id=6, name="A")
        q = Message.objects.create(bot=self.bot, chat_id=-12, message_id=1, user=u, text="В разделе шоколадные батончики")
        self.assertEqual(learn(q, "Правильно напишите вопрос", "S"), (None, False))


class FlakyEdit(FakeClient):
    """Yakuniy tahrir tarmoqda uziladi (Telegram'ga yetmagan), keyingi urinish o'tadi."""

    def __init__(self, fail_times=1):
        super().__init__()
        self.fail_times = fail_times

    def edit_text(self, chat_id, message_id, text, buttons=None, html=True, quiet=False):
        if not quiet and self.fail_times > 0:
            self.fail_times -= 1
            raise TelegramError("Tarmoq xatosi: The read operation timed out")
        return super().edit_text(chat_id, message_id, text, buttons=buttons, html=html, quiet=quiet)


class SlowNetworkTests(FlowBase):
    def setUp(self):
        super().setUp()
        old = Progress.CONFIRM_AFTER
        Progress.CONFIRM_AFTER = (0.05, 0.1)
        self.addCleanup(setattr, Progress, "CONFIRM_AFTER", old)

    def test_network_error_on_answer_is_retried_not_dropped(self):
        tg = FlakyEdit()
        pg = Progress(tg, Message(chat_id=-100, message_id=5, lang="ru"), True, every=10)
        pg.begin()
        self.assertEqual(pg.finish("ANSWER"), {"message_id": 1001})
        time.sleep(0.4)
        self.assertEqual(tg.sent[0]["text"], "ANSWER")  # oraliq xabar javobga aylandi
        self.assertFalse(getattr(tg, "deleted", []))

    def test_answer_is_sent_anew_when_edits_keep_failing(self):
        tg = FlakyEdit(fail_times=99)
        tg.edit_text = (lambda *a, **k: (_ for _ in ()).throw(TelegramError("Tarmoq xatosi: timed out")))
        pg = Progress(tg, Message(chat_id=-100, message_id=5, lang="ru"), True, every=10)
        pg.begin()
        pg.finish("ANSWER")
        time.sleep(0.5)
        self.assertEqual(tg.sent[-1]["text"], "ANSWER")
        self.assertIn(1001, tg.deleted)  # osilib qolgan oraliq xabar o'chirildi

    def test_confirm_waits_for_frame_in_flight(self):
        tg = FakeClient()
        pg = Progress(tg, Message(chat_id=-100, message_id=5, lang="ru"), True, every=10)
        pg.begin()
        pg._edit_lock.acquire()  # kadr hali yo'lda
        done = threading.Event()

        def finish():
            pg.finish("ANSWER")
            done.set()
        Progress.LOCK_WAIT = 0.1
        self.addCleanup(setattr, Progress, "LOCK_WAIT", 10.0)
        t = threading.Thread(target=finish)
        t.start()
        time.sleep(0.2)
        tg.edit_text(-100, 1001, "FRAME", quiet=True)  # kechikkan kadr javobdan keyin yetib keldi
        pg._edit_lock.release()
        t.join(15)
        time.sleep(0.4)
        self.assertEqual(tg.sent[0]["text"], "ANSWER")


class PrbcSilentTests(FlowBase):
    def setUp(self):
        super().setUp()
        it = Department.objects.create(name="IT s")
        self.said = Member.objects.create(name="Test Xodim", role="r", department=it, telegram="test_said")
        Settings.load()
        Settings.objects.update(tasks_enabled=True, task_departments=[it.id], task_mode="command", task_bot="prbc_bot",
                                task_remind_dm=True, task_remind_group=True)
        self.bot.admin_chat_id = 555
        self.bot.save()
        self.g = Group.objects.create(bot=self.bot, chat_id=-100778, title="G")
        self.u = TgUser.objects.create(tg_id=5, name="Agent Ali", username="ali")

    def q(self, mid, text):
        return Message.objects.create(bot=self.bot, group=self.g, chat_id=self.g.chat_id, message_id=mid, user=self.u, text=text)

    def test_unanswered_command_is_removed_from_group_and_sent_to_admin_chat(self):
        q = self.q(6, "kassa apparati chek chiqarmayapti")
        t = tasks.maybe_create(q, Decision("", None, 0, "", True, [{"id": self.said.id}]), self.tg)
        SupportTask.objects.filter(pk=t.pk).update(sent_at=timezone.now() - timezone.timedelta(minutes=5))
        tasks.check_unanswered(self.tg)
        t.refresh_from_db()
        self.assertIn(t.post_id, self.tg.deleted)  # guruhdagi buyruq o'chirildi
        self.assertEqual(self.tg.sent[-1]["chat"], 555)
        self.assertIn("/vazifa", self.tg.sent[-1]["text"])
        self.assertIn("admin chati", t.reply)

    def test_after_repeated_silence_no_command_is_posted_in_group(self):
        for i in range(3):
            SupportTask.objects.create(message=self.q(20 + i, f"x{i}"), assignee="test_said", title="x", post_id=100 + i,
                                       status=SupportTask.REMINDED, reply="PRBC bot buyrug'iga javob bermadi")
        q = self.q(30, "printer chek chiqarmayapti umuman")
        t = tasks.maybe_create(q, Decision("", None, 0, "", True, [{"id": self.said.id}]), self.tg)
        self.assertEqual(t.status, SupportTask.REMINDED)
        self.assertFalse([m for m in self.tg.sent if m["chat"] == self.g.chat_id])  # ochiq guruhga hech narsa
        self.assertTrue([m for m in self.tg.sent if m["chat"] == 555])


class AnswerLanguageTests(FlowBase):
    def test_ai_is_told_answer_language(self):
        from unittest import mock
        seen = {}

        def fake_run(task, *a):
            seen["message"] = a[3]
            return {"answer": "x", "confidence": 0.9, "needs_human": False, "reason": ""}, {}
        s = Settings.load()
        s.ai_enabled = True
        with mock.patch("zona.ai.service.run", fake_run):
            engine.ai_answer("В разделе шоколадные батончики", "ru", [], None, s)
        self.assertIn("RUS", seen["message"])
