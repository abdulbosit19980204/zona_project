"""Bot boshqaruvi, aniqlashtirish zanjiri, guruh tarixi va tahlil testlari."""
import os
import tempfile
from datetime import timedelta
from unittest import mock

from django.core.management import call_command
from django.utils import timezone as tz

from zona.crypto import encrypt
from zona.models import Member, TeamContact
from zona.tests import Base

from . import engine
from .models import MODE_COLLECT, MODE_LIVE, Bot, Entry, Group, HistoryJob, Message, Settings
from .runner import Handler
from .tests import OCR_PT, FakeClient, group_msg, visible


class ControlsBase(Base):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        patcher = mock.patch.dict(os.environ, {"ZONA_SUPPORT_MEDIA": media.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.team = Member.objects.create(name="Operatorlar", role="Operator", is_team=True, level="L2")
        self.op = TeamContact.objects.create(member=self.team, name="Saida", telegram="op_saida")
        self.bot = Bot.objects.create(name="S", token_enc=encrypt("1:x"), mode=MODE_LIVE, admin_chat_id=555)
        self.tg = FakeClient()

    def handler(self, **kw):
        self.bot.refresh_from_db()
        return Handler(self.bot, self.tg, **kw)


class ClarifyTests(ControlsBase):
    def test_classifier(self):
        for t in ["STIR raqamini yuboring", "skrin tashlang?", "qaysi klient?", "Пришлите ИНН клиента", "Какой код точки?"]:
            self.assertTrue(engine.is_clarifying(t), t)
        for t in ["Tuzatildi, sinxronlang", "Supervayzer o'tkazadi, unga yozing", "Напишите супервайзеру, он добавит", "Klientni marshrutga qo'shdim, endi chiqadi", "Готово, проверьте",
                  "1C'da Marshrutlar → agentni tanlab → Saqlash"]:
            self.assertFalse(engine.is_clarifying(t), t)

    def test_thread_learns_answer_and_what_to_ask_first(self):
        h = self.handler()
        h.handle(group_msg(1, 10, "Klientim agentda ko'rinmayapti, nima qilay?"))
        n_sent = len(self.tg.sent)
        h.handle(group_msg(2, 77, "STIR raqamini yuboring", "op_saida", reply_to=1))
        self.assertFalse(Entry.objects.filter(source="staff").exists())  # aniqlashtirish javob emas
        self.assertEqual(len(self.tg.sent), n_sent)                      # nomzod ham yuborilmadi
        h.handle(group_msg(3, 10, "STIR 301234567", reply_to=2))
        h.handle(group_msg(4, 77, "Klientni marshrutingizga qo'shdim, sinxronlang", "op_saida", reply_to=3))
        q = Message.objects.get(message_id=1)
        self.assertEqual((q.status, q.answered_by), (Message.ANSWERED, "Saida"))
        kinds = list(q.staff_replies.order_by("message_id").values_list("kind", flat=True))
        self.assertEqual(kinds, [Message.CLARIFY, Message.INFO, Message.STAFF])
        e = Entry.objects.get(source="staff")
        self.assertIn("marshrutingizga", e.answer)
        self.assertIn("STIR", e.ask_first)

    def test_similar_candidates_are_merged(self):
        Settings.load()
        Settings.objects.update(auto_approve_level="off")  # nomzod -> tasdiqlash oqimi (avto-tasdiq alohida tekshiriladi)
        h = self.handler()
        h.handle(group_msg(1, 10, "Klientni boshqa agentga o'tkazish kerak"))
        h.handle(group_msg(2, 77, "Supervayzer o'tkazadi, unga yozing", "op_saida", reply_to=1))
        h.handle(group_msg(3, 11, "klientni boshqa agentga o'tkazish kerak edi"))
        h.handle(group_msg(4, 77, "Supervayzer o'tkazadi", "op_saida", reply_to=3))
        self.assertEqual(Entry.objects.filter(source="staff").count(), 1)
        self.assertEqual(len(Entry.objects.get(source="staff").questions), 2)


class ModeAndToggleTests(ControlsBase):
    def setUp(self):
        super().setUp()
        call_command("support_setup", verbosity=0)
        Entry.objects.update(status=Entry.APPROVED)

    def test_collect_mode_sends_nothing_but_records(self):
        Bot.objects.filter(pk=self.bot.pk).update(mode=MODE_COLLECT)
        h = self.handler()
        h.handle(group_msg(1, 10, "Nuqta отправлена на модерацию, qachon?"))
        h.handle(group_msg(2, 12, "noma'lum murakkab savol bu yerda yozilgan"))
        self.assertEqual(self.tg.sent, [])
        q = Message.objects.get(message_id=1)
        self.assertEqual((q.status, q.stage), (Message.NEW, "template"))
        self.assertTrue(q.answer_text)  # taklif tahlil uchun saqlanadi

    def test_escalation_and_feedback_toggles(self):
        Settings.objects.filter(pk=Settings.load().pk).update(escalation_ack=False, feedback_buttons=False,
                                                               drafts_to_admin=False)
        h = self.handler()
        h.handle(group_msg(1, 10, "noma'lum murakkab savol bu yerda yozilgan"))
        self.assertEqual(visible(self.tg), [])  # na guruhga, na admin chatiga (oraliq xabar o'chirildi)
        h.handle(group_msg(2, 10, "Nuqta отправлена на модерацию, qachon?"))
        self.assertEqual(len(visible(self.tg)), 1)
        self.assertIsNone(visible(self.tg)[0]["buttons"])

    def test_bot_asks_required_info_first_then_answers(self):
        Entry.objects.create(kind=Entry.FAQ, title="Klient agentda ko'rinmayapti", answer="Supervayzer marshrutga qo'shadi.",
                             ask_first="Klient STIR raqami", status=Entry.APPROVED)
        h = self.handler()
        h.handle(group_msg(1, 10, "klient agentda ko'rinmayapti"))
        self.assertIn("STIR", self.tg.sent[-1]["text"])
        q = Message.objects.get(message_id=1)
        self.assertEqual(q.stage, "ask")
        h.handle(group_msg(2, 10, "STIR 301234567", reply_to=q.bot_reply_id))
        self.assertIn("marshrutga", self.tg.sent[-1]["text"])
        q.refresh_from_db()
        self.assertEqual(q.status, Message.ANSWERED)

    def test_settings_api_toggles(self):
        self.login("admin")
        r = self.call("patch", "support/settings/", {"escalation_ack": False, "history_days": 14, "learn_clarifications": False})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["escalation_ack"], r.json()["history_days"]), (False, 14))
        self.assertFalse(r.json()["mtproto_connected"])


class HistoryTests(ControlsBase):
    def setUp(self):
        super().setUp()
        self.group = Group.objects.create(bot=self.bot, chat_id=-1001234567890, title="Support")

    def items(self):
        t0 = tz.now() - timedelta(days=3)
        u = {"id": 10, "username": "agent1", "first_name": "Agent", "last_name": "", "is_bot": False}
        st = {"id": 77, "username": "op_saida", "first_name": "Saida", "last_name": "", "is_bot": False}
        return [
            {"message_id": 1, "_date": t0, "text": "bu nima degani?", "from": u, "reply_to": None, "photo": b"img"},
            {"message_id": 2, "_date": t0 + timedelta(minutes=4), "text": "Qaysi klient?", "from": st, "reply_to": 1, "photo": None},
            {"message_id": 3, "_date": t0 + timedelta(minutes=6), "text": "BRAND-BRO-TRADE", "from": u, "reply_to": 2, "photo": None},
            {"message_id": 4, "_date": t0 + timedelta(minutes=9), "text": "Moderatsiyadan o'tishini kuting, ertaga tasdiqlanadi",
             "from": st, "reply_to": 3, "photo": None},
        ]

    def test_run_job_reads_history_learns_and_sends_nothing(self):
        from . import history
        s = Settings.load()
        s.api_id, s.api_hash_enc, s.mtproto_session_enc = "1", encrypt("h"), encrypt("sess")
        s.save()
        job = HistoryJob.objects.create(group=self.group, days=7)
        with mock.patch.object(history, "_run", return_value=(self.items(), 1)), \
             mock.patch("support.runner.ocr.read_text", return_value=OCR_PT):
            stats = history.run_job(job.id)
        self.assertEqual(self.tg.sent, [])
        q = Message.objects.get(message_id=1, group=self.group)
        self.assertEqual((q.source, q.status, q.stage), ("history", Message.ANSWERED, "staff"))
        self.assertIn("модерацию", q.ocr_text)
        self.assertLess(q.created_at, tz.now() - timedelta(days=2))  # asl sana saqlandi
        e = Entry.objects.get(source="history")
        self.assertIn("Qaysi klient", e.ask_first)
        job.refresh_from_db()
        self.assertEqual((job.status, stats["candidates"], stats["clarifications"]), (HistoryJob.DONE, 1, 1))

    def test_history_api_requires_connected_account(self):
        self.login("admin")
        self.assertEqual(self.call("post", "support/history/", {"group": self.group.id}).status_code, 400)
        s = Settings.load()
        s.mtproto_session_enc = encrypt("sess")
        s.save()
        r = self.call("post", "support/history/", {"group": self.group.id, "days": 10})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()[0]["days"], 10)
        self.assertEqual(self.call("post", "support/history/", {"group": self.group.id}).status_code, 400)  # takror
        self.login("editor")
        self.assertEqual(self.call("get", "support/history/").status_code, 403)

    def test_mtproto_code_flow_api(self):
        from . import history
        self.login("admin")
        with mock.patch.object(history, "send_code") as sc:
            r = self.call("post", "support/mtproto/send-code/", {"phone": "+998901234567", "confirm": True})
        self.assertEqual(r.status_code, 200, r.content)
        sc.assert_called_once_with("+998901234567")
        with mock.patch.object(history, "sign_in", side_effect=history.NeedPassword()):
            r = self.call("post", "support/mtproto/sign-in/", {"code": "12345"})
        self.assertTrue(r.json()["need_password"])


class AnalyticsTests(ControlsBase):
    def test_staff_answers_and_clarifications_are_analyzed(self):
        h = self.handler()
        h.handle(group_msg(1, 10, "Klientim agentda ko'rinmayapti, nima qilay?"))
        h.handle(group_msg(2, 77, "STIR raqamini yuboring", "op_saida", reply_to=1))
        h.handle(group_msg(3, 10, "STIR 301234567", reply_to=2))
        h.handle(group_msg(4, 77, "Klientni marshrutingizga qo'shdim", "op_saida", reply_to=3))
        self.login("viewer")
        r = self.call("get", "support/analytics/?days=30")
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        row = next(x for x in d["staff"] if x["name"] == "Saida")
        self.assertEqual((row["answers"], row["clarifications"], row["candidates"]), (1, 1, 1))
        self.assertEqual(d["top_asks"][0]["count"], 1)
        self.assertEqual(d["questions"], 1)
