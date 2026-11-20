"""Aniq vaqt hisobi: Toshkent kuni (GMT+5), istalgan sana oralig'i, birinchi javob (bot yoki xodim), Telegram vaqti."""
import datetime as dt
from unittest import mock

from django.utils import timezone

from . import workload
from .models import Group, Message, TgUser
from .tests import group_msg
from .tests_v6 import FlowBase

UTC = dt.timezone.utc


class PeriodTests(FlowBase):
    def test_days_start_at_tashkent_midnight(self):
        now = dt.datetime(2026, 11, 20, 3, 0, tzinfo=UTC)  # Toshkentda 08:00
        with mock.patch.object(timezone, "now", return_value=now):
            start, end, info = workload.period({"days": "1"})
        self.assertEqual(start, dt.datetime(2026, 11, 19, 19, 0, tzinfo=UTC))  # 20-noyabr 00:00 Toshkent
        self.assertEqual(end, dt.datetime(2026, 11, 20, 19, 0, tzinfo=UTC))
        self.assertEqual(info["from"], "2026-11-20")
        with mock.patch.object(timezone, "now", return_value=now):
            start, end, info = workload.period({"from": "2026-11-18", "to": "2026-11-19"})
        self.assertEqual((info["days"], start, end), (2, dt.datetime(2026, 11, 17, 19, 0, tzinfo=UTC), dt.datetime(2026, 11, 19, 19, 0, tzinfo=UTC)))


class FirstResponseTests(FlowBase):
    def test_first_response_is_bot_when_bot_was_faster(self):
        g = Group.objects.create(bot=self.bot, chat_id=-5, title="G")
        u = TgUser.objects.create(tg_id=1, name="A")
        t0 = timezone.now() - dt.timedelta(hours=1)
        q1 = Message.objects.create(bot=self.bot, group=g, chat_id=-5, message_id=1, user=u, kind=Message.QUESTION, text="x",
                                    status=Message.ANSWERED, stage="ai", answered_by="bot")
        Message.objects.filter(pk=q1.pk).update(created_at=t0, answered_at=t0 + dt.timedelta(seconds=12))
        q2 = Message.objects.create(bot=self.bot, group=g, chat_id=-5, message_id=2, user=u, kind=Message.QUESTION, text="y",
                                    status=Message.ANSWERED, stage="staff")
        Message.objects.filter(pk=q2.pk).update(created_at=t0)
        from zona.models import Department, Member
        m = Member.objects.create(name="S", role="r", department=Department.objects.create(name="D"), telegram="s1")
        staff = TgUser.objects.create(tg_id=2, name="S", member=m)
        for i, (q, mins) in enumerate([(q1, 45), (q2, 3)]):
            a = Message.objects.create(bot=self.bot, group=g, chat_id=-5, message_id=10 + i, user=staff, kind=Message.STAFF,
                                       question=q, text="javob")
            Message.objects.filter(pk=a.pk).update(created_at=t0 + dt.timedelta(minutes=mins))
        start, end, info = workload.period({"days": "2"})
        d = workload.workload(start, end, info)
        self.assertEqual(d["answered_any"], 2)
        b = {x["label"]: x["n"] for x in d["buckets"]}
        self.assertEqual((b["10s–1m"], b["1–5m"], b["15–60m"]), (1, 1, 0))  # 12 s (bot, 45 daq emas) va 3 daq (xodim)
        self.assertEqual(d["human_median"], 180.0)  # xodim javobi — faqat bot yopmagan savol bo'yicha


class StampTests(FlowBase):
    def test_question_time_is_telegram_send_time(self):
        sent = int(timezone.now().timestamp()) - 20  # bot xabarni 20 s kechikib oldi
        m = group_msg(77, 10, "Prbc da kilent qoshish chiqmayapti")
        m["message"]["date"] = sent
        self.h().handle(m)
        q = Message.objects.get(message_id=77)
        self.assertEqual(int(q.created_at.timestamp()), sent)
