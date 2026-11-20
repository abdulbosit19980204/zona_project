"""Vazifa sarlavhasi va filtrlari, PRBC javob bermasa — ko'rsatma; rasmlardan shart chiqarish, tinish belgilariga chidamli shart."""
from django.utils import timezone

from zona.models import Department, Member

from . import engine, mining, tasks
from .engine import Decision
from .models import Entry, Group, Media, Message, Settings, SupportTask, TgUser
from .tests_v6 import FlowBase


class TaskQualityTests(FlowBase):
    def setUp(self):
        super().setUp()
        it = Department.objects.create(name="IT q")
        self.said = Member.objects.create(name="Saidabror", role="r", department=it, telegram="StargroupSaid")
        Settings.load()
        Settings.objects.update(tasks_enabled=True, task_departments=[it.id], task_mode="command", task_bot="prbc_bot")
        self.g = Group.objects.create(bot=self.bot, chat_id=-100777, title="G")
        self.u = TgUser.objects.create(tg_id=5, name="Agent Ali", username="ali")

    def q(self, mid, text="", ocr="", photo=""):
        return Message.objects.create(bot=self.bot, group=self.g, chat_id=self.g.chat_id, message_id=mid, user=self.u,
                                      text=text, ocr_text=ocr, photo_file_id=photo)

    def test_title_never_raw_ocr(self):
        e = Entry.objects.create(kind=Entry.TEMPLATE, title="Perechisleniya yoqish", answer="a", status=Entry.APPROVED)
        q = self.q(1, "", "= кассир. ago ва a в UZ-00012345", photo="ph")
        self.assertEqual(tasks.problem_text(q, e.title, e), "Perechisleniya yoqish (UZ-00012345, Agent Ali)")
        q2 = self.q(2, "", "= кассир. ago ва", photo="ph")
        self.assertEqual(tasks.problem_text(q2, "x"), "Rasmli savol (Agent Ali)")
        q3 = self.q(3, "/vazifa @StargroupSaid zakaz 1C ga o'tmayapti tekshiring")
        self.assertTrue(tasks.problem_text(q3, "x").startswith("zakaz 1C ga o'tmayapti tekshiring"))

    def test_chatter_creates_no_task_and_commands_are_not_questions(self):
        self.assertFalse(tasks.decide_task(self.q(4, "ok rahmat"), Decision("", None, 0, "", True, [{"id": self.said.id}]))[0])
        self.assertTrue(tasks.decide_task(self.q(5, "kassa apparati chek chiqarmayapti"),
                                          Decision("", None, 0, "", True, [{"id": self.said.id}]))[0])
        self.assertFalse(engine.is_question("/vazifa @StargroupSaid kassani tekshiring"))

    def test_unanswered_command_becomes_instruction(self):
        q = self.q(6, "kassa apparati chek chiqarmayapti")
        t = tasks.maybe_create(q, Decision("", None, 0, "", True, [{"id": self.said.id}]), self.tg)
        SupportTask.objects.filter(pk=t.pk).update(sent_at=timezone.now() - timezone.timedelta(minutes=5))
        tasks.check_unanswered(self.tg)
        t.refresh_from_db()
        self.assertEqual(t.status, SupportTask.REMINDED)
        edit = self.tg.edits[-1]
        self.assertEqual(edit["id"], t.post_id)
        self.assertIn("<code>/vazifa kassa apparati chek chiqarmayapti", edit["text"])
        self.assertIn("@StargroupSaid", edit["text"])


class MiningTests(FlowBase):
    def test_mines_distinctive_phrases_and_skips_shared_ones(self):
        a = Entry.objects.create(kind=Entry.TEMPLATE, title="ProTarget: «Inactive user account»", answer="x", status=Entry.APPROVED)
        b = Entry.objects.create(kind=Entry.TEMPLATE, title="ProTarget: «User already has an active visit»", answer="y", status=Entry.APPROVED)
        for i, txt in enumerate(["Визиты Подключения Inactive user account Попробовать снова", "Визиты Inactive user account Попробовать снова 14.11"]):
            Media.objects.create(kind=Media.PHOTO, path=f"a{i}", label=a, ocr_text=txt)
        Media.objects.create(kind=Media.PHOTO, path="b0", label=b, ocr_text="Визиты Подключения User already has an active visit Начать визит")
        rep = {r["entry"]: r for r in mining.mine([a.id, b.id], apply=True)}
        a.refresh_from_db()
        self.assertIn("inactive user account", " | ".join(a.triggers))
        self.assertFalse(any("vizity podklyucheniya" in t for t in a.triggers))  # ikkala ekranda bor — xos emas
        self.assertTrue(rep[b.id]["added"])
        # endi rasm tanilmasa ham OCR matni bo'yicha shablon topiladi
        d = engine.decide("Визиты\nInactive user account!\nПопробовать снова")
        self.assertEqual(d.entry, a)

    def test_trigger_tolerates_punctuation(self):
        e = Entry.objects.create(kind=Entry.TEMPLATE, title="INN", answer="z", status=Entry.APPROVED,
                                 triggers=["inn pinfl uje est v 1s"])
        found, _f, _c = engine.match_template("Этот ИНН/ПИНФЛ уже есть в 1С как контрагент", [e])
        self.assertEqual(found, e)
