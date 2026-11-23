"""Savol ochiq qolmasin: xodim reaksiyasi — qabul qildi; "✅ Javob berildi" / "⏳ Jarayonda"; savol egasi belgilamasa —
xodimdan so'rash; "hal bo'lmadi" — qayta so'rash va eslatish; tuzatilgan javobni qayta tekshirish; tahlil doirasi."""
import datetime as dt
from unittest import mock

from django.utils import timezone

from zona.models import Department, Member

from . import resolution, review
from .models import Group, Message, Settings, TgUser
from .tests_v6 import FlowBase
from .tests_v20 import NOON

STAFF = {"id": 2, "username": "test_op", "first_name": "Test"}


def reaction(mid, user=None, emoji="👍", n=1, chat=-100):
    return {"update_id": 700 + n, "message_reaction": {
        "chat": {"id": chat, "type": "supergroup"}, "message_id": mid, "user": user or STAFF, "date": 0,
        "old_reaction": [], "new_reaction": [{"type": "emoji", "emoji": emoji}] if emoji else []}}


def press(uid, data, n=1, msg_id=1, username=""):
    return {"update_id": 900 + n, "callback_query": {"id": f"c{n}", "data": data,
                                                     "from": {"id": uid, "username": username},
                                                     "message": {"message_id": msg_id, "chat": {"id": -100}}}}


class OpenBase(FlowBase):
    def setUp(self):
        super().setUp()
        Settings.load()
        Settings.objects.update(confirm_resolution=True, confirm_after=10, ask_staff_after=60, reask_after=120,
                                remind_max=2, react_accept=True)
        self.bot.admin_chat_id = 555
        self.bot.save()
        self.g = Group.objects.create(bot=self.bot, chat_id=-100, title="ROP")
        dep = Department.objects.create(name="IT o")
        self.member = Member.objects.create(name="Test Xodim", role="r", department=dep, telegram="test_op")
        self.asker = TgUser.objects.create(tg_id=1, name="Agent", username="agent1")

    def q(self, mid=5, **kw):
        kw.setdefault("status", Message.ESCALATED)
        q = Message.objects.create(bot=self.bot, group=self.g, chat_id=-100, message_id=mid, user=self.asker,
                                   source="live", kind=Message.QUESTION, text="Skidka yoqib bering", **kw)
        Message.objects.filter(pk=q.pk).update(created_at=NOON - dt.timedelta(hours=1))
        q.refresh_from_db()
        return q

    def at(self, minutes):
        return mock.patch.object(timezone, "now", return_value=NOON + dt.timedelta(minutes=minutes))


class ReactionTests(OpenBase):
    def test_staff_reaction_accepts_and_asker_is_asked_later(self):
        q = self.q()
        with self.at(0):
            self.h().handle(reaction(5))
        q.refresh_from_db()
        self.assertEqual((q.status, q.stage, q.answered_by), (Message.ANSWERED, "react", "Test Xodim"))
        self.assertEqual(q.handler.username, "test_op")
        self.assertEqual(resolution.ask_pending(self.tg, now=NOON + dt.timedelta(minutes=5)), 0)  # hali erta
        self.assertEqual(resolution.ask_pending(self.tg, now=NOON + dt.timedelta(minutes=11)), 1)
        prompt = self.tg.sent[-1]
        self.assertIn("@agent1", prompt["text"])
        datas = [b["callback_data"] for row in prompt["buttons"] for b in row]
        self.assertEqual(datas, [f"rs:{q.id}:1", f"rs:{q.id}:0", f"rs:{q.id}:a", f"rs:{q.id}:w"])
        q.refresh_from_db()
        self.assertEqual(q.resolution, "asked")
        self.assertEqual(q.next_ask_at, NOON + dt.timedelta(minutes=11 + 60))  # belgilamasa — xodimdan so'raladi

    def test_ignored_reactions(self):
        q = self.q()
        self.h().handle(reaction(5, user={"id": 1, "username": "agent1", "first_name": "A"}))  # savol egasi
        self.h().handle(reaction(5, user={"id": 9, "username": "someone", "first_name": "B"}, n=2))  # xodim emas
        self.h().handle(reaction(5, emoji=None, n=3))  # reaksiya olib tashlandi
        q.refresh_from_db()
        self.assertEqual((q.status, q.handler_id), (Message.ESCALATED, None))
        Settings.objects.update(react_accept=False)
        self.h().handle(reaction(5, n=4))
        q.refresh_from_db()
        self.assertIsNone(q.handler_id)

    def test_reaction_on_bot_answer_keeps_bot_stage(self):
        q = self.q(status=Message.ANSWERED, stage="ai", answered_by="bot", bot_reply_id=77, answer_text="x")
        self.h().handle(reaction(77))  # botning javobiga reaksiya — savolga tegishli
        q.refresh_from_db()
        self.assertEqual((q.stage, q.answered_by), ("ai", "bot"))
        self.assertIsNotNone(q.accepted_at)


class StaffButtonsTests(OpenBase):
    def setUp(self):
        super().setUp()
        self.qq = self.q(status=Message.ANSWERED, answered_by="Test Xodim", answered_at=NOON - dt.timedelta(minutes=15))
        resolution.ask_pending(self.tg, now=NOON)
        self.qq.refresh_from_db()

    def test_staff_answered_closes_for_both(self):
        Message.objects.filter(pk=self.qq.pk).update(staff_msg_id=4444)
        self.h().handle(press(2, f"rs:{self.qq.id}:a", username="test_op"))
        self.qq.refresh_from_db()
        self.assertEqual((self.qq.resolution, self.qq.resolved_by), ("yes", "xodim: Test Xodim"))
        closed = {e["id"] for e in self.tg.edits}
        self.assertTrue({self.qq.confirm_msg_id, 4444} <= closed)  # savol egasidagi va xodimdagi so'rov yopildi
        self.assertIn("javob berildi", self.tg.edits[-1]["text"])
        self.assertIsNone(self.qq.next_ask_at)

    def test_who_can_press_what(self):
        self.h().handle(press(2, f"rs:{self.qq.id}:0", username="test_op"))  # xodim "yo'q" bosa olmaydi
        self.h().handle(press(1, f"rs:{self.qq.id}:w", n=2, username="agent1"))  # savol egasi "jarayonda" bosa olmaydi
        self.h().handle(press(9, f"rs:{self.qq.id}:1", n=3, username="someone"))  # begona
        self.qq.refresh_from_db()
        self.assertEqual(self.qq.resolution, "asked")
        self.assertEqual(len(self.tg.callbacks), 3)
        self.h().handle(press(2, f"rs:{self.qq.id}:1", n=4, username="test_op"))  # xodim ✅ — javob berildi
        self.qq.refresh_from_db()
        self.assertEqual(self.qq.resolution, "yes")

    def test_work_then_reminders_then_admin(self):
        with self.at(0):
            self.h().handle(press(2, f"rs:{self.qq.id}:w", msg_id=self.qq.confirm_msg_id, username="test_op"))
        self.qq.refresh_from_db()
        self.assertEqual(self.qq.resolution, "work")
        self.assertEqual(self.qq.next_ask_at, NOON + dt.timedelta(minutes=120))
        self.assertIn("Jarayonda", self.tg.edits[-1]["text"])
        self.assertTrue(self.tg.edits[-1]["buttons"])  # tugmalar qoladi
        n0 = len(self.tg.sent)
        self.assertEqual(resolution.followups(self.tg, now=NOON + dt.timedelta(minutes=60)), 0)  # hali erta
        self.assertEqual(resolution.followups(self.tg, now=NOON + dt.timedelta(minutes=121)), 1)
        self.assertIn("@test_op", self.tg.sent[-1]["text"])
        self.assertEqual(self.tg.sent[-1]["reply_to"], 5)
        self.assertEqual(resolution.followups(self.tg, now=NOON + dt.timedelta(minutes=242)), 1)
        # remind_max=2 marta eslatildi — keyingisi admin chatiga, so'ng to'xtaydi
        self.assertEqual(resolution.followups(self.tg, now=NOON + dt.timedelta(minutes=363)), 0)
        self.assertTrue(any(m["chat"] == 555 and "ochiq qolmoqda" in m["text"] for m in self.tg.sent))
        self.qq.refresh_from_db()
        self.assertIsNone(self.qq.next_ask_at)
        self.assertEqual(len([m for m in self.tg.sent[n0:] if m["chat"] == -100]), 2)

    def test_asker_silent_staff_is_asked(self):
        Message.objects.create(bot=self.bot, group=self.g, chat_id=-100, message_id=6, question=self.qq, source="live",
                               kind=Message.STAFF, text="Yoqib berdim", status=Message.CLOSED,
                               user=TgUser.objects.create(tg_id=2, username="test_op", name="T", member=self.member))
        self.assertEqual(resolution.followups(self.tg, now=NOON + dt.timedelta(minutes=61)), 1)
        last = self.tg.sent[-1]
        self.assertIn("@test_op", last["text"])
        self.assertIn("@agent1", last["text"])
        self.qq.refresh_from_db()
        self.assertEqual(self.qq.staff_msg_id, 1000 + len(self.tg.sent))
        # savol egasi endi bosdi — ikkala so'rov ham yopiladi
        self.h().handle(press(1, f"rs:{self.qq.id}:1", username="agent1"))
        self.assertEqual({e["id"] for e in self.tg.edits[-2:]}, {self.qq.confirm_msg_id, self.qq.staff_msg_id})

    def test_night_no_followups(self):
        night = dt.datetime(2026, 11, 20, 18, 0, tzinfo=dt.timezone.utc)
        Message.objects.filter(pk=self.qq.pk).update(next_ask_at=night - dt.timedelta(hours=1))
        self.assertEqual(resolution.followups(self.tg, now=night), 0)


class NotResolvedTests(OpenBase):
    def test_no_reasks_asker_and_mentions_staff_then_staff_reply_reopens(self):
        q = self.q(status=Message.ANSWERED, answered_by="Test Xodim", answered_at=NOON - dt.timedelta(minutes=15),
                   handler=TgUser.objects.create(tg_id=2, username="test_op", name="T", member=self.member))
        resolution.ask_pending(self.tg, now=NOON)
        with self.at(0):
            self.h().handle(press(1, f"rs:{q.id}:0", username="agent1"))
        q.refresh_from_db()
        self.assertEqual((q.resolution, q.status), ("no", Message.ESCALATED))
        self.assertEqual(q.next_ask_at, NOON + dt.timedelta(minutes=120))
        self.assertEqual(resolution.followups(self.tg, now=NOON + dt.timedelta(minutes=121)), 1)
        text = self.tg.sent[-1]["text"]
        self.assertIn("@agent1", text)  # savol egasidan qayta so'raldi
        self.assertIn("@test_op", text)  # xodim eslatildi
        # xodim javob yozdi — savol egasidan yana "hal bo'ldimi?" so'raladi
        from .tests import group_msg
        with self.at(130):
            self.h().handle(group_msg(60, 2, "Tekshirdim, skidka yoqildi", username="test_op", reply_to=5))
        q.refresh_from_db()
        self.assertEqual((q.resolution, q.status), ("", Message.ANSWERED))
        self.assertIn(q.pk, [x.pk for x in resolution.due(now=NOON + dt.timedelta(minutes=141))])

    def test_admin_no_is_final_and_not_reminded(self):
        q = self.q(status=Message.ANSWERED, answered_by="Test Xodim")
        resolution.admin_mark(q, "no", "Admin")
        q.refresh_from_db()
        self.assertIsNone(q.next_ask_at)


class RefixTests(OpenBase):
    def setUp(self):
        super().setUp()
        Settings.objects.update(feedback_buttons=True, review_button=True, answer_test_note=True)
        self.qq = self.q(status=Message.ANSWERED, answered_by="bot", stage="ai", answer_text="Eski javob", bot_reply_id=300,
                         review="wrong", answer_hidden=True)

    def test_fixed_answer_has_checks_and_can_be_flagged_and_refixed(self):
        review.fix(self.qq, "Birinchi tuzatish", "Admin", tg=self.tg)
        self.qq.refresh_from_db()
        self.assertEqual((self.qq.fixed_msg_id, self.qq.review), (300, "fixed"))
        e = self.tg.edits[-1]
        self.assertIn("test rejimi", e["text"])  # tuzatilgan javobda ham test rejimi yozuvi
        self.assertEqual([b["callback_data"] for r in e["buttons"] for b in r],
                         [f"fb:{self.qq.id}:1", f"fb:{self.qq.id}:-1", f"bad:{self.qq.id}"])
        # kimdir tuzatilgan javobni ham xato dedi — yashiriladi, admin chatiga "tuzatilgan javob ham xato"
        self.h().handle(press(9, f"bad:{self.qq.id}", username="someone", msg_id=300))
        self.qq.refresh_from_db()
        self.assertEqual((self.qq.review, self.qq.answer_hidden), ("wrong", True))
        self.assertIn("yangilanishga", self.tg.edits[-1]["text"])
        self.assertTrue(any(m["chat"] == 555 and "Tuzatilgan javob ham xato" in m["text"] for m in self.tg.sent))
        # qayta tuzatish — o'sha xabar yangilanadi, yangi xabar yozilmaydi
        n = len(self.tg.sent)
        review.fix(self.qq, "Ikkinchi tuzatish", "Admin", tg=self.tg)
        self.qq.refresh_from_db()
        self.assertEqual((self.qq.fixed_msg_id, self.qq.fixed_text, self.qq.answer_hidden), (300, "Ikkinchi tuzatish", False))
        self.assertIn("Ikkinchi tuzatish", self.tg.edits[-1]["text"])
        self.assertEqual(len(self.tg.sent), n)
        # "aslida to'g'ri" — oxirgi (tuzatilgan) javob qaytariladi, asl xato javob emas
        Message.objects.filter(pk=self.qq.pk).update(answer_hidden=True)
        self.qq.refresh_from_db()
        review.restore(self.tg, self.qq)
        self.assertIn("Ikkinchi tuzatish", self.tg.edits[-1]["text"])

    def test_asker_thumbs_down_on_fixed(self):
        review.fix(self.qq, "Tuzatish", "Admin", tg=self.tg)
        Message.objects.filter(pk=self.qq.pk).update(feedback=-1)  # asl javobga allaqachon 👎 bosgan
        self.h().handle(press(1, f"fb:{self.qq.id}:-1", username="agent1", msg_id=300))
        self.qq.refresh_from_db()
        self.assertEqual((self.qq.review, self.qq.resolution), ("wrong", "no"))


class AnalyticsScopeTests(OpenBase):
    def test_history_test_groups_and_duplicates_are_excluded(self):
        test_g = Group.objects.create(bot=self.bot, chat_id=-200, title="VAZIFALAR", in_analytics=False)
        mk = Message.objects.create
        mk(bot=self.bot, group=self.g, chat_id=-100, message_id=1, kind="question", text="a", source="live",
           status=Message.ANSWERED, stage="ai", answered_by="bot", resolution="yes")
        mk(bot=self.bot, group=self.g, chat_id=-100, message_id=2, kind="question", text="b", source="live",
           status=Message.ANSWERED, stage="react", answered_by="Test Xodim", resolution="work")
        mk(bot=self.bot, group=self.g, chat_id=-100, message_id=3, kind="question", text="c", source="live",
           status=Message.ESCALATED)
        mk(bot=self.bot, group=self.g, chat_id=-100, message_id=4, kind="question", text="c", source="live",
           status=Message.CLOSED, stage="dup")
        mk(bot=self.bot, group=self.g, chat_id=-100, message_id=5, kind="question", text="h", source="history",
           status=Message.ANSWERED, stage="staff")
        mk(bot=self.bot, group=test_g, chat_id=-200, message_id=6, kind="question", text="t", source="live",
           status=Message.ANSWERED, stage="ai", answered_by="bot")
        self.login("viewer")
        r = self.call("get", "support/analytics/?days=1").json()
        self.assertEqual(r["questions"], 3)
        s = r["summary"]
        self.assertEqual((s["total"], s["bot"], s["staff"], s["react"], s["unanswered"]), (3, 1, 1, 1, 1))
        self.assertEqual((r["excluded"]["history"], r["excluded"]["groups_off"], r["excluded"]["duplicates"]), (1, 1, 1))
        self.assertEqual(r["excluded"]["groups"], ["VAZIFALAR"])
        self.assertEqual((r["resolution"]["yes"], r["resolution"]["work"], r["resolution"]["unknown"]), (1, 1, 1))
        w = self.call("get", "support/analytics/workload/?days=1").json()
        self.assertEqual(sum(g["questions"] for g in w["groups"]), 3)

    def test_group_toggle_admin_only(self):
        self.login("viewer")
        self.assertEqual(self.call("patch", f"support/groups/{self.g.id}/", {"in_analytics": False}).status_code, 403)
        self.login("admin")
        r = self.call("patch", f"support/groups/{self.g.id}/", {"in_analytics": False})
        self.assertEqual((r.status_code, r.json()["in_analytics"]), (200, False))


class StockShortageTests(FlowBase):
    """Skladda qoldiq yetarli emas (ProTarget «Заказ не оформлен»): matn umumiy bo'lsa ham ekrandagi aniq xabar hal qiladi."""

    def setUp(self):
        super().setUp()
        from .models import Entry
        self.e = Entry.objects.create(
            kind=Entry.TEMPLATE, title="ProTarget: «Заказ не оформлен» — skladda qoldiq yetarli emas", status=Entry.APPROVED,
            triggers=["недостаточно остатка", "не оформлен: на складе", "заказ не оформлен", "ostatka && yetarli emas"],
            extract=[r"Заказ\s*№\s*(?P<zakaz>\d{4,})", r"на складе\s*[«\"](?P<sklad>[^»\"]{1,60})[»\"]"],
            answer="Zakaz rasmiylashtirilmadi.\nZakaz: **№{zakaz}**\nSklad: **{sklad}**\n1) Zakazni oching.")
        self.ocr = ("Заказ не оформлен\nЗаказ №381122 не оформлен: на складе «0.2 Heinz» недостаточно остатка для 3 "
                    "товарных позиций. Откройте заказ, чтобы посмотреть список.\nОткрыть")

    def test_generic_text_with_specific_screen(self):
        from . import engine
        d = engine.decide("zakaz o'tmayapti\n" + self.ocr, "uz", text="zakaz o'tmayapti", ocr=self.ocr, fast=True)
        self.assertEqual((d.stage, d.entry.pk), ("template", self.e.pk))
        self.assertIn("№381122", d.text)
        self.assertIn("0.2 Heinz", d.text)

    def test_unrelated_text_is_not_overridden(self):
        from . import engine
        d = engine.decide("skidka yoqib bering\n" + self.ocr, "uz", text="skidka yoqib bering", ocr=self.ocr, fast=True)
        self.assertFalse(d is not None and d.entry is not None and d.entry.pk == self.e.pk)

    def test_latin_text_only(self):
        from . import engine
        d = engine.decide("zakaz ketmayapti ostatka yetarli emas deyapti", "uz", fast=True)
        self.assertEqual(d.entry.pk, self.e.pk)
        self.assertNotIn("Sklad", d.text)  # topilmagan maydon qatori tashlab ketiladi
