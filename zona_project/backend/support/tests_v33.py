"""Agent so'rovni mas'ulning o'ziga yo'llasa — "X bajaradi" takrorlanmaydi: yetkazildi, yuklama va taxminiy vaqt;
so'rov nazoratda: xodimdan "bajarildimi?" (qancha vaqtdan beri kutayotgani bilan), keyin agentdan "hal bo'ldimi?"."""
import datetime as dt

from zona.models import Member

from . import engine, resolution
from .models import Entry, Message, TgUser
from .tests import group_msg
from .tests_v20 import NOON
from .tests_v27 import OpenBase


class HandoffAckTests(OpenBase):
    def setUp(self):
        super().setUp()
        self.said, _ = Member.objects.update_or_create(name="Saidabror", defaults={"role": "Operator", "department": self.member.department,
                                                                                  "telegram": "said_t"})
        self.said_u = TgUser.objects.create(tg_id=4, username="said_t", name="Said", member=self.said)
        self.entry = Entry.objects.create(kind=Entry.FAQ, title="Aksiyani yoqib bering", questions=["aksiyani yoqib bering"],
                                          answer="Aksiyani **Saidabror** yoqadi.", status=Entry.APPROVED, responsible=self.said)
        engine._PEOPLE_IDX.update(at=0.0, rows=[])

    def ask(self, mid, text):
        with self.at(0):
            self.h().handle(group_msg(mid, 1, text, username="agent1"))
        return Message.objects.get(message_id=mid, kind="question")

    def test_addressed_request_is_acknowledged_and_tracked(self):
        q = self.ask(30, "aksiyani yoqib bering @said_t")
        reply = self.tg.sent[-1]["text"]
        self.assertIn("yetkazildi", reply)
        self.assertNotIn("yoqadi", reply)
        self.assertIn("hal bo'ldimi", reply)
        self.assertEqual((q.stage, q.status, q.resolution, q.handler_id), ("handoff", Message.ESCALATED, "asked", self.said_u.pk))
        # 1 soatdan keyin — Saidabrorning o'zidan, qancha vaqtdan beri kutayotgani bilan
        self.assertEqual(resolution.followups(self.tg, now=NOON + dt.timedelta(minutes=61)), 1)
        prompt = self.tg.sent[-1]["text"]
        self.assertIn("@said_t", prompt)
        self.assertIn("kutyapti", prompt)
        self.assertIn("soat", prompt)
        # Saidabror javob yozdi — endi agentdan "hal bo'ldimi?" so'raladi
        with self.at(70):
            self.h().handle(group_msg(60, 4, "Aksiya yoqildi, tekshirib ko'ring 10 blokdan", username="said_t", reply_to=30))
        q.refresh_from_db()
        self.assertEqual(q.resolution, "")
        self.assertIn(q.pk, [x.pk for x in resolution.due(now=NOON + dt.timedelta(minutes=81))])

    def test_not_addressed_keeps_instruction(self):
        self.ask(31, "aksiyani yoqib bering")
        self.assertIn("yoqadi", self.tg.sent[-1]["text"])

    def test_workload_is_told(self):
        for i in range(4):
            Message.objects.create(bot=self.bot, group=self.g, chat_id=-100, message_id=500 + i, kind="question", text="x",
                                   source="live", status=Message.ESCALATED, resolution="asked", handler=self.said_u, user=self.asker)
        self.ask(32, "Saidabror aksiyani yoqib bering iltimos")
        reply = self.tg.sent[-1]["text"]
        self.assertIn("so'rovlar ko'p (4 ta navbatda)", reply)

    def test_escalated_question_is_tracked(self):
        with self.at(0):
            self.h().handle(group_msg(33, 1, "qandaydir mutlaqo notanish muammo zzqx bor", username="agent1"))
        q = Message.objects.get(message_id=33, kind="question")
        if q.status == Message.ESCALATED:
            self.assertEqual(q.resolution, "asked")
            self.assertIsNotNone(q.next_ask_at)

    def test_elapsed_text(self):
        q = Message(created_at=NOON, lang="uz")
        self.assertEqual(resolution.elapsed(q, NOON + dt.timedelta(minutes=135)), "2 soat 15 daqiqa")
        self.assertEqual(resolution.elapsed(q, NOON + dt.timedelta(days=3, hours=4)), "3 kun 4 soat")
        q.lang = "ru"
        self.assertEqual(resolution.elapsed(q, NOON + dt.timedelta(minutes=5)), "5 мин")
